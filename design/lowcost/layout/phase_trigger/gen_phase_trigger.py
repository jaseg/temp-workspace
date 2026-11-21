#!/usr/bin/env python3
"""Layout fragment "phase_trigger": trigger path and 16-tap phase-recovery delay line (re-layout, JLC04161H-7628).

BUF_OUT_T (50 R) / EXT_CLK (SMA, 49.9 R at the pin) -> TMUX136 (local -0.9 V switch ground) -> TLV3801
(+/-2V5, IN- = TRIG_LEVEL) -> 100 R across CMP_P/CMP_N (2 x 50 R lines) -> CMP_P: 1 uF -> TRF37D73 (120 nH +
47 uH bias) -> 1 uF -> 12 dB pi pad 82/91/82 -> PH_LINE;  CMP_N: 1 uF -> 49.9 R dummy;  2 x 470 R -> SN65LVDS2
-> COARSE.  Delay line (SPEC decision 4, co-propagating), everything on F.Cu over the solid In1 ground, no
vias in any RF path: PSTRB_A / PSTRB_K straight 73 R lines at 40 ps per tap (loaded), PH_LINE meanders
between the gates (loaded 50 R, 70 ps per tap designed, about 75 ps expected; effective spacing 75 - 40 = 35 ps).
Per tap: BAT15-04W straddling PH_LINE (line between pins 1/2 onto pin 3 = zero-length tap), 2 x 0.47 pF C0G
bridging pin 1 / pin 2 to the strobe lines, 1 k and 2.2 k straddling each strobe line (perpendicular),
COS3502 comparators in a row behind PSTRB_A.  No stitching grid (user applies stitching after assembling
the fragments); only functional vias.

Run: python3 gen_phase_trigger.py  -> phase_trigger.kicad_pcb, prints stack-up, impedance and delay tables,
RF segment table, pad discontinuities and the checks.  KiCad 7.0 pcbnew API.  kicad-cli 7 has no DRC.
Coordinates in mm, origin = centre of the tap-0 diode, +x towards the far end, +y down (PSTRB_K side).
"""
import math, os, tempfile
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "phase_trigger.kicad_pcb")
FPLIB = "/usr/share/kicad/footprints"
ORG = (150.0, 100.0)
mm = pcbnew.FromMM

# ============================================================================= stack-up / impedance
# JLC04161H-7628 (jlcpcb.com/impedance, checked 2026-11): L1 35 um / 7628 prepreg 0.2104 mm er 4.4 /
# L2 15.2 um / core 1.065 mm er 4.6 / L3 15.2 um / 7628 0.2104 mm / L4 35 um.  Mask er 3.8, 0.6 mil (15 um)
# over the trace, 1.2 mil (30 um) over bare laminate.
H, T_CU, ER, ER_MASK, C_MASK_TR, C_MASK_SUB = 0.2104, 0.035, 4.4, 3.8, 0.015, 0.030
C0 = 0.299792458                                   # mm/ps


def microstrip(w, h=H, t=T_CU, er=ER, mask=True):
    """Hammerstad-Jensen microstrip, Hammerstad thickness correction, first-order solder-mask overlay
    (mask replaces air in the covered part of the fringing field:
    eps_eff += (er_mask - 1) (1 - q) (1 - exp(-1.2 c / h)), q = filling factor, c = mean mask thickness).
    Returns (Z0, eps_eff)."""
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
    if mask:
        q = (ee - 1) / (er - 1)
        ee += (ER_MASK - 1) * (1 - q) * (1 - math.exp(-1.2 * (C_MASK_TR + C_MASK_SUB) / 2 / h))
    return z_air(u1) / math.sqrt(ee), ee


def _K(k):
    a, b = 1.0, math.sqrt(1 - k * k)
    for _ in range(30):
        a, b = (a + b) / 2, math.sqrt(a * b)
    return math.pi / (2 * a)


def cpwg(w, g, h=H, er=ER):
    """Conductor-backed coplanar waveguide (t = 0, no mask), Wadell -> (Z0, eps_eff)."""
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


def c_per_mm(w):                                    # pF/mm
    z, ee = microstrip(w)
    return math.sqrt(ee) / (C0 * z)


def loaded(tdu, z, cl):
    """Section (delay tdu ps, Z0 z) + lumped cl pF -> (loaded delay ps, loaded Z)."""
    td = math.sqrt(tdu * (tdu + z * cl))
    return td, z * tdu / td


def solve_tdu(z, cl, target):
    lo, hi = 0.5, target
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if loaded(m, z, cl)[0] < target else (lo, m)
    return (lo + hi) / 2


def r01(x):
    return round(x / 0.01) * 0.01


W50 = r01(width_for(50.0))                          # 0.36 mm
Z50, EE50 = microstrip(W50)
GAP_RF = 2 * W50                                    # pour clearance from 50 R trace edges
W_STR = r01(width_for(73.0))                        # strobe sections 73 R
Z_STR = microstrip(W_STR)[0]
W_NODE, W_SIG, W_PWR, W_GND = 0.15, 0.2, 0.5, 0.4
# --- strobe: 0.40 pF gate + excess of the hold-cap pad the line runs through (0.62 along x 0.56 across)
#     + ~0.01 pF fringe per straddling 0402 resistor (2 per tap, pads 0.165 mm from the line edge, estimate)
C_PAD_STR = (c_per_mm(0.56) - c_per_mm(W_STR)) * 0.62
CL_STR = 0.40 + C_PAD_STR + 0.02
TD_STR = 40.0                                      # 40 ps strobe / 75 ps line per tap: effective spacing still 35 ps;
#                                                   the longer pitch gives the meander >= 0.5 mm same-net gaps
TDU_STR = solve_tdu(Z_STR, CL_STR, TD_STR)
PITCH = round(TDU_STR / ps_mm(W_STR), 3)
# --- signal line: loaded 50 R at 70 ps / tap; load 0.37 pF gate + pin-3 pad excess (0.70 x 0.45 mm)
TD_LIN = 70.0                                      # aims 5 ps short: sim/phase_array measured +5 ps on the loaded line
W_LIN = 0.25
for _ in range(3):
    C_PAD_LIN = (c_per_mm(0.45) - c_per_mm(W_LIN)) * 0.70
    CL_LIN = 0.37 + C_PAD_LIN
    z_t = math.sqrt(50.0 * TD_LIN / (TD_LIN / 50.0 - CL_LIN))   # L = Zl td, C_line = td / Zl - CL
    W_LIN_EXACT = width_for(z_t)
    W_LIN = r01(W_LIN_EXACT)
Z_LIN = microstrip(W_LIN)[0]
TDU_LIN = solve_tdu(Z_LIN, CL_LIN, TD_LIN)
L_LIN = TDU_LIN / ps_mm(W_LIN)                      # trace length per tap (pin 3 centre to pin 3 centre)
NT = 16
XT = [n * PITCH for n in range(NT)]
X15 = XT[-1]

# ============================================================================= board
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
ds.m_TrackMinWidth = mm(0.1)
ds.m_ViasMinSize = mm(0.4)
ds.m_MinThroughDrill = mm(0.2)
nc = ds.m_NetSettings.m_DefaultNetClass
nc.SetClearance(mm(0.1))
nc.SetTrackWidth(mm(0.2))
nc.SetViaDiameter(mm(0.45))
nc.SetViaDrill(mm(0.2))

NETS, FPS, ROUTES, POLYS, RFPADS = {}, {}, {}, [], []
RR = pcbnew.PAD_SHAPE_ROUNDRECT
CIRC = pcbnew.PAD_SHAPE_CIRCLE
N_VIA = {"gnd": 0, "supply": 0, "signal": 0}


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
    fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.25), mm(0.25)))
    fp.Reference().SetTextThickness(mm(0.04))
    fp.Reference().SetPosition(fp.GetPosition())
    fp.Value().SetVisible(False)
    b.Add(fp)
    FPS[ref] = fp
    return fp


def place(lib, name, ref, val, x, y, rot, nets, cond=None):
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


