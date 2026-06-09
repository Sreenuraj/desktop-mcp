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
    # Agent needs these fields to decide whether to retry
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
    resp = server.call_tool(
        "click", {"session_id": sid, "control_id": "btn_save"}
    )
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
    # Disable the control first
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
    # Override evidence dir to tmp_path
    with mock.patch.dict(os.environ, {"DESKTOP_MCP_EVIDENCE_DIR": str(tmp_path)}):
        resp = server.call_tool("capture_window", {"session_id": sid, "window_id": "win_demo"})
    assert resp["success"] is True
    assert "artifact" in resp["data"]


def test_generate_report_creates_markdown(tmp_path):
    server, sid = _server()
    # Do something so the log has entries
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
