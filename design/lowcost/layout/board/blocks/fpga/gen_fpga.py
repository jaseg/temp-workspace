"""FPGA block: GW1NZ-LV1 QN48 (U501), MS5351M (U502) + Y501, configuration / decoupling.
Run: cd blocks/fpga && python3 gen_fpga.py [--render]
Block-local mm, origin = board (56, 0.5), rectangle 18 x 22 mm (FLOORPLAN).  J501 / R511 / R512 live in mcuif.
Strobes and supply fan-outs are drawn by hand; the slow nets are routed by a small local grid router (route(),
0.05 mm grid, two layers, 45-degree moves only, pad-axis exits).  Supplies: via pairs into the In2 zones drawn here
(+3V3 everywhere, +1V2 island under U501 with a tongue to the SE corner), grounds into the In1 zone."""
import sys, os, math, json, heapq
sys.path.insert(0, "../..")
import numpy as np
from scipy import ndimage
import pcbnew
import boardlib as bl

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board"
W, H = 18.0, 22.0
W50, WS = bl.W50, 0.15
blk = bl.Block("fpga")
NL = blk.nl
MOVED = ("J501", "R511", "R512")          # programming header + UART resistors: mcuif block
REFS = sorted(r for r, c in NL.comps.items() if c["sheet"] == "/fpga_clock/" and r not in MOVED)


def bplace(ref, x, y, rot=0, side="F"):
    """place on F, flip after Add (Block.place side B segfaults in 7.0.11)"""
    fp = blk.place(ref, x, y, rot, "F")
    if side == "B":
        fp.Flip(blk.P(x, y), True)
        fp.Reference().SetLayer(pcbnew.B_Fab)
    return fp


# ---------------- placement
CX, CY = 8.6, 9.8
bplace("U501", CX, CY, 90)
bplace("U502", 12.1, 2.3, 0)              # left: VDD XA XB SCL SDA, right: CLK0 CLK1 GND VDD CLK2 (top->bottom)
bplace("Y501", 4.6, 2.0, 0)              # pin 3 XA top-right, pin 1 XB bottom-left
bplace("R509", 15.75, 2.3, 90)            # CLK1 -> MCU_CLK (F, right of U502)
bplace("R508", 8.4, 3.9, 90)              # CLK0 -> FPGA_CLK (pin 33)
bplace("R510", 7.4, 3.9, 90)              # CLK2 -> CLK2_FPGA (pin 34)
bplace("C509", 9.6, 1.3, 0, "B")          # U502.1 VDD (B, under the left pins)
bplace("C508", 14.9, 3.6, 90, "B")        # U502.7 VDD (B, under the right pins)
bplace("C510", 16.6, 6.0, 90, "B")        # 10u +3V3
# FPGA decoupling on B at the corner via pairs
bplace("C506", 4.1, 4.9, 180, "B")        # pin 36 +3V3
bplace("C502", 2.7, 6.25, 180, "B")       # pin 37 +1V2
bplace("C505", 13.0, 6.5, 0, "B")         # pin 25 +3V3
bplace("C504", 5.4, 15.4, 90, "B")        # pin 1 +3V3
bplace("C501", 12.3, 14.4, 90, "B")       # pin 12 +1V2
bplace("C503", 10.2, 17.6, 0, "B")        # 10u +1V2
bplace("C507", 2.4, 2.4, 90, "B")         # 10u +3V3
# configuration pull resistors and the JTAGSEL jumper (B, south-west)
for i, ref in enumerate(["R506", "R505", "R504", "R503", "R502", "R501"]):
    bplace(ref, 1.0 + 1.05 * i, 17.4 + (1.2 if i % 2 else 0.0), 90, "B")
bplace("JP501", 3.0, 20.9, 0, "B")
bplace("R507", 7.6, 20.4, 90, "B")

# ---------------- hand-drawn strobes (0.2 mm neck in the 0.4 mm pin row, then 0.36 mm)
STROBE = {}


def strobe(net, pts, layer="F.Cu", w=W50, name=None):
    q = blk.track(net, w, pts, layer, name=name or net, z=50, ch=0.1)
    return q


def up(p):
    return blk.pad("U501", p)


