# PostQode Desktop MCP API Specification
## Version 1.0

### Status
Draft

### Purpose
This document defines the canonical API contract between PostQode Agents and the Desktop MCP Server.

All product, architecture, and build-plan documents should use the tool names, request fields, and response format defined here.

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

## maximize_window

Request

```json
{
  "window_id": "win_001"
}
```

## minimize_window

Request

```json
{
  "window_id": "win_001"
}
```

---

# 7. Snapshot APIs

## desktop_snapshot

Request

```json
{}
```

Data

```json
{
  "applications": [],
  "windows": []
}
```

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
  "controls": []
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

# 9. Discovery APIs

## find_control

Request

```json
{
  "window_id": "win_001",
  "text": "Save"
}
```

Data

```json
{
  "control": {
    "id": "ctrl_123",
    "name": "Save",
    "type": "Button"
  }
}
```

## find_controls

Request

```json
{
  "window_id": "win_001",
  "type": "Button"
}
```

Data

```json
{
  "controls": []
}
```

## get_control

Request

```json
{
  "control_id": "ctrl_123"
}
```

---

# 10. Interaction APIs

## click

```json
{
  "control_id": "ctrl_123"
}
```

## double_click

```json
{
  "control_id": "ctrl_123"
}
```

## right_click

```json
{
  "control_id": "ctrl_123"
}
```

## hover

```json
{
  "control_id": "ctrl_123"
}
```

## focus

```json
{
  "control_id": "ctrl_123"
}
```

## drag_drop

```json
{
  "source_control_id": "ctrl_123",
  "target_control_id": "ctrl_456"
}
```

---

# 11. Text APIs

## enter_text

```json
{
  "control_id": "txt_customer",
  "value": "John Doe"
}
```

## append_text

```json
{
  "control_id": "txt_notes",
  "value": "Additional text"
}
```

## clear_text

```json
{
  "control_id": "txt_notes"
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

# 12. Selection APIs

## select_dropdown

```json
{
  "control_id": "ddl_state",
  "value": "California"
}
```

## select_tab

```json
{
  "control_id": "tab_services"
}
```

## select_radio

```json
{
  "control_id": "radio_standard"
}
```

## check

```json
{
  "control_id": "chk_active"
}
```

## uncheck

```json
{
  "control_id": "chk_active"
}
```

---

# 13. Grid APIs

Grid row indexes are zero-based.

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
  "columns": [],
  "rows": []
}
```

## find_row

Request

```json
{
  "control_id": "grid_001",
  "criteria": {
    "Name": "John Doe"
  }
}
```

Data

```json
{
  "row_index": 2,
  "row": {}
}
```

## select_row

```json
{
  "control_id": "grid_001",
  "row_index": 2
}
```

## edit_cell

```json
{
  "control_id": "grid_001",
  "row_index": 2,
  "column": "Status",
  "value": "Approved"
}
```

## read_cell

Request

```json
{
  "control_id": "grid_001",
  "row_index": 2,
  "column": "Status"
}
```

Data

```json
{
  "value": "Approved"
}
```

---

# 14. Tree APIs

## read_tree

```json
{
  "control_id": "tree_001"
}
```

## expand_node

```json
{
  "control_id": "tree_001",
  "node_path": ["Customers", "Active"]
}
```

## collapse_node

```json
{
  "control_id": "tree_001",
  "node_path": ["Customers", "Active"]
}
```

## select_node

```json
{
  "control_id": "tree_001",
  "node_path": ["Customers", "Active"]
}
```

---

# 15. Dialog APIs

## detect_dialog

```json
{}
```

## wait_for_dialog

```json
{
  "timeout": 30
}
```

## accept_dialog

```json
{
  "dialog_id": "dialog_001"
}
```

## dismiss_dialog

```json
{
  "dialog_id": "dialog_001"
}
```

---

# 16. Validation APIs

## control_exists

```json
{
  "control_id": "ctrl_123"
}
```

## wait_for_control

```json
{
  "window_id": "win_001",
  "text": "Success",
  "timeout": 30
}
```

## assert_text

```json
{
  "control_id": "lbl_status",
  "expected": "Approved"
}
```

## assert_control_state

```json
{
  "control_id": "ctrl_123",
  "enabled": true
}
```

## assert_table_row

```json
{
  "control_id": "grid_001",
  "criteria": {
    "Name": "John Doe",
    "Status": "Approved"
  }
}
```

---

# 17. Evidence APIs

## capture_window

```json
{
  "window_id": "win_001"
}
```

## capture_desktop

```json
{}
```

## start_recording

```json
{}
```

## stop_recording

```json
{}
```

---

# 18. Browser Authentication APIs

Desktop MCP handles browser authentication without a separate browser agent by attaching the browser window and applying the same snapshot, discovery, interaction, text, selection, and validation APIs to that browser window.

## wait_for_browser

```json
{
  "timeout": 60
}
```

## attach_browser_window

```json
{
  "title_contains": "Microsoft"
}
```

Data

```json
{
  "window_id": "win_browser_001"
}
```

---

# 19. Error Codes

- CONTROL_NOT_FOUND
- WINDOW_NOT_FOUND
- APP_NOT_FOUND
- SESSION_NOT_FOUND
- TIMEOUT
- ACCESS_DENIED
- CONTROL_DISABLED
- INVALID_REQUEST
- UNSUPPORTED_CONTROL
- INTERNAL_ERROR

---

# 20. Event Schema

```json
{
  "timestamp": "2026-01-01T10:00:00Z",
  "action": "click",
  "target": "btnSave",
  "result": "success"
}
```

---

# 21. Future Extensions

Reserved for:

- Citrix Adapter
- OCR Adapter
- Vision Adapter
- SAP GUI Adapter
- Oracle Forms Adapter
- macOS Adapter
- Linux Adapter

No breaking changes to the Agent contract should be required.
