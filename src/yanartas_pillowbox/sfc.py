"""Security mesh layout from a closed space-filling curve, after

    A. Bedel, Y. Coudert-Osmont, J. Martínez, R. I. Nishat, S. Whitesides, S. Lefebvre:
    "Closed space-filling curves with controlled orientation for 3D printing",
    Computer Graphics Forum 41(2), 2022, pp. 473-492, doi:10.1111/cgf.14488
    (reference code: https://github.com/mfx-inria/controllable-space-filling-curve, MIT).

The paper fills a polygon with one closed curve at an even spacing. Here that curve is the
mesh's centre line: its ``n`` traces are offsets of it, each a closed loop opened where the
curve runs out through the exit cell. The curve's spacing is ``n`` pitches at the least, so
the traces of neighbouring runs keep a pitch apart; where it is wider, the traces spread out
to share it evenly (the paper's per-segment area), so no gap opens wider than the spacing's
excess.

The steps follow the paper:

1. *Segments.* The area is split into the given zones (the folding pattern's panels: the
   paper's material zones), each zone's part into its pieces.
2. *Graph* (section 3.2). Seeds on a triangular grid, jittered, relaxed by Lloyd iterations
   into a centroidal Voronoi tessellation of each segment (shrunk by half a spacing); the
   cells' edges, clipped by the segment, form a planar graph whose vertices have degree three.
3. *Initial cycles* (3.3.1). A perfect matching of the graph (Edmonds); the edges it leaves
   out cover every vertex with disjoint cycles.
4. *Refinement and one cycle* (3.3.2). A vertex at each cell's centre, joined to the cell's
   corners; each centre is threaded into a cycle edge of its cell, the cycles are joined by
   split-and-reconnect moves and, failing those, doubled edges.
5. *Zoning.* The paper's zoning objective counts the curve's crossings of zone borders; here
   each segment's cycle is complete before the segments are joined, along a spanning tree,
   each join one split-and-reconnect across the shared border: two crossings per join, the
   least a closed curve through all segments can have. (The paper's stochastic optimizer,
   3.3.3, then has nothing left to improve: no alignment or orientation objective is set.)
6. *Geometry* (3.4). The curve is smoothed and relaxed towards an even spacing within its
   zone (the per-zone CVT objective: zone borders and the area's edge stand as mirrors).
7. *Room between the runs* (not in the paper, whose curve is a line of no width). Each run
   here carries a ribbon of all the traces, so where two runs part, the room between them
   grows up to a ribbon's width before another run fits: islands. The curve is grown into
   that room (as by differential growth: nearby runs repel, bends bulge where there is
   room), its tight bends rounded without pulling them back, and the traces spread to
   share what is left, in bends only as far as keeps neighbouring traces' skew down.

Steps 2 and 6 differ in their means: the Voronoi diagram is of points (no orientation field,
so no needles), and the geometry is relaxed by moving each vertex to the middle between its
neighbours across the curve (the CVT gradient across a run; a step per iteration, with a
Laplacian smoothing) instead of an L-BFGS solve.
"""

from __future__ import annotations

import itertools
import math
import random
from collections import defaultdict, deque
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import LineString, MultiPoint, Polygon

from yanartas_pillowbox.mesh import (
    DOWN,
    LEFT,
    UP,
    Grid,
    Mesh,
    MeshError,
    Point,
    Rays,
    resample,
)

SPACING = 1.0  # the curve's target spacing, in multiples of its least (n pitches)
SEED_SPACING = 1.4  # the CVT seeds' spacing, in target spacings (the cycle comes out sparser)
LLOYD = 6  # Lloyd iterations of the seeds
LLOYD_CURVE = 20  # CVT steps of the curve
SPREAD = 1.3  # the traces spread over at most this many target spacings
SMOOTH = 10  # the pitch of the traces smoothed over this many vertices either way
GAIN = 3.0  # the Laplacian weight per relative excess length
REPAIR = 100  # steps pushing runs apart (at most)
WINDOW = 1.5  # parts of the curve nearer than this many least spacings along it: one run
FINE = 4  # the traces offset from the curve split this many times finer
RAMP = 3  # ... ramped in over this many vertices off the tongue
MARGIN = 0.02  # ... at a pitch this much above the least (but at the exit)
SIMPLIFY = 0.002  # the traces simplified within this (mm; well within the margin)
INSIDE = 0.9  # traces inside a bend keep within this share of its radius
PUSH_MARGIN = 1.04  # runs closer than this many times their least spacing: pushed apart
BEND_SLACK = 0.85  # bends this much tighter than the tightest: smoothed (U-turns sit at it)
GROW = 150  # steps growing the curve into the room left between its runs (at most)
REACH = 1.06  # ... runs nearer than this many least spacings repel each other
GROW_RATE = 0.5  # ... the share of the room a bend bulges into per step
HARD = 10  # repair steps before bends still too sharp are smoothed the hard way
STALL = 10  # ... until it has grown less than 0.2 % over this many steps
STRAIGHT = 0.1  # bends gentler than this many least spacings' curvature: straight (skew)
SETTLE = 0  # steps settling each trace into the middle of the room either side of it
SETTLE_RATE = 0.5  # ... the share of the way there a step goes
SETTLE_REACH = 3.0  # ... copper looked for this many pitches out (beyond: a hole, moved into)
SETTLE_PIN = 1.5  # ... bends tighter than this many pitches' radius do not move inwards
SETTLE_SKEW = math.inf  # ... neighbouring traces kept within this many pitches of length (TODO)
ATTEMPTS = 8  # tries with fresh seeds when a graph comes out degenerate


class _Retry(Exception):
    """This graph cannot carry a cycle (a degenerate vertex): seed again."""


# ----------------------------------------------------------------------------- frame
class _Frame:
    """A frame in which the exit cell's open side is its top (-y) side: the given side
    turned or mirrored there."""

    def __init__(self, side: int) -> None:
        self.side = side

    def fwd(self, xy: np.ndarray) -> np.ndarray:
        x, y = xy[:, 0], xy[:, 1]
        if self.side == UP:
            return np.stack([x, y], 1)
        if self.side == DOWN:
            return np.stack([x, -y], 1)
        if self.side == LEFT:
            return np.stack([y, x], 1)
        return np.stack([y, -x], 1)  # RIGHT

    def inv(self, xy: np.ndarray) -> np.ndarray:
        x, y = xy[:, 0], xy[:, 1]
        if self.side == UP:
            return np.stack([x, y], 1)
        if self.side == DOWN:
            return np.stack([x, -y], 1)
        if self.side == LEFT:
            return np.stack([y, x], 1)
        return np.stack([-y, x], 1)

    def geom(self, g: shapely.Geometry) -> shapely.Geometry:
        return shapely.transform(g, self.fwd)


# ----------------------------------------------------------------------------- segments
@dataclass
class _Segment:
    region: int  # index of its region: one zone's piece of the area
    domain: Polygon  # where its graph lies: the region, shrunk by half a spacing


def _polygons(g: shapely.Geometry) -> list[Polygon]:
    return [p for p in shapely.get_parts(g) if isinstance(p, Polygon) and not p.is_empty]


def _regions(area: shapely.Geometry, zones: list[Polygon], least: float) -> list[Polygon]:
    """The area cut into the zones' pieces (and what no zone covers), pieces too small to
    take a curve left out."""
    out: list[Polygon] = []
    rest = area
    for z in zones:
        out += _polygons(shapely.intersection(area, z))
        rest = shapely.difference(rest, z)
    out += _polygons(rest)
    return [r for r in out if r.area >= least]


# ----------------------------------------------------------------------------- graph
class _Graph:
    """The curve's graph: vertices, edges (adjacency sets), the cells (faces) and the cycle
    links (each covered vertex has two)."""

    def __init__(self) -> None:
        self.pts: list[Point] = []
        self.adj: list[set[int]] = []
        self.seg: list[int] = []
        self.nbr: list[list[int]] = []
        self.faces: list[tuple[list[int], Polygon, int]] = []
        self._index: dict[tuple[int, int], int] = {}
        self.fixed: set[tuple[int, int]] = set()  # cycle edges no move may take

    def vertex(self, p: Point, seg: int, q: float = 1e-6) -> int:
        """The vertex at ``p`` (within ``q``), added if new."""
        kx, ky = round(p[0] / q), round(p[1] / q)
        for dx in (0, -1, 1):
            for dy in (0, -1, 1):
                i = self._index.get((kx + dx, ky + dy))
                if i is not None:
                    return i
        return self.add(p, seg, (kx, ky))

    def add(self, p: Point, seg: int, key: tuple[int, int] | None = None) -> int:
        i = len(self.pts)
        self.pts.append((float(p[0]), float(p[1])))
        self.adj.append(set())
        self.seg.append(seg)
        self.nbr.append([])
        if key is not None:
            self._index[key] = i
        return i

    def link(self, a: int, b: int) -> None:
        self.nbr[a].append(b)
        self.nbr[b].append(a)

    def unlink(self, a: int, b: int) -> None:
        self.nbr[a].remove(b)
        self.nbr[b].remove(a)


def _seeds(domain: Polygon, d: float, rng: random.Random) -> np.ndarray:
    """Seeds on a triangular grid of side ``d``, jittered by up to ``d / 20`` (section 3.2)."""
    x0, y0, x1, y1 = domain.bounds
    h = d * math.sqrt(0.75)
    pts = []
    for j in range(int((y1 - y0) / h) + 2):
        for i in range(int((x1 - x0) / d) + 2):
            r, a = d / 20 * math.sqrt(rng.random()), 2 * math.pi * rng.random()
            pts.append(
                (x0 + (i + 0.5 * (j % 2)) * d + r * math.cos(a), y0 + j * h + r * math.sin(a))
            )
    pts = np.array(pts)
    return pts[shapely.contains_xy(domain, pts[:, 0], pts[:, 1])]


