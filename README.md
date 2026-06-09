# Desktop MCP

Desktop MCP is a Model Context Protocol (MCP) server designed for AI-driven automation of Windows desktop applications. It exposes desktop UI controls as structured MCP tools so that AI agents can launch processes, inspect controls, enter text, perform mouse clicks, read grids, and capture screenshots — **without relying on fragile coordinate-based scripts and without requiring the target window to be in foreground**.

---

## What's New (Phase 1 + 2 — 2026-09-06)

### Phase 1 — Observable Failures
The server no longer hides failures behind success-shaped responses. Every tool now gives the agent enough information to self-correct.

| Change | Detail |
|---|---|
| `SNAPSHOT_EMPTY` error | `window_snapshot` raises a structured error (not `controls: []`) when UIA returns an empty tree. Includes `uia_state`, `is_foreground`, `took_ms`, and a `hint` with the recovery steps. |
| `isError: true` | Every error response sets `isError: true` on the MCP envelope — the canonical signal LLM-side libraries respect. |
| `activate_window` observable state | Returns `is_foreground`, `became_foreground`, `foreground_title`, `attempts`, `total_ms` instead of `{}`. |
| `window_snapshot` enriched | Returns `controls_count`, `capture_method` (`uia_children`/`uia_descendants`), `uia_state` (`live`/`empty`/`denied`), `took_ms`. |
| `control_tree` enriched | Returns `tree_node_count` and `took_ms`. |
| `desktop_snapshot` restored | Was removed in `5bb4eb8`; agents in production still call it. Restored as a thin wrapper over `list_windows` + per-window snapshot. |
| `wait_for_window` actually waits | Now polls every 250 ms up to `timeout_ms` (default 10 000 ms). Previously returned immediately. |
| `UNKNOWN_TOOL` guard | Unknown tool names return a structured error with `details.valid_tools` listing all 25 valid tool names. |
| Schema cleanup | `session_id` required on all tools; `additionalProperties: false` on all schemas. |

### Phase 2 — Foreground-Independent Interactions
Most interactions now work without bringing the target window to foreground.

| Change | Detail |
|---|---|
| Pattern-first dispatch | `click` on a Button → `InvokePattern.Invoke()` (no foreground). CheckBox → `TogglePattern`. ListItem/MenuItem/TabItem → `SelectionItemPattern`. `enter_text` → `ValuePattern.SetValue()`. Falls back to `click_input`/`type_keys` only if the pattern fails. |
| New actions | `toggle`, `expand_node`, `collapse_node`, `scroll_into_view` — all via UIA patterns, no foreground required. |
| Proper foreground acquisition | Replaces the Alt-key hack with the documented Windows sequence: `AllowSetForegroundWindow` → `AttachThreadInput` → `BringWindowToTop` → `SetForegroundWindow` → `SwitchToThisWindow`. |
| `restore_foreground_after_action` | Default `true`. After any action that required foreground, VSCode is restored to foreground automatically. Result includes `foreground_restored: bool`. |
| Enriched interaction results | All interaction tools return `method`, `required_foreground`, `foreground_taken`, `foreground_restored`, `took_ms`. |

---

## Capabilities

- **Session Management**: Isolated automation sessions per agent workflow.
- **Application Control**: Launch, attach to, or close applications.
- **Window Management**: Window list, focus window, maximize, minimize, close, or wait for window creation (with real polling).
- **Hierarchical Snapshots**: Recursive retrieval of UI automation trees with smart filtering. Empty trees raise `SNAPSHOT_EMPTY` with recovery hints instead of silently succeeding.
- **Pattern-First Interactions**: UIA patterns (`Invoke`, `Toggle`, `Value`, `SelectionItem`, `ExpandCollapse`, `ScrollItem`) are tried before mouse synthesis — most actions work without foreground.
- **Foreground Restoration**: VSCode stays in foreground throughout the agent session by default.
- **Grid Framework**: Read, edit, search, and select row data from enterprise `DataGrid` and `Table` elements.
- **Evidence Collection**: High-resolution screenshots, GIF recordings, and Markdown audit logs.

---

## Prerequisites

- **Python**: version 3.12 or newer.
- **Operating System**: Windows 10/11 (for UIA adapter).
  - *Note*: An in-memory adapter is included for local development and testing on macOS/Linux.
- **System Permissions**: Accessibility/UI Automation access enabled for the target applications.

---

## Installation

### Option A: Quick Setup (Recommended)

Run the setup script for your platform to automatically create the virtual environment, install dependencies, and generate your custom MCP JSON config block:

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

