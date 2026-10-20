"""Partitions: a layer's mesh area split into parts of equal area, each laid out on its own
(``sfc.generate``) with its own traces from the connector.

Each partition has a *port*: its exit cell, a square a pair of trace lanes wide (``2 n``
pitches: its ``n`` traces out and back) in the row of them along the cable's junction, and
a *neck*: a corridor exactly that wide from its port on into the area, along which its
tongue runs (``sfc.generate(neck=...)``, its traces at the pitch) to where its curve opens.
The necks fan out from the ports (a star there): each straight in through its port and the
square in front of it (its *throat*), then off at its angle, the angles spread evenly round
the ports, the outer ones turning first (so none crosses another), each long enough that
the room between it and its neighbours is a few necks wide where it ends. The area is cut
into Voronoi cells about a neck wide (Lloyd's relaxation, each zone, i.e. panel, on its
own, so that no cell straddles a fold), the cells into sectors: each cell by the way its
cheapest path from the ports leaves them (crossing a fold costs more; every step's cost
varied by a smooth random field from the seed, so two layers' borders differ), cut by rays
from between the ports, each set for its sector's share of the area but kept between the
necks either side. Beyond the fan the borders are smoothed (a cell to the partition holding
most of its border, a neighbour across a fold counting little: borders keep to folds) and
the areas evened out, each partition kept of a piece.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np
import shapely
import shapely.affinity
from shapely.geometry import LineString, Polygon

from yanartas_pillowbox.mesh import MeshError

LLOYD = 3  # Lloyd iterations of the cells
FOLD = 4.0  # crossing a fold costs this many times as far
NOISE = 0.1  # each step's cost randomized by up to this share
FIELD = 0.5  # ... and varied by up to this share over the area (smoothly)
WAVES = 4  # ... (a sum of this many plane waves)
SLANT = 0.35  # the necks and borders leave the ports this far (radians) off the junction
MOUTH = 3.0  # cells within this many necks of a neck's end: its partition's (where its curve opens)
ROOM = 3.0  # a neck runs on until the room between it and the next is this many necks wide
BEND = 1.5  # ... its turn an arc this many necks in radius
TURN = 0.25  # ... each turning this many necks further in than the one outside it (and more)
ITERATIONS = 60  # rounds setting the weights for partitions of equal area
SMOOTH = 4  # passes handing cells to the partition that holds most of their border
ACROSS = 0.25  # ... a neighbour across a fold counting this much
BALANCE = 0.01  # partitions' areas within this share of each other
HOPS = 6  # a partition kept of a piece: looked for this many cells round a cell it gives up
THIN = 0.25  # parts of a partition thinner than twice this many necks: left out
ATTEMPTS = 6  # tries at an even split
UNEVEN = 0.03  # ... even: the partitions' areas within this share of each other


@dataclass(frozen=True)
class Partition:
    """One partition: what its mesh covers (its port, neck and part) and its neck (from the
    port's middle on to where its curve opens)."""

    area: Polygon
    port: Polygon
    neck: LineString


def _parts(g: shapely.Geometry) -> list[Polygon]:
    return [p for p in shapely.get_parts(g) if isinstance(p, Polygon) and p.area > 1e-9]


def cells(
    area: shapely.Geometry, zones: list[Polygon], size: float, rng: np.random.Generator
) -> tuple[list[Polygon], list[int]]:
    """The area as Voronoi cells about ``size`` across, each zone's on its own (Lloyd's
    relaxation): the cells and each one's zone."""
    out: list[Polygon] = []
    zone: list[int] = []
    pieces = [(zi, p) for zi, z in enumerate(zones) for p in _parts(z.intersection(area))]
    covered = shapely.union_all([z for z in zones]) if zones else Polygon()
    pieces += [(len(zones), p) for p in _parts(shapely.difference(area, covered))]
    for zi, piece in pieces:
        k = max(1, round(piece.area / (size * size * math.sqrt(3) / 2)))
        x0, y0, x1, y1 = piece.bounds
        shapely.prepare(piece)
        pts = np.zeros((0, 2))
        while len(pts) < k:
            q = rng.uniform((x0, y0), (x1, y1), (4 * k, 2))
            pts = np.vstack([pts, q[shapely.contains_xy(piece, q[:, 0], q[:, 1])]])
        pts = pts[:k]
        box = shapely.box(x0, y0, x1, y1).buffer(size)
        for it in range(LLOYD + 1):
            vor = shapely.voronoi_polygons(shapely.multipoints(pts), extend_to=box, ordered=True)
            got = shapely.intersection(np.asarray(shapely.get_parts(vor)), piece)
            if it == LLOYD:
                break
            pts = shapely.get_coordinates(shapely.centroid(got))
        for c in got:
            for p in _parts(c):
                out.append(p)
                zone.append(zi)
    return out, zone


def _graph(polys: list[Polygon], zone: list[int]) -> list[list[tuple[int, float]]]:
    """Each cell's neighbours (sharing a border), with the cost of the step to it."""
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
        if s > 1e-3:
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
    mouth_cells: list[list[int]],
    frozen: np.ndarray,
    pinned: np.ndarray,
) -> np.ndarray:
    """Each partition of a piece with its port (cut off pieces to the neighbour they
    border most), its borders smoothed (a cell to the partition holding most of its
    border, a neighbour across a fold counting little) and the areas evened out (cells
    handed on between neighbours, the most uneven pair first), each kept of a piece and at
    its port."""
    owner = owner.copy()
    count = len(target)
    fixed = pinned.copy()  # (the throats and necks' ends: never moved; the fan: smoothed only)
    for cs in mouth_cells:
        fixed[cs] = True
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
        owner[i] = q
        return True

    # (pieces cut off from the port: to the neighbour most beside; the neck's end joined
    # to the port by its corridor, though its cells beside it may not be the partition's)
    for k in range(count):
        seen = set(mouth_cells[k]) | set(np.nonzero(pinned & (owner == k))[0].tolist())
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
    fixed |= frozen  # (evening out: not in the fan)
    blocked: set[tuple[int, int]] = set()
    mean = float(area.mean())
    for _ in range(len(owner)):
        over = np.bincount(owner, area, count) - target
        edge = owner[src] != owner[dst]
        pairs = {(int(a), int(b)) for a, b in zip(owner[src[edge]], owner[dst[edge]], strict=True)}
        pairs = [pq for pq in pairs if pq not in blocked and over[pq[0]] - over[pq[1]] > 2 * mean]
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


