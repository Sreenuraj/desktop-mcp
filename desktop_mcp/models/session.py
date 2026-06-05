from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Session:
    session_id: str
    applications: set[str] = field(default_factory=set)
    windows: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "applications": sorted(self.applications),
            "windows": sorted(self.windows),
        }
