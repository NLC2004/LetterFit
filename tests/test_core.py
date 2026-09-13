from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from draft import _fill_slots, honorific_for, missing_slots, profile_experiences
from llm import parse_json
from store import make_id
from web import normalize_email, regex_emails


def test_honorific():
    assert honorific_for("张三") == "张"
    assert honorific_for("欧阳修") == "欧阳"


def test_fill_slots():
    tpl = "尊敬的{老师称呼}老师：{老师方向}{交叉经历}{契合段}"
    out = _fill_slots(
        tpl,
        {"老师称呼": "李", "老师方向": "机器学习", "交叉经历": "检测", "契合段": "希望加入。"},
    )
    assert "{" not in out
    assert "尊敬的李老师" in out


def test_missing_slots():
    assert missing_slots("尊敬的{老师称呼}老师 {老师方向} {交叉经历} {契合段}") == []
    assert "{契合段}" in missing_slots("尊敬的{老师称呼}老师")


def test_profile_experiences_legacy_research():
    profile = {"research": [{"org": "实验室", "keywords": "检测", "desc": "做检测"}]}
    rows = profile_experiences(profile)
    assert rows[0]["org"] == "实验室"
    assert rows[0]["detail"] == "做检测"


def test_parse_json_fenced():
    data = parse_json("```json\n{\"老师称呼\": \"王\"}\n```")
    assert data["老师称呼"] == "王"


def test_normalize_and_regex_emails():
    assert normalize_email("mailto:A.B@Example.Edu.Cn") == "a.b@example.edu.cn"
    found = regex_emails("联系 foo@bar.edu.cn 或 name [at] school.edu.cn")
    assert "foo@bar.edu.cn" in found


def test_make_id_stable():
    a = make_id("清华", "王老师", "w@x.edu.cn")
    b = make_id("清华", "王老师", "W@X.EDU.CN")
    assert a == b
    assert len(a) == 10