def _cells(
    domain: Polygon, d: float, rng: random.Random, pin: Point | None = None
) -> list[Polygon]:
    """A centroidal Voronoi tessellation of the domain (Lloyd iterations), cells clipped by
    it, cells holding a hole of the domain split through it. A seed at ``pin`` stays there
    (the others keep their distance from it)."""
    seeds = _seeds(domain, d, rng)
    if pin is not None:
        seeds = np.vstack([seeds[np.hypot(*(seeds - pin).T) > 0.75 * d], [pin]])
    if len(seeds) < 2:
        return _split_holes(domain)
    shapely.prepare(domain)
    frame = shapely.box(*domain.bounds).buffer(2 * d)
    for it in range(LLOYD + 1):
        vor = shapely.voronoi_polygons(MultiPoint(seeds), extend_to=frame)
        cells = shapely.intersection(shapely.get_parts(vor), domain)
        cells = cells[~shapely.is_empty(cells)]
        if it == LLOYD:
            break
        parts = [max(_polygons(c), key=lambda p: p.area) for c in cells]
        cen = shapely.centroid(parts)
        inside = shapely.contains(domain, cen)
        cen = np.where(inside, cen, shapely.point_on_surface(parts))
        seeds = shapely.get_coordinates(cen)
        if pin is not None:
            seeds[np.argmin(np.hypot(*(seeds - pin).T))] = pin
    out: list[Polygon] = []
    for c in cells:
        for p in _polygons(c):
            if p.area > 1e-9:
                out += _split_holes(p)
    return out


def _split_holes(p: Polygon) -> list[Polygon]:
    """The polygon cut so that no piece has a hole (a vertical cut through each)."""
    if not p.interiors:
        return [p]
    cx = shapely.centroid(Polygon(p.interiors[0])).x
    x0, y0, x1, y1 = p.bounds
    out = []
    for half in (shapely.box(x0 - 1, y0 - 1, cx, y1 + 1), shapely.box(cx, y0 - 1, x1 + 1, y1 + 1)):
        for q in _polygons(shapely.intersection(p, half)):
            out += _split_holes(q)
    return out


def _build(g: _Graph, cells: list[Polygon], seg: int) -> None:
    """Add the cells' edges and corners to the graph."""
    for cell in cells:
        ids: list[int] = []
        for p in cell.exterior.coords[:-1]:
            i = g.vertex(p, seg)
            if not ids or ids[-1] != i:
                ids.append(i)
        while len(ids) > 1 and ids[0] == ids[-1]:
            ids.pop()
        if len(ids) < 3:
            continue
        for a, b in zip(ids, ids[1:] + ids[:1], strict=True):
            g.adj[a].add(b)
            g.adj[b].add(a)
        g.faces.append((ids, cell, seg))


def _tongue(g: _Graph, segments: list[_Segment], mouth: tuple[Point, Point]) -> tuple[int, int]:
    """The exit's tongue in the graph: its two ends, on one edge along the rim of the segment
    nearest them (which they split), the edge between them its stand-in and one the cycle
    must take. Both ends have no other edges, so the cycle runs on from each along the rim,
    away from the other."""
    seg = min(
        range(len(segments)), key=lambda i: segments[i].domain.distance(shapely.Point(mouth[0]))
    )
    count: dict[tuple[int, int], int] = defaultdict(int)
    for ids, _, si in g.faces:
        if si == seg:
            for x, y in zip(ids, ids[1:] + ids[:1], strict=True):
                count[min(x, y), max(x, y)] += 1
    rim = [e for e, k in count.items() if k == 1]  # (the segment's edge)
    lines = [LineString([g.pts[x], g.pts[y]]) for x, y in rim]
    near = [
        min(range(len(rim)), key=lambda i: lines[i].distance(shapely.Point(pt))) for pt in mouth
    ]
    if near[0] != near[1] or lines[near[0]].distance(shapely.Point(mouth[0])) > 1e-6:
        raise _Retry  # (a cell wall between the ends, or the mouth off the rim)
    x, y = rim[near[0]]
    line = lines[near[0]]
    t = [line.project(shapely.Point(pt)) for pt in mouth]
    if not min(t) > 1e-6 and max(t) < line.length - 1e-6:
        raise _Retry
    if t[0] > t[1]:  # (x on the side of the first end)
        x, y = y, x
    a, b = (g.add((line.interpolate(ti).x, line.interpolate(ti).y), seg) for ti in t)
    g.adj[x].discard(y)
    g.adj[y].discard(x)
    for u, v in ((x, a), (a, b), (b, y)):
        g.adj[u].add(v)
        g.adj[v].add(u)
    for ids, _, _ in g.faces:  # (the cell along that edge: through the new vertices)
        for j in range(len(ids)):
            if {ids[j], ids[(j + 1) % len(ids)]} == {x, y}:
                ids[j + 1 : j + 1] = [a, b] if ids[j] == x else [b, a]
                break
    g.fixed.add((min(a, b), max(a, b)))
    return a, b


# ----------------------------------------------------------------------------- matching
def _matching(n: int, nbrs: list[list[int]], rng: random.Random) -> list[int]:
    """A maximum matching (Edmonds' blossom algorithm), greedy start: ``mate`` per vertex."""
    mate = [-1] * n
    order = list(range(n))
    rng.shuffle(order)
    for v in order:
        if mate[v] < 0:
            for u in nbrs[v]:
                if mate[u] < 0 and u != v:
                    mate[v], mate[u] = u, v
                    break
    base = list(range(n))
    parent = [-1] * n
    used = [False] * n
    blossom = [False] * n

    def lca(a: int, b: int) -> int:
        seen = set()
        while True:
            a = base[a]
            seen.add(a)
            if mate[a] < 0:
                break
            a = parent[mate[a]]
        while True:
            b = base[b]
            if b in seen:
                return b
            b = parent[mate[b]]

    def mark(v: int, b: int, child: int) -> None:
        while base[v] != b:
            blossom[base[v]] = blossom[base[mate[v]]] = True
            parent[v] = child
            child = mate[v]
            v = parent[mate[v]]

    def search(root: int) -> tuple[int, list[int]]:
        touched = [root]
        used[root] = True
        queue = deque([root])
        while queue:
            v = queue.popleft()
            for u in nbrs[v]:
                if base[v] == base[u] or mate[v] == u or u == v:
                    continue
                if u == root or (mate[u] >= 0 and parent[mate[u]] >= 0):
                    b = lca(v, u)
                    mark(v, b, u)
                    mark(u, b, v)
                    for i in touched:
                        if blossom[base[i]]:
                            base[i] = b
                            if not used[i]:
                                used[i] = True
                                queue.append(i)
                    for i in touched:
                        blossom[i] = False
                elif parent[u] < 0:
                    parent[u] = v
                    touched.append(u)
                    if mate[u] < 0:
                        return u, touched
                    used[mate[u]] = True
                    touched.append(mate[u])
                    queue.append(mate[u])
        return -1, touched

    for root in order:
        if mate[root] >= 0:
            continue
        end, touched = search(root)
        v = end
        while v >= 0:
            pv = parent[v]
            nxt = mate[pv]
            mate[v], mate[pv] = pv, v
            v = nxt
        for i in touched:
            used[i], parent[i], base[i] = False, -1, i
    return mate


def _two_factor(g: _Graph, rng: random.Random) -> None:
    """Cycle links covering every vertex of degree three: the edges a perfect matching leaves
    out (section 3.3.1). Chains of degree-two vertices act as one edge; a matched chain's
    inner vertices stay off the cycle."""
    deg = [len(a) for a in g.adj]
    if any(k > 3 for k in deg):
        raise _Retry
    cubic = [i for i, k in enumerate(deg) if k == 3]
    index = {v: j for j, v in enumerate(cubic)}
    chains: list[list[int]] = []
    seen: set[tuple[int, int]] = set()
    for u in cubic:
        for w in g.adj[u]:
            if (u, w) in seen:
                continue
            chain, prev, here = [u, w], u, w
            while deg[here] == 2:
                prev, here = here, next(x for x in g.adj[here] if x != prev)
                chain.append(here)
            seen.add((u, w))
            seen.add((here, prev))
            chains.append(chain)
    nbrs: list[list[int]] = [[] for _ in cubic]
    held = [
        any((min(x, y), max(x, y)) in g.fixed for x, y in itertools.pairwise(c)) for c in chains
    ]
    for c, keep in zip(chains, held, strict=True):
        if c[0] != c[-1] and not keep:
            nbrs[index[c[0]]].append(index[c[-1]])
            nbrs[index[c[-1]]].append(index[c[0]])
    mate = _matching(len(cubic), nbrs, rng)
    if any(m < 0 for m in mate):
        raise _Retry
    matched: set[tuple[int, int]] = set()
    for c, keep in zip(chains, held, strict=True):
        a, b = c[0], c[-1]
        key = (min(a, b), max(a, b))
        if a != b and not keep and cubic[mate[index[a]]] == b and key not in matched:
            matched.add(key)
            continue
        for x, y in itertools.pairwise(c):
            g.link(x, y)
    # (rings of degree-two vertices only: a cycle by themselves)
    for v, k in enumerate(deg):
        if k == 2 and not g.nbr[v] and not any(deg[u] == 3 for u in _ring(g, v)):
            ring = _ring(g, v)
            for x, y in zip(ring, ring[1:] + ring[:1], strict=True):
                g.link(x, y)
    for u in cubic:
        if len(g.nbr[u]) != 2:
            raise _Retry


def _ring(g: _Graph, v: int) -> list[int]:
    out, prev, here = [v], -1, v
    while True:
        nxt = next((x for x in g.adj[here] if x != prev), None)
        if nxt is None or nxt == v or len(g.adj[here]) != 2:
            return out
        out.append(nxt)
        prev, here = here, nxt


