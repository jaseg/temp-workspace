"""SVG outline import (kicoil.svg_import, geometry.SVGShape): path dialects, curves, transforms, shapes, units, the
choice of the outline among several contours, and rejection of open or self-intersecting outlines."""

import ast
import math
import re
import warnings
from pathlib import Path

import pytest
from shapely.geometry import Polygon

import corpus_concave
import geomcheck
from kicoil import geometry, svg_import
from test_layout import layout

SVG_NS = 'xmlns="http://www.w3.org/2000/svg"'
RECT = [(0, 0), (30, 0), (30, 20), (0, 20)]


def write(tmp_path, body, root_attrs='', name='t.svg'):
    f = tmp_path / name
    f.write_text(f'<svg {SVG_NS} {root_attrs}>{body}</svg>')
    return f


def outline(tmp_path, body, root_attrs='', tol=0.002, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return svg_import.read_outline(write(tmp_path, body, root_attrs), tol, **kw)


def same_polygon(pts, ref, tol=1e-9):
    """ Same vertex cycle (any start, either orientation), within tol """
    if len(pts) != len(ref):
        return False
    for seq in (pts, pts[::-1]):
        for k in range(len(seq)):
            if all(math.dist(seq[(i + k) % len(seq)], r) <= tol for i, r in enumerate(ref)):
                return True
    return False


# Path data dialects for the same 30 x 20 rectangle
@pytest.mark.parametrize('d', [
    'M0 0 L30 0 L30 20 L0 20 Z',                     # explicit L
    'M0 0 H30 V20 H0 Z',                             # H/V
    'M0 0 L30 0 L30 20 L0 20 z',                     # lower case z
    'm0 0 l30 0 l0 20 l-30 0 z',                     # relative l
    'M 0,0 L 30,0 L 30,20 L 0,20 Z',                 # x,y commas (the most common form)
    'M 0 0 30 0 30 20 0 20 Z',                       # implicit lineto after M, space separated pairs
    'M 0 0,30 0,30 20,0 20 Z',                       # implicit lineto, comma separated pairs (shark fixture)
    'M0 0 L30 0 L30 20 L0 20 L0 0',                  # no Z, ends on its start point
    'M0 0 L30 0 30 20 0 20Z',                        # implicit repeated L
    'm0,0 30,0 0,20 -30,0z',                         # implicit relative lineto after m
    'M0 0h30v20h-30z',                               # relative h/v without spaces
    'M0,0L3e1,0L30,2E+1L0,20e0Z',                    # exponents
    'M0-0L30-0L30 20L-0 20Z',                        # "-" as separator
    'M0 0 L30 0 L30 20 L0 20 Z M 0 0',               # trailing lone moveto
    '\n  M 0 0\n  L 30 0\n  L 30 20\n  L 0 20\n  Z\n',  # newlines (KiCad)
])
def test_path_dialects(tmp_path, d):
    assert same_polygon(outline(tmp_path, f'<path d="{d}"/>'), RECT)


def test_dot_separator(tmp_path):
    # ".5.5" is two numbers, 0.5 and 0.5
    pts = outline(tmp_path, '<path d="M.5.5H30.5V20.5H.5Z"/>')
    assert same_polygon(pts, [(x + .5, y + .5) for x, y in RECT])


def test_subpath_after_z_starts_at_the_start_point(tmp_path):
    # After Z the current point is the subpath start, relative commands continue from there
    pts = outline(tmp_path, '<path d="M5 5 l1 0 l0 1 z l30 0 l0 20 l-30 0 z"/>')
    assert same_polygon(pts, [(x + 5, y + 5) for x, y in RECT])


@pytest.mark.parametrize('d', ['M0 0 L30', 'L0 0 30 0 30 20Z', 'M0 0 X30 0', 'M0 0 Z 5', 'M0 0 A1 1 0 2 0 3 3 Z'])
def test_invalid_path_data(tmp_path, d):
    with pytest.raises(ValueError, match='invalid path data'):
        outline(tmp_path, f'<path id="p1" d="{d}"/>')


def _max_deviation(pts, curve, n=4000):
    """ Largest distance of the dense curve samples from the closed polyline """
    poly = Polygon(pts).exterior
    from shapely.geometry import Point
    return max(poly.distance(Point(curve(i/n))) for i in range(n))


@pytest.mark.parametrize('tol', [0.001, 0.005])
def test_arcs_are_flattened_within_tolerance(tmp_path, tol):
    # A circle from two arcs
    pts = outline(tmp_path, '<path d="M10 0A10 10 0 1 1 -10 0A10 10 0 1 1 10 0Z"/>', tol=tol)
    dev = _max_deviation(pts, lambda t: (10*math.cos(2*math.pi*t), 10*math.sin(2*math.pi*t)))
    assert tol/4 < dev <= tol * 1.01
    assert all(abs(math.hypot(*p) - 10) < 1e-9 for p in pts)
    # Vertex density: about what a regular polygon with that sagitta needs
    assert len(pts) <= 1.1 * math.pi / math.acos(1 - tol/10) + 4


def test_compact_arc_flags(tmp_path):
    # "a10 10 0 0110 0": flags 0 and 1 without separators, then x = 10
    a = outline(tmp_path, '<path d="M0 0 h20 v10 a10 10 0 0110 0 v10 h-30 z"/>')
    b = outline(tmp_path, '<path d="M0 0 h20 v10 a10 10 0 0 1 10 0 v10 h-30 z"/>')
    assert a == b and len(a) > 10


def test_arc_radii_scaled_up_and_degenerate_arcs(tmp_path):
    # Radii too small for the end points are scaled up (a half circle), zero radii are a straight line
    pts = outline(tmp_path, '<path d="M0 0 A1 1 0 0 0 20 0 A0 5 0 0 0 0 0 Z"/>')
    assert abs(Polygon(pts).area - math.pi*100/2) < 0.05
    assert max(math.dist(p, (10, 0)) for p in pts) < 10 + 1e-9


def _bezier(ctrl):
    def f(t):
        n = len(ctrl) - 1
        x = y = 0.0
        for i, (px, py) in enumerate(ctrl):
            b = math.comb(n, i) * t**i * (1-t)**(n-i)
            x, y = x + b*px, y + b*py
        return x, y
    return f


def test_cubic_and_quadratic_flattened_within_tolerance(tmp_path):
    tol = 0.002
    ctrl = [(0, 0), (5, 30), (25, -20), (30, 10)]
    pts = outline(tmp_path, '<path d="M0 0 C5 30 25 -20 30 10 L30 40 L0 40 Z"/>', tol=tol)
    n = 4000
    curve = Polygon(pts).exterior
    from shapely.geometry import Point
    assert max(curve.distance(Point(_bezier(ctrl)(i/n))) for i in range(n + 1)) <= tol
    assert len(pts) < 200
    ctrl = [(0, 0), (15, 30), (30, 0)]
    pts = outline(tmp_path, '<path d="M0 0 Q15 30 30 0 Z"/>', tol=tol)
    curve = Polygon(pts).exterior
    assert max(curve.distance(Point(_bezier(ctrl)(i/n))) for i in range(n + 1)) <= tol


def test_smooth_curves_reflect_the_control_point(tmp_path):
    s = outline(tmp_path, '<path d="M0 0 C0 10 10 10 10 0 S20 -10 20 0 L20 20 L0 20 Z"/>')
    c = outline(tmp_path, '<path d="M0 0 C0 10 10 10 10 0 C10 -10 20 -10 20 0 L20 20 L0 20 Z"/>')
    assert s == c
    s = outline(tmp_path, '<path d="M0 0 Q5 10 10 0 T20 0 L20 20 L0 20 Z"/>')
    q = outline(tmp_path, '<path d="M0 0 Q5 10 10 0 Q15 -10 20 0 L20 20 L0 20 Z"/>')
    assert s == q
    # S after a non-curve command uses the current point as first control point, relative s and t too
    s = outline(tmp_path, '<path d="M0 0 L5 0 s5 10 10 0 t10 0 L20 20 L0 20 Z"/>')
    c = outline(tmp_path, '<path d="M0 0 L5 0 C5 0 10 10 15 0 Q15 0 25 0 L20 20 L0 20 Z"/>')
    assert s == c


def test_flattening_tolerance_is_in_mm_after_transforms(tmp_path):
    # The same circle drawn at 1/10 scale and scaled up by a group transform gets the same vertex count
    a = outline(tmp_path, '<path d="M10 0A10 10 0 1 1 -10 0A10 10 0 1 1 10 0Z"/>')
    b = outline(tmp_path, '<g transform="scale(10)"><path d="M1 0A1 1 0 1 1 -1 0A1 1 0 1 1 1 0Z"/></g>')
    assert len(a) == len(b)
    assert max(math.dist(p, q) for p, q in zip(a, b)) < 1e-9


@pytest.mark.parametrize('transform, expect', [
    ('scale(2)', lambda x, y: (2*x, 2*y)),
    ('scale(2, 3)', lambda x, y: (2*x, 3*y)),
    ('translate(5)', lambda x, y: (x + 5, y)),
    ('translate(5,-7)', lambda x, y: (x + 5, y - 7)),
    ('matrix(1 0 0 1 5 6)', lambda x, y: (x + 5, y + 6)),
    ('matrix(0,1,-1,0,0,0)', lambda x, y: (-y, x)),
    ('rotate(90)', lambda x, y: (-y, x)),
    ('rotate(90 15 10)', lambda x, y: (15 - (y - 10), 10 + (x - 15))),
    ('skewX(45)', lambda x, y: (x + y, y)),
    ('skewY(45)', lambda x, y: (x, y + x)),
    ('translate(10,0) scale(2)', lambda x, y: (2*x + 10, 2*y)),  # scale is applied first
    ('scale(2),translate(10,0)', lambda x, y: (2*x + 20, 2*y)),
])
def test_transforms(tmp_path, transform, expect):
    for body in (f'<path transform="{transform}" d="M0 0 H30 V20 H0 Z"/>',
                 f'<g transform="{transform}"><path d="M0 0 H30 V20 H0 Z"/></g>'):
        assert same_polygon(outline(tmp_path, body), [expect(x, y) for x, y in RECT], 1e-9)


def test_nested_group_transforms(tmp_path):
    # The group_transform.svg case: imported as 30 x 20 before, ignoring the group's scale
    pts = outline(tmp_path, '<g transform="translate(10,0)"><g transform="scale(2)">'
                            '<path transform="translate(1,1)" d="M0 0 L30 0 L30 20 L0 20 Z"/></g></g>')
    assert same_polygon(pts, [(2*(x + 1) + 10, 2*(y + 1)) for x, y in RECT])


@pytest.mark.parametrize('body, ref', [
    ('<polygon points="0,0 30,0 30,20 0,20"/>', RECT),
    ('<polygon points="0 0 30 0 30 20 0 20 7"/>', RECT),  # odd count: the last number is dropped
    ('<polyline points="0,0 30,0 30,20 0,20 0,0"/>', RECT),  # a polyline that ends on its start point is closed
    ('<rect width="30" height="20"/>', RECT),
    ('<rect x="5" y="5" width="30" height="20"/>', [(x + 5, y + 5) for x, y in RECT]),
])
def test_shape_elements(tmp_path, body, ref):
    assert same_polygon(outline(tmp_path, body), ref)


def test_curved_shape_elements(tmp_path):
    tol = 0.002
    pts = outline(tmp_path, '<circle cx="5" cy="-3" r="12"/>')
    assert all(abs(math.dist(p, (5, -3)) - 12) < 1e-9 for p in pts)
    assert abs(Polygon(pts).area - math.pi*144) < 2*math.pi*12*tol
    pts = outline(tmp_path, '<ellipse cx="0" cy="0" rx="20" ry="8"/>')
    assert all(abs((x/20)**2 + (y/8)**2 - 1) < 1e-9 for x, y in pts)
    assert abs(Polygon(pts).area - math.pi*160) < 2*math.pi*20*tol
    # Rounded rectangle; ry defaults to rx
    pts = outline(tmp_path, '<rect width="30" height="20" rx="4"/>')
    assert abs(Polygon(pts).area - (600 - (4 - math.pi)*16)) < 0.05
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    assert (min(xs), max(xs), min(ys), max(ys)) == (0, 30, 0, 20)
    # rx larger than half the width is clamped: a stadium
    pts = outline(tmp_path, '<rect width="30" height="20" rx="50" ry="10"/>')
    assert abs(Polygon(pts).area - (600 - (4 - math.pi)*150)) < 0.1


def test_use_element(tmp_path):
    body = ('<defs><path id="r" d="M0 0 H30 V20 H0 Z"/></defs>'
            '<use xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="#r" x="5" y="1" transform="scale(2)"/>')
    assert same_polygon(outline(tmp_path, body), [(2*(x + 5), 2*(y + 1)) for x, y in RECT])


@pytest.mark.parametrize('attrs, scale', [
    ('', 1.0),                                                    # no physical size: user units are mm
    ('viewBox="-5 -5 40 30"', 1.0),
    ('width="40" height="30" viewBox="-5 -5 40 30"', 1.0),        # unitless width/height are mm, too
    ('width="80" height="60" viewBox="-5 -5 40 30"', 2.0),
    ('width="40mm" height="30mm" viewBox="-5 -5 40 30"', 1.0),
    ('width="80mm" height="60mm" viewBox="-5 -5 40 30"', 2.0),
    ('width="4cm" height="3cm" viewBox="-5 -5 40 30"', 1.0),
    ('width="4in" height="3in" viewBox="0 0 40 30"', 2.54),
    ('width="40pt" height="30pt" viewBox="0 0 40 30"', 25.4/72),
    ('width="40px" height="30px" viewBox="0 0 40 30"', 25.4/96),
    ('width="80mm" viewBox="0 0 40 30"', 2.0),                     # height from the viewBox aspect ratio
    ('width="100%" height="100%" viewBox="0 0 40 30"', 1.0),
    # Inkscape with mm document units: the viewBox is the page in mm
    ('width="210mm" height="297mm" viewBox="0 0 210 297"', 1.0),
    # Old Inkscape (90 dpi user units)
    ('width="210mm" height="297mm" viewBox="0 0 744.09448819 1052.3622047"', 25.4/90),
    # meet: the smaller scale
    ('width="80mm" height="90mm" viewBox="0 0 40 30"', 2.0),
])
def test_units(tmp_path, attrs, scale):
    pts = outline(tmp_path, '<path d="M0 0 H30 V20 H0 Z"/>', attrs)
    assert same_polygon(pts, [(scale*x, scale*y) for x, y in RECT], 1e-6)


def test_units_non_uniform_and_origin(tmp_path):
    pts = outline(tmp_path, '<path d="M0 0 H30 V20 H0 Z"/>',
                  'width="80mm" height="90mm" viewBox="10 10 40 30" preserveAspectRatio="none"')
    # Only the scale of the viewBox is applied: the user coordinate origin stays the origin
    assert same_polygon(pts, [(2*x, 3*y) for x, y in RECT], 1e-9)


def test_width_rounded_by_the_exporter_is_exact(tmp_path):
    # width/height written with fewer digits than the viewBox (as in the shark fixture): one user unit is exactly 1 mm
    pts = outline(tmp_path, '<path d="M0 0 H30.1234 V20 H0 Z"/>', 'width="100.24mm" height="54.47mm" '
                  'viewBox="0 0 100.2394 54.4735"')
    assert same_polygon(pts, [(0, 0), (30.1234, 0), (30.1234, 20), (0, 20)], 0)
    # ... but not when they really differ
    pts = outline(tmp_path, '<path d="M0 0 H30 V20 H0 Z"/>', 'width="100.3mm" height="54.5mm" '
                  'viewBox="0 0 100.2394 54.4735"')
    assert not same_polygon(pts, RECT, 1e-6)


def test_physical_size_without_viewbox_is_px(tmp_path):
    with pytest.warns(UserWarning, match='no viewBox'):
        pts = svg_import.read_outline(write(tmp_path, '<path d="M0 0 H30 V20 H0 Z"/>', 'width="100mm" height="80mm"'))
    s = 25.4/96
    assert same_polygon(pts, [(s*x, s*y) for x, y in RECT])


def test_nested_svg_viewport(tmp_path):
    body = '<svg x="10" y="0" width="60" height="40" viewBox="0 0 30 20"><path d="M0 0 H30 V20 H0 Z"/></svg>'
    assert same_polygon(outline(tmp_path, body), [(2*x + 10, 2*y) for x, y in RECT])


def test_largest_closed_contour_is_the_outline(tmp_path):
    body = ('<path d="M100 100 h5 v5 h-5 z"/>'
            '<g><path d="M0 0 H30 V20 H0 Z M10 5 h5 v5 h-5 z"/></g>'
            '<polyline points="0,30 50,30 50,40"/>')
    f = write(tmp_path, body)
    with pytest.warns(UserWarning, match=r'ignoring 1 hole\(s\) inside it, 1 other closed contour\(s\), 1 open path'):
        pts = svg_import.read_outline(f)
    assert same_polygon(pts, RECT)


def test_hidden_and_non_rendered_elements_are_ignored(tmp_path):
    body = ('<defs><path d="M0 0 H300 V200 H0 Z"/></defs>'
            '<clipPath id="c"><rect width="500" height="500"/></clipPath>'
            '<g style="display:none" id="layer2"><rect width="400" height="400"/></g>'
            '<rect width="400" height="400" display="none"/>'
            '<text x="0" y="0">Label</text><line x1="0" y1="0" x2="900" y2="900"/>'
            '<path d="M0 0 H30 V20 H0 Z"/>')
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        assert same_polygon(svg_import.read_outline(write(tmp_path, body)), RECT)


def test_kicad_style_separate_segments_are_joined(tmp_path):
    # KiCad's SVG plot draws every line and arc of a board outline as a path of its own, in any direction
    body = ('<g style="fill:#000000; fill-opacity:0.0; stroke:#000000; stroke-width:0.1000;">\n'
            '<path d="M100.0000,50.0000\nL126.0000,50.0000\n" />\n'
            '<path d="M130.0000,54.0000\nL130.0000,70.0000\n" />\n'
            '<path d="M126.0000,50.0000\nA4.0000,4.0000 0.0 0,1 130.0000,54.0000\n" />\n'
            '<path d="M100.0000,70.0000\nL100.0000,50.0000\n" />\n'
            '<path d="M100.0000,70.0000\nL130.0000,70.0000\n" />\n'
            '</g>')
    pts = outline(tmp_path, body, 'width="297.0022mm" height="210.0072mm" viewBox="0.0000 0.0000 297.0022 210.0072"')
    p = Polygon(pts)
    assert p.is_valid
    assert abs(p.area - (600 - (4 - math.pi)*4)) < 0.01
    assert p.bounds == (100, 50, 130, 70)


def test_open_outline_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='no closed outline.*is open'):
        outline(tmp_path, '<path d="M0 0 H30 V20 H0"/>')
    # also when a smaller closed contour exists
    with pytest.raises(ValueError, match='largest contour.*is open'):
        outline(tmp_path, '<path d="M0 0 H30 V20 H0"/><rect x="1" y="1" width="3" height="3"/>')


