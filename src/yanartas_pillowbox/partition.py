"""Partitions: a layer's mesh area split into parts of equal area, each a curve of its own
with its own traces from the connector, all laid out at once (``sfc.generate`` with
``partitions``).

Each partition has a *port*: its exit cell, a square a pair of trace lanes wide (``2 n``
pitches: its ``n`` traces out and back) in the row of them along the cable's junction, and
in front of it a *strip* as wide, straight on into the area: its curve runs in along it and
back. The strips lie side by side (nothing between them), the middle ones longest, so that
each one's end and a stretch of its side face the open area. The rest of the area is cut
into Voronoi cells a few ports across (Lloyd's relaxation, each zone, i.e. panel, on its
own, so that no cell straddles a fold); two cells are neighbours only through a wall at
least a port long, so that no partition narrows below a curve's run in and back out. Each
cell goes to the strip its cheapest path starts from (an additively weighted Voronoi
diagram: crossing a fold costs more, every step's cost is varied by a smooth random field
and noise from the seed, so two layers' borders differ), the weights set for equal areas;
then the borders are smoothed (a cell to the partition holding most of its border, a
neighbour across a fold counting little: borders keep to folds) and the areas evened out,
each partition kept of a piece. Its curve keeps half a spacing off its borders, as off a
fold, so two partitions' curves run a spacing apart, as two runs of one curve do.
"""

from __future__ import annotations

import heapq
import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import shapely
import shapely.affinity
from shapely.geometry import Polygon

from yanartas_pillowbox import checkpoint
from yanartas_pillowbox.mesh import MeshError
from yanartas_pillowbox.rand import Rand

LLOYD = 3  # Lloyd iterations of the cells
CELL = 2.5  # the cells this many ports across
STRIP = 1.0  # the outer strips this many ports long (in front of the port)
STAGGER = 1.5  # ... each further in this many ports longer than the one outside it
FOLD = 4.0  # crossing a fold costs this many times as far
NOISE = 0.1  # each step's cost randomized by up to this share
FIELD = 0.5  # ... and varied by up to this share over the area (smoothly)
WAVES = 4  # ... (a sum of this many plane waves)
ITERATIONS = 60  # rounds setting the weights for partitions of equal area
SMOOTH = 4  # passes giving cells to the partition that holds most of their border
ACROSS = 0.25  # ... a neighbour across a fold counting this much
BALANCE = 0.01  # partitions' areas within this share of each other
HOPS = 6  # a partition kept of a piece: looked for this many cells round a cell it gives up
ATTEMPTS = 6  # tries at an even split
UNEVEN = 0.03  # ... even: the partitions' areas within this share of each other


@dataclass(frozen=True)
class Partition:
    """One partition: what its mesh covers (its cells, and in front of them its port and
    strip, where its stem runs), its port and how far in from the port's outer side its
    curve opens (the strip's end)."""

    area: Polygon
    port: Polygon
    reach: float


def _parts(g: shapely.Geometry) -> list[Polygon]:
    return [p for p in shapely.get_parts(g) if isinstance(p, Polygon) and p.area > 1e-9]


def cells(
    area: shapely.Geometry,
    zones: list[Polygon],
    size: float,
    rng: Rand,
    pins: list[tuple[float, float]] = (),
) -> tuple[list[Polygon], list[int], list[int]]:
    """The area as Voronoi cells about ``size`` across, each zone's on its own (Lloyd's
    relaxation; a seed at each of ``pins`` stays there): the cells, each one's zone, and
    each pin's cell (-1: none)."""
    out: list[Polygon] = []
    zone: list[int] = []
    pieces = [(zi, p) for zi, z in enumerate(zones) for p in _parts(z.intersection(area))]
    covered = shapely.union_all([z for z in zones]) if zones else Polygon()
    pieces += [(len(zones), p) for p in _parts(shapely.difference(area, covered))]
    held = np.asarray(pins, float).reshape(-1, 2)
    for zi, piece in pieces:
        k = max(1, round(piece.area / (size * size * math.sqrt(3) / 2)))
        x0, y0, x1, y1 = piece.bounds
        shapely.prepare(piece)
        mine = held[shapely.contains_xy(piece, held[:, 0], held[:, 1])]
        pts = np.zeros((0, 2))
        while len(pts) < k:
            q = rng.uniform((x0, y0), (x1, y1), (4 * k, 2))
            pts = np.vstack([pts, q[shapely.contains_xy(piece, q[:, 0], q[:, 1])]])
        pts = pts[:k]
        if len(mine):
            far = np.hypot(*(pts[:, None] - mine[None]).transpose(2, 0, 1)).min(1) > size / 2
            pts = np.vstack([mine, pts[far]])
        box = shapely.box(x0, y0, x1, y1).buffer(size)
        for it in range(LLOYD + 1):
            got = shapely.intersection(_voronoi(pts, box), piece)
            if it == LLOYD:
                break
            pts = shapely.get_coordinates(shapely.centroid(got))
            pts[: len(mine)] = mine
        for c in got:
            for p in _parts(c):
                out.append(p)
                zone.append(zi)
    at = []
    for q in held:
        hit = [i for i, c in enumerate(out) if c.covers(shapely.Point(q))]
        at.append(hit[0] if hit else -1)
    return out, zone, at


