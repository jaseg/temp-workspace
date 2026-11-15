"""KiCoil layout with flat corners ("cornerflat").

Drop-in replacement for `kicoil.geometry`. Polygon shapes use `CornerFlatSkeletonator`, whose spiral arms run at
constant depth around the polygon's corners and change depth only in ramps in the middle of the edges (see
`kicoil.skeletonator_alt_cornerflat`). The depth of an arm is linear in a *warped* angle; the arm start, fold and end
angles of `PlanarInductor` are warped angles, which the shape maps back to positions.

PlanarInductor picks the layout among a few candidates (the shape's layout modes, including the plain linear layout of
`kicoil.geometry` as a fallback, and rotations of the arms) by the measured turn spacing, and falls back to the next
candidate when the vias cannot be placed clear of the turns. The trace width is sized from the measured spacing as in
`kicoil.geometry`. Within half a revolution of the arm's (warped) angle, the measurement tells turns apart like the
geometric checker, by the winding angle around the coil's center (`hole_center`): pieces of one arm half a turn apart
are neighboring turns, and one turn must not touch itself from 0.17 turns on (where it wraps around a hole smaller than
the trace, or runs over its own end via), while it may fold onto itself at a tip (thin inner contours: ellipse tips,
slivers, crescents), which is reported by the fold warning. The via check covers the connections between the arm ends
and the vias.

Large or noisy polygon outlines are simplified by 1 µm (up to 20 µm where 1 µm leaves too many reflex corners) before
the straight skeleton is computed (see `CornerFlatSkeletonator.prepare_outline`): densely sampled outlines with rounded
coordinates (e.g. from files) are otherwise full of tiny reflex corners, which make the skeleton slow or run it out of
memory. This replaces the base skeletonator's own noise removal (`skeletonator.remove_reflex_jitter`), which is not
applied on top of it. On round outlines (many
short edges, no real corners) the flat corner layout and the linear layout come out about the same, and the measurement
picks either; on noisy outlines the ramps get crowded out by the noise corners and the linear layout wins.

CircleShape is the one of `kicoil.geometry`.
"""

import dataclasses
import warnings
from dataclasses import dataclass
from math import pi, ceil, floor, dist, inf

import numpy as np

from . import geometry
from .geometry import *  # noqa: F401,F403  re-export helpers
from .geometry import CircleShape, Shape  # noqa: F401
from .skeletonator_alt_cornerflat import CornerFlatSkeletonator, LinearView


# Same-turn rule of the geometric checker (tests/geomcheck.py): copper less than half a turn apart in winding angle around
# the coil's center is one turn, and one turn may only touch itself less than 0.18 turns apart (a fold at a tip; further
# apart it shorts part of the turn, a self short). Pieces closer than pi/2*(w + c) along the conductor are not compared.
# The generator applies these rules with a margin: its center (`hole_center`) and its pieces of center line are not
# exactly the checker's copper, and layouts right at a threshold flip with small changes of the input.
TURN_WINDING = 0.48 # revolutions; pieces of one arm at least this far apart in winding angle are different turns
WRAP_WINDING = 0.17 # revolutions; pieces of one turn at least this far apart in winding angle must not touch
NEAR_FACTOR = 0.95 # pieces of one turn are compared from this fraction of the checker's distance along the conductor on
TOUCH_GAP = 0.001 # mm; least gap between the copper of one turn where it must not touch (geomcheck counts copper within
# 0.1 um as touching)
WINDING_STEP = 0.02 # revolutions; pieces are split so that their winding angle changes at most this much


