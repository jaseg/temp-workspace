#!/usr/bin/env python3
"""input_stage layout fragment (KiCad 7, pcbnew scripting), re-layout for JLC04161H-7628.

SIG_IN SMA edge launch -> VIN 50R microstrip (taper + < 1 mm, unterminated 1 Mohm input, no relay)
-> 5:1 compensated divider (Ctop 1.5p / Cbot 3.3p, Rg 10R) -> U101 BUF802 (RGT VQFN-16) with
U102 OPA197 differential-integrator servo (3 x 300k / 100k alpha string, Cint 470p, Rf1 10k,
Rf2 22.1k + RV 50k, Rofs 14.3k from VOFS) -> BUF_OUT_S edge pad (sampler 10R) and
49.9R + 0R -> BUF_OUT_T 50R microstrip.  Values: sim/input/RESULT.md, as drawn in kicad/gen/gen_input.py,
minus the switchable 50R termination (K101, R101-R103, TERM_50, VBUS removed on user decision).

Every RF width comes from line_z() below (Hammerstad-Jensen + thickness + solder-mask correction,
plus a conductor-backed-CPW check for the ground-pour gap).  All bends are 45 deg; check_corners()
verifies it.  No stitching-via grid (added at board assembly); only functional vias.

Run: python3 gen_input_stage.py   (writes input_stage.kicad_pcb next to this script, prints tables/checks)
"""
import math, os, re
import pcbnew
from pcbnew import FromMM, ToMM, VECTOR2I

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "input_stage.kicad_pcb")
LIB = "/usr/share/kicad/footprints"

# ============================================================================= stack-up / line design
# JLC04161H-7628 (JLCPCB standard 4-layer, 1.6 mm; values from the JLCPCB stack-up / impedance page):
# L1 Cu 0.035 | 7628 prepreg 0.2104 mm er 4.4 | L2 0.0152 | core 1.065 mm er 4.6 | L3 0.0152 |
# 7628 prepreg 0.2104 mm | L4 0.035.  Solder mask er 3.8: 0.6 mil (15 um) over trace, 1.2 mil over substrate.
H_PP, ER_PP, T_CU = 0.2104, 4.4, 0.035
H_L3 = H_PP + 0.0152 + 1.065                  # L1 -> L3 (reference where In1 is cut out)
ER_SM, C_SM_TRACE, C_SM_SUB = 3.8, 0.015, 0.030
EPS0 = 8.854e-3                               # pF/mm
C0 = 299.792458                               # mm/ns


def _K(k):
    """complete elliptic integral of the first kind (AGM)"""
    a, b = 1.0, math.sqrt(1 - k * k)
    for _ in range(40):
        a, b = (a + b) / 2, math.sqrt(a * b)
    return math.pi / (2 * a)


def line_z(w, h=H_PP, er=ER_PP, t=T_CU, mask=True, gap=None):
    """Outer-layer line -> (Z0 ohm, eps_eff).
    Microstrip: Hammerstad-Jensen 1980 incl. their strip-thickness correction.  Solder mask: the part
    (1 - q) of the field that is in air above the substrate sees er_mask over the mask thickness; the
    covered fraction is 1 - exp(-2 c / w) (c = mean mask thickness, empirical fit that reproduces the
    usual 1-2 R drop of a 15-30 um coating, i.e. the JLC calculator's ~0.36 mm for 50 R).
    gap: coplanar ground on L1 at this gap -> conductor-backed CPW (Wadell 3.4.4, t = 0) used as a
    ratio Z_cpwg(gap) / Z_cpwg(10 h) applied to the microstrip value (the closed form alone does not
    converge to microstrip for large gaps)."""
    u, Tn = w / h, t / h
    du1 = Tn / math.pi * math.log(1 + 4 * math.e / (Tn * (1 / math.tanh(math.sqrt(6.517 * u))) ** 2))
    dur = 0.5 * (1 + 1 / math.cosh(math.sqrt(er - 1))) * du1

    def zair(x):
        return 60 * math.log((6 + (2 * math.pi - 6) * math.exp(-(30.666 / x) ** 0.7528)) / x + math.sqrt(1 + 4 / x ** 2))

    def ee(x):
        a = 1 + math.log((x ** 4 + (x / 52) ** 2) / (x ** 4 + 0.432)) / 49 + math.log(1 + (x / 18.1) ** 3) / 18.7
        b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
        return (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / x) ** (-a * b)
    u1, ur = u + du1, u + dur
    z, e = zair(ur) / math.sqrt(ee(ur)), ee(ur) * (zair(u1) / zair(ur)) ** 2
    if mask:
        q = (e - 1) / (er - 1)
        e2 = e + (ER_SM - 1) * (1 - q) * (1 - math.exp(-2 * (C_SM_TRACE + C_SM_SUB) / 2 / w))
        z, e = z * math.sqrt(e / e2), e2
    if gap is not None:
        z *= cpwg(w, gap, h, er)[0] / cpwg(w, 10 * h, h, er)[0]
    return z, e


def cpwg(w, g, h=H_PP, er=ER_PP):
    """conductor-backed coplanar waveguide, zero thickness (Wadell) -> (Z0, eps_eff)"""
    k = w / (w + 2 * g)
    k3 = math.tanh(math.pi * w / 4 / h) / math.tanh(math.pi * (w + 2 * g) / 4 / h)
    r1 = _K(k) / _K(math.sqrt(1 - k * k))
    r3 = _K(k3) / _K(math.sqrt(1 - k3 * k3))
    e = (1 + er * r3 / r1) / (1 + r3 / r1)
    return 60 * math.pi / math.sqrt(e) / (r1 + r3), e


def width_for(z, **kw):
    lo, hi = 0.05, 2.0
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if line_z(m, **kw)[0] > z else (lo, m)
    return (lo + hi) / 2


def ps_per_mm(e):
    return math.sqrt(e) * 1e3 / C0


W50_EXACT = width_for(50.0)
W50 = round(W50_EXACT, 2)                       # 0.36 mm
Z50, EE50 = line_z(W50)
PS_MM = ps_per_mm(EE50)
G_RF = 0.75                                     # F.Cu ground-pour gap to RF traces (>= 2 x W50)
Z50_CPW = line_z(W50, gap=G_RF)[0]
W_HZ, W_SIG, W_PWR, W_GND = 0.15, 0.2, 0.4, 0.4
C_PAD_PER_MM2 = EPS0 * ER_PP / H_PP              # parallel-plate pad capacitance over In1, pF/mm^2

