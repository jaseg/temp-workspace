#!/usr/bin/env python3
"""Integrated scope-fe board, SIX layers (RULES rule 10, JLC06161H-3313), integration pass of 22 Nov 2026.

  L1 F.Cu  RF / analog + components        L2 In1  solid GND (block cut-outs kept)
  L3 In2   slow bias / control + GND pour   L4 In3  power: +3V3 background, rail islands (block zones)
  L5 In4   solid GND                        L6 B.Cu inter-block digital buses + bottom components

Run:  cd design/lowcost/layout/board && python3 gen_board.py [--nofinish]
Every inter-block route here is drawn with explicit coordinates derived from blocks/*/*.ifaces.json and the
merged copper (no auto-router).  Writes scope-fe.kicad_pcb, scope-fe.kicad_pro, routes.json.
The previous (phase-one, auto-routed) script is kept in git history only.
"""
import os, sys, json, math, re
os.environ["BL_STACKUP"] = "6L"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
import pcbnew
import boardlib as bl

W, H = 100.0, 57.0
POS = {"analog": (0.0, 1.0), "phase": (0.0, 22.5), "pstrobe": (9.5, 25.0), "fpga": (56.0, 0.5),
       "power": (74.0, 0.0), "mcuif": (27.0, 45.0)}
NATIVE6 = {"analog", "pstrobe", "fpga", "power", "mcuif"}          # phase is still a 4-layer file
OUT = os.path.join(HERE, "scope-fe.kicad_pcb")
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board6/int"
os.makedirs(SCR, exist_ok=True)
W_RF = 0.16                     # 50 R on L1 / L6 (boardlib.microstrip, 0.0994 mm 3313)
W_BUS = 0.11                    # L6 bus tracks (0.11 / 0.11 at 0.22 pitch)

FAST_RX = re.compile(r"^/(TAP\d+|COARSE|FPGA_CLK|MCU_CLK|SPI_\w+|ADC_TRIG|fpga_clock/JTAG_\w+|fpga_clock/DBG2|"
                     r"FPGA_DONE|FPGA_RECONFIG|I2C_\w+|S_STROBE_\w|PH_STROBE_\w|USB_D\w)$")

m = bl.new_master(W, H)
B = m.b
for fp in B.GetFootprints():
    if fp.GetReference().startswith("H"):
        fp.SetBoardOnly(True)
        fp.Value().SetVisible(False)
        fp.Reference().SetVisible(False)
for k, (x, y) in POS.items():
    bl.merge(B, f"blocks/{k}/{k}.kicad_pcb", x, y, layer_map=None if k in NATIVE6 else bl.LAYER_MAP_4TO6)


def loc(v):
    return round(pcbnew.ToMM(v.x) - bl.ORG[0], 4), round(pcbnew.ToMM(v.y) - bl.ORG[1], 4)


def near(a, b, tol=0.02):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def zbox(z):
    bb = z.GetBoundingBox()
    return tuple(round(v, 2) for v in (pcbnew.ToMM(bb.GetX()) - bl.ORG[0], pcbnew.ToMM(bb.GetY()) - bl.ORG[1],
                                      pcbnew.ToMM(bb.GetRight()) - bl.ORG[0], pcbnew.ToMM(bb.GetBottom()) - bl.ORG[1]))


def segs(net, layer=None):
    return [t for t in B.GetTracks() if not isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == net and
            (layer is None or t.GetLayerName() == layer)]


def vias(net):
    return [t for t in B.GetTracks() if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == net]


def seg_at(net, p, layer=None):
    """segments of net with an end at p -> [(track, this_end, other_end)]"""
    out = []
    for t in segs(net, layer):
        a, b = loc(t.GetStart()), loc(t.GetEnd())
        if near(a, p):
            out.append((t, a, b))
        elif near(b, p):
            out.append((t, b, a))
    return out


def kill_via(net, p):
    for v in vias(net):
        if near(loc(v.GetPosition()), p):
            B.Remove(v)
            return True
    return False


