"""Automated geometric checks for generated planar coil footprints.

The checker only looks at the copper that ends up in the footprint (lines, arcs, vias and pads) plus a description of
the *intended* geometry (outline contour, annular width, trace width, clearance, turn count, via size and offset). It
does not use any of the generator's internal state, so it can be used to compare different layout implementations
against each other.

Checks:

    copper        Copper on a layer other than the coil's layer pair, pads other than pad 1 and pad 2, and copper in
                  footprint items the checker does not interpret (copper rectangles, circles, polygons, text, filled
                  zones, custom pads) are reported as stray copper.
    width         The emitted track widths must equal the intended trace width.
    connectivity  The copper must form one simple path from pad 1 to pad 2 that uses every track segment exactly once.
                  Track ends are joined when they coincide, when a dangling track end lies within the copper of a via
                  or pad, or when two collinear pieces of track overlap (one track drawn in two pieces). Layer changes
                  may only happen at vias. Reports open ends, branches, orphaned segments, duplicate segments, stray
                  vias (fewer than two track connections), shorts (pad 1 and pad 2 connected directly, or a path from
                  pad 1 to pad 2 that bypasses part of the conductor) and the winding number of the path around the
                  coil's center (which must match the requested number of turns).
    crossings     Centerlines of segments on the same layer that are not neighbors along the conductor path must not
                  intersect.
    clearance     Copper that belongs to different turns must keep at least `clearance` of edge-to-edge distance.
                  Copper belongs to different turns when it is at least half a turn apart in cumulative winding angle
                  around the coil's center, or far apart along the conductor path. Track-track, via-track/via-via and
                  pad-track/pad-via/pad-pad violations are reported separately. Clearance deficits between parts of the
                  *same* turn (the conductor folding onto itself at a tight tip) are counted as self overlaps.
    spacing       Sampled distribution of the edge-to-edge distance between neighboring turns, relative to the nominal
                  clearance. Tells how uniform the layout is, i.e. how much copper area is wasted by loose spacing.
    conformance   Per layer, the union of the tracks inflated by half a pitch must tile the intended annulus (contour
                  inflated by half a pitch minus the contour deflated by annular width plus half a pitch). Reports the
                  uncovered and excess area fractions, the Hausdorff distance between the actual and the intended
                  outer contour, how far any copper (tracks, vias, pads) leaves the intended envelope, and how far via
                  centers are beyond the intended via offset.
"""

import math
import itertools
from dataclasses import dataclass, field
from collections import defaultdict
import heapq

import numpy as np
import shapely
import shapely.affinity
from shapely.geometry import Polygon, LineString, Point
from shapely.strtree import STRtree


JOIN_EPS = 1e-6 # mm, endpoints closer than this are considered connected
ATTACH_TOL = 1e-3 # mm, a track end this close to a collinear track's centerline lies on it
COLLINEAR_TOL = 1e-3 # rad, maximum angle between collinear track pieces
TURN_SEP = 0.5 # revolutions; copper at least this far apart in winding angle belongs to different turns
OVERSHOOT_TOL = 0.05 # mm of copper (or of a via center) allowed beyond the intended envelope
WIDTH_TOL = 0.01 # allowed relative deviation of an emitted track width from the intended trace width ...
WIDTH_TOL_ABS = 0.001 # ... or this many mm, whichever is larger


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
    diameter: float # size along x; for circular pads the diameter
    size: tuple = None # (x, y) size, defaults to (diameter, diameter)
    shape: str = 'circle' # circle, rect, oval or roundrect
    angle: float = 0.0 # rotation in degrees, KiCad convention
    rratio: float = 0.25 # corner radius ratio for roundrect

    @property
    def extent(self):
        """ Diameter of a circle around the center that contains the pad """
        sx, sy = self.size or (self.diameter, self.diameter)
        return sx if self.is_circle() else math.hypot(sx, sy)

    def is_circle(self):
        sx, sy = self.size or (self.diameter, self.diameter)
        return self.shape == 'circle' or (self.shape in ('oval', 'roundrect') and math.isclose(sx, sy) and
                                          (self.shape == 'oval' or self.rratio >= 0.5))

    def geometry(self, quad_segs=16):
        sx, sy = self.size or (self.diameter, self.diameter)
        x, y = self.x, self.y
        if self.is_circle():
            return Point(x, y).buffer(sx/2, quad_segs=quad_segs)
        if self.shape == 'oval':
            r = min(sx, sy) / 2
            if sx >= sy:
                g = LineString([(x - sx/2 + r, y), (x + sx/2 - r, y)]).buffer(r, quad_segs=quad_segs)
            else:
                g = LineString([(x, y - sy/2 + r), (x, y + sy/2 - r)]).buffer(r, quad_segs=quad_segs)
        elif self.shape == 'roundrect':
            r = min(0.5, self.rratio) * min(sx, sy)
            g = shapely.box(x - sx/2 + r, y - sy/2 + r, x + sx/2 - r, y + sy/2 - r).buffer(r, quad_segs=quad_segs)
        else:
            g = shapely.box(x - sx/2, y - sy/2, x + sx/2, y + sy/2)
        if self.angle:
            # KiCad's y axis points down, so a positive (counter-clockwise on screen) rotation is clockwise here
            g = shapely.affinity.rotate(g, -self.angle, origin=(x, y))
        return g

    def dist_to_seg(self, a, b):
        """ Distance from the pad's copper to segment ab (for circular pads negative when ab enters the pad) """
        if self.is_circle():
            return _pt_seg_dist((self.x, self.y), a, b) - (self.size or (self.diameter,))[0]/2
        return self.geometry().distance(LineString([a, b]) if a != b else Point(a))

    def contains(self, p):
        if self.is_circle():
            return self.dist_to_seg(p, p) < 0
        return self.geometry().contains(Point(p))


