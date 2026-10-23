"""Points as (x, y) tuples and the core's little vector arithmetic (rust/core/src/geom.rs),
with Rust's numeric conventions where Python's differ."""

from __future__ import annotations

import ctypes
import ctypes.util
import math

P = tuple[float, float]

# libm's hypot: Rust's f64::hypot calls it; Python's math.hypot has its own algorithm,
# which can differ in the last bit.
_libm = ctypes.CDLL(ctypes.util.find_library("m") or "libm.so.6")
_libm.hypot.restype = ctypes.c_double
_libm.hypot.argtypes = [ctypes.c_double, ctypes.c_double]
hypot = _libm.hypot


def sub(a: P, b: P) -> P:
    return (a[0] - b[0], a[1] - b[1])


def add(a: P, b: P) -> P:
    return (a[0] + b[0], a[1] + b[1])


def scale(a: P, k: float) -> P:
    return (a[0] * k, a[1] * k)


def dot(a: P, b: P) -> float:
    return a[0] * b[0] + a[1] * b[1]


def cross(a: P, b: P) -> float:
    return a[0] * b[1] - a[1] * b[0]


def norm(a: P) -> float:
    return hypot(a[0], a[1])


def dist(a: P, b: P) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def closest(q: P, a: P, b: P) -> tuple[P, float]:
    """The point of segment a-b nearest q, and where on it (0 at a, 1 at b)."""
    e = sub(b, a)
    t = clamp(dot(sub(q, a), e) / max(dot(e, e), 1e-18), 0.0, 1.0)
    return add(a, scale(e, t)), t


def crosses(a: P, b: P, c: P, d: P) -> bool:
    """Whether segment a-b crosses c-d (strictly)."""

    def side(p: P, q: P, r: P) -> float:
        return cross(sub(q, p), sub(r, p))

    return side(a, b, c) * side(a, b, d) < 0.0 and side(c, d, a) * side(c, d, b) < 0.0


def resample(p: list[P], step: float) -> list[P]:
    """The open polyline at an even step along it (its ends kept)."""
    if len(p) < 2:
        return list(p)
    s = [0.0]
    for i in range(len(p) - 1):
        s.append(s[-1] + dist(p[i], p[i + 1]))
    total = s[-1]
    n = max(as_usize(rround(total / step)), 1)
    out = []
    k = 0
    for i in range(n + 1):
        t = total * float(i) / float(n)
        while k + 2 < len(s) and s[k + 1] < t:
            k += 1
        span = s[k + 1] - s[k]
        f = clamp((t - s[k]) / span, 0.0, 1.0) if span > 0.0 else 0.0
        out.append(add(p[k], scale(sub(p[k + 1], p[k]), f)))
    return out


# --- Rust's conventions --------------------------------------------------------------


def rround(x: float) -> float:
    """f64::round: halves away from zero (Python's round() rounds them to even)."""
    r = float(math.trunc(x))
    if abs(x - r) >= 0.5:
        r += math.copysign(1.0, x)
    return r


def as_usize(x: float) -> int:
    """`x as usize`: truncated, negatives to 0."""
    return max(int(x), 0) if x == x else 0


def signum(x: float) -> float:
    """f64::signum: 1.0 for +0.0, -1.0 for -0.0."""
    return math.copysign(1.0, x)


def rem_euclid(x: float, m: float) -> float:
    """f64::rem_euclid for m > 0."""
    r = math.fmod(x, m)
    return r + abs(m) if r < 0.0 else r


def min_by(items, key):
    """Iterator::min_by_key: the first of the least."""
    best, bk = None, None
    for it in items:
        k = key(it)
        if bk is None or k < bk:
            best, bk = it, k
    return best


def max_by(items, key):
    """Iterator::max_by_key: the LAST of the greatest (Python's max() takes the first)."""
    best, bk = None, None
    for it in items:
        k = key(it)
        if bk is None or k >= bk:
            best, bk = it, k
    return best