# ---------------------------------------------------------------- block zones -> board planes
x0p, y0p = POS["pstrobe"]
L2_CUTS = []
for z in list(B.Zones()):
    if z.GetIsRuleArea():
        b_ = zbox(z)
        # review (kept): the phase block's all-layer north_cut keep-out (the pstrobe rectangle) must not survive
        if z.IsOnLayer(pcbnew.In1_Cu) and z.IsOnLayer(pcbnew.F_Cu) and abs(b_[0] - x0p) < 0.3 and \
                abs(b_[1] - y0p) < 0.6 and (b_[2] - b_[0]) > 12:
            B.Remove(z)
            continue
        if z.IsOnLayer(pcbnew.In1_Cu):
            L2_CUTS.append(z)
        continue
    if z.GetNetname() == "GND":
        B.Remove(z)                                # replaced by board-wide GND planes / pours
    elif z.GetNetname() == "+3V3" and z.IsOnLayer(pcbnew.In3_Cu):
        B.Remove(z)                                # the L4 background plane
    elif z.IsOnLayer(pcbnew.In3_Cu):
        z.SetAssignedPriority(5)                   # block rail islands (+1V2, VTAP_P / VTAP_N strips)
for t in list(B.GetTracks()):                      # fpga +1V2 L4 track over U501 GND vias (old short)
    if not isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == "+1V2" and t.GetLayer() == pcbnew.In3_Cu:
        B.Remove(t)
for z in L2_CUTS:                                  # L3 cleared under every L2 cut-out (node windows, pad cuts)
    ol = z.Outline()
    pts = [loc(ol.CVertex(i)) for i in range(ol.COutline(0).PointCount())]
    if len(pts) >= 3:
        m.keepout(pts, layers=("In2.Cu",), tracks=True, vias=False)

LOG = []          # (net, layer(s), lane / corridor, length)
RF = {}


def T(net, w, pts, layer, lane, ch=0.1):
    q = m.track(net, w, pts, layer, ch=ch)
    LOG.append((net, layer, lane, round(bl.plen(q), 3)))
    return q


# ---------------------------------------------------------------- phase: VTH rail B.Cu -> L3 (static threshold)
# the rail segments between its end vias move to In2 (L3); the short B pieces into R380 / R381 stay on B
for net in ("/trigger_phase/VTH1", "/trigger_phase/VTH2"):
    vx = sorted(loc(v.GetPosition())[0] for v in vias(net))
    for t in segs(net, "B.Cu"):
        a, b = loc(t.GetStart()), loc(t.GetEnd())
        if abs(a[1] - b[1]) > 0.02 or abs(a[0] - b[0]) < 3:
            continue
        xa, xb = sorted((a[0], b[0]))
        inner = [x for x in vx if xa - 0.02 <= x <= xb + 0.02]
        lo, hi = min(inner), max(inner)
        y = a[1]
        B.Remove(t)
        m.track(net, 0.3, [(lo, y), (hi, y)], "In2.Cu")
        for p, q in ((xa, lo), (hi, xb)):
            if q - p > 0.02:
                m.track(net, 0.3, [(p, y), (q, y)], "B.Cu")
        LOG.append((net, "In2.Cu", "VTH rail moved B -> L3 (phase)", round(hi - lo, 3)))

# ---------------------------------------------------------------- L1: S_STROBE pair (analog E edge is 1.0 mm below fpga W)
# fpga S_STROBE_P ends at (56, 9.865), the analog P interface is (56, 10.865) = where fpga's N ends: P jogs 1 mm
# south inside the fpga margin; N's L6 hop is extended 1 mm south so its up-via meets the analog N at y 11.865
ip = [i for i in json.load(open("blocks/fpga/fpga.ifaces.json"))["ifaces"] if i["net"] == "/S_STROBE_P"][0]
ia = {i["net"]: i for i in json.load(open("blocks/analog/analog.ifaces.json"))["ifaces"]}
fP = (ip["x"] + 56.0, ip["y"] + 0.5)
aP = (ia["/S_STROBE_P"]["x"] + 0.0, ia["/S_STROBE_P"]["y"] + 1.0)
aN = (ia["/S_STROBE_N"]["x"] + 0.0, ia["/S_STROBE_N"]["y"] + 1.0)
NOT_PLACED = []
# the fpga block now ends both strobes on the analog E rows (gen_fpga.py, 22 Nov): the stubs abut, nothing to draw
assert abs(aP[1] - fP[1]) < 0.01, (aP, fP)
RF["/S_STROBE_P"] = RF["/S_STROBE_N"] = W_RF

