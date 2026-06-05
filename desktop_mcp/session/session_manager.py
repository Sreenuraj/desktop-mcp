from __future__ import annotations

from itertools import count

from desktop_mcp.errors import SessionNotFoundError
from desktop_mcp.models.session import Session


class SessionManager:
    def __init__(self) -> None:
        self._counter = count(1)
        self._sessions: dict[str, Session] = {}
        self._active_session_id: str | None = None

    def create_session(self) -> Session:
        session_id = f"session_{next(self._counter):03d}"
        session = Session(session_id=session_id)
        self._sessions[session_id] = session
        self._active_session_id = session_id
        return session

    def close_session(self, session_id: str) -> None:
        if session_id not in self._sessions:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        del self._sessions[session_id]
        if self._active_session_id == session_id:
            self._active_session_id = next(iter(self._sessions), None)

    def get_session(self, session_id: str | None = None) -> Session:
        resolved_id = session_id or self._active_session_id
        if resolved_id is None or resolved_id not in self._sessions:
            raise SessionNotFoundError("No active Desktop MCP session")
        return self._sessions[resolved_id]

    def register_application(self, application_id: str, session_id: str | None = None) -> None:
        self.get_session(session_id).applications.add(application_id)

    def register_window(self, window_id: str, session_id: str | None = None) -> None:
        self.get_session(session_id).windows.add(window_id)
