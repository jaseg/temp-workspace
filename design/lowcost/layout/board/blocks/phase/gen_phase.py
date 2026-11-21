#!/usr/bin/env python3
"""Block "phase" of the scope-fe board: trigger front chain (folded) + 16-tap phase delay line.

Netlist-true (every part placed with Block.place: refs, values, footprints and pad nets come from
kicad/export/scope-fe.net).  Geometry of the tap cell, the S meander, the symmetric summing node, the
comparator routing and the corrected bias tee is taken unchanged from layout/phase_trigger/gen_phase_trigger.py
(same formulas, same offsets); only the references / nets follow the schematic and the front chain is folded
into the west part of the block (x 0-9.5 mm, full height) because the corridor between the pstrobe chains
(x 9.5-26.5, y 12-18 local) is only 6 mm high.

Block rectangle (FLOORPLAN.md): board (0, 22.5), 99.5 x 22.5 mm, rot 0, local origin = top-left.
pstrobe cut-out: local x 9.5-26.5, y 3.5-22.5 except the axis corridor y 12-18.
Run: cd blocks/phase && python3 gen_phase.py
"""
import math, os, sys, json
sys.path.insert(0, "../..")
import boardlib as bl
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
blk = bl.Block("phase")
NL = blk.nl
W50 = bl.W50
BW, BH = 99.5, 22.5

# ============================================================================= delay-line constants (fragment)
W_STR = bl.r01(bl.width_for(73.0))                     # 0.16
Z_STR = bl.microstrip(W_STR)[0]
C_PAD_STR = (bl.c_per_mm(0.56) - bl.c_per_mm(W_STR)) * 0.62
CL_STR = 0.40 + C_PAD_STR + 0.02
TD_STR = 40.0
TDU_STR = bl.solve_tdu(Z_STR, CL_STR, TD_STR)
PITCH = round(TDU_STR / bl.ps_mm(W_STR), 3)            # 4.514
TD_LIN = 70.0
W_LIN = 0.25
for _ in range(3):
    C_PAD_LIN = (bl.c_per_mm(0.45) - bl.c_per_mm(W_LIN)) * 0.70
    CL_LIN = 0.37 + C_PAD_LIN
    z_t = math.sqrt(50.0 * TD_LIN / (TD_LIN / 50.0 - CL_LIN))
    W_LIN = bl.r01(bl.width_for(z_t))                  # 0.26
Z_LIN = bl.microstrip(W_LIN)[0]
TDU_LIN = bl.solve_tdu(Z_LIN, CL_LIN, TD_LIN)
L_LIN = TDU_LIN / bl.ps_mm(W_LIN)
NT = 16
X_P3, X_P12 = 1.0, -1.0
XD = PITCH - 1.75
PAD3_HALF_X = 0.35
XU = (XD + X_P3 + PAD3_HALF_X - W_LIN / 2) / 2
E_LAND, CH_M = 0.2, 0.2


def cell_path(Y):
    return [(X_P3, 0.0), (X_P3, Y), (XU, Y), (XU, -Y), (XD, -Y), (XD, -E_LAND), (XD + E_LAND, 0.0),
            (PITCH + X_P3, 0.0)]


lo, hi = 0.3, 4.0
for _ in range(60):
    m = (lo + hi) / 2
    lo, hi = (m, hi) if bl.plen(bl.chamfer(cell_path(m), CH_M)) < L_LIN else (lo, m)
Y_M = (lo + hi) / 2
YL = math.ceil((Y_M + W_LIN / 2 + 0.3 + 0.79) / 0.05) * 0.05      # 2.75
YNODE = YL - 0.96
X_R1K, X_R22K = -1.94, -0.06
Y_RV = YL + 1.085
DX_TAP = 0.8
W_NODE, W_SIG, W_PWR, W_GND = 0.15, 0.2, 0.5, 0.4

# ============================================================================= block placement constants
AX = 15.0                                   # tap axis (board y 37.5)
X_IF_STR = 26.5                             # pstrobe east edge: 0.16 mm strobe sections start here
X0 = X_IF_STR - X_P12 + PITCH / 2           # tap 0 (D301) centre
XT = [X0 + n * PITCH for n in range(NT)]
X15 = XT[-1]
assert X15 + 1.95 <= BW, X15

RF = {}                                     # single-width RF nets for check_board
MIXED = {}                                  # name -> (net, width) for multi-width RF nets (own check)
KEEP = []                                   # (pts, w) RF polylines for pour keep-outs
CUT = []                                    # In1 cut-outs


def T(net, w, pts, layer="F.Cu", name=None, z=None, ch=0.2, rf=False):
    q = blk.track(net, w, pts, layer, name=name, z=z, ch=ch)
    if rf:
        KEEP.append((q, w))
        MIXED.setdefault(bl.canon(net) if not net.startswith("Net-") else net, set()).add(w)
    return q


def V(x, y, net):
    return blk.via(x, y, net)


def gv(x, y):
    return blk.via(x, y, "GND")


def bplace(ref, x, y, rot=0, side="F"):
    """local helper: Block.place(side="B") flips before the footprint is on the board (segfault in
    pcbnew 7.0.11), so place on F and flip after it is added"""
    fp = blk.place(ref, x, y, rot, "F")
    if side == "B":
        fp.Flip(blk.P(x, y), True)
        fp.Reference().SetLayer(pcbnew.B_Fab)
    return fp


def place2(ref, x, y, axis, first_net, side="F"):
    """2-pad part; axis 'v': pad on first_net on top (smaller y); 'h': on the left"""
    fp = bplace(ref, x, y, 90 if axis == "v" else 0, side)
    px, py = blk.pad(ref, "@" + first_net)
    ok = (py < y - 0.1) if axis == "v" else (px < x - 0.1)
    if not ok:
        fp.SetOrientationDegrees(fp.GetOrientationDegrees() + 180)
        px, py = blk.pad(ref, "@" + first_net)
        assert ((py < y - 0.1) if axis == "v" else (px < x - 0.1)), ref
    return fp


