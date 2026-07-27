"""MCP Server for CodeNexus context engine.

This module owns the *domain logic* (indexing, pipeline, memory, license
gating). The standalone MCP transport layer in ``mcp_server.py`` reuses these
methods so there is a single source of truth for behaviour.
"""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from .graph import DependencyGraph, Edge, Node
from .license import LicenseManager, get_license
from .llm import LLMConfig, LocalLLM
from .memory import SessionMemory, get_memory
from .parser import CodeParser, create_capsule

# Map file extensions to the parser language key.
EXT_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cs": "csharp",
}


class CodeNexusServer:
    """Core engine: indexing, pipeline, and feature gating."""

    def __init__(
        self,
        workspace_path: Path,
        max_workers: int = 4,
        llm_model_path: str | None = None,
        use_llm: bool = False,
        license_manager: LicenseManager | None = None,
    ):
        self.workspace = Path(workspace_path)
        self.db_path = self.workspace / ".codenexus" / "index.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.graph = DependencyGraph(self.db_path)
        self.parser = CodeParser()
        self.server = Server("codenexus", version="1.1.32")
        self.max_workers = max_workers

        # --- License gating (single source of truth) ---
        self.license_mgr = license_manager or get_license()
        self.tier = self.license_mgr.get_tier()
        self.enabled_languages = self._resolve_languages()
        self.max_nodes_limit = self.license_mgr.get_limit("max_nodes")
        self.memory_enabled = self.license_mgr.has_feature("memory")
        self.llm_enabled = bool(use_llm and self.license_mgr.has_feature("llm"))

        # --- LLM (only when licensed + requested) ---
        self.llm: LocalLLM | None = None
        if self.llm_enabled and llm_model_path:
            self.llm = LocalLLM(LLMConfig(model_path=llm_model_path))
            self.llm.load_model()

        # --- Session memory (only when licensed) ---
        self.memory: SessionMemory | None = None
        if self.memory_enabled:
            self.memory = get_memory(self.workspace / ".codenexus" / "memory.db")
        self._session_id: str | None = None

        # File hash cache for incremental indexing
        self.cache_path = self.db_path.parent / "cache.json"
        self.file_cache = self._load_cache()

        self._setup_tools()

    # ------------------------------------------------------------------ #
    # License helpers
    # ------------------------------------------------------------------ #
    def _resolve_languages(self) -> set[str] | None:
        """Return enabled language set, or None for 'all'."""
        raw = self.license_mgr.get_limit("languages")
        if raw == "all" or raw is None:
            return None
        if isinstance(raw, (list, set, tuple)):
            return set(raw)
        return None

    def is_language_enabled(self, language: str) -> bool:
        if self.enabled_languages is None:
            return True
        return language in self.enabled_languages

    # ------------------------------------------------------------------ #
    # Session memory helpers
    # ------------------------------------------------------------------ #
    def start_session(self, name: str = "cli-session") -> str | None:
        """Start a tracked session (no-op when memory is disabled)."""
        if not self.memory:
            return None
        session = self.memory.create_session(name)
        self._session_id = session.id
        return session.id

    def end_session(self, summary: str = "") -> None:
        if self.memory and self._session_id:
            self.memory.end_session(self._session_id, summary)
            self._session_id = None

    def _record_file_change(self, file_path: str, change_type: str, line_count: int = 0):
        if self.memory and self._session_id:
            self.memory.record_file_change(self._session_id, file_path, change_type, line_count)

    def _record_intent(self, task: str, intent: str):
        if self.memory and self._session_id:
            self.memory.add_memory(self._session_id, key=f"task:{task[:80]}", value=intent)

    # ------------------------------------------------------------------ #
    # Cache / files
    # ------------------------------------------------------------------ #
    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            try:
                with open(self.cache_path) as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        try:
            with open(self.cache_path, "w") as f:
                json.dump(self.file_cache, f, indent=2)
        except Exception:
            pass

    def _get_file_hash(self, file_path: Path) -> str:
        try:
            content = file_path.read_bytes()
            return hashlib.md5(content).hexdigest()
        except Exception:
            return ""

    def list_tool_definitions(self) -> list[Tool]:
        """Return the MCP tool definitions (shared with the transport layer)."""
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

    async def dispatch_tool(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Dispatch a tool call (shared with the transport layer)."""
        if name == "run_pipeline":
            return await self._run_pipeline(arguments)
        elif name == "get_context_capsule":
            return await self._get_context_capsule(arguments)
        elif name == "get_skeleton":
            return await self._get_skeleton(arguments)
        elif name == "index_status":
            return await self._index_status()
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    def _setup_tools(self):
        @self.server.list_tools()
        async def list_tools():
            return self.list_tool_definitions()

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]):
            return await self.dispatch_tool(name, arguments)

    # ------------------------------------------------------------------ #
    # Pipeline (pure data + MCP transport)
    # ------------------------------------------------------------------ #
    def _pipeline_data(self, args: dict) -> dict:
        """Core pipeline logic. Returns a plain dict (no transport concern)."""
        task = args.get("task", "")
        max_tokens = int(args.get("max_tokens", 8000))

        intent = self.llm.analyze_intent(task) if self.llm else "explore"
        self._record_intent(task, intent)

        keywords = task.lower().split()
        nodes: list[Node] = []
        seen_ids: set[str] = set()

        for keyword in keywords:
            results = self.graph.search_nodes(keyword, limit=10)
            for node in results:
                if node.id not in seen_ids:
                    nodes.append(node)
                    seen_ids.add(node.id)

        def relevance_score(node):
            score = 0
            text = f"{node.name} {node.content} {node.signature}".lower()
            for keyword in keywords:
                if keyword in text:
                    score += 1
            return score

        nodes.sort(key=relevance_score, reverse=True)
        nodes = nodes[:20]

        result = {
            "task": task,
            "intent": intent,
            "pivot_files": [],
            "skeletons": [],
            "token_estimate": 0,
        }

        tokens_used = 0
        for node in nodes:
            if tokens_used >= max_tokens:
                break

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
        return result

    async def _run_pipeline(self, args: dict) -> list[TextContent]:
        result = self._pipeline_data(args)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    async def _get_context_capsule(self, args: dict) -> list[TextContent]:
        query = args.get("query", "")
        max_tokens = int(args.get("max_tokens", 8000))

        # Tokenize the query like the pipeline does, so multi-word queries
        # (e.g. "authentication login") actually match something.
        keywords = query.lower().split()
        nodes: list[Node] = []
        seen_ids: set[str] = set()
        for keyword in keywords:
            for node in self.graph.search_nodes(keyword, limit=10):
                if node.id not in seen_ids:
                    nodes.append(node)
                    seen_ids.add(node.id)

        capsule_parts = []
        tokens_used = 0

        for node in nodes:
            if tokens_used >= max_tokens:
                break
            skeleton = create_capsule(node.content)
            capsule_parts.append(f"=== {node.file_path}::{node.name} ===\n{skeleton}")
            tokens_used += len(skeleton.split()) * 1.3

        result = {
            "capsule": "\n\n".join(capsule_parts),
            "token_estimate": int(tokens_used),
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    async def _get_skeleton(self, args: dict) -> list[TextContent]:
        file_path = args.get("file_path", "")
        rows = self.graph.conn.execute(
            "SELECT id, file_path, name, node_type, start_line, end_line, "
            "content, signature, centrality_score FROM nodes WHERE file_path = ?",
            (file_path,),
        ).fetchall()

        if not rows:
            return [TextContent(type="text", text=f"No nodes found for {file_path}")]

        skeletons = []
        for row in rows:
            node = Node.from_row(row)
            skeletons.append(f"{node.node_type} {node.name}: {node.signature}")

        result = {"skeletons": skeletons}
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    async def _index_status(self) -> list[TextContent]:
        node_count = self.graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = self.graph.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        file_count = self.graph.conn.execute(
            "SELECT COUNT(DISTINCT file_path) FROM nodes"
        ).fetchone()[0]

        result = {
            "nodes": node_count,
            "edges": edge_count,
            "files": file_count,
            "cached_files": len(self.file_cache),
            "status": "healthy",
            "tier": self.tier.value,
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    # ------------------------------------------------------------------ #
    # Indexing
    # ------------------------------------------------------------------ #
    def _get_source_files(self) -> list[Path]:
        source_files = []
        for ext in EXT_TO_LANGUAGE:
            for file_path in self.workspace.rglob(f"*{ext}"):
                if not any(
                    skip in file_path.parts
                    for skip in {
                        "node_modules",
                        ".git",
                        "__pycache__",
                        "venv",
                        ".venv",
                        "dist",
                        "build",
                        ".codenexus",
                    }
                ):
                    source_files.append(file_path)
        return source_files

    def _parse_single_file(self, file_path: Path) -> tuple[list[Node], list[Edge]]:
        try:
            return self.parser.parse_file(file_path)
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return [], []

    def index_workspace(self, incremental: bool = True) -> int:
        """Index all files, respecting license language + node limits."""
        source_files = self._get_source_files()

        if incremental:
            files_to_index = []
            for file_path in source_files:
                file_hash = self._get_file_hash(file_path)
                file_key = str(file_path.relative_to(self.workspace))
                if self.file_cache.get(file_key) != file_hash:
                    files_to_index.append(file_path)
                    self.file_cache[file_key] = file_hash

            existing_files = {str(f.relative_to(self.workspace)) for f in source_files}
            deleted_files = [k for k in self.file_cache.keys() if k not in existing_files]
            for deleted in deleted_files:
                del self.file_cache[deleted]

            if not files_to_index:
                print("No files changed since last index")
                return 0
        else:
            files_to_index = source_files

        # Apply license language filter up-front so excluded languages are
        # never parsed (cheaper + enforces tier limits).
        allowed = [
            f
            for f in files_to_index
            if self.is_language_enabled(EXT_TO_LANGUAGE.get(f.suffix, ""))
        ]
        skipped = len(files_to_index) - len(allowed)
        if skipped:
            print(
                f"Skipped {skipped} file(s): language not enabled for tier '{self.tier.value}'"
            )

        print(f"Indexing {len(allowed)} files...")
        indexed = 0
        parse_results: list[tuple[Path, list[Node], list[Edge]]] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(self._parse_single_file, file_path): file_path
                for file_path in allowed
            }
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    nodes, edges = future.result()
                    parse_results.append((file_path, nodes, edges))
                    indexed += 1
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")

        # Enforce max_nodes limit for the current tier.
        node_cap = self.max_nodes_limit
        total_nodes = self.graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        truncated = False
        for file_path, nodes, edges in parse_results:
            for node in nodes:
                if node_cap is not None and total_nodes >= node_cap:
                    truncated = True
                    break
                self.graph.add_node(node)
                total_nodes += 1
            else:
                for edge in edges:
                    self.graph.add_edge(edge)
            # Track indexed file in session memory.
            self._record_file_change(str(file_path), "index", len(nodes))

        if truncated:
            print(
                f"Node limit reached for tier '{self.tier.value}' "
                f"(max_nodes={node_cap}). Some nodes omitted."
            )

        self._save_cache()

        if indexed > 0:
            self.graph.conn.commit()
            print("Computing centrality scores...")
            self.graph.compute_pagerank()
            try:
                self.graph.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            self.graph.conn.commit()

        return indexed

    def clear_index(self):
        """Clear all index data (and session memory if enabled)."""
        self.graph.clear()
        self.file_cache = {}
        self._save_cache()
        if self.memory:
            # Drop the memory database file so it is rebuilt clean.
            try:
                mem_path = self.workspace / ".codenexus" / "memory.db"
                if mem_path.exists():
                    mem_path.unlink()
            except Exception:
                pass
            # Reset the global memory singleton so it is re-created fresh.
            import codenexus.memory as _mem_mod

            _mem_mod._global_memory = None
            self.memory = None
