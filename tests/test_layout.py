"""Geometric layout checks over the test corpus, plus regression tests for specific layout bugs.

Run with `uv run --group dev pytest tests`. The full corpus is behind `--full-corpus` (see conftest.py); the default run
uses the quick subset.
"""

import math
import warnings

import pytest

import corpus
import geomcheck
from run_corpus import build_model


def layout(spec, caught=None):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        model = build_model(spec)
        fp = model.render_footprint()
    if caught is not None:
        caught.extend(str(x.message) for x in w)
    intent = geomcheck.intent_from_model(model)
    copper = geomcheck.extract_copper(fp, layers=model.layer_pair)
    return model, intent, geomcheck.check_layout(copper, intent)


FOLD_WARNING = 'folds onto itself'
# Failure kinds that a warning from the generator can explain
WARNED_KINDS = ('clearance', 'via clearance', 'self short')


def _cases(request_full):
    return corpus.corpus('full' if request_full else 'quick')


def pytest_generate_tests(metafunc):
    if 'spec' in metafunc.fixturenames:
        full = metafunc.config.getoption('--full-corpus')
        cases = corpus.corpus('full' if full else 'quick')
        metafunc.parametrize('spec', cases, ids=[c['name'] for c in cases])


def test_corpus_case(spec):
    caught = []
    try:
        model, intent, rep = layout(spec, caught)
    except ValueError as e:
        # Rejecting an infeasible request with a clear message is fine, crashing is not.
        pytest.skip(f'rejected: {e}')

    # Every check of the geometric checker except outline coverage, which the linear spiral does not reach at convex
    # corners of deep annuli (that is measured by run_corpus.py, not asserted here).
    kinds = [k for k in rep.failure_kinds(intent.clearance, intent.trace_width) if k != 'conformance']
    hard = [k for k in kinds if k not in WARNED_KINDS]
    assert not hard, (hard, rep.notes[:5], rep.violations[:5])
    if kinds:
        # Clearance problems are acceptable only when the generator warned about them: a turn folding onto itself
        # around a notch or a hole narrower than the trace, or a via (as wide as the trace) that does not fit the hole.
        assert any(FOLD_WARNING in m or (m.startswith('Via at') and 'neighboring turn' in m) for m in caught), (kinds, caught, rep.violations[:5])
        pytest.xfail(f'warned: {kinds}')
    # The copper must stay within the intended outline
    assert rep.overshoot < max(0.05, 0.1 * intent.trace_width)
    cut = [c for c in getattr(getattr(model.shape, 'sk', None), 'cut_protrusions', ()) if c[3] < intent.annular_width]
    if not cut:
        # (Turns do not run into protrusions narrower than two turns, those parts of the outline stay uncovered)
        assert rep.contour_hausdorff < 1.5


def spec(name):
    return next(c for c in corpus.corpus('full') if c['name'] == name)


def poly_spec(poly, annular, turns, twists, **kw):
    return corpus._spec('custom', 'polygon', turns, twists, polygon=poly, annular_width=annular, **kw)


def test_no_duplicate_vertices_at_turn_boundaries():
    # Regular polygons put vertices exactly on turn boundaries. These used to be emitted twice, making the spiral fold
    # back on itself.
    _model, _intent, rep = layout(poly_spec(corpus.regular(6, 40), 6.0, 13, 1))
    assert rep.branches == 0 and rep.backtracks == 0 and rep.degenerate_segments == 0
    assert abs(rep.winding_error) < 0.01


def test_split_detection_ignores_degenerate_skeleton_nodes():
    # The rounded rectangle is convex, it has no split events. Coincident skeleton nodes used to be taken for splits,
    # which limited the annular width to less than half of the possible depth.
    from kicoil import skeletonator
    sk = skeletonator.Skeletonator(corpus.rounded_rect(40, 25, 5))
    assert math.isclose(sk.max_depth, sk.radius)
    assert sk.max_depth > 12


