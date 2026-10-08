"""Rectangular payload inscribed, centred, in the closed pillow box. Pure functions.

Payload axes: ``payload_width`` across the box (X), ``payload_depth`` along its length (Y),
``payload_height`` along its height (Z), in the 3D model frame of ``geometry.FoldedBox``.

Interior of the closed box (zero material thickness): the body is a cylinder whose
cross-section has height profile ``Zp(X)`` (front panel at ``+Zp``, back at ``-Zp``), and each
end wall is a flap reflected across its crease, standing at ``|Y| = edge/2 - Zp(X)``. So the
interior is ``{|Z| <= Zp(X), |Y| <= edge/2 - Zp(X)}``.

**Clearance** is the true 3D distance from the payload to the nearest point of the box
surface. The surface consists of the panels (cylinders with rulings along Y) and the end walls
(cylinders with rulings along Z). For a payload inside the box, the distance to the surface
equals the smaller of the distances to the two *unbounded* cylinders: a nearest point on an
unbounded cylinder that is not on the real surface lies outside the interior, and the
segment to it crosses the real surface earlier. The nearest point on a cylinder shares the
ruling coordinate, so each distance is a 2D one:

* panels: distance, in the cross-section (X, Z), from the payload rectangle to the profile;
* end walls: in plan (X, Y) every wall point has ``|Y| >= length / 2`` (the midline length),
  with equality at X = 0, so the distance is exactly ``(length - payload_depth) / 2``.

The payload fits when ``clearance >= payload_margin``.

``fit_box`` finds the box (width, length, height only) with the smallest pattern bounding box
that keeps the margin: ``length = payload_depth + 2 margin`` and, since the cross-section
shape depends only on ``r = sagitta / W``, a 1D search over ``r`` in which each ``r`` gives the
smallest panel width ``W`` whose profile clears the payload rectangle by the margin.
"""

from __future__ import annotations

import math
from dataclasses import replace

from yanartas_pillowbox.config import SPECS_BY_NAME, Config, ConfigError
from yanartas_pillowbox.crosssection import MAX_SAGITTA_RATIO, CrossSection, width_ratio

ROUND = 0.01  # mm: results are rounded to this grid, always towards a fitting box
SAMPLES = 1000  # profile samples (per quarter) for clearance computations
FIT_SAMPLES = 600


class PayloadError(ValueError):
    """The requested payload operation is impossible. ``field`` names the culprit."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(message)


def is_empty(cfg: Config) -> bool:
    return min(cfg.payload_width, cfg.payload_depth, cfg.payload_height) <= 0


def _section(cfg: Config) -> CrossSection:
    return CrossSection(cfg.panel_width, cfg.fold_sagitta)


def _u_at_x(sec: CrossSection, x: float) -> float:
    """Arc position u in [0, W/2] whose cross-section point is at |X| = x (x <= half width)."""
    lo, hi = 0.0, sec.width / 2  # |X(u)| decreases from closed_width/2 to 0
    for _ in range(80):
        mid = (lo + hi) / 2
        if -sec.x(mid) > x:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def profile_height(cfg: Config, x: float, sec: CrossSection | None = None) -> float:
    """Half-height ``Zp`` of the box interior at distance ``x`` from the centre."""
    sec = sec or _section(cfg)
    if x >= sec.closed_width / 2:
        return 0.0
    return sec.z(_u_at_x(sec, max(0.0, x)))


# ------------------------------------------------------------------------- clearance
def _point_rect(qx: float, qz: float, a: float, b: float) -> float:
    """Signed distance from (qx, qz) (first quadrant) to the rectangle |x| <= a, |z| <= b:
    positive outside, negative (depth) inside."""
    dx, dz = qx - a, qz - b
    if dx <= 0 and dz <= 0:
        return max(dx, dz)
    return math.hypot(max(dx, 0.0), max(dz, 0.0))


def section_clearance(sec: CrossSection, width: float, height: float) -> float:
    """Distance in the cross-section from the payload rectangle (width x height, centred) to
    the profile; negative if the rectangle pokes through it. By symmetry one quarter of the
    profile suffices: u in [0, W/2] runs from the side fold (|X| max, Z = 0) to the apex."""
    a, b = width / 2, height / 2
    half = sec.width / 2

    def f(u: float) -> float:
        return _point_rect(-sec.x(u), sec.z(u), a, b)

    us = [half * i / SAMPLES for i in range(SAMPLES + 1)]
    vals = [f(u) for u in us]
    k = min(range(len(us)), key=vals.__getitem__)
    # Golden-section refinement between the neighbouring samples.
    lo, hi = us[max(0, k - 1)], us[min(SAMPLES, k + 1)]
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
    return min(vals[k], fc, fd)


def clearance(cfg: Config, sec: CrossSection | None = None) -> float | None:
    """True distance from the payload to the box surface (negative: it does not fit;
    None: no payload)."""
    if is_empty(cfg):
        return None
    sec = sec or _section(cfg)
    walls = (cfg.length - cfg.payload_depth) / 2
    return min(section_clearance(sec, cfg.payload_width, cfg.payload_height), walls)


def fits(cfg: Config, tol: float = 1e-6) -> bool:
    c = clearance(cfg)
    return c is None or c >= cfg.payload_margin - tol


def _floor(v: float) -> float:
    return math.floor(v / ROUND + 1e-9) * ROUND


def _ceil(v: float) -> float:
    return math.ceil(v / ROUND - 1e-9) * ROUND


def _r2(v: float) -> float:
    return round(v, 2)


# ------------------------------------------------------------------------- maximize
def maximize(cfg: Config, field: str) -> Config:
    """Largest value of one payload dimension that keeps the margin in the current box."""
    m = cfg.payload_margin
    sec = _section(cfg)
    if field == "payload_depth":
        if section_clearance(sec, cfg.payload_width, cfg.payload_height) < m:
            raise PayloadError(
                "payload_width", "the payload's width and height already break the margin"
            )
        depth = _floor(cfg.length - 2 * m)
        if depth <= 0:
            raise PayloadError("payload_margin", "the margin leaves no room along the length")
        return replace(cfg, payload_depth=_r2(depth))
    if field not in ("payload_width", "payload_height"):
        raise PayloadError(field, f"unknown payload field {field!r}")

    other = "payload_height" if field == "payload_width" else "payload_width"
    limit = cfg.width if field == "payload_width" else cfg.height

    def ok(v: float) -> bool:
        w, h = (v, cfg.payload_height) if field == "payload_width" else (cfg.payload_width, v)
        return section_clearance(sec, w, h) >= m

    if not ok(0.0):
        axis = other.removeprefix("payload_")
        raise PayloadError(other, f"the payload {axis} leaves no room for the margin")
    lo, hi = 0.0, limit  # ok(lo), not ok(hi)
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return replace(cfg, **{field: _r2(_floor(lo))})


# ------------------------------------------------------------------------- fit box
def pattern_area(cfg: Config) -> float:
    """Area of the flat pattern's bounding box: (2 W + glue tab) x (edge + both flaps)."""
    return (2 * cfg.panel_width + cfg.glue_tab_width) * pattern_height(cfg)


