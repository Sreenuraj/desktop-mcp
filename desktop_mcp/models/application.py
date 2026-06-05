from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Application:
    application_id: str
    process_id: int
    path: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)
