#!/usr/bin/env python3
"""L4 (In3.Cu) power planes for the six-layer scope-fe board (RULES.md rule 10, TOPOLOGY.md section 6).

    import board_power
    board_power.apply(board)            # after all blocks are merged and all supply vias exist
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    print(board_power.table(board_power.verify(board)))

apply(board) removes the In3.Cu copper zones of the rail nets that came in with the blocks and rebuilds L4:
  * +3V3 background zone over the whole board (priority 0),
  * one island per rail (+5V, -5V, +2V5, -2V5, +1V2, VBUS, VTAP_P, VTAP_N; priority 2).
The geometry is derived from the board at call time: per rail the landing points are all vias and
through-hole pads of that net.  Each island is a tree grown from the rail's landing points inside the power
block (or, for VTAP_*, from its 0R feed) by an octilinear grid router (0.25 mm grid) that keeps clear of
In3.Cu keep-outs, other rails' landing points (with their 0.5 mm lands) and the islands already placed.
Paths are tried 2.0 mm wide first (trunk), then 1.5, 1.0, 0.6 mm where the board is too tight.
Each island polygon = union of octilinear path rectangles + octagonal joints (45-degree chamfers) +
octagonal lands (via radius + 0.5 mm), closed by a chamfered inflate / deflate.
In1.Cu pour keep-outs (node windows, SMA cut-outs) that are not also on In3.Cu are replicated on In3.Cu,
unless one would cover a supply landing point (then it is skipped and reported).

Command line:  python3 board_power.py in.kicad_pcb out.kicad_pcb [render.png]
"""
import heapq
import math
import sys

import numpy as np
import pcbnew
from matplotlib.path import Path as MPath

MM = 1e6
LAYER = pcbnew.In3_Cu
RES = 0.25                     # router grid (mm)
CLEAR = 0.15                   # zone clearance
MINW = 0.2                     # zone min width
LAND = 0.5                     # copper ring around every own landing point
GAP = 0.45                     # extra spacing between two islands (copper to copper = CLEAR + GAP)
EDGE = 0.5                     # copper to board edge used by the router
WIDTHS = (2.0, 1.5, 1.0, 0.6)  # trunk first, then branches, then fall-backs (reported)
PRIO_BG, PRIO_ISLAND = 0, 2
POWER_BLOCK = (74.0, 0.0, 100.0, 22.5)   # board mm (origin = board top-left)

BACKGROUND = "+3V3"
# routing order: the strips first (fixed rows), then the short +1V2, then the long rails
ISLANDS = ["+1V2", "VBUS", "+5V", "-5V", "-2V5", "+2V5"]
RAILS = [BACKGROUND] + ISLANDS
FEED = {}
STRIPS = ["/VTAP_P", "/VTAP_N"]     # L3 tracks along the tap row (not plane rails, 12.5 mA each)
L3 = pcbnew.In2_Cu
STRIP_W = 0.5                       # VTAP track width on L3
STRIP_CLR = 0.3                     # VTAP track to foreign via
FEED_W = 1.5                        # L3 feeder width
VIA_D, VIA_DRILL, VIA_PITCH = 0.45, 0.2, 0.8
L3_COST = {"VBUS": 12.0}            # step-cost factor on L3 (VBUS = 220 mA stays on L4); default below
L3_COST_DEFAULT = 2.5
HOP_COST = 40.0                     # cost of one L4<->L3 change (in grid steps)
PRIO_FEED = 3


def fmm(v):
    return int(round(float(v) * MM))


# --------------------------------------------------------------------------------------------- board data
def board_box(board):
    bb = board.GetBoardEdgesBoundingBox()
    return bb.GetX() / MM, bb.GetY() / MM, bb.GetRight() / MM, bb.GetBottom() / MM


def rail_nets(board):
    out = {}
    for r in RAILS:
        for cand in (r, r.lstrip("/"), "/" + r.lstrip("/")):
            n = board.FindNet(cand)
            if n is not None and n.GetNetCode() > 0:
                out[r] = cand
                break
    return out


def landing_points(board, nets):
    """{rail: [(x, y, r)]} vias and through-hole pads of the rail nets (pcbnew mm)."""
    inv = {v: k for k, v in nets.items()}
    pts = {r: [] for r in nets}
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" and t.GetNetname() in inv:
            p = t.GetPosition()
            pts[inv[t.GetNetname()]].append((p.x / MM, p.y / MM, t.GetWidth() / MM / 2))
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and p.GetNetname() in inv:
                q = p.GetPosition()
                s = p.GetSize()
                pts[inv[p.GetNetname()]].append((q.x / MM, q.y / MM, max(s.x, s.y) / MM / 2))
    return pts


def other_holes(board, nets):
    """Through-hole pads / NPTH of non-rail nets: big holes the islands should not run over."""
    names = set(nets.values())
    out = []
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH) and p.GetNetname() not in names:
                q = p.GetPosition()
                s = p.GetSize()
                d = p.GetDrillSize()
                rr = max(s.x, s.y, d.x, d.y) / MM / 2
                out.append((q.x / MM, q.y / MM, rr))
    return out


def poly_points(spset, i=0):
    ol = spset.Outline(i)
    return [(ol.CPoint(k).x / MM, ol.CPoint(k).y / MM) for k in range(ol.PointCount())]


def is_pour_keepout(z):
    return z.GetIsRuleArea() and z.GetDoNotAllowCopperPour()


