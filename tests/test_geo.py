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
    m = geo.map_regions(None, [])
    assert m["selected"] is None and m["mapped"] == 0 and len(m["regions"]) == len(geo.MAP_REGIONS)


def test_impact_class_bounds():
    assert [geo.impact_class(v) for v in (None, -2, -1.25, -1, -0.4, 0, 0.39, 0.4, 1.25)] == \
        ["imp-none", "imp-n2", "imp-n2", "imp-n1", "imp-n1", "imp-0", "imp-0", "imp-p1", "imp-p2"]
    assert geo.fmt_impact(-1.5) == "−1.5" and geo.fmt_impact(0.5) == "+0.5" and geo.fmt_impact(None) == "–"


# ── 오늘의 세계 지도 ──────────────────────────────────────────
def test_map_multi_region_no_duplicates():
    a = _art(1, "2026-11-17", regions=["동아시아", "남아시아", "동아시아"], countries=["CN"], impact=-1)
    m = geo.map_regions("2026-11-17", [a])
    by = {r["name"]: r for r in m["regions"]}
    assert by["동아시아"]["count"] == 1 and by["남아시아"]["count"] == 1   # 각 지역에 한 번씩
    assert sum(r["count"] for r in m["regions"]) == 2 and m["mapped"] == 1
    assert by["동아시아"]["articles"][0]["anchor"] == "art-x-1"


def test_map_country_fallback_and_unmapped():
    arts = [_art(1, "2026-11-17", countries=["DE"]),           # 지역 없음 → 국가로 유럽
            _art(2, "2026-11-17", countries=["KR"]),           # 한국만 → 동아시아
            _art(3, "2026-11-17", regions=["북극"]),            # 북극 → 러시아·CIS
            _art(4, "2026-11-17", regions=["동남아"]),          # 태깅명 '동남아' → 동남아시아
            _art(5, "2026-11-17", countries=["AU"]),
            _art(6, "2026-11-17", drivers=["관세·무역정책"])]   # 지역도 국가도 없음
    m = geo.map_regions("2026-11-17", arts)
    by = {r["name"]: r["count"] for r in m["regions"]}
    assert by["유럽"] == 1 and by["동아시아"] == 1 and by["러시아·CIS"] == 1
    assert by["동남아시아"] == 1 and by["오세아니아"] == 1
    assert m["unmapped"] == 1 and m["mapped"] == 5


def test_map_sort_selected_and_dots():
    arts = [_art(1, "2026-11-17", regions=["유럽"], impact=0),
            _art(2, "2026-11-17", regions=["유럽"], impact=-2),
            _art(3, "2026-11-17", regions=["중동"], impact=1)]
    m = geo.map_regions("2026-11-17", arts)
    eu = next(r for r in m["regions"] if r["name"] == "유럽")
    assert [a["id"] for a in eu["articles"]] == ["x:2", "x:1"]        # |impact| 큰 순
    assert m["selected"] == geo.slug("유럽") and eu["avg"] == -1.0
    assert 18 <= eu["d"] <= 44 and next(r for r in m["regions"] if r["name"] == "북미")["d"] == 0
    svg = geo.world_map_svg(m, "M0 0l1 1z")
    # 0건 지역은 이름만 옅게, 점(버튼)은 템플릿이 건수 있는 지역에만 만든다
    assert svg.count('class="region-off"') == len(geo.MAP_REGIONS) - 2
    assert "유럽 2건" in svg and "<desc" in svg


def test_projection_bounds():
    W, H = geo.MAP_W, geo.MAP_H
    for lon, lat in [(0, 0), (180, 0), (-180, 0), (0, geo.LAT_TOP), (0, geo.LAT_BOTTOM)]:
        x, y = geo._xy(lon, lat)
        assert 0 <= x <= W and 0 <= y <= H
    assert geo._xy(-180, 0)[0] == 0 and geo._xy(180, 0)[0] == W
    for name, (lon, lat) in geo.MAP_POS.items():  # 모든 대표 지역 점이 지도 안
        x, y = geo._xy(lon, lat)
        assert 0 < x < W and 0 < y < H, name
    assert set(geo.MAP_POS) == set(geo.MAP_REGIONS)
    assert set(geo.COUNTRY_KO) <= set(geo.COUNTRY_TO_MAP)   # 국가 표가 모든 코드를 커버
