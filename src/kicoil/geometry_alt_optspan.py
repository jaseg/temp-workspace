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
""" Planar inductor layout with optimized vertex angle spans ("optspan").

This is the layout of `kicoil.geometry` (spiral depth linear in the angle coordinate between vertices, every vertex at a
fixed angle), but instead of giving each polygon edge an angle span proportional to its length, the spans (and a phase
shift of the arms relative to the polygon) are chosen to maximize the measured minimum distance between neighboring
turns. The trace width is still sized from the measured distance, so clearance is guaranteed as in `kicoil.geometry`.

Why the spans matter: along an edge of length L with angle span s, a spiral arm with k twists and pitch p sinks k*p*s
deeper. The ends of the edge move along the edge as the outline is offset inwards (by cot(theta/2) per unit of depth at
a corner with interior angle theta), so the next turn, which is one pitch deeper, is shifted along the edge against the
current one, by p*cot(theta/2) at the ends of the edge and by zero at the edge's "fixed point" u* in between. The spacing
lost is about the arm's slope times that shift. Hence:

* Edges between sharp corners should get a smaller span than their length suggests, edges between obtuse corners (or
  long edges) a larger one (analytic weighting, `analytic_spans`).
* Within an edge, the arm should run (nearly) parallel to the outline near the corners, where the shift is large, and
  descend near u*, where it is small. This is done with virtual vertices (`skeletonator_alt_optspan`): extra vertices at
  fixed fractions of an edge, with their own angle spans. Between all vertices the depth stays linear in the angle, so
  this is just a finer choice of angle spans. The slope profile approximates 1/max(|u - u*|, delta), which makes the
  product of slope and shift (nearly) constant along the edge (`make_profile`).

The optimization:

1. Candidate span sets: the reference spans of `kicoil.geometry`, the analytic weighting with linear profiles, and the
   analytic weighting with refined profiles (delta chosen per edge by the loss model, virtual vertices only on the edges
   where they gain the most).
2. A scan over a phase shift of all arms (moves arm ends, folds and vias relative to the polygon corners).
3. Iterative reweighting with measured per-edge spacing: the edges at the bottleneck lose span, edges with slack gain
   span, then a local refinement of the phase.

The best measured configuration wins. The reference configuration is always among the candidates, so the result is
never worse than `kicoil.geometry` by the measured spacing. The spacing measurement (`turn_spacing_profile`) is stricter
than `geometry.min_turn_spacing`: besides pieces of different arms and pieces of one arm half a revolution apart, it also
checks pieces of one arm that are far apart along the conductor path, since with non-uniform spans (and in narrow
regions) half a revolution of angle can be a short or a long stretch of the conductor.
"""

import bisect
import itertools
import logging
from dataclasses import dataclass
from math import *

from . import geometry as _geometry
from .skeletonator_alt_optspan import RefinedSkeletonator
from .geometry import (CircleShape, OffsetShape, Shape, TrapezoidShape, RectangleShape, SectorShape, StarShape,
                       RegularPolygonShape, SVGShape, divisors, farey_sequence, arc_approximate, polygon_is_clockwise,
                       _seg_seg_distance, mu_0)

__all__ = ['CircleShape', 'OffsetShape', 'Shape', 'TrapezoidShape', 'RectangleShape', 'SectorShape', 'StarShape',
           'RegularPolygonShape', 'SVGShape', 'PlanarInductor', 'divisors', 'farey_sequence']


ANGLE_QUANTUM = 2.0**-40

def set_spans(sk, spans):
    """ Set the angle coordinate of all vertices of Skeletonator sk from a list of edge spans (one per polygon edge,
    edge i runs from vertex i to vertex i+1). Spans are normalized to add up to one revolution. Zero spans stay exactly
    zero, so that vertices of collapsing edges share their angle exactly.

    The angles are quantized to multiples of 2^-40, so that adding a whole number of revolutions to them is exact in
    floating point. Otherwise an arm end at angle k + a can round to an angle just past a group of vertices that share
    angle a, and the arm ends at the last vertex of the group instead of the first one, cutting across the corner. """
    total = sum(spans)
    angles = [0.0]
    acc = 0.0
    for s in spans[:-1]:
        acc += s / total
        angles.append(acc)
    angles = [min(1.0, round(a / ANGLE_QUANTUM) * ANGLE_QUANTUM) for a in angles]
    sk.vertex_angles = angles
    sk.edge_spans = [b - a for a, b in itertools.pairwise(angles + [1.0])]


