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
import logging

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


def reflex_vertices(points):
    """ Indices of the reflex (concave) vertices of a counter-clockwise polygon """
    n = len(points)
    out = []
    for i in range(n):
        (x0, y0), (x1, y1), (x2, y2) = points[i-1], points[i], points[(i+1) % n]
        if (x1 - x0)*(y2 - y1) - (y1 - y0)*(x2 - x1) < 0:
            out.append(i)
    return out


def _point_segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx*dx + dy*dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0])*dx + (p[1] - a[1])*dy) / l2))
    return math.hypot(p[0] - a[0] - t*dx, p[1] - a[1] - t*dy)


def remove_reflex_jitter(points, tol, keep=()):
    """ Remove reflex vertices of a counter-clockwise polygon that lie within tol of the chord between their
    neighbors, e.g. the tiny concave corners that rounding the coordinates of a densely sampled smooth outline
    produces. A vertex is only removed while it is reflex, and only if all input vertices between its two neighbors
    (itself and those removed before) are within tol of the chord that replaces them. Removing a reflex vertex adds
    the triangle between it and the chord to the polygon, so the result contains the input and lies within tol of it.
    Its neighbors become less convex: those that become reflex may be removed in turn, so the result also lacks some
    vertices that were convex in the input (nearly collinear ones next to removed reflex corners). Vertex 0 is always
    kept, and so are the vertices whose indices are in `keep`. Vertices are removed in order of increasing deviation. """
    import heapq

    keep = set(keep) | {0}

    n = len(points)
    prev = [(i - 1) % n for i in range(n)]
    nxt = [(i + 1) % n for i in range(n)]
    alive = [True] * n

    def is_reflex(i):
        (x0, y0), (x1, y1), (x2, y2) = points[prev[i]], points[i], points[nxt[i]]
        return (x1 - x0)*(y2 - y1) - (y1 - y0)*(x2 - x1) < 0

    def deviation(i):
        """ Largest distance of the original vertices between prev[i] and nxt[i] from the chord between them """
        a, b = points[prev[i]], points[nxt[i]]
        d, k = 0.0, (prev[i] + 1) % n
        while k != nxt[i]:
            d = max(d, _point_segment_distance(points[k], a, b))
            if d > tol:
                break
            k = (k + 1) % n
        return d

    heap = [(deviation(i), i) for i in range(1, n) if i not in keep and is_reflex(i)]
    heap = [h for h in heap if h[0] <= tol]
    heapq.heapify(heap)
    count = n
    while heap and count > 3:
        d, i = heapq.heappop(heap)
        if not alive[i] or not is_reflex(i):
            continue
        current = deviation(i)
        if current != d:
            # A neighbor was removed since: requeue with the new deviation
            if current <= tol:
                heapq.heappush(heap, (current, i))
            continue
        alive[i] = False
        count -= 1
        p, q = prev[i], nxt[i]
        nxt[p], prev[q] = q, p
        for k in (p, q):
            if k not in keep and is_reflex(k):
                dk = deviation(k)
                if dk <= tol:
                    heapq.heappush(heap, (dk, k))
    return [points[i] for i in range(n) if alive[i]]


def _reflex_turn(p0, v, p1):
    """ How far a counter-clockwise outline turns right (radians, > 0 for a reflex corner) at vertex v """
    ux, uy = v[0] - p0[0], v[1] - p0[1]
    wx, wy = p1[0] - v[0], p1[1] - v[1]
    return -math.atan2(ux*wy - uy*wx, ux*wx + uy*wy)


def _circle_crossing(a, b, v, r, last):
    """ Parameter t in [0, 1] where segment a-b crosses the circle of radius r around v (the first crossing, or the
    last one if `last`) """
    dx, dy = b[0] - a[0], b[1] - a[1]
    fx, fy = a[0] - v[0], a[1] - v[1]
    qa, qb, qc = dx*dx + dy*dy, 2 * (fx*dx + fy*dy), fx*fx + fy*fy - r*r
    root = math.sqrt(max(0.0, qb*qb - 4*qa*qc))
    t = (-qb + root) / (2*qa) if last else (-qb - root) / (2*qa)
    return max(0.0, min(1.0, t))


def _cusp_cut(points, i, r):
    """ The part of a counter-clockwise polygon's outline within distance r of vertex i: (j0, j1, e_in, e_out) with
    vertices j0 .. j1 (cyclic, around i) inside the circle and e_in, e_out the points where the outline enters and
    leaves it (on the edges j0-1 -> j0 and j1 -> j1+1). None if (nearly) the whole outline is inside. """
    n = len(points)
    v = points[i]
    j0, j1, inside = i, i, 1
    while math.dist(points[(j0 - 1) % n], v) < r:
        j0, inside = (j0 - 1) % n, inside + 1
        if inside > n - 3:
            return None
    while math.dist(points[(j1 + 1) % n], v) < r:
        j1, inside = (j1 + 1) % n, inside + 1
        if inside > n - 3:
            return None
    a, b = points[(j0 - 1) % n], points[j0]
    t = _circle_crossing(a, b, v, r, last=False) # (a is outside, b inside: one crossing)
    e_in = (a[0] + t*(b[0] - a[0]), a[1] + t*(b[1] - a[1]))
    c, d = points[j1], points[(j1 + 1) % n]
    t = _circle_crossing(c, d, v, r, last=True)
    e_out = (c[0] + t*(d[0] - c[0]), c[1] + t*(d[1] - c[1]))
    return j0, j1, e_in, e_out


def _cusp_clearance(points, i, j0, j1, r):
    """ Whether the outline outside the cut of vertex i (vertices j0 .. j1, see _cusp_cut) keeps clear of the circle
    of radius r around it: the edges that continue the outline from the circle may not re-enter it, all other edges
    must stay 2 r away. Returns the radius to try instead, or None if r is fine. """
    n = len(points)
    v = points[i]
    near = set() # edges (k -> k+1) continuing the outline outwards from the circle, up to 3 r
    for step, start in ((1, j1), (-1, (j0 - 1) % n)):
        k, d = start, math.dist(points[(start + (1 if step > 0 else 0)) % n], v)
        while len(near) < n:
            near.add(k)
            k2 = (k + step) % n
            far_end = points[(k2 + (1 if step > 0 else 0)) % n]
            d2 = math.dist(far_end, v)
            if d2 <= d or d > 3 * r:
                break
            k, d = k2, d2
    worst = None
    k = j1
    while True:
        k = (k + 1) % n
        if k == (j0 - 1) % n:
            break
        dist = _point_segment_distance(v, points[k], points[(k + 1) % n])
        need = r * (1 + 1e-9) if k in near else 2 * r
        if dist <= need:
            cand = (dist if k in near else 0.5 * dist) * (1 - 1e-6)
            worst = cand if worst is None else min(worst, cand)
    return worst


