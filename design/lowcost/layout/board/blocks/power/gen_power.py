#!/usr/bin/env python3
"""POWER block of the scope-fe board (power sheet, refs 6xx): USB-C J601 (+ USBLC6 U608 on USB_DP / USB_DM),
PTC F601, TVS D601, FB601 -> VBUS; AMS1117 U601 (+3V3, B side) -> AP2112 U602 (+1V2); MT3608 boost U603
(L601, D602, C610 / C611: hot loop SW -> D602 -> C610 -> GND -> U603.2 within 4 x 3 mm) -> FB602 -> +5V4F;
LP2985 U604 (+5V), LP5907 U606 (+2V5), LM27761 U605 (-5V_LDO -> FB603 -> -5V), LM337 U607 (-2V5, B side).
Local mm, origin = block top-left = board (74, 0); +x east (J601 on the board's right edge at local x 26).
Run: cd blocks/power && python3 gen_power.py [--norender]
"""
import sys, os, math
os.environ["BL_STACKUP"] = "6L"            # native 6-layer block (JLC06161H-3313, RULES rule 10): supplies land on L4 (In3)
sys.path.insert(0, "../..")
import boardlib as bl
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board/power"
os.makedirs(SCR, exist_ok=True)
BW, BH = 26.0, 22.5
HOLE = (23.0, 3.0)                       # M3 hole at board (97, 3): keep 3.5 mm
blk = bl.Block("power")
nl = blk.nl
W_USB, S_USB = 0.18, 0.22                # 90 R edge-coupled microstrip over L2 at 0.0994 mm (IPC-2141: 89 R), pitch 0.40 kept
WP, WS = 0.6, 0.25                       # power / signal track widths
VD, VDR = 0.6, 0.3                       # power vias


def diff90(w, s):
    z = bl.microstrip(w)[0]
    return z, 2 * z * (1 - 0.48 * math.exp(-0.96 * s / bl.H))


def bplace(ref, x, y, rot=0, side="F"):
    """local helper: Block.place(side="B") crashes in pcbnew 7.0.11; place on F, then flip"""
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


def G(x, y):
    return blk.via(x, y, "GND")


def Z(net, layer, pts, prio=2, cl=0.2):
    return blk.zone(net, (layer,), pts, clearance=cl, prio=prio)


def R(x0, y0, x1, y1):
    return bl.rect_pts(x0, y0, x1, y1)


# ============================================================================= placement (F = top)
# --- USB-C on the right board edge, pads facing west (rot 90: board y = 13.5 - footprint x)
bplace("J601", 21.85, 13.5, 90)
# --- ESD array between the fan-out and the pair: rot 0 -> pins 6 / 4 (east) take DP / DM from J601,
#     pins 1 / 3 (west) give them to the pair, pins 6-1 and 4-3 joined under the body (flow-through)
bplace("U608", 13.0, 13.5, 0)
# --- protection along the bottom edge: PTC (vertical), TVS, FB601
two("F601", 15.45, 20.2, "N", "/power/VBUS_IN")
two("D601", 21.0, 20.75, "W", "/power/VBUS_F")
two("FB601", 13.45, 20.54, "S", "/power/VBUS_F")
# --- boost (top-left): L601 north of U603, D602 / C610 / C611 west of it
bplace("U603", 8.0, 6.25, 0)
two("L601", 8.2, 2.25, "W", "/power/SW_BOOST")
two("D602", 3.3, 3.1, "E", "/power/SW_BOOST")
two("C610", 2.9, 5.6, "W", "/power/+5V4")
two("C611", 2.9, 7.6, "W", "/power/+5V4")
two("C603", 11.1, 6.3, "N", "VBUS")
two("R603", 6.35, 8.7, "E", "/power/FB_BOOST")
two("R604", 8.30, 8.7, "W", "/power/FB_BOOST")
two("FB602", 2.9, 9.6, "W", "/power/+5V4")
# --- LM27761 inverter (top-middle)
bplace("U605", 15.8, 3.0, 0)
two("C618", 18.175, 0.75, "W", "/power/CF_P")
two("C619", 12.7, 3.25, "E", "/power/CPOUT")
two("C620", 14.3, 5.23, "N", "/power/-5V_LDO")
two("R605", 16.2, 4.75, "E", "/power/VFB_N5")
two("R606", 17.6, 5.23, "N", "/power/VFB_N5")
two("FB603", 15.72, 7.40, "N", "/power/-5V_LDO")
# --- LDO stack (left), rot 180: IN / GND / EN east, OUT (and BP) west -> outputs to the W edge
LDO = {"U604": 12.6, "U606": 16.4, "U602": 20.2}
for u, y in LDO.items():
    bplace(u, 3.2, y, 180)
