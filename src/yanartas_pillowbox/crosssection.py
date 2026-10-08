"""Cross-section of the closed box body, and the flat panel width that produces it.

Pure math (no config, no geometry imports). Notation: ``W`` is the flat width of one panel
(half the circumference), ``s`` the curved-fold sagitta and ``d`` the closed width of the box
measured across its cross-section from fold to fold.

A closed panel is a cylinder whose cross-section, parametrised by arc length ``u`` in
``[0, W]``, has height ``Z(u) = f(u)`` (the crease's offset from its chord) and
``X'(u) = sqrt(1 - f'(u)^2)``. With ``u - W/2 = R sin(psi)`` this gives
``X = R * E(psi)``, ``E(psi) = int_0^psi sqrt(cos 2t) dt``, so ``d = 2 R E(psi_max)``.

The shape depends only on the ratio ``r = s / W``: ``d = W * c(r)``. Given ``d`` and ``s``,
``W`` solves ``c(r) / r = d / s``; the left side decreases monotonically in ``r``.
"""

from __future__ import annotations

import math
from functools import lru_cache

# Largest sagitta/panel-width ratio that still closes with a real fold at the panel edges
# (the fold arc may turn at most 45 degrees at the corners: r < (sqrt 2 - 1) / 2 = 0.207).
MAX_SAGITTA_RATIO = 0.2


def circle_radius(chord: float, sagitta: float) -> float:
    return (chord**2 / 4 + sagitta**2) / (2 * sagitta)


def sagitta_offset(chord: float, sagitta: float, u: float) -> float:
    """Distance of the arc from its chord at chord position ``u`` (0..chord)."""
    r = circle_radius(chord, sagitta)
    return math.sqrt(max(0.0, r * r - (u - chord / 2) ** 2)) - (r - sagitta)


def _gauss_legendre(n: int) -> list[tuple[float, float]]:
    """Nodes and weights on [-1, 1] (Newton iteration on Legendre polynomials)."""
    out = []
    for i in range(1, n + 1):
        x = math.cos(math.pi * (i - 0.25) / (n + 0.5))
        for _ in range(100):
            p0, p1 = 1.0, x
            for k in range(2, n + 1):
                p0, p1 = p1, ((2 * k - 1) * x * p1 - (k - 1) * p0) / k
            dp = n * (x * p1 - p0) / (x * x - 1)
            dx = p1 / dp
            x -= dx
            if abs(dx) < 1e-16:
                break
        out.append((x, 2 / ((1 - x * x) * dp * dp)))
    return out


_GL = _gauss_legendre(64)


def e_integral(psi: float) -> float:
    """``E(psi) = int_0^psi sqrt(cos 2t) dt`` for ``0 <= psi < pi/4`` (Gauss-Legendre)."""
    half = psi / 2
    return half * sum(w * math.sqrt(max(0.0, math.cos(2 * (half * x + half)))) for x, w in _GL)


def width_ratio(r: float) -> float:
    """Closed width over panel width, ``c(r) = d / W``, for sagitta ratio ``r = s / W``."""
    radius = circle_radius(1.0, r)
    psi_max = math.asin(min(1.0, 0.5 / radius))
    return 2 * radius * e_integral(psi_max)


def max_sagitta(closed_width: float) -> float:
    """Largest fold sagitta a box of this closed width can have (see MAX_SAGITTA_RATIO)."""
    r = MAX_SAGITTA_RATIO
    return closed_width * r / width_ratio(r)


@lru_cache(maxsize=256)
def panel_width(closed_width: float, sagitta: float) -> float:
    """Flat panel width ``W`` whose closed cross-section is ``closed_width`` wide when the
    curved fold has the given sagitta. Requires ``sagitta <= max_sagitta(closed_width)``."""
    target = closed_width / sagitta
    lo, hi = 1e-9, MAX_SAGITTA_RATIO  # c(r)/r decreases from +inf to its value at hi
    if width_ratio(hi) / hi > target * (1 + 1e-12):
        raise ValueError("sagitta too large for this closed width")
    for _ in range(200):
        mid = math.sqrt(lo * hi)  # bisect in log space: r spans many decades
        if width_ratio(mid) / mid > target:
            lo = mid
        else:
            hi = mid
        if hi / lo - 1 < 1e-15:
            break
    return sagitta / ((lo + hi) / 2)


class CrossSection:
    """The closed panel's cross-section, centred on X = 0 (see module docstring).

    ``x(u)`` uses a Simpson table plus a Simpson remainder so it can be evaluated cheaply at
    many arc positions; ``closed_width`` uses the Gauss-Legendre integral."""

    TABLE = 512

    def __init__(self, width: float, sagitta: float) -> None:
        self.width = width
        self.sagitta = sagitta
        self.radius = circle_radius(width, sagitta)
        self.psi_max = math.asin(min(1.0, (width / 2) / self.radius))
        if self.psi_max >= math.pi / 4:
            raise ValueError("fold arc too steep to close (sagitta must be < 0.207 * width)")
        self._step = self.psi_max / self.TABLE
        table = [0.0]
        for k in range(self.TABLE):
            a = k * self._step
            table.append(table[-1] + _simpson(a, a + self._step, 4))
        self._table = table

    def e(self, psi: float) -> float:
        sign = -1.0 if psi < 0 else 1.0
        psi = min(abs(psi), self.psi_max)
        k = min(int(psi / self._step), self.TABLE - 1)
        a = k * self._step
        return sign * (self._table[k] + _simpson(a, psi, 4))

    def x(self, u: float) -> float:
        d = min(1.0, max(-1.0, (u - self.width / 2) / self.radius))
        return self.radius * self.e(math.asin(d))

    def z(self, u: float) -> float:
        return sagitta_offset(self.width, self.sagitta, min(self.width, max(0.0, u)))

    @property
    def closed_width(self) -> float:
        return 2 * self.radius * e_integral(self.psi_max)


def _simpson(a: float, b: float, n: int) -> float:
    """Composite Simpson rule for sqrt(cos 2t) on [a, b] (n even)."""
    if b == a:
        return 0.0
    h = (b - a) / n
    total = 0.0
    for i in range(n + 1):
        w = 1 if i in (0, n) else (4 if i % 2 else 2)
        total += w * math.sqrt(max(0.0, math.cos(2 * (a + i * h))))
    return total * h / 3