# ============================================================================= board coordinates (mm)
Y0 = 6.3           # HF row (VIN, GA, BUF_IN, OUT)
X_PAD_END = 3.7    # end of the SMA centre pad (1.27 mm wide)
X_TAPER = X_PAD_END + 0.8                        # 1.27 -> W50 taper (F.Cu zone)
X_CT = X_TAPER + 0.07 + 0.78                     # Ctop centre: pad 1 starts 0.07 mm after the taper
XA = 5.05          # alpha-string column (R114 pad 1 bridges onto Ctop pad 1)
x_ga = X_CT + 0.88                               # GA junction (Cbot column)
x_rg = x_ga + 0.88                               # Rg centre
x_bi = x_rg + 0.51                               # BUF_IN node (Rg pad 2, bias string column)
XU = x_bi + 3.125  # U101 centre (room for the pin 3 / pin 4 fan-out)
YU = Y0 + 0.25     # pins 2 and 11 on Y0
W, H = round(XU + 4.555, 2), 17.6

board = pcbnew.BOARD()
board.SetCopperLayerCount(4)
ds = board.GetDesignSettings()
ds.SetBoardThickness(FromMM(1.6))
for lay in (pcbnew.In1_Cu, pcbnew.In2_Cu):
    board.SetLayerType(lay, pcbnew.LT_POWER)
nc = ds.m_NetSettings.m_DefaultNetClass
nc.SetClearance(FromMM(0.1)); nc.SetTrackWidth(FromMM(W_SIG)); nc.SetViaDiameter(FromMM(0.5)); nc.SetViaDrill(FromMM(0.25))
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


def place(lib, name, ref, val, x, y, rot=0, side="F", nets=None):
    fp = pcbnew.FootprintLoad(os.path.join(LIB, lib + ".pretty"), name)
    assert fp is not None, name
    fp.SetReference(ref); fp.SetValue(val)
    board.Add(fp)
    if side == "B":
        fp.Flip(fp.GetPosition(), False)
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(P(x, y))
    for p in fp.Pads():
        n = (nets or {}).get(p.GetNumber())
        if n:
            p.SetNet(N(n))
    fp.Reference().SetVisible(False); fp.Value().SetVisible(False)
    for g in fp.GraphicalItems():
        if isinstance(g, pcbnew.FP_TEXT):
            g.SetTextSize(VECTOR2I(FromMM(0.25), FromMM(0.25))); g.SetTextThickness(FromMM(0.04))
    FPS[ref] = fp
    return fp


def RC(ref, val, x, y, rot, n1, n2, size="0402", side="F", cap=False):
    m = {"0402": "1005", "0603": "1608", "0805": "2012"}[size]
    lib, pre = ("Capacitor_SMD", "C") if cap else ("Resistor_SMD", "R")
    return place(lib, f"{pre}_{size}_{m}Metric", ref, val, x, y, rot, side, {"1": n1, "2": n2})


def V(ref, val, x, y, n_top, n_bot, size="0402", side="F", cap=False):
    """vertical 2-terminal part: pad1 on top (rot 270) carries n_top"""
    return RC(ref, val, x, y, 270, n_top, n_bot, size, side, cap)


def Hz(ref, val, x, y, n_left, n_right, size="0402", side="F", cap=False):
    """horizontal 2-terminal part, pad1 left"""
    return RC(ref, val, x, y, 0 if side == "F" else 180, n_left, n_right, size, side, cap)


def pad(ref, num):
    for p in FPS[ref].Pads():
        if p.GetNumber() == str(num):
            v = p.GetPosition()
            return (ToMM(v.x), ToMM(v.y))
    raise KeyError((ref, num))


TRACKS = []


def track(pts, w, net, layer=pcbnew.F_Cu):
    pts = [pad(*p) if isinstance(p[0], str) else p for p in pts]
    out = []
    for a, b in zip(pts, pts[1:]):
        if math.dist(a, b) < 1e-4:
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(P(*a)); t.SetEnd(P(*b))
        t.SetWidth(FromMM(w)); t.SetLayer(layer); t.SetNet(N(net))
        board.Add(t); out.append(t); TRACKS.append(t)
    return out


def via(x, y, net, d=0.5, drill=0.25):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(P(x, y)); v.SetWidth(FromMM(d)); v.SetDrill(FromMM(drill))
    v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(N(net)); board.Add(v)
    return v


def gvia(x, y, d=0.5, drill=0.25):
    return via(x, y, "GND", d, drill)


def svia(x, y, net):                      # small via close to U101
    return via(x, y, net, 0.45, 0.2)


def text(s, x, y, size=0.5, layer=pcbnew.F_SilkS, just=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s); t.SetPosition(P(x, y)); t.SetLayer(layer)
    t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size))); t.SetTextThickness(FromMM(size * 0.15))
    if just:
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT if just < 0 else pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    board.Add(t)


def zone(layers, net, pts, clearance=0.25, priority=0, rule=False, minw=0.2):
    z = pcbnew.ZONE(board)
    ls = pcbnew.LSET()
    for l in layers:
        ls.AddLayer(l)
    z.SetLayerSet(ls)
    ol = z.Outline(); ol.NewOutline()
    for x, y in pts:
        ol.Append(FromMM(x), FromMM(y))
    if rule:
        z.SetIsRuleArea(True); z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowVias(False); z.SetDoNotAllowTracks(False); z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
    else:
        z.SetNet(N(net)); z.SetLocalClearance(FromMM(clearance)); z.SetMinThickness(FromMM(minw))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL); z.SetAssignedPriority(priority)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(z)
    return z


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def keepout(x0, y0, x1, y1, layers=(pcbnew.F_Cu,)):
    zone(list(layers), None, rect(x0, y0, x1, y1), rule=True)


