#!/usr/bin/env python3
"""PSTROBE block of the scope-fe board: two phase-strobe chains (A from PH_STROBE_P, K from PH_STROBE_N), each
47 R -> 100 nF -> TRF37D73 (bias tee per sim/bias_tee) -> 100 nF -> 10 dB pi pad (100 / 68 / 100 R) -> 100 nF ->
GVA-84+ (VBUS through bead + 2.2 uH) -> 100 nF -> launch node PSTRB_A/K with the 80 ps shorted stub TL402/TL403
(NT402/NT403, two GND vias) and the DNP BAT15 clamp -> 50 R output to the phase block (tap 0).

Both chains come from chain(s): s = +1 chain A (north, local y 0-8.5), s = -1 chain K, mirrored about the
tap axis y = 11.5 (board 37.5).  Every two-terminal part, track, via, stub and keep-out is mirrored; the two
ICs (TRF37D73 WSON, GVA-84+ SOT-89) cannot be mirrored (chiral pin-outs): they keep rotation 0 / 90 in both
chains, with their RF pins on the mirrored line points (identical electrical path).
Run: cd blocks/pstrobe && python3 gen_pstrobe.py
"""
import sys, os, math
sys.path.insert(0, "../..")
os.environ["BL_STACKUP"] = "6L"            # phase two: native 6-layer block (JLC06161H-3313, RULES rule 10)
import boardlib as bl
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board6/pstrobe"
os.makedirs(SCR, exist_ok=True)
BW, BH, AX = 17.0, 25.0, 12.5            # FLOORPLAN 17 x 23 at (9.5, 26.0), grown 1 mm N and S: board (9.5, 25.0)
CORR = (9.5, 15.5)                         # phase corridor (board y 34.5-40.5), not ours
blk = bl.Block("pstrobe")
nl = blk.nl
W = bl.W50                                 # 6L: 0.16 mm (50.2 R, L1 over L2 0.0994 mm 3313)
assert bl.STACKUP_NAME == "6L" and abs(W - 0.16) < 1e-9, W
W_PWR, W_GND = 0.5, 0.4
N = bl.net_of
RFPOLY = []
RF = {}


def bplace(ref, x, y, rot=0, side="F"):
    """local helper: Block.place(side="B") segfaults in pcbnew 7.0.11 (flip before Board.Add): place, then flip"""
    fp = blk.place(ref, x, y, rot, "F")
    if side == "B":
        fp.Flip(blk.P(x, y), True)
        fp.Reference().SetLayer(pcbnew.B_Fab)
    return fp


def two(ref, x, y, first, net, side="F"):
    """2-terminal part centred at (x, y); the pad on `net` lies to the `first` side (W/E/N/S)"""
    net = bl.canon(net) if not net.startswith("Net-") else net
    for rot in ((0, 180) if first in "WE" else (90, 270)):
        fp = bplace(ref, x, y, rot, side)
        px, py = blk.pad(ref, "@" + net)
        ok = {"W": px < x - 1e-3, "E": px > x + 1e-3, "N": py < y - 1e-3, "S": py > y + 1e-3}[first]
        if ok:
            return fp
        blk.b.Remove(fp)
        del blk.fps[ref]
    raise ValueError((ref, net))


def gv(x, y):
    blk.via(x, y, "GND")


def rf(net, pts, name, w=W, ch=0.2):
    q = blk.track(net, w, pts, name=name, z=50, ch=ch)
    RFPOLY.append((q, w))
    RF[blk.nl.canon(net) if not net.startswith("Net-") else net] = w
    return q


