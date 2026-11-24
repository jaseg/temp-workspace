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
NATIVE6 = {"analog", "phase", "pstrobe", "fpga", "power", "mcuif"}   # all blocks native 6-layer (22 Nov)
OUT = os.path.join(HERE, "scope-fe.kicad_pcb")
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board6/int"
os.makedirs(SCR, exist_ok=True)
W_RF = 0.16                     # 50 R on L1 / L6 (boardlib.microstrip, 0.0994 mm 3313)
W_BUS = 0.11                    # L6 bus tracks (0.11 / 0.11 at 0.22 pitch)

FAST_RX = re.compile(r"^/(TAP\d+|COARSE|FPGA_CLK|MCU_CLK|SPI_\w+|ADC_TRIG|fpga_clock/JTAG_\w+|fpga_clock/DBG2|"
                     r"FPGA_DONE|FPGA_RECONFIG|I2C_\w+|S_STROBE_\w|PH_STROBE_\w|USB_D\w)$")

# --fast: reuse the cached board state just before the power / slow-line stages (written by every full run as
# SCR/pre_power.kicad_pcb + pre_power.json); skips merge, signal routes and planes (development only)
FAST = "--fast" in sys.argv
CACHE = os.path.join(SCR, "pre_power.kicad_pcb")


def loc(v):
    return round(pcbnew.ToMM(v.x) - bl.ORG[0], 4), round(pcbnew.ToMM(v.y) - bl.ORG[1], 4)


def zbox(z):
    bb = z.GetBoundingBox()
    return tuple(round(v, 2) for v in (pcbnew.ToMM(bb.GetX()) - bl.ORG[0], pcbnew.ToMM(bb.GetY()) - bl.ORG[1],
                                      pcbnew.ToMM(bb.GetRight()) - bl.ORG[0], pcbnew.ToMM(bb.GetBottom()) - bl.ORG[1]))


