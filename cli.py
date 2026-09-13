from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import time

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from config import load_profile, load_schools, load_settings
from draft import generate_draft
from faculty import enrich_selected, fetch_source
from mailer import list_attachments, remaining_today, send_mail, test_login
from store import load_draft, load_targets, save_targets, upsert_targets

app = typer.Typer(help="保研自荐邮件助手：官网名单 → 勾选 → 改稿 → 确认发送")
console = Console()


@app.command()
def smtp():
    """测试 SMTP 登录。"""
    console.print(test_login())


@app.command()
def fetch():
    """抓取 config/schools.yaml 里填写的师资页，合并进 data/targets.csv。"""
    sources = [s for s in load_schools() if (s.get("faculty_url") or "").strip()]
    if not sources:
        raise typer.Exit("请先在 config/schools.yaml 填写 faculty_url")
    people = load_targets()
    total_new = 0
    for source in sources:
        console.print(f"抓取 {source.get('school')} / {source.get('department')} …")
        try:
            incoming = fetch_source(source)
        except Exception as exc:
            console.print(f"[red]失败：{exc}[/red]")
            continue
        people, added = upsert_targets(people, incoming)
        total_new += added
        console.print(f"  解析 {len(incoming)} 人，新增 {added}")
        time.sleep(load_settings()["delay_seconds"])
    console.print(f"完成，新增 {total_new} 人。请打开 data/targets.csv 核对并勾选 selected=yes。")


@app.command()
def enrich():
    """为已勾选且缺邮箱/方向的老师抓取个人主页。单次有上限。"""
    people = load_targets()
    people, n = enrich_selected(people)
    save_targets(people)
    console.print(f"补全 {n} 人。")


@app.command()
def draft(no_homepage: bool = typer.Option(False, help="不抓取老师主页")):
    """为 selected=yes 且有邮箱、尚未发送的老师生成草稿。"""
    load_profile()
    people = load_targets()
    ready = [p for p in people if p.selected and p.email and p.status != "sent"]
    if not ready:
        raise typer.Exit("没有可生成的老师。请在 CSV 里把 selected 设为 yes。")
    for i, person in enumerate(ready, 1):
        console.print(f"[{i}/{len(ready)}] {person.name} <{person.email}>")
        try:
            generate_draft(person, fetch_homepage=not no_homepage)
        except Exception as exc:
            person.notes = f"草稿失败：{exc}"
            console.print(f"  [red]{exc}[/red]")
        time.sleep(0.3 if no_homepage else load_settings()["delay_seconds"])
    save_targets(people)
    console.print("草稿在 drafts/ 目录。")


@app.command("send")
def send_cmd():
    """逐封预览并确认发送。没有一键全发。"""
    atts = list_attachments()
    console.print("附件：" + ("、".join(p.name for p in atts) if atts else "[yellow]无[/yellow]"))
    used, limit = remaining_today()
    console.print(f"今日已发送 {used}/{limit}")
    people = load_targets()
    queue = [p for p in people if p.selected and p.status == "drafted" and p.email]
    if not queue:
        raise typer.Exit("没有待发送草稿。请先 draft，并保持 selected=yes。")
    interval = load_settings()["interval_seconds"]
    last = 0.0
    for person in queue:
        used, limit = remaining_today()
        if used >= limit:
            console.print("[red]已达今日上限。[/red]")
            break
        draft_data = load_draft(person.id) or {}
        console.rule(f"{person.name} <{person.email}>")
        console.print(f"主题：{draft_data.get('subject', '')}")
        console.print(draft_data.get("body", "[无草稿]"))
        if not (draft_data.get("body") or "").strip():
            console.print("[red]正文为空，跳过。[/red]")
            continue
        if not Confirm.ask("确认发送这一封？", default=False):
            continue
        wait = interval - (time.time() - last)
        if last and wait > 0:
            console.print(f"等待间隔 {int(wait)} 秒…")
            time.sleep(wait)
        try:
            send_mail(person.email, draft_data.get("subject") or "", draft_data.get("body") or "", person.id)
        except Exception as exc:
            console.print(f"[red]失败：{exc}[/red]")
            continue
        person.status = "sent"
        person.selected = False
        save_targets(people)
        last = time.time()
        console.print("[green]已发送[/green]")


@app.command()
def status():
    """查看名单概况。"""
    people = load_targets()
    table = Table(title="老师名单")
    table.add_column("状态")
    table.add_column("人数", justify="right")
    counts: dict[str, int] = {}
    for p in people:
        counts[p.status] = counts.get(p.status, 0) + 1
    for k, v in sorted(counts.items()):
        table.add_row(k, str(v))
    console.print(table)
    used, limit = remaining_today()
    console.print(f"今日已发送 {used}/{limit}，附件 {len(list_attachments())} 个")


@app.command()
def ui():
    """启动网页界面。"""
    import subprocess

    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py")], check=False)


if __name__ == "__main__":
    app()
