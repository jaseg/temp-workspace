"""Security mesh: a port of KiMesh's generator (https://git.yasec.de/jaseg/kimesh).

The area to cover (the *mask*) is divided into square cells, ``2 n`` trace pitches wide for
``n`` traces. A randomized depth-first walk from the *exit cell* (the one beside the mesh's
entry) visits every cell it can reach; the walk's tree decides how each cell's traces run:
every cell gets one of the tiles below by the sides on which it connects to its neighbours in
the tree (U: one, I and L: two, T: three, X: four). Trace ``i`` and its mirror ``2 n - 1 - i``
(counted across a cell's side) form one net, so each net is one loop through every cell that
starts and ends at the exit cell's open side.

Unit-cell coordinates: x right, y down (as the pattern); side bits 0b0001 +x, 0b0010 +y,
0b0100 -x, 0b1000 -y.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import shapely

Point = tuple[float, float]

RIGHT, DOWN, LEFT, UP = 0b0001, 0b0010, 0b0100, 0b1000
_STEP = {RIGHT: (1, 0), DOWN: (0, 1), LEFT: (-1, 0), UP: (0, -1)}
_OPPOSITE = {RIGHT: LEFT, DOWN: UP, LEFT: RIGHT, UP: DOWN}


class MeshError(ValueError):
    """The mesh cannot be laid out (e.g. no room for its exit cell)."""


# ----------------------------------------------------------------------------- tiles
def _tile_u(n: int, cd: float) -> Iterator[tuple[list[Point], int]]:
    """Open at the top (-y): every net turns back."""
    pitch = 1 / (2 * n)
    cd *= pitch
    for i in range(n):
        sp = (i + 0.5) * pitch
        yield (
            [
                (sp, 0),
                (sp, 1 - sp - cd),
                (sp + cd, 1 - sp),
                (1 - sp - cd, 1 - sp),
                (1 - sp, 1 - sp - cd),
                (1 - sp, 0),
            ],
            i,
        )


def _tile_i(n: int, cd: float) -> Iterator[tuple[list[Point], int]]:
    """Open at the top and the bottom: straight through."""
    for i in range(n):
        yield [((i + 0.5) / (2 * n), 0), ((i + 0.5) / (2 * n), 1)], i
        yield [((2 * n - 1 - i + 0.5) / (2 * n), 0), ((2 * n - 1 - i + 0.5) / (2 * n), 1)], i


def _tile_l(n: int, cd: float) -> Iterator[tuple[list[Point], int]]:
    """Open at the top and the right."""
    pitch = 1 / (2 * n)
    cd *= pitch
    for i in range(n):
        for sp in ((i + 0.5) * pitch, (2 * n - 1 - i + 0.5) * pitch):
            yield [(sp, 0), (sp, 1 - sp - cd), (sp + cd, 1 - sp), (1, 1 - sp)], i


def _tile_t(n: int, cd: float) -> Iterator[tuple[list[Point], int]]:
    """Open at the left, the right and the bottom."""
    pitch = 1 / (2 * n)
    cd *= pitch
    for i in range(n):
        sp = (i + 0.5) * pitch
        yield [(0, sp), (1, sp)], i
        yield [(0, 1 - sp), (sp - cd, 1 - sp), (sp, 1 - sp + cd), (sp, 1)], i
        yield [(1 - sp, 1), (1 - sp, 1 - sp + cd), (1 - sp + cd, 1 - sp), (1, 1 - sp)], i


def _tile_x(n: int, cd: float) -> Iterator[tuple[list[Point], int]]:
    """Open on all four sides: four corners."""
    pitch = 1 / (2 * n)
    cd *= pitch
    for i in range(n):
        sp = (i + 0.5) * pitch
        yield [(0, sp), (sp - cd, sp), (sp, sp - cd), (sp, 0)], i
        yield [(1 - sp, 0), (1 - sp, sp - cd), (1 - sp + cd, sp), (1, sp)], i
        yield [(0, 1 - sp), (sp - cd, 1 - sp), (sp, 1 - sp + cd), (sp, 1)], i
        yield [(1 - sp, 1), (1 - sp, 1 - sp + cd), (1 - sp + cd, 1 - sp), (1, 1 - sp)], i


Tile = Callable[[int, float], Iterator[tuple[list[Point], int]]]


def _rotated(tile: Tile, quarter_turns: int) -> Tile:
    """The tile turned by quarter turns about the cell's centre, as KiMesh's ``rotate``
    (positive: counter-clockwise in a y-up frame, i.e. clockwise on the y-down page)."""

    def turn(p: Point) -> Point:
        x, y = p
        for _ in range(quarter_turns % 4):  # (x, y) -> (1 - y, x): +90 degrees, y down
            x, y = 1 - y, x
        return (x, y)

    def wrapper(n: int, cd: float) -> Iterator[tuple[list[Point], int]]:
        for pts, net in tile(n, cd):
            yield [turn(p) for p in pts], net

    return wrapper


# KiMesh's look-up table, keyed by the sides a cell connects on. Its rotations are shapely's
# (counter-clockwise for positive angles, in the y-down frame: clockwise as seen).
_LUT = {
    0b0001: _rotated(_tile_u, 1),
    0b0010: _rotated(_tile_u, 2),
    0b0011: _rotated(_tile_l, 1),
    0b0100: _rotated(_tile_u, -1),
    0b0101: _rotated(_tile_i, -1),
    0b0110: _rotated(_tile_l, 2),
    0b0111: _tile_t,
    0b1000: _tile_u,
    0b1001: _tile_l,
    0b1010: _tile_i,
    0b1011: _rotated(_tile_t, -1),
    0b1100: _rotated(_tile_l, -1),
    0b1101: _rotated(_tile_t, 2),
    0b1110: _rotated(_tile_t, 1),
    0b1111: _tile_x,
}


def tile(key: int, n: int, chamfer: float = 0.0) -> list[tuple[list[Point], int]]:
    """The traces of a cell connecting on the sides ``key``, in unit-cell coordinates, each
    with its net. ``chamfer`` (0 to 1) cuts the corners at 45 degrees."""
    return list(_LUT[key](n, math.tan(math.pi / 8) * chamfer))


# ----------------------------------------------------------------------------- generator
@dataclass(frozen=True)
class Mesh:
    """A generated mesh: one polyline per net, from its end at the exit cell's open side
    round every reached cell back to its other end there (``ends``: the two points)."""

    traces: tuple[tuple[Point, ...], ...]
    cell: float  # the cells' size
    cells: int  # cells covered
    unreached: int  # cells inside the mask the walk could not reach

    @property
    def ends(self) -> tuple[tuple[Point, Point], ...]:
        return tuple((t[0], t[-1]) for t in self.traces)


def generate(
    mask: shapely.Geometry,
    exit_corner: Point,
    exit_side: int,
    traces: int,
    pitch: float,
    seed: int | str | None = 0,
    randomness: float = 1.0,
    chamfer: float = 0.0,
) -> Mesh:
    """The mesh over ``mask`` (a shapely geometry), ``traces`` nets at ``pitch`` (trace plus
    space). The grid is aligned so that the exit cell's corner with the smallest x and y is
    ``exit_corner``; its side ``exit_side`` (a side bit) is open: the nets' ends leave there.

    ``randomness`` below 1 prefers walking straight on; ``seed`` makes the walk repeatable."""
    if traces < 1:
        raise MeshError("need at least one trace")
    c = 2 * traces * pitch
    ox, oy = exit_corner
    x0, y0, x1, y1 = mask.bounds
    gx0, gy0 = math.floor((x0 - ox) / c), math.floor((y0 - oy) / c)
    gx1, gy1 = math.ceil((x1 - ox) / c), math.ceil((y1 - oy) / c)
    coords = [(gx, gy) for gy in range(gy0, gy1) for gx in range(gx0, gx1)]
    boxes = shapely.box(
        [ox + gx * c for gx, _ in coords],
        [oy + gy * c for _, gy in coords],
        [ox + (gx + 1) * c for gx, _ in coords],
        [oy + (gy + 1) * c for _, gy in coords],
    )
    shapely.prepare(mask)
    inside = shapely.contains(mask, boxes)
    valid = {cell for cell, ok in zip(coords, inside, strict=True) if ok}
    if (0, 0) not in valid:
        raise MeshError("no room for the mesh's exit cell")

    rnd = random.Random(seed)

    def neighbours(x: int, y: int, straight: int) -> list[tuple[int, int, int]]:
        out = [(x + dx, y + dy, side) for side, (dx, dy) in _STEP.items()]
        rnd.shuffle(out)
        if rnd.random() < 1.0 - randomness:  # (KiMesh: keep going the way it came in)
            out.sort(key=lambda q: q[2] != straight)
        return out

    keys: dict[tuple[int, int], int] = {}
    todo = valid - {(0, 0)}
    x, y, key, came = 0, 0, exit_side, _OPPOSITE[exit_side]
    stack: list[tuple[int, int, int, int]] = []
    while True:
        for nx, ny, side in neighbours(x, y, came):
            if (nx, ny) in todo:
                todo.remove((nx, ny))
                stack.append((x, y, key | side, came))
                x, y, key, came = nx, ny, _OPPOSITE[side], side
                break
        else:  # every neighbour done: this cell's tile is final
            keys[x, y] = key
            if not stack:
                break
            x, y, key, came = stack.pop()

    segments: dict[int, list[list[Point]]] = defaultdict(list)
    for (gx, gy), k in keys.items():
        for pts, net in tile(k, traces, chamfer):
            segments[net].append([(ox + (gx + u) * c, oy + (gy + v) * c) for u, v in pts])
    nets = tuple(_join(segments[i]) for i in range(traces))
    return Mesh(nets, c, len(keys), len(todo))


def _join(segments: list[list[Point]]) -> tuple[Point, ...]:
    """Chain one net's segments end to end into one polyline (a path with two loose ends),
    leaving out points where it runs straight on."""

    def key(p: Point) -> tuple[int, int]:
        return (round(p[0] * 1e6), round(p[1] * 1e6))

    at: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, seg in enumerate(segments):
        at[key(seg[0])].append(i)
        at[key(seg[-1])].append(i)
    loose = [k for k, ids in at.items() if len(ids) == 1]
    if len(loose) != 2:
        raise MeshError(f"a net does not form one path ({len(loose)} loose ends)")
    start = min(loose)  # (deterministic)
    used = [False] * len(segments)
    out: list[Point] = []
    here = start
    while True:
        nxt = next((i for i in at[here] if not used[i]), None)
        if nxt is None:
            break
        used[nxt] = True
        seg = segments[nxt]
        if key(seg[0]) != here:
            seg = seg[::-1]
        out.extend(seg if not out else seg[1:])
        here = key(seg[-1])
    if not all(used):
        raise MeshError("a net does not form one path (a closed loop is left over)")
    return _straighten(out)


def _straighten(pts: list[Point]) -> tuple[Point, ...]:
    """The polyline without repeated points and points where it runs straight on."""
    out: list[Point] = []
    for p in pts:
        if out and math.dist(out[-1], p) < 1e-9:
            continue
        if len(out) >= 2:
            (ax, ay), (bx, by) = out[-2], out[-1]
            if abs((bx - ax) * (p[1] - by) - (by - ay) * (p[0] - bx)) < 1e-12 and (
                (bx - ax) * (p[0] - bx) + (by - ay) * (p[1] - by) > 0
            ):
                out[-1] = p
                continue
        out.append(p)
    return tuple(out)
