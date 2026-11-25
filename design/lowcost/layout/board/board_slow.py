"""Slow bias / control lines (TOPOLOGY.md section 9): drawn AFTER board_power.apply_trunks() and BEFORE
board_power.apply_rest().

    import board_slow
    res = board_slow.draw(B, m, mcuif_ifaces, vtap_th_end)     # m = boardlib.Block wrapping B
    board_slow.reserve(mcuif_ifaces, vtap_th_end)              # explicit geometry, for board_power (keep-free)

Section 9 route: mcuif north edge (L6 strips y 41.8-44.6) -> tap-row lanes (L6) -> via to L3 at y 28.3-32.0 under
the comparators -> explicit L3 band west under the comparators (south of the VBUS band, north of the VTAP_N vias)
-> north through channel C (x 26-31) between the via row TAP0 / TAP1 / comparator GND (y 23-24) -> west in strip A
(and north of it to the analog vias at y 19.2-20.8) or, for DAC_TRIG / TRIG_SEL, west along the pstrobe north edge
(y 25) and south through area B.  Everything up to x 26 (west edge of channel C) is explicit (EXPL below, fixed
band order N -> S: ADC_IN | 1 mm | ADC_REF_MID VBIAS_K VBIAS_A VNEG_REF VOFS DAC_TRIG TRIG_SEL); from x 26 to the
targets a small octilinear grid search (0.1 mm) keeps the clearance from all copper of other nets on L3 (ADC_IN
1 mm from the other slow lines), vias, rule areas and the lines already drawn.
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
SLOW = {"/VBIAS_A", "/VBIAS_K", "/VOFS", "/VNEG_REF", "/DAC_TRIG", "/VTAP_TH", "/ADC_REF_MID", "/TRIG_SEL", "/ADC_IN"}


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
                xcl = 0.7 if (t.GetNetname() in SLOW and (t.GetNetname() == "/ADC_IN" or net == "/ADC_IN")) else 0.0
                self._disk(_mm(p.x), _mm(p.y), pcbnew.ToMM(t.GetWidth()) / 2 + r0 + xcl)
            elif t.GetLayer() == layer and t.GetNetCode() != code:
                a, b = t.GetStart(), t.GetEnd()
                xcl = 0.7 if (layer == pcbnew.In2_Cu and t.GetNetname() in SLOW and
                              (t.GetNetname() == "/ADC_IN" or net == "/ADC_IN")) else 0.0
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
# north through the lane and changes to L3 at its via (or, VTAP_TH, ends on the R380 / R381 link on L6).
# Strip levels nest so that no two lines cross (south -> north in source order).
EAST = [  # net, strip y, lane x, via (None = ends on L6 at the given point)
    ("/ADC_REF_MID", 44.6, 52.7, (52.7, 29.15)),
    ("/DAC_TRIG", 44.2, 53.3, (53.3, 32.0)),
    ("/VOFS", 43.8, 57.3, (57.3, 32.0)),
    ("/VBIAS_A", 43.4, 57.85, (59.5, 30.5)),       # L6 jog east past U308.3's input trace (JOG6)
    ("/VBIAS_K", 43.0, 61.8, (61.8, 29.75)),
    ("/VTAP_TH", 42.6, 62.35, None),
    ("/TRIG_SEL", 42.2, 66.3, (66.3, 32.0)),
    ("/ADC_IN", 41.8, 66.85, (66.85, 28.3)),
]
JOG6 = {"/VBIAS_A": [(57.85, 33.5), (59.5, 31.85)]}     # L6 points between the lane and the via
VNEG_VIA = (35.09, 30.5)          # VNEG_REF: west of the JTAG jogs, down tap-row lane 1 (between U305 and U306)
# explicit L3 part, north -> south: net, band y (under the comparators), column x in channel C, y of the westward
# run after the column (north group: north of the via row TAP0 / TAP1 / GND 26.41,23.08; DAC_TRIG / TRIG_SEL:
# south of the +3V3 vias 25.71,23.6-24.3 along the pstrobe north edge)
EXPL = [
    ("/ADC_IN", 28.0, 30.85, 19.35),
    ("/ADC_REF_MID", 29.15, 29.65, 21.4),
    ("/VBIAS_K", 29.75, 28.5, 21.7),
    ("/VBIAS_A", 30.05, 28.2, 22.0),
    ("/VNEG_REF", 30.5, 27.9, 22.3),
    ("/VOFS", 30.95, 27.6, 22.6),
    ("/DAC_TRIG", 32.0, 27.3, 24.97),
    ("/TRIG_SEL", 32.45, 27.0, 25.27),
]
CH = 0.5                            # 45-degree chamfer leg of the two bundle turns
# west of channel C (x < 26): explicit runs through strip A (and its northern access to the analog vias) to the
# targets; DAC_TRIG / TRIG_SEL along the pstrobe north edge (y 25), north between the GND vias (13.65 / 15.05, 24.48),
# west at y 23.05 / 23.35, south at x 8.3 / 8.6 into area B, where the grid search takes over (GRID_FROM).
TAIL = {
    "/ADC_IN": [(21.0, 19.35), (20.35, 20.0), (19.06, 20.0)],          # north of R210's via (22.14, 19.97)
    "/ADC_REF_MID": [(22.25, 21.4), (21.65, 20.8)],
    "/VBIAS_K": [(17.8, 21.7), (16.4, 20.3)],
    "/VBIAS_A": [(16.0, 22.0), (15.4, 21.4), (15.4, 15.9)],            # via on the B column south of BUF_OUT_T
    "/VNEG_REF": [(7.9, 22.3), (7.75, 22.45), (2.74, 22.45), (1.94, 21.65), (1.94, 19.2)],
    "/VOFS": [(8.15, 22.6), (8.0, 22.75), (1.6, 22.75), (1.0, 22.15), (1.0, 19.2)],
    # BOM-2 (25 Nov): the phase front column now has block L3 lines (SW_S / SW_SB, x 2-9.4, board y 23.75-35.25,
    # TRIG_LEVEL) and its +-2V5 rail vias inside them.  Neither slow line enters the column: TRIG_SEL ends at a via
    # (11.0, 23.35) east of it (gen_board draws a short L6 piece to R386; the block's x 9.25 B lane is removed), and
    # DAC_TRIG runs down the L3 lane east of SW_S (x 9.8, the old TRIG_SEL corridor) to the column's south end, so the
    # column's L3 stays one area for the +2V5 / -2V5 rails (TOPOLOGY.md section 9)
    "/DAC_TRIG": [(14.77, 24.97), (14.57, 24.77), (14.57, 23.55), (14.07, 23.05), (10.3, 23.05), (9.8, 23.55),
                  (9.8, 41.0)],
    "/TRIG_SEL": [(14.42, 25.27), (14.12, 24.97), (14.12, 23.85), (13.62, 23.35), (11.0, 23.35)],
    # (24 Nov, vias out of pads: the U302 EP vias that used to fence the x 8 corridor are gone; the line keeps its
    #  east route past U301 / U302 explicitly, so the +2V5 rail keeps its L3 access to C301 / C305 from the south)
}
GRID_ORDER = ["/DAC_TRIG"]                   # (TRIG_SEL: explicit to its via, 25 Nov)      # area B: grid search from the end of TAIL to the target
# L3 targets (existing vias of the blocks, or a via placed on the block's B stub by gen_board)
TARGET = {"/ADC_REF_MID": (21.65, 20.8), "/ADC_IN": (19.06, 20.0), "/VBIAS_K": (16.4, 20.3), "/VBIAS_A": (15.4, 15.9),
          "/VOFS": (1.0, 19.2), "/VNEG_REF": (1.94, 19.2), "/DAC_TRIG": (4.6, 44.7), "/TRIG_SEL": (11.0, 23.35)}


def plen(q):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(q, q[1:]))


def _vias(ifs):
    v = {net: via for net, ys, lx, via in EAST if via}
    v["/VNEG_REF"] = VNEG_VIA
    return v


def plan(ifs, vtap_th_end):
    """explicit geometry: {net: [(layer, pts), ...]} (layer 'B.Cu' / 'In2.Cu'), vias {net: (x, y)}"""
    out = {}
    for net, ys, lx, via in EAST:
        sx, sy = ifs[net]
        end = via if via else vtap_th_end
        out.setdefault(net, []).append(("B.Cu", [(sx, sy), (sx, ys + 0.3), (sx - 0.3, ys), (lx + 0.3, ys),
                                                 (lx, ys - 0.3)] + JOG6.get(net, []) + [end]))
    sx, sy = ifs["/VNEG_REF"]
    vx, vy = VNEG_VIA
    out["/VNEG_REF"] = [("B.Cu", [(sx, sy), (sx, 44.9), (vx, 44.9 - (sx - vx)), (vx, vy)])]
    vias = _vias(ifs)
    for net, yb, xc, yn in EXPL:
        vx, vy = vias[net]
        pts = [(vx, vy)]
        if abs(vy - yb) > 1e-6:
            pts.append((vx - abs(vy - yb), yb))
        pts += [(xc + CH, yb), (xc, yb - CH), (xc, yn + CH), (xc - CH, yn)] + TAIL[net]
        out[net].append(("In2.Cu", pts))
    return out, vias


def reserve(ifs, vtap_th_end):
    """[(layer, pts, half-width incl. clearance)] of the explicit slow-line copper and vias, for board_power"""
    p, vias = plan(ifs, vtap_th_end)
    res = []
    for net, lst in p.items():
        for lay, pts in lst:
            res.append((lay, pts, W_SLOW / 2 + 0.3))
    for net, (x, y) in vias.items():
        res.append(("all", [(x, y)], 0.225 + 0.3))
    return res


def draw(B, m, ifs, vtap_th_end, log=print):
    """ifs: {net: (x, y)} of the mcuif stubs; vtap_th_end: phase VTAP_TH interface on the R380 / R381 link.
    returns {net: [ok, length mm, vias]}"""
    res = {}
    before = {t.m_Uuid.AsString() for t in B.GetTracks()}
    p, vias = plan(ifs, vtap_th_end)
    for net, lst in p.items():
        res[net] = [True, 0.0, 0]
        for lay, pts in lst:
            q = m.track(net, W_SLOW, pts, lay, ch=0.0001)
            res[net][1] += plen(q)
        if net in vias:
            m.via(vias[net][0], vias[net][1], net)
            res[net][2] += 1
    for net in GRID_ORDER:                             # area B: grid search
        a, b = TAIL[net][-1], TARGET[net]
        q = leg(B, m, net, "L3", a, b, clr=0.15, margin=3.0, d0=2)     # DAC_TRIG tail ends heading south
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
