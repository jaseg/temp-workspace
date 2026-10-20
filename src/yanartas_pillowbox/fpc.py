"""The built-in FPC cable: a flat cable of the flex PCB that leaves the front panel's free edge.

The cable leaves the middle of the front panel's free straight edge (the glued edge, x = 0 in
the pattern), outward: the *junction*. In the pattern it runs straight out, away from the
edge, for the clearance, the inset and a thickness (the stub), turns 90 degrees up (towards
the top of the pattern, the box's front end) or down along the edge and meanders in rows
along it, stacked outward (an S), between the end sections beside the edge (the wings, the
lids' glue tabs, or the outer flaps' corners), as few as fit, its turns spread evenly so that
its tip ends at the side; the last ``plug_length`` of it is the plug that goes into a ZIF
connector. Every row makes the pattern wider.

Every turn is a 90 degree corner whose square (the cable's width on a side) is folded flat
along its diagonal from the outer to the inner corner, which lays the next run back along
the one before. Each U-turn between rows (two turns) so sends the next row on in the same
direction as the one before: folded, the cable is one straight strip (see ``unfold``),
``length`` long from the junction.

In the box (see ``docs/fpc-cable-folds.svg``), the front panel's free edge rests against the
inside of the back panel, by the glue fold (the glue tab lies on the outside): the cable
folds into the box at the junction, so the stub lies on the inside of the back panel; the
first corner folds it back towards the glued edge, leaving a triangle of two layers (half the
corner square) beside the stub; on the first row, a thickness short of the junction, the
*wall fold* straight across the cable folds it onto the inside of the front panel, along
which it runs on (round the straight fold onto the back panel, if it is that long).

The layout is made in a frame of its own (``meander``: the junction level, the stub going up,
the first turn to the right) and turned into the pattern's (mm, y down) by ``layout``.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from functools import lru_cache

from yanartas_pillowbox.config import Config

Point = tuple[float, float]


class CableError(ValueError):
    """The cable cannot be laid out. ``field`` names the culprit."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(message)


def plug_width(cfg: Config) -> float:
    """The plug's width: the contacts' span plus the edge margin on both sides."""
    return (cfg.fpc_pins - 1) * cfg.fpc_pitch + 2 * cfg.fpc_edge_margin


def cable_width(cfg: Config) -> float:
    """The cable's width away from the plug: the plug's less the inset on both sides."""
    return plug_width(cfg) - 2 * cfg.fpc_cable_inset


@dataclass(frozen=True)
class CableLayout:
    """The cable in pattern coordinates.

    ``junction`` is its seam with the front panel's free edge (x = 0), as wide as the cable,
    its ends in the order the outline (going up the free edge) meets them. ``path`` is the
    centreline, from the junction's middle through every corner's centre to the tip;
    ``outline`` the cut from the junction's first end round the tip back to its other end,
    ``plug_corners`` its corners at the plug (kept sharp); ``creases`` the corners' flat
    folds, one per inner path point, in order."""

    turn: str  # "up" | "down": the way its first corner turns it, along the edge
    width: float
    plug_width: float
    plug_length: float
    junction: tuple[Point, Point]
    path: tuple[Point, ...]
    outline: tuple[Point, ...]
    plug_corners: frozenset[Point]
    creases: tuple[tuple[Point, Point], ...]
    wall: tuple[Point, Point]  # the fold straight across the first row, onto the front panel


def _unit(a: Point, b: Point) -> Point:
    k = math.dist(a, b)
    return ((b[0] - a[0]) / k, (b[1] - a[1]) / k)


def _side(d: Point) -> Point:
    """The left-hand normal of a run going ``d`` (towards the junction's left end at the
    start, going up), in ``meander``'s frame."""
    return (d[1], -d[0])


def reflect(p: Point, crease: tuple[Point, Point]) -> Point:
    """p mirrored across the crease's line."""
    (ax, ay), (bx, by) = crease
    k = math.dist(*crease)
    ux, uy = (bx - ax) / k, (by - ay) / k
    qx, qy = p[0] - ax, p[1] - ay
    t = qx * ux + qy * uy
    return (ax + 2 * t * ux - qx, ay + 2 * t * uy - qy)


def unfold(p: Point, run: int, creases: tuple[tuple[Point, Point], ...]) -> Point:
    """Where flat point p of run ``run`` (between path points ``run`` and ``run + 1``) lies
    once every crease before it is folded flat: mirrored across the crease just before its
    run, then the one before that, and so on back to the first."""
    for crease in reversed(creases[:run]):
        p = reflect(p, crease)
    return p


