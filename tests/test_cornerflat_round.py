"""Tests for the cornerflat layout on round outlines with many vertices (see corpus_round.py)."""

import math
import random
import time
import warnings

import numpy as np
import pytest

import corpus
import corpus_round
from run_corpus import build_model


def _reflex(poly):
    n = len(poly)
    return sum(1 for i in range(n)
               if (poly[i][0]-poly[i-1][0])*(poly[(i+1) % n][1]-poly[i][1])
               - (poly[i][1]-poly[i-1][1])*(poly[(i+1) % n][0]-poly[i][0]) < 0)


def _point_polyline_distance(p, poly):
    best = math.inf
    for a, b in zip(poly, poly[1:] + poly[:1]):
        dx, dy = b[0]-a[0], b[1]-a[1]
        l2 = dx*dx + dy*dy
        t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / l2))
        best = min(best, math.hypot(p[0] - a[0] - t*dx, p[1] - a[1] - t*dy))
    return best


def test_simplify_outline_removes_rounding_noise_within_tolerance():
    from kicoil.skeletonator_alt_cornerflat import simplify_outline
    poly = corpus_round.svg_like(40, 3000, random.Random(4242))
    assert _reflex(poly) > 1000 # rounding to 1 um makes a good part of the vertices reflex
    tol = 0.001
    simple = simplify_outline(poly, tol)
    assert simple[0] == poly[0]
    assert _reflex(simple) == 0
    assert len(simple) < len(poly) / 4
    # Hausdorff distance at most tol (vertices of either outline to the other one)
    assert max(_point_polyline_distance(p, simple) for p in poly[::7]) <= tol + 1e-12
    assert max(_point_polyline_distance(p, poly) for p in simple) <= tol + 1e-12
    # A plain polygon stays as it is
    sq = corpus.rect(10, 10)
    assert simplify_outline(sq, tol) == sq


def test_cornerflat_dense_rounded_outline_is_fast():
    # The base skeleton of this outline runs out of memory after several minutes (3000 vertices, coordinates rounded to
    # 1 um). cornerflat simplifies it by 1 um first.
    poly = corpus_round.svg_like(40, 3000, random.Random(4242))
    spec = corpus._spec('svg3000r', 'polygon', 8, 3, polygon=poly, annular_width=round(0.6*corpus.max_depth(poly), 4))
    t0 = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = build_model(spec, 'geometry_alt_cornerflat')
    assert time.perf_counter() - t0 < 60
    assert model.trace_width > 0.95 * (model.spiral_pitch - model.clearance)


def test_cornerflat_simplifies_the_outline_once(monkeypatch):
    # The base Skeletonator removes rounding noise for the skeleton itself (remove_reflex_jitter) when the outline's
    # skeleton would be expensive, and keeps the removed vertices on chords. cornerflat simplifies the outline in
    # prepare_outline instead; the base class must not simplify that outline once more.
    from kicoil import skeletonator as base
    from kicoil.skeletonator_alt_cornerflat import CornerFlatSkeletonator
    calls = []
    jitter = base.remove_reflex_jitter
    monkeypatch.setattr(base, 'remove_reflex_jitter', lambda *a, **kw: calls.append(1) or jitter(*a, **kw))
    poly = corpus_round.svg_like(40, 3000, random.Random(4242))
    sk = CornerFlatSkeletonator(poly)
    assert calls == []
    assert sk.outline_tolerance == 0.001
    assert sk.input_poly == base.clean_polygon(poly)
    assert sk.poly == sk.outline == sk.skeleton_poly and sk._vertex_source is None
    assert len(sk.poly) < len(poly) / 4
    # The shape keeps the outline as given (keepout zone, checker)
    spec = corpus._spec('svg3000r', 'polygon', 8, 3, polygon=poly, annular_width=round(0.6*corpus.max_depth(poly), 4))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = build_model(spec, 'geometry_alt_cornerflat')
    assert len(model.shape.polygon) == len(poly)
    # An outline that prepare_outline leaves above the base class's simplification threshold (256 vertices, 117 reflex
    # corners deeper than 1 um, see prepare_outline's budget)
    noisy = next(c for c in corpus_round.cases() if c['name'].startswith('round_noisy_l_'))['polygon']
    sk = CornerFlatSkeletonator([tuple(p) for p in noisy])
    assert len(sk.poly) * len(base.reflex_vertices(sk.poly)) > base.Skeletonator.SIMPLIFY_COST
    assert calls == [] and sk.poly == sk.outline == sk.skeleton_poly


