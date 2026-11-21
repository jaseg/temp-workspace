#!/usr/bin/env python3
"""Layout fragment "sampler": BUF802 OUT -> 10 R -> 4-diode bridge (2x BAT15-04W) -> 2.2 pF hold ->
TPH2501 G=+3 -> TPH2501 level shifter -> 33 R / 220 pF -> ADC_IN, plus the sampler strobe output
section (TRF37D73 #2 -> 100 nF -> clip node (80 ps shorted stub + BAT15 clamp) -> CMC balun -> STRB_A/STRB_K).

Values: design/lowcost/sim/sampler/RESULT.md, sim/strobe/RESULT.md, sim/phase_array/RESULT.md (clamp),
SPEC decisions 1-3, 9 (JLC04161H-7628).
Run:  python3 gen_sampler.py   (writes sampler.kicad_pcb next to this file, prints the impedance, RF segment,
delay and pad-discontinuity tables and the sanity checks). KiCad 7.0 pcbnew API. kicad-cli 7 has no DRC.

Local coordinates in mm, origin = centre of the bridge, +x towards the strobe driver, +y down.
Mirror axis of the strobe paths: y = 0. No via stitching (added when the fragments are assembled).
"""
import math, os, tempfile
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sampler.kicad_pcb")
FPLIB = "/usr/share/kicad/footprints"
ORG = (120.0, 100.0)
mm = pcbnew.FromMM

# ============================================================================= stack-up / impedance
# JLC04161H-7628 (jlcpcb.com/impedance, checked): L1 35 um / 7628 prepreg 0.2104 mm er 4.4 / L2 15.2 um /
# core 1.065 mm er 4.6 / L3 15.2 um / 7628 0.2104 mm / L4 35 um. Mask er 3.8, 0.6 mil (15 um) over the
# trace, 1.2 mil (30 um) over bare laminate.
H, T_CU, ER, ER_MASK, C_MASK_TR, C_MASK_SUB = 0.2104, 0.035, 4.4, 3.8, 0.015, 0.030
C0 = 0.299792458                                   # mm/ps


def microstrip(w, h=H, t=T_CU, er=ER, mask=True):
    """Hammerstad-Jensen microstrip with the Hammerstad thickness correction, plus a first-order
    solder-mask overlay: the mask replaces air in the part of the fringing field it covers,
    eps_eff += (er_mask - 1) * (1 - q) * (1 - exp(-1.2 c / h)), q = filling factor of the bare line,
    c = mean mask thickness. Returns (Z0, eps_eff)."""
    u = w / h

    def z_air(x):
        f = 6 + (2 * math.pi - 6) * math.exp(-(30.666 / x) ** 0.7528)
        return 60 * math.log(f / x + math.sqrt(1 + 4 / x ** 2))

    def ee0(x):
        a = 1 + math.log((x ** 4 + (x / 52) ** 2) / (x ** 4 + 0.432)) / 49 + math.log(1 + (x / 18.1) ** 3) / 18.7
        b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
        return (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / x) ** (-a * b)
    du1 = t / h / math.pi * math.log(1 + 4 * math.e / (t / h * (1 / math.tanh(math.sqrt(6.517 * u))) ** 2))
    dur = 0.5 * (1 + 1 / math.cosh(math.sqrt(er - 1))) * du1
    u1, ur = u + du1, u + dur
    ee = ee0(ur) * (z_air(u1) / z_air(ur)) ** 2
    z_vac = z_air(u1)                              # Z0 * sqrt(eps_eff) is independent of the dielectric
    if mask:
        q = (ee - 1) / (er - 1)
        c = (C_MASK_TR + C_MASK_SUB) / 2
        ee += (ER_MASK - 1) * (1 - q) * (1 - math.exp(-1.2 * c / h))
    return z_vac / math.sqrt(ee), ee


def _K(k):
    a, b = 1.0, math.sqrt(1 - k * k)
    for _ in range(30):
        a, b = (a + b) / 2, math.sqrt(a * b)
    return math.pi / (2 * a)


def cpwg(w, g, h=H, er=ER):
    """Conductor-backed coplanar waveguide (zero thickness, no mask), Wadell. Returns (Z0, eps_eff)."""
    k = w / (w + 2 * g)
    k3 = math.tanh(math.pi * w / (4 * h)) / math.tanh(math.pi * (w + 2 * g) / (4 * h))
    r1 = _K(k) / _K(math.sqrt(1 - k * k))
    r3 = _K(k3) / _K(math.sqrt(1 - k3 * k3))
    ee = (1 + er * r3 / r1) / (1 + r3 / r1)
    return 60 * math.pi / math.sqrt(ee) / (r1 + r3), ee


def width_for(z):
    lo, hi = 0.02, 3.0
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if microstrip(m)[0] > z else (lo, m)
    return (lo + hi) / 2


def ps_mm(w):
    return math.sqrt(microstrip(w)[1]) / C0


def c_per_mm(w):                                    # pF/mm of a microstrip of width w
    z, ee = microstrip(w)
    return math.sqrt(ee) / (C0 * z)


W50_EXACT = width_for(50.0)
W50 = round(W50_EXACT / 0.01) * 0.01                # drawn width
Z50, EEFF = microstrip(W50)
PS_MM = ps_mm(W50)
GAP_RF = 2 * W50                                    # top-pour clearance from every RF trace edge
W_HOLD, W_GUARD, W_SIG, W_PWR, W_GND = 0.15, 0.10, 0.20, 0.50, 0.40

# ============================================================================= board
_TMP = tempfile.mkdtemp(prefix="sampler_fragment_")
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
ds.m_ViasMinSize = mm(0.45)
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


