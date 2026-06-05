from __future__ import annotations

from itertools import count
from typing import Any

from desktop_mcp.errors import AppNotFoundError, ControlDisabledError, ControlNotFoundError, WindowNotFoundError
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
        self.seed()

    def seed(self) -> None:
        app = Application(application_id="app_demo", process_id=1000, path="demo.exe")
        controls = [
            Control(id="btn_save", automation_id="btnSave", name="Save", type="Button", patterns=["InvokePattern"]),
            Control(id="txt_customer", automation_id="txtCustomer", name="Customer", type="Edit", value=""),
            Control(id="ddl_state", automation_id="ddlState", name="State", type="ComboBox", value=""),
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
        window = Window(window_id="win_demo", application_id=app.application_id, title="Customer Management", active=True, controls=controls)
        self._applications[app.application_id] = app
        self._windows[window.window_id] = window
        for control in controls:
            self._controls[control.id] = control

    def launch_application(self, path: str, arguments: list[str] | None = None) -> Application:
        application_id = f"app_{next(self._app_counter):03d}"
        window_id = f"win_{next(self._window_counter):03d}"
        app = Application(application_id=application_id, process_id=2000 + len(self._applications), path=path)
        window = Window(window_id=window_id, application_id=application_id, title=path.rsplit("\\", 1)[-1] or path, active=True)
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
        stale_windows = [window_id for window_id, window in self._windows.items() if window.application_id == application_id]
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

    def find_control(self, window_id: str, text: str | None = None, type: str | None = None) -> Control:
        matches = self.find_controls(window_id, type=type)
        if text is not None:
            matches = [control for control in matches if text.lower() in control.name.lower()]
        if not matches:
            raise ControlNotFoundError("Control could not be located")
        return matches[0]

    def find_controls(self, window_id: str, type: str | None = None) -> list[Control]:
        window = self.get_window(window_id)
        if type is None:
            return list(window.controls)
        return [control for control in window.controls if control.type.lower() == type.lower()]

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
            control.value = value if action == "enter_text" else f"{control.value or ''}{value}"
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

    def capture_window(self, window_id: str) -> dict:
        window = self.get_window(window_id)
        return {"window_id": window.window_id, "artifact": f"memory://screenshots/{window.window_id}.png"}

    def capture_desktop(self) -> dict:
        return {"artifact": "memory://screenshots/desktop.png"}

    def start_recording(self) -> dict:
        self._recording = True
        return {"recording": True}

    def stop_recording(self) -> dict:
        self._recording = False
        return {"recording": False, "artifact": "memory://recordings/session.mp4"}