YP, YN = 10.37, 11.37                      # analog S_STROBE_P / N ifaces (board 10.87 / 11.87)
# S_STROBE_P: pin 38 straight west, x 0.5 down to its iface (outermost)
p38 = up("38")
blk.track("/S_STROBE_P", 0.2, [p38, (4.85, p38[1])], name="S_P")
SPP = [(4.85, p38[1]), (0.87, p38[1]), (0.5, p38[1] + 0.37)]
# S_STROBE_N: pin 35 up, west at y 4.2, down at x 1.25, crosses under S_P on B.Cu (2 vias), iface below P
p35 = up("35")
blk.track("/S_STROBE_N", 0.2, [p35, (p35[0], 6.2)], name="S_N")
XN = 1.25
NV1, NV2 = (XN, p38[1] - 0.7), (XN, p38[1] + 0.7)
blk.track("/S_STROBE_N", W50, [(p35[0], 6.2), (p35[0], 4.55), (p35[0] - 0.35, 4.2), (XN + 0.35, 4.2), (XN, 4.55), NV1],
          name="S_N", ch=0.1)
blk.track("/S_STROBE_N", W50, [NV1, NV2], "B.Cu", name="S_N")
for v in (NV1, NV2):
    blk.via(*v, "/S_STROBE_N")
LN0 = blk.route_len("S_N")
nN = [NV2, (XN, YN - 0.37), (XN - 0.37, YN), (0.0, YN)]
LN = LN0 + bl.plen(nN)
# match P to N with the vertical run of P (P is shorter: add a small jog before the iface)
LP0 = blk.route_len("S_P") + bl.plen(SPP)
need = LN - LP0 - (YP - 0.37 - SPP[-1][1]) - math.hypot(0.37, 0.37) - 0.13
# P: down x 0.5 to YP - 0.37, diag to (0.13, YP), west to 0 ... extra length as a 45-degree jog to x 0.85 and back
ex = max(0.0, need)
if ex > 0.02:
    d = ex / (2 * (math.sqrt(2) - 1)) / 2              # leg of the jog (two 45-degree out/in pairs)
    d = min(d, 0.2)
    print('S jog need', ex)
    ym = (SPP[-1][1] + YP - 0.37) / 2
    jog = [(0.5, ym - 0.6), (0.5 + d, ym - 0.6 + d), (0.5 + d, ym + 0.6 - d), (0.5, ym + 0.6)]
else:
    jog = []
strobe("/S_STROBE_P", SPP + jog + [(0.5, YP - 0.37), (0.13, YP), (0.0, YP)], name="S_P")
strobe("/S_STROBE_N", nN, name="S_N")
blk.iface("/S_STROBE_P", 0.0, YP, "F.Cu", "W", "pair", W50, "U501.38; 47 R R401 in analog")
blk.iface("/S_STROBE_N", 0.0, YN, "F.Cu", "W", "pair", W50, "U501.35; dips to B.Cu under S_P (2 vias); R405 in analog")
# PH strobes: pins 39 (N) / 40 (P) west, down x 1.95 / 2.6, out on the W edge below S_N
p39, p40 = up("39"), up("40")
YPHN, YPHP = 12.6, 13.4
blk.track("/PH_STROBE_N", 0.2, [p39, (4.75, p39[1]), (4.55, p39[1] + 0.2)], name="PH_N")
blk.track("/PH_STROBE_P", 0.2, [p40, (5.15, p40[1]), (4.75, p40[1] + 0.4)], name="PH_P")
phn = [(4.55, p39[1] + 0.2), (2.15, p39[1] + 0.2), (1.95, p39[1] + 0.4), (1.95, YPHN - 0.7), (1.25, YPHN), (0.0, YPHN)]
php = [(4.75, p40[1] + 0.4), (2.8, p40[1] + 0.4), (2.6, p40[1] + 0.6), (2.6, YPHP - 0.7), (1.9, YPHP), (0.0, YPHP)]
dl = (blk.route_len("PH_N") + bl.plen(phn)) - (blk.route_len("PH_P") + bl.plen(php))
# N is longer by dl: P gets the extra length as a longer vertical: move P's turn lower and its iface stays (jog)
if dl > 0.01:
    d = min(dl / (2 * (math.sqrt(2) - 1)) / 2, 0.25)
    ym = (p40[1] + 0.6 + YPHP - 0.7) / 2
    php = php[:3] + [(2.6, ym - 0.8), (2.6 + d, ym - 0.8 + d), (2.6 + d, ym + 0.8 - d), (2.6, ym + 0.8)] + php[3:]
strobe("/PH_STROBE_N", phn, name="PH_N")
strobe("/PH_STROBE_P", php, name="PH_P")
blk.iface("/PH_STROBE_N", 0.0, YPHN, "F.Cu", "W", "pair", W50, "U501.39; 47 R R411 in pstrobe")
blk.iface("/PH_STROBE_P", 0.0, YPHP, "F.Cu", "W", "pair", W50, "U501.40; 47 R R407 in pstrobe")

