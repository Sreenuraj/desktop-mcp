from __future__ import annotations

from itertools import count
from typing import Any

from desktop_mcp.errors import (
    AppNotFoundError,
    ControlDisabledError,
    ControlNotFoundError,
    WindowNotFoundError,
)
from desktop_mcp.models.application import Application
from desktop_mcp.models.control import Control
from desktop_mcp.models.window import Window


class InMemoryDesktopAdapter:
    """Deterministic adapter for local development and contract tests."""

    def __init__(self) -> None:
        self._app_counter = count(1)
        self._window_counter = count(1)
        self._applications: dict[str, Application] = {}
        self._windows: dict[str, Window] = {}
        self._controls: dict[str, Control] = {}
        self._recording = False
        self._recording_path: str | None = None
        self.seed()

    def seed(self) -> None:
        app = Application(application_id="app_demo", process_id=1000, path="demo.exe")
        controls = [
            Control(
                id="btn_save",
                automation_id="btnSave",
                name="Save",
                type="Button",
                patterns=["InvokePattern"],
            ),
            Control(
                id="txt_customer",
                automation_id="txtCustomer",
                name="Customer",
                type="Edit",
                value="",
            ),
            Control(
                id="ddl_state",
                automation_id="ddlState",
                name="State",
                type="ComboBox",
                value="",
            ),
            Control(
                id="grid_customers",
                automation_id="gridCustomers",
                name="Customers",
                type="DataGrid",
                metadata={
                    "columns": ["Name", "Status"],
                    "rows": [
                        {"Name": "Jane Doe", "Status": "Pending"},
                        {"Name": "John Doe", "Status": "Approved"},
                    ],
                },
            ),
        ]
        window = Window(
            window_id="win_demo",
            application_id=app.application_id,
            title="Customer Management",
            active=True,
            controls=controls,
        )
        self._applications[app.application_id] = app
        self._windows[window.window_id] = window
        for control in controls:
            self._controls[control.id] = control

    def launch_application(
        self, path: str, arguments: list[str] | None = None
    ) -> Application:
        application_id = f"app_{next(self._app_counter):03d}"
        window_id = f"win_{next(self._window_counter):03d}"
        app = Application(
            application_id=application_id,
            process_id=2000 + len(self._applications),
            path=path,
        )
        window = Window(
            window_id=window_id,
            application_id=application_id,
            title=path.rsplit("\\", 1)[-1] or path,
            active=True,
        )
        self._applications[application_id] = app
        self._windows[window_id] = window
        self.activate_window(window_id)
        return app

    def attach_application(self, process_id: int) -> Application:
        for app in self._applications.values():
            if app.process_id == process_id:
                return app
        application_id = f"app_{next(self._app_counter):03d}"
        app = Application(application_id=application_id, process_id=process_id)
        self._applications[application_id] = app
        return app

    def close_application(self, application_id: str) -> None:
        if application_id not in self._applications:
            raise AppNotFoundError(f"Application not found: {application_id}")
        del self._applications[application_id]
        stale_windows = [
            window_id
            for window_id, window in self._windows.items()
            if window.application_id == application_id
        ]
        for window_id in stale_windows:
            self.close_window(window_id)

    def list_windows(self) -> list[Window]:
        return list(self._windows.values())

    def activate_window(self, window_id: str) -> None:
        if window_id not in self._windows:
            raise WindowNotFoundError(f"Window not found: {window_id}")
        for window in self._windows.values():
            window.active = False
        self._windows[window_id].active = True

    def close_window(self, window_id: str) -> None:
        if window_id not in self._windows:
            raise WindowNotFoundError(f"Window not found: {window_id}")
        window = self._windows.pop(window_id)
        for control in window.controls:
            self._controls.pop(control.id, None)

    def resize_window(self, window_id: str, state: str) -> None:
        if window_id not in self._windows:
            raise WindowNotFoundError(f"Window not found: {window_id}")
        self._windows[window_id].title = self._windows[window_id].title

    def get_window(self, window_id: str) -> Window:
        try:
            return self._windows[window_id]
        except KeyError as exc:
            raise WindowNotFoundError(f"Window not found: {window_id}") from exc

    def find_control(
        self, window_id: str, text: str | None = None, type: str | None = None
    ) -> Control:
        matches = self.find_controls(window_id, type=type)
        if text is not None:
            matches = [
                control for control in matches if text.lower() in control.name.lower()
            ]
        if not matches:
            raise ControlNotFoundError("Control could not be located")
        return matches[0]

    def find_controls(self, window_id: str, type: str | None = None) -> list[Control]:
        window = self.get_window(window_id)
        if type is None:
            return list(window.controls)
        return [
            control
            for control in window.controls
            if control.type.lower() == type.lower()
        ]

    def get_control(self, control_id: str) -> Control:
        try:
            return self._controls[control_id]
        except KeyError as exc:
            raise ControlNotFoundError(f"Control not found: {control_id}") from exc

    def interact(self, action: str, control_id: str, **kwargs: Any) -> dict:
        control = self.get_control(control_id)
        if not control.enabled:
            raise ControlDisabledError(f"Control is disabled: {control_id}")
        if action in {"enter_text", "append_text"}:
            value = str(kwargs.get("value", ""))
            control.value = (
                value if action == "enter_text" else f"{control.value or ''}{value}"
            )
        elif action == "clear_text":
            control.value = ""
        elif action in {"select_dropdown", "select_tab", "select_radio", "check"}:
            control.value = str(kwargs.get("value", "true"))
        elif action == "uncheck":
            control.value = "false"
        elif action == "focus":
            for item in self._controls.values():
                item.focused = False
            control.focused = True
        elif action == "select_row":
            row_index = int(kwargs.get("row_index", 0))
            control.value = f"row_{row_index}"
        elif action == "edit_cell":
            row_index = int(kwargs.get("row_index", 0))
            column = str(kwargs.get("column", ""))
            value = str(kwargs.get("value", ""))
            if control.metadata and "rows" in control.metadata:
                control.metadata["rows"][row_index][column] = value
        return {"action": action, "control_id": control_id}

    def read_table(self, control_id: str) -> dict:
        control = self.get_control(control_id)
        return {
            "columns": control.metadata.get("columns", []),
            "rows": control.metadata.get("rows", []),
        }

    def find_row(self, control_id: str, criteria: dict[str, Any]) -> dict:
        table = self.read_table(control_id)
        for index, row in enumerate(table["rows"]):
            if all(row.get(key) == value for key, value in criteria.items()):
                return {"row_index": index, "row": row}
        raise ControlNotFoundError("Table row could not be located")

    def capture_window(
        self,
        window_id: str,
        path: str | None = None,
        highlight_rect: tuple[int, int, int, int] | None = None,
    ) -> dict:
        import os

        window = self.get_window(window_id)
        artifact_path = path or f"memory://screenshots/{window.window_id}.png"
        if path:
            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(path, "w") as f:
                f.write("dummy window screenshot")
        return {"window_id": window.window_id, "artifact": artifact_path}

    def capture_desktop(
        self,
        path: str | None = None,
        highlight_rect: tuple[int, int, int, int] | None = None,
    ) -> dict:
        import os

        artifact_path = path or "memory://screenshots/desktop.png"
        if path:
            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(path, "w") as f:
                f.write("dummy desktop screenshot")
        return {"artifact": artifact_path}

    def start_recording(self, path: str | None = None) -> dict:
        self._recording = True
        self._recording_path = path
        return {"recording": True}

    def stop_recording(self) -> dict:
        import os

        self._recording = False
        path = self._recording_path
        if path is None:
            path = "memory://recordings/session.gif"
        else:
            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            path = os.path.abspath(path)
            try:
                from PIL import Image

                dummy = Image.new("RGB", (100, 100), color="blue")
                dummy.save(path)
            except Exception:
                with open(path, "w") as f:
                    f.write("dummy gif content")
        return {"recording": False, "artifact": path}

    def wait_for_browser(self, timeout: float = 60.0) -> dict:
        browser_win_id = "win_browser_001"
        if browser_win_id not in self._windows:
            controls = [
                Control(
                    id="txt_email",
                    automation_id="email",
                    name="Email Address",
                    type="Edit",
                    value="",
                ),
                Control(
                    id="txt_password",
                    automation_id="passwd",
                    name="Password",
                    type="Edit",
                    value="",
                ),
                Control(
                    id="btn_signin",
                    automation_id="submit",
                    name="Sign In",
                    type="Button",
                    patterns=["InvokePattern"],
                ),
            ]
            app = Application(
                application_id="app_browser",
                process_id=9999,
                path="msedge.exe",
            )
            window = Window(
                window_id=browser_win_id,
                application_id=app.application_id,
                title="Sign in to your account - Microsoft Edge",
                active=True,
                controls=controls,
            )
            self._applications[app.application_id] = app
            self._windows[window.window_id] = window
            for c in controls:
                self._controls[c.id] = c

        return {"window_id": browser_win_id}

    def attach_browser_window(self, title_contains: str | None = None) -> dict:
        browser_win_id = "win_browser_001"
        self.wait_for_browser()
        if title_contains and title_contains.lower() not in self._windows[browser_win_id].title.lower():
            raise WindowNotFoundError(
                f"Browser window with title containing " f"'{title_contains}' not found"
            )
        return {"window_id": browser_win_id}

    def click_at(self, x: int, y: int, button: str = "left") -> dict:
        return {"x": x, "y": y, "button": button}
