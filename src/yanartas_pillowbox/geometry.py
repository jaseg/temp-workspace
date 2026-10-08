"""Pure pillow box geometry (no Flask, no SVG).

Flat-pattern coordinate system: millimetres, x to the right, y *down* (same orientation as
SVG). The front panel occupies ``0 <= x <= W``, the back panel ``W <= x <= 2W`` and the glue
tab ``2W <= x <= 2W + g``. The straight body edges run from ``y = 0`` to ``y = L``; the
lens-shaped closing flaps stick out above ``y = 0`` and below ``y = L``.

Each flap is bounded by two circular arcs through the panel corners:

* the **curved fold**, bowing *into* the panel by the fold sagitta ``s_f``; its distance from
  the chord at ``x = u`` is ``f(u)``;
* the **cut edge**, bowing *out* of the panel by ``s_c = s_f - t/2``.

Folded (closed) state, used for the 3D model -- every face is an exact isometric image of its
flat face:

* Each panel becomes a cylinder whose rulings run along the length and whose cross-section,
  parametrised by arc length ``u``, has height ``Z(u) = f(u)`` (so ``X'(u) = sqrt(1 - f'(u)^2)``).
  The box is therefore ``2 s_f`` deep and every crease ``(X(u), f(u), f(u))`` lies in a plane
  at 45 degrees.
* Folding along a planar crease reflects the panel's extension across that plane. The flap
  becomes a cylindrical end wall ``{(X(u), f(u), z)}`` with vertical rulings. Front and back
  flaps of one end land on the *same* wall and overlap; with zero thickness each flap's cut
  edge lies exactly on the opposite panel's crease (the edge it closes against), and the
  ``t/2`` offset leaves room for the material.
* The glue tab lies against the inside of the front panel, along its free edge.

This needs ``|f'| <= 1``, i.e. the fold arc may turn at most 45 degrees at the corners
(``s_f < 0.207 W``); the config enforces ``s_f <= 0.2 W``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from yanartas_pillowbox.config import Config

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


def _unit(a: Point) -> Point:
    n = math.hypot(*a)
    return (a[0] / n, a[1] / n)


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


def circle_radius(chord: float, sagitta: float) -> float:
    return (chord**2 / 4 + sagitta**2) / (2 * sagitta)


def sagitta_offset(chord: float, sagitta: float, u: float) -> float:
    """Distance of the arc from its chord at chord position ``u`` (0..chord)."""
    r = circle_radius(chord, sagitta)
    return math.sqrt(max(0.0, r * r - (u - chord / 2) ** 2)) - (r - sagitta)


# --------------------------------------------------------------------------- pattern
class FoldCategory(StrEnum):
    STRAIGHT = "straight"
    CURVED = "curved"
    GLUE = "glue"


@dataclass(frozen=True)
class Fold:
    name: str
    category: FoldCategory
    segment: Segment


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
class Label:
    text: str
    position: Point  # centre of the text
    size: float


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
    label: Label | None
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


def _flap_cut(
    start: Point, end: Point, sagitta: float, bulge: Point, notch_radius: float | None
) -> list[Segment]:
    """The cut edge of one flap, optionally interrupted by a semicircular thumb notch
    centred on the arc's apex and biting into the flap."""
    arc = arc_from_chord(start, end, sagitta, bulge)
    if not notch_radius:
        return [arc]
    c, rc, r = arc.center, arc.radius, notch_radius
    apex = arc.point_at(0.5)
    u = _unit(_sub(apex, c))
    # Intersection of the notch circle (centre apex, radius r) with the cut circle.
    a = (2 * rc * rc - r * r) / (2 * rc)
    h = math.sqrt(rc * rc - a * a)
    base = _add(c, _mul(u, a))
    perp = (-u[1], u[0])
    q1, q2 = _add(base, _mul(perp, h)), _sub(base, _mul(perp, h))
    t1, t2 = arc.param_of_angle(_angle(c, q1)), arc.param_of_angle(_angle(c, q2))
    assert t1 is not None and t2 is not None
    if t1 > t2:
        (t1, q1), (t2, q2) = (t2, q2), (t1, q1)
    first = Arc(c, rc, arc.start_angle, arc.sweep * t1, arc.start, q1)
    notch = arc_through(apex, r, q1, q2, _sub(apex, _mul(u, r)))
    last = Arc(c, rc, arc.start_angle + arc.sweep * t2, arc.sweep * (1 - t2), q2, arc.end)
    return [first, notch, last]


