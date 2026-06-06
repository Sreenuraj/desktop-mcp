# Desktop Agent
# Technical Architecture Specification (TAS)

Version: 1.0
Status: Draft
Target Platform: Windows (Phase 1)

---

# 1. Purpose

This document defines the technical architecture for the Desktop Agent and Desktop MCP framework.

The objective is to enable Desktop Agents to interact with native desktop applications using a structured, accessibility-first approach while remaining platform-independent.

Phase 1 focuses exclusively on Windows desktop applications.

The Desktop MCP API Specification is the canonical source for external tool names, request fields, response envelopes, and error codes.

---

# 2. Architecture Overview

```text
+------------------------------------------------+
|                 Desktop Agent                 |
+------------------------------------------------+
                     |
                     v
+------------------------------------------------+
|                Desktop MCP Server              |
+------------------------------------------------+
| Session Manager                                |
| Window Manager                                 |
| Snapshot Engine                                |
| Discovery Engine                               |
| Interaction Engine                             |
| Validation Engine                              |
| Evidence Engine                                |
| Vision Fallback Engine                         |
+------------------------------------------------+
                     |
                     v
+------------------------------------------------+
|             Windows Adapter Layer              |
+------------------------------------------------+
| UI Automation Adapter                          |
| Process Adapter                                |
| Screenshot Adapter                             |
| Recording Adapter                              |
+------------------------------------------------+
                     |
                     v
+------------------------------------------------+
|          Microsoft UI Automation API           |
+------------------------------------------------+
```

---

# 3. Core Design Principles

## Accessibility First

Primary source of truth:

- Microsoft UI Automation Tree

The system must prefer:

- Accessibility metadata
- Automation IDs
- Control names
- Control patterns

before using screenshots or OCR.

---

## Agent Independence

Agents must never access:

- UI Automation directly
- pywinauto directly
- Windows APIs directly

All communication occurs through MCP tools.

---

## Platform Abstraction

Agent logic must remain independent of:

- Windows
- macOS
- Linux
- Citrix

Adapters are responsible for platform-specific implementation.

---

# 4. Technology Stack

## Language

Python 3.12+

---

## Primary Libraries

### Desktop Automation

- pywinauto
- pywin32

### UI Automation

- UIAutomationCore.dll
- comtypes

### Process Management

- psutil

### Screenshot Capture

- Pillow
- mss

### OCR (Future)

- Tesseract
- EasyOCR

### Vision Layer (Future)

- OpenCV

---

# 5. Component Architecture

## Session Manager

Responsible for:

- Session creation
- Session persistence
- Window tracking
- Process tracking

Example:

```json
{
  "session_id": "session_001",
  "applications": [],
  "windows": []
}
```

---

## Window Manager

Responsibilities:

- Enumerate windows
- Track active window
- Detect new windows
- Window switching

APIs:

- list_windows()
- activate_window()
- wait_for_window()

---

## Discovery Engine

Purpose:

Convert raw UI Automation trees into AI-friendly structures.

Input:

```text
Raw UI Automation Tree
```

Output:

```json
{
  "controls": []
}
```

Responsibilities:

- Tree traversal
- Control filtering
- Semantic naming
- Control classification

---

## Snapshot Engine

Most important component.

Creates structured representations of UI state.

Responsibilities:

- Window snapshots
- Control snapshots
- Application snapshots

Output Example:

```json
{
  "window":"Customer Management",
  "controls":[
    {
      "id":"ctrl_1",
      "type":"Button",
      "name":"Save"
    }
  ]
}
```

---

## Interaction Engine

Responsibilities:

- Click
- Double click
- Text entry
- Selection
- Drag and drop

Supported Patterns:

- InvokePattern
- ValuePattern
- SelectionPattern
- ExpandCollapsePattern
- TogglePattern

---

## Validation Engine

Responsibilities:

- Assertions
- Waiting
- State validation

Examples:

```python
wait_for_control()
assert_text()
control_exists()
```

---

## Evidence Engine

Responsibilities:

- Screenshots
- Screen recordings
- Execution logs
- Timeline generation

Artifacts:

```text
Screenshots
Video
Logs
Metadata
```

---

## Vision Fallback Engine

Activated only when:

- UI Automation unavailable
- Owner-drawn controls detected
- Canvas rendering detected

Capabilities:

- OCR
- Template matching
- Vision-guided interaction

---

# 6. Desktop MCP Server

## MCP Server Responsibilities

Expose desktop capabilities as tools.

Responsibilities:

- Tool registration
- Request routing
- Response formatting
- Error handling

---

## Tool Categories

### Session Tools

- launch_application
- attach_application
- close_application

### Window Tools

- list_windows
- activate_window
- wait_for_window

### Discovery Tools

- find_control
- find_controls
- get_control

### Interaction Tools

- click
- double_click
- right_click
- hover
- focus
- drag_drop
- enter_text
- append_text
- clear_text
- read_text
- select_dropdown
- select_tab
- select_radio
- check
- uncheck

### Validation Tools