def test_split_depth_is_minimum_over_splits():
    from kicoil import skeletonator
    sk = skeletonator.Skeletonator(corpus.u_shape(40, 30, 12))
    assert sk.max_depth <= 6.0 + 1e-9


def test_arm_ends_on_collapsed_edges():
    # The ellipse's tip edges collapse before the inner turn, so several vertices share one angle. Arms starting or
    # ending there used to cut across the tip and cross the neighboring turn.
    _model, _intent, rep = layout(spec('ellipse3to1_a0.60_n5k1'))
    assert rep.crossings == 0 and rep.ok_connectivity


def test_inner_and_outer_arms_meet_at_vias():
    model, _intent, rep = layout(spec('rconvex1_a0.30_n5k2'))
    assert rep.backtracks == 0 and rep.ok_connectivity


def test_trace_width_from_measured_spacing():
    # Convex corners and steep (many twists) spirals bring neighboring turns closer than the nominal pitch. The trace
    # width must account for that.
    model, intent, rep = layout(spec('square40_a0.30_n8k3'))
    assert model.projected_spiral_pitch < model.spiral_pitch
    assert rep.worst_clearance_deficit <= 1e-3


def test_arc_approximation_respects_clearance():
    _model, intent, rep = layout(spec('circle50x25_n11k5'))
    assert rep.worst_clearance_deficit <= 0.05 * intent.clearance


def test_single_layer_ignores_twists():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = build_model(poly_spec(corpus.rect(40, 20), 5, 6, 3, layers=1))
    assert model.twists == 1
    assert math.isclose(abs(model.sector_angle), 2*math.pi)


def test_too_large_clearance_is_rejected():
    with pytest.raises(ValueError):
        build_model(poly_spec(corpus.rect(40, 20), 2, 21, 1, clearance=1.0))


def test_resistance_uses_full_arm_length():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        m1 = build_model(dict(spec('circle50x25_n5k1'), turns=5))
        m2 = build_model(dict(spec('circle50x25_n5k1'), turns=9))
    # More turns means a longer track. The track length used to be computed from a single sector.
    assert m2.track_length > 1.5 * m1.track_length


def test_neck_pinch_is_a_split():
    # Two reflex corners facing each other pinch the outline off at a constant-time skeleton edge. Each end of that
    # edge has only one way up, so a node-by-node test misses the split.
    from kicoil import skeletonator
    sk = skeletonator.Skeletonator(corpus.neck(40, 20, 8))
    assert math.isclose(sk.max_depth, 4.0, abs_tol=1e-6)
    with pytest.raises(ValueError):
        build_model(poly_spec(corpus.neck(40, 20, 8), 5.0, 5, 1))


def test_arm_end_on_collapsed_group_at_half_turn():
    # The collapsing group at the ellipse's left tip has angle 0.49999999999999994. Adding the revolution number
    # rounds that to an integer + 0.5, which used to resolve the tie to the wrong end of the group, so an arm end cut
    # across the whole tip.
    model, intent, rep = layout(spec('ellipse3to2_a0.90_n9k4'))
    assert rep.crossings == 0 and rep.ok_connectivity
    assert model.projected_spiral_pitch > 0.5 * model.spiral_pitch


def test_via_clearance_on_long_segments():
    # A long center line segment that reaches into the via's own half turn used to be measured against the via,
    # which pushed the via offset far out and created real violations.
    _model, intent, rep = layout(spec('subdiv_rect_jitter_a0.90_n3k1'))
    assert rep.worst_via_deficit <= 0.05 * intent.clearance + 1e-4
    assert rep.worst_clearance_deficit <= 0.05 * intent.clearance + 1e-4


# ---------------------------------------------------------------------------------------------------------------------
# Skeletonator input handling


