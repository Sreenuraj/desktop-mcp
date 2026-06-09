"""Tool descriptions and input schemas for the Desktop MCP server.

These schemas are returned via the MCP ``tools/list`` response and are
critical for AI agents to understand what parameters each tool expects.

Phase 1.5 changes:
- ``session_id``, ``window_id``, ``application_id``, ``control_id`` are
  consistently marked required where the server actually requires them.
- ``additionalProperties: false`` added to all input schemas so agents
  receive a validation error rather than silently ignoring unknown keys.
- ``isError: true`` convention documented in every error description.
- ``desktop_snapshot`` restored (Phase 1.3).
- ``wait_for_window`` gains ``timeout_ms`` parameter (Phase 1.4).
- Enriched response field descriptions for Phase 1.2 tools.
"""

from __future__ import annotations

TOOL_SCHEMAS: dict[str, dict] = {
    # ------------------------------------------------------------------ #
    # Session management
    # ------------------------------------------------------------------ #
    "create_session": {
        "description": (
            "Create a new Desktop MCP session. Must be called before any other tool. "
            "Returns a session_id that must be passed to all subsequent calls."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    "close_session": {
        "description": "Close an active session and release all resources associated with it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "The session to close."},
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    # ------------------------------------------------------------------ #
    # Application lifecycle
    # ------------------------------------------------------------------ #
    "launch_application": {
        "description": (
            "Launch a desktop application by executable path. "
            "Returns application_id and process_id. "
            "On error returns isError: true with code APP_NOT_FOUND or INTERNAL_ERROR."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "path": {"type": "string", "description": "Absolute path to the executable."},
                "arguments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional command-line arguments.",
                },
            },
            "required": ["session_id", "path"],
            "additionalProperties": False,
        },
    },
    "attach_application": {
        "description": (
            "Attach to an already-running application by its OS process ID. "
            "On error returns isError: true with code APP_NOT_FOUND."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "process_id": {"type": "integer", "description": "OS process ID to attach to."},
            },
            "required": ["session_id", "process_id"],
            "additionalProperties": False,
        },
    },
    "close_application": {
        "description": "Terminate an application and all its child processes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "application_id": {"type": "string", "description": "The application to close."},
            },
            "required": ["session_id", "application_id"],
            "additionalProperties": False,
        },
    },
    # ------------------------------------------------------------------ #
    # Window management
    # ------------------------------------------------------------------ #
    "list_windows": {
        "description": "List all visible top-level windows on the desktop.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    "activate_window": {
        "description": (
            "Bring a window to the foreground and give it focus. "
            "Returns observable state: is_foreground, became_foreground, foreground_title, "
            "attempts, total_ms. "
            "IMPORTANT: check is_foreground in the response — a True result means the window "
            "is now active and ready for interaction. "
            "On error returns isError: true with code WINDOW_NOT_FOUND."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "window_id": {"type": "string", "description": "The window to activate."},
            },
            "required": ["session_id", "window_id"],
            "additionalProperties": False,
        },
    },
    "wait_for_window": {
        "description": (
            "Poll until a window whose title contains the given substring appears, "
            "then return it. Polls every 250 ms up to timeout_ms (default 10 000 ms). "
            "On timeout returns isError: true with code WINDOW_NOT_FOUND. "
            "Use this immediately after launch_application instead of assuming the window "
            "is already present."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "title_contains": {
                    "type": "string",
                    "description": "Case-insensitive substring to match against window titles.",
                },
                "timeout_ms": {
                    "type": "integer",
                    "description": "Maximum wait time in milliseconds. Default: 10000.",
                    "default": 10000,
                },
            },
            "required": ["session_id", "title_contains"],
            "additionalProperties": False,
        },
    },
    "close_window": {
        "description": "Close a specific window.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "window_id": {"type": "string", "description": "The window to close."},
            },
            "required": ["session_id", "window_id"],
            "additionalProperties": False,
        },
    },
    # ------------------------------------------------------------------ #
    # Snapshot / discovery
    # ------------------------------------------------------------------ #
    "desktop_snapshot": {
        "description": (
            "Return a lightweight snapshot of ALL visible windows, each with their "
            "top-level controls. Useful for initial discovery when you don't yet know "
            "which window_id to target. "
            "Each window entry includes: window_id, title, controls, controls_count, "
            "capture_method, uia_state. "
            "If a window's UIA tree is empty, its entry will contain snapshot_error "
            "with a recovery hint — do NOT treat this as success."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    "window_snapshot": {
        "description": (
            "Capture a snapshot of a specific window. "
            "Returns a flat list of ALL interactive controls with their control_id, type, "
            "name, automation_id, and value. "
            "Also returns: controls_count, capture_method (uia_children | uia_descendants | "
            "in_memory), uia_state (live | empty | denied), took_ms. "
            "CRITICAL: Use this to discover what controls exist before trying to interact. "
            "If controls_count is 0 or uia_state is 'empty'/'denied', call activate_window "
            "first and retry, or use capture_window for a visual fallback. "
            "On empty tree returns isError: true with code SNAPSHOT_EMPTY and a hint field."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "window_id": {"type": "string", "description": "The window to snapshot."},
            },
            "required": ["session_id", "window_id"],
            "additionalProperties": False,
        },
    },
    "control_tree": {
        "description": (
            "Get the hierarchical UI control tree for a window. "
            "Returns: tree (nested), tree_node_count, took_ms. "
            "Prefer window_snapshot for flat discovery; use control_tree when you need "
            "parent-child relationships."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "window_id": {"type": "string", "description": "The window to inspect."},
            },
            "required": ["session_id", "window_id"],
            "additionalProperties": False,
        },
    },
    # ------------------------------------------------------------------ #
    # Interactions
    # ------------------------------------------------------------------ #
    "click": {
        "description": (
            "Interact with a UI control (button, checkbox, tab, tree item, etc.). "
            "Specify control_id OR search by window_id + control_text/control_type. "
            "Returns: control_id, action, method (uia_invoke | uia_toggle | uia_select | "
            "uia_expand | uia_collapse | uia_scroll_into_view | click_input), "
            "required_foreground, foreground_taken, foreground_restored, took_ms. "
            "method='uia_invoke' means no foreground was needed — this is the preferred path. "
            "foreground_restored=true means VSCode was returned to foreground after the action. "
            "On error returns isError: true with code CONTROL_NOT_FOUND or CONTROL_DISABLED."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "control_id": {
                    "type": "string",
                    "description": "The control ID to interact with (from window_snapshot).",
                },
                "window_id": {
                    "type": "string",
                    "description": "Required if control_id is omitted — used to search for the control.",
                },
                "control_text": {
                    "type": "string",
                    "description": "Text/name of the control to search for (used with window_id).",
                },
                "control_type": {
                    "type": "string",
                    "description": "Control type filter, e.g. 'Button' (used with window_id).",
                },
                "action": {
                    "type": "string",
                    "enum": [
                        "left", "right", "double", "hover",
                        "toggle", "expand_node", "collapse_node", "scroll_into_view",
                    ],
                    "description": (
                        "Action to perform. Defaults to 'left'. "
                        "toggle=TogglePattern (checkbox); "
                        "expand_node/collapse_node=ExpandCollapsePattern (tree/combo); "
                        "scroll_into_view=ScrollItemPattern."
                    ),
                },
                "restore_foreground_after_action": {
                    "type": "boolean",
                    "description": (
                        "If true (default), restore the previously-focused window "
                        "(typically VSCode) after the action completes. "
                        "Set to false only when debugging foreground behaviour."
                    ),
                    "default": True,
                },
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    "click_at": {
        "description": (
            "Click at absolute screen coordinates. Use as a last resort when no control_id "
            "is available. Requires the target window to be in foreground."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "x": {"type": "integer", "description": "Absolute X screen coordinate."},
                "y": {"type": "integer", "description": "Absolute Y screen coordinate."},
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "double"],
                    "description": "Mouse button. Defaults to 'left'.",
                },
            },
            "required": ["session_id", "x", "y"],
            "additionalProperties": False,
        },
    },
    "drag_drop": {
        "description": "Drag from one control and drop onto another.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "source_control_id": {"type": "string", "description": "Control to drag from."},
                "target_control_id": {"type": "string", "description": "Control to drop onto."},
            },
            "required": ["session_id", "source_control_id", "target_control_id"],
            "additionalProperties": False,
        },
    },
    "enter_text": {
        "description": (
            "Type text into a text input control, replacing existing content. "
            "Returns: control_id, action, method (uia_value | type_keys), "
            "required_foreground, foreground_taken, took_ms. "
            "method='uia_value' means no foreground was needed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "control_id": {"type": "string", "description": "Target control ID."},
                "window_id": {
                    "type": "string",
                    "description": "Required if control_id is omitted.",
                },
                "control_text": {"type": "string", "description": "Control name to search for."},
                "control_type": {"type": "string", "description": "Control type filter."},
                "value": {"type": "string", "description": "The text to type."},
            },
            "required": ["session_id", "value"],
            "additionalProperties": False,
        },
    },
    "press_keys": {
        "description": (
            "Send raw keyboard commands to a control or the active window. "
            "Examples: '{ENTER}', '{TAB}', '^c' (Ctrl+C), '%{F4}' (Alt+F4). "
            "Crucial for legacy apps that don't expose UIA patterns. "
            "Returns: action, method, required_foreground, foreground_taken, took_ms."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "keys": {
                    "type": "string",
                    "description": "Keys to send, e.g. '{TAB}', '{ENTER}', 'hello'.",
                },
                "control_id": {
                    "type": "string",
                    "description": "Optional: target control. If omitted, sends to active window.",
                },
            },
            "required": ["session_id", "keys"],
            "additionalProperties": False,
        },
    },
    "read_text": {
        "description": "Read the current text/value from a control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "control_id": {"type": "string", "description": "Control to read from."},
            },
            "required": ["session_id", "control_id"],
            "additionalProperties": False,
        },
    },
    "select_item": {
        "description": "Select an item from a ComboBox, Dropdown, or ListBox by its value/text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "control_id": {"type": "string", "description": "The ComboBox/ListBox control ID."},
                "value": {"type": "string", "description": "The value/text of the item to select."},
            },
            "required": ["session_id", "control_id", "value"],
            "additionalProperties": False,
        },
    },
    "read_table": {
        "description": "Read all data from a DataGrid/Table control. Returns columns and rows.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "control_id": {"type": "string", "description": "The DataGrid/Table control ID."},
            },
            "required": ["session_id", "control_id"],
            "additionalProperties": False,
        },
    },
    # ------------------------------------------------------------------ #
    # Evidence / capture
    # ------------------------------------------------------------------ #
    "capture_window": {
        "description": (
            "Take a screenshot of a specific window. Saves to the session evidence directory. "
            "Use as a visual fallback when window_snapshot returns SNAPSHOT_EMPTY."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "window_id": {"type": "string", "description": "The window to capture."},
                "highlight_rect": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 4,
                    "maxItems": 4,
                    "description": "Optional [left, top, right, bottom] rect to highlight in red.",
                },
            },
            "required": ["session_id", "window_id"],
            "additionalProperties": False,
        },
    },
    "capture_desktop": {
        "description": "Take a screenshot of the entire desktop. Saves to the session evidence directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
                "highlight_rect": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 4,
                    "maxItems": 4,
                    "description": "Optional [left, top, right, bottom] rect to highlight in red.",
                },
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    "start_recording": {
        "description": "Start recording a GIF of the session for evidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    "stop_recording": {
        "description": "Stop recording and save the GIF to the evidence directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    "generate_report": {
        "description": "Generate a markdown report of all session actions and their outcomes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Active session ID."},
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
}
