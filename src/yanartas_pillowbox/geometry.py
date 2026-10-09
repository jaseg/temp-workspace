"""Pure pillow box geometry (no Flask, no SVG).

Flat-pattern coordinate system: millimetres, x to the right, y *down* (same orientation as
SVG). The front panel occupies ``0 <= x <= Wf``, the back panel ``Wf <= x <= Wf + Wb`` and the
glue tab the next ``g``; the panel widths come from ``crosssection.solve_body``, which builds
the material (thickness ``t``) around the interior ``width x height x length`` of the
config. The straight body edges run from ``y = 0`` to ``y = L`` (``cfg.edge_length``); the
lens-shaped closing flaps stick out above ``y = 0`` and below ``y = L``.

Each flap is bounded by two circular arcs through its panel's corners:

* the **curved fold**, bowing *into* the panel by the fold sagitta (front ``height/2``, back
  ``height/2 + t``); its distance from the chord at ``x = u`` is ``f(u)``;
* the **cut edge**, bowing *out* of the panel: the front (outer) flaps reach the back
  panel's outer surface, the back (inner) flaps stop at the front panel's inner surface.

Folded (closed) state of the mid-surface, used for the 3D model -- every face is an exact
isometric image of its flat face:

* Each panel becomes a cylinder whose rulings run along the length and whose cross-section,
  parametrised by arc length ``u``, has height ``Z(u) = f(u)`` (so ``X'(u) = sqrt(1 - f'(u)^2)``).
  Every crease ``(X(u), f(u), f(u))`` therefore lies in a plane at 45 degrees.
* Folding along a planar crease reflects the panel's extension across that plane. The flap
  becomes a cylindrical end wall ``{(X(u), f(u), z)}`` with vertical rulings. The back flaps'
  wall lies inside, the front flaps' wall ``t`` further out (the front fold bows in ``t``
  less), so the two flaps of an end lie on top of each other.
* The glue tab lies on the outside of the front panel, along its free edge (its
  mid-surface ``t`` out from the panel's).

This needs ``|f'| <= 1``, i.e. the fold arc may turn at most 45 degrees at the corners
(``s_f < 0.207 W``); the config enforces ``s_f <= 0.2 W`` (see ``crosssection``).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import lru_cache
from typing import Any

from yanartas_pillowbox.config import Config
from yanartas_pillowbox.crosssection import Body, circle_radius, sagitta_offset

Point = tuple[float, float]
BBox = tuple[float, float, float, float]  # min_x, min_y, max_x, max_y

TAU = 2 * math.pi


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _mul(a: Point, k: float) -> Point:
    return (a[0] * k, a[1] * k)


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _angle(center: Point, p: Point) -> float:
    return math.atan2(p[1] - center[1], p[0] - center[0])


# --------------------------------------------------------------------------- segments
@dataclass(frozen=True)
class Line:
    start: Point
    end: Point

    @property
    def length(self) -> float:
        return _dist(self.start, self.end)

    def point_at(self, t: float) -> Point:
        if t == 0:
            return self.start
        if t == 1:
            return self.end
        return _add(self.start, _mul(_sub(self.end, self.start), t))

    def bbox(self) -> BBox:
        (x0, y0), (x1, y1) = self.start, self.end
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    def distance_to(self, p: Point) -> float:
        d = _sub(self.end, self.start)
        ll = d[0] ** 2 + d[1] ** 2
        if ll == 0:
            return _dist(p, self.start)
        t = max(0.0, min(1.0, ((p[0] - self.start[0]) * d[0] + (p[1] - self.start[1]) * d[1]) / ll))
        return _dist(p, self.point_at(t))

    def sample(self, n: int) -> list[Point]:
        return [self.start, self.end]

    def reversed(self) -> Line:
        return Line(self.end, self.start)


@dataclass(frozen=True)
class Arc:
    """Circular arc. Angles are in the flat-pattern frame (y down), ``sweep`` is signed:
    positive sweeps towards increasing angle (SVG ``sweep-flag = 1``). ``start``/``end`` are
    stored explicitly so chained segments share bit-identical endpoints."""

    center: Point
    radius: float
    start_angle: float
    sweep: float
    start: Point
    end: Point

    @property
    def length(self) -> float:
        return self.radius * abs(self.sweep)

    @property
    def large_arc(self) -> bool:
        return abs(self.sweep) > math.pi

    @property
    def sweep_flag(self) -> bool:
        return self.sweep > 0

    def point_at(self, t: float) -> Point:
        if t == 0:
            return self.start
        if t == 1:
            return self.end
        a = self.start_angle + self.sweep * t
        return (
            self.center[0] + self.radius * math.cos(a),
            self.center[1] + self.radius * math.sin(a),
        )

    def param_of_angle(self, a: float) -> float | None:
        """Fraction along the arc at which angle ``a`` lies, or None if outside the arc."""
        d = (a - self.start_angle) % TAU if self.sweep > 0 else (self.start_angle - a) % TAU
        t = d / abs(self.sweep)
        return t if t <= 1 + 1e-12 else None

    def bbox(self) -> BBox:
        pts = [self.start, self.end]
        for k in range(4):
            a = k * math.pi / 2
            if self.param_of_angle(a) is not None:
                pts.append(
                    (
                        self.center[0] + self.radius * math.cos(a),
                        self.center[1] + self.radius * math.sin(a),
                    )
                )
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def distance_to(self, p: Point) -> float:
        if self.param_of_angle(_angle(self.center, p)) is not None:
            return abs(_dist(p, self.center) - self.radius)
        return min(_dist(p, self.start), _dist(p, self.end))

    def sub(self, t0: float, t1: float) -> Arc:
        return Arc(
            self.center,
            self.radius,
            self.start_angle + self.sweep * t0,
            self.sweep * (t1 - t0),
            self.point_at(t0),
            self.point_at(t1),
        )

    def sample(self, n: int) -> list[Point]:
        return [self.point_at(i / n) for i in range(n + 1)]

    def reversed(self) -> Arc:
        return Arc(
            self.center,
            self.radius,
            self.start_angle + self.sweep,
            -self.sweep,
            self.end,
            self.start,
        )


@dataclass(frozen=True)
class Polyline:
    """A chain of straight pieces used as one segment (one fold line, one SVG path)."""

    points: tuple[Point, ...]

    @property
    def start(self) -> Point:
        return self.points[0]

    @property
    def end(self) -> Point:
        return self.points[-1]

    @property
    def lines(self) -> tuple[Line, ...]:
        return tuple(Line(a, b) for a, b in itertools.pairwise(self.points))

    @property
    def length(self) -> float:
        return sum(ln.length for ln in self.lines)

    def point_at(self, t: float) -> Point:
        """Point at fraction ``t`` of the length."""
        if t <= 0:
            return self.start
        if t >= 1:
            return self.end
        target = t * self.length
        for ln in self.lines:
            if target <= ln.length:
                return ln.point_at(target / ln.length if ln.length else 0.0)
            target -= ln.length
        return self.end

    def bbox(self) -> BBox:
        xs, ys = [p[0] for p in self.points], [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    def distance_to(self, p: Point) -> float:
        return min(ln.distance_to(p) for ln in self.lines)

    def sample(self, n: int) -> list[Point]:
        return list(self.points)

    def reversed(self) -> Polyline:
        return Polyline(self.points[::-1])


Segment = Line | Arc | Polyline


def arc_through(center: Point, radius: float, start: Point, end: Point, via: Point) -> Arc:
    """Arc on the given circle from ``start`` to ``end`` that passes the direction of ``via``."""
    a0, a1, av = _angle(center, start), _angle(center, end), _angle(center, via)
    ccw = (a1 - a0) % TAU
    sweep = ccw if (av - a0) % TAU <= ccw else ccw - TAU
    return Arc(center, radius, a0, sweep, start, end)


def arc_from_chord(start: Point, end: Point, sagitta: float, bulge: Point) -> Arc:
    """Arc through ``start``/``end`` whose midpoint sits ``sagitta`` away from the chord in
    direction ``bulge`` (a unit vector perpendicular to the chord)."""
    chord = _dist(start, end)
    mid = _mul(_add(start, end), 0.5)
    radius = (chord**2 / 4 + sagitta**2) / (2 * sagitta)
    apex = _add(mid, _mul(bulge, sagitta))
    center = _sub(apex, _mul(bulge, radius))
    return arc_through(center, radius, start, end, apex)


# --------------------------------------------------------------------------- pattern
class FoldCategory(StrEnum):
    STRAIGHT = "straight"
    CURVED = "curved"
    GLUE = "glue"
    WALL = "wall"  # interior walls: inner flap -> bridge -> interior wall


class FoldDirection(StrEnum):
    """Fold direction seen from the print side: the box outside, or the inside with
    ``print_side = "inside"``. The pattern geometry is the same either way (a pillow box is
    its own mirror image), so only the fold indicators change."""

    MOUNTAIN = "mountain"  # crease points towards the viewer; the faces bend away
    VALLEY = "valley"  # the faces bend towards the viewer


@dataclass(frozen=True)
class Fold:
    name: str
    category: FoldCategory  # what the fold is for (panel joint, flap, glue tab)
    segment: Segment
    direction: FoldDirection | None = None  # set by build_pattern from the folded model


@dataclass(frozen=True)
class Outline:
    """One closed contour, traversed in a single direction."""

    segments: tuple[Segment, ...]

    @property
    def start(self) -> Point:
        return self.segments[0].start

    @property
    def end(self) -> Point:
        return self.segments[-1].end

    def is_continuous(self, tol: float = 1e-9) -> bool:
        pairs = zip(self.segments, (*self.segments[1:], self.segments[0]), strict=True)
        return all(_dist(a.end, b.start) <= tol for a, b in pairs)

    def distance_to(self, p: Point) -> float:
        return min(s.distance_to(p) for s in self.segments)

    def polyline(self, arc_steps: int = 32) -> list[Point]:
        pts: list[Point] = [self.start]
        for s in self.segments:
            pts.extend(s.sample(arc_steps)[1:])
        return pts

    def bbox(self) -> BBox:
        return union_bbox(s.bbox() for s in self.segments)


@dataclass(frozen=True)
class Face:
    """One region of the pattern bounded by cut and fold segments.

    ``boundary`` is a closed loop made of (possibly reversed) outline and fold segments.
    Every face is x-monotone: for ``x0 <= x <= x1`` it spans ``lower(x) <= y <= upper(x)``,
    where ``lower``/``upper`` are chains of boundary segments."""

    name: str
    kind: str  # "panel" | "flap" | "tab"
    boundary: tuple[Segment, ...]
    x0: float
    x1: float
    lower: tuple[Segment, ...]
    upper: tuple[Segment, ...]

    def y_range(self, x: float) -> tuple[float, float]:
        return y_on_chain(self.lower, x), y_on_chain(self.upper, x)


@dataclass(frozen=True)
class Pattern:
    outline: Outline
    folds: tuple[Fold, ...]  # body folds, folded in the 3D model
    faces: tuple[Face, ...]  # faces of the folded 3D model
    bbox: BBox
    info: dict[str, float]
    # Interior walls (not part of the folded mesh): their faces and folds, and the FPC
    # notches cut through those folds (closed cut contours inside the outline).
    wall_faces: tuple[Face, ...] = ()
    wall_folds: tuple[Fold, ...] = ()
    holes: tuple[Outline, ...] = ()

    @property
    def all_folds(self) -> tuple[Fold, ...]:
        return self.folds + self.wall_folds

    def fold(self, name: str) -> Fold:
        return next(f for f in self.folds if f.name == name)

    def face(self, name: str) -> Face:
        return next(f for f in self.faces if f.name == name)


def y_on_chain(chain: Sequence[Segment], x: float) -> float:
    """y of the x-monotone segment chain at ``x``."""
    best: tuple[float, float] | None = None  # (x-distance outside the segment, y)
    for seg in chain:
        x0, _, x1, _ = seg.bbox()
        if isinstance(seg, Polyline):
            pts = sorted(seg.points)
            y = _interp(pts, x)
        elif isinstance(seg, Line):
            (ax, ay), (bx, by) = seg.start, seg.end
            t = 0.0 if bx == ax else min(1.0, max(0.0, (x - ax) / (bx - ax)))
            y = ay + (by - ay) * t
        else:
            cx, cy = seg.center
            dx = min(seg.radius, max(-seg.radius, x - cx))
            h = math.sqrt(seg.radius**2 - dx * dx)
            # Of the two circle points at this x, take the one on the arc.
            cands = [(cx + dx, cy + h), (cx + dx, cy - h)]
            y = min(cands, key=lambda q: seg.distance_to(q))[1]
        miss = max(x0 - x, x - x1, 0.0)
        if best is None or miss < best[0]:
            best = (miss, y)
    assert best is not None
    return best[1]


def union_bbox(boxes: Any) -> BBox:
    boxes = list(boxes)
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _cut_chain(x0: float, y0: float, cuts: Sequence[Point], up: bool) -> tuple[Segment, ...]:
    """One flap's cut edge, left to right, through ``(x0 + u, y0 -+ c)`` for the (u, c)
    samples of ``crosssection.Body``: an exact arc where the samples are one (zero
    thickness), a fine polyline otherwise."""
    sign = -1.0 if up else 1.0
    pts = [(x0 + u, y0 + sign * c) for u, c in cuts]
    width, sagitta = cuts[-1][0], max(c for _, c in cuts)
    if cuts[0][1] == cuts[-1][1] == 0 and sagitta > 0:
        arc = arc_from_chord(pts[0], pts[-1], sagitta, (0.0, sign))
        if all(abs(c - sagitta_offset(width, sagitta, u)) < 1e-9 for u, c in cuts):
            return (arc,)
    return tuple(Line(a, b) for a, b in itertools.pairwise(pts) if _dist(a, b) > 1e-12)


def level_cut(cuts: Sequence[Point], width: float) -> tuple[float, float, float]:
    """(u_from, u_to, offset) of the level cut that takes exactly ``width`` off the top of a
    rising-then-falling edge given as (u, offset) samples."""

    def crossings(cap: float) -> tuple[float, float]:
        """First and last u where the edge reaches ``cap``."""
        pts = [
            u0 + (u1 - u0) * (cap - c0) / (c1 - c0)
            for (u0, c0), (u1, c1) in itertools.pairwise(cuts)
            if (c0 - cap) * (c1 - cap) <= 0 and c0 != c1
        ]
        return min(pts), max(pts)

    lo, hi = 0.0, max(c for _, c in cuts)  # flat width shrinks as the cap rises
    for _ in range(80):
        cap = (lo + hi) / 2
        a, b = crossings(cap)
        lo, hi = (cap, hi) if b - a > width else (lo, cap)
    cap = (lo + hi) / 2
    a, b = crossings(cap)
    return a, b, cap


def flatten_cut(cuts: Sequence[Point], width: float) -> tuple[Point, ...]:
    """FPC cutout: the (u, c) cut samples with the top of the edge cut off level, at the
    offset where the flat section is exactly ``width`` wide. (The edge is not quite
    symmetric, so the section sits a little off the flap's centre, around its highest
    point.)"""
    if width <= 0:
        return tuple(cuts)
    a, b, cap = level_cut(cuts, width)
    left = [q for q in cuts if q[0] < a - 1e-9]
    right = [q for q in cuts if q[0] > b + 1e-9]
    return (*left, (a, cap), (b, cap), *right)


def _lines(*pairs: tuple[Point, Point]) -> tuple[Line, ...]:
    """Lines between the given point pairs, skipping zero-length ones."""
    return tuple(Line(a, b) for a, b in pairs if _dist(a, b) > 1e-9)


# --------------------------------------------------------------------------- interior walls
WALL_MIN_HEIGHT = 1.0  # mm: the bridge and interior wall stop where the wall gets lower


@dataclass(frozen=True)
class WallLayout:
    """Interior walls of one config, in flat coordinates of the top end (``u`` along the back
    panel from the straight fold, offsets beyond the fold chord, like ``Body.back_cuts``).

    The inner flap's top edge becomes a fold (``crease``) at the bridge's mid-surface, ``t``
    inside the front panel's mid-surface. The bridge runs ``strip`` (offset + t) inward
    along the front panel, then folds down into the interior wall (``crease`` shifted by
    ``strip``), which ends on the back panel's inner surface (``drops``: its height below the
    bridge at each ``u``). Bridge and interior wall only span ``ua..ub``, where the interior
    wall is at least ``WALL_MIN_HEIGHT`` (or two thicknesses, or a tenth of the height)
    high; nearer the body folds the inner flap's edge is cut as before, at the bridge's
    level."""

    strip: float
    ua: float
    ub: float
    edge: tuple[Point, ...]  # (u, offset) of the inner flap's top edge, full width
    drops: tuple[Point, ...]  # (u, interior wall height), ua..ub
    crease: Polyline  # flat coordinates (x = front width + u, y = -offset)

    @property
    def reach(self) -> float:
        """How far the interior wall's free edge reaches beyond the fold chord."""
        wf = self.crease.start[0] - self.ua
        return max(-y_on_chain((self.crease,), wf + u) + self.strip + d for u, d in self.drops)


