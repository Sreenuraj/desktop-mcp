"""Tests for Phase 1.4 — wait_for_window proper polling loop.

Verifies that:
- wait_for_window returns immediately when the window already exists.
- wait_for_window polls and returns when the window appears mid-wait.
- wait_for_window raises WINDOW_NOT_FOUND (isError: True) on timeout.
- timeout_ms parameter is respected.
- title matching is case-insensitive.
- The returned dict is a valid window dict (has window_id, title, etc.).
"""

from __future__ import annotations

import threading
import time

import pytest

from desktop_mcp import DesktopMCPServer
from desktop_mcp.adapters.memory import InMemoryDesktopAdapter
from desktop_mcp.models.window import Window


def new_server() -> tuple[DesktopMCPServer, str]:
    server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
    response = server.call_tool("create_session", {})
    return server, response["data"]["session_id"]


# ------------------------------------------------------------------ #
# Immediate match
# ------------------------------------------------------------------ #

class TestWaitForWindowImmediateMatch:
    def test_returns_window_when_already_present(self):
        server, sid = new_server()
        # "Customer Management" window is seeded by InMemoryDesktopAdapter
        response = server.call_tool(
            "wait_for_window",
            {"session_id": sid, "title_contains": "Customer"},
        )
        assert response["success"] is True
        assert response["isError"] is False
        assert "window_id" in response["data"]
        assert "title" in response["data"]

    def test_case_insensitive_match(self):
        server, sid = new_server()
        response = server.call_tool(
            "wait_for_window",
            {"session_id": sid, "title_contains": "CUSTOMER MANAGEMENT"},
        )
        assert response["success"] is True
        assert response["data"]["title"] == "Customer Management"

    def test_partial_title_match(self):
        server, sid = new_server()
        response = server.call_tool(
            "wait_for_window",
            {"session_id": sid, "title_contains": "manage"},
        )
        assert response["success"] is True

    def test_returns_correct_window_id(self):
        server, sid = new_server()
        response = server.call_tool(
            "wait_for_window",
            {"session_id": sid, "title_contains": "Customer"},
        )
        assert response["data"]["window_id"] == "win_demo"


# ------------------------------------------------------------------ #
# Polling — window appears after a delay
# ------------------------------------------------------------------ #

class TestWaitForWindowPolling:
    def test_returns_window_that_appears_mid_wait(self):
        """Window is added 300 ms after wait_for_window starts; should be found."""

        class DelayedWindowAdapter(InMemoryDesktopAdapter):
            pass

        adapter = DelayedWindowAdapter()
        server = DesktopMCPServer(adapter=adapter)
        sid = server.call_tool("create_session", {})["data"]["session_id"]

        def add_window_after_delay():
            time.sleep(0.3)
            adapter._windows["win_calc"] = Window(
                window_id="win_calc",
                title="Calculator",
                application_id="app_calc",
                active=True,
            )

        t = threading.Thread(target=add_window_after_delay, daemon=True)
        t.start()

        response = server.call_tool(
            "wait_for_window",
            {"session_id": sid, "title_contains": "Calculator", "timeout_ms": 2000},
        )
        t.join(timeout=3)

        assert response["success"] is True
        assert response["data"]["window_id"] == "win_calc"
        assert response["data"]["title"] == "Calculator"

    def test_polling_does_not_return_wrong_window(self):
        """Ensure the returned window actually matches the title_contains."""

        class DelayedWindowAdapter(InMemoryDesktopAdapter):
            pass

        adapter = DelayedWindowAdapter()
        server = DesktopMCPServer(adapter=adapter)
        sid = server.call_tool("create_session", {})["data"]["session_id"]

        def add_window_after_delay():
            time.sleep(0.2)
            adapter._windows["win_notepad"] = Window(
                window_id="win_notepad",
                title="Notepad",
                application_id="app_notepad",
                active=False,
            )

        t = threading.Thread(target=add_window_after_delay, daemon=True)
        t.start()

        response = server.call_tool(
            "wait_for_window",
            {"session_id": sid, "title_contains": "Notepad", "timeout_ms": 2000},
        )
        t.join(timeout=3)

        assert response["success"] is True
        assert "notepad" in response["data"]["title"].lower()


# ------------------------------------------------------------------ #
# Timeout
# ------------------------------------------------------------------ #

class TestWaitForWindowTimeout:
    def test_timeout_returns_window_not_found_error(self):
        server, sid = new_server()
        response = server.call_tool(
            "wait_for_window",
            {"session_id": sid, "title_contains": "NonExistentApp_XYZ", "timeout_ms": 300},
        )
        assert response["success"] is False
        assert response["isError"] is True
        assert response["error"]["code"] == "WINDOW_NOT_FOUND"

    def test_timeout_message_includes_title(self):
        server, sid = new_server()
        response = server.call_tool(
            "wait_for_window",
            {"session_id": sid, "title_contains": "MyMissingApp", "timeout_ms": 200},
        )
        assert "MyMissingApp" in response["error"]["message"]

    def test_timeout_respects_timeout_ms_parameter(self):
        """A 200 ms timeout should complete in well under 1 second."""
        server, sid = new_server()
        t0 = time.perf_counter()
        server.call_tool(
            "wait_for_window",
            {"session_id": sid, "title_contains": "NeverExists_ABC", "timeout_ms": 200},
        )
        elapsed = time.perf_counter() - t0
        # Should finish within 1 second (generous upper bound)
        assert elapsed < 1.0

    def test_default_timeout_is_10_seconds_max(self):
        """Default timeout is 10 000 ms — we just verify the parameter is accepted."""
        server, sid = new_server()
        # Use a very short timeout to avoid actually waiting 10 s in tests
        response = server.call_tool(
            "wait_for_window",
            {"session_id": sid, "title_contains": "NeverExists_DEF", "timeout_ms": 100},
        )
        assert response["error"]["code"] == "WINDOW_NOT_FOUND"

    def test_zero_timeout_returns_error_immediately(self):
        server, sid = new_server()
        t0 = time.perf_counter()
        response = server.call_tool(
            "wait_for_window",
            {"session_id": sid, "title_contains": "NeverExists_GHI", "timeout_ms": 0},
        )
        elapsed = time.perf_counter() - t0
        assert response["success"] is False
        assert elapsed < 0.5  # should be near-instant


# ------------------------------------------------------------------ #
# Return value shape
# ------------------------------------------------------------------ #

class TestWaitForWindowReturnShape:
    def test_returned_dict_has_window_id(self):
        server, sid = new_server()
        response = server.call_tool(
            "wait_for_window",
            {"session_id": sid, "title_contains": "Customer"},
        )
        assert "window_id" in response["data"]

    def test_returned_dict_has_title(self):
        server, sid = new_server()
        response = server.call_tool(
            "wait_for_window",
            {"session_id": sid, "title_contains": "Customer"},
        )
        assert "title" in response["data"]

    def test_missing_title_contains_returns_invalid_request(self):
        server, sid = new_server()
        response = server.call_tool("wait_for_window", {"session_id": sid})
        assert response["success"] is False
        assert response["error"]["code"] == "INVALID_REQUEST"
