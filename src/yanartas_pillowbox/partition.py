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
ATTEMPTS = 6  # tries at an even split, with no neck
UNEVEN = 0.03  # ... even: the partitions' areas within this share of each other
LOPSIDED = UNEVEN  # ... but rather one with a neck than one less even than that
NECK = 2.0  # a partition no narrower than this many ports where it can be wider
PART = 3  # ... where it is wider: this many cells, or more
WALL = (0.25, 0.5, 0.75)  # ... tested at these points along each wall between cells
WIDEN = 20  # ... widened at most this many times a partition and zone a round


class Uneven(MeshError):
    """No try split the area evenly."""


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


def _walls(polys: list[Polygon]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The walls between cells: each pair's cells (``a < b``) and their shared border."""
    tree = shapely.STRtree(polys)
    a, b = tree.query(polys, predicate="intersects")
    keep = a < b
    a, b = a[keep], b[keep]
    arr = np.asarray(polys, dtype=object)
    return a, b, shapely.intersection(shapely.boundary(arr[a]), shapely.buffer(arr[b], 1e-6))


def _graph(
    walls: tuple[np.ndarray, np.ndarray, np.ndarray],
    cen: np.ndarray,
    zone: list[int],
    wall: float,
) -> list[list[tuple[int, float]]]:
    """Each cell's neighbours (sharing a border at least ``wall`` long), with the cost of
    the step to it."""
    a, b, shared = walls
    nbrs: list[list[tuple[int, float]]] = [[] for _ in cen]
    for i, j, s in zip(a, b, shapely.length(shared), strict=True):
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
    ends: list[Polygon] | None = None,
) -> list[Partition]:
    """``area`` split into one partition per port (in their order along the junction;
    ``inward`` the way from the junction into the area), of equal area, each holding its
    port, ``width`` wide (a pair of trace lanes: the ports' width), and its strip. A split
    that comes out uneven is tried again afresh. ``ends``: the zones each strip's end must
    lie within one of (where its curve opens; default: ``zones``)."""
    rng = Rand.of(seed, "partition")
    cut = _Cells(area, zones, ports, inward, width, rng, ends)
    tried = []
    for _ in range(ATTEMPTS):
        owner, necks = cut.attempt(rng)
        have = np.bincount(owner, cut.area, len(ports)) + cut.held
        off = float((have.max() - have.min()) / have.max())
        tried.append(((off > LOPSIDED, necks, off), len(tried), owner))
        if not necks and off < UNEVEN:
            break
    for (_, _, off), _, owner in sorted(tried, key=lambda t: t[:2]):
        if off > 0.5:
            break
        parts = cut.finished(owner)
        # (each port in its partition: but the slivers snapping to the union's grid leaves)
        if all(p.port.difference(p.area).area <= 1e-6 * max(1.0, p.port.area) for p in parts):
            return parts
    raise Uneven("could not split the mesh's area into partitions")


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