def two(kind, ref, val, x, y, orient, na, nb):
    """2-terminal part. orient 'h': na left / nb right; 'v': na up / nb down."""
    lib, name = {"R": ("Resistor_SMD", "R_0402_1005Metric"), "C": ("Capacitor_SMD", "C_0402_1005Metric"),
                 "L": ("Inductor_SMD", "L_0402_1005Metric"), "L1008": ("Inductor_SMD", "L_1008_2520Metric"),
                 "L1210": ("Inductor_SMD", "L_1210_3225Metric")}[kind]
    if orient == "h":
        return place(lib, name, ref, val, x, y, 0, {"1": na, "2": nb})
    return place(lib, name, ref, val, x, y, 90, {"1": nb, "2": na})


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


def testpad(ref, nn, x, y, label=None, lx=0.0, ly=-0.85, size=0.35):
    custom(ref, "TestPoint_Pad_D1.0mm", x, y, [("1", 0, 0, 1.0, 1.0, nn, CIRC)], (0.55, 0.55))
    text(label or nn, x + lx, y + ly, size)


def iface(ref, nn, x, y, sx=0.6, sy=0.5):
    custom(ref, "IF_" + nn, x, y, [("1", 0, 0, sx, sy, nn, RR)], (0, 0))


def pad(ref, num):
    for p in FPS[ref].Pads():
        if p.GetNumber() == num or (num[0] == "@" and p.GetNetname() == num[1:]):
            return loc(p.GetPosition())
    raise KeyError((ref, num))


def chamfer(pts, c):
    """Cut every corner of an axis/45-degree polyline with a 45-degree chamfer (leg c, limited by the legs)."""
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        (xa, ya), (xb, yb), (xc, yc) = pts[i - 1], pts[i], pts[i + 1]
        la, lc = math.hypot(xb - xa, yb - ya), math.hypot(xc - xb, yc - yb)
        v1 = ((xb - xa) / la, (yb - ya) / la)
        v2 = ((xc - xb) / lc, (yc - yb) / lc)
        ang = math.degrees(math.acos(max(-1, min(1, v1[0] * v2[0] + v1[1] * v2[1]))))
        if ang < 46:
            out.append((xb, yb))
            continue
        cc = min(c, la / 2.01 if i > 1 else la * 0.99, lc / 2.01 if i < len(pts) - 2 else lc * 0.99)
        out.append((xb - v1[0] * cc, yb - v1[1] * cc))
        out.append((xb + v2[0] * cc, yb + v2[1] * cc))
    out.append(pts[-1])
    return out


def track(netname, width, pts, layer=pcbnew.F_Cu, name=None, z=None, ch=0.2, check=True):
    """Polyline; pad references are resolved; 90-degree corners chamfered with leg ch."""
    pts = [pad(*p) if isinstance(p[0], str) else p for p in pts]
    q = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p[0] - q[-1][0], p[1] - q[-1][1]) > 1e-6:
            q.append(p)
    if ch and len(q) > 2:
        q = chamfer(q, ch)
    for (x0, y0), (x1, y1) in zip(q, q[1:]):
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(P(x0, y0))
        t.SetEnd(P(x1, y1))
        t.SetWidth(mm(width))
        t.SetLayer(layer)
        t.SetNet(net(netname))
        b.Add(t)
        if name:
            r = ROUTES.setdefault(name, {"net": netname, "width": width, "z": z, "segs": [], "layer": layer})
            r["segs"].append((x0, y0, x1, y1))
    if check:
        POLYS.append((name or netname, q))
    return q


def via(x, y, netname, why="gnd", drill=0.2, dia=0.45):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(P(x, y))
    v.SetDrill(mm(drill))
    v.SetWidth(mm(dia))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetNet(net(netname))
    b.Add(v)
    N_VIA[why] += 1
    return v


def gvia(x, y):
    return via(x, y, "GND", "gnd")


def text(s, x, y, size=0.4, layer=pcbnew.F_SilkS, rot=0):
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


def zone(netname, layers, pts, clearance=0.2, prio=0, rule=False):
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
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_AREA)
        z.SetMinIslandArea(int(mm(1.0)) * int(mm(1.0)))
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(mm(x + ORG[0]), mm(y + ORG[1]))
    b.Add(z)
    return z


def rfpad(ref, num):
    RFPADS.append((ref, num))


# ============================================================================= delay line geometry
# Tap cell (relative to XT[n]): D at (0,0), pins 1/2 at (-1.0, -/+0.65), pin 3 at (+1.0, 0).
# PH_LINE: enters between pins 1/2 at y = 0, ends in pin 3, leaves pin 3 downward: S meander
# x = 1.0 (down to +Y) -> XU (up to -Y) -> XD (down) -> 45 deg landing at x = PITCH - 1.55 -> next pin 3.
X_P3, X_P12 = 1.0, -1.0
XD = PITCH - 1.75
PAD3_HALF_X = 0.35                                  # pin-3 pad half length along x
XU = (XD + X_P3 + PAD3_HALF_X - W_LIN / 2) / 2      # equal gaps: pin-3 pad edge to leg XU, leg XU to leg XD
GAP_PAD3 = XU - W_LIN / 2 - (X_P3 + PAD3_HALF_X)
assert GAP_PAD3 >= 0.4 and XD - XU - W_LIN >= 0.4, (GAP_PAD3, XD - XU - W_LIN)
E_LAND = 0.2
CH_M = 0.2


def cell_path(Y):
    return [(X_P3, 0.0), (X_P3, Y), (XU, Y), (XU, -Y), (XD, -Y), (XD, -E_LAND), (XD + E_LAND, 0.0),
            (PITCH + X_P3, 0.0)]


def plen(pts):
    return sum(math.hypot(b_[0] - a_[0], b_[1] - a_[1]) for a_, b_ in zip(pts, pts[1:]))


lo, hi = 0.3, 4.0
for _ in range(60):
    m = (lo + hi) / 2
    lo, hi = (m, hi) if plen(chamfer(cell_path(m), CH_M)) < L_LIN else (lo, m)
Y_M = (lo + hi) / 2
# strobe line height: meander edge + 0.3 mm + straddling-resistor inner pad (0.79 mm inside the line)
YL = math.ceil((Y_M + W_LIN / 2 + 0.3 + 0.79) / 0.05) * 0.05
YNODE = YL - 0.96                                   # hold-cap node pad centre (|y|)
X_R1K, X_R22K = -1.94, -0.06                        # straddling resistors (1 k to the comparator, 2.2 k to VTAP)
Y_RV = YL + 1.085                                   # |y| of the vias at the resistor outer pads

# ============================================================================= main chain positions (right to left)
X_R313 = -2.25
X_R312 = X_R313 - 0.31 - 0.35 - 0.76
X_R311 = X_R312 - 0.76 - 0.35 - 0.31
X_C309 = X_R311 - 0.31 - 0.35 - 0.76
X_L301 = X_C309 - 0.76 - 0.35 - 0.31
XU3 = X_L301 - 0.31 - 0.3 - 1.2
X_C308 = XU3 - 1.2 - 0.4 - 0.76
X_R309 = X_C308 - 0.76 - 0.35 - 0.31
X_R307 = X_R309 - 0.94
XU2 = X_R307 - 2.0
XU1 = XU2 - 4.425
Y_N = -0.96                                         # CMP_N line y after its bend
BX0 = XU1 - 11.5
BX1 = X15 + 5.0

# ============================================================================= TMUX136 (U301), inputs
place("Package_DFN_QFN", "Texas_UQFN-10_1.5x2mm_P0.5mm", "U301", "TMUX136", XU1, 0.25, 0,
      {"1": "BUF_OUT_T", "2": "VSW_GND", "3": "EXT_CLK", "4": "VSW_GND", "5": "VSW_GND", "6": "VSW_GND",
       "8": "TRIG_COM", "9": "TRIG_SEL_S", "10": "+2V5"})
iface("X1", "BUF_OUT_T", BX0 + 0.35, -0.5)
track("BUF_OUT_T", W50, [("X1", "1"), ("U301", "1")], name="BUF_OUT_T: X1 -> U301.1", z=50)
rfpad("X1", "1")
YS = 4.0
place("Connector_Coaxial", "SMA_Samtec_SMA-J-P-X-ST-EM1_EdgeMount", "J301", "SMA EXT_CLK", BX0 + 2.1, YS, 270,
      {"1": "EXT_CLK", "2": "GND"})            # rot 270: PCB edge of the footprint on BX0, body off-board
