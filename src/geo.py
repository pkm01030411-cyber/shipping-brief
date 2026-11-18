"""국제정세(geo) 태깅: 어휘, 방어적 파싱, 백필, 집계.

기사마다 다음을 붙인다 (Article.geo):
  {"regions": [...], "countries": ["US", ...], "chokepoints": [...], "drivers": [...],
   "impact": -2~2, "note": "..."}
Article.geo == {} 는 '아직 분석 안 함', 키가 있으면 분석 완료(전부 비어 있을 수 있음).

Sonnet 5.5가 중첩 객체에서 도구 호출 형식을 깨뜨린 적이 있어, 모델에게는 평평한 필드
(geo_regions, geo_countries, ... 문자열 배열과 정수)로 받는다.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

log = logging.getLogger("brief.geo")

# ── 어휘 ────────────────────────────────────────────────────────
REGIONS = ["동아시아", "동남아", "남아시아", "중동", "유럽", "북미", "중남미", "아프리카", "러시아·CIS", "북극", "오세아니아"]
CHOKEPOINTS = ["홍해·바브엘만데브", "수에즈", "파나마", "호르무즈", "말라카", "흑해·보스포루스", "북극항로", "대만해협"]
DRIVERS = ["관세·무역정책", "분쟁·안보", "제재", "노사·파업", "기후·운하수위", "에너지·유가", "공급망 재편", "환경규제"]

# 모델이 조금 다르게 써도 맞춰주는 별칭 (소문자, 공백·가운뎃점 제거 후 비교)
_ALIASES = {
    "홍해": "홍해·바브엘만데브", "바브엘만데브": "홍해·바브엘만데브", "redsea": "홍해·바브엘만데브",
    "수에즈운하": "수에즈", "suez": "수에즈", "파나마운하": "파나마", "panama": "파나마",
    "호르무즈해협": "호르무즈", "말라카해협": "말라카", "싱가포르해협": "말라카",
    "흑해": "흑해·보스포루스", "보스포루스": "흑해·보스포루스", "nsr": "북극항로", "북방항로": "북극항로",
    "대만": "대만해협",
    "관세": "관세·무역정책", "무역정책": "관세·무역정책", "통상": "관세·무역정책",
    "분쟁": "분쟁·안보", "전쟁": "분쟁·안보", "안보": "분쟁·안보", "지정학": "분쟁·안보",
    "파업": "노사·파업", "노사": "노사·파업", "노동": "노사·파업",
    "기후": "기후·운하수위", "가뭄": "기후·운하수위", "운하수위": "기후·운하수위",
    "유가": "에너지·유가", "에너지": "에너지·유가", "연료": "에너지·유가",
    "공급망": "공급망 재편", "리쇼어링": "공급망 재편", "니어쇼어링": "공급망 재편",
    "환경": "환경규제", "탄소": "환경규제", "imo": "환경규제", "ets": "환경규제",
    "동북아": "동아시아", "아시아": "동아시아", "동남아시아": "동남아", "아세안": "동남아",
    "인도": "남아시아", "미국": "북미", "북아메리카": "북미", "남미": "중남미", "라틴아메리카": "중남미",
    "러시아": "러시아·CIS", "cis": "러시아·CIS", "중앙아시아": "러시아·CIS", "eu": "유럽",
    "호주": "오세아니아", "대양주": "오세아니아", "태평양도서국": "오세아니아",
}

COUNTRY_KO = {
    "KR": "한국", "US": "미국", "CN": "중국", "JP": "일본", "TW": "대만", "HK": "홍콩", "SG": "싱가포르",
    "VN": "베트남", "TH": "태국", "MY": "말레이시아", "ID": "인도네시아", "PH": "필리핀", "IN": "인도",
    "BD": "방글라데시", "LK": "스리랑카", "PK": "파키스탄", "AE": "UAE", "SA": "사우디", "IR": "이란",
    "IL": "이스라엘", "YE": "예멘", "EG": "이집트", "TR": "튀르키예", "QA": "카타르", "OM": "오만",
    "DE": "독일", "NL": "네덜란드", "BE": "벨기에", "FR": "프랑스", "GB": "영국", "IT": "이탈리아",
    "ES": "스페인", "PT": "포르투갈", "GR": "그리스", "DK": "덴마크", "NO": "노르웨이", "SE": "스웨덴",
    "FI": "핀란드", "PL": "폴란드", "UA": "우크라이나", "RU": "러시아", "KZ": "카자흐스탄", "UZ": "우즈베키스탄",
    "MN": "몽골", "CA": "캐나다", "MX": "멕시코", "PA": "파나마", "BR": "브라질", "CL": "칠레", "PE": "페루",
    "CO": "콜롬비아", "AR": "아르헨티나", "ZA": "남아공", "KE": "케냐", "TZ": "탄자니아", "NG": "나이지리아",
    "MA": "모로코", "DJ": "지부티", "AU": "호주", "NZ": "뉴질랜드", "EE": "에스토니아", "CH": "스위스",
    "KP": "북한", "MM": "미얀마", "KH": "캄보디아",
}
_KO_TO_CODE = {v: k for k, v in COUNTRY_KO.items()}

GEO_FIELDS = ("regions", "countries", "chokepoints", "drivers")


def slug(name: str) -> str:
    """앵커용: '홍해·바브엘만데브' → 'cp-홍해-바브엘만데브' 같은 안정적 id 조각."""
    return re.sub(r"[\s·/,.()]+", "-", name).strip("-").lower()


def _key(s: str) -> str:
    return re.sub(r"[\s·\-_/]+", "", str(s)).lower()


def _match(value: str, vocab: list[str]) -> str | None:
    k = _key(value)
    if not k:
        return None
    for v in vocab:
        if _key(v) == k:
            return v
    if k in _ALIASES and _ALIASES[k] in vocab:
        return _ALIASES[k]
    for v in vocab:  # 부분 일치 ('홍해 위기' → 홍해·바브엘만데브)
        if _key(v) in k or k in _key(v):
            return v
    for a, v in _ALIASES.items():
        if a in k and v in vocab:
            return v
    return None


def _as_list(x) -> list[str]:
    """['a','b'] / 'a, b' / '["a","b"]' / None → ['a','b']"""
    if x is None:
        return []
    if isinstance(x, (list, tuple)):
        out = []
        for i in x:
            out.extend(_as_list(i) if isinstance(i, (list, tuple)) else [str(i)])
        return [s.strip().strip('"\'') for s in out if str(s).strip()]
    s = str(x).strip().strip("[]")
    return [p.strip().strip('"\'') for p in re.split(r"[,\n/|]", s) if p.strip().strip('"\'')]


def norm_country(c: str) -> str | None:
    c = str(c).strip()
    if re.fullmatch(r"[A-Za-z]{2}", c):
        c = c.upper()
        return "GB" if c == "UK" else c
    return _KO_TO_CODE.get(c)


def norm_geo(item: dict) -> dict:
    """모델 응답 한 건(평평한 geo_* 필드 또는 geo 객체) → 표준 geo dict."""
    src = item.get("geo") if isinstance(item.get("geo"), dict) else {}
    get = lambda k: item.get(f"geo_{k}", src.get(k))  # noqa: E731

    def uniq(seq, n):
        out = []
        for s in seq:
            if s and s not in out:
                out.append(s)
        return out[:n]

    try:
        impact = int(round(float(get("impact") or 0)))
    except (TypeError, ValueError):
        impact = 0
    return {
        "regions": uniq((_match(v, REGIONS) for v in _as_list(get("regions"))), 3),
        "countries": uniq((norm_country(v) for v in _as_list(get("countries"))), 4),
        "chokepoints": uniq((_match(v, CHOKEPOINTS) for v in _as_list(get("chokepoints"))), 2),
        "drivers": uniq((_match(v, DRIVERS) for v in _as_list(get("drivers"))), 2),
        "impact": max(-2, min(2, impact)),
        "note": str(get("note") or "").strip(),
    }


def is_geo(g: dict | None) -> bool:
    """국제정세와 관련 있는 기사인가 (분석 완료 + 무언가 태깅됨)."""
    return bool(g) and any(g.get(k) for k in GEO_FIELDS)


# ── 프롬프트 · 스키마 조각 ────────────────────────────────────────
PROMPT = f"""
국제정세 태깅(geo_*):
- 이 기사가 해운·물류에 영향을 주는 국제정세와 연결될 때만 채운다. 인사·수상·국내 행사·단순 실적은 전부 빈 배열, impact 0.
- geo_regions: 다음 중 0~3개 {REGIONS}
- geo_countries: 기사에 실제로 등장하는 나라의 ISO 3166-1 alpha-2 코드 0~4개 (예: "US","CN","RU"). 한국(KR)은 다른 나라와 함께 핵심일 때만.
- geo_chokepoints: 다음 중 기사가 직접 다루는 것 0~2개 {CHOKEPOINTS}
- geo_drivers: 다음 중 0~2개 {DRIVERS}
- geo_impact: 해운·물류 흐름에 대한 방향, -2(큰 차질)~0(중립)~+2(큰 개선) 정수. 기사 내용만 근거로.
  예) 항만 파업 확산 -1~-2, 운하 통항 정상화 +1, 관세 유예 +1, 신규 제재로 항로 우회 -2.