# chain geometry (chain-A frame, local mm; K = mirror about AX).  Courtyards (KiCad library) never overlap:
# 0402 1.86 x 0.94, WSON-8 3.2 x 2.5, SOT-89 5.0 x 5.1 (tab side 4.2 from the line), SOD-323 3.2 x 1.9.
YL = 4.40              # RF line (GVA-84+ tab copper reaches YL - 3.95, its courtyard YL - 4.2)
YS = YL + 4.85         # stub lane: K stub edge 0.72 (2 w) from the GVA tab copper of chain K
X_IN = 0.52            # input leg column (iface on the N / S edge); R407 and C412 sit on the leg
XT = 2.74              # TRF37D73 centre x (courtyard touches the leg parts' courtyards)
X1 = XT + 1.60 + 0.47  # TRF bias bead on the corner, C416 below it (first column of the U-folded pi pad)
YR = YL + 2.55         # U row: R410 series, R408 / R409 shunts inside the U
X2 = X1 + 2.94         # second column: C417
XO = 14.60             # output column: GVA bead on the corner, C421 below, launch node at YS
XG = XO - 1.47 - 1.50  # GVA centre x (pin 3 at XO - 1.47: courtyard edge = bead courtyard edge)
XD = XO + 0.47 + 0.95  # clamp column (vertical SOD-323 beside C421)
L_STUB = 80.0 / bl.PS_MM50


def snap(ref, net, x=None, y=None):
    """move a placed part so that its pad on net lands exactly at x / y"""
    px, py = blk.pad(ref, "@" + net)
    blk.fps[ref].Move(pcbnew.VECTOR2I(bl.mm(0 if x is None else x - px), bl.mm(0 if y is None else y - py)))