if not FAST:
    m = bl.new_master(W, H)
    B = m.b
    for fp in B.GetFootprints():
        if fp.GetReference().startswith("H"):
            fp.SetBoardOnly(True)
            fp.Value().SetVisible(False)
            fp.Reference().SetVisible(False)
    for k, (x, y) in POS.items():
        bl.merge(B, f"blocks/{k}/{k}.kicad_pcb", x, y, layer_map=None if k in NATIVE6 else bl.LAYER_MAP_4TO6)




    def near(a, b, tol=0.02):
        return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol




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
    VTHV = [loc(v.GetPosition())[0] for v in B.GetTracks() if isinstance(v, pcbnew.PCB_VIA) and
            v.GetNetname().startswith('/trigger_phase/VTH')]
    RF = {}


    def T(net, w, pts, layer, lane, ch=0.1):
        q = m.track(net, w, pts, layer, ch=ch)
        LOG.append((net, layer, lane, round(bl.plen(q), 3)))
        return q


    # (the phase VTH rails are on L3 inside the native six-layer phase block since 22 Nov)

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

    # ---------------------------------------------------------------- USB 90 R pair power S -> mcuif N (L1, then L6)
    # The east TAPs (U311 / U312) run east on the L6 highway (y 29.35-30.6), so the pair crosses that band on L1:
    # from the power stubs (82.6 / 83.0, 22.5) east on L1 north of U311's pins, south on L1 in the gap U311|U312
    # (x 86.25 / 86.65), vias (86.25, 31.0) / (87.1, 31.3) below the highway, L6 diagonal between the phase GND via
    # (88.09, 31.41) and the VTAP_N via (88.09, 33.66) into tap-row lane 13 (x 89.0 / 89.4, between node window 13
    # (86.80-88.60) and the tap-14 jumpers (89.92)), south, vias east of the C357 GND via (88.09, 43.59), F into mcuif.
    W_USB = 0.18
    pDP, pDM = (82.6, 22.5), (83.0, 22.5)
    # the VTH2 rail (L1, comparator centre line y 27.755) and the highway TAP14 / TAP15 (L6, y 30.35 / 30.6) both cross the
    # pair's path: L1 down to above VTH2, L6 under it, L1 again under the highway lanes, L6 from y 31.1 on
    T("/USB_DP", W_USB, [pDP, (82.6, 22.95), (82.9, 23.25), (86.0, 23.25), (86.4, 23.65), (86.4, 27.2)], "F.Cu",
      "L1 north of U311, gap U311|U312", ch=0.0001)
    T("/USB_DM", W_USB, [pDM, (83.0, 22.55), (83.3, 22.85), (86.4, 22.85), (86.9, 23.35), (86.9, 26.7)],
      "F.Cu", "L1 north of U311, gap U311|U312", ch=0.0001)
    m.via(86.4, 27.2, "/USB_DP"); m.via(86.9, 26.7, "/USB_DM")
    T("/USB_DP", W_USB, [(86.4, 27.2), (86.4, 29.4)], "B.Cu", "L6 under the VTH2 rail")
    T("/USB_DM", W_USB, [(86.9, 26.7), (86.9, 29.9)], "B.Cu", "L6 under the VTH2 rail")
    m.via(86.4, 29.4, "/USB_DP"); m.via(86.9, 29.9, "/USB_DM")
    T("/USB_DP", W_USB, [(86.4, 29.4), (86.4, 31.06)], "F.Cu", "L1 over the highway TAP14 / TAP15")
    T("/USB_DM", W_USB, [(86.9, 29.9), (86.9, 30.96), (87.39, 31.45)], "F.Cu", "L1 over the highway TAP14 / TAP15",
      ch=0.0001)
    m.via(86.4, 31.06, "/USB_DP"); m.via(87.39, 31.45, "/USB_DM")
    T("/USB_DP", W_USB, [(86.4, 31.06), (89.0, 33.66), (89.0, 43.35), (88.0, 44.35)], "B.Cu", "L6 tap-row lane 13",
      ch=0.0001)
    T("/USB_DM", W_USB, [(87.39, 31.45), (89.4, 33.46), (89.4, 43.7), (89.6, 43.9)], "B.Cu", "L6 tap-row lane 13",
      ch=0.0001)
    m.via(88.0, 44.35, "/USB_DP"); m.via(89.6, 43.9, "/USB_DM")
    T("/USB_DP", W_USB, [(88.0, 44.35), (88.0, 45.0)], "F.Cu", "via to mcuif F stub")
    T("/USB_DM", W_USB, [(89.6, 43.9), (88.5, 45.0)], "F.Cu", "via to mcuif F stub")
    for gx, gy in ((90.35, 44.1),):          # ground via beside the mcuif-end signal vias (the phase GND via 88.09 /
        m.via(gx, gy, "GND")                 # 31.41 sits beside the highway-end pair)

    # ---------------------------------------------------------------- slow lines whose analog end is a B column: L3 vias
    # (VBIAS_A / VBIAS_K: via at y 20.3 on the B column; ADC_IN / ADC_REF_MID: their existing vias) - the B stubs
    # below are removed so the L6 COARSE lane passes
    for net, yv in (("/VBIAS_A", 15.9), ("/VBIAS_K", 20.3), ("/ADC_IN", None), ("/ADC_REF_MID", None)):
        e = (ia[net]["x"], ia[net]["y"] + 1.0)
        (t, _, o), = seg_at(net, e, "B.Cu")
        if yv is None:
            B.Remove(t)
        else:
            t.SetStart(m.P(*o)); t.SetEnd(m.P(e[0], yv))
            m.via(e[0], yv, net)

    # ---------------------------------------------------------------- L6: JTAG group (TOPOLOGY.md section 7)
    # fpga slots x 62.5-64.5: straight south to an upper band under the comparator bodies (y 24.75 + 0.3 j, between the
    # +3V3 via row y 24.25 and the R380 network / VTH via row), west, south through tap-row lanes 2 / 3 / 4 (between a
    # node window and the next summing jumpers), 45-degree jogs in the strip y 42.3-44.7 onto the J501 interfaces.
    JT = ["/fpga_clock/DBG2", "/fpga_clock/JTAG_TCK", "/fpga_clock/JTAG_TMS", "/fpga_clock/JTAG_TDI", "/fpga_clock/JTAG_TDO"]
    LANE_C = lambda n: 30.58 + 4.514 * n                 # tap-row lane centre between window n and the jumpers of n + 1
    JLANE = {JT[0]: LANE_C(2) - 0.15, JT[1]: LANE_C(2) + 0.15, JT[2]: LANE_C(3) - 0.15, JT[3]: LANE_C(3) + 0.15,
             JT[4]: LANE_C(4)}
    mc_if = {i["net"]: (i["x"] + 27.0, i["y"] + 45.0) for i in json.load(open("blocks/mcuif/mcuif.ifaces.json"))["ifaces"]}
    for j, net in enumerate(JT):
        top = fpga_stub_top(net)
        yb = round(24.75 + 0.3 * j, 3)
        xl = round(JLANE[net], 3)
        tx, ty = mc_if[net]
        ya = 42.3
        T(net, W_BUS, [top, (top[0], yb), (xl, yb), (xl, ya), (tx, ya + abs(tx - xl)), (tx, ty)], "B.Cu",
          f"L6 band y {yb:.2f}, tap-row lane x {xl:.2f}", ch=0.1)

    # ---------------------------------------------------------------- L6: MCU group + TAP15..TAP10 drop through gap U309|U310
    # slots x 65.0 + 0.5 i (i 0-9 MCU group, 10-15 TAP15..TAP10) fan into a column x 68.1 + 0.25 i (gap U309|U310, whose
    # vias were moved under the bodies in gen_phase.py), down to the highway lanes y 29.35 + 0.25 (15 - i) and east.
    # TAP10 (northmost) peels first to U310, ..., TAP15 to U312 (under-body vias, the pin-7 one approached 0.5 mm east of
    # the VTH via below it); the MCU group (south) turns south into tap-row lanes 9-12 and jogs onto the mcuif interfaces.
    MG = ["/MCU_CLK", "/SPI_CS", "/I2C_SDA", "/FPGA_DONE", "/SPI_MOSI", "/SPI_MISO", "/SPI_SCK", "/I2C_SCL",
          "/FPGA_RECONFIG", "/ADC_TRIG"] + [f"/TAP{k}" for k in range(15, 9, -1)]
    MLANE = {"/MCU_CLK": (LANE_C(10) - 0.5, 42.0),           # lane 10 (west slot): frees the ADC_IN / TRIG_SEL stubs
             "/SPI_CS": (LANE_C(10) - 0.25, 42.05), "/I2C_SDA": (LANE_C(10), 41.95),
             "/FPGA_DONE": (LANE_C(10) + 0.25, 41.85), "/SPI_MOSI": (LANE_C(11) - 0.42, 41.9),
             "/SPI_MISO": (LANE_C(11) - 0.19, 42.0), "/SPI_SCK": (LANE_C(11) + 0.04, 42.1),
             "/I2C_SCL": (LANE_C(11) + 0.27, 42.0), "/FPGA_RECONFIG": (LANE_C(12) - 0.13, 42.0),
             "/ADC_TRIG": (LANE_C(12) + 0.12, 41.9)}
    Y0 = 22.7
    for i, net in enumerate(MG):
        top = fpga_stub_top(net)
        sx = top[0]
        cx = round(68.1 + 0.25 * i, 3)
        yh = round(29.35 + 0.25 * (15 - i), 3)
        pts = [top, (sx, Y0), (cx, Y0 + abs(cx - sx)), (cx, yh)]
        if net.startswith("/TAP"):
            vx, vy = phase_if[net]
            xr = vx + 0.5 if any(abs(vx - x) < 0.02 for x in VTHV) else vx
            tail = [(xr, yh), (xr, vy + abs(xr - vx)), (vx, vy)]
            T(net, W_BUS, pts + tail, "B.Cu", f"L6 drop x {cx:.2f}, highway y {yh:.2f}, peel x {xr:.2f}", ch=0.1)
        else:
            xl, ya = MLANE[net]
            xl = round(xl, 3)
            tx, ty = mc_if[net]
            tail = [(xl, yh), (xl, ya), (tx, ya + abs(tx - xl)), (tx, ty)]
            T(net, W_BUS, pts + tail, "B.Cu", f"L6 drop x {cx:.2f}, highway y {yh:.2f}, lane x {xl:.2f}", ch=0.1)
    # TAP8 / TAP9 (U309, west of the drop gap) cannot reach U309 on L6 (the column of gap U309|U310 and the highway wall
    # it off): from their eastmost fpga slots (73.5 / 73.0) they hop to L1 right below the fpga edge and run west on L1
    # along y 22.75 / 23.15 (over the L6 fan, north of U310's cap and U309's pins, L2 ground below) straight into U309's
    # output pads 7 / 6 from above.  U309's under-body output vias + stubs are removed (no longer needed).
    for net, sx, yv, yf in (("/TAP8", 73.5, 22.75, 22.75), ("/TAP9", 73.0, 23.25, 23.15)):
        top = fpga_stub_top(net)
        T(net, W_BUS, [top, (sx, yv)], "B.Cu", "L6 fpga stub to L1 hop via")
        m.via(sx, yv, net)
        vx, vy = phase_if[net]
        for t, e, o in seg_at(net, (vx, vy), "F.Cu"):
            B.Remove(t)
            padxy = o
        kill_via(net, (vx, vy))
        pts = [(sx, yv)] + ([(sx - (yv - yf), yf)] if yv != yf else []) + [(vx, yf), padxy]
        T(net, W_BUS, pts, "F.Cu", f"L1 hop y {yf:.2f} over the fan into U309 pad", ch=0.1)
    m.via(74.1, 23.35, "GND")              # ground via beside the two hop vias
    # ---------------------------------------------------------------- slow bias / control lines (board_slow.py)
    # block ends: VOFS / VNEG_REF at their analog vias (1.0 / 1.94, 19.2; the B stubs below are removed), DAC_TRIG / TRIG_SEL
    # on a via placed on the phase B stub (4.6, 41.0) / (9.25, 44.6) (stub ends beyond removed), VTAP_TH on the R380 / R381 link
    for net, x in (("/VOFS", 1.0), ("/VNEG_REF", 1.94)):
        for t, e, o in seg_at(net, (x, 22.5), "B.Cu"):
            B.Remove(t)
    for net, (x, yc) in (("/DAC_TRIG", (4.6, 41.0)), ("/TRIG_SEL", (9.25, 44.6))):
        for t in segs(net, "B.Cu"):
            a_, b_ = loc(t.GetStart()), loc(t.GetEnd())
            if abs(a_[0] - x) < 0.02 and abs(b_[0] - x) < 0.02 and max(a_[1], b_[1]) > yc:
                lo, hi = sorted((a_[1], b_[1]))
                if lo >= yc - 1e-6:
                    B.Remove(t)
                else:
                    t.SetStart(m.P(x, lo)); t.SetEnd(m.P(x, yc))
        m.via(x, yc, net)

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
    bl.save_board(B, CACHE)
    json.dump({"mc_if": mc_if, "phase_if": phase_if, "RF": RF, "LOG": LOG, "NOT_PLACED": NOT_PLACED},
              open(CACHE.replace(".kicad_pcb", ".json"), "w"))
