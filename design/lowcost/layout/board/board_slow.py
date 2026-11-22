"""Slow bias / control lines (TOPOLOGY.md section 8), drawn after board_power.apply()  - WORK IN PROGRESS, NOT CALLED
by gen_board.py (22 Nov): the current L3 corridor layout leaves no channel for the plan below; see README.md.

    import board_slow
    res = board_slow.draw(B, m)        # m = boardlib.Block wrapping B

The layer sequence and every layer change (via position) of each net is fixed in PLAN below (chosen by hand from
the merged board: tap-row lanes, the L3 channel between the VBUS corridor and the VTAP_N track, the L6 passage
x 26.8-28.7 between the comparator GND via (26.41, 23.07) and TAP0's drop, the L3 area north of the +2V5 corridor).
Between two fixed points on ONE layer the exact path is found by a small octilinear grid search (0.1 mm) that keeps
the given clearance from all copper of other nets on that layer, all vias / pads, rule areas and the lines already
drawn; nothing is routed on a layer or through a via that the plan does not name.
"""
import heapq
import math
import numpy as np
import pcbnew

ORG = 100.0
G = 0.1
W_SLOW = 0.15
LAYERS = {"L3": pcbnew.In2_Cu, "L6": pcbnew.B_Cu}
LNAME = {"L3": "In2.Cu", "L6": "B.Cu"}


def _mm(v):
    return pcbnew.ToMM(v) - ORG


class Raster:
    def __init__(self, B, layer, net, clr, w, box):
        self.x0, self.y0, x1, y1 = box
        self.nx, self.ny = int((x1 - self.x0) / G) + 1, int((y1 - self.y0) / G) + 1
        self.occ = np.zeros((self.nx, self.ny), bool)
        xs = self.x0 + np.arange(self.nx) * G
        ys = self.y0 + np.arange(self.ny) * G
        self.X, self.Y = np.meshgrid(xs, ys, indexing="ij")
        r0 = clr + w / 2
        code = B.FindNet(net).GetNetCode() if B.FindNet(net) else -1
        for t in B.GetTracks():
            if isinstance(t, pcbnew.PCB_VIA):
                if t.GetNetCode() == code:
                    continue
                p = t.GetPosition()
                self._disk(_mm(p.x), _mm(p.y), pcbnew.ToMM(t.GetWidth()) / 2 + r0)
            elif t.GetLayer() == layer and t.GetNetCode() != code:
                a, b = t.GetStart(), t.GetEnd()
                extra = 0.8 if (layer == pcbnew.In2_Cu and (t.GetNetname() == "/ADC_IN" or net == "/ADC_IN")) else 0.0
                self._seg(_mm(a.x), _mm(a.y), _mm(b.x), _mm(b.y), pcbnew.ToMM(t.GetWidth()) / 2 + r0 + extra)
        for f in B.GetFootprints():
            for p in f.Pads():
                if not p.IsOnLayer(layer) or p.GetNetCode() == code:
                    continue
                bb = p.GetBoundingBox()
                self._rect(_mm(bb.GetX()) - r0, _mm(bb.GetY()) - r0, _mm(bb.GetRight()) + r0, _mm(bb.GetBottom()) + r0)
        from matplotlib.path import Path as MPath
        for z in B.Zones():
            if not z.IsOnLayer(layer):
                continue
            if z.GetIsRuleArea():
                if not z.GetDoNotAllowTracks():
                    continue
                polys = [z.Outline()]
            else:
                if z.GetNetCode() == code or z.GetNetname() == "GND":
                    continue
                polys = [z.GetFilledPolysList(layer)]
            for ps in polys:
                for oi in range(ps.OutlineCount()):
                    c = ps.COutline(oi)
                    pts = [(_mm(c.CPoint(k).x), _mm(c.CPoint(k).y)) for k in range(c.PointCount())]
                    if len(pts) < 3:
                        continue
                    xa, ya = np.array(pts).T
                    if xa.max() < self.x0 - 1 or xa.min() > x1 + 1 or ya.max() < self.y0 - 1 or ya.min() > y1 + 1:
                        continue
                    ins = MPath(pts).contains_points(np.c_[self.X.ravel(), self.Y.ravel()]).reshape(self.X.shape)
                    for k in range(len(pts)):
                        self._seg(*pts[k], *pts[(k + 1) % len(pts)], r0)
                    self.occ |= ins

    def _disk(self, x, y, r):
        m = (self.X - x) ** 2 + (self.Y - y) ** 2 <= r * r
        self.occ |= m

    def _seg(self, x0, y0, x1, y1, r):
        if max(x0, x1) + r < self.x0 or min(x0, x1) - r > self.x0 + self.nx * G or \
                max(y0, y1) + r < self.y0 or min(y0, y1) - r > self.y0 + self.ny * G:
            return
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy or 1e-12
        t = np.clip(((self.X - x0) * dx + (self.Y - y0) * dy) / L2, 0, 1)
        self.occ |= (self.X - x0 - t * dx) ** 2 + (self.Y - y0 - t * dy) ** 2 <= r * r

    def _rect(self, a, b, c, d):
        self.occ |= (self.X >= a) & (self.X <= c) & (self.Y >= b) & (self.Y <= d)

    def ij(self, x, y):
        return int(round((x - self.x0) / G)), int(round((y - self.y0) / G))

    def xy(self, i, j):
        return round(self.x0 + i * G, 3), round(self.y0 + j * G, 3)


