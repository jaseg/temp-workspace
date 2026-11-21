"""MCUIF block: STM32G474CBT6 (U704, LQFP-48) with its decoupling, VDDA / VREF+ filter, passive control-voltage
dividers, the VNEG_REF op-amp U701 (TLV9001), I2C pull-ups, BOOT0, LED.  36 parts (the whole /mcu_if/ sheet).
Run: cd blocks/mcuif && python3 gen_mcuif.py [--render]
Block-local mm, origin = board (27, 45); block 66.5 x 10 (bottom edge = board edge y 55).
U704 spans the full block height: its N and S pins fan out to vias under the package body (two staggered rows) and
continue on B.Cu.  USB_DP / USB_DM: 90 R edge-coupled microstrip on F.Cu over In1 (w 0.30 / s 0.20, pitch = pin pitch).
Slow nets are routed by a local grid router (copied from blocks/fpga, generalised: point sources, N-edge targets)."""
import sys, os, math, json, heapq
sys.path.insert(0, "../..")
import numpy as np
from scipy import ndimage
import pcbnew
import boardlib as bl

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board"
W, H = 66.5, 10.0
HR = 9.65                                   # routing limit towards the board edge (copper >= 0.2 mm from y 10)
WS = 0.15
blk = bl.Block("mcuif")
NL = blk.nl
REFS = sorted(r for r, c in NL.comps.items() if c["sheet"] == "/mcu_if/")


def zdiff(w, s):
    z0, ee = bl.microstrip(w)
    return 2 * z0 * (1 - 0.48 * math.exp(-0.96 * s / bl.H)), z0, ee


W90, S90 = 0.295, 0.205
ZD, Z0U, EEU = zdiff(W90, S90)
print(f"USB pair: w {W90} s {S90} -> Zdiff {ZD:.1f} R (Z0 single {Z0U:.1f} R, eps_eff {EEU:.2f}, {math.sqrt(EEU)/bl.C0:.2f} ps/mm)")


def bplace(ref, x, y, rot=0, side="F"):
    """local helper (as in phase / fpga): place on F, flip after Add (Block.place side B segfaults in 7.0.11)"""
    fp = blk.place(ref, x, y, rot, "F")
    if side == "B":
        fp.Flip(blk.P(x, y), True)
        fp.Reference().SetLayer(pcbnew.B_Fab)
    return fp


