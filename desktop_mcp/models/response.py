from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class MCPError:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class MCPResponse:
    success: bool
    data: Any
    error: MCPError | None

    @classmethod
    def ok(cls, data: Any | None = None) -> "MCPResponse":
        return cls(success=True, data={} if data is None else data, error=None)

    @classmethod
    def fail(cls, code: str, message: str) -> "MCPResponse":
        return cls(success=False, data=None, error=MCPError(code=code, message=message))

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": None if self.error is None else self.error.to_dict(),
        }
