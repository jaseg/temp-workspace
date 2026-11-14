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

This is the layout of `kicoil.geometry` (spiral depth linear in the angle coordinate between polygon vertices, every
vertex at a fixed angle), but instead of giving each polygon edge an angle span proportional to its length, the spans
(and a phase shift of the arms relative to the polygon) are chosen to maximize the measured minimum distance between
neighboring turns. The trace width is still sized from that measured distance, so clearance is guaranteed exactly as in
`kicoil.geometry`.

Why the spans matter: along an edge of length L with angle span s, a spiral arm with k twists and pitch p sinks k*p*s
deeper. The ends of the edge move along the edge as the outline is offset inwards (by cot(theta/2) per unit of depth at
a corner with interior angle theta), so the next turn, which is one pitch deeper, is shifted along the edge relative to
the current one by up to p*cot(theta/2). Combined with the slope this costs about k*p*s/L * p*cot(theta/2) of spacing.
Edges next to sharp corners should therefore get a smaller span than their length suggests, and edges next to obtuse
corners (or long edges) a larger one.

The optimization runs in three stages:

1. An analytic span weighting from that loss model (per edge, the largest slope that keeps a common target spacing,
   with the target found by bisection so that the spans add up to one revolution).
2. A scan over a phase shift of all arms (moves arm ends, folds and vias relative to the polygon corners).
3. Iterative reweighting with measured per-edge spacing: the edges at the bottleneck lose span, edges with slack gain
   span. The best measured configuration wins; the reference configuration of `kicoil.geometry` is always among the
   candidates, so the result is never worse than that by the measured spacing.
