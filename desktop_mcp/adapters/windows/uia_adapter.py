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