def test_contour_nodes_matched_despite_rounding():
    # skeleton.wasm prints 12 significant digits. Vertices were matched to skeleton nodes by rounding both to 6 decimals,
    # which fails when a coordinate lies close to a rounding boundary (KeyError).
    from kicoil import skeletonator
    x = 22.092782500010948
    assert round(float(f'{x:.12g}'), 6) != round(x, 6)
    sk = skeletonator.Skeletonator([(x, -20.0), (x, 20.0), (-x, 20.0), (-x, -20.0)])
    assert math.isclose(sk.max_depth, 20.0)
    assert sk.track_position(0, 5) == pytest.approx((x - 5, -15.0))


def test_clockwise_polygons_are_normalized():
    from kicoil import skeletonator, geometry
    cw = [(0., 0.), (0., 10.), (10., 10.), (10., 0.)]
    # A path that repeats its start point used to be classified as counter-clockwise
    assert skeletonator.polygon_is_clockwise(cw + [cw[0]])
    assert geometry.polygon_is_clockwise(cw + [cw[0]])
    sk = skeletonator.Skeletonator(cw + [cw[0]])
    assert len(sk.poly) == 4 and not skeletonator.polygon_is_clockwise(sk.poly)
    assert sk.poly[0] == cw[0]
    assert math.isclose(sk.max_depth, 5.0)
    with pytest.raises(ValueError):
        skeletonator.Skeletonator([(0., 0.), (1., 1.), (2., 2.)])


def test_svg_clockwise_path_with_closing_point(tmp_path):
    from kicoil.geometry import SVGShape
    f = tmp_path / 'cw.svg'
    f.write_text('<svg xmlns="http://www.w3.org/2000/svg"><path d="M -5 -5 L -5 5 L 5 5 L 5 -5 L -5 -5 Z"/></svg>')
    shape = SVGShape(str(f), annular_width=2)
    assert len(shape.polygon) == 4
    assert math.isclose(shape.sk.max_depth, 5.0)


def test_merge_tolerance_does_not_depend_on_position():
    # Node merging used a tolerance proportional to the distance from the origin, so small features of a polygon far
    # away from the origin disappeared, and a polygon far enough away lost its whole skeleton without an error.
    from kicoil import skeletonator
    ch = corpus.chamfered_rect(40, 30, 0.05)
    ref = skeletonator.Skeletonator(ch)
    for off in (1e5, 1e6):
        sk = skeletonator.Skeletonator([(x + off, y + off) for x, y in ch])
        assert [len(t) for t in sk.tracks] == [len(t) for t in ref.tracks]
        for i in range(len(ch)):
            x, y = sk.track_position(i, 5)
            # skeleton.wasm prints 12 significant digits, i.e. 1e-6 mm at 1e6 mm
            assert (x - off, y - off) == pytest.approx(ref.track_position(i, 5), abs=1e-11 * off)
    with pytest.raises(ValueError):
        skeletonator.Skeletonator([(x*1e-6 + 1e7, y*1e-6 + 1e7) for x, y in corpus.rect(10, 10)])


def test_spiral_argument_order_and_finiteness():
    from kicoil import skeletonator
    sk = skeletonator.Skeletonator(corpus.rect(10, 10))
    pts, angles = sk.spiral(0.0, 1.0, 0.0, 3.0)
    rpts, rangles = sk.spiral(1.0, 0.0, 3.0, 0.0)
    assert rpts == pts[::-1] and rangles == angles[::-1]
    with pytest.raises(ValueError):
        sk.spiral(0.0, math.nan, 0.0, 3.0)
    with pytest.raises(ValueError):
        list(sk.iter_vertex_angles(0.0, math.inf))


# ---------------------------------------------------------------------------------------------------------------------
# Keepout outline


def _keepout_polygons():
    import dataclasses
    from kicoil import geometry

    @dataclasses.dataclass
    class Poly(geometry.OffsetShape):
        polygon: list
        annular_width: float

    return [Poly(corpus.neck(40, 20, 8), 2.0), Poly(corpus.u_shape(40, 30, 12), 3.0), Poly(corpus.star(5, 50, 25), 3.0),
            geometry.SectorShape(inner_diameter=6, outer_diameter=40, angle=math.radians(90), annular_width=2.0),
            Poly(corpus.slotted_square(40, 2, 15), 2.0)]


