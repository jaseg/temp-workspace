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
from yanartas_pillowbox.geometry import CrossSection, FoldedBox, Pattern, Point, Point3
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


def polyline_length(pts: list[Coords]) -> float:
    return sum(math.dist(a, b) for a, b in itertools.pairwise(pts))


# ------------------------------------------------------------------------- 2D pattern
def pattern_dimensions(cfg: Config, pattern: Pattern, offset: Point) -> list[Dimension]:
    """Dimensions for the flat pattern, in SVG user units (flat coordinates + ``offset``)."""
    w, edge, g, taper = cfg.panel_width, cfg.edge_length, cfg.glue_tab_width, cfg.glue_tab_taper
    s_f = cfg.fold_sagitta
    dx, dy = offset
    x0, y0, x1, y1 = pattern.bbox
    # Outer dimension lines sit outside the sheet (pattern + margin), so they never cover it.
    gap = MARGIN + max(4.0, 0.04 * max(x1 - x0, y1 - y0))

    def p(x: float, y: float) -> Coords:
        return (x + dx, y + dy)

    top_apex = pattern.fold("front-top").segment.point_at(0.5)
    bottom_apex = pattern.fold("front-bottom").segment.point_at(0.5)
    dims = [
        # The two panels, flat, are the closed cross-section's full circumference (computed
        # from the box width and height; not an input).
        Dimension(
            "circumference",
            f"circumference {fmt(2 * w)}",
            "horizontal",
            (p(0, edge), p(2 * w, edge)),
            2 * w,
            at=y1 + dy + gap,
        ),
        # Length along the front panel's midline, between the two curved folds' apexes.
        Dimension(
            "length",
            f"length {fmt(cfg.length)}",
            "vertical",
            (p(*top_apex), p(*bottom_apex)),
            cfg.length,
            at=top_apex[0] + dx,
        ),
        # Height: twice the fold sagitta, across the back panel's top flap, from the fold's
        # apex to where the opposite panel's fold apex lands when closed (the flap's cut
        # edge stops thickness/2 short of it).
        Dimension(
            "height",
            f"height {fmt(cfg.height)}",
            "vertical",
            (p(1.5 * w, s_f), p(1.5 * w, -s_f)),
            cfg.height,
            at=1.5 * w + dx,
        ),
        # Glue tab: width and taper both dimensioned at the tab's bottom end.
        Dimension(
            "glue_tab_width",
            f"tab {fmt(g)}",
            "horizontal",
            (p(2 * w, edge), p(2 * w + g, edge - taper)),
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
                (p(2 * w, edge), p(2 * w + g, edge - taper)),
                taper,
                at=x1 + dx + gap,
            )
        )
    return dims


# ------------------------------------------------------------------------- cross-section
def section_dimensions(cfg: Config, section: dict[str, Any]) -> list[Dimension]:
    """Dimensions for the body cross-section, in its (X, Z) frame (Z up)."""
    front = section["front"]
    width, height = section["width"], section["height"]
    span = max(width, height)
    gap = 0.12 * span
    mid = len(front) // 2  # apex of the front panel (u = W/2)
    apex_f = tuple(front[mid])
    apex_b = (apex_f[0], -apex_f[1])
    return [
        Dimension(
            "height",
            f"height {fmt(cfg.height)}",
            "vertical",
            (apex_b, apex_f),
            height,
            at=width / 2 + gap,
        ),
        Dimension(
            "width",
            f"width {fmt(cfg.width)}",
            "horizontal",
            (tuple(section["back"][-1]), tuple(front[-1])),
            width,
            at=-height / 2 - gap,
        ),
        Dimension(
            "circumference",
            f"½ circumference {fmt(cfg.panel_width)}",
            "path",
            tuple(tuple(q) for q in front),
            polyline_length(front),
            offset=gap * 0.55,
        ),
    ]


# ------------------------------------------------------------------------- 3D model
def model_dimensions(cfg: Config) -> list[Dimension]:
    """Dimensions for the 3D preview, in the model frame (X across, Y length, Z height)."""
    box = FoldedBox(cfg)
    sec: CrossSection = box.section
    w, length, s_f = cfg.panel_width, cfg.edge_length, cfg.fold_sagitta
    gap = 0.12 * max(length, sec.closed_width)

    def add(a: Point3, v: Coords, k: float = 1.0) -> Coords:
        return tuple(a[i] + v[i] * k for i in range(3))

    dims: list[Dimension] = []

    # Length: along the front panel's midline (its top ridge), between the curved folds'
    # apexes; drawn above the box.
    a, b = box.map("front-panel", (w / 2, s_f)), box.map("front-panel", (w / 2, length - s_f))
    off = (0.0, 0.0, gap * 0.6)
    la, lb = add(a, off), add(b, off)
    dims.append(
        Dimension(
            "length",
            f"length {fmt(cfg.length)}",
            "aligned3d",
            (a, b),
            math.dist(a, b),
            line=(la, lb),
            extensions=((a, add(a, off, 1.15)), (b, add(b, off, 1.15))),
            label_at=tuple((la[i] + lb[i]) / 2 + off[i] * 0.5 for i in range(3)),
        )
    )

    # Height: between the front and back apex lines where they end at the curved folds,
    # drawn beyond the end of the box.
    y_end = length / 2 - s_f
    a, b = box.map("back-panel", (1.5 * w, s_f)), box.map("front-panel", (w / 2, s_f))
    assert math.isclose(a[1], y_end) and math.isclose(b[1], y_end)
    y_line = length / 2 + gap * 0.6
    la, lb = (0.0, y_line, a[2]), (0.0, y_line, b[2])
    dims.append(
        Dimension(
            "height",
            f"height {fmt(cfg.height)}",
            "aligned3d",
            (a, b),
            math.dist(a, b),
            line=(la, lb),
            extensions=((a, (0.0, y_line + gap * 0.1, a[2])), (b, (0.0, y_line + gap * 0.1, b[2]))),
            label_at=(0.0, y_line + gap * 0.45, 0.0),
        )
    )

    # Width: across the cross-section from fold to fold, at the near end of the box.
    a, b = box.map("front-panel", (0.0, 0.0)), box.map("front-panel", (w, 0.0))
    a, b = (a[0], -length / 2, a[2]), (b[0], -length / 2, b[2])  # the -Y end
    y_line = -length / 2 - gap * 0.6
    la, lb = (a[0], y_line, 0.0), (b[0], y_line, 0.0)
    dims.append(
        Dimension(
            "width",
            f"width {fmt(cfg.width)}",
            "aligned3d",
            (a, b),
            math.dist(a, b),
            line=(la, lb),
            extensions=((a, add(la, (0.0, -gap * 0.1, 0.0))), (b, add(lb, (0.0, -gap * 0.1, 0.0)))),
            label_at=(0.0, y_line - gap * 0.35, 0.0),
        )
    )
    return dims


def to_json(dims: list[Dimension]) -> list[dict[str, Any]]:
    return [d.to_json() for d in dims]
