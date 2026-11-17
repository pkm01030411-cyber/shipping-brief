"""국제정세 태깅 파싱 · 집계 단위 테스트."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import geo  # noqa: E402


def test_norm_geo_flat_fields():
    g = geo.norm_geo({"geo_regions": ["유럽", "북미", "없는지역"], "geo_countries": ["us", "중국", "UK", "XX9"],
                      "geo_chokepoints": ["홍해", "Suez"], "geo_drivers": ["파업", "관세"],
                      "geo_impact": "-3", "geo_note": " 노트 "})
    assert g["regions"] == ["유럽", "북미"]
    assert g["countries"] == ["US", "CN", "GB"]
    assert g["chokepoints"] == ["홍해·바브엘만데브", "수에즈"]
    assert g["drivers"] == ["노사·파업", "관세·무역정책"]
    assert g["impact"] == -2           # 범위 밖은 잘라냄
    assert g["note"] == "노트"


def test_norm_geo_messy_shapes():
    # 문자열로 새어 들어온 배열, 중첩 geo 객체, 빈 값
    g = geo.norm_geo({"geo_regions": '["러시아", "북극"]', "geo_chokepoints": "북극항로, 북방항로",
                      "geo_impact": None})
    assert g["regions"] == ["러시아·CIS", "북극"]
    assert g["chokepoints"] == ["북극항로"]   # 별칭 중복 제거
    assert g["impact"] == 0
    g2 = geo.norm_geo({"geo": {"regions": ["중동"], "impact": 1}})
    assert g2["regions"] == ["중동"] and g2["impact"] == 1
    empty = geo.norm_geo({})
    assert empty == {"regions": [], "countries": [], "chokepoints": [], "drivers": [], "impact": 0, "note": ""}
    assert not geo.is_geo(empty) and not geo.is_geo({})


def _art(i, d, **g):
    base = {"regions": [], "countries": [], "chokepoints": [], "drivers": [], "impact": 0, "note": ""}
    base.update(g)
    return {"id": f"x:{i}", "title": f"t{i}", "url": f"u{i}", "source_name": "s",
            "published": f"{d}T09:00:00+09:00", "geo": base}


def test_aggregate_windows_and_tiles():
    today = date(2026, 11, 18)
    arts = [
        _art(1, "2026-11-17", regions=["중동"], chokepoints=["홍해·바브엘만데브"], drivers=["분쟁·안보"], impact=-2, countries=["YE"]),
        _art(2, "2026-11-16", regions=["중동"], chokepoints=["홍해·바브엘만데브"], drivers=["분쟁·안보"], impact=-1),
        _art(3, "2026-11-15", regions=["북미"], drivers=["노사·파업"], impact=-1, countries=["US"]),
        _art(4, "2026-11-05", regions=["북미"], chokepoints=["파나마"], impact=1),   # 7일 밖, 30일 안
        _art(5, "2026-11-17"),                                                       # 분석됐지만 정세 무관
        {"id": "x:6", "title": "t", "url": "u", "published": "2026-11-17T09:00:00+09:00", "geo": {}},  # 미분석
    ]
    g = geo.aggregate(arts, today)
    assert g["analyzed"] == 5 and g["geo_count"] == 4 and g["pending"] == 1
    p7, p30 = g["periods"][7], g["periods"][30]
    assert p7["count"] == 3 and p30["count"] == 4
    red = next(c for c in p7["chokepoints"] if c["name"] == "홍해·바브엘만데브")
    assert red["count"] == 2 and red["avg"] == -1.5 and red["cls"] == "imp-n2" and red["avg_label"] == "−1.5"
    assert [a["id"] for a in red["articles"]] == ["x:1", "x:2"]              # 최신순
    assert next(c for c in p7["chokepoints"] if c["name"] == "파나마")["count"] == 0
    assert next(c for c in p30["chokepoints"] if c["name"] == "파나마")["count"] == 1
    assert len(p7["chokepoints"]) == len(geo.CHOKEPOINTS)                    # 8개 카드 고정
    assert g["tiles"]["chokepoint"]["name"] == "홍해·바브엘만데브"
    assert g["tiles"]["region"]["name"] == "중동"                            # 2건 이상 중 최저 평균
    assert g["tiles"]["driver"]["name"] == "분쟁·안보"
    assert p7["low_sample"] is True
    assert {c["name"] for c in p30["countries"]} == {"YE", "US"}
    assert p30["countries"][0]["bar"] == 1.0
    # 데이터가 11/5부터라 직전 7일(11/5~11/11)은 비교 가능, 직전 30일은 불가
    assert red["arrow"] == "↑"
    assert p30["chokepoints"][0]["arrow"] == "–" and "데이터 없음" in p30["chokepoints"][0]["arrow_label"]


def test_aggregate_heat_and_trend():
    today = date(2026, 11, 18)  # 수요일 → 이번 주 월요일 11/16
    arts = [_art(1, "2026-11-16", regions=["유럽"], drivers=["노사·파업"], impact=-1),
            _art(2, "2026-11-10", regions=["유럽"], drivers=["노사·파업"], impact=1)]
    g = geo.aggregate(arts, today)
    assert len(g["heat"]["weeks"]) == 8 and g["heat"]["weeks"][-1]["key"] == "2026-W47"
    eu = next(r for r in g["heat"]["rows"] if r["name"] == "유럽")
    assert [c["count"] for c in eu["cells"]][-2:] == [1, 1] and eu["total"] == 2
    s = g["trend"]["series"][0]
    assert s["name"] == "노사·파업" and s["total"] == 2 and len(s["ma"]) == 60
    assert g["trend"]["days_of_data"] == 9
    svg = geo.trend_svg(g["trend"])
    assert svg.startswith("<svg") and "노사·파업" in svg and "<desc" in svg


def test_aggregate_empty():
    g = geo.aggregate([], date(2026, 11, 18))
    assert g["geo_count"] == 0 and g["line"] is None and g["heat"]["max"] == 0
    assert g["tiles"]["chokepoint"] is None and g["tiles"]["region"] is None
    assert geo.trend_svg(g["trend"]) == ""
    svg = geo.route_svg(g["periods"][30]["chokepoints"], g["periods"][7]["chokepoints"])
    assert svg.count('class="cp-dot p30"') == 8 and "부산" in svg


def test_impact_class_bounds():
    assert [geo.impact_class(v) for v in (None, -2, -1.25, -1, -0.4, 0, 0.39, 0.4, 1.25)] == \
        ["imp-none", "imp-n2", "imp-n2", "imp-n1", "imp-n1", "imp-0", "imp-0", "imp-p1", "imp-p2"]
    assert geo.fmt_impact(-1.5) == "−1.5" and geo.fmt_impact(0.5) == "+0.5" and geo.fmt_impact(None) == "–"
