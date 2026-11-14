"""KiCoil layout with concentric rings and crossover jogs ("jog").

Same API as `kicoil.geometry`, but polygon shapes lay out their spiral arms as concentric rings: every turn runs at a
constant depth along the straight skeleton offset of the outline, and the radial step from one ring to the next happens
only in short crossover regions ("jogs") placed on straight edges of the outline. All traces cross over in unison at the
same jog sites, so between the jogs the spacing of neighboring turns is exactly the pitch, also around sharp corners.

Coordinates: like `kicoil.skeletonator`, arms are parametrized by an angle-like coordinate w (revolutions). The k arms
of a layer (k = twists) start at w = i/k. With K = k*m jog sites per revolution (m jogs per 1/k revolution, each
stepping by s = pitch/m), the depth profile of an arm, relative to its start, is

    D(u) = s * (n + ramp - (1/2 - c)),  q = u*K, n = floor(q - c + 1/2), ramp = clamp((q - c - n + h) / 2h, 0, 1)

a staircase that steps by s in a jog centered at q = n + c. Since D(u + 1/K) = D(u) + s, all arms (both layers, both
directions) interleave on a lattice of rings with spacing pitch, and since the jog centers are at the same w for all
arms, all traces jog at the same places. Arm ends sit in the middle of a plateau or in the middle of a jog (c = 1/2:
starts in a plateau at depth 0; c = 0: starts mid-jog).

The w coordinate is mapped to the outline piecewise linearly: the K jog sites are placed on straight edges (several jogs
may share a long edge) or on runs of consecutive edges with small turning angles (ellipses, arcs, subdivided edges);
the stretches in between get the remaining w range. Inside a jog site on a straight edge, the mapping is an affine map
from (w, depth) to the edge's coordinate system:

- shear alpha: deeper traces jog a little earlier (in the direction in which an arm gets deeper). With
  alpha = tan(theta/2), where theta is the jog angle, the traces in a jog are exact parallel offsets of each other
  (spacing exactly the pitch); with less shear the spacing is pitch * 2E / sqrt(L^2 + s^2) for a jog of length L and
  reach 2E = L + alpha*s. Arms of the two layers run in opposite directions and shear in opposite directions.
- drift beta: a common shift with depth for edges whose usable extent slides along the edge (star tips).
- the shear pivots around a depth where the layers meet (arm ends in the middle of a jog), so that both layers' arm
  ends coincide.

Jog sites are planned per edge (`plan_edge`): the jog must lie on the offset edge at the depths of the traces that pass
it, either at all depths in [0, annular width] or only at the lattice of depths that actually pass (plus the corners of
their neighbors). A binary search over the worst predicted spacing ratio with a DP over the edges allocates the jogs.

Since predictions are approximate, the final choice is by measurement: the best predicted candidates (several m, both
phases, rotations of the jog labels, both planners, with and without runs) and the plain linear spiral of
`kicoil.geometry` are measured with the same center line spacing measurement that sizes the traces, and the widest one
wins (the linear spiral is kept whenever it is at least as good). The final trace width is sized from the measured
center line spacing, exactly as in `kicoil.geometry`; the measurement also compares pieces of the same arm that are far
apart along the arm (narrow inner regions), and the via check skips arm pieces by path length like the test harness.
"""

import math
import heapq
import warnings
import dataclasses
from dataclasses import dataclass
from math import pi, dist, inf, floor, ceil, gcd

import numpy as np

from . import geometry
from .geometry import *  # noqa: F401,F403  re-export helpers
from .geometry import CircleShape, Shape, min_turn_spacing  # noqa: F401


def _snap(w, k):
    """ Snap w (revolutions) to the nearest multiple of 1/(2k) if it is within floating point error of it """
    g = 2*k
    r = round(w * g)
    if abs(w*g - r) < 1e-7:
        return r / g
    return w


def turn_spacing(arms, search_radius, path_sep, min_turn_separation=0.5):
    """ Like `geometry.min_turn_spacing`, but segments of the same arm are also compared when they are less than
    min_turn_separation revolutions apart, as long as they are more than path_sep apart along the arm. Arms that pass
    through a narrow part of the annulus (e.g. near the inner end of a deep annulus) can come close to themselves within
    less than half a revolution. Vectorized with shapely. Returns (distance, location) like min_turn_spacing. """
    import shapely
    max_span = min_turn_separation / 10
    P1, P2, ARM, TLO, THI, SLO, SHI = [], [], [], [], [], [], []
    for arm_idx, (points, angles) in enumerate(arms):
        pts = np.asarray(points, dtype=float)
        ang = np.asarray(angles, dtype=float)
        if len(pts) < 2:
            continue
        d = pts[1:] - pts[:-1]
        l = np.hypot(d[:, 0], d[:, 1])
        s0 = np.concatenate([[0.0], np.cumsum(l)])[:-1]
        keep = l > 0
        nseg = np.maximum(1, np.maximum(np.ceil(np.abs(ang[1:] - ang[:-1]) / max_span),
                                        np.ceil(l / (search_radius / 2)))).astype(int)
        for i in np.nonzero(keep)[0]:
            n = nseg[i]
            f = np.arange(n + 1) / n
            q = pts[i] + f[:, None] * d[i]
            t = ang[i] + f * (ang[i+1] - ang[i])
            sp = s0[i] + f * l[i]
            P1.append(q[:-1]); P2.append(q[1:])
            ARM.append(np.full(n, arm_idx))
            TLO.append(np.minimum(t[:-1], t[1:])); THI.append(np.maximum(t[:-1], t[1:]))
            SLO.append(sp[:-1]); SHI.append(sp[1:])
    if not P1:
        return search_radius, None
    P1, P2 = np.concatenate(P1), np.concatenate(P2)
    ARM, TLO, THI, SLO, SHI = map(np.concatenate, (ARM, TLO, THI, SLO, SHI))
    geoms = shapely.linestrings(np.stack([P1, P2], axis=1))
    tree = shapely.STRtree(geoms)
    ia, ib = tree.query(geoms, predicate='dwithin', distance=search_radius)
    m = ia < ib
    ia, ib = ia[m], ib[m]
    same = ARM[ia] == ARM[ib]
    tsep = np.maximum(TLO[ib] - THI[ia], TLO[ia] - THI[ib])
    ssep = np.maximum(SLO[ib] - SHI[ia], SLO[ia] - SHI[ib])
    m = ~(same & (tsep < min_turn_separation) & (ssep <= path_sep))
    ia, ib = ia[m], ib[m]
    if len(ia) == 0:
        return search_radius, None
    dd = shapely.distance(geoms[ia], geoms[ib])
    j = int(np.argmin(dd))
    if dd[j] >= search_radius:
        return search_radius, None
    i = ia[j]
    return float(dd[j]), (float((P1[i][0] + P2[i][0]) / 2), float((P1[i][1] + P2[i][1]) / 2))


