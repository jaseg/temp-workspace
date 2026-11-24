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
os.environ["BL_STACKUP"] = "6L"            # phase two: native 6-layer block (JLC06161H-3313, RULES rule 10)
import boardlib as bl
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board6/analog"
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
        q = [blk.pad(*p) if isinstance(p[0], str) else s.T(p) for p in pts]
        out = []
        for piece in split_at_pads(A(net), q, layer):
            piece, ch_ = pad_escape(A(net), piece, layer, ch)
            r = blk.track(A(net), w, piece, layer, name=name, z=z, ch=ch_)
            if z:
                RFPOLY.append((r, w))
            out += r if not out else r[1:]
        return out
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


def _pad_at(net, p, layer):
    """local helper: the pad of net under point p (block-local) on layer, with its half extents"""
    lay = pcbnew.F_Cu if layer == "F.Cu" else pcbnew.B_Cu if layer == "B.Cu" else None
    if lay is None:
        return None
    v = blk.P(*p)
    for f in blk.fps.values():
        for pd in f.Pads():
            if pd.GetNetname() == net and pd.IsOnLayer(lay) and pd.HitTest(v):
                bb = pd.GetBoundingBox()
                return (pcbnew.ToMM(bb.GetWidth()) / 2, pcbnew.ToMM(bb.GetHeight()) / 2,
                        blk.loc(pd.GetPosition()))
    return None


def split_at_pads(net, q, layer):
    """local helper: split a polyline at interior points that lie on a pad of the same net"""
    pieces, cur = [], [q[0]]
    for i, p in enumerate(q[1:], 1):
        cur.append(p)
        if i < len(q) - 1 and _pad_at(net, p, layer):
            pieces.append(cur)
            cur = [p]
    pieces.append(cur)
    return [c for c in pieces if len(c) > 1]


def pad_escape(net, q, layer, ch):
    """local helper (boardlib.Block.track has no pad-axis escape): a track that starts / ends on a pad leaves
    it along a pad axis; insert an escape point beyond the pad edge and shorten the chamfer leg so that no
    diagonal starts inside the pad"""
    q = list(q)
    for end in (0, 1):
        if end:
            q.reverse()
        pp = _pad_at(net, q[0], layer)
        if pp and len(q) >= 2:
            hx, hy, _c = pp
            P, Q = q[0], q[1]
            dx, dy = Q[0] - P[0], Q[1] - P[1]
            if abs(dx) > 1e-4 and abs(dy) > 1e-4:
                cands = []
                for ax in ((0, 1) if abs(dx) >= abs(dy) else (1, 0)):
                    d, o, h = (dx, dy, hx) if ax == 0 else (dy, dx, hy)
                    for e in (h + 0.05, h + 0.05 + ch):
                        if abs(d) - e >= abs(o) - 1e-6 or (e == h + 0.05 + ch and abs(d) > e + 0.05):
                            E = (P[0] + math.copysign(e, d), P[1]) if ax == 0 else (P[0], P[1] + math.copysign(e, d))
                            cands.append(E)
                            break
                    if cands:
                        break
                if cands:
                    q.insert(1, cands[0])
            # chamfer leg: the first corner's chamfer must start outside the pad
            if len(q) > 2:
                L0 = math.hypot(q[1][0] - q[0][0], q[1][1] - q[0][1])
                ch = max(0.03, min(ch, L0 - max(hx, hy) - 0.02))
        if end:
            q.reverse()
    return q, ch


RFPOLY = []
gv = lambda fr, x, y: fr.via(x, y, "GND")
rect = bl.rect_pts

# ============================================================================= INPUT STAGE (block-local mm)
# Fragment geometry (SMA launch, divider, BUF802, OUT -> R201) re-placed so that no two courtyards overlap:
# C101 moved 0.26 mm right of the J101 courtyard (SMA pad end -> C101 1.15 mm), 0402 columns at courtyard pitch.
OYI = 4.0                                  # fragment origin offset (kept for the clamp rows / launch)
FI = Frame(0.0, OYI)                       # fragment frame (launch, clamp rows)
FL = Frame(0.0, 0.0)                       # block-local frame
Y0 = 6.3                                   # line axis, fragment frame (local 10.30)
YL0 = Y0 + OYI
X_PAD_END = 3.7
X_TAPER = X_PAD_END + 0.8
X_CT = 4.70 + 0.91                         # C101 courtyard touches the J101 courtyard (x 4.70)
XA = 5.17                                  # alpha-string column (courtyard touches J101's)
X_RG = X_CT + 0.91 + 0.93                  # R104 (Rg)
x_ga = 6.50
X_BI = 7.85                                # R105 / R106 column
XU = 10.75
YU = YL0 + 0.25
W_ = W
VL = lambda ref, x, y, top, side="F": FL.two(ref, x, y, "v", top, side)
HL = lambda ref, x, y, left, side="F": FL.two(ref, x, y, "h", left, side)
gl = lambda x, y: FL.via(x, y, "GND")

FI.place("J101", 2.1, Y0, 270)
HL("C101", X_CT, YL0, "VIN")
VL("R114", XA, YL0 + 1.40, "VIN")
VL("R115", XA, YL0 + 3.26, "S1")
VL("R116", XA, YL0 + 5.12, "S2")
HL("R104", X_RG, YL0, "GA")
VL("C102", x_ga, YL0 + 1.40, "GA")
VL("R105", X_BI, YL0 + 1.40, "BUF_IN")
VL("R106", X_BI, YL0 + 3.26, "IN_BIAS_MID")
FL.place("U101", XU, YU, 0)
X_P11 = XU + 1.875
XTAPR = XTAPF = 14.27                      # R112 (down) / R118 (up) taps on BUF_OUT_S, one column (DECOUPLING-1:
                                           # the R112 column moved +0.47 mm so C614 sits at pin 10 like C109 at pin 12)
VL("R112", XTAPR, YL0 + 0.93, "BUF_OUT_S")
VL("R113", XTAPR, YL0 + 2.79, "RT_MID")
VL("R118", XTAPF, YL0 - 0.93, "FB")
X_R118 = XTAPF
VL("C108", 8.16, 8.90, "GND")              # VS+ pin 1
VL("C109", 13.34, YL0 - 1.30, "GND")       # VSO+ pin 12
VL("C614", 13.34, YL0 + 1.70, "-5V")       # VSO- pin 10, top side (DECOUPLING-1; moved from the power sheet)
VL("C616", 7.20, 8.90, "GND")              # +5V pins 1 / 12, 2.2 uF beside C108 (PDN-6; moved from the power sheet)
YBC = 12.68 + 0.93                         # bottom row under U101 (courtyards touch U101's)
VL("C112", XU - 0.95, YBC, "-5V")          # VS- pins 5 / 6
VL("R107", XU, YBC, "R_BIAS")
VL("C113", XU + 0.95, YBC, "-5V")          # pins 8 / 10
Y_CL = Y0 - 3.4
for ref, x, top in (("R109", XU - 3.1, "GND"), ("R108", XU - 2.15, "+2V5"), ("C103", XU - 1.2, "GND"),
                    ("C104", XU + 1.2, "GND"), ("R110", XU + 2.15, "-2V5"), ("R111", XU + 3.1, "GND")):
    FI.two(ref, x, Y_CL - 0.51, "v", top)
