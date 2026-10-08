"""Dimension annotations for the preview views, one per input parameter they illustrate.

Pure functions (no Flask, no SVG). Every dimension names the config field it shows
(``param``, or None for derived values), the points it measures (``points``, which lie on the
actual geometry), and the measured ``value``. Views only decide how to draw them; the
values themselves always come from the same geometry as the pattern and the 3D model.

Kinds:

* ``horizontal`` / ``vertical`` (2D): ``points`` = two measured points; ``value`` is their
  x / y distance; the dimension line is drawn at ``at`` (y for horizontal, x for vertical).
* ``radius`` (2D): ``points`` = (centre, point on the arc).
* ``path`` (2D): ``points`` = polyline along the measured curve (its length is ``value``);
  drawn parallel to it, ``offset`` to the left of the direction of travel.
* ``aligned3d`` / ``path3d`` (3D): ``points`` as above; ``line`` is the polyline to draw,
  ``extensions`` the extension lines and ``label_at`` the label anchor (all precomputed).
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Any

from yanartas_pillowbox.config import Config
from yanartas_pillowbox.geometry import Arc, CrossSection, FoldedBox, Pattern, Point, Point3
from yanartas_pillowbox.svg import MARGIN

Coords = tuple[float, ...]


@dataclass(frozen=True)
class Dimension:
    param: str | None
    label: str
    kind: str
    points: tuple[Coords, ...]
    value: float
    at: float | None = None
    offset: float | None = None
    line: tuple[Coords, ...] = ()
    extensions: tuple[tuple[Coords, Coords], ...] = ()
    label_at: Coords | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "param": self.param,
            "label": self.label,
            "kind": self.kind,
            "value": self.value,
            "points": [_r(p) for p in self.points],
        }
        if self.at is not None:
            out["at"] = round(self.at, 6)
        if self.offset is not None:
            out["offset"] = round(self.offset, 6)
        if self.line:
            out["line"] = [_r(p) for p in self.line]
        if self.extensions:
            out["extensions"] = [[_r(a), _r(b)] for a, b in self.extensions]
        if self.label_at is not None:
            out["labelAt"] = _r(self.label_at)
        return out


def _r(p: Coords) -> list[float]:
    return [round(c, 6) for c in p]


def fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def arc_param(cfg: Config) -> tuple[str, str]:
    """(param, label) for the curved-fold sagitta, depending on how the arc is specified."""
    s = cfg.fold_sagitta
    if cfg.arc_mode == "depth":
        return "depth", f"depth/2 = {fmt(s)}"
    return "sagitta", f"sagitta {fmt(s)}"


def depth_param(cfg: Config) -> tuple[str, str]:
    if cfg.arc_mode == "depth":
        return "depth", f"depth {fmt(cfg.box_depth)}"
    return "sagitta", f"2 × sagitta = {fmt(cfg.box_depth)}"  # noqa: RUF001


def polyline_length(pts: list[Coords]) -> float:
    return sum(math.dist(a, b) for a, b in itertools.pairwise(pts))


# ------------------------------------------------------------------------- 2D pattern
def pattern_dimensions(cfg: Config, pattern: Pattern, offset: Point) -> list[Dimension]:
    """Dimensions for the flat pattern, in SVG user units (flat coordinates + ``offset``)."""
    w, length, g, taper = cfg.width, cfg.length, cfg.glue_tab_width, cfg.glue_tab_taper
    dx, dy = offset
    x0, y0, x1, y1 = pattern.bbox
    # Dimension lines sit outside the sheet (pattern + margin), so they never cover it.
    gap = MARGIN + max(4.0, 0.04 * max(x1 - x0, y1 - y0))

    def p(x: float, y: float) -> Coords:
        return (x + dx, y + dy)

    dims = [
        Dimension(
            "width",
            f"width {fmt(w)}",
            "horizontal",
            (p(0, length), p(w, length)),
            w,
            at=y1 + dy + gap,
        ),
        Dimension(
            "length",
            f"length {fmt(length)}",
            "vertical",
            (p(0, 0), p(0, length)),
            length,
            at=x0 + dx - gap,
        ),
        Dimension(
            "glue_tab_width",
            f"tab {fmt(g)}",
            "horizontal",
            (p(2 * w, length), p(2 * w + g, length - taper)),
            g,
            at=y1 + dy + gap,
        ),
    ]
    if taper > 0:
        dims.append(
            Dimension(
                "glue_tab_taper",
                f"taper {fmt(taper)}",
                "vertical",
                (p(2 * w, 0), p(2 * w + g, taper)),
                taper,
                at=x1 + dx + gap,
            )
        )
    # Curved-fold sagitta, measured from the corner-to-corner chord to the fold's apex (on the
    # back panel's bottom fold, away from the label and the notch dimension).
    param, label = arc_param(cfg)
    apex = pattern.fold("back-bottom").segment.point_at(0.5)
    dims.append(
        Dimension(
            param,
            label,
            "vertical",
            (p(2 * w, length), p(*apex)),
            cfg.fold_sagitta,
            at=apex[0] + dx,
        )
    )
    if cfg.thumb_notch:
        notch = next(
            s
            for s in pattern.face("front-top-flap").lower
            if isinstance(s, Arc) and math.isclose(s.radius, cfg.thumb_notch_radius)
        )
        dims.append(
            Dimension(
                "thumb_notch_radius",
                f"R {fmt(notch.radius)}",
                "radius",
                (p(*notch.center), p(*notch.point_at(0.5))),
                notch.radius,
            )
        )
    return dims


# ------------------------------------------------------------------------- cross-section
def section_dimensions(cfg: Config, section: dict[str, Any]) -> list[Dimension]:
    """Dimensions for the body cross-section, in its (X, Z) frame (Z up)."""
    front, tab = section["front"], section["tab"]
    width, depth = section["width"], section["depth"]
    span = max(width, depth)
    gap = 0.12 * span
    mid = len(front) // 2  # apex of the front panel (u = W/2)
    apex_f = tuple(front[mid])
    apex_b = (apex_f[0], -apex_f[1])
    param, label = depth_param(cfg)
    return [
        Dimension(param, label, "vertical", (apex_b, apex_f), depth, at=width / 2 + gap),
        Dimension(
            None,
            f"≈ {fmt(width)}",
            "horizontal",
            (tuple(section["back"][-1]), tuple(front[-1])),
            width,
            at=-depth / 2 - gap,
        ),
        Dimension(
            "width",
            f"width {fmt(cfg.width)} (arc)",
            "path",
            tuple(tuple(q) for q in front),
            polyline_length(front),
            offset=gap * 0.55,
        ),
        Dimension(
            "glue_tab_width",
            f"tab {fmt(cfg.glue_tab_width)}",
            "path",
            tuple(tuple(q) for q in tab),
            polyline_length(tab),
            offset=-gap * 0.5,
        ),
    ]


# ------------------------------------------------------------------------- 3D model
def model_dimensions(cfg: Config, samples: int = 48) -> list[Dimension]:
    """Dimensions for the 3D preview, in the model frame (X across, Y length, Z depth)."""
    box = FoldedBox(cfg)
    sec: CrossSection = box.section
    w, length, s_f = cfg.width, cfg.length, cfg.fold_sagitta
    half_w = sec.closed_width / 2
    gap = 0.12 * max(length, sec.closed_width)

    def add(a: Point3, v: Coords, k: float = 1.0) -> Coords:
        return tuple(a[i] + v[i] * k for i in range(3))

    dims: list[Dimension] = []

    # Length: along the straight fold (+X), drawn further out in +X.
    a, b = (half_w, -length / 2, 0.0), (half_w, length / 2, 0.0)
    off = (gap, 0.0, 0.0)
    la, lb = add(a, off), add(b, off)
    dims.append(
        Dimension(
            "length",
            f"length {fmt(length)}",
            "aligned3d",
            (a, b),
            math.dist(a, b),
            line=(la, lb),
            extensions=((a, add(a, off, 1.15)), (b, add(b, off, 1.15))),
            label_at=tuple((la[i] + lb[i]) / 2 + off[i] * 0.4 for i in range(3)),
        )
    )

    # Depth: between the front and back apex lines where they end at the curved folds,
    # drawn beyond the end of the box.
    y_end = length / 2 - s_f
    a, b = box.map("back-panel", (1.5 * w, s_f)), box.map("front-panel", (w / 2, s_f))
    assert math.isclose(a[1], y_end) and math.isclose(b[1], y_end)
    y_line = length / 2 + gap * 0.6
    la, lb = (0.0, y_line, a[2]), (0.0, y_line, b[2])
    param, label = depth_param(cfg)
    dims.append(
        Dimension(
            param,
            label,
            "aligned3d",
            (a, b),
            math.dist(a, b),
            line=(la, lb),
            extensions=((a, (0.0, y_line + gap * 0.1, a[2])), (b, (0.0, y_line + gap * 0.1, b[2]))),
            label_at=(0.0, y_line + gap * 0.45, 0.0),
        )
    )

    # Panel width: the arc of the front panel's cross-section at mid-length.
    along = [box.map("front-panel", (w * i / samples, length / 2)) for i in range(samples + 1)]
    line: list[Coords] = []
    for i, q in enumerate(along):
        u = w * i / samples
        # Outward normal of the section (X, Z) = (-Z'(u), X'(u)); X' = sqrt(1 - Z'^2).
        h = 1e-4 * w
        dz = (sec.z(min(w, u + h)) - sec.z(max(0.0, u - h))) / (min(w, u + h) - max(0.0, u - h))
        dz = max(-1.0, min(1.0, dz))
        nx, nz = -dz, math.sqrt(1 - dz * dz)
        line.append((q[0] + nx * gap * 0.5, q[1], q[2] + nz * gap * 0.5))
    dims.append(
        Dimension(
            "width",
            f"width {fmt(w)}",
            "path3d",
            tuple(along),
            polyline_length(list(along)),
            line=tuple(line),
            extensions=((along[0], line[0]), (along[-1], line[-1])),
            label_at=add(line[samples // 2], (0.0, 0.0, gap * 0.35)),
        )
    )
    return dims


def to_json(dims: list[Dimension]) -> list[dict[str, Any]]:
    return [d.to_json() for d in dims]
