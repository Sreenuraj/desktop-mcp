import re

with open("README.md", "r") as f:
    readme = f.read()

# Replace the Tool Categories section
new_categories = """## Tool Categories

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

---"""

readme = re.sub(r'## Tool Categories.*?(?=## Running Tests)', new_categories + '\n\n', readme, flags=re.DOTALL)

with open("README.md", "w") as f:
    f.write(readme)

# Update API Spec
with open("docs/Desktop_MCP_API_Specification_v1.md", "r") as f:
    spec = f.read()

# Remove deleted sections from the spec. We will just rewrite the file with the simplified spec.