def _interp(samples: Sequence[Point], u: float) -> float:
    for (u0, c0), (u1, c1) in itertools.pairwise(samples):
        if u0 <= u <= u1:
            return c0 if u1 == u0 else c0 + (c1 - c0) * (u - u0) / (u1 - u0)
    return samples[0][1] if u < samples[0][0] else samples[-1][1]


@lru_cache(maxsize=64)
def wall_layout(cfg: Config) -> WallLayout | None:
    """The interior walls' layout, or None when they are off. Raises ValueError if the box
    is too low for them."""
    if not cfg.interior_walls:
        return None
    body, t = cfg.body, cfg.thickness
    sec, n = body.back, 2 * max(16, min(80, math.ceil(body.back.width)))
    zs = body.z_shift

    def edge_at(u: float) -> float:  # the bridge's mid-surface, t inside the front panel's
        return body.surface_z("front", -t, body.back_point(u)[0]) - zs

    def drop_at(u: float) -> float:  # bridge mid-surface down to the back's inner surface
        x = body.back_point(u)[0]
        return body.surface_z("front", -t, x) - body.surface_z("back", -t / 2, x)

    us = [sec.width * i / n for i in range(n + 1)]
    raw = [(u, edge_at(u)) for u in us]
    edge_pts: list[Point] = []
    for (u0, c0), (u1, c1) in itertools.pairwise(raw):
        edge_pts.append((u0, max(0.0, c0)))
        if (c0 > 0) != (c1 > 0):  # keep the point where the edge leaves the chord
            lo, hi = (u0, u1) if c0 <= 0 else (u1, u0)
            for _ in range(60):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if edge_at(mid) <= 0 else (lo, mid)
            if min(abs(lo - u0), abs(u1 - lo)) > 1e-6 * sec.width:
                edge_pts.append((lo, 0.0))
    edge_pts.append((raw[-1][0], max(0.0, raw[-1][1])))
    edge = tuple(sorted(edge_pts))
    min_drop = max(WALL_MIN_HEIGHT, 2 * t, 0.1 * cfg.height)
    ok = [u for u in us if drop_at(u) >= min_drop]
    if not ok:
        raise ValueError("box too low for interior walls")

    def boundary(inside: float, outside: float) -> float:
        for _ in range(60):
            mid = (inside + outside) / 2
            inside, outside = (mid, outside) if drop_at(mid) >= min_drop else (inside, mid)
        return inside

    step = sec.width / n
    ua = boundary(ok[0], max(0.0, ok[0] - step))
    ub = boundary(ok[-1], min(sec.width, ok[-1] + step))
    wf = body.front.width
    inner = [(u, c) for u, c in edge if ua + 1e-9 < u < ub - 1e-9]
    crease = Polyline(
        tuple((wf + u, -c) for u, c in [(ua, _interp(edge, ua)), *inner, (ub, _interp(edge, ub))])
    )
    k = max(2, math.ceil((ub - ua) / (sec.width / n)))
    drops = tuple((ua + (ub - ua) * i / k, drop_at(ua + (ub - ua) * i / k)) for i in range(k + 1))
    return WallLayout(cfg.interior_wall_offset + t, ua, ub, edge, drops, crease)