def build_pattern(cfg: Config) -> Pattern:
    """Turn a validated config into the flat pattern: one outline, typed folds, label."""
    w, length = cfg.width, cfg.length
    g, taper = cfg.glue_tab_width, cfg.glue_tab_taper
    s_f, s_c = cfg.fold_sagitta, cfg.cut_sagitta
    notch = cfg.thumb_notch_radius if cfg.thumb_notch else None

    up, down = (0.0, -1.0), (0.0, 1.0)
    p = {
        "tl": (0.0, 0.0),
        "tm": (w, 0.0),
        "tr": (2 * w, 0.0),
        "bl": (0.0, length),
        "bm": (w, length),
        "br": (2 * w, length),
        "gt": (2 * w + g, taper),
        "gb": (2 * w + g, length - taper),
    }

    cut_ft = tuple(_flap_cut(p["tl"], p["tm"], s_c, up, notch))
    cut_bt = tuple(_flap_cut(p["tm"], p["tr"], s_c, up, notch))
    tab = (Line(p["tr"], p["gt"]), Line(p["gt"], p["gb"]), Line(p["gb"], p["br"]))
    cut_bb = tuple(_flap_cut(p["br"], p["bm"], s_c, down, notch))
    cut_fb = tuple(_flap_cut(p["bm"], p["bl"], s_c, down, notch))
    free_edge = Line(p["bl"], p["tl"])
    outline = Outline((*cut_ft, *cut_bt, *tab, *cut_bb, *cut_fb, free_edge))

    folds = (
        Fold("front-top", FoldCategory.CURVED, arc_from_chord(p["tl"], p["tm"], s_f, down)),
        Fold("back-top", FoldCategory.CURVED, arc_from_chord(p["tm"], p["tr"], s_f, down)),
        Fold("front-bottom", FoldCategory.CURVED, arc_from_chord(p["bl"], p["bm"], s_f, up)),
        Fold("back-bottom", FoldCategory.CURVED, arc_from_chord(p["bm"], p["br"], s_f, up)),
        Fold("panels", FoldCategory.STRAIGHT, Line(p["tm"], p["bm"])),
        Fold("glue-tab", FoldCategory.GLUE, Line(p["tr"], p["br"])),
    )

    f_ft, f_bt, f_fb, f_bb, f_mid, f_glue = (f.segment for f in folds)

    def rev(chain: Sequence[Segment]) -> tuple[Segment, ...]:
        return tuple(seg.reversed() for seg in reversed(chain))

    faces = (
        Face(
            "front-panel",
            "panel",
            (f_ft, f_mid, f_fb.reversed(), free_edge),
            0.0,
            w,
            (f_ft,),
            (f_fb,),
        ),
        Face(
            "back-panel",
            "panel",
            (f_bt, f_glue, f_bb.reversed(), f_mid.reversed()),
            w,
            2 * w,
            (f_bt,),
            (f_bb,),
        ),
        Face("glue-tab", "tab", (*tab, f_glue.reversed()), 2 * w, 2 * w + g, tab[:1], tab[2:]),
        Face("front-top-flap", "flap", (*cut_ft, f_ft.reversed()), 0.0, w, cut_ft, (f_ft,)),
        Face("back-top-flap", "flap", (*cut_bt, f_bt.reversed()), w, 2 * w, cut_bt, (f_bt,)),
        Face("front-bottom-flap", "flap", (*cut_fb, f_fb), 0.0, w, (f_fb,), rev(cut_fb)),
        Face("back-bottom-flap", "flap", (*cut_bb, f_bb), w, 2 * w, (f_bb,), rev(cut_bb)),
    )

    label = (
        Label(cfg.label_text.strip(), (w / 2, length / 2), cfg.label_size) if cfg.label else None
    )
    bbox = union_bbox([outline.bbox(), *(f.segment.bbox() for f in folds)])

    fold_arc = folds[0].segment
    info = {
        "pattern_width": bbox[2] - bbox[0],
        "pattern_height": bbox[3] - bbox[1],
        "fold_sagitta": s_f,
        "cut_sagitta": s_c,
        "fold_radius": circle_radius(w, s_f),
        "cut_radius": circle_radius(w, s_c),
        "fold_arc_length": fold_arc.length,
        "box_depth": cfg.box_depth,
        "closed_width": CrossSection(w, s_f).closed_width,
        # Shallower tapers let the glued tab reach past the curved fold near the corners.
        "min_glue_tab_taper": g * fold_slope(w, s_f),
    }
    return Pattern(outline, folds, faces, label, bbox, info)


# --------------------------------------------------------------------------- 3D model
def fold_slope(width: float, sagitta: float) -> float:
    """|f'| at the panel corners: tangent of the angle the fold arc makes with its chord."""
    r = circle_radius(width, sagitta)
    return (width / 2) / (r - sagitta)


