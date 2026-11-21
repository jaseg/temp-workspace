#!/usr/bin/env python3
"""Layout fragment "sampler": BUF802 OUT -> 10 R -> 4-diode bridge (2x BAT15-04W) -> 2.2 pF hold ->
TPH2501 G=+3 -> TPH2501 level shifter -> 33 R / 220 pF -> ADC_IN, plus the sampler strobe output
section (TRF37D73 #2 -> 100 nF -> clip node with 80 ps shorted stub -> CMC balun -> STRB_A/STRB_K).

Values: design/lowcost/sim/sampler/RESULT.md, design/lowcost/sim/strobe/RESULT.md, SPEC decisions 1-3, 9.
Run:  python3 gen_sampler.py   (writes sampler.kicad_pcb next to this file, prints the delay table and
the sanity checks). KiCad 7.0 pcbnew API. kicad-cli 7 has no DRC: the checks below are this script's own.

Local coordinates in mm, origin = centre of the bridge (between D201 and D202), +x towards the strobe
driver, +y down. Everything is shifted by ORG on the sheet. Mirror axis of the strobe paths: y = 0.
"""
import math, os, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sampler.kicad_pcb")
FPLIB = "/usr/share/kicad/footprints"
ORG = (120.0, 100.0)
mm = pcbnew.FromMM

# ----------------------------------------------------------------------------- stack-up / impedance
# JLCPCB JLC04161H-3313 (1.6 mm): L1 35 um / 3313 prepreg 0.0994 mm er 4.1 / L2 15.2 um / core 1.265 mm
# / L3 15.2 um / 3313 prepreg 0.0994 mm / L4 35 um.
H, T_CU, ER = 0.0994, 0.035, 4.1


def microstrip(w, h=H, t=T_CU, er=ER):
    """Hammerstad-Jensen microstrip (Wheeler thickness correction). Returns (Z0, eps_eff)."""
    def z_air(u):
        f = 6 + (2 * math.pi - 6) * math.exp(-(30.666 / u) ** 0.7528)
        return 60 * math.log(f / u + math.sqrt(1 + 4 / u ** 2))
    u = w / h
    du = (t / h / math.pi) * (1 + math.log(2 * h / t))     # Wheeler, w/h > 1/(2 pi)
    ue = u + du
    a = 1 + math.log((u ** 4 + (u / 52) ** 2) / (u ** 4 + 0.432)) / 49 + math.log(1 + (u / 18.1) ** 3) / 18.7
    b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
    ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / u) ** (-a * b)
    return z_air(ue) / math.sqrt(ee), ee


def width_for(z):
    lo, hi = 0.02, 2.0
    for _ in range(60):
        m = (lo + hi) / 2
        if microstrip(m)[0] > z:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


W50_EXACT = width_for(50.0)
W50 = round(W50_EXACT / 0.01) * 0.01           # drawn width
Z50, EEFF = microstrip(W50)
PS_MM = math.sqrt(EEFF) * 1e3 / 299.792458      # ps per mm
W_HOLD, W_GUARD, W_SIG, W_PWR, W_GND = 0.15, 0.12, 0.2, 0.3, 0.25

# ----------------------------------------------------------------------------- board
import tempfile
_TMP = tempfile.mkdtemp(prefix="sampler_fragment_")          # NewBoard writes a project; keep it out of here
b = pcbnew.NewBoard(os.path.join(_TMP, "sampler.kicad_pcb"))
b.SetCopperLayerCount(4)
for lay, name, typ in ((pcbnew.F_Cu, "F.Cu", pcbnew.LT_SIGNAL), (pcbnew.In1_Cu, "In1.Cu", pcbnew.LT_POWER),
                       (pcbnew.In2_Cu, "In2.Cu", pcbnew.LT_POWER), (pcbnew.B_Cu, "B.Cu", pcbnew.LT_SIGNAL)):
    b.SetLayerName(lay, name)
    b.SetLayerType(lay, typ)
ds = b.GetDesignSettings()
ds.SetBoardThickness(mm(1.6))
ds.m_MinClearance = mm(0.1)
ds.m_TrackMinWidth = mm(0.1)
ds.m_ViasMinSize = mm(0.4)
ds.m_MinThroughDrill = mm(0.2)
nc = ds.m_NetSettings.m_DefaultNetClass
nc.SetClearance(mm(0.1))
nc.SetTrackWidth(mm(0.2))
nc.SetViaDiameter(mm(0.6))
nc.SetViaDrill(mm(0.3))

NETS = {}


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


FPS = {}


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


def place(lib, name, ref, val, x, y, rot, nets):
    fp = pcbnew.FootprintLoad(os.path.join(FPLIB, lib + ".pretty"), name)
    fp.SetPosition(P(x, y))
    fp.SetOrientationDegrees(rot)
    for pad in fp.Pads():
        if pad.GetNumber() in nets:
            pad.SetNet(net(nets[pad.GetNumber()]))
    return _finish(fp, ref, val)


