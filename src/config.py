from __future__ import annotations

from typing import Any

import yaml
from dotenv import load_dotenv
import os

from paths import ENV_FILE, PROFILE_FILE, SCHOOLS_FILE, SETTINGS_FILE

load_dotenv(ENV_FILE)


def _read_yaml(path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误: {path}")
    return data


def load_profile() -> dict[str, Any]:
    if not PROFILE_FILE.exists():
        example = PROFILE_FILE.with_name("profile.example.yaml")
        if example.exists():
            PROFILE_FILE.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    data = _read_yaml(PROFILE_FILE)
    if not data.get("name") or not data.get("email"):
        raise ValueError("请先完成配置向导，或在 config/profile.yaml 填写姓名和邮箱")
    return data


def save_profile(data: dict[str, Any]) -> None:
    with PROFILE_FILE.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_schools() -> list[dict[str, str]]:
    data = _read_yaml(SCHOOLS_FILE)
    sources = data.get("sources") or []
    return [s for s in sources if isinstance(s, dict)]


def load_settings() -> dict[str, Any]:
    data = _read_yaml(SETTINGS_FILE)
    fetch = data.get("fetch") or {}
    send = data.get("send") or {}
    return {
        "timeout_seconds": int(fetch.get("timeout_seconds", 25)),
        "max_bytes": int(fetch.get("max_bytes", 2_000_000)),
        "delay_seconds": float(fetch.get("delay_seconds", 1.5)),
        "max_page_chars": int(fetch.get("max_page_chars", 24000)),
        "max_homepage_chars": int(fetch.get("max_homepage_chars", 8000)),
        "max_enrich_per_run": int(fetch.get("max_enrich_per_run", 30)),
        "verify_ssl": bool(fetch.get("verify_ssl", True)),
        "max_per_day": int(send.get("max_per_day", 10000)),
        "interval_seconds": int(send.get("interval_seconds", 120)),
        "bulk_interval_seconds": int(send.get("bulk_interval_seconds", 60)),
        "require_confirm": bool(send.get("require_confirm", True)),
    }


def llm_config() -> dict[str, str]:
    return {
        "base_url": os.getenv("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        "api_key": os.getenv("LLM_API_KEY", "").strip(),
        "model": os.getenv("LLM_MODEL", "deepseek-chat").strip(),
    }


def smtp_config() -> dict[str, Any]:
    port = int(os.getenv("SMTP_PORT", "465"))
    ssl_raw = os.getenv("SMTP_SSL", "true").strip().lower()
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": port,
        "use_ssl": ssl_raw in {"1", "true", "yes"} or port == 465,
        "user": os.getenv("SMTP_USER", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", "").strip(),
        "from_name": os.getenv("SMTP_FROM_NAME", "").strip(),
    }