def _mirror(seg: Segment, length: float) -> Segment:
    """Mirror a segment from the top end to the bottom end (y -> length - y)."""

    def m(p: Point) -> Point:
        return (p[0], length - p[1])

    if isinstance(seg, Line):
        return Line(m(seg.start), m(seg.end))
    if isinstance(seg, Polyline):
        return Polyline(tuple(m(p) for p in seg.points))
    return Arc(m(seg.center), seg.radius, -seg.start_angle, -seg.sweep, m(seg.start), m(seg.end))


def _translate(seg: Segment, dy: float) -> Segment:
    def m(p: Point) -> Point:
        return (p[0], p[1] + dy)

    if isinstance(seg, Line):
        return Line(m(seg.start), m(seg.end))
    if isinstance(seg, Polyline):
        return Polyline(tuple(m(p) for p in seg.points))
    return replace(seg, center=m(seg.center), start=m(seg.start), end=m(seg.end))


@dataclass(frozen=True)
class _EndPieces:
    """The back panel's flap at one end, in top-end flat coordinates."""

    outline: tuple[Segment, ...]  # cut chain from the straight fold to the glue fold
    edge: tuple[Segment, ...]  # the flap's outer boundary (cut and fold), left to right
    wall_faces: tuple[Face, ...] = ()
    wall_folds: tuple[Fold, ...] = ()
    holes: tuple[Outline, ...] = ()