rfpad("J301", "1")
X_R301 = XU1 - 0.95 - 0.3 - 0.31
xa = X_R301 - 0.8 - (YS - 0.5)
track("EXT_CLK", W50, [("J301", "1"), (xa, YS), (xa + YS - 0.5, 0.5), ("U301", "3")], name="EXT_CLK: J301 -> U301.3",
      z=50, ch=0)
for p_ in FPS["J301"].Pads():
    if p_.GetNumber() == "2" and p_.IsOnLayer(pcbnew.F_Cu):
        gx, gy = loc(p_.GetPosition())
        gvia(gx + 2.43, gy)
two("R", "R301", "49.9", X_R301, 0.98, "v", "EXT_CLK", "GND")
rfpad("R301", "@EXT_CLK")
gvia(X_R301 - 0.31 - 0.1 - 0.225, 1.46)
track("GND", W_GND, [("R301", "@GND"), (X_R301 - 0.31 - 0.1 - 0.225, 1.46)], ch=0)
# VSW_GND: pin 2 -> via under the body; pins 4/5/6 in a local F.Cu polygon with the network below
track("VSW_GND", 0.15, [("U301", "2"), (XU1, 0.0)], ch=0)
for pn_ in ("4", "5", "6"):
    track("VSW_GND", 0.25, [("U301", pn_), (pad("U301", pn_)[0], 1.75)], ch=0)
track("VSW_GND", 0.3, [(XU1 - 0.9, 1.75), (XU1 - 0.2 + 0.94 * 3, 1.75)], ch=0)
via(XU1, 0.0, "VSW_GND", "supply")
via(XU1 - 0.9, 1.4, "VSW_GND", "supply")
for i, (kind, ref, val, other) in enumerate((("C", "C303", "1n C0G", "GND"), ("C", "C302", "100n", "GND"),
                                             ("R", "R303", "1.5k", "GND"), ("R", "R304", "2.7k", "-2V5"))):
    x = XU1 - 0.2 + 0.94 * i
    two(kind, ref, val, x, 2.38, "v", "VSW_GND", other)
    if other == "GND":
        gvia(x, 3.42)
        track("GND", W_GND, [(ref, "@GND"), (x, 3.42)], ch=0)
X_R304 = XU1 - 0.2 + 0.94 * 3
testpad("TP303", "-2V5", X_R304, 4.5, ly=0.85)
track("-2V5", W_PWR, [("R304", "@-2V5"), (X_R304, 4.5)], ch=0)
via(X_R304 + 0.65, 3.4, "-2V5", "supply")
track("-2V5", W_PWR, [(X_R304, 3.4), (X_R304 + 0.65, 3.4)], ch=0)
# VCC (+2V5) pin 10 -> C301 (to the switch ground) right above, +2V5 via pair to In2
two("C", "C301", "100n", XU1, -1.96, "v", "VSW_GND", "+2V5")
track("+2V5", 0.3, [("U301", "10"), ("C301", "@+2V5")], ch=0)
for dx in (-0.635, -1.2):
    via(XU1 + dx, -1.48, "+2V5", "supply")
    track("+2V5", 0.3, [("C301", "@+2V5"), (XU1 + dx, -1.48)], ch=0)
via(XU1, -3.0, "VSW_GND", "supply")
track("VSW_GND", 0.3, [("C301", "@VSW_GND"), (XU1, -3.0)], ch=0)
# SEL: pin 9 -> SEL_S node: R305 10 k from TRIG_SEL, R306 18 k to -2V5
X_R305, X_R306 = XU1 + 1.05, XU1 + 2.0
two("R", "R305", "10k", X_R305, -1.98, "v", "TRIG_SEL", "TRIG_SEL_S")
two("R", "R306", "18k", X_R306, -1.98, "v", "-2V5", "TRIG_SEL_S")
track("TRIG_SEL_S", W_SIG, [("U301", "9"), (XU1 + 0.75, -0.5), (X_R305, -0.8), ("R305", "@TRIG_SEL_S")], ch=0)
track("TRIG_SEL_S", W_SIG, [("R305", "@TRIG_SEL_S"), ("R306", "@TRIG_SEL_S")], ch=0)
via(X_R306, -3.03, "-2V5", "supply")
track("-2V5", 0.3, [("R306", "@-2V5"), (X_R306, -3.03)], ch=0)
testpad("TP301", "TRIG_SEL", X_R305, -4.4, ly=-1.5)
track("TRIG_SEL", W_SIG, [("R305", "@TRIG_SEL"), (X_R305, -4.4)], ch=0)
testpad("TP304", "+2V5", XU1 - 1.2, -4.4)
track("+2V5", W_PWR, [(XU1 - 1.2, -1.48), (XU1 - 1.2, -4.4)], ch=0)

# ============================================================================= TLV3801 (U302)
# rot: bottom row (y = 0) IN+ 5, VCC 6, VCC 7, OUT+ 8; top row (y = -1.9) IN- 4, VEE 3, GND 2, OUT- 1; EP = VEE
place("Package_SON", "WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm", "U302", "TLV3801", XU2, -0.95, None,
      {"1": "CMP_N", "2": "GND", "3": "-2V5", "4": "TRIG_LEVEL", "5": "TRIG_COM", "6": "+2V5", "7": "+2V5",
       "8": "CMP_P", "9": "-2V5"},
      cond=lambda pp: pp["5"][0] < -0.5 and pp["5"][1] > 0.5 and pp["8"][0] > 0.5 and pp["8"][1] > 0.5)
track("TRIG_COM", W50, [("U301", "8"), ("U302", "5")], name="TRIG_COM: U301.8 -> U302.5", z=50)
# VCC pins 6/7 -> bar -> C304 below, +2V5 via pair
two("C", "C304", "100n", XU2 - 0.25, 1.26, "v", "+2V5", "GND")
track("+2V5", 0.25, [("U302", "6"), (XU2 - 0.25, 0.5)], ch=0)
track("+2V5", 0.25, [("U302", "7"), (XU2 + 0.25, 0.5)], ch=0)
track("+2V5", 0.25, [(XU2 - 0.25, 0.5), (XU2 + 0.25, 0.5)], ch=0)
for dx in (-0.635, 0.635):
    via(XU2 - 0.25 + dx, 0.95, "+2V5", "supply")
    track("+2V5", 0.3, [(XU2 - 0.25, 0.95), (XU2 - 0.25 + dx, 0.95)], ch=0)
gvia(XU2 - 0.25, 2.3)
track("GND", W_GND, [("C304", "@GND"), (XU2 - 0.25, 2.3)], ch=0)
# VEE: pin 3 -> EP, C305 above pin 3; EP vias to the B.Cu -2V5 polygon
two("C", "C305", "100n", XU2 - 0.35, -3.16, "v", "GND", "-2V5")
track("-2V5", 0.25, [("U302", "3"), (XU2 - 0.25, -2.6)], ch=0)
track("-2V5", 0.25, [("U302", "3"), (XU2 - 0.25, -1.3)], ch=0)
for dx in (-0.4, 0.4):
    via(XU2 + dx, -0.95, "-2V5", "supply")
gvia(XU2 - 0.35, -4.2)
track("GND", W_GND, [("C305", "@GND"), (XU2 - 0.35, -4.2)], ch=0)
track("GND", 0.2, [("U302", "2"), (XU2 + 0.25, -2.4), (XU2 + 0.55, -2.7)], ch=0)
gvia(XU2 + 0.55, -2.92)
track("GND", 0.2, [(XU2 + 0.55, -2.7), (XU2 + 0.55, -2.92)], ch=0)
# IN- = TRIG_LEVEL: 10 nF at the pin, test pad above
two("C", "C306", "10n", XU2 - 1.3, -3.16, "v", "GND", "TRIG_LEVEL")
track("TRIG_LEVEL", W_SIG, [("U302", "4"), (XU2 - 0.75, -2.13), ("C306", "@TRIG_LEVEL")], ch=0)
gvia(XU2 - 1.3, -4.2)
track("GND", W_GND, [("C306", "@GND"), (XU2 - 1.3, -4.2)], ch=0)
testpad("TP302", "TRIG_LEVEL", XU2 - 1.85, -5.4)
track("TRIG_LEVEL", W_SIG, [("C306", "@TRIG_LEVEL"), (XU2 - 1.85, -2.68), (XU2 - 1.85, -5.4)])