def partition(
    area: shapely.Geometry,
    zones: list[Polygon],
    ports: list[Polygon],
    inward: tuple[float, float],
    width: float,
    seed: int,
    margin: float = 0.0,
) -> list[Partition]:
    """``area`` (less the ports) split into one partition per port (in their order along
    the junction; ``inward`` the way from the junction into the area), of equal area, each
    reaching its port by its neck, ``width`` wide (a pair of trace lanes: the ports'
    width); each kept ``margin`` off the others (but its port and neck: their traces are
    laid at the pitch). A split that comes out uneven is tried again afresh."""
    rng = np.random.default_rng(seed)
    best, worst = None, math.inf
    for _ in range(ATTEMPTS):
        parts = _partition(area, zones, ports, inward, width, rng, margin)
        a = [p.area.area for p in parts]
        bad = (max(a) - min(a)) / max(a)
        for p in parts:
            corridor = _corridor(p.neck, width).intersection(area)
            if (
                p.port.difference(p.area).area > 1e-6
                or corridor.difference(p.area).area > 1e-3 * width * width
            ):
                bad = math.inf
        if bad < worst:
            best, worst = parts, bad
        if bad < UNEVEN:
            break
    if best is None or worst > 0.5:
        raise MeshError("could not split the mesh's area into partitions")
    return best


