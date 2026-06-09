"""Polish-and-replay tests.

Covers:
 - PID-based exclusion set computed from current+ancestors.
 - Bounded LRU element cache with generation invalidation.
 - DPI awareness setter falls back through documented APIs.
 - Structured tool-call logging with secret redaction.
 - replay_recording: schema validation, happy path, error reporting.

All tests run on macOS — Windows-only code paths are mocked.
"""

from __future__ import annotations

import io
import json
import logging
import sys
from unittest.mock import MagicMock

import pytest

import desktop_mcp.adapters.windows.uia_adapter as uia_mod
from desktop_mcp import DesktopMCPServer
from desktop_mcp.adapters.memory import InMemoryDesktopAdapter
from desktop_mcp.adapters.windows.uia_adapter import (
    WindowsUIAutomationAdapter,
    _LRUElementCache,
    _set_dpi_awareness,
)
from desktop_mcp.logging import (
    ToolCallTimer,
    _JSONFormatter,
    _redact_args,
    log_tool_call,
)


# ===========================================================================
# PID exclusion set
# ===========================================================================

class TestPIDExclusion:

    def test_returns_empty_when_psutil_missing(self, monkeypatch):
        monkeypatch.setattr(uia_mod, "psutil", None)
        adapter = WindowsUIAutomationAdapter()
        assert adapter._excluded_pids == frozenset()

    def test_includes_current_and_ancestor_pids(self, monkeypatch):
        # Build a fake 3-deep PID chain: 100 -> 200 -> 300
        mocks = {}
        for pid in (100, 200, 300):
            m = MagicMock()
            m.pid = pid
            mocks[pid] = m
        mocks[100].parent.return_value = mocks[200]
        mocks[200].parent.return_value = mocks[300]
        mocks[300].parent.return_value = None

        fake_psutil = MagicMock()
        fake_psutil.Process = MagicMock(return_value=mocks[100])
        monkeypatch.setattr(uia_mod, "psutil", fake_psutil)
        monkeypatch.setattr(uia_mod.os, "getpid", lambda: 100)

        adapter = WindowsUIAutomationAdapter()
        assert adapter._excluded_pids == frozenset({100, 200, 300})

    def test_cycle_in_ancestor_chain_does_not_loop(self, monkeypatch):
        m = MagicMock()
        m.pid = 42
        m.parent.return_value = m  # cycle: a process that is its own parent

        fake_psutil = MagicMock()
        fake_psutil.Process = MagicMock(return_value=m)
        monkeypatch.setattr(uia_mod, "psutil", fake_psutil)
        monkeypatch.setattr(uia_mod.os, "getpid", lambda: 42)

        adapter = WindowsUIAutomationAdapter()
        assert adapter._excluded_pids == frozenset({42})


# ===========================================================================
# LRU element cache
# ===========================================================================

class TestLRUElementCache:

    def test_set_get_roundtrip(self):
        c = _LRUElementCache(maxsize=4)
        c["a"] = "alpha"
        assert "a" in c
        assert c["a"] == "alpha"
        assert len(c) == 1

    def test_evicts_oldest_when_full(self):
        c = _LRUElementCache(maxsize=2)
        c["a"] = 1
        c["b"] = 2
        c["c"] = 3  # evicts "a"
        assert "a" not in c
        assert "b" in c
        assert "c" in c
        assert len(c) == 2

    def test_lru_order_updated_on_access(self):
        c = _LRUElementCache(maxsize=2)
        c["a"] = 1
        c["b"] = 2
        _ = c["a"]    # touch "a" → now "b" is oldest
        c["c"] = 3    # should evict "b"
        assert "a" in c
        assert "b" not in c
        assert "c" in c

    def test_bump_generation_clears_cache(self):
        c = _LRUElementCache(maxsize=4)
        c["a"] = 1
        c["b"] = 2
        gen_before = c.generation
        new_gen = c.bump_generation()
        assert new_gen == gen_before + 1
        assert len(c) == 0
        assert "a" not in c

    def test_pop_returns_value_and_removes_entry(self):
        c = _LRUElementCache(maxsize=4)
        c["a"] = "alpha"
        assert c.pop("a") == "alpha"
        assert "a" not in c
        assert c.pop("missing", "default") == "default"

    def test_adapter_uses_lru_cache(self):
        adapter = WindowsUIAutomationAdapter()
        assert isinstance(adapter._controls_cache, _LRUElementCache)


