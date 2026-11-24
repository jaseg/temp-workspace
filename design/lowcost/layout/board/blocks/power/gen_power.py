#!/usr/bin/env python3
"""POWER block of the scope-fe board (power sheet, refs 6xx), power tree of docs/research/power-tree.md (24 Nov 2026):
USB-C J601 (+ USBLC6 U608 on USB_DP / USB_DM), PTC F601, TVS D601, FB601 -> VBUS;
U601 TPS62A01A buck VBUS -> +3V3 (F, top-left); U602 TPS62A01A buck +3V3 -> +1V2 (B, under U601);
U603 TPS63802 buck-boost VBUS -> +5V1 (F, top-middle, the block's east-most free area);
U604 LM27762 +5V1F -> +5V / -5V and U605 LM27762 +3V3_CP -> +2V5 / -2V5 (F, left column, outputs to the W edge).
C606, C614, C615, C616, C620, C622 (power sheet) are placed at their loads in other blocks (kicad/README.md table).
Local mm, origin = block top-left = board (74, 0); +x east (J601 on the board's right edge at local x 26).
Run: cd blocks/power && python3 gen_power.py [--norender]
"""
import sys, os, math
os.environ["BL_STACKUP"] = "6L"            # native 6-layer block (JLC06161H-3313, RULES rule 10): supplies land on L4 (In3)
sys.path.insert(0, "../..")
import boardlib as bl
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/fix/block-power"
os.makedirs(SCR, exist_ok=True)
BW, BH = 26.0, 22.5
HOLE = (23.0, 3.0)                       # M3 hole at board (97, 3): keep 3.5 mm
MOVED = {"C606", "C614", "C615", "C616", "C620", "C622"}   # power-sheet capacitors placed at loads in other blocks
blk = bl.Block("power")
nl = blk.nl
W_USB, S_USB = 0.18, 0.22                # 90 R edge-coupled microstrip over L2 at 0.0994 mm (IPC-2141: 89 R), pitch 0.40 kept
WP, WS = 0.6, 0.25                       # power / signal track widths
VD, VDR = 0.6, 0.3                       # power vias


def diff90(w, s):
    z = bl.microstrip(w)[0]
    return z, 2 * z * (1 - 0.48 * math.exp(-0.96 * s / bl.H))


def bplace(ref, x, y, rot=0, side="F"):
    """local helper: Block.place(side="B") crashes in pcbnew 7.0.11; place on F, then flip (mirror in x)"""
    fp = blk.place(ref, x, y, rot, "F")
    if side == "B":
        fp.Flip(blk.P(x, y), True)
        fp.Reference().SetLayer(pcbnew.B_Fab)
    return fp


def two(ref, x, y, first, net, side="F"):
    """2-terminal part centred at (x, y); its pad on `net` lies to the `first` side (W/E/N/S)"""
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


def P(ref, net):
    return blk.pad(ref, "@" + net)


def T(net, pts, w=WS, layer="F.Cu", name=None):
    return blk.track(net, w, pts, layer, name=name)


def V(x, y, net, d=VD, dr=VDR):
    return blk.via(x, y, net, d, dr)


def G(x, y, d=bl.VIA_D, dr=bl.VIA_DRILL):
    return blk.via(x, y, "GND", d, dr)


def cpoly(pts, c=0.15):
    """closed polygon with every corner sharper than 45 deg cut by a 45-degree chamfer of leg c (rule 3)"""
    n = len(pts)
    out = []
    for i in range(n):
        a, b_, cc = pts[i - 1], pts[i], pts[(i + 1) % n]
        if bl.turn_deg(a, b_, cc) < 45.5:
            out.append(b_)
            continue
        la, lc = math.hypot(b_[0] - a[0], b_[1] - a[1]), math.hypot(cc[0] - b_[0], cc[1] - b_[1])
        k = min(c, la / 2.01, lc / 2.01)
        out.append((b_[0] - (b_[0] - a[0]) / la * k, b_[1] - (b_[1] - a[1]) / la * k))
        out.append((b_[0] + (cc[0] - b_[0]) / lc * k, b_[1] + (cc[1] - b_[1]) / lc * k))
    return out


def Z(net, layer, pts, prio=2, cl=0.2, ch=0.15):
    return blk.zone(net, (layer,), cpoly(pts, ch) if ch else pts, clearance=cl, prio=prio)


def R(x0, y0, x1, y1):
    return bl.rect_pts(x0, y0, x1, y1)


# ============================================================================= placement: USB / protection (unchanged)
bplace("J601", 21.85, 13.5, 90)          # USB-C on the right board edge, pads facing west
bplace("U608", 13.0, 13.5, 0)            # ESD array, flow-through (pins 6-1 DP, 4-3 DM)
two("F601", 15.45, 20.2, "N", "/power/VBUS_IN")
two("D601", 21.0, 20.75, "W", "/power/VBUS_F")
two("FB601", 13.45, 20.54, "S", "/power/VBUS_F")
two("R602", 15.0, 11.08, "E", "/power/CC2", "B")
two("R601", 15.0, 15.9, "E", "/power/CC1", "B")


# ============================================================================= buck cell (TPS62A01A, SOT-563)
def buck(u, cin, cin_hf, lx, cout, rtop, rbot, cff, cx, cy, side, vin, vout, sw):
    """chip rot 180: VIN / SW / GND (pins 3 / 2 / 1) face +sx, EN / FB / PG face -sx.  CIN (0805) straddles pins 3 / 1
    beside the chip with SW leaving between its pads (0.9 mm gap) to the inductor; COUT sits under CIN (courtyards
    touching), VOUT pad against the inductor pad 2, GND pad straight under pin 1 / the CIN GND pad.
    sx = +1 on F; on B the cell is the mirror image (sx = -1).  Returns X(dx) -> local x."""
    sx = 1 if side == "F" else -1
    X = lambda dx: cx + sx * dx
    E = "E" if sx > 0 else "W"
    bplace(u, cx, cy, 180, side)
    two(cin, X(2.35), cy, "N", vin, side)
    two(lx, X(4.7), cy + 1.075, "N", sw, side)
    # TIGHTEN (24 Nov, user review): COUT directly under CIN, its VOUT pad against the inductor's output pad and its GND
    # pad straight under GND (1) / the CIN GND pad (courtyards touching CIN, the chip and the inductor)
    two(cout, X(1.65), cy + 2.68, E, vout, side)
    two(rtop, X(-1.85), cy - 0.55, "N", vout, side)
    two(rbot, X(-1.85), cy + 1.33, "S", "GND", side)
    if cff:
        two(cff, X(-2.8), cy - 0.55, "N", vout, side)
    if cin_hf:
        two(cin_hf, X(0.95), cy - 2.25, E, vin, side)
    return X


