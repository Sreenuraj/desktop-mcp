"""OOP Recording Engine implementations for Desktop MCP Action Recorder."""

import sys
import time
import threading
import importlib

IGNORE_WINDOW_PATTERNS = [
    "visual studio code",
    " - cursor",
    "cmd.exe",
    "powershell.exe",
    "terminal",
    "taskbar",
    "program manager",
]


class BaseRecorderEngine:
    """Abstract Base Recorder Engine outlining UI linkages and platform hooks."""

    def __init__(self, ui):
        self.ui = ui
        self.stop_event = threading.Event()
        self.target_hwnd = None
        self.last_runtime_id = None
        self.last_window_handle = None
        self.text_buffer = {}

    def start(self, app_name, minimize_others):
        """Start the recording engine thread."""
        pass

    def stop(self):
        """Stop the recording engine loop."""
        self.stop_event.set()

    def get_windows_list(self):
        """Enumerate active/visible top-level windows."""
        return []

    def close_target_app(self):
        """Gracefully close the application under test."""
        pass


class MockRecorderEngine(BaseRecorderEngine):
    """Simulated platform recorder engine for testing on non-Windows platforms."""

    def get_windows_list(self):
        return [
            "Calculator",
            "Notepad",
            "Google Chrome",
            "Visual Studio Code",
            "System Settings",
            "Command Prompt"
        ]

    def start(self, app_name, minimize_others):
        print(f"Mock recording started for target: {app_name or 'Full Desktop'} (minimize={minimize_others})")

        def mock_generator():
            mock_events = [
                {"type": "focus_shift", "win_title": "Calculator", "win_handle": 2098032},
                {"type": "click", "control_type": "Button", "name": "Clear", "auto_id": "clearButton"},
                {"type": "click", "control_type": "Button", "name": "Five", "auto_id": "num5Button"},
                {"type": "click", "control_type": "Button", "name": "Multiply", "auto_id": "multiplyButton"},
                {"type": "click", "control_type": "Button", "name": "Nine", "auto_id": "num9Button"},
                {"type": "click", "control_type": "Button", "name": "Equals", "auto_id": "equalButton"},
                {"type": "focus_shift", "win_title": "Untitled - Notepad", "win_handle": 1234567},
                {"type": "input", "control_type": "Document", "name": "Text Editor", "auto_id": "15", "text": "Hello DHCS"},
                {"type": "click", "control_type": "MenuItem", "name": "Exit", "auto_id": "Exit"}
            ]
            for ev in mock_events:
                if self.stop_event.is_set():
                    break
                time.sleep(1.5)
                if not self.ui.paused:
                    self.ui.log_event(ev)

        gen_thread = threading.Thread(target=mock_generator, daemon=True)
        gen_thread.start()

    def close_target_app(self):
        print("[Mock] Graceful target application closure requested.")
        self.ui.log_event({"type": "system", "text": "Mock target application closed gracefully."})