# ============================================================ placement
CX, CY = 48.0, 4.85
bplace("U704", CX, CY, 0)
# F.Cu, west: analog dividers (pad 1 left for rot 0)
bplace("R703", 8.0, 0.8, 0)      # VREFP -> ADC_REF_MID
bplace("R704", 8.0, 1.8, 0)      # ADC_REF_MID -> GND
bplace("C702", 8.0, 2.8, 0)      # ADC_REF_MID -> GND
bplace("R733", 12.5, 0.8, 0)     # DAC_BIAS_A -> VBIAS_A
bplace("R734", 12.5, 1.8, 0)     # VBIAS_A -> -2V5
bplace("R735", 12.5, 2.8, 0)     # DAC_BIAS_K -> VBIAS_K
bplace("R736", 12.5, 3.8, 0)     # DAC_BIAS_K -> GND
bplace("U701", 28.0, 2.2, 0)     # VNEG_REF op-amp
bplace("C720", 31.0, 1.25, 0)    # +2V5 (pad 1) at pin 5
bplace("R731", 31.0, 3.15, 180)  # VREFP -> IN- (pad 2 at pin 4)
bplace("C721", 25.0, 2.2, 0)     # GND | -2V5 (pad 2 at pin 2)
bplace("R732", 27.0, 4.9, 0)     # IN- -> VNEG_REF
bplace("C722", 29.0, 4.9, 0)     # IN- | VNEG_REF
bplace("R723", 36.5, 0.8, 0)     # DAC_TAPTH -> VTAP_TH
bplace("R724", 36.5, 1.8, 0)     # VTAP_TH -> GND
bplace("C709", 36.5, 2.8, 0)     # VTAP_TH -> GND
bplace("C713", 41.9, 2.1, 180)   # U704.1 +3V3 (pad 1 east, at the pin)
# B.Cu: VTAP supply links, slow parts, decoupling
bplace("R726", 17.149, 1.5, 90, "B")    # -2V5 -> VTAP_N (pad 2 on top)
bplace("R725", 21.663, 1.5, 90, "B")    # +2V5 -> VTAP_P
bplace("C710", 45.25, 3.75, 90, "B")    # U704.48 +3V3
bplace("R728", 47.25, 3.85, 90, "B")    # SDA pull-up
bplace("R727", 49.75, 3.85, 90, "B")    # SCL pull-up
bplace("C711", 54.6, 1.2, 0, "B")       # U704.36 +3V3
bplace("C717", 46.0, 9.0, 0, "B")       # VREFP 1u
bplace("C718", 48.4, 9.0, 0, "B")       # VREFP 100n
bplace("C716", 53.2, 9.0, 0, "B")       # VDDA 10n
bplace("C715", 55.6, 9.0, 0, "B")       # VDDA 1u
bplace("FB701", 58.0, 9.0, 0, "B")    # +3V3 -> VDDA
bplace("C712", 50.8, 9.0, 180, "B")       # U704.24 +3V3
bplace("C714", 61.4, 8.6, 0, "B")       # 10u bulk
bplace("C719", 43.4, 3.6, 90, "B")      # NRST
bplace("R730", 39.9, 2.45, 0)       # LED resistor
bplace("D701", 39.0, 0.9, 0)       # LED
bplace("R729", 33.6, 3.5, 0)       # BOOT0 pull-down
bplace("JP701", 33.6, 1.5, 0)      # BOOT0 solder jumper
for r in REFS:
    assert r in blk.fps, r

# ============================================================ router (local helper, from blocks/fpga)
G = 0.05
NX, NY = int(round(W / G)) + 1, int(round(H / G)) + 1
CLR = 0.1
LAYERS = ("F.Cu", "B.Cu")
gx, gy = np.meshgrid(np.arange(NX) * G, np.arange(NY) * G, indexing="ij")
inside = (gx <= W) & (gy <= HR)
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
KEEP = [[], []]          # extra per-layer keep-outs: (x0, y0, x1, y1)
CUR = [0]
TURN = 0.3               # turn penalty (cells)
STRIP = {}               # net -> (lane y, west end x): B.Cu lanes reserved for the west bus


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
    for fp in blk.b.GetFootprints():
        for p in fp.Pads():
            x, y = blk.loc(p.GetPosition())
            bb = p.GetBoundingBox()
            w2, h2 = pcbnew.ToMM(bb.GetWidth()) / 2 + G / 2, pcbnew.ToMM(bb.GetHeight()) / 2 + G / 2
            code = p.GetNetCode() if p.GetNetCode() > 0 else -2
            for li, ln in enumerate(LAYERS):
                if p.IsOnLayer(bl.L(ln)):
                    mark(li, x - w2, y - h2, x + w2, y + h2, code)
    for t in blk.b.GetTracks():
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
    for li in range(2):
        for (x0, y0, x1, y1) in KEEP[li]:
            mark(li, x0, y0, x1, y1, -2)
    for net, (y, xa) in STRIP.items():           # reserved B.Cu west-bus lanes (free only for their own net)
        if netcode(net) != CUR[0]:
            mark(1, xa, y - 0.08, 44.5, y + 0.08, -2)
    return own