def test_self_intersecting_outline_is_rejected(tmp_path):
    with pytest.raises(ValueError, match=r'crosses itself at \(15.000, 10.000\)'):
        outline(tmp_path, '<path d="M0 0 L30 20 L30 0 L0 20 Z"/>')
    # touching: a vertex on another edge
    with pytest.raises(ValueError, match='touches or crosses itself'):
        outline(tmp_path, '<path d="M0 0 H30 V20 H20 L15 0 L10 20 H0 Z"/>')
    # a zero-width spike folding back onto its own edge
    with pytest.raises(ValueError, match='touches or crosses itself'):
        outline(tmp_path, '<path d="M0 0 H30 V20 H15 V10 V20 H0 Z"/>')


def test_no_outline(tmp_path):
    with pytest.raises(ValueError, match='contains no outline'):
        outline(tmp_path, '<text>nothing</text>')
    f = tmp_path / 'x.svg'
    f.write_text('<html/>')
    with pytest.raises(ValueError, match='not <svg>'):
        svg_import.read_outline(f)
    f.write_text('<svg')
    with pytest.raises(ValueError, match='not a valid XML'):
        svg_import.read_outline(f)


INKSCAPE = '''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!-- Created with Inkscape (http://www.inkscape.org/) -->
<svg width="80mm" height="60mm" viewBox="0 0 80 60" version="1.1" id="svg1"
   inkscape:version="1.3.2 (091e20e, 2023-11-25)" sodipodi:docname="coil.svg"
   xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
   xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
   xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg">
  <sodipodi:namedview id="namedview1" pagecolor="#ffffff" inkscape:document-units="mm" />
  <defs id="defs1" />
  <g inkscape:label="Layer 1" inkscape:groupmode="layer" id="layer1" transform="translate(-12.5,-30.25)">
    <path style="fill:#000000;stroke:none;stroke-width:0.264583"
       d="m 22.5,40.25 h 40 c 5.522847,0 10,4.477153 10,10 v 20 c 0,5.522847 -4.477153,10 -10,10 h -40 c -5.522847,0 -10,-4.477153 -10,-10 v -20 c 0,-5.522847 4.477153,-10 10,-10 z"
       id="path1" sodipodi:nodetypes="ccccccccc" />
  </g>
  <g inkscape:label="Hidden" inkscape:groupmode="layer" id="layer2" style="display:none">
    <rect width="200" height="200" x="0" y="0" id="rect2" />
  </g>
</svg>
'''


