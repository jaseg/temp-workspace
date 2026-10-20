"""Rectangular payload inscribed, centred, in the closed pillow box. Pure functions.

Payload axes: ``payload_width`` across the box (X), ``payload_depth`` along its length (Y),
``payload_height`` along its height (Z), in the 3D model frame of ``geometry.FoldedBox``,
which is centred on the box interior.

The box surface facing the payload is the material's inner surface, ``t/2`` inside the
mid-surface the model folds: the panels (cylinders with rulings along Y, see
``crosssection.Shell``) and the inner flaps' end walls (cylinders with rulings along Z through
the back panel's creases, ``|Y| = edge/2 - Zb(u)``).

**Clearance** is the true 3D distance from the payload to the nearest point of that surface.
For a payload inside the box, the distance to the surface equals the smallest of the
distances to the *unbounded* cylinders: a nearest point on an unbounded cylinder that is not
on the real surface lies outside the interior, and the segment to it crosses the real
surface earlier. The nearest point on a cylinder shares the ruling coordinate, so each
distance is a 2D one, from a centred rectangle to a curve, minus ``t/2`` (the inner surface
is the mid-surface offset by ``t/2``):

* panels: in the cross-section (X, Z), from the payload's width x height to each panel;
* end walls: in plan (X, Y), from the payload's width x depth to the back panel's crease
  curve. Its closest point to the centre is the inner wall's apex, ``length/2`` away.

The payload fits when ``clearance >= payload_clearance``.

``fit_box`` finds the box (width, length, height only) with the smallest pattern bounding box
that keeps the clearance; see there.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace

from yanartas_pillowbox.config import SPECS_BY_NAME, Config, ConfigError
from yanartas_pillowbox.crosssection import (
    MAX_SAGITTA_RATIO,
    CrossSection,
    Shell,
    drop_at_slope,
    solve_shell,
    width_ratio,
)
from yanartas_pillowbox.geometry import MAX_SPREAD_SLOPE, max_lid_offset, min_lid_width

ROUND = 0.01  # mm: results are rounded to this grid, always towards a fitting box
SAMPLES = 1000  # curve samples for clearance computations
FIT_SAMPLES = 600

Curve = Callable[[float], tuple[float, float]]


class PayloadError(ValueError):
    """The requested payload operation is impossible. ``field`` names the culprit."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(message)


def is_empty(cfg: Config) -> bool:
    return min(cfg.payload_width, cfg.payload_depth, cfg.payload_height) <= 0


# ------------------------------------------------------------------------- clearance
def _point_rect(qx: float, qz: float, a: float, b: float) -> float:
    """Signed distance from (qx, qz) to the rectangle |x| <= a, |z| <= b: positive outside,
    negative (depth) inside."""
    dx, dz = abs(qx) - a, abs(qz) - b
    if dx <= 0 and dz <= 0:
        return max(dx, dz)
    return math.hypot(max(dx, 0.0), max(dz, 0.0))


def _grid_min(f: Callable[[float], float], grid: list[float]) -> tuple[float, float]:
    """(x, f(x)) at the minimum of f: the best grid point, refined by golden-section search
    between its neighbours (f is unimodal there)."""
    vals = [f(x) for x in grid]
    k = min(range(len(grid)), key=vals.__getitem__)
    if math.isinf(vals[k]):
        return grid[k], vals[k]
    lo, hi = grid[max(0, k - 1)], grid[min(len(grid) - 1, k + 1)]
    g = (math.sqrt(5) - 1) / 2
    c, d = hi - g * (hi - lo), lo + g * (hi - lo)
    fc, fd = f(c), f(d)
    for _ in range(40):
        if fc <= fd:
            hi, d, fd = d, c, fc
            c = hi - g * (hi - lo)
            fc = f(c)
        else:
            lo, c, fc = c, d, fd
            d = lo + g * (hi - lo)
            fd = f(d)
    return min(((grid[k], vals[k]), (c, fc), (d, fd)), key=lambda q: q[1])