@pytest.mark.parametrize('margin', [1.0, 5.0])
def test_keepout_outline_is_a_valid_outward_offset(margin):
    # The keepout outline was made by extrapolating the skeleton tracks outwards, which self-intersects at notches and
    # small-radius sectors, and makes miter spikes of 16 mm at the tips of a 5-point star for a 5 mm margin.
    from shapely.geometry import Polygon, Point
    for shape in _keepout_polygons():
        pts = shape.offset_exterior(margin)
        keepout = Polygon(pts)
        assert keepout.is_valid
        ref = Polygon(Polygon(shape.polygon).buffer(margin, join_style='mitre', mitre_limit=2.0).exterior)
        assert keepout.symmetric_difference(ref).area < 1e-6 * ref.area
        # Miters are cut off at twice the margin (the ends of the cut are slightly further away than its middle)
        outline = Polygon(shape.polygon)
        assert max(outline.distance(Point(p)) for p in pts) <= 2.1 * margin


def test_keepout_inward_and_circle_unchanged():
    from kicoil import geometry
    rect = geometry.RectangleShape(width=40, height=20, annular_width=3)
    for margin, (x, y) in ((-1, (19, 9)), (1, (21, 11))):
        pts = sorted(rect.offset_exterior(margin))
        assert len(pts) == 4
        for (px, py), (qx, qy) in zip(pts, sorted([(x, -y), (x, y), (-x, y), (-x, -y)])):
            assert math.isclose(px, qx, abs_tol=1e-9) and math.isclose(py, qy, abs_tol=1e-9)
    circle = geometry.CircleShape(20, 10)
    assert all(math.isclose(math.hypot(x, y), 15) for x, y in circle.offset_exterior(5))


# ---------------------------------------------------------------------------------------------------------------------
# Spacing measurement


def _naive_min_turn_spacing(arms, search_radius, min_turn_separation=0.5):
    from kicoil.geometry import _split_by_angle, _seg_seg_distance
    segs = []
    for arm_idx, (points, angles) in enumerate(arms):
        for q1, q2, u1, u2 in _split_by_angle(points, angles, min_turn_separation / 10):
            segs.append((q1, q2, arm_idx, min(u1, u2), max(u1, u2)))
    best = search_radius
    for i, (p1, p2, arm, t_lo, t_hi) in enumerate(segs):
        for q1, q2, arm_j, u_lo, u_hi in segs[i+1:]:
            if arm_j == arm and max(u_lo - t_hi, t_lo - u_hi) < min_turn_separation:
                continue
            best = min(best, _seg_seg_distance(p1, p2, q1, q2))
    return best


@pytest.mark.parametrize('name', ['square40_a0.30_n8k3', 'star5_a0.60_n7k3', 'circle30x6_n5k3', 'rstar1_a0.30_n8k3'])
def test_vectorized_spacing_matches_brute_force(name):
    from kicoil.geometry import min_turn_spacing
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = build_model(spec(name))
    for layer_arms in model.spiral_center_lines():
        if layer_arms:
            for radius in (model.spiral_pitch, 1.5 * model.spiral_pitch):
                assert min_turn_spacing(layer_arms, radius)[0] == pytest.approx(
                        _naive_min_turn_spacing(layer_arms, radius), abs=1e-12)


