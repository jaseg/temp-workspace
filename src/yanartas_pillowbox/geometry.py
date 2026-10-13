"""Pure pillow box geometry (no Flask, no SVG).

Flat-pattern coordinate system: millimetres, x to the right, y *down* (same orientation as
SVG). The front panel occupies ``0 <= x <= Wf``, the back panel ``Wf <= x <= Wf + Wb`` and the
glue tab the next ``g``; the panel widths come from ``crosssection.solve_body``, which builds
the material (thickness ``t``) around the interior ``width x height x length`` of the
config. The front panel's straight edges run from ``y = 0`` to ``y = Lf``
(``cfg.front_length``); the back panel and the glue tab are shorter by the end wall gap ``e``
at each end, from ``y = e`` to ``y = e + L`` (``cfg.edge_length``). The lens-shaped closing
flaps stick out beyond each panel's ends.

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
  becomes a cylindrical end wall ``{(X(u), f(u), z)}`` with vertical rulings (``f`` measured
  from its own panel's ends). The back flaps' wall lies inside, the front flaps' wall
  ``e + t`` further out on the centreline (the front fold bows in ``t`` less, and the front
  panel is ``e`` longer at each end): a clear gap ``e`` between the walls in the middle, and
  with ``e = 0`` the two flaps of an end lie on top of each other.
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


Segment = Line | Arc


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
    LID = "lid"  # outer flap -> lid over the end wall gap


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
    # Cuts inside the outline (open chains with material on both sides): where the front
    # panel's wing ends on the inner flap's cut edge.
    slits: tuple[tuple[Segment, ...], ...] = ()

    def fold(self, name: str) -> Fold:
        return next(f for f in self.folds if f.name == name)

    def face(self, name: str) -> Face:
        return next(f for f in self.faces if f.name == name)


def y_on_chain(chain: Sequence[Segment], x: float) -> float:
    """y of the x-monotone segment chain at ``x``."""
    best: tuple[float, float] | None = None  # (x-distance outside the segment, y)
    for seg in chain:
        x0, _, x1, _ = seg.bbox()
        if isinstance(seg, Line):
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


def _mirror(seg: Segment, length: float) -> Segment:
    """Mirror a segment from the top end to the bottom end (y -> length - y)."""

    def m(p: Point) -> Point:
        return (p[0], length - p[1])

    if isinstance(seg, Line):
        return Line(m(seg.start), m(seg.end))
    return Arc(m(seg.center), seg.radius, -seg.start_angle, -seg.sweep, m(seg.start), m(seg.end))


@dataclass(frozen=True)
class LidLayout:
    """The lid over the end wall gap at the top end, in flat coordinates of the front panel
    (``x``) and folded-model depths (``y_int``: distance from the front panel's top corner
    line into the box).

    The outer flap's top edge is a fold in the plane ``y_int + (Z - zs) = level``, at 45
    degrees like the curved folds: in the pattern it is the front fold arc mirrored,
    ``y = level - f(x)``. Folding across that plane puts the lid on a cylinder ruled along
    the box, ``Z = zs + level - f(x)``, the front panel's profile turned over; flat ``y``
    maps to ``y_int = level - y``. At rest (``lid_offset`` 0) ``level`` is the highest that
    keeps the lid's mid-surface at least a thickness outside the back panel's everywhere;
    the offset lowers it further, so the lid floats above the back panel.

    The two folds meet where ``f(x) = level / 2 = -drop``: in the end section, the front
    panel's fold arc (and so its cross-section) runs on past the panel's edges by
    ``spread`` on each side, and the outer flap closes to a point there. The lid's free edge
    runs ``depth(x)`` deep (``y = level - depth(x)``): the gap, up to the inner end wall's
    outer surface, plus the overlap."""

    level: float
    spread: float
    depth: tuple[Point, ...]  # (x, y_int of the free edge), x from -spread to W + spread
    arc: bool  # the free edge is an exact arc (zero thickness, no spread)

    @property
    def drop(self) -> float:
        return -self.level / 2

    def edge(self, sagitta: float) -> tuple[Segment, ...]:
        """The free edge in flat coordinates, left to right."""
        pts = [(x, self.level - d) for x, d in self.depth]
        if self.arc:
            return (arc_from_chord(pts[0], pts[-1], sagitta, (0.0, -1.0)),)
        return tuple(Line(a, b) for a, b in itertools.pairwise(pts) if _dist(a, b) > 1e-12)


MAX_SPREAD_SLOPE = 0.98  # the continued fold arc must turn less than 45 degrees, with margin


def _lid_rest(body: Body) -> float:
    """The lid's level at rest: the highest that keeps its mid-surface at least a thickness
    outside the back panel's everywhere across the box."""
    t, sec, zs = body.thickness, body.front, body.z_shift
    if t == 0:  # the back panel is the front one turned over: the lid lies on it
        return 0.0
    n = 2 * max(16, min(80, math.ceil(sec.width)))
    us = [sec.width * i / n for i in range(n + 1)]
    return min(body.surface_z("back", t, body.front_point(u)[0]) - zs + sec.z(u) for u in us)


