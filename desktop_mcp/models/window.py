from __future__ import annotations

from dataclasses import asdict, dataclass, field

from desktop_mcp.models.control import Control


@dataclass
class Window:
    window_id: str
    title: str
    application_id: str | None = None
    active: bool = False
    controls: list[Control] = field(default_factory=list)

    def to_dict(self, include_controls: bool = False) -> dict:
        data = asdict(self)
        if include_controls:
            data["controls"] = [control.to_dict() for control in self.controls]
        else:
            data.pop("controls", None)
        return data