- geo_note: 이 기사가 국제정세와 어떻게 연결되는지 한 문장. 관련 없으면 빈 문자열.
- 기사에 없는 국가·사건을 추론해 넣지 말 것.
- geo_* 필드는 모두 평평한 문자열 배열 또는 정수로만 쓴다(객체 금지)."""

SCHEMA_PROPS = {
    "geo_regions": {"type": "array", "items": {"type": "string", "enum": REGIONS}},
    "geo_countries": {"type": "array", "items": {"type": "string"}, "description": "ISO alpha-2 코드"},
    "geo_chokepoints": {"type": "array", "items": {"type": "string", "enum": CHOKEPOINTS}},
    "geo_drivers": {"type": "array", "items": {"type": "string", "enum": DRIVERS}},
    "geo_impact": {"type": "integer", "minimum": -2, "maximum": 2},
    "geo_note": {"type": "string"},
}

GEO_TOOL = {
    "name": "submit_geo",
    "description": "각 기사의 국제정세 태깅을 제출한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "object",
                          "properties": {"id": {"type": "string"}, **SCHEMA_PROPS},
                          "required": ["id", *SCHEMA_PROPS.keys()]},
            }
        },
        "required": ["items"],
    },
}


# ── 백필: 요약은 그대로 두고 geo만 추출 ─────────────────────────────
def backfill(dates: list[str] | None = None, force: bool = False) -> int:
    from .collect import refetch_bodies
    from .common import Article, all_days, load_config, load_day, save_day
    from .summarize import SYSTEM, _call_tool, _client

    cfg = load_config()
    client = _client()
    if client is None:
        log.warning("ANTHROPIC_API_KEY 없음 → geo 백필 건너뜀")
        return 0
    scfg = cfg["summarize"]
    total = 0
    for d in dates or all_days():
        day = load_day(d)
        if not day or not day.get("articles"):
            continue
        arts = [Article.from_dict(a) for a in day["articles"]]
        todo = [a for a in arts if force or not a.geo]
        if not todo:
            continue
        had_body = {a.id for a in todo if a.body}
        refetch_bodies(todo)
        bs = scfg["batch_size"]
        for i in range(0, len(todo), bs):
            batch = todo[i:i + bs]
            parts = [f"<article id=\"{a.id}\">\n제목: {a.title}\n요약: {a.summary}\n"
                     f"본문:\n{(a.body or '')[: scfg['body_chars']]}\n</article>" for a in batch]
            user = (f"아래 {len(batch)}개 기사의 국제정세 태깅만 submit_geo로 제출하세요. 모든 id 포함.\n{PROMPT}\n\n"
                    + "\n\n".join(parts))
            result = _call_tool(client, cfg, GEO_TOOL, user)
            by_id = {a.id: a for a in batch}
            for item in result.get("items", []) if isinstance(result.get("items"), list) else []:
                if isinstance(item, dict) and item.get("id") in by_id:
                    by_id[item["id"]].geo = norm_geo(item)
            for a in batch:
                if not a.geo:  # 모델이 빠뜨린 기사도 '분석 완료(빈 값)'로 표시해 재시도 루프 방지
                    a.geo = norm_geo({})
            total += len(batch)
        if not cfg["summarize"].get("keep_body", False):
            for a in todo:
                if a.id not in had_body:
                    a.body = ""
        day["articles"] = [a.to_dict() for a in arts]
        save_day(d, day)
        log.info("geo 백필 %s: %d건", d, len(todo))
    return total


# ── 집계 ────────────────────────────────────────────────────────
def _pub_date(a: dict) -> date:
    return datetime.fromisoformat(a["published"]).date()


def _avg(xs: list[int]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


def impact_class(v: float | None) -> str:
    """평균 impact → 색 클래스. 색만으로 의미를 전달하지 않도록 템플릿에서 숫자·화살표를 같이 쓴다."""
    if v is None:
        return "imp-none"
    if v <= -1.25:
        return "imp-n2"
    if v <= -0.4:
        return "imp-n1"
    if v < 0.4:
        return "imp-0"
    if v < 1.25:
        return "imp-p1"
    return "imp-p2"


def fmt_impact(v: float | None) -> str:
    if v is None:
        return "–"
    if abs(v) < 0.05:
        return "0.0"
    s = f"{v:+.1f}"
    return s.replace("-", "−")


def trend_arrow(cur: int, prev: int) -> tuple[str, str]:
    """기사 수 변화 화살표와 설명."""
    if cur == prev:
        return "→", "직전 기간과 같음"
    d = cur - prev
    return ("↑" if d > 0 else "↓"), f"직전 기간 대비 {d:+d}건".replace("-", "−")


def aggregate(articles: list[dict], today: date, weekly: dict | None = None) -> dict:
    """전체 기사(published 포함) → 대시보드 데이터. articles는 중복 없는 전체 기사 목록."""
    analyzed = [a for a in articles if a.get("geo")]
    geo_arts = [a for a in analyzed if is_geo(a["geo"])]

    def window(days: int, offset: int = 0) -> list[dict]:
        end = today - timedelta(days=offset)
        start = end - timedelta(days=days - 1)
        return [a for a in geo_arts if start <= _pub_date(a) <= end]

    def brief(a: dict) -> dict:
        return {"id": a["id"], "title": a["title"], "url": a["url"], "source": a.get("source_name", ""),
                "date": a["published"][:10], "impact": a["geo"].get("impact", 0), "note": a["geo"].get("note", ""),
                "chokepoints": a["geo"].get("chokepoints", []), "countries": a["geo"].get("countries", [])}

    first_day = min((_pub_date(a) for a in analyzed), default=today)

    def compare(cur_n: int, prev_n: int, p: int) -> tuple[str, str]:
        # 직전 기간 전체가 데이터 수집 이전이면 비교하지 않는다 (가짜 '증가' 방지)
        prev_start = today - timedelta(days=2 * p - 1)
        if first_day > prev_start:
            return "–", "비교할 직전 기간 데이터 없음"
        return trend_arrow(cur_n, prev_n)

    periods = {}
    for p in (7, 30):
        cur, prev = window(p), window(p, p)

        def by(field: str, vocab: list[str] | None, rows_cur=cur, rows_prev=prev) -> list[dict]:
            keys = vocab or sorted({k for a in rows_cur for k in a["geo"].get(field, [])})
            out = []
            for k in keys:
                hit = [a for a in rows_cur if k in a["geo"].get(field, [])]
                hit_prev = [a for a in rows_prev if k in a["geo"].get(field, [])]
                avg = _avg([a["geo"].get("impact", 0) for a in hit])
                arrow, arrow_label = compare(len(hit), len(hit_prev), p)
                out.append({
                    "name": k, "slug": slug(k), "count": len(hit), "prev": len(hit_prev),
                    "avg": avg, "avg_label": fmt_impact(avg), "cls": impact_class(avg),
                    "arrow": arrow, "arrow_label": arrow_label,
                    "articles": [brief(a) for a in sorted(hit, key=lambda a: a["published"], reverse=True)],
                })
            return out

        cps = by("chokepoints", CHOKEPOINTS)
        regions = by("regions", REGIONS)
        drivers = by("drivers", DRIVERS)
        countries = sorted(by("countries", None), key=lambda r: (-r["count"], r["name"]))[:10]
        for c in countries:
            c["label"] = COUNTRY_KO.get(c["name"], c["name"])
        cmax = max((c["count"] for c in countries), default=1) or 1
        for c in countries:
            c["bar"] = round(c["count"] / cmax, 3)
        periods[p] = {
            "count": len(cur), "prev_count": len(prev),
            "chokepoints": cps, "regions": regions, "drivers": drivers, "countries": countries,
            "low_sample": len(cur) <= 3,
        }

    # 요약 타일 (최근 7일 고정, '이번 주')
    w = periods[7]
    top_cp = max(w["chokepoints"], key=lambda r: (r["count"], -(r["avg"] or 0)), default=None)
    worst = min((r for r in w["regions"] if r["count"] >= 2), key=lambda r: r["avg"], default=None)
    top_drv = max(w["drivers"], key=lambda r: r["count"], default=None)
    tiles = {
        "chokepoint": top_cp if top_cp and top_cp["count"] else None,
        "region": worst,
        "driver": top_drv if top_drv and top_drv["count"] else None,
        "articles": {"count": w["count"], "prev": w["prev_count"],
                     "analyzed": len([a for a in analyzed if _pub_date(a) > today - timedelta(days=7)]),
                     "arrow": compare(w["count"], w["prev_count"], 7)},
    }

    # 지역 × 주 히트맵 (최근 8주, ISO week)
    weeks = []
    monday = today - timedelta(days=today.weekday())
    for i in range(7, -1, -1):
        s = monday - timedelta(weeks=i)
        y, n, _ = s.isocalendar()
        weeks.append({"key": f"{y}-W{n:02d}", "label": f"{s.month}/{s.day}", "start": s, "end": s + timedelta(days=6)})
    heat = []
    for r in REGIONS:
        cells = []
        for wk in weeks:
            hit = [a for a in geo_arts if r in a["geo"].get("regions", []) and wk["start"] <= _pub_date(a) <= wk["end"]]
            avg = _avg([a["geo"].get("impact", 0) for a in hit])
            cells.append({"count": len(hit), "avg": avg, "avg_label": fmt_impact(avg), "cls": impact_class(avg)})
        heat.append({"name": r, "slug": slug(r), "cells": cells, "total": sum(c["count"] for c in cells)})
    hmax = max((c["count"] for row in heat for c in row["cells"]), default=0)

    # 동인별 시계열 (최근 60일, 7일 이동평균) — 상위 5개 동인만 선으로
    span = [today - timedelta(days=i) for i in range(59, -1, -1)]
    daily = {d: Counter() for d in span}
    for a in geo_arts:
        d = _pub_date(a)
        if d in daily:
            for drv in a["geo"].get("drivers", []):
                daily[d][drv] += 1
    totals = Counter()
    for c in daily.values():
        totals.update(c)
    top_drivers = [k for k, _ in totals.most_common(5)]
    days_of_data = (today - first_day).days + 1
    series = []
    for drv in top_drivers:
        raw = [daily[d][drv] for d in span]
        ma = [round(sum(raw[max(0, i - 6): i + 1]) / 7, 3) for i in range(len(raw))]
        series.append({"name": drv, "slug": slug(drv), "total": totals[drv], "raw": raw, "ma": ma})

    # 이번 주 한 줄
    line = None
    if weekly and weekly.get("review", {}).get("headline"):
        try:
            end = date.fromisoformat(weekly["end"])
            if (today - end).days <= 8:
                line = {"text": weekly["review"]["headline"], "source": f"주간 리뷰 {weekly.get('week', '')}"}
        except (KeyError, ValueError):
            pass
    if line is None and w["count"]:
        parts = [f"최근 7일 국제정세 관련 기사 {w['count']}건"]
        if tiles["chokepoint"]:
            c = tiles["chokepoint"]
            parts.append(f"요충지는 {c['name']}({c['count']}건, 평균 {c['avg_label']})")
        if tiles["driver"]:
            parts.append(f"동인은 {tiles['driver']['name']}이 가장 많음")
        line = {"text": " · ".join(parts), "source": "집계"}

    return {
        "today": today.isoformat(),
        "analyzed": len(analyzed), "geo_count": len(geo_arts), "total": len(articles),
        "pending": len(articles) - len(analyzed),
        "periods": periods, "tiles": tiles, "line": line,
        "heat": {"weeks": [{"key": w_["key"], "label": w_["label"]} for w_ in weeks], "rows": heat, "max": hmax},
        "trend": {"series": series, "days": [d.isoformat() for d in span], "days_of_data": days_of_data},
    }


# ── SVG: 동인 추이 꺾은선 ─────────────────────────────────────────
LINE_COLORS = ["var(--navy)", "var(--gold)", "#7a8ca3", "#a27fb8", "#5f9e8f"]


def trend_svg(trend: dict, width: int = 720, height: int = 220) -> str:
    """7일 이동평균 꺾은선. 범례 대신 선 끝에 직접 라벨."""
    series = trend["series"]
    if not series:
        return ""
    pad_l, pad_r, pad_t, pad_b = 34, 118, 12, 26
    n = len(trend["days"])
    ymax = max(max(s["ma"]) for s in series) or 1
    nice = [0.5, 1, 2, 3, 5, 10, 20]
    ymax = next((v for v in nice if v >= ymax), ymax)
    X = lambda i: pad_l + (width - pad_l - pad_r) * i / (n - 1)  # noqa: E731
    Y = lambda v: pad_t + (height - pad_t - pad_b) * (1 - v / ymax)  # noqa: E731
    out = [f'<svg viewBox="0 0 {width} {height}" class="trend-svg" role="img" aria-labelledby="trend-title trend-desc">']
    out.append('<title id="trend-title">동인별 기사 수 추이 (7일 이동평균, 최근 60일)</title>')
    desc = ", ".join(f"{s['name']} 60일 합계 {s['total']}건" for s in series)
    out.append(f'<desc id="trend-desc">{desc}</desc>')
    for t in (0, ymax / 2, ymax):  # 가로 눈금
        y = Y(t)
        out.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{pad_l - 6}" y="{y + 4:.1f}" class="axis" text-anchor="end">{t:g}</text>')
    for i in (0, n // 2, n - 1):  # 날짜 눈금
        d = trend["days"][i]
        out.append(f'<text x="{X(i):.1f}" y="{height - 6}" class="axis" text-anchor="middle">{int(d[5:7])}/{int(d[8:])}</text>')
    label_ys = []
    for k, s in enumerate(series):
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(s["ma"]))
        color = LINE_COLORS[k % len(LINE_COLORS)]
        wdt = 2.6 if k == 0 else 1.6
        out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{wdt}" stroke-linejoin="round"/>')
        ly = Y(s["ma"][-1])
        while any(abs(ly - p) < 13 for p in label_ys):  # 라벨 겹침 방지
            ly += 13
        label_ys.append(ly)
        out.append(f'<circle cx="{X(n - 1):.1f}" cy="{Y(s["ma"][-1]):.1f}" r="3" fill="{color}"/>')
        out.append(f'<text x="{X(n - 1) + 8:.1f}" y="{ly + 4:.1f}" class="lbl" fill="{color}">{s["name"]}</text>')
    out.append("</svg>")
    return "".join(out)


# ── 세계지도 (정거원통, 본초자오선 중심) ─────────────────────────────
MAP_W, LAT_TOP, LAT_BOTTOM = 1000, 85, -58
MAP_H = round(MAP_W * (LAT_TOP - LAT_BOTTOM) / 360)  # 397 — 경도·위도 1도가 같은 길이


def _xy(lon: float, lat: float, w: int = MAP_W, h: int = MAP_H) -> tuple[float, float]:
    """경위도 → SVG 좌표. scripts/build_world_path.py 도 이 함수를 쓴다."""
    x = (lon + 180) / 360 * w
    y = (LAT_TOP - lat) / (LAT_TOP - LAT_BOTTOM) * h
    return round(x, 1), round(y, 1)


# 지도에 점을 찍는 대표 지역 (순서 고정). 세부 지역·국가마다 찍지 않는다.
MAP_REGIONS = ["동아시아", "동남아시아", "남아시아", "중동", "유럽", "러시아·CIS",
               "북미", "중남미", "아프리카", "오세아니아"]
# 태깅 지역(geo.REGIONS) → 대표 지역. 북극은 북극항로가 러시아 연안을 따라가므로 러시아·CIS로.
REGION_TO_MAP = {"동아시아": "동아시아", "동남아": "동남아시아", "남아시아": "남아시아", "중동": "중동",
                 "유럽": "유럽", "러시아·CIS": "러시아·CIS", "북극": "러시아·CIS", "북미": "북미",
                 "중남미": "중남미", "아프리카": "아프리카", "오세아니아": "오세아니아"}
COUNTRY_TO_MAP = {
    **{c: "동아시아" for c in ("KR", "CN", "JP", "TW", "HK", "MN", "KP")},
    **{c: "동남아시아" for c in ("SG", "VN", "TH", "MY", "ID", "PH", "MM", "KH")},
    **{c: "남아시아" for c in ("IN", "BD", "LK", "PK")},
    **{c: "중동" for c in ("AE", "SA", "IR", "IL", "YE", "TR", "QA", "OM")},
    **{c: "유럽" for c in ("DE", "NL", "BE", "FR", "GB", "IT", "ES", "PT", "GR", "DK", "NO", "SE",
                          "FI", "PL", "UA", "EE", "CH")},
    **{c: "러시아·CIS" for c in ("RU", "KZ", "UZ")},
    **{c: "북미" for c in ("US", "CA", "MX")},
    **{c: "중남미" for c in ("PA", "BR", "CL", "PE", "CO", "AR")},
    **{c: "아프리카" for c in ("EG", "ZA", "KE", "TZ", "NG", "MA", "DJ")},
    **{c: "오세아니아" for c in ("AU", "NZ")},
}
# 점 위치 (경도, 위도) — 대륙의 시각적 중심. 가까운 아시아 3곳은 서로 겹치지 않게 벌려 둠.
MAP_POS = {"동아시아": (116, 37), "동남아시아": (106, 8), "남아시아": (78, 21), "중동": (46, 28),
           "유럽": (14, 50), "러시아·CIS": (78, 60), "북미": (-100, 42), "중남미": (-62, -12),
           "아프리카": (20, 3), "오세아니아": (134, -25)}


def map_regions_of(a: dict) -> list[str]:
    """기사 하나가 걸리는 대표 지역들 (중복 없이, MAP_REGIONS 순서)."""
    g = a.get("geo") or {}
    hits = {REGION_TO_MAP[r] for r in g.get("regions", []) if r in REGION_TO_MAP}
    if not hits:  # 지역 태그가 없으면 국가로
        hits = {COUNTRY_TO_MAP[c] for c in g.get("countries", []) if c in COUNTRY_TO_MAP}
    return [r for r in MAP_REGIONS if r in hits]


def map_regions(day_date: str | None, day_articles: list[dict]) -> dict:
    """당일 기사 → 대표 지역별 집계 {date, regions:[...], unmapped, selected}."""
    buckets: dict[str, list[dict]] = {r: [] for r in MAP_REGIONS}
    unmapped = 0
    for a in day_articles:
        rs = map_regions_of(a)
        if not rs:
            unmapped += 1
        for r in rs:
            buckets[r].append(a)
    regions = []
    for r in MAP_REGIONS:
        arts = sorted(buckets[r], key=lambda a: (-abs((a.get("geo") or {}).get("impact", 0)),
                                                -(a.get("relevance") or 0), a["published"]))
        avg = _avg([(a.get("geo") or {}).get("impact", 0) for a in arts])
        x, y = _xy(*MAP_POS[r])
        n = len(arts)
        regions.append({
            "name": r, "slug": slug(r), "count": n, "avg": avg, "avg_label": fmt_impact(avg),
            "cls": impact_class(avg), "x": x, "y": y,
            "px": round(x / MAP_W * 100, 2), "py": round(y / MAP_H * 100, 2),  # HTML 겹침용 %
            "d": round(2 * min(22, max(9, 9 + (n ** 0.5 - 1) * 6.5))) if n else 0,  # 지름 18~44px
            "articles": [{
                "id": a["id"], "anchor": "art-" + re.sub(r"[^0-9a-z가-힣]+", "-", a["id"].lower()).strip("-"),
                "title": a["title"], "url": a["url"], "source": a.get("source_name", ""),
                "time": a["published"][11:16], "relevance": a.get("relevance") or 0,
                "impact": (a.get("geo") or {}).get("impact", 0), "note": (a.get("geo") or {}).get("note", ""),
                "countries": (a.get("geo") or {}).get("countries", []),
            } for a in arts],
        })
    with_dots = [r for r in regions if r["count"]]
    selected = max(with_dots, key=lambda r: (r["count"], -(r["avg"] or 0)))["slug"] if with_dots else None
    return {"date": day_date, "regions": regions, "unmapped": unmapped, "selected": selected,
            "mapped": sum(1 for a in day_articles if map_regions_of(a))}


def world_map_svg(map_data: dict, land_path: str) -> str:
    """육지 + 위도 보조선 + 0건 지역의 옅은 이름. 점(버튼)은 템플릿이 HTML로 겹친다."""
    w, h = MAP_W, MAP_H
    counts = ", ".join(f"{r['name']} {r['count']}건" for r in map_data["regions"] if r["count"])
    out = [f'<svg viewBox="0 0 {w} {h}" class="world-svg" role="img" aria-labelledby="map-title map-desc" '
           f'preserveAspectRatio="xMidYMid meet">',
           '<title id="map-title">당일 브리핑 기사가 다룬 지역</title>',
           f'<desc id="map-desc">{map_data.get("date") or ""} 브리핑 기준: {counts or "지역이 특정된 기사 없음"}</desc>']
    for lat in (60, 30, 0, -30):
        y = _xy(0, lat)[1]
        out.append(f'<line x1="0" x2="{w}" y1="{y}" y2="{y}" class="grid"/>')
    out.append(f'<path d="{land_path}" class="land"/>')
    for r in map_data["regions"]:
        if not r["count"]:
            out.append(f'<text x="{r["x"]}" y="{r["y"] + 4}" class="region-off" text-anchor="middle">{r["name"]}</text>')
    out.append("</svg>")
    return "".join(out)
