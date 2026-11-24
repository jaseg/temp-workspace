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
def buck(u, cin, cin_hf, lx, cout, cout_hf, rtop, rbot, cff, cx, cy, side, vin, vout, sw):
    """chip rot 180: VIN / SW / GND (pins 3 / 2 / 1) face +sx, EN / FB / PG face -sx.  CIN (0805) straddles pins 3 / 1
    beside the chip with SW leaving between its pads (0.9 mm gap) to the inductor; COUT returns to the CIN ground.
    sx = +1 on F; on B the cell is the mirror image (sx = -1)."""
    sx = 1 if side == "F" else -1
    X = lambda dx: cx + sx * dx
    E, W = ("E", "W") if sx > 0 else ("W", "E")
    bplace(u, cx, cy, 180, side)
    two(cin, X(2.35), cy, "N", vin, side)
    two(lx, X(4.7), cy + 1.075, "N", sw, side)
    two(cout, X(4.2), cy + 4.1, E, vout, side)
    two(rtop, X(-1.85), cy - 0.55, "N", vout, side)
    two(rbot, X(-1.85), cy + 1.33, "S", "GND", side)
    if cff:
        two(cff, X(-2.8), cy - 0.55, "N", vout, side)
    if cout_hf:
        two(cout_hf, X(1.45), cy + 4.1, E, vout, side)
    if cin_hf:
        two(cin_hf, X(0.95), cy - 2.25, E, vin, side)
    return X


XB1 = buck("U601", "C603", "C602", "L602", "C604", None, "R609", "R610", "C631", 3.4, 3.0, "F",
           "VBUS", "+3V3", "Net-(U601-SW)")
XB2 = buck("U602", "C609", "C607", "L603", "C605", "C608", "R611", "R612", None, 6.15, 3.0, "B",
           "+3V3", "+1V2", "Net-(U602-SW)")

# ============================================================================= U603 TPS63802 buck-boost (F, top-middle)
bplace("U603", 10.95, 4.9, 0)            # W: EN MODE AGND FB PG (1-5); E: VIN L1 GND L2 VOUT (10, 9, 8, 7, 6)
two("C601", 13.45, 1.75, "S", "VBUS")    # CIN at VIN (10) / GND, IC layer
two("L601", 16.95, 4.9, "N", "Net-(U603-L1)")
two("C610", 13.45, 8.05, "N", "/+5V1")   # COUT at VOUT (6) / GND
two("C611", 11.45, 8.45, "N", "/+5V1")
two("R603", 10.0, 7.65, "N", "/+5V1")    # FB divider south of the chip, away from L1 / L2
two("R604", 10.0, 9.53, "S", "GND")
two("C632", 11.8, 1.7, "W", "VBUS", "B")  # DNP VBUS damper (tantalum) under the converters' input


# ============================================================================= LM27762 cell (WSON-12, F)
def lm(u, cin, cin_hf, ccp, c1, rp_top, rp_bot, rn_top, rn_bot, cx, cy, ccp_0603):
    """rot 0: W column PGOOD FB+ VIN GND CP OUT- (1-6), E column EN+ OUT+ C1+ C1- EN- FB- (12-7).
    CIN at pins 3 / 4 (W), CCP south-west, C1 at pins 10 / 9 (E), FB+ divider north, FB- divider south."""
    bplace(u, cx, cy, 0)
    if cin_hf:
        two(cin_hf, cx - 2.1, cy, "N", nl.net_of(u, "3"))
        two(cin, cx - 3.55, cy, "N", nl.net_of(u, "3"))
    else:
        two(cin, cx - 2.45, cy, "N", nl.net_of(u, "3"))
    if ccp_0603:
        two(ccp, cx - 2.42, cy + 2.75, "E", nl.net_of(u, "5"))
    else:
        two(ccp, cx - 2.65, cy + 3.0, "E", nl.net_of(u, "5"))
    if c1.startswith("C618"):
        two(c1, cx + 2.2, cy, "N", nl.net_of(u, "10"))
    else:
        two(c1, cx + 1.93, cy, "N", nl.net_of(u, "10"))
    two(rp_top, cx, cy - 2.4, "W", nl.net_of(u, "2"))      # FB+ <-> OUT+
    two(rp_bot, cx - 1.88, cy - 2.4, "E", nl.net_of(u, "2"))   # GND <-> FB+
    two(rn_top, cx, cy + 2.5, "E", nl.net_of(u, "7"))      # OUT- <-> FB-
    two(rn_bot, cx + 1.88, cy + 2.5, "W", nl.net_of(u, "7"))   # FB- <-> GND


lm("U604", "C612", "C613", "C626", "C618", "R613", "R614", "R605", "R606", 4.8, 11.0, False)
lm("U605", "C625", None, "C619", "C624", "R615", "R616", "R607", "R608", 4.8, 17.85, True)

# ============================================================================= B side: beads, LDO output capacitors
PLACE_B = [  # ref, x, y, first-side, net
]
for ref, x, y, f, n in PLACE_B:
    two(ref, x, y, f, n, "B")

placed = set(blk.fps)
mine = sorted(r for r, c in nl.comps.items() if c["sheet"].startswith("/power") and r not in MOVED)
print("not placed:", sorted(set(mine) - placed))
print(bl.courtyard_overlaps(blk.b))
blk.edge_rect(0, 0, BW, BH, "Dwgs.User")
blk.circle(HOLE[0], HOLE[1], 3.5, "Dwgs.User", 0.05)
out = blk.save(SCR)
_bb = pcbnew.LoadBoard(out).ComputeBoundingBox(False)
_ox, _oy = pcbnew.ToMM(_bb.GetX()), pcbnew.ToMM(_bb.GetY())


def render(png, layers, crop):
    """kicad-cli page-size-mode 2 puts the SVG origin at the board bbox; shift the crop (local mm)"""
    x0, y0, x1, y1 = crop
    o = (100.0 - _ox, 100.0 - _oy)
    bl.render(out, png, layers, crop=(x0 + o[0], y0 + o[1], x1 + o[0], y1 + o[1]), tmpdir=SCR)


full = (-0.5, -0.5, BW + 0.5, BH + 0.5)
render(os.path.join(SCR, "p_f.png"), ("F.Cu", "F.Fab", "F.CrtYd", "Dwgs.User"), full)
render(os.path.join(SCR, "p_b.png"), ("B.Cu", "B.Fab", "B.CrtYd", "Dwgs.User"), full)