def free_maps(code, w, clr=CLR):
    CUR[0] = code
    own = raster()
    out, dists = [], []
    for li in range(2):
        occ = (own[li] != -1) & (own[li] != code)
        d = ndimage.distance_transform_edt(~occ) * G
        dists.append(d)
        ok = (d >= w / 2 + clr + 0.015) & inside
        out.append(ok)
    via_ok = (dists[0] >= bl.VIA_D / 2 + CLR + 0.005) & (dists[1] >= bl.VIA_D / 2 + CLR + 0.005) & inside
    via_ok &= (gy >= bl.VIA_D / 2 + 0.05) & (gy <= HR - 0.1)
    for t in blk.b.GetTracks():                 # hole-to-hole >= 0.25 mm also to vias of the same net
        if isinstance(t, pcbnew.PCB_VIA):
            vx, vy = blk.loc(t.GetPosition())
            via_ok &= (gx - vx) ** 2 + (gy - vy) ** 2 >= 0.46 ** 2
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
    par = p.GetParent()
    if len(par.Pads()) == 2 or abs(w2 - h2) < 0.05:
        ox, oy = blk.loc(par.GetPosition())
        axes = {0, 4} if abs(x - ox) >= abs(y - oy) else {2, 6}
    elif w2 > h2:
        axes = {0, 4}
    else:
        axes = {2, 6}
    if par.GetReference() == "U704":         # LQFP pins: outward / inward along the pin only
        axes = {0, 4} if w2 > h2 else {2, 6}
    return cells, lays, axes, (x, y)


ROUTED, FAILED = [], []


def route(net, src, dst, w=WS, via_cost=1.0, layer_pref=None, clr=CLR):
    """src: (ref, pad) or ('PT', x, y, layer); dst: list of (ref, pad) / ('VIA', x, y) / ('PT', x, y, layer) /
    ('EDGE', 'N', layer, x0, x1).  Draws tracks / vias; for EDGE returns the x reached."""
    net = NL.canon(net)
    code = netcode(net)
    ok, via_ok, _ = free_maps(code, w, clr)
    if src[0] == "PT":
        sxy = (src[1], src[2])
        scells = {(int(round(src[1] / G)), int(round(src[2] / G)))}
        slays, saxes = [LAYERS.index(src[3])], set(range(8))
    else:
        scells, slays, saxes, sxy = pad_cells(padobj(*src))
    tgt, tax, tcen = [set(), set()], {}, {}
    for d in dst:
        if d[0] == "EDGE":
            _, side, ln, a0, a1 = d
            li = LAYERS.index(ln)
            j = int(round((w / 2 + 0.05) / G + 0.5))
            for i in range(int(round(a0 / G)), int(round(a1 / G)) + 1):
                tgt[li].add((i, j))
                tax[(li, i, j)] = {6}
                tcen[(li, i, j)] = (i * G, 0.0)
        elif d[0] in ("VIA", "PT"):
            c = (int(round(d[1] / G)), int(round(d[2] / G)))
            for li in (range(2) if d[0] == "VIA" else [LAYERS.index(d[3])]):
                tgt[li].add(c)
                tax[(li,) + c] = set(range(8))
                tcen[(li,) + c] = (d[1], d[2])
        else:
            pc, pl, pa, cen = pad_cells(padobj(*d))
            for li in pl:
                for c in pc:
                    tgt[li].add(c)
                    tax[(li,) + c] = pa
                    tcen[(li,) + c] = cen
    for li in range(2):
        for c in tgt[li]:
            if 0 <= c[0] < NX and 0 <= c[1] < NY:
                ok[li][c] = True
        if li in slays:
            for c in scells:
                ok[li][c] = True
    allt = [c for li in range(2) for c in tgt[li]]
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
        if n > 1500000:
            break
        in_src = (i, j) in scells and li in slays
        for nd in (range(8) if d < 0 else (d, (d + 1) % 8, (d - 1) % 8)):
            if d < 0 and in_src and nd not in saxes:
                continue
            di, dj = DIRS[nd]
            a, b_ = i + di, j + dj
            if not (0 <= a < NX and 0 <= b_ < NY) or not ok[li][a, b_]:
                continue
            if in_src and d >= 0 and nd != d:
                continue
            step = (1.414 if nd % 2 else 1.0) * pref[li] + (TURN if (d >= 0 and nd != d) else 0.0)
            ns = (a, b_, li, nd)
            ng = g_ + step
            if ng < best.get(ns, 1e18):
                best[ns] = ng
                prev[ns] = st
                heapq.heappush(openl, (ng + hfun(a, b_), ng, ns))
        if via_ok[i, j] and not in_src and d >= 0:
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
        if k == 0:
            pts[0] = sxy
        if k == len(runs) - 1:
            gc = tcen[(goal[2], goal[0], goal[1])]
            if dst[0][0] == "EDGE":
                pts.append((pts[-1][0], 0.0))
            else:
                last = pts[-1]
                if abs(last[0] - gc[0]) < 1e-6 or abs(last[1] - gc[1]) < 1e-6 or abs(abs(last[0] - gc[0]) - abs(last[1] - gc[1])) < 1e-6:
                    pts.append(gc)
        while True:                            # drop back-tracking points (grid end -> pad centre)
            for m in range(1, len(pts) - 1):
                if bl.turn_deg(pts[m - 1], pts[m], pts[m + 1]) > 46:
                    del pts[m]
                    break
            else:
                break
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