FI.place("TP101", XU - 4.6, Y_CL - 1.2)
FI.place("TP102", XU + 4.6, Y_CL - 1.2)
# servo (OPA197) bottom-left: U102 rot 180, TAP top right, OPA_OUT bottom right, FB / +5V left
XO, YO = 2.45, 16.20
FL.place("U102", XO, YO, 180)
VL("R117", XA, 17.28, "TAP")
VL("C105", XA + 0.93, 17.28, "TAP")
VL("C107", X_BI, 15.42, "IN_AUX")
VL("R119", 1.00, 19.40, "VOFS")
VL("R123", 1.94, 19.40, "VNEG_REF")
VL("C106", 3.59, 19.40, "OPA_OUT")
HL("R121", 5.60, 18.90, "OPA_OUT")
HL("R120", 7.85, 20.20, "FB")
FL.place("RV101", 12.05, 18.85, 90)
# bottom side: U102 decoupling, bulk, test points
VL("C114", 1.60, 15.72, "GND", side="B")
HL("C110", 3.50, 17.15, "+5V", side="B")    # +5V pad clear of the U102 via
HL("C116", 11.70, 15.80, "-5V", side="B")    # bulk pair 0.2 mm south: -5V pad clear of R107's via
HL("C111", 11.70, 17.85, "+5V", side="B")
VL("C115", 13.34, 12.35, "-5V", side="B")  # second VSO- capacitor, under C614
FL.place("TP103", 5.40, 20.40, 0, "B")
FL.place("TP104", 3.20, 20.45, 0, "B")

# --- launch, divider
FI.zone("VIN", ["F.Cu"], [(X_PAD_END - 0.3, Y0 - 0.635), (X_PAD_END, Y0 - 0.635), (X_TAPER, Y0 - W / 2),
                          (X_TAPER, Y0 + W / 2), (X_PAD_END, Y0 + 0.635), (X_PAD_END - 0.3, Y0 + 0.635)],
        clearance=0.25, prio=5, minw=0.1)
FL.track("VIN", W, [(X_TAPER - 0.05, YL0), ("C101", "1")], name="VIN: SMA taper -> Ctop")
FL.track("VIN", W, [("R114", "@VIN"), (XA, YL0)])
FL.keepout(rect(XA - 0.93, YL0 + 0.2, XA + 0.93, FL.pad("R114", "@VIN")[1] + 0.93))
for sy in (-1, 1):
    gv(FI, 3.9, Y0 + sy * 3.8)
FL.track("GA", 0.3, [("C101", "2"), ("R104", "@GA")])
FL.track("GA", 0.3, [(x_ga, YL0), ("C102", "@GA")])
x, y = FL.pad("C102", "@GND")
gl(x, y + 0.64)
FL.track("GND", W_GND, [(x, y), (x, y + 0.64)])
p2, p3, p4 = FL.pad("U101", "2"), FL.pad("U101", "3"), FL.pad("U101", "4")
FL.track("BUF_IN", W_HZ, [("R104", "@BUF_IN"), p2])
rb = FL.pad("R104", "@BUF_IN")
r105 = FL.pad("R105", "@BUF_IN")
FL.track("BUF_IN", 0.3, [rb, (rb[0], rb[1] + 0.35), (r105[0], r105[1] - 0.45), r105])
FL.track("IN_BIAS_MID", 0.3, [("R105", "@IN_BIAS_MID"), ("R106", "@IN_BIAS_MID")])
# IN_BIAS: pin 3 -> via in the channel -> B.Cu -> via left of R106 -> R106
XCH = 8.52
FL.track("IN_BIAS", W_HZ, [p3, (XCH, p3[1])])
FL.via(XCH, p3[1], "IN_BIAS")
r106 = FL.pad("R106", "@IN_BIAS")
FL.via(7.0, r106[1], "IN_BIAS")
FL.track("IN_BIAS", W_HZ, [(7.0, r106[1]), r106])
FL.track("IN_BIAS", W_HZ, [(XCH, p3[1]), (XCH, 13.3), (XCH - 0.77, 14.07), (7.0, r106[1])], layer="B.Cu")
# IN_AUX: pin 4 -> channel x 8.55 -> C107 (100p at the pin) -> R121
XIA = 8.55
c107 = FL.pad("C107", "@IN_AUX")
r121 = FL.pad("R121", "@IN_AUX")
FL.track("IN_AUX", W_SIG, [p4, (XIA, p4[1]), (XIA, r121[1]), r121])
FL.track("IN_AUX", W_SIG, [(XIA, c107[1]), c107])
x, y = FL.pad("C107", "@GND")
gl(x, y + 0.70)
FL.track("GND", W_GND, [(x, y), (x, y + 0.70)])
# U101 supplies
p1, p12 = FL.pad("U101", "1"), FL.pad("U101", "12")
c108 = FL.pad("C108", "@+5V")
FL.track("+5V", 0.25, [p1, (8.75, p1[1]), (8.55, 9.60), (c108[0], 9.60)])
for y in (YL0 - 1.15, YL0 - 1.7):
    FL.via(XU - 1.55, y, "+5V")
FL.zone("+5V", ["F.Cu"], rect(c108[0] - 0.32, YL0 - 1.95, XU - 1.33, YL0 - 0.68))
c1081 = FL.pad("C108", "@GND")
gl(c108[0], 7.75)
FL.track("GND", W_GND, [c1081, (c108[0], 7.75)])
c616 = FL.pad("C616", "@+5V")                # 2.2 uF: +5V pad joined to C108's +5V pad, GND via above
FL.track("+5V", W_PWR, [c616, c108])
x, y = FL.pad("C616", "@GND")
gl(x, 7.75)
FL.track("GND", W_GND, [(x, y), (x, 7.75)])
c117 = FL.pad("C109", "@+5V")
FL.track("+5V", 0.25, [p12, (c117[0], p12[1]), c117])
for xy in ((XU + 1.5, YL0 - 1.2), (XU + 1.75, YL0 - 1.85)):
    FL.via(*xy, "+5V")
FL.zone("+5V", ["F.Cu"], [(XU + 1.2, YL0 - 0.85), (XU + 1.2, YL0 - 2.15), (XU + 2.05, YL0 - 2.15),
                          (XU + 2.05, YL0 - 1.15), (c117[0] + 0.32, YL0 - 1.15), (c117[0] + 0.32, YL0 - 0.85)])
