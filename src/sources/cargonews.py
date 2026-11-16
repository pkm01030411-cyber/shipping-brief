"""카고뉴스 (cargonews.co.kr) 수집기.

RSS(/rss/allArticle.xml)로 목록을 받고, 본문은 기사 페이지에서 가져옵니다.
  본문: article#article-view-content-div
  날짜: meta[property=article:published_time]
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import feedparser
from bs4 import BeautifulSoup

from ..common import Article, Http, clean_text, parse_kst

log = logging.getLogger("brief.cargonews")


def _idx(url: str) -> str:
    q = parse_qs(urlparse(url).query)
    return (q.get("idxno") or [""])[0]


def parse_feed(xml_text: str, cfg: dict) -> list[dict]:
    feed = feedparser.parse(xml_text)
    out = []
    for e in feed.entries:
        url = (e.get("link") or "").replace("http://", "https://")
        title = (e.get("title") or "").strip()
        pub = parse_kst(e.get("published", "") or e.get("pubDate", ""), cfg)
        if not url or not title or not pub:
            continue
        desc = BeautifulSoup(e.get("description", "") or "", "html.parser").get_text(" ", strip=True)
        out.append({
            "title": title, "url": url, "published": pub,
            "author": (e.get("author") or "").strip(), "description": desc,
        })
    return out


def parse_article(html: str, cfg: dict) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    body_el = soup.select_one("#article-view-content-div")
    body = ""
    if body_el:
        for tag in body_el.select("script, style, img, iframe, figure, figcaption, table, .article-ad, .ad"):
            tag.decompose()
        for br in body_el.find_all("br"):
            br.replace_with("\n")
        body = clean_text(body_el.get_text("\n"))
        body = re.sub(r"\n?저작권자.*$", "", body, flags=re.S).strip()

    og_title = soup.select_one("meta[property='og:title']")
    pub_meta = soup.select_one("meta[property='article:published_time']")
    section = ""
    crumbs = [a.get_text(strip=True) for a in soup.select("a[href*='sc_section_code']") if a.get_text(strip=True)]
    if crumbs:
        # 페이지 제목 "제목 < 서브 < 해운 < 기사본문" 에서 섹션 뽑기
        m = re.search(r"<\s*([^<]+?)\s*<\s*기사본문", soup.title.get_text() if soup.title else "")
        section = m.group(1).strip() if m else ""

    return {
        "title": og_title["content"].strip() if og_title and og_title.get("content") else "",
        "published": parse_kst(pub_meta["content"], cfg) if pub_meta and pub_meta.get("content") else None,
        "body": body,
        "category": section,
    }


def collect(cfg: dict, http: Http, cutoff: datetime, known: set[str]) -> list[Article]:
    scfg = cfg["sources"]["cargonews"]
    max_n = cfg["collect"]["max_per_source"]
    skip_kw = scfg.get("skip_title_keywords", [])

    try:
        entries = parse_feed(http.get(scfg["rss"]).text, cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("카고뉴스 RSS 실패: %s", e)
        return []

    picked = []
    for it in entries:
        if it["published"] < cutoff or it["url"] in known:
            continue
        if any(k in it["title"] for k in skip_kw):
            continue
        picked.append(it)
    picked = sorted(picked, key=lambda x: x["published"], reverse=True)[:max_n]

    articles: list[Article] = []
    for it in picked:
        try:
            detail = parse_article(http.get(it["url"]).text, cfg)
        except Exception as e:  # noqa: BLE001
            log.warning("카고뉴스 본문 실패 %s: %s", it["url"], e)
            detail = {}
        body = detail.get("body") or it["description"]  # 본문 실패 시 RSS 요약문으로 대체
        if not body:
            continue
        articles.append(Article(
            id=f"cargonews:{_idx(it['url'])}",
            source="cargonews",
            source_name=scfg["name"],
            title=detail.get("title") or it["title"],
            url=it["url"],
            published=(detail.get("published") or it["published"]).isoformat(),
            category=detail.get("category", ""),
            author=it["author"],
            body=body,
        ))
    log.info("카고뉴스: %d건 수집", len(articles))
    return articles
