"""Tests specific to the concave corpus family (tests/corpus_concave.py)."""

import math
import re
import warnings

import pytest
import shapely
from shapely import affinity
from shapely.geometry import Polygon

import corpus_concave
from kicoil import geometry, skeletonator


def _raw_path(svg_file):
    d = re.search(r' d="([^"]+)"', svg_file.read_text()).group(1)
    return [tuple(map(float, p.split())) for p in d.strip('MZ ').split(',')]


def _clockwise(pts):
    return not shapely.is_ccw(shapely.LinearRing(pts))


def _import(svg_file):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore') # recentering warning
        return geometry.SVGShape(filename=str(svg_file), annular_width=3.0)


def test_shark_svg_fixture_is_clockwise_and_repeats_start():
    # The corpus fixture has to exercise the reorientation of the outline
    raw = _raw_path(corpus_concave.SHARK_SVG)
    assert raw[0] == raw[-1]
    assert _clockwise(raw)


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
    assert _clockwise(raw) == (not reverse)
    shape = _import(svg)
    assert not _clockwise(shape.polygon)
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


# ---- Round joints at sharp reflex corners (Skeletonator.ROUND_JOINT_*) ----

def _mitered_skeletonator(poly):
    class Mitered(skeletonator.Skeletonator):
        ROUND_JOINT_MIN_TURN = math.inf
    return Mitered(poly)


def test_heart_cusp_gets_a_round_joint():
    heart = corpus_concave.heart()
    sk = skeletonator.Skeletonator(heart)
    assert _mitered_skeletonator(heart).max_depth < 1.7 # the mitered cusp's spike hits the bottom of the heart
    assert sk.max_depth > 10 # (inscribed radius 11.5 mm)
    assert sk.joint_radius == sk.ROUND_JOINT_RADIUS
    assert sk.outline == skeletonator.clean_polygon(heart) # the outline as given (keepout zone, checker)
    turns = skeletonator.turn_angles(sk.outline)
    (k,), = (-turns > sk.ROUND_JOINT_MIN_TURN).nonzero()
    v = heart[k]
    assert abs(v[0]) < 1e-9 and math.degrees(-turns[k]) > 170 # the cusp at the top
    # The cusp is cut by an arc of the joint radius through the inside of the outline: every other vertex stays
    joint = Polygon(sk.poly)
    assert joint.is_valid and Polygon(heart).buffer(1e-9).contains(joint)
    assert Polygon(heart).area - joint.area < math.pi * sk.joint_radius**2
    new = [p for p in sk.poly if p not in set(heart)]
    assert set(sk.poly) - set(new) == set(heart) - {v}
    assert all(math.dist(p, v) <= sk.joint_radius * (1 + 1e-9) for p in new) and len(new) > 20


def test_round_joint_offsets_are_round():
    # Near the cusp, the offset at depth d is a polygonal arc of radius r + d around it, within the tolerance, so the
    # offsets are those of the Euclidean (round) offset of the outline, at most r deeper
    heart = corpus_concave.heart()
    sk = skeletonator.Skeletonator(heart)
    v, r = heart[0], sk.joint_radius
    for d in (1.0, 3.0, 6.0, 9.0):
        pts = [sk.track_position(k, d) for k in range(len(sk.poly))]
        near = min(math.dist(p, v) for p in pts)
        assert d + r - 1e-4 <= near <= d + r + sk.ROUND_JOINT_TOLERANCE
        euclid = Polygon(heart).buffer(-d, quad_segs=64)
        assert Polygon(pts).symmetric_difference(euclid).area < 0.01 * euclid.area


def _insert_after(poly, i, dist):
    """ poly with a collinear vertex inserted dist mm after vertex i """
    a, b = poly[i], poly[(i + 1) % len(poly)]
    t = dist / math.dist(a, b)
    return poly[:i+1] + [(a[0] + t*(b[0] - a[0]), a[1] + t*(b[1] - a[1]))] + poly[i+1:]