def max_lid_offset(body: Body) -> float:
    """Largest lid offset whose end section turns at most ``MAX_SPREAD_SLOPE`` (negative:
    not even a resting lid fits)."""
    sec = body.front
    r, m = sec.radius, MAX_SPREAD_SLOPE
    d = m * r / math.sqrt(1 + m * m)
    drop = (r - sec.sagitta) - math.sqrt(r * r - d * d)
    return _lid_rest(body) + 2 * drop


@lru_cache(maxsize=64)
def lid_layout(cfg: Config) -> LidLayout | None:
    """The lid's layout, or None without an end wall gap. Raises ValueError if the lid
    offset needs the front panel's cross-section to run on past 45 degrees."""
    if cfg.end_wall_gap <= 0:
        return None
    body, t = cfg.body, cfg.thickness
    sec, zs = body.front, body.z_shift
    n = 2 * max(16, min(80, math.ceil(sec.width)))
    us = [sec.width * i / n for i in range(n + 1)]
    level = _lid_rest(body) - cfg.lid_offset
    # Where the fold arc, continued, is level / 2 off its chord: half-chord d from the middle.
    r, s = sec.radius, sec.sagitta
    d = math.sqrt(max(0.0, r * r - (r - s + level / 2) ** 2))
    if d / math.sqrt(max(1e-300, r * r - d * d)) > MAX_SPREAD_SLOPE * (1 + 1e-12):
        raise ValueError("lid offset too large: the end section would need to turn past 45 degrees")
    spread = max(0.0, d - sec.width / 2)
    k = max(2, math.ceil(4 * spread))  # samples on each continuation
    xs_flat = (
        [
            *(-spread + spread * i / k for i in range(k)),
            *us,
            *(sec.width + spread * (i + 1) / k for i in range(k)),
        ]
        if spread > 0
        else us
    )
    reach = cfg.end_wall_gap - t / 2 + cfg.lid_overlap
    g_x, p_x = body.glue_point[0], body.fold_point[0]

    def crease_depth(x: float) -> float:
        """Depth of the back panel's crease at flat x (0 beyond the back panel)."""
        x3 = body.front_x + sec.x_ext(x)
        if t == 0 and 0 <= x <= sec.width:
            return sec.z(x)  # the back panel is the front one turned over
        if not g_x <= x3 <= p_x:
            return 0.0
        return max(0.0, zs - body.surface_z("back", 0.0, x3))

    depth = tuple((x, reach + crease_depth(x)) for x in xs_flat)
    return LidLayout(level, spread, depth, t == 0 and spread == 0)


@dataclass(frozen=True)
class _End:
    """One end of the pattern (top-end coordinates): the outline from the front panel's free
    edge round to the glue fold, its faces and folds, the inner flap's cut edge (whole), the
    slit (the part of that edge the wing shares) and the wing's seam with the panel."""

    chain: tuple[Segment, ...]
    faces: tuple[Face, ...]
    folds: tuple[Fold, ...]
    back_cut: tuple[Segment, ...]
    slit: tuple[Segment, ...]
    seam_r: tuple[Segment, ...]


