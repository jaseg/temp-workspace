"""Wire geometry: catenary sag between two poles, projected the way Factorio draws it.

Factorio's camera looks straight down with height drawn as an upward screen offset:
a point at ground position ``g`` and height ``z`` is drawn at ``g + (0, -z)``.  A
wire therefore hangs in a vertical plane above the straight ground line between the
two poles.  We model it as a real catenary through both attachment points with a
fixed amount of slack (its length is ``chord * (1 + slack)``), which is how power lines
are strung in practice: the sag grows with the span, so long big-pole spans droop
much more than short small-pole hops.

The shadow of the wire is the same curve cast onto the ground along the sun
direction, which Factorio encodes in each pole's ``shadow`` connection points.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

Vec = tuple[float, float]

DEFAULT_SLACK = 0.015


def catenary_constant(span: float, rise: float, length: float) -> float:
    """Solve for the catenary parameter ``a`` (same units as ``span``).

    A catenary ``z(s) = a*cosh((s - s0)/a) + c`` through two points ``span`` apart
    horizontally and ``rise`` apart vertically has arc length ``length`` iff
    ``sqrt(length^2 - rise^2) = 2 a sinh(span / (2a))``.
    """
    if span <= 0:
        raise ValueError("span must be positive")
    target = math.sqrt(max(length * length - rise * rise, 0.0))
    if target <= span * (1 + 1e-12):
        return math.inf  # taut: a straight line

    # f(a) = 2a sinh(span/2a) is decreasing in a, from inf (a -> 0) to span (a -> inf).
    # Solve in u = span / (2a): sinh(u)/u = target/span.
    ratio = target / span
    lo, hi = 1e-9, 1.0
    while math.sinh(hi) / hi < ratio:
        hi *= 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if math.sinh(mid) / mid < ratio:
            lo = mid
        else:
            hi = mid
    u = 0.5 * (lo + hi)
    return span / (2.0 * u)


def sag_profile(span: float, h1: float, h2: float, slack: float = DEFAULT_SLACK, samples: int = 24) -> list[float]:
    """How far below the straight chord the wire hangs at ``samples`` evenly spaced
    points along the span (first and last are 0).

    ``h1`` and ``h2`` are the attachment heights; ``slack`` is the extra wire length as
    a fraction of the chord length.
    """
    if samples < 2:
        raise ValueError("need at least two samples")
    if span <= 0:
        return [0.0] * samples
    rise = h2 - h1
    chord = math.hypot(span, rise)
    a = catenary_constant(span, rise, chord * (1.0 + slack))
    if math.isinf(a):
        return [0.0] * samples

    # Position of the lowest point (vertex) s0 so the curve passes through both ends:
    # a*(cosh((span - s0)/a) - cosh(-s0/a)) = rise
    #   => sinh((span/2 - s0)/a) = rise / (2a sinh(span/(2a)))
    m = math.asinh(rise / (2.0 * a * math.sinh(span / (2.0 * a))))
    s0 = span / 2.0 - a * m
    c = h1 - a * math.cosh(-s0 / a)

    out = []
    for i in range(samples):
        t = i / (samples - 1)
        s = t * span
        z = a * math.cosh((s - s0) / a) + c
        chord_z = h1 + t * rise
        out.append(max(chord_z - z, 0.0))
    out[0] = out[-1] = 0.0
    return out


def wire_polyline(
    ground1: Vec,
    attach1: Vec,
    ground2: Vec,
    attach2: Vec,
    slack: float = DEFAULT_SLACK,
    samples: int = 24,
) -> list[Vec]:
    """Screen-space points of a wire between two poles.

    ``ground*`` are the pole positions; ``attach*`` are the wire attachment offsets
    relative to them (``connection_points[].wire.copper``; negative y is height).
    All values share one unit (tiles or millimetres - the result is in the same unit).
    """
    a = (ground1[0] + attach1[0], ground1[1] + attach1[1])
    b = (ground2[0] + attach2[0], ground2[1] + attach2[1])
    span = math.dist(ground1, ground2)
    sag = sag_profile(span, -attach1[1], -attach2[1], slack, samples)
    pts = []
    for i, d in enumerate(sag):
        t = i / (samples - 1)
        pts.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]) + d))
    return pts


def shadow_polyline(
    ground1: Vec,
    attach1: Vec,
    shadow1: Vec,
    ground2: Vec,
    attach2: Vec,
    shadow2: Vec,
    slack: float = DEFAULT_SLACK,
    samples: int = 24,
) -> list[Vec]:
    """Ground-space points of the wire's shadow.

    A point at height ``h`` casts its shadow ``h * v`` away from its ground position,
    where ``v`` is the per-unit-height shadow vector.  Factorio gives us the shadow of
    the attachment point (``shadow*``, relative to the pole), so ``v = shadow / h``.
    Where the wire sags by ``d`` its shadow moves back towards the ground line by
    ``d * v``.
    """
    h1, h2 = -attach1[1], -attach2[1]
    v1 = (shadow1[0] / h1, shadow1[1] / h1) if h1 > 0 else (0.0, 0.0)
    v2 = (shadow2[0] / h2, shadow2[1] / h2) if h2 > 0 else (0.0, 0.0)
    s1 = (ground1[0] + shadow1[0], ground1[1] + shadow1[1])
    s2 = (ground2[0] + shadow2[0], ground2[1] + shadow2[1])
    span = math.dist(ground1, ground2)
    sag = sag_profile(span, h1, h2, slack, samples)
    pts = []
    for i, d in enumerate(sag):
        t = i / (samples - 1)
        vx = v1[0] + t * (v2[0] - v1[0])
        vy = v1[1] + t * (v2[1] - v1[1])
        pts.append((s1[0] + t * (s2[0] - s1[0]) - d * vx, s1[1] + t * (s2[1] - s1[1]) - d * vy))
    return pts


Matrix = tuple[tuple[float, float], tuple[float, float]]
IDENTITY: Matrix = ((1.0, 0.0), (0.0, 1.0))


def shadow_matrix(copper: Vec, shadow_copper: Vec, angle_deg: float | None) -> Matrix:
    """Linear map that re-casts the game's shadows in another sun direction.

    A point at ground offset ``g`` and height ``z`` casts its shadow at ``g + z*v``, and
    the game's shadows all fall nearly horizontally to the right.  Writing shadow offsets
    in the basis (``v``, ground y) and swapping ``v`` for a vector of the same length at
    ``angle_deg`` (screen angle, clockwise from +x since y points down; 45 = down-right)
    moves every shadow, sprite or wire, as if the sun had moved, with the pole's foot
    staying where it is.  ``None`` keeps the game's direction.
    """
    if angle_deg is None:
        return IDENTITY
    h = -copper[1]
    if h <= 0:
        return IDENTITY
    vx, vy = shadow_copper[0] / h, shadow_copper[1] / h
    if abs(vx) < 1e-9:
        return IDENTITY
    length = math.hypot(vx, vy)
    a = math.radians(angle_deg)
    wx, wy = length * math.cos(a), length * math.sin(a)
    # M = [w e_y] @ inv([v e_y]),  inv([[vx, 0], [vy, 1]]) = [[1/vx, 0], [-vy/vx, 1]]
    return ((wx / vx, 0.0), (wy / vx - vy / vx, 1.0))


def apply(m: Matrix, p: Vec) -> Vec:
    return (m[0][0] * p[0] + m[0][1] * p[1], m[1][0] * p[0] + m[1][1] * p[1])


def samples_for_span(span_tiles: float) -> int:
    """Enough polyline points for the curve to look smooth at any zoom we care about."""
    return max(8, min(64, math.ceil(span_tiles * 2) + 1))


def orientation_frame(ground: Vec, neighbours: Sequence[Vec], frames: int = 4) -> int:
    """Pick the direction frame for a pole from the directions of its wires.

    Electric pole sprites come in 4 orientations, 45 degrees apart; the cross-arm is
    perpendicular to the wires.  Frame 0 suits wires running north-south, 1 for
    NE-SW, 2 for east-west and 3 for NW-SE.  Wire directions are axial (a wire
    going east is the same as one going west), so we average them as doubled angles.
    """
    sx = sy = 0.0
    for n in neighbours:
        dx, dy = n[0] - ground[0], n[1] - ground[1]
        if dx == 0 and dy == 0:
            continue
        theta = math.atan2(dy, dx)
        sx += math.cos(2 * theta)
        sy += math.sin(2 * theta)
    if abs(sx) < 1e-9 and abs(sy) < 1e-9:
        return 0
    theta = math.atan2(sy, sx) / 2.0  # mean axis, screen angle (y down)
    step = math.pi / frames
    return round(((theta - math.pi / 2) % math.pi) / step) % frames