two("C614", 0.46, 11.17, "S", "/power/BP_5V")
two("C616", 0.46, 14.03, "N", "+5V")
two("C624", 0.46, 17.83, "N", "+2V5")
two("C608", 0.46, 20.67, "S", "+1V2")
two("C615", 6.25, 12.6, "N", "/power/+5V4F")
two("C613", 6.25, 16.4, "N", "/power/+5V4F")
two("C607", 6.25, 20.2, "N", "+3V3")

# ============================================================================= placement (B = bottom)
bplace("U601", 5.0, 4.6, 0, "B")          # AMS1117: pins x 8.15 (1 GND / 2 +3V3 / 3 VBUS), tab x 1.85
bplace("U607", 5.0, 14.4, 0, "B")         # LM337:  pins x 8.15 (1 ADJ / 2 -5V / 3 -2V5), tab (-5V) x 1.85
B_PARTS = [  # ref, x, y, first-side, net
    ("C604", 11.3, 1.4, "W", "+3V3"), ("C605", 11.3, 3.4, "W", "+3V3"), ("C606", 5.0, 0.54, "E", "+3V3"),  # review: y 0.5 left the pads 0.19 mm from the edge
    ("C601", 11.3, 7.9, "W", "VBUS"), ("C602", 8.3, 8.7, "W", "VBUS"),
    ("C612", 4.3, 9.5, "E", "/power/+5V4F"), ("C623", 14.5, 1.5, "E", "/power/+5V4F"),
    ("C621", 11.15, 14.4, "W", "-5V"), ("C622", 15.24, 6.2, "E", "-5V"), ("C627", 15.24, 8.0, "E", "-5V"),
    ("C626", 11.15, 12.1, "W", "/power/ADJ_N25"), ("R607", 10.7, 16.7, "W", "-2V5"),
    ("R608", 10.2, 10.12, "S", "/power/ADJ_N25"),
    ("C628", 11.15, 18.7, "W", "-2V5"), ("C629", 10.7, 20.3, "W", "-2V5"),
    ("C617", 1.9, 19.2, "W", "+5V"), ("C625", 5.6, 19.2, "E", "+2V5"), ("C609", 5.6, 21.4, "E", "+1V2"),
    ("R602", 15.0, 11.08, "E", "/power/CC2"), ("R601", 15.0, 15.9, "E", "/power/CC1"),
]
for ref, x, y, f, n in B_PARTS:
    two(ref, x, y, f, n, "B")

