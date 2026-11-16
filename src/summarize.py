"""2단계: Claude로 기사 요약 + 관련도 점수 + 오늘의 Top N 선정.

출력 구조(JSON)를 보장하기 위해 tool-use(구조화 출력)를 사용합니다.
ANTHROPIC_API_KEY가 없으면 본문 첫 문단을 요약으로 쓰는 '오프라인 모드'로 동작합니다.
"""
from __future__ import annotations

import logging
import os

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
- 인사·동정·수상·행사 소식은 relevance 1~2."""

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
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "relevance": {"type": "integer", "minimum": 1, "maximum": 5},
                    },
                    "required": ["id", "summary", "why", "tags", "relevance"],
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


def _call_tool(client, cfg, tool: dict, user_text: str) -> dict:
    scfg = cfg["summarize"]
    resp = client.messages.create(
        model=scfg["model"],
        max_tokens=scfg["max_tokens"],
        system=SYSTEM,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": user_text}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == tool["name"]:
            return block.input
    raise RuntimeError("모델이 구조화 출력을 반환하지 않음")


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
    brief["top"] = [t for t in brief.get("top", []) if t.get("id") in valid][: scfg["top_n"]]
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
