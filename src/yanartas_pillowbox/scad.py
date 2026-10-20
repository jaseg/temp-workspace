"""OpenSCAD model of the box's interior: the main (payload) space, and with an end wall gap
the two end spaces between each outer end wall and the inner end wall inside it.

Every space is an exact intersection of two prisms, because each of its walls is a cylinder
ruled along one axis (frame of the 3D model: X across, Y along the length, Z height, centred
on the interior):

* the cross-section prism (along Y), bounded by the panels' inner surfaces, or for an end
  space by the front panel's inner surface and the lid's inner surface (the back panel
  stops at the inner wall; the lid covers the gap);
* the plan prism (along Z), bounded by the end walls' surfaces facing the space.

The inner flaps' cut corners and FPC cutouts are left out.
"""

from __future__ import annotations

import itertools
import json
import math
from collections.abc import Callable, Sequence

from yanartas_pillowbox import __version__
from yanartas_pillowbox.config import Config
from yanartas_pillowbox.crosssection import curve_samples
from yanartas_pillowbox.geometry import _interior, lid_layout

Point = tuple[float, float]


def _offset_curve(mid: Callable[[float], Point], width: float, d: float, ext: float) -> list[Point]:
    """(X, Y) samples, sorted by X, of a plan curve ``mid(u)`` (u in 0..width, Y = f(X))
    offset by ``d`` towards -Y, extended along its end tangents by ``ext``."""
    n = curve_samples(width)
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


def _interp(samples: Sequence[Point], x: float) -> float:
    """y of the x-sorted polyline at ``x`` (clamped at its ends)."""
    for (x0, y0), (x1, y1) in itertools.pairwise(samples):
        if x0 <= x <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return samples[0][1] if x < samples[0][0] else samples[-1][1]


def _spread(cfg: Config) -> float:
    lid = lid_layout(cfg)
    return 0.0 if lid is None else lid.spread


def _front_point(cfg: Config, u: float) -> Point:
    """The front panel's mid-surface (X, Z) at flat u, its section continued past the
    panel's edges (the widened end sections)."""
    shell = cfg.shell
    return (shell.front_x + shell.front.x_ext(u), shell.z_shift + shell.front.z_ext(u))


def _plan_curves(cfg: Config) -> dict[str, list[Point]]:
    """Plan curves at the top end (+Y): the inner wall's two surfaces and the outer wall's
    inner surface (across the widened end section)."""
    shell, t = cfg.shell, cfg.thickness
    half, front, back = shell.edge_length / 2, shell.front, shell.back
    ext = 2 * (shell.inner_fold[0] - shell.inner_glue[0])  # far past the interior's corners
    sp = _spread(cfg)

    def inner(u: float) -> Point:
        return (shell.back_point(u)[0], half - back.z(u))

    def outer(v: float) -> Point:  # the front panel runs on by the gap, and wider
        return (_front_point(cfg, v - sp)[0], half + cfg.end_wall_gap - front.z_ext(v - sp))

    return {
        "inner_in": _offset_curve(inner, back.width, t / 2, ext),
        # (only where the inner wall is: beyond it the end space ends at its corner line)
        "inner_out": _offset_curve(inner, back.width, -t / 2, 0.0),
        "outer_in": _offset_curve(outer, front.width + 2 * sp, t / 2, ext),
    }


def main_plan(cfg: Config) -> list[Point]:
    """Plan outline of the main space, between the inner end walls; the bottom end mirrors
    the top."""
    top = _plan_curves(cfg)["inner_in"]
    return [*top, *((x, -y) for x, y in reversed(top))]


def _front_inner(cfg: Config, x: float) -> float:
    """Z of the front panel's inner surface at ``X = x``, across the widened end section."""
    shell, t, sp = cfg.shell, cfg.thickness, _spread(cfg)
    sec = shell.front

    def at(u: float) -> Point:
        (px, pz), k = _front_point(cfg, u), sec.slope_ext(u)
        return (px + t / 2 * k, pz - t / 2 * math.sqrt(1 - k * k))  # inward: -normal

    lo, hi = -sp, sec.width + sp
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if at(mid)[0] < x else (lo, mid)
    return at((lo + hi) / 2)[1]


