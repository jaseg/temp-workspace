"""Prototype (exploration only): lift the split-depth limit of concave outlines by rounding sharp reflex corners.

At a reflex corner with interior angle theta, the straight-skeleton (mitered) inward offset moves the corner vertex
by depth/sin(theta/2) per unit of depth, i.e. a sharp reflex corner shoots a spike deep into the shape. The spike hits
the opposite side long before the Euclidean inward offset (erosion) of the outline would pinch off, which is the
straight skeleton's first split event and limits the annular width (`Skeletonator.max_depth`). Example: the cusp at the
top of a heart splits the skeleton at a depth of 1.6 mm although its inscribed circle has a radius of 11.5 mm.

Here every reflex corner that turns by more than `REFLEX_MIN_TURN` is replaced by a small arc of radius `REFLEX_RADIUS`
centered *at the corner* (the corner is cut off by a disk around it). The modified outline lies inside the intended one,
so the copper stays inside the outline. The arc's straight skeleton offset is a growing (polygonal) circle around the
corner, so the offset outline follows the Euclidean offset there and splits only where the outline really has a neck.

This does not help against real necks (a dumbbell's bar, a shark's tail peduncle): for those, see the coverage
estimates in the concave corpus report (cutting protrusions at necks, multiple coils).

The base layout is `kicoil.geometry`, or the module named by the environment variable KICOIL_PROBE_BASE (e.g.
geometry_alt_cornerflat). The shape keeps the intended outline in `design_outline` for the checker.
"""

import importlib
import math
import os
from dataclasses import dataclass, field

_base = importlib.import_module(f'kicoil.{os.environ.get("KICOIL_PROBE_BASE", "geometry")}')
globals().update({k: v for k, v in vars(_base).items() if not k.startswith('__')})

REFLEX_RADIUS = 0.5 # mm, radius of the arc that replaces a sharp reflex corner
REFLEX_MIN_TURN = math.radians(15) # corners that turn less than this are left alone
ARC_SEG_ANGLE = math.radians(15) # angle per segment of the replacement arc


def round_reflex_corners(poly, radius=REFLEX_RADIUS, min_turn=REFLEX_MIN_TURN, seg_angle=ARC_SEG_ANGLE, only=None):
    """ Replace each sharp reflex corner of the counter-clockwise polygon poly (or only those with an index in `only`)
    by an arc of the given radius centered at the corner, sweeping through the inside of the polygon. The radius is
    limited to 0.45 times the shorter adjacent edge. Returns the new polygon (a subset of poly). """
    n = len(poly)
    out = []
    for i in range(n):
        if only is not None and i not in only:
            out.append(poly[i])
            continue
        p0, v, p1 = poly[i-1], poly[i], poly[(i+1) % n]
        ux, uy = v[0] - p0[0], v[1] - p0[1]
        wx, wy = p1[0] - v[0], p1[1] - v[1]
        lu, lw = math.hypot(ux, uy), math.hypot(wx, wy)
        if lu == 0 or lw == 0:
            continue
        cross = ux*wy - uy*wx
        turn = math.atan2(cross, ux*wx + uy*wy) # > 0: left turn (convex), < 0: right turn (reflex)
        if turn > -min_turn:
            out.append(v)
            continue
        r = min(radius, 0.45*lu, 0.45*lw)
        # interior angle theta = pi - turn (> pi). The arc runs clockwise around v from direction -u to direction w.
        a0 = math.atan2(-uy, -ux)
        theta = math.pi - turn
        k = max(2, math.ceil(theta / seg_angle))
        for j in range(k+1):
            a = a0 - theta*j/k
            out.append((v[0] + r*math.cos(a), v[1] + r*math.sin(a)))
    return out


def split_vertices(sk):
    """ Indices of the polygon vertices whose skeleton track ends at the first split event """
    return {i for i, t in enumerate(sk.tracks) if t[-1] in sk.divergent and abs(t[-1].time - sk.max_depth) <= sk.teps}


def lift_split_depth(poly, radius=REFLEX_RADIUS, max_iter=30):
    """ Greedily round the sharp reflex corners that cause the first split event, as long as that makes the split
    deeper. Rounding every reflex corner is not always better: it turns a parallel-sided protrusion (comb tooth) into a
    neck that pinches off earlier, and it narrows a real neck by about the radius. Returns (polygon, split depths). """
    from kicoil import skeletonator
    poly = skeletonator.clean_polygon(poly)
    sk = skeletonator.Skeletonator(poly)
    history = [sk.max_depth]
    for _ in range(max_iter):
        idx = split_vertices(sk)
        cand = round_reflex_corners(sk.poly, radius, only=idx)
        if len(cand) == len(sk.poly):
            break # nothing to round (the split is caused by corners too flat to round)
        try:
            sk2 = skeletonator.Skeletonator(cand)
        except (ValueError, RuntimeError):
            break
        if sk2.max_depth <= sk.max_depth + 1e-6:
            break
        sk = sk2
        history.append(sk.max_depth)
    # Not done: when the deepest event is the final collapse rather than a split (a star), rounding all reflex corners
    # raises it (rounded star: 11.67 -> 12.65 mm), but the layout got worse there (pitch ratio 0.28 instead of 0.72 at
    # 90 % depth: the arcs' vertices have nearly zero angle span, and the arm starts crowd at them).
    return list(sk.poly), history


@dataclass
class PolygonShape(_base.OffsetShape if hasattr(_base, 'OffsetShape') else object):
    polygon: list
    annular_width: float
    arc_tolerance: float = 0.05
    reflex_radius: float = REFLEX_RADIUS
    design_outline: list = field(default=None)

    def __post_init__(self):
        from kicoil import skeletonator
        self.design_outline = skeletonator.clean_polygon(self.polygon)
        self.polygon, self.split_history = lift_split_depth(self.design_outline, self.reflex_radius)
        super().__post_init__()

    @property
    def slug(self):
        return f'polygon_{len(self.design_outline)}pt_rr'

    @property
    def desc(self):
        return f'{len(self.design_outline)} point polygonal (reflex corners rounded)'
