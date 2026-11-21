"""FPGA block: GW1NZ-LV1 QN48 (U501), MS5351M (U502) + Y501, WR-WST programming footprint J501, config / decoupling.
Run: cd blocks/fpga && python3 gen_fpga.py [--render]
Block-local mm, origin = board (56, 0.5).  L-shaped block: main 24 x 22 mm, plus a strip x 24..29.6, y 0..7.4 for J501.
Strobes are drawn by hand; the slow nets are routed by a small local grid router (route(), 0.05 mm grid, two layers,
45-degree moves only, pad-axis exits) because boardlib has none.  Supplies end in via pairs (In2), grounds in vias (In1)."""
import sys, os, math, json, heapq
sys.path.insert(0, "../..")
import numpy as np
from scipy import ndimage
import pcbnew
import boardlib as bl

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board"
W, H = 24.0, 22.0                 # main rectangle
SX, SY = 29.6, 7.4                # strip for J501 (x W..SX, y 0..SY)
W50, WS = bl.W50, 0.2
blk = bl.Block("fpga")
NL = blk.nl
REFS = sorted(r for r, c in NL.comps.items() if c["sheet"] == "/fpga_clock/") + ["R407", "R411"]


def bplace(ref, x, y, rot=0, side="F"):
    """local helper (as in phase): place on F, flip after Add (Block.place side B segfaults in 7.0.11)"""
    fp = blk.place(ref, x, y, rot, "F")
    if side == "B":
        fp.Flip(blk.P(x, y), True)
        fp.Reference().SetLayer(pcbnew.B_Fab)
    return fp


# ---------------- placement
CX, CY = 10.0, 12.6
bplace("U501", CX, CY, 90)
bplace("J501", 14.8, 3.3, 270)
bplace("U502", 17.6, 8.6, 180)
bplace("Y501", 22.0, 8.6, 0)
bplace("R508", 13.6, 9.6, 180)          # CLK0 -> FPGA_CLK (pad 1 at U502)
bplace("R509", 13.6, 8.8, 180)          # CLK1 -> MCU_CLK
bplace("R510", 13.6, 7.6, 180)          # CLK2 -> CLK2_FPGA
bplace("C508", 15.9, 6.9, 0, "B")       # U502 pin 7 VDD
bplace("C509", 20.4, 10.7, 0)           # U502 pin 1 VDD
bplace("C510", 18.0, 11.2, 0, "B")      # 10u +3V3
# QFN decoupling on B at the supply pins (pin -> via pair -> cap)
bplace("C506", 6.3, 8.2, 90, "B")       # pin 36 +3V3
bplace("C502", 5.7, 11.0, 90, "B")      # pin 37 +1V2
bplace("C504", 7.0, 17.6, 90, "B")      # pin 1 +3V3
bplace("C501", 13.1, 17.6, 90, "B")     # pin 12 +1V2
bplace("C505", 13.9, 11.3, 90, "B")     # pin 25 +3V3
bplace("C503", 15.4, 17.6, 90, "B")     # 10u +1V2
bplace("C507", 15.4, 13.6, 90, "B")     # 10u +3V3
# PH strobe series resistors (B, next to the pin vias), J501 UART resistors (B, under the plug body)
bplace("R411", 0.55, 12.6, 90, "B")
bplace("R407", 1.45, 12.6, 90, "B")
bplace("R511", 23.05, 6.4, 90, "B")
bplace("R512", 20.5, 6.4, 90, "B")
# configuration resistors (B, bottom-left)
for i, ref in enumerate(["R506", "R505", "R504", "R503", "R502", "R501"]):
    bplace(ref, 2.4 + 0.76 * i, 18.2 + (1.45 if i % 2 else 0.0), 90, "B")
bplace("JP501", 3.6, 15.3, 0, "B")
bplace("R507", 6.6, 20.6, 90, "B")

# fix 2-pad orientation: pad 1 on top for the vertical parts where the netlist side matters is left to the router


# ---------------- hand-drawn strobes
RF = {"/S_STROBE_P": W50, "/S_STROBE_N": W50, "Net-(C412-Pad1)": W50, "Net-(C422-Pad1)": W50}
p35, p38 = blk.pad("U501", "35"), blk.pad("U501", "38")
YP, YN = 9.365, 10.365                  # analog S_STROBE ifaces (board 9.865 / 10.865)
X1, YT = 5.0, 7.4
nN = [p35, (p35[0], YT), (X1, YT), (X1 - (YN - YT), YN), (0.0, YN)]
qN = blk.track("/S_STROBE_N", W50, nN, name="S_N", z=50, ch=0.45)
V1, V2 = (5.2, 10.4), (1.0, YP)
qP1 = blk.track("/S_STROBE_P", W50, [p38, (5.6, p38[1]), V1], name="S_P", z=50)


