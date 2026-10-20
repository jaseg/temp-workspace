"""Partitions of a mesh's area: of equal area, together the whole of it, each of a piece and
at its own port (in turn along the junction), feeders a pair of lanes wide where needed."""

import itertools

import pytest
import shapely

from yanartas_pillowbox import mesh, partition, sfc

PITCH = 0.3
AREA = shapely.box(0, 0, 60, 40)
ZONES = [shapely.box(0, 0, 30, 40), shapely.box(30, 0, 60, 40)]


def ports(count: int, n: int) -> list[shapely.Polygon]:
    c = 2 * n * PITCH
    y0 = 20 - count * c / 2
    return [shapely.box(0, y0 + k * c, c, y0 + (k + 1) * c) for k in range(count)]


@pytest.mark.parametrize(("count", "seed"), [(3, 0), (3, 1), (4, 2), (1, 3)])
def test_partitions(count, seed):
    n = 2
    ps = ports(count, n)
    parts = partition.partition(AREA, ZONES, ps, (1.0, 0.0), 2 * n * PITCH, seed)
    assert len(parts) == count
    areas = [p.area.area for p in parts]
    assert max(areas) - min(areas) < 0.03 * max(areas)  # (of equal area)
    assert sum(areas) == pytest.approx(AREA.area, rel=5e-3)  # (the whole, once: but crumbs)
    for a, b in itertools.combinations(parts, 2):
        assert a.area.intersection(b.area).area < 1e-6
    for p, port in zip(parts, ps, strict=True):
        assert p.area.geom_type == "Polygon"  # (of a piece)
        assert p.port == port and port.difference(p.area).area < 1e-6
        # (a feeder from the port's middle on, its corridor a port wide, inside)
        assert p.feeder.coords[0] == pytest.approx(tuple(port.centroid.coords[0]))
        corridor = p.feeder.buffer(PITCH * n, cap_style="flat").intersection(AREA)
        assert corridor.difference(p.area).area < 1e-3 * (2 * n * PITCH) ** 2


def test_seed_repeats_the_partitions_and_another_differs():
    ps = ports(3, 2)
    a = partition.partition(AREA, ZONES, ps, (1.0, 0.0), 1.2, 5)
    b = partition.partition(AREA, ZONES, ps, (1.0, 0.0), 1.2, 5)
    c = partition.partition(AREA, ZONES, ps, (1.0, 0.0), 1.2, 6)
    assert [p.area.equals(q.area) for p, q in zip(a, b, strict=True)] == [True] * 3
    assert not all(p.area.equals(q.area) for p, q in zip(a, c, strict=True))


def test_cells_keep_to_the_zones():
    import numpy as np

    polys, zone = partition.cells(AREA, ZONES, 2.0, np.random.default_rng(0))
    assert sum(p.area for p in polys) == pytest.approx(AREA.area)
    for p, z in zip(polys, zone, strict=True):  # (no cell across the fold)
        assert ZONES[z].buffer(1e-6).contains(p)


def test_a_neck_carries_the_tongue_on():
    """A partition laid out along a feeder: its traces leave through its port at the pitch,
    run along the feeder and fill the part beyond, nearer nothing than the pitch."""
    n = 2
    c = 2 * n * PITCH
    area = shapely.box(0, 0, 30, 20)
    feeder = shapely.LineString([(c / 2, 10), (4, 10), (8, 14)])
    m = sfc.generate(area, (0, 10 - c / 2), mesh.LEFT, n, PITCH, seed=1, feeder=feeder)
    lines = [shapely.LineString(t) for t in m.traces]
    assert all(line.is_simple for line in lines)
    assert min(a.distance(b) for a, b in itertools.combinations(lines, 2)) > 0.99 * PITCH
    corridor = feeder.buffer(c / 2, cap_style="flat")
    inside = shapely.union_all(lines).intersection(corridor.buffer(-PITCH / 4))
    assert inside.length > 2 * n * 0.8 * feeder.length  # (its traces run along it)