# ---------------------------------------------------------------- L1: BUF_OUT_T analog S (15.75) -> phase N (8.79), y 22.5
a_end, p_end = (15.75, 22.5), (8.79, 22.5)
YB = 22.35                      # BUF_OUT_T run; the PH_STROBE pair passes south of it (y 22.85 / 23.21)
for t, e, o in seg_at("/BUF_OUT_T", a_end, "F.Cu"):
    B.Remove(t); a_from = o
for t, e, o in seg_at("/BUF_OUT_T", p_end, "F.Cu"):
    t.SetStart(m.P(p_end[0], YB + 0.6)); t.SetEnd(m.P(*o))
T("/BUF_OUT_T", W_RF, [a_from, (a_end[0], YB - 0.6), (a_end[0] - 0.6, YB), (p_end[0] + 0.6, YB),
                       (p_end[0], YB + 0.6)], "F.Cu", "analog S -> phase N along y 22.35 (L1)")

# ---------------------------------------------------------------- L1: PH_STROBE pair fpga W -> pstrobe N inputs
# fpga W exits P (56, 21.85) north / N south (pins swapped 22 Nov); west along the exit rows to x 25, 45-degree step
# down to y 22.85 / 23.21 (south of BUF_OUT_T, north of the phase strip parts), west, south into (10.00 / 10.60, 25.00).
# N is the inner line of both bends: two equal 45-degree bumps (south) on its upper run make it equal to P.
ipf = {i["net"]: (i["x"] + 56.0, i["y"] + 0.5) for i in json.load(open("blocks/fpga/fpga.ifaces.json"))["ifaces"]}
ips = {i["net"]: (i["x"] + 9.5, i["y"] + 25.0) for i in json.load(open("blocks/pstrobe/pstrobe.ifaces.json"))["ifaces"]}
sP, sN = ipf["/PH_STROBE_P"], ipf["/PH_STROBE_N"]
eP, eN = ips["/PH_STROBE_P"], ips["/PH_STROBE_N"]
YP2, YN2 = 22.85, 23.21
XP, XN = 24.0, 24.2
PP = [sP, (XP + (YP2 - sP[1]), sP[1]), (XP, YP2), (eP[0] + 0.3, YP2), (eP[0], YP2 + 0.3), eP]


def n_pts(h):
    q = [sN]
    for xb in (33.0, 29.5):                        # bumps (west-going): down at xb, flat 0.6, up
        q += [(xb, sN[1]), (xb - h, sN[1] + h), (xb - h - 0.6, sN[1] + h), (xb - 2 * h - 0.6, sN[1])]
    return q + [(XN + (YN2 - sN[1]), sN[1]), (XN, YN2), (eN[0] + 0.3, YN2), (eN[0], YN2 + 0.3), eN]


lo, hi = 0.0, 0.6
for _ in range(60):
    mid = (lo + hi) / 2
    lo, hi = (mid, hi) if bl.plen(n_pts(mid)) < bl.plen(PP) else (lo, mid)
T("/PH_STROBE_P", W_RF, PP, "F.Cu", "L1 fpga W y 21.85 -> y 22.85 -> pstrobe N (10.00, 25.00)", ch=0.0001)
T("/PH_STROBE_N", W_RF, n_pts(mid), "F.Cu", "L1 fpga W y 22.19 -> y 23.21 -> pstrobe N (10.60, 25.00), 2 bumps h %.3f" % mid,
  ch=0.0001)
