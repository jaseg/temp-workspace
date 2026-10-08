"""Pure pillow box geometry (no Flask, no SVG).

Flat-pattern coordinate system: millimetres, x to the right, y *down* (same orientation as
SVG). The front panel occupies ``0 <= x <= W``, the back panel ``W <= x <= 2W`` and the glue
tab ``2W <= x <= 2W + g``. The straight body edges run from ``y = 0`` to ``y = L``; the
lens-shaped closing flaps stick out above ``y = 0`` and below ``y = L``.

Each flap is bounded by two circular arcs through the panel corners:

* the **curved fold**, bowing *into* the panel by the fold sagitta ``s_f``;
* the **cut edge**, bowing *out* of the panel by ``s_c = s_f - t/2``.

Design model: when the box is closed, the two creases at one end face each other and form a
lens of total height ``2 s_f`` (the box depth). Folding a flap in mirrors its cut edge across
the crease, so it lands on the opposite panel's crease, i.e. the flap's outer edge closes
against a curve of exactly the same arc length. The half-thickness offset makes the flap a
touch smaller than that opening so both flaps can overlap.
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
class Pattern:
    outline: Outline
    folds: tuple[Fold, ...]
    label: Label | None
    bbox: BBox
    info: dict[str, float]


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

    segs: list[Segment] = []
    segs += _flap_cut(p["tl"], p["tm"], s_c, up, notch)
    segs += _flap_cut(p["tm"], p["tr"], s_c, up, notch)
    segs += [Line(p["tr"], p["gt"]), Line(p["gt"], p["gb"]), Line(p["gb"], p["br"])]
    segs += _flap_cut(p["br"], p["bm"], s_c, down, notch)
    segs += _flap_cut(p["bm"], p["bl"], s_c, down, notch)
    segs.append(Line(p["bl"], p["tl"]))
    outline = Outline(tuple(segs))

    folds = (
        Fold("front-top", FoldCategory.CURVED, arc_from_chord(p["tl"], p["tm"], s_f, down)),
        Fold("back-top", FoldCategory.CURVED, arc_from_chord(p["tm"], p["tr"], s_f, down)),
        Fold("front-bottom", FoldCategory.CURVED, arc_from_chord(p["bl"], p["bm"], s_f, up)),
        Fold("back-bottom", FoldCategory.CURVED, arc_from_chord(p["bm"], p["br"], s_f, up)),
        Fold("panels", FoldCategory.STRAIGHT, Line(p["tm"], p["bm"])),
        Fold("glue-tab", FoldCategory.GLUE, Line(p["tr"], p["br"])),
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
        "closed_width": closed_cross_section(w, s_f)[2],
    }
    return Pattern(outline, folds, label, bbox, info)


# --------------------------------------------------------------------------- 3D model
def closed_cross_section(width: float, bulge: float) -> tuple[float, float, float]:
    """Cross-section of one closed panel: a circular arc of arc length ``width`` (the panel
    is not stretched) and height ``bulge``. Returns (half_angle, radius, chord)."""
    target = bulge / width  # = (1 - cos θ) / (2 θ), increasing on (0, π]
    lo, hi = 1e-9, math.pi
    for _ in range(80):
        mid = (lo + hi) / 2
        if (1 - math.cos(mid)) / (2 * mid) < target:
            lo = mid
        else:
            hi = mid
    theta = (lo + hi) / 2
    radius = width / (2 * theta)
    return theta, radius, 2 * radius * math.sin(theta)


def build_model3d(cfg: Config, nu: int = 40, nv: int = 8, nf: int = 4) -> dict[str, Any]:
    """Shaded approximation of the closed box for the 3D preview.

    Frame: millimetres, X across the box, Y along the straight edges (up), Z depth. Each panel
    keeps its width as the arc length of its cross-section and bulges by the fold sagitta, so
    the closed box is ``2 s_f`` deep. Each closing flap is modelled as the surface between its
    crease and the end ridge where the two panels' corners meet.
    """
    w, length = cfg.width, cfg.length
    s_f = cfg.fold_sagitta
    theta, radius, chord = closed_cross_section(w, s_f)
    half_len = length / 2

    def section(u: float) -> tuple[float, float]:
        phi = -theta + 2 * theta * u / w
        return radius * math.sin(phi), radius * math.cos(phi) - radius * math.cos(theta)

    us = [w * i / nu for i in range(nu + 1)]
    xs_zs = [section(u) for u in us]
    # How far the crease cuts into the panel at each u, measured along the length.
    inset = [sagitta_offset(w, s_f, u) for u in us]

    def grid(
        rows: Sequence[Sequence[tuple[float, float, float]]],
    ) -> dict[str, list[float] | list[int]]:
        positions = [c for row in rows for pt in row for c in pt]
        cols = len(rows[0])
        indices: list[int] = []
        for j in range(len(rows) - 1):
            for i in range(cols - 1):
                a, b = j * cols + i, j * cols + i + 1
                c, d = a + cols, b + cols
                indices += [a, b, d, a, d, c]
        return {"positions": [round(v, 5) for v in positions], "indices": indices}

    parts: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    for side, zs in (("front", 1.0), ("back", -1.0)):
        rows = []
        for j in range(nv + 1):
            row = []
            for (x, z), d in zip(xs_zs, inset, strict=True):
                y_flat = d + (length - 2 * d) * j / nv
                row.append((x, half_len - y_flat, zs * z))
            rows.append(row)
        parts.append({"name": f"{side}-panel", "kind": "panel", **grid(rows)})
        for end, ys in (("top", 1.0), ("bottom", -1.0)):
            crease = [
                (x, ys * (half_len - d), zs * z) for (x, z), d in zip(xs_zs, inset, strict=True)
            ]
            ridge = [(x, ys * half_len, 0.0) for x, _ in xs_zs]
            flap_rows = [
                [
                    tuple(c + (r - c) * k / nf for c, r in zip(cp, rp, strict=True))
                    for cp, rp in zip(crease, ridge, strict=True)
                ]
                for k in range(nf + 1)
            ]
            parts.append({"name": f"{side}-{end}-flap", "kind": "flap", **grid(flap_rows)})
            lines.append({"category": FoldCategory.CURVED.value, "points": crease})

    lines.append(
        {
            "category": FoldCategory.STRAIGHT.value,
            "points": [(chord / 2, -half_len, 0.0), (chord / 2, half_len, 0.0)],
        }
    )
    lines.append(
        {
            "category": FoldCategory.GLUE.value,
            "points": [(-chord / 2, -half_len, 0.0), (-chord / 2, half_len, 0.0)],
        }
    )
    for line in lines:
        line["points"] = [[round(c, 5) for c in pt] for pt in line["points"]]

    return {
        "units": "mm",
        "parts": parts,
        "lines": lines,
        "bounds": {"width": chord, "length": length, "depth": 2 * s_f},
    }