def turn_spacing_profile(arms, search_radius, vertex_angles, path_floor, min_turn_separation=0.5, stats=None):
    """ Like geometry.min_turn_spacing, but stricter for pieces of the same arm, and additionally returns the smallest
    distance seen by each polygon edge.

    Pieces of different arms are always checked against each other. Pieces of the same arm are checked against each
    other when they are at least min_turn_separation revolutions apart (as in geometry.min_turn_spacing), *or* when the
    path length between them along the arm is at least max(4*d, path_floor), where d is their distance. The latter is
    what a clearance check along the conductor path counts as belonging to different turns (pieces closer than
    4*(trace width + clearance) along the path never are). This matters when the angle spans are far from proportional
    to the edge lengths, or in narrow regions where an arm comes back close to itself.

    Returns (distance, location, per_edge) where per_edge[i] is the smallest center line distance between a piece of
    a turn running along edge i (by angle) and another turn, or search_radius when there is none closer. If stats is a
    dict, the number of candidate pairs examined is added to stats['pairs'] (a deterministic measure of the work). """
    n_edges = len(vertex_angles)
    segs = []
    max_span = min_turn_separation / 10
    for arm_idx, (points, angles) in enumerate(arms):
        s_acc = 0.0
        for (p1, p2), (t1, t2) in zip(zip(points, points[1:]), zip(angles, angles[1:])):
            if p1 == p2:
                continue
            seg_len = dist(p1, p2)
            n = max(1, ceil(abs(t2 - t1) / max_span))
            for i in range(n):
                q1 = (p1[0] + (p2[0]-p1[0])*i/n, p1[1] + (p2[1]-p1[1])*i/n)
                q2 = (p1[0] + (p2[0]-p1[0])*(i+1)/n, p1[1] + (p2[1]-p1[1])*(i+1)/n)
                u1, u2 = t1 + (t2-t1)*i/n, t1 + (t2-t1)*(i+1)/n
                mid = (u1 + u2) / 2
                frac = mid - floor(mid)
                edge = max(0, bisect.bisect_right(vertex_angles, frac) - 1)
                segs.append((q1, q2, arm_idx, min(u1, u2), max(u1, u2), edge,
                             s_acc + seg_len*i/n, s_acc + seg_len*(i+1)/n,
                             min(q1[0], q2[0]), max(q1[0], q2[0]), min(q1[1], q2[1]), max(q1[1], q2[1])))
            s_acc += seg_len

    cell = search_radius
    grid = {}
    for idx, sg in enumerate(segs):
        x0, x1, y0, y1 = sg[8:12]
        for gx in range(floor(x0/cell), floor(x1/cell) + 1):
            for gy in range(floor(y0/cell), floor(y1/cell) + 1):
                grid.setdefault((gx, gy), []).append(idx)

    per_edge = [search_radius] * n_edges
    best, where = search_radius, None
    pairs = 0
    for idx, (p1, p2, arm, t_lo, t_hi, edge, s_lo, s_hi, ax0, ax1, ay0, ay1) in enumerate(segs):
        seen = set()
        for gx in range(floor((ax0 - search_radius)/cell), floor((ax1 + search_radius)/cell) + 1):
            for gy in range(floor((ay0 - search_radius)/cell), floor((ay1 + search_radius)/cell) + 1):
                for jdx in grid.get((gx, gy), ()):
                    if jdx <= idx or jdx in seen:
                        continue
                    seen.add(jdx)
                    pairs += 1
                    q1, q2, arm_j, u_lo, u_hi, edge_j, r_lo, r_hi, bx0, bx1, by0, by1 = segs[jdx]
                    bound = max(per_edge[edge], per_edge[edge_j])
                    if bx0 - ax1 >= bound or ax0 - bx1 >= bound or by0 - ay1 >= bound or ay0 - by1 >= bound:
                        continue
                    d = _seg_seg_distance(p1, p2, q1, q2)
                    if d >= bound:
                        continue
                    if arm_j == arm and max(u_lo - t_hi, t_lo - u_hi) < min_turn_separation:
                        if max(r_lo - s_hi, s_lo - r_hi) < max(4*d, path_floor):
                            continue
                    if d < per_edge[edge]:
                        per_edge[edge] = d
                    if d < per_edge[edge_j]:
                        per_edge[edge_j] = d
                    if d < best:
                        best, where = d, ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2)
    if stats is not None:
        stats['pairs'] = stats.get('pairs', 0) + pairs
    return best, where, per_edge