def round_cusps(points, miter_limit, radius, seg_angle, max_new_vertices, min_radius=0.0, max_seg_angle=None,
                max_cost=None, skipped=None):
    """ Cut the sharp reflex corners ("cusps") of a counter-clockwise polygon with a small disk around the corner.

    At a reflex corner that turns by phi, the mitered inward offset (the straight skeleton's wavefront) has its vertex
    on the bisector, 1/cos(phi/2) times the depth away from the corner, while the true (Euclidean) inward offset runs
    around the corner on a circle of radius depth. For a sharp cusp (the top of a heart, phi near 180 degrees) the
    mitered vertex shoots far into the shape: every turn of the spiral runs into a zero-width spike and back, and the
    spike hits the other side long before the shape pinches off (an early split event, which limits the annular width).

    A corner is a cusp if the outline, measured where it enters and leaves the circle of the given radius around the
    vertex, turns by more than the turn whose miter factor 1/cos(phi/2) is miter_limit (120 degrees for a limit of 2).
    Measuring the turn at that scale makes the test independent of how densely the outline is sampled (vertices
    within the circle, e.g. a collinear vertex next to the cusp or a cusp split into two corners of 87 degrees, count
    as one corner, cut around the sharpest of them; reflex vertices from rounding noise far below the radius are no
    cusps).

    The part of the polygon within the radius of the cusp is removed: the outline between the points where it enters
    and leaves the circle (e_in, e_out) is replaced by an arc of the circle through the inside of the polygon, in
    segments of at most seg_angle (s). The arc's inward offset at depth d is a polygonal circle of radius
    radius + d/cos(s/2) around the corner, i.e. the Euclidean offset of the given outline within
    radius + d (1/cos(s/2) - 1). (The whole arc needs the fine segments, also the 90 degrees on either side between
    an edge and its normal: there the convex vertex at e_in eats up the arc's segments one by one, and a coarse
    segment would survive as a mitered reflex corner.) The removed area is less than pi radius^2 per cusp and the
    result lies inside the given polygon (checked; if not, nothing is cut).

    The radius is reduced if the rest of the outline comes closer than 2 radii to the corner (or the outline re-enters
    the circle), so that the result stays simple; a corner that would need a radius below min_radius (arc chords too
    short for the skeleton's numerical resolution) is left as it is. If the arcs together would add more than
    max_new_vertices vertices, or the skeleton's cost (vertices x reflex vertices) would exceed max_cost, the segment
    angle is raised, up to max_seg_angle (default 20 degrees: coarser arcs leave reflex corners whose mitered tracks
    can hit another edge early, e.g. a 12-pointed sawblade splits at 4.6 mm instead of 19.9 mm with 29 degree
    segments); if they need more vertices even then (an outline with many cusps), no corner is cut (all or nothing,
    so that a symmetric outline stays symmetric). Corners left as they are are appended to `skipped` as
    (index, turn, reason).

    Returns (polygon, cusps, seg) with cusps a list of (index of the corner in points, radius, turn in radians,
    indices of the new vertices in the result) and seg the segment angle used. Vertex 0 of the result is vertex 0 of
    the input, or the first new vertex of the cut that removes it. """
    n = len(points)
    if skipped is None:
        skipped = []
    if n < 4:
        return list(points), [], seg_angle
    min_turn = 2 * math.acos(min(1.0, 1.0 / miter_limit))
    max_seg = max(seg_angle, math.radians(20) if max_seg_angle is None else max_seg_angle)
    turns = [_reflex_turn(points[k-1], points[k], points[(k+1) % n]) for k in range(n)]
    # Candidates: corners that turn by a few degrees or more themselves (a cusp may be split into several corners)
    order = sorted((k for k in range(n) if turns[k] > math.radians(5)), key=lambda k: -turns[k])
    cuts = [] # (i, r, phi, j0, j1, e_in, e_out)
    taken = set()
    for i in order:
        if i in taken:
            continue
        v = points[i]
        if any(math.dist(v, points[c[0]]) <= c[1] for c in cuts):
            continue # (within a cusp that is cut: its turn is part of that cusp's)
        r = radius
        cut = _cusp_cut(points, i, r)
        if cut is None:
            continue
        j0, j1, e_in, e_out = cut
        phi = _reflex_turn(e_in, v, e_out)
        if phi <= min_turn:
            continue
        for _attempt in range(20):
            smaller = _cusp_clearance(points, i, j0, j1, r)
            if smaller is None:
                break
            r = smaller
            if r < min_radius:
                break
            cut = _cusp_cut(points, i, r)
            if cut is None:
                break
            j0, j1, e_in, e_out = cut
        else:
            cut = None
        if cut is None or r < min_radius:
            skipped.append((i, turns[i], 'the outline passes too close to it'))
            continue
        phi = _reflex_turn(e_in, v, e_out) # (the turn at the smaller radius)
        if phi <= min_turn:
            continue
        span = {(j0 + m) % n for m in range((j1 - j0) % n + 1)}
        if span & taken or {(j0 - 1) % n, (j1 + 1) % n} & taken or \
                any(math.dist(v, points[c[0]]) < c[1] + r for c in cuts):
            continue # (overlaps a cut)
        taken |= span
        cuts.append((i, r, phi, j0, j1, e_in, e_out))
    if not cuts:
        return list(points), [], seg_angle

    reflex = [t > 0 for t in turns]
    n_reflex = sum(reflex)

    def fits(seg):
        # The arc's k + 1 vertices (e_in, e_out convex, the others reflex) replace the vertices inside the circle
        new = new_reflex = 0
        for _i, _r, phi, j0, j1, _a, _b in cuts:
            k = max(2, math.ceil((math.pi + phi) / seg - 1e-9))
            run = [(j0 + m) % n for m in range((j1 - j0) % n + 1)]
            new += k + 1 - len(run)
            new_reflex += k - 1 - sum(reflex[j] for j in run)
        return new <= max_new_vertices and (max_cost is None or (n + new) * (n_reflex + new_reflex) <= max_cost)
    seg = seg_angle
    if not fits(seg):
        if not fits(max_seg):
            skipped.extend((c[0], turns[c[0]], 'too many cusps for the skeleton\'s vertex budget') for c in cuts)
            return list(points), [], seg_angle
        lo, hi = seg, max_seg # (bisect the finest segment angle within the budget)
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            lo, hi = (lo, mid) if fits(mid) else (mid, hi)
        seg = hi
    arcs = {}
    for i, r, phi, j0, j1, e_in, e_out in cuts:
        v = points[i]
        a_in = math.atan2(e_in[1] - v[1], e_in[0] - v[0])
        theta = math.pi + phi # the interior angle at v, measured at e_in and e_out
        k = max(2, math.ceil(theta / seg - 1e-9))
        # Clockwise around v (through the inside) from e_in to e_out
        arc = [e_in] + [(v[0] + r*math.cos(a_in - theta*m/k), v[1] + r*math.sin(a_in - theta*m/k))
                        for m in range(1, k)] + [e_out]
        arcs[j0] = (i, r, phi, j1, arc)
    start = 0
    for j0, (_i, _r, _phi, j1, _arc) in arcs.items():
        if 0 != j0 and (0 - j0) % n <= (j1 - j0) % n:
            start = j0 # vertex 0 is inside this cut: start with the cut
    out, cusps = [], []
    m = 0
    while m < n:
        k = (start + m) % n
        if k in arcs:
            i, r, phi, j1, arc = arcs[k]
            first = len(out)
            out.extend(arc)
            cusps.append((i, r, phi, range(first, len(out))))
            m += (j1 - k) % n + 1
        else:
            out.append(points[k])
            m += 1
    from shapely.geometry import Polygon
    cut, given = Polygon(out), Polygon(points)
    if not cut.is_valid or not given.buffer(1e-9 * math.sqrt(given.area)).contains(cut):
        skipped.extend((c[0], turns[c[0]], 'the cut outline would not be simple') for c in cuts)
        return list(points), [], seg_angle
    return out, cusps, seg


