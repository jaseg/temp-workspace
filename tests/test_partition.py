"""Partitions of a mesh's area: of equal area, together the whole of it, each of a piece and
at its own port (in turn along the junction) with its strip; and the mesh laid out over
them at once, a curve and its traces in each."""

import itertools

import numpy as np
import pytest
import shapely

from yanartas_pillowbox import mesh, partition, sfc

PITCH = 0.3
AREA = shapely.box(0, 0, 60, 40)
ZONES = [shapely.box(0, 0, 30, 40), shapely.box(30, 0, 60, 40)]


def ports(count: int, n: int, y: float = 20) -> list[shapely.Polygon]:
    c = 2 * n * PITCH
    y0 = y - count * c / 2
    return [shapely.box(0, y0 + k * c, c, y0 + (k + 1) * c) for k in range(count)]


@pytest.mark.parametrize(("count", "seed"), [(3, 0), (3, 1), (4, 2), (1, 3), (6, 4)])
def test_partitions(count, seed):
    n = 2
    ps = ports(count, n)
    width = 2 * n * PITCH
    parts = partition.partition(AREA, ZONES, ps, (1.0, 0.0), width, seed)
    assert len(parts) == count
    areas = [p.area.area for p in parts]
    assert max(areas) - min(areas) < 0.03 * max(areas)  # (of equal area)
    assert sum(areas) == pytest.approx(AREA.area, rel=5e-3)  # (the whole, once: but crumbs)
    for a, b in itertools.combinations(parts, 2):
        assert a.area.intersection(b.area).area < 1e-6
    strips = partition.strips(ps, (1.0, 0.0), width)
    for p, port, strip in zip(parts, ps, strips, strict=True):
        assert p.area.geom_type == "Polygon"  # (of a piece)
        assert p.port == port and port.difference(p.area).area < 1e-6
        # (its strip its own, as wide as the port, its curve opening at its end)
        assert strip.difference(p.area).area < 1e-6
        assert strip.bounds[1] == pytest.approx(port.bounds[1])
        assert p.reach == pytest.approx(strip.bounds[2] - port.bounds[0])
    # (the strips side by side, no two as long)
    reach = [p.reach for p in parts]
    assert all(abs(a - b) > width for a, b in itertools.pairwise(reach))


def test_seed_repeats_the_partitions_and_another_differs():
    ps = ports(3, 2)
    a = partition.partition(AREA, ZONES, ps, (1.0, 0.0), 1.2, 5)
    b = partition.partition(AREA, ZONES, ps, (1.0, 0.0), 1.2, 5)
    c = partition.partition(AREA, ZONES, ps, (1.0, 0.0), 1.2, 6)
    assert [p.area.equals(q.area) for p, q in zip(a, b, strict=True)] == [True] * 3
    assert not all(p.area.equals(q.area) for p, q in zip(a, c, strict=True))


def test_cells_keep_to_the_zones_and_their_pins():
    pins = [(5.0, 5.0), (40.0, 30.0)]
    polys, zone, at = partition.cells(AREA, ZONES, 2.0, np.random.default_rng(0), pins)
    assert sum(p.area for p in polys) == pytest.approx(AREA.area)
    for p, z in zip(polys, zone, strict=True):  # (no cell across the fold)
        assert ZONES[z].buffer(1e-6).contains(p)
    for q, i in zip(pins, at, strict=True):
        assert polys[i].covers(shapely.Point(q))


def test_the_mesh_over_partitions():
    """Each partition's traces leave through its port at the pitch, in a row with the
    next's, stay in it and fill it; none nearer another than about the pitch; their lengths
    matched within each partition."""
    n, count = 2, 2
    zones = [shapely.box(0, 0, 15, 20), shapely.box(15, 0, 30, 20)]
    ps = ports(count, n, 10)
    width = 2 * n * PITCH
    y0 = ps[0].bounds[1]
    area = shapely.box(0, 0, 30, 20).difference(shapely.box(-1, y0, 0, y0 + count * width))
    parts = partition.partition(area, zones, ps, (1.0, 0.0), width, 3)
    m = sfc.generate(
        area, [p.bounds[:2] for p in ps], mesh.LEFT, n, PITCH, seed=1, zones=zones,
        partitions=[p.area for p in parts], stems=[p.reach for p in parts],
    )  # fmt: skip
    assert m.groups == (n, n) and m.unreached == 0 and len(m.traces) == count * n
    lines = [shapely.LineString(t) for t in m.traces]
    assert all(line.is_simple for line in lines)
    assert min(a.distance(b) for a, b in itertools.combinations(lines, 2)) > 0.98 * PITCH
    # (the exits' ends in a row along the junction at the pitch)
    ends = sorted(q[1] for t in m.traces for q in (t[0], t[-1]))
    assert np.allclose(np.diff(ends), PITCH)
    for k, part in enumerate(parts):
        mine = lines[k * n : (k + 1) * n]
        beyond = part.area.buffer(PITCH)
        assert all(beyond.contains(line) for line in mine)
        lengths = [line.length for line in mine]
        assert max(lengths) - min(lengths) < 15 * PITCH
    cover = mesh.density(m.traces, area, PITCH / 2, PITCH / 2)
    assert cover.thin < 0.02  # (nothing left much emptier than the rest: no holes)
