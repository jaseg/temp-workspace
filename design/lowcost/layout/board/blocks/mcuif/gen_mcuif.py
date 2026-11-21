"""MCUIF block: STM32G474CBT6 (U704, LQFP-48) with decoupling, VDDA / VREF+ filter, passive control-voltage dividers,
the VNEG_REF op-amp U701, I2C pull-ups, BOOT0, LED (the /mcu_if/ sheet) plus J501 (programming header) and its UART
series resistors R511 / R512 (fpga_clock sheet, moved here).
Run: cd blocks/mcuif && python3 gen_mcuif.py [--render]
Block-local mm, origin = board (27, 45); block 66.5 x 12; copper >= 0.5 mm from y 12 (board edge) and nothing but
interface stubs within 0.5 mm of y 0.  Hand-drawn, planned fan-out (no router).  Pin-escape plan (U704 rot 0):
  N side  39-44, 46: inward vias in two staggered rows, B.Cu straight north = FPGA bus interfaces;
          37 / 38 (SWD): outward, two F.Cu lanes along the top (y 0.7 / 1.05) west to J501 pins 8 / 10 from above;
          45 BOOT0: inward via, top B.Cu lane west; 47 / 48 / 1: GND via, C713 in the NW notch.
  E side  33 / 34 USB east then north (90 R pair); 25 / 27 (ADC_TRIG / RECONFIG) east to vias, B.Cu north;
          28 LED east to R730 / D701; 31 / 32 UART inward vias, B.Cu lanes west; 35 / 36 GND / C711 (NE notch).
  W side  5 CLK, 8 ADC_IN, 9 TRIG_SEL: F.Cu west then north (columns); 10 DAC_TAPTH F.Cu west to its divider column;
          12 DAC_TRIG via to a B.Cu lane; 6 DBG1 / 7 NRST inward vias, B.Cu lanes west (C719 on F at pin 7).
  S side  13 / 14 / 17 DAC outputs, 20 VREF+, 21 VDDA: inward vias, B.Cu (VREF+ / VDDA caps on B at the vias).
B.Cu lane order leaving the west side (N->S): BOOT0, RX, TX, DBG1, NRST, VREFP, BIAS_K, BIAS_A, VOFS, DAC_TRIG.
The J501 bus (RX, TX, DBG1, NRST) enters the north-row pins from above; JTAG leaves the south row on F.Cu."""
import sys, os, math, json
sys.path.insert(0, "../..")
import pcbnew
import boardlib as bl

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board"
os.makedirs(SCR, exist_ok=True)
W, H = 66.5, 12.0
WS = 0.15                                   # signal width
WP = 0.3                                    # supply stubs (pad-wide for 0402)
blk = bl.Block("mcuif")
NL = blk.nl
MOVED = ["J501", "R511", "R512"]
REFS = sorted([r for r, c in NL.comps.items() if c["sheet"] == "/mcu_if/"] + MOVED)
cn = NL.canon


def zdiff(w, s):
    z0, ee = bl.microstrip(w)
    return 2 * z0 * (1 - 0.48 * math.exp(-0.96 * s / bl.H)), z0, ee


W90, S90 = 0.295, 0.205
ZD, Z0U, EEU = zdiff(W90, S90)


def place(ref, x, y, orient="h", first=None, side="F", rot=None):
    """2-pad parts: orient h / v; first = net of the pad that must be west (h) or north (v)"""
    if rot is not None:
        fp = blk.place(ref, x, y, rot)
        if side == "B":
            fp.Flip(blk.P(x, y), True)
            fp.Reference().SetLayer(pcbnew.B_Fab)
        return fp
    for r in ((0, 180) if orient == "h" else (90, 270)):
        fp = blk.place(ref, x, y, r)
        if side == "B":
            fp.Flip(blk.P(x, y), True)
            fp.Reference().SetLayer(pcbnew.B_Fab)
        if first is None:
            return fp
        p = blk.pad(ref, "@" + first)
        q = [blk.loc(pp.GetPosition()) for pp in fp.Pads() if pp.GetNetname() != cn(first)][0]
        ok = (p[0] < q[0]) if orient == "h" else (p[1] < q[1])
        if ok:
            return fp
        blk.b.Remove(fp)
        del blk.fps[ref]
    raise RuntimeError(ref)


def T(net, w, pts, layer="F.Cu"):
    blk.track(cn(net), w, pts, layer)


def V(net, *pts):
    for x, y in pts:
        blk.via(x, y, cn(net))


def P(ref, n):
    return blk.pad(ref, n)


def IF(net, x, w=WS, note="", layer="B.Cu", cls="slow"):
    blk.iface(cn(net), x, 0.0, layer, "N", cls, w, note)


