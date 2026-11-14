"""Variable-width ("tapered") traces for laid-out kicoil coils.

The layout modules size one trace width for the whole coil from the narrowest gap between neighboring turns. Most of the
conductor has more room than that. This module takes a laid-out `PlanarInductor` (from `kicoil.geometry` or one of the
alternative layout modules), treats its spiral center lines as infinitely thin conductors and grows every piece of trace
as wide as the local free space allows, keeping the specified clearance to the copper of other turns, to vias and to
pads. Copper of the same turn may merge. The goal is the lowest DC resistance, i.e. the smallest sum of length/width.

Width model
-----------
The center lines are cut into pieces of at most `piece_length`. Every vertex v gets a width w_v; a piece from vertex a to
vertex b is a trace whose width changes linearly from w_a to w_b. Whatever copper is emitted for a piece lies inside the
"capsule" around its center line with the radius max(w_a, w_b)/2 (shown below for both representations). So two pieces k
and m of different turns keep the clearance when

    max(w_a, w_b)/2 + max(w_c, w_d)/2 <= dist(k, m) - clearance

i.e. when w_x + w_y <= 2 (dist(k, m) - clearance) for every end x of k and every end y of m. This is a set of linear
constraints on the vertex widths ("each conductor takes half of the gap" is one feasible point of it). Vias and pads of
other turns and the envelope of the coil (the outline grown by half the constant trace width, the inner contour shrunk by
the same, plus the via and pad copper and the connections to them) give upper bounds per vertex. The widths start at the
symmetric split, and are then grown one vertex at a time, narrowest first, into whatever room the constraints leave
(which uses up gaps whose other side is held back by a different neighbor). Widths are rounded down to `quantum`.

Representations
---------------
'v'     A tapered piece is drawn as two straight tracks of the narrow width w_n, sharing the narrow end point and diverging
        to the two sides of the wide end: the ends are the wide end point +- n (w_w - w_n)/2, n the unit normal. The
        round caps at the wide end lie inside the circle of radius w_w/2 around the wide end point, so the union is
        inside the piece's capsule. The union covers the trapezoid when w_w <= 2 w_n (the two tracks' copper overlaps
        all the way); longer tapers are split. These are plain tracks and export to Gerber as lines with round
        apertures.
'poly'  A tapered piece is a filled 4-point copper polygon (fp_poly, no outline stroke): the trapezoid with the end
        widths, ends perpendicular to the center line. Where two trapezoids meet at a bend, a filled copper circle of the
        vertex width closes the notch on the outside of the bend. Pieces of constant width are tracks in both
        representations.

Coordinates are rounded to 1 nm (KiCad's resolution), and the side offsets are rounded, not the end points, so the wide
end point is exactly the midpoint of a V's two end points and of a trapezoid's end edge.

The emitted copper is checked again exactly (shapely distances between the real primitives: the round-capped tracks,
polygons and circles) for clearance between different turns, see `TaperResult.verify`.
"""

import time
import math
import warnings
from dataclasses import dataclass, field
from math import pi, dist, inf, ceil, floor, log2

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon

from gerbonara.cad.kicad.footprints import Polygon as FpPolygon, Circle as FpCircle, XYCoord, Atom

from . import kicad
from .geometry import _seg_seg_distance_np, _point_seg_distance_np

NM = 1e-6 # mm, coordinate resolution of the emitted footprint
MIN_TAPER = 1e-4 # mm, pieces whose end widths differ less than this are emitted with constant width (the smaller)
MAX_PIECE_TURN = 0.04 # revolutions of winding angle per piece at most
TURN_SEP = 0.5 # revolutions; copper this far apart in winding angle belongs to different turns


@dataclass
class TaperOptions:
    min_width: float = None # mm; default: the clearance, at least 0.1 mm. Never more than the constant trace width.
    max_width: float = None # mm; default: no limit other than the free space
    piece_length: float = None # mm; default: half the nominal pitch
    quantum: float = 0.005 # mm, widths are rounded down to multiples of this
    balance: bool = True # grow widths into room left over by the symmetric split
    joint_angle: float = 2.0 # degrees; trapezoid joints bent more than this get a circle (polygon representation)
    max_v_ratio: float = 2.0 # wide / narrow width of one V; longer tapers are split
    width_tol: float = 0.03 # relative undercut allowed when merging pieces of a straight run into one taper
    arm_angle_turns: bool = False # also separate turns by the arm angle parameter (stricter than geomcheck)
    simplify: float = 0.0 # simplify the center lines (Douglas-Peucker) to this fraction of the clearance; 0: off. This
    # moves turns closer by up to twice the tolerance, which narrows the traces where the constant width layout is tight


@dataclass
class Conductor:
    layer: int # index into the layer pair
    pts: np.ndarray # (n, 2) center line, outer end first
    theta: np.ndarray # (n,) arm angle parameter in revolutions
    phi: np.ndarray # (n,) cumulative geometric winding angle around the coil center in revolutions
    s: np.ndarray # (n,) path length from the start of this conductor
    vidx: np.ndarray = None # (n,) global vertex index


@dataclass
class Body:
    kind: str # 'via' or 'pad'
    x: float
    y: float
    diameter: float
    layers: tuple # layer indices
    owners: list # [(conductor index, theta, phi, s)] for the conductors that end at this body