# ----------------------------------------------------------------------------- refinement
def _centres(g: _Graph) -> None:
    """A vertex at each cell's centre, joined to the corners it sees; each threaded into one
    cycle edge along its cell (section 3.3.2: a bipartite matching of cells to edges)."""
    polys = [f[1] for f in g.faces]
    cen = shapely.centroid(polys)
    ok = shapely.contains(polys, cen)
    spokes: list[tuple[int, int]] = []
    lines = []
    for fi, (ids, _, _) in enumerate(g.faces):
        if not ok[fi]:
            continue
        c = cen[fi]
        for v in ids:
            spokes.append((fi, v))
            lines.append(LineString([(c.x, c.y), g.pts[v]]))
    if not spokes:
        return
    grown = shapely.buffer(polys, 1e-7)
    good = shapely.covers(np.array([grown[f] for f, _ in spokes]), lines)
    sees: dict[int, set[int]] = defaultdict(set)
    for (fi, v), k in zip(spokes, good, strict=True):
        if k:
            sees[fi].add(v)
    cands: dict[int, list[tuple[int, int]]] = {}
    for fi, vs in sees.items():
        if sum(1 for v in vs if g.nbr[v]) < 3:
            continue
        ids = g.faces[fi][0]
        es = [
            (min(a, b), max(a, b))
            for a, b in zip(ids, ids[1:] + ids[:1], strict=True)
            if a in vs and b in vs and b in g.nbr[a] and (min(a, b), max(a, b)) not in g.fixed
        ]
        if es:
            cands[fi] = es
    owner: dict[tuple[int, int], int] = {}
    chosen: dict[int, tuple[int, int]] = {}
    for fi in cands:  # augmenting paths (BFS) over cells and their edges
        prev: dict[int, tuple[int, tuple[int, int]] | None] = {fi: None}
        queue, end = deque([fi]), None
        while queue and end is None:
            f = queue.popleft()
            for e in cands[f]:
                o = owner.get(e)
                if o is None:
                    end = (f, e)
                    break
                if o not in prev:
                    prev[o] = (f, e)
                    queue.append(o)
        if end is None:
            continue
        f, e = end
        while True:
            owner[e] = f
            chosen[f] = e
            step = prev[f]
            if step is None:
                break
            f, e = step
    for fi, (a, b) in chosen.items():
        c = g.add((cen[fi].x, cen[fi].y), g.faces[fi][2])
        g.unlink(a, b)
        g.link(a, c)
        g.link(c, b)
        for v in sees[fi]:
            g.adj[c].add(v)
            g.adj[v].add(c)


class _Union:
    def __init__(self, n: int) -> None:
        self.p = list(range(n))

    def find(self, a: int) -> int:
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def join(self, a: int, b: int) -> bool:
        a, b = self.find(a), self.find(b)
        if a == b:
            return False
        self.p[b] = a
        return True

    def grow(self, n: int) -> None:
        self.p += list(range(len(self.p), n))


def _cycle_union(g: _Graph) -> _Union:
    u = _Union(len(g.pts))
    for a, ns in enumerate(g.nbr):
        for b in ns:
            u.join(a, b)
    return u


def _merge(g: _Graph, u: _Union) -> None:
    """Join the cycles of each segment into one: split-and-reconnect where two cycle edges
    face each other across a quad of graph edges, then doubled edges (section 3.3.2)."""
    changed = True
    while changed:
        changed = False
        for x1 in range(len(g.pts)):
            for x2 in list(g.nbr[x1]):
                if (min(x1, x2), max(x1, x2)) in g.fixed or x2 not in g.nbr[x1]:
                    continue
                for y1 in g.adj[x1]:
                    if not g.nbr[y1] or u.find(y1) == u.find(x1):
                        continue
                    y2 = next((y for y in g.nbr[y1] if y in g.adj[x2]), None)
                    if y2 is None or (min(y1, y2), max(y1, y2)) in g.fixed:
                        continue
                    g.unlink(x1, x2)
                    g.unlink(y1, y2)
                    g.link(x1, y1)
                    g.link(x2, y2)
                    u.join(x1, y1)
                    changed = True
                    break
    for x in range(len(g.pts)):  # what is left: double a graph edge between two cycles
        if not g.nbr[x]:
            continue
        for y in list(g.adj[x]):
            if g.nbr[y] and g.seg[y] == g.seg[x] and u.find(x) != u.find(y) and _double(g, x, y):
                u.grow(len(g.pts))
                u.join(x, y)
                u.join(x, len(g.pts) - 1)
                u.join(x, len(g.pts) - 2)


def _double(g: _Graph, u: int, v: int) -> bool:
    """Join the cycles through ``u`` and ``v`` by doubling the edge between them (paper
    figure 8): the copy runs from a point on one of ``u``'s cycle edges to one on ``v``'s,
    both on the same side of the edge, crossing nothing. False where there is no such side."""
    (ux, uy), (vx, vy) = g.pts[u], g.pts[v]

    def side(w: int) -> float:
        wx, wy = g.pts[w]
        return (vx - ux) * (wy - uy) - (vy - uy) * (wx - ux)

    for sign in (1.0, -1.0):
        qs = [
            w for w in g.nbr[u] if sign * side(w) > 1e-9 and (min(u, w), max(u, w)) not in g.fixed
        ]
        rs = [
            w for w in g.nbr[v] if sign * side(w) > 1e-9 and (min(v, w), max(v, w)) not in g.fixed
        ]
        if not qs or not rs:
            continue
        q, r = qs[0], rs[0]
        t = 0.25
        a = (ux + t * (g.pts[q][0] - ux), uy + t * (g.pts[q][1] - uy))
        b = (vx + t * (g.pts[r][0] - vx), vy + t * (g.pts[r][1] - vy))
        copy = LineString([a, b])
        around = {w for x in (u, v, q, r) for w in g.adj[x] | {x}}
        if any(
            copy.crosses(LineString([g.pts[x], g.pts[y]]))
            for x in around
            for y in g.nbr[x]
            if x < y
        ):
            continue
        u2, v2 = g.add(a, g.seg[u]), g.add(b, g.seg[v])
        g.unlink(u, q)
        g.unlink(v, r)
        g.link(u, v)
        g.link(u2, v2)
        g.link(u2, q)
        g.link(v2, r)
        return True
    return False


# ----------------------------------------------------------------------------- zoning
def _join_segments(
    g: _Graph, u: _Union, segments: list[_Segment], regions: list[Polygon], spacing: float
) -> None:
    """Join the segments' cycles along a spanning tree of the segments that share a border
    (longest borders first): each join one split-and-reconnect across the border."""
    tree = shapely.STRtree(regions)
    pairs = []
    a_idx, b_idx = tree.query(regions, predicate="intersects")
    for i, j in zip(a_idx, b_idx, strict=True):
        if i < j:
            border = shapely.line_merge(
                shapely.intersection(regions[i].boundary, regions[j].buffer(1e-6))
            )
            if border.length >= 2 * spacing:
                pairs.append((border.length, int(i), int(j), border))
    pairs.sort(key=lambda p: -p[0])
    by_region: dict[int, list[int]] = defaultdict(list)
    for v, s in enumerate(g.seg):
        if g.nbr[v]:
            by_region[segments[s].region].append(v)
    for _, ri, rj, border in pairs:
        for line in sorted(_lines(border), key=lambda ln: -ln.length):
            if line.length >= 2 * spacing and _connect(
                g, u, segments, by_region[ri], by_region[rj], line, spacing
            ):
                break


def _lines(g: shapely.Geometry) -> list[LineString]:
    return [p for p in shapely.get_parts(g) if isinstance(p, LineString) and p.length > 0]


def _connect(
    g: _Graph,
    u: _Union,
    segments: list[_Segment],
    va: list[int],
    vb: list[int],
    line: LineString,
    spacing: float,
) -> bool:
    """One split-and-reconnect across the border ``line`` between two cycle edges (of cycles
    not yet joined) facing each other across it, away from the border's ends (where other
    borders meet it): the shortest joins, nearest the border's middle. Edges along their
    segments' edges first, then any near the border; either way, the joins cross no edge of
    the curve (of any segment: near corners, a third may come close)."""
    end = min(2 * spacing, line.length / 6)
    cycle = [(a, b) for a in range(len(g.pts)) for b in g.nbr[a] if a < b]
    tree = shapely.STRtree(shapely.linestrings([[g.pts[a], g.pts[b]] for a, b in cycle]))
    for along, near, reach in ((True, 1.0, 2.0), (False, 1.8, 2.6)):
        edges = [
            _border_edges(g, segments, vs, line, near * spacing, end, along) for vs in (va, vb)
        ]
        cands = []
        mid = line.length / 2
        for a1, a2, s1, s2 in edges[0]:
            for b1, b2, t1, t2 in edges[1]:
                if u.find(a1) == u.find(b1) or min(s2, t2) - max(s1, t1) < 0.1 * spacing:
                    continue
                l1, l2 = math.dist(g.pts[a1], g.pts[b1]), math.dist(g.pts[a2], g.pts[b2])
                if max(l1, l2) <= reach * spacing:
                    cands.append((l1 + l2 + 0.05 * abs((s1 + s2) / 2 - mid), a1, a2, b1, b2))
        cands.sort()
        for _, a1, a2, b1, b2 in cands[:100]:
            ends = ((a1, b1), (a2, b2))
            joins = [LineString([g.pts[x], g.pts[y]]) for x, y in ends]
            if joins[0].intersects(joins[1]) or any(
                not set(e) & set(cycle[i])
                for e, j in zip(ends, joins, strict=True)
                for i in tree.query(j, predicate="intersects")
            ):
                continue
            g.unlink(a1, a2)
            g.unlink(b1, b2)
            g.link(a1, b1)
            g.link(a2, b2)
            u.join(a1, b1)
            return True
    return False


def _border_edges(
    g: _Graph,
    segments: list[_Segment],
    vs: list[int],
    line: LineString,
    near: float,
    end: float,
    along: bool,
) -> list[tuple[int, int, float, float]]:
    """The cycle edges among ``vs`` within ``near`` of ``line`` and ``end`` from its ends
    (``along``: only those along their segment's edge), each with its ends' places along
    the line, in order."""
    if not vs:
        return []
    p = np.array([g.pts[v] for v in vs])
    close = shapely.distance(line, shapely.points(p)) <= near
    keep = {v for v, k in zip(vs, close, strict=True) if k}
    out = []
    for a in keep:
        for b in g.nbr[a]:
            if a > b or b not in keep or (a, b) in g.fixed:
                continue
            (ax, ay), (bx, by) = g.pts[a], g.pts[b]
            if along and (
                g.seg[a] != g.seg[b]
                or segments[g.seg[a]].domain.boundary.distance(
                    shapely.Point((ax + bx) / 2, (ay + by) / 2)
                )
                > 1e-6
            ):
                continue
            sa, sb = line.project(shapely.Point(ax, ay)), line.project(shapely.Point(bx, by))
            if min(sa, sb) < end or max(sa, sb) > line.length - end:
                continue
            out.append((a, b, sa, sb) if sa <= sb else (b, a, sb, sa))
    return out


