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
os.environ["BL_STACKUP"] = "6L"            # 22 Nov: native 6-layer block (In2 = L3 slow, In3 = L4 power), merge with layer_map=None
sys.path.insert(0, "../..")
import boardlib as bl
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
blk = bl.Block("phase")
NL = blk.nl
BW, BH = 99.5, 22.5

# ============================================================================= six-layer RF geometry (phase two)
# RULES rule 10: L1 over L2 = 3313 prepreg 0.0994 mm, er 4.1 (boardlib STACKUPS["6L"], solder-mask corrected).
# 22 Nov 2026: native 6-layer file (F / In1 L2 GND / In2 L3 slow: VTH rails / In3 L4 power: VTAP strips / In4 / B).
H6, ER6 = bl.STACKUPS["6L"]["H"], bl.STACKUPS["6L"]["ER"]


def z6(w):
    return bl.microstrip(w, h=H6, er=ER6)[0]


def ps6(w):                                             # ps / mm
    return math.sqrt(bl.microstrip(w, h=H6, er=ER6)[1]) / bl.C0


def c6(w):                                              # pF / mm
    z, ee = bl.microstrip(w, h=H6, er=ER6)
    return math.sqrt(ee) / (bl.C0 * z)


W_MIN_FAB = 0.09                                        # JLC 6-layer minimum track
W_MIN_RF = 0.10                                         # used minimum for controlled-impedance lines (margin)
W50 = bl.r01(bl.width_for_6l(50.0))                     # 0.16 mm (50.2 R)
Z50 = z6(W50)

# --- strobe lines PSTRB_A / K: straight sections of one pitch; the pitch is KEPT (4.514 mm, comparators and the
#     summing-node routing unchanged).  Loaded Z = Z0 * tdu / td with tdu fixed by the pitch, so the narrowest
#     manufacturable trace gives the highest loaded impedance; the pad loading (0.5 p cap pad 0.56 x 0.62 on solid
#     L2) is not cut: with it the loaded delay lands on 40 ps within 2 %.
PITCH = 4.514
PAD_STR_W, PAD_STR_L = 0.56, 0.62
C_GATE_STR, C_MISC_STR = 0.40, 0.02
TD_STR_TGT = 40.0
W_STR = W_MIN_RF
Z_STR = z6(W_STR)
C_PAD_STR = (c6(PAD_STR_W) - c6(W_STR)) * PAD_STR_L
CL_STR = C_GATE_STR + C_PAD_STR + C_MISC_STR
TDU_STR = PITCH * ps6(W_STR)
TD_STR, ZL_STR = bl.loaded(TDU_STR, Z_STR, CL_STR)
# --- signal line PH_LINE: loaded 50 R; the per-tap delay keeps the designed line - strobe difference
#     (70 - 40 = 30 ps model) so the effective tap spacing is unchanged with the actual strobe delay
TD_LIN = TD_STR + (70.0 - 40.0)
PAD_LIN_W, PAD_LIN_L = 0.45, 0.70                       # BAT15 pad 3 (SOT-323), line along the 0.70 mm length
C_GATE_LIN = 0.37
W_LIN = 0.10
for _ in range(4):
    C_PAD_LIN = (c6(PAD_LIN_W) - c6(W_LIN)) * PAD_LIN_L
    CL_LIN = C_GATE_LIN + C_PAD_LIN
    z_t = math.sqrt(50.0 * TD_LIN / (TD_LIN / 50.0 - CL_LIN))
    W_LIN = max(W_MIN_RF, bl.r01(bl.width_for_6l(z_t)))
Z_LIN = z6(W_LIN)
TDU_LIN = bl.solve_tdu(Z_LIN, CL_LIN, TD_LIN)
TD_LIN_A, ZL_LIN = bl.loaded(TDU_LIN, Z_LIN, CL_LIN)
L_LIN = TDU_LIN / ps6(W_LIN)
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
YL_MIN = math.ceil((Y_M + W_LIN / 2 + 0.3 + 0.79) / 0.05) * 0.05
YL = 2.75                                   # kept (4-layer value): rows, pstrobe interface, comparators
assert YL_MIN <= YL, YL_MIN
YNODE = YL - 0.96
X_R1K, X_R22K = -1.94, -0.06
Y_CUT0 = 0.40                               # node cut-out now covers the BAT15 pads 1 / 2 completely (was 0.55)
Y_RV = YL + 1.085
DX_TAP = 0.8
W_NODE, W_SIG, W_PWR, W_GND = 0.15, 0.2, 0.5, 0.4

# ============================================================================= block placement constants
AX = 15.0                                   # tap axis (board y 37.5)
X_IF_STR = 26.5                             # pstrobe east edge: 0.16 mm strobe sections start here
SHIFT_W = 0.29                              # line moved west (tap-0 summing via stays 0.2 mm off pstrobe)
X0 = X_IF_STR - X_P12 + PITCH / 2 - SHIFT_W  # tap 0 (D301) centre
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
            T(node, W_NODE, [(x + X_P12, AX + YNODE * s), (x + xr, AX + YNODE * s), (x + xr, yi)], ch=0.1)
        V(x + X_R22K, AX + Y_RV * s, rail)
        T(rail, 0.3, [P(rna if s < 0 else rnk, "@" + rail), (x + X_R22K, AX + Y_RV * s)], ch=0)
        CUT.append(bl.rect_pts(x - 1.35, AX + Y_CUT0 * s, x + 0.45, AX + (YL - 0.4) * s))
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
        T(net, W_STR, [(max(x + X_P12 - PITCH / 2, X_IF_STR), AX + YL * s), (x + X_P12 + PITCH / 2, AX + YL * s)],
          name=f"{net} section {n}", z=round(Z_STR), rf=True)

# --- strobe interfaces (pstrobe east edge, the 0.16 mm sections start on the boundary)
for s, net in ((-1, "PSTRB_A"), (+1, "PSTRB_K")):
    blk.iface(net, X_IF_STR, AX + YL * s, "F.Cu", "W", "rf50", W50,
              f"pstrobe output, 50 R ({W50} mm) up to the boundary, {W_STR} mm ({Z_STR:.0f} R) from here; equal A/K")

# --- far end: terminations (vertical, pad centred on the line, GND pad outward)
XE = X15 + X_P12 + PITCH / 2
for s, net, ref in ((-1, "PSTRB_A", "R379"), (+1, "PSTRB_K", "R378")):
    place2(ref, XE, AX + (YL + 0.51) * s, "v", net if s > 0 else "GND")
    g = P(ref, "@GND")
    gv(g[0], g[1] + 0.75 * s)
    T("GND", W_GND, [g, (g[0], g[1] + 0.75 * s)], ch=0)
