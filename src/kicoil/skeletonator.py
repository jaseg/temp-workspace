import math
import itertools
import subprocess
import os
from tempfile import NamedTemporaryFile
from dataclasses import dataclass
from pathlib import Path
import importlib.resources
import lzma
import sys
import hashlib

import platformdirs
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import wasmtime


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


def polygon_is_clockwise(points):
    (x1, y1, i), *_rest = sorted((x, y, i) for i, (x, y) in enumerate(points))
    x0, y0 = points[(i-1)%len(points)]
    x2, y2 = points[(i+1)%len(points)]
    det = (x0*y1 + x1*y2 + x2*y0) - (x2*y1 + x1*y0 + x0*y2)
    return det < 0


def polygon_center_of_mass(polygon):
    # https://en.wikipedia.org/wiki/Centroid
    total_x, total_y = 0, 0
    area = 0
    for (x1, y1), (x2, y2) in edge_cycle(polygon):
        diff = (x1*y2 - x2*y1)
        total_x += (x1 + x2) * diff
        total_y += (y1 + y2) * diff
        area += diff
    area /= 2
    total_x /= 6*area
    total_y /= 6*area
    return total_x, total_y


class WasmApp:
    def __init__(self, wasm_filename, cachedir="kicoil"):
        module_binary = importlib.resources.read_binary(__package__, wasm_filename)

        module_path_digest = hashlib.sha256(__file__.encode()).hexdigest()
        module_digest = hashlib.sha256(module_binary).hexdigest()
        cache_path = Path(os.getenv("KICOIL_CACHE_DIR", platformdirs.user_cache_dir(cachedir)))
        cache_path.mkdir(parents=True, exist_ok=True)
        cache_filename = (cache_path / f'{wasm_filename}-{module_path_digest[:8]}-{module_digest[:16]}')
        
        self.engine = wasmtime.Engine()

        try:
            with cache_filename.open("rb") as cache_file:
                self.module = wasmtime.Module.deserialize(self.engine, lzma.decompress(cache_file.read()))
        except:
            print("Preparing to run {}. This might take a while...".format(wasm_filename), file=sys.stderr)
            self.module = wasmtime.Module(self.engine, module_binary)
            with cache_filename.open("wb") as cache_file:
                cache_file.write(lzma.compress(self.module.serialize(), preset=0))

    def run(self, stdin='', argv=[]):
        with NamedTemporaryFile('r') as stdout_f, NamedTemporaryFile('w') as stdin_f:
            stdin_f.write(stdin)
            stdin_f.flush()

            wasi_cfg = wasmtime.WasiConfig()
            wasi_cfg.argv = argv
            wasi_cfg.stdin_file = stdin_f.name
            wasi_cfg.stdout_file = stdout_f.name
            wasi_cfg.inherit_stderr()

            linker = wasmtime.Linker(self.engine)
            linker.define_wasi()
            store = wasmtime.Store(self.engine)
            store.set_wasi(wasi_cfg)
            self.app = linker.instantiate(store, self.module)
            linker.define_instance(store, "app", self.app)

            try:
                self.app.exports(store)["_start"](store)
            except wasmtime.ExitTrap as trap:
                if trap.code != 0:
                    raise
            return 0, stdout_f.read()


@dataclass(frozen=True)
class SkeletonNode:
    x: float
    y: float
    time: float

    @property
    def pos(self):
        return self.x, self.y


skeleton_wasm = WasmApp('skeleton.wasm')

def compute_skeleton(exterior):
    points_deduplicated = []
    for p1, p2 in edge_cycle(exterior):
        if p2 != p1:
            points_deduplicated.append(p1)
    input_data = '\n'.join(f'{x} {y}' for x, y in points_deduplicated)
    Path('/tmp/debug.txt').write_text(input_data)
    
    rc, data = skeleton_wasm.run(input_data)

    # Parse output: each line is "x1 y1 x2 y2 t1 t2"
    node_map = {}  # Map (x, y, t) to SkeletonNode
    edges = []

    for line in data.strip().split('\n'):
        if not line:
            continue

        parts = line.split()
        if len(parts) != 6:
            continue

        x1, y1, x2, y2, t1, t2 = map(float, parts)

        n1 = (x1, y1, t1)
        if n1 not in node_map:
            node_map[n1] = SkeletonNode(*n1)
        
        n2 = (x2, y2, t2)
        if n2 not in node_map:
            node_map[n2] = SkeletonNode(*n2)

        edges.append((node_map[n1], node_map[n2]))

    nodes = list(node_map.values())
    return nodes, edges


class Skeletonator:
    def __init__(self, poly):
        self.poly = poly
        self.poly_edges = list(zip(poly, poly[1:] + poly[:1]))
        self.circumference = sum(math.dist(a, b) for a, b in self.poly_edges)
        self.skeleton_nodes, self.skeleton_edges = compute_skeleton(exterior=poly)
        self.arc_map = {}
        self.divergent = set()
        self.radius = max(n.time for n in self.skeleton_nodes)
        self.min_radius = self.radius
        for n1, n2 in self.skeleton_edges:
            if n1 in self.arc_map:
                self.divergent.add(n1)
                self.min_radius = min(n1.time, self.radius)
            self.arc_map[n1] = n2
        coord_map = {}
        for n in self.skeleton_nodes:
            p = (round(n.x, 6), round(n.y, 6))
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
                return (n0, n1), interpolate(n0.pos, n1.pos, t, n0.time, n1.time)
        else:
            raise ValueError(f'{r=:.3f} is out of bounds [0, {self.radius - self.min_radius:.4f}]')

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
        with PdfPages(filename) as pdf:
            fig, ax = plt.subplots(figsize=(10, 10))

            # polygon outline
            poly_x = [p[0] for p in self.poly] + [self.poly[0][0]]
            poly_y = [p[1] for p in self.poly] + [self.poly[0][1]]
            ax.plot(poly_x, poly_y, 'b-', linewidth=2, label='Polygon')
            ax.plot(poly_x, poly_y, 'bo', markersize=4)

            # skeleton edges
            for node1, node2 in self.skeleton_edges:
                ax.plot([node1.x, node2.x], [node1.y, node2.y], 'r-', linewidth=1, alpha=0.7)

            # skeleton nodes
            for n in self.skeleton_nodes:
                if n in self.divergent:
                    ax.plot(n.x, n.y, 'go', markersize=6)
                elif n in self.arc_map:
                    ax.plot(n.x, n.y, 'ro', markersize=3, alpha=0.5)
                else:
                    ax.plot(n.x, n.y, 'o', color='magenta', markersize=6)

            ax.set_aspect('equal', adjustable='box')
            ax.grid(True, alpha=0.3)
            ax.legend()
            ax.set_title(f'Polygon Skeleton (radius: {self.radius:.3f}, min_radius: {self.min_radius:.3f})')
            ax.set_xlabel('X')
            ax.set_ylabel('Y')
            ax.invert_yaxis()
            pdf.savefig(fig, bbox_inches='tight')
            plt.close(fig)