def edge_pad(ref, net, x, y, w, h):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("input_stage", "IF_PAD"))
    fp.SetReference(ref); fp.SetValue(net)
    fp.Reference().SetVisible(False); fp.Value().SetVisible(False)
    p = pcbnew.PAD(fp)
    p.SetNumber("1"); p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetSize(VECTOR2I(FromMM(w), FromMM(h)))
    ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.F_Mask)
    p.SetLayerSet(ls); fp.Add(p); board.Add(fp)
    fp.SetPosition(P(x, y)); p.SetNet(N(net))
    FPS[ref] = fp


# ============================================================================= placement
# --- RF chain on Y0, left to right: SMA - taper - Ctop (R114 tap on its pad 1) - Rg - BUF802 pin 2
place("Connector_Coaxial", "SMA_Samtec_SMA-J-P-X-ST-EM1_EdgeMount", "J101", "SIG_IN", 2.1, Y0, 270,
      nets={"1": "VIN", "2": "GND"})
TAP_DY = W50 / 2 - 0.08 + 0.27 + 0.51            # 0402 part centre offset from the line centre
Hz("C101", "1.5p C0G 100V", X_CT, Y0, "VIN", "GA", cap=True)          # Ctop, first divider part
V("R114", "300k 0.1%", XA, Y0 + TAP_DY, "VIN", "S1")                # first alpha resistor, pad 1 on Ctop pad 1
Hz("R104", "10", x_rg, Y0, "GA", "BUF_IN")                           # Rg
V("C102", "3.3p C0G", x_ga, Y0 + 1.3, "GA", "GND", cap=True)          # Cbot
V("R105", "4.99M", x_bi, Y0 + 1.3, "BUF_IN", "IN_BIAS_MID")
V("R106", "4.99M", x_bi, Y0 + 2.9, "IN_BIAS_MID", "IN_BIAS")
U1N = {"1": "+5V", "2": "BUF_IN", "3": "IN_BIAS", "4": "IN_AUX", "5": "-5V", "6": "-5V", "7": "R_BIAS",
       "8": "-5V", "10": "-5V", "11": "BUF_OUT_S", "12": "+5V", "14": "CLL", "15": "CLH", "17": "GND"}
place("Package_DFN_QFN", "VQFN-16-1EP_3x3mm_P0.5mm_EP1.68x1.68mm", "U101", "BUF802IRGTR", XU, YU, 0, nets=U1N)
for p in FPS["U101"].Pads():
    if p.GetNumber() == "":
        p.SetNet(N("GND"))
X_P11 = XU + 1.875                                # outer end of the OUT pad
x_sp = X_P11 + 0.67 + 0.32                        # splitter column (pin-10/12 escape between)
V("R112", "49.9", x_sp, Y0 + TAP_DY, "BUF_OUT_S", "RT_MID")
V("R113", "0", x_sp, Y0 + TAP_DY + 1.6, "RT_MID", "BUF_OUT_T")
V("R118", "10.0k 0.1%", x_sp + 0.95, Y0 - TAP_DY, "FB", "BUF_OUT_S")  # Rf1 sense, pad2 on the OUT line
edge_pad("IF1", "BUF_OUT_S", W - 0.2, Y0, 0.4, W50)
# --- U101 supply decoupling, right at the pins
y_top_cap, y_bot_cap = YU - 1.875 - 0.2 - 0.27 - 0.51, YU + 1.875 + 0.2 + 0.27 + 0.51
V("C108", "100n", XU - 2.4, Y0 - 1.36, "GND", "+5V", cap=True)          # VS+ pin 1
V("C117", "100n", x_sp, Y0 - 1.36, "GND", "+5V", cap=True)              # VSO+ pin 12
V("C110", "100n", XU - 0.65, y_bot_cap, "-5V", "GND", cap=True)          # VS- pins 5/6
V("R107", "17.8k", XU + 0.25, y_bot_cap, "R_BIAS", "-5V")               # R_Bias pin 7
V("C111", "100n", XU + 1.15, y_bot_cap, "-5V", "GND", cap=True)          # VS-/VSO- pins 8/10
# --- clamp dividers above U101 (pad1 row = CLx node)
Y_CL = Y0 - 3.4
for ref, val, x, top in (("R109", "1.5k", XU - 3.1, "GND"), ("R108", "1k", XU - 2.15, "+2V5"),
                         ("C103", "1u", XU - 1.2, "GND"), ("C104", "1u", XU + 1.2, "GND"),
                         ("R110", "1k", XU + 2.15, "-2V5"), ("R111", "1.5k", XU + 3.1, "GND")):
    V(ref, val, x, Y_CL - 0.51, top, "CLH" if x < XU else "CLL", cap=ref.startswith("C"))
place("TestPoint", "TestPoint_Pad_D1.0mm", "TP101", "CLH", XU - 4.3, Y_CL - 1.2, nets={"1": "CLH"})
place("Connector_PinHeader_1.27mm", "PinHeader_1x03_P1.27mm_Vertical", "J3", "CLAMP", XU - 8.5, 1.0, 90,
      nets={"1": "GND", "2": "-2V5", "3": "+2V5"})
# --- alpha string and servo (below the HF row)
V("R115", "300k 0.1%", XA, Y0 + TAP_DY + 1.6, "S1", "S2")
V("R116", "300k 0.1%", XA, Y0 + TAP_DY + 3.2, "S2", "TAP")
XO, YO = XA + 0.95, Y0 + 6.8                     # U102 (rot 270: IN+ top-left on the alpha column)
place("Package_TO_SOT_SMD", "SOT-23-5", "U102", "OPA197IDBVR", XO, YO, 270,
      nets={"1": "OPA_OUT", "2": "-5V", "3": "TAP", "4": "FB", "5": "+5V"})