d3 = P("D316", "3")
XR377, YR377 = BW - 0.93, AX + 1.8
place2("R377", XR377, YR377, "h", "Net-(D301-common)")
r1 = P("R377", "@Net-(D301-common)")
dxe = d3[0] - r1[0]
T("Net-(D301-common)", W_LIN, [d3, (d3[0], YR377 - 0.47 - dxe), (r1[0], YR377 - 0.47), r1], name="PH_LINE end -> R377",
  z=round(Z_LIN), rf=True, ch=0)
g = P("R377", "@GND")
gv(g[0], g[1] - 0.68)
T("GND", W_GND, [g, (g[0], g[1] - 0.68)], ch=0)
blk.via(r1[0], r1[1], "Net-(D301-common)", 0.35, 0.15)   # TP304 (LINE_IN) on B under R377 pad 1 (via in pad)
bplace("TP304", r1[0], r1[1], 0, side="B")

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
        # 22 Nov (TOPOLOGY.md section 8): VTH on L1 at the body centre line YC, pins 2 / 4 by short inward stubs;
        # vias only where the B-side divider (R380 / R381) joins: U308 pin 4 and U309 pin 2
        T(vth, W_SIG, [(px, py), (px, YC)], ch=0)
        if (k, pin) in ((3, "4"), (4, "2")):
            V(px, VTH_Y, vth)
        VTH_X[vth].append(px)
    # +3V3 pin 8: pad-wide copper to the 100 n left of the pin, via pair to In2; GND pin 5 via
    p8, p5 = P(ref, "8"), P(ref, "5")
    cref = f"C{346 + k}"
    xcap = p8[0] - 1.30
    place2(cref, xcap, p8[1] - 1.1, "v", "GND")
    cp = P(cref, "@+3V3")
    cg = P(cref, "@GND")
    T("+3V3", 0.5, [(p8[0], cp[1]), cp], ch=0)       # starts inside the long pin-8 pad
    YUB = YC - 0.75                                  # under-body via row (22 Nov, board drop of the east TAPs)
    if k == 5:
        # U310: its cap vias sat in the L6 fan-in of the MCU / TAP drop (board x 68-72.5): +3V3 via under the body
        # at pin 8, the cap's GND pad goes to the F ground pour
        V(p8[0], YUB, "+3V3")
        T("+3V3", 0.5, [p8, (p8[0], YUB)], ch=0)
        # TIGHTEN (24 Nov): GND via 0.6 mm east of the cap's GND pad, just east of the L6 fan-in (board x <= 72.0),
        # joined to the pad by the F ground pour (was 1.6 mm to the nearest GND via)
        gv(xcap + 0.85, cg[1] + 0.13)
    else:
        for dy in (-0.4, -1.05):
            V(xcap - 0.7, cp[1] + dy, "+3V3")
        T("+3V3", 0.45, [cp, (xcap - 0.4, cp[1]), (xcap - 0.7, cp[1] - 0.3), (xcap - 0.7, cp[1] - 1.05)], ch=0)
        if k == 4:      # U309: cap GND via 0.53 mm west, clear of the JTAG drop at board x 62.5
            gq = (xcap - 0.43, cg[1] - 0.65)         # NE of the +3V3 via pair (power clearance 0.15), west of the
            gv(*gq)                                  # JTAG drop (board x 62.5), below TAP7's lane (y 22.66)
            T("GND", W_GND, [cg, (xcap, cg[1] - 0.35), (xcap - 0.3, cg[1] - 0.65), gq], ch=0)
        else:
            gv(xcap, cg[1] - 0.62)
            T("GND", W_GND, [cg, (xcap, cg[1] - 0.62)], ch=0)
    if k == 4:          # U309: pin-5 GND via under the body (out of the fan-in)
        gv(p5[0], YUB)
        T("GND", 0.6, [p5, (p5[0], YUB)], ch=0)
    else:
        gv(p5[0], p5[1] - 1.3)
        T("GND", 0.6, [p5, (p5[0], p5[1] - 1.3)], ch=0)
    # outputs: via at the pin, B.Cu stub to the north edge
    for pin in ("7", "6"):
        px, py = P(ref, pin)
        net = nn(ref, pin)
        if k >= 4:      # U309-U312: via under the body, reached from the L6 highway below (TOPOLOGY.md section 7)
            V(px, YUB, net)
            T(net, W_SIG, [(px, py), (px, YUB)], ch=0)
            blk.iface(net, px, YUB, "B.Cu", "-", "slow", W_SIG, "comparator output, via under the body")
            continue
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
# 22 Nov: the rails run on L1 under the comparator bodies (centre line YC); the divider joins through one via per rail
v1, v2 = sorted(VTH_X["/trigger_phase/VTH1"]), sorted(VTH_X["/trigger_phase/VTH2"])
T("/trigger_phase/VTH1", 0.3, [(v1[0] - 0.3, YC), (v1[-1] + 0.3, YC)], layer="F.Cu", ch=0)
T("/trigger_phase/VTH1", 0.3, [(v1[-1], VTH_Y), P("R380", "@/trigger_phase/VTH1")], layer="B.Cu", ch=0)
T("/trigger_phase/VTH2", 0.3, [(v2[0] - 0.3, YC), (v2[-1] + 0.3, YC)], layer="F.Cu", ch=0)
T("/trigger_phase/VTH2", 0.3, [P("R381", "@/trigger_phase/VTH2"), (v2[0], VTH_Y)], layer="B.Cu", ch=0)
T("/VTAP_TH", 0.25, [P("R380", "@/VTAP_TH"), P("R381", "@/VTAP_TH")], layer="B.Cu", ch=0)
for cref, rref, net in (("C354", "R380", "/trigger_phase/VTH1"), ("C355", "R381", "/trigger_phase/VTH2")):
    rp = P(rref, "@" + net)
    place2(cref, rp[0], VTH_Y - 1.45, "v", "GND", side="B")
    g = P(cref, "@GND")
    cq = P(cref, "@" + net)
    T(net, 0.3, [rp, cq], layer="B.Cu", ch=0)
    gx = g[0] - 0.75          # 22 Nov: both GND vias west (C355's east via sat on the U309 under-body TAP8 via)
    gv(gx, g[1])
    T("GND", W_GND, [g, (gx, g[1])], layer="B.Cu", ch=0)
