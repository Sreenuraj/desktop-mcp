# Desktop MCP API Specification
## Version 1.2

### Status
Active — Phase 1 + Phase 2 implemented

### Changelog
| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-08-01 | Initial draft — 18 core tools |
| 1.1 | 2026-09-01 | Draft refinements |
| 1.2 | 2026-09-06 | **Phase 1**: `isError`, `SNAPSHOT_EMPTY`, `UNKNOWN_TOOL`, enriched responses, `desktop_snapshot` restored, `wait_for_window` polling. **Phase 2**: pattern-first dispatch, `restore_foreground_after_action`, new actions (`toggle`, `expand_node`, `collapse_node`, `scroll_into_view`). |

### Purpose
This document defines the canonical API contract between Desktop Agents and the Desktop MCP Server.

All product, architecture, and build-plan documents should use the tool names, request fields, and response format defined here. The API exposes 25 core tools optimised for LLM agent reliability.

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

> **Phase 1.6**: `isError: true` is the canonical MCP `CallToolResult` signal. LLM-side libraries (e.g. Claude's tool-use SDK) respect this field. Always check `isError` before trusting `data`.

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

> **Phase 1.2 + 2.3**: Returns observable foreground state instead of `{}`. Uses `AttachThreadInput` sequence instead of the Alt-key hack.

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

> **Phase 1.4**: Now polls every 250 ms up to `timeout_ms`. Previously returned immediately without waiting.

Request

```json
{
  "session_id": "session_001",
  "title_contains": "Calculator",
  "timeout_ms": 10000
}
```

Data — returns the matching window dict on success.

```json
{
  "window_id": "win_001",
  "title": "Calculator",
  "active": true
}
```

On timeout: `isError: true`, code `WINDOW_NOT_FOUND`.

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

> **Phase 1.3**: Restored. Was removed in commit `5bb4eb8`; agents in production still call it. Now a thin wrapper over `list_windows` + per-window shallow snapshot.

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

> **Phase 1.2**: Enriched with `controls_count`, `capture_method`, `uia_state`, `took_ms`.
> **Phase 1.1**: Raises `SNAPSHOT_EMPTY` (with `isError: true`) instead of silently returning `controls: []`.

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
- `in_memory` — in-memory adapter (dev/test)

## control_tree

> **Phase 1.2**: Enriched with `tree_node_count` and `took_ms`.

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

# 9. Control Model

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

# 10. Interaction APIs

## click

> **Phase 2.1**: Pattern-first dispatch — tries UIA patterns before mouse synthesis. Most interactions no longer require the target window to be in foreground.
> **Phase 2.4**: `restore_foreground_after_action` (default `true`) restores VSCode to foreground after each action.

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

---

# 11. Text APIs

## enter_text

> **Phase 2.1**: Uses `ValuePattern.SetValue()` first (no foreground needed); falls back to `type_keys` only if the pattern is unavailable.

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

# 12. Selection APIs

## select_item

> **Phase 2.1**: Uses `SelectionItemPattern.Select()` (no foreground needed).

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

# 13. Grid APIs

## read_table

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

---

# 14. Evidence APIs

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

---

# 15. Agent Recovery Playbook

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
  → method: click_input, foreground_restored: true   ← foreground returned to VSCode
```

### Unknown tool called

```
error.code == "UNKNOWN_TOOL"
  → error.details.valid_tools  ← use one of these instead
```

---

# 16. Tool Surface Summary (25 tools)

| Category | Tool | Phase added/updated |
|---|---|---|
| Session | `create_session`, `close_session` | v1.0 |
| Application | `launch_application`, `attach_application`, `close_application` | v1.0 |
| Window | `list_windows`, `activate_window`*, `wait_for_window`*, `close_window` | v1.0 / *v1.2 |
| Snapshot | `desktop_snapshot`†, `window_snapshot`*, `control_tree`* | v1.0 / †restored v1.2 / *enriched v1.2 |
| Interaction | `click`*, `enter_text`*, `press_keys`, `select_item`*, `drag_drop` | v1.0 / *pattern-first v1.2 |
| Grid | `read_table` | v1.0 |
| Evidence | `capture_window`, `capture_desktop`, `start_recording`, `stop_recording`, `generate_report` | v1.0 |
| Coordinates | `click_at` | v1.0 |
