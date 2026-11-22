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


class Planner:
    def __init__(self, board, strips):
        self.nets = rail_nets(board)
        self.pts = landing_points(board, self.nets)
        self.box = box = board_box(board)
        self.G = G = Grid(box)
        edge = (G.X < box[0] + EDGE) | (G.X > box[2] - EDGE) | (G.Y < box[1] + EDGE) | (G.Y > box[3] - EDGE)
        holes = other_holes(board, self.nets)
        # ---- L4
        self.keep = G.empty()
        for ko in l4_keepouts(board):
            G.poly(self.keep, ko)
        base = edge | dilate(self.keep, CLEAR)
        for (x, y, r) in holes:
            G.disk(base, x, y, r + CLEAR)
        self.base = base
        # ---- L3: keep-outs on In2, foreign In2 tracks, VTAP tracks (1 mm), holes, edge
        k3 = G.empty()
        for z in board.Zones():
            if is_pour_keepout(z) and z.GetLayerSet().Contains(L3):
                o = z.Outline()
                for i in range(o.OutlineCount()):
                    pp = poly_points(o, i)
                    if len(pp) >= 3:
                        G.poly(k3, pp)
        b3 = edge | dilate(k3, CLEAR)
        for (x, y, r) in holes:
            G.disk(b3, x, y, r + CLEAR)
        self.l3_tracks = []
        for t in board.GetTracks():
            if t.GetClass() == "PCB_TRACK" and t.GetLayer() == L3:
                a, b = t.GetStart(), t.GetEnd()
                self.l3_tracks.append(((a.x / MM, a.y / MM), (b.x / MM, b.y / MM), t.GetWidth() / MM, t.GetNetname()))
        for line_set in strips.values():
            for line in line_set:
                for p, q in zip(line[:-1], line[1:]):
                    seg_mask(G, b3, p, q, STRIP_W / 2 + 1.0)
        self.base3 = b3
        # ---- where a 3-via array may sit: away from F.Cu / B.Cu / In2 copper and every through item
        vb = edge.copy()
        rv = VIA_D / 2 + 0.15
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                p = t.GetPosition()
                G.disk(vb, p.x / MM, p.y / MM, t.GetWidth() / MM / 2 + rv)
            elif t.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu, L3):
                a, b = t.GetStart(), t.GetEnd()
                seg_mask(G, vb, (a.x / MM, a.y / MM), (b.x / MM, b.y / MM), t.GetWidth() / MM / 2 + rv)
        for f in board.GetFootprints():
            for pd in f.Pads():
                bb = pd.GetBoundingBox()
                x0, y0, x1, y1 = bb.GetX() / MM - rv, bb.GetY() / MM - rv, bb.GetRight() / MM + rv, bb.GetBottom() / MM + rv
                i0, j0 = G.ij(x0, y0)
                i1, j1 = G.ij(x1, y1)
                vb[max(i0, 0):max(i1 + 1, 0), max(j0, 0):max(j1 + 1, 0)] = True
        for z in board.Zones():                       # F / B copper zones (pads' pours) and keep-outs
            ls = z.GetLayerSet()
            if z.GetIsRuleArea() and z.GetDoNotAllowVias():     # copper pours flow around a new via
                o = z.Outline()
                for i in range(o.OutlineCount()):
                    pp = poly_points(o, i)
                    if len(pp) >= 3:
                        G.poly(vb, pp, grow=rv)
        for line_set in strips.values():
            for line in line_set:
                for p, q in zip(line[:-1], line[1:]):
                    seg_mask(G, vb, p, q, STRIP_W / 2 + rv + 0.2)
        vb |= self.keep | k3
        # the array (centre +- 0.8 mm in any direction) fits where a disk of 0.8 mm is free of forbidden centres
        self.hop_ok = ~dilate(vb, VIA_PITCH + RES * 0.5)
        self.groups = {r: cluster(self.pts[r]) for r in ISLANDS if self.pts.get(r)}
        self.foreign = {}
        self.resv = {}
        for rail in self.groups:
            m = G.empty()
            for other, lst in self.pts.items():
                if other == rail:
                    continue
                ring = 0.25 if other == BACKGROUND else LAND
                for (x, y, r) in lst:
                    G.disk(m, x, y, r + ring + CLEAR)
            self.foreign[rail] = m
            lm = G.empty()
            for p, q in _mst(self.groups[rail]):
                a, b = G.ij(*p), G.ij(*q)
                for i, j in line_cells(a[0], a[1], b[0], b[1]):
                    if 0 <= i < G.ny and 0 <= j < G.nx:
                        lm[i, j] = True
            self.resv[rail] = dilate(lm, RESERVE_R)
        self.free3_static = ~dilate(self.base3, FEED_W / 2)

    def start_group(self, rail):
        groups = self.groups[rail]
        bx0, by0 = self.box[0], self.box[1]
        for k, g in enumerate(groups):
            if any(POWER_BLOCK[0] <= p[0] - bx0 <= POWER_BLOCK[2] and POWER_BLOCK[1] <= p[1] - by0
                   <= POWER_BLOCK[3] for p in g):
                return k
        return 0

    def dijkstra2(self, free4, free3, hop, sources, targets, cost4, l3f):
        """two-layer search: state = layer * N + cell. Sources / targets on L4 only."""
        ny, nx = free4.shape
        N = nx * ny
        f4 = free4.ravel().tolist()
        f3 = free3.ravel().tolist()
        hp = hop.ravel().tolist()
        c4 = cost4.ravel().tolist()
        dist, prev, h = {}, {}, []
        for s0 in sources:
            if f4[s0]:
                dist[s0] = 0.0
                prev[s0] = -1
                heapq.heappush(h, (0.0, s0))
        while h:
            d, u = heapq.heappop(h)
            if d > dist.get(u, 1e18):
                continue
            if u < N and u in targets:
                path = []
                while u != -1:
                    path.append(u)
                    u = prev[u]
                return targets[path[0]], path[::-1]
            lay, c = divmod(u, N)
            i, j = divmod(c, nx)
            if hp[c]:
                if lay == 0 and f3[c]:
                    v, nd = N + c, d + HOP_COST
                elif lay == 1 and f4[c]:
                    v, nd = c, d + HOP_COST
                else:
                    v = None
                if v is not None and nd < dist.get(v, 1e18):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(h, (nd, v))
            fl = f4 if lay == 0 else f3
            for di, dj, cc in DIRS:
                ii, jj = i + di, j + dj
                if 0 <= ii < ny and 0 <= jj < nx:
                    w = ii * nx + jj
                    if not fl[w]:
                        continue
                    nd = d + cc * ((1.0 + c4[w]) if lay == 0 else l3f)
                    v = lay * N + w
                    if nd < dist.get(v, 1e18):
                        dist[v] = nd
                        prev[v] = u
                        heapq.heappush(h, (nd, v))
        return None, None

    def route_rail(self, rail, placed, placed3, later):
        G = self.G
        nx, N = G.nx, G.nx * G.ny
        obst = self.base | dilate(placed, CLEAR + GAP) | self.foreign[rail]
        cost = np.zeros((G.ny, G.nx))
        for o in later:
            cost += RESERVE_COST * self.resv[o]
        free3 = self.free3_static & ~dilate(placed3, CLEAR + GAP + FEED_W / 2)
        l3f = L3_COST.get(rail, L3_COST_DEFAULT)
        frees = {}
        groups = self.groups[rail]
        start = self.start_group(rail)
        tree = set()
        disks = {}

        def gcells(k):
            if k not in disks:
                m = G.empty()
                for (x, y, r) in groups[k]:
                    G.disk(m, x, y, 0.6)
                disks[k] = np.flatnonzero(m.ravel()).tolist()
            return disks[k]
        tree.update(gcells(start))
        todo = set(range(len(groups))) - {start}
        segs, feeds, hops, unreached, length = [], [], [], [], 0.0
        m3 = G.empty()
        while todo:
            hit = None
            for w in WIDTHS:
                if w not in frees:
                    frees[w] = ~dilate(obst, w / 2)
                free = frees[w]
                ff = free.ravel()
                targets = {c: k for k in todo for c in gcells(k) if ff[c]}
                src = {c for c in tree if ff[c]}
                if not targets or not src:
                    continue
                hop = self.hop_ok & frees.setdefault(2.0, ~dilate(obst, 1.0)) & free3
                k, path = self.dijkstra2(free, free3, hop, src, targets, cost, l3f)
                if k is not None:
                    hit = (k, path, w, free)
                    break
            if hit is None:
                # stuck (e.g. the start is boxed in): grow a second tree from the next group; reported as
                # missing links by verify() if the trees never meet
                k0 = min(todo)
                unreached.append(groups[k0])
                tree.update(gcells(k0))
                todo.discard(k0)
                continue
            k, path, w, free = hit
            # split into layer runs
            runs, cur, lay = [], [], 0
            for u in path:
                l_, c = divmod(u, N)
                if l_ != lay and cur:
                    runs.append((lay, cur))
                    hops.append(G.xy(*divmod(c, nx)))
                    cur = []
                lay = l_
                cur.append(divmod(c, nx))
            runs.append((lay, cur))
            for lay, cells in runs:
                fm = free if lay == 0 else free3
                poly = simplify(fm, cells) if len(cells) > 1 else cells
                line = [G.xy(i, j) for i, j in poly]
                if lay == 0:
                    segs.append((line, w))
                    for a, b in zip(poly[:-1], poly[1:]):
                        for i, j in line_cells(a[0], a[1], b[0], b[1]):
                            tree.add(i * nx + j)
                else:
                    feeds.append((line, FEED_W))
                    for p_, q_ in zip(line[:-1], line[1:]):
                        seg_mask(G, m3, p_, q_, FEED_W / 2)
                    if len(line) == 1:
                        G.disk(m3, line[0][0], line[0][1], FEED_W / 2)
                length += sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(line[:-1], line[1:]))
            tree.update(gcells(k))
            todo.discard(k)
        for (x, y) in hops:
            G.disk(m3, x, y, 1.3)
        parts = []
        for line, w in segs:
            for p, q in zip(line[:-1], line[1:]):
                parts.append(seg_rect(p, q, w))
            for p in line:
                parts.append(octagon(p[0], p[1], w / 2))
        for (x, y, r) in self.pts[rail]:
            parts.append(octagon(x, y, r + LAND))
        for (x, y) in hops:
            parts.append(octagon(x, y, 1.3))
        shape = chamfer_close(union(parts))
        box = self.box
        clip = polyset([(box[0] + 0.3, box[1] + 0.3), (box[2] - 0.3, box[1] + 0.3), (box[2] - 0.3, box[3] - 0.3),
                        (box[0] + 0.3, box[3] - 0.3)])
        shape.BooleanIntersection(clip, pcbnew.SHAPE_POLY_SET.PM_STRICTLY_SIMPLE)
        m = G.empty()
        for i in range(shape.OutlineCount()):
            G.poly(m, poly_points(shape, i))
        # L3 feeder shapes (one zone per connected feeder)
        fparts = []
        for line, w in feeds:
            for p, q in zip(line[:-1], line[1:]):
                fparts.append(seg_rect(p, q, w))
            for p in line:
                fparts.append(octagon(p[0], p[1], w / 2))
        for (x, y) in hops:
            fparts.append(octagon(x, y, 1.3))
        fshape = chamfer_close(union(fparts)) if fparts else None
        # via arrays: 3 vias at each hop, along the adjoining L3 run
        arrays = []
        for (x, y) in hops:
            d = None
            for line, _ in feeds:
                for p in (line[0], line[-1]):
                    if abs(p[0] - x) < 1e-6 and abs(p[1] - y) < 1e-6 and len(line) > 1:
                        q = line[1] if p is line[0] else line[-2]
                        L = math.hypot(q[0] - p[0], q[1] - p[1])
                        d = ((q[0] - p[0]) / L, (q[1] - p[1]) / L)
            d = d or (1.0, 0.0)
            arrays.append([(x + k * VIA_PITCH * d[0], y + k * VIA_PITCH * d[1]) for k in (-1, 0, 1)])
        wmin = min((w for _, w in segs), default=None)
        return dict(shape=shape, segs=segs, feeds=feeds, fshape=fshape, arrays=arrays, unreached=unreached,
                    wmin=wmin, length=length, raster=m, raster3=m3)

    def bg_isolated(self, placed):
        G = self.G
        free = ~(dilate(placed, CLEAR + 0.1) | self.keep)
        free &= (G.X > self.box[0] + 0.4) & (G.X < self.box[2] - 0.4) & (G.Y > self.box[1] + 0.4) & \
            (G.Y < self.box[3] - 0.4)
        lab, n = _components(free)
        if n == 0:
            return list(self.pts.get(BACKGROUND, []))
        sizes = np.bincount(lab.ravel())
        sizes[0] = 0
        main = int(sizes.argmax())
        bad = []
        for (x, y, r) in self.pts.get(BACKGROUND, []):
            m = G.empty()
            G.disk(m, x, y, r + 0.3)
            if not (lab[m] == main).any():
                bad.append((x, y, r))
        return bad

    def run(self, order):
        G = self.G
        placed, placed3 = G.empty(), G.empty()
        out = {}
        for n, rail in enumerate(order):
            d = self.route_rail(rail, placed, placed3, order[n + 1:])
            placed |= d["raster"]
            placed3 |= d["raster3"]
            out[rail] = d
        bad = self.bg_isolated(placed)
        unr = sum(len(g) for d in out.values() for g in d["unreached"])
        nfeed = sum(len(d["arrays"]) for d in out.values())
        narrow = sum(1 for d in out.values() for _, w in d["segs"] if w < 1.5)
        score = (unr + len(bad), nfeed + narrow, sum(d["length"] for d in out.values()))
        return score, out, bad


