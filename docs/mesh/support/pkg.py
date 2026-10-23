"""What sfc.py imports from the package (``mesh``, ``rand``), copied verbatim from
src/yanartas_pillowbox (by the notebook's build), and stand-ins for its progress reports and
checkpoints, which do nothing here."""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import math
import secrets
from collections.abc import Callable, MutableSequence, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

# ---- mesh.py ---------------------------------------------------------------------------
CHUNK = 50_000  # queries at a time (bounds the memory a query takes)


RIGHT, DOWN, LEFT, UP = 0b0001, 0b0010, 0b0100, 0b1000


Point = tuple[float, float]


Piece = tuple[Point, Point | None, Point]


class MeshError(ValueError):
    """The mesh cannot be laid out (e.g. no room for its exit cell)."""


@dataclass(frozen=True)
class Mesh:
    """A generated mesh: one polyline per net, from its end at the exit cell's open side
    round the area back to its other end there (``ends``: the two points)."""

    traces: tuple[tuple[Point, ...], ...]
    cell: float  # the exit cell's size (KiMesh: every cell's)
    cells: int  # cells covered (KiMesh: grid cells; sfc: the curve's graph cells)
    unreached: int  # parts the mesh could not reach (KiMesh: grid cells; sfc: regions)
    origin: Point = (0.0, 0.0)  # the exit cell's corner: the grid's alignment
    algorithm: str = "kimesh"  # what laid it out: "kimesh" or "sfc"
    # each net as lines and arcs (``traces`` then: these drawn as a polyline), if fitted
    arcs: tuple[tuple[Piece, ...], ...] | None = None
    # the partitions' traces in turn (how many each; one partition: all), and their areas
    groups: tuple[int, ...] = ()
    parts: tuple = ()  # (shapely polygons)
    # the traces matched in length together, in turn (how many each: ``matching``; none
    # given: each partition's)
    matched: tuple[int, ...] = ()

    @property
    def pairs(self) -> list[tuple[int, int]]:
        """The neighbouring traces matched in length together (as differential pairs)."""
        sizes = self.matched or self.groups or (len(self.traces),)
        out, first = [], 0
        for size in sizes:
            out += [(i, i + 1) for i in range(first, first + size - 1)]
            first += size
        return out

    @property
    def ends(self) -> tuple[tuple[Point, Point], ...]:
        return tuple((t[0], t[-1]) for t in self.traces)