def two(kind, ref, val, x, y, orient, na, nb, size="0402"):
    """2-terminal part. orient 'h': na left / nb right; 'v': na up / nb down."""
    lib, name = {"R": ("Resistor_SMD", f"R_{size}_1005Metric" if size == "0402" else f"R_{size}_2012Metric"),
                 "C": ("Capacitor_SMD", f"C_{size}_1005Metric" if size == "0402" else f"C_{size}_2012Metric"),
                 "FB": ("Inductor_SMD", "L_0402_1005Metric"),
                 "L": ("Inductor_SMD", "L_1210_3225Metric")}[kind]
    if orient == "h":
        return place(lib, name, ref, val, x, y, 0, {"1": na, "2": nb})
    return place(lib, name, ref, val, x, y, 90, {"1": nb, "2": na})      # rot 90: pad 1 at +y (down)


def custom(ref, val, x, y, pads, crt, label=None):
    """Footprint from pads [(num, dx, dy, sx, sy, net, shape)], courtyard half sizes crt=(cx, cy)."""
    fp = pcbnew.FOOTPRINT(b)
    fp.SetFPID(pcbnew.LIB_ID("sampler_fragment", val))
    for num, dx, dy, sx, sy, nn, shape in pads:
        pd = pcbnew.PAD(fp)
        pd.SetNumber(num)
        pd.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pd.SetShape(shape)
        if shape == pcbnew.PAD_SHAPE_ROUNDRECT:
            pd.SetRoundRectRadiusRatio(0.1)
        pd.SetLayerSet(pd.SMDMask())
        pd.SetSize(pcbnew.VECTOR2I(mm(sx), mm(sy)))
        pd.SetPosition(pcbnew.VECTOR2I(mm(dx), mm(dy)))
        pd.SetPos0(pcbnew.VECTOR2I(mm(dx), mm(dy)))
        if nn:
            pd.SetNet(net(nn))
        fp.Add(pd)
    cx, cy = crt
    for lay, (ax, ay), wd in ((pcbnew.F_CrtYd, (cx, cy), 0.05), (pcbnew.F_Fab, (cx - 0.25, cy - 0.25), 0.1)):
        if ax <= 0 or ay <= 0:
            continue
        pts = [(-ax, -ay), (ax, -ay), (ax, ay), (-ax, ay), (-ax, -ay)]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            s = pcbnew.FP_SHAPE(fp, pcbnew.SHAPE_T_SEGMENT)
            s.SetLayer(lay)
            s.SetWidth(mm(wd))
            s.SetStart0(pcbnew.VECTOR2I(mm(x0), mm(y0)))
            s.SetEnd0(pcbnew.VECTOR2I(mm(x1), mm(y1)))
            s.SetDrawCoord()
            fp.Add(s)
    fp.SetPosition(P(x, y))
    return _finish(fp, ref, val)


def pad(ref, num):
    """Pad centre by number, or by net name with a leading '@'."""
    for p in FPS[ref].Pads():
        if p.GetNumber() == num or (num[0] == "@" and p.GetNetname() == num[1:]):
            return loc(p.GetPosition())
    raise KeyError((ref, num))


ROUTES = {}          # name -> list of (x0, y0, x1, y1)
TRACKS = []


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
        TRACKS.append(t)
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


def text(s, x, y, size=0.5, layer=pcbnew.F_SilkS, rot=0, just=0):
    t = pcbnew.PCB_TEXT(b)
    t.SetText(s)
    t.SetPosition(P(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * 0.15))
    t.SetTextAngleDegrees(rot)
    t.SetHorizJustify(just)
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
        z.SetDoNotAllowVias(True)
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
BX0, BY0, BX1, BY1 = -8.0, -9.2, 23.5, 13.6
for a, c in zip(rect_pts(BX0, BY0, BX1, BY1), rect_pts(BX0, BY0, BX1, BY1)[1:] + [(BX0, BY0)]):
    line(*a, *c)

RR = pcbnew.PAD_SHAPE_ROUNDRECT
# ============================================================================= input leg + bridge
custom("X1", "IF_BUF_OUT_S", -6.4, 0, [("1", 0, 0, 0.6, 0.5, "BUF_OUT_S", RR)], (0, 0))
two("R", "R201", "10", -4.6, 0, "h", "BUF_OUT_S", "BRG_IN")
place("Package_TO_SOT_SMD", "SOT-323_SC-70", "D201", "BAT15-04W", -1.8, 0, 0,
      {"1": "BRG_A", "2": "BRG_K", "3": "BRG_IN"})
