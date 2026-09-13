from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import time
from datetime import datetime

import pandas as pd
import streamlit as st
import yaml
from dotenv import load_dotenv, set_key

from config import load_profile, load_schools, load_settings, llm_config, save_profile, smtp_config
from draft import generate_draft, missing_slots, profile_experiences
from faculty import enrich_selected, fetch_source, parse_faculty_list
from llm import complete as llm_complete
from logging_setup import setup_logging
from mailer import explain_send_error, list_attachments, remaining_today, send_bulk, send_mail, test_login
from models import CSV_FIELDS, Professor
from paths import ATTACHMENTS_DIR, ENV_FILE, PROFILE_FILE, SCHOOLS_FILE, TEMPLATE_FILE
from resume import extract_text_from_bytes, generate_template_from_resume
from presets import LLM_PRESETS, SMTP_PRESETS
from store import load_draft, load_targets, save_draft, save_targets, upsert_targets


st.set_page_config(page_title="LetterFit 保研自荐邮件助手", layout="wide")
setup_logging()


# ---------------------------------------------------------------- 配置向导

WIZARD_STEPS = ["个人信息", "发信邮箱", "大模型", "简历附件", "完成"]


def _smtp_ready() -> bool:
    smtp = smtp_config()
    return bool(smtp["host"] and smtp["user"] and smtp["password"])


def _llm_ready() -> bool:
    return bool(llm_config()["api_key"])


def _profile_ready() -> bool:
    try:
        profile = load_profile()
    except Exception:
        return False
    return bool(profile_experiences(profile))


def _write_env(values: dict[str, str]) -> None:
    ENV_FILE.touch(exist_ok=True)
    for key, value in values.items():
        set_key(str(ENV_FILE), key, value)
    load_dotenv(ENV_FILE, override=True)


def _load_profile_safe() -> dict:
    try:
        return load_profile()
    except Exception:
        return {}


def _wizard_step_profile() -> bool:
    """填写个人信息与经历。返回 True 表示可进入下一步。"""
    profile = _load_profile_safe()
    st.markdown("#### 第 1 步 / 共 4 步：个人信息与科研经历")
    st.caption("这些信息用于邮件落款、主题，以及让大模型从你的真实经历里挑选与老师的契合点（不会编造）。")

    name = st.text_input("姓名 *", value=profile.get("name") or "")
    c1, c2 = st.columns(2)
    with c1:
        email = st.text_input("你的邮箱（用于落款）*", value=profile.get("email") or "")
        school = st.text_input("学校", value=profile.get("school") or "")
        college = st.text_input("学院", value=profile.get("college") or "")
    with c2:
        major = st.text_input("专业", value=profile.get("major") or "")
        grade = st.text_input("年级", value=profile.get("grade") or "", placeholder="如：2027届本科生")
        rank = st.text_input("成绩 / 排名", value=profile.get("rank") or "", placeholder="如：专业排名前10%")
    subject = st.text_input(
        "邮件主题（留空自动生成）",
        value=profile.get("subject") or "",
        placeholder="如：某某大学张三推免自荐信",
    )

    st.markdown("**科研 / 项目 / 实习经历** *（至少一条，大模型只从这里挑选与老师的契合点）*")
    exps = profile_experiences(profile)
    exp_df = pd.DataFrame(exps) if exps else pd.DataFrame([{"org": "", "keywords": "", "detail": ""}])
    exp_edited = st.data_editor(
        exp_df,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config={
            "org": st.column_config.TextColumn("单位 / 项目", required=True),
            "keywords": st.column_config.TextColumn("关键词（填进邮件，顿号分隔）", required=True),
            "detail": st.column_config.TextColumn("你做了什么（供模型判断契合度）", width="large"),
        },
        key="wizard_exp_editor",
    )

    interests = st.text_area(
        "研究兴趣（每行一个）",
        value="\n".join(str(i) for i in (profile.get("interests") or [])),
        height=80,
    )
    awards = st.text_area(
        "奖项荣誉（每行一个）",
        value="\n".join(str(a) for a in (profile.get("awards") or [])),
        height=80,
    )

    if st.button("保存并下一步", type="primary"):
        rows = [
            {"org": str(r.get("org") or "").strip(), "keywords": str(r.get("keywords") or "").strip(),
             "detail": str(r.get("detail") or "").strip()}
            for _, r in exp_edited.iterrows()
        ]
        rows = [r for r in rows if r["org"] or r["keywords"]]
        if not name.strip() or not email.strip():
            st.error("请填写姓名和邮箱。")
            return False
        if not rows:
            st.error("请至少填写一条经历，否则无法生成个性化内容。")
            return False
        data = dict(profile)
        data.update(
            {
                "name": name.strip(),
                "email": email.strip(),
                "school": school.strip(),
                "college": college.strip(),
                "major": major.strip(),
                "grade": grade.strip(),
                "rank": rank.strip(),
                "subject": subject.strip(),
                "interests": [ln.strip() for ln in interests.splitlines() if ln.strip()],
                "experiences": rows,
                "awards": [ln.strip() for ln in awards.splitlines() if ln.strip()],
            }
        )
        data.pop("research", None)  # 旧字段迁移为 experiences
        save_profile(data)
        st.success("已保存个人信息。")
        return True
    return False