RF["/PH_STROBE_P"] = RF["/PH_STROBE_N"] = W_RF
RF["/BUF_OUT_T"] = W_RF

# ---------------------------------------------------------------- L6: COARSE + TAP0..7 west staircase
# fpga stubs: vertical B pieces at x 58.0 + 0.5 k down to y 22.5 (k 0 COARSE, 1..8 TAP0..7); phase TAP ends: via at
# (x_k, 23.92) with a B stub north to y 22.5.  Lanes y = 20.90 + 0.22 k (COARSE northmost), above the comparator
# GND via row (y 23.07) and below the analog block's B parts; TAP k drops at its comparator via.
WEST = ["/COARSE"] + [f"/TAP{k}" for k in range(8)]
fpga_if = {i["net"]: (i["x"] + 56.0, i["y"] + 0.5) for i in json.load(open("blocks/fpga/fpga.ifaces.json"))["ifaces"]}
phase_if = {i["net"]: (i["x"], i["y"] + 22.5) for i in json.load(open("blocks/phase/phase.ifaces.json"))["ifaces"]}


def fpga_stub_top(net):
    """remove the fpga's vertical S-edge stub of net; return its upper end (where the fan-out diagonal ends)"""
    e = fpga_if[net]
    (t, _, o), = seg_at(net, e, "B.Cu")
    B.Remove(t)
    return o


def phase_stub_via(net):
    e = phase_if[net]
    (t, _, o), = seg_at(net, e, "B.Cu")
    B.Remove(t)
    return o


for k, net in enumerate(WEST):
    top = fpga_stub_top(net)
    y = round(20.90 + 0.22 * k, 3)
    if net == "/COARSE":
        # COARSE (U304, phase NW) arrives from the west north of TAP0, then passes under the analog block's
        # south row at y 22.45 (between the FB track y 21.9 and the VSW_GND row y 22.95) to the phase stub top
        pe = phase_if[net]
        T(net, W_BUS, [top, (top[0], y), (23.6, y), (23.6 - (22.45 - y), 22.45), (pe[0] + 0.3, 22.45),
                       (pe[0], 22.75)], "B.Cu", "L6 lane y 20.90 / y 22.45 (north of TAP0)", ch=0.1)
        # the phase stub started at (4.45, 22.5): shorten it to begin at 22.75
        for t, e, o in seg_at(net, pe, "B.Cu"):
            t.SetStart(m.P(pe[0], 22.75)); t.SetEnd(m.P(*o))
        continue
    v = phase_stub_via(net)
    T(net, W_BUS, [top, (top[0], y), (v[0], y), v], "B.Cu", f"L6 west staircase lane y {y:.2f}", ch=0.1)

# ---------------------------------------------------------------- L6: USB 90 R pair power S -> mcuif N
# power F stubs end at (82.6 / 83.0, 22.5): vias (DP 23.25 / DM 22.80, staggered), east on L6 north of the U311 output
# vias (y 23.92), south in the gap U311 | U312 (x 86.25 / 86.65, clear of the via column 85.69), a 45-degree jog
# under the comparators to tap-row lane 13 (x 89.03 / 89.43, between node window 13 (86.80-88.60) and the tap-14
# jumpers (89.92)), south to y 42.4, jog west, vias, F stubs into the mcuif interfaces (88.0 / 88.5, 45.0).
W_USB = 0.18
pDP, pDM = (82.6, 22.5), (83.0, 22.5)
T("/USB_DP", W_USB, [pDP, (82.6, 23.0)], "F.Cu", "power S stub to via (L1)")
T("/USB_DM", W_USB, [pDM, (83.0, 22.6), (83.4, 23.0)], "F.Cu", "power S stub to via (L1)")
m.via(82.6, 23.0, "/USB_DP"); m.via(83.4, 23.0, "/USB_DM")
# jog x 86.25 / 86.65 -> 89.0 / 89.4 at y 28.2-31.0 passes between the VTH via row (y 28.93, x 85.69) and the phase
# GND via (88.09, 31.41); lane 13 down to y 43.7, vias east of the C357 GND via (88.09, 43.59), F diagonals into
# the mcuif stubs
T("/USB_DP", W_USB, [(82.6, 23.0), (83.05, 23.45), (85.85, 23.45), (86.25, 23.85), (86.25, 28.2), (89.0, 30.95),
                     (89.0, 43.35), (88.0, 44.35)], "B.Cu", "L6 gap U311|U312, tap-row lane 13", ch=0.0001)