def place_cond(ref, x, y, cond, side="F"):
    fp = bplace(ref, x, y, 0, side)
    for r in (0, 90, 180, 270):
        fp.SetOrientationDegrees(r)
        pp = {p.GetNumber(): (blk.loc(p.GetPosition())[0] - x, blk.loc(p.GetPosition())[1] - y) for p in fp.Pads()}
        if cond(pp):
            return fp
    raise RuntimeError(ref)


def P(ref, n):
    return blk.pad(ref, n)


def nn(ref, pad):
    return NL.net_of(ref, pad)


# ============================================================================= tap cells (fragment geometry)
for n, x in enumerate(XT):
    d = f"D{301 + n}"
    ca, ck = f"C{314 + 2 * n}", f"C{315 + 2 * n}"
    rna, rnk, rsa, rsk = (f"R{313 + 4 * n + i}" for i in range(4))
    na, nk = nn(d, "1"), nn(d, "2")
    sm = nn(rsa, "2")
    blk.place(d, x, AX, 0)
    assert P(d, "1")[1] < AX and P(d, "3")[0] > x
    place2(ca, x + X_P12, AX - (YL - 0.48), "v", "PSTRB_A")
    place2(ck, x + X_P12, AX + (YL - 0.48), "v", nk)
    place2(rsa, x + X_R1K, AX - YL, "v", sm)
    place2(rna, x + X_R22K, AX - YL, "v", "VTAP_N")
    place2(rsk, x + X_R1K, AX + YL, "v", nk)
    place2(rnk, x + X_R22K, AX + YL, "v", nk)
    for s, node, rail in ((-1, na, "VTAP_N"), (+1, nk, "VTAP_P")):
        T(node, W_NODE, [(x + X_P12, AX + 0.65 * s), (x + X_P12, AX + YNODE * s)], ch=0)
        for xr, ref in ((X_R1K, rsa if s < 0 else rsk), (X_R22K, rna if s < 0 else rnk)):
            yi = P(ref, "@" + node)[1]
            T(node, W_NODE, [(x + X_P12, AX + YNODE * s), (x + xr, AX + YNODE * s), (x + xr, yi)], ch=0.2)
        V(x + X_R22K, AX + Y_RV * s, rail)
        T(rail, 0.3, [P(rna if s < 0 else rnk, "@" + rail), (x + X_R22K, AX + Y_RV * s)], ch=0)
        CUT.append(bl.rect_pts(x - 1.35, AX + 0.55 * s, x + 0.45, AX + (YL - 0.4) * s))
    # summing node: both 1 k outer pads -> vias -> straight B.Cu jumper; comparator tap from the jumper midpoint
    V(x + X_R1K, AX + Y_RV, sm)
    V(x + X_R1K, AX - Y_RV, sm)
    T(sm, W_SIG, [P(rsk, "@" + sm), (x + X_R1K, AX + Y_RV)], ch=0)
    T(sm, W_SIG, [P(rsa, "@" + sm), (x + X_R1K, AX - Y_RV)], ch=0)
    T(sm, W_SIG, [(x + X_R1K, AX + Y_RV), (x + X_R1K, AX - Y_RV)], layer="B.Cu", ch=0)
    T(sm, W_SIG, [(x + X_R1K, AX), (x + X_R1K - DX_TAP, AX - DX_TAP), (x + X_R1K - DX_TAP, AX - Y_RV)],
      layer="B.Cu", ch=0)
    V(x + X_R1K - DX_TAP, AX - Y_RV, sm)
    # PH_LINE meander to the next tap, strobe sections
    if n < NT - 1:
        T("Net-(D301-common)", W_LIN, [(x + px, AX + py) for px, py in cell_path(Y_M)], name=f"PH_LINE cell {n}",
          z=round(Z_LIN), ch=CH_M, rf=True)
    for s, net in ((-1, "PSTRB_A"), (+1, "PSTRB_K")):
        T(net, W_STR, [(x + X_P12 - PITCH / 2, AX + YL * s), (x + X_P12 + PITCH / 2, AX + YL * s)],
          name=f"{net} section {n}", z=73, rf=True)

# --- strobe interfaces (pstrobe east edge, the 0.16 mm sections start on the boundary)
for s, net in ((-1, "PSTRB_A"), (+1, "PSTRB_K")):
    blk.iface(net, X_IF_STR, AX + YL * s, "F.Cu", "W", "rf50", W50,
              "pstrobe output, 50 R up to the boundary, 0.16 mm (73 R) from here; equal A/K")

# --- far end: terminations (vertical, pad centred on the line, GND pad outward)
XE = X15 + X_P12 + PITCH / 2
for s, net, ref in ((-1, "PSTRB_A", "R379"), (+1, "PSTRB_K", "R378")):
    place2(ref, XE, AX + (YL + 0.51) * s, "v", net if s > 0 else "GND")
    g = P(ref, "@GND")
    gv(g[0], g[1] + 0.75 * s)
    T("GND", W_GND, [g, (g[0], g[1] + 0.75 * s)], ch=0)
XR377 = X15 + X_P3 + 0.62
place2("R377", XR377, AX + 0.51, "v", "Net-(D301-common)")
T("Net-(D301-common)", W_LIN, [P("D316", "3"), P("R377", "1")], name="PH_LINE end -> R377", z=round(Z_LIN), rf=True)
g = P("R377", "@GND")
gv(g[0], g[1] + 0.7)
T("GND", W_GND, [g, (g[0], g[1] + 0.7)], ch=0)
blk.place("TP304", XR377 - 0.05, AX - 1.25, 0)
T("Net-(D301-common)", 0.2, [P("R377", "1"), P("TP304", "1")], ch=0)