def _partition(
    area: shapely.Geometry,
    zones: list[Polygon],
    ports: list[Polygon],
    inward: tuple[float, float],
    width: float,
    rng: np.random.Generator,
    margin: float,
) -> list[Partition]:
    count = len(ports)
    inv = np.asarray(inward, float) / math.hypot(*inward)
    necks = _fan(ports, inv, width, area)
    corridors = [_corridor(n, width) for n in necks]
    # (each port's throat: the cell in front of it, as wide, its partition's for sure)
    throats = [
        shapely.affinity.translate(port, *(inv * _depth(port, inv))).intersection(area)
        for port in ports
    ]
    rest = shapely.difference(area, shapely.union_all([*ports, *throats]))
    polys, zone = cells(rest, zones, width, rng)
    if len(polys) < 4 * count:
        raise MeshError("no room for the mesh's partitions")
    for t in throats:
        polys.append(t)
        zone.append(
            next((zi for zi, z in enumerate(zones) if z.intersects(t.centroid)), len(zones))
        )
    mouth_cells = [[len(polys) - count + k] for k in range(count)]
    nbrs = _graph(polys, zone)
    arr = np.asarray(polys, dtype=object)
    cen = shapely.get_coordinates(shapely.centroid(arr))
    cell_area = shapely.area(arr)
    noise = 1.0 + NOISE * rng.random(len(polys))
    field = _field(cen, rng)
    cost = [
        [(j, step * noise[j] * (field[i] + field[j]) / 2) for j, step in v]
        for i, v in enumerate(nbrs)
    ]
    tips = [int(np.argmin(np.hypot(*(cen - np.asarray(n.coords)[-1]).T))) for n in necks]
    want = float(cell_area.sum() + sum(p.area for p in ports)) / count
    owner = _weighted(
        cost, cell_area, [[t] for t in tips], want - np.array([p.area for p in ports]), width
    )
    # The fan: each cell near the ports and necks its nearest neck's, each neck's end in
    # its own partition (where its curve opens); all kept so.
    pts = shapely.points(cen)
    near = np.array(
        [
            shapely.distance(shapely.union_all([p, c]), pts)
            for p, c in zip(ports, corridors, strict=True)
        ]
    )
    frozen = near.min(0) < width
    owner[frozen] = np.argmin(near[:, frozen], axis=0)
    # (where the discs overlap, as of two necks ending side by side: the nearer end's)
    ends = np.array([shapely.distance(shapely.Point(n.coords[-1]), pts) for n in necks])
    pinned = ends.min(0) < MOUTH * width
    owner[pinned] = np.argmin(ends[:, pinned], axis=0)
    frozen |= pinned
    for k, cs in enumerate(mouth_cells):
        owner[cs] = k
    # Evened out, and again for what the necks add and take.
    target = np.full(count, float(cell_area.sum() + sum(p.area for p in ports)) / count)
    extra = np.zeros(count)
    # (and the cells handed past a narrow channel kept where they went)
    for _ in range(3):
        owner = _refine(owner, nbrs, zone, cell_area, target - extra, mouth_cells, frozen, pinned)
        out, handed = _areas(owner, arr, area, ports, corridors, margin, width)
        for g, k in handed:
            went = ~frozen & (owner != k) & shapely.contains(g, pts)
            owner[went] = k
            frozen |= went
        for k in range(count):
            extra[k] = out[k].area - cell_area[owner == k].sum()
    return [Partition(_one(out[k], ports[k]), ports[k], necks[k]) for k in range(count)]


