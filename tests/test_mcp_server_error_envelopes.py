"""Tests for Phase 1.6 — MCP isError convention and Phase 1.3 UNKNOWN_TOOL guard.

Verifies that:
- Every error response carries ``isError: True`` in the envelope.
- ``success: False`` and a structured ``error`` dict are always present.
- ``error.details`` is always a dict (never None).
- Unknown tool names return ``UNKNOWN_TOOL`` with a list of valid tools.
- ``SnapshotEmptyError`` surfaces as ``SNAPSHOT_EMPTY`` with ``isError: True``.
"""

from __future__ import annotations

import pytest

from desktop_mcp import DesktopMCPServer
from desktop_mcp.adapters.memory import InMemoryDesktopAdapter
from desktop_mcp.errors import SnapshotEmptyError, WindowNotFoundError


def new_server() -> tuple[DesktopMCPServer, str]:
    server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
    response = server.call_tool("create_session", {})
    return server, response["data"]["session_id"]


# ------------------------------------------------------------------ #
# isError field is always present
# ------------------------------------------------------------------ #

class TestIsErrorAlwaysPresent:
    def test_success_response_has_is_error_false(self):
        server, sid = new_server()
        response = server.call_tool("list_windows", {"session_id": sid})
        assert response["success"] is True
        assert response["isError"] is False

    def test_error_response_has_is_error_true(self):
        server, sid = new_server()
        response = server.call_tool("window_snapshot", {"session_id": sid, "window_id": "win_nonexistent"})
        assert response["success"] is False
        assert response["isError"] is True

    def test_session_not_found_has_is_error_true(self):
        server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
        response = server.call_tool("list_windows", {"session_id": "bad_session"})
        assert response["success"] is False
        assert response["isError"] is True

    def test_missing_required_field_has_is_error_true(self):
        server, sid = new_server()
        # window_id is required for window_snapshot
        response = server.call_tool("window_snapshot", {"session_id": sid})
        assert response["success"] is False
        assert response["isError"] is True

    def test_create_session_is_error_false(self):
        server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
        response = server.call_tool("create_session", {})
        assert response["isError"] is False


# ------------------------------------------------------------------ #
# Error envelope structure
# ------------------------------------------------------------------ #

class TestErrorEnvelopeStructure:
    def test_error_has_code_message_details(self):
        server, sid = new_server()
        response = server.call_tool("window_snapshot", {"session_id": sid, "window_id": "win_bad"})
        assert response["success"] is False
        error = response["error"]
        assert "code" in error
        assert "message" in error
        assert "details" in error
        assert isinstance(error["details"], dict)

    def test_success_error_is_none(self):
        server, sid = new_server()
        response = server.call_tool("list_windows", {"session_id": sid})
        assert response["error"] is None

    def test_data_is_none_on_error(self):
        server, sid = new_server()
        response = server.call_tool("window_snapshot", {"session_id": sid, "window_id": "win_bad"})
        assert response["data"] is None

    def test_all_keys_present_on_success(self):
        server, sid = new_server()
        response = server.call_tool("list_windows", {"session_id": sid})
        assert set(response.keys()) == {"success", "data", "error", "isError"}

    def test_all_keys_present_on_error(self):
        server, sid = new_server()
        response = server.call_tool("window_snapshot", {"session_id": sid, "window_id": "win_bad"})
        assert set(response.keys()) == {"success", "data", "error", "isError"}


# ------------------------------------------------------------------ #
# UNKNOWN_TOOL guard (Phase 1.3)
# ------------------------------------------------------------------ #

