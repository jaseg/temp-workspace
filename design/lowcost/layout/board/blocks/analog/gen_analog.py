#!/usr/bin/env python3
"""ANALOG block of the scope-fe board: input stage (SMA, divider, BUF802, OPA197 servo) + sampler (bridge,
hold, level shifter) + the complete sampler strobe chain (S_STROBE_P -> 47 R -> 100 nF -> TRF37D73 #1 with
bias tee -> 12 dB pi pad -> TRF37D73 #2 with bias tee -> 100 nF -> clip node (80 ps shorted stub TL401 /
NT401, BAT15-03W clamp) -> balun T401 -> STRB_A / STRB_K arms -> bridge).

Geometry ported from layout/input_stage/gen_input_stage.py (frame FI) and layout/sampler/gen_sampler.py
(frame FS, origin = bridge centre); every part comes from the netlist through boardlib.Block.place.
Run: cd blocks/analog && python3 gen_analog.py
"""
import sys, os, math
sys.path.insert(0, "../..")
import boardlib as bl
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board/analog"
os.makedirs(SCR, exist_ok=True)
BW, BH = 56.0, 21.5                       # FLOORPLAN block rectangle (board x 0, y 1)
blk = bl.Block("analog")
nl = blk.nl
W = bl.W50
W_HZ, W_SIG, W_PWR, W_GND, W_HOLD, W_GUARD = 0.15, 0.2, 0.5, 0.4, 0.15, 0.10
N = bl.net_of
ALIAS = {
    # input stage
    "BUF_IN": N("U101", 2), "IN_BIAS_MID": N("R105", 2), "IN_BIAS": N("U101", 3), "R_BIAS": N("U101", 7),
    "CLL": N("U101", 14), "CLH": N("U101", 15), "S1": N("R114", 2), "S2": N("R115", 2), "TAP": N("R116", 2),
    "FB": N("U102", 4), "OPA_OUT": N("U102", 1), "RF2_MID": N("R120", 2), "RT_MID": N("R112", 2),
    "IN_AUX": N("U101", 4), "VIN": N("J101", 1), "GA": N("C101", 2),
    # sampler
    "BRG_IN": N("D201", 3), "HOLD": N("D202", 3), "BRG_A": N("D201", 1), "BRG_K": N("D201", 2),
    "BIAS_A_N": N("C201", 2), "BIAS_K_N": N("C202", 2), "HOLD_OUT": N("U201", 1), "HOLD_FB": N("U201", 4),
    "SHIFT_OUT": N("U202", 1), "SHIFT_IN": N("U202", 4),
    # strobe chain
    "CLIP": N("T401", 1), "TRF2_OUT": N("U402", 7), "TRF2_RFIN": N("U402", 2), "TRF2_IN": N("C406", 1),
    "TRF2_BIAS": N("FB402", 2), "TRF1_OUT": N("U401", 7), "TRF1_BIAS": N("FB401", 2), "PADN": N("C405", 2),
    "TRF1_RFIN": N("U401", 2), "TRF1_IN": N("C401", 1), "STUB_END": N("NT401", 1), "N1": N("R405", 2),
    "N2": N("C411", 2),
}


def A(n):
    return ALIAS.get(n) or bl.canon(n)


class Frame:
    """fragment coordinates -> block-local (pure translation)"""

    def __init__(s, dx, dy):
        s.dx, s.dy = dx, dy

    def T(s, p):
        return p if isinstance(p[0], str) else (p[0] + s.dx, p[1] + s.dy)

    def pad(s, ref, num):
        if isinstance(num, str) and num.startswith("@"):
            num = "@" + A(num[1:])
        x, y = blk.pad(ref, num)
        return (x - s.dx, y - s.dy)

    def track(s, net, w, pts, layer="F.Cu", name=None, z=None, ch=0.2):
        pts = [(p[0], ("@" + A(p[1][1:])) if str(p[1]).startswith("@") else p[1]) if isinstance(p[0], str) else p
               for p in pts]
        q = blk.track(A(net), w, [s.T(p) for p in pts], layer, name=name, z=z, ch=ch)
        if z:
            RFPOLY.append((q, w))
        return q

    def via(s, x, y, net, dia=bl.VIA_D, drill=bl.VIA_DRILL):
        return blk.via(x + s.dx, y + s.dy, A(net), dia, drill)

    def place(s, ref, x, y, rot=0, side="F"):
        # local helper: boardlib.Block.place flips before the footprint is on the board (segfaults in
        # pcbnew 7.0.11), so place on F and flip after it was added
        fp = blk.place(ref, x + s.dx, y + s.dy, rot, "F")
        if side == "B":
            fp.Flip(fp.GetPosition(), True)
            fp.Reference().SetLayer(pcbnew.B_Fab)
        return fp

    def two(s, ref, x, y, orient, na, side="F"):
        """2-terminal part: the pad on net na left ('h') or up ('v'); rotation chosen from the netlist"""
        na = A(na)
        for rot in ((0, 180) if orient == "h" else (90, 270)):
            fp = s.place(ref, x, y, rot, side)
            px, py = s.pad(ref, "@" + na)
            if (orient == "h" and px < x - 1e-3) or (orient == "v" and py < y - 1e-3):
                return fp
            blk.b.Remove(fp)
            del blk.fps[ref]
        raise ValueError((ref, na))

    def shift_to(s, ref, num, x=None, y=None):
        """move a placed part so that pad num lands at x / y (frame)"""
        fp = blk.fps[ref]
        px, py = s.pad(ref, num)
        dx = 0 if x is None else x - px
        dy = 0 if y is None else y - py
        fp.Move(pcbnew.VECTOR2I(bl.mm(dx), bl.mm(dy)))

    def keepout(s, pts, layers=("F.Cu",)):
        blk.keepout([s.T(p) for p in pts], layers)

    def zone(s, net, layers, pts, clearance=0.15, prio=3, minw=0.15):
        blk.zone(A(net), layers, [s.T(p) for p in pts], clearance, prio, minw)


RFPOLY = []
gv = lambda fr, x, y: fr.via(x, y, "GND")
rect = bl.rect_pts

# ============================================================================= INPUT STAGE (frame FI)
OYI = 4.0                                  # input fragment origin at block (0, 4.0): SMA clear of the M3 hole
FI = Frame(0.0, OYI)
Y0 = 6.3
X_PAD_END = 3.7
X_TAPER = X_PAD_END + 0.8
X_CT = X_TAPER + 0.07 + 0.78
XA = 5.05
x_ga = X_CT + 0.88
x_rg = x_ga + 0.88
x_bi = x_rg + 0.51
XU = x_bi + 3.125
YU = Y0 + 0.25
TAP_DY = W / 2 - 0.08 + 0.27 + 0.51
V = lambda ref, x, y, top, side="F": FI.two(ref, x, y, "v", top, side)
Hz = lambda ref, x, y, left, side="F": FI.two(ref, x, y, "h", left, side)

