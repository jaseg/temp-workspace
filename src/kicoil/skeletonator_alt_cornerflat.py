"""Straight skeleton spiral mapping with flat corners ("cornerflat").

The base `Skeletonator` makes the depth of a spiral arm linear in the angle coordinate. At a convex corner this means
that a turn leaving the corner already runs at a slope towards the next (deeper) turn, whose corner sits further along
the edge, so the two turns come closer than one pitch.

This variant separates the *position* parameter t (the angle, one unit per revolution) from a *warped* angle w(t) in
which the depth is linear. Per polygon edge, w is constant ("flat zone") near both ends of the edge and changes only in
a "ramp" in the middle of the edge. The ramp is defined in absolute coordinates along the edge (u, the distance along
the edge direction from the edge's start point on the outline), and it is the same interval [lo, hi] for every depth.
Since points at the same u and different depths on one edge face differ exactly by a translation along the edge
normal, neighboring turns (which differ by one pitch in depth at every w) are exact translates of each other inside
every ramp, and run along the offset outline in the flat zones around corners. The ramp interval is the intersection of
the edge's extents over the whole depth range used by the spiral, so every corner of every turn falls into a flat zone
of its neighbors.

Depth changes are distributed over the edges proportionally to their ramp lengths, which gives the same slope on every
ramp. Edges that collapse within the depth range (or whose extents over the depth range do not overlap) get no ramp and
are crossed at constant depth.
"""

import math
import bisect

from . import skeletonator as base


