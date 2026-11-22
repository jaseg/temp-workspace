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
ISLANDS = ["/VTAP_N", "/VTAP_P", "+1V2", "+5V", "-5V", "VBUS", "-2V5", "+2V5"]
RAILS = [BACKGROUND] + ISLANDS
FEED = {"/VTAP_P": "+2V5", "/VTAP_N": "-2V5"}   # strips start at the via nearest to this rail (0R link)


def fmm(v):
    return pcbnew.FromMM(v)


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


def dijkstra(free, sources, targets):
    """free: bool[ny, nx]; sources: set of flat idx; targets: dict flat idx -> key. Returns (key, path idx list)."""
    ny, nx = free.shape
    fl = free.ravel().tolist()
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
                nd = d + c
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


def plan(board, report):
    nets = rail_nets(board)
    pts = landing_points(board, nets)
    holes = other_holes(board, nets)
    box = board_box(board)
    G = Grid(box)
    bx0, by0 = box[0], box[1]

    base = G.empty()                                    # obstacles for every island
    base[:, :] = False
    inner = G.empty()
    inner |= (G.X < box[0] + EDGE) | (G.X > box[2] - EDGE) | (G.Y < box[1] + EDGE) | (G.Y > box[3] - EDGE)
    base |= inner
    for ko in l4_keepouts(board):
        G.poly(base, ko, grow=CLEAR)
    for (x, y, r) in holes:
        G.disk(base, x, y, r + CLEAR)

    placed = G.empty()                                  # copper of islands already planned
    islands = {}
    for rail in ISLANDS:
        if rail not in nets or not pts.get(rail):
            continue
        own = pts[rail]
        obst = base | dilate(placed, CLEAR + GAP)
        for other, lst in pts.items():
            if other == rail:
                continue
            ring = 0.25 if other == BACKGROUND else LAND
            for (x, y, r) in lst:
                G.disk(obst, x, y, r + ring + CLEAR)
        # free masks per width (path centre may be where a disk of w/2 does not touch an obstacle)
        frees = {w: ~dilate(obst, w / 2) for w in WIDTHS}
        groups = cluster(own)
        # start group: inside the power block, or the strip feed
        if rail in FEED and pts.get(FEED[rail]):
            fx = [(x, y) for (x, y, _) in pts[FEED[rail]]]
            start = min(range(len(groups)), key=lambda k: min(math.hypot(p[0] - q[0], p[1] - q[1])
                                                               for p in groups[k] for q in fx))
        else:
            def inpb(g):
                return any(POWER_BLOCK[0] <= p[0] - bx0 <= POWER_BLOCK[2] and POWER_BLOCK[1] <= p[1] - by0
                           <= POWER_BLOCK[3] for p in g)
            cand = [k for k, g in enumerate(groups) if inpb(g)]
            start = cand[0] if cand else 0
        tree_cells = set()
        segs = []                                       # (polyline pts mm, w)
        lands = []
        nx = G.nx

        def add_group_cells(g):
            for (x, y, r) in g:
                m = G.empty()
                G.disk(m, x, y, 0.6)
                tree_cells.update(np.flatnonzero(m.ravel()).tolist())

        add_group_cells(groups[start])
        todo = set(range(len(groups))) - {start}
        unreached = []
        widths_used = []
        while todo:
            done_any = False
            for w in WIDTHS:
                free = frees[w]
                targets = {}
                for k in todo:
                    for (x, y, r) in groups[k]:
                        m = G.empty()
                        G.disk(m, x, y, 0.6)
                        for c in np.flatnonzero((m & free).ravel()).tolist():
                            targets[c] = k
                src = {c for c in tree_cells if free.ravel()[c]}
                if not targets or not src:
                    continue
                k, path = dijkstra(free, src, targets)
                if k is None:
                    continue
                cells = [divmod(c, nx) for c in path]
                poly = simplify(free, cells)
                segs.append(([G.xy(i, j) for i, j in poly], w))
                widths_used.append(w)
                # tree grows by the path and the reached group
                for a, b in zip(poly[:-1], poly[1:]):
                    for i, j in line_cells(a[0], a[1], b[0], b[1]):
                        tree_cells.add(i * nx + j)
                add_group_cells(groups[k])
                todo.discard(k)
                done_any = True
                break
            if not done_any:
                unreached += [groups[k] for k in todo]
                break
        # polygon
        parts = []
        for line, w in segs:
            for p, q in zip(line[:-1], line[1:]):
                parts.append(seg_rect(p, q, w))
            for p in line:
                parts.append(octagon(p[0], p[1], w / 2))
        for (x, y, r) in own:
            parts.append(octagon(x, y, r + LAND))
        shape = chamfer_close(union(parts))
        clip = polyset([(box[0] + 0.3, box[1] + 0.3), (box[2] - 0.3, box[1] + 0.3), (box[2] - 0.3, box[3] - 0.3),
                        (box[0] + 0.3, box[3] - 0.3)])
        shape.BooleanIntersection(clip, pcbnew.SHAPE_POLY_SET.PM_STRICTLY_SIMPLE)
        islands[rail] = dict(shape=shape, segs=segs, unreached=unreached,
                             wmin=min(widths_used) if widths_used else None)
        # raster of this island for the next rails
        m = G.empty()
        for i in range(shape.OutlineCount()):
            G.poly(m, poly_points(shape, i))
        placed |= m
    report["grid"] = (G.nx, G.ny)
    return nets, pts, islands, box