# ----------------------------------------------------------------------------- combinatorics
def _curve(
    area: shapely.Geometry,
    zones: list[Polygon],
    spacing: float,
    mouth: tuple[Point, Point],
    rng: random.Random,
) -> tuple[np.ndarray, list[Polygon], np.ndarray, int, int]:
    """The closed curve through the segments the exit's can reach: its vertices from the
    tongue's end at ``mouth[0]`` round to its other end (the tongue, out through the exit
    and back, closes it), the regions, each vertex's region, the cells and the regions
    left out."""
    regions = _regions(area, zones, 2 * spacing**2)
    segments = [
        _Segment(ri, d)
        for ri, r in enumerate(regions)
        for d in _polygons(r.buffer(-spacing / 2))
        if d.area >= spacing**2
    ]
    if not segments:
        raise MeshError("no room for the mesh")
    # (a seed pinned inside the mouth: no cell wall reaches the edge between its ends)
    d = SEED_SPACING * spacing
    at = shapely.Point(mouth[0])
    exit_seg = min(range(len(segments)), key=lambda i: segments[i].domain.distance(at))
    pin = ((mouth[0][0] + mouth[1][0]) / 2, (mouth[0][1] + mouth[1][1]) / 2 + d / 2)
    if not segments[exit_seg].domain.contains(shapely.Point(pin)):
        pin = None
    for _ in range(ATTEMPTS):
        g = _Graph()
        for si, s in enumerate(segments):
            _build(g, _cells(s.domain, d, rng, pin if si == exit_seg else None), si)
        try:
            ends = _tongue(g, segments, mouth)
            _two_factor(g, rng)
        except _Retry:
            continue
        break
    else:
        raise MeshError("could not build the curve's graph")
    cells = len(g.faces)
    _centres(g)
    u = _cycle_union(g)
    _merge(g, u)
    _join_segments(g, u, segments, regions, spacing)
    a, b = ends
    root = u.find(a)
    order = [b, a]  # walk from a away from b (the tongue between them)
    while True:
        nxt = next(x for x in g.nbr[order[-1]] if x != order[-2])
        if nxt == b:
            break
        order.append(nxt)
    order = [*order[1:], b]
    pts = np.array([g.pts[v] for v in order])
    seg = np.array([segments[g.seg[v]].region for v in order])
    left = {segments[g.seg[v]].region for v in range(len(g.pts)) if g.nbr[v]}
    left -= {segments[g.seg[v]].region for v in range(len(g.pts)) if g.nbr[v] and u.find(v) == root}
    return pts, regions, seg, cells, len(left)


# ----------------------------------------------------------------------------- geometry
def _even(p: np.ndarray, k: int, step: float, smooth: bool = False) -> np.ndarray:
    """The closed curve's first ``k`` vertices (an open polyline; the rest stay) resampled
    at an even step (``smooth``: along a spline through them, so as not to cut corners),
    unless that would make it cross itself (where it cuts a corner between runs close
    together): then only its long segments split."""
    if smooth:
        fine = _spline(p, 4)[: 4 * (k - 1) + 1]  # (the spline from the first to the k-th)
        free = resample(fine, step)
    else:
        free = resample(p[:k], step)
    q = np.vstack([free, p[k:]])
    i, _ = _crossing(q, np.arange(len(q)))
    return free if not len(i) else _split(p[:k], 1.5 * step)


def _split(p: np.ndarray, longest: float) -> np.ndarray:
    """The open polyline with its segments longer than ``longest`` split evenly (the
    vertices kept where they are)."""
    seg = np.hypot(*np.diff(p, axis=0).T)
    parts = np.maximum(1, np.ceil(seg / longest)).astype(int)
    if (parts == 1).all():
        return p
    t = np.concatenate([np.arange(m) / m for m in parts])
    i = np.repeat(np.arange(len(seg)), parts)
    return np.vstack([p[i] + (p[i + 1] - p[i]) * t[:, None], p[-1:]])


def _respace(p: np.ndarray, step: float) -> np.ndarray:
    """The open polyline at about ``step`` between vertices without moving any (so that,
    resampled step after step, it does not shrink): vertices closer to the next but one
    than ``step`` dropped (not two in a row; its ends kept), segments longer than one and a
    half split."""
    seg = np.hypot(*np.diff(p, axis=0).T)
    drop = np.zeros(len(p), bool)
    drop[1:-1] = seg[:-1] + seg[1:] < step
    drop[1:] &= ~drop[:-1]
    return _split(p[~drop], 1.5 * step)


def _spacing(
    p: np.ndarray, mirrors: tuple[np.ndarray, np.ndarray], reach: float, window: float
) -> tuple[np.ndarray, np.ndarray]:
    """For each vertex of the closed curve ``p``: the distance to its neighbour across the
    curve on its left and right (a mirror's at twice the distance to it), at most ``reach``.
    Parts of the curve within ``window`` along it do not count."""
    n = len(p)
    q = np.roll(p, -1, axis=0)
    t = q - np.roll(p, 1, axis=0)
    t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-12)[:, None]
    normal = np.stack([-t[:, 1], t[:, 0]], 1)
    arc = np.concatenate([[0.0], np.cumsum(np.hypot(*(q - p).T))])
    total, arc = arc[-1], arc[:-1]
    ma, mb = mirrors
    rays = Rays(np.vstack([p, ma]), np.vstack([q, mb]), reach)
    out = []
    for sign in (1.0, -1.0):
        ray, seg, hit = rays.cast(p, sign * normal)
        curve = seg < n
        gap = np.abs(arc[ray] - arc[np.where(curve, seg, 0)])
        near = curve & (np.minimum(gap, total - gap) < window)
        hit = np.where(curve, hit, 2 * hit)[~near]
        d = np.full(n, reach)
        np.minimum.at(d, ray[~near], hit)
        out.append(d)
    return out[0], out[1]


def _mirrors(regions: list[Polygon], step: float) -> tuple[np.ndarray, np.ndarray]:
    """The regions' borders (the area's edges and the zones' borders), in short pieces."""
    a, b = [], []
    for r in regions:
        for ring in (r.exterior, *r.interiors):
            c = resample(np.asarray(ring.coords), step)
            a.append(c[:-1])
            b.append(c[1:])
    return np.vstack(a), np.vstack(b)