def buck_routes(X, cy, side, vin, vout, sw, fb, cff, hf=True):
    """copper of one buck cell (mirror-image on B): SW track, VIN / GND / VOUT polygons, EN, FB divider"""
    L_ = "F.Cu" if side == "F" else "B.Cu"
    xs = lambda pts: [(X(x - 3.4), y) for x, y in pts]          # cell geometry drawn for the F cell at cx = 3.4
    T(sw, xs([(4.15, cy), (8.1, cy)]), 0.35, L_)                   # pin 2 -> between the CIN pads -> inductor pad 1
    # GND: pin 1 + CIN GND pad + COUT GND pad in one polygon; the plane vias sit at the capacitor pads (east of the
    # CIN GND pad, under the COUT GND pad), none at the chip
    Z("GND", L_, xs([(3.6, 3.4), (6.55, 3.4), (6.55, 3.8), (7.1, 3.8), (7.1, 4.3), (6.55, 4.6), (4.75, 4.6),
                     (4.75, 6.55), (5.5, 6.55), (5.5, 7.95), (3.6, 7.95)]), prio=3)
    # VOUT: inductor pad 2 -> COUT VOUT pad -> vias behind the capacitor (south of it)
    Z(vout, L_, xs([(5.45, 4.85), (9.2, 4.85), (9.2, 5.85), (7.4, 5.85), (7.4, 7.3), (5.75, 7.3), (5.75, 6.45),
                    (5.45, 6.45)]), prio=4)
    T(vin, xs([(2.65, 2.5), (2.65, 2.0), (3.05, 1.6), (3.75, 1.6), (4.15, 2.0), (4.15, 2.45)]), WS, L_)  # EN (4) = VIN
    T(fb, xs([(2.65, 3.0), (1.55, 3.0)]), WS, L_)
    T(fb, xs([(1.55, 2.96), (1.55, 3.82)]), WS, L_)
    if cff:
        T(vout, xs([(0.6, 1.95), (1.55, 1.95)]), WS, L_)
        T(fb, xs([(0.6, 2.95), (1.55, 2.95)]), WS, L_)
    # TIGHTEN (24 Nov): GND vias at the capacitor GND pads (CIN east side, COUT south side), mirrored for the B cell,
    # so each via position serves both cells (3 per cell, 6 in all; were 8 per cell in the middle of the polygon)
    for x, y in xs([(6.85, 4.05), (4.3, 6.95), (4.3, 7.65)]):
        G(x, y)
    if hf:
        T("GND", xs([(3.87, 0.75), (3.25, 0.75), (3.25, 1.0)]), WS, L_)   # CIN_hf ground
        G(*xs([(3.25, 1.0)])[0])
    for x, y in xs([(6.35, 6.95), (7.0, 6.95)]):                   # VOUT vias behind COUT (L4 +3V3)
        if side == "F":
            V(x, y, vout, bl.VIA_D, bl.VIA_DRILL)


XB1 = buck("U601", "C603", None, "L602", "C604", "R609", "R610", "C631", 3.4, 3.0, "F",
           "VBUS", "+3V3", "Net-(U601-SW)")
XB2 = buck("U602", "C609", "C607", "L603", "C605", "R611", "R612", None, 6.15, 3.0, "B",
           "+3V3", "+1V2", "Net-(U602-SW)")
two("C608", 0.6, 8.85, "N", "+1V2", "B")     # 1u at the +1V2 output (U602 COUT HF); 0.4 mm west of the U604 VIN via

# ============================================================================= U603 TPS63802 buck-boost (F, top-middle)
UX = 11.35                               # U603 centre x (TIGHTEN: +0.4 so C601 fits between L602 and L601)
bplace("U603", UX, 4.9, 0)               # W: EN MODE AGND FB PG (1-5); E: VIN L1 GND L2 VOUT (10, 9, 8, 7, 6)
# 24 Nov (user review): L601 right against the L1 / L2 pins (courtyards touching), capacitors horizontal.
# TIGHTEN (24 Nov, second review; TPS63802 datasheet 12.2 layout example: CIN / COUT at the VIN / VOUT ends of the pin
# row, GND pads joined to PGND next to the chip): C601 courtyard on the chip's north courtyard edge, C610 on its south
# edge (0.0 mm, also touching L601 / L602), VBUS / +5V1 pad straight above VIN (10) / below VOUT (6), GND pad west,
# returned to PGND (8) through the 0.9 mm channel between the two pin columns; C611 stacked under C610
two("L601", UX + 4.0, 4.9, "N", "Net-(U603-L1)")
two("C601", UX - 0.2, 2.12, "E", "VBUS")
two("C610", UX - 0.2, 7.68, "E", "/+5V1")
two("C611", UX - 0.2, 9.64, "E", "/+5V1")
two("R603", 13.78, 9.3, "W", "/+5V1")    # FB divider east of C611, away from L1 / L2 (FB on In2 from the pin)
two("R604", 15.64, 9.3, "E", "GND")
two("C632", 15.2, 6.0, "W", "VBUS", "B")  # DNP VBUS damper (tantalum): VBUS pad on the B strip, off the C601 vias
# DECOUPLING-8 (24 Nov): C602 100n (was 2 mm from U601, whose C603 straddles its pins) moved to the USBLC6 VBUS pin:
# B side under U608 pin 5, VBUS pad on the B VBUS strip, GND pad into the B pour
two("C602", 14.65, 14.3, "W", "VBUS", "B")

# ============================================================================= LM27762 cells (WSON-12, F)
# REPAIR (24 Nov, recheck RP-1; datasheet SNVSAF7C 7.4.1: COUT+ / COUT- on the IC's layer next to OUT+ / OUT-, no vias
# between pin and capacitor; user rule: plane vias at the capacitors, not at the IC pins).  The four 10u LDO output
# capacitors moved from B to F (moved, not added): C617 north of U604 (OUT+ pad 1.3 mm from pin 11), C621 under U604
# (OUT- pad 0.4 mm from pin 6, vertical), C630 east of the gap U604 / U605 (U605 OUT+), C628 under U605 (OUT-).  Each
# capacitor's GND pad returns to the EP / pour on L1 and carries its own plane via; the rail vias (bead side, sense
# taps) sit behind the capacitors.  To make room the FB+ / FB- dividers of U604 and the FB- divider of U605 went to
# B (slow parts, RULES rule 8) right under the cell, U605's FB+ divider into the free F strip north of C625, U604
# moved up 0.30 mm and U605 up 0.45 mm.
CY4, CY5, CXL = 11.65, 18.55, 4.8