place("Package_TO_SOT_SMD", "SOT-323_SC-70", "D202", "BAT15-04W", 1.8, 0, 0,
      {"1": "BRG_A", "2": "BRG_K", "3": "HOLD"})
track("BUF_OUT_S", W50, [("X1", "1"), ("R201", "1")], name="BUF802 OUT -> R201")
track("BRG_IN", W50, [("R201", "2"), ("D201", "3")], name="R201 -> D201.3 (between D201 pins 1/2)")

XM = (pad("D201", "1")[0] + pad("D202", "1")[0]) / 2      # rail midpoint (-1.0)
for s, rail, bias_n, strb, vb in ((-1, "BRG_A", "BIAS_A_N", "STRB_A", "VBIAS_A"),
                                  (+1, "BRG_K", "BIAS_K_N", "STRB_K", "VBIAS_K")):
    p1 = "1" if s < 0 else "2"
    d1, d2 = pad("D201", p1), pad("D202", p1)
    yr = 1.7 * s
    track(rail, W_SIG, [d1, (d1[0], yr), (XM, yr)], name=f"{rail} rail D201")
    track(rail, W_SIG, [d2, (d2[0], yr), (XM, yr)], name=f"{rail} rail D202")
    ab = "A" if s < 0 else "K"
    r25 = f"R20{2 if s < 0 else 3}"
    c47 = f"C20{1 if s < 0 else 2}"
    rb = f"R20{5 if s < 0 else 6}"
    c10 = f"C20{3 if s < 0 else 4}"
    if s < 0:
        two("R", r25, "24.9", XM, -2.65, "v", bias_n, rail)
        two("C", c47, "47p C0G", XM, -4.55, "v", strb, bias_n)
        two("R", rb, "1k", -2.6, -3.6, "h", vb, bias_n)
        two("C", c10, "10n", -4.3, -3.1, "v", vb, "GND")
    else:
        two("R", r25, "24.9", XM, 2.65, "v", rail, bias_n)
        two("C", c47, "47p C0G", XM, 4.55, "v", bias_n, strb)
        two("R", rb, "1k", -2.6, 3.6, "h", vb, bias_n)
        two("C", c10, "10n", -4.3, 3.1, "v", "GND", vb)
    rp = pad(r25, "1" if s > 0 else "1")
    # resistor pad on the rail side
    rpads = sorted([pad(r25, "1"), pad(r25, "2")], key=lambda q: abs(q[1]))
    cpads = sorted([pad(c47, "1"), pad(c47, "2")], key=lambda q: abs(q[1]))
    track(rail, W_SIG, [(XM, yr), rpads[0]], name=f"{rail} rail R25")
    track(bias_n, W_SIG, [rpads[1], cpads[0]], name=f"{ab} R25 -> C47")
    track(bias_n, W_SIG, [pad(rb, "2"), (XM, 3.6 * s)])
    vpads = sorted([pad(c10, "1"), pad(c10, "2")], key=lambda q: abs(q[1]))
    vb_pad = vpads[1]
    gnd_pad = vpads[0]
    track(vb, W_SIG, [pad(rb, "1"), (vb_pad[0], 3.6 * s), vb_pad])
    track("GND", W_GND, [gnd_pad, (gnd_pad[0], 1.95 * s)])
    via(gnd_pad[0], 1.95 * s, "GND")
    tp = f"TP20{1 if s < 0 else 2}"
    custom(tp, "TestPoint_Pad_D1.0mm", -6.5, 7.6 * s, [("1", 0, 0, 1.0, 1.0, vb, pcbnew.PAD_SHAPE_CIRCLE)], (0.75, 0.75))
    track(vb, W_SIG, [vb_pad, (vb_pad[0], 4.4 * s), (-6.5, 6.6 * s), (-6.5, 7.6 * s)])
    text(vb, -6.5, 8.75 * s, 0.6)

# ============================================================================= hold node, U201
place("Package_TO_SOT_SMD", "SOT-23-5", "U201", "TPH2501", 5.6, -0.95, 0,
      {"1": "HOLD_OUT", "2": "-2V5", "3": "HOLD", "4": "HOLD_FB", "5": "+2V5"})
track("HOLD", W_HOLD, [("D202", "3"), ("U201", "3")], name="hold node D202.3 -> U201.3")
two("C", "C205", "2.2p C0G", 4.0, 1.7, "v", "HOLD", "GND")
track("HOLD", W_HOLD, [(4.0, 0.0), ("C205", "@HOLD")], name="hold node branch -> C205")
track("GND", W_GND, [("C205", "@GND"), (4.0, 2.9)])
via(4.0, 2.9, "GND")
two("R", "R207", "1.00k 1%", 5.09, -3.3, "h", "HOLD_OUT", "HOLD_FB")
track("HOLD_OUT", W_SIG, [("U201", "1"), (4.58, -2.4), ("R207", "1")])
track("HOLD_OUT", W_SIG, [("R207", "1"), (3.7, -3.3)])
via(3.7, -3.3, "HOLD_OUT")
# -IN under the U201 body between the two pad columns, then the guard ring (same net)
track("HOLD_FB", W_HOLD, [("R207", "2"), (5.6, 0.0), ("U201", "4")])
track("HOLD_FB", W_GUARD, [(5.6, -0.475), (1.8, -0.475), (1.8, 1.7), (6.7375, 1.7), (6.7375, 0.0)],
      name="guard ring (HOLD_FB = U201 -IN)")