@dataclass
class TaperResult:
    model: object
    options: TaperOptions
    w0: float # constant trace width of the model
    clearance: float
    conductors: list
    bodies: list
    widths: np.ndarray # per vertex
    allowed: np.ndarray # per vertex, before flooring at the minimum width
    lo: float
    hi: float
    forced: int # vertices whose free space is below the minimum width
    unresolved: int # vertex pairs that still violate a constraint (only where the constant layout did too)
    r_const: float # DC resistance / sheet resistance of the constant width layout (same center lines)
    r_taper: float # DC resistance / sheet resistance of the vertex width profile (before merging into spans)
    length: float
    time: float
    base_footprint: object = None
    envelope: object = None
    ring: object = None
    _layers: tuple = None

    @property
    def gain(self):
        """ Conductance gain: constant-width resistance / tapered resistance (emitted profile) """
        return self.r_const / self.resistance()

    @property
    def min_width(self):
        return float(self.widths.min())

    def pieces(self):
        """ Yield (layer, p, q, wp, wq, conductor index, theta_p, theta_q, s_p, s_q) per piece """
        for ci, c in enumerate(self.conductors):
            w = self.widths[c.vidx]
            for k in range(len(c.pts) - 1):
                yield (c.layer, c.pts[k], c.pts[k+1], w[k], w[k+1], ci, c.theta[k], c.theta[k+1], c.s[k], c.s[k+1])

    # ---- emission ----

    def spans(self):
        """ The emitted width profile: per conductor a list of spans (k0, k1, w0, w1) over the vertices k0..k1, which lie
        on a straight line, with the width changing linearly from w0 to w1. Within a straight run of pieces, the profile
        follows the vertex widths from below, with at most `width_tol` (relative, at least one quantum) of undercut,
        using as few spans as a greedy pass finds. Every span stays below the vertex widths, so it keeps the clearance.
        """
        if getattr(self, '_spans', None) is not None:
            return self._spans
        out = []
        q = self.options.quantum or 0.0
        rel = self.options.width_tol
        for c in self.conductors:
            w = self.widths[c.vidx]
            s = c.s
            pts = c.pts
            n = len(pts)
            spans = []
            i = 0
            while i < n - 1:
                j = i + 1
                best = j
                while j < n:
                    if j > i + 1 and not _collinear(pts[i], pts[j-1], pts[j], tol=1e-7):
                        break
                    ks = np.arange(i + 1, j)
                    if len(ks):
                        f = (s[ks] - s[i]) / (s[j] - s[i])
                        line = w[i] + f * (w[j] - w[i])
                        tol = np.maximum(q, rel * w[ks])
                        if np.any(line > w[ks] + 1e-12) or np.any(line < w[ks] - tol):
                            break
                    best = j
                    j += 1
                spans.append((i, best, float(w[i]), float(w[best])))
                i = best
            out.append(spans)
        self._spans = out
        return out

    def primitives(self, style='v'):
        """ Copper primitives of the tapered layout, as dicts with keys kind ('line', 'poly' or 'circle'), layer (index),
        geometry data, and the owner (conductor, center line ends, theta, phi and s ranges) used for the clearance
        verification. """
        prims = []
        lim = math.radians(self.options.joint_angle)
        for ci, (c, spans) in enumerate(zip(self.conductors, self.spans())):
            pts = [_round_pt(p) for p in c.pts]
            kinds = []
            for k0, k1, wp, wq in spans:
                p, q = pts[k0], pts[k1]
                own = (ci, p, q, c.theta[k0], c.theta[k1], c.phi[k0], c.phi[k1], c.s[k0], c.s[k1])
                if abs(wp - wq) < MIN_TAPER:
                    wp = wq = min(wp, wq)
                    prims.append(dict(kind='line', layer=c.layer, a=p, b=q, width=_round_down(min(wp, wq)), owner=own))
                    kinds.append('line')
                elif style == 'v':
                    prims.extend(_v_taper(p, q, wp, wq, c.layer, own, self.options.max_v_ratio))
                    kinds.append('v')
                else:
                    prims.append(_trapezoid(p, q, wp, wq, c.layer, own))
                    kinds.append('poly')
            if style == 'poly':
                # Close the notch on the outside of bends between two trapezoids
                for (a0, k, _w0, wk), (_k, b1, _w2, _w3), ka, kb in zip(spans, spans[1:], kinds, kinds[1:]):
                    if ka == 'poly' and kb == 'poly' and _bend(pts[a0], pts[k], pts[b1]) > lim:
                        own = (ci, pts[k], pts[k], c.theta[k], c.theta[k], c.phi[k], c.phi[k], c.s[k], c.s[k])
                        prims.append(dict(kind='circle', layer=c.layer, center=pts[k], diameter=_round_down(wk),
                                          owner=own))
        return prims

    def resistance(self):
        """ DC resistance per unit sheet resistance of the emitted profile (1D integral over the trapezoids) """
        r = 0.0
        for c, spans in zip(self.conductors, self.spans()):
            for k0, k1, wp, wq in spans:
                L = c.s[k1] - c.s[k0]
                if abs(wq - wp) < MIN_TAPER:
                    r += L / min(wp, wq)
                else:
                    r += L * math.log(wq / wp) / (wq - wp)
        return r

    def footprint(self, style='v', name=None):
        """ KiCad footprint with the tapered copper. Pads, vias, keepout zone and metadata are those of the model's own
        footprint. """
        import copy
        fp = copy.deepcopy(self.base_footprint)
        if name:
            fp.name = name
        fp.lines = [l for l in fp.lines if l.layer not in self._layers]
        fp.arcs = [a for a in fp.arcs if a.layer not in self._layers]
        for p in self.primitives(style):
            layer = self._layers[p['layer']]
            if p['kind'] == 'line':
                fp.lines.append(kicad.make_line(*p['a'], *p['b'], p['width'], layer))
            elif p['kind'] == 'poly':
                fp.polygons.append(FpPolygon(pts=[XYCoord(x=x, y=y) for x, y in p['pts']],
                                             layer=layer, width=0.0, stroke=None, fill=Atom.solid))
            else:
                x, y = p['center']
                fp.circles.append(FpCircle(center=XYCoord(x=x, y=y), end=XYCoord(x=_rnd(x + p['diameter']/2), y=y),
                                           layer=layer, width=0.0, stroke=None, fill=Atom.solid))
        fp.descr = (fp.descr or '') + f' Tapered traces ({style}), {self.min_width:.3f} to {float(self.widths.max()):.3f} mm.'
        return fp

    def piece_intent(self):
        """ The emitted width profile as [(layer name, p, q, wp, wq)] per straight span, for geomcheck's per-piece width
        check (Intent.piece_widths) """
        out = []
        for c, spans in zip(self.conductors, self.spans()):
            for k0, k1, wp, wq in spans:
                if abs(wp - wq) < MIN_TAPER:
                    wp = wq = min(wp, wq)
                out.append((self._layers[c.layer], _round_pt(c.pts[k0]), _round_pt(c.pts[k1]), wp, wq))
        return out

    # ---- verification and metrics ----

    def verify(self, style='v', prims=None):
        """ Exact clearance check of the emitted copper: smallest edge-to-edge distance between primitives of different
        turns (same layer), and between primitives and vias/pads of other turns. Returns (smallest gap - clearance,
        where); inf when nothing of another turn is closer than twice the clearance. """
        prims = self.primitives(style) if prims is None else prims
        cores, radii, owners, layers = [], [], [], []
        for p in prims:
            if p['kind'] == 'line':
                cores.append(LineString([p['a'], p['b']]) if p['a'] != p['b'] else Point(p['a']))
                radii.append(p['width'] / 2)
            elif p['kind'] == 'poly':
                cores.append(Polygon(p['pts']))
                radii.append(0.0)
            else:
                cores.append(Point(p['center']))
                radii.append(p['diameter'] / 2)
            owners.append(p['owner'])
            layers.append(p['layer'])
        cores = np.array(cores, dtype=object)
        radii = np.array(radii)
        layers = np.array(layers)
        tree = shapely.STRtree(cores)
        reach = float(radii.max()) if len(radii) else 0.0
        s_far = self._s_far()
        arm = self.options.arm_angle_turns
        worst, where = inf, None
        ia, ib = tree.query(cores, predicate='dwithin', distance=2*reach + self.clearance)
        sel = (ia < ib) & (layers[ia] == layers[ib])
        ia, ib = ia[sel], ib[sel]
        if len(ia):
            d = shapely.distance(cores[ia], cores[ib]) - radii[ia] - radii[ib]
            close = d < 2 * self.clearance
            for i, j, g in zip(ia[close], ib[close], d[close]):
                x, y = shapely.get_coordinates(shapely.shortest_line(cores[i], cores[j]))
                if not _different_turn_at(_owner_at(owners[i], x), _owner_at(owners[j], y), s_far, arm):
                    continue
                if g - self.clearance < worst:
                    worst, where = g - self.clearance, tuple(x)
        for b in self.bodies:
            bp = Point(b.x, b.y)
            for i in tree.query(bp, predicate='dwithin', distance=b.diameter/2 + reach + self.clearance):
                if layers[i] not in b.layers:
                    continue
                g = shapely.distance(cores[i], bp) - radii[i] - b.diameter/2
                if g >= 2 * self.clearance:
                    continue
                x = shapely.get_coordinates(shapely.shortest_line(cores[i], bp))[0]
                o = _owner_at(owners[i], x)
                if not all(_different_turn_at(o, (bo[0], bo[1], bo[2], (bo[3], bo[3])), s_far, arm)
                           for bo in b.owners):
                    continue
                if g - self.clearance < worst:
                    worst, where = g - self.clearance, (b.x, b.y)
        return worst, where

    def _s_far(self):
        inner_len = self.ring_inner_length
        return 0.9 * max(4 * (self.w0 + self.clearance), 0.25 * inner_len)

    def copper_union(self, style=None):
        """ Copper area per layer (shapely geometry), including vias and pads. style None: the constant-width layout. """
        out = []
        for li in range(len(self._layers)):
            geoms = []
            if style is None:
                for c in self.conductors:
                    if c.layer == li:
                        geoms.append(LineString(c.pts).buffer(self.w0/2, quad_segs=8))
            else:
                for p in self.primitives(style):
                    if p['layer'] != li:
                        continue
                    if p['kind'] == 'line':
                        geoms.append(LineString([p['a'], p['b']]).buffer(p['width']/2, quad_segs=8))
                    elif p['kind'] == 'poly':
                        geoms.append(Polygon(p['pts']))
                    else:
                        geoms.append(Point(p['center']).buffer(p['diameter']/2, quad_segs=8))
            geoms += [Point(b.x, b.y).buffer(b.diameter/2, quad_segs=8) for b in self.bodies if li in b.layers]
            out.append(shapely.unary_union(geoms))
        return out

    def fill_fraction(self, style=None):
        """ Mean over the spiral layers of the fraction of the annulus (outline to inner contour) covered by copper """
        fr = []
        for li, cu in enumerate(self.copper_union(style)):
            if li >= max(1, getattr(self.model, 'layers', 2)):
                continue
            fr.append(cu.intersection(self.ring).area / self.ring.area)
        return float(np.mean(fr))

    def stats(self):
        out = {}
        for style in ('v', 'poly'):
            prims = self.primitives(style)
            out[style] = dict(lines=sum(p['kind'] == 'line' for p in prims),
                              polys=sum(p['kind'] == 'poly' for p in prims),
                              circles=sum(p['kind'] == 'circle' for p in prims))
        return out