def chain(s):
    A = s > 0
    my = (lambda y: y) if A else (lambda y: 2 * AX - y)
    NS = (lambda d: d) if A else (lambda d: {"N": "S", "S": "N", "W": "W", "E": "E"}[d])
    R_IN, C_IN, U, FB, L, RD, CC, C1N, C100, C10U, CX, C_O, RS1, RSER, RS2, C_I, G, FBG, LG, CG1, CG2, CG10, C_OUT, \
        D, TL, NT, TP1, TP2 = (
            ("R407", "C412", "U403", "FB403", "L403", "R417", "C434", "C415", "C414", "C413", "C432", "C416", "R408",
             "R410", "R409", "C417", "U404", "FB404", "L404", "C418", "C419", "C420", "C421", "D402", "TL402", "NT402",
             "TP403", "TP404") if A else
            ("R411", "C422", "U405", "FB405", "L405", "R418", "C435", "C425", "C424", "C423", "C433", "C426", "R412",
             "R414", "R413", "C427", "U406", "FB406", "L406", "C428", "C429", "C430", "C431", "D403", "TL403", "NT403",
             "TP405", "TP406"))
    PIN = "/PH_STROBE_P" if A else "/PH_STROBE_N"
    OUT = "/PSTRB_A" if A else "/PSTRB_K"
    n_in1, n_rfin, n_rfout, n_bias = N(R_IN, 2), N(U, 2), N(U, 7), N(FB, 2)
    n_padin, n_padout, n_gin, n_gout, n_gbias, n_stub = N(C_O, 2), N(C_I, 1), N(G, 1), N(G, 3), N(FBG, 2), N(NT, 1)
    yl, ys, yr = my(YL), my(YS), my(YR)
    # ---------------------------------------------------------------- RF parts
    two(C_IN, X_IN, my(YL - 1.00), NS("S"), n_rfin)       # input leg: C412 (pad 2 just above the line)
    two(R_IN, X_IN, my(YL - 2.87), NS("N"), PIN)         # 47 R above it, courtyards touching
    bplace(U, XT, yl + 0.25, 0)                          # pins 2 / 7 on the line (both chains: rotation 0)
    assert abs(blk.pad(U, "2")[1] - yl) < 1e-6
    two(FB, X1, yl - s * 0.48, NS("N"), n_bias)          # bead pad 1 centred on the corner, body away from the stub
    snap(FB, n_rfout, y=yl)
    two(C_O, X1, my(YL + 1.40), NS("N"), n_rfout)        # DC block down the first column
    two(RSER, X1 + 1.47, yr, "W", n_padin)               # pi pad series 68 R on the U row
    xa_, xb_ = blk.pad(RSER, "@" + n_padin)[0], blk.pad(RSER, "@" + n_padout)[0]
    two(RS1, xa_, my(YR - 1.42), NS("S"), n_padin)       # shunts above the series pads, inside the U
    two(RS2, xb_, my(YR - 1.42), NS("S"), n_padout)
    two(C_I, X2, my(YL + 1.40), NS("S"), n_padout)       # DC block up the second column
    bplace(G, XG, yl - 1.95, 90)                         # GVA-84+: pin 1 W, pin 3 E on the line, tab north
    assert abs(blk.pad(G, "1")[1] - yl) < 1e-6 and blk.pad(G, "1")[0] < XG
    two(FBG, XO, yl - s * 0.48, NS("N"), n_gbias)        # GVA bead: pad 1 centred on the corner, body away
    snap(FBG, n_gout, y=yl)
    two(C_OUT, XO, my(YL + 1.40), NS("N"), n_gout)
    two(D, XD, my(YS - 1.35), NS("S"), OUT)              # DNP clamp: cathode pad on the output row's edge
    # ---------------------------------------------------------------- RF tracks
    y0 = 0.0 if A else BH
    rf(PIN, [(X_IN, y0), (R_IN, "@" + PIN)], f"{PIN[1:]} input")
    rf(n_in1, [(R_IN, "@" + n_in1), (C_IN, "@" + n_in1)], f"{U} in 1")
    rf(n_rfin, [(C_IN, "@" + n_rfin), (X_IN, yl), (U, "2")], f"{U} RFIN")
    rf(n_rfout, [(U, "7"), (X1, yl)], f"{U} RFOUT")
    rf(n_rfout, [(X1, yl), (C_O, "@" + n_rfout)], f"{U} RFOUT b")   # 90-degree joint inside the bead pad
    rf(n_padin, [(C_O, "@" + n_padin), (X1, yr), (RSER, "@" + n_padin)], f"{U} pad in", ch=0.3)
    rf(n_padin, [(RSER, "@" + n_padin), (RS1, "@" + n_padin)], f"{U} shunt 1")
    rf(n_padout, [(RSER, "@" + n_padout), (X2, yr), (C_I, "@" + n_padout)], f"{U} pad out", ch=0.3)
    rf(n_padout, [(RSER, "@" + n_padout), (RS2, "@" + n_padout)], f"{U} shunt 2")
    rf(n_gin, [(C_I, "@" + n_gin), (X2, yl), (G, "1")], f"{G} IN", ch=0.3)
    rf(n_gout, [(G, "3"), (XO, yl)], f"{G} OUT")
    rf(n_gout, [(XO, yl), (C_OUT, "@" + n_gout)], f"{G} OUT b")      # joint inside the bead pad
    # launch node = a T at (XO, ys): drop from C421 north, stub west, output east (6L: a 0.3 chamfer at the node
    # would leave the 0.16 mm stub start 0.21 mm off the line copper, i.e. disconnected)
    rf(OUT, [(C_OUT, "@" + OUT), (XO, ys)], f"{OUT[1:]} drop")
    rf(OUT, [(XO, ys), (BW - 0.5, ys), (BW, my(YS + 0.5))], f"{OUT[1:]} output", ch=0.3)
    dx_, dy_ = blk.pad(D, "@" + OUT)
    RFPOLY.append((blk.track(OUT, W, [(dx_, dy_), (dx_, ys)]), W))
    q_st, l_st = blk.tline(TL, [(XO, ys), (XO - L_STUB, ys)], W)
    RFPOLY.append((q_st, W))
    RF[OUT] = W
    # stub short: NT pad 1 on the stub end, pad 2 -> two GND vias towards the line.  6L: the 80 ps stub is
    # 0.30 mm longer (5.925 ps/mm), so the net tie stands across the stub (pad 2 towards the line, x 0.6-1.6 is
    # free between the input leg and U403) instead of in-line (that put pad 2 / the vias off the block edge)
    xe = XO - L_STUB
    two(NT, xe, my(YS - 0.5), NS("S"), n_stub)
    assert max(abs(a - b) for a, b in zip(blk.pad(NT, "@" + n_stub), (xe, ys))) < 1e-6
    gx, gy = blk.pad(NT, "2")
    blk.track("GND", W_GND, [(gx, gy), (gx, my(YS - 2.32))])
    gv(gx, my(YS - 1.64))
    gv(gx, my(YS - 2.32))
    # clamp GND -> via beyond its pad
    x, y = blk.pad(D, "@GND")
    blk.track("GND", W_GND, [(x, y), (x, y - s * 0.62)])
    gv(x, y - s * 0.62)
    for r in (RS1, RS2):                                 # shunt GND vias at the line level inside the U
        x, y = blk.pad(r, "@GND")
        blk.track("GND", W_GND, [(x, y), (x, yl)])
        gv(x, yl)
    # ---------------------------------------------------------------- TRF GND pins -> EP, EP vias
    xu, yu = blk.loc(blk.fps[U].GetPosition())
    for pn in ("3", "4", "5", "6", "8"):
        x, y = blk.pad(U, pn)
        blk.track("GND", 0.25, [(x, y), (xu, y)])
    for dy in (-0.55, 0.0, 0.55):
        gv(xu, yu + dy)
    # ---------------------------------------------------------------- TRF VCC (pin 1 is north in both chains)
    p1 = blk.pad(U, "1")
    yc = (yu - 1.25) - 0.95
    two(C1N, p1[0], yc, "S", "+3V3")
    two(C100, p1[0] + 0.96, yc, "S", "+3V3")
    c1, c2 = blk.pad(C1N, "@+3V3"), blk.pad(C100, "@+3V3")
    blk.track("+3V3", 0.25, [p1, c1])
    vx = c2[0] + 0.85
    va, vb = (vx, c2[1]), (vx, c2[1] - 0.75)
    blk.track("+3V3", W_PWR, [c1, c2, va, vb])
    blk.track("+3V3", W_PWR, [va, vb], layer="B.Cu")
    for v in (va, vb):
        blk.via(*v, "+3V3")
    gvs = []
    for c in (C1N, C100):
        x, y = blk.pad(c, "@GND")
        blk.track("GND", W_GND, [(x, y), (x, y - 0.55)])
        gv(x, y - 0.55)
        gvs.append((x, y - 0.55))
    # 10 uF on B.Cu under the pin-1 caps (GND pad over the two GND vias), spare 100 nF beside it
    two(C10U, (gvs[0][0] + gvs[1][0]) / 2, yc, "S", "+3V3", side="B")
    snap(C10U, "GND", y=gvs[0][1] - 0.15)
    ct = blk.pad(C10U, "@+3V3")
    blk.track("+3V3", W_PWR, [ct, (va[0] - abs(ct[1] - va[1]), ct[1]), va], layer="B.Cu")
    two(CX, 0.60, yc - 0.15, "S", "+3V3", side="B")
    cxp, cxg = blk.pad(CX, "@+3V3"), blk.pad(CX, "@GND")
    blk.track("+3V3", 0.4, [cxp, (cxp[0], ct[1]), ct], layer="B.Cu", ch=0.06)
    gt = blk.pad(C10U, "@GND")
    blk.track("GND", 0.4, [cxg, (cxg[0], gt[1]), gt], layer="B.Cu")
    # ---------------------------------------------------------------- TRF bias tee on B.Cu (straight chain)
    pb = blk.pad(FB, "2")
    yt = my(YL - 1.80)
    blk.track(n_bias, 0.5, [pb, (pb[0], yt)])
    blk.via(pb[0], yt, n_bias)
    two(L, pb[0] + 1.40, yt, "W", n_bias, side="B")      # 1210 pad 1 over the via
    lc = blk.pad(L, "@+3V3")
    two(CC, lc[0] + 1.85, yt, "W", "+3V3", side="B")      # cold-pad 100 nF along the chain (courtyards touch)
    cc = blk.pad(CC, "@+3V3")
    blk.track("+3V3", 0.64, [lc, cc], layer="B.Cu")
    g = blk.pad(CC, "@GND")
    blk.track("GND", W_GND, [g, (g[0], g[1] + s * 0.65)], layer="B.Cu")
    gv(g[0], g[1] + s * 0.65)
    for d in (-0.75, 0.75):                               # +3V3 enters through the capacitor pad
        blk.via(cc[0], cc[1] + d, "+3V3")
    blk.track("+3V3", 0.56, [(cc[0], cc[1] - 0.75), (cc[0], cc[1] + 0.75)], layer="B.Cu")
    two(RD, pb[0] + 1.40, my(0.54), "W", n_bias, side="B")  # 1 k beside the 1210 (outer side)
    r1, r2 = blk.pad(RD, "@" + n_bias), blk.pad(RD, "@+3V3")
    l1 = blk.pad(L, "@" + n_bias)
    blk.track(n_bias, 0.4, [r1, (l1[0] + 0.35, r1[1]), (l1[0], r1[1] + s * 0.35), l1], layer="B.Cu")
    blk.track("+3V3", 0.4, [r2, (lc[0] - 0.35, r2[1]), (lc[0], r2[1] + s * 0.35), lc], layer="B.Cu")
    bplace(TP1, pb[0], my(YL - 1.80 + 1.58 + 1.01), 0, "B")   # test point below the 1210
    blk.track(n_bias, 0.4, [l1, blk.pad(TP1, "1")], layer="B.Cu")
    # ---------------------------------------------------------------- GVA GND tab vias
    xg_, yg_ = blk.loc(blk.fps[G].GetPosition())
    for dx in (-0.45, 0.45):
        for dy in (-1.2, 0.0):
            gv(xg_ + dx, yg_ + dy)
    # ---------------------------------------------------------------- GVA bias tee on B.Cu (VBUS)
    pg = blk.pad(FBG, "2")
    yv = my(YL - 1.55)
    blk.track(n_gbias, 0.5, [pg, (XO, yv)])
    blk.via(XO, yv, n_gbias)
    two(LG, XO, my(YL - 1.55 - 1.062), NS("S"), n_gbias, side="B")   # 2.2 uH straight on from the bead via
    snap(LG, n_gbias, y=yv)
    lv = blk.pad(LG, "@VBUS")
    two(CG1, XO - 0.85 - 0.95, lv[1], "E", "VBUS", side="B")       # cold-pad 1 nF across the VBUS pad
    c1v = blk.pad(CG1, "@VBUS")
    blk.track("VBUS", 0.64, [lv, c1v], layer="B.Cu")
    g = blk.pad(CG1, "@GND")
    gv(*g)                                                         # GND via in the pad (under the GVA tab)
    for d in (0.62, 1.32):                                         # VBUS enters through the capacitor pad
        blk.via(c1v[0], c1v[1] + s * d, "VBUS")
    blk.track("VBUS", 0.5, [c1v, (c1v[0], c1v[1] + s * 1.32)], layer="B.Cu")
    bplace(TP2, XO, my(4.56), 0, "B")
    blk.track(n_gbias, 0.4, [(XO, yv), blk.pad(TP2, "1")], layer="B.Cu")
    # VBUS bulk: 10 uF 0805 + 100 nF on B.Cu below the GVA, own via pair and GND via
    two(CG10, 11.25, my(7.00), "W", "VBUS", side="B")
    two(CG2, 11.25, my(7.00 - 0.98 - 0.47), "W", "VBUS", side="B")
    p10, g10 = blk.pad(CG10, "@VBUS"), blk.pad(CG10, "@GND")
    p2, g2 = blk.pad(CG2, "@VBUS"), blk.pad(CG2, "@GND")
    for d in (-0.40, 0.40):
        blk.via(p10[0] - 0.90, p10[1] + d, "VBUS")
    blk.track("VBUS", 0.6, [(p10[0] - 0.90, p10[1] - 0.40), (p10[0] - 0.90, p10[1] + 0.40)], layer="B.Cu")
    blk.track("VBUS", 0.6, [(p10[0] - 0.90, p10[1]), p10], layer="B.Cu")
    blk.track("VBUS", 0.4, [p2, (p10[0], p2[1]), p10], layer="B.Cu", ch=0.12)
    blk.track("GND", 0.4, [g2, (g10[0], g2[1]), g10], layer="B.Cu", ch=0.12)
    blk.track("GND", W_GND, [g10, (g10[0] + 0.60, g10[1])], layer="B.Cu")
    gv(g10[0] + 0.60, g10[1])
    return {"stub": l_st, "out": blk.route_len(f"{OUT[1:]} drop") + blk.route_len(f"{OUT[1:]} output"), "in": blk.route_len(f"{PIN[1:]} input")}


