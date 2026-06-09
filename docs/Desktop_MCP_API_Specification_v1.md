# Desktop MCP API Specification
## Version 1.3

### Status
Active

### Changelog
| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-08-01 | Initial draft — 18 core tools |
| 1.1 | 2026-09-01 | Draft refinements |
| 1.2 | 2026-09-06 | `isError`, `SNAPSHOT_EMPTY`, `UNKNOWN_TOOL`, enriched responses, `desktop_snapshot` restored, `wait_for_window` polling, pattern-first dispatch, `restore_foreground_after_action`, new click actions (`toggle`, `expand_node`, `collapse_node`, `scroll_into_view`). |
| 1.3 | 2026-09-06 | Added waiters (`wait_for_control`, `wait_for_idle`), grid/tree tools (`select_row`, `click_cell`, `read_cell`, `read_tree`), dialog awareness (`list_dialogs`), grounding tools (`get_foreground_window`, `get_focused_control`, `health_check`), recorder replay (`replay_recording`). Performance & polish: bounded LRU cache, PID-based host exclusion, DPI awareness, structured JSON logging. **36 tools total.** |

### Purpose
This document defines the canonical API contract between Desktop Agents and the Desktop MCP Server.

All product, architecture, and build-plan documents should use the tool names, request fields, and response format defined here. The API exposes 36 core tools optimised for LLM agent reliability.

---

# 1. API Principles

- Platform independent
- JSON request/response format
- Stable control identifiers
- Accessibility-first (UIA patterns before mouse synthesis)
- Vision as fallback
- Session-based execution
- **Observable failures** — every error carries a structured `error` object with `code`, `message`, and `details`; `isError: true` is set on the MCP envelope so LLM-side libraries can detect failures without parsing the body

---

# 2. Session Scope

Desktop MCP execution is session-based.

The active `session_id` must be supplied in every tool request (except `create_session`). All stateful tools require `session_id`.

---

# 3. Standard Response Contract

All tools return the same envelope.

## Success

```json
{
  "success": true,
  "data": {},
  "error": null,
  "isError": false
}
```

