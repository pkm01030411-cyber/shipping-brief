"""3단계: data/*.json → site/ (정적 HTML)."""
from __future__ import annotations

import logging
import shutil
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .common import (SITE_DIR, STATIC_DIR, TEMPLATE_DIR, all_days, load_config,
                     load_day, now_local)

log = logging.getLogger("brief.build")

WEEKDAYS = "월화수목금토일"


def fmt_date(s: str) -> str:
    d = datetime.strptime(s, "%Y-%m-%d")
    return f"{d.year}년 {d.month}월 {d.day}일 ({WEEKDAYS[d.weekday()]})"


def fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%m.%d %H:%M")
    except ValueError:
        return iso


def prepare_day(day: dict) -> dict:
    """템플릿용 가공: Top 기사 분리, 관련도순 정렬, 출처별 집계."""
    arts = day.get("articles", [])
    brief = day.get("brief", {}) or {}
    by_id = {a["id"]: a for a in arts}
    top = []
    for t in brief.get("top", []):
        a = by_id.get(t["id"])
        if a:
            top.append({**a, "reason": t.get("reason", "")})
    top_ids = {t["id"] for t in top}
    rest = [a for a in arts if a["id"] not in top_ids]
    rest.sort(key=lambda a: (-(a.get("relevance") or 0), a["published"]), reverse=False)
    # relevance 내림차순, 같은 점수면 최신순
    rest.sort(key=lambda a: a["published"], reverse=True)
    rest.sort(key=lambda a: -(a.get("relevance") or 0))
    sources = {}
    for a in arts:
        sources[a["source_name"]] = sources.get(a["source_name"], 0) + 1
    return {**day, "top": top, "rest": rest, "sources": sources, "brief": brief,
            "date_label": fmt_date(day["date"])}


def build() -> None:
    cfg = load_config()
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]))
    env.filters["ftime"] = fmt_time
    env.filters["fdate"] = fmt_date

    days = all_days()
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    (SITE_DIR / "day").mkdir(parents=True)
    shutil.copytree(STATIC_DIR, SITE_DIR / "static")

    site = {**cfg["site"], "built_at": now_local(cfg).strftime("%Y-%m-%d %H:%M")}
    archive = []
    prepared = {}
    for d in days:
        day = load_day(d)
        if not day:
            continue
        p = prepare_day(day)
        prepared[d] = p
        archive.append({"date": d, "label": p["date_label"], "count": len(day["articles"]),
                        "headline": p["brief"].get("headline", "")})

    day_tpl = env.get_template("day.html")
    for i, d in enumerate(days):
        if d not in prepared:
            continue
        prev_d = days[i + 1] if i + 1 < len(days) else None
        next_d = days[i - 1] if i > 0 else None
        html = day_tpl.render(site=site, day=prepared[d], prev=prev_d, next=next_d, root="../")
        (SITE_DIR / "day" / f"{d}.html").write_text(html, encoding="utf-8")

    # 인덱스 = 가장 최근 날짜
    if days:
        latest = prepared[days[0]]
        html = day_tpl.render(site=site, day=latest, prev=days[1] if len(days) > 1 else None,
                              next=None, root="", is_index=True)
    else:
        html = env.get_template("empty.html").render(site=site, root="")
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")

    html = env.get_template("archive.html").render(site=site, archive=archive, root="")
    (SITE_DIR / "archive.html").write_text(html, encoding="utf-8")
    (SITE_DIR / ".nojekyll").write_text("")
    log.info("사이트 생성: %d일치 → site/", len(days))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build()
