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
    folds: tuple[Fold, ...]
    faces: tuple[Face, ...]
    bbox: BBox
    info: dict[str, float]

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


def _lines(*pairs: tuple[Point, Point]) -> tuple[Line, ...]:
    """Lines between the given point pairs, skipping zero-length ones."""
    return tuple(Line(a, b) for a, b in pairs if _dist(a, b) > 1e-9)


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
    cut_bt = _cut_chain(wf, 0.0, back_cuts, up=True)
    tab = (Line(p["tr"], p["gt"]), Line(p["gt"], p["gb"]), Line(p["gb"], p["br"]))
    cut_bb = rev(_cut_chain(wf, length, back_cuts, up=False))
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
        Face("back-top-flap", "flap", (*cut_bt, f_bt.reversed()), wf, w2, cut_bt, (f_bt,)),
        Face(
            "front-bottom-flap",
            "flap",
            (f_fb, *step_b, *cut_fb, *free_bottom),
            0.0,
            wf,
            (f_fb,),
            rev(cut_fb),
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
    folds = tuple(replace(f, direction=fold_direction(cfg, f.segment, faces)) for f in folds)
    return Pattern(outline, folds, faces, bbox, info)


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
        "bounds": {  # of the mid-surface model
            "width": x1 - x0,
            "length": cfg.edge_length,  # overall, corner to corner
            "height": z1 - z0,
        },
        "interior": {"width": cfg.width, "length": cfg.length, "height": cfg.height},
    }


def _flat_area(flat: list[float], tri: tuple[int, int, int]) -> float:
    (ax, ay), (bx, by), (cx, cy) = ((flat[2 * i], flat[2 * i + 1]) for i in tri)
    return abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2


def _trace(points: Any, n: int) -> list[list[float]]:
    return [[round(c, 6) for c in points(i / n)] for i in range(n + 1)]


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


def build_cross_section(
    cfg: Config, samples: int = 96, pattern: Pattern | None = None
) -> dict[str, Any]:
    """2D cross-section of the closed box body, perpendicular to its length.

    The body is a cylinder between the curved folds, so this section is the same at every
    point along the length. Coordinates are (X, Z) in mm in the 3D model's frame: X across
    the box, Z height with the front panel at +Z, centred on the interior. ``front``/``back``
    are the panels' mid-surfaces (from ``FoldedBox``, so the section, 3D preview and pattern
    always agree), ``interior`` the closed outline of the interior, ``inner`` the interior's
    corners and apexes (where the interior width and height are measured).
    """
    box = FoldedBox(cfg)
    body = box.body
    pattern = pattern or build_pattern(cfg)
    wf, wb, mid = body.front.width, body.back.width, cfg.edge_length / 2

    def trace(face: str, x0: float, x1: float) -> list[list[float]]:
        def at(f: float) -> tuple[float, float]:
            p = box.map(face, (x0 + (x1 - x0) * f, mid))
            return (p[0], p[2])

        return _trace(at, samples)

    front = trace("front-panel", 0.0, wf)  # glued edge (-X) -> straight fold (+X)
    back = trace("back-panel", wf, wf + wb)  # straight fold (+X) -> glue fold (-X)
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
        "folds": [
            {
                "category": FoldCategory.STRAIGHT.value,
                "direction": pattern.fold("panels").direction,
                "point": front[-1],
            },
            {
                "category": FoldCategory.GLUE.value,
                "direction": pattern.fold("glue-tab").direction,
                "point": back[-1],
            },
        ],
        "width": cfg.width,  # interior
        "height": cfg.height,
        "thickness": body.thickness,
        "bbox": [round(c, 6) for c in body_bbox(body)],
    }
