"""MCP tool contract tests.

Covers the scenarios that matter for an LLM agent driving desktop apps:
- Session lifecycle (create / close)
- Tool call response shape (success, error, isError)
- Unknown tool returns structured UNKNOWN_TOOL error
- window_snapshot returns controls + metadata
- activate_window returns observable foreground state
- wait_for_window polls and times out correctly
- desktop_snapshot is a valid tool (restored in Phase 1.3)
- click / enter_text return interaction metadata
- Errors carry isError: true and a structured error envelope
- Evidence: capture_window, generate_report
- Adapter selection: UIA on Windows, InMemory elsewhere
- Phase 4: wait_for_control, wait_for_idle, select_row, click_cell,
  read_cell, read_tree, list_dialogs, get_foreground_window,
  get_focused_control, health_check
"""

from __future__ import annotations

import os
import sys
from unittest import mock

import pytest

from desktop_mcp import DesktopMCPServer
from desktop_mcp.adapters.memory import InMemoryDesktopAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _server() -> tuple[DesktopMCPServer, str]:
    server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
    sid = server.call_tool("create_session", {})["data"]["session_id"]
    return server, sid


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

def test_create_session_returns_session_id():
    server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
    resp = server.call_tool("create_session", {})
    assert resp["success"] is True
    assert resp["isError"] is False
    assert "session_id" in resp["data"]


def test_stateful_tools_require_valid_session():
    server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
    resp = server.call_tool("list_windows", {"session_id": "bad_session"})
    assert resp["success"] is False
    assert resp["isError"] is True
    assert resp["error"]["code"] == "SESSION_NOT_FOUND"


def test_all_responses_have_standard_envelope():
    """Every tool call must return success, data, error, isError."""
    server, sid = _server()
    resp = server.call_tool("list_windows", {"session_id": sid})
    assert set(resp.keys()) == {"success", "data", "error", "isError"}


# ---------------------------------------------------------------------------
# Unknown tool guard (Phase 1.3)
# ---------------------------------------------------------------------------

def test_unknown_tool_returns_structured_error():
    server, sid = _server()
    resp = server.call_tool("desktop_snapshot_old", {"session_id": sid})
    assert resp["success"] is False
    assert resp["isError"] is True
    assert resp["error"]["code"] == "UNKNOWN_TOOL"
    assert "valid_tools" in resp["error"]["details"]


def test_desktop_snapshot_is_now_a_valid_tool():
    """desktop_snapshot was removed then restored — must not return UNKNOWN_TOOL."""
    server, sid = _server()
    resp = server.call_tool("desktop_snapshot", {"session_id": sid})
    assert resp["success"] is True
    assert resp["error"] is None


# ---------------------------------------------------------------------------
# window_snapshot — enriched response (Phase 1.2)
# ---------------------------------------------------------------------------

def test_window_snapshot_returns_controls_and_metadata():
    server, sid = _server()
    resp = server.call_tool("window_snapshot", {"session_id": sid, "window_id": "win_demo"})
    data = resp["data"]
    assert resp["success"] is True
    assert len(data["controls"]) > 0
    assert data["controls_count"] == len(data["controls"])
    assert "capture_method" in data
    assert data["uia_state"] == "live"


def test_window_snapshot_missing_window_returns_error():
    server, sid = _server()
    resp = server.call_tool("window_snapshot", {"session_id": sid, "window_id": "win_nonexistent"})
    assert resp["success"] is False
    assert resp["isError"] is True


# ---------------------------------------------------------------------------
# activate_window — observable state (Phase 1.2)
# ---------------------------------------------------------------------------

def test_activate_window_returns_observable_state():
    server, sid = _server()
    resp = server.call_tool("activate_window", {"session_id": sid, "window_id": "win_demo"})
    data = resp["data"]
    assert resp["success"] is True
    assert data["window_id"] == "win_demo"
    assert "is_foreground" in data
    assert "became_foreground" in data
    assert isinstance(data["attempts"], int)
    assert isinstance(data["total_ms"], int)