def lm(u, cin, cin_hf, ccp, c1, cx, cy):
    """rot 0: W column PGOOD FB+ VIN GND CP OUT- (1-6), E column EN+ OUT+ C1+ C1- EN- FB- (12-7).
    CIN at pins 3 / 4 (W), CCP south-west, C1 at pins 10 / 9 (E)."""
    bplace(u, cx, cy, 0)
    n = lambda p: nl.net_of(u, p)
    if cin_hf:
        two(cin_hf, cx - 2.1, cy, "N", n("3"))
        two(cin, cx - 3.55, cy, "N", n("3"))
    else:
        two(cin, cx - 2.45, cy, "N", n("3"))
    if ccp == "C619":
        two(ccp, cx - 2.42, cy + 2.75, "E", n("5"))
    else:
        two(ccp, cx - 2.65, cy + 3.0, "E", n("5"))
    two(c1, cx + (2.2 if c1 == "C618" else 2.05), cy, "N", n("10"))


lm("U604", "C612", "C613", "C626", "C618", CXL, CY4)
lm("U605", "C625", None, "C619", "C624", CXL, CY5)
N4 = lambda p: nl.net_of("U604", p)
N5 = lambda p: nl.net_of("U605", p)
# U604 outputs (F): C617 OUT+ north (courtyard on the chip's), C621 OUT- vertical under pin 6; FB604 vertical north-east
two("C617", 5.6, CY4 - 2.73, "E", "/power/+5V_LDO")
two("C621", 4.85, CY4 + 3.45, "N", "/power/-5V_LDO")
two("FB604", 8.05, CY4 - 3.0, "S", "/power/+5V_LDO")
# U605 outputs (F): C630 OUT+ vertical east of C621 (pad 0.55 mm from pin 11's track), C628 OUT- under the chip
two("C630", 7.3, CY4 + 4.25, "S", "/power/+2V5_LDO")
two("C628", 5.58, CY5 + 2.85, "W", "/power/-2V5_LDO")
# feedback dividers: U604 on B under the cell; U605 FB+ on F north of C625, FB- on B under the cell
two("R614", 2.6, CY4 - 2.9, "E", N4("2"), "B")      # GND <-> FB+
two("R613", 4.6, CY4 - 2.9, "W", N4("2"), "B")      # FB+ <-> OUT+
two("R605", 4.9, CY4 + 1.95, "E", N4("7"), "B")     # OUT- <-> FB-
two("R606", 6.75, CY4 + 2.7, "N", N4("7"), "B")     # FB- <-> GND
two("R615", 1.07, CY5 - 2.31, "W", "/power/+2V5_LDO")  # OUT+ <-> FB+ (F)
two("R616", 2.94, CY5 - 2.31, "E", "GND")              # FB+ <-> GND (F)
two("R607", 4.7, CY5 + 3.1, "W", "/power/-2V5_LDO", "B")  # OUT- <-> FB-
two("R608", 6.4, CY5 + 2.6, "N", N5("7"), "B")            # FB- <-> GND

# ============================================================================= B side: beads, slow parts
PLACE_B = [  # ref, x, y, first-side, net
    ("FB602", 11.7, 9.3, "N", "/+5V1"),             # +5V1 -> +5V1F (U604 input)
    ("FB603", 2.0, 14.25, "E", "/power/-5V_LDO"),
    ("C627", 1.6, 15.5, "W", "-5V"),
    ("FB605", 2.9, 16.95, "W", "/power/+3V3_CP"),    # +3V3 -> U605 input
    ("R617", 2.4, 19.2, "W", "/power/+3V3_CP"),      # PG pull-up
    ("C629", 0.6, 19.7, "S", "-2V5"),
    ("FB607", 2.0, 21.4, "E", "/power/-2V5_LDO"),
    ("FB606", 8.75, 15.3, "W", "/power/+2V5_LDO"),
]
for ref, x, y, f, n_ in PLACE_B:
    two(ref, x, y, f, n_, "B")
placed = set(blk.fps)
mine = sorted(r for r, c in nl.comps.items() if c["sheet"].startswith("/power") and r not in MOVED)
print("not placed:", sorted(set(mine) - placed))

# ============================================================================= routing: USB (unchanged)
DP, DM = "/USB_DP", "/USB_DM"
W_FO = W_USB                                # fan-out at the 0.5 mm connector pitch
T(DP, [(17.81, 12.75), (15.7, 12.75)], W_FO, name="DP fanout")
T(DP, [(15.7, 12.75), (15.2, 12.75), (15.0, 12.55), (14.14, 12.55)], W_FO, name="DP fanout")
T(DP, [(17.81, 13.75), (16.7, 13.75)], W_FO, name="DP inner")
blk.via(16.7, 13.75, DP)
T(DP, [(16.7, 13.75), (15.7, 12.75)], W_FO, "B.Cu", name="DP hop")
blk.via(15.7, 12.75, DP)
T(DM, [(17.81, 13.25), (16.2, 13.25), (15.2, 14.25)], W_FO, name="DM inner")
T(DM, [(17.81, 14.25), (15.2, 14.25)], W_FO, name="DM fanout")
T(DM, [(15.2, 14.25), (15.0, 14.45), (14.14, 14.45)], W_FO, name="DM fanout")
T(DP, [(14.14, 12.55), (11.86, 12.55)], W_USB, name="DP esd")
T(DM, [(14.14, 14.45), (11.86, 14.45)], W_USB, name="DM esd")
T("GND", [(11.86, 13.5), (11.1, 13.5)], WS)
G(11.1, 13.5)
T("VBUS", [(14.14, 13.5), (15.1, 13.5)], WS)
blk.via(15.1, 13.5, "VBUS")
T(DP, [(11.86, 12.55), (11.0, 12.55), (10.25, 13.3), (9.4, 13.3), (8.6, 14.1), (8.6, BH)], W_USB, name="DP pair")
T(DM, [(11.86, 14.45), (11.0, 14.45), (10.25, 13.7), (9.57, 13.7), (9.0, 14.27), (9.0, BH)], W_USB, name="DM pair")
for nm_, r_ in blk.routes.items():
    if r_["net"] in (DP, DM):
        for q in r_["pts"]:
            blk.rf_keepout(q, W_USB, gap=2 * W_USB)
