"""MCP Server for CodeNexus context engine."""

import json
import asyncio
import hashlib
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from mcp.server import Server
from mcp.types import Tool, TextContent

from .graph import DependencyGraph, Node, Edge
from .parser import CodeParser, create_capsule

class CodeNexusServer:
    """MCP server providing context tools for AI agents."""
    
    def __init__(self, workspace_path: Path, max_workers: int = 4):
        self.workspace = workspace_path
        self.db_path = workspace_path / ".codenexus" / "index.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.graph = DependencyGraph(self.db_path)
        self.parser = CodeParser()
        self.server = Server("codenexus")
        self.max_workers = max_workers
        
        # File hash cache for incremental indexing
        self.cache_path = self.db_path.parent / "cache.json"
        self.file_cache = self._load_cache()
        
        self._setup_tools()
    
    def _load_cache(self) -> dict:
        """Load file hash cache from disk."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def _save_cache(self):
        """Save file hash cache to disk."""
        try:
            with open(self.cache_path, "w") as f:
                json.dump(self.file_cache, f, indent=2)
        except Exception:
            pass
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of file content."""
        try:
            content = file_path.read_bytes()
            return hashlib.md5(content).hexdigest()
        except Exception:
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
                            "preset": {"type": "string", "enum": ["auto", "explore", "debug", "modify"]},
                            "max_tokens": {"type": "integer", "default": 8000},
                        },
                        "required": ["task"]
                    }
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
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="get_skeleton",
                    description="File structure without bodies",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "detail": {"type": "string", "enum": ["minimal", "standard", "detailed"]},
                        },
                        "required": ["file_path"]
                    }
                ),
                Tool(
                    name="index_status",
                    description="Index health and statistics",
                    inputSchema={"type": "object", "properties": {}}
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
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    async def _run_pipeline(self, args: dict) -> list[TextContent]:
        """Run context search pipeline."""
        task = args.get("task", "")
        max_tokens = args.get("max_tokens", 8000)
        
        # Extract keywords from task
        keywords = task.lower().split()
        
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
        nodes = nodes[:20]  # Limit to top 20
        
        # Build capsule
        result = {
            "task": task,
            "pivot_files": [],
            "skeletons": [],
            "token_estimate": 0
        }
        
        tokens_used = 0
        for node in nodes:
            if tokens_used >= max_tokens:
                break
            
            # Get full content for top nodes, skeleton for rest
            full_content = node.content
            skeleton = node.signature + "\n..."
            
            if tokens_used + len(full_content.split()) * 1.3 < max_tokens * 0.6:
                result["pivot_files"].append({
                    "path": node.file_path,
                    "name": node.name,
                    "content": full_content
                })
                tokens_used += len(full_content.split()) * 1.3
            else:
                result["skeletons"].append({
                    "path": node.file_path,
                    "name": node.name,
                    "skeleton": skeleton
                })
                tokens_used += len(skeleton.split()) * 1.3
        
        result["token_estimate"] = int(tokens_used)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    async def _get_context_capsule(self, args: dict) -> list[TextContent]:
        """Get context capsule for a query."""
        query = args.get("query", "")
        max_tokens = args.get("max_tokens", 8000)
        
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
        
        return [TextContent(
            type="text",
            text="\n\n".join(capsule_parts)
        )]
    
    async def _get_skeleton(self, args: dict) -> list[TextContent]:
        """Get file skeleton."""
        file_path = args.get("file_path", "")
        detail = args.get("detail", "standard")
        
        # Find nodes in file
        rows = self.graph.conn.execute(
            "SELECT * FROM nodes WHERE file_path = ?", (file_path,)
        ).fetchall()
        
        if not rows:
            return [TextContent(type="text", text=f"No nodes found for {file_path}")]
        
        skeletons = []
        for row in rows:
            node = Node(*row[:9])
            skeletons.append(f"{node.node_type} {node.name}: {node.signature}")
        
        return [TextContent(
            type="text",
            text=f"=== Skeleton: {file_path} ===\n" + "\n".join(skeletons)
        )]
    
    async def _index_status(self) -> list[TextContent]:
        """Get index status."""
        node_count = self.graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = self.graph.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        file_count = self.graph.conn.execute(
            "SELECT COUNT(DISTINCT file_path) FROM nodes"
        ).fetchone()[0]
        
        return [TextContent(
            type="text",
            text=json.dumps({
                "nodes": node_count,
                "edges": edge_count,
                "files": file_count,
                "cached_files": len(self.file_cache),
                "status": "healthy"
            }, indent=2)
        )]
    
    def _get_source_files(self) -> list[Path]:
        """Get all source files in workspace."""
        extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java"}
        skip_dirs = {"node_modules", ".git", "__pycache__", "venv", ".venv", 
                     "dist", "build", ".codenexus"}
        
        source_files = []
        for ext in extensions:
            for file_path in self.workspace.rglob(f"*{ext}"):
                if not any(skip in file_path.parts for skip in skip_dirs):
                    source_files.append(file_path)
        
        return source_files
    
    def _parse_single_file(self, file_path: Path) -> tuple[list[Node], list[Edge]]:
        """Parse a single file (for parallel execution)."""
        try:
            return self.parser.parse_file(file_path)
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return [], []
    
    def index_workspace(self, incremental: bool = True):
        """
        Index all files in workspace.
        
        Args:
            incremental: If True, only index changed files
        """
        source_files = self._get_source_files()
        
        if incremental:
            # Filter to only changed files
            files_to_index = []
            for file_path in source_files:
                file_hash = self._get_file_hash(file_path)
                file_key = str(file_path.relative_to(self.workspace))
                
                if self.file_cache.get(file_key) != file_hash:
                    files_to_index.append(file_path)
                    self.file_cache[file_key] = file_hash
            
            # Remove deleted files from cache
            existing_files = {str(f.relative_to(self.workspace)) for f in source_files}
            deleted_files = [k for k in self.file_cache.keys() if k not in existing_files]
            for deleted in deleted_files:
                del self.file_cache[deleted]
            
            if not files_to_index:
                print("No files changed since last index")
                return 0
        else:
            files_to_index = source_files
        
        print(f"Indexing {len(files_to_index)} files...")
        
        # Parallel parsing
        indexed = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(self._parse_single_file, file_path): file_path
                for file_path in files_to_index
            }
            
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    nodes, edges = future.result()
                    for node in nodes:
                        self.graph.add_node(node)
                    for edge in edges:
                        self.graph.add_edge(edge)
                    indexed += 1
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")
        
        # Save cache
        self._save_cache()
        
        # Compute PageRank after indexing
        if indexed > 0:
            print("Computing centrality scores...")
            self.graph.compute_pagerank()
        
        return indexed
    
    def clear_index(self):
        """Clear all index data."""
        self.graph.clear()
        self.file_cache = {}
        self._save_cache()
