# Desktop MCP — Hardening Plan

Status: Draft v1 (2026-09-06)
Owner: @sreenuraj
Goal: Make `desktop-mcp` work *seamlessly* for an LLM agent driving Windows desktop apps (SURGE in particular), with parity-of-feel to Playwright MCP for the web. The agent must be able to discover controls, drive interactions, and recover from errors **without depending on the target app being in foreground**.

---

## Why this plan exists

Real-world session logs (`test_session_logs/178091*`) from a Windows 10/11 machine, agent driving `calc.exe` via PostQode (VSCode-hosted), show **identical fatal failure in 4 consecutive sessions**:

```
create_session         ✓
launch_application     ✓
list_windows           ✓   (Calculator present, active: false)
activate_window        ✓   returns {} — no proof it worked
window_snapshot        ✓   controls: []     ← FAILURE reported as SUCCESS
control_tree           ✓   tree: []         ← FAILURE reported as SUCCESS
desktop_snapshot       ✓   (tool removed in 5bb4eb8 — agent still tries it)
find_controls          ✓   controls: []
activate_window (re)   ✓
capture_window         ✓
…agent gives up, falls back to non-MCP commands
```

**The agent never pressed a single calculator button** across all 4 sessions. The empty-tree / silent-success pattern leaves it nothing to recover from — every retry returns the same "success".

This plan addresses the root causes, not the symptoms.

---

## Root causes (ordered by impact)

### RC1 — Empty result returned as success
`window_snapshot`, `control_tree`, `find_controls`, `activate_window` all return success-shaped responses when they have actually failed. The agent has no signal that anything is wrong, so it loops.

`uia_adapter.get_window`:
```python
for child in children:
    try:
        controls.extend(self._build_control_tree(child))
    except Exception:
        pass   # ← silently swallowed
```

### RC2 — Foreground assumed for every action
Almost every interaction first calls the focus dance (10 attempts × Alt-keystroke hack × ~0.15s each). When PostQode's approval prompt steals focus mid-tool-call, the dance races against VSCode coming back to foreground. Result: a sub-second tool can take 40+ seconds (see ts gap 1780918848499 → 1780918890509 in session 4) and still fail.

UIA exposes invokable patterns (`Invoke`, `Toggle`, `Value`, `SelectionItem`, `ExpandCollapse`, `ScrollItem`) that work **without foreground**. We only use `click_input` (mouse synthesis), which requires foreground.

### RC3 — UWP / suspended-process windows
Modern Windows apps (UWP, MSIX, Win32 with composition) suspend their UIA provider when not foreground. `pywinauto.descendants()` then legitimately returns `[]`. Our adapter treats this identically to a Win32 app that genuinely has no children. SURGE is likely Win32/Delphi/WinForms (not UWP), but the diagnostic muscle developed here makes us robust regardless.

### RC4 — `activate_window` provides no observable state
Returns `{}` whether the window came forward or not. Agent can't tell if it should retry, give up, or proceed.

### RC5 — Tool surface inconsistencies
- `desktop_snapshot` was removed in commit `5bb4eb8` but the agent still calls it (cached in agent context / past examples). Either restore it or document its removal in tool descriptions.
- `wait_for_window` does not actually wait — it returns immediately or raises (see `mcp_server.wait_for_window`). The name lies.
- Tool result schemas are inconsistent (`{}` vs structured objects).
- `isError: true` MCP convention is not set on failures.

### RC6 — Performance: descendant walk across all windows
`_resolve_control` enumerates *all* top-level windows (13 in the session log: 6 File Explorers, Teams, Notepad, browsers, etc.) and walks each on every resolve. Title-based VSCode/Cursor exclusion is fragile.

---

## Phased plan

The phases are ordered so that each one is **independently valuable**. Phase 1 alone would have turned the 4 failed sessions into 4 informative ones, even if no other change shipped.

---

### Phase 1 — Observable failures (P0, ~1 day)

**Goal:** every tool returns enough state for the agent to self-correct. Stop hiding failures behind success-shaped responses.

#### 1.1 Structured "empty result" detection
File: `desktop_mcp/adapters/windows/uia_adapter.py`

In `get_window` and `_build_control_tree`:
- After descendant enumeration, if `controls == []` AND the window is one that *should* have children (i.e. it has a non-trivial `BoundingRectangle` and a non-`Pane`/`Window`-only class), **raise `DesktopMCPError(code="SNAPSHOT_EMPTY", message="UIA returned no descendants for window <title>. Likely causes: window is not foreground / process is suspended / UIA access denied. Try activate_window then window_snapshot again, or use capture_window for visual fallback.", details={"window_id": ..., "title": ..., "is_foreground": bool, "uia_state": "live|empty|denied"})`**.
- Don't `except Exception: pass` inside the traversal — log it at WARN with the element name and re-raise the *first* exception if no descendants were produced.