# 22 Nov: VTAP_TH no longer runs down to the south edge here: the board brings it up tap-row lane 7 on L6 and ends on
# the R380 / R381 link (x 62.35); TP305 sits north of the link (B), clear of the L6 lanes
xv = XT[8] - 3.65
yt = VTH_Y - 1.52
bplace("TP305", xv, yt, 0, side="B")
T("/VTAP_TH", 0.25, [(xv, yt), (xv, VTH_Y)], layer="B.Cu", ch=0)
blk.iface("/VTAP_TH", xv + 0.42, VTH_Y, "B.Cu", "S", "slow", 0.25, "R380/R381 1 k link; the board joins from the south (lane 7)")

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
# 22 Nov: the B.Cu feed columns (x 43.86 / 48.37) are gone (they sat in the JTAG tap-row lanes); the L4 strips are fed
# on L4 from the mcuif R725 / R726 vias by the board's power islands (board_power.py)
for net in ("VTAP_N", "VTAP_P"):
    blk.iface(net, 0, 0, "In3.Cu", "-", "supply", None, "L4 strip under the taps (drawn by this block), fed on L4")

# ============================================================================= front chain
# Column x 0-9.5 (full height): J102, shunts, U301 TMUX136, U302 TLV3801, CMP_P / CMP_N network, U304.
# Axis corridor x 9.5-26.5, y 12-18: U303 TRF37D73 -> bias tee (bead on top, choke / 1 k / cold cap on B
# straight below through a via pair) -> C311 -> 12 dB pi pad -> PH_LINE launch.  North strip y 0-2.5
# (x 9.5-26.5, above pstrobe): C301 and the VSW_GND network (B).
# --- J102 EXT_CLK edge SMA, R301 / R122 49.9 R shunts (staggered, both north of the line), U301 (rot 270)
YJ = 4.0
blk.place("J102", 2.1, YJ, 270)
jx, jy = P("J102", "1")
for s_ in (-1, 1):                          # J102 ground pads (F + B): via rows into In1
    for xg_ in (0.7, 1.7, 2.7, 3.6):
        gv(xg_, YJ + 2.825 * s_)
for ref, xs in (("R301", 5.17), ("R122", 6.11)):
    place2(ref, xs, YJ - 0.51, "v", "GND")
    g = P(ref, "@GND")
    gv(g[0], g[1] - 0.62)
    T("GND", 0.4, [g, (g[0], g[1] - 0.62)], ch=0)
XU1, YU1 = 8.04, 5.3
place_cond("U301", XU1, YU1, lambda pp: pp["1"][1] < -0.5 and pp["1"][0] > 0.5 and pp["3"][1] < -0.5)
p1, p3, p8, p9, p10 = (P("U301", k) for k in ("1", "3", "8", "9", "10"))
assert abs(p3[0] - 7.79) < 1e-4 and abs(p1[0] - 8.79) < 1e-4 and abs(p8[0] - 8.29) < 1e-4, (p1, p3, p8)
T("/EXT_CLK", W50, [P("J102", "1"), (p3[0], YJ), p3], name="EXT_CLK: J102 -> U301.3", z=50, rf=True)
T("/BUF_OUT_T", W50, [(p1[0], 0.0), p1], name="BUF_OUT_T: N edge -> U301.1", z=50, rf=True)
blk.iface("/BUF_OUT_T", p1[0], 0.0, "F.Cu", "N", "rf50", W50, "from the input stage (BUF802 trigger output)")
# VSW_GND pins 2, 4, 5, 6, 7 (DECOUPLING-3, 24 Nov): 0.5 mm bar under the body from pin 5 to x 8.35, every VSW pin
# joined pad-wide; C303 (1 n C0G, VSW -> GND) on top at pin 5; C302 (100 n VSW -> GND) and C301 (100 n +2V5 -> VSW)
# on B directly under U301, joined by a 0.5 mm B bar through the VSW via; C301's +2V5 pad on a via at pin 10
VSW = "/trigger_phase/VSW_GND"
q2, q4, q5, q6, q7 = (P("U301", k) for k in "24567")
T(VSW, 0.5, [q5, (8.25, YU1)], ch=0)
for q, w_ in ((q2, 0.2), (q4, 0.25), (q6, 0.25), (q7, 0.2)):
    T(VSW, w_, [q, (q[0], YU1)], ch=0)
XVV = 7.55                                          # VSW via under the body
V(XVV, YU1, VSW)
place2("C303", 5.68, YU1, "h", "GND")                # top, VSW pad 0.4 mm from pin 5 (courtyards touch)
T(VSW, 0.5, [P("C303", "@" + VSW), q5], ch=0)
place2("C302", 6.5, YU1, "h", "GND", side="B")       # B under the west pins
place2("C301", 8.55, YU1, "h", VSW, side="B")        # B under the body, +2V5 pad below pin 10
T(VSW, 0.5, [P("C302", "@" + VSW), P("C301", "@" + VSW)], layer="B.Cu", ch=0)
YG3 = YU1 + 0.65                                     # shared GND via of C303 (F) and C302 (B)
g3, g2b = P("C303", "@GND"), P("C302", "@GND")
gv(g3[0], YG3)
T("GND", 0.4, [g3, (g3[0], YG3)], ch=0)
T("GND", 0.4, [g2b, (g2b[0], YG3), (g3[0], YG3)], layer="B.Cu")
c1v = P("C301", "@" + VSW)
T(VSW, 0.3, [c1v, (c1v[0], 0.45), (18.65, 0.45), (18.9, 0.7), (18.9, 1.25)], layer="B.Cu", ch=0.3)
# VCC pin 10 -> east, north beside BUF_OUT_T to the +2V5 via in the north strip; a via at (XVC, 4.68) on the way
# lands on C301's +2V5 pad (B)
XVC = 9.20                                  # corner inside the pin-10 pad
T("+2V5", 0.3, [p10, (XVC, p10[1]), (XVC, 2.2)], ch=0)
V(XVC, 2.2, "+2V5")
YV10 = 4.15                                 # 0.1 mm off the pin-1 pad corner
V(XVC, YV10, "+2V5")
c1p = P("C301", "@+2V5")
T("+2V5", 0.4, [c1p, (c1p[0], YV10 + XVC - c1p[0]), (XVC, YV10)], layer="B.Cu", ch=0)
place2("C306", 11.8, 1.62, "v", "GND", side="B")   # second U302 100 n at the north +2V5 via pair; GND pad into the B pour
c6p = P("C306", "@+2V5")
T("+2V5", 0.4, [(XVC, 2.2), (XVC + 2.2 - c6p[1], c6p[1]), c6p], layer="B.Cu", ch=0)
# (24 Nov, board integration: the +2V5 via at x 10.45 sat under the board PH_STROBE_N run x 10.60; C306 moved
# 0.12 mm south so its GND via clears the PH_STROBE_N run at board y 23.21)
# (24 Nov, integration: C306's GND pad is fed by the board's B pour again; its own via sat on the board's L3
# DAC_TRIG / TRIG_SEL slow lines at y 23.05 / 23.35)
V(11.1, c6p[1], "+2V5")
# VSW network on B in the north strip: R304 (GND), R305 (-2V5), TP301
for x, ref in ((15.8, "R304"), (17.2, "R305")):
    place2(ref, x, 1.5, "v", VSW, side="B")
    o = [p for p in ("1", "2") if nn(ref, p) != VSW][0]
    op = P(ref, o)
    T(VSW, 0.3, [(x, 0.45), P(ref, "@" + VSW)], layer="B.Cu", ch=0)
    V(op[0] + 0.65, op[1], nn(ref, o))
    T(nn(ref, o), 0.3, [op, (op[0] + 0.65, op[1])], layer="B.Cu", ch=0)