gl(c117[0], 7.75)
FL.track("GND", W_GND, [("C109", "@GND"), (c117[0], 7.75)])
p5, p6, p7, p8, p10 = (FL.pad("U101", n) for n in ("5", "6", "7", "8", "10"))
c112, c113 = FL.pad("C112", "@-5V"), FL.pad("C113", "@-5V")
YP = 12.60
FL.track("-5V", 0.25, [p5, (p5[0], YP), c112])
FL.track("-5V", 0.25, [p6, (p6[0], 12.50), (p5[0], 12.50)])
FL.zone("-5V", ["F.Cu"], [(p5[0] - 0.13, 12.0), (p6[0] + 0.13, 12.0), (p6[0] + 0.13, 12.45), (10.27, 12.68),
                          (10.27, 13.50), (8.80, 13.50), (8.80, 12.55), (p5[0] - 0.13, 12.55)])
for y in (12.80, 13.45):
    FL.via(9.0, y, "-5V")
FL.track("-5V", 0.25, [p8, (p8[0], YP), c113])
FL.zone("-5V", ["F.Cu"], [(p8[0] - 0.13, 12.0), (12.80, 12.0), (12.80, 12.95), (12.05, 12.95), (12.05, 13.45),
                          (11.37, 13.45), (11.37, 12.55), (p8[0] - 0.13, 12.55)])
for xy in ((12.25, 12.0), (12.5, 12.65)):
    FL.via(*xy, "-5V")
# TIGHTEN (24 Nov): no plane via between the VS- pins (5 / 6 / 8) and their capacitors: the board's -5V rail router
# had landed a via between pins 5 and 6 (current reached the pins before C112).  Via-only rule area (pours allowed)
# over the pin row and the pin-to-capacitor copper; the rail lands on the vias behind C112 / C113 instead.
_ko = blk.keepout([FL.T(p) for p in rect(p5[0] - 0.4, p5[1] - 0.5, p8[0] + 0.4, YP + 0.2)], ("F.Cu",), vias=True)
_ko.SetDoNotAllowCopperPour(False)
# pin 10 (VSO-): along the pin row to C614 (top, mirror of C109 at pin 12), one via to C115 on B
c614 = FL.pad("C614", "@-5V")
YV10 = c614[1] - 0.31 - 0.24                 # via just above the C614 pad (outside it)
FL.track("-5V", 0.25, [p10, (c614[0], p10[1]), c614])
FL.via(c614[0], YV10, "-5V")
FL.track("-5V", 0.4, [(c614[0], YV10), ("C115", "@-5V")], layer="B.Cu")
g614, g115 = FL.pad("C614", "@GND"), FL.pad("C115", "@GND")
YG10 = g115[1] + 0.31 + 0.26                 # shared GND via below both GND pads
gl(c614[0], YG10)
FL.track("GND", W_GND, [g614, (c614[0], YG10)])
FL.track("GND", W_GND, [g115, (c614[0], YG10)], layer="B.Cu")
FL.track("R_BIAS", 0.25, [p7, (p7[0], 12.55), (XU, 12.795), ("R107", "@R_BIAS")])
for ref, net in (("C112", "GND"), ("R107", "-5V"), ("C113", "GND")):
    x, y = FL.pad(ref, "@" + net)
    FL.via(x, y + 0.68, net)
    FL.track(net, W_GND, [(x, y), (x, y + 0.68)])
for dx in (-0.42, 0.42):
    for dy in (-0.42, 0.42):
        FL.via(XU + dx, YU + dy, "GND")
# clamp dividers (fragment frame)
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
# outputs: taps on BUF_OUT_S; 49.9R + 0R -> BUF_OUT_T to the south boundary
FL.track("BUF_OUT_S", W, [("R112", "@BUF_OUT_S"), (XTAPR, YL0)], name="R112 tap", z=50)
FL.track("BUF_OUT_S", W, [("R118", "@BUF_OUT_S"), (XTAPF, YL0)], name="R118 tap", z=50)
FL.track("RT_MID", 0.4, [("R112", "@RT_MID"), ("R113", "@RT_MID")])
xt, yt0 = FL.pad("R113", "@BUF_OUT_T")
X_T = 15.75
q_t = FL.track("BUF_OUT_T", W, [(xt, yt0), (xt, 14.5), (X_T, 14.5 + X_T - xt), (X_T, BH)],
               name="BUF_OUT_T: 0R -> south boundary", z=50, ch=0.3)
# FB (Rf1 sense): via above R118, B.Cu down x 14.6 and west along y 20.9 to R120 / the FB row
r118 = FL.pad("R118", "@FB")
FL.via(r118[0], 8.2, "FB")
FL.track("FB", W_SIG, [r118, (r118[0], 8.2)])
XFBB, YFBB = 6.75, 20.90
FL.track("FB", W_SIG, [(r118[0], 8.2), (14.6, 8.53), (14.6, 20.4), (14.1, YFBB), (XFBB, YFBB)], layer="B.Cu")
FL.via(XFBB, YFBB, "FB")
r120 = FL.pad("R120", "@FB")
FL.track("FB", W_SIG, [(XFBB, YFBB), (XFBB, r120[1] + 0.3), (XFBB + 0.3, r120[1]), r120])
# FB row: U102.4 -> left edge -> R119 / R123 / C106 bottom pads -> R120
p4o = FL.pad("U102", "4")
yfr = FL.pad("C106", "@FB")[1]
FL.track("FB", 0.15, [p4o, (0.40, p4o[1]), (0.40, yfr), ("R119", "@FB")])
FL.track("FB", W_SIG, [("R119", "@FB"), ("C106", "@FB"), (6.45, yfr), (XFBB, yfr + 0.3), (XFBB, r120[1] + 0.3)])
for ref, net in (("R119", "VOFS"), ("R123", "VNEG_REF")):
    x, y = FL.pad(ref, "@" + net)
    FL.track(net, W_SIG, [(x, y), (x, 18.2)])
    FL.via(x, 18.2, net)
    FL.track(net, W_SIG, [(x, 18.2), (x, BH)], layer="B.Cu")