def _samples(
    regions: list[Polygon], step: float, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Points on a square grid (randomly offset) over the regions, with their region."""
    pts, reg = [], []
    off = rng.random(2) * step
    for ri, r in enumerate(regions):
        x0, y0, x1, y1 = r.bounds
        xs = np.arange(x0 - off[0], x1 + step, step)
        ys = np.arange(y0 - off[1], y1 + step, step)
        gx, gy = np.meshgrid(xs, ys)
        gx, gy = gx.ravel(), gy.ravel()
        ok = shapely.contains_xy(r, gx, gy)
        pts.append(np.stack([gx[ok], gy[ok]], 1))
        reg.append(np.full(int(ok.sum()), ri))
    return np.vstack(pts), np.concatenate(reg)


def _region_of(regions: list[Polygon], p: np.ndarray) -> np.ndarray:
    out = np.full(len(p), -1)
    for ri, r in enumerate(regions):
        shapely.prepare(r)
        out[(out < 0) & shapely.contains_xy(r, p[:, 0], p[:, 1])] = ri
    return out


def _lloyd(
    p: np.ndarray, reg: np.ndarray, samples: np.ndarray, sreg: np.ndarray, spacing: float
) -> np.ndarray:
    """Each vertex's centroid of the area nearer to it than to any other vertex of the curve
    in its region (the per-zone CVT): the vertex itself where that area is empty."""
    grid = Grid(p, 0.75 * spacing)
    sums = np.zeros_like(p)
    count = np.zeros(len(p))
    chunk = 50_000
    for k in range(0, len(samples), chunk):
        q, qr = samples[k : k + chunk], sreg[k : k + chunk]
        near = grid.nearest(q, lambda qi, pi, qr=qr: reg[pi] == qr[qi])
        has = near >= 0
        np.add.at(sums, near[has], q[has])
        np.add.at(count, near[has], 1)
    out = p.copy()
    has = count > 0
    out[has] = sums[has] / count[has, None]
    return out


def _neighbours(
    p: np.ndarray, window: float, reach: float, side: int = 0, which: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """For each vertex of the closed curve ``p`` (or those ``which`` indexes): the nearest
    vertex of the curve more than ``window`` away along it (and within ``reach``; on its left
    for ``side`` 1, its right for -1, either for 0), and the distance to it (``reach`` and -1
    where there is none)."""
    q = np.roll(p, -1, axis=0)
    t = q - np.roll(p, 1, axis=0)
    normal = np.stack([-t[:, 1], t[:, 0]], 1)
    arc = np.concatenate([[0.0], np.cumsum(np.hypot(*(q - p).T))])
    total, arc = arc[-1], arc[:-1]
    grid = Grid(p, reach)

    def ok(qi: np.ndarray, pi: np.ndarray) -> np.ndarray:
        gap = np.abs(arc[qi] - arc[pi])
        far = np.minimum(gap, total - gap) > window
        if side:
            far &= side * np.sum((p[pi] - p[qi]) * normal[qi], axis=1) > 0
        return far

    which = np.arange(len(p)) if which is None else which
    near = np.full(len(which), -1)
    for k in range(0, len(which), 50_000):
        w = which[k : k + 50_000]
        near[k : k + 50_000] = grid.nearest(p[w], lambda qi, pi, w=w: ok(w[qi], pi))
    d = np.where(near >= 0, np.hypot(*(p[np.maximum(near, 0)] - p[which]).T), reach)
    return near, np.minimum(d, reach)


def _lap(p: np.ndarray) -> np.ndarray:
    return (np.roll(p, 1, axis=0) + np.roll(p, -1, axis=0)) / 2 - p


def _taubin(p: np.ndarray, k: int, passes: int = 2) -> np.ndarray:
    """Taubin smoothing (a shrinking step, then an inflating one) of the closed curve's
    first ``k`` vertices but the first and last: zigzags gone, the shape kept."""
    p = p.copy()
    for _ in range(passes):
        for f in (0.5, -0.53):
            d = f * _lap(p)
            p[1 : k - 1] += d[1 : k - 1]
    return p


def _relax(
    curve: np.ndarray,
    tongue: np.ndarray,
    area: shapely.Geometry,
    regions: list[Polygon],
    spacing: float,
    least: float,
    pitch: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, int]:
    """The curve, relaxed: ``curve`` is an open polyline from the tongue's left end round to
    its right end, the tongue closes it. Returned closed (the tongue last), with the number
    of vertices before the tongue's (the first and that last one are the tongue's ends).

    Each step moves the curve to its per-zone CVT centroids, smooths it (Taubin) and shrinks
    or inflates it (a Laplacian step, at the scale of a few vertices) to keep its length near
    the area over the spacing (the paper's length objective), resampling it after. Then,
    at a finer step, where two runs come closer than ``least`` (with a margin), or a run
    nearer the area's edge than half that, they are pushed apart, and where the curve bends
    tighter than its traces can follow, it is smoothed. No step lets the curve cross
    itself: what would, stays."""
    step = spacing / 2
    target = sum(r.area for r in regions) / spacing
    tongue_len = float(np.sum(np.hypot(*np.diff(tongue, axis=0).T)))
    free = _split(curve, step)
    samples, sreg = _samples(regions, spacing / 3, rng)
    inner = tongue[1:-1]
    bend = _bend(round(least / pitch), pitch)
    for _ in range(LLOYD_CURVE):
        p = np.vstack([free, inner])
        k = len(free)
        old = p.copy()
        reg = _region_of(regions, p)
        p[1 : k - 1] = _lloyd(p, reg, samples, sreg, spacing)[1 : k - 1]
        p = _taubin(p, k)
        # (bends tighter than the traces can follow: smoothed while the length is held)
        sharp = np.abs(_radius(p, 1)) < BEND_SLACK * bend
        sharp[k - 1 :] = sharp[0] = False
        soft = sharp | np.roll(sharp, 1) | np.roll(sharp, -1)
        soft[k - 1 :] = soft[0] = False
        p[soft] += 0.5 * _lap(p)[soft]
        length = float(np.sum(np.hypot(*np.diff(p[:k], axis=0).T))) + tongue_len
        lam = float(np.clip(GAIN * (length - target) / target, -0.2, 0.5))
        lap = _lap(p)
        lap = sum(np.roll(lap, i, axis=0) for i in range(-2, 3)) / 5
        p[1 : k - 1] += lam * lap[1 : k - 1]
        move = p - old  # (at most half a step: the curve does not jump)
        size = np.hypot(move[:, 0], move[:, 1])
        p = old + move * np.minimum(1.0, (step / 2) / np.maximum(size, 1e-12))[:, None]
        free = _even(_untangle(old, p), k, step)

    step = spacing / 4
    inner = resample(np.vstack([free[-1], tongue[1:-1], free[0]]), step)[1:-1]
    free = _even(np.vstack([free, inner]), len(free), step, smooth=True)
    want = PUSH_MARGIN * least
    window = WINDOW * least
    # The edge the curve keeps off by half a spacing: the area's, and the zones' borders but
    # where the curve crosses them (where it joins the zones).
    edge = np.vstack([resample(np.asarray(r.coords), step / 2) for r in _rings(area)])
    borders = _borders(regions, area, step / 2)
    if len(borders):
        crossing = shapely.intersection(
            LineString(np.vstack([free, inner, free[:1]])),
            shapely.union_all([r.boundary for r in regions]),
        )
        xs = shapely.get_coordinates(crossing)
        if len(xs):
            near = Grid(xs, 1.5 * spacing).nearest(borders)
            far = (near < 0) | (np.hypot(*(borders - xs[np.maximum(near, 0)]).T) > 1.5 * spacing)
            borders = borders[far]
        edge = np.vstack([edge, borders])
    edges = Grid(edge, want)
    p, k = _grow(
        np.vstack([free, inner]), len(free), step, least, target - tongue_len, edge, edges, bend
    )
    free = p[:k]
    hot = None
    for it in range(REPAIR):
        free = _respace(p[:k], step)
        p = np.vstack([free, inner])
        k = len(free)
        which = np.arange(k)
        if hot is not None:  # only where something moved nearby
            cell = np.floor(free / want).astype(np.int64)
            which = np.nonzero(np.isin(cell[:, 0] * 1_000_003 + cell[:, 1], hot))[0]
        near, d = _neighbours(p, window, want, which=which)
        e = edges.nearest(p[which], lambda qi, pi: np.ones(len(qi), bool))
        de = np.where(e >= 0, np.hypot(*(p[which] - edge[np.maximum(e, 0)]).T), want)
        movable = (which > 0) & (which < k - 1)  # (the tongue's ends stay)
        bad = [  # (the edge stands for a run's middle: twice the distance to it counts)
            ((near >= 0) & (d < want) & movable, p[np.maximum(near, 0)], d),
            ((e >= 0) & (2 * de < want) & movable, edge[np.maximum(e, 0)], 2 * de),
        ]
        sharp = np.abs(_radius(p, 1)) < BEND_SLACK * bend
        sharp[k - 1 :] = sharp[0] = False
        if not sharp.any() and not any(hit.any() for hit, _, _ in bad):
            break
        move = np.zeros_like(p)
        for hit, other, dist in bad:
            away = p[which[hit]] - other[hit]
            away /= np.maximum(np.hypot(away[:, 0], away[:, 1]), 1e-12)[:, None]
            np.add.at(move, which[hit], away * (0.6 * (want - dist[hit]) + step / 8)[:, None])
        move = (np.roll(move, 1, axis=0) + 2 * move + np.roll(move, -1, axis=0)) / 4
        move += _soften(p, k, sharp, hard=it >= HARD)
        _mouths(p, k, move)
        size = np.hypot(move[:, 0], move[:, 1])
        move *= np.minimum(1.0, (step / 2) / np.maximum(size, 1e-12))[:, None]
        p = _untangle(p, p + move)
        moved = size[:k] > 0
        cell = np.unique(np.floor(p[:k][moved] / want).astype(np.int64), axis=0)
        cell = np.unique((cell[:, None, :] + _AROUND[None]).reshape(-1, 2), axis=0)
        hot = cell[:, 0] * 1_000_003 + cell[:, 1]
    return p, k


def _soften(p: np.ndarray, k: int, sharp: np.ndarray, hard: bool = False) -> np.ndarray:
    """A move rounding the curve's ``sharp`` bends: Taubin's smoothing about them, so that
    they open out rather than pull back (the curve keeps its length); ``hard``: a Laplacian
    step at them, for those Taubin's leaves too sharp."""
    soft = sharp.copy()
    for i in range(1, 4):
        soft |= np.roll(sharp, i) | np.roll(sharp, -i)
    out = _taubin(p, k, 2) - p
    out[~soft] = 0
    if hard:
        near = sharp | np.roll(sharp, 1) | np.roll(sharp, -1)
        out[near] += 0.5 * _lap(p)[near]
    return out


def _mouths(p: np.ndarray, k: int, move: np.ndarray) -> None:
    """Off the tongue's mouths: the curve on along their arcs' end for a while (``move``
    amended: the vertex next to each mouth put on that line, the next two drawn towards it,
    whatever else moves them; the tongue and its ends stay)."""
    for end, prev, sign in ((0, len(p) - 1, 1), (k - 1, k, -1)):
        t = p[end] - p[prev]
        t /= max(math.hypot(*t), 1e-12)
        for m in (1, 2, 3):
            i = end + sign * m
            on = p[end] + t * math.dist(p[i], p[end])
            move[i] = (on - p[i]) if m == 1 else move[i] + (0.5 / m) * (on - p[i])
    move[0] = move[k - 1] = 0
    move[k:] = 0


def _grow(
    p: np.ndarray,
    k: int,
    step: float,
    least: float,
    target: float,
    edge: np.ndarray,
    edges: Grid,
    bend: float,
) -> tuple[np.ndarray, int]:
    """The closed curve ``p`` (its first ``k`` vertices free, the rest the tongue's) grown
    into the room between its runs, as by differential growth: runs nearer each other (or
    twice the area's edge) than a little over the least spacing repel each other, and while
    the free part is shorter than ``target``, its bends bulge out where there is room. Each
    step looks again only where something was pushed the step before (an island at a time,
    in effect, once the rest has settled)."""
    reach = REACH * least
    look = reach + step
    window = WINDOW * least
    width = max(1, round(least / step / 2))  # (pushes smoothed over about a least spacing)
    hot = None
    lengths: list[float] = []
    for _ in range(GROW):
        free = _respace(p[:k], step)
        p = np.vstack([free, p[k:]])
        k = len(free)
        length = float(np.sum(np.hypot(*np.diff(free, axis=0).T)))
        lengths.append(length)
        stalled = len(lengths) > STALL and length < lengths[-STALL - 1] * 1.002
        if length >= target or stalled:
            break  # (grown as far as it goes)
        which = np.arange(k)
        if hot is not None:
            cell = np.floor(free / look).astype(np.int64)
            which = np.nonzero(np.isin(cell[:, 0] * 1_000_003 + cell[:, 1], hot))[0]
        if not len(which):
            break
        t = np.roll(p, -1, axis=0) - np.roll(p, 1, axis=0)
        t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-12)[:, None]
        normal = np.stack([-t[:, 1], t[:, 0]], 1)
        _, left = _neighbours(p, window, look, 1, which)
        _, right = _neighbours(p, window, look, -1, which)
        e = edges.nearest(p[which], lambda qi, pi: np.ones(len(qi), bool))
        to = edge[np.maximum(e, 0)] - p[which]
        de = np.where(e >= 0, 2 * np.hypot(to[:, 0], to[:, 1]), look)
        at = np.sum(to * normal[which], axis=1) > 0
        left = np.where(at, np.minimum(left, de), left)
        right = np.where(at, right, np.minimum(right, de))
        force = (np.maximum(reach - right, 0) - np.maximum(reach - left, 0)) / 2
        if length < target:
            lap = _lap(p)
            out = -sum(np.roll(lap, i, axis=0) for i in range(-2, 3))[which]
            way = np.sign(np.sum(out * normal[which], axis=1))
            room = np.where(way > 0, left, right) - reach
            force += way * GROW_RATE * np.clip(room, 0, step)
        push = np.zeros(len(p))
        push[which] = force
        push[k:] = 0
        busy = np.abs(push) > 0.05 * step
        if not busy.any():
            break
        for _ in range(2):
            push = sum(np.roll(push, i) for i in range(-width, width + 1)) / (2 * width + 1)
        move = normal * push[:, None] + _taubin(p, k, 1) - p
        sharp = np.abs(_radius(p, 1)) < BEND_SLACK * bend
        sharp[k - 1 :] = sharp[0] = False
        move += _soften(p, k, sharp)
        _mouths(p, k, move)
        size = np.hypot(move[:, 0], move[:, 1])
        move *= np.minimum(1.0, (step / 2) / np.maximum(size, 1e-12))[:, None]
        p = _untangle(p, p + move)
        cell = np.unique(np.floor(p[:k][busy[:k]] / look).astype(np.int64), axis=0)
        cell = np.unique((cell[:, None, :] + _AROUND[None]).reshape(-1, 2), axis=0)
        hot = cell[:, 0] * 1_000_003 + cell[:, 1]
    return p, k


