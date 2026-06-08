#!/usr/bin/env python3
import sys
import time
import threading
import importlib

# Try to import tkinter globally for method scoping
try:
    import tkinter as tk
    from tkinter import scrolledtext, filedialog, ttk, messagebox
except ImportError:
    tk = None
    scrolledtext = None
    filedialog = None
    ttk = None
    messagebox = None

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
        self.line_num_area = None
        self.scrollbar = None
        self.status_lbl = None
        self.record_btn = None
        self.pause_btn = None
        self.events = []
        self.paused = False

        self.setup_frame = None
        self.recorder_frame = None

        self.target_app = None
        self.minimize_others = True
        self.on_recording_started_callback = None
        self.on_close_target_callback = None
        self.target_format = None
        self.target_closed = False

    def start(self, on_close_callback, target_app=None, window_list=None, on_recording_started_callback=None) -> bool:
        if tk is None or scrolledtext is None or ttk is None:
            print("Warning: Tkinter or ttk not available, running in pure console mode.")
            return False

        self.root = tk.Tk()
        self.root.title("Desktop MCP - Action Recorder")
        self.root.geometry("520x500")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e2e")
        self.root.protocol("WM_DELETE_WINDOW", on_close_callback)

        self.on_recording_started_callback = on_recording_started_callback

        if target_app:
            self.target_app = target_app
            self.show_recorder_screen()
            if self.on_recording_started_callback:
                self.on_recording_started_callback(self.target_app, self.minimize_others)
        else:
            self.show_setup_screen(window_list or [])

        self.root.mainloop()
        return True

    def show_setup_screen(self, window_list):
        self.setup_frame = tk.Frame(self.root, bg="#1e1e2e")
        self.setup_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Title
        title_lbl = tk.Label(
            self.setup_frame, text="Desktop MCP - Action Recorder", fg="#cdd6f4", bg="#1e1e2e",
            font=("Segoe UI", 14, "bold")
        )
        title_lbl.pack(pady=(10, 20))

        # Dropdown section
        drop_lbl = tk.Label(
            self.setup_frame, text="Select Target Application to Record:", fg="#a6adc8", bg="#1e1e2e",
            font=("Segoe UI", 10)
        )
        drop_lbl.pack(anchor=tk.W, pady=(5, 2))

        # Custom combobox autocompletion
        self.combo = ttk.Combobox(self.setup_frame, values=window_list, font=("Segoe UI", 10))
        self.combo.pack(fill=tk.X, pady=(0, 15))

        # Enable autocomplete filtering
        all_values = list(window_list)

        def on_keyrelease(event):
            if event.keysym in ("Up", "Down", "Left", "Right", "Return", "Escape", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"):
                return
            typed = self.combo.get()
            if not typed:
                self.combo['values'] = all_values
            else:
                filtered = [item for item in all_values if typed.lower() in item.lower()]
                self.combo['values'] = filtered
            try:
                self.combo.post()
            except Exception:
                pass

        self.combo.bind('<KeyRelease>', on_keyrelease)
        self.combo.bind('<FocusIn>', lambda e: self.combo.post())

        # Manual path section
        path_lbl = tk.Label(
            self.setup_frame, text="Or Enter Application Executable Path:", fg="#a6adc8", bg="#1e1e2e",
            font=("Segoe UI", 10)
        )
        path_lbl.pack(anchor=tk.W, pady=(5, 2))

        path_frame = tk.Frame(self.setup_frame, bg="#1e1e2e")
        path_frame.pack(fill=tk.X, pady=(0, 15))

        self.path_entry = tk.Entry(path_frame, font=("Segoe UI", 10), bg="#181825", fg="#cdd6f4", insertbackground="white", bd=1, relief=tk.FLAT)
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)

        def browse_file():
            if filedialog:
                path = filedialog.askopenfilename(
                    title="Select Application Executable",
                    filetypes=[("Executable Files", "*.exe"), ("All Files", "*.*")]
                )
                if path:
                    self.path_entry.delete(0, tk.END)
                    self.path_entry.insert(0, path)

        browse_btn = tk.Button(
            path_frame, text="Browse...", bg="#45475a", fg="#cdd6f4",
            activebackground="#585b70", font=("Segoe UI", 9),
            command=browse_file, bd=0, padx=10
        )
        browse_btn.pack(side=tk.RIGHT, padx=(10, 0))

        # Checkbox
        self.minimize_var = tk.BooleanVar(value=True)
        minimize_chk = tk.Checkbutton(
            self.setup_frame, text="Minimize other windows to avoid distraction",
            variable=self.minimize_var, fg="#cdd6f4", bg="#1e1e2e",
            selectcolor="#1e1e2e", activebackground="#1e1e2e", activeforeground="#cdd6f4",
            font=("Segoe UI", 9)
        )
        minimize_chk.pack(anchor=tk.W, pady=10)

        # Buttons Frame
        btn_frame = tk.Frame(self.setup_frame, bg="#1e1e2e")
        btn_frame.pack(fill=tk.X, pady=20)

        start_btn = tk.Button(
            btn_frame, text="Start Recording", bg="#a6e3a1", fg="#11111b",
            activebackground="#89b4fa", font=("Segoe UI", 10, "bold"),
            command=self.on_start_click, bd=0, padx=20, pady=8
        )
        start_btn.pack(side=tk.LEFT)

        desktop_btn = tk.Button(
            btn_frame, text="Record Full Desktop (No Target)", bg="#45475a", fg="#cdd6f4",
            activebackground="#585b70", font=("Segoe UI", 10),
            command=self.on_desktop_click, bd=0, padx=20, pady=8
        )
        desktop_btn.pack(side=tk.RIGHT)

    def on_start_click(self):
        selected_app = self.combo.get().strip()
        selected_path = self.path_entry.get().strip()
        self.minimize_others = self.minimize_var.get()

        self.target_app = selected_path if selected_path else selected_app
        self.setup_frame.destroy()

        self.show_recorder_screen()
        if self.on_recording_started_callback:
            self.on_recording_started_callback(self.target_app, self.minimize_others)

    def on_desktop_click(self):
        self.target_app = None
        self.minimize_others = False
        self.setup_frame.destroy()

        self.show_recorder_screen()
        if self.on_recording_started_callback:
            self.on_recording_started_callback(None, False)

    def show_recorder_screen(self):
        self.recorder_frame = tk.Frame(self.root, bg="#1e1e2e")
        self.recorder_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        header = tk.Frame(self.recorder_frame, bg="#313244", pady=10)
        header.pack(fill=tk.X, side=tk.TOP)

        self.status_lbl = tk.Label(
            header, text="● Recording", fg="#f38ba8", bg="#313244",
            font=("Segoe UI", 11, "bold")
        )
        self.status_lbl.pack(side=tk.LEFT, padx=15)

        app_display = f"Target: {self.target_app[:25]}..." if self.target_app else "Full Desktop"
        subtitle = tk.Label(
            header, text=app_display, fg="#a6adc8", bg="#313244",
            font=("Segoe UI", 9)
        )
        subtitle.pack(side=tk.RIGHT, padx=15)

        # Toolbar Frame
        toolbar = tk.Frame(self.recorder_frame, bg="#252538", pady=6)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        # Record Button (Toggle)
        self.record_btn = tk.Button(
            toolbar, text="● Record", bg="#1e1e2e", fg="#f38ba8",
            activebackground="#45475a", activeforeground="#f38ba8",
            font=("Segoe UI", 9, "bold"), command=self.toggle_record,
            bd=0, padx=10, pady=4, relief=tk.FLAT
        )
        self.record_btn.pack(side=tk.LEFT, padx=(10, 5))

        # Pause Button
        self.pause_btn = tk.Button(
            toolbar, text="⏸ Pause", bg="#1e1e2e", fg="#f9e2af",
            activebackground="#45475a", activeforeground="#f9e2af",
            font=("Segoe UI", 9, "bold"), command=self.toggle_pause,
            bd=0, padx=10, pady=4, relief=tk.FLAT
        )
        self.pause_btn.pack(side=tk.LEFT, padx=5)

        # Stop Button
        self.stop_btn = tk.Button(
            toolbar, text="⏹ Stop", bg="#1e1e2e", fg="#f38ba8",
            activebackground="#45475a", activeforeground="#f38ba8",
            font=("Segoe UI", 9, "bold"), command=self.stop_recording,
            bd=0, padx=10, pady=4, relief=tk.FLAT
        )
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # Copy Button
        copy_btn = tk.Button(
            toolbar, text="📋 Copy", bg="#1e1e2e", fg="#89b4fa",
            activebackground="#45475a", activeforeground="#89b4fa",
            font=("Segoe UI", 9, "bold"), command=self.copy_transcript,
            bd=0, padx=10, pady=4, relief=tk.FLAT
        )
        copy_btn.pack(side=tk.LEFT, padx=5)

        # Clear Button
        clear_btn = tk.Button(
            toolbar, text="🗑 Clear", bg="#1e1e2e", fg="#a6adc8",
            activebackground="#45475a", activeforeground="#cdd6f4",
            font=("Segoe UI", 9, "bold"), command=self.clear_transcript,
            bd=0, padx=10, pady=4, relief=tk.FLAT
        )
        clear_btn.pack(side=tk.LEFT, padx=5)

        # Target Format Selection on the right
        format_lbl = tk.Label(
            toolbar, text="Format:", fg="#a6adc8", bg="#252538",
            font=("Segoe UI", 9)
        )
        format_lbl.pack(side=tk.RIGHT, padx=(5, 5))

        self.target_format = tk.StringVar(value="Python (pywinauto)")
        self.format_combo = ttk.Combobox(
            toolbar, textvariable=self.target_format,
            values=["Python (pywinauto)", "Desktop MCP Tools", "Action Log"],
            width=18, font=("Segoe UI", 9), state="readonly"
        )
        self.format_combo.pack(side=tk.RIGHT, padx=(0, 10))
        self.format_combo.bind("<<ComboboxSelected>>", lambda e: self.regenerate_display())

        # Middle frame for Line numbers + Text Area + Scrollbar
        middle_frame = tk.Frame(self.recorder_frame, bg="#181825")
        middle_frame.pack(padx=12, pady=12, fill=tk.BOTH, expand=True, side=tk.TOP)

        # Line numbers
        self.line_num_area = tk.Text(
            middle_frame, width=4, padx=5, bg="#11111b", fg="#585b70",
            font=("Consolas", 10), state=tk.DISABLED, bd=0, highlightthickness=0
        )
        self.line_num_area.pack(side=tk.LEFT, fill=tk.Y)

        # Scrollbar
        self.scrollbar = tk.Scrollbar(middle_frame, bg="#181825")
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Text Area (normal text widget, wrap=tk.NONE)
        self.text_area = tk.Text(
            middle_frame, wrap=tk.NONE, bg="#181825", fg="#cdd6f4",
            insertbackground="white", font=("Consolas", 10), bd=0,
            highlightthickness=0
        )
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Sync scrolling
        def on_scroll(*args):
            self.text_area.yview(*args)
            self.line_num_area.yview(*args)

        def on_text_scroll(*args):
            self.scrollbar.set(*args)
            self.line_num_area.yview_moveto(args[0])

        self.scrollbar.config(command=on_scroll)
        self.text_area.config(yscrollcommand=on_text_scroll)

        # Bind MouseWheel so it scrolls both synchronously
        def on_mouse_wheel(event):
            delta = event.delta
            if sys.platform == "darwin":
                self.text_area.yview_scroll(-int(delta), "units")
                self.line_num_area.yview_scroll(-int(delta), "units")
            else:
                self.text_area.yview_scroll(-int(delta/120), "units")
                self.line_num_area.yview_scroll(-int(delta/120), "units")
            return "break"

        self.text_area.bind("<MouseWheel>", on_mouse_wheel)
        self.line_num_area.bind("<MouseWheel>", on_mouse_wheel)

        self.events = [{"type": "system", "text": f"Recording started. target_app='{self.target_app or 'None'}'"}]
        self.regenerate_display()

    def toggle_record(self) -> None:
        self.paused = not self.paused
        self.update_states()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.update_states()

    def stop_recording(self) -> None:
        self.paused = True
        if self.record_btn:
            self.record_btn.configure(text="○ Record", fg="#a6adc8")
        if self.pause_btn:
            self.pause_btn.configure(text="▶ Resume", fg="#a6e3a1")
        if self.status_lbl:
            self.status_lbl.configure(text="Stopped", fg="#a6adc8")
        self.log_event({"type": "system", "text": "Recording Stopped."})
        self.prompt_close_target()

    def prompt_close_target(self) -> None:
        if self.target_app and not self.target_closed:
            if messagebox:
                ans = messagebox.askyesno(
                    "Close Application",
                    f"Would you like to close the target application under test ('{self.target_app}')?"
                )
                if ans:
                    self.target_closed = True
                    if self.on_close_target_callback:
                        self.on_close_target_callback()
                    else:
                        print("[System] Close target requested (no callback registered).")
                else:
                    self.target_closed = True

    def update_states(self) -> None:
        if self.paused:
            if self.record_btn:
                self.record_btn.configure(text="○ Record", fg="#a6adc8")
            if self.pause_btn:
                self.pause_btn.configure(text="▶ Resume", fg="#a6e3a1")
            if self.status_lbl:
                self.status_lbl.configure(text="Paused", fg="#f9e2af")
            self.log_event({"type": "system", "text": "Recording Paused."})
        else:
            if self.record_btn:
                self.record_btn.configure(text="● Record", fg="#f38ba8")
            if self.pause_btn:
                self.pause_btn.configure(text="⏸ Pause", fg="#f9e2af")
            if self.status_lbl:
                self.status_lbl.configure(text="● Recording", fg="#f38ba8")
            self.log_event({"type": "system", "text": "Recording Resumed."})

    def log_action(self, text: str) -> None:
        # Compatibility fallback
        self.log_event({"type": "system", "text": text})

    def log_event(self, event_dict: dict) -> None:
        # Also print Action Log format to console stdout
        print(self.format_single_event(event_dict, "Action Log"), end="")

        if not self.root:
            self.events.append(event_dict)
            return

        def _update():
            self.events.append(event_dict)
            self.regenerate_display()

        self.root.after(0, _update)

    def format_single_event(self, ev: dict, fmt: str) -> str:
        if fmt == "Action Log":
            if ev["type"] == "system":
                return f"{ev['text']}\n"
            elif ev["type"] == "focus_shift":
                return f"\n[Window] Focus shifted to: '{ev['win_title']}' (HWND: {ev['win_handle']})\n"
            elif ev["type"] == "click":
                return f"  -> Clicked {ev['control_type']}: '{ev['name']}' (auto_id='{ev['auto_id']}')\n"
            elif ev["type"] == "checkbox":
                return f"  -> CheckBox: '{ev['name']}' (auto_id='{ev['auto_id']}') -> {ev['state']}\n"
            elif ev["type"] == "input":
                return f"  -> Input Text: '{ev['text']}' into {ev['control_type']} '{ev['name']}' (auto_id='{ev['auto_id']}')\n"
            elif ev["type"] == "combobox":
                return f"  -> ComboBox: '{ev['name']}' (auto_id='{ev['auto_id']}') selection: '{ev['value']}'\n"

        elif fmt == "Python (pywinauto)":
            if ev["type"] == "system":
                return f"# {ev['text']}\n"
            elif ev["type"] == "focus_shift":
                title = ev["win_title"]
                return f"\n# Focus shifted to: {title}\nwin = app.window(title=\"{title}\")\nwin.set_focus()\n"
            elif ev["type"] == "click":
                ctrl_type = ev["control_type"]
                name = ev["name"]
                auto_id = ev["auto_id"]
                selector = []
                if auto_id:
                    selector.append(f'auto_id="{auto_id}"')
                if name:
                    selector.append(f'title="{name}"')
                selector.append(f'control_type="{ctrl_type}"')
                sel_str = ", ".join(selector)
                return f'win.child_window({sel_str}).click()\n'
            elif ev["type"] == "checkbox":
                name = ev["name"]
                auto_id = ev["auto_id"]
                state = ev["state"]
                selector = []
                if auto_id:
                    selector.append(f'auto_id="{auto_id}"')
                if name:
                    selector.append(f'title="{name}"')
                selector.append('control_type="CheckBox"')
                sel_str = ", ".join(selector)
                if state == "Checked":
                    return f'win.child_window({sel_str}).check()\n'
                elif state == "Unchecked":
                    return f'win.child_window({sel_str}).uncheck()\n'
                else:
                    return f'win.child_window({sel_str}).click()\n'
            elif ev["type"] == "input":
                ctrl_type = ev["control_type"]
                name = ev["name"]
                auto_id = ev["auto_id"]
                text = ev["text"]
                selector = []
                if auto_id:
                    selector.append(f'auto_id="{auto_id}"')
                if name:
                    selector.append(f'title="{name}"')
                selector.append(f'control_type="{ctrl_type}"')
                sel_str = ", ".join(selector)
                return f'win.child_window({sel_str}).set_edit_text("{text}")\n'
            elif ev["type"] == "combobox":
                name = ev["name"]
                auto_id = ev["auto_id"]
                val = ev["value"]
                selector = []
                if auto_id:
                    selector.append(f'auto_id="{auto_id}"')
                if name:
                    selector.append(f'title="{name}"')
                selector.append('control_type="ComboBox"')
                sel_str = ", ".join(selector)
                return f'win.child_window({sel_str}).select("{val}")\n'

        elif fmt == "Desktop MCP Tools":
            if ev["type"] == "system":
                return ""
            elif ev["type"] == "focus_shift":
                title = ev["win_title"]
                return f'{{"tool": "activate_window", "arguments": {{"window_id": "{title}"}}}}'
            elif ev["type"] == "click":
                auto_id = ev["auto_id"] or ev["name"]
                return f'{{"tool": "click", "arguments": {{"control_id": "{auto_id}"}}}}'
            elif ev["type"] == "checkbox":
                auto_id = ev["auto_id"] or ev["name"]
                return f'{{"tool": "click", "arguments": {{"control_id": "{auto_id}"}}}}'
            elif ev["type"] == "input":
                auto_id = ev["auto_id"] or ev["name"]
                text = ev["text"]
                return f'{{"tool": "enter_text", "arguments": {{"control_id": "{auto_id}", "text": "{text}"}}}}'
            elif ev["type"] == "combobox":
                auto_id = ev["auto_id"] or ev["name"]
                return f'{{"tool": "click", "arguments": {{"control_id": "{auto_id}"}}}}'

        return ""

    def regenerate_display(self) -> None:
        if not self.text_area:
            return

        fmt = self.target_format.get()
        content = ""

        if fmt == "Python (pywinauto)":
            content += "#!/usr/bin/env python3\n"
            content += "from pywinauto import Application\n"
            content += "import time\n\n"
            if self.target_app:
                content += f"app = Application(backend=\"uia\").connect(title=\"{self.target_app}\")\n"
            else:
                content += "app = Application(backend=\"uia\").start(\"calc.exe\")  # Fallback launch\n"
            for ev in self.events:
                content += self.format_single_event(ev, fmt)
        elif fmt == "Desktop MCP Tools":
            tool_lines = []
            for ev in self.events:
                line = self.format_single_event(ev, fmt)
                if line:
                    tool_lines.append(line)
            content += "[\n"
            content += ",\n".join(f"  {line}" for line in tool_lines)
            content += "\n]"
        else:
            for ev in self.events:
                content += self.format_single_event(ev, fmt)

        self.text_area.configure(state=tk.NORMAL)
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert(tk.END, content)
        self.text_area.see(tk.END)
        self.text_area.configure(state=tk.DISABLED)

        self.update_line_numbers()

    def update_line_numbers(self) -> None:
        if not self.line_num_area or not self.text_area:
            return
        self.line_num_area.configure(state=tk.NORMAL)
        self.line_num_area.delete("1.0", tk.END)
        num_lines = int(self.text_area.index('end-1c').split('.')[0])
        line_nums_str = "\n".join(str(i) for i in range(1, num_lines + 1))
        self.line_num_area.insert("1.0", line_nums_str)
        self.line_num_area.configure(state=tk.DISABLED)

    def copy_transcript(self) -> None:
        if not self.root or not self.text_area:
            return
        content = self.text_area.get("1.0", tk.END).strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(content)

    def clear_transcript(self) -> None:
        self.events = [{"type": "system", "text": "Logs cleared."}]
        self.regenerate_display()


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
            project_root = os.path.abspath(os.path.join(script_dir, ".."))
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

    print("====================================================")
    print("      Desktop MCP - Action Recorder")
    print("====================================================")
    print("Launch status: Listening to active Windows UIA events.")

    uia_instance = IUIA()
    desktop_instance = Desktop(backend="uia")
    target_hwnd = None
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

                        # Target check
                        is_target = False
                        if not ui.target_app:
                            is_target = True
                        else:
                            if target_hwnd and win_handle == target_hwnd:
                                is_target = True
                            elif win_title and ui.target_app.lower() in win_title.lower():
                                is_target = True

                        if win_handle != last_window_handle:
                            last_window_handle = win_handle
                            if not should_ignore and is_target:
                                ui.log_event({
                                    "type": "focus_shift",
                                    "win_title": win_title,
                                    "win_handle": win_handle
                                })

                        if not should_ignore and is_target:
                            if click_control_type == "Button":
                                ui.log_event({
                                    "type": "click",
                                    "control_type": "Button",
                                    "name": click_name,
                                    "auto_id": click_auto_id
                                })
                                clicked_el_logged = True
                            elif click_control_type == "MenuItem":
                                ui.log_event({
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
                                ui.log_event({
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
                                ui.log_event({
                                    "type": "combobox",
                                    "name": click_name,
                                    "auto_id": click_auto_id,
                                    "value": val
                                })
                                clicked_el_logged = True
                            else:
                                if click_name or click_auto_id:
                                    ui.log_event({
                                        "type": "click",
                                        "control_type": click_control_type,
                                        "name": click_name,
                                        "auto_id": click_auto_id
                                    })
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

                # Target check
                is_target = False
                if not ui.target_app:
                    is_target = True
                else:
                    if target_hwnd and win_handle == target_hwnd:
                        is_target = True
                    elif win_title and ui.target_app.lower() in win_title.lower():
                        is_target = True

                # Flush input text buffer immediately when focus shifts to another element
                if runtime_id != last_runtime_id:
                    if last_runtime_id in text_buffer:
                        edit_info = text_buffer.pop(last_runtime_id)
                        try:
                            val = edit_info["el"].get_value() or ""
                            if val:
                                ui.log_event({
                                    "type": "input",
                                    "control_type": edit_info["type"],
                                    "name": edit_info["name"],
                                    "auto_id": edit_info["auto_id"],
                                    "text": val
                                })
                        except Exception:
                            pass
                    last_runtime_id = runtime_id

                    # Only capture focus and inputs if target
                    if not should_ignore and is_target:
                        if not clicked_el_logged:
                            name = info.name or ""
                            control_type = info.control_type or ""
                            auto_id = info.automation_id or ""

                            if control_type == "Button":
                                ui.log_event({
                                    "type": "click",
                                    "control_type": "Button",
                                    "name": name,
                                    "auto_id": auto_id
                                })
                            elif control_type == "MenuItem":
                                ui.log_event({
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
                                ui.log_event({
                                    "type": "checkbox",
                                    "name": name,
                                    "auto_id": auto_id,
                                    "state": state
                                })
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
                                ui.log_event({
                                    "type": "combobox",
                                    "name": name,
                                    "auto_id": auto_id,
                                    "value": val
                                })
                            else:
                                if name or auto_id:
                                    ui.log_event({
                                        "type": "click",
                                        "control_type": control_type,
                                        "name": name,
                                        "auto_id": auto_id
                                    })

                if win_handle != last_window_handle:
                    last_window_handle = win_handle
                    if not should_ignore and is_target:
                        ui.log_event({
                            "type": "focus_shift",
                            "win_title": win_title,
                            "win_handle": win_handle
                        })

            except Exception:
                pass

    # Start UIA listening thread
    record_thread = threading.Thread(target=polling_loop, daemon=True)
    record_thread.start()

    def setup_target_application(app_name: str, minimize_others: bool = True) -> None:
        nonlocal target_hwnd
        try:
            import time
            import subprocess
            import os

            # Wait briefly for Tkinter window to initialize
            time.sleep(0.5)

            # Try to get clean name if it is a path
            clean_name = os.path.basename(app_name)
            if clean_name.lower().endswith(".exe"):
                clean_name = clean_name[:-4]

            # Find the target window
            for win in Desktop.windows():
                title = win.window_text()
                if title and (app_name.lower() in title.lower() or clean_name.lower() in title.lower()):
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
                            if title and (app_name.lower() in title.lower() or clean_name.lower() in title.lower()):
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
            if minimize_others:
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

    def on_recording_started(app, minimize_others):
        if app:
            setup_thread = threading.Thread(target=lambda: setup_target_application(app, minimize_others), daemon=True)
            setup_thread.start()

    def get_windows_list() -> list[str]:
        try:
            titles = []
            for win in Desktop.windows():
                title = win.window_text()
                if title:
                    titles.append(title)

            # Supplement with win32gui to ensure all visible windows are listed
            try:
                import win32gui

                def enum_visible_cb(hwnd, extra):
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        if title and title not in IGNORE_WINDOW_PATTERNS:
                            titles.append(title)
                    return True

                win32gui.EnumWindows(enum_visible_cb, None)
            except Exception:
                pass

            return sorted(list(set(titles)))
        except Exception:
            return []

    def close_target_app():
        nonlocal target_hwnd
        if target_hwnd:
            try:
                import win32gui  # type: ignore
                import win32con  # type: ignore
                print(f"Closing target application (HWND: {target_hwnd}) gracefully via WM_CLOSE...")
                win32gui.PostMessage(target_hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception as e:
                print(f"Error closing target application gracefully: {e}")
                try:
                    from pywinauto import Application  # type: ignore
                    Application().connect(handle=target_hwnd).kill()
                except Exception as e2:
                    print(f"Failed fallback target application kill: {e2}")

    ui.on_close_target_callback = close_target_app

    def on_close():
        stop_event.set()
        # Flush any remaining text buffer
        for r_id, edit_info in text_buffer.items():
            try:
                val = edit_info["el"].get_value() or ""
                if val:
                    ui.log_event({
                        "type": "input",
                        "control_type": edit_info["type"],
                        "name": edit_info["name"],
                        "auto_id": edit_info["auto_id"],
                        "text": val
                    })
            except Exception:
                pass

        # Prompt target close if not already handled
        if ui.target_app and not ui.target_closed:
            ui.prompt_close_target()

        if ui.root:
            ui.root.destroy()
        sys.exit(0)

    window_list = get_windows_list()

    try:
        # Start GUI main loop on main thread
        started = ui.start(
            on_close_callback=on_close,
            target_app=target_app,
            window_list=window_list,
            on_recording_started_callback=on_recording_started
        )
        if not started:
            # Interactive Console Fallback Screen
            print("\n====================================================")
            print("    Desktop MCP - Action Recorder Console Setup     ")
            print("====================================================")
            print("Open Windows List:")
            for idx, t in enumerate(window_list, 1):
                print(f" [{idx}] {t}")
            print("\nEnter target window number, type a window title/executable path, or press Enter for full desktop:")
            user_choice = input("Choice: ").strip()

            minimize_input = input("Minimize other windows? (y/n) [y]: ").strip().lower()
            minimize_others = minimize_input != 'n'

            target = ""
            if user_choice:
                try:
                    choice_idx = int(user_choice) - 1
                    if 0 <= choice_idx < len(window_list):
                        target = window_list[choice_idx]
                    else:
                        target = user_choice
                except ValueError:
                    target = user_choice

            if target:
                print(f"Configured recording target: '{target}' (minimize_others={minimize_others})")
                on_recording_started(target, minimize_others)
            else:
                print("Configured recording target: Full Desktop")

            print("\nConsole Recording active. Press Ctrl+C to stop.")
            while not stop_event.is_set():
                time.sleep(0.5)

    except KeyboardInterrupt:
        on_close()


def run_mock_recorder() -> None:
    print("====================================================")
    print("      Desktop MCP - Action Recorder (Mock Mode)")
    print("====================================================")
    print("Running in simulated mode (macOS/Linux platform detected).")

    ui = RecorderUI()
    stop_event = threading.Event()

    def close_target_app():
        print("[Mock] Graceful target application closure requested.")
        ui.log_event({"type": "system", "text": "Mock target application closed gracefully."})

    ui.on_close_target_callback = close_target_app

    def on_close():
        stop_event.set()
        if ui.target_app and not ui.target_closed:
            ui.prompt_close_target()
        if ui.root:
            ui.root.destroy()
        sys.exit(0)

    # Mock window list
    mock_windows = [
        "Calculator",
        "Notepad",
        "Google Chrome",
        "Visual Studio Code",
        "System Settings",
        "Command Prompt"
    ]

    def on_mock_started(app, minimize_others):
        print(f"Mock recording started for target: {app or 'Full Desktop'} (minimize={minimize_others})")

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
                if stop_event.is_set():
                    break
                time.sleep(1.5)
                if not ui.paused:
                    ui.log_event(ev)

        gen_thread = threading.Thread(target=mock_generator, daemon=True)
        gen_thread.start()

    started = ui.start(
        on_close_callback=on_close,
        target_app=None,
        window_list=mock_windows,
        on_recording_started_callback=on_mock_started
    )
    if not started:
        print("Mock Console Recording active. Outputting example logs...")
        time.sleep(1)
        ui.log_event({"type": "focus_shift", "win_title": "Calculator", "win_handle": 2098032})
        ui.log_event({"type": "click", "control_type": "Button", "name": "Clear", "auto_id": "clearButton"})
        ui.log_event({"type": "click", "control_type": "Button", "name": "Five", "auto_id": "num5Button"})
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