def _finish(fp, ref, val, bottom=False):
    fp.SetReference(ref)
    fp.SetValue(val)
    fp.Reference().SetLayer(pcbnew.F_Fab)
    fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.25), mm(0.25)))
    fp.Reference().SetTextThickness(mm(0.04))
    fp.Reference().SetPosition(fp.GetPosition())
    fp.Value().SetVisible(False)
    for g in fp.GraphicalItems():                       # library fab texts (${REFERENCE}) small
        if g.GetClass() in ("FP_TEXT", "PCB_TEXT"):
            g.SetTextSize(pcbnew.VECTOR2I(mm(0.25), mm(0.25)))
            g.SetTextThickness(mm(0.04))
    b.Add(fp)
    if bottom:
        fp.Flip(fp.GetPosition(), True)
    FPS[ref] = fp
    return fp


def place(lib, name, ref, val, x, y, rot, nets, bottom=False):
    fp = pcbnew.FootprintLoad(os.path.join(FPLIB, lib + ".pretty"), name)
    fp.SetPosition(P(x, y))
    fp.SetOrientationDegrees(rot)
    for p in fp.Pads():
        if p.GetNumber() in nets:
            p.SetNet(net(nets[p.GetNumber()]))
    return _finish(fp, ref, val, bottom)


def two(kind, ref, val, x, y, orient, na, nb, size="0402", bottom=False):
    """2-terminal part. orient 'h': na left / nb right; 'v': na up / nb down."""
    lib, name = {"R": ("Resistor_SMD", f"R_{size}_1005Metric" if size == "0402" else f"R_{size}_2012Metric"),
                 "C": ("Capacitor_SMD", f"C_{size}_1005Metric" if size == "0402" else f"C_{size}_2012Metric"),
                 "FB": ("Inductor_SMD", "L_0402_1005Metric"),
                 "L": ("Inductor_SMD", "L_1210_3225Metric")}[kind]
    if orient == "h":
        return place(lib, name, ref, val, x, y, 0, {"1": na, "2": nb}, bottom)
    return place(lib, name, ref, val, x, y, 90, {"1": nb, "2": na}, bottom)      # rot 90: pad 1 at +y


def custom(ref, val, x, y, pads, crt, bottom=False):
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
    for lay, (ax, ay), wd in ((pcbnew.F_CrtYd, (cx, cy), 0.05), (pcbnew.F_Fab, (cx - 0.2, cy - 0.2), 0.08)):
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
    return _finish(fp, ref, val, bottom)


def testpad(ref, nn, x, y, bottom=False):
    return custom(ref, "TestPoint_Pad_D1.0mm", x, y, [("1", 0, 0, 1.0, 1.0, nn, pcbnew.PAD_SHAPE_CIRCLE)],
                  (0.7, 0.7), bottom)


def pad(ref, num):
    """Pad centre by number, or by net name with a leading '@'."""
    for p in FPS[ref].Pads():
        if p.GetNumber() == num or (num[0] == "@" and p.GetNetname() == num[1:]):
            return loc(p.GetPosition())
    raise KeyError((ref, num))


ROUTES = {}          # name -> dict(net, width, z, segs)
POLYS = []           # (name, points) for the 45-degree check
TRACKS = []


def track(netname, width, pts, layer=pcbnew.F_Cu, name=None, z=None):
    pts = [pad(*p) if isinstance(p[0], str) else p for p in pts]
    pts = [p for i, p in enumerate(pts) if i == 0 or math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) > 1e-6]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(P(x0, y0))
        t.SetEnd(P(x1, y1))
        t.SetWidth(mm(width))
        t.SetLayer(layer)
        t.SetNet(net(netname))
        b.Add(t)
        TRACKS.append(t)
        if name:
            ROUTES.setdefault(name, dict(net=netname, width=width, z=z, segs=[]))["segs"].append((x0, y0, x1, y1))
    POLYS.append((name or netname, pts, layer))
    return pts


N_VIA = {}


def via(x, y, netname, drill=0.3, dia=0.6, why="gnd"):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(P(x, y))
    v.SetDrill(mm(drill))
    v.SetWidth(mm(dia))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetNet(net(netname))
    b.Add(v)
    N_VIA[why] = N_VIA.get(why, 0) + 1
    return v


def svia(x, y, netname, why="signal"):
    return via(x, y, netname, 0.2, 0.45, why)


def text(s, x, y, size=0.4, layer=pcbnew.F_SilkS, rot=0):
    t = pcbnew.PCB_TEXT(b)
    t.SetText(s)
    t.SetPosition(P(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * 0.15))
    t.SetTextAngleDegrees(rot)
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
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


def zone(netname, layers, pts, clearance=0.2, prio=0, rule=False, thermal=False):
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
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL if thermal else pcbnew.ZONE_CONNECTION_FULL)
        z.SetAssignedPriority(prio)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(mm(x + ORG[0]), mm(y + ORG[1]))
    b.Add(z)
    return z


def chamfer(pts, c):
    """Polyline through pts with every corner cut by a 45-degree chamfer of leg c (pts: 0/45/90-degree legs)."""
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        (xa, ya), (xb, yb), (xc, yc) = pts[i - 1], pts[i], pts[i + 1]
        la, lc = math.hypot(xb - xa, yb - ya), math.hypot(xc - xb, yc - yb)
        out.append((xb - (xb - xa) / la * c, yb - (yb - ya) / la * c))
        out.append((xb + (xc - xb) / lc * c, yb + (yc - yb) / lc * c))
    out.append(pts[-1])
    return out


RR = pcbnew.PAD_SHAPE_ROUNDRECT
W = W50

# ============================================================================= input leg + bridge
D1X, D2X = -1.7, 1.7                       # BAT15-04W, courtyards (+-1.7) touching
place("Package_TO_SOT_SMD", "SOT-323_SC-70", "D201", "BAT15-04W", D1X, 0, 0, {"1": "BRG_A", "2": "BRG_K", "3": "BRG_IN"})
place("Package_TO_SOT_SMD", "SOT-323_SC-70", "D202", "BAT15-04W", D2X, 0, 0, {"1": "BRG_A", "2": "BRG_K", "3": "HOLD"})
two("R", "R201", "10", D1X - 1.7 - 0.93, 0, "h", "BUF_OUT_S", "BRG_IN")
custom("X1", "IF_BUF_OUT_S", pad("R201", "1")[0] - 0.8, 0, [("1", 0, 0, 0.6, 0.5, "BUF_OUT_S", RR)], (0, 0))
track("BUF_OUT_S", W, [("X1", "1"), ("R201", "1")], name="BUF_OUT_S: X1 -> R201", z=50)
track("BRG_IN", W, [("R201", "2"), ("D201", "3")], name="BRG_IN: R201 -> D201.3 (under D201)", z=50)