def _untangle(old: np.ndarray, new: np.ndarray) -> np.ndarray:
    """The closed curve ``new`` (``old`` moved; ``old`` crossing nowhere) with the vertices
    of every segment that would cross another back where they were."""
    new = new.copy()
    n = len(new)
    moved = np.nonzero(np.any(new != old, axis=1))[0]
    for _ in range(50):
        if not len(moved):
            return new
        i, j = _crossing(new, np.unique(np.concatenate([moved, (moved - 1) % n])))
        if not len(i):
            return new
        back = np.unique(np.concatenate([i, (i + 1) % n, j, (j + 1) % n]))
        new[back] = old[back]
        moved = back
    return old


def _crossing(p: np.ndarray, which: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The segments of the closed polyline ``p`` among ``which`` (segment ``i`` from vertex
    ``i`` to the next) that cross or touch another one, other than their neighbours: the
    pairs."""
    q = np.roll(p, -1, axis=0)
    e = q - p
    length = np.hypot(e[:, 0], e[:, 1])
    rays = Rays(p, q, max(float(length.max()), 1e-6))
    d = e[which] / np.maximum(length[which], 1e-12)[:, None]
    ray, seg, t = rays.cast(p[which], d)
    i = which[ray]
    n = len(p)
    gap = np.abs(i - seg)
    hit = (np.minimum(gap, n - gap) > 1) & (t <= length[i])
    return i[hit], seg[hit]


def _radius(p: np.ndarray, reach: int = 2) -> np.ndarray:
    """The closed curve's signed radius of curvature at each vertex (positive turning left,
    towards the normal), from the turn between the chords ``reach`` vertices either way."""
    a = p - np.roll(p, reach, axis=0)
    b = np.roll(p, -reach, axis=0) - p
    turn = np.arctan2(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0], np.sum(a * b, axis=1))
    chord = (np.hypot(a[:, 0], a[:, 1]) + np.hypot(b[:, 0], b[:, 1])) / 2
    return chord / np.where(np.abs(turn) < 1e-9, 1e-9, turn)


_AROUND = np.array([(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)])


def _bend(n: int, pitch: float) -> float:
    """The tightest the curve may bend: its innermost trace (at the least pitch) within the
    bend's radius, and a U-turn no narrower than the least spacing."""
    return max((n - 1) / 2 * pitch / INSIDE, n * pitch / 2)


def _borders(regions: list[Polygon], area: shapely.Geometry, step: float) -> np.ndarray:
    """Points along the borders between regions (the folds; not the area's edge)."""
    edge = area.boundary.buffer(1e-6)
    lines = shapely.difference(shapely.union_all([r.boundary for r in regions]), edge)
    pts = [resample(shapely.get_coordinates(ln), step) for ln in _lines(shapely.line_merge(lines))]
    return np.vstack(pts) if pts else np.zeros((0, 2))


def _rings(g: shapely.Geometry) -> list[shapely.LinearRing]:
    return [r for poly in _polygons(g) for r in (poly.exterior, *poly.interiors)]


def _lanes(
    p: np.ndarray,
    k: int,
    area: shapely.Geometry,
    n: int,
    pitch: float,
    spacing: float,
    exact: np.ndarray,
) -> list[np.ndarray]:
    """The ``n`` traces round the closed curve ``p`` (vertices ``k`` on: the tongue's), as
    closed polylines: offsets of the curve at a pitch that shares the spacing to the next run
    on each side evenly (the area's edge counts as a run's middle), never below ``pitch``
    (with a margin; exactly where ``exact``: the tongue's legs). Offset from the curve made smooth
    (a Catmull-Rom spline through its vertices) and fine, so that no chord cuts a bend."""
    least = n * pitch
    cap = SPREAD * spacing
    sides = []
    q = np.roll(p, -2, axis=0) - np.roll(p, 2, axis=0)  # (a smooth normal)
    q /= np.maximum(np.hypot(q[:, 0], q[:, 1]), 1e-12)[:, None]
    normal = np.stack([-q[:, 1], q[:, 0]], 1)
    ea, eb = [], []
    for r in _rings(area):
        c = resample(np.asarray(r.coords), spacing / 2)
        ea.append(c[:-1])
        eb.append(c[1:])
    rays = Rays(np.vstack(ea), np.vstack(eb), cap / 2)
    radius = _radius(p)
    # the least pitch: with the margin, but on the tongue's legs (exactly the pitch there),
    # ramped in along the curve off them
    idx = np.nonzero(exact)[0]
    gap = np.abs(np.arange(len(p))[:, None] - idx[[0, -1]][None, :])
    off = np.where(exact, 0, np.min(np.minimum(gap, len(p) - gap), axis=1))
    floor = least * (1 + MARGIN * np.clip(off / RAMP, 0.0, 1.0))
    for side in (1, -1):
        _, d = _neighbours(p, WINDOW * least, cap, side)
        ray, _, t = rays.cast(p, side * normal)
        np.minimum.at(d, ray, 2 * t)
        # inside a bend: the innermost trace within its radius
        inside = side * radius > 0
        d[inside] = np.minimum(d[inside], INSIDE * np.abs(radius[inside]) * 2 * n / max(n - 1, 1))
        d[exact] = least
        m = d.copy()  # smoothed: a running minimum, then a running mean (never above d)
        for i in range(1, SMOOTH + 1):
            m = np.minimum(m, np.minimum(np.roll(d, i), np.roll(d, -i)))
        d = sum(np.roll(m, i) for i in range(-SMOOTH, SMOOTH + 1)) / (2 * SMOOTH + 1)
        d = np.maximum(d, floor)
        sides.append(_balance(floor / n, d / n, p, k, least))
    fine = _spline(p, FINE)
    t = np.arange(len(fine)) / FINE  # (each fine vertex's place between the curve's)
    lo = np.floor(t).astype(int) % len(p)
    hi = (lo + 1) % len(p)
    f = t - np.floor(t)
    q = np.roll(fine, -1, axis=0) - np.roll(fine, 1, axis=0)
    q /= np.maximum(np.hypot(q[:, 0], q[:, 1]), 1e-12)[:, None]
    normal = np.stack([-q[:, 1], q[:, 0]], 1)
    out = []
    tangent = np.stack([normal[:, 1], -normal[:, 0]], 1)
    for j in range(n):
        o = j - (n - 1) / 2
        side = sides[0] if o > 0 else sides[1]
        step = (side[lo] * (1 - f) + side[hi] * f) * o
        lane = fine + normal * step[:, None]
        # inside a bend tighter than the offset, the offset runs backwards: not those
        ahead = np.sum((np.roll(lane, -1, axis=0) - lane) * tangent, axis=1) > 0
        ahead &= np.roll(ahead, 1)
        out.append(_unloop(lane[ahead]))
    return out


def _balance(lo: np.ndarray, hi: np.ndarray, p: np.ndarray, k: int, least: float) -> np.ndarray:
    """The pitch of one side's traces along the closed curve ``p``: up to ``hi`` (to share the
    room), down to ``lo`` (the least) where that would skew them. Neighbouring traces on one
    side differ in length by the pitch times the curve's turning, so a pitch above the least
    in a bend skews them, one way or the other with the bend's sense; along the curve from
    the exit (vertex ``k``: the tongue's), the traces spread in a bend only where that pays
    back the skew run up so far, on the straight wherever there is room (the choice eased in
    and out over a few vertices)."""
    curv = 1 / _radius(p)  # (signed: turning left)
    ds = np.hypot(*(np.roll(p, -1, axis=0) - p).T)
    order = np.roll(np.arange(len(p)), -k)
    out = lo.copy()
    skew, u = 0.0, 0.0
    ease = 2 / (SMOOTH + 1)
    straight = STRAIGHT / least
    for i in order.tolist():
        c = curv[i]
        want = 1.0 if abs(c) < straight or skew * c <= 0 else 0.0
        u += ease * (want - u)
        out[i] = lo[i] + u * (hi[i] - lo[i])
        skew += out[i] * c * ds[i]
    return out