FI.place("J101", 2.1, Y0, 270)
Hz("C101", X_CT, Y0, "VIN")
V("R114", XA, Y0 + TAP_DY, "VIN")
Hz("R104", x_rg, Y0, "GA")
V("C102", x_ga, Y0 + 1.3, "GA")
V("R105", x_bi, Y0 + 1.3, "BUF_IN")
V("R106", x_bi, Y0 + 2.9, "IN_BIAS_MID")
FI.place("U101", XU, YU, 0)
X_P11 = XU + 1.875
x_sp = X_P11 + 0.67 + 0.32
V("R112", x_sp, Y0 + TAP_DY, "BUF_OUT_S")
V("R113", x_sp, Y0 + TAP_DY + 1.6, "RT_MID")
X_R118 = x_sp + 0.75                       # pulled 0.2 mm left (fragment 0.95) so R201 sits 2.8 mm from OUT
V("R118", X_R118, Y0 - TAP_DY, "FB")
V("C108", XU - 2.4, Y0 - 1.36, "GND")      # VS+ pin 1
V("C109", x_sp, Y0 - 1.36, "GND")          # VSO+ pin 12 (fragment C117)
y_bot_cap = YU + 1.875 + 0.2 + 0.27 + 0.51
V("C112", XU - 0.65, y_bot_cap, "-5V")     # VS- pins 5/6 (fragment C110)
V("R107", XU + 0.25, y_bot_cap, "R_BIAS")
V("C113", XU + 1.15, y_bot_cap, "-5V")     # pins 8/10 (fragment C111)
Y_CL = Y0 - 3.4
for ref, x, top in (("R109", XU - 3.1, "GND"), ("R108", XU - 2.15, "+2V5"), ("C103", XU - 1.2, "GND"),
                    ("C104", XU + 1.2, "GND"), ("R110", XU + 2.15, "-2V5"), ("R111", XU + 3.1, "GND")):
    V(ref, x, Y_CL - 0.51, top)
FI.place("TP101", XU - 4.3, Y_CL - 1.2)
FI.place("TP102", XU + 4.3, Y_CL - 1.2)
V("R115", XA, Y0 + TAP_DY + 1.6, "S1")
V("R116", XA, Y0 + TAP_DY + 3.2, "S2")
XO, YO = XA + 0.95, Y0 + 6.8
FI.place("U102", XO, YO, 270)
Y_P3O = YO - 1.1375
Hz("R117", XA - 1.13, YO - 2.05, "GND")
Hz("C105", XA - 1.13, Y_P3O, "GND")
V("C114", XO, YO - 1.1, "-5V", side="B")           # OPA V- (fragment C113)
V("C110", XO + 0.95, YO + 1.0, "GND", side="B")    # OPA V+ (fragment C112)
x_p1o = XO + 0.95
Hz("R121", x_p1o + 0.51, Y0 + 4.3, "OPA_OUT")
V("C107", x_bi + 1.02, Y0 + 4.81, "IN_AUX")
FI.place("TP103", XA + 1.25, Y0 + 3.4)
X_CI = XO + 1.9
V("C106", X_CI, YO - 0.2, "OPA_OUT")
Y_FB = YO + 2.25
Hz("R120", X_CI + 0.27, Y_FB, "FB")
V("R119", XO + 0.5, Y_FB + 0.51, "FB")
WI = 15.3
FI.place("RV101", WI - 3.25, YO + 1.75, 90)
YJ = 17.6 - 0.9
V("C116", 1.15, YJ - 2.4, "GND", side="B")         # 10u -5V bulk (bottom)
V("C111", 2.9, YJ - 2.4, "GND", side="B")          # 10u +5V bulk (bottom, fragment C115)
V("C115", X_P11 + 0.3, Y0 + 2.45, "-5V", side="B") # 100n -5V at the pin-10 via (bottom)
FI.place("TP104", 4.2, YJ + 0.2)

# --- routing (fragment geometry)
FI.zone("VIN", ["F.Cu"], [(X_PAD_END - 0.3, Y0 - 0.635), (X_PAD_END, Y0 - 0.635), (X_TAPER, Y0 - W / 2),
                          (X_TAPER, Y0 + W / 2), (X_PAD_END, Y0 + 0.635), (X_PAD_END - 0.3, Y0 + 0.635)],
        clearance=0.25, prio=5, minw=0.1)
FI.track("VIN", W, [(X_TAPER - 0.05, Y0), ("C101", "1")], name="VIN: SMA taper -> Ctop")
FI.track("VIN", W, [("R114", "@VIN"), (XA, Y0)])
FI.keepout(rect(XA - 0.93, Y0 + 0.2, XA + 0.93, FI.pad("R114", "@VIN")[1] + 0.93))
for sy in (-1, 1):
    gv(FI, 3.9, Y0 + sy * 3.8)
FI.track("GA", 0.3, [("C101", "2"), ("R104", "@GA")])
FI.track("GA", 0.3, [(x_ga, Y0), ("C102", "@GA")])
y_cbv = FI.pad("C102", "@GND")[1] + 0.64
gv(FI, x_ga, y_cbv)
FI.track("GND", W_GND, [("C102", "@GND"), (x_ga, y_cbv)])
p2, p3, p4 = FI.pad("U101", "2"), FI.pad("U101", "3"), FI.pad("U101", "4")
FI.track("BUF_IN", W_HZ, [("R104", "@BUF_IN"), p2])
FI.track("BUF_IN", 0.3, [("R104", "@BUF_IN"), ("R105", "@BUF_IN")])
FI.track("IN_BIAS_MID", 0.3, [("R105", "@IN_BIAS_MID"), ("R106", "@IN_BIAS_MID")])
xb = x_bi + 0.67
r1062 = FI.pad("R106", "@IN_BIAS")
FI.track("IN_BIAS", W_HZ, [p3, (XU - 2.0, p3[1]), (xb, p3[1] + XU - 2.0 - xb), (xb, Y0 + 2.95),
                          (xb - (r1062[1] - Y0 - 2.95), r1062[1]), r1062])
xa_ = xb + 0.35
c107 = FI.pad("C107", "@IN_AUX")
FI.track("IN_AUX", W_SIG, [p4, (xa_ + 0.2, p4[1]), (xa_, p4[1] + 0.2), (xa_, c107[1]), c107])
FI.track("IN_AUX", 0.3, [("R121", "@IN_AUX"), c107])
c1072 = FI.pad("C107", "@GND")
gv(FI, c1072[0], c1072[1] + 0.7)
FI.track("GND", W_GND, [c1072, (c1072[0], c1072[1] + 0.7)])
# U101 supplies
p1, p12 = FI.pad("U101", "1"), FI.pad("U101", "12")
c108 = FI.pad("C108", "@+5V")
FI.track("+5V", 0.25, [p1, (c108[0] + 0.55, p1[1]), (c108[0] + 0.3, c108[1] + 0.05)])
for y in (Y0 - 1.15, Y0 - 1.7):
    FI.via(XU - 1.55, y, "+5V")
FI.zone("+5V", ["F.Cu"], rect(c108[0] - 0.32, Y0 - 1.95, XU - 1.33, Y0 - 0.68))
c1081 = FI.pad("C108", "@GND")
gv(FI, c108[0], Y0 - 2.55)
FI.track("GND", W_GND, [c1081, (c108[0], Y0 - 2.55)])
c117 = FI.pad("C109", "@+5V")
FI.track("+5V", 0.25, [p12, (X_P11 + 0.12, p12[1]), (X_P11 + 0.12 + p12[1] - c117[1], c117[1]), c117])
for xy in ((XU + 1.5, Y0 - 1.2), (XU + 1.75, Y0 - 1.85)):
    FI.via(*xy, "+5V")