def curve_clearance(curve: Curve, length: float, a: float, b: float) -> float:
    """Distance from the centred rectangle |x| <= a, |z| <= b to the curve ``curve(u)``,
    u in [0, length]; negative if the rectangle pokes through it."""

    def f(u: float) -> float:
        return _point_rect(*curve(u), a, b)

    return _grid_min(f, [length * i / SAMPLES for i in range(SAMPLES + 1)])[1]


def section_clearance(shell: Shell, width: float, height: float) -> float:
    """Distance in the cross-section from the payload rectangle (width x height, centred) to
    the panels' inner surfaces; negative if the rectangle pokes through them."""
    a, b, h = width / 2, height / 2, shell.thickness / 2
    return (
        min(
            curve_clearance(shell.front_point, shell.front.width, a, b),
            curve_clearance(shell.back_point, shell.back.width, a, b),
        )
        - h
    )


def wall_clearance(shell: Shell, width: float, depth: float) -> float:
    """Distance in plan from the payload (width x depth, centred) to the inner end walls'
    inner surfaces (the same at both ends)."""
    half = shell.edge_length / 2

    def wall(u: float) -> tuple[float, float]:
        return (shell.back_point(u)[0], half - shell.back.z(u))

    return curve_clearance(wall, shell.back.width, width / 2, depth / 2) - shell.thickness / 2


def clearance(cfg: Config) -> float | None:
    """True distance from the payload to the box surface (negative: it does not fit;
    None: no payload)."""
    if is_empty(cfg):
        return None
    shell = cfg.shell
    return min(
        section_clearance(shell, cfg.payload_width, cfg.payload_height),
        wall_clearance(shell, cfg.payload_width, cfg.payload_depth),
    )


def fits(cfg: Config, tol: float = 1e-6) -> bool:
    c = clearance(cfg)
    return c is None or c >= cfg.payload_clearance - tol


def _floor(v: float) -> float:
    return math.floor(v / ROUND + 1e-9) * ROUND


def _ceil(v: float) -> float:
    return math.ceil(v / ROUND - 1e-9) * ROUND


def _r2(v: float) -> float:
    return round(v, 2)


# ------------------------------------------------------------------------- maximize
def maximize(cfg: Config, field: str) -> Config:
    """Largest value of one payload dimension that keeps the clearance in the current box."""
    m = cfg.payload_clearance
    shell = cfg.shell
    if field == "payload_depth":
        if section_clearance(shell, cfg.payload_width, cfg.payload_height) < m:
            raise PayloadError(
                "payload_width", "the payload's width and height already break the clearance"
            )

        def ok(v: float) -> bool:
            return wall_clearance(shell, cfg.payload_width, v) >= m

        if not ok(0.0):
            raise PayloadError("payload_clearance", "the clearance leaves no room along the length")
        limit = cfg.edge_length
    elif field in ("payload_width", "payload_height"):
        other = "payload_height" if field == "payload_width" else "payload_width"
        limit = cfg.width if field == "payload_width" else cfg.height

        def ok(v: float) -> bool:
            w, h = (v, cfg.payload_height) if field == "payload_width" else (cfg.payload_width, v)
            return section_clearance(shell, w, h) >= m and (
                field == "payload_height" or wall_clearance(shell, v, cfg.payload_depth) >= m
            )

        if not ok(0.0):
            axis = other.removeprefix("payload_")
            raise PayloadError(other, f"the payload {axis} leaves no room for the clearance")
    else:
        raise PayloadError(field, f"unknown payload field {field!r}")

    lo, hi = 0.0, limit  # ok(lo), not ok(hi)
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return replace(cfg, **{field: _r2(_floor(lo))})


