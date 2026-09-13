from __future__ import annotations

import os

import httpx

APP_VERSION = "1.0.0"
UPDATE_URL = os.getenv("UPDATE_URL", "").strip()


def check_update(timeout: float = 3.0) -> dict | None:
    if not UPDATE_URL:
        return None
    try:
        resp = httpx.get(UPDATE_URL, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        latest = str(data.get("version") or "")
        if latest:
            return {"version": latest, "url": str(data.get("url") or ""), "notes": str(data.get("notes") or "")}
    except Exception:
        return None
    return None
