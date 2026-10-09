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

import itertools
import math
from dataclasses import dataclass
from functools import cached_property, lru_cache

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

    def slope(self, u: float) -> float:
        """``Z'(u) = f'(u)``: the sine of the section's angle to the X axis at ``u``."""
        d = min(self.width, max(0.0, u)) - self.width / 2
        return -d / math.sqrt(self.radius**2 - d * d)

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


# --------------------------------------------------------------------------- material thickness
def _mitre(
    d1: tuple[float, float], s1: float, d2: tuple[float, float], s2: float
) -> tuple[float, float]:
    """The point v at signed distances ``cross(d1, v) = s1`` and ``cross(d2, v) = s2`` from two
    lines through the origin with unit directions d1 and d2."""
    a11, a12, a21, a22 = -d1[1], d1[0], -d2[1], d2[0]
    det = a11 * a22 - a12 * a21
    return ((s1 * a22 - a12 * s2) / det, (a11 * s2 - a21 * s1) / det)


def _edge_sine(width: float, sagitta: float) -> float:
    """``sin`` of a closed panel's angle to the X axis at its edges, ``f'(0)``."""
    return (width / 2) / (circle_radius(width, sagitta) - sagitta)


@dataclass(frozen=True)
class Body:
    """Mid-surface geometry of the closed body, made of material of thickness ``t``, whose
    *interior* is ``width`` x ``height`` x ``length`` (see ``solve_body``).

    Frame: the 3D model's (X across, Z height), centred on the interior. The **front** panel
    (+Z) carries the outer flaps and has the glue tab on top of it; the **back** panel (-Z)
    carries the inner flaps. Each panel is a ``CrossSection`` (zero-thickness folding of the
    mid-surface stays exact), placed by ``front_x``/``back_x`` and ``z_shift``:

    * front: ``(front_x + front.x(u), z_shift + front.z(u))``, u from the glued edge E to the
      straight fold P;
    * back: ``(back_x - back.x(u), z_shift - back.z(u))``, u from P to the glue fold G.

    The end walls stand at each panel's crease (``Y = f(u)`` from the corner line), so the
    outer flaps' wall must be ``t`` further out than the inner flaps' wall: the front fold bows
    in by ``height/2``, the back fold by ``height/2 + t``. On the centreline that puts the
    inner surfaces of the panels at ``Z = +-height/2`` and of the inner wall at
    ``|Y| = length/2``. The inner flaps reach the front panel's inner surface, the outer flaps
    the back panel's outer surface (flush with the outside of the body).

    The glue tab lies on the outside of the front panel: its mid-surface is the front's,
    offset by ``t`` along the outward normal. It leaves G along the tangent at E for
    ``tab_lead`` (G lies ``t / sin(alpha)`` beyond E), then follows the offset curve.
    """

    width: float
    height: float
    length: float
    thickness: float
    front: CrossSection
    back: CrossSection
    front_x: float
    back_x: float
    inner_fold: tuple[float, float]  # interior corner at the straight fold
    inner_glue: tuple[float, float]  # interior corner at the glued edge

    @property
    def z_shift(self) -> float:
        return self.thickness / 2

    @property
    def edge_length(self) -> float:
        """Straight body edges, corner to corner."""
        return edge_length(self.length, self.height, self.thickness)

    @property
    def front_cut_sagitta(self) -> float:
        """Outer flaps' cut edge at its furthest: reaches the back panel's outer surface,
        ``height/2 + 1.5 t`` out at the back panel's apex."""
        return max(c for _, c in self.front_cuts)

    @property
    def back_cut_sagitta(self) -> float:
        """Inner flaps' cut edge at the centre: stops at the front panel's inner surface."""
        return self.height / 2 - self.thickness / 2

    def surface_z(self, panel: str, offset: float, x: float) -> float:
        """Z of a panel's surface ``offset`` out from its mid-surface (along the outward
        normal; negative: inwards) at ``X = x``. Beyond the panel's ends the surface
        continues along its end tangents."""
        sec = self.front if panel == "front" else self.back
        point = self.front_point if panel == "front" else self.back_point
        normal = self.front_normal if panel == "front" else self.back_normal

        def at(u: float) -> tuple[float, float]:
            (px, pz), (nx, nz) = point(u), normal(u)
            return (px + offset * nx, pz + offset * nz)

        lo, hi = 0.0, sec.width
        (x_lo, z_lo), (x_hi, z_hi) = at(lo), at(hi)
        rising = x_hi > x_lo  # X runs with u on the front panel, against it on the back
        for end, (ex, ez) in ((lo, (x_lo, z_lo)), (hi, (x_hi, z_hi))):
            if (x < ex) == (rising == (end == lo)) and x != ex:  # beyond this end
                k = sec.slope(end)
                tx, tz = (
                    (math.sqrt(1 - k * k), k) if panel == "front" else (-math.sqrt(1 - k * k), -k)
                )
                return ez + (x - ex) * tz / tx
        for _ in range(100):
            mid = (lo + hi) / 2
            if (at(mid)[0] < x) == rising:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-13 * sec.width:
                break
        return at((lo + hi) / 2)[1]

    @cached_property
    def front_cuts(self) -> tuple[tuple[float, float], ...]:
        """Outer (front) flaps' cut edge as (x, offset beyond the chord) samples, x from the
        glued edge: flush with the back panel's outer surface all along (at the glued edge
        too, where the back panel runs on to the glue fold)."""
        sec, n = self.front, _cut_samples(self.front.width)
        out = []
        for i in range(n + 1):
            u = sec.width * i / n
            x = self.front_point(u)[0]
            c = self.z_shift - self.surface_z("back", self.thickness / 2, x)
            out.append((u, c if c > 1e-9 else 0.0))  # exactly at the corners when t = 0
        return tuple(out)

    @cached_property
    def back_cuts(self) -> tuple[tuple[float, float], ...]:
        """Inner (back) flaps' cut edge as (u, offset beyond the chord) samples, u from the
        straight fold: stops at the front panel's inner surface (never below the chord, so
        near the corners it runs along the chord)."""
        sec, n = self.back, _cut_samples(self.back.width)

        def target(u: float) -> float:
            x = self.back_point(u)[0]
            return self.surface_z("front", -self.thickness / 2, x) - self.z_shift

        raw = [(sec.width * i / n, target(sec.width * i / n)) for i in range(n + 1)]
        out: list[tuple[float, float]] = []
        for (u0, c0), (u1, c1) in itertools.pairwise(raw):
            out.append((u0, c0 if c0 > 1e-9 else 0.0))
            if (c0 > 1e-9) != (c1 > 1e-9):  # add the point where the edge leaves the chord
                lo, hi = (u0, u1) if c0 <= 1e-9 else (u1, u0)
                for _ in range(60):
                    mid = (lo + hi) / 2
                    lo, hi = (mid, hi) if target(mid) <= 1e-9 else (lo, mid)
                if min(lo - u0, u1 - lo) > 1e-6 * sec.width:
                    out.append((lo, 0.0))
        u, c = raw[-1]
        out.append((u, c if c > 1e-9 else 0.0))
        return tuple(out)

    @property
    def circumference(self) -> float:
        return self.front.width + self.back.width

    @property
    def edge_sine(self) -> float:
        """``sin(alpha)``: the front panel's angle to the X axis at the glued edge."""
        return self.front.slope(0.0)

    @property
    def tab_lead(self) -> float:
        s = self.edge_sine
        return self.thickness * math.sqrt(1 - s * s) / s

    @property
    def fold_point(self) -> tuple[float, float]:
        """The straight fold P."""
        return self.front_point(self.front.width)

    @property
    def glue_point(self) -> tuple[float, float]:
        """The glue fold G."""
        return self.back_point(self.back.width)

    def front_point(self, u: float) -> tuple[float, float]:
        return (self.front_x + self.front.x(u), self.z_shift + self.front.z(u))

    def back_point(self, u: float) -> tuple[float, float]:
        return (self.back_x - self.back.x(u), self.z_shift - self.back.z(u))

    def front_normal(self, u: float) -> tuple[float, float]:
        """Outward unit normal of the front panel."""
        k = self.front.slope(u)
        return (-k, math.sqrt(1 - k * k))

    def back_normal(self, u: float) -> tuple[float, float]:
        """Outward unit normal of the back panel."""
        k = self.back.slope(u)
        return (k, -math.sqrt(1 - k * k))

    def tab_point(self, v: float) -> tuple[float, float]:
        """Glue-tab mid-surface at arc length ``v`` from the glue fold."""
        t, sec = self.thickness, self.front
        s = self.edge_sine
        gx, gz = self.glue_point
        lead = self.tab_lead
        if v <= lead:
            return (gx + v * math.sqrt(1 - s * s), gz + v * s)
        # Along the offset curve, arc length grows by t per radian the tangent turns.
        a0, target = math.asin(s), v - lead
        u = target
        for _ in range(60):
            k = sec.slope(u)
            d = min(sec.width, max(0.0, u)) - sec.width / 2
            dk = -(sec.radius**2) / (sec.radius**2 - d * d) ** 1.5  # f''(u)
            du = (u + t * (a0 - math.asin(k)) - target) / (1 - t * dk / math.sqrt(1 - k * k))
            u -= du
            if abs(du) < 1e-13:
                break
        (x, z), (nx, nz) = self.front_point(u), self.front_normal(u)
        return (x + t * nx, z + t * nz)


