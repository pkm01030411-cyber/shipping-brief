"""러시아·유라시아 정세 섹션: 수집 → 관련도 선별 → 한국어 번역 요약 → 오늘의 브리핑.

  data/eurasia/YYYY-MM-DD.json
    articles: 게재 기사 (하루 10~15건, 한국어 제목·요약)
    screened: 선별에서 빠진 후보 (한국어 제목만 — '그 밖의 기사' 목록과 중복 방지용)
    brief:    헤드라인 · 흐름 · Top 3 · 지켜볼 포인트

해운물류 브리핑과 같은 원칙: 같은 날 재실행(백업 cron)해도 새 기사가 없으면 API를 부르지 않는다.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from .common import DATA_DIR, Article, Http, load_config, now_local, today_str
from .sources import eurasia as src
from .summarize import BRIEF_TOOL, _call_tool, _client, norm_refs

log = logging.getLogger("brief.eurasia")
EDIR = DATA_DIR / "eurasia"

SYSTEM = """당신은 러시아·유라시아 정세를 매일 추려 주는 지역 애널리스트이자 번역가입니다.
독자는 러시아학을 전공하고 국제물류 포워더·정기선사 취업을 준비하는 한국 대학생입니다.
목표는 '러시아·중앙아시아·코카서스·북극의 정세가 무역·물류에 어떤 의미인지'를 매일 10분 안에 파악하는 것.

번역 원칙:
- 원문은 영어 또는 러시아어. 제목·요약·해설은 모두 자연스러운 한국어로 쓴다(번역투 금지, '~다' 체).
- 인명·지명은 국립국어원 외래어 표기법을 따른다(블라디보스토크, 무르만스크, 토카예프, 미르지요예프).
  독자가 원어를 찾아볼 법한 핵심 고유명사만 처음 한 번 괄호로 원어 병기(예: 노바테크(Novatek)).
- 수치·날짜·단위는 원문 그대로. 기사에 없는 사실을 보태지 않는다.

출처 시각:
- 기사마다 '출처 시각'이 주어진다(독립 망명 언론, 러시아 업계지, 지역 매체 등). 매체의 프레이밍을 사실처럼 옮기지 말고,
  주장·평가는 "~라고 매체는 전했다/주장했다"처럼 출처를 드러낸다. 크렘린·정부 발표도 마찬가지.

요약 필드:
- summary: 2~3문장 핵심 사실.
- why: 정세 관점에서 왜 중요한가 1문장.
- logistics: 해운·철도·항만·무역·제재 집행에 미칠 영향 1문장. 물류와 정말 무관하면 빈 문자열.
- insight: 어떻게 읽어야 하나 — 과거 흐름·다른 나라·다른 기사와 연결한 해석 1~2문장. 추측은 '~가능성이 있다'로 표시.
- terms: 러시아·유라시아 정치경제나 물류 용어 중 독자가 정확히 설명 못 할 법한 것 0~2개
  (예: EAEU(유라시아경제연합), 실로비키, 그림자 선단, NSR 운항 허가, 중간회랑(TITR)). 한 문장 해설.
