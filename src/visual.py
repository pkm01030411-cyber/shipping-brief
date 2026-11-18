"""리뉴얼(해도+야경 / 에디토리얼) 화면용 보조 로직.

- 기사 → 일러스트 매칭 (static/img/*.webp)
- 본문 속 용어에 하이라이트 버튼 달기
- 시작 페이지 항로 선, 항만 좌표
- 기사별 위치 지도 핀
- 지도 배경 SVG (야경 / 크림 해도)

투영은 geo._xy 를 그대로 써서 기존 정세 대시보드 지도와 좌표가 일치한다.
"""
from __future__ import annotations

import re
from html import escape

from markupsafe import Markup

from . import geo as geo_mod
from .common import STATIC_DIR

IMG_DIR = STATIC_DIR / "img"

# ── 일러스트 ─────────────────────────────────────────────────────
# pos: 카드 띠(가로로 긴 틀)에 맞출 때 보일 부분 (object-position)
ILLUSTRATIONS = {
    "container-ship": {"alt": "밤바다를 지나는 초대형 컨테이너선", "w": 1600, "h": 238, "pos": "33% 60%"},
    "sts-crane": {"alt": "야간 컨테이너 터미널의 안벽 갠트리크레인이 컨테이너를 들어 올리는 모습", "w": 856, "h": 665, "pos": "50% 40%"},
    "yard": {"alt": "조명이 켜진 컨테이너 야적장과 RTG 크레인", "w": 1220, "h": 385, "pos": "50% 55%"},
    "bulk-carrier": {"alt": "갑판 크레인 네 기를 단 벌크선", "w": 1600, "h": 257, "pos": "12% 60%"},
    "tanker": {"alt": "갑판에 파이프라인이 이어진 원유 탱커", "w": 1600, "h": 239, "pos": "92% 60%"},
    "lng-carrier": {"alt": "화물 탱크가 솟은 LNG 운반선", "w": 1600, "h": 264, "pos": "62% 55%"},
    "tugboat": {"alt": "선수에 방현재를 두른 예선", "w": 850, "h": 420, "pos": "50% 55%"},
    "lost-ship": {"alt": "별이 뜬 밤바다에 홀로 떠 있는 컨테이너선", "w": 1040, "h": 600, "pos": "50% 70%"},
    "teu": {"alt": "같은 축척으로 그린 20피트와 40피트 컨테이너", "w": 1160, "h": 640, "pos": "50% 50%"},
    "cross-section": {"alt": "컨테이너선 단면: 선창 안과 갑판 위에 쌓인 컨테이너", "w": 930, "h": 680, "pos": "50% 50%"},
}

_RULES = [  # (정규식, 일러스트) — 위에서부터 먼저 맞는 것
    (r"LNG|LPG|가스선|액화", "lng-carrier"),
    (r"탱커|유조선|원유|VLCC|석유제품|정유", "tanker"),
    (r"벌크|BDI|건화물|철광석|석탄|곡물|케이프사이즈|파나막스|수프라막스", "bulk-carrier"),
    (r"예선|터그|도선|예인", "tugboat"),
    (r"항만|부두|터미널|안벽|크레인|하역|선석|항만공사|BPA|IPA|UPA", "sts-crane"),
    (r"물류센터|창고|풀필먼트|포워더|포워딩|3PL|내륙|철도|트럭|항공화물|CY|CFS|야적", "yard"),
]
_CATEGORY = {"항만": "sts-crane", "물류": "yard", "항공": "yard", "무역": "container-ship",
             "해운": "container-ship", "조선": "container-ship"}


def available() -> set[str]:
    return {k for k in ILLUSTRATIONS if (IMG_DIR / f"{k}.webp").exists()}


def pick_illustration(a: dict, have: set[str]) -> dict | None:
    hay = " ".join([a.get("title", ""), " ".join(a.get("tags", []) or []), a.get("subtitle", "")])
    name = None
    for pat, ill in _RULES:
        if re.search(pat, hay, re.I):
            name = ill
            break
    if not name:
        name = _CATEGORY.get(a.get("category", ""), "container-ship")
    if name not in have:
        name = "container-ship" if "container-ship" in have else None
    if not name:
        return None
    return {"name": name, **ILLUSTRATIONS[name]}


