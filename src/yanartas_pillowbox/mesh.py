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
CHUNK = 50_000  # queries at a time (bounds the memory a query takes)

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

    @property
    def ends(self) -> tuple[tuple[Point, Point], ...]:
        return tuple((t[0], t[-1]) for t in self.traces)


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


# ----------------------------------------------------------------------------- metrics
@dataclass(frozen=True)
class Spacing:
    """The space between a mesh's traces (copper edge to copper edge), measured along every
    trace on either side where another trace (or another stretch of the same one) faces
    it: lengths in mm of trace side, the space in mm."""

    measured: float  # trace length with copper facing it, both sides counted
    below: float  # ... with less than the nominal space
    under: float  # ... with less than the nominal space less the tolerance (5 %)
    within: float  # ... between that and the nominal space plus 20 %
    over: float  # ... with more
    least: float  # the least space found

    def to_dict(self) -> dict[str, float]:
        return {k: round(v, 4) for k, v in self.__dict__.items()}


def spacing(
    traces: Sequence[Sequence[Point]], width: float, space: float, step: float | None = None
) -> Spacing:
    """The spacing profile of ``traces`` (of ``width``, nominally ``space`` apart): samples
    every ``step`` along each, the nearest copper on either side within one and a half
    pitches (in a cone about the normal; not the same trace within two and a half pitches
    along it)."""
    pitch = width + space
    step = step or pitch
    pts, net, arc, normal, weight = [], [], [], [], []
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
    found = {"measured": 0.0, "below": 0.0, "under": 0.0, "within": 0.0, "over": 0.0}
    least = math.inf
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
        for o in (-1, 1):  # (to the segments either side of the nearest sample: exact)
            k = np.clip(j + o, 0, len(p) - 1)
            same = net[k] == net[j]
            dist = np.where(same, np.minimum(dist, _to_segment(q, p[j], p[k])), dist)
        gap = dist - width
        wt = weight[has]
        found["measured"] += float(wt.sum())
        found["below"] += float(wt[gap < space - 1e-9].sum())
        found["under"] += float(wt[gap < 0.95 * space].sum())
        found["within"] += float(wt[(gap >= 0.95 * space) & (gap <= 1.2 * space)].sum())
        found["over"] += float(wt[gap > 1.2 * space].sum())
        if len(gap):
            least = min(least, float(gap.min()))
    return Spacing(**found, least=least if math.isfinite(least) else 0.0)


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