else:
    m = bl.Block("master")
    B = m.b = pcbnew.LoadBoard(CACHE)
    m.nets = {str(k): v for k, v in B.GetNetsByName().items()}
    _c = json.load(open(CACHE.replace(".kicad_pcb", ".json")))
    mc_if = {k: tuple(v) for k, v in _c["mc_if"].items()}
    phase_if = {k: tuple(v) for k, v in _c["phase_if"].items()}
    RF, LOG, NOT_PLACED = _c["RF"], [tuple(x) for x in _c["LOG"]], _c["NOT_PLACED"]
    import board_finish as bf

    def near(a, b, tol=0.02):
        return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol

    def segs(net, layer=None):
        return [t for t in B.GetTracks() if not isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == net and
                (layer is None or t.GetLayerName() == layer)]

    def vias(net):
        return [t for t in B.GetTracks() if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == net]

# 24 Nov 2026: slow bias / control lines FIRST (explicit geometry, board_slow.py), then every supply rail by the
# grid router of board_power.py around them (TOPOLOGY.md section 10)
import board_power
import board_slow
pcbnew.ZONE_FILLER(B).Fill(B.Zones())
SLOW = board_slow.draw(B, m, mc_if, phase_if["/VTAP_TH"])
print("slow lines:", SLOW)
for net, (ok, L_, nv) in SLOW.items():
    LOG.append((net, "B.Cu+In2.Cu", "slow line (board_slow.py): L6 tap-row lane, L3 north", L_))
    if not ok:
        NOT_PLACED.append((net, "board_slow: no L3 path (see log)"))
