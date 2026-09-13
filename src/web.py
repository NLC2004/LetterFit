from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from charset_normalizer import from_bytes
import httpx

from config import load_settings

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
OBFUSCATED_RE = re.compile(
    r"([A-Za-z0-9._%+\-]+)\s*(?:\[at\]|\(at\)|\s+at\s+|＠)\s*([A-Za-z0-9.\-]+\.[A-Za-z]{2,})",
    re.I,
)
TITLE_RE = re.compile(r"(教授|副教授|讲师|研究员|副研究员|助理教授|特聘研究员)")


def normalize_email(value: str) -> str:
    text = unescape(value or "").strip().lower()
    text = text.replace("mailto:", "").split("?")[0].strip()
    text = text.replace("[at]", "@").replace("(at)", "@").replace(" at ", "@")
    text = text.replace("＠", "@")
    text = re.sub(r"\s+", "", text)
    if EMAIL_RE.fullmatch(text):
        return text
    match = EMAIL_RE.search(text)
    return match.group(0) if match else ""


def decode_bytes(content: bytes, header_encoding: str | None = None) -> str:
    candidates = [header_encoding, "utf-8", "gbk", "gb2312"]
    for enc in candidates:
        if not enc:
            continue
        try:
            return content.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    best = from_bytes(content).best()
    return str(best) if best else content.decode("utf-8", errors="replace")


def fetch_html(url: str) -> str:
    settings = load_settings()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"只允许 http/https: {url}")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": f"{parsed.scheme}://{parsed.netloc}/",
    }
    with httpx.Client(
        headers=headers,
        timeout=settings["timeout_seconds"],
        follow_redirects=True,
        verify=settings["verify_ssl"],
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        content = resp.content[: settings["max_bytes"]]
        return decode_bytes(content, resp.encoding)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return soup.get_text("\n")


def compress_for_llm(text: str, max_chars: int) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    keys = ("@", "at]", "教授", "副教授", "讲师", "研究员", "邮箱", "mail", "方向", "主页", "研究")
    useful, weak = [], []
    for ln in lines:
        if len(ln) > 400:
            ln = ln[:400]
        if any(k.lower() in ln.lower() if k.isascii() else k in ln for k in keys):
            useful.append(ln)
        else:
            weak.append(ln)
    merged = "\n".join(useful)
    if len(merged) < max_chars // 2:
        merged = (merged + "\n" + "\n".join(weak[:250])).strip()
    return merged[:max_chars]


def extract_mailtos_and_links(html: str, base_url: str) -> tuple[list[dict], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[dict] = []
    homepages: list[str] = []
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        name = a.get_text(" ", strip=True)
        if href.lower().startswith("mailto:"):
            email = normalize_email(href)
            if email:
                found.append({"name": name, "email": email, "homepage": ""})
            continue
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        abs_url = urljoin(base_url, href)
        if name and TITLE_RE.search(name):
            homepages.append(abs_url)
        elif name and re.fullmatch(r"[\u4e00-\u9fff]{2,4}", name):
            homepages.append(abs_url)
            found.append({"name": name, "email": "", "homepage": abs_url})
    return found, homepages


def regex_emails(text: str) -> list[str]:
    emails = {normalize_email(m.group(0)) for m in EMAIL_RE.finditer(text)}
    for m in OBFUSCATED_RE.finditer(text):
        emails.add(normalize_email(f"{m.group(1)}@{m.group(2)}"))
    return sorted(e for e in emails if e)
