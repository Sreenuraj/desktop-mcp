"""MCP stdio wire-protocol tests.

Verifies that the JSON-RPC layer (desktop_mcp/server/stdio.py) correctly
advertises tools and wraps tool results as MCP text content.
"""

from __future__ import annotations

import json

from desktop_mcp.server.mcp_server import DesktopMCPServer
from desktop_mcp.server.stdio import handle_request
from desktop_mcp.server.tool_schemas import TOOL_SCHEMAS
from desktop_mcp.adapters.memory import InMemoryDesktopAdapter


def _server() -> DesktopMCPServer:
    return DesktopMCPServer(adapter=InMemoryDesktopAdapter())


def _call(server, method, params=None):
    return handle_request(server, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def test_initialize_advertises_tools_capability():
    resp = _call(_server(), "initialize")
    assert resp["result"]["capabilities"]["tools"] == {}


def test_tools_list_returns_all_registered_tools():
    resp = _call(_server(), "tools/list")
    names = {t["name"] for t in resp["result"]["tools"]}
    assert set(TOOL_SCHEMAS.keys()).issubset(names)


def test_every_tool_has_input_schema():
    resp = _call(_server(), "tools/list")
    for tool in resp["result"]["tools"]:
        assert "inputSchema" in tool, f"Tool {tool['name']} missing inputSchema"
        assert tool["inputSchema"]["type"] == "object"


def test_tool_call_result_is_text_content():
    """tools/call must wrap the result as MCP TextContent."""
    resp = _call(_server(), "tools/call", {"name": "create_session", "arguments": {}})
    content = resp["result"]["content"]
    assert len(content) > 0
    assert content[0]["type"] == "text"
    data = json.loads(content[0]["text"])
    assert "session_id" in data or "success" in data
