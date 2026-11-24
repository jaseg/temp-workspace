"""FPGA block, six layers (JLC06161H-3313, RULES rule 10): GW1NZ-LV1 QN48 (U501), MS5351M (U502) + Y501,
configuration / decoupling.   Run: cd blocks/fpga && python3 gen_fpga.py [--render]
Block-local mm, origin = board (56, 0.5), 18 x 22 mm.  L1 F.Cu parts + strobes, L2 In1 GND, L3 In2 GND pour (nothing
fast), L4 In3 +3V3 with a +1V2 island, L5 In4 GND, L6 B.Cu fan-out over L5.
Every escape to the block edges is drawn here with explicit coordinates (TOPOLOGY.md section 1): planar per layer.
  - west bundle (L6): COARSE + TAP0..4 from the top pins (via stair north of the pads, runs west, down the west margin),
    TAP5 / TAP6 from the west pins 41 / 47; fans to the S edge slots 2.0 .. 5.5.
  - TAP7 (pin 6) and DBG2 (pin 8): L1 south, west over the JTAG L6 lanes, via, L6 to the edge.
  - JTAG (pins 3 4 5 7): via at the pins, L6 straight south.
  - MCU_CLK, SPI_CS, I2C_SDA, SPI_MOSI, SPI_MISO, SPI_SCK, I2C_SCL, ADC_TRIG: L6 lanes under the package (entering
    from the east: vias at the east pins, the I2C / MCU_CLK lines from U502 down the NE corner), out under the bottom
    pads, fanned to their slots.
  - FPGA_DONE / FPGA_RECONFIG (west pins 46 / 48): L1 down the west side, east over the bundle, via at their slots.
  - TAP8..15 (pins 9-11, 13-17): L1 south / east, via near the edge, L6 stub.
Only the local support connections (crystal, caps, pull resistors, ties) use the small grid router."""
import sys, os, math, json, heapq
os.environ["BL_STACKUP"] = "6L"
sys.path.insert(0, "../..")
import numpy as np
from scipy import ndimage
import pcbnew
import boardlib as bl

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board"
W, H = 18.0, 22.0
W50 = bl.W50                         # 0.16 mm = 50 R on L1 / L6 (6L)
WS = 0.12                            # digital fan-out
blk = bl.Block("fpga")
NL = blk.nl
MOVED = ("J501", "R511", "R512")
REFS = sorted(r for r, c in NL.comps.items() if c["sheet"] == "/fpga_clock/" and r not in MOVED)
C = NL.canon


def bplace(ref, x, y, rot=0, side="F"):
    fp = blk.place(ref, x, y, rot, "F")
    if side == "B":
        fp.Flip(blk.P(x, y), True)
        fp.Reference().SetLayer(pcbnew.B_Fab)
    return fp


def up(p):
    return blk.pad("U501", str(p))


def T(net, w, pts, layer="F.Cu", ch=0.15, name=None):
    return blk.track(net, w, pts, layer, ch=ch, name=name)


def V(x, y, net):
    blk.via(x, y, net)


# ---------------- placement
CX, CY = 8.6, 11.165                 # pin 38 (S_STROBE_P) at y 9.365; its W exit jogs 1.0 mm south to the analog E row (y 10.365 local)
U502X, U502Y = 11.1, 2.2
bplace("U501", CX, CY, 90)
bplace("U502", U502X, U502Y, 180)    # left: 6 CLK2, 7 VDD, 8 GND, 9 CLK1, 10 CLK0 (top->bottom); right: 5 SDA, 4 SCL, 3 XB, 2 XA, 1 VDD
bplace("Y501", 16.3, 5.55, 90)
bplace("R510", 7.2, 5.0, 270)         # CLK2 -> CLK2_FPGA (pin 34), straight above pin 34 (24 Nov: C508 took its spot)
bplace("R508", 8.5, 5.0, 270)         # CLK0 -> FPGA_CLK (pin 33); CLK0 drops straight from pin 10 (24 Nov)
bplace("R509", 11.3, 3.0, 180, "B")   # CLK1 -> MCU_CLK, on B under U502 (CLK1 via under the body, 24 Nov)
# +3V3_CLK (24 Nov, DECOUPLING-5 / power-tree.md): FB608 from +3V3, C510 10u + C623 1u after it; C508 on TOP at pin 7
# (VDDO) and C509 at pin 1 (VDD), each GND pad with its own via right beside it
bplace("C508", 7.45, 2.18, 270)       # U502.7 VDDO, F, pad 1 on the pin-7 row, GND via (7.45, 3.45)
bplace("C509", 13.3, 5.0, 270)        # U502.1 VDD, F, straight below pin 1, GND via (13.3, 6.2)
bplace("C623", 12.3, 5.0, 270)        # 1u +3V3_CLK beside C509, GND via (12.3, 6.2)
bplace("C507", 16.0, 9.2, 0, "B")     # 10u +3V3 (moved to B under C510, 24 Nov: FB608 takes its F spot)
bplace("C510", 16.0, 8.75, 0)         # 10u +3V3_CLK
bplace("FB608", 15.8375, 10.6, 180)   # +3V3 (pad 1, via to L4) -> +3V3_CLK (pad 2, straight up to C510.1)
bplace("C506", 4.05, 7.45, 180)      # pin 36 +3V3 (VCCX); 24 Nov 0.2 mm north: GND via between the GND pads
bplace("C502", 4.05, 8.65, 180)      # pin 37 +1V2
bplace("C505", 12.3, 6.9, 0)         # pin 25 +3V3
bplace("C504", 6.4, 15.7, 270)       # pin 1 +3V3
bplace("C501", 11.9, 15.25, 0)       # pin 12 +1V2
bplace("C503", 14.6, 14.6, 90, "B")  # 10u +1V2 (B, SE)
bplace("R501", 3.3, 14.3, 180)       # RECONFIG pull-up (F, SW pocket)
bplace("R507", 5.6, 15.6, 0, "B")    # TCK pull-down (B, SW of the package)
# configuration pull resistors + JP501 on F in the free NW corner; the pins reach them on L3 (slow static lines)
bplace("JP501", 4.6, 1.3, 0)
for ref, x, y in (("R502", 1.2, 0.75), ("R503", 1.2, 1.75), ("R504", 1.2, 2.75), ("R505", 3.3, 3.05), ("R506", 5.4, 3.05)):
    bplace(ref, x, y, 0)

