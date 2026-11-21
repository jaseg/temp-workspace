#!/usr/bin/env python3
"""Layout fragment "phase_trigger": trigger path and 16-tap phase-recovery delay line.

BUF_OUT_T (50 R microstrip) / EXT_CLK (SMA, 49.9 R) -> TMUX136 (local -0.9 V switch ground) -> TLV3801
(+/-2V5, IN- = TRIG_LEVEL) -> 100 R across CMP_P/CMP_N -> CMP_P: 1 uF -> TRF37D73 (120 nH + 47 uH choke)
-> 1 uF -> 12 dB pi pad 82/91/82 -> PH_LINE;  CMP_N: 1 uF -> 49.9 R dummy;  2 x 470 R bridge -> SN65LVDS2
-> COARSE.  Delay line (SPEC decision 4, co-propagating): PSTRB_A / PSTRB_K straight on F.Cu at 35 ps
per tap (loaded), PH_LINE on B.Cu (over a local In2 ground) at 70 ps per tap, up through two vias to each
gate.  Per tap: BAT15-04W, 2 x 0.47 pF C0G, 2.2 k to VTAP_N / VTAP_P, 2 x 1 k summing into a COS3502
half (IN- = VTH = VTAP_TH through 1 k / 100 nF), outputs TAP0..TAP15 to edge pads.  All three lines end
in 49.9 R.  Values: design/lowcost/sim/phase/RESULT.md, SPEC decisions 4-6, 9.

Run:  python3 gen_phase_trigger.py   (writes phase_trigger.kicad_pcb next to this file, prints the
stack-up, the per-tap delay table and the sanity checks).  KiCad 7.0 pcbnew API.  kicad-cli 7 has no
DRC: the checks at the end are this script's own.

Coordinates in mm, origin = centre of the tap-0 diode, +x along the line (far end), +y down
(towards PSTRB_K).  Everything is shifted by ORG on the sheet.
"""
import math, os, tempfile
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "phase_trigger.kicad_pcb")
FPLIB = "/usr/share/kicad/footprints"
ORG = (150.0, 100.0)
mm = pcbnew.FromMM
C0 = 299.792458                      # mm/ns

# ============================================================================= stack-up / line design
# JLC04161H-3313 (1.6 mm): L1 35 um / 3313 prepreg 0.0994 mm er 4.1 / In1 / core 1.265 mm / In2 /
# 3313 prepreg 0.0994 mm / L4 35 um.  F.Cu lines reference In1 (GND), B.Cu lines reference In2,
# which is GND under the delay line.
H, T_CU, ER = 0.0994, 0.035, 4.1
EPS0 = 8.854e-3                      # pF/mm


def microstrip(w, h=H, t=T_CU, er=ER):
    """Hammerstad-Jensen microstrip with Wheeler thickness correction -> (Z0, eps_eff)."""
    def z_air(u):
        f = 6 + (2 * math.pi - 6) * math.exp(-(30.666 / u) ** 0.7528)
        return 60 * math.log(f / u + math.sqrt(1 + 4 / u ** 2))
    u = w / h
    ue = u + (t / h / math.pi) * (1 + math.log(2 * h / t))
    a = 1 + math.log((u ** 4 + (u / 52) ** 2) / (u ** 4 + 0.432)) / 49 + math.log(1 + (u / 18.1) ** 3) / 18.7
    b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
    ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / u) ** (-a * b)
    return z_air(ue) / math.sqrt(ee), ee


def width_for(z):
    lo, hi = 0.02, 2.0
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if microstrip(m)[0] > z else (lo, m)
    return (lo + hi) / 2


def ps_mm(w):
    return math.sqrt(microstrip(w)[1]) * 1e3 / C0


def loaded(tdu, z, cl):
    """Unloaded section (delay tdu ps, Z0 z) + lumped cl pF -> (loaded delay ps, loaded Z)."""
    td = math.sqrt(tdu * (tdu + z * cl))
    return td, z * tdu / td


W50_EXACT = width_for(50.0)
W50 = round(W50_EXACT / 0.01) * 0.01                       # 0.17 mm
W_STR = 0.09               # strobe lines: 73 R would need 0.07 mm; 0.09 mm is the JLC 4-layer minimum
W_LIN = 0.10               # PH_LINE trace (B.Cu over In2 GND), 64.5 R unloaded
W_SIG, W_PWR, W_GND, W_NODE = 0.15, 0.3, 0.25, 0.15
Z_STR, Z_LIN = microstrip(W_STR)[0], microstrip(W_LIN)[0]
# loads per tap: gate 0.4 pF (strobe side, SPEC / task) resp. 0.37 pF (line side, RESULT) plus the excess
# pad capacitance over the 0.0994 mm prepreg (pad area minus the trace that would be there anyway)
C_PAD_STR = EPS0 * ER * (0.56 * 0.62 - W_STR * 0.62) / H    # 0402 hold-cap pad on the strobe line
C_PAD_LIN = EPS0 * ER * (0.70 * 0.45 - W_LIN * 0.70) / H    # SOT-323 pin 3 pad on the line
CL_STR = 0.40 + C_PAD_STR
CL_LIN = 0.37 + C_PAD_LIN
# vias (0.2 / 0.45 mm, F.Cu <-> B.Cu) treated as 1.53 mm line sections in er 4.4 FR4, impedance ~ line
T_VIA = (1.6 - 2 * 0.035) * math.sqrt(4.4) * 1e3 / C0       # ps per via traversal
TD_STR, TD_LIN = 35.0, 70.0


def solve_tdu(z, cl, target):
    lo, hi = 1.0, target
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if loaded(m, z, cl)[0] < target else (lo, m)
    return (lo + hi) / 2


TDU_STR = solve_tdu(Z_STR, CL_STR, TD_STR)
PITCH = round(TDU_STR / ps_mm(W_STR), 3)                    # tap pitch = strobe length per tap
TDU_LIN = solve_tdu(Z_LIN, CL_LIN, TD_LIN)
L_LIN = (TDU_LIN - 2 * T_VIA) / ps_mm(W_LIN)                # trace length per tap (both layers)
NT = 16
XT = [n * PITCH for n in range(NT)]

# ============================================================================= board helpers
_TMP = tempfile.mkdtemp(prefix="phase_trigger_fragment_")
b = pcbnew.NewBoard(os.path.join(_TMP, "phase_trigger.kicad_pcb"))
b.SetCopperLayerCount(4)
for lay, name, typ in ((pcbnew.F_Cu, "F.Cu", pcbnew.LT_SIGNAL), (pcbnew.In1_Cu, "In1.Cu", pcbnew.LT_POWER),
                       (pcbnew.In2_Cu, "In2.Cu", pcbnew.LT_POWER), (pcbnew.B_Cu, "B.Cu", pcbnew.LT_SIGNAL)):
    b.SetLayerName(lay, name)
    b.SetLayerType(lay, typ)
ds = b.GetDesignSettings()
ds.SetBoardThickness(mm(1.6))
ds.m_MinClearance = mm(0.1)
ds.m_TrackMinWidth = mm(0.09)
ds.m_ViasMinSize = mm(0.4)
ds.m_MinThroughDrill = mm(0.2)
nc = ds.m_NetSettings.m_DefaultNetClass
nc.SetClearance(mm(0.1))
nc.SetTrackWidth(mm(0.2))
nc.SetViaDiameter(mm(0.6))
nc.SetViaDrill(mm(0.3))

