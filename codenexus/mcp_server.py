"""MCP Server implementation for CodeNexus."""

import json
import sys
from pathlib import Path
from typing import Any

from .graph import Node


class MCPError(Exception):
    """MCP protocol error."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message


class CodeNexusMCPServer:
    """MCP Server implementing stdio JSON-RPC protocol."""

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_INFO = {"name": "codenexus", "version": "1.1.20"}

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

    def run(self):
        """Run the MCP server via stdio."""
        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                    response = self._handle_request(request)
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
                except json.JSONDecodeError as e:
                    self._send_error(None, -32700, f"Parse error: {e}")
                except Exception as e:
                    self._send_error(None, -32603, str(e))
        except EOFError:
            pass

    def _handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a JSON-RPC request."""
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")

        if method == "initialize":
            return self._handle_initialize(params, req_id)
        elif method == "initialized":
            return self._handle_initialized()
        elif method == "tools/list":
            return self._handle_tools_list(req_id)
        elif method == "tools/call":
            return self._handle_tools_call(params, req_id)
        elif method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}
        else:
            self._send_error(req_id, -32601, f"Method not found: {method}")
            return None

    def _handle_initialize(self, params: dict, req_id: Any) -> dict:
        """Handle initialize request."""
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": self.SERVER_INFO,
            },
        }

    def _handle_initialized(self) -> None:
        """Handle initialized notification."""
        return None

    def _handle_tools_list(self, req_id: Any) -> dict:
        """Handle tools/list request."""
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": self.TOOLS}}

    def _handle_tools_call(self, params: dict, req_id: Any) -> dict:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            if tool_name == "run_pipeline":
                result = self._run_pipeline(arguments)
            elif tool_name == "get_context_capsule":
                result = self._get_context_capsule(arguments)
            elif tool_name == "get_skeleton":
                result = self._get_skeleton(arguments)
            elif tool_name == "index_status":
                result = self._index_status()
            else:
                self._send_error(req_id, -32601, f"Unknown tool: {tool_name}")
                return None

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
            }
        except Exception as e:
            self._send_error(req_id, -32603, str(e))
            return None

    def _send_error(self, req_id: Any, code: int, message: str):
        """Send JSON-RPC error."""
        error = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
        sys.stdout.write(json.dumps(error) + "\n")
        sys.stdout.flush()

    def _run_pipeline(self, args: dict) -> dict:
        """Run context pipeline."""
        from .graph import DependencyGraph

        task = args.get("task", "")
        max_tokens = args.get("max_tokens", 8000)

        if not self.db_path.exists():
            return {"error": "No index found. Run 'codenexus index' first."}

        graph = DependencyGraph(self.db_path)
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

    def _get_context_capsule(self, args: dict) -> dict:
        """Get context capsule."""
        from .graph import DependencyGraph
        from .parser import create_capsule

        query = args.get("query", "")
        max_tokens = args.get("max_tokens", 8000)

        if not self.db_path.exists():
            return {"error": "No index found"}

        graph = DependencyGraph(self.db_path)
        nodes = graph.search_nodes(query, limit=10)

        capsule_parts = []
        tokens_used = 0

        for node in nodes:
            if tokens_used >= max_tokens:
                break
            skeleton = create_capsule(node.content)
            capsule_parts.append(f"=== {node.file_path}::{node.name} ===\n{skeleton}")
            tokens_used += len(skeleton.split()) * 1.3

        return {"capsule": "\n\n".join(capsule_parts), "token_estimate": int(tokens_used)}

    def _get_skeleton(self, args: dict) -> dict:
        """Get file skeleton."""
        from .graph import DependencyGraph

        file_path = args.get("file_path", "")

        if not self.db_path.exists():
            return {"error": "No index found"}

        graph = DependencyGraph(self.db_path)
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

    def _index_status(self) -> dict:
        """Get index status."""
        from .graph import DependencyGraph

        if not self.db_path.exists():
            return {"status": "no_index", "nodes": 0, "edges": 0, "files": 0}

        graph = DependencyGraph(self.db_path)
        node_count = graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = graph.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        file_count = graph.conn.execute("SELECT COUNT(DISTINCT file_path) FROM nodes").fetchone()[0]

        return {"status": "healthy", "nodes": node_count, "edges": edge_count, "files": file_count}