## Failure

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "CONTROL_NOT_FOUND",
    "message": "Control could not be located",
    "details": {}
  },
  "isError": true
}
```

> `isError: true` is the canonical MCP `CallToolResult` signal. LLM-side libraries (e.g. Claude's tool-use SDK) respect this field. Always check `isError` before trusting `data`.

Tool-specific examples below show request payloads and the `data` object returned inside the standard envelope.

---

# 4. Error Codes

| Code | Meaning | Recovery |
|---|---|---|
| `CONTROL_NOT_FOUND` | Control ID not found in any window | Re-run `window_snapshot` to get fresh IDs |
| `WINDOW_NOT_FOUND` | Window ID not found or `wait_for_window` timed out | Check `list_windows`; increase `timeout_ms` |
| `APP_NOT_FOUND` | Application process not found | Verify path; check `list_windows` |
| `SESSION_NOT_FOUND` | `session_id` is invalid or expired | Call `create_session` again |
| `SNAPSHOT_EMPTY` | UIA returned no interactive controls for a visible window | Call `activate_window` then retry `window_snapshot`; or use `capture_window` for visual fallback. `details.hint` contains the recovery message. |
| `UNKNOWN_TOOL` | Tool name not recognised | `details.valid_tools` lists all valid tool names |
| `CONTROL_DISABLED` | Control exists but is disabled | Wait for the app to enable it |
| `UNSUPPORTED_CONTROL` | Action not supported for this control type | Use a different action |
| `INVALID_REQUEST` | A required field is missing or invalid | Check the tool's schema (`details` lists the offending key) |
| `INTERNAL_ERROR` | Unexpected server error | Check server logs |

---

# 5. Session Lifecycle

## create_session

Request

```json
{}
```

Data

```json
{
  "session_id": "session_001"
}
```

## close_session

Request

```json
{
  "session_id": "session_001"
}
```

Data

```json
{}
```

---

# 6. Application APIs

## launch_application

Request

```json
{
  "session_id": "session_001",
  "path": "C:\\Windows\\System32\\calc.exe",
  "arguments": []
}
```

Data

```json
{
  "application_id": "app_1234",
  "process_id": 1234
}
```

## attach_application

Request

```json
{
  "session_id": "session_001",
  "process_id": 1234
}
```

Data

```json
{
  "application_id": "app_1234"
}
```

## close_application

Request

```json
{
  "session_id": "session_001",
  "application_id": "app_1234"
}
```

Data

```json
{}
```

---

# 7. Window APIs

## list_windows

Request

```json
{
  "session_id": "session_001"
}
```

Data

```json
{
  "windows": [
    {
      "window_id": "win_001",
      "application_id": "app_001",
      "title": "Customer Management",
      "active": true
    }
  ]
}
```

## activate_window

Returns observable foreground state. Uses the documented `AttachThreadInput` sequence rather than synthetic keystrokes.

Request

```json
{
  "session_id": "session_001",
  "window_id": "win_001"
}
```

Data

```json
{
  "window_id": "win_001",
  "is_foreground": true,
  "became_foreground": true,
  "foreground_window_id": "win_001",
  "foreground_title": "Calculator",
  "attempts": 1,
  "total_ms": 87
}
```

> **IMPORTANT**: Check `is_foreground` in the response. If `false`, the window did not come to foreground — retry or use `capture_window` for visual fallback.

## wait_for_window

Polls every 250 ms up to `timeout_ms`. Returns the matching window dict on success, `WINDOW_NOT_FOUND` on timeout.

Request

```json
{
  "session_id": "session_001",
  "title_contains": "Calculator",
  "timeout_ms": 10000
}
```

Data

```json
{
  "window_id": "win_001",
  "title": "Calculator",
  "active": true
}
```

> Use `wait_for_window` immediately after `launch_application` instead of assuming the window is already present.

## close_window

Request

```json
{
  "session_id": "session_001",
  "window_id": "win_001"
}
```

Data

```json
{}
```

---

# 8. Snapshot APIs

## desktop_snapshot

Lightweight snapshot of every visible top-level window with its top-level controls.

Request

```json
{
  "session_id": "session_001"
}
```

Data

```json
{
  "windows_count": 3,
  "windows": [
    {
      "window_id": "win_001",
      "title": "Calculator",
      "active": true,
      "controls_count": 32,
      "capture_method": "uia_descendants",
      "uia_state": "live",
      "controls": [...]
    }
  ]
}
```

> If a window's UIA tree is empty, its entry contains `snapshot_error` with a recovery hint. Do **not** treat `controls: []` as success.

## window_snapshot

Returns the flat control list for a window. Raises `SNAPSHOT_EMPTY` (with `isError: true`) when UIA returns nothing rather than silently returning an empty list.

Request

```json
{
  "session_id": "session_001",
  "window_id": "win_001"
}
```

Data (success)

```json
{
  "window_id": "win_001",
  "title": "Calculator",
  "active": true,
  "controls_count": 32,
  "capture_method": "uia_descendants",
  "uia_state": "live",
  "took_ms": 142,
  "controls": [
    {
      "id": "ctrl_123",
      "name": "Seven",
      "type": "Button",
      "enabled": true,
      "visible": true,
      "focused": false,
      "patterns": ["InvokePattern"]
    }
  ]
}
```

Error (empty tree)

```json
{
  "success": false,
  "isError": true,
  "error": {
    "code": "SNAPSHOT_EMPTY",
    "message": "UIA returned no descendants for window 'Calculator'...",
    "details": {
      "window_id": "win_001",
      "title": "Calculator",
      "is_foreground": false,
      "uia_state": "empty",
      "took_ms": 38,
      "hint": "Call activate_window then window_snapshot again, or use capture_window for visual fallback."
    }
  }
}
```

`uia_state` values:
- `live` — controls were found
- `empty` — UIA returned nothing (window likely not foreground / process suspended)
- `denied` — UIA threw an exception (access denied / COM error)

`capture_method` values:
- `uia_children` — populated via `children()` traversal
- `uia_descendants` — populated via `descendants()` fallback
- `uwp_child_*` — populated by walking into the real child of a UWP `ApplicationFrameWindow` host
- `fg_retry_*` — populated after a foreground acquisition + retry
- `in_memory` — in-memory adapter (dev/test)

## control_tree

Hierarchical control tree. Returns `tree_node_count` and `took_ms`.

Request

```json
{
  "session_id": "session_001",
  "window_id": "win_001"
}
```

Data

```json
{
  "window_id": "win_001",
  "tree_node_count": 47,
  "took_ms": 89,
  "tree": [...]
}
```

---

# 9. Waiters

## wait_for_control

Polls until a control matching the criteria appears. At least one of `name`, `automation_id`, `control_type` must be provided. Default poll interval is 250 ms.

Request

```json
{
  "session_id": "session_001",
  "window_id": "win_001",
  "name": "Save",
  "state": "enabled",
  "timeout_ms": 10000
}
```

`state` values: `exists` (default), `enabled`, `visible`.

Data — returns the matched control dict (same shape as `window_snapshot` entries). On timeout: `isError: true`, code `CONTROL_NOT_FOUND`.

## wait_for_idle

Waits until the window's UI tree count stays stable for `idle_ms` milliseconds. Uses `WaitForInputIdle` (Win32) + a tree-settle check.

Request

```json
{
  "session_id": "session_001",
  "window_id": "win_001",
  "idle_ms": 500,
  "timeout_ms": 10000
}
```

Data

```json
{
  "idle": true,
  "settled_ms": 612
}
```

On timeout: `isError: true`, code `INTERNAL_ERROR`.

---

# 10. Control Model

```json
{
  "id": "ctrl_123",
  "automation_id": "btnSave",
  "name": "Save",
  "type": "Button",
  "enabled": true,
  "visible": true,
  "focused": false,
  "bounds": {
    "x": 100,
    "y": 200,
    "width": 80,
    "height": 32
  },
  "patterns": ["InvokePattern", "ValuePattern", "TogglePattern", "ExpandCollapsePattern", "ScrollItemPattern"]
}
```

`bounds` are returned for evidence, diagnostics, and vision fallback. Agents should prefer `control_id` and must not use coordinates for standard accessibility-driven interaction.

`patterns` lists the UIA automation patterns the control supports. The server uses these to choose the most reliable interaction method (pattern-first, no foreground required).

---

# 11. Interaction APIs

## click

Pattern-first dispatch — tries UIA patterns before mouse synthesis. Most interactions no longer require the target window to be in foreground. `restore_foreground_after_action` (default `true`) restores the previously-focused window after each action.

Request

```json
{
  "session_id": "session_001",
  "control_id": "ctrl_123",
  "action": "left",
  "restore_foreground_after_action": true
}
```

`action` values:
| Value | UIA Pattern used | Foreground required |
|---|---|---|
| `left` (Button) | `InvokePattern.Invoke()` | No |
| `left` (CheckBox) | `TogglePattern.Toggle()` | No |
| `left` (ListItem/MenuItem/TabItem/RadioButton) | `SelectionItemPattern.Select()` | No |
| `left` (other) | `click_input()` | Yes |
| `toggle` | `TogglePattern.Toggle()` | No |
| `expand_node` | `ExpandCollapsePattern.Expand()` | No |
| `collapse_node` | `ExpandCollapsePattern.Collapse()` | No |
| `scroll_into_view` | `ScrollItemPattern.ScrollIntoView()` | No |
| `right` | `right_click_input()` | Yes |
| `double` | `double_click_input()` | Yes |
| `hover` | `move_mouse_input()` | Yes |

Data

```json
{
  "control_id": "ctrl_123",
  "action": "left",
  "method": "uia_invoke",
  "required_foreground": false,
  "foreground_taken": false,
  "foreground_restored": false,
  "took_ms": 12
}
```

`method` values: `uia_invoke`, `uia_toggle`, `uia_select`, `uia_value`, `uia_expand`, `uia_collapse`, `uia_scroll_into_view`, `click_input`, `type_keys`, `global_send_keys`.

> `required_foreground: false` + `method: uia_invoke` is the ideal path — the action succeeded without touching foreground at all.

## drag_drop

Request

```json
{
  "session_id": "session_001",
  "source_control_id": "ctrl_123",
  "target_control_id": "ctrl_456"
}
```

## press_keys

Request

```json
{
  "session_id": "session_001",
  "keys": "{TAB}John Doe{ENTER}^c",
  "control_id": "ctrl_123"
}
```

*If `control_id` is omitted, sends keys to the active window.*

Data

```json
{
  "action": "press_keys",
  "method": "type_keys",
  "required_foreground": true,
  "foreground_taken": true,
  "foreground_restored": true,
  "took_ms": 45
}
```

## click_at

Click at absolute screen coordinates. Last resort — use `control_id` when possible.

Request

```json
{
  "session_id": "session_001",
  "x": 540,
  "y": 320,
  "button": "left"
}
```

---

# 12. Text APIs

## enter_text

Uses `ValuePattern.SetValue()` first (no foreground needed); falls back to `type_keys` only if the pattern is unavailable.

Request

```json
{
  "session_id": "session_001",
  "control_id": "txt_customer",
  "value": "John Doe"
}
```

Data

```json
{
  "action": "enter_text",
  "method": "uia_value",
  "required_foreground": false,
  "foreground_taken": false,
  "foreground_restored": false,
  "took_ms": 8
}
```

## read_text

Request

```json
{
  "session_id": "session_001",
  "control_id": "txt_notes"
}
```

Data

```json
{
  "value": "Current text"
}
```

---

# 13. Selection APIs

## select_item

Uses `SelectionItemPattern.Select()` (no foreground needed).

Request

```json
{
  "session_id": "session_001",
  "control_id": "ddl_state",
  "value": "California"
}
```

Data

```json
{
  "action": "select_item",
  "method": "uia_select",
  "required_foreground": false,
  "foreground_taken": false,
  "foreground_restored": false,
  "took_ms": 6
}
```

---

# 14. Grid & Tree APIs

## read_table

Read all rows of a DataGrid/Table as a list of dicts keyed by column name.

Request

```json
{
  "session_id": "session_001",
  "control_id": "grid_001"
}
```

Data

```json
{
  "columns": ["ID", "Name", "Status"],
  "rows": [
    {"ID": "1", "Name": "John Doe", "Status": "Approved"}
  ]
}
```

## select_row

Select a row by `by_text` (case-insensitive substring of any cell) or `by_index` (zero-based).

Request

```json
{
  "session_id": "session_001",
  "control_id": "grid_001",
  "by_index": 0
}
```

Data

```json
{
  "control_id": "grid_001",
  "row_control_id": "ctrl_row_0",
  "method": "uia_select",
  "row_index": 0
}
```

## click_cell

Click a specific cell by zero-based `row` and `column`.

Request

```json
{
  "session_id": "session_001",
  "control_id": "grid_001",
  "row": 0,
  "column": 1
}
```

Data

```json
{
  "control_id": "grid_001",
  "cell_control_id": "ctrl_r0_c1",
  "row": 0,
  "column": 1,
  "method": "uia_invoke"
}
```

## read_cell

Read a specific cell's value.

Request

```json
{
  "session_id": "session_001",
  "control_id": "grid_001",
  "row": 0,
  "column": 1
}
```

Data

```json
{
  "control_id": "grid_001",
  "row": 0,
  "column": 1,
  "value": "Approved"
}
```

## read_tree

Read a TreeView as a nested structure. Use `max_depth` (default 4) to bound traversal.

Request

```json
{
  "session_id": "session_001",
  "control_id": "tree_001",
  "max_depth": 4
}
```

Data

```json
{
  "node_count": 12,
  "nodes": [
    {
      "name": "Patients",
      "control_id": "ctrl_node_1",
      "expanded": true,
      "children": [
        {"name": "Jane Doe", "control_id": "ctrl_node_2", "expanded": false, "children": []}
      ]
    }
  ]
}
```

---

# 15. Dialog Awareness

## list_dialogs

Returns modal/popup windows owned by an application. Heuristic: small bounding rectangle, `WS_POPUP` style, or a title containing common dialog keywords. Use after actions that may pop an error/confirmation/login dialog.

Request

```json
{
  "session_id": "session_001",
  "application_id": "app_1234"
}
```

Data

```json
{
  "count": 1,
  "dialogs": [
    {
      "window_id": "win_dialog_001",
      "title": "Error: Login Failed",
      "application_id": "app_1234"
    }
  ]
}
```

---

# 16. Grounding & Diagnostics

## get_foreground_window

Returns the currently-foreground window. Use to verify `restore_foreground_after_action` worked.

Request

```json
{
  "session_id": "session_001"
}
```

Data

```json
{
  "window_id": "win_vscode",
  "hwnd": 591234,
  "title": "Desktop MCP — Visual Studio Code"
}
```

## get_focused_control

Returns the control with keyboard focus in *window_id*. `control_id` is `null` when no control has focus.

Request

```json
{
  "session_id": "session_001",
  "window_id": "win_001"
}
```

Data

```json
{
  "window_id": "win_001",
  "control_id": "txt_customer",
  "name": "Customer",
  "type": "Edit",
  "automation_id": "txtCustomer"
}
```

## health_check

Diagnostic snapshot of the MCP server environment. Call at the start of a session to verify dependencies and learn which PIDs the server excludes from click targets.

Request

```json
{
  "session_id": "session_001"
}
```

Data

```json
{
  "platform": "Windows-10-10.0.19045-SP0",
  "python_version": "3.12.5",
  "uia_available": true,
  "parent_pid": 4032,
  "mcp_pid": 9876,
  "libraries": {
    "pywinauto": "0.6.8",
    "comtypes": "1.2.0",
    "psutil": "5.9.6"
  },
  "dpi_awareness": 2,
  "dpi_set_method": "SetProcessDpiAwarenessContext(-4)",
  "foreground_window": { "window_id": "win_vscode", "hwnd": 591234, "title": "VS Code" },
  "pid_chain": [
    {"pid": 9876, "name": "python.exe"},
    {"pid": 4032, "name": "Code.exe"}
  ],
  "excluded_pids": [4032, 9876],
  "cache_size": 0,
  "cache_generation": 0
}
```

---

# 17. Evidence APIs

## capture_window

Request

```json
{
  "session_id": "session_001",
  "window_id": "win_001",
  "highlight_rect": [100, 200, 180, 232]
}
```

> Use as a visual fallback when `window_snapshot` returns `SNAPSHOT_EMPTY`.

## capture_desktop

Request

```json
{
  "session_id": "session_001"
}
```

## start_recording

Request

```json
{
  "session_id": "session_001"
}
```

## stop_recording

Request

```json
{
  "session_id": "session_001"
}
```

## generate_report

Request

```json
{
  "session_id": "session_001"
}
```

Returns a Markdown audit log of every action performed in the session.

---

# 18. Recorder Replay

## replay_recording

Replays a recording JSON file by executing each step via this MCP server. Every step is routed back through `call_tool`, so logging, evidence capture, and the error envelope behave identically to a live agent run.

The recording schema is defined in [`docs/recording_schema.md`](./recording_schema.md).

Request

```json
{
  "session_id": "session_001",
  "path": "/abs/path/recording.json",
  "stop_on_error": true
}
```

Data

```json
{
  "path": "/abs/path/recording.json",
  "session_id": "session_001",
  "steps_total": 7,
  "steps_executed": 7,
  "steps_succeeded": 6,
  "steps_failed": 1,
  "aborted": true,
  "results": [
    {"step": 0, "tool": "wait_for_window", "success": true},
    {"step": 6, "tool": "read_text", "success": false,
     "error": {"code": "CONTROL_NOT_FOUND",
               "message": "Control not found: ctrl_42_display"}}
  ]
}
```

- `stop_on_error` (default `true`) aborts on the first failing step.
- The replayer injects `session_id` into every step that omits it, so recordings can be session-agnostic.

---

# 19. Agent Recovery Playbook

The following patterns are the recommended recovery sequences for common failure modes.

### Empty control tree after launch

```
launch_application  →  wait_for_window  →  window_snapshot
                                              ↓ SNAPSHOT_EMPTY?
                                         activate_window  →  window_snapshot (retry)
                                              ↓ still empty?
                                         capture_window  (visual fallback)
