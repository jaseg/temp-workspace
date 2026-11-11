import itertools
import math

import pytest
from factorio_poles import geometry
from factorio_poles.geometry import catenary_constant, orientation_frame, sag_profile, shadow_polyline, wire_polyline


def arc_length(span, h1, h2, sag):
    n = len(sag)
    pts = [(i / (n - 1) * span, h1 + i / (n - 1) * (h2 - h1) - d) for i, d in enumerate(sag)]
    return sum(math.dist(a, b) for a, b in itertools.pairwise(pts))


@pytest.mark.parametrize("span,rise,slack", [(10, 0, 0.015), (30, 0, 0.01), (7.5, 1.2, 0.02), (20, -3, 0.05)])
def test_catenary_constant_has_requested_length(span, rise, slack):
    chord = math.hypot(span, rise)
    a = catenary_constant(span, rise, chord * (1 + slack))
    assert 2 * a * math.sinh(span / (2 * a)) == pytest.approx(math.sqrt((chord * (1 + slack)) ** 2 - rise**2))


def test_taut_wire_is_straight():
    assert math.isinf(catenary_constant(10, 0, 10))
    assert sag_profile(10, 2, 2, slack=0) == [0.0] * 24


@pytest.mark.parametrize("span,h1,h2", [(10, 2, 2), (30, 3.8, 3.8), (7.5, 2.6, 3.1), (16, 3.8, 2.7)])
def test_sag_profile(span, h1, h2):
    slack = 0.015
    sag = sag_profile(span, h1, h2, slack, samples=201)
    assert sag[0] == sag[-1] == 0
    assert all(d >= 0 for d in sag)
    assert max(sag) > 0
    # The sampled curve really is (1 + slack) times the chord.
    assert arc_length(span, h1, h2, sag) == pytest.approx(math.hypot(span, h2 - h1) * (1 + slack), rel=1e-4)


def test_sag_is_symmetric_for_level_wires_and_grows_with_span():
    sag = sag_profile(10, 2, 2, 0.015, samples=101)
    assert sag == pytest.approx(sag[::-1], abs=1e-12)
    assert max(sag) == pytest.approx(sag[50])
    # Fixed slack: sag proportional to span (small-sag approximation L*sqrt(3e/8)).
    assert max(sag) == pytest.approx(10 * math.sqrt(3 * 0.015 / 8), rel=0.02)
    assert max(sag_profile(30, 2, 2, 0.015)) > 2.9 * max(sag_profile(10, 2, 2, 0.015))


def test_lowest_point_moves_towards_lower_end():
    sag = sag_profile(20, 1, 4, 0.03, samples=101)
    heights = [1 + i / 100 * 3 - d for i, d in enumerate(sag)]
    low = heights.index(min(heights))
    assert low < 50


def test_wire_polyline_ends_on_attachment_points():
    pts = wire_polyline((0, 0), (0.1, -2.5), (6, 1), (0.0, -3.0), 0.015, 16)
    assert pts[0] == pytest.approx((0.1, -2.5))
    assert pts[-1] == pytest.approx((6.0, -2.0))
    assert len(pts) == 16
    # Wires sag downwards on screen (+y).
    mid = pts[8]
    chord_y = -2.5 + (mid[0] - 0.1) / 5.9 * 0.5
    assert mid[1] > chord_y


def test_shadow_polyline_ends_on_shadow_points_and_bends_back():
    g1, a1, s1 = (0, 0), (0, -2.5), (3, 0.1)
    g2, a2, s2 = (0, 6), (0, -2.5), (3, 0.1)
    pts = shadow_polyline(g1, a1, s1, g2, a2, s2, 0.03, 21)
    assert pts[0] == pytest.approx((3, 0.1))
    assert pts[-1] == pytest.approx((3, 6.1))
    # Lower wire, shorter shadow: the middle is pulled back towards the poles.
    assert pts[10][0] < 3


@pytest.mark.parametrize(
    "neighbours,frame",
    [
        ([(0, -5)], 0),  # wire to the north: cross-arm east-west
        ([(0, 5), (0, -5)], 0),
        ([(5, 0)], 2),
        ([(-5, 0), (5, 0)], 2),
        ([(5, -5)], 1),  # NE
        ([(-5, 5)], 1),  # SW
        ([(5, 5)], 3),  # SE
        ([], 0),
    ],
)
def test_orientation_frame(neighbours, frame):
    assert orientation_frame((0, 0), neighbours) == frame


def test_samples_for_span_bounds():
    assert geometry.samples_for_span(0.5) == 8
    assert geometry.samples_for_span(100) == 64