def interior_point(poly):
    """ A point inside a simple polygon: the middle of the widest section of the horizontal line half way between the
    two vertex y coordinates nearest to the middle of its y extent (the interior point of GEOS, which shapely's
    representative_point and the geometric checker use). """
    ys = [y for _x, y in poly]
    cy = (min(ys) + max(ys)) / 2
    hi = min((y for y in ys if y > cy), default=max(ys))
    lo = max((y for y in ys if y <= cy), default=min(ys))
    y0 = (hi + lo) / 2
    xs = sorted(a[0] + (y0 - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
                for a, b in zip(poly, poly[1:] + poly[:1]) if (a[1] > y0) != (b[1] > y0))
    if len(xs) < 2:
        return (sum(x for x, _y in poly) / len(poly), cy)
    x0, x1 = max(zip(xs[::2], xs[1::2]), key=lambda iv: iv[1] - iv[0])
    return ((x0 + x1) / 2, y0)


def hole_center(sk, depth):
    """ The coil's center as the geometric checker sees it: the interior point (`interior_point`) of the inner contour,
    the offset outline at the given depth (a little beyond the annular width), which every turn winds around. """
    poly = []
    for i in range(len(sk.tracks)):
        p = tuple(float(c) for c in sk.track_position(i, depth))
        if not poly or dist(p, poly[-1]) > 1e-9:
            poly.append(p)
    while len(poly) > 1 and dist(poly[0], poly[-1]) <= 1e-9:
        poly.pop()
    if len(poly) < 3:
        return poly[0] if poly else (0.0, 0.0)
    return interior_point(poly)


def _split_pieces(points, angles, max_span, center):
    """ Pieces of an arm's center line as arrays (q1, q2, u1, u2, w1, w2), split like `geometry._split_by_angle_np` (at
    most max_span of the arm's angle per piece) and, with a center, also so that the winding angle around it changes by
    at most WINDING_STEP per piece. w1, w2 are the cumulative winding angles (revolutions) at the piece's ends, exact for
    the straight pieces (zeros without a center). """
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    ang = np.asarray(angles, dtype=float)
    a, b, ta, tb = pts[:-1], pts[1:], ang[:-1], ang[1:]
    keep = ~np.all(a == b, axis=1)
    a, b, ta, tb = a[keep], b[keep], ta[keep], tb[keep]
    if center is None:
        q1, q2, u1, u2 = _split_uniform(a, b, ta, tb, max_span)
        return q1, q2, u1, u2, np.zeros(len(q1)), np.zeros(len(q1))
    c = np.asarray(center, dtype=float)
    ra, rb = a - c, b - c
    turn = np.arctan2(ra[:, 0]*rb[:, 1] - ra[:, 1]*rb[:, 0], ra[:, 0]*rb[:, 0] + ra[:, 1]*rb[:, 1]) / (2*pi)
    # Cumulative winding angle at the segment starts (a straight segment turns by less than half a revolution)
    wa = np.concatenate([[0.0], np.cumsum(turn)[:-1]])
    if len(a):
        wa += np.arctan2(ra[0, 1], ra[0, 0]) / (2*pi)
    # Split at equal steps of the winding angle: the step boundaries are where rays from the center cross the segment
    n = np.maximum(1, np.ceil(np.abs(turn) / WINDING_STEP)).astype(np.int64)
    idx = np.repeat(np.arange(len(a)), n)
    k = np.arange(len(idx)) - np.repeat(np.cumsum(n) - n, n)
    nn = n[idx]
    e = b[idx] - a[idx]
    rai = ra[idx]

    def cut(f):
        th = 2*pi * (wa[idx] + turn[idx] * f)
        ux, uy = np.cos(th), np.sin(th)
        den = ux*e[:, 1] - uy*e[:, 0]
        t = -(ux*rai[:, 1] - uy*rai[:, 0]) / np.where(den == 0, 1.0, den)
        return np.where(f <= 0, 0.0, np.where(f >= 1, 1.0, np.clip(t, 0.0, 1.0)))
    f0, f1 = k / nn, (k + 1) / nn
    s0, s1 = cut(f0), cut(f1)
    a1, b1 = a[idx] + e * s0[:, None], a[idx] + e * s1[:, None]
    t1, t2 = ta[idx] + (tb[idx] - ta[idx]) * s0, ta[idx] + (tb[idx] - ta[idx]) * s1
    w0 = wa[idx] + turn[idx] * f0
    # Then at equal steps of the arm's angle, which is linear along the segment
    q1, q2, u1, u2, parent = _split_uniform(a1, b1, t1, t2, max_span, with_parent=True)
    rp = a1[parent] - c

    def wind_at(q):
        rq = q - c
        return w0[parent] + np.arctan2(rp[:, 0]*rq[:, 1] - rp[:, 1]*rq[:, 0], rp[:, 0]*rq[:, 0] + rp[:, 1]*rq[:, 1]) / (2*pi)
    return q1, q2, u1, u2, wind_at(q1), wind_at(q2)


def _split_uniform(a, b, ta, tb, max_span, with_parent=False):
    """ Split segments ab (angles ta, tb) into equal pieces of at most max_span in angle, like
    `geometry._split_by_angle_np` """
    n = np.maximum(1, np.ceil(np.abs(tb - ta) / max_span)).astype(np.int64)
    idx = np.repeat(np.arange(len(a)), n)
    k = np.arange(len(idx)) - np.repeat(np.cumsum(n) - n, n)
    nn = n[idx]
    f0, f1 = k / nn, (k + 1) / nn
    a, b, ta, tb = a[idx], b[idx], ta[idx], tb[idx]
    res = (a + (b - a) * f0[:, None], a + (b - a) * f1[:, None], ta + (tb - ta) * f0, ta + (tb - ta) * f1)
    return res + (idx,) if with_parent else res


def min_turn_spacing(arms, search_radius, min_turn_separation=0.5, center=None, same_turn_limit=None):
    """ Like `geometry.min_turn_spacing`, but with a center (a point inside the coil's hole), pairs of pieces of the same
    arm that are less than min_turn_separation apart in the arm's angle and at least WRAP_WINDING revolutions apart in
    winding angle around the center are also reported: where a turn wraps around a hole smaller than the trace, or
    the arm runs at constant warped angle (around a flat corner, or the tip of a thin inner contour) while it winds
    around the center, the arm's angle does not tell turns apart.

    Returns (distance, location, wraps), where distance and location are as in geometry.min_turn_spacing, and wraps is
    a tuple of arrays (distances, winding separations, path separations, locations) of such same-arm pairs closer than
    same_turn_limit (default: search_radius). Separations are the gaps between the pieces' intervals.

    Vectorized with numpy (the candidate pairs come from `geometry._candidate_pairs`), so that outlines with thousands of
    vertices are measured quickly. """
    pieces = [_split_pieces(points, angles, min_turn_separation / 10, center) for points, angles in arms]
    pieces = [pc for pc in pieces if len(pc[0])]
    if same_turn_limit is None:
        same_turn_limit = search_radius
    wrap_d, wrap_w, wrap_s, wrap_at = [np.zeros(0)], [np.zeros(0)], [np.zeros(0)], [np.zeros((0, 2))]
    if not pieces:
        return search_radius, None, (wrap_d[0], wrap_w[0], wrap_s[0], wrap_at[0])
    P, Q, U1, U2, W1, W2 = (np.concatenate([pc[k] for pc in pieces]) for k in range(6))
    arm = np.concatenate([np.full(len(pc[0]), i) for i, pc in enumerate(pieces)])
    tlo, thi = np.minimum(U1, U2), np.maximum(U1, U2)
    wlo, whi = np.minimum(W1, W2), np.maximum(W1, W2)
    seg_len = np.hypot(*(Q - P).T)
    S1 = np.concatenate([np.cumsum(seg_len[arm == i]) for i in range(len(pieces))])
    S0 = S1 - seg_len
    lo, hi = np.minimum(P, Q), np.maximum(P, Q)
    lox, loy, hix, hiy = lo[:, 0], lo[:, 1], hi[:, 0], hi[:, 1]

    best, where = search_radius, None
    for i, j in geometry._candidate_pairs(lo, hi, search_radius):
        # Lower bound of the distance from the bounding boxes
        gx = np.maximum(0, np.maximum(lox[i] - hix[j], lox[j] - hix[i]))
        gy = np.maximum(0, np.maximum(loy[i] - hiy[j], loy[j] - hiy[i]))
        sel = np.hypot(gx, gy) < search_radius
        i, j = i[sel], j[sel]
        same_turn = (arm[i] == arm[j]) & (np.maximum(tlo[j] - thi[i], tlo[i] - thi[j]) < min_turn_separation)
        if same_turn.any() and center is not None:
            fi, fj = i[same_turn], j[same_turn]
            wsep = np.maximum(wlo[fj] - whi[fi], wlo[fi] - whi[fj])
            sel = wsep >= WRAP_WINDING
            fi, fj, wsep = fi[sel], fj[sel], wsep[sel]
            if len(fi):
                d = geometry._seg_seg_distance_np(P[fi], Q[fi], P[fj], Q[fj])
                sel = d < same_turn_limit
                wrap_d.append(d[sel])
                wrap_w.append(wsep[sel])
                wrap_s.append(np.maximum(S0[fj] - S1[fi], S0[fi] - S1[fj])[sel])
                wrap_at.append((P[fi[sel]] + Q[fi[sel]]) / 2)
        i, j = i[~same_turn], j[~same_turn]
        if not len(i):
            continue
        d = geometry._seg_seg_distance_np(P[i], Q[i], P[j], Q[j])
        k = int(np.argmin(d))
        if d[k] < best:
            best = float(d[k])
            where = tuple(float(c) for c in (P[i[k]] + Q[i[k]]) / 2)
    return best, where, tuple(np.concatenate(x) for x in (wrap_d, wrap_w, wrap_s, wrap_at))


def _record_folds(model):
    """ Measure where a turn comes close to itself (e.g. around a sharp tip or a narrow notch) on the chosen layout, with
    the measurement of `kicoil.geometry`, so that PlanarInductor.__post_init__ warns about it as the base layout does.
    Only sets min_fold_spacing/min_fold_location and fold_candidates, the trace width is not affected. """
    arms = model.spiral_center_lines()
    res = [geometry.min_turn_spacing(a, model.spiral_pitch * (1 + 1e-9), folds=True) for a in arms if a]
    if res:
        model.min_fold_spacing, model.min_fold_location = min(((r[2], r[3]) for r in res), key=lambda r: r[0])
        # Pairs that converge into a tapered tip, which the base layout also warns about (see PlanarInductor)
        model.fold_candidates = geometry.FoldCandidates()
        for r in res:
            model.fold_candidates.merge(r[4])


class OffsetShape(geometry.OffsetShape):
    """ Polygon shape laid out with flat corners and ramps (see `CornerFlatSkeletonator`). Angles passed to and
    returned from the spiral methods are *warped* angles, in which the depth of an arm is linear.

    The shape offers several layouts ("spiral modes"): the flat corner layout with ramps constrained over the whole
    depth range ('cont'), optionally one with ramps optimized for the depths at which the turns actually pass them
    ('lattice', for few turns), and the plain linear layout of `kicoil.geometry` ('linear'). PlanarInductor measures
    them and keeps the one with the widest turn spacing. """

    def __post_init__(self):
        self.sk = CornerFlatSkeletonator(self.polygon)
        if self.annular_width >= self.sk.max_depth:
            raise ValueError(f'Annular width ({self.annular_width:.2f}) is too large. Must be less than {self.sk.max_depth:.2f}')
        if self.annular_width <= 0:
            raise ValueError(f'Annular width must be positive')
        self.sk.set_angle_reference(self.annular_width)
        self.view = self.sk
        self._linear = None
        self.max_via_offset = self.sk.max_depth - self.annular_width
        self.outer_radius = self.sk.radius
        self.inner_radius = self.sk.radius - self.annular_width

    def configure_spiral(self, pitch, twists, clockwise=False, layers=2, sweep=None):
        """ Optimize the ramps for the given spiral.

        A sheared ramp (deeper turns start their ramp earlier along the edge) gives neighboring turns more room, but only
        for arms that run in one direction: a shear that helps inward arms hurts outward arms by the same amount. Since
        inward and outward arms have to meet at the vias at both depth 0 and the full annular width, they cannot use
        different shears. So shear is only optimized for one direction in single layer coils, which have no outward
        arms. Two layer coils use a shear common to both directions only where it pays off despite the loss, on edges
        whose extent slides along the edge with depth (e.g. the tips of a star). """
        direction = -1 if clockwise else 1
        self.sk.configure(pitch, twists, direction, shear=True if layers == 1 else 'sym',
                          residue_signs=(direction,) if layers == 1 else (1, -1), sweep=sweep)
        self.view = self.sk

    def spiral_modes(self):
        return self.sk.modes() + ['linear']

    def set_spiral_mode(self, mode):
        if mode == 'linear':
            if self._linear is None:
                self._linear = LinearView(self.sk, self.annular_width)
            self.view = self._linear
        else:
            self.sk.set_mode(mode)
            self.view = self.sk
        self.spiral_mode = mode

    def compute_spiral_t(self, a1, a2, fn=None):
        """ Spiral center line from warped angle a1 on the outer radius to warped angle a2 on the inner radius, plus each
        point's warped angle in revolutions. """
        w1, w2 = a1/(2*pi), a2/(2*pi)
        A = self.annular_width
        v = self.view
        if w1 <= w2:
            points, angles = v.spiral(v.unwarp(w1), v.unwarp(w2), 0, A)
        else:
            points, angles = v.spiral(v.unwarp(w2), v.unwarp(w1), A, 0)
            points, angles = points[::-1], angles[::-1]
        angles = [v.warp(t) for t in angles]
        angles[0], angles[-1] = w1, w2
        return points, angles

    def compute_spiral(self, a1, a2, fn=None, debug=False):
        points, _angles = self.compute_spiral_t(a1, a2)
        return points, sum(dist(p, q) for p, q in zip(points, points[1:])), [None]*len(points)

    def project_point(self, r, a, r_ref=None):
        v = self.view
        return v.position(v.unwarp(a/(2*pi)), v.radius - r)


@dataclass
class PolygonShape(OffsetShape):
    polygon: list
    annular_width: float
    arc_tolerance: float = 0.05

    @property
    def slug(self):
        return f'polygon_{len(self.polygon)}pt'

    @property
    def desc(self):
        return f'{len(self.polygon)} point polygonal'


# The shapes of kicoil.geometry, laid out with flat corners (their __post_init__ sets up the polygon and then calls
# OffsetShape.__post_init__, which resolves to the one above).
@dataclass
class TrapezoidShape(geometry.TrapezoidShape, OffsetShape):
    pass


@dataclass
class RectangleShape(geometry.RectangleShape, OffsetShape):
    pass


@dataclass
class SectorShape(geometry.SectorShape, OffsetShape):
    pass


@dataclass
class StarShape(geometry.StarShape, OffsetShape):
    pass


@dataclass
class RegularPolygonShape(geometry.RegularPolygonShape, OffsetShape):
    pass


@dataclass
class SVGShape(geometry.SVGShape, OffsetShape):
    pass


@dataclass
class PlanarInductor(geometry.PlanarInductor):

    # The layout is chosen among candidates (shape layout mode, arm phase) by measured turn spacing.
    MODE_GOOD_ENOUGH = 0.995 # stop trying layout modes when the spacing is at least this fraction of the pitch
    PHASE_SEARCH_BELOW = 0.97 # try other arm phases when the spacing is below this fraction of the pitch
    PHASE_STEPS = 12 # arm phases tried per sector (1/twists revolution)
    PHASE_MIN_GAIN = 0.01 # use a non-zero arm phase only if it gains at least this fraction of the pitch
    PHASE_COARSE = 3 # phases (in PHASE_STEPS) measured first; the others only if the spacing changes with these
    PHASE_FLAT_TOL = 0.002 # ... by more than this fraction of the pitch
    MAX_VIA_RETRIES = 6

    def __post_init__(self):
        self.arm_phase = 0.0
        self._excluded = ()
        self._measure_cache = {}
        if not hasattr(self.shape, 'configure_spiral') or self.turns < 1 or self.twists < 1:
            return super().__post_init__()

        twists = 1 if self.layers == 1 else self.twists
        pitch = (self.shape.outer_radius - self.shape.inner_radius) / (self.turns / self.layers)
        self.shape.configure_spiral(pitch, twists, self.clockwise, self.layers, sweep=self.turns / self.layers / twists)

        # If the vias of the chosen layout cannot be placed clear of the turns, fall back to the next best candidate:
        # the first failure of a layout mode excludes that candidate, the second one the mode's rotated (non-zero arm
        # phase) candidates, the third one the whole mode. Finally fall back to the first candidate if none works.
        initial = {f.name: getattr(self, f.name) for f in dataclasses.fields(self)}
        excluded = []
        first = None
        for attempt in range(self.MAX_VIA_RETRIES + 1):
            if attempt > 0:
                for name, value in initial.items():
                    setattr(self, name, value)
            self._excluded = tuple(excluded)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                super().__post_init__()
            key = self._layout_key()
            if first is None:
                first = key
            if self._vias_ok():
                break
            fails = sum(1 for e in excluded if isinstance(e, tuple) and e[0] == key[0]
                        or isinstance(e, tuple) and e[:1] == ('phases',) and e[1] == key[0])
            excluded.append(key if fails == 0 else ('phases', key[0]) if fails == 1 else key[0])
            if not [c for c in self._candidates if not self._is_excluded(c, excluded)]:
                break
        if not self._vias_ok() and self._layout_key() != first:
            # Nothing helped: use the layout with the best spacing
            for name, value in initial.items():
                setattr(self, name, value)
            self._excluded = ('only', first)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                super().__post_init__()
        for w in caught:
            warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)

    @staticmethod
    def _is_excluded(key, excluded):
        return key in excluded or key[0] in excluded or (key[1] != 0 and ('phases', key[0]) in excluded)

    def _layout_key(self):
        return (getattr(self.shape, 'spiral_mode', None), self.arm_phase)

    def _vias_ok(self):
        gap, _where = self.via_track_clearance()
        return gap >= self.clearance - 1e-6 and self.via_ring_spacing() >= self.via_diameter + self.clearance - 1e-6

    def arm_angles(self, i):
        start_angle, fold_angle, end_angle = super().arm_angles(i)
        ph = 2*pi * getattr(self, 'arm_phase', 0.0)
        return start_angle + ph, fold_angle + ph, end_angle + ph

    def _set_layout(self, key):
        mode, phase = key
        if mode is not None:
            self.shape.set_spiral_mode(mode)
        self.arm_phase = phase
        self._center_lines = None

    def measure_turn_spacing(self):
        """ Measure the turn spacing of candidate layouts and keep the one with the widest spacing.

        Candidates are the shape's layout modes (see OffsetShape), and rotations of the arms' start angles by a fraction
        of a sector. The phase matters for deep annuli, where the innermost turns of different arms meet across a narrow
        inner contour. The alternatives are only tried when the first layout loses noticeable spacing. """
        excluded = getattr(self, '_excluded', ())
        only = excluded[:1] == ('only',)
        modes = self.shape.spiral_modes() if hasattr(self.shape, 'spiral_modes') else [None]
        if only:
            keys, modes = [excluded[1]], [excluded[1][0]]
            excluded = ()
        else:
            modes = [m for m in modes if m not in excluded] or modes
            keys = [(m, 0.0) for m in modes]
        self._candidates = list(keys)
        cache = self.__dict__.setdefault('_measure_cache', {})
        results = {}

        def measure(key):
            if key not in cache:
                self._set_layout(key)
                cache[key] = self._measure_turn_spacing()
            results[key] = cache[key]
            return results[key][0]

        def best_key():
            ok = [k for k in results if not self._is_excluded(k, excluded)] or list(results)
            return max(ok, key=lambda k: (results[k][0] - (self.PHASE_MIN_GAIN*self.spiral_pitch if k[1] else 0),
                                          -keys.index(k) if k in keys else -len(keys))) if ok else None

        for key in keys:
            if measure(key) >= self.MODE_GOOD_ENOUGH * self.spiral_pitch:
                break
        bk = best_key()
        phase_search = (hasattr(self.shape, 'spiral_modes') and not only
                        and results[bk][0] < self.PHASE_SEARCH_BELOW * self.spiral_pitch)
        if phase_search:
            twists = 1 if self.layers == 1 else self.twists
            for mode in modes:
                if mode == 'lattice' or (mode, 0.0) not in results:
                    continue # the lattice allocation is specific to the arm phase it was computed for
                # Coarse phases first. If the spacing does not change with them (e.g. on round outlines, where rotating
                # the arms changes nothing), skip the others: they would have to gain PHASE_MIN_GAIN in between.
                steps = range(1, self.PHASE_STEPS)
                coarse = [q for q in steps if q % self.PHASE_COARSE == 0]
                ref = results[(mode, 0.0)][0]
                flat = all(abs(measure((mode, q / self.PHASE_STEPS / twists)) - ref)
                           <= self.PHASE_FLAT_TOL * self.spiral_pitch for q in coarse)
                for q in steps:
                    key = (mode, q / self.PHASE_STEPS / twists)
                    if flat and q not in coarse:
                        continue
                    self._candidates.append(key)
                    measure(key)
                    results[key] = results.pop(key) # keep the candidates in phase order (ties go to the first one)
            bk = best_key()

        # The copper should reach the outline everywhere. A single layer spiral leaves sharp corners uncovered when they
        # come late in the first revolution; rotating the arms helps. Among the candidates of the chosen mode with
        # (almost) the same spacing, prefer the best coverage.
        if hasattr(self.shape, 'polygon') and not only and bk[0] != 'lattice':
            under = {bk: self._contour_undershoot(bk, results[bk][0])}
            if under[bk] > self.UNDERSHOOT_LIMIT:
                twists = 1 if self.layers == 1 else self.twists
                for q in range(self.PHASE_STEPS):
                    key = (bk[0], q / self.PHASE_STEPS / twists)
                    if self._is_excluded(key, excluded):
                        continue
                    if key not in self._candidates:
                        self._candidates.append(key)
                    if measure(key) >= results[bk][0] - 0.005*self.spiral_pitch:
                        under[key] = self._contour_undershoot(key, results[key][0])
                # The widest spacing among those that cover the outline, and among equally wide ones (rotations often
                # measure the same spacing, up to rounding) the best coverage; else the best coverage
                ok = [k for k in under if under[k] <= self.UNDERSHOOT_LIMIT]
                if ok:
                    widest = max(results[k][0] for k in ok)
                    ok = [k for k in ok if results[k][0] >= widest - 1e-9 * self.spiral_pitch]
                bk = min(ok or under, key=lambda k: under[k])
        self._set_layout(bk)
        _record_folds(self)
        return results[bk]

    UNDERSHOOT_LIMIT = 1.15 # largest distance from the outline to the copper, in trace pitches, before trying to improve

    def _contour_undershoot(self, key, spacing):
        """ Largest distance from the outline to the copper of any layer, in units of the trace pitch, for the given
        layout and turn spacing (= trace width + clearance) """
        self._set_layout(key)
        w = max(spacing - (self.clearance or 0), 0.0)
        segs = [seg for layer in self.spiral_center_lines() for pts, _ang in layer for seg in zip(pts, pts[1:])]
        if not segs or spacing <= 0:
            return 0.0
        cell = max(spacing, 1e-3)
        grid = {}
        for idx, (a, b) in enumerate(segs):
            for gx in range(floor(min(a[0], b[0])/cell), floor(max(a[0], b[0])/cell) + 1):
                for gy in range(floor(min(a[1], b[1])/cell), floor(max(a[1], b[1])/cell) + 1):
                    grid.setdefault((gx, gy), []).append(idx)
        poly = self.shape.polygon
        worst = 0.0
        for p, q in zip(poly, poly[1:] + poly[:1]):
            n = max(1, ceil(dist(p, q) / (spacing / 4)))
            for i in range(n):
                x, y = p[0] + (q[0]-p[0])*i/n, p[1] + (q[1]-p[1])*i/n
                best = inf
                r = 0
                while best == inf or r * cell < best + cell:
                    cx, cy = floor(x/cell), floor(y/cell)
                    for gx in range(cx - r, cx + r + 1):
                        for gy in range(cy - r, cy + r + 1):
                            if max(abs(gx - cx), abs(gy - cy)) != r:
                                continue
                            for idx in grid.get((gx, gy), ()):
                                a, b = segs[idx]
                                best = min(best, geometry._seg_seg_distance(a, b, (x, y), (x, y)))
                    r += 1
                    if r > 10000:
                        break
                worst = max(worst, best - w/2)
        return worst / spacing

    def _measure_turn_spacing(self):
        """ Smallest center line distance between neighboring turns on the same layer, and where it occurs.

        Pieces of different arms, and of one arm at least half a revolution apart in the arm's angle, are neighbors (as
        in `kicoil.geometry`). The geometric checker tells turns apart by the winding angle around the coil's center
        instead. The arm's warped angle is constant around flat corners and around the tip of a thin inner contour, so
        for pieces of one arm less than half a revolution apart in it, the winding angle around `hole_center` decides:
        pieces at least TURN_WINDING apart are neighbors; pieces at least WRAP_WINDING apart (one turn wrapping around a
        hole smaller than the trace, or running over its own end via) must not touch, which limits the trace width to
        their distance; closer in winding angle, the turn folds onto itself at a tip, which does not limit the spacing
        (`_record_folds` measures it for the fold warning). As in the checker, pieces of one turn are only compared when
        they are at least pi/2 times the trace pitch apart along the conductor (closer, they are bends of one piece of
        track). That threshold depends on the result: a pair rules out an interval of spacings, and the result is the
        largest spacing no pair rules out. """
        arms = self.spiral_center_lines()
        search_radius = 1.5 * self.spiral_pitch
        sk = getattr(self.shape, 'sk', None)
        center = getattr(self.shape, '_hole_center', None)
        if center is None and sk is not None:
            A = self.shape.annular_width
            center = self.shape._hole_center = hole_center(sk, min(1.02 * A, (A + sk.max_depth) / 2))
        clearance = self.clearance or 0.0
        best, where, wraps = search_radius, None, []
        for layer_arms in arms:
            if layer_arms:
                d, w, f = min_turn_spacing(layer_arms, search_radius, center=center, same_turn_limit=self.spiral_pitch)
                wraps.append(f)
                if d < best:
                    best, where = d, w
        wd, ww, ws, wat = (np.concatenate([f[k] for f in wraps]) if wraps else np.zeros((0, 2) if k == 3 else 0)
                           for k in range(4))
        if where is None and not len(wd):
            return self.spiral_pitch, None
        best = min(best, self.spiral_pitch)
        # The spacing a pair allows: its distance for different turns, distance plus clearance for one turn
        bound = np.where(ww >= TURN_WINDING, wd, wd + clearance - TOUCH_GAP)
        # geomcheck compares pieces at least pi/2*(w + c) apart along the conductor, which depends on the result: a pair
        # rules out the spacings s in (bound, ds / (NEAR_FACTOR*pi/2)]. Find the largest spacing no pair rules out.
        reach = ws / (NEAR_FACTOR * pi/2)
        while True:
            sel = np.flatnonzero((reach >= best) & (bound < best - 1e-12))
            if not len(sel):
                break
            # smallest bound; ties broken by location like min() over (distance, location) tuples
            k = sel[np.lexsort((wat[sel, 1], wat[sel, 0], bound[sel]))[0]]
            best, where = float(bound[k]), (float(wat[k][0]), float(wat[k][1]))
        return best, where

    def via_track_clearance(self):
        """ Like geometry.PlanarInductor.via_track_clearance, but also checks the straight connections between the arm
        ends and their vias, which become long when the via offset is large. Returns (gap, location). """
        gap, where = super().via_track_clearance()
        inner_r = self.shape.inner_radius - self.via_offset
        outer_r = self.shape.outer_radius + self.via_offset
        arms = self.spiral_center_lines()
        conns = [] # (layer, a, b, {arm index: angle in revolutions where the connection attaches})
        for i in range(self.twists):
            start_angle, fold_angle, _end_angle = self.arm_angles(i)
            r = inner_r - (2*self.via_offset if self.stagger_inner_vias and i%2 != 0 else 0)
            v = self.shape.project_point(r, fold_angle)
            p0 = arms[0][i][0][-1]
            conns.append((0, p0, v, {i: fold_angle/(2*pi)}))
            if self.layers > 1:
                conns.append((1, arms[1][i][0][-1], v, {i: fold_angle/(2*pi)}))
            if i > 0:
                j = (i - self.turns) % self.twists
                r = outer_r + (2*self.via_offset if self.stagger_outer_vias and i%2 != 0 else 0)
                v = self.shape.project_point(r, start_angle)
                conns.append((0, arms[0][i][0][0], v, {i: start_angle/(2*pi)}))
                if self.layers > 1:
                    conns.append((1, arms[1][j][0][0], v, {j: self.arm_angles(j)[2]/(2*pi)}))
        best = inf
        for layer, a, b, attach in conns:
            if dist(a, b) < 1e-9:
                continue
            for arm, (points, angles) in enumerate(arms[layer]):
                tv = attach.get(arm)
                for p1, p2, t1, t2 in geometry._split_by_angle(points, angles, 0.05):
                    if tv is not None and abs(t1 - tv) < 0.5 and abs(t2 - tv) < 0.5:
                        continue
                    d = geometry._seg_seg_distance(p1, p2, a, b)
                    if d - self.trace_width < best:
                        best, w = d - self.trace_width, b
        if best < gap:
            return best, w
        return gap, where
