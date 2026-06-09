"""Core MCP server contract tests.

Updated for Phase 1 changes:
- All responses now include ``isError`` field.
- ``activate_window`` returns an observable-state dict (not ``{}``).
- Unknown tools return ``UNKNOWN_TOOL`` code (not ``INVALID_REQUEST``).
- ``window_snapshot`` returns ``controls_count``, ``capture_method``, ``uia_state``.
- ``control_tree`` returns ``tree_node_count`` and ``took_ms``.
- ``desktop_snapshot`` is a valid tool again (Phase 1.3).
"""

from desktop_mcp import DesktopMCPServer
from desktop_mcp.adapters.memory import InMemoryDesktopAdapter


def new_server() -> tuple[DesktopMCPServer, str]:
    server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
    response = server.call_tool("create_session", {})
    return server, response["data"]["session_id"]


# ------------------------------------------------------------------ #
# Response contract
# ------------------------------------------------------------------ #

def test_all_tool_calls_use_standard_response_contract():
    server = DesktopMCPServer()

    response = server.call_tool("create_session", {})

    # Phase 1.6: isError is now part of the contract
    assert set(response) == {"success", "data", "error", "isError"}
    assert response["success"] is True
    assert response["error"] is None
    assert response["isError"] is False
    assert response["data"]["session_id"] == "session_001"


def test_stateful_tools_require_a_session():
    server = DesktopMCPServer()

    response = server.call_tool("list_windows", {})

    assert response["success"] is False
    assert response["data"] is None
    assert response["error"]["code"] == "SESSION_NOT_FOUND"
    assert response["isError"] is True


# ------------------------------------------------------------------ #
# window_snapshot — Phase 1.2 enriched response
# ------------------------------------------------------------------ #

def test_window_snapshot_returns_controls():
    server, session_id = new_server()

    response = server.call_tool(
        "window_snapshot", {"session_id": session_id, "window_id": "win_demo"}
    )

    assert response["success"] is True
    assert response["data"]["window_id"] == "win_demo"
    assert response["data"]["title"] == "Customer Management"
    assert any(control["id"] == "btn_save" for control in response["data"]["controls"])


def test_window_snapshot_returns_controls_count():
    server, session_id = new_server()

    response = server.call_tool(
        "window_snapshot", {"session_id": session_id, "window_id": "win_demo"}
    )

    assert response["success"] is True
    assert "controls_count" in response["data"]
    assert response["data"]["controls_count"] == len(response["data"]["controls"])


def test_window_snapshot_returns_capture_method():
    server, session_id = new_server()

    response = server.call_tool(
        "window_snapshot", {"session_id": session_id, "window_id": "win_demo"}
    )

    assert "capture_method" in response["data"]


def test_window_snapshot_returns_uia_state():
    server, session_id = new_server()

    response = server.call_tool(
        "window_snapshot", {"session_id": session_id, "window_id": "win_demo"}
    )

    assert "uia_state" in response["data"]
    assert response["data"]["uia_state"] == "live"


# ------------------------------------------------------------------ #
# control_tree — Phase 1.2 enriched response
# ------------------------------------------------------------------ #

def test_control_tree_returns_tree_node_count():
    server, session_id = new_server()

    response = server.call_tool(
        "control_tree", {"session_id": session_id, "window_id": "win_demo"}
    )

    assert response["success"] is True
    assert "tree_node_count" in response["data"]
    assert isinstance(response["data"]["tree_node_count"], int)
    assert response["data"]["tree_node_count"] >= 0


def test_control_tree_returns_took_ms():
    server, session_id = new_server()

    response = server.call_tool(
        "control_tree", {"session_id": session_id, "window_id": "win_demo"}
    )

    assert "took_ms" in response["data"]
    assert isinstance(response["data"]["took_ms"], int)


# ------------------------------------------------------------------ #
# activate_window — Phase 1.2 observable state
# ------------------------------------------------------------------ #

def test_activate_window_returns_observable_state():
    server, session_id = new_server()

    response = server.call_tool(
        "activate_window", {"session_id": session_id, "window_id": "win_demo"}
    )

    assert response["success"] is True
    data = response["data"]
    assert "window_id" in data
    assert "is_foreground" in data
    assert "became_foreground" in data
    assert "attempts" in data
    assert "total_ms" in data


def test_activate_window_returns_window_id():
    server, session_id = new_server()

    response = server.call_tool(
        "activate_window", {"session_id": session_id, "window_id": "win_demo"}
    )

    assert response["data"]["window_id"] == "win_demo"


# ------------------------------------------------------------------ #
# desktop_snapshot — Phase 1.3 restored
# ------------------------------------------------------------------ #

def test_desktop_snapshot_is_valid_tool():
    server, session_id = new_server()

    response = server.call_tool("desktop_snapshot", {"session_id": session_id})

    assert response["success"] is True
    assert response["isError"] is False
    assert "windows" in response["data"]
    assert "windows_count" in response["data"]


def test_desktop_snapshot_includes_controls_per_window():
    server, session_id = new_server()

    response = server.call_tool("desktop_snapshot", {"session_id": session_id})

    windows = response["data"]["windows"]
    assert len(windows) > 0
    for win in windows:
        assert "controls" in win
        assert "controls_count" in win


# ------------------------------------------------------------------ #
# Unknown tool — Phase 1.3 UNKNOWN_TOOL guard
# ------------------------------------------------------------------ #

def test_unknown_tool_returns_unknown_tool_code():
    """Phase 1.3: unknown tools now return UNKNOWN_TOOL, not INVALID_REQUEST."""
    server, session_id = new_server()

    response = server.call_tool("not_a_tool", {"session_id": session_id})

    assert response["success"] is False
    assert response["isError"] is True
    assert response["error"]["code"] == "UNKNOWN_TOOL"


def test_assert_text_failure_returns_unknown_tool():
    """assert_text was never a real tool — now returns UNKNOWN_TOOL."""
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
    assert response["error"]["code"] == "UNKNOWN_TOOL"


# ------------------------------------------------------------------ #
# click_at
# ------------------------------------------------------------------ #

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


# ------------------------------------------------------------------ #
# wait_for_window — Phase 1.4 polling
# ------------------------------------------------------------------ #

def test_wait_for_window_finds_existing_window():
    server, session_id = new_server()

    response = server.call_tool(
        "wait_for_window",
        {"session_id": session_id, "title_contains": "Customer"},
    )

    assert response["success"] is True
    assert response["data"]["window_id"] == "win_demo"


def test_wait_for_window_timeout_returns_error():
    server, session_id = new_server()

    response = server.call_tool(
        "wait_for_window",
        {"session_id": session_id, "title_contains": "NonExistentXYZ", "timeout_ms": 100},
    )

    assert response["success"] is False
    assert response["isError"] is True
    assert response["error"]["code"] == "WINDOW_NOT_FOUND"