# ---------------- edge slots (S edge, L6), TOPOLOGY.md section 1, west to east, 0.5 mm pitch
ORDER = (["/COARSE"] + [f"/TAP{i}" for i in range(8)] +
         [C(n) for n in ("DBG2", "JTAG_TCK", "JTAG_TMS", "JTAG_TDI", "JTAG_TDO", "MCU_CLK", "SPI_CS", "I2C_SDA",
                         "FPGA_DONE", "SPI_MOSI", "SPI_MISO", "SPI_SCK", "I2C_SCL", "FPGA_RECONFIG", "ADC_TRIG")] +
         [f"/TAP{i}" for i in range(15, 7, -1)])          # east group reversed (TAP8 eastmost), 22 Nov
SLOT = {n: round(2.0 + 0.5 * k, 3) for k, n in enumerate(ORDER)}
YE = 21.2                                            # via row of the L1-routed nets near the edge (staggered)


def ye(net):
    return 20.35 if ORDER.index(net) % 2 == 0 else 21.45      # ZONES-3 (24 Nov): 1.21 mm diagonal pitch
NOTE = {}


def edge(net, note, w=WS):
    blk.iface(net, SLOT[net], H, "B.Cu", "S", "slow", w, note)


RF = {}
# ---------------- strobes (L1, 0.16 mm)
p38 = up(38)
YSP = p38[1] + 1.0                  # analog E interface row (board 10.865): one 45-degree jog in the W margin, no vias
T("/S_STROBE_P", W50, [p38, (2.9, p38[1]), (1.9, YSP), (0.0, YSP)], ch=0.0001, name="S_P")
RF["/S_STROBE_P"] = W50
blk.iface("/S_STROBE_P", 0.0, YSP, "F.Cu", "W", "pair", W50, "U501.38; one straight F.Cu line, no vias; R401 in analog")
# S_STROBE_N (termination only): pin 35 north, west over the L6 bundle at y 6.9, via at the W edge, L6 down under S_P,
# via, 0.4 mm F stub to the analog iface
p35 = up(35)
YSN = 11.365                         # analog N row (board 11.865)
T("/S_STROBE_N", W50, [p35, (p35[0], 6.9), (6.5, 6.6), (0.4, 6.6)], ch=0.0001, name="S_N")
T("/S_STROBE_N", W50, [(0.4, 6.6), (0.4, YSN)], "B.Cu", name="S_N")
T("/S_STROBE_N", W50, [(0.4, YSN), (0.0, YSN)], name="S_N")
V(0.4, 6.6, "/S_STROBE_N")
V(0.4, YSN, "/S_STROBE_N")
V(0.4, 5.95, "GND")                  # ZONES-4: ground via 0.65 mm from each S_STROBE_N layer change
V(0.4, YSN + 0.635, "GND")
RF["/S_STROBE_N"] = W50
blk.iface("/S_STROBE_N", 0.0, YSN, "F.Cu", "W", "pair", W50, "U501.35; F - via - B - via - F, terminated only; R405 in analog")
# PH_STROBE pair: west, down the west margin (N outer x 0.9, P inner x 1.26), out west at the S end of the W edge
p39, p40 = up(39), up(40)
YPN = 21.35


def ph_pts(p, xd, yo):
    return [p, (xd + 0.4, p[1]), (xd, p[1] + 0.4), (xd, yo - 0.4), (xd - 0.4, yo), (0.0, yo)]


def ph_pts(p, xd, yo, yh=None):
    yh = p[1] if yh is None else yh
    head = [p, (5.15, p[1]), (5.15 - (p[1] - yh), yh)] if yh != p[1] else [p]
    return head + [(xd + 0.4, yh), (xd, yh + 0.4), (xd, yo - 0.4), (xd - 0.4, yo), (0.0, yo)]


def ph2(p, yh, x0, ydn, xd, yo):
    """pin -> west at yh -> 45 deg down to ydn from x0 (below the S_STROBE_P exit) -> west -> down the margin at xd"""
    head = [p] if abs(yh - p[1]) < 1e-6 else [p, (5.15, p[1]), (5.15 - (p[1] - yh), yh)]
    return head + [(x0, yh), (x0 - (ydn - yh), ydn), (xd + 0.4, ydn), (xd, ydn + 0.4), (xd, yo - 0.4), (xd - 0.4, yo),
                   (0.0, yo)]


PHP = ph2(p39, p39[1], 3.4, p39[1] + 1.0, 0.9, YPN)      # pin 39 = PH_STROBE_P (swapped 22 Nov), outer
LP = bl.plen(PHP)
lo, hi = YPN + 0.2, YPN + 0.6                      # PH_N exit y solved for equal length
for _ in range(60):
    mid = (lo + hi) / 2
    lo, hi = (mid, hi) if bl.plen(ph2(p40, 10.12, 3.6, 10.12 + 1.005, 1.26, mid)) < LP else (lo, mid)
YPP = round(mid, 4)
T("/PH_STROBE_P", W50, PHP, ch=0.0001, name="PH_P")
T("/PH_STROBE_N", W50, ph2(p40, 10.12, 3.6, 10.12 + 1.005, 1.26, YPP), ch=0.0001, name="PH_N")
RF["/PH_STROBE_N"] = RF["/PH_STROBE_P"] = W50
blk.iface("/PH_STROBE_P", 0.0, YPN, "F.Cu", "W", "pair", W50, "U501.39; pair with N, equal length; 47 R R407 in pstrobe")
blk.iface("/PH_STROBE_N", 0.0, YPP, "F.Cu", "W", "pair", W50, "U501.40; pair with P, equal length; 47 R R411 in pstrobe")

# ---------------- west bundle: COARSE + TAP0..4 from the top pins (L1 stub north, via stair, L6 west and south)
TOPP = [(27, "/COARSE"), (28, "/TAP0"), (29, "/TAP1"), (30, "/TAP2"), (31, "/TAP3"), (32, "/TAP4")]
DX = {"/COARSE": 0.9, "/TAP0": 1.25, "/TAP1": 1.6, "/TAP2": 1.95, "/TAP3": 2.3, "/TAP4": 2.65, "/TAP5": 3.2, "/TAP6": 3.75}
YF = 18.9                                           # bundle fan to the edge slots starts here


