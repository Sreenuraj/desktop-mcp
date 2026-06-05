from __future__ import annotations

from desktop_mcp.errors import DesktopMCPError


class WindowsUIAutomationAdapter:
    """Windows UI Automation adapter placeholder.

    The public API is isolated here so the server can remain platform independent.
    The concrete pywinauto/UIA implementation should be added behind these methods.
    """

    def _not_implemented(self) -> None:
        raise DesktopMCPError("Windows UI Automation adapter is not implemented yet")

    def launch_application(self, path: str, arguments: list[str] | None = None):
        self._not_implemented()

    def attach_application(self, process_id: int):
        self._not_implemented()

    def close_application(self, application_id: str) -> None:
        self._not_implemented()

    def list_windows(self):
        self._not_implemented()

    def activate_window(self, window_id: str) -> None:
        self._not_implemented()

    def close_window(self, window_id: str) -> None:
        self._not_implemented()

    def resize_window(self, window_id: str, state: str) -> None:
        self._not_implemented()

    def get_window(self, window_id: str):
        self._not_implemented()

    def find_control(self, window_id: str, text: str | None = None, type: str | None = None):
        self._not_implemented()

    def find_controls(self, window_id: str, type: str | None = None):
        self._not_implemented()

    def get_control(self, control_id: str):
        self._not_implemented()

    def interact(self, action: str, control_id: str, **kwargs):
        self._not_implemented()

    def read_table(self, control_id: str):
        self._not_implemented()

    def capture_window(self, window_id: str):
        self._not_implemented()

    def capture_desktop(self):
        self._not_implemented()