T("/USB_DM", W_USB, [(83.4, 23.0), (83.6, 22.8), (86.0, 22.8), (86.65, 23.45), (86.65, 27.8), (89.4, 30.55),
                     (89.4, 43.7), (89.6, 43.9)], "B.Cu", "L6 gap U311|U312, tap-row lane 13", ch=0.0001)
m.via(88.0, 44.35, "/USB_DP"); m.via(89.6, 43.9, "/USB_DM")
T("/USB_DP", W_USB, [(88.0, 44.35), (88.0, 45.0)], "F.Cu", "via to mcuif F stub")
T("/USB_DM", W_USB, [(89.6, 43.9), (88.5, 45.0)], "F.Cu", "via to mcuif F stub")
for gx, gy in ((82.0, 23.6), (83.9, 22.2), (90.35, 44.1)):          # ground vias beside the signal vias
    m.via(gx, gy, "GND")

# ---------------------------------------------------------------- slow lines whose analog end is a B column: L3 vias
# (VBIAS_A / VBIAS_K: via at y 20.3 on the B column; ADC_IN / ADC_REF_MID: their existing vias) - the B stubs
# below are removed so the L6 COARSE lane passes
for net, yv in (("/VBIAS_A", 16.3), ("/VBIAS_K", 20.3), ("/ADC_IN", None), ("/ADC_REF_MID", None)):
    e = (ia[net]["x"], ia[net]["y"] + 1.0)
    (t, _, o), = seg_at(net, e, "B.Cu")
    if yv is None:
        B.Remove(t)
    else:
        t.SetStart(m.P(*o)); t.SetEnd(m.P(e[0], yv))
        m.via(e[0], yv, net)

# phase TAP8..15 B stubs (y 23.92 -> 22.5) end on the fpga's middle-group stubs: removed, the comparator vias stay
BLOCK_EAST = ("U309's output vias (65.10 / 66.37, 23.92) and pin-5 GND via (67.64, 23.97) lie directly under the fpga "
              "MCU-group slots (65.0-69.5, 22.5); U310's cap vias (70.85, 23.61 / 24.25), (71.55, 23.07) under the TAP slots; "
              "the 18-track fan-in to a column needs >= 3 mm of free L6 height there")
BLOCK_MID = ("the only comparator gaps are 4.4 mm wide (U308|U309 x 59.0-63.4, U309|U310 x 68.0-72.5); gap 1 holds R380 / "
             "R381 / C354 / C355 + GND vias (59.04 / 64.66, 27.0), VTAP_TH B column x 61.93 and U309 cap vias (61.83, "
             "23.61 / 24.25), (62.53, 23.07); TAP8 / TAP9 (U309, x 65.1 / 66.37) sit between the gaps and need a slot "
             "order JTAG | MCU | TAP9 TAP8 | TAP15..10 that the fpga's F escapes cannot give without crossing the "
             "DONE / RECONFIG F runs (local y 18.1 / 18.5)")
for k in range(8, 16):
    net = f"/TAP{k}"
    phase_stub_via(net)
    NOT_PLACED.append((net, BLOCK_EAST))
for net in ("/fpga_clock/DBG2", "/fpga_clock/JTAG_TCK", "/fpga_clock/JTAG_TMS", "/fpga_clock/JTAG_TDI",
            "/fpga_clock/JTAG_TDO", "/MCU_CLK", "/SPI_CS", "/I2C_SDA", "/FPGA_DONE", "/SPI_MOSI", "/SPI_MISO",
            "/SPI_SCK", "/I2C_SCL", "/FPGA_RECONFIG", "/ADC_TRIG"):
    NOT_PLACED.append((net, BLOCK_MID))