# ---------------------------------------------------------------------------
# wait_for_window — polling (Phase 1.4)
# ---------------------------------------------------------------------------

def test_wait_for_window_returns_matching_window():
    server, sid = _server()
    resp = server.call_tool(
        "wait_for_window", {"session_id": sid, "title_contains": "Customer"}
    )
    assert resp["success"] is True
    assert resp["data"]["window_id"] == "win_demo"


def test_wait_for_window_timeout_returns_window_not_found():
    server, sid = _server()
    resp = server.call_tool(
        "wait_for_window",
        {"session_id": sid, "title_contains": "DoesNotExistXYZ", "timeout_ms": 50},
    )
    assert resp["success"] is False
    assert resp["isError"] is True
    assert resp["error"]["code"] == "WINDOW_NOT_FOUND"


# ---------------------------------------------------------------------------
# Interactions — enriched result (Phase 1.2 / 2.1)
# ---------------------------------------------------------------------------

def test_click_returns_action_metadata():
    server, sid = _server()
    resp = server.call_tool("click", {"session_id": sid, "control_id": "btn_save"})
    assert resp["success"] is True
    data = resp["data"]
    assert data["action"] in ("left", "click")
    assert "control_id" in data


def test_enter_text_updates_control_value():
    server, sid = _server()
    server.call_tool(
        "enter_text", {"session_id": sid, "control_id": "txt_customer", "value": "ACME"}
    )
    snap = server.call_tool("window_snapshot", {"session_id": sid, "window_id": "win_demo"})
    customer_ctrl = next(
        (c for c in snap["data"]["controls"] if c["id"] == "txt_customer"), None
    )
    assert customer_ctrl is not None
    assert customer_ctrl["value"] == "ACME"


def test_click_disabled_control_returns_error():
    server, sid = _server()
    server.adapter._controls["btn_save"].enabled = False
    resp = server.call_tool("click", {"session_id": sid, "control_id": "btn_save"})
    assert resp["success"] is False
    assert resp["isError"] is True
    assert resp["error"]["code"] == "CONTROL_DISABLED"


def test_click_nonexistent_control_returns_error():
    server, sid = _server()
    resp = server.call_tool("click", {"session_id": sid, "control_id": "ctrl_ghost"})
    assert resp["success"] is False
    assert resp["isError"] is True
    assert resp["error"]["code"] == "CONTROL_NOT_FOUND"


# ---------------------------------------------------------------------------
# control_tree — enriched response (Phase 1.2)
# ---------------------------------------------------------------------------

def test_control_tree_returns_tree_with_counts():
    server, sid = _server()
    resp = server.call_tool("control_tree", {"session_id": sid, "window_id": "win_demo"})
    data = resp["data"]
    assert resp["success"] is True
    assert isinstance(data["tree"], list)
    assert isinstance(data["tree_node_count"], int)
    assert data["tree_node_count"] >= len(data["tree"])
    assert isinstance(data["took_ms"], int)


# ---------------------------------------------------------------------------
# desktop_snapshot — all windows (Phase 1.3)
# ---------------------------------------------------------------------------

def test_desktop_snapshot_returns_all_windows_with_controls():
    server, sid = _server()
    resp = server.call_tool("desktop_snapshot", {"session_id": sid})
    data = resp["data"]
    assert resp["success"] is True
    assert data["windows_count"] > 0
    for win in data["windows"]:
        assert "controls" in win
        assert "controls_count" in win


# ---------------------------------------------------------------------------
# Evidence collection
# ---------------------------------------------------------------------------

def test_capture_window_saves_artifact(tmp_path):
    server, sid = _server()
    with mock.patch.dict(os.environ, {"DESKTOP_MCP_EVIDENCE_DIR": str(tmp_path)}):
        resp = server.call_tool("capture_window", {"session_id": sid, "window_id": "win_demo"})
    assert resp["success"] is True
    assert "artifact" in resp["data"]