blk.iface(DP, 8.6, BH, "F.Cu", "S", "pair", W_USB, "90 R pair to U704.34 (mcuif); pitch 0.40, w 0.18 / s 0.22 (6L)")
blk.iface(DM, 9.0, BH, "F.Cu", "S", "pair", W_USB, "90 R pair to U704.33 (mcuif)")
# --- CC pull-downs (B side)
T("/power/CC2", [(17.81, 11.75), (16.7, 11.75)], WS)
blk.via(16.7, 11.75, "/power/CC2")
T("/power/CC2", [(16.7, 11.75), (16.03, 11.08), ("R602", "1")], WS, "B.Cu")
T("/power/CC1", [(17.81, 14.75), (16.7, 14.75)], WS)
blk.via(16.7, 14.75, "/power/CC1")
T("/power/CC1", [(16.7, 14.75), (16.7, 15.45), (16.25, 15.9), ("R601", "1")], WS, "B.Cu")
for r in ("R601", "R602"):
    x, y = blk.pad(r, "2")
    yv = y + 0.75 if r == "R602" else y - 0.7
    T("GND", [(x, y), (x, yv)], WS, "B.Cu")
    G(x, yv)
# --- connector GND to the shell, VBUS_IN joined on B.Cu (vias beside the pads, under the body)
T("GND", [(17.81, 10.25), (17.81, 9.3)], 0.5)
T("GND", [(17.81, 16.75), (17.81, 17.7)], 0.5)
T("/power/VBUS_IN", [(17.81, 11.05), (18.6, 11.05), (18.95, 11.4), (18.95, 11.5)], 0.45)
T("/power/VBUS_IN", [(17.81, 15.95), (18.6, 15.95), (18.95, 15.6), (18.95, 15.5)], 0.45)
V(18.95, 11.5, "/power/VBUS_IN")
V(18.95, 15.5, "/power/VBUS_IN")
T("/power/VBUS_IN", [(18.95, 11.5), (18.95, 15.5)], 0.7, "B.Cu")
T("/power/VBUS_IN", [(17.81, 15.95), (16.3, 15.95), (15.45, 16.8), ("F601", "1")], WP)
# --- PTC -> TVS / FB601 -> VBUS
T("/power/VBUS_F", [("F601", "2"), (16.5, 21.6), (17.35, 20.75), ("D601", "2")], 0.8)
T("/power/VBUS_F", [("F601", "2"), ("FB601", "1")], 0.8)
T("GND", [("D601", "1"), (23.0, 18.0)], 0.8)
G(22.2, 22.1); G(23.8, 22.1)
T("VBUS", [("FB601", "2"), (13.45, 19.0), (14.0, 18.45), (14.0, 17.4)], 0.8)
V(14.0, 18.3, "VBUS"); V(14.0, 17.4, "VBUS")
blk.iface("VBUS", 14.0, 17.85, "In3.Cu", "S", "supply", None,
          "via pair at FB601; J501 pin 1 only (the GVA-84+ chokes moved to +5V1)")
T("VBUS", [(15.1, 13.5), (13.6, 13.5)], 0.4, "B.Cu")

# ============================================================================= routing: VBUS input of U601 / U603
# F polygon: C603 / U601.3 / C602 (top-left) along the top edge to C601 / U603.10 / EN / MODE; fed from the B strip
# TIGHTEN (24 Nov): F polygon = vias behind C601 (13.0, 0.65-1.95) -> C601 VBUS pad -> U603 VIN (10), and a strip along
# the top edge (north of C601's GND pad) to C603 -> U601 VIN (3); the vias at U603's pins are gone
# (the strip widens to y 2.05 over L602 between x 6.6 and 8.65, so that the C607 GND via (6.3, 1.0) and the +1V2
# sense via (8.0, 1.2) cannot cut it in two next to the board edge's copper clearance)
Z("VBUS", "F.Cu", [(5.0, 0.3), (13.45, 0.3), (13.45, 2.25), (12.8, 2.25), (12.8, 4.02), (11.6, 4.02), (11.6, 1.15),
                   (8.65, 1.15), (8.65, 2.05), (6.6, 2.05), (6.6, 2.62), (3.9, 2.62), (3.9, 2.2), (5.0, 2.2)], prio=5)
for y in (0.65, 1.3, 1.95):
    V(13.0, y, "VBUS")
Z("VBUS", "B.Cu", [(12.65, 0.4), (14.2, 0.4), (14.2, 16.6), (14.4, 16.6), (14.4, 18.9), (13.05, 18.9), (13.05, 2.6),
                   (12.65, 2.6)], prio=4)
# U603 EN (1) / MODE (2) = VIN: static tie through In2 (slow / static layer) to the VBUS via behind C601
Z("VBUS", "F.Cu", [(9.4, 3.8), (10.45, 3.8), (10.45, 4.5), (9.4, 4.5)], prio=6, ch=0.1)
V(9.6, 4.15, "VBUS", bl.VIA_D, bl.VIA_DRILL)
T("VBUS", [(9.6, 4.15), (11.6, 2.15), (12.8, 2.15), (13.0, 1.95)], 0.2, "In2.Cu")

# ============================================================================= routing: U601 (+3V3, F) / U602 (+1V2, B)
buck_routes(XB1, 3.0, "F", "VBUS", "+3V3", "Net-(U601-SW)", "Net-(U601-FB)", True, hf=False)
buck_routes(XB2, 3.0, "B", "+3V3", "+1V2", "Net-(U602-SW)", "Net-(U602-FB)", False)
# U601 VOUT sense: R609 / C631 top pads -> +3V3 via (L4 plane)
T("+3V3", [(1.05, 1.95), (1.05, 1.2)], WS)
blk.via(1.05, 1.2, "+3V3")
blk.iface("+3V3", 6.68, 6.95, "In3.Cu", "W", "supply", None,
          "via pair behind C604 (U601 output) into the L4 +3V3 plane; U602 (B) takes its input from L4 at C609")
# U602 input on B: via behind C609 (L4 +3V3) -> C609 / C607 -> pin 3
V(3.6, 0.9, "+3V3", bl.VIA_D, bl.VIA_DRILL)
Z("+3V3", "B.Cu", [(2.95, 0.45), (5.15, 0.45), (5.15, 1.25), (4.65, 1.25), (4.65, 1.95), (5.85, 1.95), (5.85, 2.62),
                   (2.95, 2.62)], prio=5)