if "--slowonly" in sys.argv:
    bl.save_board(B, os.path.join(SCR, "slow.kicad_pcb"))
    sys.exit(0)
# the phase block's L4 VTAP strips go: L4 is +3V3 only (TOPOLOGY.md section 8); VTAP_P / VTAP_N run on L3
for z in list(B.Zones()):
    if not z.GetIsRuleArea() and z.IsOnLayer(pcbnew.In3_Cu) and z.GetNetname() in ("/VTAP_P", "/VTAP_N"):
        B.Remove(z)
# review (22 Nov): dangling block copper from the DRC (VTAP stubs, VTH rail overhangs, R305 via, TRIG_SEL pad entry)
print("review cleanup:", bf.cleanup(B, m))
if "--prepower" in sys.argv:
    bl.save_board(B, os.path.join(SCR, "prepower.kicad_pcb"))
    sys.exit(0)
_rp = board_power.apply(B, m)
print("power: failed", _rp.get("failed"), "| no landing", _rp.get("no_landing"), "| vias", _rp.get("vias"), "| dangling", _rp.get("dangling"), "| tight", _rp.get("tight"), "| pruned", _rp.get("pruned"), "| snapped", _rp.get("snapped"), "| corners", _rp.get("corners"))
pcbnew.ZONE_FILLER(B).Fill(B.Zones())
print("rail widening [mm widened]:", board_power.widen(B, m))
import board_stitch
# R737.2 (TRIG_SEL pull-down, B side) sits in a B.Cu pour pocket (BOOT0, JP701, R729) whose neck no longer fills:
# explicit B track to the neighbouring GND pad R729.2
m.track("GND", 0.25, [(70.3, 48.86), (69.85, 48.86), (69.75, 48.76), (69.75, 47.49), (69.65, 47.39), (69.1, 47.39)],
        "B.Cu", ch=0.0001)