def stub(net, x, y, w=WS, note="", cls="slow"):
    """F.Cu column top -> via at (x, y) -> B.Cu stub to the N edge = interface"""
    V(net, (x, y))
    T(net, w, [(x, y), (x, 0.0)], "B.Cu")
    IF(net, x, w, note, cls=cls)


# ============================================================ U704 and its pins
CX, CY = 52.0, 6.3
blk.place("U704", CX, CY, 0)


def wy(k):              # W side pin k (1..12): y
    return CY - 2.75 + 0.5 * (k - 1)


def ey(k):              # E side pin k (25..36): y
    return CY + 2.75 - 0.5 * (k - 25)


def nx(k):              # N side pin k (37..48): x
    return CX + 2.75 - 0.5 * (k - 37)


def sx(k):              # S side pin k (13..24): x
    return CX - 2.75 + 0.5 * (k - 13)


XW_TIP, XW_IN = CX - 4.9, CX - 3.425       # W pad outer / inner end
XE_TIP, XE_IN = CX + 4.9, CX + 3.425
YN_TIP, YN_IN = CY - 4.9, CY - 3.425
YS_TIP, YS_IN = CY + 4.9, CY + 3.425
UP = lambda k: P("U704", str(k))

# ============================================================ placement (other parts)
JX, JY = 15.0, 8.2
blk.place("J501", JX, JY, 90)                     # holes x 4.2..25.8, courtyard y 4.9..11.5 (board y 56.5)
place("R511", 7.8, 4.05, "h", "Net-(J501-Pin_2)", "B")    # RX series R on B, J501 side west
place("R512", 10.3, 4.55, "h", "Net-(J501-Pin_4)", "B")   # TX series R on B
# decoupling in the U704 courtyard notches (F)
place("C713", 47.9, 2.05, "h", "GND")             # pins 48 / 1
place("C710", 48.6, 2.3, "h", "+3V3", "B")        # second 100 nF at pins 48 / 1 (B, at the inner vias)
place("C711", 56.1, 2.05, "h", "+3V3")            # pin 36
place("C712", 56.1, 10.6, "h", "+3V3")            # pin 24
place("C714", 60.0, 10.6, "h", "GND")             # 10 uF bulk
place("C719", 45.9, 6.55, "h", "GND")             # NRST at pin 7
# VREF+ / VDDA on B at the pin vias
place("C717", 53.23, 7.0, "h", "/mcu_if/VREFP", "B")
place("C718", 53.23, 7.95, "h", "/mcu_if/VREFP", "B")
place("C716", 53.75, 10.5, "h", "/mcu_if/VDDA", "B")
place("C715", 51.85, 10.5, "h", "/mcu_if/VDDA", "B")
place("FB701", 49.95, 10.5, "h", "+3V3", "B")
# I2C pull-ups on B beside their lanes (fpga bus, top)
place("R727", 56.1, 3.3, "h", "/I2C_SCL", "B")    # SCL: east of its inner via, B under the E pads
place("R728", 52.2, 6.0, "h", "/I2C_SDA", "B")    # SDA: under the body (F drop from the pin-44 via)
# BOOT0 (B, north of the bus lanes)
place("JP701", 45.5, 3.0, "h", "/mcu_if/BOOT0", "B")
place("R729", 42.1, 2.9, "v", "GND", "B")
# LED (E side)
place("R730", 59.6, 7.55, "h", "/mcu_if/LED")
place("D701", 62.1, 7.55, "h", "Net-(D701-K)")
# VTAP 0 R links (east of the USB pair)
place("R725", 63.6, 2.6, "v", "/VTAP_P")
place("R726", 65.45, 2.6, "v", "/VTAP_N")
# divider columns (F): series R inline (input south, output north), shunt parts hanging west
COLY = 3.6
place("R723", 43.3, COLY, "v", "/VTAP_TH")        # DAC_TAPTH -> VTAP_TH
place("R724", 41.9, 2.05, "h", "GND")
place("C709", 41.9, 3.09, "h", "GND")
place("R735", 39.5, COLY, "v", "/VBIAS_K")        # DAC_BIAS_K -> VBIAS_K
place("R736", 38.1, COLY + 0.51, "h", "GND")      # DAC_BIAS_K -> GND, at the input pad
place("R733", 36.0, COLY, "v", "/VBIAS_A")        # DAC_BIAS_A -> VBIAS_A
place("R734", 34.6, 2.05, "h", "-2V5")            # VBIAS_A -> -2V5
# ADC_REF_MID divider (W1, above J501's east end)
place("R703", 28.8, 3.6, "h", "/ADC_REF_MID")
place("R704", 27.2, 2.5, "h", "GND")
place("C702", 26.9, 3.6, "h", "GND")
# U701 group (far west, above J501)
blk.place("U701", 5.5, 2.5, 180)                  # 4 IN- / 5 V+ west, 1 OUT / 2 V- / 3 GND east
place("R731", 2.4, 1.55, "h", "/mcu_if/VREFP")
place("C720", 2.4, 3.45, "h", "GND")
place("R732", 8.25, 1.9, "v", "Net-(U701--)")
place("C722", 9.25, 1.9, "v", "Net-(U701--)")
place("C721", 8.42, 2.03, "v", "GND", "B")        # pin 2 / 3 decoupling on B, beside the two vias (no via-in-pad)
# R737 TRIG_SEL reset pull-down (2.0k, PA1 floats at reset): on B under the TRIG_SEL column, TRIG_SEL pad on the
# column-top via (B stub south, on-axis), GND pad into the B.Cu ground pour
place("R737", 44.0, 3.3, "v", "/TRIG_SEL", "B")
for r in REFS:
    assert r in blk.fps, r

