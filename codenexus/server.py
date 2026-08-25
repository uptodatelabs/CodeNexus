"""MCP Server for CodeNexus context engine."""

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from .graph import DependencyGraph, Edge, Node
from .llm import LLMConfig, LocalLLM
from .parser import CodeParser, create_capsule, detect_language
from .resolver import FileEntry, ImportResolver

logger = logging.getLogger(__name__)

# Directories never indexed. Matched against exact path parts (a directory
# named ``node_modules_backup`` is a legitimate project folder).
SKIP_DIRS = {
    "node_modules",
    "bower_components",
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    "dist",
    "build",
    "target",
    "vendor",
    "coverage",
    "htmlcov",
    "site-packages",
    ".codenexus",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
    ".next",
    ".idea",
    ".vscode",
}

SOURCE_EXTENSIONS = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".cs")

# Bumped when indexing output format changes so existing caches invalidate
# and files get re-indexed under the new scheme once.
CACHE_VERSION = "v2"

_PRESET_LIMITS = {"explore": 15, "debug": 10, "modify": 10}


class CodeNexusServer:
    """MCP server providing context tools for AI agents."""

    def __init__(
        self,
        workspace_path: Path,
        max_workers: int = 4,
        llm_model_path: str | None = None,
        use_llm: bool = False,
    ):
        self.workspace = workspace_path
        self.db_path = workspace_path / ".codenexus" / "index.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.graph = DependencyGraph(self.db_path)
        self.parser = CodeParser()
        self.server = Server("codenexus")
        self.max_workers = max_workers

        # LLM is optional and loaded lazily: constructing the server must not
        # pull hundreds of MB of model weights into RAM as a side effect.
        self.llm: LocalLLM | None = None
        if use_llm:
            self.llm = LocalLLM(LLMConfig(model_path=llm_model_path))

        # File hash cache for incremental indexing
        self.cache_path = self.db_path.parent / "cache.json"
        self.file_cache = self._load_cache()

        self._setup_tools()

    def _load_cache(self) -> dict:
        """Load file hash cache from disk."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Could not load index cache: %s", e)
        return {}

    def _save_cache(self):
        """Save file hash cache to disk."""
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.file_cache, f, indent=2)
        except OSError as e:
            logger.warning("Could not save index cache: %s", e)

    @staticmethod
    def _get_file_hash(file_path: Path) -> str:
        """Calculate MD5 hash of file content."""
        try:
            return hashlib.md5(file_path.read_bytes()).hexdigest()
        except OSError as e:
            logger.debug("Could not hash %s: %s", file_path, e)
            return ""

    def _setup_tools(self):
        """Register MCP tools."""

        @self.server.list_tools()
        async def list_tools():
            return [
                Tool(
                    name="run_pipeline",
                    description="Primary tool: context search + impact analysis in one call",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "task": {"type": "string", "description": "Task description"},
                            "preset": {
                                "type": "string",
                                "enum": ["auto", "explore", "debug", "modify"],
                            },
                            "max_tokens": {"type": "integer", "default": 8000},
                        },
                        "required": ["task"],
                    },
                ),
                Tool(
                    name="get_context_capsule",
                    description="Lightweight context search for relevant code",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "max_tokens": {"type": "integer", "default": 8000},
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="get_skeleton",
                    description="File structure without bodies",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "detail": {
                                "type": "string",
                                "enum": ["minimal", "standard", "detailed"],
                            },
                        },
                        "required": ["file_path"],
                    },
                ),
                Tool(
                    name="index_status",
                    description="Index health and statistics",
                    inputSchema={"type": "object", "properties": {}},
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]):
            if name == "run_pipeline":
                return await self._run_pipeline(arguments)
            elif name == "get_context_capsule":
                return await self._get_context_capsule(arguments)
            elif name == "get_skeleton":
                return await self._get_skeleton(arguments)
            elif name == "index_status":
                return await self._index_status()
            else:
                raise ValueError(f"Unknown tool: {name}")

    async def _run_pipeline(self, args: dict) -> list[TextContent]:
        """Run context search pipeline."""
        task = str(args.get("task", "")).strip()
        if not task:
            raise ValueError("run_pipeline requires a non-empty 'task'")
        max_tokens = int(args.get("max_tokens") or 8000)
        preset = str(args.get("preset", "auto"))

        # Extract keywords from task (drop common stop words that would match
        # nearly every node and drown the ranking).
        stop_words = {
            "the", "a", "an", "to", "for", "of", "in", "on", "and", "or",
            "fix", "add", "make", "please", "should", "with", "that", "this",
        }
        keywords = [w for w in task.lower().split() if w not in stop_words] or task.lower().split()

        # Search for relevant nodes using multiple queries
        nodes = []
        seen_ids = set()

        for keyword in keywords:
            results = self.graph.search_nodes(keyword, limit=10)
            for node in results:
                if node.id not in seen_ids:
                    nodes.append(node)
                    seen_ids.add(node.id)

        # Sort by relevance (simple heuristic: more keywords matched = higher rank)
        def relevance_score(node):
            score = 0
            text = f"{node.name} {node.content} {node.signature}".lower()
            for keyword in keywords:
                if keyword in text:
                    score += 1
            return score

        nodes.sort(key=relevance_score, reverse=True)
        # Presets tune how wide the capsule reaches; "auto" keeps the default.
        limit = _PRESET_LIMITS.get(preset, 20)
        if preset not in ("auto", "explore", "debug", "modify"):
            logger.debug("Unknown preset %r; using default width", preset)
        nodes = nodes[:limit]

        # Build capsule
        result = {"task": task, "pivot_files": [], "skeletons": [], "token_estimate": 0}

        tokens_used = 0
        for node in nodes:
            if tokens_used >= max_tokens:
                break

            # Get full content for top nodes, skeleton for rest
            full_content = node.content
            skeleton = node.signature + "\n..."

            if tokens_used + len(full_content.split()) * 1.3 < max_tokens * 0.6:
                result["pivot_files"].append(
                    {"path": node.file_path, "name": node.name, "content": full_content}
                )
                tokens_used += len(full_content.split()) * 1.3
            else:
                result["skeletons"].append(
                    {"path": node.file_path, "name": node.name, "skeleton": skeleton}
                )
                tokens_used += len(skeleton.split()) * 1.3

        result["token_estimate"] = int(tokens_used)

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    async def _get_context_capsule(self, args: dict) -> list[TextContent]:
        """Get context capsule for a query."""
        query = str(args.get("query", "")).strip()
        if not query:
            raise ValueError("get_context_capsule requires a non-empty 'query'")
        max_tokens = int(args.get("max_tokens") or 8000)

        nodes = self.graph.search_nodes(query, limit=10)

        capsule_parts = []
        tokens_used = 0

        for node in nodes:
            if tokens_used >= max_tokens:
                break

            # Create skeleton
            skeleton = create_capsule(node.content)
            capsule_parts.append(f"=== {node.file_path}::{node.name} ===\n{skeleton}")
            tokens_used += len(skeleton.split()) * 1.3

        return [TextContent(type="text", text="\n\n".join(capsule_parts))]

    async def _get_skeleton(self, args: dict) -> list[TextContent]:
        """Get file skeleton."""
        file_path = str(args.get("file_path", "")).strip()
        if not file_path:
            raise ValueError("get_skeleton requires a non-empty 'file_path'")

        nodes = self.graph.get_file_nodes(file_path)

        if not nodes:
            return [TextContent(type="text", text=f"No nodes found for {file_path}")]

        skeletons = [f"{n.node_type} {n.name}: {n.signature}" for n in nodes]

        return [
            TextContent(type="text", text=f"=== Skeleton: {file_path} ===\n" + "\n".join(skeletons))
        ]

    async def _index_status(self) -> list[TextContent]:
        """Get index status."""
        node_count = self.graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = self.graph.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        file_count = self.graph.conn.execute(
            "SELECT COUNT(DISTINCT file_path) FROM nodes"
        ).fetchone()[0]

        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "nodes": node_count,
                        "edges": edge_count,
                        "files": file_count,
                        "cached_files": len(self.file_cache),
                        "status": "healthy",
                    },
                    indent=2,
                ),
            )
        ]

    def _get_source_files(self) -> list[Path]:
        """Get all source files in workspace."""
        source_files = []
        for file_path in self.workspace.rglob("*"):
            if file_path.suffix.lower() not in SOURCE_EXTENSIONS:
                continue
            if any(part in SKIP_DIRS for part in file_path.parts):
                continue
            source_files.append(file_path)

        return source_files

    def _parse_single_file(
        self, file_path: Path
    ) -> tuple[list[Node], list[Edge]] | None:
        """Parse a single file (for parallel execution).

        Returns None when parsing failed so callers don't record a cache hit
        that would hide the failure from future incremental runs.
        """
        try:
            return self.parser.parse_file(file_path)
        except Exception as e:
            logger.warning("Error parsing %s: %s", file_path, e)
            return None

    def index_workspace(self, incremental: bool = True):
        """
        Index all files in workspace.

        Args:
            incremental: If True, only index changed files
        """
        source_files = self._get_source_files()

        if not incremental:
            # Full re-index starts from a clean slate so entries from deleted
            # or previously mis-parsed files cannot linger.
            self.graph.clear()

        if incremental:
            # Filter to only changed files. Cache keys are version-prefixed so
            # upgrading CodeNexus transparently triggers one full re-index.
            files_to_index: list[tuple[Path, str]] = []
            for file_path in source_files:
                file_hash = self._get_file_hash(file_path)
                file_key = f"{CACHE_VERSION}:{file_path.relative_to(self.workspace)}"
                if self.file_cache.get(file_key) != file_hash:
                    files_to_index.append((file_path, file_key))

            # Purge deleted/renamed files from both cache versions and the DB.
            current_keys = {
                f"{CACHE_VERSION}:{f.relative_to(self.workspace)}" for f in source_files
            }
            stale_keys = [k for k in self.file_cache if k not in current_keys]
            for key in stale_keys:
                del self.file_cache[key]
                rel = key.split(":", 1)[1] if ":" in key else key
                abs_path = str((self.workspace / rel).resolve())
                self.graph.delete_file_nodes(abs_path)

            if not files_to_index:
                logger.info("No files changed since last index")
                return 0
        else:
            files_to_index = [(f, f"{CACHE_VERSION}:{f.relative_to(self.workspace)}") for f in source_files]

        logger.info("Indexing %d files...", len(files_to_index))

        # Parallel parsing
        entries: list[FileEntry] = []
        pending_hashes: list[tuple[str, str]] = []  # (cache_key, md5)
        indexed = 0

        def parse_one(item: tuple[Path, str]):
            file_path, cache_key = item
            return file_path, cache_key, self._parse_single_file(file_path)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for file_path, cache_key, result in executor.map(parse_one, files_to_index):
                if result is None:
                    continue  # failed parse: leave old cache entry untouched
                nodes, raw_edges = result
                self.graph.add_nodes(nodes)
                # Raw import edges are NOT inserted directly: their source is
                # a "{path}::import" pseudo-node. The resolver rewrites them
                # into real module/symbol edges below.

                language = detect_language(file_path)
                entry_symbols = {node.name: node.id for node in nodes}
                raw_imports = [e.target_id for e in raw_edges]
                entries.append(
                    FileEntry(
                        abs_path=file_path,
                        rel_path=str(file_path),
                        language=language or "",
                        symbols=entry_symbols,
                        raw_imports=raw_imports,
                    )
                )
                pending_hashes.append((cache_key, self._get_file_hash(file_path)))
                indexed += 1

        # Rewrite imports into real edges between module/symbol nodes.
        if entries:
            resolver = ImportResolver(self.workspace)
            module_nodes, import_edges = resolver.build(entries)
            self.graph.add_nodes(module_nodes)
            self.graph.add_edges(import_edges)

        # Record hashes only for successfully parsed files.
        for cache_key, file_hash in pending_hashes:
            self.file_cache[cache_key] = file_hash

        # Save cache
        self._save_cache()

        # Compute PageRank after indexing
        if indexed > 0:
            logger.info("Computing centrality scores...")
            self.graph.compute_pagerank()

        return indexed

    def clear_index(self):
        """Clear all index data."""
        self.graph.clear()
        self.file_cache = {}
        self._save_cache()
