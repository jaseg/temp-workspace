"""Tests specific to the concave corpus family (tests/corpus_concave.py)."""

import logging
import math
import re
import warnings

import pytest
from shapely import affinity
from shapely.geometry import Polygon

import corpus_concave
from kicoil import geometry, skeletonator


def _raw_path(svg_file):
    d = re.search(r' d="([^"]+)"', svg_file.read_text()).group(1)
    return [tuple(map(float, p.split())) for p in d.strip('MZ ').split(',')]


def _import(svg_file):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore') # recentering warning
        return geometry.SVGShape(filename=str(svg_file), annular_width=3.0)


def test_shark_svg_fixture_is_clockwise_and_repeats_start():
    # The corpus fixture has to exercise SVGShape's reorientation branch
    raw = _raw_path(corpus_concave.SHARK_SVG)
    assert raw[0] == raw[-1]
    assert geometry.polygon_is_clockwise(raw)


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('repeat_start', [True, False])
def test_svg_import_independent_of_orientation(tmp_path, reverse, repeat_start):
    svg = tmp_path / 'shark.svg'
    corpus_concave.write_shark_svg(svg, reverse=reverse)
    if not repeat_start:
        text = svg.read_text()
        d = re.search(r' d="([^"]+)"', text).group(1)
        pts = d.strip('MZ ').split(',')
        svg.write_text(text.replace(d, 'M ' + ','.join(pts[:-1]) + ' Z'))
    raw = _raw_path(svg)
    assert geometry.polygon_is_clockwise(raw) == (not reverse)
    shape = _import(svg)
    assert not geometry.polygon_is_clockwise(shape.polygon)
    # Same outline as the polygon, mirrored in y (SVG and KiCad both have y pointing down)
    ref = Polygon([(x, -y) for x, y in corpus_concave.shark()])
    got = Polygon(shape.polygon)
    assert got.is_valid
    # (SVGShape recenters on the centroid, the corpus polygon is centered before rounding and simplification)
    c, cr = got.centroid, ref.centroid
    assert abs(c.x) < 1e-6 and abs(c.y) < 1e-6
    ref = affinity.translate(ref, -cr.x, -cr.y)
    assert got.symmetric_difference(ref).area < 1e-3
    assert abs(shape.sk.max_depth - corpus_concave.split_depth(corpus_concave.shark())) < 1e-3


def test_probe_rounds_the_heart_cusp_inside_the_outline():
    # Prototype (geometry_alt_concave_probe): rounding the reflex corners that cause the first split event. The base
    # Skeletonator now cuts the heart's cusp itself (round_cusps), so the probe starts from the lifted split depth.
    from kicoil import geometry_alt_concave_probe as probe
    radii = []
    poly, history = probe.lift_split_depth(corpus_concave.heart(), radii=radii)
    assert history[0] > 10
    assert all(r <= probe.REFLEX_RADIUS for r in radii)
    design = Polygon(corpus_concave.heart())
    assert design.buffer(1e-9).contains(Polygon(poly))


# ---- Sharp reflex cusps (Skeletonator.round_cusps) ----

def _mitered_skeletonator(poly):
    class Mitered(skeletonator.Skeletonator):
        CUSP_MITER_LIMIT = math.inf
    return Mitered(poly)


