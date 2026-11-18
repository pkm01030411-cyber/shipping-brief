"""러시아·유라시아 섹션: 파서 · 선별 로직 · 파이프라인(가짜 HTTP·가짜 모델)."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from src import eurasia as eu
from src import eurasia_weekly as euw
from src.sources import eurasia as E

F = Path(__file__).parent / "fixtures" / "eurasia"
CFG = yaml.safe_load(open(Path(__file__).parent.parent / "config.yaml", encoding="utf-8"))
KST = ZoneInfo("Asia/Seoul")


def fx(name):
    return (F / name).read_text(encoding="utf-8")


# ── 파서 ────────────────────────────────────────────────────────
def test_eurasianet_date_only_pubdate():
    items = E.parse_rss(fx("eurasianet.xml"), "eurasianet", CFG)
    assert len(items) == 3
    assert items[0]["published"].date().isoformat() == "2026-11-17"
    assert items[0]["title"].startswith("China secures")


def test_barents_home_and_article():
    items = E.parse_barents_home(fx("barents_home.html"))
    assert items and all(i["url"].startswith("https://www.thebarentsobserver.com/") for i in items)
    assert items[0]["_num"] >= items[-1]["_num"]           # 최신순
    assert all(i["title"] and '"' not in i["category"] for i in items)
    d = E.parse_barents_article(fx("barents_article.html"))
    assert d["published"].isoformat().startswith("2026-11-17T14:05")
    assert "paragraph one" in d["body"] and "paragraph two" in d["body"] and "Related" not in d["body"]


def test_portnews_list_moscow_time():
    items = E.parse_portnews_list(fx("portnews_ru_list.html"))
    assert len(items) == 6
    a = items[0]
    assert a["url"].startswith("https://portnews.ru/news/") and a["category"]
    assert a["published"].utcoffset() == timedelta(hours=3)
    assert a["published"].date().isoformat() == "2026-11-18"
    d = E.parse_portnews_article(fx("portnews_article.html"))
    assert d["published"].utcoffset() == timedelta(hours=3)
    assert "Первый абзац" in d["body"] and "var x" not in d["body"]


def test_generic_body_skips_donation_box():
    body = E.extract_body(fx("mt_article.html"), [".article__block--html"])
    assert "Crimean Bridge" in body and "rail traffic" in body and "Support" not in body


def test_kotra_list_and_detail():
    items = E.parse_kotra_list(json.load(open(F / "kotra_list.json", encoding="utf-8")))
    assert len(items) == 3
    k = items[0]
    assert k["id"].startswith("kotra:") and k["date"] == "2026-11-17" and "&middot;" not in k["summary_raw"]
    assert "pNttSn=" in k["url"] and k["kbc"].endswith("무역관")
    assert "수출 제한" in E.parse_kotra_detail(fx("kotra_detail.html"))


def test_cand_id_stable():
    assert E.cand_id("meduza", "https://x/1") == E.cand_id("meduza", "https://x/1")
    assert E.cand_id("meduza", "https://x/1") != E.cand_id("meduza", "https://x/2")


# ── 선별 ────────────────────────────────────────────────────────
def _c(i, score, h=0):
    return {"id": f"s:{i}", "score": score, "published": datetime(2026, 11, 18, 12, tzinfo=KST) - timedelta(hours=h)}


def test_pick_caps_and_fills():
    ecfg = {"min_daily": 10, "max_daily": 15}
    cands = [_c(i, 4) for i in range(20)]
    chosen, rest = eu.pick(cands, 0, ecfg)
    assert len(chosen) == 15 and len(rest) == 5
    # 3점 이상이 4건뿐 → 2점으로 10건까지 채우고, 1점은 넣지 않음
    cands = [_c(i, 4) for i in range(4)] + [_c(10 + i, 2) for i in range(10)] + [_c(30 + i, 1) for i in range(5)]
    chosen, rest = eu.pick(cands, 0, ecfg)
    assert len(chosen) == 10 and all(c["score"] >= 2 for c in chosen)
    # 이미 13건 게재된 날(백업 실행)엔 2건만 더
    chosen, _ = eu.pick([_c(i, 5) for i in range(6)], 13, ecfg)
    assert len(chosen) == 2


# ── 파이프라인 ──────────────────────────────────────────────────
class FakeResp:
    def __init__(self, text):
        self.text = text


class FakeHttp:
    def __init__(self, cfg):
        self.s = None

    def get(self, url, **kw):
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        if "themoscowtimes.com/rss" in url:
            t = now.strftime("%a, %d %b %Y %H:%M:%S +0300")
            return FakeResp(f"""<rss><channel><item><title>Russia extends gasoline export ban</title>