XM = (pad("D201", "1")[0] + pad("D202", "1")[0]) / 2     # rail junction x (-1.0)
YR = 1.72                                                  # rail y
for s, rail, node, strb, vb, ab in ((-1, "BRG_A", "BIAS_A_N", "STRB_A", "VBIAS_A", "A"),
                                    (+1, "BRG_K", "BIAS_K_N", "STRB_K", "VBIAS_K", "K")):
    i = 0 if s < 0 else 1
    r25, c47, r1k, c10, tp = ("R202", "R203")[i], ("C201", "C202")[i], ("R205", "R206")[i], ("C203", "C204")[i], ("TP201", "TP202")[i]
    up_dn = (lambda a, bb: (a, bb) if s < 0 else (bb, a))          # (outer, inner) -> (up, down)
    two("R", r25, "24.9", XM, s * 2.23, "v", *up_dn(node, rail))
    two("C", c47, "47p C0G", XM + 0.48, s * 4.07, "h", node, strb)       # node pad above R25, arm leaves along x
    two("R", r1k, "1k", XM - 0.47 - 0.93, s * 3.17, "h", vb, node)
    two("C", c10, "10n", pad(r1k, "1")[0], s * 4.55, "v", *up_dn("GND", vb))
    pn = "1" if s < 0 else "2"
    for d in ("D201", "D202"):
        x0, y0 = pad(d, pn)
        dx = 1 if x0 < XM else -1
        track(rail, W, [(x0, y0), (x0, s * (YR - 0.35)), (x0 + dx * 0.35, s * YR), (XM, s * YR)],
              name=f"{rail} rail {d}", z=50)
    track(node, W_SIG, [(XM, s * 2.74), (XM, s * 4.07)])
    track(node, W_SIG, [(r1k, "2"), (XM, s * 3.17)])
    track(vb, W_SIG, [(c10, "@" + vb), (r1k, "1")])
    gx, gy = pad(c10, "@GND")
    via(gx, gy + s * 0.62, "GND")
    track("GND", W_GND, [(gx, gy), (gx, gy + s * 0.62)])
    testpad(tp, vb, -5.1, s * 3.17)
    track(vb, W_SIG, [(r1k, "1"), (-5.1, s * 3.17)])
    text(vb, -5.1, s * 4.25, 0.45)

# ============================================================================= hold node, U201 (G = +3)
UX1 = D2X + 1.7 + 2.05                                     # courtyards touching -> pin 3 on the axis
place("Package_TO_SOT_SMD", "SOT-23-5", "U201", "TPH2501", UX1, -0.95, 0,
      {"1": "HOLD_OUT", "2": "-2V5", "3": "HOLD", "4": "HOLD_FB", "5": "+2V5"})
track("HOLD", W_HOLD, [("D202", "3"), ("U201", "3")], name="HOLD: D202.3 -> U201.3", z=None)
two("C", "C205", "2.2p C0G", 3.4 + 0.46, 0.75 + 0.91, "v", "HOLD", "GND")
xc = pad("C205", "@HOLD")[0]
track("HOLD", W_HOLD, [(xc, 0.0), ("C205", "@HOLD")], name="HOLD: branch -> C205", z=None)
gx, gy = pad("C205", "@GND")
track("GND", W_GND, [(gx, gy), (gx, gy + 0.6)])
via(gx, gy + 0.6, "GND")
two("R", "R207", "1.00k 1%", 3.4 - 0.93, -1.9, "h", "HOLD_FB", "HOLD_OUT")
two("R", "R208", "499 1%", xc + 0.46 + 0.93, 1.66, "h", "HOLD_FB", "GND")
xg = pad("R207", "1")[0]
# guard (HOLD_FB = U201 -IN, sits at the hold voltage): pin 4 -> under the body -> between pins 2/3 ->
# around D202.3 / hold trace / C205.1 (between the C205 pads) -> R208
track("HOLD_FB", W_GUARD, [("U201", "4"), (UX1 + 0.25, 0.0), (UX1 - 0.25, -0.5), (xg + 0.3, -0.5), (xg, -0.2),
                           (xg, 0.6), (xg + 1.06, 1.66), ("R208", "1")], name="guard ring (HOLD_FB)")
track("HOLD_FB", W_HOLD, [("R207", "1"), (xg, -0.2)])
x, y = pad("R208", "2")
track("GND", W_GND, [(x, y), (x + 0.6, y)])
via(x + 0.6, y, "GND")
# OUT: R207 on the outside, B.Cu via under the body (between the pad columns)
track("HOLD_OUT", W_SIG, [("R207", "2"), ("U201", "1"), (UX1, -1.9)])
svia(UX1, -1.9, "HOLD_OUT")
# -2V5: pin 2 -> via, 100 nF on B.Cu right under it
p2 = pad("U201", "2")
track("-2V5", 0.5, [p2, (3.3, p2[1])])
svia(3.3, p2[1], "-2V5", why="supply")
two("C", "C209", "100n", 3.3, -1.95, "v", "GND", "-2V5", bottom=True)
track("-2V5", W_PWR, [(3.3, p2[1]), ("C209", "@-2V5")], layer=pcbnew.B_Cu)
gx, gy = pad("C209", "@GND")
track("GND", W_GND, [(gx, gy), (gx, gy - 0.6)], layer=pcbnew.B_Cu)
via(gx, gy - 0.6, "GND")
# +2V5: pin 5 -> 100 nF along the pad axis, wide
two("C", "C208", "100n", UX1 + 2.05 + 0.91, -1.9, "h", "+2V5", "GND")
track("+2V5", 0.6, [("U201", "5"), ("C208", "1")])
xv = (pad("U201", "5")[0] + 0.66 + pad("C208", "1")[0] - 0.28) / 2
svia(xv, -2.6, "+2V5", why="supply")
track("+2V5", W_PWR, [(xv, -1.9), (xv, -2.6)])
x, y = pad("C208", "2")
track("GND", W_GND, [(x, y), (x, y + 0.72)])
via(x, y + 0.72, "GND")
# B.Cu feeds to bottom-side test pads
testpad("TP203", "-2V5", 1.6, -5.0, bottom=True)
testpad("TP204", "+2V5", xv, -5.0, bottom=True)
c9 = pad("C209", "@-2V5")
track("-2V5", W_PWR, [c9, (2.3, c9[1]), (1.6, c9[1] - 0.7), (1.6, -5.0)], layer=pcbnew.B_Cu)
track("+2V5", W_PWR, [(xv, -2.6), (xv, -5.0)], layer=pcbnew.B_Cu)
text("-2V5", 1.6, -6.05, 0.45, pcbnew.B_SilkS)
text("+2V5", xv, -6.05, 0.45, pcbnew.B_SilkS)

