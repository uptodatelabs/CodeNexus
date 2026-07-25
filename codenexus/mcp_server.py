"""MCP Server implementation for CodeNexus.

Uses the official `mcp` Python SDK so it speaks the standard stdio MCP
transport (Content-Length framed JSON-RPC) that clients such as Hermes,
Claude Code, Cursor, and others expect.
"""

from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .graph import DependencyGraph, Node

SERVER_INFO = {"name": "codenexus", "version": "1.1.26"}


async def _run_pipeline(workspace: Path, args: dict) -> dict:
    """Run context pipeline."""

    task = args.get("task", "")
    max_tokens = int(args.get("max_tokens", 8000))

    db_path = workspace / ".codenexus" / "index.db"
    if not db_path.exists():
        return {"error": "No index found. Run 'codenexus index' first."}

    graph = DependencyGraph(db_path)
    keywords = task.lower().split()

    nodes = []
    seen_ids = set()
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

    result = {"task": task, "pivot_files": [], "skeletons": [], "token_estimate": 0}
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


async def _get_context_capsule(workspace: Path, args: dict) -> dict:
    """Get context capsule."""
    from .parser import create_capsule

    query = args.get("query", "")
    max_tokens = int(args.get("max_tokens", 8000))

    db_path = workspace / ".codenexus" / "index.db"
    if not db_path.exists():
        return {"error": "No index found"}

    graph = DependencyGraph(db_path)
    keywords = query.lower().split()
    nodes = []
    seen_ids = set()
    for keyword in keywords:
        results = graph.search_nodes(keyword, limit=10)
        for node in results:
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

    return {"capsule": "\n\n".join(capsule_parts), "token_estimate": int(tokens_used)}


async def _get_skeleton(workspace: Path, args: dict) -> dict:
    """Get file skeleton."""
    db_path = workspace / ".codenexus" / "index.db"
    file_path = args.get("file_path", "")

    if not db_path.exists():
        return {"error": "No index found"}

    graph = DependencyGraph(db_path)
    rows = graph.conn.execute(
        "SELECT id, file_path, name, node_type, start_line, end_line, "
        "content, signature, centrality_score FROM nodes WHERE file_path = ?",
        (file_path,),
    ).fetchall()

    if not rows:
        return {"error": f"No nodes found for {file_path}"}

    skeletons = []
    for row in rows:
        node = Node.from_row(row)
        skeletons.append(f"{node.node_type} {node.name}: {node.signature}")

    return {"skeletons": skeletons}


async def _index_status(workspace: Path) -> dict:
    """Get index status."""
    db_path = workspace / ".codenexus" / "index.db"

    if not db_path.exists():
        return {"status": "no_index", "nodes": 0, "edges": 0, "files": 0}

    graph = DependencyGraph(db_path)
    node_count = graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edge_count = graph.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    file_count = graph.conn.execute(
        "SELECT COUNT(DISTINCT file_path) FROM nodes"
    ).fetchone()[0]

    return {"status": "healthy", "nodes": node_count, "edges": edge_count, "files": file_count}


def create_server(workspace: str) -> Server:
    """Build an MCP Server instance for the given workspace."""
    ws = Path(workspace)
    server = Server("codenexus")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
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
                    "properties": {"file_path": {"type": "string"}},
                    "required": ["file_path"],
                },
            ),
            Tool(
                name="index_status",
                description="Index health and statistics",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            if name == "run_pipeline":
                result = await _run_pipeline(ws, arguments)
            elif name == "get_context_capsule":
                result = await _get_context_capsule(ws, arguments)
            elif name == "get_skeleton":
                result = await _get_skeleton(ws, arguments)
            elif name == "index_status":
                result = await _index_status(ws)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

            import json
            return [
                TextContent(type="text", text=json.dumps(result, indent=2, default=str))
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {e}")]

    return server


async def run_server(workspace: str) -> None:
    """Run the MCP server over stdio."""
    server = create_server(workspace)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