# ============================================================ supplies at U704
# NW: pin 48 west and pin 1 north into C713.1, C713.2 GND via; pin 47 GND inward via; pin 1 inner +3V3 via
c1, c2 = P("C713", "@+3V3"), P("C713", "@GND")
T("+3V3", WP, [(nx(48), c1[1]), c1])
T("+3V3", WP, [(c1[0], wy(1)), c1])
T("+3V3", 0.25, [UP(1), (XW_IN + 0.45, wy(1))])
V("+3V3", (XW_IN + 0.45, wy(1)))
T("GND", WP, [c2, (c2[0], 2.85)])
V("GND", (c2[0], 2.85))
T("GND", 0.25, [UP(47), (nx(47), 3.3)])
V("GND", (nx(47), 3.3))
a, g = P("C710", "@+3V3"), P("C710", "@GND")
T("+3V3", WP, [a, (a[0], 3.0), (a[0] + 0.55, wy(1)), (XW_IN + 0.45, wy(1))], "B.Cu")
T("GND", WP, [g, (g[0], 2.85), (nx(47), 3.3)], "B.Cu")
# NE: pin 36 north into C711.1, inner +3V3 via; C711.2 -> 2 GND vias; pin 35 GND east via
c1, c2 = P("C711", "@+3V3"), P("C711", "@GND")
T("+3V3", WP, [(c1[0], ey(36)), c1])
T("+3V3", WP, [c1, (c1[0], 1.25)])
V("+3V3", (c1[0], 1.25))
T("GND", WP, [c2, (c2[0], 1.25)])
T("GND", WP, [c2, (57.3, c2[1])])
V("GND", (c2[0], 1.25), (57.3, c2[1]))
T("GND", 0.25, [UP(35), (57.4, ey(35))])
V("GND", (57.4, ey(35)))
# SE: pin 24 east into C712.1, inner +3V3 via; C712.2 -> GND via pair -> C714
c1, c2 = P("C712", "@+3V3"), P("C712", "@GND")
T("+3V3", WP, [(sx(24), c1[1]), c1])
T("+3V3", 0.25, [UP(24), (sx(24), YS_IN - 0.45)])
V("+3V3", (sx(24), YS_IN - 0.45))
T("GND", WP, [c2, (58.0, c2[1])])
V("GND", (57.3, c2[1]), (58.0, c2[1]))
b1, b2 = P("C714", "@GND"), P("C714", "@+3V3")
T("GND", 0.5, [(58.0, c2[1]), b1])
T("+3V3", 0.5, [b2, (62.6, b2[1])])
V("+3V3", (61.9, b2[1]), (62.6, b2[1]))
# S side GND pins 19 / 23: inward vias
T("GND", 0.25, [UP(19), (sx(19), YS_IN - 0.45)])
V("GND", (sx(19), YS_IN - 0.45))
T("GND", 0.25, [UP(23), (sx(23), YS_IN - 1.05)])
V("GND", (sx(23), YS_IN - 1.05))
# VREF+ (pin 20): inward via -> C718 / C717 on B (VREFP pads in one column at the via x)
vr = (sx(20), YS_IN - 1.05)
T("/mcu_if/VREFP", 0.25, [UP(20), vr])
V("/mcu_if/VREFP", vr)
T("/mcu_if/VREFP", WP, [vr, P("C718", "@VREFP"), P("C717", "@VREFP")], "B.Cu")
g1, g2 = P("C717", "@GND"), P("C718", "@GND")
T("GND", WP, [g1, g2, (g2[0], 8.65)], "B.Cu")
V("GND", (g2[0], 8.65))
# VDDA (pin 21): inward via -> C716 (below), C715 and FB701 west along y 9.75 / 10.5 on B
vd = (sx(21), YS_IN - 0.45)
T("/mcu_if/VDDA", 0.25, [UP(21), vd])
V("/mcu_if/VDDA", vd)
d6, d5, fbv = P("C716", "@VDDA"), P("C715", "@VDDA"), P("FB701", "@VDDA")
T("/mcu_if/VDDA", WP, [vd, d6], "B.Cu")
T("/mcu_if/VDDA", 0.2, [(vd[0], 9.75), (d5[0], 9.75), d5], "B.Cu")
T("/mcu_if/VDDA", WP, [d5, fbv], "B.Cu")
g6, g5, f3 = P("C716", "@GND"), P("C715", "@GND"), P("FB701", "@+3V3")
T("GND", WP, [g6, (g6[0], 9.65), (sx(23), YS_IN - 1.05)], "B.Cu")
T("GND", WP, [g5, (g5[0], 11.15), (g6[0], 11.15), g6], "B.Cu")
T("+3V3", WP, [f3, (48.75, f3[1])], "B.Cu")
V("+3V3", (48.75, f3[1]))