def meander(
    junction: tuple[Point, Point],
    x_left: float,
    x_right: float,
    length: float,
    gap: float,
    inset: float,
    plug_length: float,
    stub: float,
    first_run: float = 0.0,
) -> tuple[Point, ...]:
    """Centreline of the cable leaving ``junction`` (level, left to right, y down):
    up the ``stub``, right along the first row, then rows stacked upward between ``x_left``
    and ``x_right``, until the folded cable reaches ``length`` past the junction. Rows are
    ``gap`` apart (the last one a further ``inset``, for the plug's ears); the plug always
    lies on the last row's straight part, past its corner.

    The cable takes as few rows as fit, and its turns are spread evenly: every turn moves in
    from its side by the same amount, so that the tip (which needs no room for a turn) ends
    at its side. The first row runs at least ``first_run`` from its corner to its turn.

    Folded, the first row runs back from the first corner's centre (the stub and half the
    cable's width above the junction); every U-turn takes the row pitch back again (its
    connector folds back over the row's end)."""
    (x0, y0), (x1, _) = junction
    w = x1 - x0
    h = w / 2
    xc = (x0 + x1) / 2
    first = h + plug_length  # shortest last row: past the corner square, then the plug
    ends = (x_left + h, x_right - h)  # the turns' centres at each side, farthest out
    full = ends[1] - ends[0]
    pitch = w + gap
    if full <= pitch + inset:
        raise CableError("fpc_cable_length", "no room for the cable's rows beside the edge")
    rem = length + stub + h  # still to go along the folded cable, from the first corner
    if rem < first:
        raise CableError(
            "fpc_cable_length", f"must be at least {_fmt(first - stub - h)} mm (the plug)"
        )
    y = y0 - stub - h
    pts: list[Point] = [(xc, y0), (xc, y)]
    head = ends[1] - xc  # the first row, to its turn
    if rem <= head + h:  # one row, no turn
        pts.append((xc + rem, y))
        return tuple(pts)
    min_head = max(w, first_run)  # the turn clear of the first corner (and the wall fold)
    if head < min_head:
        raise CableError(
            "fpc_cable_length", "no room beside the edge's middle for the cable's first turn"
        )
    # The fewest rows n whose folded reach, the tip at its side, holds the cable; then the
    # slack, spread over the 2 (n - 1) turns: each first row's turn, the two turns of every
    # middle row and the last row's turn are each that much farther in.
    reach = head + h - inset  # less a pitch and a full row per further row
    n = 1 + math.ceil((rem - reach) / (full - pitch))
    shift = (reach + (n - 1) * (full - pitch) - rem) / (2 * (n - 1))
    shift = min(shift, head - min_head, (full - w) / 2)  # every row still holds its turns
    right = True
    for row in range(n - 1):
        end = ends[1] - shift if right else ends[0] + shift
        pts.append((end, y))
        y -= pitch + (inset if row == n - 2 else 0.0)
        pts.append((end, y))
        right = not right
    # The last row: what is left of the folded cable, past the previous turns.
    xs = [p[0] for p in pts[1::2]]
    rem += (n - 1) * pitch + inset
    rem -= sum(abs(b - a) for a, b in itertools.pairwise(xs))
    if not first <= rem <= abs((x_right if right else x_left) - xs[-1]) + 1e-9:
        raise CableError("fpc_cable_length", "the cable's rows do not fit its length")
    pts.append((xs[-1] + rem if right else xs[-1] - rem, y))
    return tuple(pts)


def outline(
    path: tuple[Point, ...], width: float, plug: float, plug_length: float
) -> tuple[tuple[Point, ...], frozenset[Point]]:
    """The cable's cut, from the start's left side (the junction's left end, in ``meander``'s
    frame) round the tip to its right side: the centreline offset by half the width on both
    sides, square at every corner, widened to the plug's half width over the last
    ``plug_length``; and its corners at the plug (the tip's, and the steps to the ears)."""
    h, hp = width / 2, plug / 2
    dirs = [_unit(a, b) for a, b in itertools.pairwise(path)]

    def off(p: Point, n: Point, k: float) -> Point:
        return (p[0] + k * n[0], p[1] + k * n[1])

    left: list[Point] = [off(path[0], _side(dirs[0]), h)]
    for p, d0, d1 in zip(path[1:-1], dirs, dirs[1:], strict=False):
        n0, n1 = _side(d0), _side(d1)
        left.append((p[0] + h * (n0[0] + n1[0]), p[1] + h * (n0[1] + n1[1])))
    tip, d = path[-1], dirs[-1]
    q = (tip[0] - plug_length * d[0], tip[1] - plug_length * d[1])
    n = _side(d)
    plug_left = [off(q, n, h), off(q, n, hp), off(tip, n, hp)] if hp > h else [off(tip, n, h)]
    centres = [*path[:-1], *((q, q, tip) if hp > h else (tip,))]
    left += plug_left
    right = [(2 * c[0] - p[0], 2 * c[1] - p[1]) for p, c in zip(left, centres, strict=True)]
    k = len(plug_left)
    return (*left, *reversed(right)), frozenset([*left[-k:], *right[-k:]])


