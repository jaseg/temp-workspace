#!/usr/bin/env python3
"""input_stage layout fragment (KiCad 7, pcbnew scripting).

SIG_IN SMA edge launch -> VIN 50R microstrip -> K101 HFD3 (both poles, 2 x 100R 0603) 50R termination
-> 5:1 compensated divider (Ctop 1.5p / Cbot 3.3p, Rg 10R) -> U101 BUF802 (RGT VQFN-16) with
U102 OPA197 differential-integrator servo (3 x 300k / 100k alpha string, Cint 470p, Rf1 10k,
Rf2 22.1k + RV 50k, Rofs 14.3k from VOFS) -> BUF_OUT_S edge pad (sampler 10R) and
49.9R + 0R -> BUF_OUT_T 50R microstrip.  Values: sim/input/RESULT.md, as drawn in kicad/gen/gen_input.py.

Run: python3 gen_input_stage.py   (writes input_stage.kicad_pcb next to this script, prints checks)
"""
import math, os, re, sys
import pcbnew
from pcbnew import FromMM, ToMM, VECTOR2I

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "input_stage.kicad_pcb")
LIB = "/usr/share/kicad/footprints"

# ----------------------------------------------------------------------------- stack-up / geometry
# JLC04161H-3313 (JLCPCB 4-layer 1.6 mm): L1 35 um | 3313 prepreg 0.0994 mm er 4.1 | L2 15.2 um |
# core 1.265 mm er 4.6 | L3 15.2 um | 3313 prepreg 0.0994 mm | L4 35 um.  Solder mask ~15 um er 3.8.
H_PP, ER_PP, T_CU = 0.0994, 4.1, 0.035


def microstrip(w, h=H_PP, t=T_CU, er=ER_PP):
    """Hammerstad-Jensen microstrip (1980) incl. their strip-thickness correction, uncovered
    (solder mask lowers Z0 by roughly 1-2 R on this thin prepreg; not modelled) -> (Z0, er_eff)."""
    u, T = w / h, t / h
    du1 = T / math.pi * math.log(1 + 4 * math.e / (T / math.tanh(math.sqrt(6.517 * u)) ** 2))
    dur = 0.5 * (1 + 1 / math.cosh(math.sqrt(er - 1))) * du1

    def z0(u):
        f = 6 + (2 * math.pi - 6) * math.exp(-(30.666 / u) ** 0.7528)
        return 60 * math.log(f / u + math.sqrt(1 + 4 / u ** 2))

    def ee(u):
        a = 1 + math.log((u ** 4 + (u / 52) ** 2) / (u ** 4 + 0.432)) / 49 + math.log(1 + (u / 18.1) ** 3) / 18.7
        b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
        return (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / u) ** (-a * b)
    u1, ur = u + du1, u + dur
    e = ee(ur) * (z0(u1) / z0(ur)) ** 2
    return z0(ur) / math.sqrt(ee(ur)), e


def width_for(z):
    lo, hi = 0.02, 1.0
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if microstrip(m)[0] > z else (lo, m)
    return m


W50_EXACT = width_for(50.0)
W50 = round(W50_EXACT - 0.005, 2)          # 0.17 mm: ~50.8 R bare, ~49-50 R under mask
Z50, EE50 = microstrip(W50)
PS_MM = math.sqrt(EE50) * 3.3356           # ps per mm
W_HZ = 0.15                                 # high-impedance node traces (GA, IN)
W_SIG = 0.2
W_PWR = 0.35

# ----------------------------------------------------------------------------- board coordinates (mm)
Y0 = 14.0          # HF row (VIN, GA, IN, OUT)
XC = 13.4          # K101 COM column (pins 4 / 9)
XU = XC + 8.5      # U101 centre x
YU = Y0 + 0.25     # U101 centre y (pins 2 and 11 on Y0)
W, H = XU + 3.4, 24.5

board = pcbnew.BOARD()
board.SetCopperLayerCount(4)
ds = board.GetDesignSettings()
ds.SetBoardThickness(FromMM(1.6))
for lay, typ in ((pcbnew.In1_Cu, pcbnew.LT_POWER), (pcbnew.In2_Cu, pcbnew.LT_POWER)):
    board.SetLayerType(lay, typ)
try:
    nc = ds.m_NetSettings.m_DefaultNetClass
    nc.SetClearance(FromMM(0.1)); nc.SetTrackWidth(FromMM(W_SIG)); nc.SetViaDiameter(FromMM(0.5))
    nc.SetViaDrill(FromMM(0.25))
except Exception as e:  # pragma: no cover
    print("netclass defaults not set:", e)
ds.m_MinClearance = FromMM(0.1)
ds.m_TrackMinWidth = FromMM(0.1)
ds.m_ViasMinSize = FromMM(0.45)
ds.m_MinThroughDrill = FromMM(0.2)
ds.m_CopperEdgeClearance = FromMM(0.1)

NETS = {}


def N(name):
    if name not in NETS:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        NETS[name] = ni
    return NETS[name]


def P(x, y):
    return VECTOR2I(FromMM(x), FromMM(y))


FPS = {}