def fan(net, x, y_from, layer="B.Cu"):
    """vertical at x down to YF, 45 degrees to the slot, down to the edge (L6)"""
    s = SLOT[net]
    pts = [(x, y_from), (x, YF), (s, YF + abs(s - x)), (s, H)]
    return pts


for k, (pin, net) in enumerate(TOPP):
    p = up(pin)
    yv = round(5.25 + 0.4 * k, 3)                   # COARSE northmost (outermost)
    T(net, WS, [p, (p[0], yv)])
    V(p[0], yv, net)
    x = DX[net]
    T(net, WS, [(p[0], yv), (x + 0.0, yv)] + fan(net, x, yv)[1:], "B.Cu", ch=0.3)
    edge(net, f"U501.{pin}; west bundle on L6")
# TAP5 (pin 41) / TAP6 (pin 47): via west of the pin, L6 down inside the bundle
p41, p47 = up(41), up(47)
# REPAIR (24 Nov, recheck RF2-5): TAP5 via 0.15 mm east and 0.4 mm, so its L2 / L5 antipad stays clear of the
# board PH_STROBE_N run (centre 0.46 mm away, was 0.42; antipad 0.35 < 0.38 to the strobe edge: L2 solid under it)
YT5 = p41[1] + 0.02
T("/TAP5", WS, [p41, (3.92, p41[1]), (3.9, YT5)])
blk.via(3.9, YT5, "/TAP5", 0.4, 0.2)
T("/TAP5", WS, [(3.9, YT5), (DX["/TAP5"], YT5)] + fan("/TAP5", DX["/TAP5"], YT5)[1:], "B.Cu", ch=0.3)
edge("/TAP5", "U501.41; west bundle on L6")
T("/TAP6", WS, [p47, (3.75, p47[1])])
V(3.75, p47[1], "/TAP6")
T("/TAP6", WS, fan("/TAP6", 3.75, p47[1]), "B.Cu", ch=0.3)
edge("/TAP6", "U501.47; west bundle on L6")

# ---------------- west column: configuration pins to vias (pull resistors on B under the package)
COLV = {}
for pin, xv in ((42, 4.3), (43, 4.85), (44, 4.3), (45, 4.85), (46, 4.3)):
    net = NL.net_of("U501", str(pin))
    p = up(pin)
    T(net, WS, [p, (xv, p[1])])
    V(xv, p[1], net)
    COLV[pin] = (xv, p[1])
# L3 (In2) slow lines: column vias west, north at x 2.95 .. 1.15 to staggered vias below the NW resistors
L3X = {42: 2.95, 43: 2.5, 44: 2.05, 45: 1.6, 46: 1.15}
L3V = {}
for pin, xl in L3X.items():
    net = NL.net_of("U501", str(pin))
    xv, yv = COLV[pin]
    yt = 4.4 if pin % 2 == 0 else 3.8
    T(net, WS, [(xv, yv), (xl, yv), (xl, yt)], "In2.Cu", ch=0.3)
    V(xl, yt, net)
    L3V[pin] = (xl, yt)

# ---------------- DONE / RECONFIG: L1 west, down the west side (DONE outer x 2.0, RECONFIG x 2.4), east to their slots
p46, p48 = up(46), up(48)
YD, YR = 18.5, 18.1
T("/FPGA_DONE", WS, [p46, (2.0, p46[1]), (2.0, YD), (SLOT["/FPGA_DONE"], YD)], ch=0.3)
T("/FPGA_RECONFIG", WS, [p48, (2.4, p48[1]), (2.4, YR), (SLOT["/FPGA_RECONFIG"], YR)], ch=0.3)
for net, y in (("/FPGA_DONE", YD), ("/FPGA_RECONFIG", YR)):
    V(SLOT[net], y, net)
    T(net, WS, [(SLOT[net], y), (SLOT[net], H)], "B.Cu")
edge("/FPGA_DONE", "U501.46 (DONE); F.Cu west / south / east, via; pull-up R502")
edge("/FPGA_RECONFIG", "U501.48 (RECONFIG_N); F.Cu west / south / east, via; pull-up R501")

# ---------------- JTAG (pins 3 4 5 7): vias at the pins, L6 straight south
JV = {3: (7.2, 15.0), 4: (7.6, 15.6), 5: (8.0, 15.0), 7: (8.8, 15.0)}
for pin, v in JV.items():
    net = NL.net_of("U501", str(pin))
    T(net, WS, [up(pin), v])
    V(*v, net)
    s = SLOT[net]
    T(net, WS, [v, (v[0], 15.75), (s, 15.75 + abs(s - v[0])), (s, H)], "B.Cu", ch=0.1)
    edge(net, f"U501.{pin}; to J501 in mcuif")
# TAP7 (pin 6) and DBG2 (pin 8): L1 south, west over the JTAG lanes, via, L6 to the edge
for pin, net, yr in ((6, "/TAP7", 17.2), (8, C("DBG2"), 17.6)):
    p = up(pin)
    s = SLOT[net]
    T(net, WS, [p, (p[0], yr), (s, yr)], ch=0.3)
    V(s, yr, net)
    T(net, WS, [(s, yr), (s, H)], "B.Cu")
    edge(net, f"U501.{pin}")

# ---------------- TAP8..10 (bottom pins 9..11) and TAP11..15 (east pins 13..17): L1, via at YE, L6 stub
for pin, net, yr in ((9, "/TAP15", 16.9), (10, "/TAP14", 16.6), (11, "/TAP13", 16.3)):
    p = up(pin)
    s = SLOT[net]
    T(net, WS, [p, (p[0], yr), (s, yr), (s, ye(net))], ch=0.3)
    V(s, ye(net), net)
    T(net, WS, [(s, ye(net)), (s, H)], "B.Cu")
    edge(net, f"U501.{pin}")