def _voronoi(pts: np.ndarray, box: Polygon) -> np.ndarray:
    """Each point's Voronoi cell (within ``box``), in the points' order (shapely's
    ``ordered`` is newer than the browser's shapely)."""
    cells_ = np.asarray(shapely.get_parts(shapely.voronoi_polygons(
        shapely.multipoints(pts), extend_to=box
    )))  # fmt: skip
    at, cell = shapely.STRtree(cells_).query(shapely.points(pts), predicate="intersects")
    out = np.empty(len(pts), dtype=object)
    out[at] = cells_[cell]  # (a point on two cells' wall: either)
    return out


def _graph(polys: list[Polygon], zone: list[int], wall: float) -> list[list[tuple[int, float]]]:
    """Each cell's neighbours (sharing a border at least ``wall`` long), with the cost of
    the step to it."""
    tree = shapely.STRtree(polys)
    a, b = tree.query(polys, predicate="intersects")
    keep = a < b
    a, b = a[keep], b[keep]
    arr = np.asarray(polys, dtype=object)
    shared = shapely.length(
        shapely.intersection(shapely.boundary(arr[a]), shapely.buffer(arr[b], 1e-6))
    )
    cen = shapely.get_coordinates(shapely.centroid(arr))
    nbrs: list[list[tuple[int, float]]] = [[] for _ in polys]
    for i, j, s in zip(a, b, shared, strict=True):
        if s >= wall:
            step = float(np.hypot(*(cen[i] - cen[j]))) * (FOLD if zone[i] != zone[j] else 1.0)
            nbrs[i].append((int(j), step))
            nbrs[j].append((int(i), step))
    return nbrs


def _connected(
    owner: np.ndarray, nbrs: list[list[tuple[int, float]]], p: int, without: int
) -> bool:
    """Whether partition ``p`` stays of a piece without cell ``without``: its neighbours in
    ``p`` still joined to each other (looked for near it first)."""
    mine = [j for j, _ in nbrs[without] if owner[j] == p]
    if len(mine) <= 1:
        return True
    want = set(mine)
    seen = {mine[0]}
    ring = [mine[0]]
    for _ in range(HOPS):
        nxt = []
        for i in ring:
            for j, _ in nbrs[i]:
                if j != without and j not in seen and owner[j] == p:
                    seen.add(j)
                    nxt.append(j)
        ring = nxt
        if want <= seen:
            return True
    # (not near: all the way round)
    while ring:
        nxt = []
        for i in ring:
            for j, _ in nbrs[i]:
                if j != without and j not in seen and owner[j] == p:
                    seen.add(j)
                    nxt.append(j)
        ring = nxt
        if want <= seen:
            return True
    return False