@dataclass
class Copper:
    segs: list
    vias: list
    pads: list
    layers: tuple
    unhandled: list = field(default_factory=list) # descriptions of copper items the checker cannot interpret


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


def _is_copper_layer(name):
    return isinstance(name, str) and name.endswith('.Cu')


def _item_layers(item):
    out = []
    for attr in ('layer', 'layers'):
        v = getattr(item, attr, None)
        if v is None:
            continue
        for l in ([v] if isinstance(v, str) else v):
            out.append(l if isinstance(l, str) else getattr(l, 'layer', str(l)))
    return out


def extract_copper(footprint, layers=("F.Cu", "B.Cu"), arc_tol=0.0005):
    """ Convert a gerbonara footprint into a flat list of straight copper segments, vias and pads. Copper items that
    are not lines, arcs or simple pads are listed in `Copper.unhandled`. """
    segs = []
    for l in footprint.lines:
        segs.append(Seg(l.layer, (l.start.x, l.start.y), (l.end.x, l.end.y), l.stroke.width))
    for a in footprint.arcs:
        pts = _arc_points((a.start.x, a.start.y), (a.mid.x, a.mid.y), (a.end.x, a.end.y), arc_tol)
        for p1, p2 in itertools.pairwise(pts):
            segs.append(Seg(a.layer, p1, p2, a.stroke.width))

    unhandled = []
    for attr in ('rectangles', 'circles', 'polygons', 'curves', 'texts', 'text_boxes'):
        for item in getattr(footprint, attr, None) or []:
            cu = [l for l in _item_layers(item) if _is_copper_layer(l)]
            if cu:
                unhandled.append(f'{attr.rstrip("s")} on {",".join(cu)}')
    for z in getattr(footprint, 'zones', None) or []:
        cu = [l for l in _item_layers(z) if _is_copper_layer(l)]
        if cu and getattr(z, 'keepout', None) is None:
            unhandled.append(f'copper zone on {",".join(cu)}')

    vias, pads = [], []
    for p in footprint.pads:
        cu = tuple(l for l in p.layers if _is_copper_layer(l))
        if not cu:
            continue
        number = str(p.number) if p.number is not None else ''
        if p.drill and p.drill.diameter and number in ('', 'NC'):
            vias.append(Via(p.at.x, p.at.y, p.size.x))
            continue
        shape = str(getattr(p.shape, 'name', p.shape))
        if shape not in ('circle', 'rect', 'oval', 'roundrect'):
            unhandled.append(f'{shape} pad {number} (checked as its bounding rectangle)')
            shape = 'rect'
        pads.append(Pad(number, cu, p.at.x, p.at.y, p.size.x, size=(p.size.x, p.size.y), shape=shape,
                        angle=p.at.rotation or 0.0, rratio=getattr(p, 'roundrect_rratio', None) or 0.25))
    return Copper(segs, vias, pads, tuple(layers), unhandled)


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
    via_diameter: float = 0.0
    via_offset: float = 0.0 # how far outside the contour (outer vias) or inside the inner contour (inner vias) vias sit
    via_stagger: bool = False # every other via sits at three times the via offset


