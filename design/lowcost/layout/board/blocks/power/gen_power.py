#!/usr/bin/env python3
"""POWER block of the scope-fe board (power sheet, refs 6xx): USB-C J601 (+ USBLC6 U608 on USB_DP / USB_DM),
PTC F601, TVS D601, FB601 -> VBUS; AMS1117 U601 (+3V3, B side) -> AP2112 U602 (+1V2); MT3608 boost U603
(L601, D602, C610 / C611: hot loop SW -> D602 -> C610 -> GND -> U603.2 within 4 x 3 mm) -> FB602 -> +5V4F;
LP2985 U604 (+5V), LP5907 U606 (+2V5), LM27761 U605 (-5V_LDO -> FB603 -> -5V), LM337 U607 (-2V5, B side).
Local mm, origin = block top-left = board (74, 0); +x east (J601 on the board's right edge at local x 26).
Run: cd blocks/power && python3 gen_power.py [--norender]
"""
import sys, os, math
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
W_USB, S_USB = 0.25, 0.15                # 90 R edge-coupled pair (IPC-2141: 91 R), see diff90()
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
two("R603", 6.38, 8.7, "E", "/power/FB_BOOST")
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
    ("C604", 11.3, 1.4, "W", "+3V3"), ("C605", 11.3, 3.4, "W", "+3V3"), ("C606", 13.6, 9.45, "W", "+3V3"),
    ("C601", 11.3, 7.9, "W", "VBUS"), ("C602", 12.6, 10.4, "W", "VBUS"),
    ("C612", 4.3, 9.5, "E", "/power/+5V4F"), ("C623", 14.5, 1.5, "E", "/power/+5V4F"),
    ("C621", 11.6, 12.5, "E", "-5V"), ("C622", 15.0, 6.2, "E", "-5V"), ("C627", 15.0, 8.0, "E", "-5V"),
    ("C626", 11.6, 14.6, "W", "/power/ADJ_N25"), ("R607", 10.9, 16.6, "W", "-2V5"),
    ("R608", 12.9, 16.6, "W", "/power/ADJ_N25"),
    ("C628", 11.6, 18.6, "W", "-2V5"), ("C629", 10.9, 20.4, "W", "-2V5"),
    ("C617", 1.8, 19.0, "W", "+5V"), ("C625", 1.8, 21.0, "W", "+2V5"), ("C609", 5.4, 19.0, "W", "+1V2"),
    ("R602", 15.0, 11.1, "E", "/power/CC2"), ("R601", 15.0, 15.9, "E", "/power/CC1"),
]
for ref, x, y, f, n in B_PARTS:
    two(ref, x, y, f, n, "B")

# ============================================================================= checks of placement
placed = set(blk.fps)
mine = sorted(r for r, c in nl.comps.items() if c["sheet"].startswith("/power"))
print("not placed:", sorted(set(mine) - placed))
exec(open(os.path.join(HERE, "route_power.py")).read()) if False else None
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
    render(os.path.join(SCR, "power_f.png"), ("F.Cu", "F.Fab", "F.CrtYd", "Dwgs.User"), full)
    render(os.path.join(SCR, "power_b.png"), ("B.Cu", "B.Fab", "B.CrtYd", "Dwgs.User"), full)