def _refine(
    owner: np.ndarray,
    nbrs: list[list[tuple[int, float]]],
    zone: list[int],
    area: np.ndarray,
    target: np.ndarray,
    fronts: list[int],
    guard: Callable[[np.ndarray, int], bool] | None = None,
) -> np.ndarray:
    """Each partition of a piece with the cell in front of its strip (cut off pieces to the
    neighbour they border most), its borders smoothed (a cell to the partition holding most of its
    border, a neighbour across a fold counting little) and the areas evened out (cells
    passed on between neighbours, the most uneven pair first), each kept of a piece."""
    owner = owner.copy()
    count = len(target)
    fixed = np.zeros(len(owner), bool)
    fixed[fronts] = True
    src = np.repeat(np.arange(len(owner)), [len(v) for v in nbrs])
    dst = np.array([j for v in nbrs for j, _ in v], int)
    zn = np.asarray(zone)
    weight = np.where(zn[src] == zn[dst], 1.0, ACROSS)

    def votes() -> np.ndarray:
        v = np.bincount(src * count + owner[dst], weight, len(owner) * count)
        return v.reshape(len(owner), count)

    def move(i: int, q: int) -> bool:
        p = int(owner[i])
        if fixed[i] or not _connected(owner, nbrs, p, i):
            return False
        if guard is not None and not guard(owner, i):
            return False
        owner[i] = q
        return True

    for k in range(count):  # (pieces cut off from the strip: to the neighbour most beside)
        seen = {fronts[k]}
        stack = list(seen)
        while stack:
            i = stack.pop()
            for j, _ in nbrs[i]:
                if j not in seen and owner[j] == k:
                    seen.add(j)
                    stack.append(j)
        lost = [i for i in np.nonzero(owner == k)[0] if i not in seen]
        while lost:
            v = votes()
            v[:, k] = 0.0
            rest = []
            for i in lost:
                if v[i].max() > 0:
                    owner[i] = int(np.argmax(v[i]))
                else:
                    rest.append(i)
            if len(rest) == len(lost):
                break
            lost = rest
    for _ in range(SMOOTH):
        v = votes()
        best = np.argmax(v, axis=1)
        mine = v[np.arange(len(owner)), owner]
        cand = np.nonzero((best != owner) & (v.max(1) > 2 * mine) & ~fixed)[0]
        if not sum(move(int(i), int(best[i])) for i in cand):
            break
    blocked: set[tuple[int, int]] = set()
    mean = float(area.mean())
    for _ in range(len(owner)):
        over = np.bincount(owner, area, count) - target
        edge = owner[src] != owner[dst]
        pairs = {(int(a), int(b)) for a, b in zip(owner[src[edge]], owner[dst[edge]], strict=True)}
        pairs = [pq for pq in pairs if pq not in blocked and over[pq[0]] - over[pq[1]] > mean]
        if not pairs or max(over) < BALANCE * float(target.mean()) / 2:
            break
        p, q = max(pairs, key=lambda pq: over[pq[0]] - over[pq[1]])
        need = (over[p] - over[q]) / 2
        v = votes()
        cells_ = np.unique(src[edge & (owner[src] == p) & (owner[dst] == q)])
        cells_ = cells_[np.argsort(-v[cells_, q])]  # (most into q first)
        moved = 0.0
        for i in cells_:
            if moved >= need:
                break
            if move(int(i), q):
                moved += area[i]
        if not moved:
            blocked.add((p, q))
    return owner


@checkpoint.step("partition")
def partition(
    area: shapely.Geometry,
    zones: list[Polygon],
    ports: list[Polygon],
    inward: tuple[float, float],
    width: float,
    seed: int,
) -> list[Partition]:
    """``area`` split into one partition per port (in their order along the junction;
    ``inward`` the way from the junction into the area), of equal area, each holding its
    port, ``width`` wide (a pair of trace lanes: the ports' width), and its strip. A split
    that comes out uneven is tried again afresh."""
    rng = Rand.of(seed, "partition")
    best, worst = None, math.inf
    for _ in range(ATTEMPTS):
        parts = _partition(area, zones, ports, inward, width, rng)
        a = [p.area.area for p in parts]
        bad = (max(a) - min(a)) / max(a)
        # (each port in its partition: but the slivers snapping to the union's grid leaves)
        if any(p.port.difference(p.area).area > 1e-6 * max(1.0, p.port.area) for p in parts):
            bad = math.inf
        if bad < worst:
            best, worst = parts, bad
        if bad < UNEVEN:
            break
    if best is None or worst > 0.5:
        raise MeshError("could not split the mesh's area into partitions")
    return best