def _track_point(track, depth, time_eps, times=None):
    """ Position on a vertex track (a list of skeleton nodes with non-decreasing time) at the given depth, see
    Skeletonator.track_position. """
    if times is None:
        times = [n.time for n in track]
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
    if n1.time - n0.time <= time_eps:
        return n1.pos if depth >= n1.time else n0.pos
    return interpolate(n0.pos, n1.pos, depth, n0.time, n1.time)


def _tracks_meet(ti, tj, until):
    """ Walk two vertex tracks forward in depth, up to depth `until`. Returns (times, merge): the node times of both
    tracks that were passed, and the depth from which the two tracks continue on the same nodes (so that the two
    vertices coincide at every greater depth), or None if they do not meet up to `until`. """
    a = b = 0
    la, lb = len(ti), len(tj)
    times = []
    while a < la and b < lb:
        ta, tb = ti[a].time, tj[b].time
        if min(ta, tb) > until:
            return times, None
        if ta < tb:
            times.append(ta)
            a += 1
        elif tb < ta:
            times.append(tb)
            b += 1
        else:
            # Nodes at the same time: the tracks meet if they share one of them and continue identically from there
            a2, b2 = a, b
            while a2 < la and ti[a2].time == ta:
                a2 += 1
            while b2 < lb and tj[b2].time == tb:
                b2 += 1
            for x in range(a, a2):
                for y in range(b, b2):
                    if ti[x] is tj[y] and ti[x:] == tj[y:]:
                        return times, ta
            times.append(ta)
            a, b = a2, b2
    times.extend(n.time for n in itertools.chain(ti[a:], tj[b:]) if n.time <= until)
    return times, None


def _chord_track(ta, tb, f, time_eps):
    """ Track of a vertex that was removed from the outline for the skeleton (see Skeletonator._spiral_vertices), at
    fraction f of the chord from vertex A (track ta) to vertex B (track tb) that replaced it.

    It moves like a vertex between two collinear edges in the skeleton of the full outline: it keeps its position
    along the chord, at the point of the offset edge A(d) B(d) with the same component along the chord's direction,
    until A or B reaches it. From there on it is absorbed into that vertex and continues on its track (on the same
    nodes). The track has a node at every node time of either track up to there, and where it is absorbed. """
    (ax, ay), (bx, by) = ta[0].pos, tb[0].pos
    length = math.hypot(bx - ax, by - ay)
    ex, ey = (bx - ax) / length, (by - ay) / length
    u = f * length
    def along(p):
        return (p[0] - ax)*ex + (p[1] - ay)*ey - u

    out = []
    times_a, times_b = [n.time for n in ta], [n.time for n in tb]
    a = b = 0
    la, lb = len(ta), len(tb)
    prev = None # (t, pa, pb, ga, gb) at the previous node
    while a < la or b < lb:
        t = min(times_a[a] if a < la else math.inf, times_b[b] if b < lb else math.inf)
        a2, b2 = a, b
        while a2 < la and times_a[a2] == t:
            a2 += 1
        while b2 < lb and times_b[b2] == t:
            b2 += 1
        # The value at depth t of a track without a node there
        mid_a = None if a2 > a else _track_point(ta, t, time_eps, times_a)
        mid_b = None if b2 > b else _track_point(tb, t, time_eps, times_b)
        # Several nodes at the same time are a jump (see _track_point): step through them together
        for s in range(max(a2 - a, b2 - b)):
            pa = ta[min(a + s, a2 - 1)].pos if mid_a is None else mid_a
            pb = tb[min(b + s, b2 - 1)].pos if mid_b is None else mid_b
            ga, gb = along(pa), along(pb)
            if ga >= 0 or gb <= 0:
                # Absorbed by A or B: at the depth where it reaches the vertex, linear in between
                cand = []
                for g, g0, track, i, i2, p, k in ((ga, 0 if prev is None else prev[3], ta, a, a2, pa, 1),
                                                  (-gb, 0 if prev is None else -prev[4], tb, b, b2, pb, 2)):
                    if g >= 0:
                        if prev is None or prev[0] >= t or g == g0:
                            cand.append((t, k, track, i, i2, p, None))
                        else:
                            ts = prev[0] + (t - prev[0]) * (-g0) / (g - g0)
                            p0 = prev[k]
                            w = (ts - prev[0]) / (t - prev[0])
                            q = (p0[0] + w*(p[0] - p0[0]), p0[1] + w*(p[1] - p0[1]))
                            cand.append((ts, k, track, i, i2, q, ts))
                ts, _k, track, i, i2, q, synthetic = min(cand, key=lambda c: (c[0], c[1]))
                if synthetic is None and i2 > i:
                    out.extend(track[min(i + s, i2 - 1):])
                else:
                    out.append(SkeletonNode(q[0], q[1], ts))
                    out.extend(track[i:])
                return out
            w = -ga / (gb - ga)
            out.append(SkeletonNode(pa[0] + w*(pb[0] - pa[0]), pa[1] + w*(pb[1] - pa[1]), t))
            prev = (t, pa, pb, ga, gb)
        a, b = a2, b2
    return out


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
        """ Run the module's main function. Returns (0, stdout). If the module exits with an error or aborts (a
        failed CGAL precondition, an exception such as bad_alloc), raises WasmAppError with what it wrote to
        stderr. """
        with NamedTemporaryFile('r') as stdout_f, NamedTemporaryFile('w') as stdin_f, \
                NamedTemporaryFile('r') as stderr_f:
            stdin_f.write(stdin)
            stdin_f.flush()

            wasi_cfg = wasmtime.WasiConfig()
            wasi_cfg.argv = argv
            wasi_cfg.stdin_file = stdin_f.name
            wasi_cfg.stdout_file = stdout_f.name
            wasi_cfg.stderr_file = stderr_f.name

            linker = wasmtime.Linker(self.engine)
            linker.define_wasi()
            store = wasmtime.Store(self.engine)
            store.set_wasi(wasi_cfg)
            self.app = linker.instantiate(store, self.module)
            linker.define_instance(store, "app", self.app)

            failed = None
            try:
                self.app.exports(store)["_start"](store)
            except wasmtime.ExitTrap as trap:
                if trap.code != 0:
                    failed = f'exit code {trap.code}'
            except wasmtime.Trap as trap:
                failed = str(trap).splitlines()[0] # e.g. abort() after an uncaught exception
            stderr = stderr_f.read()
            if failed is not None:
                raise WasmAppError(failed, stderr)
            if stderr:
                sys.stderr.write(stderr)
            return 0, stdout_f.read()


