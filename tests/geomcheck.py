"""Automated geometric checks for generated planar coil footprints.

The checker only looks at the copper that ends up in the footprint (lines, arcs, vias and pads) plus a description of
the *intended* geometry (outline contour, annular width, trace width, clearance, turn count). It does not use any of the
generator's internal state, so it can be used to compare different layout implementations against each other.

Checks:

    connectivity  The centerline graph of all copper must form one simple path from pad 1 to pad 2. Layer changes may
                  only happen at vias. Reports open ends, branches, orphaned segments and the winding number of the path
                  around the coil's center (which must match the requested number of turns).
    crossings     Centerlines of segments on the same layer that are not neighbors along the conductor path must not
                  intersect.
    clearance     Copper that belongs to different turns (i.e. that is far apart along the conductor path) must keep
                  at least `clearance` of edge-to-edge distance. Reports the worst deficit and the conductor length that
                  is affected.
    spacing       Sampled distribution of the edge-to-edge distance between neighboring turns, relative to the nominal
                  clearance. Tells how uniform the layout is, i.e. how much copper area is wasted by loose spacing.
    conformance   Per layer, the union of the tracks inflated by half a pitch must tile the intended annulus (contour
                  inflated by half a pitch minus the contour deflated by annular width plus half a pitch). Reports the
                  uncovered and excess area fractions and the Hausdorff distance between the actual and the intended
                  outer contour.
"""

import math
import itertools
from dataclasses import dataclass, field
from collections import defaultdict
import heapq

import numpy as np
import shapely
from shapely.geometry import Polygon, LineString, Point, MultiLineString
from shapely.strtree import STRtree


JOIN_EPS = 1e-6 # mm, endpoints closer than this are considered connected


@dataclass
class Seg:
    layer: str
    a: tuple
    b: tuple
    width: float

    @property
    def length(self):
        return math.dist(self.a, self.b)


@dataclass
class Via:
    x: float
    y: float
    diameter: float


@dataclass
class Pad:
    number: str
    layers: tuple
    x: float
    y: float
    diameter: float


@dataclass
class Copper:
    segs: list
    vias: list
    pads: list
    layers: tuple


def _arc_points(start, mid, end, tol):
    (x0, y0), (x1, y1), (x2, y2) = start, mid, end
    d = 2 * (x0 * (y1 - y2) + x1 * (y2 - y0) + x2 * (y0 - y1))
    if abs(d) < 1e-12:
        return [start, end]
    ux = ((x0*x0 + y0*y0) * (y1 - y2) + (x1*x1 + y1*y1) * (y2 - y0) + (x2*x2 + y2*y2) * (y0 - y1)) / d
    uy = ((x0*x0 + y0*y0) * (x2 - x1) + (x1*x1 + y1*y1) * (x0 - x2) + (x2*x2 + y2*y2) * (x1 - x0)) / d
    r = math.dist((ux, uy), start)
    a0 = math.atan2(y0-uy, x0-ux)
    a1 = math.atan2(y1-uy, x1-ux)
    a2 = math.atan2(y2-uy, x2-ux)
    # sweep from a0 through a1 to a2
    s1 = (a1 - a0) % (2*math.pi)
    s2 = (a2 - a0) % (2*math.pi)
    sweep = s2 if s1 <= s2 else s2 - 2*math.pi
    step = 2*math.acos(max(-1, 1 - tol/r)) if r > tol else math.pi/8
    n = max(2, math.ceil(abs(sweep) / step))
    pts = [(ux + r*math.cos(a0 + sweep*i/n), uy + r*math.sin(a0 + sweep*i/n)) for i in range(n+1)]
    pts[0], pts[-1] = start, end
    return pts


def extract_copper(footprint, layers=("F.Cu", "B.Cu"), arc_tol=0.0005):
    """ Convert a gerbonara footprint into a flat list of straight copper segments, vias and pads. """
    segs = []
    for l in footprint.lines:
        segs.append(Seg(l.layer, (l.start.x, l.start.y), (l.end.x, l.end.y), l.stroke.width))
    for a in footprint.arcs:
        pts = _arc_points((a.start.x, a.start.y), (a.mid.x, a.mid.y), (a.end.x, a.end.y), arc_tol)
        for p1, p2 in itertools.pairwise(pts):
            segs.append(Seg(a.layer, p1, p2, a.stroke.width))
    vias, pads = [], []
    for p in footprint.pads:
        if p.drill and p.drill.diameter:
            vias.append(Via(p.at.x, p.at.y, p.size.x))
        else:
            pads.append(Pad(p.number, tuple(p.layers), p.at.x, p.at.y, p.size.x))
    return Copper(segs, vias, pads, tuple(layers))