# ---------------- supply fan-outs (hand-drawn): pin -> pad-wide neck -> 0.4 mm -> via pair
SUPV = {}


def supply(pin, neck, diag, n=2, step=(0.5, 0.5)):
    """neck: list of points after the pad (0.2 mm), diag: first via; second via at diag + step"""
    net = NL.net_of("U501", pin)
    p = up(pin)
    blk.track(net, 0.2, [p] + neck, name="sup" + pin)
    blk.track(net, 0.4, [neck[-1], diag], name="sup" + pin)
    v2 = (diag[0] + step[0], diag[1] + step[1])
    blk.track(net, 0.4, [diag, v2])
    blk.via(*diag, net)
    blk.via(*v2, net)
    SUPV[pin] = (diag, v2)


supply("36", [(6.4, 6.1), (6.1, 5.8)], (5.7, 5.4), step=(-0.5, -0.5))
supply("37", [(5.0, 7.6), (4.6, 7.2)], (4.15, 6.75), step=(-0.5, -0.5))
supply("25", [(10.8, 6.1)], (10.8, 6.1), step=(0.65, 0.0))
supply("1", [(6.4, 13.4)], (6.4, 13.95), step=(-0.5, 0.5))
supply("12", [(10.8, 13.4), (11.1, 13.7)], (11.5, 14.1), step=(0.5, 0.5))
for pin in ("2", "26"):                                      # GND pins straight into the exposed pad
    p = up(pin)
    e = (p[0], CY + 2.2) if p[1] > CY else (p[0], CY - 2.2)
    blk.track("GND", 0.2, [p, e])
for dx in (-1.2, 0.0, 1.2):                                  # EP thermal vias
    for dy in (-1.2, 0.0, 1.2):
        blk.via(CX + dx, CY + dy, "GND")

# ---------------- grid router
G = 0.05
NX, NY = int(round(W / G)) + 1, int(round(H / G)) + 1
CLR = 0.1
LAYERS = ("F.Cu", "B.Cu")
gx, gy = np.meshgrid(np.arange(NX) * G, np.arange(NY) * G, indexing="ij")
inside = (gx <= W) & (gy <= H)
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
EXTRA = {"U502": 0.1}                       # footprint pad clearance 0.2 mm (0.1 above the router default)


def netcode(name):
    return blk.net(name).GetNetCode()


def raster():
    own = [np.full((NX, NY), -1, np.int32) for _ in LAYERS]

    def mark(li, x0, y0, x1, y1, code, shape=None):
        i0, i1 = max(0, int(math.floor(x0 / G))), min(NX - 1, int(math.ceil(x1 / G)))
        j0, j1 = max(0, int(math.floor(y0 / G))), min(NY - 1, int(math.ceil(y1 / G)))
        if i0 > i1 or j0 > j1:
            return
        sub = (slice(i0, i1 + 1), slice(j0, j1 + 1))
        m = np.ones((i1 - i0 + 1, j1 - j0 + 1), bool) if shape is None else shape(gx[sub], gy[sub])
        o = own[li][sub]
        o[m] = code
    b = blk.b
    for fp in b.GetFootprints():
        ex = EXTRA.get(fp.GetReference(), 0.0)
        for p in fp.Pads():
            x, y = blk.loc(p.GetPosition())
            bb = p.GetBoundingBox()
            w2, h2 = pcbnew.ToMM(bb.GetWidth()) / 2 + G / 2 + ex, pcbnew.ToMM(bb.GetHeight()) / 2 + G / 2 + ex
            code = p.GetNetCode() if p.GetNetCode() > 0 else -2
            circ = p.GetShape() == pcbnew.PAD_SHAPE_CIRCLE
            shp = (lambda X, Y, x=x, y=y, r=w2: (X - x) ** 2 + (Y - y) ** 2 <= r * r) if circ else None
            for li, ln in enumerate(LAYERS):
                if p.IsOnLayer(bl.L(ln)) or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    mark(li, x - w2, y - h2, x + w2, y + h2, code, shp)
    for t in b.GetTracks():
        code = t.GetNetCode()
        if isinstance(t, pcbnew.PCB_VIA):
            x, y = blk.loc(t.GetPosition())
            r = pcbnew.ToMM(t.GetWidth()) / 2 + G / 2
            for li in range(2):
                mark(li, x - r, y - r, x + r, y + r, code, lambda X, Y, x=x, y=y, r=r: (X - x) ** 2 + (Y - y) ** 2 <= r * r)
            continue
        ln = t.GetLayerName()
        if ln not in LAYERS:
            continue
        (x0, y0), (x1, y1) = blk.loc(t.GetStart()), blk.loc(t.GetEnd())
        r = pcbnew.ToMM(t.GetWidth()) / 2 + G / 2

        def seg(X, Y, x0=x0, y0=y0, x1=x1, y1=y1, r=r):
            dx, dy = x1 - x0, y1 - y0
            L2 = dx * dx + dy * dy or 1e-9
            u = np.clip(((X - x0) * dx + (Y - y0) * dy) / L2, 0, 1)
            return (X - x0 - u * dx) ** 2 + (Y - y0 - u * dy) ** 2 <= r * r
        mark(LAYERS.index(ln), min(x0, x1) - r, min(y0, y1) - r, max(x0, x1) + r, max(y0, y1) + r, code, seg)
    return own