def _spline(p: np.ndarray, m: int) -> np.ndarray:
    """The closed polyline through ``p`` as a Catmull-Rom spline (centripetal), ``m``
    vertices per segment (the first of each at the segment's start)."""
    p0, p1, p2, p3 = np.roll(p, 1, axis=0), p, np.roll(p, -1, axis=0), np.roll(p, -2, axis=0)

    def knot(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return np.maximum(np.hypot(*(b - a).T), 1e-9) ** 0.5

    t1 = knot(p0, p1)
    t2 = t1 + knot(p1, p2)
    t3 = t2 + knot(p2, p3)
    out = []
    for i in range(m):
        t = (t1 + (t2 - t1) * i / m)[:, None]
        a1 = ((t1[:, None] - t) * p0 + t * p1) / t1[:, None]
        a2 = ((t2[:, None] - t) * p1 + (t - t1[:, None]) * p2) / (t2 - t1)[:, None]
        a3 = ((t3[:, None] - t) * p2 + (t - t2[:, None]) * p3) / (t3 - t2)[:, None]
        b1 = ((t2[:, None] - t) * a1 + t * a2) / t2[:, None]
        b2 = ((t3[:, None] - t) * a2 + (t - t1[:, None]) * a3) / (t3 - t1)[:, None]
        out.append(((t2[:, None] - t) * b1 + (t - t1[:, None]) * b2) / (t2 - t1)[:, None])
    return np.stack(out, 1).reshape(-1, 2)


def _unloop(q: np.ndarray, reach: int = 40) -> np.ndarray:
    """The closed polyline without the small loops an offset leaves inside tight bends:
    where a segment crosses one up to ``reach`` segments on, the vertices between give way
    to the crossing."""
    for _ in range(4):
        a, b = q, np.roll(q, -1, axis=0)
        r = b - a
        hits = []
        for j in range(2, reach + 1):
            c, s = np.roll(a, -j, axis=0), np.roll(r, -j, axis=0)
            den = r[:, 0] * s[:, 1] - r[:, 1] * s[:, 0]
            w = c - a
            ok = np.abs(den) > 1e-15
            den = np.where(ok, den, 1.0)
            t = (w[:, 0] * s[:, 1] - w[:, 1] * s[:, 0]) / den
            u = (w[:, 0] * r[:, 1] - w[:, 1] * r[:, 0]) / den
            ok &= (t > 0) & (t < 1) & (u > 0) & (u < 1)
            for i in np.nonzero(ok)[0]:
                hits.append((int(i), j, a[i] + t[i] * r[i]))
        if not hits:
            return q
        n = len(q)
        keep = np.ones(n, bool)
        q = q.copy()
        hits.sort(key=lambda h: (h[0], -h[1]))
        done = -1
        for i, j, x in hits:
            span = [(i + m) % n for m in range(1, j + 1)]
            if i <= done or not all(keep[v] for v in span) or not keep[i]:
                continue
            q[span[0]] = x
            for v in span[1:]:
                keep[v] = False
            done = i + j
        q = q[keep]
    return q


# ----------------------------------------------------------------------------- settling
class _Traces:
    """Open polylines held as one array: each vertex's trace, and the vertex before and
    after it on its trace (-1 at its ends)."""

    def __init__(self, lines: list[np.ndarray], u: list[np.ndarray] | None = None) -> None:
        self.p = np.vstack(lines)
        self.net = np.concatenate([np.full(len(t), i) for i, t in enumerate(lines)])
        if u is None:  # (where along its trace, as laid: a share of it)
            u = []
            for t in lines:
                arc = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(t, axis=0).T))])
                u.append(arc / max(arc[-1], 1e-12))
        self.u = np.concatenate(u)
        first = np.cumsum([0] + [len(t) for t in lines])
        idx = np.arange(len(self.p))
        self.prev = np.where(np.isin(idx, first[:-1]), -1, idx - 1)
        self.next = np.where(np.isin(idx, first[1:] - 1), -1, idx + 1)
        self.first = first

    def lines(self) -> list[np.ndarray]:
        return [self.p[a:b] for a, b in itertools.pairwise(self.first)]

    def respaced(self, step: float) -> _Traces:
        """The traces at about ``step`` between vertices (``_respace``), each vertex's place
        as laid carried along."""
        lines, us = [], []
        for a, b in itertools.pairwise(self.first):
            t, u = self.p[a:b], self.u[a:b]
            seg = np.hypot(*np.diff(t, axis=0).T)
            drop = np.zeros(len(t), bool)
            drop[1:-1] = seg[:-1] + seg[1:] < step
            drop[1:] &= ~drop[:-1]
            t, u = t[~drop], u[~drop]
            seg = np.hypot(*np.diff(t, axis=0).T)
            parts = np.maximum(1, np.ceil(seg / (1.5 * step))).astype(int)
            f = np.concatenate([np.arange(m) / m for m in parts])
            i = np.repeat(np.arange(len(seg)), parts)
            lines.append(np.vstack([t[i] + (t[i + 1] - t[i]) * f[:, None], t[-1:]]))
            us.append(np.concatenate([u[i] + (u[i + 1] - u[i]) * f, u[-1:]]))
        return _Traces(lines, us)

    def arc(self) -> np.ndarray:
        seg = np.hypot(*(self.p[np.maximum(self.prev, 0)] - self.p).T)
        seg[self.prev < 0] = 0.0
        out = np.cumsum(seg)
        return out - np.repeat(out[self.first[:-1]], np.diff(self.first))

    def normals(self) -> np.ndarray:
        a = self.p[np.where(self.prev < 0, np.arange(len(self.p)), self.prev)]
        b = self.p[np.where(self.next < 0, np.arange(len(self.p)), self.next)]
        t = b - a
        t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-12)[:, None]
        return np.stack([-t[:, 1], t[:, 0]], 1)

    def turning(self, reach: int = 2) -> np.ndarray:
        """Each vertex's signed curvature (turning left: positive), from the chords
        ``reach`` vertices either way along its trace (0 near its ends)."""
        a, b = np.arange(len(self.p)), np.arange(len(self.p))
        for _ in range(reach):
            a = np.where(self.prev[a] >= 0, self.prev[a], a)
            b = np.where(self.next[b] >= 0, self.next[b], b)
        u, v = self.p - self.p[a], self.p[b] - self.p
        turn = np.arctan2(u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0], np.sum(u * v, axis=1))
        chord = (np.hypot(u[:, 0], u[:, 1]) + np.hypot(v[:, 0], v[:, 1])) / 2
        return np.where(chord > 1e-12, turn / np.maximum(chord, 1e-12), 0.0)


def _settle(
    lines: list[np.ndarray], pitch: float, area: shapely.Geometry, keep: shapely.Geometry
) -> list[np.ndarray]:
    """The traces, each settled on its own into the room around it: every vertex moved
    towards the middle between the nearest copper on either side of it (the area's edge
    standing for copper at twice its distance; nothing within reach: a hole, moved into),
    never nearer other copper than a pitch, nor across it. Smoothness counts for little (a
    trace may kink into a corner of a hole; only jitter is smoothed away), but in a tight
    bend nothing moves along its axis into it: the innermost trace of a U-turn keeps its
    tip where it is and closes up its legs. Neighbouring traces keep their lengths (run
    from the exit) within ``SETTLE_SKEW`` pitches of each other at every point along the
    curve: where one is ahead, it stops gaining (or the other losing) until the other
    catches up. Only vertices near ones that moved are looked at again. The ends and the
    exit (``keep``) stay as laid."""
    step = pitch / 2
    near, far = 2 * pitch, SETTLE_REACH * pitch
    own = 0.5 * pitch  # (the trace's own vertices nearer along it: not copper across)
    tr = _Traces([np.asarray(t, float) for t in lines]).respaced(step)
    n = len(lines)
    edge = np.vstack([resample(np.asarray(r.coords), step / 2) for r in _rings(area)])
    edges = Grid(edge, far)
    shapely.prepare(keep)
    total = np.array([float(np.sum(np.hypot(*np.diff(t, axis=0).T))) for t in lines])
    bins = max(int(np.max(total) / (2 * pitch)), 1)  # (positions along the curve)
    base = _binned(tr, bins)  # (each trace's length by position, as laid)
    gained = np.zeros((n, bins))
    limit = SETTLE_SKEW * pitch
    hot = None
    for _ in range(SETTLE):
        p, net = tr.p, tr.net
        arc = tr.arc()
        where = np.minimum((tr.u * bins).astype(int), bins - 1)
        normal = tr.normals()
        fixed = (tr.prev < 0) | (tr.next < 0) | shapely.contains_xy(keep, p[:, 0], p[:, 1])
        for _ in range(4):  # (and a few vertices on from the ends)
            fixed |= fixed[np.maximum(tr.prev, 0)] & (tr.prev >= 0)
            fixed |= fixed[np.maximum(tr.next, 0)] & (tr.next >= 0)
        look = np.arange(len(p))
        if hot is not None:
            cell = np.floor(p / far).astype(np.int64)
            look = np.nonzero(np.isin(cell[:, 0] * 1_000_003 + cell[:, 1], hot))[0]
        push = np.zeros(len(p))
        if len(look):
            push[look] = _centring(p, net, arc, normal, look, edge, edges, near, far, own, pitch)
        push *= SETTLE_RATE
        # a tight bend: no move along its axis into it (its tip pinned, its legs may close)
        curv = tr.turning()
        axis = _bend_axes(tr, curv, SETTLE_PIN * pitch)
        move = normal * push[:, None]
        into = np.sum(move * axis, axis=1)
        move -= np.maximum(into, 0.0)[:, None] * axis
        # skew: where a trace is ahead of a neighbour (by position along the curve), no
        # more gaining there; where behind, no losing
        run = np.cumsum(gained, axis=1)
        ahead = np.zeros((n, bins))
        for t in range(n - 1):
            ahead[t] = np.maximum(ahead[t], run[t] - run[t + 1])
            ahead[t + 1] = np.maximum(ahead[t + 1], run[t + 1] - run[t])
        behind = np.zeros((n, bins))
        for t in range(n - 1):
            behind[t] = np.maximum(behind[t], run[t + 1] - run[t])
            behind[t + 1] = np.maximum(behind[t + 1], run[t] - run[t + 1])
        grows = -np.sum(move * normal, axis=1) * curv  # (length change per unit length)
        stop = ((grows > 0) & (ahead[net, where] > limit)) | (
            (grows < 0) & (behind[net, where] > limit)
        )
        move[stop | fixed] = 0.0
        size = np.hypot(move[:, 0], move[:, 1])
        move *= np.minimum(1.0, (step / 3) / np.maximum(size, 1e-12))[:, None]
        new = p + move
        # jitter smoothed away (Taubin: no shrinking) round what moved, but where fixed
        busy = np.hypot(move[:, 0], move[:, 1]) > 0
        busy |= busy[np.maximum(tr.prev, 0)] | busy[np.maximum(tr.next, 0)]
        busy &= (tr.prev >= 0) & (tr.next >= 0) & ~fixed
        for f in (0.3, -0.32):
            lap = (new[np.maximum(tr.prev, 0)] + new[np.maximum(tr.next, 0)]) / 2 - new
            new[busy] += f * lap[busy]
        new = _keep_clear(tr, p, new, pitch, own)
        # skew, exactly: where a pair's running difference passes the limit and grew, the
        # moves of the trace that gained more there taken back
        tr.p = new
        now = _binned(tr, bins) - base
        tr.p = p
        back = np.zeros(len(p), bool)
        before, after = np.cumsum(gained, axis=1), np.cumsum(now, axis=1)
        for t in range(n - 1):
            for a, b in ((t, t + 1), (t + 1, t)):
                over = (after[a] - after[b] > limit) & (after[a] - after[b] > before[a] - before[b])
                if not over.any():
                    continue
                last = int(np.nonzero(over)[0][-1])
                more = (now[a] - gained[a]) > (now[b] - gained[b])
                more[last + 1 :] = False
                back |= (net == a) & more[where]
        if back.any():
            new = new.copy()
            new[back] = p[back]
            new = _keep_clear(tr, p, new, pitch, own)
        moved = np.hypot(*(new - p).T) > 0.02 * pitch
        if not moved.any():
            break
        cell = np.unique(np.floor(new[moved] / far).astype(np.int64), axis=0)
        cell = np.unique((cell[:, None, :] + _AROUND[None]).reshape(-1, 2), axis=0)
        hot = cell[:, 0] * 1_000_003 + cell[:, 1]
        tr.p = new
        tr = tr.respaced(step)
        gained = _binned(tr, bins) - base
    return tr.lines()


