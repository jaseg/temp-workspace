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


def polygon_signed_area(points):
    """ Signed area of a polygon (shoelace formula), positive for counter-clockwise polygons. Repeated points, e.g. a
    closing point equal to the first one, do not change the result. """
    n = len(points)
    if n < 3:
        return 0.0
    x0, y0 = points[0]
    area = 0.0
    for (x1, y1), (x2, y2) in itertools.pairwise(points[1:]):
        # Relative to the first point to limit cancellation for polygons far away from the origin
        area += (x1 - x0)*(y2 - y0) - (x2 - x0)*(y1 - y0)
    return area / 2


def polygon_is_clockwise(points):
    """ Orientation of a simple polygon from its signed area. Unlike a test at a single extreme vertex, this works when
    the polygon repeats a point (e.g. the start point at the end, as SVG paths often do). """
    return polygon_signed_area(points) < 0


def clean_polygon(points):
    """ Return the polygon as a list of float tuples in counter-clockwise order, with consecutive duplicate points
    (including a closing point equal to the first point) removed. Vertex 0 stays vertex 0. Raises ValueError for
    polygons that have fewer than three distinct points, non-finite coordinates or zero area. """
    pts = []
    for p in points:
        x, y = p
        x, y = float(x), float(y)
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError(f'Polygon has a non-finite coordinate ({x}, {y})')
        if not pts or (x, y) != pts[-1]:
            pts.append((x, y))
    while len(pts) > 1 and pts[-1] == pts[0]:
        pts.pop()
    if len(pts) < 3:
        raise ValueError(f'Polygon must have at least 3 distinct points, it has {len(pts)}')
    area = polygon_signed_area(pts)
    if not area or not math.isfinite(area):
        raise ValueError('Polygon has zero area')
    if area < 0:
        pts = pts[:1] + pts[:0:-1]
    return pts


def _remove_collinear(pts, tol):
    """ Drop vertices that lie on the straight line through their neighbors (within tol), and repeated vertices """
    pts = list(pts)
    changed = True
    while changed and len(pts) > 3:
        changed = False
        out = []
        n = len(pts)
        for i in range(n):
            (x0, y0), (x1, y1) = (out[-1] if out else pts[i-1]), pts[i]
            x2, y2 = pts[(i+1) % n]
            l = math.hypot(x2 - x0, y2 - y0)
            if math.hypot(x1 - x0, y1 - y0) <= tol or (
                    l > tol and abs((x2 - x0)*(y1 - y0) - (y2 - y0)*(x1 - x0)) <= tol * l and
                    (x1 - x0)*(x2 - x1) + (y1 - y0)*(y2 - y1) >= 0):
                changed = True
                continue
            out.append(pts[i])
        if len(out) < 3:
            break
        pts = out
    return pts