for pin, net in ((13, "/TAP12"), (14, "/TAP11"), (15, "/TAP10"), (16, "/TAP9"), (17, "/TAP8")):
    p = up(pin)
    s = SLOT[net]
    T(net, WS, [p, (s, p[1]), (s, ye(net))], ch=0.3)
    V(s, ye(net), net)
    T(net, WS, [(s, ye(net)), (s, H)], "B.Cu")
    edge(net, f"U501.{pin}")

# ---------------- M group: L6 lanes under the package, entering from the east
EV = {24: ("/SPI_CS", 12.2), 22: ("/SPI_MOSI", 13.15), 21: ("/SPI_MISO", 12.2), 20: ("/SPI_SCK", 13.15),
      18: ("/ADC_TRIG", 12.2)}            # ZONES-3 (24 Nov): two staggered columns, >= 1.03 mm between neighbours
LANE = {"/MCU_CLK": 9.3, "/SPI_CS": 9.62, "/I2C_SDA": 9.94, "/SPI_MOSI": 10.26, "/SPI_MISO": 10.58, "/SPI_SCK": 10.9,
        "/I2C_SCL": 11.22, "/ADC_TRIG": 11.54}
LANE = {C(k): v for k, v in LANE.items()}
YL = 16.0                                            # lanes fan to their slots below this


def lane_tail(net):
    x, s = LANE[net], SLOT[net]
    return [(x, YL), (s, YL + abs(s - x)), (s, H)]


for pin, (net, xv) in EV.items():
    net = C(net)
    p = up(pin)
    T(net, WS, [p, (xv, p[1])])
    V(xv, p[1], net)
    T(net, WS, [(xv, p[1]), (LANE[net], p[1])] + lane_tail(net), "B.Cu", ch=0.25)
    edge(net, f"U501.{pin}; L6 lane under the package")
# I2C from U502 (right pins 5 SDA / 4 SCL): F east to vias, L6 down the NE corner (SDA x 13.6, SCL x 14.0), west in
sda, scl = blk.pad("U502", "5"), blk.pad("U502", "4")
VSDA, VSCL = (14.4, sda[1]), (14.95, scl[1])
T("/I2C_SDA", WS, [sda, VSDA])
T("/I2C_SCL", WS, [scl, VSCL])
V(*VSDA, "/I2C_SDA")
V(*VSCL, "/I2C_SCL")
T("/I2C_SDA", WS, [VSDA, (13.75, VSDA[1] + 0.65), (13.75, up(23)[1]), (LANE[C("I2C_SDA")], up(23)[1])] + lane_tail(C("I2C_SDA")),
  "B.Cu", ch=0.25)
T("/I2C_SCL", WS, [VSCL, (14.0, VSCL[1] + 0.95), (14.0, up(19)[1]), (LANE[C("I2C_SCL")], up(19)[1])] + lane_tail(C("I2C_SCL")),
  "B.Cu", ch=0.25)
edge(C("I2C_SDA"), "MS5351M SDA; L6 down the NE corner, lane under U501")
edge(C("I2C_SCL"), "MS5351M SCL; L6 down the NE corner, lane under U501")

# MCU_CLK: U502.9 CLK1 -> F west -> via -> R509 (B) -> L6 east under U502 -> down x 13.2 -> lane (westmost)
ck1 = blk.pad("U502", "9")
VCK1 = (9.85, ck1[1])                                  # under the U502 body (24 Nov)
T("Net-(U502-CLK1)", WS, [ck1, VCK1])
V(*VCK1, "Net-(U502-CLK1)")
r9a, r9b = blk.pad("R509", "@Net-(U502-CLK1)"), blk.pad("R509", "@MCU_CLK")
T("Net-(U502-CLK1)", WS, [VCK1, (VCK1[0] + (r9a[1] - VCK1[1]), r9a[1]), r9a], "B.Cu", ch=0.0001)
YMC = up(25)[1] + 0.335                              # 8.55: entry row under the top-right pads
T("/MCU_CLK", WS, [r9b, (r9b[0], YMC - 0.45), (r9b[0] - 0.45, YMC),
                   (LANE[C("MCU_CLK")], YMC)] + lane_tail(C("MCU_CLK")), "B.Cu", ch=0.25)
edge(C("MCU_CLK"), "MS5351M CLK1 via R509 33 R; L6 under U502 / U501 -> STM32 PF0")
# FPGA_CLK: CLK0 (U502.10) -> R508 -> pin 33; CLK2 (U502.6) -> R510 -> pin 34 (both F.Cu, short, over L2)
ck0, ck2 = blk.pad("U502", "10"), blk.pad("U502", "6")
r8a, r8b = blk.pad("R508", "@Net-(U502-CLK0)"), blk.pad("R508", "@FPGA_CLK")
T("Net-(U502-CLK0)", WS, [ck0, (8.05, ck0[1]), (8.05, 3.7), (r8a[0], 3.7 + r8a[0] - 8.05), r8a], ch=0.0001)
p33 = up(33)
T("/fpga_clock/FPGA_CLK", WS, [r8b, (r8b[0], 5.85), (p33[0], 5.85 + abs(r8b[0] - p33[0])), p33], ch=0.0001)
r10a, r10b = blk.pad("R510", "@Net-(U502-CLK2)"), blk.pad("R510", "@CLK2_FPGA")
T("Net-(U502-CLK2)", WS, [ck2, (6.85, ck2[1]), (6.85, 3.85), (r10a[0], 3.85 + r10a[0] - 6.85), r10a], ch=0.0001)
T("/fpga_clock/CLK2_FPGA", WS, [r10b, up(34)], ch=0.0001)

