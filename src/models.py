from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import Any

CSV_FIELDS = [
    "id",
    "school",
    "department",
    "name",
    "title",
    "email",
    "research",
    "homepage",
    "source_url",
    "selected",
    "status",
    "notes",
    "updated_at",
]

STATUSES = ("new", "drafted", "sent", "skipped", "failed", "need_email")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是"}


@dataclass
class Professor:
    id: str
    school: str
    department: str
    name: str
    title: str = ""
    email: str = ""
    research: str = ""
    homepage: str = ""
    source_url: str = ""
    selected: bool = False
    status: str = "new"
    notes: str = ""
    updated_at: str = ""

    def to_row(self) -> dict[str, str]:
        data = asdict(self)
        data["selected"] = "yes" if self.selected else "no"
        if not data.get("updated_at"):
            data["updated_at"] = _now()
        return {k: "" if data.get(k) is None else str(data.get(k)) for k in CSV_FIELDS}

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "Professor":
        values: dict[str, Any] = {}
        for f in fields(cls):
            raw = (row.get(f.name) or "").strip()
            if f.name == "selected":
                values[f.name] = _as_bool(raw)
            else:
                values[f.name] = raw
        if not values.get("status"):
            values["status"] = "new"
        return cls(**values)

    def merge_from(self, incoming: "Professor") -> None:
        """Keep send/draft state; fill empty contact fields from a new fetch."""
        for key in ("title", "email", "research", "homepage", "source_url", "department"):
            new = getattr(incoming, key).strip()
            old = getattr(self, key).strip()
            if new and (not old or len(new) > len(old)):
                setattr(self, key, new)
        if self.status == "need_email" and self.email:
            self.status = "new"
        self.updated_at = _now()
