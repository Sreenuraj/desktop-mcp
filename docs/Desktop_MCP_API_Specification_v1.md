# Desktop MCP API Specification
## Version 1.1

### Status
Draft

### Purpose
This document defines the canonical API contract between Desktop Agents and the Desktop MCP Server.

All product, architecture, and build-plan documents should use the tool names, request fields, and response format defined here. The API has been drastically simplified to 18 core tools to optimize LLM performance and reliability.

---

# 1. API Principles

- Platform independent
- JSON request/response format
- Stable control identifiers
- Accessibility-first
- Vision as fallback
- Session-based execution

---

# 2. Session Scope

Desktop MCP execution is session-based.

The active `session_id` may be supplied explicitly in tool requests or bound implicitly by the MCP runtime context. Implementations must document which mode they use. If the runtime does not provide implicit session binding, every stateful tool request must include `session_id`.

---

# 3. Standard Response Contract

All tools return the same envelope.

## Success

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

## Failure

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "CONTROL_NOT_FOUND",
    "message": "Control could not be located"
  }
}
```

Tool-specific examples below show request payloads and the `data` object returned inside the standard envelope.

---

# 4. Session Lifecycle

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

# 5. Application APIs

## launch_application

Request

```json
{
  "path": "C:\\Program Files\\App\\app.exe",
  "arguments": []
}
```

Data

```json
{
  "application_id": "app_001",
  "process_id": 1234
}
```

## attach_application

Request

```json
{
  "process_id": 1234
}
```

Data

```json
{
  "application_id": "app_001"
}
```

## close_application

Request

```json
{
  "application_id": "app_001"
}
```

Data

```json
{}
```

---

# 6. Window APIs

## list_windows

Request

```json
{}
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

Request

```json
{
  "window_id": "win_001"
}
```

## wait_for_window

Request

```json
{
  "title_contains": "Login",
  "timeout": 30
}
```

## close_window

Request

```json
{
  "window_id": "win_001"
}
```

---

# 7. Snapshot APIs

## window_snapshot

Request

```json
{
  "window_id": "win_001"
}
```

Data

```json
{
  "window_id": "win_001",
  "title": "Customer Management",
  "controls": [
    {
      "id": "ctrl_123",
      "name": "Save",
      "type": "Button",
      "enabled": true,
      "visible": true,
      "focused": false
    }
  ]
}
```

## control_tree

Request

```json
{
  "window_id": "win_001"
}
```

Data

```json
{
  "window_id": "win_001",
  "tree": []
}
```

---

# 8. Control Model

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
  "patterns": ["InvokePattern"]
}
```

`bounds` are returned for evidence, diagnostics, and vision fallback. Agents should prefer `control_id` and must not use coordinates for standard accessibility-driven interaction.

---

# 9. Interaction APIs

## click

Request

```json
{
  "control_id": "ctrl_123",
  "action": "left" 
}
```
*Note: `action` can be "left", "right", "double", or "hover". The MCP server will automatically handle invoking UI patterns like Select/Toggle for checkboxes and tabs behind the scenes.*

## drag_drop

Request

```json
{
  "source_control_id": "ctrl_123",
  "target_control_id": "ctrl_456"
}
```

## press_keys

Request

```json
{
  "keys": "{TAB}John Doe{ENTER}^c",
  "control_id": "ctrl_123" 
}
```
*Note: Sends raw keystrokes. Crucial for legacy applications. If `control_id` is omitted, it sends keys to the active window.*

---

# 10. Text APIs

## enter_text

Request

```json
{
  "control_id": "txt_customer",
  "value": "John Doe"
}
```

## read_text

Request

```json
{
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

# 11. Selection APIs

## select_item

Request

```json
{
  "control_id": "ddl_state",
  "value": "California"
}
```
*Note: Use this for explicitly selecting options in ComboBoxes or ListBoxes without needing to click the popup open.*

---

# 12. Grid APIs

## read_table

Request

```json
{
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

# 13. Evidence APIs

## capture_window

Request

```json
{
  "window_id": "win_001"
}
```

## capture_desktop

Request

```json
{}
```

## start_recording

Request

```json
{}
```

## stop_recording

Request

```json
{}
```

## generate_report

Request

```json
{}
```

---

# 14. Error Codes

- CONTROL_NOT_FOUND
- WINDOW_NOT_FOUND
- APP_NOT_FOUND
- SESSION_NOT_FOUND
- INTERNAL_ERROR
