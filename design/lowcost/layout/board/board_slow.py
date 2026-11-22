"""Slow bias / control lines (TOPOLOGY.md section 8), drawn BEFORE board_power.apply() (the power module runs last
and flows its corridors around this copper).

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
    def __init__(self, B, layer, net, clr, w, box, extra=()):
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
                xcl = 0.7 if (layer == pcbnew.In2_Cu and (t.GetNetname() == "/ADC_IN" or net == "/ADC_IN")) else 0.0
                self._seg(_mm(a.x), _mm(a.y), _mm(b.x), _mm(b.y), pcbnew.ToMM(t.GetWidth()) / 2 + r0 + xcl)
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

        for (xa, ya), (xb, yb) in extra:                 # ordering fences (see draw)
            self._seg(xa, ya, xb, yb, r0 + 0.3)

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


def search(R, a, b, d0=-1):
    """8-connected Dijkstra with a turn penalty; returns grid cells or None"""
    sa, sb = R.ij(*a), R.ij(*b)
    occ = R.occ.copy()
    for (i, j) in (sa, sb):                       # free the end points' own neighbourhood
        occ[max(0, i - 3):i + 4, max(0, j - 3):j + 4] = False
    D = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    best = {}
    pq = [(0.0, sa[0], sa[1], d0)]
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
            nc = c + (1.4142 if di and dj else 1.0) + (2.0 if d >= 0 and nd != d else 0.0)
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


def leg(B, m, net, layer, a, b, clr=0.2, w=W_SLOW, margin=3.0, extra=(), d0=-1):
    box = (max(0.3, min(a[0], b[0]) - margin), max(0.3, min(a[1], b[1]) - margin),
           min(99.7, max(a[0], b[0]) + margin), min(56.7, max(a[1], b[1]) + margin))
    R = Raster(B, LAYERS[layer], net, clr, w, box, extra)
    cells = search(R, a, b, d0)
    if cells is None:
        return None
    pts = simplify(R, cells)
    pts[0], pts[-1] = a, b
    q = m.track(net, w, pts, LNAME[layer], ch=0.0001)
    return q


# ---------------------------------------------------------------- the plan (board mm)
# L6 part (explicit): each line leaves its mcuif stub (y 45) north to its strip level, west to its tap-row lane,
# north through the lane (between a node window and the next summing jumpers) past the tap row and the comparator
# bottom pins, and changes to L3 at a via between the comparators' pad rows (y 28.5-29.15, north of the tap row and
# of the later VTAP tracks, south of the VTH rail on L1) or, for VTAP_TH, ends on the R380 / R381 link on L6.
# Strip levels nest so that no two lines cross (south -> north in source order).
EAST = [  # net, strip y, lane x, via (None = ends on L6 at the given point)
    ("/ADC_REF_MID", 44.6, 52.7, (52.7, 28.0)),
    ("/DAC_TRIG", 44.2, 53.3, (53.3, 31.0)),
    ("/VOFS", 43.8, 57.3, (57.3, 32.0)),
    ("/VBIAS_A", 43.4, 57.85, (57.85, 28.93)),
    ("/VBIAS_K", 43.0, 61.8, (61.8, 30.0)),
    ("/VTAP_TH", 42.6, 62.35, None),
    ("/TRIG_SEL", 42.2, 66.3, (66.3, 32.0)),
    ("/ADC_IN", 41.8, 66.85, (66.85, 28.3)),
]
# L3 targets (existing vias / pads of the blocks, or a via placed on the block's B stub by gen_board)
TARGET = {"/ADC_REF_MID": (21.65, 20.8), "/ADC_IN": (19.06, 20.0), "/VBIAS_K": (16.4, 20.3), "/VBIAS_A": (15.4, 16.3),
          "/VOFS": (1.0, 19.2), "/VNEG_REF": (1.94, 19.2), "/DAC_TRIG": (4.6, 41.0), "/TRIG_SEL": (9.25, 44.6)}
L3_ORDER = ["/ADC_REF_MID", "/ADC_IN", "/VBIAS_A", "/VBIAS_K", "/VNEG_REF", "/VOFS", "/DAC_TRIG", "/TRIG_SEL"]
# explicit L3 band under the highway / comparators (north -> south), x from the via west to WEST_X; ADC_IN keeps 1 mm
# from its neighbours; lanes pass the band's vias (VTH 58.61 / 65.1, R380 / R381 GND 59.04 / 63.16, C358 GND 33.92 /
# 31.41, the slow vias themselves) with >= 0.45 mm centre distance
BAND = {"/ADC_REF_MID": 28.0, "/ADC_IN": 29.1, "/VBIAS_A": 30.2, "/VBIAS_K": 30.65, "/VNEG_REF": 31.9,
        "/VOFS": 32.35, "/DAC_TRIG": 32.65, "/TRIG_SEL": 33.0}   # south of the VBUS trunk (L3, y 24.7-27.45)
WEST_X = 27.6
WEST_ORDER = ["/ADC_REF_MID", "/ADC_IN", "/VBIAS_K", "/VNEG_REF", "/VOFS", "/VBIAS_A", "/DAC_TRIG", "/TRIG_SEL"]
VNEG_VIA = (35.09, 31.9)


def plen(q):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(q, q[1:]))


def draw(B, m, ifs, vtap_th_end, log=print):
    """ifs: {net: (x, y)} of the mcuif stubs; vtap_th_end: phase VTAP_TH interface on the R380 / R381 link.
    returns {net: [ok, length mm, vias]}"""
    res = {}
    vias = {}
    before = {t.m_Uuid.AsString() for t in B.GetTracks()}
    for net, ys, lx, via in EAST:
        sx, sy = ifs[net]
        end = via if via else vtap_th_end
        pts = [(sx, sy), (sx, ys + 0.3), (sx - 0.3, ys), (lx + 0.3, ys), (lx, ys - 0.3), end]
        q = m.track(net, W_SLOW, pts, "B.Cu", ch=0.0001)
        res[net] = [True, plen(q), 0]
        if via:
            m.via(via[0], via[1], net)
            vias[net] = via
            res[net][2] += 1
    # VNEG_REF: west of the JTAG jogs, down tap-row lane 1 (between U305 and U306)
    sx, sy = ifs["/VNEG_REF"]
    vx, vy = VNEG_VIA
    q = m.track("/VNEG_REF", W_SLOW, [(sx, sy), (sx, 44.9), (vx, 44.9 - (sx - vx)), (vx, vy)], "B.Cu", ch=0.0001)
    m.via(vx, vy, "/VNEG_REF")
    vias["/VNEG_REF"] = (vx, vy)
    res["/VNEG_REF"] = [True, plen(q), 1]
    for net in L3_ORDER:                               # explicit band
        (vx, vy), yb = vias[net], BAND[net]
        pts = [(vx, vy)]
        if abs(vy - yb) > 1e-6:
            pts.append((vx - abs(vy - yb), yb))
        pts.append((WEST_X, yb))
        q = m.track(net, W_SLOW, pts, "In2.Cu", ch=0.0001)
        res[net][1] += plen(q)
    for net in WEST_ORDER:                             # west of the band: grid search
        a, b = (WEST_X, BAND[net]), TARGET[net]
        q = leg(B, m, net, "L3", a, b, clr=0.15, margin=8.0, d0=4)     # arrives heading west
        if q is None:
            res[net][0] = False
            log(f"slow line {net}: no L3 path {a} -> {b}")
            continue
        res[net][1] += plen(q)
    # a line that could not be completed is removed again (no dangling half-routes)
    for net, v in res.items():
        if v[0]:
            continue
        for t in list(B.GetTracks()):
            if t.GetNetname() == net and t.m_Uuid.AsString() not in before:
                B.Remove(t)
        v[1], v[2] = 0.0, 0
    return {k: (v[0], round(v[1], 2), v[2]) for k, v in res.items()}
