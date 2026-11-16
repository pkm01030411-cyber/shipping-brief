"""2단계: Claude로 기사 요약 + 관련도 점수 + 오늘의 Top N 선정.

출력 구조(JSON)를 보장하기 위해 tool-use(구조화 출력)를 사용합니다.
ANTHROPIC_API_KEY가 없으면 본문 첫 문단을 요약으로 쓰는 '오프라인 모드'로 동작합니다.
"""
from __future__ import annotations

import json
import logging
import os
import re

from .common import Article, load_config, load_day, now_local, save_day, today_str

log = logging.getLogger("brief.summarize")

SYSTEM = """당신은 해운·물류 전문지를 매일 읽고 핵심만 추려주는 업계 애널리스트입니다.
독자는 국제물류 포워더·정기선사 취업을 준비하는 대학생으로, 매일 10분 안에 업계 흐름을 파악하려 합니다.

원칙:
- 요약은 기사에 있는 사실만. 추측·과장 금지. 수치(TEU, %, 달러, 지수)는 그대로 살릴 것.
- 한국어 '~다' 체의 간결한 문장. 기사 문장을 그대로 베끼지 말고 재구성할 것.
- why(한 줄 의미)는 "이 뉴스가 업계/취준생 관점에서 왜 중요한가"를 1문장으로. 뻔한 말 대신 맥락을 줄 것.
- tags는 2~4개, 짧은 명사 (예: HMM, SCFI, 북미항로, 관세, 파업, 항공화물).
- relevance는 독자 관심사와의 관련도 1~5. 단, 관심사에서 멀어도 업계 전체에 큰 뉴스면 4 이상.
- 표/지수 나열 기사([표] …)는 relevance 2 이하, 요약은 핵심 수치 1~2개만.
- 인사·동정·수상·행사 소식은 relevance 1~2.

용어 해설(terms):
- 기사에 나온 업계 용어·약어·제도·지표·기업 유형 중 취준생이 정확히 설명 못 할 법한 것을 1~3개. 각각 한 문장(40자 내외)으로 실무 맥락까지.
  기사에 그런 용어가 정말 하나도 없을 때만 빈 배열. 예: 3PL, 포워더, 환적, 선복, 얼라이언스, BAF, D/O, 복합운송, 풀필먼트, 항만배후단지, 터미널 운영사(TOC)도 대상.
  예) "PSS(성수기 부가료): 선사가 성수기 수요 증가를 이유로 기본 운임에 얹는 추가 요금. 화주는 보통 2~4주 전 공지를 받는다."
- TEU, 컨테이너처럼 누구나 아는 말은 넣지 말 것. 기사에 없는 용어도 넣지 말 것.
- 같은 날 다른 기사에서 이미 나왔을 법한 기본 용어는 가장 관련 깊은 기사 하나에만.

인사이트(insight):
- why가 "왜 중요한가"라면 insight는 "그래서 어떻게 읽어야 하나" — 1~2문장.
- 기사 밖의 맥락과 연결할 것: 다른 선사·항로에 미칠 파급, 운임·선복·물동량 사이의 인과, 과거 유사 사례, 화주·포워더·선사 각자의 손익.
- 추측은 "~가능성이 있다", "~로 해석할 수 있다"로 표시. 기사에 없는 수치를 지어내지 말 것.
- 면접에서 "이 뉴스를 어떻게 보느냐"고 물었을 때 답할 수 있는 수준의 한 줄 관점이면 충분하다."""

