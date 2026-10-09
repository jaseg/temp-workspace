"""OpenSCAD model of the box's interior: the main (payload) space, and with interior walls the
two end spaces between each inner flap and its interior wall.

Every space is an exact intersection of two prisms, because each of its walls is a cylinder
ruled along one axis (frame of the 3D model: X across, Y along the length, Z height, centred
on the interior):

* the cross-section prism (along Y), bounded by the panels' inner surfaces, or for an end
  space by the bridge's underside and the back panel's inner surface;
* the plan prism (along Z), bounded by the end walls' surfaces facing the space.

The FPC trough in a bridge and the inner flaps' cut corners are left out.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence

from yanartas_pillowbox import __version__
from yanartas_pillowbox.config import Config
from yanartas_pillowbox.crosssection import Body
from yanartas_pillowbox.geometry import WallLayout, _interior, _interp, wall_layout

Point = tuple[float, float]


def _samples(width: float) -> int:
    return 2 * max(16, min(80, math.ceil(width)))


def _offset_curve(mid: Callable[[float], Point], width: float, d: float, ext: float) -> list[Point]:
    """(X, Y) samples, sorted by X, of a plan curve ``mid(u)`` (u in 0..width, Y = f(X))
    offset by ``d`` towards -Y, extended along its end tangents by ``ext``."""
    n = _samples(width)
    pts = [mid(width * i / n) for i in range(n + 1)]
    pts.sort()
    out = []
    for i, (x, y) in enumerate(pts):
        (ax, ay), (bx, by) = pts[max(0, i - 1)], pts[min(n, i + 1)]
        k = math.hypot(bx - ax, by - ay)
        nx, ny = (by - ay) / k, -(bx - ax) / k  # right of +X: towards -Y
        out.append((x + d * nx, y + d * ny))
    for i, j in ((0, 1), (-1, -2)):
        (x0, y0), (x1, y1) = out[i], out[j]
        k = math.hypot(x0 - x1, y0 - y1)
        tip = (x0 + ext * (x0 - x1) / k, y0 + ext * (y0 - y1) / k)
        if i == 0:
            out.insert(0, tip)
        else:
            out.append(tip)
    return out


def _plan_curves(body: Body, layout: WallLayout | None) -> dict[str, list[Point]]:
    """Plan curves at the top end (+Y): the inner flap's inner surface, and the interior
    wall's two surfaces."""
    half, back, t = body.edge_length / 2, body.back, body.thickness
    ext = 2 * (body.inner_fold[0] - body.inner_glue[0])  # far past the interior's corners

    def flap(u: float) -> Point:
        return (body.back_point(u)[0], half - back.z(u))

    curves = {"flap": _offset_curve(flap, back.width, t / 2, ext)}
    if layout is not None:

        def wall(u: float) -> Point:  # the inner flap's mirror image, layout.strip further in
            return (body.back_point(u)[0], half - layout.strip - 2 * back.sagitta + back.z(u))

        curves["wall_in"] = _offset_curve(wall, back.width, t / 2, ext)
        curves["wall_out"] = _offset_curve(wall, back.width, -t / 2, ext)
    return curves


def _span(body: Body, layout: WallLayout) -> tuple[float, float]:
    """X range of the bridge and interior wall."""
    xa, xb = body.back_point(layout.ua)[0], body.back_point(layout.ub)[0]
    return min(xa, xb), max(xa, xb)


def main_plan(cfg: Config) -> list[Point]:
    """Plan outline of the main space: up to the interior walls (where they are), and to the
    inner flaps elsewhere; the bottom end mirrors the top."""
    body = cfg.body
    layout = wall_layout(cfg)
    curves = _plan_curves(body, layout)
    flap = curves["flap"]
    if layout is None:
        top = flap
    else:
        x0, x1 = _span(body, layout)
        wall = curves["wall_in"]
        inside = sorted({x0, x1, *(x for x, _ in wall if x0 < x < x1)})
        top = [
            *((x, y) for x, y in flap if x < x0),
            (x0, _interp(flap, x0)),
            *((x, _interp(wall, x)) for x in inside),
            (x1, _interp(flap, x1)),
            *((x, y) for x, y in flap if x > x1),
        ]
    return [*top, *((x, -y) for x, y in reversed(top))]