def _back_end(cfg: Config, fpc: bool) -> _EndPieces:
    """The inner flap at the top end (with interior walls, if on), and FPC cutout."""
    body = cfg.body
    wf = body.front.width
    width = cfg.fpc_cutout_width if fpc else 0.0
    layout = wall_layout(cfg)
    if layout is None:
        chain = _cut_chain(wf, 0.0, flatten_cut(body.back_cuts, width), up=True)
        return _EndPieces(chain, chain)

    s, crease = layout.strip, layout.crease
    pa, pb = crease.start, crease.end
    left = [(wf + u, -c) for u, c in layout.edge if u < layout.ua - 1e-9]
    right = [(wf + u, -c) for u, c in layout.edge if u > layout.ub + 1e-9]
    left_cut = tuple(Line(a, b) for a, b in itertools.pairwise([*left, pa]) if _dist(a, b) > 1e-12)
    right_cut = tuple(
        Line(a, b) for a, b in itertools.pairwise([pb, *right]) if _dist(a, b) > 1e-12
    )
    crease2 = _translate(crease, -s)
    pa2, pb2 = crease2.start, crease2.end
    free_pts = [(wf + u, y_on_chain((crease2,), wf + u) - d) for u, d in layout.drops]
    free = tuple(Line(a, b) for a, b in itertools.pairwise(free_pts) if _dist(a, b) > 1e-12)
    pa3, pb3 = free_pts[0], free_pts[-1]
    side_a1, side_a2 = Line(pa, pa2), Line(pa2, pa3)
    side_b2, side_b1 = Line(pb3, pb2), Line(pb2, pb)
    outline = (*left_cut, side_a1, side_a2, *free, side_b2, side_b1, *right_cut)
    x0, x1 = pa[0], pb[0]
    # The folds, split around the FPC notches (if any): (left, notch, right) pieces, where
    # the notch pieces are cut, not folded. Without a cutout the "notch" is empty.
    if width > 0:
        # FPC: notch both folds over the cutout width (a level cut of exactly that width
        # across the top of the fold), cutting the inner flap and the interior wall back to
        # the same level below the bridge; the bridge keeps its full edge.
        ua_n, ub_n, level = level_cut([(x - wf, -y) for x, y in crease.points], width)
        na, nb = (wf + ua_n, -level), (wf + ub_n, -level)
        mid = [q for q in crease.points if ua_n + 1e-9 < q[0] - wf < ub_n - 1e-9]
        c1 = (
            Polyline((*(q for q in crease.points if q[0] < na[0] - 1e-9), na)),
            Polyline((na, *mid, nb)),
            Polyline((nb, *(q for q in crease.points if q[0] > nb[0] + 1e-9))),
        )
        c2 = tuple(_translate(seg, -s) for seg in c1)
        flap_notch = Line(na, nb)  # the inner flap's edge in the notch
        # ... and the interior wall's, cut back as far below the bridge (mirrored about it).
        wall_notch = Polyline(tuple((x, 2 * (y - s) - (-level - s)) for x, y in c1[1].points))
        holes = (
            Outline((c1[1], flap_notch.reversed())),
            Outline((c2[1], wall_notch.reversed())),
        )
        folds = tuple(
            Fold(f"{name}-{side}", FoldCategory.WALL, seg)
            for name, pieces in (("bridge", c1), ("wall", c2))
            for side, seg in (("left", pieces[0]), ("right", pieces[2]))
        )
        flap_edge: tuple[Segment, ...] = (c1[0], flap_notch, c1[2])
        bridge_top: tuple[Segment, ...] = c1
        bridge_bottom: tuple[Segment, ...] = c2
        wall_top: tuple[Segment, ...] = (c2[0], wall_notch, c2[2])
    else:
        holes = ()
        folds = (
            Fold("bridge", FoldCategory.WALL, crease),
            Fold("wall", FoldCategory.WALL, crease2),
        )
        flap_edge = bridge_top = (crease,)
        bridge_bottom = wall_top = (crease2,)

    def back_along(chain: Sequence[Segment]) -> tuple[Segment, ...]:
        return tuple(seg.reversed() for seg in reversed(chain))

    bridge = Face(
        "bridge",
        "bridge",
        (*bridge_top, side_b1.reversed(), *back_along(bridge_bottom), side_a1.reversed()),
        x0,
        x1,
        bridge_bottom,
        bridge_top,
    )
    wall = Face(
        "wall",
        "wall",
        (*wall_top, side_b2.reversed(), *back_along(free), side_a2.reversed()),
        x0,
        x1,
        free,
        wall_top,
    )
    return _EndPieces(outline, (*left_cut, *flap_edge, *right_cut), (bridge, wall), folds, holes)