# U602 output: L603 -> C605 -> C608 -> +1V2 via (1.0, 7.9); VOUT sense R611 via In2 (slow / static layer) to that via
blk.track("+1V2", 0.5, [(2.4, 7.15), (1.65, 7.9), (0.6, 7.9), (0.6, 8.4)], "B.Cu", ch=0.15)
blk.via(1.0, 7.9, "+1V2")
T("+1V2", [(8.0, 1.94), (8.0, 1.2)], WS, "B.Cu")
blk.via(8.0, 1.2, "+1V2")
T("+1V2", [(8.0, 1.2), (7.2, 0.4), (0.9, 0.4), (0.5, 0.8), (0.5, 7.4), (1.0, 7.9)], 0.2, "In2.Cu")
blk.iface("+1V2", 1.0, 7.9, "In3.Cu", "W", "supply", None, "via at C605 / C608 (U602 output, B)")


# ============================================================================= routing: U603 buck-boost
T("GND", [(UX - 0.9, 4.9), (11.2, 4.9)], 0.2)                              # AGND (3) by its own trace to PGND (8)
# switch nodes: pin 9 (L1) / pin 7 (L2) -> 45-degree flare -> L601 pads
DXU = UX - 10.95
xu = lambda pts: [(x + DXU, y) for x, y in pts]
Z("Net-(U603-L1)", "F.Cu", xu([(11.9, 4.28), (13.05, 4.28), (13.75, 3.58), (13.75, 2.35), (16.15, 2.35), (16.15, 3.75),
                               (14.05, 3.75), (13.28, 4.52), (11.9, 4.52)]), prio=6, ch=0.1)
Z("Net-(U603-L2)", "F.Cu", xu([(11.9, 5.28), (13.28, 5.28), (14.05, 6.05), (16.15, 6.05), (16.15, 7.45), (13.75, 7.45),
                               (13.75, 6.22), (13.05, 5.52), (11.9, 5.52)]), prio=6, ch=0.1)
# PGND (8) copper east under L601 between its pads (no vias there any more)
Z("GND", "F.Cu", xu([(11.9, 4.72), (13.45, 4.72), (14.25, 3.95), (16.6, 3.95), (16.6, 5.85), (14.25, 5.85),
                     (13.45, 5.08), (11.9, 5.08)]), prio=3, ch=0.1)
# hot-loop ground: C601 GND pad -> channel between the pin columns -> PGND (8) <- channel <- C610 / C611 GND pads
Z("GND", "F.Cu", [(10.3, 1.6), (11.4, 1.6), (11.4, 10.4), (10.65, 10.4), (10.65, 11.25), (9.95, 11.25), (9.95, 10.4),
                  (9.65, 10.4), (9.65, 6.6), (10.95, 6.6), (10.95, 3.55), (9.4, 3.55), (9.4, 3.0), (10.3, 3.0)],
  prio=6, ch=0.1)
# GND vias at the capacitor GND pads, on the side away from the hot loop (west / south)
V(9.2, 1.95, "GND", VD, VDR)                                               # C601, west
G(9.7, 3.3)                                                                # C601, south-west
T("GND", [(9.2, 1.95), (9.7, 1.95)], 0.6)
G(9.25, 7.45)                                                              # C610, west
T("GND", [(9.25, 7.45), (9.7, 7.45)], 0.45)
G(10.3, 10.95)                                                             # C611, south (also C617 on B)
# +5V1: VOUT (6) -> C610 / C611 +5V1 pads -> vias behind C611 (B strip / L3 rail); R603 top pad on the same polygon
Z("/+5V1", "F.Cu", [(11.6, 5.75), (12.85, 5.75), (12.85, 8.9), (13.6, 8.9), (13.6, 9.7), (12.85, 9.7), (12.85, 12.0),
                    (11.15, 12.0), (11.15, 10.75), (11.6, 10.75)], prio=5)
for y in (10.95, 11.65):
    V(12.4, y, "/+5V1", bl.VIA_D, bl.VIA_DRILL)
# FB (4): via west of the pin -> In2 -> via at the R603 / R604 junction (east of C611, away from L1 / L2)
T("Net-(U603-FB)", [(UX - 0.9, 5.4), (9.65, 5.4)], 0.2)
V(9.65, 5.4, "Net-(U603-FB)", bl.VIA_D, bl.VIA_DRILL)
T("Net-(U603-FB)", [(9.65, 5.4), (10.15, 5.9), (10.15, 10.2), (10.4, 10.45), (14.2, 10.45), (14.71, 9.94)], 0.2,
  "In2.Cu")
T("Net-(U603-FB)", [(14.27, 9.3), (15.15, 9.3)], 0.2)
T("Net-(U603-FB)", [(14.71, 9.3), (14.71, 9.94)], 0.2)
V(14.71, 9.94, "Net-(U603-FB)", bl.VIA_D, bl.VIA_DRILL)
# PG (pin 5) -> via -> In2 -> U605 EN+ / EN- network (B)
T("/power/PG_5V1", [(UX - 0.9, 5.9), (9.85, 5.9), (9.6, 6.15)], 0.2)
blk.via(9.6, 6.15, "/power/PG_5V1")
T("/power/PG_5V1", [(9.6, 6.15), (8.3, 7.45), (8.3, 18.2), (7.9, 18.6)], 0.2, "In2.Cu")
blk.via(7.9, 18.6, "/power/PG_5V1")
# +5V1 on B: polygon under C610 / C611 -> FB602 (B) -> +5V1F network; strip south to the GVA-84+ interface
Z("/+5V1", "B.Cu", [(10.9, 6.3), (12.85, 6.3), (12.85, 9.0), (10.9, 9.0)], prio=5)
T("/+5V1", [(12.6, 8.8), (12.6, 20.0), (12.3, 20.3), (12.3, 21.7)], 0.5, "B.Cu")
V(12.3, 20.9, "/+5V1"); V(12.3, 21.7, "/+5V1")
blk.iface("/+5V1", 12.3, 21.3, "In3.Cu", "S", "supply", None,
          "NEW: via pair, +5V1 (TPS63802 output, 0.29 / 0.34 A) to the GVA-84+ chokes L404.2 / L406.2 (pstrobe); "
          "replaces the old VBUS strip along the S edge")