def _wizard_step_smtp() -> bool:
    st.markdown("#### 第 2 步 / 共 4 步：发信邮箱")
    st.caption("邮件从你的邮箱发出，邮箱密码只保存在你自己电脑的 .env 文件里。")
    smtp = smtp_config()
    profile = _load_profile_safe()

    provider_names = list(SMTP_PRESETS.keys())
    current = next((n for n, p in SMTP_PRESETS.items() if p["host"] and p["host"] == smtp["host"]), provider_names[-1])
    provider = st.selectbox("选择你的邮箱", provider_names, index=provider_names.index(current))
    preset = SMTP_PRESETS[provider]
    st.info(preset["guide"])

    manual = not preset["host"]
    c1, c2, c3 = st.columns(3)
    with c1:
        host = st.text_input("SMTP 服务器", value=smtp["host"] or preset["host"], disabled=not manual)
    with c2:
        port = st.number_input("端口", value=int(smtp["port"] or preset["port"]), step=1, disabled=not manual)
    with c3:
        use_ssl = st.checkbox("使用 SSL（465 端口勾选；587 不勾）", value=bool(preset["ssl"]), disabled=not manual)

    user = st.text_input("邮箱地址", value=smtp["user"], placeholder=preset["user_hint"])
    password = st.text_input("邮箱密码", value=smtp["password"], type="password")
    from_name = st.text_input("发件人显示名", value=smtp["from_name"] or profile.get("name") or "")

    if st.button("保存并测试登录", type="primary"):
        if not host or not user or not password:
            st.error("请填完整：服务器、邮箱地址、邮箱密码。")
            return False
        _write_env(
            {
                "SMTP_HOST": host.strip(),
                "SMTP_PORT": str(int(port)),
                "SMTP_SSL": "true" if use_ssl else "false",
                "SMTP_USER": user.strip(),
                "SMTP_PASSWORD": password.strip(),
                "SMTP_FROM_NAME": from_name.strip(),
            }
        )
        with st.spinner("正在登录邮箱服务器…"):
            try:
                st.success(test_login())
                st.session_state["smtp_tested"] = True
            except Exception as exc:
                st.session_state["smtp_tested"] = False
                st.error(explain_send_error(exc))
                return False
    if st.session_state.get("smtp_tested"):
        if st.button("下一步"):
            return True
    else:
        st.warning("请先点「保存并测试登录」，通过后才能继续。")
    return False