SIGV = [(86.4, 27.2), (86.9, 26.7), (86.4, 29.4), (86.9, 29.9), (86.4, 31.06), (87.39, 31.45), (88.0, 44.35), (89.6, 43.9), (73.5, 22.75), (73.0, 23.25)] + \
    [loc(v.GetPosition()) for v in B.GetTracks() if isinstance(v, pcbnew.PCB_VIA) and
     v.GetNetname() in ("/VBIAS_A", "/VBIAS_K", "/ADC_IN", "/ADC_REF_MID", "/VOFS", "/VNEG_REF", "/DAC_TRIG",
                        "/TRIG_SEL")]
# ZONES-4 (24 Nov): every via of a fast / RF net (board and block fan-outs) gets a GND via within 1 mm where room
_fastv = [loc(v.GetPosition()) for v in B.GetTracks() if isinstance(v, pcbnew.PCB_VIA) and
          (FAST_RX.match(v.GetNetname()) or v.GetNetname() in RF)]
SIGV += [p_ for p_ in _fastv if not any(abs(p_[0] - q[0]) < 0.01 and abs(p_[1] - q[1]) < 0.01 for q in SIGV)]
RFT = [(loc(t.GetStart()), loc(t.GetEnd()), pcbnew.ToMM(t.GetWidth())) for t in B.GetTracks()
       if t.GetClass() == "PCB_TRACK" and t.GetNetname() in ("/BUF_OUT_T", "/PH_STROBE_P", "/PH_STROBE_N")]
