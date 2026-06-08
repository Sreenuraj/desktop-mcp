#!/usr/bin/env python3
import sys
import time
import threading
import importlib

# Try to import tkinter globally for method scoping
try:
    import tkinter as tk
    from tkinter import scrolledtext
except ImportError:
    tk = None
    scrolledtext = None

# List of window titles to ignore during recording (to prevent logging IDE/terminal noise)
IGNORE_WINDOW_PATTERNS = [
    "visual studio code",
    " - cursor",
    "cmd.exe",
    "powershell.exe",
    "terminal",
    "taskbar",
    "program manager",
]


class RecorderUI:
    """Lightweight Tkinter-based dark-mode UI overlay for the recorder."""
    def __init__(self):
        self.root = None
        self.text_area = None
        self.status_lbl = None
        self.pause_btn = None
        self.transcript = []
        self.paused = False

    def start(self, on_close_callback) -> bool:
        if tk is None or scrolledtext is None:
            print("Warning: Tkinter not available, running in pure console mode.")
            return False

        self.root = tk.Tk()
        self.root.title("Desktop MCP - Action Recorder")
        self.root.geometry("480x450")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e2e")

        # Header
        header = tk.Frame(self.root, bg="#313244", pady=10)
        header.pack(fill=tk.X)

        self.status_lbl = tk.Label(
            header, text="● Recording", fg="#f38ba8", bg="#313244",
            font=("Segoe UI", 11, "bold")
        )
        self.status_lbl.pack(side=tk.LEFT, padx=15)

        subtitle = tk.Label(
            header, text="Float Window (Always on Top)", fg="#a6adc8", bg="#313244",
            font=("Segoe UI", 9)
        )
        subtitle.pack(side=tk.RIGHT, padx=15)

        # Scrolled Text Box
        self.text_area = scrolledtext.ScrolledText(
            self.root, wrap=tk.WORD, bg="#181825", fg="#cdd6f4",
            insertbackground="white", font=("Consolas", 10), bd=0,
            highlightthickness=0
        )
        self.text_area.pack(padx=12, pady=12, fill=tk.BOTH, expand=True)
        self.text_area.insert(tk.END, "Waiting for user interactions...\n")
        self.text_area.configure(state=tk.DISABLED)

        # Footer Button Panel
        btn_frame = tk.Frame(self.root, bg="#1e1e2e")
        btn_frame.pack(fill=tk.X, pady=8)

        copy_btn = tk.Button(
            btn_frame, text="Copy Transcript", bg="#89b4fa", fg="#11111b",
            activebackground="#b4befe", font=("Segoe UI", 9, "bold"),
            command=self.copy_transcript, bd=0, padx=12, pady=6
        )
        copy_btn.pack(side=tk.LEFT, padx=15)

        self.pause_btn = tk.Button(
            btn_frame, text="Pause", bg="#f9e2af", fg="#11111b",
            activebackground="#b4befe", font=("Segoe UI", 9, "bold"),
            command=self.toggle_pause, bd=0, padx=12, pady=6
        )
        self.pause_btn.pack(side=tk.LEFT, padx=15)

        clear_btn = tk.Button(
            btn_frame, text="Clear Logs", bg="#45475a", fg="#cdd6f4",
            activebackground="#585b70", font=("Segoe UI", 9),
            command=self.clear_transcript, bd=0, padx=12, pady=6
        )
        clear_btn.pack(side=tk.RIGHT, padx=15)

        self.root.protocol("WM_DELETE_WINDOW", on_close_callback)
        self.root.mainloop()
        return True

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        if self.paused:
            if self.pause_btn:
                self.pause_btn.configure(text="Resume", bg="#a6e3a1")
            if self.status_lbl:
                self.status_lbl.configure(text="Paused", fg="#f9e2af")
            self.log_action("[System] Recording Paused.")
        else:
            if self.pause_btn:
                self.pause_btn.configure(text="Pause", bg="#f9e2af")
            if self.status_lbl:
                self.status_lbl.configure(text="● Recording", fg="#f38ba8")
            self.log_action("[System] Recording Resumed.")

    def log_action(self, text: str) -> None:
        print(text)  # Also print to terminal stdout
        if not self.root:
            return

        def _update():
            self.transcript.append(text)
            self.text_area.configure(state=tk.NORMAL)
            self.text_area.insert(tk.END, text + "\n")
            self.text_area.see(tk.END)
            self.text_area.configure(state=tk.DISABLED)

        self.root.after(0, _update)

    def copy_transcript(self) -> None:
        if not self.root:
            return
        content = "\n".join(self.transcript)
        self.root.clipboard_clear()
        self.root.clipboard_append(content)

    def clear_transcript(self) -> None:
        self.transcript.clear()
        if self.text_area:
            self.text_area.configure(state=tk.NORMAL)
            self.text_area.delete("1.0", tk.END)
            self.text_area.configure(state=tk.DISABLED)


