from __future__ import annotations

import re

from config import load_profile, load_settings
from llm import complete_json
from models import Professor
from paths import TEMPLATE_FILE
from store import save_draft
from web import compress_for_llm, fetch_html, html_to_text

SLOTS = ("老师称呼", "老师方向", "交叉经历", "契合段")
SLOT_MARKERS = tuple("{" + k + "}" for k in SLOTS)


def missing_slots(text: str) -> list[str]:
    return [m for m in SLOT_MARKERS if m not in (text or "")]


def profile_experiences(profile: dict) -> list[dict]:
    raw = profile.get("experiences") or profile.get("research") or []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        org = str(item.get("org") or "").strip()
        keywords = str(item.get("keywords") or "").strip()
        detail = str(item.get("detail") or item.get("desc") or "").strip()
        if org or keywords or detail:
            out.append({"org": org, "keywords": keywords, "detail": detail})
    return out


def _slot_system(profile: dict) -> str:
    exps = profile_experiences(profile)
    options = "；".join(
        f"{e['org']}（{e['keywords'] or e['detail'][:40]}）" if e["org"] else (e["keywords"] or e["detail"][:40])
        for e in exps
    ) or "（请先在配置里填写经历）"
    return f"""你只填写保研自荐信模板中的空位，不要改写模板里已经写好的经历、论文和奖项。
返回 JSON，键必须是：老师称呼、老师方向、交叉经历、契合段。
1. 老师称呼：只填姓氏（复姓填前两字），不要带“老师”或“尊敬的”。
2. 老师方向：根据老师信息写 2-4 个具体研究方向，顿号分隔，必须来自老师简介。
3. 交叉经历：只能从学生已有经历里挑 2-3 项。可选范围：{options}。不要发明学生没做过的方向。
4. 契合段：2-4 句话，不要编造老师论文，不要保证录取。
"""


def honorific_for(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "老师"
    surnames2 = ("欧阳", "司马", "上官", "诸葛", "司徒", "夏侯", "慕容")
    if any(name.startswith(s) for s in surnames2):
        return name[:2]
    return name[:1]


def load_template() -> str:
    if not TEMPLATE_FILE.exists():
        raise FileNotFoundError(f"找不到邮件模板：{TEMPLATE_FILE}")
    return TEMPLATE_FILE.read_text(encoding="utf-8").strip() + "\n"


def _teacher_context(person: Professor, fetch_homepage: bool) -> str:
    extra = ""
    if fetch_homepage and person.homepage:
        try:
            settings = load_settings()
            html = fetch_html(person.homepage)
            extra = compress_for_llm(html_to_text(html), settings["max_homepage_chars"])
        except Exception as exc:
            extra = f"（主页读取失败：{exc}）"
    return f"""姓名：{person.name}
职称：{person.title}
学校：{person.school} {person.department}
邮箱：{person.email}
已整理方向：{person.research}
主页：{person.homepage}
主页摘录：
{extra}
"""


def default_subject(profile: dict) -> str:
    return (profile.get("subject") or f"{profile.get('school', '')}{profile.get('name', '')}推免自荐信").strip()


def _fill_slots(template: str, slots: dict[str, str]) -> str:
    text = template
    for key in SLOTS:
        text = text.replace("{" + key + "}", slots[key])
    # 兼容旧版用 XXX 占位的模板
    text = re.sub(r"尊敬的XXX老师", f"尊敬的{slots['老师称呼']}老师", text)
    text = text.replace("您团队在XXX、XXX及相关方向", f"您团队在{slots['老师方向']}及相关方向")
    text = text.replace("与我目前在XXX、XXX及XXX方面", f"与我目前在{slots['交叉经历']}方面")
    return text


def _ask_slots(person: Professor, profile: dict, fetch_homepage: bool) -> dict[str, str]:
    exps = profile_experiences(profile)
    if not exps:
        raise RuntimeError("还没有填写科研/项目经历。请在配置向导里至少写一条。")
    exp_lines = "\n".join(
        f"- {e['org']}：{e['keywords']}" + (f"（{e['detail']}）" if e["detail"] else "")
        for e in exps
    )
    interests = "、".join(str(i).strip() for i in (profile.get("interests") or []) if str(i).strip())
    interest_line = f"- 兴趣方向：{interests}\n" if interests else ""
    user = f"""老师信息：
{_teacher_context(person, fetch_homepage)}

学生可对齐的经历（只能从这里选交叉点）：
{exp_lines}
{interest_line}
请填写 JSON。老师称呼必须是「{honorific_for(person.name)}」。
"""
    data = complete_json(_slot_system(profile), user, temperature=0.3)
    if not isinstance(data, dict):
        raise RuntimeError("模型未返回 JSON 空位")
    slots = {k: str(data.get(k) or "").strip() for k in SLOTS}
    slots["老师称呼"] = honorific_for(person.name)
    missing = [k for k in SLOTS if not slots[k]]
    if missing:
        raise RuntimeError("模板空位未填完整：" + "、".join(missing))
    slots["契合段"] = slots["契合段"].lstrip()
    return slots


def generate_draft(person: Professor, profile: dict | None = None, fetch_homepage: bool = True) -> dict:
    profile = profile or load_profile()
    template = load_template()
    slots = _ask_slots(person, profile, fetch_homepage)
    body = _fill_slots(template, slots).strip() + "\n"
    payload = {
        "to": person.email,
        "name": person.name,
        "school": person.school,
        "department": person.department,
        "subject": default_subject(profile),
        "body": body,
        "slots": slots,
    }
    save_draft(person.id, payload)
    person.status = "drafted"
    return payload
