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
    for a, b in itertools.combinations(lines, 2):  # no two traces nearer than the pitch
        assert a.distance(b) > 0.99 * PITCH
    # the space between the traces: rarely below the nominal one, much of it within -5 /
    # +20 % (settled, the room left over is shared out evenly, a little over that)
    sp = mesh.spacing(m.traces, PITCH / 2, PITCH / 2)
    assert sp.under < 0.05 * sp.measured and sp.below < 0.1 * sp.measured
    assert sp.within > 0.35 * sp.measured and sp.least > 0  # (rare tight spots allowed)
    assert sp.wide < 0.08 * sp.measured  # (few islands between the curve's runs, settled)


def test_seed_repeats_the_layout():
    a = sfc.generate(AREA, (7, 0), mesh.UP, 2, PITCH, seed=3, zones=ZONES)
    assert a == sfc.generate(AREA, (7, 0), mesh.UP, 2, PITCH, seed=3, zones=ZONES)


def test_arcs_draw_the_same_traces():
    """In lines and arcs, each trace keeps to the simplified one within a few micrometres,
    in far fewer pieces, its ends as before; ``traces`` the arcs drawn as a polyline."""
    a = sfc.generate(AREA, (7, 0), mesh.UP, 2, PITCH, seed=3, zones=ZONES)
    b = sfc.generate(AREA, (7, 0), mesh.UP, 2, PITCH, seed=3, zones=ZONES, arcs=True)
    assert a.arcs is None and b.arcs is not None
    tol = sfc.ARCS * PITCH / 0.3
    for line, poly, pieces in zip(a.traces, b.traces, b.arcs, strict=True):
        assert (poly[0], poly[-1]) == (line[0], line[-1])
        assert pieces[0][0] == poly[0] and pieces[-1][2] == poly[-1]
        assert any(m is not None for _, m, _ in pieces) and len(pieces) < len(line)
        assert all(q[0] == p[2] for p, q in itertools.pairwise(pieces))
        far = shapely.hausdorff_distance(LineString(line), LineString(poly), densify=0.05)
        assert far < 3 * tol + sfc.SIMPLIFY * PITCH / 0.3
        assert poly == mesh.sample_arcs(pieces, tol)


def test_sample_arcs_keeps_to_the_circle():
    """A quarter circle and a line: the chords within the tolerance, round the right way."""
    r, tol = 1.0, 1e-3
    s = math.sqrt(0.5)
    pieces = [((1.0, 0.0), (s, s), (0.0, 1.0)), ((0.0, 1.0), None, (-1.0, 1.0))]
    pts = mesh.sample_arcs(pieces, tol)
    assert pts[0] == (1.0, 0.0) and pts[-2:] == ((0.0, 1.0), (-1.0, 1.0))
    arc = np.array(pts[:-1])
    assert np.allclose(np.hypot(*arc.T), r) and (arc >= -1e-12).all()  # (the short way)
    mids = (arc[1:] + arc[:-1]) / 2
    assert (r - np.hypot(*mids.T)).max() <= tol


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


def test_cells_tile_their_domain():
    """The Rust core's centroidal Voronoi cells cover the domain once (no gaps, no overlap,
    no slivers), round a hole too."""
    import yanartas_mesh
    from shapely.geometry import Polygon

    domain = shapely.box(0, 0, 12, 8).difference(shapely.box(5, 3, 7, 5))
    rings = [np.asarray(r.coords)[:-1] for r in (domain.exterior, *domain.interiors)]
    cells = [Polygon(c) for c in yanartas_mesh._cells(rings, 1.5, 3, None, 6)]
    union = shapely.union_all(cells)
    assert all(c.is_valid for c in cells)
    assert math.isclose(sum(c.area for c in cells), domain.area, rel_tol=1e-9)
    assert math.isclose(union.area, domain.area, rel_tol=1e-9)
    assert min(c.area for c in cells) > 0.05 * 1.5**2