FI.zone("+5V", ["F.Cu"], [(XU + 1.2, Y0 - 0.85), (XU + 1.2, Y0 - 2.15), (XU + 2.05, Y0 - 2.15), (XU + 2.05, Y0 - 1.15),
                          (c117[0] + 0.32, Y0 - 1.15), (c117[0] + 0.32, Y0 - 0.85), (XU + 1.95, Y0 - 0.85),
                          (XU + 1.95, Y0 - 0.85)])
gv(FI, c117[0], Y0 - 2.55)
FI.track("GND", W_GND, [("C109", "@GND"), (c117[0], Y0 - 2.55)])
p5, p6, p7, p8, p10 = (FI.pad("U101", n) for n in ("5", "6", "7", "8", "10"))
c110, c111 = FI.pad("C112", "@-5V"), FI.pad("C113", "@-5V")
FI.zone("-5V", ["F.Cu"], [(p5[0] - 0.13, YU + 1.3), (p6[0] + 0.13, YU + 1.3), (p6[0] + 0.13, YU + 2.05),
                          (c110[0] + 0.32, c110[1] - 0.2), (c110[0] + 0.32, c110[1] + 0.3), (XU - 1.65, c110[1] + 0.6),
                          (XU - 1.65, YU + 1.95), (p5[0] - 0.13, YU + 1.95)])
FI.track("-5V", 0.25, [p5, (p5[0], YU + 2.0), c110])
FI.track("-5V", 0.25, [p6, (p6[0], YU + 1.95), c110])
for y in (Y0 + 2.45, Y0 + 3.05):
    FI.via(XU - 1.35, y, "-5V")
FI.zone("-5V", ["F.Cu"], [(p8[0] - 0.13, YU + 1.3), (p8[0] + 0.13, YU + 1.3), (XU + 1.75, YU + 1.3),
                          (XU + 1.75, YU + 2.45), (c111[0] + 0.32, YU + 2.45), (c111[0] + 0.32, c111[1] + 0.3),
                          (c111[0] - 0.32, c111[1] + 0.3), (p8[0] - 0.13, YU + 2.0)])
FI.track("-5V", 0.25, [p8, (p8[0], YU + 1.95), c111])
FI.track("-5V", 0.25, [p10, (X_P11 + 0.05, p10[1]), (X_P11 + 0.3, p10[1] + 0.25), (X_P11 + 0.3, Y0 + 1.45)])
FI.via(X_P11 + 0.3, Y0 + 1.45, "-5V")
FI.track("-5V", 0.4, [(X_P11 + 0.3, Y0 + 1.45), ("C115", "@-5V")], layer="B.Cu")
c1152 = FI.pad("C115", "@GND")
gv(FI, c1152[0], c1152[1] + 0.65)
FI.track("GND", W_GND, [c1152, (c1152[0], c1152[1] + 0.65)], layer="B.Cu")
for xy in ((XU + 1.5, Y0 + 1.7), (XU + 1.75, Y0 + 2.35)):
    FI.via(*xy, "-5V")
FI.track("R_BIAS", 0.25, [p7, ("R107", "@R_BIAS")])
yv = FI.pad("C112", "@GND")[1] + 0.68
for ref, net in (("C112", "GND"), ("R107", "-5V"), ("C113", "GND")):
    x, y = FI.pad(ref, "@" + net)
    FI.via(x, yv, net)
    FI.track(net, W_GND, [(x, y), (x, yv)])
for dx in (-0.42, 0.42):
    for dy in (-0.42, 0.42):
        FI.via(XU + dx, YU + dy, "GND")
# clamp dividers
p14, p15 = FI.pad("U101", "14"), FI.pad("U101", "15")
for p_, ref, net in ((p15, "C103", "CLH"), (p14, "C104", "CLL")):
    xc = FI.pad(ref, "@" + net)[0]
    d = abs(xc - p_[0])
    FI.track(net, W_SIG, [p_, (p_[0], Y_CL + d), (xc, Y_CL)])
FI.track("CLH", 0.3, [("R109", "@CLH"), ("C103", "@CLH")])
FI.track("CLL", 0.3, [("C104", "@CLL"), ("R111", "@CLL")])
for tpr, rr, net, sg in (("TP101", "R109", "CLH", 1), ("TP102", "R111", "CLL", -1)):
    tp = FI.pad(tpr, "1")
    r_ = FI.pad(rr, "@" + net)
    FI.track(net, W_SIG, [tp, (tp[0] + sg * (r_[1] - tp[1]), r_[1]), r_])
YCV = 0.55
for ref, top in (("R109", "GND"), ("R108", "+2V5"), ("C103", "GND"), ("C104", "GND"), ("R110", "-2V5"),
                 ("R111", "GND")):
    x, y = FI.pad(ref, "@" + top)
    FI.via(x, YCV, top)
    FI.track(top, W_GND, [(x, y), (x, YCV)])
# outputs: OUT pin -> BUF_OUT_S -> R201 (sampler, below); 49.9R + 0R -> BUF_OUT_T to the south boundary
p11 = FI.pad("U101", "11")
FI.track("BUF_OUT_S", W, [("R112", "@BUF_OUT_S"), (x_sp, Y0)], name="R112 tap", z=50)
FI.track("BUF_OUT_S", W, [("R118", "@BUF_OUT_S"), (X_R118, Y0)], name="R118 tap", z=50)
FI.track("RT_MID", 0.4, [("R112", "@RT_MID"), ("R113", "@RT_MID")])
xt, yt0 = FI.pad("R113", "@BUF_OUT_T")
X_T = 15.75                                  # BUF_OUT_T exit column (FLOORPLAN: analog S, x 15.3)
Y_SOUTH = BH - OYI
q_t = FI.track("BUF_OUT_T", W, [(xt, yt0), (xt, yt0 + 0.9), (X_T, yt0 + 0.9 + X_T - xt), (X_T, Y_SOUTH)],
               name="BUF_OUT_T: 0R -> south boundary", z=50, ch=0.3)
# Rf1 sense: FB via above R118, B.Cu down the right side to the Cint drop
r118 = FI.pad("R118", "@FB")
FI.via(r118[0], Y0 - 2.1, "FB")
FI.track("FB", W_SIG, [r118, (r118[0], Y0 - 2.1)])
Y_FBB = YO + 1.1
FI.track("FB", W_SIG, [(r118[0], Y0 - 2.1), (r118[0], Y_FBB - 0.7), (r118[0] - 0.7, Y_FBB), (X_CI, Y_FBB)],
         layer="B.Cu")
FI.via(X_CI, Y_FBB, "FB")
# alpha string, servo
FI.track("S1", 0.3, [("R114", "@S1"), ("R115", "@S1")])
FI.track("S2", 0.3, [("R115", "@S2"), ("R116", "@S2")])
p3o = FI.pad("U102", "3")
FI.track("TAP", 0.3, [("R116", "@TAP"), p3o])
r1172 = FI.pad("R117", "@TAP")
FI.track("TAP", W_SIG, [r1172, (XA, r1172[1])])
FI.track("TAP", 0.3, [("C105", "@TAP"), p3o])
for ref in ("R117", "C105"):
    x, y = FI.pad(ref, "@GND")
    gv(FI, x - 0.7, y)
    FI.track("GND", W_GND, [(x, y), (x - 0.7, y)])