def _path_coords(points):
    s = [0.0]
    for p, q in zip(points, points[1:]):
        s.append(s[-1] + dist(p, q))
    return s


class JogSite:
    """ A jog from along-edge coordinate x on edge `edge0` to edge `edge1` (the same edge for a jog on a single straight
    edge, a run of consecutive edges otherwise). Along-edge coordinates are measured from the edge's start vertex. At
    depth d the jog starts at x0 and ends at x1, both shifted by (beta - sigma*alpha)*(d - dpiv): alpha is the shear
    that keeps the traces of a jog parallel (opposite for the two arm directions), beta a common drift that follows edges
    whose extent slides along the edge with depth. """

    def __init__(self, edge0, x0, edge1, x1, alpha, dpiv, L, rho, interior=(), beta=0.0):
        self.edge0, self.x0, self.edge1, self.x1 = edge0, x0, edge1, x1
        self.alpha, self.dpiv, self.L, self.rho, self.beta = alpha, dpiv, L, rho, beta
        self.interior = list(interior) # vertices inside the jog (runs only)

    @property
    def edge(self):
        return self.edge0

    def x(self, b, d, sigma):
        return (self.x1 if b else self.x0) + (self.beta - sigma * self.alpha) * (d - self.dpiv)

    def __repr__(self):
        e = f'{self.edge0}' if self.edge0 == self.edge1 else f'{self.edge0}..{self.edge1}'
        return (f'JogSite(e={e}, x0={self.x0:.3f}, x1={self.x1:.3f}, L={self.L:.3f}, alpha={self.alpha:.3f}, '
                f'beta={self.beta:.3f}, dpiv={self.dpiv:.3f}, rho={self.rho:.3f})')


