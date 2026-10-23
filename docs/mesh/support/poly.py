"""Polygons as rings of points (outline first, then holes; not closed), and the operations
the curve's graph needs (rust/core/src/poly.rs). ``intersection`` uses shapely (GEOS) where
the core uses the geo crate (i_overlay): the same shapes, but rounded differently in the
last bits and with their vertices in another order."""

from __future__ import annotations

import math

import shapely
from shapely.geometry import Polygon

from .vec import P, closest, dist

Rings = list[list[P]]


def ring_area(r: list[P]) -> float:
    n = len(r)
    s = 0.0
    for i in range(n):
        a, b = r[i], r[(i + 1) % n]
        s += a[0] * b[1] - b[0] * a[1]
    return s / 2.0


def area(p: Rings) -> float:
    s = 0.0
    for k, r in enumerate(p):
        a = abs(ring_area(r))
        s += a if k == 0 else -a
    return s


def centroid(p: Rings) -> P:
    cx = cy = a = 0.0
    for k, r in enumerate(p):
        sign = (1.0 if k == 0 else -1.0) * math.copysign(1.0, ring_area(r))
        n = len(r)
        for i in range(n):
            u, v = r[i], r[(i + 1) % n]
            c = (u[0] * v[1] - v[0] * u[1]) * sign
            cx += (u[0] + v[0]) * c
            cy += (u[1] + v[1]) * c
            a += c
    if abs(a) < 1e-18:
        return tuple(p[0][0])
    return (cx / (3.0 * a), cy / (3.0 * a))


def contains(p: Rings, q: P) -> bool:
    """Whether q is inside (even-odd over all rings)."""
    inside = False
    for r in p:
        n = len(r)
        for i in range(n):
            a, b = r[i], r[(i + 1) % n]
            if (a[1] > q[1]) != (b[1] > q[1]):
                x = a[0] + (q[1] - a[1]) / (b[1] - a[1]) * (b[0] - a[0])
                if x > q[0]:
                    inside = not inside
    return inside


def boundary_distance(p: Rings, q: P) -> float:
    d = math.inf
    for r in p:
        n = len(r)
        for i in range(n):
            d = min(d, dist(closest(q, r[i], r[(i + 1) % n])[0], q))
    return d


def distance(p: Rings, q: P) -> float:
    """The distance from q to the polygon (0 inside)."""
    return 0.0 if contains(p, q) else boundary_distance(p, q)


def bounds(p: Rings) -> tuple[float, float, float, float]:
    xs = [q[0] for r in p for q in r]
    ys = [q[1] for r in p for q in r]
    return (min(xs), min(ys), max(xs), max(ys))


def to_shapely(p: Rings) -> Polygon:
    return Polygon(p[0], p[1:])


def from_shapely(g: shapely.Geometry) -> list[Rings]:
    out = []
    for poly in shapely.get_parts(g):
        if poly.geom_type != "Polygon" or poly.is_empty:
            continue
        rings = [[tuple(q) for q in ring.coords[:-1]] for ring in (poly.exterior, *poly.interiors)]
        if len(rings[0]) >= 3:
            out.append(rings)
    return out


def intersection(a: Rings, b: Rings) -> list[Rings]:
    """The pieces of a within b."""
    return from_shapely(shapely.intersection(to_shapely(a), to_shapely(b)))


def rect(x0: float, y0: float, x1: float, y1: float) -> Rings:
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]


def inner_point(p: Rings) -> P:
    """A point inside: the centroid when inside, else the middle of the widest stretch
    inside across a row through the bounds."""
    c = centroid(p)
    if contains(p, c):
        return c
    b = bounds(p)
    for frac in (0.5, 0.25, 0.75, 0.125, 0.375, 0.625, 0.875):
        y = b[1] + (b[3] - b[1]) * frac
        xs = []
        for r in p:
            n = len(r)
            for i in range(n):
                u, v = r[i], r[(i + 1) % n]
                if (u[1] > y) != (v[1] > y):
                    xs.append(u[0] + (y - u[1]) / (v[1] - u[1]) * (v[0] - u[0]))
        xs.sort()
        pairs = [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]
        if pairs:
            best = None
            for w in pairs:  # (the last of the widest, as max_by)
                if best is None or w[1] - w[0] >= best[1] - best[0]:
                    best = w
            return ((best[0] + best[1]) / 2.0, y)
    return c