Y_P3O = YO - 1.1375                              # U102 top pin row
Hz("R117", "100k 0.1%", XA - 1.13, YO - 2.05, "GND", "TAP")
Hz("C105", "18p C0G", XA - 1.13, Y_P3O, "GND", "TAP", cap=True)
V("C113", "100n", XO, YO - 1.1, "-5V", "GND", side="B", cap=True)        # OPA V- (bottom, under pin 2)
V("C112", "100n", XO + 0.95, YO + 1.0, "GND", "+5V", side="B", cap=True) # OPA V+ (bottom, under pin 5)
x_p1o = XO + 0.95                                 # OPA OUT pin column
Hz("R121", "1k", x_p1o + 0.51, Y0 + 4.3, "OPA_OUT", "IN_AUX")            # Raux, pad 1 right above OPA OUT
V("C107", "100p C0G", x_bi + 1.02, Y0 + 4.81, "IN_AUX", "GND", cap=True)  # Caux
place("TestPoint", "TestPoint_Pad_D1.0mm", "TP103", "SERVO", XA + 1.25, Y0 + 3.4, nets={"1": "OPA_OUT"})
X_CI = XO + 1.9
V("C106", "470p C0G", X_CI, YO - 0.2, "OPA_OUT", "FB", cap=True)         # Cint
Y_FB = YO + 2.25                                  # FB line
Hz("R120", "22.1k 0.1%", X_CI + 0.27, Y_FB, "FB", "RF2_MID")              # Rf2, pad 1 under the Cint drop
V("R119", "14.3k 0.1%", XO + 0.5, Y_FB + 0.51, "FB", "VOFS")             # Rofs, pad 1 on the FB line
place("Potentiometer_SMD", "Potentiometer_Bourns_3314J_Vertical", "RV101", "50k", W - 3.25, YO + 1.75, 90,
      nets={"1": "RF2_MID", "2": "GND", "3": "GND"})
# --- header and bulk caps (bulk caps on the bottom side, straight into the header pins)
YJ = H - 0.9
J2N = ["-5V", "+5V", "GND", "VOFS"]
X_J2 = 1.15
place("Connector_PinHeader_1.27mm", "PinHeader_1x04_P1.27mm_Vertical", "J2", "PWR", X_J2, YJ, 90,
      nets={str(i + 1): n for i, n in enumerate(J2N)})
V("C116", "10u", X_J2, YJ - 2.4, "GND", "-5V", size="0805", side="B", cap=True)
V("C115", "10u", X_J2 + 1.75, YJ - 2.4, "GND", "+5V", size="0805", side="B", cap=True)

# ============================================================================= routing
F, B = pcbnew.F_Cu, pcbnew.B_Cu
RF = {}                                          # net -> list of (tracks, intended Z0, note)
# --- VIN: SMA pad -> taper (zone) -> 50R line -> Ctop pad 1 (R114 bridges onto it)
zone([F], "VIN", [(X_PAD_END - 0.3, Y0 - 0.635), (X_PAD_END, Y0 - 0.635), (X_TAPER, Y0 - W50 / 2),
                  (X_TAPER, Y0 + W50 / 2), (X_PAD_END, Y0 + 0.635), (X_PAD_END - 0.3, Y0 + 0.635)],
     clearance=0.25, priority=5, minw=0.1)
RF["VIN"] = [(track([(X_TAPER - 0.05, Y0), ("C101", 1)], W50, "VIN"), 50, "SMA taper end -> Ctop pad 1")]
track([("R114", 1), (XA, Y0)], 0.4, "VIN")
# SMA ground legs: one via per leg ties F/B legs, In1 and the In2 GND island under the launch
for sy in (-1, 1):
    gvia(3.9, Y0 + sy * 3.8)
# --- divider: GA / BUF_IN (thin, low-C cut-out below)
track([("C101", 2), ("R104", 1)], 0.3, "GA")
track([(x_ga, Y0), ("C102", 1)], 0.3, "GA")
y_cbv = pad("C102", 2)[1] + 0.64
gvia(x_ga, y_cbv); track([("C102", 2), (x_ga, y_cbv)], W_GND, "GND")
p2, p3, p4 = pad("U101", 2), pad("U101", 3), pad("U101", 4)
track([("R104", 2), p2], W_HZ, "BUF_IN")
track([("R104", 2), ("R105", 1)], 0.3, "BUF_IN")
track([("R105", 2), ("R106", 1)], 0.3, "IN_BIAS_MID")
xb = x_bi + 0.67
track([p3, (XU - 2.0, p3[1]), (xb, p3[1] + XU - 2.0 - xb), (xb, Y0 + 2.95),
       (xb - (pad("R106", 2)[1] - Y0 - 2.95), pad("R106", 2)[1]), ("R106", 2)], W_HZ, "IN_BIAS")
xa_ = xb + 0.35
c107 = pad("C107", 1)
track([p4, (xa_ + 0.2, p4[1]), (xa_, p4[1] + 0.2), (xa_, c107[1]), ("C107", 1)], W_SIG, "IN_AUX")
track([("R121", 2), ("C107", 1)], 0.3, "IN_AUX")
gvia(c107[0], pad("C107", 2)[1] + 0.7); track([("C107", 2), (c107[0], pad("C107", 2)[1] + 0.7)], W_GND, "GND")
# --- U101 supplies (zones = local copper polygons; vias in pairs at the capacitors)
p1, p12 = pad("U101", 1), pad("U101", 12)
c108 = pad("C108", 2)
track([p1, (c108[0] + 0.55, p1[1]), (c108[0] + 0.3, c108[1] + 0.05)], 0.25, "+5V")
for y in (Y0 - 1.15, Y0 - 1.7):
    svia(XU - 1.55, y, "+5V")
zone([F], "+5V", rect(c108[0] - 0.32, Y0 - 1.95, XU - 1.33, Y0 - 0.68), clearance=0.15, priority=3, minw=0.15)
gvia(c108[0], Y0 - 2.55); track([("C108", 1), (c108[0], Y0 - 2.55)], W_GND, "GND")
c117 = pad("C117", 2)
track([p12, (X_P11 + 0.12, p12[1]), (X_P11 + 0.12 + p12[1] - c117[1], c117[1]), c117], 0.25, "+5V")
for xy in ((XU + 1.5, Y0 - 1.2), (XU + 1.75, Y0 - 1.85)):
    svia(*xy, "+5V")
zone([F], "+5V", [(XU + 1.2, Y0 - 0.68), (XU + 1.2, Y0 - 2.15), (XU + 2.05, Y0 - 2.15), (XU + 2.05, Y0 - 1.15),
                  (c117[0] + 0.32, Y0 - 1.15), (c117[0] + 0.32, Y0 - 0.55), (XU + 1.95, Y0 - 0.55),
                  (XU + 1.95, Y0 - 0.68)], clearance=0.15, priority=3, minw=0.15)
