"""The space-filling-curve mesh layout (after Bedel et al., 2022), on small areas: each net
one path out through the exit, its traces apart and in the area, the zones (panels) joined
across their border as seldom as can be."""

import itertools
import math

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString

from yanartas_pillowbox import mesh, sfc

PITCH = 0.3
AREA = shapely.box(0, 0, 30, 20)
ZONES = [shapely.box(0, 0, 15, 20), shapely.box(15, 0, 30, 20)]
FOLD = LineString([(15, -1), (15, 21)])


def exit_edge(corner, side, c):
    x, y = corner
    return {
        mesh.UP: LineString([(x, y), (x + c, y)]),
        mesh.DOWN: LineString([(x, y + c), (x + c, y + c)]),
        mesh.LEFT: LineString([(x, y), (x, y + c)]),
        mesh.RIGHT: LineString([(x + c, y), (x + c, y + c)]),
    }[side]


@pytest.mark.parametrize(
    ("n", "side", "corner"),
    [
        (2, mesh.UP, (7, 0)),
        (4, mesh.UP, (7, 0)),
        (2, mesh.DOWN, (7, 18.8)),
        (2, mesh.LEFT, (0, 9)),
        (2, mesh.RIGHT, (28.8, 9)),
    ],
)
def test_layout(n, side, corner):
    m = sfc.generate(AREA, corner, side, n, PITCH, seed=1, zones=ZONES)
    c = 2 * n * PITCH
    assert m.algorithm == "sfc" and len(m.traces) == n and m.unreached == 0
    edge = exit_edge(corner, side, c)
    mid = edge.interpolate(0.5, normalized=True)
    ends = []
    for a, b in m.ends:  # both ends on the exit side, mirrored about its middle
        assert edge.distance(shapely.Point(a)) < 1e-9 and edge.distance(shapely.Point(b)) < 1e-9
        assert math.isclose(math.dist(a, mid.coords[0]), math.dist(b, mid.coords[0]), abs_tol=1e-6)
        ends += [a, b]
    along = sorted(edge.project(shapely.Point(p)) for p in ends)  # at the pitch
    assert all(math.isclose(y - x, PITCH, abs_tol=1e-6) for x, y in itertools.pairwise(along))
    # net 1 outermost
    assert [math.dist(t[0], mid.coords[0]) for t in m.traces] == sorted(
        (math.dist(t[0], mid.coords[0]) for t in m.traces), reverse=True
    )
    lines = [LineString(t) for t in m.traces]
    for line in lines:
        assert line.is_simple and AREA.buffer(1e-9).contains(line)
        # (the copper inside, but where the traces leave)
        assert AREA.buffer(-PITCH / 4).contains(line.difference(edge.buffer(PITCH)))
        # the curve joins the two zones once: each trace crosses their border twice
        assert len(shapely.get_parts(line.intersection(FOLD))) == 2
    for a, b in itertools.combinations(lines, 2):  # no two traces touch (no shorts)
        assert a.distance(b) > PITCH / 2
    # the space between the traces: mostly within the nominal one -5 / +20 %, rarely below
    sp = mesh.spacing(m.traces, PITCH / 2, PITCH / 2)
    assert sp.under < 0.05 * sp.measured and sp.below < 0.1 * sp.measured
    assert sp.within > 0.5 * sp.measured and sp.least > 0  # (rare tight spots allowed)
    assert sp.wide < 0.15 * sp.measured  # (few islands between the curve's runs)


def test_seed_repeats_the_layout():
    a = sfc.generate(AREA, (7, 0), mesh.UP, 2, PITCH, seed=3, zones=ZONES)
    assert a == sfc.generate(AREA, (7, 0), mesh.UP, 2, PITCH, seed=3, zones=ZONES)


def test_without_zones_and_with_a_hole():
    area = AREA.difference(shapely.box(10, 8, 18, 14))
    m = sfc.generate(area, (7, 0), mesh.UP, 2, PITCH, seed=2)
    hole = shapely.box(10, 8, 18, 14)
    for t in m.traces:  # (round the hole, the copper clear of it)
        line = LineString(t)
        assert line.is_simple and line.distance(hole) >= PITCH / 4


def test_no_room_for_the_exit():
    with pytest.raises(mesh.MeshError):
        sfc.generate(shapely.box(0, 0, 1, 1), (0, 0), mesh.UP, 4, PITCH)


def test_untangle_keeps_the_curve_simple():
    """A move that would make the curve cross itself is taken back."""
    old = np.array([(0, 0), (4, 0), (4, 1), (0, 1)], float)
    new = old.copy()
    new[1] = (4, 2)  # (the edge 0-1 would cross 2-3)
    assert not len(sfc._crossing(old, np.arange(4))[0])
    out = sfc._untangle(old, new)
    assert not len(sfc._crossing(out, np.arange(4))[0])
