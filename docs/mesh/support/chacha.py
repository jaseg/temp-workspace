"""The curve graph's random source (rust/core/src/graph.rs ``Rng``): the ChaCha20 stream
(RFC 8439's block function, a 64-bit block counter, nonce zero) under a 256-bit key."""

from __future__ import annotations

M32 = 0xFFFFFFFF


def _rotl(x: int, n: int) -> int:
    return ((x << n) | (x >> (32 - n))) & M32


def chacha20_block(key: list[int], tail: list[int]) -> list[int]:
    """One block: the state after twenty rounds, plus itself."""
    init = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574, *key, *tail]
    s = list(init)

    def q(a: int, b: int, c: int, d: int) -> None:
        s[a] = (s[a] + s[b]) & M32
        s[d] = _rotl(s[d] ^ s[a], 16)
        s[c] = (s[c] + s[d]) & M32
        s[b] = _rotl(s[b] ^ s[c], 12)
        s[a] = (s[a] + s[b]) & M32
        s[d] = _rotl(s[d] ^ s[a], 8)
        s[c] = (s[c] + s[d]) & M32
        s[b] = _rotl(s[b] ^ s[c], 7)

    for _ in range(10):
        q(0, 4, 8, 12)
        q(1, 5, 9, 13)
        q(2, 6, 10, 14)
        q(3, 7, 11, 15)
        q(0, 5, 10, 15)
        q(1, 6, 11, 12)
        q(2, 7, 8, 13)
        q(3, 4, 9, 14)
    return [(o + i) & M32 for o, i in zip(s, init, strict=True)]


class Rng:
    def __init__(self, key: bytes):
        self.key = [int.from_bytes(key[4 * i : 4 * i + 4], "little") for i in range(8)]
        self.counter = 0
        self.block: list[int] = []
        self.used = 16

    def next_u32(self) -> int:
        if self.used == 16:
            c = self.counter
            self.block = chacha20_block(self.key, [c & M32, c >> 32, 0, 0])
            self.counter += 1
            self.used = 0
        self.used += 1
        return self.block[self.used - 1]

    def next_u64(self) -> int:
        lo = self.next_u32()
        return (self.next_u32() << 32) | lo

    def random(self) -> float:
        """In [0, 1) (53 bits)."""
        return float(self.next_u64() >> 11) / float(1 << 53)

    def below(self, n: int) -> int:
        """In 0 .. n - 1, without bias."""
        top = (1 << 64) - 1
        zone = top - (top % n + 1) % n
        while True:
            w = self.next_u64()
            if w <= zone:
                return w % n

    def shuffle(self, v: list) -> None:
        for i in range(len(v) - 1, 0, -1):
            j = self.below(i + 1)
            v[i], v[j] = v[j], v[i]
