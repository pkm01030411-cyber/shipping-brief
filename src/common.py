"""공용 유틸: 설정 로드, HTTP 세션, 날짜 처리, 데이터 파일 입출력."""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"
TEMPLATE_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"

log = logging.getLogger("brief")


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def tz(cfg: dict) -> ZoneInfo:
    return ZoneInfo(cfg["site"].get("timezone", "Asia/Seoul"))


def now_local(cfg: dict) -> datetime:
    return datetime.now(tz(cfg))


def today_str(cfg: dict) -> str:
    return now_local(cfg).strftime("%Y-%m-%d")


# ── 기사 데이터 모델 ────────────────────────────────────────────
@dataclass
class Article:
    id: str                      # "ksg:148502", "cargonews:61242"
    source: str                  # "ksg" | "cargonews"
    source_name: str             # 표시용 이름
    title: str
    url: str
    published: str               # ISO 8601 (로컬 시간대 포함)
    category: str = ""
    subtitle: str = ""
    author: str = ""
    body: str = ""               # 본문 텍스트 (요약 입력용)
    # ── 요약 단계에서 채워짐 ──
    summary: str = ""
    why: str = ""
    insight: str = ""            # 어떻게 읽어야 하나 (맥락·파급)
    terms: list[dict] = field(default_factory=list)   # [{term, explanation}]
    tags: list[str] = field(default_factory=list)
    relevance: int = 0           # 1~5
    geo: dict = field(default_factory=dict)  # 국제정세 태깅 ({} = 아직 분석 안 함)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Article":
        defaults = {"tags": [], "terms": [], "relevance": 0, "geo": {}}
        return cls(**{k: d.get(k, defaults.get(k, "")) for k in cls.__dataclass_fields__})


# ── HTTP ────────────────────────────────────────────────────────
class Http:
    def __init__(self, cfg: dict):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": cfg["collect"]["user_agent"],
            "Accept-Language": "ko-KR,ko;q=0.9",
        })
        self.delay = float(cfg["collect"].get("delay_seconds", 0.5))
        self._last = 0.0

    def get(self, url: str, **kw) -> requests.Response:
        wait = self.delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        r = self.s.get(url, timeout=20, **kw)
        self._last = time.time()
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
            r.encoding = r.apparent_encoding
        return r


# ── 텍스트 정리 ──────────────────────────────────────────────────
_WS = re.compile(r"[ \t ]+")
_NL = re.compile(r"\n{3,}")


def clean_text(s: str) -> str:
    s = s.replace("\r", "")
    s = _WS.sub(" ", s)
    s = "\n".join(line.strip() for line in s.split("\n"))
    s = _NL.sub("\n\n", s)
    return s.strip()


# ── 데이터 파일 ──────────────────────────────────────────────────
def day_file(date: str) -> Path:
    return DATA_DIR / f"{date}.json"


def load_day(date: str) -> dict | None:
    p = day_file(date)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_day(date: str, payload: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(day_file(date), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def all_days() -> list[str]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sorted((p.stem for p in DATA_DIR.glob("????-??-??.json")), reverse=True)


def is_published(day: dict | None) -> bool:
    """게재된 날짜인가. published_at 필드가 없는 파일은 예전 방식(수집 즉시 게재)이라 게재된 것으로 본다."""
    return bool(day) and ("published_at" not in day or bool(day.get("published_at")))


def published_days() -> list[str]:
    return [d for d in all_days() if is_published(load_day(d))]


# ── 본문 임시 보관 (저장소에 커밋하지 않음: .gitignore의 cache/) ─────────
CACHE_DIR = ROOT / "cache" / "bodies"


def cache_body(aid: str, body: str) -> None:
    if body:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / (aid.replace(":", "_").replace("/", "_") + ".txt")).write_text(body, encoding="utf-8")


def cached_body(aid: str) -> str:
    p = CACHE_DIR / (aid.replace(":", "_").replace("/", "_") + ".txt")
    return p.read_text(encoding="utf-8") if p.exists() else ""


def known_urls(days_back: int = 14) -> set[str]:
    """최근 N일간 이미 수집한 기사 URL (중복 방지)."""
    urls: set[str] = set()
    for d in all_days()[:days_back]:
        day = load_day(d) or {}
        for a in day.get("articles", []):
            urls.add(a["url"])
    return urls


def parse_kst(s: str, cfg: dict) -> datetime | None:
    """'2026-11-16 09:07' / '2026-11-16 09:07:12' / ISO 문자열 → aware datetime."""
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=tz(cfg))
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=tz(cfg))
    except ValueError:
        return None