def remove_old(board, nets):
    names = set(nets.values())
    kill = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            if str(z.GetZoneName()) == "L4_window":
                kill.append(z)
            continue
        if z.GetLayerSet().Contains(LAYER) and z.GetNetname() in names:
            kill.append(z)
    for z in kill:
        board.Delete(z)


def new_zone(board, net, shape, prio, name):
    z = pcbnew.ZONE(board)
    z.SetLayer(LAYER)
    z.SetNetCode(board.FindNet(net).GetNetCode())
    z.SetAssignedPriority(prio)
    z.SetLocalClearance(fmm(CLEAR))
    z.SetMinThickness(fmm(MINW))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetZoneName(name)
    cp = pcbnew.SHAPE_POLY_SET(shape)
    cp.thisown = False                     # the zone takes ownership
    z.SetOutline(cp)
    z.SetIsFilled(False)
    board.Add(z)
    return z


_LAST = {}


def apply(board):
    """Build the L4 power layer on a merged board. Returns a report dict. Call ZONE_FILLER afterwards."""
    report = {}
    nets = rail_nets(board)
    remove_old(board, nets)
    replicate_keepouts(board, landing_points(board, nets), report)
    nets, pts, islands, box = plan(board, report)
    bg = polyset([(box[0] + 0.3, box[1] + 0.3), (box[2] - 0.3, box[1] + 0.3), (box[2] - 0.3, box[3] - 0.3),
                  (box[0] + 0.3, box[3] - 0.3)])
    new_zone(board, nets[BACKGROUND], bg, PRIO_BG, "L4_+3V3")
    for rail, d in islands.items():
        new_zone(board, nets[rail], d["shape"], PRIO_ISLAND, "L4_" + rail.lstrip("/"))
    report["islands"] = {r: dict(wmin=d["wmin"], unreached=d["unreached"], segs=d["segs"])
                         for r, d in islands.items()}
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
    conn = board.GetConnectivity()
    conn.RecalculateRatsnest()
    out = {}
    for name, code in codes.items():
        try:
            rn = conn.GetRatsnestForNet(code)
            out[name] = len(rn.GetUnconnected()) if hasattr(rn, "GetUnconnected") else None
        except Exception:
            out[name] = None
    if any(v is None for v in out.values()):
        # fallback: count via pcbnew's own union of connected items per net
        for name, code in codes.items():
            items = list(conn.GetNetItems(code, [pcbnew.PCB_PAD_T, pcbnew.PCB_VIA_T, pcbnew.PCB_TRACE_T,
                                                 pcbnew.PCB_ZONE_T]))
            seen = set()
            comps = 0
            for it in items:
                if it.m_Uuid.AsString() in seen if hasattr(it, "m_Uuid") else False:
                    continue
                comps += 1
                for c in conn.GetConnectedItems(it, [pcbnew.PCB_PAD_T, pcbnew.PCB_VIA_T, pcbnew.PCB_TRACE_T,
                                                     pcbnew.PCB_ZONE_T]):
                    seen.add(c.m_Uuid.AsString())
                seen.add(it.m_Uuid.AsString())
            out[name] = max(comps - 1, 0)
    return out


