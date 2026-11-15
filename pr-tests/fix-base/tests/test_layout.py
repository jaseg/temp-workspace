"""Geometric layout checks over the test corpus, plus regression tests for specific layout bugs (see docs/DEFECTS.md).

Run with `uv run --group dev pytest tests`. The full corpus is behind `--full-corpus` (see conftest.py); the default run
uses the quick subset.
"""

import json
import math
import warnings
from pathlib import Path

import pytest

import corpus
import geomcheck
from run_corpus import build_model


def layout(spec, caught=None, impl='kicoil'):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        model = build_model(spec, impl)
        fp = model.render_footprint()
    if caught is not None:
        caught.extend(str(x.message) for x in w)
    intent = geomcheck.intent_from_model(model)
    copper = geomcheck.extract_copper(fp, layers=model.layer_pair)
    return model, intent, geomcheck.check_layout(copper, intent)


# Failure kinds of corpus cases that are known limitations of the layout (outline features narrower than the trace,
# see tests/README.md), as found by run_corpus.py on the full corpus: {case name: [failure kinds]}. Conformance is not
# asserted by test_corpus_case and not listed.
KNOWN_FAILURES = json.loads((Path(__file__).parent / 'data' / 'known_failures.json').read_text())


def pytest_generate_tests(metafunc):
    if 'spec' in metafunc.fixturenames:
        full = metafunc.config.getoption('--full-corpus')
        cases = corpus.corpus('full' if full else 'quick')
        metafunc.parametrize('spec', cases, ids=[c['name'] for c in cases])


def test_corpus_case(spec):
    try:
        model, intent, rep = layout(spec)
    except ValueError as e:
        # Rejecting an infeasible request with a clear message is fine, crashing is not.
        pytest.skip(f'rejected: {e}')

    # Every check of the geometric checker except outline coverage, which the linear spiral does not reach at convex
    # corners of deep annuli (that is measured by run_corpus.py, not asserted here).
    kinds = [k for k in rep.failure_kinds(intent.clearance, intent.trace_width) if k != 'conformance']
    known = set(KNOWN_FAILURES.get(spec['name'], ()))
    if spec.get('known_issue'):
        # A documented limitation of the layout for this outline (see the corpus module that defines the case)
        known |= set(spec['known_issue']['kinds'])
        kinds += ['overshoot'] if rep.overshoot >= max(0.05, 0.1 * intent.trace_width) else []
        kinds += ['contour'] if rep.contour_hausdorff >= 1.5 and not _cut_protrusions(model, intent) else []
    known |= set(spec.get('known_failures', {}))
    unexplained = [k for k in kinds if k not in known]
    assert not unexplained, (unexplained, rep.notes[:5], rep.violations[:5])
    if kinds:
        pytest.xfail(f'known: {kinds}')
    # The copper must stay within the intended outline
    assert rep.overshoot < max(0.05, 0.1 * intent.trace_width)
    if not _cut_protrusions(model, intent):
        # (Turns do not run into protrusions narrower than two turns, those parts of the outline stay uncovered)
        assert rep.contour_hausdorff < 1.5


def _cut_protrusions(model, intent):
    return [c for c in getattr(getattr(model.shape, 'sk', None), 'cut_protrusions', ()) if c[3] < intent.annular_width]


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
    import shapely
    from kicoil import skeletonator
    cw = [(0., 0.), (0., 10.), (10., 10.), (10., 0.)]
    # A path that repeats its start point used to be classified as counter-clockwise
    sk = skeletonator.Skeletonator(cw + [cw[0]])
    assert len(sk.poly) == 4 and shapely.is_ccw(shapely.LinearRing(sk.poly))
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


