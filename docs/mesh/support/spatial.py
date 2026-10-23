"""The core's spatial look-ups: a bucket grid of points (grid.rs), segments bucketed by the
cells their boxes touch (segs.rs), and which zone a point is in (zones.rs). Iteration order
is the core's, so that ties between equally near points resolve the same way."""

from __future__ import annotations

import math
from collections.abc import Callable

from .vec import P, cross, dist, dot, sub


class Grid:
    """Points in square cells (a counting sort by cell); ``within`` yields every point no
    further than r from q, with its squared distance, in the core's order."""

    def __init__(self, p: list[P], cell: float, keep: Callable[[int], bool] = lambda i: True):
        if p:
            x0 = min(q[0] for q in p)
            y0 = min(q[1] for q in p)
            x1 = max(q[0] for q in p)
            y1 = max(q[1] for q in p)
        else:
            x0 = y0 = x1 = y1 = 0.0
        self.x0, self.y0, self.cell = x0, y0, cell
        self.w = max(int(math.floor((x1 - x0) / cell)) + 1, 1)
        self.h = max(int(math.floor((y1 - y0) / cell)) + 1, 1)
        start = [0] * (self.w * self.h + 1)
        key = [None] * len(p)
        for i, q in enumerate(p):
            if keep(i):
                k = self._key(q)
                key[i] = k
                start[k + 1] += 1
        for k in range(self.w * self.h):
            start[k + 1] += start[k]
        fill = list(start)
        items = [0] * start[-1]
        for i, k in enumerate(key):
            if k is not None:
                items[fill[k]] = i
                fill[k] += 1
        self.start, self.items = start, items
        self.xs = [p[i][0] for i in items]
        self.ys = [p[i][1] for i in items]

    def _cx(self, x: float) -> int:
        return math.floor((x - self.x0) / self.cell)

    def _cy(self, y: float) -> int:
        return math.floor((y - self.y0) / self.cell)

    def _key(self, q: P) -> int:
        i = min(max(self._cx(q[0]), 0), self.w - 1)
        j = min(max(self._cy(q[1]), 0), self.h - 1)
        return j * self.w + i

    def within(self, q: P, r: float) -> list[tuple[int, float]]:
        i0, i1 = max(self._cx(q[0] - r), 0), min(self._cx(q[0] + r), self.w - 1)
        j0, j1 = max(self._cy(q[1] - r), 0), min(self._cy(q[1] + r), self.h - 1)
        out = []
        if i0 > i1 or j0 > j1:
            return out
        r2 = r * r
        qx, qy = q
        xs, ys, items, start, w = self.xs, self.ys, self.items, self.start, self.w
        for j in range(j0, j1 + 1):
            row = j * w
            for k in range(start[row + i0], start[row + i1 + 1]):
                dx, dy = xs[k] - qx, ys[k] - qy
                d = dx * dx + dy * dy
                if d <= r2:
                    out.append((items[k], d))
        return out

    def around(self, q: P, r: float) -> list[int]:
        """Each point in the cells within r of q (a superset of those within r)."""
        i0, i1 = max(self._cx(q[0] - r), 0), min(self._cx(q[0] + r), self.w - 1)
        j0, j1 = max(self._cy(q[1] - r), 0), min(self._cy(q[1] + r), self.h - 1)
        out = []
        for j in range(j0, j1 + 1):
            row = j * self.w
            for i in range(i0, i1 + 1):
                k = row + i
                out += self.items[self.start[k] : self.start[k + 1]]
        return out