def end_plan(cfg: Config) -> list[Point]:
    """Plan outline of the top end space, between the inner flap and the interior wall."""
    body = cfg.body
    layout = wall_layout(cfg)
    assert layout is not None
    curves = _plan_curves(body, layout)
    x0, x1 = _span(body, layout)
    xs = sorted({x0, x1, *(x for x, _ in curves["flap"] if x0 < x < x1)})
    return [
        *((x, _interp(curves["wall_out"], x)) for x in xs),
        *((x, _interp(curves["flap"], x)) for x in reversed(xs)),
    ]


def main_section(cfg: Config) -> list[Point]:
    """(X, Z) outline of the main space: the panels' inner surfaces."""
    return [(x, z) for x, z in _interior(cfg.body, _samples(cfg.body.front.width))]


def end_section(cfg: Config) -> list[Point]:
    """(X, Z) outline of an end space over the walls' span: from the back panel's inner
    surface up to the bridge's underside (1.5 t inside the front panel's mid-surface)."""
    body, t = cfg.body, cfg.thickness
    layout = wall_layout(cfg)
    assert layout is not None
    x0, x1 = _span(body, layout)
    n = _samples(x1 - x0)
    xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
    return [
        *((x, body.surface_z("back", -t / 2, x)) for x in xs),
        *((x, body.surface_z("front", -1.5 * t, x)) for x in reversed(xs)),
    ]


def _poly(pts: Sequence[Point]) -> str:
    rows = ",\n".join(f"    [{x:.4f}, {y:.4f}]" for x, y in pts)
    return f"polygon([\n{rows}\n  ]);"


def render_scad(cfg: Config) -> str:
    """The OpenSCAD source of the interior model."""
    body = cfg.body
    layout = wall_layout(cfg)
    reach = body.edge_length + 2 * cfg.height + 10  # prism lengths: past every bound
    extrude = f"linear_extrude(height = {reach:.4f}, center = true, convexity = 4)"
    lines = [
        f"// Pillow box interior, generated by yanartas-pillowbox {__version__}. Units: mm.",
        "// Frame: X across the box, Y along its length, Z its height (front panel at +Z),",
        "// centred on the interior. The material itself is not modelled.",
        f"// Interior {cfg.width:g} x {cfg.length:g} x {cfg.height:g} mm (W x L x H),"
        f" material {cfg.thickness:g} mm.",
        f"// config: {json.dumps(cfg.to_dict(), separators=(',', ':'))}",
        "",
        "// The space for the payload, bounded by the panels and by the interior walls (or the",
        "// inner end flaps).",
        "module main_space() {",
        "  intersection() {",
        f"    rotate([90, 0, 0]) {extrude} main_section();",
        f"    {extrude} main_plan();",
        "  }",
        "}",
        "",
        "module main_section() {",
        "  " + _poly(main_section(cfg)),
        "}",
        "",
        "module main_plan() {",
        "  " + _poly(main_plan(cfg)),
        "}",
        "",
    ]
    if layout is not None:
        lines += [
            "// The space between the inner end flap and the interior wall, under the bridge,",
            "// at the +Y end (end_spaces() places both).",
            "module end_space() {",
            "  intersection() {",
            f"    rotate([90, 0, 0]) {extrude} end_section();",
            f"    {extrude} end_plan();",
            "  }",
            "}",
            "",
            "module end_spaces() {",
            "  end_space();",
            "  mirror([0, 1, 0]) end_space();",
            "}",
            "",
            "module end_section() {",
            "  " + _poly(end_section(cfg)),
            "}",
            "",
            "module end_plan() {",
            "  " + _poly(end_plan(cfg)),
            "}",
            "",
        ]
    lines += [
        "// The payload (width x depth x height, centred).",
        "module payload() {",
        f"  cube([{cfg.payload_width:g}, {cfg.payload_depth:g}, {cfg.payload_height:g}],"
        " center = true);",
        "}",
        "",
        'color("SkyBlue") main_space();',
    ]
    if layout is not None:
        lines.append('color("Orchid") end_spaces();')
    if cfg.payload_width > 0 and cfg.payload_depth > 0 and cfg.payload_height > 0:
        lines.append("%payload();  // preview only")
    return "\n".join(lines) + "\n"
