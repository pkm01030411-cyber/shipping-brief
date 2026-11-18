"""러시아·유라시아 섹션 소스 수집기.

모든 수집기는 '후보(candidate)' dict 목록을 돌려준다. 본문은 선별(관련도 상위 10~15건) 뒤에만
fetch_body()로 가져와 요청 수를 줄인다.

  candidate = {source, url, title, published(datetime|None), description, body(선택), category}

GitHub Actions(미국 서버)에서 2026-11-18 접속 점검 완료:
  The Moscow Times RSS · Meduza EN RSS · Eurasianet RSS · Times of Central Asia RSS(본문 포함)
  The Barents Observer(RSS 없음 → 홈 목록 + 기사 메타) · PortNews 러시아어판(RSS 없음 → 날짜별 목록)
  KOTRA 해외시장뉴스(RSS 중지 → 목록 JSON API, 국가 코드별)
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import feedparser
from bs4 import BeautifulSoup

from ..common import clean_text, parse_kst

log = logging.getLogger("brief.eurasia.src")

MSK = ZoneInfo("Europe/Moscow")
UTC = ZoneInfo("UTC")


def cand_id(source: str, url: str) -> str:
    """URL 기반의 안정적인 기사 id (같은 기사는 몇 번 수집해도 같은 id)."""
    return f"{source}:{hashlib.sha1(url.encode()).hexdigest()[:10]}"


# ── 본문 추출 ────────────────────────────────────────────────────
_JUNK = ("script, style, noscript, iframe, figure, figcaption, form, aside, button, svg, "
         ".contribute-article, .newsletter, .signup, .related, .share, .advert, .ad")


def _paras_text(els) -> str:
    out = []
    for p in els:
        t = p.get_text(" ", strip=True)
        if t:
            out.append(t)
    return clean_text("\n\n".join(out))


def extract_body(html: str, selectors: list[str] | None = None, min_len: int = 40) -> str:
    """지정 선택자 → 없으면 '긴 문단을 가장 많이 품은 부모 유형'의 문단을 문서 순서대로 모은다.
    (Moscow Times·Barents처럼 본문이 여러 블록으로 쪼개진 페이지도 처리)"""
    soup = BeautifulSoup(html, "html.parser")
    for j in soup.select(_JUNK):
        j.decompose()
    for sel in selectors or []:
        els = soup.select(sel)
        if els:
            ps = [p for el in els for p in (el.find_all("p") or [el])]
            txt = _paras_text(ps)
            if len(txt) >= min_len:
                return txt
    sig = Counter()
    long_ps = []
    for p in soup.find_all("p"):
        if len(p.get_text(strip=True)) >= 60:
            par = p.parent
            key = (par.name, " ".join(par.get("class") or []))
            sig[key] += 1
            long_ps.append((key, p))
    if not sig:
        return ""
    best = sig.most_common(1)[0][0]
    return _paras_text(p for k, p in long_ps if k == best)


def _html_to_text(s: str) -> str:
    if not s:
        return ""
    return extract_body(s) or clean_text(BeautifulSoup(s, "html.parser").get_text("\n"))


def _meta(soup: BeautifulSoup, prop: str) -> str:
    m = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return (m.get("content") or "").strip() if m else ""


def _iso_dt(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    s = re.sub(r"([+-]\d{2})$", r"\1:00", s)  # '2026-11-18 15:04:00+03' → '+03:00'
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# ── RSS 공통 ─────────────────────────────────────────────────────
def parse_rss(xml: str, source: str, cfg: dict) -> list[dict]:
    feed = feedparser.parse(xml)
    out = []
    for e in feed.entries:
        url = (e.get("link") or "").strip()
        title = re.sub(r"\s+", " ", (e.get("title") or "").replace("\xa0", " ")).strip()
        if not url or not title:
            continue
        pub = None
        if e.get("published_parsed"):
            pub = datetime(*e.published_parsed[:6], tzinfo=UTC)
        else:
            raw = (e.get("published") or e.get("pubdate") or "").strip()
            for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
                try:  # Eurasianet: 'Nov 17, 2026' (날짜만) → 그날 정오(현지)로 간주
                    pub = datetime.strptime(raw, fmt).replace(hour=12, tzinfo=ZoneInfo(cfg["site"]["timezone"]))
                    break
                except ValueError:
                    pass
        desc = BeautifulSoup(e.get("summary", "") or "", "html.parser").get_text(" ", strip=True)
        content = ""
        for c in e.get("content", []) or []:
            content += c.get("value", "")
        cat = ""
        if e.get("tags"):
            cat = (e.tags[0].get("term") or "").strip()
        out.append({"source": source, "url": url, "title": title, "published": pub,
                    "description": desc[:400], "body": _html_to_text(content) if content else "",
                    "category": cat})
    return out


# ── The Barents Observer (홈 목록) ───────────────────────────────
BARENTS_BASE = "https://www.thebarentsobserver.com"


def parse_barents_home(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        h = a["href"]
        m = re.search(r"/(news|security|climate-crisis|democracy-and-media|opinion|arctic-lens|business)/[^/]+/(\d{5,})$", h)
        if not m:
            continue
        head = a.select_one(".headline")
        if not head:
            continue
        url = h if h.startswith("http") else BARENTS_BASE + h
        if url in seen:
            continue
        seen.add(url)
        kicker = a.select_one(".kicker")
        out.append({"source": "barents", "url": url, "title": head.get_text(" ", strip=True),
                    "published": None, "description": "", "body": "",
                    "category": kicker.get_text(" ", strip=True).strip('"“”') if kicker else m.group(1),
                    "_num": int(m.group(2))})
    out.sort(key=lambda x: -x["_num"])  # 번호가 클수록 최신
    return out


def parse_barents_article(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    return {"published": _iso_dt(_meta(soup, "article:published_time")),
            "description": _meta(soup, "og:description"),
            "body": extract_body(html, [".bodytext"])}


# ── PortNews 러시아어판 (날짜별 목록) ─────────────────────────────
PORTNEWS_BASE = "https://portnews.ru"
_RU_MONTHS = {m: i + 1 for i, m in enumerate(
    ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"])}


def _ru_date(s: str):
    m = re.search(r"(\d{1,2})\s+([а-я]+)\s+(\d{4})", s.lower())
    if not m or m.group(2) not in _RU_MONTHS:
        return None
    return datetime(int(m.group(3)), _RU_MONTHS[m.group(2)], int(m.group(1))).date()


def parse_portnews_list(html: str, fallback_date=None) -> list[dict]:
    """목록은 '18 ноября 2026' 날짜 구분선 + 'HH:MM' 시각 + 제목 + 분류. 시각은 모스크바 기준."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".page_newsList") or soup
    cur = fallback_date
    out = []
    for el in root.find_all(["div"], recursive=True):
        cls = el.get("class") or []
        if "date_hr" in cls:
            d = _ru_date(el.get_text(" ", strip=True))
            if d:
                cur = d
        elif "nl_item" in cls:
            a = el.find("a", href=re.compile(r"^/news/\d+/?$"))
            if not a or cur is None:
                continue
            t = el.select_one(".onlytime")
            hh, mm = (t.get_text(strip=True).split(":") + ["0"])[:2] if t else ("12", "0")
            try:
                pub = datetime(cur.year, cur.month, cur.day, int(hh), int(mm), tzinfo=MSK)
            except ValueError:
                pub = None
            rub = el.select_one(".nl_rubric_name")
            out.append({"source": "portnews", "url": PORTNEWS_BASE + a["href"],
                        "title": (a.get("title") or a.get_text(" ", strip=True)).strip(),
                        "published": pub, "description": "", "body": "",
                        "category": rub.get_text(" ", strip=True) if rub else ""})
    return out