@dataclass
class Intent:
    """ Description of the intended layout """
    contour: list # outer contour of the coil (track centerline of the outermost turn), CCW polygon
    annular_width: float # depth from contour to centerline of the innermost turn
    turns: int
    trace_width: float
    clearance: float
    pitch: float # nominal centerline-to-centerline distance of neighboring turns
    center: tuple = None # a point inside the coil's hole, used for winding number computation
    clockwise: bool = False
    spiral_layers: int = 2 # number of layers that carry spiral turns (the others only carry connections)


@dataclass
class Report:
    ok_connectivity: bool = True
    open_ends: int = 0
    branches: int = 0
    orphans: int = 0
    degenerate_segments: int = 0
    backtracks: int = 0
    reaches_pad2: bool = True
    winding: float = float('nan')
    winding_error: float = float('nan')
    crossings: int = 0
    clearance_violations: int = 0
    worst_clearance_deficit: float = 0.0 # mm, track to track
    via_violations: int = 0
    worst_via_deficit: float = 0.0 # mm, via to via or via to track
    stubs: int = 0 # dangling stubs next to the terminal pads
    violation_length: float = 0.0 # mm of conductor affected
    self_overlaps: int = 0 # same-turn overlaps, e.g. at very sharp tips
    min_spacing_ratio: float = float('nan') # min edge-to-edge distance between turns / clearance
    p5_spacing_ratio: float = float('nan')
    p95_spacing_ratio: float = float('nan') # (spacing + w) / pitch at 95th percentile
    uncovered_fraction: float = float('nan')
    excess_fraction: float = float('nan')
    contour_hausdorff: float = float('nan') # max distance from contour to copper, in pitches
    overshoot: float = float('nan') # mm of copper outside the intended envelope
    total_length: float = 0.0
    n_segments: int = 0
    notes: list = field(default_factory=list)
    violations: list = field(default_factory=list) # [(layer, point, deficit)]
    crossing_points: list = field(default_factory=list)
    spacing_samples: list = field(default_factory=list) # [(layer, point, ratio)] if requested

    def score(self, clearance):
        """ Single scalar badness, 0 is perfect """
        s = 0
        if not self.ok_connectivity:
            s += 1000
        s += 100 * self.crossings
        s += 10 * self.worst_clearance_deficit / clearance
        s += 1 * self.worst_via_deficit / clearance
        if not math.isnan(self.winding_error):
            s += 100 * min(1, abs(self.winding_error))
        if not math.isnan(self.uncovered_fraction):
            s += 10*self.uncovered_fraction + 10*self.excess_fraction + max(0, self.contour_hausdorff - 1)
        return s

    def conformance_ok(self, trace_width):
        if math.isnan(self.uncovered_fraction):
            return True
        return (self.uncovered_fraction < 0.05 and self.contour_hausdorff < 1.25
                and self.overshoot < max(0.05, 0.1*trace_width))

    def passed(self, clearance, trace_width, rel_tol=0.05, vias=True):
        return (self.ok_connectivity and self.crossings == 0
                and self.worst_clearance_deficit <= rel_tol * clearance + 1e-4
                and (not vias or self.worst_via_deficit <= rel_tol * clearance + 1e-4)
                and abs(self.winding_error) < 0.05
                and self.conformance_ok(trace_width))


class _UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[b] = a


def _cluster_points(points, eps):
    """ Cluster points (list of (key, (x,y))) whose distance is below eps. Returns key -> cluster id. """
    uf = _UnionFind()
    grid = defaultdict(list)
    for key, (x, y) in points:
        gx, gy = math.floor(x/eps), math.floor(y/eps)
        uf.find(key)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other, (ox, oy) in grid[(gx+dx, gy+dy)]:
                    if math.dist((x, y), (ox, oy)) < eps:
                        uf.union(other, key)
        grid[(gx, gy)].append((key, (x, y)))
    return {key: uf.find(key) for key, _ in points}


