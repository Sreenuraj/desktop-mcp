import json

from desktop_mcp.server.mcp_server import DesktopMCPServer
from desktop_mcp.server.stdio import handle_request


def test_initialize_response_advertises_tools_capability():
    response = handle_request(
        DesktopMCPServer(),
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )

    assert response["result"]["serverInfo"]["name"] == "desktop-mcp"
    assert "tools" in response["result"]["capabilities"]


def test_tools_list_returns_desktop_mcp_tools():
    response = handle_request(
        DesktopMCPServer(),
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )

    tool_names = {tool["name"] for tool in response["result"]["tools"]}
    assert "create_session" in tool_names
    assert "window_snapshot" in tool_names


def test_all_tools_have_defined_schemas():
    response = handle_request(
        DesktopMCPServer(),
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )

    for tool in response["result"]["tools"]:
        name = tool["name"]
        description = tool["description"]
        # Ensure the description is not the fallback
        assert description != f"Desktop MCP tool: {name}", f"Tool '{name}' is missing a detailed schema description"
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"


def test_tools_call_wraps_desktop_mcp_response_as_text_content():
    server = DesktopMCPServer()
    response = handle_request(
        server,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "create_session", "arguments": {}},
        },
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["success"] is True
    assert payload["data"]["session_id"] == "session_001"