RES = {"A": chain(+1), "K": chain(-1)}

# ============================================================================= pours, keep-outs
IN = 0.15
REG = {"A": bl.rect_pts(IN, IN, BW - IN, CORR[0] - IN), "K": bl.rect_pts(IN, CORR[1] + IN, BW - IN, BH - IN)}
for r in REG.values():
    blk.zone("GND", ["In1.Cu"], r, clearance=0.2, prio=0)
    blk.zone("GND", ["F.Cu"], r, clearance=0.25, prio=0)
    blk.zone("GND", ["B.Cu"], r, clearance=0.25, prio=0)
for q, w in RFPOLY:
    blk.rf_keepout(q, w, gap=2 * w + 0.03)

# ============================================================================= 6L pad compensation
# (same method as blocks/analog) pF/mm from boardlib.microstrip (mask corrected): L2 at H2 (3313, er 4.1); where
# L2 is cut under a pad the reference is L3 (GND pour, 0.565 mm deeper, core er ~4.5).  Every in-line RF pad
# whose excess C over L2 (pad vs. the 0.16 mm line over the pad length) exceeds 30 fF gets an L2 cut of the pad
# size; L3 keeps its GND pour under it with a no-track / no-via rule area (no bias line under an RF pad).
H2 = bl.STACKUPS["6L"]["H"]
H3 = H2 + 0.0152 + 0.55
ER_DEEP = 4.5
C_EXCESS_MAX = 0.030