def plan(board, report, strips, orders=None):
    P = Planner(board, strips)
    rails = [r for r in ISLANDS if r in P.groups]
    import random
    rnd = random.Random(1)
    cands = [rails]
    for _ in range((orders or ORDERS) - 1):
        o = rails[:]
        rnd.shuffle(o)
        cands.append(o)
    best = None
    for order in cands:
        score, out, bad = P.run(order)
        report.setdefault("orders", []).append((score[:2], order))
        if best is None or score < best[0]:
            best = (score, out, bad, order)
        if score[0] == 0 and score[1] == 0:
            break
    score, islands, bad, order = best
    report["order"] = order
    report["score"] = score
    report["bg_isolated_raster"] = bad
    return P.nets, P.pts, islands, P.box


def remove_old(board, nets):
    names = set(nets.values()) | set(STRIPS)
    kill = []
    for z in board.Zones():
        nm = str(z.GetZoneName())
        if z.GetIsRuleArea():
            if nm == "L4_window":
                kill.append(z)
            continue
        if (z.GetLayerSet().Contains(LAYER) and z.GetNetname() in names) or nm.startswith("L3_feed"):
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
    # background: drop isolated +3V3 scraps; islands / feeders: keep every piece (a piece cut off by foreign
    # holes is still reported by verify() as a missing link instead of silently vanishing)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS if prio == PRIO_BG else pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    z.SetZoneName(name)
    cp = pcbnew.SHAPE_POLY_SET(shape)
    cp.thisown = False                     # the zone takes ownership
    z.SetOutline(cp)
    z.SetIsFilled(False)
    board.Add(z)
    return z