def tie(ref, num, d=0.7, w=None, pair=False):
    """pad -> own via (GND to In1, supply to In2) beyond the pad along the part axis; pair = second via"""
    p = padobj(ref, num)
    net = p.GetNetname()
    px, py = blk.loc(p.GetPosition())
    ox, oy = blk.loc(p.GetParent().GetPosition())
    dx, dy = px - ox, py - oy
    n_ = math.hypot(dx, dy) or 1.0
    w = w or (0.3 if (net == "GND" or net.startswith("+") or net.startswith("-")) else 0.2)
    v = place_via(net, px + dx / n_ * d, py + dy / n_ * d, keep=[(ref, num)])
    route(net, (ref, num), [v], w)
    if pair:
        ux, uy = v[1] - px, v[2] - py
        nu = math.hypot(ux, uy) or 1.0
        v2 = place_via(net, v[1] + ux / nu * 0.7, v[2] + uy / nu * 0.7, keep=[(ref, num)])
        route(net, ("PT", v[1], v[2], "B.Cu" if padobj(ref, num).IsOnLayer(pcbnew.B_Cu) else "F.Cu"), [v2], w)


def edge(net, src, x0, x1, w=WS, note="", layer="B.Cu"):
    x = route(net, src, [("EDGE", "N", layer, x0, x1)], w)
    if x is not None:
        blk.iface(net, x, 0.0, layer, "N", "slow", w, note)
    return x


# ============================================================ U704 fan-out under the body (N and S rows)
VIA_AT = {}
YN_IN, YS_IN = CY - 3.425, CY + 3.425
for k in range(12):
    pn, ps_ = str(37 + k), str(13 + k)
    xn, xs = CX + 2.75 - 0.5 * k, CX - 2.75 + 0.5 * k
    yn = CY - (2.9 if k % 2 == 0 else 2.3)
    ys = CY + (2.9 if k % 2 == 0 else 2.3)
    for pin, x, yin, yv in ((pn, xn, YN_IN, yn), (ps_, xs, YS_IN, ys)):
        net = NL.net_of("U704", pin)
        if net.startswith("unconnected"):
            continue
        wv = 0.25 if (net in ("GND", "+3V3") or net.startswith("/mcu_if/V")) else WS
        blk.track(net, wv, [(x, yin), (x, yv)], "F.Cu")
        blk.via(x, yv, net)
        VIA_AT[pin] = (x, yv)