# ============================================================ N side: FPGA bus (inward vias, B.Cu north)
NOTE = {"/I2C_SCL": "MS5351M; 4.7k R727 here", "/SPI_SCK": "U501.28", "/SPI_MISO": "U501.30",
        "/SPI_MOSI": "U501.29", "/I2C_SDA": "MS5351M; 4.7k R728 here", "/FPGA_DONE": "U501.46 (R502 pull-up)",
        "/SPI_CS": "U501.31"}
VIA_N = {}
for k in (39, 40, 41, 42, 43, 44, 46):
    net = NL.net_of("U704", str(k))
    yv = 3.3 if k % 2 else 3.9
    T(net, WS, [UP(k), (nx(k), yv)])
    V(net, (nx(k), yv))
    T(net, WS, [(nx(k), yv), (nx(k), 0.0)], "B.Cu")
    IF(net, nx(k), WS, f"U704.{k}; {NOTE[net]}")
    VIA_N[k] = (nx(k), yv)
T("/I2C_SCL", WS, [(nx(39), 2.9), (nx(39) + 0.4, 3.3), P("R727", "@I2C_SCL")], "B.Cu")
v = P("R727", "@+3V3")
T("+3V3", WP, [v, (57.3, v[1])], "B.Cu")
V("+3V3", (57.3, v[1]))
vs = (nx(44), 6.0)                                 # SDA: F under the body to a via in the free pocket
T("/I2C_SDA", WS, [VIA_N[44], vs])
V("/I2C_SDA", vs)
T("/I2C_SDA", WS, [vs, P("R728", "@I2C_SDA")], "B.Cu")
v = P("R728", "@+3V3")
T("+3V3", WP, [v, (53.4, v[1])], "B.Cu")
V("+3V3", (53.4, v[1]))

# ============================================================ SWD: outward, top F.Cu lanes to J501 pins 8 / 10
T("/UC_SWDIO", WS, [UP(37), (nx(37), 0.7), (P("J501", "8")[0], 0.7), P("J501", "8")])
T("/UC_SWCLK", WS, [UP(38), (nx(38), 1.05), (P("J501", "10")[0], 1.05), P("J501", "10")])

# ============================================================ under-body B.Cu lanes to the west
LX = XW_TIP - 0.3          # lanes leave the W pad row here (x 46.8)
YL = {"BOOT0": 4.4, "RX": 4.9, "TX": 5.4, "DBG1": 6.05, "NRST": 6.55, "VREFP": 7.0, "BIAS_K": 7.5,
      "BIAS_A": 8.0, "VOFS": 8.5, "DAC_TRIG": 9.05}