# ============================================================================= checks of placement
placed = set(blk.fps)
mine = sorted(r for r, c in nl.comps.items() if c["sheet"].startswith("/power"))
print("not placed:", sorted(set(mine) - placed))
# ============================================================================= routing
DP, DM = "/USB_DP", "/USB_DM"
W_FO = W_USB                                # fan-out at the 0.5 mm connector pitch
# --- USB fan-out (J601 pads at x 17.81): outer B6 (DP) / B7 (DM) straight on F; inner A6 (DP) hops on B.Cu
T(DP, [(17.81, 12.75), (15.7, 12.75)], W_FO, name="DP fanout")
T(DP, [(15.7, 12.75), (15.2, 12.75), (15.0, 12.55), (14.14, 12.55)], W_FO, name="DP fanout")
T(DP, [(17.81, 13.75), (16.7, 13.75)], W_FO, name="DP inner")
blk.via(16.7, 13.75, DP)
T(DP, [(16.7, 13.75), (15.7, 12.75)], W_FO, "B.Cu", name="DP hop")
blk.via(15.7, 12.75, DP)
T(DM, [(17.81, 13.25), (16.2, 13.25), (15.2, 14.25)], W_FO, name="DM inner")
T(DM, [(17.81, 14.25), (15.2, 14.25)], W_FO, name="DM fanout")
T(DM, [(15.2, 14.25), (15.0, 14.45), (14.14, 14.45)], W_FO, name="DM fanout")
# flow-through under U608 (pins 6-1, 4-3)
T(DP, [(14.14, 12.55), (11.86, 12.55)], W_USB, name="DP esd")
T(DM, [(14.14, 14.45), (11.86, 14.45)], W_USB, name="DM esd")
T("GND", [(11.86, 13.5), (11.1, 13.5)], WS)
G(11.1, 13.5)
T("VBUS", [(14.14, 13.5), (15.1, 13.5)], WS)
blk.via(15.1, 13.5, "VBUS")
# 90 R pair west, then south to the S edge (DP outer of the bend)
qp = T(DP, [(11.86, 12.55), (11.0, 12.55), (10.25, 13.3), (9.4, 13.3), (8.6, 14.1), (8.6, BH)], W_USB, name="DP pair")
qm = T(DM, [(11.86, 14.45), (11.0, 14.45), (10.25, 13.7), (9.57, 13.7), (9.0, 14.27), (9.0, BH)], W_USB, name="DM pair")
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
blk.iface("VBUS", 14.0, 17.85, "In3.Cu", "S", "supply", None, "via pair at FB601; VBUS L4 strip along the S edge (pstrobe GVA chokes)")
# --- VBUS on B.Cu: FB601 vias -> C602 / C601 -> U601.3 and up to the boost (vias beside C603 / U603.5)
Z("VBUS", "B.Cu", [(7.0, 6.0), (9.6, 6.0), (9.6, 4.9), (11.0, 4.9), (11.0, 6.0), (13.95, 6.0), (13.95, 16.6),
                   (14.4, 16.6), (14.4, 18.9), (13.25, 18.9), (13.25, 9.4), (7.0, 9.4)], prio=4)
V(10.3, 5.5, "VBUS"); V(10.2, 6.4, "VBUS")
# --- boost, F side: SW node polygon, VBUS (L601.1, C603, U603.4/5), +5V4 (D602.1, C610, C611, FB602.1)
Z("/power/SW_BOOST", "F.Cu", [(4.45, 2.45), (7.45, 2.45), (7.55, 5.62), (6.15, 5.62), (6.15, 3.8), (4.45, 3.8)], prio=5)
Z("VBUS", "F.Cu", [(8.95, 0.4), (11.75, 0.4), (11.75, 6.0), (10.6, 6.0), (10.6, 7.6), (9.0, 7.6), (9.0, 4.4), (8.95, 4.4)], prio=4)
Z("/power/+5V4", "F.Cu", [(0.9, 2.4), (2.45, 2.4), (2.45, 10.3), (0.9, 10.3)], prio=4)
T("/power/+5V4", [("R603", "1"), (2.4, 8.7)], WS)
T("/power/FB_BOOST", [("U603", "3"), (6.86, 8.7)], WS)
T("/power/FB_BOOST", [("R603", "2"), ("R604", "1")], WS)
T("GND", [("R604", "2"), (9.3, 8.7)], WS); G(9.3, 8.7)
T("GND", [("U603", "2"), (5.25, 6.25), (4.6, 5.6), ("C610", "2")], 0.5)
T("GND", [("C610", "2"), ("C611", "2")], 0.5)
G(4.6, 6.6); G(5.3, 7.3)
T("GND", [("C603", "2"), (11.1, 7.9), (11.5, 8.3), (11.9, 8.3)], 0.5); G(11.9, 8.3)
# --- U601 (B): tab = pin 2 joined under the body, GND pin -> via, +3V3 B polygon (C604 / C605 / C606)
T("+3V3", [("U601", "2"), (1.85, 4.6)], 1.0, "B.Cu")
Z("+3V3", "B.Cu", [(0.2, 0.0), (11.2, 0.0), (11.2, 4.1), (9.4, 4.1), (9.4, 5.4), (6.9, 5.4), (6.9, 8.3), (0.2, 8.3)], prio=3)
T("GND", [("U601", "1"), (7.0, 2.3), (6.0, 1.3), (3.5, 1.3)], 0.5, "B.Cu"); G(3.5, 1.3)
T("GND", [("C606", "2"), (3.85, 0.54)], WS, "B.Cu"); G(3.85, 0.54)
G(12.3, 2.4)
for k in (5.0, 6.0):
    blk.via(0.45, k, "+3V3")
