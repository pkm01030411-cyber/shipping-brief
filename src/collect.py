"""1단계: 기사 수집 → data/YYYY-MM-DD.json (기사 발행일 기준, 요약 전 상태)."""
from __future__ import annotations

import logging

from collections import defaultdict
from datetime import datetime, timedelta

from .common import (Article, Http, cache_body, cached_body, is_published, known_urls, load_config,
                     load_day, now_local, save_day, today_str)
from .sources import cargonews, ksg

log = logging.getLogger("brief.collect")

SOURCES = {"ksg": ksg, "cargonews": cargonews}


def sweep(keys: list[str], start: datetime) -> dict[str, int]:
    """소스들을 훑어 start 이후 새 기사를 '발행일(한국 시간)' 날짜 파일에 나눠 담는다. 요약은 하지 않는다.
    새로 만든 날짜 파일은 published_at=None (게재 전 — 사이트에 안 보임). 본문은 cache/에만 둔다.
    반환: {날짜: 추가 건수}"""
    cfg = load_config()
    http = Http(cfg)
    known = known_urls(30)
    new: list[Article] = []
    for key in keys:
        mod = SOURCES.get(key)
        if not mod or not cfg["sources"].get(key, {}).get("enabled", False):
            continue
        try:
            got = mod.collect(cfg, http, start, known)
        except Exception as e:  # noqa: BLE001
            log.exception("%s 수집 중 오류: %s", key, e)
            continue
        log.info("%s: 새 기사 %d건", key, len(got))
        known |= {a.url for a in got}
        new += got

    added: dict[str, int] = defaultdict(int)
    by_date: dict[str, list[Article]] = defaultdict(list)
    for a in new:
        cache_body(a.id, a.body)
        a.body = ""
        by_date[a.published[:10]].append(a)
    for d, arts in by_date.items():
        day = load_day(d) or {"date": d, "articles": [], "brief": {}, "published_at": None}
        have = {x["url"] for x in day.get("articles", [])}
        fresh = [a for a in arts if a.url not in have]
        if not fresh:
            continue
        day["articles"] = sorted(day.get("articles", []) + [a.to_dict() for a in fresh],
                                 key=lambda x: x["published"], reverse=True)
        day["collected_at"] = now_local(cfg).isoformat(timespec="seconds")
        save_day(d, day)
        added[d] += len(fresh)
        log.info("data/%s.json ← %d건 (누적 %d건, %s)", d, len(fresh), len(day["articles"]),
                 "게재됨" if is_published(day) else "게재 전")
    return dict(added)


def run(date: str | None = None) -> dict:
    """(호환) 지금 바로 모든 소스를 어제 0시부터 훑는다."""
    cfg = load_config()
    now = now_local(cfg)
    start = datetime.combine(now.date() - timedelta(days=1), datetime.min.time(), tzinfo=now.tzinfo)
    keys = [k for k, v in cfg["sources"].items() if v.get("enabled")]
    sweep(keys, start)
    return load_day(date or today_str(cfg)) or {}


def refetch_bodies(articles: list[Article]) -> int:
    """본문이 비어 있는 기사(저장 시 지운 것)를 원문 URL에서 다시 가져온다. 재요약용."""
    cfg = load_config()
    http = Http(cfg)
    n = 0
    for a in articles:
        if a.body:
            continue
        a.body = cached_body(a.id)  # 같은 실행(또는 같은 러너)에서 수집한 본문
        if a.body:
            n += 1
            continue
        mod = SOURCES.get(a.source)
        if not mod:
            continue
        try:
            detail = mod.parse_article(http.get(a.url).text, cfg)
            if detail.get("body"):
                a.body = detail["body"]
                n += 1
        except Exception as e:  # noqa: BLE001
            log.warning("본문 재수집 실패 %s: %s", a.url, e)
    log.info("본문 재수집: %d건", n)
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run()