def _binned(tr: _Traces, bins: int) -> np.ndarray:
    """Each trace's length by position along it as laid (``bins`` of it)."""
    out = np.zeros((int(tr.net.max()) + 1, bins))
    seg = np.nonzero(tr.next >= 0)[0]
    where = np.minimum((tr.u[seg] * bins).astype(int), bins - 1)
    np.add.at(out, (tr.net[seg], where), np.hypot(*(tr.p[tr.next[seg]] - tr.p[seg]).T))
    return out


def _centring(
    p: np.ndarray,
    net: np.ndarray,
    arc: np.ndarray,
    normal: np.ndarray,
    look: np.ndarray,
    edge: np.ndarray,
    edges: Grid,
    near: float,
    far: float,
    own: float,
    pitch: float,
) -> np.ndarray:
    """For the vertices ``look``: how far (to the left: positive) the middle between the
    nearest copper either side of each is, short of a pitch from it (half one from the
    area's edge, which stands for copper at twice its distance). Looked for ``near`` first,
    then ``far``; nothing that far: a hole, as wide as that."""
    out = []
    for side in (1.0, -1.0):
        d = np.full(len(look), far)
        todo = np.arange(len(look))
        for reach in (near, far):
            if not len(todo):
                break
            grid = Grid(p, reach)
            q = look[todo]

            def ok(
                qi: np.ndarray,
                pi: np.ndarray,
                side: float = side,
                q: np.ndarray = q,
                reach: float = reach,
            ) -> np.ndarray:
                v = p[pi] - p[q[qi]]
                dd = np.hypot(v[:, 0], v[:, 1])
                facing = side * np.sum(v * normal[q[qi]], axis=1) >= 0.7 * dd
                other = (net[pi] != net[q[qi]]) | (np.abs(arc[pi] - arc[q[qi]]) > own)
                return facing & other & (dd <= reach) & (dd > 0)

            j = grid.nearest(p[q], ok)
            found = j >= 0
            d[todo[found]] = np.hypot(*(p[j[found]] - p[q[found]]).T)
            todo = todo[~found]
        q = look

        def facing_edge(
            qi: np.ndarray, pi: np.ndarray, side: float = side, q: np.ndarray = q
        ) -> np.ndarray:
            return side * np.sum((edge[pi] - p[q[qi]]) * normal[q[qi]], axis=1) > 0

        e = edges.nearest(p[q], facing_edge)
        de = np.where(e >= 0, np.hypot(*(edge[np.maximum(e, 0)] - p[q]).T), far)
        out.append((np.minimum(d, 2 * de), de))
    (left, eleft), (right, eright) = out
    push = (left - right) / 2
    return np.where(
        push > 0,
        np.minimum(push, np.minimum(left - pitch, eleft - pitch / 2)),
        np.maximum(push, -np.minimum(right - pitch, eright - pitch / 2)),
    )


def _bend_axes(tr: _Traces, curv: np.ndarray, radius: float) -> np.ndarray:
    """For each vertex in a bend tighter than ``radius`` (zero elsewhere): the direction
    into the bend at its tightest point (its axis, pointing in)."""
    tight = np.abs(curv) * radius > 1
    axis = np.zeros_like(tr.p)
    if not tight.any():
        return axis
    normal = tr.normals()
    # runs of tight vertices along each trace, turning the same way
    start = tight & ~(
        tight[np.maximum(tr.prev, 0)]
        & (tr.prev >= 0)
        & (np.sign(curv[np.maximum(tr.prev, 0)]) == np.sign(curv))
    )
    run = np.cumsum(start) - 1
    run[~tight] = -1
    ids = run[tight]
    idx = np.nonzero(tight)[0]
    best = np.full(ids.max() + 1, -1)
    order = np.lexsort((np.abs(curv[idx]), ids))
    best[ids[order]] = idx[order]  # (the last per run: its tightest vertex)
    tip = best[ids]
    axis[idx] = normal[tip] * np.sign(curv[tip])[:, None]
    return axis


def _keep_clear(
    tr: _Traces, old: np.ndarray, new: np.ndarray, pitch: float, own: float
) -> np.ndarray:
    """``new`` with the vertices that would come nearer other copper than a pitch (with a
    margin for the sampling), or whose segments would cross, back where they were
    (``old``). A trace's own vertices ``a`` apart along it count as other copper once
    they are nearer than a semicircle that long would hold them (2 a / pi): it may U-turn,
    but not pinch."""
    new = new.copy()
    net = tr.net
    need = 1.02 * pitch
    for _ in range(6):
        moved = np.nonzero(np.any(new != old, axis=1))[0]
        if not len(moved):
            break
        tr.p = new
        arc = tr.arc()

        def close(
            qi: np.ndarray,
            pi: np.ndarray,
            moved: np.ndarray = moved,
            arc: np.ndarray = arc,
            new: np.ndarray = new,
        ) -> np.ndarray:
            q = moved[qi]
            d = np.hypot(*(new[pi] - new[q]).T)
            sep = np.abs(arc[pi] - arc[q])
            same = net[pi] == net[q]
            limit = np.where(same, np.minimum(need, 0.95 * 2 * sep / np.pi), need)
            return (d < limit) & (~same | (sep > own))

        j = Grid(new, need).nearest(new[moved], close)
        bad = moved[j >= 0]
        # segments that cross
        seg = np.nonzero(tr.next >= 0)[0]
        touch = np.isin(seg, moved) | np.isin(tr.next[seg], moved)
        a, b = new[seg], new[tr.next[seg]]
        e = b - a
        length = np.hypot(e[:, 0], e[:, 1])
        rays = Rays(a, b, max(float(length.max()), 1e-6))
        k = np.nonzero(touch)[0]
        ray, hit, t = rays.cast(a[k], e[k] / np.maximum(length[k], 1e-12)[:, None])
        i, h = seg[k[ray]], seg[hit]
        cross = (t <= length[k[ray]]) & (h != i) & (h != tr.prev[i]) & (tr.next[h] != i)
        crossed = np.concatenate([i[cross], tr.next[i[cross]], h[cross], tr.next[h[cross]]])
        back = np.unique(np.concatenate([bad, crossed[crossed >= 0]]))
        if not len(back):
            break
        new[back] = old[back]
    tr.p = old
    return new


# ----------------------------------------------------------------------------- generator
def generate(
    mask: shapely.Geometry,
    exit_corner: Point,
    exit_side: int,
    traces: int,
    pitch: float,
    seed: int | str | None = 0,
    zones: tuple[Polygon, ...] | list[Polygon] = (),
) -> Mesh:
    """The mesh over ``mask``: ``traces`` nets at ``pitch`` (trace plus space) round a closed
    space-filling curve, out through the exit cell (as ``kimesh.generate``: its corner with
    the smallest x and y ``exit_corner``, its side ``exit_side`` open). ``zones`` (the
    folding pattern's panels) are filled one by one and joined across their borders as
    seldom as can be; ``seed`` makes the layout repeatable."""
    if traces < 1:
        raise MeshError("need at least one trace")
    n = traces
    c = 2 * n * pitch
    least = n * pitch
    spacing = SPACING * least
    frame = _Frame(exit_side)
    ox, oy = exit_corner
    cell = frame.geom(shapely.box(ox, oy, ox + c, oy + c))
    x0, y0, _, _ = cell.bounds
    area = frame.geom(mask)
    # (the exit's leads run on from the open side: nothing of the mesh beyond it)
    area = shapely.difference(area, shapely.box(x0 - pitch, y0 - 4 * c, x0 + c + pitch, y0))
    if not area.buffer(1e-6).contains(shapely.box(x0, y0, x0 + c, y0 + 1.5 * spacing)):
        raise MeshError("no room for the mesh's exit cell")
    ym, ytop = y0 + spacing, y0 - least
    # The tongue's legs run straight through the exit cell to its mouth: the curve keeps
    # out of the cell up to there (its traces' pitch there is the least).
    area = shapely.difference(area, shapely.box(x0, y0 - 4 * c, x0 + c, ym))
    rng = random.Random(seed)
    nrng = np.random.default_rng(rng.getrandbits(64))
    # The tongue: two legs, a run's spacing apart, straight up through the exit cell.
    ax, bx = x0 + c / 4, x0 + 3 * c / 4
    pts, regions, _, cells, left = _curve(
        area,
        [frame.geom(z) for z in zones],
        spacing,
        ((ax, ym + spacing / 2), (bx, ym + spacing / 2)),
        rng,
    )
    tongue = np.array([(bx, ym), (bx, ytop), (ax, ytop), (ax, ym)])
    curve = np.vstack([[(ax, ym)], pts, [(bx, ym)]])
    p, k = _relax(curve, tongue, area, regions, spacing, least, pitch, nrng)
    cut = shapely.box(x0, ytop - c, x0 + c, y0)  # (within the leads' corridor)
    out = []
    exact = np.zeros(len(p), bool)  # (the tongue's legs: the traces at the pitch)
    exact[k:] = p[k:, 1] < y0 + spacing / 4
    lines = []
    for ring in _lanes(p, k, area, n, pitch, spacing, exact):
        line = shapely.line_merge(shapely.difference(LineString(np.vstack([ring, ring[:1]])), cut))
        if not isinstance(line, LineString):
            raise MeshError("a trace does not leave through the exit")
        lines.append(np.asarray(line.coords))
    if SETTLE:
        keep = shapely.box(x0 - c, ytop - c, x0 + 2 * c, ym + spacing)  # (the exit: as laid)
        lines = _settle(lines, pitch, area, keep)
    for xy in lines:
        line = LineString(xy)
        tol = SIMPLIFY * pitch / 0.3
        fast = line.simplify(tol, preserve_topology=False)
        line = fast if fast.is_simple else line.simplify(tol, preserve_topology=True)
        out.append(frame.inv(np.asarray(line.coords)))
    # net 1 outermost: its ends farthest from the exit's middle
    mid = frame.inv(np.array([[(ax + bx) / 2, y0]]))[0]
    out.sort(key=lambda t: -math.dist(t[0], mid))
    nets = tuple(tuple((float(x), float(y)) for x, y in t) for t in out)
    return Mesh(nets, c, cells, left, exit_corner, "sfc")