p2o, p5o, p1o, p4o = FI.pad("U102", "2"), FI.pad("U102", "5"), FI.pad("U102", "1"), FI.pad("U102", "4")
FI.via(p2o[0], YO - 2.2, "-5V")
FI.track("-5V", 0.6, [p2o, (p2o[0], YO - 2.2)])
FI.track("-5V", 0.5, [(p2o[0], YO - 2.2), ("C114", "@-5V")], layer="B.Cu")
gv(FI, XO, YO)
FI.track("GND", 0.5, [("C114", "@GND"), (XO, YO)], layer="B.Cu")
c112 = FI.pad("C110", "@GND")
FI.track("GND", 0.5, [c112, (c112[0], c112[1] - 0.05), (c112[0] - (c112[1] - 0.05 - YO), YO), (XO + 0.05, YO)], layer="B.Cu")
FI.via(XO, p5o[1], "+5V")
FI.track("+5V", 0.6, [p5o, (XO, p5o[1])])
c1122 = FI.pad("C110", "@+5V")
FI.track("+5V", 0.5, [(XO, p5o[1]), (XO + c1122[1] - p5o[1], c1122[1]), c1122], layer="B.Cu")
r121 = FI.pad("R121", "@OPA_OUT")
FI.track("OPA_OUT", W_SIG, [p1o, r121])
tp3 = FI.pad("TP103", "1")
FI.track("OPA_OUT", W_SIG, [tp3, (r121[0], tp3[1] + r121[0] - tp3[0]), r121])
c106 = FI.pad("C106", "@OPA_OUT")
FI.track("OPA_OUT", W_SIG, [p1o, (c106[0] - (c106[1] - p1o[1]), p1o[1]), c106])
FI.track("FB", W_SIG, [p4o, (p4o[0], Y_FB - 0.4), (p4o[0] + 0.4, Y_FB), ("R120", "@FB")])
FI.track("FB", 0.25, [("C106", "@FB"), (X_CI, Y_FBB)])
FI.track("FB", 0.25, [(X_CI, Y_FBB), (X_CI, Y_FB)])
rv1 = FI.pad("RV101", "1")
r1202 = FI.pad("R120", "@RF2_MID")
FI.track("RF2_MID", 0.3, [r1202, (r1202[0] + rv1[1] - r1202[1], rv1[1]), rv1])
x, y = FI.pad("RV101", "3")
gv(FI, x + 1.5, y)
FI.track("GND", W_GND, [(x, y), (x + 1.5, y)])
x, y = FI.pad("RV101", "2")
gv(FI, x, y + 1.5)
FI.track("GND", W_GND, [(x, y), (x, y + 1.5)])
# VOFS: Rofs pad -> via -> B.Cu stub to the south boundary
r1192 = FI.pad("R119", "@VOFS")
X_VOFS = r1192[0] - 0.6
FI.track("VOFS", W_SIG, [r1192, (r1192[0], r1192[1] + 0.3), (X_VOFS, r1192[1] + 0.9)])
FI.via(X_VOFS, r1192[1] + 0.9, "VOFS")
FI.track("VOFS", W_SIG, [(X_VOFS, r1192[1] + 0.9), (X_VOFS, Y_SOUTH)], layer="B.Cu")
# bulk caps (bottom): supply pad -> via pair to In2, GND pad -> via
for ref, net in (("C116", "-5V"), ("C111", "+5V")):
    x, y = FI.pad(ref, "@" + net)
    FI.via(x - 0.35, y + 0.95, net)
    FI.via(x + 0.35, y + 0.95, net)
    FI.track(net, 0.6, [(x, y), (x, y + 0.95)], layer="B.Cu")
    FI.track(net, 0.6, [(x - 0.35, y + 0.95), (x + 0.35, y + 0.95)], layer="B.Cu")
    x, y = FI.pad(ref, "@GND")
    gv(FI, x, y - 0.95)
    FI.track("GND", 0.6, [(x, y), (x, y - 0.95)], layer="B.Cu")