# ------------------------------------------------------------------------- fit box
def _scale_needed(x: float, z: float, a: float, b: float, m: float) -> float:
    """Smallest scale W at which the profile point W * (x, z) is at least ``m`` away from the
    rectangle |X| <= a, |Z| <= b (the distance grows monotonically with W)."""
    wa = a / x if x > 0 else math.inf
    wb = b / z if z > 0 else math.inf
    if m <= 0:
        return min(wa, wb)
    # Past the first edge only one coordinate exceeds the rectangle ...
    if wa <= wb and wa + m / x <= wb:
        return wa + m / x
    if wb < wa and wb + m / z <= wa:
        return wb + m / z
    # ... otherwise the point clears the corner: |W (x, z) - (a, b)| = m.
    qa, qb = x * x + z * z, -2 * (a * x + b * z)
    qc = a * a + b * b - m * m
    return (-qb + math.sqrt(max(0.0, qb * qb - 4 * qa * qc))) / (2 * qa)


def _candidate(base: Config, r: float) -> tuple[float, float, float] | None:
    """(approximate pattern area, width, height) of the smallest box with sagitta ratio r
    that keeps the clearance, or None if that box violates a constraint on the untouched
    parameters. Approximates the interior by a zero-thickness box of the interior size."""
    a, b, m, t = (
        base.payload_width / 2,
        base.payload_height / 2,
        base.payload_clearance,
        base.thickness,
    )
    sec = CrossSection(1.0, r)
    panel = max(
        _scale_needed(-sec.x(u), sec.z(u), a, b, m)
        for u in (0.5 * i / FIT_SAMPLES for i in range(FIT_SAMPLES + 1))
    )
    sagitta = r * panel
    width = panel * width_ratio(r)
    length = _fit_length(base)
    if width < 10 or 2 * sagitta - t < 0.5 or base.glue_tab_width >= panel:
        return None
    if width > SPECS_BY_NAME["width"].maximum or 2 * sagitta > SPECS_BY_NAME["height"].maximum:
        return None
    # The lid offset the widened ends allow is about twice the drop at the steepest turn,
    # less the lid's resting level (about -3 t); see geometry.max_lid_offset.
    drop = drop_at_slope(panel, sagitta, MAX_SPREAD_SLOPE)
    if base.end_wall_gap > 0 and drop < (base.lid_offset + 4 * t) / 2:
        return None  # too steep at the sides to widen the ends for the lids
    # The front panel's edge, plus at both ends the outer flaps (sagitta + 1.5 t) or, with a
    # gap, the lids (about the gap, the overlap, the sagitta, 2.5 t and the lid offset beyond
    # the edge). (The overhangs' width is left out: it is small and changes slowly with r.)
    gap = base.end_wall_gap
    edge = length + 2 * sagitta + 3 * t + 2 * gap
    reach = sagitta + 1.5 * t
    if gap > 0:
        reach = gap + base.lid_overlap + sagitta + 2.5 * t + base.lid_offset
    area = (2 * panel + base.glue_tab_width) * (edge + 2 * reach)
    return area, width, 2 * sagitta


def _min_width(cfg: Config, height: float, guess: float) -> float | None:
    """Smallest interior width (to 1 um) at which the payload's cross-section keeps the
    clearance, for this height; None if there is none within the width limit."""
    t, m = cfg.thickness, cfg.payload_clearance
    w_max = SPECS_BY_NAME["width"].maximum

    def ok(w: float) -> bool:
        try:
            shell = solve_shell(w, height, cfg.length, t)
        except ValueError:  # too narrow to close at this height
            return False
        return section_clearance(shell, cfg.payload_width, cfg.payload_height) >= m

    step = 0.02 * guess + 0.5
    lo, hi = max(cfg.payload_width, guess - step), min(w_max, guess + step)
    while ok(lo) and lo > cfg.payload_width:
        lo, hi = max(cfg.payload_width, lo - 4 * step), lo
    while not ok(hi):
        if hi >= w_max:
            return None
        lo, hi = hi, min(w_max, hi + 4 * step)
    while hi - lo > 1e-3:
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if ok(mid) else (mid, hi)
    return hi


