"""Security meshes: what the layout algorithms share.

Two algorithms lay out a mesh, each in its own module:

- ``kimesh``: KiMesh's tiles on a square grid, walked by a randomized spanning tree;
- ``sfc``: a closed space-filling curve after Bedel et al. (2022), offset into the traces.

Both take the area to cover (the *mask*, a shapely geometry) and the *exit cell*: a square
``2 n`` trace pitches wide at ``exit_corner`` (its corner with the smallest x and y) whose
side ``exit_side`` is open. They return a ``Mesh``: ``n`` nets, each one polyline whose two
ends lie on that side, at the pitch, mirrored about its middle (net 1 outermost).

Coordinates: x right, y down (as the pattern); side bits 0b0001 +x, 0b0010 +y, 0b0100 -x,
0b1000 -y.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

Point = tuple[float, float]
# A piece of a trace drawn in lines and arcs: start, an arc's halfway point (a line: None), end.
Piece = tuple[Point, Point | None, Point]
CHUNK = 50_000  # queries at a time (bounds the memory a query takes)
PAIRS = 2_000_000  # ray-segment pairs at a time (bounds the memory a ray cast takes)

RIGHT, DOWN, LEFT, UP = 0b0001, 0b0010, 0b0100, 0b1000
STEP = {RIGHT: (1, 0), DOWN: (0, 1), LEFT: (-1, 0), UP: (0, -1)}
OPPOSITE = {RIGHT: LEFT, DOWN: UP, LEFT: RIGHT, UP: DOWN}


class MeshError(ValueError):
    """The mesh cannot be laid out (e.g. no room for its exit cell)."""


@dataclass(frozen=True)
class Mesh:
    """A generated mesh: one polyline per net, from its end at the exit cell's open side
    round the area back to its other end there (``ends``: the two points)."""

    traces: tuple[tuple[Point, ...], ...]
    cell: float  # the exit cell's size (KiMesh: every cell's)
    cells: int  # cells covered (KiMesh: grid cells; sfc: the curve's graph cells)
    unreached: int  # parts the mesh could not reach (KiMesh: grid cells; sfc: regions)
    origin: Point = (0.0, 0.0)  # the exit cell's corner: the grid's alignment
    algorithm: str = "kimesh"  # what laid it out: "kimesh" or "sfc"
    # each net as lines and arcs (``traces`` then: these drawn as a polyline), if fitted
    arcs: tuple[tuple[Piece, ...], ...] | None = None
    # the partitions' traces in turn (how many each; one partition: all), and their areas
    groups: tuple[int, ...] = ()
    parts: tuple = ()  # (shapely polygons)

    @property
    def pairs(self) -> list[tuple[int, int]]:
        """The neighbouring traces of each partition (as differential pairs)."""
        sizes = self.groups or (len(self.traces),)
        out, first = [], 0
        for size in sizes:
            out += [(i, i + 1) for i in range(first, first + size - 1)]
            first += size
        return out

    @property
    def ends(self) -> tuple[tuple[Point, Point], ...]:
        return tuple((t[0], t[-1]) for t in self.traces)


def sample_arcs(pieces: Sequence[Piece], tol: float) -> tuple[Point, ...]:
    """The pieces as a polyline: each arc's chords within ``tol`` of it."""
    out: list[Point] = [pieces[0][0]] if pieces else []
    for a, m, b in pieces:
        if m is not None:
            # (the circle through the three points; the way round from a through m to b)
            (ax, ay), (mx, my), (bx, by) = a, m, b
            d = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
            if abs(d) > 1e-12:
                a2, m2, b2 = ax * ax + ay * ay, mx * mx + my * my, bx * bx + by * by
                ox = (a2 * (my - by) + m2 * (by - ay) + b2 * (ay - my)) / d
                oy = (a2 * (bx - mx) + m2 * (ax - bx) + b2 * (mx - ax)) / d
                r = math.dist((ox, oy), a)
                t0 = math.atan2(ay - oy, ax - ox)
                tm = (math.atan2(my - oy, mx - ox) - t0) % math.tau
                sweep = (math.atan2(by - oy, bx - ox) - t0) % math.tau
                if tm > sweep:
                    sweep -= math.tau
                step = 2 * math.acos(max(1 - tol / r, -1.0))
                k = max(2, math.ceil(abs(sweep) / step))
                out += [
                    (ox + r * math.cos(t0 + sweep * i / k), oy + r * math.sin(t0 + sweep * i / k))
                    for i in range(1, k)
                ]
        out.append(b)
    return tuple(out)