# ============================================================ USB pair (F.Cu, 90 R, pitch 0.5 = pin pitch)
RF = {"/USB_DP": W90, "/USB_DM": W90}
pDP, pDM = blk.pad("U704", "34"), blk.pad("U704", "33")
XV = 57.0                      # DP vertical run; DM at XV + 0.5
dp = [pDP, (XV - 1.1, pDP[1]), (XV, pDP[1] - 1.1), (XV, 0.0)]
t = 1.1 + 0.5 * math.tan(math.radians(22.5))
dm = [pDM, (XV - 1.1 + 0.5 * math.tan(math.radians(22.5)), pDM[1]), (XV + 0.5, pDP[1] - 1.1 + 0.5 - 0.5 * math.tan(math.radians(22.5)) - 0.5 + 0.5 * math.tan(math.radians(22.5)) * 0), (XV + 0.5, 0.0)]
# exact parallel offset of the 45-degree segment (pitch 0.5)
o = 0.5 / math.sqrt(2)
ax, ay = dp[1][0] + o, dp[1][1] + o            # DM diagonal passes through (DP diag point + normal * 0.5)
dm = [pDM, (ax + (ay - pDM[1]), pDM[1]), (XV + 0.5, ay - (XV + 0.5 - ax)), (XV + 0.5, 0.0)]
blk.track("/USB_DP", W90, dp, "F.Cu", name="USB_DP", z=45, ch=0.0)
blk.track("/USB_DM", W90, dm, "F.Cu", name="USB_DM", z=45, ch=0.0)
LDP, LDM = blk.route_len("USB_DP"), blk.route_len("USB_DM")
for q in (dp, dm):
    blk.rf_keepout(q, W90, 2 * W90)
# (no extra router keep-out: the router keeps 0.1 mm, the pour keeps 2 w)
blk.iface("/USB_DP", XV, 0.0, "F.Cu", "N", "pair", W90, f"90 R diff (w {W90} s {S90}) from J601 / U608; {LDP:.2f} mm in block")
blk.iface("/USB_DM", XV + 0.5, 0.0, "F.Cu", "N", "pair", W90, f"90 R diff; {LDM:.2f} mm in block")

# ============================================================ straight B.Cu lanes N row -> N edge (fpga bus)
NOTE = {"/UC_SWDIO": "J501.8", "/UC_SWCLK": "J501.10", "/I2C_SCL": "MS5351M; 4.7k R727 here", "/SPI_SCK": "U501.28",
        "/SPI_MISO": "U501.30", "/SPI_MOSI": "U501.29", "/I2C_SDA": "MS5351M; 4.7k R728 here", "/DBG1": "J501.12"}
for pin in ("37", "38", "39", "40", "41", "42", "44", "46"):
    net = NL.net_of("U704", pin)
    x, y = VIA_AT[pin]
    blk.track(net, WS, [(x, y), (x, 0.0)], "B.Cu")
    blk.iface(net, x, 0.0, "B.Cu", "N", "slow", WS, f"U704.{pin}; {NOTE[net]}")

# ============================================================ jobs
JOBS = []


def job(name, fn):
    JOBS.append((name, fn))


V = lambda pin: ("PT", VIA_AT[pin][0], VIA_AT[pin][1], "B.Cu")
LANES = [("/VOFS", 9.4, 0.7), ("/VNEG_REF", 9.0, 1.2), ("/DAC_TRIG", 8.6, 1.7), ("/TRIG_SEL", 8.2, 2.2),
         ("/ADC_IN", 7.8, 4.5), ("/mcu_if/VREFP", 7.4, 6.7), ("/mcu_if/DAC_BIAS_K", 7.0, 10.6), ("/mcu_if/DAC_BIAS_A", 6.6, 11.1)]
for n_, y_, xa_ in LANES:
    STRIP[NL.canon(n_)] = (y_, xa_)
