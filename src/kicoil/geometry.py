
# Copyright 2025 Jan Sebastian Götte <code@jaseg.de>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import warnings
import logging
import itertools
from dataclasses import dataclass, field
import sys
from math import *

import numpy as np

from gerbonara.cad.kicad.footprints import Footprint
from gerbonara.cad.kicad.primitives import Zone, Hatch, ZoneKeepout, ZonePolygon, XYCoord

from . import kicad, skeletonator


mu_0 = 1.25663706127e-06 # from scipy.constants


def point_line_distance(p, l1, l2):
    x0, y0 = p
    x1, y1 = l1
    x2, y2 = l2
    # https://en.wikipedia.org/wiki/Distance_from_a_point_to_a_line
    return ((x2-x1)*(y1-y0) - (x1-x0)*(y2-y1)) / sqrt((x2-x1)**2 + (y2-y1)**2)


# https://en.wikipedia.org/wiki/Farey_sequence#Next_term
def farey_sequence(n: int, descending: bool = False) -> None:
    """Print the n'th Farey sequence. Allow for either ascending or descending."""
    a, b, c, d = 0, 1, 1, n
    if descending:
        a, c = 1, n - 1
    yield a, b

    while c <= n and not descending or a > 0 and descending:
        k = (n + b) // d
        a, b, c, d = c, d, k * c - a, k * d - b
        yield a, b


def divisors(n, max_b=10):
    for a, b in farey_sequence(n):
        if a != 0 and a == n and b < max_b:
            yield b
        if b != 1 and b == n and a < max_b:
            yield a


def arc_approximate(points, trace_width, layer, tolerance=0.02, level=0):
    """ Approximate spiral arm using circular arcs. This results in a smoother output using less segments than if we
    approximate the arc using straight line segments.

    The input to this function is a list of points of a straight line segment approximation, and it returns a list of
    gerbonara arc objects approximating the input. """ 
    indent = '    ' * level
    if len(points) < 3:
        raise ValueError('Need at least three points to approximate')

    i_mid = len(points)//2

    x0, y0 = points[0]
    x1, y1 = points[i_mid]
    x2, y2 = points[-1]

    if len(points) < 5:
        yield kicad.make_arc(x0, y0, x2, y2, x1, y1, trace_width, layer)
        return

    # https://stackoverflow.com/questions/56224824/how-do-i-find-the-circumcenter-of-the-triangle-using-python-without-external-lib
    d = 2 * (x0 * (y2 - y1) + x2 * (y1 - y0) + x1 * (y0 - y2))
    if abs(d) < 1e-12:
        # Collinear points, split until the pieces are short enough to be emitted as (nearly straight) arcs
        yield from arc_approximate(points[:i_mid+1], trace_width, layer, tolerance, level+1)
        yield from arc_approximate(points[i_mid:], trace_width, layer, tolerance, level+1)
        return
    cx = ((x0 * x0 + y0 * y0) * (y2 - y1) + (x2 * x2 + y2 * y2) * (y1 - y0) + (x1 * x1 + y1 * y1) * (y0 - y2)) / d
    cy = ((x0 * x0 + y0 * y0) * (x1 - x2) + (x2 * x2 + y2 * y2) * (x0 - x1) + (x1 * x1 + y1 * y1) * (x2 - x0)) / d
    r = dist((cx, cy), (x1, y1))
    if any(abs(dist((px, py), (cx, cy)) - r) > tolerance for px, py in points):
        yield from arc_approximate(points[:i_mid+1], trace_width, layer, tolerance, level+1)
        yield from arc_approximate(points[i_mid:], trace_width, layer, tolerance, level+1)

    else:
        if point_line_distance((x1, y1), (x0, y0), (x2, y2)) > 0:
            yield kicad.make_arc(x0, y0, x2, y2, x1, y1, trace_width, layer)
        else:
            yield kicad.make_arc(x2, y2, x0, y0, x1, y1, trace_width, layer)


def polygon_is_clockwise(coords):
    """ Orientation from the polygon's signed (shoelace) area. Works when the path repeats its start point. """
    return skeletonator.polygon_is_clockwise(coords)


