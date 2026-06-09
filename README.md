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

The server exposes the following refined, highly-capable core tools (18 tools):

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

### 4. Snapshots & Discovery
- `window_snapshot`: **[Core Discovery]** Returns a flat list of all interactive controls.
- `control_tree`: Returns recursive, hierarchical control nodes.

### 5. Interactions
- `click`: Interact with any element. Accepts an `action` argument (`left`, `right`, `double`, `hover`) and intelligently handles checkboxes, tabs, and tree nodes.
- `enter_text` / `read_text`: Safely input or extract text.
- `press_keys`: **[NEW]** Send raw PyWinAuto keys (e.g., `{TAB}`, `^c`) to the active window. Extremely crucial for legacy app support.
- `select_item`: Direct API for picking items from Dropdowns/ComboBoxes/ListBoxes.
- `drag_drop`: Drag and drop from one control to another.

### 6. Grids
- `read_table`: Returns columns and rows from a DataGrid.

### 7. Evidence & Reporting
- `capture_window` / `capture_desktop`: High-resolution screengrabs.
- `start_recording` / `stop_recording`: Capture video evidence of workflows.
- `generate_report`: Generates a Markdown audit log of the session.

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

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

