from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from desktop_mcp.server.mcp_server import DesktopMCPServer
from desktop_mcp.server.tool_schemas import TOOL_SCHEMAS


def handle_request(
    server: DesktopMCPServer, request: dict[str, Any]
) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    if method == "notifications/initialized":
        return None

    try:
        result: dict[str, Any]
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "desktop-mcp", "version": "0.2.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            tools_list = []
            for name in server.tools:
                schema = TOOL_SCHEMAS.get(name, {})
                tools_list.append({
                    "name": name,
                    "description": schema.get(
                        "description", f"Desktop MCP tool: {name}"
                    ),
                    "inputSchema": schema.get(
                        "inputSchema",
                        {"type": "object", "additionalProperties": True},
                    ),
                })
            result = {"tools": tools_list}
        elif method == "tools/call":
            tool_name = params.get("name")
            if not isinstance(tool_name, str):
                return _error(
                    request_id, -32602, "Invalid params: name must be a string"
                )
            arguments = params.get("arguments") or {}
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(server.call_tool(tool_name, arguments)),
                    }
                ]
            }
        else:
            return _error(request_id, -32601, f"Unsupported method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return _error(request_id, -32603, str(exc))


def run_stdio(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
    server = DesktopMCPServer()
    for line in stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = handle_request(server, request)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, f"Invalid JSON: {exc}")
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


def main() -> None:
    run_stdio()


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


if __name__ == "__main__":
    main()