def _seg_seg_distance(a, b, c, d):
    """ Minimum distance between line segments ab and cd """
    def orient(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0])
    d1, d2, d3, d4 = orient(c, d, a), orient(c, d, b), orient(a, b, c), orient(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and d1 != 0 and d2 != 0 and ((d3 > 0) != (d4 > 0)) and d3 != 0 and d4 != 0:
        return 0.0

    def pt_seg(p, s1, s2):
        dx, dy = s2[0]-s1[0], s2[1]-s1[1]
        l2 = dx*dx + dy*dy
        if l2 == 0:
            return dist(p, s1)
        t = max(0.0, min(1.0, ((p[0]-s1[0])*dx + (p[1]-s1[1])*dy) / l2))
        return dist(p, (s1[0] + t*dx, s1[1] + t*dy))

    return min(pt_seg(a, c, d), pt_seg(b, c, d), pt_seg(c, a, b), pt_seg(d, a, b))


def _split_by_angle(points, angles, max_span):
    """ Yield (p1, p2, t1, t2) for the segments of a polyline with point angles, skipping zero-length segments and
    splitting segments that span more than max_span revolutions. """
    for (p1, p2), (t1, t2) in zip(zip(points, points[1:]), zip(angles, angles[1:])):
        if p1 == p2:
            continue
        n = max(1, ceil(abs(t2 - t1) / max_span))
        for i in range(n):
            q1 = (p1[0] + (p2[0]-p1[0])*i/n, p1[1] + (p2[1]-p1[1])*i/n)
            q2 = (p1[0] + (p2[0]-p1[0])*(i+1)/n, p1[1] + (p2[1]-p1[1])*(i+1)/n)
            yield q1, q2, t1 + (t2-t1)*i/n, t1 + (t2-t1)*(i+1)/n


def _split_by_angle_np(points, angles, max_span):
    """ Vectorized `_split_by_angle`: returns arrays (q1, q2, u1, u2) of the pieces, with q1, q2 of shape (n, 2). """
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    ang = np.asarray(angles, dtype=float)
    a, b, ta, tb = pts[:-1], pts[1:], ang[:-1], ang[1:]
    keep = ~np.all(a == b, axis=1)
    a, b, ta, tb = a[keep], b[keep], ta[keep], tb[keep]
    n = np.maximum(1, np.ceil(np.abs(tb - ta) / max_span)).astype(np.int64)
    idx = np.repeat(np.arange(len(a)), n)
    k = np.arange(len(idx)) - np.repeat(np.cumsum(n) - n, n)
    nn = n[idx]
    f0, f1 = k / nn, (k + 1) / nn
    a, b, ta, tb = a[idx], b[idx], ta[idx], tb[idx]
    return (a + (b - a) * f0[:, None], a + (b - a) * f1[:, None], ta + (tb - ta) * f0, ta + (tb - ta) * f1)


def _point_seg_distance_np(p, s1, s2):
    d = s2 - s1
    l2 = np.einsum('ij,ij->i', d, d)
    t = np.einsum('ij,ij->i', p - s1, d) / np.where(l2 == 0, 1.0, l2)
    t = np.clip(np.where(l2 == 0, 0.0, t), 0.0, 1.0)
    return np.hypot(*(p - (s1 + d * t[:, None])).T)


def _seg_seg_distance_np(a, b, c, d):
    """ Vectorized `_seg_seg_distance` for arrays of segments ab and cd, shape (n, 2) each """
    def orient(p, q, r):
        return (q[:, 0]-p[:, 0])*(r[:, 1]-p[:, 1]) - (q[:, 1]-p[:, 1])*(r[:, 0]-p[:, 0])
    d1, d2, d3, d4 = orient(c, d, a), orient(c, d, b), orient(a, b, c), orient(a, b, d)
    crossing = (((d1 > 0) != (d2 > 0)) & (d1 != 0) & (d2 != 0) & ((d3 > 0) != (d4 > 0)) & (d3 != 0) & (d4 != 0))
    dist = np.minimum(np.minimum(_point_seg_distance_np(a, c, d), _point_seg_distance_np(b, c, d)),
                      np.minimum(_point_seg_distance_np(c, a, b), _point_seg_distance_np(d, a, b)))
    return np.where(crossing, 0.0, dist)


def _candidate_pairs(lo, hi, radius, max_pairs=1_000_000):
    """ Yield arrays (i, j), i < j, of all pairs of boxes [lo, hi] (arrays of shape (n, 2)) that come closer than radius,
    plus some pairs that do not, in batches of at most about max_pairs pairs (a crowded cell is split over several
    batches). Each pair is yielded once. Uses a uniform grid with cell size radius: every box, grown by radius/2, is
    entered into all cells it touches. Two boxes closer than radius share at least one cell, and a pair is only reported
    in the cell that contains the lower left corner of the intersection of the grown boxes. """
    n = len(lo)
    if n < 2:
        return
    cell = radius
    glo, ghi = lo - radius/2, hi + radius/2
    c0 = np.floor(glo / cell).astype(np.int64)
    c1 = np.floor(ghi / cell).astype(np.int64)
    cmin = c0.min(axis=0)
    c0, c1 = c0 - cmin, c1 - cmin
    width = int(c1[:, 1].max()) + 1
    c0x, c0y = c0[:, 0], c0[:, 1]
    nx, ny = c1[:, 0] - c0x + 1, c1[:, 1] - c0y + 1
    counts = nx * ny
    seg = np.repeat(np.arange(n), counts)
    k = np.arange(len(seg)) - np.repeat(np.cumsum(counts) - counts, counts)
    nys = ny[seg]
    keys = (c0x[seg] + k // nys) * width + c0y[seg] + k % nys
    order = np.argsort(keys, kind='stable')
    keys, seg = keys[order], seg[order]
    _uniq, starts, sizes = np.unique(keys, return_index=True, return_counts=True)
    # Every entry is paired with the entries after it in its cell. Process the entries in ranges of at most about
    # max_pairs pairs.
    partners_all = np.repeat(starts + sizes, sizes) - np.arange(len(keys)) - 1
    cum = np.cumsum(partners_all)
    gx, gy = glo[:, 0], glo[:, 1]
    p0 = 0
    while p0 < len(keys):
        base = cum[p0 - 1] if p0 else 0
        p1 = max(p0 + 1, int(np.searchsorted(cum, base + max_pairs, side='right')))
        partners = partners_all[p0:p1]
        pos = np.arange(p0, p1)
        p0 = p1
        total = int(partners.sum())
        if total == 0:
            continue
        I = np.repeat(pos, partners)
        J = I + 1 + (np.arange(total) - np.repeat(np.cumsum(partners) - partners, partners))
        si, sj = seg[I], seg[J]
        # Reference cell of the pair: the cell containing the lower left corner of the intersection of the grown boxes
        rx = np.floor(np.maximum(gx[si], gx[sj]) / cell).astype(np.int64) - cmin[0]
        ry = np.floor(np.maximum(gy[si], gy[sj]) / cell).astype(np.int64) - cmin[1]
        sel = (rx * width + ry) == keys[I]
        si, sj = si[sel], sj[sel]
        yield np.minimum(si, sj), np.maximum(si, sj)


def _box_gap(lox, loy, hix, hiy, i, j):
    """ Lower bound of the distance between the contents of boxes i and j (index arrays) """
    gx = np.maximum(0, np.maximum(lox[i] - hix[j], lox[j] - hix[i]))
    gy = np.maximum(0, np.maximum(loy[i] - hiy[j], loy[j] - hiy[i]))
    return np.hypot(gx, gy)


class FoldCandidates:
    """ Pairs of pieces of the same spiral turn that come close to each other although they are far apart along the
    conductor (see min_turn_spacing), kept as the Pareto front of (distance small, path separation large): for every
    path separation, the closest pair that is at least that far apart along the conductor. """

    def __init__(self):
        self.d = np.empty(0)
        self.path = np.empty(0)
        self.loc = np.empty((0, 2))

    def add(self, d, path, loc):
        d = np.concatenate([self.d, d])
        path = np.concatenate([self.path, path])
        loc = np.concatenate([self.loc, loc])
        order = np.lexsort((d, -path)) # path descending, then distance ascending
        d, path, loc = d[order], path[order], loc[order]
        # Keep entries whose distance is smaller than that of every entry with a larger path separation
        prev_min = np.concatenate([[inf], np.minimum.accumulate(d)[:-1]])
        keep = d < prev_min
        self.d, self.path, self.loc = d[keep], path[keep], loc[keep]

    def merge(self, other):
        self.add(other.d, other.path, other.loc)

    def closest(self, min_path):
        """ (distance, location) of the closest pair at least min_path apart along the conductor, or (inf, None) """
        sel = self.path > min_path
        if not sel.any():
            return inf, None
        k = int(np.flatnonzero(sel)[-1]) # path descending, distance descending along the front: the last one
        return float(self.d[k]), tuple(float(c) for c in self.loc[k])


def min_turn_spacing(arms, search_radius, min_turn_separation=0.5, folds=False, max_pairs=1_000_000):
    """ Find the smallest centerline distance between neighboring turns of a set of spiral arms on one layer.

    arms is a list of (points, angles) tuples, with angles in revolutions. Segments of different arms are always
    checked against each other. Segments of the same arm are only checked against each other when they are at least
    min_turn_separation revolutions apart, so that the arm's own bends do not count. Long segments are split so that
    this test is accurate to a tenth of min_turn_separation.

    Returns (distance, location). Distances above search_radius are not reported, (search_radius, None) is returned if
    nothing closer was found.

    With folds=True, also looks at pairs of pieces of the *same* turn (less than min_turn_separation apart) that are far
    apart along the conductor compared to their distance d: more than pi*d along the conductor (a U-turn of diameter d
    is (pi/2)*d long, a corner of angle a gives d/sin(a/2)). That happens where the turn runs around a narrow notch of
    the outline, or into a narrow tip, and comes back along the other side. Returns (distance, location, fold distance,
    fold location, fold candidates), where the fold distance and location are those of the closest pair that is more
    than pi*d + search_radius apart along the conductor, and the fold candidates (a `FoldCandidates`) allow asking for
    the closest pair more than a given distance apart along the conductor.

    The pieces are grouped into chunks of consecutive pieces of one arm (about search_radius/4 long), which are paired
    first, so that the pairs of pieces of one turn, which make up most of the pairs closer than search_radius on a
    finely subdivided outline, are skipped chunk by chunk. Memory use is bounded by max_pairs.
    """
    R = search_radius
    pieces = [_split_by_angle_np(points, angles, min_turn_separation / 10) for points, angles in arms]
    fold_front = FoldCandidates()
    if not pieces or not sum(len(q1) for q1, _q2, _u1, _u2 in pieces):
        return (R, None, R, None, fold_front) if folds else (R, None)
    P = np.concatenate([q1 for q1, _q2, _u1, _u2 in pieces])
    Q = np.concatenate([q2 for _q1, q2, _u1, _u2 in pieces])
    U1 = np.concatenate([u1 for _q1, _q2, u1, _u2 in pieces])
    U2 = np.concatenate([u2 for _q1, _q2, _u1, u2 in pieces])
    arm = np.concatenate([np.full(len(q1), i) for i, (q1, _q2, _u1, _u2) in enumerate(pieces)])
    tlo, thi = np.minimum(U1, U2), np.maximum(U1, U2)
    # Position along the conductor (per arm) at the start and end of every piece
    seg_len = np.hypot(*(Q - P).T)
    S1 = np.concatenate([np.cumsum(seg_len[arm == i]) for i in range(len(pieces))])
    S0 = S1 - seg_len
    # Cut pieces that are long compared to the search radius into shorter pieces for the spatial grid. The short pieces
    # keep the angle interval of the piece they belong to, so the same-turn test does not change.
    n_sub = np.maximum(1, np.ceil(seg_len / (4 * R))).astype(np.int64)
    if n_sub.max() > 1:
        idx = np.repeat(np.arange(len(P)), n_sub)
        k = (np.arange(len(idx)) - np.repeat(np.cumsum(n_sub) - n_sub, n_sub))[:, None]
        nn = n_sub[idx][:, None]
        P, Q = P[idx] + (Q[idx] - P[idx]) * (k / nn), P[idx] + (Q[idx] - P[idx]) * ((k + 1) / nn)
        S0, S1 = S0[idx] + (S1[idx] - S0[idx]) * (k / nn)[:, 0], S0[idx] + (S1[idx] - S0[idx]) * ((k + 1) / nn)[:, 0]
        tlo, thi, arm = tlo[idx], thi[idx], arm[idx]
    lo, hi = np.minimum(P, Q), np.maximum(P, Q)
    lox, loy, hix, hiy = lo[:, 0], lo[:, 1], hi[:, 0], hi[:, 1]
    n = len(P)

    # Chunks: runs of at most CHUNK consecutive pieces of one arm, about R/4 long
    CHUNK = 64
    local = np.arange(n) - np.searchsorted(arm, arm) # index within the arm (pieces are ordered by arm)
    new_chunk = np.ones(n, dtype=bool)
    new_chunk[1:] = ((arm[1:] != arm[:-1]) | (np.floor(S0[1:] / (R / 4)) != np.floor(S0[:-1] / (R / 4)))
                     | (local[1:] // CHUNK != local[:-1] // CHUNK))
    c_start = np.flatnonzero(new_chunk)
    c_size = np.diff(np.append(c_start, n))
    c_lox, c_loy = np.minimum.reduceat(lox, c_start), np.minimum.reduceat(loy, c_start)
    c_hix, c_hiy = np.maximum.reduceat(hix, c_start), np.maximum.reduceat(hiy, c_start)
    c_tlo, c_thi = np.minimum.reduceat(tlo, c_start), np.maximum.reduceat(thi, c_start)
    c_s0, c_s1 = np.minimum.reduceat(S0, c_start), np.maximum.reduceat(S1, c_start)
    c_arm = arm[c_start]
    nc = len(c_start)

    # Chunk pairs closer than R (plus every chunk with itself)
    ca_list, cb_list = [np.arange(nc)], [np.arange(nc)]
    for a, b in _candidate_pairs(np.stack([c_lox, c_loy], axis=1), np.stack([c_hix, c_hiy], axis=1), R):
        ca_list.append(a)
        cb_list.append(b)
    ca, cb = np.concatenate(ca_list), np.concatenate(cb_list)
    cgap = _box_gap(c_lox, c_loy, c_hix, c_hiy, ca, cb)
    same_arm = c_arm[ca] == c_arm[cb]
    # Every pair of pieces of the two chunks is less than min_turn_separation apart: all of them are the same turn
    all_same_turn = same_arm & (np.maximum(c_thi[cb] - c_tlo[ca], c_thi[ca] - c_tlo[cb]) < min_turn_separation)
    need_diff = ~all_same_turn & (cgap < R)
    if folds:
        # Fold candidates are more than pi*d apart along the conductor
        max_path = np.maximum(c_s1[cb] - c_s0[ca], c_s1[ca] - c_s0[cb])
        need_fold = same_arm & (cgap < R) & (max_path > pi * cgap)
    else:
        need_fold = np.zeros(len(ca), dtype=bool)
    keep = need_diff | need_fold
    order = np.argsort(cgap[keep], kind='stable') # closest first, so that the best distance drops quickly
    ca, cb, cgap = ca[keep][order], cb[keep][order], cgap[keep][order]
    need_diff, need_fold = need_diff[keep][order], need_fold[keep][order]

    best, where = R, None
    fold_best, fold_where = R, None
    npairs = c_size[ca] * c_size[cb]
    cum = np.cumsum(npairs)
    p0 = 0
    while p0 < len(ca):
        base = cum[p0 - 1] if p0 else 0
        p1 = max(p0 + 1, int(np.searchsorted(cum, base + max_pairs, side='right')))
        sl = slice(p0, p1)
        p0 = p1
        # Skip chunk pairs that cannot improve the result any more
        sel = (need_diff[sl] & (cgap[sl] < best)) | need_fold[sl]
        a, b = ca[sl][sel], cb[sl][sel]
        if not len(a):
            continue
        # Expand into pairs of pieces
        sa, sb = c_size[a], c_size[b]
        cnt = sa * sb
        rep = np.repeat(np.arange(len(a)), cnt)
        k = np.arange(len(rep)) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        i = c_start[a][rep] + k // sb[rep]
        j = c_start[b][rep] + k % sb[rep]
        pair_ok = (a[rep] != b[rep]) | (i < j)
        diff_ok = need_diff[sl][sel][rep]
        fold_ok = need_fold[sl][sel][rep]
        i, j, diff_ok, fold_ok = i[pair_ok], j[pair_ok], diff_ok[pair_ok], fold_ok[pair_ok]
        gap = _box_gap(lox, loy, hix, hiy, i, j)
        # Pieces of the same arm less than min_turn_separation apart belong to the same turn
        same_turn = (arm[i] == arm[j]) & (np.maximum(tlo[j] - thi[i], tlo[i] - thi[j]) < min_turn_separation)
        if folds:
            fsel = same_turn & fold_ok & (gap < R)
            fi, fj, fgap = i[fsel], j[fsel], gap[fsel]
            path = np.maximum(S0[fj] - S1[fi], S0[fi] - S1[fj])
            fsel = path > pi * fgap
            fi, fj, path = fi[fsel], fj[fsel], path[fsel]
            if len(fi):
                d = _seg_seg_distance_np(P[fi], Q[fi], P[fj], Q[fj])
                fsel = (path > pi * d + 1e-9 * R) & (d < R)
                fi, d, path = fi[fsel], d[fsel], path[fsel]
                if len(fi):
                    loc = (P[fi] + Q[fi]) / 2
                    fold_front.add(d, path, loc)
                    far = np.where(path > pi * d + R, d, inf)
                    kk = int(np.argmin(far))
                    if far[kk] < fold_best:
                        fold_best = float(far[kk])
                        fold_where = tuple(float(c) for c in loc[kk])
        dsel = ~same_turn & diff_ok & (gap < best)
        i, j = i[dsel], j[dsel]
        if not len(i):
            continue
        d = _seg_seg_distance_np(P[i], Q[i], P[j], Q[j])
        kk = int(np.argmin(d))
        if d[kk] < best:
            best = float(d[kk])
            where = tuple(float(c) for c in (P[i[kk]] + Q[i[kk]]) / 2)
    if folds:
        return best, where, fold_best, fold_where, fold_front
    return best, where


class Shape:
    # How far the inner via ring may be moved inwards from the innermost turn
    max_via_offset = inf


@dataclass
class CircleShape(Shape):
    outer_diameter: float
    inner_diameter: float


    def __post_init__(self):
        self.outer_radius = self.outer_diameter / 2
        self.inner_radius = self.inner_diameter / 2
        # The inner via ring must not pass the center (it would end up on the opposite side)
        self.max_via_offset = self.inner_radius


    @property
    def slug(self):
        return f'circle_{self.outer_diameter:.2f}x{self.inner_diameter:.2f}'


    @property
    def desc(self):
        return f'{self.outer_diameter:.2f} mm OD, {self.inner_diameter:.2f} mm ID circular'


    def compute_spiral(self, a1, a2, fn=64, debug=False):
        r1, r2 = self.outer_radius, self.inner_radius
        fn = ceil(fn * abs(a2-a1)/(2*pi))
        x0, y0 = cos(a1)*r1, sin(a1)*r1
        dr = 3 if r2 < r1 else -3

        xn, yn = x0, y0
        points = [(x0, y0)]
        dists = []
        for i in range(fn):
            xp, yp = xn, yn
            r = r1 + (i+1)*(r2-r1)/fn
            a = a1 + (i+1)*(a2-a1)/fn
            xn, yn = cos(a)*r, sin(a)*r
            points.append((xn, yn))
            dists.append(dist((xp, yp), (xn, yn)))

        return points, sum(dists), [None]*len(points)


    def compute_spiral_t(self, a1, a2, tolerance=0.0005):
        """ Spiral center line from angle a1 on the outer radius to angle a2 on the inner radius with a maximum chord error
        of `tolerance`, plus each point's angle in revolutions. """
        fn = max(16, ceil(pi / acos(1 - tolerance/self.outer_radius)))
        points, _length, _refs = self.compute_spiral(a1, a2, fn=fn)
        n = len(points) - 1
        return points, [(a1 + i*(a2-a1)/n) / (2*pi) for i in range(n+1)]

    def project_point(self, r, a, r_ref=None):
        return cos(a) * r, sin(a) * r


    def offset_exterior(self, margin):
        r = self.outer_radius + margin
        tol = 0.05 # mm
        n = ceil(pi / acos(1 - tol/r))
        return [(r*cos(a*2*pi/n), r*sin(a*2*pi/n)) for a in range(n)]


class OffsetShape(Shape):
    def __post_init__(self):
        self.sk = skeletonator.Skeletonator(self.polygon)
        # The skeletonator normalizes the outline (counter-clockwise, no repeated points). Use the same outline here, so
        # that vertex indices agree.
        self.polygon = list(self.sk.poly)
        if self.annular_width >= self.sk.max_depth:
            raise ValueError(f'Annular width ({self.annular_width:.2f}) is too large. Must be less than {self.sk.max_depth:.2f}')
        if self.annular_width <= 0:
            raise ValueError(f'Annular width must be positive')
        self.sk.set_angle_reference(self.annular_width)
        self.max_via_offset = self.sk.max_depth - self.annular_width
        self.outer_radius = self.sk.radius
        self.inner_radius = self.sk.radius - self.annular_width

    def set_fold_limit(self, limit):
        """ Turns closer than `limit` to the collapse depth of a narrow protrusion of the outline cut across the
        protrusion's mouth instead of running into it and folding onto themselves. See Skeletonator.set_fold_limit. """
        self.sk.set_fold_limit(limit)

    @property
    def slug(self):
        return f'polygonal_{len(self.polygon)}pt_a{self.annular_width:.2f}mm'


    @property
    def desc(self):
        return f'polygonal (n={len(self.polygon)} point, {self.annular_width:.2f} mm annular width)'


    def compute_spiral(self, a1, a2, fn=None, debug=False):
        # Skeletonator uses a t coordinate from 0 - 1 per revolution instead of a radian angle.
        points = []
        angle_refs = []
        for point, angle_ref in self.sk.do_spiral(a1/(2*pi), a2/(2*pi), self.outer_radius, self.inner_radius, debug=debug):
            points.append(point)
            angle_refs.append(angle_ref)
        if a2 < a1:
            points = points[::-1]
            angle_refs = angle_refs[::-1]
        arm_length = sum(dist(p1, p2) for p1, p2 in zip(points, points[1:]))
        return points, arm_length, angle_refs


    def compute_spiral_t(self, a1, a2, fn=None):
        """ Spiral center line from angle a1 on the outer radius to angle a2 on the inner radius, plus each point's angle
        in revolutions. """
        t1, t2 = a1/(2*pi), a2/(2*pi)
        if t1 <= t2:
            return self.sk.spiral(t1, t2, 0, self.annular_width)
        points, angles = self.sk.spiral(t2, t1, self.annular_width, 0)
        return points[::-1], angles[::-1]

    def project_point(self, r, a, r_ref=None):
        # Skeletonator uses a t coordinate from 0 - 1 per revolution instead of a radian angle.
        return self.sk.project_point(a/(2*pi) % 1, r, r_ref=r_ref)


    KEEPOUT_MITER_LIMIT = 2.0 # keepout corners are cut off at this multiple of the margin from the outline's corner

    def offset_exterior(self, margin):
        """ Outline offset outwards by margin (inwards for a negative margin), e.g. for the keepout zone. """
        if margin > 0:
            # Extrapolating the skeleton tracks outwards is only valid up to the first event of the exterior skeleton,
            # so compute a real polygon offset.
            return skeletonator.offset_polygon_outward(self.polygon, margin, miter_limit=self.KEEPOUT_MITER_LIMIT)
        # do_spiral returns the closing point twice
        return [p for p, _r_ref in self.sk.do_spiral(0, 1, self.outer_radius + margin, self.outer_radius + margin)][:-1]


@dataclass
class TrapezoidShape(OffsetShape):
    width: float
    height: float
    offset: float
    annular_width: float
    arc_tolerance: float = 0.05 # mm
    polygon: list = field(init=False)

    def __post_init__(self):
        w, h, d = self.width, self.height, self.offset
        self.polygon = [(w/2-d, -h/2), (w/2, h/2), (-w/2, h/2), (-w/2+d, -h/2)]
        super().__post_init__()
    
    @property
    def slug(self):
        return f'trapezoid_{self.width:.2f}-2*{self.offset:.2f}x{self.height:.2f}'
    
    @property
    def desc(self):
        return f'{self.width:.2f} x {self.height:.2f} mm, {self.offset:.2f} mm offset isosceles trapezoidal'


@dataclass
class RectangleShape(OffsetShape):
    width: float
    height: float
    annular_width: float
    arc_tolerance: float = 0.05 # mm
    polygon: list = field(init=False)

    def __post_init__(self):
        w, h = self.width, self.height
        self.polygon = [(w/2, -h/2), (w/2, h/2), (-w/2, h/2), (-w/2, -h/2)]
        super().__post_init__()
    
    @property
    def slug(self):
        return f'rectangle_{self.width:.2f}x{self.height:.2f}'
    
    @property
    def desc(self):
        return f'{self.width:.2f} x {self.height:.2f} mm rectangle'

@dataclass
class SectorShape(OffsetShape):
    inner_diameter: float
    outer_diameter: float
    angle: float
    annular_width: float
    arc_tolerance: float = 0.05 # mm
    polygon: list = field(init=False)

    def __post_init__(self):
        # Careful: The inner/outer radius properties are relative to the polygon center and are very different from these!
        r1, r2 = self.inner_diameter / 2, self.outer_diameter/2
        n1 = ceil(pi / acos(1 - self.arc_tolerance/self.inner_diameter) * self.angle / (2*pi))
        n2 = ceil(pi / acos(1 - self.arc_tolerance/self.outer_diameter) * self.angle / (2*pi))
        # center on y axis
        pt = lambda r, a: (r*sin(a), r*cos(a))
        self.polygon  = [pt(r2, self.angle/2 - i/n1 * self.angle) for i in range(n1+1)]
        self.polygon += [pt(r1, i/n1 * self.angle - self.angle/2) for i in range(n1+1)]
        super().__post_init__()
    
    @property
    def slug(self):
        return f'sector_{self.outer_diameter:.2f}x{self.inner_diameter:.2f}_{degrees(self.angle):.0f}deg'
    
    @property
    def desc(self):
        return f'{self.outer_diameter:.2f} x {self.inner_diameter:.2f} mm {degrees(self.angle):.0f} deg sector'


@dataclass
class StarShape(OffsetShape):
    inner_diameter: float
    outer_diameter: float
    annular_width: float
    points: int = 5
    arc_tolerance: float = 0.05 # mm
    polygon: list = field(init=False)

    def __post_init__(self):
        # center on y axis
        pt = lambda r, a: (-r*sin(a), r*cos(a))
        circle = lambda r, n, phase: [pt(r, (i + phase)*2*pi/n) for i in range(n)]
        self.polygon  = [x for pair in zip(circle(self.outer_diameter/2, self.points, 0), circle(self.inner_diameter/2, self.points, 0.5)) for x in pair]
        super().__post_init__()
    
    @property
    def slug(self):
        return f'star_{self.outer_diameter:.2f}x{self.inner_diameter:.2f}'
    
    @property
    def desc(self):
        purpose = ', for demonic purposes' if self.points == 5 else ''
        return f'{self.outer_diameter:.2f} x {self.inner_diameter:.2f} mm star shape{purpose}'


@dataclass
class RegularPolygonShape(OffsetShape):
    diameter: float
    annular_width: float
    corners: int = 8
    arc_tolerance: float = 0.05 # mm
    polygon: list = field(init=False)

    def __post_init__(self):
        # center on y axis
        pt = lambda r, a: (-r*sin(a), r*cos(a))
        circle = lambda r, n, phase: [pt(r, (i + phase)*2*pi/n) for i in range(n)]
        self.polygon  = list(circle(self.diameter/2, self.corners, 0))
        super().__post_init__()
    
    @property
    def slug(self):
        return f'regular_{self.corners}gon_{self.diameter:.2f}'
    
    @property
    def desc(self):
        return f'{self.diameter:.2f} mm diameter {self.corners} corner regular polygon'


@dataclass
class SVGShape(OffsetShape):
    filename: str
    annular_width: float
    arc_tolerance: float = 0.05 # mm
    polygon: list = field(init=False)

    def __post_init__(self):
        # center on y axis
        from bs4 import BeautifulSoup
        with open(self.filename) as f:
            soup = BeautifulSoup(f.read(), features='xml')
            path = soup.find('path', recursive=True)
            d = path.attrs['d']
            d = d.strip('MmZ ').replace(',', 'L')
            coord_pairs = d.split('L')
            coords = [tuple(map(float, pair.split())) for pair in coord_pairs]
            
        if polygon_is_clockwise(coords):
            coords = coords[::-1]
            
        # Calculate bounding box
        min_x = min(x for x, _y in coords)
        max_x = max(x for x, _y in coords)
        min_y = min(y for _x, y in coords)
        max_y = max(y for _x, y in coords)
        if max_x < 0 or max_y < 0 or min_x > 0 or min_y > 0:
            # (0, 0) is not within the polygon's axis-aligned bounding box, recenter.
            ox, oy = skeletonator.polygon_center_of_mass(coords)
            warnings.warn(f'Polygon looks not centered, bounds are ({min_x:.2f}, {min_y:.2f}), ({max_x:.2f}, {max_y:.2f}). Aligning (0, 0) with polygon centroid at ({ox:.2f}, {oy:.2f})')
            coords = [(x-ox, y-oy) for x, y in coords]
        
        self.polygon  = coords
        super().__post_init__()
    
    @property
    def slug(self):
        return f'svg_{len(self.polygon)}n'
    
    @property
    def desc(self):
        return f'{len(self.polygon)} node imported SVG shape'

@dataclass
class PlanarInductor():
    shape: Shape
    turns: int
    twists: int
    trace_width: float = None
    clearance: float = None
    layers: int = 2
    via_diameter: float = 0.6
    via_drill: float = None
    via_offset: float = None
    stagger_inner_vias: bool = False
    stagger_outer_vias: bool = False
    keepout_zone: bool = True
    keepout_margin: float = 0.0
    copper_thickness: float = 0.035
    layer_pair: str = 'F.Cu,B.Cu'
    clockwise: bool = False
    approximate_arcs: bool = True

    def __post_init__(self):
        self.logger = logging.getLogger('kicoil')

        if self.turns < 1:
            raise ValueError(f'Error: PlanarInductor.turns must be 1 or more')

        if self.twists < 1:
            raise ValueError(f'Error: PlanarInductor.twists must be 1 or more')

        if self.layers == 1 and self.twists > 1:
            warnings.warn('Warning: Twists set to a value other than 1, but single-layer mode is enabled. The twists value will be ignored.')
            self.twists = 1

        self.turns_per_layer = self.turns/self.layers
        self.sector_angle = 2*pi / self.twists

        if self.clockwise:
            self.sector_angle *= -1
            
        self.sweeping_angle = self.sector_angle * self.turns_per_layer
        self.spiral_pitch = (self.shape.outer_radius-self.shape.inner_radius) / self.turns_per_layer
        self.R = None # will be calculated during render

        if gcd(self.twists, self.turns) != 1:
            raise ValueError(f'For the geometry to work out, the twists parameter must be co-prime to turns, i.e. the two must have 1 as their greatest common divisor. You can print valid values for twists by running the kicoil CLI with --show-twists [turns number].\n\n'
                                       f'Right now, both are divisible by {gcd(self.twists, self.turns)}.\n'
                                       f'Valid twist counts for n={self.turns} turns are: {list(divisors(self.turns, max(self.turns, 25)))}\n'
                                       f'Valid turn counts for k={self.twists} twists are: {list(divisors(self.twists, max(self.twists, 25)))}')

        if (self.stagger_inner_vias or self.stagger_outer_vias) and self.twists%2 != 0:
            raise ValueError('For via staggering to work, twists must be even and turns must be odd.')

        self._prepare_shape()

        # The distance between neighboring turns is less than the nominal spiral pitch, since the turns run at an angle
        # to the outline, and since at corners the spiral's bends do not line up exactly between turns. Instead of
        # estimating this, measure the actual spiral center lines.
        self.projected_spiral_pitch, self.min_pitch_location = self.measure_turn_spacing()
        self.logger.info(f'Nominal spiral pitch {self.spiral_pitch:.3f} mm, '
                         f'smallest distance between turns {self.projected_spiral_pitch:.3f} mm.')

        pp = self.projected_spiral_pitch
        if self.min_pitch_location is not None and round(pp, 3) < round(self.spiral_pitch, 3):
            x, y = self.min_pitch_location
            pitch_hint = (f' The projected pitch is the smallest distance between the center lines of neighboring '
                          f'turns, {pp:.3f} mm (nominal pitch {self.spiral_pitch:.3f} mm), measured near '
                          f'({x:.3f}, {y:.3f}).')
            if pp < 0.5 * self.spiral_pitch:
                pitch_hint += (' This happens when the annular width reaches into a narrow part of the outline that '
                               'collapses before the innermost turn; a smaller annular width or fewer twists avoid it.')
            else:
                pitch_hint += (' Turns come closer than the nominal pitch at corners and where the spiral runs at a '
                               'steep angle (many twists).')
        else:
            pitch_hint = ''

        if self.trace_width is None and self.clearance is None:
            self.clearance = 0.15
            warnings.warn(f'Warning: Neither trace width nor clearance given. Defaulting to {self.clearance:.3f} mm clearance.')

        if self.trace_width is None:
            if round(self.clearance, 3) >= round(pp, 3):
                raise ValueError(f'Given clearance of {self.clearance:.3f} mm is larger than the projected spiral pitch '
                                 f'of {pp:.3f} mm. Reduce clearance or increase the size of the coil.' + pitch_hint)
            self.trace_width = pp - self.clearance
            self.logger.info(f'Calculated trace width for {self.clearance:.3f} mm clearance is {self.trace_width:.3f} mm.')

        elif self.clearance is None:
            if round(self.trace_width, 3) >= round(pp, 3):
                raise ValueError(f'Given trace width of {self.trace_width:.3f} mm is larger than the projected spiral '
                                 f'pitch of {pp:.3f} mm. Reduce trace width or increase the size of the coil.' + pitch_hint)
            self.clearance = pp - self.trace_width
            self.logger.info(f'Calculated clearance for {self.trace_width:.3f} mm trace width is {self.clearance:.3f} mm.')

        else:
            if round(self.trace_width, 3) >= round(pp, 3):
                raise ValueError(f'Given trace width of {self.trace_width:.3f} mm is larger than the projected spiral '
                                 f'pitch of {pp:.3f} mm. Reduce trace width or increase the size of the coil.' + pitch_hint)
            clearance_actual = pp - self.trace_width
            if round(clearance_actual, 3) < round(self.clearance, 3):
                raise ValueError(f'Actual clearance for {self.trace_width:.3f} mm trace width is {clearance_actual:.3f} '
                                 f'mm, which is lower than the given clearance of {self.clearance:.3f} mm. Reduce trace '
                                 f'width to at most {floor((pp - self.clearance) * 1000) / 1000:.3f} mm, reduce the '
                                 f'clearance or increase the size of the coil.' + pitch_hint)

        # Copper of one turn folding onto itself: two pieces of the same turn closer than trace width plus clearance
        # that are more than pi*d plus the pitch apart along the conductor (folds around notches), or more than
        # 4*(trace width + clearance) (converging sides of a tapered tip; the geometric checker counts pieces of copper
        # that far apart along the conductor as different turns). Subclasses with their own measure_turn_spacing may
        # not measure folds.
        fold_location, fold_spacing = getattr(self, 'min_fold_location', None), getattr(self, 'min_fold_spacing', inf)
        candidates = getattr(self, 'fold_candidates', None)
        if candidates is not None:
            d, loc = candidates.closest(4 * (self.trace_width + self.clearance))
            if loc is not None and d < fold_spacing:
                fold_spacing, fold_location = d, loc
        if fold_location is not None and fold_spacing < self.trace_width + self.clearance - 1e-6:
            x, y = fold_location
            gap = fold_spacing - self.trace_width
            what = f'overlaps itself by {-gap:.3f} mm' if gap < 0 else f'comes within {gap:.3f} mm of itself'
            warnings.warn(f'Near ({x:.3f}, {y:.3f}) the copper of one turn {what}: the turn runs around a part of '
                          f'the outline that is narrower than the turn pitch (a narrow notch or slot, or a narrow tip the '
                          f'annulus reaches deep into) and comes back along its other side. This does not short '
                          f'different turns, but the copper of that turn folds onto itself. Widen that part of the '
                          f'outline, reduce the annular width, or use fewer turns or a smaller trace width.')

        if round(self.via_diameter, 2) < round(self.trace_width, 2):
            self.logger.warning(f'Clipping via diameter from {self.via_diameter:.2f} mm to trace width of {self.trace_width:.2f} mm.')
            self.via_diameter = self.trace_width

        if self.via_drill is None:
            self.via_drill = max(self.via_diameter / 2, self.via_diameter - 1.2)
            self.logger.warning(f'No via drill given, defaulting to {self.via_drill:.2f} mm based on via diameter.')

        # The inner via ring must not go past the center of a circle or the collapse depth of a polygon outline. A
        # staggered inner ring reaches three times the via offset inwards.
        inner_reach = 3 if self.stagger_inner_vias else 1
        max_offset = self.shape.max_via_offset / inner_reach

        auto_via_offset = self.via_offset is None
        if auto_via_offset:
            self.via_offset = min(max(0, (self.via_diameter - self.trace_width)/2), max_offset)
            self.logger.info(f'Autocalculated via offset {self.via_offset:.2f} mm')

        if isclose(self.via_offset, 0, abs_tol=1e-6):
            self.via_offset = 0

        # Vias that are wider than the trace can come too close to a neighboring turn when that turn runs at an angle.
        # When the via offset is calculated automatically, move the vias further away from the turns until they clear.
        # Moving the inner vias inwards also moves them closer together, so stop when that would make them overlap.
        gap, where = self.via_track_clearance()
        for _ in range(10):
            if gap >= self.clearance - 1e-6 or not auto_via_offset:
                break
            old_offset = self.via_offset
            self.via_offset = min(max_offset, self.via_offset + self.clearance - gap + 1e-4)
            new_gap, new_where = self.via_track_clearance()
            if self.via_offset <= old_offset or new_gap <= gap or self.via_ring_spacing() < self.via_diameter + self.clearance:
                self.via_offset = old_offset
                break
            gap, where = new_gap, new_where
            self.logger.info(f'Increased via offset to {self.via_offset:.2f} mm to keep vias clear of neighboring turns')
        if gap < self.clearance - 1e-6:
            if gap < 0:
                problem = (f'overlaps a neighboring turn by {-gap:.3f} mm (a clearance of {self.clearance:.3f} mm is '
                           f'required)')
            else:
                problem = (f'is only {gap:.3f} mm away from a neighboring turn, which is less than the clearance of '
                           f'{self.clearance:.3f} mm')
            warnings.warn(f'Via at ({where[0]:.3f}, {where[1]:.3f}) {problem}. ' +
                          ('Reduce the via diameter or the annular width.' if auto_via_offset else
                           'Increase the via offset or reduce the via diameter.'))
        if self.via_offset * inner_reach > self.shape.max_via_offset + 1e-9:
            warnings.warn(f'The inner vias are {self.via_offset * inner_reach:.3f} mm inside the innermost turn, which '
                          f'is beyond the center of the shape ({self.shape.max_via_offset:.3f} mm). Reduce the via '
                          f'offset or the annular width.')

        self.inner_via_ring_radius = self.shape.inner_radius - self.via_offset
        self.outer_via_ring_radius = self.shape.outer_radius + self.via_offset
        self.logger.info(f'Inner via ring @r={self.inner_via_ring_radius:.2f} mm (from {self.shape.inner_radius:.2f} mm)')
        self.logger.info(f'Outer via ring @r={self.outer_via_ring_radius:.2f} mm (from {self.shape.outer_radius:.2f} mm)')

        # Check if the vias of the inner or outer ring are so large that they would overlap. This uses the actual via
        # positions, so it works for any shape.
        closest = self.via_ring_spacing()
        if closest < self.via_diameter + self.clearance - 1e-6:
            warnings.warn(f'Overlapping vias: vias are {closest:.2f} mm apart, but need '
                          f'{self.via_diameter + self.clearance:.2f} mm (via diameter plus clearance). '
                          f'Reduce the annular width, the via diameter or the number of twists.')

        t, _, b = self.layer_pair.partition(',')
        self.layer_pair = (t.strip(), b.strip())

        # For fill factor & inductance formulas, See https://coil32.net/pcb-coil.html for details
        d_avg = (2*self.shape.outer_radius + self.shape.inner_radius)/2
        phi = (2*self.shape.outer_radius - 2*self.shape.inner_radius) / (2*self.shape.outer_radius + 2*self.shape.inner_radius)
        c1, c2, c3, c4 = 1.00, 2.46, 0.00, 0.20 # FIXME for other shapes
        self.L = mu_0 * self.turns**2 * d_avg*1e3 * c1 / 2 * (log(c2/phi) + c3*phi + c4*phi**2)
        self.logger.info(f'Outer diameter: {2*self.shape.outer_radius:g} mm')
        self.logger.info(f'Average diameter: {d_avg:g} mm')
        self.logger.info(f'Inner diameter: {2*self.shape.inner_radius:g} mm')
        self.logger.info(f'Fill factor: {phi:g}')
        self.logger.info(f'Approximate inductance: {self.L:g} µH')

        # One arm runs from the outside to the inside of a layer
        _points, arm_length, _angle_refs = self.shape.compute_spiral(a1=0, a2=self.sweeping_angle)

        self.track_length = arm_length*self.twists*self.layers
        self.logger.info(f'Approximate track length: {self.track_length:.2f} mm')

        A = self.copper_thickness/1e3 * self.trace_width/1e3 # trace cross-section area
        rho = 1.68e-8 # specific resistivity of copper
        self.R = self.track_length/1e3 * rho / A
        self.logger.info(f'Approximate resistance: {self.R:g} Ω')

    def _prepare_shape(self):
        """ Configure the shape for this coil's pitch: turns that would run into a protrusion of the outline narrower
        than one pitch cut across it instead. Called again before rendering, in case the shape object was used for
        another coil in between. """
        set_fold_limit = getattr(self.shape, 'set_fold_limit', None)
        if set_fold_limit is None:
            return
        set_fold_limit(self.spiral_pitch / 2)
        sk = getattr(self.shape, 'sk', None)
        if sk is None or getattr(self, '_fold_reported', False):
            return
        self._fold_reported = True
        for x, y, depth, cut_depth in getattr(sk, 'cut_protrusions', ()):
            if cut_depth < self.shape.annular_width:
                self.logger.info(f'The outline has a narrow part that collapses at a depth of {depth:.3f} mm near '
                                 f'({x:.3f}, {y:.3f}). Turns deeper than {cut_depth:.3f} mm cut across its base instead '
                                 f'of running into it, since its sides would be less than one pitch apart.')
        for x, y, depth in getattr(sk, 'uncut_protrusions', ()):
            if depth < self.shape.annular_width:
                warnings.warn(f'The outline has a narrow part that collapses at a depth of {depth:.3f} mm near '
                              f'({x:.3f}, {y:.3f}), inside the annular width. Turns running into it fold onto '
                              f'themselves (copper of the same turn overlaps). Reduce the annular width below '
                              f'{depth:.3f} mm or widen that part of the outline.')

    def arm_angles(self, i):
        """ Start, fold and end angle of the i'th arm pair. The arm on the first layer runs inwards from the start to the
        fold angle, the arm on the second layer runs outwards from the fold to the end angle. """
        start_angle = i*self.sector_angle
        fold_angle = start_angle + self.sweeping_angle
        end_angle = fold_angle + self.sweeping_angle
        return start_angle, fold_angle, end_angle

    def spiral_center_lines(self):
        """ Center lines of all spiral arms as [layer 0 arms, layer 1 arms], each arm a (points, angles) tuple. Arms on
        layer 0 run from the start to the fold angle, arms on layer 1 from the end to the fold angle. """
        if getattr(self, '_center_lines', None) is None:
            arms = [[], []]
            for i in range(self.twists):
                start_angle, fold_angle, end_angle = self.arm_angles(i)
                arms[0].append(self.shape.compute_spiral_t(start_angle, fold_angle))
                if self.layers > 1:
                    arms[1].append(self.shape.compute_spiral_t(end_angle, fold_angle))
            self._center_lines = arms
        return self._center_lines

    def via_ring_spacing(self):
        """ Smallest center distance between any two vias for the current via offset """
        self.inner_via_ring_radius = self.shape.inner_radius - self.via_offset
        self.outer_via_ring_radius = self.shape.outer_radius + self.via_offset
        inner, outer = self.via_positions()
        return min((dist(p, q) for p, q in itertools.combinations(inner + outer, 2)), default=inf)

    def via_track_clearance(self):
        """ Smallest edge-to-edge distance between a via and a turn of a spiral arm (other than the turn the via connects
        to), using the current via offset and trace width. Returns (gap, via position). """
        inner_r = self.shape.inner_radius - self.via_offset
        outer_r = self.shape.outer_radius + self.via_offset
        vias = [] # (position, {(layer, arm index): angle in revolutions where the arm connects to the via})
        for i in range(self.twists):
            start_angle, fold_angle, _end_angle = self.arm_angles(i)
            r = inner_r - (2*self.via_offset if self.stagger_inner_vias and i%2 != 0 else 0)
            vias.append((self.shape.project_point(r, fold_angle), {(0, i): fold_angle/(2*pi), (1, i): fold_angle/(2*pi)}))
            if i > 0:
                j = (i - self.turns) % self.twists
                r = outer_r + (2*self.via_offset if self.stagger_outer_vias and i%2 != 0 else 0)
                vias.append((self.shape.project_point(r, start_angle),
                             {(0, i): start_angle/(2*pi), (1, j): self.arm_angles(j)[2]/(2*pi)}))

        center_lines = self.spiral_center_lines()
        cached = getattr(self, '_via_pieces', None)
        if cached is None or cached[0] is not center_lines:
            # Arm center lines split into pieces of at most 0.05 revolutions, so that the part of an arm that leads into
            # a via can be skipped accurately. Cached for the via offset search, which calls this repeatedly.
            cached = self._via_pieces = (center_lines, {
                (layer, arm): _split_by_angle_np(points, angles, 0.05)
                for layer, layer_arms in enumerate(center_lines) for arm, (points, angles) in enumerate(layer_arms)})
        best, where = inf, None
        for (layer, arm), (p1, p2, t1, t2) in cached[1].items():
            if not len(p1):
                continue
            for v, connections in vias:
                # Skip the part of an arm that leads into the via itself
                tv = connections.get((layer, arm))
                if tv is not None:
                    sel = ~((np.abs(t1 - tv) < 0.5) & (np.abs(t2 - tv) < 0.5))
                    a, b = p1[sel], p2[sel]
                    if not len(a):
                        continue
                else:
                    a, b = p1, p2
                d = float(_point_seg_distance_np(np.broadcast_to(np.asarray(v, dtype=float), a.shape), a, b).min())
                if d < best:
                    best, where = d, v
        return best - self.via_diameter/2 - self.trace_width/2, where

    def measure_turn_spacing(self):
        """ Smallest center line distance between neighboring turns on the same layer, and where it occurs """
        arms = self.spiral_center_lines()
        # The result is capped at the nominal pitch, so nothing further away needs to be looked at
        search_radius = self.spiral_pitch * (1 + 1e-9)
        results = [min_turn_spacing(layer_arms, search_radius, folds=True) for layer_arms in arms if layer_arms]
        best, where = min(((r[0], r[1]) for r in results), key=lambda r: r[0])
        # Same turn folding onto itself, e.g. around a notch of the outline narrower than the pitch. This does not
        # short different turns, so it does not limit the trace width, but it is reported as a warning.
        self.min_fold_spacing, self.min_fold_location = min(((r[2], r[3]) for r in results), key=lambda r: r[0])
        self.fold_candidates = FoldCandidates()
        for r in results:
            self.fold_candidates.merge(r[4])
        if where is None:
            # Nothing closer than the search radius: e.g. less than a single turn per layer. Fall back to the nominal
            # pitch.
            return self.spiral_pitch, None
        return min(best, self.spiral_pitch), where

    def via_positions(self):
        """ Positions of the inner and outer via rings. The outer ring's first entry is where the pads are. """
        inner, outer = [], []
        for i in range(self.twists):
            start_angle, fold_angle, _end_angle = self.arm_angles(i)
            r = self.inner_via_ring_radius
            if self.stagger_inner_vias and i%2 != 0:
                r -= 2*self.via_offset
            inner.append(self.shape.project_point(r, fold_angle))

            r = self.outer_via_ring_radius
            if self.stagger_outer_vias and i%2 != 0:
                r += 2*self.via_offset
            outer.append(self.shape.project_point(r, start_angle))
        return inner, outer[1:]

    @property
    def default_footprint_name(self):
        return f'planar-coil-{self.shape.slug}-n{self.turns}-k{self.twists}'

    DEFAULT_ARC_TOLERANCE = 0.02 # mm
    DEFAULT_CIRCLE_SEGMENTS = 64 # per revolution
    MIN_ARC_FIT_SEGMENTS = 256 # points per revolution the arc approximation of circles is fitted to
    RENDER_TOLERANCE_FLOOR = 0.0005 # mm, smallest arc tolerance / chord error, used when the clearance is (nearly) 0

    def effective_render_options(self, arc_tolerance=None, circle_segments=None):
        """ Arc tolerance and number of segments per revolution that render_footprint actually uses for circles, given
        the user's values (None: automatic). The trace width is sized from the exact spiral center lines, so the
        approximation must not eat up a noticeable part of the clearance. Both neighboring turns may deviate by the
        tolerance towards each other, so the tolerance is at most clearance/80 (at least RENDER_TOLERANCE_FLOOR), which
        bounds the loss to clearance/40: the arc tolerance is capped at that value, arcs are fitted to at least 256
        points per revolution, and polylines (approximate_arcs=False) get enough segments for a chord error within it.
        Returns (arc_tolerance, circle_segments, notes), where notes lists the user values that were overridden. Only
        circles use these settings; other shapes get no notes. """
        notes = []
        tol_limit = self.render_tolerance_limit()
        user_tol, user_segs = arc_tolerance, circle_segments
        arc_tolerance = min(self.DEFAULT_ARC_TOLERANCE if user_tol is None else user_tol, tol_limit)
        circle_segments = self.DEFAULT_CIRCLE_SEGMENTS if user_segs is None else user_segs
        if not isinstance(self.shape, CircleShape):
            return arc_tolerance, circle_segments, notes

        if self.approximate_arcs:
            if user_tol is not None and user_tol > tol_limit:
                notes.append(f'arc tolerance reduced from {user_tol:.4f} mm to {tol_limit:.4f} mm '
                             f'({self.render_tolerance_desc()})')
            needed = self.MIN_ARC_FIT_SEGMENTS
        else:
            # Chord error r*(1 - cos(pi/n)) <= tol_limit on the outer radius
            needed = ceil(pi / acos(max(-1.0, 1 - tol_limit / self.shape.outer_radius)))
        if circle_segments < needed:
            if user_segs is not None:
                notes.append(f'circle segments raised from {user_segs} to {needed} per revolution to keep the '
                             f'{"arc fit" if self.approximate_arcs else "chord error"} within '
                             f'{tol_limit:.4f} mm ({self.render_tolerance_desc()})')
            circle_segments = needed
        return arc_tolerance, circle_segments, notes

    def render_tolerance_limit(self):
        """ Largest deviation of the rendered circle tracks from the exact spiral: clearance/80, at least
        RENDER_TOLERANCE_FLOOR (so that clearance 0 still gives a finite number of segments). """
        return max(self.clearance / 80, self.RENDER_TOLERANCE_FLOOR)

    def render_tolerance_desc(self):
        return 'clearance/80' if self.clearance / 80 >= self.RENDER_TOLERANCE_FLOOR else 'minimum tolerance'

    def render_footprint(self, name=None, arc_tolerance=None, circle_segments=None, geometry_debug_file=None):
        """ Render the coil as a KiCad footprint. arc_tolerance and circle_segments only apply to circles; None means
        automatic. Values that would eat into the clearance are tightened, see `effective_render_options`. """
        if name is None:
            name = self.default_footprint_name

        from . import __version__
        footprint = Footprint(
                name=name,
                generator=kicad.Atom('kicoil'),
                generator_version=__version__,
                layer='F.Cu',
                descr=f"{self.turns} turn {self.shape.desc} twisted coil footprint, inductance approximately {self.L:.6f} µH. Generated by kicoil, version {__version__}.",
                clearance=self.clearance,
                zone_connect=0)

        self._prepare_shape()
        arc_tolerance, circle_segments, notes = self.effective_render_options(arc_tolerance, circle_segments)
        for note in notes:
            self.logger.warning(f'Overriding render setting: {note}.')

        def add_track(points, layer):
            if self.approximate_arcs and isinstance(self.shape, CircleShape) and len(points) >= 3:
                footprint.arcs.extend(arc_approximate(points, self.trace_width, layer, arc_tolerance))
            else:
                footprint.lines.extend(kicad.make_line(*p1, *p2, self.trace_width, layer)
                                       for p1, p2 in zip(points, points[1:]) if p1 != p2)

        def add_line(p1, p2, layer):
            # Skip zero-length connections, e.g. when the via offset is zero
            if dist(p1, p2) > 1e-9:
                footprint.lines.append(kicad.make_line(*p1, *p2, self.trace_width, layer))

        arms_layers = [[], []]
        for i in range(self.twists):
            start_angle, fold_angle, end_angle = self.arm_angles(i)

            # Handle the spiral arm
            points_layer0, arm_length, angle_refs_layer0 = self.shape.compute_spiral(a1=start_angle, a2=fold_angle, fn=circle_segments, debug=True)
            xn, yn = points_layer0[-1]
            add_track(points_layer0, self.layer_pair[0])

            if self.layers > 1:
                # Handle the returning arm on the bottom layer
                points_layer1, _, angle_refs_layer1 = self.shape.compute_spiral(a1=end_angle, a2=fold_angle, fn=circle_segments, debug=True)
                points_layer1 = points_layer1[::-1]
                add_track(points_layer1, self.layer_pair[1])

            else:
                # Add a straight connecting segment connecting the inner point to the outside of the spiral.
                xq, yq = self.shape.project_point(self.shape.outer_radius, fold_angle)
                points_layer1 = [(xn, yn), (xq, yq)]
                add_line((xn, yn), (xq, yq), self.layer_pair[1])
            
            arms_layers[0].append(points_layer0)
            arms_layers[1].append(points_layer1)

        inner_vias, outer_vias = self.via_positions()
        for i in range(self.twists):
            # Inner via ring
            points_layer0 = arms_layers[0][i]
            points_layer1 = arms_layers[1][i]
            xv, yv = inner_vias[i]
            add_line(points_layer0[-1], (xv, yv), self.layer_pair[0])
            add_line((xv, yv), points_layer1[0], self.layer_pair[1])
            footprint.pads.append(kicad.make_via(xv, yv,
                                                 self.via_diameter, self.via_drill, self.clearance,
                                                 self.layer_pair))

            # Outer via ring. At the start of the coil we place the pads instead.
            points_layer0 = arms_layers[0][i]
            points_layer1 = arms_layers[1][(i - self.turns) % self.twists]
            if i > 0:
                xv, yv = outer_vias[i-1]
                add_line(points_layer0[0], (xv, yv), self.layer_pair[0])
                add_line(points_layer1[-1], (xv, yv), self.layer_pair[1])
                footprint.pads.append(kicad.make_via(xv, yv,
                                                     self.via_diameter, self.via_drill, self.clearance,
                                                     self.layer_pair))
            
            else:
                # Place the pads at the ends of the spiral arms on the outer radius
                px, py = points_layer0[0]
                footprint.pads.append(kicad.make_pad(1, [self.layer_pair[0]], px, py, self.trace_width, self.clearance))
                qx, qy = points_layer1[-1]
                footprint.pads.append(kicad.make_pad(2, [self.layer_pair[1]], qx, qy, self.trace_width, self.clearance))

        if self.keepout_zone:
            pts = self.shape.offset_exterior(self.keepout_margin)
            footprint.zones.append(Zone(layers=['*.Cu'],
                hatch=Hatch(),
                filled_areas_thickness=False,
                keepout=ZoneKeepout(copperpour_allowed=False),
                polygon=ZonePolygon(pts=[XYCoord(x=x, y=y) for x, y in pts])))

        if geometry_debug_file:
            self.shape.sk.dump_to_pdf(geometry_debug_file)
        return footprint