def free_maps(code, w):
    own = raster()
    out, dists = [], []
    edge = ndimage.distance_transform_edt(np.pad(inside, 1)) [1:-1, 1:-1] * G
    for li in range(2):
        occ = (own[li] != -1) & (own[li] != code)
        d = ndimage.distance_transform_edt(~occ) * G
        dists.append(d)
        ok = (d >= w / 2 + CLR + 0.015) & inside & (edge >= w / 2 + 0.05 - 1e-9)
        out.append(ok)
    via_ok = (dists[0] >= bl.VIA_D / 2 + CLR + 0.01) & (dists[1] >= bl.VIA_D / 2 + CLR + 0.01) & inside
    via_ok &= edge >= bl.VIA_D / 2 + 0.15
    via_ok &= ~((abs(gx - CX) < 3.35 + 0.5) & (abs(gy - CY) < 3.35 + 0.5))   # no vias in the U501 pin fan-out ring
    via_ok &= ~((abs(gx - 12.1) < 2.9 + 0.35) & (abs(gy - 2.3) < 1.15 + 0.3))  # nor at the U502 pin ends
    for t in blk.b.GetTracks():                    # via-to-via (also same net) >= 0.5 mm centre distance
        if isinstance(t, pcbnew.PCB_VIA):
            vx, vy = blk.loc(t.GetPosition())
            via_ok &= (gx - vx) ** 2 + (gy - vy) ** 2 >= 0.5 ** 2
    return out, via_ok, own


def padobj(ref, num):
    if str(num)[0] == "@":
        return [p for p in blk.fps[ref].Pads() if p.GetNetname() == NL.canon(num[1:])][0]
    return blk.pad_obj(ref, num)


def pad_cells(p):
    x, y = blk.loc(p.GetPosition())
    bb = p.GetBoundingBox()
    w2, h2 = pcbnew.ToMM(bb.GetWidth()) / 2, pcbnew.ToMM(bb.GetHeight()) / 2
    cells = set()
    for i in range(int(math.ceil((x - w2) / G)), int(math.floor((x + w2) / G)) + 1):
        for j in range(int(math.ceil((y - h2) / G)), int(math.floor((y + h2) / G)) + 1):
            if (i * G - x) ** 2 <= (w2 - 0.03) ** 2 + 1e-9 and (j * G - y) ** 2 <= (h2 - 0.03) ** 2 + 1e-9:
                cells.add((i, j))
    lays = [li for li, ln in enumerate(LAYERS) if p.IsOnLayer(bl.L(ln))]
    if p.GetShape() == pcbnew.PAD_SHAPE_CIRCLE:
        axes = set(range(8))
    else:
        axes = {0, 2, 4, 6}
    return cells, lays, axes, (x, y), (w2, h2)


ROUTED, FAILED = [], []