def c_mm(w, h=H2):
    """pF per mm of a w-wide strip over a plane h below"""
    z, ee = bl.microstrip(w, h=h, er=bl.STACKUPS["6L"]["ER"] if h <= H2 + 1e-6 else ER_DEEP)
    return math.sqrt(ee) / (bl.C0 * z)


def _pad_axis(pd, net):
    """axis (0 = x, 1 = y) of the RF track that enters the pad; None for the TLine footprints' own pads"""
    if pd.GetParent().GetReference().startswith("TL"):
        return None
    for t in blk.b.GetTracks():
        if t.GetNetname() != net or isinstance(t, pcbnew.PCB_VIA) or t.GetLayer() != pcbnew.F_Cu:
            continue
        for e, o in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
            if pd.HitTest(e) or t.HitTest(pd.GetPosition()):
                a, b_ = blk.loc(e), blk.loc(o)
                return 0 if abs(b_[0] - a[0]) >= abs(b_[1] - a[1]) else 1
    return 0                                     # NT402 / NT403 pad 1: the stub enters along x


PADCOMP = []
for f_ in blk.fps.values():
    for pd in f_.Pads():
        net_ = pd.GetNetname()
        if net_ not in RF or not pd.IsOnLayer(pcbnew.F_Cu):
            continue
        ax = _pad_axis(pd, net_)
        if ax is None:
            continue
        bb = pd.GetBoundingBox()
        dims = (pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight()))
        along, across = dims[ax], dims[1 - ax]
        cx, cy = blk.loc(pd.GetPosition())
        c_line = c_mm(W) * along
        ex2 = c_mm(across) * along - c_line
        cut = ex2 > C_EXCESS_MAX
        if cut:
            r_ = bl.rect_pts(cx - dims[0] / 2, cy - dims[1] / 2, cx + dims[0] / 2, cy + dims[1] / 2)
            blk.keepout(r_, ("In1.Cu",))
            blk.keepout(r_, ("In2.Cu",), tracks=True, vias=True).SetDoNotAllowCopperPour(False)
        PADCOMP.append((f"{f_.GetReference()}.{pd.GetNumber()}", across, along, ex2 * 1e3,
                        "L2 cut" if cut else "-", ((c_mm(across, H3) * along - c_line) if cut else ex2) * 1e3))

