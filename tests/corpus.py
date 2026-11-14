"""Corpus of planar coil test cases.

Every case is a plain dict ("spec") so that it can be fed to different layout implementations:

    {
        'name': str,            # unique case name
        'shape': str,           # 'circle' or 'polygon'
        'polygon': [(x, y)],    # CCW outline for 'polygon' shapes
        'outer_diameter': float, 'inner_diameter': float,  # for 'circle' shapes
        'annular_width': float, # for 'polygon' shapes
        'turns': int, 'twists': int, 'layers': int, 'clockwise': bool,
        'clearance': float, 'trace_width': float or None,
        'tags': [str],          # e.g. 'convex', 'reflex', 'sweep', 'hard'
    }

The corpus is generated deterministically (seeded RNG). `corpus('quick')` returns a small subset that is fast enough for
the pytest suite, `corpus('full')` everything including the parameter sweeps.
"""

import math
import random
from math import gcd

from shapely.geometry import Polygon
import shapely


def _ccw(pts):
    p = Polygon(pts)
    if not p.exterior.is_ccw:
        pts = pts[::-1]
    return [(float(x), float(y)) for x, y in pts]


def regular(n, d, phase=0.0):
    r = d/2
    return _ccw([(-r*math.sin(2*math.pi*(i+phase)/n), r*math.cos(2*math.pi*(i+phase)/n)) for i in range(n)])


def rect(w, h):
    return _ccw([(w/2, -h/2), (w/2, h/2), (-w/2, h/2), (-w/2, -h/2)])


def trapezoid(w, h, off):
    return _ccw([(w/2-off, -h/2), (w/2, h/2), (-w/2, h/2), (-w/2+off, -h/2)])


def star(n, od, id_):
    pts = []
    for i in range(n):
        for r, ph in ((od/2, 0), (id_/2, 0.5)):
            a = 2*math.pi*(i+ph)/n
            pts.append((-r*math.sin(a), r*math.cos(a)))
    return _ccw(pts)


def sector(od, id_, angle_deg, tol=0.05):
    angle = math.radians(angle_deg)
    r1, r2 = id_/2, od/2
    n1 = math.ceil(math.pi / math.acos(1 - tol/id_) * angle / (2*math.pi))
    pt = lambda r, a: (r*math.sin(a), r*math.cos(a))
    poly = [pt(r2, angle/2 - i/n1 * angle) for i in range(n1+1)]
    poly += [pt(r1, i/n1 * angle - angle/2) for i in range(n1+1)]
    # center the shape (the sector's centroid is far away from the origin)
    c = Polygon(poly).centroid
    return _ccw([(x-c.x, y-c.y) for x, y in poly])


def ellipse(a, b, n=64):
    return _ccw([(a/2*math.cos(2*math.pi*i/n), b/2*math.sin(2*math.pi*i/n)) for i in range(n)])


def rounded_rect(w, h, r, n=6):
    pts = []
    for cx, cy, a0 in ((w/2-r, h/2-r, 0), (-w/2+r, h/2-r, 90), (-w/2+r, -h/2+r, 180), (w/2-r, -h/2+r, 270)):
        for i in range(n+1):
            a = math.radians(a0 + 90*i/n)
            pts.append((cx + r*math.cos(a), cy + r*math.sin(a)))
    return _ccw(pts)


def chamfered_rect(w, h, c):
    return _ccw([(w/2, -h/2+c), (w/2, h/2-c), (w/2-c, h/2), (-w/2+c, h/2), (-w/2, h/2-c), (-w/2, -h/2+c),
                 (-w/2+c, -h/2), (w/2-c, -h/2)])


def l_shape(w, h, t):
    pts = [(0, 0), (w, 0), (w, t), (t, t), (t, h), (0, h)]
    c = Polygon(pts).centroid
    return _ccw([(x-c.x, y-c.y) for x, y in pts])


def u_shape(w, h, t):
    pts = [(0, 0), (w, 0), (w, h), (w-t, h), (w-t, t), (t, t), (t, h), (0, h)]
    c = Polygon(pts).centroid
    return _ccw([(x-c.x, y-c.y) for x, y in pts])