# ============================================================================= level shifter U202, ADC RC
UX, UY = 3.4, 6.5
place("Package_TO_SOT_SMD", "SOT-23-5", "U202", "TPH2501", UX, UY, 0,
      {"1": "SHIFT_OUT", "2": "GND", "3": "ADC_REF_MID", "4": "SHIFT_IN", "5": "+3V3"})
two("R", "R209", "1k", UX + 2.05 + 0.93, UY + 0.95, "h", "SHIFT_IN", "HOLD_OUT")
two("R", "R210", "1k", UX, UY + 1.7 + 0.47, "h", "SHIFT_OUT", "SHIFT_IN")
two("R", "R211", "33", UX - 2.05 - 0.93, UY - 0.95, "h", "ADC_IN", "SHIFT_OUT")
two("C", "C207", "220p C0G", UX - 2.05 - 1.86 - 0.91, UY - 0.95, "h", "GND", "ADC_IN")
two("C", "C206", "10n", UX - 2.05 - 0.91, UY + 0.95, "h", "GND", "ADC_REF_MID")
two("C", "C210", "100n", UX + 2.05 + 0.91, UY - 0.95, "h", "+3V3", "GND")
track("SHIFT_IN", W_SIG, [("U202", "4"), ("R209", "1")])
track("SHIFT_IN", W_SIG, [(UX + 0.6, UY + 0.95), (UX + 0.6, UY + 2.17)])
track("SHIFT_OUT", W_SIG, [("R211", "2"), ("U202", "1"), (UX - 0.05, UY - 0.95)])
svia(UX - 0.05, UY - 0.95, "SHIFT_OUT")
xr = pad("R210", "1")[0] - 0.75
svia(xr, UY + 2.17, "SHIFT_OUT")
track("SHIFT_OUT", W_SIG, [(UX - 0.05, UY - 0.95), (UX - 0.05, UY + 2.17 - (UX - 0.05 - xr)), (xr, UY + 2.17)],
      layer=pcbnew.B_Cu)
track("SHIFT_OUT", W_SIG, [(xr, UY + 2.17), ("R210", "1")])
track("ADC_IN", W_SIG, [("R211", "1"), ("C207", "2")])
track("ADC_REF_MID", W_SIG, [("U202", "3"), ("C206", "2")])
track("+3V3", 0.6, [("U202", "5"), ("C210", "1")])
svia(UX + 2.48, UY - 1.6, "+3V3", why="supply")
track("+3V3", W_PWR, [("C210", "1"), (UX + 2.48, UY - 1.6)])
for ref, num, dx, dy in (("C210", "2", 0.62, 0), ("C207", "1", 0, 0.62), ("C206", "1", 0, 0.62)):
    x, y = pad(ref, num)
    track("GND", W_GND, [(x, y), (x + dx, y + dy)])
    via(x + dx, y + dy, "GND")
x, y = pad("U202", "2")
track("GND", W_GND, [(x, y), (x - 0.95, y)])
via(x - 0.95, y, "GND")
x, y = pad("R209", "2")
svia(x + 0.6, y, "HOLD_OUT")
track("HOLD_OUT", W_SIG, [(x, y), (x + 0.6, y)])
XH = UX1 - 0.25
track("HOLD_OUT", W_SIG, [(UX1, -1.9), (XH, -1.65), (XH, y - (x + 0.6 - XH)), (x + 0.6, y)], layer=pcbnew.B_Cu)
x, y = pad("C207", "2")
testpad("TP205", "ADC_IN", x, UY + 2.2)
track("ADC_IN", W_SIG, [(x, y), (x, UY + 2.2)])
x, y = pad("C206", "2")
d = UX - 1.75 - x
testpad("TP206", "ADC_REF_MID", UX - 1.75, UY + 3.0)
track("ADC_REF_MID", W_SIG, [(x, y), (x, y + 0.6), (UX - 1.75, y + 0.6 + d), (UX - 1.75, UY + 3.0)])
text("ADC_IN", pad("C207", "2")[0], UY + 3.1, 0.35)
text("REF_MID", UX - 0.1, UY + 3.0, 0.35)
text("U202 shift", UX + 3.0, UY + 2.3, 0.4)

# ============================================================================= balun, R204, STRB_A / STRB_K arms
XB = 11.0 + 0.47 + 1.47                    # R204 at x = 11.0, courtyards touching
two("R", "R204", "1k", 11.0, 0.0, "v", "STRB_A", "STRB_K")
custom("T401", "CMC_0805_balun", XB, 0.0,
       [("1", 0.835, -0.435, 0.76, 0.51, "STRB_CLIP", RR), ("3", 0.835, 0.435, 0.76, 0.51, "GND", RR),
        ("2", -0.835, -0.435, 0.76, 0.51, "STRB_A", RR), ("4", -0.835, 0.435, 0.76, 0.51, "STRB_K", RR)],
       (1.47, 0.94))
