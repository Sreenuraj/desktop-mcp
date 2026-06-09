from __future__ import annotations

import contextlib
import logging
import os
import sys
import time
import warnings
from typing import Any

from desktop_mcp.errors import (
    AppNotFoundError,
    ControlDisabledError,
    ControlNotFoundError,
    DesktopMCPError,
    SnapshotEmptyError,
    UnsupportedControlError,
    WindowNotFoundError,
)
from desktop_mcp.models.application import Application
from desktop_mcp.models.control import Control
from desktop_mcp.models.window import Window

logger = logging.getLogger(__name__)

# Try to import Windows dependencies, otherwise define them as None to allow
# testing/linting on macOS
psutil: Any = None
win32con: Any = None
win32gui: Any = None
win32process: Any = None
ctypes_mod: Any = None
ImageGrab: Any = None
PyWinApplication: Any = None
PyWinDesktop: Any = None
pywinauto_mouse: Any = None

try:
    if sys.platform == "win32":
        import ctypes as ctypes_mod_real  # type: ignore

        ctypes_mod = ctypes_mod_real
        import psutil as psutil_mod  # type: ignore

        psutil = psutil_mod
        import win32con as win32con_mod  # type: ignore

        win32con = win32con_mod
        import win32gui as win32gui_mod  # type: ignore

        win32gui = win32gui_mod
        import win32process as win32process_mod  # type: ignore

        win32process = win32process_mod
        from PIL import ImageGrab as ImageGrab_mod

        ImageGrab = ImageGrab_mod
        from pywinauto import Application as PyWinApplication_mod  # type: ignore

        PyWinApplication = PyWinApplication_mod
        from pywinauto import Desktop as PyWinDesktop_mod  # type: ignore

        PyWinDesktop = PyWinDesktop_mod
        from pywinauto import mouse as pywinauto_mouse_mod  # type: ignore

        pywinauto_mouse = pywinauto_mouse_mod
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Phase 3 — UWP / suspended-process detection constants
# ---------------------------------------------------------------------------

# Window class names that indicate a UWP host shell.  The real app UI lives
# in a nested child window, not directly under the host.
_UWP_HOST_CLASS_NAMES = frozenset({
    "ApplicationFrameWindow",
    "Windows.UI.Core.CoreWindow",
})

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

# Control types that are pure structural containers — an empty tree of only these
# types is a strong signal that UIA didn't actually enumerate the app's UI.
_STRUCTURAL_ONLY_TYPES = frozenset({"Pane", "Window", "Group", "Custom", "Separator"})

# Actions that can be performed via UIA patterns without requiring foreground.
# Everything else falls back to mouse/keyboard synthesis which needs foreground.
_PATTERN_ACTIONS = frozenset(
    {"click", "left", "toggle", "select_item", "enter_text", "expand_node",
     "collapse_node", "scroll_into_view", "read_text"}
)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _is_foreground(hwnd: int) -> bool:
    """Return True if *hwnd* is the current foreground window."""
    try:
        return bool(win32gui and win32gui.GetForegroundWindow() == hwnd)
    except Exception:
        return False


def _get_foreground_hwnd() -> int:
    """Return the HWND of the current foreground window (0 on failure)."""
    try:
        if win32gui:
            return win32gui.GetForegroundWindow() or 0
    except Exception:
        pass
    return 0


def _get_foreground_title() -> str:
    """Return the title of the current foreground window (best-effort)."""
    try:
        if win32gui:
            hwnd = win32gui.GetForegroundWindow()
            return win32gui.GetWindowText(hwnd) or ""
    except Exception:
        pass
    return ""


def _has_non_trivial_bounds(win_wrapper: Any) -> bool:
    """Return True if the window has a non-zero bounding rectangle."""
    try:
        rect = win_wrapper.rectangle()
        return (rect.width() > 0) and (rect.height() > 0)
    except Exception:
        return True  # assume non-trivial if we can't check


def _controls_are_structural_only(controls: list[Control]) -> bool:
    """Return True if every control in *controls* is a pure structural container."""
    if not controls:
        return True
    return all(c.type in _STRUCTURAL_ONLY_TYPES for c in controls)


# ---------------------------------------------------------------------------
# Phase 2.3 — Proper foreground acquisition
# ---------------------------------------------------------------------------

def _acquire_foreground(hwnd: int) -> bool:
    """Bring *hwnd* to the foreground using the documented Windows sequence.

    Replaces the Alt-key hack with:
      1. AllowSetForegroundWindow(ASFW_ANY)
      2. AttachThreadInput(current, foreground, TRUE)
      3. BringWindowToTop(hwnd)
      4. SetForegroundWindow(hwnd)
      5. SwitchToThisWindow(hwnd, TRUE)  — last resort
      6. AttachThreadInput(current, foreground, FALSE)

    Returns True if the window became foreground.
    """
    if not (win32gui and ctypes_mod):
        return False
    try:
        # Allow any process to set foreground
        ASFW_ANY = 0xFFFFFFFF
        ctypes_mod.windll.user32.AllowSetForegroundWindow(ASFW_ANY)

        # Get thread IDs
        current_thread = ctypes_mod.windll.kernel32.GetCurrentThreadId()
        fg_hwnd = win32gui.GetForegroundWindow()
        fg_thread = 0
        if fg_hwnd and win32process:
            try:
                fg_thread, _ = win32process.GetWindowThreadProcessId(fg_hwnd)
            except Exception:
                pass

        attached = False
        if fg_thread and fg_thread != current_thread:
            try:
                ctypes_mod.windll.user32.AttachThreadInput(
                    current_thread, fg_thread, True
                )
                attached = True
            except Exception:
                pass

        try:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.05)

            if not _is_foreground(hwnd):
                # Last resort: SwitchToThisWindow
                ctypes_mod.windll.user32.SwitchToThisWindow(hwnd, True)
                time.sleep(0.05)
        finally:
            if attached:
                try:
                    ctypes_mod.windll.user32.AttachThreadInput(
                        current_thread, fg_thread, False
                    )
                except Exception:
                    pass

        return _is_foreground(hwnd)
    except Exception as exc:
        logger.debug("_acquire_foreground failed for hwnd=%d: %s", hwnd, exc)
        return False


# ---------------------------------------------------------------------------
# Phase 3.1 — UWP / suspended-process detection helpers
# ---------------------------------------------------------------------------

def _get_window_class_name(hwnd: int) -> str:
    """Return the Win32 class name of *hwnd* (empty string on failure)."""
    try:
        if win32gui:
            return win32gui.GetClassName(hwnd) or ""
    except Exception:
        pass
    return ""