blk.iface("+3V3", 0.45, 5.5, "In3.Cu", "W", "supply", None, "via pair from the U601 tab polygon (B.Cu)")
# --- +5V4F: FB602.2 -> F polygon over the LDO inputs; F track east -> via -> B -> U605.1 / C623 / EN
T("/power/+5V4F", [("FB602", "2"), (5.0, 9.6)], WP)
V(5.0, 9.6, "/power/+5V4F")
Z("/power/+5V4F", "F.Cu", [(4.55, 9.1), (7.7, 9.1), (7.7, 18.0), (4.55, 18.0)], prio=3)
T("/power/+5V4F", [(5.0, 9.6), (5.6, 9.6), (5.65, 9.55), (13.0, 9.55), (13.4, 9.15), (13.4, 4.3)], 0.5)
V(13.4, 4.3, "/power/+5V4F")
T("/power/+5V4F", [(13.4, 4.3), (13.85, 3.85), (13.85, 2.25)], 0.4, "B.Cu")
blk.via(13.85, 2.25, "/power/+5V4F")
T("/power/+5V4F", [(13.85, 2.25), ("U605", "1")], WS)
T("/power/+5V4F", [(13.85, 3.3), (14.98, 2.17), ("C623", "1")], 0.4, "B.Cu")
T("/power/+5V4F", [("U605", "6"), (18.3, 3.25)], WS)
blk.via(18.3, 3.25, "/power/+5V4F")
T("/power/+5V4F", [(18.3, 3.25), (17.35, 4.2), (14.3, 4.2), (13.85, 3.85)], WS, "B.Cu")
T("GND", [("C623", "2"), (13.3, 1.5)], WS, "B.Cu"); G(13.3, 1.5)
# --- LM27761
T("GND", [("U605", "2"), (15.8, 2.75)], WS)
G(15.8, 2.6); G(15.8, 3.4)
T("/power/CF_P", [("U605", "8"), (17.0, 2.25), (17.4, 1.85), ("C618", "1")], WS)
T("/power/CF_N", [("U605", "7"), (17.6, 2.75), (18.95, 1.4), ("C618", "2")], WS)
T("/power/CPOUT", [("U605", "3"), ("C619", "1")], WS)
T("GND", [("C619", "2"), (11.92, 2.4)], WS)
T("/power/-5V_LDO", [("U605", "4"), (14.55, 3.75), (14.3, 4.0), ("C620", "1")], WS)
T("/power/-5V_LDO", [("C620", "1"), ("R605", "1")], WS)
T("/power/-5V_LDO", [(15.7, 4.75), (15.7, 6.34)], 0.4)
T("/power/VFB_N5", [("U605", "5"), (17.1, 3.75), (17.6, 4.25), ("R606", "1")], WS)
T("/power/VFB_N5", [("R605", "2"), (17.6, 4.75)], WS)
T("GND", [("R606", "2"), (17.6, 6.4)], WS); G(17.6, 6.4)
T("GND", [("C620", "2"), (14.3, 6.0), (14.1, 6.2)], WS)
# -5V: FB603.2 -> via pair (L4 iface) -> B: C627 / C622
T("-5V", [("FB603", "2"), (15.72, 9.3)], 0.5)
V(15.72, 9.3, "-5V"); V(16.8, 8.46, "-5V")
T("-5V", [("FB603", "2"), (16.8, 8.46)], 0.5)
T("-5V", [(15.72, 9.3), (15.72, 6.2)], 0.5, "B.Cu")
for c in ("C622", "C627"):
    x, y = blk.pad(c, "2")
    T("GND", [(x, y), (14.1, y)], WS, "B.Cu"); G(14.1, y)
blk.iface("-5V", 15.72, 9.3, "In3.Cu", "W", "supply", None, "via pair at FB603; L4 tongue to U607 tab and W along the top band")
# --- LDO stack (F): GND pins -> via under the body, outputs west to the caps and iface vias
for u, y in LDO.items():
    T("GND", [(u, "2"), (3.2, y)], WS); blk.via(3.2, y, "GND")