class WasmAppError(RuntimeError):
    def __init__(self, reason, stderr):
        self.reason, self.stderr = reason, stderr
        detail = ' '.join(stderr.split())
        super().__init__(f'{reason}: {detail}' if detail else reason)


# Nodes compare and hash by identity: compute_skeleton makes one object per distinct (x, y, time), and the vertex tracks
# hold millions of references to them on dense outlines, where a hash of the coordinates on every lookup is slow.
@dataclass(frozen=True, eq=False)
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

    try:
        rc, data = skeleton_wasm.run(input_data)
    except WasmAppError as e:
        if 'is_simple' in e.stderr:
            raise ValueError('The outline is not a simple polygon: it crosses or touches itself.') from e
        if 'bad_alloc' in e.stderr:
            raise ValueError(f'The straight skeleton of the outline ({len(points_deduplicated)} vertices) ran out of '
                             f'memory. Simplify the outline (fewer vertices, fewer concave corners).') from e
        raise RuntimeError(f'Error computing straight skeleton ({e})') from e

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

    `self.outline` is the polygon as given (normalized by `clean_polygon`), `self.poly` the polygon the vertex indices
    refer to and `self.skeleton_poly` the one the skeleton was computed for. All three are the same unless the outline
    has so many reflex vertices that its skeleton would be expensive: then `self.skeleton_poly` lacks the vertices that
    `remove_reflex_jitter` removes (within JITTER_TOLERANCE, 1 µm, of the chord that replaces them, see
    `_skeleton_of`), and `self.poly` has them projected onto that chord, with tracks along it (`_chord_track`).
    Before that, sharp reflex corners (cusps) of the outline are cut with a tiny arc (`round_cusps`, see CUSP_*):
    `self.layout_outline` is the outline after that (the one `self.poly` and `self.skeleton_poly` derive from),
    `self.cusps` lists the corners that were cut. The layout outline lies inside `self.outline`.

    The angle coordinate is fixed for the whole shape: vertex i always sits at angle `self.vertex_angles[i]`, no matter
    the depth. This makes consecutive turns of a spiral, and the arms of a multi-arm spiral, line up with each other
    exactly at every vertex.
    """

    TIME_EPS = 1e-9

    def __init__(self, poly, ref_depth=None):
        # Normalize the input: CGAL needs a counter-clockwise polygon without repeated points. Vertex 0 stays vertex 0.
        poly = clean_polygon(poly)
        self.outline = poly # the outline as given, normalized
        poly, self.cusps = self._round_cusps(poly)
        self.layout_outline = poly # the outline the spiral follows: self.outline with its cusps cut
        poly, self.skeleton_nodes, self.skeleton_edges = self._skeleton_of(poly)
        self.skeleton_poly = poly # the outline the skeleton was computed for; self.outline unless it was simplified
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
        self._adjacency = adjacency

        # Match the polygon vertices to the skeleton's contour nodes (time 0). The coordinates CGAL prints are rounded
        # to 12 significant digits, so they are matched to the nearest contour node instead of by value.
        contour = sorted({canon[n] for n in self.skeleton_nodes if n.time <= teps}, key=lambda n: (n.x, n.y))
        contour_x = [n.x for n in contour]
        match_tol = 1e-6 * extent + float_floor
        self.node_map = {}
        self.tracks = []
        # How a track goes on from a node depends only on the node. On smooth outlines all tracks run to the center
        # (their total length is quadratic in the number of vertices), so a track that reaches a node some earlier
        # track has passed copies the rest of that track.
        seen = {} # node -> (track, index) of its first occurrence
        for x, y in poly:
            lo = bisect.bisect_left(contour_x, x - match_tol)
            hi = bisect.bisect_right(contour_x, x + match_tol)
            start = min(contour[lo:hi], key=lambda n: math.hypot(n.x - x, n.y - y), default=None)
            if start is None or math.hypot(start.x - x, start.y - y) > match_tol:
                raise RuntimeError(f'Straight skeleton has no node at polygon vertex ({x}, {y})')
            self.node_map[(x, y)] = start
            track = [start]
            while True:
                node = track[-1]
                prev = seen.get(node)
                if prev is not None:
                    other, k = prev
                    track.extend(other[k+1:])
                    break
                seen[node] = (track, len(track) - 1)
                if node not in self.arc_map or node in self.divergent:
                    break
                exit_node = self._arc_exit[node]
                if exit_node is not node:
                    track.append(exit_node) # move along the constant-time group to where the way up leaves
                    seen.setdefault(exit_node, (track, len(track) - 1))
                track.append(self.arc_map[exit_node])
            self.tracks.append(track)
        if self.max_depth <= 0 or any(len(track) < 2 or track[-1].time <= 0 for track in self.tracks):
            raise ValueError('Degenerate straight skeleton: the polygon is too small, or too far away from the origin '
                             'for its size, to be represented with floating point precision.')
        # The tracks of the skeleton's vertices; the vertices that were removed for the skeleton get tracks along the
        # chord that replaced them (see _spiral_vertices).
        self._skeleton_tracks = self.tracks
        self._raw_skeleton_tracks = list(self.tracks) # the track lists are never modified in place
        self.poly, self._vertex_source = self._spiral_vertices(poly, merge_tol)
        self.poly_edges = list(zip(self.poly, self.poly[1:] + self.poly[:1]))
        self.circumference = sum(math.dist(a, b) for a, b in self.poly_edges)
        self.tracks = self._expand_tracks(self._skeleton_tracks)
        self._raw_tracks = list(self.tracks)
        self._track_nodes = list(seen) # every node on a track, once
        self._track_times = [[n.time for n in track] for track in self.tracks]
        self._tracks_version = 0 # changes whenever self.tracks changes
        self.fold_limit = 0.0
        self.uncut_protrusions = []
        self.cut_protrusions = []

        self.set_angle_reference(ref_depth)

    # Sharp reflex corners (cusps), see round_cusps. A reflex corner whose mitered offset vertex moves more than
    # CUSP_MITER_LIMIT times as fast as the wavefront (a turn of more than 120 degrees, measured at CUSP_RADIUS from
    # the corner) is cut with an arc of radius CUSP_RADIUS around it, so that the offsets run around the corner on a
    # polygonal circle instead of shooting a spike into the shape. Near the corner the turns then run up to
    # CUSP_RADIUS + depth * (1/cos(s/2) - 1) deeper than the Euclidean offset of the given outline, s the arc's segment
    # angle: s is chosen so that the second term stays below CUSP_DEPTH_TOL at the maximum inscribed radius (the
    # deepest any offset gets). Corners up to 120 degrees (an L's 90 degree corner, a star's inner corners) keep their
    # miter, as the keepout zone does (KEEPOUT_MITER_LIMIT in geometry.py). The radius grows with the outline's
    # extent where the arc's chords would otherwise come near the skeleton's numerical resolution (outlines above
    # about 300 mm).
    CUSP_MITER_LIMIT = 2.0
    CUSP_RADIUS = 0.01 # mm
    CUSP_DEPTH_TOL = 0.02 # mm
    CUSP_DEPTH_WARN = 0.05 # mm; warn if the budget makes the arcs so coarse that turns run this much deeper
    CUSP_MIN_CHORD = 3e-6 # times the extent: 10x the node merge tolerance
    CUSP_MAX_VERTICES = 360 # vertices all arcs together may add (more cusps: coarser arcs; far more: no cut)
    CUSP_EXTRA_COST = 50_000 # skeleton cost the arcs may add at least (about 5 s), see _skeleton_of

    def _round_cusps(self, poly):
        log = logging.getLogger('kicoil')
        xs, ys = [x for x, _y in poly], [y for _x, y in poly]
        extent = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
        n, r = len(poly), len(reflex_vertices(poly))
        if not any(_reflex_turn(poly[k-1], poly[k], poly[(k+1) % n]) > math.radians(5) for k in range(n)):
            self._cusp_vertices, self.cusp_segment_angle = set(), None
            return poly, []
        import shapely
        from shapely.geometry import Polygon
        try:
            ref_depth = shapely.maximum_inscribed_circle(Polygon(poly), 1e-3 * extent).length
        except Exception:
            ref_depth = 0.5 * extent
        ref_depth = max(ref_depth, self.CUSP_DEPTH_TOL)
        seg = 2 * math.acos(1 / (1 + self.CUSP_DEPTH_TOL / ref_depth))
        seg = min(seg, math.radians(15))
        min_chord = self.CUSP_MIN_CHORD * extent
        radius = max(self.CUSP_RADIUS, min_chord / (2 * math.sin(seg / 2)))
        # The arcs' vertices are reflex: they add to the skeleton's cost (vertices x reflex vertices, see _skeleton_of).
        # Allow them to double it, or to add CUSP_EXTRA_COST, but at most CUSP_MAX_VERTICES vertices. (This bounds the
        # cost of the arcs' vertices. A cut cusp makes the skeleton slower in any case, by about the same factor for a
        # single flat cut as for a fine arc: the wavefront no longer falls apart early. Heart: 0.35 s -> 1.9 s at 80
        # vertices, 6 s -> 28 s at 360.)
        skipped = []
        out, cusps, used = round_cusps(poly, self.CUSP_MITER_LIMIT, radius, seg, self.CUSP_MAX_VERTICES,
                                       min_radius=min_chord / (2 * math.sin(seg / 2)),
                                       max_cost=n * r + max(n * r, self.CUSP_EXTRA_COST), skipped=skipped)
        self._cusp_vertices = {k for c in cusps for k in c[3]}
        self.cusp_segment_angle = used
        if cusps:
            log.info(f'{len(cusps)} sharp reflex corner(s) of the outline cut with an arc of radius '
                     f'{min(c[1] for c in cusps):.3g} to {max(c[1] for c in cusps):.3g} mm in '
                     f'{math.degrees(used):.1f} degree segments: ' +
                     ', '.join(f'({poly[i][0]:.3f}, {poly[i][1]:.3f}) turning {math.degrees(phi):.1f} degrees'
                               for i, _r, phi, _k in cusps[:5]) + (' ...' if len(cusps) > 5 else ''))
            err = ref_depth * (1 / math.cos(used / 2) - 1)
            if radius + err > self.CUSP_DEPTH_WARN:
                log.warning(f'{len(cusps)} sharp reflex corners: their arcs have {math.degrees(used):.1f} degree '
                            f'segments to keep the skeleton affordable, so turns near them can run up to '
                            f'{radius + err:.3f} mm deeper than the intended offset')
        if skipped:
            log.warning(f'{len(skipped)} sharp reflex corner(s) of the outline left mitered (' +
                        '; '.join(f'({poly[i][0]:.3f}, {poly[i][1]:.3f}) turning {math.degrees(t):.1f} degrees: {why}'
                                  for i, t, why in skipped[:3]) + (' ...' if len(skipped) > 3 else '') +
                        '): the offsets shoot a spike into the shape there, and the usable annular width may be small')
        return out, [c[:3] for c in cusps]

    # Straight skeletons of outlines with many reflex vertices are slow and need a lot of memory: CGAL looks for split
    # events of every reflex vertex with every edge, and a nearly degenerate input (e.g. coordinates rounded to a grid)
    # makes it fall back to exact arithmetic. Time and memory grow with (number of vertices) x (number of reflex
    # vertices): about 0.1 ms and 1.2 kB per unit for clean outlines (stars, gears), 0.2 ms and 2.4 kB for outlines
    # with coordinates rounded to 1 µm. A 1000 vertex outline with 146 reflex vertices takes 30 s, one with 3000
    # vertices and 1261 reflex vertices runs out of memory (bad_alloc) after 6 to 11 minutes. skeleton.wasm can use
    # at most 4 GB of memory (32 bit WebAssembly).
    JITTER_TOLERANCE = 0.001 # mm; reflex vertices this close to the chord of their neighbors are rounding noise
    SIMPLIFY_COST = 25_000 # above this cost, the outline is simplified for the skeleton (remove_reflex_jitter)
    MAX_COST = 3_500_000 # above this cost (after simplifying), the skeleton cannot fit into 4 GB even at 1.2 kB/unit

    def _skeleton_of(self, poly):
        """ Straight skeleton of the outline, simplified first if its skeleton would be expensive. Returns (outline
        used, nodes, edges). Outlines whose skeleton certainly does not fit into skeleton.wasm's memory raise a
        ValueError. """
        n, r = len(poly), len(reflex_vertices(poly))
        what = f'{n} vertices, {r} of them reflex (concave) corners'
        if n * r > self.SIMPLIFY_COST:
            # Tiny reflex corners from rounding noise (e.g. coordinates exported with 1 µm resolution) make up most
            # reflex vertices of a dense smooth outline. Without them, the outline moves outward by at most
            # JITTER_TOLERANCE, far below any useful clearance. The removed vertices stay vertices of the spiral, on
            # the chord that replaced them (_spiral_vertices), so the angle reference stays as fine as the outline.
            # This is only done where it makes the skeleton much cheaper (or possible at all): outlines whose reflex
            # corners are real, with a few shallow ones among them, are left alone.
            # (The arcs that cut cusps are not noise, although their chords are within 1 µm of each other)
            simple = remove_reflex_jitter(poly, self.JITTER_TOLERANCE, keep=getattr(self, '_cusp_vertices', ()))
            rs = len(reflex_vertices(simple))
            if len(simple) < n and (len(simple) * rs <= n * r / 2 or n * r > self.MAX_COST):
                what = (f'{len(simple)} vertices, {rs} of them reflex (concave) corners deeper than '
                        f'{self.JITTER_TOLERANCE * 1000:.0f} µm, after removing {n - len(simple)} shallower ones')
                if len(simple) * rs <= self.MAX_COST:
                    try:
                        nodes, edges = compute_skeleton(exterior=simple)
                    except ValueError:
                        # E.g. a chord that touches another part of the outline: use the outline as it is
                        what = f'{n} vertices, {r} of them reflex (concave) corners'
                    else:
                        logging.getLogger('kicoil').info(
                            f'Outline simplified for the straight skeleton: {n - len(simple)} vertices within '
                            f'{self.JITTER_TOLERANCE * 1000:.0f} µm of the chord between their neighbors were '
                            f'removed ({n} vertices, {r} of them reflex, before; {len(simple)} and {rs} after).')
                        return simple, nodes, edges
                else:
                    n, r = len(simple), rs # for the error below
        if n * r > self.MAX_COST:
            raise ValueError(f'The outline is too complex for the straight skeleton: it has {what}. The skeleton needs '
                             f'about 1.2 kB of memory or more per vertex and reflex corner pair ({n * r} pairs), more '
                             f'than the 4 GB it can use (the limit is {self.MAX_COST} pairs). Simplify the outline: '
                             f'fewer vertices, or fewer concave corners (e.g. smooth out noise from the import).')
        nodes, edges = compute_skeleton(exterior=poly)
        return poly, nodes, edges

    def _spiral_vertices(self, skeleton_poly, min_gap):
        """ The vertices of the spiral's coordinate system: the outline's vertices, where those that were removed for
        the skeleton (see _skeleton_of) are projected onto the chord that replaced them. Returns (vertices, source),
        with source[i] = (k, f): vertex i is at fraction f of the skeleton's edge from its vertex k to k+1 (f = 0 for
        the skeleton's vertices themselves). source is None if the skeleton has all vertices of the outline.

        Keeping these vertices keeps the angle reference (an angle span per edge, see set_angle_reference) as fine as
        the outline, e.g. along nearly straight stretches with many vertices. A projected vertex that would not be at
        least min_gap further along the chord than the one before it is left out. """
        outline = self.layout_outline
        if len(skeleton_poly) == len(outline):
            return skeleton_poly, None
        kept, j = [], 0
        for i, p in enumerate(outline):
            if j < len(skeleton_poly) and p == skeleton_poly[j]:
                kept.append(i)
                j += 1
        assert j == len(skeleton_poly) and kept[0] == 0, 'the skeleton outline must be a subsequence of the outline'
        m, n = len(skeleton_poly), len(outline)
        poly, source = [], []
        for k in range(m):
            (ax, ay), (bx, by) = skeleton_poly[k], skeleton_poly[(k + 1) % m]
            poly.append((ax, ay))
            source.append((k, 0.0))
            dx, dy = bx - ax, by - ay
            length = math.hypot(dx, dy)
            end = kept[k + 1] if k + 1 < m else n
            u_prev = 0.0
            for i in range(kept[k] + 1, end):
                px, py = outline[i]
                u = ((px - ax)*dx + (py - ay)*dy) / length # distance along the chord
                if u_prev + min_gap < u < length - min_gap:
                    f = u / length
                    poly.append((ax + f*dx, ay + f*dy))
                    source.append((k, f))
                    u_prev = u
        return poly, source

    def _expand_tracks(self, skeleton_tracks):
        """ Tracks of all vertices (self.poly) from the tracks of the skeleton's vertices """
        if self._vertex_source is None:
            return skeleton_tracks
        m = len(skeleton_tracks)
        return [skeleton_tracks[k] if f == 0 else
                _chord_track(skeleton_tracks[k], skeleton_tracks[(k + 1) % m], f, self.TIME_EPS)
                for k, f in self._vertex_source]

    def set_fold_limit(self, limit):
        """ Cut off narrow protrusions of the offset outline.

        Where two parallel (or converging) edges of the outline collapse onto each other at depth T while the outline
        goes on beyond T (a constant-time group of skeleton nodes with one way up, e.g. the stem of a T, a finger, a
        keyhole's tab), the offset outline at depths just below T has a sliver of width about 2*(T - depth). A spiral
        turn at such a depth runs into the sliver and back out, so its copper folds onto itself. With a limit > 0, the
        vertices inside the protrusion ("tips") jump to the protrusion's mouth at depth T - limit and follow the mouth
        from there, i.e. turns deeper than T - limit cut straight across the protrusion's mouth. Use half the turn
        pitch, so that every turn that runs into a protrusion has its two sides at least one pitch apart.

        The mouth is spanned by the tracks that reach the protrusion's exit node from outside it (usually the two
        reflex corners where the protrusion meets the rest of the outline). Each tip lands on the mouth chord between
        the mouth vertices before and after it in outline order: at the orthogonal projection of its position at
        T - limit, clamped to the chord and kept in outline order. For a straight protrusion this is the projection
        along its axis, so each tip stays on its own side; for a bent one (an L) the tips still land on the chord
        instead of inside the outline. Where the mouth has a single vertex (its other side is an edge, e.g. the part
        of a square beside a slot), the tips move along the protrusion's axis at the mouth onto the line through that
        vertex perpendicular to the axis, so they stay on their side.

        Protrusions are cut in order of increasing T, each on the tracks as already cut by the shallower ones, so the
        vertices of a protrusion nested in a wider one (a stepped finger, a side branch) are cut at the inner mouth
        first and then again at the outer mouth.

        Protrusions whose mouth cannot be determined are left as they are and listed in `uncut_protrusions` as
        (x, y, T) of the collapse point. Cut protrusions are listed in `cut_protrusions` as (x, y, T, cut depth).
        """
        limit = max(0.0, float(limit))
        if limit == self.fold_limit:
            return
        self.fold_limit = limit
        raw = self._raw_skeleton_tracks # cut the skeleton's vertex tracks, the others follow them (_expand_tracks)
        tracks = list(raw)
        self.uncut_protrusions = []
        cut = {}
        exit_of = self._arc_exit
        def in_group(n, exit_node):
            return exit_of.get(n) is exit_node and abs(n.time - exit_node.time) <= self.teps
        # A track that passes a member of a constant-time group other than its exit node goes on to the exit node.
        # Without such groups there is nothing to cut (this is the common case for smooth outlines, whose tracks are
        # too long to scan).
        has_groups = any(exit_of.get(m, m) is not m and in_group(m, exit_of[m]) for m in self._track_nodes)
        if limit > 0 and has_groups:
            def entry(t, e):
                """ Index j where track t enters the group of exit e at a member other than e (t[j+1] is e), or None """
                for j in range(1, len(t) - 1):
                    m = t[j]
                    if t[j+1] is e and m is not e and exit_of.get(m) is e and in_group(m, e) \
                            and not in_group(t[j-1], e):
                        return j
                return None
            # Mouth of a protrusion: the tracks that reach the group's exit node from outside the group
            mouths = {}
            exits = set()
            for i, t in enumerate(raw):
                for a, b in itertools.pairwise(t):
                    if exit_of.get(b) is b and not in_group(a, b):
                        mouths.setdefault(b, []).append(i)
                    if b is not a and exit_of.get(a) is b and in_group(a, b):
                        exits.add(b)
            n = len(raw)
            for e in sorted(exits, key=lambda e: (e.time, e.x, e.y)):
                T = e.time
                if T <= limit * 1e-6:
                    continue
                tips = {}
                for i, t in enumerate(tracks):
                    j = entry(t, e)
                    if j is not None:
                        tips[i] = j
                if not tips:
                    continue
                mouth = sorted(set(mouths.get(e, ())))
                if not mouth:
                    self.uncut_protrusions.append((e.x, e.y, T))
                    continue
                tc = max(0.0, T - limit)
                mpos = {k: _track_point(tracks[k], tc, self.TIME_EPS) for k in mouth}
                # Tips between the same two mouth vertices (in outline order) land on the same chord, in outline order.
                runs = {}
                for i in tips:
                    a = next(((i - d) % n for d in range(1, n) if (i - d) % n in mpos), None)
                    b = next(((i + d) % n for d in range(1, n) if (i + d) % n in mpos), None)
                    runs.setdefault((a, b), []).append(i)
                # Axis of the protrusion at its mouth: from the exit node along the group's last edge
                near = [m for m in self._adjacency.get(e, ()) if in_group(m, e) and m is not e]
                axis = None
                if len(near) == 1:
                    ux, uy = near[0].x - e.x, near[0].y - e.y
                    ul = math.hypot(ux, uy)
                    if ul > self.merge_tol:
                        axis = (ux / ul, uy / ul)
                for (a, b), run in runs.items():
                    run.sort(key=lambda i: (i - a) % n)
                    (ax, ay), (bx, by) = mpos[a], mpos[b]
                    dx, dy = bx - ax, by - ay
                    dd = dx*dx + dy*dy
                    s_prev = 0.0
                    for i in run:
                        t, j = tracks[i], tips[i]
                        tx, ty = _track_point(t, tc, self.TIME_EPS)
                        if dd > self.merge_tol**2:
                            # Onto the chord between the two mouth vertices, in outline order
                            s = min(1.0, max(0.0, ((tx - ax)*dx + (ty - ay)*dy) / dd))
                            s = s_prev = max(s, s_prev)
                            qx, qy = ax + s*dx, ay + s*dy
                        else:
                            # A single mouth vertex: the other side of the mouth is an edge of the outline. Move along
                            # the axis onto the line through the mouth vertex perpendicular to it, which keeps the tip
                            # on its own side (on that edge).
                            m = t[j]
                            ux, uy = axis if axis is not None else (m.x - e.x, m.y - e.y)
                            ul = math.hypot(ux, uy)
                            if ul <= self.merge_tol:
                                qx, qy = ax, ay
                            else:
                                ux, uy = ux / ul, uy / ul
                                d = (tx - ax)*ux + (ty - ay)*uy
                                qx, qy = tx - d*ux, ty - d*uy
                        head = [p for p in t[:j] if p.time < tc]
                        tracks[i] = head + [SkeletonNode(tx, ty, tc), SkeletonNode(qx, qy, tc)] + t[j+1:]
                cut[e] = (e.x, e.y, T, tc)
        self.cut_protrusions = list(cut.values())
        if tracks != self._skeleton_tracks:
            self._skeleton_tracks = tracks
            self.tracks = self._expand_tracks(tracks)
            self._track_times = [[n.time for n in track] for track in self.tracks]
            self._tracks_version = getattr(self, '_tracks_version', 0) + 1
        self.set_angle_reference(getattr(self, 'ref_depth', None))

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
        key = (getattr(self, '_tracks_version', None), max_depth)
        if getattr(self, '_angle_reference_key', None) == key:
            return # same tracks, same depth range: nothing changed
        min_len = self._min_edge_lengths(max_depth)
        self._apply_edge_lengths(min_len, max_depth)
        self._angle_reference_key = key

    def _sample_depths(self, max_depth):
        """ Depths at which the edge lengths are sampled: 0, max_depth and every track node time in between """
        cached = getattr(self, '_all_times', None)
        version = getattr(self, '_tracks_version', None)
        if cached is None or cached[0] != version or version is None:
            cached = self._all_times = (version, sorted(set(itertools.chain.from_iterable(self._track_times))))
        times = cached[1]
        inner = times[bisect.bisect_right(times, 0):bisect.bisect_left(times, max_depth)]
        return sorted({0.0, max_depth}.union(inner))

    def _min_edge_lengths_bruteforce(self, max_depth):
        """ Reference implementation of `_min_edge_lengths`: every edge at every sample depth, O(n * depths). """
        depths = self._sample_depths(max_depth)
        n = len(self.poly)
        min_len = [math.inf] * n
        for d in depths:
            pts = [self.track_position(i, d) for i in range(n)]
            for i in range(n):
                min_len[i] = min(min_len[i], math.dist(pts[i], pts[(i+1) % n]))
        return min_len

    def _min_edge_lengths(self, max_depth):
        """ Shortest length of every edge (vertex i to vertex i+1) over the sample depths (`_sample_depths`).

        Same result as evaluating every edge at every sample depth (`_min_edge_lengths_bruteforce`), which is quadratic
        in the number of vertices, but only looks at the parts of the edge's own two tracks before they meet:

        - Once the two tracks have met (they continue on the same nodes), the two vertices have the same position at
          every greater depth, so the edge's shortest length is exactly 0 if that happens within max_depth. On a
          smooth outline the tracks are long (all of them run to the center), but neighboring tracks meet soon.
        - Before that, between two consecutive node times of the two tracks (a "piece"), the edge vector is an affine
          function of the depth, so its length is convex there and its smallest value over the sample depths in the
          piece is at one of the two sample depths around the piece's continuous minimum.

        The candidate depths (and their neighbors, against rounding) are evaluated with the same `track_position`
        calls as in the brute force version, so the values are identical. """
        depths = self._sample_depths(max_depth)
        nd = len(depths)
        n = len(self.poly)
        teps = self.TIME_EPS

        def velocity(i, d):
            """ d(position)/d(depth) of track i on the piece of its track that starts at depth d """
            track, times = self.tracks[i], self._track_times[i]
            if len(track) == 1 or d >= times[-1]:
                return 0.0, 0.0
            k = 0 if d <= times[0] else max(0, min(len(track) - 2, bisect.bisect_right(times, d) - 1))
            n0, n1 = track[k], track[k+1]
            dt = n1.time - n0.time
            if dt <= teps or math.isclose(n0.time, n1.time): # constant there, see _track_point and interpolate
                return 0.0, 0.0
            return (n1.x - n0.x) / dt, (n1.y - n0.y) / dt

        def dist_at(i, j, d):
            return math.dist(self.track_position(i, d), self.track_position(j, d))

        min_len = [math.inf] * n
        for i in range(n):
            j = (i + 1) % n
            times, merge = _tracks_meet(self.tracks[i], self.tracks[j], max_depth)
            end = max_depth if merge is None else max(0.0, merge)
            bounds = sorted({0.0, end}.union(t for t in times if 0 < t < end))
            best = math.inf
            if merge is not None:
                # The vertices coincide from depth `merge` on
                best = min(dist_at(i, j, end), dist_at(i, j, max_depth))
                pieces = itertools.pairwise(bounds)
            else:
                pieces = itertools.pairwise(bounds + [math.inf]) # the last piece is max_depth alone
            for b0, b1 in pieces:
                # Sample depths in [b0, b1)
                lo = bisect.bisect_left(depths, b0)
                hi = nd if b1 == math.inf else bisect.bisect_left(depths, b1)
                if hi <= lo:
                    continue
                cand = {lo}
                if hi - lo > 1:
                    pi, pj = self.track_position(i, b0), self.track_position(j, b0)
                    vix, viy = velocity(i, b0)
                    vjx, vjy = velocity(j, b0)
                    ex, ey = pj[0] - pi[0], pj[1] - pi[1]
                    wx, wy = vjx - vix, vjy - viy
                    ww = wx*wx + wy*wy
                    d_min = b0 if ww <= 0 else b0 - (ex*wx + ey*wy) / ww
                    k = bisect.bisect_left(depths, d_min, lo, hi)
                    cand.update(m for m in range(k - 2, k + 2) if lo <= m < hi)
                    cand.add(hi - 1)
                for m in cand:
                    best = min(best, dist_at(i, j, depths[m]))
            min_len[i] = best
        return min_len

    def _apply_edge_lengths(self, min_len, max_depth):
        """ Vertex angles from the edges' shortest lengths, see set_angle_reference """
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
        return _track_point(self.tracks[i], depth, self.TIME_EPS, self._track_times[i])

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