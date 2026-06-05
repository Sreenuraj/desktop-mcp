class DesktopMCPError(Exception):
    code = "INTERNAL_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


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
