from __future__ import annotations

import os
import time
from unittest import mock

from desktop_mcp.adapters.memory import InMemoryDesktopAdapter
from desktop_mcp.adapters.windows.uia_adapter import WindowsUIAutomationAdapter
from desktop_mcp.server.mcp_server import DesktopMCPServer


def test_action_log_collection():
    server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())

    # 1. create_session should initialize session and log itself
    res = server.call_tool("create_session", {})
    assert res["success"] is True
    session_id = res["data"]["session_id"]

    session = server.sessions.get_session(session_id)
    assert len(session.logs) == 1
    assert session.logs[0]["tool"] == "create_session"
    assert session.logs[0]["status"] == "success"

    # 2. Call other tools, should append to logs
    server.call_tool("list_windows", {"session_id": session_id})
    assert len(session.logs) == 2
    assert session.logs[1]["tool"] == "list_windows"
    assert session.logs[1]["status"] == "success"
    assert isinstance(session.logs[1]["duration"], float)


def test_report_generation(tmp_path):
    # Set evidence dir using temporary path
    env_mock = {"DESKTOP_MCP_EVIDENCE_DIR": str(tmp_path)}
    with mock.patch.dict(os.environ, env_mock):
        server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
        res = server.call_tool("create_session", {})
        session_id = res["data"]["session_id"]

        # Capture desktop (will write dummy file under session evidence dir)
        cap_res = server.call_tool("capture_desktop", {"session_id": session_id})
        assert cap_res["success"] is True
        artifact_path = cap_res["data"]["artifact"]
        assert os.path.exists(artifact_path)

        # Fail some assertion to test failure logging/evidence
        fail_res = server.call_tool(
            "assert_text",
            {
                "session_id": session_id,
                "control_id": "txt_customer",
                "expected": "WrongName",
            },
        )
        assert fail_res["success"] is False

        # Generate report
        rep_res = server.call_tool("generate_report", {"session_id": session_id})
        assert rep_res["success"] is True
        report_path = rep_res["data"]["artifact"]
        assert os.path.exists(report_path)

        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert f"# Session Execution Report - {session_id}" in content
        assert "create_session" in content
        assert "capture_desktop" in content
        assert "assert_text" in content


def test_gif_recorder_in_memory_adapter(tmp_path):
    env_mock = {"DESKTOP_MCP_EVIDENCE_DIR": str(tmp_path)}
    with mock.patch.dict(os.environ, env_mock):
        server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
        res = server.call_tool("create_session", {})
        session_id = res["data"]["session_id"]

        # Start recording
        start_res = server.call_tool("start_recording", {"session_id": session_id})
        assert start_res["success"] is True

        # Stop recording
        stop_res = server.call_tool("stop_recording", {"session_id": session_id})
        assert stop_res["success"] is True
        gif_path = stop_res["data"]["artifact"]
        assert os.path.exists(gif_path)
        assert gif_path.endswith(".gif")


def test_windows_gif_recorder_background_thread(tmp_path):
    adapter = WindowsUIAutomationAdapter()
    adapter._check_platform = mock.Mock()

    gif_path = os.path.join(tmp_path, "recording_windows.gif")

    # Mock PIL ImageGrab to return a mock frame
    mock_frame = mock.Mock()
    mock_frame.resize.return_value = mock_frame

    # Mock save to write a dummy file on disk so exists() passes
    def dummy_save(*args, **kwargs):
        with open(gif_path, "w") as f:
            f.write("mock gif")

    mock_frame.save.side_effect = dummy_save

    with mock.patch("desktop_mcp.adapters.windows.uia_adapter.ImageGrab") as mock_grab:
        mock_grab.grab.return_value = mock_frame

        # Start recording
        rec_res = adapter.start_recording(path=gif_path)
        assert rec_res["recording"] is True

        # Sleep briefly to allow frames to be captured in background
        time.sleep(0.5)

        # Stop recording
        stop_res = adapter.stop_recording()
        assert stop_res["recording"] is False
        assert os.path.exists(gif_path)

        # Verify save was called on first frame with append options
        mock_frame.save.assert_called_once()
        args, kwargs = mock_frame.save.call_args
        assert args[0] == os.path.abspath(gif_path)
        assert kwargs["save_all"] is True
        assert "append_images" in kwargs