X_VOFS = FL.pad("R119", "@VOFS")[0]
X_VNEG = FL.pad("R123", "@VNEG_REF")[0]
# alpha string, TAP
FL.track("S1", 0.3, [("R114", "@S1"), ("R115", "@S1")])
FL.track("S2", 0.3, [("R115", "@S2"), ("R116", "@S2")])
p3o = FL.pad("U102", "3")
r116 = FL.pad("R116", "@TAP")
FL.track("TAP", 0.25, [p3o, (4.55, p3o[1]), (4.85, p3o[1] + 0.3), (4.85, r116[1]), r116])
FL.track("TAP", 0.3, [r116, ("R117", "@TAP")])
FL.track("TAP", 0.3, [("R117", "@TAP"), ("C105", "@TAP")])
g1, g2 = FL.pad("R117", "@GND"), FL.pad("C105", "@GND")
FL.track("GND", W_GND, [g1, g2, (6.75, g2[1])])
gl(6.75, g2[1])
# OPA_OUT: pin 1 down to C106, R121; via + TP103 on B.Cu
p1o = FL.pad("U102", "1")
FL.track("OPA_OUT", W_SIG, [p1o, ("C106", "@OPA_OUT"), ("R121", "@OPA_OUT")])
FL.via(4.36, FL.pad("R121", "@OPA_OUT")[1], "OPA_OUT")
FL.track("OPA_OUT", W_SIG, [(4.36, FL.pad("R121", "@OPA_OUT")[1]), ("TP103", "1")], layer="B.Cu")
# U102 supplies: vias in the body column x 2.45; C114 / C110 on B.Cu
p2o, p5o = FL.pad("U102", "2"), FL.pad("U102", "5")
FL.track("-5V", 0.5, [p2o, (XO, p2o[1])])
FL.via(XO, p2o[1], "-5V")
FL.track("+5V", 0.5, [p5o, (XO, p5o[1])])
FL.via(XO, p5o[1], "+5V")
gl(XO, 15.25)
FL.track("-5V", 0.5, [("C114", "@-5V"), (XO, p2o[1])], layer="B.Cu")
FL.track("GND", 0.5, [("C114", "@GND"), (XO, 15.25)], layer="B.Cu")
FL.track("+5V", 0.5, [("C110", "@+5V"), (XO, p5o[1])], layer="B.Cu")
x, y = FL.pad("C110", "@GND")
FL.track("GND", 0.4, [(x, y), (4.4, y), (4.4, 17.9)], layer="B.Cu")
gl(4.4, 17.9)
# bulk (B.Cu): -5V at the R107 via, +5V via pair between the RV101 pads, shared GND via
x, y = FL.pad("C116", "@-5V")
FL.track("-5V", 0.6, [(x, y), (x, 14.77)], layer="B.Cu")
ga, gb = FL.pad("C116", "@GND"), FL.pad("C111", "@GND")
FL.track("GND", 0.6, [ga, gb], layer="B.Cu")
gl(ga[0], 16.82)
x, y = FL.pad("C111", "@+5V")
FL.track("+5V", 0.6, [(x, y), (x, 18.85)], layer="B.Cu")
FL.track("+5V", 0.6, [(10.40, 18.85), (11.10, 18.85)], layer="B.Cu")
for xv in (10.40, 11.10):
    FL.via(xv, 18.85, "+5V")
# RV101: RF2_MID from R120, GND pads to vias
rv1 = FL.pad("RV101", "1")
r1202 = FL.pad("R120", "@RF2_MID")
FL.track("RF2_MID", 0.3, [r1202, (rv1[0] - 1.25, r1202[1]), (rv1[0] - 1.05, rv1[1]), rv1])
x, y = FL.pad("RV101", "3")
FL.track("GND", W_GND, [(x, y), (x - 0.5, y), (x - 0.5, 18.85)])
gl(x - 0.5, 18.85)
x, y = FL.pad("RV101", "2")
FL.track("GND", W_GND, [(x, y), (x, y + 1.0), (13.55, 20.35)])
gl(13.55, 20.35)
for tp, dx, dy in (("TP104", 0, 0.2),):
    x, y = FL.pad(tp, "1")
    gl(x + dx, y + dy)
# keep-outs / cut-outs of the input stage
# 6L: L2 is only 0.0994 mm under L1, so the SMA centre pad, the divider node (C101.2 / R104 / C102) and the
# BUF802 input see L5 ground (1.354 mm) instead: L2 (In1), L3 (In2) and L4 (In3) cleared under them.
NODE_CUT = ("In1.Cu", "In2.Cu", "In3.Cu")
NODE_WIN = {}
SMA_CUT = (0, YL0 - 0.9, X_PAD_END, YL0 + 0.9)
FL.keepout(rect(*SMA_CUT), NODE_CUT)
NODE_WIN["SMA centre pad"] = SMA_CUT
# L-shaped window: the full height over C101.2 / R104 / C102 / R105.1, only the BUF_IN strip at U101.2 so that
# the IN_BIAS channel via (x 8.52, at pin 3) stays outside it
X_HZ0, X_HZ1, X_HZ2 = FL.pad("C101", "2")[0] - 0.3, 8.25, XU - 1.1
FL.keepout([(X_HZ0, YL0 - 0.45), (X_HZ2, YL0 - 0.45), (X_HZ2, YL0 + 0.25), (X_HZ1, YL0 + 0.25), (X_HZ1, YL0 + 1.1),
            (X_HZ0, YL0 + 1.1)], ("F.Cu",) + NODE_CUT + ("B.Cu",))
NODE_WIN["divider node"] = (X_HZ0, YL0 - 0.45, X_HZ1, YL0 + 1.1)
NODE_WIN["BUF802 input"] = (X_HZ1, YL0 - 0.45, X_HZ2, YL0 + 0.25)
g = W / 2 + 0.75
FL.keepout(rect(X_TAPER - 0.05, YL0 - g, FL.pad("C101", "2")[0], YL0 + g))
for sg in (-1, 1):
    FL.keepout(rect(X_PAD_END, YL0 + sg * 0.65, X_TAPER, YL0 + sg * g))

# ============================================================================= SAMPLER (frame FS, bridge centre)
D1X, D2X = -1.7, 1.7
XR201 = X_R118 + 0.47 + 0.93               # R201 courtyard touches the R118 courtyard
XBR = XR201 - (D1X - 1.7 - 0.93)
YBR = YL0
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
assert abs(pA[1] + pK[1]) < 1e-3 and abs(pA[0] + pK[0] - 2 * XB) < 1e-3     # outputs point-symmetric about T401
# RF-1 / RF-4: T401 and the uncoupled 50 R arms kept (sim/strobe_arms/RESULT.md); R204 on the bridge axis with one
# pad in each arm. The arms are mirror images about the bridge axis (y 0) from C201 / C202 through R204 to the
# T401 centre column; only the last 0.38 mm into the diagonal output pads (2 left, 4 right) differs in direction,
# so both arms are equal in length by construction (no matching bump).
XR = XB - 2.4                                    # R204 column (pads at y -/+0.51; T401 GND via between)
XV = XR - 0.7                                    # arm column (same-net gap to the R204 exit 0.54 mm)
YJ = 1.05                                        # arm row past T401 (0.28 mm outside its pad rows)
FS.two("R204", XR, 0.0, "v", "STRB_A")
YR204 = abs(FS.pad("R204", "@STRB_A")[1])