def route(net, src, dst, w=WS, via_cost=1.0, layer_pref=None):
    """src: (ref, pad); dst: list of (ref, pad) / ('VIA', x, y) / ('EDGE', 'S', layer, x0, x1)"""
    net = NL.canon(net)
    code = netcode(net)
    ok, via_ok, _ = free_maps(code, w)
    sp = padobj(*src)
    scells, slays, saxes, sxy, _ = pad_cells(sp)
    tgt = [set(), set()]
    tpad = [set(), set()]
    tax, tcen = {}, {}
    for d in dst:
        if d[0] == "EDGE":
            _, side, ln, a0, a1 = d
            li = LAYERS.index(ln)
            for i in range(int(round(a0 / G)), int(round(a1 / G)) + 1):
                c = (i, NY - 1 - int(round((w / 2 + 0.05) / G + 0.499)))
                tgt[li].add(c)
                tax[(li,) + c] = {2}
                tcen[(li,) + c] = (i * G, H)
        elif d[0] == "VIA":
            c = (int(round(d[1] / G)), int(round(d[2] / G)))
            for li in range(2):
                tgt[li].add(c)
                tax[(li,) + c] = set(range(8))
                tcen[(li,) + c] = (d[1], d[2])
        else:
            pc, pl, pa, cen, _ = pad_cells(padobj(*d))
            for li in pl:
                for c in pc:
                    tgt[li].add(c)
                    tpad[li].add(c)
                    tax[(li,) + c] = pa
                    tcen[(li,) + c] = cen
    for li in range(2):
        for c in tgt[li]:
            if c in tpad[li] or dst[0][0] == "VIA":
                ok[li][c] = True
        tgt[li] = {c for c in tgt[li] if ok[li][c]}
        if li in slays:
            for c in scells:
                ok[li][c] = True
    allt = [c for li in range(2) for c in tgt[li]]
    if not allt:
        FAILED.append((net, src, None))
        return None
    tx0, tx1 = min(c[0] for c in allt), max(c[0] for c in allt)
    ty0, ty1 = min(c[1] for c in allt), max(c[1] for c in allt)

    def hfun(i, j):
        dx = max(tx0 - i, 0, i - tx1)
        dy = max(ty0 - j, 0, j - ty1)
        return max(dx, dy) + 0.414 * min(dx, dy)
    si, sj = int(round(sxy[0] / G)), int(round(sxy[1] / G))
    if (si, sj) not in scells:
        si, sj = min(scells, key=lambda c: (c[0] * G - sxy[0]) ** 2 + (c[1] * G - sxy[1]) ** 2)
    openl, best, prev = [], {}, {}
    for li in slays:
        st = (si, sj, li, -1)
        best[st] = 0.0
        heapq.heappush(openl, (hfun(si, sj), 0.0, st))
    pref = [1.0, 1.0] if layer_pref is None else layer_pref
    goal, n = None, 0
    while openl:
        f, g_, st = heapq.heappop(openl)
        if g_ > best.get(st, 1e18) + 1e-9:
            continue
        i, j, li, d = st
        if (i, j) in tgt[li] and d >= 0 and d in tax[(li, i, j)] and not ((i, j) in scells and li in slays):
            goal = st
            break
        n += 1
        if n > 700000:
            break
        in_src = (i, j) in scells and li in slays
        near_src = False
        if d >= 0 and not in_src and li in slays:
            bi, bj = i - DIRS[d][0], j - DIRS[d][1]
            near_src = (bi, bj) in scells
        for nd in (range(8) if d < 0 else (d, (d + 1) % 8, (d - 1) % 8)):
            if d < 0 and nd not in saxes:
                continue
            if (in_src or near_src) and d >= 0 and nd != d:
                continue
            di, dj = DIRS[nd]
            a, b_ = i + di, j + dj
            if not (0 <= a < NX and 0 <= b_ < NY) or not ok[li][a, b_]:
                continue
            if (a, b_) in tpad[li] and (nd not in tax[(li, a, b_)] or (d >= 0 and nd != d) or d < 0 and not in_src):
                continue
            step = (1.414 if nd % 2 else 1.0) * pref[li] + (0.3 if (d >= 0 and nd != d) else 0.0)
            ns = (a, b_, li, nd)
            ng = g_ + step
            if ng < best.get(ns, 1e18):
                best[ns] = ng
                prev[ns] = st
                heapq.heappush(openl, (ng + hfun(a, b_), ng, ns))
        if via_ok[i, j] and not in_src and not near_src and d >= 0 and (i, j) not in tpad[li]:
            ns = (i, j, 1 - li, -1)
            ng = g_ + via_cost / G
            if ok[1 - li][i, j] and ng < best.get(ns, 1e18):
                best[ns] = ng
                prev[ns] = st
                heapq.heappush(openl, (ng + hfun(i, j), ng, ns))
    if goal is None:
        FAILED.append((net, src, dst[0] if dst else None))
        print("  ROUTE FAILED", net, src, n)
        return None
    path = [goal]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    runs, cur = [], [path[0]]
    for s in path[1:]:
        if s[2] != cur[-1][2]:
            runs.append(cur)
            cur = [s]
        else:
            cur.append(s)
    runs.append(cur)
    for k, r in enumerate(runs):
        pts = [(round(s[0] * G, 3), round(s[1] * G, 3)) for s in r]
        if k == 0 and len(pts) > 1:
            # start exactly on the pad centre line along the exit axis
            dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
            if abs(dy) < 1e-9:
                pts = [(round(sxy[0], 4), pts[0][1])] + pts[1:]
            elif abs(dx) < 1e-9:
                pts = [(pts[0][0], round(sxy[1], 4))] + pts[1:]
        if k == len(runs) - 1:
            if dst[0][0] == "EDGE":
                pts.append((pts[-1][0], H))
            else:
                gc = tcen[(goal[2], goal[0], goal[1])]
                last = pts[-1]
                if (goal[0], goal[1]) in tpad[goal[2]]:
                    pass                                   # ends inside the pad, entered along its axis
                elif abs(last[0] - gc[0]) < 1e-6 or abs(last[1] - gc[1]) < 1e-6 or \
                        abs(abs(last[0] - gc[0]) - abs(last[1] - gc[1])) < 1e-6:
                    pts.append(gc)
        q = [pts[0]]
        for a_, b2, c2 in zip(pts, pts[1:], pts[2:]):
            v1 = (b2[0] - a_[0], b2[1] - a_[1])
            v2 = (c2[0] - b2[0], c2[1] - b2[1])
            if abs(v1[0] * v2[1] - v1[1] * v2[0]) > 1e-9 or v1[0] * v2[0] + v1[1] * v2[1] < 0:
                q.append(b2)
        q.append(pts[-1])
        t = [q[0]]
        for p_ in q[1:]:
            if math.hypot(p_[0] - t[-1][0], p_[1] - t[-1][1]) > 1e-6:
                t.append(p_)
        for (a_, b2) in zip(t, t[1:]):
            blk.track(net, w, [a_, b2], LAYERS[r[0][2]])
        if k < len(runs) - 1:
            blk.via(round(r[-1][0] * G, 3), round(r[-1][1] * G, 3), net)
    ROUTED.append(net)
    if dst[0][0] == "EDGE":
        return path[-1][0] * G
    return True