def _split_at_x(
    chain: Sequence[Segment], x: float
) -> tuple[tuple[Segment, ...], tuple[Segment, ...]]:
    """An x-monotone chain (left to right) split at ``x``; both parts share the exact point."""
    for i, seg in enumerate(chain):
        if not seg.start[0] <= x <= seg.end[0]:
            continue
        if x == seg.end[0]:
            return tuple(chain[: i + 1]), tuple(chain[i + 1 :])
        if isinstance(seg, Line):
            k = (x - seg.start[0]) / (seg.end[0] - seg.start[0])
            q = (x, seg.start[1] + (seg.end[1] - seg.start[1]) * k)
            first, second = Line(seg.start, q), Line(q, seg.end)
        else:
            q = (x, y_on_chain((seg,), x))
            k = seg.param_of_angle(_angle(seg.center, q))
            assert k is not None
            first = replace(seg.sub(0.0, k), start=seg.start, end=q)
            second = replace(seg.sub(k, 1.0), start=q, end=seg.end)
        parts = ((*chain[:i], first), (second, *chain[i + 1 :]))
        return tuple(s for s in parts[0] if s.length > 1e-12), tuple(
            s for s in parts[1] if s.length > 1e-12
        )
    raise ValueError(f"x = {x} outside the chain")


def overall_length(cfg: Config) -> float:
    """The box's overall length (mid-surface): the front panel's, plus where the widened end
    sections' outer walls reach past its ends."""
    lid = lid_layout(cfg)
    return cfg.front_length + (0.0 if lid is None else 2 * lid.drop)


def _mirror_face(face: Face, length: float, name: str) -> Face:
    """A top-end face mirrored to the bottom end."""
    return Face(
        name,
        face.kind,
        tuple(_mirror(seg, length) for seg in face.boundary),
        face.x0,
        face.x1,
        tuple(_mirror(seg, length) for seg in face.upper),
        tuple(_mirror(seg, length) for seg in face.lower),
    )