two("R", "R208", "499 1%", 7.25, 2.6, "h", "HOLD_FB", "GND")
track("HOLD_FB", W_HOLD, [(6.7375, 1.7), ("R208", "1")])
track("GND", W_GND, [("R208", "2"), (8.35, 2.6)])
via(8.35, 2.6, "GND")
# supplies
two("C", "C209", "100n", 2.9, -2.6, "v", "GND", "-2V5")
track("-2V5", W_SIG, [("U201", "2"), (3.3, -0.95), (2.9, -1.35), ("C209", "@-2V5")])
track("-2V5", W_SIG, [("C209", "@-2V5"), (2.05, -2.09)])
via(2.05, -2.09, "-2V5")
track("GND", W_GND, [("C209", "@GND"), (2.9, -3.75)])
via(2.9, -3.75, "GND")
two("C", "C208", "100n", 7.2, -3.6, "v", "GND", "+2V5")
track("+2V5", W_SIG, [("U201", "5"), (6.7375, -2.5), (7.2, -2.9), ("C208", "@+2V5")])
track("+2V5", W_SIG, [("C208", "@+2V5"), (7.95, -3.09)])
via(7.95, -3.09, "+2V5")
track("GND", W_GND, [("C208", "@GND"), (7.2, -4.75)])
via(7.2, -4.75, "GND")
# feeds on B.Cu to the test pads at the top edge
custom("TP203", "TestPoint_Pad_D1.0mm", -0.5, -7.9, [("1", 0, 0, 1.0, 1.0, "-2V5", pcbnew.PAD_SHAPE_CIRCLE)], (0.75, 0.75))
custom("TP204", "TestPoint_Pad_D1.0mm", 7.95, -7.9, [("1", 0, 0, 1.0, 1.0, "+2V5", pcbnew.PAD_SHAPE_CIRCLE)], (0.75, 0.75))
track("-2V5", W_PWR, [(2.05, -2.09), (2.05, -2.6), (-0.5, -5.15), (-0.5, -7.0)], layer=pcbnew.B_Cu)
via(-0.5, -7.0, "-2V5")
track("-2V5", W_PWR, [(-0.5, -7.0), (-0.5, -7.9)])
track("+2V5", W_PWR, [(7.95, -3.09), (7.95, -7.0)], layer=pcbnew.B_Cu)
via(7.95, -7.0, "+2V5")
track("+2V5", W_PWR, [(7.95, -7.0), (7.95, -7.9)])
text("-2V5", -0.5, -8.75, 0.6)
text("+2V5", 7.95, -8.75, 0.6)
# U201 OUT to the level shifter on B.Cu (outside the hold cut-out)
track("HOLD_OUT", W_SIG, [(3.7, -3.3), (6.0, -3.3), (6.0, 4.0), (8.0, 6.0), (8.0, 9.95)], layer=pcbnew.B_Cu)
via(8.0, 9.95, "HOLD_OUT")

# ============================================================================= level shifter U202, ADC RC
place("Package_TO_SOT_SMD", "SOT-23-5", "U202", "TPH2501", 3.0, 9.0, 0,
      {"1": "SHIFT_OUT", "2": "GND", "3": "ADC_REF_MID", "4": "SHIFT_IN", "5": "+3V3"})