bl.save_board(B, os.path.join(SCR, "routed.kicad_pcb"))
print("NOT PLACED:")
for r in NOT_PLACED:
    print("  ", r)
print("routes (net, layer, lane, length mm):")
for r in LOG:
    print("  ", r)
if "--nofinish" in sys.argv:
    sys.exit(0)

# ---------------------------------------------------------------- planes, stitching (minimal), silk, project
import board_finish as bf
for t in B.GetTracks():
    if t.GetClass() == "PCB_TRACK" and t.GetNetname() in RF and t.GetLayerName() == "F.Cu":
        m.rf_keepout([loc(t.GetStart()), loc(t.GetEnd())], pcbnew.ToMM(t.GetWidth()), layer="F.Cu")
bf.planes(B, m)
for z in B.Zones():
    if not z.GetIsRuleArea():
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
bf.silk(B, m)
pcbnew.ZONE_FILLER(B).Fill(B.Zones())
bl.save_board(B, OUT)
bf.write_pro(OUT.replace(".kicad_pcb", ".kicad_pro"), sorted(RF))


def rule10(B, step=0.25):
    polys = {}
    for z in B.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != "GND":
            continue
        for lid in (pcbnew.In1_Cu, pcbnew.In4_Cu):
            if z.IsOnLayer(lid):
                polys.setdefault(lid, []).append(z.GetFilledPolysList(lid))
    res = {"fast_on_L3": [], "samples": 0, "no_ref": []}
    for t in B.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            continue
        net = t.GetNetname()
        if not (FAST_RX.match(net) or net in RF):
            continue
        if t.GetLayer() == pcbnew.In2_Cu and net != "/FPGA_DONE":     # DONE: static config line, L3 allowed
            res["fast_on_L3"].append((net, loc(t.GetStart()), loc(t.GetEnd())))
            continue
        ref = {pcbnew.F_Cu: pcbnew.In1_Cu, pcbnew.B_Cu: pcbnew.In4_Cu}.get(t.GetLayer())
        if ref is None:
            continue
        a, b = t.GetStart(), t.GetEnd()
        k = max(1, int(pcbnew.ToMM(math.hypot(b.x - a.x, b.y - a.y)) / step))
        for i in range(k + 1):
            p = pcbnew.VECTOR2I(int(a.x + (b.x - a.x) * i / k), int(a.y + (b.y - a.y) * i / k))
            res["samples"] += 1
            if not any(pl.Contains(p) for pl in polys.get(ref, [])):
                res["no_ref"].append((net, t.GetLayerName(), loc(p)))
    res["L4"] = []
    for z in B.Zones():
        if z.GetIsRuleArea() or not z.IsOnLayer(pcbnew.In3_Cu):
            continue
        res["L4"].append((z.GetNetname(), z.GetFilledPolysList(pcbnew.In3_Cu).OutlineCount(), zbox(z)))
    return res


r10 = rule10(B)
print(f"rule 10: fast-net segments on L3: {len(r10['fast_on_L3'])}; L1/L6 samples {r10['samples']}, "
      f"without filled GND on L2/L5: {len(r10['no_ref'])}")
from collections import Counter
for k_, v_ in Counter((a_[0], a_[1]) for a_ in r10["no_ref"]).most_common(20):
    print("   ", k_, v_)
for z_ in r10["L4"]:
    print("   L4 zone", z_)
json.dump({"log": LOG, "not_placed": NOT_PLACED, "rf": RF, "rule10": {k: (v if k in ("samples", "L4") else len(v)) for k, v in r10.items()},
           "rule10_detail": r10}, open(os.path.join(HERE, "routes.json"), "w"), indent=1)
c = bl.check_board(OUT, rf_widths=RF, verbose=8)
json.dump({k: v for k, v in c.items() if k != "details"}, open(os.path.join(SCR, "check.json"), "w"), indent=1)
json.dump(c["details"], open(os.path.join(SCR, "check_details.json"), "w"), indent=1, default=str)