def arm(s):
    """one strobe arm (s = -1 STRB_A, +1 STRB_K): 47 pF pad -> column XV -> R204 pad (entered from the bridge side,
    left outward) -> row YJ -> T401 centre column -> output pad"""
    c47, nn, tp = (("C201", "STRB_A", "2"), ("C202", "STRB_K", "4"))[0 if s < 0 else 1]
    cp = FS.pad(c47, "@" + nn)
    pt = FS.pad("T401", tp)
    dx = 1 if pt[0] > XB else -1
    return nn, [cp, (XV - 0.4, s * YA), (XV, s * (YA - 0.4)), (XV, s * YR204), (XR, s * YR204), (XR, s * YJ),
                (XB, s * YJ), (XB, s * (abs(pt[1]) + 0.2)), (XB + dx * 0.2, s * abs(pt[1])), pt]


nA, ptsA = arm(-1)
nK, ptsK = arm(1)
LA0 = LK = bl.plen(ptsA)
assert abs(bl.plen(ptsA) - bl.plen(ptsK)) < 1e-6
qA = FS.track(nA, W, ptsA, name="STRB_A arm", z=50)
qK = FS.track(nK, W, ptsK, name="STRB_K arm", z=50)
FS.track("GND", W_GND, [pG, (pG[0] - 0.75, pG[1])])
gv(FS, pG[0] - 0.75, pG[1])

# ============================================================================= strobe chain (TRF #2, pad, TRF #1)
YL = -0.435
XTAP = XB + 1.47 + 0.95
XT2 = XTAP + 0.95 + 1.82 + 0.94 + 1.6
XC410 = XTAP + 0.95 + 0.91
FS.two("C410", XC410, YL, "h", "CLIP")
FS.place("D401", XTAP, YL - 0.40 - 1.05, 90)


def trf(XT, U, FB, L, RD, CCOLD, C1N, C100, C10U, TP, out_net, bias_net, in_net):
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
        pdl = [q_ for q_ in blk.fps[L].Pads() if q_.GetNetname() == A(net_)][0].GetBoundingBox()
        y0_ = pcbnew.ToMM(pdl.GetTop()) - YBR - 100 + 0.35
        y1_ = pcbnew.ToMM(pdl.GetBottom()) - YBR - 100 - 0.35
        yt_ = min(max(ry, y0_), y1_)
        xe_ = pcbnew.ToMM(pdl.GetRight()) - XBR - 100      # L pad inner edge
        if abs(yt_ - ry) < 1e-3:
            FS.track(net_, 0.5, [(rx, ry), (xe_ - 0.3, ry)])
        else:
            FS.track(net_, 0.5, [(rx, ry), (rx, yt_), (xe_ - 0.3, yt_)], ch=0.1)
    # test point (B.Cu) on the bias node: via 0.75 mm beside the bead's cold pad, off both the bead and the choke
    # pad (BIASTEE-6: no open via in a choke pad), short track along the bead pad axis
    xtp = XFB - 0.75
    FS.track(bias_net, W_SIG, [(XFB, yfb), (xtp, yfb)])
    FS.via(xtp, yfb, bias_net)
    FS.place(TP, xtp, yfb, 0, "B")
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
    # VCC: pin 1 -> 1 nF (nearest) -> 100 nF (C606 / C622, moved from the power sheet, PDN-7 / BIASTEE-2) -> via pair;
    # 10 uF on B.Cu below the via pair
    p1_ = FS.pad(U, "1")
    XC5 = XT + 1.6 + 0.46
    FS.two(C1N, XC5, 0.565 + 0.91, "v", "+3V3")
    FS.two(C100, XC5 + 0.92, 0.565 + 0.91, "v", "+3V3")
    c5 = FS.pad(C1N, "@+3V3")
    FS.track("+3V3", 0.25, [p1_, (c5[0] - (c5[1] - p1_[1]), p1_[1]), c5])
    XVV = (XC5 + 1.55, XC5 + 2.07)
    FS.track("+3V3", W_PWR, [c5, (C100, "@+3V3"), (XVV[1], c5[1])])
    for xv_ in XVV:
        FS.via(xv_, c5[1], "+3V3")
    for c_ in (C1N, C100):
        x, y = FS.pad(c_, "@GND")
        FS.track("GND", W_GND, [(x, y), (x, y + 0.6)])
        gv(FS, x, y + 0.6)
    FS.two(C10U, XVV[1], c5[1] + 1.85, "v", "+3V3", side="B")
    ct = FS.pad(C10U, "@+3V3")
    FS.track("+3V3", 0.6, [(XVV[0], c5[1]), (XVV[1], c5[1]), ct], layer="B.Cu")
    x, y = FS.pad(C10U, "@GND")
    FS.track("GND", 0.6, [(x, y), (x, y + 0.8)], layer="B.Cu")
    gv(FS, x, y + 0.8)
    return XFB


XFB2 = trf(XT2, "U402", "FB402", "L402", "R416", "C408", "C409", "C622", "C407", "TP402", "TRF2_OUT", "TRF2_BIAS", "TRF2_RFIN")
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
# shunts above the line (courtyards touch the series parts'), 50 R stub from the line to the shunt pad
for r, xs, net_ in (("R403", a + 1.0, "TRF2_IN"), ("R402", a + 3.0, "PADN")):
    FS.two(r, xs, YL - 1.40, "v", "GND")
    if r == "R402":                              # 0603 (PARTS-1): courtyard bottom on the series row's courtyard top
        blk.fps[r].BuildCourtyardCaches()
        cy_ = blk.fps[r].GetCourtyard(pcbnew.F_CrtYd).BBox()
        blk.fps[r].Move(pcbnew.VECTOR2I(0, bl.mm(YL - 0.47 + YBR + 100) - cy_.GetBottom()))
    FS.track(net_, W, [(xs, YL), (r, "@" + A(net_))], name=f"{r} shunt stub", z=50)
FS.two("R404", a + 2.0, YL, "h", "TRF2_IN")
FS.two("C405", a + 4.0, YL, "h", "PADN")
for r in ("R403", "R402"):
    x, y = FS.pad(r, "@GND")
    dy_ = 0.62 if r == "R403" else 0.72          # via clear of the 0603 pad
    FS.track("GND", W_GND, [(x, y), (x, y - dy_)])
    gv(FS, x, y - dy_)
XT1 = a + 7.45
trf(XT1, "U401", "FB401", "L401", "R415", "C403", "C404", "C606", "C402", "TP401", "TRF1_OUT", "TRF1_BIAS", "TRF1_RFIN")
FS.track("TRF2_RFIN", W, [p2, ("C406", "@TRF2_RFIN")], name="TRF2_RFIN: U402.2 -> C406", z=50)
FS.track("TRF2_IN", W, [("C406", "@TRF2_IN"), ("R404", "@TRF2_IN")], name="TRF2_IN: C406 -> R404", z=50)
FS.track("PADN", W, [("R404", "@PADN"), ("C405", "@PADN")], name="PADN: R404 -> C405", z=50)
FS.track("TRF1_OUT", W, [("C405", "@TRF1_OUT"), FS.pad("U401", "7")], name="TRF1_OUT: C405 -> FB401 -> U401.7",
         z=50)