two("R", "R209", "1k", 6.6, 9.95, "h", "SHIFT_IN", "HOLD_OUT")
track("HOLD_OUT", W_SIG, [(8.0, 9.95), ("R209", "2")])
track("SHIFT_IN", W_SIG, [("U202", "4"), ("R209", "1")])
two("R", "R210", "1k", 3.0, 6.6, "h", "SHIFT_OUT", "SHIFT_IN")
track("SHIFT_OUT", W_SIG, [("U202", "1"), (1.8625, 7.2), ("R210", "1")])
track("SHIFT_IN", W_HOLD, [("R210", "2"), (3.0, 7.1), (3.0, 9.95), ("U202", "4")])
two("R", "R211", "33", -0.6, 8.05, "h", "ADC_IN", "SHIFT_OUT")
track("SHIFT_OUT", W_SIG, [("U202", "1"), ("R211", "2")])
two("C", "C207", "220p C0G", -2.2, 8.6, "v", "ADC_IN", "GND")
track("ADC_IN", W_SIG, [("R211", "1"), ("C207", "@ADC_IN")])
track("GND", W_GND, [("C207", "@GND"), (-2.2, 9.8)])
via(-2.2, 9.8, "GND")
two("C", "C206", "10n", 0.4, 10.5, "v", "ADC_REF_MID", "GND")
track("ADC_REF_MID", W_SIG, [("U202", "3"), ("C206", "@ADC_REF_MID")])
track("GND", W_GND, [("C206", "@GND"), (0.4, 11.7)])
via(0.4, 11.7, "GND")
track("GND", W_GND, [("U202", "2"), (0.8, 9.0)])
via(0.8, 9.0, "GND")
two("C", "C210", "100n", 6.0, 8.05, "h", "+3V3", "GND")
track("+3V3", W_SIG, [("U202", "5"), ("C210", "1"), (5.49, 7.3)])
via(5.49, 7.3, "+3V3")
track("GND", W_GND, [("C210", "2"), (6.51, 7.3)])
via(6.51, 7.3, "GND")
for ref, nn, x in (("TP205", "ADC_IN", -4.0), ("TP206", "ADC_REF_MID", -1.3), ("TP207", "GND", 1.6)):
    custom(ref, "TestPoint_Pad_D1.0mm", x, 12.5, [("1", 0, 0, 1.0, 1.0, nn, pcbnew.PAD_SHAPE_CIRCLE)], (0.75, 0.75))
track("ADC_IN", W_SIG, [("C207", "@ADC_IN"), (-3.2, 8.09), (-4.0, 8.9), (-4.0, 12.5)])
track("ADC_REF_MID", W_SIG, [("C206", "@ADC_REF_MID"), (-0.4, 9.99), (-1.3, 10.9), (-1.3, 12.5)])
track("GND", W_GND, [(1.6, 12.5), (1.6, 11.6)])
via(1.6, 11.6, "GND")
text("ADC_IN", -6.2, 12.5, 0.45)
text("ADC_REF_MID", -1.3, 11.45, 0.4)
text("GND", 2.9, 12.5, 0.45)

# ============================================================================= strobe output: balun, 1 k, arms
XB = 12.0
custom("T401", "CMC_0805_balun", XB, 0.0,
       [("1", 0.835, -0.435, 0.76, 0.51, "STRB_CLIP", RR), ("3", 0.835, 0.435, 0.76, 0.51, "GND", RR),
        ("2", -0.835, -0.435, 0.76, 0.51, "STRB_A", RR), ("4", -0.835, 0.435, 0.76, 0.51, "STRB_K", RR)],
       (1.47, 0.94))
two("R", "R204", "1k", 9.95, 0.0, "v", "STRB_A", "STRB_K")
for s, nn, pn, cref in ((-1, "STRB_A", "2", "C201"), (+1, "STRB_K", "4", "C202")):
    cp = sorted([pad(cref, "1"), pad(cref, "2")], key=lambda q: -abs(q[1]))[0]     # outer pad of the 47 pF
    track(nn, W50, [(T401p := pad("T401", pn)), (9.95, T401p[1]), (9.95, 5.0 * s), (9.35, 5.6 * s),
                    (XM + 0.6, 5.6 * s), (XM, 5.0 * s), cp], name=f"{nn} balun -> 47 pF")
track("GND", W_GND, [("T401", "3"), (12.835, 1.3)])
via(12.835, 1.3, "GND")

# ============================================================================= TRF37D73 #2, clip node, stub
YL = -0.435                                    # RF line y (balun pin 1 / TRF pins 2, 7)
XT = 17.7
place("Package_SON", "WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm", "U402", "TRF37D73", XT, YL - 0.25, 180,
      {"1": "+3V3", "2": "TRF2_RFIN", "3": "GND", "4": "GND", "5": "GND", "6": "GND", "7": "TRF2_OUT",
       "8": "GND", "9": "GND"})
two("C", "C404", "100n", 14.6, YL, "h", "STRB_CLIP", "TRF2_OUT")
XTAP = 13.52
track("STRB_CLIP", W50, [("T401", "1"), (XTAP, YL)], name="clip: balun pin 1 -> stub tap")
track("STRB_CLIP", W50, [(XTAP, YL), ("C404", "1")], name="clip: stub tap -> C404")
track("TRF2_OUT", W50, [("C404", "2"), ("U402", "7")], name="TRF2 out -> C404")
# shorted stub: 80 ps one way, from the tap to the net tie / GND vias
L_STUB = 80.0 / PS_MM
YS = 6.0
xe = XTAP + (L_STUB - (YS - YL))
custom("NT401", "NetTie_stub_short", xe + 0.5, YS,
       [("1", -0.5, 0, 0.5, 0.5, "STRB_CLIP", pcbnew.PAD_SHAPE_CIRCLE), ("2", 0.5, 0, 0.5, 0.5, "GND", pcbnew.PAD_SHAPE_CIRCLE)],
       (0, 0))