ARTICLE_TOOL = {
    "name": "submit_summaries",
    "description": "각 기사의 요약 결과를 제출한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "summary": {"type": "string", "description": "2~3문장 핵심 요약"},
                        "why": {"type": "string", "description": "왜 중요한지 1문장"},
                        "insight": {"type": "string", "description": "어떻게 읽어야 하는지 — 맥락·파급·해석 1~2문장"},
                        "terms": {
                            "type": "array",
                            "description": "업계 용어 해설 0~3개",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "term": {"type": "string", "description": "용어 (약어면 풀네임 병기: 'PSS(성수기 부가료)')"},
                                    "explanation": {"type": "string", "description": "한 문장 해설, 실무 맥락 포함"},
                                },
                                "required": ["term", "explanation"],
                            },
                        },
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "relevance": {"type": "integer", "minimum": 1, "maximum": 5},
                    },
                    "required": ["id", "summary", "why", "insight", "terms", "tags", "relevance"],
                },
            }
        },
        "required": ["items"],
    },
}

BRIEF_TOOL = {
    "name": "submit_brief",
    "description": "오늘의 브리핑(헤드라인, Top N, 흐름 한 줄)을 제출한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string", "description": "오늘 하루를 요약하는 한 줄 제목 (30자 내외)"},
            "overview": {"type": "string", "description": "오늘 뉴스 전체의 흐름을 3~4문장으로. 서로 다른 기사를 연결해 맥락을 줄 것."},
            "top": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "reason": {"type": "string", "description": "오늘 꼭 읽어야 하는 이유 1문장"},
                    },
                    "required": ["id", "reason"],
                },
            },
            "watch": {"type": "array", "items": {"type": "string"},
                      "description": "앞으로 지켜볼 포인트 2~3개 (각 1문장)"},
        },
        "required": ["headline", "overview", "top", "watch"],
    },
}


def _client():
    try:
        import anthropic
    except ImportError:
        return None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return anthropic.Anthropic()


