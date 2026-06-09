from desktop_mcp import DesktopMCPServer
from desktop_mcp.adapters.memory import InMemoryDesktopAdapter


def new_server() -> tuple[DesktopMCPServer, str]:
    server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
    response = server.call_tool("create_session", {})
    return server, response["data"]["session_id"]


def test_all_tool_calls_use_standard_response_contract():
    server = DesktopMCPServer()

    response = server.call_tool("create_session", {})

    assert set(response) == {"success", "data", "error"}
    assert response["success"] is True
    assert response["error"] is None
    assert response["data"]["session_id"] == "session_001"


def test_stateful_tools_require_a_session():
    server = DesktopMCPServer()

    response = server.call_tool("list_windows", {})

    assert response["success"] is False
    assert response["data"] is None
    assert response["error"]["code"] == "SESSION_NOT_FOUND"


def test_window_snapshot_returns_controls():
    server, session_id = new_server()

    response = server.call_tool(
        "window_snapshot", {"session_id": session_id, "window_id": "win_demo"}
    )

    assert response["success"] is True
    assert response["data"]["window_id"] == "win_demo"
    assert response["data"]["title"] == "Customer Management"
    assert any(control["id"] == "btn_save" for control in response["data"]["controls"])


def test_assert_text_failure_returns_invalid_request():
    server, session_id = new_server()

    response = server.call_tool(
        "assert_text",
        {
            "session_id": session_id,
            "control_id": "txt_customer",
            "expected": "Approved",
        },
    )

    assert response["success"] is False
    assert response["error"]["code"] == "INVALID_REQUEST"


def test_unknown_tool_returns_invalid_request():
    server, session_id = new_server()

    response = server.call_tool("not_a_tool", {"session_id": session_id})

    assert response["success"] is False
    assert response["error"]["code"] == "INVALID_REQUEST"


def test_click_at():
    server, session_id = new_server()

    response = server.call_tool(
        "click_at",
        {"session_id": session_id, "x": 100, "y": 200, "button": "right"},
    )

    assert response["success"] is True
    assert response["data"]["x"] == 100
    assert response["data"]["y"] == 200
    assert response["data"]["button"] == "right"



