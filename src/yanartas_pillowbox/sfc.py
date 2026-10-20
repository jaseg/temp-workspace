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
import sys
from collections import defaultdict, deque
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import LineString, MultiPoint, Polygon

from yanartas_pillowbox import progress
from yanartas_pillowbox.mesh import (
    DOWN,
    LEFT,
    UP,
    Grid,
    Mesh,
    MeshError,
    Point,
    resample,
)

try:  # (the settling's Rust core, on all cores: rust/python; the browser has its wasm)
    import yanartas_mesh as _native
except ImportError:  # pragma: no cover
    _native = None

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
SETTLE = 40  # steps settling each trace into the middle of the room either side of it
SETTLE_RATE = 0.5  # ... the share of the way there a step goes
SETTLE_REACH = 3.0  # ... copper looked for this many pitches out (beyond: a hole, moved into)
SETTLE_PIN = 1.5  # ... bends tighter than this many pitches' radius do not move inwards
SETTLE_COOL = 2.0  # ... the moves dying down over the steps as (1 - step / steps) to this
SETTLE_STEP = 0.35  # ... the traces held at this many pitches between vertices
SETTLE_STILL = 0.005  # ... moves shorter than this many pitches: none
SETTLE_BAND = 1.0  # ... traces within this many pitches of length of each other: not steered
SETTLE_LEAP = 0.34  # ... a vertex moved at most this many of the steps between vertices
SETTLE_TUNE = 3.0  # ... a trace this many pitches behind (or ahead): steered at full strength
SETTLE_STEER = 0.6  # ... the share of its bends' depth a step grows (or straightens) them by
SETTLE_SPAN = 25  # ... (where along the curve it gains more, over this many places)
SETTLE_STEER_COOL = 2.0  # ... (the steering dying down as the moves, to this)
SETTLE_TIP = 1.0  # ... U-turns tighter than this many pitches per trace's radius: tips
SETTLE_REACH_OUT = 1.0  # ... leaning out along their axis by this share of the room
MATCH = 20  # steps matching the settled traces' lengths (taking it out of the longer)
# (the band above how far the leads swing to and fro through the bends: else every swing is cut)
MATCH_BAND = 15.0  # ... no trace more than this many pitches ahead of the shortest
MATCH_RATE = 0.5  # ... the share of their bends' depth a step straightens them by, at most
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
            progress.report("graph", si + 1, len(segments) + 1, cells=len(g.pts))
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
    """The curve, relaxed by the Rust core (``curve::relax``; see ARCHITECTURE.md, 6. and 7.):
    ``curve`` an open polyline from the tongue's left end round to its right end, the tongue
    closing it. Returned closed (the tongue last), with the number of vertices before the
    tongue's. Here, what needs shapely: the regions' rings and area, the area's edge and the
    borders between regions (points along them)."""
    step = spacing / 8  # (the edge's points: half the finer relaxing step apart)
    edge = np.vstack([resample(np.asarray(r.coords), step) for r in _rings(area)])
    p, k = _core().relax_curve(
        np.ascontiguousarray(curve, float),
        np.ascontiguousarray(tongue, float),
        [[np.asarray(r.coords, float) for r in _rings(z)] for z in regions],
        sum(r.area for r in regions) / spacing,
        edge,
        np.ascontiguousarray(_borders(regions, area, step), float),
        spacing,
        least,
        pitch,
        tuple(float(v) for v in rng.random(2) * spacing / 3),
        {
            "lloyd_curve": LLOYD_CURVE,
            "gain": GAIN,
            "push_margin": PUSH_MARGIN,
            "window": WINDOW,
            "bend_slack": BEND_SLACK,
            "grow": GROW,
            "reach": REACH,
            "grow_rate": GROW_RATE,
            "hard": HARD,
            "stall": STALL,
            "repair": REPAIR,
            "inside": INSIDE,
        },
        lambda step, steps: progress.report("relax", step, steps),
    )
    return np.asarray(p), int(k)


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
    closed polylines, by the Rust core (``lanes::lanes``): offsets of the curve at a pitch
    that shares the spacing to the next run on each side evenly (the area's edge counts as a
    run's middle), never below ``pitch`` (with a margin; exactly where ``exact``: the
    tongue's legs), in bends only as far as keeps skew down."""
    rings = [resample(np.asarray(r.coords), spacing / 2) for r in _rings(area)]
    out = _core().offset_lanes(
        np.ascontiguousarray(p, float),
        k,
        np.vstack([c[:-1] for c in rings]),
        np.vstack([c[1:] for c in rings]),
        n,
        pitch,
        spacing,
        [bool(x) for x in exact],
        {
            "spread": SPREAD,
            "smooth": SMOOTH,
            "fine": FINE,
            "ramp": float(RAMP),
            "margin": MARGIN,
            "inside": INSIDE,
            "window": WINDOW,
            "straight": STRAIGHT,
        },
    )
    return [np.asarray(t) for t in out]


# ----------------------------------------------------------------------------- settling
def _settle(
    lines: list[np.ndarray],
    pitch: float,
    area: shapely.Geometry,
    regions: list[Polygon],
    keep: shapely.Geometry,
) -> list[np.ndarray]:
    """The traces, each settled on its own into the room around it, then matched in length,
    by the Rust core (rust/core; see ARCHITECTURE.md, Settling): natively its extension
    (yanartas_mesh, on all cores), in the browser its WebAssembly build. Here, what needs
    shapely: the edge's points (the area's edge, and the zones' borders but where the
    traces cross them at the curve's joins, where they stay as laid), the zones' rings, and
    the exit (``keep``, left as laid)."""
    step = SETTLE_STEP * pitch
    far = SETTLE_REACH * pitch
    edge = np.vstack([resample(np.asarray(r.coords), step / 2) for r in _rings(area)])
    borders = _borders(regions, area, step / 2)
    xs = shapely.get_coordinates(
        shapely.intersection(
            shapely.MultiLineString(lines), shapely.union_all([r.boundary for r in regions])
        )
    )
    if len(borders) and len(xs):
        near_x = Grid(xs, far).nearest(borders)
        clear = (near_x < 0) | (np.hypot(*(borders - xs[np.maximum(near_x, 0)]).T) > far)
        edge = np.vstack([edge, borders[clear]])
    elif len(borders):
        edge = np.vstack([edge, borders])
    settle = _core().settle_traces

    def report(d: dict) -> None:
        progress.report(d.pop("phase"), d.pop("step"), d.pop("steps"), **d)

    out = settle(
        [np.ascontiguousarray(t, float) for t in lines],
        pitch,
        np.ascontiguousarray(edge, float),
        [[np.asarray(r.coords, float) for r in _rings(z)] for z in regions],
        tuple(float(v) for v in keep.bounds),
        _params(),
        report,
    )
    return [np.asarray(t) for t in out]


def _core() -> object:
    """The Rust core (rust/core): natively its extension ``yanartas_mesh``, in the browser
    its WebAssembly build behind the same calls."""
    core = _native if _native is not None else _browser_core()
    if core is None:
        raise MeshError(
            "the mesh layout needs its Rust core: install yanartas-mesh (rust/python), "
            "or in the browser build its WebAssembly (artifact/build.py)"
        )
    return core


def _browser_core() -> object | None:
    """In the browser (Pyodide), the WebAssembly build the web worker loaded
    (``self.yanartasMesh``), behind the extension's calls; else none."""
    if sys.platform != "emscripten":
        return None
    import types

    import js  # type: ignore[import-not-found]
    from pyodide.ffi import create_proxy, to_js  # type: ignore[import-not-found]

    mesh = getattr(js, "yanartasMesh", None)
    if mesh is None:
        return None

    def f64(a: np.ndarray) -> object:
        return to_js(np.ascontiguousarray(a, float).ravel())

    def u32(a: list[int]) -> object:
        return to_js(np.asarray(a, np.uint32))

    def flat(points: list[np.ndarray]) -> tuple[object, object]:
        both = np.vstack(points) if points else np.zeros((0, 2))
        return f64(both), u32([len(q) for q in points])

    def obj(d: dict) -> object:
        return to_js(d, dict_converter=js.Object.fromEntries)

    def unflat(points: object, lens: object) -> list[np.ndarray]:
        pts = np.asarray(points.to_py(), float).reshape(-1, 2)
        return np.split(pts, np.cumsum(np.asarray(lens.to_py(), int))[:-1])

    def call(fn, *args, report=None):  # noqa: ANN001, ANN002, ANN202
        hook = create_proxy(report) if report is not None else None
        try:
            return fn(*args, hook)
        finally:
            if hook is not None:
                hook.destroy()

    def settle_traces(lines, pitch, edge, zones, keep, params, report):  # noqa: ANN001, ANN202
        rings = [r for z in zones for r in z]
        out = call(
            mesh.settle, *flat(lines), pitch, f64(edge), *flat(rings),
            u32([len(z) for z in zones]), f64(np.array(keep)), obj(params),
            report=lambda o: report(o.to_py()),
        )  # fmt: skip
        return unflat(out.points, out.lens)

    def relax_curve(*a: object) -> tuple[np.ndarray, int]:
        curve, tongue, regions, target, edge, borders, spacing, least, pitch = a[:9]
        offset, params, report = a[9:]
        rings = [r for z in regions for r in z]
        out = call(
            mesh.relax_curve, f64(curve), f64(tongue), *flat(rings),
            u32([len(z) for z in regions]), target, f64(edge), f64(borders), spacing, least,
            pitch, f64(np.array(offset)), obj(params), report=report,
        )  # fmt: skip
        return np.asarray(out.points.to_py(), float).reshape(-1, 2), int(out.k)

    def offset_lanes(p, k, edge_a, edge_b, n, pitch, spacing, exact, params):  # noqa: ANN001, ANN202
        out = mesh.offset_lanes(
            f64(p), k, f64(edge_a), f64(edge_b), n, pitch, spacing,
            to_js(np.asarray(exact, np.uint8)), obj(params),
        )  # fmt: skip
        return unflat(out.points, out.lens)

    return types.SimpleNamespace(
        settle_traces=settle_traces, relax_curve=relax_curve, offset_lanes=offset_lanes
    )


def _params() -> dict[str, float]:
    """The settling's constants, by the Rust core's names for them."""
    return {
        "steps": SETTLE,
        "rate": SETTLE_RATE,
        "reach": SETTLE_REACH,
        "pin": SETTLE_PIN,
        "cool": SETTLE_COOL,
        "step": SETTLE_STEP,
        "still": SETTLE_STILL,
        "band": SETTLE_BAND,
        "leap": SETTLE_LEAP,
        "tune": SETTLE_TUNE,
        "steer": SETTLE_STEER,
        "span": SETTLE_SPAN,
        "steer_cool": SETTLE_STEER_COOL,
        "tip": SETTLE_TIP,
        "reach_out": SETTLE_REACH_OUT,
        "match_steps": MATCH,
        "match_band": MATCH_BAND,
        "match_rate": MATCH_RATE,
    }


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
    progress.report("graph", cells=cells)
    p, k = _relax(curve, tongue, area, regions, spacing, least, pitch, nrng)
    progress.report("relax", vertices=len(p))
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
        progress.report("lanes", traces=len(lines))
        lines = _settle(lines, pitch, area, regions, keep)
    progress.report("match", 1, 1)
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