NST = board_stitch.stitch(B, m, RFT, SIGV)
# second chance for the signal vias without a ground via: the same raster at the board's own clearance (0.12 mm
# instead of the stitching margin 0.2), every spot within 1.5 mm (0.05 mm steps)
if NST.get("lacking"):
    _clr0 = board_stitch.CLR
    board_stitch.CLR = 0.2                       # >= the Power netclass clearance 0.15 + raster margin
    _occ = board_stitch.build_mask(B)
    board_stitch.CLR = _clr0
    _still = []
    for sx, sy in NST["lacking"]:
        _best = None
        for _i in range(-30, 31):
            for _j in range(-30, 31):
                x_, y_ = sx + 0.05 * _i, sy + 0.05 * _j
                d_ = math.hypot(x_ - sx, y_ - sy)
                if not (0.55 <= d_ <= 1.5):
                    continue
                gi, gj = int(round(x_ / board_stitch.G)), int(round(y_ / board_stitch.G))
                if 0 <= gi < _occ.shape[0] and 0 <= gj < _occ.shape[1] and not _occ[gi, gj]:
                    if _best is None or d_ < _best[0]:
                        _best = (d_, round(x_, 3), round(y_, 3))
        if _best:
            m.via(_best[1], _best[2], "GND")
            _occ = board_stitch.build_mask(B) if False else _occ
            _k = int(1.0 / board_stitch.G)
            gi, gj = int(round(_best[1] / board_stitch.G)), int(round(_best[2] / board_stitch.G))
            _occ[max(0, gi - _k):gi + _k + 1, max(0, gj - _k):gj + _k + 1] = True
            NST["beside signal vias"] += 1
            NST["signal vias without a ground via"] -= 1
            NST.setdefault("second_chance", []).append(((sx, sy), _best[1:], round(_best[0], 2)))
        else:
            _still.append((sx, sy))
    NST["lacking"] = _still
_gv = [loc(v.GetPosition()) for v in B.GetTracks() if isinstance(v, pcbnew.PCB_VIA) and v.GetNetname() == "GND"]
_far = [(p_, round(min(math.hypot(p_[0] - g[0], p_[1] - g[1]) for g in _gv), 2)) for p_ in _fastv]
NST["fast vias"] = len(_far)
NST["fast vias with a GND via <= 1 mm"] = sum(1 for _, d in _far if d <= 1.0)
NST["fast vias > 1 mm"] = sorted([(p_, d) for p_, d in _far if d > 1.0], key=lambda r: -r[1])
print("GND stitching:", NST)
bf.silk(B, m)
# routes.json first (board_power.py reads it), then the power module as the LAST copper step
json.dump({"log": LOG, "not_placed": NOT_PLACED, "rf": RF, "stitch": NST}, open(os.path.join(HERE, "routes.json"), "w"),
          indent=1)
pcbnew.ZONE_FILLER(B).Fill(B.Zones())
B.BuildConnectivity()
PWR = board_power.verify(B)
print(board_power.table(PWR))
if "--powonly" in sys.argv:
    bl.save_board(B, os.path.join(SCR, "powonly.kicad_pcb"))
    sys.exit(0)
# REPAIR (24 Nov, recheck RF2-9 / PARTS-9): DNP parts of the schematic (symbol 'dnp yes') are excluded from the
# placement (pos) file on the board, so the assembler does not place them.  The KiCad 7 board format has no footprint
# DNP flag, so the nightly parity check still lists 'Do not populate' for these 4 (C631, D402, D403, R122); the BOM
# flag stays as on the symbol (in BOM, marked DNP by gen_bom).
import re as _re, glob as _glob
_DNP = set()
for _f in _glob.glob(os.path.join(HERE, "../../kicad/*.kicad_sch")):
    for _m in _re.finditer(r'\(symbol \(lib_id "[^"]+"\)(.*?)\(property "Reference" "([^"]+)"', open(_f).read(), _re.S):
        if _re.search(r'\(dnp yes\)', _m.group(1)):
            _DNP.add(_m.group(2))
