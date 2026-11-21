#!/usr/bin/env python3
"""Integrated scope-fe board, SIX layers (RULES rule 10, JLC06161H-3313), phase one: layer conversion and
routing topology.

  L1 F.Cu  RF / analog + components        L2 In1  solid GND (block cut-outs kept)
  L3 In2   slow bias / control lines + GND  L4 In3  power: +3V3 background plane, other rails as wide strips
  L5 In4   solid GND                        L6 B.Cu fast inter-block digital buses + bottom components

Run:  cd design/lowcost/layout/board && python3 gen_board.py
Writes scope-fe.kicad_pcb + scope-fe.kicad_pro (KiCad 7.0.11 format) and routes.json.
The blocks are 4-layer files; they are merged with boardlib.LAYER_MAP_4TO6 (block In1 -> L2, block In2 -> L4).
Interface positions come from blocks/*/*.ifaces.json, block sizes from their positions only, so a re-derived
block (phase two) that changes by a few tenths of a millimetre is re-merged without edits here.
"""
import os, sys, json, math, re
os.environ["BL_STACKUP"] = "6L"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
import pcbnew
import boardlib as bl
import boardroute as br

W, H = 100.0, 57.0
POS = {"analog": (0.0, 1.0), "phase": (0.0, 22.5), "pstrobe": (9.5, 25.0), "fpga": (56.0, 0.5),
       "power": (74.0, 0.0), "mcuif": (27.0, 45.0)}
W_RF_BLK = 0.36            # phase one: inter-block RF lines keep the blocks' (old 4-layer) 50 R geometry
OUT = os.path.join(HERE, "scope-fe.kicad_pcb")
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board6/int"
os.makedirs(SCR, exist_ok=True)

# fast digital inter-block nets: L6 (B.Cu) only, never L3 (rule 10)
FAST_RX = re.compile(r"^/(TAP\d+|COARSE|FPGA_CLK|MCU_CLK|SPI_\w+|ADC_TRIG|fpga_clock/JTAG_\w+|fpga_clock/DBG2|"
                     r"FPGA_DONE|FPGA_RECONFIG|I2C_\w+|ADC_IN)$")
SLOW_L3 = ("/VBIAS_A", "/VBIAS_K", "/VOFS", "/VNEG_REF", "/DAC_TRIG", "/TRIG_LEVEL", "/VTAP_TH", "/ADC_REF_MID",
           "/TRIG_SEL")
RAIL_L4 = ("/VTAP_P", "/VTAP_N")

m = bl.new_master(W, H)
B = m.b
for fp in B.GetFootprints():                       # mounting holes: board-only (no schematic symbol)
    if fp.GetReference().startswith("H"):
        fp.SetBoardOnly(True)
        fp.Value().SetVisible(False)
        fp.Reference().SetVisible(False)
for k, (x, y) in POS.items():
    bl.merge(B, f"blocks/{k}/{k}.kicad_pcb", x, y, layer_map=bl.LAYER_MAP_4TO6)


def loc(v):
    return round(pcbnew.ToMM(v.x) - bl.ORG[0], 4), round(pcbnew.ToMM(v.y) - bl.ORG[1], 4)


def zbox(z):
    bb = z.GetBoundingBox()
    return tuple(round(v, 2) for v in (pcbnew.ToMM(bb.GetX()) - bl.ORG[0], pcbnew.ToMM(bb.GetY()) - bl.ORG[1],
                                      pcbnew.ToMM(bb.GetRight()) - bl.ORG[0], pcbnew.ToMM(bb.GetBottom()) - bl.ORG[1]))


# ---------------------------------------------------------------- planes owned by the integrator
x0p, y0p = POS["pstrobe"]
L2_CUTS = []
for z in list(B.Zones()):
    if z.GetIsRuleArea():
        # review (kept): the phase block's all-layer "north_cut" keep-out (its hole for pstrobe chain A, the
        # pstrobe rectangle) must not survive the merge - it blanked the ground under chain A
        b_ = zbox(z)
        if z.IsOnLayer(pcbnew.In1_Cu) and z.IsOnLayer(pcbnew.F_Cu) and abs(b_[0] - x0p) < 0.3 and \
                abs(b_[1] - y0p) < 0.3 and (b_[2] - b_[0]) > 12:
            B.Remove(z)
            continue
        if z.IsOnLayer(pcbnew.In1_Cu):
            L2_CUTS.append(z)
        continue
    if z.GetNetname() == "GND" and (z.IsOnLayer(pcbnew.In1_Cu) or z.IsOnLayer(pcbnew.In3_Cu)):
        B.Remove(z)                                # replaced by the board-wide L2 / L5 planes
    elif z.GetNetname() == "+3V3" and z.IsOnLayer(pcbnew.In3_Cu):
        B.Remove(z)                                # fpga's +3V3: the L4 background plane
    elif z.IsOnLayer(pcbnew.In3_Cu):
        z.SetAssignedPriority(5)                   # block rail zones (+1V2, VTAP_P / VTAP_N strips) over +3V3
