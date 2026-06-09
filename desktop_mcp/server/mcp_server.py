from __future__ import annotations

from collections.abc import Callable
from typing import Any

from desktop_mcp.adapters.base import DesktopAdapter
from desktop_mcp.adapters.memory import InMemoryDesktopAdapter
from desktop_mcp.errors import DesktopMCPError, InvalidRequestError, UnknownToolError
from desktop_mcp.logging import log_tool_call
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
            # Phase 1.3: desktop_snapshot restored as thin wrapper
            "desktop_snapshot": self.desktop_snapshot,
            "window_snapshot": self.window_snapshot,
            "control_tree": self.control_tree,
            "click": self.click,
            "click_at": self.click_at,
            "drag_drop": self.drag_drop,
            "enter_text": self.enter_text,
            "press_keys": self.press_keys,
            "read_text": self.read_text,
            "select_item": self.select_item,
            "read_table": self.read_table,
            "capture_window": self.capture_window,
            "capture_desktop": self.capture_desktop,
            "start_recording": self.start_recording,
            "stop_recording": self.stop_recording,
            "generate_report": self.generate_report,
            # Phase 4.1 — waiters
            "wait_for_control": self.wait_for_control,
            "wait_for_idle": self.wait_for_idle,
            # Phase 4.2 — richer control kinds
            "select_row": self.select_row,
            "click_cell": self.click_cell,
            "read_cell": self.read_cell,
            "read_tree": self.read_tree,
            # Phase 4.3 — dialog awareness
            "list_dialogs": self.list_dialogs,
            # Phase 4.4 — grounding tools
            "get_foreground_window": self.get_foreground_window,
            "get_focused_control": self.get_focused_control,
            "health_check": self.health_check,
            # Recorder ↔ MCP round-trip
            "replay_recording": self.replay_recording,
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
            # Phase 1.3: UNKNOWN_TOOL guard — structured error listing valid tools
            if name not in self._tools:
                raise UnknownToolError(
                    f"Unknown tool: '{name}'. Valid tools are: "
                    + ", ".join(sorted(self._tools)),
                    details={"requested_tool": name, "valid_tools": sorted(self._tools)},
                )
            if name != "create_session":
                session = self.sessions.get_session(session_id)
                session_id = session.session_id
            data = self._tools[name](payload or {})
            if name == "create_session" and isinstance(data, dict):
                session_id = data.get("session_id")
            duration = time.time() - start_time
            log_action(session_id, "success", duration, result_data=data)
            # Structured JSON log to stderr (mirrors session log).
            log_tool_call(
                tool=name,
                args=payload,
                took_ms=int(duration * 1000),
                result_kind="success",
                session_id=session_id,
            )
            return MCPResponse.ok(data).to_dict()
        except DesktopMCPError as exc:
            duration = time.time() - start_time
            err_info = {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
            log_action(session_id, "error", duration, error_info=err_info)
            log_tool_call(
                tool=name,
                args=payload,
                took_ms=int(duration * 1000),
                result_kind="error",
                error_code=exc.code,
                session_id=session_id,
            )
            # Phase 1.6: set isError=True on the MCP CallToolResult envelope
            return MCPResponse.fail(exc.code, exc.message, details=exc.details).to_dict()
        except Exception as exc:
            duration = time.time() - start_time
            err_info = {"code": "INTERNAL_ERROR", "message": str(exc), "details": {}}
            log_action(session_id, "error", duration, error_info=err_info)
            log_tool_call(
                tool=name,
                args=payload,
                took_ms=int(duration * 1000),
                result_kind="error",
                error_code="INTERNAL_ERROR",
                session_id=session_id,
            )
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
        """Phase 1.2: returns observable foreground state instead of empty {}."""
        result = self.adapter.activate_window(self._required(payload, "window_id"))
        # The memory adapter returns None (old contract); normalise gracefully.
        if result is None:
            return {"window_id": payload.get("window_id"), "is_foreground": None}
        return result

    # ------------------------------------------------------------------
    # Phase 1.4 — wait_for_window: proper polling loop
    # ------------------------------------------------------------------

    def wait_for_window(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Poll until a window whose title contains *title_contains* appears.

        Parameters
        ----------
        title_contains : str
            Case-insensitive substring to match against window titles.
        timeout_ms : int, optional
            Maximum time to wait in milliseconds (default 10 000).

        Returns the matching window dict on success, or raises
        ``WindowNotFoundError`` on timeout.
        """
        import time

        from desktop_mcp.errors import WindowNotFoundError

        title_contains = str(self._required(payload, "title_contains")).lower()
        timeout_ms = int(payload.get("timeout_ms", 10_000))
        poll_interval = 0.25  # seconds

        deadline = time.perf_counter() + timeout_ms / 1000.0
        while True:
            for window in self.adapter.list_windows():
                if title_contains in window.title.lower():
                    return window.to_dict()

            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                break
            time.sleep(min(poll_interval, remaining))

        raise WindowNotFoundError(
            f"Window with title containing '{payload.get('title_contains')}' "
            f"not found within {timeout_ms} ms"
        )

    def close_window(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.adapter.close_window(self._required(payload, "window_id"))
        return {}

    # ------------------------------------------------------------------
    # Phase 1.3: desktop_snapshot — thin wrapper over list_windows +
    # per-window shallow snapshot
    # ------------------------------------------------------------------

    def desktop_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return a lightweight snapshot of all visible windows.

        Each entry includes the window metadata plus a shallow control list
        (top-level controls only, no deep recursion).  This is the same
        information the agent used to get from the now-removed
        ``desktop_snapshot`` tool, restored for backward compatibility.
        """
        windows_out = []
        for window in self.adapter.list_windows():
            entry = window.to_dict(include_controls=False)
            # Best-effort shallow snapshot — skip windows that error
            try:
                win_detail = self.adapter.get_window(window.window_id)
                entry["controls"] = self._flatten_controls(win_detail.controls)
                entry["controls_count"] = len(entry["controls"])
                # Include snapshot metadata if the adapter attached it
                meta = getattr(win_detail, "_snapshot_meta", None)
                if meta:
                    entry.update(meta)
            except Exception as exc:
                entry["controls"] = []
                entry["controls_count"] = 0
                entry["snapshot_error"] = str(exc)
            windows_out.append(entry)
        return {"windows": windows_out, "windows_count": len(windows_out)}

    # ------------------------------------------------------------------
    # Phase 1.2: window_snapshot — enriched with metadata
    # ------------------------------------------------------------------

    def window_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        window = self.adapter.get_window(self._required(payload, "window_id"))
        data = window.to_dict(include_controls=False)
        flat_controls = self._flatten_controls(window.controls)
        data["controls"] = flat_controls
        data["controls_count"] = len(flat_controls)

        # Merge snapshot metadata attached by the UIA adapter (Phase 1.2)
        meta = getattr(window, "_snapshot_meta", None)
        if meta:
            data.setdefault("capture_method", meta.get("capture_method", "uia_children"))
            data.setdefault("uia_state", meta.get("uia_state", "live"))
            data.setdefault("took_ms", meta.get("took_ms"))
        else:
            # Memory adapter / other adapters — provide sensible defaults
            data.setdefault("capture_method", "in_memory")
            data.setdefault("uia_state", "live")

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

    # ------------------------------------------------------------------
    # Phase 1.2: control_tree — enriched with node count and timing
    # ------------------------------------------------------------------

    def control_tree(self, payload: dict[str, Any]) -> dict[str, Any]:
        import time

        t0 = time.perf_counter()
        window = self.adapter.get_window(self._required(payload, "window_id"))
        tree = [control.to_dict(include_children=True) for control in window.controls]
        took_ms = int((time.perf_counter() - t0) * 1000)

        def count_nodes(nodes: list[dict]) -> int:
            total = 0
            for node in nodes:
                total += 1
                total += count_nodes(node.get("children", []))
            return total

        return {
            "window_id": window.window_id,
            "tree": tree,
            "tree_node_count": count_nodes(tree),
            "took_ms": took_ms,
        }

    def click(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action", "left"))
        return self._interaction(action, payload)

    def press_keys(self, payload: dict[str, Any]) -> dict[str, Any]:
        keys = self._required(payload, "keys")
        control_id = payload.get("control_id")
        if control_id:
            return self.adapter.interact("press_keys", control_id, keys=keys)
        else:
            return self.adapter.interact("press_keys", "", keys=keys)

    def select_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction(
            "select_item", payload, value=self._required(payload, "value")
        )

    def drag_drop(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Drag a control onto another control.

        Implemented as: hover source → press_mouse → move to target → release.
        Requires foreground on the source window because it uses synthesised
        mouse input.  Falls back to a ``NotImplementedError`` if the adapter
        does not expose ``drag_drop`` or ``click_at``.
        """
        source = self._required(payload, "source_control_id")
        target = self._required(payload, "target_control_id")

        # Adapter-native implementation if available
        drag = getattr(self.adapter, "drag_drop", None)
        if callable(drag):
            return drag(source, target)

        # Fallback: compute centre points and synthesise mouse drag
        try:
            src_ctrl = self.adapter.get_control(source)
            tgt_ctrl = self.adapter.get_control(target)
            sb = src_ctrl.bounds or {}
            tb = tgt_ctrl.bounds or {}
            if not (sb and tb):
                raise DesktopMCPError(
                    "drag_drop: control bounds unavailable",
                    details={"source": source, "target": target},
                )
            sx = int(sb.get("x", sb.get("left", 0))) + int(sb.get("width", 0)) // 2
            sy = int(sb.get("y", sb.get("top", 0))) + int(sb.get("height", 0)) // 2
            tx = int(tb.get("x", tb.get("left", 0))) + int(tb.get("width", 0)) // 2
            ty = int(tb.get("y", tb.get("top", 0))) + int(tb.get("height", 0)) // 2

            # pywinauto mouse drag — only available on the UIA adapter
            import importlib
            try:
                pwa_mouse = importlib.import_module("pywinauto.mouse")
                pwa_mouse.press(coords=(sx, sy))
                pwa_mouse.move(coords=(tx, ty))
                pwa_mouse.release(coords=(tx, ty))
                return {
                    "action": "drag_drop",
                    "source_control_id": source,
                    "target_control_id": target,
                    "source_xy": [sx, sy],
                    "target_xy": [tx, ty],
                    "method": "pywinauto_mouse_drag",
                }
            except ImportError:
                # In-memory adapter / non-Windows: report as a stub
                return {
                    "action": "drag_drop",
                    "source_control_id": source,
                    "target_control_id": target,
                    "source_xy": [sx, sy],
                    "target_xy": [tx, ty],
                    "method": "stub",
                }
        except DesktopMCPError:
            raise
        except Exception as exc:
            raise DesktopMCPError(
                f"drag_drop failed: {exc}",
                details={"source": source, "target": target},
            ) from exc

    def click_at(self, payload: dict[str, Any]) -> dict[str, Any]:
        x = int(self._required(payload, "x"))
        y = int(self._required(payload, "y"))
        button = str(payload.get("button", "left"))
        return self.adapter.click_at(x, y, button)

    def enter_text(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction(
            "enter_text", payload, value=self._required(payload, "value")
        )

    def read_text(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "value": (
                self.adapter.get_control(
                    self._required(payload, "control_id")
                ).value
                or ""
            )
        }

    def read_table(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.adapter.read_table(self._required(payload, "control_id"))

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

    def _capture_failure_evidence(
        self, control_id: str, session_id: str | None = None
    ) -> None:
        try:
            import os

            highlight_rect = None
            try:
                control = self.adapter.get_control(control_id)
                if control.bounds:
                    b = control.bounds
                    highlight_rect = (
                        b["left"],
                        b["top"],
                        b["left"] + b["width"],
                        b["top"] + b["height"],
                    )
            except Exception:
                pass

            if session_id:
                import time

                ev_dir = self._get_evidence_dir(session_id)
                path = os.path.join(
                    ev_dir, f"failure_{control_id}_{int(time.time())}.png"
                )
                self.adapter.capture_desktop(path=path, highlight_rect=highlight_rect)
            else:
                self.adapter.capture_desktop(highlight_rect=highlight_rect)
        except Exception:
            pass

    def capture_window(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = payload.get("session_id")
        window_id = self._required(payload, "window_id")
        highlight_rect = payload.get("highlight_rect")
        if isinstance(highlight_rect, list) and len(highlight_rect) == 4:
            highlight_rect = tuple(highlight_rect)
        else:
            highlight_rect = None

        if session_id:
            import time
            import os

            ev_dir = self._get_evidence_dir(session_id)
            path = os.path.join(ev_dir, f"window_{window_id}_{int(time.time())}.png")
            return self.adapter.capture_window(
                window_id, path=path, highlight_rect=highlight_rect
            )
        return self.adapter.capture_window(window_id, highlight_rect=highlight_rect)

    def capture_desktop(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = payload.get("session_id")
        highlight_rect = payload.get("highlight_rect")
        if isinstance(highlight_rect, list) and len(highlight_rect) == 4:
            highlight_rect = tuple(highlight_rect)
        else:
            highlight_rect = None

        if session_id:
            import time
            import os

            ev_dir = self._get_evidence_dir(session_id)
            path = os.path.join(ev_dir, f"desktop_{int(time.time())}.png")
            return self.adapter.capture_desktop(path=path, highlight_rect=highlight_rect)
        return self.adapter.capture_desktop(highlight_rect=highlight_rect)

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

    # ------------------------------------------------------------------
    # Phase 4.1 — wait_for_control
    # ------------------------------------------------------------------

    def wait_for_control(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Poll until a control matching the criteria appears in a window.

        At least one of name, automation_id, or control_type must be provided.
        """
        window_id = self._required(payload, "window_id")
        name = payload.get("name")
        automation_id = payload.get("automation_id")
        control_type = payload.get("control_type")
        state = str(payload.get("state", "exists"))
        timeout_ms = int(payload.get("timeout_ms", 10_000))

        if not any([name, automation_id, control_type]):
            from desktop_mcp.errors import InvalidRequestError
            raise InvalidRequestError(
                "wait_for_control requires at least one of: name, automation_id, control_type"
            )

        return self.adapter.wait_for_control(
            window_id=window_id,
            name=name,
            automation_id=automation_id,
            control_type=control_type,
            state=state,
            timeout_ms=timeout_ms,
        )

    # ------------------------------------------------------------------
    # Phase 4.1 — wait_for_idle
    # ------------------------------------------------------------------

    def wait_for_idle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Wait until the window's UI tree stops changing."""
        window_id = self._required(payload, "window_id")
        idle_ms = int(payload.get("idle_ms", 500))
        timeout_ms = int(payload.get("timeout_ms", 10_000))
        return self.adapter.wait_for_idle(
            window_id=window_id,
            idle_ms=idle_ms,
            timeout_ms=timeout_ms,
        )

    # ------------------------------------------------------------------
    # Phase 4.2 — select_row, click_cell, read_cell, read_tree
    # ------------------------------------------------------------------

    def select_row(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Select a row in a DataGrid/ListView by text or index."""
        control_id = self._required(payload, "control_id")
        by_text = payload.get("by_text")
        by_index = payload.get("by_index")
        if by_index is not None:
            by_index = int(by_index)
        if by_text is None and by_index is None:
            from desktop_mcp.errors import InvalidRequestError
            raise InvalidRequestError(
                "select_row requires either by_text or by_index"
            )
        return self.adapter.select_row(
            control_id=control_id,
            by_text=by_text,
            by_index=by_index,
        )

    def click_cell(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Click a specific cell in a DataGrid by row and column index."""
        return self.adapter.click_cell(
            control_id=self._required(payload, "control_id"),
            row=int(self._required(payload, "row")),
            column=int(self._required(payload, "column")),
        )

    def read_cell(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Read the value of a specific cell in a DataGrid."""
        return self.adapter.read_cell(
            control_id=self._required(payload, "control_id"),
            row=int(self._required(payload, "row")),
            column=int(self._required(payload, "column")),
        )

    def read_tree(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Read a TreeView control as a nested structure."""
        return self.adapter.read_tree(
            control_id=self._required(payload, "control_id"),
            max_depth=int(payload.get("max_depth", 4)),
        )

    # ------------------------------------------------------------------
    # Phase 4.3 — list_dialogs
    # ------------------------------------------------------------------

    def list_dialogs(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return modal/popup windows owned by an application."""
        application_id = self._required(payload, "application_id")
        dialogs = self.adapter.list_dialogs(application_id)
        return {"dialogs": dialogs, "count": len(dialogs)}

    # ------------------------------------------------------------------
    # Phase 4.4 — grounding tools
    # ------------------------------------------------------------------

    def get_foreground_window(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the window_id and title of the current foreground window."""
        return self.adapter.get_foreground_window()

    def get_focused_control(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the control that currently has keyboard focus."""
        return self.adapter.get_focused_control(
            self._required(payload, "window_id")
        )

    def health_check(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return diagnostic information about the MCP server environment."""
        return self.adapter.health_check()

    # ------------------------------------------------------------------
    # replay_recording
    # ------------------------------------------------------------------

    def replay_recording(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Replay a recording produced by the action recorder.

        Accepts a JSON file in the schema documented in
        ``docs/recording_schema.md``. Each step in the recording becomes a
        single ``call_tool`` invocation against this same server instance,
        so the resulting evidence/logs are indistinguishable from a real
        agent-driven session.

        Parameters
        ----------
        path : str
            Absolute path to the recording JSON file.
        session_id : str
            Session to attribute the replay to.
        stop_on_error : bool, optional (default: True)
            If True (default), the first failing step aborts the replay.
            If False, all steps are attempted and the report lists the
            failed ones.

        Returns
        -------
        dict with:
          - ``steps_total``        — number of steps in the file
          - ``steps_executed``     — number actually run
          - ``steps_succeeded``    — count of successful steps
          - ``steps_failed``       — count of failed steps
          - ``results``            — list of {step, tool, success, error?}
          - ``aborted``            — True if stop_on_error halted the run
        """
        import json
        import os

        session_id = self._required(payload, "session_id")
        # Validate session exists up-front so we fail fast with a clear error.
        self.sessions.get_session(session_id)

        path = str(self._required(payload, "path"))
        stop_on_error = bool(payload.get("stop_on_error", True))

        if not os.path.isfile(path):
            raise InvalidRequestError(
                f"Recording file not found: {path}",
                details={"path": path},
            )

        try:
            with open(path, encoding="utf-8") as f:
                recording = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise DesktopMCPError(
                f"Failed to load recording {path}: {exc}",
                details={"path": path},
            ) from exc

        # Accept either {"steps": [...]} or a raw list of steps. Anything
        # else is a schema error; bail with a useful message.
        if isinstance(recording, dict):
            steps = recording.get("steps")
            if steps is None:
                raise InvalidRequestError(
                    "Recording JSON is missing top-level 'steps' field. "
                    "See docs/recording_schema.md.",
                    details={"path": path, "keys": list(recording.keys())},
                )
        elif isinstance(recording, list):
            steps = recording
        else:
            raise InvalidRequestError(
                "Recording JSON must be an object with 'steps' or a list of steps.",
                details={"path": path, "type": type(recording).__name__},
            )

        if not isinstance(steps, list):
            raise InvalidRequestError(
                "Recording 'steps' must be a list.",
                details={"path": path, "type": type(steps).__name__},
            )

        results: list[dict[str, Any]] = []
        steps_succeeded = 0
        steps_failed = 0
        aborted = False

        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                # Treat malformed step as a failure so the report stays
                # honest, but don't crash the whole replay.
                results.append({
                    "step": index,
                    "tool": None,
                    "success": False,
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": f"Step {index} is not an object",
                    },
                })
                steps_failed += 1
                if stop_on_error:
                    aborted = True
                    break
                continue

            tool = step.get("tool")
            args = dict(step.get("arguments") or step.get("args") or {})
            if not tool:
                results.append({
                    "step": index,
                    "tool": None,
                    "success": False,
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": f"Step {index} is missing 'tool' field",
                    },
                })
                steps_failed += 1
                if stop_on_error:
                    aborted = True
                    break
                continue

            # Inject session_id if the step omitted it (the typical case).
            args.setdefault("session_id", session_id)

            # Route back through call_tool so logging, evidence capture, and
            # the standard MCP envelope all flow exactly as they would for
            # a live agent. This is the whole point of the round-trip.
            envelope = self.call_tool(tool, args)
            success = bool(envelope.get("success"))
            entry: dict[str, Any] = {
                "step": index,
                "tool": tool,
                "success": success,
            }
            if not success:
                entry["error"] = envelope.get("error")
                steps_failed += 1
                if stop_on_error:
                    results.append(entry)
                    aborted = True
                    break
            else:
                steps_succeeded += 1
            results.append(entry)

        return {
            "path": os.path.abspath(path),
            "session_id": session_id,
            "steps_total": len(steps),
            "steps_executed": len(results),
            "steps_succeeded": steps_succeeded,
            "steps_failed": steps_failed,
            "aborted": aborted,
            "results": results,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _interaction(
        self, action: str, payload: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        # window_id is optional when control_id is provided, but we still
        # forward it to the adapter as a resolution hint so it does not
        # have to scan every top-level window on the desktop.
        window_id = payload.get("window_id")
        control_id = payload.get("control_id")
        if not control_id:
            # Need a window to locate the control by text/type
            window_id = self._required(payload, "window_id")
            text = payload.get("control_text")
            type_ = payload.get("control_type")
            control = self.adapter.find_control(window_id, text=text, type=type_)
            control_id = control.id

        # Phase 2.4: pass restore_foreground_after_action to the adapter
        restore_fg = bool(payload.get("restore_foreground_after_action", True))
        # Adapters that don't accept ``window_id`` (the in-memory one) will
        # raise TypeError; fall back to the legacy signature in that case.
        try:
            return self.adapter.interact(
                action,
                control_id,
                restore_foreground=restore_fg,
                window_id=window_id,
                **kwargs,
            )
        except TypeError:
            return self.adapter.interact(
                action, control_id, restore_foreground=restore_fg, **kwargs
            )

    def _required(self, payload: dict[str, Any], key: str) -> Any:
        value = payload.get(key)
        if value is None:
            raise InvalidRequestError(f"Missing required field: {key}")
        return value
