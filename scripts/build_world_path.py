"""world-atlas@2 의 land-110m.json(TopoJSON) → static/world-land.path.txt (SVG path d 문자열).

개발 시점에 한 번만 실행해서 결과를 커밋한다. 사이트는 런타임에 지도 데이터를 받지 않는다.

  cd /tmp && npm pack world-atlas@2 && tar -xzf world-atlas-*.tgz
  python scripts/build_world_path.py /tmp/package/land-110m.json

투영은 src/geo.py 의 _xy 를 그대로 써서 점 좌표와 지도가 반드시 일치하게 한다.
출처: Natural Earth (public domain) via world-atlas (ISC).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.geo import LAT_BOTTOM, _xy  # noqa: E402


def decode_arcs(topo: dict) -> list[list[tuple[float, float]]]:
    """델타 인코딩된 TopoJSON arc → 경위도 좌표 목록."""
    (sx, sy), (tx, ty) = topo["transform"]["scale"], topo["transform"]["translate"]
    out = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        out.append(pts)
    return out


def ring_coords(ring: list[int], arcs: list[list[tuple[float, float]]]) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for idx in ring:
        seg = arcs[idx] if idx >= 0 else list(reversed(arcs[~idx]))
        pts.extend(seg if not pts else seg[1:])  # 이어지는 arc의 첫 점은 앞 arc의 끝점과 같다
    return pts


def polygons(obj: dict):
    if obj["type"] == "GeometryCollection":
        for g in obj["geometries"]:
            yield from polygons(g)
    elif obj["type"] == "Polygon":
        yield obj["arcs"]
    elif obj["type"] == "MultiPolygon":
        yield from obj["arcs"]


def build(src: Path) -> str:
    topo = json.loads(src.read_text())
    arcs = decode_arcs(topo)
    parts = []
    kept = dropped = 0
    for poly in polygons(topo["objects"]["land"]):
        for ring in poly:
            pts = ring_coords(ring, arcs)
            if max(lat for _, lat in pts) < LAT_BOTTOM:  # 남극 제거
                dropped += 1
                continue
            # 180도 경선을 건너는 고리(추코트카, 피지 등): 경도를 연속으로 펴고, 밖으로 나간 쪽은
            # 360도 옮긴 사본을 하나 더 그린다. 화면 밖 부분은 viewBox가 잘라낸다.
            unwrapped = [pts[0]]
            for lon, lat in pts[1:]:
                prev = unwrapped[-1][0]
                while lon - prev > 180:
                    lon -= 360
                while lon - prev < -180:
                    lon += 360
                unwrapped.append((lon, lat))
            variants = [unwrapped]
            if max(l for l, _ in unwrapped) > 180:
                variants.append([(l - 360, t) for l, t in unwrapped])
            if min(l for l, _ in unwrapped) < -180:
                variants.append([(l + 360, t) for l, t in unwrapped])
            for v in variants:
                part = ring_path(v)
                if part:
                    parts.append(part)
                    kept += 1
    print(f"rings kept {kept}, dropped(antarctica) {dropped}", file=sys.stderr)
    return "".join(parts)


def ring_path(pts: list[tuple[float, float]]) -> str | None:
    xy = []
    for lon, lat in pts:
        x, y = _xy(lon, max(lat, LAT_BOTTOM - 2))  # 남쪽 끝은 살짝 넘겨서 자름 (viewBox가 가림)
        p = (round(x, 1), round(y, 1))
        if not xy or p != xy[-1]:  # 반올림 후 같은 점은 생략
            xy.append(p)
    if len(xy) < 3:
        return None
    # 첫 점은 절대좌표, 이후는 상대좌표(l)로 써서 크기를 줄인다
    rel = [f"{round(x1 - x0, 1):g} {round(y1 - y0, 1):g}" for (x0, y0), (x1, y1) in zip(xy, xy[1:])]
    return f"M{xy[0][0]:g} {xy[0][1]:g}l" + " ".join(rel) + "z"



if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/build_world_path.py path/to/land-110m.json")
    d = build(Path(sys.argv[1]))
    out = ROOT / "static" / "world-land.path.txt"
    out.write_text(d)
    print(f"wrote {out} ({len(d) / 1024:.1f} KB)", file=sys.stderr)