def _naive_spacing(arms, search_radius, center):
    """ Brute force version of geometry_alt_cornerflat.min_turn_spacing (same pieces, every pair) """
    from kicoil.geometry import _seg_seg_distance
    from kicoil.geometry_alt_cornerflat import _split_pieces, WRAP_WINDING
    segs = []
    for arm_idx, (points, angles) in enumerate(arms):
        s = 0.0
        for q1, q2, u1, u2, w1, w2 in zip(*_split_pieces(points, angles, 0.05, center)):
            l = math.dist(q1, q2)
            segs.append((q1, q2, arm_idx, min(u1, u2), max(u1, u2), min(w1, w2), max(w1, w2), s, s + l))
            s += l
    best, wraps = search_radius, []
    for i, (p1, p2, arm, t_lo, t_hi, v_lo, v_hi, s_lo, s_hi) in enumerate(segs):
        for q1, q2, arm_j, u_lo, u_hi, x_lo, x_hi, r_lo, r_hi in segs[i+1:]:
            d = _seg_seg_distance(p1, p2, q1, q2)
            if arm_j == arm and max(u_lo - t_hi, t_lo - u_hi) < 0.5:
                wsep = max(x_lo - v_hi, v_lo - x_hi)
                if wsep >= WRAP_WINDING and d < search_radius:
                    wraps.append((d, wsep, max(r_lo - s_hi, s_lo - r_hi)))
                continue
            best = min(best, d)
    return best, sorted(wraps)


def _exact_winding(points, center):
    a = [math.atan2(y - center[1], x - center[0]) for x, y in points]
    out = [a[0]]
    for x in a[1:]:
        out.append(out[-1] + (x - out[-1] + math.pi) % (2*math.pi) - math.pi)
    return [v / (2*math.pi) for v in out]


@pytest.mark.parametrize('name', ['star5_a0.60_n5k1', 'round_poly16_a0.90_n5k1', 'sector90_a0.90_n3k1',
                                  'round_blob2_a0.90_n5k1'])
def test_cornerflat_vectorized_spacing_matches_brute_force(name):
    from kicoil.geometry_alt_cornerflat import min_turn_spacing, hole_center, _split_pieces, WINDING_STEP
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = build_model(next(c for c in corpus.corpus('full') if c['name'] == name), 'geometry_alt_cornerflat')
    radius = 1.5 * model.spiral_pitch
    center = hole_center(model.shape.sk, 1.02 * model.shape.annular_width)
    for layer_arms in model.spiral_center_lines():
        if layer_arms:
            for c in (None, center):
                d, _where, wraps = min_turn_spacing(layer_arms, radius, center=c)
                nd, nwraps = _naive_spacing(layer_arms, radius, c)
                assert d == pytest.approx(nd, abs=1e-12)
                got = sorted(zip(*(x.tolist() for x in wraps[:3])))
                assert len(got) == len(nwraps)
                assert np.array(got).reshape(-1, 3) == pytest.approx(np.array(nwraps).reshape(-1, 3), abs=1e-12)
            # The pieces' winding angles are exact (as seen from the center) and change by at most WINDING_STEP
            for points, angles in layer_arms:
                q1, q2, _u1, _u2, w1, w2 = _split_pieces(points, angles, 0.05, center)
                assert np.all(np.abs(w2 - w1) <= WINDING_STEP + 1e-12)
                ref = _exact_winding(list(map(tuple, q1)) + [tuple(q2[-1])], center)
                assert np.append(w1, w2[-1]) - (ref[0] - w1[0]) == pytest.approx(ref, abs=1e-9)


def test_cornerflat_no_nanometer_pieces_near_vias(monkeypatch):
    # With the 512 vertex ellipse unsimplified, a vertex, a ramp start and a ramp end lie within nanometers of each
    # other next to an inner via. Pieces that short have an arbitrary direction (hairpins), and their ends got joined to
    # the via (connectivity broken).
    import geomcheck
    from kicoil import skeletonator_alt_cornerflat
    monkeypatch.setattr(skeletonator_alt_cornerflat.CornerFlatSkeletonator, 'prepare_outline',
                        classmethod(lambda cls, poly: (list(poly), 0.0)))
    spec = next(c for c in corpus.corpus('round') if c['name'] == 'round_ellipse3to1_a0.60_n21k8')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = build_model(spec, 'geometry_alt_cornerflat')
        fp = model.render_footprint(circle_segments=64)
    assert len(model.shape.sk.poly) == 512
    for layer in model.spiral_center_lines():
        for points, _angles in layer:
            assert min(math.dist(p, q) for p, q in zip(points, points[1:])) > 1e-5
    intent = geomcheck.intent_from_model(model)
    rep = geomcheck.check_layout(geomcheck.extract_copper(fp, layers=model.layer_pair), intent)
    assert rep.ok_connectivity, rep.notes
    assert rep.backtracks == 0