JOGX, JOG = 33.0, 0.85     # the J501 bus moves up by JOG at x JOGX (45 deg)
# BOOT0 (pin 45): inward via, down to its lane, west to R729 / JP701 (B)
vb = (nx(45), 3.3)
T("/mcu_if/BOOT0", WS, [UP(45), vb])
V("/mcu_if/BOOT0", vb)
jb, rb = P("JP701", "@BOOT0"), P("R729", "@BOOT0")
T("/mcu_if/BOOT0", WS, [vb, (vb[0], YL["BOOT0"]), (jb[0], YL["BOOT0"]), jb], "B.Cu")
T("/mcu_if/BOOT0", WS, [rb, (rb[0], YL["BOOT0"]), (jb[0], YL["BOOT0"])], "B.Cu")
j3, rg = P("JP701", "@+3V3"), P("R729", "@GND")
T("+3V3", WP, [j3, (j3[0] + 0.55, j3[1]), (47.25, 3.55), (P("C710", "@+3V3")[0] + 0.55, wy(1))], "B.Cu")
T("GND", WP, [rg, (rg[0], 1.75), (41.05, 1.75), (40.75, 2.05)], "B.Cu")
# UART (pins 32 RX / 31 TX): inward vias
vrx, vtx = (XE_IN - 0.325, ey(32)), (XE_IN - 0.925, ey(31))
T("/HOST_RX", WS, [UP(32), vrx])
T("/HOST_TX", WS, [UP(31), vtx])
V("/HOST_RX", vrx)
V("/HOST_TX", vtx)
# DBG1 (pin 6) / NRST (pin 7): inward vias; NRST also out to C719
vdb, vnr = (XW_IN + 0.425, wy(6)), (XW_IN + 0.925, wy(7))
T("/DBG1", WS, [UP(6), vdb])
T("/UC_NRST", WS, [UP(7), vnr])
V("/DBG1", vdb)
V("/UC_NRST", vnr)
T("/UC_NRST", WS, [UP(7), P("C719", "@UC_NRST")])
cg = P("C719", "@GND")
T("GND", WP, [cg, (cg[0], 1.9)])                   # F.Cu up between the CLK / ADC_IN columns (B lanes below)
V("GND", (cg[0], 1.9))
# J501 targets (north row, entered from above) with R511 / R512 inline on B
J = {k: P("J501", str(k)) for k in range(1, 17)}
r1a, r1b = P("R511", "@Net-(J501-Pin_2)"), P("R511", "@HOST_RX")
r2a, r2b = P("R512", "@Net-(J501-Pin_4)"), P("R512", "@HOST_TX")
T("Net-(J501-Pin_2)", WS, [r1a, (J[2][0], r1a[1]), J[2]], "B.Cu")
T("Net-(J501-Pin_4)", WS, [r2a, (J[4][0], r2a[1]), J[4]], "B.Cu")


def bus(net, src_pts, y, x_end_pts):
    """B.Cu lane: src_pts (under the body) -> west at y -> 45-degree jog up by JOG at JOGX -> x_end_pts"""
    pts = list(src_pts) + [(src_pts[-1][0], y) if abs(src_pts[-1][1] - y) > 1e-6 else src_pts[-1]]
    pts += [(JOGX, y), (JOGX - JOG, y - JOG)] + list(x_end_pts)
    T(net, WS, pts, "B.Cu")


bus("/HOST_RX", [vrx, (vrx[0] - (vrx[1] - YL["RX"]), YL["RX"])], YL["RX"], [r1b])
bus("/HOST_TX", [vtx], YL["TX"], [r2b])
bus("/DBG1", [vdb], YL["DBG1"], [(J[12][0], YL["DBG1"] - JOG), J[12]])
bus("/UC_NRST", [vnr], YL["NRST"], [(J[14][0], YL["NRST"] - JOG), J[14]])
# VREFP lane: C717 -> west -> via (REF_MID column, x 29.9) -> down -> bottom channel y 11.1 -> x 0.9 -> U701 group
XREF = 29.9
T("/mcu_if/VREFP", WS, [P("C717", "@VREFP"), (XREF, YL["VREFP"]), (XREF, 11.1), (0.9, 11.1), (0.9, 2.3)], "B.Cu")
V("/mcu_if/VREFP", (XREF, YL["VREFP"]), (0.9, 2.3))
# S-side DAC outputs: inward vias, up to their lanes, west to their column vias
COLX = {"BIAS_K": 39.5, "BIAS_A": 36.0, "VOFS": 32.5, "DAC_TRIG": 31.6}
for key, k, yv in (("BIAS_K", 17, YS_IN - 0.45), ("BIAS_A", 14, YS_IN - 1.05), ("VOFS", 13, YS_IN - 0.45)):
    net = NL.net_of("U704", str(k))
    T(net, WS, [UP(k), (sx(k), yv)])
    V(net, (sx(k), yv))
    T(net, WS, [(sx(k), yv), (sx(k), YL[key]), (COLX[key], YL[key])], "B.Cu")
    V(net, (COLX[key], YL[key]))
# DAC_TRIG (pin 12): F stub west, via, B lane
vdt = (XW_TIP - 0.5, wy(12))
T("/DAC_TRIG", WS, [UP(12), vdt])
V("/DAC_TRIG", vdt)
T("/DAC_TRIG", WS, [vdt, (COLX["DAC_TRIG"], YL["DAC_TRIG"])], "B.Cu")
V("/DAC_TRIG", (COLX["DAC_TRIG"], YL["DAC_TRIG"]))