#### 1.2 Action results include observed state
File: `desktop_mcp/adapters/windows/uia_adapter.py`, `desktop_mcp/server/mcp_server.py`

| Tool | Old result | New result |
|---|---|---|
| `activate_window` | `{}` | `{ "window_id": "...", "is_foreground": true, "became_foreground": true, "foreground_window_id": "...", "foreground_title": "Calculator", "attempts": 1, "total_ms": 87 }` |
| `window_snapshot` | `{ controls, active, title }` | `{ controls, controls_count, capture_method: "uia_children" \| "uia_descendants" \| "fallback", uia_state: "live" \| "empty" \| "denied", took_ms, hint?: "..." }` |
| `control_tree` | `{ tree }` | `{ tree, tree_node_count, took_ms }` |
| `find_controls` | `{ controls }` | `{ controls, count, search_strategy: "by_name" \| "by_automation_id" \| ... }` |
| `click` / `enter_text` / `press_keys` | `{ control_id, action }` | `{ control_id, action, method: "uia_invoke" \| "uia_value" \| "click_input", required_foreground: bool, foreground_taken: bool, took_ms }` |

#### 1.3 Restore `desktop_snapshot` OR explicitly remove from agent vocabulary
The agent in production *still calls it*. Pick one:
- (A) Re-add as a thin wrapper over `list_windows` + per-window `window_snapshot(shallow=True)`. Simplest. Matches what the agent already expects.
- (B) Add a global "tool not found" guard in the MCP server that returns a structured `UNKNOWN_TOOL` error listing valid tool names.

Recommendation: **do both**. (A) for compatibility, (B) for hygiene.

#### 1.4 Fix `wait_for_window` to actually wait
File: `desktop_mcp/server/mcp_server.py`
- Add a polling loop: every 250ms call `list_windows`, return first match. Hard timeout via `timeout_ms` (default 10000). Return error `WINDOW_NOT_FOUND` on timeout.

#### 1.5 Tool schema cleanup
File: `desktop_mcp/server/tool_schemas.py`
- Mark `session_id`, `window_id`, `application_id` consistently as required where needed.
- Set `additionalProperties: false` for tool input schemas.
- Document `isError: true` convention for all error returns.

#### 1.6 MCP `isError` convention
File: `desktop_mcp/server/mcp_server.py`
- When returning an error envelope (`success: false`), also set `isError: true` on the MCP `CallToolResult`. This is the canonical signal LLM-side libraries respect.

**Acceptance criteria for Phase 1:**
- Re-running the calc.exe scenario produces, on first `window_snapshot` after launch, **either** a populated tree **or** a structured error with a recovery hint — never `controls: []` as success.
- The agent's known retry behavior on `SNAPSHOT_EMPTY` (with included hint) leads to a successful follow-up.

---

### Phase 2 — Foreground-independent interactions (P0, ~2 days)

**Goal:** make most interactions work without bringing the target window to foreground. This is the conceptual shift that gives us Playwright-MCP parity-of-feel.

#### 2.1 Pattern-first interaction dispatcher
File: `desktop_mcp/adapters/windows/uia_adapter.py` → `interact()`

Rewrite the action router so it tries UIA patterns *first* and only falls back to mouse synthesis if no suitable pattern exists.

| Intent | Try first | Fallback |
|---|---|---|
| `click` | `InvokePattern.Invoke()` | `click_input()` |
| `toggle` (checkbox) | `TogglePattern.Toggle()` | `click_input()` |
| `select_item` (list/combo) | `SelectionItemPattern.Select()` | `click_input()` |
| `enter_text` | `ValuePattern.SetValue(text)` | focus + `type_keys()` |
| `press_keys` (when targeted at a control with hwnd) | `SendMessage(WM_KEYDOWN/WM_CHAR)` to hwnd | global `keyboard.send()` |
| `expand_node` | `ExpandCollapsePattern.Expand()` | `click_input()` |
| `scroll_into_view` | `ScrollItemPattern.ScrollIntoView()` | scroll synth |
| `read_text` (rich) | `TextPattern.DocumentRange.GetText()` | `Name`/`Value` |

Each call records `method` and `required_foreground=false` on the result.