u7, u8, u1 = blk.pad("U502", "7"), blk.pad("U502", "8"), blk.pad("U502", "1")
CK3 = C("+3V3_CLK")
c8v, c8g = blk.pad("C508", "@" + CK3), blk.pad("C508", "@GND")
T(CK3, 0.25, [u7, c8v])                                   # pin 7 -> C508.1 on the same row (0.24 mm gap)
T("GND", 0.3, [c8g, (c8g[0], 3.45)])
V(c8g[0], 3.45, "GND")
T(CK3, 0.25, [u7, (10.1, u7[1])])                        # pin 7 -> via under the body -> B -> via -> F -> pin 1
V(10.1, u7[1], CK3)
T(CK3, 0.3, [(10.1, u7[1]), (12.1, u7[1])], "B.Cu")    # continues below (REPAIR)
c9v, c9g = blk.pad("C509", "@" + CK3), blk.pad("C509", "@GND")
c23v, c23g = blk.pad("C623", "@" + CK3), blk.pad("C623", "@GND")
# REPAIR (24 Nov, recheck RF2-3): the B link from pin 7 comes up at C623 (north of its pad), so pin 1 is fed through
# C509 / C623 and not straight from the via
XL1 = c23v[0]
T(CK3, 0.3, [(12.1, u7[1]), (12.6, u7[1] + 0.5), (12.6, c23v[1] - 1.05), (XL1, c23v[1] - 0.75)], "B.Cu")
V(XL1, c23v[1] - 0.75, CK3)
T(CK3, 0.25, [(XL1, c23v[1] - 0.75), c23v])
T(CK3, 0.25, [u1, c9v])
T(CK3, 0.25, [c23v, c9v])
for g_ in (c9g, c23g):
    T("GND", 0.3, [g_, (g_[0], 6.2)])
    V(g_[0], 6.2, "GND")
T("GND", 0.25, [u8, (10.6, u8[1])])
V(10.6, u8[1], "GND")
fbv = blk.pad("FB608", "@" + CK3)
T(CK3, 0.4, [fbv, blk.pad("C510", "@" + CK3)])
fb1 = blk.pad("FB608", "@+3V3")
T("+3V3", 0.4, [fb1, (fb1[0], 11.35)])                  # FB608 input: via to the L4 +3V3 plane
V(fb1[0], 11.35, "+3V3")
c10g = blk.pad("C510", "@GND")
T("GND", 0.4, [c10g, (c10g[0], 7.7)])                   # C510 GND: via straight north of its pad
V(c10g[0], 7.7, "GND")
# ---------------- supply necks (pad-wide 0.2 mm, then 0.4 mm) and the decoupling capacitors at the pins
p36, p37, p25, p1, p12 = up(36), up(37), up(25), up(1), up(12)
c506 = blk.pad("C506", "@+3V3")
T("+3V3", 0.2, [p36, (p36[0], c506[1] + 0.1), (p36[0] - 0.1, c506[1]), c506], ch=0.0001)
V(5.55, 7.65, "+3V3")                                    # (stays clear of the B TAP4 lane y 7.25)
T("+3V3", 0.2, [(5.55, c506[1]), (5.55, 7.65)])
c502 = blk.pad("C502", "@+1V2")
T("+1V2", 0.2, [p37, (5.15, p37[1]), (5.15 - (p37[1] - c502[1]), c502[1]), c502], ch=0.0001)
V(5.05, 8.3, "+1V2")
T("+1V2", 0.25, [(5.05, 8.3), (5.05, 8.865)])
# DECOUPLING-6: C506 / C502 keep the shared via between their GND pads (no other spot: the L6 west-bundle lanes
# y 5.25-7.25 north, S_STROBE_P y 9.37 south, the L3 configuration lines x 1.15-2.95 west)
# VIAS-OUT-OF-PADS (24 Nov): the gap between the two GND pads was 0.38 mm and the via touched both; C506 moved
# 0.2 mm north, so the via sits in a 0.58 mm gap (hole edge 0.19 mm off each pad; west of it run the L3
# configuration lines, x <= 2.95)
YGV = (blk.pad("C506", "@GND")[1] + blk.pad("C502", "@GND")[1]) / 2
V(blk.pad("C506", "@GND")[0], YGV, "GND")
T("GND", 0.3, [blk.pad("C506", "@GND"), (blk.pad("C506", "@GND")[0], YGV)])
T("GND", 0.3, [blk.pad("C502", "@GND"), (blk.pad("C502", "@GND")[0], YGV)])
T("+3V3", 0.2, [p25, (p25[0], 7.45)])
V(p25[0], 7.45, "+3V3")
c504 = blk.pad("C504", "@+3V3")
T("+3V3", 0.2, [p1, c504])
c501 = blk.pad("C501", "@+1V2")
T("+1V2", 0.2, [p12, (p12[0], c501[1] - 0.3), (p12[0] + 0.3, c501[1]), c501], ch=0.0001)
for pin in ("2", "26"):                              # GND pins straight into the exposed pad
    p = up(pin)
    T("GND", 0.2, [p, (p[0], CY + 1.85 if p[1] > CY else CY - 1.85)])
THV = [(7.15, 9.7), (7.15, 11.2), (7.15, 12.7), (8.3, 9.6), (8.3, 11.7)]
for v in THV:
    V(*v, "GND")
# RECONFIG pull-up R501 (F) on the RECONFIG descent, +3V3 via; JP501 (F) GND via, JTAGSEL via
r1n, r1v = blk.pad("R501", "@FPGA_RECONFIG"), blk.pad("R501", "@+3V3")
T("/FPGA_RECONFIG", WS, [(2.4, r1n[1]), r1n])
T("+3V3", 0.3, [r1v, (4.35, r1v[1])])
V(4.35, r1v[1], "+3V3")

# ---------------- grid router (local support connections only)
# ---------------- grid router
G = 0.05
NX, NY = int(round(W / G)) + 1, int(round(H / G)) + 1
CLR = 0.1
LAYERS = ("F.Cu", "B.Cu")
gx, gy = np.meshgrid(np.arange(NX) * G, np.arange(NY) * G, indexing="ij")
inside = (gx <= W) & (gy <= H)
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
EXTRA = {"U502": 0.1}                       # footprint pad clearance 0.2 mm (0.1 above the router default)


def netcode(name):
    return blk.net(name).GetNetCode()


