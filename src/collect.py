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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run()
