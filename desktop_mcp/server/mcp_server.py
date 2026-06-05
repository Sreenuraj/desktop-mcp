from __future__ import annotations

from collections.abc import Callable
from typing import Any

from desktop_mcp.adapters.base import DesktopAdapter
from desktop_mcp.adapters.memory import InMemoryDesktopAdapter
from desktop_mcp.errors import DesktopMCPError, InvalidRequestError
from desktop_mcp.models.response import MCPResponse
from desktop_mcp.session.session_manager import SessionManager


class DesktopMCPServer:
    def __init__(
        self,
        adapter: DesktopAdapter | None = None,
        session_manager: SessionManager | None = None,
    ) -> None:
        if adapter is None:
            import os
            import sys

            adapter_type = os.environ.get("DESKTOP_MCP_ADAPTER")
            if adapter_type == "uia" or (
                adapter_type is None and sys.platform == "win32"
            ):
                from desktop_mcp.adapters.windows import WindowsUIAutomationAdapter

                adapter = WindowsUIAutomationAdapter()
            else:
                adapter = InMemoryDesktopAdapter()
        self.adapter = adapter
        self.sessions = session_manager or SessionManager()
        self._tools: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "create_session": self.create_session,
            "close_session": self.close_session,
            "launch_application": self.launch_application,
            "attach_application": self.attach_application,
            "close_application": self.close_application,
            "list_windows": self.list_windows,
            "activate_window": self.activate_window,
            "wait_for_window": self.wait_for_window,
            "close_window": self.close_window,
            "maximize_window": self.maximize_window,
            "minimize_window": self.minimize_window,
            "desktop_snapshot": self.desktop_snapshot,
            "window_snapshot": self.window_snapshot,
            "control_tree": self.control_tree,
            "find_control": self.find_control,
            "find_controls": self.find_controls,
            "get_control": self.get_control,
            "click": self.click,
            "double_click": self.double_click,
            "right_click": self.right_click,
            "hover": self.hover,
            "focus": self.focus,
            "drag_drop": self.drag_drop,
            "enter_text": self.enter_text,
            "append_text": self.append_text,
            "clear_text": self.clear_text,
            "read_text": self.read_text,
            "select_dropdown": self.select_dropdown,
            "select_tab": self.select_tab,
            "select_radio": self.select_radio,
            "check": self.check,
            "uncheck": self.uncheck,
            "read_table": self.read_table,
            "find_row": self.find_row,
            "select_row": self.select_row,
            "edit_cell": self.edit_cell,
            "read_cell": self.read_cell,
            "read_tree": self.read_tree,
            "expand_node": self.expand_node,
            "collapse_node": self.collapse_node,
            "select_node": self.select_node,
            "detect_dialog": self.detect_dialog,
            "wait_for_dialog": self.wait_for_dialog,
            "accept_dialog": self.accept_dialog,
            "dismiss_dialog": self.dismiss_dialog,
            "control_exists": self.control_exists,
            "wait_for_control": self.wait_for_control,
            "assert_text": self.assert_text,
            "assert_control_state": self.assert_control_state,
            "assert_table_row": self.assert_table_row,
            "capture_window": self.capture_window,
            "capture_desktop": self.capture_desktop,
            "start_recording": self.start_recording,
            "stop_recording": self.stop_recording,
            "wait_for_browser": self.wait_for_browser,
            "attach_browser_window": self.attach_browser_window,
            "generate_report": self.generate_report,
        }

    def call_tool(
        self, name: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        import time

        start_time = time.time()
        session_id = payload.get("session_id") if payload else None

        def log_action(
            sid: str | None,
            status: str,
            duration: float,
            error_info: dict | None = None,
            result_data: dict | None = None,
        ):
            if not sid:
                return
            try:
                session = self.sessions.get_session(sid)
                artifacts = []
                if result_data and "artifact" in result_data:
                    artifacts.append(result_data["artifact"])
                entry = {
                    "timestamp": time.time(),
                    "tool": name,
                    "input": payload.copy() if payload else {},
                    "status": status,
                    "duration": duration,
                    "error": error_info,
                    "artifacts": artifacts,
                }
                session.logs.append(entry)
            except Exception:
                pass

        try:
            if name not in self._tools:
                raise InvalidRequestError(f"Unknown tool: {name}")
            if name != "create_session":
                session = self.sessions.get_session(session_id)
                session_id = session.session_id
            data = self._tools[name](payload or {})
            if name == "create_session" and isinstance(data, dict):
                session_id = data.get("session_id")
            duration = time.time() - start_time
            log_action(session_id, "success", duration, result_data=data)
            return MCPResponse.ok(data).to_dict()
        except DesktopMCPError as exc:
            duration = time.time() - start_time
            err_info = {"code": exc.code, "message": exc.message}
            log_action(session_id, "error", duration, error_info=err_info)
            return MCPResponse.fail(exc.code, exc.message).to_dict()
        except Exception as exc:
            duration = time.time() - start_time
            err_info = {"code": "INTERNAL_ERROR", "message": str(exc)}
            log_action(session_id, "error", duration, error_info=err_info)
            return MCPResponse.fail("INTERNAL_ERROR", str(exc)).to_dict()

    @property
    def tools(self) -> list[str]:
        return sorted(self._tools)

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"session_id": self.sessions.create_session().session_id}

    def close_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.sessions.close_session(self._required(payload, "session_id"))
        return {}

    def launch_application(self, payload: dict[str, Any]) -> dict[str, Any]:
        app = self.adapter.launch_application(
            self._required(payload, "path"), payload.get("arguments", [])
        )
        self.sessions.register_application(
            app.application_id, payload.get("session_id")
        )
        for window in self.adapter.list_windows():
            if window.application_id == app.application_id:
                self.sessions.register_window(
                    window.window_id, payload.get("session_id")
                )
        return app.to_dict()

    def attach_application(self, payload: dict[str, Any]) -> dict[str, Any]:
        app = self.adapter.attach_application(
            int(self._required(payload, "process_id"))
        )
        self.sessions.register_application(
            app.application_id, payload.get("session_id")
        )
        return {"application_id": app.application_id}

    def close_application(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.adapter.close_application(self._required(payload, "application_id"))
        return {}

    def list_windows(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"windows": [window.to_dict() for window in self.adapter.list_windows()]}

    def activate_window(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.adapter.activate_window(self._required(payload, "window_id"))
        return {}

    def wait_for_window(self, payload: dict[str, Any]) -> dict[str, Any]:
        title_contains = str(self._required(payload, "title_contains")).lower()
        for window in self.adapter.list_windows():
            if title_contains in window.title.lower():
                return window.to_dict()
        raise InvalidRequestError(
            f"Window not found within timeout: {payload.get('title_contains')}"
        )

    def close_window(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.adapter.close_window(self._required(payload, "window_id"))
        return {}

    def maximize_window(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.adapter.resize_window(self._required(payload, "window_id"), "maximized")
        return {}

    def minimize_window(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.adapter.resize_window(self._required(payload, "window_id"), "minimized")
        return {}

    def desktop_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        windows = []
        for win in self.adapter.list_windows():
            data = win.to_dict(include_controls=False)
            data["controls"] = self._flatten_controls(win.controls)
            windows.append(data)
        return {"applications": [], "windows": windows}

    def window_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        window = self.adapter.get_window(self._required(payload, "window_id"))
        data = window.to_dict(include_controls=False)
        data["controls"] = self._flatten_controls(window.controls)
        return data

    def _flatten_controls(self, controls: list[Any]) -> list[dict[str, Any]]:
        flat = []

        def helper(ctrls: list[Any]) -> None:
            for c in ctrls:
                if hasattr(c, "to_dict"):
                    data = c.to_dict(include_children=False)
                    flat.append(data)
                    if hasattr(c, "children") and c.children:
                        helper(c.children)
                elif isinstance(c, dict):
                    data = c.copy()
                    children = data.pop("children", None)
                    flat.append(data)
                    if children:
                        helper(children)

        helper(controls)
        return flat

    def control_tree(self, payload: dict[str, Any]) -> dict[str, Any]:
        window = self.adapter.get_window(self._required(payload, "window_id"))
        return {
            "window_id": window.window_id,
            "tree": [
                control.to_dict(include_children=True) for control in window.controls
            ],
        }

    def find_control(self, payload: dict[str, Any]) -> dict[str, Any]:
        control = self.adapter.find_control(
            self._required(payload, "window_id"),
            payload.get("text"),
            payload.get("type"),
        )
        return {"control": control.to_dict()}

    def find_controls(self, payload: dict[str, Any]) -> dict[str, Any]:
        controls = self.adapter.find_controls(
            self._required(payload, "window_id"), payload.get("type")
        )
        return {"controls": [control.to_dict() for control in controls]}

    def get_control(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.adapter.get_control(self._required(payload, "control_id")).to_dict()

    def click(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction("click", payload)

    def double_click(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction("double_click", payload)

    def right_click(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction("right_click", payload)

    def hover(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction("hover", payload)

    def focus(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction("focus", payload)

    def drag_drop(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = self._required(payload, "source_control_id")
        target = self._required(payload, "target_control_id")
        return {
            "action": "drag_drop",
            "source_control_id": source,
            "target_control_id": target,
        }

    def enter_text(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction(
            "enter_text", payload, value=self._required(payload, "value")
        )

    def append_text(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction(
            "append_text", payload, value=self._required(payload, "value")
        )

    def clear_text(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction("clear_text", payload)

    def read_text(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "value": self.adapter.get_control(
                self._required(payload, "control_id")
            ).value
            or ""
        }

    def select_dropdown(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction(
            "select_dropdown", payload, value=self._required(payload, "value")
        )

    def select_tab(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction("select_tab", payload)

    def select_radio(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction("select_radio", payload)

    def check(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction("check", payload)

    def uncheck(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction("uncheck", payload)

    def read_table(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.adapter.read_table(self._required(payload, "control_id"))

    def find_row(self, payload: dict[str, Any]) -> dict[str, Any]:
        finder = getattr(self.adapter, "find_row")
        return finder(
            self._required(payload, "control_id"), self._required(payload, "criteria")
        )

    def select_row(self, payload: dict[str, Any]) -> dict[str, Any]:
        control_id = self._required(payload, "control_id")
        row_index = int(self._required(payload, "row_index"))
        return self.adapter.interact("select_row", control_id, row_index=row_index)

    def edit_cell(self, payload: dict[str, Any]) -> dict[str, Any]:
        control_id = self._required(payload, "control_id")
        row_index = int(self._required(payload, "row_index"))
        column = self._required(payload, "column")
        value = self._required(payload, "value")
        return self.adapter.interact(
            "edit_cell", control_id, row_index=row_index, column=column, value=value
        )

    def read_cell(self, payload: dict[str, Any]) -> dict[str, Any]:
        table = self.adapter.read_table(self._required(payload, "control_id"))
        row_index = int(self._required(payload, "row_index"))
        return {
            "value": table["rows"][row_index].get(self._required(payload, "column"))
        }

    def read_tree(self, payload: dict[str, Any]) -> dict[str, Any]:
        control = self.adapter.get_control(self._required(payload, "control_id"))
        return {"tree": control.to_dict(include_children=True)}

    def expand_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"node_path": self._required(payload, "node_path"), "expanded": True}

    def collapse_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"node_path": self._required(payload, "node_path"), "expanded": False}

    def select_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"node_path": self._required(payload, "node_path"), "selected": True}

    def detect_dialog(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"dialog": None}

    def wait_for_dialog(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"dialog": None}

    def accept_dialog(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"dialog_id": self._required(payload, "dialog_id"), "accepted": True}

    def dismiss_dialog(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"dialog_id": self._required(payload, "dialog_id"), "dismissed": True}

    def control_exists(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.adapter.get_control(self._required(payload, "control_id"))
        return {"exists": True}

    def wait_for_control(self, payload: dict[str, Any]) -> dict[str, Any]:
        window_id = self._required(payload, "window_id")
        text = payload.get("text")
        type_ = payload.get("type")
        timeout = float(payload.get("timeout", 10.0))

        import time

        start_time = time.perf_counter()
        while True:
            try:
                control = self.adapter.find_control(window_id, text, type_)
                return {"control": control.to_dict()}
            except DesktopMCPError:
                if time.perf_counter() - start_time >= timeout:
                    raise
                time.sleep(0.5)

    def _get_evidence_dir(self, session_id: str) -> str:
        import os

        evidence_base = os.environ.get("DESKTOP_MCP_EVIDENCE_DIR", "./evidence")
        return os.path.abspath(os.path.join(evidence_base, session_id))

    def generate_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = self._required(payload, "session_id")
        session = self.sessions.get_session(session_id)

        import datetime
        import os

        start_dt = datetime.datetime.fromtimestamp(
            session.start_time, datetime.timezone.utc
        )
        start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            f"# Session Execution Report - {session_id}",
            "",
            "## Session Metadata",
            f"- **Session ID**: {session_id}",
            f"- **Start Time**: {start_str}",
            f"- **Applications**: {', '.join(sorted(session.applications)) or 'None'}",
            f"- **Windows**: {', '.join(sorted(session.windows)) or 'None'}",
            "",
            "## Action Timeline",
            "",
            "| Timestamp | Tool | Status | Duration | Artifacts/Notes |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]

        for entry in session.logs:
            ts = datetime.datetime.fromtimestamp(
                entry["timestamp"], datetime.timezone.utc
            ).strftime("%H:%M:%S.%f")[:-3]
            tool = entry["tool"]
            status = entry["status"].upper()
            duration = f"{entry['duration']:.3f}s"

            notes = []
            if entry["error"]:
                notes.append(
                    f"Error: {entry['error']['code']} - {entry['error']['message']}"
                )
            if entry["artifacts"]:
                for art in entry["artifacts"]:
                    filename = os.path.basename(art)
                    notes.append(f"[{filename}](file://{art})")
            notes_str = "; ".join(notes) if notes else "-"

            lines.append(f"| {ts} | `{tool}` | {status} | {duration} | {notes_str} |")

        report_content = "\n".join(lines)

        ev_dir = self._get_evidence_dir(session_id)
        os.makedirs(ev_dir, exist_ok=True)
        report_path = os.path.abspath(os.path.join(ev_dir, "report.md"))

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        return {"session_id": session_id, "artifact": report_path}

    def assert_text(self, payload: dict[str, Any]) -> dict[str, Any]:
        control_id = self._required(payload, "control_id")
        expected = self._required(payload, "expected")
        session_id = payload.get("session_id")
        try:
            actual = self.adapter.get_control(control_id).value or ""
            if actual != expected:
                raise InvalidRequestError(f"Expected text {expected!r}, got {actual!r}")
            return {"passed": True, "expected": expected, "actual": actual}
        except Exception:
            self._capture_failure_evidence(control_id, session_id)
            raise

    def assert_control_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        control_id = self._required(payload, "control_id")
        session_id = payload.get("session_id")
        try:
            control = self.adapter.get_control(control_id)
            for field in ("enabled", "visible", "focused"):
                if field in payload and getattr(control, field) != payload[field]:
                    raise InvalidRequestError(
                        f"Expected {field}={payload[field]!r}, "
                        f"got {getattr(control, field)!r}"
                    )
            return {"passed": True}
        except Exception:
            self._capture_failure_evidence(control_id, session_id)
            raise

    def _capture_failure_evidence(
        self, control_id: str, session_id: str | None = None
    ) -> None:
        try:
            import os

            if session_id:
                import time

                ev_dir = self._get_evidence_dir(session_id)
                path = os.path.join(
                    ev_dir, f"failure_{control_id}_{int(time.time())}.png"
                )
                self.adapter.capture_desktop(path=path)
            else:
                self.adapter.capture_desktop()
        except Exception:
            pass

    def assert_table_row(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.find_row(payload)

    def capture_window(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = payload.get("session_id")
        window_id = self._required(payload, "window_id")
        if session_id:
            import time
            import os

            ev_dir = self._get_evidence_dir(session_id)
            path = os.path.join(ev_dir, f"window_{window_id}_{int(time.time())}.png")
            return self.adapter.capture_window(window_id, path=path)
        return self.adapter.capture_window(window_id)

    def capture_desktop(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = payload.get("session_id")
        if session_id:
            import time
            import os

            ev_dir = self._get_evidence_dir(session_id)
            path = os.path.join(ev_dir, f"desktop_{int(time.time())}.png")
            return self.adapter.capture_desktop(path=path)
        return self.adapter.capture_desktop()

    def start_recording(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = self._required(payload, "session_id")
        # Ensure session exists
        self.sessions.get_session(session_id)
        import os

        ev_dir = self._get_evidence_dir(session_id)
        gif_path = os.path.join(ev_dir, "recording.gif")

        recorder = getattr(self.adapter, "start_recording", None)
        if recorder:
            return recorder(path=gif_path)
        return {"recording": True}

    def stop_recording(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = self._required(payload, "session_id")
        # Ensure session exists
        self.sessions.get_session(session_id)

        recorder = getattr(self.adapter, "stop_recording", None)
        if recorder:
            return recorder()
        return {"recording": False}

    def wait_for_browser(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = payload.get("session_id")
        if session_id:
            self.sessions.get_session(session_id)

        timeout = float(payload.get("timeout", 60.0))
        return self.adapter.wait_for_browser(timeout=timeout)

    def attach_browser_window(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = payload.get("session_id")
        if session_id:
            self.sessions.get_session(session_id)

        title_contains = payload.get("title_contains")
        title_str = str(title_contains) if title_contains is not None else None
        return self.adapter.attach_browser_window(title_contains=title_str)

    def _interaction(
        self, action: str, payload: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        return self.adapter.interact(
            action, self._required(payload, "control_id"), **kwargs
        )

    def _required(self, payload: dict[str, Any], key: str) -> Any:
        value = payload.get(key)
        if value is None:
            raise InvalidRequestError(f"Missing required field: {key}")
        return value
