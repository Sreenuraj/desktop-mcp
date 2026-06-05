# PostQode Desktop Agent
## MVP Build Plan & Implementation Roadmap

Version: 1.0
Status: Draft

Progress Tracker: `docs/PostQode_Desktop_Agent_Implementation_Progress.md`

---

# 1. Executive Summary

This document defines the implementation roadmap for delivering the first production-ready version of the PostQode Desktop Agent.

The objective is to validate that PostQode can automate enterprise Windows desktop applications using a Desktop MCP architecture built on Microsoft UI Automation.

The Desktop MCP API Specification is the canonical source for external tool names, request fields, response envelopes, and error codes.

Current implementation status, completed tasks, remaining work, and next priorities are tracked in `PostQode_Desktop_Agent_Implementation_Progress.md`.

The MVP focuses on:

- Windows 10/11
- WinForms
- WPF
- Native Windows Applications
- Browser-based SSO flows

The MVP intentionally excludes:

- Citrix
- Remote Desktop
- OCR-first automation
- Smart card authentication
- macOS

---

# 2. MVP Success Criteria

The MVP is successful if it can:

### Application Management

- Launch applications
- Attach to running applications
- Close applications

### Navigation

- Switch windows
- Detect new windows
- Handle modal dialogs

### Interaction

- Click buttons
- Enter text
- Select dropdown values
- Select tabs
- Check/uncheck controls

### Validation

- Read values
- Validate labels
- Verify messages

### Enterprise Data

- Read tables
- Select rows
- Read grids

### Authentication

- Complete Microsoft SSO flows
- Return to desktop application

---

# 3. Recommended Technology Stack

## Core

Python 3.12+

## Desktop Automation

- pywinauto
- pywin32

## UI Automation

- comtypes
- UIAutomationCore

## Utilities

- psutil
- Pillow
- mss

## Testing

- pytest

---

# 4. Proof of Concept Scope

Build a POC before building the complete platform.

POC Goals:

### Goal 1

Launch application

### Goal 2

Take structured snapshot

### Goal 3

Discover controls

### Goal 4

Click controls

### Goal 5

Enter text

### Goal 6

Handle Microsoft SSO browser login

### Goal 7

Return to application

If these work reliably, proceed with MVP.

---

# 5. Development Phases

## Phase 0 - Technical Validation

Duration:

3-5 Days

Objectives:

- Validate pywinauto
- Validate UI Automation
- Validate browser interaction
- Validate table extraction

Deliverables:

- Technical spike
- Feasibility report

Exit Criteria:

Able to:

- Open application
- Read controls
- Click controls
- Read grids

---

## Phase 1 - Desktop MCP Foundation

Duration:

1 Week

Components:

### Session Manager

- Session creation
- Session cleanup

### Window Manager

- Window discovery
- Window switching

### Application Manager

- Launch
- Attach
- Close

Deliverables:

Working MCP skeleton.

---

## Phase 2 - Snapshot Engine

Duration:

1 Week

Components:

### Window Snapshot

Capture:

- Window metadata
- Controls
- Control hierarchy

### Control Model

Normalize:

- Buttons
- Textboxes
- Dropdowns
- Grids

Deliverables:

AI-friendly snapshots.

---

## Phase 3 - Interaction Engine

Duration:

1 Week

Implement:

- click
- double_click
- enter_text
- clear_text
- select_dropdown
- select_tab

Deliverables:

End-to-end workflow execution.

---

## Phase 4 - Validation Engine

Duration:

3-4 Days

Implement:

- wait_for_control
- assert_text
- control_exists
- assert_control_state

Deliverables:

Reliable assertions.

---

## Phase 5 - Grid Framework

Duration:

1 Week

Implement:

- read_table
- find_row
- select_row
- edit_cell

Deliverables:

Enterprise grid support.

---

## Phase 6 - Evidence Collection

Duration:

3-4 Days

Implement:

- screenshots
- action logs
- execution reports