def _fan(
    ports: list[Polygon], inward: np.ndarray, width: float, area: shapely.Geometry
) -> list[LineString]:
    """Each port's neck: from its middle straight in through its throat (and further, the
    more ports lie outside it on its side), then off at its angle (spread evenly round
    the ports, ``SLANT`` off the junction at most), on until the room between it and its
    neighbours is ``ROOM`` necks wide (shortened to stay in the area)."""
    count = len(ports)
    along = np.array([inward[1], -inward[0]])
    pc = shapely.get_coordinates(shapely.centroid(np.asarray(ports, dtype=object)))
    order = list(np.argsort(pc @ along))
    top = math.pi / 2 - SLANT
    share = 2 * top / count
    angle = {k: -top + (r + 0.5) * share for r, k in enumerate(order)}
    # (straight in: through the throat, and the turn's arc only beyond it; then a turn
    # further in each port in from the outside)
    radius = BEND * width
    head = {}
    for side in (order, order[::-1]):
        h = 2 * width
        for k in side[: (count + 1) // 2]:
            head[k] = max(head.get(k, 0.0), h + radius * math.tan(abs(angle[k]) / 2))
            h = head[k] + width * (TURN + math.tan(abs(angle[k]) / 2))
    reach = max(ROOM * width / max(share, 1e-6), 2 * width) + width
    shapely.prepare(area)
    inner = area.buffer(-width / 2)
    out = []
    for k in range(count):
        foot = pc[k]  # (the port's middle)
        bend = foot + inward * (head[k] - width / 2)
        way = inward * math.cos(angle[k]) + along * math.sin(angle[k])
        line = _rounded(foot, bend, bend + way * reach, radius)
        # (it ends where it would come within half a neck of the area's edge)
        inside = shapely.intersection(line, inner)
        piece = next(
            (g for g in shapely.get_parts(inside) if g.distance(shapely.Point(foot)) < 1e-6),
            None,
        )
        if piece is not None and piece.length < line.length - 1e-9:
            line = piece
        out.append(line)
    return out


def _rounded(a: np.ndarray, b: np.ndarray, c: np.ndarray, radius: float) -> LineString:
    """The path a - b - c with its corner at b an arc of ``radius``."""
    u, v = (b - a) / np.hypot(*(b - a)), (c - b) / np.hypot(*(c - b))
    turn = math.atan2(u[0] * v[1] - u[1] * v[0], u @ v)
    if abs(turn) < 1e-6:
        return LineString([a, c])
    t = radius * math.tan(abs(turn) / 2)
    start = b - u * t
    normal = np.array([-u[1], u[0]]) * math.copysign(1.0, turn)
    centre = start + normal * radius
    steps = max(2, math.ceil(abs(turn) / 0.15))
    arc = [
        centre - normal * radius * math.cos(f * turn) + u * radius * math.sin(abs(f * turn))
        for f in np.linspace(0, 1, steps + 1)
    ]
    return LineString([a, *arc, c])


def _corridor(neck: LineString, width: float) -> shapely.Geometry:
    return neck.buffer(width / 2, cap_style="flat", join_style="round")


def _field(cen: np.ndarray, rng: np.random.Generator) -> np.ndarray:
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
    width: float,
) -> np.ndarray:
    """Each cell to the source its cheapest path starts from, each source's start weighted
    (an additively weighted Voronoi diagram over the cells, from the necks' ends: far
    enough apart for the weights to tell): each partition the tree of its source's paths,
    so of a piece and round its neck's end; the weights set so that each gets about
    ``want`` of the area."""
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
    best[best < 0] = 0
    return best


