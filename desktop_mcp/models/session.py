from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Session:
    session_id: str
    applications: set[str] = field(default_factory=set)
    windows: set[str] = field(default_factory=set)
    logs: list[dict] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "applications": sorted(self.applications),
            "windows": sorted(self.windows),
            "logs": self.logs,
            "start_time": self.start_time,
        }
