"""Structured JSON logging to stderr for Desktop MCP.

The MCP stdio transport reserves stdout for protocol messages; stderr is
free for diagnostic noise.  We emit one JSON object per line so logs can
be machine-parsed by the agent host or by ``jq`` / ``logcli``.

We avoid taking a hard dependency on ``structlog`` — a tiny stdlib-only
JSON formatter is sufficient and keeps the install footprint small.

Usage:

    from desktop_mcp.logging import get_logger, log_tool_call

    log = get_logger(__name__)
    log.info("hello", extra={"tool": "click", "took_ms": 12})

    # OR use the helper for tool-call structured logs:
    log_tool_call(
        tool="click",
        args={"control_id": "ctrl_1"},
        took_ms=12,
        result_kind="success",
    )

Redaction:
    Tool arguments are passed through ``_redact_args`` which drops/masks
    keys that commonly carry secrets (``password``, ``token``, ``secret``,
    ``api_key``, ``value`` when the tool is ``enter_text``).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Environment-variable controls so users can dial verbosity without code edits.
_LOG_LEVEL = os.environ.get("DESKTOP_MCP_LOG_LEVEL", "INFO").upper()
_LOG_FORMAT = os.environ.get("DESKTOP_MCP_LOG_FORMAT", "json").lower()  # json|text

# Keys whose values must never leak into logs.
_REDACT_KEY_PATTERNS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
)

# Tools whose ``value`` argument is sensitive (typed credentials).
_VALUE_SENSITIVE_TOOLS = frozenset({"enter_text"})


class _JSONFormatter(logging.Formatter):
    """One-line JSON formatter.

    Standard log record fields plus everything in ``record.__dict__["extra"]``
    are merged into the output.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": round(record.created, 3),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # ``logging`` flattens ``extra={"k": v}`` into the record's __dict__,
        # so we surface the well-known keys we care about.  Note: we cannot
        # use ``args`` here because LogRecord already owns that name — we
        # use ``tool_args`` internally and surface it as ``args`` on output.
        for key in (
            "tool",
            "tool_args",
            "took_ms",
            "result_kind",
            "error_code",
            "session_id",
            "window_id",
            "control_id",
            "method",
        ):
            if key in record.__dict__:
                out_key = "args" if key == "tool_args" else key
                payload[out_key] = record.__dict__[key]
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        try:
            return json.dumps(payload, default=str, ensure_ascii=False)
        except Exception:
            # Last-ditch fallback so a bad payload never silences logging.
            return json.dumps({
                "ts": payload["ts"],
                "level": payload["level"],
                "logger": payload["logger"],
                "msg": str(payload["msg"]),
            })


_configured = False


def _configure_root() -> None:
    """Attach a single stderr handler to the ``desktop_mcp`` root logger.

    Idempotent — calling multiple times never adds duplicate handlers.
    """
    global _configured
    if _configured:
        return
    root = logging.getLogger("desktop_mcp")
    # Don't propagate to the global root: avoids double-printing when the
    # host application (e.g. VSCode) also configures Python logging.
    root.propagate = False
    root.setLevel(_LOG_LEVEL)

    # Skip if a handler already exists (e.g. tests reuse the logger).
    has_stderr = any(
        isinstance(h, logging.StreamHandler) and h.stream is sys.stderr
        for h in root.handlers
    )
    if not has_stderr:
        handler = logging.StreamHandler(sys.stderr)
        if _LOG_FORMAT == "text":
            handler.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s"
            ))
        else:
            handler.setFormatter(_JSONFormatter())
        root.addHandler(handler)
    _configured = True


def get_logger(name: str = "desktop_mcp") -> logging.Logger:
    """Return a configured logger.

    Always returns a logger under the ``desktop_mcp`` namespace so the
    single stderr handler we install catches it.
    """
    _configure_root()
    if not name.startswith("desktop_mcp"):
        name = f"desktop_mcp.{name}"
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def _redact_value(_value: Any) -> str:
    """Return a placeholder that proves the value existed without leaking it."""
    return "***redacted***"


def _redact_args(tool: str, args: dict[str, Any] | None) -> dict[str, Any]:
    """Return a shallow copy of *args* with sensitive values redacted.

    Rules:
      - Any key whose lowercase form contains one of ``_REDACT_KEY_PATTERNS``.
      - The ``value`` key when the tool is in ``_VALUE_SENSITIVE_TOOLS``.

    Non-dict inputs (e.g. None) round-trip as ``{}``.
    """
    if not isinstance(args, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in args.items():
        lk = str(k).lower()
        if any(p in lk for p in _REDACT_KEY_PATTERNS):
            out[k] = _redact_value(v)
        elif k == "value" and tool in _VALUE_SENSITIVE_TOOLS:
            out[k] = _redact_value(v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------

def log_tool_call(
    tool: str,
    args: dict[str, Any] | None = None,
    took_ms: int | None = None,
    result_kind: str = "success",
    error_code: str | None = None,
    session_id: str | None = None,
    logger: logging.Logger | None = None,
) -> None:
    """Emit a single structured log entry for a tool invocation.

    Fields: ``tool, args_redacted, took_ms, result_kind, error_code?``.
    """
    log = logger or get_logger("desktop_mcp.tool")
    # ``args`` is a reserved attribute on Python's ``LogRecord`` — we route
    # the redacted payload through ``tool_args`` and let ``_JSONFormatter``
    # rename it back to ``args`` on output.
    extra = {
        "tool": tool,
        "tool_args": _redact_args(tool, args),
        "took_ms": took_ms,
        "result_kind": result_kind,
    }
    if error_code:
        extra["error_code"] = error_code
    if session_id:
        extra["session_id"] = session_id

    level = logging.INFO if result_kind == "success" else logging.WARNING
    log.log(level, f"tool_call {tool} {result_kind}", extra=extra)


class ToolCallTimer:
    """Context manager that times a tool call and logs the outcome.

    Example::

        with ToolCallTimer("click", payload, session_id=sid) as t:
            result = adapter.interact(...)
            t.result_kind = "success"
    """

    __slots__ = ("tool", "args", "session_id", "result_kind", "error_code", "_t0")

    def __init__(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> None:
        self.tool = tool
        self.args = args
        self.session_id = session_id
        self.result_kind: str = "success"
        self.error_code: str | None = None
        self._t0 = 0.0

    def __enter__(self) -> "ToolCallTimer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        took_ms = int((time.perf_counter() - self._t0) * 1000)
        if exc_type is not None and self.result_kind == "success":
            # Exception escaped without the caller marking failure — record it.
            self.result_kind = "error"
            if self.error_code is None:
                self.error_code = getattr(exc, "code", exc_type.__name__)
        log_tool_call(
            tool=self.tool,
            args=self.args,
            took_ms=took_ms,
            result_kind=self.result_kind,
            error_code=self.error_code,
            session_id=self.session_id,
        )