for z in B.Zones():
    if not z.GetIsRuleArea():
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
# fpga block fix: its +1V2 plane-layer track (60.4, 7.1) ran across the U501 exposed-pad GND vias (short, found
# in the 4-layer review); the +1V2 L4 zone of the block already joins the same vias
for t in list(B.GetTracks()):
    if not isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == "+1V2" and t.GetLayer() == pcbnew.In3_Cu:
        B.Remove(t)

# L2 cut-outs (hold nodes, divider node, SMA pads, tap pads): L3 is cleared too (no pour, no slow track) so the
# cut-out keeps its purpose (the pad sees the far reference, not a pour 0.55 mm below the missing L2);
# the L4 power plane stays (0.78 mm below L1, AC ground through the decoupling)
for z in L2_CUTS:
    ol = z.Outline()
    pts = [loc(ol.CVertex(i)) for i in range(ol.OutlineCount() and ol.COutline(0).PointCount())]
    if len(pts) >= 3:
        m.keepout(pts, layers=("In2.Cu",), tracks=True, vias=False)

# ---------------------------------------------------------------- interfaces -> route end points
IF = {}
for k in POS:
    d = json.load(open(f"blocks/{k}/{k}.ifaces.json"))
    for i in d["ifaces"]:
        if i["class"] == "supply" and i["layer"].startswith("In"):
            continue
        x, y = i["x"] + POS[k][0], i["y"] + POS[k][1]
        IF.setdefault(bl.canon(i["net"]), []).append(dict(i, bx=round(x, 4), by=round(y, 4), block=k))

COMPASS = ["E", "SE", "S", "SW", "W", "NW", "N", "NE"]


def compass(dx, dy):
    a = math.degrees(math.atan2(dy, dx)) % 360
    return COMPASS[int(round(a / 45)) % 8]


def tracks_at(net, x, y, layer=None, tol=0.003):
    out = []
    for t in B.GetTracks():
        if t.GetNetname() != net or isinstance(t, pcbnew.PCB_VIA):
            continue
        if layer and t.GetLayerName() != layer:
            continue
        for e, o in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
            ex, ey = loc(e)
            if abs(ex - x) < tol and abs(ey - y) < tol:
                out.append((t, loc(o)))
    return out


def via_at(net, x, y, tol=0.003):
    for t in B.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == net:
            vx, vy = loc(t.GetPosition())
            if abs(vx - x) < tol and abs(vy - y) < tol:
                return t
    return None


def endpoint(net, i, strip=True, maxlen=3.0):
    """route end point for an interface: the via behind a straight stub (stub deleted, the route may leave the
    via on any layer) or the stub end"""
    x, y, ly = i["bx"], i["by"], i["layer"]
    ts = tracks_at(net, x, y, ly)
    if not ts:
        return (x, y, ly, "*")
    t, (ox, oy) = ts[0]
    if strip and via_at(net, ox, oy) is not None and \
            (math.hypot(x - ox, y - oy) < maxlen or i["block"] == "analog"):
        B.Remove(t)
        return (ox, oy, "*", "*")
    return (x, y, ly, compass(x - ox, y - oy))


R = br.Router(m, W, H)
# slow L3 lines and power strips stay out of the L2 cut-out areas and of the analog block's quiet core
for z in L2_CUTS:
    b_ = zbox(z)
    R.keep("In2.Cu", *b_)
LOG = []


def rt(net, a, b, **kw):
    r = R.route(net, a, b, **kw)
    L = sum(bl.plen(p) for _, p in r) if r else None
    LOG.append((bl.canon(net), None if L is None else round(L, 3), None if not r else len(r) - 1,
                sorted({ln for ln, _ in r}) if r else None))
    return r