def pattern_height(cfg: Config) -> float:
    return cfg.edge_length + 2 * cfg.cut_sagitta


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
    """(pattern area, width, height) of the smallest box with sagitta ratio r that keeps the
    margin, or None if that box violates a constraint on the untouched parameters."""
    a, b, m = base.payload_width / 2, base.payload_height / 2, base.payload_margin
    sec = CrossSection(1.0, r)
    panel = max(
        _scale_needed(-sec.x(u), sec.z(u), a, b, m)
        for u in (0.5 * i / FIT_SAMPLES for i in range(FIT_SAMPLES + 1))
    )
    sagitta = r * panel
    width = panel * width_ratio(r)
    length = max(base.payload_depth + 2 * m, 10.0)
    if width < 10 or sagitta - base.thickness / 2 < 0.25 or base.glue_tab_width >= panel:
        return None
    if width > SPECS_BY_NAME["width"].maximum or 2 * sagitta > SPECS_BY_NAME["height"].maximum:
        return None
    if base.glue_tab_taper > (length + 2 * sagitta) / 2 - 1:
        return None
    area = (2 * panel + base.glue_tab_width) * (length + 4 * sagitta - base.thickness)
    return area, width, 2 * sagitta


def fit_box(cfg: Config) -> Config:
    """Box (width, length, height) holding the payload with its margin, with the smallest
    pattern bounding box. Glue tab, thickness and colors are kept."""
    if is_empty(cfg):
        raise PayloadError("payload_width", "set all three payload dimensions first")
    length = _r2(_ceil(max(cfg.payload_depth + 2 * cfg.payload_margin, 10.0)))

    def area(r: float) -> float:
        c = _candidate(cfg, r)
        return math.inf if c is None else c[0]

    lo_r, hi_r = 1e-3, MAX_SAGITTA_RATIO
    n = 80
    grid = [lo_r * (hi_r / lo_r) ** (i / n) for i in range(n + 1)]
    values = [area(r) for r in grid]
    best = min(range(len(grid)), key=values.__getitem__)
    if math.isinf(values[best]):
        raise PayloadError(
            "payload_width",
            "no valid box holds this payload with the current margin, glue tab and thickness",
        )
    # Golden-section refinement between the grid neighbours (area is unimodal there).
    a, b = grid[max(0, best - 1)], grid[min(n, best + 1)]
    g = (math.sqrt(5) - 1) / 2
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = area(c), area(d)
    for _ in range(40):
        if fc <= fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = area(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = area(d)
    r = min((grid[best], c, d), key=area)
    cand = _candidate(cfg, r)
    assert cand is not None
    _, width, height = cand

    # Round to the grid towards a box that still fits: height down (keeps the arc within
    # limits), then width up until the margin holds.
    out = replace(cfg, length=length, height=_r2(_floor(height)), width=_r2(_ceil(width)))
    for _ in range(1000):
        if fits(out):
            break
        out = replace(out, width=_r2(out.width + ROUND))
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
        "margin": cfg.payload_margin,
        "clearance": None if c is None else round(c, 4),
        "empty": is_empty(cfg),
        "fits": fits(cfg),
    }