class WindowsRecorderEngine(BaseRecorderEngine):
    """Windows UIA-native recording engine using pywinauto and win32 hooks."""

    def __init__(self, ui):
        super().__init__(ui)
        self.uiawrapper = None
        self.uia_defines = None
        self.pywin_desktop = None
        self.win32api = None
        self.win32gui = None
        self.win32con = None
        self.UIAWrapper = None
        self.IUIA = None
        self.Desktop = None
        self.uia_instance = None
        self.desktop_instance = None

    def load_dependencies(self) -> bool:
        if self.uia_instance is not None:
            return True

        try:
            self.uiawrapper = importlib.import_module("pywinauto.controls.uiawrapper")
            self.uia_defines = importlib.import_module("pywinauto.uia_defines")
            self.pywin_desktop = importlib.import_module("pywinauto")
            self.win32api = importlib.import_module("win32api")
            self.win32gui = importlib.import_module("win32gui")
            self.win32con = importlib.import_module("win32con")

            self.UIAWrapper = self.uiawrapper.UIAWrapper
            self.IUIA = self.uia_defines.IUIA
            self.Desktop = self.pywin_desktop.Desktop
            self.uia_instance = self.IUIA()
            self.desktop_instance = self.Desktop(backend="uia")
            return True
        except ImportError as exc:
            print(f"Error: Missing required Windows dependencies ({exc}).")
            try:
                choice = input("Would you like to install the required dependencies automatically now? (y/n) [y]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                choice = 'n'

            if choice != 'n':
                print("Installing dependencies...")
                import subprocess
                import os

                script_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
                pyproject_path = os.path.join(project_root, "pyproject.toml")

                if os.path.exists(pyproject_path):
                    cmd = [sys.executable, "-m", "pip", "install", "-e", f"{project_root}[windows]"]
                else:
                    cmd = [sys.executable, "-m", "pip", "install", "pywinauto>=0.6.8", "pywin32>=306", "comtypes>=1.2", "psutil>=5.9", "mss>=9.0", "Pillow>=10.0"]

                try:
                    subprocess.check_call(cmd)
                    print("\nDependencies installed successfully! Please restart the script to run the recorder.")
                    sys.exit(0)
                except Exception as e:
                    print(f"Failed to install dependencies automatically: {e}")
                    print("Please run manually: pip install -e .[windows]")
                    sys.exit(1)
            else:
                print("Please install the dependencies manually: pip install -e .[windows]")
                sys.exit(1)

    def start(self, app_name, minimize_others):
        self.load_dependencies()

        print("====================================================")
        print("      Desktop MCP - Action Recorder")
        print("====================================================")
        print("Launch status: Listening to active Windows UIA events.")

        # Start UIA listening thread
        record_thread = threading.Thread(target=self.polling_loop, daemon=True)
        record_thread.start()

        if app_name:
            setup_thread = threading.Thread(target=lambda: self.setup_target_application(app_name, minimize_others), daemon=True)
            setup_thread.start()

    def polling_loop(self):
        # Initialize COM on background thread
        try:
            pythoncom = importlib.import_module("pythoncom")
            pythoncom.CoInitialize()
        except Exception:
            pass

        last_mouse_down = False

        while not self.stop_event.is_set():
            time.sleep(0.05)  # 50ms polling for responsive click/focus tracking

            if self.ui.paused:
                # Still track mouse state to avoid logging the click on the "Resume" button itself
                try:
                    mouse_state = self.win32api.GetAsyncKeyState(0x01)
                    last_mouse_down = bool(mouse_state & 0x8000)
                except Exception:
                    pass
                continue

            # 1. Check for Mouse Click
            try:
                mouse_state = self.win32api.GetAsyncKeyState(0x01)  # Left Mouse Button
                is_mouse_down = bool(mouse_state & 0x8000)
            except Exception:
                is_mouse_down = False

            click_detected = is_mouse_down and not last_mouse_down
            last_mouse_down = is_mouse_down

            clicked_el_logged = False
            if click_detected:
                try:
                    x, y = self.win32gui.GetCursorPos()
                    raw_click_el = self.desktop_instance.from_point(x, y)
                    if raw_click_el:
                        click_info = raw_click_el.element_info
                        click_runtime_id = click_info.runtime_id
                        click_name = click_info.name or ""
                        click_control_type = click_info.control_type or ""
                        click_auto_id = click_info.automation_id or ""

                        try:
                            parent_win = raw_click_el.top_level_parent()
                            win_title = parent_win.element_info.name or ""
                            win_handle = parent_win.handle
                        except Exception:
                            win_title = ""
                            win_handle = None

                        should_ignore = False
                        win_title_lower = win_title.lower()
                        for pattern in IGNORE_WINDOW_PATTERNS:
                            if pattern in win_title_lower:
                                should_ignore = True
                                break

                        # Target check
                        is_target = False
                        if not self.ui.target_app:
                            is_target = True
                        else:
                            if self.target_hwnd and win_handle == self.target_hwnd:
                                is_target = True
                            elif win_title and self.ui.target_app.lower() in win_title.lower():
                                is_target = True

                        if win_handle != self.last_window_handle:
                            self.last_window_handle = win_handle
                            if not should_ignore and is_target:
                                self.ui.log_event({
                                    "type": "focus_shift",
                                    "win_title": win_title,
                                    "win_handle": win_handle
                                })

                        if not should_ignore and is_target:
                            if click_control_type == "Button":
                                self.ui.log_event({
                                    "type": "click",
                                    "control_type": "Button",
                                    "name": click_name,
                                    "auto_id": click_auto_id
                                })
                                clicked_el_logged = True
                            elif click_control_type == "MenuItem":
                                self.ui.log_event({
                                    "type": "click",
                                    "control_type": "MenuItem",
                                    "name": click_name,
                                    "auto_id": click_auto_id
                                })
                                clicked_el_logged = True
                            elif click_control_type == "CheckBox":
                                try:
                                    state = "Checked" if raw_click_el.is_checked() else "Unchecked"
                                except Exception:
                                    state = "Toggled"
                                self.ui.log_event({
                                    "type": "checkbox",
                                    "name": click_name,
                                    "auto_id": click_auto_id,
                                    "state": state
                                })
                                clicked_el_logged = True
                            elif click_control_type in ("Edit", "Document"):
                                # Let standard focus loop handle text box typing/buffering
                                pass
                            elif click_control_type == "ComboBox":
                                try:
                                    val = raw_click_el.get_value() or ""
                                except Exception:
                                    val = ""
                                self.ui.log_event({
                                    "type": "combobox",
                                    "name": click_name,
                                    "auto_id": click_auto_id,
                                    "value": val
                                })
                                clicked_el_logged = True
                            else:
                                if click_name or click_auto_id:
                                    self.ui.log_event({
                                        "type": "click",
                                        "control_type": click_control_type,
                                        "name": click_name,
                                        "auto_id": click_auto_id
                                    })
                                    clicked_el_logged = True

                            if clicked_el_logged:
                                self.last_runtime_id = click_runtime_id
                except Exception:
                    pass

            # 2. Check for Keyboard Focus Shifts
            try:
                raw_el = self.uia_instance.uia.GetFocusedElement()
                if not raw_el:
                    continue

                el = self.UIAWrapper(raw_el)
                info = el.element_info
                runtime_id = info.runtime_id

                try:
                    parent_win = el.top_level_parent()
                    win_handle = parent_win.handle
                    win_title = parent_win.element_info.name or ""
                except Exception:
                    win_handle = None
                    win_title = ""

                should_ignore = False
                win_title_lower = win_title.lower()
                for pattern in IGNORE_WINDOW_PATTERNS:
                    if pattern in win_title_lower:
                        should_ignore = True
                        break

                # Target check
                is_target = False
                if not self.ui.target_app:
                    is_target = True
                else:
                    if self.target_hwnd and win_handle == self.target_hwnd:
                        is_target = True
                    elif win_title and self.ui.target_app.lower() in win_title.lower():
                        is_target = True

                # Flush input text buffer immediately when focus shifts to another element
                if runtime_id != self.last_runtime_id:
                    if self.last_runtime_id in self.text_buffer:
                        edit_info = self.text_buffer.pop(self.last_runtime_id)
                        try:
                            val = edit_info["el"].get_value() or ""
                            if val:
                                self.ui.log_event({
                                    "type": "input",
                                    "control_type": edit_info["type"],
                                    "name": edit_info["name"],
                                    "auto_id": edit_info["auto_id"],
                                    "text": val
                                })
                        except Exception:
                            pass
                    self.last_runtime_id = runtime_id

                    # Only capture focus and inputs if target
                    if not should_ignore and is_target:
                        if not clicked_el_logged:
                            name = info.name or ""
                            control_type = info.control_type or ""
                            auto_id = info.automation_id or ""

                            if control_type == "Button":
                                self.ui.log_event({
                                    "type": "click",
                                    "control_type": "Button",
                                    "name": name,
                                    "auto_id": auto_id
                                })
                            elif control_type == "MenuItem":
                                self.ui.log_event({
                                    "type": "click",
                                    "control_type": "MenuItem",
                                    "name": name,
                                    "auto_id": auto_id
                                })
                            elif control_type == "CheckBox":
                                try:
                                    state = "Checked" if el.is_checked() else "Unchecked"
                                except Exception:
                                    state = "Toggled"
                                self.ui.log_event({
                                    "type": "checkbox",
                                    "name": name,
                                    "auto_id": auto_id,
                                    "state": state
                                })
                            elif control_type in ("Edit", "Document"):
                                self.text_buffer[runtime_id] = {
                                    "el": el,
                                    "name": name,
                                    "type": control_type,
                                    "auto_id": auto_id
                                }
                            elif control_type == "ComboBox":
                                try:
                                    val = el.get_value() or ""
                                except Exception:
                                    val = ""
                                self.ui.log_event({
                                    "type": "combobox",
                                    "name": name,
                                    "auto_id": auto_id,
                                    "value": val
                                })
                            else:
                                if name or auto_id:
                                    self.ui.log_event({
                                        "type": "click",
                                        "control_type": control_type,
                                        "name": name,
                                        "auto_id": auto_id
                                    })

                if win_handle != self.last_window_handle:
                    self.last_window_handle = win_handle
                    if not should_ignore and is_target:
                        self.ui.log_event({
                            "type": "focus_shift",
                            "win_title": win_title,
                            "win_handle": win_handle
                        })

            except Exception:
                pass

    def setup_target_application(self, app_name: str, minimize_others: bool = True) -> None:
        try:
            import os
            import subprocess

            # Wait briefly for Tkinter window to initialize
            time.sleep(0.5)

            # Try to get clean name if it is a path
            clean_name = os.path.basename(app_name)
            if clean_name.lower().endswith(".exe"):
                clean_name = clean_name[:-4]

            # Find the target window
            for win in self.Desktop.windows():
                title = win.window_text()
                if title and (app_name.lower() in title.lower() or clean_name.lower() in title.lower()):
                    self.target_hwnd = win.handle
                    break

            # Attempt launch if not running
            if not self.target_hwnd:
                print(f"Target application window matching '{app_name}' not found. Launching...")
                try:
                    cmd = app_name
                    if app_name.lower() in ("notepad", "notepad.exe"):
                        cmd = "notepad.exe"
                    elif app_name.lower() in ("calc", "calculator", "calc.exe"):
                        cmd = "calc.exe"

                    subprocess.Popen(cmd, shell=True)
                    for _ in range(50):
                        time.sleep(0.1)
                        for win in self.Desktop.windows():
                            title = win.window_text()
                            if title and (app_name.lower() in title.lower() or clean_name.lower() in title.lower()):
                                self.target_hwnd = win.handle
                                break
                        if self.target_hwnd:
                            break
                except Exception as e:
                    print(f"Failed to launch target '{app_name}': {e}")

            if not self.target_hwnd:
                print(f"Warning: Could not find or launch window matching '{app_name}'.")
                return

            print(f"Target application active (HWND: {self.target_hwnd})")

            # Find our own recorder window
            recorder_hwnd = self.win32gui.FindWindow(None, "Desktop MCP - Action Recorder")

            # Enumerate and minimize other visible windows
            if minimize_others:
                def enum_cb(hwnd, extra):
                    if hwnd == self.target_hwnd or hwnd == recorder_hwnd:
                        return True
                    if self.win32gui.IsWindowVisible(hwnd):
                        title = self.win32gui.GetWindowText(hwnd)
                        cls = self.win32gui.GetClassName(hwnd)
                        if title and cls not in ("Shell_TrayWnd", "Progman", "Button"):
                            self.win32gui.ShowWindow(hwnd, 6)  # SW_MINIMIZE = 6
                    return True

                self.win32gui.EnumWindows(enum_cb, None)

            # Focus target application
            try:
                self.win32gui.ShowWindow(self.target_hwnd, 9)  # SW_RESTORE = 9
                self.win32gui.SetForegroundWindow(self.target_hwnd)
            except Exception as e:
                print(f"Could not focus target window: {e}")

        except Exception as e:
            print(f"Error in target app setup: {e}")

    def get_windows_list(self) -> list[str]:
        self.load_dependencies()
        try:
            titles = []
            for win in self.Desktop.windows():
                title = win.window_text()
                if title:
                    titles.append(title)

            # Supplement with win32gui to ensure all visible windows are listed
            try:
                def enum_visible_cb(hwnd, extra):
                    if self.win32gui.IsWindowVisible(hwnd):
                        title = self.win32gui.GetWindowText(hwnd)
                        if title and title not in IGNORE_WINDOW_PATTERNS:
                            titles.append(title)
                    return True
                self.win32gui.EnumWindows(enum_visible_cb, None)
            except Exception:
                pass

            return sorted(list(set(titles)))
        except Exception:
            return []

    def close_target_app(self):
        if self.target_hwnd:
            try:
                print(f"Closing target application (HWND: {self.target_hwnd}) gracefully via WM_CLOSE...")
                self.win32gui.PostMessage(self.target_hwnd, self.win32con.WM_CLOSE, 0, 0)
            except Exception as e:
                print(f"Error closing target application gracefully: {e}")
                try:
                    from pywinauto import Application  # type: ignore
                    Application().connect(handle=self.target_hwnd).kill()
                except Exception as e2:
                    print(f"Failed fallback target application kill: {e2}")