def _wizard_step_llm() -> bool:
    st.markdown("#### 第 3 步 / 共 4 步：大模型")
    st.caption("用于把网页整理成老师名单、并按你的模板填写与老师相关的空位。推荐 DeepSeek，新用户有免费额度。")
    llm = llm_config()

    preset_names = list(LLM_PRESETS.keys())
    current = next(
        (n for n, p in LLM_PRESETS.items() if p["base_url"] and p["base_url"] == llm["base_url"]),
        preset_names[0],
    )
    preset_name = st.selectbox("选择大模型服务", preset_names, index=preset_names.index(current))
    preset = LLM_PRESETS[preset_name]
    st.info(preset["guide"])

    manual = not preset["base_url"]
    c1, c2 = st.columns(2)
    with c1:
        base_url = st.text_input("Base URL", value=llm["base_url"] or preset["base_url"], disabled=not manual)
    with c2:
        model = st.text_input("模型名", value=llm["model"] or preset["model"], disabled=not manual)
    api_key = st.text_input("API Key", value=llm["api_key"], type="password")

    if st.button("保存并测试调用", type="primary"):
        if not base_url or not model or not api_key:
            st.error("请填完整：Base URL、模型名、API Key。")
            return False
        _write_env(
            {
                "LLM_BASE_URL": base_url.strip(),
                "LLM_MODEL": model.strip(),
                "LLM_API_KEY": api_key.strip(),
            }
        )
        with st.spinner("正在调用大模型…"):
            try:
                llm_complete("你是助手", "只回复两个字：正常")
                st.success("大模型调用成功。")
                st.session_state["llm_tested"] = True
            except Exception as exc:
                st.session_state["llm_tested"] = False
                msg = str(exc)
                if "401" in msg or "auth" in msg.lower():
                    st.error("API Key 无效，请检查是否复制完整。")
                elif "429" in msg:
                    st.error("额度不足或请求太频繁，请检查账户余额。")
                else:
                    st.error(f"调用失败：{msg}")
                return False
    if st.session_state.get("llm_tested"):
        if st.button("下一步"):
            return True
    else:
        st.warning("请先点「保存并测试调用」，通过后才能继续。")
    return False


def _wizard_step_attachment() -> bool:
    st.markdown("#### 第 4 步 / 共 4 步：简历附件")
    st.caption("每封信都会附上这里的文件，建议只放一份 PDF 简历。")
    ATTACHMENTS_DIR.mkdir(exist_ok=True)
    uploaded = st.file_uploader(
        "上传简历（PDF / Word）",
        type=["pdf", "doc", "docx"],
        accept_multiple_files=True,
    )
    if uploaded:
        for f in uploaded:
            (ATTACHMENTS_DIR / f.name).write_bytes(f.getbuffer())
        st.success("已保存：" + "、".join(f.name for f in uploaded))
    atts = list_attachments()
    if atts:
        st.write("当前附件：" + "、".join(p.name for p in atts))
    else:
        st.warning("还没有附件。可以先跳过，之后在「材料与配置」页上传。")
    if st.button("下一步", type="primary"):
        return True
    return False


def _wizard_step_done() -> bool:
    st.markdown("#### 配置完成")
    checks = [
        ("个人信息与经历", _profile_ready()),
        ("发信邮箱", _smtp_ready()),
        ("大模型", _llm_ready()),
        ("简历附件", bool(list_attachments())),
    ]
    for label, ok in checks:
        st.write(("✅ " if ok else "⚠️ ") + label)
    st.markdown(
        """
**接下来的使用流程：**

1. 「师资名单」页：粘贴学院师资页文本（或填好 `config/schools.yaml` 后抓取），核对邮箱并勾选老师
2. 「生成草稿」页：为勾选的老师生成个性化信件
3. 「确认发送」页：逐封检查后再发，**不要一次性群发太多**，每天建议不超过 30 封
        """
    )
    if st.button("开始使用", type="primary"):
        return True
    return False


def render_wizard() -> None:
    st.title("保研自荐邮件助手 · 首次配置")
    st.caption("约 3 分钟。所有信息只保存在你自己的电脑上。")
    step = st.session_state.get("setup_step", 0)
    st.progress((step + 1) / len(WIZARD_STEPS), text=f"当前：{WIZARD_STEPS[step]}")

    advanced = st.session_state.get("setup_done", False)
    if step == 0:
        done = _wizard_step_profile()
    elif step == 1:
        done = _wizard_step_smtp()
    elif step == 2:
        done = _wizard_step_llm()
    elif step == 3:
        done = _wizard_step_attachment()
    else:
        done = _wizard_step_done()

    if done:
        if step + 1 < len(WIZARD_STEPS):
            st.session_state["setup_step"] = step + 1
        else:
            st.session_state["setup_done"] = True
            st.session_state["setup_step"] = 0
        st.rerun()

    if not advanced:
        st.divider()
        if st.button("我是进阶用户，跳过向导（自己改配置文件）"):
            st.session_state["setup_done"] = True
            st.rerun()


# ---------------------------------------------------------------- 主界面

def _people_to_df(people: list[Professor]) -> pd.DataFrame:
    rows = [p.to_row() for p in people]
    df = pd.DataFrame(rows, columns=CSV_FIELDS)
    if "selected" in df.columns:
        df["selected"] = df["selected"].map(lambda x: str(x).lower() in {"yes", "true", "1"})
    return df