class JogLayout:
    """ Concentric ring layout with k jog sites per revolution. See module docstring. """

    H = 0.1 # half width of a jog in units of a period (1/k revolution)

    def __init__(self, sk, edges, A, pitch, k, sites, c=0.5, end_sigma=0, rot=0):
        self.sk, self.edges, self.A, self.pitch, self.k = sk, edges, A, pitch, k
        self.sites = sites
        self.c = c # phase of the jog centers within a period: 0.5 (arm starts in a plateau) or 0 (arm starts mid-jog)
        self.end_sigma = end_sigma # shear direction used for arm end points and vias (0: unsheared)
        n = len(sk.poly)
        h = self.H

        # Physical cyclic order of vertices and jog sites
        by_edge = {}
        inside = set()
        for st in sites:
            by_edge.setdefault(st.edge0, []).append(st)
            inside.update(st.interior)
        items = []
        for e in range(n):
            if e not in inside:
                items.append(('v', e))
            for st in sorted(by_edge.get(e, []), key=lambda st: st.x0):
                items.append(('j', st))
        # Start right after the last jog, so that stretch 0 contains vertex 0 (rot shifts this by whole jogs)
        jogs_at = [i for i, it in enumerate(items) if it[0] == 'j']
        last = jogs_at[(rot - 1) % len(jogs_at)]
        items = items[last+1:] + items[:last+1]
        self.rot = rot
        order = [it[1] for it in items if it[0] == 'j']
        assert len(order) == k

        # Split into stretches: stretch j lies between jog j-1 and jog j. Stretch 0 wraps around and contains vertex 0.
        stretches = [[] for _ in range(k)]
        j = 0
        for kind, val in items:
            if kind == 'j':
                j += 1
            else:
                stretches[j % k].append(val)

        ref_depths = [0.0, A/2, A]
        es = end_sigma

        def distribute(seq, w_lo, w_hi, w_mid=None):
            """ w for the items of seq (first and last at w_lo and w_hi) proportional to the mean arc length. When w_mid
            is given, the arc midpoint (clamped to the inner items) is mapped to w_mid. """
            lengths = []
            for a, b in zip(seq, seq[1:]):
                l = 0
                for d in ref_depths:
                    l += dist(self._pos(a, d, es), self._pos(b, d, es))
                lengths.append(l / len(ref_depths) + 1e-9 * (sk.circumference + 1))
            cum = [0.0]
            for l in lengths:
                cum.append(cum[-1] + l)
            S = cum[-1]
            if w_mid is None:
                return [w_lo + (w_hi - w_lo) * sc / S for sc in cum]
            s_mid = S / 2
            if len(seq) > 2:
                s_mid = min(max(s_mid, cum[1]), cum[-2])
            ws = []
            for sc in cum:
                if sc <= s_mid:
                    ws.append(w_lo + (w_mid - w_lo) * (sc / s_mid if s_mid > 0 else 1.0))
                else:
                    ws.append(w_mid + (w_hi - w_mid) * ((sc - s_mid) / (S - s_mid)))
            if len(seq) > 2 and s_mid == cum[1]:
                ws[1] = w_mid
            if len(seq) > 2 and s_mid == cum[-2]:
                ws[-2] = w_mid
            return ws

        knots = [] # (w, kind, payload)
        for j in range(k):
            w_lo = (j - 1 + c + h) / k
            w_hi = (j + c - h) / k
            s_prev = order[(j - 1) % k]
            s_next = order[j]
            seq = [('j', (s_prev, 1))] + [('v', v) for v in stretches[j]] + [('j', (s_next, 0))]
            ws = distribute(seq, w_lo, w_hi, (j - 0.5 + c) / k)
            for (kind, val), w in zip(seq[1:-1], ws[1:-1]):
                knots.append((w, kind, val))
            # jog j: start knot at w_hi, end knot at w_hi + 2h/k, interior vertices of runs in between
            w_end = (j + c + h) / k
            knots.append((w_hi, 'j', (s_next, 0)))
            if s_next.interior:
                seq = [('j', (s_next, 0))] + [('v', v) for v in s_next.interior] + [('j', (s_next, 1))]
                ws = distribute(seq, w_hi, w_end)
                for (kind, val), w in zip(seq[1:-1], ws[1:-1]):
                    knots.append((w, kind, val))
            knots.append((w_end, 'j', (s_next, 1)))
        knots.sort(key=lambda t: t[0])
        self.knots = knots
        self.knot_w = [t[0] for t in knots]
        self.w0 = (c - 1 + h) / k # start of the revolution covered by the knot list

    # --- mapping ---

    def _pos(self, knot, d, sigma):
        kind, val = knot
        if kind == 'v':
            return self.sk.track_position(val, d)
        site, b = val
        P, u, nrm = self.edges[site.edge1 if b else site.edge0]
        x = site.x(b, d, sigma)
        return (P[0] + x*u[0] + d*nrm[0], P[1] + x*u[1] + d*nrm[1])

    def iter_knots(self, lo, hi, eps=1e-12):
        """ Yield (w, knot) for all knots with lo < w < hi, in order """
        m = floor(lo - self.w0) - 1
        nk = len(self.knots)
        while True:
            base = m
            for w, kind, val in self.knots:
                ww = w + base
                if ww >= hi - eps:
                    return
                if ww > lo + eps:
                    yield ww, (kind, val)
            m += 1

    def point(self, w, d, sigma=None):
        """ Point at w on the ring at depth d (interpolated between knots) """
        if sigma is None:
            sigma = self.end_sigma
        m = floor(w - self.w0)
        f = w - m
        ws = self.knot_w
        idx = np.searchsorted(ws, f, side='right') - 1 # last knot with w <= f
        nk = len(ws)
        if idx < 0:
            idx = nk - 1
            wa = ws[idx] - 1
        else:
            wa = ws[idx]
        if idx + 1 < nk:
            wb = ws[idx + 1]
            kb = self.knots[idx + 1]
        else:
            wb = ws[0] + 1
            kb = self.knots[0]
        ka = self.knots[idx]
        pa = self._pos(ka[1:], d, sigma)
        if abs(f - wa) < 1e-12:
            return pa
        pb = self._pos(kb[1:], d, sigma)
        t = (f - wa) / (wb - wa) if wb > wa else 0.0
        return (pa[0] + t*(pb[0]-pa[0]), pa[1] + t*(pb[1]-pa[1]))

    def D(self, u):
        q = u * self.k
        c = self.c
        n = floor(q - c + 0.5)
        r = q - c - n
        h = self.H
        ramp = min(1.0, max(0.0, (r + h) / (2*h)))
        return self.pitch * (n + ramp - (0.5 - c))

    def arm(self, ws, we):
        """ Arm from w=ws at depth 0 to w=we at depth A. Returns points and angles from ws to we. """
        k = self.k
        ws, we = _snap(ws, k), _snap(we, k)
        sigma = 1 if we > ws else -1
        lo, hi = min(ws, we), max(ws, we)
        pts, angs = [], []
        p_lo = self.point(lo, 0.0 if lo == ws else self.A)
        pts.append(p_lo)
        angs.append(lo)
        for w, knot in self.iter_knots(lo, hi):
            if abs(w - lo) < 1e-12 or abs(w - hi) < 1e-12:
                continue
            d = sigma * self.D(w - ws)
            p = self._pos(knot, d, sigma)
            if dist(p, pts[-1]) > 1e-9:
                pts.append(p)
                angs.append(w)
        p_hi = self.point(hi, self.A if hi == we else 0.0)
        if dist(p_hi, pts[-1]) > 1e-9 or len(pts) == 1:
            pts.append(p_hi)
            angs.append(hi)
        else:
            pts[-1], angs[-1] = p_hi, hi
        if sigma < 0:
            pts, angs = pts[::-1], angs[::-1]
        return pts, angs


def _edge_frames(sk):
    """ For every outline edge: (origin, unit direction, inward normal) """
    poly = sk.poly
    n = len(poly)
    area = sum(x1*y2 - x2*y1 for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]))
    sgn = 1 if area > 0 else -1
    frames = []
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i+1) % n]
        l = math.hypot(x2-x1, y2-y1)
        if l == 0:
            frames.append(((x1, y1), (1.0, 0.0), (0.0, 1.0)))
            continue
        u = ((x2-x1)/l, (y2-y1)/l)
        nrm = (-u[1]*sgn, u[0]*sgn)
        frames.append(((x1, y1), u, nrm))
    return frames