def _fit_length(cfg: Config) -> float:
    """Box length for the payload depth and clearance."""
    return max(cfg.payload_depth + 2 * cfg.payload_clearance, 10.0)


def fit_box(cfg: Config) -> Config:
    """Box (width, length, height) holding the payload with its clearance, with the smallest
    pattern bounding box. Glue tab, thickness and the lids are kept: the box is widened as far
    as the lid offset needs (see ``geometry.max_lid_offset``).

    The height comes from a fast search on an approximation: the interior as a zero-thickness
    box of the interior size, whose cross-section shape depends only on ``r = sagitta / W``
    (a 1D search over ``r``, each ``r`` giving the smallest ``W`` whose profile clears the
    payload by the clearance). The area is flat around its minimum, so the small error in the
    height costs next to nothing; the width is then solved exactly for that height, and the
    length grown until the end walls keep the clearance."""
    if is_empty(cfg):
        raise PayloadError("payload_width", "set all three payload dimensions first")
    length = _r2(_ceil(_fit_length(cfg)))

    def area(r: float) -> float:
        c = _candidate(cfg, r)
        return math.inf if c is None else c[0]

    lo_r, hi_r, n = 1e-3, MAX_SAGITTA_RATIO, 80
    r, best = _grid_min(area, [lo_r * (hi_r / lo_r) ** (i / n) for i in range(n + 1)])
    if math.isinf(best):
        raise PayloadError(
            "payload_width",
            "no valid box holds this payload with the current clearance, glue tab and thickness",
        )
    cand = _candidate(cfg, r)
    assert cand is not None
    _, width, height = cand

    # Exact width for the (rounded down) height, rounded up to the grid; then the length.
    height = _r2(_floor(height))
    base = replace(cfg, length=length, height=height)
    exact = _min_width(base, height, width)
    if exact is None:
        raise PayloadError("payload_width", "the fitted box would be wider than the limit")
    out = replace(base, width=_r2(_ceil(exact)))
    for _ in range(1000):
        shell, m = out.shell, cfg.payload_clearance
        lids_ok = out.end_wall_gap <= 0 or max_lid_offset(shell) >= out.lid_offset
        if lids_ok and fits(out):
            break
        if not lids_ok:
            # Too steep at the sides to widen the ends for the lids: a flatter (wider) box.
            wide = min_lid_width(out)
            if wide is None:
                raise PayloadError(
                    "lid_offset", "no box within the width limit allows this lid offset"
                )
            out = replace(out, width=max(wide, _r2(out.width + ROUND)))
        elif section_clearance(shell, cfg.payload_width, cfg.payload_height) < m:
            out = replace(out, width=_r2(out.width + ROUND))
        else:
            # The end walls' clearance grows by exactly half of what the length grows (the
            # walls keep their shape): one step, rounded up.
            walls = wall_clearance(shell, cfg.payload_width, cfg.payload_depth)
            length = _r2(_ceil(out.length + 2 * max(m - walls, 0.0)))
            out = replace(out, length=max(length, _r2(out.length + ROUND)))
    try:
        return Config.from_dict(out.to_dict())
    except ConfigError as exc:  # pragma: no cover - guarded by _candidate
        field, msg = next(iter(exc.errors.items()))
        raise PayloadError(field, f"the fitted box is invalid: {msg}") from None


def summary(cfg: Config) -> dict[str, object]:
    """Payload data for the previews."""
    c = clearance(cfg)
    return {
        "width": cfg.payload_width,
        "depth": cfg.payload_depth,
        "height": cfg.payload_height,
        "min_clearance": cfg.payload_clearance,
        "clearance": None if c is None else round(c, 4),
        "empty": is_empty(cfg),
        "fits": fits(cfg),
    }