job("L_vofs", lambda: edge("/VOFS", V("13"), 0.9, 1.1, note="U704.13 DAC -> R119 (input block)"))
job("L_vneg", lambda: edge("/VNEG_REF", ("R732", "@VNEG_REF"), 1.4, 1.6, note="U701 out -> R123 (input block)"))
job("L_dactrig", lambda: edge("/DAC_TRIG", ("U704", "12"), 1.9, 2.1, note="U704.12 DAC -> R383 (phase)"))
job("L_trigsel", lambda: edge("/TRIG_SEL", V("43"), 2.4, 2.6, note="U704.43 -> R302 (phase)"))
job("L_adcin", lambda: edge("/ADC_IN", ("U704", "8"), 4.7, 4.9, note="U704.8 ADC in; RC R211 / C207 sit in the analog block"))
job("L_vref", lambda: route("/mcu_if/VREFP", V("20"), [("R703", "@VREFP")], 0.2))
job("L_vref3", lambda: route("/mcu_if/VREFP", ("R731", "@VREFP"), [("R703", "@VREFP"), ("C718", "@VREFP")], 0.2))
job("L_biask", lambda: route("/mcu_if/DAC_BIAS_K", V("17"), [("R735", "@DAC_BIAS_K"), ("R736", "@DAC_BIAS_K")]))
job("L_biasa", lambda: route("/mcu_if/DAC_BIAS_A", V("14"), [("R733", "@DAC_BIAS_A")]))
# supply / decoupling first (wide)
job("fbt", lambda: tie("FB701", "@+3V3", pair=True))
job("c710", lambda: route("+3V3", V("48"), [("C710", "@+3V3")], 0.3))
job("p1", lambda: route("+3V3", ("U704", "1"), [("C713", "@+3V3")], 0.3))
job("p36", lambda: route("+3V3", ("U704", "36"), [("C711", "@+3V3")], 0.3))
job("p35", lambda: tie("U704", "35", 0.6, 0.3))
job("p24", lambda: route("+3V3", V("24"), [("C712", "@+3V3")], 0.3))
job("vref", lambda: route("/mcu_if/VREFP", V("20"), [("C718", "@VREFP")], 0.25))
job("vref2", lambda: route("/mcu_if/VREFP", ("C717", "@VREFP"), [("C718", "@VREFP")], 0.25))
job("vdda", lambda: route("/mcu_if/VDDA", V("21"), [("C716", "@VDDA")], 0.25))
job("vdda2", lambda: route("/mcu_if/VDDA", ("C715", "@VDDA"), [("C716", "@VDDA"), ("FB701", "@VDDA")], 0.25))
job("vdda3", lambda: route("/mcu_if/VDDA", ("C716", "@VDDA"), [("C715", "@VDDA")], 0.25))
job("u701v5", lambda: route("+2V5", ("U701", "5"), [("C720", "@+2V5")], 0.3))
job("u701v2", lambda: route("-2V5", ("U701", "2"), [("C721", "@-2V5")], 0.3))
job("u701g", lambda: tie("U701", "3", 0.9, 0.3))
for ref, num, pair in (("C710", "@GND", False), ("C713", "@GND", False), ("C713", "@+3V3", True), ("C711", "@GND", False),
                       ("C711", "@+3V3", True), ("C712", "@GND", False), ("C712", "@+3V3", True), ("C717", "@GND", False),
                       ("C718", "@GND", False), ("C715", "@GND", False), ("C716", "@GND", False), ("C714", "@GND", True),
                       ("C714", "@+3V3", True), ("C720", "@GND", False), ("C720", "@+2V5", True), ("C721", "@GND", False),
                       ("C721", "@-2V5", True), ("R725", "@+2V5", True), ("R726", "@-2V5", True),                        ("R704", "@GND", False), ("C702", "@GND", False), ("R736", "@GND", False), ("R724", "@GND", False),
                       ("C709", "@GND", False), ("C719", "@GND", False), ("R729", "@GND", False), ("R734", "@-2V5", False)):
    job("tie" + ref + num, lambda ref=ref, num=num, pair=pair: tie(ref, num, pair=pair))
# VTAP supply links straight to the N edge (B.Cu)
for ref, net in (("R725", "/VTAP_P"), ("R726", "/VTAP_N")):
    def f(ref=ref, net=net):
        a = blk.pad(ref, "@" + net)
        blk.track(net, 0.4, [a, (a[0], 0.0)], "B.Cu")
        blk.iface(net, a[0], 0.0, "B.Cu", "N", "supply", 0.4, f"{ref} 0 R from {'+2V5' if 'P' in net else '-2V5'} (In2 via pair at the part)")
    job("vtap" + ref, f)