XV, YA = 10.2, 4.07                         # arm vertical x, arm horizontal |y|
for s, nn, pn, cref in ((-1, "STRB_A", "2", "C201"), (+1, "STRB_K", "4", "C202")):
    cp = pad(cref, "@" + nn)
    tp = pad("T401", pn)
    track(nn, W, [cp, (XV - 0.4, s * YA), (XV, s * (YA - 0.4)),
                  (XV, s * 0.935), (XV + 0.5, s * 0.435), tp], name=f"{nn} arm: 47 pF -> balun", z=50)
x, y = pad("T401", "3")
track("GND", W_GND, [(x, y), (x, y + 0.75)])
via(x, y + 0.75, "GND")

# ============================================================================= TRF37D73 #2, clip node, clamp, stub
YL = -0.435
XTAP = XB + 1.47 + 0.95                    # clamp courtyard touches the balun courtyard
XT = XTAP + 0.95 + 1.82 + 0.94 + 1.6       # D203 | C404 | FB402 | U402, courtyards touching
place("Package_SON", "WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm", "U402", "TRF37D73", XT, YL - 0.25, 180,
      {"1": "+3V3", "2": "TRF2_RFIN", "3": "GND", "4": "GND", "5": "GND", "6": "GND", "7": "TRF2_OUT",
       "8": "GND", "9": "GND"})
XC404 = XTAP + 0.95 + 0.91
two("C", "C404", "100n", XC404, YL, "h", "STRB_CLIP", "TRF2_OUT")
# bias tee (sim/bias_tee/RESULT.md): one straight chain perpendicular to the line, courtyards touching:
# FB402 BLM15HD102 with pad 1 centred ON the 50 R line (no stub) -> L402 47 uH 1210 (pad-wide link) with R416 1 k
# beside it -> C411 100 nF across the cold pad (GND via at its GND pad) -> +3V3 plane via pair beyond C411; C412 10 uF.
XFB = XC404 + 0.91 + 0.47
YFB = YL - 0.485                                 # bead centre: pad 1 (TRF2_OUT) on the line axis
two("FB", "FB402", "BLM15HD102", XFB, YFB, "v", "TRF2_BIAS", "TRF2_OUT")
YL402 = YFB - 0.93 - 2.28 - 0.09                # 1210 courtyard touches the bead / U402 courtyards
two("L", "L402", "47u LQH32CN", XFB, YL402, "v", "+3V3", "TRF2_BIAS")
XR416 = XFB + 1.58 + 0.47                       # 1 k damping resistor beside the 1210 (courtyards touching)
two("R", "R416", "1k", XR416, YL402, "v", "+3V3", "TRF2_BIAS")
place("Diode_SMD", "D_SOD-323", "D203", "BAT15-03W", XTAP, YL - 0.40 - 1.05, 90, {"1": "STRB_CLIP", "2": "GND"})
p7, p2 = pad("U402", "7"), pad("U402", "2")
NECK = 0.25                                     # WSON pad height
track("STRB_CLIP", W, [("T401", "1"), (XTAP, YL), ("C404", "1")], name="STRB_CLIP: balun.1 -> tap -> C404", z=50)
track("TRF2_OUT", W, [("C404", "2"), (p7[0] - 0.25, YL)], name="TRF2_OUT: C404 -> U402.7", z=50)
track("TRF2_OUT", NECK, [(p7[0] - 0.25, YL), p7], name="neck in U402.7 pad", z=50)
track("STRB_CLIP", 0.3, [(XTAP, YL), ("D203", "1")])
x, y = pad("D203", "2")
track("GND", W_GND, [(x, y), (x, y - 0.65)])
via(x, y - 0.65, "GND")
W_BT = 0.64                                     # bias-tee links as wide as the 0402 pads
track("TRF2_BIAS", W_BT, [("FB402", "@TRF2_BIAS"), ("L402", "@TRF2_BIAS")], name="bias tee: FB402 -> L402")
# R416 pads to the L402 pads: one 45-degree link each (R pad centre -> inside the 1210 pad)
for net_, sgn in (("TRF2_BIAS", 1), ("+3V3", -1)):
    rx, ry = pad("R416", "@" + net_)
    lx, ly = pad("L402", "@" + net_)
    d_ = rx - (lx + 1.325 - 0.18)
    track(net_, 0.5, [(rx, ry), (rx - d_, ry + sgn * d_)], name=f"bias tee: R416 -> L402 ({net_})")
# input side
XC403 = XT + 1.6 + 0.91
two("C", "C403", "100n", XC403, YL, "h", "TRF2_RFIN", "TRF2_IN")
XX2 = XC403 + 0.91 + 0.45
custom("X2", "IF_TRF2_IN", XX2, YL, [("1", 0, 0, 0.6, 0.5, "TRF2_IN", RR)], (0, 0))
track("TRF2_RFIN", NECK, [p2, (p2[0] + 0.25, YL)], name="neck in U402.2 pad", z=50)
track("TRF2_RFIN", W, [(p2[0] + 0.25, YL), ("C403", "1")], name="TRF2_RFIN: U402.2 -> C403", z=50)
track("TRF2_IN", W, [("C403", "2"), ("X2", "1")], name="TRF2_IN: C403 -> X2", z=50)
# ground pins to the exposed pad, 3 EP vias (0.2/0.45, tented)
for pn in ("3", "4", "5", "6", "8"):
    x, y = pad("U402", pn)
    track("GND", 0.25, [(x, y), (XT, y)])
for dy in (-0.55, 0.0, 0.55):
    svia(XT, YL - 0.25 + dy, "GND", why="gnd")
