from __future__ import annotations

import ssl
import smtplib
import socket
import time
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from config import load_profile, load_settings, smtp_config
from paths import ATTACHMENTS_DIR
from store import append_sent_log, sent_today_count

SKIP_ATTACH_NAMES = {"请把附件放这里.txt", ".gitkeep"}
ATTACH_SUFFIXES = {".pdf", ".doc", ".docx"}


def list_attachments() -> list[Path]:
    if not ATTACHMENTS_DIR.exists():
        return []
    files = []
    for path in sorted(ATTACHMENTS_DIR.iterdir()):
        if not path.is_file():
            continue
        if path.name in SKIP_ATTACH_NAMES or path.name.startswith("."):
            continue
        if path.suffix.lower() in ATTACH_SUFFIXES:
            files.append(path)
    return files


def remaining_today() -> tuple[int, int]:
    settings = load_settings()
    used = sent_today_count()
    return used, settings["max_per_day"]


def _subtype(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application", "pdf"
    if suffix == ".doc":
        return "application", "msword"
    if suffix == ".docx":
        return "application", "vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application", "octet-stream"


def build_message(to_email: str, subject: str, body: str) -> EmailMessage:
    profile = load_profile()
    smtp = smtp_config()
    from_email = smtp["user"] or profile["email"]
    from_name = smtp["from_name"] or profile.get("name") or ""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid(domain=from_email.split("@")[-1] if "@" in from_email else "localhost")
    msg.set_content(body, charset="utf-8")
    for path in list_attachments():
        maintype, subtype = _subtype(path)
        msg.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )
    return msg


def explain_send_error(exc: Exception) -> str:
    raw = str(exc)
    text = raw.lower()
    if isinstance(exc, smtplib.SMTPAuthenticationError) or "535" in raw or "534" in raw or "authentication" in text:
        return "邮箱登录被拒绝：邮箱密码不正确，或尚未开启 SMTP 服务。请核对密码，并确认网页版邮箱已开启 SMTP。"
    if isinstance(exc, (TimeoutError, socket.timeout)) or "timed out" in text or "timeout" in text:
        return "连接超时：检查 SMTP 服务器地址和端口，或换网络重试。"
    if "550" in raw or "553" in raw:
        return "对方服务器拒收：收件人地址可能有误，或邮箱被临时限制。"
    if "unexpectedly closed" in text:
        return "连接被中断：多半是发送太频繁，请间隔更久再发。"
    return raw


def _open_smtp():
    smtp = smtp_config()
    if not smtp["host"]:
        raise RuntimeError("未配置 SMTP 服务器地址。")
    if not smtp["user"] or not smtp["password"]:
        raise RuntimeError("未配置发信邮箱或邮箱密码（SMTP_USER / SMTP_PASSWORD）。")
    context = ssl.create_default_context()
    if smtp["use_ssl"]:
        client = smtplib.SMTP_SSL(smtp["host"], smtp["port"], context=context, timeout=30)
    else:
        client = smtplib.SMTP(smtp["host"], smtp["port"], timeout=30)
        client.ehlo()
        client.starttls(context=context)
    client.login(smtp["user"], smtp["password"])
    return client


def test_login() -> str:
    smtp = smtp_config()
    client = _open_smtp()
    try:
        client.noop()
    finally:
        try:
            client.quit()
        except Exception:
            pass
    return f"登录成功：{smtp['user']} @ {smtp['host']}:{smtp['port']}"


def _deliver(client, to_email: str, subject: str, body: str, person_id: str = "") -> None:
    if not to_email or "@" not in to_email:
        raise RuntimeError("收件人邮箱无效")
    msg = build_message(to_email, subject, body)
    try:
        client.send_message(msg)
    except Exception:
        append_sent_log(
            {
                "status": "failed",
                "to": to_email,
                "subject": subject,
                "person_id": person_id,
            }
        )
        raise
    append_sent_log(
        {
            "status": "sent",
            "to": to_email,
            "subject": subject,
            "person_id": person_id,
            "attachments": [p.name for p in list_attachments()],
        }
    )


def send_mail(to_email: str, subject: str, body: str, person_id: str = "") -> None:
    used, limit = remaining_today()
    if used >= limit:
        raise RuntimeError(f"今日已发 {used} 封，达到上限 {limit}。可在 config/settings.yaml 调整。")
    client = _open_smtp()
    try:
        _deliver(client, to_email, subject, body, person_id)
    finally:
        try:
            client.quit()
        except Exception:
            pass


def send_bulk(jobs: list[dict]) -> list[dict]:
    """连续发送，无间隔。每项含 to/subject/body/person_id。受每日上限约束。"""
    used, limit = remaining_today()
    remaining = max(0, limit - used)
    if remaining <= 0:
        raise RuntimeError(f"今日已发 {used} 封，达到上限 {limit}。")
    interval = max(10, int(load_settings().get("bulk_interval_seconds", 60)))
    todo = jobs[:remaining]
    results: list[dict] = []
    client = _open_smtp()
    try:
        for i, job in enumerate(todo):
            if i > 0:
                time.sleep(interval)
            item = {
                "to": job.get("to") or "",
                "name": job.get("name") or "",
                "person_id": job.get("person_id") or "",
                "ok": False,
                "error": "",
            }
            try:
                _deliver(
                    client,
                    item["to"],
                    job.get("subject") or "",
                    job.get("body") or "",
                    item["person_id"],
                )
                item["ok"] = True
            except Exception as exc:
                item["error"] = str(exc)
            results.append(item)
    finally:
        try:
            client.quit()
        except Exception:
            pass
    skipped = len(jobs) - len(todo)
    if skipped:
        results.append(
            {
                "to": "",
                "name": "",
                "person_id": "",
                "ok": False,
                "error": f"已达今日上限，另有 {skipped} 封未发送",
            }
        )
    return results