FS.two("C401", XT1 + 2.51, YL, "h", "TRF1_RFIN")
FS.two("R401", XT1 + 2.51 + 1.84, YL, "h", "TRF1_IN")
FS.track("TRF1_RFIN", W, [FS.pad("U401", "2"), ("C401", "@TRF1_RFIN")], name="TRF1_RFIN: U401.2 -> C401", z=50)
FS.track("TRF1_IN", W, [("C401", "@TRF1_IN"), ("R401", "@TRF1_IN")], name="TRF1_IN: C401 -> R401", z=50)
XE = BW - XBR
FS.track("S_STROBE_P", W, [("R401", "@S_STROBE_P"), (XE, YL)], name="S_STROBE_P: R401 -> east boundary", z=50)
# S_STROBE_N dummy: 47 R -> 100 nF -> 49.9 R to GND, a column right of U401's supply
XN = XE - 0.57
YN = YL + 1.0
FS.two("R405", XN, YN + 0.51, "v", "S_STROBE_N")
FS.shift_to("R405", "@S_STROBE_N", y=YN)
_yr = blk.fps["R405"].GetPosition().y / 1e6 - 100 - YBR
FS.two("C411", XN, _yr + 1.84, "v", "N1")
FS.two("R406", XN, _yr + 3.68, "v", "N2")
FS.track("S_STROBE_N", W, [("R405", "@S_STROBE_N"), (XE, YN)], name="S_STROBE_N: R405 -> east boundary", z=50)
FS.track("N1", 0.3, [("R405", "@N1"), ("C411", "@N1")])
FS.track("N2", 0.3, [("C411", "@N2"), ("R406", "@N2")])
x, y = FS.pad("R406", "@GND")
FS.track("GND", W_GND, [(x, y), (x, y + 0.62)])
gv(FS, x, y + 0.62)

# shorted stub TL401 (80 ps) from the tap: down, east, down; NT401 to GND.
# RF-2: the short is a GND via in NT401 pad 2 (tented: the net-tie pads carry no mask opening / paste) plus two
# flanking vias; the residual delay of the 1.0 mm x 0.5 mm net-tie strip over L2 and the L1 -> L2 via barrel is
# taken off the line so that the stub is 80 ps to the L2 short. Same recipe for every stub end (NT401-NT403).
Z_TIE, EE_TIE = bl.microstrip_6l(0.5)
L_TIE = Z_TIE * math.sqrt(EE_TIE) / bl.C0 * 1.0e-3          # nH: 1.0 mm of 0.5 mm strip (pad 1 -> pad 2 centre)
L_VIA_L2 = 0.2 * 0.115 * (math.log(4 * 0.115 / 0.2) + 1)    # nH: 0.115 mm barrel L1 -> L2, 0.2 mm drill
TAU_END = (L_TIE + L_VIA_L2) / bl.Z50 * 1e3                 # ps
L_STUB = (80.0 - TAU_END) / bl.PS_MM50
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
gv(FS, gn[0], gn[1])                             # the short: via in the net-tie GND pad
for dx in (-0.65, 0.65):
    gv(FS, gn[0] + dx, gn[1])
FS.track("GND", W_GND, [(gn[0] - 0.65, gn[1]), (gn[0] + 0.65, gn[1])])

# ============================================================================= sampler keep-outs
HOLD_CUT = rect(2.25, -0.42, 5.15, 1.5)
FS.keepout(HOLD_CUT, NODE_CUT + ("B.Cu",))
NODE_WIN["hold node"] = (2.25 + XBR, -0.42 + YBR, 5.15 + XBR, 1.5 + YBR)
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

# ============================================================================= 6L pad compensation / node C
# Microstrip capacitance per mm from boardlib.microstrip (mask corrected).  References: L2 at H2 (3313, er 4.1);
# L3 at H3 when only L2 is cut (L2 copper + 0.55 core, er ~4.5); L5 at H5 when L2 / L3 / L4 are cut.
H2 = bl.STACKUPS["6L"]["H"]
H3 = H2 + 0.0152 + 0.55
H5 = H3 + 0.0152 + 0.1088 + 0.0152 + 0.55
ER_DEEP = 4.5
C_EXCESS_MAX = 0.030                               # pF: cut L2 under an in-line RF pad above this


def c_mm(w, h=H2, er=None):
    """pF per mm of a w-wide strip over a plane h below (boardlib microstrip)"""
    z, ee = bl.microstrip(w, h=h, er=er or (bl.STACKUPS["6L"]["ER"] if h <= H2 + 1e-6 else ER_DEEP))
    return math.sqrt(ee) / (bl.C0 * z)


RF_NETS = [A(n) for n in ("VIN", "BUF_OUT_S", "BUF_OUT_T", "BRG_IN", "BRG_A", "BRG_K", "STRB_A", "STRB_K", "CLIP",
                          "TRF2_OUT", "TRF2_RFIN", "TRF2_IN", "PADN", "TRF1_OUT", "TRF1_RFIN", "TRF1_IN",
                          "S_STROBE_P", "S_STROBE_N", "STUB_END")]


def _in_win(x, y):
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in NODE_WIN.values())


def _pad_axis(pd, net):
    """axis (0 = x, 1 = y) of the RF track that enters the pad (block-local)"""
    c = blk.loc(pd.GetPosition())
    for t in blk.b.GetTracks():
        if t.GetNetname() != net or isinstance(t, pcbnew.PCB_VIA) or not pd.IsOnLayer(t.GetLayer()):
            continue
        for e, o in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
            if pd.HitTest(e) or t.HitTest(pd.GetPosition()):     # ends on the pad, or runs over it (bead pads)
                a, b_ = blk.loc(e), blk.loc(o)
                return 0 if abs(b_[0] - a[0]) >= abs(b_[1] - a[1]) else 1
    if f_.GetReference().startswith("TL"):
        return None                                              # the stub's own end pads are the line
    bb = pd.GetBoundingBox()                                     # no track (stub end NT401): long axis
    return 1 if bb.GetHeight() > bb.GetWidth() else 0


def track_only_keepout(pts, layers):
    """rule area: no tracks / vias, copper pour allowed (keeps the L3 GND pour under an L2 pad cut solid)"""
    z = blk.keepout(pts, layers, tracks=True, vias=False)
    z.SetDoNotAllowCopperPour(False)
    return z