_LAST = {}


def apply(board, orders=None, json_path=None):
    """Build L4 (+ L3 feeders, VTAP tracks) on a freshly merged board. Returns a report. Fill zones afterwards."""
    import json
    import os
    report = {}
    nets = rail_nets(board)
    remove_old(board, nets)
    replicate_keepouts(board, landing_points(board, nets), report)
    strips, sprob = strip_tracks(board, nets)
    report["strip_clearance_problems"] = sprob
    occ = []
    for net, lines in strips.items():
        code = board.FindNet(net).GetNetCode()
        for line in lines:
            for p, q in zip(line[:-1], line[1:]):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(fmm(p[0]), fmm(p[1])))
                t.SetEnd(pcbnew.VECTOR2I(fmm(q[0]), fmm(q[1])))
                t.SetWidth(fmm(STRIP_W))
                t.SetLayer(L3)
                t.SetNetCode(code)
                board.Add(t)
            occ.append(dict(net=net, kind="track", layer="In2.Cu", width=STRIP_W,
                            pts=[(round(x, 4), round(y, 4)) for x, y in line]))
    nets, pts, islands, box = plan(board, report, strips, orders)
    bg = polyset([(box[0] + 0.3, box[1] + 0.3), (box[2] - 0.3, box[1] + 0.3), (box[2] - 0.3, box[3] - 0.3),
                  (box[0] + 0.3, box[3] - 0.3)])
    new_zone(board, nets[BACKGROUND], bg, PRIO_BG, "L4_+3V3")
    for rail, d in islands.items():
        new_zone(board, nets[rail], d["shape"], PRIO_ISLAND, "L4_" + rail.lstrip("/"))
        code = board.FindNet(nets[rail]).GetNetCode()
        if d["fshape"] is not None:
            for i in range(d["fshape"].OutlineCount()):
                sub = pcbnew.SHAPE_POLY_SET()
                sub.AddOutline(d["fshape"].Outline(i))
                new_zone(board, nets[rail], sub, PRIO_FEED, f"L3_feed_{rail.lstrip('/')}_{i}", L3)
                occ.append(dict(net=nets[rail], kind="zone", layer="In2.Cu",
                                pts=[(round(x, 4), round(y, 4)) for x, y in poly_points(sub, 0)]))
        for arr in d["arrays"]:
            for (x, y) in arr:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(fmm(x), fmm(y)))
                v.SetWidth(fmm(VIA_D))
                v.SetDrill(fmm(VIA_DRILL))
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetNetCode(code)
                board.Add(v)
            occ.append(dict(net=nets[rail], kind="via_array", layer="all", dia=VIA_D,
                            pts=[(round(x, 4), round(y, 4)) for x, y in arr]))
    report["islands"] = {r: dict(wmin=d["wmin"], unreached=d["unreached"], segs=d["segs"], feeds=d["feeds"],
                                 arrays=d["arrays"]) for r, d in islands.items()}
    report["strips"] = strips
    report["l3"] = occ
    jp = json_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "board_power_L3.json")
    with open(jp, "w") as f:
        json.dump(dict(note="L3 (In2.Cu) copper occupied by board_power.py: board coordinates are pcbnew mm "
                       "(board origin at pcbnew (100, 100)); keep slow lines >= 0.3 mm away", items=occ), f, indent=1)
    report["json"] = jp
    _LAST.clear()
    _LAST.update(report)
    return report


