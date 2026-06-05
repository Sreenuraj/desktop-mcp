from __future__ import annotations

import os
import sys
from typing import Any

from desktop_mcp.errors import (
    AppNotFoundError,
    ControlDisabledError,
    ControlNotFoundError,
    DesktopMCPError,
    UnsupportedControlError,
    WindowNotFoundError,
)
from desktop_mcp.models.application import Application
from desktop_mcp.models.control import Control
from desktop_mcp.models.window import Window

# Try to import Windows dependencies, otherwise define them as None to allow
# testing/linting on macOS
psutil: Any = None
win32con: Any = None
win32gui: Any = None
ImageGrab: Any = None
PyWinApplication: Any = None
PyWinDesktop: Any = None

try:
    if sys.platform == "win32":
        import psutil as psutil_mod

        psutil = psutil_mod
        import win32con as win32con_mod

        win32con = win32con_mod
        import win32gui as win32gui_mod

        win32gui = win32gui_mod
        from PIL import ImageGrab as ImageGrab_mod

        ImageGrab = ImageGrab_mod
        from pywinauto import Application as PyWinApplication_mod

        PyWinApplication = PyWinApplication_mod
        from pywinauto import Desktop as PyWinDesktop_mod

        PyWinDesktop = PyWinDesktop_mod
except ImportError:
    pass

# A map of UIA control types to standard, agent-friendly Desktop MCP control types
UIA_CONTROL_TYPE_MAP = {
    "Button": "Button",
    "Calendar": "Calendar",
    "CheckBox": "CheckBox",
    "ComboBox": "ComboBox",
    "Custom": "Custom",
    "DataGrid": "DataGrid",
    "DataItem": "DataItem",
    "Document": "Document",
    "Edit": "Edit",
    "Group": "Group",
    "Header": "Header",
    "HeaderItem": "HeaderItem",
    "Hyperlink": "Hyperlink",
    "Image": "Image",
    "List": "ListBox",
    "ListItem": "ListItem",
    "Menu": "Menu",
    "MenuBar": "MenuBar",
    "MenuItem": "MenuItem",
    "Pane": "Pane",
    "ProgressBar": "ProgressBar",
    "RadioButton": "RadioButton",
    "ScrollBar": "ScrollBar",
    "SemanticKey": "Key",
    "Separator": "Separator",
    "Slider": "Slider",
    "Spinner": "Spinner",
    "SplitButton": "SplitButton",
    "StatusBar": "StatusBar",
    "Tab": "TabControl",
    "TabItem": "TabItem",
    "Table": "Table",
    "Text": "Text",
    "Thumb": "Thumb",
    "TitleBar": "TitleBar",
    "ToolBar": "ToolBar",
    "ToolTip": "ToolTip",
    "Tree": "TreeView",
    "TreeItem": "TreeViewItem",
    "Window": "Window",
}


