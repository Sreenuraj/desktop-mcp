"""Tool descriptions and input schemas for the Desktop MCP server.

These schemas are returned via the MCP ``tools/list`` response and are
critical for AI agents to understand what parameters each tool expects.
"""

from __future__ import annotations

TOOL_SCHEMAS: dict[str, dict] = {
    "create_session": {
        "description": (
            "Create a new Desktop MCP session. Must be called before any "
            "other tool. Returns a session_id that should be passed to "
            "subsequent calls."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "close_session": {
        "description": "Close an active session and release all resources.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID to close.",
                }
            },
            "required": ["session_id"],
        },
    },
    "launch_application": {
        "description": (
            "Launch a desktop application by executable path. Supports "
            "both Win32 and UWP apps (e.g. calc.exe, notepad.exe). "
            "Returns application_id and process_id."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Path to the executable "
                        "(e.g. 'calc.exe', 'notepad.exe', "
                        "'C:\\\\Program Files\\\\app.exe')."
                    ),
                },
                "arguments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional command-line arguments.",
                },
            },
            "required": ["path"],
        },
    },
    "attach_application": {
        "description": (
            "Attach to an already-running application by its process ID."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "process_id": {
                    "type": "integer",
                    "description": "The OS process ID to attach to.",
                }
            },
            "required": ["process_id"],
        },
    },
    "close_application": {
        "description": "Close an application and terminate its process tree.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "string",
                    "description": "The application ID returned by launch or attach.",
                }
            },
            "required": ["application_id"],
        },
    },
    "list_windows": {
        "description": (
            "List all visible top-level windows on the desktop. Returns "
            "window_id, title, application_id, and active status for each."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "activate_window": {
        "description": (
            "Bring a window to the foreground and give it focus. "
            "Also restores the window if it is minimized."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_id": {
                    "type": "string",
                    "description": "The window ID to activate.",
                }
            },
            "required": ["window_id"],
        },
    },
    "wait_for_window": {
        "description": (
            "Wait for a window with a matching title to appear. "
            "Useful after launching an application."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title_contains": {
                    "type": "string",
                    "description": (
                        "Substring to match against the window title "
                        "(case-insensitive)."
                    ),
                }
            },
            "required": ["title_contains"],
        },
    },
    "close_window": {
        "description": "Close a specific window.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_id": {
                    "type": "string",
                    "description": "The window ID to close.",
                }
            },
            "required": ["window_id"],
        },
    },
    "maximize_window": {
        "description": "Maximize a window to fill the screen.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_id": {
                    "type": "string",
                    "description": "The window ID to maximize.",
                }
            },
            "required": ["window_id"],
        },
    },
    "minimize_window": {
        "description": "Minimize a window to the taskbar.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_id": {
                    "type": "string",
                    "description": "The window ID to minimize.",
                }
            },
            "required": ["window_id"],
        },
    },
    "restore_window": {
        "description": (
            "Restore a minimized or maximized window to its normal size."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_id": {
                    "type": "string",
                    "description": "The window ID to restore.",
                }
            },
            "required": ["window_id"],
        },
    },
    "desktop_snapshot": {
        "description": (
            "Capture a snapshot of the entire desktop including all windows "
            "and their UI controls. Returns a flat list of controls per "
            "window with type, name, automation_id, bounds, value, and "
            "supported patterns. Use this to discover all visible UI "
            "elements across the desktop."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "window_snapshot": {
        "description": (
            "Capture a snapshot of a specific window and its UI controls. "
            "Returns a flat list of all interactive controls with their "
            "id, type, name, automation_id, bounds, value, and patterns. "
            "Use the control IDs from this snapshot to interact with "
            "elements (click, enter_text, etc.)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_id": {
                    "type": "string",
                    "description": "The window ID to snapshot.",
                }
            },
            "required": ["window_id"],
        },
    },
    "control_tree": {
        "description": (
            "Get the hierarchical UI control tree for a window. Returns "
            "a nested tree of controls with parent-child relationships. "
            "Useful for understanding the UI structure."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_id": {
                    "type": "string",
                    "description": "The window ID to get the tree for.",
                }
            },
            "required": ["window_id"],
        },
    },
    "find_control": {
        "description": (
            "Find a single UI control in a window by text and/or type. "
            "Returns the first matching control."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_id": {
                    "type": "string",
                    "description": "The window ID to search in.",
                },
                "text": {
                    "type": "string",
                    "description": (
                        "Text to search for in the control name "
                        "(case-insensitive substring match)."
                    ),
                },
                "type": {
                    "type": "string",
                    "description": (
                        "Control type to filter by "
                        "(e.g. 'Button', 'Edit', 'CheckBox')."
                    ),
                },
            },
            "required": ["window_id"],
        },
    },
    "find_controls": {
        "description": (
            "Find all UI controls in a window, optionally filtered by type."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_id": {
                    "type": "string",
                    "description": "The window ID to search in.",
                },
                "type": {
                    "type": "string",
                    "description": (
                        "Control type to filter by "
                        "(e.g. 'Button', 'Edit', 'CheckBox')."
                    ),
                },
            },
            "required": ["window_id"],
        },
    },
    "get_control": {
        "description": (
            "Get details of a specific control by its control_id. "
            "Returns the control's name, type, value, bounds, and state."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID to retrieve.",
                }
            },
            "required": ["control_id"],
        },
    },
    "click": {
        "description": (
            "Click a UI control. Uses the Invoke pattern for buttons, "
            "falling back to coordinate-based click simulation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID to click.",
                }
            },
            "required": ["control_id"],
        },
    },
    "click_at": {
        "description": (
            "Click at absolute screen coordinates. Use this when you know "
            "the pixel position but don't have a control_id. Useful as a "
            "fallback or for custom UI elements."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {
                    "type": "integer",
                    "description": "X coordinate (pixels from left).",
                },
                "y": {
                    "type": "integer",
                    "description": "Y coordinate (pixels from top).",
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "double"],
                    "description": (
                        "Mouse button to use. Defaults to 'left'."
                    ),
                },
            },
            "required": ["x", "y"],
        },
    },
    "double_click": {
        "description": "Double-click a UI control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID to double-click.",
                }
            },
            "required": ["control_id"],
        },
    },
    "right_click": {
        "description": "Right-click a UI control to open its context menu.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID to right-click.",
                }
            },
            "required": ["control_id"],
        },
    },
    "hover": {
        "description": "Move the mouse cursor over a UI control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID to hover over.",
                }
            },
            "required": ["control_id"],
        },
    },
    "focus": {
        "description": "Set keyboard focus on a UI control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID to focus.",
                }
            },
            "required": ["control_id"],
        },
    },
    "drag_drop": {
        "description": "Drag from one control and drop onto another.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_control_id": {
                    "type": "string",
                    "description": "The control ID to drag from.",
                },
                "target_control_id": {
                    "type": "string",
                    "description": "The control ID to drop onto.",
                },
            },
            "required": ["source_control_id", "target_control_id"],
        },
    },
    "enter_text": {
        "description": (
            "Type text into a text input control, replacing any existing "
            "content."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the text field.",
                },
                "value": {
                    "type": "string",
                    "description": "The text to type.",
                },
            },
            "required": ["control_id", "value"],
        },
    },
    "append_text": {
        "description": "Append text to the end of a text input control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the text field.",
                },
                "value": {
                    "type": "string",
                    "description": "The text to append.",
                },
            },
            "required": ["control_id", "value"],
        },
    },
    "clear_text": {
        "description": "Clear all text from a text input control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the text field.",
                }
            },
            "required": ["control_id"],
        },
    },
    "read_text": {
        "description": "Read the current text/value from a control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID to read from.",
                }
            },
            "required": ["control_id"],
        },
    },
    "select_dropdown": {
        "description": "Select an item from a dropdown/combo box control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the dropdown.",
                },
                "value": {
                    "type": "string",
                    "description": "The value/text of the item to select.",
                },
            },
            "required": ["control_id", "value"],
        },
    },
    "select_tab": {
        "description": "Select a tab in a tab control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the tab item.",
                }
            },
            "required": ["control_id"],
        },
    },
    "select_radio": {
        "description": "Select a radio button.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the radio button.",
                }
            },
            "required": ["control_id"],
        },
    },
    "check": {
        "description": "Check a checkbox control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the checkbox.",
                }
            },
            "required": ["control_id"],
        },
    },
    "uncheck": {
        "description": "Uncheck a checkbox control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the checkbox.",
                }
            },
            "required": ["control_id"],
        },
    },
    "read_table": {
        "description": (
            "Read all data from a grid/table control. Returns columns "
            "(headers) and rows (data dictionaries)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the DataGrid or Table.",
                }
            },
            "required": ["control_id"],
        },
    },
    "find_row": {
        "description": (
            "Find a row in a grid/table matching the given criteria. "
            "Returns the row index and data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the DataGrid or Table.",
                },
                "criteria": {
                    "type": "object",
                    "description": (
                        "Column-value pairs to match "
                        '(e.g. {"Name": "John"}).'
                    ),
                },
            },
            "required": ["control_id", "criteria"],
        },
    },
    "select_row": {
        "description": "Select a row in a grid/table by its zero-based index.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the DataGrid or Table.",
                },
                "row_index": {
                    "type": "integer",
                    "description": "Zero-based row index to select.",
                },
            },
            "required": ["control_id", "row_index"],
        },
    },
    "edit_cell": {
        "description": "Edit a cell in a grid/table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the DataGrid or Table.",
                },
                "row_index": {
                    "type": "integer",
                    "description": "Zero-based row index.",
                },
                "column": {
                    "type": "string",
                    "description": "Column header name or zero-based index.",
                },
                "value": {
                    "type": "string",
                    "description": "The new cell value.",
                },
            },
            "required": ["control_id", "row_index", "column", "value"],
        },
    },
    "read_cell": {
        "description": "Read the value of a specific cell in a grid/table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the DataGrid or Table.",
                },
                "row_index": {
                    "type": "integer",
                    "description": "Zero-based row index.",
                },
                "column": {
                    "type": "string",
                    "description": "Column header name.",
                },
            },
            "required": ["control_id", "row_index", "column"],
        },
    },
    "read_tree": {
        "description": "Read the hierarchical data from a TreeView control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the TreeView.",
                }
            },
            "required": ["control_id"],
        },
    },
    "expand_node": {
        "description": "Expand a node in a TreeView control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_path": {
                    "type": "string",
                    "description": "Path to the node to expand.",
                }
            },
            "required": ["node_path"],
        },
    },
    "collapse_node": {
        "description": "Collapse a node in a TreeView control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_path": {
                    "type": "string",
                    "description": "Path to the node to collapse.",
                }
            },
            "required": ["node_path"],
        },
    },
    "select_node": {
        "description": "Select a node in a TreeView control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_path": {
                    "type": "string",
                    "description": "Path to the node to select.",
                }
            },
            "required": ["node_path"],
        },
    },
    "detect_dialog": {
        "description": "Check if a modal dialog is currently present.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "wait_for_dialog": {
        "description": "Wait for a modal dialog to appear.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "accept_dialog": {
        "description": "Accept (OK/Yes) a dialog.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dialog_id": {
                    "type": "string",
                    "description": "The dialog ID to accept.",
                }
            },
            "required": ["dialog_id"],
        },
    },
    "dismiss_dialog": {
        "description": "Dismiss (Cancel/No) a dialog.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dialog_id": {
                    "type": "string",
                    "description": "The dialog ID to dismiss.",
                }
            },
            "required": ["dialog_id"],
        },
    },
    "control_exists": {
        "description": "Check whether a control exists and is accessible.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID to check.",
                }
            },
            "required": ["control_id"],
        },
    },
    "wait_for_control": {
        "description": (
            "Wait for a control to appear in a window, polling at 500ms "
            "intervals until the timeout."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_id": {
                    "type": "string",
                    "description": "The window ID to search in.",
                },
                "text": {
                    "type": "string",
                    "description": "Text to match in the control name.",
                },
                "type": {
                    "type": "string",
                    "description": "Control type to filter by.",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (default: 10).",
                },
            },
            "required": ["window_id"],
        },
    },
    "assert_text": {
        "description": (
            "Assert that a control contains the expected text. "
            "Takes a screenshot on failure."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID to check.",
                },
                "expected": {
                    "type": "string",
                    "description": "The expected text value.",
                },
            },
            "required": ["control_id", "expected"],
        },
    },
    "assert_control_state": {
        "description": (
            "Assert properties of a control (enabled, visible, focused). "
            "Takes a screenshot on failure."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID to check.",
                },
                "enabled": {
                    "type": "boolean",
                    "description": "Expected enabled state.",
                },
                "visible": {
                    "type": "boolean",
                    "description": "Expected visibility state.",
                },
                "focused": {
                    "type": "boolean",
                    "description": "Expected focus state.",
                },
            },
            "required": ["control_id"],
        },
    },
    "assert_table_row": {
        "description": (
            "Assert that a table contains a row matching the criteria."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "The control ID of the DataGrid or Table.",
                },
                "criteria": {
                    "type": "object",
                    "description": "Column-value pairs to match.",
                },
            },
            "required": ["control_id", "criteria"],
        },
    },
    "capture_window": {
        "description": (
            "Take a screenshot of a specific window. Returns the file "
            "path of the saved PNG image."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_id": {
                    "type": "string",
                    "description": "The window ID to capture.",
                }
            },
            "required": ["window_id"],
        },
    },
    "capture_desktop": {
        "description": (
            "Take a screenshot of the entire desktop. Returns the file "
            "path of the saved PNG image."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "start_recording": {
        "description": (
            "Start recording the screen as an animated GIF. "
            "Call stop_recording to save the GIF."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID to record for.",
                }
            },
            "required": ["session_id"],
        },
    },
    "stop_recording": {
        "description": (
            "Stop screen recording and save the animated GIF. "
            "Returns the file path of the saved recording."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID.",
                }
            },
            "required": ["session_id"],
        },
    },
    "wait_for_browser": {
        "description": (
            "Wait for a browser window (Chrome, Edge, Firefox) to appear. "
            "Useful for SSO/OAuth flows where a browser pop-up is expected."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (default: 60).",
                }
            },
            "required": [],
        },
    },
    "attach_browser_window": {
        "description": (
            "Find and attach to an existing browser window. "
            "Returns the window_id for further interaction."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title_contains": {
                    "type": "string",
                    "description": (
                        "Optional substring to match in the browser title."
                    ),
                }
            },
            "required": [],
        },
    },
    "generate_report": {
        "description": (
            "Generate a Markdown execution report for a session, including "
            "a timeline of all actions, durations, and artifact links."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID to generate a report for.",
                }
            },
            "required": ["session_id"],
        },
    },
}