@dataclass
class Report:
    ok_connectivity: bool = True
    open_ends: int = 0
    branches: int = 0
    orphans: int = 0
    degenerate_segments: int = 0
    duplicate_segments: int = 0 # segments lying completely on top of another collinear segment
    stray_vias: int = 0 # vias with fewer than two track connections
    shorts: int = 0 # pad 1 connected to pad 2 directly, or a path from pad 1 to pad 2 that bypasses segments
    stray_copper: int = 0 # copper on other layers, extra pads, footprint items the checker does not interpret
    backtracks: int = 0
    reaches_pad2: bool = True
    winding: float = float('nan')
    winding_error: float = float('nan')
    crossings: int = 0
    clearance_violations: int = 0
    worst_clearance_deficit: float = 0.0 # mm, track to track
    via_violations: int = 0
    worst_via_deficit: float = 0.0 # mm, via to via or via to track
    pad_violations: int = 0
    worst_pad_deficit: float = 0.0 # mm, pad to track of another turn, pad to via, pad to pad
    stubs: int = 0 # dangling stubs next to the terminal pads
    violation_length: float = 0.0 # mm of conductor affected
    self_overlaps: int = 0 # same-turn clearance deficits, e.g. at very sharp tips
    worst_self_overlap: float = 0.0 # mm, largest deficit among the self overlaps
    min_width: float = float('nan') # mm, narrowest emitted track
    max_width: float = float('nan') # mm, widest emitted track
    width_error: float = 0.0 # mm, largest deviation of an emitted track width from the intended trace width
    min_spacing_ratio: float = float('nan') # min edge-to-edge distance between turns / clearance
    p5_spacing_ratio: float = float('nan')
    p95_spacing_ratio: float = float('nan') # (spacing + w) / pitch at 95th percentile
    uncovered_fraction: float = float('nan')
    excess_fraction: float = float('nan')
    contour_hausdorff: float = float('nan') # max distance from contour to copper, in pitches
    overshoot: float = float('nan') # mm of copper (tracks, vias, pads) outside the intended envelope
    via_misplacement: float = 0.0 # mm, how far a via center is beyond the intended via offset
    total_length: float = 0.0
    n_segments: int = 0
    notes: list = field(default_factory=list)
    violations: list = field(default_factory=list) # [(layer, point, deficit)]
    crossing_points: list = field(default_factory=list)
    spacing_samples: list = field(default_factory=list) # [(layer, point, ratio)] if requested
    self_overlap_points: list = field(default_factory=list) # [(layer, p, q, deficit, turns apart, path distance)]

    def note(self, msg, limit=40):
        if len(self.notes) < limit:
            self.notes.append(msg)

    def score(self, clearance):
        """ Single scalar badness, 0 is perfect """
        s = 0
        if not self.ok_connectivity:
            s += 1000
        s += 100 * self.crossings
        s += 100 * self.stray_copper
        s += 10 * self.backtracks
        s += 10 * self.worst_clearance_deficit / clearance
        s += 1 * self.worst_via_deficit / clearance
        s += 1 * self.worst_pad_deficit / clearance
        if not math.isnan(self.winding_error):
            s += 100 * min(1, abs(self.winding_error))
        if not math.isnan(self.uncovered_fraction):
            s += 10*self.uncovered_fraction + 10*self.excess_fraction + max(0, self.contour_hausdorff - 1)
        return s

    def width_ok(self, trace_width):
        return self.width_error <= max(WIDTH_TOL_ABS, WIDTH_TOL * trace_width)

    def conformance_ok(self, trace_width=None):
        """ `trace_width` is only accepted for backwards compatibility: the overshoot tolerance is absolute. """
        if math.isnan(self.uncovered_fraction):
            return True
        return (self.uncovered_fraction < 0.05 and self.contour_hausdorff < 1.25
                and self.overshoot < OVERSHOOT_TOL)

    def failure_kinds(self, clearance, trace_width, rel_tol=0.05, vias=True):
        """ Names of the failed checks. passed() is True exactly when this is empty. """
        tol = rel_tol * clearance + 1e-4
        kinds = []
        if not self.ok_connectivity:
            kinds.append('connectivity')
        if self.shorts:
            kinds.append('short')
        if self.stray_vias:
            kinds.append('stray via')
        if self.duplicate_segments:
            kinds.append('duplicate')
        if self.stray_copper:
            kinds.append('stray copper')
        if self.crossings:
            kinds.append('crossing')
        if self.backtracks:
            kinds.append('backtrack')
        if not self.width_ok(trace_width):
            kinds.append('width')
        if self.worst_clearance_deficit > tol:
            kinds.append('clearance')
        if self.worst_pad_deficit > tol:
            kinds.append('pad clearance')
        if vias and self.worst_via_deficit > tol:
            kinds.append('via clearance')
        if vias and self.via_misplacement > OVERSHOOT_TOL:
            kinds.append('via offset')
        if not abs(self.winding_error) < 0.05:
            kinds.append('winding')
        if not self.conformance_ok(trace_width):
            kinds.append('conformance')
        return kinds

    def passed(self, clearance, trace_width, rel_tol=0.05, vias=True):
        return not self.failure_kinds(clearance, trace_width, rel_tol, vias)


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