def _outer_boundary(points, tol):
    """ Boundary of the unbounded face of the arrangement formed by a closed polyline, as a counter-clockwise list of
    points. The polyline may intersect itself, touch itself and contain collinear overlapping pieces; intersections are
    computed with tolerance tol. """
    import numpy as np

    n = len(points)
    segs = [(points[i], points[(i+1) % n]) for i in range(n)]
    segs = [(a, b) for a, b in segs if math.dist(a, b) > tol]
    m = len(segs)
    A = np.array([a for a, _b in segs])
    B = np.array([b for _a, b in segs])
    lo, hi = np.minimum(A, B) - tol, np.maximum(A, B) + tol

    # Parameters at which each segment is cut: its ends, intersections with other segments, and the points where
    # collinear segments start to overlap
    cuts = [[0.0, 1.0] for _ in range(m)]
    def add_cut(i, t):
        cuts[i].append(min(1.0, max(0.0, t)))

    chunk = max(1, 2_000_000 // max(m, 1))
    for i0 in range(0, m, chunk):
        i1 = min(m, i0 + chunk)
        overlap = ((lo[i0:i1, None, 0] <= hi[None, :, 0]) & (lo[None, :, 0] <= hi[i0:i1, None, 0]) &
                   (lo[i0:i1, None, 1] <= hi[None, :, 1]) & (lo[None, :, 1] <= hi[i0:i1, None, 1]))
        ii, jj = np.nonzero(overlap)
        ii = ii + i0
        sel = jj > ii
        for i, j in zip(ii[sel].tolist(), jj[sel].tolist()):
            (ax, ay), (bx, by) = segs[i]
            (cx, cy), (dx, dy) = segs[j]
            rx, ry, sx, sy = bx - ax, by - ay, dx - cx, dy - cy
            lr, ls = math.hypot(rx, ry), math.hypot(sx, sy)
            denom = rx*sy - ry*sx
            qx, qy = cx - ax, cy - ay
            if abs(denom) > 1e-12 * lr * ls:
                t = (qx*sy - qy*sx) / denom
                u = (qx*ry - qy*rx) / denom
                if -tol/lr <= t <= 1 + tol/lr and -tol/ls <= u <= 1 + tol/ls:
                    add_cut(i, t)
                    add_cut(j, u)
            elif abs(qx*ry - qy*rx) <= tol * lr:
                # Collinear: cut each segment where the other one's ends lie on it
                for px, py in ((cx, cy), (dx, dy)):
                    t = ((px - ax)*rx + (py - ay)*ry) / lr**2
                    if -tol/lr <= t <= 1 + tol/lr:
                        add_cut(i, t)
                for px, py in ((ax, ay), (bx, by)):
                    u = ((px - cx)*sx + (py - cy)*sy) / ls**2
                    if -tol/ls <= u <= 1 + tol/ls:
                        add_cut(j, u)

    # Nodes: cut points, merged within tol
    node_pos = []
    grid = {}
    def node(x, y):
        key = (math.floor(x / tol), math.floor(y / tol))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for k in grid.get((key[0]+dx, key[1]+dy), ()):
                    if math.hypot(node_pos[k][0] - x, node_pos[k][1] - y) <= tol:
                        return k
        node_pos.append((x, y))
        grid.setdefault(key, []).append(len(node_pos) - 1)
        return len(node_pos) - 1

    adjacency = {}
    for (a, b), ts in zip(segs, cuts):
        ids = []
        for t in sorted(set(ts)):
            k = node(a[0] + t*(b[0] - a[0]), a[1] + t*(b[1] - a[1]))
            if not ids or ids[-1] != k:
                ids.append(k)
        for k1, k2 in itertools.pairwise(ids):
            adjacency.setdefault(k1, set()).add(k2)
            adjacency.setdefault(k2, set()).add(k1)

    # Walk the outer face counter-clockwise, starting at the lowest of the leftmost nodes. At every node, take the
    # rightmost turn (the smallest counter-clockwise angle from the direction we came from), keeping the unbounded face
    # on the right.
    start = min(adjacency, key=lambda k: node_pos[k])
    back = math.pi / 2 # pretend we arrived heading downwards
    cur = start
    out = []
    first_step = None
    for _ in range(4 * sum(len(v) for v in adjacency.values()) + 10):
        x, y = node_pos[cur]
        best, best_angle = None, None
        for k in adjacency[cur]:
            a = math.atan2(node_pos[k][1] - y, node_pos[k][0] - x)
            rel = (a - back) % (2*math.pi)
            if rel <= 1e-12: # back where we came from, only if there is no other way
                rel = 2*math.pi
            if best is None or rel < best_angle:
                best, best_angle = k, rel
        step = (cur, best)
        if step == first_step:
            return out
        if first_step is None:
            first_step = step
        out.append((x, y))
        bx, by = node_pos[best]
        back = math.atan2(y - by, x - bx)
        cur = best
    raise RuntimeError('Could not trace the outer boundary of the offset outline')


def offset_polygon_outward(poly, margin, miter_limit=2.0):
    """ Outward offset of a simple polygon by `margin` with mitered corners. Miters longer than miter_limit * margin are
    cut off (beveled) at that distance from the corner. Returns the outer boundary of the offset region as a
    counter-clockwise list of points; bays of the outline that close up are filled.

    The raw offset curve (offset edges joined by miters at convex corners, and by a detour through the original vertex
    at reflex corners) contains the boundary of the offset region, plus loops wherever the offset is not a simple
    shift of the outline (short edges between reflex corners, bays that close up). Every point of the raw curve lies in
    the offset region, so the boundary of its unbounded face is the outer boundary of the offset region.
    """
    pts = clean_polygon(poly)
    xs, ys = [x for x, _y in pts], [y for _x, y in pts]
    extent = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    tol = 1e-9 * (extent + margin) + 1e-12 * max(abs(c) for c in xs + ys)
    pts = _remove_collinear(pts, tol)
    if margin <= 0:
        raise ValueError('margin must be positive')
    n = len(pts)
    raw = []
    for i in range(n):
        (x0, y0), (x1, y1), (x2, y2) = pts[i-1], pts[i], pts[(i+1) % n]
        l1, l2 = math.hypot(x1 - x0, y1 - y0), math.hypot(x2 - x1, y2 - y1)
        d1x, d1y, d2x, d2y = (x1 - x0)/l1, (y1 - y0)/l1, (x2 - x1)/l2, (y2 - y1)/l2
        n1x, n1y, n2x, n2y = d1y, -d1x, d2y, -d2x # outward normals of the incoming and outgoing edge
        cross = d1x*d2y - d1y*d2x
        dot = d1x*d2x + d1y*d2y
        if cross >= 0:
            # Convex corner (or straight): miter, cut off at miter_limit
            bx, by = n1x + n2x, n1y + n2y
            bl = math.hypot(bx, by)
            if bl > 1e-9 and margin * 2 / bl <= miter_limit * margin * (1 + 1e-9):
                # The miter point is at distance margin / cos(half turn angle) = 2 * margin / bl
                f = 2 * margin / bl**2
                raw.append((x1 + f*bx, y1 + f*by))
            else:
                if bl > 1e-9:
                    bx, by = bx / bl, by / bl
                else: # U-turn
                    bx, by = d1x, d1y
                lim = miter_limit * margin
                nb = n1x*bx + n1y*by # same for n2
                s1 = (lim - margin*nb) / (d1x*bx + d1y*by)
                s2 = (lim - margin*nb) / -(d2x*bx + d2y*by)
                raw.append((x1 + margin*n1x + s1*d1x, y1 + margin*n1y + s1*d1y))
                raw.append((x1 + margin*n2x - s2*d2x, y1 + margin*n2y - s2*d2y))
        else:
            # Reflex corner: the mitered inner corner when both edges are long enough for it, else a detour through the
            # vertex itself (which lies inside the offset region)
            retract = margin * -cross / (1 + dot) # margin * tan(half turn angle)
            if dot > 0 and retract <= min(l1, l2):
                f = margin / (1 + dot)
                raw.append((x1 + f*(n1x + n2x), y1 + f*(n1y + n2y)))
            else:
                raw.append((x1 + margin*n1x, y1 + margin*n1y))
                raw.append((x1, y1))
                raw.append((x1 + margin*n2x, y1 + margin*n2y))
    out = _outer_boundary(raw, tol)
    return _remove_collinear(out, tol)


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
        # Normalize the input: CGAL needs a counter-clockwise polygon without repeated points. Vertex 0 stays vertex 0.
        poly = clean_polygon(poly)
        self.poly = poly
        self.poly_edges = list(zip(poly, poly[1:] + poly[:1]))
        self.circumference = sum(math.dist(a, b) for a, b in self.poly_edges)
        self.skeleton_nodes, self.skeleton_edges = compute_skeleton(exterior=poly)
        self.debug_arms = []

        # Tolerances. They scale with the polygon's extent (bounding box diagonal), not with its distance from the
        # origin. skeleton.wasm prints 12 significant digits, so coordinates of nodes that coincide exactly can differ by
        # about 1e-12 times their magnitude; the floor (100x that) covers polygons far away from the origin.
        xs, ys = [x for x, _y in poly], [y for _x, y in poly]
        extent = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
        magnitude = max(abs(c) for c in xs + ys)
        float_floor = 1e-10 * magnitude
        merge_tol = 3e-7 * extent + float_floor # nodes closer than this (in x, y and time) are one node
        teps = 1e-9 * extent + float_floor # time tolerance for constant-time skeleton edges
        self.merge_tol, self.teps = merge_tol, teps

        # Merge skeleton nodes that coincide (CGAL emits clusters of nodes connected by zero-length edges at degenerate
        # events, e.g. at the center of regular polygons).
        canon = {}
        buckets = {}
        for n in sorted(self.skeleton_nodes, key=lambda n: n.time):
            key = (math.floor(n.x / merge_tol), math.floor(n.y / merge_tol))
            match = None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for m in buckets.get((key[0]+dx, key[1]+dy), ()):
                        if abs(m.x - n.x) <= merge_tol and abs(m.y - n.y) <= merge_tol and abs(m.time - n.time) <= merge_tol:
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

        # Match the polygon vertices to the skeleton's contour nodes (time 0). The coordinates CGAL prints are rounded
        # to 12 significant digits, so they are matched to the nearest contour node instead of by value.
        contour = sorted({canon[n] for n in self.skeleton_nodes if n.time <= teps}, key=lambda n: (n.x, n.y))
        contour_x = [n.x for n in contour]
        match_tol = 1e-6 * extent + float_floor
        self.node_map = {}
        self.tracks = []
        for x, y in poly:
            lo = bisect.bisect_left(contour_x, x - match_tol)
            hi = bisect.bisect_right(contour_x, x + match_tol)
            start = min(contour[lo:hi], key=lambda n: math.hypot(n.x - x, n.y - y), default=None)
            if start is None or math.hypot(start.x - x, start.y - y) > match_tol:
                raise RuntimeError(f'Straight skeleton has no node at polygon vertex ({x}, {y})')
            self.node_map[(x, y)] = start
            track = [start]
            while track[-1] in self.arc_map and track[-1] not in self.divergent:
                exit_node = self._arc_exit[track[-1]]
                if exit_node is not track[-1]:
                    track.append(exit_node) # move along the constant-time group to where the way up leaves
                track.append(self.arc_map[track[-1]])
            self.tracks.append(track)
        if self.max_depth <= 0 or any(len(track) < 2 or track[-1].time <= 0 for track in self.tracks):
            raise ValueError('Degenerate straight skeleton: the polygon is too small, or too far away from the origin '
                             'for its size, to be represented with floating point precision.')
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
        """ Position of polygon vertex i on the offset outline at the given depth. Depths beyond the end of the track are
        clamped to the track's end.

        Negative depths are extrapolated linearly along the vertex's first skeleton arc. This is only a local
        extrapolation, valid for small outward distances (e.g. the outer via ring): it is the vertex of a mitered
        outward offset only until the first event of the *exterior* skeleton. Further out, short edges between reflex
        vertices invert and convex tips give unbounded miters. Use `offset_polygon_outward` for a real outward offset.
        """
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
        if not (math.isfinite(t1) and math.isfinite(t2)):
            raise ValueError(f'Spiral angles must be finite, got {t1} and {t2}')
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
        """ Return the points and angles of a spiral arm from angle t1 at depth d1 to angle t2 at depth d2. The depth
        changes linearly with the angle. The points are in order from t1 to t2, also when t2 < t1. """
        if not all(math.isfinite(v) for v in (t1, t2, d1, d2)):
            raise ValueError(f'Spiral parameters must be finite, got angles {t1}, {t2} and depths {d1}, {d2}')
        if t2 < t1:
            points, angles = self.spiral(t2, t1, d2, d1)
            return points[::-1], angles[::-1]
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