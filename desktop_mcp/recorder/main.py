"""Main entry point and orchestration module for the Action Recorder."""

import sys
import time
import argparse
from desktop_mcp.recorder.ui import RecorderUI
from desktop_mcp.recorder.engine import WindowsRecorderEngine, MockRecorderEngine


def main():
    parser = argparse.ArgumentParser(description="Desktop MCP Interaction Recorder")
    parser.add_argument("--app", "-a", type=str, help="Target application name or path to launch and focus, minimizing others")
    args = parser.parse_args()

    ui = RecorderUI()

    # Determine platform and instantiate corresponding engine
    if sys.platform == "win32":
        engine = WindowsRecorderEngine(ui)
    else:
        engine = MockRecorderEngine(ui)

    # Setup callbacks
    ui.on_close_target_callback = engine.close_target_app
    ui.on_refresh_windows_callback = engine.get_windows_list

    def on_recording_started(app, minimize_others):
        engine.start(app, minimize_others)

    ui.on_recording_started_callback = on_recording_started

    def on_close():
        engine.stop()

        # Flush any remaining text buffers
        if hasattr(engine, "text_buffer"):
            for r_id, edit_info in engine.text_buffer.items():
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

        # Prompt target closure if not already handled
        if ui.target_app and not ui.target_closed:
            ui.prompt_close_target()

        if ui.root:
            ui.root.destroy()
        sys.exit(0)

    window_list = engine.get_windows_list()

    # Start UI main loop
    started = ui.start(
        on_close_callback=on_close,
        target_app=args.app,
        window_list=window_list,
        on_recording_started_callback=on_recording_started
    )

    if not started:
        # Fallback Interactive Console Setup Menu
        print("\n====================================================")
        print("    Desktop MCP - Action Recorder Console Setup     ")
        print("====================================================")
        print("Open Windows List:")
        for idx, t in enumerate(window_list, 1):
            print(f" [{idx}] {t}")
        print("\nEnter target window number, type a window title/executable path, or press Enter for full desktop:")
        try:
            user_choice = input("Choice: ").strip()
            minimize_input = input("Minimize other windows? (y/n) [y]: ").strip().lower()
            minimize_others = minimize_input != 'n'
        except (KeyboardInterrupt, EOFError):
            print("\nExiting setup.")
            sys.exit(0)

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
            on_recording_started(None, False)

        print("\nConsole Recording active. Press Ctrl+C to stop.")
        try:
            while not engine.stop_event.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

        # Cleanup on terminal exit
        engine.stop()
        if target:
            try:
                close_choice = input(f"Would you like to close the target application '{target}'? (y/n) [y]: ").strip().lower()
                if close_choice != 'n':
                    engine.close_target_app()
            except (KeyboardInterrupt, EOFError):
                pass
        sys.exit(0)


if __name__ == "__main__":
    main()
