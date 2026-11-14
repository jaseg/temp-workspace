""" Skeletonator with virtual vertices for the "optspan" layout (see geometry_alt_optspan).

A virtual vertex sits at a fixed fraction f of a polygon edge. Its "track" is the point at fraction f of that edge on
the offset outline at every depth (i.e. the interpolation between the tracks of the edge's two end points), so it
always lies on the offset outline and the offset outline does not change. Virtual vertices get their own angle
coordinate like real vertices. Since spiral arms run with depth linear in angle between vertices, virtual vertices let
the arm's depth profile along an edge be piecewise linear instead of linear: the arm can run nearly parallel to the
outline next to the corners and descend in the middle of the edge, where neighboring turns are not shifted against each
other by the shrinking or growing of the edge.
"""

import math
import itertools

from .skeletonator import Skeletonator, interpolate


class RefinedSkeletonator(Skeletonator):
    def __init__(self, base, knots):
        """ base: a plain Skeletonator of the polygon. knots: {real edge index: sorted fractions in (0, 1)}. """
        self.__dict__.update(base.__dict__)
        self.base = base
        n = len(base.poly)
        self.real_n = n
        self.vmap = []
        poly = []
        for i in range(n):
            self.vmap.append((i, 0.0))
            poly.append(base.poly[i])
            for f in knots.get(i, ()):
                if 0 < f < 1:
                    self.vmap.append((i, f))
                    poly.append(interpolate(base.poly[i], base.poly[(i+1) % n], f))
        self.poly = poly
        self.poly_edges = list(zip(poly, poly[1:] + poly[:1]))
        self.real_index = [j for j, (i, f) in enumerate(self.vmap) if f == 0]
        self.debug_arms = []

    def track_position(self, i, depth):
        e, f = self.vmap[i]
        p0 = self.base.track_position(e, depth)
        if f == 0:
            return p0
        p1 = self.base.track_position((e + 1) % self.real_n, depth)
        return (p0[0] + f*(p1[0]-p0[0]), p0[1] + f*(p1[1]-p0[1]))

    def set_angle_reference(self, max_depth=None):
        """ Same as Skeletonator.set_angle_reference, for the refined vertex list """
        if max_depth is None:
            max_depth = self.max_depth
        max_depth = max(0, min(max_depth, self.max_depth))
        depths = {0.0, max_depth}
        for times in self.base._track_times:
            depths.update(t for t in times if 0 < t < max_depth)
        n = len(self.poly)
        min_len = [math.inf] * n
        for d in sorted(depths):
            pts = [self.track_position(i, d) for i in range(n)]
            for i in range(n):
                min_len[i] = min(min_len[i], math.dist(pts[i], pts[(i+1) % n]))
        total = sum(min_len)
        if total <= 1e-9 * self.circumference:
            min_len = [math.dist(a, b) for a, b in self.poly_edges]
            total = sum(min_len)
        self.ref_depth = max_depth
        self.vertex_angles = [0.0]
        for l in min_len[:-1]:
            self.vertex_angles.append(self.vertex_angles[-1] + l / total)
        self.vertex_angles = [1.0 if 1.0 - a < 1e-12 else a for a in self.vertex_angles]
        self.edge_spans = [b - a for a, b in itertools.pairwise(self.vertex_angles + [1.0])]

    def _real(self, p):
        return self.base.poly[self.vmap[self.poly.index(p)][0]]

    def iter_arcs(self, p):
        yield from self.base.iter_arcs(self._real(p))

    def project_arc(self, p, r):
        i = self.poly.index(p)
        arc, _pos = self.base.project_arc(self.base.poly[self.vmap[i][0]], r)
        return arc, self.track_position(i, self.radius - r)

    def map_circumference(self, r):
        depth = self.radius - r
        points = [self.track_position(i, depth) for i in range(len(self.poly))]
        return [None] * len(points), points
