"""러시아·유라시아 주간 리뷰: 지난 7일의 유라시아 기사 + KOTRA 러시아·CIS 무역관 뉴스.

KOTRA 해외시장뉴스는 하루 1~2건 수준이라 일일 브리핑 대신 여기서 한 주치를 모아 읽는다.
  python run.py --weekly            # 강제 생성
  python run.py --weekly-if-monday  # 월요일에만 (워크플로)
결과: data/eurasia/weekly/YYYY-Www.json
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta

from .common import Http, load_config, now_local, today_str
from .eurasia import EDIR, SYSTEM, all_edays, load_eday
from .sources import eurasia as src
from .summarize import _call_tool, _client, norm_refs
from .weekly import week_id

log = logging.getLogger("brief.eurasia.weekly")
WDIR = EDIR / "weekly"

WEEKLY_TOOL = {
    "name": "submit_weekly",
    "description": "러시아·유라시아 주간 리뷰를 제출한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string", "description": "이번 주를 한 줄로 (30자 내외)"},
            "overview": {"type": "string", "description": "이번 주 러시아·유라시아 정세 흐름 4~6문장. 사건을 연결해 서사로, 물류·무역 함의까지."},
            "themes": {
                "type": "array", "description": "핵심 테마 3~4개",
                "items": {"type": "object", "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string", "description": "2~4문장"},
                    "article_ids": {"type": "array", "items": {"type": "string"}}},
                    "required": ["title", "body", "article_ids"]},
            },
            "kotra_ids": {"type": "array", "items": {"type": "string"},
                          "description": "KOTRA 기사 id (kotra:...) — 아래 kotra_summaries, kotra_points와 같은 순서"},
            "kotra_summaries": {"type": "array", "items": {"type": "string"},
                                "description": "각 KOTRA 기사 핵심 2문장"},
            "kotra_points": {"type": "array", "items": {"type": "string"},
                             "description": "각 KOTRA 기사가 한국 기업·물류 실무에 주는 시사점 1문장"},
            "top_ids": {"type": "array", "items": {"type": "string"}, "description": "이번 주 꼭 기억할 유라시아 기사 id 3~5개"},
            "top_reasons": {"type": "array", "items": {"type": "string"}, "description": "top_ids와 같은 순서의 이유 1문장"},
            "questions": {"type": "array", "items": {"type": "string"},
                          "description": "면접·자소서용으로 생각해볼 질문 3개 (러시아학 전공 + 물류 지원자 관점)"},
        },
        "required": ["headline", "overview", "themes", "kotra_ids", "kotra_summaries", "kotra_points",
                     "top_ids", "top_reasons", "questions"],
    },
}


def all_eweeks() -> list[str]:
    WDIR.mkdir(parents=True, exist_ok=True)
    return sorted((p.stem for p in WDIR.glob("????-W??.json")), reverse=True)


def load_eweek(wid: str) -> dict | None:
    p = WDIR / f"{wid}.json"
    return json.load(open(p, encoding="utf-8")) if p.exists() else None


def gather_kotra(cfg, start: str, end: str) -> list[dict]:
    kcfg = cfg["eurasia"].get("kotra") or {}
    if not kcfg.get("enabled"):
        return []
    http = Http(cfg)
    items, seen = [], set()
    for code, name in (kcfg.get("countries") or {}).items():
        try:
            got = src.kotra_list(http, str(code))
        except Exception as e:  # noqa: BLE001
            log.warning("KOTRA %s 목록 실패: %s", name, e)
            continue
        for it in got:
            if it["id"] in seen or not (start <= it["date"] <= end):
                continue
            seen.add(it["id"])
            it["country"] = name
            items.append(it)
    items.sort(key=lambda x: x["date"], reverse=True)
    items = items[: int(kcfg.get("max_items", 15))]
    for it in items:
        try:
            it["body"] = src.parse_kotra_detail(http.get(it["url"]).text)
        except Exception as e:  # noqa: BLE001
            log.warning("KOTRA 본문 실패 %s: %s", it["url"], e)
            it["body"] = ""
    log.info("KOTRA 러시아·CIS: %d건 (%s~%s)", len(items), start, end)
    return items


def run(end_date: str | None = None, only_monday: bool = False) -> dict | None:
    cfg = load_config()
    if not (cfg.get("eurasia") or {}).get("enabled"):
        return None
    now = now_local(cfg)
    if only_monday and now.weekday() != 0:
        return None
    end = datetime.strptime(end_date or today_str(cfg), "%Y-%m-%d").date()
    if only_monday:
        end -= timedelta(days=1)
    start = end - timedelta(days=6)
    wid = week_id(end)
    if only_monday and (WDIR / f"{wid}.json").exists():
        log.info("유라시아 주간 %s 이미 있음 → 건너뜀", wid)
        return load_eweek(wid)

    wanted = {(end - timedelta(days=i)).isoformat() for i in range(7)}
    arts = []
    for d in sorted(x for x in all_edays() if x in wanted):
        for a in (load_eday(d) or {}).get("articles", []):
            arts.append({**a, "date": d})
    kotra = gather_kotra(cfg, start.isoformat(), end.isoformat())
    if not arts and not kotra:
        log.warning("유라시아 주간 리뷰 대상 없음")
        return None

    client = _client()
    review: dict
    if client is None:
        review = {"headline": f"지난 7일 유라시아 {len(arts)}건 · KOTRA {len(kotra)}건",
                  "overview": "ANTHROPIC_API_KEY 없이 생성된 주간 리뷰입니다.", "themes": [], "top": [],
                  "questions": [], "offline": True}
        for k in kotra:
            k["summary"], k["point"] = k["summary_raw"], ""
    else:
        lines = [f"[{a['id']}] {a['date']} ({a['source_name']} · {a.get('stance', '')}, 관련도 {a.get('relevance', 0)}) "
                 f"{a['title']}\n   {a.get('summary', '')}" for a in sorted(arts, key=lambda a: a["published"])]
        klines = [f"[{k['id']}] {k['date']} {k['kbc']} ({k['country']}, {k['board']}) {k['title']}\n"
                  f"   {(k['body'] or k['summary_raw'])[:1800]}" for k in kotra]
        interests = "\n".join(f"- {i}" for i in cfg["eurasia"]["interests"])
        user = (f"독자 관심사:\n{interests}\n\n{start} ~ {end} 한 주의 러시아·유라시아 기사 {len(arts)}건과 "
                f"KOTRA 러시아·CIS 무역관 뉴스 {len(kotra)}건입니다. 주간 리뷰를 submit_weekly로 제출하세요. "
                f"KOTRA 기사는 하나도 빠짐없이 kotra_ids/kotra_summaries/kotra_points에 같은 순서로. "
                f"themes·top의 id는 아래 목록에 있는 것만.\n\n"
                f"=== 유라시아 기사 ===\n" + ("\n".join(lines) or "(없음)") +
                f"\n\n=== KOTRA 무역관 뉴스 ===\n" + ("\n\n".join(klines) or "(없음)"))
        review = _call_tool(client, cfg, WEEKLY_TOOL, user, system=SYSTEM, max_tokens=cfg["eurasia"]["max_tokens"])
        valid = {a["id"] for a in arts}
        titles = {a["title"]: a["id"] for a in arts}
        ids, reasons = review.pop("top_ids", None) or [], review.pop("top_reasons", None) or []
        review["top"] = norm_refs([{"id": i, "reason": reasons[n] if n < len(reasons) else ""}
                                   for n, i in enumerate(ids)] if isinstance(ids, list) else ids,
                                  valid, 5, titles=titles)
        themes = []
        for t in review.get("themes") or []:
            if isinstance(t, dict):
                tids = t.get("article_ids") or []
                themes.append({"title": str(t.get("title", "")), "body": str(t.get("body", "")),
                               "article_ids": [r["id"] for r in norm_refs(list(tids) if isinstance(tids, list) else [tids],
                                                                          valid, titles=titles)]})
        review["themes"] = themes
        kid, ks, kp = (review.pop("kotra_ids", None) or [], review.pop("kotra_summaries", None) or [],
                       review.pop("kotra_points", None) or [])
        by_k = {}
        for n, i in enumerate(kid if isinstance(kid, list) else []):
            i = str(i).strip("[] ")
            by_k[i] = (str(ks[n]) if n < len(ks) else "", str(kp[n]) if n < len(kp) else "")
        for k in kotra:
            k["summary"], k["point"] = by_k.get(k["id"], (k["summary_raw"], ""))
            k["summary"] = k["summary"] or k["summary_raw"]
        review["questions"] = [str(q) for q in review.get("questions") or [] if q]
        review["model"] = cfg["summarize"]["model"]

    for k in kotra:
        k.pop("body", None)
    ref_ids = {t["id"] for t in review.get("top", [])} | {i for t in review.get("themes", []) for i in t["article_ids"]}
    payload = {
        "week": wid, "start": start.isoformat(), "end": end.isoformat(), "generated_at": now.isoformat(),
        "article_count": len(arts), "review": review, "kotra": kotra,
        "tag_counts": Counter(t for a in arts for t in a.get("tags", [])).most_common(16),
        "articles": [a for a in arts if a["id"] in ref_ids],
    }
    WDIR.mkdir(parents=True, exist_ok=True)
    with open(WDIR / f"{wid}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.info("유라시아 주간 리뷰 생성: %s (기사 %d, KOTRA %d)", wid, len(arts), len(kotra))
    return payload