def raster():
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
        ex = EXTRA.get(fp.GetReference(), 0.0)
        for p in fp.Pads():
            x, y = blk.loc(p.GetPosition())
            bb = p.GetBoundingBox()
            w2, h2 = pcbnew.ToMM(bb.GetWidth()) / 2 + G / 2 + ex, pcbnew.ToMM(bb.GetHeight()) / 2 + G / 2 + ex
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
    own = raster()
    out, dists = [], []
    edge = ndimage.distance_transform_edt(np.pad(inside, 1)) [1:-1, 1:-1] * G
    for li in range(2):
        occ = (own[li] != -1) & (own[li] != code)
        d = ndimage.distance_transform_edt(~occ) * G
        dists.append(d)
        ok = (d >= w / 2 + CLR + 0.015) & inside & (edge >= w / 2 + 0.05 - 1e-9)
        out.append(ok)
    via_ok = (dists[0] >= bl.VIA_D / 2 + CLR + 0.01) & (dists[1] >= bl.VIA_D / 2 + CLR + 0.01) & inside
    via_ok &= edge >= bl.VIA_D / 2 + 0.15
    via_ok &= ~((abs(gx - CX) < 3.35 + 0.5) & (abs(gy - CY) < 3.35 + 0.5))   # no vias in the U501 pin fan-out ring
    via_ok &= ~((abs(gx - U502X) < 2.9 + 0.35) & (abs(gy - U502Y) < 1.15 + 0.3))  # nor at the U502 pin ends
    # VIAS-OUT-OF-PADS (24 Nov): no via in or at ANY soldered pad, same net included (tented vias only): the via
    # centre stays >= pad bbox + 0.31 mm, i.e. hole edge >= 0.21 mm outside the pad (RULES.md rule 12)
    for fp_ in blk.b.GetFootprints():
        for p_ in fp_.Pads():
            if p_.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            px_, py_ = blk.loc(p_.GetPosition())
            bb_ = p_.GetBoundingBox()
            via_ok &= ~((abs(gx - px_) < pcbnew.ToMM(bb_.GetWidth()) / 2 + 0.31) &
                        (abs(gy - py_) < pcbnew.ToMM(bb_.GetHeight()) / 2 + 0.31))
    for t in blk.b.GetTracks():                    # via-to-via (also same net) >= 0.5 mm centre distance
        if isinstance(t, pcbnew.PCB_VIA):
            vx, vy = blk.loc(t.GetPosition())
            via_ok &= (gx - vx) ** 2 + (gy - vy) ** 2 >= 0.5 ** 2
    return out, via_ok, own


def padobj(ref, num):
    if str(num)[0] == "@":
        return [p for p in blk.fps[ref].Pads() if p.GetNetname() == NL.canon(num[1:])][0]
    return blk.pad_obj(ref, num)


def pad_cells(p):
    x, y = blk.loc(p.GetPosition())
    bb = p.GetBoundingBox()
    w2, h2 = pcbnew.ToMM(bb.GetWidth()) / 2, pcbnew.ToMM(bb.GetHeight()) / 2
    cells = set()
    for i in range(int(math.ceil((x - w2) / G)), int(math.floor((x + w2) / G)) + 1):
        for j in range(int(math.ceil((y - h2) / G)), int(math.floor((y + h2) / G)) + 1):
            if (i * G - x) ** 2 <= (w2 - 0.03) ** 2 + 1e-9 and (j * G - y) ** 2 <= (h2 - 0.03) ** 2 + 1e-9:
                cells.add((i, j))
    lays = [li for li, ln in enumerate(LAYERS) if p.IsOnLayer(bl.L(ln))]
    if p.GetShape() == pcbnew.PAD_SHAPE_CIRCLE:
        axes = set(range(8))
    else:
        axes = {0, 2, 4, 6}
    return cells, lays, axes, (x, y), (w2, h2)


ROUTED, FAILED = [], []
ENDS = {}


