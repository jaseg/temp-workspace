import math
import itertools
import subprocess
import os
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


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


class SkeletonNode:
    """Wrapper class for skeleton nodes to match py_straight_skeleton interface"""
    def __init__(self, x, y, time):
        self.position = type('Position', (), {'x': x, 'y': y})()
        self.time = time
        self.x = x
        self.y = y

    def __hash__(self):
        return hash((self.x, self.y, self.time))

    def __eq__(self, other):
        return (self.x, self.y, self.time) == (other.x, other.y, other.time)

    def __repr__(self):
        return f'SkeletonNode({self.x}, {self.y}, t={self.time})'


class SkeletonWrapper:
    """Wrapper class for skeleton to match py_straight_skeleton interface"""
    def __init__(self, nodes, edges):
        self.nodes = nodes
        self.edges = edges

    def arc_iterator(self):
        """Iterate through skeleton edges as node pairs"""
        return iter(self.edges)


def compute_skeleton_cli(exterior, holes=None):
    """
    Compute straight skeleton using the CLI program instead of py_straight_skeleton.

    Args:
        exterior: List of (x, y) tuples representing the polygon vertices
        holes: Not supported in this implementation

    Returns:
        SkeletonWrapper object compatible with py_straight_skeleton interface
    """
    if holes:
        raise NotImplementedError("Holes are not supported in CLI implementation")

    # Find the skeleton_cli binary
    # Look in project root directory
    cli_path = Path(__file__).parent.parent.parent / 'skeleton_cli'
    if not cli_path.exists():
        raise FileNotFoundError(f"skeleton_cli binary not found at {cli_path}")

    # Prepare input: one point per line
    points_deduplicated = []
    for p1, p2 in edge_cycle(exterior):
        if p2 != p1:
            points_deduplicated.append(p1)
    input_data = '\n'.join(f'{x} {y}' for x, y in points_deduplicated)
    Path('/tmp/debug.txt').write_text(input_data)

    # Run the CLI program
    try:
        result = subprocess.run(
            [str(cli_path)],
            input=input_data,
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise ValueError(f'Error computing polygon straight skeleton. CGAL says: {e.stdout.rstrip()}\n{e.stderr.rstrip()}')

    # Parse output: each line is "x1 y1 x2 y2 t1 t2"
    node_dict = {}  # Map (x, y, t) to SkeletonNode
    edges = []

    for line in result.stdout.strip().split('\n'):
        if not line:
            continue

        parts = line.split()
        if len(parts) != 6:
            continue

        x1, y1, x2, y2, t1, t2 = map(float, parts)

        # Create or get nodes
        key1 = (x1, y1, t1)
        key2 = (x2, y2, t2)

        if key1 not in node_dict:
            node_dict[key1] = SkeletonNode(x1, y1, t1)
        if key2 not in node_dict:
            node_dict[key2] = SkeletonNode(x2, y2, t2)

        node1 = node_dict[key1]
        node2 = node_dict[key2]

        edges.append((node1, node2))

    nodes = list(node_dict.values())
    return SkeletonWrapper(nodes, edges)


class Skeletonator:
    def __init__(self, poly):
        self.poly = poly
        self.poly_edges = list(zip(poly, poly[1:] + poly[:1]))
        self.circumference = sum(math.dist(a, b) for a, b in self.poly_edges)
        self.skeleton = compute_skeleton_cli(exterior=poly, holes=[])
        self.arc_map = {}
        self.divergent = set()
        self.radius = max(n.time for n in self.skeleton.nodes)
        self.min_radius = self.radius
        for n1, n2 in self.skeleton.arc_iterator():
            if n1 in self.arc_map:
                self.divergent.add(n1)
                self.min_radius = min(n1.time, self.radius)
            self.arc_map[n1] = n2
        coord_map = {}
        for n in self.skeleton.nodes:
            p = (round(n.position.x, 6), round(n.position.y, 6))
            coord_map[p] = n
        self.node_map = {}
        for x, y in poly:
            p = (round(x, 6), round(y, 6))
            self.node_map[(x, y)] = coord_map[p]
        self.dump_to_pdf('/tmp/test.pdf')

    def iter_arcs(self, p):
        i = 0
        start = self.node_map[p]
        #print('start', start, start in self.arc_map, start in self.divergent)
        while start in self.arc_map and not start in self.divergent:
            end = self.arc_map[start]
            #print('end', i, end)
            i += 1
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
            raise ValueError(f'{r=:.3f} is out of bounds [0, {self.min_radius:.4f}]')

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
            r_ref = min(r_inner, r_outer) # Handle outward spirals where the radii are swapped
            _ic_arcs, inner_circumference = self.map_circumference(r_ref)

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
                    _arc, p2_proj_r1 = self.project_arc(p2, r1)
                    yield interpolate(p1_proj, p2_proj_r1, t1, tp1, tp2), r_ref
                if approx_in_range(t2, tp1, tp2):
                    _arc, p1_proj_r2 = self.project_arc(p1, r2)
                    yield interpolate(p1_proj_r2, p2_proj, t2, tp1, tp2), r_ref
                elif approx_in_range(tp2, t1, t2):
                    yield p2_proj, r_ref

    def dump_to_pdf(self, filename):
        """
        Dump the polygon and its computed skeleton to a PDF file using matplotlib.
        """
        with PdfPages(filename) as pdf:
            fig, ax = plt.subplots(figsize=(10, 10))

            # Plot the polygon
            poly_x = [p[0] for p in self.poly] + [self.poly[0][0]]
            poly_y = [p[1] for p in self.poly] + [self.poly[0][1]]
            ax.plot(poly_x, poly_y, 'b-', linewidth=2, label='Polygon')
            ax.plot(poly_x, poly_y, 'bo', markersize=4)

            # Plot the skeleton edges
            for node1, node2 in self.skeleton.arc_iterator():
                ax.plot([node1.x, node2.x], [node1.y, node2.y], 'r-', linewidth=1, alpha=0.7)

            # Plot skeleton nodes
            for node in self.skeleton.nodes:
                ax.plot(node.x, node.y, 'ro', markersize=3, alpha=0.5)

            # Plot divergent nodes with a different marker
            for node in self.divergent:
                ax.plot(node.x, node.y, 'go', markersize=6, label='Divergent' if node == list(self.divergent)[0] else '')

            for node in self.skeleton.nodes:
                if node not in self.arc_map and node not in self.divergent:
                    ax.plot(node.x, node.y, 'o', color='magenta', markersize=6, label='Divergent' if self.divergent and node == list(self.divergent)[0] else '')

            ax.set_aspect('equal', adjustable='box')
            ax.grid(True, alpha=0.3)
            ax.legend()
            ax.set_title(f'Polygon Skeleton (radius: {self.radius:.3f}, min_radius: {self.min_radius:.3f})')
            ax.set_xlabel('X')
            ax.set_ylabel('Y')

            pdf.savefig(fig, bbox_inches='tight')
            plt.close(fig)