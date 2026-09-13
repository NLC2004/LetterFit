from __future__ import annotations

import hashlib
import json
from datetime import datetime

from models import CSV_FIELDS, Professor
from paths import TARGETS_FILE, SENT_LOG_FILE, DRAFTS_DIR


def make_id(school: str, name: str, email: str) -> str:
    raw = f"{(school or '').strip()}|{(name or '').strip()}|{(email or '').strip().lower()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def load_targets() -> list[Professor]:
    if not TARGETS_FILE.exists():
        return []
    import csv

    rows: list[Professor] = []
    with TARGETS_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not any((row.get(k) or "").strip() for k in ("name", "email")):
                continue
            rows.append(Professor.from_row(row))
    return rows


def save_targets(items: list[Professor]) -> None:
    import csv

    TARGETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TARGETS_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for item in items:
            writer.writerow(item.to_row())


def _index_keys(person: Professor) -> list[str]:
    keys = [f"{person.school}|{person.name}"]
    email = (person.email or "").strip().lower()
    if email:
        keys.append(email)
    return keys


def upsert_targets(existing: list[Professor], incoming: list[Professor]) -> tuple[list[Professor], int]:
    index: dict[str, int] = {}
    for i, item in enumerate(existing):
        for key in _index_keys(item):
            index[key] = i

    added = 0
    for person in incoming:
        hit = next((index[k] for k in _index_keys(person) if k in index), None)
        if hit is not None:
            existing[hit].merge_from(person)
            for key in _index_keys(existing[hit]):
                index[key] = hit
        else:
            existing.append(person)
            idx = len(existing) - 1
            for key in _index_keys(person):
                index[key] = idx
            added += 1
    save_targets(existing)
    return existing, added


def selected_targets(items: list[Professor] | None = None) -> list[Professor]:
    items = items if items is not None else load_targets()
    return [p for p in items if p.selected and p.status != "sent"]


def draft_path(person_id: str):
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    return DRAFTS_DIR / f"{person_id}.json"


def save_draft(person_id: str, payload: dict) -> None:
    path = draft_path(person_id)
    payload = dict(payload)
    payload["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_draft(person_id: str) -> dict | None:
    path = draft_path(person_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def append_sent_log(entry: dict) -> None:
    SENT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = dict(entry)
    entry.setdefault("at", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    with SENT_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def sent_today_count() -> int:
    if not SENT_LOG_FILE.exists():
        return 0
    today = datetime.now().strftime("%Y-%m-%d")
    n = 0
    for line in SENT_LOG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(item.get("at", "")).startswith(today) and item.get("status") == "sent":
            n += 1
    return n