bplace("TP301", 18.9, 1.25, 0, side="B")
# SEL pin 9: via, B.Cu lane x 9.25 down to R303 (-2V5) / R302 (TRIG_SEL) near the south edge
XS = 9.25
T("Net-(U301-SEL)", W_SIG, [p9, (p9[0], 6.3), (p9[0] + 0.13, 6.43), (p9[0] + 0.13, 6.65)], ch=0)
V(p9[0] + 0.13, 6.65, "Net-(U301-SEL)")
place2("R303", 7.9, 19.0, "v", "Net-(U301-SEL)", side="B")
place2("R302", 9.0, 20.5, "v", "Net-(U301-SEL)", side="B")
T("Net-(U301-SEL)", W_SIG, [(p9[0] + 0.13, 6.65), (XS, 6.98), (XS, 19.4), (9.0, 19.65), P("R302", "@Net-(U301-SEL)")],
  layer="B.Cu", ch=0)
T("Net-(U301-SEL)", W_SIG, [P("R303", "@Net-(U301-SEL)"), (XS, P("R303", "@Net-(U301-SEL)")[1])], layer="B.Cu", ch=0)
q = P("R303", "@-2V5")
V(q[0], q[1] + 0.62, "-2V5")
T("-2V5", 0.3, [q, (q[0], q[1] + 0.62)], layer="B.Cu", ch=0)
q = P("R302", "@/TRIG_SEL")
T("/TRIG_SEL", W_SIG, [q, (q[0], q[1] + 0.4), (XS, q[1] + 0.65), (XS, BH)], layer="B.Cu", ch=0)
blk.iface("/TRIG_SEL", XS, BH, "B.Cu", "S", "slow", W_SIG, "R302 10 k to U301 SEL")

# --- U302 TLV3801 (rot 90): IN+ pin 5 straight below U301.8, CMP_P pin 8 / CMP_N pin 1 on the west column
XU2, YU2 = 7.54, 8.6
place_cond("U302", XU2, YU2, lambda pp: pp["5"][1] < -0.5 and pp["5"][0] > 0.5 and pp["8"][0] < -0.5)
i5 = P("U302", "5")
assert abs(i5[0] - p8[0]) < 1e-4
T("Net-(U301-COM1)", W50, [p8, i5], name="COM1: U301.8 -> U302.5", z=50, rf=True)
r6, r7 = P("U302", "6"), P("U302", "7")
for q in (r6, r7):
    T("+2V5", 0.25, [q, (q[0], q[1] - 0.35), (XU2, q[1] - 0.6)], ch=0)
YV6 = r6[1] - 0.85                          # +2V5 via of pins 6 / 7 (between U301 and U302)
V(XU2, YV6, "+2V5")
T("+2V5", 0.3, [(XU2, r6[1] - 0.6), (XU2, YV6)], ch=0)
# DECOUPLING-2 / PDN-6 (24 Nov): no top-side room between U301 and U302 (COM1, SEL, CMP_P and the pin rows), so the
# caps sit on B in line with the via: C305 (100 n) west of it, C615 (1 u, power sheet, moved here) east of it; each
# pad beside the via (not on it), own GND via
place2("C305", XU2 - 1.04, YV6, "h", "GND", side="B")
T("+2V5", 0.4, [P("C305", "@+2V5"), (XU2, YV6)], layer="B.Cu", ch=0)
g = P("C305", "@GND")
gv(g[0] - 0.6, g[1])
T("GND", 0.4, [g, (g[0] - 0.6, g[1])], layer="B.Cu", ch=0)
place2("C615", XU2 + 0.61, YV6, "v", "+2V5", side="B")
c615 = P("C615", "@+2V5")
T("+2V5", 0.3, [(XU2, YV6), (XU2 + 0.21, YV6 - 0.21), (c615[0], YV6 - 0.21)], layer="B.Cu", ch=0)
g = P("C615", "@GND")
gv(g[0] + 0.65, g[1])
T("GND", 0.4, [g, (g[0] + 0.65, g[1])], layer="B.Cu", ch=0)
# VEE: pin 3 into the EP, 2 EP vias (-2V5); C620 (2.2 u, power sheet, moved here) and C307 (100 n) on B, each
# -2V5 pad straight below one EP via, GND pads joined, one GND via south of them that also takes GND pin 2
q3 = P("U302", "3")
T("-2V5", 0.25, [q3, (q3[0], YU2 + 0.4)], ch=0)
XEP = (XU2 - 0.4, XU2 + 0.54)
for x_ in XEP:
    V(x_, YU2, "-2V5")
for x_, ref in zip(XEP, ("C620", "C307")):
    place2(ref, x_, YU2 + 1.03, "v", "-2V5", side="B")
    T("-2V5", 0.4, [(x_, YU2), P(ref, "@-2V5")], layer="B.Cu", ch=0)
