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
        self.transcript = []

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

        status_lbl = tk.Label(
            header, text="● Recording", fg="#f38ba8", bg="#313244",
            font=("Segoe UI", 11, "bold")
        )
        status_lbl.pack(side=tk.LEFT, padx=15)

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

        clear_btn = tk.Button(
            btn_frame, text="Clear Logs", bg="#45475a", fg="#cdd6f4",
            activebackground="#585b70", font=("Segoe UI", 9),
            command=self.clear_transcript, bd=0, padx=12, pady=6
        )
        clear_btn.pack(side=tk.RIGHT, padx=15)

        self.root.protocol("WM_DELETE_WINDOW", on_close_callback)
        self.root.mainloop()
        return True

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


def run_windows_recorder() -> None:
    try:
        uiawrapper = importlib.import_module("pywinauto.controls.uiawrapper")
        uia_defines = importlib.import_module("pywinauto.uia_defines")
        UIAWrapper = uiawrapper.UIAWrapper
        IUIA = uia_defines.IUIA
    except ImportError as exc:
        print(f"Error: Missing required Windows dependencies. Please install with 'pip install -e .[windows]'\nDetail: {exc}")
        sys.exit(1)

    print("====================================================")
    print("      Desktop MCP - Codegen Interaction Recorder     ")
    print("====================================================")
    print("Launch status: Listening to active Windows UIA events.")

    uia_instance = IUIA()
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
        while not stop_event.is_set():
            time.sleep(0.1)
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
    print("      Desktop MCP - Codegen Interaction Recorder     ")
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
    if sys.platform == "win32":
        run_windows_recorder()
    else:
        run_mock_recorder()


if __name__ == "__main__":
    main()
