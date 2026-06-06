#!/usr/bin/env python3
"""Technical Spike: Windows UI Automation and pywinauto Validation.

This script demonstrates and validates:
1. Application launching and attachment.
2. Top-level window listing and selection.
3. Control hierarchy traversal and property extraction.
4. Input interactions (entering text).
5. Window screenshot capture.
6. Graceful teardown.

It supports a mock mode on non-Windows platforms to show expected behavior.
"""

import sys
import time

def run_windows_spike() -> None:
    print("Running technical spike on Windows...")
    try:
        from pywinauto import Application, Desktop
        from PIL import ImageGrab
    except ImportError as exc:
        print(f"Error: Missing required Windows dependencies. Please install with 'pip install -e .[windows]'\nDetail: {exc}")
        sys.exit(1)

    # 1. Launch Application
    print("Step 1: Launching Notepad.exe...")
    app = Application(backend="uia").start("notepad.exe")
    time.sleep(1.0)  # Allow Notepad to initialize

    # 2. Detect & Select Window
    print("Step 2: Detecting open windows...")
    desktop = Desktop(backend="uia")
    notepad_win = None
    for win in desktop.windows():
        if "notepad" in win.window_text().lower():
            notepad_win = win
            break

    if not notepad_win:
        print("Error: Notepad window could not be detected.")
        sys.exit(1)

    print(f"Successfully connected to Notepad: Title='{notepad_win.window_text()}', Handle={notepad_win.handle}")

    # 3. Traverse Control Tree & Discovery
    print("Step 3: Traversing control tree...")
    descendants = notepad_win.descendants()
    print(f"Found {len(descendants)} controls in the Notepad window.")

    # Find the Edit control where text can be entered
    edit_control = None
    for ctrl in descendants:
        control_type = ctrl.element_info.control_type
        print(f" - Control: Name='{ctrl.element_info.name}', Type='{control_type}', AutoID='{ctrl.element_info.automation_id}'")
        # Notepad text area is typically Document or Edit control type
        if control_type in ("Document", "Edit"):
            edit_control = ctrl

    if not edit_control:
        print("Warning: Standard Document/Edit control not found, using first fallback...")
        edit_control = notepad_win.type_keys

    # 4. Text Interaction
    print("Step 4: Entering text into Document control...")
    if hasattr(edit_control, "set_edit_text"):
        edit_control.set_edit_text("Hello, Desktop MCP Agent Spike!")
    else:
        # Fallback to key entry
        notepad_win.type_keys("Hello, Desktop MCP Agent Spike!", with_spaces=True)
    time.sleep(0.5)

    # 5. Capture Screenshot
    print("Step 5: Capturing window screenshot...")
    rect = notepad_win.rectangle()
    bbox = (rect.left, rect.top, rect.right, rect.bottom)
    screenshot = ImageGrab.grab(bbox=bbox)
    screenshot.save("notepad_spike_screenshot.png")
    print("Screenshot saved to notepad_spike_screenshot.png")

    # 6. Teardown
    print("Step 6: Closing Notepad...")
    notepad_win.close()
    print("Spike successfully completed on Windows!")


def run_mock_spike() -> None:
    print("Running simulated spike (macOS/Linux platform detected)...")
    print("Step 1: Simulating Notepad.exe launch...")
    time.sleep(0.2)
    print("Step 2: Simulating window discovery...")
    print(" - Found window: Title='Untitled - Notepad', HWND=56102, PID=8402")
    
    print("Step 3: Simulating control tree traversal...")
    controls = [
        {"name": "File", "type": "MenuItem", "auto_id": "FileMenu"},
        {"name": "Edit", "type": "MenuItem", "auto_id": "EditMenu"},
        {"name": "Text Editor", "type": "Document", "auto_id": "15"},
        {"name": "Status Bar", "type": "StatusBar", "auto_id": "StatusBar"},
    ]
    for c in controls:
        print(f" - Control: Name='{c['name']}', Type='{c['type']}', AutoID='{c['auto_id']}'")
        
    print("Step 4: Simulating text entry into 'Text Editor' Document control...")
    print(" - Action 'enter_text' value='Hello, Desktop MCP Agent Spike!' successful.")
    
    print("Step 5: Simulating screenshot capture of window bounds (left=100, top=100, right=800, bottom=600)...")
    print(" - Screenshot artifact simulated: mock_notepad_screenshot.png")
    
    print("Step 6: Simulating process cleanup...")
    print("Spike successfully completed in mock mode!")


def main() -> None:
    if sys.platform == "win32":
        run_windows_spike()
    else:
        run_mock_spike()


if __name__ == "__main__":
    main()
