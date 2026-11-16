"""주간 리뷰: 지난 7일치 브리핑을 묶어 Claude가 흐름·핵심 기사·면접용 질문을 정리.

  python run.py --weekly            # 강제 생성 (오늘 기준 지난 7일)
  python run.py --weekly-if-monday  # 월요일에만 (워크플로용)
결과: data/weekly/YYYY-Www.json
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import timedelta
from pathlib import Path

from .common import DATA_DIR, Article, all_days, load_config, load_day, now_local, today_str
from .summarize import SYSTEM, _call_tool, _client, norm_refs

log = logging.getLogger("brief.weekly")
WEEKLY_DIR = DATA_DIR / "weekly"

WEEKLY_TOOL = {
    "name": "submit_weekly",
    "description": "주간 리뷰를 제출한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string", "description": "이번 주를 한 줄로 (30자 내외)"},
            "overview": {"type": "string", "description": "이번 주 업계 흐름 4~6문장. 날짜별 사건을 연결해 서사로."},
            "themes": {
                "type": "array",
                "description": "이번 주 핵심 테마 3~5개",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string", "description": "2~4문장. 어떤 기사들이 이 테마를 이루는지"},
                        "article_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "body", "article_ids"],
                },
            },
            "top": {
                "type": "array",
                "description": "이번 주 꼭 기억할 기사 5개",
                "items": {"type": "object", "properties": {"id": {"type": "string"}, "reason": {"type": "string"}},
                          "required": ["id", "reason"]},
            },
            "questions": {
                "type": "array", "items": {"type": "string"},
                "description": "이번 주 뉴스를 바탕으로 면접관이 물을 법한 질문 또는 자소서에 녹일 만한 관점 3~5개",
            },
        },
        "required": ["headline", "overview", "themes", "top", "questions"],
    },
}


def week_id(d) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def all_weeks() -> list[str]:
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    return sorted((p.stem for p in WEEKLY_DIR.glob("????-W??.json")), reverse=True)


def load_week(wid: str) -> dict | None:
    p = WEEKLY_DIR / f"{wid}.json"
    return json.load(open(p, encoding="utf-8")) if p.exists() else None


def gather(cfg, end_date: str, days: int = 7) -> tuple[list[dict], list[str]]:
    """end_date(포함) 기준 지난 N일의 기사와 날짜 목록."""
    from datetime import datetime
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    wanted = {(end - timedelta(days=i)).isoformat() for i in range(days)}
    dates = sorted(d for d in all_days() if d in wanted)
    arts: list[dict] = []
    for d in dates:
        day = load_day(d) or {}
        for a in day.get("articles", []):
            arts.append({**a, "date": d})
    return arts, dates


def offline_review(arts: list[dict]) -> dict:
    top = sorted(arts, key=lambda a: (-(a.get("relevance") or 0), a["published"]))[:5]
    return {"headline": f"지난 7일 {len(arts)}건", "overview": "ANTHROPIC_API_KEY 없이 생성된 주간 리뷰입니다.",
            "themes": [], "top": [{"id": a["id"], "reason": "관련도 상위"} for a in top], "questions": [], "offline": True}


def run(end_date: str | None = None, only_monday: bool = False) -> dict | None:
    cfg = load_config()
    now = now_local(cfg)
    if only_monday and now.weekday() != 0:
        log.info("월요일이 아니므로 주간 리뷰 건너뜀")
        return None
    end_date = end_date or today_str(cfg)
    # 월요일 실행이면 '지난주 월~일'이 대상 → 전날(일요일)까지
    from datetime import datetime
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if only_monday:
        end = end - timedelta(days=1)
    arts, dates = gather(cfg, end.isoformat())
    if not arts:
        log.warning("주간 리뷰 대상 기사 없음")
        return None
    wid = week_id(end)
    start = (end - timedelta(days=6)).isoformat()

    client = _client()
    if client is None:
        review = offline_review(arts)
    else:
        lines = []
        for a in sorted(arts, key=lambda a: a["published"]):
            lines.append(f"[{a['id']}] {a['date']} ({a['source_name']}, 관련도 {a.get('relevance', 0)}) {a['title']}\n"
                         f"   {a.get('summary', '')}")
        interests = "\n".join(f"- {i}" for i in cfg["summarize"]["interests"])
        user = (f"독자 관심사:\n{interests}\n\n{start} ~ {end} 한 주 동안 수집된 기사 {len(arts)}건입니다. "
                f"한 주의 흐름을 정리한 주간 리뷰를 submit_weekly로 제출하세요. "
                f"themes의 article_ids와 top의 id는 반드시 아래 목록의 id만 사용할 것.\n\n" + "\n".join(lines))
        review = _call_tool(client, cfg, WEEKLY_TOOL, user)
        valid = {a["id"] for a in arts}
        titles = {a["title"]: a["id"] for a in arts}
        review["top"] = norm_refs(review.get("top"), valid, 5, titles=titles)
        themes = []
        for t in review.get("themes") or []:
            if not isinstance(t, dict):
                continue
            ids = t.get("article_ids") or []
            if isinstance(ids, str):
                ids = [ids]
            themes.append({"title": str(t.get("title", "")), "body": str(t.get("body", "")),
                           "article_ids": [r["id"] for r in norm_refs(list(ids), valid, titles=titles)]})
        review["themes"] = themes
        review["questions"] = [str(q) for q in (review.get("questions") or []) if q]
        review["model"] = cfg["summarize"]["model"]

    tag_counts = Counter(t for a in arts for t in a.get("tags", []))
    payload = {
        "week": wid, "start": start, "end": end.isoformat(), "dates": dates,
        "article_count": len(arts), "generated_at": now.isoformat(),
        "review": review,
        "tag_counts": tag_counts.most_common(20),
        # 페이지 렌더에 필요한 기사 스냅샷 (top·themes에서 참조되는 것만)
        "articles": [a for a in arts if a["id"] in
                     ({t["id"] for t in review.get("top", [])} |
                      {i for t in review.get("themes", []) for i in t.get("article_ids", [])})],
    }
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    with open(WEEKLY_DIR / f"{wid}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.info("주간 리뷰 생성: %s (%d건)", wid, len(arts))
    return payload