# ---------------------------------------------------------------------------------------------------------------------


def _rnd(x):
    return round(float(x) / NM) * NM


def _round_pt(p):
    return (_rnd(p[0]), _rnd(p[1]))


def _round_down(w):
    return math.floor(float(w) / NM + 1e-6) * NM


def _collinear(a, b, c, tol=1e-9):
    ux, uy = b[0]-a[0], b[1]-a[1]
    vx, vy = c[0]-b[0], c[1]-b[1]
    lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
    if lu == 0 or lv == 0:
        return True
    return abs(ux*vy - uy*vx) / (lu*lv) < tol and ux*vx + uy*vy > 0


def _bend(a, b, c):
    ux, uy = b[0]-a[0], b[1]-a[1]
    vx, vy = c[0]-b[0], c[1]-b[1]
    return abs(math.atan2(ux*vy - uy*vx, ux*vx + uy*vy))


def _normal(p, q):
    dx, dy = q[0]-p[0], q[1]-p[1]
    l = math.hypot(dx, dy)
    return (-dy/l, dx/l)


def _v_taper(p, q, wp, wq, layer, own, max_ratio=2.0):
    """ Tracks of a V taper from p (width wp) to q (width wq), split so that each V widens by at most max_ratio """
    if wp > wq:
        p, q, wp, wq = q, p, wq, wp
        own = (own[0], own[2], own[1], own[4], own[3], own[6], own[5], own[8], own[7])
    # widths along the piece at the split points: geometric progression
    m = max(1, ceil(log2(wq / wp) / log2(max_ratio) - 1e-9))
    ws = [wp * (wq / wp) ** (i / m) for i in range(m + 1)]
    ws[0], ws[-1] = wp, wq
    out = []
    nx, ny = _normal(p, q)
    prev = p
    for i in range(m):
        t = (ws[i+1] - wp) / (wq - wp)
        end = q if i == m - 1 else _round_pt((p[0] + t*(q[0]-p[0]), p[1] + t*(q[1]-p[1])))
        wn = _round_down(ws[i])
        ww = ws[i+1] if i == m - 1 else _round_down(ws[i+1])
        h = (ww - wn) / 2
        # offsets rounded towards zero: the round caps stay inside the circle of radius ww/2 around the wide end
        o = (math.trunc(nx*h/NM)*NM, math.trunc(ny*h/NM)*NM)
        e1 = (end[0] + o[0], end[1] + o[1])
        e2 = (end[0] - o[0], end[1] - o[1])
        out.append(dict(kind='line', layer=layer, a=prev, b=_round_pt(e1), width=wn, owner=own))
        out.append(dict(kind='line', layer=layer, a=prev, b=_round_pt(e2), width=wn, owner=own))
        prev = end
    return out