gvia(c117[0], Y0 - 2.55); track([("C117", 1), (c117[0], Y0 - 2.55)], W_GND, "GND")
p5, p6, p7, p8, p10 = (pad("U101", n) for n in (5, 6, 7, 8, 10))
c110, c111 = pad("C110", 1), pad("C111", 1)
zone([F], "-5V", [(p5[0] - 0.13, YU + 1.3), (p6[0] + 0.13, YU + 1.3), (p6[0] + 0.13, YU + 2.05),
                  (c110[0] + 0.32, c110[1] - 0.2), (c110[0] + 0.32, c110[1] + 0.3), (XU - 1.65, c110[1] + 0.6),
                  (XU - 1.65, YU + 1.95), (p5[0] - 0.13, YU + 1.95)], clearance=0.15, priority=3, minw=0.15)
track([p5, (p5[0], YU + 2.0), (c110[0], c110[1])], 0.25, "-5V"); track([p6, (p6[0], YU + 1.95), (c110[0], c110[1])], 0.25, "-5V")
for y in (Y0 + 2.45, Y0 + 3.05):
    svia(XU - 1.35, y, "-5V")
zone([F], "-5V", [(p8[0] - 0.13, YU + 1.3), (p8[0] + 0.13, YU + 1.3), (XU + 1.75, YU + 1.3),
                  (XU + 1.75, YU + 2.45), (c111[0] + 0.32, YU + 2.45), (c111[0] + 0.32, c111[1] + 0.3),
                  (c111[0] - 0.32, c111[1] + 0.3), (p8[0] - 0.13, YU + 2.0)], clearance=0.15, priority=3, minw=0.15)
track([p8, (p8[0], YU + 1.95), (c111[0], c111[1])], 0.25, "-5V")
track([p10, (X_P11 + 0.05, p10[1]), (X_P11 + 0.3, p10[1] + 0.25), (X_P11 + 0.3, Y0 + 1.45)], 0.25, "-5V")
svia(X_P11 + 0.3, Y0 + 1.45, "-5V")
for xy in ((XU + 1.5, Y0 + 1.7), (XU + 1.75, Y0 + 2.35)):
    svia(*xy, "-5V")
track([p7, ("R107", 1)], 0.25, "R_BIAS")
yv = pad("C110", 2)[1] + 0.68
for ref, net in (("C110", "GND"), ("R107", "-5V"), ("C111", "GND")):
    x = pad(ref, 2)[0]
    via(x, yv, net); track([(ref, 2), (x, yv)], W_GND, net)
for dx in (-0.42, 0.42):                       # EP ground vias (in the exposed pad: unavoidable)
    for dy in (-0.42, 0.42):
        svia(XU + dx, YU + dy, "GND")
# --- clamp dividers
p14, p15 = pad("U101", 14), pad("U101", 15)
for p_, ref, net in ((p15, "C103", "CLH"), (p14, "C104", "CLL")):
    xc = pad(ref, 2)[0]
    d = abs(xc - p_[0])
    track([p_, (p_[0], Y_CL + d), (xc, Y_CL)], W_SIG, net)
track([("R109", 2), ("C103", 2)], 0.3, "CLH"); track([("C104", 2), ("R111", 2)], 0.3, "CLL")
tp = pad("TP101", 1); r109 = pad("R109", 2)
track([tp, (tp[0] + (r109[1] - tp[1]), r109[1]), r109], W_SIG, "CLH")
YCV = 0.55
for ref in ("R109", "R108", "C103", "C104", "R110", "R111"):
    x = pad(ref, 1)[0]; net = FPS[ref].Pads()[0].GetNetname()
    via(x, YCV, net); track([(ref, 1), (x, YCV)], W_GND, net)
# +2V5 / -2V5 from J3 on B.Cu
j32, j33 = pad("J3", 2), pad("J3", 3)
xr8, xr10 = pad("R108", 1)[0], pad("R110", 1)[0]
track([j33, (j33[0] + 0.25, 1.25), (xr8 - 0.7, 1.25), (xr8, YCV)], 0.3, "+2V5", B)
track([j32, (j32[0] + 0.9, 1.9), (xr10 - 0.9, 1.9), (xr10, 1.0), (xr10, YCV)], 0.3, "-2V5", B)
# --- output: OUT pin -> 50R -> edge pad IF1; 49.9R + 0R -> BUF_OUT_T 50R to the right edge (IF2)
p11 = pad("U101", 11)
RF["BUF_OUT_S"] = [(track([p11, ("IF1", 1)], W50, "BUF_OUT_S"), 50, "OUT pin -> edge pad IF1")]
track([("R112", 1), (x_sp, Y0)], 0.4, "BUF_OUT_S"); track([("R118", 2), (x_sp + 0.95, Y0)], 0.4, "BUF_OUT_S")
track([("R112", 2), ("R113", 1)], 0.4, "RT_MID")
xt, yt0 = pad("R113", 2)
Y_T = yt0 + 0.8                                   # BUF_OUT_T row at the right edge
RF["BUF_OUT_T"] = [(track([("R113", 2), (xt, Y_T - 0.5), (xt + 0.5, Y_T), (W - 0.05, Y_T)], W50, "BUF_OUT_T"),
                    50, "0R pad -> right edge IF2")]
edge_pad("IF2", "BUF_OUT_T", W - 0.2, Y_T, 0.4, W50)
# Rf1: FB via above R118, B.Cu down the right edge and left under the pot to the Cint/FB drop
r118 = pad("R118", 1)
svia(r118[0], Y0 - 2.1, "FB"); track([("R118", 1), (r118[0], Y0 - 2.1)], W_SIG, "FB")
Y_FBB = YO + 1.1                                  # B.Cu FB row and FB via on the Cint drop
track([(r118[0], Y0 - 2.1), (r118[0], Y_FBB - 0.7), (r118[0] - 0.7, Y_FBB), (X_CI, Y_FBB)], W_SIG, "FB", B)
svia(X_CI, Y_FBB, "FB")
# --- alpha string -> TAP -> U102 IN+
track([("R114", 2), ("R115", 1)], 0.3, "S1"); track([("R115", 2), ("R116", 1)], 0.3, "S2")
p3o = pad("U102", 3)
track([("R116", 2), p3o], 0.3, "TAP")
track([("R117", 2), (XA, pad("R117", 2)[1])], W_SIG, "TAP")
track([("C105", 2), p3o], 0.3, "TAP")
for ref in ("R117", "C105"):
    x, y = pad(ref, 1); gvia(x - 0.7, y); track([(ref, 1), (x - 0.7, y)], W_GND, "GND")
