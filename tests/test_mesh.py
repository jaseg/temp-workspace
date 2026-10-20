"""What the mesh layouts share: the spacing profile and the pair skew."""

import pytest

from yanartas_pillowbox import mesh


def test_spacing_of_parallel_traces():
    lines = [[(0, 0.3 * i), (10, 0.3 * i)] for i in range(3)]
    sp = mesh.spacing(lines, 0.15, 0.15)
    assert sp.least == pytest.approx(0.15)
    assert sp.below == 0 and sp.over == 0 and sp.within == pytest.approx(sp.measured)
    assert sp.measured == pytest.approx(40, rel=0.05)  # (the two gaps, both their sides)
    tight = mesh.spacing([[(0, 0), (10, 0)], [(0, 0.28), (10, 0.28)]], 0.15, 0.15)
    assert tight.least == pytest.approx(0.13) and tight.under == pytest.approx(tight.measured)
    wide = mesh.spacing([[(0, 0), (10, 0)], [(0, 0.36), (10, 0.36)]], 0.15, 0.15)
    assert wide.over == pytest.approx(wide.measured) and wide.wide == 0


def test_spacing_sees_islands_but_not_the_edge():
    """A gap wider than the nearest-copper search still counts (straight across), as far as
    three times as many pitches as there are traces; beyond, it is the area's edge."""
    lines = [[(0, 0), (10, 0)], [(0, 0.3), (10, 0.3)], [(0, 1.5), (10, 1.5)]]
    sp = mesh.spacing(lines, 0.15, 0.15)
    assert sp.largest == pytest.approx(1.05)
    assert sp.wide == pytest.approx(sp.measured / 2, rel=0.1)  # (the island's two sides)
    assert sp.measured == pytest.approx(40, rel=0.05)  # (not the outer sides: the edge)
    far = mesh.spacing([[(0, 0), (10, 0)], [(0, 9), (10, 9)]], 0.15, 0.15)
    assert far.measured == 0 and far.largest == 0


def test_skew():
    """Total: the difference in length; local: the most one is longer than the other so far."""
    a = [(0, 0), (10, 0), (20, 0)]
    b = [(0, 0.3), (10, 0.3), (20, 0.3)]
    assert mesh.skew(a, b) == pytest.approx((0, 0), abs=0.3)
    # b takes a detour 2 mm deep at 5 mm, then runs along again
    detour = [(0, 0.3), (5, 0.3), (5, 2.3), (6, 2.3), (6, 0.3), (20, 0.3)]
    total, local = mesh.skew(a, detour)
    assert total == pytest.approx(4)
    assert local == pytest.approx(4, abs=0.5)
    # a lead made up again later: little total skew, but a local one
    early = [(0, 0), (5, 0), (5, 2.3), (6, 2.3), (6, 0), (20, 0)]
    late = [(0, 0.3), (14, 0.3), (14, 2.6), (15, 2.6), (15, 0.3), (20, 0.3)]
    total, local = mesh.skew(early, late)
    assert total == pytest.approx(0, abs=0.7)
    assert local > 3.5


def test_density_sees_holes_but_not_the_edge():
    """Traces side by side at the pitch fill their area at the nominal density, its edge
    counting no hole; leave a few out and the hole shows."""
    import shapely

    area = shapely.box(0, 0, 20, 12)
    full = [[(0, 0.15 + 0.3 * i), (20, 0.15 + 0.3 * i)] for i in range(40)]
    d = mesh.density(full, area, 0.15, 0.15)
    assert d.mean == pytest.approx(1, abs=0.02) and d.spread < 0.02 and d.thin == 0
    holed = [t for i, t in enumerate(full) if not 16 <= i < 24]  # (a 2.4 mm wide gap)
    h = mesh.density(holed, area, 0.15, 0.15)
    assert h.thin > 0.05 and h.least < 0.3 and h.spread > 0.1