class WindowsUIAutomationAdapter:
    """Windows UI Automation adapter using pywinauto and comtypes.

    Exposes the public DesktopAdapter protocol while encapsulating
    Windows-specific automation APIs.
    """

    def __init__(self) -> None:
        self._apps: dict[str, Any] = {}
        self._controls_cache: dict[str, Any] = {}
        import threading

        self._recording_thread: threading.Thread | None = None
        self._stop_recording_event = threading.Event()
        self._recording_frames: list[Any] = []
        self._recording_path: str | None = None

    def _check_platform(self) -> None:
        if sys.platform != "win32":
            raise DesktopMCPError(
                "Windows UI Automation adapter is only supported on Windows"
            )
        if PyWinApplication is None:
            raise DesktopMCPError(
                "Required Windows libraries (pywinauto, pywin32, psutil, Pillow) "
                "are not installed"
            )

    def launch_application(
        self, path: str, arguments: list[str] | None = None
    ) -> Application:
        self._check_platform()
        args_str = " ".join(arguments) if arguments else ""
        cmd_line = f'"{path}" {args_str}'.strip()
        try:
            app = PyWinApplication(backend="uia").start(cmd_line)
            process_id = app.process
            application_id = f"app_{process_id}"
            self._apps[application_id] = app
            return Application(
                application_id=application_id, process_id=process_id, path=path
            )
        except Exception as exc:
            raise DesktopMCPError(
                f"Failed to launch application {path}: {exc}"
            ) from exc

    def attach_application(self, process_id: int) -> Application:
        self._check_platform()
        try:
            app = PyWinApplication(backend="uia").connect(process=process_id)
            application_id = f"app_{process_id}"
            self._apps[application_id] = app
            return Application(application_id=application_id, process_id=process_id)
        except Exception as exc:
            raise AppNotFoundError(
                f"Failed to attach to process {process_id}: {exc}"
            ) from exc

    def close_application(self, application_id: str) -> None:
        self._check_platform()
        try:
            pid = (
                int(application_id.split("_")[1])
                if "_" in application_id
                else int(application_id)
            )
        except (ValueError, IndexError) as exc:
            raise AppNotFoundError(f"Invalid application ID: {application_id}") from exc

        self._apps.pop(application_id, None)

        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
        except psutil.NoSuchProcess:
            pass
        except Exception as exc:
            raise DesktopMCPError(
                f"Failed to close application {application_id}: {exc}"
            ) from exc

    def list_windows(self) -> list[Window]:
        self._check_platform()
        windows = []
        try:
            desktop = PyWinDesktop(backend="uia")
            for win in desktop.windows():
                try:
                    handle = win.handle
                    title = win.window_text() or ""
                    if not title:
                        continue
                    process_id = win.process_id()
                    application_id = f"app_{process_id}"
                    active = win32gui.GetForegroundWindow() == handle
                    window_id = f"win_{handle}"
                    windows.append(
                        Window(
                            window_id=window_id,
                            title=title,
                            application_id=application_id,
                            active=active,
                        )
                    )
                except Exception:
                    continue
        except Exception as exc:
            raise DesktopMCPError(f"Failed to list windows: {exc}") from exc
        return windows

    def activate_window(self, window_id: str) -> None:
        self._check_platform()
        try:
            win = self._resolve_window(window_id)
            win.set_focus()
        except WindowNotFoundError:
            raise
        except Exception as exc:
            raise DesktopMCPError(
                f"Failed to activate window {window_id}: {exc}"
            ) from exc

    def close_window(self, window_id: str) -> None:
        self._check_platform()
        try:
            win = self._resolve_window(window_id)
            win.close()
        except WindowNotFoundError:
            raise
        except Exception as exc:
            raise DesktopMCPError(f"Failed to close window {window_id}: {exc}") from exc

    def resize_window(self, window_id: str, state: str) -> None:
        self._check_platform()
        try:
            win = self._resolve_window(window_id)
            if state == "maximized":
                win.maximize()
            elif state == "minimized":
                win.minimize()
            else:
                win.restore()
        except WindowNotFoundError:
            raise
        except Exception as exc:
            raise DesktopMCPError(
                f"Failed to resize window {window_id}: {exc}"
            ) from exc

    def get_window(self, window_id: str) -> Window:
        self._check_platform()
        try:
            win_wrapper = self._resolve_window(window_id)
            handle = win_wrapper.handle
            title = win_wrapper.window_text() or ""
            process_id = win_wrapper.process_id()
            application_id = f"app_{process_id}"
            active = win32gui.GetForegroundWindow() == handle

            # Recursively build hierarchical controls starting from immediate children
            controls = []
            try:
                for child in win_wrapper.children():
                    controls.extend(self._build_control_tree(child))
            except Exception:
                # Robust fallback: extract a flat list of descendants
                for desc in win_wrapper.descendants():
                    try:
                        if self._should_include_control(desc):
                            controls.append(self._map_control(desc))
                    except Exception:
                        continue

            return Window(
                window_id=window_id,
                title=title,
                application_id=application_id,
                active=active,
                controls=controls,
            )
        except WindowNotFoundError:
            raise
        except Exception as exc:
            raise DesktopMCPError(f"Failed to get window {window_id}: {exc}") from exc

    def _should_include_control(self, element: Any) -> bool:
        """Filter out layout/formatting elements to keep tree snapshots AI-friendly."""
        try:
            info = element.element_info
            ctrl_type = info.control_type or ""

            # Interactive elements should always be included
            if ctrl_type in (
                "Button",
                "CheckBox",
                "ComboBox",
                "Edit",
                "RadioButton",
                "Hyperlink",
                "MenuItem",
                "TabItem",
                "TreeViewItem",
            ):
                return True

            # Items with custom names or automation IDs are semantically useful
            if info.name or info.automation_id:
                return True

            # If it's a grid, table, list box, tree view, or tab control, include it
            if ctrl_type in ("Table", "DataGrid", "List", "Tree", "Tab"):
                return True

            # Filter out structural layout panes/groups with no semantic identifiers
            if ctrl_type in ("Pane", "Group", "Custom", "Separator"):
                return False

            return True
        except Exception:
            return True

    def _build_control_tree(
        self, element: Any, current_depth: int = 0, max_depth: int = 8
    ) -> list[Control]:
        """Recursively traverse the UIA element hierarchy.

        Filters out non-essential containers, lifting their semantic
        children up to keep tree shallow.
        """
        if current_depth > max_depth:
            return []

        try:
            if not element.is_visible():
                return []
        except Exception:
            pass

        include = self._should_include_control(element)

        child_controls = []
        try:
            for child in element.children():
                child_controls.extend(
                    self._build_control_tree(child, current_depth + 1, max_depth)
                )
        except Exception:
            pass

        if include:
            control = self._map_control(element)
            control.children = child_controls
            return [control]
        else:
            return child_controls

    def find_control(
        self, window_id: str, text: str | None = None, type: str | None = None
    ) -> Control:
        self._check_platform()
        controls = self.find_controls(window_id, type)
        if text is not None:
            controls = [c for c in controls if text.lower() in c.name.lower()]
        if not controls:
            raise ControlNotFoundError("Control could not be located")
        return controls[0]

    def find_controls(self, window_id: str, type: str | None = None) -> list[Control]:
        self._check_platform()
        # Flatten the control tree to allow searching
        window = self.get_window(window_id)
        flat_controls = []

        def flatten(ctrls: list[Control]) -> None:
            for c in ctrls:
                flat_controls.append(c)
                flatten(c.children)

        flatten(window.controls)

        if type is None:
            return flat_controls
        return [c for c in flat_controls if c.type.lower() == type.lower()]

    def get_control(self, control_id: str) -> Control:
        self._check_platform()
        el = self._resolve_control(control_id)
        return self._map_control(el)

    def interact(self, action: str, control_id: str, **kwargs: Any) -> dict:
        self._check_platform()
        el = self._resolve_control(control_id)
        if not el.is_enabled():
            raise ControlDisabledError(f"Control is disabled: {control_id}")

        try:
            if action == "click":
                if hasattr(el, "invoke") and el.element_info.control_type == "Button":
                    try:
                        el.invoke()
                    except Exception:
                        el.click_input()
                else:
                    el.click_input()
            elif action == "double_click":
                if hasattr(el, "double_click_input"):
                    el.double_click_input()
                else:
                    el.click_input()
                    el.click_input()
            elif action == "right_click":
                el.right_click_input()
            elif action == "hover":
                el.move_mouse_input()
            elif action == "focus":
                el.set_focus()
            elif action == "enter_text":
                val = kwargs.get("value", "")
                if hasattr(el, "set_edit_text"):
                    el.set_edit_text(val)
                else:
                    el.type_keys(val, with_spaces=True, with_tabs=True)
            elif action == "append_text":
                val = kwargs.get("value", "")
                existing = ""
                try:
                    if hasattr(el, "get_value"):
                        existing = el.get_value() or ""
                    else:
                        existing = el.window_text() or ""
                except Exception:
                    pass
                if hasattr(el, "set_edit_text"):
                    el.set_edit_text(existing + val)
                else:
                    el.type_keys(val, with_spaces=True, with_tabs=True)
            elif action == "clear_text":
                if hasattr(el, "set_edit_text"):
                    el.set_edit_text("")
                else:
                    el.type_keys("^a{BACKSPACE}")
            elif action in ("select_dropdown", "select_tab", "select_radio", "check"):
                val = str(kwargs.get("value", "true"))
                if action == "check" and hasattr(el, "check"):
                    el.check()
                elif hasattr(el, "select"):
                    el.select(val)
                else:
                    el.click_input()
            elif action == "uncheck":
                if hasattr(el, "uncheck"):
                    el.uncheck()
                else:
                    el.click_input()
            elif action == "select_row":
                row_index = int(kwargs.get("row_index", 0))
                data_rows = [
                    d
                    for d in el.descendants()
                    if d.element_info.control_type in ("DataItem", "Row")
                ]
                if row_index < len(data_rows):
                    row_el = data_rows[row_index]
                    if hasattr(row_el, "select"):
                        row_el.select()
                    else:
                        row_el.click_input()
                else:
                    raise ControlNotFoundError(
                        f"Row index {row_index} out of range for grid {control_id}"
                    )
            elif action == "edit_cell":
                row_index = int(kwargs.get("row_index", 0))
                column = str(kwargs.get("column", ""))
                value = str(kwargs.get("value", ""))

                data_rows = [
                    d
                    for d in el.descendants()
                    if d.element_info.control_type in ("DataItem", "Row")
                ]
                if row_index < len(data_rows):
                    row_el = data_rows[row_index]
                    cells = [
                        c
                        for c in row_el.descendants()
                        if c.element_info.control_type
                        in ("Text", "Edit", "CheckBox", "DataItem")
                    ]

                    headers = [
                        d
                        for d in el.descendants()
                        if d.element_info.control_type == "Header"
                    ]
                    header_items = []
                    for h in headers:
                        header_items.extend(
                            [
                                d.element_info.name
                                for d in h.descendants()
                                if d.element_info.name
                            ]
                        )
                    if not header_items:
                        header_items = [
                            d.element_info.name
                            for d in el.descendants()
                            if d.element_info.control_type == "HeaderItem"
                            and d.element_info.name
                        ]

                    cell_el = None
                    if column in header_items:
                        col_index = header_items.index(column)
                        if col_index < len(cells):
                            cell_el = cells[col_index]
                    else:
                        try:
                            col_index = int(column)
                            if col_index < len(cells):
                                cell_el = cells[col_index]
                        except ValueError:
                            pass

                    if cell_el:
                        if hasattr(cell_el, "set_edit_text"):
                            cell_el.set_edit_text(value)
                        else:
                            cell_el.click_input()
                            cell_el.type_keys(value, with_spaces=True, with_tabs=True)
                    else:
                        raise ControlNotFoundError(
                            f"Cell in column {column} not found in row {row_index}"
                        )
                else:
                    raise ControlNotFoundError(
                        f"Row index {row_index} out of range for grid {control_id}"
                    )
            else:
                raise UnsupportedControlError(f"Unsupported action {action}")

            return {"action": action, "control_id": control_id}
        except DesktopMCPError:
            raise
        except Exception as exc:
            raise DesktopMCPError(f"Interaction {action} failed: {exc}") from exc

    def read_table(self, control_id: str) -> dict:
        self._check_platform()
        el = self._resolve_control(control_id)

        columns = []
        rows = []

        try:
            headers = [
                d for d in el.descendants() if d.element_info.control_type == "Header"
            ]
            header_items = []
            for h in headers:
                header_items.extend(
                    [
                        d.element_info.name
                        for d in h.descendants()
                        if d.element_info.name
                    ]
                )

            if not header_items:
                header_items = [
                    d.element_info.name
                    for d in el.descendants()
                    if d.element_info.control_type == "HeaderItem"
                    and d.element_info.name
                ]

            columns = header_items

            data_rows = [
                d
                for d in el.descendants()
                if d.element_info.control_type in ("DataItem", "Row")
            ]
            for row_el in data_rows:
                row_cells = {}
                cells = [
                    c
                    for c in row_el.descendants()
                    if c.element_info.control_type
                    in ("Text", "Edit", "CheckBox", "DataItem")
                ]

                if columns:
                    for i, cell in enumerate(cells):
                        if i < len(columns):
                            col_name = columns[i]
                            try:
                                row_cells[col_name] = (
                                    cell.window_text() or cell.element_info.name or ""
                                )
                            except Exception:
                                row_cells[col_name] = ""
                else:
                    for i, cell in enumerate(cells):
                        col_name = f"Column {i}"
                        try:
                            row_cells[col_name] = (
                                cell.window_text() or cell.element_info.name or ""
                            )
                        except Exception:
                            row_cells[col_name] = ""
                if row_cells:
                    rows.append(row_cells)
        except Exception as exc:
            raise DesktopMCPError(f"Failed to read table: {exc}") from exc

        return {"columns": columns, "rows": rows}

    def find_row(self, control_id: str, criteria: dict[str, Any]) -> dict:
        self._check_platform()
        table = self.read_table(control_id)
        for index, row in enumerate(table["rows"]):
            if all(row.get(key) == value for key, value in criteria.items()):
                return {"row_index": index, "row": row}
        raise ControlNotFoundError("Table row could not be located")

    def capture_window(self, window_id: str, path: str | None = None) -> dict:
        self._check_platform()
        try:
            win = self._resolve_window(window_id)
            rect = win.rectangle()
            bbox = (rect.left, rect.top, rect.right, rect.bottom)
            screenshot = ImageGrab.grab(bbox=bbox)

            if path is None:
                os.makedirs("screenshots", exist_ok=True)
                path = os.path.abspath(f"screenshots/{window_id}.png")
            else:
                dir_name = os.path.dirname(path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                path = os.path.abspath(path)

            screenshot.save(path)
            return {"window_id": window_id, "artifact": path}
        except Exception as exc:
            raise DesktopMCPError(f"Failed to capture window: {exc}") from exc

    def capture_desktop(self, path: str | None = None) -> dict:
        self._check_platform()
        try:
            screenshot = ImageGrab.grab()
            if path is None:
                os.makedirs("screenshots", exist_ok=True)
                path = os.path.abspath("screenshots/desktop.png")
            else:
                dir_name = os.path.dirname(path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                path = os.path.abspath(path)
            screenshot.save(path)
            return {"artifact": path}
        except Exception as exc:
            raise DesktopMCPError(f"Failed to capture desktop: {exc}") from exc

    def start_recording(self, path: str | None = None) -> dict:
        self._check_platform()
        if self._recording_thread and self._recording_thread.is_alive():
            return {"recording": True, "message": "Recording already in progress"}

        self._recording_path = path
        self._recording_frames = []
        self._stop_recording_event.clear()

        def record_loop():
            import time

            while not self._stop_recording_event.is_set():
                try:
                    if ImageGrab is not None:
                        frame = ImageGrab.grab()
                        frame = frame.resize((800, 600))
                        self._recording_frames.append(frame)
                except Exception:
                    pass
                time.sleep(0.2)

        import threading

        self._recording_thread = threading.Thread(target=record_loop, daemon=True)
        self._recording_thread.start()
        return {"recording": True}

    def stop_recording(self) -> dict:
        self._check_platform()
        if not self._recording_thread or not self._recording_thread.is_alive():
            return {"recording": False, "message": "No recording in progress"}

        self._stop_recording_event.set()
        self._recording_thread.join(timeout=2.0)

        path = self._recording_path
        if path is None:
            os.makedirs("recordings", exist_ok=True)
            path = os.path.abspath("recordings/recording.gif")
        else:
            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            path = os.path.abspath(path)

        if self._recording_frames:
            try:
                first_frame = self._recording_frames[0]
                first_frame.save(
                    path,
                    save_all=True,
                    append_images=self._recording_frames[1:],
                    duration=200,
                    loop=0,
                )
            except Exception as exc:
                raise DesktopMCPError(f"Failed to compile animated GIF: {exc}") from exc
        else:
            try:
                from PIL import Image

                dummy = Image.new("RGB", (800, 600), color="black")
                dummy.save(path)
            except Exception as exc:
                raise DesktopMCPError(
                    f"Failed to create empty recording: {exc}"
                ) from exc

        self._recording_frames = []
        return {"recording": False, "artifact": path}

    def wait_for_browser(self, timeout: float = 60.0) -> dict:
        self._check_platform()
        import time

        start = time.perf_counter()
        while time.perf_counter() - start < timeout:
            for win in self.list_windows():
                try:
                    pid = (
                        int(win.application_id.split("_")[1])
                        if win.application_id and "_" in win.application_id
                        else None
                    )
                    if pid:
                        proc_name = psutil.Process(pid).name().lower()
                        if any(
                            b in proc_name
                            for b in (
                                "chrome",
                                "msedge",
                                "edge",
                                "firefox",
                                "browser",
                                "iexplore",
                            )
                        ):
                            return {"window_id": win.window_id}
                except Exception:
                    pass

                title_lower = win.title.lower()
                if any(
                    b in title_lower
                    for b in (
                        " - google chrome",
                        " - microsoft edge",
                        " - firefox",
                    )
                ):
                    return {"window_id": win.window_id}
            time.sleep(0.5)

        raise WindowNotFoundError("Browser window could not be located within timeout")

    def attach_browser_window(self, title_contains: str | None = None) -> dict:
        self._check_platform()
        for win in self.list_windows():
            if title_contains and title_contains.lower() not in win.title.lower():
                continue
            try:
                pid = (
                    int(win.application_id.split("_")[1])
                    if win.application_id and "_" in win.application_id
                    else None
                )
                if pid:
                    proc_name = psutil.Process(pid).name().lower()
                    if any(
                        b in proc_name
                        for b in (
                            "chrome",
                            "msedge",
                            "edge",
                            "firefox",
                            "browser",
                            "iexplore",
                        )
                    ):
                        return {"window_id": win.window_id}
            except Exception:
                pass

            title_lower = win.title.lower()
            if any(
                b in title_lower
                for b in (
                    " - google chrome",
                    " - microsoft edge",
                    " - firefox",
                )
            ):
                return {"window_id": win.window_id}

        for win in self.list_windows():
            if title_contains and title_contains.lower() in win.title.lower():
                return {"window_id": win.window_id}

        raise WindowNotFoundError("Browser window not found")

    def _resolve_window(self, window_id: str) -> Any:
        try:
            handle = (
                int(window_id.split("_")[1]) if "_" in window_id else int(window_id)
            )
        except (ValueError, IndexError) as exc:
            raise WindowNotFoundError(f"Invalid window ID: {window_id}") from exc

        try:
            desktop = PyWinDesktop(backend="uia")
            win = desktop.window(handle=handle)
            # Access a property to force validation of window existence
            _ = win.window_text()
            return win
        except Exception as exc:
            raise WindowNotFoundError(f"Window not found: {window_id}") from exc

    def _resolve_control(self, control_id: str) -> Any:
        if control_id in self._controls_cache:
            try:
                # Validate the cached element
                _ = self._controls_cache[control_id].element_info.name
                return self._controls_cache[control_id]
            except Exception:
                del self._controls_cache[control_id]

        desktop = PyWinDesktop(backend="uia")
        for win in desktop.windows():
            try:
                for desc in win.descendants():
                    desc_id = self._get_control_id(desc)
                    self._controls_cache[desc_id] = desc
                    if desc_id == control_id:
                        return desc
            except Exception:
                continue
        raise ControlNotFoundError(f"Control not found: {control_id}")

    def _get_control_id(self, element: Any) -> str:
        try:
            runtime_id = element.element_info.runtime_id
            if runtime_id:
                return "ctrl_" + "_".join(map(str, runtime_id))
        except Exception:
            pass
        return f"ctrl_{id(element)}"

    def _map_control(self, element: Any) -> Control:
        info = element.element_info
        control_id = self._get_control_id(element)
        self._controls_cache[control_id] = element

        # Normalize type
        raw_type = info.control_type or ""
        normalized_type = UIA_CONTROL_TYPE_MAP.get(raw_type, raw_type)

        patterns = []
        try:
            if hasattr(element, "invoke"):
                patterns.append("InvokePattern")
            if hasattr(element, "get_value") or hasattr(element, "set_edit_text"):
                patterns.append("ValuePattern")
            if hasattr(element, "select") or hasattr(element, "is_selected"):
                patterns.append("SelectionItemPattern")
            if hasattr(element, "toggle") or hasattr(element, "get_toggle_state"):
                patterns.append("TogglePattern")
        except Exception:
            pass

        bounds = {}
        try:
            rect = element.rectangle()
            bounds = {
                "x": rect.left,
                "y": rect.top,
                "width": rect.width(),
                "height": rect.height(),
            }
        except Exception:
            pass

        value = None
        try:
            if hasattr(element, "get_value"):
                value = element.get_value()
            elif hasattr(element, "window_text"):
                value = element.window_text()
        except Exception:
            pass

        return Control(
            id=control_id,
            name=info.name or "",
            type=normalized_type,
            automation_id=info.automation_id,
            enabled=element.is_enabled(),
            visible=element.is_visible(),
            focused=info.focused,
            value=value,
            bounds=bounds,
            patterns=patterns,
        )
