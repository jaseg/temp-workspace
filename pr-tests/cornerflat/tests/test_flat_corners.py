"""Tests for the flat corner layout (Skeletonator.flat_corners) and the arm phase."""

import dataclasses
import math
import warnings

import pytest
import shapely

import corpus
import run_corpus
from kicoil import geometry


def _model(shape, turns=8, twists=3, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return geometry.PlanarInductor(shape=shape, turns=turns, twists=twists, clearance=0.2, **kw)


@pytest.fixture
def square():
    return geometry.RectangleShape(width=40, height=40, annular_width=12)


def test_turns_run_at_constant_depth_around_corners(square):
    _model(square)
    assert square.layout is not square.sk
    points, _angles = square.layout.spiral(0.0, 2.0, 0.0, 6.0)
    ring = shapely.LinearRing(square.polygon)
    depths = [ring.distance(shapely.Point(p)) for p in points]
    # The depth changes on one ramp per edge and revolution, and nowhere else
    changes = sum(not math.isclose(a, b, abs_tol=1e-4) for a, b in zip(depths, depths[1:]))
    assert changes == 2 * len(square.polygon)
    assert depths[0] == pytest.approx(0) and depths[-1] == pytest.approx(6)


def test_flat_corners_widen_the_turn_spacing(square):
    model = _model(square)
    assert model.measure_turn_spacing()[0] >= 0.99 * model.spiral_pitch
    # The linear layout slopes across the corners, where neighboring turns come closer
    linear = _model(square, flat_corners=False)
    assert square.layout is square.sk
    assert linear.measure_turn_spacing()[0] < 0.95 * linear.spiral_pitch


def test_shared_shape_keeps_each_coils_layout(square):
    # The GUI's worker keeps the shape between jobs: rendering a coil after another one used the shape must give the
    # same footprint as before
    def lines(fp):
        return [(line.start.x, line.start.y, line.end.x, line.end.y) for line in fp.lines]
    a = _model(square, 8, 3)
    before = lines(a.render_footprint())
    _model(square, 5, 2, flat_corners=False)
    assert lines(a.render_footprint()) == before


@pytest.mark.parametrize('name', ['rect40x20_a0.30_n13k1', 'l_shape_a0.60_n21k8'])
def test_vias_at_flat_corners_clear_the_turns(name):
    # Here an arm ends where the flat stretch around a corner begins, at the end of a ramp. The via has to sit at the
    # corner of the deeper (inner via, convex corner) or the outward (outer via, reflex corner) offset: on the line of
    # the ramp's end it came within 0.006 and 0.022 mm of the neighboring turn.
    spec = next(c for c in corpus.corpus('full') if c['name'] == name)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = run_corpus.build_model(spec)
    assert model.shape.layout is not model.shape.sk
    assert model.via_track_clearance()[0] >= model.clearance - 1e-6


def test_arm_phase_rotates_the_arms(square):
    def starts(model):
        arms = [model.shape.compute_spiral(*model.arm_angles(i)[:2]) for i in range(model.twists)]
        return sorted((round(x, 9), round(y, 9)) for x, y in (points[0] for points, _ in arms))
    base = starts(_model(square))
    assert starts(_model(square, arm_phase=360 / 3)) == base
    assert starts(_model(square, arm_phase=30)) != base


def test_debug_arms_mark_start_end_and_vertices(square):
    _model(square)
    square.sk.debug_arms.clear()
    square.layout.spiral(0.0, 2.0, 0.0, 6.0, debug=True)
    (arm, inward, _t1, _t2), = square.sk.debug_arms
    kinds = [kind for _p, kind, _start, _r, _i in arm]
    assert kinds[0] == 1 and kinds[-1] == 2 and set(kinds[1:-1]) == {3}
    assert arm[0][3] == pytest.approx(square.sk.radius) and arm[-1][3] == pytest.approx(square.sk.radius - 6.0)
    # two revolutions pass every corner twice (one of them may be the start point)
    assert sum(i is not None for _p, _k, _s, _r, i in arm) >= 2 * len(square.polygon) - 1