def _sample_depths(sk, max_depth):
    depths = {0.0, max_depth}
    for times in sk._track_times:
        depths.update(t for t in times if 0 < t < max_depth)
    depths = sorted(depths)
    # Add intermediate samples, the edge lengths are piecewise linear in depth but the loss model is not
    out = []
    for a, b in itertools.pairwise(depths):
        out.extend(a + (b - a) * j / 4 for j in range(4))
    out.append(depths[-1])
    return out


def edge_samples(sk, max_depth, k, pitch):
    """ Per polygon edge of Skeletonator sk, a list of (a, c1, c2) samples over the depth range [0, max_depth]: a is
    the slope of a spiral arm relative to the edge per unit of angle span (k*pitch / edge length), c1 and c2 are the
    distances by which the edge's start and end point move along the edge per unit of depth, positive when the edge
    shrinks there (cot of half the corner angle for a plain corner). a is inf where the edge has collapsed. """
    n = len(sk.poly)
    eps = max(1e-6, 1e-4 * max_depth)
    samples = [[] for _ in range(n)]
    for d in _sample_depths(sk, max_depth):
        d0, d1 = max(0.0, d - eps), min(d + eps, sk.max_depth)
        if d1 <= d0:
            continue
        pts = [sk.track_position(i, d) for i in range(n)]
        pts0 = [sk.track_position(i, d0) for i in range(n)]
        pts1 = [sk.track_position(i, d1) for i in range(n)]
        for i in range(n):
            j = (i + 1) % n
            a, b = pts[i], pts[j]
            L = dist(a, b)
            if L < 1e-9:
                samples[i].append((inf, 0.0, 0.0))
                continue
            ex, ey = (b[0]-a[0])/L, (b[1]-a[1])/L
            c1 = ((pts1[i][0]-pts0[i][0])*ex + (pts1[i][1]-pts0[i][1])*ey) / (d1 - d0)
            c2 = -((pts1[j][0]-pts0[j][0])*ex + (pts1[j][1]-pts0[j][1])*ey) / (d1 - d0)
            samples[i].append((k * pitch / L, c1, c2))
    return samples


LINEAR_PROFILE = ((), (1.0,))

def make_profile(ustar, delta, ratio=1.6):
    """ Depth profile along an edge as (knots, weights): interior knot fractions and the fraction of the edge's angle
    span (i.e. of its depth change) for each piece between 0, the knots and 1. The profile approximates a depth slope
    proportional to 1 / max(|u - ustar|, delta) at edge fraction u.

    Why: when the edge shrinks or grows as it is offset inwards, the turn one pitch deeper is shifted along the edge
    against the current turn by an amount proportional to (ustar - u), where ustar is the fixed point of the shrinking.
    The loss of spacing is the slope times this shift, so the slope should be inversely proportional to the shift. """
    knots = set()
    for sgn in (-1, 1):
        x = delta
        for _ in range(64):
            u = ustar + sgn*x
            if (sgn < 0 and u <= 0) or (sgn > 0 and u >= 1):
                break
            if 0 < u < 1:
                knots.add(u)
            x *= ratio
    knots = sorted(u for u in knots if 1e-3 < u < 1 - 1e-3)
    def G(u):
        x = u - ustar
        if abs(x) <= delta:
            return x / delta
        return copysign(1 + log(abs(x) / delta), x)
    bounds = [0.0] + knots + [1.0]
    weights = [G(b) - G(a) for a, b in itertools.pairwise(bounds)]
    total = sum(weights)
    return tuple(knots), tuple(w / total for w in weights)


