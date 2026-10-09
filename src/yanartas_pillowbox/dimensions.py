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
from yanartas_pillowbox.geometry import FoldedBox, Pattern, Point, Point3
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
    """Dimensions for the flat pattern, in SVG user units (flat coordinates + ``offset``).

    Width, length and height are interior dimensions: where they are measured inside the
    material, the measured points sit off the drawn lines by the material allowance."""
    body = cfg.body
    wf, wb = body.front.width, body.back.width
    edge, g, taper, t = cfg.edge_length, cfg.glue_tab_width, cfg.glue_tab_taper, cfg.thickness
    dx, dy = offset
    x0, y0, x1, y1 = pattern.bbox
    # Outer dimension lines sit outside the sheet (pattern + margin), so they never cover it.
    gap = MARGIN + max(4.0, 0.04 * max(x1 - x0, y1 - y0))

    def p(x: float, y: float) -> Coords:
        return (x + dx, y + dy)

    # Interior length along the front panel's midline: the inner end walls' inner surfaces
    # stand 1.5 t inside the front panel's curved folds (outer wall, then inner wall).
    ya, yb = body.front.sagitta + 1.5 * t, edge - body.front.sagitta - 1.5 * t
    # Interior height across the back panel's top (inner) flap: from t/2 inside the fold (the
    # back panel's inner surface) to the cut edge (the front panel's inner surface).
    xh = wf + wb / 2
    y_cut = pattern.face("back-top-flap").y_range(xh)[0]
    dims = [
        # The two panels, flat, are the closed cross-section's full circumference (computed
        # from the box width, height and thickness; not an input).
        Dimension(
            "circumference",
            f"circumference {fmt(wf + wb)}",
            "horizontal",
            (p(0, edge), p(wf + wb, edge)),
            wf + wb,
            at=y1 + dy + gap,
        ),
        Dimension(
            "length",
            f"length {fmt(cfg.length)}",
            "vertical",
            (p(wf / 2, ya), p(wf / 2, yb)),
            yb - ya,
            at=wf / 2 + dx,
        ),
        Dimension(
            "height",
            f"height {fmt(cfg.height)}",
            "vertical",
            (p(xh, body.back.sagitta - t / 2), p(xh, y_cut)),
            body.back.sagitta - t / 2 - y_cut,
            at=xh + dx,
        ),
        # Glue tab: width and taper both dimensioned at the tab's bottom end.
        Dimension(
            "glue_tab_width",
            f"tab {fmt(g)}",
            "horizontal",
            (p(wf + wb, edge), p(wf + wb + g, edge - taper)),
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
                (p(wf + wb, edge), p(wf + wb + g, edge - taper)),
                taper,
                at=x1 + dx + gap,
            )
        )
    return dims


# ------------------------------------------------------------------------- cross-section
def section_dimensions(cfg: Config, section: dict[str, Any]) -> list[Dimension]:
    """Dimensions for the body cross-section, in its (X, Z) frame (Z up). Width and height
    are measured on the interior (the material's inner surfaces)."""
    front, inner = section["front"], section["inner"]
    x0, z0, x1, z1 = section["bbox"]
    gap = 0.12 * max(x1 - x0, z1 - z0)
    return [
        Dimension(
            "height",
            f"height {fmt(cfg.height)}",
            "vertical",
            (tuple(inner["back_apex"]), tuple(inner["front_apex"])),
            inner["front_apex"][1] - inner["back_apex"][1],
            at=x1 + gap,
        ),
        Dimension(
            "width",
            f"width {fmt(cfg.width)}",
            "horizontal",
            (tuple(inner["glue"]), tuple(inner["fold"])),
            inner["fold"][0] - inner["glue"][0],
            at=z0 - gap,
        ),
        # Part of the (computed) circumference: the front panel's arc.
        Dimension(
            "circumference",
            f"front panel {fmt(cfg.body.front.width)}",
            "path",
            tuple(tuple(q) for q in front),
            polyline_length(front),
            offset=gap * 0.55,
        ),
    ]


# ------------------------------------------------------------------------- 3D model
def model_dimensions(cfg: Config) -> list[Dimension]:
    """Dimensions for the 3D preview, in the model frame (X across, Y length, Z height),
    measured on the interior."""
    box = FoldedBox(cfg)
    body = box.body
    wf, length, s_f, t = body.front.width, cfg.edge_length, body.front.sagitta, cfg.thickness
    x0, x1 = body.inner_glue[0], body.inner_fold[0]
    gap = 0.12 * max(length, x1 - x0)

    def add(a: Point3, v: Coords, k: float = 1.0) -> Coords:
        return tuple(a[i] + v[i] * k for i in range(3))

    dims: list[Dimension] = []

    # Length: along the front panel's midline (its top ridge), between the inner end walls'
    # inner surfaces, 1.5 t inside the front's curved folds; drawn above the box.
    a = box.map("front-panel", (wf / 2, s_f + 1.5 * t))
    b = box.map("front-panel", (wf / 2, length - s_f - 1.5 * t))
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

    # Height: between the panels' inner surfaces on the centreline, at the interior's end,
    # drawn beyond the end of the box.
    y_end = cfg.length / 2
    a, b = (0.0, y_end, -cfg.height / 2), (0.0, y_end, cfg.height / 2)
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

    # Width: across the interior from inner corner to inner corner, at the near end.
    z = (body.inner_glue[1] + body.inner_fold[1]) / 2
    a, b = (x0, -length / 2, z), (x1, -length / 2, z)
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