def _naive_min_turn_spacing(arms, search_radius, min_turn_separation=0.5):
    """ Every pair of segment pieces of at most a twentieth of min_turn_separation in angle """
    import numpy as np
    import shapely
    segs, arm, lo, hi = [], [], [], []
    for k, (points, angles) in enumerate(arms):
        for (p, q), (a, b) in zip(zip(points, points[1:]), zip(angles, angles[1:])):
            n = max(1, math.ceil(abs(b - a) / (min_turn_separation / 20)))
            for i in range(n):
                segs.append([(p[0] + (q[0]-p[0])*i/n, p[1] + (q[1]-p[1])*i/n),
                             (p[0] + (q[0]-p[0])*(i+1)/n, p[1] + (q[1]-p[1])*(i+1)/n)])
                arm.append(k)
                lo.append(min(a, b) + abs(b - a)*i/n)
                hi.append(min(a, b) + abs(b - a)*(i+1)/n)
    geoms, arm, lo, hi = shapely.linestrings(segs), np.array(arm), np.array(lo), np.array(hi)
    best = search_radius
    for i in range(len(geoms) - 1):
        j = np.arange(i + 1, len(geoms))
        j = j[(arm[j] != arm[i]) | (np.maximum(lo[j] - hi[i], lo[i] - hi[j]) >= min_turn_separation)]
        if len(j):
            best = min(best, float(shapely.distance(geoms[i], geoms[j]).min()))
    return best