def _mirror_face(face: Face, length: float, name: str) -> Face:
    m = tuple(_mirror(seg, length) for seg in face.boundary)
    return Face(
        name,
        face.kind,
        m,
        face.x0,
        face.x1,
        tuple(_mirror(seg, length) for seg in face.upper),
        tuple(_mirror(seg, length) for seg in face.lower),
    )


def build_pattern(cfg: Config) -> Pattern:
    """Turn a validated config into the flat pattern: one outline and typed folds."""
    body = cfg.body
    wf, wb, length = body.front.width, body.back.width, cfg.edge_length
    w2 = wf + wb
    g, taper = cfg.glue_tab_width, cfg.glue_tab_taper
    sf, sb = body.front.sagitta, body.back.sagitta
    front_cuts, back_cuts = body.front_cuts, body.back_cuts
    # The outer flaps reach past the corners where the back panel runs on (glued edge) or
    # bends around the outside (straight fold): short cut steps there.
    c_left, c_right = front_cuts[0][1], front_cuts[-1][1]

    up, down = (0.0, -1.0), (0.0, 1.0)
    p = {
        "tl": (0.0, 0.0),
        "tm": (wf, 0.0),
        "tr": (w2, 0.0),
        "bl": (0.0, length),
        "bm": (wf, length),
        "br": (w2, length),
        "gt": (w2 + g, taper),
        "gb": (w2 + g, length - taper),
    }

    def rev(chain: Sequence[Segment]) -> tuple[Segment, ...]:
        return tuple(seg.reversed() for seg in reversed(chain))

    cut_ft = _cut_chain(0.0, 0.0, front_cuts, up=True)
    step_t = _lines(((wf, -c_right), p["tm"]))
    fpc = cfg.fpc_cutout
    top = _back_end(cfg, fpc in ("front", "both"))
    bottom = _back_end(cfg, fpc in ("back", "both"))
    cut_bt = top.outline
    edge_bt = top.edge
    tab = (Line(p["tr"], p["gt"]), Line(p["gt"], p["gb"]), Line(p["gb"], p["br"]))
    cut_bb = rev(tuple(_mirror(seg, length) for seg in bottom.outline))
    edge_bb = tuple(_mirror(seg, length) for seg in bottom.edge)  # left to right
    step_b = _lines((p["bm"], (wf, length + c_right)))
    cut_fb = rev(_cut_chain(0.0, length, front_cuts, up=False))
    free_bottom = _lines(((0.0, length + c_left), p["bl"]))
    free_edge = Line(p["bl"], p["tl"])
    free_top = _lines((p["tl"], (0.0, -c_left)))
    outline = Outline(
        (
            *cut_ft,
            *step_t,
            *cut_bt,
            *tab,
            *cut_bb,
            *step_b,
            *cut_fb,
            *free_bottom,
            free_edge,
            *free_top,
        )
    )

    folds = (
        Fold("front-top", FoldCategory.CURVED, arc_from_chord(p["tl"], p["tm"], sf, down)),
        Fold("back-top", FoldCategory.CURVED, arc_from_chord(p["tm"], p["tr"], sb, down)),
        Fold("front-bottom", FoldCategory.CURVED, arc_from_chord(p["bl"], p["bm"], sf, up)),
        Fold("back-bottom", FoldCategory.CURVED, arc_from_chord(p["bm"], p["br"], sb, up)),
        Fold("panels", FoldCategory.STRAIGHT, Line(p["tm"], p["bm"])),
        Fold("glue-tab", FoldCategory.GLUE, Line(p["tr"], p["br"])),
    )

    f_ft, f_bt, f_fb, f_bb, f_mid, f_glue = (f.segment for f in folds)

    faces = (
        Face(
            "front-panel",
            "panel",
            (f_ft, f_mid, f_fb.reversed(), free_edge),
            0.0,
            wf,
            (f_ft,),
            (f_fb,),
        ),
        Face(
            "back-panel",
            "panel",
            (f_bt, f_glue, f_bb.reversed(), f_mid.reversed()),
            wf,
            w2,
            (f_bt,),
            (f_bb,),
        ),
        Face("glue-tab", "tab", (*tab, f_glue.reversed()), w2, w2 + g, tab[:1], tab[2:]),
        Face(
            "front-top-flap",
            "flap",
            (*cut_ft, *step_t, f_ft.reversed(), *free_top),
            0.0,
            wf,
            cut_ft,
            (f_ft,),
        ),
        Face("back-top-flap", "flap", (*edge_bt, f_bt.reversed()), wf, w2, edge_bt, (f_bt,)),
        Face(
            "front-bottom-flap",
            "flap",
            (f_fb, *step_b, *cut_fb, *free_bottom),
            0.0,
            wf,
            (f_fb,),
            rev(cut_fb),
        ),
        Face("back-bottom-flap", "flap", (*rev(edge_bb), f_bb), wf, w2, (f_bb,), edge_bb),
    )
    wall_faces = (
        *(replace(f, name=f"top-{f.name}") for f in top.wall_faces),
        *(_mirror_face(f, length, f"bottom-{f.name}") for f in bottom.wall_faces),
    )
    wall_dir = FoldDirection.MOUNTAIN if cfg.print_side == "outside" else FoldDirection.VALLEY
    wall_folds = (
        *(replace(f, name=f"top-{f.name}", direction=wall_dir) for f in top.wall_folds),
        *(
            replace(
                f, name=f"bottom-{f.name}", segment=_mirror(f.segment, length), direction=wall_dir
            )
            for f in bottom.wall_folds
        ),
    )
    holes = (
        *top.holes,
        *(Outline(tuple(_mirror(seg, length) for seg in h.segments)) for h in bottom.holes),
    )

    bbox = union_bbox(
        [
            outline.bbox(),
            *(f.segment.bbox() for f in (*folds, *wall_folds)),
            *(h.bbox() for h in holes),
        ]
    )

    x0, z0, x1, z1 = body_bbox(body)
    info = {
        "pattern_width": bbox[2] - bbox[0],
        "pattern_height": bbox[3] - bbox[1],
        "front_fold_sagitta": sf,
        "back_fold_sagitta": sb,
        # Cut edges' furthest reach beyond the chord (outer flaps) and at the centre (inner).
        "front_cut_sagitta": max(c for _, c in front_cuts),
        "back_cut_sagitta": max(c for _, c in back_cuts),
        "front_fold_radius": circle_radius(wf, sf),
        "back_fold_radius": circle_radius(wb, sb),
        "box_height": cfg.height,
        "edge_length": length,
        "front_panel_width": wf,
        "back_panel_width": wb,
        "circumference": w2,
        "outer_width": x1 - x0,  # outside of the material, fold to fold
        "outer_height": z1 - z0,
        "outer_length": length,
        # Shallower tapers let the glued tab reach past the curved fold near the corners.
        "min_glue_tab_taper": g * fold_slope(wf, sf),
    }
    layout = wall_layout(cfg)
    if layout is not None:
        info["interior_wall_width"] = layout.ub - layout.ua
        info["interior_wall_strip"] = layout.strip
    folds = tuple(replace(f, direction=fold_direction(cfg, f.segment, faces)) for f in folds)
    return Pattern(outline, folds, faces, bbox, info, wall_faces, wall_folds, holes)