def straighten(pts: list[Point]) -> tuple[Point, ...]:
    """The polyline without repeated points and points where it runs straight on."""
    out: list[Point] = []
    for p in pts:
        if out and math.dist(out[-1], p) < 1e-9:
            continue
        if len(out) >= 2:
            (ax, ay), (bx, by) = out[-2], out[-1]
            if abs((bx - ax) * (p[1] - by) - (by - ay) * (p[0] - bx)) < 1e-12 and (
                (bx - ax) * (p[0] - bx) + (by - ay) * (p[1] - by) > 0
            ):
                out[-1] = p
                continue
        out.append(p)
    return tuple(out)


# ----------------------------------------------------------------------------- geometry
def resample(p: np.ndarray, step: float) -> np.ndarray:
    """The open polyline at an even step along it (its ends kept)."""
    seg = np.hypot(*np.diff(p, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(1, round(s[-1] / step))
    t = np.linspace(0.0, s[-1], n + 1)
    return np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], 1)


class Grid:
    """Points bucketed on a square grid, for nearest-point queries."""

    def __init__(self, p: np.ndarray, size: float) -> None:
        self.p, self.size = p, size
        keys = self._keys(np.floor(p / size).astype(np.int64))
        self.order = np.argsort(keys, kind="stable")
        self.keys = keys[self.order]

    @staticmethod
    def _keys(c: np.ndarray) -> np.ndarray:
        return c[:, 0] * 1_000_003 + c[:, 1]

    def nearest(
        self, q: np.ndarray, ok: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None
    ) -> np.ndarray:
        """For each query, the nearest point in its cell or the eight around it (for which
        ``ok(query indices, point indices)`` holds); -1 where there is none."""
        out = np.full(len(q), -1)
        for k in range(0, len(q), CHUNK):  # (bounded memory, however many)
            out[k : k + CHUNK] = self._nearest(
                q[k : k + CHUNK], None if ok is None else (lambda qi, pi, k=k: ok(qi + k, pi))
            )
        return out

    def within(self, q: np.ndarray, r: float) -> tuple[np.ndarray, np.ndarray]:
        """Every pair of a query and a point no further than ``r`` (at most the grid's
        size) from it: the queries' indices and the points'."""
        qs, ps = [], []
        for k in range(0, len(q), CHUNK):
            part = q[k : k + CHUNK]
            c = np.floor(part / self.size).astype(np.int64)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    keys = self._keys(c + np.array([dx, dy]))
                    lo = np.searchsorted(self.keys, keys, "left")
                    count = np.searchsorted(self.keys, keys, "right") - lo
                    has = np.nonzero(count)[0]
                    if not len(has):
                        continue
                    cnt = count[has]
                    qi = np.repeat(has, cnt)
                    first = np.concatenate([[0], np.cumsum(cnt)[:-1]])
                    pi = self.order[np.repeat(lo[has] - first, cnt) + np.arange(len(qi))]
                    v = part[qi] - self.p[pi]
                    near = v[:, 0] ** 2 + v[:, 1] ** 2 <= r * r
                    qs.append(qi[near] + k)
                    ps.append(pi[near])
        if not qs:
            return np.zeros(0, int), np.zeros(0, int)
        return np.concatenate(qs), np.concatenate(ps)

    def _nearest(
        self, q: np.ndarray, ok: Callable[[np.ndarray, np.ndarray], np.ndarray] | None
    ) -> np.ndarray:
        c = np.floor(q / self.size).astype(np.int64)
        best = np.full(len(q), np.inf)
        out = np.full(len(q), -1)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                keys = self._keys(c + np.array([dx, dy]))
                lo = np.searchsorted(self.keys, keys, "left")
                count = np.searchsorted(self.keys, keys, "right") - lo
                has = np.nonzero(count)[0]
                if not len(has):
                    continue
                cnt = count[has]
                qi = np.repeat(has, cnt)  # (grouped by query, in order)
                first = np.concatenate([[0], np.cumsum(cnt)[:-1]])
                pi = self.order[np.repeat(lo[has] - first, cnt) + np.arange(len(qi))]
                d2 = np.sum((q[qi] - self.p[pi]) ** 2, axis=1)
                if ok is not None:
                    d2[~ok(qi, pi)] = np.inf
                low = np.minimum.reduceat(d2, first)
                at = d2 == np.repeat(low, cnt)
                take, pick = np.unique(qi[at], return_index=True)
                better = low[np.searchsorted(has, take)] < best[take]
                take = take[better]
                best[take] = low[np.searchsorted(has, take)]
                out[take] = pi[at][pick[better]]
        return out