Deliverables:

Test evidence.

---

## Phase 7 - Browser Authentication

Duration:

3-5 Days

Implement:

- browser detection
- browser attachment
- Microsoft SSO support

Workflow:

Application
    -> Browser
    -> Login
    -> Application

Deliverables:

End-to-end SSO automation.

---

# 6. Suggested Repository Structure

```text
desktop-mcp/
│
├── server/
├── adapters/
├── session/
├── engines/
├── tools/
├── models/
├── tests/
└── examples/
```

---

# 7. MVP Tool Priority

Priority 1

Must Have

- launch_application
- attach_application
- list_windows
- activate_window
- window_snapshot
- find_control
- click
- enter_text

Priority 2

Should Have

- read_table
- select_row
- wait_for_control
- assert_text

Priority 3

Nice To Have

- recording
- video capture
- vision fallback for custom-rendered controls

---

# 8. Acceptance Test Suite

## Test 1

Application Launch

Expected:

Application launches successfully and returns an `application_id` plus at least one discoverable window.

---

## Test 2

Window Detection

Expected:

Window is listed by `list_windows`, activated by `activate_window`, and remains associated with the active session.

---

## Test 3

Control Discovery

Expected:

`window_snapshot` returns stable `control_id` values, control names, control types, state fields, and hierarchy data for standard controls.

---

## Test 4

Text Entry

Expected:

`enter_text` writes the requested value and `read_text` returns the same value.

---

## Test 5

Button Interaction

Expected:

`click` invokes the target button and the expected UI state change is visible through a follow-up snapshot or validation API.

---

## Test 6

Grid Read

Expected:

`read_table` returns column metadata and rows, `find_row` returns a zero-based `row_index`, and `select_row` selects the expected row.

---

## Test 7

SSO Login

Expected:

Desktop MCP detects and attaches the browser window, completes Microsoft SSO using normal snapshot/discovery/interaction APIs, and returns focus to the desktop application.

---

## Test 8

Workflow Execution

Expected:

An end-to-end business flow completes with screenshots and action logs captured for the main steps and any failures.

---

# 9. Risks & Mitigations

## Risk

Custom Controls

Mitigation:

Validate accessibility support during Phase 0. Defer OCR/computer-vision fallback to the future Vision Platform phase unless a customer-critical MVP control cannot be automated through UI Automation.

---

## Risk

Large Grids

Mitigation:

Dedicated Grid Engine.

---

## Risk

Unexpected Dialogs

Mitigation:

Dialog detection APIs.

---

## Risk

Browser Authentication Variations

Mitigation:

Window-based browser automation.

---

# 10. Demo Applications

Use these during development.

### WinForms Demo

Microsoft WinForms Sample Apps

### WPF Demo

Microsoft WPF Sample Apps

### Electron

Visual Studio Code

### Native Windows

Notepad

Calculator

---

# 11. Estimated Timeline

Phase 0

3-5 Days

Phase 1

1 Week

Phase 2

1 Week

Phase 3

1 Week

Phase 4

3-4 Days

Phase 5

1 Week

Phase 6

3-4 Days

Phase 7

3-5 Days

Total

Approximately 6-8 weeks with one engineer, including Phase 0.

Two Engineers

Approximately 4-5 weeks if work can be parallelized across foundation, snapshots, evidence, and validation.

---

# 12. Go / No-Go Criteria

Proceed to Productization only if:

- Control discovery > 90%
- Standard interactions > 95%
- Browser authentication stable
- Grid extraction reliable
- Multi-window workflows supported

If any of these fail, revisit architecture before investing further.

---

# 13. Future Roadmap

Product Phase 2

- Recorder
- Self-healing locators
- Advanced reporting
- Test generation

Product Phase 3

- OCR
- Computer Vision
- Citrix

Product Phase 4

- macOS Support
- Linux Support

Product Phase 5

- SAP GUI Adapter
- Oracle Forms Adapter