def test_spacing_measurement_is_fast():
    # The pure Python measurement took 5-16 s for a 100 mm circle and 10-70 s for a 1000 vertex outline.
    import time
    from kicoil import geometry
    poly = corpus.rounded_rect(60, 40, 10, n=250)
    shape = geometry.OffsetShape.__new__(geometry.OffsetShape)
    shape.polygon, shape.annular_width = poly, 12
    geometry.OffsetShape.__post_init__(shape)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        t0 = time.perf_counter()
        geometry.PlanarInductor(shape=geometry.CircleShape(100, 20), turns=41, twists=5, clearance=0.1)
        geometry.PlanarInductor(shape=shape, turns=15, twists=4, clearance=0.15)
        elapsed = time.perf_counter() - t0
    assert elapsed < 10 # about 1 s on a desktop machine


# ---------------------------------------------------------------------------------------------------------------------
# Vias, rendering, export


def test_circle_inner_vias_stay_on_their_side_of_the_center():
    # With vias wider than the hole, the automatic via offset loop pushed the inner vias through the center of a circle
    # (no upper bound), where they swapped sides and the overlap check never fired.
    from kicoil import geometry
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        model = geometry.PlanarInductor(shape=geometry.CircleShape(20, 1), turns=9, twists=2, clearance=0.15,
                                        via_diameter=2.0)
    assert model.inner_via_ring_radius >= -1e-9
    assert model.via_offset <= model.shape.max_via_offset + 1e-9
    assert any('Overlapping vias' in str(x.message) for x in w)
    overlap = [str(x.message) for x in w if 'overlaps a neighboring turn by' in str(x.message)]
    assert overlap and not any('less than the clearance' in m for m in overlap) # the overlap is larger than it


def test_polyline_circle_respects_clearance():
    # Without arcs, circles were rendered with the given 64 segments per turn, and the chords ate up to 16 % of the
    # clearance.
    from kicoil import geometry
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = geometry.PlanarInductor(shape=geometry.CircleShape(50, 25), turns=11, twists=3, clearance=0.15,
                                        approximate_arcs=False)
        fp = model.render_footprint(circle_segments=64)
    intent = geomcheck.intent_from_model(model)
    rep = geomcheck.check_layout(geomcheck.extract_copper(fp, layers=model.layer_pair), intent)
    assert rep.worst_clearance_deficit <= 0.05 * intent.clearance
    assert model.effective_render_options(None, 64)[1] > 64


def test_tightened_render_settings_are_reported(caplog):
    import logging
    from kicoil import geometry
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = geometry.PlanarInductor(shape=geometry.CircleShape(50, 25), turns=5, twists=1, clearance=0.15)
    with caplog.at_level(logging.WARNING, logger='kicoil'):
        model.render_footprint()
    assert not [r for r in caplog.records if 'Overriding' in r.getMessage()]
    with caplog.at_level(logging.WARNING, logger='kicoil'):
        model.render_footprint(arc_tolerance=0.1, circle_segments=32)
    msgs = [r.getMessage() for r in caplog.records if 'Overriding' in r.getMessage()]
    assert any('arc tolerance' in m for m in msgs) and any('circle segments' in m for m in msgs)
    # The arc tolerance and the segment count only apply to circles drawn with arcs / as polylines respectively.
    caplog.clear()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        rect = geometry.PlanarInductor(shape=geometry.RectangleShape(width=50, height=40, annular_width=10), turns=5,
                                       twists=1, clearance=0.2)
        polyline = geometry.PlanarInductor(shape=geometry.CircleShape(50, 25), turns=5, twists=1, clearance=0.15,
                                           approximate_arcs=False)
    with caplog.at_level(logging.WARNING, logger='kicoil'):
        rect.render_footprint(arc_tolerance=0.1, circle_segments=32)
        polyline.render_footprint(arc_tolerance=0.1)
    assert not [r for r in caplog.records if 'Overriding' in r.getMessage()]


@pytest.mark.parametrize('arcs', [False, True])
def test_zero_clearance_renders(arcs):
    # The chord error limit clearance/40 was 0 for clearance 0: ZeroDivisionError in effective_render_options.
    from kicoil import geometry
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = geometry.PlanarInductor(shape=geometry.CircleShape(50, 25), turns=7, twists=4, clearance=0.0,
                                        approximate_arcs=arcs)
        fp = model.render_footprint()
    assert len(fp.arcs if arcs else fp.lines) > 0


