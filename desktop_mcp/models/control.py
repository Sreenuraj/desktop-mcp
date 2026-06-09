from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Control:
    id: str
    name: str
    type: str
    automation_id: str | None = None
    enabled: bool = True
    visible: bool = True
    focused: bool = False
    value: str | None = None
    bounds: dict[str, int] = field(default_factory=dict)
    patterns: list[str] = field(default_factory=list)
    children: list["Control"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def control_id(self) -> str:
        """Alias for ``id`` — used by the server layer for consistency."""
        return self.id

    def to_dict(self, include_children: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_children:
            data.pop("children", None)
        return data