```

### Foreground race (approval prompt stole focus)

```
click(control_id, restore_foreground_after_action=true)
  → method: uia_invoke, required_foreground: false   ← ideal, no race possible
  → method: click_input, foreground_restored: true   ← foreground returned to caller
```

### Modal dialog appeared after action

```
click(...) → list_dialogs(application_id=...)
  → count > 0 ? handle each dialog before continuing
```

### Unknown tool called

```
error.code == "UNKNOWN_TOOL"
  → error.details.valid_tools  ← use one of these instead
```

### UI hasn't finished updating

```
click(...)  →  wait_for_idle(window_id=..., idle_ms=500)  →  window_snapshot
```

---

# 20. Tool Surface Summary (36 tools)

| Category | Tool |
|---|---|
| Session | `create_session`, `close_session` |
| Application | `launch_application`, `attach_application`, `close_application` |
| Window | `list_windows`, `activate_window`, `wait_for_window`, `close_window` |
| Snapshot | `desktop_snapshot`, `window_snapshot`, `control_tree` |
| Waiters | `wait_for_control`, `wait_for_idle` |
| Interaction | `click`, `enter_text`, `press_keys`, `select_item`, `drag_drop`, `click_at`, `read_text` |
| Grid & Tree | `read_table`, `select_row`, `click_cell`, `read_cell`, `read_tree` |
| Dialogs | `list_dialogs` |
| Grounding | `get_foreground_window`, `get_focused_control`, `health_check` |
| Evidence | `capture_window`, `capture_desktop`, `start_recording`, `stop_recording`, `generate_report` |
| Replay | `replay_recording` |
