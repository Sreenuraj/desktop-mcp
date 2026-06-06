#!/usr/bin/env python3
import sys
import time

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


def run_windows_recorder() -> None:
    try:
        from pywinauto.controls.uiawrapper import UIAWrapper
        from pywinauto.uia_defines import IUIA
    except ImportError as exc:
        print(f"Error: Missing required Windows dependencies. Please install with 'pip install -e .[windows]'\nDetail: {exc}")
        sys.exit(1)

    print("====================================================")
    print("      Desktop MCP - Codegen Interaction Recorder     ")
    print("====================================================")
    print("Instructions:")
    print("1. Click on the target application to start interacting.")
    print("2. The recorder will log window focus changes, clicks, and text entries.")
    print("3. System windows like VS Code and Command Prompt will be ignored.")
    print("4. Press Ctrl+C in this terminal to stop and copy the transcript.\n")

    uia_instance = IUIA()
    last_runtime_id = None
    last_window_handle = None
    text_buffer = {}  # Tracks values of Edit controls to log final inputs on focus-out

    try:
        while True:
            time.sleep(0.1)
            try:
                # Get the globally focused UIA element
                raw_el = uia_instance.uia.GetFocusedElement()
                if not raw_el:
                    continue

                el = UIAWrapper(raw_el)
                info = el.element_info
                runtime_id = info.runtime_id

                # Resolve top level parent window
                try:
                    parent_win = el.top_level_parent()
                    win_handle = parent_win.handle
                    win_title = parent_win.element_info.name or ""
                except Exception:
                    win_handle = None
                    win_title = ""

                # Check if this window should be ignored (e.g. VS Code, console)
                should_ignore = False
                win_title_lower = win_title.lower()
                for pattern in IGNORE_WINDOW_PATTERNS:
                    if pattern in win_title_lower:
                        should_ignore = True
                        break

                if should_ignore:
                    continue

                # Log Window Change
                if win_handle != last_window_handle:
                    last_window_handle = win_handle
                    print(f"\n[Window] Focus shifted to: '{win_title}' (HWND: {win_handle})")

                # Log Element Interaction
                if runtime_id != last_runtime_id:
                    # If we left an edit control that we were typing in, print its final value
                    if last_runtime_id in text_buffer:
                        edit_info = text_buffer.pop(last_runtime_id)
                        try:
                            # Query current value of that control
                            val = edit_info["el"].get_value() or ""
                            if val:
                                print(f"  -> Input Text: '{val}' into {edit_info['type']} '{edit_info['name']}' (auto_id='{edit_info['auto_id']}')")
                        except Exception:
                            pass

                    last_runtime_id = runtime_id

                    name = info.name or ""
                    control_type = info.control_type or ""
                    auto_id = info.automation_id or ""

                    # Log actions based on control type
                    if control_type == "Button":
                        print(f"  -> Clicked Button: '{name}' (auto_id='{auto_id}')")
                    elif control_type == "MenuItem":
                        print(f"  -> Selected Menu Item: '{name}' (auto_id='{auto_id}')")
                    elif control_type == "CheckBox":
                        try:
                            state = "Checked" if el.is_checked() else "Unchecked"
                        except Exception:
                            state = "Toggled"
                        print(f"  -> CheckBox: '{name}' (auto_id='{auto_id}') -> {state}")
                    elif control_type in ("Edit", "Document"):
                        # Save reference to track typing when they move focus out
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
                        print(f"  -> ComboBox: '{name}' (auto_id='{auto_id}') selection: '{val}'")
                    else:
                        # Log general focus changes on interactive elements
                        if name or auto_id:
                            print(f"  -> Focused Element: {control_type} '{name}' (auto_id='{auto_id}')")

            except Exception:
                pass

    except KeyboardInterrupt:
        print("\n\nRecording stopped.")
        # Flush any remaining text buffer
        for r_id, edit_info in text_buffer.items():
            try:
                val = edit_info["el"].get_value() or ""
                if val:
                    print(f"  -> Input Text: '{val}' into {edit_info['type']} '{edit_info['name']}' (auto_id='{edit_info['auto_id']}')")
            except Exception:
                pass
        print("====================================================")
        print("Copy the printed actions above and paste them directly to your AI agent.")


def run_mock_recorder() -> None:
    print("====================================================")
    print("      Desktop MCP - Codegen Interaction Recorder     ")
    print("====================================================")
    print("Running in simulated mode (macOS/Linux platform detected).")
    print("On a Windows machine with pywinauto, this recorder will hook")
    print("into UIA focus events and print a clean action log.\n")
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