def strips(
    ports: list[Polygon],
    inward: tuple[float, float],
    width: float,
    zones: list[Polygon] | None = None,
) -> list[Polygon]:
    """Each port's strip: from the port's inner side straight on in, as wide; the middle
    ones longest, no two side by side as long. With ``zones``, in the first order (rising
    to the longest and falling off again; the outer ports' shortest first on the first
    port's side) that leaves the square in front of every strip's end (where its curve
    opens) within one zone: off a fold that closes in on the ports, a strip running along it
    would end too near it for its curve to open (its domain keeps half a spacing off)."""
    inv = np.asarray(inward, float) / math.hypot(*inward)
    count = len(ports)
    first = sorted(range(count), key=lambda k: (min(k, count - 1 - k), k))
    orders = [first]
    if zones is not None and count <= 6:
        for perm in itertools.permutations(range(count)):
            depth = [perm.index(k) for k in range(count)]  # (each port's rank)
            top = depth.index(max(depth))
            rises = all(a < b for a, b in itertools.pairwise(depth[: top + 1]))
            falls = all(a > b for a, b in itertools.pairwise(depth[top:]))
            if rises and falls and list(perm) != first:
                orders.append(list(perm))

    def laid(rank: list[int]) -> list[tuple[Polygon, Polygon]]:
        out = []
        for k, port in enumerate(ports):
            depth = width * (STRIP + STAGGER * rank.index(k))
            d = shapely.get_coordinates(port) @ inv
            step = float(d.max() - d.min())
            ahead = shapely.affinity.translate(port, *(inv * step))
            far = shapely.affinity.translate(port, *(inv * (step + depth - width)))
            end = shapely.affinity.translate(port, *(inv * (step + depth)))
            out.append((shapely.union_all([ahead, far]).convex_hull, end))
        return out

    if zones is None:
        return [lane for lane, _ in laid(first)]
    grown = [z.buffer(1e-6) for z in zones]
    for rank in orders:
        lanes = laid(rank)
        if all(any(z.contains(end) for z in grown) for _, end in lanes):
            return [lane for lane, _ in lanes]
    raise MeshError(
        "no room for the mesh's exits beside a fold (move the cable's entry: see Cable entry)"
    )


def _partition(
    area: shapely.Geometry,
    zones: list[Polygon],
    ports: list[Polygon],
    inward: tuple[float, float],
    width: float,
    rng: Rand,
) -> list[Partition]:
    count = len(ports)
    inv = np.asarray(inward, float) / math.hypot(*inward)
    lanes = strips(ports, inward, width, zones)
    # (a cell pinned in front of each strip's end, its own: where its curve opens)
    ends = []
    for s in lanes:
        d = shapely.get_coordinates(s) @ inv
        mid = np.asarray(s.centroid.coords[0]) + inv * (
            float(d.max()) - float(s.centroid.coords[0] @ inv)
        )
        ends.append(tuple(mid + inv * CELL * width / 2))
    rest = shapely.difference(area, shapely.union_all([*ports, *lanes]))
    polys, zone, front = cells(rest, zones, CELL * width, rng, ends)
    if len(polys) < 2 * count or min(front) < 0 or len(set(front)) < count:
        raise MeshError("no room for the mesh's partitions")
    # (and the strip's end all its own: a box over it, out of the cells beside)
    side = np.array([-inv[1], inv[0]]) * width / 2
    for k, end in enumerate(ends):
        e = np.asarray(end) - inv * CELL * width / 2  # (the strip's end's middle)
        f = e + inv * 0.75 * width
        cut = shapely.intersection(Polygon([e - side, e + side, f + side, f - side]), rest)
        for i in range(len(polys)):
            if i != front[k] and polys[i].intersects(cut):
                polys[i] = max(
                    _parts(polys[i].difference(cut)) or [Polygon()], key=lambda q: q.area
                )
        polys[front[k]] = _one(shapely.union_all([polys[front[k]], cut]), polys[front[k]])
    gone = {i for i, q in enumerate(polys) if q.is_empty or q.area < 1e-9}
    if gone:
        keep = [i for i in range(len(polys)) if i not in gone]
        remap = {old: new for new, old in enumerate(keep)}
        polys = [polys[i] for i in keep]
        zone = [zone[i] for i in keep]
        front = [remap[i] for i in front]
    nbrs = _graph(polys, zone, 0.99 * width)
    arr = np.asarray(polys, dtype=object)
    cen = shapely.get_coordinates(shapely.centroid(arr))
    cell_area = shapely.area(arr)
    noise = 1.0 + NOISE * rng.random(len(polys))
    field = _field(cen, rng)
    cost = [
        [(j, step * noise[j] * (field[i] + field[j]) / 2) for j, step in v]
        for i, v in enumerate(nbrs)
    ]
    held = [p.area + s.area for p, s in zip(ports, lanes, strict=True)]
    total = float(cell_area.sum() + sum(held))
    want = total / count - np.array(held)
    owner = _weighted(cost, cell_area, [[i] for i in front], want)
    # (cells no path through a wide enough wall reaches: to the partition beside)
    loose = _graph(polys, zone, 1e-3)
    for _ in range(len(polys)):
        lost = np.nonzero(owner < 0)[0]
        if not len(lost):
            break
        for i in lost:
            near = [owner[j] for j, _ in loose[i] if owner[j] >= 0]
            if near:
                owner[i] = max(set(near), key=near.count)
    owner[owner < 0] = 0
    owner = _refine(owner, nbrs, zone, cell_area, want, front)
    # (necks widened, then the areas evened out again without narrowing any: no cell passed
    # on whose partition would come apart without it, eroded as for a neck, round it)
    necks = _Necks(loose, zone, front)
    owner = _widened(owner, necks, set(front))
    owner = _refine(owner, nbrs, zone, cell_area, want, front, necks.spares)
    owner = _pinched(owner, arr, zone, loose, front, width)
    out = []
    for k in range(count):
        g = shapely.union_all([*arr[owner == k], ports[k], lanes[k]], grid_size=1e-6)
        d = shapely.get_coordinates(lanes[k]) @ inv
        e = shapely.get_coordinates(ports[k]) @ inv
        out.append(Partition(_one(g, ports[k]), ports[k], float(d.max() - e.min())))
    return out


