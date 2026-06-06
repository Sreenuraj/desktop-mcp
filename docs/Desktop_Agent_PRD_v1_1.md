# Desktop Agent & Desktop MCP Framework
## Product Requirements Document (PRD)

### Version
1.1
### Status
Draft
### Scope
Phase 1: Windows Support Only

---

# 1. Overview

The Desktop Agent enables AI-driven interaction, testing, validation, and automation of desktop applications running on Windows.

The solution extends Desktop MCP's existing Agent architecture beyond web applications and APIs to support enterprise thick-client applications.

The Desktop MCP API Specification is the canonical source for tool names, request fields, response envelopes, and error codes.

---

# 2. Goals

- Launch desktop applications
- Discover UI controls
- Navigate workflows
- Execute tests
- Perform exploratory testing
- Capture evidence
- Validate business processes

---

# 3. Supported Platforms (Phase 1)

## Windows

Supported Technologies:

- WinForms
- WPF
- MFC
- Electron
- Native Win32
- .NET Desktop Applications

Technology Stack:

- Microsoft UI Automation (UIA)
- pywinauto
- pywin32

Future:

- macOS Accessibility Adapter
- Linux Adapter
- Citrix Vision Adapter

---

# 4. Architecture

```text
Desktop Agent
       |
       v
Desktop MCP
       |
       v
Windows Adapter
       |
       v
Microsoft UI Automation
```

---

# 5. Design Principles

## Accessibility First

Primary interaction mechanism:

- UI Automation Tree
- Accessibility Tree

Avoid:

- OCR-first approaches
- Coordinate clicking
- Pixel matching

## Vision as Fallback

Used only when controls cannot be discovered through UI Automation.

---

# 6. Core Capabilities

### Application Management

- launch_application
- attach_application
- close_application

### Window Management

- list_windows
- activate_window
- wait_for_window
- close_window
- maximize_window
- minimize_window

### Observation

- desktop_snapshot
- window_snapshot
- control_tree
- capture_window
- capture_desktop

### Discovery

- find_control
- find_controls
- get_control

### Interaction

- click
- double_click
- right_click
- hover
- focus
- drag_drop

### Text Operations

- enter_text
- append_text
- clear_text
- read_text

### Selection Controls

- select_dropdown
- select_tab
- select_radio
- check
- uncheck

### Grid Operations

- read_table
- find_row
- select_row
- edit_cell
- read_cell

### Tree Operations

- read_tree
- expand_node
- collapse_node
- select_node

### Dialog Operations

- detect_dialog
- wait_for_dialog
- accept_dialog
- dismiss_dialog

### Validation

- control_exists
- wait_for_control
- assert_text
- assert_control_state
- assert_table_row

---

# 7. Browser Authentication Support

Desktop applications frequently launch browser-based authentication flows:

- Microsoft SSO
- Azure AD
- Okta
- Ping
- Google Workspace

The Desktop MCP must support:

- Browser detection
- Browser attachment
- Browser accessibility inspection
- Browser interaction

without requiring a separate browser agent.

---

# 8. Evidence Collection

### Screenshots

Capture:

- Before action
- After action
- On failure

### Video Recording

Optional session recording.

### Interaction Logs

Capture:

- Action
- Timestamp
- Result

---

# 9. Error Handling

Detect and report:

- Application crashes
- Missing controls
- Unresponsive windows
- Unexpected dialogs
- Access denied errors
- Stale references

---

# 10. Security Requirements

- No credential storage
- Secure secret injection
- Audit logging
- Session isolation
- Least privilege execution
- Encrypted local storage for non-secret session metadata, logs, and evidence only

---

# 11. Desktop MCP Tool Contract

## Objective

The Desktop MCP Tool Contract defines the stable interface between Desktop Agents and any Desktop Adapter implementation.

This contract ensures that:

- Agents remain platform independent
- Windows implementation can be replaced without agent changes
- Future macOS support requires only a new adapter
- Citrix and Vision adapters can be added later

The Agent MUST never interact directly with UI Automation APIs.

---

## Design Rules

### Rule 1

Agent communicates only through MCP tools.

### Rule 2

Every control must have a stable MCP identifier.

Example:

```json
{
  "id": "ctrl_12345",
  "type": "Button",
  "name": "Save"
}
```

### Rule 3

Agent must never use screen coordinates.

Bad:

```json
{
  "x": 500,
  "y": 200
}
```

Good:

```json
{
  "control_id": "ctrl_12345"
}
```

### Rule 4

All tool responses must use the standard Desktop MCP response envelope:

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

---

## Tool Categories

### Session Tools

#### launch_application

```json
{
  "path": "C:\\Program Files\\App\\app.exe",
  "arguments": []
}
```

#### attach_application

```json
{
  "process_id": 1234
}
```

#### close_application

```json
{
  "application_id": "app_1"
}
```

---

### Window Tools

#### list_windows

Returns:

```json
{
  "windows": []
}
```

#### activate_window

```json
{
  "window_id": "window_1"
}
```

#### wait_for_window

```json
{
  "title_contains": "Login",
  "timeout": 30
}
```

---

### Observation Tools

#### desktop_snapshot

Returns:

```json
{
  "applications": [],
  "windows": []
}
```

#### window_snapshot

Returns:

```json
{
  "window_id": "window_1",
  "title": "Customer Management",
  "controls": []
}
```

#### control_tree

Returns complete accessibility hierarchy.

---

### Discovery Tools

#### find_control

```json
{
  "text": "Save"
}
```

#### find_controls

```json
{
  "type": "Button"
}
```

#### get_control

```json
{
  "control_id": "ctrl_123"
}
```

---

### Interaction Tools

#### click

```json
{
  "control_id": "ctrl_123"
}
```

#### enter_text

```json
{
  "control_id": "txt_customer",
  "value": "John Doe"
}
```

#### select_dropdown

```json
{
  "control_id": "state",
  "value": "California"
}
```

---

### Grid Tools

#### read_table

```json
{
  "control_id": "grid_1"
}
```

#### select_row

```json
{
  "control_id": "grid_1",
  "row_index": 2
}
```

Grid row indexes are zero-based.

#### find_row

```json
{
  "control_id": "grid_1",
  "criteria": {
    "Name": "John Doe"
  }
}
```

---

### Validation Tools

#### wait_for_control

```json
{
  "text": "Success",
  "timeout": 30
}
```

#### assert_text

```json
{
  "control_id": "lbl_status",
  "expected": "Approved"
}
```

---

### Evidence Tools

#### capture_window

#### capture_desktop

#### start_recording

#### stop_recording

---

## Standard Response Format

All MCP tools must return:

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

Failure:

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

---

## Future Adapter Compatibility

The contract must support:

| Platform | Adapter |
|-----------|----------|
| Windows | UI Automation |
| macOS | Accessibility API |
| Linux | AT-SPI |
| Citrix | Vision Adapter |
| SAP GUI | SAP Adapter |
| Oracle Forms | Oracle Adapter |

without requiring changes to Desktop Agents.

---

# 12. Success Criteria

The Desktop Agent should automate:

- 90%+ standard desktop controls
- 80%+ enterprise workflows
- Browser authentication workflows
- Grid-heavy applications
- Multi-window workflows

without requiring coordinate-based automation.