def lenP(top):
    return [V1, (V1[0], top + 0.4), (V1[0] - 0.4, top), (V2[0] + 0.4, top), (V2[0], top + 0.4), V2]


LN = blk.route_len("S_N")
lo, hi = 6.5, 9.5                       # solve the B meander top so P = N
for _ in range(40):
    mid = (lo + hi) / 2
    tot = bl.plen([p38, (5.6, p38[1]), V1]) + bl.plen(lenP(mid)) + (V2[0] - 0.0)
    lo, hi = (mid, hi) if tot > LN else (lo, mid)
blk.track("/S_STROBE_P", W50, lenP(mid), "B.Cu", name="S_P", z=50)
blk.track("/S_STROBE_P", W50, [V2, (0.0, YP)], name="S_P", z=50)
for v in (V1, V2):
    blk.via(*v, "/S_STROBE_P")
blk.iface("/S_STROBE_P", 0.0, YP, "F.Cu", "W", "pair", W50, "U501.38; crosses under N on B.Cu (2 vias), 47 R R401 in analog")
blk.iface("/S_STROBE_N", 0.0, YN, "F.Cu", "W", "pair", W50, "U501.35")
# PH strobe: R411 / R407 on B, 0.36 mm lines straight down to the S edge (mirror-equal)
for ref, net in (("R411", "Net-(C422-Pad1)"), ("R407", "Net-(C412-Pad1)")):
    a = blk.pad(ref, "@" + net)
    blk.track(net, W50, [a, (a[0], H)], "B.Cu", name=net, z=50)
    blk.iface(net, a[0], H, "B.Cu", "S", "pair", W50, f"{ref} 47 R at U501 ({'PH_STROBE_N' if ref == 'R411' else 'PH_STROBE_P'})")

# ---------------- supply / ground vias (In2 / In1)
SUP_V = {"36": (7.45, 8.75), "37": (6.3, 10.05), "1": (7.45, 16.45), "12": (12.55, 16.45), "25": (12.55, 8.75)}
for dx in (-1.2, 0.0, 1.2):                     # EP thermal vias
    for dy in (-1.2, 0.0, 1.2):
        blk.via(CX + dx, CY + dy, "GND")


# ---------------- grid router
G = 0.05
NX, NY = int(round(SX / G)) + 1, int(round(H / G)) + 1
CLR = 0.1
LAYERS = ("F.Cu", "B.Cu")
inside = np.zeros((NX, NY), bool)
gx, gy = np.meshgrid(np.arange(NX) * G, np.arange(NY) * G, indexing="ij")
inside |= (gx <= W) & (gy <= H)
inside |= (gx <= SX) & (gy <= SY)
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


def netcode(name):
    return blk.net(name).GetNetCode()


def raster():
    """owner[layer] = net code per cell (-1 free, -2 hole / other)"""
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
        for p in fp.Pads():
            x, y = blk.loc(p.GetPosition())
            bb = p.GetBoundingBox()
            w2, h2 = pcbnew.ToMM(bb.GetWidth()) / 2 + G / 2, pcbnew.ToMM(bb.GetHeight()) / 2 + G / 2
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
    """per layer: cell usable by a track of width w of net code; via map"""
    own = raster()
    out, dists = [], []
    for li in range(2):
        occ = (own[li] != -1) & (own[li] != code)
        d = ndimage.distance_transform_edt(~occ) * G
        dists.append(d)
        ok = (d >= w / 2 + CLR + 0.005) & inside
        # keep w/2 + 0.05 from the block outline (iface stubs end on it)
        ok &= ndimage.distance_transform_edt(inside) * G >= w / 2 + 0.05 - 1e-9
        out.append(ok)
    via_ok = (dists[0] >= bl.VIA_D / 2 + CLR + 0.005) & (dists[1] >= bl.VIA_D / 2 + CLR + 0.005) & inside
    via_ok &= ndimage.distance_transform_edt(inside) * G >= bl.VIA_D / 2 + 0.1
    return out, via_ok, own


def padobj(ref, num):
    if str(num)[0] == "@":
        return [p for p in blk.fps[ref].Pads() if p.GetNetname() == NL.canon(num[1:])][0]
    return blk.pad_obj(ref, num)