- assert_text
- wait_for_control
- control_exists
- assert_control_state
- assert_table_row

### Evidence Tools

- capture_window
- capture_desktop
- start_recording
- stop_recording

### Grid Tools

- read_table
- find_row
- select_row
- edit_cell
- read_cell

### Tree Tools

- read_tree
- expand_node
- collapse_node
- select_node

### Dialog Tools

- detect_dialog
- wait_for_dialog
- accept_dialog
- dismiss_dialog

### Browser Authentication Tools

- wait_for_browser
- attach_browser_window

---

# 7. Internal Package Structure

```text
desktop_mcp/
│
├── server/
│   ├── mcp_server.py
│   └── router.py
│
├── session/
│   ├── session_manager.py
│   └── state_store.py
│
├── adapters/
│   ├── windows/
│   │   ├── uia_adapter.py
│   │   ├── process_adapter.py
│   │   └── screenshot_adapter.py
│
├── engines/
│   ├── snapshot_engine.py
│   ├── discovery_engine.py
│   ├── interaction_engine.py
│   ├── validation_engine.py
│   └── evidence_engine.py
│
├── models/
│   ├── control.py
│   ├── window.py
│   └── snapshot.py
│
└── tools/
    ├── session_tools.py
    ├── interaction_tools.py
    └── validation_tools.py
```

---

# 8. Control Model

Standard control object.

```json
{
  "id":"ctrl_123",
  "automation_id":"btnSave",
  "name":"Save",
  "type":"Button",
  "enabled":true,
  "visible":true,
  "focused":false,
  "bounds":{},
  "patterns":[]
}
```

---

# 9. Snapshot Strategy

Snapshots are the primary context source for agents.

Agent never receives:

- Raw UI Automation trees
- Native handles
- COM objects

Agent receives:

```json
{
  "window":"Application",
  "controls":[]
}
```

Snapshots should be optimized for LLM consumption.

---

# 10. Browser Authentication Flow

Supported:

- Azure AD
- Microsoft SSO
- Okta
- Ping
- Google

Workflow:

```text
Launch App
      |
      v
Desktop Window
      |
      v
Browser Opens
      |
      v
Attach Browser Window
      |
      v
Authenticate
      |
      v
Browser Closes
      |
      v
Attach Application Window
```

No separate browser agent required.

---

# 11. Grid Framework

Enterprise applications are grid-heavy.

Dedicated support required.

Capabilities:

- Read rows
- Read columns
- Find rows
- Select rows
- Edit cells

Example:

```json
{
  "columns":[],
  "rows":[]
}
```

---

# 12. Error Model

Standardized errors.

Example:

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

Common Codes:

- CONTROL_NOT_FOUND
- WINDOW_NOT_FOUND
- APP_NOT_FOUND
- TIMEOUT
- ACCESS_DENIED
- CONTROL_DISABLED

---

# 13. Security Model

Requirements:

- No credential persistence
- Secure secret injection
- Session isolation
- Audit logging
- Encrypted local storage for non-secret session metadata, logs, and evidence only

---

# 14. Recording Architecture (Future)

Recorder Components:

```text
Event Listener
      |
      v
Action Translator
      |
      v
Workflow Generator
      |
      v
Agent Script
```

Capabilities:

- Capture user actions
- Generate workflows
- Generate agent prompts
- Generate reusable tests

---

# 15. Citrix Strategy (Future)

Citrix will require a future vision adapter:

```text
Vision Engine
    +
OCR
    +
Vision-guided interaction
```

Separate adapter:

```text
Citrix Adapter
```

No changes required to Agent layer. Any coordinate handling remains internal to the Citrix adapter and is not exposed to agents as a standard interaction mechanism.

---

# 16. Future Platform Expansion

Supported by adapter model.

```text
Desktop MCP
     |
     +---- Windows Adapter
     +---- macOS Adapter
     +---- Linux Adapter
     +---- Citrix Adapter
```

Agent remains unchanged.

---

# 17. Performance Targets

Targets are p95 measurements for standard Windows desktop applications with typical enterprise forms. Large virtualized grids and custom-rendered controls may require separate targets.

Window Snapshot:

< 500 ms

Control Discovery:

< 300 ms

Control Interaction:

< 200 ms

Screenshot:

< 1 second

Application Attach:

< 2 seconds

---

# 18. Success Criteria

The architecture must support:

- 90%+ standard desktop controls
- 80%+ enterprise workflows
- Multi-window applications
- Browser authentication workflows
- Grid-heavy applications
- Large enterprise desktop systems

without coordinate-based automation.

---

# 19. Recommended Phase Plan

## Phase 1

Windows Desktop MCP

Features:

- UI Automation
- Discovery
- Interaction
- Snapshots
- Screenshots
- Browser authentication

## Phase 2

Enhanced Enterprise Support

Features:

- Recording
- Self-healing locators
- Advanced grids
- Better validation

## Phase 3

Vision Platform

Features:

- OCR
- Computer Vision
- Citrix Support
- Remote Desktop Support
