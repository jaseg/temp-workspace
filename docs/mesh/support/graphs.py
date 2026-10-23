"""Standard graph algorithms the curve's graph uses (rust/core/src/graph.rs): Edmonds'
blossom algorithm for a maximum matching, and union-find."""

from __future__ import annotations

from collections import deque

from .chacha import Rng

NO = -1


def matching(n: int, nbrs: list[list[int]], rng: Rng) -> list[int | None]:
    """A maximum matching (Edmonds' blossom algorithm), greedy start in a shuffled order:
    each vertex's mate (None: unmatched)."""
    mate = [NO] * n
    order = list(range(n))
    rng.shuffle(order)
    for v in order:
        if mate[v] == NO:
            for u in nbrs[v]:
                if mate[u] == NO and u != v:
                    mate[v], mate[u] = u, v
                    break
    base = list(range(n))
    parent = [NO] * n
    used = [False] * n
    blossom = [False] * n

    def lca(a: int, b: int) -> int:
        seen = set()
        while True:
            a = base[a]
            seen.add(a)
            if mate[a] == NO:
                break
            a = parent[mate[a]]
        while True:
            b = base[b]
            if b in seen:
                return b
            b = parent[mate[b]]

    def mark(v: int, b: int, child: int) -> None:
        while base[v] != b:
            blossom[base[v]] = True
            blossom[base[mate[v]]] = True
            parent[v] = child
            child = mate[v]
            v = parent[mate[v]]

    for root in order:
        if mate[root] != NO:
            continue
        touched = [root]
        used[root] = True
        queue = deque([root])
        end = NO
        while queue and end == NO:
            v = queue.popleft()
            for u in nbrs[v]:
                if base[v] == base[u] or mate[v] == u or u == v:
                    continue
                if u == root or (mate[u] != NO and parent[mate[u]] != NO):
                    b = lca(v, u)
                    mark(v, b, u)
                    mark(u, b, v)
                    for i in touched:
                        if blossom[base[i]]:
                            base[i] = b
                            if not used[i]:
                                used[i] = True
                                queue.append(i)
                    for i in touched:
                        blossom[i] = False
                elif parent[u] == NO:
                    parent[u] = v
                    touched.append(u)
                    if mate[u] == NO:
                        end = u
                        break
                    used[mate[u]] = True
                    touched.append(mate[u])
                    queue.append(mate[u])
        v = end
        while v != NO:
            pv = parent[v]
            nxt = mate[pv]
            mate[v], mate[pv] = pv, v
            v = nxt
        for i in touched:
            used[i] = False
            parent[i] = NO
            base[i] = i
    return [None if m == NO else m for m in mate]


class Union:
    """Union-find with path halving; ``join`` hangs b's root under a's."""

    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, a: int) -> int:
        p = self.p
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def join(self, a: int, b: int) -> bool:
        a, b = self.find(a), self.find(b)
        if a == b:
            return False
        self.p[b] = a
        return True

    def grow(self, n: int) -> None:
        self.p.extend(range(len(self.p), n))


class SortedSet:
    """A small set iterated in sorted order (the core's BTreeSet): adjacency of a planar
    graph, a handful of items each."""

    __slots__ = ("items",)

    def __init__(self, items=()):
        self.items = sorted(set(items))

    def add(self, x: int) -> None:
        import bisect

        i = bisect.bisect_left(self.items, x)
        if i == len(self.items) or self.items[i] != x:
            self.items.insert(i, x)

    def update(self, xs) -> None:
        for x in xs:
            self.add(x)

    def discard(self, x: int) -> None:
        import bisect

        i = bisect.bisect_left(self.items, x)
        if i < len(self.items) and self.items[i] == x:
            del self.items[i]

    def __contains__(self, x: object) -> bool:
        import bisect

        i = bisect.bisect_left(self.items, x)
        return i < len(self.items) and self.items[i] == x

    def __iter__(self):
        return iter(list(self.items))

    def __len__(self) -> int:
        return len(self.items)