def test_inkscape_file(tmp_path):
    f = tmp_path / 'ink.svg'
    f.write_text(INKSCAPE)
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        pts = svg_import.read_outline(f)
    p = Polygon(pts)
    assert p.is_valid
    assert max(abs(a - b) for a, b in zip(p.bounds, (0, 10, 60, 50))) < 1e-6
    # Rounded rectangle 60 x 40 with r = 10 (cubic Bezier quarter circles, 0.027 % radius error)
    assert abs(p.area - (2400 - (400 - 100*math.pi))) < 0.1


def test_svgshape_dialect_files(tmp_path):
    # The cases of the original report, through SVGShape: all give the 30 x 20 rectangle (the group transform 60 x 40)
    for d in ('M0 0 H30 V20 H0 Z', 'M0 0 L30 0 L30 20 L0 20 z', 'm0 0 l30 0 l0 20 l-30 0 z',
              'M 0,0 L 30,0 L 30,20 L 0,20 Z', 'M 0 0 30 0 30 20 0 20 Z'):
        f = write(tmp_path, f'<path d="{d}"/>', 'viewBox="-5 -5 40 30"')
        s = geometry.SVGShape(filename=str(f), annular_width=3)
        assert Polygon(s.polygon).bounds == (0, 0, 30, 20)
    f = write(tmp_path, '<g transform="scale(2)"><path d="M0 0 L30 0 L30 20 L0 20 Z"/></g>')
    assert Polygon(geometry.SVGShape(filename=str(f), annular_width=3).polygon).bounds == (0, 0, 60, 40)