ga, gb = P("C620", "@GND"), P("C307", "@GND")
XG2 = (ga[0] + gb[0]) / 2
YG2 = ga[1] + 0.54
T("GND", 0.4, [ga, gb], layer="B.Cu", ch=0)
T("GND", 0.4, [(XG2, ga[1]), (XG2, YG2)], layer="B.Cu", ch=0)
gv(XG2, YG2)
q2_ = P("U302", "2")
T("GND", 0.25, [q2_, (q2_[0], YG2 - 0.45), (XG2, YG2 - 0.45 + XG2 - q2_[0]), (XG2, YG2)], ch=0)
# TRIG_LEVEL pin 4: 45-degree stub to a via east of the caps, B.Cu lane x 8.8 to the passive level network
q4_ = P("U302", "4")
XTL, YTB = 8.8, 12.4
YVT = q4_[1] + 0.4 + XTL - q4_[0]
V(XTL, YVT, "/TRIG_LEVEL")
T("/TRIG_LEVEL", W_SIG, [q4_, (q4_[0], q4_[1] + 0.4), (XTL, YVT)], ch=0)
T("/TRIG_LEVEL", W_SIG, [(XTL, YVT), (XTL, YTB - 0.4), (XTL - 0.4, YTB), (1.4, YTB)], layer="B.Cu", ch=0)
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
place2("C304", 6.6, YTB + 0.48, "v", "/trigger_phase/TRIG_LEVEL", side="B")
g = P("C304", "@GND")
gv(g[0], 14.3)
T("GND", 0.3, [g, (g[0], 14.3)], layer="B.Cu", ch=0)
bplace("TP302", 7.6, 15.6, 0, side="B")
T("/TRIG_LEVEL", W_SIG, [(7.6, YTB), (7.6, 15.6)], layer="B.Cu", ch=0)

# --- outputs: CMP_P (west line) and CMP_N (east line) straight down through the R306 bridge, the R311 / R312
#     470 R taps and the C308 / C312 coupling caps; R310 49.9 R terminates CMP_N
q8_, q1_ = P("U302", "8"), P("U302", "1")
XN = q1_[0]
XP = XN - 1.02
YR306 = YU2 + 1.6 + 0.47
Y_TAP = YR306 + 0.94
Y_CC = Y_TAP + 0.47 + 0.91
place2("R306", XP + 0.51, YR306, "h", "/trigger_phase/CMP_P")
place2("R311", XP - 0.51, Y_TAP, "h", "Net-(U304-A)")
place2("R312", XN + 0.51, Y_TAP, "h", "/trigger_phase/CMP_N")
place2("C308", XP, Y_CC, "v", "/trigger_phase/CMP_P")
place2("C312", XN, Y_CC, "v", "/trigger_phase/CMP_N")
yt = q8_[1] - 0.35
cmp_p = [q8_, (q8_[0], yt), (q8_[0] - 0.35, yt - 0.35), (XP + 0.35, yt - 0.35), (XP, yt), P("C308", "@/trigger_phase/CMP_P")]
T("/trigger_phase/CMP_P", W50, cmp_p, name="CMP_P: U302.8 -> R306 -> R311 -> C308", z=50, rf=True, ch=0)
T("/trigger_phase/CMP_N", W50, [q1_, P("C312", "@/trigger_phase/CMP_N")], name="CMP_N: U302.1 -> R306 -> R312 -> C312",
  z=50, rf=True)
c12 = P("C312", "@Net-(C312-Pad2)")
place2("R310", XN + 1.39, c12[1], "h", "Net-(C312-Pad2)")
T("Net-(C312-Pad2)", W50, [c12, P("R310", "@Net-(C312-Pad2)")], ch=0, rf=True)
g = P("R310", "@GND")
gv(g[0], g[1] - 0.62)
T("GND", W_GND, [g, (g[0], g[1] - 0.62)], ch=0)

# --- U303 TRF37D73 on the axis in the corridor: RFIN pin 2 from the west, RFOUT pin 7 to the east
XU3, YU3 = 11.0, AX + 0.25
blk.place("U303", XU3, YU3, 0)
assert abs(P("U303", "7")[1] - AX) < 1e-6 and P("U303", "7")[0] > XU3
rin = P("U303", "2")
c8p = P("C308", "@Net-(U303-RFIN)")
T("Net-(U303-RFIN)", W50, [c8p, (XP, AX - 0.4), (XP + 0.4, AX), rin], name="RFIN: C308 -> U303.2", z=50, rf=True)
for pn in ("3", "4", "5", "6", "8"):
    x, y = P("U303", pn)
    T("GND", 0.2, [(x, y), (XU3 + (0.3 if x > XU3 else -0.3), y)], ch=0)
for dy in (-0.5, 0.0, 0.5):
    blk.via(XU3, YU3 + dy, "GND", 0.4, 0.2)
# DECOUPLING-7 (24 Nov): VCC pin 1 straight north into C309 on the TOP side (as the other TRF37D73: cap at the pin,
# then the via pair), +3V3 via pair east of the cap pad, GND via east of the GND pad (all x <= 11.3: the pstrobe
# PH_STROBE_N L6 line runs under the corridor at x 11.87)
q = P("U303", "1")
place2("C309", q[0], 13.07, "v", "GND")
c9p, c9g = P("C309", "@+3V3"), P("C309", "@GND")
T("+3V3", 0.25, [q, c9p], ch=0)
for xv_ in (10.75, 11.30):
    V(xv_, c9p[1], "+3V3")
T("+3V3", 0.45, [c9p, (11.30, c9p[1])], ch=0)
gv(10.75, c9g[1])
T("GND", 0.4, [c9g, (10.75, c9g[1])], ch=0)
# --- bias tee (sim/bias_tee/RESULT.md): FB301 pad ON the line; pad 2 -> via pair -> L302 47 uH (B, along the
#     axis) with R382 1 k beside it (B) -> C313 100 n at the cold pad (B) -> +3V3 via pair beyond C313
XFB = 13.08
place2("FB301", XFB, AX + 0.485, "v", "Net-(U303-RFOUT)")
fb2 = P("FB301", "@Net-(FB301-Pad2)")
YLB = 16.2
DXL = 1.1                                   # BIASTEE-6 (24 Nov): choke pad 2 starts 0.25 mm east of the via pair
XL = XFB + 1.4 + DXL
bplace("L302", XL, YLB, 0, side="B")
if P("L302", "@Net-(FB301-Pad2)")[0] > XL:
    pcbnew_fp = blk.b.FindFootprintByReference("L302")
    pcbnew_fp.SetOrientationDegrees(pcbnew_fp.GetOrientationDegrees() + 180)
l2p = P("L302", "@Net-(FB301-Pad2)")
assert abs(l2p[0] - XFB - DXL) < 1e-4
T("Net-(FB301-Pad2)", 0.5, [fb2, (XFB, 17.2)], ch=0)
for yv in (16.6, 17.2):
    V(XFB, yv, "Net-(FB301-Pad2)")