# ============================================================================= outputs: 100 R, 470 R bridge, dummy
two("R", "R307", "100", X_R307, -0.48, "v", "CMP_N", "CMP_P")
two("R", "R309", "470", X_R309, 0.48, "v", "CMP_P", "LVDS_A")
two("R", "R310", "470", X_R309, Y_N - 0.48, "v", "LVDS_B", "CMP_N")
X_C307 = X_R309 + 0.94
two("C", "C307", "1u", X_C307, Y_N - 0.48, "v", "CMP_N_DUM", "CMP_N")
two("R", "R308", "49.9", X_C307, -3.26, "v", "GND", "CMP_N_DUM")
two("C", "C308", "1u", X_C308, 0.0, "h", "CMP_P", "TRF_IN")
for r_, n_ in (("R307", "1"), ("R307", "2"), ("R309", "@CMP_P"), ("R310", "@CMP_N"), ("C307", "@CMP_N"),
               ("C308", "1"), ("C308", "2"), ("C307", "@CMP_N_DUM"), ("R308", "@CMP_N_DUM")):
    rfpad(r_, n_)
p1 = pad("U302", "1")
track("CMP_N", W50, [p1, (p1[0] + 0.2, p1[1]), (p1[0] + 0.2 + (Y_N - p1[1]), Y_N), ("C307", "@CMP_N")],
      name="CMP_N: U302.1 -> R307 -> R310 -> C307", z=50, ch=0)
track("CMP_P", W50, [("U302", "8"), ("C308", "1")], name="CMP_P: U302.8 -> R307 -> R309 -> C308", z=50)
track("CMP_N_DUM", W50, [("C307", "@CMP_N_DUM"), ("R308", "@CMP_N_DUM")], name="CMP_N_DUM: C307 -> R308 (49.9 R)",
      z=50)
gvia(X_C307 + 0.31 + 0.1 + 0.225, -3.74)
track("GND", W_GND, [("R308", "@GND"), (X_C307 + 0.31 + 0.1 + 0.225, -3.74)], ch=0)
# SN65LVDS2 (U304) above; LVDS_A crosses under CMP_N on B.Cu (slow path)
YU4 = -6.0
place("Package_TO_SOT_SMD", "SOT-23-5", "U304", "SN65LVDS2", X_R309 - 1.137, YU4, 0,
      {"1": "+3V3", "2": "GND", "3": "LVDS_A", "4": "LVDS_B", "5": "COARSE"})
track("LVDS_B", W_SIG, [("R310", "@LVDS_B"), ("U304", "4")])
via(X_R309, 1.565, "LVDS_A", "signal")
track("LVDS_A", W_SIG, [("R309", "@LVDS_A"), (X_R309, 1.565)], ch=0)
xp3, yp3 = pad("U304", "3")
xv3 = xp3 - 0.66 - 0.325
via(xv3, yp3, "LVDS_A", "signal")
track("LVDS_A", W_SIG, [(X_R309, 1.565), (X_R309, yp3 + (X_R309 - xv3)), (xv3, yp3)], layer=pcbnew.B_Cu, ch=0)
track("LVDS_A", W_SIG, [(xv3, yp3), ("U304", "3")], ch=0)
xp1, yp1 = pad("U304", "1")
two("C", "C310", "100n", xp1 - 0.66 - 0.13 - 0.76, yp1, "h", "GND", "+3V3")
track("+3V3", 0.5, [("U304", "1"), ("C310", "@+3V3")], ch=0)
xc10 = pad("C310", "@+3V3")[0]
via(xc10, yp1 - 0.635, "+3V3", "supply")
via(xc10 + 0.57, yp1 - 0.635, "+3V3", "supply")
track("+3V3", 0.4, [("C310", "@+3V3"), (xc10, yp1 - 0.635)], ch=0)
track("+3V3", 0.4, [("C310", "@+3V3"), (xc10 + 0.57, yp1 - 0.635)], ch=0)
xg10 = pad("C310", "@GND")[0]
gvia(xg10 - 0.6, yp1)
track("GND", W_GND, [("C310", "@GND"), (xg10 - 0.6, yp1)], ch=0)
xp2, yp2 = pad("U304", "2")
gvia(xp2 - 0.66 - 0.1 - 0.225, yp2)
track("GND", W_GND, [("U304", "2"), (xp2 - 0.66 - 0.1 - 0.225, yp2)], ch=0)
xp5, yp5 = pad("U304", "5")
testpad("TP305", "COARSE", xp5 + 0.4, yp5 - 1.6, lx=1.3, ly=0)
track("COARSE", W_SIG, [("U304", "5"), (xp5 + 0.4, yp5), (xp5 + 0.4, yp5 - 1.6)])

# ============================================================================= TRF37D73 line driver (U303)
place("Package_SON", "WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm", "U303", "TRF37D73", XU3, 0.25, 0,
      {"1": "+3V3", "2": "TRF_IN", "3": "GND", "4": "GND", "5": "GND", "6": "GND", "7": "TRF_OUT", "8": "GND",
       "9": "GND"})
track("TRF_IN", W50, [("C308", "2"), ("U303", "2")], name="TRF_IN: C308 -> U303.2", z=50)
for pn in ("3", "4", "5", "6", "8"):
    x, y = pad("U303", pn)
    track("GND", 0.2, [(x, y), (XU3 + (0.3 if x > XU3 else -0.3), y)], ch=0)
for dy in (-0.45, 0.25, 0.95):
    via(XU3, dy, "GND", "gnd", 0.2, 0.4)
# VCC pin 1 -> C312 100 n + C311 1 n right above, +3V3 via pair at C312 (both 0.25 mm further left than before
# so that the 1210 47 uH of the bias tee fits right of them)
X_C312, X_C311 = XU3 - 1.2, XU3 - 0.26
two("C", "C312", "100n", X_C312, -1.6, "v", "GND", "+3V3")
two("C", "C311", "1n C0G", X_C311, -1.6, "v", "GND", "+3V3")
track("+3V3", 0.3, [("U303", "1"), ("C312", "@+3V3")], ch=0)
track("+3V3", W_PWR, [("C312", "@+3V3"), ("C311", "@+3V3")], ch=0)
for dy in (-0.5, 0.05):
    via(X_C312 - 0.66, -1.12 + dy, "+3V3", "supply")
track("+3V3", 0.4, [("C312", "@+3V3"), (X_C312 - 0.66, -1.62)], ch=0)
track("+3V3", 0.4, [("C312", "@+3V3"), (X_C312 - 0.66, -1.07)], ch=0)
for c_ in ("C311", "C312"):
    x, y = pad(c_, "@GND")
    gvia(x, y - 0.58)
    track("GND", W_GND, [(x, y), (x, y - 0.58)], ch=0)
# output bias tee (sim/bias_tee/RESULT.md), one straight chain perpendicular to the line, courtyards touching:
# FB301 BLM15HD102 with pad 1 centred ON the line (no stub) -> L302 47 uH 1210 (pad-wide link) with R382 1 k beside
# it -> C314 100 nF across the cold pad (GND via at its GND pad) -> +3V3 plane via pair beyond C314.
# (was: L301 120 nH + 47 uH 0806 on a 1008 land, cold end 100 n + 1 n beside the inductor)
two("L", "FB301", "BLM15HD102", X_L301, -0.485, "v", "TRF_BIAS", "TRF_OUT")
YL302 = -0.485 - 0.93 - 2.28
two("L1210", "L302", "47u LQH32CN", X_L301, YL302, "v", "+3V3", "TRF_BIAS")
two("R", "R382", "1k", X_L301 + 1.58 + 0.47, YL302, "v", "+3V3", "TRF_BIAS")
two("C", "C309", "1u", X_C309, 0.0, "h", "TRF_OUT", "PAD_IN")
for r_, n_ in (("FB301", "@TRF_OUT"), ("C309", "1"), ("C309", "2")):
    rfpad(r_, n_)