# ============================================================================= routing: LM27762 cells (common F part)
def lm_common(u, cin, cin_hf, ccp, c1, cx, cy):
    n = lambda p: nl.net_of(u, p)
    y = lambda k: cy + (-1.25, -0.75, -0.25, 0.25, 0.75, 1.25)[k - 1]      # W pins 1-6
    ye = lambda k: cy + {12: -1.25, 11: -0.75, 10: -0.25, 9: 0.25, 8: 0.75, 7: 1.25}[k]
    xw, xe = cx - 0.95, cx + 0.95
    W2 = 0.25
    T("GND", [(xw, y(1) + 0.05), (cx - 0.3, y(1) + 0.05)], 0.2)                # PGOOD (GND) into the EP
    G(cx, cy - 0.6); G(cx, cy + 0.6)                                         # EP vias
    xc = blk.pad(cin_hf or cin, "@" + bl.canon(n("3")))[0]
    if cin_hf:                                                               # CIN 0402 straight at pins 3 / 4
        T(n("3"), [(xw, y(3)), (xc, y(3))], W2)
        T("GND", [(xw, y(4)), (xc, y(4))], W2)
        xb = blk.pad(cin, "1")[0]
        T(n("3"), [(xc, cy - 0.6), (xb, cy - 0.6)], 0.4)
        T("GND", [(xc, cy + 0.6), (xb, cy + 0.6)], 0.4)
    else:                                                                    # CIN 0805: jog into the pads
        T(n("3"), [(xw, y(3)), (cx - 1.75, y(3)), (cx - 1.95, y(3) - 0.2), (cx - 1.95, y(3) - 0.4)], W2)
        T("GND", [(xw, y(4)), (cx - 1.75, y(4)), (cx - 1.95, y(4) + 0.2), (cx - 1.95, y(4) + 0.4)], W2)
    ycp = blk.pad(ccp, "1")[1]
    T(n("5"), [(xw, y(5)), (cx - 1.45, y(5)), (cx - 1.45, ycp - 0.25)], W2)     # CP south into CCP
    x1 = blk.pad(c1, "1")[0]
    if c1 == "C618":                                                         # 0603: jog into the pads
        T(n("10"), [(xe, ye(10)), (cx + 1.5, ye(10)), (cx + 1.6, ye(10) - 0.1), (x1 - 0.1, ye(10) - 0.1)], W2)
        T(n("9"), [(xe, ye(9)), (cx + 1.5, ye(9)), (cx + 1.6, ye(9) + 0.1), (x1 - 0.1, ye(9) + 0.1)], W2)
    else:                                                                    # 0402: pads in line with pins 10 / 9
        T(n("10"), [(xe, ye(10)), (x1 - 0.05, ye(10))], W2)
        T(n("9"), [(xe, ye(9)), (x1 - 0.05, ye(9))], W2)
    return xw, xe, y, ye


# ============================================================================= routing: U604 (+5V / -5V)
xw, xe, y, ye = lm_common("U604", "C612", "C613", "C626", "C618", CXL, CY4)
cy, cx = CY4, CXL
# OUT+ (11): east, north straight into C617's OUT+ pad; C617 -> FB604 (pad 1) -> +5V via behind the bead
T("/power/+5V_LDO", [(xe, ye(11)), (6.25, ye(11)), (6.25, cy - 2.3)], 0.25)
T("/power/+5V_LDO", [(6.7, cy - 2.2), (7.8, cy - 2.2)], 0.4)
T("+5V", [(8.05, blk.pad("FB604", "@+5V")[1]), (8.05, 7.0)], 0.4)
V(8.05, 7.0, "+5V", bl.VIA_D, bl.VIA_DRILL)
blk.iface("+5V", 8.05, 7.0, "In3.Cu", "W", "supply", None, "via behind FB604 (U604 OUT+ 4.80 V, 41 mA)")
T("/power/+5V_LDO", [(8.3, cy - 2.2), (8.95, cy - 2.2)], 0.25)              # FB+ sense tap behind the bead
V(8.95, cy - 2.2, "/power/+5V_LDO", bl.VIA_D, bl.VIA_DRILL)
# C617 GND pad -> EP (L1) and its plane via (west)
T("GND", [(4.65, cy - 2.3), (4.65, cy - 1.15)], 0.4)
T("GND", [(4.5, cy - 2.5), (4.5, 7.85), (4.3, 7.65)], 0.3)           # -> U601 cell GND via 0.55 mm north of the pad
# EN+ (12) = VIN: via straight north of the pin (B +5V1F strip)
T(N4("12"), [(xe, ye(12)), (xe, cy - 1.7)], 0.2)
V(xe, cy - 1.7, N4("12"), bl.VIA_D, bl.VIA_DRILL)
# FB+ (2): west, north to its via; divider R614 / R613 on B
T(N4("2"), [(xw, y(2)), (cx - 1.5, y(2)), (cx - 1.5, cy - 2.05)], 0.2)
V(cx - 1.5, cy - 2.05, N4("2"), bl.VIA_D, bl.VIA_DRILL)
T(N4("2"), [(cx - 1.5, cy - 2.05), (3.11, cy - 2.24), (3.11, cy - 2.62)], 0.2, "B.Cu")
T(N4("2"), [(3.11, cy - 2.9), (4.09, cy - 2.9)], 0.2, "B.Cu")
T("/power/+5V_LDO", [(8.95, cy - 2.2), (8.25, cy - 2.9), (5.11, cy - 2.9)], 0.2, "B.Cu")
T("GND", [(2.09, cy - 2.9), (2.09, cy - 2.05)], 0.25, "B.Cu")
G(2.09, cy - 2.05)
# OUT- (6): south into C621's OUT- pad; via behind it (east) to the B divider / FB603
T(N4("6"), [(xw, y(6)), (xw, cy + 1.5), (4.25, cy + 1.9), (4.25, cy + 2.25)], 0.25)
T(N4("6"), [(5.4, cy + 2.85), (5.95, cy + 2.85)], 0.4)
V(5.95, cy + 2.85, N4("6"), bl.VIA_D, bl.VIA_DRILL)
T(N4("6"), [(5.95, cy + 2.85), (3.0, cy + 2.85)], 0.4, "B.Cu")              # -> FB603 (B)
T(N4("6"), [(4.39, cy + 2.85), (4.39, cy + 2.2)], 0.25, "B.Cu")           # -> R605
# FB- (7): south to its via; B: R605 / R606
T(N4("7"), [(xe, ye(7)), (xe, cy + 1.7), (6.0, cy + 1.95)], 0.2)
V(6.0, cy + 1.95, N4("7"), bl.VIA_D, bl.VIA_DRILL)
T(N4("7"), [(6.0, cy + 1.95), (5.41, cy + 1.95)], 0.2, "B.Cu")
T(N4("7"), [(6.0, cy + 1.95), (6.24, cy + 2.19), (6.6, cy + 2.19)], 0.2, "B.Cu")
T("GND", [(6.75, cy + 3.21), (7.2, cy + 3.21), (7.65, cy + 2.76), (7.65, cy + 2.5)], 0.25, "B.Cu")
# EN- (8) = VIN: east, south to its via (B +5V1F)
T(N4("8"), [(xe, ye(8)), (cx + 1.45, ye(8)), (cx + 1.45, ye(8) + 0.4), (cx + 1.85, ye(8) + 0.8),
            (cx + 1.95, ye(8) + 0.8)], 0.2)