def _face_at(faces: Sequence[Face], p: Point) -> Face:
    for face in faces:
        if face.x0 < p[0] < face.x1:
            lo, hi = face.y_range(p[0])
            if lo < p[1] < hi:
                return face
    raise ValueError(f"no face at {p}")


def print_side_normal(box: FoldedBox, face: str, p: Point, h: float) -> Point3:
    """Unit normal, in the folded box, of the face's print side at flat point p (interior).

    Flat pattern axes are x right, y down, so x cross y points into the page, away from the
    viewer; the print side's normal is the folded image of the opposite direction."""
    dx = [
        b - a
        for a, b in zip(
            box.map(face, (p[0] - h, p[1])), box.map(face, (p[0] + h, p[1])), strict=True
        )
    ]
    dy = [
        b - a
        for a, b in zip(
            box.map(face, (p[0], p[1] - h)), box.map(face, (p[0], p[1] + h)), strict=True
        )
    ]
    n = (
        -(dx[1] * dy[2] - dx[2] * dy[1]),
        -(dx[2] * dy[0] - dx[0] * dy[2]),
        -(dx[0] * dy[1] - dx[1] * dy[0]),
    )
    k = math.hypot(*n)
    return (n[0] / k, n[1] / k, n[2] / k)


def fold_direction(cfg: Config, segment: Segment, faces: Sequence[Face]) -> FoldDirection:
    """Mountain or valley, seen from the print side, from the folded model: at the fold's
    midpoint, does the face on one side bend away from (mountain) or towards (valley) the
    print side of the face on the other side?"""
    box = FoldedBox(cfg)
    eps = 1e-3 * cfg.body.front.width
    p = segment.point_at(0.5)
    a, b = segment.point_at(0.5 - 1e-4), segment.point_at(0.5 + 1e-4)
    t = (b[0] - a[0], b[1] - a[1])
    k = math.hypot(*t)
    n = (-t[1] / k, t[0] / k)
    qa, qb = (p[0] + eps * n[0], p[1] + eps * n[1]), (p[0] - eps * n[0], p[1] - eps * n[1])
    face_a, face_b = _face_at(faces, qa), _face_at(faces, qb)
    normal_a = print_side_normal(box, face_a.name, qa, eps / 4)
    if cfg.print_side == "inside":  # seen from the other side of the material
        normal_a = (-normal_a[0], -normal_a[1], -normal_a[2])
    origin = box.map(face_b.name, p)
    into_b = [c - o for c, o in zip(box.map(face_b.name, qb), origin, strict=True)]
    bend = sum(i * j for i, j in zip(into_b, normal_a, strict=True))
    return FoldDirection.MOUNTAIN if bend < 0 else FoldDirection.VALLEY


# --------------------------------------------------------------------------- 3D model
def fold_slope(width: float, sagitta: float) -> float:
    """|f'| at the panel corners: tangent of the angle the fold arc makes with its chord."""
    r = circle_radius(width, sagitta)
    return (width / 2) / (r - sagitta)


Point3 = tuple[float, float, float]