class _Cells:
    """A layer's area in cells, with its strips and their ends' cells, the cells' graphs
    and necks: set up once for all attempts at a split."""

    def __init__(
        self,
        area: shapely.Geometry,
        zones: list[Polygon],
        ports: list[Polygon],
        inward: tuple[float, float],
        width: float,
        rng: Rand,
        ends_in: list[Polygon] | None = None,
    ) -> None:
        count = len(ports)
        self.inv = inv = np.asarray(inward, float) / math.hypot(*inward)
        self.ports, self.width = ports, width
        self.lanes = lanes = strips(ports, inward, width, zones if ends_in is None else ends_in)
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
        self.zone, self.front = zone, front
        self.arr = arr = np.asarray(polys, dtype=object)
        self.cen = shapely.get_coordinates(shapely.centroid(arr))
        walls = _walls(polys)
        self.nbrs = _graph(walls, self.cen, zone, 0.99 * width)
        # (cells no path through a wide enough wall reaches: given to the partition beside)
        self.loose = _graph(walls, self.cen, zone, 1e-3)
        self.area = shapely.area(arr)
        self.held = np.array([p.area + s.area for p, s in zip(ports, lanes, strict=True)])
        total = float(self.area.sum() + self.held.sum())
        self.want = total / count - self.held
        self.necks = _Necks(arr, zone, walls, self.loose, front, width)

    def attempt(self, rng: Rand) -> tuple[np.ndarray, int]:
        """A split (each cell's partition) and how many necks it has left."""
        nbrs, loose, zone, front = self.nbrs, self.loose, self.zone, self.front
        noise = 1.0 + NOISE * rng.random(len(self.arr))
        field = _field(self.cen, rng)
        cost = [
            [(j, step * noise[j] * (field[i] + field[j]) / 2) for j, step in v]
            for i, v in enumerate(nbrs)
        ]
        owner = _weighted(cost, self.area, [[i] for i in front], self.want)
        for _ in range(len(owner)):
            lost = np.nonzero(owner < 0)[0]
            if not len(lost):
                break
            for i in lost:
                near = [owner[j] for j, _ in loose[i] if owner[j] >= 0]
                if near:
                    owner[i] = max(set(near), key=near.count)
        owner[owner < 0] = 0
        owner = _refine(owner, nbrs, zone, self.area, self.want, front)
        # (necks widened, then the areas evened out again without narrowing any)
        owner = _widened(owner, self.necks, nbrs, set(front))
        owner = _refine(owner, nbrs, zone, self.area, self.want, front, self.necks.spares)
        return owner, self.necks.left(owner)

    def finished(self, owner: np.ndarray) -> list[Partition]:
        """The partitions of a split, what lies past a passage too narrow for any curve
        given to the neighbours."""
        owner = _pinched(owner, self.arr, self.zone, self.loose, self.front, self.width)
        out = []
        for k, (port, lane) in enumerate(zip(self.ports, self.lanes, strict=True)):
            g = shapely.union_all([*self.arr[owner == k], port, lane], grid_size=1e-6)
            d = shapely.get_coordinates(lane) @ self.inv
            e = shapely.get_coordinates(port) @ self.inv
            out.append(Partition(_one(g, port), port, float(d.max() - e.min())))
        return out


def _components(n: int, a: np.ndarray, b: np.ndarray, node: np.ndarray) -> np.ndarray:
    """Each node's component through the edges ``a``-``b`` (named by its least node; -1:
    not a node): least names passed along the edges, then followed to their own."""
    lab = np.where(node, np.arange(n), -1)
    while True:
        m = np.minimum(lab[a], lab[b])
        new = lab.copy()
        np.minimum.at(new, a, m)
        np.minimum.at(new, b, m)
        on = new >= 0
        while True:  # (each name to its own name's: halving the chains)
            jump = np.where(on, new[np.where(on, new, 0)], -1)
            if (jump == new).all():
                break
            new = jump
        if (new == lab).all():
            return lab
        lab = new