# ---------------------------------------------------------------- 1. RF / matched nets on F.Cu
RF = {}
# S_STROBE_P / N and PSTRB_A / K: the block interfaces abut (analog / fpga, pstrobe / phase)
for t, o in tracks_at("/PH_STROBE_N", *[(i["bx"], i["by"]) for i in IF["/PH_STROBE_N"] if i["block"] == "fpga"][0],
                      "F.Cu") + \
        tracks_at("/PH_STROBE_P", *[(i["bx"], i["by"]) for i in IF["/PH_STROBE_P"] if i["block"] == "fpga"][0], "F.Cu"):
    B.Remove(t)
ipp = [i for i in IF["/PH_STROBE_P"] if i["block"] == "pstrobe"][0]
ipn = [i for i in IF["/PH_STROBE_N"] if i["block"] == "pstrobe"][0]
# the pstrobe inputs are boxed in on F.Cu by the phase block's C301 / C306 row: both strobes drop to L6 (over
# L5 ground) through one via each right at the pstrobe interface (same via count on P and N), GND vias beside
vp = m.via(ipp["bx"], ipp["by"] + 0.1, "/PH_STROBE_P"); R.add_item(vp)
m.track("/PH_STROBE_P", W_RF_BLK, [(ipp["bx"], ipp["by"]), (ipp["bx"], ipp["by"] + 0.1)], "F.Cu")
vn = m.via(ipn["bx"], ipn["by"] - 0.1, "/PH_STROBE_N"); R.add_item(vn)
m.track("/PH_STROBE_N", W_RF_BLK, [(ipn["bx"], ipn["by"]), (ipn["bx"], ipn["by"] - 0.1)], "F.Cu")
fpp = [i for i in IF["/PH_STROBE_P"] if i["block"] == "fpga"][0]
fpn = [i for i in IF["/PH_STROBE_N"] if i["block"] == "fpga"][0]
php = (fpp["bx"] + 1.9, fpp["by"], "F.Cu", "SW")
phn = (fpn["bx"] + 1.25, fpn["by"], "F.Cu", "SW")
for net, a, b in (("/PH_STROBE_N", phn, (ipn["bx"], ipn["by"] - 0.1, "*", "*")),
                  ("/PH_STROBE_P", php, (ipp["bx"], ipp["by"] + 0.1, "*", "*"))):
    rt(net, a, b, w=W_RF_BLK, layers=("F.Cu", "B.Cu"), lcost={"F.Cu": 1.2}, clr=0.2, via_cost=6.0, margin=12,
       maxn=3_000_000)
RF["/PH_STROBE_P"] = RF["/PH_STROBE_N"] = W_RF_BLK

# BUF_OUT_T: analog S -> phase N (U301), 50 R on F.Cu
a, b = [endpoint("/BUF_OUT_T", i, strip=False) for i in IF["/BUF_OUT_T"]]
rt("/BUF_OUT_T", a, b, w=W_RF_BLK, layers=("F.Cu",), clr=0.3)
RF["/BUF_OUT_T"] = W_RF_BLK

# ---------------------------------------------------------------- 2. inter-block signal routing
# end points: every block brings its inter-block nets to a via + short B.Cu stub: the stub is removed and the
# route starts at the via, so the via becomes the layer change (L1 -> L6 or L3)
NETS = sorted(n for n, v in IF.items() if len({i["block"] for i in v}) >= 2 and n not in RF and
              all(i["class"] in ("slow", "supply", "pair") for i in v) and "STROBE" not in n)
EP = {}
for net in NETS:
    v = IF[net]
    if len(v) != 2:
        print("skip", net, len(v))
        continue
    EP[net] = [endpoint(net, i) for i in v]
    EP[net + ":w"] = max(i["width"] or 0.15 for i in v)
FAILED_FAST = []
SLOW_ON_L6 = []
ROUTED = set()


def fast(net, margin=10, maxn=400_000, w=None):
    """fast digital net: L6 (B.Cu over L5 GND); where the planar L6 topology is blocked (crossing the TAP
    ribbon / comb), a short hop on L1 (F.Cu over L2 GND, allowed by rule 11) - never L3"""
    a, b = EP[net]
    w = w or min(0.15, EP[net + ":w"])
    for lays, mg, mx in ((("B.Cu",), margin, maxn), (("B.Cu", "F.Cu"), 15, 1_000_000),
                         (("B.Cu", "F.Cu"), 40, 2_500_000)):
        r = rt(net, a, b, w=w, layers=lays, lcost={"F.Cu": 4.0}, via_cost=3.0, clr=0.1, margin=mg, maxn=mx)
        if r:
            ROUTED.add(net)
            return r
        LOG.pop()
    FAILED_FAST.append(net)
    return None