class FoldedBox:
    """Maps flat-pattern points of each face to their position in the closed box.

    3D frame: millimetres, X across the box, Y along the straight edges (up, centred), Z height
    (front panel at +Z)."""

    def __init__(self, cfg: Config) -> None:
        self.body: Body = cfg.body
        self.length = cfg.edge_length

    def map(self, face: str, p: Point) -> Point3:
        body, length = self.body, self.length
        front, back, zs = body.front, body.back, body.z_shift
        x, y = p
        # Crease planes (unshifted Z): front y = Z, back y = -Z (and mirrored at y = L).
        if face == "front-panel":
            pos = (body.front_x + front.x(x), y, zs + front.z(x))
        elif face == "front-top-flap":  # reflected across the crease plane y = Z
            pos = (body.front_x + front.x(x), front.z(x), zs + y)
        elif face == "front-bottom-flap":  # reflected across y + Z = L
            pos = (body.front_x + front.x(x), length - front.z(x), zs + length - y)
        elif face == "back-panel":
            u = x - front.width
            pos = (body.back_x - back.x(u), y, zs - back.z(u))
        elif face == "back-top-flap":  # reflected across y = -Z
            u = x - front.width
            pos = (body.back_x - back.x(u), back.z(u), zs - y)
        elif face == "back-bottom-flap":  # reflected across y - Z = L
            u = x - front.width
            pos = (body.back_x - back.x(u), length - back.z(u), zs + y - length)
        elif face == "glue-tab":  # on the outside of the front panel's free edge
            tx, tz = body.tab_point(x - front.width - back.width)
            pos = (tx, y, tz)
        else:
            raise KeyError(face)
        return (pos[0], length / 2 - pos[1], pos[2])


def _face_columns(face: Face, step: float) -> list[float]:
    n = max(24, min(160, math.ceil((face.x1 - face.x0) / step)))
    xs = {face.x0 + (face.x1 - face.x0) * i / n for i in range(n + 1)}
    for seg in (*face.lower, *face.upper):  # keep chain breakpoints
        xs.update(q[0] for q in (seg.start, seg.end))
        if isinstance(seg, Polyline):
            xs.update(q[0] for q in seg.points)
        if isinstance(seg, Arc):  # and arc apexes, so the mesh reaches the full bulge
            xs.add(seg.point_at(0.5)[0])
    out: list[float] = []
    for x in sorted(xs):
        if face.x0 - 1e-9 <= x <= face.x1 + 1e-9 and (not out or x - out[-1] > 1e-7):
            out.append(min(face.x1, max(face.x0, x)))
    return out


def build_model3d(
    cfg: Config, pattern: Pattern | None = None, step: float = 1.0, rows: int = 4
) -> dict[str, Any]:
    """Triangle mesh of the closed box: one part per pattern face.

    Each part carries its flat-pattern coordinates (``flat``, x/y pairs) alongside the folded
    3D ``positions``; triangulation is done in the flat face, so every triangle is an
    (up to chord error) isometric image of a piece of the pattern."""
    pattern = pattern or build_pattern(cfg)
    box = FoldedBox(cfg)
    parts: list[dict[str, Any]] = []
    for face in pattern.faces:
        xs = _face_columns(face, step)
        flat: list[float] = []
        positions: list[float] = []
        for x in xs:
            lo, hi = face.y_range(x)
            for j in range(rows + 1):
                y = lo + (hi - lo) * j / rows
                flat += [x, y]
                positions += box.map(face.name, (x, y))
        indices: list[int] = []
        k = rows + 1
        for i in range(len(xs) - 1):
            for j in range(rows):
                a, c = i * k + j, i * k + j + 1
                b, d = a + k, c + k
                for tri in ((a, b, d), (a, d, c)):
                    if _flat_area(flat, tri) > 1e-9:
                        indices += tri
        parts.append(
            {
                "name": face.name,
                "kind": face.kind,
                "flat": [round(v, 6) for v in flat],
                "positions": [round(v, 6) for v in positions],
                "indices": indices,
            }
        )

    lines: list[dict[str, Any]] = []
    for fold in pattern.folds:
        face = next(
            f
            for f in pattern.faces
            if fold.segment in (*f.lower, *f.upper) or fold.segment in f.boundary
        )
        n = 64 if isinstance(fold.segment, Arc) else 1
        pts = [box.map(face.name, fold.segment.point_at(i / n)) for i in range(n + 1)]
        lines.append(
            {
                "name": fold.name,
                "category": fold.category.value,
                "direction": fold.direction.value if fold.direction else None,
                "points": [[round(c, 6) for c in pt] for pt in pts],
            }
        )

    x0, z0, x1, z1 = body_bbox(box.body, with_material=False)
    return {
        "walls": _wall_volumes(cfg, box, max(48, math.ceil(cfg.body.back.width / step)), rows),
        "units": "mm",
        "parts": parts,
        "lines": lines,
        "bounds": {  # of the mid-surface model
            "width": x1 - x0,
            "length": cfg.edge_length,  # overall, corner to corner
            "height": z1 - z0,
        },
        "interior": {"width": cfg.width, "length": cfg.length, "height": cfg.height},
    }


def _wall_volumes(
    cfg: Config, box: FoldedBox, columns: int = 48, rows: int = 1
) -> list[dict[str, Any]]:
    """Bridges and interior walls of the closed box, for the 3D preview (drawn like the
    payload, not folded paper): one surface per bridge and wall, each with the closed
    ``outline`` of its edges. Placed like the inner flap they hang from: the bridge at the
    inner flap's top fold height, running ``strip`` inward; the wall hanging from its inner
    end down to the back panel's inner surface."""
    layout = wall_layout(cfg)
    if layout is None:
        return []
    body, edge = box.body, cfg.edge_length
    wf = body.front.width
    us = [layout.ua + (layout.ub - layout.ua) * i / columns for i in range(columns + 1)]
    top_z = [body.z_shift - y_on_chain((layout.crease,), wf + u) for u in us]
    drops = [_interp(layout.drops, u) for u in us]
    out: list[dict[str, Any]] = []
    for end in ("top", "bottom"):
        sign = 1.0 if end == "top" else -1.0

        def at(u: float, inward: float, z: float, sign: float = sign) -> list[float]:
            y_raw = body.back.z(u) + inward  # from the corner line, into the box
            y = sign * (edge / 2 - y_raw)
            return [round(body.back_point(u)[0], 6), round(y, 6), round(z, 6)]

        for kind in ("bridge", "wall"):
            grid = []  # per column: rows + 1 points from the inner flap / bridge end
            for u, z, d in zip(us, top_z, drops, strict=True):
                if kind == "bridge":
                    pts = [at(u, layout.strip * j / rows, z) for j in range(rows + 1)]
                else:
                    pts = [at(u, layout.strip, z - d * j / rows) for j in range(rows + 1)]
                grid.append(pts)
            k = rows + 1
            indices = []
            for i in range(columns):
                for j in range(rows):
                    a, b = i * k + j, i * k + j + 1
                    c, d = a + k, b + k
                    indices += [a, c, d, a, d, b]
            outline = (
                [col[0] for col in grid]
                + grid[-1][1:]
                + [col[-1] for col in reversed(grid)][1:]
                + grid[0][-2:0:-1]
            )
            out.append(
                {
                    "name": f"{end}-{kind}",
                    "kind": kind,
                    "positions": [c for col in grid for p in col for c in p],
                    "indices": indices,
                    "outline": outline,
                }
            )
    return out


