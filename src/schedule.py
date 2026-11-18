"""수집·게재 일정.

GitHub Actions가 30분마다 깨어나 `python run.py`(= --auto)를 실행하면, 이 모듈이
config.yaml의 `schedule:`을 읽고 지금 해야 할 일을 정한다.

  수집(collect) : 소스를 훑어 새 기사를 '기사 발행일(한국 시간)' 날짜 파일에 모은다. 요약하지 않음(API 비용 0).
  게재(publish) : 대상 날짜(기본: 전날) 기사를 요약·브리핑하고 사이트에 공개한다.

시각은 '이 시각이 지난 뒤 첫 점검'에 실행된다. GitHub 스케줄러가 늦거나 한 번 건너뛰어도
다음 점검에서 따라잡는다(밀린 수집·게재는 모두 처리).

state: data/state.json  {"collected": {소스키: 마지막 수집 시각 ISO}}
게재 여부는 각 날짜 파일의 "published_at" (없으면 예전 방식 파일 = 이미 게재).
"""
from __future__ import annotations

import json
import re
from datetime import date as Date
from datetime import datetime, time, timedelta

from .common import DATA_DIR, now_local

STATE_FILE = DATA_DIR / "state.json"
SECTIONS = ("shipping", "eurasia")


def _times(v) -> list[time]:
    if v is None:
        return []
    if isinstance(v, (str, int)):
        v = [v]
    out = []
    for s in v:
        s = str(s).strip()
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise ValueError(f"시각 형식 오류: {s!r} — \"07:00\"처럼 HH:MM으로 적어 주세요")
        out.append(time(int(m.group(1)), int(m.group(2))))
    return sorted(set(out))


def _sched(cfg) -> dict:
    return cfg.get("schedule") or {}


def section_of(cfg, key: str) -> str:
    return "eurasia" if key in ((cfg.get("eurasia") or {}).get("sources") or {}) else "shipping"


def source_keys(cfg, section: str | None = None) -> list[str]:
    keys = []
    if section in (None, "shipping"):
        keys += [k for k, v in cfg["sources"].items() if v.get("enabled", False)]
    if section in (None, "eurasia") and (cfg.get("eurasia") or {}).get("enabled"):
        keys += [k for k, v in cfg["eurasia"]["sources"].items() if v.get("enabled", True)]
    return keys


def collect_times(cfg, key: str) -> list[time]:
    """소스 > 섹션 > 전체 순으로 덮어쓴다."""
    s = _sched(cfg)
    src = (s.get("sources") or {}).get(key) or {}
    if "collect" in src:
        return _times(src["collect"])
    sec = (s.get("sections") or {}).get(section_of(cfg, key)) or {}
    if "collect" in sec:
        return _times(sec["collect"])
    return _times(s.get("collect", "07:00"))


def publish_time(cfg, section: str) -> time:
    s = _sched(cfg)
    sec = (s.get("sections") or {}).get(section) or {}
    t = _times(sec.get("publish", s.get("publish", "07:00")))
    return t[0]


def publish_day(cfg, section: str) -> str:
    """'yesterday'(기본): 아침에 전날치를 게재 / 'today': 그날 저녁에 당일치를 게재."""
    s = _sched(cfg)
    sec = (s.get("sections") or {}).get(section) or {}
    v = str(sec.get("day", s.get("day", "yesterday"))).strip().lower()
    if v not in ("yesterday", "today"):
        raise ValueError(f"schedule day는 yesterday 또는 today: {v!r}")
    return v


def last_slot(times: list[time], now: datetime) -> datetime | None:
    """now 이전의 가장 최근 예정 시각 (오늘 또는 어제)."""
    best = None
    for d in (now.date(), now.date() - timedelta(days=1)):
        for t in times:
            dt = datetime.combine(d, t, tzinfo=now.tzinfo)
            if dt <= now and (best is None or dt > best):
                best = dt
    return best


# ── 상태 ────────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        return json.load(open(STATE_FILE, encoding="utf-8"))
    return {"collected": {}}


def save_state(st: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2, sort_keys=True)


def due_sources(cfg, st: dict, now: datetime, section: str) -> list[str]:
    due = []
    for k in source_keys(cfg, section):
        slot = last_slot(collect_times(cfg, k), now)
        last = st.get("collected", {}).get(k)
        if slot is None:
            continue
        if last is None or datetime.fromisoformat(last) < slot:
            due.append(k)
    return due


def window_start(cfg, st: dict, now: datetime, keys: list[str]) -> datetime:
    """수집 범위의 시작: 어제 0시, 단 마지막 수집이 더 오래됐으면 그날 0시부터(최대 4일). 밀린 날 따라잡기."""
    start = datetime.combine(now.date() - timedelta(days=1), time(0), tzinfo=now.tzinfo)
    floor = start - timedelta(days=3)
    for k in keys:
        last = st.get("collected", {}).get(k)
        if last:
            d = datetime.fromisoformat(last).astimezone(now.tzinfo)
            start = min(start, datetime.combine(d.date(), time(0), tzinfo=now.tzinfo))
    return max(start, floor)


def mark_collected(st: dict, keys: list[str], now: datetime) -> None:
    st.setdefault("collected", {}).update({k: now.isoformat(timespec="seconds") for k in keys})


def target_day(cfg, section: str, now: datetime) -> Date:
    return now.date() - timedelta(days=1) if publish_day(cfg, section) == "yesterday" else now.date()


def publish_due(cfg, section: str, now: datetime, unpublished: list[str]) -> list[str]:
    """게재할 날짜들. 대상일(전날 또는 당일)은 게재 시각이 지났을 때, 그보다 이전의 밀린 날짜는 바로."""
    t = publish_time(cfg, section)
    target = target_day(cfg, section, now)
    out = []
    for d in sorted(unpublished):
        dd = Date.fromisoformat(d)
        if dd < target or (dd == target and now.time() >= t):
            out.append(d)
    return out


def describe(cfg) -> list[str]:
    """사람이 읽는 일정 요약 (로그·README용)."""
    lines = []
    for sec in SECTIONS:
        if sec == "eurasia" and not (cfg.get("eurasia") or {}).get("enabled"):
            continue
        day = "전날" if publish_day(cfg, sec) == "yesterday" else "당일"
        lines.append(f"[{sec}] 게재 {publish_time(cfg, sec).strftime('%H:%M')} ({day} 기사)")
        for k in source_keys(cfg, sec):
            lines.append(f"   - {k}: 수집 " + ", ".join(t.strftime("%H:%M") for t in collect_times(cfg, k)))
    return lines


def now(cfg) -> datetime:
    return now_local(cfg)
