# Desktop MCP

Desktop MCP is a Model Context Protocol (MCP) server designed for AI-driven automation of Windows desktop applications. It exposes desktop UI controls as structured MCP tools so that AI agents can launch processes, inspect controls, enter text, perform mouse clicks, read grids, and capture screenshots without relying on fragile coordinate-based scripts.

---

## Capabilities

- **Session Management**: Isolated automation sessions per agent workflow.
- **Application Control**: Launch, attach to, or close applications.
- **Window Management**: Window list, focus window, maximize, minimize, close, or wait for window creation.
- **Hierarchical Snapshots**: Recursive retrieval of UI automation trees with smart filtering to remove layout-only elements (e.g. anonymous panes).
- **Element Interaction**: Pattern-based inputs (clicks, keypresses, checking checkboxes, dropdown/tab selection) with automated coordinate/typing fallbacks.
- **Grid Framework**: Read, edit, search, and select row data from enterprise `DataGrid` and `Table` elements.
- **Validation**: High-reliability retries on element waits, state assertions, and automatic screenshot captures on failure.

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
   *Alternatively, run `python examples/codegen_recorder.py -a "Calculator"`.*

### UI and Console Controls
- **Floating UI Overlay**: On Windows, starting the recorder opens a dark-themed, always-on-top floating window showing a **● Recording** status. Your manual inputs (clicks, keypresses, text entries) will display there in real-time.
- **Pause & Resume**: Use the **Pause / Resume** button in the floating UI to temporarily suspend recording. While paused, the status displays "Paused" (yellow) and no user actions are captured, allowing you to navigate/interact without recording clutter.
- **Copy Transcript**: Click **Copy Transcript** on the floating window to copy all recorded actions to your clipboard.
- **Terminal Fallback**: If Tkinter is not installed on the system, the recorder will output a warning and automatically fall back to **Console-only Mode**. In this mode, actions continue to print to the terminal in real-time, and you can copy the transcript directly from the console output or press `Ctrl+C` to exit.
- **Mock Mode**: On macOS or Linux, running the recorder will output an example interaction transcript in simulated mode for testing purposes.

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

The server exposes the following toolsets:

### 1. Sessions
- `create_session`: Creates a new session ID.
- `close_session`: Teardown session and release locks.

### 2. Applications
- `launch_application`: Launch an application executable.
- `attach_application`: Connect to a running process ID.
- `close_application`: Closes the application.

### 3. Windows
- `list_windows`: Lists all top-level windows.
- `activate_window`: Brings the window into focus.
- `wait_for_window`: Wait for a window with matching title to open.
- `close_window`: Closes the target window.
- `maximize_window` / `minimize_window`: Resize the window.

### 4. Snapshots & Discovery
- `desktop_snapshot` / `window_snapshot`: Returns details and flat control lists.
- `control_tree`: Returns recursive, hierarchical control nodes.
- `find_control` / `find_controls` / `get_control`: Inspect and locate UI elements.

### 5. Interactions
- `click` / `double_click` / `right_click` / `hover` / `focus`: Mouse and focus actions.
- `enter_text` / `append_text` / `clear_text` / `read_text`: Keyboard and input actions.
- `select_dropdown` / `select_tab` / `select_radio` / `check` / `uncheck`: Selection widgets.

### 6. Validation
- `control_exists` / `wait_for_control`: Verification & wait methods.
- `assert_text` / `assert_control_state`: Check values. (Captures a screenshot automatically on failure).

### 7. Grids
- `read_table`: Returns columns and rows from a grid.
- `find_row`: Searches a grid row matching criteria.
- `select_row`: Selects the row at `row_index`.
- `edit_cell` / `read_cell`: Modifies or reads a specific cell value.

### 8. Evidence & Browser Authentication
- `capture_window` / `capture_desktop`: Screengrabs.
- `start_recording` / `stop_recording`: Capture video evidence of workflows.
- `wait_for_browser` / `attach_browser_window`: Bypasses OAuth/SSO login screens by switching control.

---

## Running Tests

Verify your installation by running the test suite:

```bash
python -m pytest
```

Expected result:

```text
57 passed
```