# ============================================================================= comparators COS3502 U305-U312
YC = AX - (YL + 7.0)
VTH_Y = YC + 1.175
SUM_LEN = []
VTH_X = {"/trigger_phase/VTH1": [], "/trigger_phase/VTH2": []}
for k in range(NT // 2):
    n0, n1 = 2 * k, 2 * k + 1
    xta, xtb = XT[n0] + X_R1K - DX_TAP, XT[n1] + X_R1K - DX_TAP
    xc = (xta + xtb) / 2 + 0.635
    ref = f"U{305 + k}"
    place_cond(ref, xc, YC, lambda pp: pp["1"][1] > 1.0 and pp["1"][0] < pp["4"][0])
    x1, y1 = P(ref, "1")
    x3, y3 = P(ref, "3")
    yj = y3 + 0.975 + 0.2
    assert abs((x1 - xta) - (xtb - x3)) < 5e-6 and x1 > xta
    ra = [(xta, AX - Y_RV), (xta, yj + (x1 - xta)), (x1, yj), (x1, y1)]
    rb = [(xtb, AX - Y_RV), (xtb, yj + (xtb - x3)), (x3, yj), (x3, y3)]
    T(nn(ref, "1"), W_SIG, ra, ch=0)
    T(nn(ref, "3"), W_SIG, rb, ch=0)
    SUM_LEN.append((n0, bl.plen(ra), n1, bl.plen(rb)))
    vth = nn(ref, "2")
    for pin in ("2", "4"):
        px, py = P(ref, pin)
        V(px, VTH_Y, vth)
        T(vth, W_SIG, [(px, py), (px, VTH_Y)], ch=0)
        VTH_X[vth].append(px)
    # +3V3 pin 8: pad-wide copper to the 100 n left of the pin, via pair to In2; GND pin 5 via
    p8, p5 = P(ref, "8"), P(ref, "5")
    cref = f"C{346 + k}"
    xcap = p8[0] - 1.30
    place2(cref, xcap, p8[1] - 0.6, "v", "GND")
    cp = P(cref, "@+3V3")
    cg = P(cref, "@GND")
    T("+3V3", 0.5, [(p8[0], cp[1]), cp], ch=0)
    for dy in (0.0, -0.65):
        V(xcap - 0.7, cp[1] + dy, "+3V3")
    T("+3V3", 0.45, [cp, (xcap - 0.7, cp[1]), (xcap - 0.7, cp[1] - 0.65)], ch=0.2)
    gv(xcap, cg[1] - 0.62)
    T("GND", W_GND, [cg, (xcap, cg[1] - 0.62)], ch=0)
    gv(p5[0], p5[1] - 1.3)
    T("GND", 0.6, [p5, (p5[0], p5[1] - 1.3)], ch=0)
    # outputs: via at the pin, B.Cu stub to the north edge
    for pin in ("7", "6"):
        px, py = P(ref, pin)
        net = nn(ref, pin)
        V(px, py - 1.35, net)
        T(net, W_SIG, [(px, py), (px, py - 1.35)], ch=0)
        T(net, W_SIG, [(px, py - 1.35), (px, 0.0)], layer="B.Cu", ch=0)
        blk.iface(net, px, 0.0, "B.Cu", "N", "slow", W_SIG, "comparator output")
assert all(abs(la - lb) < 1e-5 for _, la, _, lb in SUM_LEN)

# --- VTH rails (B.Cu) and the VTAP_TH feed between U308 and U309 (B side parts)
xg = (VTH_X["/trigger_phase/VTH1"][-1] + VTH_X["/trigger_phase/VTH2"][0]) / 2
XVTH = xg
x_r380, x_r381 = xg - 1.55, xg + 1.55
place2("R380", x_r380, VTH_Y, "h", "/trigger_phase/VTH1", side="B")
place2("R381", x_r381, VTH_Y, "h", "/VTAP_TH", side="B")
T("/trigger_phase/VTH1", 0.3, [(VTH_X["/trigger_phase/VTH1"][0], VTH_Y), P("R380", "@/trigger_phase/VTH1")], layer="B.Cu", ch=0)
T("/trigger_phase/VTH2", 0.3, [P("R381", "@/trigger_phase/VTH2"), (VTH_X["/trigger_phase/VTH2"][-1], VTH_Y)], layer="B.Cu", ch=0)
T("/VTAP_TH", 0.25, [P("R380", "@/VTAP_TH"), P("R381", "@/VTAP_TH")], layer="B.Cu", ch=0)
for cref, rref, net in (("C354", "R380", "/trigger_phase/VTH1"), ("C355", "R381", "/trigger_phase/VTH2")):
    rp = P(rref, "@" + net)
    place2(cref, rp[0], VTH_Y - 1.45, "v", "GND", side="B")
    g = P(cref, "@GND")
    cq = P(cref, "@" + net)
    T(net, 0.3, [rp, cq], layer="B.Cu", ch=0)
    gx = g[0] + (-0.75 if net.endswith("1") else 0.75)
    gv(gx, g[1])
    T("GND", W_GND, [g, (gx, g[1])], layer="B.Cu", ch=0)
# VTAP_TH down to the south edge on B.Cu (between taps 7 and 8, clear of the jumpers), TP305 on B
xv = XT[8] - 3.65
T("/VTAP_TH", 0.25, [(xv, VTH_Y), (xv, BH)], layer="B.Cu", ch=0)
bplace("TP305", xv, BH - 1.3, 0, side="B")
blk.iface("/VTAP_TH", xv, BH, "B.Cu", "S", "slow", 0.25, "R380/R381 1 k to VTH1/VTH2")

# --- VTAP strips (In2) decoupling: C358/C359 (VTAP_N) and C356/C357 (VTAP_P), mirror images, at taps 1 / 13
for tap, cn, cp_ in ((1, "C358", "C356"), (13, "C359", "C357")):
    x = XT[tap] + X_R22K
    for s, ref, rail in ((-1, cn, "VTAP_N"), (+1, cp_, "VTAP_P")):
        yc_ = AX + (Y_RV + 1.15) * s
        place2(ref, x, yc_, "v", rail if s > 0 else "GND")
        rp, g = P(ref, "@" + rail), P(ref, "@GND")
        T(rail, 0.3, [rp, (x, AX + Y_RV * s)], ch=0)
        gv(x, g[1] + 0.62 * s)
        T("GND", W_GND, [g, (x, g[1] + 0.62 * s)], ch=0)
# VTAP_N / VTAP_P to the south edge: via into the In2 strip, B.Cu straight down between the taps
for net, xx, yy in (("VTAP_N", XT[3] + 0.85, AX - Y_RV + 0.2), ("VTAP_P", XT[4] + 0.85, AX + Y_RV + 1.0)):
    V(xx, yy, net)
    T(net, 0.3, [(xx, yy), (xx, BH)], layer="B.Cu", ch=0)
    blk.iface(net, xx, BH, "B.Cu", "S", "supply", 0.3, "In2 strip under the taps (drawn by this block)")

# ============================================================================= front chain (west part, x 0-9.5)
# --- J102 EXT_CLK edge SMA, R122 + R301 49.9 R shunts at the pin (both on the netlist), U301 TMUX136
YJ = 4.0
blk.place("J102", 2.1, YJ, 270)
jx, jy = P("J102", "1")
XU1, YU1 = 5.6, YJ - 0.25
blk.place("U301", XU1, YU1, 0)
assert abs(P("U301", "3")[1] - YJ) < 1e-6 and P("U301", "1")[1] < P("U301", "3")[1]
T("/EXT_CLK", W50, [P("J102", "1"), P("U301", "3")], name="EXT_CLK: J102 -> U301.3", z=50, rf=True)
for s_ in (-1, 1):                          # J102 ground pads (F + B): via rows into In1
    for xg_ in (0.7, 1.7, 2.7, 3.6):
        gv(xg_, YJ + 2.825 * s_)
XSH = 4.1
place2("R301", XSH, YJ - 0.51, "v", "GND")
place2("R122", XSH, YJ + 0.51, "v", "/EXT_CLK")
for ref, s in (("R301", -1), ("R122", +1)):
    g = P(ref, "@GND")
    yj_pad = YJ + 2.825 * s
    T("GND", 0.5, [g, (g[0], yj_pad - 0.5 * s)], ch=0)
b1 = P("U301", "1")
T("/BUF_OUT_T", W50, [(b1[0], 0.0), b1], name="BUF_OUT_T: N edge -> U301.1", z=50, rf=True)
blk.iface("/BUF_OUT_T", b1[0], 0.0, "F.Cu", "N", "rf50", W50, "from the input stage (BUF802 trigger output)")
# VSW_GND: pins 2, 4, 5, 6, 7 joined under the body; centre via to the B.Cu network
VSW = "/trigger_phase/VSW_GND"
p2, p4, p5, p6, p7 = (P("U301", k) for k in "24567")
T(VSW, 0.15, [p2, (XU1 - 0.25, p2[1]), (XU1, YU1)], ch=0)
T(VSW, 0.2, [(XU1, YU1), p5], ch=0)
T(VSW, 0.15, [p4, (XU1 - 0.3, p4[1]), (XU1 - 0.15, p5[1]), p5], ch=0)
T(VSW, 0.15, [p6, (XU1 + 0.3, p6[1]), (XU1 + 0.15, p5[1]), p5], ch=0)
T(VSW, 0.15, [p7, p6], ch=0)
V(XU1, YU1, VSW)
# VCC pin 10: C301 (+2V5 / VSW_GND) right above, +2V5 via pair
place2("C301", XU1, 1.75, "v", VSW)
c1v, c1p = P("C301", "@" + VSW), P("C301", "@+2V5")
T("+2V5", 0.3, [P("U301", "10"), c1p], ch=0)
T("+2V5", 0.3, [c1p, (XU1 + 0.52, c1p[1]), (XU1 + 0.7, c1p[1] - 0.18)], ch=0)
V(XU1 + 0.7, c1p[1] - 0.18, "+2V5")
V(XU1 + 0.7, c1p[1] - 0.83, "+2V5")
T("+2V5", 0.3, [(XU1 + 0.7, c1p[1] - 0.18), (XU1 + 0.7, c1p[1] - 0.83)], ch=0)
V(XU1, 0.55, VSW)
T(VSW, 0.3, [c1v, (XU1, 0.55)], ch=0)
# VSW network on B.Cu under the TMUX (C302, C303 to GND, R304 to GND, R305 to -2V5), TP301
T(VSW, 0.3, [(XU1, 0.55), (XU1, YU1)], layer="B.Cu", ch=0)
VSWX = [(5.25, "C302"), (6.0, "C303"), (6.75, "R304"), (8.2, "R305")]
T(VSW, 0.3, [(XU1, YU1), (XU1, YU1 + 0.4)], layer="B.Cu", ch=0)
T(VSW, 0.3, [(5.25, YU1 + 0.4), (8.2, YU1 + 0.4)], layer="B.Cu", ch=0)
for x, ref in VSWX:
    place2(ref, x, YU1 + 0.4 + 0.5, "v", VSW, side="B")
    o = [p for p in ("1", "2") if nn(ref, p) != VSW][0]
    op = P(ref, o)
    T(VSW, 0.3, [(x, YU1 + 0.4), P(ref, "@" + VSW)], layer="B.Cu", ch=0)
    V(op[0], op[1] + 0.55, nn(ref, o))
    T(nn(ref, o), 0.3, [op, (op[0], op[1] + 0.55)], layer="B.Cu", ch=0)
bplace("TP301", 7.5, YU1 + 0.4, 0, side="B")
# SEL: pin 9 -> R303 (to -2V5) / R302 (from TRIG_SEL), top side right of the TMUX
p9 = P("U301", "9")
place2("R303", 7.5, 2.0, "v", "-2V5")
place2("R302", 8.46, 2.0, "v", "/TRIG_SEL")
s3 = P("R303", "@Net-(U301-SEL)")
T("Net-(U301-SEL)", W_SIG, [p9, (s3[0] - 0.49, p9[1]), s3], ch=0)
T("Net-(U301-SEL)", 0.25, [s3, P("R302", "@Net-(U301-SEL)")], ch=0)
q = P("R303", "@-2V5")
V(q[0], q[1] - 0.65, "-2V5")
T("-2V5", 0.3, [q, (q[0], q[1] - 0.65)], ch=0)
q = P("R302", "@/TRIG_SEL")
V(q[0], q[1] - 0.65, "/TRIG_SEL")
T("/TRIG_SEL", W_SIG, [q, (q[0], q[1] - 0.65)], ch=0)
ts = (P("R302", "@/TRIG_SEL")[0], P("R302", "@/TRIG_SEL")[1] - 0.65)

# --- U302 TLV3801: IN+ from the north (COM1), CMP_P north-west, CMP_N south
XU2, YU2 = 6.8, 9.0
place_cond("U302", XU2, YU2, lambda pp: pp["5"][1] < -0.5 and pp["5"][0] > 0.5 and pp["8"][0] < -0.5)
c8 = P("U301", "8")
i5 = P("U302", "5")
T("Net-(U301-COM1)", W50, [c8, (c8[0] + 0.475, c8[1]), (i5[0], c8[1] + i5[0] - c8[0] - 0.475), i5],
  name="COM1: U301.8 -> U302.5", z=50, rf=True)
# VCC 6/7 -> Y -> via pair (+2V5); decoupling C305 / C306 on B.Cu
q6, q7 = P("U302", "6"), P("U302", "7")
ym = q7[1] - 0.3
T("+2V5", 0.25, [q7, (q7[0], ym), (XU2, ym - 0.25)], ch=0)
T("+2V5", 0.25, [q6, (q6[0], ym), (XU2, ym - 0.25)], ch=0)
V(XU2, ym - 0.25, "+2V5")
V(XU2, ym - 0.9, "+2V5")
T("+2V5", 0.3, [(XU2, ym - 0.25), (XU2, ym - 0.9)], ch=0)
T("+2V5", 0.3, [(XU2, ym - 0.9), (XU2, ym - 1.22)], layer="B.Cu", ch=0)
for ref, yy in (("C305", ym - 1.22), ("C306", ym - 0.25)):
    place2(ref, XU2 + 0.48, yy, "h", "+2V5", side="B")
    g = P(ref, "@GND")
    gv(g[0] + 0.55, g[1])
    T("GND", 0.3, [g, (g[0] + 0.55, g[1])], layer="B.Cu", ch=0)
# VEE: pin 3 into the EP, 2 EP vias (-2V5 to In2); C307 on B.Cu at the EP vias
q3 = P("U302", "3")
T("-2V5", 0.25, [q3, (q3[0], YU2 + 0.45)], ch=0)
for dx in (-0.4, 0.4):
    V(XU2 + dx, YU2, "-2V5")
place2("C307", XU2 + 0.4 + 0.48, YU2, "h", "-2V5", side="B")
g = P("C307", "@GND")
gv(g[0] + 0.5, g[1])
T("GND", 0.3, [g, (g[0] + 0.5, g[1])], layer="B.Cu", ch=0)
q2 = P("U302", "2")
gv(q2[0], q2[1] + 0.62)
T("GND", 0.25, [q2, (q2[0], q2[1] + 0.62)], ch=0)
# TRIG_LEVEL pin 4: via, C304 10 n + TP302 on B.Cu, B.Cu to the south edge
q4 = P("U302", "4")
V(q4[0], q4[1] + 0.62, "/TRIG_LEVEL")
T("/TRIG_LEVEL", W_SIG, [q4, (q4[0], q4[1] + 0.62)], ch=0)
XTL, XTS = 8.75, 9.25
YTB = 20.8                                 # B.Cu TRIG_LEVEL bus to the passive level network (R383-R385, B side)
T("/TRIG_LEVEL", W_SIG, [(q4[0], q4[1] + 0.62), (q4[0] + 0.3, q4[1] + 0.92), (XTL - 0.2, q4[1] + 0.92),
                         (XTL, q4[1] + 1.12), (XTL, YTB - 0.4), (XTL - 0.4, YTB), (1.4, YTB)], layer="B.Cu")
for ref, xr, other in (("R383", 4.6, "/DAC_TRIG"), ("R384", 3.0, "-2V5"), ("R385", 1.4, "GND")):
    place2(ref, xr, YTB + 0.51, "v", "/trigger_phase/TRIG_LEVEL", side="B")
    op = P(ref, "@" + other)
    if other == "/DAC_TRIG":
        T(other, W_SIG, [op, (op[0], BH)], layer="B.Cu", ch=0)
        blk.iface("/DAC_TRIG", op[0], BH, "B.Cu", "S", "slow", W_SIG,
                  "R383 5.1 k to TRIG_LEVEL (passive level network: R384 8.87 k to -2V5, R385 2 k to GND, C304)")
    else:
        V(op[0] + 0.8, op[1], other)
        T(other, 0.3, [op, (op[0] + 0.8, op[1])], layer="B.Cu", ch=0)
place2("C304", XTL - 0.55, q4[1] + 2.2, "h", "GND", side="B")
T("/TRIG_LEVEL", W_SIG, [P("C304", "@/TRIG_LEVEL"), (XTL, P("C304", "@/TRIG_LEVEL")[1])], layer="B.Cu", ch=0)
g = P("C304", "@GND")
gv(g[0], g[1] + 0.6)
T("GND", 0.3, [g, (g[0], g[1] + 0.6)], layer="B.Cu", ch=0)
bplace("TP302", XTL - 0.55, 17.0, 0, side="B")
# TRIG_SEL B.Cu to the south edge
T("/TRIG_SEL", W_SIG, [ts, (XTS - 0.3, ts[1]), (XTS, ts[1] + 0.3), (XTS, BH)], layer="B.Cu")
blk.iface("/TRIG_SEL", XTS, BH, "B.Cu", "S", "slow", W_SIG, "R302 10 k to U301 SEL")

# --- outputs: CMP_P west then down to C308 / U303; CMP_N down: R306 bridge, R312 tap, C312, R310 49.9 R
XP = 4.5
q8, q1 = P("U302", "8"), P("U302", "1")
YR306 = 10.7
place2("R306", XP + 0.51, YR306, "h", "/trigger_phase/CMP_P")
place2("R311", XP - 0.51, 12.25, "h", "Net-(U304-A)")
place2("C308", XP, 13.4, "v", "/trigger_phase/CMP_P")
cmp_p = [q8, (q8[0], 7.55), (q8[0] - 0.45, 7.1), (XP + 0.45, 7.1), (XP, 7.55), P("C308", "@/trigger_phase/CMP_P")]
T("/trigger_phase/CMP_P", W50, cmp_p, name="CMP_P: U302.8 -> R311 -> R306 -> C308", z=50, rf=True)
XN = XP + 1.02
place2("R312", XN + 0.51, 11.55, "h", "/trigger_phase/CMP_N")
place2("C312", XN, 12.62, "v", "/trigger_phase/CMP_N")
d_ = q1[0] - XN
T("/trigger_phase/CMP_N", W50, [q1, (q1[0], YR306 - d_), (XN, YR306), P("C312", "@/trigger_phase/CMP_N")],
  name="CMP_N: U302.1 -> R306 -> R312 -> C312", z=50, rf=True)
c12 = P("C312", "@Net-(C312-Pad2)")
place2("R310", XN + 1.08, c12[1], "h", "Net-(C312-Pad2)")
T("Net-(C312-Pad2)", W50, [c12, P("R310", "@Net-(C312-Pad2)")], ch=0, rf=True)
g = P("R310", "@GND")
gv(g[0], g[1] - 0.62)
T("GND", W_GND, [g, (g[0], g[1] - 0.62)], ch=0)
# --- U303 TRF37D73 on the axis: RFIN pin 2 from the west, RFOUT pin 7 to the east
XU3, YU3 = 6.3, AX + 0.25
blk.place("U303", XU3, YU3, 0)
assert abs(P("U303", "7")[1] - AX) < 1e-6 and P("U303", "7")[0] > XU3
rin = P("U303", "2")
T("Net-(U303-RFIN)", W50, [P("C308", "@Net-(U303-RFIN)"), (XP, AX - 0.4), (XP + 0.4, AX), rin],
  name="RFIN: C308 -> U303.2", z=50, rf=True)
for pn in ("3", "4", "5", "6", "8"):
    x, y = P("U303", pn)
    T("GND", 0.2, [(x, y), (XU3 + (0.3 if x > XU3 else -0.3), y)], ch=0)
for dy in (-0.5, 0.0, 0.5):
    blk.via(XU3, YU3 + dy, "GND", 0.4, 0.2)
# VCC pin 1 -> up -> via pair; C309 100 n on B.Cu right under the vias
q = P("U303", "1")
T("+3V3", 0.3, [q, (q[0] + 0.0, q[1] - 0.35), (q[0] + 0.3, q[1] - 0.65)], ch=0)
V(q[0] + 0.3, q[1] - 0.65, "+3V3")
V(q[0] + 0.3, q[1] - 0.65 - 0.0 + 0.0, "+3V3") if False else None
place2("C309", q[0] + 0.3 + 0.48, q[1] - 0.65, "h", "+3V3", side="B")
g = P("C309", "@GND")
gv(g[0] + 0.5, g[1])
T("GND", 0.3, [g, (g[0] + 0.5, g[1])], layer="B.Cu", ch=0)
# --- bias tee (sim/bias_tee/RESULT.md): FB301 pad ON the line, straight chain down, R382 beside L302,
#     C313 100 n across the cold pad (GND via at its GND pad), +3V3 via pair beyond C313
XFB = 8.0
place2("FB301", XFB, AX + 0.485, "v", "Net-(U303-RFOUT)")
YL302 = AX + 0.485 + 0.93 + 2.28
place2("L302", XFB, YL302, "v", "Net-(FB301-Pad2)")
place2("R382", XFB - 2.05, YL302, "v", "Net-(FB301-Pad2)")
T("Net-(FB301-Pad2)", 0.64, [P("FB301", "@Net-(FB301-Pad2)"), P("L302", "@Net-(FB301-Pad2)")], ch=0)
for net_, sgn in (("Net-(FB301-Pad2)", -1), ("+3V3", 1)):
    rx, ry = P("R382", "@" + net_)
    lx, ly = P("L302", "@" + net_)
    d2 = (lx - 1.325 + 0.18) - rx
    T(net_, 0.5, [(rx, ry), (rx + d2, ry + sgn * d2)], ch=0)
yl2 = P("L302", "@+3V3")[1]
YC313 = YL302 + 2.28 + 0.46
place2("C313", XFB - 0.48, YC313, "h", "GND")
cpx, cpy = P("C313", "@+3V3")
T("+3V3", 0.56, [(cpx, yl2), (cpx, cpy)], ch=0)
gx_, gy_ = P("C313", "@GND")
gv(gx_ - 0.62, gy_)
T("GND", W_GND, [(gx_, gy_), (gx_ - 0.62, gy_)], ch=0)
VIA_Y = cpy + 0.31 + 0.1 + 0.225 + 0.02
for dx in (-0.3, 0.3):
    V(cpx + dx, VIA_Y, "+3V3")
T("+3V3", 0.5, [(cpx - 0.3, VIA_Y), (cpx + 0.3, VIA_Y)], ch=0)
T("+3V3", 0.56, [(cpx, cpy), (cpx, VIA_Y)], ch=0)
# --- C311 1 u, 12 dB pi pad R307 82 / R308 91 / R309 82, PH_LINE launch
XC311 = 9.42
place2("C311", XC311, AX, "h", "Net-(U303-RFOUT)")
T("Net-(U303-RFOUT)", W50, [P("U303", "7"), P("C311", "@Net-(U303-RFOUT)")], name="RFOUT: U303.7 -> FB301 -> C311",
  z=50, rf=True)
XR307, XR308, XR309 = 10.82, 12.24, 13.66
place2("R307", XR307, AX + 0.51, "v", "Net-(C311-Pad2)")
place2("R308", XR308, AX, "h", "Net-(C311-Pad2)")
place2("R309", XR309, AX + 0.51, "v", "Net-(D301-common)")
T("Net-(C311-Pad2)", W50, [P("C311", "@Net-(C311-Pad2)"), P("R308", "@Net-(C311-Pad2)")], name="pad in", z=50, rf=True)
for ref in ("R307", "R309"):
    g = P(ref, "@GND")
    gv(g[0], g[1] + 0.65)
    T("GND", W_GND, [g, (g[0], g[1] + 0.65)], ch=0)
X_STEP = X0 - 1.6
T("Net-(D301-common)", W50, [P("R308", "@Net-(D301-common)"), (X_STEP, AX)], name="PH_LINE launch 50 R", z=50, rf=True)
T("Net-(D301-common)", W_LIN, [(X_STEP, AX), (X0 + X_P3, AX)], name="PH_LINE launch 0.26", z=round(Z_LIN), rf=True)

# --- U304 SN65LVDS2 (COARSE), R311 / R312 470 R taps
XU4, YU4 = 1.95, 10.0
place_cond("U304", XU4, YU4, lambda pp: pp["3"][0] < -0.5 and pp["3"][1] > 0.5)     # rot 0: A bottom-left
pa, pb, pv, pc, pg = (P("U304", k) for k in "34152")
ra_ = P("R311", "@Net-(U304-A)")
T("Net-(U304-A)", W_SIG, [pa, (pa[0], ra_[1] - 0.3), (pa[0] + 0.3, ra_[1]), ra_])
rb_ = P("R312", "@Net-(U304-B)")
V(rb_[0] + 0.5, rb_[1], "Net-(U304-B)")
T("Net-(U304-B)", W_SIG, [rb_, (rb_[0] + 0.5, rb_[1])], ch=0)
V(3.9, 11.1, "Net-(U304-B)")
T("Net-(U304-B)", W_SIG, [pb, (3.75, pb[1]), (3.9, 11.1)], ch=0)
T("Net-(U304-B)", W_SIG, [(3.9, 11.1), (4.35, rb_[1]), (rb_[0] + 0.5, rb_[1])], layer="B.Cu")
V(pv[0], 8.28, "+3V3")
T("+3V3", 0.5, [pv, (pv[0], 8.28)], ch=0)
place2("C310", pv[0] + 0.17, 8.28, "h", "+3V3", side="B")
g = P("C310", "@GND")
gv(g[0] + 0.55, g[1])
T("GND", 0.3, [g, (g[0] + 0.55, g[1])], layer="B.Cu", ch=0)
gv(XU4, YU4)
T("GND", 0.4, [pg, (XU4, YU4)], ch=0)
V(3.9, pc[1], "/COARSE")
T("/COARSE", W_SIG, [pc, (3.9, pc[1])], ch=0)
XCO = 4.45
T("/COARSE", W_SIG, [(3.9, pc[1]), (XCO, pc[1] - 0.55), (XCO, 0.0)], layer="B.Cu")
bplace("TP303", 5.15, 8.4, 0, side="B")
T("/COARSE", W_SIG, [(XCO, 8.4), P("TP303", "1")], layer="B.Cu", ch=0)
blk.iface("/COARSE", XCO, 0.0, "B.Cu", "N", "slow", W_SIG, "SN65LVDS2 output to the FPGA")

SUPPLY_VIAS = {}
for t in blk.b.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() in ("+3V3", "+2V5", "-2V5"):
        SUPPLY_VIAS.setdefault(t.GetNetname(), []).append(blk.loc(t.GetPosition()))

# ============================================================================= zones
# In1 = GND over the block (the integrator replaces it), cut-outs under the hold nodes and the SMA pin
outline = [(0, 0), (BW, 0), (BW, BH), (26.5, BH), (26.5, 18.0), (9.5, 18.0), (9.5, BH), (0, BH), (0, 0)]
outline = [(0, 0), (BW, 0), (BW, BH), (26.5, BH), (26.5, 18.0), (9.5, 18.0), (9.5, BH), (0, BH)]
top_ol = [(0, 0), (BW, 0), (BW, BH), (26.5, BH), (26.5, 18.0), (9.5, 18.0), (9.5, BH), (0, BH)]
north_cut = [(9.5, 3.5), (26.5, 3.5), (26.5, 12.0), (9.5, 12.0)]
IN = 0.2
blk_ol = [(IN, IN), (BW - IN, IN), (BW - IN, BH - IN), (26.5 + IN, BH - IN), (26.5 + IN, 18.0 - IN),
          (9.5 - IN, 18.0 - IN), (9.5 - IN, BH - IN), (IN, BH - IN)]
blk.zone("GND", ["In1.Cu"], blk_ol, clearance=0.2)
blk.keepout(north_cut, ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"))
for c in CUT:
    blk.keepout(c, ("In1.Cu",))
blk.keepout(bl.rect_pts(0.0, YJ - 0.95, jx + 1.9, YJ + 0.95), ("In1.Cu",))
XV0, XV1 = XT[0] - 3.2, X15 + 1.5
blk.zone("VTAP_N", ["In2.Cu"], bl.rect_pts(XV0, AX - (Y_RV + 1.4), XV1, AX - 0.15), clearance=0.3, prio=1)
blk.zone("VTAP_P", ["In2.Cu"], bl.rect_pts(XV0, AX + 0.15, XV1, AX + Y_RV + 1.4), clearance=0.3, prio=1)
# F.Cu GND pour (keeps 2 w from every RF trace) - the integrator may keep or replace it
blk.zone("GND", ["F.Cu"], blk_ol, clearance=0.2, prio=0)
blk.keepout(bl.rect_pts(XT[0] + X_P12 - PITCH / 2 - 0.1, AX - (YL + W_STR / 2 + 2 * W_STR),
                        XE + 0.1, AX + YL + W_STR / 2 + 2 * W_STR), ("F.Cu",))
for q, w in KEEP:
    blk.rf_keepout(q, w)
blk.keepout(bl.rect_pts(0.0, 0.0, 9.4, 11.6), ("F.Cu",))     # dense front chain: no top pour

# ============================================================================= drawings, save
blk.edge_rect(0, 0, BW, BH, layer="Dwgs.User")
for a, c in ((north_cut[0], north_cut[1]), (north_cut[1], north_cut[2]), (north_cut[2], north_cut[3]),
             (north_cut[3], north_cut[0])):
    blk.line(*a, *c, layer="Dwgs.User")
for a, c in (((9.5, 18.0), (26.5, 18.0)), ((26.5, 18.0), (26.5, BH)), ((9.5, 18.0), (9.5, BH))):
    blk.line(*a, *c, layer="Dwgs.User")
blk.text("PHASE", 40.0, 21.6, 0.5)
blk.text("EXT_CLK", 1.6, 8.6, 0.35)
for n, x in enumerate(XT):
    blk.text(str(n), x + 1.85, AX + YL + 1.0, 0.3)
path = blk.save(HERE)

# ============================================================================= tables
print(f"PITCH {PITCH} mm, W_STR {W_STR}, W_LIN {W_LIN}, L_LIN {L_LIN:.3f} mm/tap, Y_M {Y_M:.3f}, YL {YL}")
print(f"tap 0 x {X0:.3f}, tap 15 x {X15:.3f} (local), axis y {AX}")
for nm in blk.routes:
    r = blk.routes[nm]
    L = blk.route_len(nm)
    if r["z"]:
        print(f"  {nm:45s} w {r['width']:.2f} L {L:7.3f} mm  {L * bl.ps_mm(r['width']):7.1f} ps")
print("summing taps A = B:", SUM_LEN[0][1], SUM_LEN[0][3])
REFS = [r for r, c in NL.comps.items() if c["sheet"] == "/trigger_phase/"] + ["J102", "R122"]
RFC = {"/EXT_CLK": W50, "/BUF_OUT_T": W50, "Net-(U301-COM1)": W50, "/trigger_phase/CMP_P": W50,
       "/trigger_phase/CMP_N": W50, "Net-(U303-RFIN)": W50, "Net-(U303-RFOUT)": W50, "Net-(C311-Pad2)": W50,
       "Net-(C312-Pad2)": W50}
res = bl.check_board(path, refs=REFS, rf_widths=RFC)
# mixed-width RF nets: every track of the net must have one of its design widths
b2 = pcbnew.LoadBoard(path)
bad = 0
for t in b2.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        continue
    n_ = t.GetNetname()
    w = round(pcbnew.ToMM(t.GetWidth()), 3)
    if n_ == "Net-(D301-common)" and t.GetLayer() == pcbnew.F_Cu and w not in (W50, W_LIN, 0.2):
        bad += 1
    if n_ in ("/PSTRB_A", "/PSTRB_K") and w not in (W_STR,):
        bad += 1
for k in ("clearance", "unrouted", "corner"):
    for e in res["details"][k]:
        print("   ", k, e)
# containment: copper / pads inside the block rectangle and outside the pstrobe cut-out
out = []
for it in list(b2.GetTracks()) + [p for f in b2.GetFootprints() for p in f.Pads()]:
    if isinstance(it, pcbnew.PAD) and it.GetParent().GetReference() == "J102":
        continue
    bb_ = it.GetBoundingBox()
    x0_, y0_ = pcbnew.ToMM(bb_.GetLeft()) - 100, pcbnew.ToMM(bb_.GetTop()) - 100
    x1_, y1_ = pcbnew.ToMM(bb_.GetRight()) - 100, pcbnew.ToMM(bb_.GetBottom()) - 100
    inside = x0_ >= -0.16 and y0_ >= -0.16 and x1_ <= BW + 0.16 and y1_ <= BH + 0.16   # iface stub end caps
    cut = x1_ > 9.5 + 1e-3 and x0_ < 26.5 - 1e-3 and ((y1_ > 3.5 + 1e-3 and y0_ < 12.0 - 1e-3) or y1_ > 18.0 + 1e-3)
    if not inside or cut:
        out.append((it.GetNetname(), round(x0_, 2), round(y0_, 2), round(x1_, 2), round(y1_, 2)))
print("items outside the block area:", len(out), out[:8])
print("mixed-width RF nets (PH_LINE 0.36/0.26, PSTRB 0.16): deviations", bad)
json.dump({k: v for k, v in res.items() if k != "details"}, open("/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board/phase_check.json", "w"), indent=1)
if "--render" in sys.argv:
    S = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board"
    bl.render(path, os.path.join(HERE, "phase.png"), layers=("F.Cu", "B.Cu", "F.SilkS", "F.Fab", "Dwgs.User"),
              tmpdir=S)
    bb = b2.ComputeBoundingBox(False)
    ox, oy = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())
    for nm_, (x0_, x1_) in (("phase_detail.png", (0.0, 14.0)), ("phase_taps.png", (26.0, 40.0)), ("phase_end.png", (86.0, 99.5))):
        bl.render(path, os.path.join(HERE if nm_ == "phase_detail.png" else S, nm_),
                  layers=("F.Cu", "B.Cu", "F.Fab", "Dwgs.User"),
                  crop=(100 + x0_ - ox, 100 - oy, 100 + x1_ - ox, 122.5 - oy), tmpdir=S)
