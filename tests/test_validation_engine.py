from __future__ import annotations

import pytest
from unittest import mock

from desktop_mcp.errors import ControlNotFoundError, InvalidRequestError
from desktop_mcp.models.control import Control
from desktop_mcp.server.mcp_server import DesktopMCPServer


def test_wait_for_control_retry_success():
    mock_adapter = mock.Mock()
    
    # Setup adapter to fail the first two times, then succeed on the third
    ctrl = Control(id="btn_submit", name="Submit", type="Button")
    
    call_count = 0
    def find_control_side_effect(window_id, text, type_):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ControlNotFoundError("Not ready yet")
        return ctrl

    mock_adapter.find_control.side_effect = find_control_side_effect
    
    server = DesktopMCPServer(adapter=mock_adapter)
    server.call_tool("create_session", {})
    
    response = server.call_tool(
        "wait_for_control",
        {
            "session_id": "session_001",
            "window_id": "win_123",
            "text": "Submit",
            "timeout": 2.0,
        }
    )
    
    assert response["success"] is True
    assert response["data"]["control"]["id"] == "btn_submit"
    assert call_count == 3  # Verified it polled 3 times


def test_wait_for_control_timeout():
    mock_adapter = mock.Mock()
    mock_adapter.find_control.side_effect = ControlNotFoundError("Never found")
    
    server = DesktopMCPServer(adapter=mock_adapter)
    server.call_tool("create_session", {})
    
    # Should poll and then raise ControlNotFoundError
    response = server.call_tool(
        "wait_for_control",
        {
            "session_id": "session_001",
            "window_id": "win_123",
            "text": "Submit",
            "timeout": 0.2,
        }
    )
    
    assert response["success"] is False
    assert response["error"]["code"] == "CONTROL_NOT_FOUND"


def test_assert_text_success_and_metadata():
    mock_adapter = mock.Mock()
    ctrl = Control(id="lbl_status", name="Status", type="Text", value="Complete")
    mock_adapter.get_control.return_value = ctrl

    server = DesktopMCPServer(adapter=mock_adapter)
    server.call_tool("create_session", {})
    
    response = server.call_tool(
        "assert_text",
        {
            "session_id": "session_001",
            "control_id": "lbl_status",
            "expected": "Complete",
        }
    )
    
    assert response["success"] is True
    assert response["data"]["passed"] is True
    assert response["data"]["expected"] == "Complete"
    assert response["data"]["actual"] == "Complete"


def test_assert_text_failure_triggers_screenshot():
    mock_adapter = mock.Mock()
    ctrl = Control(id="lbl_status", name="Status", type="Text", value="Pending")
    mock_adapter.get_control.return_value = ctrl
    
    server = DesktopMCPServer(adapter=mock_adapter)
    server.call_tool("create_session", {})
    
    response = server.call_tool(
        "assert_text",
        {
            "session_id": "session_001",
            "control_id": "lbl_status",
            "expected": "Complete",
        }
    )
    
    assert response["success"] is False
    assert response["error"]["code"] == "INVALID_REQUEST"
    # Verify capture_desktop was called due to assertion failure
    mock_adapter.capture_desktop.assert_called_once()


def test_assert_control_state_success():
    mock_adapter = mock.Mock()
    ctrl = Control(id="btn_ok", name="OK", type="Button", enabled=True, visible=True, focused=False)
    mock_adapter.get_control.return_value = ctrl

    server = DesktopMCPServer(adapter=mock_adapter)
    server.call_tool("create_session", {})
    
    response = server.call_tool(
        "assert_control_state",
        {
            "session_id": "session_001",
            "control_id": "btn_ok",
            "enabled": True,
            "visible": True,
            "focused": False,
        }
    )
    
    assert response["success"] is True
    assert response["data"]["passed"] is True


def test_assert_control_state_failure_triggers_screenshot():
    mock_adapter = mock.Mock()
    ctrl = Control(id="btn_ok", name="OK", type="Button", enabled=False, visible=True, focused=False)
    mock_adapter.get_control.return_value = ctrl

    server = DesktopMCPServer(adapter=mock_adapter)
    server.call_tool("create_session", {})
    
    response = server.call_tool(
        "assert_control_state",
        {
            "session_id": "session_001",
            "control_id": "btn_ok",
            "enabled": True,  # Fails since control.enabled is False
        }
    )
    
    assert response["success"] is False
    assert response["error"]["code"] == "INVALID_REQUEST"
    mock_adapter.capture_desktop.assert_called_once()