def matching(n: int) -> tuple[int, ...]:
    """How a ribbon's ``n`` neighbouring traces are matched in length: in pairs (1-2, 3-4,
    ...), an odd one's middle group three (7: 1-2, 3-4-5, 6-7); between groups not, so that
    a pair can grow into a hole its ribbon cannot."""
    if n < 2:
        return (n,) if n else ()
    sizes = [2] * (n // 2)
    if n % 2:
        sizes[len(sizes) // 2] += 1
    return tuple(sizes)


def sample_arcs(pieces: Sequence[Piece], tol: float) -> tuple[Point, ...]:
    """The pieces as a polyline: each arc's chords within ``tol`` of it."""
    out: list[Point] = [pieces[0][0]] if pieces else []
    for a, m, b in pieces:
        if m is not None:
            # (the circle through the three points; the way round from a through m to b)
            (ax, ay), (mx, my), (bx, by) = a, m, b
            d = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
            if abs(d) > 1e-12:
                a2, m2, b2 = ax * ax + ay * ay, mx * mx + my * my, bx * bx + by * by
                ox = (a2 * (my - by) + m2 * (by - ay) + b2 * (ay - my)) / d
                oy = (a2 * (bx - mx) + m2 * (ax - bx) + b2 * (mx - ax)) / d
                r = math.dist((ox, oy), a)
                t0 = math.atan2(ay - oy, ax - ox)
                tm = (math.atan2(my - oy, mx - ox) - t0) % math.tau
                sweep = (math.atan2(by - oy, bx - ox) - t0) % math.tau
                if tm > sweep:
                    sweep -= math.tau
                step = 2 * math.acos(max(1 - tol / r, -1.0))
                k = max(2, math.ceil(abs(sweep) / step))
                out += [
                    (ox + r * math.cos(t0 + sweep * i / k), oy + r * math.sin(t0 + sweep * i / k))
                    for i in range(1, k)
                ]
        out.append(b)
    return tuple(out)


def resample(p: np.ndarray, step: float) -> np.ndarray:
    """The open polyline at an even step along it (its ends kept)."""
    seg = np.hypot(*np.diff(p, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(1, round(s[-1] / step))
    t = np.linspace(0.0, s[-1], n + 1)
    return np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], 1)


class Grid:
    """Points bucketed on a square grid, for nearest-point queries."""

    def __init__(self, p: np.ndarray, size: float) -> None:
        self.p, self.size = p, size
        keys = self._keys(np.floor(p / size).astype(np.int64))
        self.order = np.argsort(keys, kind="stable")
        self.keys = keys[self.order]

    @staticmethod
    def _keys(c: np.ndarray) -> np.ndarray:
        return c[:, 0] * 1_000_003 + c[:, 1]

    def nearest(
        self, q: np.ndarray, ok: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None
    ) -> np.ndarray:
        """For each query, the nearest point in its cell or the eight around it (for which
        ``ok(query indices, point indices)`` holds); -1 where there is none."""
        out = np.full(len(q), -1)
        for k in range(0, len(q), CHUNK):  # (bounded memory, however many)
            out[k : k + CHUNK] = self._nearest(
                q[k : k + CHUNK], None if ok is None else (lambda qi, pi, k=k: ok(qi + k, pi))
            )
        return out

    def within(self, q: np.ndarray, r: float) -> tuple[np.ndarray, np.ndarray]:
        """Every pair of a query and a point no further than ``r`` (at most the grid's
        size) from it: the queries' indices and the points'."""
        qs, ps = [], []
        for k in range(0, len(q), CHUNK):
            part = q[k : k + CHUNK]
            c = np.floor(part / self.size).astype(np.int64)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    keys = self._keys(c + np.array([dx, dy]))
                    lo = np.searchsorted(self.keys, keys, "left")
                    count = np.searchsorted(self.keys, keys, "right") - lo
                    has = np.nonzero(count)[0]
                    if not len(has):
                        continue
                    cnt = count[has]
                    qi = np.repeat(has, cnt)
                    first = np.concatenate([[0], np.cumsum(cnt)[:-1]])
                    pi = self.order[np.repeat(lo[has] - first, cnt) + np.arange(len(qi))]
                    v = part[qi] - self.p[pi]
                    near = v[:, 0] ** 2 + v[:, 1] ** 2 <= r * r
                    qs.append(qi[near] + k)
                    ps.append(pi[near])
        if not qs:
            return np.zeros(0, int), np.zeros(0, int)
        return np.concatenate(qs), np.concatenate(ps)

    def _nearest(
        self, q: np.ndarray, ok: Callable[[np.ndarray, np.ndarray], np.ndarray] | None
    ) -> np.ndarray:
        c = np.floor(q / self.size).astype(np.int64)
        best = np.full(len(q), np.inf)
        out = np.full(len(q), -1)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                keys = self._keys(c + np.array([dx, dy]))
                lo = np.searchsorted(self.keys, keys, "left")
                count = np.searchsorted(self.keys, keys, "right") - lo
                has = np.nonzero(count)[0]
                if not len(has):
                    continue
                cnt = count[has]
                qi = np.repeat(has, cnt)  # (grouped by query, in order)
                first = np.concatenate([[0], np.cumsum(cnt)[:-1]])
                pi = self.order[np.repeat(lo[has] - first, cnt) + np.arange(len(qi))]
                d2 = np.sum((q[qi] - self.p[pi]) ** 2, axis=1)
                if ok is not None:
                    d2[~ok(qi, pi)] = np.inf
                low = np.minimum.reduceat(d2, first)
                at = d2 == np.repeat(low, cnt)
                take, pick = np.unique(qi[at], return_index=True)
                better = low[np.searchsorted(has, take)] < best[take]
                take = take[better]
                best[take] = low[np.searchsorted(has, take)]
                out[take] = pi[at][pick[better]]
        return out


# ---- rand.py ---------------------------------------------------------------------------
DOMAIN = b"yanartas-pillowbox/rng/v1"


BLOCK = 1024  # bytes of stream drawn at a time


def _frame(*parts: bytes) -> bytes:
    """The parts, each length-prefixed: unambiguous however they split."""
    return b"".join(len(p).to_bytes(4, "big") + p for p in parts)


def derive(key: bytes, label: str) -> bytes:
    """The 256-bit key ``key`` gives the consumer ``label`` (e.g. "layer/F.Cu", "kimesh")."""
    return hashlib.shake_256(_frame(DOMAIN, b"key", key, label.encode())).digest(32)


def key_of(seed: str | int | bytes | None) -> bytes:
    """A seed's 256-bit key: text (as ``Config.mesh_seed``) distilled; a whole number (as
    tests and scripts pass) as its digits, in a domain of its own; a key as it is; none, a
    fresh one from the system's secure source."""
    if seed is None:
        return secrets.token_bytes(32)
    if isinstance(seed, bytes):
        if len(seed) != 32:
            raise ValueError("a key is 32 bytes")
        return seed
    kind = b"int" if isinstance(seed, int) else b"text"
    return hashlib.shake_256(_frame(DOMAIN, b"seed", kind, str(seed).encode())).digest(32)


@dataclasses.dataclass
class Rand:
    """A deterministic, cryptographically secure stream of uniform numbers from a 256-bit
    key (``key``, hex; ``block`` and ``pos`` where in the stream it is: its whole state, so
    checkpoints keep it)."""

    key: str
    block: int = 0
    pos: int = 0

    def __post_init__(self) -> None:
        self._buf = b""
        self._at = -1  # (the block ``_buf`` holds)

    @classmethod
    def of(cls, seed: str | int | bytes | None, label: str) -> Rand:
        """The stream for consumer ``label`` of ``seed``."""
        return cls(derive(key_of(seed), label).hex())

    def child(self, label: str) -> Rand:
        """A stream of its own for consumer ``label`` (from the key, not this stream)."""
        return Rand(self.key_for(label).hex())

    def key_for(self, label: str) -> bytes:
        """The 256-bit key for consumer ``label`` (e.g. one in the Rust core)."""
        return derive(bytes.fromhex(self.key), label)

    def take(self, n: int) -> bytes:
        """The stream's next ``n`` bytes."""
        out = bytearray()
        while len(out) < n:
            if self._at != self.block:
                msg = _frame(
                    DOMAIN, b"stream", bytes.fromhex(self.key), self.block.to_bytes(8, "big")
                )
                self._buf = hashlib.shake_256(msg).digest(BLOCK)
                self._at = self.block
            take = min(n - len(out), BLOCK - self.pos)
            out += self._buf[self.pos : self.pos + take]
            self.pos += take
            if self.pos == BLOCK:
                self.block, self.pos = self.block + 1, 0
        return bytes(out)

    def _words(self, n: int) -> np.ndarray:
        return np.frombuffer(self.take(8 * n), dtype="<u8")

    def random(self, size: int | tuple[int, ...] | None = None) -> Any:
        """Uniform in [0, 1): one float, or an array of ``size`` (53 bits each)."""
        shape = () if size is None else size
        n = int(np.prod(shape))
        x = (self._words(n) >> np.uint64(11)).astype(float) / float(1 << 53)
        return float(x[0]) if size is None else x.reshape(shape)

    def uniform(self, low: Any = 0.0, high: Any = 1.0, size: Any = None) -> Any:
        """Uniform in [low, high) (broadcast against ``size``, as numpy's)."""
        low, high = np.asarray(low, float), np.asarray(high, float)
        if size is None:
            size = np.broadcast(low, high).shape or None
        u = self.random(size)
        out = low + (high - low) * u
        return float(out) if np.ndim(out) == 0 else out

    def below(self, n: int) -> int:
        """Uniform in 0 .. n - 1, without bias (64-bit draws, the uneven top rejected)."""
        if n <= 0:
            raise ValueError("n must be positive")
        limit = (1 << 64) - (1 << 64) % n
        while True:
            w = int.from_bytes(self.take(8), "little")
            if w < limit:
                return w % n

    def shuffle(self, x: MutableSequence[Any]) -> None:
        """In place, uniformly (Fisher-Yates)."""
        for i in range(len(x) - 1, 0, -1):
            j = self.below(i + 1)
            x[i], x[j] = x[j], x[i]


# ---- stand-ins -------------------------------------------------------------------------
class progress:
    """sfc's progress reports: ignored."""

    @staticmethod
    def report(*a: Any, **k: Any) -> None:
        pass


class checkpoint:
    """sfc's step timing and checkpoints: none."""

    @staticmethod
    def step(name: str) -> Callable:
        return lambda f: f

    @staticmethod
    def run(f: Callable) -> Callable:
        return f

    @staticmethod
    def timed(name: str) -> contextlib.AbstractContextManager:
        return contextlib.nullcontext()
