"""Corpus family 'round': round and smooth outlines given as polygons with many vertices.

Polygonal circles (16 to 1024 vertices, plus analytic circles of the same size as the reference), a dense outline like
an SVG import (2500 vertices, and 1000 vertices with coordinates rounded to 1 µm), ellipses, superellipses, smooth random blobs
(low order Fourier radius), a stadium and a rounded rectangle with fine arcs, an egg and a teardrop, a smooth concave
bean, noisy circles (small radial jitter, many tiny alternating convex/reflex corners), polygons whose edges are split
into nearly collinear runs, polygons with very short edges between long ones, and mixed sharp and round outlines (a D
shape with a fine arc, a circle with one sharp tip).

Select with `run_corpus.py --kind round`. All case names start with 'round_'.
"""

import math
import random

from corpus import _ccw, _spec, max_depth, regular, ellipse


def superellipse(a, b, e, n):
    """ |x/a|^e + |y/b|^e = 1 (a, b: full width and height) """
    pts = []
    for i in range(n):
        t = 2*math.pi*i/n
        c, s = math.cos(t), math.sin(t)
        pts.append((a/2*math.copysign(abs(c)**(2/e), c), b/2*math.copysign(abs(s)**(2/e), s)))
    return _ccw(pts)


def fourier_blob(d, n, rng, order=4, amp=0.12):
    """ Star-shaped smooth blob: radius = d/2 * (1 + sum of low order harmonics) """
    coef = [(rng.uniform(-amp, amp) / k, rng.uniform(0, 2*math.pi)) for k in range(2, order+1)]
    pts = []
    for i in range(n):
        t = 2*math.pi*i/n
        r = d/2 * (1 + sum(a*math.cos(k*t + ph) for k, (a, ph) in zip(range(2, order+1), coef)))
        pts.append((r*math.cos(t), r*math.sin(t)))
    return _ccw(pts)


def stadium(w, h, n):
    """ Rectangle w x h with semicircular ends (n segments per semicircle) """
    r = h/2
    pts = []
    for cx, a0 in ((w/2 - r, -90), (-w/2 + r, 90)):
        for i in range(n+1):
            a = math.radians(a0 + 180*i/n)
            pts.append((cx + r*math.cos(a), r*math.sin(a)))
    return _ccw(pts)


def rounded_rect_fine(w, h, r, n):
    pts = []
    for cx, cy, a0 in ((w/2-r, h/2-r, 0), (-w/2+r, h/2-r, 90), (-w/2+r, -h/2+r, 180), (w/2-r, -h/2+r, 270)):
        for i in range(n+1):
            a = math.radians(a0 + 90*i/n)
            pts.append((cx + r*math.cos(a), cy + r*math.sin(a)))
    return _ccw(pts)


def egg(d, n, k=0.18):
    """ Egg: ellipse-like curve with one end blunter than the other """
    pts = []
    for i in range(n):
        t = 2*math.pi*i/n
        x = d/2 * math.cos(t)
        y = d/2 * 0.75 * math.sin(t) * (1 + k*math.cos(t))
        pts.append((x, y))
    return _centered(pts)


def teardrop(d, n):
    """ Circle of diameter d with a sharp tip: two tangent lines from a point 1.6 r from the center """
    r = d/2
    tip = 1.6*r
    a0 = math.acos(r/tip) # tangent points at +-a0 from the tip direction
    pts = [(tip, 0.0)]
    for i in range(n+1):
        a = a0 + (2*math.pi - 2*a0) * i/n
        pts.append((r*math.cos(a), r*math.sin(a)))
    return _centered(pts)


def bean(d, n):
    """ Smooth concave kidney: circle with a smooth dent on one side """
    pts = []
    for i in range(n):
        t = 2*math.pi*i/n
        r = d/2 * (1 - 0.28*math.exp(-((math.atan2(math.sin(t - math.pi/2), math.cos(t - math.pi/2)))/0.55)**2))
        pts.append((1.25*r*math.cos(t), 0.8*r*math.sin(t)))
    return _centered(pts)


