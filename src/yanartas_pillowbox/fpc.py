"""The built-in FPC cable: a flat cable of the flex PCB that leaves one inner flap.

The cable leaves the top of the inner (back panel's) flap's cut edge, cut off level over
exactly the cable's width (like the FPC cutout): the *junction*; the flap keeps its height.
In the pattern it runs straight up, away from the flap, for the clearance, the inset and a
thickness (the stub), turns 90 degrees towards the glue tab and meanders in horizontal rows
stacked upward (an S), from the wing to the glue tab's free edge; the last ``plug_length``
of it is the plug that goes into a ZIF connector. Rows past the top of the rest of the
pattern grow its bounding box.

Every turn is a 90 degree corner whose square (the cable's width on a side) is folded flat
along its diagonal from the outer to the inner corner, which lays the next run back along
the one before. Each U-turn between rows (two turns) so sends the next row on in the same
direction as the one before: folded, the cable is one straight strip (see ``unfold``),
``length`` long from the junction.

In the box (see ``docs/fpc-cable-folds.svg``), the cable folds 90 degrees into the box at
the junction, so the stub lies on the inside of the front panel; the first corner folds it
back towards the inner wall, leaving a triangle of two layers (half the corner square)
beside the stub; on the first row, a thickness short of the junction, the *wall fold*
straight across the cable folds it 90 degrees up the inside of the inner wall; it bends
round towards the back panel (with a radius of half the box's height) and runs on along the
inside of the back panel.

Pattern coordinates as in ``geometry`` (y down); the layout is made at the top end and
mirrored to the bottom end like the rest of the pattern.
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
    """The cable at the top end, in pattern coordinates.

    ``level`` is the inner flap's level cut, (u from, u to, offset) in the flap's cut
    samples (as ``geometry.level_cut``), exactly as wide as the cable: the ``junction``.
    ``path`` is the centreline, from the junction's middle through every corner's centre to
    the tip; ``outline`` the cut from the junction's left end round the tip back to its right
    end, ``plug_corners`` its corners at the plug (kept sharp); ``creases`` the corners'
    flat folds, one per inner path point, in order."""

    width: float
    plug_width: float
    plug_length: float
    level: tuple[float, float, float]
    junction: tuple[Point, Point]  # left to right
    path: tuple[Point, ...]
    outline: tuple[Point, ...]
    plug_corners: frozenset[Point]
    creases: tuple[tuple[Point, Point], ...]
    wall: tuple[Point, Point]  # the fold straight across the first row, up the inner wall


def _unit(a: Point, b: Point) -> Point:
    k = math.dist(a, b)
    return ((b[0] - a[0]) / k, (b[1] - a[1]) / k)


def _side(d: Point) -> Point:
    """The left-hand normal of a run going ``d`` (towards the junction's left end at the
    start, going up), in the top end's coordinates."""
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
) -> tuple[Point, ...]:
    """Centreline of the cable leaving ``junction`` (level, left to right, at the top end):
    up the ``stub``, right along the first row to ``x_right``, then rows between ``x_left`` and
    ``x_right`` stacked upward, until the folded cable reaches ``length`` past the junction.
    Rows are ``gap`` apart (the last one a further ``inset``, for the plug's ears); the plug
    always lies on the last row's straight part, past its corner.

    Folded, the first row runs back from the first corner's centre (the stub and half the
    cable's width above the junction); every U-turn takes the row pitch back again (its
    connector folds back over the row's end)."""
    (x0, y0), (x1, _) = junction
    w = x1 - x0
    h = w / 2
    xc = (x0 + x1) / 2
    first = h + plug_length  # shortest last row: past the corner square, then the plug
    ends = (x_left + h, x_right - h)  # the turns' centres at each side
    full = ends[1] - ends[0]
    if full <= w + gap + inset:
        raise CableError("fpc_cable_length", "no room for the cable's rows beside the flap")
    pts: list[Point] = [(xc, y0), (xc, y0 - stub - h)]
    rem = length + stub + h  # still to go along the folded cable, from the first corner
    if rem < first:
        raise CableError(
            "fpc_cable_length", f"must be at least {_fmt(first - stub - h)} mm (the plug)"
        )
    x, y, right = xc, y0 - stub - h, True
    while True:
        end = ends[1] if right else ends[0]
        run = abs(end - x)
        if rem <= run:  # the tip lies on this row
            pts.append((x + rem if right else x - rem, y))
            return tuple(pts)
        if run < w:  # the turn would overlap the corner before it
            raise CableError(
                "fpc_cable_length", "no room beside the flap's middle for the cable's first turn"
            )
        pitch = w + gap
        if rem - run + pitch <= full:  # the next row is the last: room for the plug's ears
            pitch += inset
            last = rem - run + pitch
            if last < first:
                # Turn earlier, so that the last row holds the corner and the plug.
                back = first - last
                if run - back < w:
                    raise CableError(
                        "fpc_cable_length",
                        f"the cable would end in a turn: make it {_fmt(back)} mm longer or "
                        f"{_fmt(rem - run + pitch)} mm shorter",
                    )
                end += -back if right else back
                run -= back
        pts.append((end, y))
        rem -= run - pitch
        x, y, right = end, y - pitch, not right
        pts.append((x, y))