def _raw_path(svg_file):
    d = re.search(r' d="([^"]+)"', svg_file.read_text()).group(1)
    return [tuple(map(float, p.split())) for p in d.strip('MZ ').split(',')]


def test_shark_fixture_takes_the_reorientation_branch():
    # The shark fixture's path is clockwise in its own numbers (negative shoelace area; it appears counter-clockwise on
    # screen, where y points down). SVGShape reverses it, keeping vertex 0, and recenters it.
    raw = _raw_path(corpus_concave.SHARK_SVG)
    read = svg_import.read_outline(corpus_concave.SHARK_SVG)
    assert read == raw[:-1] # the repeated start point is dropped, nothing else changes
    assert svg_import.signed_area(read) < 0
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        shape = geometry.SVGShape(filename=str(corpus_concave.SHARK_SVG), annular_width=3)
    ox = raw[0][0] - shape.polygon[0][0]
    oy = raw[0][1] - shape.polygon[0][1]
    expect = [(x - ox, y - oy) for x, y in read[:1] + read[:0:-1]]
    assert max(math.dist(p, q) for p, q in zip(shape.polygon, expect)) < 1e-9
    assert len(shape.polygon) == len(expect)


def test_clockwise_and_counter_clockwise_give_the_same_outline(tmp_path):
    # Both orientations of a file and with or without the repeated start point: the same polygon, the same vertex 0
    ccw = '0 0,30 0,30 20,10 20,10 10,0 10'
    pts = ccw.split(',')
    cw = ','.join(pts[:1] + pts[:0:-1])
    shapes = []
    for d in (ccw, ccw + ',0 0', cw, cw + ',0 0'):
        f = write(tmp_path, f'<path d="M {d} Z"/>', name='o.svg')
        assert (svg_import.signed_area(svg_import.read_outline(f)) < 0) == d.startswith(cw)
        shapes.append(geometry.SVGShape(filename=str(f), annular_width=2).polygon)
    assert all(s == shapes[0] for s in shapes)
    assert shapes[0][0] == (0, 0) and not geometry.polygon_is_clockwise(shapes[0])


