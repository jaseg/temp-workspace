"""The block world: a grid of cells, one block each, holding the floor, redstone dust, blocks and text plaques,
and the tools to place things into it without collisions (`fits`, `route`, `place_plaque`).

Cells are (i, j): i east, j south. Everything drawn on the page is a block in some cell, so all of it shares the
schematic's grid."""

import heapq
import math
from dataclasses import dataclass, field

DIRS = {'north': (0, -1), 'south': (0, 1), 'east': (1, 0), 'west': (-1, 0)}
OPP = {'north': 'south', 'south': 'north', 'east': 'west', 'west': 'east'}


def dir_of(dx, dz):
    if abs(dx) >= abs(dz):
        return 'east' if dx > 0 else 'west'
    return 'south' if dz > 0 else 'north'


def step(c, d):
    return c[0] + DIRS[d][0], c[1] + DIRS[d][1]


def dust_tint(power):
    """Redstone dust colour for a power level, as the game computes it."""
    f = power / 15
    r = f * .6 + (.4 if power else .3)
    g = max(0.0, f * f * .7 - .5)
    b = max(0.0, f * f * .6 - .7)
    return round(r * 255), round(g * 255), round(b * 255)


@dataclass
class Block:
    """A block (or several stacked) to draw in a cell. `kind` is 'state' (pack blockstate), 'box' (a box of block
    textures, for bodies and plaques) or 'raw' (a prepared sprite id)."""
    i: float
    y: float
    j: float
    kind: str
    args: tuple
    flat: bool = False          # flat on the floor: drawn before everything that stands up
    owner: object = None
    overlay: bool = False       # part of the page frame, drawn flat on top of everything


@dataclass
class Text:
    """Text painted onto a plane: `origin` (world), `u` and `v` (world vectors along the image's x and y)."""
    text: str
    origin: tuple
    u: tuple
    v: tuple
    color: tuple
    shadow: bool = True
    layer: str = 'flat'
    scale: float = 1.0


@dataclass
class Plaque:
    """A text on a base of block textures, `w` x `h` cells with its top-left cell at (i, j)."""
    text: str
    i: int
    j: int
    w: int
    h: int
    vertical: bool
    style: str
    scale: int = 1
    meta: dict = field(default_factory=dict)


