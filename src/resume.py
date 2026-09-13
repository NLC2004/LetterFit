from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from draft import missing_slots
from llm import complete

TEMPLATE_FROM_RESUME_SYSTEM = """你是保研自荐信写手。根据学生简历原文，写一封中文自荐信底稿。
硬性要求：
1. 必须原样保留四个花括号空位：{老师称呼} {老师方向} {交叉经历} {契合段}
2. 第一行必须是：尊敬的{老师称呼}老师：
3. 自我介绍段里必须各出现一次：「关注到您团队在{老师方向}及相关方向」和「与我目前在{交叉经历}方面」
4. 科研经历写完后、奖项之前，单独成段只写 {契合段}
5. 只使用简历里出现的信息，不要编造
6. 第一人称，不要保证录取
7. 只返回信件正文，不要 markdown 代码块
"""


def extract_text_from_bytes(data: bytes, filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return _pdf_text(data)
    if name.endswith(".docx"):
        return _docx_text(data)
    if name.endswith(".txt") or name.endswith(".md"):
        return data.decode("utf-8", errors="replace")
    if name.endswith(".doc"):
        raise RuntimeError("暂不支持旧版 .doc，请另存为 PDF 或 .docx。")
    raise RuntimeError("请上传 PDF、Word（.docx）或纯文本简历。")


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if len(text) < 40:
        raise RuntimeError("没能从这份 PDF 读出足够文字。若是扫描件，请把内容粘贴到文本框。")
    return text


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    text = "".join(t.text or "" for t in root.findall(".//w:t", ns)).strip()
    if len(text) < 40:
        raise RuntimeError("没能从这份 Word 读出足够文字。")
    return text


def generate_template_from_resume(resume_text: str) -> str:
    text = (resume_text or "").strip()
    if len(text) < 40:
        raise RuntimeError("简历内容太短。")
    user = "下面是学生简历原文，请据此写自荐信底稿：\n\n" + text[:12000]
    raw = complete(TEMPLATE_FROM_RESUME_SYSTEM, user, temperature=0.3)
    body = _strip_fence(raw)
    missing = missing_slots(body)
    if missing:
        retry = user + "\n\n上次稿缺少这些空位：" + "、".join(missing) + "。请重写，四个空位一个都不能少。"
        body = _strip_fence(complete(TEMPLATE_FROM_RESUME_SYSTEM, retry, temperature=0.2))
    missing = missing_slots(body)
    if missing:
        raise RuntimeError("模型没有保留全部空位：" + "、".join(missing))
    return body.strip() + "\n"


def _strip_fence(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:\w+)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()