@pytest.mark.parametrize('od,idd,n,k,c,arcs', [(200, 190, 11, 3, 0.5, True), (4, 3, 11, 3, 0.05, True),
                                               (50, 25, 11, 3, 0.15, False)])
def test_circle_render_loses_at_most_clearance_over_40(od, idd, n, k, c, arcs):
    # Both neighboring turns may deviate by the arc tolerance / chord error towards each other. With a tolerance of
    # clearance/40 the rendered copper lost up to 4.4 % (arcs, 200/190 mm) and 5.1 % (4/3 mm) of the clearance.
    from kicoil import geometry
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = geometry.PlanarInductor(shape=geometry.CircleShape(od, idd), turns=n, twists=k, clearance=c,
                                        approximate_arcs=arcs)
        fp = model.render_footprint()
    intent = geomcheck.intent_from_model(model)
    rep = geomcheck.check_layout(geomcheck.extract_copper(fp, layers=model.layer_pair), intent, do_conformance=False)
    assert rep.worst_clearance_deficit <= c / 40 + 1e-6


def test_kicad_pcb_export(tmp_path):
    # Board.serialize() failed with a MappingError on the empty legacy footprint list, and the SMD terminal pads were
    # dropped.
    from click.testing import CliRunner
    from gerbonara.cad.kicad.pcb import Board
    from kicoil.cli import cli
    out = tmp_path / 'coil.kicad_pcb'
    res = CliRunner().invoke(cli, ['--format', 'kicad-pcb', '--twists', '3', '--turns', '5', '--clearance', '0.2',
                                   'circle', str(out)])
    assert res.exit_code == 0, res.output
    board = Board.open(out)
    assert len(board.track_arcs) > 0
    assert len(board.vias) == 2 + 3 # inner ring 3, outer ring 2 (the third outer position holds the pads)
    pads = [p for fp in board.footprints for p in fp.pads]
    assert sorted(p.number for p in pads) == ['1', '2']
    copper = {'F.Cu', 'B.Cu'}
    assert {a.layer for a in board.track_arcs} <= copper and {s.layer for s in board.track_segments} <= copper
    assert all(set(v.layers) == copper for v in board.vias)
    res = CliRunner().invoke(cli, ['--format', 'kicad-pcb', '--twists', '2', '--turns', '5', '--clearance', '0.2',
                                   'rectangle', str(out)])
    assert res.exit_code == 0, res.output
    board = Board.open(out)
    assert len(board.track_segments) > 0
    # gerbonara's TrackSegment.from_footprint_line swaps layer and locked: every segment was written on layer "False".
    assert {s.layer for s in board.track_segments} == copper
    assert not any(s.locked for s in board.track_segments)
    # Single layer: the bridge is the only straight segment, on the back layer.
    res = CliRunner().invoke(cli, ['--format', 'kicad-pcb', '--single-layer', '--turns', '5', '--clearance', '0.2',
                                   'circle', str(out)])
    assert res.exit_code == 0, res.output
    board = Board.open(out)
    assert [s.layer for s in board.track_segments] == ['B.Cu']
    assert {a.layer for a in board.track_arcs} == {'F.Cu'}


def test_error_messages_give_the_measured_spacing():
    # Trace width and clearance both given: the message used to say "Reduce clearance" and gave no hint about the
    # measured spacing, which is smaller than the nominal pitch at the corners.
    from kicoil import geometry
    with pytest.raises(ValueError) as e:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            geometry.PlanarInductor(shape=geometry.RectangleShape(width=50, height=40, annular_width=10), turns=10,
                                    twists=3, trace_width=1.75, clearance=0.2)
    msg = str(e.value)
    assert 'Reduce trace width' in msg and '1.885 mm' in msg and 'measured near' in msg


