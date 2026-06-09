# Desktop MCP

Desktop MCP is a Model Context Protocol (MCP) server for AI-driven automation of Windows desktop applications. It exposes desktop UI controls as structured MCP tools so that AI agents can launch processes, inspect controls, enter text, click buttons, read grids, and capture screenshots — without relying on fragile screen coordinates and without requiring the target window to be in foreground.

---

## Capabilities

- **Session Management** — Isolated automation sessions per agent workflow.
- **Application Control** — Launch, attach to, or close applications by path or process ID.
- **Window Management** — List windows, bring to focus, wait for a window to appear (with real polling), or close it.
- **Control Discovery** — Snapshot a window's full control tree as a flat list or hierarchical tree. Empty trees return a structured error with a recovery hint instead of silently succeeding.
- **Pattern-First Interactions** — UIA automation patterns (`InvokePattern`, `TogglePattern`, `ValuePattern`, `SelectionItemPattern`, `ExpandCollapsePattern`, `ScrollItemPattern`) are used before mouse synthesis. Most button clicks, text entry, and selections work without the target window being in foreground.
- **Foreground Restoration** — After any action that required foreground, the previously-focused window (typically your IDE) is automatically restored.
- **Grid Framework** — Read rows and columns from enterprise `DataGrid` and `Table` controls.
- **Evidence Collection** — High-resolution screenshots, GIF recordings, and Markdown audit logs saved per session.

---

## Prerequisites

- **Python** 3.12 or newer
- **Operating System** — Windows 10/11 for full UIA automation. An in-memory adapter is included for development and testing on macOS/Linux.
- **System Permissions** — Accessibility/UI Automation access must be enabled for the target applications.

---

## Installation

### Option A: Quick Setup (Recommended)

Run the setup script for your platform. It creates a virtual environment, installs all dependencies, and prints the MCP configuration block to paste into your AI client.

#### Windows (PowerShell)
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
.\setup.ps1
```

#### macOS / Linux
```bash
./setup.sh
```

---

### Option B: Manual Installation

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install with development dependencies
pip install --upgrade pip
pip install -e ".[dev]"

# Windows: also install UIA/Win32 extras
pip install -e ".[dev,windows]"
```

---

## Running the Server

> **You do not need to start the server manually.** Because this is a `stdio`-based MCP server, your AI client (Claude Desktop, Cursor, etc.) spawns and manages the server process automatically.

To run manually for debugging:

```bash
python -m desktop_mcp.server.stdio
# or, if installed in editable mode:
desktop-mcp
```

---

## Configuring Your AI Client