def place(lib, name, ref, val, x, y, rot=0, side="F", nets=None, critical=False):
    fp = pcbnew.FootprintLoad(os.path.join(LIB, lib + ".pretty"), name)
    assert fp is not None, name
    fp.SetReference(ref)
    fp.SetValue(val)
    board.Add(fp)
    if side == "B":
        fp.Flip(fp.GetPosition(), False)
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(P(x, y))
    for pad in fp.Pads():
        n = (nets or {}).get(pad.GetNumber())
        if n:
            pad.SetNet(N(n))
    fp.Reference().SetTextSize(VECTOR2I(FromMM(0.5), FromMM(0.5)))
    fp.Reference().SetTextThickness(FromMM(0.08))
    fp.Reference().SetVisible(False)          # dense fragment: refs on F.Fab only
    fp.Value().SetVisible(False)
    for g in fp.GraphicalItems():               # library ${REFERENCE} fab text: small
        if isinstance(g, pcbnew.FP_TEXT):
            g.SetTextSize(VECTOR2I(FromMM(0.3), FromMM(0.3))); g.SetTextThickness(FromMM(0.05))
    fp.critical = critical
    FPS[ref] = fp
    return fp


def R(ref, val, x, y, rot=0, n1=None, n2=None, size="0402", side="F", critical=False, cap=False):
    lib = "Capacitor_SMD" if cap else "Resistor_SMD"
    m = {"0402": "1005", "0603": "1608", "0805": "2012"}[size]
    name = f"{'C' if cap else 'R'}_{size}_{m}Metric"
    return place(lib, name, ref, val, x, y, rot, side, {"1": n1, "2": n2}, critical)


def C(ref, val, x, y, rot=0, n1=None, n2=None, size="0402", side="F", critical=False):
    return R(ref, val, x, y, rot, n1, n2, size, side, critical, cap=True)


def pad(ref, num):
    for p in FPS[ref].Pads():
        if p.GetNumber() == str(num):
            v = p.GetPosition()
            return (ToMM(v.x), ToMM(v.y))
    raise KeyError((ref, num))


def track(pts, w, net, layer=pcbnew.F_Cu):
    pts = [pad(*p) if isinstance(p[0], str) else p for p in pts]
    out = []
    for a, b in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(P(*a)); t.SetEnd(P(*b))
        t.SetWidth(FromMM(w)); t.SetLayer(layer); t.SetNet(N(net))
        board.Add(t)
        out.append(t)
    return out


def via(x, y, net, d=0.5, drill=0.25):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(P(x, y)); v.SetWidth(FromMM(d)); v.SetDrill(FromMM(drill))
    v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(N(net))
    board.Add(v)
    return v


def gvia(x, y, d=0.5, drill=0.25):
    return via(x, y, "GND", d, drill)


def text(s, x, y, size=0.6, layer=pcbnew.F_SilkS, rot=0, just=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s); t.SetPosition(P(x, y)); t.SetLayer(layer)
    t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size))); t.SetTextThickness(FromMM(size * 0.15))
    t.SetTextAngleDegrees(rot)
    if just:
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT if just < 0 else pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    board.Add(t)
    return t


def poly(layer, pts, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_POLY)
    s.SetPolyPoints([P(*p) for p in pts])
    s.SetLayer(layer); s.SetWidth(FromMM(width)); s.SetFilled(False)
    board.Add(s)