def _is_uwp_host(hwnd: int) -> bool:
    """Return True if *hwnd* is a UWP host shell window.

    UWP apps are wrapped in an ``ApplicationFrameWindow`` shell.  The actual
    app UI lives in a nested child window, not directly under the host.
    """
    return _get_window_class_name(hwnd) in _UWP_HOST_CLASS_NAMES


def _is_immersive_process(hwnd: int) -> bool:
    """Return True if the process owning *hwnd* is a UWP/immersive process.

    Uses ``IsImmersiveProcess`` from user32.dll (Windows 8+).
    Falls back to False on older Windows or when ctypes is unavailable.
    """
    try:
        if not (ctypes_mod and win32process):
            return False
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        hproc = ctypes_mod.windll.kernel32.OpenProcess(
            0x0400,  # PROCESS_QUERY_INFORMATION
            False,
            pid,
        )
        if not hproc:
            return False
        try:
            result = ctypes_mod.windll.user32.IsImmersiveProcess(hproc)
            return bool(result)
        finally:
            ctypes_mod.windll.kernel32.CloseHandle(hproc)
    except Exception:
        return False


def _find_uwp_real_child(win_wrapper: Any) -> Any | None:
    """For a UWP ``ApplicationFrameWindow`` host, find the nested child that
    holds the real app UI.

    The real child is typically the first child whose class name is NOT
    ``ApplicationFrameTitleBarWindow`` or ``ApplicationFrameInputSinkWindow``.
    Returns the child wrapper, or None if not found.
    """
    try:
        if not win32gui:
            return None
        host_hwnd = win_wrapper.handle

        real_child = None

        def _enum_cb(child_hwnd, _):
            nonlocal real_child
            cls = _get_window_class_name(child_hwnd)
            if cls not in (
                "ApplicationFrameTitleBarWindow",
                "ApplicationFrameInputSinkWindow",
                "ApplicationFrameStatusBarWindow",
            ):
                real_child = child_hwnd
                return False  # stop enumeration
            return True  # continue

        ctypes_mod.windll.user32.EnumChildWindows(
            host_hwnd,
            ctypes_mod.WINFUNCTYPE(
                ctypes_mod.c_bool, ctypes_mod.POINTER(ctypes_mod.c_int), ctypes_mod.POINTER(ctypes_mod.c_int)
            )(_enum_cb),
            0,
        )

        if real_child:
            try:
                desktop = PyWinDesktop(backend="uia")
                child_win = desktop.window(handle=real_child)
                return child_win.wrapper_object()
            except Exception:
                pass
    except Exception:
        pass
    return None