def d_shape(d, n=24):
    r = d/2
    pts = [(r*math.cos(math.pi/2 - math.pi*i/n), r*math.sin(math.pi/2 - math.pi*i/n)) for i in range(n+1)]
    pts += [(-r*0.3, -r), (-r*0.3, r)]
    c = Polygon(pts).centroid
    return _ccw([(x-c.x, y-c.y) for x, y in pts])


def subdivided_rect(w, h, jitter, rng):
    """ Rectangle with extra, nearly collinear vertices on its edges """
    pts = []
    corners = [(w/2, -h/2), (w/2, h/2), (-w/2, h/2), (-w/2, -h/2)]
    for (x1, y1), (x2, y2) in zip(corners, corners[1:] + corners[:1]):
        pts.append((x1, y1))
        for k in range(1, 3):
            t = k/3 + rng.uniform(-0.05, 0.05)
            nx, ny = -(y2-y1), (x2-x1)
            ln = math.hypot(nx, ny)
            j = rng.uniform(-jitter, jitter)
            pts.append((x1 + t*(x2-x1) + j*nx/ln, y1 + t*(y2-y1) + j*ny/ln))
    return _ccw(pts)


def random_convex(n, d, rng):
    pts = [(rng.gauss(0, 1), rng.gauss(0, 1)) for _ in range(n*3)]
    hull = shapely.convex_hull(shapely.MultiPoint(pts))
    coords = list(hull.exterior.coords)[:-1]
    c = hull.centroid
    scale = d / max(hull.bounds[2]-hull.bounds[0], hull.bounds[3]-hull.bounds[1])
    return _ccw([((x-c.x)*scale, (y-c.y)*scale) for x, y in coords])


def random_starlike(n, d, rng, depth=0.35):
    pts = []
    for i in range(n):
        a = 2*math.pi*(i + rng.uniform(-0.3, 0.3))/n
        r = d/2 * (1 - rng.uniform(0, depth))
        pts.append((r*math.cos(a), r*math.sin(a)))
    return _ccw(pts)


def max_depth(poly):
    """ Radius of the maximum inscribed circle """
    p = Polygon(poly)
    line = shapely.maximum_inscribed_circle(p, tolerance=0.001)
    return line.length


TURN_SETS = [
    # (turns, twists)
    (2, 1), (3, 1), (5, 1), (5, 2), (5, 3), (7, 3), (8, 3), (9, 4), (11, 5), (13, 1), (16, 5), (21, 8),
]


def _valid(turns, twists):
    return gcd(turns, twists) == 1


def base_shapes():
    rng = random.Random(1234)
    shapes = {
        'square40': (rect(40, 40), ['convex']),
        'rect40x20': (rect(40, 20), ['convex']),
        'rect60x12': (rect(60, 12), ['convex', 'thin']),
        'trapezoid': (trapezoid(50, 40, 10), ['convex']),
        'triangle': (regular(3, 40), ['convex', 'sharp']),
        'pentagon': (regular(5, 40), ['convex']),
        'hexagon': (regular(6, 40), ['convex']),
        'octagon': (regular(8, 40), ['convex']),
        '24gon': (regular(24, 40), ['convex', 'many']),
        'ellipse3to1': (ellipse(60, 20), ['convex', 'many']),
        'ellipse3to2': (ellipse(45, 30, 48), ['convex', 'many']),
        'roundrect': (rounded_rect(40, 25, 5), ['convex', 'many']),
        'chamfer_tiny': (chamfered_rect(40, 30, 0.05), ['convex', 'short-edge']),
        'chamfer_small': (chamfered_rect(40, 30, 1.0), ['convex', 'short-edge']),
        'subdiv_rect': (subdivided_rect(40, 30, 0.01, rng), ['convex', 'collinear']),
        'subdiv_rect_jitter': (subdivided_rect(40, 30, 0.3, rng), ['reflex', 'collinear']),
        'star5': (star(5, 50, 25), ['reflex', 'sharp']),
        'star6_shallow': (star(6, 50, 38), ['reflex']),
        'star8': (star(8, 50, 34), ['reflex']),
        'sector45': (sector(50, 25, 45), ['reflex', 'many', 'sharp']),
        'sector90': (sector(60, 20, 90), ['reflex', 'many']),
        'sector180': (sector(60, 30, 180), ['reflex', 'many']),
        'l_shape': (l_shape(40, 40, 15), ['reflex']),
        'u_shape': (u_shape(40, 30, 12), ['reflex']),
        'd_shape': (d_shape(40), ['convex', 'many']),
    }
    for i in range(4):
        shapes[f'rconvex{i}'] = (random_convex(8, 40, rng), ['convex', 'random'])
    for i in range(4):
        shapes[f'rstar{i}'] = (random_starlike(9, 40, rng), ['reflex', 'random'])
    return shapes