def build_pattern(cfg: Config) -> Pattern:
    """Turn a validated config into the flat pattern: one outline and typed folds.

    The front panel's straight edges run from ``y = 0`` to ``y = Lf`` (``cfg.front_length``);
    the back panel and the glue tab are ``2 e`` shorter (``e``, the end wall gap): they run
    from ``y = e`` to ``y = e + L`` (``cfg.edge_length``). Each flap's wall stands at its own
    panel's crease, so the inner walls stand ``e`` inside the outer walls. With a gap, each
    outer flap carries a lid over it (``LidLayout``). The bottom end mirrors the top."""
    body = cfg.body
    wf, wb, length = body.front.width, body.back.width, cfg.front_length
    e, edge = cfg.end_wall_gap, cfg.edge_length
    w2 = wf + wb
    g, taper = cfg.glue_tab_width, cfg.glue_tab_taper
    sf, sb = body.front.sagitta, body.back.sagitta
    front_cuts, back_cuts = body.front_cuts, body.back_cuts
    lid = lid_layout(cfg)

    up, down = (0.0, -1.0), (0.0, 1.0)
    p = {
        "tl": (0.0, 0.0),
        "tf": (wf, 0.0),  # front panel's corners at the straight fold
        "bf": (wf, length),
        "tm": (wf, e),  # back panel's corners there
        "bm": (wf, e + edge),
        "tr": (w2, e),
        "br": (w2, e + edge),
        "bl": (0.0, length),
        "gt": (w2 + g, e + taper),
        "gb": (w2 + g, e + edge - taper),
    }

    def rev(chain: Sequence[Segment]) -> tuple[Segment, ...]:
        return tuple(seg.reversed() for seg in reversed(chain))

    def mirror(chain: Sequence[Segment]) -> tuple[Segment, ...]:
        return tuple(_mirror(seg, length) for seg in chain)

    def back_end(fpc: bool) -> tuple[Segment, ...]:
        """The inner flap's cut edge at the top end, left to right; the FPC cutout cuts its
        top off level."""
        cuts = flatten_cut(back_cuts, cfg.fpc_cutout_width if fpc else 0.0)
        return _cut_chain(wf, e, cuts, up=True)

    f_ft = arc_from_chord(p["tl"], p["tf"], sf, down)

    def end(fpc: bool) -> _End:
        """One end of the pattern, in top-end coordinates (the bottom end is mirrored)."""
        back_cut = back_end(fpc)
        if lid is None:
            # The outer flap reaches past the corners where the back panel runs on (glued
            # edge) or bends around the outside (straight fold): short cut steps there.
            c_left, c_right = front_cuts[0][1], front_cuts[-1][1]
            free_top = _lines((p["tl"], (0.0, -c_left)))
            cut_ft = _cut_chain(0.0, 0.0, front_cuts, up=True)
            step_t = _lines(((wf, -c_right), p["tf"]))
            chain = (*free_top, *cut_ft, *step_t)
            flap = Face(
                "front-top-flap", "flap", (*chain, f_ft.reversed()), 0.0, wf, cut_ft, (f_ft,)
            )
            return _End((*chain, *back_cut), (flap,), (), back_cut, (), ())
        # The end section: the front panel's fold arc (and cross-section) runs on by
        # ``spread`` past both of its edges (the wings, over the gap only), to where it meets
        # the lid's fold, mirrored about ``y = -drop``: the outer flap is a lens again. At
        # the straight fold the wing's end is the inner flap's cut edge: one cut (a slit,
        # with material on both sides) separates the two.
        dd, sp = lid.drop, lid.spread
        crease = arc_from_chord((-sp, -dd), (wf + sp, -dd), sf + dd, up)
        lid_edge = lid.edge(sf)
        lid_l, lid_r = Line((-sp, -dd), lid_edge[0].start), Line(lid_edge[-1].end, (wf + sp, -dd))
        if sp == 0:  # zero thickness, no offset: the lid's fold runs through the corners
            chain = (*_lines(((0.0, e), p["tl"])), lid_l, *lid_edge, lid_r)
            chain = (*chain, *_lines((p["tf"], p["tm"])), *back_cut)
            wings: tuple[Face, ...] = ()
            arcs: tuple[Segment, ...] = (f_ft,)
            wing_folds: tuple[Fold, ...] = ()
            slit: tuple[Segment, ...] = ()
        else:
            full = arc_from_chord((-sp, -dd), (wf + sp, -dd), sf + dd, down)
            t0 = full.param_of_angle(_angle(full.center, p["tl"]))
            t1 = full.param_of_angle(_angle(full.center, p["tf"]))
            assert t0 is not None and t1 is not None
            f_left = replace(full.sub(0.0, t0), start=full.start, end=p["tl"])
            f_right = replace(full.sub(t1, 1.0), start=p["tf"], end=full.end)
            slit, rest = _split_at_x(back_cut, wf + sp)
            meet = slit[-1].end
            wing_bl, wing_l = Line((0.0, e), (-sp, e)), Line((-sp, e), (-sp, -dd))
            wing_r = Line((wf + sp, -dd), meet)
            seam_l, seam_r = Line(p["tl"], (0.0, e)), Line(p["tm"], p["tf"])
            chain = (wing_bl, wing_l, lid_l, *lid_edge, lid_r, wing_r, *rest)
            wings = (
                Face(
                    "front-top-left",
                    "panel",
                    (f_left, seam_l, wing_bl, wing_l),
                    -sp,
                    0.0,
                    (f_left,),
                    (wing_bl.reversed(),),
                ),
                Face(
                    "front-top-right",
                    "panel",
                    (f_right, wing_r, *rev(slit), seam_r),
                    wf,
                    wf + sp,
                    (f_right,),
                    slit,
                ),
            )
            arcs = (f_left, f_ft, f_right)
            wing_folds = (
                Fold("front-top-left", FoldCategory.CURVED, f_left),
                Fold("front-top-right", FoldCategory.CURVED, f_right),
            )
        faces = (
            *wings,
            Face("front-top-flap", "flap", (crease, *rev(arcs)), -sp, wf + sp, (crease,), arcs),
            Face(
                "front-top-lid",
                "lid",
                (lid_l, *lid_edge, lid_r, crease.reversed()),
                -sp,
                wf + sp,
                lid_edge,
                (crease,),
            ),
        )
        folds = (*wing_folds, Fold("lid-top", FoldCategory.LID, crease))
        if sp > 0:  # the inner flap's edge as the outline and the slit have it, split
            back_cut = (*slit, *rest)
        return _End(chain, faces, folds, back_cut, slit, (seam_r,) if sp > 0 else ())

    top = end(cfg.fpc_cutout in ("front", "both"))
    bottom = end(cfg.fpc_cutout in ("back", "both"))
    tab = (Line(p["tr"], p["gt"]), Line(p["gt"], p["gb"]), Line(p["gb"], p["br"]))
    free_edge = Line((0.0, length - e), (0.0, e))
    outline = Outline((*top.chain, *tab, *rev(mirror(bottom.chain)), free_edge))
    slits = tuple(c for c in (top.slit, mirror(bottom.slit)) if c)

    folds = (
        Fold("front-top", FoldCategory.CURVED, f_ft),
        Fold("back-top", FoldCategory.CURVED, arc_from_chord(p["tm"], p["tr"], sb, down)),
        Fold("front-bottom", FoldCategory.CURVED, _mirror(f_ft, length)),
        Fold("back-bottom", FoldCategory.CURVED, arc_from_chord(p["bm"], p["br"], sb, up)),
        Fold("panels", FoldCategory.STRAIGHT, Line(p["tm"], p["bm"])),
        Fold("glue-tab", FoldCategory.GLUE, Line(p["tr"], p["br"])),
        *top.folds,
        *(
            Fold(f.name.replace("-top", "-bottom"), f.category, _mirror(f.segment, length))
            for f in bottom.folds
        ),
    )

    _, f_bt, f_fb, f_bb, f_mid, f_glue = (f.segment for f in folds[:6])
    # The front panel, fold to fold; with an end wall gap its edges over the gaps are cut, or
    # adjoin the wings (seams: neither cut nor fold, the wings are the same surface).
    side_t = top.seam_r[0].reversed() if top.seam_r else None
    side_t_chain = (side_t,) if side_t else _lines((p["tf"], p["tm"]))
    side_b = (
        rev(mirror((bottom.seam_r[0].reversed(),)))
        if bottom.seam_r
        else rev(mirror(_lines((p["tf"], p["tm"]))))
    )
    left_t: tuple[Segment, ...] = _lines((p["tl"], (0.0, e)))
    left_b = rev(mirror(left_t))
    cut_bb = rev(mirror(bottom.back_cut))

    faces = (
        Face(
            "front-panel",
            "panel",
            (
                f_ft,
                *side_t_chain,
                f_mid,
                *side_b,
                f_fb.reversed(),
                *rev(left_b),
                free_edge,
                *rev(left_t),
            ),
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
        *top.faces,
        *(_mirror_face(f, length, f.name.replace("-top-", "-bottom-")) for f in bottom.faces),
        Face(
            "back-top-flap", "flap", (*top.back_cut, f_bt.reversed()), wf, w2, top.back_cut, (f_bt,)
        ),
        Face("back-bottom-flap", "flap", (*cut_bb, f_bb), wf, w2, (f_bb,), rev(cut_bb)),
    )
    bbox = union_bbox([outline.bbox(), *(f.segment.bbox() for f in folds)])

    x0, z0, x1, z1 = body_bbox(body)
    info = {
        "pattern_width": bbox[2] - bbox[0],
        "pattern_height": bbox[3] - bbox[1],
        "front_fold_sagitta": sf,
        "back_fold_sagitta": sb,
        # Cut edges' furthest reach beyond the chord (outer flaps) and at the centre (inner).
        "front_cut_sagitta": max(c for _, c in front_cuts) if lid is None else sf - lid.level,
        "back_cut_sagitta": max(c for _, c in back_cuts),
        "front_fold_radius": circle_radius(wf, sf),
        "back_fold_radius": circle_radius(wb, sb),
        "box_height": cfg.height,
        "edge_length": edge,
        "front_edge_length": length,
        "front_panel_width": wf,
        "back_panel_width": wb,
        "circumference": w2,
        "outer_width": x1 - x0,  # outside of the material, fold to fold
        "outer_height": z1 - z0,
        # (the widened end sections' outer walls reach past the front panel's ends)
        "outer_length": length + (0.0 if lid is None else 2 * lid.drop),
        # Shallower tapers let the glued tab reach past the curved fold near the corners.
        "min_glue_tab_taper": g * fold_slope(wf, sf),
    }
    if lid is not None:
        # The end sections' growth over the body (mid-surface): across the box, the front
        # panel's continued section; in height, the lid below the back panel's apex.
        front = body.front
        info["end_width_increase"] = (
            front.x_ext(wf + lid.spread) - front.x_ext(-lid.spread) - (x1 - x0 - body.thickness)
        )
        info["end_height_increase"] = -lid.level - body.thickness
    folds = tuple(replace(f, direction=fold_direction(cfg, f.segment, faces)) for f in folds)
    return Pattern(outline, folds, faces, bbox, info, slits)


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
        self.length = cfg.front_length
        self.gap = cfg.end_wall_gap
        lid = lid_layout(cfg)
        self.lid_level = 0.0 if lid is None else lid.level

    def map(self, face: str, p: Point) -> Point3:
        body, length, e = self.body, self.length, self.gap
        front, back, zs = body.front, body.back, body.z_shift
        x, y = p
        # Crease planes (unshifted Z): front y = Z, back y - e = -Z (and mirrored about the
        # middle, y = L / 2).
        if face.startswith("front-"):
            # (beyond the panel's edges, in the end sections: the fold arc continued)
            inside = 0 <= x <= front.width
            fx = body.front_x + (front.x(x) if inside else front.x_ext(x))
            fz = front.z(x) if inside else front.z_ext(x)
            k = self.lid_level
        if face in (
            "front-panel",
            *(f"front-{e}-{s}" for e in ("top", "bottom") for s in ("left", "right")),
        ):
            pos = (fx, y, zs + fz)
        elif face == "front-top-flap":  # reflected across the crease plane y = Z
            pos = (fx, fz, zs + y)
        elif face == "front-bottom-flap":  # reflected across y + Z = L
            pos = (fx, length - fz, zs + length - y)
        elif face == "front-top-lid":  # the flap reflected again, across y + Z = level
            pos = (fx, k - y, zs + k - fz)
        elif face == "front-bottom-lid":
            pos = (fx, 2 * length - k - y, zs + k - fz)
        elif face == "back-panel":
            u = x - front.width
            pos = (body.back_x - back.x(u), y, zs - back.z(u))
        elif face == "back-top-flap":  # reflected across y - e = -Z
            u = x - front.width
            pos = (body.back_x - back.x(u), e + back.z(u), zs + e - y)
        elif face == "back-bottom-flap":  # reflected across y - Z = L - e
            u = x - front.width
            pos = (body.back_x - back.x(u), length - e - back.z(u), zs + y + e - length)
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
        "units": "mm",
        "parts": parts,
        "lines": lines,
        "bounds": {  # of the mid-surface model (wider and taller at the ends with lids)
            "width": max(x1 - x0, _span(parts, 0)),
            "length": overall_length(cfg),  # overall, wall to wall
            "height": max(z1 - z0, _span(parts, 2)),
        },
        "interior": {"width": cfg.width, "length": cfg.length, "height": cfg.height},
    }


def _span(parts: list[dict[str, Any]], axis: int) -> float:
    """Extent of the mesh parts along one axis."""
    values = [v for part in parts for v in part["positions"][axis::3]]
    return max(values) - min(values)


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
            # Past the (mitred) corners the inner surfaces run through each other.
            other = body.surface_z("back" if panel == "front" else "front", -h, q[0])
            if gx < q[0] < fx and (q[1] > other if panel == "front" else q[1] < other):
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
    wf, wb, mid = body.front.width, body.back.width, cfg.front_length / 2

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