# VCC pin 1: 1 nF + 100 nF in a row right below, via pair to In2
p1 = pad("U402", "1")
XC5 = XT + 1.6 + 0.46
two("C", "C405", "1n", XC5, 0.565 + 0.91, "v", "+3V3", "GND")
two("C", "C406", "100n", XC5 + 0.92, 0.565 + 0.91, "v", "+3V3", "GND")
c5 = pad("C405", "@+3V3")
track("+3V3", 0.25, [p1, (c5[0] - (c5[1] - p1[1]), p1[1]), c5])
track("+3V3", W_PWR, [c5, ("C406", "@+3V3"), (XC5 + 0.92 + 0.62, c5[1])])
svia(XC5 + 0.92 + 0.62, c5[1], "+3V3", why="supply")
for c in ("C405", "C406"):
    x, y = pad(c, "@GND")
    track("GND", W_GND, [(x, y), (x, y + 0.6)])
    via(x, y + 0.6, "GND")
# L402 cold end: C411 100 nF horizontal right across the cold pad (+3V3 pad over it, GND pad beside, GND via at
# that pad); the +3V3 plane via pair sits beyond C411 (supply enters through the capacitor), C412 10 uF next to it.
yt = pad("L402", "@+3V3")[1]
YC411 = YL402 - 2.28 - 0.46                     # courtyards touching
two("C", "C411", "100n", XFB + 0.48, YC411, "h", "+3V3", "GND")
cpx, cpy = pad("C411", "@+3V3")
track("+3V3", 0.56, [(cpx, cpy), (cpx, yt)], name="bias tee: C411 -> L402 cold pad")
gx, gy = pad("C411", "@GND")
track("GND", W_GND, [(gx, gy), (gx + 0.62, gy)])
via(gx + 0.62, gy, "GND")
VIA_Y = cpy - 0.31 - 0.1 - 0.3 - 0.05
for dx in (-0.36, 0.36):                         # plane via pair on the far side of C411
    via(cpx + dx, VIA_Y, "+3V3", why="supply")
track("+3V3", 0.6, [(cpx - 0.36, VIA_Y), (cpx + 0.36, VIA_Y)])
track("+3V3", 0.56, [(cpx, VIA_Y), (cpx, cpy)])
XC412 = XFB - 0.91 - 1.7                        # 10 uF 0805 left of C411, +3V3 pad towards it
YC412 = VIA_Y                                   # on the via row: C412 -> plane vias -> C411 -> L402
assert YC412 + 0.98 <= YL402 - 2.28 + 1e-6
two("C", "C412", "10u", XC412, YC412, "h", "GND", "+3V3", size="0805")
track("+3V3", 0.6, [("C412", "@+3V3"), (cpx - 0.36, VIA_Y)])
gx, gy = pad("C412", "@GND")
track("GND", W_GND, [(gx, gy), (gx - 0.75, gy)])
via(gx - 0.75, gy, "GND")
VPWR_Y = min(VIA_Y - 0.2, YC412 - 0.98 + 0.45)
testpad("TP401", "+3V3", XX2 - 0.2, -4.6, bottom=True)
via(XX2 - 0.2, -3.6, "+3V3", why="supply")
track("+3V3", W_PWR, [(XX2 - 0.2, -3.6), (XX2 - 0.2, -4.6)], layer=pcbnew.B_Cu)
testpad("TP207", "GND", -5.1, 6.2, bottom=True)
text("+3V3", XX2 - 0.2, -5.6, 0.45, pcbnew.B_SilkS)
text("GND", -5.1, 7.25, 0.45, pcbnew.B_SilkS)

# shorted stub: 80 ps one way from the tap centre; down, right, down, ends in NT401 + 2 GND vias
L_STUB = 80.0 / PS_MM
Y1, X2R, CH = 3.9, XT + 1.95, 0.45
legs = [(XTAP, YL), (XTAP, Y1), (X2R, Y1)]
pre = chamfer(legs + [(X2R, Y1 + 1)], CH)[:-1]
used = sum(math.hypot(b2[0] - a[0], b2[1] - a[1]) for a, b2 in zip(pre, pre[1:]))
y_end = pre[-1][1] + (L_STUB - used)
stub_pts = pre + [(X2R, y_end)]
track("STRB_CLIP", W, stub_pts, name="stub: tap -> short (80 ps)", z=50)
custom("NT401", "NetTie_stub_short", X2R, y_end + 0.5,
       [("1", 0, -0.5, 0.36, 0.36, "STRB_CLIP", pcbnew.PAD_SHAPE_CIRCLE),
        ("2", 0, 0.4, 0.7, 0.7, "GND", pcbnew.PAD_SHAPE_CIRCLE)], (0, 0))
nt = FPS["NT401"]
cu = pcbnew.FP_SHAPE(nt, pcbnew.SHAPE_T_SEGMENT)
cu.SetLayer(pcbnew.F_Cu)
cu.SetWidth(mm(W))
cu.SetStart0(pcbnew.VECTOR2I(0, mm(-0.5)))
cu.SetEnd0(pcbnew.VECTOR2I(0, mm(0.4)))
cu.SetDrawCoord()
nt.Add(cu)
if hasattr(nt, "AddNetTiePadGroup"):
    nt.AddNetTiePadGroup("1, 2")
for dx in (-0.7, 0.7):
    via(X2R + dx, y_end + 0.9, "GND", why="stub short")
track("GND", W_GND, [(X2R - 0.7, y_end + 0.9), (X2R + 0.7, y_end + 0.9)])

# ============================================================================= outline
BX0, BX1 = pad("X1", "1")[0] - 0.3, XX2 + 0.3
BY0, BY1 = VPWR_Y - 0.65, max(y_end + 2.0, UY + 3.95)
for a, c in zip(rect_pts(BX0, BY0, BX1, BY1), rect_pts(BX0, BY0, BX1, BY1)[1:] + [(BX0, BY0)]):
    line(*a, *c)

