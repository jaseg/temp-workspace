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


def _closest(p1, p2, q1, q2):
    """ Distance and closest points of segments p1p2 and q1q2 (scalar reference) """
    from kicoil.geometry import _seg_seg_distance

    def foot(p, a, b):
        dx, dy = b[0]-a[0], b[1]-a[1]
        l2 = dx*dx + dy*dy
        t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / l2))
        return (a[0] + t*dx, a[1] + t*dy)
    if _seg_seg_distance(p1, p2, q1, q2) == 0.0:
        # crossing: the intersection point
        dx1, dy1, dx2, dy2 = p2[0]-p1[0], p2[1]-p1[1], q2[0]-q1[0], q2[1]-q1[1]
        den = dx1*dy2 - dy1*dx2
        if den != 0:
            t = ((q1[0]-p1[0])*dy2 - (q1[1]-p1[1])*dx2) / den
            x = (p1[0] + t*dx1, p1[1] + t*dy1)
            return 0.0, x, x
    cands = [(p1, foot(p1, q1, q2)), (p2, foot(p2, q1, q2)), (foot(q1, p1, p2), q1), (foot(q2, p1, p2), q2)]
    x, y = min(cands, key=lambda c: math.dist(*c))
    return math.dist(x, y), x, y


def _wind(a, b, c):
    """ Signed angle from a to b around c, in revolutions """
    a1 = math.atan2(a[1] - c[1], a[0] - c[0])
    b1 = math.atan2(b[1] - c[1], b[0] - c[0])
    return ((b1 - a1 + math.pi) % (2*math.pi) - math.pi) / (2*math.pi)


def _naive_spacing(arms, search_radius, centers):
    """ Brute force version of geometry_alt_cornerflat.min_turn_spacing (same pieces, every pair) """
    from kicoil.geometry_alt_cornerflat import _split_pieces
    segs = []
    off = 0
    for arm_idx, (points, angles) in enumerate(arms):
        s = 0.0
        w = [math.atan2(points[0][1] - c[1], points[0][0] - c[0]) / (2*math.pi) for c in centers or ()]
        for q1, q2, u1, u2, parent in zip(*_split_pieces(points, angles, 0.05)):
            q1, q2 = tuple(q1), tuple(q2)
            l = math.dist(q1, q2)
            segs.append((q1, q2, arm_idx, min(u1, u2), max(u1, u2), list(w), s, off + parent))
            w = [wi + _wind(q1, q2, c) for wi, c in zip(w, centers or ())]
            s += l
        off += len(points) - 1
    best, same = search_radius, {}
    for i, (p1, p2, arm, t_lo, t_hi, w1, s1, g1) in enumerate(segs):
        for q1, q2, arm_j, u_lo, u_hi, w2, s2, g2 in segs[i+1:]:
            if arm_j == arm and max(u_lo - t_hi, t_lo - u_hi) < 0.5:
                if not centers:
                    continue
                d, x, y = _closest(p1, p2, q1, q2)
                if d >= search_radius:
                    continue
                wsep = max(abs(a + _wind(p1, x, c) - b - _wind(q1, y, c)) for a, b, c in zip(w1, w2, centers))
                ds = abs(s1 + math.dist(p1, x) - s2 - math.dist(q1, y))
                key = (g1, g2)
                if key not in same or d < same[key][0]:
                    same[key] = (d, wsep, ds)
                continue
            best = min(best, _closest(p1, p2, q1, q2)[0])
    return best, sorted(same.values())


@pytest.mark.parametrize('name', ['star5_a0.60_n5k1', 'round_poly16_a0.90_n5k1', 'sector90_a0.90_n3k1',
                                  'round_blob2_a0.90_n5k1', 'octagon_a0.90_n3k1'])
def test_cornerflat_vectorized_spacing_matches_brute_force(name):
    from kicoil.geometry_alt_cornerflat import min_turn_spacing, checker_centers
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = build_model(next(c for c in corpus.corpus('full') if c['name'] == name), 'geometry_alt_cornerflat')
    radius = 1.5 * model.spiral_pitch
    centers = checker_centers(model.shape)
    for layer_arms in model.spiral_center_lines():
        if layer_arms:
            for c in (None, centers):
                d, _where, same = min_turn_spacing(layer_arms, radius, centers=c)
                nd, nsame = _naive_spacing(layer_arms, radius, c)
                assert d == pytest.approx(nd, abs=1e-12)
                got = sorted(zip(*(x.tolist() for x in same[:3])))
                assert len(got) == len(nsame)
                # (closest points of nearly parallel pieces are not unique: compare distances exactly, the separations
                # loosely)
                assert [g[0] for g in got] == pytest.approx([n[0] for n in nsame], abs=1e-9)
                if got:
                    assert np.array(got)[:, 1:] == pytest.approx(np.array(nsame)[:, 1:], abs=0.02)


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


def _variant(name, rotate=0.0, shift=(0.0, 0.0), **changes):
    """ A corpus case with its outline rotated about the origin and shifted, and other spec entries changed """
    spec = dict(next(c for c in corpus.corpus('full') if c['name'] == name))
    c, s = math.cos(math.radians(rotate)), math.sin(math.radians(rotate))
    spec['polygon'] = [(c*x - s*y + shift[0], s*x + c*y + shift[1]) for x, y in spec['polygon']]
    spec.update(changes)
    spec['name'] = f'{name}@r{rotate}_t{shift[0]},{shift[1]}'
    return spec