# ============================================================================= interfaces, outline
blk.iface("PH_STROBE_P", X_IN, 0.0, "F.Cu", "N", "pair", W, "chain A input, R407 47 R here; FPGA U501")
blk.iface("PH_STROBE_N", X_IN, BH, "F.Cu", "S", "pair", W, "chain K input (mirror), R411 47 R here; match P/N")
blk.iface("PSTRB_A", BW, 9.75, "F.Cu", "E", "rf50", W, "to phase tap 0 (phase iface 26.5 / 34.75 board)")
blk.iface("PSTRB_K", BW, 15.25, "F.Cu", "E", "rf50", W, "to phase tap 0 (phase iface 26.5 / 40.25 board)")
blk.iface("+3V3", 0, 0, "In3.Cu", "-", "supply", None, "TRF VCC and bias tees: via pairs, L4 (In3) x 0-12")
blk.iface("VBUS", 0, 0, "In3.Cu", "-", "supply", None, "GVA-84+ tees: via pairs at C418 / C428, L4 (In3) x 10-15")
blk.edge_rect(0, 0, BW, BH, layer="Dwgs.User")
blk.line(0, CORR[0], BW, CORR[0], layer="Dwgs.User")
blk.line(0, CORR[1], BW, CORR[1], layer="Dwgs.User")
blk.text("PSTROBE A", 6.0, 7.6, 0.4, "F.Fab")
blk.text("PSTROBE K", 6.0, 17.4, 0.4, "F.Fab")
for fp_ in blk.fps.values():                 # reference designators hidden on Fab (no room for 0.8 mm silk text)
    fab = pcbnew.B_Fab if fp_.GetLayer() == pcbnew.B_Cu else pcbnew.F_Fab
    for t_ in (fp_.Reference(), fp_.Value()):
        t_.SetLayer(fab)
        t_.SetTextSize(pcbnew.VECTOR2I(bl.mm(0.3), bl.mm(0.3)))
        t_.SetTextThickness(bl.mm(0.05))
    for g_ in fp_.GraphicalItems():           # the library's ${REFERENCE} copy on Fab
        if g_.GetClass() in ("FP_TEXT", "PCB_TEXT") and g_.GetLayer() in (pcbnew.F_Fab, pcbnew.B_Fab):
            g_.SetTextSize(pcbnew.VECTOR2I(bl.mm(0.3), bl.mm(0.3)))
            g_.SetTextThickness(bl.mm(0.05))