def noisy_circle(d, n, jitter, rng):
    """ Polygonal circle with radial jitter: many tiny alternating convex and reflex corners """
    pts = []
    for i in range(n):
        t = 2*math.pi*i/n
        r = d/2 + rng.uniform(-jitter, jitter)
        pts.append((r*math.cos(t), r*math.sin(t)))
    return _ccw(pts)


def collinear_runs(d, n, sub, jitter, rng):
    """ Regular n-gon whose edges are split into `sub` pieces with tiny perpendicular jitter (nearly collinear runs) """
    base = regular(n, d)
    pts = []
    for (x1, y1), (x2, y2) in zip(base, base[1:] + base[:1]):
        nx, ny = -(y2-y1), (x2-x1)
        ln = math.hypot(nx, ny)
        for k in range(sub):
            t = k/sub
            j = rng.uniform(-jitter, jitter) if k else 0.0
            pts.append((x1 + t*(x2-x1) + j*nx/ln, y1 + t*(y2-y1) + j*ny/ln))
    return _ccw(pts)


def short_edge_polygon(d, n, short):
    """ Regular n-gon with every corner cut by a very short edge (alternating long and very short edges) """
    base = regular(n, d)
    pts = []
    m = len(base)
    for i in range(m):
        p0, p1, p2 = base[i-1], base[i], base[(i+1) % m]
        for q in (p0, p2):
            l = math.dist(p1, q)
            pts.append((p1[0] + (q[0]-p1[0])*short/2/l, p1[1] + (q[1]-p1[1])*short/2/l))
    return _ccw(pts)


def d_shape_fine(d, n):
    r = d/2
    pts = [(r*math.cos(math.pi/2 - math.pi*i/n), r*math.sin(math.pi/2 - math.pi*i/n)) for i in range(n+1)]
    pts += [(-r*0.3, -r), (-r*0.3, r)]
    return _centered(pts)


def circle_tip(d, n, tip=1.25):
    """ Polygonal circle with one vertex pulled outward into a sharp spike """
    pts = [(d/2*math.cos(2*math.pi*i/n), d/2*math.sin(2*math.pi*i/n)) for i in range(n)]
    pts[0] = (d/2*tip, 0.0)
    return _ccw(pts)


def _centered(pts):
    from shapely.geometry import Polygon
    c = Polygon(pts).centroid
    return _ccw([(x-c.x, y-c.y) for x, y in pts])


def svg_like(d, n, rng):
    """ Dense outline as an SVG import produces it: a smooth blob flattened into n points, coordinates rounded to 1 µm """
    pts = fourier_blob(d, n, rng, order=5, amp=0.15)
    out = []
    for x, y in pts:
        q = (round(x, 3), round(y, 3))
        if not out or q != out[-1]:
            out.append(q)
    if out[-1] == out[0]:
        out.pop()
    return _ccw(out)


def shapes():
    rng = random.Random(4242)
    return {
        'poly16': (regular(16, 40), ['convex', 'polycircle']),
        'poly64': (regular(64, 40), ['convex', 'polycircle']),
        'poly256': (regular(256, 40), ['convex', 'polycircle']),
        'poly1024': (regular(1024, 40), ['convex', 'polycircle', 'huge']),
        'dense2500': (fourier_blob(40, 2500, rng, order=5, amp=0.15), ['convex', 'huge', 'smooth']),
        'ellipse2to1': (ellipse(50, 25, 256), ['convex', 'smooth']),
        'ellipse3to1': (ellipse(60, 20, 512), ['convex', 'smooth']),
        'squircle': (superellipse(40, 40, 4, 256), ['convex', 'smooth']),
        'superell': (superellipse(50, 30, 2.5, 200), ['convex', 'smooth']),
        'blob1': (fourier_blob(40, 200, rng), ['smooth', 'random']),
        'blob2': (fourier_blob(40, 200, rng, order=3, amp=0.2), ['smooth', 'random']),
        'stadium': (stadium(50, 24, 64), ['convex', 'smooth', 'mixed']),
        'roundrect': (rounded_rect_fine(40, 28, 8, 32), ['convex', 'smooth', 'mixed']),
        'egg': (egg(40, 200), ['convex', 'smooth']),
        'teardrop': (teardrop(36, 160), ['convex', 'mixed', 'sharp']),
        'bean': (bean(40, 240), ['reflex', 'smooth']),
        'noisy_s': (noisy_circle(40, 256, 0.02, rng), ['reflex', 'noisy']),
        'noisy_l': (noisy_circle(40, 256, 0.2, rng), ['reflex', 'noisy']),
        'collinear': (collinear_runs(40, 24, 8, 1e-4, rng), ['reflex', 'collinear']),
        'shortedge': (short_edge_polygon(40, 24, 0.02), ['convex', 'short-edge']),
        'dshape': (d_shape_fine(40, 128), ['convex', 'mixed', 'sharp']),
        'tip': (circle_tip(36, 128), ['reflex', 'mixed', 'sharp']),
    }