def _spec(name, shape, turns, twists, layers=2, clockwise=False, clearance=0.15, trace_width=None, tags=(), **kw):
    d = dict(name=name, shape=shape, turns=turns, twists=twists, layers=layers, clockwise=clockwise,
             clearance=clearance, trace_width=trace_width, tags=list(tags))
    d.update(kw)
    return d


def corpus(kind='full'):
    cases = []

    # Circles (analytic reference)
    for od, id_ in ((50, 25), (30, 6), (20, 18)):
        for turns, twists in TURN_SETS[::2]:
            cases.append(_spec(f'circle{od}x{id_}_n{turns}k{twists}', 'circle', turns, twists,
                               outer_diameter=od, inner_diameter=id_, tags=['circle']))

    shapes = base_shapes()
    fractions = (0.3, 0.6, 0.9)
    for sname, (poly, tags) in shapes.items():
        depth = max_depth(poly)
        for fi, frac in enumerate(fractions):
            for ti, (turns, twists) in enumerate(TURN_SETS):
                # thin out the matrix deterministically to keep the corpus size manageable
                if (ti + fi) % 3 != 0:
                    continue
                cases.append(_spec(f'{sname}_a{frac:.2f}_n{turns}k{twists}', 'polygon', turns, twists,
                                   polygon=poly, annular_width=round(frac*depth, 4), tags=tags + [f'frac{frac}']))
        # single layer and clockwise variants
        cases.append(_spec(f'{sname}_a0.60_n6_1layer', 'polygon', 6, 1, layers=1,
                           polygon=poly, annular_width=round(0.6*depth, 4), tags=tags + ['single-layer']))
        cases.append(_spec(f'{sname}_a0.60_n7k3_cw', 'polygon', 7, 3, clockwise=True,
                           polygon=poly, annular_width=round(0.6*depth, 4), tags=tags + ['clockwise']))

    # Parameter sweeps: small tweaks of the same layout. A robust layout engine should behave smoothly here.
    sweep_bases = ['rect40x20', 'hexagon', 'star8', 'sector90', 'rstar1', 'ellipse3to1', 'chamfer_small']
    for sname in sweep_bases:
        poly, tags = shapes[sname]
        depth = max_depth(poly)
        for k in range(9):
            frac = 0.5 + 0.03*k
            cases.append(_spec(f'sweep_{sname}_a{frac:.3f}_n9k4', 'polygon', 9, 4,
                               polygon=poly, annular_width=round(frac*depth, 4), tags=tags + ['sweep']))
        for k, scale in enumerate((0.97, 0.99, 1.0, 1.01, 1.03)):
            sp = [(x*scale, y*scale) for x, y in poly]
            cases.append(_spec(f'sweep_{sname}_s{scale:.2f}_n7k3', 'polygon', 7, 3,
                               polygon=sp, annular_width=round(0.6*depth, 4), tags=tags + ['sweep']))

    # High turn count / dense cases
    for sname in ['square40', 'octagon', 'star6_shallow', 'roundrect', 'rconvex1']:
        poly, tags = shapes[sname]
        depth = max_depth(poly)
        for turns, twists in ((30, 1), (31, 7)):
            cases.append(_spec(f'dense_{sname}_n{turns}k{twists}', 'polygon', turns, twists,
                               polygon=poly, annular_width=round(0.7*depth, 4), tags=tags + ['dense']))

    assert len({c['name'] for c in cases}) == len(cases)
    if kind == 'quick':
        return cases[::7]
    return cases


if __name__ == '__main__':
    import sys
    cs = corpus(sys.argv[1] if len(sys.argv) > 1 else 'full')
    print(len(cs), 'cases')