def _areas(
    owner: np.ndarray,
    arr: np.ndarray,
    area: shapely.Geometry,
    ports: list[Polygon],
    corridors: list[shapely.Geometry],
    margin: float,
    width: float,
) -> tuple[list[Polygon], list[tuple[Polygon, int]]]:
    """Each port's partition: the port, its cells, its neck's corridor, the others'
    corridors and ports kept out; pieces so cut off from their port handed to a
    neighbour, and those past a narrow channel (these also returned, with whom to);
    each but its port and corridor ``margin`` off the others."""
    count = len(ports)
    out = []
    for k in range(count):
        mine = owner == k
        cells_ = shapely.union_all(arr[mine]) if mine.any() else Polygon()
        whole = shapely.union_all([cells_, ports[k], corridors[k]]).intersection(area)
        others = [g for m in range(count) if m != k for g in (corridors[m], ports[m])]
        out.append(shapely.difference(whole, shapely.union_all(others)))
    out = _reattach(out, ports, corridors)
    own = [shapely.union_all([ports[k], corridors[k]]) for k in range(count)]
    out, handed = _narrows(out, ports, corridors, own, width)
    if margin > 0:  # (each but its port and corridor kept off the others)
        out = [
            shapely.difference(
                g, shapely.difference(
                    shapely.union_all([h for m, h in enumerate(out) if m != k]).buffer(margin),
                    own[k],
                ),
            )
            for k, g in enumerate(out)
        ]  # fmt: skip
    # (parts too thin for a curve, as the wedges between two necks fanning apart, or a
    # channel the margin narrowed: left out)
    thin = THIN * width
    out = [
        _one(shapely.union_all([
            shapely.difference(g, own[k]).buffer(-thin).buffer(thin).intersection(g), own[k]
        ]).intersection(g), ports[k])
        for k, g in enumerate(out)
    ]  # fmt: skip
    return out, handed


def _narrows(
    out: list, ports: list[Polygon], corridors: list, own: list, width: float
) -> tuple[list, list[tuple[Polygon, int]]]:
    """What lies past a channel narrower than a curve's run in and out (a neck wide) to the
    neighbour whose part (not its corridor) it borders the most: its curve would squeeze
    through (as between a neck's end and the next neck), or the part, of a piece and
    fitting, given to the partition it bulges out of. Crumbs (at corners) stay."""
    out, handed = list(out), []
    for k in range(len(out)):
        body = shapely.difference(out[k], own[k])
        opened = body.buffer(-width / 2).buffer(width / 2).intersection(body)
        mouth = own[k].buffer(width / 8)
        main = shapely.union_all(
            [own[k], *(g for g in _parts(opened) if g.intersects(mouth))]
        ).buffer(width / 8).intersection(out[k])
        for g in _parts(shapely.difference(out[k], main)):
            if not width * width <= g.area < body.area / 2:
                continue
            best, share = None, 0.0
            for m in range(len(out)):
                if m != k:
                    s = g.boundary.intersection(
                        shapely.difference(out[m], corridors[m]).buffer(1e-6)
                    ).length
                    if s > share:
                        best, share = m, s
            if best is not None and share > width:
                out[best] = shapely.union_all([out[best], g])
                out[k] = shapely.difference(out[k], g)
                handed.append((g, best))
    return out, handed


def _depth(port: Polygon, inward: np.ndarray) -> float:
    """How deep the port runs in."""
    d = shapely.get_coordinates(port) @ inward
    return float(d.max() - d.min())


def _reattach(out: list, ports: list[Polygon], corridors: list) -> list:
    """Pieces of a partition cut off from its port (by another's corridor) to a neighbour
    whose part (not its corridor) they touch the most."""
    out = list(out)
    count = len(out)
    for k in range(count):
        pieces = _parts(out[k])
        if len(pieces) < 2:
            continue
        keep = max(pieces, key=lambda g: (g.intersects(ports[k].buffer(1e-6)), g.area))
        for g in pieces:
            if g is keep:
                continue
            best, share = None, 0.0
            for m in range(count):
                if m == k:
                    continue
                body = shapely.difference(out[m], corridors[m])
                s = g.boundary.intersection(body.buffer(1e-6)).length
                if s > share:
                    best, share = m, s
            if best is not None:
                out[best] = shapely.union_all([out[best], g])
                out[k] = shapely.difference(out[k], g)
    return out


def _one(g: shapely.Geometry, port: Polygon) -> Polygon:
    """The piece reaching the port (the rest, if any, unreachable: dropped)."""
    pieces = _parts(g)
    return max(pieces, key=lambda q: (q.intersects(port.buffer(1e-6)), q.area))
