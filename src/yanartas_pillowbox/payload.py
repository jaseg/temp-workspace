"""Rectangular payload inscribed, centred, in the closed pillow box. Pure functions.

Payload axes: ``payload_width`` across the box (X), ``payload_depth`` along its length (Y),
``payload_height`` along its height (Z), in the 3D model frame of ``geometry.FoldedBox``.

Interior of the closed box (zero material thickness): the body is a cylinder whose
cross-section has height profile ``Zp(X)`` (front panel at ``+Zp``, back at ``-Zp``), and each
end wall is a flap reflected across its crease, standing at ``|Y| = edge/2 - Zp(X)``. So the
interior is ``{|Z| <= Zp(X), |Y| <= edge/2 - Zp(X)}`` and, since ``Zp`` is largest at the
centre, a centred payload fits iff

* ``payload_depth <= length`` (the midline length: the end walls are closest at X = 0), and
* ``Zp(payload_width / 2) >= payload_height / 2``.

``fit_box`` finds the box (width, length, height only) of smallest pattern bounding-box area
that holds the payload. The cross-section shape depends only on ``r = sagitta / W``; for a
given ``r`` the payload's top corner touches the profile at one arc position, which fixes the
panel width ``W``. That leaves a 1D search over ``r``.
"""

from __future__ import annotations

import math
from dataclasses import replace

from yanartas_pillowbox.config import SPECS_BY_NAME, Config, ConfigError
from yanartas_pillowbox.crosssection import MAX_SAGITTA_RATIO, CrossSection, width_ratio

ROUND = 0.01  # mm: results are rounded to this grid, always towards a fitting box


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


def fits(cfg: Config, tol: float = 1e-6) -> bool:
    if is_empty(cfg):
        return True
    if cfg.payload_depth > cfg.length + tol or cfg.payload_width >= cfg.width:
        return False
    return 2 * profile_height(cfg, cfg.payload_width / 2) >= cfg.payload_height - tol


def _floor(v: float) -> float:
    return math.floor(v / ROUND + 1e-9) * ROUND


def _ceil(v: float) -> float:
    return math.ceil(v / ROUND - 1e-9) * ROUND


def _r2(v: float) -> float:
    return round(v, 2)


# ------------------------------------------------------------------------- maximize
def maximize(cfg: Config, field: str) -> Config:
    """Largest value of one payload dimension that still fits the current box."""
    if field == "payload_depth":
        return replace(cfg, payload_depth=_r2(_floor(cfg.length)))
    sec = _section(cfg)
    if field == "payload_height":
        if cfg.payload_width >= cfg.width:
            raise PayloadError("payload_width", "the payload is as wide as the box")
        h = 2 * profile_height(cfg, cfg.payload_width / 2, sec)
        return replace(cfg, payload_height=_r2(_floor(h)))
    if field == "payload_width":
        if cfg.payload_height >= cfg.height:
            raise PayloadError("payload_height", "the payload is as high as the box")
        # Arc position where the profile reaches half the payload height.
        lo, hi = 0.0, sec.width / 2  # z(u) increases from 0 to the sagitta
        for _ in range(80):
            mid = (lo + hi) / 2
            if sec.z(mid) < cfg.payload_height / 2:
                lo = mid
            else:
                hi = mid
        w = 2 * -sec.x(hi)
        return replace(cfg, payload_width=_r2(_floor(w)))
    raise PayloadError(field, f"unknown payload field {field!r}")


# ------------------------------------------------------------------------- fit box
def pattern_area(cfg: Config) -> float:
    """Area of the flat pattern's bounding box: (2 W + glue tab) x (edge + both flaps)."""
    return (2 * cfg.panel_width + cfg.glue_tab_width) * pattern_height(cfg)


def pattern_height(cfg: Config) -> float:
    return cfg.edge_length + 2 * cfg.cut_sagitta


def _touch(r: float, aspect: float) -> tuple[float, float]:
    """For sagitta ratio ``r`` (unit panel width) the arc position where the payload's corner
    with width/height ratio ``aspect`` touches the profile: returns (|X|, Z) there."""
    sec = CrossSection(1.0, r)
    lo, hi = 1e-12, 0.5  # |X|/Z decreases from +inf (u = 0) to 0 (u = 1/2)
    for _ in range(100):
        mid = (lo + hi) / 2
        if -sec.x(mid) / max(sec.z(mid), 1e-300) > aspect:
            lo = mid
        else:
            hi = mid
    u = (lo + hi) / 2
    return -sec.x(u), sec.z(u)


def _candidate(base: Config, r: float) -> tuple[float, float, float] | None:
    """(pattern area, width, height) of the box with sagitta ratio r that the payload just
    touches, or None if that box violates a constraint on the untouched parameters."""
    pw, pd, ph = base.payload_width, base.payload_depth, base.payload_height
    _, zn = _touch(r, pw / ph)
    panel = (ph / 2) / zn
    sagitta = r * panel
    width = panel * width_ratio(r)
    length = max(pd, 10.0)
    if width < 10 or sagitta - base.thickness / 2 < 0.25 or base.glue_tab_width >= panel:
        return None
    if width > SPECS_BY_NAME["width"].maximum or 2 * sagitta > SPECS_BY_NAME["height"].maximum:
        return None
    if base.glue_tab_taper > (length + 2 * sagitta) / 2 - 1:
        return None
    area = (2 * panel + base.glue_tab_width) * (length + 4 * sagitta - base.thickness)
    return area, width, 2 * sagitta


def fit_box(cfg: Config) -> Config:
    """Box (width, length, height) holding the payload with the smallest pattern bounding box.
    Glue tab, thickness and colors are kept."""
    if is_empty(cfg):
        raise PayloadError("payload_width", "set all three payload dimensions first")
    length = _r2(_ceil(max(cfg.payload_depth, 10.0)))

    def area(r: float) -> float:
        c = _candidate(cfg, r)
        return math.inf if c is None else c[0]

    lo_r, hi_r = 1e-3, MAX_SAGITTA_RATIO
    n = 120
    grid = [lo_r * (hi_r / lo_r) ** (i / n) for i in range(n + 1)]
    values = [area(r) for r in grid]
    best = min(range(len(grid)), key=values.__getitem__)
    if math.isinf(values[best]):
        raise PayloadError(
            "payload_width",
            "no valid box holds this payload with the current glue tab and thickness",
        )
    # Golden-section refinement between the grid neighbours (area is unimodal there).
    a, b = grid[max(0, best - 1)], grid[min(n, best + 1)]
    g = (math.sqrt(5) - 1) / 2
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = area(c), area(d)
    for _ in range(60):
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
    # limits), then width up until the payload fits.
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
    return {
        "width": cfg.payload_width,
        "depth": cfg.payload_depth,
        "height": cfg.payload_height,
        "empty": is_empty(cfg),
        "fits": fits(cfg),
    }
