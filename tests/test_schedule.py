"""수집·게재 일정 판단."""
import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from src import schedule as S

KST = ZoneInfo("Asia/Seoul")
BASE = yaml.safe_load(open(Path(__file__).parent.parent / "config.yaml", encoding="utf-8"))


def cfg(**sched):
    c = json.loads(json.dumps(BASE))
    c["schedule"] = sched
    return c


def at(d, hm):
    h, m = map(int, hm.split(":"))
    return datetime(2026, 11, d, h, m, tzinfo=KST)


def test_override_priority():
    c = cfg(collect=["07:00"], publish="07:00",
            sections={"eurasia": {"collect": ["07:30"], "publish": "08:00"}},
            sources={"meduza": {"collect": ["13:00", "07:00"]}, "ksg": {"collect": "06:00"}})
    assert S.collect_times(c, "ksg") == [time(6)]
    assert S.collect_times(c, "cargonews") == [time(7)]
    assert S.collect_times(c, "portnews") == [time(7, 30)]          # 섹션
    assert S.collect_times(c, "meduza") == [time(7), time(13)]      # 소스
    assert S.publish_time(c, "shipping") == time(7) and S.publish_time(c, "eurasia") == time(8)


def test_bad_time_is_explained():
    with pytest.raises(ValueError, match="HH:MM"):
        S.collect_times(cfg(collect=["7시"]), "ksg")


def test_due_sources_catch_up_and_once_per_slot():
    c = cfg(collect=["07:00"], sources={"meduza": {"collect": ["13:00", "07:00"]}})
    st = {"collected": {}}
    assert "ksg" not in S.due_sources(c, {"collected": {"ksg": at(19, "07:08").isoformat()}}, at(19, "07:37"), "shipping")
    assert S.due_sources(c, st, at(19, "06:37"), "shipping") == ["ksg", "cargonews"]   # 처음엔 어제 07:00 슬롯
    st = {"collected": {"ksg": at(18, "07:10").isoformat(), "cargonews": at(19, "07:10").isoformat()}}
    assert S.due_sources(c, st, at(19, "07:40"), "shipping") == ["ksg"]                # 오늘 슬롯 아직
    st = {"collected": {"meduza": at(19, "07:10").isoformat()}}
    assert "meduza" not in S.due_sources(c, st, at(19, "12:37"), "eurasia")
    assert "meduza" in S.due_sources(c, st, at(19, "13:07"), "eurasia")


def test_window_start_extends_for_missed_days():
    c = cfg()
    now = at(19, "07:07")
    assert S.window_start(c, {"collected": {}}, now, ["ksg"]) == at(18, "00:00")
    st = {"collected": {"ksg": at(16, "07:05").isoformat()}}
    assert S.window_start(c, st, now, ["ksg"]) == at(16, "00:00")
    st = {"collected": {"ksg": at(1, "07:05").isoformat()}}
    assert S.window_start(c, st, now, ["ksg"]) == at(15, "00:00")      # 최대 4일


def test_publish_due_yesterday_mode():
    c = cfg(publish="07:00")
    un = ["2026-11-17", "2026-11-18", "2026-11-19"]
    assert S.publish_due(c, "shipping", at(19, "06:37"), un) == ["2026-11-17"]       # 밀린 날만
    assert S.publish_due(c, "shipping", at(19, "07:07"), un) == ["2026-11-17", "2026-11-18"]  # 오늘 것은 내일


def test_publish_due_today_mode():
    c = cfg(publish="18:30", day="today")
    assert S.publish_due(c, "shipping", at(19, "18:07"), ["2026-11-19"]) == []
    assert S.publish_due(c, "shipping", at(19, "18:37"), ["2026-11-19"]) == ["2026-11-19"]
