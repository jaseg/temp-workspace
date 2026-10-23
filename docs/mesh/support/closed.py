"""Polylines, closed and open (rust/core/src/closed.rs): index arithmetic that wraps, and
the smoothing, curvature and resampling the relaxation uses."""

from __future__ import annotations

import math

from .vec import P, add, as_usize, dist, norm, scale, sub


def at(n: int, i: int) -> int:
    return i % n


def lap(p: list[P]) -> list[P]:
    """Each vertex's step to the middle of its neighbours (closed)."""
    n = len(p)
    return [sub(scale(add(p[(i - 1) % n], p[(i + 1) % n]), 0.5), p[i]) for i in range(n)]


def box_mean(v: list[float], w: int) -> list[float]:
    """The mean of v over -w..=w places round each (closed)."""
    n = len(v)
    out = []
    for i in range(n):
        s = 0.0
        for d in range(-w, w + 1):
            s = s + v[(i + d) % n]
        out.append(s / float(2 * w + 1))
    return out


def taubin(p: list[P], k: int, passes: int) -> list[P]:
    """Taubin smoothing (a shrinking step, then an inflating one) of the closed curve's first
    k vertices but the first and last."""
    p = list(p)
    for _ in range(passes):
        for f in (0.5, -0.53):
            d = lap(p)
            for i in range(1, max(k - 1, 0)):
                p[i] = add(p[i], scale(d[i], f))
    return p


def radius(p: list[P], reach: int) -> list[float]:
    """The signed radius of curvature at each vertex (positive turning left)."""
    n = len(p)
    out = []
    for i in range(n):
        a = sub(p[i], p[(i - reach) % n])
        b = sub(p[(i + reach) % n], p[i])
        turn = math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1])
        chord = (norm(a) + norm(b)) / 2.0
        out.append(chord / (1e-9 if abs(turn) < 1e-9 else turn))
    return out


def normals(p: list[P], reach: int) -> list[P]:
    """Unit normals (to the left) from the chord between each vertex's neighbours."""
    n = len(p)
    out = []
    for i in range(n):
        t = sub(p[(i + reach) % n], p[(i - reach) % n])
        length = max(norm(t), 1e-12)
        out.append((-t[1] / length, t[0] / length))
    return out


def arcs(p: list[P]) -> tuple[list[float], float]:
    """Each vertex's length run along the closed curve, and the whole length."""
    n = len(p)
    out, s = [], 0.0
    for i in range(n):
        out.append(s)
        s += dist(p[i], p[(i + 1) % n])
    return out, s


def split(p: list[P], longest: float) -> list[P]:
    """The open polyline with its segments longer than ``longest`` split evenly."""
    out = []
    for i in range(len(p) - 1):
        a, b = p[i], p[i + 1]
        parts = max(as_usize(math.ceil(dist(a, b) / longest)), 1)
        for j in range(parts):
            out.append(add(a, scale(sub(b, a), float(j) / float(parts))))
    if p:
        out.append(p[-1])
    return out


def respace(p: list[P], step: float) -> list[P]:
    """The open polyline at about ``step`` between vertices without moving any."""
    m = len(p)
    short = [0 < k < m - 1 and dist(p[k - 1], p[k]) + dist(p[k], p[k + 1]) < step for k in range(m)]
    kept = [p[k] for k in range(m) if not (short[k] and not (k > 0 and short[k - 1]))]
    return split(kept, 1.5 * step)


def spline(p: list[P], m: int) -> list[P]:
    """The closed polyline through p as a centripetal Catmull-Rom spline, m vertices per
    segment (the first of each at the segment's start)."""
    n = len(p)

    def knot(a: P, b: P) -> float:
        return math.sqrt(max(dist(a, b), 1e-9))

    def mix(a: P, ta: float, b: P, tb: float, t: float) -> P:
        return scale(add(scale(a, tb - t), scale(b, t - ta)), 1.0 / (tb - ta))

    out = []
    for i in range(n):
        p0, p1 = p[(i - 1) % n], p[i]
        p2, p3 = p[(i + 1) % n], p[(i + 2) % n]
        t1 = knot(p0, p1)
        t2 = t1 + knot(p1, p2)
        t3 = t2 + knot(p2, p3)
        for j in range(m):
            t = t1 + (t2 - t1) * float(j) / float(m)
            a1 = mix(p0, 0.0, p1, t1, t)
            a2 = mix(p1, t1, p2, t2, t)
            a3 = mix(p2, t2, p3, t3, t)
            b1 = mix(a1, 0.0, a2, t2, t)
            b2 = mix(a2, t1, a3, t3, t)
            out.append(mix(b1, t1, b2, t2, t))
    return out


def dilate(mask: list[bool], w: int) -> list[bool]:
    """mask grown w places either way (closed)."""
    n = len(mask)
    return [any(mask[(i + d) % n] for d in range(-w, w + 1)) for i in range(n)]
