from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MCPError:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


@dataclass(frozen=True)
class MCPResponse:
    success: bool
    data: Any
    error: MCPError | None
    # Phase 1.6: isError is the canonical MCP CallToolResult signal that
    # LLM-side libraries (e.g. Claude's tool-use SDK) respect.
    isError: bool = False

    @classmethod
    def ok(cls, data: Any | None = None) -> "MCPResponse":
        return cls(success=True, data={} if data is None else data, error=None, isError=False)

    @classmethod
    def fail(
        cls,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> "MCPResponse":
        return cls(
            success=False,
            data=None,
            error=MCPError(code=code, message=message, details=details or {}),
            isError=True,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": None if self.error is None else self.error.to_dict(),
            "isError": self.isError,
        }