# --- U102 supplies: vias at the pins, 100n on the bottom side, shared GND via in the SOT centre
p2o, p5o, p1o, p4o = pad("U102", 2), pad("U102", 5), pad("U102", 1), pad("U102", 4)
via(p2o[0], YO - 2.2, "-5V"); track([p2o, (p2o[0], YO - 2.2)], 0.6, "-5V")
track([(p2o[0], YO - 2.2), ("C113", 1)], 0.5, "-5V", B)
gvia(XO, YO); track([("C113", 2), (XO, YO)], 0.5, "GND", B)
c112 = pad("C112", 1)
track([("C112", 1), (c112[0], c112[1] - 0.05), (c112[0] - (c112[1] - 0.05 - YO), YO), (XO, YO)], 0.5, "GND", B)
via(XO, p5o[1], "+5V"); track([p5o, (XO, p5o[1])], 0.6, "+5V")       # +5V via between pins 4 and 5
c1122 = pad("C112", 2)
track([(XO, p5o[1]), (XO + c1122[1] - p5o[1], c1122[1]), c1122], 0.5, "+5V", B)
# --- OPA_OUT: pin 1 straight up into Raux pad 1, TP103 beside it, right to Cint
r121 = pad("R121", 1)
track([p1o, r121], W_SIG, "OPA_OUT")
tp3 = pad("TP103", 1)
track([tp3, (r121[0], tp3[1] + r121[0] - tp3[0]), r121], W_SIG, "OPA_OUT")
c106 = pad("C106", 1)
track([p1o, (c106[0] - (c106[1] - p1o[1]), p1o[1]), c106], W_SIG, "OPA_OUT")
# --- FB node: pin 4 -> FB line (y = Y_FB) -> Rf2 pad 1 <- Cint drop (FB via) ; Rofs pad 1 on the line
track([p4o, (p4o[0], Y_FB - 0.4), (p4o[0] + 0.4, Y_FB), ("R120", 1)], W_SIG, "FB")
track([("C106", 2), (X_CI, Y_FBB)], 0.25, "FB"); track([(X_CI, Y_FBB), (X_CI, Y_FB)], 0.25, "FB")
rv1 = pad("RV101", 1); r1202 = pad("R120", 2)
track([r1202, (r1202[0] + rv1[1] - r1202[1], rv1[1]), rv1], 0.3, "RF2_MID")
x, y = pad("RV101", 3); gvia(x + 1.5, y); track([("RV101", 3), (x + 1.5, y)], W_GND, "GND")
x, y = pad("RV101", 2); gvia(x, y + 1.5); track([("RV101", 2), (x, y + 1.5)], W_GND, "GND")
# --- VOFS into J2 pin 4; bulk caps on B.Cu straight into the J2 supply pins
r1192, j24 = pad("R119", 2), pad("J2", 4)
track([r1192, (r1192[0] - (j24[1] - r1192[1]), j24[1]), j24], W_SIG, "VOFS")
track([("C116", 2), ("J2", 1)], 0.6, "-5V", B)
c1152, j22 = pad("C115", 2), pad("J2", 2)
track([c1152, (c1152[0], j22[1] - (c1152[0] - j22[0]) - 0.3), (j22[0], j22[1] - 0.3), j22], 0.6, "+5V", B)

# ============================================================================= zones
outline = rect(0, 0, W, H)
for a, b in zip(outline, outline[1:] + outline[:1]):
    s = pcbnew.PCB_SHAPE(board); s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(P(*a)); s.SetEnd(P(*b)); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(FromMM(0.1)); board.Add(s)
I1, I2 = pcbnew.In1_Cu, pcbnew.In2_Cu
# RF keep-outs on F.Cu (ground pour stays >= G_RF from every RF trace edge)
g = W50 / 2 + G_RF
keepout(X_TAPER - 0.05, Y0 - g, pad("C101", 2)[0], Y0 + g)
keepout(XU + 1.0, Y0 - g, W, Y0 + g)
keepout(xt - g, yt0, W, Y_T + g)
# SMA launch: In1 cut out under the 1.27 mm centre pad; In2 is a GND island there (reference L3);
# F.Cu pour 0.25 mm beside the pad -> CPWG over L3 (see table)
keepout(0, Y0 - 0.9, X_PAD_END, Y0 + 0.9, (I1,))
# low-capacitance cut-out: Ctop pad 2, GA, Cbot pad 1, Rg, BUF_IN, R105 pad 1, U101 pin 2 region
CUT_HZ = (pad("C101", 2)[0] - 0.3, Y0 - 0.45, XU - 1.1, Y0 + 1.1)
keepout(*CUT_HZ, (F, I1, I2, B))
zone([I1], "GND", outline, clearance=0.2)
zone([F], "GND", outline, clearance=0.25, priority=0)
zone([B], "GND", outline, clearance=0.25, priority=0)
# In2: GND island under the SMA; -5V band below the HF row (U101 bottom, U102 V-) with a tongue down the
# left edge to J2 pin 1; +5V everywhere else (top band, right-edge corridor, bottom band)
zone([I2], "GND", rect(0, Y0 - 4.0, 4.7, Y0 + 4.0), clearance=0.25, priority=2)
X_M5 = X_P11 + 0.85
MINUS5 = [(0, Y0 + 0.3), (X_M5, Y0 + 0.3), (X_M5, YO + 0.5), (1.75, YO + 0.5), (1.75, H), (0, H)]
zone([I2], "-5V", MINUS5, clearance=0.25, priority=1)
zone([I2], "+5V", outline, clearance=0.25, priority=0)

# ============================================================================= silkscreen / fab
text("SIG_IN", 0.25, Y0 + 4.45, 0.4, just=-1)
text("S>", W - 0.1, Y0 - 0.6, 0.35, just=1)
text("T>", W - 0.1, Y_T + 0.6, 0.35, just=1)
for i, n in enumerate(J2N):
    text(n, X_J2 + 1.27 * i, YJ - 0.85, 0.3)
