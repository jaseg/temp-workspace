"""The security mesh generator (a KiMesh port): every net one path through every reachable
cell, both ends at the exit cell's open side, nets apart by their pitch."""

import itertools
import math

import pytest
import shapely
from shapely.geometry import LineString

from yanartas_pillowbox import mesh

PITCH = 0.3


def ring():
    """A frame with a hole: the walk must go round it."""
    return shapely.box(0, 0, 30, 20).difference(shapely.box(10, 8, 18, 14))


@pytest.mark.parametrize("n", [1, 2, 4])
@pytest.mark.parametrize("side", [mesh.UP, mesh.DOWN, mesh.LEFT, mesh.RIGHT])
def test_each_net_is_one_path_ending_at_the_exit(n, side):
    c = 2 * n * PITCH
    exit_cell = {
        mesh.UP: (12, 0),
        mesh.DOWN: (12, 20 - c),
        mesh.LEFT: (0, 3),
        mesh.RIGHT: (30 - c, 3),
    }
    corner = exit_cell[side]
    m = mesh.generate(ring(), corner, side, n, PITCH, seed=3)
    assert len(m.traces) == n and m.unreached == 0
    x, y = corner
    edge = {
        mesh.UP: LineString([(x, y), (x + c, y)]),
        mesh.DOWN: LineString([(x, y + c), (x + c, y + c)]),
        mesh.LEFT: LineString([(x, y), (x, y + c)]),
        mesh.RIGHT: LineString([(x + c, y), (x + c, y + c)]),
    }[side]
    ends = []
    for a, b in m.ends:  # both ends on the exit side, mirrored about its middle
        assert edge.distance(shapely.Point(a)) < 1e-9 and edge.distance(shapely.Point(b)) < 1e-9
        ends += [a, b]
        mid = edge.interpolate(0.5, normalized=True)
        assert math.isclose(
            math.dist(a, (mid.x, mid.y)), math.dist(b, (mid.x, mid.y)), abs_tol=1e-9
        )
    # ... at the pitch across the side, nets nested from the outside in
    along = sorted(edge.project(shapely.Point(p)) for p in ends)
    assert all(math.isclose(b - a, PITCH, abs_tol=1e-9) for a, b in itertools.pairwise(along))


def test_every_cell_is_covered_and_traces_stay_inside():
    mask = ring()
    m = mesh.generate(mask, (12, 0), mesh.UP, 4, PITCH, seed=1)
    cells = sum(
        1
        for gx in range(13)
        for gy in range(9)
        if mask.contains(
            shapely.box(12 + (gx - 5) * 2.4, gy * 2.4, 12 + (gx - 4) * 2.4, (gy + 1) * 2.4)
        )
    )
    assert m.cells == cells and m.cell == pytest.approx(2.4)
    covered = shapely.union_all([LineString(t) for t in m.traces]).buffer(PITCH)
    for t in m.traces:
        assert mask.buffer(1e-9).contains(LineString(t))
    # every cell has traces through it (the walk reached them all)
    assert covered.area > 0.9 * mask.area - 2.4 * mask.length


def test_nets_keep_their_pitch_apart():
    m = mesh.generate(ring(), (12, 0), mesh.UP, 3, PITCH, seed=5, chamfer=0.5)
    lines = [LineString(t) for t in m.traces]
    for a, b in itertools.combinations(lines, 2):
        assert a.distance(b) >= PITCH - 1e-9


def test_seed_repeats_the_walk_and_randomness_steers_it():
    a = mesh.generate(ring(), (12, 0), mesh.UP, 2, PITCH, seed=7)
    assert a == mesh.generate(ring(), (12, 0), mesh.UP, 2, PITCH, seed=7)
    assert a != mesh.generate(ring(), (12, 0), mesh.UP, 2, PITCH, seed=8)
    straight = mesh.generate(ring(), (12, 0), mesh.UP, 2, PITCH, seed=7, randomness=0)
    corners = lambda m: sum(len(t) for t in m.traces)  # noqa: E731
    assert corners(straight) < corners(a)  # walking straight on turns less


def test_tiles_connect_on_their_sides():
    """Each tile's traces end exactly on the sides its key names, at the pitch."""
    for key in range(1, 16):
        for pts, _net in mesh.tile(key, 2):
            for p in (pts[0], pts[-1]):
                on = {
                    mesh.RIGHT: p[0] == pytest.approx(1),
                    mesh.DOWN: p[1] == pytest.approx(1),
                    mesh.LEFT: p[0] == pytest.approx(0),
                    mesh.UP: p[1] == pytest.approx(0),
                }
                sides = [s for s, hit in on.items() if hit]
                assert sides and all(key & s for s in sides), (key, p)


def test_no_room_for_the_exit():
    with pytest.raises(mesh.MeshError):
        mesh.generate(shapely.box(0, 0, 1, 1), (0, 0), mesh.UP, 4, PITCH)
