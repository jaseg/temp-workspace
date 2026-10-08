"""Test helpers: a tiny parser for the SVG path subset we emit (M, L, A, Z)."""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

from yanartas_pillowbox.geometry import Arc, Line, Segment, arc_through
from yanartas_pillowbox.svg import SVG_NS

TOKEN = re.compile(r"[MLAZ]|-?\d+(?:\.\d+)?")


def parse_path(d: str) -> tuple[list[str], list[Segment]]:
    """Return (command letters, segments in absolute user units)."""
    toks = TOKEN.findall(d.replace(",", " "))
    cmds: list[str] = []
    segs: list[Segment] = []
    i = 0
    cur = start = (0.0, 0.0)
    while i < len(toks):
        c = toks[i]
        cmds.append(c)
        i += 1
        if c == "M":
            cur = start = (float(toks[i]), float(toks[i + 1]))
            i += 2
        elif c == "L":
            p = (float(toks[i]), float(toks[i + 1]))
            segs.append(Line(cur, p))
            cur = p
            i += 2
        elif c == "A":
            r = float(toks[i])
            large, sweep = int(toks[i + 3]), int(toks[i + 4])
            p = (float(toks[i + 5]), float(toks[i + 6]))
            segs.append(_svg_arc(cur, p, r, bool(large), bool(sweep)))
            cur = p
            i += 7
        elif c == "Z":
            if math.dist(cur, start) > 0:
                segs.append(Line(cur, start))
            cur = start
        else:  # pragma: no cover
            raise ValueError(c)
    return cmds, segs


def _svg_arc(
    p0: tuple[float, float], p1: tuple[float, float], r: float, large: bool, sweep: bool
) -> Arc:
    mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
    half = math.dist(p0, p1) / 2
    h = math.sqrt(max(0.0, r * r - half * half))
    d = ((p1[0] - p0[0]) / (2 * half), (p1[1] - p0[1]) / (2 * half))
    n = (-d[1], d[0])
    # SVG: centre is on the side such that (large != sweep) picks the "+n" centre.
    sign = 1 if large != sweep else -1
    c = (mid[0] + sign * n[0] * h, mid[1] + sign * n[1] * h)
    a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
    a1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
    delta = (a1 - a0) % (2 * math.pi) if sweep else -((a0 - a1) % (2 * math.pi))
    via_a = a0 + delta / 2
    via = (c[0] + r * math.cos(via_a), c[1] + r * math.sin(via_a))
    return arc_through(c, r, p0, p1, via)


def loop_area(segs) -> float:
    """Exact signed area enclosed by a closed loop of lines and circular arcs (Green)."""
    twice = 0.0
    for s in segs:
        (x0, y0), (x1, y1) = s.start, s.end
        if isinstance(s, Line):
            twice += x0 * y1 - x1 * y0
        else:
            cx, cy = s.center
            twice += cx * (y1 - y0) - cy * (x1 - x0) + s.radius**2 * s.sweep
    return twice / 2


def svg_elements(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def q(tag: str) -> str:
    return f"{{{SVG_NS}}}{tag}"


def polyline(segs: list[Segment], steps: int = 48) -> list[tuple[float, float]]:
    pts = [segs[0].start]
    for s in segs:
        pts.extend(s.sample(steps)[1:])
    return pts


def segments_intersect(a, b, c, d, eps: float = 1e-9) -> bool:
    """Proper or touching intersection of segments ab and cd."""

    def orient(p, q_, r):
        return (q_[0] - p[0]) * (r[1] - p[1]) - (q_[1] - p[1]) * (r[0] - p[0])

    def on_seg(p, q_, r):
        return (
            min(p[0], r[0]) - eps <= q_[0] <= max(p[0], r[0]) + eps
            and min(p[1], r[1]) - eps <= q_[1] <= max(p[1], r[1]) + eps
        )

    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and (
        (o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)
    ):
        return True
    return any(
        abs(o) <= eps and on_seg(p, q_, r)
        for o, p, q_, r in ((o1, a, c, b), (o2, a, d, b), (o3, c, a, d), (o4, c, b, d))
    )


def self_intersections(pts: list[tuple[float, float]]) -> list[tuple[int, int]]:
    """Pairs of non-adjacent edges of the closed polygon ``pts`` that intersect."""
    if math.dist(pts[0], pts[-1]) < 1e-9:
        pts = pts[:-1]
    n = len(pts)
    edges = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
    hits = []
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if segments_intersect(*edges[i], *edges[j]):
                hits.append((i, j))
    return hits