track("TRF_OUT", W50, [("U303", "7"), ("C309", "1")], name="TRF_OUT: U303.7 -> FB301 -> C309", z=50)
W_BT = 0.64                                     # bias-tee links as wide as the 0402 pads
track("TRF_BIAS", W_BT, [("FB301", "@TRF_BIAS"), ("L302", "@TRF_BIAS")], ch=0)
for net_, sgn in (("TRF_BIAS", 1), ("+3V3", -1)):  # R382 pads -> L302 pads, one 45-degree link each
    rx, ry = pad("R382", "@" + net_)
    lx, ly = pad("L302", "@" + net_)
    d_ = rx - (lx + 1.325 - 0.18)
    track(net_, 0.5, [(rx, ry), (rx - d_, ry + sgn * d_)], ch=0)
yl2 = pad("L302", "@+3V3")[1]
YC314 = YL302 - 2.28 - 0.46
X_C314 = X_L301 + 0.48
two("C", "C314", "100n", X_C314, YC314, "h", "+3V3", "GND")
cpx, cpy = pad("C314", "@+3V3")
track("+3V3", 0.56, [(cpx, cpy), (cpx, yl2)], ch=0)
gx_, gy_ = pad("C314", "@GND")
gvia(gx_ + 0.6, gy_)
track("GND", W_GND, [(gx_, gy_), (gx_ + 0.6, gy_)], ch=0)
VIA_Y = cpy - 0.31 - 0.1 - 0.225 - 0.05
for dx in (-0.3, 0.3):                           # plane via pair on the far side of C314
    via(cpx + dx, VIA_Y, "+3V3", "supply")
track("+3V3", 0.5, [(cpx - 0.3, VIA_Y), (cpx + 0.3, VIA_Y)], ch=0)
track("+3V3", 0.56, [(cpx, VIA_Y), (cpx, cpy)], ch=0)
# 12 dB pi pad
two("R", "R311", "82", X_R311, 0.48, "v", "PAD_IN", "GND")
two("R", "R312", "91", X_R312, 0.0, "h", "PAD_IN", "PH_LINE")
two("R", "R313", "82", X_R313, 0.48, "v", "PH_LINE", "GND")
for r_, n_ in (("R311", "@PAD_IN"), ("R312", "1"), ("R312", "2"), ("R313", "@PH_LINE")):
    rfpad(r_, n_)
track("PAD_IN", W50, [("C309", "2"), ("R312", "1")], name="PAD_IN: C309 -> R311 -> R312", z=50)
for r_ in ("R311", "R313"):
    x, y = pad(r_, "@GND")
    gvia(x - 0.31 - 0.1 - 0.225, y)
    track("GND", W_GND, [(x, y), (x - 0.31 - 0.1 - 0.225, y)], ch=0)
X_STEP = -1.6
track("PH_LINE", W50, [("R312", "2"), (X_STEP, 0.0)], name="PH_LINE launch: R312 -> R313 -> step", z=50)
track("PH_LINE", W_LIN, [(X_STEP, 0.0), (XT[0] + X_P3, 0.0)], name="PH_LINE launch: step -> D01.3", z=round(Z_LIN))
testpad("TP306", "+3V3", cpx - 1.5, VIA_Y, lx=-1.2, ly=0)
track("+3V3", W_PWR, [(cpx - 0.3, VIA_Y), (cpx - 1.5, VIA_Y)], ch=0)
testpad("TP307", "GND", XU3 - 1.0, -4.6, lx=0, ly=-0.85)
gvia(XU3 - 1.0, -3.6)
track("GND", W_PWR, [(XU3 - 1.0, -3.6), (XU3 - 1.0, -4.6)], ch=0)

# ============================================================================= strobe launch
XS = -4.4
YX = YL + 2.6
for s, nn, ref in ((-1, "PSTRB_A", "X2"), (+1, "PSTRB_K", "X3")):
    iface(ref, nn, XS, YX * s, 0.5, 0.6)
    rfpad(ref, "1")
    track(nn, W50, [(XS, YX * s), (XS, (YL + 0.5) * s), (XS + 0.5, YL * s), (XT[0] + X_P12 - PITCH / 2, YL * s)],
          name=f"{nn} feed: {ref} -> half section before tap 0", z=50, ch=0)
    text(nn, XS + 1.5, (YX + 0.55) * s, 0.4)

# ============================================================================= tap cells
CUT = []
DX_TAP = 0.8                                        # comparator tap run, west of the summing jumper (B.Cu)
for n, x in enumerate(XT):
    na, nk, sm = f"TAP{n}_A", f"TAP{n}_K", f"TAP{n}_IN"
    place("Package_TO_SOT_SMD", "SOT-323_SC-70", f"D{n + 1:02d}", "BAT15-04W", x, 0.0, 0,
          {"1": na, "2": nk, "3": "PH_LINE"})
    two("C", f"CA{n:02d}", "0.47p C0G", x + X_P12, -(YL - 0.48), "v", "PSTRB_A", na)
    two("C", f"CK{n:02d}", "0.47p C0G", x + X_P12, +(YL - 0.48), "v", nk, "PSTRB_K")
    two("R", f"RSA{n:02d}", "1k", x + X_R1K, -YL, "v", sm, na)
    two("R", f"RNA{n:02d}", "2.2k", x + X_R22K, -YL, "v", "VTAP_N", na)
    two("R", f"RSK{n:02d}", "1k", x + X_R1K, +YL, "v", nk, sm)
    two("R", f"RNK{n:02d}", "2.2k", x + X_R22K, +YL, "v", nk, "VTAP_P")
    for s, node in ((-1, na), (+1, nk)):
        # pin 1 / pin 2 -> cap node pad (straight), cap node pad -> both resistor inner pads
        track(node, W_NODE, [(x + X_P12, 0.65 * s), (x + X_P12, YNODE * s)], ch=0, name=f"hold node {n} {s}")
        for xr in (X_R1K, X_R22K):
            track(node, W_NODE, [(x + X_P12, YNODE * s), (x + xr, YNODE * s), (x + xr, (YL - 0.48) * s)], ch=0.2,
                  name=f"hold node {n} {s}")
        rail = "VTAP_N" if s < 0 else "VTAP_P"
        via(x + X_R22K, Y_RV * s, rail, "supply")
        track(rail, 0.3, [(x + X_R22K, (YL + 0.48) * s), (x + X_R22K, Y_RV * s)], ch=0)
        CUT.append(rect_pts(x - 1.35, 0.55 * s, x + 0.45, (YL - 0.4) * s))
    # summing node: K-side 1 k -> via -> B.Cu -> via at the A side
    via(x + X_R1K, Y_RV, sm, "signal")
    via(x + X_R1K, -Y_RV, sm, "signal")
    track(sm, W_SIG, [(x + X_R1K, YL + 0.48), (x + X_R1K, Y_RV)], ch=0)
    track(sm, W_SIG, [(x + X_R1K, Y_RV), (x + X_R1K, -Y_RV)], layer=pcbnew.B_Cu, ch=0)
    track(sm, W_SIG, [(x + X_R1K, -(YL + 0.48)), (x + X_R1K, -Y_RV)], ch=0)
    # comparator tap from the MIDPOINT of the B.Cu jumper (equal path from the A-side and the K-side 1 k):
    # B.Cu branch at 45 degrees to a parallel run DX_TAP west of the jumper, up to its own via in the via row
    track(sm, W_SIG, [(x + X_R1K, 0.0), (x + X_R1K - DX_TAP, -DX_TAP), (x + X_R1K - DX_TAP, -Y_RV)],
          layer=pcbnew.B_Cu, ch=0)
    via(x + X_R1K - DX_TAP, -Y_RV, sm, "signal")
    rfpad(f"D{n + 1:02d}", "3")
    rfpad(f"CA{n:02d}", "@PSTRB_A")
    rfpad(f"CK{n:02d}", "@PSTRB_K")
    # PH_LINE meander to the next tap (S shape, every cell identical)
    if n < NT - 1:
        track("PH_LINE", W_LIN, [(x + px, py) for px, py in cell_path(Y_M)], name=f"PH_LINE cell {n}",
              z=round(Z_LIN), ch=CH_M)
        for s, nn in ((-1, "PSTRB_A"), (+1, "PSTRB_K")):
            track(nn, W_STR, [(x + X_P12 - PITCH / 2, YL * s), (x + X_P12 + PITCH / 2, YL * s)],
                  name=f"{nn} section {n}", z=73)
    else:
        for s, nn in ((-1, "PSTRB_A"), (+1, "PSTRB_K")):
            track(nn, W_STR, [(x + X_P12 - PITCH / 2, YL * s), (x + X_P12 + PITCH / 2, YL * s)],
                  name=f"{nn} section {n}", z=73)