class OffsetShape(geometry.OffsetShape):
    """ Polygon shape with the concentric ring + jog layout. Without a configured layout (`self.layout is None`), it
    behaves exactly like `kicoil.geometry.OffsetShape` (linear spiral). """

    layout = None

    def __post_init__(self):
        super().__post_init__()
        self.layout = None
        self.edges = _edge_frames(self.sk)
        self._edge_limits = {}

    # --- jog site planning ---

    def edge_limits(self, e, A):
        """ Depth samples and along-edge coordinates a(d), b(d) of the offset edge e for depths in [0, A] """
        key = (e, A)
        if key in self._edge_limits:
            return self._edge_limits[key]
        sk = self.sk
        n = len(sk.poly)
        P, u, nrm = self.edges[e]
        ds = {0.0, A}
        for i in (e, (e+1) % n):
            ds.update(t for t in sk._track_times[i] if 0 < t < A)
        ds = np.array(sorted(ds))
        a, b, off = [], [], []
        for d in ds:
            p1 = sk.track_position(e, d)
            p2 = sk.track_position((e+1) % n, d)
            a.append((p1[0]-P[0])*u[0] + (p1[1]-P[1])*u[1])
            b.append((p2[0]-P[0])*u[0] + (p2[1]-P[1])*u[1])
            # sanity: the offset edge must lie on the line at distance d
            off.append(abs((p1[0]-P[0])*nrm[0] + (p1[1]-P[1])*nrm[1] - d) + abs((p2[0]-P[0])*nrm[0] + (p2[1]-P[1])*nrm[1] - d))
        res = (ds, np.array(a), np.array(b), max(off))
        self._edge_limits[key] = res
        return res

    ALPHAS = np.linspace(0, 1.5, 31)

    @staticmethod
    def jog_samples(A, step, sigmas, offset, ds=None):
        """ Points that traces pass in a jog: (sigma, depth, kappa) where kappa = 2f - 1 is the position along the jog
        (-1 at its start, +1 at its end).

        Lattice mode (ds None): traces enter a jog from a plateau whose depth is offset + t*step and leave it one step
        deeper (sigma = +1) or shallower (sigma = -1). Only depths in [0, A] count: arms start at depth 0 and end at
        depth A, possibly in the middle of a jog. Continuous mode: both jog ends at all depths ds. """
        out = []
        if ds is not None:
            for sg in sigmas:
                for d in ds:
                    out.append((sg, d, -1.0))
                    out.append((sg, d, 1.0))
            return out
        t0 = floor((-step - offset) / step)
        t1 = ceil((A + step - offset) / step)
        for sg in sigmas:
            for t in range(t0, t1 + 1):
                dL = offset + t * step
                if sg > 0:
                    f_lo, f_hi = max(0.0, -dL / step), min(1.0, (A - dL) / step)
                else:
                    f_lo, f_hi = max(0.0, (dL - A) / step), min(1.0, dL / step)
                if f_hi - f_lo < 1e-9:
                    continue
                for f in (f_lo, (f_lo + f_hi) / 2, f_hi):
                    out.append((sg, dL + sg * f * step, 2*f - 1))
        return out

    MAX_LATTICE_SAMPLES = 150

    def plan_edge(self, e, A, step, sigmas, pivots, qmax, margin, gap, offset=0.0, pitch=None, lattice=True):
        """ Best jog parameters for q = 1..qmax jogs on edge e. Returns {q: (rho, L, alpha, dpiv, x_lo, E, gap)}.

        The jogs of an edge form a block [X - Etot, X + Etot] (at the pivot depth). Every point that a trace passes in
        a jog (see jog_samples) must lie on the offset edge at its depth, shifted by the shear. In lattice mode, the
        corners of the neighboring turns (one pitch shallower and deeper) must stay out of the jog, too. Solved on a
        grid of shears, with a search for the widest block per shear. """
        if pitch is None:
            pitch = step
        if not lattice:
            offset = pitch = 0.0 # not used
        key = ('edge', e, A, step, tuple(sorted(sigmas)), tuple(pivots), qmax, margin, gap, offset, pitch, lattice)
        if key in self._edge_limits:
            return self._edge_limits[key]
        ds, a, b, err = self.edge_limits(e, A)
        res = {}
        self._edge_limits[key] = res
        if err > 1e-6 * max(1.0, self.sk.radius) or np.min(b - a) <= 2 * margin or np.max(b - a) < 0.1 * step:
            return res
        samples = None
        if lattice:
            samples = self.jog_samples(A, step, sigmas, offset)
            if len(samples) > self.MAX_LATTICE_SAMPLES:
                return res # many turns: practically the same as the continuous constraint
        else:
            samples = self.jog_samples(A, step, sigmas, offset, ds=ds)
        if not samples:
            return res
        sg = np.array([t[0] for t in samples], dtype=float)
        dep = np.array([t[1] for t in samples])
        kap = np.array([t[2] for t in samples])
        if lattice:
            near = [np.clip(dep + dd, 0, A) for dd in (-pitch, 0.0, pitch)]
            a_s = np.max([np.interp(x, ds, a) for x in near], axis=0) + margin
            b_s = np.min([np.interp(x, ds, b) for x in near], axis=0) - margin
        else:
            a_s = np.interp(dep, ds, a) + margin
            b_s = np.interp(dep, ds, b) - margin
        al = self.ALPHAS[:, None]
        span = float(np.max(b) - np.min(a))
        nal = len(self.ALPHAS)
        rows = np.arange(nal)
        Q = np.arange(1, qmax + 1)[:, None]
        # Common drift: only for edges whose usable extent slides along the edge with depth (star tips)
        betas = [0.0]
        if ds[-1] > ds[0]:
            drift = ((a[-1] + b[-1]) - (a[0] + b[0])) / 2 / (ds[-1] - ds[0])
            if abs(drift) > 0.05 and len(sigmas) > 1:
                betas += [float(drift), float(drift) / 2]
        for dpiv, beta in [(dp, bt) for dp in pivots for bt in betas]:
            shift = (al * sg[None, :] - beta) * (dep - dpiv)[None, :] # (nalpha, ns), moves the bounds into X coordinates
            lo = a_s[None, :] + shift
            hi = b_s[None, :] + shift

            def F(E):
                Xlo = (lo - kap[None, :] * E[:, None]).max(axis=1)
                Xhi = (hi - kap[None, :] * E[:, None]).min(axis=1)
                return Xhi - Xlo, Xlo, Xhi

            # The feasible block widths form an interval (F is concave in E): coarse grid, then bisection at its upper
            # end
            grid = np.linspace(0, span / 2, 33)
            KE = kap[None, :, None] * grid[None, None, :] # (1, ns, ngrid)
            feas = ((hi[:, :, None] - KE).min(axis=1) - (lo[:, :, None] - KE).max(axis=1)) >= 0 # (nalpha, ngrid)
            any_f = feas.any(axis=1)
            if not any_f.any():
                continue
            last = len(grid) - 1 - np.argmax(feas[:, ::-1], axis=1)
            E_ok = grid[last]
            E_bad = np.where(last + 1 < len(grid), grid[np.minimum(last + 1, len(grid) - 1)], grid[-1])
            for _ in range(8):
                mid = (E_ok + E_bad) / 2
                f_mid = F(mid)[0] >= 0
                E_ok = np.where(f_mid, mid, E_ok)
                E_bad = np.where(f_mid, E_bad, mid)
            Etot = np.where(any_f, E_ok, 0.0)
            _f, Xlo, Xhi = F(Etot)
            X = (Xlo + Xhi) / 2
            # Shift of the jog knots at the arm end depths (0 and A), relative to the unsheared position. Arm ends
            # between two jogs on the same edge must stay clear of both.
            endshift = (self.ALPHAS + abs(beta)) * max(abs(dpiv), abs(A - dpiv))
            g = gap + 2*endshift
            E = (Etot[None, :] - (Q - 1) * g[None, :] / 2) / Q # (nq, nalpha)
            # Jog length (along the edge) for each arm direction, and the spacing ratio 2E / |(L, step)|
            Ls = [2*E - (self.ALPHAS[None, :] - sgn * beta) * step for sgn in sigmas]
            L = np.minimum.reduce(Ls)
            Lmax = np.maximum.reduce(Ls)
            ok = any_f[None, :] & (E > 0) & (L >= 0)
            rho = np.where(ok, np.minimum(1.0, 2*E / np.sqrt(np.maximum(Lmax, 0)**2 + step**2)), -1.0)
            best = rho.max(axis=1, keepdims=True)
            Lm = np.where(rho >= best - 1e-9, L, -inf)
            idx = np.argmax(Lm, axis=1) # best rho, among (nearly) equal ones the gentlest jog (largest L)
            for qi in range(qmax):
                i = idx[qi]
                if not ok[qi, i]:
                    break
                q = qi + 1
                entry = (float(rho[qi, i]), float(L[qi, i]), float(self.ALPHAS[i]), float(dpiv), float(X[i] - Etot[i]),
                         float(E[qi, i]), float(g[i]), beta)
                if q not in res or entry[0] > res[q][0] + 1e-9 or (abs(entry[0] - res[q][0]) <= 1e-9 and entry[1] > res[q][1]):
                    res[q] = entry
        return res

    MAX_RUN_TURN = 0.6 # rad, total turning of the convex vertices inside a multi-edge jog
    MAX_RUN_EDGES = 32

    def _run_geometry(self, margin):
        """ Geometry of all candidate runs: list of (edges, x0, x1, L(d) samples, max |tan(turn/2)| of inner vertices) """
        key = ('runs', margin)
        if key in self._edge_limits:
            return self._edge_limits[key]
        A = self.annular_width
        sk = self.sk
        n = len(self.polygon)
        out = []
        self._edge_limits[key] = out
        if n < 3:
            return out
        ds = np.linspace(0, A, 17)
        V = np.array([[sk.track_position(i, d) for d in ds] for i in range(n)]) # (n, m, 2)
        elen = np.linalg.norm(V[(np.arange(n) + 1) % n] - V, axis=2) # (n, m) offset edge lengths
        turn = []
        for v in range(n):
            _P0, u0, _n0 = self.edges[(v - 1) % n]
            _P1, u1, _n1 = self.edges[v]
            cr = u0[0]*u1[1] - u0[1]*u1[0]
            dt = u0[0]*u1[0] + u0[1]*u1[1]
            turn.append(math.atan2(cr, dt))
        lim = {}
        for e in range(n):
            eds, a, b, err = self.edge_limits(e, A)
            if err > 1e-6 * max(1.0, sk.radius):
                continue
            lim[e] = (np.interp(ds, eds, a), np.interp(ds, eds, b), a.max() + margin, b.min() - margin)
        for e0 in range(n):
            if e0 not in lim:
                continue
            a0, b0, x0, _ = lim[e0]
            if np.any(b0 - x0 < 0):
                continue
            head = b0 - x0 # usable length on the first edge at each depth
            mid = np.zeros_like(ds)
            total_turn, max_tan = 0.0, 0.0
            for m in range(1, min(self.MAX_RUN_EDGES, n - 1)):
                v = (e0 + m) % n # vertex entering edge e1
                e1 = v
                total_turn += abs(turn[v])
                max_tan = max(max_tan, abs(math.tan(turn[v] / 2)))
                if total_turn > self.MAX_RUN_TURN:
                    break
                if e1 in lim:
                    a1, b1, _, x1 = lim[e1]
                    tail = x1 - a1
                    if np.all(tail >= 0):
                        L = head + mid + tail
                        if np.all(L > 0):
                            out.append(([(e0 + i) % n for i in range(m + 1)], float(x0), float(x1), L, max_tan))
                mid = mid + elen[e1]
        return out

    def plan_runs(self, step, margin):
        """ Candidate multi-edge jogs: runs of consecutive edges with small turning angles at the inner vertices
        (ellipses, arcs, subdivided edges). The jog spans the run from the start of the usable part of the first edge to
        the end of the usable part of the last edge, unsheared. The spacing estimate includes the loss at the inner
        vertices (a jog's slope s across a corner that turns by phi costs about s*tan(phi/2) of the pitch, on one of the
        layers). Returns a list of (rho, edges, JogSite). """
        out = []
        for edges, x0, x1, L, max_tan in self._run_geometry(margin):
            sl = step / L
            rho = float(np.min(1 / np.sqrt(1 + sl**2) * (1 - sl * max_tan)))
            site = JogSite(edges[0], x0, edges[-1], x1, 0.0, 0.0, float(L.min()), rho, edges[1:])
            out.append((rho, edges, site))
        return out

    @staticmethod
    def _select_mixed(k, n, plans, run_cands):
        """ Choose k jogs among single edges (plans: edge -> {q: (rho, ...)}) and runs (list of (rho, edges, site)) that
        maximize the worst ratio. Binary search on the threshold; for a threshold, a DP over the edges finds the maximum
        number of jogs on disjoint edges (runs occupy all their edges). """
        def feasible(t, build=False):
            cap = {e: max((q for q, v in p.items() if v[0] >= t), default=0) for e, p in plans.items()}
            # shortest qualifying run per start edge
            short = {}
            for rho, edges, site in run_cands:
                if rho >= t and (edges[0] not in short or len(edges) < len(short[edges[0]][0])):
                    short[edges[0]] = (edges, site)
            best = None
            for rot in sorted({0, n // 3, (2 * n) // 3}):
                # DP over edges rot, rot+1, ... (linear order), f[i] = max jogs using the first i edges
                pos = {(rot + i) % n: i for i in range(n)}
                ends = {}
                for e0, (edges, site) in short.items():
                    i0, i1 = pos[edges[0]], pos[edges[-1]]
                    if i1 >= i0:
                        ends.setdefault(i1, []).append((i0, edges, site))
                f = [0] * (n + 1)
                back = [None] * (n + 1)
                for i in range(n):
                    e = (rot + i) % n
                    f[i+1], back[i+1] = f[i], ('skip',)
                    if cap.get(e, 0) and f[i] + cap[e] > f[i+1]:
                        f[i+1], back[i+1] = f[i] + cap[e], ('edge', e, cap[e])
                    for i0, edges, site in ends.get(i, ()):
                        if f[i0] + 1 > f[i+1]:
                            f[i+1], back[i+1] = f[i0] + 1, ('run', i0, edges, site)
                if best is None or f[n] > best[0]:
                    best = (f[n], back)
            if not build:
                return best[0] >= k
            total, back = best
            count, runs_sel = {}, []
            i = n
            while i > 0:
                b = back[i]
                if b[0] == 'skip':
                    i -= 1
                elif b[0] == 'edge':
                    count[b[1]] = b[2]
                    i -= 1
                else:
                    runs_sel.append(b[3])
                    i = b[1]
            # Drop surplus jogs: first from the most loaded edges, then runs
            surplus = total - k
            while surplus > 0 and any(q > 1 for q in count.values()):
                e = max(count, key=count.get)
                count[e] -= 1
                surplus -= 1
            while surplus > 0 and runs_sel:
                runs_sel.pop()
                surplus -= 1
            while surplus > 0 and count:
                e = next(e for e, q in count.items() if q > 0)
                count[e] -= 1
                surplus -= 1
            return {e: q for e, q in count.items() if q > 0}, runs_sel

        values = sorted({v[0] for p in plans.values() for v in p.values()} | {r[0] for r in run_cands}, reverse=True)
        lo, hi = 0, len(values) - 1 # values[lo] is the most ambitious threshold
        if not values or not feasible(values[hi]):
            return None
        while lo < hi:
            mid = (lo + hi) // 2
            if feasible(values[mid]):
                hi = mid
            else:
                lo = mid + 1
        return feasible(values[lo], build=True)

    def plan_jogs(self, k, step, sigmas, pivots, margin=None, gap=None, runs=False, offset=0.0, pitch=None,
                  lattice=True):
        """ Allocate k jog sites to edges (and, with runs=True, runs of edges), greedily maximizing the worst jog spacing
        ratio. Returns a list of JogSite or None """
        A = self.annular_width
        n = len(self.polygon)
        if margin is None:
            margin = 0.02 * step
        if gap is None:
            gap = 0.25 * step
        plans = {}
        for e in range(n):
            p = self.plan_edge(e, A, step, sigmas, pivots, k, margin, gap, offset, pitch, lattice)
            if p:
                plans[e] = p
        run_cands = self.plan_runs(step, margin) if runs else []
        if not plans and not run_cands:
            return None
        if runs and run_cands:
            sel = self._select_mixed(k, n, plans, run_cands)
            if sel is None:
                return None
            count, chosen_runs = sel
        else:
            # Greedy: hand out jogs one by one to the edge that keeps the best ratio with one more jog. Ratios decrease
            # with the number of jogs per edge, so this maximizes the minimum ratio.
            count = {e: 0 for e in plans}
            chosen_runs = []
            heap = [(-p[1][0], -p[1][1], e) for e, p in plans.items() if 1 in p]
            heapq.heapify(heap)
            for _ in range(k):
                if not heap:
                    return None
                _r, _l, e = heapq.heappop(heap)
                count[e] += 1
                q = count[e] + 1
                if q in plans[e]:
                    heapq.heappush(heap, (-plans[e][q][0], -plans[e][q][1], e))
        sites = list(chosen_runs)
        for e, q in count.items():
            if q == 0:
                continue
            rho, L, alpha, dpiv, x_lo, E, g, beta = plans[e][q]
            for j in range(q):
                xc = x_lo + E + j * (2*E + g)
                sites.append(JogSite(e, xc - E, e, xc + E, alpha, dpiv, L, rho, beta=beta))
        return sites

    MAX_M = 6 # jogs per period
    MAX_SITES = 48

    def jog_layouts(self, k, tpl, pitch, sigmas, layers, limit=6):
        """ Candidate jog layouts for k arms per layer, tpl turns per layer and the given pitch, best predicted first.

        With m jogs per period (1/k revolution), each jog steps by pitch/m. Formally this is the same as a layout for k*m
        arms with a pitch of pitch/m (the arms start at multiples of 1/k = m/(k*m) revolutions). Smaller steps fit
        shorter edges. """
        A = self.annular_width
        n = len(self.polygon)
        s0 = next(iter(sigmas)) if len(sigmas) == 1 else 0
        planned = []
        for m in range(1, self.MAX_M + 1):
            K = k * m
            if K > self.MAX_SITES or K > 4 * n:
                break
            step = pitch / m
            tm = tpl * m
            half = abs(tm - round(tm)) > 1e-9
            configs = [] # (c, pivots, end_sigma)
            if layers == 1:
                # Single layer: the arm starts mid-jog, so that the outermost ring is at half a step depth (otherwise
                # parts of the outline would be a full pitch away from copper). There is no second layer to meet at the
                # arm ends, so the shear can pivot anywhere.
                configs.append((0.0, [0.0, A/2, A], s0))
                configs.append((0.5, [0.0, A/2, A], s0))
            elif half:
                # Folds mid-jog (shear pivots at the fold depth) or starts mid-jog (pivot at depth 0)
                configs.append((0.5, [A], 0))
                configs.append((0.0, [0.0], 0))
            else:
                configs.append((0.5, [0.0, A/2, A], 0))
            for ci, (c, pivots, es) in enumerate(configs):
                seen = []
                for runs, lattice in ((False, False), (True, False), (False, True), (True, True)):
                    sites = self.plan_jogs(K, step, sigmas, pivots, runs=runs, offset=(0.5 - c) * step, pitch=pitch,
                                           lattice=lattice)
                    if not sites:
                        continue
                    key = sorted((st.edge0, st.edge1, round(st.x0, 9)) for st in sites)
                    if key in seen:
                        continue
                    seen.append(key)
                    rho = min(st.rho for st in sites)
                    if (half and c == 0.5) or (c == 0.0 and (half or layers == 1)):
                        # Arm ends in the middle of a jog: the end point (depth 0 or the annular width) is only about
                        # half a jog away from where the neighboring turn leaves the jog
                        for st in sites:
                            reach = st.x1 - st.x0 if st.edge0 == st.edge1 else st.L
                            rho = min(rho, math.hypot(reach / 2, step / 2) / pitch)
                    rs = []
                    for rot in range(min(m, 2) if layers > 1 else 1):
                        layout = JogLayout(self.sk, self.edges, A, step, K, sites, c=c, end_sigma=es, rot=rot)
                        r = round(min(rho, self._end_crowding(layout, k, tpl, pitch, layers)), 3)
                        if r in rs:
                            continue # a rotation that makes no difference to the predicted spacing
                        rs.append(r)
                        planned.append((-r, m, ci, rot, len(planned), layout))
        planned.sort(key=lambda t: t[:5])
        self.planned = [(-t[0], t[-1]) for t in planned]
        return [t[-1] for t in planned[:limit]]

    @staticmethod
    def _end_crowding(layout, k, tpl, pitch, layers):
        """ Smallest distance between the inner (fold) ends of different arms, and between their outer ends, relative to
        the pitch. Vias sit there, and they are at least as wide as the trace. """
        folds = [layout.point(_snap(i/k + tpl/k, layout.k), layout.A) for i in range(k)]
        starts = [layout.point(_snap(i/k, layout.k), 0.0) for i in range(k)]
        best = inf
        for pts in (folds, starts):
            for i in range(len(pts)):
                for j in range(i):
                    best = min(best, dist(pts[i], pts[j]))
        return best / pitch

    def set_layout(self, layout):
        self.layout = layout

    # --- spiral API ---

    def compute_spiral_t(self, a1, a2, fn=None):
        if self.layout is None:
            return super().compute_spiral_t(a1, a2, fn)
        return self.layout.arm(a1/(2*pi), a2/(2*pi))

    def compute_spiral(self, a1, a2, fn=None, debug=False):
        if self.layout is None:
            return super().compute_spiral(a1, a2, fn, debug)
        points, _angles = self.compute_spiral_t(a1, a2)
        return points, sum(dist(p, q) for p, q in zip(points, points[1:])), [None]*len(points)

    def project_point(self, r, a, r_ref=None):
        if self.layout is None:
            return super().project_point(r, a, r_ref)
        w = _snap(a/(2*pi), self.layout.k)
        return self.layout.point(w, self.outer_radius - r)


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


# The predefined shapes of kicoil.geometry, laid out with jogs
class TrapezoidShape(geometry.TrapezoidShape, OffsetShape):
    pass


class RectangleShape(geometry.RectangleShape, OffsetShape):
    pass


class SectorShape(geometry.SectorShape, OffsetShape):
    pass


class StarShape(geometry.StarShape, OffsetShape):
    pass


class RegularPolygonShape(geometry.RegularPolygonShape, OffsetShape):
    pass


class SVGShape(geometry.SVGShape, OffsetShape):
    pass


@dataclass
class PlanarInductor(geometry.PlanarInductor):

    MAX_TRIES = 5

    def __post_init__(self):
        shape = self.shape
        if not (isinstance(shape, OffsetShape) and self.turns >= 1 and self.twists >= 1
                and self.layers in (1, 2) and (self.layers == 1 or gcd(self.twists, self.turns) == 1)):
            return super().__post_init__()

        ranked = self._rank_layouts()
        # Use the layout with the widest turn spacing. If its vias cannot be placed clear of the turns, try the next one.
        initial = {f.name: getattr(self, f.name) for f in dataclasses.fields(self)}
        # Layouts in order of decreasing spacing; the first one whose vias clear the turns wins
        attempts = [layout for d, layout in ranked][:self.MAX_TRIES]

        def build(layout):
            for name, value in initial.items():
                setattr(self, name, value)
            shape.set_layout(layout)
            self._center_lines = None
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                super(PlanarInductor, self).__post_init__()
            return caught

        caught = None
        tried = []
        for layout in attempts:
            caught = build(layout)
            if self._vias_ok():
                break
            gap, _where = self.via_track_clearance()
            tried.append((gap - self.clearance, layout))
        else:
            # Nothing had clear vias. The linear spiral is the reference layout: use it if its vias are clear, else the
            # layout whose vias come closest to clearing the turns.
            if not any(layout is None for layout in attempts):
                caught = build(None)
                if self._vias_ok():
                    tried = None
                else:
                    gap, _where = self.via_track_clearance()
                    tried.append((gap - self.clearance, None))
            if tried is not None:
                best = max(tried, key=lambda t: t[0])[1]
                if best is not shape.layout:
                    caught = build(best)
        self.layout = shape.layout
        for w in caught:
            warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)

    def _vias_ok(self):
        gap, _where = self.via_track_clearance()
        return gap >= self.clearance - 1e-6 and self.via_ring_spacing() >= self.via_diameter + self.clearance - 1e-6

    def _arm_lines(self, k, tpl):
        sector = 2*pi / k * (-1 if self.clockwise else 1)
        sweep = sector * tpl
        arms = [[], []]
        for i in range(k):
            start = i*sector
            fold = start + sweep
            end = fold + sweep
            arms[0].append(self.shape.compute_spiral_t(start, fold))
            if self.layers > 1:
                arms[1].append(self.shape.compute_spiral_t(end, fold))
        return arms

    def _path_sep(self, d):
        """ Separation along an arm above which two pieces of the same arm count as different turns, for a pitch (trace
        width plus clearance) of d. This mirrors the test harness: max(4 pitches, a quarter of the inner perimeter). """
        shape = self.shape
        if isinstance(shape, OffsetShape):
            inner = shape.sk.calc_circumference(shape.inner_radius)
        else:
            inner = 2*pi*shape.inner_radius
        return max(4*d, 0.25*inner)

    def _measure(self, arms, pitch):
        """ Smallest center line distance between neighboring turns, and where it occurs. Same-arm pieces are compared
        when they are half a revolution apart, or further apart along the arm than _path_sep (which depends on the
        result, so iterate). """
        best, where = pitch, None
        sep = self._path_sep(pitch)
        for _ in range(4):
            for layer_arms in arms:
                if layer_arms:
                    d, w = turn_spacing(layer_arms, 1.001 * pitch, sep)
                    if w is not None and d < best:
                        best, where = d, w
            new_sep = self._path_sep(best)
            if new_sep >= sep * 0.999:
                break
            sep = new_sep
        return best, where

    def _spacing(self, k, tpl, pitch):
        return self._measure(self._arm_lines(k, tpl), pitch)[0]

    def measure_turn_spacing(self):
        if getattr(self.shape, 'layout', None) is None and not isinstance(self.shape, OffsetShape):
            return super().measure_turn_spacing()
        best, where = self._measure(self.spiral_center_lines(), self.spiral_pitch)
        if where is None:
            return self.spiral_pitch, None
        return min(best, self.spiral_pitch), where

    def via_track_clearance(self):
        """ Like `geometry.PlanarInductor.via_track_clearance`, but the part of an arm that leads into a via is skipped by
        its length along the arm (see _path_sep), not by its angle. """
        inner_r = self.shape.inner_radius - self.via_offset
        outer_r = self.shape.outer_radius + self.via_offset
        arms = self.spiral_center_lines()
        sep = self._path_sep(self.trace_width + self.clearance)
        vias = [] # (position, {(layer, arm index): path coordinate where the arm connects to the via})
        for i in range(self.twists if self.layers > 1 else 1):
            start_angle, fold_angle, _end_angle = self.arm_angles(i)
            r = inner_r - (2*self.via_offset if self.stagger_inner_vias and i%2 != 0 else 0)
            conn = {}
            if arms[0]:
                conn[(0, i)] = 'end'
            if self.layers > 1 and arms[1]:
                conn[(1, i)] = 'end'
            vias.append((self.shape.project_point(r, fold_angle), conn))
            if i > 0:
                j = (i - self.turns) % self.twists
                r = outer_r + (2*self.via_offset if self.stagger_outer_vias and i%2 != 0 else 0)
                vias.append((self.shape.project_point(r, start_angle), {(0, i): 'start', (1, j): 'start'}))

        best, where = inf, None
        for layer, layer_arms in enumerate(arms):
            for arm, (points, angles) in enumerate(layer_arms):
                s = _path_coords(points)
                total = s[-1]
                for (p1, p2), s1, s2 in zip(zip(points, points[1:]), s, s[1:]):
                    for v, connections in vias:
                        c = connections.get((layer, arm))
                        if c is not None:
                            # arms run from the start (outer end) to the fold (inner end) on layer 0, and from the end
                            # (outer end) to the fold on layer 1
                            sv = total if c == 'end' else 0.0
                            if max(s1 - sv, sv - s2) < sep:
                                continue
                        d = geometry._seg_seg_distance(p1, p2, v, v)
                        if d < best:
                            best, where = d, v
        return best - self.via_diameter/2 - self.trace_width/2, where

    def _rank_layouts(self):
        """ All candidate layouts (jog layouts and the linear spiral, None), sorted by measured turn spacing, widest
        first. Jog layouts win ties. """
        shape = self.shape
        k = 1 if self.layers == 1 else self.twists
        tpl = self.turns / self.layers
        pitch = shape.annular_width / tpl
        s0 = -1 if self.clockwise else 1
        sigmas = {s0} if self.layers == 1 else {s0, -s0}
        cands = []
        for layout in shape.jog_layouts(k, tpl, pitch, sigmas, self.layers):
            shape.set_layout(layout)
            try:
                d = self._spacing(k, tpl, pitch)
            except Exception:
                continue
            cands.append((d, 1, -len(cands), layout))
        shape.set_layout(None)
        try:
            lin = self._spacing(k, tpl, pitch)
        except Exception:
            lin = 0
        cands.append((lin / 0.999, 0, 0, None))
        cands.sort(key=lambda t: (round(t[0] / pitch, 4),) + t[1:3], reverse=True)
        self.layout_candidates = [(d, layout) for d, _p, _i, layout in cands]
        return self.layout_candidates