def _flat_area(flat: list[float], tri: tuple[int, int, int]) -> float:
    (ax, ay), (bx, by), (cx, cy) = ((flat[2 * i], flat[2 * i + 1]) for i in tri)
    return abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2


def _trace(points: Any, n: int) -> list[list[float]]:
    return [[round(c, 6) for c in points(i / n)] for i in range(n + 1)]


def _band(mid: list[list[float]], thickness: float) -> list[list[float]]:
    """Closed outline of the material around a mid-surface polyline: offset by +-t/2
    perpendicular to it, ends cut square."""
    h = thickness / 2
    sides: tuple[list[list[float]], list[list[float]]] = ([], [])
    for i, (x, z) in enumerate(mid):
        (ax, az), (bx, bz) = mid[max(0, i - 1)], mid[min(len(mid) - 1, i + 1)]
        k = math.hypot(bx - ax, bz - az)
        nx, nz = -(bz - az) / k, (bx - ax) / k
        for side, s in zip(sides, (h, -h), strict=True):
            side.append([round(x + s * nx, 6), round(z + s * nz, 6)])
    return sides[0] + sides[1][::-1]


def _interior(body: Body, samples: int) -> list[list[float]]:
    """Closed outline of the interior: the panels' inner surfaces (t/2 inside the
    mid-surface), from the interior corner at the glued edge over the front panel to the
    corner at the straight fold and back along the back panel."""
    h = body.thickness / 2
    (gx, gz), (fx, fz) = body.inner_glue, body.inner_fold
    out = [(gx, gz)]
    for panel, sec, point, normal in (
        ("front", body.front, body.front_point, body.front_normal),
        ("back", body.back, body.back_point, body.back_normal),
    ):
        for i in range(samples + 1):
            (x, z), (nx, nz) = point(sec.width * i / samples), normal(sec.width * i / samples)
            q = (x - h * nx, z - h * nz)
            if gx < q[0] < fx:  # past the corners the inner surfaces run into each other
                out.append(q)
        out.append((fx, fz) if panel == "front" else (gx, gz))
    return [[round(c, 6) for c in q] for q in out]


def body_bbox(body: Body, with_material: bool = True) -> BBox:
    """(x0, z0, x1, z1) of the closed body's cross-section, glue tab included."""
    h = body.thickness / 2 if with_material else 0.0
    pts = []
    for sec, point, normal in (
        (body.front, body.front_point, body.front_normal),
        (body.back, body.back_point, body.back_normal),
    ):
        for i in range(129):
            (x, z), (nx, nz) = point(sec.width * i / 128), normal(sec.width * i / 128)
            pts.append((x + h * nx, z + h * nz))
    (gx, gz), (px, pz) = body.glue_point, body.fold_point
    pts += [(gx - h, gz), (px + h, pz)]  # outsides of the two side folds (rounded)
    return (
        min(p[0] for p in pts),
        min(p[1] for p in pts),
        max(p[0] for p in pts),
        max(p[1] for p in pts),
    )


def build_cross_section(cfg: Config, samples: int = 96) -> dict[str, Any]:
    """2D cross-section of the closed box body, perpendicular to its length.

    The body is a cylinder between the curved folds, so this section is the same at every
    point along the length. Coordinates are (X, Z) in mm in the 3D model's frame: X across
    the box, Z height with the front panel at +Z, centred on the interior. ``front``/``back``
    are the panels' mid-surfaces (from ``FoldedBox``, so the section, 3D preview and pattern
    always agree), ``glue_tab`` the glue tab's mid-surface from the glue fold, on the
    outside of the front panel, ``material`` the outlines of the material around the two
    panels and the tab, ``interior`` the closed outline of the interior, ``inner``
    the interior's corners and apexes (where the interior width and height are measured).
    """
    box = FoldedBox(cfg)
    body = box.body
    wf, wb, mid = body.front.width, body.back.width, cfg.edge_length / 2

    def trace(face: str, x0: float, x1: float) -> list[list[float]]:
        def at(f: float) -> tuple[float, float]:
            p = box.map(face, (x0 + (x1 - x0) * f, mid))
            return (p[0], p[2])

        return _trace(at, samples)

    front = trace("front-panel", 0.0, wf)  # glued edge (-X) -> straight fold (+X)
    back = trace("back-panel", wf, wf + wb)  # straight fold (+X) -> glue fold (-X)
    glue_tab = trace("glue-tab", wf + wb, wf + wb + cfg.glue_tab_width)  # glue fold -> free edge
    h = body.thickness / 2
    fa, ba = body.front_point(wf / 2), body.back_point(wb / 2)
    inner = {
        "fold": list(body.inner_fold),
        "glue": list(body.inner_glue),
        "front_apex": [fa[0], fa[1] - h],
        "back_apex": [ba[0], ba[1] + h],
    }
    return {
        "units": "mm",
        "front": front,
        "back": back,
        "interior": _interior(body, samples),
        "inner": {k: [round(c, 6) for c in v] for k, v in inner.items()},
        "glue_tab": glue_tab,
        "material": [_band(c, body.thickness) for c in (front, back, glue_tab)],
        "width": cfg.width,  # interior
        "height": cfg.height,
        "thickness": body.thickness,
        "bbox": [round(c, 6) for c in body_bbox(body)],
    }
