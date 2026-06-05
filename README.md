# PostQode Desktop MCP

PostQode Desktop MCP is a Desktop Model Context Protocol server for AI-driven automation of Windows desktop applications. It exposes desktop automation as structured MCP tools so an agent can launch applications, inspect windows and controls, interact with UI elements, validate state, and collect evidence without using raw screen coordinates.

The current implementation includes the MCP contract, stdio entrypoint, session management, tool routing, typed models, an in-memory adapter for development/tests, and a placeholder Windows UI Automation adapter. The Windows adapter is intentionally isolated so `pywinauto`, `pywin32`, and UI Automation work can be added without changing the agent-facing contract.

## Current Status

- Status: MVP Foundation (Phase 0 and Phase 1 Complete)
- Runtime: Python 3.12+
- MCP transport: stdio JSON-RPC
- Local adapter: in-memory demo adapter
- Windows adapter: concrete implementation using `pywinauto`, `psutil`, and UI Automation
- Primary docs: `docs/PostQode_Desktop_MCP_API_Specification_v1.md`

## Prerequisites

For local development:

- Python 3.12 or newer
- Git
- `pytest` for running tests

For Windows desktop automation work:

- Windows 10 or Windows 11
- Python 3.12+
- Desktop apps running in the same user session as the MCP server
- Accessibility/UI Automation enabled on the target application
- Optional Windows dependencies from the `windows` extra:
  - `pywinauto`
  - `pywin32`
  - `comtypes`
  - `psutil`
  - `Pillow`
  - `mss`

## Installation

Clone or open this repository, then create a virtual environment:

```bash
cd /Users/sreenuraj/desktop-mcp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

For Windows adapter development, install the Windows extras on a Windows machine:

```bash
python -m pip install -e ".[dev,windows]"
```

## Run Tests

```bash
python -m pytest
```

Expected result:

```text
14 passed
```

## Run the MCP Server

Run the stdio server directly:

```bash
python -m desktop_mcp.server.stdio
```

If the package is installed in editable mode, you can also run:

```bash
desktop-mcp
```

The server reads JSON-RPC requests from stdin and writes JSON-RPC responses to stdout. Agents should configure it as a stdio MCP server.

## Agent MCP Configuration

Use this command when configuring an AI agent or MCP client:

```bash
python -m desktop_mcp.server.stdio
```

Example `settings.json` entry:

```json
{
  "mcpServers": {
    "postqode-desktop": {
      "command": "python",
      "args": ["-m", "desktop_mcp.server.stdio"],
      "cwd": "/Users/sreenuraj/desktop-mcp"
    }
  }
}
```

If you installed the package and want to use the console script:

```json
{
  "mcpServers": {
    "postqode-desktop": {
      "command": "desktop-mcp",
      "args": [],
      "cwd": "/Users/sreenuraj/desktop-mcp"
    }
  }
}
```

If your agent runs inside a virtual environment, point `command` at that environment's Python executable:

```json
{
  "mcpServers": {
    "postqode-desktop": {
      "command": "/Users/sreenuraj/desktop-mcp/.venv/bin/python",
      "args": ["-m", "desktop_mcp.server.stdio"],
      "cwd": "/Users/sreenuraj/desktop-mcp"
    }
  }
}
```

On Windows, the same pattern applies:

```json
{
  "mcpServers": {
    "postqode-desktop": {
      "command": "C:\\path\\to\\desktop-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "desktop_mcp.server.stdio"],
      "cwd": "C:\\path\\to\\desktop-mcp"
    }
  }
}
```

## Configuring the Adapter

The Desktop MCP server dynamically selects the adapter to use:
- **Default (Windows)**: Uses `WindowsUIAutomationAdapter` automatically when run on Windows (`win32`).
- **Fallback**: On non-Windows platforms (macOS/Linux), it automatically falls back to `InMemoryDesktopAdapter`.
- **Manual Override**: You can explicitly select the adapter by setting the `DESKTOP_MCP_ADAPTER` environment variable to either `"uia"` or `"memory"`.

Example setting in your agent configuration `settings.json`:

```json
{
  "mcpServers": {
    "postqode-desktop": {
      "command": "python",
      "args": ["-m", "desktop_mcp.server.stdio"],
      "cwd": "/Users/sreenuraj/desktop-mcp",
      "env": {
        "DESKTOP_MCP_ADAPTER": "uia"
      }
    }
  }
}
```

## MCP Details

Transport:

- `stdio`

Supported JSON-RPC methods:

- `initialize`
- `notifications/initialized`
- `tools/list`
- `tools/call`

Tool call responses are returned as MCP text content. The text is a JSON string using the Desktop MCP response envelope:

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

Failure example:

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

## Example MCP Tool Flow

Create a session:

```json
{
  "name": "create_session",
  "arguments": {}
}
```

List windows:

```json
{
  "name": "list_windows",
  "arguments": {
    "session_id": "session_001"
  }
}
```

Find a control:

```json
{
  "name": "find_control",
  "arguments": {
    "session_id": "session_001",
    "window_id": "win_demo",
    "text": "Save"
  }
}
```

Click a control:

```json
{
  "name": "click",
  "arguments": {
    "session_id": "session_001",
    "control_id": "btn_save"
  }
}
```

Enter and read text:

```json
{
  "name": "enter_text",
  "arguments": {
    "session_id": "session_001",
    "control_id": "txt_customer",
    "value": "John Doe"
  }
}
```

```json
{
  "name": "read_text",
  "arguments": {
    "session_id": "session_001",
    "control_id": "txt_customer"
  }
}
```

## Tool Categories

Session:

- `create_session`
- `close_session`

Application:

- `launch_application`
- `attach_application`
- `close_application`

Window:

- `list_windows`
- `activate_window`
- `wait_for_window`
- `close_window`
- `maximize_window`
- `minimize_window`

Snapshot and discovery:

- `desktop_snapshot`
- `window_snapshot`
- `control_tree`
- `find_control`
- `find_controls`
- `get_control`

Interaction:

- `click`
- `double_click`
- `right_click`
- `hover`
- `focus`
- `drag_drop`

Text:

- `enter_text`
- `append_text`
- `clear_text`
- `read_text`

Selection:

- `select_dropdown`
- `select_tab`
- `select_radio`
- `check`
- `uncheck`

Grid and tree:

- `read_table`
- `find_row`
- `select_row`
- `edit_cell`
- `read_cell`
- `read_tree`
- `expand_node`
- `collapse_node`
- `select_node`

Dialogs and validation:

- `detect_dialog`
- `wait_for_dialog`
- `accept_dialog`
- `dismiss_dialog`
- `control_exists`
- `wait_for_control`
- `assert_text`
- `assert_control_state`
- `assert_table_row`

Evidence and browser auth:

- `capture_window`
- `capture_desktop`
- `start_recording`
- `stop_recording`
- `wait_for_browser`
- `attach_browser_window`

## Session Behavior

Most tools are stateful and require an active session. Start every workflow with `create_session`.

The current server supports explicit session IDs in tool arguments. If an agent omits `session_id` after creating a session, the in-process server can use the active session, but explicit `session_id` is recommended for reliable multi-session behavior.

## Development Notes

The in-memory adapter returns a demo window named `Customer Management` with controls such as:

- `btn_save`
- `txt_customer`
- `ddl_state`
- `grid_customers`

This lets agents and tests exercise the MCP contract before the Windows UI Automation adapter is complete.

## Windows Adapter Roadmap

The next implementation step is to replace the placeholder methods in `desktop_mcp/adapters/windows/uia_adapter.py` with real Windows automation:

- Process launch/attach through `pywinauto` and `psutil`
- Window enumeration through UI Automation/Win32 APIs
- Control snapshots through Microsoft UI Automation
- Interaction through UIA patterns first, then safe fallbacks
- Screenshot capture through `mss`/`Pillow`

Agents should not call Windows APIs directly. They should use MCP tools only.

## Repository Layout

```text
desktop_mcp/
  adapters/
    memory.py
    windows/uia_adapter.py
  models/
  server/
    mcp_server.py
    stdio.py
  session/
docs/
tests/
```