nt = FPS["NT401"]
cu = pcbnew.FP_SHAPE(nt, pcbnew.SHAPE_T_SEGMENT)          # net-tie copper bridge
cu.SetLayer(pcbnew.F_Cu)
cu.SetWidth(mm(0.3))
cu.SetStart0(pcbnew.VECTOR2I(mm(-0.5), 0))
cu.SetEnd0(pcbnew.VECTOR2I(mm(0.5), 0))
cu.SetDrawCoord()
nt.Add(cu)
if hasattr(nt, "AddNetTiePadGroup"):
    nt.AddNetTiePadGroup("1, 2")
track("STRB_CLIP", W50, [(XTAP, YL), (XTAP, YS), (xe, YS)], name="stub (80 ps, shorted)")
track("GND", 0.4, [(xe + 1.0, YS), (xe + 1.9, YS)])
for dx, dy in ((1.3, 0.0), (1.9, -0.55), (1.9, 0.55)):
    via(xe + dx, YS + dy, "GND")
# bias tee: bead (RF side) + 47 uH, decoupling at the cold end
two("FB", "FB402", "1k@100M", 15.5, -1.85, "v", "TRF2_BIAS", "TRF2_OUT")
two("L", "L402", "47u", 15.5, -5.1, "v", "+3V3", "TRF2_BIAS")
track("TRF2_OUT", W_SIG, [(15.5, YL), ("FB402", "1")])
track("TRF2_BIAS", W_PWR, [("FB402", "2"), ("L402", "@TRF2_BIAS")])
two("C", "C411", "1n", 17.9, -6.0, "v", "+3V3", "GND")
two("C", "C412", "10u", 19.5, -6.0, "v", "+3V3", "GND", size="0805")
track("+3V3", W_PWR, [("L402", "@+3V3"), (17.9, -6.5), ("C411", "2")])
track("+3V3", W_PWR, [(17.9, -6.51), (19.5, -6.95), ("C412", "2")])
track("+3V3", W_PWR, [("L402", "@+3V3"), (15.5, -7.7)])
via(15.0, -7.7, "+3V3")
via(16.0, -7.7, "+3V3")
track("+3V3", W_PWR, [(15.0, -7.7), (16.0, -7.7)])
track("GND", W_GND, [("C411", "1"), (17.9, -4.85)])
via(17.9, -4.85, "GND")
track("GND", W_GND, [("C412", "1"), (19.5, -4.3)])
via(19.5, -4.3, "GND")
# TRF ground pins to the exposed pad, EP vias
for pn in ("3", "4", "5", "6", "8"):
    x, y = pad("U402", pn)
    track("GND", W_SIG, [(x, y), (XT, y)])
for dy in (-0.55, 0.0, 0.55):
    via(XT, YL - 0.25 + dy, "GND", drill=0.2, dia=0.4)
# VCC pin 1 decoupling
x1, y1 = pad("U402", "1")
two("C", "C405", "1n", 19.6, 1.6, "v", "+3V3", "GND")
two("C", "C406", "100n", 20.7, 1.6, "v", "+3V3", "GND")
track("+3V3", W_GND, [(x1, y1), (x1, 1.09), ("C405", "2"), ("C406", "2")])
track("+3V3", W_GND, [(x1, 1.09), (x1, 1.75)])
via(x1, 1.75, "+3V3")
for c in ("C405", "C406"):
    x, y = pad(c, "1")
    track("GND", W_GND, [(x, y), (x, y + 0.65)])
    via(x, y + 0.65, "GND")
# input: from the 12 dB pad (TRF #1 chain) via the 100 nF block
two("C", "C403", "100n", 20.3, YL, "h", "TRF2_RFIN", "TRF2_IN")
custom("X2", "IF_TRF2_IN", 22.6, YL, [("1", 0, 0, 0.6, 0.5, "TRF2_IN", RR)], (0, 0))
track("TRF2_RFIN", W50, [("U402", "2"), ("C403", "1")], name="TRF2 in <- C403")
track("TRF2_IN", W50, [("C403", "2"), ("X2", "1")], name="X2 -> C403")
custom("TP401", "TestPoint_Pad_D1.0mm", 21.8, -8.0, [("1", 0, 0, 1.0, 1.0, "+3V3", pcbnew.PAD_SHAPE_CIRCLE)], (0.75, 0.75))
track("+3V3", W_PWR, [(21.8, -8.0), (21.8, -7.0)])
via(21.8, -7.0, "+3V3")
text("+3V3", 21.8, -8.85, 0.5)
custom("TP402", "TestPoint_Pad_D1.0mm", 21.8, 11.8, [("1", 0, 0, 1.0, 1.0, "GND", pcbnew.PAD_SHAPE_CIRCLE)], (0.75, 0.75))
track("GND", W_GND, [(21.8, 11.8), (21.8, 10.9)])
via(21.8, 10.9, "GND")
text("GND", 21.8, 12.85, 0.5)