def pad_cells(p):
    """target cells inside a pad (per layer list) and its allowed axis directions"""
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
    if p.GetShape() == pcbnew.PAD_SHAPE_CIRCLE:
        axes = set(range(8))
    elif len(par.Pads()) == 2 or abs(w2 - h2) < 0.05:
        ox, oy = blk.loc(par.GetPosition())
        axes = {0, 4} if abs(x - ox) >= abs(y - oy) else {2, 6}
    elif w2 > h2:
        axes = {0, 4}
    else:
        axes = {2, 6}
    return cells, lays, axes, (x, y)


ROUTED, FAILED = [], []


def route(net, src, dst, w=WS, via_cost=1.6, layer_pref=None, iface=None):
    """src: (ref, pad); dst: list of (ref, pad) / ('VIA', x, y) / ('EDGE', side, layer, x0, x1).  Draws tracks / vias."""
    net = NL.canon(net)
    code = netcode(net)
    ok, via_ok, _ = free_maps(code, w)
    sp = padobj(*src)
    scells, slays, saxes, sxy = pad_cells(sp)
    tgt = [set(), set()]
    tax = {}
    tcen = {}
    for d in dst:
        if d[0] == "EDGE":
            _, side, ln, a0, a1 = d
            li = LAYERS.index(ln)
            for i in range(int(round(a0 / G)), int(round(a1 / G)) + 1):
                if side == "S":
                    c = (i, NY - 1 - int(round((w / 2 + 0.05) / G - 1e-6)))
                    tgt[li].add(c)
                    tax[(li,) + c] = {2}
                    tcen[(li,) + c] = (i * G, H)
                else:                              # E edge of the strip: a0..a1 are y
                    c = (NX - 1 - int(round((w / 2 + 0.05) / G - 1e-6)), i)
                    tgt[li].add(c)
                    tax[(li,) + c] = {0}
                    tcen[(li,) + c] = (SX, i * G)
        elif d[0] == "VIA":
            c = (int(round(d[1] / G)), int(round(d[2] / G)))
            for li in range(2):
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
            ok[li][c] = True
        for c in scells:
            if li in slays:
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
    goal = None
    n = 0
    while openl:
        f, g_, st = heapq.heappop(openl)
        if g_ > best.get(st, 1e18) + 1e-9:
            continue
        i, j, li, d = st
        if (i, j) in tgt[li] and d >= 0 and d in tax[(li, i, j)] and not ((i, j) in scells and li in slays):
            goal = st
            break
        n += 1
        if n > 900000:
            break
        in_src = (i, j) in scells and li in slays
        for nd in (range(8) if d < 0 else (d, (d + 1) % 8, (d - 1) % 8)):
            if d < 0 and in_src and nd not in saxes:
                continue
            if d < 0 and not in_src:
                pass
            di, dj = DIRS[nd]
            a, b_ = i + di, j + dj
            if not (0 <= a < NX and 0 <= b_ < NY) or not ok[li][a, b_]:
                continue
            if in_src and d >= 0 and nd != d:
                continue                       # leave the source pad straight along its axis
            step = (1.414 if nd % 2 else 1.0) * pref[li] + (0.3 if (d >= 0 and nd != d) else 0.0)
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
    # split into layer runs
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
            if not dst[0][0] == "EDGE":
                last = pts[-1]
                if abs(last[0] - gc[0]) < 1e-6 or abs(last[1] - gc[1]) < 1e-6 or abs(abs(last[0] - gc[0]) - abs(last[1] - gc[1])) < 1e-6:
                    pts.append(gc)
            elif dst[0][1] == "S":
                pts.append((pts[-1][0], H))
            else:
                pts.append((SX, pts[-1][1]))
        # compress collinear
        q = [pts[0]]
        for a_, b2, c2 in zip(pts, pts[1:], pts[2:]):
            v1 = (b2[0] - a_[0], b2[1] - a_[1])
            v2 = (c2[0] - b2[0], c2[1] - b2[1])
            if abs(v1[0] * v2[1] - v1[1] * v2[0]) > 1e-9 or v1[0] * v2[0] + v1[1] * v2[1] < 0:
                q.append(b2)
        q.append(pts[-1])
        if len(q) >= 2 and bl.plen(q) > 1e-6:
            t = [q[0]]
            for p_ in q[1:]:
                if math.hypot(p_[0] - t[-1][0], p_[1] - t[-1][1]) > 1e-6:
                    t.append(p_)
            if len(t) >= 2:
                for (a_, b2) in zip(t, t[1:]):          # draw segment by segment: no chamfering of grid joints
                    blk.track(net, w, [a_, b2], LAYERS[r[0][2]])
        if k < len(runs) - 1:
            blk.via(round(r[-1][0] * G, 3), round(r[-1][1] * G, 3), net)
    ROUTED.append(net)
    if dst[0][0] == "EDGE":
        return path[-1][0] * G if dst[0][1] == "S" else path[-1][1] * G
    return True