def parse_portnews_article(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    return {"published": _iso_dt(_meta(soup, "article:published_time")),
            "body": extract_body(html, ["[itemprop=articleBody]"])}


# ── 수집 진입점 ──────────────────────────────────────────────────
def collect_candidates(key: str, scfg: dict, cfg: dict, http, cutoff: datetime, known: set[str]) -> list[dict]:
    """소스 하나의 새 후보 목록 (cutoff 이후 · 이미 본 URL 제외 · 소스별 상한)."""
    cap = int(scfg.get("max_candidates", 40))
    kind = scfg.get("kind", "rss")
    if kind == "rss":
        items = parse_rss(http.get(scfg["url"]).text, key, cfg)
        # 피드가 짧은 곳(Times of Central Asia: 10건)은 WordPress 페이지 피드를 더 읽는다
        for n in range(2, int(scfg.get("feed_pages", 1)) + 1):
            if items and min((i["published"] for i in items if i.get("published")), default=cutoff) < cutoff:
                break  # 이미 수집 범위 이전까지 닿음
            sep = "&" if "?" in scfg["url"] else "?"
            try:
                items += parse_rss(http.get(f"{scfg['url']}{sep}paged={n}").text, key, cfg)
            except Exception as e:  # noqa: BLE001
                log.warning("%s 피드 %d쪽 실패: %s", key, n, e)
                break
    elif kind == "barents":
        items = parse_barents_home(http.get(scfg["url"]).text)
        items = [it for it in items if it["url"] not in known][:cap]
        for it in items:  # 홈 목록엔 날짜가 없어 기사 메타를 읽는다 (새 기사만, 하루 몇 건)
            try:
                it.update({k: v for k, v in parse_barents_article(http.get(it["url"]).text).items() if v})
            except Exception as e:  # noqa: BLE001
                log.warning("Barents 기사 메타 실패 %s: %s", it["url"], e)
    elif kind == "portnews":
        # 날짜별 목록 페이지(모스크바 날짜)를 수집 시작일부터 오늘까지
        today = datetime.now(MSK).date()
        first = cutoff.astimezone(MSK).date()
        dates = [today - timedelta(days=i) for i in range((today - first).days + 1)][:5]
        items = []
        for i, d in enumerate(dates):
            url = scfg["url"] if i == 0 else f"{scfg['url'].rstrip('/')}/{d.isoformat()}/"
            try:
                items += parse_portnews_list(http.get(url).text, d)
            except Exception as e:  # noqa: BLE001
                log.warning("PortNews 목록 실패 %s: %s", url, e)
    else:
        raise ValueError(f"알 수 없는 소스 종류: {kind}")

    out, seen = [], set()
    skip = [s.lower() for s in scfg.get("skip_title_keywords", [])]
    for it in items:
        if it["url"] in known or it["url"] in seen:
            continue
        if it.get("published") and it["published"] < cutoff:
            continue
        if it.get("published") is None and kind != "barents":
            continue
        if any(s in it["title"].lower() for s in skip):
            continue
        seen.add(it["url"])
        it.pop("_num", None)
        out.append(it)
    out.sort(key=lambda x: x.get("published") or cutoff, reverse=True)
    return out[:cap]


def fetch_body(c: dict, scfg: dict, http) -> str:
    """선별된 기사만 본문을 가져온다. RSS에 본문이 충분히 있으면 그대로."""
    if len(c.get("body") or "") >= 600:
        return c["body"]
    html = http.get(c["url"]).text
    kind = scfg.get("kind", "rss")
    if kind == "portnews":
        d = parse_portnews_article(html)
        if d.get("published"):
            c["published"] = d["published"]
        return d["body"]
    if kind == "barents":
        return parse_barents_article(html)["body"]
    soup = BeautifulSoup(html, "html.parser")
    if not c.get("published"):
        c["published"] = _iso_dt(_meta(soup, "article:published_time"))
    return extract_body(html, scfg.get("body_selectors") or [])


# ── KOTRA 해외시장뉴스 (주간 리뷰용) ─────────────────────────────
KOTRA_BASE = "https://dream.kotra.or.kr"
KOTRA_BBS = "242,244,322,245,246,464,518,505,484,519"  # 뉴스 게시판 전체 (경제·무역, 통상·규제, 투자진출, 현장·인터뷰, 기고 등)


def kotra_list(http, nat_cd: str, per_page: int = 20) -> list[dict]:
    """국가별 최신 뉴스 목록 (JSON). 목록 페이지에서 쓰는 AJAX와 같은 요청."""
    s = http.s
    ref = f"{KOTRA_BASE}/kotranews/cms/com/index.do?MENU_ID=70"
    s.get(ref, timeout=20)  # 세션 쿠키
    data = {"pageNo": "1", "pagePerCnt": str(per_page), "recordCountPerPage": str(per_page),
            "SITE_NO": "3", "MENU_ID": "70", "CONTENTS_NO": "1", "bbsGbn": "00", "bbsSn": KOTRA_BBS,
            "pNewsGbn": KOTRA_BBS, "pNttSn": "", "viewType": "", "pStartDt": "", "pEndDt": "",
            "sSearchVal": "", "pNatCd": str(nat_cd)}
    r = s.post(f"{KOTRA_BASE}/ajaxf/frNews/getKotraBoardList.do", data=data, timeout=25,
               headers={"X-Requested-With": "XMLHttpRequest", "Referer": ref})
    r.raise_for_status()
    return parse_kotra_list(r.json())


def _unent(s: str) -> str:
    return BeautifulSoup(s or "", "html.parser").get_text(" ", strip=True)


def parse_kotra_list(js: dict) -> list[dict]:
    out = []
    for x in ((js or {}).get("data") or {}).get("list") or []:
        sn, bbs = str(x.get("NTT_SN") or ""), str(x.get("BBS_SN") or "")
        if not sn:
            continue
        out.append({
            "id": f"kotra:{sn}",
            "title": _unent(x.get("NTT_SJ")),
            "summary_raw": _unent(x.get("SMMAR_CN")),
            "date": str(x.get("OTHBC_DT") or "")[:10],
            "kbc": x.get("KBC") or "", "nat": x.get("NAT") or "", "board": x.get("BBS_NAME") or "",
            "url": (f"{KOTRA_BASE}/kotranews/cms/news/actionKotraBoardDetail.do?SITE_NO=3&MENU_ID=70"
                    f"&CONTENTS_NO=1&bbsGbn={bbs}&bbsSn={bbs}&pNttSn={sn}"),
        })
    return out


def parse_kotra_detail(html: str) -> str:
    return extract_body(html, [".view_txt"], min_len=20)


def parse_dt_any(s: str, cfg: dict) -> datetime | None:
    return _iso_dt(s) or parse_kst(s, cfg)