def _trapezoid(p, q, wp, wq, layer, own):
    nx, ny = _normal(p, q)
    hp, hq = _round_down(wp) / 2, _round_down(wq) / 2
    op = (math.trunc(nx*hp/NM)*NM, math.trunc(ny*hp/NM)*NM)
    oq = (math.trunc(nx*hq/NM)*NM, math.trunc(ny*hq/NM)*NM)
    pts = [(p[0]+op[0], p[1]+op[1]), (q[0]+oq[0], q[1]+oq[1]), (q[0]-oq[0], q[1]-oq[1]), (p[0]-op[0], p[1]-op[1])]
    return dict(kind='poly', layer=layer, pts=[_round_pt(x) for x in pts], owner=own)


def _owner_at(o, x):
    """ (conductor, theta, phi, s interval) of owner range o = (conductor, a, b, theta range, phi range, s range) at
    the point of its center line a-b closest to x. The path position is kept as the piece's interval: geomcheck measures
    path distances between pieces as the gap between their intervals. """
    ci, a, b = o[0], o[1], o[2]
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx*dx + dy*dy
    t = 0.0 if l2 == 0 else min(1.0, max(0.0, ((x[0] - a[0])*dx + (x[1] - a[1])*dy) / l2))
    return (ci, o[3] + t*(o[4] - o[3]), o[5] + t*(o[6] - o[5]), (min(o[7], o[8]), max(o[7], o[8])))


