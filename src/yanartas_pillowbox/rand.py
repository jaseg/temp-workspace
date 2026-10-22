"""The layouts' randomness: deterministic, from a seed, and cryptographically secure.

A seed (any text) is distilled into a 256-bit key; each consumer of randomness gets a key
of its own derived from it under a label of its own (``derive``: domain separation, so no
two of them, here or in the Rust core, ever draw on one stream). ``Rand`` is a stream of
uniform numbers from a key: SHAKE-256 in counter mode (each block the XOF's output for the
key and the block's number, under a domain of its own apart from the keys'). The Rust core
draws from ChaCha20 under keys derived here (``Rand.key_for``)."""

from __future__ import annotations

import dataclasses
import hashlib
import secrets
from collections.abc import MutableSequence
from typing import Any

import numpy as np

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
