import math
import itertools

from py_straight_skeleton import compute_skeleton


def interpolate(p1, p2, t, t_start=0, t_end=1):
    """ Interpolate along the line from point p1 to point p2 using t as the interpolation variable.
        t_start and t_end set the bounds of t, t_start at p1, and t_end at p2.
        When both interval ends coincide, clips and returns p1.
    """
    if math.isclose(t_start, t_end):
        return p1
    t_range = t_end - t_start
    t = (t - t_start) / t_range
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    return (x1 + t*dx, y1 + t*dy)


def approx_in_range(value, lower, upper):
    """ Approximate range check """
    if math.isclose(value, lower) or math.isclose(value, upper):
        return True
    return lower <= value <= upper


def edge_cycle(points):
    """ From a list of points return an iterator of all edges assuming they are a closed loop:
        [A B C] -> [AB BC CA]
    """
    return itertools.pairwise(itertools.chain(points, points[:1]))


class Skeletonator:
    def __init__(self, poly):
        self.poly = poly
        self.poly_edges = list(zip(poly, poly[1:] + poly[:1]))
        self.circumference = sum(math.dist(a, b) for a, b in self.poly_edges)
        self.skeleton = compute_skeleton(exterior=poly, holes=[])
        self.arc_map = {}
        self.divergent = set()
        self.radius = max(n.time for n in self.skeleton.nodes)
        self.min_radius = self.radius
        for n1, n2 in self.skeleton.arc_iterator():
            if n1 in self.arc_map:
                self.divergent.add(n1)
                self.min_radius = min(n1.time, self.radius)
            self.arc_map[n1] = n2
        self.node_map = dict(zip(poly, self.skeleton.nodes))

    def iter_arcs(self, p):
        start = self.node_map[p]
        while start in self.arc_map and not start in self.divergent:
            end = self.arc_map[start]
            yield start, end
            start = end

    def project_arc(self, p, r):
        t = self.radius - r

        for n0, n1 in self.iter_arcs(p):
            if t < 0 or approx_in_range(t, n0.time, n1.time):
                p0 = (n0.position.x, n0.position.y)
                p1 = (n1.position.x, n1.position.y)
                return (n0, n1), interpolate(p0, p1, t, n0.time, n1.time)
        else:
            raise ValueError('r is out of bounds!')

    def calc_circumference(self, r):
        projected = [self.project_arc(p, r)[1] for p in self.poly]
        return sum(math.dist(p1, p2) for p1, p2 in zip(projected, projected[1:] + projected[:1]))

    def project_point(self, t, r=None, r_ref=None):
        t %= 1
        if r is None:
            r = self.radius

        if r_ref is None:
            r_ref = r
        
        t_start = 0
        p_cur = None
        _arcs, points_at_r = self.map_circumference(r_ref)
        circumference_at_r = sum(math.dist(p1, p2) for p1, p2 in edge_cycle(points_at_r))
        for (p1, p2), (p1r, p2r) in zip(self.poly_edges, edge_cycle(points_at_r)):
            edge_frac = math.dist(p1r, p2r) / circumference_at_r
            t_end = t_start + edge_frac
    
            if approx_in_range(t, t_start, t_end):
                p1, p2 = self.project_arc(p1, r)[1], self.project_arc(p2, r)[1]
                p_cur = interpolate(p1, p2, t, t_start, t_end)
                return p_cur

            t_start = t_end

    def map_circumference(self, r):
        points, arcs = [], []
        for p in self.poly:
            arc, pt = self.project_arc(p, r)
            arcs.append(arc)
            points.append(pt)
        return arcs, points
    
    def do_spiral(self, t1, t2, r1=None, r2=None):
        if r1 is None:
            r1 = self.radius
        if r2 is None:
            r2 = self.min_radius

        if t2 < t1:
            t1, t2 = t2, t1
            r1, r2 = r2, r1

        def r_interpolate(t):
            t = max(t1, min(t2, t)) # Clip to start/end of spiral
            f = (t - t1) / (t2 - t1)
            return r1 + (r2 - r1) * f

        for t_start in range(math.floor(t1), math.ceil(t2)):
            t_end = t_start + 1
            r_outer = r_interpolate(t_start)
            r_inner = r_interpolate(t_end)
            oc_arcs, outer_circumference = self.map_circumference(r_outer)
            ic_arcs, inner_circumference = self.map_circumference(r_inner)

            angle = t_start
            circumference_angles = []
            inner_circumference_sum = sum(math.dist(p1, p2) for p1, p2 in edge_cycle(inner_circumference))
            point_angles = []
            for p1, p2 in edge_cycle(inner_circumference):
                edge_angle = math.dist(p1, p2) / inner_circumference_sum
                point_angles.append(angle)
                angle += edge_angle
            point_angles.append(t_end)

            for (p1, p2), (tp1, tp2) in zip(self.poly_edges, itertools.pairwise(point_angles)):
                rp1 = r_interpolate(tp1)
                rp2 = r_interpolate(tp2)
                _arc, p1_proj = self.project_arc(p1, rp1)
                _arc, p2_proj = self.project_arc(p2, rp2)
                
                if approx_in_range(t1, tp1, tp2):
                    yield interpolate(p1_proj, p2_proj, t1, tp1, tp2), r_inner
                if approx_in_range(t2, tp1, tp2):
                    yield interpolate(p1_proj, p2_proj, t2, tp1, tp2), r_inner
                elif approx_in_range(tp2, t1, t2):
                    yield p2_proj, r_inner