"""Straight skeleton spiral mapping with flat corners ("cornerflat").

The base `Skeletonator` makes the depth of a spiral arm linear in the angle coordinate. At a convex corner this means
that a turn leaving the corner already runs at a slope towards the next (deeper) turn, whose corner sits further along
the edge, so the two turns come closer than one pitch.

This variant separates the *position* parameter t (the angle, one unit per revolution) from a *warped* angle w(t) in
which the depth is linear. Per polygon edge, w is constant ("flat zone") near both ends of the edge and changes only in
a "ramp" in the middle of the edge, so all turns run along the offset outline around corners.

Ramps are defined in absolute coordinates along the edge: u is the distance along the edge direction from the edge's
start point on the outline. A turn at depth d starts its ramp at u = lo + beta*d and ends it at u = hi + beta*d' (d'
its depth at the ramp end). Points at the same u and different depths of one edge face differ by a translation along
the edge normal, so neighboring turns (which differ by one pitch p in depth at every w) are exact translates of each
other by (beta*p, p). The interval [lo, hi] is chosen so that every turn's ramp starts after its own corner and after
the corners of its neighbors (in the straight skeleton, corners move along the edge with depth), likewise for the end.
Then corners only ever meet flat stretches of their neighbors, and the spacing within a ramp of length R (in sheared
coordinates) with depth change D is p*R/sqrt((R + beta*D)^2 + D^2).

The shear beta helps arms whose depth increases along the edge if negative, and hurts arms running the other way by the
same amount. Single layer coils (all arms inward) use the best shear; two layer coils, whose inward and outward arms
have to meet at the vias, use a common, symmetric shear only on edges that need it (edges whose extent slides along the
edge with depth, like star tips).

The depth change of one revolution (pitch * twists) is distributed over the edges to maximize the smallest spacing
factor (a binary search over the factor). For few turns, only a few depths actually pass each ramp end (a lattice with
period p); `_lattice_search` optimizes the vertices' warped angles under these weaker constraints as an alternative
allocation ('lattice' mode). Edges without a usable ramp are crossed at constant depth.
"""

import math
import bisect
import os
import pickle

from . import skeletonator as base


_base_compute_skeleton = base.compute_skeleton


def compute_skeleton(exterior):
    """ Fork-safe wrapper around `skeletonator.compute_skeleton`.

    wasmtime's WASI implementation starts native helper threads the first time a module runs. A process that has done
    so cannot fork safely: the next WASI call in a forked child (e.g. a multiprocessing worker) deadlocks. As long as
    wasm has not run in this process yet, run the computation in a short-lived forked child instead, so that this
    process never starts those threads and stays safe to fork. `WasmApp.run` sets `.app`, so its presence tells us
    whether wasm has already run in this process (or in a parent it was forked from). """
    if not hasattr(os, 'fork') or hasattr(base.skeleton_wasm, 'app'):
        return _base_compute_skeleton(exterior=exterior)
    rfd, wfd = os.pipe()
    pid = os.fork()
    if pid == 0:
        status = 1
        try:
            os.close(rfd)
            data = pickle.dumps(_base_compute_skeleton(exterior=exterior))
            with os.fdopen(wfd, 'wb') as f:
                f.write(data)
            status = 0
        finally:
            os._exit(status)
    os.close(wfd)
    with os.fdopen(rfd, 'rb') as f:
        data = f.read()
    _, status = os.waitpid(pid, 0)
    if status != 0 or not data:
        raise RuntimeError('Error computing straight skeleton.')
    return pickle.loads(data)