# far end: terminations
XE = X15 + X_P12 + PITCH / 2
for s, nn, ref in ((-1, "PSTRB_A", "R402"), (+1, "PSTRB_K", "R403")):
    two("R", ref, "49.9", XE + 0.6 + 0.48, YL * s, "h", nn, "GND")
    rfpad(ref, "1")
    track(nn, W50, [(XE, YL * s), (ref, "1")], name=f"{nn} end: -> {ref} 49.9 R", z=50)
    xg, yg = pad(ref, "2")
    gvia(xg + 0.6, yg)
    track("GND", W_GND, [(xg, yg), (xg + 0.6, yg)], ch=0)
two("R", "R401", "49.9", X15 + X_P3 + 1.6 + 0.48, 0.0, "h", "PH_LINE", "GND")
rfpad("R401", "1")
track("PH_LINE", W_LIN, [(X15 + X_P3, 0.0), (X15 + X_P3 + 0.8, 0.0)], name="PH_LINE end: D16.3 -> step", z=round(Z_LIN))
track("PH_LINE", W50, [(X15 + X_P3 + 0.8, 0.0), ("R401", "1")], name="PH_LINE end: step -> R401 49.9 R", z=50)
xg, yg = pad("R401", "2")
gvia(xg + 0.6, yg)
track("GND", W_GND, [(xg, yg), (xg + 0.6, yg)], ch=0)

# VTAP rails = In2 strips; decoupling 2 x 100 n per rail at both ends; test pads at the far end
for s, rail, tp in ((-1, "VTAP_N", "TP402"), (+1, "VTAP_P", "TP403")):
    # far end: horizontal capacitor beyond the last tap
    ref = f"C{'N' if s < 0 else 'P'}15"
    two("C", ref, "100n", X15 + 2.6, (Y_RV + 0.75) * s, "h", "GND", rail)
    for nn_ in (rail, "GND"):
        xr_, yr_ = pad(ref, "@" + nn_)
        via(xr_, yr_ + 0.6 * s, nn_, "supply" if nn_ != "GND" else "gnd")
        track(nn_, 0.4, [(xr_, yr_), (xr_, yr_ + 0.6 * s)], ch=0)
    # near end: vertical capacitor (mirror image on both rails), clear of the tap-0 comparator via and route
    ref = f"C{'N' if s < 0 else 'P'}00"
    two("C", ref, "100n", XT[0] - 3.5, (Y_RV + 1.0) * s, "v", *((rail, "GND") if s > 0 else ("GND", rail)))   # GND pad outward
    for nn_, d in ((rail, -0.6), ("GND", +0.6)):
        xr_, yr_ = pad(ref, "@" + nn_)
        via(xr_, yr_ + d * s, nn_, "supply" if nn_ != "GND" else "gnd")
        track(nn_, 0.4, [(xr_, yr_), (xr_, yr_ + d * s)], ch=0)
    testpad(tp, rail, X15 + 4.2, (Y_RV + 0.75) * s, lx=0, ly=0.85 * s)
    track(rail, W_PWR, [pad(f"C{'N' if s < 0 else 'P'}15", "@" + rail), (X15 + 4.2, (Y_RV + 0.75) * s)], ch=0)