def route(net, src, dst, w=WS, via_cost=1.0, layer_pref=None):
    """src: (ref, pad); dst: list of (ref, pad) / ('VIA', x, y) / ('EDGE', 'S', layer, x0, x1)"""
    net = NL.canon(net)
    code = netcode(net)
    ok, via_ok, _ = free_maps(code, w)
    sp = padobj(*src)
    scells, slays, saxes, sxy, _ = pad_cells(sp)
    tgt = [set(), set()]
    tpad = [set(), set()]
    tax, tcen = {}, {}
    for d in dst:
        if d[0] == "EDGE":
            _, side, ln, a0, a1 = d
            li = LAYERS.index(ln)
            for i in range(int(round(a0 / G)), int(round(a1 / G)) + 1):
                c = (i, NY - 1 - int(round((w / 2 + 0.05) / G + 0.499)))
                tgt[li].add(c)
                tax[(li,) + c] = {2}
                tcen[(li,) + c] = (i * G, H)
        elif d[0] == "VIA":
            ci, cj = int(round(d[1] / G)), int(round(d[2] / G))
            for di_ in (-2, -1, 0, 1, 2):
                for dj_ in (-2, -1, 0, 1, 2):
                    c = (ci + di_, cj + dj_)
                    r_ = math.hypot(c[0] * G - d[1], c[1] * G - d[2])
                    if 0.02 < r_ <= 0.11 and (round(c[0] * G, 3), round(c[1] * G, 3)) not in ENDS.get(net, set()):
                        for li in range(2):
                            tgt[li].add(c)
                            tax[(li,) + c] = set(range(8))
                            tcen[(li,) + c] = None
        else:
            pc, pl, pa, cen, _ = pad_cells(padobj(*d))
            for li in pl:
                for c in pc:
                    tgt[li].add(c)
                    tpad[li].add(c)
                    tax[(li,) + c] = pa
                    tcen[(li,) + c] = cen
    for li in range(2):
        for c in tgt[li]:
            if c in tpad[li] or dst[0][0] == "VIA":
                ok[li][c] = True
        tgt[li] = {c for c in tgt[li] if ok[li][c]}
        if li in slays:
            for c in scells:
                ok[li][c] = True
    allt = [c for li in range(2) for c in tgt[li]]
    if not allt:
        FAILED.append((net, src, None))
        return None
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
    goal, n = None, 0
    while openl:
        f, g_, st = heapq.heappop(openl)
        if g_ > best.get(st, 1e18) + 1e-9:
            continue
        i, j, li, d = st
        if (i, j) in tgt[li] and d >= 0 and d in tax[(li, i, j)] and not ((i, j) in scells and li in slays):
            goal = st
            break
        n += 1
        if n > 700000:
            break
        in_src = (i, j) in scells and li in slays
        near_src = False
        if d >= 0 and not in_src and li in slays:
            bi, bj = i - DIRS[d][0], j - DIRS[d][1]
            near_src = (bi, bj) in scells or (bi - DIRS[d][0], bj - DIRS[d][1]) in scells
        for nd in (range(8) if d < 0 else (d, (d + 1) % 8, (d - 1) % 8)):
            if d < 0 and nd not in saxes:
                continue
            if (in_src or near_src) and d >= 0 and nd != d:
                continue
            di, dj = DIRS[nd]
            a, b_ = i + di, j + dj
            if not (0 <= a < NX and 0 <= b_ < NY) or not ok[li][a, b_]:
                continue
            if (a, b_) in tpad[li] and (nd not in tax[(li, a, b_)] or (d >= 0 and nd != d) or d < 0 and not in_src):
                continue
            step = (1.414 if nd % 2 else 1.0) * pref[li] + (0.3 if (d >= 0 and nd != d) else 0.0)
            ns = (a, b_, li, nd)
            ng = g_ + step
            if ng < best.get(ns, 1e18):
                best[ns] = ng
                prev[ns] = st
                heapq.heappush(openl, (ng + hfun(a, b_), ng, ns))
        if via_ok[i, j] and not in_src and not near_src and d >= 0 and (i, j) not in tpad[li]:
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
        if k == 0 and len(pts) > 1:
            # start exactly on the pad centre line along the exit axis
            dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
            if abs(dy) < 1e-9:
                pts = [(round(sxy[0], 4), pts[0][1])] + pts[1:]
            elif abs(dx) < 1e-9:
                pts = [(pts[0][0], round(sxy[1], 4))] + pts[1:]
        if k == len(runs) - 1:
            if dst[0][0] == "EDGE":
                pts.append((pts[-1][0], H))
            else:
                gc = tcen[(goal[2], goal[0], goal[1])]
                last = pts[-1]
                if gc is None or (goal[0], goal[1]) in tpad[goal[2]]:
                    pass                                   # ends inside the pad, entered along its axis
                elif abs(last[0] - gc[0]) < 1e-6 or abs(last[1] - gc[1]) < 1e-6 or \
                        abs(abs(last[0] - gc[0]) - abs(last[1] - gc[1])) < 1e-6:
                    pts.append(gc)
        q = [pts[0]]
        for a_, b2, c2 in zip(pts, pts[1:], pts[2:]):
            v1 = (b2[0] - a_[0], b2[1] - a_[1])
            v2 = (c2[0] - b2[0], c2[1] - b2[1])
            if abs(v1[0] * v2[1] - v1[1] * v2[0]) > 1e-9 or v1[0] * v2[0] + v1[1] * v2[1] < 0:
                q.append(b2)
        q.append(pts[-1])
        t = [q[0]]
        for p_ in q[1:]:
            if math.hypot(p_[0] - t[-1][0], p_[1] - t[-1][1]) > 1e-6:
                t.append(p_)
        for (a_, b2) in zip(t, t[1:]):
            blk.track(net, w, [a_, b2], LAYERS[r[0][2]])
            ENDS.setdefault(net, set()).update({(round(a_[0], 3), round(a_[1], 3)), (round(b2[0], 3), round(b2[1], 3))})
        if k < len(runs) - 1:
            blk.via(round(r[-1][0] * G, 3), round(r[-1][1] * G, 3), net)
    ROUTED.append(net)
    if dst[0][0] == "EDGE":
        return path[-1][0] * G
    return True


def place_via(net, x, y, keep=()):
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


def tie(ref, num, d=0.75, pair=False, w=None):
    """pad -> own via (GND to In1, supply to In2) beyond the pad along the part axis; pair = second via"""
    p = padobj(ref, num)
    net = p.GetNetname()
    px, py = blk.loc(p.GetPosition())
    ox, oy = blk.loc(p.GetParent().GetPosition())
    dx, dy = px - ox, py - oy
    n_ = math.hypot(dx, dy) or 1.0
    w = w or (0.4 if net in ("GND", "+3V3", "+1V2") else 0.2)
    v = place_via(net, px + dx / n_ * d, py + dy / n_ * d, keep=[(ref, num)])
    r = route(net, (ref, num), [v], w)
    if pair and r:
        v2 = place_via(net, v[1] + dx / n_ * 0.6, v[2] + dy / n_ * 0.6)
        route(net, (ref, num), [v2], w)
    return r


def to_edge(net, src, x0, x1, w=WS, note=""):
    x = route(net, src, [("EDGE", "S", "B.Cu", x0, x1)], w)
    if x is not None:
        blk.iface(net, round(x, 3), H, "B.Cu", "S", "slow", w, note)
    return x



# ---------------- local support connections (router: F.Cu / B.Cu, vias land in the L2/L5 GND or L4 supply planes)
JOBS = []


def job(name, fn):
    JOBS.append((name, fn))


BPREF = [25.0, 1.0]
FPREF = [1.0, 25.0]


def vias_of(net):
    net = NL.canon(net)
    return [("VIA",) + blk.loc(t.GetPosition()) for t in blk.b.GetTracks()
            if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == net]


def near_vias(net, xy, n=6):
    return sorted(vias_of(net), key=lambda v: (v[1] - xy[0]) ** 2 + (v[2] - xy[1]) ** 2)[:n]


def rb(net, src, dst, w=WS, pref=BPREF, vc=30.0):
    return route(net, src, dst, w, layer_pref=pref, via_cost=vc)


for num in ("2", "4"):                               # crystal GND pads: own via outward along x
    def fy(num=num):
        x, y = blk.pad("Y501", num)
        v = (x, y - 1.15) if num == "2" else (x - 0.95, y)
        T("GND", 0.3, [(x, y), v])
        V(*v, "GND")
    job("y501g" + num, fy)
# crystal, U502 supply
job("xa", lambda: route("Net-(U502-XA)", ("U502", "2"), [("Y501", "@Net-(U502-XA)")], layer_pref=FPREF, via_cost=30))
job("xb", lambda: route("Net-(U502-XB)", ("U502", "3"), [("Y501", "@Net-(U502-XB)")], layer_pref=FPREF, via_cost=30))
job("clk3v3", lambda: route(CK3, ("C510", "@" + CK3), [("C509", "@" + CK3), ("C623", "@" + CK3)], 0.3,
                             layer_pref=FPREF, via_cost=30))
