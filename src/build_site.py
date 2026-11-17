"""3단계: data/*.json → site/ (정적 HTML + 태그 페이지 + 주간 리뷰 + PWA + RSS)."""
from __future__ import annotations

import json
import logging
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from html import escape
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .common import (SITE_DIR, STATIC_DIR, TEMPLATE_DIR, all_days, load_config,
                     load_day, now_local)
from . import geo as geo_mod
from .weekly import all_weeks, load_week

log = logging.getLogger("brief.build")

WEEKDAYS = "월화수목금토일"


# ── 필터 ────────────────────────────────────────────────────────
def fmt_date(s: str) -> str:
    d = datetime.strptime(s, "%Y-%m-%d")
    return f"{d.year}년 {d.month}월 {d.day}일 ({WEEKDAYS[d.weekday()]})"


def fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%m.%d %H:%M")
    except ValueError:
        return iso


def tag_slug(t: str) -> str:
    """태그 → 파일명. 한글은 그대로, 구분자는 '-'로. URL은 퍼센트 인코딩."""
    s = re.sub(r"[\s/\\·•:;,.()\[\]{}'\"?#&]+", "-", t.strip()).strip("-").lower()
    return quote(s or "tag", safe="")


def tag_file(t: str) -> str:
    s = re.sub(r"[\s/\\·•:;,.()\[\]{}'\"?#&]+", "-", t.strip()).strip("-").lower()
    return s or "tag"


# ── 키워드 ──────────────────────────────────────────────────────
def match_keywords(a: dict, keywords: list[str]) -> list[str]:
    hay = " ".join([a.get("title", ""), a.get("subtitle", ""), a.get("summary", ""),
                    " ".join(a.get("tags", []))])
    out = []
    for k in keywords:
        if k.isascii():
            # 영문 키워드(ONE, MSC…)는 단어 경계로 — 'zone', 'phone' 오탐 방지. 한글 접미(ONE은/ONE이) 허용
            if re.search(r"(?<![A-Za-z])" + re.escape(k) + r"(?![A-Za-z])", hay):
                out.append(k)
        elif k.lower() in hay.lower():
            out.append(k)
    return out


def annotate(a: dict, keywords: list[str]) -> dict:
    return {**a, "kw": match_keywords(a, keywords)}


# ── 하루치 가공 ──────────────────────────────────────────────────
def prepare_day(day: dict, cfg: dict) -> dict:
    keywords = cfg["site"].get("highlight_keywords", [])
    arts = [annotate(a, keywords) for a in day.get("articles", [])]
    brief = day.get("brief", {}) or {}
    by_id = {a["id"]: a for a in arts}
    top = []
    for t in brief.get("top", []):
        a = by_id.get(t["id"])
        if a:
            top.append({**a, "reason": t.get("reason", "")})
    top_ids = {t["id"] for t in top}
    rest = [a for a in arts if a["id"] not in top_ids]
    rest.sort(key=lambda a: a["published"], reverse=True)
    rest.sort(key=lambda a: -(a.get("relevance") or 0))

    sources: dict[str, int] = {}
    source_keys: dict[str, str] = {}
    for a in arts:
        sources[a["source_name"]] = sources.get(a["source_name"], 0) + 1
        source_keys[a["source"]] = a["source_name"]
    kw_counter = Counter(k for a in arts for k in a["kw"])
    # 오늘의 용어: 기사별 terms를 모아 중복 제거 (관련도 높은 기사 우선)
    glossary, seen_terms = [], set()
    for a in sorted(arts, key=lambda x: -(x.get("relevance") or 0)):
        for t in a.get("terms", []) or []:
            key = re.sub(r"[\s()（）]", "", t["term"].split("(")[0]).lower()
            if key and key not in seen_terms:
                seen_terms.add(key)
                glossary.append({**t, "url": a["url"], "title": a["title"]})
    pubs = sorted(a["published"] for a in arts)
    coverage = f"{fmt_time(pubs[0])} ~ {fmt_time(pubs[-1])} 기사" if pubs else ""
    return {**day, "articles": arts, "top": top, "rest": rest, "sources": sources,
            "source_keys": list(source_keys.items()), "brief": brief, "coverage": coverage, "glossary": glossary,
            "kw_counts": kw_counter.most_common(), "date_label": fmt_date(day["date"])}