def _interval_gap(a, b):
    return max(0.0, a[0] - b[1], b[0] - a[1])


def _different_turn_at(o1, o2, s_far, arm=False):
    """ Like _different_turn at single points (conductor, theta, phi, s interval) """
    return (o1[0] != o2[0] or (arm and abs(o1[1] - o2[1]) >= TURN_SEP) or abs(o1[2] - o2[2]) >= TURN_SEP
            or _interval_gap(o1[3], o2[3]) >= s_far)


def _different_turn(o1, o2, s_far, arm=False):
    """ Owners (conductor, theta range, phi range, s range): copper of different conductors always belongs to different
    turns; on the same conductor, when it is half a revolution apart in winding angle around the coil center (largest
    difference; with arm=True also in the arm's angle parameter) or far apart along the path (gap between the path
    intervals). This follows geomcheck's definition, with the largest instead of the local winding difference, and 0.9
    times its path distance. """
    if o1[0] != o2[0]:
        return True
    th = max(abs(o1[1] - o2[1]), abs(o1[1] - o2[2]), abs(o1[2] - o2[1]), abs(o1[2] - o2[2]))
    ph = max(abs(o1[3] - o2[3]), abs(o1[3] - o2[4]), abs(o1[4] - o2[3]), abs(o1[4] - o2[4]))
    ds = _interval_gap((min(o1[5], o1[6]), max(o1[5], o1[6])), (min(o2[5], o2[6]), max(o2[5], o2[6])))
    return (arm and th >= TURN_SEP) or ph >= TURN_SEP or ds >= s_far


def _douglas_peucker(P, tol):
    """ Indices of the points of polyline P kept by Douglas-Peucker simplification with tolerance tol """
    n = len(P)
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = P[i], P[j]
        mid = P[i+1:j]
        d = _point_seg_distance_np(mid, np.broadcast_to(a, mid.shape), np.broadcast_to(b, mid.shape))
        k = int(np.argmax(d))
        if d[k] > tol:
            m = i + 1 + k
            keep[m] = True
            stack.append((i, m))
            stack.append((m, j))
    return np.flatnonzero(keep)


def _contour(model):
    """ Outline polygon (CCW) and annular width of the model's shape """
    shape = model.shape
    if hasattr(shape, 'polygon'):
        poly = Polygon(shape.polygon)
        annular = shape.annular_width
    else:
        r = shape.outer_radius
        n = max(64, ceil(pi / math.acos(1 - 0.001/r)))
        poly = Polygon([(r*math.cos(2*pi*i/n), r*math.sin(2*pi*i/n)) for i in range(n)])
        annular = shape.outer_radius - shape.inner_radius
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly, annular


def _inset(poly, d):
    return poly.buffer(-d, join_style='mitre', mitre_limit=10)


def _winding(pts, center):
    a = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    da = np.diff(a)
    da = (da + pi) % (2*pi) - pi
    return np.concatenate([[0.0], np.cumsum(da)]) / (2*pi)