def test_gui_and_kicad_plugin_call(tmp_path):
    # The KiCad plugin opens the GUI (kicoil.gui), which creates the shape with these keyword arguments
    src = (Path(geometry.__file__).parent / 'gui.py').read_text()
    calls = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call) and getattr(n.func, 'id', None) == 'SVGShape']
    assert len(calls) == 1
    kw = sorted(k.arg for k in calls[0].keywords)
    assert kw == ['annular_width', 'filename'] and not calls[0].args
    f = tmp_path / 'ink.svg'
    f.write_text(INKSCAPE)
    shape = geometry.SVGShape(filename=str(f), annular_width=5.0)
    assert shape.sk.max_depth > 19
    plugin = (Path(geometry.__file__).parents[2] / 'kicad-plugin' / 'kicoil_action.py').read_text()
    assert 'kicoil.gui.main' in plugin


def test_cli_svg_default_tolerance():
    from kicoil import cli
    opt = {p.name: p for p in cli.svg.params}['arc_tolerance']
    assert opt.default == 0.002 == geometry.SVGShape.__dataclass_fields__['arc_tolerance'].default


@pytest.mark.parametrize('impl', ['kicoil', 'geometry_alt_cornerflat'])
def test_curved_svg_lays_out_cleanly(tmp_path, impl):
    # End to end: an Inkscape rounded rectangle (cubic Beziers, relative commands, layer transform, hidden layer)
    f = tmp_path / 'ink.svg'
    f.write_text(INKSCAPE)
    spec = dict(name='svg_inkscape', shape='svg', svg_file=str(f), turns=7, twists=3, layers=2, clockwise=False,
                clearance=0.15, trace_width=None, annular_width=10.0)
    if impl == 'kicoil':
        model, intent, rep = layout(spec)
    else:
        import run_corpus
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            model = run_corpus.build_model(spec, impl=impl)
            fp = model.render_footprint()
        intent = geomcheck.intent_from_model(model)
        rep = geomcheck.check_layout(geomcheck.extract_copper(fp, layers=model.layer_pair), intent)
    kinds = [k for k in rep.failure_kinds(intent.clearance, intent.trace_width) if k != 'conformance']
    assert not kinds, (kinds, rep.notes[:5])
    assert len(model.shape.polygon) < 400
