"""Tool descriptions and input schemas for the Desktop MCP server.

These schemas are returned via the MCP ``tools/list`` response and are
critical for AI agents to understand what parameters each tool expects.
"""

from __future__ import annotations

TOOL_SCHEMAS: dict[str, dict] = {
    "create_session": {
        "description": "Create a new Desktop MCP session. Must be called before any other tool. Returns a session_id.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    "close_session": {
        "description": "Close an active session and release resources.",
        "inputSchema": {"type": "object", "properties": {"session_id": {"type": "string"}}, "required": ["session_id"]},
    },
    "launch_application": {
        "description": "Launch a desktop application by executable path. Returns application_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the executable."},
                "arguments": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["path"],
        },
    },
    "attach_application": {
        "description": "Attach to an already-running application by process ID.",
        "inputSchema": {"type": "object", "properties": {"process_id": {"type": "integer"}}, "required": ["process_id"]},
    },
    "close_application": {
        "description": "Close an application.",
        "inputSchema": {"type": "object", "properties": {"application_id": {"type": "string"}}, "required": ["application_id"]},
    },
    "list_windows": {
        "description": "List all visible top-level windows.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    "activate_window": {
        "description": "Bring a window to the foreground and give it focus.",
        "inputSchema": {"type": "object", "properties": {"window_id": {"type": "string"}}, "required": ["window_id"]},
    },
    "wait_for_window": {
        "description": "Wait for a window with a matching title to appear.",
        "inputSchema": {
            "type": "object",
            "properties": {"title_contains": {"type": "string", "description": "Substring to match (case-insensitive)."}},
            "required": ["title_contains"],
        },
    },
    "close_window": {
        "description": "Close a specific window.",
        "inputSchema": {"type": "object", "properties": {"window_id": {"type": "string"}}, "required": ["window_id"]},
    },
    "window_snapshot": {
        "description": "Capture a snapshot of a specific window. Returns a flat list of all interactive controls with their control_id, type, name, automation_id, and value. CRITICAL: Use this to discover what controls exist before trying to interact with them.",
        "inputSchema": {"type": "object", "properties": {"window_id": {"type": "string"}}, "required": ["window_id"]},
    },
    "control_tree": {
        "description": "Get the hierarchical UI control tree for a window.",
        "inputSchema": {"type": "object", "properties": {"window_id": {"type": "string"}}, "required": ["window_id"]},
    },
    "click": {
        "description": "Interact with a UI control (button, checkbox, tab, tree item, etc.). Specify control_id OR search for it using window_id and control_text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {"type": "string", "description": "The control ID to interact with."},
                "window_id": {"type": "string", "description": "The window ID (required if control_id is omitted)."},
                "control_text": {"type": "string", "description": "Text/name of the control to search for."},
                "control_type": {"type": "string", "description": "Control type to filter by (e.g. 'Button')."},
                "action": {
                    "type": "string", 
                    "enum": ["left", "right", "double", "hover"],
                    "description": "The mouse action to perform. Defaults to 'left'."
                }
            },
            "required": [],
        },
    },
    "click_at": {
        "description": "Click at absolute screen coordinates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "button": {"type": "string", "enum": ["left", "right", "double"], "description": "Defaults to 'left'."},
            },
            "required": ["x", "y"],
        },
    },
    "drag_drop": {
        "description": "Drag from one control and drop onto another.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_control_id": {"type": "string"},
                "target_control_id": {"type": "string"},
            },
            "required": ["source_control_id", "target_control_id"],
        },
    },
    "enter_text": {
        "description": "Type text into a text input control, replacing existing content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {"type": "string"},
                "window_id": {"type": "string"},
                "control_text": {"type": "string"},
                "control_type": {"type": "string"},
                "value": {"type": "string", "description": "The text to type."},
            },
            "required": ["value"],
        },
    },
    "press_keys": {
        "description": "Send raw keyboard commands to a control or the active window (e.g., '{ENTER}', '^c' for Ctrl+C). Crucial for legacy apps.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keys": {"type": "string", "description": "The keys to send (e.g., '{TAB}', '{ENTER}', 'hello')."},
                "control_id": {"type": "string", "description": "Optional: the control to send keys to. If omitted, sends to the active window."},
            },
            "required": ["keys"],
        },
    },
    "read_text": {
        "description": "Read the current text/value from a control.",
        "inputSchema": {"type": "object", "properties": {"control_id": {"type": "string"}}, "required": ["control_id"]},
    },
    "select_item": {
        "description": "Select an item from a ComboBox, Dropdown, or ListBox control by its value/text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "control_id": {"type": "string"},
                "value": {"type": "string", "description": "The value/text of the item to select."},
            },
            "required": ["control_id", "value"],
        },
    },
    "read_table": {
        "description": "Read all data from a DataGrid/Table control. Returns columns and rows.",
        "inputSchema": {"type": "object", "properties": {"control_id": {"type": "string"}}, "required": ["control_id"]},
    },
    "capture_window": {
        "description": "Take a screenshot of a specific window. Saves to evidence directory.",
        "inputSchema": {"type": "object", "properties": {"window_id": {"type": "string"}}, "required": ["window_id"]},
    },
    "capture_desktop": {
        "description": "Take a screenshot of the entire desktop. Saves to evidence directory.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    "start_recording": {
        "description": "Start recording a GIF of the session.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    "stop_recording": {
        "description": "Stop recording and save the GIF.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    "generate_report": {
        "description": "Generate a markdown report of the session actions.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    }
}