@pytest.mark.parametrize('name', ['square40_a0.30_n8k3', 'star5_a0.60_n7k3', 'circle30x6_n5k3', 'rstar1_a0.30_n8k3'])
def test_spacing_matches_brute_force(name):
    from kicoil.geometry import min_turn_spacing
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = build_model(spec(name))
    for layer_arms, chunks in zip(model.spiral_center_lines(), model._chunks):
        if layer_arms:
            for radius in (model.spiral_pitch, 1.5 * model.spiral_pitch):
                assert min_turn_spacing(chunks, radius)[0] == pytest.approx(
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


def test_circle_inner_vias_stay_on_their_side_of_the_center():
    # With vias wider than the hole, the automatic via offset loop pushed the inner vias through the center of a circle
    # (no upper bound), where they swapped sides and the overlap check never fired.
    # The two 2 mm vias in the 1 mm hole overlap each other even on the innermost turn, which shorts the arms: since
    # D33 the request is rejected instead of warned. The vias it names are on opposite sides of the center.
    from kicoil import geometry
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        with pytest.raises(geometry.OverlappingViasError,
                           match=r'the vias at \(0\.000, 0\.500\) and \(-0\.000, -0\.500\) are 1\.000 mm apart'):
            geometry.PlanarInductor(shape=geometry.CircleShape(20, 1), turns=9, twists=2, clearance=0.15,
                                    via_diameter=2.0)
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


@pytest.mark.parametrize('name', ['narrow_tshape_w5.0_n4k1', 'narrow_tshape_w5.0_n7k3', 'narrow_finger_w6.0_n5k2',
                                  'narrow_keyhole_w7.0_n7k3', 'narrow_finger_w6.0_n9k4'])
def test_vanishing_protrusion_is_cut(name):
    # The two sides of a protrusion that collapses inside the annulus (stem of a T, finger, keyhole tab) used to be
    # followed by turns just above the collapse depth, so that the turn's copper folded onto itself along the whole
    # protrusion (clearance deficit up to 18x the clearance, path touching itself).
    model, intent, rep = layout(spec(name))
    assert rep.ok_connectivity and rep.crossings == 0 and rep.backtracks == 0
    assert rep.worst_clearance_deficit <= 0.05 * intent.clearance + 1e-4


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


def test_spacing_measurement_dense_outline_few_turns():
    # A finely subdivided outline with few turns (an SVG import) puts thousands of pieces of one turn into each grid
    # cell of the spacing search: all pairs of a cell were built at once (2.4 GB and 20 s for 16000 points). The pieces
    # are now paired chunk by chunk and pairs of one turn are skipped per chunk.
    import time
    import tracemalloc
    from kicoil.geometry import center_line_chunks, min_turn_spacing
    N = 16000
    pts, ang = [], []
    for i in range(N + 1):
        t = i / N
        r = 30 - 20 * t
        pts.append((r * math.cos(2 * math.pi * t), r * math.sin(2 * math.pi * t)))
        ang.append(t)
    tracemalloc.start()
    t0 = time.perf_counter()
    best, _where = min_turn_spacing([center_line_chunks(pts, ang, 0.025)], 20.0)
    elapsed = time.perf_counter() - t0
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert best == pytest.approx(19.662, abs=1e-3)
    assert peak < 400e6 and elapsed < 10 # about 0.1 GB and 0.5 s


def _smooth_blob(d, n, seed, order=5, amp=0.15, decimals=None):
    """ Star-shaped smooth blob with n vertices (low order Fourier radius); with decimals, the coordinates are rounded
    like those of an SVG or DXF import """
    import random
    rng = random.Random(seed)
    coef = [(rng.uniform(-amp, amp) / k, rng.uniform(0, 2*math.pi)) for k in range(2, order+1)]
    pts = []
    for i in range(n):
        t = 2*math.pi*i/n
        r = d/2 * (1 + sum(a*math.cos(k*t + ph) for k, (a, ph) in zip(range(2, order+1), coef)))
        p = (r*math.cos(t), r*math.sin(t))
        if decimals is not None:
            p = (round(p[0], decimals), round(p[1], decimals))
        if not pts or p != pts[-1]:
            pts.append(p)
    if pts[-1] == pts[0]:
        pts.pop()
    return pts


ANGLE_REFERENCE_CASES = ['ellipse3to1_a0.90_n16k5', 'sector180_a0.30_n8k3', 'star5_a0.30_n8k3', 'neck_a0.30_n5k2',
                         'chamfer_tiny_a0.30_n8k3', 'sector90_a0.30_n5k2', 'narrow_tshape_w5.0_n7k3',
                         'narrow_stepped_w4.0_n4k1', 'narrow_branch_w3.0_n7k3', 'narrow_lfinger_w3.0_n9k4',
                         'narrow_slot_w10.0_n4k1']


def _min_edge_lengths_bruteforce(sk, max_depth):
    """ Every edge at depth 0, max_depth and every node time of all tracks in between """
    times = sorted({n.time for t in sk.tracks for n in t if 0 < n.time < max_depth} | {0.0, max_depth})
    n = len(sk.poly)
    out = [math.inf] * n
    for d in times:
        pts = [sk.track_position(i, d) for i in range(n)]
        out = [min(out[i], math.dist(pts[i], pts[(i+1) % n])) for i in range(n)]
    return out


@pytest.mark.parametrize('name', ANGLE_REFERENCE_CASES)
def test_edge_lengths_match_brute_force(name):
    # set_angle_reference evaluated every edge at every node time of all tracks (quadratic, 35 s for a 2500 vertex
    # outline). The fast version only looks at the edge's own tracks until they meet; it must give the same lengths,
    # also on tracks cut at protrusions.
    from kicoil import skeletonator
    s = spec(name)
    sk = skeletonator.Skeletonator(s['polygon'])
    pitch = s['annular_width'] / (s['turns'] / s['layers'])
    for limit in (0.0, pitch / 2):
        sk.set_fold_limit(limit)
        for depth in (s['annular_width'], sk.max_depth, 0.5 * s['annular_width']):
            fast = sk._min_edge_lengths(depth)
            brute = _min_edge_lengths_bruteforce(sk, depth)
            assert max(abs(a - b) for a, b in zip(fast, brute)) <= 1e-15 * sum(brute)


def test_angle_reference_is_linear_on_smooth_outlines(monkeypatch):
    # On a smooth outline all vertex tracks run to the center, so the old set_angle_reference called track_position
    # n times for each of about n node times (6.3 million calls for 2500 vertices). It also ran again for every call
    # of set_fold_limit, although nothing was cut.
    from kicoil import skeletonator
    poly = _smooth_blob(40, 1000, 7)
    calls = {'track_position': 0, 'min_edge_lengths': 0}
    track_position = skeletonator.Skeletonator.track_position
    min_edge_lengths = skeletonator.Skeletonator._min_edge_lengths
    def counting_track_position(self, i, depth):
        calls['track_position'] += 1
        return track_position(self, i, depth)
    def counting_min_edge_lengths(self, depth):
        calls['min_edge_lengths'] += 1
        return min_edge_lengths(self, depth)
    monkeypatch.setattr(skeletonator.Skeletonator, 'track_position', counting_track_position)
    monkeypatch.setattr(skeletonator.Skeletonator, '_min_edge_lengths', counting_min_edge_lengths)
    sk = skeletonator.Skeletonator(poly)
    assert sum(len(t) for t in sk.tracks) > 100 * len(poly) # long tracks
    assert calls['track_position'] < 30 * len(poly)
    angles = list(sk.vertex_angles)
    sk.set_fold_limit(1.0) # nothing to cut
    sk.set_angle_reference(sk.max_depth) # same depth
    assert calls['min_edge_lengths'] == 1 and sk.vertex_angles == angles
    sk.set_angle_reference(0.5 * sk.max_depth)
    assert calls['min_edge_lengths'] == 2


@pytest.mark.parametrize('poly', [[(0, 0), (20, 0), (0, 10), (0, -5)],
                                  [(0, 0), (10, 0), (10, 10), (5, 0), (0, 10)],
                                  [(0, 0), (10, 0), (10, 10), (5, 5), (10, 10), (0, 10)]])
def test_self_intersecting_outline_is_a_value_error(poly):
    # skeleton.wasm aborts on a CGAL precondition, which surfaced as a wasmtime Trap
    from kicoil import skeletonator
    with pytest.raises(ValueError, match='not a simple polygon'):
        skeletonator.Skeletonator(poly)


def test_fold_at_thin_inner_tip_is_a_same_turn_fold():
    # 60 x 20 ellipse, 90 % annular width: the innermost turn runs around the thin tip of the inner contour and comes
    # back 3.56 mm away on the other side (0.045 turns further in winding angle, 14.5 mm along the conductor). The
    # checker counts this fold of one turn as a self overlap. Before it decided by winding angle alone, the 14.5 mm path
    # distance (more than 4 x (trace width + clearance) = 14.36 mm) made it a clearance violation between turns.
    poly = corpus.ellipse(60, 20, 512)
    model, intent, rep = layout(poly_spec(poly, round(0.9 * corpus.max_depth(poly), 4), 5, 1))
    assert rep.clearance_violations == 0 and rep.self_overlaps > 0 and rep.self_shorts == 0
    assert rep.failure_kinds(intent.clearance, intent.trace_width) == []


@pytest.mark.parametrize('name, pair', [
    ('round_ellipse20to1_a0.90_n16k5', '(-10.449, -0.130) and (-10.449, 0.130)'),
    ('round_ellipse10to1_a0.90_n16k5', '(-7.808, -0.196) and (-7.808, 0.196)')])
def test_overlapping_vias_rejected(name, pair):
    # 90 % of a slender ellipse, 5 arms: the inner contour is a sliver, and the automatic via offset (0.2 mm, up to the
    # collapse depth) used to put all five inner vias at (0, 0) of the 20:1 ellipse, and two at (-7.389, 0) of the 10:1
    # one, which shorted the arms (only a warning). Pulled back to the innermost turn, two vias on opposite sides of the
    # sliver are still closer than the via diameter: no placement keeps them apart, so the request is rejected.
    with pytest.raises(ValueError, match=r'Overlapping vias: the vias at .* would short the arms') as e:
        build_model(spec(name))
    assert pair in str(e.value)


def test_overlapping_vias_rejected_circle():
    # The same for a circle with a 1 mm hole and 5 arms: the inner vias are 0.59 mm apart even on the innermost turn
    with pytest.raises(ValueError, match='Overlapping vias'):
        build_model(corpus._spec('custom', 'circle', 16, 5, outer_diameter=20, inner_diameter=1.0))


def test_via_offset_pulled_back_to_keep_vias_apart():
    # 60 x 6 ellipse, 60 % annular width, 21 turns, 8 arms: at the automatic via offset (0.289 mm) two inner vias sit
    # 0.623 mm apart on opposite sides of the sliver-shaped inner contour. The offset is reduced to where the smallest
    # gap (via to via or via to the neighboring turn) is largest: 0.714 mm apart, 0.105 mm from the neighboring turn.
    caught = []
    model, intent, rep = layout(spec('round_ellipse10to1_a0.60_n21k8'), caught)
    assert model.via_offset == pytest.approx(0.2441, abs=1e-3)
    assert model.via_ring_spacing()[0] == pytest.approx(0.714, abs=1e-3)
    assert rep.ok_connectivity and rep.worst_via_deficit < 0.05
    assert any(m.startswith('Overlapping vias') and '0.714 mm apart' in m for m in caught)


@pytest.mark.parametrize('name', ['round_ellipse10to1_a0.60_n8k3', 'round_ellipse10to1_a0.60_n6_1layer',
                                  'round_ellipse20to1_a0.30_n5k1'])
def test_arm_ends_at_via(name):
    # The arm that ends at the sharp tip of a sliver-shaped inner contour (fold point (23.879, 0) of the 60 x 6
    # ellipse) has its via 1.36 mm back along the tip's spine: at the tip the neighboring turn's sides are only 0.45 mm
    # from the spine and converge at about 6 degrees, so a via there has no clearance. The connection from the tip back
    # to the via ran over the arm's own copper (a backtrack); now the arm ends where it passes the via.
    model, intent, rep = layout(spec(name))
    assert rep.backtracks == 0, rep.notes
    assert rep.failure_kinds(intent.clearance, intent.trace_width) == []


def test_arm_trim_at_via():
    from kicoil.geometry import _trim_arm_at_via
    arm = [(0, 0), (5, 0), (5, 1), (10, 1)]
    # via back along the last piece: the arm ends at the point closest to the via
    assert _trim_arm_at_via(arm, (8, 1.2)) == [(0, 0), (5, 0), (5, 1), (8.0, 1.0)]
    assert _trim_arm_at_via(arm, (5.1, 0.5)) == [(0, 0), (5, 0), (5.0, 0.5)]
    # via ahead or to the side of the arm end: unchanged
    assert _trim_arm_at_via(arm, (10, -1)) == arm
    assert _trim_arm_at_via(arm, (11, 1.2)) == arm


@pytest.mark.parametrize('name', ['rstar0_a0.90_n3k1', 'pentagon_a0.90_n3k1'])
def test_via_arrival_is_not_a_self_short(name):
    # 90 % annular width, 3 turns: the wide trace (7.2 and 8.5 mm) curves tightly around the small inner contour into
    # its via (as wide as the trace), and its copper overlaps the via for 7 to 10 mm back along the conductor (0.18 to
    # 0.42 turns around the center). Followed from the via, that copper never leaves the via's reach: it is the
    # conductor's own arrival, a single piece of copper that the via adds nothing to, not a self short (checker).
    _model, _intent, rep = layout(spec(name))
    assert not rep.own_via_shorts, rep.notes


def _tri15(f):
    # An isosceles triangle with a 15 degree apex, 50 mm tall, annular width f * split depth, 13 turns, 4 twists
    import corpus_concave as cc
    from shapely.geometry import Polygon
    b = 2*50*math.tan(math.radians(7.5))
    poly = cc._ccw_coords(cc._centered(Polygon([(0, 50), (-b/2, 0), (b/2, 0)])))
    return dict(name=f'tri15_f{f}', shape='polygon', polygon=poly, annular_width=round(f*cc.split_depth(poly), 4),
                turns=13, twists=4, layers=2, clockwise=False, clearance=0.15, trace_width=None, tags=[])


@pytest.mark.parametrize('f', [0.70, 0.72, 0.75, 0.78])
def test_tip_merge_at_the_inner_via_is_gone(f):
    # Triangle with a 15 degree apex, 13 turns, 4 twists: the innermost arm used to run past its inner via into the
    # apex and its copper merged with the via's over 6.6-7.2 (w + c), a self merge. The arm now ends where it passes
    # its via (geometry._trim_arm_at_via), so the hairpin at the apex merges only locally (below 5 (w + c)).
    model, intent, rep = layout(_tri15(f))
    assert 'self merge' not in rep.failure_kinds(intent.clearance, intent.trace_width)
    assert rep.max_self_touch_bypass < 5 * (model.trace_width + model.clearance)



@pytest.mark.parametrize('turns, twists', [(5, 2), (7, 3)])
def test_single_layer_with_several_twists(turns, twists):
    # Single-layer coils keep the requested twists (upstream 89b0829, before they were reset to one). The layouts are
    # valid, but the outline coverage (not asserted) is often worse than with one twist, see docs/DEFECTS.md (D12).
    for name, (poly, _tags) in corpus.base_shapes().items():
        try:
            _model, intent, rep = layout(poly_spec(poly, round(0.6 * corpus.max_depth(poly), 4), turns, twists,
                                                   layers=1))
        except ValueError:
            continue # (e.g. the annular width is beyond a split of the outline)
        kinds = rep.failure_kinds(intent.clearance, intent.trace_width)
        assert set(kinds) <= {'conformance'}, (name, kinds)
