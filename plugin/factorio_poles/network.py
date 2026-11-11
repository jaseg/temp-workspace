"""Decide which poles are wired to each other.

Rules (Factorio's, restricted to what makes sense on a schematic):

* Only poles on the same net (same Value) are ever wired together.
* Two poles can be wired if they are no further apart than the *shorter* of their
  two ``maximum_wire_distance`` values.
* A pole holds at most ``max_connections`` copper wires (5 in Factorio).

Within those rules there are two layouts:

``tree`` (default)
    The shortest set of wires that connects everything reachable: a minimum
    spanning forest.  No redundant triangles, so the drawing stays clean.

``mesh``
    Every pair in reach gets a wire, shortest first, until each pole has used up its
    connections.  Busier, and closer to what you get by hand-placing poles in-game.

Anything that can't be reached ends up in a separate *island*; :func:`islands`
reports them so the plugin can point them out.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .geometry import orientation_frame
from .prototypes import MAX_COPPER_CONNECTIONS, PoleType, wire_reach


@dataclass(frozen=True)
class Pole:
    id: str  # KiCad item UUID of the symbol
    net: str  # value of the power symbol = net name
    type: PoleType
    position: tuple[float, float]  # tiles

    def distance(self, other: Pole) -> float:
        return math.dist(self.position, other.position)


@dataclass(frozen=True)
class Wire:
    a: Pole
    b: Pole

    @property
    def key(self) -> tuple[str, str]:
        return (self.a.id, self.b.id)


class _DisjointSet:
    def __init__(self, items: Iterable[str]):
        self.parent = {i: i for i in items}

    def find(self, i: str) -> str:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: str, b: str) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        # Deterministic: the smaller id becomes the root.
        if rb < ra:
            ra, rb = rb, ra
        self.parent[rb] = ra
        return True


def _candidates(poles: Sequence[Pole]) -> list[tuple[float, Pole, Pole]]:
    out = []
    ordered = sorted(poles, key=lambda p: p.id)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            if a.net != b.net:
                continue
            d = a.distance(b)
            if d <= wire_reach(a.type, b.type) + 1e-9 and d > 1e-9:
                out.append((d, a, b))
    # Ties broken by ids so the same schematic always produces the same wires.
    out.sort(key=lambda e: (round(e[0], 9), e[1].id, e[2].id))
    return out


def connect(poles: Sequence[Pole], mode: str = "tree", max_connections: int = MAX_COPPER_CONNECTIONS) -> list[Wire]:
    """Compute the wires for one sheet's worth of poles."""
    if mode not in ("tree", "mesh"):
        raise ValueError(f"unknown connection mode {mode!r}")
    dsu = _DisjointSet(p.id for p in poles)
    degree: dict[str, int] = defaultdict(int)
    wires: list[Wire] = []
    for _, a, b in _candidates(poles):
        if degree[a.id] >= max_connections or degree[b.id] >= max_connections:
            continue
        if mode == "tree" and dsu.find(a.id) == dsu.find(b.id):
            continue
        dsu.union(a.id, b.id)
        degree[a.id] += 1
        degree[b.id] += 1
        wires.append(Wire(a, b))
    return wires


def islands(poles: Sequence[Pole], wires: Sequence[Wire]) -> dict[str, list[list[Pole]]]:
    """Group each net's poles into connected islands, largest island first."""
    dsu = _DisjointSet(p.id for p in poles)
    for w in wires:
        dsu.union(w.a.id, w.b.id)
    by_net: dict[str, dict[str, list[Pole]]] = defaultdict(lambda: defaultdict(list))
    for p in sorted(poles, key=lambda p: p.id):
        by_net[p.net][dsu.find(p.id)].append(p)
    return {net: sorted(groups.values(), key=lambda g: (-len(g), g[0].id)) for net, groups in sorted(by_net.items())}


def orientations(poles: Sequence[Pole], wires: Sequence[Wire]) -> dict[str, int]:
    """Direction frame for every pole, facing its wires."""
    neighbours: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for w in wires:
        neighbours[w.a.id].append(w.b.position)
        neighbours[w.b.id].append(w.a.position)
    return {p.id: orientation_frame(p.position, neighbours[p.id], p.type.frames) for p in poles}