class _Necks:
    """Necks on the cell graph: a cell is *interior* to its partition when every neighbour
    of it (through any wall; in its zone, zone by zone) is of the same partition, and a
    partition's *wide parts* are its interior cells' groups (joined through walls), so that
    two wide parts are joined only through a neck under three cells wide, where a curve
    runs in and back out with no room to turn: its graph's cycles there join the rest at a
    few cells only, if at all, and leave the part beyond bare. Its exit's cell, with no wide
    part within two steps of it, counts as a part of its own (a neck cuts it off from the
    rest)."""

    def __init__(
        self, loose: list[list[tuple[int, float]]], zone: list[int], front: list[int]
    ) -> None:
        self.loose = loose
        self.nb = [[j for j, _ in v] for v in loose]
        self.zn = np.asarray(zone)
        self.front = front
        self.src = np.repeat(np.arange(len(loose)), [len(v) for v in loose])
        self.dst = np.array([j for v in loose for j, _ in v], int)
        self.same = self.zn[self.src] == self.zn[self.dst]

    def parts(self, owner: np.ndarray, k: int, z: int | None) -> list[list[int]]:
        """Partition ``k``'s wide parts (in zone ``z``; None: all), the largest first."""
        n = len(owner)
        edges = np.ones(len(self.src), bool) if z is None else self.same
        out_edge = edges & (owner[self.dst] != k)
        interior = (owner == k) & (np.bincount(self.src[out_edge], minlength=n) == 0)
        if z is not None:
            interior &= self.zn == z
        cells = set(np.nonzero(interior)[0].tolist())
        groups = []
        while cells:
            start = cells.pop()
            group, todo = [start], [start]
            while todo:
                i = todo.pop()
                for j in self.nb[i]:
                    if j in cells:
                        cells.discard(j)
                        group.append(j)
                        todo.append(j)
            if len(group) > 1:  # (a lone interior cell: no room to turn either)
                groups.append(group)
        groups.sort(key=len, reverse=True)
        f = self.front[k] if k < len(self.front) else None
        if f is not None and groups and (z is None or self.zn[f] == z) and owner[f] == k:
            # (within two steps: the cells beside the exit's touch the strips' ends beside)
            near = {f, *self.nb[f]}
            near |= {j for c in list(near) for j in self.nb[c]}
            if not any(near.intersection(g) for g in groups):
                groups.insert(1, [f])
        return groups

    def count(self, owner: np.ndarray, k: int, z: int | None) -> int:
        return len(self.parts(owner, k, z))

    def spares(self, owner: np.ndarray, i: int) -> bool:
        """Whether cell ``i`` can leave its partition without narrowing it: round it (three
        steps through walls, in its zone), its partition's wide parts come apart into no more
        groups without it than with it."""
        m, z = int(owner[i]), int(self.zn[i])
        ring, seen = [i], {i}
        for _ in range(3):
            ring = [j for c in ring for j in self.nb[c] if j not in seen and self.zn[j] == z]
            seen.update(ring)
        window = [c for c in seen if owner[c] == m]
        near = {c: [j for j in self.nb[c] if j in seen and self.zn[j] == z] for c in window}

        def groups(without: int | None) -> int:
            mine = {c for c in window if c != without}
            # (interior: every neighbour seen, in the zone, its own; beyond the window: as if)
            inner = {
                c
                for c in mine
                if all(owner[j] == m and j != without for j in self.nb[c] if j in near[c])
            }
            n, left = 0, set(inner)
            while left:
                todo = [left.pop()]
                n += 1
                while todo:
                    c = todo.pop()
                    for j in self.nb[c]:
                        if j in left:
                            left.discard(j)
                            todo.append(j)
            return n

        return groups(i) <= groups(None)