def _rounded(pts, decimals):
    out = []
    for x, y in pts:
        q = (round(x, decimals), round(y, decimals))
        if not out or q != out[-1]:
            out.append(q)
    if out[-1] == out[0]:
        out.pop()
    return corpus._ccw(out)


def test_prepare_outline_raises_the_tolerance_for_coarse_noise():
    from kicoil.skeletonator import clean_polygon
    from kicoil.skeletonator_alt_cornerflat import CornerFlatSkeletonator as CF, count_reflex
    # Coordinates rounded to 10 um: 1 um leaves 667 reflex vertices among 1384, 10 um none
    poly = clean_polygon(_rounded(corpus_round.fourier_blob(40, 2000, random.Random(12), order=5, amp=0.15), 2))
    simple, tol = CF.prepare_outline(poly)
    assert tol == 0.01 and count_reflex(simple) == 0
    assert max(_point_polyline_distance(p, simple) for p in poly[::5]) <= tol + 1e-12
    # 10 um radial jitter on a 1024-gon: 10 um leaves 104 reflex vertices, 20 um none
    poly = clean_polygon(corpus_round.noisy_circle(40, 1024, 0.01, random.Random(5)))
    simple, tol = CF.prepare_outline(poly)
    assert tol == 0.02 and count_reflex(simple) == 0
    # Small cheap outlines are used as given (nearly collinear runs keep their vertices)
    poly = clean_polygon(corpus_round.shapes()['collinear'][0])
    assert CF.prepare_outline(poly) == (poly, 0.0)
    # Real noise (0.2 mm jitter) is not removed by any tolerance up to 20 um: the 1 um outline is kept
    poly = clean_polygon(corpus_round.shapes()['noisy_l'][0])
    _simple, tol = CF.prepare_outline(poly)
    assert tol == 0.001


def test_cornerflat_jittered_outline_deep():
    # 10 um radial jitter, 90 % annular width: with the jitter corners left in the outline (1 um), the skeleton takes
    # over a minute and the layout reaches a pitch ratio of 0.73 with a misplaced via; on the 20 um outline 0.81
    import geomcheck
    poly = corpus_round.noisy_circle(40, 1024, 0.01, random.Random(5))
    spec = corpus._spec('noisy1024', 'polygon', 16, 5, polygon=poly, annular_width=round(0.9*corpus.max_depth(poly), 4))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = build_model(spec, 'geometry_alt_cornerflat')
        fp = model.render_footprint()
    intent = geomcheck.intent_from_model(model)
    rep = geomcheck.check_layout(geomcheck.extract_copper(fp, layers=model.layer_pair), intent)
    assert rep.failure_kinds(intent.clearance, intent.trace_width) == ['conformance'], rep.notes[:5]
    assert (model.trace_width + model.clearance) / model.spiral_pitch > 0.8


def test_cornerflat_coarsely_rounded_outline_is_fast():
    # Coordinates rounded to 10 um (2 decimals): the skeleton of the outline simplified by 1 um takes over 5 minutes
    import geomcheck
    poly = _rounded(corpus_round.fourier_blob(40, 2000, random.Random(12), order=5, amp=0.15), 2)
    spec = corpus._spec('svg2000r2', 'polygon', 8, 3, polygon=poly, annular_width=round(0.6*corpus.max_depth(poly), 4))
    t0 = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = build_model(spec, 'geometry_alt_cornerflat')
        fp = model.render_footprint()
    assert time.perf_counter() - t0 < 60
    intent = geomcheck.intent_from_model(model)
    rep = geomcheck.check_layout(geomcheck.extract_copper(fp, layers=model.layer_pair), intent)
    assert rep.overshoot < 0.02
    kinds = rep.failure_kinds(intent.clearance, intent.trace_width)
    assert not [k for k in kinds if k != 'conformance'], (kinds, rep.notes[:5])


def test_noisy_round_shapes_use_the_skeleton_depth():
    # The straight skeleton of the 0.2 mm jitter circle collapses at 16.8 mm, well before its inscribed circle
    # (19.8 mm): corpus_round uses the skeleton's limit for the annular fractions, so every case gets laid out
    from kicoil.skeletonator import Skeletonator
    for name, depth in corpus_round.SKELETON_DEPTH.items():
        assert Skeletonator(corpus_round.shapes()[name][0]).max_depth == pytest.approx(depth, abs=1e-3)


def _cornerflat_case(name):
    import geomcheck
    spec = next(c for c in corpus.corpus('full') if c['name'] == name)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        model = build_model(spec, 'geometry_alt_cornerflat')
        fp = model.render_footprint(circle_segments=64)
    intent = geomcheck.intent_from_model(model)
    rep = geomcheck.check_layout(geomcheck.extract_copper(fp, layers=model.layer_pair), intent)
    return model, rep, rep.failure_kinds(intent.clearance, intent.trace_width), [str(w.message) for w in caught]