After running the setup script, paste the printed configuration into your client's settings file (`settings.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "desktop-mcp": {
      "command": "C:\\path\\to\\desktop-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "desktop_mcp.server.stdio"],
      "cwd": "C:\\path\\to\\desktop-mcp"
    }
  }
}
```

To force the in-memory adapter (useful for testing without a Windows machine):

```json
{
  "mcpServers": {
    "desktop-mcp": {
      "command": "python",
      "args": ["-m", "desktop_mcp.server.stdio"],
      "cwd": "C:\\path\\to\\desktop-mcp",
      "env": { "DESKTOP_MCP_ADAPTER": "memory" }
    }
  }
}
```

---

## Tool Reference

The server exposes 25 tools. Every tool call returns the same envelope:

```json
{ "success": true,  "data": { ... }, "error": null,    "isError": false }
{ "success": false, "data": null,    "error": { "code": "...", "message": "...", "details": {} }, "isError": true }
```

`isError: true` is the canonical MCP signal — check it before trusting `data`.

### Sessions
| Tool | Description |
|---|---|
| `create_session` | Start a new session. Returns `session_id`. Must be called first. |
| `close_session` | End the session and release resources. |

### Applications
| Tool | Description |
|---|---|
| `launch_application` | Launch an executable by path. Returns `application_id`. |
| `attach_application` | Attach to a running process by PID. |
| `close_application` | Terminate an application and its children. |

### Windows
| Tool | Description |
|---|---|
| `list_windows` | List all visible top-level windows. |
| `activate_window` | Bring a window to foreground. Returns `is_foreground`, `became_foreground`, `total_ms` so you can verify it worked. |
| `wait_for_window` | Poll until a window with a matching title appears. Accepts `timeout_ms` (default 10 000). Returns `WINDOW_NOT_FOUND` on timeout. Use immediately after `launch_application`. |
| `close_window` | Close a specific window. |

### Snapshots & Discovery
| Tool | Description |
|---|---|
| `desktop_snapshot` | Snapshot all visible windows with their controls. Good for initial discovery. |
| `window_snapshot` | **Core discovery tool.** Returns a flat list of all interactive controls with `id`, `name`, `type`, `patterns`. Also returns `controls_count`, `uia_state` (`live`/`empty`/`denied`), `capture_method`, `took_ms`. Returns `SNAPSHOT_EMPTY` error (with a `hint`) if UIA returns no controls — never silently returns an empty list. |
| `control_tree` | Hierarchical control tree. Returns `tree_node_count` and `took_ms`. |

### Interactions
| Tool | Description |
|---|---|
| `click` | Click a control. Uses UIA patterns first (no foreground needed for buttons, checkboxes, list items). `action` can be `left`, `right`, `double`, `hover`, `toggle`, `expand_node`, `collapse_node`, `scroll_into_view`. Set `restore_foreground_after_action: false` only when debugging. |
| `enter_text` | Type text into a control. Uses `ValuePattern.SetValue()` first (no foreground needed). |
| `read_text` | Read the current value of a control. |
| `press_keys` | Send raw keystrokes (e.g. `{TAB}`, `{ENTER}`, `^c`). Essential for legacy apps. |
| `select_item` | Select an item from a ComboBox or ListBox by value text. |
| `drag_drop` | Drag from one control and drop onto another. |
| `click_at` | Click at absolute screen coordinates. Last resort — use `control_id` when possible. |

### Grids
| Tool | Description |
|---|---|
| `read_table` | Read all rows and columns from a DataGrid or Table control. |

### Evidence
| Tool | Description |
|---|---|
| `capture_window` | Screenshot of a specific window. Use as visual fallback when `window_snapshot` returns `SNAPSHOT_EMPTY`. |
| `capture_desktop` | Full desktop screenshot. |
| `start_recording` / `stop_recording` | Record a GIF of the session. |
| `generate_report` | Generate a Markdown audit log of all session actions. |

---

## Typical Agent Workflow

```
create_session
  → launch_application(path="C:\\Windows\\System32\\calc.exe")
  → wait_for_window(title_contains="Calculator", timeout_ms=10000)
  → window_snapshot(window_id="win_...")
      controls_count: 32, uia_state: "live"
      → agent sees buttons: "Seven", "Plus", "Three", "Equals", "display"
  → click(control_id="ctrl_...", action="left")   # method: uia_invoke, required_foreground: false
  → click(control_id="ctrl_...")                  # Plus
  → click(control_id="ctrl_...")                  # Three
  → click(control_id="ctrl_...")                  # Equals
  → read_text(control_id="ctrl_...")              # value: "10"
  → close_session
```

## Recovery Patterns

**Empty control tree:**
```
window_snapshot → SNAPSHOT_EMPTY
  → activate_window → window_snapshot (retry)
  → still empty? → capture_window (visual fallback)
```

**Unknown tool name:**
```
error.code == "UNKNOWN_TOOL"
  → error.details.valid_tools  ← full list of 25 valid tool names
```

---

## Interaction Recorder

Desktop MCP includes a UIA-native interaction recorder (similar to Playwright Codegen) that captures your manual interactions and outputs them as Desktop MCP tool calls.

### Windows (PowerShell — recommended)
```powershell
.\run_recorder.ps1 -a Calculator
```
The script auto-elevates to Administrator, creates/updates the virtual environment, and launches the recorder.

### Windows (CMD)
```cmd
run_recorder.bat --app Calculator
```

### macOS / Linux (mock mode)
```bash
./run_recorder.sh
```

### Manual
```bash
desktop-mcp-recorder --app "Calculator"
# or
python -m desktop_mcp.recorder.main -a "Calculator"
```

The recorder UI shows captured actions in real time. Use the **Format** dropdown to switch between Python pywinauto, Desktop MCP tools, or Action Log output. You can switch formats while recording or after.

---

## Running Tests

```bash
python -m pytest
```

Expected:

```
123 passed
```

---

## License

MIT — see [LICENSE](LICENSE).
