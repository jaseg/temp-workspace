"""Concave (non-convex) design targets: a plush-shark silhouette (as a polygon and as an SVG file loaded through
`geometry.SVGShape`), bean, heart, crescent, C, rounded L and U, cross, comb, star with rounded tips and a dumbbell.

For a non-convex outline the straight skeleton's first split event (`Skeletonator.max_depth`) limits the annular
width, often far below the maximum inscribed radius. Annular widths are therefore absolute, chosen as fractions of
each shape's split depth (`split_depth()`), not of the inscribed radius as in the main corpus.

`cases()` is picked up by tests/corpus.py (family 'concave').
"""

import math
from functools import lru_cache
from pathlib import Path

import shapely
from shapely.geometry import Polygon, Point, box
from shapely import affinity

DATA_DIR = Path(__file__).parent / 'data'
SHARK_SVG = DATA_DIR / 'shark.svg'


def _ccw_coords(geom, simplify=0.0):
    if simplify:
        geom = geom.simplify(simplify, preserve_topology=True)
    if not isinstance(geom, Polygon):
        geom = max(geom.geoms, key=lambda g: g.area)
    g = shapely.geometry.polygon.orient(Polygon(geom.exterior), 1.0)
    pts = [(round(float(x), 4), round(float(y), 4)) for x, y in g.exterior.coords[:-1]]
    return pts


def _centered(geom):
    c = geom.centroid
    return affinity.translate(geom, -c.x, -c.y)


def _smooth_curve(pts, n=8):
    """ Quadratic B-spline through the control points pts (open), n samples per span; keeps the end points """
    out = [pts[0]]
    mids = [pts[0]] + [((a[0]+b[0])/2, (a[1]+b[1])/2) for a, b in zip(pts[1:-2], pts[2:-1])] + [pts[-1]]
    for i in range(len(pts) - 2):
        p0, p1, p2 = mids[i], pts[i+1], mids[i+1]
        for k in range(1, n+1):
            t = k/n
            out.append(((1-t)**2*p0[0] + 2*(1-t)*t*p1[0] + t**2*p2[0],
                        (1-t)**2*p0[1] + 2*(1-t)*t*p1[1] + t**2*p2[1]))
    return out


def shark():
    """ Generic plush-shark side view, about 90 mm long (x), snout at +x, y up. Plump elongated body with a rounded
    snout and a slightly flat belly, a swept-back dorsal fin, two pectoral fins below the body, and a forked tail with a
    longer upper lobe. """
    # Body: smooth outline from the tail peduncle over the back to the snout and back along the belly
    body_ctrl = [(-30, 4.0), (-22, 7.5), (-8, 11.5), (8, 13.0), (24, 11.5), (35, 8.0), (41.5, 3.0), (42, -2.0),
                 (37, -7.0), (26, -10.5), (8, -11.5), (-10, -9.5), (-22, -6.5), (-30, -4.0)]
    body = Polygon(_smooth_curve(body_ctrl, 8) + [(-34, -3.8), (-34, 3.8)])
    # Dorsal fin, swept back, with a curved leading edge and a concave trailing edge
    dorsal = Polygon(_smooth_curve([(12, 11.0), (5, 16.0), (-2, 22.0), (-4.5, 23.0)], 8) +
                     _smooth_curve([(-4.5, 23.0), (-3.5, 18.0), (-2, 14.0), (-7, 9.5)], 8)[1:])
    # Pectoral fins below the body, pointing down and back
    pect1 = Polygon(_smooth_curve([(23, -9.0), (17, -15.0), (10, -21.0), (7.5, -21.5)], 7) +
                    _smooth_curve([(7.5, -21.5), (8.5, -17.0), (10.5, -13.0), (11, -9.0)], 7)[1:])
    pect2 = Polygon(_smooth_curve([(5, -10.0), (1, -14.0), (-4, -17.5), (-6, -17.8)], 6) +
                    _smooth_curve([(-6, -17.8), (-5, -14.0), (-3, -11.0), (-3.5, -8.0)], 6)[1:])
    # Forked tail: upper lobe (longer), lower lobe, notch in between
    tail = Polygon([(-31, 4.2)] + _smooth_curve([(-33, 4.5), (-40, 10.0), (-46, 17.0), (-48.5, 18.5)], 7)[1:] +
                   _smooth_curve([(-48.5, 18.5), (-47, 10.0), (-44, 4.0), (-42, 1.0)], 7)[1:] +
                   _smooth_curve([(-42, 1.0), (-44, -3.0), (-46.5, -8.5), (-47.5, -11.0)], 7)[1:] +
                   _smooth_curve([(-47.5, -11.0), (-42, -8.0), (-36, -5.0), (-31, -4.2)], 7)[1:])
    geom = shapely.union_all([body, dorsal, pect1, pect2, tail]).buffer(0.3, quad_segs=3).buffer(-0.3, quad_segs=3)
    return _ccw_coords(_centered(geom), simplify=0.06)