# ============================================================================= silkscreen
text("BUF_OUT_S", pad("X1", "1")[0] + 0.9, -0.8, 0.4)
text("TRF2_IN", XX2 - 0.9, YL - 0.9, 0.4)
text("STRB_A", 8.3, -YA + 0.6, 0.4)
text("STRB_K", 8.3, YA - 0.6, 0.4)
text("80 ps stub", X2R - 3.2, Y1 + 0.75, 0.4)
text("SAMPLER fragment 4L JLC04161H-7628", 14.5, BY1 - 0.5, 0.4)

# ============================================================================= zones
IN = 0.2
outline = rect_pts(BX0 + IN, BY0 + IN, BX1 - IN, BY1 - IN)
HOLD_CUT = rect_pts(2.25, -0.42, 5.15, 1.5)        # under D202.3, the hold trace, U201.3, C205.1
zone("GND", [pcbnew.In1_Cu], outline, clearance=0.2)
zone("+3V3", [pcbnew.In2_Cu], outline, clearance=0.3)
zone("GND", [pcbnew.B_Cu], outline, clearance=0.25)
zone("GND", [pcbnew.F_Cu], outline, clearance=0.25, prio=0)
zone(None, [pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu], HOLD_CUT, rule=True)
zone(None, [pcbnew.F_Cu], rect_pts(1.5, -1.0, 5.9, 2.05), rule=True)      # no top pour at the guard / hold node
# RF clearance: no top pour within GAP_RF of any RF trace edge (keep-out per segment, octagonal ends)
RF_KEEP = GAP_RF + W / 2
for nm, r in ROUTES.items():
    if r["z"] is None:
        continue
    for x0, y0, x1, y1 in r["segs"]:
        L = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        nx, ny = -uy, ux
        e = RF_KEEP * math.tan(math.pi / 8)
        pts = [(x0 - ux * RF_KEEP + nx * e, y0 - uy * RF_KEEP + ny * e), (x0 - ux * e + nx * RF_KEEP, y0 - uy * e + ny * RF_KEEP),
               (x1 + ux * e + nx * RF_KEEP, y1 + uy * e + ny * RF_KEEP), (x1 + ux * RF_KEEP + nx * e, y1 + uy * RF_KEEP + ny * e),
               (x1 + ux * RF_KEEP - nx * e, y1 + uy * RF_KEEP - ny * e), (x1 + ux * e - nx * RF_KEEP, y1 + uy * e - ny * RF_KEEP),
               (x0 - ux * e - nx * RF_KEEP, y0 - uy * e - ny * RF_KEEP), (x0 - ux * RF_KEEP - nx * e, y0 - uy * RF_KEEP - ny * e)]
        zone(None, [pcbnew.F_Cu], pts, rule=True)
for ref in ("R201", "C403", "C404", "T401", "R204", "D201", "D202", "C201", "C202", "FB402"):   # RF pads: pour away too
    for p in FPS[ref].Pads():
        if p.GetNetname() == "GND":
            continue
        x, y = loc(p.GetPosition())
        sx, sy = pcbnew.ToMM(p.GetBoundingBox().GetWidth()) / 2 + GAP_RF, pcbnew.ToMM(p.GetBoundingBox().GetHeight()) / 2 + GAP_RF
        zone(None, [pcbnew.F_Cu], rect_pts(x - sx, y - sy, x + sx, y + sy), rule=True)

filler = pcbnew.ZONE_FILLER(b)
filler.Fill(b.Zones())

# ============================================================================= reports


def route_len(name):
    return sum(math.hypot(x1 - x0, y1 - y0) for x0, y0, x1, y1 in ROUTES[name]["segs"])


zc, eec = cpwg(W, GAP_RF)
zms0 = microstrip(W, t=1e-6, mask=False)[0]          # same assumptions as the CPWG formula (t = 0, no mask)
lo, hi = 0.05, 2.0
for _ in range(50):
    m = (lo + hi) / 2
    lo, hi = (m, hi) if cpwg(W, m)[0] < zms0 else (lo, m)
G_X = (lo + hi) / 2
print(f"Stack-up JLC04161H-7628: h={H} mm er={ER}, t={T_CU} mm, mask er={ER_MASK} {C_MASK_TR * 1e3:.0f}/{C_MASK_SUB * 1e3:.0f} um")
print(f"50 R microstrip (H-J + t + mask): exact {W50_EXACT:.3f} mm -> drawn {W:.2f} mm: Z0={Z50:.2f} R, "
      f"eps_eff={EEFF:.3f}, {PS_MM:.3f} ps/mm   (no mask: Z0={microstrip(W, mask=False)[0]:.2f} R)")
print(f"coplanar check (Wadell CPWG, t=0, no mask): side ground starts to pull Z below the microstrip value "
      f"({zms0:.1f} R) only for gaps < {G_X:.2f} mm = {G_X / H:.1f} h; pour gap used {GAP_RF:.2f} mm = {GAP_RF / H:.1f} h "
      f"(CPWG formula there {zc:.1f} R, above microstrip = out of its range) -> line is microstrip-dominated")
print(f"{'RF segment / route':42s} {'net':10s} {'w mm':>5s} {'Z0 int':>6s} {'Z0 calc':>7s} {'len mm':>7s} {'ps':>6s}")
for nm, r in ROUTES.items():
    if r["z"] is None and not nm.startswith("HOLD"):
        continue
    L = route_len(nm)
    zz = microstrip(r["width"])[0]
    print(f"{nm:42s} {r['net']:10s} {r['width']:5.2f} {str(r['z'] or '-'):>6s} {zz:7.1f} {L:7.3f} {L * ps_mm(r['width']):6.1f}")
print("\nlength-defined elements: intended vs actual")
la, lk = route_len("STRB_A arm: 47 pF -> balun"), route_len("STRB_K arm: 47 pF -> balun")
ls_ = route_len("stub: tap -> short (80 ps)")
print(f"  shorted stub     80.0 ps  {L_STUB:.3f} mm  -> actual {ls_:.3f} mm = {ls_ * PS_MM:.2f} ps (tap centre to net-tie pad)")
print(f"  STRB_A / STRB_K  equal    -> {la:.3f} / {lk:.3f} mm = {la * PS_MM:.2f} / {lk * PS_MM:.2f} ps, mismatch {abs(la - lk) * 1e3:.1f} um")
for a_, k_ in (("BRG_A rail D201", "BRG_K rail D201"), ("BRG_A rail D202", "BRG_K rail D202")):
    print(f"  {a_} / {k_}: {route_len(a_):.3f} / {route_len(k_):.3f} mm")