PADCOMP = []
for f_ in blk.fps.values():
    for pd in f_.Pads():
        net_ = pd.GetNetname()
        if net_ not in RF_NETS or not pd.IsOnLayer(pcbnew.F_Cu):
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
        win = _in_win(cx, cy)
        shorted = f_.GetReference().startswith("NT")             # stub short: no voltage, no compensation
        cut = (not win) and (not shorted) and ex2 > C_EXCESS_MAX
        if cut:
            # RF-6: the cut clears L2, L3 and L4 (as the integrated board does), so the cut part of the pad sees L5;
            # its length along the line is sized for zero excess C (rest of the pad over L2)
            c2_, c5_ = c_mm(across), c_mm(across, H5)
            lc = min(along, along * (c2_ - c_mm(W)) / (c2_ - c5_))
            res = c2_ * (along - lc) + c5_ * lc - c_line
            h_ = (lc / 2, dims[1] / 2) if ax == 0 else (dims[0] / 2, lc / 2)
            r_ = rect(cx - h_[0], cy - h_[1], cx + h_[0], cy + h_[1])
            blk.keepout(r_, ("In1.Cu", "In2.Cu", "In3.Cu"))
        PADCOMP.append((f"{f_.GetReference()}.{pd.GetNumber()}", across, along, ex2 * 1e3,
                        "node window" if win else (f"cut {lc:.2f} mm" if cut else "-"),
                        (c_mm(across, H5) * along - c_line if win else res if cut else ex2) * 1e3))

# ============================================================================= interfaces, outline drawing
YLl = YL + YBR
blk.iface("S_STROBE_P", BW, YLl, "F.Cu", "E", "pair", W, "from U501 pin 38 (FPGA); 50 R, R401 47 R in this block")
blk.iface("S_STROBE_N", BW, YLl + 1.0, "F.Cu", "E", "pair", W, "from U501 pin 35; dummy load R405/C411/R406 here")
blk.iface("BUF_OUT_T", X_T, BH, "F.Cu", "S", "rf50", W, "to U301.1 (phase block)")
blk.iface("VOFS", X_VOFS, BH, "B.Cu", "S", "slow", W_SIG, "R119 (FB offset)")
blk.iface("VNEG_REF", X_VNEG, BH, "B.Cu", "S", "slow", W_SIG, "R123 (FB offset)")
for vb, s_ in (("VBIAS_A", -1), ("VBIAS_K", 1)):
    blk.iface(vb, VB_X[s_] + XBR, BH, "B.Cu", "S", "slow", W_SIG, "R205 / R206 via B.Cu column")
blk.iface("ADC_IN", xa + XBR, BH, "B.Cu", "S", "slow", W_SIG, "R211 / C207")
blk.iface("ADC_REF_MID", UX - 1.75 + XBR, BH, "B.Cu", "S", "slow", W_SIG, "U202.3 / C206")
for net, note in (("+5V", "U101 / U102, L4 via pairs x 2-15"), ("-5V", "U101 / U102, L4 via pairs x 1-14"),
                  ("+2V5", "R108 and U201 (L4 island under U201)"), ("-2V5", "R110 and U201 (via pair at C209)"),
                  ("+3V3", "U202, TRF bias tees and VCC via pairs x 23-56")):
    blk.iface(net, 0, 0, "In3.Cu", "-", "supply", None, note)
blk.edge_rect(0, 0, BW, BH, layer="Dwgs.User")
blk.text("ANALOG", 33.0, 20.6, 0.8)
for d_ in blk.b.GetDrawings():                   # board texts: 0.8 mm / 0.15 mm (JLC legibility)
    if d_.GetClass() == "PCB_TEXT":
        d_.SetTextThickness(bl.mm(0.15))


def strip_silk_over_pads(margin=0.1):
    """local helper: remove footprint silkscreen segments that run over (or within margin of) any copper pad
    on the same side (library silk outlines of J101 / U102 / 0402s next to tightly placed parts)"""
    pads = [(p, p.GetBoundingBox()) for f in blk.b.GetFootprints() for p in f.Pads()]
    n = 0
    for f in blk.b.GetFootprints():
        for g in list(f.GraphicalItems()):
            if g.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS) or g.GetClass() not in ("PCB_SHAPE", "FP_SHAPE", "MGRAPHIC"):
                continue
            cu = pcbnew.F_Cu if g.GetLayer() == pcbnew.F_SilkS else pcbnew.B_Cu
            bb = g.GetBoundingBox()
            bb.Inflate(bl.mm(margin) + g.GetWidth() // 2)
            for p, pb in pads:
                if p.GetParent().GetReference() != f.GetReference() and p.IsOnLayer(cu) and bb.Intersects(pb) \
                        and p.GetEffectiveShape(cu).Collide(g.GetEffectiveShape(), bl.mm(margin) + g.GetWidth() // 2):
                    f.Remove(g)
                    n += 1
                    break
    return n


print("silk segments removed over pads:", strip_silk_over_pads())

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
print(f"{'TL401 stub (tap -> NT401 pad 1)':42s} {W:5.2f} {l_stub:7.3f} {l_stub * bl.PS_MM50:6.1f}  (+ {TAU_END:.1f} ps short = 80.0 ps)")
la, lk = blk.route_len("STRB_A arm"), blk.route_len("STRB_K arm")
print(f"STRB_A / STRB_K arms {la:.3f} / {lk:.3f} mm = {la * bl.PS_MM50:.1f} / {lk * bl.PS_MM50:.1f} ps, mismatch "
      f"{abs(la - lk) * 1e3:.1f} um (mirror images, R204 on the axis)")
o11 = blk.pad("U101", "11")
r1 = blk.pad("R201", "@" + A("BUF_OUT_S"))
print(f"BUF802 OUT pin centre -> R201 pad 1 centre {r1[0] - o11[0]:.3f} mm; SMA pad end -> Ctop pad 1 edge "
      f"{FI.pad('C101', '1')[0] - 0.27 - X_PAD_END:.3f} mm")

# 6L tables: impedance, pad compensation, node capacitance, via placement
print("impedance (JLC06161H-3313, L1 over L2 h 0.0994 mm er 4.1, mask corrected; L6 over L5 identical)")
for z_ in (50, 73, 100):
    w_ = bl.width_for_6l(z_)
    print(f"  {z_:3d} R: w {w_:.3f} mm (drawn {bl.r01(w_):.2f}: {bl.microstrip_6l(bl.r01(w_))[0]:.1f} R)")
for w_ in (W, W_HOLD, W_SIG, 0.3, 0.4):
    z_, ee_ = bl.microstrip_6l(w_)
    print(f"  w {w_:.2f} mm: Z0 {z_:5.1f} R, eps_eff {ee_:.3f}, {math.sqrt(ee_) / bl.C0:.3f} ps/mm, "
          f"{c_mm(w_) * 1e3:.0f} fF/mm")
print(f"pad compensation (excess C of a pad vs. the {W} mm line over the same length; if > {C_EXCESS_MAX * 1e3:.0f} fF "
      f"L2 / L3 / L4 cut under the pad (L5 reference), cut length along the line sized for zero excess)")
print(f"stub end: net tie {L_TIE * 1e3:.0f} pH + via L1->L2 {L_VIA_L2 * 1e3:.0f} pH = {TAU_END:.2f} ps; line "
      f"{L_STUB:.3f} mm = {L_STUB * bl.PS_MM50:.2f} ps; total {L_STUB * bl.PS_MM50 + TAU_END:.2f} ps")
print(f"  {'pad':10s} {'across':>6s} {'along':>6s} {'over L2 fF':>10s}  action       {'after fF':>8s}")
for row in sorted(PADCOMP):
    print(f"  {row[0]:10s} {row[1]:6.2f} {row[2]:6.2f} {row[3]:10.1f}  {row[4]:12s} {row[5]:8.1f}")


def node_c(net):
    """layout capacitance of a net's F.Cu copper (pF): (as cut, all over L2)"""
    cc, c2 = 0.0, 0.0
    for f_ in blk.fps.values():
        for pd in f_.Pads():
            if pd.GetNetname() == net and pd.IsOnLayer(pcbnew.F_Cu):
                bb = pd.GetBoundingBox()
                a_, b_ = sorted((pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())))
                h_ = H5 if _in_win(*blk.loc(pd.GetPosition())) else H2
                cc += c_mm(a_, h_) * b_
                c2 += c_mm(a_) * b_
    for t in blk.b.GetTracks():
        if t.GetNetname() == net and t.GetLayer() == pcbnew.F_Cu and not isinstance(t, pcbnew.PCB_VIA):
            a_, b_ = blk.loc(t.GetStart()), blk.loc(t.GetEnd())
            l_ = math.hypot(b_[0] - a_[0], b_[1] - a_[1])
            w_ = pcbnew.ToMM(t.GetWidth())
            h_ = H5 if _in_win((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2) else H2
            cc += c_mm(w_, h_) * l_
            c2 += c_mm(w_) * l_
    return cc, c2


print(f"node capacitance (layout copper only; windows: L2 / L3 / L4 cleared, reference L5 at {H5:.3f} mm)")
for lab, net_ in (("hold node (D202.3 / U201.3 / C205)", A("HOLD")), ("divider node GA (C101.2 / R104 / C102)", A("GA")),
                  ("BUF802 input (R104.2 / U101.2 / R105)", A("BUF_IN")), ("SMA centre pad + taper (VIN)", A("VIN"))):
    cc, c2 = node_c(net_)
    print(f"  {lab:42s} {cc * 1e3:6.0f} fF   (over solid L2: {c2 * 1e3:6.0f} fF)")


def _dseg(p, a, b):
    ux, uy = b[0] - a[0], b[1] - a[1]
    n2 = ux * ux + uy * uy or 1e-12
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ux + (p[1] - a[1]) * uy) / n2))
    return math.hypot(p[0] - a[0] - t * ux, p[1] - a[1] - t * uy)