NETS, FPS, ROUTES = {}, {}, {}
RR = pcbnew.PAD_SHAPE_ROUNDRECT
CIRC = pcbnew.PAD_SHAPE_CIRCLE


def net(name):
    if name not in NETS:
        n = pcbnew.NETINFO_ITEM(b, name)
        b.Add(n)
        NETS[name] = n
    return NETS[name]


def P(x, y):
    return pcbnew.VECTOR2I(mm(x + ORG[0]), mm(y + ORG[1]))


def loc(v):
    return (pcbnew.ToMM(v.x) - ORG[0], pcbnew.ToMM(v.y) - ORG[1])


def _finish(fp, ref, val):
    fp.SetReference(ref)
    fp.SetValue(val)
    fp.Reference().SetLayer(pcbnew.F_Fab)
    fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.3), mm(0.3)))
    fp.Reference().SetTextThickness(mm(0.05))
    fp.Reference().SetPosition(fp.GetPosition())
    fp.Value().SetVisible(False)
    b.Add(fp)
    FPS[ref] = fp
    return fp


def place(lib, name, ref, val, x, y, rot, nets, cond=None):
    """Library footprint. rot may be None: then the first of 0/90/180/270 for which cond(pads) holds."""
    fp = pcbnew.FootprintLoad(os.path.join(FPLIB, lib + ".pretty"), name)
    fp.SetPosition(P(x, y))
    for r in ([rot] if rot is not None else [0, 90, 180, 270]):
        fp.SetOrientationDegrees(r)
        pp = {p.GetNumber(): (pcbnew.ToMM(p.GetPosition().x) - ORG[0] - x, pcbnew.ToMM(p.GetPosition().y) - ORG[1] - y)
              for p in fp.Pads()}
        if cond is None or cond(pp):
            break
    else:
        raise RuntimeError(f"no rotation for {ref}")
    for pad_ in fp.Pads():
        if pad_.GetNumber() in nets:
            pad_.SetNet(net(nets[pad_.GetNumber()]))
    return _finish(fp, ref, val)


def two(kind, ref, val, x, y, orient, na, nb, size="0402"):
    """2-terminal part. orient 'h': na left / nb right; 'v': na up / nb down."""
    lib, name = {"R": ("Resistor_SMD", "R_0402_1005Metric"), "C": ("Capacitor_SMD", "C_0402_1005Metric"),
                 "L": ("Inductor_SMD", "L_0402_1005Metric"), "L1008": ("Inductor_SMD", "L_1008_2520Metric")}[kind]
    if orient == "h":
        return place(lib, name, ref, val, x, y, 0, {"1": na, "2": nb})
    return place(lib, name, ref, val, x, y, 90, {"1": nb, "2": na})      # rot 90: pad 1 at +y (down)


def custom(ref, val, x, y, pads, crt):
    fp = pcbnew.FOOTPRINT(b)
    fp.SetFPID(pcbnew.LIB_ID("phase_trigger_fragment", val))
    for num, dx, dy, sx, sy, nn, shape in pads:
        pd = pcbnew.PAD(fp)
        pd.SetNumber(num)
        pd.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pd.SetShape(shape)
        if shape == RR:
            pd.SetRoundRectRadiusRatio(0.1)
        pd.SetLayerSet(pd.SMDMask())
        pd.SetSize(pcbnew.VECTOR2I(mm(sx), mm(sy)))
        pd.SetPosition(pcbnew.VECTOR2I(mm(dx), mm(dy)))
        pd.SetPos0(pcbnew.VECTOR2I(mm(dx), mm(dy)))
        if nn:
            pd.SetNet(net(nn))
        fp.Add(pd)
    cx, cy = crt
    if cx > 0:
        pts = [(-cx, -cy), (cx, -cy), (cx, cy), (-cx, cy), (-cx, -cy)]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            s = pcbnew.FP_SHAPE(fp, pcbnew.SHAPE_T_SEGMENT)
            s.SetLayer(pcbnew.F_CrtYd)
            s.SetWidth(mm(0.05))
            s.SetStart0(pcbnew.VECTOR2I(mm(x0), mm(y0)))
            s.SetEnd0(pcbnew.VECTOR2I(mm(x1), mm(y1)))
            s.SetDrawCoord()
            fp.Add(s)
    fp.SetPosition(P(x, y))
    return _finish(fp, ref, val)


def testpad(ref, nn, x, y, label=None, lx=0.0, ly=-1.0, size=0.45):
    custom(ref, "TestPoint_Pad_D1.0mm", x, y, [("1", 0, 0, 1.0, 1.0, nn, CIRC)], (0.75, 0.75))
    text(label or nn, x + lx, y + ly, size)


def iface(ref, nn, x, y):
    custom(ref, "IF_" + nn, x, y, [("1", 0, 0, 0.6, 0.5, nn, RR)], (0, 0))


def pad(ref, num):
    for p in FPS[ref].Pads():
        if p.GetNumber() == num or (num[0] == "@" and p.GetNetname() == num[1:]):
            return loc(p.GetPosition())
    raise KeyError((ref, num))


def track(netname, width, pts, layer=pcbnew.F_Cu, name=None):
    pts = [pad(*p) if isinstance(p[0], str) else p for p in pts]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if abs(x0 - x1) < 1e-6 and abs(y0 - y1) < 1e-6:
            continue
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(P(x0, y0))
        t.SetEnd(P(x1, y1))
        t.SetWidth(mm(width))
        t.SetLayer(layer)
        t.SetNet(net(netname))
        b.Add(t)
        if name:
            ROUTES.setdefault(name, []).append((x0, y0, x1, y1))
    return pts


def via(x, y, netname, drill=0.3, dia=0.6):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(P(x, y))
    v.SetDrill(mm(drill))
    v.SetWidth(mm(dia))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetNet(net(netname))
    b.Add(v)
    return v


def svia(x, y, netname):                        # small via 0.2 / 0.45 mm
    return via(x, y, netname, 0.2, 0.45)


def text(s, x, y, size=0.5, layer=pcbnew.F_SilkS, rot=0):
    t = pcbnew.PCB_TEXT(b)
    t.SetText(s)
    t.SetPosition(P(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * 0.15))
    t.SetTextAngleDegrees(rot)
    b.Add(t)
    return t


def line(x0, y0, x1, y1, layer=pcbnew.Edge_Cuts, w=0.1):
    s = pcbnew.PCB_SHAPE(b)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(P(x0, y0))
    s.SetEnd(P(x1, y1))
    s.SetLayer(layer)
    s.SetWidth(mm(w))
    b.Add(s)