def _df_to_people(df: pd.DataFrame) -> list[Professor]:
    people = []
    for _, row in df.iterrows():
        data = {k: "" if pd.isna(row.get(k)) else str(row.get(k)) for k in CSV_FIELDS}
        people.append(Professor.from_row(data))
    return people


def _reload():
    st.session_state["people"] = load_targets()


if "people" not in st.session_state:
    _reload()
if "last_sent_at" not in st.session_state:
    st.session_state.last_sent_at = 0.0

people: list[Professor] = st.session_state["people"]
settings = load_settings()
used, limit = remaining_today()

_setup_incomplete = not (_profile_ready() and _smtp_ready() and _llm_ready())
if _setup_incomplete and not st.session_state.get("setup_done"):
    render_wizard()
    st.stop()

st.title("保研自荐邮件助手")
st.caption("从学院官网师资页整理名单 → 你勾选 → 按 Template/template 套信并只改与老师相关的空位 → 你确认后才发送。")

c1, c2, c3 = st.columns(3)
c1.metric("名单人数", len(people))
c2.metric("已勾选待联系", sum(1 for p in people if p.selected and p.status != "sent"))
c3.metric("今日已发送", f"{used} / {limit}")

tabs = st.tabs(["1. 材料与配置", "2. 师资名单", "3. 生成草稿", "4. 确认发送"])

with tabs[0]:
    if st.session_state.pop("wizard_notice", False):
        st.success("配置向导已完成。")
    st.subheader("配置状态")
    smtp = smtp_config()
    llm = llm_config()
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**发信邮箱**")
        st.write(f"{smtp['from_name']} `<{smtp['user'] or '未配置'}>`")
        st.write(f"{smtp['host'] or '未配置服务器'}:{smtp['port']}  SSL={smtp['use_ssl']}")
        if st.button("测试 SMTP 登录"):
            try:
                st.success(test_login())
            except Exception as exc:
                st.error(explain_send_error(exc))
    with col_b:
        st.markdown("**大模型**")
        st.write(llm["base_url"] or "未配置")
        st.write(llm["model"])
        st.write("API Key：" + ("已填写" if llm["api_key"] else "未填写"))

    if st.button("重新打开配置向导（修改邮箱 / 大模型 / 个人信息）"):
        st.session_state["setup_done"] = False
        st.session_state["setup_step"] = 0
        st.rerun()

    st.subheader("简历附件")
    ATTACHMENTS_DIR.mkdir(exist_ok=True)
    uploaded = st.file_uploader("上传简历（PDF / Word），每封信都会附上", type=["pdf", "doc", "docx"], accept_multiple_files=True)
    if uploaded:
        for f in uploaded:
            (ATTACHMENTS_DIR / f.name).write_bytes(f.getbuffer())
        st.success("已保存：" + "、".join(f.name for f in uploaded))
    atts = list_attachments()
    if atts:
        st.success("将随信附上：" + "、".join(p.name for p in atts))
    else:
        st.warning("还没有附件。请先上传自荐简历。")

    st.subheader("根据简历生成邮件底稿")
    st.caption("调用已配置的大模型，按简历原文写一封通用自荐信，并留下四个空位。生成后请检查再保存。")
    resume_up = st.file_uploader("上传简历（PDF / Word），或在下方粘贴文字", type=["pdf", "docx", "txt"], key="resume_for_template")
    resume_paste = st.text_area("也可以直接粘贴简历文本", height=120, key="resume_paste")
    if st.button("根据简历生成底稿", type="primary"):
        try:
            if resume_up is not None:
                text = extract_text_from_bytes(resume_up.getvalue(), resume_up.name)
            elif resume_paste.strip():
                text = resume_paste.strip()
            else:
                raise RuntimeError("请先上传简历文件，或把简历文字粘贴到文本框。")
            if not _llm_ready():
                raise RuntimeError("还没有配置大模型 API Key。请先完成配置向导。")
            with st.spinner("正在根据简历写底稿…"):
                st.session_state["generated_template"] = generate_template_from_resume(text)
                st.session_state["tpl_editor_n"] = st.session_state.get("tpl_editor_n", 0) + 1
            st.success("已生成，请在下方检查后再保存。")
        except Exception as exc:
            st.error(str(exc))

    st.subheader("邮件底稿 Template/template")
    st.caption("请保留四个花括号空位。其余段落生成个性化信件时会原样套用。")
    default_tpl = st.session_state.get("generated_template")
    if not default_tpl:
        default_tpl = TEMPLATE_FILE.read_text(encoding="utf-8") if TEMPLATE_FILE.exists() else ""
    tpl_n = st.session_state.get("tpl_editor_n", 0)
    tpl_edited = st.text_area("Template/template", value=default_tpl, height=320, key=f"tpl_area_{tpl_n}")
    if st.button("保存邮件底稿"):
        miss = missing_slots(tpl_edited)
        if miss:
            st.error("请保留这些空位：" + "、".join(miss))
        else:
            TEMPLATE_FILE.write_text(tpl_edited, encoding="utf-8")
            st.session_state.pop("generated_template", None)
            st.success("已保存邮件底稿。")

    st.subheader("个人材料")
    raw = PROFILE_FILE.read_text(encoding="utf-8") if PROFILE_FILE.exists() else ""
    edited = st.text_area("config/profile.yaml", value=raw, height=360)
    if st.button("保存个人材料"):
        try:
            data = yaml.safe_load(edited)
            if not isinstance(data, dict):
                raise ValueError("YAML 必须是字典")
            PROFILE_FILE.write_text(edited, encoding="utf-8")
            st.success("已保存。")
        except Exception as exc:
            st.error(f"保存失败：{exc}")

    with st.expander("师资页来源 config/schools.yaml"):
        st.code(SCHOOLS_FILE.read_text(encoding="utf-8"), language="yaml")
        st.caption("用编辑器改这个文件后，到「师资名单」页点抓取。")