TURNS = [(5, 1), (8, 3), (16, 5), (21, 8)]
FRACTIONS = (0.3, 0.6, 0.9)


def cases():
    out = []
    for si, (sname, (poly, tags)) in enumerate(shapes().items()):
        depth = max_depth(poly)
        tags = tags + ['round']
        huge = 'huge' in tags
        for fi, frac in enumerate(FRACTIONS):
            for ti, (turns, twists) in enumerate(TURNS):
                # Half of the matrix (a quarter for the huge outlines, which are slow for every implementation)
                if (ti + fi) % (4 if huge else 2) != 0:
                    continue
                out.append(_spec(f'round_{sname}_a{frac:.2f}_n{turns}k{twists}', 'polygon', turns, twists,
                                 polygon=poly, annular_width=round(frac*depth, 4), tags=tags + [f'frac{frac}']))
        # Single layer and clockwise variants, alternating between shapes
        if huge:
            pass
        elif si % 2 == 0:
            out.append(_spec(f'round_{sname}_a0.60_n6_1layer', 'polygon', 6, 1, layers=1,
                             polygon=poly, annular_width=round(0.6*depth, 4), tags=tags + ['single-layer']))
        else:
            out.append(_spec(f'round_{sname}_a0.60_n7k3_cw', 'polygon', 7, 3, clockwise=True,
                             polygon=poly, annular_width=round(0.6*depth, 4), tags=tags + ['clockwise']))

    # Dense outline with coordinates rounded to 1 µm, as imported from a file with 3 decimals: the rounding noise turns
    # about 15 % of the vertices into tiny reflex corners, which makes the straight skeleton slow (and with 3000 such
    # vertices, it runs out of memory). One case only.
    poly = svg_like(40, 1000, random.Random(4243))
    out.append(_spec('round_svg1000r_a0.60_n8k3', 'polygon', 8, 3, polygon=poly,
                     annular_width=round(0.6*max_depth(poly), 4), tags=['round', 'huge', 'noisy', 'rounded']))

    # Analytic reference for the polygonal circles: CircleShape with the circumscribed diameter (40) and the annular
    # width the polygon cases use for poly1024 (the inscribed radius of the n-gons differs by at most 2 % at n=16)
    depth = max_depth(regular(1024, 40))
    for fi, frac in enumerate(FRACTIONS):
        for ti, (turns, twists) in enumerate(TURNS):
            if (ti + fi) % 2 != 0:
                continue
            aw = round(frac*depth, 4)
            out.append(_spec(f'round_circleref_a{frac:.2f}_n{turns}k{twists}', 'circle', turns, twists,
                             outer_diameter=40.0, inner_diameter=round(40.0 - 2*aw, 4), tags=['circle', 'round']))
    return out


if __name__ == '__main__':
    cs = cases()
    print(len(cs), 'cases')
    for name, (poly, tags) in shapes().items():
        print(f'{name:12s} {len(poly):5d} vertices  max depth {max_depth(poly):.3f}')