for c in ("C615", "C613"):
    x, y = blk.pad(c, "2")
    T("GND", [(x, y), (x, y + 0.67)], WS); G(x, y + 0.67)
T("/power/BP_5V", [("U604", "4"), ("C614", "1")], WS)
T("GND", [("C614", "2"), (0.46, 10.0)], WS); G(0.9, 9.9) if False else None
T("+5V", [("U604", "5"), ("C616", "1")], WP)
T("+5V", [("C616", "1"), (0.45, 12.6)], WP); blk.via(0.45, 12.6, "+5V")
T("+2V5", [("U606", "5"), ("C624", "1")], WP)
T("+2V5", [("C624", "1"), (0.45, 16.2)], WP); blk.via(0.45, 16.2, "+2V5")
T("+1V2", [("U602", "5"), (1.25, 21.15)], WP)
T("+1V2", [(1.25, 21.15), ("C608", "1")], WP)
T("+1V2", [(1.25, 21.15), (1.25, 21.95)], WP); blk.via(1.25, 21.95, "+1V2")
blk.iface("+5V", 0.45, 12.6, "In3.Cu", "W", "supply", None, "via at C616 (+ B bulk C617); L4 tongue W to the input stage")
blk.iface("+2V5", 0.45, 16.2, "In3.Cu", "W", "supply", None, "via at C624 (+ B bulk C625)")
blk.iface("+1V2", 1.25, 21.95, "In3.Cu", "W", "supply", None, "via at C608 (+ B bulk C609)")
Z("+3V3", "F.Cu", [(4.55, 18.7), (7.0, 18.7), (7.0, 21.9), (4.55, 21.9)], prio=3)
blk.via(6.6, 19.0, "+3V3")
T("GND", [("C607", "2"), (6.25, 21.6), (5.75, 22.1), (5.6, 22.1)], WS); G(5.6, 22.1)
# B bulk caps of the outputs: via in the outer pad (plane-fed)
for c, n in (("C617", "+5V"), ("C625", "+2V5"), ("C609", "+1V2")):
    x, y = blk.pad(c, "1")
    xv = 0.95 if c == "C617" else 7.5
    if c != "C617":
        T(n, [(x, y), (xv, y)], 0.5, "B.Cu")
    blk.via(xv, y, n)
# --- LM337 (B): tab = pin 2 (-5V) joined, ADJ divider, -2V5 out
T("-5V", [("U607", "2"), (1.85, 14.4)], 0.6, "B.Cu")
blk.via(2.0, 14.5, "-5V"); blk.via(2.9, 14.5, "-5V")
T("-5V", [("U607", "2"), ("C621", "1")], 0.5, "B.Cu")
T("/power/ADJ_N25", [("U607", "1"), ("C626", "1")], WS, "B.Cu")
T("/power/ADJ_N25", [("R608", "1"), ("C626", "1")], WS, "B.Cu")
T("/power/ADJ_N25", [("R607", "2"), (12.9, 16.7), (12.9, 11.45), (12.6, 11.15), (10.2, 11.15)], WS, "B.Cu")
T("-2V5", [("U607", "3"), ("R607", "1")], 0.5, "B.Cu")
T("-2V5", [("R607", "1"), (10.22, 18.7)], 0.5, "B.Cu")
T("-2V5", [(10.22, 18.7), ("C629", "1")], 0.5, "B.Cu")
V(9.75, 18.0, "-2V5"); V(9.75, 19.0, "-2V5")
T("-2V5", [(9.75, 18.0), (9.75, 19.0)], 0.5, "B.Cu")
T("-2V5", [(9.75, 18.5), (10.22, 18.5)], 0.5, "B.Cu")
blk.iface("-2V5", 9.75, 18.5, "In3.Cu", "S", "supply", None, "via pair at C628 / R607 (B)")
T("GND", [("R608", "2"), (10.2, 9.4)], WS, "B.Cu")
T("GND", [("C602", "2"), (9.3, 8.7)], WS, "B.Cu")
T("VBUS", [(15.1, 13.5), (13.6, 13.5)], 0.4, "B.Cu")
# --- grounds: F / B pours, In1 plane of the block (the integrator's board plane replaces it)
for l_ in ("F.Cu", "B.Cu"):
    Z("GND", l_, R(0, 0, BW, BH), prio=0).SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
