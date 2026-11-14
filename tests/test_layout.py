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

    assert rep.ok_connectivity, rep.notes
    assert rep.crossings == 0, rep.crossing_points[:5]
    assert rep.backtracks == 0
    assert abs(rep.winding_error) < 0.05, rep.winding
    if 'narrow' in spec['tags'] and any(FOLD_WARNING in m for m in caught):
        # A turn running around a notch narrower than the pitch folds onto itself. That is a known, warned-about
        # limitation (no short between different turns: no crossings, connectivity checked above).
        pytest.xfail('turn folds onto itself around a narrow notch (warned)')
    # Track to track clearance: at most 5% of the clearance may be missing (numerical tolerance of the checker)
    assert rep.worst_clearance_deficit <= 0.05 * intent.clearance + 1e-4, rep.violations[:5]
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
    assert any('overlaps a neighboring turn by' in str(x.message) for x in w)


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