def _cut_samples(width: float) -> int:
    """Even number of polyline segments for a flap's cut edge (0.5 mm each up to 160)."""
    return 2 * max(16, min(80, math.ceil(width)))


def edge_length(length: float, height: float, thickness: float) -> float:
    """Straight body edges for an interior ``length`` x ``height``: the inner wall's
    mid-surface stands ``t/2`` beyond the interior, at the back fold's apex (``height/2 + t``
    in from the corner line)."""
    return length + height + 3 * thickness


def _assemble(xf: float, s_f: float, s_b: float, t: float) -> tuple[float, ...]:
    """Body pieces for a front panel of closed mid-surface width ``xf``."""
    wf = panel_width(xf, s_f)
    sf = _edge_sine(wf, s_f)
    xb = xf + t / sf  # the glue fold sits t / sin(alpha) beyond the front's free edge
    wb = panel_width(xb, s_b)
    sb = _edge_sine(wb, s_b)
    cf, cb = math.sqrt(1 - sf * sf), math.sqrt(1 - sb * sb)
    # Interior corners, relative to P and G: where the panels' inner surfaces (t/2 inside the
    # mid-surface) meet. At the glued edge the front's inner surface is 3t/2 from G's line.
    vp = _mitre((-cf, sf), t / 2, (-cb, -sb), -t / 2)
    vg = _mitre((cf, sf), -1.5 * t, (cb, -sb), t / 2)
    return wf, wb, xb, vp[0], vp[1], vg[0], vg[1]