def shark_svg_path_d(pts, margin=5.0, reverse=False):
    """ SVG path data of the outline in SVG coordinates (y down, all coordinates positive, so the shark appears upright
    in an SVG viewer), repeating the start point, in the dialect the original SVGShape read ("M x y,x y,...,x y Z" with
    commas between points; kicoil.svg_import reads all path syntax, test_svg_import.py tests the others).

    SVGShape takes the file's numbers as they are (KiCad's y axis points down, too) and reverses the point order when
    their shoelace area is negative (`polygon_is_clockwise`). `pts` is counter-clockwise with y up; mirroring y flips the
    sign of the shoelace area, so the default path is clockwise in its own numbers (negative shoelace area, which
    appears counter-clockwise on screen) and SVGShape has to reorient it. `reverse=True` gives the other order. """
    xs = [x for x, _y in pts]
    ys = [y for _x, y in pts]
    x0, y1 = min(xs) - margin, max(ys) + margin
    svg_pts = [(x - x0, y1 - y) for x, y in pts]
    if reverse:
        svg_pts = svg_pts[::-1]
    svg_pts.append(svg_pts[0])
    return 'M ' + ','.join(f'{x:.4f} {y:.4f}' for x, y in svg_pts) + ' Z', (max(xs) - x0 + margin, y1 - min(ys) + margin)


def write_shark_svg(path=SHARK_SVG, reverse=False):
    d, (w, h) = shark_svg_path_d(shark(), reverse=reverse)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n'
                    f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.2f}mm" height="{h:.2f}mm" '
                    f'viewBox="0 0 {w:.4f} {h:.4f}">\n'
                    f'  <path fill="#7da7d9" stroke="none" d="{d}"/>\n</svg>\n')


def bean(w=44, h=28, n=72):
    """ Kidney bean: an ellipse with a smooth dent in the middle of its top side """
    pts = []
    for i in range(n):
        a = 2*math.pi*i/n
        x, y = w/2*math.cos(a), h/2*math.sin(a)
        y -= 0.42*h * math.exp(-(x/(0.22*w))**2) * max(0.0, math.sin(a))**2
        pts.append((x, y))
    return _ccw_coords(_centered(Polygon(pts)))


def heart(size=44, n=80):
    """ Classic parametric heart: reflex cusp at the top, sharp tip at the bottom """
    pts = []
    for i in range(n):
        t = 2*math.pi*i/n
        pts.append((16*math.sin(t)**3, 13*math.cos(t) - 5*math.cos(2*t) - 2*math.cos(3*t) - math.cos(4*t)))
    g = Polygon(pts)
    s = size / (g.bounds[2] - g.bounds[0])
    return _ccw_coords(_centered(affinity.scale(g, s, s, origin=(0, 0))))


def crescent(r1=22, r2=17, off=10):
    """ Moon crescent: a disk minus an offset disk. Two sharp tips. """
    g = Point(0, 0).buffer(r1, quad_segs=24).difference(Point(off, 0).buffer(r2, quad_segs=24))
    return _ccw_coords(_centered(g), simplify=0.02)


def c_shape(ro=22, ri=12, gap_deg=70):
    """ Thick C: an annulus with a gap, rounded ends """
    ring = Point(0, 0).buffer(ro, quad_segs=24).difference(Point(0, 0).buffer(ri, quad_segs=24))
    a = math.radians(gap_deg/2)
    wedge = Polygon([(0, 0), (2*ro*math.cos(a), 2*ro*math.sin(a)), (2*ro, 0), (2*ro*math.cos(a), -2*ro*math.sin(a))])
    g = ring.difference(wedge)
    t = (ro - ri)/2
    for s in (1, -1):
        g = g.union(Point((ri+t)*math.cos(a), s*(ri+t)*math.sin(a)).buffer(t, quad_segs=8))
    return _ccw_coords(_centered(g), simplify=0.02)