def outline(
    path: tuple[Point, ...], width: float, plug: float, plug_length: float
) -> tuple[tuple[Point, ...], frozenset[Point]]:
    """The cable's cut, from the start's left side (the junction's left end at the top end)
    round the tip to its right side: the centreline offset by half the width on both sides,
    square at every corner, widened to the plug's half width over the last ``plug_length``;
    and its corners at the plug (the tip's, and the steps to the ears)."""
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
    """The cable at the top end (also for a cable at the bottom end, which the pattern
    mirrors), or None without one. Raises ``CableError``."""
    if cfg.fpc_cable == "none":
        return None
    from yanartas_pillowbox.geometry import level_cut, lid_layout  # (geometry imports this)

    body = cfg.body
    wf, wb, e = body.front.width, body.back.width, cfg.end_wall_gap
    w, wp, gap = cable_width(cfg), plug_width(cfg), cfg.fpc_cable_gap
    # The cable leaves the top of the flap's edge, cut off level over exactly its width
    # (like the FPC cutout): just enough to fold it flat there; the flap keeps its height.
    a, b, cap = level_cut(body.back_cuts, w)
    junction = ((wf + a, e - cap), (wf + b, e - cap))
    lid = lid_layout(cfg)
    spread = 0.0 if lid is None else lid.spread
    # The stub clears the flap's edge by the clearance (and the plug's ears), and is a
    # thickness longer: the first row, folded back over it, folds up the wall a thickness
    # short of the junction (on the wall's inner surface), clear of the corner square.
    stub = gap + cfg.fpc_cable_inset + cfg.thickness
    path = meander(
        junction,
        wf + spread + gap,  # clear of the wing (or the outer flap)
        wf + wb + cfg.glue_tab_width,  # the glue tab's free edge
        cfg.fpc_cable_length,
        gap,
        cfg.fpc_cable_inset,
        cfg.fpc_plug_length,
        stub,
    )
    pts, plug = outline(path, w, wp, cfg.fpc_plug_length)
    pts = (junction[0], *pts[1:-1], junction[1])  # bit-identical with the flap's edge
    # The wall fold: on the first row, where (folded back) it gets to a thickness short of
    # the junction again: the stub and half the width, less a thickness, past its corner.
    (cx, cy), (ex, _) = path[1], path[2]
    along = stub + w / 2 - cfg.thickness
    room = abs(ex - cx) - (w / 2 if len(path) > 3 else cfg.fpc_plug_length)
    if along > room:
        raise CableError(
            "fpc_cable_length",
            "too short to fold up the inner wall: the first row must reach past the wall fold",
        )
    x = cx + along
    wall = ((x, cy + w / 2), (x, cy - w / 2))
    return CableLayout(
        w, wp, cfg.fpc_plug_length, (a, b, cap), junction, path, pts, plug, creases(path, w), wall
    )


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")
