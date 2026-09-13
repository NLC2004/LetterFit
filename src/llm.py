from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from config import llm_config


def _client() -> OpenAI:
    cfg = llm_config()
    if not cfg["api_key"]:
        raise RuntimeError("未配置 LLM_API_KEY。请复制 .env.example 为 .env 并填写。")
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=60, max_retries=2)


def complete(system: str, user: str, temperature: float = 0.3) -> str:
    cfg = llm_config()
    resp = _client().chat.completions.create(
        model=cfg["model"],
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def complete_json(system: str, user: str, temperature: float = 0.1) -> Any:
    text = complete(system, user, temperature=temperature)
    return parse_json(text)


def parse_json(text: str) -> Any:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", raw)
        if not match:
            raise
        return json.loads(match.group(1))