def test_heart_cusp_is_cut_with_a_tiny_arc_inside_the_outline():
    heart = corpus_concave.heart()
    sk = skeletonator.Skeletonator(heart)
    assert _mitered_skeletonator(heart).max_depth < 1.7 # the mitered cusp's spike hits the bottom of the heart
    assert sk.max_depth > 10 # (inscribed radius 11.5 mm)
    (i, r, phi), = sk.cusps
    assert heart[i] == (0.0, 5.0) or abs(heart[i][0]) < 1e-9 # the cusp at the top
    assert math.degrees(phi) > 170 and r == sk.CUSP_RADIUS
    assert sk.outline == skeletonator.clean_polygon(heart) # the outline as given (keepout zone, checker)
    layout = Polygon(sk.layout_outline)
    assert layout.is_valid and Polygon(heart).buffer(1e-9).contains(layout)
    assert Polygon(heart).area - layout.area < math.pi * r * r
    # The arc: vertices on a circle of radius r around the corner, segments of at most the segment angle, which keeps
    # the arc's depth error below CUSP_DEPTH_TOL at the inscribed radius
    seg = sk.cusp_segment_angle
    assert 11.5 * (1 / math.cos(seg / 2) - 1) <= sk.CUSP_DEPTH_TOL * 1.01
    arc = [p for p in sk.layout_outline if p not in set(heart)]
    assert all(abs(math.dist(p, heart[i]) - r) < 1e-12 for p in arc)
    assert len(arc) == math.ceil((math.pi + phi) / seg) + 1
    assert sk.poly == sk.layout_outline


def test_cut_cusp_offsets_are_round():
    # The inward offset of the cut outline near the cusp is a polygonal circle of radius r + d/cos(s/2) around it,
    # i.e. within r + d (1/cos(s/2) - 1) of the Euclidean offset of the given outline
    heart = corpus_concave.heart()
    sk = skeletonator.Skeletonator(heart)
    (i, r, _phi), = sk.cusps
    v = heart[i]
    s = sk.cusp_segment_angle
    for d in (1.0, 3.0, 6.0, 9.0):
        pts = [sk.track_position(k, d) for k in range(len(sk.poly))]
        near = min(math.dist(p, v) for p in pts)
        assert d + r - 1e-4 <= near <= r + d / math.cos(s/2) + 1e-4
        ring = Polygon(pts)
        euclid = Polygon(heart).buffer(-d, quad_segs=64)
        assert ring.symmetric_difference(euclid).area < 0.01 * euclid.area


def _insert_after(poly, i, dist):
    """ poly with a collinear vertex inserted dist mm after vertex i """
    a, b = poly[i], poly[(i + 1) % len(poly)]
    t = dist / math.dist(a, b)
    return poly[:i+1] + [(a[0] + t*(b[0] - a[0]), a[1] + t*(b[1] - a[1]))] + poly[i+1:]


def _split_cusp(poly, i, dist):
    """ poly with vertex i replaced by two vertices dist mm apart, on its two edges (a cusp split in two corners) """
    v, a, b = poly[i], poly[i-1], poly[(i + 1) % len(poly)]
    pa = (v[0] + dist/2 * (a[0] - v[0]) / math.dist(a, v), v[1] + dist/2 * (a[1] - v[1]) / math.dist(a, v))
    pb = (v[0] + dist/2 * (b[0] - v[0]) / math.dist(b, v), v[1] + dist/2 * (b[1] - v[1]) / math.dist(b, v))
    return poly[:i] + [pa, pb] + poly[i+1:]


@pytest.mark.parametrize('variant', ['n400', 'collinear_1um', 'collinear_5um', 'split_1um', 'size250', 'not_vertex0'])
def test_heart_cusp_cut_does_not_depend_on_sampling_or_size(variant):
    # The cusp is found and cut however the outline is sampled near it (vertices within the arc's radius are part of
    # the cut), and also for large outlines (the radius grows so that the arc's chords stay well above the skeleton's
    # numerical resolution). Before, a vertex within 8 µm of the cusp, 380 or more vertices on the heart, or a heart
    # wider than 210 mm left the cusp mitered (split depth back to 0.4 to 8 mm).
    heart = corpus_concave.heart()
    size = 44
    if variant == 'n400':
        poly = corpus_concave.heart(n=400)
    elif variant.startswith('collinear'):
        poly = _insert_after(heart, 0, 0.001 if variant.endswith('1um') else 0.005)
    elif variant == 'split_1um':
        poly = _split_cusp(heart, 0, 0.001)
    elif variant == 'size250':
        size = 250
        poly = corpus_concave.heart(size=size)
    else:
        poly = heart[17:] + heart[:17]
    sk = skeletonator.Skeletonator(poly)
    assert len(sk.cusps) == 1
    assert sk.max_depth > 0.229 * size # (10.13 mm at 44 mm)
    layout = Polygon(sk.layout_outline)
    assert layout.is_valid and Polygon(poly).buffer(1e-9).contains(layout)
    if variant == 'size250':
        assert sk.cusps[0][1] > sk.CUSP_RADIUS