# local analog networks
job("u701in", lambda: route("Net-(U701--)", ("U701", "4"), [("R731", "@Net-(U701--)")]))
job("u701fb", lambda: route("Net-(U701--)", ("R732", "@Net-(U701--)"), [("U701", "4"), ("R731", "@Net-(U701--)")]))
job("u701fbc", lambda: route("Net-(U701--)", ("C722", "@Net-(U701--)"), [("R732", "@Net-(U701--)")]))
job("u701out", lambda: route("/VNEG_REF", ("U701", "1"), [("R732", "@VNEG_REF")]))
job("u701outc", lambda: route("/VNEG_REF", ("C722", "@VNEG_REF"), [("R732", "@VNEG_REF")]))
job("refmid", lambda: route("/ADC_REF_MID", ("R704", "@ADC_REF_MID"), [("R703", "@ADC_REF_MID")]))
job("refmidc", lambda: route("/ADC_REF_MID", ("C702", "@ADC_REF_MID"), [("R704", "@ADC_REF_MID")]))
job("biasa", lambda: route("/VBIAS_A", ("R734", "@VBIAS_A"), [("R733", "@VBIAS_A")]))
job("biask", lambda: route("/mcu_if/DAC_BIAS_K", ("R736", "@DAC_BIAS_K"), [("R735", "@DAC_BIAS_K")]))
job("vth", lambda: route("/VTAP_TH", ("R724", "@VTAP_TH"), [("R723", "@VTAP_TH")]))
job("vthc", lambda: route("/VTAP_TH", ("C709", "@VTAP_TH"), [("R724", "@VTAP_TH")]))
# MCU signals
job("dactapth", lambda: route("/mcu_if/DAC_TAPTH", ("U704", "10"), [("R723", "@DAC_TAPTH")]))
job("led", lambda: route("/mcu_if/LED", ("U704", "2"), [("R730", "@LED")]))
job("ledk", lambda: route("Net-(D701-K)", ("R730", "@Net-(D701-K)"), [("D701", "1")]))
job("leda", lambda: tie("D701", "2"))
job("boot0", lambda: route("/mcu_if/BOOT0", V("45"), [("R729", "@BOOT0")]))
job("boot0j", lambda: route("/mcu_if/BOOT0", ("JP701", "1"), [("R729", "@BOOT0")]))
job("boot0v", lambda: tie("JP701", "2"))
job("nrstc", lambda: route("/UC_NRST", ("U704", "7"), [("C719", "@UC_NRST")]))
job("scl", lambda: route("/I2C_SCL", V("39"), [("R727", "@I2C_SCL")]))
job("sda", lambda: route("/I2C_SDA", V("44"), [("R728", "@I2C_SDA")]))
job("pu3", lambda: route("+3V3", ("R727", "@+3V3"), [("R728", "@+3V3"), ("C710", "@+3V3")], 0.2))
job("pu4", lambda: route("+3V3", ("R728", "@+3V3"), [("C710", "@+3V3")], 0.2))
# to the N edge: fpga / programming header
job("mclk", lambda: edge("/MCU_CLK", ("U704", "5"), 39.0, 44.8, note="U704.5 PF0; from MS5351M CLK1 (R509 33 R in fpga)"))
job("nrst", lambda: edge("/UC_NRST", ("C719", "@UC_NRST"), 39.0, 44.8, note="U704.7; J501.14 (fpga block)"))
job("htx", lambda: edge("/HOST_TX", ("U704", "31"), 51.6, 56.2, note="U704.31 PA9 -> R512 / J501.4"))
job("hrx", lambda: edge("/HOST_RX", ("U704", "32"), 51.6, 56.2, note="U704.32 PA10 <- R511 / J501.2"))
job("adctrig", lambda: edge("/ADC_TRIG", ("U704", "25"), 51.6, 56.2, note="U704.25 PB11 <- U501.41"))
job("done", lambda: edge("/FPGA_DONE", V("16"), 51.6, 56.2, note="U704.16 <- U501.46 (R502 pull-up)"))
job("reconf", lambda: edge("/FPGA_RECONFIG", V("18"), 51.6, 56.2, note="U704.18 -> U501.48 (R501 pull-up)"))
job("spics", lambda: edge("/SPI_CS", V("22"), 51.6, 56.2, note="U704.22 -> U501.31"))
# to the N edge: analog / trigger (west end, towards board x 28-33)
job("refmide", lambda: edge("/ADC_REF_MID", ("R703", "@ADC_REF_MID"), 5.4, 6.6, note="R703 / R704 / C702 -> U202"))
job("vbiask", lambda: edge("/VBIAS_K", ("R735", "@VBIAS_K"), 3.6, 4.2, note="R735 divider -> sampler"))
job("vbiasa", lambda: edge("/VBIAS_A", ("R733", "@VBIAS_A"), 2.9, 3.4, note="R733 / R734 divider -> sampler"))
job("vthe", lambda: edge("/VTAP_TH", ("R723", "@VTAP_TH"), 35.219, 35.219, w=0.25, note="R723 / R724 / C709 -> R380 / R381"))

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
json.dump([n for n in PRIO] + [n for n in FAILJ if n not in PRIO], open(os.path.join(SCR, "mcuif_prio_next.json"), "w"))