# ---------------------------------------------------------------------------------------------------------------------
# Narrow features of the outline


@pytest.mark.parametrize('name', ['narrow_tshape_w5.0_n4k1', 'narrow_tshape_w5.0_n7k3', 'narrow_finger_w6.0_n5k2',
                                  'narrow_keyhole_w7.0_n7k3', 'narrow_finger_w6.0_n9k4'])
def test_vanishing_protrusion_is_cut(name):
    # The two sides of a protrusion that collapses inside the annulus (stem of a T, finger, keyhole tab) used to be
    # followed by turns just above the collapse depth, so that the turn's copper folded onto itself along the whole
    # protrusion (clearance deficit up to 18x the clearance, path touching itself).
    model, intent, rep = layout(spec(name))
    assert rep.ok_connectivity and rep.crossings == 0 and rep.backtracks == 0
    assert rep.worst_clearance_deficit <= 0.05 * intent.clearance + 1e-4


def test_fold_around_narrow_notch_is_reported():
    caught = []
    model, intent, rep = layout(spec('narrow_slot_w10.0_n4k1'), caught)
    assert rep.ok_connectivity and rep.crossings == 0
    assert any(FOLD_WARNING in m for m in caught)


@pytest.mark.parametrize('name', ['narrow_stepped_w4.0_n4k1', 'narrow_stepped_w6.0_n4k1', 'narrow_branch_w3.0_n7k3',
                                  'narrow_branch_w6.0_n4k1'])
def test_nested_protrusions_are_cut_at_every_mouth(name):
    # The protrusion cut stopped after the first protrusion a track passes through: the tips of a narrow finger on top
    # of a wider one (or of a side branch) were cut at the inner mouth only and still ran up the outer protrusion's
    # axis, while the other vertices of the outer protrusion were cut at its mouth. One turn then ran up the axis and
    # straight back, a zero-width hairpin (connectivity broken, reported as a branch).
    model, intent, rep = layout(spec(name))
    assert rep.ok_connectivity and rep.branches == 0 and rep.crossings == 0 and rep.backtracks == 0
    assert rep.worst_clearance_deficit <= 0.05 * intent.clearance + 1e-4


def test_bent_protrusion_is_cut_on_its_mouth():
    # The tips of a protrusion moved along the direction from their own entry into the collapsed group to its exit,
    # which is oblique for an L-shaped protrusion: they landed 0.6 mm inside the outline, the measured spacing dropped
    # to 61 % of the pitch and the whole coil got a 45 % thinner trace than with a straight finger of the same width.
    sq = [(-20, -20), (20, -20), (20, 20)]
    straight = sq + [(2, 20), (2, 32), (-2, 32), (-2, 20), (-20, 20)]
    bent = sq + [(2, 20), (2, 28), (12, 28), (12, 32), (-2, 32), (-2, 20), (-20, 20)]
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        w_straight = build_model(poly_spec(straight, 6, 13, 3)).trace_width
        model, intent, rep = layout(poly_spec(bent, 6, 13, 3))
    assert model.trace_width >= 0.98 * w_straight
    assert rep.ok_connectivity and rep.crossings == 0 and rep.worst_clearance_deficit <= 1e-4


def test_fold_at_tapered_finger_is_reported():
    # A turn running into a tapered finger and back: its copper overlapped itself (0.04 mm) at pieces 18.2 mm apart
    # along the conductor, which the checker counts as a clearance violation. The fold test only looked at pieces more
    # than pi*d + pitch = 19.3 mm apart and did not warn.
    poly = [(-20.0, -20.0), (20.0, -20.0), (20.0, 20.0), (-4.487019801766503, 20.0), (-6.0495799658954175, 28.436328047481098),
            (-9.675310650842189, 28.436328047481098), (-11.237870814971103, 20.0), (-20.0, 20.0)]
    caught = []
    model, intent, rep = layout(poly_spec(poly, 15.87099714894963, 5, 3), caught)
    assert rep.ok_connectivity and rep.crossings == 0
    assert any(FOLD_WARNING in m for m in caught)