- tags: 2~4개 짧은 한국어 명사 (예: 러시아, 제재, 북극항로, 카자흐스탄, 중간회랑, 유가, 우크라이나전쟁).
- relevance 1~5: 독자 관심사와의 관련도. 관심사 밖이어도 지역 전체에 큰 사건이면 4 이상.
  국내 사회·문화·개별 범죄·연예·스포츠는 1~2."""

SCREEN_TOOL = {
    "name": "submit_screening",
    "description": "후보 기사마다 한국어 제목과 관련도 점수를 제출한다. 세 배열은 같은 길이·같은 순서.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ids": {"type": "array", "items": {"type": "string"}, "description": "후보 id (예: meduza:1a2b3c4d5e) — 입력 순서대로 전부"},
            "titles_ko": {"type": "array", "items": {"type": "string"}, "description": "ids와 같은 순서의 한국어 제목 (40자 내외)"},
            "scores": {"type": "array", "items": {"type": "integer"}, "description": "ids와 같은 순서의 관련도 1~5"},
        },
        "required": ["ids", "titles_ko", "scores"],
    },
}


def as_list(x) -> list:
    """모델이 배열 대신 JSON 문자열이나 도구 마크업 문자열을 줄 때도 리스트로 복원한다."""
    if isinstance(x, list):
        out = []
        for v in x:
            if isinstance(v, str) and v.strip().startswith(("{", "[")):
                try:
                    v = json.loads(v)
                except json.JSONDecodeError:
                    pass
            out.extend(v if isinstance(v, list) else [v])
        return out
    if isinstance(x, str):
        t = x.strip()
        if t.startswith(("[", "{")):
            try:
                v = json.loads(t)
                return as_list(v if isinstance(v, list) else [v])
            except json.JSONDecodeError:
                pass
        blocks = re.split(r"<item>|(?=<parameter name=\"id\">)", t)
        items = []
        for b in blocks:
            params = dict(re.findall(r'<parameter name="(\w+)">\s*(.*?)\s*(?:</parameter>|(?=<parameter)|(?=</item>)|$)', b, re.S))
            if params:
                items.append(params)
        if items:
            return items
        return [v.strip() for v in t.split("\n") if v.strip()]
    return [] if x is None else [x]


ARTICLE_TOOL = {
    "name": "submit_summaries",
    "description": "각 기사의 한국어 번역 요약을 제출한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title_ko": {"type": "string", "description": "본문을 읽고 다듬은 한국어 제목"},
                        "summary": {"type": "string"},
                        "why": {"type": "string"},
                        "logistics": {"type": "string", "description": "물류·무역 영향 1문장, 무관하면 빈 문자열"},
                        "insight": {"type": "string"},
                        "terms": {"type": "array", "items": {
                            "type": "object",
                            "properties": {"term": {"type": "string"}, "explanation": {"type": "string"}},
                            "required": ["term", "explanation"]}},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "relevance": {"type": "integer", "minimum": 1, "maximum": 5},
                    },
                    "required": ["id", "title_ko", "summary", "why", "logistics", "insight", "terms", "tags", "relevance"],
                },
            }
        },
        "required": ["items"],
    },
}


@dataclass
class EArticle(Article):
    orig_title: str = ""         # 원문 제목 (영어·러시아어)
    lang: str = ""               # en | ru
    logistics: str = ""          # 물류·무역 영향
    stance: str = ""             # 출처 시각 라벨
    score: int = 0               # 선별 점수 (제목 기준)

    @classmethod
    def from_dict(cls, d: dict) -> "EArticle":
        defaults = {"tags": [], "terms": [], "relevance": 0, "geo": {}, "score": 0}
        return cls(**{k: d.get(k, defaults.get(k, "")) for k in cls.__dataclass_fields__})


# ── 데이터 파일 ──────────────────────────────────────────────────
def eday_file(date: str):
    return EDIR / f"{date}.json"


def load_eday(date: str) -> dict | None:
    p = eday_file(date)
    return json.load(open(p, encoding="utf-8")) if p.exists() else None


def save_eday(date: str, payload: dict) -> None:
    EDIR.mkdir(parents=True, exist_ok=True)
    with open(eday_file(date), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def all_edays() -> list[str]:
    EDIR.mkdir(parents=True, exist_ok=True)
    return sorted((p.stem for p in EDIR.glob("????-??-??.json")), reverse=True)


def known_urls(days_back: int = 21) -> set[str]:
    urls: set[str] = set()
    for d in all_edays()[:days_back]:
        day = load_eday(d) or {}
        urls |= {a["url"] for a in day.get("articles", [])}
        urls |= {s["url"] for s in day.get("screened", [])}
    return urls


def _lang(source: str) -> str:
    return "ru" if source == "portnews" else "en"


# ── 선별 ────────────────────────────────────────────────────────
def _interests(ecfg) -> str:
    return "\n".join(f"- {i}" for i in ecfg["interests"])


def screen(client, cfg, cands: list[dict]) -> None:
    """제목·리드만으로 관련도와 한국어 제목을 매긴다 (60건씩 한 번 호출)."""
    ecfg = cfg["eurasia"]
    for i in range(0, len(cands), 60):
        batch = cands[i:i + 60]
        lines = [f"[{c['id']}] ({c['source_name']} · {c['stance']}{' · ' + c['category'] if c.get('category') else ''}) "
                 f"{c['title']}" + (f"\n    {c['description'][:220]}" if c.get("description") else "")
                 for c in batch]
        user = (f"독자 관심사:\n{_interests(ecfg)}\n\n아래 {len(batch)}건은 오늘 들어온 러시아·유라시아 기사 후보입니다. "
                f"각 기사의 한국어 제목(title_ko)과 관련도 점수(score 1~5)를 submit_screening으로 제출하세요. "
                f"같은 사건을 여러 매체가 다루면 가장 충실해 보이는 하나만 4~5점, 나머지는 2점 이하로. "
                f"모든 id를 빠짐없이.\n\n" + "\n".join(lines))
        log.info("선별 요청 %d~%d / %d", i + 1, i + len(batch), len(cands))
        try:
            res = _call_tool(client, cfg, SCREEN_TOOL, user, system=SYSTEM, max_tokens=ecfg["max_tokens"])
        except Exception as e:  # noqa: BLE001
            log.warning("선별 실패 → 최신순 대체: %s", e)
            continue
        try:
            by_id = {c["id"]: c for c in batch}
            raw_ids = res.get("ids")
            ids = (re.findall(r"[a-z]+:[0-9a-f]{10}", raw_ids) if isinstance(raw_ids, str) and not raw_ids.strip().startswith("[")
                   else as_list(raw_ids))
            titles, scores = as_list(res.get("titles_ko")), as_list(res.get("scores"))
            if not ids and res.get("items"):  # 혹시 items 형태로 답한 경우
                its = [i for i in as_list(res.get("items")) if isinstance(i, dict)]
                ids = [i.get("id") for i in its]; titles = [i.get("title_ko") for i in its]; scores = [i.get("score") for i in its]
            n_ok = 0
            for k, raw in enumerate(ids):
                c = by_id.get(str(raw).strip("[]\" "))
                if c is None:
                    continue
                n_ok += 1
                c["title_ko"] = str(titles[k]).strip() if k < len(titles) and titles[k] else ""
                try:
                    c["score"] = max(1, min(5, int(scores[k])))
                except (IndexError, TypeError, ValueError):
                    pass
            if n_ok < len(batch) // 2:
                log.warning("선별 응답 인식 %d/%d — 원본 키: %s, 앞부분: %s", n_ok, len(batch), list(res), str(res)[:300])
        except Exception as e:  # noqa: BLE001 — 응답 모양이 이상해도 최신순 대체로 계속
            log.warning("선별 응답 해석 실패: %s — %s", e, str(res)[:300])


def pick(cands: list[dict], already: int, ecfg: dict) -> tuple[list[dict], list[dict]]:
    """점수 순으로 오늘 게재분을 고른다. 이미 게재한 already건을 포함해 최대 max_daily,
    3점 이상이 모자라면 2점짜리로 min_daily까지 채운다."""
    lo, hi = int(ecfg["min_daily"]), int(ecfg["max_daily"])
    ranked = sorted(cands, key=lambda c: (-(c.get("score") or 0),
                                          -(c["published"].timestamp() if c.get("published") else 0)))
    room = max(0, hi - already)
    chosen = [c for c in ranked if (c.get("score") or 0) >= 3][:room]
    if already + len(chosen) < lo:
        for c in ranked:
            if already + len(chosen) >= min(lo, hi):
                break
            if c not in chosen and (c.get("score") or 0) >= 2:
                chosen.append(c)
    rest = [c for c in ranked if c not in chosen]
    return chosen, rest


# ── 요약 ────────────────────────────────────────────────────────
def summarize(client, cfg, arts: list[EArticle]) -> None:
    ecfg = cfg["eurasia"]
    todo = [a for a in arts if not a.summary]
    bs = int(ecfg["batch_size"])
    for i in range(0, len(todo), bs):
        batch = todo[i:i + bs]
        parts = [f"<article id=\"{a.id}\">\n출처: {a.source_name} (출처 시각: {a.stance}) / {a.category}\n"
                 f"원문 언어: {'러시아어' if a.lang == 'ru' else '영어'}\n원제: {a.orig_title}\n"
                 f"본문:\n{(a.body or a.subtitle)[: ecfg['body_chars']]}\n</article>" for a in batch]
        user = (f"독자 관심사:\n{_interests(ecfg)}\n\n아래 {len(batch)}개 기사를 한국어로 번역·요약해 submit_summaries로 제출하세요. "
                f"모든 id를 빠짐없이.\n\n" + "\n\n".join(parts))
        log.info("요약 요청 %d~%d / %d", i + 1, i + len(batch), len(todo))
        try:
            res = _call_tool(client, cfg, ARTICLE_TOOL, user, system=SYSTEM, max_tokens=ecfg["max_tokens"])
        except Exception as e:  # noqa: BLE001
            log.warning("요약 실패: %s", e)
            continue
        try:
            by_id = {a.id: a for a in batch}
            items = [i for i in as_list(res.get("items")) if isinstance(i, dict)]
            if len(items) < len(batch):
                log.warning("요약 응답 %d/%d건 — 앞부분: %s", len(items), len(batch), str(res)[:300])
            for it in items:
                a = by_id.get(str(it.get("id", "")).strip("[]"))
                if not a:
                    continue
                a.title = str(it.get("title_ko") or a.title).strip()
                a.summary = str(it.get("summary") or "").strip()
                a.why = str(it.get("why") or "").strip()
                a.logistics = str(it.get("logistics") or "").strip()
                a.insight = str(it.get("insight") or "").strip()
                terms = []
                for t in as_list(it.get("terms")):
                    if isinstance(t, dict) and t.get("term"):
                        terms.append({"term": str(t["term"]).strip(), "explanation": str(t.get("explanation", "")).strip()})
                    elif isinstance(t, str) and ":" in t:
                        k, v = t.split(":", 1)
                        terms.append({"term": k.strip(), "explanation": v.strip()})
                a.terms = terms[:2]
                a.tags = [str(t).strip() for t in as_list(it.get("tags")) if str(t).strip()][:4]
                try:
                    a.relevance = max(1, min(5, int(it.get("relevance", a.score or 3))))
                except (TypeError, ValueError):
                    a.relevance = a.score or 3
        except Exception as e:  # noqa: BLE001
            log.warning("요약 응답 해석 실패: %s — %s", e, str(res)[:300])


def make_brief(client, cfg, arts: list[EArticle]) -> dict:
    ecfg = cfg["eurasia"]
    n = int(ecfg["top_n"])
    lines = [f"[{a.id}] ({a.source_name} · {a.stance}, 관련도 {a.relevance}) {a.title}\n   요약: {a.summary}\n"
             f"   의미: {a.why}" + (f"\n   물류: {a.logistics}" if a.logistics else "") for a in arts]
    user = (f"독자 관심사:\n{_interests(ecfg)}\n\n오늘의 러시아·유라시아 기사 {len(arts)}건 요약입니다. "
            f"오늘의 헤드라인, 전체 흐름(overview — 서로 다른 기사를 연결해 정세의 맥락을, 매체 시각 차이가 있으면 짚을 것), "
            f"꼭 읽을 Top {n}(id와 이유), 앞으로 지켜볼 포인트를 submit_brief로 제출하세요. "
            f"Top은 정확히 {n}개, 서로 다른 주제로.\n\n" + "\n\n".join(lines))
    brief = _call_tool(client, cfg, BRIEF_TOOL, user, system=SYSTEM, max_tokens=ecfg["max_tokens"])
    valid = {a.id for a in arts}
    by_id = {a.id: a for a in arts}
    ids, reasons = brief.pop("top_ids", None), as_list(brief.pop("top_reasons", None))
    if isinstance(ids, str):
        ids = as_list(ids)
    raw = ([{"id": i, "reason": reasons[k] if k < len(reasons) and isinstance(reasons[k], str) else ""}
            for k, i in enumerate(ids)] if isinstance(ids, list) else (ids or brief.get("top")))
    top = norm_refs(raw, valid, n, titles={a.title: a.id for a in arts})
    brief["top_source"] = "model" if len(top) >= min(n, len(arts)) else "fallback"
    have = {t["id"] for t in top}
    for a in sorted(arts, key=lambda a: -(a.relevance or 0)):
        if len(top) >= n:
            break
        if a.id not in have:
            top.append({"id": a.id, "reason": ""}); have.add(a.id)
    for t in top:
        t["reason"] = t["reason"] or by_id[t["id"]].why
    brief["top"] = top
    brief["watch"] = [str(w) for w in as_list(brief.get("watch")) if w]
    return brief


def offline_brief(cfg, arts: list[EArticle]) -> dict:
    for a in arts:
        if not a.summary:
            first = (a.body or "").split("\n")[0]
            a.summary = (first[:220] + "…") if len(first) > 220 else first
            a.relevance = a.relevance or a.score or 3
    top = sorted(arts, key=lambda a: a.published, reverse=True)[: cfg["eurasia"]["top_n"]]
    return {"headline": f"러시아·유라시아 기사 {len(arts)}건",
            "overview": "ANTHROPIC_API_KEY가 설정되지 않아 번역·요약 없이 생성된 목록입니다.",
            "top": [{"id": a.id, "reason": "최신 기사"} for a in top], "watch": [], "offline": True}


# ── 실행 ────────────────────────────────────────────────────────
def gather(cfg, http, known: set[str]) -> list[dict]:
    ecfg = cfg["eurasia"]
    cutoff = now_local(cfg) - timedelta(hours=float(ecfg["window_hours"]))
    cands: list[dict] = []
    for key, scfg in ecfg["sources"].items():
        if not scfg.get("enabled", True):
            continue
        try:
            got = src.collect_candidates(key, scfg, cfg, http, cutoff, known)
        except Exception as e:  # noqa: BLE001 — 한 소스가 막혀도 나머지는 진행
            log.warning("%s 목록 실패: %s", key, e)
            continue
        for c in got:
            c["id"] = src.cand_id(key, c["url"])
            c["source_name"], c["stance"] = scfg["name"], scfg.get("stance", "")
            c["score"], c["title_ko"] = 0, ""
        log.info("%s: 새 후보 %d건", key, len(got))
        cands += got
    return cands


def run(date: str | None = None, force: bool = False) -> dict | None:
    cfg = load_config()
    ecfg = cfg.get("eurasia") or {}
    if not ecfg.get("enabled"):
        return None
    date = date or today_str(cfg)
    day = load_eday(date) or {"date": date, "articles": [], "screened": [], "brief": {}}
    arts = [EArticle.from_dict(a) for a in day.get("articles", [])]
    http = Http(cfg)
    if force:  # 재요약: 저장 때 지운 본문을 원문에서 다시 가져온다
        for a in arts:
            a.summary = ""
            scfg = ecfg["sources"].get(a.source, {})
            try:
                a.body = src.fetch_body({"url": a.url, "body": "", "published": None}, scfg, http)
            except Exception as e:  # noqa: BLE001
                log.warning("본문 재수집 실패 %s: %s", a.url, e)
    known = known_urls() | {a.url for a in arts}
    cands = gather(cfg, http, known)
    client = _client()

    new_arts: list[EArticle] = []
    if cands:
        if client is not None:
            screen(client, cfg, cands)
        for c in cands:  # 선별 실패·오프라인 → 점수 3으로 최신순
            c["score"] = c["score"] or 3
        chosen, rest = pick(cands, len(arts), ecfg)
        for c in chosen:
            scfg = ecfg["sources"][c["source"]]
            try:
                body = src.fetch_body(c, scfg, http)
            except Exception as e:  # noqa: BLE001
                log.warning("본문 실패 %s: %s", c["url"], e)
                body = ""
            body = body or c.get("description", "")
            if not body:
                rest.append(c)
                continue
            pub = c.get("published") or now_local(cfg)
            new_arts.append(EArticle(
                id=c["id"], source=c["source"], source_name=c["source_name"],
                title=c.get("title_ko") or c["title"], url=c["url"],
                published=pub.astimezone(now_local(cfg).tzinfo).isoformat(),
                category=c.get("category", ""), subtitle=c.get("description", "")[:300], body=body,
                orig_title=c["title"], lang=_lang(c["source"]), stance=c["stance"], score=c["score"]))
        day.setdefault("screened", [])
        for c in rest:
            day["screened"].append({"id": c["id"], "source": c["source"], "source_name": c["source_name"],
                                    "url": c["url"], "title": c["title"], "title_ko": c.get("title_ko", ""),
                                    "score": c.get("score", 0),
                                    "published": (c["published"].isoformat() if c.get("published") else "")})
        log.info("후보 %d건 → 게재 %d건 (기존 %d건), 제외 %d건", len(cands), len(new_arts), len(arts), len(rest))
    arts += new_arts

    if not arts:
        if day.get("screened"):
            save_eday(date, day)
        log.info("유라시아: 게재할 기사 없음")
        return day

    need_brief = bool(new_arts) or force or not day.get("brief", {}).get("top") \
        or day.get("brief", {}).get("top_source") != "model"
    if client is None:
        if need_brief:
            day["brief"] = offline_brief(cfg, arts)
    else:
        summarize(client, cfg, arts)
        for a in arts:  # 모델이 빠뜨린 기사
            if not a.summary:
                a.summary = (a.subtitle or a.body[:200]).replace("\n", " ")
                a.relevance = a.relevance or a.score or 3
        if need_brief:
            try:
                brief = make_brief(client, cfg, arts)
                brief["model"] = cfg["summarize"]["model"]
                day["brief"] = brief
            except Exception as e:  # noqa: BLE001
                log.warning("유라시아 브리핑 실패: %s", e)
                day["brief"] = day.get("brief") or offline_brief(cfg, arts)
    if need_brief:
        day["brief"]["summarized_at"] = now_local(cfg).isoformat()

    for a in arts:  # 본문은 저장소에 남기지 않음 (저작권·용량)
        a.body = ""
    arts.sort(key=lambda a: a.published, reverse=True)
    day["articles"] = [a.to_dict() for a in arts]
    day["generated_at"] = now_local(cfg).isoformat()
    save_eday(date, day)
    log.info("유라시아 저장: %d건 → data/eurasia/%s.json", len(arts), date)
    return day


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run()
