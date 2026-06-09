# Desktop MCP

Desktop MCP is a Model Context Protocol (MCP) server for AI-driven automation of Windows desktop applications. It exposes desktop UI controls as structured MCP tools so an AI agent can launch processes, inspect controls, enter text, click buttons, read grids, capture evidence, and replay recorded sessions — without relying on fragile screen coordinates and, for most actions, without requiring the target window to be in foreground.

---

## Capabilities

- **Session Management** — Isolated automation sessions per agent workflow.
- **Application Control** — Launch, attach to, or close applications by path or PID.
- **Window Management** — List windows, bring to focus, poll until a window appears, or close it.
- **Control Discovery** — Snapshot a window's full control tree as a flat list or hierarchical tree. Empty trees raise a structured `SNAPSHOT_EMPTY` error with a recovery hint instead of silently succeeding.
- **Pattern-First Interactions** — UIA automation patterns (`InvokePattern`, `TogglePattern`, `ValuePattern`, `SelectionItemPattern`, `ExpandCollapsePattern`, `ScrollItemPattern`) are tried before mouse synthesis. Most button clicks, text entry, and selections work without bringing the target window to the foreground.
- **Foreground Restoration** — After an action that did require foreground, the previously-focused window (typically your IDE) is automatically restored.
- **Waiters** — `wait_for_window`, `wait_for_control`, and `wait_for_idle` poll real state with explicit timeouts.
- **Rich Control Kinds** — `select_row`, `click_cell`, `read_cell` for DataGrid/ListView; `read_tree` for TreeView.
- **Dialog Awareness** — `list_dialogs` detects modal/popup windows owned by an application.
- **Grounding Tools** — `get_foreground_window`, `get_focused_control`, `health_check` let the agent verify environment state and library versions.
- **Recorder Round-Trip** — Replay recorded sessions deterministically via `replay_recording`. See [docs/recording_schema.md](docs/recording_schema.md).
- **Evidence Collection** — Per-window screenshots, GIF recordings, and Markdown audit logs saved per session.
- **Performance & Polish** — Bounded LRU element cache (256 entries, generation-tagged), PID-based exclusion of the host process, per-monitor DPI awareness, and structured JSON logging to stderr.

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

### Logging

The server emits one structured JSON log line per tool call to stderr. Configure with:

| Variable | Default | Effect |
|---|---|---|
| `DESKTOP_MCP_LOG_LEVEL` | `INFO` | Standard Python logging level. |
| `DESKTOP_MCP_LOG_FORMAT` | `json` | `json` or `text`. |

Sensitive arguments (`password`, `token`, `secret`, `api_key`, plus `value` for `enter_text`) are redacted from the logs.

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

The server exposes **36 tools**. Every tool call returns the same envelope:

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
| `window_snapshot` | **Core discovery tool.** Returns a flat list of interactive controls with `id`, `name`, `type`, `patterns`, plus `controls_count`, `uia_state` (`live`/`empty`/`denied`), `capture_method`, `took_ms`. Returns `SNAPSHOT_EMPTY` (with a `hint`) when UIA returns nothing — never silently returns an empty list. |
| `control_tree` | Hierarchical control tree. Returns `tree_node_count` and `took_ms`. |

### Waiters
| Tool | Description |
|---|---|
| `wait_for_control` | Poll until a control matching `name` / `automation_id` / `control_type` appears in a window. Optional `state`: `exists` / `enabled` / `visible`. |
| `wait_for_idle` | Wait until the window's UI tree stops changing for `idle_ms` (default 500 ms). Uses `WaitForInputIdle` + tree-settle check. |

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

### Grids & Trees
| Tool | Description |
|---|---|
| `read_table` | Read all rows and columns from a DataGrid or Table control. |
| `select_row` | Select a row in a DataGrid/ListView by `by_text` or `by_index`. |
| `click_cell` | Click a specific cell by zero-based `row` + `column`. |
| `read_cell` | Read the value of a specific cell. |
| `read_tree` | Read a TreeView as a nested `{name, control_id, expanded, children}` structure. |

### Dialogs
| Tool | Description |
|---|---|
| `list_dialogs` | Return modal/popup windows owned by an application — use after actions that may pop a confirmation/error/login dialog. |

### Grounding & Diagnostics
| Tool | Description |
|---|---|
| `get_foreground_window` | Return the current foreground window. Use to confirm `restore_foreground_after_action` worked. |
| `get_focused_control` | Return the control with keyboard focus in a window. |
| `health_check` | Diagnostic snapshot: platform, Python/library versions, DPI awareness path, PID chain, excluded host PIDs, cache stats. Call at the start of a session to verify the environment. |

### Evidence
| Tool | Description |
|---|---|
| `capture_window` | Screenshot of a specific window. Use as visual fallback when `window_snapshot` returns `SNAPSHOT_EMPTY`. |
| `capture_desktop` | Full desktop screenshot. |
| `start_recording` / `stop_recording` | Record a GIF of the session. |
| `generate_report` | Generate a Markdown audit log of all session actions. |
| `replay_recording` | Replay a recording JSON file (schema: [docs/recording_schema.md](docs/recording_schema.md)). Returns per-step success/error and `aborted` flag. Honours `stop_on_error` (default `true`). |

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
  → error.details.valid_tools  ← full list of all valid tool names
```

**Dialog appeared after action:**
```
click(...) → list_dialogs(application_id="app_...")
  → count > 0? handle each dialog before continuing
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

### Replaying a Recording

Save a recording as JSON in the schema documented in [docs/recording_schema.md](docs/recording_schema.md), then replay it via the MCP tool:

```json
{
  "tool": "replay_recording",
  "arguments": {
    "session_id": "session_001",
    "path": "/abs/path/recording.json",
    "stop_on_error": true
  }
}
```

The replayer routes every step through the same `call_tool` path as a live agent, so logs and evidence are identical.

---

## Running Tests

```bash
python -m pytest
```

Expected:

```
95 passed
```

---

## License

MIT — see [LICENSE](LICENSE).