def place_via(net, x, y, keep=()):
    _, vok, _ = free_maps(netcode(NL.canon(net)), 0.2)
    for ref, num in keep:
        p = padobj(ref, num)
        px, py = blk.loc(p.GetPosition())
        bb = p.GetBoundingBox()
        w2, h2 = pcbnew.ToMM(bb.GetWidth()) / 2 + 0.33, pcbnew.ToMM(bb.GetHeight()) / 2 + 0.33
        vok &= ~((abs(gx - px) < w2) & (abs(gy - py) < h2))
    d = (gx - x) ** 2 + (gy - y) ** 2
    d[~vok] = 1e9
    i, j = np.unravel_index(np.argmin(d), d.shape)
    if d[i, j] > 4.0:
        print("  no via spot near", net, x, y)
    vx, vy = round(float(i * G), 3), round(float(j * G), 3)
    blk.via(vx, vy, net)
    return ("VIA", vx, vy)


def tie(ref, num, d=0.75, pair=False, w=None):
    """pad -> own via (GND to In1, supply to In2) beyond the pad along the part axis; pair = second via"""
    p = padobj(ref, num)
    net = p.GetNetname()
    px, py = blk.loc(p.GetPosition())
    ox, oy = blk.loc(p.GetParent().GetPosition())
    dx, dy = px - ox, py - oy
    n_ = math.hypot(dx, dy) or 1.0
    w = w or (0.4 if net in ("GND", "+3V3", "+1V2") else 0.2)
    v = place_via(net, px + dx / n_ * d, py + dy / n_ * d, keep=[(ref, num)])
    r = route(net, (ref, num), [v], w)
    if pair and r:
        v2 = place_via(net, v[1] + dx / n_ * 0.6, v[2] + dy / n_ * 0.6)
        route(net, (ref, num), [v2], w)
    return r


def to_edge(net, src, x0, x1, w=WS, note=""):
    x = route(net, src, [("EDGE", "S", "B.Cu", x0, x1)], w)
    if x is not None:
        blk.iface(net, round(x, 3), H, "B.Cu", "S", "slow", w, note)
    return x


# ---------------- routing jobs
JOBS = []


def job(name, fn):
    JOBS.append((name, fn))


# decoupling: cap supply pad -> second via of the pin's pair (0.4 mm), cap GND pad -> via pair
DEC = {"C506": "36", "C502": "37", "C505": "25", "C504": "1", "C501": "12"}
for c, pin in DEC.items():
    def f(c=c, pin=pin):
        net = NL.net_of("U501", pin)
        route(net, (c, "@" + net), [("VIA",) + SUPV[pin][1], ("VIA",) + SUPV[pin][0]], 0.4)
        tie(c, "@GND", pair=True)
    job("dec" + c, f)