for ref, num, pr in (
                     ("C507", "@+3V3", True), ("C507", "@GND", True),
 ("C504", "@+3V3", True), ("C504", "@GND", True),
                     ("C501", "@+1V2", True), ("C501", "@GND", True), ("C503", "@+1V2", True), ("C503", "@GND", True)):
    job("tie%s%s" % (ref, num), lambda ref=ref, num=num, pr=pr: tie(ref, num, pair=pr))
def _c505g():                                        # DECOUPLING-6: own GND via 0.4 mm below the C505 GND pad
    g_ = blk.pad("C505", "@GND")
    T("GND", 0.3, [g_, (g_[0], 7.6)])
    V(g_[0], 7.6, "GND")
job("c505g", _c505g)
job("c505v", lambda: route("+3V3", ("C505", "@+3V3"), [("VIA", up(25)[0], 7.45)], 0.3, layer_pref=FPREF, via_cost=30))
# configuration resistors (F, NW): net pad -> its L3 via, other pad -> own GND / +3V3 via; JP501 to R504
CFGR = {42: "R506", 43: "R505", 44: "R504", 45: "R503", 46: "R502"}
# VIAS-OUT-OF-PADS (24 Nov): the three +3V3 pull-up pads (R502-R504, x 0.69 column at the block's west edge) share
# one +3V3 via below the column (their own vias sat at the pads: no room west of the column or between the rows)
def _cfg3v3():
    pts = [blk.pad(r_, "@+3V3") for r_ in ("R502", "R503", "R504")]
    T("+3V3", 0.4, pts + [(pts[0][0], 3.45)], ch=0.0001)
    V(pts[0][0], 3.45, "+3V3")
job("cfg3v3", _cfg3v3)
for pin, r_ in CFGR.items():
    def f(pin=pin, r_=r_):
        net = NL.net_of("U501", str(pin))
        route(net, (r_, "@" + net), [("VIA",) + L3V[pin]], WS, layer_pref=FPREF, via_cost=30)
        other = [p.GetNumber() for p in blk.fps[r_].Pads() if p.GetNetname() != net][0]
        if blk.fps[r_].Pads()[0].GetNetname() != "+3V3" and blk.fps[r_].Pads()[1].GetNetname() != "+3V3":
            tie(r_, other)
    job("cfg%d" % pin, f)
job("jsel", lambda: route("/fpga_clock/JTAGSEL_N", ("JP501", "@JTAGSEL_N"), [("R504", "@JTAGSEL_N")], WS, layer_pref=FPREF, via_cost=30))
job("jpg", lambda: tie("JP501", "@GND"))
job("tck", lambda: (rb(C("JTAG_TCK"), ("R507", "@JTAG_TCK"), [("VIA",) + JV[3]]), tie("R507", "@GND")))

print("routing", len(JOBS), "jobs ...")
FAILJ = []
for name, fn in JOBS:
    nf = len(FAILED)
    fn()
    if len(FAILED) > nf:
        FAILJ.append(name)
print("failed jobs:", FAILJ)

# ---------------- planes
blk.zone("GND", ["In1.Cu"], bl.rect_pts(0, 0, W, H), 0.2)
blk.zone("GND", ["In2.Cu"], bl.rect_pts(0, 0, W, H), 0.2)
blk.zone("GND", ["In4.Cu"], bl.rect_pts(0, 0, W, H), 0.2)
blk.zone("+3V3", ["In3.Cu"], bl.rect_pts(0, 0, W, H), 0.2, prio=0)
ISL = [(3.4, 8.1), (5.9, 8.1), (5.9, 9.0), (11.9, 9.0), (11.9, 13.8), (W, 13.8), (W, 16.1), (10.6, 16.1), (10.6, 14.4),
       (5.3, 14.4), (5.3, 9.6), (3.4, 9.6)]
blk.zone("+1V2", ["In3.Cu"], ISL, 0.2, prio=1)
blk.iface("+3V3", W, 5.0, "In3.Cu", "E", "supply", None, "L4 +3V3 zone over the block; feed from power W (board 74.45, 5.5)")
blk.iface("+1V2", W, 15.35, "In3.Cu", "E", "supply", None, "L4 +1V2 island (pins 12 / 37, C501-C503), strip east at y 13.8-16.1")
blk.iface("GND", 0, 0, "In1.Cu", "-", "supply", None, "L2 / L3 / L5 GND zones over the block")
blk.edge_rect(0, 0, W, H, "Dwgs.User")
for fp_ in blk.fps.values():
    fp_.Reference().SetLayer(pcbnew.B_Fab if fp_.GetLayer() == pcbnew.B_Cu else pcbnew.F_Fab)
blk.save(HERE)
path = os.path.join(HERE, "fpga.kicad_pcb")
print("strobe lengths: S_P %.3f S_N %.3f PH_P %.3f PH_N %.3f" % (blk.route_len("S_P"), blk.route_len("S_N"),
                                                               blk.route_len("PH_P"), blk.route_len("PH_N")))
print("slots:", {k.split("/")[-1]: v for k, v in SLOT.items()})
res = bl.check_board(path, refs=REFS, rf_widths=RF)
for k in ("clearance", "corner", "pad_axis", "unrouted", "rf_width", "rf_gap"):
    for e in res["details"].get(k, [])[:25]:
        print("   ", k, e)
CY_HITS = bl.courtyard_overlaps(path)
print("courtyard overlaps:", len(CY_HITS), CY_HITS)
if "--render" in sys.argv:
    bl.render(path, os.path.join(HERE, "fpga.png"), layers=("F.Cu", "B.Cu", "F.SilkS", "F.Fab", "Dwgs.User"), tmpdir=SCR)
    bl.render(path, os.path.join(HERE, "fpga_detail.png"), layers=("F.Cu", "B.Cu", "F.Fab", "Dwgs.User"),
              crop=(0, 0, 13, 14), tmpdir=SCR)