def replicate_keepouts(board, pts, report):
    """Copy In1.Cu pour keep-outs to In3.Cu (node windows etc.) unless they are already on In3."""
    allpts = [(x, y) for r in pts for (x, y, _) in pts[r]]
    have = set()
    for z in board.Zones():
        if is_pour_keepout(z) and z.GetLayerSet().Contains(LAYER):
            bb = z.GetBoundingBox()
            have.add((round(bb.GetX() / MM, 2), round(bb.GetY() / MM, 2), round(bb.GetRight() / MM, 2),
                      round(bb.GetBottom() / MM, 2)))
    new = []
    for z in list(board.Zones()):
        if not (is_pour_keepout(z) and z.GetLayerSet().Contains(pcbnew.In1_Cu)) or z.GetLayerSet().Contains(LAYER):
            continue
        bb = z.GetBoundingBox()
        key = (round(bb.GetX() / MM, 2), round(bb.GetY() / MM, 2), round(bb.GetRight() / MM, 2),
               round(bb.GetBottom() / MM, 2))
        if key in have:
            continue
        ol = z.Outline()
        hit = [p for p in allpts if ol.Contains(pcbnew.VECTOR2I(fmm(p[0]), fmm(p[1])))]
        if hit:
            report.setdefault("keepout_skipped", []).append((key, hit))
            continue
        k = pcbnew.ZONE(board)
        k.SetIsRuleArea(True)
        k.SetDoNotAllowCopperPour(True)
        k.SetDoNotAllowVias(False)
        k.SetDoNotAllowTracks(False)
        k.SetDoNotAllowPads(False)
        k.SetDoNotAllowFootprints(False)
        k.SetLayer(LAYER)
        cp = pcbnew.SHAPE_POLY_SET(ol)
        cp.thisown = False                 # the zone takes ownership
        k.SetOutline(cp)
        k.SetZoneName("L4_window")
        board.Add(k)
        have.add(key)
        new.append(k)
    report["keepouts_added"] = len(new)


def l4_keepouts(board):
    out = []
    for z in board.Zones():
        if is_pour_keepout(z) and z.GetLayerSet().Contains(LAYER):
            o = z.Outline()
            for i in range(o.OutlineCount()):
                pp = poly_points(o, i)
                if len(pp) >= 3:
                    out.append(pp)
    return out


# --------------------------------------------------------------------------------------------- raster
class Grid:
    def __init__(self, box):
        self.x0, self.y0, x1, y1 = box
        self.nx = int(math.ceil((x1 - self.x0) / RES)) + 1
        self.ny = int(math.ceil((y1 - self.y0) / RES)) + 1
        self.box = box
        xs = self.x0 + RES * np.arange(self.nx)
        ys = self.y0 + RES * np.arange(self.ny)
        self.X, self.Y = np.meshgrid(xs, ys)          # [iy, ix]

    def empty(self):
        return np.zeros((self.ny, self.nx), bool)

    def ij(self, x, y):
        return int(round((y - self.y0) / RES)), int(round((x - self.x0) / RES))

    def xy(self, i, j):
        return self.x0 + j * RES, self.y0 + i * RES

    def disk(self, m, x, y, r):
        i0, j0 = self.ij(x - r, y - r)
        i1, j1 = self.ij(x + r, y + r)
        i0, j0 = max(i0 - 1, 0), max(j0 - 1, 0)
        i1, j1 = min(i1 + 2, self.ny), min(j1 + 2, self.nx)
        if i0 >= i1 or j0 >= j1:
            return
        sub = (self.X[i0:i1, j0:j1] - x) ** 2 + (self.Y[i0:i1, j0:j1] - y) ** 2 <= r * r
        m[i0:i1, j0:j1] |= sub

    def poly(self, m, pts, grow=0.0):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        i0, j0 = self.ij(min(xs) - grow, min(ys) - grow)
        i1, j1 = self.ij(max(xs) + grow, max(ys) + grow)
        i0, j0 = max(i0 - 1, 0), max(j0 - 1, 0)
        i1, j1 = min(i1 + 2, self.ny), min(j1 + 2, self.nx)
        if i0 >= i1 or j0 >= j1:
            return
        path = MPath(pts + [pts[0]], closed=True)
        P = np.column_stack([self.X[i0:i1, j0:j1].ravel(), self.Y[i0:i1, j0:j1].ravel()])
        inside = path.contains_points(P).reshape(i1 - i0, j1 - j0)
        if grow > 0:
            inside = dilate(inside, grow)
        m[i0:i1, j0:j1] |= inside


def dilate(m, r):
    n = int(math.ceil(r / RES))
    if n <= 0:
        return m.copy()
    out = m.copy()
    ny, nx = m.shape
    for di in range(-n, n + 1):
        for dj in range(-n, n + 1):
            if (di * di + dj * dj) * RES * RES > r * r + 1e-9 or (di == 0 and dj == 0):
                continue
            src = m[max(0, -di):ny - max(0, di), max(0, -dj):nx - max(0, dj)]
            out[max(0, di):ny - max(0, -di), max(0, dj):nx - max(0, -dj)] |= src
    return out