class Segs:
    """Segments a-b bucketed by the grid cells their boxes touch."""

    def __init__(self, a: list[P], b: list[P], cell: float):
        self.a, self.b, self.cell = a, b, cell
        cells: dict[tuple[int, int], list[int]] = {}
        for i in range(len(a)):
            lo, hi = self._span(a[i], b[i])
            for x in range(lo[0], hi[0] + 1):
                for y in range(lo[1], hi[1] + 1):
                    cells.setdefault((x, y), []).append(i)
        self.cells = cells

    def _span(self, a: P, b: P) -> tuple[tuple[int, int], tuple[int, int]]:
        c = self.cell
        return (
            (math.floor(min(a[0], b[0]) / c), math.floor(min(a[1], b[1]) / c)),
            (math.floor(max(a[0], b[0]) / c), math.floor(max(a[1], b[1]) / c)),
        )

    def around(self, p: P, q: P) -> list[int]:
        """Each segment whose cells the box of p-q touches (maybe more than once)."""
        lo, hi = self._span(p, q)
        out = []
        for x in range(lo[0], hi[0] + 1):
            for y in range(lo[1], hi[1] + 1):
                v = self.cells.get((x, y))
                if v:
                    out += v
        return out

    def cast(self, p: P, d: P, reach: float) -> tuple[float, int] | None:
        """Where the ray from p along unit d first meets a segment within reach."""
        q = (p[0] + d[0] * reach, p[1] + d[1] * reach)
        best = None
        for j in self.around(p, q):
            t = ray_hit(p, d, self.a[j], self.b[j])
            if t is not None and t <= reach and (best is None or t < best[0]):
                best = (t, j)
        return best


def ray_hit(p: P, d: P, a: P, b: P) -> float | None:
    """How far along the ray from p along unit d it meets segment a-b (> 1e-9), if it does."""
    e = sub(b, a)
    den = cross(d, e)
    if abs(den) <= 1e-12:
        return None
    w = sub(a, p)
    t = cross(w, e) / den
    s = cross(w, d) / den
    return t if (t > 1e-9 and 0.0 <= s <= 1.0) else None


def crossing(p: list[P], which: list[int]) -> list[tuple[int, int]]:
    """The closed polyline's segments among ``which`` (segment i from vertex i to the next)
    that cross or touch another other than their neighbours: the pairs."""
    n = len(p)
    if n < 4:
        return []
    mean = 0.0
    for i in range(n):
        mean += dist(p[i], p[(i + 1) % n])
    mean /= n
    segs = Segs(list(p), [p[(i + 1) % n] for i in range(n)], max(4.0 * mean, 1e-6))
    out = []
    for i in which:
        a, b = p[i], p[(i + 1) % n]
        e = sub(b, a)
        length = math.sqrt(dot(e, e))
        if length <= 0.0:
            continue
        d = (e[0] / length, e[1] / length)
        found = set()
        for j in segs.around(a, b):
            gap = abs(i - j)
            if min(gap, n - gap) <= 1:
                continue
            t = ray_hit(a, d, segs.a[j], segs.b[j])
            if t is not None and t <= length:
                found.add((i, j))
        out += sorted(found)
    return out


class Zones:
    """Which zone a point is in: an even-odd ray test against the zones' rings, their edges
    bucketed by height."""

    def __init__(self, zones: list[list[list[P]]], row: float):
        edges = []
        for z, rings in enumerate(zones):
            for ring in rings:
                for k in range(len(ring)):
                    a, b = tuple(ring[k]), tuple(ring[(k + 1) % len(ring)])
                    if a != b:
                        edges.append((z, a, b))
        if edges:
            y0 = min(min(e[1][1], e[2][1]) for e in edges)
            y1 = max(max(e[1][1], e[2][1]) for e in edges)
        else:
            y0 = y1 = 0.0
        n = max(int(math.floor((y1 - y0) / row)) + 1, 1)
        rows: list[list] = [[] for _ in range(n)]
        for e in edges:
            lo = min(int(math.floor((min(e[1][1], e[2][1]) - y0) / row)), n - 1)
            hi = min(int(math.floor((max(e[1][1], e[2][1]) - y0) / row)), n - 1)
            for r in range(lo, hi + 1):
                rows[r].append(e)
        self.y0, self.row, self.rows, self.zones = y0, row, rows, len(zones)

    def of(self, q: P) -> int | None:
        """The zone q is in (the first holding it), or None."""
        r = math.floor((q[1] - self.y0) / self.row)
        if r < 0 or r >= len(self.rows):
            return None
        inside = [False] * self.zones
        for z, a, b in self.rows[r]:
            if (a[1] > q[1]) != (b[1] > q[1]):
                x = a[0] + (q[1] - a[1]) / (b[1] - a[1]) * (b[0] - a[0])
                if x > q[0]:
                    inside[z] = not inside[z]
        for z, i in enumerate(inside):
            if i:
                return z
        return None