def profile_terms(profile, c1, c2):
    """ (B, M) of a profile for end point shifts c1, c2: B = max over the edge of slope factor times shift, M = max slope
    factor. The relative spacing on the edge for slope a*s is about (1 - a*s*B) / sqrt(1 + (a*s*M)^2). """
    knots, weights = profile
    bounds = [0.0] + list(knots) + [1.0]
    B, M = 0.0, 0.0
    for (ua, ub), w in zip(itertools.pairwise(bounds), weights):
        fp = w / (ub - ua) # slope factor on this piece
        shift = max(abs(c1 - ua*(c1 + c2)), abs(c1 - ub*(c1 + c2)))
        B = max(B, fp * shift)
        M = max(M, fp)
    return B, M


def _max_slope(g, B, M):
    """ Largest x >= 0 with (1 - x*B) / sqrt(1 + (x*M)^2) >= g """
    if g >= 1:
        return 0.0
    return (1 - g*g) / (B + sqrt(g*g * (B*B + M*M*(1 - g*g))))


def analytic_spans(samples, base_spans, profile_options, knot_budget=None, gain_fraction=0.85):
    """ Edge spans from the loss model. For each edge, profile_options[i] is a list of candidate profiles, the first of
    which must be the plain linear profile. For a target relative spacing g, each edge gets the largest span (with the
    best of its profiles) that keeps that spacing at all sampled depths, and g is chosen by bisection so that the spans
    add up to one revolution. Edges with zero base span (collapsing edges) keep a zero span.

    Refined profiles cost extra vertices (and evaluation time). They are only kept for the edges that account for
    gain_fraction of the total span gain over the linear profile, and for at most knot_budget extra vertices.

    Returns (spans, chosen profile per edge, g) or None. """
    n = len(samples)
    terms = []
    for i in range(n):
        opts = []
        if base_spans[i] > 0 and samples[i] and all(a < inf for a, _c1, _c2 in samples[i]):
            for prof in profile_options[i]:
                opts.append((prof, [(a, *profile_terms(prof, c1, c2)) for a, c1, c2 in samples[i]]))
        terms.append(opts)
    if not any(terms):
        return None

    def solve(terms):
        def spans_for(g):
            spans, profs, gains = [], [], []
            for opts in terms:
                best_s, best_p, lin_s = 0.0, None, 0.0
                for idx, (prof, ts) in enumerate(opts):
                    s = min(_max_slope(g, B, M) / a for a, B, M in ts)
                    if idx == 0:
                        lin_s = s
                    # Only use a refined profile when it is noticeably better than the plain one
                    if best_p is None or s > best_s * (1.02 if idx > 0 else 1.0):
                        best_s, best_p = s, prof
                spans.append(best_s)
                profs.append(best_p)
                gains.append(best_s - lin_s)
            return spans, profs, gains

        lo, hi = 0.0, 1.0
        result = None
        for _ in range(40):
            g = (lo + hi) / 2
            res = spans_for(g)
            if sum(res[0]) >= 1.0:
                lo, result = g, res
            else:
                hi = g
        if result is None or sum(result[0]) <= 0:
            return None
        return (*result, lo)

    result = solve(terms)
    if result is None:
        return None
    spans, profs, gains, g = result
    total_gain = sum(gains)
    if total_gain > 0:
        keep = set()
        acc, knots = 0.0, 0
        for gain, i in sorted(((gain, i) for i, gain in enumerate(gains) if gain > 0), reverse=True):
            if acc >= gain_fraction * total_gain:
                break
            if knot_budget is not None and knots + len(profs[i][0]) > knot_budget:
                continue
            keep.add(i)
            acc += gain
            knots += len(profs[i][0])
        if len(keep) < sum(1 for x in gains if x > 0):
            result = solve([opts if i in keep else opts[:1] for i, opts in enumerate(terms)])
            if result is None:
                return None
            spans, profs, gains, g = result
    total = sum(spans)
    return [s / total for s in spans], profs, g


def _ustar(samples_i):
    """ Fixed point of the shrinking/growing of an edge (as fraction of the edge) at the sample with the largest loss """
    worst, c1, c2 = -1, 0.0, 0.0
    for a, s1, s2 in samples_i:
        if a < inf and a * max(abs(s1), abs(s2)) > worst:
            worst, c1, c2 = a * max(abs(s1), abs(s2)), s1, s2
    if abs(c1 + c2) < 1e-9:
        return 0.5 if abs(c1) < 1e-9 else (-20.0 if c1 < 0 else 21.0)
    return max(-20.0, min(21.0, c1 / (c1 + c2)))