# ============================================================================= comparators COS3502 (SOIC-8)
YC = -(YL + 7.0)
SUM_LEN = []
VTH_Y = YC + 1.175
for k in range(NT // 2):
    n0, n1 = 2 * k, 2 * k + 1
    # pins 1 and 3 mirror-symmetric about the middle of the two tap vias: both channels get the same route length
    xta, xtb = XT[n0] + X_R1K - DX_TAP, XT[n1] + X_R1K - DX_TAP
    xc = (xta + xtb) / 2 + 0.635
    ref = f"U{11 + k}"
    place("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm", ref, "COS3502", xc, YC, None,
          {"1": f"TAP{n0}_IN", "2": "VTH", "3": f"TAP{n1}_IN", "4": "VTH", "5": "GND", "6": f"TAP{n1}",
           "7": f"TAP{n0}", "8": "+3V3"},
          cond=lambda pp: pp["1"][1] > 1.0 and pp["1"][0] < pp["4"][0])
    x1, y1 = pad(ref, "1")
    x3, y3 = pad(ref, "3")
    yj = y3 + 0.975 + 0.2
    assert abs((x1 - xta) - (xtb - x3)) < 1e-6 and x1 > xta
    ra = [(xta, -Y_RV), (xta, yj + (x1 - xta)), (x1, yj), (x1, y1)]
    rb = [(xtb, -Y_RV), (xtb, yj + (xtb - x3)), (x3, yj), (x3, y3)]
    track(f"TAP{n0}_IN", W_SIG, ra, ch=0)
    track(f"TAP{n1}_IN", W_SIG, rb, ch=0)
    SUM_LEN.append((n0, plen(ra), n1, plen(rb)))
    for pin in ("2", "4"):
        px, py = pad(ref, pin)
        via(px, VTH_Y, "VTH", "signal")
        track("VTH", W_SIG, [(px, py), (px, VTH_Y)], ch=0)
    p8, p5 = pad(ref, "8"), pad(ref, "5")
    cref = f"C{30 + k}"
    two("C", cref, "100n", p8[0], p8[1] - 0.975 - 0.1 - 0.76, "v", "GND", "+3V3")
    track("+3V3", 0.6, [p8, (cref, "@+3V3")], ch=0)
    yv = pad(cref, "@+3V3")[1]
    for dx in (-0.635, 0.635):
        via(p8[0] + dx, yv, "+3V3", "supply")
        track("+3V3", 0.4, [(p8[0], yv), (p8[0] + dx, yv)], ch=0)
    xg, yg = pad(cref, "@GND")
    gvia(xg, yg - 0.58)
    track("GND", W_GND, [(xg, yg), (xg, yg - 0.58)], ch=0)
    gvia(p5[0], p5[1] - 0.975 - 0.1 - 0.225)
    track("GND", 0.6, [p5, (p5[0], p5[1] - 0.975 - 0.1 - 0.225)], ch=0)
    for n, pin in ((n0, "7"), (n1, "6")):
        px, py = pad(ref, pin)
        testpad(f"TP{500 + n}", f"TAP{n}", px, py - 3.0, label=f"T{n}", ly=-0.85, size=0.3)
        track(f"TAP{n}", W_SIG, [(px, py), (px, py - 3.0)], ch=0)
x_last4 = pad(f"U{11 + NT // 2 - 1}", "4")[0]
track("VTH", 0.3, [(-3.0, VTH_Y), (x_last4, VTH_Y)], layer=pcbnew.B_Cu, ch=0)
via(-3.0, VTH_Y, "VTH", "signal")
two("R", "R404", "1k", -4.3, VTH_Y, "h", "VTAP_TH", "VTH")
two("C", "C404", "100n", -3.82, VTH_Y + 1.4, "v", "VTH", "GND")
track("VTH", W_SIG, [("R404", "2"), (-3.0, VTH_Y)], ch=0)
track("VTH", W_SIG, [("R404", "2"), ("C404", "@VTH")], ch=0)
xg, yg = pad("C404", "@GND")
gvia(xg, yg + 0.58)
track("GND", W_GND, [(xg, yg), (xg, yg + 0.58)], ch=0)
testpad("TP401", "VTAP_TH", -5.9, VTH_Y, ly=-0.85)
track("VTAP_TH", W_SIG, [("R404", "1"), (-5.9, VTH_Y)], ch=0)

# ============================================================================= outline
BY0 = YC - 2.475 - 0.975 - 3.0 - 1.4
BY1 = max(YX + 0.8, YS + 2.825 + 0.675 + 0.35)
for a, c in zip(rect_pts(BX0, BY0, BX1, BY1), rect_pts(BX0, BY0, BX1, BY1)[1:] + [(BX0, BY0)]):
    line(*a, *c)

# ============================================================================= silkscreen
text("BUF_OUT_T", BX0 + 2.0, -1.3, 0.4)
text("EXT_CLK", BX0 + 5.6, YS + 1.2, 0.4)
text("PHASE_TRIGGER 4L JLC04161H-7628", BX0 + 7.0, BY0 + 1.0, 0.5)
text("TMUX136", XU1 - 0.9, 4.3, 0.3)
text("TLV3801", XU2, 2.9, 0.3)
text("TRF37D73", XU3, 1.9, 0.3)
text("12 dB", X_R312, 1.6, 0.3)
text("LVDS2", X_R309 - 1.137, YU4 - 2.0, 0.3)
text(f"PH_LINE {W_LIN:.2f} mm, {TD_LIN:.0f} ps/tap", 20.0, YL + 2.2, 0.4)
text(f"PSTRB_A/K {W_STR:.2f} mm, pitch {PITCH:.3f} mm", 45.0, YL + 2.2, 0.4)
for n, x in enumerate(XT):
    text(str(n), x + 1.85, YL + 1.0, 0.3)

# ============================================================================= zones
IN = 0.25
outline = rect_pts(BX0 + IN, BY0 + IN, BX1 - IN, BY1 - IN)
zone("GND", [pcbnew.In1_Cu], outline, clearance=0.2)
zone("+3V3", [pcbnew.In2_Cu], outline, clearance=0.3, prio=0)
zone("+2V5", [pcbnew.In2_Cu], rect_pts(BX0 + IN, -3.6, XU2 + 1.0, BY1 - IN), clearance=0.3, prio=1)
XV0, XV1 = XT[0] - 4.0, X15 + 4.6
zone("VTAP_N", [pcbnew.In2_Cu], rect_pts(XV0, -(Y_RV + 1.4), XV1, -0.15), clearance=0.3, prio=1)
zone("VTAP_P", [pcbnew.In2_Cu], rect_pts(XV0, 0.15, XV1, Y_RV + 1.4), clearance=0.3, prio=1)
zone("GND", [pcbnew.B_Cu], outline, clearance=0.25, prio=0)
zone("-2V5", [pcbnew.B_Cu], rect_pts(XU1 + 0.9, -3.6, XU2 + 1.0, 3.8), clearance=0.25, prio=1)
zone("VSW_GND", [pcbnew.B_Cu], rect_pts(XU1 - 1.2, -3.4, XU1 + 0.7, 1.8), clearance=0.25, prio=1)
zone("VSW_GND", [pcbnew.F_Cu], rect_pts(XU1 - 1.15, 0.95, XU1 + 2.95, 2.2), clearance=0.15, prio=2)
zone("GND", [pcbnew.F_Cu], outline, clearance=0.2, prio=0)
for c in CUT:                                         # hold nodes: no In1 ground below (In2 VTAP strip instead)
    zone(None, [pcbnew.In1_Cu], c, rule=True)
xj, yj_ = pad("J301", "1")
zone(None, [pcbnew.In1_Cu], rect_pts(BX0 + IN, yj_ - 0.95, xj + 1.9, yj_ + 0.95), rule=True)   # SMA pin
# no top pour between the strobe lines of the delay line (dense meander) and within 2 w of the strobe lines
zone(None, [pcbnew.F_Cu], rect_pts(XT[0] + X_P12 - PITCH / 2 - 0.1, -(YL + W_STR / 2 + 2 * W_STR),
                                    XE + 0.1, YL + W_STR / 2 + 2 * W_STR), rule=True)
# RF pour keep-outs: octagon around every RF segment at 2 w from the trace edge, rectangle around RF pads
for nm, r in ROUTES.items():
    if r["z"] is None:
        continue
    w = r["width"]
    K = 2 * w + w / 2
    e = K * math.tan(math.pi / 8)
    for x0, y0, x1, y1 in r["segs"]:
        L = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        nx, ny = -uy, ux
        pts = [(x0 - ux * K + nx * e, y0 - uy * K + ny * e), (x0 - ux * e + nx * K, y0 - uy * e + ny * K),
               (x1 + ux * e + nx * K, y1 + uy * e + ny * K), (x1 + ux * K + nx * e, y1 + uy * K + ny * e),
               (x1 + ux * K - nx * e, y1 + uy * K - ny * e), (x1 + ux * e - nx * K, y1 + uy * e - ny * K),
               (x0 - ux * e - nx * K, y0 - uy * e - ny * K), (x0 - ux * K - nx * e, y0 - uy * K - ny * e)]
        zone(None, [pcbnew.F_Cu], pts, rule=True)
for ref, num in RFPADS:
    for p_ in FPS[ref].Pads():
        if p_.GetNumber() == num or (num[0] == "@" and p_.GetNetname() == num[1:]):
            if not p_.IsOnLayer(pcbnew.F_Cu):
                continue
            bb = p_.GetBoundingBox()
            x0, y0 = loc(pcbnew.VECTOR2I(bb.GetX(), bb.GetY()))
            x1, y1 = x0 + pcbnew.ToMM(bb.GetWidth()), y0 + pcbnew.ToMM(bb.GetHeight())
            g = 2 * W50
            zone(None, [pcbnew.F_Cu], rect_pts(x0 - g, y0 - g, x1 + g, y1 + g), rule=True)
            break

pcbnew.ZONE_FILLER(b).Fill(b.Zones())

# ============================================================================= reports


def route_len(nm):
    return sum(math.hypot(x1 - x0, y1 - y0) for x0, y0, x1, y1 in ROUTES[nm]["segs"])


print("Stack-up JLC04161H-7628: F.Cu 35 um / 7628 0.2104 mm er 4.4 / In1 GND / core 1.065 mm er 4.6 / In2 power / "
      "7628 0.2104 mm / B.Cu; mask er 3.8, 15 um over trace, 30 um over laminate")
print(f"{'line':34s} {'w mm':>6s} {'Z0 R':>6s} {'eps_eff':>7s} {'ps/mm':>6s}")
for lab, w in (("50 R (all 50 R nets)", W50), ("PSTRB_A/K sections (73 R target)", W_STR),
               (f"PH_LINE sections ({z_t:.1f} R target)", W_LIN)):
    z_, e_ = microstrip(w)
    print(f"{lab:34s} {w:6.2f} {z_:6.1f} {e_:7.3f} {ps_mm(w):6.3f}")
print(f"  exact widths: 50 R {width_for(50):.3f} mm, 73 R {width_for(73):.3f} mm, PH_LINE {W_LIN_EXACT:.3f} mm; "
      f"50 R without mask {microstrip(W50, mask=False)[0]:.1f} R")
zms0 = microstrip(W50, t=1e-6, mask=False)[0]
lo, hi = 0.05, 2.0
for _ in range(50):
    m = (lo + hi) / 2
    lo, hi = (m, hi) if cpwg(W50, m)[0] < zms0 else (lo, m)
print(f"coplanar check (Wadell CPWG, t=0, no mask): side ground lowers Z below the microstrip value ({zms0:.1f} R) "
      f"only for gaps < {(lo + hi) / 2:.2f} mm; pour gap used 2 w = {GAP_RF:.2f} mm (CPWG there "
      f"{cpwg(W50, GAP_RF)[0]:.1f} R) -> microstrip-dominated, no correction")

print("\nloaded lines (per tap)  intended -> design")
la_ = route_len("PSTRB_A section 3")
ll_ = route_len("PH_LINE cell 3")
for lab, w, z0, cl, tdu, L, tdt in (("PSTRB_A/K", W_STR, Z_STR, CL_STR, TDU_STR, la_, TD_STR),
                                    ("PH_LINE", W_LIN, Z_LIN, CL_LIN, TDU_LIN, ll_, TD_LIN)):
    td, zl = loaded(L * ps_mm(w), z0, cl)
    print(f"  {lab:10s} w {w:.2f} mm, Z0 unloaded {z0:.1f} R, load {cl:.3f} pF, section {L:.3f} mm "
          f"(needed {tdu / ps_mm(w):.3f}), unloaded {L * ps_mm(w):.2f} ps, loaded {td:.2f} ps "
          f"(target {tdt:.1f}), loaded Z {zl:.1f} R")
_jb = Y_RV + DX_TAP * math.sqrt(2) + (Y_RV - DX_TAP)
print(f"summing node (per tap): 1 k pad -> via {Y_RV - YL - 0.48:.3f} mm F.Cu on both sides, via -> jumper midpoint "
      f"{Y_RV:.3f} mm B.Cu on both sides (A = K), midpoint -> tap via {DX_TAP * math.sqrt(2) + (Y_RV - DX_TAP):.3f} mm B.Cu, "
      f"tap via -> comparator pin F.Cu: " + ", ".join(sorted({f"{la:.3f} / {lb:.3f}" for _, la, _, lb in SUM_LEN}))
      + " mm (channel A / B)")
assert all(abs(la - lb) < 1e-6 for _, la, _, lb in SUM_LEN)
print(f"  pitch {PITCH:.3f} mm, meander half-height Y {Y_M:.3f} mm, legs x = {X_P3:.2f} / {XU:.3f} / {XD:.3f} "
      f"(gaps {XU - X_P3 - W_LIN:.3f} / {XD - XU - W_LIN:.3f} mm), strobe |y| {YL:.2f} mm")
print(f"{'interval':>8s} {'A mm':>7s} {'K mm':>7s} {'A ps':>6s} {'K ps':>6s} {'line mm':>8s} {'line ps':>8s} {'eff ps':>7s}")
res = []
for n in range(NT - 1):
    la, lk, ll = route_len(f"PSTRB_A section {n}"), route_len(f"PSTRB_K section {n}"), route_len(f"PH_LINE cell {n}")
    ta, tk, tl = (loaded(la * ps_mm(W_STR), Z_STR, CL_STR)[0], loaded(lk * ps_mm(W_STR), Z_STR, CL_STR)[0],
                  loaded(ll * ps_mm(W_LIN), Z_LIN, CL_LIN)[0])
    res.append((ta, tk, tl))
    if n in (0, 1, 7, 14):
        print(f"{n:3d}-{n + 1:<4d} {la:7.3f} {lk:7.3f} {ta:6.2f} {tk:6.2f} {ll:8.3f} {tl:8.2f} {tl - ta:7.2f}")
spread = [max(r[i] for r in res) - min(r[i] for r in res) for i in range(3)]
print(f"  15 intervals: spread A {spread[0]:.4f} / K {spread[1]:.4f} / line {spread[2]:.4f} ps (all cells identical)")

print(f"\n{'RF segment':52s} {'net':10s} {'w':>5s} {'Z int':>5s} {'Z0':>5s} {'len mm':>7s} {'ps':>6s}")
for nm, r in ROUTES.items():
    if r["z"] is None:
        continue
    if ("section" in nm and not nm.endswith((" 0", " 15"))) or ("cell" in nm and not nm.endswith((" 0", " 14"))):
        continue
    L = route_len(nm)
    print(f"{nm:52s} {r['net']:10s} {r['width']:5.2f} {r['z']:5d} {microstrip(r['width'])[0]:5.1f} {L:7.3f} "
          f"{L * ps_mm(r['width']):6.1f}")
print("  (sections 1..14 / cells 1..13 identical to the ones listed)")

print("\npad discontinuities (excess C vs the line the pad replaces):")
for lab, wl, wp, lp in (("0402 in-line on 50 R (C308, C309, R312)", W50, 0.62, 0.56),
                        ("0402 shunt/T pad on 50 R (R301, R307, R309, R310, R311, R313, FB301)", W50, 0.62, 0.56),
                        ("SOT-323 pin 3 on PH_LINE (in the tap load)", W_LIN, 0.45, 0.70),
                        ("0402 hold-cap pad on the strobe line (in the tap load)", W_STR, 0.56, 0.62),
                        ("WSON / UQFN pins (narrower than the line)", W50, 0.25, 0.5)):
    dc = (c_per_mm(wp) - c_per_mm(wl)) * lp
    print(f"  {lab:70s} {dc * 1e3:+6.1f} fF")
zs, es = microstrip(1.27, h=0.2104 + 0.0152 + 1.065)
print(f"  SMA centre pin 1.27 mm: In1 cut out below -> referenced to In2 at 1.29 mm: {zs:.0f} R over 1.8 mm "
      f"(vs {(c_per_mm(1.27) - c_per_mm(W50)) * 1.8 * 1e3:.0f} fF excess without the cut-out)")
print("vias:", N_VIA, "(no stitching vias)")

# --- checks
bad = []
for nm, pts in POLYS:
    for a, c, d in zip(pts, pts[1:], pts[2:]):
        v1, v2 = (c[0] - a[0], c[1] - a[1]), (d[0] - c[0], d[1] - c[1])
        ang = math.degrees(math.acos(max(-1, min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / math.hypot(*v1) / math.hypot(*v2)))))
        if ang > 45.5:
            bad.append(f"{nm} at ({c[0]:.2f}, {c[1]:.2f}): {ang:.0f} deg")