@lru_cache(maxsize=512)
def solve_body(width: float, height: float, length: float, thickness: float) -> Body:
    """Mid-surface body whose interior is ``width`` (inner corner to inner corner) by
    ``height`` by ``length``. Raises ValueError if an arc is too steep to close."""
    t = thickness
    s_f, s_b = height / 2, height / 2 + t
    xf = width
    for _ in range(100):
        wf, wb, xb, vpx, vpz, vgx, vgz = _assemble(xf, s_f, s_b, t)
        err = width - (xb + vpx - vgx)
        if abs(err) <= 1e-12 * width:
            break
        xf += err  # d(interior)/d(xf) is 1 up to O(t / width)
    p = (xb - vpx - vgx) / 2  # centres the interior on X = 0
    front, back = CrossSection(wf, s_f), CrossSection(wb, s_b)
    return Body(
        width,
        height,
        length,
        t,
        front,
        back,
        front_x=p - front.closed_width / 2,
        back_x=p - back.closed_width / 2,
        inner_fold=(p + vpx, t / 2 + vpz),
        inner_glue=(p - xb + vgx, t / 2 + vgz),
    )


def max_height(width: float, thickness: float) -> float:
    """Largest interior height a body of this interior width can have (to 1 um)."""

    def ok(h: float) -> bool:
        try:
            solve_body(width, h, 1.0, thickness)
        except ValueError:
            return False
        return True

    lo, hi = 0.0, 2 * max_sagitta(width + 20 * thickness) + 1.0
    while ok(hi):  # pragma: no cover - the bound above is generous
        hi *= 2
    while hi - lo > 1e-4:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return lo
