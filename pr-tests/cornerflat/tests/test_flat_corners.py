"""Tests for the flat corner layout (skeletonator.FlatCorners) and the choice among layouts in PlanarInductor."""

import warnings

import numpy as np
import pytest

from kicoil import geometry


def _model(shape, turns=8, twists=3):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return geometry.PlanarInductor(shape=shape, turns=turns, twists=twists, clearance=0.2)


@pytest.fixture
def square():
    return geometry.RectangleShape(width=40, height=40, annular_width=12)


def _flat_layouts(shape):
    return {mode: layout for mode, layout in shape.layouts.items() if mode != 'linear'}


def test_warp_is_monotone_and_unwarp_inverts_it(square):
    _model(square)
    assert _flat_layouts(square)
    for layout in _flat_layouts(square).values():
        t = np.linspace(-1, 2, 3001)
        w = np.array([layout.warp(x) for x in t])
        assert np.all(np.diff(w) >= -1e-12)
        assert np.allclose([layout.warp(x + 1) - layout.warp(x) for x in t[:300]], 1)
        for x in np.linspace(-1, 2, 301):
            assert layout.warp(layout.unwarp(x)) == pytest.approx(x, abs=1e-9)


def test_turns_run_at_constant_depth_around_corners(square):
    _model(square)
    for layout in _flat_layouts(square).values():
        # The depth of an arm is linear in the warped angle, which does not change around any corner
        for a in layout.vertex_angles:
            assert layout.warp(a - 1e-6) == pytest.approx(layout.warp(a + 1e-6), abs=1e-12)
        # and changes on the ramps only
        assert all(o > 0 for o in layout.omega)
        assert sum(layout.omega) == pytest.approx(1)


def test_flat_corners_widen_the_turn_spacing(square):
    model = _model(square)
    assert model.layout_key[0] != 'linear'
    assert model.projected_spiral_pitch >= 0.99 * model.spiral_pitch
    # The linear layout slopes across the corners, where neighboring turns come closer
    assert model._spacing_of(('linear', 0.0)) < 0.95 * model.spiral_pitch


def test_next_layout_when_the_vias_do_not_clear(square, monkeypatch):
    first = _model(square).layout_key
    vias_ok = geometry.PlanarInductor._vias_ok
    monkeypatch.setattr(geometry.PlanarInductor, '_vias_ok', lambda self: self.layout_key != first and vias_ok(self))
    assert _model(square).layout_key not in (first, None)
    # If no candidate clears, the best one is used (and the via placement warns)
    monkeypatch.setattr(geometry.PlanarInductor, '_vias_ok', lambda self: False)
    assert _model(square).layout_key == first


def test_shared_shape_keeps_each_coils_layout(square):
    # The GUI's worker keeps the shape between jobs: rendering a coil after another one used the shape must give the
    # same footprint as before
    def lines(fp):
        return [(line.start.x, line.start.y, line.end.x, line.end.y) for line in fp.lines]
    a = _model(square, 8, 3)
    before = lines(a.render_footprint())
    b = _model(square, 5, 2)
    assert b.layout_key != a.layout_key or b.spiral_pitch != a.spiral_pitch
    assert lines(a.render_footprint()) == before


def test_vias_clear_the_copper_that_comes_back_to_them():
    # Here the best layout's outer arm runs out of its via and wraps back onto it within half a revolution. The via
    # check sees that copper, so the next layout candidate is used.
    shape = geometry.TrapezoidShape(width=50, height=40, offset=7.641, annular_width=9.087)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        model = geometry.PlanarInductor(shape=shape, turns=3, twists=5, clockwise=True, clearance=0.117)
    assert model.layout_key != ('cont', 0.0)
    assert model._vias_ok() and not [w for w in caught if 'overlaps' in str(w.message)]
    model._set_layout(('cont', 0.0))
    assert model.own_via_return()[0] < 0


def test_spiral_arguments_must_be_finite(square):
    _model(square)
    for mode in square.spiral_modes():
        square.set_spiral_mode(mode)
        with pytest.raises(ValueError):
            square.compute_spiral(0.0, float('nan'))
        with pytest.raises(ValueError):
            square.compute_spiral(0.0, float('inf'))


def test_debug_arms_mark_start_end_and_vertices(square):
    _model(square)
    for layout in _flat_layouts(square).values():
        square.sk.debug_arms.clear()
        layout.spiral(0.0, 2.0, 0.0, 6.0, debug=True)
        (arm, inward, _t1, _t2), = square.sk.debug_arms
        kinds = [kind for _p, kind, _start, _r, _i in arm]
        assert kinds[0] == 1 and kinds[-1] == 2 and set(kinds[1:-1]) == {3}
        assert arm[0][3] == pytest.approx(square.sk.radius) and arm[-1][3] == pytest.approx(square.sk.radius - 6.0)
        # two revolutions pass every corner twice (one of them may be the start point)
        assert sum(i is not None for _p, _k, _s, _r, i in arm) >= 2 * len(square.polygon) - 1