@pytest.mark.parametrize('name', ['round_ellipse3to1_a0.90_n5k1', 'round_ellipse10to1_a0.90_n5k1',
                                  'concave_crescent_a0.9_n5k1'])
def test_cornerflat_thin_inner_contour_folds_do_not_limit_the_spacing(name):
    # The innermost turn runs into the tip of the thin inner contour and comes back along its other side, a few
    # hundredths of a turn further on in winding angle: one turn folding onto itself, which the checker accepts (a self
    # overlap). cornerflat used to count pieces of one arm far apart along the conductor as different turns and got a
    # pitch ratio of 0.84 (ellipses) and 0.74 (crescent), failing conformance; the fixed layout gets 0.997 and 1.0.
    model, rep, kinds, caught = _cornerflat_case(name)
    assert kinds == [], rep.notes[:5]
    assert (model.trace_width + model.clearance) / model.spiral_pitch > 0.99
    assert rep.self_overlaps > 0 and rep.self_shorts == 0
    # ... and warns about the fold, like the fixed layout (D32)
    assert any('the copper of one turn' in w for w in caught), caught


@pytest.mark.parametrize('name', ['round_blob2_a0.90_n5k1', 'round_noisy_l_a0.90_n5k1', 'sector90_a0.90_n3k1',
                                  'sector180_a0.90_n3k1', 'rstar0_a0.90_n3k1'])
def test_cornerflat_turn_wrapping_a_small_hole_does_not_touch_itself(name):
    # A trace about as wide as the pitch wraps around an inner contour smaller than itself and touched itself 0.19 to
    # 0.26 turns further on (a self short): pieces of one arm less than half a revolution apart in the arm's angle were
    # never compared unless they were far apart along the conductor.
    model, rep, kinds, _caught = _cornerflat_case(name)
    assert rep.self_shorts == 0, rep.notes[:5]
    assert not [k for k in kinds if k != 'conformance'], rep.notes[:5]


def test_cornerflat_does_not_run_over_its_own_end_via():
    # The 'lattice' layout of this coil (6.6 mm trace, 2 mm hole) ran its last half turn past its own inner via, 0.47
    # turns before the via in winding angle: the via overlapped that copper by 2.8 mm, which the checker exempts (it is
    # less than pi/2 pitches plus the via radius along the conductor from the via), but the tapered layout had to narrow
    # the trace to 0.12 x w0 there. The measurement now sees the contact, and another arm phase is chosen.
    from kicoil import taper
    model, rep, kinds, _caught = _cornerflat_case('rconvex0_a0.90_n3k1')
    assert rep.self_shorts == 0 and not [k for k in kinds if k != 'conformance']
    inner_via = model.via_positions()[0][0]
    w = model.trace_width
    for points, angles in (layer[0] for layer in model.spiral_center_lines()):
        # copper more than pi/2 pitches along the conductor before the via keeps clear of it
        s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(np.array(points), axis=0).T))])
        far = s < s[-1] - math.pi/2 * (w + model.clearance) - model.via_diameter/2
        pts = np.array(points)[far]
        dmin = min(_point_segment(inner_via, a, b) for a, b in zip(pts, pts[1:]))
        assert dmin >= w/2 + model.via_diameter/2
    r = taper.taper_layout(model, piece_length=0.5 * model.spiral_pitch)
    assert r.necks == 0 and r.min_width >= model.trace_width - 1e-9


def _point_segment(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    l2 = dx*dx + dy*dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / l2))
    return math.hypot(p[0] - a[0] - t*dx, p[1] - a[1] - t*dy)


def test_hole_center_is_the_checker_center():
    # hole_center is the interior point (as shapely's representative_point computes it) of the inner contour
    from shapely.geometry import Polygon
    from kicoil.geometry_alt_cornerflat import interior_point, hole_center
    from kicoil.skeletonator_alt_cornerflat import CornerFlatSkeletonator
    rng = random.Random(3)
    for _ in range(50):
        poly = corpus.random_starlike(12, 30, rng)
        assert interior_point(poly) == pytest.approx(Polygon(poly).representative_point().coords[0], abs=1e-12)
    spec = next(c for c in corpus.corpus('full') if c['name'] == 'rconvex0_a0.90_n3k1')
    A = spec['annular_width']
    inner = Polygon(spec['polygon']).buffer(-1.02*A, join_style='mitre', mitre_limit=10)
    sk = CornerFlatSkeletonator([tuple(p) for p in spec['polygon']])
    assert hole_center(sk, 1.02*A) == pytest.approx(inner.representative_point().coords[0], abs=1e-6)
