"""MCP Server for CodeNexus context engine.

This module owns the *domain logic* (indexing, pipeline, memory, license
gating). The standalone MCP transport layer in ``mcp_server.py`` reuses these
methods so there is a single source of truth for behaviour.
"""

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from .graph import DependencyGraph, Edge, Node
from .llm import LLMConfig, LocalLLM
from .memory import SessionMemory, get_memory
from .parser import CodeParser, create_capsule
from .resolver import FileEntry, ImportResolver

# Map file extensions to the parser language key.
# Directories never indexed; matched against exact path parts.
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

logger = logging.getLogger(__name__)

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
        license_manager: object | None = None,  # deprecated, ignored
    ):
        self.workspace = Path(workspace_path)
        self.db_path = self.workspace / ".codenexus" / "index.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.graph = DependencyGraph(self.db_path)
        self.parser = CodeParser()
        self.server = Server("codenexus", version="1.1.40")
        self.max_workers = max_workers

        # Fully open source: every feature is enabled unconditionally.
        # (license_manager parameter is accepted for backwards compatibility
        # and ignored.)
        del license_manager
        self.enabled_languages: set[str] | None = None  # all languages
        self.max_nodes_limit = None  # unlimited
        self.memory_enabled = True
        self.llm_enabled = bool(use_llm)

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

    def is_language_enabled(self, language: str) -> bool:
        """All languages are enabled — CodeNexus is fully open source."""
        return True

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
            # Raising lets the SDK transport surface a proper JSON-RPC error;
            # returning text here reported unknown tools as success.
            raise ValueError(f"Unknown tool: {name}")

    # ------------------------------------------------------------------ #
    # Query routing (single index vs federated workspace)
    # ------------------------------------------------------------------ #
    @property
    def _federated(self):
        """FederatedGraph when this workspace root has a workspace.json."""
        if not hasattr(self, "_federated_cache"):
            self._federated_cache = None
            try:
                if (self.workspace / ".codenexus" / "workspace.json").exists():
                    from .federation import FederatedGraph

                    self._federated_cache = FederatedGraph.from_workspace(self.workspace)
                    if self._federated_cache is not None:
                        logger.info(
                            "Multi-repo serving enabled (%d members)",
                            len(self._federated_cache.members),
                        )
            except Exception as e:  # never break single-index serving
                logger.warning("Federation unavailable: %s", e)
                self._federated_cache = None
        return self._federated_cache

    def _query_graph(self):
        """The graph MCP tools should read: federated when configured."""
        fed = self._federated
        return fed if fed is not None else self.graph

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
        graph = self._query_graph()

        for keyword in keywords:
            results = graph.search_nodes(keyword, limit=10)
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
        graph = self._query_graph()
        for keyword in keywords:
            for node in graph.search_nodes(keyword, limit=10):
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
        file_path = str(args.get("file_path", "")).strip()
        nodes = self._query_graph().get_file_nodes(file_path)

        if not nodes:
            return [TextContent(type="text", text=f"No nodes found for {file_path}")]

        skeletons = [f"{n.node_type} {n.name}: {n.signature}" for n in nodes]
        result = {"skeletons": skeletons}
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    async def _index_status(self) -> list[TextContent]:
        graph = self._query_graph()
        if hasattr(graph, "counts"):  # FederatedGraph
            counts = graph.counts()
        else:
            counts = {
                "nodes": self.graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0],
                "edges": self.graph.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
                "files": self.graph.conn.execute(
                    "SELECT COUNT(DISTINCT file_path) FROM nodes"
                ).fetchone()[0],
                "mode": "single",
            }
        result = {
            "nodes": counts["nodes"],
            "edges": counts["edges"],
            "files": counts["files"],
            "mode": counts.get("mode", "single"),
            "cached_files": len(self.file_cache),
            "status": "healthy",
        }
        if "repos" in counts:
            result["repos"] = counts["repos"]
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
        """Index all files in the workspace."""
        source_files = self._get_source_files()

        if not incremental:
            # Full re-index starts clean so rows from deleted or previously
            # mis-parsed files cannot linger.
            self.graph.clear()

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
                # Purge the deleted file's nodes/edges from the graph.
                abs_path = str((self.workspace / deleted).resolve())
                self.graph.delete_file_nodes(abs_path)

            if not files_to_index:
                print("No files changed since last index")
                return 0
        else:
            files_to_index = source_files


        print(f"Indexing {len(files_to_index)} files...")
        indexed = 0
        parse_results: list[tuple[Path, list[Node], list[Edge]]] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(self._parse_single_file, file_path): file_path
                for file_path in files_to_index
            }
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    nodes, edges = future.result()
                    parse_results.append((file_path, nodes, edges))
                    indexed += 1
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")

        node_cap = None  # unlimited (open source)
        total_nodes = self.graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        truncated = False  # kept for API compatibility; always False
        # Call targets may reference builtins/external symbols with no node;
        # only edges whose endpoints exist may be inserted (FK enforced).
        known_ids = {
            row[0] for row in self.graph.conn.execute("SELECT id FROM nodes")
        }
        # Pass 1 — nodes only. Edges are inserted in pass 2 AFTER every file's
        # symbols exist: filtering during streaming made acceptance depend on
        # ThreadPoolExecutor completion order (a call into a not-yet-inserted
        # file was dropped on some runs, kept on others).
        pending_edges = []
        for file_path, nodes, edges in parse_results:
            for node in nodes:
                if node_cap is not None and total_nodes >= node_cap:
                    truncated = True
                    break
                self.graph.add_node(node)
                known_ids.add(node.id)
                total_nodes += 1
            pending_edges.extend(edges)
            # Track indexed file in session memory.
            self._record_file_change(str(file_path), "index", len(nodes))

        # Pass 2 — edges whose endpoints exist anywhere in the graph.
        for edge in pending_edges:
            if edge.source_id.endswith("::import"):
                # Pseudo-source edges are rewritten into real module/symbol
                # edges by the resolver below.
                continue
            if edge.source_id in known_ids and edge.target_id in known_ids:
                self.graph.add_edge(edge)

        # Resolve imports into real edges between module/symbol nodes so
        # PageRank, impact analysis and dependents queries operate on a
        # connected graph (previously every import edge was dangling).
        if parse_results:
            entries = [
                FileEntry(
                    abs_path=fp,
                    rel_path=str(fp),
                    language=EXT_TO_LANGUAGE.get(fp.suffix, ""),
                    symbols={n.name: n.id for n in nds},
                    raw_imports=[e.target_id for e in es],
                )
                for fp, nds, es in parse_results
            ]
            module_nodes, import_edges = ImportResolver(self.workspace).build(entries)
            for mod_node in module_nodes:
                if node_cap is None or total_nodes < node_cap:
                    self.graph.add_node(mod_node)
                    known_ids.add(mod_node.id)
                    total_nodes += 1
            import_edges = [
                e for e in import_edges
                if e.source_id in known_ids and e.target_id in known_ids
            ]
            self.graph.add_edges(import_edges)

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