def _widened(owner: np.ndarray, necks: _Necks, fixed: set[int]) -> np.ndarray:
    """Each partition's necks widened where the cells beside allow, as a whole and zone by
    zone (a curve's regions are a partition's pieces in each zone, each laid out on its own,
    joined to the others across the folds): where its wide parts (``_Necks``) are several,
    it takes the cells on the cheapest way from its largest to the next (its own cells free,
    a neighbour's at a cost) and those beside them, each a neighbour can spare (not one it
    needs to hold together itself or to stay wide, nor a strip's end's), a corridor three
    cells wide, until its wide parts are one or none can be spared."""
    owner = owner.copy()
    nb, zn = necks.nb, necks.zn
    for _ in range(3):
        moved = False
        for k in range(int(owner.max()) + 1):
            for z in [None, *sorted(set(zn[owner == k].tolist()))]:
                for _ in range(4):
                    parts = necks.parts(owner, k, z)
                    if len(parts) < 2:
                        break
                    path = _cheapest(owner, nb, zn, k, z, parts[0], set(parts[1]), fixed)
                    if path is None:
                        break
                    want = [c for c in path if owner[c] != k]
                    want += [
                        j
                        for c in path
                        for j in nb[c]
                        if owner[j] != k and (z is None or zn[j] == z)
                    ]
                    took = False
                    for j in dict.fromkeys(want):
                        if owner[j] == k or j in fixed:
                            continue
                        if _connected(owner, necks.loose, int(owner[j]), j) and necks.spares(
                            owner, j
                        ):
                            owner[j] = k
                            took = moved = True
                    if not took:
                        break
        if not moved:
            break
    return owner


def _cheapest(
    owner: np.ndarray,
    nb: list[list[int]],
    zn: np.ndarray,
    k: int,
    z: int | None,
    start: list[int],
    goal: set[int],
    fixed: set[int],
) -> list[int] | None:
    """The cheapest way through the cells (in zone ``z``; None: any) from ``start`` to
    ``goal``: partition ``k``'s cells free, any other's one each (a strip's end's: none)."""
    dist = {c: 0 for c in start}
    back: dict[int, int] = {}
    heap = [(0, c) for c in start]
    while heap:
        d, c = heapq.heappop(heap)
        if c in goal:
            path = [c]
            while path[-1] in back:
                path.append(back[path[-1]])
            return path
        if d > dist[c]:
            continue
        for j in nb[c]:
            if (z is not None and zn[j] != z) or (j in fixed and owner[j] != k):
                continue
            nd = d + (0 if owner[j] == k else 1)
            if nd < dist.get(j, math.inf):
                dist[j] = nd
                back[j] = c
                heapq.heappush(heap, (nd, j))
    return None