def _lid_inner(cfg: Config, x: float) -> float:
    """Z of the lid's inner surface at ``X = x``: the lid is the front panel turned over
    about ``Z = zs + level / 2`` (``geometry.LidLayout``), its inner surface the image of the
    front panel's."""
    shell, lid = cfg.shell, lid_layout(cfg)
    assert lid is not None
    return 2 * shell.z_shift + lid.level - _front_inner(cfg, x)


def _end_span(cfg: Config) -> tuple[float, float]:
    """X range of the end spaces: as far across the widened end section as the front panel's
    inner surface lies above the lid's."""

    def room(x: float) -> float:
        return _front_inner(cfg, x) - _lid_inner(cfg, x)

    def edge(inside: float, outside: float) -> float:
        if room(outside) > 0:
            return outside
        for _ in range(80):
            mid = (inside + outside) / 2
            inside, outside = (mid, outside) if room(mid) > 0 else (inside, mid)
        return inside

    sp, w = _spread(cfg), cfg.shell.front.width
    return edge(0.0, _front_point(cfg, -sp)[0]), edge(0.0, _front_point(cfg, w + sp)[0])


def end_plan(cfg: Config) -> list[Point]:
    """Plan outline of the top end space, between the inner and the outer end wall."""
    curves = _plan_curves(cfg)
    x0, x1 = _end_span(cfg)
    xs = sorted({x0, x1, *(x for x, _ in curves["outer_in"] if x0 < x < x1)})
    return [
        *((x, _interp(curves["inner_out"], x)) for x in xs),
        *((x, _interp(curves["outer_in"], x)) for x in reversed(xs)),
    ]


def main_section(cfg: Config) -> list[Point]:
    """(X, Z) outline of the main space: the panels' inner surfaces."""
    return [(x, z) for x, z in _interior(cfg.shell, curve_samples(cfg.shell.front.width))]


def end_section(cfg: Config) -> list[Point]:
    """(X, Z) outline of an end space: from the lid's inner surface up to the front panel's
    inner surface, across the widened end section."""
    x0, x1 = _end_span(cfg)
    n = curve_samples(x1 - x0)
    xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
    return [
        *((x, _lid_inner(cfg, x)) for x in xs),
        *((x, _front_inner(cfg, x)) for x in reversed(xs[1:-1])),
    ]


def _poly(pts: Sequence[Point]) -> str:
    rows = ",\n".join(f"    [{x:.4f}, {y:.4f}]" for x, y in pts)
    return f"polygon([\n{rows}\n  ]);"


def render_scad(cfg: Config) -> str:
    """The OpenSCAD source of the interior model."""
    gap = cfg.end_wall_gap > 0
    reach = cfg.front_length + 2 * cfg.height + 10  # prism lengths: past every bound
    extrude = f"linear_extrude(height = {reach:.4f}, center = true, convexity = 4)"
    lines = [
        f"// Pillow box interior, generated by yanartas-pillowbox {__version__}. Units: mm.",
        "// Frame: X across the box, Y along its length, Z its height (front panel at +Z),",
        "// centred on the interior. The material itself is not modelled.",
        f"// Interior {cfg.width:g} x {cfg.length:g} x {cfg.height:g} mm (W x L x H),"
        f" material {cfg.thickness:g} mm.",
        f"// config: {json.dumps(cfg.to_dict(), separators=(',', ':'))}",
        "",
        "// The space for the payload, bounded by the panels and the inner end walls.",
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
    if gap:
        lines += [
            "// The space between the inner and the outer end wall, from the front panel to the",
            "// lid, at the +Y end (end_spaces() places both).",
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
    if gap:
        lines.append('color("Orchid") end_spaces();')
    if cfg.payload_width > 0 and cfg.payload_depth > 0 and cfg.payload_height > 0:
        lines.append("%payload();  // preview only")
    return "\n".join(lines) + "\n"
