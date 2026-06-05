import os
from unittest import mock

from desktop_mcp.adapters.memory import InMemoryDesktopAdapter
from desktop_mcp.adapters.windows.uia_adapter import WindowsUIAutomationAdapter
from desktop_mcp.server.mcp_server import DesktopMCPServer


def test_default_adapter_on_non_windows():
    # If platform is not win32, and no env var is set, it should
    # default to memory adapter
    with mock.patch("sys.platform", "darwin"):
        with mock.patch.dict(os.environ, {}, clear=True):
            server = DesktopMCPServer()
            assert isinstance(server.adapter, InMemoryDesktopAdapter)


def test_explicit_memory_adapter_env():
    # Setting DESKTOP_MCP_ADAPTER=memory should select InMemoryDesktopAdapter
    with mock.patch.dict(os.environ, {"DESKTOP_MCP_ADAPTER": "memory"}):
        server = DesktopMCPServer()
        assert isinstance(server.adapter, InMemoryDesktopAdapter)


def test_explicit_uia_adapter_env():
    # Setting DESKTOP_MCP_ADAPTER=uia should select WindowsUIAutomationAdapter
    with mock.patch.dict(os.environ, {"DESKTOP_MCP_ADAPTER": "uia"}):
        server = DesktopMCPServer()
        assert isinstance(server.adapter, WindowsUIAutomationAdapter)


def test_default_adapter_on_windows():
    # On Windows, if no env var is set, it should default to WindowsUIAutomationAdapter
    with mock.patch("sys.platform", "win32"):
        with mock.patch.dict(os.environ, {}, clear=True):
            server = DesktopMCPServer()
            assert isinstance(server.adapter, WindowsUIAutomationAdapter)