DIRS = [(0, 1, 1.0), (0, -1, 1.0), (1, 0, 1.0), (-1, 0, 1.0),
        (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]


def dijkstra(free, sources, targets, cost=None):
    """free: bool[ny, nx]; sources: set of flat idx; targets: dict flat idx -> key; cost: float[ny, nx] extra
    cost per step (soft reservations). Returns (key, path idx list)."""
    ny, nx = free.shape
    fl = free.ravel().tolist()
    cl = cost.ravel().tolist() if cost is not None else [0.0] * (nx * ny)
    dist = {}
    prev = {}
    h = []
    for s in sources:
        if fl[s]:
            dist[s] = 0.0
            prev[s] = -1
            heapq.heappush(h, (0.0, s))
    turn = {}
    while h:
        d, u = heapq.heappop(h)
        if d > dist.get(u, 1e18):
            continue
        if u in targets:
            path = []
            while u != -1:
                path.append(u)
                u = prev[u]
            return targets[path[0]], path[::-1]
        i, j = divmod(u, nx)
        for di, dj, c in DIRS:
            ii, jj = i + di, j + dj
            if 0 <= ii < ny and 0 <= jj < nx:
                v = ii * nx + jj
                if not fl[v]:
                    continue
                nd = d + c * (1.0 + cl[v])
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(h, (nd, v))
    return None, None


def line_cells(i0, j0, i1, j1):
    n = max(abs(i1 - i0), abs(j1 - j0))
    if n == 0:
        return [(i0, j0)]
    return [(i0 + (i1 - i0) * k // n, j0 + (j1 - j0) * k // n) for k in range(n + 1)]


def octi(a, b):
    di, dj = b[0] - a[0], b[1] - a[1]
    return di == 0 or dj == 0 or abs(di) == abs(dj)


def seg_free(free, a, b):
    return all(free[i, j] for i, j in line_cells(a[0], a[1], b[0], b[1]))


def simplify(free, cells):
    """Grid path -> octilinear polyline (cell coordinates) with as few corners as the free mask allows."""
    out = [cells[0]]
    i = 0
    n = len(cells)
    while i < n - 1:
        a = cells[i]
        best = None
        lo = i + 1
        for j in range(n - 1, i, -1):
            b = cells[j]
            if octi(a, b):
                if seg_free(free, a, b):
                    best = (j, [b])
                    break
                continue
            di, dj = b[0] - a[0], b[1] - a[1]
            m = min(abs(di), abs(dj))
            s_i, s_j = (1 if di > 0 else -1), (1 if dj > 0 else -1)
            k1 = (a[0] + s_i * m, a[1] + s_j * m)          # diagonal first
            k2 = (b[0] - s_i * m, b[1] - s_j * m)          # axis first
            for k in (k1, k2):
                if seg_free(free, a, k) and seg_free(free, k, b):
                    best = (j, [k, b])
                    break
            if best:
                break
        if best is None:
            best = (lo, [cells[lo]])
        i = best[0]
        for p in best[1]:
            if p != out[-1]:
                out.append(p)
    return out


# --------------------------------------------------------------------------------------------- geometry
def octagon(x, y, a):
    """Axis-aligned regular octagon with apothem a (pcbnew mm) as a SHAPE_POLY_SET."""
    t = a * math.tan(math.pi / 8)
    pts = [(a, t), (t, a), (-t, a), (-a, t), (-a, -t), (-t, -a), (t, -a), (a, -t)]
    return polyset([(x + u, y + v) for u, v in pts])


def polyset(pts):
    s = pcbnew.SHAPE_POLY_SET()
    s.NewOutline()
    for x, y in pts:
        s.Append(fmm(x), fmm(y))
    return s


def seg_rect(p, q, w):
    dx, dy = q[0] - p[0], q[1] - p[1]
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return None
    nx, ny = -dy / L * w / 2, dx / L * w / 2
    return polyset([(p[0] + nx, p[1] + ny), (q[0] + nx, q[1] + ny), (q[0] - nx, q[1] - ny), (p[0] - nx, p[1] - ny)])


def union(parts):
    acc = pcbnew.SHAPE_POLY_SET()
    for s in parts:
        if s is not None:
            acc.BooleanAdd(s, pcbnew.SHAPE_POLY_SET.PM_FAST)
    acc.Simplify(pcbnew.SHAPE_POLY_SET.PM_STRICTLY_SIMPLE)
    return acc


def chamfer_close(s, c=0.3):
    s = pcbnew.SHAPE_POLY_SET(s)
    s.Inflate(fmm(c), 8, pcbnew.SHAPE_POLY_SET.CHAMFER_ALL_CORNERS)
    s.Inflate(-fmm(c), 8, pcbnew.SHAPE_POLY_SET.CHAMFER_ALL_CORNERS)
    s.Simplify(pcbnew.SHAPE_POLY_SET.PM_STRICTLY_SIMPLE)
    return s


# --------------------------------------------------------------------------------------------- planner
def cluster(points, d=1.6):
    """Group landing points closer than d (via pairs) -> list of lists."""
    groups = []
    for p in points:
        hit = [g for g in groups if any(math.hypot(p[0] - q[0], p[1] - q[1]) < d for q in g)]
        merged = [p]
        for g in hit:
            merged += g
            groups.remove(g)
        groups.append(merged)
    return groups


def _mst(groups):
    """Euclidean MST over group centroids -> list of (p, q)."""
    c = [(sum(p[0] for p in g) / len(g), sum(p[1] for p in g) / len(g)) for g in groups]
    if len(c) < 2:
        return []
    inn = {0}
    out = []
    while len(inn) < len(c):
        best = None
        for i in inn:
            for j in range(len(c)):
                if j in inn:
                    continue
                d = math.hypot(c[i][0] - c[j][0], c[i][1] - c[j][1])
                if best is None or d < best[0]:
                    best = (d, i, j)
        inn.add(best[2])
        out.append((c[best[1]], c[best[2]]))
    return out


def _components(mask):
    """4-connected labels of a bool mask (BFS; small grids only)."""
    ny, nx = mask.shape
    lab = np.zeros(mask.shape, np.int32).ravel()
    fl = mask.ravel()
    n = 0
    for s0 in np.flatnonzero(fl):
        if lab[s0]:
            continue
        n += 1
        lab[s0] = n
        st = [s0]
        while st:
            u = st.pop()
            i, j = divmod(u, nx)
            for v, ok in ((u - nx, i > 0), (u + nx, i < ny - 1), (u - 1, j > 0), (u + 1, j < nx - 1)):
                if ok and fl[v] and not lab[v]:
                    lab[v] = n
                    st.append(v)
    return lab.reshape(mask.shape), n


RESERVE_R = 1.75      # soft reservation half-width around the straight MST links of rails not yet routed
RESERVE_COST = 3.0    # extra cost factor per step inside a reservation
ORDERS = 12           # routing orders tried (the first is ISLANDS as listed; others seeded shuffles)


def seg_mask(G, m, p, q, r):
    """mark grid cells within r of segment p-q."""
    x0, x1 = min(p[0], q[0]) - r, max(p[0], q[0]) + r
    y0, y1 = min(p[1], q[1]) - r, max(p[1], q[1]) + r
    i0, j0 = G.ij(x0, y0)
    i1, j1 = G.ij(x1, y1)
    i0, j0 = max(i0 - 1, 0), max(j0 - 1, 0)
    i1, j1 = min(i1 + 2, G.ny), min(j1 + 2, G.nx)
    if i0 >= i1 or j0 >= j1:
        return
    X, Y = G.X[i0:i1, j0:j1], G.Y[i0:i1, j0:j1]
    dx, dy = q[0] - p[0], q[1] - p[1]
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        d2 = (X - p[0]) ** 2 + (Y - p[1]) ** 2
    else:
        t = np.clip(((X - p[0]) * dx + (Y - p[1]) * dy) / L2, 0, 1)
        d2 = (X - p[0] - t * dx) ** 2 + (Y - p[1] - t * dy) ** 2
    m[i0:i1, j0:j1] |= d2 <= r * r


def strip_tracks(board, nets_all):
    """VTAP_P / VTAP_N on L3: a 0.5 mm track tree (0.1 mm grid router, octilinear) from the 0R-link via (the via
    of the net farthest from its row) to every resistor via of the net, >= STRIP_CLR from every foreign via,
    out of the In2 keep-outs (node windows), clear of the existing L3 tracks. Returns ({net: [lines]}, problems)."""
    global RES
    allv = [(t.GetPosition().x / MM, t.GetPosition().y / MM, t.GetWidth() / MM / 2, t.GetNetname())
            for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    nets = [n for n in STRIPS if board.FindNet(n) is not None and sum(1 for v in allv if v[3] == n) >= 2]
    if not nets:
        return {}, []
    own = {n: [(x, y) for (x, y, r, m) in allv if m == n] for n in nets}
    xs = [p[0] for n in nets for p in own[n]]
    ys = [p[1] for n in nets for p in own[n]]
    bb = board_box(board)
    sub = (max(bb[0], min(xs) - 4), max(bb[1], min(ys) - 4), min(bb[2], max(xs) + 4), min(bb[3], max(ys) + 4))
    old = RES
    RES = 0.1
    try:
        G = Grid(sub)
        hw = STRIP_W / 2
        base = (G.X < bb[0] + 0.5 + hw) | (G.X > bb[2] - 0.5 - hw) | (G.Y < bb[1] + 0.5 + hw) | (G.Y > bb[3] - 0.5 - hw)
        for z in board.Zones():
            if is_pour_keepout(z) and z.GetLayerSet().Contains(L3):
                o = z.Outline()
                for i in range(o.OutlineCount()):
                    pp = poly_points(o, i)
                    if len(pp) >= 3:
                        G.poly(base, pp, grow=CLEAR + hw)
        for t in board.GetTracks():
            if t.GetClass() == "PCB_TRACK" and t.GetLayer() == L3 and t.GetNetname() not in nets:
                a_, b_ = t.GetStart(), t.GetEnd()
                seg_mask(G, base, (a_.x / MM, a_.y / MM), (b_.x / MM, b_.y / MM), t.GetWidth() / MM / 2 + CLEAR + hw)
        for (x, y, r) in other_holes(board, {}):
            G.disk(base, x, y, r + CLEAR + hw)
        out, problems = {}, []
        drawn = {}

        def route(net, others):
            obst = base.copy()
            for (x, y, r, m) in allv:
                if m != net:
                    G.disk(obst, x, y, r + STRIP_CLR + hw)
            for o in others:
                for line in drawn.get(o, []):
                    for p_, q_ in zip(line[:-1], line[1:]):
                        seg_mask(G, obst, p_, q_, 2 * hw + STRIP_CLR)
            free = ~obst
            pts_ = own[net]
            yrow = sorted(p[1] for p in pts_)[len(pts_) // 2]
            feed = max(pts_, key=lambda p: abs(p[1] - yrow))
            tree = set()
            m = G.empty()
            G.disk(m, feed[0], feed[1], 0.12)
            tree.update(np.flatnonzero((m & free).ravel()).tolist())
            todo = [p for p in pts_ if p != feed]
            lines, miss = [], []
            while todo:
                targets = {}
                for k, p in enumerate(todo):
                    mm_ = G.empty()
                    G.disk(mm_, p[0], p[1], 0.12)
                    for c in np.flatnonzero((mm_ & free).ravel()).tolist():
                        targets[c] = k
                src = {c for c in tree if free.ravel()[c]}
                k, path = dijkstra(free, src, targets) if targets and src else (None, None)
                if k is None:
                    miss += todo
                    break
                poly = simplify(free, [divmod(c, G.nx) for c in path])
                line = [G.xy(i, j) for i, j in poly]
                lines.append(line)
                for a2, b2 in zip(poly[:-1], poly[1:]):
                    for i, j in line_cells(a2[0], a2[1], b2[0], b2[1]):
                        tree.add(i * G.nx + j)
                todo.pop(k)
            return lines, miss
        order = sorted(nets, key=lambda n: -max(abs(p[1] - sorted(q[1] for q in own[n])[len(own[n]) // 2])
                                                 for p in own[n]))
        for attempt in (order, order[::-1]):
            drawn.clear()
            miss_all = []
            for n in attempt:
                lines, miss = route(n, [o for o in attempt if o != n and o in drawn])
                drawn[n] = lines
                miss_all += [(n, round(x - 100, 3), round(y - 100, 3)) for x, y in miss]
            if not miss_all:
                break
        out = dict(drawn)
        problems = miss_all
    finally:
        RES = old
    return out, problems


def _pt_seg(x, y, p, q):
    dx, dy = q[0] - p[0], q[1] - p[1]
    L2 = dx * dx + dy * dy
    t = 0 if L2 < 1e-12 else max(0, min(1, ((x - p[0]) * dx + (y - p[1]) * dy) / L2))
    return math.hypot(x - p[0] - t * dx, y - p[1] - t * dy)



# ============================================================================================ L3 corridor plan
# Hand-specified corridor centre lines (board mm, origin = board top-left), TOPOLOGY.md section 8.
# Each entry: rail -> list of (polyline, width). Branches (0.8 mm tracks) to the landing vias are routed
# automatically from these corridors (max BRANCH_MAX mm); farther vias are reported, not chased.
TRUNKS = {
    "-5V": [   # outermost: top edge, then down the west side past the SMA keep-outs to the input stage
        ([(90.25, 8.9), (87.4, 6.05), (87.4, 2.0), (86.6, 1.2), (8.4, 1.2), (7.6, 2.0), (7.6, 7.4),
          (4.75, 10.25), (4.75, 13.4), (5.45, 14.1), (10.5, 14.1)], 1.5),
        ([(76.45, 14.5), (83.0, 14.5), (87.4, 10.1), (87.4, 6.05)], 1.5),
    ],
    "+5V": [   # second: y 3 along the top, down at x 15 to the BUF802 / servo supply vias
        ([(74.45, 12.6), (73.3, 11.45), (73.3, 3.8), (72.5, 3.0), (16.8, 3.0), (15.0, 4.8), (15.0, 8.2), (13.9, 9.3)], 1.5),
        ([(74.95, 19.2), (73.3, 17.55), (73.3, 11.45)], 1.5),
    ],
    "+1V2": [  # power block LDO -> FPGA, all on L3 (no +1V2 copper on L4)
        ([(81.5, 21.4), (75.8, 21.4), (75.25, 21.95)], 1.5),
        ([(75.25, 21.95), (74.5, 21.2), (71.5, 21.2), (69.25, 18.95), (69.25, 16.4)], 1.5),
        ([(69.25, 16.4), (68.45, 15.6), (68.45, 14.5), (62.75, 8.8), (61.05, 8.8)], 1.0),
    ],
    "+2V5": [  # band y 23.2 (north member), then down x 6 to the trigger front chain
        ([(74.45, 16.2), (75.8, 17.55), (78.4, 17.55), (79.85, 19.0), (81.5, 19.0), (82.7, 20.2), (82.7, 22.4),
          (81.9, 23.2), (6.8, 23.2), (6.0, 24.0), (6.0, 28.5)], 1.5),
        ([(28.5, 23.2), (28.5, 9.4), (27.8, 8.7), (27.15, 8.7)], 1.0),     # hold amplifier
    ],
    "-2V5": [  # band y 25.0, down x 13 / x 5.2 west of the pstrobe column, along the bottom, east on y 47
        ([(83.75, 18.5), (84.6, 19.35), (84.6, 24.2), (83.8, 25.0), (13.8, 25.0), (13.0, 25.8), (13.0, 29.4),
          (10.4, 32.0), (6.0, 32.0), (5.2, 32.8), (5.2, 50.6), (6.0, 51.4), (24.0, 51.4), (28.4, 47.0),
          (91.65, 47.0), (92.45, 47.8), (92.45, 49.5)], 1.5),
    ],
    "VBUS": [  # band y 26.8 (south member) to the pstrobe choke column
        ([(89.1, 13.5), (88.0, 14.6), (88.0, 26.0), (87.2, 26.8), (23.6, 26.8), (22.78, 27.6), (22.78, 28.9),
          (20.8, 30.9), (20.8, 44.5), (22.78, 46.48), (22.78, 48.3)], 1.5),
    ],
}
# L6 (B.Cu) tracks: J501 pin 1 programmer supply (0.5 mm, TOPOLOGY.md section 8)
L6_TRACKS = {"VBUS": [([(22.78, 48.65), (28.6, 54.47), (32.47, 54.47)], 0.5)]}
HOPS = []                 # (rail, L6 polyline, width) with a 3-via array at each end; none used
BRANCH_W = 0.8
BRANCH_MAX = 6.0
BRANCH_CLR = 0.2          # branch track to foreign via / copper
FPGA_RECT = (56.0, 0.5, 74.0, 22.5)
PRIO_L3 = 3


def _org(board):
    b = board_box(board)
    return b[0], b[1]


def _old_arrays(board, names):
    """vias of rail nets that form a straight 3-via array at 0.8 mm pitch (earlier board_power output)."""
    by = {}
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" and t.GetNetname() in names:
            p = t.GetPosition()
            by.setdefault(t.GetNetname(), []).append((p.x / MM, p.y / MM, t))
    kill = set()
    for n, vs in by.items():
        for a in vs:
            for b in vs:
                if b is a:
                    continue
                dx, dy = b[0] - a[0], b[1] - a[1]
                if abs(math.hypot(dx, dy) - VIA_PITCH) > 0.02:
                    continue
                for c in vs:
                    if abs(c[0] - (b[0] + dx)) < 0.02 and abs(c[1] - (b[1] + dy)) < 0.02:
                        kill.update([id(a[2]), id(b[2]), id(c[2])])
                        kill_items[id(a[2])] = a[2]
                        kill_items[id(b[2])] = b[2]
                        kill_items[id(c[2])] = c[2]
    return [kill_items[k] for k in kill]


kill_items = {}


def remove_old(board, nets):
    """In3: delete every copper zone except +3V3; drop earlier board_power output (L3/L4 zones, 3-via arrays,
    0.8 / 1.5 mm L3 tracks and the L6 J501 feed of the rail nets)."""
    ox, oy = _org(board)
    names = set(nets.values()) - {BACKGROUND}
    kill_items.clear()
    for v in _old_arrays(board, names):
        board.Delete(v)
    old_t = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() in names and
             ((t.GetLayer() == L3 and round(t.GetWidth() / MM, 2) in (0.8, 1.0, 1.5)) or
              (t.GetLayer() == pcbnew.B_Cu and t.GetNetname() == "VBUS" and round(t.GetWidth() / MM, 2) == 0.5))]
    for t in old_t:
        board.Delete(t)
    kill = []
    for z in board.Zones():
        nm = str(z.GetZoneName())
        if z.GetIsRuleArea():
            if nm == "L4_window":
                kill.append(z)
            continue
        if nm.startswith("L3_") or nm.startswith("L4_"):
            kill.append(z)
            continue
        if z.GetLayerSet().Contains(LAYER):
            bb = z.GetBoundingBox()
            inside = (FPGA_RECT[0] <= bb.GetX() / MM - ox and bb.GetRight() / MM - ox <= FPGA_RECT[2] and
                      FPGA_RECT[1] <= bb.GetY() / MM - oy and bb.GetBottom() / MM - oy <= FPGA_RECT[3])
            if z.GetNetname() == BACKGROUND:
                kill.append(z)          # re-created whole-board below
                continue
            kill.append(z)
    for z in kill:
        board.Delete(z)


def new_zone(board, net, shape, prio, name, layer=LAYER):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNetCode(board.FindNet(net).GetNetCode())
    z.SetAssignedPriority(prio)
    z.SetLocalClearance(fmm(CLEAR))
    z.SetMinThickness(fmm(MINW))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS if prio == PRIO_BG else pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    z.SetZoneName(name)
    cp = pcbnew.SHAPE_POLY_SET(shape)
    cp.thisown = False
    z.SetOutline(cp)
    z.SetIsFilled(False)
    board.Add(z)
    return z


def _add_track(board, net, pts, w, layer):
    code = board.FindNet(net).GetNetCode()
    for p, q in zip(pts[:-1], pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(fmm(p[0]), fmm(p[1])))
        t.SetEnd(pcbnew.VECTOR2I(fmm(q[0]), fmm(q[1])))
        t.SetWidth(fmm(w))
        t.SetLayer(layer)
        t.SetNetCode(code)
        board.Add(t)


def corridor_shape(lines):
    parts = []
    for line, w in lines:
        for p, q in zip(line[:-1], line[1:]):
            parts.append(seg_rect(p, q, w))
        for p in line:
            parts.append(octagon(p[0], p[1], w / 2))
    return chamfer_close(union(parts), 0.2)


def _branches(board, nets, pts, corr_abs, report):
    """Route 0.8 mm L3 branches from each rail's corridor to its landing vias (0.1 mm grid, octilinear)."""
    global RES
    old = RES
    RES = 0.1
    out = {}
    try:
        G = Grid(board_box(board))
        hw = BRANCH_W / 2
        bb = board_box(board)
        base = (G.X < bb[0] + 0.5 + hw) | (G.X > bb[2] - 0.5 - hw) | (G.Y < bb[1] + 0.5 + hw) | (G.Y > bb[3] - 0.5 - hw)
        for z in board.Zones():
            if is_pour_keepout(z) and z.GetLayerSet().Contains(L3):
                o = z.Outline()
                for i in range(o.OutlineCount()):
                    pp = poly_points(o, i)
                    if len(pp) >= 3:
                        G.poly(base, pp, grow=CLEAR + hw)
        allv = [(t.GetPosition().x / MM, t.GetPosition().y / MM, t.GetWidth() / MM / 2, t.GetNetname())
                for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
        l3t = [((t.GetStart().x / MM, t.GetStart().y / MM), (t.GetEnd().x / MM, t.GetEnd().y / MM),
                t.GetWidth() / MM / 2, t.GetNetname()) for t in board.GetTracks()
               if t.GetClass() == "PCB_TRACK" and t.GetLayer() == L3]
        for (x, y, r) in other_holes(board, {}):
            G.disk(base, x, y, r + CLEAR + hw)
        cmask = {}
        for rail, lines in corr_abs.items():
            m = G.empty()
            for line, w in lines:
                for p, q in zip(line[:-1], line[1:]):
                    seg_mask(G, m, p, q, w / 2)
            cmask[rail] = m
        drawn = []
        for rail, lines in corr_abs.items():
            net = nets[rail]
            obst = base.copy()
            for (x, y, r, n) in allv:
                if n != net:
                    G.disk(obst, x, y, r + BRANCH_CLR + hw)
            for (p, q, r, n) in l3t:
                if n != net and "VTH" not in n:
                    seg_mask(G, obst, p, q, r + BRANCH_CLR + hw)
            for o, m in cmask.items():
                if o != rail:
                    obst |= dilate(m, 0.3 + hw)
            for (o, line) in drawn:
                if o != rail:
                    for p, q in zip(line[:-1], line[1:]):
                        seg_mask(G, obst, p, q, BRANCH_W / 2 + 0.3 + hw)
            free = ~obst
            src = set(np.flatnonzero((cmask[rail] & free).ravel()).tolist())
            out[rail] = []
            for (x, y, r) in pts[rail]:
                vm = G.empty()
                G.disk(vm, x, y, r)
                if (vm & cmask[rail]).any():
                    continue                     # the corridor covers the via
                tm = G.empty()
                G.disk(tm, x, y, 0.12)
                targets = {c: 0 for c in np.flatnonzero((tm & free).ravel()).tolist()}
                k, path = dijkstra(free, src, targets) if targets and src else (None, None)
                if k is None:
                    report.setdefault("unreached", []).append((rail, round(x - bb[0], 3), round(y - bb[1], 3), "blocked"))
                    continue
                poly = simplify(free, [divmod(c, G.nx) for c in path])
                line = [G.xy(i, j) for i, j in poly]
                L = sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(line[:-1], line[1:]))
                if L > BRANCH_MAX:
                    report.setdefault("unreached", []).append((rail, round(x - bb[0], 3), round(y - bb[1], 3),
                                                               f"{L:.1f} mm from corridor"))
                    continue
                line[-1] = (x, y)
                out[rail].append(line)
                drawn.append((rail, line))
    finally:
        RES = old
    return out


def apply(board, json_path=None, png_path=None):
    """L4 = one +3V3 plane; L3 = table-driven corridors + routed branches; VTAP tracks; L6 J501 feed.
    Call on a freshly merged board, then fill all zones, then verify()."""
    import json
    import os
    report = {}
    nets = rail_nets(board)
    ox, oy = _org(board)
    remove_old(board, nets)
    replicate_keepouts(board, landing_points(board, nets), report)
    box = board_box(board)
    bg = polyset([(box[0] + 0.3, box[1] + 0.3), (box[2] - 0.3, box[1] + 0.3), (box[2] - 0.3, box[3] - 0.3),
                  (box[0] + 0.3, box[3] - 0.3)])
    new_zone(board, nets[BACKGROUND], bg, PRIO_BG, "L4_+3V3")
    occ = []
    # VTAP strips: keep existing L3 tracks of those nets if present, else draw them
    have = {t.GetNetname() for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetLayer() == L3}
    if not all(n in have for n in STRIPS):
        strips, prob = strip_tracks(board, nets)
        report["strip_problems"] = prob
        for net, lines in strips.items():
            if net in have:
                continue
            for line in lines:
                _add_track(board, net, line, STRIP_W, L3)
                occ.append(dict(net=net, kind="track", layer="In2.Cu", width=STRIP_W,
                                pts=[(round(x - ox, 3), round(y - oy, 3)) for x, y in line]))
    else:
        report["strip_problems"] = "VTAP L3 tracks already on the board: kept"
    corr = {r: [([(x + ox, y + oy) for x, y in line], w) for line, w in lst]
            for r, lst in TRUNKS.items() if r in nets}
    pts = landing_points(board, nets)
    for rail, lines in corr.items():
        shp = corridor_shape(lines)
        for i in range(shp.OutlineCount()):
            sub = pcbnew.SHAPE_POLY_SET()
            sub.AddOutline(shp.Outline(i))
            new_zone(board, nets[rail], sub, PRIO_L3, f"L3_{rail}_{i}", L3)
            occ.append(dict(net=nets[rail], kind="zone", layer="In2.Cu",
                            pts=[(round(x - ox, 3), round(y - oy, 3)) for x, y in poly_points(sub, 0)]))
    br = _branches(board, nets, pts, corr, report)
    for rail, lines in br.items():
        for line in lines:
            _add_track(board, nets[rail], line, BRANCH_W, L3)
            occ.append(dict(net=nets[rail], kind="track", layer="In2.Cu", width=BRANCH_W,
                            pts=[(round(x - ox, 3), round(y - oy, 3)) for x, y in line]))
    for rail, lst in L6_TRACKS.items():
        for line, w in lst:
            _add_track(board, nets[rail], [(x + ox, y + oy) for x, y in line], w, pcbnew.B_Cu)
    report["l6_clearance"] = _check_l6(board)
    report["branches"] = {r: len(v) for r, v in br.items()}
    report["corr"] = corr
    report["l3"] = occ
    jp = json_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "board_power_L3.json")
    with open(jp, "w") as f:
        json.dump(dict(note="L3 (In2.Cu) copper added by board_power.py, board mm (origin board top-left). "
                       "Keep slow lines >= 0.3 mm away (1.5 mm channel beside corridors).", items=occ), f, indent=1)
    report["json"] = jp
    draw_plan(board, png_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "board_power_plan.png"),
              corr, br, pts)
    _LAST.clear()
    _LAST.update(report)
    return report


def _check_l6(board):
    """clearance of the L6 J501 feed against other B.Cu copper (pads / tracks / vias), mm."""
    ox, oy = _org(board)
    probs = []
    for rail, lst in L6_TRACKS.items():
        net = rail
        for line, w in lst:
            L = [(x + ox, y + oy) for x, y in line]
            for t in board.GetTracks():
                if t.GetNetname() == net:
                    continue
                if t.GetClass() == "PCB_VIA" or t.GetLayer() == pcbnew.B_Cu:
                    a, b = t.GetStart(), t.GetEnd()
                    for p, q in zip(L[:-1], L[1:]):
                        for (x, y) in ((a.x / MM, a.y / MM), (b.x / MM, b.y / MM)):
                            d = _pt_seg(x, y, p, q) - w / 2 - t.GetWidth() / MM / 2
                            if d < 0.15:
                                probs.append((round(x - ox, 2), round(y - oy, 2), t.GetNetname(), round(d, 2)))
            for f in board.GetFootprints():
                for pd in f.Pads():
                    if pd.GetNetname() == net or not pd.IsOnLayer(pcbnew.B_Cu):
                        continue
                    q0 = pd.GetPosition()
                    rr = max(pd.GetSize().x, pd.GetSize().y) / MM / 2
                    for p, q in zip(L[:-1], L[1:]):
                        d = _pt_seg(q0.x / MM, q0.y / MM, p, q) - w / 2 - rr
                        if d < 0.15:
                            probs.append((f.GetReference(), pd.GetNumber(), round(d, 2)))
    return probs


def draw_plan(board, path, corr, br, pts):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ox, oy = _org(board)
    col = {"+1V2": "orange", "+5V": "red", "-5V": "blue", "VBUS": "green", "-2V5": "purple", "+2V5": "brown",
           "/VTAP_P": "m", "/VTAP_N": "c"}
    fig, ax = plt.subplots(figsize=(20, 11.8))
    ax.add_patch(plt.Rectangle((0, 0), 100, 57, fc="none", ec="k", lw=1.5))
    for nm, (x0, y0, x1, y1) in dict(analog=(0, 1, 56, 22.5), fpga=(56, .5, 74, 22.5), power=(74, 0, 100, 22.5),
                                     phase=(0, 22.5, 99.5, 45), pstrobe=(9.5, 25, 26.5, 50),
                                     mcuif=(27, 45, 93.5, 57)).items():
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fc="none", ec="0.6", ls="--"))
        ax.text(x0 + .3, y0 + 1.0, nm, color="0.4", fontsize=9)
    for z in board.Zones():
        if is_pour_keepout(z) and z.GetLayerSet().Contains(L3):
            o = z.Outline()
            for i in range(o.OutlineCount()):
                pp = poly_points(o, i)
                if len(pp) >= 3:
                    ax.add_patch(plt.Polygon([(x - ox, y - oy) for x, y in pp], fc="0.75", ec="none"))
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetLayer() == L3 and t.GetNetname() in col:
            a, b = t.GetStart(), t.GetEnd()
            ax.plot([a.x / MM - ox, b.x / MM - ox], [a.y / MM - oy, b.y / MM - oy], color=col[t.GetNetname()], lw=1)
    for rail, lines in corr.items():
        for line, w in lines:
            ax.plot([x - ox for x, y in line], [y - oy for x, y in line], color=col.get(rail, "k"), lw=w * 7.5,
                    alpha=.45, solid_capstyle="butt", solid_joinstyle="miter")
        ax.plot([], [], color=col.get(rail, "k"), lw=6, alpha=.45, label=rail)
    for rail, lines in br.items():
        for line in lines:
            ax.plot([x - ox for x, y in line], [y - oy for x, y in line], color=col.get(rail, "k"), lw=3)
    for rail, l in pts.items():
        if rail == BACKGROUND:
            continue
        ax.scatter([x - ox for x, y, r in l], [y - oy for x, y, r in l], s=14, color=col.get(rail, "k"), zorder=5,
                   edgecolors="k", linewidths=.4)
    for rail, lst in L6_TRACKS.items():
        for line, w in lst:
            ax.plot([x for x, y in line], [y for x, y in line], color=col.get(rail, "k"), lw=2, ls=":",
                    label=f"{rail} L6 to J501.1")
    for u in _LAST.get("unreached", []) + []:
        pass
    ax.set_xlim(-1, 101)
    ax.set_ylim(58, -1)
    ax.set_aspect("equal")
    ax.legend(loc="lower right", fontsize=8, ncol=4)
    ax.set_title("board_power: L4 = +3V3 plane; L3 corridors (wide), branches (thin), landing vias (dots), "
                 "grey = L3 keep-outs")
    ax.set_xticks(range(0, 101, 5))
    ax.set_yticks(range(0, 58, 5))
    ax.grid(lw=.2)
    plt.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


_LAST = {}


def verify(board):
    """Per rail net (after fill): missing links (union-find over pads / tracks / vias / filled zones, as boardlib),
    corridors / branches / hops, landing points; +3V3: L4 polygons and landing points inside the L4 fill."""
    nets = rail_nets(board)
    allnets = dict(nets)
    for sn in STRIPS:
        if board.FindNet(sn) is not None:
            allnets[sn] = sn
    codes = {r: board.FindNet(n).GetNetCode() for r, n in allnets.items()}
    unc = _unconnected_per_net(board, codes)
    pts = landing_points(board, nets)
    res = {}
    for rail, net in allnets.items():
        d = dict(net=net, unconnected=unc.get(rail))
        if rail == BACKGROUND:
            fills = [z.GetFilledPolysList(LAYER) for z in board.Zones()
                     if not z.GetIsRuleArea() and z.GetNetname() == net and z.GetLayerSet().Contains(LAYER)]
            d["l4_polys"] = sum(f.OutlineCount() for f in fills)
            miss = [(round(x - 100, 2), round(y - 100, 2)) for (x, y, r) in pts[rail]
                    if not any(f.Contains(pcbnew.VECTOR2I(fmm(x), fmm(y))) for f in fills)]
            d["landing"] = len(pts[rail])
            d["missing"] = miss
        else:
            d["corridors"] = len(TRUNKS.get(rail, []))
            d["width"] = min((w for _, w in TRUNKS.get(rail, [])), default=STRIP_W if rail in STRIPS else None)
            d["branches"] = _LAST.get("branches", {}).get(rail, 0)
            d["landing"] = len(pts.get(rail, []))
        res[rail] = d
    res["_pcbnew_total"] = unc["_pcbnew_total"]
    res["_rails_total"] = sum((unc.get(r) or 0) for r in allnets)
    return res


def table(res):
    lines = ["rail      landing  corridors  width  branches  missing-links  notes"]
    for r, d in res.items():
        if r.startswith("_"):
            continue
        if r == BACKGROUND:
            lines.append(f"{r:9s} {d['landing']:7d}  L4 plane   -      -         {d['unconnected']}             "
                         f"L4 polygons {d['l4_polys']}, landing outside fill {d['missing'] or 0}")
        else:
            lines.append(f"{r:9s} {d['landing']:7d}  {d['corridors']:9d}  {str(d['width']):5s}  {d['branches']:8d}  "
                         f"{d['unconnected']}")
    lines.append(f"missing links over the rail nets: {res['_rails_total']};  pcbnew GetUnconnectedCount() board-wide: "
                 f"{res['_pcbnew_total']}")
    return "\n".join(lines)


def _unconnected_per_net(board, codes):
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    import boardlib as bl
    board.BuildConnectivity()
    total = board.GetConnectivity().GetUnconnectedCount(True)
    miss = {}
    for line in bl.unrouted_nets(board):
        name, n = line.rsplit(" (", 1)
        miss[name] = int(n.rstrip(")"))
    out = {r: miss.get(board.FindNet(code).GetNetname(), 0) for r, code in codes.items()}
    out["_pcbnew_total"] = total
    return out


def main(argv):
    """python3 board_power.py in.kicad_pcb out.kicad_pcb [render_prefix] [--drop-l3-vth]"""
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    board = pcbnew.LoadBoard(args[0])
    if "--drop-l3-vth" in argv:          # test only: VTH moves to L1 (integrator); treat its L3 copper as free
        for t in [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetLayer() == L3
                  and "VTH" in t.GetNetname()]:
            board.Delete(t)
    rep = apply(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    res = verify(board)
    board.Save(args[1])
    print("VTAP:", rep.get("strip_problems"))
    print("L6 J501 feed clearance problems:", rep.get("l6_clearance"))
    print("landing vias not branched:", rep.get("unreached"))
    print(table(res))
    if len(args) > 2:
        sys.path.insert(0, __file__.rsplit("/", 1)[0])
        import boardlib as bl
        bl.render(args[1], args[2] + "_In3.png", layers=("In3.Cu", "Edge.Cuts"))
        bl.render(args[1], args[2] + "_In2.png", layers=("In2.Cu", "Edge.Cuts"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