x, y = FI.pad("TP104", "1")
gv(FI, x + 0.95, y)
FI.track("GND", W_GND, [(x, y), (x + 0.95, y)])
# keep-outs / cut-outs of the input stage
FI.keepout(rect(0, Y0 - 0.9, X_PAD_END, Y0 + 0.9), ("In1.Cu",))
CUT_HZ = (FI.pad("C101", "2")[0] - 0.3, Y0 - 0.45, XU - 1.1, Y0 + 1.1)
FI.keepout(rect(*CUT_HZ), ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"))
g = W / 2 + 0.75
FI.keepout(rect(X_TAPER - 0.05, Y0 - g, FI.pad("C101", "2")[0], Y0 + g))
for sg in (-1, 1):                             # beside the launch taper (the taper polygon itself is VIN copper)
    FI.keepout(rect(X_PAD_END, Y0 + sg * 0.65, X_TAPER, Y0 + sg * g))

# ============================================================================= SAMPLER (frame FS, bridge centre)
D1X, D2X = -1.7, 1.7
XR201 = X_R118 + 0.32 + 0.05 + 0.78       # R201 pad 1 abuts the R118 tap pad (same net)
XBR = XR201 - (D1X - 1.7 - 0.93)
YBR = Y0 + OYI
FS = Frame(XBR, YBR)
FS.place("D201", D1X, 0, 0)
FS.place("D202", D2X, 0, 0)
FS.two("R201", D1X - 1.7 - 0.93, 0, "h", "BUF_OUT_S")
qs = blk.track(A("BUF_OUT_S"), W, [blk.pad("U101", "11"), blk.pad("R201", "@" + A("BUF_OUT_S"))],
               name="BUF_OUT_S: OUT pin -> R201", z=50)
RFPOLY.append((qs, W))
FS.track("BRG_IN", W, [("R201", "@BRG_IN"), ("D201", "3")], name="BRG_IN: R201 -> D201.3", z=50)
XM = (FS.pad("D201", "1")[0] + FS.pad("D202", "1")[0]) / 2
YR = 1.72
XV, YA = 9.9, 4.07
XB = XV + 3.04
VB_X = {-1: -4.6, 1: -3.6}                 # VBIAS via / B.Cu column


def bridge_half(s):
    """one mirror half of the bridge (s = -1: A side, up; +1: K side, down)"""
    i = 0 if s < 0 else 1
    rail, node, vb = ("BRG_A", "BRG_K")[i], ("BIAS_A_N", "BIAS_K_N")[i], ("VBIAS_A", "VBIAS_K")[i]
    r25, c47, r1k, c10, tp = ("R202", "R203")[i], ("C201", "C202")[i], ("R205", "R206")[i], ("C203", "C204")[i], \
        ("TP201", "TP202")[i]
    up = (lambda a, b_: a if s < 0 else b_)
    FS.two(r25, XM, s * 2.23, "v", up(node, rail))
    FS.two(c47, XM + 0.48, s * 4.07, "h", node)
    FS.two(r1k, XM - 0.47 - 0.93, s * 3.17, "h", vb)
    FS.two(c10, FS.pad(r1k, "@" + vb)[0], s * 4.55, "v", up("GND", vb))
    pn = "1" if s < 0 else "2"
    for d in ("D201", "D202"):
        x0, y0 = FS.pad(d, pn)
        dx = 1 if x0 < XM else -1
        FS.track(rail, W, [(x0, y0), (x0, s * (YR - 0.35)), (x0 + dx * 0.35, s * YR), (XM, s * YR)],
                 name=f"{rail} rail {d}", z=50)
    FS.track(node, W_SIG, [(XM, s * 2.74), (XM, s * 4.07)])
    FS.track(node, W_SIG, [(r1k, "@" + node), (XM, s * 3.17)])
    FS.track(vb, W_SIG, [(c10, "@" + vb), (r1k, "@" + vb)])
    gx, gy = FS.pad(c10, "@GND")
    gv(FS, gx, gy + s * 0.62)
    FS.track("GND", W_GND, [(gx, gy), (gx, gy + s * 0.62)])
    # VBIAS: via, B.Cu column to the south boundary; test point on B.Cu
    vx = VB_X[s]
    FS.track(vb, W_SIG, [(r1k, "@" + vb), (vx, s * 3.17)])
    FS.via(vx, s * 3.17, vb)
    FS.track(vb, W_SIG, [(vx, s * 3.17), (vx, BH - YBR)], layer="B.Cu")
    FS.place(tp, vx, s * 3.17 if s < 0 else 7.0, 0, "B")
    return vx


for s_ in (-1, 1):
    bridge_half(s_)

# hold node, U201 (G = +3)
UX1 = D2X + 1.7 + 2.05
FS.place("U201", UX1, -0.95, 0)
FS.track("HOLD", W_HOLD, [("D202", "3"), ("U201", "3")], name="HOLD: D202.3 -> U201.3")
FS.two("C205", 3.4 + 0.46, 0.75 + 0.91, "v", "HOLD")
xc = FS.pad("C205", "@HOLD")[0]
FS.track("HOLD", W_HOLD, [(xc, 0.0), ("C205", "@HOLD")])
gx, gy = FS.pad("C205", "@GND")
FS.track("GND", W_GND, [(gx, gy), (gx, gy + 0.6)])
gv(FS, gx, gy + 0.6)
FS.two("R207", 3.4 - 0.93, -1.9, "h", "HOLD_FB")
FS.two("R208", xc + 0.46 + 0.93, 1.66, "h", "HOLD_FB")
xg = FS.pad("R207", "@HOLD_FB")[0]
FS.track("HOLD_FB", W_GUARD, [("U201", "4"), (UX1 + 0.25, 0.0), (UX1 - 0.25, -0.5), (xg + 0.3, -0.5), (xg, -0.2),
                              (xg, 0.6), (xg + 1.06, 1.66), ("R208", "@HOLD_FB")], name="guard ring (HOLD_FB)")
FS.track("HOLD_FB", W_HOLD, [("R207", "@HOLD_FB"), (xg, -0.2)])
x, y = FS.pad("R208", "@GND")
FS.track("GND", W_GND, [(x, y), (x + 0.6, y)])
gv(FS, x + 0.6, y)
FS.track("HOLD_OUT", W_SIG, [("R207", "@HOLD_OUT"), ("U201", "1"), (UX1, -1.9)])
FS.via(UX1, -1.9, "HOLD_OUT")
p2u = FS.pad("U201", "2")
FS.track("-2V5", 0.5, [p2u, (3.3, p2u[1])])
FS.via(3.3, p2u[1], "-2V5")
FS.two("C209", 3.3, -1.95, "v", "GND", side="B")
FS.track("-2V5", W_PWR, [(3.3, p2u[1]), ("C209", "@-2V5")], layer="B.Cu")
x9, y9 = FS.pad("C209", "@-2V5")
gx, gy = FS.pad("C209", "@GND")
FS.track("GND", W_GND, [(gx, gy), (gx, gy - 0.6)], layer="B.Cu")
gv(FS, gx, gy - 0.6)
FS.two("C208", UX1 + 2.05 + 0.91, -1.9, "h", "+2V5")
FS.track("+2V5", 0.6, [("U201", "5"), ("C208", "@+2V5")])
xv = (FS.pad("U201", "5")[0] + 0.66 + FS.pad("C208", "@+2V5")[0] - 0.28) / 2
FS.via(xv - 0.3, -2.6, "+2V5")
FS.via(xv + 0.35, -2.6, "+2V5")
FS.track("+2V5", W_PWR, [(xv, -1.9), (xv, -2.6)])
FS.track("+2V5", W_PWR, [(xv - 0.3, -2.6), (xv + 0.35, -2.6)])
x, y = FS.pad("C208", "@GND")
FS.track("GND", W_GND, [(x, y), (x, y + 0.72)])
gv(FS, x, y + 0.72)

# level shifter U202, ADC RC
UX, UY = 3.4, 6.5
FS.place("U202", UX, UY, 0)
FS.two("R209", UX + 2.05 + 0.93, UY + 0.95, "h", "SHIFT_IN")
FS.two("R210", UX, UY + 1.7 + 0.47, "h", "SHIFT_OUT")
FS.two("R211", UX - 2.05 - 0.93, UY - 0.95, "h", "ADC_IN")
FS.two("C207", UX - 2.05 - 1.86 - 0.91, UY - 0.95, "h", "GND")
FS.two("C206", UX - 2.05 - 0.91, UY + 0.95, "h", "GND")
FS.two("C210", UX + 2.05 + 0.91, UY - 0.95, "h", "+3V3")
FS.track("SHIFT_IN", W_SIG, [("U202", "4"), ("R209", "@SHIFT_IN")])
FS.track("SHIFT_IN", W_SIG, [(UX + 0.6, UY + 0.95), (UX + 0.6, UY + 2.17)])
FS.track("SHIFT_OUT", W_SIG, [("R211", "@SHIFT_OUT"), ("U202", "1"), (UX - 0.05, UY - 0.95)])
FS.via(UX - 0.05, UY - 0.95, "SHIFT_OUT")
xr = FS.pad("R210", "@SHIFT_OUT")[0] - 0.75
FS.via(xr, UY + 2.17, "SHIFT_OUT")
FS.track("SHIFT_OUT", W_SIG, [(UX - 0.05, UY - 0.95), (UX - 0.05, UY + 2.17 - (UX - 0.05 - xr)), (xr, UY + 2.17)],
         layer="B.Cu")
FS.place("TP204", UX - 0.05, UY + 0.4, 0, "B")
FS.track("SHIFT_OUT", W_SIG, [(xr, UY + 2.17), ("R210", "@SHIFT_OUT")])
FS.track("ADC_IN", W_SIG, [("R211", "@ADC_IN"), ("C207", "@ADC_IN")])
FS.track("ADC_REF_MID", W_SIG, [("U202", "3"), ("C206", "@ADC_REF_MID")])
FS.track("+3V3", 0.6, [("U202", "5"), ("C210", "@+3V3")])
FS.via(UX + 2.48, UY - 1.6, "+3V3")
FS.via(UX + 3.13, UY - 1.6, "+3V3")
FS.track("+3V3", W_PWR, [("C210", "@+3V3"), (UX + 2.48, UY - 1.6)])
FS.track("+3V3", W_PWR, [(UX + 2.53, UY - 1.6), (UX + 3.13, UY - 1.6)])
for ref, dx, dy in (("C210", 0.62, 0), ("C207", 0, 0.62), ("C206", 0, 0.62)):
    x, y = FS.pad(ref, "@GND")
    FS.track("GND", W_GND, [(x, y), (x + dx, y + dy)])
    gv(FS, x + dx, y + dy)
x, y = FS.pad("U202", "2")
FS.track("GND", W_GND, [(x, y), (x - 0.95, y)])
gv(FS, x - 0.95, y)
x, y = FS.pad("R209", "@HOLD_OUT")
FS.via(x + 0.6, y, "HOLD_OUT")
FS.track("HOLD_OUT", W_SIG, [(x, y), (x + 0.6, y)])
XH = UX1 - 0.25
FS.track("HOLD_OUT", W_SIG, [(UX1, -1.9), (XH, -1.65), (XH, y - (x + 0.6 - XH)), (x + 0.6, y)], layer="B.Cu")
FS.place("TP203", XH, 3.3, 0, "B")
# ADC_IN / ADC_REF_MID: F.Cu down, via, B.Cu to the south boundary
Y_S = BH - YBR
xa, ya = FS.pad("C207", "@ADC_IN")
FS.track("ADC_IN", W_SIG, [(xa, ya), (xa, UY + 2.2)])
FS.via(xa, UY + 2.2, "ADC_IN")
FS.track("ADC_IN", W_SIG, [(xa, UY + 2.2), (xa, Y_S)], layer="B.Cu")
xr_, yr_ = FS.pad("C206", "@ADC_REF_MID")
d = UX - 1.75 - xr_
FS.track("ADC_REF_MID", W_SIG, [(xr_, yr_), (xr_, yr_ + 0.6), (UX - 1.75, yr_ + 0.6 + d), (UX - 1.75, UY + 3.0)])
FS.via(UX - 1.75, UY + 3.0, "ADC_REF_MID")
FS.track("ADC_REF_MID", W_SIG, [(UX - 1.75, UY + 3.0), (UX - 1.75, Y_S)], layer="B.Cu")

# ============================================================================= balun, R204, STRB arms
for rot in (0, 90, 180, 270):
    FS.place("T401", XB, 0.0, rot)
    p1t, p2t = FS.pad("T401", "1"), FS.pad("T401", "2")
    if p1t[0] > XB and p1t[1] < 0 and p2t[0] < XB and p2t[1] < 0:
        break
    blk.b.Remove(blk.fps["T401"])
    del blk.fps["T401"]
pA, pK, pG = FS.pad("T401", "2"), FS.pad("T401", "4"), FS.pad("T401", "3")
FS.two("R204", XV + 0.55, 0.0, "v", "STRB_A")
FS.shift_to("R204", "@STRB_A", y=pA[1])


def arm(s):
    """mirror-symmetric arm section (s = -1 STRB_A, +1 STRB_K): 47 pF pad -> corner -> vertical at XV"""
    c47 = ("C201", "C202")[0 if s < 0 else 1]
    nn = ("STRB_A", "STRB_K")[0 if s < 0 else 1]
    cp = FS.pad(c47, "@" + nn)
    return nn, [cp, (XV - 0.4, s * YA), (XV, s * (YA - 0.4))]


nA, baseA = arm(-1)
nK, baseK = arm(1)
tailA = [(XV, pA[1] - 0.4), (XV + 0.4, pA[1]), pA]
YKB = 1.35                                       # K passes under the balun to its pad 4 (library land 1/4 | 2/3)
tailK = [(XV, YKB + 0.4), (XV + 0.4, YKB), (pK[0] - 0.4, YKB), (pK[0], YKB - 0.4), pK]
LA0 = bl.plen(baseA + tailA)
LK = bl.plen(baseK + tailK)
hb = (LK - LA0) / (2 * (math.sqrt(2) - 1))       # length-matching bump on the A arm (45-degree trapezoid)
xb1 = baseA[0][0] + 0.6
xb2 = xb1 + 2 * hb + 0.4
ptsA = [baseA[0], (xb1, -YA), (xb1 + hb, -YA - hb), (xb2 - hb, -YA - hb), (xb2, -YA)] + baseA[1:] + tailA
qA = FS.track(nA, W, ptsA, name="STRB_A arm", z=50)
qK = FS.track(nK, W, baseK + tailK, name="STRB_K arm", z=50)
rk = FS.pad("R204", "@STRB_K")
FS.track("STRB_K", W, [rk, (rk[0], YKB)], name="R204 -> STRB_K", z=50)
FS.track("GND", W_GND, [pG, (pG[0] - 0.75, pG[1])])
gv(FS, pG[0] - 0.75, pG[1])

# ============================================================================= strobe chain (TRF #2, pad, TRF #1)
YL = -0.435
XTAP = XB + 1.47 + 0.95
XT2 = XTAP + 0.95 + 1.82 + 0.94 + 1.6
XC410 = XTAP + 0.95 + 0.91
FS.two("C410", XC410, YL, "h", "CLIP")
FS.place("D401", XTAP, YL - 0.40 - 1.05, 90)


def trf(XT, U, FB, L, RD, CCOLD, C1N, C10U, TP, out_net, bias_net, in_net):
    """TRF37D73 stage, U at XT on the line: bias tee (bead pad 1 on the line -> 47 uH || 1 k -> cold-pad 100 nF,
    plane via pair beyond it), VCC pin 1 nF + via pair + 10 uF on B.Cu, GND pins to the EP, EP vias"""
    for rot in (180, 0):
        FS.place(U, XT, YL - 0.25, rot)
        if abs(FS.pad(U, "7")[1] - YL) < 1e-3 and FS.pad(U, "7")[0] < XT:
            break
        blk.b.Remove(blk.fps[U])
        del blk.fps[U]
    XFB = XT - 2.07
    FS.two(FB, XFB, YL - 0.5, "v", bias_net)
    FS.shift_to(FB, "@" + out_net, y=YL)
    yfb = FS.pad(FB, "@" + bias_net)[1]
    YLL = YL - 0.485 - 0.93 - 2.28 - 0.09
    FS.two(L, XFB, YLL, "v", "+3V3")
    FS.two(RD, XFB + 1.58 + 0.47, YLL, "v", "+3V3")
    lb = FS.pad(L, "@" + bias_net)
    FS.track(bias_net, 0.64, [(XFB, yfb), (XFB, lb[1])], name=f"bias tee {FB} -> {L}")
    for net_, sgn in ((bias_net, 1), ("+3V3", -1)):
        rx, ry = FS.pad(RD, "@" + net_)
        lx, ly = FS.pad(L, "@" + net_)
        d_ = rx - (lx + 1.325 - 0.18)
        FS.track(net_, 0.5, [(rx, ry), (rx - d_, ry + sgn * d_)])
    # test point (B.Cu) on the bias node, via on the bead -> choke link
    ytp = (yfb + lb[1]) / 2
    FS.via(XFB, ytp, bias_net)
    FS.place(TP, XFB, ytp, 0, "B")
    # cold pad: 100 nF across it, GND via at its GND pad, +3V3 plane via pair beyond the capacitor
    yt = FS.pad(L, "@+3V3")[1]
    YC = YLL - 2.28 - 0.46
    FS.two(CCOLD, XFB + 0.48, YC, "h", "+3V3")
    cpx, cpy = FS.pad(CCOLD, "@+3V3")
    FS.track("+3V3", 0.56, [(cpx, cpy), (cpx, yt)])
    gx, gy = FS.pad(CCOLD, "@GND")
    FS.track("GND", W_GND, [(gx, gy), (gx + 0.62, gy)])
    gv(FS, gx + 0.62, gy)
    vy = cpy - 0.31 - 0.1 - 0.3 - 0.05
    for dx in (-0.36, 0.36):
        FS.via(cpx + dx, vy, "+3V3")
    FS.track("+3V3", 0.6, [(cpx - 0.36, vy), (cpx + 0.36, vy)])
    FS.track("+3V3", 0.56, [(cpx, vy), (cpx, cpy)])
    # GND pins -> EP, EP vias
    for pn in ("3", "4", "5", "6", "8"):
        x, y = FS.pad(U, pn)
        FS.track("GND", 0.25, [(x, y), (XT, y)])
    for dy in (-0.55, 0.0, 0.55):
        FS.via(XT, YL - 0.25 + dy, "GND")
    # VCC: pin 1 -> 1 nF (along the row) -> via pair; 10 uF on B.Cu under the vias
    p1_ = FS.pad(U, "1")
    XC5 = XT + 1.6 + 0.46
    FS.two(C1N, XC5, 0.565 + 0.91, "v", "+3V3")
    c5 = FS.pad(C1N, "@+3V3")
    FS.track("+3V3", 0.25, [p1_, (c5[0] - (c5[1] - p1_[1]), p1_[1]), c5])
    FS.track("+3V3", W_PWR, [c5, (XC5 + 1.22, c5[1])])
    for dx in (0.62, 1.22):
        FS.via(XC5 + dx, c5[1], "+3V3")
    x, y = FS.pad(C1N, "@GND")
    FS.track("GND", W_GND, [(x, y), (x, y + 0.6)])
    gv(FS, x, y + 0.6)
    FS.two(C10U, XC5 + 0.92, c5[1] + 1.4, "v", "+3V3", side="B")
    ct = FS.pad(C10U, "@+3V3")
    FS.track("+3V3", 0.6, [(XC5 + 0.62, c5[1]), (XC5 + 1.22, c5[1])], layer="B.Cu")
    FS.track("+3V3", 0.6, [(ct[0], c5[1]), ct], layer="B.Cu")
    x, y = FS.pad(C10U, "@GND")
    FS.track("GND", 0.6, [(x, y), (x, y + 0.8)], layer="B.Cu")
    gv(FS, x, y + 0.8)
    return XFB


XFB2 = trf(XT2, "U402", "FB402", "L402", "R416", "C408", "C409", "C407", "TP402", "TRF2_OUT", "TRF2_BIAS", "TRF2_RFIN")
p7, p2 = FS.pad("U402", "7"), FS.pad("U402", "2")
FS.track("CLIP", W, [("T401", "1"), (XTAP, YL), ("C410", "@CLIP")], name="CLIP: balun.1 -> tap -> C410", z=50)
FS.track("TRF2_OUT", W, [("C410", "@TRF2_OUT"), p7], name="TRF2_OUT: C410 -> FB402 -> U402.7", z=50)
FS.track("CLIP", W, [(XTAP, YL), ("D401", "1")], name="clamp tap", z=50)
x, y = FS.pad("D401", "2")
FS.track("GND", W_GND, [(x, y), (x, y - 0.65)])
gv(FS, x, y - 0.65)
# input network of TRF #2: 100 nF, 12 dB pi pad (82 / 91 / 82), 100 nF
a = XT2 + 2.51
FS.two("C406", a, YL, "h", "TRF2_RFIN")
FS.two("R403", a + 1.0, YL - 0.5, "v", "GND")
FS.shift_to("R403", "@TRF2_IN", y=YL)
FS.two("R404", a + 2.0, YL, "h", "TRF2_IN")
FS.two("R402", a + 3.0, YL - 0.5, "v", "GND")
FS.shift_to("R402", "@PADN", y=YL)
FS.two("C405", a + 4.0, YL, "h", "PADN")
for r in ("R403", "R402"):
    x, y = FS.pad(r, "@GND")
    FS.track("GND", W_GND, [(x, y), (x, y - 0.62)])
    gv(FS, x, y - 0.62)
XT1 = a + 7.45
trf(XT1, "U401", "FB401", "L401", "R415", "C403", "C404", "C402", "TP401", "TRF1_OUT", "TRF1_BIAS", "TRF1_RFIN")
FS.track("TRF2_RFIN", W, [p2, ("C406", "@TRF2_RFIN")], name="TRF2_RFIN: U402.2 -> C406", z=50)
FS.track("TRF2_IN", W, [("C406", "@TRF2_IN"), ("R404", "@TRF2_IN")], name="TRF2_IN: C406 -> R404", z=50)
FS.track("PADN", W, [("R404", "@PADN"), ("C405", "@PADN")], name="PADN: R404 -> C405", z=50)
FS.track("TRF1_OUT", W, [("C405", "@TRF1_OUT"), FS.pad("U401", "7")], name="TRF1_OUT: C405 -> FB401 -> U401.7",
         z=50)
FS.two("C401", XT1 + 2.51, YL, "h", "TRF1_RFIN")
FS.two("R401", XT1 + 3.51, YL, "h", "TRF1_IN")
FS.track("TRF1_RFIN", W, [FS.pad("U401", "2"), ("C401", "@TRF1_RFIN")], name="TRF1_RFIN: U401.2 -> C401", z=50)
FS.track("TRF1_IN", W, [("C401", "@TRF1_IN"), ("R401", "@TRF1_IN")], name="TRF1_IN: C401 -> R401", z=50)
XE = BW - XBR
FS.track("S_STROBE_P", W, [("R401", "@S_STROBE_P"), (XE, YL)], name="S_STROBE_P: R401 -> east boundary", z=50)
# S_STROBE_N dummy: 47 R -> 100 nF -> 49.9 R to GND, a column right of U401's supply
XN = XE - 0.57
YN = YL + 1.0
FS.two("R405", XN, YN + 0.51, "v", "S_STROBE_N")
FS.shift_to("R405", "@S_STROBE_N", y=YN)
FS.two("C411", XN, YN + 2.0, "v", "N1")
FS.two("R406", XN, YN + 3.5, "v", "N2")
FS.track("S_STROBE_N", W, [("R405", "@S_STROBE_N"), (XE, YN)], name="S_STROBE_N: R405 -> east boundary", z=50)
FS.track("N1", 0.3, [("R405", "@N1"), ("C411", "@N1")])
FS.track("N2", 0.3, [("C411", "@N2"), ("R406", "@N2")])
x, y = FS.pad("R406", "@GND")
FS.track("GND", W_GND, [(x, y), (x, y + 0.62)])
gv(FS, x, y + 0.62)

# shorted stub TL401 (80 ps) from the tap: down, east, down; NT401 to GND
L_STUB = 80.0 / bl.PS_MM50
Y1, X2R, CH = 3.9, XT2 + 1.95, 0.45
pre = bl.chamfer([(XTAP, YL), (XTAP, Y1), (X2R, Y1), (X2R, Y1 + 1)], CH)[:-1]
y_end = pre[-1][1] + (L_STUB - bl.plen(pre))
stub = [FS.T(p) for p in pre + [(X2R, y_end)]]
q_stub, l_stub = blk.tline("TL401", stub, W)
RFPOLY.append((q_stub, W))
for rot in (90, 270):
    FS.place("NT401", X2R, y_end + 0.5, rot)
    if FS.pad("NT401", "1")[1] < y_end + 0.5:
        break
    blk.b.Remove(blk.fps["NT401"])
    del blk.fps["NT401"]
FS.shift_to("NT401", "1", x=X2R, y=y_end)
gn = FS.pad("NT401", "2")
for dx in (-0.7, 0.7):
    gv(FS, gn[0] + dx, gn[1] + 0.3)
FS.track("GND", W_GND, [(gn[0] - 0.7, gn[1] + 0.3), (gn[0] - 0.3, gn[1]), (gn[0] + 0.3, gn[1]), (gn[0] + 0.7, gn[1] + 0.3)])

# ============================================================================= sampler keep-outs
HOLD_CUT = rect(2.25, -0.42, 5.15, 1.5)
FS.keepout(HOLD_CUT, ("In1.Cu", "In2.Cu", "B.Cu"))
FS.keepout(rect(1.5, -1.0, 5.9, 2.05), ("F.Cu",))

# ============================================================================= pours, hole keep-out, RF keep-outs
IN = 0.2
OUTLINE = rect(IN, IN, BW - IN, BH - IN)
HX, HY, HR = 3.0, 2.0, 3.6                 # M3 hole at board (3, 3) = block (3, 2)
hole = [(HX + HR * math.cos(k * math.pi / 8), HY + HR * math.sin(k * math.pi / 8)) for k in range(16)]
blk.keepout(hole, ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"), tracks=True, vias=True)
blk.zone("GND", ["In1.Cu"], OUTLINE, clearance=0.2, prio=0)
blk.zone("GND", ["F.Cu"], OUTLINE, clearance=0.25, prio=0)
blk.zone("GND", ["B.Cu"], OUTLINE, clearance=0.25, prio=0)
for q, w in RFPOLY:
    blk.rf_keepout(q, w, gap=2 * w + 0.03)

# ============================================================================= interfaces, outline drawing
YLl = YL + YBR
blk.iface("S_STROBE_P", BW, YLl, "F.Cu", "E", "pair", W, "from U501 pin 38 (FPGA); 50 R, R401 47 R in this block")
blk.iface("S_STROBE_N", BW, YLl + 1.0, "F.Cu", "E", "pair", W, "from U501 pin 35; dummy load R405/C411/R406 here")
blk.iface("BUF_OUT_T", X_T, BH, "F.Cu", "S", "rf50", W, "to U301.1 (phase block)")
blk.iface("VOFS", X_VOFS, BH, "B.Cu", "S", "slow", W_SIG, "R119")
for vb, s_ in (("VBIAS_A", -1), ("VBIAS_K", 1)):
    blk.iface(vb, VB_X[s_] + XBR, BH, "B.Cu", "S", "slow", W_SIG, "R205 / R206 via B.Cu column")
blk.iface("ADC_IN", xa + XBR, BH, "B.Cu", "S", "slow", W_SIG, "R211 / C207")
blk.iface("ADC_REF_MID", UX - 1.75 + XBR, BH, "B.Cu", "S", "slow", W_SIG, "U202.3 / C206")
for net, note in (("+5V", "U101 / U102, In2 via pairs x 2-15"), ("-5V", "U101 / U102, In2 via pairs x 1-14"),
                  ("+2V5", "R108 and U201 (In2 island under U201)"), ("-2V5", "R110 and U201 (via pair at C209)"),
                  ("+3V3", "U202, TRF bias tees and VCC via pairs x 23-56")):
    blk.iface(net, 0, 0, "In2.Cu", "-", "supply", None, note)
blk.edge_rect(0, 0, BW, BH, layer="Dwgs.User")
blk.text("ANALOG", 30.0, 20.8, 0.6)
blk.text("SIG_IN", 0.8, YBR + 4.6, 0.4)

for fp_ in blk.fps.values():                     # library fab texts small (as in the fragments)
    for g_ in fp_.GraphicalItems():
        if g_.GetClass() in ("FP_TEXT", "PCB_TEXT"):
            g_.SetTextSize(pcbnew.VECTOR2I(bl.mm(0.3), bl.mm(0.3)))
            g_.SetTextThickness(bl.mm(0.05))
out = blk.save(HERE)

# ============================================================================= tables
print(f"block {BW} x {BH} mm; bridge centre at local ({XBR:.2f}, {YBR:.2f}); input frame origin (0, {OYI})")
print(f"{'route':42s} {'w':>5s} {'mm':>7s} {'ps':>6s}")
for nm in blk.routes:
    if blk.routes[nm]["z"]:
        L_ = blk.route_len(nm)
        print(f"{nm:42s} {blk.routes[nm]['width']:5.2f} {L_:7.3f} {L_ * bl.PS_MM50:6.1f}")
print(f"{'TL401 stub (tap -> NT401 pad 1)':42s} {W:5.2f} {l_stub:7.3f} {l_stub * bl.PS_MM50:6.1f}  (target 80.0 ps)")
la, lk = blk.route_len("STRB_A arm"), blk.route_len("STRB_K arm")
print(f"STRB_A / STRB_K arms {la:.3f} / {lk:.3f} mm, mismatch {abs(la - lk) * 1e3:.1f} um (A bump h = {hb:.3f} mm)")
o11 = blk.pad("U101", "11")
r1 = blk.pad("R201", "@" + A("BUF_OUT_S"))
print(f"BUF802 OUT pin centre -> R201 pad 1 centre {r1[0] - o11[0]:.3f} mm; SMA pad end -> Ctop pad 1 edge "
      f"{FI.pad('C101', '1')[0] - 0.27 - X_PAD_END:.3f} mm")

# ============================================================================= checks
import floorplan as fpl
mem = fpl.membership(nl)
REFS = sorted([r for r, b_ in mem.items() if b_ == "analog" and r not in ("J102", "R122")] +
              ["C402", "C403", "C404", "C407", "C408", "C409"])
RF = {A(n): W for n in ("VIN", "BUF_OUT_S", "BUF_OUT_T", "BRG_IN", "BRG_A", "BRG_K", "STRB_A", "STRB_K", "CLIP",
                        "TRF2_OUT", "TRF2_RFIN", "TRF2_IN", "PADN", "TRF1_OUT", "TRF1_RFIN", "TRF1_IN",
                        "S_STROBE_P", "S_STROBE_N")}
res = bl.check_board(out, refs=REFS, rf_widths=RF, verbose=12)
_bb = pcbnew.LoadBoard(out).ComputeBoundingBox(False)
_ox, _oy = pcbnew.ToMM(_bb.GetX()), pcbnew.ToMM(_bb.GetY())


def render(png, layers, crop):
    """local helper: kicad-cli page-size-mode 2 puts the SVG origin at the board bbox (the SMA body overhangs
    the block by 10 mm), so boardlib.render's crop (pcbnew mm) is shifted by the bbox origin here"""
    x0, y0, x1, y1 = crop
    bl.render(out, png, layers, crop=(x0 - _ox, y0 - _oy, x1 - _ox, y1 - _oy), tmpdir=SCR)


if os.environ.get("RENDER", "1") == "1":
    lay = ("F.Cu", "F.SilkS", "F.Fab", "Dwgs.User")
    render(os.path.join(HERE, "analog.png"), lay, (99.5, 99.5, 156.5, 122.0))
    render(os.path.join(HERE, "analog_detail.png"), lay, (127.0, 104.0, 150.0, 119.0))
    render(os.path.join(SCR, "analog_b.png"), ("B.Cu", "B.Fab", "Dwgs.User"), (99.5, 99.5, 156.5, 122.0))