def _seg_seg_dist(a, b, c, d):
    """ Minimum distance between segments ab and cd """
    if _segments_intersect(a, b, c, d):
        return 0.0
    return min(_pt_seg_dist(a, c, d), _pt_seg_dist(b, c, d), _pt_seg_dist(c, a, b), _pt_seg_dist(d, a, b))


def _pt_seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx-ax, by-ay
    l2 = dx*dx + dy*dy
    if l2 == 0:
        return math.dist(p, a)
    t = max(0, min(1, ((px-ax)*dx + (py-ay)*dy) / l2))
    return math.dist(p, (ax + t*dx, ay + t*dy))


def _orient(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def _segments_intersect(a, b, c, d):
    """ Proper intersection test (touching counts) """
    d1, d2 = _orient(c, d, a), _orient(c, d, b)
    d3, d4 = _orient(a, b, c), _orient(a, b, d)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def _intersection_point(a, b, c, d):
    x1, y1 = a; x2, y2 = b; x3, y3 = c; x4, y4 = d
    den = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
    if den == 0:
        return a
    t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / den
    return (x1 + t*(x2-x1), y1 + t*(y2-y1))


def check_layout(copper: Copper, intent: Intent, sample_step=None, do_conformance=True, max_records=200,
                 keep_samples=False):
    rep = Report()
    segs = [s for s in copper.segs if s.layer in copper.layers]
    rep.n_segments = len(segs)
    rep.degenerate_segments = sum(1 for s in segs if s.length < 1e-6)
    segs = [s for s in segs if s.length >= 1e-6]
    rep.total_length = sum(s.length for s in segs)

    w, clr, pitch = intent.trace_width, intent.clearance, intent.pitch
    contour = Polygon(intent.contour)
    if not contour.is_valid:
        contour = contour.buffer(0)

    # ---- connectivity graph ----
    pts = []
    for i, s in enumerate(segs):
        pts.append(((i, 0), s.a))
        pts.append(((i, 1), s.b))
    # cluster per layer
    by_layer = defaultdict(list)
    for (i, e), p in pts:
        by_layer[segs[i].layer].append(((i, e), p))
    node_of = {}
    for layer, lpts in by_layer.items():
        for key, cid in _cluster_points(lpts, JOIN_EPS).items():
            node_of[key] = (layer, cid)
    node_pos = {}
    for (i, e), p in pts:
        node_pos.setdefault(node_of[(i, e)], p)

    adj = defaultdict(list) # node -> [(other node, length, edge id)]
    for i, s in enumerate(segs):
        n1, n2 = node_of[(i, 0)], node_of[(i, 1)]
        adj[n1].append((n2, s.length, ('seg', i)))
        adj[n2].append((n1, s.length, ('seg', i)))

    def nodes_at(layer, x, y, eps):
        return [n for n, p in node_pos.items() if n[0] == layer and math.dist(p, (x, y)) < eps]

    # Vias connect the nodes of both layers at their center.
    via_nodes = []
    for j, v in enumerate(copper.vias):
        vn = ('via', j)
        via_nodes.append(vn)
        node_pos[vn] = (v.x, v.y)
        attached = 0
        for layer in copper.layers:
            for n in nodes_at(layer, v.x, v.y, JOIN_EPS):
                adj[vn].append((n, 0.0, ('via', j)))
                adj[n].append((vn, 0.0, ('via', j)))
                attached += 1
        if attached < 2:
            rep.notes.append(f'via {j} at ({v.x:.3f}, {v.y:.3f}) has {attached} track connections')
            rep.open_ends += 1

    pad_nodes = {}
    for pad in copper.pads:
        ns = []
        for layer in pad.layers:
            ns += nodes_at(layer, pad.x, pad.y, JOIN_EPS)
        pad_nodes[pad.number] = ns

    start = pad_nodes.get('1', [])
    end = pad_nodes.get('2', [])
    if not start or not end:
        rep.ok_connectivity = False
        rep.reaches_pad2 = False
        rep.notes.append('pad 1 or pad 2 not attached to any track')
        return rep
    pad_node_set = set(start) | set(end)

    # Degree check. A node with degree 1 that is not at a pad is an open end, a node with degree > 2 is a branch.
    for n, nbrs in adj.items():
        if n[0] == 'via':
            continue
        deg = len(nbrs)
        if deg == 1 and n not in pad_node_set:
            # Dead ends right next to a terminal pad are stubs: ugly, but they do not break the circuit.
            x, y = node_pos[n]
            if any(math.dist((x, y), (p.x, p.y)) < 2*p.diameter for p in copper.pads):
                rep.stubs += 1
                continue
            rep.open_ends += 1
            if len(rep.notes) < 20:
                x, y = node_pos[n]
                rep.notes.append(f'open end on {n[0]} at ({x:.3f}, {y:.3f})')
        elif deg > 2:
            rep.branches += 1
            if len(rep.notes) < 20:
                x, y = node_pos[n]
                rep.notes.append(f'branch (degree {deg}) on {n[0]} at ({x:.3f}, {y:.3f})')

    # Dijkstra from pad 1 to get path positions
    dist = {}
    heap = [(0.0, n) for n in start]
    while heap:
        d, n = heapq.heappop(heap)
        if n in dist:
            continue
        dist[n] = d
        for m, l, _e in adj[n]:
            if m not in dist:
                heapq.heappush(heap, (d + l, m))

    rep.reaches_pad2 = any(n in dist for n in end)
    seg_s = np.full(len(segs), np.nan)
    for i, s in enumerate(segs):
        d1, d2 = dist.get(node_of[(i, 0)]), dist.get(node_of[(i, 1)])
        if d1 is None or d2 is None:
            rep.orphans += 1
            continue
        seg_s[i] = (d1 + d2) / 2

    rep.ok_connectivity = rep.reaches_pad2 and rep.orphans == 0 and rep.branches == 0 and rep.open_ends == 0

    # Order segments along the path and compute backtracking & winding
    order = [i for i in np.argsort(seg_s) if not np.isnan(seg_s[i])]
    if intent.center is not None and order:
        cx, cy = intent.center
        total = 0.0
        for i in order:
            s = segs[i]
            n1, n2 = node_of[(i, 0)], node_of[(i, 1)]
            a, b = (s.a, s.b) if dist[n1] <= dist[n2] else (s.b, s.a)
            a1 = math.atan2(a[1]-cy, a[0]-cx)
            a2 = math.atan2(b[1]-cy, b[0]-cx)
            total += (a2 - a1 + math.pi) % (2*math.pi) - math.pi
        rep.winding = total / (2*math.pi)
        expected = -intent.turns if intent.clockwise else intent.turns
        rep.winding_error = rep.winding - expected

    # Backtracks: consecutive same-layer segments that reverse direction
    prev = None
    for i in order:
        s = segs[i]
        n1, n2 = node_of[(i, 0)], node_of[(i, 1)]
        a, b = (s.a, s.b) if dist[n1] <= dist[n2] else (s.b, s.a)
        if prev is not None and prev[0] == s.layer:
            (pa, pb) = prev[1]
            v1 = (pb[0]-pa[0], pb[1]-pa[1])
            v2 = (b[0]-a[0], b[1]-a[1])
            l1, l2 = math.hypot(*v1), math.hypot(*v2)
            if l1 > 0 and l2 > 0:
                cos = (v1[0]*v2[0] + v1[1]*v2[1]) / (l1*l2)
                if cos < -0.985: # > ~170 deg turn
                    rep.backtracks += 1
                    if len(rep.notes) < 40:
                        rep.notes.append(f'backtrack on {s.layer} at ({a[0]:.3f}, {a[1]:.3f})')
        prev = (s.layer, (a, b))

    # ---- crossings and clearance ----
    # Separation along the conductor path above which two pieces of copper count as belonging to different turns.
    inner = _inset(contour, intent.annular_width)
    inner_len = inner.length if not inner.is_empty else contour.length
    s_far = max(4*(w + clr), 0.25 * inner_len)
    # Pieces closer than this along the path never count as clearance violations or crossings at all
    s_near = math.pi/2 * (w + clr)

    geoms = [LineString([s.a, s.b]) for s in segs]
    layer_arr = np.array([s.layer for s in segs])
    tree = STRtree(geoms)
    max_w = max([s.width for s in segs] + [0])
    q_a, q_b = tree.query(geoms, predicate='dwithin', distance=max_w + clr)
    mask = q_a < q_b
    q_a, q_b = q_a[mask], q_b[mask]
    violating_segs = set()
    for i, j in zip(q_a, q_b):
        si, sj = segs[i], segs[j]
        if si.layer != sj.layer:
            continue
        if np.isnan(seg_s[i]) or np.isnan(seg_s[j]):
            continue
        ds = abs(seg_s[i] - seg_s[j]) - (si.length + sj.length)/2
        if ds < s_near:
            continue
        if _segments_intersect(si.a, si.b, sj.a, sj.b):
            rep.crossings += 1
            if len(rep.crossing_points) < max_records:
                rep.crossing_points.append((si.layer, _intersection_point(si.a, si.b, sj.a, sj.b)))
        d = _seg_seg_dist(si.a, si.b, sj.a, sj.b)
        required = (si.width + sj.width)/2 + clr
        deficit = required - d
        if deficit > 1e-4:
            if ds < s_far:
                rep.self_overlaps += 1
                continue
            rep.clearance_violations += 1
            rep.worst_clearance_deficit = max(rep.worst_clearance_deficit, deficit)
            violating_segs.add(i)
            violating_segs.add(j)
            if len(rep.violations) < max_records:
                rep.violations.append((si.layer, ((si.a[0]+si.b[0])/2, (si.a[1]+si.b[1])/2), deficit))

    # vias vs tracks and vias vs vias
    via_geoms = [Point(v.x, v.y) for v in copper.vias]
    for j, v in enumerate(copper.vias):
        vn = ('via', j)
        s_via = dist.get(vn)
        for i in tree.query(via_geoms[j], predicate='dwithin', distance=v.diameter/2 + max_w/2 + clr):
            s = segs[i]
            if s_via is None or np.isnan(seg_s[i]):
                continue
            ds = abs(seg_s[i] - s_via) - s.length/2
            if ds < s_far:
                continue
            d = _pt_seg_dist((v.x, v.y), s.a, s.b)
            deficit = v.diameter/2 + s.width/2 + clr - d
            if deficit > 1e-4:
                rep.via_violations += 1
                rep.worst_via_deficit = max(rep.worst_via_deficit, deficit)
                violating_segs.add(i)
                if len(rep.violations) < max_records:
                    rep.violations.append(('via', (v.x, v.y), deficit))
        for k in range(j+1, len(copper.vias)):
            u = copper.vias[k]
            deficit = (v.diameter + u.diameter)/2 + clr - math.dist((v.x, v.y), (u.x, u.y))
            if deficit > 1e-4:
                rep.via_violations += 1
                rep.worst_via_deficit = max(rep.worst_via_deficit, deficit)
                if len(rep.violations) < max_records:
                    rep.violations.append(('via', (v.x, v.y), deficit))
    rep.violation_length = sum(segs[i].length for i in violating_segs)

    # ---- spacing distribution ----
    if sample_step is None:
        sample_step = max(pitch / 2, rep.total_length / 20000)
    ratios = []
    for i, s in enumerate(segs):
        if np.isnan(seg_s[i]):
            continue
        n = max(1, int(s.length / sample_step))
        for k in range(n):
            t = (k + 0.5) / n
            p = (s.a[0] + t*(s.b[0]-s.a[0]), s.a[1] + t*(s.b[1]-s.a[1]))
            sp = seg_s[i] + (t - 0.5) * s.length
            best = math.inf
            for j in tree.query(Point(p), predicate='dwithin', distance=2*pitch):
                if j == i or layer_arr[j] != s.layer or np.isnan(seg_s[j]):
                    continue
                if abs(seg_s[j] - sp) - segs[j].length/2 < s_far:
                    continue
                best = min(best, _pt_seg_dist(p, segs[j].a, segs[j].b) - (s.width + segs[j].width)/2)
            if best < math.inf:
                ratios.append(best / clr if clr > 0 else best)
                if keep_samples:
                    rep.spacing_samples.append((s.layer, p, (best + s.width) / pitch))
    if ratios:
        r = np.array(ratios)
        rep.min_spacing_ratio = float(r.min())
        rep.p5_spacing_ratio = float(np.percentile(r, 5))
        rep.p95_spacing_ratio = float(np.percentile(r, 95))

    # ---- conformance ----
    if do_conformance:
        _conformance(rep, copper, segs, geoms, intent, contour)

    return rep


def _inset(poly, d):
    return poly.buffer(-d, join_style='mitre', mitre_limit=10)


def _conformance(rep, copper, segs, geoms, intent, contour):
    """ Compare the copper area with the intended annulus.

    A spiral only touches the outer contour where an arm starts, and only reaches the inner contour where an arm ends.
    In between, the outermost track sits up to one pitch inside the contour. The checks therefore use three regions:

        core      Depths [pitch/2, annular - pitch/2] from the contour. Every layer must cover this completely when
                  its tracks are inflated by half a pitch. Uncovered area here means wasted space (loose spacing, a
                  missing turn, a collapsed region).
        envelope  Depths [-w/2, annular + w/2 + via offset]. No copper may leave this region (excess).
        contour   Every point of the outer contour must be within one pitch of copper on some layer (undershoot).
    """
    w, p = intent.trace_width, intent.pitch
    via_extra = 0
    core = _inset(contour, p/2).difference(_inset(contour, intent.annular_width - p/2))
    env = contour.buffer(w/2 + via_extra + 1e-3, join_style='mitre', mitre_limit=10).difference(
            _inset(contour, intent.annular_width + w/2 + via_extra + 1e-3))
    uncovered = []
    all_copper = []
    # Vias may sit outside of the envelope (via offset). Allow the copper of their connection stubs.
    via_zones = [Point(v.x, v.y).buffer(v.diameter/2 + w/2 + env.distance(Point(v.x, v.y)) + 1e-3)
                 for v in copper.vias]
    if via_zones:
        env = env.union(shapely.unary_union(via_zones))
    for li, layer in enumerate(copper.layers):
        lines = [geoms[i] for i, s in enumerate(segs) if s.layer == layer]
        if not lines:
            continue
        if core.area > 0 and li < intent.spiral_layers:
            loose = shapely.unary_union(shapely.buffer(lines, p/2 * 1.001, quad_segs=4))
            uncovered.append(core.difference(loose).area / core.area)
        all_copper.append(shapely.unary_union(shapely.buffer(lines, w/2, quad_segs=4)))
    if not all_copper:
        return
    cu = shapely.unary_union(all_copper)
    rep.uncovered_fraction = max(uncovered) if uncovered else 0.0
    ring = _inset(contour, 0).difference(_inset(contour, intent.annular_width))
    rep.excess_fraction = cu.difference(env).area / max(ring.area, 1e-9)
    # undershoot: distance from the contour to the nearest copper, in units of pitch
    pts = shapely.points(shapely.get_coordinates(shapely.segmentize(contour.exterior, p/4)))
    rep.contour_hausdorff = float(shapely.distance(pts, cu).max()) / p
    # overshoot: distance of copper beyond the envelope in mm
    bpts = shapely.points(shapely.get_coordinates(shapely.segmentize(cu.boundary, p/4)))
    rep.overshoot = float(shapely.distance(bpts, env).max())


def intent_from_model(model, contour_tol=0.01):
    """ Derive the intended geometry from a kicoil PlanarInductor object. This only uses the user-facing parameters
    (shape outline, annular width, turns, trace width, clearance), not any internal layout state. """
    from kicoil.geometry import CircleShape
    shape = model.shape
    if isinstance(shape, CircleShape):
        r = shape.outer_radius
        n = max(64, math.ceil(math.pi / math.acos(1 - contour_tol/r)))
        contour = [(r*math.cos(2*math.pi*i/n), r*math.sin(2*math.pi*i/n)) for i in range(n)]
        annular = shape.outer_radius - shape.inner_radius
    else:
        contour = list(shape.polygon)
        annular = shape.annular_width
    poly = Polygon(contour)
    if not poly.exterior.is_ccw:
        contour = contour[::-1]
        poly = Polygon(contour)
    inner = poly.buffer(-annular * 1.02, join_style='mitre', mitre_limit=10)
    if inner.is_empty:
        inner = poly.buffer(-annular * 0.98, join_style='mitre', mitre_limit=10)
    if inner.is_empty:
        center = poly.representative_point().coords[0]
    else:
        if not isinstance(inner, Polygon):
            inner = max(inner.geoms, key=lambda g: g.area)
        center = inner.representative_point().coords[0]
    return Intent(contour=contour, annular_width=annular, turns=model.turns, trace_width=model.trace_width,
                  clearance=model.clearance, pitch=model.trace_width + model.clearance, center=center,
                  clockwise=model.clockwise, spiral_layers=model.layers)
