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
import bisect

import platformdirs
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
                    raise RuntimeError('Error computing straight skeleton.')
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
    input_data = '\n'.join(f'{float(x)!r} {float(y)!r}' for x, y in points_deduplicated)

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
    """ Maps a polygon's straight skeleton to a coordinate system for spiral layout.

    Coordinates are an "angle" t (one revolution per unit, polygon vertex 0 at t=0) and a "radius" r, which is
    `self.radius - depth`, where depth is the inward offset distance from the polygon outline. A point (t, r) lies on
    the polygon's inward offset at that depth (i.e. on the straight skeleton wavefront at time=depth).

    Every polygon vertex moves along a chain of skeleton arcs ("track") as the outline is offset inwards. The offset
    outline at a given depth is the polygon formed by the positions of all vertices on their tracks at that depth. This
    works up to the first split event, where the offset outline falls apart into multiple pieces; `self.min_radius`
    holds that depth limit (the name is historical, it is a depth, not a radius).

    The angle coordinate is fixed for the whole shape: vertex i always sits at angle `self.vertex_angles[i]`, no matter
    the depth. This makes consecutive turns of a spiral, and the arms of a multi-arm spiral, line up with each other
    exactly at every vertex.
    """

    TIME_EPS = 1e-9

    def __init__(self, poly, ref_depth=None):
        self.poly = poly
        self.poly_edges = list(zip(poly, poly[1:] + poly[:1]))
        self.circumference = sum(math.dist(a, b) for a, b in self.poly_edges)
        self.skeleton_nodes, self.skeleton_edges = compute_skeleton(exterior=poly)
        self.debug_arms = []

        # Merge skeleton nodes that coincide (CGAL emits clusters of nodes connected by zero-length edges at degenerate
        # events, e.g. at the center of regular polygons).
        scale = max(1.0, max(abs(c) for p in poly for c in p))
        eps = 1e-9 * scale
        canon = {}
        buckets = {}
        for n in sorted(self.skeleton_nodes, key=lambda n: n.time):
            key = (round(n.x / eps / 1e3), round(n.y / eps / 1e3))
            match = None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for m in buckets.get((key[0]+dx, key[1]+dy), ()):
                        if abs(m.x - n.x) <= 1e3*eps and abs(m.y - n.y) <= 1e3*eps and abs(m.time - n.time) <= 1e3*eps:
                            match = m
            if match is None:
                buckets.setdefault(key, []).append(n)
                canon[n] = n
            else:
                canon[n] = match

        adjacency = {}
        for n1, n2 in self.skeleton_edges:
            c1, c2 = canon[n1], canon[n2]
            if c1 is c2:
                continue
            adjacency.setdefault(c1, set()).add(c2)
            adjacency.setdefault(c2, set()).add(c1)

        # Vertex tracks follow the skeleton towards strictly increasing time. Nodes joined by constant-time edges (e.g.
        # where two parallel edges of the outline meet) form a single event. An event with more than one way up is a
        # split (or vertex) event, beyond which the offset outline is no longer a single polygon: a reflex vertex
        # hitting an edge, or a neck between two reflex corners pinching off.
        teps = 1e-9 * scale
        self.radius = max(n.time for n in self.skeleton_nodes)
        self.divergent = set()
        self.arc_map = {}
        self._arc_exit = {} # node -> node of its constant-time group from which the way up leaves
        split_time = self.radius
        seen = set()
        for n0 in adjacency:
            if n0 in seen:
                continue
            group, todo = [], [n0]
            seen.add(n0)
            while todo:
                n = todo.pop()
                group.append(n)
                for m in adjacency[n]:
                    if m not in seen and abs(m.time - n.time) <= teps:
                        seen.add(m)
                        todo.append(m)
            members = set(group)
            ups = {}
            for n in group:
                for m in adjacency[n]:
                    if m not in members and m.time > n.time + teps:
                        ups.setdefault(m, n)
            if len(ups) > 1:
                self.divergent.update(group)
                split_time = min(split_time, min(n.time for n in group))
            elif len(ups) == 1:
                (up, exit_node), = ups.items()
                for n in group:
                    self.arc_map[n] = up
                    self._arc_exit[n] = exit_node
        self.min_radius = split_time
        self.max_depth = split_time

        contour_nodes = {}
        for n in self.skeleton_nodes:
            if n.time <= self.TIME_EPS:
                contour_nodes[(round(n.x, 6), round(n.y, 6))] = canon[n]
        self.node_map = {}
        self.tracks = []
        for x, y in poly:
            start = contour_nodes[(round(x, 6), round(y, 6))]
            self.node_map[(x, y)] = start
            track = [start]
            while track[-1] in self.arc_map and track[-1] not in self.divergent:
                exit_node = self._arc_exit[track[-1]]
                if exit_node is not track[-1]:
                    track.append(exit_node) # move along the constant-time group to where the way up leaves
                track.append(self.arc_map[track[-1]])
            self.tracks.append(track)
        self._track_times = [[n.time for n in track] for track in self.tracks]

        self.set_angle_reference(ref_depth)

    def set_angle_reference(self, max_depth=None):
        """ Fix the angle coordinate of every vertex.

        Each edge gets an angle span proportional to its *shortest* length over the depth range [0, max_depth] that the
        spiral uses. The depth difference a spiral arm covers along an edge is proportional to the edge's angle span, so
        this choice bounds the slope of the spiral relative to the edge (and thus the loss of clearance between turns
        caused by that slope) at every depth, including edges that shrink (convex corners) or grow (reflex corners).
        """
        if max_depth is None:
            max_depth = self.max_depth
        max_depth = max(0, min(max_depth, self.max_depth))
        depths = {0.0, max_depth}
        for times in self._track_times:
            depths.update(t for t in times if 0 < t < max_depth)
        depths = sorted(depths)
        n = len(self.poly)
        min_len = [math.inf] * n
        for d in depths:
            pts = [self.track_position(i, d) for i in range(n)]
            for i in range(n):
                min_len[i] = min(min_len[i], math.dist(pts[i], pts[(i+1) % n]))
        # Edges that (nearly) collapse within the depth range get a span of exactly zero, so that all vertices of a
        # collapsing group share exactly the same angle. Tiny non-zero spans would break the tie resolution in _locate.
        min_len = [l if l > 1e-9 * self.circumference else 0.0 for l in min_len]
        total = sum(min_len)
        if total <= 1e-9 * self.circumference:
            # Everything collapses at max_depth: fall back to outline edge lengths
            min_len = [math.dist(a, b) for a, b in self.poly_edges]
            total = sum(min_len)
        self.ref_depth = max_depth
        self.vertex_angles = [0.0]
        for l in min_len[:-1]:
            self.vertex_angles.append(self.vertex_angles[-1] + l / total)
        # Quantize the angles to a binary grid, so that `revolution + angle` is computed exactly and angle comparisons
        # (in particular ties between vertices of a collapsing group) are exact. Vertices at the end that share their
        # angle with vertex 0 (a run of collapsing edges across vertex 0) get an angle of exactly 1.
        self.vertex_angles = [round(a * self.ANGLE_GRID) / self.ANGLE_GRID for a in self.vertex_angles]
        self.vertex_angles = [1.0 if 1.0 - a < 1e-12 else a for a in self.vertex_angles]
        self.edge_spans = [b - a for a, b in itertools.pairwise(self.vertex_angles + [1.0])]

    def track_position(self, i, depth):
        """ Position of polygon vertex i on the offset outline at the given depth. Negative depths are extrapolated
        linearly along the first arc (this yields a mitered outward offset). Depths beyond the end of the track are
        clamped to the track's end. """
        track = self.tracks[i]
        times = self._track_times[i]
        if len(track) == 1:
            return track[0].pos
        if depth <= times[0]:
            j = 0
        elif depth >= times[-1]:
            # Beyond the end of the track the outline has collapsed, there is nothing to extrapolate.
            return track[-1].pos
        else:
            j = max(0, min(len(track) - 2, bisect.bisect_right(times, depth) - 1))
        n0, n1 = track[j], track[j+1]
        if n1.time - n0.time <= self.TIME_EPS:
            return n1.pos if depth >= n1.time else n0.pos
        return interpolate(n0.pos, n1.pos, depth, n0.time, n1.time)

    def iter_arcs(self, p):
        track = self.tracks[self.poly.index(p)]
        yield from itertools.pairwise(track)

    def project_arc(self, p, r):
        i = self.poly.index(p)
        depth = self.radius - r
        if depth > self.max_depth + 1e-9:
            raise ValueError(f'{r=:.3f} is out of bounds [{self.radius - self.max_depth:.4f}, {self.radius:.4f}]')
        track = self.tracks[i]
        arc = (track[0], track[min(1, len(track)-1)])
        return arc, self.track_position(i, depth)

    def calc_circumference(self, r):
        projected = self.map_circumference(r)[1]
        return sum(math.dist(p1, p2) for p1, p2 in edge_cycle(projected))

    def map_circumference(self, r):
        depth = self.radius - r
        points = [self.track_position(i, depth) for i in range(len(self.poly))]
        arcs = [(t[0], t[min(1, len(t)-1)]) for t in self.tracks]
        return arcs, points

    ANGLE_EPS = 1e-9
    ANGLE_GRID = 2**40 # vertex angles are multiples of 1/ANGLE_GRID, exact in sums with integers below 2**12

    def snap_angle(self, t):
        """ Snap an angle to the nearest vertex angle if it is within ANGLE_EPS of it. Angles of arm ends are computed
        with floating point arithmetic, and several vertices can share the same angle (when edges collapse before the
        spiral's reference depth). Snapping makes the comparisons with vertex angles exact. """
        k = math.floor(t)
        frac = t - k
        i = bisect.bisect_left(self.vertex_angles, frac)
        for j in (i-1, i):
            if 0 <= j < len(self.vertex_angles) and abs(self.vertex_angles[j] - frac) < self.ANGLE_EPS:
                return k + self.vertex_angles[j]
        if 1.0 - frac < self.ANGLE_EPS:
            return k + 1.0
        return t

    def _locate(self, t):
        """ For angle t, return (k, i, f): t lies in revolution k on the edge from vertex i to vertex i+1 at fraction f.

        When several vertices share angle t, this returns the *first* of them (as the end of the edge leading to it,
        f=1). Spiral arms start and end there and include the other vertices of the group in their first turn. """
        k = math.floor(t)
        frac = t - k
        if frac <= 0:
            k, frac = k-1, 1.0
        i = bisect.bisect_left(self.vertex_angles, frac) # first vertex with angle >= frac, n if there is none
        i -= 1 # the edge leading there
        span = self.edge_spans[i]
        f = 1.0 if span <= 0 else (frac - self.vertex_angles[i]) / span
        return k, i, max(0.0, min(1.0, f))

    def _vertex_angle(self, k, i):
        if i >= len(self.poly):
            return k + 1 + self.vertex_angles[i - len(self.poly)]
        return k + self.vertex_angles[i]

    def _point_on_spiral(self, t, depth_fn):
        """ Point at angle t on the polyline through all vertices v at depth depth_fn(angle of v) """
        k, i, f = self._locate(t)
        n = len(self.poly)
        a0, a1 = self._vertex_angle(k, i), self._vertex_angle(k, i+1)
        p0 = self.track_position(i, depth_fn(a0))
        p1 = self.track_position((i+1) % n, depth_fn(a1))
        return interpolate(p0, p1, f)

    def project_point(self, t, r=None, r_ref=None):
        """ Point at angle t on the offset outline at radius r. r_ref is accepted for API compatibility and ignored, the
        angle mapping is fixed. """
        if r is None:
            r = self.radius
        depth = self.radius - r
        return self._point_on_spiral(self.snap_angle(t), lambda a: depth)

    def iter_vertex_angles(self, t1, t2):
        """ Yield (angle, vertex index) for all vertices with t1 <= angle < t2, in order """
        n = len(self.poly)
        k = math.floor(t1) - 1
        while True:
            for i in range(n):
                a = k + self.vertex_angles[i]
                if a >= t2:
                    return
                if a >= t1:
                    yield a, i
            k += 1

    def spiral(self, t1, t2, d1, d2):
        """ Return the points and angles of a spiral arm from angle t1 at depth d1 to angle t2 at depth d2 (t1 < t2).
        The depth changes linearly with the angle. """
        t1, t2 = self.snap_angle(t1), self.snap_angle(t2)
        if math.isclose(t1, t2):
            depth_fn = lambda t: d1
        else:
            depth_fn = lambda t: d1 + (d2 - d1) * (t - t1) / (t2 - t1)

        # The end points are placed on the offset outline at constant depth, so that they do not depend on the
        # direction of the spiral. This way, the end points of inward and outward spirals meet exactly.
        points = [self._point_on_spiral(t1, lambda a: d1)]
        angles = [t1]
        for a, i in self.iter_vertex_angles(t1, t2):
            p = self.track_position(i, d1 if a == t1 else depth_fn(a))
            if math.dist(p, points[-1]) > 1e-12:
                points.append(p)
                angles.append(a)
        p = self._point_on_spiral(t2, lambda a: d2)
        if math.dist(p, points[-1]) > 1e-12 or len(points) == 1:
            points.append(p)
            angles.append(t2)
        else:
            points[-1], angles[-1] = p, t2
        return points, angles

    def do_spiral(self, t1, t2, r1=None, r2=None, debug=False):
        """ Yield the points of a spiral arm from angle t1 at radius r1 to angle t2 at radius r2. The radius changes
        linearly with the angle. Points are yielded in order of increasing angle as (point, r_ref) tuples; r_ref is
        kept for API compatibility. """
        if r1 is None:
            r1 = self.radius
        if r2 is None:
            r2 = self.radius - self.max_depth

        direction = True
        if t2 < t1:
            direction = False
            t1, t2 = t2, t1
            r1, r2 = r2, r1

        r_ref = min(r1, r2)
        arm, _angles = self.spiral(t1, t2, self.radius - r1, self.radius - r2)
        if debug:
            self.debug_arms.append((arm, direction, t1, t2))
        for p in arm:
            yield p, r_ref

    def dump_to_pdf(self, filename):
        import matplotlib.pyplot as plt
    
        fig, ax = plt.subplots(figsize=(10, 10))

        # polygon outline
        poly_x = [p[0] for p in self.poly] + [self.poly[0][0]]
        poly_y = [p[1] for p in self.poly] + [self.poly[0][1]]
        ax.plot(poly_x, poly_y, '-', color='black', linewidth=.5, label='Polygon')

        # skeleton edges
        for node1, node2 in self.skeleton_edges:
            ax.plot([node1.x, node2.x], [node1.y, node2.y], '-', color='gray', linewidth=.5, alpha=0.7)

        # skeleton nodes
        for n in self.skeleton_nodes:
            if n in self.divergent:
                ax.plot(n.x, n.y, 'o', markerfacecolor='none', markeredgecolor='green', markersize=4)
            elif n in self.arc_map:
                ax.plot(n.x, n.y, 'o', color='black', markersize=3, alpha=0.5)
            else:
                ax.plot(n.x, n.y, 'o', markerfacecolor='none', markeredgecolor='magenta', markersize=4)

        count = {True: 0, False: 0}
        for arm, direction, t1, t2 in self.debug_arms:
            xs = [x for x, y in arm]
            ys = [y for x, y in arm]
            ax.plot(xs, ys, linewidth=.2, color='red' if direction else 'blue')
            align = 'left' if direction else 'right'
            ax.text(xs[-1], ys[-1], f'{count[direction]}', size=3, horizontalalignment=align)
            ax.text(xs[0], ys[0], f'{count[direction]}', size=3, horizontalalignment=align, color='gray')
            count[direction] += 1

        xs, ys = [], []
        for i in range(100):
            r = self.radius - (i/99) * self.min_radius
            arc, (px, py) = self.project_arc(self.poly[0], r)
            xs.append(px)
            ys.append(py)
        ax.plot(xs, ys, '--', linewidth=.5, color='black')

        ax.set_aspect('equal', adjustable='box')
        ax.grid(True, alpha=0.3)
        ax.legend()
        ax.set_title(f'Polygon Skeleton (radius: {self.radius:.3f}, min_radius: {self.min_radius:.3f})')
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.invert_yaxis()
        fig.savefig(filename, bbox_inches='tight', dpi=600)
        plt.close(fig)