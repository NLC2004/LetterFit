from __future__ import annotations

import json
import time

from config import load_settings
from llm import complete_json
from models import Professor
from store import make_id
from web import (
    compress_for_llm,
    extract_mailtos_and_links,
    fetch_html,
    html_to_text,
    normalize_email,
    regex_emails,
)

LIST_SYSTEM = """你从学院官网「师资/导师介绍」页面整理老师名单。
只根据给定文本提取，不要编造邮箱或主页。
若某位老师没有邮箱，email 填空字符串。
返回 JSON：{"professors":[{"name":"","title":"","email":"","research":"","homepage":""}]}
research 用一句话概括研究方向；homepage 必须是原文中的完整 URL，没有则留空。
不要包含行政人员、辅导员、实验员（除非明确是研究生导师）。"""

HOME_SYSTEM = """你从老师个人主页提取信息。只根据原文，不要编造。
返回 JSON：{"name":"","title":"","email":"","research":"","homepage":""}
research 写成 30-80 字，覆盖具体方向和近期工作，不要空泛形容词。
email 没有就留空。"""


def _clean_person(item: dict, school: str, department: str, source_url: str) -> Professor | None:
    name = (item.get("name") or "").strip()
    email = normalize_email(item.get("email") or "")
    if not name:
        return None
    if len(name) > 20:
        return None
    status = "new" if email else "need_email"
    return Professor(
        id=make_id(school, name, email),
        school=school,
        department=department,
        name=name,
        title=(item.get("title") or "").strip(),
        email=email,
        research=(item.get("research") or "").strip(),
        homepage=(item.get("homepage") or "").strip(),
        source_url=source_url,
        selected=False,
        status=status,
    )


def parse_faculty_list(html: str, source_url: str, school: str, department: str) -> list[Professor]:
    settings = load_settings()
    text = html_to_text(html)
    hints, _ = extract_mailtos_and_links(html, source_url)
    emails = regex_emails(text)
    payload = {
        "source_url": source_url,
        "deterministic_hints": hints[:80],
        "emails_found": emails[:80],
        "page_text": compress_for_llm(text, settings["max_page_chars"]),
    }
    data = complete_json(LIST_SYSTEM, json.dumps(payload, ensure_ascii=False))
    rows = data.get("professors") if isinstance(data, dict) else data
    people: list[Professor] = []
    seen: set[str] = set()
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        person = _clean_person(item, school, department, source_url)
        if not person:
            continue
        key = person.email or f"{person.school}|{person.name}"
        if key in seen:
            continue
        seen.add(key)
        people.append(person)

    if not people:
        for hint in hints:
            person = _clean_person(hint, school, department, source_url)
            if person:
                key = person.email or f"{person.school}|{person.name}"
                if key not in seen:
                    seen.add(key)
                    people.append(person)
    return people


def parse_homepage(html: str, page_url: str) -> dict:
    settings = load_settings()
    text = html_to_text(html)
    emails = regex_emails(text)
    payload = {
        "page_url": page_url,
        "emails_found": emails[:20],
        "page_text": compress_for_llm(text, settings["max_homepage_chars"]),
    }
    data = complete_json(HOME_SYSTEM, json.dumps(payload, ensure_ascii=False))
    if not isinstance(data, dict):
        data = {}
    if not data.get("email") and emails:
        data["email"] = emails[0]
    data["homepage"] = data.get("homepage") or page_url
    return data


def fetch_source(source: dict) -> list[Professor]:
    url = (source.get("faculty_url") or "").strip()
    if not url:
        raise ValueError(f"{source.get('school')} / {source.get('department')} 未填写 faculty_url")
    html = fetch_html(url)
    return parse_faculty_list(
        html,
        url,
        school=(source.get("school") or "").strip(),
        department=(source.get("department") or "").strip(),
    )


def enrich_professor(person: Professor) -> Professor:
    url = (person.homepage or "").strip()
    if not url:
        return person
    html = fetch_html(url)
    info = parse_homepage(html, url)
    if info.get("email") and not person.email:
        person.email = normalize_email(info["email"])
    if info.get("research"):
        person.research = info["research"]
    if info.get("title") and not person.title:
        person.title = info["title"]
    if person.email and person.status == "need_email":
        person.status = "new"
    return person


def enrich_selected(people: list[Professor], delay: float | None = None) -> tuple[list[Professor], int]:
    settings = load_settings()
    wait = settings["delay_seconds"] if delay is None else delay
    budget = settings["max_enrich_per_run"]
    updated = 0
    for person in people:
        if updated >= budget:
            break
        if not person.selected:
            continue
        if not person.homepage:
            continue
        if person.email and person.research:
            continue
        enrich_professor(person)
        updated += 1
        time.sleep(wait)
    return people, updated
