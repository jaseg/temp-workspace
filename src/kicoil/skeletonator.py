import math
import itertools

from py_straight_skeleton import compute_skeleton


def interpolate(p1, p2, t, t_start, t_end):
    t_range = t_end - t_start
    t = (t - t_start) / t_range
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    return (x1 + t*dx, y1 + t*dy)

def approx_in_range(value, lower, upper):
    if math.isclose(value, lower) or math.isclose(value, upper):
        return True
    return lower <= value <= upper

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
        if r < self.radius - self.min_radius:
            raise ValueError(f'r (={r:.2f}) must be greater than {self.radius - self.min_radius:.2f}')
        t = self.radius - r

        for n0, n1 in self.iter_arcs(p):
            # project first arc outwards in case r < 0
            if t < 0 or approx_in_range(t, n0.time, n1.time):
                p0 = (n0.position.x, n0.position.y)
                p1 = (n1.position.x, n1.position.y)
                return interpolate(p0, p1, t, n0.time, n1.time)

    def project_point(self, t, r=None):
        t %= 1
        if r is None:
            r = self.radius
        
        t_start = 0
        p_cur = None
        for p1, p2 in self.poly_edges:
            edge_frac = math.dist(p1, p2) / self.circumference
            t_end = t_start + edge_frac
    
            if approx_in_range(t, t_start, t_end):
                p1, p2 = self.project_arc(p1, r), self.project_arc(p2, r)
                p_cur = interpolate(p1, p2, t, t_start, t_end)
                return p_cur

            t_start = t_end

    def do_spiral(self, t1, t2, r1=None, r2=None):
        if r1 is None:
            r1 = self.radius
        if r2 is None:
            r2 = self.radius - self.min_radius
        
        if t2 < t1:
            t1, t2 = t2, t1
            r1, r2 = r2, r1

        r_interpolate = lambda t: r1 + (r2 - r1) * ((t - t1) / (t2 - t1))
            
        yield self.project_point(t1, r1)

        edge_iter = itertools.cycle(self.poly_edges)
        
        t_start = 0
        t = t1
        for p1, p2 in edge_iter:
            edge_frac = math.dist(p1, p2) / self.circumference
            t_end = t_start + edge_frac
    
            if approx_in_range(t1, t_start, t_end):
                if t2 > t_end:
                    yield self.project_arc(p2, r_interpolate(t_end))
                t_start = t_end
                break

            t_start = t_end

        for p1, p2 in edge_iter:
            edge_frac = math.dist(p1, p2) / self.circumference
            t_end = t_start + edge_frac
            
            if t2 > t_end:
                yield self.project_arc(p2, r_interpolate(t_end))
            else:
                break

            t_start = t_end

        yield self.project_point(t2, r2)