class Rays:
    """Ray casting against segments, bucketed on a grid as wide as the rays are long."""

    def __init__(self, a: np.ndarray, b: np.ndarray, reach: float) -> None:
        self.a, self.b, self.reach = a, b, reach
        cells, ids = self._cells(a, b)
        order = np.argsort(cells, kind="stable")
        self.keys, self.ids = cells[order], ids[order]

    def _cells(self, a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """The grid cells each segment's box touches (it spans at most two each way)."""
        lo = np.floor(np.minimum(a, b) / self.reach).astype(np.int64)
        hi = np.floor(np.maximum(a, b) / self.reach).astype(np.int64)
        keys, ids = [], []
        n = np.arange(len(a))
        for dx in (0, 1):
            for dy in (0, 1):
                ok = (lo[:, 0] + dx <= hi[:, 0]) & (lo[:, 1] + dy <= hi[:, 1])
                keys.append((lo[ok, 0] + dx) * 1_000_003 + (lo[ok, 1] + dy))
                ids.append(n[ok])
        return np.concatenate(keys), np.concatenate(ids)

    def cast(self, p: np.ndarray, d: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Every hit of the rays ``p + t d`` (``0 < t <= reach``, ``d`` unit): the ray, the
        segment and ``t``."""
        cells, rays = self._cells(p, p + d * self.reach)
        lo = np.searchsorted(self.keys, cells, "left")
        count = np.searchsorted(self.keys, cells, "right") - lo
        # (in parts of at most PAIRS ray-segment pairs: a few long segments make wide cells,
        # and every ray in them meets every segment; memory bounded, as in the browser)
        out: tuple[list, list, list] = ([], [], [])
        upto = np.cumsum(count)
        k = 0
        while k < len(cells):
            m = max(int(np.searchsorted(upto, (upto[k - 1] if k else 0) + PAIRS, "right")), k + 1)
            r, sg, t = self._hits(p, d, rays[k:m], lo[k:m], count[k:m])
            for acc, x in zip(out, (r, sg, t), strict=True):
                acc.append(x)
            k = m
        if not out[0]:
            return np.zeros(0, int), np.zeros(0, int), np.zeros(0)
        return np.concatenate(out[0]), np.concatenate(out[1]), np.concatenate(out[2])

    def _hits(
        self, p: np.ndarray, d: np.ndarray, rays: np.ndarray, lo: np.ndarray, count: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        ray = np.repeat(rays, count)
        start = np.repeat(lo - np.concatenate([[0], np.cumsum(count)[:-1]]), count)
        seg = self.ids[start + np.arange(len(ray))]
        q, e = self.a[seg], self.b[seg] - self.a[seg]
        dr, w = d[ray], q - p[ray]
        den = dr[:, 0] * e[:, 1] - dr[:, 1] * e[:, 0]
        ok = np.abs(den) > 1e-12
        den = np.where(ok, den, 1.0)
        t = (w[:, 0] * e[:, 1] - w[:, 1] * e[:, 0]) / den
        s = (w[:, 0] * dr[:, 1] - w[:, 1] * dr[:, 0]) / den
        ok &= (t > 1e-9) & (t <= self.reach) & (s >= 0) & (s <= 1)
        return ray[ok], seg[ok], t[ok]


# ----------------------------------------------------------------------------- metrics
@dataclass(frozen=True)
class Spacing:
    """The space between a mesh's traces (copper edge to copper edge), measured along every
    trace on either side where another trace (or another stretch of the same one) faces
    it: lengths in mm of trace side, the space in mm. (Facing nothing: at the area's edge.)"""

    measured: float  # trace length with copper facing it, both sides counted
    below: float  # ... with less than the nominal space
    under: float  # ... with less than the nominal space less the tolerance (5 %)
    within: float  # ... between that and the nominal space plus 20 %
    over: float  # ... with more
    wide: float  # ... with more than twice the nominal space (the islands between runs)
    least: float  # the least space found
    largest: float  # the largest

    def to_dict(self) -> dict[str, float]:
        return {k: round(v, 4) for k, v in self.__dict__.items()}


def spacing(
    traces: Sequence[Sequence[Point]], width: float, space: float, step: float | None = None
) -> Spacing:
    """The spacing profile of ``traces`` (of ``width``, nominally ``space`` apart), summed
    up from ``gaps``."""
    _, weight, sides = gaps(traces, width, space, step)
    found = {k: 0.0 for k in ("measured", "below", "under", "within", "over", "wide")}
    least, largest = math.inf, 0.0
    for gap in sides:
        has = ~np.isnan(gap)
        gap, wt = gap[has], weight[has]
        found["measured"] += float(wt.sum())
        found["below"] += float(wt[gap < space - 1e-9].sum())
        found["under"] += float(wt[gap < 0.95 * space].sum())
        found["within"] += float(wt[(gap >= 0.95 * space) & (gap <= 1.2 * space)].sum())
        found["over"] += float(wt[gap > 1.2 * space].sum())
        found["wide"] += float(wt[gap > 2 * space].sum())
        if len(gap):
            least = min(least, float(gap.min()))
            largest = max(largest, float(gap.max()))
    return Spacing(**found, least=least if math.isfinite(least) else 0.0, largest=largest)


@dataclass(frozen=True)
class Density:
    """How evenly a mesh's copper covers its area: the copper's share of the area about
    each point (blurred over ``DENSITY_BLUR``), against the nominal share (trace width over
    pitch), away from the area's edge. A hole between runs shows as a dip."""

    mean: float  # the mean share, of the nominal
    spread: float  # its standard deviation, of the nominal
    thin: float  # the share of the area under 70 % of the nominal
    least: float  # the least found, of the nominal

    def to_dict(self) -> dict[str, float]:
        return {k: round(v, 4) for k, v in self.__dict__.items()}


DENSITY_BLUR = 1.0  # the copper's share of the area taken over about this far (mm)
DENSITY_CELL = 0.2  # ... on a grid this fine (mm)
THIN = 0.7  # under this share of the nominal: thin


def density(
    traces: Sequence[Sequence[Point]],
    area: object,  # (shapely geometry: what the mesh covers)
    width: float,
    space: float,
    blur: float = DENSITY_BLUR,
    cell: float = DENSITY_CELL,
) -> Density:
    """The coverage of ``area`` by ``traces`` (``width`` wide, nominally ``space`` apart):
    each trace's copper (its length times its width) put in the grid cells along it, then
    blurred (three box blurs: about a Gaussian), over the area blurred alike (so the edge
    counts no hole); the points at least about ``blur`` inside the edge measured."""
    import shapely

    x0, y0, x1, y1 = area.bounds
    pad = 4 * blur
    nx = math.ceil((x1 - x0 + 2 * pad) / cell)
    ny = math.ceil((y1 - y0 + 2 * pad) / cell)
    ox, oy = x0 - pad, y0 - pad
    copper = np.zeros(nx * ny)
    step = cell / 2
    for t in traces:
        p = np.asarray(t, float)
        if len(p) < 2:
            continue
        q = resample(p, step)
        mid = (q[1:] + q[:-1]) / 2
        seg = np.hypot(*np.diff(q, axis=0).T)
        i = np.clip(((mid[:, 0] - ox) / cell).astype(np.int64), 0, nx - 1)
        j = np.clip(((mid[:, 1] - oy) / cell).astype(np.int64), 0, ny - 1)
        copper += np.bincount(j * nx + i, seg * width, nx * ny)
    copper = copper.reshape(ny, nx) / (cell * cell)
    xs = ox + (np.arange(nx) + 0.5) * cell
    ys = oy + (np.arange(ny) + 0.5) * cell
    inside = shapely.contains_xy(area, *np.meshgrid(xs, ys)).astype(float)
    # (three box blurs of half-width r: variance r (r + 1) cells²)
    r = max(1, round((math.sqrt(1 + 4 * (blur / cell) ** 2) - 1) / 2))

    def smooth(a: np.ndarray) -> np.ndarray:
        for _ in range(3):
            for axis in (0, 1):
                c = np.cumsum(np.insert(a, 0, 0.0, axis=axis), axis=axis)
                n = a.shape[axis]
                hi = np.take(c, np.minimum(np.arange(n) + r + 1, n), axis=axis)
                lo = np.take(c, np.maximum(np.arange(n) - r, 0), axis=axis)
                a = (hi - lo) / (2 * r + 1)
        return a

    share = smooth(inside)
    deep = (inside > 0) & (share > 0.9)
    if not deep.any():
        return Density(0.0, 0.0, 0.0, 0.0)
    v = (smooth(copper * inside)[deep] / share[deep]) / (width / (width + space))
    return Density(float(v.mean()), float(v.std()), float((v < THIN).mean()), float(v.min()))


def gaps(
    traces: Sequence[Sequence[Point]], width: float, space: float, step: float | None = None
) -> tuple[np.ndarray, np.ndarray, tuple[np.ndarray, np.ndarray]]:
    """Samples every ``step`` (a pitch) along each of ``traces``, the trace length each
    stands for, and the space to the nearest copper on either side of each (left, right;
    NaN where none faces it): within one and a half pitches, in a cone about the normal (not
    the same trace within two and a half pitches along it); where there is none, the first
    copper straight across, as far as three times as many pitches as there are traces
    (further: the area's edge)."""
    pitch = width + space
    step = step or pitch
    pts, net, arc, normal, weight = [], [], [], [], []
    exact = _Polylines(traces)
    for i, t in enumerate(traces):
        p = resample(np.asarray(t, float), step)
        d = np.gradient(p, axis=0)
        d /= np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-12)[:, None]
        pts.append(p)
        net.append(np.full(len(p), i))
        arc.append(np.arange(len(p)) * step)
        normal.append(np.stack([-d[:, 1], d[:, 0]], 1))
        w = np.full(len(p), step)
        w[[0, -1]] = step / 2
        weight.append(w)
    p, net, arc, normal, weight = (np.concatenate(x) for x in (pts, net, arc, normal, weight))
    reach = 1.5 * pitch  # (past the nominal space plus 20 %, by a margin)
    along = 2.5 * pitch  # (round a sharp corner, the same trace that far on is out of reach)
    grid = Grid(p, reach)
    seg = np.nonzero(net[:-1] == net[1:])[0]  # (each sample to the next on its trace)
    far = [Rays(p[seg], p[seg + 1], r) for r in (4 * pitch, 3 * max(len(traces), 2) * pitch)]
    sides = []
    for side in (1.0, -1.0):

        def ok(qi: np.ndarray, pi: np.ndarray, side: float = side) -> np.ndarray:
            v = p[pi] - p[qi]
            dist = np.hypot(v[:, 0], v[:, 1])
            facing = side * np.sum(v * normal[qi], axis=1) >= 0.7 * dist
            other = (net[pi] != net[qi]) | (np.abs(arc[pi] - arc[qi]) > along)
            return facing & other & (dist <= reach) & (dist > 0)

        near = grid.nearest(p, ok)
        has = near >= 0
        q, j = p[has], near[has]
        dist = np.hypot(*(p[j] - q).T)
        for o in (-1, 1):  # (to the chords either side of the nearest sample)
            k = np.clip(j + o, 0, len(p) - 1)
            same = net[k] == net[j]
            dist = np.where(same, np.minimum(dist, _to_segment(q, p[j], p[k])), dist)
        # near the nominal space or below: to the trace itself (a chord cuts a bend's corner)
        close = np.nonzero(dist - width < 1.25 * space)[0]
        i = np.nonzero(has)[0][close]
        better = exact.distance(
            q[close], net[j[close]], arc[j[close]], 2 * step, net[i], arc[i], along
        )
        dist[close] = np.where(np.isfinite(better), better, dist[close])
        gap = np.full(len(p), np.nan)
        gap[has] = dist - width
        # nothing that near: straight across, further out
        wide = np.nonzero(~has)[0]
        across = np.full(len(wide), np.inf)
        for rays in far:
            for c in range(0, len(wide), CHUNK // 8):
                i = wide[c : c + CHUNK // 8]
                ray, s, t = rays.cast(p[i], side * normal[i])
                a = seg[s]
                mine = (net[a] == net[i[ray]]) & (np.abs(arc[a] - arc[i[ray]]) <= along)
                keep = (t > width / 2) & ~mine
                np.minimum.at(across, c + ray[keep], t[keep])
            if np.isfinite(across).all():
                break
        hit = np.isfinite(across)
        gap[wide[hit]] = across[hit] - width
        sides.append(gap)
    return p, weight, (sides[0], sides[1])


class _Polylines:
    """The traces' own segments, for exact distances near a point along one of them."""

    def __init__(self, traces: Sequence[Sequence[Point]]) -> None:
        self.a, self.b, self.start, self.arc, self.len = [], [], [], [], []
        first = 0
        for t in traces:
            q = np.asarray(t, float)
            seg = np.hypot(*np.diff(q, axis=0).T)
            self.a.append(q[:-1])
            self.b.append(q[1:])
            self.arc.append(np.concatenate([[0.0], np.cumsum(seg)])[:-1])
            self.len.append(seg)
            self.start.append(first)
            first += len(seg)
        self.ends = np.array([*self.start, first])
        self.a, self.b, self.arc, self.len = (
            np.concatenate(x) for x in (self.a, self.b, self.arc, self.len)
        )

    def distance(
        self,
        q: np.ndarray,
        net: np.ndarray,
        at: np.ndarray,
        span: float,
        own: np.ndarray,
        here: np.ndarray,
        along: float,
    ) -> np.ndarray:
        """Each point's distance to trace ``net`` where it runs within ``span`` of ``at`` along
        it; not where that is the point's ``own`` trace within ``along`` of ``here``."""
        out = np.full(len(q), np.inf)
        for i in np.unique(net):
            sel = np.nonzero(net == i)[0]
            lo, hi = self.ends[i], self.ends[i + 1]
            arc = self.arc[lo:hi]
            first = lo + np.maximum(np.searchsorted(arc, at[sel] - span, "right") - 1, 0)
            last = lo + np.searchsorted(arc, at[sel] + span, "right")
            count = last - first
            qi = np.repeat(sel, count)
            si = np.repeat(first - np.concatenate([[0], np.cumsum(count)[:-1]]), count)
            si += np.arange(len(qi))
            d = _to_segment(q[qi], self.a[si], self.b[si])
            # (a segment of its own trace reaching within that, however long)
            near = (self.arc[si] <= here[qi] + along) & (
                self.arc[si] + self.len[si] >= here[qi] - along
            )
            d[(own[qi] == i) & near] = np.inf
            np.minimum.at(out, qi, d)
        return out


def _to_segment(q: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Each point's distance to its segment."""
    e = b - a
    t = np.clip(np.sum((q - a) * e, axis=1) / np.maximum(np.sum(e * e, axis=1), 1e-18), 0, 1)
    return np.hypot(*(a + e * t[:, None] - q).T)


def skew(a: Sequence[Point], b: Sequence[Point], step: float = 0.5) -> tuple[float, float]:
    """Two neighbouring traces taken as a differential pair, both from the same end: the
    difference in their lengths, and the largest difference in the length run along each
    from that end to where they face each other (``a`` sampled every ``step``, each sample
    matched to the nearest point of ``b`` a little ahead of the last match)."""
    pa, pb = np.asarray(a, float), np.asarray(b, float)
    la = float(np.sum(np.hypot(*np.diff(pa, axis=0).T)))
    lb = float(np.sum(np.hypot(*np.diff(pb, axis=0).T)))
    qa = resample(pa, step)
    fine = step / 4
    qb = resample(pb, fine)
    sa = np.linspace(0.0, la, len(qa))
    sb = np.linspace(0.0, lb, len(qb))
    block = 64
    ahead = int(block * step / fine * max(lb / max(la, 1e-9), 1.0) * 2) + 64
    j, worst = 0, 0.0
    for k in range(0, len(qa), block):
        q = qa[k : k + block]
        cand = qb[j : j + ahead]
        d2 = np.sum((q[:, None, :] - cand[None, :, :]) ** 2, axis=2)
        m = j + np.maximum.accumulate(np.argmin(d2, axis=1))
        worst = max(worst, float(np.max(np.abs(sa[k : k + block] - sb[m]))))
        j = int(m[-1])
    return abs(la - lb), worst
