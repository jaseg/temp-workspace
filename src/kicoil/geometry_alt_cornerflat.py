"""KiCoil layout with flat corners ("cornerflat").

Drop-in replacement for `kicoil.geometry`. Polygon shapes use `CornerFlatSkeletonator`, whose spiral arms run at
constant depth around the polygon's corners and change depth only in ramps in the middle of the edges (see
`kicoil.skeletonator_alt_cornerflat`). The depth of an arm is linear in a *warped* angle; the arm start, fold and end
angles of `PlanarInductor` are warped angles, which the shape maps back to positions.

PlanarInductor picks the layout among a few candidates (the shape's layout modes, including the plain linear layout of
`kicoil.geometry` as a fallback, and rotations of the arms) by the measured turn spacing, and falls back to the next
candidate when the vias cannot be placed clear of the turns. The trace width is sized from the measured spacing as in
`kicoil.geometry`. Within half a revolution of the arm's (warped) angle, the measurement tells turns apart like the
geometric checker, by the winding angle around the coil's center, between the closest points of two track segments:
pieces of one arm half a turn apart are neighboring turns, and one turn must keep the clearance from itself from 0.175
turns on (where it wraps around a hole smaller than the trace), while it may fold onto itself at a tip (thin inner
contours: ellipse tips, slivers, crescents), which is reported by the fold warning. The center is the checker's, and on
symmetric holes, where the checker's choice is a tie that rounding decides, every center it may pick
(`checker_centers`). The vias at the arm ends are checked against the track of their own arm in the same way. The via
check covers the connections between the arm ends and the vias.

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


# Same-turn rule of the geometric checker (tests/geomcheck.py): copper less than half a turn apart in cumulative winding
# angle around the coil's center is one turn, and one turn may only touch itself less than 0.18 turns apart (a fold at a
# tip; further apart it shorts part of the turn, a self short). Pieces closer than pi/2*(w + c) along the conductor are
# not compared. The measurement takes the winding angles and path positions at the closest points of two pieces, as the
# checker does, and applies the rules with small margins, so that a layout does not sit right at a threshold.
TURN_WINDING = 0.48 # revolutions; pieces of one arm at least this far apart in winding angle are different turns
WRAP_WINDING = 0.175 # revolutions; pieces of one turn at least this far apart in winding angle must keep the clearance
NEAR_FACTOR = 0.98 # pieces of one turn are compared from this fraction of the checker's distance along the conductor on
# The checker's center is the interior point of an inset of the outline, which jumps where two vertex heights or two
# section widths tie (symmetric holes: mirrored centers). The measurement uses every center within these tolerances.
CENTER_TIE_Y = 2e-3 # of the inset's height: vertex heights this close to the middle count as above and as below
CENTER_TIE_W = 5e-3 # sections at least this much (relative) less wide than the widest count as the widest


def interior_point(poly):
    """ A point inside a simple polygon: the middle of the widest section of the horizontal line half way between the
    two vertex y coordinates nearest to the middle of its y extent (the interior point of GEOS, which shapely's
    representative_point and the geometric checker use). """
    return interior_points(poly, 0.0, 0.0)[0]


def interior_points(poly, tie_y=CENTER_TIE_Y, tie_w=CENTER_TIE_W):
    """ Every point `interior_point` can return when the vertex heights within tie_y (times the polygon's height) of the
    middle of its y extent count as above or below it, and the sections within tie_w (relative) of the widest as the
    widest. The first one is `interior_point`'s. """
    ys = [y for _x, y in poly]
    cy = (min(ys) + max(ys)) / 2
    tol = tie_y * (max(ys) - min(ys))
    above = [y for y in ys if y > cy]
    below = [y for y in ys if y <= cy]
    splits = [(above, below)]
    if tol > 0:
        near = [y for y in ys if abs(y - cy) <= tol]
        if near:
            splits.append(([y for y in above if y > cy + tol] + near, [y for y in below if y < cy - tol]))
            splits.append(([y for y in above if y > cy + tol], [y for y in below if y < cy - tol] + near))
    out = []
    for hi_set, lo_set in splits:
        hi = min(hi_set, default=max(ys))
        lo = max(lo_set, default=min(ys))
        y0 = (hi + lo) / 2
        xs = sorted(a[0] + (y0 - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
                    for a, b in zip(poly, poly[1:] + poly[:1]) if (a[1] > y0) != (b[1] > y0))
        if len(xs) < 2:
            pts = [(sum(x for x, _y in poly) / len(poly), cy)]
        else:
            ivs = list(zip(xs[::2], xs[1::2]))
            widest = max(ivs, key=lambda iv: iv[1] - iv[0])
            width = widest[1] - widest[0]
            pts = [((widest[0] + widest[1]) / 2, y0)]
            pts += [((x0 + x1) / 2, y0) for x0, x1 in ivs if x1 - x0 >= width * (1 - tie_w) and (x0, x1) != widest]
        out += [p for p in pts if all(dist(p, q) > 1e-9 for q in out)]
    return out


def checker_centers(shape):
    """ The coil's center as the geometric checker picks it (the interior point of the outline inset by 1.02 times the
    annular width, with mitred corners, see geomcheck.intent_from_model), first, followed by the other points it may
    pick on a slightly changed input (`interior_points`). Without shapely, the inner contour is the skeleton's offset
    outline. """
    A = shape.annular_width
    try:
        from shapely.geometry import Polygon
    except ImportError: # pragma: no cover
        Polygon = None
    if Polygon is not None:
        contour = list(getattr(shape, 'design_outline', None) or shape.polygon)
        poly = Polygon(contour)
        if not poly.exterior.is_ccw:
            poly = Polygon(contour[::-1])
        inner = poly.buffer(-A * 1.02, join_style='mitre', mitre_limit=10)
        if inner.is_empty:
            inner = poly.buffer(-A * 0.98, join_style='mitre', mitre_limit=10)
        if inner.is_empty:
            return [poly.representative_point().coords[0]]
        if inner.geom_type != 'Polygon':
            inner = max(inner.geoms, key=lambda g: g.area)
        pts = [tuple(map(float, p)) for p in inner.exterior.coords[:-1]]
    else:
        sk = shape.sk
        pts = []
        for i in range(len(sk.tracks)):
            p = tuple(float(c) for c in sk.track_position(i, min(1.02 * A, (A + sk.max_depth) / 2)))
            if not pts or dist(p, pts[-1]) > 1e-9:
                pts.append(p)
        while len(pts) > 1 and dist(pts[0], pts[-1]) <= 1e-9:
            pts.pop()
    if len(pts) < 3:
        return [pts[0] if pts else (0.0, 0.0)]
    return interior_points(pts)


def _split_pieces(points, angles, max_span):
    """ Pieces of an arm's center line as arrays (q1, q2, u1, u2, parent), split like `geometry._split_by_angle_np`
    (at most max_span of the arm's angle per piece); parent is the index of the center line segment the piece is on.
    Consecutive pieces join (q2[k] == q1[k+1]). """
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    ang = np.asarray(angles, dtype=float)
    a, b, ta, tb = pts[:-1], pts[1:], ang[:-1], ang[1:]
    seg = np.flatnonzero(~np.all(a == b, axis=1))
    q1, q2, u1, u2, parent = _split_uniform(a[seg], b[seg], ta[seg], tb[seg], max_span, with_parent=True)
    return q1, q2, u1, u2, seg[parent]


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


def _windings(q1, q2, centers):
    """ Cumulative winding angles (revolutions) at the starts q1 of consecutive pieces around each center, shape
    (len(centers), len(q1)); exact, since a straight piece turns by less than half a revolution around a point off it """
    c = np.asarray(centers, dtype=float)[:, None, :]
    r1, r2 = q1[None] - c, q2[None] - c
    turn = _angle_between(r1, r2)
    w = np.cumsum(turn, axis=1) - turn
    return w + np.arctan2(r1[..., 1], r1[..., 0])[:, :1] / (2*pi)


def _angle_between(r1, r2):
    """ Signed angle (revolutions) from vectors r1 to r2 (arrays of shape (..., 2)) """
    return np.arctan2(r1[..., 0]*r2[..., 1] - r1[..., 1]*r2[..., 0], r1[..., 0]*r2[..., 0] + r1[..., 1]*r2[..., 1]) / (2*pi)


def _seg_seg_closest_np(a, b, c, d):
    """ Distance and closest points (x on ab, y on cd) of arrays of segments ab and cd. Among equally close points the
    choice is that of `geometry._seg_seg_distance_np`'s terms (endpoint to segment). """
    def orient(p, q, r):
        return (q[:, 0]-p[:, 0])*(r[:, 1]-p[:, 1]) - (q[:, 1]-p[:, 1])*(r[:, 0]-p[:, 0])
    d1, d2, d3, d4 = orient(c, d, a), orient(c, d, b), orient(a, b, c), orient(a, b, d)
    crossing = (((d1 > 0) != (d2 > 0)) & (d1 != 0) & (d2 != 0) & ((d3 > 0) != (d4 > 0)) & (d3 != 0) & (d4 != 0))

    def foot(p, s1, s2):
        e = s2 - s1
        l2 = np.einsum('ij,ij->i', e, e)
        t = np.einsum('ij,ij->i', p - s1, e) / np.where(l2 == 0, 1.0, l2)
        return s1 + e * np.clip(np.where(l2 == 0, 0.0, t), 0.0, 1.0)[:, None]
    cands = [(a, foot(a, c, d)), (b, foot(b, c, d)), (foot(c, a, b), c), (foot(d, a, b), d)]
    ds = np.stack([np.hypot(*(x - y).T) for x, y in cands])
    k = np.argmin(ds, axis=0)
    n = np.arange(len(a))
    x = np.stack([cx for cx, _ in cands])[k, n]
    y = np.stack([cy for _, cy in cands])[k, n]
    dist_ = ds[k, n]
    if crossing.any():
        t = (d1 / np.where(crossing, d1 - d2, 1.0))[:, None]
        xi = a + (b - a) * t
        x = np.where(crossing[:, None], xi, x)
        y = np.where(crossing[:, None], xi, y)
        dist_ = np.where(crossing, 0.0, dist_)
    return dist_, x, y


def min_turn_spacing(arms, search_radius, min_turn_separation=0.5, centers=None, same_turn_limit=None):
    """ Like `geometry.min_turn_spacing`, but with centers (points inside the coil's hole), pairs of pieces of the same
    arm that are less than min_turn_separation apart in the arm's angle are also reported: where a turn wraps around a
    hole smaller than the trace, or the arm runs at constant warped angle (around a flat corner, or the tip of a thin
    inner contour) while it winds around the center, the arm's angle does not tell turns apart.

    Returns (distance, location, same), where distance and location are as in geometry.min_turn_spacing, and same is a
    tuple of arrays (distances, winding separations, path separations, locations, segment pairs) of such same-arm
    pairs closer than same_turn_limit (default: search_radius): for each pair of center line segments, the closest pair
    of their pieces, which is what the geometric checker compares (it does not split the track segments). The
    separations are those of the closest points, the winding separation the largest one around any of the centers; a
    segment pair (shape (n, 2)) names the center line segments (numbered over all arms).

    Vectorized with numpy (the candidate pairs come from `geometry._candidate_pairs`), so that outlines with thousands of
    vertices are measured quickly. """
    pieces = [_split_pieces(points, angles, min_turn_separation / 10) for points, angles in arms]
    offsets = np.cumsum([0] + [max(len(points) - 1, 0) for points, _angles in arms])
    keep = [k for k, pc in enumerate(pieces) if len(pc[0])]
    if same_turn_limit is None:
        same_turn_limit = search_radius
    same = [[np.zeros(0)], [np.zeros(0)], [np.zeros(0)], [np.zeros((0, 2))], [np.zeros((0, 2), dtype=np.int64)]]
    if not keep:
        return search_radius, None, tuple(x[0] for x in same)
    P, Q, U1, U2 = (np.concatenate([pieces[k][m] for k in keep]) for m in range(4))
    seg = np.concatenate([pieces[k][4] + offsets[k] for k in keep])
    arm = np.concatenate([np.full(len(pieces[k][0]), k) for k in keep])
    W = (np.concatenate([_windings(pieces[k][0], pieces[k][1], centers) for k in keep], axis=1)
         if centers else None)
    tlo, thi = np.minimum(U1, U2), np.maximum(U1, U2)
    seg_len = np.hypot(*(Q - P).T)
    S0 = np.concatenate([np.cumsum(seg_len[arm == k]) for k in keep]) - seg_len
    lo, hi = np.minimum(P, Q), np.maximum(P, Q)
    lox, loy, hix, hiy = lo[:, 0], lo[:, 1], hi[:, 0], hi[:, 1]
    cs = np.asarray(centers, dtype=float)[:, None, :] if centers else None
    best, where = search_radius, None
    for i, j in geometry._candidate_pairs(lo, hi, search_radius):
        # Lower bound of the distance from the bounding boxes
        gx = np.maximum(0, np.maximum(lox[i] - hix[j], lox[j] - hix[i]))
        gy = np.maximum(0, np.maximum(loy[i] - hiy[j], loy[j] - hiy[i]))
        sel = np.hypot(gx, gy) < search_radius
        i, j = i[sel], j[sel]
        same_turn = (arm[i] == arm[j]) & (np.maximum(tlo[j] - thi[i], tlo[i] - thi[j]) < min_turn_separation)
        if same_turn.any() and centers:
            fi, fj = i[same_turn], j[same_turn]
            d, x, y = _seg_seg_closest_np(P[fi], Q[fi], P[fj], Q[fj])
            sel = d < same_turn_limit
            fi, fj, d, x, y = fi[sel], fj[sel], d[sel], x[sel], y[sel]
            wx = W[:, fi] + _angle_between(P[fi][None] - cs, x[None] - cs)
            wy = W[:, fj] + _angle_between(P[fj][None] - cs, y[None] - cs)
            same[0].append(d)
            same[1].append(np.max(np.abs(wx - wy), axis=0))
            same[2].append(np.abs(S0[fi] + np.hypot(*(x - P[fi]).T) - S0[fj] - np.hypot(*(y - P[fj]).T)))
            same[3].append((x + y) / 2)
            same[4].append(np.stack([seg[fi], seg[fj]], axis=1))
        i, j = i[~same_turn], j[~same_turn]
        if not len(i):
            continue
        d = geometry._seg_seg_distance_np(P[i], Q[i], P[j], Q[j])
        k = int(np.argmin(d))
        if d[k] < best:
            best = float(d[k])
            where = tuple(float(c) for c in (P[i[k]] + Q[i[k]]) / 2)
    return best, where, _closest_per_segment(*(np.concatenate(x) for x in same))


def _end_via_pairs(arms, limit, centers, max_span=0.05):
    """ The vias at the ends of the arms (centered on the arm's end points) against the track of their own arm, as the
    geometric checker sees them: for each center line segment of an arm closer than limit to an end of the arm, as
    arrays: the distance from that end, and the winding and path separations of the closest point from it (the winding
    separation is the largest one around any of the centers), and the closest point. """
    out = [[np.zeros(0)], [np.zeros(0)], [np.zeros(0)], [np.zeros((0, 2))], [np.zeros((0, 1), dtype=np.int64)]]
    cs = np.asarray(centers, dtype=float)[:, None, :]
    for points, angles in arms:
        q1, q2, _u1, _u2, seg = _split_pieces(points, angles, max_span)
        if not len(q1):
            continue
        W = _windings(q1, q2, centers)
        seg_len = np.hypot(*(q2 - q1).T)
        S0 = np.cumsum(seg_len) - seg_len
        w_end = W[:, -1] + _angle_between(q1[-1][None] - cs[:, 0], q2[-1][None] - cs[:, 0])
        for e, s_e, w_e in ((q1[0], 0.0, W[:, 0]), (q2[-1], S0[-1] + seg_len[-1], w_end)):
            ev = np.broadcast_to(e, q1.shape)
            d, x, _y = _seg_seg_closest_np(q1, q2, ev, ev)
            k = np.flatnonzero(d < limit)
            d, x = d[k], x[k]
            wx = W[:, k] + _angle_between(q1[k][None] - cs, x[None] - cs)
            res = _closest_per_segment(d, np.max(np.abs(wx - w_e[:, None]), axis=0),
                                       np.abs(S0[k] + np.hypot(*(x - q1[k]).T) - s_e), x, seg[k][:, None])
            for m in range(5):
                out[m].append(res[m])
    return tuple(np.concatenate(x) for x in out[:4])


def _closest_per_segment(d, *rest):
    """ Of piece pairs (distances, further arrays..., segment keys as the last array, shape (n, k)), keep the closest
    one of each key: the one the checker, which compares whole track segments, sees """
    keys = rest[-1]
    if not len(d):
        return (d,) + rest
    order = np.lexsort((d,) + tuple(keys[:, m] for m in reversed(range(keys.shape[1]))))
    sk = keys[order]
    first = np.ones(len(sk), dtype=bool)
    first[1:] = np.any(sk[1:] != sk[:-1], axis=1)
    k = order[first]
    return (d[k],) + tuple(x[k] for x in rest)


def _record_folds(model, spacing, folds):
    """ Measure where a turn comes close to itself (e.g. around a sharp tip or a narrow notch) on the chosen layout, with
    the measurement of `kicoil.geometry`, so that PlanarInductor.__post_init__ warns about it as the base layout does.
    Same-turn contacts the spacing measurement classed as folds (see `PlanarInductor._measure_turn_spacing`) are
    added where the checker compares them (at least pi/2 times the turn spacing apart along the conductor): a turn
    folding onto itself around the tip of a thin inner contour, or wrapping around a small hole less than WRAP_WINDING
    apart in winding angle. Only sets min_fold_spacing/min_fold_location and fold_candidates, the trace width is not
    affected. """
    arms = model.spiral_center_lines()
    res = [geometry.min_turn_spacing(a, model.spiral_pitch * (1 + 1e-9), folds=True) for a in arms if a]
    if res:
        model.min_fold_spacing, model.min_fold_location = min(((r[2], r[3]) for r in res), key=lambda r: r[0])
        # Pairs that converge into a tapered tip, which the base layout also warns about (see PlanarInductor)
        model.fold_candidates = geometry.FoldCandidates()
        for r in res:
            model.fold_candidates.merge(r[4])
    fd, fs, fat = folds
    sel = np.flatnonzero(fs >= pi/2 * spacing)
    if len(sel):
        k = sel[np.argmin(fd[sel])]
        if fd[k] < getattr(model, 'min_fold_spacing', inf):
            model.min_fold_spacing, model.min_fold_location = float(fd[k]), (float(fat[k][0]), float(fat[k][1]))


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
        self._fold_cache = {}
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
        self._folds = self.__dict__.setdefault('_fold_cache', {})
        results = {}

        def measure(key):
            if key not in cache:
                self._set_layout(key)
                cache[key] = self._measure_turn_spacing()
                self._folds[key] = self._last_folds
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
                # The widest spacing among those that cover the outline (the first of equally wide ones: rotations often
                # measure the same spacing, up to rounding), else the best coverage
                ok = [k for k in under if under[k] <= self.UNDERSHOOT_LIMIT]
                if ok:
                    widest = max(results[k][0] for k in ok)
                    bk = next(k for k in ok if results[k][0] >= widest - 1e-9 * self.spiral_pitch)
                else:
                    bk = min(under, key=lambda k: under[k])
        self._set_layout(bk)
        _record_folds(self, results[bk][0], self._folds.get(bk, (np.zeros(0), np.zeros(0), np.zeros((0, 2)))))
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
        for pieces of one arm less than half a revolution apart in it, the winding angle between their closest points
        decides, around every center the checker may pick (`checker_centers`, the largest separation counts): pieces at
        least TURN_WINDING apart are neighbors; pieces at least WRAP_WINDING apart (one turn wrapping around a hole
        smaller than the trace) must keep the clearance like neighbors, but only where they are at least pi/2 times the
        turn spacing apart along the conductor, as in the checker (closer, they are bends of one piece of track); closer
        in winding angle, the turn folds onto itself at a tip, which does not limit the spacing (`_record_folds` warns
        about it). The path threshold depends on the result: a pair rules out an interval of spacings, and the result is
        the largest spacing no pair rules out. """
        arms = self.spiral_center_lines()
        search_radius = 1.5 * self.spiral_pitch
        centers = None
        if getattr(self.shape, 'sk', None) is not None and hasattr(self.shape, 'polygon'):
            centers = getattr(self.shape, '_checker_centers', None)
            if centers is None:
                centers = self.shape._checker_centers = checker_centers(self.shape)
        clearance = self.clearance or 0.0
        best, where, same, vias = search_radius, None, [], []
        for layer_arms in arms:
            if layer_arms:
                d, w, f = min_turn_spacing(layer_arms, search_radius, centers=centers, same_turn_limit=self.spiral_pitch)
                same.append(f)
                if centers:
                    vias.append(_end_via_pairs(layer_arms, self.spiral_pitch, centers))
                if d < best:
                    best, where = d, w
        sd, sw, ss, sat = (np.concatenate([f[k] for f in same]) if same else np.zeros((0, 2) if k == 3 else 0)
                           for k in range(4))
        vd, vw, vs, vat = (np.concatenate([f[k] for f in vias]) if vias else np.zeros((0, 2) if k == 3 else 0)
                           for k in range(4))
        fold = sw < WRAP_WINDING
        self._last_folds = (sd[fold], ss[fold], sat[fold])
        vsame = vw >= WRAP_WINDING
        if where is None and not (~fold).any() and not vsame.any():
            return self.spiral_pitch, None
        best = min(best, self.spiral_pitch)
        # Pairs of one turn wrapping around the hole keep the clearance like different turns, but the checker only
        # compares them at least pi/2*(w + c) apart along the conductor, which depends on the result: such a pair rules
        # out the spacings s in (d, ds / (NEAR_FACTOR*pi/2)]. Different turns rule out every spacing above d.
        # The vias at the arms' ends (as wide as the trace, w = s - c, when no wider via is given) against the track of
        # their own arm, as in the checker: a via keeps the clearance (its center at least s from the track's center
        # line) from track of other turns, and from track of its own turn at least pi/2*s plus its radius along the
        # conductor from it, which rules out the spacings s in (d, (ds + c/2) / (NEAR_FACTOR*pi/2 + 1/2)].
        bound = np.concatenate([sd[~fold], vd[vsame]])
        reach = np.concatenate([np.where(sw[~fold] >= TURN_WINDING, inf, ss[~fold] / (NEAR_FACTOR * pi/2)),
                                np.where(vw[vsame] >= TURN_WINDING, inf,
                                         (vs[vsame] + clearance/2) / (NEAR_FACTOR * pi/2 + 0.5))])
        wat = np.concatenate([sat[~fold], vat[vsame]])
        # The largest spacing no pair rules out: go down to the smallest bound of the pairs that rule out the current
        # one, until none does
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