# ===========================================================================
# DPI awareness
# ===========================================================================

class TestDPIAwareness:

    @pytest.fixture(autouse=True)
    def reset_global(self):
        # Each test gets a fresh "not yet set" state.
        uia_mod._dpi_awareness_set = False
        yield
        uia_mod._dpi_awareness_set = False

    def test_no_op_when_ctypes_unavailable(self, monkeypatch):
        monkeypatch.setattr(uia_mod, "ctypes_mod", None)
        status = _set_dpi_awareness()
        assert status["method"] is None
        assert status["error"] == "ctypes unavailable"

    def test_uses_per_monitor_aware_v2_when_available(self, monkeypatch):
        ctypes_mock = MagicMock()
        # SetProcessDpiAwarenessContext(-4) returns True → V2 path wins
        set_ctx = MagicMock(return_value=True)
        ctypes_mock.windll.user32.SetProcessDpiAwarenessContext = set_ctx
        monkeypatch.setattr(uia_mod, "ctypes_mod", ctypes_mock)

        status = _set_dpi_awareness()
        assert "SetProcessDpiAwarenessContext(-4)" in status["method"]
        set_ctx.assert_called_with(-4)

    def test_falls_back_to_setprocessdpiaware_when_modern_apis_fail(self, monkeypatch):
        ctypes_mock = MagicMock()
        # All modern paths fail
        ctypes_mock.windll.user32.SetProcessDpiAwarenessContext = MagicMock(
            return_value=False
        )
        # shcore.SetProcessDpiAwareness returns non-zero (failure)
        shcore = MagicMock()
        shcore.SetProcessDpiAwareness = MagicMock(return_value=1)
        # Make ctypes_mock.windll.shcore return our shcore mock
        ctypes_mock.windll.shcore = shcore
        # SetProcessDPIAware succeeds (no return checked)
        ctypes_mock.windll.user32.SetProcessDPIAware = MagicMock()

        monkeypatch.setattr(uia_mod, "ctypes_mod", ctypes_mock)
        status = _set_dpi_awareness()
        assert status["method"] == "SetProcessDPIAware"

    def test_idempotent_when_already_set(self, monkeypatch):
        uia_mod._dpi_awareness_set = True
        ctypes_mock = MagicMock()
        monkeypatch.setattr(uia_mod, "ctypes_mod", ctypes_mock)
        status = _set_dpi_awareness()
        assert status["already_set"] is True
        assert status["method"] is None
        # Must not have called any DPI setters when already set.
        ctypes_mock.windll.user32.SetProcessDpiAwarenessContext.assert_not_called()


# ===========================================================================
# Structured logging
# ===========================================================================