T("Net-(FB301-Pad2)", 0.5, [(XFB, 16.6), (l2p[0], 16.6)], layer="B.Cu", ch=0)
T("Net-(FB301-Pad2)", 0.5, [(XFB, 17.2), (l2p[0], 17.2)], layer="B.Cu", ch=0)
place2("R382", XL, YLB - 2.05, "h", "Net-(FB301-Pad2)", side="B")
for net_, sgn in (("Net-(FB301-Pad2)", -1), ("+3V3", 1)):
    rx, ry = P("R382", "@" + net_)
    lx, ly = P("L302", "@" + net_)
    T(net_, 0.3, [(rx, ry), (lx - sgn * 0.32, ry), (lx, ry + 0.32), (lx, YLB - 1.0)], layer="B.Cu", ch=0)
lp = P("L302", "@+3V3")
place2("C313", lp[0] + 1.8, YLB, "h", "+3V3", side="B")
cpx, cpy = P("C313", "@+3V3")
T("+3V3", 0.5, [lp, (cpx, cpy)], layer="B.Cu", ch=0)
gx_, gy_ = P("C313", "@GND")
gv(gx_, gy_ + 0.65)
T("GND", W_GND, [(gx_, gy_), (gx_, gy_ + 0.65)], layer="B.Cu", ch=0)
for yv in (cpy + 0.65, cpy + 1.25):
    V(cpx, yv, "+3V3")
T("+3V3", 0.5, [(cpx, cpy), (cpx, cpy + 1.25)], layer="B.Cu", ch=0)
# --- C311 1 u, 12 dB pi pad R307 82 / R308 91 / R309 82 (shunts north, GND vias), PH_LINE launch
XC311 = XFB + 0.47 + 0.91 + 0.01
place2("C311", XC311, AX, "h", "Net-(U303-RFOUT)")
T("Net-(U303-RFOUT)", W50, [P("U303", "7"), P("C311", "@Net-(U303-RFOUT)")], name="RFOUT: U303.7 -> FB301 -> C311",
  z=50, rf=True)
XR307 = XC311 + 0.91 + 0.47 + 0.01
XR308 = XR307 + 0.47 + 0.93 + 0.01
XR309 = XR308 + 0.93 + 0.47 + 0.01
place2("R307", XR307, AX - 0.51, "v", "GND")
place2("R308", XR308, AX, "h", "Net-(C311-Pad2)")
place2("R309", XR309, AX - 0.51, "v", "GND")
T("Net-(C311-Pad2)", W50, [P("C311", "@Net-(C311-Pad2)"), P("R308", "@Net-(C311-Pad2)")], name="pad in", z=50, rf=True)
# BIASTEE-5 (24 Nov): pad compensation of the line-driver tee like the pstrobe tees: every in-line pad of FB301 / C311
# whose excess C over the 0.16 mm line exceeds 30 fF gets an L2 cut of the pad size and an L3 no-track / no-via area
# (the board's L3 GND pour stays under it and becomes the reference, 0.68 mm down)
PADCOMP = []
for ref, pn in (("FB301", "1"), ("C311", "1"), ("C311", "2")):
    pd = blk.fps[ref].FindPadByNumber(pn)
    bb_ = pd.GetBoundingBox()
    wx, wy = pcbnew.ToMM(bb_.GetWidth()), pcbnew.ToMM(bb_.GetHeight())
    cx_, cy_ = blk.loc(pd.GetPosition())
    along, across = wx, wy                     # the line runs along x through all three pads
    exc = (c6(across) - c6(W50)) * along
    if exc > 0.030:
        r_ = bl.rect_pts(cx_ - wx / 2, cy_ - wy / 2, cx_ + wx / 2, cy_ + wy / 2)
        blk.keepout(r_, ("In1.Cu",))
        blk.keepout(r_, ("In2.Cu",), tracks=True, vias=True).SetDoNotAllowCopperPour(False)
    PADCOMP.append((f"{ref}.{pn}", across, along, exc * 1e3, exc > 0.030))
for ref in ("R307", "R309"):
    g = P(ref, "@GND")
    gv(g[0], g[1] - 0.65)
    T("GND", W_GND, [g, (g[0], g[1] - 0.65)], ch=0)
X_STEP = X0 - 1.6
T("Net-(D301-common)", W50, [P("R308", "@Net-(D301-common)"), (X_STEP, AX)], name="PH_LINE launch 50 R", z=50, rf=True)
T("Net-(D301-common)", W_LIN, [(X_STEP, AX), (X0 + X_P3, AX)], name=f"PH_LINE launch {W_LIN}", z=round(Z_LIN), rf=True)

# --- U304 SN65LVDS2 (COARSE) west of the network, R311 / R312 470 R taps
XU4, YU4 = 2.0, 10.0
place_cond("U304", XU4, YU4, lambda pp: pp["3"][0] < -0.5 and pp["3"][1] > 0.5)     # rot 0: A bottom-left
pa, pb, pv, pc, pg = (P("U304", k) for k in "34152")
ra_ = P("R311", "@Net-(U304-A)")
ya = ra_[1] + 0.3
T("Net-(U304-A)", W_SIG, [ra_, (ra_[0] - 0.55, ra_[1]), (ra_[0] - 0.85, ya), (pa[0] + 0.3, ya), (pa[0], ya - 0.3), pa], ch=0)
rb_ = P("R312", "@Net-(U304-B)")
V(rb_[0] + 0.55, rb_[1], "Net-(U304-B)")
T("Net-(U304-B)", W_SIG, [rb_, (rb_[0] + 0.55, rb_[1])], ch=0)
XVB = pb[0] + 0.9
V(XVB, pb[1], "Net-(U304-B)")
T("Net-(U304-B)", W_SIG, [pb, (XVB, pb[1])], ch=0)
YB4 = rb_[1] - 0.16                          # 24 Nov: lane 0.5 mm lower, clear of the U302 decoupling GND via
T("Net-(U304-B)", W_SIG, [(XVB, pb[1]), (XVB + YB4 - pb[1], YB4), (rb_[0] + 0.55 - 0.16, YB4), (rb_[0] + 0.55, rb_[1])],
  layer="B.Cu", ch=0)
