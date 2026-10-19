"""Security meshes: what the layout algorithms share.

Two algorithms lay out a mesh, each in its own module:

- ``kimesh``: KiMesh's tiles on a square grid, walked by a randomized spanning tree;
- ``sfc``: a closed space-filling curve after Bedel et al. (2022), offset into the traces.

Both take the area to cover (the *mask*, a shapely geometry) and the *exit cell*: a square
``2 n`` trace pitches wide at ``exit_corner`` (its corner with the smallest x and y) whose
side ``exit_side`` is open. They return a ``Mesh``: ``n`` nets, each one polyline whose two
ends lie on that side, at the pitch, mirrored about its middle (net 1 outermost).

Coordinates: x right, y down (as the pattern); side bits 0b0001 +x, 0b0010 +y, 0b0100 -x,
0b1000 -y.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Point = tuple[float, float]

RIGHT, DOWN, LEFT, UP = 0b0001, 0b0010, 0b0100, 0b1000
STEP = {RIGHT: (1, 0), DOWN: (0, 1), LEFT: (-1, 0), UP: (0, -1)}
OPPOSITE = {RIGHT: LEFT, DOWN: UP, LEFT: RIGHT, UP: DOWN}


class MeshError(ValueError):
    """The mesh cannot be laid out (e.g. no room for its exit cell)."""


@dataclass(frozen=True)
class Mesh:
    """A generated mesh: one polyline per net, from its end at the exit cell's open side
    round the area back to its other end there (``ends``: the two points)."""

    traces: tuple[tuple[Point, ...], ...]
    cell: float  # the exit cell's size (KiMesh: every cell's)
    cells: int  # cells covered (KiMesh: grid cells; sfc: the curve's graph cells)
    unreached: int  # parts the mesh could not reach (KiMesh: grid cells; sfc: regions)
    origin: Point = (0.0, 0.0)  # the exit cell's corner: the grid's alignment

    @property
    def ends(self) -> tuple[tuple[Point, Point], ...]:
        return tuple((t[0], t[-1]) for t in self.traces)


def straighten(pts: list[Point]) -> tuple[Point, ...]:
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