# ============================================================ pours, outline, ifaces
blk.zone("GND", ["In1.Cu"], bl.rect_pts(0, 0, W, H), 0.2)
blk.zone("GND", ["F.Cu"], bl.rect_pts(0, 0, W, HR + 0.1), 0.2, minw=0.2)
blk.zone("GND", ["B.Cu"], bl.rect_pts(0, 0, W, HR + 0.1), 0.2, minw=0.2)
for n in ("+3V3", "+2V5", "-2V5"):
    blk.iface(n, 0, 0, "In2.Cu", "-", "supply", None, "via pairs at the caps; In2 region by the integrator")
blk.edge_rect(0, 0, W, H, "Dwgs.User")
blk.save(HERE)
path = os.path.join(HERE, "mcuif.kicad_pcb")
print(f"USB_DP {LDP:.3f} mm, USB_DM {LDM:.3f} mm in block (skew {abs(LDP - LDM):.3f} mm = {abs(LDP - LDM) * math.sqrt(EEU) / bl.C0:.2f} ps)")
res = bl.check_board(path, refs=REFS, rf_widths=RF)
for k in ("clearance", "corner"):
    for e in res["details"][k][:15]:
        print("   ", k, e)


def courtyard_overlaps(pcb):
    """local helper: pairwise courtyard intersection per side (area > 0.005 mm2)"""
    b = pcbnew.LoadBoard(pcb)
    fps = list(b.GetFootprints())
    for f in fps:
        f.BuildCourtyardCaches()
    hits = []
    for lay in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        polys = [(f.GetReference(), f.GetCourtyard(lay)) for f in fps]
        polys = [(r, p) for r, p in polys if p.OutlineCount()]
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                a = pcbnew.SHAPE_POLY_SET(polys[i][1])
                a.BooleanIntersection(polys[j][1], pcbnew.SHAPE_POLY_SET.PM_FAST)
                ar = a.Area() / 1e12
                if ar > 0.005:
                    hits.append((polys[i][0], polys[j][0], pcbnew.LayerName(lay), round(ar, 3)))
    return hits


CY_HITS = courtyard_overlaps(path)
print("courtyard overlaps:", len(CY_HITS), CY_HITS)
if "--render" in sys.argv:
    bl.render(path, os.path.join(HERE, "mcuif.png"), layers=("F.Cu", "B.Cu", "F.SilkS", "F.Fab", "Dwgs.User"), tmpdir=SCR)
    bl.render(path, os.path.join(HERE, "mcuif_detail.png"), layers=("F.Cu", "B.Cu", "F.Fab", "B.Fab"),
              crop=(40.0, 0.0, 58.0, 10.8), tmpdir=SCR)   # crop in SVG (board-area) units