V(cx + 1.95, ye(8) + 0.8, N4("8"), bl.VIA_D, bl.VIA_DRILL)
# C621 GND pad -> plane via east; C630 GND via north of its pad
T("GND", [(5.4, cy + 4.55), (6.0, cy + 4.55)], 0.3)
G(6.0, cy + 4.55)
G(7.65, cy + 2.5)
# CIN feed: B +5V1F from FB602 to U604 VIN (via behind C612), EN+ and EN-
T("/power/+5V1F", [(1.25, cy - 0.95), (1.25, cy - 1.85)], 0.4)
V(1.25, cy - 1.85, "/power/+5V1F", bl.VIA_D, bl.VIA_DRILL)
T("/power/+5V1F", [("FB602", "2"), (11.7, 11.6), (6.2, 11.6), (6.2, cy - 1.25), (xe, cy - 1.7)], 0.4, "B.Cu")
T("/power/+5V1F", [(6.2, cy - 1.25), (1.7, cy - 1.25), (1.25, cy - 1.7), (1.25, cy - 1.85)], 0.4, "B.Cu")
T("/power/+5V1F", [(CXL + 1.95, ye(8) + 0.8), (CXL + 1.95, 12.15), (6.2, 11.6)], 0.4, "B.Cu")
# B: FB603 -> C627 / -5V via
T("-5V", [(1.12, 15.5), (1.12, 14.25)], 0.4, "B.Cu")
T("-5V", [(1.21, 14.25), (0.75, 14.25), (0.4, 13.9), (0.4, 13.6)], 0.4, "B.Cu")
V(0.4, 13.6, "-5V", bl.VIA_D, bl.VIA_DRILL)
blk.iface("-5V", 0.4, 13.6, "In3.Cu", "W", "supply", None, "via at FB603 / C627 (U604 OUT- -4.64 V, 41 mA)")
# U604 CIN ground via (C613 / C612 GND pads)
T("GND", [(2.7, cy + 0.65), (2.7, cy + 1.2), (2.55, cy + 1.35)], 0.4)
G(2.55, cy + 1.35)

# ============================================================================= routing: U605 (+2V5 / -2V5)
xw, xe, y, ye = lm_common("U605", "C625", None, "C619", "C624", CXL, CY5)
cy, cx = CY5, CXL
# OUT+ (11): east, north into C630's OUT+ pad; via behind it to FB606 (B) and the FB+ sense line (In2)
T("/power/+2V5_LDO", [(xe, ye(11)), (6.3, ye(11)), (6.3, cy - 1.1), (6.55, cy - 1.35), (6.8, cy - 1.35)], 0.25)
T("/power/+2V5_LDO", [(7.6, cy - 1.35), (7.6, cy - 0.8)], 0.4)
V(7.6, cy - 0.8, "/power/+2V5_LDO", bl.VIA_D, bl.VIA_DRILL)
T("/power/+2V5_LDO", [(7.6, cy - 0.8), (7.6, 15.3)], 0.4, "B.Cu")
T("+2V5", [(9.54, 15.3), (10.45, 15.3)], 0.4, "B.Cu")
V(10.45, 15.3, "+2V5", bl.VIA_D, bl.VIA_DRILL)
blk.iface("+2V5", 10.45, 15.3, "In3.Cu", "W", "supply", None, "via at FB606 (U605 OUT+ 2.50 V, 48 mA)")
T("/power/+2V5_LDO", [(7.6, cy - 0.8), (7.25, cy - 1.15), (4.3, cy - 1.15), (4.0, cy - 1.45), (0.75, cy - 1.45),
                      (0.56, cy - 1.64)], 0.2, "In2.Cu")                    # FB+ sense to R615 (F)
V(0.56, cy - 1.64, "/power/+2V5_LDO", bl.VIA_D, bl.VIA_DRILL)
T("/power/+2V5_LDO", [(0.56, cy - 1.64), (0.56, cy - 2.31)], 0.25)
# FB+ (2): west, north to R616 / R615 (F, north of C625)
T(N5("2"), [(xw, y(2)), (3.35, y(2)), (3.35, cy - 1.55), (3.18, cy - 1.72), (2.43, cy - 1.72), (2.43, cy - 2.1)],
  0.2)