@pytest.mark.parametrize('variant', ['n400', 'collinear_1um', 'collinear_5um', 'size250', 'not_vertex0'])
def test_heart_round_joint_does_not_depend_on_sampling_or_size(variant):
    heart = corpus_concave.heart()
    size = 44
    if variant == 'n400':
        poly = corpus_concave.heart(n=400)
    elif variant.startswith('collinear'):
        poly = _insert_after(heart, 0, 0.001 if variant.endswith('1um') else 0.005)
    elif variant == 'size250':
        size = 250
        poly = corpus_concave.heart(size=size)
    else:
        poly = heart[17:] + heart[:17]
    sk = skeletonator.Skeletonator(poly)
    assert sk.joint_radius > 0 and Polygon(sk.poly).is_valid and Polygon(poly).buffer(1e-9).contains(Polygon(sk.poly))
    assert sk.max_depth > 0.229 * size # (10.13 mm at 44 mm)
    if variant == 'size250':
        assert sk.joint_radius > sk.ROUND_JOINT_RADIUS # (the arc's chords well above the skeleton's resolution)


@pytest.mark.parametrize('name', ['lround', 'uround', 'cross', 'comb', 'starround', 'dumbbell', 'shark', 'bean',
                                  'crescent', 'cshape'])
def test_modest_reflex_corners_keep_their_miter(name):
    # Reflex corners that turn by at most ROUND_JOINT_MIN_TURN (miter factor 2) are mitered: these outlines lay out
    # on the outline as given
    poly = corpus_concave.shapes()[name][0]
    sk = skeletonator.Skeletonator(poly)
    assert sk.joint_radius == 0 and sk.poly == sk.outline


def _sawblade(n, ro, ri=20.0, f=0.97):
    pts = []
    for k in range(n):
        a = 2*math.pi*k/n
        pts.append((ro*math.cos(a), ro*math.sin(a)))
        b = a + 2*math.pi/n * f
        pts.append((ri*math.cos(b), ri*math.sin(b)))
    return pts


def test_sawblade_gets_round_joints():
    # A 12-pointed sawblade whose inner corners all turn by 137 degrees: mitered, a tooth's inner corner hits the next
    # tooth at 13.4 mm; with round joints the offsets do not fall apart before 19 mm
    pts = _sawblade(12, 60.0)
    assert sum(-skeletonator.turn_angles(pts) > math.radians(120)) == 12
    sk = skeletonator.Skeletonator(pts)
    assert sk.max_depth > 19 and _mitered_skeletonator(pts).max_depth < 13.5


def test_round_joint_next_to_another_edge_keeps_the_outline_simple():
    # Two V notches from the top and the bottom whose tips (cusps) are 0.004 mm apart: the joint radius is reduced
    # until the arcs keep the outline in one piece
    poly = [(-10, -10), (-0.5, -10), (0, -0.002), (0.5, -10), (10, -10), (10, 10), (0.5, 10), (0, 0.002), (-0.5, 10),
            (-10, 10)]
    sk = skeletonator.Skeletonator(poly)
    assert 0 < sk.joint_radius <= 0.002 and Polygon(sk.poly).is_valid
    with pytest.raises(ValueError):
        skeletonator.round_reflex_joints(skeletonator.clean_polygon(poly), 0.01, math.radians(5), math.radians(120))


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
    # concave_heart_a0.3_n5k1 the innermost turn's copper also merges at that tip (a self merge, 7.5 (w + c)).
    kinds = set(rep.failure_kinds(intent.clearance, intent.trace_width))
    assert kinds <= {'conformance', 'self merge'}
    if 'self merge' in kinds:
        assert all(' at (' in n and float(n.split(' at (')[1].split(',')[1].split(')')[0]) < -20
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
                # (The heart's depth is that of the first version of its round joint, a cut 0.01 mm deeper than the
                # outline; the corpus keeps it so that its annular widths stay the same)
                assert abs(cache[key] - corpus_concave.compute_split_depth(poly, mitered)) < 1e-3 * cache[key]
    assert seen >= len(shapes)