@dataclass
class PlanarInductor(_geometry.PlanarInductor):
    optimize_spans: bool = True
    refine_edges: bool = True
    phase_steps: int = 8
    reweight_iterations: int = 24
    reweight_starts: int = 2
    knot_budget: int = 40
    work_budget: int = 400_000

    PROFILE_DELTAS = (0.3, 0.15, 0.08, 0.04)

    def __post_init__(self):
        self.arm_phase = 0.0 # radians, shift of all arms relative to the polygon's angle origin
        self._optimized = False
        self._work = {}
        super().__post_init__()

    def arm_angles(self, i):
        start_angle, fold_angle, end_angle = super().arm_angles(i)
        return start_angle + self.arm_phase, fold_angle + self.arm_phase, end_angle + self.arm_phase

    def measure_turn_spacing(self):
        if not isinstance(self.shape, OffsetShape):
            return super().measure_turn_spacing()
        if not self._optimized:
            self._optimized = True
            self._reference_config = None
            if self.optimize_spans:
                try:
                    self.optimize_layout()
                except Exception as e: # never fail because of the optimizer, fall back to the reference layout
                    self.logger.warning(f'Span optimization failed: {e!r}')
                    if self._reference_config is not None:
                        self._set_config(self._reference_config)
        best, where, _per_edge = self._measure()
        if where is None:
            return self.spiral_pitch, None
        return min(best, self.spiral_pitch), where

    def _set_config(self, config):
        sk, spans, phase = config
        set_spans(sk, spans)
        self.shape.sk = sk
        self.arm_phase = phase
        self._center_lines = None

    def _path_floor(self):
        """ Lower bound of the path length along an arm beyond which a clearance check counts two pieces as different
        turns: a quarter of the inner outline's length (with some margin). """
        sk = getattr(self.shape.sk, 'base', self.shape.sk)
        d = self.shape.annular_width
        pts = [sk.track_position(i, d) for i in range(len(sk.poly))]
        inner_len = sum(dist(a, b) for a, b in zip(pts, pts[1:] + pts[:1]))
        return 0.9 * 0.25 * inner_len

    def _measure(self):
        """ Strict measured minimum turn spacing of the current configuration: (distance, location, per-edge distance) """
        arms = self.spiral_center_lines()
        search_radius = 1.5 * self.spiral_pitch
        sk = self.shape.sk
        floor_ = self._path_floor()
        best, where = search_radius, None
        per_edge = [search_radius] * len(sk.poly)
        for layer_arms in arms:
            if not layer_arms:
                continue
            d, w, pe = turn_spacing_profile(layer_arms, search_radius, sk.vertex_angles, floor_, stats=self._work)
            if d < best:
                best, where = d, w
            per_edge = [min(a, b) for a, b in zip(per_edge, pe)]
        return best, where, per_edge

    def _evaluate(self, config):
        """ Measured minimum turn spacing and per-edge minimum spacing for the given (skeletonator, spans, phase) """
        self._set_config(config)
        best, _where, per_edge = self._measure()
        return best, per_edge

    def optimize_layout(self):
        # Always start from the plain skeletonator of the polygon, even if this shape was optimized before
        base_sk = getattr(self.shape.sk, 'base', self.shape.sk)
        base_sk.set_angle_reference(self.shape.annular_width)
        base_spans = list(base_sk.edge_spans)
        self._reference_config = (base_sk, base_spans, 0.0)
        n = len(base_sk.poly)
        k = self.twists
        pitch = self.spiral_pitch
        sign = 1 if self.sector_angle > 0 else -1

        cache = {}
        def evaluate(cfg):
            sk, spans, phase = cfg
            key = (id(sk), tuple(round(s, 12) for s in spans), round(phase, 12))
            if key not in cache:
                cache[key] = self._evaluate(cfg)
            return cache[key]

        candidates = [(base_sk, base_spans)]
        samples = edge_samples(base_sk, self.shape.annular_width, k, pitch)
        ana = analytic_spans(samples, base_spans, [[LINEAR_PROFILE]] * n)
        if ana is not None:
            candidates.append((base_sk, ana[0]))
        if self.refine_edges:
            options = []
            for i in range(n):
                us = _ustar(samples[i])
                options.append([LINEAR_PROFILE] + [make_profile(us, d) for d in self.PROFILE_DELTAS])
            ana_r = analytic_spans(samples, base_spans, options, knot_budget=self.knot_budget)
            if ana_r is not None:
                spans, profs, _g = ana_r
                knots = {i: list(p[0]) for i, p in enumerate(profs) if p is not None and p[0]}
                if knots:
                    rsk = RefinedSkeletonator(base_sk, knots)
                    rspans = []
                    for i in range(n):
                        prof = profs[i] or LINEAR_PROFILE
                        rspans.extend(spans[i] * w for w in prof[1])
                    candidates.append((rsk, rspans))

        # The measured spacing is capped at the nominal pitch, there is nothing to gain beyond that.
        good_enough = 0.998 * pitch

        # Stage 1+2: span candidates times arm phases. The phase shifts the arms by a fraction of the angle between
        # neighboring arms.
        phases = [sign * 2*pi/k * j/self.phase_steps for j in range(self.phase_steps)]
        unique = []
        for sk, spans in candidates:
            if not any(sk is sk2 and all(abs(a - b) < 1e-9 for a, b in zip(spans, spans2)) for sk2, spans2 in unique):
                unique.append((sk, spans))
        # Work budget: the optimization stops early when the spacing measurements examined this many segment pairs
        # (a deterministic stand-in for run time, which grows with the number of turns and vertices).
        over_budget = lambda: self._work.get('pairs', 0) > self.work_budget

        best_val, best_cfg = -inf, None
        cand_best = [(-inf, None)] * len(unique) # best (value, config) of every candidate over the phases
        for j, phase in enumerate(phases):
            for c, (sk, spans) in enumerate(unique):
                if best_val >= good_enough or (j > 0 and over_budget()):
                    break
                val, pe = evaluate((sk, spans, phase))
                if val > cand_best[c][0] + 1e-9:
                    cand_best[c] = (val, (sk, spans, phase))
                if val > best_val + 1e-9:
                    best_val, best_cfg = val, (sk, spans, phase)
        per_candidate = [x for x in cand_best if x[1] is not None]

        # Stage 3: iterative reweighting of the spans, starting from the best two candidates (at their best phase)
        per_candidate.sort(key=lambda x: -x[0])
        for _val, start_cfg in per_candidate[:self.reweight_starts]:
            sk, spans, phase = start_cfg
            cur_val, cur_pe = evaluate(start_cfg)
            eta = 1.0
            for it in range(self.reweight_iterations):
                if best_val >= good_enough or over_budget():
                    break
                new = []
                for i in range(len(spans)):
                    if spans[i] <= 0:
                        new.append(0.0)
                        continue
                    ratio = max(0.5, min(2.0, cur_pe[i] / cur_val)) if cur_val > 0 else 1.0
                    new.append(spans[i] * ratio ** eta)
                total = sum(new)
                new = [x / total for x in new]
                val, pe = evaluate((sk, new, phase))
                if val > cur_val + 1e-9:
                    spans, cur_val, cur_pe = new, val, pe
                    if val > best_val + 1e-9:
                        best_val, best_cfg = val, (sk, new, phase)
                else:
                    eta /= 2
                    if eta < 1/64:
                        break

        # Final phase refinement around the best phase
        sk, spans, phase = best_cfg
        step = 2*pi/k / self.phase_steps
        for _ in range(3):
            step /= 2
            for ph in (phase - step, phase + step):
                if best_val >= good_enough or over_budget():
                    break
                val, _pe = evaluate((sk, spans, ph))
                if val > best_val + 1e-9:
                    best_val, best_cfg = val, (sk, spans, ph)
            sk, spans, phase = best_cfg

        self._set_config(best_cfg)
        ref_val = evaluate(self._reference_config)[0]
        self._set_config(best_cfg)
        self.optimization_info = dict(reference=ref_val, optimized=best_val, evaluations=len(cache),
                                      pairs=self._work.get('pairs', 0),
                                      refined=isinstance(best_cfg[0], RefinedSkeletonator), phase=best_cfg[2])
        self.logger.info(f'Span optimization: min turn spacing {ref_val:.4f} -> {best_val:.4f} mm '
                         f'({len(cache)} evaluations, phase {degrees(best_cfg[2]):.1f} deg)')