def place_via(net, x, y, keep=()):
    """via of net at the free spot nearest to (x, y); keep = pads (ref, num) whose copper it must not touch"""
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


def gvia(x, y, keep=()):
    return place_via("GND", x, y, keep)


def svia(net, x, y, keep=()):
    return place_via(net, x, y, keep)


def tie(ref, num, net=None, d=0.7):
    """pad -> own via (GND to In1, supply to In2) placed beyond the pad along the part axis"""
    p = padobj(ref, num)
    net = net or p.GetNetname()
    px, py = blk.loc(p.GetPosition())
    ox, oy = blk.loc(p.GetParent().GetPosition())
    dx, dy = px - ox, py - oy
    n_ = math.hypot(dx, dy) or 1.0
    v = place_via(net, px + dx / n_ * d, py + dy / n_ * d, keep=[(ref, num)])
    return route(net, (ref, num), [v], 0.3 if net in ("GND", "+3V3", "+1V2") else 0.2)


IFACE_NOTES = {}


def to_edge(net, src, x0, x1, w=WS, note=""):
    x = route(net, src, [("EDGE", "S", "B.Cu", x0, x1)], w)
    if x is not None:
        blk.iface(net, x, H, "B.Cu", "S", "slow", w, note)
    return x


# ---------------- routing (order matters: tight escapes first)
print("routing ...")
# QFN supply pins -> their vias (pad-wide 0.2 copper at the pin, 0.3 beyond is not possible at 0.4 pitch)
for pin, (x, y) in list(SUP_V.items()):
    v = place_via(NL.net_of("U501", pin), x, y)
    SUP_V[pin] = v[1:]
    route(NL.net_of("U501", pin), ("U501", pin), [v], 0.2)
# QFN GND pins -> EP
for pin in ("2", "26"):
    route("GND", ("U501", pin), [("U501", "49")], 0.2)
# PH strobe pins -> R411 / R407 (B) through one via each
route("/PH_STROBE_N", ("U501", "39"), [("R411", "@PH_STROBE_N")])
route("/PH_STROBE_P", ("U501", "40"), [("R407", "@PH_STROBE_P")])
# decoupling caps: supply pad -> pin via, GND pad -> GND via
DEC = {"C506": "36", "C502": "37", "C504": "1", "C501": "12", "C505": "25"}
for c, pin in DEC.items():
    net = NL.net_of("U501", pin)
    route(net, (c, "@" + net), [("VIA", *SUP_V[pin])], 0.3)
    tie(c, "@GND")
# taps: fixed order along the S edge
TAPX = {i: 8.3 + 0.62 * i for i in range(16)}
TAPPIN = {NL.net_of("U501", p): p for p in [str(k) for k in list(range(9, 12)) + list(range(13, 25)) + [27]]}
for i in list(range(3, 15)) + [0, 1, 2, 15]:
    net = f"/TAP{i}"
    to_edge(net, ("U501", TAPPIN[net]), TAPX[i] - 0.2, TAPX[i] + 0.2, note=f"U501.{TAPPIN[net]}")
print("taps done")

# ---------------- clock generator
route("Net-(U502-CLK0)", ("U502", "10"), [("R508", "@Net-(U502-CLK0)")])
route("Net-(U502-CLK1)", ("U502", "9"), [("R509", "@Net-(U502-CLK1)")])
route("Net-(U502-CLK2)", ("U502", "6"), [("R510", "@Net-(U502-CLK2)")])
route("Net-(U502-XA)", ("U502", "2"), [("Y501", "3")])
route("Net-(U502-XB)", ("U502", "3"), [("Y501", "1")])
route("/fpga_clock/FPGA_CLK", ("R508", "@FPGA_CLK"), [("U501", "33")])
route("/fpga_clock/CLK2_FPGA", ("R510", "@CLK2_FPGA"), [("U501", "34")])
route("+3V3", ("U502", "7"), [("C508", "@+3V3")], 0.3)
route("+3V3", ("U502", "1"), [("C509", "@+3V3")], 0.3)
for ref, num in (("C508", "@+3V3"), ("C509", "@+3V3"), ("C508", "@GND"), ("C509", "@GND"), ("U502", "8"),
                 ("Y501", "2"), ("Y501", "4"), ("C510", "@+3V3"), ("C510", "@GND"), ("C503", "@+1V2"), ("C503", "@GND"),
                 ("C507", "@+3V3"), ("C507", "@GND")):
    tie(ref, num)
