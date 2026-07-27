"""MCP Server implementation for CodeNexus.

Thin transport layer over the official `mcp` Python SDK. All domain logic
(indexing, pipeline, gating) lives in :mod:`codenexus.server` so this module
stays a single, well-defined adapter.
"""

from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .server import CodeNexusServer


def create_server(workspace: str) -> Server:
    """Build an MCP Server instance backed by CodeNexusServer.

    Reuses the engine's tool definitions and dispatch so there is no
    duplicate implementation of behaviour between the CLI and the MCP
    transport layer.
    """
    ws = Path(workspace)
    engine = CodeNexusServer(ws)

    server = Server("codenexus", version="1.1.28")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return engine.list_tool_definitions()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            return await engine.dispatch_tool(name, arguments)
        except Exception as e:  # pragma: no cover - defensive
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