# ============================================================ W side F.Cu columns north
YIF = 1.5                   # column-top interface vias (under the SWD lanes)
for k, xc, yv, note in ((5, 46.35, YIF, "U704.5 PF0 HSE bypass <- MS5351M CLK1 (R509 33 R in fpga)"),
                        (8, 44.5, YIF, "U704.8 PA0 ADC in; RC R211 / C207 in the analog block"),
                        (9, 44.0, YIF + 0.6, "U704.9 PA1 -> R302 / TMUX136 select (phase)")):
    net = NL.net_of("U704", str(k))
    T(net, WS, [UP(k), (xc, wy(k)), (xc, yv)])
    stub(net, xc, yv, WS, note)
    if k == 9:
        T(net, WS, [(xc, yv), P("R737", "@TRIG_SEL")], "B.Cu")
# straight DAC columns from the B lanes
for key, net, note in (("VOFS", "/VOFS", "U704.13 DAC1_OUT2 -> R119 (input block)"),
                       ("DAC_TRIG", "/DAC_TRIG", "U704.12 DAC1_OUT1 -> R383 (phase)")):
    x = COLX[key]
    T(net, WS, [(x, YL[key]), (x, YIF)])
    stub(net, x, YIF, WS, note)


def column(xc, y_in, src_net, rs, out_net, w=WS, note="", src=None):
    """series R rs vertical at xc: input from (xc, y_in) up into its south pad; output from its north pad to the
    column-top via and interface"""
    a, b = P(rs, "@" + src_net), P(rs, "@" + out_net)
    T(src_net, WS, (src or []) + [(xc, y_in), a])
    T(out_net, w, [b, (xc, YIF)])
    stub(out_net, xc, YIF, w, note)


# TAPTH: pin 10 F west at its own y to x 43.3, north into R723; R724 / C709 hang west at the output node
xt = 43.3
column(xt, wy(10), "/mcu_if/DAC_TAPTH", "R723", "/VTAP_TH", 0.25, "R723 / R724 / C709 -> R380 / R381 (phase)",
       src=[UP(10)])
for ref in ("R724", "C709"):
    a, g = P(ref, "@VTAP_TH"), P(ref, "@GND")
    T("/VTAP_TH", 0.25, [a, (xt, a[1])])
    T("GND", WP, [g, (40.75, g[1])])
    V("GND", (40.75, g[1]))
# BIAS_K: R735 inline, R736 at the input pad
column(COLX["BIAS_K"], YL["BIAS_K"], "/mcu_if/DAC_BIAS_K", "R735", "/VBIAS_K", WS, "R735 5.1k from U704.17 -> sampler")
a, g = P("R736", "@DAC_BIAS_K"), P("R736", "@GND")
T("/mcu_if/DAC_BIAS_K", WS, [a, P("R735", "@DAC_BIAS_K")])
T("GND", WP, [g, (37.0, g[1])])
V("GND", (37.0, g[1]))
# BIAS_A: R733 inline, R734 to -2V5 at the output node
column(COLX["BIAS_A"], YL["BIAS_A"], "/mcu_if/DAC_BIAS_A", "R733", "/VBIAS_A", WS, "R733 / R734 divider -> sampler")
a, g = P("R734", "@VBIAS_A"), P("R734", "@-2V5")
T("/VBIAS_A", WS, [a, (COLX["BIAS_A"], a[1])])
T("-2V5", WP, [g, (33.4, g[1])])
V("-2V5", (33.4, g[1]))
# ADC_REF_MID: VREFP via (29.9, 7.0) north into R703 (east pad), node -> R704 / C702 / interface
a, b = P("R703", "@VREFP"), P("R703", "@ADC_REF_MID")
T("/mcu_if/VREFP", WS, [(XREF, YL["VREFP"]), (XREF, a[1]), a])
xm = b[0]
T("/ADC_REF_MID", WS, [b, (xm, YIF)])
stub("/ADC_REF_MID", xm, YIF, WS, "R703 / R704 / C702 -> U202 (sampler)")
for ref in ("R704", "C702"):
    a, g = P(ref, "@ADC_REF_MID"), P(ref, "@GND")
    T("/ADC_REF_MID", WS, [a, (xm, a[1])] if abs(a[1] - b[1]) > 1e-6 else [a, b])
    T("GND", WP, [g, (g[0] - 0.75, g[1])])
    V("GND", (g[0] - 0.75, g[1]))

