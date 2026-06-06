from __future__ import annotations

from typing import Protocol

from desktop_mcp.models.application import Application
from desktop_mcp.models.control import Control
from desktop_mcp.models.window import Window


class DesktopAdapter(Protocol):
    def launch_application(
        self, path: str, arguments: list[str] | None = None
    ) -> Application:
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

    def find_control(
        self, window_id: str, text: str | None = None, type: str | None = None
    ) -> Control:
        ...

    def find_controls(self, window_id: str, type: str | None = None) -> list[Control]:
        ...

    def get_control(self, control_id: str) -> Control:
        ...

    def interact(self, action: str, control_id: str, **kwargs) -> dict:
        ...

    def read_table(self, control_id: str) -> dict:
        ...

    def capture_window(
        self,
        window_id: str,
        path: str | None = None,
        highlight_rect: tuple[int, int, int, int] | None = None,
    ) -> dict:
        ...

    def capture_desktop(
        self,
        path: str | None = None,
        highlight_rect: tuple[int, int, int, int] | None = None,
    ) -> dict:
        ...

    def wait_for_browser(self, timeout: float = 60.0) -> dict:
        ...

    def attach_browser_window(self, title_contains: str | None = None) -> dict:
        ...

    def click_at(self, x: int, y: int, button: str = "left") -> dict:
        ...