YV4 = pv[1] - 0.55
V(pv[0], YV4, "+3V3")
T("+3V3", 0.5, [pv, (pv[0], YV4)], ch=0)
place2("C310", pv[0] + 0.48, YV4, "h", "+3V3", side="B")
g = P("C310", "@GND")
gv(g[0] + 0.43, g[1])
T("GND", 0.3, [g, (g[0] + 0.43, g[1])], layer="B.Cu", ch=0)
gv(XU4, YU4)
T("GND", 0.4, [pg, (XU4, YU4)], ch=0)
XCV = pc[0] + 0.76
V(XCV, pc[1], "/COARSE")
T("/COARSE", W_SIG, [pc, (XCV, pc[1])], ch=0)
XCO = 4.45
XTP3 = 5.6
bplace("TP303", XTP3, pc[1], 0, side="B")
T("/COARSE", W_SIG, [(XCV, pc[1]), (XTP3, pc[1])], layer="B.Cu", ch=0)
T("/COARSE", W_SIG, [(XTP3, pc[1]), (XTP3, pc[1] - 1.05), (XCO, pc[1] - 1.05 - (XTP3 - XCO)), (XCO, 0.0)], layer="B.Cu", ch=0)
blk.iface("/COARSE", XCO, 0.0, "B.Cu", "N", "slow", W_SIG, "SN65LVDS2 output to the FPGA")

# ============================================================================= ground stitching (ZONES-1 / -2, 24 Nov)
# The board's L3 GND webs between the hold-node windows and the L6 GND fingers between the tap-row lanes had no via
# inside the tap row.  One GND via per meander cell at (tap x + 1.9, axis + 1.95): above the meander top segment
# (0.23 mm), west of the next cell's 1 k pad (0.18), east of the board's tap-row L6 lanes (they sit at tap x
# + 0.69..1.39), east of the next cell's B summing tap only on the K side (so K side only), in the L3 web outside both
# windows.  Cells 0-14 (cell 15 has no meander; a board +2V5 L3 track passes there): pitch 4.514 mm.  Further vias
# in free spots found against the integrated board (scope-fe.kicad_pcb, all layers, >= 0.15 mm): west end of the row,
# the north ends of the L6 fingers x 40-44 and 80.8-84.4, the far end of the L3 island under the front column and the
# B island east of the VSW network.
STITCH = [(XT[n] + 1.9, AX + 1.95) for n in range(NT - 1)]
STITCH += [(26.85, AX + 1.1), (42.0, 3.75), (42.0, 10.75), (82.7, 10.0), (6.5, 17.3), (20.1, 1.5)]
for xy in STITCH:
    gv(*xy)

SUPPLY_VIAS = {}
for t in blk.b.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() in ("+3V3", "+2V5", "-2V5"):
        SUPPLY_VIAS.setdefault(t.GetNetname(), []).append(blk.loc(t.GetPosition()))

# ============================================================================= zones
# In1 = GND over the block (the integrator replaces it), cut-outs under the hold nodes and the SMA pin
outline = [(0, 0), (BW, 0), (BW, BH), (26.5, BH), (26.5, 18.0), (9.5, 18.0), (9.5, BH), (0, BH), (0, 0)]
outline = [(0, 0), (BW, 0), (BW, BH), (26.5, BH), (26.5, 18.0), (9.5, 18.0), (9.5, BH), (0, BH)]
top_ol = [(0, 0), (BW, 0), (BW, BH), (26.5, BH), (26.5, 18.0), (9.5, 18.0), (9.5, BH), (0, BH)]
north_cut = [(9.5, 2.5), (26.5, 2.5), (26.5, 12.0), (9.5, 12.0)]
IN = 0.2
blk_ol = [(IN, IN), (BW - IN, IN), (BW - IN, BH - IN), (26.5 + IN, BH - IN), (26.5 + IN, 18.0 - IN),
          (9.5 - IN, 18.0 - IN), (9.5 - IN, BH - IN), (IN, BH - IN)]
blk.zone("GND", ["In1.Cu"], blk_ol, clearance=0.2)
blk.zone("GND", ["In4.Cu"], blk_ol, clearance=0.2)      # 24 Nov: L5 solid GND (as in pstrobe), so the stitching vias
                                                       # tie two planes in the block file too
blk.keepout(north_cut, ("F.Cu", "In1.Cu", "In3.Cu", "B.Cu"))
# node / SMA cut-outs: L2 (block In1) AND L4 (block In2 -> In3) cleared; the integrator clears L3 under every L2
# cut-out, so the hold nodes reference L5 (1.37 mm) as they referenced In2 (1.29 mm) on the 4-layer board
for c in CUT:
    blk.keepout(c, ("In1.Cu", "In2.Cu", "In3.Cu"))
blk.keepout(bl.rect_pts(0.0, YJ - 0.95, jx + 1.9, YJ + 0.95), ("In1.Cu", "In2.Cu", "In3.Cu"))
XV0, XV1 = XT[0] - 3.2, X15 + 1.5
blk.zone("VTAP_N", ["In3.Cu"], bl.rect_pts(XV0, AX - (Y_RV + 1.4), XV1, AX - 0.15), clearance=0.3, prio=1)
blk.zone("VTAP_P", ["In3.Cu"], bl.rect_pts(XV0, AX + 0.15, XV1, AX + Y_RV + 1.4), clearance=0.3, prio=1)
# F.Cu GND pour (keeps 2 w from every RF trace) - the integrator may keep or replace it
blk.zone("GND", ["F.Cu"], blk_ol, clearance=0.2, prio=0)
blk.keepout(bl.rect_pts(XT[0] + X_P12 - PITCH / 2 - 0.1, AX - (YL + W_STR / 2 + 2 * W_STR),
                        XE + 0.1, AX + YL + W_STR / 2 + 2 * W_STR), ("F.Cu",))
for q, w in KEEP:
    blk.rf_keepout(q, w)
blk.keepout(bl.rect_pts(0.0, 0.0, 9.5, BH), ("F.Cu",))       # dense front column: no top pour
# (22 Nov: the north-strip F pour keep-out x 9.5-26.5 is gone: C301 / C306 are on B now and the PH_STROBE pair
# runs there on L1, so the strip gets its ground pour)

# ============================================================================= drawings, save
blk.edge_rect(0, 0, BW, BH, layer="Dwgs.User")
for a, c in ((north_cut[0], north_cut[1]), (north_cut[1], north_cut[2]), (north_cut[2], north_cut[3]),
             (north_cut[3], north_cut[0])):
    blk.line(*a, *c, layer="Dwgs.User")
for a, c in (((9.5, 18.0), (26.5, 18.0)), ((26.5, 18.0), (26.5, BH)), ((9.5, 18.0), (9.5, BH))):
    blk.line(*a, *c, layer="Dwgs.User")