# 용어 해설 도해: 이 용어가 나오면 팝업·사이드바에 그림을 함께
DIAGRAMS = [
    (r"TEU|FEU|컨테이너", "teu"),
    (r"선복|선창|적재|하역|해치|래싱|적부", "cross-section"),
]


def term_diagram(term: str, have: set[str]) -> str | None:
    for pat, name in DIAGRAMS:
        if re.search(pat, term, re.I) and name in have:
            return name
    return None


# ── 용어 하이라이트 ───────────────────────────────────────────────
def term_key(term: str) -> str:
    """'카페리(Car Ferry)' → '카페리'"""
    return re.split(r"[（(]", term, 1)[0].strip()


def termify(a: dict, fields=("summary", "why", "insight")) -> dict[str, Markup]:
    """각 용어의 첫 등장(필드 순서대로)에 <button class="term">을 단다. 나머지 글자는 이스케이프."""
    terms = a.get("terms") or []
    used: set[int] = set()
    out: dict[str, Markup] = {}
    for f in fields:
        text = escape(a.get(f) or "")
        marks: dict[str, str] = {}
        for i, t in enumerate(terms):
            if i in used:
                continue
            k = term_key(t.get("term", ""))
            if len(k) < 2:
                continue
            pat = re.compile(re.escape(escape(k)), re.I if k.isascii() else 0)
            m = pat.search(text)
            if not m:
                continue
            token = f"\x00{i}\x00"
            marks[token] = (f'<button type="button" class="term" data-term="{i}" aria-expanded="false" '
                            f'aria-controls="term-pop">{m.group(0)}</button>')
            text = text[:m.start()] + token + text[m.end():]
            used.add(i)
        for token, html in marks.items():
            text = text.replace(token, html)
        out[f + "_html"] = Markup(text)
    out["terms_unplaced"] = [i for i in range(len(terms)) if i not in used]
    return out


# ── 항만 · 항로 (시작 페이지) ──────────────────────────────────────
PORTS = [  # (이름, 영문, 경도, 위도)
    ("부산", "BUSAN", 129.04, 35.10), ("상하이", "SHANGHAI", 121.50, 31.23),
    ("싱가포르", "SINGAPORE", 103.82, 1.26), ("콜롬보", "COLOMBO", 79.85, 6.93),
    ("수에즈", "SUEZ", 32.55, 29.97), ("로테르담", "ROTTERDAM", 4.40, 51.90),
    ("LA·롱비치", "LOS ANGELES", -118.25, 33.73), ("파나마", "PANAMA", -79.60, 9.00),
    ("뉴욕", "NEW YORK", -74.00, 40.70), ("희망봉", "CAPE", 18.47, -34.36),
    ("블라디보스토크", "VLADIVOSTOK", 131.88, 43.12),
]
_ROUTES = {
    # 아시아–유럽 (수에즈 경유)
    "main": [(129.04, 35.1), (125, 32), (121.5, 31.2), (120.5, 25), (114, 15), (108, 7), (103.8, 1.26), (98, 5.5),
             (88, 6), (79.85, 6.93), (65, 11), (51, 12.5), (43.4, 12.6), (39, 19), (34.5, 27.5), (32.55, 29.97),
             (30, 32.5), (20, 34.5), (10, 37.5), (-5.6, 35.95), (-9.6, 39.5), (-9, 44), (-5, 48.5), (1.5, 50.8),
             (4.4, 51.9)],
    # 희망봉 우회
    "detour": [(79.85, 6.93), (62, -8), (45, -26), (31, -33.5), (18.47, -36.5), (5, -20), (-12, 2), (-18, 15),
               (-16, 27), (-9.6, 35.5), (-5.6, 35.95)],
    # 태평양 (날짜변경선에서 끊어 그린다)
    "pacific_w": [(129.04, 35.1), (140, 36), (160, 40), (180, 42)],
    "pacific_e": [(-180, 42), (-160, 41), (-140, 37), (-118.25, 33.73)],
    # 파나마 → 미 동안
    "panama": [(-118.25, 33.73), (-110, 22), (-95, 13), (-79.6, 7.5), (-79.6, 9.0), (-77, 13), (-75, 22),
               (-74, 32), (-74, 40.7)],
}


