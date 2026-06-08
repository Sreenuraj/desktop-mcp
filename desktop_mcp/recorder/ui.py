"""Platform-agnostic Tkinter GUI for the Desktop MCP Action Recorder."""

import sys
import tkinter as tk
from tkinter import scrolledtext, filedialog, ttk, messagebox


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
        self.stop_btn = None
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