with tabs[1]:
    st.subheader("从学院官网整理老师")
    st.info(
        "学院官网基本爬不下来。请打开师资页后按 Ctrl+A 全选、Ctrl+C 复制，"
        "再粘贴到下面，让模型按 学校 / 学院 / 导师名 / 邮箱 / 职称 / 方向 整理。"
    )
    sources = [s for s in load_schools() if (s.get("faculty_url") or "").strip()]
    if not sources:
        st.warning("请先在 config/schools.yaml 填写 faculty_url。")
    else:
        labels = [f"{s.get('school')} / {s.get('department')} — {s.get('faculty_url')}" for s in sources]
        picked = st.selectbox("选择师资页", options=list(range(len(labels))), format_func=lambda i: labels[i])
        source = sources[picked]
        if st.button("抓取该页并合并到名单", type="primary"):
            with st.spinner("正在抓取并让模型整理名单…"):
                try:
                    incoming = fetch_source(source)
                    people, added = upsert_targets(people, incoming)
                    st.session_state["people"] = people
                    st.success(f"解析到 {len(incoming)} 人，新增 {added} 人。请核对邮箱后再勾选。")
                except Exception as exc:
                    st.error(f"抓取失败：{exc}")
                    st.info("不少学院网站会拦截程序访问。可把师资页全文粘贴到下面再解析。")

    st.markdown("**抓取失败时：粘贴师资页文本**")
    paste = st.text_area("从浏览器复制老师列表或个人介绍", height=140, placeholder="姓名、职称、邮箱、研究方向…")
    school_in = st.text_input("学校", value=source.get("school") if sources else "")
    dept_in = st.text_input("学院", value=source.get("department") if sources else "")
    if st.button("从粘贴文本解析"):
        if not paste.strip():
            st.error("请先粘贴内容。")
        else:
            with st.spinner("正在解析…"):
                try:
                    incoming = parse_faculty_list(
                        paste,
                        source_url="pasted",
                        school=school_in.strip(),
                        department=dept_in.strip(),
                    )
                    people, added = upsert_targets(people, incoming)
                    st.session_state["people"] = people
                    st.success(f"解析到 {len(incoming)} 人，新增 {added} 人。")
                except Exception as exc:
                    st.error(str(exc))

    st.subheader("名单（请先核对再勾选）")
    st.caption("只勾选你真正要联系的老师。已发送过的请保持 status=sent。邮箱空的可以先勾选再点「补全主页」。")
    df = _people_to_df(people)
    keyword = st.text_input("按姓名 / 方向 / 学院筛选", "")
    view = df
    if keyword.strip():
        k = keyword.strip()
        mask = df.apply(lambda r: k in " ".join(map(str, r.values)), axis=1)
        view = df[mask]
    edited_df = st.data_editor(
        view,
        hide_index=True,
        use_container_width=True,
        column_config={
            "selected": st.column_config.CheckboxColumn("勾选", default=False),
            "research": st.column_config.TextColumn("研究方向", width="large"),
            "email": st.column_config.TextColumn("邮箱"),
            "homepage": st.column_config.TextColumn("主页"),
        },
        disabled=["id"],
        height=420,
    )
    if st.button("保存名单修改"):
        if keyword.strip():
            df.update(edited_df)
            people = _df_to_people(df)
        else:
            people = _df_to_people(edited_df)
        save_targets(people)
        st.session_state["people"] = people
        st.success("已保存到 data/targets.csv")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("勾选所有未发送的老师"):
            n = 0
            for p in people:
                if p.status != "sent":
                    p.selected = True
                    n += 1
            save_targets(people)
            st.session_state["people"] = people
            st.success(f"已勾选 {n} 位未发送的老师。")
            st.rerun()
    with col2:
        if st.button("补全已勾选老师的主页信息"):
            with st.spinner("只抓取已勾选且缺邮箱/方向的老师主页…"):
                try:
                    people, n = enrich_selected(people)
                    save_targets(people)
                    st.session_state["people"] = people
                    st.success(f"补全了 {n} 人。单次最多 {settings['max_enrich_per_run']} 人。")
                except Exception as exc:
                    st.error(str(exc))
    with col3:
        if st.button("全不选"):
            for p in people:
                p.selected = False
            save_targets(people)
            st.session_state["people"] = people
            st.rerun()
    with col4:
        if st.button("重新加载 CSV"):
            _reload()
            st.rerun()

