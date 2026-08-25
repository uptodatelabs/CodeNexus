"""MCP stdio server for CodeNexus.

Implements the Model Context Protocol over newline-delimited JSON-RPC 2.0 on
stdin/stdout. Protocol rules enforced here:

- Requests (with an ``id``) always get exactly one response line.
- Notifications (no ``id``) NEVER get a response — replying to them corrupts
  strict clients, and writing ``null`` lines is equally fatal.
- Tool execution failures use the MCP ``result.isError`` convention instead
  of transport-level errors.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

from ._version import __version__
from .pipeline import build_query_capsule, build_task_capsule

logger = logging.getLogger(__name__)

# Protocol versions this server can speak. A client requesting one of these
# gets it echoed back; anything else falls back to the oldest supported.
SUPPORTED_PROTOCOL_VERSIONS = ["2024-11-05", "2025-03-26"]
DEFAULT_PROTOCOL_VERSION = "2024-11-05"

# Upper bound for a single stdin frame; guards against memory exhaustion
# from a hostile client piping unbounded lines.
_MAX_LINE_BYTES = 10 * 1024 * 1024


class MCPError(Exception):
    """JSON-RPC protocol error carrying its response code."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class CodeNexusMCPServer:
    """MCP Server implementing stdio JSON-RPC protocol."""

    SERVER_INFO = {"name": "codenexus", "version": __version__}

    TOOLS = [
        {
            "name": "run_pipeline",
            "description": "Primary tool: context search + impact analysis in one call",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description"},
                    "preset": {"type": "string", "enum": ["auto", "explore", "debug", "modify"]},
                    "max_tokens": {"type": "integer", "default": 8000},
                },
                "required": ["task"],
            },
        },
        {
            "name": "get_context_capsule",
            "description": "Lightweight context search for relevant code",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_tokens": {"type": "integer", "default": 8000},
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_skeleton",
            "description": "File structure without bodies",
            "inputSchema": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        },
        {
            "name": "index_status",
            "description": "Index health and statistics",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]

    def __init__(self, workspace: str):
        self.workspace = Path(workspace)
        self.db_path = self.workspace / ".codenexus" / "index.db"
        self._graph = None

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------
    def run(self):
        """Serve requests on stdin/stdout until EOF."""
        try:
            self._serve_loop()
        finally:
            self.close()

    def _serve_loop(self):
        while True:
            try:
                line = sys.stdin.readline()
            except OSError:
                break
            if not line:
                break
            if len(line) > _MAX_LINE_BYTES:
                self._write(self._error(None, -32600, "Request too large"))
                continue
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError as e:
                self._write(self._error(None, -32700, f"Parse error: {e}"))
                continue

            try:
                response = self._handle_request(request)
            except MCPError as e:
                req_id = request.get("id") if isinstance(request, dict) else None
                self._write(self._error(req_id, e.code, e.message))
                continue
            except Exception as e:
                logger.exception("Unhandled error serving request")
                req_id = request.get("id") if isinstance(request, dict) else None
                self._write(self._error(req_id, -32603, str(e)))
                continue

            # Notifications yield None and are never answered.
            if response is not None:
                self._write(response)

    @staticmethod
    def _write(payload: dict):
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    def _handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Handle one JSON-RPC message.

        Returns a response dict for requests, or None for notifications
        (which must never be answered).
        """
        if not isinstance(request, dict):
            raise MCPError(-32600, "Invalid request: expected an object")

        method = request.get("method")
        params = request.get("params") or {}
        has_id = "id" in request
        req_id = request.get("id")

        if method == "initialize":
            return self._handle_initialize(params, req_id)
        elif method in ("notifications/initialized", "initialized"):
            # Lifecycle notification: acknowledge by silence.
            return None
        elif method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": self.TOOLS}}
        elif method == "tools/call":
            return self._handle_tools_call(params, req_id)
        elif method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}
        else:
            if not has_id:
                # Unknown notification: ignore per JSON-RPC 2.0.
                logger.debug("Ignoring unknown notification %r", method)
                return None
            raise MCPError(-32601, f"Method not found: {method}")

    def _handle_initialize(self, params: dict, req_id: Any) -> dict:
        requested = ""
        if isinstance(params, dict):
            requested = str(params.get("protocolVersion", "") or "")
        negotiated = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else DEFAULT_PROTOCOL_VERSION
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": negotiated,
                "capabilities": {"tools": {}},
                "serverInfo": self.SERVER_INFO,
            },
        }

    def _handle_tools_call(self, params: dict, req_id: Any) -> dict:
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}

        handlers = {
            "run_pipeline": self._run_pipeline,
            "get_context_capsule": self._get_context_capsule,
            "get_skeleton": self._get_skeleton,
            "index_status": self._index_status,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            raise MCPError(-32601, f"Unknown tool: {tool_name}")

        try:
            result = handler(arguments)
        except MCPError as e:
            # Expected rejection (bad arguments etc.): report as tool failure.
            logger.warning("Tool %s rejected: %s", tool_name, e.message)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {e.message}"}],
                    "isError": True,
                },
            }
        except Exception as e:
            # Per MCP tools convention, tool failures are successful responses
            # flagged with isError so clients can render them as results.
            logger.exception("Tool %s failed", tool_name)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                    "isError": True,
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
        }

    # ------------------------------------------------------------------
    # Argument validation
    # ------------------------------------------------------------------
    @staticmethod
    def _require(args: dict, key: str) -> str:
        value = args.get(key)
        if not isinstance(value, str) or not value.strip():
            raise MCPError(-32602, f"Missing required argument '{key}'")
        return value.strip()

    @staticmethod
    def _positive_int(args: dict, key: str, default: int) -> int:
        raw = args.get(key, default)
        try:
            value = int(raw)
        except (TypeError, ValueError) as err:
            raise MCPError(-32602, f"Argument '{key}' must be an integer") from err
        if value <= 0:
            raise MCPError(-32602, f"Argument '{key}' must be positive")
        return value

    # ------------------------------------------------------------------
    # Graph lifecycle
    # ------------------------------------------------------------------
    def _get_graph(self):
        """Open (once) the workspace index graph."""
        if self._graph is None:
            from .graph import DependencyGraph

            self._graph = DependencyGraph(self.db_path)
        return self._graph

    def close(self):
        if self._graph is not None:
            self._graph.close()
            self._graph = None

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------
    def _run_pipeline(self, args: dict) -> dict:
        task = self._require(args, "task")
        max_tokens = self._positive_int(args, "max_tokens", 8000)
        preset = args.get("preset", "auto")
        return build_task_capsule(self._get_graph(), task, preset=preset, max_tokens=max_tokens)

    def _get_context_capsule(self, args: dict) -> dict:
        query = self._require(args, "query")
        max_tokens = self._positive_int(args, "max_tokens", 8000)
        return build_query_capsule(self._get_graph(), query, max_tokens=max_tokens)

    def _get_skeleton(self, args: dict) -> dict:
        file_path = self._require(args, "file_path")

        graph = self._get_graph()
        nodes = graph.get_file_nodes(file_path)
        if not nodes:
            return {"skeletons": [], "message": f"No nodes found for {file_path}"}

        return {"skeletons": [f"{n.node_type} {n.name}: {n.signature}" for n in nodes]}

    def _index_status(self, args: dict | None = None) -> dict:
        if not self.db_path.exists():
            return {"status": "no_index", "nodes": 0, "edges": 0, "files": 0}

        graph = self._get_graph()
        node_count = graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = graph.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        file_count = graph.conn.execute("SELECT COUNT(DISTINCT file_path) FROM nodes").fetchone()[0]

        return {"status": "healthy", "nodes": node_count, "edges": edge_count, "files": file_count}