# ============================================================ U701 group (west)
u = lambda k: P("U701", str(k))
r31v, r31n = P("R731", "@VREFP"), P("R731", "@Net-(U701--)")
T("/mcu_if/VREFP", WS, [(0.9, 2.3), (0.9, r31v[1]), r31v])
T("Net-(U701--)", WS, [r31n, u(4)])
T("Net-(U701--)", WS, [u(4), (u(4)[0], 0.75), (P("C722", "@Net-(U701--)")[0], 0.75), P("C722", "@Net-(U701--)")])
T("Net-(U701--)", WS, [(P("R732", "@Net-(U701--)")[0], 0.75), P("R732", "@Net-(U701--)")])
ro, co = P("R732", "@VNEG_REF"), P("C722", "@VNEG_REF")
T("/VNEG_REF", WS, [u(1), (ro[0], u(1)[1]), ro])
T("/VNEG_REF", WS, [(ro[0], u(1)[1]), (co[0], u(1)[1]), co])
T("/VNEG_REF", WS, [(co[0], u(1)[1]), (9.95, u(1)[1]), (9.95, 0.9)])
stub("/VNEG_REF", 9.95, 0.9, WS, "U701 TLV9001 out (-1.97 V) -> R123 (input block)")
c20p, c20g = P("C720", "@+2V5"), P("C720", "@GND")
T("+2V5", WP, [u(5), c20p])
T("+2V5", WP, [c20p, (c20p[0], 4.3)])
V("+2V5", (c20p[0], 4.3))
T("GND", WP, [c20g, (c20g[0], 4.3)])
V("GND", (c20g[0], 4.3))
T("GND", WP, [u(3), (u(3)[0] + 0.0, 0.85)]) if False else None
# U701 pin 3 (GND, +IN) and pin 2 (-2V5): vias east of the pads; C721 on B between them
v3 = (u(3)[0] + 0.9, u(3)[1])
T("GND", WP, [u(3), v3])
V("GND", v3)
v2 = (u(2)[0] + 0.9, u(2)[1])
T("-2V5", WP, [u(2), v2])
V("-2V5", v2)
T("GND", WP, [v3, P("C721", "@GND")], "B.Cu")
T("-2V5", WP, [v2, P("C721", "@-2V5")], "B.Cu")


# ============================================================ JTAG: J501 south row north on F.Cu, via, B stub
JNOTE = {5: "DBG2 -> U501", 7: "JTAG TCK -> U501.3", 9: "JTAG TMS", 11: "JTAG TDI", 13: "JTAG TDO"}
for k in (5, 7, 9, 11, 13):
    net = NL.net_of("J501", str(k))
    T(net, WS, [J[k], (J[k][0], 1.6)])
    stub(net, J[k][0], 1.6, WS, f"J501.{k} {JNOTE[k]} (fpga S-W)")

# ============================================================ VTAP links, LED, E-side bus, USB
for ref, net, sup in (("R725", "/VTAP_P", "+2V5"), ("R726", "/VTAP_N", "-2V5")):
    a, s = P(ref, "@" + net), P(ref, "@" + sup)
    T(net, 0.4, [a, (a[0], 0.85)])
    stub(net, a[0], 0.85, 0.4, f"{ref} 0 R from {sup} (In2 via pair at the part)", cls="supply")
    T(sup, 0.4, [s, (s[0], 4.85)])
    V(sup, (s[0], 4.15), (s[0], 4.85))
la, lk = P("R730", "@LED"), P("R730", "@Net-(D701-K)")
T("/mcu_if/LED", WS, [UP(28), la])
T("Net-(D701-K)", WS, [lk, P("D701", "@Net-(D701-K)")])
d3 = P("D701", "@+3V3")
T("+3V3", WP, [d3, (d3[0] + 0.85, d3[1])])
V("+3V3", (d3[0] + 0.85, d3[1]))
for k, xv, note in ((27, 58.1, "U704.27 PB13 -> U501.48 RECONFIG_N (R501 pull-up)"),
                    (25, 58.8, "U704.25 PB11 EXTI11 <- U501.41")):
    net = NL.net_of("U704", str(k))
    T(net, WS, [UP(k), (xv, ey(k))])
    V(net, (xv, ey(k)))
    T(net, WS, [(xv, ey(k)), (xv, 0.0)], "B.Cu")
    IF(net, xv, WS, note)
# USB pair (F.Cu, 90 R, pitch 0.5 = pin pitch), DP bump for skew
RF = {"/USB_DP": W90, "/USB_DM": W90}
pDP, pDM = UP(34), UP(33)
XV = 61.0