def line(layer, a, b, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(P(*a)); s.SetEnd(P(*b)); s.SetLayer(layer); s.SetWidth(FromMM(width))
    board.Add(s)


def zone(layers, net, pts, clearance=0.25, priority=0, rule=False):
    z = pcbnew.ZONE(board)
    ls = pcbnew.LSET()
    for l in layers:
        ls.AddLayer(l)
    z.SetLayerSet(ls)
    ol = z.Outline(); ol.NewOutline()
    for x, y in pts:
        ol.Append(FromMM(x), FromMM(y))
    if rule:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowVias(False); z.SetDoNotAllowTracks(False); z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
    else:
        z.SetNet(N(net))
        z.SetLocalClearance(FromMM(clearance))
        z.SetMinThickness(FromMM(0.2))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetAssignedPriority(priority)
    board.Add(z)
    return z


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


# ----------------------------------------------------------------------------- custom footprints
def edge_pad(ref, net, x, y, w=0.5, h=0.4, label=None):
    """Interface pad (custom footprint): small SMD pad at the fragment edge, copper only."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("input_stage", "IF_PAD_%.1fx%.1f" % (w, h)))
    fp.SetReference(ref); fp.SetValue(net)
    fp.Reference().SetVisible(False); fp.Value().SetVisible(False)
    p = pcbnew.PAD(fp)
    p.SetNumber("1"); p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetSize(VECTOR2I(FromMM(w), FromMM(h)))
    ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.F_Mask)
    p.SetLayerSet(ls)
    fp.Add(p)
    board.Add(fp)
    fp.SetPosition(P(x, y))
    p.SetNet(N(net))
    fp.critical = False
    FPS[ref] = fp
    return fp


# ============================================================================= placement
# SIG_IN edge-launch SMA (Samtec SMA-J-P-H-ST-EM1): board edge at x = 0, centre pin on F.Cu along +x.
place("Connector_Coaxial", "SMA_Samtec_SMA-J-P-X-ST-EM1_EdgeMount", "J101", "SIG_IN", 2.1, Y0, 270,
      nets={"1": "VIN", "2": "GND"}, critical=True)
# K101 HFD3 on the BOTTOM side (the body would cover the HF parts otherwise); top side only sees the
# pins.  Rows horizontal: pins 1,3,4,5 at Y0-2.54, pins 12,10,9,8 at Y0+2.54, COM (4/9) at x = XC.
place("Relay_THT", "Relay_DPDT_Kemet_EC2", "K101", "HFD3/3", XC - 7.62, Y0 - 2.54, 270, side="B",
      nets={"1": "COIL_P", "12": "TERM_50", "4": "K_COM1", "9": "K_COM2", "5": "GND", "8": "GND"},
      critical=True)
# Termination: 2 x 100R 0603, one per pole, between the rows; VIN pad toward Ctop.
R("R101", "100", XC, Y0 - 1.05, 180, "VIN", "K_COM1", size="0603", critical=True)
R("R102", "100", XC, Y0 + 1.05, 180, "VIN", "K_COM2", size="0603", critical=True)
C("C101", "1.5p C0G 100V", XC + 2.45, Y0, 0, "VIN", "GA", critical=True)          # Ctop
C("C102", "3.3p C0G", XC + 3.35, Y0 + 1.0, 0, "GA", "GND", critical=True)        # Cbot
R("R104", "10", XC + 4.35, Y0, 0, "GA", "BUF_IN", critical=True)                # Rg
R("R105", "4.99M", XC + 4.85, Y0 + 1.55, 270, "BUF_IN", "IN_BIAS_MID", critical=True)
R("R106", "4.99M", XC + 5.85, Y0 + 1.55, 270, "IN_BIAS", "IN_BIAS_MID", critical=True)
U1N = {"1": "+5V", "2": "BUF_IN", "3": "IN_BIAS", "4": "IN_AUX", "5": "-5V", "6": "-5V", "7": "R_BIAS",
       "8": "-5V", "10": "-5V", "11": "BUF_OUT_S", "12": "+5V", "14": "CLL", "15": "CLH", "17": "GND"}
place("Package_DFN_QFN", "VQFN-16-1EP_3x3mm_P0.5mm_EP1.68x1.68mm", "U101", "BUF802IRGTR", XU, YU, 0,
      nets=U1N, critical=True)
for p in FPS["U101"].Pads():          # unnamed paste pads of the EP belong to GND too
    if p.GetNumber() == "":
        p.SetNet(N("GND"))
# output: OUT -> edge pad (sampler 10R), 49.9R + 0R -> BUF_OUT_T
edge_pad("IF1", "BUF_OUT_S", W - 0.35, Y0, 0.5, 0.4)
R("R112", "49.9", XU + 2.85, Y0 + 0.95, 270, "BUF_OUT_S", "RT_MID", critical=True)
R("R113", "0", XU + 2.85, Y0 + 2.85, 270, "RT_MID", "BUF_OUT_T", critical=True)
C("C117", "100n", XU + 2.85, Y0 - 1.2, 90, "+5V", "GND", critical=True)            # VSO+ (pin 12)
C("C118", "100n", XU + 2.15, Y0 + 2.45, 270, "-5V", "GND", side="B")             # VSO- (pin 10), bottom
C("C108", "100n", XU - 2.3, Y0 - 2.85, 90, "+5V", "GND", critical=True)             # VS+ (pin 1)
C("C110", "100n", XU - 0.5, Y0 + 4.0, 270, "-5V", "GND")                          # VS- pins 5/6
C("C111", "100n", XU + 1.4, Y0 + 4.0, 270, "-5V", "GND")                         # VS- pin 8
R("R107", "17.8k", XU + 0.45, Y0 + 3.9, 270, "R_BIAS", "-5V")                      # R_Bias
C("C107", "100p C0G", XU - 1.7, Y0 + 3.5, 270, "IN_AUX", "GND")                   # Caux
R("R121", "1k", XU - 2.9, Y0 + 2.99, 0, "OPA_OUT", "IN_AUX")                      # Raux
# clamp dividers: CLH = +1.5 V from +2V5, CLL = -1.5 V from -2V5
C("C103", "1u", XU - 0.8, Y0 - 3.7, 0, "GND", "CLH")
C("C104", "1u", XU + 1.3, Y0 - 3.7, 0, "CLL", "GND")
R("R109", "1.5k", XU - 1.3, Y0 - 5.4, 90, "CLH", "GND")
R("R108", "1k", XU - 0.25, Y0 - 5.4, 90, "CLH", "+2V5")
R("R110", "1k", XU + 0.8, Y0 - 5.4, 90, "CLL", "-2V5")
R("R111", "1.5k", XU + 1.85, Y0 - 5.4, 90, "CLL", "GND")
# alpha string: first 300k on the VIN line between the relay rows
R("R114", "300k 0.1%", 8.3, Y0 - 0.85, 90, "VIN", "S1")
R("R115", "300k 0.1%", 8.3, 9.4, 90, "S1", "S2")
R("R116", "300k 0.1%", 8.3, 7.9, 90, "S2", "TAP")
R("R117", "100k 0.1%", 7.0, 6.95, 0, "GND", "TAP")
C("C105", "18p C0G", 8.3, 5.8, 90, "TAP", "GND")
# OPA197 servo
place("Package_TO_SOT_SMD", "SOT-23-5", "U102", "OPA197IDBVR", 12.0, 6.0, 0,
      nets={"1": "OPA_OUT", "2": "-5V", "3": "TAP", "4": "FB", "5": "+5V"})
C("C106", "470p C0G", 12.0, 3.4, 0, "OPA_OUT", "FB")                                 # Cint
C("C112", "100n", 13.2, 3.1, 0, "+5V", "GND", side="B")                              # OPA V+
C("C113", "100n", 9.9, 4.9, 90, "-5V", "GND", side="B")                              # OPA V-
R("R118", "10.0k 0.1%", 15.2, 5.0, 0, "FB", "BUF_OUT_S")                            # Rf1
R("R119", "14.3k 0.1%", 15.2, 6.2, 0, "FB", "VOFS")                                 # Rofs
R("R120", "22.1k 0.1%", 15.2, 3.8, 0, "FB", "RF2_MID")                              # Rf2
place("Potentiometer_SMD", "Potentiometer_Bourns_3314J_Vertical", "RV101", "50k", 18.6, 4.0, 0,
      nets={"1": "RF2_MID", "2": "GND", "3": "GND"})
# test points
place("TestPoint", "TestPoint_Pad_D1.0mm", "TP101", "CLH", 17.3, 8.9, nets={"1": "CLH"})
place("TestPoint", "TestPoint_Pad_D1.0mm", "TP103", "SERVO", 10.0, 2.4, nets={"1": "OPA_OUT"})
# relay coil: VBUS -> 39R 0805 -> coil+ (pin 1); coil- (pin 12) -> TERM_50 (low-side switch on mcu_if)
R("R103", "39", 10.0, 20.4, 0, "COIL_P", "VBUS", size="0805")
# headers at the fragment edges (1.27 mm pitch)
place("Connector_PinHeader_1.27mm", "PinHeader_1x05_P1.27mm_Vertical", "J2", "PWR_TOP", W - 1.1, 1.2, 0,
      nets={"1": "GND", "2": "+5V", "3": "+2V5", "4": "-2V5", "5": "VOFS"})
place("Connector_PinHeader_1.27mm", "PinHeader_1x04_P1.27mm_Vertical", "J3", "PWR_BOT", 1.2, H - 1.2, 90,
      nets={"1": "GND", "2": "-5V", "3": "TERM_50", "4": "VBUS"})
C("C115", "10u", 14.0, 1.3, 0, "+5V", "GND", size="0805")
C("C116", "10u", 13.0, H - 1.4, 0, "-5V", "GND", size="0805")

# ============================================================================= routing
# --- VIN: SMA centre pin -> 50R microstrip between the relay rows -> Ctop pad
x_pad_end = 3.7
track([(1.9, Y0), (x_pad_end, Y0)], 1.0, "VIN")                    # on the SMA pin pad
track([(x_pad_end, Y0), (x_pad_end + 0.5, Y0)], 0.5, "VIN")        # 0.5 mm taper step
vin_line = track([(x_pad_end + 0.5, Y0), ("C101", 1)], W50, "VIN")
# termination taps and relay COM connections
for r_, pin, sgn in (("R101", 4, -1), ("R102", 9, 1)):
    track([(XC + 0.825, Y0), (r_, 1)], 0.3, "VIN")
    track([(r_, 2), ("K101", pin)], 0.3, "K_COM1" if pin == 4 else "K_COM2")
# alpha string tap
track([(8.3, Y0), ("R114", 1)], 0.2, "VIN")
track([("R114", 2), (8.3, 11.0), ("R115", 1)], W_SIG, "S1")
track([("R115", 2), ("R116", 1)], W_SIG, "S2")
track([("R116", 2), (8.3, 6.95), ("R117", 2)], W_SIG, "TAP")
track([(8.3, 6.95), ("C105", 1)], W_SIG, "TAP")
track([(8.3, 6.95), ("U102", 3)], W_SIG, "TAP")
track([("R117", 1), (6.0, 6.95)], 0.3, "GND"); gvia(6.0, 6.95)
track([("C105", 2), (8.3, 4.6)], 0.3, "GND"); gvia(8.3, 4.6)

# --- GA / IN (high impedance, thin, In1/In2 cut out below)
track([("C101", 2), ("R104", 1)], W_HZ, "GA")
track([(pad("C101", 2)[0] + 0.1, Y0), (pad("C101", 2)[0] + 0.1, Y0 + 0.5), ("C102", 1)], W_HZ, "GA")
track([("C102", 2), (pad("C102", 2)[0], Y0 + 1.75)], 0.25, "GND"); gvia(pad("C102", 2)[0], Y0 + 1.8)
track([("R104", 2), ("U101", 2)], W_HZ, "BUF_IN")
track([(pad("R105", 1)[0], Y0), ("R105", 1)], W_HZ, "BUF_IN")
track([("R105", 2), ("R106", 2)], W_HZ, "IN_BIAS_MID")
track([("R106", 1), (pad("R106", 1)[0] + 0.3, YU + 0.25), ("U101", 3)], W_HZ, "IN_BIAS")

# --- U101 supplies
p1 = pad("U101", 1)
track([p1, (p1[0] - 0.55, p1[1]), (XU - 2.3, Y0 - 1.0), ("C108", 1)], 0.25, "+5V")
via(XU - 2.95, pad("C108", 1)[1], "+5V"); track([("C108", 1), (XU - 2.95, pad("C108", 1)[1])], 0.3, "+5V")
track([("C108", 2), (XU - 2.3, Y0 - 3.85)], 0.3, "GND"); gvia(XU - 2.3, Y0 - 3.9)
p12 = pad("U101", 12)
track([p12, (XU + 2.1, p12[1]), (XU + 2.4, Y0 - 0.69), ("C117", 1)], 0.25, "+5V")
via(XU + 1.7, Y0 - 1.65, "+5V"); track([(XU + 2.1, p12[1]), (XU + 1.7, Y0 - 1.65)], 0.25, "+5V")
track([("C117", 2), (XU + 2.85, Y0 - 2.4)], 0.3, "GND"); gvia(XU + 2.85, Y0 - 2.45)
p10 = pad("U101", 10)
track([p10, (XU + 2.15, p10[1]), (XU + 2.15, Y0 + 1.6)], 0.25, "-5V"); via(XU + 2.15, Y0 + 1.6, "-5V")
track([(XU + 2.15, Y0 + 1.6), ("C118", 1)], 0.3, "-5V", pcbnew.B_Cu)
track([("C118", 2), (XU + 2.1, Y0 + 4.2)], 0.3, "GND", pcbnew.B_Cu); gvia(XU + 2.1, Y0 + 4.2)
p5, p6, p7, p8 = (pad("U101", n) for n in (5, 6, 7, 8))
track([p5, (p5[0], p5[1] + 0.65), (p6[0], p6[1] + 0.65), p6], 0.2, "-5V")
track([((p5[0] + p6[0]) / 2, p5[1] + 0.65), ("C110", 1)], 0.25, "-5V")
via(XU - 1.2, Y0 + 2.3, "-5V"); track([(p5[0], p5[1] + 0.65), (XU - 1.2, Y0 + 2.3)], 0.25, "-5V")
track([("C110", 2), (XU - 0.5, Y0 + 5.2)], 0.3, "GND"); gvia(XU - 0.5, Y0 + 5.25)
track([p7, (p7[0], p7[1] + 0.9), ("R107", 1)], 0.2, "R_BIAS")
track([p8, (p8[0] + 0.35, p8[1] + 0.6), (XU + 1.25, Y0 + 2.75), ("C111", 1)], 0.25, "-5V")
via(XU + 1.25, Y0 + 2.75, "-5V")
track([("R107", 2), (pad("R107", 2)[0], Y0 + 5.05)], 0.25, "-5V"); via(pad("R107", 2)[0], Y0 + 5.1, "-5V")
track([("C111", 2), (XU + 1.4, Y0 + 5.3)], 0.3, "GND"); gvia(XU + 1.4, Y0 + 5.35)
# EP thermal / ground vias (2 x 2 inside the 1.68 mm pad)
for dx in (-0.42, 0.42):
    for dy in (-0.42, 0.42):
        gvia(XU + dx, YU + dy, 0.45, 0.2)
# In_Aux, Raux, Caux
p4 = pad("U101", 4)
track([p4, (XU - 1.7, p4[1]), ("C107", 1)], W_SIG, "IN_AUX")
track([(XU - 1.7, pad("R121", 2)[1]), ("R121", 2)], W_SIG, "IN_AUX")
track([("C107", 2), (XU - 1.7, Y0 + 4.6)], 0.3, "GND"); gvia(XU - 1.7, Y0 + 4.65)
# CLH / CLL
p15, p14 = pad("U101", 15), pad("U101", 14)
track([p15, (p15[0], Y0 - 2.9), (pad("C103", 2)[0], Y0 - 3.3), ("C103", 2)], W_SIG, "CLH")
track([("C103", 2), (pad("R108", 1)[0], Y0 - 4.3), ("R108", 1)], W_SIG, "CLH")
track([(pad("R108", 1)[0], Y0 - 4.3), (pad("R109", 1)[0], Y0 - 4.3), ("R109", 1)], W_SIG, "CLH")
track([("R109", 1), ("TP101", 1)], W_SIG, "CLH")
track([p14, (p14[0], Y0 - 2.9), (pad("C104", 1)[0], Y0 - 3.3), ("C104", 1)], W_SIG, "CLL")
track([("C104", 1), (pad("R110", 1)[0], Y0 - 4.3), ("R110", 1)], W_SIG, "CLL")
track([(pad("R110", 1)[0], Y0 - 4.3), (pad("R111", 1)[0], Y0 - 4.3), ("R111", 1)], W_SIG, "CLL")
track([("C103", 1), (XU - 2.3, Y0 - 3.9)], 0.3, "GND")
track([("C104", 2), (pad("C104", 2)[0] + 0.55, Y0 - 3.7)], 0.3, "GND"); gvia(pad("C104", 2)[0] + 0.6, Y0 - 3.7)
track([("R109", 2), (pad("R109", 2)[0], 7.9)], 0.3, "GND"); gvia(pad("R109", 2)[0], 7.85)
track([("R111", 2), (pad("R111", 2)[0], 7.9)], 0.3, "GND"); gvia(pad("R111", 2)[0], 7.85)
via(pad("R108", 2)[0], 7.85, "+2V5"); track([("R108", 2), (pad("R108", 2)[0], 7.85)], 0.3, "+2V5")
via(pad("R110", 2)[0], 7.85, "-2V5"); track([("R110", 2), (pad("R110", 2)[0], 7.85)], 0.3, "-2V5")

# --- output: OUT pin -> edge pad (BUF_OUT_S), 49.9R, 0R, BUF_OUT_T microstrip to the bottom edge
p11 = pad("U101", 11)
out_s = track([p11, ("IF1", 1)], 0.3, "BUF_OUT_S")
track([(pad("R112", 1)[0], Y0), ("R112", 1)], 0.3, "BUF_OUT_S")
track([("R112", 2), ("R113", 1)], 0.3, "RT_MID")
xt = pad("R113", 2)[0]
out_t = track([("R113", 2), (xt, H - 0.35)], W50, "BUF_OUT_T")
edge_pad("IF2", "BUF_OUT_T", xt, H - 0.35, 0.4, 0.5)
# Rf1 sense from the OUT node: via next to the pin, B.Cu to R118 at the servo
xs = XU + 2.35
via(xs, Y0, "BUF_OUT_S", 0.45, 0.2)
track([(xs, Y0), (xs, 10.9), (17.1, 10.9), (16.4, 10.0), (16.4, 5.0)], W_SIG, "BUF_OUT_S", pcbnew.B_Cu)
via(16.4, 5.0, "BUF_OUT_S", 0.45, 0.2); track([(16.4, 5.0), ("R118", 2)], W_SIG, "BUF_OUT_S")

# --- servo
track([("U102", 4), (14.0, pad("U102", 4)[1]), (14.0, 3.4), ("C106", 2)], W_SIG, "FB")
for r_ in ("R118", "R119", "R120"):
    track([(14.0, pad(r_, 1)[1]), (r_, 1)], W_SIG, "FB")
track([("U102", 1), (pad("U102", 1)[0], 3.4), ("C106", 1)], W_SIG, "OPA_OUT")
track([(pad("U102", 1)[0], 3.4), (pad("U102", 1)[0], 2.4), ("TP103", 1)], W_SIG, "OPA_OUT")
track([("R120", 2), (16.2, pad("R120", 2)[1]), ("RV101", 1)], W_SIG, "RF2_MID")
track([("RV101", 3), (pad("RV101", 3)[0], 4.6), (pad("RV101", 2)[0] + 0.6, 4.6), ("RV101", 2)], 0.3, "GND")
gvia(pad("RV101", 2)[0] + 1.6, pad("RV101", 2)[1])
track([("RV101", 2), (pad("RV101", 2)[0] + 1.6, pad("RV101", 2)[1])], 0.3, "GND")
# OPA supplies (decoupling caps on B.Cu under the vias)
via(13.2, 4.2, "+5V"); track([("U102", 5), (13.2, 4.2)], 0.3, "+5V")
track([(13.2, 4.2), ("C112", 1)], 0.3, "+5V", pcbnew.B_Cu)
track([("C112", 2), (pad("C112", 2)[0], 2.3)], 0.3, "GND", pcbnew.B_Cu); gvia(pad("C112", 2)[0], 2.3)
via(9.9, 6.0, "-5V"); track([("U102", 2), (9.9, 6.0)], 0.3, "-5V")
track([(9.9, 6.0), ("C113", 1)], 0.3, "-5V", pcbnew.B_Cu)
track([("C113", 2), (9.9, 3.7)], 0.3, "GND", pcbnew.B_Cu); gvia(9.9, 3.65)
# OPA_OUT -> Raux: down the channel between NC (10.86) and COM (13.4) columns on B.Cu
via(11.2, 3.4, "OPA_OUT"); track([(pad("U102", 1)[0], 3.4), (11.2, 3.4)], W_SIG, "OPA_OUT")
track([(11.2, 3.4), (12.13, 4.3), (12.13, 18.0), (17.0, 18.0)], W_SIG, "OPA_OUT", pcbnew.B_Cu)
via(17.0, 18.0, "OPA_OUT", 0.45, 0.2)
track([(17.0, 18.0), ("R121", 1)], W_SIG, "OPA_OUT")
# OPA V- from the -5V plane region (lower half of In2): B.Cu channel x = 9.3
via(8.8, 19.0, "-5V")
track([(9.9, 6.0), (8.8, 7.1), (8.8, 19.0)], 0.3, "-5V", pcbnew.B_Cu)

# --- relay coil and TERM_50
k1, k12 = pad("K101", 1), pad("K101", 12)
track([k1, (7.2, k1[1] + 0.9), (7.2, 20.4), (7.7, 20.4)], 0.3, "COIL_P", pcbnew.B_Cu)
via(7.7, 20.4, "COIL_P"); track([(7.7, 20.4), ("R103", 1)], 0.3, "COIL_P")
track([("R103", 2), (pad("R103", 2)[0], 21.9), (pad("J3", 4)[0] + 0.6, 21.9), ("J3", 4)], 0.3, "VBUS")
track([k12, (k12[0], 18.5), (pad("J3", 3)[0], 20.5), ("J3", 3)], 0.3, "TERM_50")
# --- headers
track([("J3", 2), (pad("J3", 2)[0], H - 2.45)], 0.35, "-5V"); via(pad("J3", 2)[0], H - 2.5, "-5V")
track([("C116", 1), (pad("C116", 1)[0], H - 3.0)], 0.4, "-5V"); via(pad("C116", 1)[0], H - 3.0, "-5V")
track([("C116", 2), (pad("C116", 2)[0] + 0.9, pad("C116", 2)[1])], 0.4, "GND"); gvia(pad("C116", 2)[0] + 1.0, pad("C116", 2)[1])
track([("J2", 2), (pad("J2", 2)[0] - 0.8, pad("J2", 2)[1])], 0.35, "+5V"); via(pad("J2", 2)[0] - 0.85, pad("J2", 2)[1], "+5V")
track([("C115", 1), (pad("C115", 1)[0], 2.6)], 0.4, "+5V"); via(pad("C115", 1)[0], 2.65, "+5V")
track([("C115", 2), (pad("C115", 2)[0] + 0.9, pad("C115", 2)[1])], 0.4, "GND"); gvia(pad("C115", 2)[0] + 1.0, pad("C115", 2)[1])
# +2V5 / -2V5 / VOFS from J2 on B.Cu along the top edge
j3, j4, j5 = pad("J2", 3), pad("J2", 4), pad("J2", 5)
via(j3[0] - 0.9, j3[1], "+2V5"); track([j3, (j3[0] - 0.9, j3[1])], 0.3, "+2V5")
track([(j3[0] - 0.9, j3[1]), (pad("R108", 2)[0], j3[1]), (pad("R108", 2)[0], 7.85)], 0.3, "+2V5", pcbnew.B_Cu)
via(j4[0] - 0.9, j4[1], "-2V5"); track([j4, (j4[0] - 0.9, j4[1])], 0.3, "-2V5")
track([(j4[0] - 0.9, j4[1]), (pad("R110", 2)[0], j4[1]), (pad("R110", 2)[0], 7.85)], 0.3, "-2V5", pcbnew.B_Cu)
track([j5, (j5[0] - 0.7, j5[1] + 0.7), (j5[0] - 0.7, 7.3), (16.2, 7.3), (pad("R119", 2)[0], 6.8), ("R119", 2)],
      W_SIG, "VOFS")
gvia(pad("J2", 1)[0] - 0.85, pad("J2", 1)[1]); track([("J2", 1), (pad("J2", 1)[0] - 0.8, pad("J2", 1)[1])], 0.35, "GND")
gvia(pad("J3", 1)[0], H - 2.3); track([("J3", 1), (pad("J3", 1)[0], H - 2.3)], 0.35, "GND")

# --- GND stitching along VIN and BUF_OUT_T, around the SMA and the board
stitch = [(x, Y0 + s * 1.2) for x in (4.6, 6.4, 9.7, 11.1) for s in (-1, 1)]
stitch += [(xt - 0.85, y) for y in (19.2, 20.7, 22.2, 23.6)]
stitch += [(xt + 0.5, y) for y in (20.0, 21.7, 23.0)]
stitch += [(3.2, Y0 - 4.0), (3.2, Y0 + 4.0), (1.0, Y0 - 4.0), (1.0, Y0 + 4.0), (4.4, Y0 - 2.9), (4.4, Y0 + 2.9)]
for x, y in stitch:
    gvia(x, y)

# ============================================================================= zones
outline = rect(0, 0, W, H)
poly(pcbnew.Edge_Cuts, outline, 0.1)
# low-capacitance cut-out under Ctop pad 2, GA, Cbot pad 1, Rg, IN, Rb1 pad 1, U101 pin 2 (In1 + In2 + F.Cu pour)
cut_hz = rect(XC + 2.62, Y0 - 0.6, XU - 1.0, Y0 + 0.95)
zone([pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.F_Cu, pcbnew.B_Cu], None, cut_hz, rule=True)
# SMA centre pad: remove In1/In2 under the 1.27 mm pin pad (reference = B.Cu / connector body)
zone([pcbnew.In1_Cu, pcbnew.In2_Cu], None, rect(0, Y0 - 0.9, x_pad_end + 0.2, Y0 + 0.9), rule=True)
zone([pcbnew.In1_Cu], "GND", outline, clearance=0.2)
zone([pcbnew.In2_Cu], "+5V", rect(0, 0, W, Y0 - 0.2), clearance=0.25)
zone([pcbnew.In2_Cu], "-5V", rect(0, Y0 + 0.2, W, H), clearance=0.25)
zone([pcbnew.F_Cu], "GND", outline, clearance=0.3)
zone([pcbnew.B_Cu], "GND", outline, clearance=0.25)

# ============================================================================= silkscreen / fab
text("SIG_IN", 1.0, Y0 - 5.0, 0.7, just=-1)
text("input_stage", 0.5, 4.3, 0.7, just=-1)
text("K101 HFD3 on B side", XC - 3.8, Y0 + 3.7, 0.5)
text("BUF_OUT_S -> right edge (10R <= 3 mm)", W - 0.3, Y0 + 6.0, 0.4, just=1)
text("S>", W - 0.05, Y0 - 0.55, 0.35, just=1)
text("sampler 10R", W - 0.1, Y0 - 1.5, 0.45, just=1) if False else None
text("BUF_OUT_T 50R", xt - 0.3, H - 1.6, 0.5, just=1)
text("GND -5V TERM_50 VBUS", 0.5, H - 2.3, 0.45, just=-1)
for i_, n_ in enumerate(("GND", "+5V", "+2V5", "-2V5", "VOFS")):
    text(n_, W - 1.9, 1.2 + 1.27 * i_, 0.4, just=1)
text("CLH", 17.3, 10.0, 0.45); text("SERVO", 10.0, 1.2, 0.45)
for ref, fp in ([] if True else FPS.items()):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(ref); t.SetLayer(pcbnew.B_Fab if fp.IsFlipped() else pcbnew.F_Fab)
    t.SetPosition(fp.GetPosition()); t.SetTextSize(VECTOR2I(FromMM(0.3), FromMM(0.3)))
    t.SetTextThickness(FromMM(0.05))
    board.Add(t)
text("4L JLC04161H-3313: L1 sig | 0.0994 PP | L2 GND | 1.265 core | L3 +5V/-5V | 0.0994 PP | L4 GND+slow",
     0.3, H + 1.0, 0.5, pcbnew.F_Fab, just=-1)
text("50R microstrip w=%.2f mm (Z0 %.1f R, %.2f ps/mm)" % (W50, Z50, PS_MM), 0.3, H + 1.8, 0.5,
     pcbnew.F_Fab, just=-1)

# ============================================================================= fill, checks


def tlen(tracks):
    return sum(ToMM(t.GetLength()) for t in tracks)


print("Stack-up: L1-L2 prepreg %.4f mm er %.1f, Cu %.3f mm" % (H_PP, ER_PP, T_CU))
print("50R microstrip: exact w = %.3f mm, used %.2f mm -> Z0 %.1f R, er_eff %.2f, %.2f ps/mm"
      % (W50_EXACT, W50, Z50, EE50, PS_MM))
print("\n%-34s %10s %10s %10s %10s" % ("line", "int. mm", "int. ps", "act. mm", "act. ps"))
# VIN: SMA pin pad end -> centroid of the two termination taps (RESULT: 6 mm / 50R)
vin_term = XC + 0.825 - x_pad_end
vin_ctop = pad("C101", 1)[0] - x_pad_end
rows = [("VIN: SMA pad -> termination taps", 6.0, vin_term),
        ("VIN: termination -> Ctop pad (stub)", 0.0, vin_ctop - vin_term),
        ("BUF_OUT_S: OUT pin -> edge pad", 1.5, tlen(out_s)),
        ("BUF_OUT_T: 0R -> edge (50R line)", float("nan"), tlen(out_t))]
for name, imm, amm in rows:
    print("%-34s %10.2f %10.1f %10.2f %10.1f" % (name, imm, imm * PS_MM, amm, amm * PS_MM))
stub = math.dist(pad("R101", 1), (XC + 0.825, Y0)) + 1.6 + math.dist(pad("R101", 2), pad("K101", 4))
print("termination stub VIN -> R -> K101 COM pin: %.1f mm per pole (RESULT asks < 2 mm, see README)" % stub)

# courtyard overlaps (same side) for critical parts
probs = 0
crit = [f for f in FPS.values() if f.critical]
for f in FPS.values():
    f.BuildCourtyardCaches()
for i, a in enumerate(crit):
    for b in list(FPS.values()):
        if b is a or (b.critical and list(FPS.values()).index(b) < list(FPS.values()).index(a) and b in crit):
            continue
        if a.IsFlipped() != b.IsFlipped():
            continue
        lay = pcbnew.B_CrtYd if a.IsFlipped() else pcbnew.F_CrtYd
        ca, cb = a.GetCourtyard(lay), b.GetCourtyard(lay)
        if ca.OutlineCount() == 0 or cb.OutlineCount() == 0:
            continue
        x = pcbnew.SHAPE_POLY_SET(ca)
        x.BooleanIntersection(cb, pcbnew.SHAPE_POLY_SET.PM_FAST)
        if x.OutlineCount() and x.Area() > FromMM(0.01) * FromMM(0.01):
            print("COURTYARD OVERLAP %s / %s" % (a.GetReference(), b.GetReference())); probs += 1

# copper clearance (tracks, vias, pads; zones are filled with their own clearance)
items = []
for t in board.GetTracks():
    for lay in ([t.GetLayer()] if t.Type() == pcbnew.PCB_TRACE_T else
                [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]):
        items.append((lay, t))
for f in FPS.values():
    for p in f.Pads():
        for lay in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
            if p.IsOnLayer(lay) and (p.GetAttribute() != pcbnew.PAD_ATTRIB_PTH or lay in (pcbnew.F_Cu, pcbnew.B_Cu)):
                items.append((lay, p))
CL = FromMM(0.1)
shapes = [(lay, it, it.GetEffectiveShape(lay), it.GetBoundingBox()) for lay, it in items]
viol = []
for i in range(len(shapes)):
    la, a, sa, ba = shapes[i]
    for j in range(i + 1, len(shapes)):
        lb, b, sb, bb = shapes[j]
        if la != lb or a.GetNetCode() == b.GetNetCode() and a.GetNetCode() > 0:
            continue
        if a.GetParent() is not None and b.GetParent() is not None and isinstance(a, pcbnew.PAD) \
                and isinstance(b, pcbnew.PAD) and a.GetParent() == b.GetParent() and a.GetNetCode() == 0:
            continue
        bx = pcbnew.BOX2I(ba.GetPosition(), ba.GetSize()); bx.Inflate(CL)
        if not bx.Intersects(bb):
            continue
        if sa.Collide(sb, CL - 1):
            viol.append((board.GetLayerName(la), a.GetNetname(), b.GetNetname(),
                         ToMM(a.GetPosition()), ToMM(b.GetPosition())))
for v in viol:
    print("CLEARANCE < 0.1 mm:", v)
# edge clearance of copper items
print("courtyard problems: %d, clearance violations: %d" % (probs, len(viol)))

board.Save(OUT)

# ----------------------------------------------------------------------------- stack-up into (setup)
STACKUP = """    (stackup
      (layer "F.SilkS" (type "Top Silk Screen"))
      (layer "F.Paste" (type "Top Solder Paste"))
      (layer "F.Mask" (type "Top Solder Mask") (thickness 0.015) (epsilon_r 3.8))
      (layer "F.Cu" (type "copper") (thickness 0.035))
      (layer "dielectric 1" (type "prepreg") (thickness 0.0994) (material "7628/3313 (JLC 3313)") (epsilon_r 4.1) (loss_tangent 0.02))
      (layer "In1.Cu" (type "copper") (thickness 0.0152))
      (layer "dielectric 2" (type "core") (thickness 1.265) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
      (layer "In2.Cu" (type "copper") (thickness 0.0152))
      (layer "dielectric 3" (type "prepreg") (thickness 0.0994) (material "7628/3313 (JLC 3313)") (epsilon_r 4.1) (loss_tangent 0.02))
      (layer "B.Cu" (type "copper") (thickness 0.035))
      (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.015) (epsilon_r 3.8))
      (layer "B.Paste" (type "Bottom Solder Paste"))
      (layer "B.SilkS" (type "Bottom Silk Screen"))
      (copper_finish "ENIG")
      (dielectric_constraints no)
    )
"""
s = open(OUT).read()
s = re.sub(r"\(setup\n", "(setup\n" + STACKUP, s, count=1)
s = s.replace('(1 "In1.Cu" power)', '(1 "In1.Cu" power "GND")').replace('(2 "In2.Cu" power)', '(2 "In2.Cu" power "PWR")')
open(OUT, "w").write(s)
b2 = pcbnew.LoadBoard(OUT)          # parse again (validates the file), fill zones, count unrouted
b2.BuildConnectivity()
pcbnew.ZONE_FILLER(b2).Fill(b2.Zones())
b2.BuildConnectivity()
conn = b2.GetConnectivity()
conn.RecalculateRatsnest()
print("unrouted connections after zone fill (ratsnest):", conn.GetUnconnectedCount(False))
b2.Save(OUT)
s = open(OUT).read()
if "(stackup" not in s:
    s = re.sub(r"\(setup\n", "(setup\n" + STACKUP, s, count=1)
    open(OUT, "w").write(s)
print("wrote", OUT)