def _conductors(model, fp, piece_length, simplify_tol=0.0):
    """ Conductors (spiral arms with their connections to vias and pads, outer end first) and copper bodies (vias, pads)
    of a laid-out model, cut into pieces of at most piece_length. """
    arms = model.spiral_center_lines()
    inner_vias, outer_vias = model.via_positions()
    layers = 2 if getattr(model, 'layers', 2) > 1 else 1
    twists = model.twists
    raw = [] # (layer, pts, theta)
    for i in range(twists):
        _start, fold, _end = model.arm_angles(i)
        pts, th = arms[0][i]
        pts, th = [tuple(p) for p in pts], list(th)
        if i > 0:
            pts, th = [tuple(outer_vias[i-1])] + pts, [th[0]] + th
        pts, th = pts + [tuple(inner_vias[i])], th + [th[-1]]
        raw.append((0, pts, th))
    if layers > 1:
        for j in range(twists):
            pts, th = arms[1][j]
            pts, th = [tuple(p) for p in pts], list(th)
            i = (j + model.turns) % twists
            if i > 0:
                pts, th = [tuple(outer_vias[i-1])] + pts, [th[0]] + th
            pts, th = pts + [tuple(inner_vias[j])], th + [th[-1]]
            raw.append((1, pts, th))
    else:
        # single layer: return strap on the second layer from the inner via to the outline
        _start, fold, _end = model.arm_angles(0)
        xn = arms[0][0][0][-1]
        xq = model.shape.project_point(model.shape.outer_radius, fold)
        t = fold / (2*pi)
        raw.append((1, [tuple(xq), tuple(xn), tuple(inner_vias[0])], [t, t, t]))

    contour, annular = _contour(model)
    inner = _inset(contour, annular * 1.02)
    if inner.is_empty:
        inner = _inset(contour, annular * 0.98)
    if inner.is_empty:
        center = contour.representative_point().coords[0]
    else:
        if not isinstance(inner, Polygon):
            inner = max(inner.geoms, key=lambda g: g.area)
        center = inner.representative_point().coords[0]

    conductors = []
    for layer, pts, th in raw:
        P = np.array(pts, dtype=float)
        T = np.array(th, dtype=float)
        keep = np.concatenate([[True], np.hypot(*np.diff(P, axis=0).T) > 1e-9])
        P, T = P[keep], T[keep]
        if simplify_tol:
            keep = _douglas_peucker(P, simplify_tol)
            P, T = P[keep], T[keep]
        out_p, out_t = [P[0]], [T[0]]
        for k in range(len(P) - 1):
            L = dist(P[k], P[k+1])
            # at most piece_length long, and at most MAX_PIECE_TURN revolutions of winding angle (the turn separation
            # uses the largest winding angle difference between two pieces, so long pieces would be over-constrained)
            a0 = math.atan2(P[k][1] - center[1], P[k][0] - center[0])
            a1 = math.atan2(P[k+1][1] - center[1], P[k+1][0] - center[0])
            sweep = abs((a1 - a0 + pi) % (2*pi) - pi) / (2*pi)
            m = max(1, ceil(L / piece_length - 1e-9), ceil(sweep / MAX_PIECE_TURN - 1e-9))
            for q in range(1, m + 1):
                f = q / m
                out_p.append(P[k] + f * (P[k+1] - P[k]))
                out_t.append(T[k] + f * (T[k+1] - T[k]))
        P, T = np.array(out_p), np.array(out_t)
        S = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(P, axis=0).T))])
        conductors.append(Conductor(layer, P, T, _winding(P, center), S))

    # Vias and pads from the model's footprint, owned by the conductors that end at them
    layer_names = list(model.layer_pair) if isinstance(model.layer_pair, tuple) else \
        [l.strip() for l in model.layer_pair.split(',')]
    bodies = []
    for pad in fp.pads:
        cu = tuple(i for i, l in enumerate(layer_names) if l in pad.layers or '*.Cu' in pad.layers)
        if not cu:
            continue
        is_via = bool(pad.drill and pad.drill.diameter) and str(pad.number) in ('', 'NC')
        x, y = pad.at.x, pad.at.y
        owners = []
        for ci, c in enumerate(conductors):
            for k in (0, len(c.pts) - 1):
                if c.layer in cu and math.hypot(c.pts[k][0] - x, c.pts[k][1] - y) < 1e-6:
                    owners.append((ci, c.theta[k], c.phi[k], c.s[k]))
        bodies.append(Body('via' if is_via else 'pad', x, y, max(pad.size.x, pad.size.y), cu, owners))
    for ci, c in enumerate(conductors):
        for k in (0, len(c.pts) - 1):
            if not any(o[0] == ci and o[3] == c.s[k] for b in bodies for o in b.owners):
                raise ValueError(f'conductor {ci} end at {tuple(c.pts[k])} is not at a via or pad')
    return conductors, bodies, contour, annular, center, layer_names