#### 2.2 New `_with_foreground` boundary
Currently every `interact` wraps in the focus dance. Replace with:
```python
def interact(action, control_id, **kwargs):
    element = self._resolve(control_id)
    method = self._best_method(action, element)
    if method.requires_foreground:
        with self._foreground_lease(element.window()):
            return method.execute(element, **kwargs)
    return method.execute(element, **kwargs)   # no foreground touched
```

Only `click_input`, `type_keys`, drag, and global hotkeys go through `_foreground_lease`.

#### 2.3 Proper foreground acquisition (when truly needed)
File: `desktop_mcp/adapters/windows/uia_adapter.py`
Replace the Alt-key hack with the documented Windows sequence:
1. `AllowSetForegroundWindow(ASFW_ANY)`
2. `AttachThreadInput(currentThread, foregroundThread, TRUE)`
3. `BringWindowToTop(hwnd)`
4. `SetForegroundWindow(hwnd)`
5. `SwitchToThisWindow(hwnd, TRUE)` (last resort)
6. `AttachThreadInput(currentThread, foregroundThread, FALSE)`

If foreground still wasn't acquired, return error `FOREGROUND_DENIED` with the title of the window that has foreground (so the agent knows VSCode/approval grabbed it).

#### 2.4 `restore_foreground_after_action` flag
Optional parameter on every interaction tool (default true). After action completes, return foreground to whatever owned it before (typically VSCode). This is what makes the round-trip feel seamless: the user doesn't see windows flickering.

**Acceptance criteria for Phase 2:**
- A scripted scenario "click Calculator's 7 → click + → click 3 → click =" succeeds while VSCode is in foreground for the *entire* duration. Verified by capturing the foreground window title before/after each action.
- Tool calls report `method: "uia_invoke", required_foreground: false`.

---

### Phase 3 — Snapshot on background windows (P1, ~1-2 days)

**Goal:** populate a control tree even when the target window is not foreground.

#### 3.1 UWP / suspended-process detection
File: `desktop_mcp/adapters/windows/uia_adapter.py`
- Detect via class name: `ApplicationFrameWindow`, `Windows.UI.Core.CoreWindow`.
- Detect via process: `IsImmersiveProcess(hProcess)`.
- Detect via heuristic: descendants returned `[]` once AND window has non-zero `BoundingRectangle` AND `IsEnabled=true`.

#### 3.2 Walk into hosted child for UWP
For `ApplicationFrameWindow`, the actual app UI is in a nested window. Find the child via `EnumChildWindows`, then snapshot the child instead of the host.

#### 3.3 Z-order pre-warm (non-stealing)
- Call `BringWindowToTop(hwnd)` (changes Z-order, does **not** require foreground rights, does **not** activate).
- Sleep 50ms (gives UWP provider a chance to resume).
- Snapshot.
- If snapshot still empty, retry once with a brief actual foreground acquisition (Phase 2.3), snapshot, then restore foreground.

#### 3.4 Property-cached snapshot
Build a `UIA_CacheRequest` with only the properties we need (`Name`, `AutomationId`, `ControlType`, `BoundingRectangle`, `IsEnabled`, `IsOffscreen`, `ClassName`, supported patterns). One COM round-trip per element instead of N.

**Acceptance criteria for Phase 3:**
- Calc.exe `window_snapshot` returns ≥10 button controls while VSCode is in foreground.
- For a Win32 app (Notepad or SURGE), the same holds without any foreground change.

---

### Phase 4 — Playwright-parity tool surface (P1, ~2-3 days)

**Goal:** the agent has every primitive it needs for non-trivial flows.

#### 4.1 Waiters
- `wait_for_window(title_contains | application_id, timeout_ms)` — proper poll.
- `wait_for_control(window_id, name | automation_id | control_type, timeout_ms, state?: "exists" | "enabled" | "visible")`.
- `wait_for_idle(window_id, idle_ms=500, timeout_ms=10000)` — uses UIA `WaitForInputIdle` + a "no tree change for `idle_ms`" settle check.

#### 4.2 Control kinds we don't cover well today
- `expand_control` / `collapse_control` / `scroll_into_view`.
- `select_row(control_id, by_text | by_index)` for DataGrid/ListView.
- `click_cell(control_id, row, column)` and `read_cell(...)`.
- `read_tree(control_id, max_depth)` for TreeView controls (richer than current `read_table`).

#### 4.3 Dialog awareness
- `list_dialogs(application_id)` — returns modal/popup windows owned by the app.
- After every action: if a new modal appeared, include `new_dialogs: [...]` in the action result. Mirrors how Playwright reports new pages.