def l3_end(net, e):
    """slow line end on a B.Cu stub (not a via): add the via to L3 right at the interface"""
    if e[2] == "*" or e[2] == "In2.Cu":
        return e
    v = m.via(e[0], e[1], net)
    R.add_item(v)
    return (e[0], e[1], "*", "*")


def slow(net):
    a, b = [l3_end(net, e) for e in EP[net]]
    EP[net] = [a, b]
    w = 0.2
    for mg, mx in ((10, 400_000), (40, 2_500_000)):
        r = rt(net, a, b, w=w, layers=("In2.Cu",), clr=0.15, margin=mg, maxn=mx)
        if r:
            ROUTED.add(net)
            return r
        LOG.pop()
    # fallback (reported as a rule-10 deviation): L3 with an L6 section where the L3 corridor is walled off
    r = rt(net, a, b, w=w, layers=("In2.Cu", "B.Cu"), lcost={"B.Cu": 4.0}, via_cost=2.0, clr=0.15, margin=45,
           maxn=3_000_000)
    if r:
        ROUTED.add(net)
        SLOW_ON_L6.append(net)
    return r


# ---- planned TAP ribbon, west group (TAP0..9): L6 lanes between the fpga S via row (y 21.1, north) and the
# phase comparator via row (y 23.92, south), staircase in pin order (lane k at y0 + 0.2 k, 0.1 mm lines /
# 0.1 mm gaps): no lane crosses another.  Block adjustment: the phase GND via at (62.53, 23.07) (U-comparator
# GND pad drop) moves 0.28 mm south so that lane TAP7 passes.
for t in list(B.GetTracks()):
    if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == "GND":
        vx, vy = loc(t.GetPosition())
        if abs(vx - 62.53) < 0.02 and abs(vy - 23.075) < 0.02:
            for tt in B.GetTracks():
                if not isinstance(tt, pcbnew.PCB_VIA) and tt.GetNetname() == "GND":
                    for get, set_ in ((tt.GetStart, tt.SetStart), (tt.GetEnd, tt.SetEnd)):
                        q = loc(get())
                        if abs(q[0] - vx) < 0.02 and abs(q[1] - vy) < 0.02:
                            set_(m.P(q[0], 23.35))
            t.SetPosition(m.P(vx, 23.35))
            R.add_item(t)
TAP_W, TAP_P, TAP_Y0 = 0.1, 0.2, 21.48
for k in range(10):
    net = f"/TAP{k}"
    (xa, ya, _, _), (xb, yb, _, _) = EP[net]
    (xp, yp), (xs, ys) = sorted([(xa, ya), (xb, yb)], key=lambda q: -q[1])      # phase (south), fpga (north)
    Y = round(TAP_Y0 + TAP_P * k, 3)
    pts = [(xp, yp), (xp, Y), (xs, Y), (xs, ys)]
    m.track(net, TAP_W, pts, "B.Cu", ch=0.1)
    for p_, q_ in zip(pts, pts[1:]):
        R.mark_seg("B.Cu", p_[0], p_[1], q_[0], q_[1], TAP_W / 2, m.net(net).GetNetCode())
    LOG.append((net, round(bl.plen(pts), 3), 0, ["B.Cu"]))
    ROUTED.add(net)

taps_e = [f"/TAP{k}" for k in range(15, 9, -1)]
# the fpga's SPI / I2C / MCU_CLK comb (B.Cu, 0.25 mm pitch, no vias) has only one way out (south, through the
# east TAP region): it goes first, MCU_CLK (clock) first of all
fast_order = ["/MCU_CLK", "/SPI_SCK", "/SPI_MOSI", "/SPI_MISO", "/SPI_CS", "/I2C_SDA", "/I2C_SCL"] + taps_e + \
    ["/ADC_TRIG", "/FPGA_DONE", "/FPGA_RECONFIG", "/COARSE"] + \
    [n for n in NETS if "JTAG" in n or "DBG2" in n] + ["/ADC_IN"]
for net in fast_order:
    if net in EP:
        fast(net)
# slow lines in the order of their mcuif end (west to east) so that the L3 corridor fills without walls
for net in sorted([n for n in SLOW_L3 if n in EP],
                  key=lambda n: min(e[0] for e, i in zip(EP[n], IF[n]) if i["block"] == "mcuif") if any(
                      i["block"] == "mcuif" for i in IF[n]) else 0):
    slow(net)