# --------------------------------------------------------------------------------------------- verify
def _outline_segments(fill, i):
    ol = fill.Outline(i)
    P = np.array([(ol.CPoint(k).x / MM, ol.CPoint(k).y / MM) for k in range(ol.PointCount())])
    return P, np.roll(P, -1, axis=0)


def _dist_to_segments(p, A, B):
    AB = B - A
    L2 = (AB ** 2).sum(1)
    L2[L2 == 0] = 1e-12
    t = np.clip(((p - A) * AB).sum(1) / L2, 0, 1)
    C = A + AB * t[:, None]
    return np.sqrt(((C - p) ** 2).sum(1)).min()


def _unconnected_per_net(board, codes):
    """pcbnew 7 does not wrap RN_NET, so per net: boardlib's union-find over pads / tracks / vias / filled zone
    islands (missing links per rail net); plus pcbnew's own board-wide GetUnconnectedCount()."""
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    import boardlib as bl
    board.BuildConnectivity()
    total = board.GetConnectivity().GetUnconnectedCount(True)
    miss = {}
    for line in bl.unrouted_nets(board):
        name, n = line.rsplit(" (", 1)
        miss[name] = int(n.rstrip(")"))
    out = {}
    for r, code in codes.items():
        out[r] = miss.get(board.FindNet(code).GetNetname(), 0)
    out["_pcbnew_total"] = total
    return out