# ============================================================================= silkscreen
text("BUF_OUT_S", -6.4, -1.0, 0.5)
text("<- BUF802 OUT", -5.6, 1.0, 0.35)
text("TRF2_IN", 22.6, -1.45, 0.5)
text("<- 12 dB pad", 21.9, 0.55, 0.35)
text("SAMPLER fragment (4L JLC04161H-3313)", 12.5, 12.9, 0.5)
text("STRB_A", 6.0, -6.3, 0.45)
text("STRB_K", 6.0, 6.3, 0.45)
text("80 ps stub (shorted)", 17.0, 6.85, 0.45)
text("T401 balun", 12.0, -1.6, 0.4)
text("GUARD", 1.25, 2.4, 0.35)
text("U202 level shift", 3.0, 11.3, 0.4)

# ============================================================================= zones
IN = 0.25
outline = rect_pts(BX0 + IN, BY0 + IN, BX1 - IN, BY1 - IN)
HOLD_CUT = rect_pts(2.25, -0.38, 5.2, 1.5)         # under D202.3, the hold trace, U201.3, C205.1
zone("GND", [pcbnew.In1_Cu], outline, clearance=0.2)
zone("+3V3", [pcbnew.In2_Cu], outline, clearance=0.3)
zone("GND", [pcbnew.B_Cu], outline, clearance=0.25)
zone("GND", [pcbnew.F_Cu], outline, clearance=0.3)
zone(None, [pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu], HOLD_CUT, rule=True)
zone(None, [pcbnew.F_Cu], rect_pts(1.4, -0.85, 7.3, 2.05), rule=True)   # no top pour inside / near the guard


# ============================================================================= stitching vias
def items_other_net(netname):
    out = []
    for t in b.GetTracks():
        if t.GetNetname() != netname:
            out.append(t)
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != netname:
                out.append(p)
    return out


def can_via(x, y, r=0.3, clr=0.18):
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            vx, vy = loc(t.GetPosition())
            d = math.hypot(vx - x, vy - y)
            if d < r + pcbnew.ToMM(t.GetWidth()) / 2 + 0.2:
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
            dx = max(x0 - x, 0, x - x1)
            dy = max(y0 - y, 0, y - y1)
            lim = r + (0.15 if p.GetNetname() == "GND" else clr)
            if math.hypot(dx, dy) < lim:
                return False
    for (x0, y0, x1, y1) in [tuple(c for c in pt) for pt in [(2.0, -0.6, 5.45, 1.75)]]:  # hold cut-out area
        if x0 < x < x1 and y0 < y < y1:
            return False
    if not (BX0 + 0.6 < x < BX1 - 0.6 and BY0 + 0.6 < y < BY1 - 0.6):
        return False
    return True


def seg_dist(px, py, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy
    u = 0 if L2 == 0 else max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / L2))
    return math.hypot(px - x0 - u * dx, py - y0 - u * dy)


N_STITCH = 0
STITCH_OFF = W50 / 2 + 0.55
for name in ("STRB_A balun -> 47 pF", "STRB_K balun -> 47 pF", "stub (80 ps, shorted)", "clip: stub tap -> C404",
             "TRF2 out -> C404", "X2 -> C403", "BUF802 OUT -> R201", "R201 -> D201.3 (between D201 pins 1/2)"):
    for (x0, y0, x1, y1) in ROUTES[name]:
        L = math.hypot(x1 - x0, y1 - y0)
        nx, ny = -(y1 - y0) / L, (x1 - x0) / L
        n = max(1, int(L / 1.0))
        for i in range(n + 1):
            u = i / n
            for sgn in (1, -1):
                x = x0 + u * (x1 - x0) + sgn * nx * STITCH_OFF
                y = y0 + u * (y1 - y0) + sgn * ny * STITCH_OFF
                if can_via(x, y):
                    via(x, y, "GND")
                    N_STITCH += 1
# extra ground vias in open areas (ties F.Cu pour, In1, B.Cu)
for gx in range(-7, 23, 2):
    for gy in range(-8, 13, 2):
        if can_via(gx + 0.3, gy + 0.3, clr=0.35):
            via(gx + 0.3, gy + 0.3, "GND")
            N_STITCH += 1

# ============================================================================= fill, checks, save
filler = pcbnew.ZONE_FILLER(b)
filler.Fill(b.Zones())


