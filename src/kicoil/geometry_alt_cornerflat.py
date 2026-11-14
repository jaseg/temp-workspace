"""KiCoil layout with flat corners ("cornerflat").

Drop-in replacement for `kicoil.geometry`. Polygon shapes use `CornerFlatSkeletonator`, whose spiral arms run at
constant depth around the polygon's corners and change depth only in ramps in the middle of the edges (see
`kicoil.skeletonator_alt_cornerflat`). The depth of an arm is linear in a *warped* angle; the arm start, fold and end
angles of `PlanarInductor` are warped angles, which the shape maps back to positions.

PlanarInductor picks the layout among a few candidates (the shape's layout modes, including the plain linear layout of
`kicoil.geometry` as a fallback, and rotations of the arms) by the measured turn spacing, and falls back to the next
candidate when the vias cannot be placed clear of the turns. The trace width is sized from the measured spacing as in
`kicoil.geometry`. The measurement additionally covers pieces of one arm that fold back onto each other within half a
revolution, and the via check covers the connections between the arm ends and the vias.

CircleShape is the one of `kicoil.geometry`.
"""

import dataclasses
import warnings
from dataclasses import dataclass
from math import pi, ceil, floor, dist, inf

from . import geometry
from .geometry import *  # noqa: F401,F403  re-export helpers
from .geometry import CircleShape, Shape  # noqa: F401
from .skeletonator_alt_cornerflat import CornerFlatSkeletonator, LinearView


def min_turn_spacing(arms, search_radius, min_turn_separation=0.5, min_path_separation=inf):
    """ Like `geometry.min_turn_spacing`, but segments of the same arm that are less than min_turn_separation
    revolutions apart are also reported when they are more than min_path_separation apart along the arm: near the inner
    end of a deep annulus, the arm can fold back onto itself within less than half a revolution.

    Returns (distance, location, folds), where distance and location are as in geometry.min_turn_spacing, and folds is
    a list of (distance, path separation, location) of such same-arm pairs closer than search_radius. """
    segs = []
    max_span = min_turn_separation / 10
    for arm_idx, (points, angles) in enumerate(arms):
        s = 0.0
        for q1, q2, u1, u2 in geometry._split_by_angle(points, angles, max_span):
            l = dist(q1, q2)
            segs.append((q1, q2, arm_idx, min(u1, u2), max(u1, u2), s, s + l))
            s += l

    cell = search_radius
    grid = {}
    def cells(p1, p2, margin):
        x0, x1 = min(p1[0], p2[0]) - margin, max(p1[0], p2[0]) + margin
        y0, y1 = min(p1[1], p2[1]) - margin, max(p1[1], p2[1]) + margin
        for gx in range(floor(x0/cell), floor(x1/cell) + 1):
            for gy in range(floor(y0/cell), floor(y1/cell) + 1):
                yield gx, gy

    for idx, (p1, p2, *_rest) in enumerate(segs):
        for c in cells(p1, p2, 0):
            grid.setdefault(c, []).append(idx)

    best, where = search_radius, None
    folds = []
    for idx, (p1, p2, arm, t_lo, t_hi, s_lo, s_hi) in enumerate(segs):
        seen = set()
        for c in cells(p1, p2, search_radius):
            for jdx in grid.get(c, ()):
                if jdx <= idx or jdx in seen:
                    continue
                seen.add(jdx)
                q1, q2, arm_j, u_lo, u_hi, r_lo, r_hi = segs[jdx]
                if arm_j == arm and max(u_lo - t_hi, t_lo - u_hi) < min_turn_separation:
                    sep = max(r_lo - s_hi, s_lo - r_hi)
                    if sep > min_path_separation:
                        d = geometry._seg_seg_distance(p1, p2, q1, q2)
                        if d < search_radius:
                            folds.append((d, sep, ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2)))
                    continue
                d = geometry._seg_seg_distance(p1, p2, q1, q2)
                if d < best:
                    best, where = d, ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2)
    return best, where, folds


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
                if mode == 'lattice':
                    continue # the lattice allocation is specific to the arm phase it was computed for
                for q in range(1, self.PHASE_STEPS):
                    key = (mode, q / self.PHASE_STEPS / twists)
                    self._candidates.append(key)
                    measure(key)
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
                bk = min(under, key=lambda k: (under[k] > self.UNDERSHOOT_LIMIT, -results[k][0] if under[k] <= self.UNDERSHOOT_LIMIT else under[k]))
        self._set_layout(bk)
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

        Pieces of the same arm count as neighbors when they are at least half a revolution apart, or when they are far
        apart along the arm (geomcheck counts pieces more than max(4 pitches, a quarter of the inner contour length)
        apart along the conductor as different turns; use a slightly smaller threshold here). """
        arms = self.spiral_center_lines()
        search_radius = 1.5 * self.spiral_pitch
        sk = getattr(self.shape, 'sk', None)
        if sk is not None:
            inner_len = sk.calc_circumference(self.shape.inner_radius)
        else:
            inner_len = 2*pi*self.shape.inner_radius
        # geomcheck's threshold depends on the trace pitch, which depends on the result. Collect all same-arm pairs that
        # are far enough apart along the arm for the smallest possible threshold, then resolve.
        best, where, folds = search_radius, None, []
        for layer_arms in arms:
            if layer_arms:
                d, w, f = min_turn_spacing(layer_arms, search_radius, min_path_separation=0.9*0.25*inner_len)
                folds += f
                if d < best:
                    best, where = d, w
        if where is None and not folds:
            return self.spiral_pitch, None
        best = min(best, self.spiral_pitch)
        while True:
            min_path = 0.9 * max(4*best, 0.25*inner_len)
            closer = [(d, w) for d, sep, w in folds if sep > min_path and d < best - 1e-12]
            if not closer:
                break
            best, where = min(closer)
        return min(best, self.spiral_pitch), where

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