for i, n in enumerate(("GND", "-2V5", "+2V5")):
    text(n, XU - 8.5 + 1.27 * i, 2.0, 0.3)
for i, s_ in enumerate(("JLC04161H-7628, 1.6 mm: L1 | 7628 0.2104 er 4.4 |",
                        "L2 GND | core 1.065 | L3 +5V/-5V | 7628 | L4 GND",
                        "50R microstrip w=%.2f mm (mask): Z0 %.1f R," % (W50, Z50),
                        "eps_eff %.2f, %.2f ps/mm, pour gap %.2f mm" % (EE50, PS_MM, G_RF))):
    text(s_, 0.1, H + 0.6 + 0.55 * i, 0.35, pcbnew.F_Fab, just=-1)

# ============================================================================= tables
print("Stack-up JLC04161H-7628: L1-L2 7628 prepreg %.4f mm er %.1f, Cu %.3f mm, mask er %.1f %.0f/%.0f um"
      % (H_PP, ER_PP, T_CU, ER_SM, C_SM_TRACE * 1e3, C_SM_SUB * 1e3))
zb, eb = line_z(W50, mask=False)
print("50R line: exact w %.3f mm -> used %.2f mm: Z0 %.1f R masked (%.1f R bare), eps_eff %.3f, %.2f ps/mm"
      % (W50_EXACT, W50, Z50, zb, EE50, PS_MM))
print("  coplanar check, F.Cu pour gap %.2f mm: Z0 %.1f R (CPWG ratio model); gap 0.25 mm would give %.1f R"
      % (G_RF, Z50_CPW, line_z(W50, gap=0.25)[0]))
zs = cpwg(1.27, 0.25, H_L3)[0]
print("SMA centre pad 1.27 mm: over In1 (no cut) %.1f R; In1 cut, L3 GND island, pour gap 0.25: %.1f R"
      % (line_z(1.27, gap=0.25)[0], zs))


def tlen(ts):
    return sum(ToMM(t.GetLength()) for t in ts)


print("\nRF segments:\n%-10s %-30s %6s %6s %7s %7s" % ("net", "segment", "w mm", "Z0", "len mm", "ps"))
for net, segs in RF.items():
    for ts, zi, note in segs:
        for t in ts:
            w_ = ToMM(t.GetWidth()); z_ = line_z(w_)[0]
            print("%-10s %-30s %6.2f %6.1f %7.2f %7.1f" % (net, note, w_, z_, ToMM(t.GetLength()),
                                                          ToMM(t.GetLength()) * PS_MM))
print("necks < 1 mm: U101 OUT pad 0.25 mm wide, 0.41 mm from pad centre to pad end (line 0.36 mm starts on it)")
print("\nexcess pad capacitance (parallel plate over In1, %.3f pF/mm^2, pad area minus line area):" % C_PAD_PER_MM2)


def pad_rect(ref, n):
    x, y = pad(ref, n)
    for p in FPS[ref].Pads():
        if p.GetNumber() == str(n):
            bb = p.GetBoundingBox()
            return ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom())