class _Necks:
    """Necks, as where a partition eroded by ``NECK`` ports comes apart, tested at points
    (each cell's centre, and three along each wall between two cells): a point is *clear*
    when no border lies within ``NECK`` ports' half of it, the area's outline or a wall
    between two partitions (zone by zone: or two zones). The walls near each point are
    found once, so whether it is clear is a look at their two cells' partitions. A
    partition's *wide parts* are its cells with clear centres joined through walls with a
    clear point, those of ``PART`` cells or more: two of them are joined only through a
    neck, narrower than a run in and back out, where its curve's graph's cycles join the
    rest at a few cells only, if at all, and leave the part beyond bare. Its exit's cell,
    with no wide part within two steps of it, counts as a part of its own (a neck cuts it
    off from the rest)."""

    def __init__(
        self,
        arr: np.ndarray,
        zone: list[int],
        walls: tuple[np.ndarray, np.ndarray, np.ndarray],
        loose: list[list[tuple[int, float]]],
        front: list[int],
        width: float,
    ) -> None:
        n = len(arr)
        self.n = n
        self.loose = loose
        self.nb = [[j for j, _ in v] for v in loose]
        self.zn = np.asarray(zone)
        self.front = front
        a, b, walls = walls
        keep = shapely.length(walls) >= 1e-3  # (as the loose graph's)
        a, b, walls = a[keep], b[keep], walls[keep]
        self.a, self.b, self.m = a, b, len(a)
        self.wall = {(int(i), int(j)): w for w, (i, j) in enumerate(zip(a, b, strict=True))}
        cen = shapely.centroid(arr)
        off = ~shapely.covers(arr, cen)
        cen[off] = shapely.point_on_surface(arr[off])
        probes = np.concatenate(
            [cen, *(shapely.line_interpolate_point(walls, f, normalized=True) for f in WALL)]
        )
        self.probes = probes
        reach = NECK * width / 2
        outline = shapely.boundary(shapely.union_all(arr, grid_size=1e-6))
        shapely.prepare(outline)
        self.always = shapely.dwithin(outline, probes, reach)
        p, w = shapely.STRtree(walls).query(probes, predicate="dwithin", distance=reach)
        order = np.argsort(p, kind="stable")
        self.pp, self.pa, self.pb = p[order], a[w[order]], b[w[order]]
        self.at = np.searchsorted(self.pp, np.arange(len(probes) + 1))
        self.local: dict[int, tuple] = {}
        self.natives: dict[bool, np.ndarray] = {}
        self.last: tuple = (None, None)

    def clear(self, owner: np.ndarray, zonal: bool) -> np.ndarray:
        """Whether each point is clear."""
        bad = owner[self.pa] != owner[self.pb]
        if zonal:
            bad |= self.zn[self.pa] != self.zn[self.pb]
        out = ~self.always
        out[self.pp[bad]] = False
        return out

    def _wall_clear(self, ok: np.ndarray) -> np.ndarray:
        n, m = self.n, self.m
        return ok[n:].reshape(len(WALL), m).any(0)

    def _labels(self, owner: np.ndarray, zonal: bool) -> np.ndarray:
        """Each cell's group (-1: no clear centre): cells of a partition with clear centres
        joined through walls with a clear point (``zonal``: walls between zones as borders),
        named by a cell of theirs."""
        key = (owner.tobytes(), zonal)
        if self.last[0] == key:
            return self.last[1]
        ok = self.clear(owner, zonal)
        node = ok[: self.n]
        edge = self._wall_clear(ok) & node[self.a] & node[self.b]
        lab = _components(self.n, self.a[edge], self.b[edge], node)
        self.last = (key, lab)
        return lab

    def _native(self, zonal: bool) -> np.ndarray:
        """Each cell's group as if the area were one partition (-1: no clear centre): where
        the area itself is narrow, by its outline or between folds."""
        if zonal not in self.natives:
            self.natives[zonal] = self._labels(np.zeros(self.n, int), zonal)
        return self.natives[zonal]

    def parts(self, owner: np.ndarray, k: int, z: int | None) -> list[list[int]]:
        """Partition ``k``'s wide parts (in zone ``z``; None: all) that a neck parts where
        the area itself is wide, the largest first: of the area's wide stretch where the
        second largest is largest."""
        native = self._native(z is not None)
        lab = self._labels(owner, z is not None)
        mine = (owner == k) & (lab >= 0)
        if z is not None:
            mine &= self.zn == z
        cells = np.nonzero(mine)[0]
        names, which = np.unique(lab[cells], return_inverse=True)
        by: dict[int, list[list[int]]] = {}
        for g in range(len(names)):
            group = cells[which == g].tolist()
            if len(group) >= PART:
                by.setdefault(int(native[group[0]]), []).append(group)
        for gs in by.values():
            gs.sort(key=len, reverse=True)
        groups = max(by.values(), key=lambda gs: len(gs[1]) if len(gs) > 1 else 0, default=[])
        f = self.front[k] if k < len(self.front) else None
        if f is not None and by and (z is None or self.zn[f] == z) and owner[f] == k:
            # (within two steps: the cells beside the exit's touch the strips' ends beside)
            near = {f, *self.nb[f]}
            near |= {j for c in list(near) for j in self.nb[c]}
            if not any(near.intersection(g) for gs in by.values() for g in gs):
                main = max((g for gs in by.values() for g in gs), key=len)
                groups = [main, [f]]
        return groups

    def left(self, owner: np.ndarray) -> int:
        """How many partitions, as a whole or in a zone, have necks."""
        return sum(
            len(self.parts(owner, k, z)) > 1
            for k in range(int(owner.max()) + 1)
            for z in [None, *sorted(set(self.zn[owner == k].tolist()))]
        )

    def narrow(self, owner: np.ndarray, cells: list[int], z: int | None) -> list[int]:
        """The cells whose walls with ``cells`` (and those between them) keep a point
        there from being clear: of other partitions, nearest first."""
        k = int(owner[cells[0]])
        pts = list(cells)
        for i, j in itertools.pairwise(cells):
            w = self.wall.get((min(i, j), max(i, j)))
            if w is not None:
                pts += [self.n + s * self.m + w for s in range(len(WALL))]
        out: dict[int, None] = {}
        for p in pts:
            for e in range(self.at[p], self.at[p + 1]):
                x, y = int(self.pa[e]), int(self.pb[e])
                if owner[x] == owner[y] or self.zn[x] != self.zn[y]:
                    continue  # (no border there, or a fold's: as it is)
                for c in (x, y):
                    if owner[c] != k and (z is None or self.zn[c] == z):
                        out[c] = None
        return list(out)

    def spares(self, owner: np.ndarray, i: int) -> bool:
        """Whether cell ``i`` can leave its partition without narrowing it: round it (three
        steps through walls, in its zone), its partition's cells with clear centres, joined
        through walls with a clear point, come apart into no more groups without it than
        with it."""
        if i not in self.local:
            z = self.zn[i]
            ring, seen = [i], {i}
            for _ in range(3):
                ring = [j for c in ring for j in self.nb[c] if j not in seen and self.zn[j] == z]
                seen.update(ring)
            cells = np.array(sorted(seen))
            ws = np.array(
                [w for c in cells for j in self.nb[c] if c < j and j in seen
                 for w in [self.wall[(c, j)]]],
                int,
            )  # fmt: skip
            pts = np.concatenate([cells, *(self.n + s * self.m + ws for s in range(len(WALL)))])
            ent = np.concatenate([np.arange(self.at[p], self.at[p + 1]) for p in pts])
            slot = np.repeat(np.arange(len(pts)), self.at[pts + 1] - self.at[pts])
            pa, pb = self.pa[ent], self.pb[ent]
            cross = self.zn[pa] != self.zn[pb]
            self.local[i] = (cells, ws, len(pts), slot, pa, pb, cross, ~self.always[pts])
        cells, ws, npts, slot, pa, pb, cross, free = self.local[i]
        m = owner[i]
        oa, ob = owner[pa], owner[pb]

        def groups(without: bool) -> int:
            if without:
                xa, xb = np.where(pa == i, -1, oa), np.where(pb == i, -1, ob)
            else:
                xa, xb = oa, ob
            bad = (xa != xb) | cross
            ok = free & (np.bincount(slot[bad], minlength=npts) == 0)
            mine = owner[cells] == m
            if without:
                mine &= cells != i
            node = set(cells[ok[: len(cells)] & mine].tolist())
            wok = ok[len(cells) :].reshape(len(WALL), len(ws)).any(0)
            adj: dict[int, list[int]] = {}
            for w in ws[wok].tolist():
                x, y = int(self.a[w]), int(self.b[w])
                if x in node and y in node:
                    adj.setdefault(x, []).append(y)
                    adj.setdefault(y, []).append(x)
            n = 0
            while node:
                todo = [node.pop()]
                n += 1
                while todo:
                    c = todo.pop()
                    for j in adj.get(c, ()):
                        if j in node:
                            node.discard(j)
                            todo.append(j)
            return n

        return groups(True) <= groups(False)