def test_generate_report_creates_markdown(tmp_path):
    server, sid = _server()
    server.call_tool("window_snapshot", {"session_id": sid, "window_id": "win_demo"})
    with mock.patch.dict(os.environ, {"DESKTOP_MCP_EVIDENCE_DIR": str(tmp_path)}):
        resp = server.call_tool("generate_report", {"session_id": sid})
    assert resp["success"] is True
    report_path = resp["data"]["artifact"]
    assert os.path.exists(report_path)
    content = open(report_path).read()
    assert "window_snapshot" in content


# ---------------------------------------------------------------------------
# Adapter selection
# ---------------------------------------------------------------------------

def test_default_adapter_is_memory_on_non_windows():
    if sys.platform == "win32":
        pytest.skip("Only relevant on non-Windows")
    server = DesktopMCPServer()
    assert isinstance(server.adapter, InMemoryDesktopAdapter)


def test_explicit_memory_adapter_env(monkeypatch):
    monkeypatch.setenv("DESKTOP_MCP_ADAPTER", "memory")
    server = DesktopMCPServer()
    assert isinstance(server.adapter, InMemoryDesktopAdapter)


# ===========================================================================
# Phase 4.1 — Waiters
# ===========================================================================

def test_wait_for_control_finds_existing_control():
    """wait_for_control returns the control immediately when it already exists."""
    server, sid = _server()
    resp = server.call_tool(
        "wait_for_control",
        {"session_id": sid, "window_id": "win_demo", "name": "Save"},
    )
    assert resp["success"] is True
    assert resp["data"]["id"] == "btn_save"


def test_wait_for_control_by_automation_id():
    server, sid = _server()
    resp = server.call_tool(
        "wait_for_control",
        {"session_id": sid, "window_id": "win_demo", "automation_id": "txtCustomer"},
    )
    assert resp["success"] is True
    assert resp["data"]["id"] == "txt_customer"


def test_wait_for_control_by_type():
    server, sid = _server()
    resp = server.call_tool(
        "wait_for_control",
        {"session_id": sid, "window_id": "win_demo", "control_type": "Button"},
    )
    assert resp["success"] is True
    assert resp["data"]["type"] == "Button"


def test_wait_for_control_not_found_returns_error():
    server, sid = _server()
    resp = server.call_tool(
        "wait_for_control",
        {"session_id": sid, "window_id": "win_demo", "name": "NonExistentXYZ", "timeout_ms": 50},
    )
    assert resp["success"] is False
    assert resp["isError"] is True
    assert resp["error"]["code"] == "CONTROL_NOT_FOUND"


def test_wait_for_control_requires_at_least_one_criterion():
    server, sid = _server()
    resp = server.call_tool(
        "wait_for_control",
        {"session_id": sid, "window_id": "win_demo"},
    )
    assert resp["success"] is False
    assert resp["isError"] is True
    assert resp["error"]["code"] == "INVALID_REQUEST"


def test_wait_for_idle_returns_idle_true():
    """In-memory adapter is always immediately idle."""
    server, sid = _server()
    resp = server.call_tool(
        "wait_for_idle",
        {"session_id": sid, "window_id": "win_demo"},
    )
    assert resp["success"] is True
    assert resp["data"]["idle"] is True
    assert isinstance(resp["data"]["settled_ms"], int)


# ===========================================================================
# Phase 4.2 — Richer control kinds
# ===========================================================================

def test_select_row_by_index():
    server, sid = _server()
    resp = server.call_tool(
        "select_row",
        {"session_id": sid, "control_id": "grid_customers", "by_index": 0},
    )
    assert resp["success"] is True
    assert resp["data"]["row_index"] == 0


def test_select_row_by_text():
    server, sid = _server()
    resp = server.call_tool(
        "select_row",
        {"session_id": sid, "control_id": "grid_customers", "by_text": "Jane"},
    )
    assert resp["success"] is True
    assert resp["data"]["row_index"] == 0


def test_select_row_out_of_range_returns_error():
    server, sid = _server()
    resp = server.call_tool(
        "select_row",
        {"session_id": sid, "control_id": "grid_customers", "by_index": 99},
    )
    assert resp["success"] is False
    assert resp["isError"] is True
    assert resp["error"]["code"] == "CONTROL_NOT_FOUND"


