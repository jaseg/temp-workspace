"""Tests for the cornerflat layout on round outlines with many vertices (see corpus_round.py)."""

import math
import random
import time
import warnings

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


def _naive_spacing(arms, search_radius, min_path_separation):
    from kicoil.geometry import _split_by_angle, _seg_seg_distance
    segs = []
    for arm_idx, (points, angles) in enumerate(arms):
        s = 0.0
        for q1, q2, u1, u2 in _split_by_angle(points, angles, 0.05):
            l = math.dist(q1, q2)
            segs.append((q1, q2, arm_idx, min(u1, u2), max(u1, u2), s, s + l))
            s += l
    best, folds = search_radius, []
    for i, (p1, p2, arm, t_lo, t_hi, s_lo, s_hi) in enumerate(segs):
        for q1, q2, arm_j, u_lo, u_hi, r_lo, r_hi in segs[i+1:]:
            d = _seg_seg_distance(p1, p2, q1, q2)
            if arm_j == arm and max(u_lo - t_hi, t_lo - u_hi) < 0.5:
                if max(r_lo - s_hi, s_lo - r_hi) > min_path_separation and d < search_radius:
                    folds.append(d)
                continue
            best = min(best, d)
    return best, sorted(folds)


@pytest.mark.parametrize('name', ['star5_a0.60_n5k1', 'round_poly16_a0.90_n5k1', 'sector90_a0.90_n3k1'])
def test_cornerflat_vectorized_spacing_matches_brute_force(name):
    from kicoil.geometry_alt_cornerflat import min_turn_spacing
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = build_model(next(c for c in corpus.corpus('full') if c['name'] == name), 'geometry_alt_cornerflat')
    radius = 1.5 * model.spiral_pitch
    for layer_arms in model.spiral_center_lines():
        if layer_arms:
            for min_path in (math.inf, 2 * model.spiral_pitch):
                d, _where, folds = min_turn_spacing(layer_arms, radius, min_path_separation=min_path)
                nd, nfolds = _naive_spacing(layer_arms, radius, min_path)
                assert d == pytest.approx(nd, abs=1e-12)
                assert sorted(folds[0]) == pytest.approx(nfolds, abs=1e-12)


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
    # 10 um radial jitter on a 1024-gon: within the budget at 10 um
    poly = clean_polygon(corpus_round.noisy_circle(40, 1024, 0.01, random.Random(5)))
    simple, tol = CF.prepare_outline(poly)
    assert tol == 0.01 and len(simple) * count_reflex(simple) <= CF.SKELETON_BUDGET
    # Small cheap outlines are used as given (nearly collinear runs keep their vertices)
    poly = clean_polygon(corpus_round.shapes()['collinear'][0])
    assert CF.prepare_outline(poly) == (poly, 0.0)
    # Real noise (0.2 mm jitter) is not removed by any tolerance up to 10 um: the 1 um outline is kept
    poly = clean_polygon(corpus_round.shapes()['noisy_l'][0])
    _simple, tol = CF.prepare_outline(poly)
    assert tol == 0.001


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