out = blk.save(HERE)

# ============================================================================= tables
print(f"block {BW} x {BH} mm at board (9.5, 25.0); lines at local y {YL} / {2 * AX - YL}")
print(f"{'route':28s} {'w':>5s} {'mm':>7s} {'ps':>6s}")
for nm in blk.routes:
    if blk.routes[nm]["z"]:
        L_ = blk.route_len(nm)
        print(f"{nm:28s} {blk.routes[nm]['width']:5.2f} {L_:7.3f} {L_ * bl.PS_MM50:6.1f}")
for k, r in RES.items():
    print(f"chain {k}: stub {r['stub']:.3f} mm = {r['stub'] * bl.PS_MM50:.1f} ps; output (C421/C431 pad -> edge) "
          f"{r['out']:.3f} mm; input (edge -> 47 R) {r['in']:.3f} mm")
print("impedance (JLC06161H-3313, L1 over L2 h 0.0994 mm er 4.1, mask corrected; L6 over L5 identical)")
for z_ in (50,):
    w_ = bl.width_for_6l(z_)
    print(f"  {z_:3d} R: w {w_:.3f} mm (drawn {bl.r01(w_):.2f}: {bl.microstrip_6l(bl.r01(w_))[0]:.1f} R)")
for w_ in (0.10, W, 0.25, 0.36, 0.5):
    z_, ee_ = bl.microstrip_6l(w_)
    print(f"  w {w_:.2f} mm: Z0 {z_:5.1f} R, eps_eff {ee_:.3f}, {math.sqrt(ee_) / bl.C0:.3f} ps/mm, "
          f"{c_mm(w_) * 1e3:.0f} fF/mm")
print(f"pad compensation (excess C vs. the {W} mm line over the pad length; L2 cut if > {C_EXCESS_MAX * 1e3:.0f} fF)")
print(f"  {'pad':10s} {'across':>6s} {'along':>6s} {'over L2 fF':>10s}  action  {'after fF':>8s}")
for row in sorted(PADCOMP):
    print(f"  {row[0]:10s} {row[1]:6.2f} {row[2]:6.2f} {row[3]:10.1f}  {row[4]:6s}  {row[5]:8.1f}")
