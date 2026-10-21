"""Shared checks."""

import pytest

from yanartas_pillowbox import mesh


@pytest.fixture
def even():
    """A check that a mesh covers its area evenly, as a settled one does: its copper's
    density near the nominal everywhere (`mesh.density`: no dip under 70 %, little spread),
    no place much farther from copper than between neighbours at the pitch (`mesh.holes`:
    farther than two thirds of a pitch, a pitch in from the edge), and most of the space
    between traces within -5 / +20 % of the nominal (`mesh.spacing`)."""

    def check(traces, area, pitch, *, blur=mesh.DENSITY_BLUR, cell=mesh.DENSITY_CELL,
              within=0.4):  # fmt: skip
        d = mesh.density(traces, area, pitch / 2, pitch / 2, blur, cell)
        assert 0.85 <= d.mean <= 0.95, d  # (the copper as dense as at the pitch, about)
        assert d.spread < 0.03 and d.thin < 0.002 and d.least > 0.75, d  # (and evenly)
        h = mesh.holes(traces, area, 2 * pitch / 3, pitch)
        assert h.share < 0.01 and h.largest < 0.15, h  # (no hole a pair would fit in)
        s = mesh.spacing(traces, pitch / 2, pitch / 2)
        assert s.under < 0.01 * s.measured, s  # (never much nearer than the pitch)
        assert s.within > within * s.measured and s.wide < 0.08 * s.measured, s
        return d, h, s

    return check