<link>https://www.themoscowtimes.com/a1</link><pubDate>{t}</pubDate><description>Lead</description></item>
<item><title>Moscow theater premiere</title><link>https://www.themoscowtimes.com/a2</link><pubDate>{t}</pubDate></item>
</channel></rss>""")
        if "portnews.ru/news/" == url[-len("portnews.ru/news/"):]:
            d = now.date()
            months = list(E._RU_MONTHS)
            return FakeResp(f"""<div class='page_newsList'><div class='date_hr'><p>{d.day} {months[d.month - 1]} {d.year}</p></div>
<div class='nl_item'><p class='onlytime'>00:01</p><a href='/news/1/' title='Росморречфлот усилит северный завоз'><p>x</p></a>
<div class='nl_rubric_name'><a><p>судоходство</p></a></div></div></div>""")
        if url.endswith("/a1") or url.endswith("/a2"):
            return FakeResp("<div class='article__block--html'><p>" + "Body text about fuel exports and rail. " * 5 + "</p></div>")
        if "portnews.ru/news/1/" in url:
            return FakeResp(fx("portnews_article.html"))
        raise RuntimeError("blocked " + url)


class FakeClient:
    """_call_tool을 대신해 도구 이름별로 그럴듯한 결과를 돌려준다."""
    calls: list = []

    def __call__(self, client, cfg, tool, user, system=None, max_tokens=None):
        FakeClient.calls.append(tool["name"])
        ids = [l.split("]")[0].split("[")[-1] for l in user.splitlines() if l.startswith("[")]
        ids += [l.split('"')[1] for l in user.splitlines() if l.startswith("<article id=")]
        if tool["name"] == "submit_screening":
            return {"items": [{"id": i, "title_ko": f"한국어 제목 {i}", "score": 1 if "theater" in user.split(i)[1][:80] else 4}
                              for i in ids]}
        if tool["name"] == "submit_summaries":
            return {"items": [{"id": i, "title_ko": f"번역 제목 {i}", "summary": "요약입니다.", "why": "의미.",
                               "logistics": "물류 영향.", "insight": "해석.", "terms": [{"term": "TSR", "explanation": "철도"}],
                               "tags": ["러시아", "제재"], "relevance": 4} for i in ids]}
        if tool["name"] == "submit_brief":
            return {"headline": "헤드라인", "overview": "흐름", "top_ids": ids[:3], "top_reasons": ["a", "b", "c"],
                    "watch": ["w1"]}
        raise AssertionError(tool["name"])


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(eu, "EDIR", tmp_path / "eurasia")
    monkeypatch.setattr(eu, "Http", FakeHttp)
    cfg = json.loads(json.dumps(CFG))
    for k, v in cfg["eurasia"]["sources"].items():
        v["enabled"] = k in ("moscowtimes", "portnews")
    monkeypatch.setattr(eu, "load_config", lambda: cfg)
    monkeypatch.setattr(eu, "_client", lambda: object())
    monkeypatch.setattr(eu, "_call_tool", FakeClient())
    FakeClient.calls = []
    return tmp_path


def test_run_end_to_end(sandbox):
    day = eu.run("2026-11-18")
    arts = day["articles"]
    # 연극 기사(1점)는 빠지고, 2건 게재 (min_daily를 못 채워도 1점은 넣지 않음)
    assert {a["source"] for a in arts} == {"moscowtimes", "portnews"}
    assert len(arts) == 2 and len(day["screened"]) == 1
    a = next(a for a in arts if a["source"] == "portnews")
    assert a["title"].startswith("번역 제목") and a["orig_title"] == "Росморречфлот усилит северный завоз"
    assert a["lang"] == "ru" and a["stance"] and a["logistics"] and a["body"] == ""
    assert day["brief"]["top_source"] == "model" and len(day["brief"]["top"]) == 2
    assert FakeClient.calls == ["submit_screening", "submit_summaries", "submit_brief"]
    # 백업 실행: 새 기사 없음 → API 호출 없음
    FakeClient.calls = []
    eu.run("2026-11-18")
    assert FakeClient.calls == []


def test_run_offline(sandbox, monkeypatch):
    monkeypatch.setattr(eu, "_client", lambda: None)
    day = eu.run("2026-11-18")
    assert day["brief"]["offline"] and len(day["articles"]) == 3
    assert FakeClient.calls == []


def test_weekly_skips_when_not_monday(monkeypatch):
    cfg = json.loads(json.dumps(CFG))
    monkeypatch.setattr(euw, "load_config", lambda: cfg)
    monkeypatch.setattr(euw, "now_local", lambda c: datetime(2026, 11, 18, 19, tzinfo=KST))  # 수요일
    assert euw.run(only_monday=True) is None