def rect_pts(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def zone(netname, layers, pts, clearance=0.25, prio=0, rule=False):
    z = pcbnew.ZONE(b)
    ls = pcbnew.LSET()
    for l in layers:
        ls.AddLayer(l)
    z.SetLayerSet(ls)
    if rule:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowTracks(False)
        z.SetDoNotAllowVias(False)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
    else:
        z.SetNet(net(netname))
        z.SetLocalClearance(mm(clearance))
        z.SetMinThickness(mm(0.2))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetAssignedPriority(prio)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(mm(x + ORG[0]), mm(y + ORG[1]))
    b.Add(z)
    return z


# ============================================================================= outline
X15 = XT[-1]
BX0, BY0, BX1, BY1 = -42.0, -16.3, X15 + 7.5, 8.3
for a, c in zip(rect_pts(BX0, BY0, BX1, BY1), rect_pts(BX0, BY0, BX1, BY1)[1:] + [(BX0, BY0)]):
    line(*a, *c)

# ============================================================================= TMUX136 (U301)
XU1, XU2 = -32.5, -28.0
# TMUX136 RSE (UQFN-10 1.5 x 2 mm, TI RSE0010A land pattern = KiCad Texas_UQFN-10_1.5x2mm_P0.5mm)
place("Package_DFN_QFN", "Texas_UQFN-10_1.5x2mm_P0.5mm", "U301", "TMUX136", XU1, 0.25, 0,
      {"1": "TRIG_A", "2": "VSW_GND", "3": "EXT_CLK", "4": "VSW_GND", "5": "VSW_GND", "6": "VSW_GND",
       "8": "TRIG_COM", "9": "TRIG_SEL_S", "10": "+2V5"})
# BUF_OUT_T: 50 R line from the input fragment (49.9 R + 0 R there) to A1 (high-impedance end)
iface("X1", "BUF_OUT_T", BX0 + 0.5, -3.5)
track("BUF_OUT_T", W50, [("X1", "1"), (XU1 - 3.0, -3.5), (XU1 - 1.5, -2.0), (XU1 - 1.5, -0.9)],
      name="BUF_OUT_T line")
# net change at the pin: TRIG_A = BUF_OUT_T (same copper); keep one net name
for p in FPS["U301"].Pads():
    if p.GetNumber() == "1":
        p.SetNet(net("BUF_OUT_T"))
track("BUF_OUT_T", W50, [(XU1 - 1.5, -0.9), (XU1 - 1.1, -0.5), ("U301", "1")], name="BUF_OUT_T line")
# EXT_CLK: SMA edge launch -> 49.9 R at the pin -> B1
YS_SMA = 1.4
place("Connector_Coaxial", "SMA_Samtec_SMA-J-P-X-ST-EM1_EdgeMount", "J301", "SMA EXT_CLK", BX0 + 2.1, YS_SMA, None,
      {"1": "EXT_CLK", "2": "GND"}, cond=lambda pp: pp["1"][0] < -0.1)
two("R", "R301", "49.9", XU1 - 2.4, YS_SMA + 0.48, "v", "EXT_CLK", "GND")
track("EXT_CLK", W50, [("J301", "1"), (XU1 - 2.4, YS_SMA)], name="EXT_CLK line")
track("EXT_CLK", W50, [(XU1 - 2.4, YS_SMA), (XU1 - 1.5, 0.5), ("U301", "3")], name="EXT_CLK line")
track("GND", W_GND, [("R301", "@GND"), (XU1 - 2.4, 3.0)])
svia(XU1 - 2.4, 3.0, "GND")
# unused channel / EN / GND pin -> VSW_GND
track("VSW_GND", W_SIG, [("U301", "4"), ("U301", "5"), ("U301", "6")])
track("VSW_GND", W_SIG, [("U301", "2"), (XU1 - 1.0, 0.0)])
svia(XU1 - 1.0, 0.0, "VSW_GND")
# VCC (+2V5) decoupled to the switch ground
two("C", "C301", "100n", XU1, -2.15, "v", "VSW_GND", "+2V5")
track("+2V5", W_SIG, [("U301", "10"), ("C301", "@+2V5"), (XU1 - 0.55, -1.67)])
svia(XU1 - 0.55, -1.67, "+2V5")                                 # In2 +2V5 zone
track("VSW_GND", W_SIG, [("C301", "@VSW_GND"), (XU1, -3.0)])
svia(XU1, -3.0, "VSW_GND")
track("VSW_GND", W_SIG, [(XU1, -3.0), (XU1 - 0.95, -2.05), (XU1 - 1.0, 0.0), (XU1 - 1.0, 1.4)], layer=pcbnew.B_Cu)
svia(XU1 - 1.0, 1.4, "VSW_GND")
# local switch ground -0.9 V: 2.7 k to -2V5, 1.5 k to GND, 100 n + 1 n at pin 5
for i, (kind, ref, val, other) in enumerate((("R", "R304", "2.7k", "-2V5"), ("C", "C303", "1n C0G", "GND"),
                                             ("C", "C302", "100n", "GND"), ("R", "R303", "1.5k", "GND"))):
    x = XU1 - 1.0 + i
    two(kind, ref, val, x, 2.7, "v", "VSW_GND", other)
    track(other, W_GND, [(ref, "@" + other), (x, 3.9)])
    svia(x, 3.9, other)
track("VSW_GND", W_SIG, [(XU1 - 1.0, 2.22), (XU1 + 2.0, 2.22)])
track("VSW_GND", W_SIG, [("U301", "5"), (XU1, 2.22)])
track("VSW_GND", W_SIG, [(XU1 - 1.0, 1.4), (XU1 - 1.0, 2.22)])
# SEL: TRIG_SEL -> 10 k -> SEL, 18 k to -2V5
two("R", "R305", "10k", XU1 + 1.1, -2.2, "v", "TRIG_SEL", "TRIG_SEL_S")
two("R", "R306", "18k", XU1 + 2.1, -2.2, "v", "-2V5", "TRIG_SEL_S")
track("TRIG_SEL_S", W_SIG, [("U301", "9"), (XU1 + 1.1, -0.5), ("R305", "@TRIG_SEL_S"), ("R306", "@TRIG_SEL_S")])
track("-2V5", W_SIG, [("R306", "@-2V5"), (XU1 + 2.1, -3.4)])
svia(XU1 + 2.1, -3.4, "-2V5")
testpad("TP301", "TRIG_SEL", XU1 + 1.1, -6.0, ly=-1.6, size=0.35)
track("TRIG_SEL", W_SIG, [("R305", "@TRIG_SEL"), (XU1 + 1.1, -6.0)])

# ============================================================================= TLV3801 (U302)
# WSON-8 DSG, rotated: bottom row (y = 0) IN+ 5, VCC 6, VCC 7, OUT+ 8; top row (y = -1.9) IN- 4, VEE 3,
# GND 2, OUT- 1; exposed pad = VEE.
place("Package_SON", "WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm", "U302", "TLV3801", XU2, -0.95, None,
      {"1": "CMP_N", "2": "GND", "3": "-2V5", "4": "TRIG_LEVEL", "5": "TRIG_COM", "6": "+2V5", "7": "+2V5",
       "8": "CMP_P", "9": "-2V5"},
      cond=lambda pp: pp["5"][0] < -0.5 and pp["8"][0] > 0.5 and pp["8"][1] > 0.5)
track("TRIG_COM", W50, [("U301", "8"), ("U302", "5")], name="TRIG_COM")
# VCC pins 6/7 -> 100 n below; +2V5 from the In2 zone
two("C", "C304", "100n", XU2 + 0.7, 1.6, "v", "+2V5", "GND")
track("+2V5", W_SIG, [("U302", "6"), ("U302", "7")])
track("+2V5", W_SIG, [(XU2, 0.0), (XU2, 0.6), (XU2 + 0.7, 0.6), ("C304", "@+2V5"), (XU2 + 1.4, 1.12)])
svia(XU2 + 1.4, 1.12, "+2V5")
track("GND", W_GND, [("C304", "@GND"), (XU2 + 0.7, 2.8)])
svia(XU2 + 0.7, 2.8, "GND")
# VEE = pin 3 + exposed pad; 100 n; EP vias to the B.Cu -2V5 feed
track("-2V5", W_SIG, [("U302", "3"), ("U302", "9")])
for dx in (-0.4, 0.4):
    svia(XU2 + dx, -0.95, "-2V5")
two("C", "C305", "100n", XU2 - 0.25, -3.5, "v", "GND", "-2V5")
track("-2V5", W_SIG, [("U302", "3"), ("C305", "@-2V5")])
track("GND", W_GND, [("C305", "@GND"), (XU2 - 0.25, -4.4)])
svia(XU2 - 0.25, -4.4, "GND")
track("GND", W_SIG, [("U302", "2"), (XU2 + 0.4, -2.7)])
svia(XU2 + 0.4, -2.7, "GND")
# IN- = TRIG_LEVEL, 10 nF at the pin, feed on B.Cu to the bottom-edge pad
two("C", "C306", "10n", XU2 - 1.3, -3.5, "v", "GND", "TRIG_LEVEL")
track("TRIG_LEVEL", W_SIG, [("U302", "4"), (XU2 - 1.3, -1.9), ("C306", "@TRIG_LEVEL")])
track("GND", W_GND, [("C306", "@GND"), (XU2 - 1.3, -4.5)])
svia(XU2 - 1.3, -4.5, "GND")
track("TRIG_LEVEL", W_SIG, [(XU2 - 1.3, -1.9), (XU2 - 1.3, -1.25)])
svia(XU2 - 1.3, -1.25, "TRIG_LEVEL")
track("TRIG_LEVEL", W_SIG, [(XU2 - 1.3, -1.25), (XU2 - 1.3, 6.4)], layer=pcbnew.B_Cu)
svia(XU2 - 1.3, 6.4, "TRIG_LEVEL")
testpad("TP302", "TRIG_LEVEL", XU2 - 1.3, 7.4, lx=-2.7, ly=0.0, size=0.35)
track("TRIG_LEVEL", W_SIG, [(XU2 - 1.3, 6.4), (XU2 - 1.3, 7.4)])
# -2V5 feed on B.Cu: EP -> trunk y=-4.6 -> R306, R304 -> test pad
track("-2V5", W_PWR, [(XU2 + 0.4, -0.95), (XU2 + 1.4, -0.95), (XU2 + 1.4, -5.0), (XU1 - 3.6, -5.0)],
      layer=pcbnew.B_Cu)
track("-2V5", W_PWR, [(XU1 + 2.1, -3.4), (XU1 + 2.1, -5.0)], layer=pcbnew.B_Cu)
track("-2V5", W_PWR, [(XU1 - 1.0, 3.9), (XU1 - 1.6, 4.5), (XU1 - 3.6, 4.5), (XU1 - 3.6, -5.0), (XU1 - 3.6, -5.1)],
      layer=pcbnew.B_Cu)
via(XU1 - 3.6, -5.1, "-2V5")
testpad("TP303", "-2V5", XU1 - 3.6, -6.0, size=0.35)
track("-2V5", W_PWR, [(XU1 - 3.6, -5.1), (XU1 - 3.6, -6.0)])
testpad("TP304", "+2V5", XU1 - 1.4, -6.0, size=0.35)
via(XU1 - 1.4, -6.95, "+2V5")
track("+2V5", W_PWR, [(XU1 - 1.4, -6.95), (XU1 - 1.4, -6.0)])

# ============================================================================= outputs, 100 R, bridge, dummy
XR = XU2 + 2.05
two("R", "R307", "100", XR, -0.95, "v", "CMP_N", "CMP_P")
track("CMP_P", W50, [("U302", "8"), (XR, 0.0)], name="CMP_P")
track("CMP_P", W_SIG, [(XR, 0.0), ("R307", "@CMP_P")])
track("CMP_N", W50, [("U302", "1"), (XR, -1.9)], name="CMP_N")
track("CMP_N", W_SIG, [(XR, -1.9), ("R307", "@CMP_N")])
two("C", "C307", "1u", XR, -2.95, "v", "CMP_N_DUM", "CMP_N")
two("R", "R308", "49.9", XR, -4.9, "v", "GND", "CMP_N_DUM")
track("CMP_N", W50, [(XR, -1.9), ("C307", "@CMP_N")])
track("CMP_N_DUM", W50, [("C307", "@CMP_N_DUM"), ("R308", "@CMP_N_DUM")])
track("GND", W_GND, [("R308", "@GND"), (XR, -6.1)])
svia(XR, -6.1, "GND")
XB = XR + 1.2
XU4 = XB + 1.1375
place("Package_TO_SOT_SMD", "SOT-23-5", "U304", "SN65LVDS2", XU4, 5.3, 180,
      {"1": "+3V3", "2": "GND", "3": "LVDS_A", "4": "LVDS_B", "5": "COARSE"})
XA = pad("U304", "3")[0]
two("R", "R310", "470", XB, -2.38, "v", "LVDS_B", "CMP_N")
two("R", "R309", "470", XA, 0.6, "v", "CMP_P", "LVDS_A")
track("CMP_N", W50, [(XR, -1.9), ("R310", "@CMP_N")], name="CMP_N")
track("LVDS_B", W_SIG, [("R310", "@LVDS_B"), (XB, -3.6)])
svia(XB, -3.6, "LVDS_B")
track("LVDS_B", W_SIG, [(XB, -3.6), (XB, 3.3)], layer=pcbnew.B_Cu)
svia(XB, 3.3, "LVDS_B")
track("LVDS_B", W_SIG, [(XB, 3.3), ("U304", "4")])
track("LVDS_A", W_SIG, [("R309", "@LVDS_A"), ("U304", "3")])
two("C", "C310", "100n", XU4 + 3.0, 6.25, "h", "+3V3", "GND")
track("+3V3", W_SIG, [("U304", "1"), ("C310", "@+3V3")])
via(XU4 + 2.52, 7.1, "+3V3")
track("+3V3", W_SIG, [("C310", "@+3V3"), (XU4 + 2.52, 7.1)])
track("GND", W_GND, [("C310", "@GND"), (XU4 + 3.48, 7.1)])
svia(XU4 + 3.48, 7.1, "GND")
track("GND", W_SIG, [("U304", "2"), (XU4 + 2.3, 5.3)])
svia(XU4 + 2.3, 5.3, "GND")
xc5 = pad("U304", "5")[0]
testpad("TP305", "COARSE", xc5 - 1.8, 7.4, ly=-1.0)
track("COARSE", W_SIG, [("U304", "5"), (xc5 - 0.8, 6.25), (xc5 - 1.8, 7.25)])

# ============================================================================= TRF37D73 line driver (U303)
XU3 = -17.0
C_IN_X = -19.6
two("C", "C308", "1u", C_IN_X, 0.0, "h", "CMP_P", "TRF_IN")
track("CMP_P", W50, [(XR, 0.0), ("C308", "1")], name="CMP_P")
place("Package_SON", "WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm", "U303", "TRF37D73", XU3, 0.25, 0,
      {"1": "+3V3", "2": "TRF_IN", "3": "GND", "4": "GND", "5": "GND", "6": "GND", "7": "TRF_OUT", "8": "GND",
       "9": "GND"})
track("TRF_IN", W50, [("C308", "2"), ("U303", "2")], name="TRF_IN")
for pn in ("3", "4", "5", "6", "8"):
    x, y = pad("U303", pn)
    track("GND", W_SIG, [(x, y), (XU3, y)])
for dy in (-0.55, 0.0, 0.55):
    via(XU3, 0.25 + dy, "GND", 0.2, 0.4)
# VCC pin 1: 1 n + 100 n, +3V3 via to In2
two("C", "C311", "1n", XU3 - 1.45, -2.4, "v", "GND", "+3V3")
two("C", "C312", "100n", XU3 - 0.4, -2.4, "v", "GND", "+3V3")
track("+3V3", W_GND, [("U303", "1"), (XU3 - 1.45, -0.5), ("C311", "@+3V3"), ("C312", "@+3V3"), (XU3 + 0.4, -1.92)])
via(XU3 + 0.4, -1.92, "+3V3")
for c in ("C311", "C312"):
    x, y = pad(c, "@GND")
    track("GND", W_GND, [(x, y), (x, y - 0.75)])
    svia(x, y - 0.75, "GND")
# output: choke 120 nH (high SRF) + 47 uH to +3V3, 1 uF, 12 dB pi pad
XL = -14.9
two("C", "C309", "1u", -14.4, 0.0, "h", "TRF_OUT", "PAD_IN")
track("TRF_OUT", W50, [("U303", "7"), ("C309", "1")], name="TRF_OUT")
two("L", "L301", "120n", XL, -1.45, "v", "TRF_BIAS", "TRF_OUT")
two("L1008", "L302", "47u", XL, -4.4, "v", "+3V3", "TRF_BIAS")
track("TRF_OUT", W_SIG, [(XL, 0.0), ("L301", "@TRF_OUT")])
track("TRF_BIAS", W_PWR, [("L301", "@TRF_BIAS"), ("L302", "@TRF_BIAS")])
two("C", "C313", "1n", XL - 1.9, -7.4, "v", "GND", "+3V3")
two("C", "C314", "100n", XL + 1.9, -7.4, "v", "GND", "+3V3")
yl2 = pad("L302", "@+3V3")[1]
track("+3V3", W_PWR, [("L302", "@+3V3"), (XL, -6.5)])
track("+3V3", W_PWR, [(XL - 1.9, -6.5), (XL + 1.9, -6.5)])
for cx in (XL - 1.9, XL + 1.9):
    track("+3V3", W_PWR, [(cx, -6.5), (cx, -6.92)])
via(XL, -6.5, "+3V3")
for c in ("C313", "C314"):
    x, y = pad(c, "@GND")
    track("GND", W_GND, [(x, y), (x, y - 0.7)])
    svia(x, y - 0.7, "GND")
two("R", "R311", "82", -12.9, 0.48, "v", "PAD_IN", "GND")
two("R", "R312", "91", -11.3, 0.0, "h", "PAD_IN", "PH_LINE")
two("R", "R313", "82", -9.7, 0.48, "v", "PH_LINE", "GND")
track("PAD_IN", W50, [("C309", "2"), ("R312", "1")], name="pad")
for r in ("R311", "R313"):
    x, y = pad(r, "@GND")
    track("GND", W_GND, [(x, y), (x, y + 0.75)])
    svia(x, y + 0.75, "GND")
X_LAUNCH = -8.4
track("PH_LINE", W50, [("R312", "2"), (X_LAUNCH, 0.0)], name="PH_LINE launch")
svia(X_LAUNCH, 0.0, "PH_LINE")
track("PH_LINE", W50, [(X_LAUNCH, 0.0), (-1.4, 0.0)], layer=pcbnew.B_Cu, name="PH_LINE launch")
track("PH_LINE", W_LIN, [(-1.4, 0.0), (0.35, 0.0)], layer=pcbnew.B_Cu, name="PH_LINE launch")
testpad("TP306", "+3V3", -19.0, -6.0)
via(-19.0, -5.0, "+3V3")
track("+3V3", W_PWR, [(-19.0, -5.0), (-19.0, -6.0)])
testpad("TP307", "GND", -23.5, -6.0)
svia(-23.5, -5.0, "GND")
track("GND", W_PWR, [(-23.5, -5.0), (-23.5, -6.0)])
testpad("TP308", "GND", -18.0, 7.4, lx=1.4, ly=0.0)
svia(-18.0, 6.4, "GND")
track("GND", W_PWR, [(-18.0, 6.4), (-18.0, 7.4)])

# ============================================================================= delay line: strobe launch
YL = 2.73                                       # |y| of PSTRB_A (-) / PSTRB_K (+)
YR = 4.35                                       # |y| of the VTAP_N (-) / VTAP_P (+) rails
XS = -4.0
for s, nn, ref in ((-1, "PSTRB_A", "X2"), (+1, "PSTRB_K", "X3")):
    iface(ref, nn, XS, 6.4 * s)
    track(nn, W50, [(XS, 6.4 * s), (XS, (YL + 0.4) * s), (XS + 0.4, YL * s), (-1.6, YL * s)],
          name=f"{nn} launch")
    track(nn, W_STR, [(-1.6, YL * s), (XT[0] - 1.0, YL * s)], name=f"{nn} launch")
    text(nn, XS - 2.2, 6.4 * s, 0.5)
    text("strobe in", XS - 2.2, 6.4 * s + 0.75 * (1 if s > 0 else -1), 0.35)

# ============================================================================= tap cells (loop)
LIN_TAP = {}            # n -> list of (x0, y0, x1, y1) of PH_LINE copper from V_in(n) to V_in(n+1)
CUT = []                # In1 ground cut-outs under the hold nodes
KEEP_TOP = []
VIA_IN, VIA_OUT = 0.35, 1.65
CH = 0.3                                        # 45 degree chamfer of the B.Cu meander corners


def meander_depth(L, run):
    """Depth D of the U (down from y=0) so that top segment + U = L. run = horizontal B.Cu length."""
    top = VIA_OUT - VIA_IN
    # U: down D, across run, up D, two chamfered corners
    return (L - top - run + 2 * (2 * CH - CH * math.sqrt(2))) / 2


D_U = meander_depth(L_LIN, PITCH - (VIA_OUT - VIA_IN))
for n, x in enumerate(XT):
    na, nk, sm = f"TAP{n}_A", f"TAP{n}_K", f"TAP{n}_IN"
    place("Package_TO_SOT_SMD", "SOT-323_SC-70", f"D{n + 1:02d}", "BAT15-04W", x, 0.0, 0,
          {"1": na, "2": nk, "3": "PH_LINE"})
    two("C", f"CA{n:02d}", "0.47p C0G", x - 1.0, -(YL - 0.48), "v", "PSTRB_A", na)
    two("C", f"CK{n:02d}", "0.47p C0G", x - 1.0, +(YL - 0.48), "v", nk, "PSTRB_K")
    two("R", f"RNA{n:02d}", "2.2k", x, -YL, "v", "VTAP_N", na)
    two("R", f"RSA{n:02d}", "1k", x + 1.0, -YL, "v", sm, na)
    two("R", f"RNK{n:02d}", "2.2k", x, +YL, "v", nk, "VTAP_P")
    two("R", f"RSK{n:02d}", "1k", x + 1.0, +YL, "v", nk, sm)
    for s, node, pin in ((-1, na, "1"), (+1, nk, "2")):
        yb = (YL - 0.96) * s                    # node bus = hold-cap node pad row
        track(node, W_NODE, [(x - 1.0, 0.65 * s), (x - 1.0, yb)])
        track(node, W_NODE, [(x - 1.0, yb), (x + 1.0, yb)])
        track(node, W_NODE, [(x, yb), (x, (YL - 0.48) * s)])
        track(node, W_NODE, [(x + 1.0, yb), (x + 1.0, (YL - 0.48) * s)])
        rail = "VTAP_N" if s < 0 else "VTAP_P"
        track(rail, W_SIG, [(x, (YL + 0.48) * s), (x, YR * s)])
        track(sm, W_SIG, [(x + 1.0, (YL + 0.48) * s), (x + 1.0, 3.8 * s)])
        svia(x + 1.0, 3.8 * s, sm)
        CUT.append(rect_pts(x - 1.45, 0.35 * s, x + 1.45, (YL - 0.28) * s))
    KEEP_TOP.append(rect_pts(x - 1.7, -(YL - 0.2), x + 1.7, YL - 0.2))
    # summing node on B.Cu between the two line vias of this tap
    track(sm, W_SIG, [(x + 1.0, 3.8), (x + 1.0, -3.8)], layer=pcbnew.B_Cu)
    # PH_LINE: V_in -> pin 3 -> V_out on F.Cu (under the body), then the B.Cu U to the next tap
    svia(x + VIA_IN, 0.0, "PH_LINE")
    svia(x + VIA_OUT, 0.0, "PH_LINE")
    seg = track("PH_LINE", W_LIN, [(x + VIA_IN, 0.0), (x + VIA_OUT, 0.0)], name=f"line top {n}")
    if n < NT - 1:
        xa, xb = x + VIA_OUT, XT[n + 1] + VIA_IN
        pts = [(xa, 0.0), (xa, D_U - CH), (xa + CH, D_U), (xb - CH, D_U), (xb, D_U - CH), (xb, 0.0)]
        track("PH_LINE", W_LIN, pts, layer=pcbnew.B_Cu, name=f"line U {n}")
    if n < NT - 1:
        for s, nn in ((-1, "PSTRB_A"), (+1, "PSTRB_K")):
            track(nn, W_STR, [(x - 1.0, YL * s), (XT[n + 1] - 1.0, YL * s)], name=f"{nn} tap {n}")

# far end: 49.9 R terminations of all three lines
XE = X15 + 2.8
for s, nn, ref in ((-1, "PSTRB_A", "R402"), (+1, "PSTRB_K", "R403")):
    two("R", ref, "49.9", XE, YL * s, "h", nn, "GND")
    track(nn, W_STR, [(X15 - 1.0, YL * s), (XE - 0.6, YL * s)], name=f"{nn} end")
    track(nn, W50, [(XE - 0.6, YL * s), (ref, "1")], name=f"{nn} end")
    track("GND", W_GND, [(ref, "2"), (XE + 1.1, YL * s)])
    svia(XE + 1.1, YL * s, "GND")
track("PH_LINE", W_LIN, [(X15 + VIA_OUT, 0.0), (X15 + 2.4, 0.0)], layer=pcbnew.B_Cu, name="PH_LINE end")
svia(X15 + 2.4, 0.0, "PH_LINE")
two("R", "R401", "49.9", X15 + 3.3, 0.0, "h", "PH_LINE", "GND")
track("PH_LINE", W_LIN, [(X15 + 2.4, 0.0), ("R401", "1")], name="PH_LINE end")
track("GND", W_GND, [("R401", "2"), (X15 + 4.4, 0.0)])
svia(X15 + 4.4, 0.0, "GND")
text("50R", X15 + 3.3, -0.75, 0.35)

# VTAP rails (F.Cu) with 100 nF every two taps, test pads at the far end
for s, rail, tp in ((-1, "VTAP_N", "TP402"), (+1, "VTAP_P", "TP403")):
    track(rail, W_PWR, [(XT[0] - 0.6, YR * s), (X15 + 6.0, YR * s)])
    testpad(tp, rail, X15 + 6.0, YR * s + 0.9 * s, ly=1.1 * s, lx=-0.6)
    track(rail, W_PWR, [(X15 + 6.0, YR * s), (X15 + 6.0, YR * s + 0.9 * s)])
    for n in range(0, NT, 2):
        cx = XT[n] + 2.5
        ref = f"C{'N' if s < 0 else 'P'}{n:02d}"
        if s < 0:
            two("C", ref, "100n", cx, -5.1, "v", "GND", rail)
        else:
            two("C", ref, "100n", cx, 5.1, "v", rail, "GND")
        track(rail, W_SIG, [(ref, "@" + rail), (cx, YR * s)])
        track("GND", W_GND, [(ref, "@GND"), (cx, 6.2 * s)])
        svia(cx, 6.2 * s, "GND")

# ============================================================================= comparators COS3502 (SOIC-8)
YC = -10.4
VTH_Y = YC + 0.9
YTP = -14.9
for k in range(NT // 2):
    n0, n1 = 2 * k, 2 * k + 1
    xc = XT[n0] + 1.0 + PITCH / 2
    ref = f"U{11 + k}"
    # inputs (pins 1-4) towards the taps, pin 1 at the left
    place("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm", ref, "COS3502", xc, YC, None,
          {"1": f"TAP{n0}_IN", "2": "VTH", "3": f"TAP{n1}_IN", "4": "VTH", "5": "GND", "6": f"TAP{n1}",
           "7": f"TAP{n0}", "8": "+3V3"},
          cond=lambda pp: pp["1"][1] > 1.0 and pp["1"][0] < pp["4"][0])
    for n, pin in ((n0, "1"), (n1, "3")):
        px, py = pad(ref, pin)
        xs = XT[n] + 1.0
        track(f"TAP{n}_IN", W_SIG, [(xs, -3.8), (xs, -6.3)], layer=pcbnew.B_Cu)
        svia(xs, -6.3, f"TAP{n}_IN")
        track(f"TAP{n}_IN", W_SIG, [(xs, -6.3), (px, py + 0.95), (px, py)])
    for pin in ("2", "4"):
        px, py = pad(ref, pin)
        track("VTH", W_SIG, [(px, py), (px, VTH_Y)])
        svia(px, VTH_Y, "VTH")
    p8, p5 = pad(ref, "8"), pad(ref, "5")
    track("+3V3", W_PWR, [p8, (p8[0], YC - 0.9)])
    svia(p8[0], YC - 0.9, "+3V3")
    track("GND", W_PWR, [p5, (p5[0], YC - 0.9)])
    svia(p5[0], YC - 0.9, "GND")
    cref = f"C{30 + k}"
    two("C", cref, "100n", p5[0] + 1.4, p5[1], "v", "GND", "+3V3")
    track("GND", W_PWR, [(cref, "@GND"), (p5[0], pad(cref, "@GND")[1])])
    xg, yg = pad(cref, "@+3V3")
    track("+3V3", W_PWR, [(xg, yg), (xg, yg + 0.75)])
    svia(xg, yg + 0.75, "+3V3")
    for n, pin, dx in ((n0, "7", -1.6), (n1, "6", +1.6)):
        px, py = pad(ref, pin)
        tpx = xc + dx
        testpad(f"TP{500 + n}", f"TAP{n}", tpx, YTP, ly=-0.95, size=0.4)
        track(f"TAP{n}", W_SIG, [(px, py), (px, py - 1.2), (tpx, YTP)])
track("VTH", W_PWR, [(-1.5, VTH_Y), (pad(f"U{11 + NT // 2 - 1}", "4")[0], VTH_Y)], layer=pcbnew.B_Cu)
# VTH filter: VTAP_TH -> 1 k -> VTH, 100 nF
two("R", "R404", "1k", -2.0, -11.6, "v", "VTAP_TH", "VTH")
two("C", "C404", "100n", -1.0, -11.6, "v", "GND", "VTH")
track("VTH", W_SIG, [("R404", "@VTH"), ("C404", "@VTH"), (-1.0, -10.4), (-1.5, -10.4)])
svia(-1.5, -10.4, "VTH")
track("VTH", W_SIG, [(-1.5, -10.4), (-1.5, VTH_Y)], layer=pcbnew.B_Cu)
x, y = pad("C404", "@GND")
track("GND", W_GND, [(x, y), (x, y - 0.75)])
svia(x, y - 0.75, "GND")
testpad("TP401", "VTAP_TH", -2.0, YTP, ly=-0.95, size=0.4)
track("VTAP_TH", W_SIG, [("R404", "@VTAP_TH"), (-2.0, YTP)])
for ref, x in (("TP404", -4.0), ("TP405", X15 + 6.0)):
    testpad(ref, "GND", x, YTP, ly=-0.95, size=0.4)
    svia(x, YTP + 1.0, "GND")
    track("GND", W_PWR, [(x, YTP), (x, YTP + 1.0)])

# ============================================================================= silkscreen
text("BUF_OUT_T", BX0 + 2.2, -4.4, 0.5)
text("<- input fragment (50R)", BX0 + 3.6, -2.6, 0.35)
text("EXT_CLK", BX0 + 5.2, YS_SMA + 2.0, 0.5)
text("PHASE_TRIGGER fragment (4L JLC04161H-3313)", -24.0, -14.6, 0.6)
text("TMUX136", XU1, -0.9 + 4.2 - 7.5, 0.35)
text("TLV3801", XU2, -3.6, 0.4)
text("TRF37D73", XU3, 2.4, 0.4)
text("12 dB pad", -11.3, -1.0, 0.4)
text("SN65LVDS2", XU4 - 0.2, 3.4, 0.35)
text("PH_LINE (B.Cu) -> 16 taps, 70 ps/tap", 12.0, 7.4, 0.45)
text(f"PSTRB_A/K (F.Cu): 35 ps/tap, pitch {PITCH:.2f} mm", 42.0, 7.4, 0.45)
text("TAP0..TAP15 = COS3502 outputs (3V3) at the top edge", -24.0, -13.4, 0.45)
for n, x in enumerate(XT):
    text(str(n), x - 1.0, 3.55, 0.35, layer=pcbnew.F_SilkS)
text("VTAP_N", -2.0, -YR, 0.35)
text("VTAP_P", -2.0, YR, 0.35)

# ============================================================================= zones
IN = 0.25
outline = rect_pts(BX0 + IN, BY0 + IN, BX1 - IN, BY1 - IN)
zone("GND", [pcbnew.In1_Cu], outline, clearance=0.2)
zone("+3V3", [pcbnew.In2_Cu], outline, clearance=0.3, prio=0)
zone("+2V5", [pcbnew.In2_Cu], rect_pts(BX0 + IN, BY0 + IN, -24.6, BY1 - IN), clearance=0.3, prio=1)
zone("GND", [pcbnew.In2_Cu], rect_pts(-10.0, -3.45, BX1 - IN, BY1 - IN), clearance=0.3, prio=2)
zone("GND", [pcbnew.B_Cu], outline, clearance=0.3)
zone("GND", [pcbnew.F_Cu], outline, clearance=0.3)
for c in CUT:                                    # hold nodes: no In1 ground below (low node capacitance)
    zone(None, [pcbnew.In1_Cu], c, rule=True)
for k in KEEP_TOP:                               # no top pour inside the tap cell
    zone(None, [pcbnew.F_Cu], k, rule=True)


# ============================================================================= stitching vias
def seg_dist(px, py, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy
    u = 0 if L2 == 0 else max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / L2))
    return math.hypot(px - x0 - u * dx, py - y0 - u * dy)


def can_via(x, y, r=0.225, clr=0.18):
    if not (BX0 + 0.6 < x < BX1 - 0.6 and BY0 + 0.6 < y < BY1 - 0.6):
        return False
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            vx, vy = loc(t.GetPosition())
            if math.hypot(vx - x, vy - y) < r + pcbnew.ToMM(t.GetWidth()) / 2 + 0.2:
                return False
            continue
        if t.GetNetname() == "GND":
            continue
        (x0, y0), (x1, y1) = loc(t.GetStart()), loc(t.GetEnd())
        if seg_dist(x, y, x0, y0, x1, y1) < r + pcbnew.ToMM(t.GetWidth()) / 2 + clr:
            return False
    for fp in b.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            x0, y0 = loc(pcbnew.VECTOR2I(bb.GetX(), bb.GetY()))
            x1, y1 = x0 + pcbnew.ToMM(bb.GetWidth()), y0 + pcbnew.ToMM(bb.GetHeight())
            d = math.hypot(max(x0 - x, 0, x - x1), max(y0 - y, 0, y - y1))
            if d < r + (0.15 if p.GetNetname() == "GND" else clr):
                return False
    for c in CUT:
        (cx0, cy0), (cx1, cy1) = c[0], c[2]
        if min(cx0, cx1) - 0.3 < x < max(cx0, cx1) + 0.3 and min(cy0, cy1) - 0.3 < y < max(cy0, cy1) + 0.3:
            return False
    return True


N_STITCH = 0
for name in list(ROUTES):
    if not (name.startswith(("PSTRB", "PH_LINE", "line U", "BUF_OUT_T", "EXT_CLK", "CMP_", "TRF_", "pad",
                             "TRIG_COM"))):
        continue
    off = 0.62
    for (x0, y0, x1, y1) in ROUTES[name]:
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 0.3:
            continue
        nx, ny = -(y1 - y0) / L, (x1 - x0) / L
        nst = max(1, int(L / 0.9))
        for i in range(nst + 1):
            u = i / nst
            for sg in (1, -1):
                xx, yy = x0 + u * (x1 - x0) + sg * nx * off, y0 + u * (y1 - y0) + sg * ny * off
                if can_via(xx, yy):
                    svia(xx, yy, "GND")
                    N_STITCH += 1
for gx in [BX0 + 1.0 + 1.5 * i for i in range(int((BX1 - BX0) / 1.5))]:
    for gy in [BY0 + 1.0 + 1.5 * j for j in range(int((BY1 - BY0) / 1.5))]:
        if can_via(gx, gy, clr=0.35):
            svia(gx, gy, "GND")
            N_STITCH += 1

# ============================================================================= fill, reports, checks
pcbnew.ZONE_FILLER(b).Fill(b.Zones())


def rlen(segs):
    return sum(math.hypot(x1 - x0, y1 - y0) for x0, y0, x1, y1 in segs)


z50, e50 = microstrip(W50)
print("Stack-up: F.Cu / 3313 0.0994 mm er 4.1 / In1 GND / core 1.265 / In2 / 3313 0.0994 / B.Cu, t 35 um")
print(f"  50 R: exact {W50_EXACT:.3f} mm, drawn {W50:.2f} mm -> {z50:.1f} R, eps_eff {e50:.3f}, {ps_mm(W50):.3f} ps/mm")
print(f"  strobe line {W_STR:.2f} mm: Z0 {Z_STR:.1f} R, {ps_mm(W_STR):.3f} ps/mm; load {CL_STR:.3f} pF/tap "
      f"(0.40 gate + {C_PAD_STR:.3f} pad)")
print(f"  PH_LINE {W_LIN:.2f} mm: Z0 {Z_LIN:.1f} R, {ps_mm(W_LIN):.3f} ps/mm; load {CL_LIN:.3f} pF/tap "
      f"(0.37 gate + {C_PAD_LIN:.3f} pad); vias {T_VIA:.1f} ps each, 2 per tap")
print(f"  design: strobe unloaded {TDU_STR:.2f} ps/tap -> pitch {PITCH:.3f} mm; line unloaded {TDU_LIN:.2f} ps/tap "
      f"-> trace {L_LIN:.3f} mm/tap, U depth {D_U:.3f} mm")
print(f"{'tap':>5s} {'PSTRB_A mm':>10s} {'PSTRB_K mm':>10s} {'A ps':>7s} {'K ps':>7s} {'line mm':>8s} {'line ps':>8s}"
      f" {'eff ps':>7s}   (intended 35.0 / 35.0 / 70.0 / 35.0)")
res = []
for n in range(NT - 1):
    la = rlen(ROUTES[f"PSTRB_A tap {n}"])
    lk = rlen(ROUTES[f"PSTRB_K tap {n}"])
    ll = rlen(ROUTES[f"line top {n}"]) + rlen(ROUTES[f"line U {n}"])
    ta, za = loaded(la * ps_mm(W_STR), Z_STR, CL_STR)
    tk, _ = loaded(lk * ps_mm(W_STR), Z_STR, CL_STR)
    tl, zl = loaded(ll * ps_mm(W_LIN) + 2 * T_VIA, Z_LIN, CL_LIN)
    res.append((ta, tk, tl))
    print(f"{n:2d}-{n + 1:<2d} {la:10.3f} {lk:10.3f} {ta:7.2f} {tk:7.2f} {ll:8.3f} {tl:8.2f} {tl - ta:7.2f}")
spread = [max(r[i] for r in res) - min(r[i] for r in res) for i in range(3)]
print(f"spread over the 15 intervals: A {spread[0]:.4f} ps, K {spread[1]:.4f} ps, line {spread[2]:.4f} ps")
print(f"loaded impedance: strobe {za:.1f} R, PH_LINE {zl:.1f} R (terminations 49.9 R)")
for nm in ("BUF_OUT_T line", "EXT_CLK line", "TRIG_COM", "CMP_P", "CMP_N", "TRF_IN", "TRF_OUT",
           "PH_LINE launch", "PSTRB_A launch", "PSTRB_K launch", "PSTRB_A end", "PSTRB_K end", "PH_LINE end"):
    print(f"  {nm:16s} {rlen(ROUTES[nm]):7.3f} mm")
print(f"stitching / ground vias added: {N_STITCH}")

errs = []
fps = list(b.GetFootprints())
boxes = {}
for fp in fps:
    fp.BuildCourtyardCaches()
    c = fp.GetCourtyard(pcbnew.F_CrtYd)
    if c.OutlineCount():
        bb = c.BBox()
        boxes[fp.GetReference()] = (pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()),
                                    pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
refs = sorted(boxes)
for i, r1 in enumerate(refs):
    for r2 in refs[i + 1:]:
        a, c = boxes[r1], boxes[r2]
        ox = min(a[2], c[2]) - max(a[0], c[0])
        oy = min(a[3], c[3]) - max(a[1], c[1])
        if ox > 0.005 and oy > 0.005:
            errs.append(f"courtyard overlap {r1} / {r2} ({ox:.2f} x {oy:.2f} mm)")
CLR = mm(0.1) - 1000
CU = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
tr = list(b.GetTracks())
pads_ = [p for fp in fps for p in fp.Pads() if p.GetNumber()]
items = [(t, t.GetBoundingBox()) for t in tr] + [(p, p.GetBoundingBox()) for p in pads_]
M = mm(0.15)
for i, (t, bt) in enumerate(items):
    if not isinstance(t, pcbnew.PCB_TRACK):
        continue
    for u, bu in items[i + 1:]:
        if u.GetNetCode() == t.GetNetCode():
            continue
        if (bt.GetRight() + M < bu.GetX() or bu.GetRight() + M < bt.GetX() or
                bt.GetBottom() + M < bu.GetY() or bu.GetBottom() + M < bt.GetY()):
            continue
        for lay in CU:
            if t.IsOnLayer(lay) and u.IsOnLayer(lay) and \
                    t.GetEffectiveShape(lay).Collide(u.GetEffectiveShape(lay), CLR):
                who = u.GetParent().GetReference() + "." + u.GetNumber() if isinstance(u, pcbnew.PAD) else "track"
                errs.append(f"clearance {t.GetNetname()} / {u.GetNetname()} ({who}) on {b.GetLayerName(lay)} "
                            f"near {tuple(round(v, 2) for v in loc(t.GetPosition()))}")
                break
for i, p in enumerate(pads_):
    bp = p.GetBoundingBox()
    for q in pads_[i + 1:]:
        if p.GetParent() is q.GetParent() or p.GetNetCode() == q.GetNetCode():
            continue
        bq = q.GetBoundingBox()
        if (bp.GetRight() + M < bq.GetX() or bq.GetRight() + M < bp.GetX() or
                bp.GetBottom() + M < bq.GetY() or bq.GetBottom() + M < bp.GetY()):
            continue
        if p.GetEffectiveShape(pcbnew.F_Cu).Collide(q.GetEffectiveShape(pcbnew.F_Cu), CLR):
            errs.append(f"pad clearance {p.GetParent().GetReference()}.{p.GetNumber()} / "
                        f"{q.GetParent().GetReference()}.{q.GetNumber()}")
print("courtyard / clearance check:", "OK" if not errs else f"{len(errs)} problems")
for e in sorted(set(errs))[:60]:
    print("  ", e)
nonet = [f"{p.GetParent().GetReference()}.{p.GetNumber()}" for p in pads_ if not p.GetNetname()]
print("pads without net (intentional: U301.7 COM2 open):", nonet)

pcbnew.SaveBoard(OUT, b)
STACKUP = """    (stackup
      (layer "F.SilkS" (type "Top Silk Screen"))
      (layer "F.Paste" (type "Top Solder Paste"))
      (layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
      (layer "F.Cu" (type "copper") (thickness 0.035))
      (layer "dielectric 1" (type "prepreg") (thickness 0.0994) (material "3313") (epsilon_r 4.1) (loss_tangent 0.02))
      (layer "In1.Cu" (type "copper") (thickness 0.0152))
      (layer "dielectric 2" (type "core") (thickness 1.265) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
      (layer "In2.Cu" (type "copper") (thickness 0.0152))
      (layer "dielectric 3" (type "prepreg") (thickness 0.0994) (material "3313") (epsilon_r 4.1) (loss_tangent 0.02))
      (layer "B.Cu" (type "copper") (thickness 0.035))
      (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
      (layer "B.Paste" (type "Bottom Solder Paste"))
      (layer "B.SilkS" (type "Bottom Silk Screen"))
      (copper_finish "ENIG")
      (dielectric_constraints no)
    )
"""
with open(OUT) as f:
    s = f.read()
if "(stackup" not in s:
    s = s.replace("  (setup\n", "  (setup\n" + STACKUP, 1)
with open(OUT, "w") as f:
    f.write(s)
print("wrote", OUT)
for ext in (".kicad_pro", ".kicad_prl"):
    pth = OUT[:-len(".kicad_pcb")] + ext
    if os.path.exists(pth):
        os.remove(pth)