# USB 90 R pair (power S -> mcuif N): F.Cu if a clear path exists, else L6 over L5
USB = {}
for net in ("/USB_DP", "/USB_DM"):
    if net not in EP:
        continue
    a, b = EP[net]
    r = rt(net, a, b, w=0.25, layers=("F.Cu",), clr=0.2, margin=8, maxn=600_000)
    if not r:
        LOG.pop()
        r = rt(net, a, b, w=0.2, layers=("F.Cu", "B.Cu"), lcost={"F.Cu": 1.5}, via_cost=4.0, clr=0.2, margin=15,
               maxn=1_500_000)
    USB[net] = r is not None
# VTAP_P / VTAP_N are rails (TP2272 outputs feeding the tap bias strips): L4 strips from the mcuif via to the
# phase strip vias
for net in RAIL_L4:
    if net in EP:
        a, b = EP[net]
        for wid in (0.6, 0.4):
            r = rt(net, a, b, w=wid, layers=("In3.Cu",), clr=0.25, margin=12, maxn=800_000)
            if r:
                ROUTED.add(net)
                break
            LOG.pop()
rest = [n for n in NETS if n in EP and n not in ROUTED and n not in FAILED_FAST and n not in RAIL_L4 and
        "USB" not in n]
for net in rest:
    print("unplanned slow net, routed on L3:", net)
    slow(net)

bl.save_board(B, os.path.join(SCR, "routed.kicad_pcb"))
print("routes:")
for r in LOG:
    print("  ", r)
print("\n".join(R.log))

# ---------------------------------------------------------------- 3. supplies (L4), planes, stitching, silk
import board_finish as bf
SUP = []
bf.route_supplies(B, m, R, SUP)
print("supply links:", sum(1 for s in SUP if s[-1]), "routed,", [s for s in SUP if not s[-1]], "failed")
rf_tr = []
for t in B.GetTracks():
    if t.GetClass() == "PCB_TRACK" and t.GetNetname() in RF and t.GetLayerName() in ("F.Cu", "B.Cu"):
        rf_tr.append((loc(t.GetStart()), loc(t.GetEnd()), pcbnew.ToMM(t.GetWidth())))
        m.rf_keepout([loc(t.GetStart()), loc(t.GetEnd())], pcbnew.ToMM(t.GetWidth()), layer=t.GetLayerName())
bf.planes(B, m)
for z in B.Zones():
    if not z.GetIsRuleArea():
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
# ground vias beside every signal via that changes reference layer (L1/L2 -> L6/L5 or L3)
nb = 0
sig_vias = [t for t in B.GetTracks() if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() in EP or
            isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() in RF]
nst = bf.stitch(B, m, R, rf_tr)
print("GND stitching vias:", nst)
bf.silk(B, m)
pcbnew.ZONE_FILLER(B).Fill(B.Zones())
bl.save_board(B, OUT)
bf.write_pro(OUT.replace(".kicad_pcb", ".kicad_pro"), sorted(RF))


# ---------------------------------------------------------------- 4. rule-10 checks
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
    # L4 zones: contiguous (one filled polygon per rail zone)
    res["L4"] = []
    for z in B.Zones():
        if z.GetIsRuleArea() or not z.IsOnLayer(pcbnew.In3_Cu):
            continue
        fp = z.GetFilledPolysList(pcbnew.In3_Cu)
        res["L4"].append((z.GetNetname(), fp.OutlineCount(), zbox(z)))
    return res


r10 = rule10(B)
print(f"rule 10: fast-net segments on L3: {len(r10['fast_on_L3'])}; L1/L6 samples {r10['samples']}, "
      f"without filled GND on L2/L5: {len(r10['no_ref'])}")
from collections import Counter
for k_, v_ in Counter((a_[0], a_[1]) for a_ in r10["no_ref"]).most_common(20):
    print("   ", k_, v_)
for z_ in r10["L4"]:
    print("   L4 zone", z_)
json.dump({"log": LOG, "fail": R.log, "failed_fast_on_L6": FAILED_FAST, "slow_with_L6_section": SLOW_ON_L6, "rf": RF, "usb": USB, "supply": SUP,
           "stitch": nst, "rule10": {k: (v if k in ("samples", "L4") else len(v)) for k, v in r10.items()},
           "rule10_detail": r10}, open(os.path.join(HERE, "routes.json"), "w"), indent=1)
c = bl.check_board(OUT, rf_widths=RF, verbose=8)
json.dump({k: v for k, v in c.items() if k != "details"}, open(os.path.join(SCR, "check.json"), "w"), indent=1)
json.dump(c["details"], open(os.path.join(SCR, "check_details.json"), "w"), indent=1, default=str)