with tabs[2]:
    st.subheader("为已勾选老师生成草稿")
    ready = [p for p in people if p.selected and p.email and p.status != "sent"]
    missing = [p for p in people if p.selected and not p.email and p.status != "sent"]
    if missing:
        st.warning("以下老师还没有邮箱，不会生成：" + "、".join(p.name for p in missing))
    st.write(f"可生成 {len(ready)} 封。将套用 `Template/template`，只改称呼、老师方向和契合段。")
    fetch_home = st.checkbox("生成时抓取老师主页", value=True)
    if st.button("开始生成草稿", type="primary", disabled=not ready):
        try:
            load_profile()
        except Exception as exc:
            st.error(str(exc))
        else:
            progress = st.progress(0.0)
            log = st.empty()
            ok, fail = 0, 0
            for i, person in enumerate(ready):
                log.info(f"正在写给 {person.name} <{person.email}>")
                try:
                    generate_draft(person, fetch_homepage=fetch_home)
                    ok += 1
                except Exception as exc:
                    person.notes = f"草稿失败：{exc}"
                    fail += 1
                    st.error(f"{person.name}: {exc}")
                progress.progress((i + 1) / len(ready))
                time.sleep(settings["delay_seconds"] if fetch_home else 0.2)
            save_targets(people)
            st.session_state["people"] = people
            st.success(f"完成：成功 {ok}，失败 {fail}。请到下一页逐封确认。")

    drafted = [p for p in people if p.status == "drafted"]
    if drafted:
        st.markdown("**已有草稿**")
        st.dataframe(
            pd.DataFrame(
                [{"姓名": p.name, "邮箱": p.email, "学院": p.department, "方向": p.research} for p in drafted]
            ),
            hide_index=True,
            use_container_width=True,
        )