def route_len(name):
    return sum(math.hypot(x1 - x0, y1 - y0) for x0, y0, x1, y1 in ROUTES[name])


print(f"Stack-up: L1-L2 prepreg h={H} mm er={ER}, t={T_CU} mm. 50 R width (H-J) {W50_EXACT:.3f} mm -> drawn "
      f"{W50:.2f} mm: Z0={Z50:.1f} R, eps_eff={EEFF:.3f}, {PS_MM:.2f} ps/mm")
print(f"{'path':44s} {'intended':>16s} {'actual mm':>9s} {'actual ps':>9s}")
rows = [("BUF802 OUT -> R201", "short"),
        ("R201 -> D201.3 (between D201 pins 1/2)", "<= 3 mm"),
        ("hold node D202.3 -> U201.3", "minimum"),
        ("hold node branch -> C205", "minimum"),
        ("stub (80 ps, shorted)", "80 ps"),
        ("STRB_A balun -> 47 pF", "= STRB_K"),
        ("STRB_K balun -> 47 pF", "= STRB_A"),
        ("BRG_A rail D201", "= BRG_K D201"), ("BRG_K rail D201", "= BRG_A D201"),
        ("BRG_A rail D202", "= BRG_K D202"), ("BRG_K rail D202", "= BRG_A D202"),
        ("A R25 -> C47", "= K"), ("K R25 -> C47", "= A")]
for nm, intent in rows:
    L = route_len(nm)
    print(f"{nm:44s} {intent:>16s} {L:9.3f} {L * PS_MM:9.1f}")
dA, dK = route_len("STRB_A balun -> 47 pF"), route_len("STRB_K balun -> 47 pF")
print(f"STRB_A - STRB_K mismatch: {abs(dA - dK) * 1000:.1f} um ({abs(dA - dK) * PS_MM:.3f} ps); "
      f"stub error {route_len('stub (80 ps, shorted)') * PS_MM - 80:+.2f} ps")
print(f"stitching / ground vias added: {N_STITCH}")

# --- sanity: courtyards
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
# --- sanity: copper clearance (tracks/vias vs tracks/vias/pads of other nets, >= 0.1 mm)
CLR = mm(0.1) - 1000
tr = list(b.GetTracks())
pads = [p for fp in fps for p in fp.Pads() if p.GetNumber()]
CU = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
for i, t in enumerate(tr):
    for lay in CU:
        if not t.IsOnLayer(lay):
            continue
        st = t.GetEffectiveShape(lay)
        for u in tr[i + 1:]:
            if u.GetNetCode() == t.GetNetCode() or not u.IsOnLayer(lay):
                continue
            if st.Collide(u.GetEffectiveShape(lay), CLR):
                errs.append(f"clearance {t.GetNetname()} / {u.GetNetname()} on {b.GetLayerName(lay)} at "
                            f"{loc(t.GetPosition())}")
        for p in pads:
            if p.GetNetCode() == t.GetNetCode() or not p.IsOnLayer(lay):
                continue
            if st.Collide(p.GetEffectiveShape(lay), CLR):
                errs.append(f"clearance {t.GetNetname()} / pad {p.GetParent().GetReference()}.{p.GetNumber()} "
                            f"({p.GetNetname()}) on {b.GetLayerName(lay)}")
for i, p in enumerate(pads):
    for q in pads[i + 1:]:
        if p.GetParent() is q.GetParent() or p.GetNetCode() == q.GetNetCode():
            continue
        if p.GetEffectiveShape(pcbnew.F_Cu).Collide(q.GetEffectiveShape(pcbnew.F_Cu), CLR):
            errs.append(f"pad clearance {p.GetParent().GetReference()}.{p.GetNumber()} / "
                        f"{q.GetParent().GetReference()}.{q.GetNumber()}")
# --- sanity: every pad with a net has copper (track or zone) touching it
unrouted = []
for p in pads:
    if not p.GetNetname():
        unrouted.append(f"{p.GetParent().GetReference()}.{p.GetNumber()} (no net)")
print("courtyard / clearance check:", "OK" if not errs else f"{len(errs)} problems")
for e in sorted(set(errs))[:40]:
    print("  ", e)
for u in unrouted:
    print("   pad without net:", u)

pcbnew.SaveBoard(OUT, b)

# stack-up: written into (setup) of the saved file (the 7.0 Python API has no stack-up editor)
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
# net tie: declare pad group so KiCad DRC accepts the stub short
with open(OUT, "w") as f:
    f.write(s)
print("wrote", OUT)
for ext in (".kicad_pro", ".kicad_prl"):                      # SaveBoard side products, not part of the fragment
    pth = OUT[:-len(".kicad_pcb")] + ext
    if os.path.exists(pth):
        os.remove(pth)