def _closest_on_seg(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx-ax, by-ay
    l2 = dx*dx + dy*dy
    if l2 == 0:
        return a
    t = max(0, min(1, ((p[0]-ax)*dx + (p[1]-ay)*dy) / l2))
    return (ax + t*dx, ay + t*dy)


def _pt_seg_dist(p, a, b):
    return math.dist(p, _closest_on_seg(p, a, b))


def _seg_seg_closest(a, b, c, d):
    """ Minimum distance between segments ab and cd, and a pair of closest points (on ab, on cd) """
    if _segments_intersect(a, b, c, d):
        x = _intersection_point(a, b, c, d)
        return 0.0, x, x
    best = None
    for p, q in ((a, _closest_on_seg(a, c, d)), (b, _closest_on_seg(b, c, d)),
                 (_closest_on_seg(c, a, b), c), (_closest_on_seg(d, a, b), d)):
        dd = math.dist(p, q)
        if best is None or dd < best[0]:
            best = (dd, p, q)
    return best


def _seg_seg_dist(a, b, c, d):
    """ Minimum distance between segments ab and cd """
    return _seg_seg_closest(a, b, c, d)[0]


def _orient(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def _segments_intersect(a, b, c, d):
    """ Strict crossing test: True only when the segments cross at a single point interior to both. Touching (an
    endpoint lying on the other segment) and collinear overlaps return False; `_seg_seg_closest` reports them as a
    distance of zero, so the clearance check flags them when the two pieces belong to different turns. """
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


def _wrap(a):
    return (a + math.pi) % (2*math.pi) - math.pi


def _parallel(s, t):
    ux, uy = s.b[0]-s.a[0], s.b[1]-s.a[1]
    vx, vy = t.b[0]-t.a[0], t.b[1]-t.a[1]
    lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
    if lu == 0 or lv == 0:
        return False
    return abs(ux*vy - uy*vx) / (lu*lv) < COLLINEAR_TOL


def _on_seg(p, s, tol=ATTACH_TOL):
    return _pt_seg_dist(p, s.a, s.b) < tol


def check_layout(copper: Copper, intent: Intent, sample_step=None, do_conformance=True, max_records=200,
                 keep_samples=False):
    rep = Report()
    layers = tuple(copper.layers)

    # ---- stray copper ----
    for desc in copper.unhandled:
        rep.stray_copper += 1
        rep.note(f'unhandled copper: {desc}')
    for s in copper.segs:
        if s.layer not in layers:
            rep.stray_copper += 1
            rep.note(f'track on {s.layer}, outside the layer pair, at ({s.a[0]:.3f}, {s.a[1]:.3f})')
    pads = [] # [(pad, its copper layers within the layer pair)]
    for pad in copper.pads:
        pl = layers if '*.Cu' in pad.layers else tuple(l for l in pad.layers if l in layers)
        other = [l for l in pad.layers if l not in layers and l != '*.Cu']
        if other:
            rep.stray_copper += 1
            rep.note(f'pad {pad.number} on {",".join(other)}, outside the layer pair')
        if pad.number not in ('1', '2'):
            rep.stray_copper += 1
            rep.note(f'unexpected pad {pad.number!r} at ({pad.x:.3f}, {pad.y:.3f})')
        if pl:
            pads.append((pad, pl))

    segs = [s for s in copper.segs if s.layer in layers]
    rep.n_segments = len(segs)
    rep.degenerate_segments = sum(1 for s in segs if s.length < 1e-6)
    segs = [s for s in segs if s.length >= 1e-6]
    rep.total_length = sum(s.length for s in segs)

    w, clr, pitch = intent.trace_width, intent.clearance, intent.pitch
    if segs:
        rep.min_width = min(s.width for s in segs)
        rep.max_width = max(s.width for s in segs)
        rep.width_error = max(abs(rep.min_width - w), abs(rep.max_width - w))
        if not rep.width_ok(w):
            rep.note(f'track widths {rep.min_width:.4f} to {rep.max_width:.4f} mm, intended {w:.4f} mm')

    contour = Polygon(intent.contour)
    if not contour.is_valid:
        contour = contour.buffer(0)

    geoms = [LineString([s.a, s.b]) for s in segs]
    layer_arr = np.array([s.layer for s in segs])
    tree = STRtree(geoms)
    max_w = max([s.width for s in segs] + [0])

    # ---- connectivity graph ----
    pts = []
    for i, s in enumerate(segs):
        pts.append(((i, 0), s.a))
        pts.append(((i, 1), s.b))
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
    seg_deg = defaultdict(int)
    for i in range(len(segs)):
        seg_deg[node_of[(i, 0)]] += 1
        seg_deg[node_of[(i, 1)]] += 1

    uf = _UnionFind()
    for n in node_pos:
        uf.find(n)

    # Collinear pieces on the same layer. An exact copy of a segment (same end nodes, either direction), or a loose
    # piece (both ends dangling) lying completely on top of another segment, is a duplicate. Two pieces that overlap
    # partially, where each one's dangling end lies on the other, are one track drawn in two pieces. Pieces that fold
    # back onto each other at a common node are left to the backtrack check.
    duplicate = set()
    q_a, q_b = tree.query(geoms, predicate='dwithin', distance=ATTACH_TOL)
    for i, j in zip(q_a, q_b):
        if i >= j or segs[i].layer != segs[j].layer or not _parallel(segs[i], segs[j]):
            continue
        si, sj = segs[i], segs[j]
        shared = {node_of[(i, 0)], node_of[(i, 1)]} & {node_of[(j, 0)], node_of[(j, 1)]}
        j_on_i = _on_seg(sj.a, si) and _on_seg(sj.b, si)
        i_on_j = _on_seg(si.a, sj) and _on_seg(si.b, sj)
        k = j if j_on_i else i
        if (j_on_i or i_on_j) and (len(shared) == 2 or
                                   (not shared and seg_deg[node_of[(k, 0)]] == 1 and seg_deg[node_of[(k, 1)]] == 1)):
            if k not in duplicate:
                duplicate.add(k)
                rep.duplicate_segments += 1
                s = segs[k]
                rep.note(f'duplicate segment on {s.layer} at ({s.a[0]:.3f}, {s.a[1]:.3f})-({s.b[0]:.3f}, {s.b[1]:.3f})')
            continue
        if shared:
            continue
        for ei in (0, 1):
            ni = node_of[(i, ei)]
            if seg_deg[ni] != 1 or not _on_seg(si.b if ei else si.a, sj):
                continue
            for ej in (0, 1):
                nj = node_of[(j, ej)]
                if seg_deg[nj] == 1 and _on_seg(sj.b if ej else sj.a, si):
                    uf.union(ni, nj)
    rdeg = defaultdict(int)
    for n, d in seg_deg.items():
        rdeg[uf.find(n)] += d

    # Vias and pads are copper bodies. They absorb the track nodes at their center and the dangling track ends that lie
    # within their copper.
    bodies = [] # (node id, layers, contains(p), center)
    for j, v in enumerate(copper.vias):
        vn = ('via', j)
        uf.find(vn)
        node_pos[vn] = (v.x, v.y)
        bodies.append((vn, layers, (lambda p, v=v: math.dist(p, (v.x, v.y)) < v.diameter/2), (v.x, v.y)))
    pad_node = defaultdict(list)
    for k, (pad, pl) in enumerate(pads):
        pn = ('pad', k)
        uf.find(pn)
        node_pos[pn] = (pad.x, pad.y)
        pad_node[pad.number].append(pn)
        bodies.append((pn, pl, pad.contains, (pad.x, pad.y)))
    dangling_owner = {}
    track_nodes = [(n, p) for n, p in node_pos.items() if n[0] not in ('via', 'pad')]
    for bn, bl, inside, (bx, by) in bodies:
        for n, p in track_nodes:
            if n[0] not in bl:
                continue
            dd = math.dist(p, (bx, by))
            if dd < JOIN_EPS:
                uf.union(bn, n)
            elif rdeg[uf.find(n)] == 1 and inside(p):
                if n not in dangling_owner or dd < dangling_owner[n][1]:
                    dangling_owner[n] = (bn, dd)
    for n, (bn, _dd) in dangling_owner.items():
        uf.union(bn, n)
    # Vias touching pads, and pads touching pads, on a common layer are connected
    for j, v in enumerate(copper.vias):
        for k, (pad, pl) in enumerate(pads):
            if pad.dist_to_seg((v.x, v.y), (v.x, v.y)) < v.diameter/2:
                uf.union(('via', j), ('pad', k))
    for (k1, (p1, l1)), (k2, (p2, l2)) in itertools.combinations(enumerate(pads), 2):
        if set(l1) & set(l2) and p1.geometry().intersects(p2.geometry()):
            uf.union(('pad', k1), ('pad', k2))

    R = uf.find
    members = defaultdict(list)
    for n in list(uf.parent):
        members[R(n)].append(n)
    rnode_pos = {}
    for r, ms in members.items():
        body = [m for m in ms if m[0] in ('via', 'pad')]
        rnode_pos[r] = node_pos[body[0] if body else ms[0]]

    def body_kind(r):
        kinds = {m[0] for m in members[r]}
        return 'pad' if 'pad' in kinds else 'via' if 'via' in kinds else 'track'

    adj = defaultdict(list) # representative node -> [(other node, length, segment index)]
    for i, s in enumerate(segs):
        if i in duplicate:
            continue
        n1, n2 = R(node_of[(i, 0)]), R(node_of[(i, 1)])
        adj[n1].append((n2, s.length, i))
        adj[n2].append((n1, s.length, i))

    start = {R(n) for n in pad_node.get('1', [])}
    end = {R(n) for n in pad_node.get('2', [])}
    if not start or not end:
        rep.ok_connectivity = False
        rep.reaches_pad2 = False
        rep.note('pad 1 or pad 2 missing')
        return rep
    if start & end:
        rep.shorts += 1
        rep.note('short: pad 1 and pad 2 are connected directly through via or pad copper')
    for r in start | end:
        if not adj[r]:
            rep.note(f'pad {"1" if r in start else "2"} is not attached to any track')

    # Dangling stubs at the terminal pads (e.g. a connection to a via that was replaced by the pads): ugly, but they do
    # not break the circuit. A stub is a dead-end chain of track that starts at a pad and is at most as long as the pad
    # plus the via offset.
    stub_segs = set()
    stub_ends = defaultdict(int)
    for r, nbrs in list(adj.items()):
        if len(nbrs) != 1 or body_kind(r) != 'track':
            continue
        cur, seg = nbrs[0][0], nbrs[0][2]
        chain, length = [seg], segs[seg].length
        while body_kind(cur) == 'track' and len(adj[cur]) == 2:
            nxt = [(m, i) for m, _l, i in adj[cur] if i != seg]
            if not nxt:
                break
            cur, seg = nxt[0]
            chain.append(seg)
            length += segs[seg].length
        if body_kind(cur) != 'pad':
            continue
        extent = max(pads[m[1]][0].extent for m in members[cur] if m[0] == 'pad')
        if length > extent + 3*abs(intent.via_offset or 0) + 1e-6:
            continue
        rep.stubs += 1
        stub_ends[r] += 1
        stub_ends[cur] += 1
        stub_segs.update(chain)

    # Degree check
    check_nodes = dict.fromkeys(list(adj.keys()) + [R(('via', j)) for j in range(len(copper.vias))])
    for r in check_nodes:
        if r in stub_ends and body_kind(r) == 'track' and len(adj[r]) == 1:
            continue # the dangling end of a stub
        deg = len(adj[r]) - stub_ends.get(r, 0)
        kind = body_kind(r)
        x, y = rnode_pos[r]
        if kind == 'pad':
            if deg > 1 and not (r in start and r in end):
                rep.branches += 1
                rep.note(f'pad at ({x:.3f}, {y:.3f}) has {deg} track connections')
        elif kind == 'via':
            if deg < 2:
                rep.stray_vias += 1
                vr = max(copper.vias[m[1]].diameter/2 for m in members[r] if m[0] == 'via')
                attached = {e for _m, _l, e in adj[r]}
                touching = sorted({segs[i].layer for i in tree.query(Point(x, y), predicate='dwithin',
                                                                       distance=vr + max_w/2)
                                   if i not in attached and _pt_seg_dist((x, y), segs[i].a, segs[i].b) <
                                   vr + segs[i].width/2})
                rep.note(f'stray via at ({x:.3f}, {y:.3f}) with {deg} track connections' +
                         (f', its copper touches tracks on {" and ".join(touching)}' if touching else ''))
            elif deg > 2:
                rep.branches += 1
                rep.note(f'via at ({x:.3f}, {y:.3f}) has {deg} track connections')
        else:
            if deg == 1:
                rep.open_ends += 1
                rep.note(f'open end on {r[0]} at ({x:.3f}, {y:.3f})')
            elif deg > 2:
                rep.branches += 1
                rep.note(f'branch (degree {deg}) on {r[0]} at ({x:.3f}, {y:.3f})')

    # Dijkstra from pad 1 to get path positions
    dist = {}
    prev_edge = {}
    counter = itertools.count()
    heap = [(0.0, next(counter), n, None, None) for n in start]
    while heap:
        d, _c, n, pn, pe = heapq.heappop(heap)
        if n in dist:
            continue
        dist[n] = d
        prev_edge[n] = (pn, pe)
        for m, l, e in adj[n]:
            if m not in dist:
                heapq.heappush(heap, (d + l, next(counter), m, n, e))

    rep.reaches_pad2 = any(n in dist for n in end)
    seg_s = np.full(len(segs), np.nan)
    for i, s in enumerate(segs):
        if i in duplicate:
            continue
        d1, d2 = dist.get(R(node_of[(i, 0)])), dist.get(R(node_of[(i, 1)]))
        if d1 is None or d2 is None:
            rep.orphans += 1
            continue
        seg_s[i] = (d1 + d2) / 2

    # The path from pad 1 to pad 2 must use every segment exactly once. If it does not although nothing branches off
    # the path, some copper connects distant parts of the conductor.
    if rep.reaches_pad2 and not (start & end):
        n = min((n for n in end if n in dist), key=lambda n: dist[n])
        on_path = set()
        while prev_edge[n][0] is not None:
            n, e = prev_edge[n]
            on_path.add(e)
        bypassed = [i for i in range(len(segs)) if not np.isnan(seg_s[i]) and i not in on_path and i not in stub_segs]
        if bypassed and rep.branches == 0 and rep.open_ends == 0:
            rep.shorts += 1
            rep.note(f'short: the path from pad 1 to pad 2 bypasses {len(bypassed)} segments '
                     f'({sum(segs[i].length for i in bypassed):.2f} mm)')

    rep.ok_connectivity = (rep.reaches_pad2 and rep.orphans == 0 and rep.branches == 0 and rep.open_ends == 0
                           and rep.stray_vias == 0 and rep.shorts == 0 and rep.duplicate_segments == 0
                           and all(adj[r] for r in start | end))

    # Order segments along the path. theta_a[i] is the cumulative winding angle around the center at the path-earlier
    # end of segment i; it also counts the angle between consecutive track ends (e.g. overlapping pieces).
    order = [i for i in np.argsort(seg_s) if not np.isnan(seg_s[i])]
    oriented = {}
    for i in order:
        s = segs[i]
        n1, n2 = R(node_of[(i, 0)]), R(node_of[(i, 1)])
        oriented[i] = (s.a, s.b, n1, n2) if dist[n1] <= dist[n2] else (s.b, s.a, n2, n1)
    theta_a = np.full(len(segs), np.nan)
    node_theta = {}
    have_center = intent.center is not None
    cx, cy = intent.center if have_center else (0.0, 0.0)

    def ang(p):
        return math.atan2(p[1]-cy, p[0]-cx)

    if have_center and order:
        total = 0.0
        prev_pt = None
        for i in order:
            a, b, n1, n2 = oriented[i]
            if prev_pt is not None:
                total += _wrap(ang(a) - ang(prev_pt))
            theta_a[i] = total
            node_theta.setdefault(n1, total)
            total += _wrap(ang(b) - ang(a))
            node_theta.setdefault(n2, total)
            prev_pt = b
        rep.winding = total / (2*math.pi)
        expected = -intent.turns if intent.clockwise else intent.turns
        rep.winding_error = rep.winding - expected

    def theta_at(i, p):
        """ Cumulative winding angle at point p of segment i """
        if not have_center or np.isnan(theta_a[i]):
            return math.nan
        return theta_a[i] + _wrap(ang(p) - ang(oriented[i][0]))

    # Backtracks: consecutive same-layer segments that reverse direction
    prev = None
    for i in order:
        s = segs[i]
        a, b, _n1, _n2 = oriented[i]
        if prev is not None and prev[0] == s.layer:
            (pa, pb) = prev[1]
            v1 = (pb[0]-pa[0], pb[1]-pa[1])
            v2 = (b[0]-a[0], b[1]-a[1])
            l1, l2 = math.hypot(*v1), math.hypot(*v2)
            if l1 > 0 and l2 > 0:
                cos = (v1[0]*v2[0] + v1[1]*v2[1]) / (l1*l2)
                if cos < -0.985: # > ~170 deg turn
                    rep.backtracks += 1
                    rep.note(f'backtrack on {s.layer} at ({a[0]:.3f}, {a[1]:.3f})')
        prev = (s.layer, (a, b))

    # ---- crossings and clearance ----
    # Copper at least TURN_SEP revolutions apart in cumulative winding angle belongs to different turns. So does copper
    # that is far apart along the conductor path (also the fallback when there is no center).
    inner = _inset(contour, intent.annular_width)
    inner_len = inner.length if not inner.is_empty else contour.length
    s_far = max(4*(w + clr), 0.25 * inner_len)
    # Pieces of the same turn closer than this along the path never count as clearance violations or crossings
    s_near = math.pi/2 * (w + clr)
    turn_sep = TURN_SEP * 2*math.pi

    def other_turn(ds, th1, th2):
        return abs(th1 - th2) >= turn_sep or ds >= s_far

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
        d, p, q = _seg_seg_closest(si.a, si.b, sj.a, sj.b)
        deficit = (si.width + sj.width)/2 + clr - d
        crossing = d == 0.0 and _segments_intersect(si.a, si.b, sj.a, sj.b)
        if deficit <= 1e-4 and not crossing:
            continue
        ds = abs(seg_s[i] - seg_s[j]) - (si.length + sj.length)/2
        far = other_turn(ds, theta_at(i, p), theta_at(j, q))
        if not far and ds < s_near:
            continue
        if crossing:
            rep.crossings += 1
            if len(rep.crossing_points) < max_records:
                rep.crossing_points.append((si.layer, p))
        if deficit > 1e-4:
            if not far:
                rep.self_overlaps += 1
                rep.worst_self_overlap = max(rep.worst_self_overlap, deficit)
                if len(rep.self_overlap_points) < max_records:
                    rep.self_overlap_points.append((si.layer, p, q, deficit,
                                                    abs(theta_at(i, p) - theta_at(j, q)) / (2*math.pi), ds))
                continue
            rep.clearance_violations += 1
            rep.worst_clearance_deficit = max(rep.worst_clearance_deficit, deficit)
            violating_segs.add(i)
            violating_segs.add(j)
            if len(rep.violations) < max_records:
                rep.violations.append((si.layer, ((si.a[0]+si.b[0])/2, (si.a[1]+si.b[1])/2), deficit))

    def body_pos(n):
        """ Path position and winding angle of a via or pad, (None, nan) if it is not on the path """
        r = R(n)
        if r not in dist:
            return None, math.nan
        return dist[r], node_theta.get(r, math.nan)

    def body_seg_far(s_body, th_body, i, p):
        if s_body is None or np.isnan(seg_s[i]):
            return True
        th = theta_at(i, p)
        return other_turn(abs(seg_s[i] - s_body) - segs[i].length/2, th, th_body)

    # vias vs tracks and vias vs vias
    for j, v in enumerate(copper.vias):
        s_via, th_via = body_pos(('via', j))
        for i in tree.query(Point(v.x, v.y), predicate='dwithin', distance=v.diameter/2 + max_w/2 + clr):
            s = segs[i]
            q = _closest_on_seg((v.x, v.y), s.a, s.b)
            if not body_seg_far(s_via, th_via, i, q):
                continue
            deficit = v.diameter/2 + s.width/2 + clr - math.dist((v.x, v.y), q)
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

    # pads vs tracks of other turns, vias and other pads
    def pad_violation(pad, deficit):
        rep.pad_violations += 1
        rep.worst_pad_deficit = max(rep.worst_pad_deficit, deficit)
        if len(rep.violations) < max_records:
            rep.violations.append(('pad', (pad.x, pad.y), deficit))

    for k, (pad, pl) in enumerate(pads):
        s_pad, th_pad = body_pos(('pad', k))
        for i in tree.query(Point(pad.x, pad.y), predicate='dwithin', distance=pad.extent/2 + max_w/2 + clr):
            s = segs[i]
            if s.layer not in pl:
                continue
            q = _closest_on_seg((pad.x, pad.y), s.a, s.b)
            if not body_seg_far(s_pad, th_pad, i, q):
                continue
            deficit = s.width/2 + clr - pad.dist_to_seg(s.a, s.b)
            if deficit > 1e-4:
                violating_segs.add(i)
                pad_violation(pad, deficit)
        for j, v in enumerate(copper.vias):
            if R(('via', j)) in start & end:
                continue # reported as a short
            s_via, th_via = body_pos(('via', j))
            if s_via is not None and s_pad is not None and not other_turn(abs(s_via - s_pad), th_via, th_pad):
                continue
            deficit = v.diameter/2 + clr - pad.dist_to_seg((v.x, v.y), (v.x, v.y))
            if deficit > 1e-4:
                pad_violation(pad, deficit)
        for k2 in range(k+1, len(pads)):
            pad2, pl2 = pads[k2]
            if not set(pl) & set(pl2):
                continue
            deficit = clr - pad.geometry().distance(pad2.geometry())
            if deficit > 1e-4:
                pad_violation(pad, deficit)
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
            th_p = theta_at(i, p)
            best = math.inf
            for j in tree.query(Point(p), predicate='dwithin', distance=2*pitch):
                if j == i or layer_arr[j] != s.layer or np.isnan(seg_s[j]):
                    continue
                q = _closest_on_seg(p, segs[j].a, segs[j].b)
                gap = math.dist(p, q) - (s.width + segs[j].width)/2
                if gap >= best:
                    continue
                if not other_turn(abs(seg_s[j] - sp) - segs[j].length/2, th_p, theta_at(j, q)):
                    continue
                best = gap
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
        _conformance(rep, copper, segs, geoms, [p for p, _pl in pads], intent, contour)

    return rep


def _inset(poly, d):
    return poly.buffer(-d, join_style='mitre', mitre_limit=10)


def _band(contour, outside, depth):
    """ Region from `outside` mm outside the contour to `depth` mm inside it """
    return contour.buffer(outside, join_style='mitre', mitre_limit=10).difference(_inset(contour, depth))


def _conformance(rep, copper, segs, geoms, pads, intent, contour):
    """ Compare the copper area with the intended annulus.

    A spiral only touches the outer contour where an arm starts, and only reaches the inner contour where an arm ends.
    In between, the outermost track sits up to one pitch inside the contour. The checks therefore use three regions:

        core      Depths [pitch/2, annular - pitch/2] from the contour. Every layer must cover this completely when
                  its tracks are inflated by half a pitch. Uncovered area here means wasted space (loose spacing, a
                  missing turn, a collapsed region).
        envelope  Depths [-w/2, annular + w/2]. No copper (tracks, vias, pads) may leave this region (overshoot,
                  excess), except around vias: via centers may sit up to the intended via offset (three times that
                  with staggered vias) outside the contour or inside the inner contour, and near a via, its copper and
                  the copper of the tracks leading to it may extend into the band that a via at that offset covers.
        contour   Every point of the outer contour must be within one pitch of copper on some layer (undershoot).
    """
    w, p = intent.trace_width, intent.pitch
    tol = 1e-3
    core = _inset(contour, p/2).difference(_inset(contour, intent.annular_width - p/2))
    env = _band(contour, w/2 + tol, intent.annular_width + w/2 + tol)
    uncovered = []
    all_copper = []

    via_reach = abs(intent.via_offset or 0) * (3 if intent.via_stagger else 1)
    if copper.vias:
        via_band = _band(contour, via_reach + tol, intent.annular_width + via_reach + tol)
        rep.via_misplacement = float(shapely.distance(shapely.points([(v.x, v.y) for v in copper.vias]),
                                                      via_band).max())
        vd = max([v.diameter for v in copper.vias] + [w])
        ext = via_reach + vd/2 + tol
        # The track from the arm end to the via runs along the skeleton, which at sharp corners is longer than the via
        # offset. Allow three times the offset around the via.
        zone_r = vd/2 + w/2 + 3*via_reach + tol
        zones = shapely.unary_union([Point(v.x, v.y).buffer(zone_r) for v in copper.vias])
        env = env.union(_band(contour, ext, intent.annular_width + ext).intersection(zones))
        if rep.via_misplacement > OVERSHOOT_TOL:
            rep.note(f'a via center is {rep.via_misplacement:.3f} mm beyond the intended via offset of '
                     f'{via_reach:.3f} mm')

    for li, layer in enumerate(copper.layers):
        idx = [i for i, s in enumerate(segs) if s.layer == layer]
        if not idx:
            continue
        lines = [geoms[i] for i in idx]
        if core.area > 0 and li < intent.spiral_layers:
            loose = shapely.unary_union(shapely.buffer(lines, p/2 * 1.001, quad_segs=4))
            uncovered.append(core.difference(loose).area / core.area)
        widths = np.array([segs[i].width for i in idx])
        all_copper.append(shapely.unary_union(shapely.buffer(lines, widths/2, quad_segs=4)))
    if not all_copper:
        return
    all_copper += [Point(v.x, v.y).buffer(v.diameter/2, quad_segs=8) for v in copper.vias]
    all_copper += [pad.geometry(quad_segs=8) for pad in pads]
    cu = shapely.unary_union(all_copper)
    rep.uncovered_fraction = max(uncovered) if uncovered else 0.0
    ring = _inset(contour, 0).difference(_inset(contour, intent.annular_width))
    rep.excess_fraction = cu.difference(env).area / max(ring.area, 1e-9)
    # undershoot: distance from the contour to the nearest copper, in units of pitch
    pts = shapely.points(shapely.get_coordinates(shapely.segmentize(contour.exterior, p/4)))
    rep.contour_hausdorff = float(shapely.distance(pts, cu).max()) / p
    # overshoot: distance of copper beyond the envelope in mm
    bpts = shapely.points(shapely.get_coordinates(shapely.segmentize(cu.boundary, p/4)))
    bd = shapely.distance(bpts, env)
    rep.overshoot = float(bd.max())
    if rep.overshoot >= OVERSHOOT_TOL:
        x, y = shapely.get_coordinates(bpts[int(bd.argmax())])[0]
        rep.note(f'copper {rep.overshoot:.3f} mm outside the intended envelope at ({x:.3f}, {y:.3f})')


def intent_from_model(model, contour_tol=0.01):
    """ Derive the intended geometry from a kicoil PlanarInductor object. This only uses the user-facing parameters
    (shape outline, annular width, turns, trace width, clearance, via diameter, offset and staggering), not any internal
    layout state. Attributes an alternative implementation lacks fall back to the base implementation's defaults. """
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

    w = model.trace_width
    via_diameter = getattr(model, 'via_diameter', None) or w
    via_offset = getattr(model, 'via_offset', None)
    if via_offset is None:
        via_offset = max(0.0, (via_diameter - w)/2)
    stagger = bool(getattr(model, 'stagger_inner_vias', False) or getattr(model, 'stagger_outer_vias', False))
    return Intent(contour=contour, annular_width=annular, turns=model.turns, trace_width=w,
                  clearance=model.clearance, pitch=w + model.clearance, center=center,
                  clockwise=model.clockwise, spiral_layers=getattr(model, 'layers', 2),
                  via_diameter=via_diameter, via_offset=abs(via_offset), via_stagger=stagger)