def search(R, a, b):
    """8-connected Dijkstra with a turn penalty; returns grid cells or None"""
    sa, sb = R.ij(*a), R.ij(*b)
    occ = R.occ.copy()
    for (i, j) in (sa, sb):                       # free the end points' own neighbourhood
        occ[max(0, i - 3):i + 4, max(0, j - 3):j + 4] = False
    D = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    best = {}
    pq = [(0.0, sa[0], sa[1], -1)]
    prev = {}
    while pq:
        c, i, j, d = heapq.heappop(pq)
        if (i, j, d) in best:
            continue
        best[(i, j, d)] = c
        if (i, j) == sb:
            cells = [(i, j)]
            k = (i, j, d)
            while k in prev:
                k = prev[k]
                cells.append(k[:2])
            return cells[::-1]
        for nd, (di, dj) in enumerate(D):
            if d >= 0:
                turn = min((nd - d) % 8, (d - nd) % 8)
                if turn > 1:
                    continue                      # no turn sharper than 45 degrees
            ni, nj = i + di, j + dj
            if not (0 <= ni < R.nx and 0 <= nj < R.ny) or occ[ni, nj]:
                continue
            nc = c + (1.4142 if di and dj else 1.0) + (0.6 if d >= 0 and nd != d else 0.0)
            key = (ni, nj, nd)
            if key in best:
                continue
            prev[key] = (i, j, d)
            heapq.heappush(pq, (nc, ni, nj, nd))
    return None


def simplify(R, cells):
    pts = [R.xy(*cells[0])]
    for k in range(1, len(cells) - 1):
        d0 = (cells[k][0] - cells[k - 1][0], cells[k][1] - cells[k - 1][1])
        d1 = (cells[k + 1][0] - cells[k][0], cells[k + 1][1] - cells[k][1])
        if d0 != d1:
            pts.append(R.xy(*cells[k]))
    pts.append(R.xy(*cells[-1]))
    return pts


def leg(B, m, net, layer, a, b, clr=0.2, w=W_SLOW, margin=3.0):
    box = (max(0.3, min(a[0], b[0]) - margin), max(0.3, min(a[1], b[1]) - margin),
           min(99.7, max(a[0], b[0]) + margin), min(56.7, max(a[1], b[1]) + margin))
    R = Raster(B, LAYERS[layer], net, clr, w, box)
    cells = search(R, a, b)
    if cells is None:
        return None
    pts = simplify(R, cells)
    pts[0], pts[-1] = a, b
    q = m.track(net, w, pts, LNAME[layer], ch=0.0001)
    return q


# ---------------------------------------------------------------- the plan (board mm)
# Analog-east group (ADC_REF_MID, ADC_IN, VBIAS_K, VBIAS_A):
#   mcuif stub (y 45) -L6-> tap-row lane (5 / 8 / 7 / 6) -> via in the L3 channel y 27.5-32.4 (between the VBUS
#   corridor and the VTAP_N track; ARM 28.3 / ADC_IN 29.3 / VK 30.3 / VA 30.9, ADC_IN 1 mm from its neighbours)
#   -L3-> west to the passage -> via -L6-> north through the passage x 26.9-28.4 (between the comparator GND via
#   (26.41, 23.07) and TAP0's drop x 28.98) across the +2V5 / -2V5 / VBUS corridors -> via north of the +2V5
#   corridor (y 21.6, x 24.6-26.7) -L3-> the analog block's L3 via.
SPEC = [  # net, lane x, channel via, passage via, north via, target
    ("/ADC_REF_MID", 53.15, (53.15, 28.3), (28.4, 28.3), (26.7, 21.6), (21.65, 20.8)),
    ("/ADC_IN", 66.6, (66.6, 29.3), (27.9, 29.3), (26.0, 21.6), (19.06, 20.0)),
    ("/VBIAS_K", 62.45, (62.45, 30.3), (27.4, 30.3), (25.3, 21.6), (16.4, 20.3)),
    ("/VBIAS_A", 57.45, (57.45, 30.9), (26.9, 30.9), (24.6, 21.6), (15.4, 16.3)),
]
ORDER_L3N = ["/ADC_REF_MID", "/ADC_IN", "/VBIAS_K", "/VBIAS_A"]


def draw(B, m, ifs, log=print):
    """returns {net: (ok, length mm, n vias)}"""
    res = {n: [True, 0.0, 0] for n, *_ in SPEC}
    vias = []

    def L(net, layer, a, b, **kw):
        if not res[net][0]:
            return
        q = leg(B, m, net, layer, a, b, **kw)
        if q is None:
            res[net][0] = False
            log(f"slow line {net}: no {layer} path {a} -> {b}")
            return
        res[net][1] += sum(math.hypot(y[0] - x[0], y[1] - x[1]) for x, y in zip(q, q[1:]))

    def V(net, p):
        m.via(p[0], p[1], net)
        res[net][2] += 1
    for net, lx, cv, pv, nv, tgt in SPEC:              # all vias first, so no leg passes over a later via spot
        V(net, cv); V(net, pv); V(net, nv)
    for net, lx, cv, pv, nv, tgt in SPEC:              # L6: mcuif -> lane -> channel via
        s = ifs[net]
        L(net, "L6", s, (lx, 41.9))
        L(net, "L6", (lx, 41.9), cv)
    for net, lx, cv, pv, nv, tgt in SPEC:              # L3 channel, north line first
        L(net, "L3", cv, pv, clr=0.25)
    for net, lx, cv, pv, nv, tgt in reversed(SPEC):    # L6 passage, west (inner) line first
        L(net, "L6", pv, nv, margin=2.0)
    for net in ORDER_L3N:                              # L3 north of the corridors
        nv, tgt = [(e[4], e[5]) for e in SPEC if e[0] == net][0]
        L(net, "L3", nv, tgt, margin=4.0)
    return {k: (v[0], round(v[1], 2), v[2]) for k, v in res.items()}