@pytest.mark.parametrize('name', ['lround', 'uround', 'cross', 'comb', 'starround', 'dumbbell', 'shark', 'bean',
                                  'crescent', 'cshape'])
def test_modest_reflex_corners_keep_their_miter(name):
    # Reflex corners that turn by at most 120 degrees (miter factor 2) are left alone, so these outlines (and every
    # outline of the main and round corpus) lay out exactly as before
    poly = corpus_concave.shapes()[name][0]
    sk = skeletonator.Skeletonator(poly)
    assert sk.cusps == [] and sk.layout_outline == sk.outline


def _sawblade(n, ro, ri=20.0, f=0.97):
    pts = []
    for k in range(n):
        a = 2*math.pi*k/n
        pts.append((ro*math.cos(a), ro*math.sin(a)))
        b = a + 2*math.pi/n * f
        pts.append((ri*math.cos(b), ri*math.sin(b)))
    return pts


def test_many_cusps_get_coarser_arcs_within_the_budget():
    # A 12-pointed sawblade whose inner corners all turn by 137 degrees: the arcs get coarser (at most 20 degree
    # segments) so that the skeleton's cost stays bounded. Its Euclidean offsets never fall apart; the cut outline's
    # skeleton does not split before 19 mm either (mitered: 13.4 mm; with 29 degree segments a residual reflex corner
    # of each arc hits a tooth at 4.6 mm, hence the limit).
    pts = _sawblade(12, 60.0)
    turns = [skeletonator._reflex_turn(pts[k-1], pts[k], pts[(k+1) % len(pts)]) for k in range(len(pts))]
    assert sum(t > math.radians(120) for t in turns) == 12
    sk = skeletonator.Skeletonator(pts)
    assert len(sk.cusps) == 12
    assert math.radians(10) < sk.cusp_segment_angle <= math.radians(20) + 1e-9
    assert sk.max_depth > 19 and _mitered_skeletonator(pts).max_depth < 13.5
    out = sk.layout_outline
    assert max(skeletonator._reflex_turn(out[k-1], out[k], out[(k+1) % len(out)]) for k in range(len(out))) \
        <= sk.cusp_segment_angle * (1 + 1e-6)
    assert Polygon(pts).buffer(1e-9).contains(Polygon(out)) and Polygon(out).is_valid


def test_too_many_cusps_are_left_mitered_with_a_warning(caplog):
    # A 24-pointed sawblade: even 20 degree arcs exceed the budget. No corner is cut (all or nothing keeps the outline
    # symmetric), and a warning says so.
    pts = _sawblade(24, 30.0)
    skipped = []
    out, cusps, _seg = skeletonator.round_cusps(pts, 2.0, 0.01, math.radians(5), 360, skipped=skipped)
    assert (out, cusps) == (pts, []) and len(skipped) == 24
    out, cusps, seg = skeletonator.round_cusps(pts, 2.0, 0.01, math.radians(5), 10**6)
    assert len(cusps) == 24 and seg == math.radians(5)
    with caplog.at_level(logging.WARNING, logger='kicoil'):
        sk = skeletonator.Skeletonator(pts)
    assert sk.cusps == [] and sk.layout_outline == sk.outline
    assert any('left mitered' in r.getMessage() for r in caplog.records)