def _round(g, r_convex, r_reflex, q=4):
    """ Round convex corners with an opening and reflex corners with a closing """
    if r_convex:
        g = g.buffer(-r_convex, join_style='mitre').buffer(r_convex, quad_segs=q)
    if r_reflex:
        g = g.buffer(r_reflex, quad_segs=q).buffer(-r_reflex, join_style='mitre')
    return g


def rounded_l(w=44, h=44, t=16, r=4):
    g = Polygon([(0, 0), (w, 0), (w, t), (t, t), (t, h), (0, h)])
    return _ccw_coords(_centered(_round(g, r, r)), simplify=0.01)


def rounded_u(w=44, h=36, t=13, r=4):
    g = Polygon([(0, 0), (w, 0), (w, h), (w-t, h), (w-t, t), (t, t), (t, h), (0, h)])
    return _ccw_coords(_centered(_round(g, r, r)), simplify=0.01)


def cross(span=44, arm=14, r=2.5):
    g = box(-span/2, -arm/2, span/2, arm/2).union(box(-arm/2, -span/2, arm/2, span/2))
    return _ccw_coords(_round(g, r, r), simplify=0.01)


def comb(w=44, base=12, teeth=4, tooth_w=5, tooth_l=14):
    """ Bar with teeth sticking out on one side. The teeth's sides collapse at depth tooth_w/2. """
    g = box(-w/2, 0, w/2, base)
    pitch = w / teeth
    for i in range(teeth):
        cx = -w/2 + pitch*(i + 0.5)
        g = g.union(box(cx - tooth_w/2, base - 0.01, cx + tooth_w/2, base + tooth_l))
    return _ccw_coords(_centered(_round(g, 1.0, 0)), simplify=0.01)


def rounded_star(n=5, od=50, id_=26, r=3):
    pts = []
    for i in range(n):
        for rr, ph in ((od/2, 0), (id_/2, 0.5)):
            a = 2*math.pi*(i+ph)/n
            pts.append((-rr*math.sin(a), rr*math.cos(a)))
    return _ccw_coords(_round(Polygon(pts), r, 0), simplify=0.01)


def dumbbell(r=12, sep=34, neck=9):
    g = Point(-sep/2, 0).buffer(r, quad_segs=12).union(Point(sep/2, 0).buffer(r, quad_segs=12))
    g = g.union(box(-sep/2, -neck/2, sep/2, neck/2))
    return _ccw_coords(_round(g, 0, 3), simplify=0.01)


def shapes():
    """ name -> (polygon, tags) """
    return {
        'shark': (shark(), ['reflex', 'shark', 'many']),
        'bean': (bean(), ['reflex', 'many']),
        'heart': (heart(), ['reflex', 'many', 'sharp']),
        'crescent': (crescent(), ['reflex', 'many', 'sharp']),
        'cshape': (c_shape(), ['reflex', 'many']),
        'lround': (rounded_l(), ['reflex', 'many']),
        'uround': (rounded_u(), ['reflex', 'many']),
        'cross': (cross(), ['reflex', 'many']),
        'comb': (comb(), ['reflex', 'narrow']),
        'starround': (rounded_star(), ['reflex', 'many']),
        'dumbbell': (dumbbell(), ['reflex', 'many', 'neck']),
    }


@lru_cache(maxsize=None)
def _split_depth(poly):
    from kicoil import skeletonator
    return skeletonator.Skeletonator(list(poly)).max_depth


def split_depth(poly):
    """ Depth of the straight skeleton's first split event (= the largest annular width the layout accepts) """
    return _split_depth(tuple(map(tuple, poly)))


def inscribed_radius(poly):
    return shapely.maximum_inscribed_circle(Polygon(poly), tolerance=0.001).length


FRACTIONS = (0.3, 0.6, 0.9)
THIN_TRACE = 0.1 # mm
TURNS = ((5, 1), (8, 3), (13, 4))  # (12, 4) is not co-prime


