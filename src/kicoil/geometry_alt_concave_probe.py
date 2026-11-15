"""Prototype (exploration only): lift the split-depth limit of concave outlines by rounding sharp reflex corners.

The base Skeletonator now cuts sharp reflex corners (turning by more than 120 degrees) itself, with a 0.01 mm arc
(`skeletonator.round_cusps`, D-CUSP-1 in docs/DEFECTS.md); this probe rounds further corners on top of that.

At a reflex corner with interior angle theta, the straight-skeleton (mitered) inward offset moves the corner vertex
by depth/sin(theta/2) per unit of depth, i.e. a sharp reflex corner shoots a spike deep into the shape. The spike hits
the opposite side long before the Euclidean inward offset (erosion) of the outline would pinch off, which is the
straight skeleton's first split event and limits the annular width (`Skeletonator.max_depth`). Example: the cusp at the
top of a heart splits the skeleton at a depth of 1.6 mm although its inscribed circle has a radius of 11.5 mm.

Here every reflex corner that turns by more than `REFLEX_MIN_TURN` is replaced by a small arc centered *at the corner*
(the corner is cut off by a disk around it). The arc's radius is `REFLEX_RADIUS` (0.02 mm), at most 0.45 times the shorter
adjacent edge; `rounded_radii` on the shape lists the effective radii. The radius is kept tiny on purpose: the layout
measures depth from the arc, i.e. from a point r inside the intended corner, so near the corner the turns run r deeper
than the intended annulus (plus d*(1/cos(seg/2) - 1) from the polygonal arc at depth d). With the former 0.5 mm default
(0.078 mm effective at the heart's cusp, 15 degree segments) the heart's n8k3 coils overshot the intended envelope by up
to 0.096 mm; with 0.02 mm and 5 degree segments by at most 0.022 mm. The split depth does not depend on the radius. The modified outline lies inside the intended one,
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

# (Overridable through the environment for exploration: KICOIL_PROBE_RADIUS in mm, KICOIL_PROBE_SEG_DEG in degrees)
REFLEX_RADIUS = float(os.environ.get('KICOIL_PROBE_RADIUS', 0.02)) # mm, radius of the arc replacing a sharp reflex corner
REFLEX_MIN_TURN = math.radians(15) # corners that turn less than this are left alone
ARC_SEG_ANGLE = math.radians(float(os.environ.get('KICOIL_PROBE_SEG_DEG', 5))) # angle per segment of the arc


def round_reflex_corners(poly, radius=REFLEX_RADIUS, min_turn=REFLEX_MIN_TURN, seg_angle=ARC_SEG_ANGLE, only=None,
                         radii=None):
    """ Replace each sharp reflex corner of the counter-clockwise polygon poly (or only those with an index in `only`)
    by an arc of the given radius centered at the corner, sweeping through the inside of the polygon. The radius is
    limited to 0.45 times the shorter adjacent edge (appended to the list `radii` if given). Returns the new polygon (a
    subset of poly). """
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
        if radii is not None:
            radii.append(r)
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


def lift_split_depth(poly, radius=REFLEX_RADIUS, max_iter=30, seg_angle=ARC_SEG_ANGLE, radii=None):
    """ Greedily round the sharp reflex corners that cause the first split event, as long as that makes the split
    deeper. Rounding every reflex corner is not always better: it turns a parallel-sided protrusion (comb tooth) into a
    neck that pinches off earlier, and it narrows a real neck by about the radius. Returns (polygon, split depths). """
    from kicoil import skeletonator
    poly = skeletonator.clean_polygon(poly)
    sk = skeletonator.Skeletonator(poly)
    history = [sk.max_depth]
    for _ in range(max_iter):
        idx = split_vertices(sk)
        r_new = []
        cand = round_reflex_corners(sk.poly, radius, seg_angle=seg_angle, only=idx, radii=r_new)
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
        if radii is not None:
            radii.extend(r_new)
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
        self.rounded_radii = []
        self.polygon, self.split_history = lift_split_depth(self.design_outline, self.reflex_radius,
                                                            radii=self.rounded_radii)
        super().__post_init__()

    @property
    def slug(self):
        return f'polygon_{len(self.design_outline)}pt_rr'

    @property
    def desc(self):
        return f'{len(self.design_outline)} point polygonal (reflex corners rounded)'