class World:
    def __init__(self, i0, j0, i1, j1):
        self.i0, self.j0 = i0, j0           # the world's cells are i0 <= i < W, j0 <= j < H
        self.W, self.H = i1, j1
        self.dust = {}              # cell -> {net: set of directions}
        self.solid = {}             # cell -> owner, for anything that blocks dust, plaques and other parts
        self.soft = {}              # cell -> owner, kept clear for one owner (pins before they are routed)
        self.blocks = []
        self.plaques = []
        self.texts = []
        self.floor = {}             # cell -> floor block id (default: decided by the page)
        self.circuit = set()        # cells that belong to the schematic (for the platform and decorations)

    def inside(self, c):
        return self.i0 <= c[0] < self.W and self.j0 <= c[1] < self.H

    # -- dust -------------------------------------------------------------------
    def link(self, a, b, net):
        """Dust of `net` from cell a to the neighbouring cell b."""
        d = dir_of(b[0] - a[0], b[1] - a[1])
        self.dust.setdefault(a, {}).setdefault(net, set()).add(d)
        self.dust.setdefault(b, {}).setdefault(net, set()).add(OPP[d])
        self.circuit.update((a, b))

    def dot(self, c, net):
        self.dust.setdefault(c, {}).setdefault(net, set())
        self.circuit.add(c)

    def path(self, cells, net):
        if len(cells) == 1:
            self.dot(cells[0], net)
        for a, b in zip(cells, cells[1:]):
            self.link(a, b, net)

    def free_for(self, c, owner=None, net=None, dust_ok=False):
        """Whether a part (owner) may use cell c."""
        if not self.inside(c):
            return False
        o = self.solid.get(c)
        if o is not None and o != owner:
            return False
        s = self.soft.get(c)
        if s is not None and s != owner:
            return False
        if not dust_ok and c in self.dust:
            nets = self.dust[c]
            if net is None or any(n != net for n in nets):
                return False
        return True

    def occupy(self, cells, owner):
        for c in cells:
            self.solid[c] = owner
            self.circuit.add(c)

    # -- routing ------------------------------------------------------------------
    def route(self, start, goal, net, owner=None, limit=40, avoid=()):
        """Shortest dust path from start to goal with few bends, through cells that are free or carry the same
        net. Returns the cells (start and goal included) or None."""
        if start == goal:
            return [start]
        avoid = set(avoid)
        pq = [(0, start, None)]
        best = {(start, None): 0}
        prev = {}
        while pq:
            cost, c, d = heapq.heappop(pq)
            if c == goal:
                out = [c]
                key = (c, d)
                while key in prev:
                    key = prev[key]
                    out.append(key[0])
                return out[::-1]
            if cost > limit:
                break
            for nd, (dx, dz) in DIRS.items():
                n = (c[0] + dx, c[1] + dz)
                if n in avoid:
                    continue
                if n != goal and not self.passable(n, net, owner):
                    continue
                nc = cost + 1 + (0 if d in (None, nd) else 1.5)
                if nc < best.get((n, nd), 1e9):
                    best[(n, nd)] = nc
                    prev[(n, nd)] = (c, d)
                    heapq.heappush(pq, (nc, n, nd))
        return None

    def passable(self, c, net, owner):
        if not self.inside(c):
            return False
        o = self.solid.get(c)
        if o is not None:
            return False
        s = self.soft.get(c)
        if s is not None and s != owner:
            return False
        nets = self.dust.get(c)
        return not nets or set(nets) == {net}

    # -- plaques ------------------------------------------------------------------
    def plaque_cells(self, i, j, w, h):
        return [(i + a, j + b) for a in range(w) for b in range(h)]

    def place_plaque(self, pq, reach=3, avoid_dust=True, along=None, owner=None, net=None):
        """Put a plaque at its spot, or nudged as little as possible to where it covers nothing. Returns whether it
        found a clear spot (it is placed at its own spot otherwise). A plaque may lie on dust of `net`."""
        best = None
        for di, dj in nudges(reach, along):
            i, j = pq.i + di, pq.j + dj
            cells = self.plaque_cells(i, j, pq.w, pq.h)
            if all(self.inside(c) and c not in self.solid
                   and (not avoid_dust or c not in self.dust or (net is not None and set(self.dust[c]) == {net}))
                   and self.soft.get(c) in (None, owner) for c in cells):
                best = (i, j)
                break
        ok = best is not None
        if ok:
            pq.i, pq.j = best
        self.plaques.append(pq)
        cells = self.plaque_cells(pq.i, pq.j, pq.w, pq.h)
        for c in cells:
            self.solid.setdefault(c, pq)
        self.circuit.update(cells)
        return ok


def nudges(reach, along=None):
    """Offsets to try, nearest first; `along` ('x' or 'z') prefers moving along that axis."""
    out = []
    for di in range(-reach * 2, reach * 2 + 1):
        for dj in range(-reach, reach + 1):
            if along == 'z':
                cost = abs(di) * 1.6 + abs(dj)
            else:
                cost = abs(di) + abs(dj) * 1.3
            out.append((cost, abs(dj), abs(di), (di, dj)))
    out.sort()
    return [o[-1] for o in out if o[0] <= reach * 2.2]


def cells_on_segment(a, b):
    """The cells from a to b: straight, or as a staircase for slanted segments."""
    (i0, j0), (i1, j1) = a, b
    out = [(i0, j0)]
    i, j = i0, j0
    n = max(abs(i1 - i0), abs(j1 - j0))
    if n == 0:
        return out
    for k in range(1, n + 1):
        ti = i0 + round((i1 - i0) * k / n)
        tj = j0 + round((j1 - j0) * k / n)
        if ti != i and tj != j:          # diagonal step: go round the corner
            out.append((ti, j))
        i, j = ti, tj
        out.append((i, j))
    return out


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])