class CornerFlatSkeletonator(base.Skeletonator):

    W_EPS = 1e-9

    def __init__(self, poly, ref_depth=None, ramp_margin=0.0, pitch=None):
        self.ramp_margin = ramp_margin
        self.pitch = pitch
        super().__init__(poly, ref_depth)

    # ---------------------------------------------------------------------------------------------------------------
    # Setup

    def set_angle_reference(self, max_depth=None):
        if max_depth is None:
            max_depth = self.max_depth
        max_depth = max(0, min(max_depth, self.max_depth))
        self.ref_depth = max_depth
        n = len(self.poly)
        A = max_depth

        self.e_origin = []
        self.e_dir = []
        lo_l, hi_l, g_l, zs_l, r_l = [], [], [], [], []
        for i in range(n):
            j = (i + 1) % n
            O, Q = self.poly[i], self.poly[j]
            L0 = math.dist(O, Q)
            dx, dy = (Q[0] - O[0]) / L0, (Q[1] - O[1]) / L0
            self.e_origin.append(O)
            self.e_dir.append((dx, dy))

            def u_of(p):
                return (p[0] - O[0]) * dx + (p[1] - O[1]) * dy

            ui = [u_of(self.track_position(i, d)) for d in self._depth_samples(i, A)]
            uj = [u_of(self.track_position(j, d)) for d in self._depth_samples(j, A)]
            lo, hi = max(ui), min(uj)
            umin, umax = min(ui), max(uj)
            m = self.ramp_margin
            lo, hi = lo + m, hi - m
            G = max(umax - umin, 0.0)
            R = hi - lo
            if R <= 1e-6 * self.circumference:
                R = 0.0
                mid = (lo + hi) / 2
                lo = hi = min(max(mid, umin), umax)
            lo_l.append(lo)
            hi_l.append(hi)
            zs_l.append(max(lo - umin, 0.0))
            r_l.append(R)
            g_l.append(max(G, zs_l[-1] + R))

        total_R = sum(r_l)
        self.flat_ok = total_R > 1e-6 * self.circumference
        self.ramp_lo, self.ramp_hi, self.ramp_len = lo_l, hi_l, r_l

        # Position parameter: every edge gets an angle span proportional to its extent over the depth range, so that all
        # vertices have distinct angles.
        floor_g = 1e-4 * self.circumference / n
        g_l = [max(g, floor_g) for g in g_l]
        total_g = sum(g_l)
        self.vertex_angles = [0.0]
        for g in g_l[:-1]:
            self.vertex_angles.append(self.vertex_angles[-1] + g / total_g)
        self.edge_spans = [b - a for a, b in zip(self.vertex_angles, self.vertex_angles[1:] + [1.0])]
        self._va_ext = self.vertex_angles + [1.0]

        # Ramp start/end angles within each edge
        self.ta, self.tb = [], []
        for i in range(n):
            a, e = self.vertex_angles[i], self.edge_spans[i]
            G = g_l[i]
            ta = a + e * min(1.0, zs_l[i] / G)
            tb = min(a + e, ta + e * r_l[i] / G)
            self.ta.append(ta)
            self.tb.append(tb)

        # Warped angle at each vertex
        if self.flat_ok:
            self.omega = [r / total_R for r in r_l]
        else:
            self.omega = list(self.edge_spans)
            self.ta = list(self.vertex_angles)
            self.tb = [a + e for a, e in zip(self.vertex_angles, self.edge_spans)]
        self.W = [0.0]
        for om in self.omega[:-1]:
            self.W.append(self.W[-1] + om)
        self._W_ext = self.W + [1.0]
        self._breaks = sorted(set(self.vertex_angles) | {t for t in self.ta + self.tb if 0 <= t < 1})
        self._flat_t_cache = {}

    def _depth_samples(self, i, A):
        ds = {0.0, A}
        ds.update(t for t in self._track_times[i] if 0 < t < A)
        return sorted(ds)

    # ---------------------------------------------------------------------------------------------------------------
    # Coordinates

    def _locate_edge(self, t):
        """ (k, i, f): t is in revolution k, on edge i (a_i < f <= a_{i+1}) at absolute fractional angle f. """
        k = math.floor(t)
        f = t - k
        if f <= 0:
            k, f = k - 1, 1.0
        i = bisect.bisect_left(self.vertex_angles, f) - 1
        return k, max(0, i), f

    def warp(self, t):
        k, i, f = self._locate_edge(t)
        return k + self._warp_in_edge(i, f)

    def _warp_in_edge(self, i, f):
        Wi, om = self.W[i], self.omega[i]
        if om <= 0:
            return Wi
        ta, tb = self.ta[i], self.tb[i]
        if f <= ta:
            return Wi
        if f >= tb:
            return Wi + om
        return Wi + om * (f - ta) / (tb - ta)

    def unwarp(self, w):
        """ Position angle t for warped angle w. Where w is constant over an angle range (a flat zone around corners),
        the vertex in that range is returned, or the middle between the first and last vertex if there are several. """
        k = math.floor(w)
        g = w - k
        if 1.0 - g < self.W_EPS:
            k, g = k + 1, 0.0
        n = len(self.poly)
        # flat value?
        for i in range(n + 1):
            if abs(self._W_ext[i] - g) < self.W_EPS:
                return k + self._flat_t(self._W_ext[i] % 1.0 if i < n else 0.0)
        i = bisect.bisect_right(self.W, g) - 1
        i = max(0, min(n - 1, i))
        om = self.omega[i]
        if om <= 0:
            return k + self._flat_t(self.W[i])
        return k + self.ta[i] + (g - self.W[i]) / om * (self.tb[i] - self.ta[i])

    def _flat_t(self, Wv):
        if Wv in self._flat_t_cache:
            return self._flat_t_cache[Wv]
        n = len(self.poly)
        angles = []
        for i in range(n):
            if abs(self.W[i] - Wv) < self.W_EPS:
                angles.append(self.vertex_angles[i])
            elif abs(self.W[i] - (Wv + 1)) < self.W_EPS:
                angles.append(self.vertex_angles[i] - 1)
        if not angles:
            # Should not happen; fall back to linear interpolation
            t = Wv
        else:
            angles.sort()
            # the vertices of a flat run are contiguous (cyclically); find the largest gap to handle wrap-around
            if len(angles) > 1:
                ext = angles + [angles[0] + 1]
                _, q = max((ext[q+1] - ext[q], q) for q in range(len(angles)))
                # first vertex of the run is right after the largest gap, last right before it
                first = angles[(q + 1) % len(angles)]
                last = angles[q]
                if last < first:
                    last += 1
                t = (first + last) / 2
            else:
                t = angles[0]
        t = t % 1.0
        self._flat_t_cache[Wv] = t
        return t

    def _edge_point(self, i, f, d):
        n = len(self.poly)
        j = (i + 1) % n
        Vi, Vj = self.track_position(i, d), self.track_position(j, d)
        a, e = self.vertex_angles[i], self.edge_spans[i]
        if not self.flat_ok or self.omega[i] <= 0:
            g = 0.0 if e <= 0 else (f - a) / e
            return base.interpolate(Vi, Vj, max(0.0, min(1.0, g)))
        O, (dx, dy) = self.e_origin[i], self.e_dir[i]
        ui = (Vi[0] - O[0]) * dx + (Vi[1] - O[1]) * dy
        uj = (Vj[0] - O[0]) * dx + (Vj[1] - O[1]) * dy
        if uj - ui <= 1e-12:
            return Vi

        def clamp(u):
            return min(max(u, ui), uj)

        ta, tb = self.ta[i], self.tb[i]
        lo, hi = self.ramp_lo[i], self.ramp_hi[i]
        if f <= ta:
            g = 1.0 if ta <= a else (f - a) / (ta - a)
            u = ui + g * (clamp(lo) - ui)
        elif f >= tb:
            b = a + e
            g = 0.0 if b <= tb else (f - tb) / (b - tb)
            u = clamp(hi) + g * (uj - clamp(hi))
        else:
            u = clamp(lo + (f - ta) / (tb - ta) * (hi - lo))
        return base.interpolate(Vi, Vj, (u - ui) / (uj - ui))

    def position(self, t, depth):
        _k, i, f = self._locate_edge(t)
        return self._edge_point(i, f, depth)

    def project_point(self, t, r=None, r_ref=None):
        if r is None:
            r = self.radius
        return self.position(t, self.radius - r)

    def iter_breaks(self, t1, t2):
        """ Yield all break angles (vertices, ramp starts and ends) strictly between t1 and t2 """
        k = math.floor(t1)
        while True:
            for b in self._breaks:
                a = k + b
                if a >= t2:
                    return
                if a > t1:
                    yield a
            k += 1

    def spiral(self, t1, t2, d1, d2):
        """ Points and angles of a spiral arm from angle t1 at depth d1 to angle t2 at depth d2 (t1 < t2). The depth is
        linear in the warped angle. """
        w1, w2 = self.warp(t1), self.warp(t2)
        if abs(w2 - w1) < 1e-12:
            if math.isclose(t1, t2):
                depth_fn = lambda t: d1
            else:
                depth_fn = lambda t: d1 + (d2 - d1) * (t - t1) / (t2 - t1)
        else:
            depth_fn = lambda t: d1 + (d2 - d1) * (self.warp(t) - w1) / (w2 - w1)

        points = [self.position(t1, d1)]
        angles = [t1]
        for a in self.iter_breaks(t1, t2):
            p = self.position(a, depth_fn(a))
            if math.dist(p, points[-1]) > 1e-12:
                points.append(p)
                angles.append(a)
        p = self.position(t2, d2)
        if math.dist(p, points[-1]) > 1e-12 or len(points) == 1:
            points.append(p)
            angles.append(t2)
        else:
            points[-1], angles[-1] = p, t2
        return points, angles