def _check_spec(spec):
    import geomcheck
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        model = build_model(spec, 'geometry_alt_cornerflat')
        fp = model.render_footprint(circle_segments=64)
    intent = geomcheck.intent_from_model(model)
    rep = geomcheck.check_layout(geomcheck.extract_copper(fp, layers=model.layer_pair), intent)
    return model, rep, rep.failure_kinds(intent.clearance, intent.trace_width), [str(w.message) for w in caught]


@pytest.mark.parametrize('name,rotate,shift', [
    ('concave_crescent_a0.9_n5k1', 270, (0, 0)), ('concave_crescent_a0.9_n5k1', 90, (0, 0)),
    ('cres16_12_a0.93_n5k1', 90, (0, 0)), ('cres17_10_a0.93_n5k1', 90, (0, 0)), ('sector180_a0.90_n3k1', 0, (0.01, 0)),
    ('sector180_a0.90_n3k1', 0, (0, 0)), ('octagon_a0.90_n3k1', 0, (0.01, 0.003))])
def test_cornerflat_layout_does_not_depend_on_the_checker_center_tie(name, rotate, shift):
    # The checker's center is the interior point of the inner contour: on a mirror symmetric hole (crescent, sector,
    # octagon) two sections of the scan line are equally wide, and rounding decides which one it picks. The rotated
    # crescent and the shifted sector180 got self shorts and clearance violations when the generator's center landed in
    # the other one. The measurement now uses both.
    if name.startswith('cres1'):
        # other crescents than the corpus one (outer radius 22, inner radius r2 offset by off)
        import corpus_concave
        r2, off = (int(v) for v in name[4:].split('_')[:2])
        poly = corpus_concave.crescent(22, r2, off)
        c, s = math.cos(math.radians(rotate)), math.sin(math.radians(rotate))
        poly = corpus._ccw([(c*x - s*y, s*x + c*y) for x, y in poly])
        spec = corpus._spec(f'{name}@r{rotate}', 'polygon', 5, 1, polygon=poly,
                            annular_width=round(0.93 * corpus.max_depth(poly), 4))
    else:
        spec = _variant(name, rotate, shift)
    _model, rep, kinds, _caught = _check_spec(spec)
    assert rep.self_shorts == 0 and not [k for k in kinds if k not in ('conformance', 'backtrack')], rep.notes[:5]


@pytest.mark.parametrize('turns,twists', [(3, 1), (5, 1)])
def test_cornerflat_keeps_the_checker_clean_layout_around_its_end_via(turns, twists):
    # rconvex0 at 90 %: a 6-7 mm trace in a 2 mm hole, whose innermost track and end via overlap the track leading
    # past them. The checker compares whole track segments (closest points), and the via with track of its own turn
    # only from pi/2*(w + c) plus its radius along the conductor on, and accepts the layout. The measurement compared
    # short pieces of the long segments and rejected it: at n3k1 the pitch ratio dropped from 0.969 to 0.852, at n5k1
    # a passing layout (0.983) was replaced by a failing one (0.960) with same-turn contacts.
    _model, rep, kinds, _caught = _check_spec(_variant('rconvex0_a0.90_n3k1', turns=turns, twists=twists))
    assert rep.self_shorts == 0 and not [k for k in kinds if k != 'conformance'], rep.notes[:5]
    assert (_model.trace_width + _model.clearance) / _model.spiral_pitch > (0.96 if turns == 3 else 0.98)
    if turns == 5:
        assert kinds == []


def test_checker_centers_start_with_the_checker_center():
    # The first center is the checker's own (geomcheck.intent_from_model), on every polygon case of the corpus
    import types
    import geomcheck
    from shapely.geometry import Polygon
    from kicoil.geometry_alt_cornerflat import interior_point, checker_centers
    rng = random.Random(3)
    for _ in range(50):
        poly = corpus.random_starlike(12, 30, rng)
        assert interior_point(poly) == pytest.approx(Polygon(poly).representative_point().coords[0], abs=1e-12)
    cases = corpus.corpus('full')
    for kind in corpus.EXTRA_FAMILIES:
        cases += corpus.corpus(kind)
    seen = 0
    for spec in cases:
        if spec.get('shape') != 'polygon' or not spec.get('polygon'):
            continue
        shape = types.SimpleNamespace(polygon=[tuple(p) for p in spec['polygon']], annular_width=spec['annular_width'])
        model = types.SimpleNamespace(shape=shape, turns=spec['turns'], trace_width=1.0, clearance=0.1, clockwise=False)
        want = geomcheck.intent_from_model(model).center
        got = checker_centers(shape)
        assert got[0] == pytest.approx(want, abs=1e-9), spec['name']
        seen += 1
    assert seen > 500


def test_checker_centers_cover_mirrored_ties():
    # A mirror symmetric hole has two equally wide sections: both centers are used
    import types
    from kicoil.geometry_alt_cornerflat import checker_centers
    spec = next(c for c in corpus.corpus('full') if c['name'] == 'octagon_a0.90_n3k1')
    shape = types.SimpleNamespace(polygon=[tuple(p) for p in spec['polygon']], annular_width=spec['annular_width'])
    ys = sorted(round(c[1], 6) for c in checker_centers(shape))
    assert len(ys) == 2 and ys[0] == pytest.approx(-ys[1]) and ys[1] > 0.1