print("bend check (<= 45 deg per vertex, all chamfered polylines):", "OK" if not bad else f"{len(bad)}: {bad[:12]}")

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
IC_OV = []
for i, r1 in enumerate(refs):
    for r2 in refs[i + 1:]:
        a, c = boxes[r1], boxes[r2]
        ox = min(a[2], c[2]) - max(a[0], c[0])
        oy = min(a[3], c[3]) - max(a[1], c[1])
        if ox > 0.02 and oy > 0.02:
            if r1.startswith("U") or r2.startswith("U"):
                IC_OV.append(f"{r1}/{r2} {min(ox, oy):.2f}")
            else:
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
            if t.IsOnLayer(lay) and u.IsOnLayer(lay) and t.GetEffectiveShape(lay).Collide(u.GetEffectiveShape(lay), CLR):
                who = u.GetParent().GetReference() + "." + u.GetNumber() if isinstance(u, pcbnew.PAD) else u.GetNetname()
                errs.append(f"clearance {t.GetNetname()} / {who} on {b.GetLayerName(lay)} near "
                            f"{tuple(round(v, 2) for v in loc(t.GetPosition()))}")
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
print("courtyard / clearance check (0.1 mm):", "OK" if not errs else f"{len(errs)} problems")
print(f"  intentional: {len(IC_OV)} parts sit at IC pins inside the IC courtyard margin (pad gap >= 0.25 mm):",
      ", ".join(IC_OV))
for e in sorted(set(errs))[:40]:
    print("  ", e)
# RF pour clearance: sample the RF tracks, the filled F.Cu GND pour must stay >= 2 w from the trace edge
gz = [z for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname() == "GND" and z.IsOnLayer(pcbnew.F_Cu)][0]
fill = gz.GetFilledPolysList(pcbnew.F_Cu)
viol = []
for nm, r in ROUTES.items():
    if r["z"] is None:
        continue
    w = r["width"]
    for x0, y0, x1, y1 in r["segs"]:
        for i in range(11):
            u = i / 10
            if fill.Collide(P(x0 + u * (x1 - x0), y0 + u * (y1 - y0)), mm(2.5 * w - 0.02)):
                viol.append(nm)
                break
print("RF pour clearance (>= 2 w from trace edge):", "OK" if not viol else sorted(set(viol)))
b.BuildConnectivity()
cn = b.GetConnectivity()
print("unconnected items after fill:", cn.GetUnconnectedCount(False))
for code, ni in b.GetNetsByNetcode().items():
    try:
        rn = cn.GetRatsnestForNet(code)
        if rn and len(rn.GetEdges()):
            print("   unrouted net", ni.GetNetname(), len(rn.GetEdges()))
    except Exception as e_:
        pass
nonet = [f"{p.GetParent().GetReference()}.{p.GetNumber()}" for p in pads_ if not p.GetNetname()]
print("pads without net (U301.7 COM2 open on purpose):", nonet)
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
