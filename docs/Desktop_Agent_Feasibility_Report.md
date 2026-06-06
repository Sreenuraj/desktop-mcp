# Desktop Agent
## Phase 0 - Technical Feasibility Report

## 1. Executive Summary

This report validates the technical feasibility of automating enterprise Windows desktop applications using Python and Microsoft UI Automation (UIA) via `pywinauto`.

Based on our technical spike and research:
- **Feasibility:** HIGH. The combination of `pywinauto` with the UIA backend and native Windows API bindings provides complete access to the desktop control tree, process launching, window state control, and basic input interactions.
- **Suitability for Agentic Workflows:** HIGH. Structuring control trees into stable, queryable control lists enables LLM-based agents to reliably locate and interact with interface elements without relying on fragile coordinate-based clicks.

---

## 2. Core Technology Stack Assessment

### 2.1 pywinauto (UIA Backend)
`pywinauto` acts as the primary wrapper for Microsoft UI Automation. 
- **Strengths:** Out-of-the-box support for UIA control patterns (`InvokePattern`, `ValuePattern`, `SelectionPattern`, etc.), window handle binding, and robust input simulation (`click_input`, `type_keys`).
- **Limitations:** Performance can degrade on large or deeply nested control trees. To mitigate this, tree snapshots should be filtered or depth-limited.

### 2.2 comtypes & UIAutomationCore
For advanced use cases (e.g. customized virtual grids or custom SSO dialogs), direct COM interaction using `comtypes` is feasible but complex. The default `pywinauto` wrappers cover 95% of standard WPF, WinForms, and native controls.

### 2.3 Process and Window Utilities
`psutil` is suitable for resolving application process trees and process IDs. `win32gui` and `win32process` (from `pywin32`) are used for low-level window handle resolution, window enumeration, and identifying the foreground window.

---

## 3. Key Capability Feasibility

### 3.1 Control Discovery & Hierarchy Extraction
- **UIA Control Types:** Standard controls (Buttons, Edits, ComboBoxes, Grids) expose clear UIA control types, automation IDs, and names.
- **Control Identifiers:** UIA elements provide a unique `runtime_id` (a tuple of integers) representing the element uniquely within the OS session. This provides a stable identifier for stateless MCP tool requests.

### 3.2 Desktop & Grid Extraction
Enterprise applications make heavy use of DataGrids.
- **Extraction Method:** DataGrids can be parsed by traversing child elements (`DataItem` or `Row` type) and mapping cell contents by index to header columns.
- **Handling Virtualization:** If rows are virtualized (rendered only when scrolled into view), standard tree traversal will only extract visible rows. Supporting full virtualized grids will require using the `ScrollPattern` or keyboard inputs (`{DOWN}` key events) to bring hidden rows into view.

### 3.3 Browser Reattachment & Microsoft SSO
- **SSO Flow:** Applications redirecting to browsers (such as Edge/Chrome) for Microsoft SSO can be detected by monitoring new top-level browser windows.
- **Detection Method:** List open windows to identify browser processes (`chrome.exe`, `msedge.exe`).
- **Reattachment:** The agent can attach to the browser window via its HWND and automate the UIA tree of the browser login page, then return focus to the main desktop application upon successful redirection.

---

## 4. Known Risks and Mitigation Strategies

| Risk | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **Deeply Nested Control Trees** | High (leads to slow tool execution) | Implement depth-limited traversal and node-type filtering in UIA queries. |
| **Custom Rendered Controls** | Medium (no UIA metadata) | Fall back to name-based heuristic matching or mouse click coordinate mapping via bounding boxes. |
| **UIA Thread Blocking** | Low | Execute UIA calls on a separate background thread or ensure short timeouts on COM operations. |
| **OS Platform Lock-in** | Medium | Isolate all OS-specific API calls to `WindowsUIAutomationAdapter` and default to an in-memory mock adapter on non-Windows platforms. |