def run_windows_recorder(target_app: str = None) -> None:
    try:
        uiawrapper = importlib.import_module("pywinauto.controls.uiawrapper")
        uia_defines = importlib.import_module("pywinauto.uia_defines")
        pywin_desktop = importlib.import_module("pywinauto")
        win32api = importlib.import_module("win32api")
        win32gui = importlib.import_module("win32gui")
        UIAWrapper = uiawrapper.UIAWrapper
        IUIA = uia_defines.IUIA
        Desktop = pywin_desktop.Desktop
    except ImportError as exc:
        print(f"Error: Missing required Windows dependencies. Please install with 'pip install -e .[windows]'\nDetail: {exc}")
        sys.exit(1)

    print("====================================================")
    print("      Desktop MCP - Action Recorder")
    print("====================================================")
    print("Launch status: Listening to active Windows UIA events.")

    uia_instance = IUIA()
    desktop_instance = Desktop(backend="uia")
    last_runtime_id = None
    last_window_handle = None
    text_buffer = {}
    stop_event = threading.Event()
    ui = RecorderUI()

    def polling_loop():
        # Initialize COM on background thread
        try:
            pythoncom = importlib.import_module("pythoncom")
            pythoncom.CoInitialize()
        except Exception:
            pass

        nonlocal last_runtime_id, last_window_handle
        last_mouse_down = False

        while not stop_event.is_set():
            time.sleep(0.05)  # 50ms polling for responsive click/focus tracking

            if ui.paused:
                # Still track mouse state to avoid logging the click on the "Resume" button itself
                try:
                    mouse_state = win32api.GetAsyncKeyState(0x01)
                    last_mouse_down = bool(mouse_state & 0x8000)
                except Exception:
                    pass
                continue

            # 1. Check for Mouse Click
            try:
                mouse_state = win32api.GetAsyncKeyState(0x01)  # Left Mouse Button
                is_mouse_down = bool(mouse_state & 0x8000)
            except Exception:
                is_mouse_down = False

            click_detected = is_mouse_down and not last_mouse_down
            last_mouse_down = is_mouse_down

            clicked_el_logged = False
            if click_detected:
                try:
                    x, y = win32gui.GetCursorPos()
                    raw_click_el = desktop_instance.from_point(x, y)
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

                        if not should_ignore:
                            if win_handle != last_window_handle:
                                last_window_handle = win_handle
                                ui.log_action(f"\n[Window] Focus shifted to: '{win_title}' (HWND: {win_handle})")

                            if click_control_type == "Button":
                                ui.log_action(f"  -> Clicked Button: '{click_name}' (auto_id='{click_auto_id}')")
                                clicked_el_logged = True
                            elif click_control_type == "MenuItem":
                                ui.log_action(f"  -> Selected Menu Item: '{click_name}' (auto_id='{click_auto_id}')")
                                clicked_el_logged = True
                            elif click_control_type == "CheckBox":
                                try:
                                    state = "Checked" if raw_click_el.is_checked() else "Unchecked"
                                except Exception:
                                    state = "Toggled"
                                ui.log_action(f"  -> CheckBox: '{click_name}' (auto_id='{click_auto_id}') -> {state}")
                                clicked_el_logged = True
                            elif click_control_type in ("Edit", "Document"):
                                # Let standard focus loop handle text box typing/buffering
                                pass
                            elif click_control_type == "ComboBox":
                                try:
                                    val = raw_click_el.get_value() or ""
                                except Exception:
                                    val = ""
                                ui.log_action(f"  -> ComboBox: '{click_name}' (auto_id='{click_auto_id}') selection: '{val}'")
                                clicked_el_logged = True
                            else:
                                if click_name or click_auto_id:
                                    ui.log_action(f"  -> Clicked Element: {click_control_type} '{click_name}' (auto_id='{click_auto_id}')")
                                    clicked_el_logged = True

                            if clicked_el_logged:
                                last_runtime_id = click_runtime_id
                except Exception:
                    pass

            # 2. Check for Keyboard Focus Shifts
            try:
                raw_el = uia_instance.uia.GetFocusedElement()
                if not raw_el:
                    continue

                el = UIAWrapper(raw_el)
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

                if should_ignore:
                    continue

                if win_handle != last_window_handle:
                    last_window_handle = win_handle
                    ui.log_action(f"\n[Window] Focus shifted to: '{win_title}' (HWND: {win_handle})")

                if runtime_id != last_runtime_id:
                    if last_runtime_id in text_buffer:
                        edit_info = text_buffer.pop(last_runtime_id)
                        try:
                            val = edit_info["el"].get_value() or ""
                            if val:
                                ui.log_action(f"  -> Input Text: '{val}' into {edit_info['type']} '{edit_info['name']}' (auto_id='{edit_info['auto_id']}')")
                        except Exception:
                            pass

                    last_runtime_id = runtime_id

                    if not clicked_el_logged:
                        name = info.name or ""
                        control_type = info.control_type or ""
                        auto_id = info.automation_id or ""

                        if control_type == "Button":
                            ui.log_action(f"  -> Clicked Button: '{name}' (auto_id='{auto_id}')")
                        elif control_type == "MenuItem":
                            ui.log_action(f"  -> Selected Menu Item: '{name}' (auto_id='{auto_id}')")
                        elif control_type == "CheckBox":
                            try:
                                state = "Checked" if el.is_checked() else "Unchecked"
                            except Exception:
                                state = "Toggled"
                            ui.log_action(f"  -> CheckBox: '{name}' (auto_id='{auto_id}') -> {state}")
                        elif control_type in ("Edit", "Document"):
                            text_buffer[runtime_id] = {
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
                            ui.log_action(f"  -> ComboBox: '{name}' (auto_id='{auto_id}') selection: '{val}'")
                        else:
                            if name or auto_id:
                                ui.log_action(f"  -> Focused Element: {control_type} '{name}' (auto_id='{auto_id}')")
            except Exception:
                pass

    # Start UIA listening thread
    record_thread = threading.Thread(target=polling_loop, daemon=True)
    record_thread.start()

    # If target app is specified, run setup logic (launch, minimize others, focus)
    if target_app:
        def setup_target_application(app_name: str) -> None:
            try:
                import time
                import subprocess

                # Wait briefly for Tkinter window to initialize
                time.sleep(0.5)

                # Find the target window
                target_hwnd = None
                for win in Desktop.windows():
                    title = win.window_text()
                    if title and app_name.lower() in title.lower():
                        target_hwnd = win.handle
                        break

                # Attempt launch if not running
                if not target_hwnd:
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
                            for win in Desktop.windows():
                                title = win.window_text()
                                if title and app_name.lower() in title.lower():
                                    target_hwnd = win.handle
                                    break
                            if target_hwnd:
                                break
                    except Exception as e:
                        print(f"Failed to launch target '{app_name}': {e}")

                if not target_hwnd:
                    print(f"Warning: Could not find or launch window matching '{app_name}'.")
                    return

                print(f"Target application active (HWND: {target_hwnd})")

                # Find our own recorder window
                recorder_hwnd = win32gui.FindWindow(None, "Desktop MCP - Action Recorder")

                # Enumerate and minimize other visible windows
                def enum_cb(hwnd, extra):
                    if hwnd == target_hwnd or hwnd == recorder_hwnd:
                        return True
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        cls = win32gui.GetClassName(hwnd)
                        if title and cls not in ("Shell_TrayWnd", "Progman", "Button"):
                            win32gui.ShowWindow(hwnd, 6)  # SW_MINIMIZE = 6
                    return True

                win32gui.EnumWindows(enum_cb, None)

                # Focus target application
                try:
                    win32gui.ShowWindow(target_hwnd, 9)  # SW_RESTORE = 9
                    win32gui.SetForegroundWindow(target_hwnd)
                except Exception as e:
                    print(f"Could not focus target window: {e}")

            except Exception as e:
                print(f"Error in target app setup: {e}")

        setup_thread = threading.Thread(target=lambda: setup_target_application(target_app), daemon=True)
        setup_thread.start()

    def on_close():
        stop_event.set()
        # Flush any remaining text buffer
        for r_id, edit_info in text_buffer.items():
            try:
                val = edit_info["el"].get_value() or ""
                if val:
                    print(f"  -> Input Text: '{val}' into {edit_info['type']} '{edit_info['name']}' (auto_id='{edit_info['auto_id']}')")
            except Exception:
                pass
        if ui.root:
            ui.root.destroy()
        sys.exit(0)

    try:
        # Start GUI main loop on main thread
        started = ui.start(on_close)
        if not started:
            print("Console Recording active. Press Ctrl+C to stop.")
            while not stop_event.is_set():
                time.sleep(0.5)
    except KeyboardInterrupt:
        on_close()


def run_mock_recorder() -> None:
    print("====================================================")
    print("      Desktop MCP - Action Recorder")
    print("====================================================")
    print("Running in simulated mode (macOS/Linux platform detected).")
    print("On a Windows machine with pywinauto, this recorder will hook")
    print("into UIA focus events and display a dark-mode floating UI.\n")
    print("Example recorded output:")
    print("[Window] Focus shifted to: 'Calculator'")
    print("  -> Clicked Button: 'Clear' (auto_id='clearButton')")
    print("  -> Clicked Button: 'Five' (auto_id='num5Button')")
    print("  -> Clicked Button: 'Multiply' (auto_id='multiplyButton')")
    print("  -> Clicked Button: 'Nine' (auto_id='num9Button')")
    print("  -> Clicked Button: 'Equals' (auto_id='equalButton')")
    print("\n[Window] Focus shifted to: 'Untitled - Notepad'")
    print("  -> Input Text: 'Hello DHCS' into Document 'Text Editor' (auto_id='15')")
    print("  -> Selected Menu Item: 'Exit' (auto_id='Exit')")
    print("====================================================")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Desktop MCP Interaction Recorder")
    parser.add_argument("--app", "-a", type=str, help="Target application name or path to launch and focus, minimizing others")
    args = parser.parse_args()

    if sys.platform == "win32":
        run_windows_recorder(target_app=args.app)
    else:
        run_mock_recorder()


if __name__ == "__main__":
    main()