#### 4.4 Grounding tools
- `get_foreground_window()` — agent can check what's actually focused.
- `get_focused_control(window_id)` — keyboard-focus owner.
- `health_check()` — Windows version, DPI awareness, UIA available, MCP-server's parent PID (so the agent knows what to *exclude* from clicks), pywinauto/comtypes versions.

**Acceptance criteria for Phase 4:**
- An automation can: launch SURGE → wait for main window → wait for "Login" control → enter creds → click Login → wait_for_idle → assert no error dialog appeared → navigate to a patient record. All via documented MCP tools, no `pip`/`python` subshell escapes.

---

### Phase 5 — Performance & polish (P2, ~1 day)

#### 5.1 PID-based exclusion
File: `desktop_mcp/adapters/windows/uia_adapter.py`
- On startup, read `os.getppid()` chain (the MCP server is spawned by VSCode → exclude VSCode + ancestors).
- Cache the exclusion set; don't title-match Cursor/Claude/Warp/JetBrains.

#### 5.2 Element cache
- LRU(256) `control_id → IUIAutomationElement` keyed by `(window_id, generation)`. Bump generation on each `window_snapshot`. Drop stale entries.

#### 5.3 DPI awareness
- Call `SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)` at MCP startup. Without it, `BoundingRectangle` is wrong on multi-monitor / scaled-DPI setups.

#### 5.4 Structured logging
- `structlog` JSON to stderr (MCP allows stderr noise).
- Every tool call logs: `tool, args_redacted, took_ms, result_kind, error_code?`.

#### 5.5 Tests
- `tests/test_uia_adapter_focus.py` — mock UIA, assert pattern-first dispatch.
- `tests/test_mcp_server_error_envelopes.py` — assert `isError: true` is set.
- `tests/test_wait_for_window.py` — fake clock, assert polling + timeout.

---

### Phase 6 — Recorder ↔ MCP round-trip (P2, depends on recorder shape)

Out of scope for now (user said recorder is fine), but for completeness:
- The recorder should emit `control_id` references using the same scheme as the MCP server, so a recorded script can be executed via MCP `click` / `enter_text` calls.
- Provide `replay_recording(path)` MCP tool.

---

## What we are explicitly NOT doing (yet)

- OCR fallback when UIA is denied. Possible Phase 7 but bring real evidence before committing.
- Image-template matching. Same.
- Cross-machine session resume.
- Multi-monitor coordinate translation beyond DPI awareness (5.3).
- Speculative interactions (Playwright's `force: true`).

---

## Order of execution and gating

| Phase | Effort | Gate to next |
|---|---|---|
| 1. Observable failures | 1d | Live test on Windows with calc.exe: must see a real error or a populated tree. |
| 2. Foreground-independent interactions | 2d | Live test: full add operation in Calculator with VSCode foreground throughout. |
| 3. Background snapshot | 1-2d | Live test: populated tree on calc.exe AND on a Win32 app (Notepad/SURGE) while VSCode foreground. |
| 4. Parity tool surface | 2-3d | Live test: full SURGE login + 1 user flow. |
| 5. Performance & polish | 1d | All tests pass; logs are structured; multi-monitor smoke test. |

Total realistic: **7-10 engineering days** spread over 2 weeks with live SURGE validation.

---

## Acceptance: end-to-end agent UX

After Phase 1+2+3, the same calc.exe scenario should look like:

```
create_session         ✓
launch_application     ✓
wait_for_window        ✓   (polls, returns when titled Calculator exists)
window_snapshot        ✓   controls_count: 32, capture_method: uia_descendants
                           → agent sees the 7/8/9/+/= buttons by name
click(name="Seven")    ✓   method: uia_invoke, required_foreground: false
click(name="Plus")     ✓
click(name="Three")    ✓
click(name="Equals")   ✓
read_text(name="display") ✓   value: "10"
```

VSCode never leaves foreground. No approval-prompt focus race. The agent never has to guess.

That is the bar for "Playwright-MCP-equivalent for desktop."

---

## Open questions for the user

1. **Should `restore_foreground_after_action` (Phase 2.4) be on or off by default?** On = invisible-feeling agent (recommended). Off = explicit and predictable for debugging.
2. **For SURGE specifically: do you have admin/UIA-provider access guarantees, or do we need to plan for elevated-process windows (e.g. hospital workstations with restricted UAC)?**
3. **Is there a SURGE test build I can target, or should all dev be against calc.exe + Notepad until SURGE is available?**
4. **Recorder round-trip (Phase 6) — keep deferred or pull forward?**