def test_cusp_next_to_another_edge_keeps_the_outline_simple():
    # Two V notches from the top and the bottom whose tips (cusps) are 0.004 mm apart: the arcs stay within half that
    # distance of their corner
    poly = [(-10, -10), (-0.5, -10), (0, -0.002), (0.5, -10), (10, -10), (10, 10), (0.5, 10), (0, 0.002), (-0.5, 10),
            (-10, 10)]
    out, cusps, _seg = skeletonator.round_cusps(poly, 2.0, 0.01, math.radians(5), 100)
    assert len(cusps) == 2
    assert all(r <= 0.002 + 1e-9 for _i, r, _phi, _arc in cusps)
    assert Polygon(out).is_valid and Polygon(poly).buffer(1e-9).contains(Polygon(out))


# Before the fix (mitered cusp): backtracks into the spike, copper 1.3 to 6.9 mm deeper than the annulus, vias up to
# 4.3 mm beyond the via offset, clearance and via clearance violations
HEART_CASES = ['concave_heart_a0.6_n8k3', 'concave_heart_a0.6_n6_1layer', 'concave_heart_a0.9_n8k3',
               'concave_heart_a0.3_n5k1', 'concave_heartdeep_a0.6_n8k3', 'concave_heartdeep_a0.9_n5k1']


@pytest.mark.parametrize('name', HEART_CASES)
def test_heart_cusp_layout(name):
    from test_layout import layout, spec
    caught = []
    model, intent, rep = layout(spec(name), caught)
    # Conformance fails only where the outer turn does not reach the heart's sharp convex bottom tip (contour, a known
    # limitation of the linear spiral at tips of a few degrees, as for the crescent's horns). With the 0.04 mm trace of
    # concave_heart_a0.3_n5k1 the innermost turn's copper also merges at that tip (a self merge, 7.5 (w + c), warned).
    kinds = set(rep.failure_kinds(intent.clearance, intent.trace_width))
    assert kinds <= {'conformance', 'self merge'}
    if 'self merge' in kinds:
        assert any('touches itself where the turn runs into a sharp tip' in m for m in caught), caught
        assert all(f' at (' in n and float(n.split(' at (')[1].split(',')[1].split(')')[0]) < -20
                   for n in rep.notes if n.startswith('self merge')), rep.notes # (at the bottom tip, not the cusp)
    assert rep.backtracks == 0
    assert rep.overshoot < 0.025 and rep.via_misplacement < 0.025
    assert rep.uncovered_fraction < 0.05 # (the mitered intended contour counted 6.5 to 22 % here)


@pytest.mark.parametrize('scale', [0.97, 0.99, 1.01, 1.03])
def test_heart_layout_is_robust_to_scaling(scale):
    from test_layout import layout, spec
    s = dict(spec('concave_heartdeep_a0.6_n8k3'))
    s['polygon'] = [(x*scale, y*scale) for x, y in s['polygon']]
    model, intent, rep = layout(s)
    assert set(rep.failure_kinds(intent.clearance, intent.trace_width)) <= {'conformance'}
    assert rep.backtracks == 0 and rep.overshoot < 0.025 and rep.uncovered_fraction < 0.05


def test_committed_split_depths_are_current():
    """ The concave corpus reads split depths from tests/data/concave_split_depths.json (so that it does not depend on
    the implementation under test); every entry must match the live computation of the fixed code. """
    cache = corpus_concave._split_depth_cache()
    assert cache
    shapes = {**{n: p for n, (p, _t) in corpus_concave.shapes().items()}}
    seen = 0
    for poly in shapes.values():
        for mitered in (False, True):
            key = corpus_concave._poly_key(tuple(map(tuple, poly)), mitered)
            if key in cache:
                seen += 1
                assert abs(cache[key] - corpus_concave.compute_split_depth(poly, mitered)) < 1e-9
    assert seen >= len(shapes)