def _spec(name, shape, turns, twists, layers=2, clockwise=False, clearance=0.15, tags=(), **kw):
    d = dict(name=name, shape=shape, turns=turns, twists=twists, layers=layers, clockwise=clockwise,
             clearance=clearance, trace_width=None, tags=list(tags))
    d.update(kw)
    return d


# Known limitations of the straight-skeleton layout (kicoil.geometry) for some outlines. test_layout.py xfails a case of
# such an outline only when every failure kind of the checker is among the listed ones ('overshoot': copper deeper than
# the intended annulus; 'contour': the outer turn stays more than 1.5 mm from the outline somewhere).
KNOWN_ISSUES = {
    'heart': dict(
        kinds=('backtrack', 'overshoot', 'contour', 'via offset', 'clearance', 'via clearance', 'self merge'),
        reason='sharp reflex cusp: its mitered offset vertex moves at 1/sin(theta/2) per unit depth, so every turn runs '
               'into a zero-width spike deep inside the outline and back (backtracks, copper far deeper than the '
               'annular width, the copper of the spike merging) and the skeleton splits at 1.6 mm of 11.5 mm '
               'inscribed radius'),
}


# The same for single cases
CASE_ISSUES = {
    # Sharp convex tips (the crescent's horns, the shark's tail lobes) that the outer turn of the linear spiral does not
    # reach; in the single-layer shark only with the start vertex of the SVG import, which puts the arm start there.
    **{name: dict(kinds=('contour',), reason='outer turn does not reach a sharp convex tip')
       for name in ('concave_crescent_a0.3_n13k4', 'concave_crescent_a0.6_n13k4', 'concave_sharksvg_a0.6_n6_1layer')},
}


def _variants(prefix, base, tags, depth):
    out = []
    for frac in FRACTIONS:
        aw = round(frac*depth, 4)
        for turns, twists in TURNS:
            out.append(_spec(f'{prefix}_a{frac:.1f}_n{turns}k{twists}', turns=turns, twists=twists,
                             annular_width=aw, tags=tags + [f'frac{frac}'], **base))
    aw = round(0.6*depth, 4)
    out.append(_spec(f'{prefix}_a0.6_n6_1layer', turns=6, twists=1, layers=1, annular_width=aw,
                     tags=tags + ['single-layer'], **base))
    out.append(_spec(f'{prefix}_a0.6_n7k3_cw', turns=7, twists=3, clockwise=True, annular_width=aw,
                     tags=tags + ['clockwise'], **base))
    return out


def cases():
    out = []
    for name, (poly, tags) in shapes().items():
        depth = split_depth(poly)
        base = dict(shape='polygon', polygon=poly)
        if name in KNOWN_ISSUES:
            base['known_issue'] = KNOWN_ISSUES[name]
        out += _variants(f'concave_{name}', base, tags + ['concave'], depth)
        if name == 'shark':
            # The same outline through the SVG import (path clockwise in its own numbers, i.e. reoriented by SVGShape,
            # repeating its start point, y down)
            out += _variants('concave_sharksvg', dict(shape='svg', svg_file=str(SHARK_SVG.relative_to(DATA_DIR.parent))),
                             tags + ['concave', 'svg'], depth)
    for c in out:
        # Nominal trace width (pitch minus clearance) below 0.1 mm: not manufacturable on a usual PCB process. These cases
        # stay in the family (robustness and rejection of infeasible requests) but are left out of headline statistics.
        if c['annular_width'] * c['layers'] / c['turns'] - c['clearance'] < THIN_TRACE:
            c['tags'].append('thin')
        if c['name'] in CASE_ISSUES:
            assert 'known_issue' not in c
            c['known_issue'] = CASE_ISSUES[c['name']]
    assert set(CASE_ISSUES) <= {c['name'] for c in out}
    return out


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['write-svg']:
        write_shark_svg()
    for name, (poly, _tags) in shapes().items():
        d, ri = split_depth(poly), inscribed_radius(poly)
        print(f'{name:10s} {len(poly):4d} pts  split depth {d:6.3f}  inscribed radius {ri:6.3f}  ratio {d/ri:.3f}')
    print(len(cases()), 'cases')