"""

import bisect
import itertools
import logging
from dataclasses import dataclass
from math import *

from . import geometry as _geometry
from .geometry import (CircleShape, OffsetShape, Shape, TrapezoidShape, RectangleShape, SectorShape, StarShape,
                       RegularPolygonShape, SVGShape, divisors, farey_sequence, arc_approximate, polygon_is_clockwise,
                       min_turn_spacing, _seg_seg_distance, mu_0)

__all__ = ['CircleShape', 'OffsetShape', 'Shape', 'TrapezoidShape', 'RectangleShape', 'SectorShape', 'StarShape',
           'RegularPolygonShape', 'SVGShape', 'PlanarInductor', 'divisors', 'farey_sequence']


def set_spans(sk, spans):
    """ Set the angle coordinate of all vertices of Skeletonator sk from a list of edge spans (one per polygon edge,
    edge i runs from vertex i to vertex i+1). Spans are normalized to add up to one revolution. Zero spans stay exactly
    zero, so that vertices of collapsing edges share their angle exactly. """
    total = sum(spans)
    spans = [s / total for s in spans]
    angles = [0.0]
    for s in spans[:-1]:
        angles.append(angles[-1] + s if s > 0 else angles[-1])
    angles = [1.0 if 1.0 - a < 1e-12 else a for a in angles]
    sk.vertex_angles = angles
    sk.edge_spans = [b - a for a, b in itertools.pairwise(angles + [1.0])]


def turn_spacing_profile(arms, search_radius, vertex_angles, min_turn_separation=0.5):
    """ Like geometry.min_turn_spacing, but additionally returns the smallest distance seen by each polygon edge.

    Returns (distance, location, per_edge) where per_edge[i] is the smallest center line distance between a piece of
    a turn running along edge i (by angle) and a neighboring turn, or search_radius when there is none closer. """
    n_edges = len(vertex_angles)
    segs = []
    max_span = min_turn_separation / 10
    for arm_idx, (points, angles) in enumerate(arms):
        for (p1, p2), (t1, t2) in zip(zip(points, points[1:]), zip(angles, angles[1:])):
            if p1 == p2:
                continue
            n = max(1, ceil(abs(t2 - t1) / max_span))
            for i in range(n):
                q1 = (p1[0] + (p2[0]-p1[0])*i/n, p1[1] + (p2[1]-p1[1])*i/n)
                q2 = (p1[0] + (p2[0]-p1[0])*(i+1)/n, p1[1] + (p2[1]-p1[1])*(i+1)/n)
                u1, u2 = t1 + (t2-t1)*i/n, t1 + (t2-t1)*(i+1)/n
                mid = (u1 + u2) / 2
                frac = mid - floor(mid)
                edge = max(0, bisect.bisect_right(vertex_angles, frac) - 1)
                segs.append((q1, q2, arm_idx, min(u1, u2), max(u1, u2), edge))

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

    per_edge = [search_radius] * n_edges
    best, where = search_radius, None
    for idx, (p1, p2, arm, t_lo, t_hi, edge) in enumerate(segs):
        seen = set()
        for c in cells(p1, p2, search_radius):
            for jdx in grid.get(c, ()):
                if jdx <= idx or jdx in seen:
                    continue
                seen.add(jdx)
                q1, q2, arm_j, u_lo, u_hi, edge_j = segs[jdx]
                if arm_j == arm and max(u_lo - t_hi, t_lo - u_hi) < min_turn_separation:
                    continue
                d = _seg_seg_distance(p1, p2, q1, q2)
                if d < per_edge[edge]:
                    per_edge[edge] = d
                if d < per_edge[edge_j]:
                    per_edge[edge_j] = d
                if d < best:
                    best, where = d, ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2)
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


def analytic_spans(sk, max_depth, k, pitch, base_spans):
    """ Edge spans from the loss model described in the module docstring.

    For edge i at depth d with length L and end point shifts c1, c2 (along-edge movement of the end points per unit of
    depth, positive when the edge shrinks), a span s gives the slope a = k*pitch*s/L, and the relative spacing between
    neighboring turns is approximately (1 - a*max(|c1|, |c2|)) / sqrt(1 + a^2). For a target relative spacing g, each
    edge gets the largest span that keeps that spacing at all sampled depths, and g is chosen by bisection so that the
    spans add up to one revolution. Edges with zero base span (collapsing edges) keep a zero span.
    """
    n = len(sk.poly)
    depths = _sample_depths(sk, max_depth)
    eps = max(1e-6, 1e-4 * max_depth)
    # per edge list of (slope per unit span, shift) samples
    samples = [[] for _ in range(n)]
    for d in depths:
        d0, d1 = max(0.0, d - eps), d + eps if d + eps <= sk.max_depth else d
        if d1 <= d0:
            continue
        pts = [sk.track_position(i, d) for i in range(n)]
        pts0 = [sk.track_position(i, d0) for i in range(n)]
        pts1 = [sk.track_position(i, d1) for i in range(n)]
        for i in range(n):
            if base_spans[i] <= 0:
                continue
            j = (i + 1) % n
            a, b = pts[i], pts[j]
            L = dist(a, b)
            if L < 1e-9:
                samples[i].append((inf, 0.0))
                continue
            ex, ey = (b[0]-a[0])/L, (b[1]-a[1])/L
            # shift of the end points along the edge per unit depth, positive when the edge shrinks
            c1 = ((pts1[i][0]-pts0[i][0])*ex + (pts1[i][1]-pts0[i][1])*ey) / (d1 - d0)
            c2 = -((pts1[j][0]-pts0[j][0])*ex + (pts1[j][1]-pts0[j][1])*ey) / (d1 - d0)
            samples[i].append((k * pitch / L, max(abs(c1), abs(c2))))

    def max_span(i, g):
        """ Largest span of edge i that keeps relative spacing g at all sampled depths """
        s_best = inf
        for a, c in samples[i]:
            if a == inf:
                return 0.0
            # solve (1 - x*c) / sqrt(1 + x^2) = g for slope x >= 0 (left side is decreasing in x)
            lo, hi = 0.0, 1.0
            f = lambda x: (1 - x*c) / sqrt(1 + x*x) - g
            if f(0) <= 0:
                return 0.0
            while f(hi) > 0 and hi < 1e6:
                hi *= 2
            for _ in range(50):
                mid = (lo + hi) / 2
                if f(mid) > 0:
                    lo = mid
                else:
                    hi = mid
            s_best = min(s_best, lo / a)
        return s_best

    active = [i for i in range(n) if base_spans[i] > 0 and samples[i]]
    if not active:
        return None
    lo_g, hi_g = 0.0, 1.0
    spans = None
    for _ in range(40):
        g = (lo_g + hi_g) / 2
        s = [max_span(i, g) if i in active else 0.0 for i in range(n)]
        if sum(s) >= 1.0:
            lo_g, spans = g, s
        else:
            hi_g = g
    if spans is None or sum(spans) <= 0:
        return None
    total = sum(spans)
    return [x / total for x in spans]


@dataclass
class PlanarInductor(_geometry.PlanarInductor):
    optimize_spans: bool = True
    phase_steps: int = 8
    reweight_iterations: int = 24

    def __post_init__(self):
        self.arm_phase = 0.0 # radians, shift of all arms relative to the polygon's angle origin
        self._optimized = False
        super().__post_init__()

    def arm_angles(self, i):
        start_angle, fold_angle, end_angle = super().arm_angles(i)
        return start_angle + self.arm_phase, fold_angle + self.arm_phase, end_angle + self.arm_phase

    def measure_turn_spacing(self):
        if not self._optimized:
            self._optimized = True
            if self.optimize_spans and isinstance(self.shape, OffsetShape):
                try:
                    self.optimize_layout()
                except Exception as e: # never fail because of the optimizer, fall back to the reference layout
                    self.logger.warning(f'Span optimization failed: {e}')
                    self._set_config(self._reference_config)
        return super().measure_turn_spacing()

    def _set_config(self, config):
        spans, phase = config
        set_spans(self.shape.sk, spans)
        self.arm_phase = phase
        self._center_lines = None

    def _evaluate(self, config):
        """ Measured minimum turn spacing and per-edge minimum spacing for the given (spans, phase) """
        self._set_config(config)
        arms = self.spiral_center_lines()
        search_radius = 1.5 * self.spiral_pitch
        sk = self.shape.sk
        best = search_radius
        per_edge = [search_radius] * len(sk.poly)
        for layer_arms in arms:
            if not layer_arms:
                continue
            d, _where, pe = turn_spacing_profile(layer_arms, search_radius, sk.vertex_angles)
            best = min(best, d)
            per_edge = [min(a, b) for a, b in zip(per_edge, pe)]
        return best, per_edge

    def optimize_layout(self):
        sk = self.shape.sk
        n = len(sk.poly)
        base_spans = list(sk.edge_spans)
        self._reference_config = (base_spans, 0.0)
        k = self.twists
        pitch = self.spiral_pitch
        sign = 1 if self.sector_angle > 0 else -1

        cache = {}
        def evaluate(spans, phase):
            key = (tuple(round(s, 12) for s in spans), round(phase, 12))
            if key not in cache:
                cache[key] = self._evaluate((spans, phase))
            return cache[key]

        candidates = [base_spans]
        ana = analytic_spans(sk, self.shape.annular_width, k, pitch, base_spans)
        if ana is not None:
            candidates.append(ana)

        # Stage 1+2: span candidates times arm phases. The phase shifts the arms by a fraction of the angle between
        # neighboring arms.
        phases = [sign * 2*pi/k * j/self.phase_steps for j in range(self.phase_steps)]
        best_val, best_cfg, best_pe = -inf, None, None
        for spans in candidates:
            for phase in phases:
                val, pe = evaluate(spans, phase)
                if val > best_val + 1e-9:
                    best_val, best_cfg, best_pe = val, (spans, phase), pe

        # Stage 3: iterative reweighting of the spans at the best phase
        spans, phase = best_cfg
        cur_val, cur_pe = best_val, best_pe
        eta = 1.0
        for it in range(self.reweight_iterations):
            ref = cur_val
            new = []
            for i in range(n):
                if spans[i] <= 0:
                    new.append(0.0)
                    continue
                ratio = max(0.5, min(2.0, cur_pe[i] / ref)) if ref > 0 else 1.0
                new.append(spans[i] * ratio ** eta)
            total = sum(new)
            new = [s / total for s in new]
            val, pe = evaluate(new, phase)
            if val > cur_val + 1e-9:
                spans, cur_val, cur_pe = new, val, pe
                if val > best_val + 1e-9:
                    best_val, best_cfg = val, (new, phase)
            else:
                eta /= 2
                if eta < 1/64:
                    break

        # Final phase refinement around the best phase
        spans, phase = best_cfg
        step = 2*pi/k / self.phase_steps
        for _ in range(3):
            step /= 2
            for ph in (phase - step, phase + step):
                val, _pe = evaluate(spans, ph)
                if val > best_val + 1e-9:
                    best_val, best_cfg = val, (spans, ph)
            spans, phase = best_cfg

        self._set_config(best_cfg)
        ref_val = cache[(tuple(round(s, 12) for s in base_spans), 0.0)][0]
        self.logger.info(f'Span optimization: min turn spacing {ref_val:.4f} -> {best_val:.4f} mm '
                         f'({len(cache)} evaluations, phase {degrees(best_cfg[1]):.1f} deg)')