def _naive_folds(arms, search_radius, min_turn_separation=0.5):
    """ Brute force fold candidates: pairs of pieces of the same turn with their distance d and their separation along
    the conductor, if that is more than pi*d. Pieces are split like in min_turn_spacing. """
    from kicoil.geometry import _split_by_angle, _seg_seg_distance
    out = []
    for points, angles in arms:
        pieces, s = [], 0.0
        for q1, q2, u1, u2 in _split_by_angle(points, angles, min_turn_separation / 10):
            l = math.dist(q1, q2)
            n = max(1, math.ceil(l / (4 * search_radius)))
            for k in range(n):
                a = (q1[0] + (q2[0]-q1[0])*k/n, q1[1] + (q2[1]-q1[1])*k/n)
                b = (q1[0] + (q2[0]-q1[0])*(k+1)/n, q1[1] + (q2[1]-q1[1])*(k+1)/n)
                pieces.append((a, b, min(u1, u2), max(u1, u2), s + l*k/n, s + l*(k+1)/n))
            s += l
        for i, (a, b, tlo, thi, s0, s1) in enumerate(pieces):
            for c, d_, ulo, uhi, r0, r1 in pieces[i+1:]:
                if max(ulo - thi, tlo - uhi) >= min_turn_separation:
                    continue
                d = _seg_seg_distance(a, b, c, d_)
                path = max(r0 - s1, s0 - r1)
                if d < search_radius and path > math.pi * d + 1e-9 * search_radius:
                    out.append((d, path))
    return out


@pytest.mark.parametrize('name', ['narrow_slot_w10.0_n4k1', 'narrow_taper_w15.9_n5k2', 'sector180_a0.90_n3k1',
                                  'ellipse3to1_a0.90_n16k5'])
def test_fold_candidates_match_brute_force(name):
    # The chunked search skips pairs of chunks that cannot hold a fold candidate; it must find the same ones.
    from kicoil.geometry import min_turn_spacing
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        try:
            model = build_model(spec(name))
        except ValueError:
            pytest.skip('rejected')
    R = model.spiral_pitch
    found = 0
    for layer_arms in model.spiral_center_lines():
        if not layer_arms:
            continue
        _best, _where, fold_best, _fold_where, front = min_turn_spacing(layer_arms, R, folds=True)
        naive = _naive_folds(layer_arms, R)
        found += len(naive)
        assert fold_best == pytest.approx(min([d for d, p in naive if p > math.pi*d + R], default=R), abs=1e-12)
        for min_path in (0.5*R, R, 2*R, 4*R, 8*R):
            assert front.closest(min_path)[0] == pytest.approx(
                    min([d for d, p in naive if p > min_path], default=math.inf), abs=1e-12)
    assert found # every one of these cases has turns that come back close to themselves


def test_spacing_measurement_dense_outline_few_turns():
    # A finely subdivided outline with few turns (an SVG import) puts thousands of pieces of one turn into each grid
    # cell of the spacing search: all pairs of a cell were built at once (2.4 GB and 20 s for 16000 points). The pieces
    # are now paired chunk by chunk and pairs of one turn are skipped per chunk.
    import time
    import tracemalloc
    from kicoil.geometry import min_turn_spacing
    N = 16000
    pts, ang = [], []
    for i in range(N + 1):
        t = i / N
        r = 30 - 20 * t
        pts.append((r * math.cos(2 * math.pi * t), r * math.sin(2 * math.pi * t)))
        ang.append(t)
    tracemalloc.start()
    t0 = time.perf_counter()
    best, _where = min_turn_spacing([(pts, ang)], 20.0)
    elapsed = time.perf_counter() - t0
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert best == pytest.approx(19.662, abs=1e-3)
    assert peak < 400e6 and elapsed < 10 # about 0.1 GB and 0.5 s