def taper_layout(model, options=None, **kw):
    """ Compute tapered trace widths for a laid-out PlanarInductor. Returns a TaperResult. """
    t0 = time.perf_counter()
    opt = options or TaperOptions(**kw)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        fp = model.render_footprint()
    w0, clr = model.trace_width, model.clearance
    pitch = model.spiral_pitch
    h = opt.piece_length or pitch / 2
    lo = min(opt.min_width if opt.min_width is not None else max(clr, 0.1), w0)
    conductors, bodies, contour, annular, center, layer_names = _conductors(
        model, fp, h, clr * opt.simplify if opt.simplify else 0.0)

    # global vertex numbering
    nv = 0
    for c in conductors:
        c.vidx = np.arange(nv, nv + len(c.pts))
        nv += len(c.pts)

    # pieces
    PA, PB, VA, VB, CI, LY = [], [], [], [], [], []
    TH, PH, SS = [], [], []
    for ci, c in enumerate(conductors):
        PA.append(c.pts[:-1]); PB.append(c.pts[1:])
        VA.append(c.vidx[:-1]); VB.append(c.vidx[1:])
        CI.append(np.full(len(c.pts) - 1, ci)); LY.append(np.full(len(c.pts) - 1, c.layer))
        TH.append(np.stack([c.theta[:-1], c.theta[1:]], 1)); PH.append(np.stack([c.phi[:-1], c.phi[1:]], 1))
        SS.append(np.stack([c.s[:-1], c.s[1:]], 1))
    PA, PB, VA, VB, CI, LY = map(np.concatenate, (PA, PB, VA, VB, CI, LY))
    TH, PH, SS = map(np.concatenate, (TH, PH, SS))
    npieces = len(PA)

    # envelope: outline grown by w0/2, inner contour shrunk by w0/2, plus vias, pads
    env = contour.buffer(w0/2, quad_segs=32).difference(_inset(contour, annular + w0/2))
    extra = [Point(b.x, b.y).buffer(b.diameter/2, quad_segs=32) for b in bodies]
    # and the copper of the constant width layout itself (where it leaves the band, e.g. the connections to the vias, or
    # turns cutting across a narrow part of the outline), so that nothing is narrowed below the constant width by it
    for c in conductors:
        extra.append(LineString(c.pts).buffer(w0/2, quad_segs=32))
    env = shapely.unary_union([env] + extra)
    ring = contour.difference(_inset(contour, annular))

    hi = opt.max_width if opt.max_width is not None else inf

    # caps per piece
    lines = shapely.linestrings(np.stack([PA, PB], 1))
    cap = 2 * shapely.distance(env.boundary, lines)
    inside = shapely.covered_by(lines, env)
    cap = np.where(inside, cap, 0.0)

    s_far = 0.9 * max(4 * (w0 + clr), 0.25 * _inset(contour, annular).length if not _inset(contour, annular).is_empty
                      else contour.length)
    tree = shapely.STRtree(lines)
    for b in bodies:
        bp = Point(b.x, b.y)
        idx = tree.query(bp, predicate='dwithin', distance=b.diameter/2 + clr + min(hi, 4*pitch + w0))
        for i in idx:
            if LY[i] not in b.layers:
                continue
            own = (CI[i], TH[i, 0], TH[i, 1], PH[i, 0], PH[i, 1], SS[i, 0], SS[i, 1])
            if not all(_different_turn(own, (ci, th, th, ph, ph, s, s), s_far, opt.arm_angle_turns)
                       for ci, th, ph, s in b.owners):
                continue
            d = float(_point_seg_distance_np(np.array([[b.x, b.y]]), PA[i:i+1], PB[i:i+1])[0])
            cap[i] = min(cap[i], 2 * (d - b.diameter/2 - clr))

    # pairs of pieces of different turns on the same layer. A pair can only limit the widths when its distance is below
    # (W_i + W_j)/2 + clearance, where W is an upper bound of the width: the cap, and twice the distance to the nearest
    # piece of another turn (less the clearance and the narrowest partner). Find that nearest distance first with a
    # radius of a few pitches, then query each piece with its own radius.
    def other_turn_pairs(ia, ib):
        sel = (ia != ib) & (LY[ia] == LY[ib])
        ia, ib = ia[sel], ib[sel]
        same = CI[ia] == CI[ib]
        th = np.max(np.abs(TH[ia][:, :, None] - TH[ib][:, None, :]), axis=(1, 2))
        ph = np.max(np.abs(PH[ia][:, :, None] - PH[ib][:, None, :]), axis=(1, 2))
        ds = np.maximum(0, np.maximum(SS[ia].min(1) - SS[ib].max(1), SS[ib].min(1) - SS[ia].max(1)))
        diff = ~same | ((th >= TURN_SEP) & opt.arm_angle_turns) | (ph >= TURN_SEP) | (ds >= s_far)
        ia, ib = ia[diff], ib[diff]
        return ia, ib, _seg_seg_distance_np(PA[ia], PB[ia], PA[ib], PB[ib])

    cap = np.minimum(cap, hi)
    r1 = 2 * pitch + clr
    ia, ib = tree.query(lines, predicate='dwithin', distance=r1)
    ia, ib, d = other_turn_pairs(ia, ib)
    dmin = np.full(npieces, inf)
    np.minimum.at(dmin, ia, d)
    W = np.maximum(np.minimum(cap, 2 * (dmin - clr) - lo), lo)
    big = W + clr > r1
    if np.any(big):
        ja, jb = tree.query(lines[big], predicate='dwithin', distance=W[big] + clr)
        ja = np.flatnonzero(big)[ja]
        ja, jb, dj = other_turn_pairs(ja, jb)
        ia, ib, d = np.concatenate([ia, ja]), np.concatenate([ib, jb]), np.concatenate([d, dj])
    # (<=: the pair with the nearest partner, which W is derived from, must stay even at equality)
    keep = d <= (W[ia] + W[ib]) / 2 + clr + 1e-9
    ia, ib, d = ia[keep], ib[keep], d[keep]
    bound = 2 * (d - clr)

    # vertex level: cap, and pair constraints w_x + w_y <= bound for the ends x of one piece and y of the other
    vcap = np.full(nv, hi)
    np.minimum.at(vcap, VA, cap)
    np.minimum.at(vcap, VB, cap)
    X = np.concatenate([VA[ia], VA[ia], VB[ia], VB[ia]])
    Y = np.concatenate([VA[ib], VB[ib], VA[ib], VB[ib]])
    B = np.tile(bound, 4)
    X, Y = np.minimum(X, Y), np.maximum(X, Y)
    order = np.lexsort((B, Y, X))
    X, Y, B = X[order], Y[order], B[order]
    first = np.ones(len(X), dtype=bool)
    first[1:] = (X[1:] != X[:-1]) | (Y[1:] != Y[:-1])
    X, Y, B = X[first], Y[first], B[first]
    # adjacency in CSR form
    U = np.concatenate([X, Y]); Vn = np.concatenate([Y, X]); BB = np.concatenate([B, B])
    o = np.argsort(U, kind='stable')
    U, Vn, BB = U[o], Vn[o], BB[o]
    ptr = np.searchsorted(U, np.arange(nv + 1))

    # symmetric split
    half = np.full(nv, inf)
    np.minimum.at(half, U, BB / 2)
    allowed = np.minimum(vcap, half)
    w = np.minimum(np.maximum(allowed, lo), max(hi, lo))
    forced = int(np.sum(allowed < lo - 1e-9))

    # repair constraints broken by flooring at the minimum width (lower the partner, down to the minimum width)
    viol = np.flatnonzero(w[X] + w[Y] > B + 1e-9)
    for k in viol:
        x, y, b = X[k], Y[k], B[k]
        for u, v in ((x, y), (y, x)):
            w[u] = max(min(w[u], b - w[v]), min(lo, w[u]))

    if opt.balance:
        Vl, Bl = Vn.tolist(), BB.tolist()
        wl = w.tolist()
        capl = vcap.tolist()
        for _pass in range(2):
            for v in np.argsort(w, kind='stable').tolist():
                room = capl[v]
                for k in range(ptr[v], ptr[v+1]):
                    r = Bl[k] - wl[Vl[k]]
                    if r < room:
                        room = r
                if room > wl[v]:
                    wl[v] = room
            w = np.array(wl)

    # quantize down, on a grid anchored at the constant trace width (so that widths at or above it stay at or above it,
    # and neighboring widths differ by whole quanta); widths below it (rare) are kept
    q = opt.quantum
    if q:
        wq = np.where(w >= w0, w0 + np.floor((w - w0) / q + 1e-9) * q, w)
        w = np.where(wq >= lo - 1e-12, wq, np.minimum(w, lo))

    unresolved = int(np.sum(w[X] + w[Y] > B + 1e-6))

    # resistance (per unit sheet resistance)
    wa, wb = w[VA], w[VB]
    L = np.hypot(*(PB - PA).T)
    dw = wb - wa
    with np.errstate(divide='ignore', invalid='ignore'):
        rt = np.where(np.abs(dw) > 1e-12, L * np.log(wb / wa) / np.where(np.abs(dw) > 1e-12, dw, 1), L / wa)
    r_taper = float(rt.sum())
    r_const = float(L.sum() / w0)

    res = TaperResult(model=model, options=opt, w0=w0, clearance=clr, conductors=conductors, bodies=bodies, widths=w,
                      allowed=allowed, lo=lo, hi=hi, forced=forced, unresolved=unresolved, r_const=r_const,
                      r_taper=r_taper, length=float(L.sum()), time=time.perf_counter() - t0, base_footprint=fp,
                      envelope=env, ring=ring, _layers=tuple(layer_names))
    res.vcap = vcap # per vertex upper bound from vias, pads and the envelope (diagnostics)
    res.pairs = (X, Y, B)
    inner_c = _inset(contour, annular)
    res.ring_inner_length = inner_c.length if not inner_c.is_empty else contour.length
    return res