class CrossSection:
    """Cross-section of a closed panel, parametrised by arc length ``u`` in ``[0, W]``:
    ``Z(u) = f(u)`` (the crease offset) and ``X'(u) = sqrt(1 - f'(u)^2)``, centred on X = 0.

    With ``u - W/2 = R sin(psi)``, ``X = R * E(psi)`` where ``E(psi) = int_0^psi sqrt(cos 2t) dt``,
    evaluated with a Simpson table plus a Simpson remainder."""

    TABLE = 512

    def __init__(self, width: float, sagitta: float) -> None:
        self.width = width
        self.sagitta = sagitta
        self.radius = circle_radius(width, sagitta)
        self.psi_max = math.asin(min(1.0, (width / 2) / self.radius))
        if self.psi_max >= math.pi / 4:
            raise ValueError("fold arc too steep to close (sagitta must be < 0.207 * width)")
        self._step = self.psi_max / self.TABLE
        table = [0.0]
        for k in range(self.TABLE):
            a = k * self._step
            table.append(table[-1] + _simpson(a, a + self._step, 4))
        self._table = table

    def e(self, psi: float) -> float:
        sign = -1.0 if psi < 0 else 1.0
        psi = min(abs(psi), self.psi_max)
        k = min(int(psi / self._step), self.TABLE - 1)
        a = k * self._step
        return sign * (self._table[k] + _simpson(a, psi, 4))

    def x(self, u: float) -> float:
        d = min(1.0, max(-1.0, (u - self.width / 2) / self.radius))
        return self.radius * self.e(math.asin(d))

    def z(self, u: float) -> float:
        return sagitta_offset(self.width, self.sagitta, min(self.width, max(0.0, u)))

    @property
    def closed_width(self) -> float:
        return 2 * self.radius * self.e(self.psi_max)


def _simpson(a: float, b: float, n: int) -> float:
    """Composite Simpson rule for sqrt(cos 2t) on [a, b] (n even)."""
    if b == a:
        return 0.0
    h = (b - a) / n
    total = 0.0
    for i in range(n + 1):
        w = 1 if i in (0, n) else (4 if i % 2 else 2)
        total += w * math.sqrt(max(0.0, math.cos(2 * (a + i * h))))
    return total * h / 3


Point3 = tuple[float, float, float]


class FoldedBox:
    """Maps flat-pattern points of each face to their position in the closed box.

    3D frame: millimetres, X across the box, Y along the straight edges (up, centred), Z depth
    (front panel at +Z)."""

    def __init__(self, cfg: Config) -> None:
        self.width = cfg.width
        self.length = cfg.length
        self.section = CrossSection(cfg.width, cfg.fold_sagitta)

    def map(self, face: str, p: Point) -> Point3:
        w, length, sec = self.width, self.length, self.section
        x, y = p
        if face == "front-panel":
            pos = (sec.x(x), y, sec.z(x))
        elif face == "front-top-flap":  # reflected across the crease plane y = Z
            pos = (sec.x(x), sec.z(x), y)
        elif face == "front-bottom-flap":  # reflected across y + Z = L
            pos = (sec.x(x), length - sec.z(x), length - y)
        elif face == "back-panel":
            u = x - w
            pos = (-sec.x(u), y, -sec.z(u))
        elif face == "back-top-flap":  # reflected across y = -Z
            u = x - w
            pos = (-sec.x(u), sec.z(u), -y)
        elif face == "back-bottom-flap":  # reflected across y - Z = L
            u = x - w
            pos = (-sec.x(u), length - sec.z(u), y - length)
        elif face == "glue-tab":  # glued to the inside of the front panel's free edge
            u = x - 2 * w
            pos = (sec.x(u), y, sec.z(u))
        else:
            raise KeyError(face)
        return (pos[0], length / 2 - pos[1], pos[2])


def _face_columns(face: Face, step: float) -> list[float]:
    n = max(24, min(160, math.ceil((face.x1 - face.x0) / step)))
    xs = {face.x0 + (face.x1 - face.x0) * i / n for i in range(n + 1)}
    for seg in (*face.lower, *face.upper):  # keep chain breakpoints (e.g. notch corners)
        xs.update(q[0] for q in (seg.start, seg.end))
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
                "points": [[round(c, 6) for c in pt] for pt in pts],
            }
        )

    return {
        "units": "mm",
        "parts": parts,
        "lines": lines,
        "bounds": {
            "width": box.section.closed_width,
            "length": cfg.length,
            "depth": cfg.box_depth,
        },
    }


def _flat_area(flat: list[float], tri: tuple[int, int, int]) -> float:
    (ax, ay), (bx, by), (cx, cy) = ((flat[2 * i], flat[2 * i + 1]) for i in tri)
    return abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2