class TestUnknownToolGuard:
    def test_unknown_tool_returns_unknown_tool_code(self):
        server, sid = new_server()
        response = server.call_tool("not_a_tool", {"session_id": sid})
        assert response["success"] is False
        assert response["isError"] is True
        assert response["error"]["code"] == "UNKNOWN_TOOL"

    def test_unknown_tool_lists_valid_tools_in_details(self):
        server, sid = new_server()
        response = server.call_tool("desktop_snapshot_old", {"session_id": sid})
        details = response["error"]["details"]
        assert "valid_tools" in details
        assert isinstance(details["valid_tools"], list)
        assert "window_snapshot" in details["valid_tools"]
        assert "desktop_snapshot" in details["valid_tools"]

    def test_unknown_tool_includes_requested_tool_in_details(self):
        server, sid = new_server()
        response = server.call_tool("my_fake_tool", {"session_id": sid})
        details = response["error"]["details"]
        assert details.get("requested_tool") == "my_fake_tool"

    def test_removed_desktop_snapshot_is_now_valid(self):
        """desktop_snapshot was removed in 5bb4eb8 but is now restored (Phase 1.3)."""
        server, sid = new_server()
        response = server.call_tool("desktop_snapshot", {"session_id": sid})
        # Should succeed, not return UNKNOWN_TOOL
        assert response["success"] is True
        assert response["isError"] is False

    def test_assert_text_still_unknown(self):
        """assert_text was never a real tool — should still be UNKNOWN_TOOL."""
        server, sid = new_server()
        response = server.call_tool("assert_text", {"session_id": sid, "control_id": "x", "expected": "y"})
        assert response["error"]["code"] == "UNKNOWN_TOOL"


# ------------------------------------------------------------------ #
# SNAPSHOT_EMPTY error (Phase 1.1)
# ------------------------------------------------------------------ #

class TestSnapshotEmptyError:
    """Test that SnapshotEmptyError is correctly surfaced through the server."""

    def test_snapshot_empty_error_has_correct_code(self):
        """Simulate an adapter that raises SnapshotEmptyError."""

        class EmptyWindowAdapter(InMemoryDesktopAdapter):
            def get_window(self, window_id):
                raise SnapshotEmptyError(
                    "UIA returned no descendants for window 'Calculator'.",
                    details={
                        "window_id": window_id,
                        "title": "Calculator",
                        "is_foreground": False,
                        "uia_state": "empty",
                        "took_ms": 42,
                        "hint": "Try activate_window then window_snapshot again.",
                    },
                )

        server = DesktopMCPServer(adapter=EmptyWindowAdapter())
        sid = server.call_tool("create_session", {})["data"]["session_id"]
        response = server.call_tool("window_snapshot", {"session_id": sid, "window_id": "win_123"})

        assert response["success"] is False
        assert response["isError"] is True
        assert response["error"]["code"] == "SNAPSHOT_EMPTY"

    def test_snapshot_empty_error_details_include_hint(self):
        class EmptyWindowAdapter(InMemoryDesktopAdapter):
            def get_window(self, window_id):
                raise SnapshotEmptyError(
                    "Empty tree.",
                    details={
                        "window_id": window_id,
                        "title": "Calc",
                        "is_foreground": False,
                        "uia_state": "empty",
                        "took_ms": 10,
                        "hint": "Call activate_window first.",
                    },
                )

        server = DesktopMCPServer(adapter=EmptyWindowAdapter())
        sid = server.call_tool("create_session", {})["data"]["session_id"]
        response = server.call_tool("window_snapshot", {"session_id": sid, "window_id": "win_x"})

        details = response["error"]["details"]
        assert "hint" in details
        assert "activate_window" in details["hint"]
        assert details["uia_state"] == "empty"

    def test_snapshot_empty_error_details_include_window_id(self):
        class EmptyWindowAdapter(InMemoryDesktopAdapter):
            def get_window(self, window_id):
                raise SnapshotEmptyError(
                    "Empty.",
                    details={"window_id": window_id, "title": "X", "is_foreground": False,
                             "uia_state": "empty", "took_ms": 5, "hint": "retry"},
                )

        server = DesktopMCPServer(adapter=EmptyWindowAdapter())
        sid = server.call_tool("create_session", {})["data"]["session_id"]
        response = server.call_tool("window_snapshot", {"session_id": sid, "window_id": "win_42"})
        assert response["error"]["details"]["window_id"] == "win_42"
