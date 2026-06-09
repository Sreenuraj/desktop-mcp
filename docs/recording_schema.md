# Desktop MCP — Recording JSON Schema

Status: Draft (2026-09-06)
Scope: recorder ↔ MCP round-trip.

A recording is a JSON file describing a sequence of MCP tool calls that, when
replayed against a live `DesktopMCPServer`, reproduce a user-driven session.

The intent is **deterministic re-execution from a recording**: the action
recorder writes a file in this schema; the agent (or a CI job) invokes the
MCP tool [`replay_recording`](../desktop_mcp/server/mcp_server.py) to run it.

This document is the source of truth for both writers (recorder) and readers
(`replay_recording`). The schema below describes the format the recorder is
expected to emit.

---

## File layout

```json
{
  "version": 1,
  "metadata": {
    "recorded_at": "2026-09-06T08:31:12Z",
    "target_app": "calc.exe",
    "notes": "Add 7 + 3 = 10"
  },
  "steps": [
    { "tool": "wait_for_window",
      "arguments": { "title_contains": "Calculator" } },

    { "tool": "window_snapshot",
      "arguments": { "window_id": "win_2098032" } },

    { "tool": "click",
      "arguments": { "control_id": "ctrl_42_7_seven" } },

    { "tool": "click",
      "arguments": { "control_id": "ctrl_42_plus" } },

    { "tool": "click",
      "arguments": { "control_id": "ctrl_42_3_three" } },

    { "tool": "click",
      "arguments": { "control_id": "ctrl_42_equals" } },

    { "tool": "read_text",
      "arguments": { "control_id": "ctrl_42_display" } }
  ]
}
```

### Top-level fields

| Field      | Type     | Required | Description |
|------------|----------|----------|-------------|
| `version`  | integer  | no       | Schema version. Defaults to `1`. Unknown versions are still loaded; new fields are ignored. |
| `metadata` | object   | no       | Free-form metadata (timestamps, target app, human notes). Never used to drive behavior. |
| `steps`    | array    | **yes**  | Ordered list of [step objects](#step-objects). May be empty. |

`replay_recording` also accepts a **bare list** at the top level
(`[ {step}, {step}, ... ]`) for one-off recordings. Prefer the object form
with `steps` so future versions can add metadata without a format break.

### Step objects

Each step is a single MCP tool invocation. The fields mirror the
[`call_tool`](../desktop_mcp/server/mcp_server.py) signature.

| Field        | Type    | Required | Description |
|--------------|---------|----------|-------------|
| `tool`       | string  | **yes**  | Name of the MCP tool, e.g. `click`, `enter_text`, `wait_for_window`. Must exist in the server's tool registry — unknown names produce a structured `UNKNOWN_TOOL` error. |
| `arguments`  | object  | no       | Arguments payload passed to the tool. Defaults to `{}`. Aliased as `args` for legacy recordings. |
| `delay_ms`   | integer | no       | _Reserved_. Not currently honored by `replay_recording`. Recorders may emit it; readers MUST tolerate it. |
| `expect`     | object  | no       | _Reserved_. Future support for inline assertions (`expect.value == "10"`). Readers MUST tolerate it. |

The MCP `session_id` is **session-bound by the replayer**:
`replay_recording` injects `session_id` into every step's `arguments` if the
step omits it. Recordings can (and should) be written without a hard-coded
`session_id` so the same file is replayable from any session.

---

## Control ID parity

For the round-trip to work, the recorder MUST emit `control_id` values
using the same scheme the MCP server uses, so a recorded step's
`{"tool": "click", "arguments": {"control_id": "ctrl_…"}}` resolves the
same control when replayed.

The current scheme (`uia_adapter._get_control_id`) is:

```
ctrl_<runtime_id_part_0>_<runtime_id_part_1>_…
```

i.e. the UIA `RuntimeId` joined by underscores, prefixed with `ctrl_`.
Recordings made by the action recorder and recordings made by the agent's
own `window_snapshot` calls share this format. The recorder is already
correct (see `desktop_mcp.recorder.engine`); this section documents the
contract so future schema changes don't drift.

---

## Replay semantics

`replay_recording` executes steps in order and returns a structured report:

```json
{
  "path": "/abs/path/recording.json",
  "session_id": "sess_…",
  "steps_total": 7,
  "steps_executed": 7,
  "steps_succeeded": 6,
  "steps_failed": 1,
  "aborted": true,
  "results": [
    { "step": 0, "tool": "wait_for_window", "success": true },
    …,
    { "step": 6, "tool": "read_text",
      "success": false,
      "error": { "code": "CONTROL_NOT_FOUND",
                 "message": "Control not found: ctrl_42_display" } }
  ]
}
```

Behavior:

- Each step is run through `DesktopMCPServer.call_tool`, so logging,
  evidence capture, and the MCP error envelope behave identically to a
  live agent run. **There is no special path for replay**; that's by design.
- `stop_on_error` (default `true`) aborts on the first failing step.
  Set to `false` to attempt every step and collect all failures.
- Recordings are **not** retried automatically. The agent decides whether
  to re-replay after fixing the underlying problem.

---

## Producing a recording from the recorder

The action recorder UI (`desktop-mcp-recorder`) emits events in its own
internal format. A converter that turns those events into this schema is
out of scope for the current iteration. When that converter ships, it MUST:

1. Use the `control_id` scheme described above (no opaque ids).
2. Emit one step per logical action — coalesce multi-key typing into a
   single `enter_text` step, not one `press_keys` per character.
3. Insert `wait_for_window` / `wait_for_control` steps after any action
   that triggers navigation, so replays don't race the target app.

Until that converter exists, recordings can be **hand-written** for
regression tests (see ``tests/test_replay.py`` for examples).