for _fp in B.GetFootprints():
    if _fp.GetReference() in _DNP:
        _fp.SetAttributes(_fp.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
print("DNP (excluded from the pos file):", sorted(_DNP))
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


def classify(B, no_ref):
    """split the samples without filled GND into deliberate cut-outs, via / PTH antipads (the plane's clearance
    around a via or through-hole pad the track passes or ends in) and real plane holes"""
    from collections import Counter
    P = lambda x, y: pcbnew.VECTOR2I(pcbnew.FromMM(x + bl.ORG[0]), pcbnew.FromMM(y + bl.ORG[1]))
    cuts = {"F.Cu": [z for z in B.Zones() if z.GetIsRuleArea() and z.IsOnLayer(pcbnew.In1_Cu)],
            "B.Cu": [z for z in B.Zones() if z.GetIsRuleArea() and z.IsOnLayer(pcbnew.In4_Cu)]}
    vv = [loc(v.GetPosition()) + (v.GetNetname(),) for v in B.GetTracks() if isinstance(v, pcbnew.PCB_VIA)]
    pp = [loc(p.GetPosition()) + (p.GetNetname(), pcbnew.ToMM(max(p.GetSize().x, p.GetSize().y)) / 2)
          for f in B.GetFootprints() for p in f.Pads() if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)]
    cls, real = Counter(), []
    for net, lay, (x, y) in no_ref:
        if any(z.Outline().Contains(P(x, y)) for z in cuts[lay]):
            cls["deliberate cut-out (listed L2 / L5 window)"] += 1
        elif any(math.hypot(x - a, y - b) < 0.55 and n != "GND" for a, b, n in vv):
            cls["via antipad"] += 1
        elif any(math.hypot(x - a, y - b) < r + 0.4 and n != "GND" for a, b, n, r in pp):
            cls["PTH antipad"] += 1
        else:
            cls["REAL plane hole"] += 1
            real.append((net, lay, round(x, 2), round(y, 2)))
    return cls, real
print(f"rule 10: fast-net segments on L3: {len(r10['fast_on_L3'])}; L1/L6 samples {r10['samples']}, "
      f"without filled GND on L2/L5: {len(r10['no_ref'])}")
CLS, REAL = classify(B, r10["no_ref"])
print("   classes:", dict(CLS))
for r_ in REAL[:30]:
    print("    real hole:", r_)
for z_ in r10["L4"]:
    print("   L4 zone", z_)
json.dump({"log": LOG, "not_placed": NOT_PLACED, "rf": RF, "rule10_classes": dict(CLS), "stitch": NST, "rule10": {k: (v if k in ("samples", "L4") else len(v)) for k, v in r10.items()},
           "rule10_detail": r10}, open(os.path.join(HERE, "routes.json"), "w"), indent=1)
c = bl.check_board(OUT, rf_widths=RF, verbose=8)
json.dump({k: v for k, v in c.items() if k != "details"}, open(os.path.join(SCR, "check.json"), "w"), indent=1)
json.dump(c["details"], open(os.path.join(SCR, "check_details.json"), "w"), indent=1, default=str)
# VIAS-OUT-OF-PADS (24 Nov, RULES.md rule 12): ordinary tented vias only (no plugged / capped / filled vias), so no
# via may lie in or touch a soldered SMD pad (copper, mask or paste opening) on either side; exposed pads only as
# listed in via_in_pad.EP_ALLOW (0.2 mm drill, wholly inside the pad).  Must report FAIL 0.
import via_in_pad
VIP = via_in_pad.check(OUT)
via_in_pad.report(VIP, verbose=True)
json.dump({k: (v if isinstance(v, int) else len(v)) for k, v in VIP.items()}, open(os.path.join(SCR, "via_in_pad.json"), "w"),
          indent=1)
if VIP["fail"] or VIP["bare_with_opening"]:
    print("VIA-IN-PAD CHECK FAILED:", len(VIP["fail"]), "vias in soldered pads")