def usb(hb):
    L = lambda q: sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(q, q[1:]))
    yb = pDP[1] - 1.1 - 0.2
    dp = [pDP, (XV - 1.1, pDP[1]), (XV, pDP[1] - 1.1), (XV, yb), (XV - hb, yb - hb), (XV - hb, yb - hb - 0.3),
          (XV, yb - 2 * hb - 0.3), (XV, 0.0)] if hb > 0 else [pDP, (XV - 1.1, pDP[1]), (XV, pDP[1] - 1.1), (XV, 0.0)]
    xa = XV - 1.1 + 0.5 * math.tan(math.radians(22.5))
    dm = [pDM, (xa, pDM[1]), (XV + 0.5, pDM[1] - (XV + 0.5 - xa)), (XV + 0.5, 0.0)]
    return dp, dm, L(dp), L(dm)


dp0, dm0, l0, m0 = usb(0)
HB = (m0 - l0) / (2 * math.sqrt(2) - 2)
dp, dm, _, _ = usb(HB)
blk.track("/USB_DP", W90, dp, "F.Cu", name="USB_DP", z=45, ch=0.0)
blk.track("/USB_DM", W90, dm, "F.Cu", name="USB_DM", z=45, ch=0.0)
LDP, LDM = blk.route_len("USB_DP"), blk.route_len("USB_DM")
for q in (dp, dm):
    blk.rf_keepout(q, W90, 2 * W90)
blk.iface("/USB_DP", XV, 0.0, "F.Cu", "N", "pair", W90, f"90 R diff (w {W90} s {S90}) from J601 / U608; {LDP:.2f} mm in block")
blk.iface("/USB_DM", XV + 0.5, 0.0, "F.Cu", "N", "pair", W90, f"90 R diff; {LDM:.2f} mm in block")

# ============================================================ silkscreen: J501 outline clipped at its pegs; U704 wedge off
for ref in ("J501", "U704"):
    fp = blk.fps[ref]
    for gi in list(fp.GraphicalItems()):
        if gi.GetLayer() == pcbnew.F_SilkS and gi.GetClass() not in ("PCB_FP_TEXT", "PCB_TEXT"):
            if ref == "U704" and gi.GetShape() != pcbnew.SHAPE_T_POLY:
                continue
            fp.Remove(gi)
sx0, sx1, sy0, sy1 = JX - 13.955, JX + 13.955, JY - 2.8, JY + 2.8
for seg in (((sx0, sy0), (2.3, sy0)), ((6.2, sy0), (sx1, sy0)), ((sx0, sy1), (23.8, sy1)), ((27.7, sy1), (sx1, sy1)),
            ((sx0, sy0), (sx0, sy1)), ((sx1, sy0), (sx1, sy1))):
    blk.line(seg[0][0], seg[0][1], seg[1][0], seg[1][1], "F.SilkS", 0.12)

# ============================================================ pours, outline, supply interfaces
blk.zone("GND", ["In1.Cu"], bl.rect_pts(0, 0, W, H - 0.5), 0.2)
blk.zone("GND", ["F.Cu"], bl.rect_pts(0, 0.5, W, H - 0.5), 0.2, minw=0.2)
blk.zone("GND", ["B.Cu"], bl.rect_pts(0, 0.5, W, H - 0.5), 0.2, minw=0.2)
for n in ("+3V3", "+2V5", "-2V5", "VBUS"):
    blk.iface(n, 0, 0, "In2.Cu", "-", "supply", None, "via pairs at the caps / THT pins of J501; In2 region by the integrator")
blk.edge_rect(0, 0, W, H, "Dwgs.User")
blk.save(HERE)
path = os.path.join(HERE, "mcuif.kicad_pcb")
print(f"USB pair: w {W90} s {S90} -> Zdiff {ZD:.1f} R; DP {LDP:.3f} mm, DM {LDM:.3f} mm (skew {abs(LDP - LDM):.3f} mm)")
res = bl.check_board(path, refs=REFS, rf_widths=RF)
for k in ("clearance", "corner", "pad_axis", "unrouted", "courtyard"):
    for e in res["details"][k][:40]:
        print("   ", k, e)
print("interfaces (board x = local + 27):")
for f in sorted(blk.ifaces, key=lambda d: d["x"]):
    if f["side"] == "N":
        print(f"   {f['net']:24s} {f['x'] + 27:7.2f} {f['layer']}")
if "--render" in sys.argv:
    bl.render(path, os.path.join(HERE, "mcuif.png"), layers=("F.Cu", "B.Cu", "F.SilkS", "F.Fab", "Dwgs.User"), tmpdir=SCR)
    bl.render(path, os.path.join(HERE, "mcuif_detail.png"), layers=("F.Cu", "B.Cu", "F.Fab", "B.Fab"),
              crop=(40.0, 0.0, 64.0, 12.5), tmpdir=SCR)