def creases(path: tuple[Point, ...], width: float) -> tuple[tuple[Point, Point], ...]:
    """Each corner's flat fold: the diagonal of its square from the outer to the inner
    corner, along the difference of the incoming and outgoing directions (mirroring across
    it lays the outgoing run back along the incoming one)."""
    h = width / 2
    out = []
    for a, p, b in zip(path, path[1:], path[2:], strict=False):
        d0, d1 = _unit(a, p), _unit(p, b)
        s = (d0[0] - d1[0], d0[1] - d1[1])
        out.append(((p[0] - h * s[0], p[1] - h * s[1]), (p[0] + h * s[0], p[1] + h * s[1])))
    return tuple(out)


@lru_cache(maxsize=64)
def layout(cfg: Config) -> CableLayout | None:
    """The cable, or None without one. Raises ``CableError``."""
    if cfg.fpc_cable == "none":
        return None
    e, lf, t = cfg.end_wall_gap, cfg.front_length, cfg.thickness
    w, wp, gap = cable_width(cfg), plug_width(cfg), cfg.fpc_cable_gap
    # Laid out in ``meander``'s frame: the junction level at y = 0, centred on x = 0, the stub
    # going up (out of the edge), the first turn to the right (along the edge, up or down).
    junction = ((-w / 2, 0.0), (w / 2, 0.0))
    # The rows clear the end sections beside the edge (beyond the back panel's ends: the
    # wings, the lids' glue tabs, the outer flaps' corners) by the clearance.
    reach = lf / 2 - e - gap
    # The stub clears the edge by the clearance (and the plug's ears), and is a thickness
    # longer: the first row, folded back over it, folds onto the front panel a thickness
    # short of the junction (on the panel's inner surface), clear of the corner square.
    stub = gap + cfg.fpc_cable_inset + t
    path = meander(
        junction,
        -reach,
        reach,
        cfg.fpc_cable_length,
        gap,
        cfg.fpc_cable_inset,
        cfg.fpc_plug_length,
        stub,
        stub + w - t,  # the first row reaches past the wall fold
    )
    pts, plug = outline(path, w, wp, cfg.fpc_plug_length)
    # The wall fold: on the first row, where (folded back) it gets to a thickness short of
    # the junction again: the stub and half the width, less a thickness, past its corner.
    (cx, cy), (ex, _) = path[1], path[2]
    along = stub + w / 2 - t
    room = abs(ex - cx) - (w / 2 if len(path) > 3 else cfg.fpc_plug_length)
    if along > room:
        raise CableError(
            "fpc_cable_length",
            "too short to fold onto the front panel: the first row must reach past the wall fold",
        )
    x = cx + along
    wall = ((x, cy + w / 2), (x, cy - w / 2))

    # Into the pattern: out of the edge (up in the frame) is -x, the first turn (right) up
    # (-y) or down (+y) along it, from the edge's middle. Turning down mirrors the frame, so
    # the outline then runs the other way round.
    k = -1.0 if cfg.fpc_cable == "up" else 1.0

    def at(q: Point) -> Point:
        return (q[1], lf / 2 + k * q[0])

    def line(pair: tuple[Point, Point]) -> tuple[Point, Point]:
        return (at(pair[0]), at(pair[1]))

    pts = tuple(at(q) for q in pts)
    pts = pts if k < 0 else tuple(reversed(pts))
    ends = line(junction)
    ends = ends if k < 0 else (ends[1], ends[0])
    return CableLayout(
        cfg.fpc_cable,
        w,
        wp,
        cfg.fpc_plug_length,
        ends,
        tuple(at(q) for q in path),
        (ends[0], *pts[1:-1], ends[1]),  # bit-identical with the junction
        frozenset(at(q) for q in plug),
        tuple(line(c) for c in creases(path, w)),
        line(wall),
    )


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")