# ---------------- JTAG / DBG2 to J501
route("/fpga_clock/JTAG_TCK", ("U501", "3"), [("J501", "7")])
route("/fpga_clock/JTAG_TCK", ("R507", "@JTAG_TCK"), [("U501", "3"), ("J501", "7")])
tie("R507", "@GND")
for pin, jp in (("4", "9"), ("5", "11"), ("7", "13"), ("6", "5")):
    route(NL.net_of("U501", pin), ("U501", pin), [("J501", jp)])
# ---------------- configuration pins
for pin, r in (("42", "R506"), ("43", "R505"), ("44", "R504"), ("45", "R503"), ("46", "R502"), ("48", "R501")):
    net = NL.net_of("U501", pin)
    route(net, ("U501", pin), [(r, "@" + net)])
    other = [p.GetNumber() for p in blk.fps[r].Pads() if p.GetNetname() != net][0]
    tie(r, other)
route("/fpga_clock/JTAGSEL_N", ("JP501", "1"), [("U501", "44"), ("R504", "@JTAGSEL_N")])
tie("JP501", "2")
to_edge("/COARSE", ("U501", "47"), 2.0, 8.0, note="U501.47 (SN65LVDS2 in the phase block)")
to_edge("/FPGA_DONE", ("R502", "@FPGA_DONE"), 2.0, 8.0, note="R502 4.7k pull-up; to the MCU")
to_edge("/FPGA_RECONFIG", ("R501", "@FPGA_RECONFIG"), 2.0, 8.0, note="R501 4.7k pull-up; MCU open-drain")
to_edge("/ADC_TRIG", ("U501", "41"), 2.0, 8.0, note="U501.41 -> STM32 PB11")
# ---------------- SPI, I2C, MCU clock, J501 MCU lines
for pin in ("28", "29", "30", "31"):
    to_edge(NL.net_of("U501", pin), ("U501", pin), 18.0, 23.8, note=f"U501.{pin}")
to_edge("/MCU_CLK", ("R509", "@MCU_CLK"), 18.0, 23.8, note="MS5351M CLK1 via 33 R -> STM32 PF0")
to_edge("/I2C_SCL", ("U502", "4"), 18.0, 23.8, note="MS5351M (pull-ups in mcuif)")
to_edge("/I2C_SDA", ("U502", "5"), 18.0, 23.8, note="MS5351M")
route("Net-(J501-Pin_2)", ("J501", "2"), [("R511", "@Net-(J501-Pin_2)")])
route("Net-(J501-Pin_4)", ("J501", "4"), [("R512", "@Net-(J501-Pin_4)")])
to_edge("/HOST_RX", ("R511", "@HOST_RX"), 18.0, 23.8, note="J501.2 via R511 100 R -> STM32 PA10")
to_edge("/HOST_TX", ("R512", "@HOST_TX"), 18.0, 23.8, note="J501.4 via R512 100 R <- STM32 PA9")
for jp in ("8", "10", "12", "14"):
    to_edge(NL.net_of("J501", jp), ("J501", jp), 18.0, 23.8, note=f"J501.{jp} -> STM32")
x = route("VBUS", ("J501", "1"), [("EDGE", "E", "B.Cu", 0.5, 6.5)], 0.4)
if x is not None:
    blk.iface("VBUS", SX, x, "B.Cu", "E", "supply", 0.4, "J501.1 (5 V to the cable); from the power block")
blk.iface("+3V3", 0, 0, "In2.Cu", "-", "supply", None, "via pairs at the caps; J501.3 THT on the In2 +3V3 region")
blk.iface("+1V2", 0, 0, "In2.Cu", "-", "supply", None, "vias at U501.12 / .37 and C501-C503: In2 +1V2 island under U501")
print("failed:", FAILED)
blk.edge_rect(0, 0, W, H, "Dwgs.User")
blk.save(HERE)
path = os.path.join(HERE, "fpga.kicad_pcb")
res = bl.check_board(path, refs=REFS, rf_widths=RF)
for k in ("clearance", "corner"):
    for e in res["details"][k][:15]:
        print("   ", k, e)
bl.render(path, os.path.join(SCR, "fpga_t.png"), layers=("F.Cu", "B.Cu", "F.Fab", "Dwgs.User"), tmpdir=SCR)
