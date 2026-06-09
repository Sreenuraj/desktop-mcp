from __future__ import annotations

from typing import Any


class DesktopMCPError(Exception):
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}


class InvalidRequestError(DesktopMCPError):
    code = "INVALID_REQUEST"


class SessionNotFoundError(DesktopMCPError):
    code = "SESSION_NOT_FOUND"


class AppNotFoundError(DesktopMCPError):
    code = "APP_NOT_FOUND"


class WindowNotFoundError(DesktopMCPError):
    code = "WINDOW_NOT_FOUND"


class ControlNotFoundError(DesktopMCPError):
    code = "CONTROL_NOT_FOUND"


class UnsupportedControlError(DesktopMCPError):
    code = "UNSUPPORTED_CONTROL"


class ControlDisabledError(DesktopMCPError):
    code = "CONTROL_DISABLED"


class SnapshotEmptyError(DesktopMCPError):
    """Raised when UIA returns an empty control tree for a window that should have children.

    The agent should treat this as a recoverable error: try activate_window then
    window_snapshot again, or fall back to capture_window for visual inspection.
    """

    code = "SNAPSHOT_EMPTY"


class UnknownToolError(DesktopMCPError):
    """Raised when the agent calls a tool name that does not exist."""

    code = "UNKNOWN_TOOL"