print("intended vs actual (6L ps/mm %.3f)" % bl.PS_MM50)
for k, r in RES.items():
    print(f"  chain {k}: stub target 80.0 ps = {80.0 / bl.PS_MM50:.3f} mm, drawn {r['stub']:.3f} mm = "
          f"{r['stub'] * bl.PS_MM50:.2f} ps; output target A = K, drawn {r['out']:.3f} mm = {r['out'] * bl.PS_MM50:.2f} ps")
dA = abs(RES["A"]["out"] - RES["K"]["out"])
print(f"A/K output mismatch {dA * 1e3:.1f} um")
assert dA < 0.05

# ============================================================================= checks
import floorplan as fpl
mem = fpl.membership(nl)
ANALOG_TOOK = ("C402", "C403", "C404", "C407", "C408", "C409")
REFS = sorted(r for r, b_ in mem.items() if b_ == "pstrobe" and r not in ANALOG_TOOK)
res = bl.check_board(out, refs=REFS, rf_widths=RF, verbose=12)


def courtyard_overlaps(path, min_area=0.005):
    """local helper: pairwise intersection of the library courtyards (F.CrtYd / B.CrtYd) per board side"""
    b_ = pcbnew.LoadBoard(path)
    fps = list(b_.GetFootprints())
    cy = []
    for f_ in fps:
        f_.BuildCourtyardCaches()
        for lay in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            p_ = f_.GetCourtyard(lay)
            if p_.OutlineCount():
                cy.append((f_.GetReference(), lay, p_))
    hits = []
    for i in range(len(cy)):
        for j in range(i + 1, len(cy)):
            (ra, la, pa), (rb, lb, pb_) = cy[i], cy[j]
            if la != lb or not pa.BBox().Intersects(pb_.BBox()):
                continue
            x_ = pa.CloneDropTriangulation() if hasattr(pa, "CloneDropTriangulation") else pcbnew.SHAPE_POLY_SET(pa)
            x_.BooleanIntersection(pb_, pcbnew.SHAPE_POLY_SET.PM_FAST)
            ar = x_.Area() / 1e12
            if ar > min_area:
                hits.append((ra, rb, round(ar, 3)))
    nocy = [f_.GetReference() for f_ in fps if not any(c[0] == f_.GetReference() for c in cy)]
    print(f"courtyard overlaps (> {min_area} mm2): {len(hits)}  {hits[:20]}   (no courtyard: {nocy})")
    return hits


CY_HITS = courtyard_overlaps(out)

_bb = pcbnew.LoadBoard(out).ComputeBoundingBox(False)
_ox, _oy = pcbnew.ToMM(_bb.GetX()), pcbnew.ToMM(_bb.GetY())


def render(png, layers, crop):
    """local helper: kicad-cli page-size-mode 2 puts the SVG origin at the board bbox; shift the crop (local mm)"""
    x0, y0, x1, y1 = crop
    o = (100.0 - _ox, 100.0 - _oy)
    bl.render(out, png, layers, crop=(x0 + o[0], y0 + o[1], x1 + o[0], y1 + o[1]), tmpdir=SCR)


if "--norender" not in sys.argv:
    lay = ("F.Cu", "B.Cu", "F.SilkS", "F.Fab", "Dwgs.User")
    render(os.path.join(HERE, "pstrobe.png"), lay, (-0.5, -0.5, 17.5, 25.5))
    render(os.path.join(HERE, "pstrobe_detail.png"), lay, (-0.3, -0.3, 9.3, 9.8))
    render(os.path.join(HERE, "pstrobe_detail_L1L2.png"), ("F.Cu", "In1.Cu", "F.Fab", "Dwgs.User"),
           (-0.3, 3.0, 17.3, 10.0))
    render(os.path.join(SCR, "pstrobe_f.png"), ("F.Cu", "F.Fab", "Dwgs.User"), (-0.5, -0.5, 17.5, 25.5))
    render(os.path.join(SCR, "pstrobe_b.png"), ("B.Cu", "B.Fab", "Dwgs.User"), (-0.5, -0.5, 17.5, 25.5))