def verify(board):
    """Per rail: L4 filled polygons, landing points inside the L4 fill (missing listed), L3 feeders and via arrays,
    planned min trunk / feeder width, missing links per net (union-find over pads / tracks / vias / filled zones
    after fill); plus the board-wide pcbnew GetUnconnectedCount() and the sum over the rail nets."""
    nets = rail_nets(board)
    pts = landing_points(board, nets)
    res = {}
    zones, z3 = {}, {}
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        if z.GetLayerSet().Contains(LAYER):
            zones.setdefault(z.GetNetname(), []).append(z)
        if z.GetLayerSet().Contains(L3) and str(z.GetZoneName()).startswith("L3_feed"):
            z3.setdefault(z.GetNetname(), []).append(z)
    allnets = dict(nets)
    for sn in STRIPS:
        if board.FindNet(sn) is not None:
            allnets[sn] = sn
    codes = {r: board.FindNet(n).GetNetCode() for r, n in allnets.items()}
    unc = _unconnected_per_net(board, codes)
    isl = _LAST.get("islands", {})
    for rail, net in allnets.items():
        if rail in STRIPS:
            res[rail] = dict(net=net, polygons=0, landing=None, inside=None, missing=[], feeders=0, arrays=0,
                             wmin=STRIP_W, fw=None, unconnected=unc.get(rail), kind="L3 track")
            continue
        fills = [z.GetFilledPolysList(LAYER) for z in zones.get(net, [])]
        npoly = sum(f.OutlineCount() for f in fills)
        inside, missing = 0, []
        for (x, y, r) in pts[rail]:
            v = pcbnew.VECTOR2I(fmm(x), fmm(y))
            if any(f.Contains(v) for f in fills):
                inside += 1
            else:
                missing.append((round(x - 100, 3), round(y - 100, 3)))
        f3 = sum(z.GetFilledPolysList(L3).OutlineCount() for z in z3.get(net, []))
        d = isl.get(rail, {})
        res[rail] = dict(net=net, polygons=npoly, landing=len(pts[rail]), inside=inside, missing=missing,
                         feeders=f3, arrays=len(d.get("arrays", [])), wmin=d.get("wmin"),
                         fw=FEED_W if d.get("feeds") else None, unconnected=unc.get(rail),
                         kind="background" if rail == BACKGROUND else "island")
    res["_pcbnew_total"] = unc["_pcbnew_total"]
    res["_rails_total"] = sum((unc.get(r) or 0) for r in allnets)
    return res


