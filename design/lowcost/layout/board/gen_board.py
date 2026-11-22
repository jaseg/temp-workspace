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
dy = aP[1] - fP[1]
NOT_PLACED = []
if abs(dy) > 0.01:
    # P cannot jog: the fpga's PH_STROBE pair turns down the W margin at x 56.9 / 57.26, y 10.26 / 10.62, i.e.
    # right under the 1 mm jog (needs a gen_fpga.py change: strobe pin row 1 mm lower) -> reported, not drawn
    NOT_PLACED.append(("/S_STROBE_P", "fpga W (56, %.3f) vs analog E (56, %.3f): 1 mm offset, jog blocked by the "
                       "fpga PH_STROBE pair at x 56.9-57.3" % (fP[1], aP[1])))
    # N: F stub + via at (56.4, fP_N) removed (its end would touch the analog P stub), L6 hop extended 1 mm south
    # to the analog N row, new via + F stub
    nN = (fP[0], aP[1])
    for t, e, o in seg_at("/S_STROBE_N", nN, "F.Cu"):
        B.Remove(t)
        vxy = o
    kill_via("/S_STROBE_N", vxy)
    for t, e, o in seg_at("/S_STROBE_N", vxy, "B.Cu"):
        t.SetEnd(m.P(vxy[0], aN[1])); t.SetStart(m.P(*o))
    m.via(vxy[0], aN[1], "/S_STROBE_N")
    T("/S_STROBE_N", W_RF, [(vxy[0], aN[1]), aN], "F.Cu", "fpga W edge (L6 hop extended 1 mm)")
RF["/S_STROBE_P"] = RF["/S_STROBE_N"] = W_RF

# ---------------------------------------------------------------- L1: BUF_OUT_T analog S (15.75) -> phase N (8.79), y 22.5
a_end, p_end = (15.75, 22.5), (8.79, 22.5)
for t, e, o in seg_at("/BUF_OUT_T", a_end, "F.Cu"):
    B.Remove(t); a_from = o
for t, e, o in seg_at("/BUF_OUT_T", p_end, "F.Cu"):
    t.SetStart(m.P(p_end[0], p_end[1] + 0.6)); t.SetEnd(m.P(*o))
T("/BUF_OUT_T", W_RF, [a_from, (a_end[0], a_end[1] - 0.6), (a_end[0] - 0.6, a_end[1]), (p_end[0] + 0.6, p_end[1]),
                       (p_end[0], p_end[1] + 0.6)], "F.Cu", "analog S -> phase N along y 22.5 (L1)")
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
for k in range(8, 16):
    net = f"/TAP{k}"
    phase_stub_via(net)
    NOT_PLACED.append((net, "east staircase: no L6 lane between the power block vias (y <= 22.33) and the comparator "
                       "via rows (y 23.07 / 23.61 / 23.97 / 24.25) east of x 67"))
for net in ("/fpga_clock/DBG2", "/fpga_clock/JTAG_TCK", "/fpga_clock/JTAG_TMS", "/fpga_clock/JTAG_TDI",
            "/fpga_clock/JTAG_TDO", "/MCU_CLK", "/SPI_CS", "/I2C_SDA", "/FPGA_DONE", "/SPI_MOSI", "/SPI_MISO",
            "/SPI_SCK", "/I2C_SCL", "/FPGA_RECONFIG", "/ADC_TRIG"):
    NOT_PLACED.append((net, "middle-group drop x 57.6-64.9 blocked on L6 by the R380 / R381 / VTAP_TH B network "
                       "(y 26.5-29.2) and vias (61.83, 23.61 / 24.25), (62.53, 23.07)"))
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
        if t.GetLayer() == pcbnew.In2_Cu:
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