def _z_order_prewarm(hwnd: int) -> None:
    """Bring *hwnd* to the top of the Z-order WITHOUT stealing foreground.

    ``BringWindowToTop`` changes Z-order only — it does not activate the
    window or steal focus from the current foreground owner.  This gives
    UWP/suspended-process UIA providers a chance to resume.
    """
    try:
        if win32gui:
            win32gui.BringWindowToTop(hwnd)
            time.sleep(0.05)  # give the UIA provider time to wake up
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 2.2 — _foreground_lease context manager
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _foreground_lease(hwnd: int, restore_hwnd: int = 0):
    """Context manager that acquires foreground for *hwnd*, runs the body,
    then restores foreground to *restore_hwnd* (Phase 2.4).

    Yields a dict with ``acquired`` (bool) and ``restored`` (bool).
    """
    result = {"acquired": False, "restored": False}
    try:
        result["acquired"] = _acquire_foreground(hwnd)
        yield result
    finally:
        if restore_hwnd and restore_hwnd != hwnd:
            try:
                restored = _acquire_foreground(restore_hwnd)
                result["restored"] = restored
            except Exception:
                pass


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
            # Take a snapshot of existing window handles before launch
            existing_handles: set[int] = set()
            try:
                for w in PyWinDesktop(backend="uia").windows():
                    existing_handles.add(w.handle)
            except Exception:
                pass

            app = PyWinApplication(backend="uia").start(cmd_line)
            process_id = app.process

            # Wait briefly — UWP apps (e.g. calc.exe) are shims that
            # spawn a separate process and exit immediately.
            time.sleep(1.5)

            # Check if the launched process is still alive
            process_alive = False
            try:
                proc = psutil.Process(process_id)
                process_alive = proc.is_running() and proc.status() != "zombie"
            except Exception:
                pass

            if process_alive:
                application_id = f"app_{process_id}"
                self._apps[application_id] = app
                return Application(
                    application_id=application_id,
                    process_id=process_id,
                    path=path,
                )

            # UWP shim case: original process died, find the new window
            new_win = None
            for w in PyWinDesktop(backend="uia").windows():
                if w.handle not in existing_handles:
                    try:
                        title = w.window_text() or ""
                        if title:
                            new_win = w
                            break
                    except Exception:
                        continue

            if new_win is not None:
                real_pid = new_win.process_id()
                application_id = f"app_{real_pid}"
                try:
                    real_app = PyWinApplication(backend="uia").connect(
                        handle=new_win.handle
                    )
                    self._apps[application_id] = real_app
                except Exception:
                    self._apps[application_id] = app
                return Application(
                    application_id=application_id,
                    process_id=real_pid,
                    path=path,
                )

            # Fallback: return original PID even though it may be dead
            application_id = f"app_{process_id}"
            self._apps[application_id] = app
            return Application(
                application_id=application_id,
                process_id=process_id,
                path=path,
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
                    active = _is_foreground(handle)
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

    # ------------------------------------------------------------------
    # Phase 1.2 + 2.3 — activate_window with proper foreground acquisition
    # ------------------------------------------------------------------

    def activate_window(self, window_id: str) -> dict[str, Any]:
        """Bring a window to the foreground using the proper Windows sequence.

        Phase 2.3: replaces the Alt-key hack with AttachThreadInput sequence.
        Returns observable state so the agent can verify success.
        """
        self._check_platform()
        t0 = time.perf_counter()
        try:
            win = self._resolve_window(window_id)
            if hasattr(win, "is_minimized") and win.is_minimized():
                win.restore()
                time.sleep(0.1)

            hwnd = win.handle if hasattr(win, "handle") else None
            became_foreground = False
            attempts = 1

            if hwnd:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                became_foreground = _acquire_foreground(hwnd)

            if hasattr(win, "set_focus"):
                try:
                    win.set_focus()
                except Exception:
                    pass

            is_fg = _is_foreground(hwnd) if hwnd else False
            fg_hwnd = _get_foreground_hwnd()
            fg_title = _get_foreground_title()
            fg_window_id = f"win_{fg_hwnd}" if fg_hwnd else ""
            total_ms = int((time.perf_counter() - t0) * 1000)

            return {
                "window_id": window_id,
                "is_foreground": is_fg,
                "became_foreground": became_foreground,
                "foreground_window_id": fg_window_id,
                "foreground_title": fg_title,
                "attempts": attempts,
                "total_ms": total_ms,
            }
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

    # ------------------------------------------------------------------
    # Phase 1.1 + 1.2 — get_window with empty-result detection
    # ------------------------------------------------------------------

    def get_window(self, window_id: str) -> Window:
        """Snapshot a window's control tree.

        Phase 3 snapshot strategy (in order, stopping as soon as controls appear):

        1. Restore/show the window (no foreground steal).
        2. Z-order pre-warm: ``BringWindowToTop`` without stealing focus.
        3. Attempt UIA snapshot (children → descendants).
        4. If empty AND window is a UWP ``ApplicationFrameWindow`` host:
           walk into the real child window and snapshot that instead.
        5. If still empty: acquire full foreground (Phase 2.3) and retry once.
        6. If still empty and window has non-trivial bounds: raise
           ``SnapshotEmptyError`` with a structured hint.
        """
        self._check_platform()
        t0 = time.perf_counter()
        try:
            win_wrapper = self._resolve_window(window_id)
            handle = win_wrapper.handle
            title = win_wrapper.window_text() or ""
            process_id = win_wrapper.process_id()
            application_id = f"app_{process_id}"

            # Step 1: restore minimised window (no foreground steal yet)
            try:
                if win_wrapper.is_minimized():
                    win_wrapper.restore()
                    time.sleep(0.15)
                if win32gui and win32con:
                    win32gui.ShowWindow(handle, win32con.SW_SHOW)
            except Exception:
                pass

            # Step 2: Phase 3.3 — Z-order pre-warm (non-stealing)
            _z_order_prewarm(handle)

            def _snapshot_wrapper(wrapper: Any) -> tuple[list[Control], str, Exception | None]:
                """Try children() then descendants() on *wrapper*.
                Returns (controls, capture_method, first_exception).
                """
                controls_out: list[Control] = []
                method_out = "uia_children"
                first_exc: Exception | None = None

                try:
                    children = wrapper.children()
                except Exception as exc:
                    children = []
                    first_exc = exc

                for child in children:
                    try:
                        controls_out.extend(self._build_control_tree(child))
                    except Exception as exc:
                        logger.warning(
                            "Error building control tree for child of window %r: %s",
                            title, exc,
                        )
                        if first_exc is None:
                            first_exc = exc

                if not controls_out:
                    method_out = "uia_descendants"
                    try:
                        descendants = wrapper.descendants()
                    except Exception as exc:
                        descendants = []
                        if first_exc is None:
                            first_exc = exc

                    for desc in descendants:
                        try:
                            if self._should_include_control(desc):
                                controls_out.append(self._map_control(desc))
                        except Exception as exc:
                            logger.warning(
                                "Error mapping descendant in window %r: %s",
                                title, exc,
                            )

                return controls_out, method_out, first_exc

            # Step 3: first snapshot attempt
            controls, capture_method, first_exception = _snapshot_wrapper(win_wrapper)

            # Step 4: Phase 3.2 — UWP host → walk into real child
            if (not controls or _controls_are_structural_only(controls)) and _is_uwp_host(handle):
                logger.debug(
                    "Window %r is a UWP ApplicationFrameWindow host; "
                    "attempting to snapshot real child.",
                    title,
                )
                real_child = _find_uwp_real_child(win_wrapper)
                if real_child is not None:
                    child_controls, child_method, child_exc = _snapshot_wrapper(real_child)
                    if child_controls and not _controls_are_structural_only(child_controls):
                        controls = child_controls
                        capture_method = f"uwp_child_{child_method}"
                        first_exception = child_exc

            # Step 5: full foreground acquisition + retry (last resort)
            if not controls or _controls_are_structural_only(controls):
                logger.debug(
                    "Snapshot of %r still empty after Z-order prewarm; "
                    "acquiring foreground and retrying.",
                    title,
                )
                try:
                    _acquire_foreground(handle)
                    if hasattr(win_wrapper, "set_focus"):
                        win_wrapper.set_focus()
                    time.sleep(0.1)
                except Exception:
                    pass

                retry_controls, retry_method, retry_exc = _snapshot_wrapper(win_wrapper)
                if retry_controls and not _controls_are_structural_only(retry_controls):
                    controls = retry_controls
                    capture_method = f"fg_retry_{retry_method}"
                    first_exception = retry_exc

            active = _is_foreground(handle)
            took_ms = int((time.perf_counter() - t0) * 1000)

            # Step 6: Phase 1.1 — raise SnapshotEmptyError when tree is still empty
            if not controls or _controls_are_structural_only(controls):
                has_bounds = _has_non_trivial_bounds(win_wrapper)
                if has_bounds:
                    is_uwp = _is_uwp_host(handle) or _is_immersive_process(handle)
                    uia_state = "denied" if first_exception else "empty"
                    hint_parts = [
                        "UIA returned no interactive descendants for this window.",
                        "Likely causes: window is not foreground / process is suspended"
                        " / UIA access denied.",
                    ]
                    if is_uwp:
                        hint_parts.append(
                            "This appears to be a UWP/immersive app. "
                            "UWP providers may suspend when not foreground. "
                            "Try activate_window then window_snapshot again."
                        )
                    hint_parts.append(
                        "Recovery: call activate_window then window_snapshot again, "
                        "or use capture_window for a visual fallback."
                    )
                    hint = " ".join(hint_parts)
                    raise SnapshotEmptyError(
                        f"UIA returned no descendants for window '{title}'. "
                        f"Likely causes: window is not foreground / process is suspended "
                        f"/ UIA access denied. "
                        f"Try activate_window then window_snapshot again, "
                        f"or use capture_window for visual fallback.",
                        details={
                            "window_id": window_id,
                            "title": title,
                            "is_foreground": active,
                            "is_uwp": is_uwp,
                            "uia_state": uia_state,
                            "took_ms": took_ms,
                            "hint": hint,
                        },
                    )

            win_obj = Window(
                window_id=window_id,
                title=title,
                application_id=application_id,
                active=active,
                controls=controls,
            )
            win_obj._snapshot_meta = {  # type: ignore[attr-defined]
                "controls_count": len(controls),
                "capture_method": capture_method,
                "uia_state": "live",
                "took_ms": took_ms,
            }
            return win_obj

        except (WindowNotFoundError, SnapshotEmptyError):
            raise
        except Exception as exc:
            raise DesktopMCPError(f"Failed to get window {window_id}: {exc}") from exc

    def _should_include_control(self, element: Any) -> bool:
        """Filter out layout/formatting elements to keep tree snapshots AI-friendly."""
        try:
            info = element.element_info
            ctrl_type = info.control_type or ""

            if ctrl_type in (
                "Button", "CheckBox", "ComboBox", "Edit", "RadioButton",
                "Hyperlink", "MenuItem", "TabItem", "TreeViewItem",
            ):
                return True

            if info.name or info.automation_id:
                return True

            if ctrl_type in ("Table", "DataGrid", "List", "Tree", "Tab"):
                return True

            if ctrl_type in ("Pane", "Group", "Custom", "Separator"):
                return False

            return True
        except Exception:
            return True

    def _build_control_tree(
        self, element: Any, current_depth: int = 0, max_depth: int = 8
    ) -> list[Control]:
        """Recursively traverse the UIA element hierarchy."""
        if current_depth > max_depth:
            return []

        include = self._should_include_control(element)

        child_controls: list[Control] = []
        first_child_exc: Exception | None = None
        try:
            children = element.children()
        except Exception:
            children = []

        for child in children:
            try:
                child_controls.extend(
                    self._build_control_tree(child, current_depth + 1, max_depth)
                )
            except Exception as exc:
                logger.warning(
                    "Skipping child element during control tree build: %s", exc
                )
                if first_child_exc is None:
                    first_child_exc = exc

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
        window = self.get_window(window_id)
        flat_controls: list[Control] = []

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

    # ------------------------------------------------------------------
    # Phase 2.1 + 2.2 + 2.4 — Pattern-first interaction dispatcher
    # ------------------------------------------------------------------

    def interact(
        self,
        action: str,
        control_id: str,
        restore_foreground: bool = True,
        **kwargs: Any,
    ) -> dict:
        """Execute an action on a control.

        Phase 2.1: tries UIA patterns first (no foreground needed), falls back
        to mouse/keyboard synthesis only when no pattern is available.

        Phase 2.2: foreground is only acquired inside ``_foreground_lease``
        when the chosen method actually requires it.

        Phase 2.4: if ``restore_foreground=True`` (default), the foreground
        window that was active *before* the action is restored afterwards.
        This keeps VSCode in foreground throughout the agent session.
        """
        self._check_platform()
        t0 = time.perf_counter()

        # Global press_keys with no control target
        if not control_id and action == "press_keys":
            import pywinauto.keyboard

            keys = kwargs.get("keys", "")
            pywinauto.keyboard.send_keys(keys, with_spaces=True, with_tabs=True)
            took_ms = int((time.perf_counter() - t0) * 1000)
            return {
                "action": action,
                "control_id": control_id,
                "method": "global_send_keys",
                "required_foreground": True,
                "foreground_taken": False,
                "foreground_restored": False,
                "took_ms": took_ms,
            }

        el = self._resolve_control(control_id)
        if not el.is_enabled():
            raise ControlDisabledError(f"Control is disabled: {control_id}")

        # Capture the current foreground window so we can restore it (Phase 2.4)
        caller_hwnd = _get_foreground_hwnd() if restore_foreground else 0

        method = "click_input"
        required_foreground = True
        foreground_taken = False
        foreground_restored = False

        def _get_parent_hwnd() -> int:
            try:
                if hasattr(el, "top_level_parent"):
                    parent = el.top_level_parent()
                    if hasattr(parent, "handle"):
                        return parent.handle
            except Exception:
                pass
            return 0

        def _ensure_foreground() -> bool:
            """Acquire foreground for the control's parent window.
            Returns True if foreground was acquired."""
            nonlocal foreground_taken
            parent_hwnd = _get_parent_hwnd()
            if not parent_hwnd:
                return False
            try:
                if hasattr(el, "top_level_parent"):
                    parent = el.top_level_parent()
                    if hasattr(parent, "is_minimized") and parent.is_minimized():
                        parent.restore()
                        time.sleep(0.1)
            except Exception:
                pass
            acquired = _acquire_foreground(parent_hwnd)
            if acquired:
                foreground_taken = True
            return acquired

        def _restore_caller() -> bool:
            """Restore foreground to the caller's window (Phase 2.4)."""
            nonlocal foreground_restored
            if caller_hwnd and caller_hwnd != _get_foreground_hwnd():
                restored = _acquire_foreground(caller_hwnd)
                foreground_restored = restored
                return restored
            return False

        try:
            # ----------------------------------------------------------------
            # Phase 2.1: Pattern-first dispatch table
            # ----------------------------------------------------------------

            if action in ("left", "click"):
                ctrl_type = el.element_info.control_type

                # Button → InvokePattern (no foreground needed)
                if hasattr(el, "invoke") and ctrl_type == "Button":
                    try:
                        el.invoke()
                        method = "uia_invoke"
                        required_foreground = False
                    except Exception:
                        _ensure_foreground()
                        el.click_input()
                        method = "click_input"

                # CheckBox → TogglePattern (no foreground needed)
                elif hasattr(el, "toggle") and ctrl_type == "CheckBox":
                    try:
                        el.toggle()
                        method = "uia_toggle"
                        required_foreground = False
                    except Exception:
                        _ensure_foreground()
                        el.click_input()
                        method = "click_input"

                # List/menu/tab/radio items → SelectionItemPattern (no foreground)
                elif hasattr(el, "select") and ctrl_type in (
                    "ListItem", "MenuItem", "TabItem", "RadioButton", "TreeViewItem",
                ):
                    try:
                        el.select()
                        method = "uia_select"
                        required_foreground = False
                    except Exception:
                        _ensure_foreground()
                        el.click_input()
                        method = "click_input"

                # Hyperlink → InvokePattern
                elif hasattr(el, "invoke") and ctrl_type == "Hyperlink":
                    try:
                        el.invoke()
                        method = "uia_invoke"
                        required_foreground = False
                    except Exception:
                        _ensure_foreground()
                        el.click_input()
                        method = "click_input"

                # SplitButton → InvokePattern
                elif hasattr(el, "invoke") and ctrl_type == "SplitButton":
                    try:
                        el.invoke()
                        method = "uia_invoke"
                        required_foreground = False
                    except Exception:
                        _ensure_foreground()
                        el.click_input()
                        method = "click_input"

                # Fallback: mouse click (requires foreground)
                else:
                    _ensure_foreground()
                    el.click_input()
                    method = "click_input"

            elif action == "toggle":
                # Explicit toggle action (e.g. checkbox)
                if hasattr(el, "toggle"):
                    try:
                        el.toggle()
                        method = "uia_toggle"
                        required_foreground = False
                    except Exception:
                        _ensure_foreground()
                        el.click_input()
                        method = "click_input"
                else:
                    _ensure_foreground()
                    el.click_input()
                    method = "click_input"

            elif action == "double":
                _ensure_foreground()
                if hasattr(el, "double_click_input"):
                    el.double_click_input()
                else:
                    el.click_input()
                    el.click_input()
                method = "click_input"

            elif action == "right":
                _ensure_foreground()
                el.right_click_input()
                method = "click_input"

            elif action == "hover":
                _ensure_foreground()
                el.move_mouse_input()
                method = "click_input"

            elif action == "enter_text":
                val = kwargs.get("value", "")
                # ValuePattern.SetValue — no foreground needed
                if hasattr(el, "set_edit_text"):
                    try:
                        el.set_edit_text(val)
                        method = "uia_value"
                        required_foreground = False
                    except Exception:
                        _ensure_foreground()
                        el.type_keys(val, with_spaces=True, with_tabs=True)
                        method = "type_keys"
                else:
                    _ensure_foreground()
                    el.type_keys(val, with_spaces=True, with_tabs=True)
                    method = "type_keys"

            elif action == "press_keys":
                val = kwargs.get("keys", "")
                _ensure_foreground()
                el.set_focus()
                el.type_keys(val, with_spaces=True, with_tabs=True)
                method = "type_keys"

            elif action == "select_item":
                val = str(kwargs.get("value", ""))
                # SelectionItemPattern — no foreground needed
                if hasattr(el, "select"):
                    try:
                        el.select(val)
                        method = "uia_select"
                        required_foreground = False
                    except Exception:
                        _ensure_foreground()
                        el.click_input()
                        method = "click_input"
                else:
                    _ensure_foreground()
                    el.click_input()
                    method = "click_input"

            elif action == "expand_node":
                # ExpandCollapsePattern — no foreground needed
                if hasattr(el, "expand"):
                    try:
                        el.expand()
                        method = "uia_expand"
                        required_foreground = False
                    except Exception:
                        _ensure_foreground()
                        el.click_input()
                        method = "click_input"
                else:
                    _ensure_foreground()
                    el.click_input()
                    method = "click_input"

            elif action == "collapse_node":
                # ExpandCollapsePattern — no foreground needed
                if hasattr(el, "collapse"):
                    try:
                        el.collapse()
                        method = "uia_collapse"
                        required_foreground = False
                    except Exception:
                        _ensure_foreground()
                        el.click_input()
                        method = "click_input"
                else:
                    _ensure_foreground()
                    el.click_input()
                    method = "click_input"

            elif action == "scroll_into_view":
                # ScrollItemPattern — no foreground needed
                if hasattr(el, "scroll_into_view"):
                    try:
                        el.scroll_into_view()
                        method = "uia_scroll_into_view"
                        required_foreground = False
                    except Exception:
                        _ensure_foreground()
                        el.click_input()
                        method = "click_input"
                else:
                    required_foreground = False
                    method = "noop"

            else:
                raise UnsupportedControlError(f"Unsupported action {action}")

            # Phase 2.4: restore foreground to caller (VSCode) after action
            if restore_foreground and foreground_taken:
                _restore_caller()

            took_ms = int((time.perf_counter() - t0) * 1000)
            return {
                "action": action,
                "control_id": control_id,
                "method": method,
                "required_foreground": required_foreground,
                "foreground_taken": foreground_taken,
                "foreground_restored": foreground_restored,
                "took_ms": took_ms,
            }

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
                    if d.element_info.control_type == "HeaderItem" and d.element_info.name
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

    def capture_window(
        self,
        window_id: str,
        path: str | None = None,
        highlight_rect: tuple[int, int, int, int] | None = None,
    ) -> dict:
        self._check_platform()
        try:
            win = self._resolve_window(window_id)
            rect = win.rectangle()
            bbox = (rect.left, rect.top, rect.right, rect.bottom)
            screenshot = ImageGrab.grab(bbox=bbox)

            if highlight_rect:
                try:
                    from PIL import ImageDraw

                    rel_left = highlight_rect[0] - rect.left
                    rel_top = highlight_rect[1] - rect.top
                    rel_right = highlight_rect[2] - rect.left
                    rel_bottom = highlight_rect[3] - rect.top
                    draw = ImageDraw.Draw(screenshot)
                    draw.rectangle(
                        (rel_left, rel_top, rel_right, rel_bottom),
                        outline="red",
                        width=3,
                    )
                except Exception:
                    pass

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

    def capture_desktop(
        self,
        path: str | None = None,
        highlight_rect: tuple[int, int, int, int] | None = None,
    ) -> dict:
        self._check_platform()
        try:
            screenshot = ImageGrab.grab()

            if highlight_rect:
                try:
                    from PIL import ImageDraw

                    draw = ImageDraw.Draw(screenshot)
                    draw.rectangle(highlight_rect, outline="red", width=3)
                except Exception:
                    pass

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
                                "chrome", "msedge", "edge", "firefox",
                                "browser", "iexplore",
                            )
                        ):
                            return {"window_id": win.window_id}
                except Exception:
                    pass

                title_lower = win.title.lower()
                if any(
                    b in title_lower
                    for b in (" - google chrome", " - microsoft edge", " - firefox")
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
                            "chrome", "msedge", "edge", "firefox",
                            "browser", "iexplore",
                        )
                    ):
                        return {"window_id": win.window_id}
            except Exception:
                pass

            title_lower = win.title.lower()
            if any(
                b in title_lower
                for b in (" - google chrome", " - microsoft edge", " - firefox")
            ):
                return {"window_id": win.window_id}

        for win in self.list_windows():
            if title_contains and title_contains.lower() in win.title.lower():
                return {"window_id": win.window_id}

        raise WindowNotFoundError("Browser window not found")

    def click_at(self, x: int, y: int, button: str = "left") -> dict:
        """Perform a mouse click at absolute screen coordinates."""
        self._check_platform()
        try:
            if button == "double":
                pywinauto_mouse.double_click(coords=(x, y))
            elif button == "right":
                pywinauto_mouse.right_click(coords=(x, y))
            else:
                pywinauto_mouse.click(coords=(x, y))
            return {"x": x, "y": y, "button": button}
        except Exception as exc:
            raise DesktopMCPError(f"Failed to click at ({x}, {y}): {exc}") from exc

    # ------------------------------------------------------------------
    # Phase 4.1 — wait_for_control
    # ------------------------------------------------------------------

    def wait_for_control(
        self,
        window_id: str,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        state: str = "exists",
        timeout_ms: int = 10_000,
    ) -> dict:
        """Poll until a control matching the criteria appears in *window_id*.

        Parameters
        ----------
        name : str, optional
            Case-insensitive substring match against control name.
        automation_id : str, optional
            Exact match against AutomationId.
        control_type : str, optional
            Exact match against control type (e.g. "Button").
        state : "exists" | "enabled" | "visible"
            Condition the control must satisfy.
        timeout_ms : int
            Maximum wait time in milliseconds (default 10 000).

        Returns the matching control dict on success.
        Raises ``ControlNotFoundError`` on timeout.
        """
        self._check_platform()
        from desktop_mcp.errors import ControlNotFoundError

        poll_interval = 0.25
        deadline = time.perf_counter() + timeout_ms / 1000.0

        while True:
            try:
                win = self.get_window(window_id)
                flat: list[Control] = []

                def _flatten(ctrls: list[Control]) -> None:
                    for c in ctrls:
                        flat.append(c)
                        _flatten(c.children)

                _flatten(win.controls)

                for ctrl in flat:
                    if name and name.lower() not in ctrl.name.lower():
                        continue
                    if automation_id and ctrl.automation_id != automation_id:
                        continue
                    if control_type and ctrl.type.lower() != control_type.lower():
                        continue
                    # State check
                    if state == "enabled" and not ctrl.enabled:
                        continue
                    if state == "visible" and not ctrl.visible:
                        continue
                    return ctrl.to_dict()
            except Exception:
                pass

            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                break
            time.sleep(min(poll_interval, remaining))

        criteria = []
        if name:
            criteria.append(f"name~'{name}'")
        if automation_id:
            criteria.append(f"automation_id='{automation_id}'")
        if control_type:
            criteria.append(f"type='{control_type}'")
        raise ControlNotFoundError(
            f"Control ({', '.join(criteria) or 'any'}) not found in window "
            f"'{window_id}' within {timeout_ms} ms (state={state})"
        )

    # ------------------------------------------------------------------
    # Phase 4.1 — wait_for_idle
    # ------------------------------------------------------------------

    def wait_for_idle(
        self,
        window_id: str,
        idle_ms: int = 500,
        timeout_ms: int = 10_000,
    ) -> dict:
        """Wait until the window's UI tree stops changing for *idle_ms* ms.

        Strategy:
        1. Call ``WaitForInputIdle`` on the process (Win32 apps only).
        2. Poll the control count every 100 ms; when it hasn't changed for
           *idle_ms* ms, declare idle.

        Returns ``{"idle": true, "settled_ms": <actual settle time>}``.
        Raises ``DesktopMCPError`` with code ``IDLE_TIMEOUT`` on timeout.
        """
        self._check_platform()
        t0 = time.perf_counter()
        deadline = t0 + timeout_ms / 1000.0
        poll_interval = 0.1  # 100 ms

        # Step 1: WaitForInputIdle (best-effort, Win32 only)
        try:
            win_wrapper = self._resolve_window(window_id)
            pid = win_wrapper.process_id()
            if ctypes_mod:
                hproc = ctypes_mod.windll.kernel32.OpenProcess(
                    0x00100000,  # SYNCHRONIZE
                    False,
                    pid,
                )
                if hproc:
                    ctypes_mod.windll.user32.WaitForInputIdle(
                        hproc, min(timeout_ms, 5000)
                    )
                    ctypes_mod.windll.kernel32.CloseHandle(hproc)
        except Exception:
            pass

        # Step 2: tree-settle check
        last_count: int | None = None
        stable_since: float = time.perf_counter()

        while True:
            try:
                win = self.get_window(window_id)
                flat: list[Control] = []

                def _flatten(ctrls: list[Control]) -> None:
                    for c in ctrls:
                        flat.append(c)
                        _flatten(c.children)

                _flatten(win.controls)
                count = len(flat)
            except Exception:
                count = -1

            now = time.perf_counter()
            if count != last_count:
                last_count = count
                stable_since = now
            elif (now - stable_since) * 1000 >= idle_ms:
                settled_ms = int((now - t0) * 1000)
                return {"idle": True, "settled_ms": settled_ms}

            if now >= deadline:
                break
            time.sleep(min(poll_interval, deadline - now))

        raise DesktopMCPError(
            f"Window '{window_id}' did not become idle within {timeout_ms} ms",
            details={"window_id": window_id, "timeout_ms": timeout_ms},
        )

    # ------------------------------------------------------------------
    # Phase 4.2 — select_row, click_cell, read_cell, read_tree
    # ------------------------------------------------------------------

    def select_row(
        self,
        control_id: str,
        by_text: str | None = None,
        by_index: int | None = None,
    ) -> dict:
        """Select a row in a DataGrid/ListView by text match or zero-based index.

        Tries ``SelectionItemPattern.Select()`` on the row element first;
        falls back to ``click_input()`` if the pattern is unavailable.
        """
        self._check_platform()
        el = self._resolve_control(control_id)

        try:
            rows = [
                d for d in el.descendants()
                if d.element_info.control_type in ("DataItem", "ListItem", "Row")
            ]
        except Exception as exc:
            raise DesktopMCPError(f"Failed to enumerate rows: {exc}") from exc

        if not rows:
            raise ControlNotFoundError(f"No rows found in control {control_id}")

        target_row = None
        if by_index is not None:
            if by_index < 0 or by_index >= len(rows):
                raise ControlNotFoundError(
                    f"Row index {by_index} out of range (0–{len(rows) - 1})"
                )
            target_row = rows[by_index]
        elif by_text is not None:
            for row in rows:
                try:
                    row_text = row.window_text() or row.element_info.name or ""
                    if by_text.lower() in row_text.lower():
                        target_row = row
                        break
                    # Also check cell text
                    for cell in row.descendants():
                        cell_text = cell.window_text() or cell.element_info.name or ""
                        if by_text.lower() in cell_text.lower():
                            target_row = row
                            break
                    if target_row:
                        break
                except Exception:
                    continue

        if target_row is None:
            raise ControlNotFoundError(
                f"Row matching {'index=' + str(by_index) if by_index is not None else 'text=' + repr(by_text)} "
                f"not found in control {control_id}"
            )

        method = "click_input"
        try:
            if hasattr(target_row, "select"):
                target_row.select()
                method = "uia_select"
            else:
                target_row.click_input()
        except Exception:
            try:
                target_row.click_input()
                method = "click_input"
            except Exception as exc:
                raise DesktopMCPError(f"Failed to select row: {exc}") from exc

        row_id = self._get_control_id(target_row)
        return {
            "control_id": control_id,
            "row_control_id": row_id,
            "method": method,
            "row_index": rows.index(target_row),
        }

    def click_cell(self, control_id: str, row: int, column: int) -> dict:
        """Click a specific cell in a DataGrid by zero-based row and column index."""
        self._check_platform()
        el = self._resolve_control(control_id)

        try:
            rows = [
                d for d in el.descendants()
                if d.element_info.control_type in ("DataItem", "Row")
            ]
        except Exception as exc:
            raise DesktopMCPError(f"Failed to enumerate rows: {exc}") from exc

        if row < 0 or row >= len(rows):
            raise ControlNotFoundError(
                f"Row {row} out of range (0–{len(rows) - 1})"
            )

        row_el = rows[row]
        try:
            cells = [
                c for c in row_el.descendants()
                if c.element_info.control_type in (
                    "DataItem", "Text", "Edit", "CheckBox", "Custom"
                )
            ]
        except Exception as exc:
            raise DesktopMCPError(f"Failed to enumerate cells: {exc}") from exc

        if column < 0 or column >= len(cells):
            raise ControlNotFoundError(
                f"Column {column} out of range (0–{len(cells) - 1})"
            )

        cell_el = cells[column]
        method = "click_input"
        try:
            if hasattr(cell_el, "invoke"):
                cell_el.invoke()
                method = "uia_invoke"
            else:
                cell_el.click_input()
        except Exception:
            try:
                cell_el.click_input()
                method = "click_input"
            except Exception as exc:
                raise DesktopMCPError(f"Failed to click cell: {exc}") from exc

        cell_id = self._get_control_id(cell_el)
        return {
            "control_id": control_id,
            "cell_control_id": cell_id,
            "row": row,
            "column": column,
            "method": method,
        }

    def read_cell(self, control_id: str, row: int, column: int) -> dict:
        """Read the text value of a specific cell in a DataGrid."""
        self._check_platform()
        el = self._resolve_control(control_id)

        try:
            rows = [
                d for d in el.descendants()
                if d.element_info.control_type in ("DataItem", "Row")
            ]
        except Exception as exc:
            raise DesktopMCPError(f"Failed to enumerate rows: {exc}") from exc

        if row < 0 or row >= len(rows):
            raise ControlNotFoundError(f"Row {row} out of range (0–{len(rows) - 1})")

        row_el = rows[row]
        try:
            cells = [
                c for c in row_el.descendants()
                if c.element_info.control_type in (
                    "DataItem", "Text", "Edit", "CheckBox", "Custom"
                )
            ]
        except Exception as exc:
            raise DesktopMCPError(f"Failed to enumerate cells: {exc}") from exc

        if column < 0 or column >= len(cells):
            raise ControlNotFoundError(
                f"Column {column} out of range (0–{len(cells) - 1})"
            )

        cell_el = cells[column]
        value = ""
        try:
            if hasattr(cell_el, "get_value"):
                value = cell_el.get_value() or ""
            if not value:
                value = cell_el.window_text() or cell_el.element_info.name or ""
        except Exception:
            pass

        return {
            "control_id": control_id,
            "row": row,
            "column": column,
            "value": value,
        }

    def read_tree(self, control_id: str, max_depth: int = 4) -> dict:
        """Read a TreeView control as a nested dict structure.

        Returns ``{"nodes": [...], "node_count": N}`` where each node has
        ``name``, ``control_id``, ``expanded``, and ``children``.
        """
        self._check_platform()
        el = self._resolve_control(control_id)

        def _read_node(element: Any, depth: int) -> dict:
            node_id = self._get_control_id(element)
            self._controls_cache[node_id] = element
            name = element.element_info.name or element.window_text() or ""
            expanded = False
            try:
                if hasattr(element, "is_expanded"):
                    expanded = bool(element.is_expanded())
            except Exception:
                pass

            children_nodes = []
            if depth < max_depth:
                try:
                    for child in element.children():
                        if child.element_info.control_type in (
                            "TreeItem", "TreeViewItem"
                        ):
                            children_nodes.append(_read_node(child, depth + 1))
                except Exception:
                    pass

            return {
                "name": name,
                "control_id": node_id,
                "expanded": expanded,
                "children": children_nodes,
            }

        nodes = []
        try:
            for child in el.children():
                if child.element_info.control_type in ("TreeItem", "TreeViewItem"):
                    nodes.append(_read_node(child, 0))
        except Exception as exc:
            raise DesktopMCPError(f"Failed to read tree: {exc}") from exc

        def _count(node_list: list) -> int:
            total = 0
            for n in node_list:
                total += 1 + _count(n["children"])
            return total

        return {"nodes": nodes, "node_count": _count(nodes)}

    # ------------------------------------------------------------------
    # Phase 4.3 — list_dialogs
    # ------------------------------------------------------------------

    def list_dialogs(self, application_id: str) -> list[dict]:
        """Return modal/popup windows owned by *application_id*.

        A dialog is any top-level window whose owner is a window belonging
        to the same process, or whose style includes WS_POPUP / WS_DLGFRAME.
        """
        self._check_platform()
        try:
            pid = (
                int(application_id.split("_")[1])
                if "_" in application_id
                else int(application_id)
            )
        except (ValueError, IndexError) as exc:
            raise DesktopMCPError(
                f"Invalid application_id: {application_id}"
            ) from exc

        dialogs = []
        try:
            desktop = PyWinDesktop(backend="uia")
            for win in desktop.windows():
                try:
                    win_pid = win.process_id()
                    if win_pid != pid:
                        continue
                    title = win.window_text() or ""
                    handle = win.handle
                    window_id = f"win_{handle}"

                    # Heuristic: dialog if it has a small bounding rect or
                    # a title that suggests a dialog (OK/Cancel/Error/Warning)
                    is_dialog = False
                    try:
                        rect = win.rectangle()
                        w, h = rect.width(), rect.height()
                        # Small window relative to typical app window
                        if 0 < w < 800 and 0 < h < 600:
                            is_dialog = True
                        # Or check WS_POPUP style via GetWindowLong
                        if win32gui and ctypes_mod:
                            GWL_STYLE = -16
                            WS_POPUP = 0x80000000
                            style = ctypes_mod.windll.user32.GetWindowLongW(
                                handle, GWL_STYLE
                            )
                            if style & WS_POPUP:
                                is_dialog = True
                    except Exception:
                        pass

                    if is_dialog:
                        dialogs.append({
                            "window_id": window_id,
                            "title": title,
                            "application_id": application_id,
                        })
                except Exception:
                    continue
        except Exception as exc:
            raise DesktopMCPError(f"Failed to list dialogs: {exc}") from exc

        return dialogs

    # ------------------------------------------------------------------
    # Phase 4.4 — get_foreground_window, get_focused_control, health_check
    # ------------------------------------------------------------------

    def get_foreground_window(self) -> dict:
        """Return the window_id and title of the current foreground window."""
        self._check_platform()
        hwnd = _get_foreground_hwnd()
        title = _get_foreground_title()
        window_id = f"win_{hwnd}" if hwnd else ""
        return {
            "window_id": window_id,
            "hwnd": hwnd,
            "title": title,
        }

    def get_focused_control(self, window_id: str) -> dict:
        """Return the control that currently has keyboard focus in *window_id*.

        Uses ``GetFocusedElement`` from the UIA automation object.
        Falls back to scanning the control tree for ``focused=True``.
        """
        self._check_platform()
        try:
            win_wrapper = self._resolve_window(window_id)
            # Try UIA GetFocusedElement via pywinauto
            try:
                focused = win_wrapper.get_focus()
                if focused:
                    ctrl = self._map_control(focused)
                    return {
                        "window_id": window_id,
                        "control_id": ctrl.id,
                        "name": ctrl.name,
                        "type": ctrl.type,
                        "automation_id": ctrl.automation_id,
                    }
            except Exception:
                pass

            # Fallback: scan tree for focused=True
            try:
                win = self.get_window(window_id)
                flat: list[Control] = []

                def _flatten(ctrls: list[Control]) -> None:
                    for c in ctrls:
                        flat.append(c)
                        _flatten(c.children)

                _flatten(win.controls)
                for ctrl in flat:
                    if ctrl.focused:
                        return {
                            "window_id": window_id,
                            "control_id": ctrl.id,
                            "name": ctrl.name,
                            "type": ctrl.type,
                            "automation_id": ctrl.automation_id,
                        }
            except Exception:
                pass

            return {
                "window_id": window_id,
                "control_id": None,
                "name": None,
                "type": None,
                "automation_id": None,
            }
        except WindowNotFoundError:
            raise
        except Exception as exc:
            raise DesktopMCPError(
                f"Failed to get focused control for {window_id}: {exc}"
            ) from exc

    def health_check(self) -> dict:
        """Return diagnostic information about the MCP server environment.

        Includes: Windows version, DPI awareness, UIA availability,
        parent PID chain (so the agent knows what to exclude from clicks),
        and library versions.
        """
        self._check_platform()
        import platform

        result: dict = {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "uia_available": PyWinApplication is not None,
            "parent_pid": os.getppid(),
            "mcp_pid": os.getpid(),
            "libraries": {},
            "dpi_awareness": None,
            "foreground_window": None,
        }

        # Library versions
        try:
            import pywinauto
            result["libraries"]["pywinauto"] = pywinauto.__version__
        except Exception:
            result["libraries"]["pywinauto"] = "unavailable"

        try:
            import comtypes
            result["libraries"]["comtypes"] = comtypes.__version__
        except Exception:
            result["libraries"]["comtypes"] = "unavailable"

        try:
            if psutil:
                result["libraries"]["psutil"] = psutil.__version__
        except Exception:
            result["libraries"]["psutil"] = "unavailable"

        # DPI awareness
        try:
            if ctypes_mod:
                awareness = ctypes_mod.windll.user32.GetAwarenessFromDpiAwarenessContext(
                    ctypes_mod.windll.user32.GetThreadDpiAwarenessContext()
                )
                result["dpi_awareness"] = awareness
        except Exception:
            pass

        # Current foreground window
        try:
            result["foreground_window"] = self.get_foreground_window()
        except Exception:
            pass

        # Parent PID chain (so agent knows what to exclude)
        try:
            if psutil:
                chain = []
                proc = psutil.Process(os.getpid())
                while proc is not None:
                    chain.append({"pid": proc.pid, "name": proc.name()})
                    try:
                        proc = proc.parent()
                    except Exception:
                        break
                result["pid_chain"] = chain
        except Exception:
            result["pid_chain"] = []

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
            return win.wrapper_object()
        except Exception:
            pass

        try:
            app = PyWinApplication(backend="uia").connect(handle=handle)
            win = app.window(handle=handle)
            return win.wrapper_object()
        except Exception as exc:
            raise WindowNotFoundError(f"Window not found: {window_id}") from exc

    def _resolve_control(self, control_id: str) -> Any:
        if control_id in self._controls_cache:
            try:
                _ = self._controls_cache[control_id].element_info.name
                return self._controls_cache[control_id]
            except Exception:
                del self._controls_cache[control_id]

        def should_skip_window(win) -> bool:
            try:
                title = (win.window_text() or "").lower()
                for pattern in (
                    "visual studio code", " - cursor", "cmd.exe",
                    "powershell.exe", "terminal",
                ):
                    if pattern in title:
                        return True
            except Exception:
                pass
            return False

        desktop = PyWinDesktop(backend="uia")
        active_handle = None

        try:
            active_win = desktop.active()
            active_handle = active_win.handle
            if not should_skip_window(active_win):
                for desc in active_win.descendants():
                    desc_id = self._get_control_id(desc)
                    self._controls_cache[desc_id] = desc
                    if desc_id == control_id:
                        return desc
        except Exception:
            pass

        for win in desktop.windows():
            try:
                if active_handle and win.handle == active_handle:
                    continue
            except Exception:
                pass
            if should_skip_window(win):
                continue
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
            if hasattr(element, "expand") or hasattr(element, "collapse"):
                patterns.append("ExpandCollapsePattern")
            if hasattr(element, "scroll_into_view"):
                patterns.append("ScrollItemPattern")
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