print(f"  BUF_OUT_S + BRG_IN (X1 -> D201.3) {route_len('BUF_OUT_S: X1 -> R201') + route_len('BRG_IN: R201 -> D201.3 (under D201)'):.3f} mm")

print("\npad discontinuities (excess C of the pad vs the 0.36 mm line it replaces, C' line "
      f"{c_per_mm(W):.4f} pF/mm):")
for ref, num, wp, lp in (("R201/C403/C404", "0402", 0.62, 0.55), ("R204 (shunt, on line)", "0402", 0.64, 0.54),
                         ("T401", "pad", 0.51, 0.76), ("D201/D202 pins", "SOT-323", 0.45, 0.7),
                         ("D203 cathode", "SOD-323", 0.45, 0.6), ("X1/X2", "iface", 0.5, 0.6),
                         ("U402 pins 2/7", "WSON", 0.25, 0.5)):
    dc = (c_per_mm(wp) - c_per_mm(W)) * lp
    print(f"  {ref:24s} {num:8s} {wp:.2f} x {lp:.2f} mm  dC = {dc * 1e3:+.1f} fF")
print("vias:", N_VIA)

# --- sanity: bends (every vertex of every polyline turns by <= 45 degrees)
bad = []
for nm, pts, lay in POLYS:
    for a, c, d in zip(pts, pts[1:], pts[2:]):
        v1 = (c[0] - a[0], c[1] - a[1])
        v2 = (d[0] - c[0], d[1] - c[1])
        ang = math.degrees(math.acos(max(-1, min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / math.hypot(*v1) / math.hypot(*v2)))))
        if ang > 45.5:
            bad.append(f"{nm} at ({c[0]:.2f}, {c[1]:.2f}): {ang:.0f} deg")
print("bend check (<= 45 deg per vertex):", "OK" if not bad else bad)

# --- sanity: courtyards
errs = []
fps = list(b.GetFootprints())
boxes = {}
for fp in fps:
    fp.BuildCourtyardCaches()
    side = pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd
    c = fp.GetCourtyard(side)
    if c.OutlineCount():
        bb = c.BBox()
        boxes[fp.GetReference()] = (side, pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()),
                                    pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
refs = sorted(boxes)
for i, r1 in enumerate(refs):
    for r2 in refs[i + 1:]:
        a, c = boxes[r1], boxes[r2]
        if a[0] != c[0]:
            continue
        ox = min(a[3], c[3]) - max(a[1], c[1])
        oy = min(a[4], c[4]) - max(a[2], c[2])
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
                            f"({loc(t.GetPosition())[0]:.2f}, {loc(t.GetPosition())[1]:.2f})")
        for p in pads:
            if p.GetNetCode() == t.GetNetCode() or not p.IsOnLayer(lay):
                continue
            if p.GetParent().GetReference() == "NT401":
                continue
            if st.Collide(p.GetEffectiveShape(lay), CLR):
                errs.append(f"clearance {t.GetNetname()} / pad {p.GetParent().GetReference()}.{p.GetNumber()} "
                            f"({p.GetNetname()}) on {b.GetLayerName(lay)}")
for i, p in enumerate(pads):
    for q in pads[i + 1:]:
        if p.GetParent() is q.GetParent() or p.GetNetCode() == q.GetNetCode():
            continue
        for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
            if p.IsOnLayer(lay) and q.IsOnLayer(lay) and \
                    p.GetEffectiveShape(lay).Collide(q.GetEffectiveShape(lay), CLR):
                errs.append(f"pad clearance {p.GetParent().GetReference()}.{p.GetNumber()} / "
                            f"{q.GetParent().GetReference()}.{q.GetNumber()}")
print("courtyard / clearance check:", "OK" if not errs else f"{len(errs)} problems")
for e in sorted(set(errs))[:40]:
    print("  ", e)
print(f"board {BX1 - BX0:.1f} x {BY1 - BY0:.1f} mm")

pcbnew.SaveBoard(OUT, b)

STACKUP = """    (stackup
      (layer "F.SilkS" (type "Top Silk Screen"))
      (layer "F.Paste" (type "Top Solder Paste"))
      (layer "F.Mask" (type "Top Solder Mask") (thickness 0.015) (epsilon_r 3.8))
      (layer "F.Cu" (type "copper") (thickness 0.035))
      (layer "dielectric 1" (type "prepreg") (thickness 0.2104) (material "7628") (epsilon_r 4.4) (loss_tangent 0.02))
      (layer "In1.Cu" (type "copper") (thickness 0.0152))
      (layer "dielectric 2" (type "core") (thickness 1.065) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
      (layer "In2.Cu" (type "copper") (thickness 0.0152))
      (layer "dielectric 3" (type "prepreg") (thickness 0.2104) (material "7628") (epsilon_r 4.4) (loss_tangent 0.02))
      (layer "B.Cu" (type "copper") (thickness 0.035))
      (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.015) (epsilon_r 3.8))
      (layer "B.Paste" (type "Bottom Solder Paste"))
      (layer "B.SilkS" (type "Bottom Silk Screen"))
      (copper_finish "HAL lead-free")
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
rb = pcbnew.LoadBoard(OUT)                       # ratsnest on the saved, filled board
rb.BuildConnectivity()
rc = rb.GetConnectivity()
rc.RecalculateRatsnest()
print("unrouted connections after zone fill:", rc.GetUnconnectedCount(False))
for ext in (".kicad_pro", ".kicad_prl"):
    pth = OUT[:-len(".kicad_pcb")] + ext
    if os.path.exists(pth):
        os.remove(pth)
