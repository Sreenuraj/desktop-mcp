# PostQode Desktop MCP

Initial implementation of the PostQode Desktop MCP framework described in `docs/`.

The current code provides:

- Standard Desktop MCP response envelopes
- Session lifecycle management
- Application, window, snapshot, discovery, interaction, text, selection, grid, validation, evidence, and browser-auth tool routing
- In-memory adapter for tests and local development
- Windows adapter placeholder that keeps platform-specific automation isolated

Phase 1 targets Windows automation through a future `pywinauto`/UI Automation adapter while keeping the agent-facing contract platform independent.