# U502 / Y501
job("xa", lambda: route("Net-(U502-XA)", ("U502", "2"), [("Y501", "3")]))
job("xb", lambda: route("Net-(U502-XB)", ("U502", "3"), [("Y501", "1")]))
job("clk0", lambda: route("Net-(U502-CLK0)", ("U502", "10"), [("R508", "@Net-(U502-CLK0)")]))
job("clk2", lambda: route("Net-(U502-CLK2)", ("U502", "6"), [("R510", "@Net-(U502-CLK2)")]))
job("clk1", lambda: route("Net-(U502-CLK1)", ("U502", "9"), [("R509", "@Net-(U502-CLK1)")]))
job("fclk", lambda: route("/fpga_clock/FPGA_CLK", ("R508", "@FPGA_CLK"), [("U501", "33")]))
job("fclk2", lambda: route("/fpga_clock/CLK2_FPGA", ("R510", "@CLK2_FPGA"), [("U501", "34")]))
job("u502v1", lambda: route("+3V3", ("U502", "1"), [("C509", "@+3V3")], 0.2))
job("u502v7", lambda: route("+3V3", ("U502", "7"), [("C508", "@+3V3")], 0.2))
job("u502g", lambda: tie("U502", "8", d=1.6, w=0.2))
for ref, num, pr in (("C509", "@+3V3", True), ("C509", "@GND", True), ("C508", "@+3V3", True), ("C508", "@GND", True),
                     ("Y501", "2", False), ("Y501", "4", False), ("C510", "@+3V3", True), ("C510", "@GND", True),
                     ("C503", "@+1V2", True), ("C503", "@GND", True), ("C507", "@+3V3", True), ("C507", "@GND", True)):
    job("tie%s%s" % (ref, num), lambda ref=ref, num=num, pr=pr: tie(ref, num, pair=pr))
# south-west: config pins via the pull resistors, iface nets to the S edge (west end, x 0.4 .. 4.6)
CFG = {"42": "R506", "43": "R505", "44": "R504", "45": "R503"}
for pin, r in CFG.items():
    def f(pin=pin, r=r):
        net = NL.net_of("U501", pin)
        route(net, ("U501", pin), [(r, "@" + net)])
        other = [p.GetNumber() for p in blk.fps[r].Pads() if p.GetNetname() != net][0]
        tie(r, other)
    job("cfg" + pin, f)
job("jp", lambda: (route("/fpga_clock/JTAGSEL_N", ("JP501", "1"), [("R504", "@JTAGSEL_N")]), tie("JP501", "2")))
SWX = (0.4, 4.6)
job("adct", lambda: to_edge("/ADC_TRIG", ("U501", "41"), *SWX, note="U501.41 -> STM32 (mcuif)"))
job("done", lambda: (to_edge("/FPGA_DONE", ("U501", "46"), *SWX, note="U501.46, R502 4.7k pull-up here; -> STM32"),
                     route("/FPGA_DONE", ("R502", "@FPGA_DONE"), [("U501", "46")]), tie("R502", "@+3V3")))
job("coarse", lambda: to_edge("/COARSE", ("U501", "47"), *SWX, note="U501.47 <- SN65LVDS2 (phase)"))
job("reconf", lambda: (to_edge("/FPGA_RECONFIG", ("U501", "48"), *SWX, note="U501.48, R501 4.7k pull-up here; STM32 open-drain"),
                       route("/FPGA_RECONFIG", ("R501", "@FPGA_RECONFIG"), [("U501", "48")]), tie("R501", "@+3V3")))
# JTAG / DBG2 to the S edge next to them (x 4.6 .. 8.4), TCK with its 4.7k pull-down R507
JX = (4.6, 8.6)
for pin, nm in (("3", "TCK"), ("4", "TMS"), ("5", "TDI"), ("6", "DBG2"), ("7", "TDO")):
    def f(pin=pin, nm=nm):
        to_edge(NL.net_of("U501", pin), ("U501", pin), *JX, note=f"U501.{pin} -> J501 (mcuif)")
        if nm == "TCK":
            route("/fpga_clock/JTAG_TCK", ("R507", "@JTAG_TCK"), [("U501", "3")])
            tie("R507", "@GND")
    job("jtag" + pin, f)