bad_v = []
for v in blk.b.GetTracks():
    if not isinstance(v, pcbnew.PCB_VIA):
        continue
    pv, rv = blk.loc(v.GetPosition()), pcbnew.ToMM(v.GetWidth()) / 2
    if _in_win(*pv):
        bad_v.append((v.GetNetname(), pv, "node window"))
    for q, w in RFPOLY:
        if min(_dseg(pv, a, b) for a, b in zip(q, q[1:])) < w / 2 + rv + 0.1:
            bad_v.append((v.GetNetname(), pv, "RF copper"))
            break
print(f"vias in node windows / within 0.1 mm of RF or stub copper: {len(bad_v)}", bad_v[:10])
# BIASTEE-6: no via in or touching a soldered pad (net-tie pads and test points excepted: no solder / by design)
in_pad = []
for v in blk.b.GetTracks():
    if not isinstance(v, pcbnew.PCB_VIA):
        continue
    for f_ in blk.fps.values():
        if f_.GetReference().startswith(("NT", "TP", "TL")):
            continue
        for pd in f_.Pads():
            if f_.GetReference().startswith("U") and min(pcbnew.ToMM(pd.GetSize().x), pcbnew.ToMM(pd.GetSize().y)) > 0.8:
                continue                         # exposed pads: thermal / ground vias by design
            for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
                if pd.IsOnLayer(lay) and pd.GetEffectiveShape(lay).Collide(v.GetEffectiveShape(lay), 0):
                    in_pad.append((f"{f_.GetReference()}.{pd.GetNumber()}", v.GetNetname(), blk.loc(v.GetPosition())))
print(f"vias in / touching soldered pads: {len(in_pad)}", in_pad[:12])

# ============================================================================= checks
import floorplan as fpl
mem = fpl.membership(nl)
REFS = sorted([r for r, b_ in mem.items() if b_ == "analog" and r not in ("J102", "R122")] +
              ["C402", "C403", "C404", "C407", "C408", "C409"] +
              ["C606", "C614", "C616", "C622"])         # power-sheet capacitors moved to the loads (24 Nov schematic)
RF = {A(n): W for n in ("VIN", "BUF_OUT_S", "BUF_OUT_T", "BRG_IN", "BRG_A", "BRG_K", "STRB_A", "STRB_K", "CLIP",
                        "TRF2_OUT", "TRF2_RFIN", "TRF2_IN", "PADN", "TRF1_OUT", "TRF1_RFIN", "TRF1_IN",
                        "S_STROBE_P", "S_STROBE_N")}
res = bl.check_board(out, refs=REFS, rf_widths=RF, verbose=12)
if os.environ.get("DETAIL"):
    for k_ in ("pad_axis", "clearance", "corner"):
        print(k_, res["details"][k_])


def courtyard_overlaps(pcb, min_area=0.005):
    """courtyard rule: no two footprints on the same side with overlapping courtyards (area > min_area mm2)"""
    b_ = pcbnew.LoadBoard(pcb)
    cs = []
    for f in b_.GetFootprints():
        f.BuildCourtyardCaches()
        for lay in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            ps = f.GetCourtyard(lay)
            if ps.OutlineCount():
                cs.append((f.GetReference(), lay, ps, ps.BBox()))
    hits = []
    for i in range(len(cs)):
        for j in range(i + 1, len(cs)):
            a_, c_ = cs[i], cs[j]
            if a_[1] != c_[1] or not a_[3].Intersects(c_[3]):
                continue
            x_ = pcbnew.SHAPE_POLY_SET(a_[2])
            x_.BooleanIntersection(c_[2], pcbnew.SHAPE_POLY_SET.PM_FAST)
            ar = x_.Area() / 1e12
            if ar > min_area:
                hits.append(f"{a_[0]}/{c_[0]} {ar:.3f} mm2")
    return hits


_crt = courtyard_overlaps(out)
print(f"courtyard overlaps (> 0.005 mm2, same side): {len(_crt)}", _crt[:20])
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
    render(os.path.join(HERE, "analog_detail.png"), lay, (99.5, 103.5, 117.5, 122.0))
    render(os.path.join(SCR, "analog_b.png"), ("B.Cu", "B.Fab", "Dwgs.User"), (99.5, 99.5, 156.5, 122.0))