def _pct(lon: float, lat: float) -> tuple[float, float]:
    x, y = geo_mod._xy(lon, lat)
    return round(x / geo_mod.MAP_W * 100, 2), round(y / geo_mod.MAP_H * 100, 2)


def _path(points: list[tuple[float, float]]) -> str:
    xy = [geo_mod._xy(lon, lat) for lon, lat in points]
    d = f"M{xy[0][0]} {xy[0][1]}"
    # 꺾이는 점마다 살짝 둥글게 (2차 곡선)
    for i in range(1, len(xy) - 1):
        (x0, y0), (x1, y1), (x2, y2) = xy[i - 1], xy[i], xy[i + 1]
        mx, my = round((x1 + x2) / 2, 1), round((y1 + y2) / 2, 1)
        d += f" Q{x1} {y1} {mx} {my}"
    d += f" L{xy[-1][0]} {xy[-1][1]}"
    return d


def chart_routes() -> dict:
    ports = []
    for name, en, lon, lat in PORTS:
        x, y = geo_mod._xy(lon, lat)
        ns = "N" if lat >= 0 else "S"
        ew = "E" if lon >= 0 else "W"
        ports.append({"name": name, "en": en, "x": x, "y": y,
                      "coord": f"{abs(lat):.0f}°{ns} {abs(lon):.0f}°{ew}"})
    return {"w": geo_mod.MAP_W, "h": geo_mod.MAP_H, "ports": ports,
            "routes": [{"id": k, "d": _path(v)} for k, v in _ROUTES.items()]}


# ── 기사 위치 지도 ────────────────────────────────────────────────
CHOKEPOINT_POS = {"홍해·바브엘만데브": (40.5, 16.5), "수에즈": (32.5, 30.5), "파나마": (-79.6, 9.0),
                  "호르무즈": (56.4, 26.4), "말라카": (100.5, 3.5), "흑해·보스포루스": (31, 43),
                  "북극항로": (100, 76), "대만해협": (119.6, 24.2)}


def locator_pins(a: dict) -> list[dict]:
    g = a.get("geo") or {}
    pins, seen = [], set()
    for c in g.get("chokepoints", []) or []:
        if c in CHOKEPOINT_POS and c not in seen:
            seen.add(c)
            px, py = _pct(*CHOKEPOINT_POS[c])
            pins.append({"name": c, "px": px, "py": py, "kind": "cp"})
    for r in geo_mod.map_regions_of(a):
        if r not in seen:
            seen.add(r)
            px, py = _pct(*geo_mod.MAP_POS[r])
            pins.append({"name": r, "px": px, "py": py, "kind": "region"})
    return pins


def region_slugs(a: dict) -> str:
    return " ".join(geo_mod.slug(r) for r in geo_mod.map_regions_of(a))


# ── 지도 배경 SVG ────────────────────────────────────────────────
def world_svg(land_path: str, land: str, stroke: str, grid: str) -> str:
    w, h = geo_mod.MAP_W, geo_mod.MAP_H
    lines = []
    for lon in range(-150, 180, 30):
        x = geo_mod._xy(lon, 0)[0]
        lines.append(f'<line x1="{x}" x2="{x}" y1="0" y2="{h}"/>')
    for lat in (60, 30, 0, -30):
        y = geo_mod._xy(0, lat)[1]
        lines.append(f'<line x1="0" x2="{w}" y1="{y}" y2="{y}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet">'
            f'<g stroke="{grid}" stroke-width="0.6" fill="none">{"".join(lines)}</g>'
            f'<path d="{land_path}" fill="{land}" stroke="{stroke}" stroke-width="0.6" stroke-linejoin="round"/></svg>')
