from __future__ import annotations

from typing import Protocol

from desktop_mcp.models.application import Application
from desktop_mcp.models.control import Control
from desktop_mcp.models.window import Window


class DesktopAdapter(Protocol):
    def launch_application(self, path: str, arguments: list[str] | None = None) -> Application:
        ...

    def attach_application(self, process_id: int) -> Application:
        ...

    def close_application(self, application_id: str) -> None:
        ...

    def list_windows(self) -> list[Window]:
        ...

    def activate_window(self, window_id: str) -> None:
        ...

    def close_window(self, window_id: str) -> None:
        ...

    def resize_window(self, window_id: str, state: str) -> None:
        ...

    def get_window(self, window_id: str) -> Window:
        ...

    def find_control(self, window_id: str, text: str | None = None, type: str | None = None) -> Control:
        ...

    def find_controls(self, window_id: str, type: str | None = None) -> list[Control]:
        ...

    def get_control(self, control_id: str) -> Control:
        ...

    def interact(self, action: str, control_id: str, **kwargs) -> dict:
        ...

    def read_table(self, control_id: str) -> dict:
        ...

    def capture_window(self, window_id: str) -> dict:
        ...

    def capture_desktop(self) -> dict:
        ...