# TAPs: pins 9-11 (bottom), 13-24 (right side), 27 (top) -> S edge x 8.6 .. 14.6
TAPPIN = {NL.net_of("U501", p): p for p in [str(k) for k in list(range(9, 12)) + list(range(13, 25)) + [27]]}
for i in range(16):
    net = f"/TAP{i}"
    job("tap%d" % i, lambda net=net: to_edge(net, ("U501", TAPPIN[net]), 8.6, 14.9, note=f"U501.{TAPPIN[net]}"))
# east group: SPI, MCU_CLK, I2C -> S edge x 14.6 .. 17.7
EX = (14.6, 17.75)
for pin in ("28", "29", "30", "31"):
    job("spi" + pin, lambda pin=pin: to_edge(NL.net_of("U501", pin), ("U501", pin), *EX, note=f"U501.{pin} -> STM32"))
job("mclk", lambda: to_edge("/MCU_CLK", ("R509", "@MCU_CLK"), *EX, note="MS5351M CLK1 via R509 33 R -> STM32 PF0"))
job("scl", lambda: to_edge("/I2C_SCL", ("U502", "4"), *EX, note="MS5351M SCL (pull-ups in mcuif)"))
job("sda", lambda: to_edge("/I2C_SDA", ("U502", "5"), *EX, note="MS5351M SDA"))

PRIO = json.load(open(os.path.join(HERE, "prio.json"))) if os.path.exists(os.path.join(HERE, "prio.json")) else []
order = [j for p in PRIO for j in JOBS if j[0] == p] + [j for j in JOBS if j[0] not in PRIO]
print("routing", len(order), "jobs ...")
FAILJ = []
for name, fn in order:
    nf = len(FAILED)
    fn()
    if len(FAILED) > nf:
        FAILJ.append(name)
print("failed jobs:", FAILJ)
print("failed nets:", sorted(set(f[0] for f in FAILED)))
json.dump([n for n in FAILJ] + [n for n in PRIO if n not in FAILJ], open(os.path.join(SCR, "fpga_prio_next.json"), "w"))

# ---------------- planes: In1 GND, In2 +3V3 with a +1V2 island (U501 core) and tongue to the SE corner (power +1V2)
blk.zone("GND", ["In1.Cu"], bl.rect_pts(0, 0, W, H), 0.2)
blk.zone("+3V3", ["In2.Cu"], bl.rect_pts(0, 0, W, H), 0.2, prio=0)
ISL = [(3.0, 5.6), (7.0, 5.6), (7.0, 7.2), (10.2, 7.2), (10.2, 12.4), (12.6, 12.4), (12.6, 15.6), (16.0, 15.6), (16.0, 20.6),
       (W, 20.6), (W, H), (8.8, H), (8.8, 15.4), (5.0, 15.4), (5.0, 7.4), (3.0, 7.4)]
blk.zone("+1V2", ["In2.Cu"], ISL, 0.2, prio=1)
blk.iface("+3V3", 0, 0, "In2.Cu", "-", "supply", None, "In2 +3V3 zone over the block; feed from power W (board 74.45, 5.5)")
blk.iface("+1V2", W, H - 0.7, "In2.Cu", "E", "supply", None, "In2 +1V2 island, tongue to the SE corner (power +1V2 at board 75.25, 21.95)")
blk.edge_rect(0, 0, W, H, "Dwgs.User")
for fp_ in blk.fps.values():
    fp_.Reference().SetLayer(pcbnew.B_Fab if fp_.GetLayer() == pcbnew.B_Cu else pcbnew.F_Fab)
blk.save(HERE)
path = os.path.join(HERE, "fpga.kicad_pcb")
print("strobe lengths: S_P %.3f S_N %.3f PH_P %.3f PH_N %.3f" % (blk.route_len("S_P"), blk.route_len("S_N"),
                                                               blk.route_len("PH_P"), blk.route_len("PH_N")))
RFT = {}
res = bl.check_board(path, refs=REFS, rf_widths=RFT)
for k in ("clearance", "corner", "pad_axis", "unrouted"):
    for e in res["details"][k][:20]:
        print("   ", k, e)
CY_HITS = bl.courtyard_overlaps(path)
print("courtyard overlaps:", len(CY_HITS), CY_HITS)
if "--render" in sys.argv:
    bl.render(path, os.path.join(HERE, "fpga.png"), layers=("F.Cu", "B.Cu", "F.SilkS", "F.Fab", "Dwgs.User"), tmpdir=SCR)
    bl.render(path, os.path.join(HERE, "fpga_detail.png"), layers=("F.Cu", "B.Cu", "F.Fab", "Dwgs.User"),
              crop=(0, 0, 13, 14), tmpdir=SCR)