Create a virtual environment and install the package:

```bash
# Create and activate environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in editable mode with development dependencies
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

For Windows desktop automation, install the Windows extras:

```bash
python -m pip install -e ".[dev,windows]"
```

---

## Running the Server

> [!NOTE]
> You **do not** need to manually start or keep the server running in the background. Because this is a `stdio`-based MCP server, your AI client (e.g., Claude Desktop or Cursor) will automatically spawn the server process when it starts and stop it when it closes.
>
> Simply complete the setup steps, add the generated configuration to your client's settings, and the client will manage the lifecycle of the server for you.

If you want to run the stdio server manually for debugging or testing:

```bash
python -m desktop_mcp.server.stdio
```

If the package is installed in editable mode, you can also use:

```bash
desktop-mcp
```

The server reads JSON-RPC requests from stdin and writes JSON-RPC responses to stdout.

---

## Interaction Recorder (Codegen)

The Desktop MCP includes a UIA-native interaction recorder (similar to Playwright's Codegen) that listens to global UIA events on Windows and logs your manual inputs. It uses stable UIA properties (automation IDs, names, types) instead of fragile screen coordinates.

### Running the Recorder

We provide automated setup and execution scripts that handle elevating privileges, creating/activating virtual environments, and installing all platform prerequisites automatically.

#### Quick Run (Recommended)
- **Windows (PowerShell/CMD)**: Double-click or run `run_recorder.bat` (or execute `.\run_recorder.ps1` in PowerShell). This script will:
  1. Detect if it is running as Administrator (relaunching with elevated privileges if needed).
  2. Create/update the `.venv` virtual environment.
  3. Install all Windows and UIA-specific dependencies automatically.
  4. Launch the interaction recorder.
  *Note*: You can specify a target application to focus and minimize distractions:
  ```powershell
  .\run_recorder.ps1 -a Calculator
  # or
  run_recorder.bat --app Calculator
  ```
- **macOS / Linux**: Run `./run_recorder.sh`. This will prepare the virtual environment and launch the recorder in simulated/mock mode.

#### Manual/Global Run (Windows)
1. Open a command prompt or PowerShell window **as Administrator** (required to listen to focus events across administrative applications).
2. Start the recorder:
   ```bash
   desktop-mcp-recorder --app "Calculator"
   ```
   *Alternatively, run `python -m desktop_mcp.recorder.main -a "Calculator"`.*

### UI and Console Controls

#### 1. Interactive Config Screen (On Startup)
If you start the recorder without specifying a target application via command-line arguments:

> [!TIP]
> **Open your target application first**: The dropdown list dynamically enumerates currently running/open windows. If your application is not running yet, open it before launching the recorder, or enter/browse to its executable path in the manual entry field to auto-launch it.

- **Target Application Dropdown**: A search-as-you-type combobox containing all active window titles is displayed. Typing in the box filters the dropdown dynamically.
- **Executable File Browser**: A manual path entry field with a **Browse...** button that opens a native file dialog so you can easily select a `.exe` binary.
- **Workspace Minimization**: A checkbox to toggle whether all other windows are minimized on startup (enabled by default).
- **Desktop Recording**: A fallback button to record the full desktop screen (no specific application focus/minimization).

#### 2. Interactive Console Fallback Setup
If Tkinter is not installed:
- The terminal displays a **Console Setup Menu** showing a numbered list of all open window titles.
- It prompts you to select a target application by entering its number, typing a title, entering a path, or pressing Enter to record the full desktop.

#### 3. Recording Overlay & Controls
- **Floating UI Overlay**: Once recording starts, a dark-themed, always-on-top floating window displays your captured actions in real-time.
- **Dynamic Output Formats**: Select output view formats (Python pywinauto, Desktop MCP tools, or Action Log) using the **Format** dropdown on the right of the toolbar. You can switch formats at any time (**both while recording and after recording**).
- **Pause & Resume**: Click **Pause** to temporarily suspend event logging, and click **Resume** to restart capturing.
- **Stop & Graceful Close**: Click **Stop** to stop recording. The recorder will prompt you (Yes/No dialog) to ask if you want to close the target application under test, closing it gracefully if confirmed. Closing the recorder window also prompts to close the target app.
- **Copy & Clear**: Click **Copy** to copy all recorded actions to your clipboard (without line numbers), and click **Clear** to clear the current logs.
- **Mock Mode**: On macOS or Linux, the config wizard and recording overlay run in simulated/mock mode for developer testing.

---

## Configuring the Adapter

The Desktop MCP server dynamically selects the adapter to use:
- **Default (Windows)**: Uses `WindowsUIAutomationAdapter` automatically when run on Windows (`win32`).
- **Fallback**: On non-Windows platforms (macOS/Linux), it automatically falls back to `InMemoryDesktopAdapter`.
- **Manual Override**: You can explicitly select the adapter by setting the `DESKTOP_MCP_ADAPTER` environment variable to either `"uia"` or `"memory"`.

---

## Agent Configuration Examples

### Claude Desktop / Cursor Settings

Add this configuration to your client settings (`settings.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "desktop-mcp": {
      "command": "python",
      "args": ["-m", "desktop_mcp.server.stdio"],
      "cwd": "C:\\path\\to\\desktop-mcp",
      "env": {
        "DESKTOP_MCP_ADAPTER": "uia"
      }
    }
  }
}
```

If your agent runs inside a virtual environment, point the command to that environment's Python executable:

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

---

## Tool Categories

The server exposes 25 core tools:

### 1. Sessions
- `create_session`: Creates a new session ID.
- `close_session`: Teardown session and release locks.

### 2. Applications
- `launch_application`: Launch an application executable.
- `attach_application`: Connect to a running process ID.
- `close_application`: Closes the application.

### 3. Windows
- `list_windows`: Lists all top-level windows.
- `activate_window`: Brings the window into focus. **Returns observable state** (`is_foreground`, `became_foreground`, `total_ms`) so the agent can verify success.
- `wait_for_window`: **Polls** until a window with matching title appears (250 ms interval, configurable `timeout_ms`). Use immediately after `launch_application`.
- `close_window`: Closes the target window.

### 4. Snapshots & Discovery
- `desktop_snapshot`: Returns a snapshot of **all** visible windows with their controls. Useful for initial discovery.
- `window_snapshot`: **[Core Discovery]** Returns a flat list of all interactive controls. Returns `controls_count`, `capture_method`, `uia_state`. Raises `SNAPSHOT_EMPTY` (with recovery hint) instead of silently returning an empty list.
- `control_tree`: Returns recursive, hierarchical control nodes with `tree_node_count`.

### 5. Interactions
- `click`: Interact with any element. **Pattern-first**: Button→`InvokePattern`, CheckBox→`TogglePattern`, ListItem/Tab/Radio→`SelectionItemPattern`. Accepts `action`: `left`, `right`, `double`, `hover`, `toggle`, `expand_node`, `collapse_node`, `scroll_into_view`. Supports `restore_foreground_after_action` (default `true`).
- `enter_text`: Type text. Uses `ValuePattern.SetValue()` first (no foreground needed).
- `read_text`: Extract text value from a control.
- `press_keys`: Send raw PyWinAuto keys (e.g., `{TAB}`, `^c`) to a control or the active window.
- `select_item`: Direct API for picking items from Dropdowns/ComboBoxes/ListBoxes via `SelectionItemPattern`.
- `drag_drop`: Drag and drop from one control to another.

### 6. Grids
- `read_table`: Returns columns and rows from a DataGrid.

### 7. Evidence & Reporting
- `capture_window`: Screenshot of a specific window. Use as visual fallback when `window_snapshot` returns `SNAPSHOT_EMPTY`.
- `capture_desktop`: Full desktop screenshot.
- `start_recording` / `stop_recording`: Capture GIF evidence of workflows.
- `generate_report`: Generates a Markdown audit log of the session.

### 8. Coordinates (last resort)
- `click_at`: Click at absolute screen coordinates. Requires foreground. Use only when no `control_id` is available.

---

## Agent Recovery Playbook

### Empty control tree after launch
```
launch_application
  → wait_for_window (polls until window appears)
  → window_snapshot
      ↓ SNAPSHOT_EMPTY (isError: true)?
  → activate_window  →  window_snapshot (retry)
      ↓ still empty?
  → capture_window  (visual fallback)
```

### Foreground race (approval prompt stole focus)
```
click(control_id="ctrl_123", restore_foreground_after_action=true)
  → method: "uia_invoke", required_foreground: false   ← ideal, no race possible
  → method: "click_input", foreground_restored: true   ← VSCode restored after action
```

### Unknown tool name
```
error.code == "UNKNOWN_TOOL"
  → error.details.valid_tools  ← full list of valid tool names
```

---

## Running Tests

Verify your installation by running the test suite:

```bash
python -m pytest
```

Expected result:

```text
123 passed
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