class TestStructuredLogging:

    def test_redacts_password_key(self):
        out = _redact_args("click", {"username": "alice", "password": "hunter2"})
        assert out["username"] == "alice"
        assert out["password"] == "***redacted***"

    def test_redacts_value_for_enter_text(self):
        out = _redact_args("enter_text", {"control_id": "ctrl_1", "value": "secret"})
        assert out["control_id"] == "ctrl_1"
        assert out["value"] == "***redacted***"

    def test_does_not_redact_value_for_other_tools(self):
        out = _redact_args("select_item", {"value": "Option A"})
        assert out["value"] == "Option A"

    def test_non_dict_args_yield_empty(self):
        assert _redact_args("click", None) == {}
        assert _redact_args("click", "not a dict") == {}

    def test_json_formatter_emits_one_line_json(self):
        formatter = _JSONFormatter()
        record = logging.LogRecord(
            name="desktop_mcp.tool", level=logging.INFO, pathname="x",
            lineno=1, msg="tool_call click success", args=(), exc_info=None,
        )
        record.tool = "click"
        record.took_ms = 12
        record.result_kind = "success"
        out = formatter.format(record)
        assert "\n" not in out
        payload = json.loads(out)
        assert payload["tool"] == "click"
        assert payload["took_ms"] == 12
        assert payload["result_kind"] == "success"

    def test_log_tool_call_emits_to_desktop_mcp_logger(self, monkeypatch):
        # Capture logs by attaching a StringIO handler.
        log = logging.getLogger("desktop_mcp")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(_JSONFormatter())
        log.addHandler(handler)
        try:
            log_tool_call(
                tool="click",
                args={"control_id": "ctrl_1", "password": "shh"},
                took_ms=5,
                result_kind="success",
                session_id="sess_test",
            )
        finally:
            log.removeHandler(handler)
        # Find the JSON line we just emitted.
        lines = [ln for ln in stream.getvalue().splitlines() if ln.strip()]
        assert lines, "No log line emitted"
        payload = json.loads(lines[-1])
        assert payload["tool"] == "click"
        assert payload["args"]["password"] == "***redacted***"
        assert payload["session_id"] == "sess_test"

    def test_tool_call_timer_records_outcome(self, monkeypatch):
        # Capture log emissions.
        captured = {}

        def fake_log(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr("desktop_mcp.logging.log_tool_call", fake_log)
        with ToolCallTimer("click", {"x": 1}, session_id="sess_x") as t:
            t.result_kind = "success"

        assert captured["tool"] == "click"
        assert captured["result_kind"] == "success"
        assert captured["session_id"] == "sess_x"
        assert isinstance(captured["took_ms"], int)


# ===========================================================================
# server-level logging integration
# ===========================================================================

class TestServerLoggingIntegration:

    def test_call_tool_emits_structured_log_on_success(self, monkeypatch):
        # Replace log_tool_call with a spy so we don't have to parse stderr.
        calls = []

        def spy(**kwargs):
            calls.append(kwargs)

        monkeypatch.setattr("desktop_mcp.server.mcp_server.log_tool_call", spy)

        server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
        server.call_tool("create_session", {})

        assert calls, "log_tool_call should have been invoked"
        assert calls[-1]["tool"] == "create_session"
        assert calls[-1]["result_kind"] == "success"

    def test_call_tool_emits_error_code_on_failure(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "desktop_mcp.server.mcp_server.log_tool_call",
            lambda **kw: calls.append(kw),
        )
        server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
        server.call_tool("bogus_tool_xyz", {})
        assert calls[-1]["result_kind"] == "error"
        assert calls[-1]["error_code"] == "UNKNOWN_TOOL"


# ===========================================================================
# replay_recording
# ===========================================================================

def _make_server() -> tuple[DesktopMCPServer, str]:
    server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
    sid = server.call_tool("create_session", {})["data"]["session_id"]
    return server, sid


class TestReplayRecording:

    def test_replay_recording_is_registered(self):
        server, _ = _make_server()
        assert "replay_recording" in server.tools

    def test_happy_path_runs_every_step(self, tmp_path):
        server, sid = _make_server()
        recording = {
            "version": 1,
            "steps": [
                {"tool": "list_windows", "arguments": {}},
                {"tool": "window_snapshot",
                 "arguments": {"window_id": "win_demo"}},
                {"tool": "click", "arguments": {"control_id": "btn_save"}},
            ],
        }
        path = tmp_path / "rec.json"
        path.write_text(json.dumps(recording))

        resp = server.call_tool(
            "replay_recording",
            {"session_id": sid, "path": str(path)},
        )
        assert resp["success"] is True
        data = resp["data"]
        assert data["steps_total"] == 3
        assert data["steps_executed"] == 3
        assert data["steps_succeeded"] == 3
        assert data["steps_failed"] == 0
        assert data["aborted"] is False

    def test_accepts_bare_list_format(self, tmp_path):
        server, sid = _make_server()
        path = tmp_path / "rec.json"
        path.write_text(json.dumps([
            {"tool": "list_windows", "arguments": {}},
        ]))
        resp = server.call_tool(
            "replay_recording",
            {"session_id": sid, "path": str(path)},
        )
        assert resp["success"] is True
        assert resp["data"]["steps_succeeded"] == 1

    def test_session_id_is_injected_into_each_step(self, tmp_path):
        """Steps that omit session_id should get the replayer's session_id."""
        server, sid = _make_server()
        path = tmp_path / "rec.json"
        # Note: no session_id in the step's arguments.
        path.write_text(json.dumps({
            "steps": [{"tool": "list_windows", "arguments": {}}],
        }))
        resp = server.call_tool(
            "replay_recording",
            {"session_id": sid, "path": str(path)},
        )
        assert resp["success"] is True
        assert resp["data"]["results"][0]["success"] is True

    def test_stop_on_error_aborts_on_first_failure(self, tmp_path):
        server, sid = _make_server()
        path = tmp_path / "rec.json"
        path.write_text(json.dumps({
            "steps": [
                {"tool": "list_windows", "arguments": {}},
                {"tool": "click", "arguments": {"control_id": "ghost_ctrl"}},
                # This step should never run because we abort on the failure above.
                {"tool": "list_windows", "arguments": {}},
            ],
        }))
        resp = server.call_tool(
            "replay_recording",
            {"session_id": sid, "path": str(path), "stop_on_error": True},
        )
        assert resp["success"] is True
        data = resp["data"]
        assert data["aborted"] is True
        assert data["steps_executed"] == 2
        assert data["steps_failed"] == 1

    def test_stop_on_error_false_runs_every_step(self, tmp_path):
        server, sid = _make_server()
        path = tmp_path / "rec.json"
        path.write_text(json.dumps({
            "steps": [
                {"tool": "list_windows", "arguments": {}},
                {"tool": "click", "arguments": {"control_id": "ghost_ctrl"}},
                {"tool": "list_windows", "arguments": {}},
            ],
        }))
        resp = server.call_tool(
            "replay_recording",
            {"session_id": sid, "path": str(path), "stop_on_error": False},
        )
        assert resp["success"] is True
        data = resp["data"]
        assert data["aborted"] is False
        assert data["steps_executed"] == 3
        assert data["steps_succeeded"] == 2
        assert data["steps_failed"] == 1

    def test_missing_file_returns_invalid_request(self, tmp_path):
        server, sid = _make_server()
        resp = server.call_tool(
            "replay_recording",
            {"session_id": sid, "path": str(tmp_path / "does_not_exist.json")},
        )
        assert resp["success"] is False
        assert resp["isError"] is True
        assert resp["error"]["code"] == "INVALID_REQUEST"

    def test_malformed_json_returns_error(self, tmp_path):
        server, sid = _make_server()
        path = tmp_path / "bad.json"
        path.write_text("not valid json {")
        resp = server.call_tool(
            "replay_recording",
            {"session_id": sid, "path": str(path)},
        )
        assert resp["success"] is False
        assert resp["isError"] is True

    def test_missing_steps_field_returns_invalid_request(self, tmp_path):
        server, sid = _make_server()
        path = tmp_path / "rec.json"
        path.write_text(json.dumps({"version": 1, "metadata": {}}))
        resp = server.call_tool(
            "replay_recording",
            {"session_id": sid, "path": str(path)},
        )
        assert resp["success"] is False
        assert resp["isError"] is True
        assert resp["error"]["code"] == "INVALID_REQUEST"

    def test_step_without_tool_field_is_reported_as_failure(self, tmp_path):
        server, sid = _make_server()
        path = tmp_path / "rec.json"
        path.write_text(json.dumps({
            "steps": [{"arguments": {"foo": "bar"}}],
        }))
        resp = server.call_tool(
            "replay_recording",
            {"session_id": sid, "path": str(path), "stop_on_error": False},
        )
        assert resp["success"] is True
        assert resp["data"]["steps_failed"] == 1
        assert resp["data"]["results"][0]["error"]["code"] == "INVALID_REQUEST"

    def test_args_alias_is_accepted(self, tmp_path):
        """Legacy recordings may use 'args' instead of 'arguments'."""
        server, sid = _make_server()
        path = tmp_path / "rec.json"
        path.write_text(json.dumps({
            "steps": [{"tool": "list_windows", "args": {}}],
        }))
        resp = server.call_tool(
            "replay_recording",
            {"session_id": sid, "path": str(path)},
        )
        assert resp["success"] is True
        assert resp["data"]["steps_succeeded"] == 1