blk.text("PHASE", 40.0, 21.6, 0.8, layer="F.Fab")
blk.text("EXT_CLK", 1.6, 8.6, 0.8, layer="F.Fab")
for n, x in enumerate(XT):
    blk.text(str(n), x + 1.85, AX + YL + 1.0, 0.8, layer="F.Fab")

def silk_fix():
    """RULE 9: footprint silk that touches a pad (any footprint, same side) or another footprint's silk
    moves to the Fab layer of its side"""
    mm_ = pcbnew.FromMM
    pads = [(p, p.GetBoundingBox()) for f in blk.b.GetFootprints() for p in f.Pads()]
    fab = {pcbnew.F_SilkS: pcbnew.F_Fab, pcbnew.B_SilkS: pcbnew.B_Fab}
    cu = {pcbnew.F_SilkS: pcbnew.F_Cu, pcbnew.B_SilkS: pcbnew.B_Cu}
    keep, n = [], 0
    for f in blk.b.GetFootprints():
        for it in list(f.GraphicalItems()):
            lay = it.GetLayer()
            if lay not in fab:
                continue
            bb = it.GetBoundingBox()
            bb.Inflate(mm_(0.12))
            if any(p.IsOnLayer(cu[lay]) and bb.Intersects(pb) for p, pb in pads):
                it.SetLayer(fab[lay])
                n += 1
            else:
                keep.append((f.GetReference(), it, bb))
    for i, (r, it, bb) in enumerate(keep):
        if any(r2 != r and it2.GetLayer() == it.GetLayer() and bb.Intersects(bb2) for r2, it2, bb2 in keep[:i]):
            it.SetLayer(fab[it.GetLayer()])
            n += 1
    return n


print("silk items moved to Fab:", silk_fix())
path = blk.save(HERE)

# ============================================================================= tables
print(f"PITCH {PITCH} mm, W_STR {W_STR}, W_LIN {W_LIN}, L_LIN {L_LIN:.3f} mm/tap, Y_M {Y_M:.3f}, YL {YL}")
print("6-layer microstrip L1/L2 (h %.4f, er %.1f, mask):" % (H6, ER6))
for w_ in (0.09, 0.10, 0.11, 0.12, 0.14, W50, 0.20, 0.26, 0.36, 0.45, 0.56):
    print(f"  w {w_:.2f}  Z0 {z6(w_):6.2f} R  {ps6(w_):.3f} ps/mm  {c6(w_):.4f} pF/mm")
print("line     width  Z0 unl.  load (gate + pad)        section            loaded delay  loaded Z")
print(f"PSTRB    {W_STR:.2f}  {Z_STR:6.2f}  {CL_STR:.3f} pF ({C_GATE_STR + C_MISC_STR:.2f} + {C_PAD_STR:.3f})  {PITCH:.3f} mm {TDU_STR:5.2f} ps  {TD_STR:5.2f} ps  {ZL_STR:5.2f} R")
print(f"PH_LINE  {W_LIN:.2f}  {Z_LIN:6.2f}  {CL_LIN:.3f} pF ({C_GATE_LIN:.2f} + {C_PAD_LIN:.3f})  {L_LIN:.3f} mm {TDU_LIN:5.2f} ps  {TD_LIN_A:5.2f} ps  {ZL_LIN:5.2f} R")
print(f"effective tap spacing (line - strobe) {TD_LIN_A - TD_STR:.2f} ps (4-layer design 70.00 - 40.00 = 30.00 model)")
print(f"meander same-net gaps: X_P3..XU {XU - X_P3 - W_LIN:.3f}, XU..XD {XD - XU - W_LIN:.3f}, pad3..XU {XU - W_LIN / 2 - X_P3 - PAD3_HALF_X:.3f} mm; YL_MIN {YL_MIN:.2f} (YL {YL})")
cell_pts = bl.chamfer(cell_path(Y_M), CH_M)
print(f"drawn cell length {bl.plen(cell_pts):.3f} mm (target {L_LIN:.3f})")
print(f"tap 0 x {X0:.3f}, tap 15 x {X15:.3f} (local), axis y {AX}")
for nm in blk.routes:
    r = blk.routes[nm]
    L = blk.route_len(nm)
    if r["z"]:
        print(f"  {nm:45s} w {r['width']:.2f} L {L:7.3f} mm  {L * ps6(r['width']):7.1f} ps")
print("summing taps A = B:", SUM_LEN[0][1], SUM_LEN[0][3])
REFS = [r for r, c in NL.comps.items() if c["sheet"] == "/trigger_phase/"] + ["J102", "R122", "C615", "C620"]
print("pad compensation (excess C vs. the 0.16 mm line; L2 cut + L3 no-track/no-via if > 30 fF):")
for row in PADCOMP:
    print(f"  {row[0]:8s} across {row[1]:.2f} along {row[2]:.2f} excess {row[3]:6.1f} fF  {'L2 cut' if row[4] else '-'}")
print("ground stitching vias:", len(STITCH))
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
    cut = x1_ > 9.5 + 1e-3 and x0_ < 26.5 - 1e-3 and ((y1_ > 2.5 + 1e-3 and y0_ < 12.0 - 1e-3) or y1_ > 18.0 + 1e-3)
    if not inside or cut:
        out.append((it.GetNetname(), round(x0_, 2), round(y0_, 2), round(x1_, 2), round(y1_, 2)))
print("items outside the block area:", len(out), out[:8])
print(f"mixed-width RF nets (PH_LINE {W50}/{W_LIN}, PSTRB {W_STR}): deviations", bad)
json.dump({k: v for k, v in res.items() if k != "details"}, open("/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board/phase_check.json", "w"), indent=1)
if "--render" in sys.argv:
    S = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board"
    bl.render(path, os.path.join(HERE, "phase.png"), layers=("F.Cu", "B.Cu", "F.SilkS", "F.Fab", "Dwgs.User"),
              tmpdir=S)
    bb = b2.ComputeBoundingBox(False)
    ox, oy = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())
    for nm_, (x0_, x1_) in (("phase_detail.png", (26.0, 40.0)), ("front_chain_detail.png", (0.0, 30.0)), ("phase_end.png", (86.0, 99.5))):
        bl.render(path, os.path.join(HERE if nm_ != "phase_end.png" else S, nm_),
                  layers=("F.Cu", "B.Cu", "F.Fab", "Dwgs.User"),
                  crop=(100 + x0_ - ox, 100 - oy, 100 + x1_ - ox, 122.5 - oy), tmpdir=S)