# ---- cornerflat: rank layout candidates by tapered conductance ----

def cornerflat_candidates(model):
    """ Layout candidates (mode, arm phase) that a cornerflat PlanarInductor measured, with their turn spacing, best
    first """
    cache = getattr(model, '_measure_cache', {})
    return sorted(((k, v[0]) for k, v in cache.items()), key=lambda kv: -kv[1])


def cornerflat_forced(make_model, key):
    """ Build a cornerflat model with the layout candidate `key` = (mode, arm phase) forced. `make_model(cls)` must
    construct a fresh PlanarInductor of the given class (with a fresh shape). """
    from . import geometry
    from . import geometry_alt_cornerflat as cf

    class Forced(cf.PlanarInductor):
        def __post_init__(self):
            self.arm_phase = 0.0
            self._measure_cache = {}
            twists = 1 if self.layers == 1 else self.twists
            pitch = (self.shape.outer_radius - self.shape.inner_radius) / (self.turns / self.layers)
            self.shape.configure_spiral(pitch, twists, self.clockwise, self.layers,
                                        sweep=self.turns / self.layers / twists)
            self._excluded = ('only', key)
            geometry.PlanarInductor.__post_init__(self)

    return make_model(Forced)


def rank_cornerflat_by_taper(make_model, model=None, max_candidates=8, **taper_kw):
    """ Re-rank the layout candidates of a cornerflat coil by tapered DC resistance instead of the minimum turn spacing.
    Returns a list of dicts (key, spacing, w0, r_const, r_taper, vias_ok, default) sorted by r_taper. The default choice
    of the layout module is marked. Considers at most max_candidates candidates (best spacing first, the default
    choice always included). """
    from . import geometry_alt_cornerflat as cf
    if model is None:
        model = make_model(cf.PlanarInductor)
    default = model._layout_key()
    cands = cornerflat_candidates(model)
    keys = [k for k, _s in cands][:max_candidates]
    if default not in keys:
        keys.append(default)
    spacing = dict(cands)
    out = []
    for key in keys:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                m = model if key == default else cornerflat_forced(make_model, key)
            r = taper_layout(m, **taper_kw)
        except Exception as e: # a candidate can be rejected (e.g. no room for the trace)
            out.append(dict(key=key, spacing=spacing.get(key), error=f'{type(e).__name__}: {e}'[:200],
                            default=key == default))
            continue
        out.append(dict(key=key, spacing=spacing.get(key), w0=m.trace_width, r_const=r.r_const, r_taper=r.r_taper,
                        vias_ok=m._vias_ok(), default=key == default, result=r))
    out.sort(key=lambda d: d.get('r_taper', inf))
    return out