def test_click_cell_returns_cell_info():
    server, sid = _server()
    resp = server.call_tool(
        "click_cell",
        {"session_id": sid, "control_id": "grid_customers", "row": 0, "column": 0},
    )
    assert resp["success"] is True
    assert resp["data"]["row"] == 0
    assert resp["data"]["column"] == 0
    assert "cell_control_id" in resp["data"]


def test_read_cell_returns_value():
    server, sid = _server()
    resp = server.call_tool(
        "read_cell",
        {"session_id": sid, "control_id": "grid_customers", "row": 0, "column": 0},
    )
    assert resp["success"] is True
    assert resp["data"]["value"] == "Jane Doe"


def test_read_cell_second_column():
    server, sid = _server()
    resp = server.call_tool(
        "read_cell",
        {"session_id": sid, "control_id": "grid_customers", "row": 1, "column": 1},
    )
    assert resp["success"] is True
    assert resp["data"]["value"] == "Approved"


def test_read_tree_returns_nodes_structure():
    server, sid = _server()
    resp = server.call_tool(
        "read_tree",
        {"session_id": sid, "control_id": "grid_customers"},
    )
    assert resp["success"] is True
    assert "nodes" in resp["data"]
    assert "node_count" in resp["data"]
    assert isinstance(resp["data"]["nodes"], list)


# ===========================================================================
# Phase 4.3 — Dialog awareness
# ===========================================================================

def test_list_dialogs_returns_empty_when_no_dialogs():
    server, sid = _server()
    resp = server.call_tool(
        "list_dialogs",
        {"session_id": sid, "application_id": "app_demo"},
    )
    assert resp["success"] is True
    assert resp["data"]["count"] == 0
    assert resp["data"]["dialogs"] == []


def test_list_dialogs_finds_error_window():
    """A window with 'error' in the title should be detected as a dialog."""
    server, sid = _server()
    from desktop_mcp.models.window import Window
    error_win = Window(
        window_id="win_err",
        application_id="app_demo",
        title="Error: Login Failed",
        active=False,
    )
    server.adapter._windows["win_err"] = error_win

    resp = server.call_tool(
        "list_dialogs",
        {"session_id": sid, "application_id": "app_demo"},
    )
    assert resp["success"] is True
    assert resp["data"]["count"] == 1
    assert resp["data"]["dialogs"][0]["window_id"] == "win_err"


# ===========================================================================
# Phase 4.4 — Grounding tools
# ===========================================================================

def test_get_foreground_window_returns_active_window():
    server, sid = _server()
    resp = server.call_tool("get_foreground_window", {"session_id": sid})
    assert resp["success"] is True
    data = resp["data"]
    assert "window_id" in data
    assert "title" in data
    assert "hwnd" in data
    # In-memory adapter: win_demo is active
    assert data["window_id"] == "win_demo"


def test_get_focused_control_returns_none_when_nothing_focused():
    server, sid = _server()
    resp = server.call_tool(
        "get_focused_control",
        {"session_id": sid, "window_id": "win_demo"},
    )
    assert resp["success"] is True
    data = resp["data"]
    assert data["window_id"] == "win_demo"
    assert data["control_id"] is None


def test_get_focused_control_returns_focused_control():
    server, sid = _server()
    # Focus a control
    server.adapter._controls["txt_customer"].focused = True
    resp = server.call_tool(
        "get_focused_control",
        {"session_id": sid, "window_id": "win_demo"},
    )
    assert resp["success"] is True
    assert resp["data"]["control_id"] == "txt_customer"


def test_health_check_returns_environment_info():
    server, sid = _server()
    resp = server.call_tool("health_check", {"session_id": sid})
    assert resp["success"] is True
    data = resp["data"]
    assert "platform" in data
    assert "python_version" in data
    assert "uia_available" in data
    assert "mcp_pid" in data
    assert "libraries" in data
    assert "foreground_window" in data