Z("GND", "In1.Cu", R(0, 0, BW, BH), prio=0)
blk.keepout([(HOLE[0] + 3.5 * math.cos(a_ * math.pi / 8), HOLE[1] + 3.5 * math.sin(a_ * math.pi / 8)) for a_ in range(16)],
            ("F.Cu", "In1.Cu", "B.Cu"), tracks=True, vias=True)
blk.edge_rect(0, 0, BW, BH, "Dwgs.User")
out = blk.save(HERE)


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
            x_ = pcbnew.SHAPE_POLY_SET(pa)
            x_.BooleanIntersection(pb_, pcbnew.SHAPE_POLY_SET.PM_FAST)
            ar = x_.Area() / 1e12
            if ar > min_area:
                hits.append((ra, rb, round(ar, 3)))
    nocy = [f_.GetReference() for f_ in fps if not any(c[0] == f_.GetReference() for c in cy)]
    # outside the block rectangle / inside the hole keep-out
    outside = []
    for f_ in fps:
        for lay in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            p_ = f_.GetCourtyard(lay)
            if p_.OutlineCount():
                bb = p_.BBox()
                x0, y0 = pcbnew.ToMM(bb.GetX()) - 100, pcbnew.ToMM(bb.GetY()) - 100
                x1, y1 = pcbnew.ToMM(bb.GetRight()) - 100, pcbnew.ToMM(bb.GetBottom()) - 100
                if x0 < -0.01 or y0 < -0.01 or x1 > BW + 0.01 or y1 > BH + 0.01:
                    outside.append((f_.GetReference(), round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)))
    print(f"courtyard overlaps (> {min_area} mm2): {len(hits)}  {hits[:40]}   (no courtyard: {nocy}); outside: {outside}")
    return hits


for nm_ in blk.routes:
    if blk.routes[nm_]["net"] in (DP, DM):
        print(f"{nm_:12s} {blk.route_len(nm_):6.2f} mm")
print("USB pair: w %.2f s %.2f -> Z0 %.1f R, Zdiff %.1f R (IPC-2141)" % ((W_USB, S_USB) + diff90(W_USB, S_USB)))
import floorplan as fpl
REFS = sorted(r_ for r_, b_ in fpl.membership(nl).items() if b_ == "power")
RF = {DP: W_USB, DM: W_USB}
res = bl.check_board(out, refs=REFS, rf_widths=RF, verbose=40)
for k_ in ('unrouted', 'corner'):
    print(k_, res['details'][k_] if 'details' in res else '')
CY_HITS = courtyard_overlaps(out)
_bb = pcbnew.LoadBoard(out).ComputeBoundingBox(False)
_ox, _oy = pcbnew.ToMM(_bb.GetX()), pcbnew.ToMM(_bb.GetY())


def render(png, layers, crop):
    """local helper: kicad-cli page-size-mode 2 puts the SVG origin at the board bbox; shift the crop (local mm)"""
    x0, y0, x1, y1 = crop
    o = (100.0 - _ox, 100.0 - _oy)
    bl.render(out, png, layers, crop=(x0 + o[0], y0 + o[1], x1 + o[0], y1 + o[1]), tmpdir=SCR)


if "--norender" not in sys.argv:
    full = (-0.5, -0.5, BW + 0.5, BH + 0.5)
    lay = ("F.Cu", "B.Cu", "F.SilkS", "F.Fab", "Dwgs.User")
    render(os.path.join(HERE, "power.png"), lay, full)
    render(os.path.join(HERE, "power_detail.png"), lay, (9.5, 9.5, 19.5, 17.5))
    render(os.path.join(SCR, "power_f.png"), ("F.Cu", "F.Fab", "F.CrtYd", "Dwgs.User"), full)
    render(os.path.join(SCR, "power_b.png"), ("B.Cu", "B.Fab", "B.CrtYd", "Dwgs.User"), full)