def _widened(
    owner: np.ndarray,
    necks: _Necks,
    nbrs: list[list[tuple[int, float]]],
    fixed: set[int],
) -> np.ndarray:
    """Each partition's necks widened where the cells beside allow, as a whole and zone by
    zone (a curve's regions are a partition's pieces in each zone, each laid out on its own,
    joined to the others across the folds): where its wide parts (``_Necks``) are several,
    it takes the cells on the cheapest way from its largest to the next (its own cells free,
    a neighbour's at a cost) and those of the neighbours' that keep the way narrow, each a
    neighbour can spare (not one it needs to hold together itself or to stay wide, nor a
    strip's end's), until its wide parts are one or none can be spared. (Of a piece through
    walls a port long, ``nbrs``, as ``_refine`` keeps partitions: a piece joined to the rest
    by a shorter wall only, it hands on whole.)"""
    owner = owner.copy()
    nb, zn = necks.nb, necks.zn
    for _ in range(3):
        moved = False
        for k in range(int(owner.max()) + 1):
            for z in [None, *sorted(set(zn[owner == k].tolist()))]:
                for _ in range(WIDEN):
                    parts = necks.parts(owner, k, z)
                    if len(parts) < 2:
                        break
                    path = _cheapest(owner, nb, zn, k, z, parts[0], set(parts[1]), fixed)
                    if path is None:
                        break
                    took = False
                    want = [c for c in path if owner[c] != k]
                    want += necks.narrow(owner, [c for c in path if owner[c] == k], z)
                    for j in dict.fromkeys(want):
                        if (
                            j not in fixed
                            and _connected(owner, nbrs, int(owner[j]), j)
                            and necks.spares(owner, j)
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
    held = {i for cs in sources for i in cs}  # (each source its own partition's)
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
                if d + c < dist[j] and j not in held:
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