def verify(board):
    nets = rail_nets(board)
    pts = landing_points(board, nets)
    res = {}
    zones = {}
    for z in board.Zones():
        if not z.GetIsRuleArea() and z.GetLayerSet().Contains(LAYER):
            zones.setdefault(z.GetNetname(), []).append(z)
    codes = {r: board.FindNet(n).GetNetCode() for r, n in nets.items()}
    unc = _unconnected_per_net(board, codes)
    segs = _LAST.get("islands", {})
    for rail, net in nets.items():
        fills = [z.GetFilledPolysList(LAYER) for z in zones.get(net, [])]
        npoly = sum(f.OutlineCount() for f in fills)
        inside, missing = 0, []
        poly_of = []
        for (x, y, r) in pts[rail]:
            v = pcbnew.VECTOR2I(fmm(x), fmm(y))
            hit = None
            for fi, f in enumerate(fills):
                for k in range(f.OutlineCount()):
                    if f.Contains(v, k):
                        hit = (fi, k)
                        break
                if hit:
                    break
            if hit:
                inside += 1
                poly_of.append(hit)
            else:
                missing.append((round(x - 100, 3), round(y - 100, 3)))
        # width achieved along the planned centre lines (distance to the fill outline, holes ignored)
        wmin = None
        if rail in segs and fills:
            ws = []
            for line, w in segs[rail]["segs"]:
                for p, q in zip(line[:-1], line[1:]):
                    L = math.hypot(q[0] - p[0], q[1] - p[1])
                    n = max(int(L / 0.25), 1)
                    for k in range(n + 1):
                        s = np.array((p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n))
                        v = pcbnew.VECTOR2I(fmm(s[0]), fmm(s[1]))
                        best = None
                        for f in fills:
                            for kk in range(f.OutlineCount()):
                                if f.Contains(v, kk):
                                    A, B = _outline_segments(f, kk)
                                    best = 2 * _dist_to_segments(s, A, B)
                        # sample points near landing vias sit at outline ends of the path: skip those
                        if best is not None:
                            near_end = min(math.hypot(s[0] - a[0], s[1] - a[1]) for a in (line[0], line[-1]))
                            if near_end > w:
                                ws.append(min(best, 9.99))
            wmin = round(min(ws), 2) if ws else None
        res[rail] = dict(net=net, polygons=npoly, landing=len(pts[rail]), inside=inside, missing=missing,
                         single=len(set(poly_of)) <= 1, wmin=wmin,
                         planned_wmin=segs.get(rail, {}).get("wmin"), unconnected=unc.get(rail))
    return res


def table(res):
    lines = ["rail     polys  landing  in-fill  one-poly  w_min(mm)  planned  pcbnew-unconnected  missing"]
    for r, d in res.items():
        lines.append(f"{r:8s} {d['polygons']:5d}  {d['landing']:7d}  {d['inside']:7d}  {str(d['single']):8s}  "
                     f"{str(d['wmin']):9s}  {str(d['planned_wmin']):7s}  {str(d['unconnected']):18s}  "
                     f"{d['missing'] if d['missing'] else '-'}")
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
    print("keep-outs replicated on In3.Cu:", rep.get("keepouts_added"), " skipped:", rep.get("keepout_skipped", []))
    for r, d in rep["islands"].items():
        if d["unreached"]:
            print("UNREACHED", r, d["unreached"])
    print(table(res))
    if len(argv) > 3:
        sys.path.insert(0, __file__.rsplit("/", 1)[0])
        import boardlib as bl
        bl.render(argv[2], argv[3], layers=("In3.Cu", "Edge.Cuts"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