def _pinched(
    owner: np.ndarray,
    arr: np.ndarray,
    zone: list[int],
    loose: list[list[tuple[int, float]]],
    front: list[int],
    width: float,
) -> np.ndarray:
    """The cells of a partition's piece in a zone past a passage narrower than its curve's
    run in and back out (where its curve's domain, the piece shrunk by half a spacing, comes
    apart: what lies past it no curve reaches) to the neighbour beside them most."""
    owner = owner.copy()
    zn = np.asarray(zone)
    cen = shapely.points(shapely.get_coordinates(shapely.centroid(arr)))
    fixed = set(front)
    for _ in range(4):
        moved = False
        for k in range(owner.max() + 1):
            for z in set(zn[owner == k].tolist()):
                mine = np.nonzero((owner == k) & (zn == z))[0]
                piece = shapely.union_all(arr[mine], grid_size=1e-6)
                for g in _parts(piece):
                    parts = _parts(g.buffer(-width / 4))
                    if len(parts) < 2:
                        continue
                    main = max(parts, key=lambda q: q.area).buffer(width / 4 + 1e-6)
                    for i in mine:
                        if i in fixed or not g.covers(cen[i]) or main.covers(cen[i]):
                            continue
                        near = [owner[j] for j, _ in loose[i] if owner[j] != k]
                        if near:
                            owner[i] = max(set(near), key=near.count)
                            moved = True
        if not moved:
            break
    return owner


def _field(cen: np.ndarray, rng: Rand) -> np.ndarray:
    """A smooth random cost over the cells (a few plane waves, about as long as the area
    is wide): the partitions' borders bent one way on one layer, another on the other."""
    span = float(np.ptp(cen, axis=0).max()) or 1.0
    out = np.zeros(len(cen))
    for _ in range(WAVES):
        angle = rng.uniform(0, math.tau)
        k = math.tau / (span * rng.uniform(0.3, 1.0))
        out += np.cos(
            cen @ np.array([math.cos(angle), math.sin(angle)]) * k + rng.uniform(0, math.tau)
        )
    return 1.0 + FIELD * out / WAVES


def _weighted(
    cost: list[list[tuple[int, float]]],
    area: np.ndarray,
    sources: list[list[int]],
    want: np.ndarray,
) -> np.ndarray:
    """Each cell to the source its cheapest path starts from, each source's start weighted
    (an additively weighted Voronoi diagram over the cells, from the strips' ends): each
    partition the tree of its source's paths, so of a piece; the weights set so that each
    gets about ``want`` of the area (cells no path reaches: -1)."""
    count = len(sources)
    w = np.zeros(count)
    best, best_err = None, math.inf
    step = None
    for _ in range(ITERATIONS):
        owner = np.full(len(area), -1)
        dist = np.full(len(area), np.inf)
        heap = []
        for k, cs in enumerate(sources):
            for i in cs:
                if -w[k] < dist[i]:
                    dist[i] = -w[k]
                    owner[i] = k
                    heap.append((-w[k], i, k))
        heapq.heapify(heap)
        while heap:
            d, i, k = heapq.heappop(heap)
            if d > dist[i] or owner[i] != k:
                continue
            for j, c in cost[i]:
                if d + c < dist[j]:
                    dist[j] = d + c
                    owner[j] = k
                    heapq.heappush(heap, (d + c, j, k))
        have = np.bincount(owner[owner >= 0], area[owner >= 0], count)
        err = have / want - 1
        if np.abs(err).max() < best_err:
            best, best_err = owner.copy(), float(np.abs(err).max())
        if best_err < BALANCE / 2:
            break
        if step is None:  # (about a tenth of how far the cells lie from their sources)
            step = 0.1 * float(np.median(dist[np.isfinite(dist)] + w[owner[np.isfinite(dist)]]))
        w -= np.clip(err, -1, 1) * step
        w -= w.mean()
        step *= 0.93
    assert best is not None
    return best


def _one(g: shapely.Geometry, port: Polygon) -> Polygon:
    """The piece reaching the port (the rest, if any, unreachable: dropped)."""
    pieces = _parts(g)
    return max(pieces, key=lambda q: (q.intersects(port.buffer(1e-6)), q.area))