def table(res):
    lines = ["rail      L4-polys  landing  in-L4-fill  L3-feeders  via-arrays(3)  min-trunk  feeder-w  missing-links"]
    for r, d in res.items():
        if r.startswith("_"):
            continue
        lines.append(f"{r:9s} {d['polygons']:8d}  {str(d['landing']):7s}  {str(d['inside']):10s}  {d['feeders']:10d}  "
                     f"{d['arrays']:13d}  {str(d['wmin']):9s}  {str(d['fw']):8s}  {d['unconnected']}"
                     + (f"   NOT IN FILL {d['missing']}" if d["missing"] else ""))
    lines.append(f"missing links summed over rail nets: {res.get('_rails_total')};  "
                 f"pcbnew GetUnconnectedCount() board-wide: {res.get('_pcbnew_total')}")
    return "\n".join(lines)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    board = pcbnew.LoadBoard(argv[1])
    rep = apply(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    res = verify(board)
    board.Save(argv[2])
    print("routing order", rep["order"], "score", rep["score"][:2], "bg isolated (raster)", rep["bg_isolated_raster"])
    print("VTAP L3 vias not reached:", rep.get("strip_clearance_problems"))
    print("keep-outs replicated on In3.Cu:", rep.get("keepouts_added"), " skipped:", rep.get("keepout_skipped", []))
    for r, d in rep["islands"].items():
        if d["unreached"]:
            print("UNREACHED", r, d["unreached"])
    print(table(res))
    if len(argv) > 3:
        sys.path.insert(0, __file__.rsplit("/", 1)[0])
        import boardlib as bl
        bl.render(argv[2], argv[3], layers=("In3.Cu", "Edge.Cuts"))
        bl.render(argv[2], argv[3].replace(".png", "_L3.png"), layers=("In2.Cu", "Edge.Cuts"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
