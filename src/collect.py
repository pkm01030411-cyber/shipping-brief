"""1단계: 기사 수집 → data/YYYY-MM-DD.json (articles, 요약 전 상태)."""
from __future__ import annotations

import logging

from .common import (Article, Http, cutoff_time, day_file, known_urls, load_config,
                     load_day, now_local, save_day, today_str)
from .sources import cargonews, ksg

log = logging.getLogger("brief.collect")

SOURCES = {"ksg": ksg, "cargonews": cargonews}


def run(date: str | None = None) -> dict:
    cfg = load_config()
    date = date or today_str(cfg)
    http = Http(cfg)
    cutoff = cutoff_time(cfg)
    known = known_urls()

    # 같은 날 재실행 시 이미 모은 기사는 유지 (요약도 보존)
    existing = load_day(date) or {}
    articles: list[Article] = [Article.from_dict(a) for a in existing.get("articles", [])]
    known |= {a.url for a in articles}

    for key, mod in SOURCES.items():
        if not cfg["sources"].get(key, {}).get("enabled", False):
            continue
        try:
            articles += mod.collect(cfg, http, cutoff, known)
        except Exception as e:  # noqa: BLE001
            log.exception("%s 수집 중 오류: %s", key, e)

    articles.sort(key=lambda a: a.published, reverse=True)
    if not articles:
        # 새 기사가 없으면 빈 날짜를 만들지 않는다 (사이트는 최신 브리핑을 유지)
        p = day_file(date)
        if p.exists() and not (load_day(date) or {}).get("articles"):
            p.unlink()
        log.info("새 기사 없음 → data/%s.json 생성 안 함", date)
        return {"date": date, "articles": [], "brief": {}}
    payload = {
        "date": date,
        "generated_at": now_local(cfg).isoformat(),
        "articles": [a.to_dict() for a in articles],
        "brief": existing.get("brief", {}),
    }
    save_day(date, payload)
    log.info("총 %d건 저장 → data/%s.json", len(articles), date)
    return payload


def refetch_bodies(articles: list[Article]) -> int:
    """본문이 비어 있는 기사(저장 시 지운 것)를 원문 URL에서 다시 가져온다. 재요약용."""
    cfg = load_config()
    http = Http(cfg)
    n = 0
    for a in articles:
        if a.body:
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
