from unittest import mock

from desktop_mcp.adapters.memory import InMemoryDesktopAdapter
from desktop_mcp.adapters.windows.uia_adapter import WindowsUIAutomationAdapter
from desktop_mcp.server.mcp_server import DesktopMCPServer


def test_in_memory_browser_flow():
    server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())

    # Initialize session
    res = server.call_tool("create_session", {})
    assert res["success"] is True
    session_id = res["data"]["session_id"]

    # 1. Wait for browser should return win_browser_001
    wait_res = server.call_tool("wait_for_browser", {"session_id": session_id})
    assert wait_res["success"] is True
    window_id = wait_res["data"]["window_id"]
    assert window_id == "win_browser_001"

    # 2. Get snapshot of browser controls
    snap_res = server.call_tool(
        "window_snapshot", {"session_id": session_id, "window_id": window_id}
    )
    assert snap_res["success"] is True
    controls = snap_res["data"]["controls"]

    # Find email, password and submit controls
    email_ctrl = next(c for c in controls if c["name"] == "Email Address")
    passwd_ctrl = next(c for c in controls if c["name"] == "Password")
    submit_ctrl = next(c for c in controls if c["name"] == "Sign In")

    # 3. Enter Email
    enter_email = server.call_tool(
        "enter_text",
        {
            "session_id": session_id,
            "control_id": email_ctrl["id"],
            "value": "test@microsoft.com",
        },
    )
    assert enter_email["success"] is True

    # 4. Enter Password
    enter_pass = server.call_tool(
        "enter_text",
        {
            "session_id": session_id,
            "control_id": passwd_ctrl["id"],
            "value": "secret123",
        },
    )
    assert enter_pass["success"] is True

    # 5. Click Sign In
    click_res = server.call_tool(
        "click", {"session_id": session_id, "control_id": submit_ctrl["id"]}
    )
    assert click_res["success"] is True

    # 6. Read back entered values to verify state mutation
    read_email = server.call_tool(
        "read_text", {"session_id": session_id, "control_id": email_ctrl["id"]}
    )
    assert read_email["data"]["value"] == "test@microsoft.com"


def test_attach_browser_window_success():
    server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
    res = server.call_tool("create_session", {})
    session_id = res["data"]["session_id"]

    # Attach by matching title
    attach_res = server.call_tool(
        "attach_browser_window", {"session_id": session_id, "title_contains": "Edge"}
    )
    assert attach_res["success"] is True
    assert attach_res["data"]["window_id"] == "win_browser_001"


def test_attach_browser_window_failure():
    server = DesktopMCPServer(adapter=InMemoryDesktopAdapter())
    res = server.call_tool("create_session", {})
    session_id = res["data"]["session_id"]

    # Attach with wrong title should fail
    attach_res = server.call_tool(
        "attach_browser_window", {"session_id": session_id, "title_contains": "Chrome"}
    )
    assert attach_res["success"] is False
    assert attach_res["error"]["code"] == "WINDOW_NOT_FOUND"


def test_windows_adapter_browser_detection():
    adapter = WindowsUIAutomationAdapter()
    adapter._check_platform = mock.Mock()

    # Mock list_windows to return windows
    win_mock = mock.Mock()
    win_mock.window_id = "win_chrome_999"
    win_mock.title = "Microsoft Authentication - Google Chrome"
    win_mock.application_id = "app_1234"

    adapter.list_windows = mock.Mock(return_value=[win_mock])

    # Verify chrome suffix triggers detection
    res = adapter.wait_for_browser(timeout=1.0)
    assert res["window_id"] == "win_chrome_999"

    # Verify chrome suffix triggers attachment
    attach_res = adapter.attach_browser_window(title_contains="Microsoft")
    assert attach_res["window_id"] == "win_chrome_999"
