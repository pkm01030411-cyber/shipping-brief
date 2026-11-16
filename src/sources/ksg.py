"""코리아쉬핑가제트 (ksg.co.kr) 수집기.

RSS가 없어 카테고리 목록 페이지를 크롤링합니다.
  목록: /news/news_list.jsp?page=N&bbsID=news&categoryCode=XXX&bbsCategory=KSG
        ul.new_list > li > dl.textarea > dt > a (제목)  /  div.date (YYYY-MM-DD HH:MM)
  본문: /news/main_newsView.jsp?pNum=NNN
        h1#newsTitle, #newsSubTitle1, #newsRegDate, #categorySpace, #newsContent
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import urljoin, parse_qs, urlparse

from bs4 import BeautifulSoup

from ..common import Article, Http, clean_text, parse_kst

log = logging.getLogger("brief.ksg")

BASE = "https://www.ksg.co.kr"
LIST_URL = BASE + "/news/news_list.jsp?page={page}&bbsID=news&categoryCode={code}&bbsCategory=KSG"


def _pnum(url: str) -> str:
    q = parse_qs(urlparse(url).query)
    return (q.get("pNum") or [""])[0]


def parse_list(html: str, category: str, cfg: dict) -> list[dict]:
    """목록 HTML → [{title, url, published(datetime), category}]"""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for li in soup.select("ul.new_list > li"):
        a = li.select_one("dl.textarea dt a[href*='main_newsView']")
        if not a:
            continue
        date_el = li.select_one("div.date")
        dt = parse_kst(date_el.get_text(" ", strip=True), cfg) if date_el else None
        url = urljoin(BASE, a["href"])
        title = a.get_text(" ", strip=True)
        if not title or not dt:
            continue
        out.append({"title": title, "url": url, "published": dt, "category": category})
    return out


def parse_article(html: str, cfg: dict) -> dict:
    """본문 HTML → {title, subtitle, published, category, body, author}"""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("h1#newsTitle")
    sub = soup.select_one("#newsSubTitle1")
    date = soup.select_one("#newsRegDate")
    cat = soup.select_one("#categorySpace")
    body_el = soup.select_one("#newsContent")

    body = ""
    author = ""
    if body_el:
        for tag in body_el.select("script, style, img, iframe, table"):
            tag.decompose()
        for br in body_el.find_all("br"):
            br.replace_with("\n")
        body = clean_text(body_el.get_text("\n"))
        # 말미 '< 박한솔 기자 hsolpark@ksg.co.kr >' 분리
        m = re.search(r"<\s*([^<>]+?기자[^<>]*)>\s*$", body)
        if m:
            author = m.group(1).strip()
            body = body[: m.start()].rstrip()
        # ▲ 사진 캡션 줄 제거
        body = "\n".join(l for l in body.split("\n") if not l.startswith("▲"))

    return {
        "title": title.get_text(" ", strip=True) if title else "",
        "subtitle": sub.get_text(" ", strip=True) if sub else "",
        "published": parse_kst(date.get_text(" ", strip=True), cfg) if date else None,
        "category": cat.get_text(" ", strip=True) if cat else "",
        "body": body,
        "author": author,
    }


def collect(cfg: dict, http: Http, cutoff: datetime, known: set[str]) -> list[Article]:
    scfg = cfg["sources"]["ksg"]
    max_n = cfg["collect"]["max_per_source"]
    seen: dict[str, dict] = {}

    for code, cname in scfg["categories"].items():
        for page in range(1, scfg.get("pages_per_category", 1) + 1):
            url = LIST_URL.format(page=page, code=code)
            try:
                items = parse_list(http.get(url).text, cname, cfg)
            except Exception as e:  # noqa: BLE001
                log.warning("KSG 목록 실패 %s: %s", url, e)
                break
            if not items:
                break
            older_found = False
            for it in items:
                if it["published"] < cutoff:
                    older_found = True
                    continue
                if it["url"] in known or it["url"] in seen:
                    continue
                seen[it["url"]] = it
            if older_found:
                break  # 목록은 최신순 → 더 이전 페이지는 볼 필요 없음

    # 최신순으로 자르고 본문 수집
    picked = sorted(seen.values(), key=lambda x: x["published"], reverse=True)[:max_n]
    articles: list[Article] = []
    for it in picked:
        try:
            detail = parse_article(http.get(it["url"]).text, cfg)
        except Exception as e:  # noqa: BLE001
            log.warning("KSG 본문 실패 %s: %s", it["url"], e)
            detail = {}
        if not detail.get("body"):
            log.info("KSG 본문 없음(건너뜀): %s", it["title"])
            continue
        pub = detail.get("published") or it["published"]
        articles.append(Article(
            id=f"ksg:{_pnum(it['url'])}",
            source="ksg",
            source_name=scfg["name"],
            title=detail.get("title") or it["title"],
            url=it["url"],
            published=pub.isoformat(),
            category=it["category"] or detail.get("category", ""),
            subtitle=detail.get("subtitle", ""),
            author=detail.get("author", ""),
            body=detail["body"],
        ))
    log.info("KSG: %d건 수집", len(articles))
    return articles