# ── RSS 출력 ────────────────────────────────────────────────────
def build_feed(site: dict, days: list[dict]) -> str:
    items = []
    for d in days[:14]:
        b = d["brief"]
        desc = escape((b.get("headline", "") + "\n\n" + b.get("overview", "")).strip())
        top = "".join(f"<li>{escape(t['title'])} — {escape(t.get('reason', ''))}</li>" for t in d["top"])
        items.append(f"""<item>
<title>{escape(d['date_label'])} — {escape(b.get('headline', '브리핑'))}</title>
<link>{site['base_url']}day/{d['date']}.html</link>
<guid>{site['base_url']}day/{d['date']}.html</guid>
<pubDate>{datetime.strptime(d['date'], '%Y-%m-%d').strftime('%a, %d %b %Y 07:00:00 +0900')}</pubDate>
<description><![CDATA[<p>{desc}</p><ol>{top}</ol>]]></description>
</item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>{escape(site['title'])}</title>
<link>{site['base_url']}</link>
<description>{escape(site['tagline'])}</description>
<language>ko</language>
{''.join(items)}
</channel></rss>"""


# ── 빌드 ────────────────────────────────────────────────────────
def build() -> None:
    cfg = load_config()
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]))
    env.filters["ftime"] = fmt_time
    env.filters["fdate"] = fmt_date
    env.filters["tagslug"] = tag_slug
    env.filters["impcls"] = geo_mod.impact_class
    env.filters["impfmt"] = geo_mod.fmt_impact
    env.filters["geoslug"] = geo_mod.slug
    env.globals["country_ko"] = geo_mod.COUNTRY_KO

    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    for sub in ("day", "tag", "week"):
        (SITE_DIR / sub).mkdir(parents=True)
    shutil.copytree(STATIC_DIR, SITE_DIR / "static")

    site = {**cfg["site"], "built_at": now_local(cfg).strftime("%Y-%m-%d %H:%M")}
    site["base_url"] = (site.get("base_url") or "").rstrip("/") + "/" if site.get("base_url") else ""

    # 하루치 페이지
    days = all_days()
    prepared: dict[str, dict] = {}
    archive = []
    for d in days:
        day = load_day(d)
        if not day or not day.get("articles"):
            continue
        p = prepare_day(day, cfg)
        prepared[d] = p
        archive.append({"date": d, "label": p["date_label"], "count": len(day["articles"]),
                        "headline": p["brief"].get("headline", "")})
    days = [d for d in days if d in prepared]

    day_tpl = env.get_template("day.html")
    for i, d in enumerate(days):
        prev_d = days[i + 1] if i + 1 < len(days) else None
        next_d = days[i - 1] if i > 0 else None
        html = day_tpl.render(site=site, day=prepared[d], prev=prev_d, next=next_d, root="../", nav="today")
        (SITE_DIR / "day" / f"{d}.html").write_text(html, encoding="utf-8")

    # 오늘 = 가장 최근 날짜
    if days:
        html = day_tpl.render(site=site, day=prepared[days[0]], prev=days[1] if len(days) > 1 else None,
                              next=None, root="", nav="today")
    else:
        html = env.get_template("empty.html").render(site=site, root="", nav="today")
    (SITE_DIR / "today.html").write_text(html, encoding="utf-8")

    (SITE_DIR / "archive.html").write_text(
        env.get_template("archive.html").render(site=site, archive=archive, root="", nav="archive"), encoding="utf-8")

    # 태그 페이지
    by_tag: dict[str, list[dict]] = defaultdict(list)
    for d in days:
        for a in prepared[d]["articles"]:
            for t in a.get("tags", []):
                by_tag[t].append(a)
    # 관심 키워드도 태그처럼 페이지 생성 (태그에 없더라도 본문 매칭으로)
    for kw in cfg["site"].get("highlight_keywords", []):
        if kw not in by_tag:
            hits = [a for d in days for a in prepared[d]["articles"] if kw in a["kw"]]
            if hits:
                by_tag[kw] = hits
    tag_tpl = env.get_template("tag.html")
    tag_index = []
    max_count = max((len(v) for v in by_tag.values()), default=1)
    for t, arts in by_tag.items():
        # 같은 기사가 두 번 들어가지 않게
        seen, uniq = set(), []
        for a in arts:
            if a["id"] not in seen:
                seen.add(a["id"]); uniq.append(a)
        groups: dict[str, list[dict]] = defaultdict(list)
        for a in uniq:
            groups[a["published"][:10]].append(a)
        by_date = sorted(groups.items(), reverse=True)
        html = tag_tpl.render(site=site, tag=t, articles=uniq, by_date=by_date,
                              first_date=by_date[-1][0], last_date=by_date[0][0], root="../", nav="tags")
        (SITE_DIR / "tag" / f"{tag_file(t)}.html").write_text(html, encoding="utf-8")
        tag_index.append({"name": t, "count": len(uniq), "weight": round(len(uniq) / max_count, 2)})
    tag_index.sort(key=lambda x: (-x["count"], x["name"]))
    (SITE_DIR / "tags.html").write_text(
        env.get_template("tags.html").render(site=site, tags=tag_index, root="", nav="tags"), encoding="utf-8")

    # 스크랩
    (SITE_DIR / "scrap.html").write_text(
        env.get_template("scrap.html").render(site=site, root="", nav="scrap"), encoding="utf-8")

    # 주간 리뷰
    weeks = all_weeks()
    keywords = cfg["site"].get("highlight_keywords", [])
    week_tpl = env.get_template("weekly.html")
    for i, wid in enumerate(weeks):
        w = load_week(wid)
        if not w:
            continue
        by_id = {a["id"]: annotate(a, keywords) for a in w.get("articles", [])}
        top = [{**by_id[t["id"]], "reason": t.get("reason", "")} for t in w["review"].get("top", []) if t["id"] in by_id]
        label = f"{w['week'][:4]}년 {int(w['week'][-2:])}주차"
        ctx = {**w, "by_id": by_id, "top": top, "label": label}
        html = week_tpl.render(site=site, week=ctx, root="../", nav="weekly",
                               prev=weeks[i + 1] if i + 1 < len(weeks) else None,
                               next=weeks[i - 1] if i > 0 else None)
        (SITE_DIR / "week" / f"{wid}.html").write_text(html, encoding="utf-8")
        if i == 0:
            (SITE_DIR / "weekly.html").write_text(
                week_tpl.render(site=site, week=ctx, root="", nav="weekly",
                                prev=weeks[1] if len(weeks) > 1 else None, next=None), encoding="utf-8")
    if not weeks:
        (SITE_DIR / "weekly.html").write_text(
            env.get_template("weekly_empty.html").render(site=site, root="", nav="weekly"), encoding="utf-8")

    # 국제정세 대시보드
    seen_ids, all_articles = set(), []
    for d in days:
        for a in prepared[d]["articles"]:
            if a["id"] not in seen_ids:
                seen_ids.add(a["id"]); all_articles.append(a)
    g = geo_mod.aggregate(all_articles, now_local(cfg).date(), load_week(weeks[0]) if weeks else None)
    (SITE_DIR / "geo.html").write_text(env.get_template("geo.html").render(
        site=site, root="", nav="geo", g=g,
        route_svg=geo_mod.route_svg(g["periods"][30]["chokepoints"], g["periods"][7]["chokepoints"]),
        trend_svg=geo_mod.trend_svg(g["trend"])), encoding="utf-8")
    (SITE_DIR / "geo.json").write_text(json.dumps(g, ensure_ascii=False, default=str), encoding="utf-8")

    # 대문(홈)
    latest_week = None
    if weeks and load_week(weeks[0]):
        w = load_week(weeks[0])
        latest_week = {**w, "label": f"{w['week'][:4]}년 {int(w['week'][-2:])}주차"}
    kw_counter: Counter = Counter()
    for d in days[:7]:
        for kw, n in prepared[d]["kw_counts"]:
            kw_counter[kw] += n
    kw_top = kw_counter.most_common(8)
    kw_max = kw_top[0][1] if kw_top else 1
    kw_trend = [(k, n, round(n / kw_max, 2)) for k, n in kw_top]
    home = env.get_template("home.html").render(
        site=site, root="", nav="home",
        latest=prepared[days[0]] if days else None, days=days,
        total_articles=sum(len(prepared[d]["articles"]) for d in days),
        week=latest_week, kw_trend=kw_trend, archive=archive, top_tags=tag_index[:14],
        geo_top=sorted([c for c in g["periods"][30]["chokepoints"] if c["count"]],
                       key=lambda c: (-c["count"], c["avg"] or 0))[:3],
        geo_line=g["line"], geo_tiles=g["tiles"])
    (SITE_DIR / "index.html").write_text(home, encoding="utf-8")

    # PWA
    manifest = {
        "name": site["title"], "short_name": site.get("short_name", site["title"]),
        "description": site["tagline"], "start_url": "./index.html", "scope": "./",
        "display": "standalone", "background_color": "#fbfaf7", "theme_color": "#0f3d5e", "lang": "ko",
        "icons": [{"src": "static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}],
    }
    (SITE_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    sw = (STATIC_DIR / "sw.js").read_text(encoding="utf-8").replace("__BUILD__", site["built_at"])
    (SITE_DIR / "sw.js").write_text(sw, encoding="utf-8")

    # RSS
    (SITE_DIR / "feed.xml").write_text(build_feed(site, [prepared[d] for d in days]), encoding="utf-8")
    (SITE_DIR / ".nojekyll").write_text("")
    log.info("사이트 생성: %d일치, 태그 %d개, 주간 %d개 → site/", len(days), len(tag_index), len(weeks))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build()