with tabs[3]:
    st.subheader("预览并确认发送")
    st.markdown(
        f"每天最多 **{limit}** 封。逐封发送间隔 **{settings['interval_seconds']}** 秒；"
        f"批量发送每封间隔 **{settings['bulk_interval_seconds']}** 秒。"
    )
    selected_drafted = [p for p in people if p.selected and p.status == "drafted" and p.email]
    queue = selected_drafted or [p for p in people if p.status == "drafted" and p.email]
    if not queue:
        st.info("还没有可发送的草稿。请先勾选老师并生成草稿。")
    else:
        names = [f"{p.name}  <{p.email}>  [{p.school} {p.department}]" for p in queue]
        idx = st.selectbox("选择一封", options=list(range(len(queue))), format_func=lambda i: names[i])
        person = queue[idx]
        draft = load_draft(person.id) or {}
        subject = st.text_input("主题", value=draft.get("subject") or "")
        body = st.text_area("正文（可直接改）", value=draft.get("body") or "", height=420)
        st.caption("收件人：" + person.email)
        wait = settings["interval_seconds"] - (time.time() - st.session_state.last_sent_at)
        if st.session_state.last_sent_at and wait > 0:
            st.warning(f"距上一封不足间隔，还需等待 {int(wait)} 秒。")

        colx, coly, colz = st.columns(3)
        with colx:
            if st.button("保存对草稿的修改"):
                draft.update({"subject": subject, "body": body, "to": person.email})
                save_draft(person.id, draft)
                st.success("已保存草稿。")
        with coly:
            if st.button("跳过这位老师"):
                person.selected = False
                person.status = "skipped"
                person.notes = (person.notes + " | 跳过").strip(" |")
                save_targets(people)
                st.session_state["people"] = people
                st.rerun()
        with colz:
            confirm = st.checkbox("我已核对正文、收件人和附件，确认发送这一封")
            if st.button("发送这一封", type="primary", disabled=not confirm):
                if not body.strip() or not subject.strip():
                    st.error("主题和正文都不能为空。")
                elif wait > 0 and st.session_state.last_sent_at:
                    st.error(f"请再等 {int(wait)} 秒。")
                else:
                    try:
                        send_mail(person.email, subject, body, person_id=person.id)
                        person.status = "sent"
                        person.selected = False
                        person.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                        save_targets(people)
                        draft.update({"subject": subject, "body": body, "to": person.email})
                        save_draft(person.id, draft)
                        st.session_state["people"] = people
                        st.session_state.last_sent_at = time.time()
                        st.success(f"已发送给 {person.name} <{person.email}>")
                    except Exception as exc:
                        st.error(explain_send_error(exc))

        st.divider()
        st.subheader("批量发送")
        st.caption(
            f"将依次发送队列里的 {len(queue)} 封草稿（已勾选优先，否则全部已生成草稿），"
            f"每封间隔 {settings['bulk_interval_seconds']} 秒，仍受每日上限约束。"
            "失败的不会改成已发送，可稍后重试。"
        )
        st.warning("短时间内大量发送容易触发邮箱风控。建议优先逐封发送给最匹配的老师，每天控制在 30 封以内。")
        bulk_confirm = st.checkbox(
            f"确认依次发送这 {len(queue)} 封，且不再逐封预览",
            key="bulk_confirm",
        )
        if st.button("开始批量发送", type="primary", disabled=not bulk_confirm):
            jobs = []
            skipped_empty = []
            for p in queue:
                d = load_draft(p.id) or {}
                if not (d.get("body") or "").strip() or not (d.get("subject") or "").strip():
                    skipped_empty.append(p.name)
                    continue
                jobs.append(
                    {
                        "to": p.email,
                        "name": p.name,
                        "person_id": p.id,
                        "subject": d.get("subject") or "",
                        "body": d.get("body") or "",
                    }
                )
            if skipped_empty:
                st.warning("正文或主题为空，已跳过：" + "、".join(skipped_empty))
            if not jobs:
                st.error("没有可发送的完整草稿。")
            else:
                with st.spinner(f"正在依次发送 {len(jobs)} 封，每封间隔 {settings['bulk_interval_seconds']} 秒…"):
                    try:
                        results = send_bulk(jobs)
                    except Exception as exc:
                        st.error(explain_send_error(exc))
                    else:
                        by_id = {p.id: p for p in people}
                        ok_n = fail_n = 0
                        fail_names = []
                        for item in results:
                            person = by_id.get(item.get("person_id") or "")
                            if item.get("ok") and person:
                                person.status = "sent"
                                person.selected = False
                                person.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                                ok_n += 1
                            elif item.get("error"):
                                fail_n += 1
                                if item.get("name"):
                                    fail_names.append(f"{item['name']}（{item['error']}）")
                        save_targets(people)
                        st.session_state["people"] = people
                        if ok_n:
                            st.success(f"已发送 {ok_n} 封。")
                        if fail_n:
                            st.error("失败 " + str(fail_n) + " 封：" + "；".join(fail_names[:8]))