class CornerFlatSkeletonator(base.Skeletonator):

    W_EPS = 1e-9

    def __init__(self, poly, ref_depth=None, ramp_margin=0.0):
        self.ramp_margin = ramp_margin
        # Build the skeleton and vertex tracks exactly like the base class, but with the fork-safe skeleton computation
        base.compute_skeleton = compute_skeleton
        try:
            super().__init__(poly, ref_depth)
        finally:
            base.compute_skeleton = _base_compute_skeleton

    # ---------------------------------------------------------------------------------------------------------------
    # Setup

    BETA_GRID = (-3, -2, -1.5, -1.25, -1, -0.8, -0.6, -0.45, -0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3, 0.45, 0.6, 0.8, 1, 1.25,
                 1.5, 2, 3, 4)

    def set_angle_reference(self, max_depth=None):
        """ Set the depth range [0, max_depth] used by the spiral and set up the ramps """
        if max_depth is None:
            max_depth = self.max_depth
        self.ref_depth = max(0, min(max_depth, self.max_depth))
        self._build()

    def configure(self, pitch, twists, direction=1, shear=True, residue_signs=None, sweep=None):
        """ Set the spiral's pitch (depth difference between neighboring turns) and number of interleaved arms. The
        depth change per revolution is pitch * twists. This lets the ramps be chosen for the best spacing.

        direction is +1 for arms whose depth increases with the angle, -1 for arms whose depth decreases. A shear of the
        ramps that helps one direction hurts the other one by the same amount. shear=True optimizes the shear for arms
        of the given direction only (all arms must run in that direction), shear='sym' for both directions (a shear then
        only costs, but it gives ramps to edges whose extent slides along the edge with depth), False disables it.

        At warped angle w, arms whose depth increases with w pass at depths congruent to pitch*twists*w modulo the
        pitch, arms whose depth decreases at depths congruent to -pitch*twists*w. residue_signs lists which of these
        occur (default: (direction,)).

        sweep is the angle (revolutions) one arm covers. Arms start at warped angles direction*j/twists and end
        (fold) one sweep later. """
        self.pitch, self.twists, self.direction, self.shear = pitch, twists, direction, shear
        if sweep is not None:
            self.arm_starts = sorted({(direction * j / twists) % 1.0 for j in range(twists)})
            self.arm_folds = sorted({(direction * (j / twists + sweep)) % 1.0 for j in range(twists)})
        else:
            self.arm_starts = self.arm_folds = None
        self.residue_signs = tuple(residue_signs) if residue_signs else (direction,)
        self._build()

    @staticmethod
    def _max_delta(R, beta, F):
        """ Largest depth change Δ on a ramp of length R (in sheared coordinates) with shear beta, such that the
        spacing between neighboring turns is at least F pitches: R / sqrt((R + beta Δ)^2 + Δ^2) >= F, R + beta Δ >= 0 """
        b2 = beta*beta
        h = (-beta + math.sqrt(b2 + (1 + b2) * (1/(F*F) - 1))) / (1 + b2)
        if beta < 0:
            h = min(h, -1/beta)
        return R * max(h, 0.0)

    # Per-edge geometry

    def _u_at(self, i, v, d):
        """ Position of vertex v's track at depth d along edge i's direction, from edge i's start on the outline """
        O, (dx, dy) = self.e_origin[i], self.e_dir[i]
        q = self.track_position(v, d)
        return (q[0] - O[0]) * dx + (q[1] - O[1]) * dy

    def _cont_depths(self, v):
        """ Depths at which vertex v's track (and with neighbor offsets +-p, the constraints) can have kinks """
        A, p = self.ref_depth, self._p
        ds = {0.0, A}
        ds.update(t for t in self._track_times[v] if 0 < t < A)
        if p > 0:
            ds.update(min(max(x, 0.0), A) for t in list(ds) for x in (t - p, t + p))
        return sorted(ds)

    def _lattice(self, w):
        """ Depths in [0, A] at which turns pass warped angle w """
        A, p, k = self.ref_depth, self._p, self._k
        out = set()
        for sign in self.residue_signs:
            r = (sign * p * k * w) % p
            if p - r < 1e-9 * max(1.0, p):
                r = 0.0
            m = 0
            while r + m*p <= A + 1e-9:
                out.add(min(r + m*p, A))
                m += 1
        return sorted(out)

    def _constraints(self, i, Di, Dj, lattice):
        """ (gi, gj): lists of (depth, u) for the ramp start (lower bound) and end (upper bound) constraints of edge i.
        Di/Dj are the depths of the turns at the ramp start/end. The ramp of a turn has to start after its own corner
        and after the projections of the corners of its neighbors at depth +- p, likewise for the end. """
        n = len(self.poly)
        j = (i + 1) % n
        A, p = self.ref_depth, self._p

        def env(v, d, fn):
            vals = [self._u_at(i, v, d)]
            if p > 0:
                for x in (d - p, d + p):
                    if lattice:
                        if -1e-9 <= x <= A + 1e-9:
                            vals.append(self._u_at(i, v, min(max(x, 0.0), A)))
                    else:
                        vals.append(self._u_at(i, v, min(max(x, 0.0), A)))
            return fn(vals)

        return [(d, env(i, d, max)) for d in Di], [(d, env(j, d, min)) for d in Dj]

    def _edge_cands(self, i, gi, gj, betas):
        eps_len = 1e-6 * self.circumference
        cands = []
        for beta in betas:
            lo = max(u - beta*d for d, u in gi) + self.ramp_margin
            hi = min(u - beta*d for d, u in gj) - self.ramp_margin
            if hi - lo > eps_len:
                cands.append((beta, lo, hi, hi - lo))
        return cands

    def _shear_sign(self, beta, sign):
        """ The shear as seen by the arms that suffer most from it """
        return abs(beta) if self.shear == 'sym' else sign * beta

    def _allocate(self, cands_l, need, sign):
        """ Distribute the depth change `need` of one revolution over the edges, maximizing the smallest spacing factor.
        Returns (F, choice, delta) or None. """
        n = len(cands_l)
        if not any(cands_l):
            return None

        def dmax_edge(i, F):
            return max((self._max_delta(c[3], self._shear_sign(c[0], sign), F) for c in cands_l[i]), default=0.0)

        def total(F):
            return sum(dmax_edge(i, F) for i in range(n))

        if total(1.0) >= need:
            F = 1.0
        else:
            lo_F, hi_F = 1e-4, 1.0
            for _ in range(50):
                mid = (lo_F + hi_F) / 2
                if total(mid) >= need:
                    lo_F = mid
                else:
                    hi_F = mid
            F = lo_F
        dm = [dmax_edge(i, F) for i in range(n)]
        tot = sum(dm)
        if tot <= 0:
            return None
        choice = [None] * n
        delta = [0.0] * n
        for i in range(n):
            d = dm[i] * need / tot
            best = None
            for c in cands_l[i]:
                if self._max_delta(c[3], self._shear_sign(c[0], sign), F) >= d * (1 - 1e-9):
                    key = (abs(c[0]), -c[3])
                    if best is None or key < best[0]:
                        best = (key, c)
            if best is not None and d > 0:
                choice[i], delta[i] = best[1], d
        if sum(delta) < need * (1 - 1e-6):
            return None
        return F, choice, delta

    def _alloc_W(self, delta, need):
        W = [0.0]
        for d in delta[:-1]:
            W.append(W[-1] + d / need)
        return W + [1.0]

    LATTICE_MAX_TURNS = 8

    def _lattice_edge(self, i, Wi, Wj, need):
        """ Spacing factor and ramp (beta=0) of edge i when its ramp runs from warped angle Wi to Wj, constrained only at
        the depths where turns actually pass the ramp's ends """
        D = need * (Wj - Wi)
        if D <= 1e-12:
            return 1.0, None
        n = len(self.poly)
        Di = self._lattice(Wi) or self._cont_depths(i)
        Dj = self._lattice(Wj) or self._cont_depths((i+1) % n)
        # Arms that start or end within the ramp sit at depth 0 or A there
        def within(ws):
            return any(Wi - 1e-9 <= w <= Wj + 1e-9 or Wi - 1e-9 <= w + 1 <= Wj + 1e-9 for w in ws)
        extra = []
        if self.arm_folds is None or within(self.arm_folds):
            extra.append(self.ref_depth)
        if self.arm_starts is None or within(self.arm_starts):
            extra.append(0.0)
        Di, Dj = sorted(set(Di) | set(extra)), sorted(set(Dj) | set(extra))
        gi, gj = self._constraints(i, Di, Dj, True)
        lo = max(u for _d, u in gi) + self.ramp_margin
        hi = min(u for _d, u in gj) - self.ramp_margin
        R = hi - lo
        if R <= 1e-6 * self.circumference:
            return 0.0, None
        return R / math.hypot(R, D), (0.0, lo, hi, R)

    def _lattice_search(self, alloc, need):
        """ With few turns, only a few depths pass each ramp end, and the ramps can be much longer than the edges' extent
        over the whole depth range. Optimize the warped angles of the vertices for the best smallest spacing factor
        (coordinate search starting from the allocation for the continuous constraints). """
        n = len(self.poly)
        W = self._alloc_W(alloc[2], need)
        res = [self._lattice_edge(i, W[i], W[i+1], need) for i in range(n)]
        if any(r[0] <= 0 for r in res):
            return None
        step = 0.25 / n
        evals = 0
        while step > 1e-5 and evals < 4000:
            improved = False
            for i in range(1, n):
                cur = min(res[i-1][0], res[i][0])
                for s in (step, -step):
                    w = W[i] + s
                    if not (W[i-1] <= w <= W[i+1]):
                        w = min(max(w, W[i-1]), W[i+1])
                        if w == W[i]:
                            continue
                    ra = self._lattice_edge(i-1, W[i-1], w, need)
                    rb = self._lattice_edge(i, w, W[i+1], need)
                    evals += 1
                    if min(ra[0], rb[0]) > cur + 1e-12:
                        W[i], res[i-1], res[i] = w, ra, rb
                        improved = True
                        break
            if not improved:
                step /= 2
        F = min(r[0] for r in res)
        choice = [r[1] for r in res]
        delta = [need * (W[i+1] - W[i]) if choice[i] is not None else 0.0 for i in range(n)]
        if abs(sum(delta) - need) > 1e-6 * need:
            return None
        return F, choice, delta

    def _build(self):
        n = len(self.poly)
        A = self.ref_depth
        p = getattr(self, 'pitch', None) or 0.0
        k = getattr(self, 'twists', None) or 1
        sign = getattr(self, 'direction', 1)
        configured = p > 0
        self._p, self._k = p, k

        self.e_origin, self.e_dir = [], []
        for i in range(n):
            O, Q = self.poly[i], self.poly[(i + 1) % n]
            L0 = math.dist(O, Q)
            self.e_origin.append(O)
            self.e_dir.append(((Q[0] - O[0]) / L0, (Q[1] - O[1]) / L0))

        cont_l, ext_l, betas_l = [], [], []
        for i in range(n):
            j = (i + 1) % n
            di, dj = self._cont_depths(i), self._cont_depths(j)
            gi, gj = self._constraints(i, di, dj, False)
            ext_l.append((min(self._u_at(i, i, d) for d in di), max(self._u_at(i, j, d) for d in dj)))
            betas = {0.0}
            if configured and getattr(self, 'shear', False):
                betas.update(self.BETA_GRID)
                # velocities of the edge's end points
                for g in (gi, gj):
                    for (d1, u1), (d2, u2) in zip(g, g[1:]):
                        if d2 - d1 > 1e-9:
                            v = (u2 - u1) / (d2 - d1)
                            if abs(v) < 6:
                                betas.add(round(v, 6))
            betas = sorted(betas)
            betas_l.append(betas)
            cont_l.append(self._edge_cands(i, gi, gj, betas))

        need = p * k
        self._ext_l = ext_l
        self.allocations = {}
        if configured:
            alloc = self._allocate(cont_l, need, sign)
            if alloc is not None:
                self.allocations['cont'] = alloc
                if getattr(self, 'shear', False) is not True and A / p <= self.LATTICE_MAX_TURNS:
                    better = self._lattice_search(alloc, need)
                    if better is not None and better[0] > alloc[0] + 0.01:
                        self.allocations['lattice'] = better
            self.set_mode('cont')
        else:
            # Not configured: no shear, depth change proportional to ramp length
            choice = [None] * n
            for i in range(n):
                for c in cont_l[i]:
                    if c[0] == 0.0:
                        choice[i] = c
            rs = [c[3] if c else 0.0 for c in choice]
            self.spacing_factor = None
            self._apply(choice, [r / sum(rs) for r in rs] if sum(rs) > 0 else None)

    def modes(self):
        """ Names of the alternative ramp allocations, best predicted first ('cont' is always valid) """
        return sorted(self.allocations, key=lambda m: m != 'cont') or ['cont']

    def set_mode(self, mode):
        n = len(self.poly)
        alloc = self.allocations.get(mode)
        self.mode = mode
        if alloc is None:
            self.spacing_factor = None
            self._apply([None]*n, None)
        else:
            self.spacing_factor = alloc[0]
            need = self._p * self._k
            self._apply(alloc[1], [d / need for d in alloc[2]])

    def _apply(self, choice, omega):
        n = len(self.poly)
        A = self.ref_depth
        ext_l = self._ext_l
        self.flat_ok = omega is not None and sum(omega) > 0.5
        self.beta = [c[0] if c else 0.0 for c in choice]
        self.ramp_lo = [c[1] if c else 0.0 for c in choice]
        self.ramp_hi = [c[2] if c else 0.0 for c in choice]
        self.ramp_len = [c[3] if c else 0.0 for c in choice]

        # Position parameter: every edge gets an angle span proportional to its extent over the depth range, so that all
        # vertices have distinct angles. Within the edge, the ramp gets a span proportional to its length.
        floor_g = 1e-4 * self.circumference / n
        parts = []
        for i in range(n):
            umin, umax = ext_l[i]
            if choice[i] is not None and self.flat_ok:
                R = self.ramp_len[i]
                zs = max(0.0, self.ramp_lo[i] + self.beta[i]*A/2 - umin)
                ze = max(0.0, umax - (self.ramp_hi[i] + self.beta[i]*A/2))
                parts.append((zs + floor_g/3, R + floor_g/3, ze + floor_g/3))
            else:
                parts.append((max(umax - umin, 0.0) + floor_g, 0.0, 0.0))
        total_g = sum(sum(q) for q in parts)
        self.vertex_angles = [0.0]
        for q in parts[:-1]:
            self.vertex_angles.append(self.vertex_angles[-1] + sum(q) / total_g)
        self.edge_spans = [b - a for a, b in zip(self.vertex_angles, self.vertex_angles[1:] + [1.0])]
        self.ta, self.tb = [], []
        for i in range(n):
            a = self.vertex_angles[i]
            zs, R, _ze = parts[i]
            self.ta.append(a + zs / total_g)
            self.tb.append(min(a + self.edge_spans[i], a + (zs + R) / total_g))

        if not self.flat_ok:
            # Fallback: depth linear in the position angle
            omega = list(self.edge_spans)
            self.ta = list(self.vertex_angles)
            self.tb = [a + e for a, e in zip(self.vertex_angles, self.edge_spans)]
            self.beta = [0.0] * n
            choice = [True] * n
        self.omega = [o if choice[i] is not None else 0.0 for i, o in enumerate(omega)]
        self.W = [0.0]
        for om in self.omega[:-1]:
            self.W.append(self.W[-1] + om)
        self._W_ext = self.W + [1.0]
        self._breaks = sorted(set(self.vertex_angles) | {t for t in self.ta + self.tb if 0 <= t < 1})
        self._flat_t_cache = {}

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
        t = self._unwarp(w)
        # A flat run can wrap around vertex 0, then the angle found can be off by one revolution
        return t + round(w - self.warp(t))

    def _unwarp(self, w):
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
        sh = self.beta[i] * d
        if f <= ta:
            g = 1.0 if ta <= a else (f - a) / (ta - a)
            u = ui + g * (clamp(lo + sh) - ui)
        elif f >= tb:
            b = a + e
            g = 0.0 if b <= tb else (f - tb) / (b - tb)
            u = clamp(hi + sh) + g * (uj - clamp(hi + sh))
        else:
            u = clamp(lo + (f - ta) / (tb - ta) * (hi - lo) + sh)
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


class LinearView:
    """ The plain layout of `skeletonator.Skeletonator` (depth linear in the angle, fixed vertex angles), using the
    skeleton of an existing CornerFlatSkeletonator. Offers the same interface as CornerFlatSkeletonator's spiral
    methods, with the warped angle equal to the angle. """

    SHARED = ('poly', 'poly_edges', 'circumference', 'skeleton_nodes', 'skeleton_edges', 'radius', 'divergent',
              'arc_map', 'min_radius', 'max_depth', 'node_map', 'tracks', '_track_times')

    def __init__(self, sk, max_depth):
        lin = object.__new__(base.Skeletonator)
        for name in self.SHARED:
            setattr(lin, name, getattr(sk, name))
        lin.debug_arms = []
        base.Skeletonator.set_angle_reference(lin, max_depth)
        self.lin = lin
        self.radius = sk.radius

    def warp(self, t):
        return t

    def unwarp(self, w):
        return w

    def spiral(self, t1, t2, d1, d2):
        return self.lin.spiral(t1, t2, d1, d2)

    def position(self, t, depth):
        return self.lin.project_point(t % 1, self.lin.radius - depth)