T(N5("2"), [(1.58, cy - 2.31), (2.43, cy - 2.31)], 0.2)
T("GND", [(3.45, cy - 2.31), (4.5, cy - 2.31)], 0.3)                       # R616 GND -> C621 GND pad
# EN+ (12) = PG_5V1: via north of the pin
T(N5("12"), [(xe, ye(12)), (xe, cy - 1.7)], 0.2)
V(xe, cy - 1.7, N5("12"), bl.VIA_D, bl.VIA_DRILL)
# EN- (8): short east to its via (0.4 mm)
T(N5("8"), [(xe, ye(8)), (6.2, ye(8))], 0.2)
V(6.2, ye(8), N5("8"), 0.4, 0.2)
# FB- (7): east, via; B: R608 (vertical) / R607
T(N5("7"), [(xe, ye(7)), (6.15, ye(7)), (6.4, ye(7) + 0.25)], 0.2)
V(6.4, ye(7) + 0.25, N5("7"), bl.VIA_D, bl.VIA_DRILL)
T(N5("7"), [(6.4, ye(7) + 0.25), (6.4, cy + 2.05)], 0.2, "B.Cu")
T(N5("7"), [(5.21, cy + 3.1), (5.7, cy + 3.1), (5.7, cy + 2.5), (6.06, cy + 2.14), (6.25, cy + 2.14)], 0.2, "B.Cu")
# OUT- (6): south into C628's OUT- pad; via behind it (north-east) -> B: R607, FB607
T(N5("6"), [(xw, y(6)), (xw, cy + 1.7), (4.25, cy + 2.1), (4.25, cy + 2.35)], 0.25)
T(N5("6"), [(5.55, cy + 1.9), (5.0, cy + 1.9), (5.0, cy + 2.35)], 0.4)
V(5.55, cy + 1.9, N5("6"), bl.VIA_D, bl.VIA_DRILL)
T(N5("6"), [(5.55, cy + 1.9), (4.55, cy + 1.9), (3.9, cy + 2.55), (3.0, cy + 2.55)], 0.4, "B.Cu")
T(N5("6"), [(4.19, cy + 2.26), (4.19, cy + 2.95)], 0.25, "B.Cu")
# C628 GND plane via (east of its pad)
T("GND", [(7.0, cy + 2.85), (7.45, cy + 2.85)], 0.4)
G(7.45, cy + 2.85)
# CIN: +3V3_CP via west of C625 (B: FB605 / R617)
T("/power/+3V3_CP", [(2.35, cy - 0.95), (1.21, cy - 0.95)], 0.4)
V(1.21, cy - 0.95, "/power/+3V3_CP", bl.VIA_D, bl.VIA_DRILL)
T("/power/+3V3_CP", [(2.11, 16.95), (2.11, 17.5), (2.01, cy - 0.95), (1.21, cy - 0.95)], 0.4, "B.Cu")
T("/power/+3V3_CP", [(1.89, 19.2), (1.89, cy - 0.26), (1.21, cy - 0.94)], 0.25, "B.Cu")
T("+3V3", [(4.5, 16.9), (3.9, 16.9)], 0.3, "B.Cu")                       # L4 +3V3 via east of FB605
V(4.5, 16.9, "+3V3", bl.VIA_D, bl.VIA_DRILL)
# PG network (B): R617 -> EN- via -> EN+ via, In2 via from U603 PG
T("/power/PG_5V1", [(2.91, 19.2), (3.5, 19.2), (3.9, 19.6), (5.9, 19.6), (6.2, ye(8))], 0.2, "B.Cu")
T("/power/PG_5V1", [(6.2, ye(8)), (6.6, 18.9), (7.6, 18.9), (7.9, 18.6)], 0.2, "B.Cu")
T("/power/PG_5V1", [(xe, cy - 1.7), (6.4, cy - 1.05), (6.4, 18.7), (6.6, 18.9)], 0.2, "B.Cu")
# -2V5: FB607 -> C629 + via
T("-2V5", [(0.6, 20.18), (0.6, 20.75)], 0.4, "B.Cu")
T("-2V5", [(0.6, 20.75), (0.6, 21.25), (0.75, 21.4), (1.21, 21.4)], 0.4, "B.Cu")
V(0.6, 20.75, "-2V5", bl.VIA_D, bl.VIA_DRILL)
blk.iface("-2V5", 0.6, 20.75, "In3.Cu", "W", "supply", None, "via at FB607 / C629 (U605 OUT- -2.50 V, 50 mA)")
# U605 CIN ground via (C625 / C619)
T("GND", [(2.35, cy + 1.3), (2.35, cy + 1.55), (2.0, cy + 1.9)], 0.4)
G(2.0, cy + 1.9, 0.4, 0.2)
G(17.75, 6.0)                                                            # C632 (B) GND pad, east

# ============================================================================= grounds: F / B pours, In1 plane of the block
# L4 +3V3 stand-in for the board's background plane (removed at merge, gen_board): joins U601's output vias, U602's
# input via (3.6, 0.9) and the R609 sense via inside the block, as on the board
blk.zone("+3V3", ("In3.Cu",), R(0, 0, BW, BH), prio=0)
for l_ in ("F.Cu", "B.Cu"):
    blk.zone("GND", (l_,), R(0, 0, BW, BH), prio=0)
blk.zone("GND", ("In1.Cu",), R(0, 0, BW, BH), prio=0)
blk.keepout([(HOLE[0] + 3.5 * math.cos(a_ * math.pi / 8), HOLE[1] + 3.5 * math.sin(a_ * math.pi / 8)) for a_ in range(16)],
            ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"), tracks=True, vias=True)
blk.edge_rect(0, 0, BW, BH, "Dwgs.User")
out = blk.save(HERE)

for nm_ in blk.routes:
    if blk.routes[nm_]["net"] in (DP, DM):
        print(f"{nm_:12s} {blk.route_len(nm_):6.2f} mm")
print("USB pair: w %.2f s %.2f -> Z0 %.1f R, Zdiff %.1f R (IPC-2141)" % ((W_USB, S_USB) + diff90(W_USB, S_USB)))
import floorplan as fpl
REFS = sorted(r_ for r_, b_ in fpl.membership(nl).items() if b_ == "power" and r_ not in MOVED)
RF = {DP: W_USB, DM: W_USB}
res = bl.check_board(out, refs=REFS, rf_widths=RF, verbose=40)
for k_ in ('unrouted', 'corner', 'pad_axis', 'clearance'):
    print(k_, res['details'][k_] if 'details' in res else '')
_fb = pcbnew.LoadBoard(out)
pcbnew.ZONE_FILLER(_fb).Fill(_fb.Zones())
_rout = os.path.join(SCR, "power_filled.kicad_pcb")
_fb.Save(_rout)
_bb = _fb.ComputeBoundingBox(False)
_ox, _oy = pcbnew.ToMM(_bb.GetX()), pcbnew.ToMM(_bb.GetY())


def render(png, layers, crop):
    """kicad-cli page-size-mode 2 puts the SVG origin at the board bbox; shift the crop (local mm)"""
    x0, y0, x1, y1 = crop
    o = (100.0 - _ox, 100.0 - _oy)
    bl.render(_rout, png, layers, crop=(x0 + o[0], y0 + o[1], x1 + o[0], y1 + o[1]), tmpdir=SCR)


if "--norender" not in sys.argv:
    full = (-0.5, -0.5, BW + 0.5, BH + 0.5)
    render(os.path.join(HERE, "power.png"), ("F.Cu", "F.SilkS", "F.Fab", "Dwgs.User"), full)
    render(os.path.join(HERE, "power_b.png"), ("B.Cu", "B.Fab", "Dwgs.User"), full)
    render(os.path.join(HERE, "power_detail.png"), ("F.Cu", "F.Fab", "Dwgs.User"), (8.5, 0.0, 19.5, 12.0))
    render(os.path.join(HERE, "power_detail_bucks.png"), ("F.Cu", "F.Fab", "Dwgs.User"), (0.0, 0.0, 10.5, 9.0))
    render(os.path.join(SCR, "power_f.png"), ("F.Cu", "F.Fab", "F.CrtYd", "Dwgs.User"), full)
    render(os.path.join(SCR, "power_b.png"), ("B.Cu", "B.Fab", "B.CrtYd", "Dwgs.User"), full)
    render(os.path.join(SCR, "power_in2.png"), ("In2.Cu", "F.Fab", "Dwgs.User"), full)