def _extract_json(text: str) -> dict | None:
    """텍스트 응답에서 JSON 객체를 최대한 건져낸다 (```json ... ``` 또는 첫 { ~ 마지막 })."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    cand = m.group(1) if m else None
    if not cand:
        s, e = text.find("{"), text.rfind("}")
        cand = text[s:e + 1] if s != -1 and e > s else None
    if not cand:
        return None
    try:
        return json.loads(cand)
    except json.JSONDecodeError:
        return None


def _call_tool(client, cfg, tool: dict, user_text: str) -> dict:
    """구조화 출력. 일부 모델은 tool_choice 강제를 지원하지 않아 auto + 지시문으로 유도하고,
    그래도 텍스트로 답하면 JSON을 파싱한다."""
    scfg = cfg["summarize"]
    user_text += (f"\n\n반드시 `{tool['name']}` 도구를 호출해 결과를 제출하세요. "
                  f"도구를 쓸 수 없다면 동일한 스키마의 JSON 객체만 ```json 블록으로 출력하세요.")
    resp = client.messages.create(
        model=scfg["model"],
        max_tokens=scfg["max_tokens"],
        system=SYSTEM,
        tools=[tool],
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": user_text}],
    )
    texts = []
    for block in resp.content:
        if block.type == "tool_use" and block.name == tool["name"]:
            return block.input
        if block.type == "text":
            texts.append(block.text)
    parsed = _extract_json("\n".join(texts))
    if parsed is not None:
        log.info("도구 호출 대신 텍스트 JSON 응답을 파싱함")
        return parsed
    raise RuntimeError("모델이 구조화 출력을 반환하지 않음: " + "\n".join(texts)[:300])


def norm_refs(items, valid: set[str], limit: int | None = None, reason_key: str = "reason",
              titles: dict[str, str] | None = None) -> list[dict]:
    """모델이 [{'id','reason'}] 대신 ['id', ...], {'id': 'reason'}, 대괄호 붙은 id, 제목 등으로 줘도 받아준다."""
    out, seen = [], set()
    titles = {k.strip().lower(): v for k, v in (titles or {}).items()}  # title → id
    if isinstance(items, dict):
        items = [{"id": k, reason_key: v} for k, v in items.items()]
    if isinstance(items, str):
        # 도구 호출 포맷이 문자열로 새어 들어온 경우: <parameter name="id">ksg:1</parameter> ... 를 긁어낸다
        params = re.findall(r'<parameter name="(\w+)">\s*(.*?)\s*(?:</parameter>|(?=<parameter)|(?=</item>)|$)', items, re.S)
        parsed, cur = [], {}
        for k, v in params:
            if k == "id" and cur:
                parsed.append(cur); cur = {}
            cur[k] = v.strip()
        if cur:
            parsed.append(cur)
        if not parsed:  # 그냥 id 나열
            parsed = [{"id": m} for m in re.findall(r"[a-z]+:\d+", items)]
        items = parsed
    for t in items or []:
        if isinstance(t, str):
            t = {"id": t, reason_key: ""}
        if not isinstance(t, dict):
            continue
        raw = str(t.get("id") or t.get("article_id") or t.get("title") or "").strip().strip("[]")
        i = raw if raw in valid else None
        if i is None:  # 'ksg:148502' 없이 숫자만 왔거나 제목을 준 경우
            cands = [v for v in valid if v.endswith(":" + raw)]
            i = cands[0] if len(cands) == 1 else titles.get(raw.lower())
        if i and i not in seen:
            seen.add(i)
            out.append({"id": i, reason_key: str(t.get(reason_key, "") or "").strip()})
    if not out and items:
        log.warning("참조 정규화 실패 — 원본: %s", str(items)[:300])
    return out[:limit] if limit else out


def _interests_text(cfg) -> str:
    return "\n".join(f"- {i}" for i in cfg["summarize"]["interests"])


def summarize_articles(client, cfg, articles: list[Article]) -> None:
    scfg = cfg["summarize"]
    todo = [a for a in articles if not a.summary]
    bs = scfg["batch_size"]
    for i in range(0, len(todo), bs):
        batch = todo[i:i + bs]
        parts = []
        for a in batch:
            body = a.body[: scfg["body_chars"]]
            parts.append(f"<article id=\"{a.id}\">\n출처: {a.source_name} / {a.category}\n제목: {a.title}\n"
                         f"{('부제: ' + a.subtitle) if a.subtitle else ''}\n본문:\n{body}\n</article>")
        user = (f"독자 관심사:\n{_interests_text(cfg)}\n\n아래 {len(batch)}개 기사를 각각 요약하고 submit_summaries로 제출하세요. "
                f"모든 id를 빠짐없이 포함할 것.\n\n" + "\n\n".join(parts))
        log.info("요약 요청 %d~%d / %d", i + 1, i + len(batch), len(todo))
        result = _call_tool(client, cfg, ARTICLE_TOOL, user)
        by_id = {a.id: a for a in batch}
        for item in result.get("items", []):
            a = by_id.get(item.get("id"))
            if not a:
                continue
            a.summary = item.get("summary", "").strip()
            a.why = item.get("why", "").strip()
            a.insight = (item.get("insight") or "").strip()
            terms = []
            for t in (item.get("terms") or []):
                if isinstance(t, dict) and t.get("term"):
                    terms.append({"term": str(t["term"]).strip(), "explanation": str(t.get("explanation", "")).strip()})
                elif isinstance(t, str) and ":" in t:
                    k, v = t.split(":", 1)
                    terms.append({"term": k.strip(), "explanation": v.strip()})
            a.terms = terms[:3]
            a.tags = [t.strip() for t in item.get("tags", []) if t.strip()][:4]
            a.relevance = max(1, min(5, int(item.get("relevance", 3))))
        for a in batch:
            if not a.summary:  # 모델이 빠뜨린 경우 대비
                a.summary = a.body[:200].replace("\n", " ") + "…"
                a.relevance = a.relevance or 3


def make_brief(client, cfg, articles: list[Article]) -> dict:
    scfg = cfg["summarize"]
    lines = []
    for a in articles:
        lines.append(f"[{a.id}] ({a.source_name}/{a.category}, 관련도 {a.relevance}) {a.title}\n"
                     f"   요약: {a.summary}\n   의미: {a.why}")
    user = (f"독자 관심사:\n{_interests_text(cfg)}\n\n오늘 수집된 기사 {len(articles)}건의 요약입니다. "
            f"오늘의 헤드라인, 전체 흐름(overview), 꼭 읽어야 할 Top {scfg['top_n']}(id와 이유), "
            f"앞으로 지켜볼 포인트를 submit_brief로 제출하세요. Top은 정확히 {scfg['top_n']}개, "
            f"서로 다른 주제로 고를 것.\n\n" + "\n\n".join(lines))
    brief = _call_tool(client, cfg, BRIEF_TOOL, user)
    valid = {a.id for a in articles}
    by_id = {a.id: a for a in articles}
    raw_top = brief.get("top")
    top = norm_refs(raw_top, valid, scfg["top_n"], titles={a.title: a.id for a in articles})
    if len(top) < scfg["top_n"]:
        log.warning("Top %d/%d만 인식됨 — 원본: %s", len(top), scfg["top_n"], str(raw_top)[:400].replace("\n", " "))
        have = {t["id"] for t in top}
        for a in sorted(articles, key=lambda a: -a.relevance):  # 모자라면 관련도 상위로 채움
            if len(top) >= scfg["top_n"]:
                break
            if a.id not in have:
                top.append({"id": a.id, "reason": ""}); have.add(a.id)
    for t in top:  # 이유가 비면 기사의 '의미'로 대체
        if not t["reason"]:
            t["reason"] = by_id[t["id"]].why
    brief["top"] = top
    brief["watch"] = [str(w) for w in (brief.get("watch") or []) if w]
    return brief


def offline_brief(cfg, articles: list[Article]) -> dict:
    """API 키 없이 실행할 때의 대체 브리핑."""
    for a in articles:
        if not a.summary:
            first = a.body.split("\n")[0]
            a.summary = (first[:220] + "…") if len(first) > 220 else first
            a.why = ""
            a.relevance = 3
    top = sorted(articles, key=lambda a: a.published, reverse=True)[: cfg["summarize"]["top_n"]]
    return {
        "headline": f"오늘의 해운물류 뉴스 {len(articles)}건",
        "overview": "ANTHROPIC_API_KEY가 설정되지 않아 AI 요약 없이 생성된 브리핑입니다.",
        "top": [{"id": a.id, "reason": "최신 기사"} for a in top],
        "watch": [],
        "offline": True,
    }


def run(date: str | None = None, force: bool = False) -> dict:
    cfg = load_config()
    date = date or today_str(cfg)
    day = load_day(date)
    if not day or not day.get("articles"):
        log.warning("요약할 기사가 없습니다: %s", date)
        return day or {}
    articles = [Article.from_dict(a) for a in day["articles"]]
    if force:
        for a in articles:
            a.summary = ""
        if any(not a.body for a in articles):
            from .collect import refetch_bodies  # 저장 시 지운 본문을 원문에서 다시 가져옴
            refetch_bodies(articles)

    client = _client()
    if client is None:
        log.warning("ANTHROPIC_API_KEY 없음 → 오프라인 모드")
        brief = offline_brief(cfg, articles)
    else:
        summarize_articles(client, cfg, articles)
        brief = make_brief(client, cfg, articles)
        brief["model"] = cfg["summarize"]["model"]

    brief["summarized_at"] = now_local(cfg).isoformat()
    if not cfg["summarize"].get("keep_body", False):
        for a in articles:  # 요약이 끝난 본문은 저장소에 남기지 않음 (저작권·용량)
            a.body = ""
    day["articles"] = [a.to_dict() for a in articles]
    day["brief"] = brief
    save_day(date, day)
    log.info("요약 완료: %d건, Top %d", len(articles), len(brief.get("top", [])))
    return day


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run(force="--force" in sys.argv)