def overlap(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


r114, c1011 = pad_rect("R114", 1), pad_rect("C101", 1)
a114 = (r114[2] - r114[0]) * (r114[3] - r114[1]) - overlap(r114, c1011)
pads_x = [("SMA centre pad (In1 cut, CPWG over L3)", 0.0),
          ("C101 0402 pad 1 (line end)", C_PAD_PER_MM2 * (0.54 * 0.64 - 0.27 * W50)),
          ("R114 0402 pad bridged onto C101 pad 1", C_PAD_PER_MM2 * a114),
          ("R112 + R118 0402 tap pads on BUF_OUT_S", 2 * C_PAD_PER_MM2 * 0.54 * 0.64),
          ("R113 0402 pad 2 at BUF_OUT_T start", C_PAD_PER_MM2 * (0.54 * 0.64 - 0.54 * W50))]
for n_, c_ in pads_x:
    print("  %-48s %.3f pF" % (n_, c_))
print("\nlength-defined elements:\n%-44s %9s %9s %9s %9s" % ("element", "int. mm", "int. ps", "act. mm", "act. ps"))
L_STUB = c1011[0] - X_PAD_END                    # SMA pad end -> first divider part (Ctop pad 1 edge)
rows = [("VIN: SMA pad end -> Ctop pad 1 edge (stub)", 5.0, L_STUB),
        ("VIN: SMA pad end -> Ctop pad 1 centre", 5.0, pad("C101", 1)[0] - X_PAD_END),
        ("BUF_IN: Rg pad 2 -> U101 pin 2 (0.15 mm)", float("nan"), p2[0] - pad("R104", 2)[0]),
        ("BUF_OUT_S: OUT pin -> edge (10R <= 3 mm)", 3.0, tlen(RF["BUF_OUT_S"][0][0])),
        ("BUF_OUT_S: OUT pin -> R112 tap", 0.0, x_sp - p11[0]),
        ("BUF_OUT_T: 0R -> right edge (< 30 mm)", float("nan"), tlen(RF["BUF_OUT_T"][0][0]))]
for name, imm, amm in rows:
    print("%-44s %9.2f %9.1f %9.2f %9.1f" % (name, imm, imm * PS_MM, amm, amm * PS_MM))
print("1 Mohm input stub: %.2f mm = %.1f ps one way (%.1f ps round trip) from SMA pad end to Ctop; outline %.2f x %.2f mm"
      % (L_STUB, L_STUB * PS_MM, 2 * L_STUB * PS_MM, W, H))

# ============================================================================= checks
probs = 0
# intended overlaps: R114 pad bridged onto Ctop pad 1; pad-to-pad bridges into SOT/test pads
OK_PAIRS = [{"C101", "R114"}, {"U102", "R117"}, {"U102", "C105"}, {"TP103", "R121"},
            {"TP101", "J3"}]          # pad-to-pad bridges; header courtyard only; bodies >= 0.13 mm apart
print("courtyard overlaps accepted by design:", ", ".join("/".join(sorted(p)) for p in OK_PAIRS))
fl = list(FPS.values())
for f in fl:
    f.BuildCourtyardCaches()
for i, a in enumerate(fl):
    for b in fl[i + 1:]:
        if a.IsFlipped() != b.IsFlipped():
            continue
        lay = pcbnew.B_CrtYd if a.IsFlipped() else pcbnew.F_CrtYd
        ca, cb = a.GetCourtyard(lay), b.GetCourtyard(lay)
        if ca.OutlineCount() == 0 or cb.OutlineCount() == 0:
            continue
        x = pcbnew.SHAPE_POLY_SET(ca); y = pcbnew.SHAPE_POLY_SET(cb)
        x.Deflate(FromMM(0.15), 8); y.Deflate(FromMM(0.15), 8)      # courtyards may touch
        x.BooleanIntersection(y, pcbnew.SHAPE_POLY_SET.PM_FAST)
        pair = {a.GetReference(), b.GetReference()}
        if pair in OK_PAIRS:
            continue
        if x.OutlineCount() and x.Area() > FromMM(0.01) * FromMM(0.01):
            print("COURTYARD OVERLAP %s / %s" % (a.GetReference(), b.GetReference())); probs += 1


def check_corners():
    """every joint of exactly two track segments (same net/layer, not on a pad) must turn <= 45 deg"""
    ends = {}
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_TRACE_T:
            continue
        a, b = t.GetStart(), t.GetEnd()
        for p, q in ((a, b), (b, a)):
            k = (t.GetNetCode(), t.GetLayer(), round(ToMM(p.x), 3), round(ToMM(p.y), 3))
            ends.setdefault(k, []).append((ToMM(q.x) - ToMM(p.x), ToMM(q.y) - ToMM(p.y)))
    bad = []
    for k, v in ends.items():
        if len(v) != 2:
            continue
        on_pad = any(p_.HitTest(P(k[2], k[3])) for f in FPS.values() for p_ in f.Pads()
                     if p_.GetNetCode() == k[0] and p_.IsOnLayer(k[1]))
        on_via = any(t.Type() == pcbnew.PCB_VIA_T and t.GetNetCode() == k[0] and
                     math.dist(ToMM(t.GetPosition()), (k[2], k[3])) < 0.01 for t in board.GetTracks())
        if on_pad or on_via:
            continue
        (ax, ay), (bx, by) = v
        cosang = (ax * bx + ay * by) / math.hypot(ax, ay) / math.hypot(bx, by)
        turn = 180 - math.degrees(math.acos(max(-1, min(1, cosang))))
        if turn > 45.5:
            bad.append((board.GetLayerName(k[1]), board.FindNet(k[0]).GetNetname(), k[2], k[3], round(turn)))
    return bad


bad = check_corners()
for b_ in bad:
    print("CORNER > 45 deg:", b_)
items = []
for t in board.GetTracks():
    for lay in ([t.GetLayer()] if t.Type() == pcbnew.PCB_TRACE_T else [F, I1, I2, B]):
        items.append((lay, t))
for f in FPS.values():
    for p in f.Pads():
        for lay in (F, I1, I2, B):
            if p.IsOnLayer(lay) and (p.GetAttribute() != pcbnew.PAD_ATTRIB_PTH or lay in (F, B)):
                items.append((lay, p))
CL = FromMM(0.1)
shapes = [(lay, it, it.GetEffectiveShape(lay), it.GetBoundingBox()) for lay, it in items]
viol = []
for i in range(len(shapes)):
    la, a, sa, ba = shapes[i]
    for j in range(i + 1, len(shapes)):
        lb, b, sb, bb = shapes[j]
        if la != lb or (a.GetNetCode() == b.GetNetCode() and a.GetNetCode() > 0):
            continue
        if isinstance(a, pcbnew.PAD) and isinstance(b, pcbnew.PAD) and a.GetParent() == b.GetParent() and a.GetNetCode() == 0:
            continue
        bx = pcbnew.BOX2I(ba.GetPosition(), ba.GetSize()); bx.Inflate(CL)
        if bx.Intersects(bb) and sa.Collide(sb, CL - 1):
            viol.append((board.GetLayerName(la), a.GetNetname(), b.GetNetname(),
                         tuple(round(v, 2) for v in ToMM(a.GetPosition())), tuple(round(v, 2) for v in ToMM(b.GetPosition()))))
for v in viol:
    print("CLEARANCE < 0.1 mm:", v)
nv = sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T)
print("courtyard problems: %d, clearance violations: %d, corners > 45 deg: %d, vias: %d (no stitching grid)"
      % (probs, len(viol), len(bad), nv))

board.Save(OUT)
STACKUP = """    (stackup
      (layer "F.SilkS" (type "Top Silk Screen"))
      (layer "F.Paste" (type "Top Solder Paste"))
      (layer "F.Mask" (type "Top Solder Mask") (thickness 0.015) (epsilon_r 3.8))
      (layer "F.Cu" (type "copper") (thickness 0.035))
      (layer "dielectric 1" (type "prepreg") (thickness 0.2104) (material "7628 (JLC04161H-7628)") (epsilon_r 4.4) (loss_tangent 0.02))
      (layer "In1.Cu" (type "copper") (thickness 0.0152))
      (layer "dielectric 2" (type "core") (thickness 1.065) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
      (layer "In2.Cu" (type "copper") (thickness 0.0152))
      (layer "dielectric 3" (type "prepreg") (thickness 0.2104) (material "7628 (JLC04161H-7628)") (epsilon_r 4.4) (loss_tangent 0.02))
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
b2 = pcbnew.LoadBoard(OUT)
pcbnew.ZONE_FILLER(b2).Fill(b2.Zones())
b2.BuildConnectivity()
conn = b2.GetConnectivity(); conn.RecalculateRatsnest()
print("unrouted connections after zone fill (ratsnest):", conn.GetUnconnectedCount(False))
for e in conn.GetRatsnestForNet(0) if False else []:
    pass
for net in b2.GetNetsByName().values():
    try:
        rn = conn.GetRatsnestForNet(net.GetNetCode())
        if rn and rn.GetUnconnectedCount() if hasattr(rn, "GetUnconnectedCount") else False:
            print("  unrouted net:", net.GetNetname())
    except Exception:
        pass
b2.Save(OUT)
s = open(OUT).read()
if "(stackup" not in s:
    open(OUT, "w").write(re.sub(r"\(setup\n", "(setup\n" + STACKUP, s, count=1))
print("wrote", OUT)
