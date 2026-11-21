#!/usr/bin/env python3
"""Integrated scope-fe board: merge the six blocks, route the inter-block nets, planes, stitching, silk.

Run:  cd design/lowcost/layout/board && python3 gen_board.py [--render]
Writes scope-fe.kicad_pcb + scope-fe.kicad_pro (KiCad 7.0.11 format) and, with --render, the PNGs.
"""
import os, sys, json, math, glob
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
import pcbnew
import boardlib as bl
import boardroute as br

W, H = 100.0, 57.0
POS = {"analog": (0.0, 1.0), "phase": (0.0, 22.5), "pstrobe": (9.5, 25.0), "fpga": (56.0, 0.5),
       "power": (74.0, 0.0), "mcuif": (27.0, 45.0)}
OUT = os.path.join(HERE, "scope-fe.kicad_pcb")
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board/int"
os.makedirs(SCR, exist_ok=True)

m = bl.new_master(W, H)
B = m.b
for fp in B.GetFootprints():                       # mounting holes: board-only (no schematic symbol)
    if fp.GetReference().startswith("H"):
        fp.SetBoardOnly(True)
        fp.Value().SetVisible(False)
        fp.Reference().SetVisible(False)
for k, (x, y) in POS.items():
    bl.merge(B, f"blocks/{k}/{k}.kicad_pcb", x, y)


def loc(v):
    return round(pcbnew.ToMM(v.x) - bl.ORG[0], 4), round(pcbnew.ToMM(v.y) - bl.ORG[1], 4)


# ---------------------------------------------------------------- planes owned by the integrator
for z in list(B.Zones()):
    if z.GetIsRuleArea():
        continue
    if z.GetNetname() == "GND" and z.IsOnLayer(pcbnew.In1_Cu):
        B.Remove(z)                                # replaced by one board-wide In1 plane below
    elif z.GetNetname() == "+3V3" and z.IsOnLayer(pcbnew.In2_Cu):
        B.Remove(z)                                # fpga's In2 +3V3: replaced by the board partition

for z in B.Zones():                                # isolated pour slivers (e.g. the mcuif's 8) are removed
    if not z.GetIsRuleArea():
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)

# ---------------------------------------------------------------- interfaces -> route end points
IF = {}
for k in POS:
    d = json.load(open(f"blocks/{k}/{k}.ifaces.json"))
    for i in d["ifaces"]:
        if i["class"] == "supply" and i["layer"].startswith("In2"):
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


def endpoint(net, i, strip=True):
    """route end point for an interface: the via behind a straight stub (stub deleted) or the stub end"""
    x, y, ly = i["bx"], i["by"], i["layer"]
    ts = tracks_at(net, x, y, ly)
    if not ts:
        return (x, y, ly, "*")
    t, (ox, oy) = ts[0]
    if strip and via_at(net, ox, oy) is not None and len(tracks_at(net, ox, oy, ly)) == 1 and \
            (math.hypot(x - ox, y - oy) < 2.5 or i["block"] == "analog"):
        B.Remove(t)
        return (ox, oy, "*", "*")
    return (x, y, ly, compass(x - ox, y - oy))


def trim(net, x, y, layer, length):
    """shorten the stub ending at (x, y) by length; returns the new end point spec"""
    t, (ox, oy) = tracks_at(net, x, y, layer)[0]
    L = math.hypot(x - ox, y - oy)
    u = max(0.0, (L - length) / L)
    nx, ny = round(ox + (x - ox) * u, 4), round(oy + (y - oy) * u, 4)
    if u <= 0.0:
        B.Remove(t)
    else:
        if loc(t.GetStart()) == (x, y):
            t.SetStart(m.P(nx, ny))
        else:
            t.SetEnd(m.P(nx, ny))
    return (nx, ny, layer, compass(x - ox, y - oy))


R = br.Router(m, W, H)
LOG = []


def rt(net, a, b, **kw):
    r = R.route(net, a, b, **kw)
    L = sum(bl.plen(p) for _, p in r) if r else None
    LOG.append((bl.canon(net), None if L is None else round(L, 3), None if not r else len(r) - 1))
    return r


# ---------------------------------------------------------------- 1. RF / matched nets on F.Cu
RF = {}
# S_STROBE_P / N and PSTRB_A / K: the block interfaces abut (analog / fpga, pstrobe / phase): nothing to route
# PH_STROBE_P / N: fpga W -> pstrobe N (P) / S (N); the fpga stubs end on the analog R405 / C411 column, so
# they are cut back to their last bend
for net in ("/PH_STROBE_P", "/PH_STROBE_N"):
    pass
for t, o in tracks_at("/PH_STROBE_N", 56.0, 13.1, "F.Cu") + tracks_at("/PH_STROBE_P", 56.0, 13.58, "F.Cu"):
    B.Remove(t)
# the pstrobe inputs are boxed in on F.Cu by the phase block's C301 / C306 row (P) - both strobes drop to
# B.Cu through one via each right at the pstrobe interface (same via count on P and N)
vp = m.via(10.02, 25.1, "/PH_STROBE_P"); R.add_item(vp)
m.track("/PH_STROBE_P", bl.W50, [(10.02, 25.0), (10.02, 25.1)], "F.Cu")
vn = m.via(10.02, 49.9, "/PH_STROBE_N"); R.add_item(vn)
m.track("/PH_STROBE_N", bl.W50, [(10.02, 50.0), (10.02, 49.9)], "F.Cu")
php = (57.9, 13.58, "F.Cu", "SW")
phn = (57.25, 13.1, "F.Cu", "SW")
for net, a, b in (("/PH_STROBE_N", phn, (10.02, 49.9, "*", "*")), ("/PH_STROBE_P", php, (10.02, 25.1, "*", "*"))):
    r = rt(net, a, b, w=bl.W50, layers=("F.Cu", "B.Cu"), clr=0.2, via_cost=6.0, margin=12, maxn=3_000_000)
RF["/PH_STROBE_P"] = RF["/PH_STROBE_N"] = bl.W50

# BUF_OUT_T: analog S (15.75, 22.5) -> phase N (8.79, 22.5), 50 R on F.Cu
a, b = [endpoint("/BUF_OUT_T", i, strip=False) for i in IF["/BUF_OUT_T"]]
rt("/BUF_OUT_T", a, b, w=bl.W50, layers=("F.Cu",), clr=0.3)
RF["/BUF_OUT_T"] = bl.W50

# fpga SPI / I2C / MCU_CLK comb (0.25 mm pitch at the S edge): continue the comb straight down into the free
# B.Cu strip of the phase block with staggered ends (east line ends first) so that every line can turn off
COMB = ["/SPI_SCK", "/SPI_MOSI", "/SPI_MISO", "/SPI_CS", "/MCU_CLK", "/I2C_SDA", "/I2C_SCL"]
COMB_END = {}
for k, net in enumerate(COMB):
    i = [i for i in IF[net] if i["block"] == "fpga"][0]
    x, y = i["bx"], i["by"]
    ye = round(23.0 + (len(COMB) - 1 - k) * 0.5, 3)
    m.track(net, i["width"] or 0.12, [(x, y), (x, ye)], "B.Cu")
    COMB_END[net] = (x, ye, "B.Cu", "S")
for t in B.GetTracks():
    if t.GetNetname() in COMB:
        R.add_item(t)

# ---------------------------------------------------------------- 2. slow nets (B.Cu, In2 where needed)
SLOW = sorted(n for n, v in IF.items() if len({i["block"] for i in v}) >= 2 and n not in RF and
              all(i["class"] in ("slow", "supply") for i in v) and "STROBE" not in n and "USB" not in n)
taps = [n for n in SLOW if "/TAP" in n] + ["/COARSE"]
rest = [n for n in SLOW if n not in taps]
# channel plan: TAP0..15 + COARSE on In2 only, in the band y 20.5..27.0 (under the fpga pin row, the analog /
# phase seam and the comparator row); everything that crosses the phase block runs on B.Cu in the free columns
# between the tap cells and hops the VTH rail (B.Cu, y 28.9) on In2 in the band y 27.4..32.0
TAP_AVOID = [("In2.Cu", 0, 0, W, 20.5), ("In2.Cu", 0, 27.0, W, H)]
X_AVOID = [("In2.Cu", 0, 0, W, 21.0), ("In2.Cu", 61.5, 21.0, 94.0, 23.8), ("In2.Cu", 0, 45.0, W, H), ("B.Cu", 0, 22.5, 9.5, 45.0)]
first = [n for n in rest if "JTAG" in n or "DBG" in n] + [n for n in reversed(COMB) if n in rest]
ANA = [n for n in rest if n in ("/VOFS", "/VNEG_REF", "/VBIAS_A", "/VBIAS_K", "/ADC_IN", "/ADC_REF_MID")]
order = [f"/TAP{k}" for k in (0, 1, 2, 3, 4, 5, 7, 6, 8, 9, 15, 14, 13, 12, 11, 10)] + ["/COARSE"] + ANA + first + \
    [n for n in rest if n not in first and n not in ANA]
# explicit In2 lanes for the far west taps (nested ribbon: TAP0 on top), w 0.1 / pitch 0.2
LANE_W = 0.1
for k in range(6):
    net = f"/TAP{k}"
    ef = [i for i in IF[net] if i["block"] == "fpga"][0]
    ep = [i for i in IF[net] if i["block"] == "phase"][0]
    a = endpoint(net, ef)
    b = endpoint(net, ep)
    fx, fy = a[0], a[1]
    px, py = b[0], b[1]
    Y = round(21.55 + 0.2 * k, 3)
    c = 0.2
    pts = [(fx, fy), (fx, Y - c), (fx - c, Y), (px + (py - Y), Y), (px, py)]
    m.track(net, LANE_W, pts, "In2.Cu", ch=0.0)
    for p, q in zip(pts, pts[1:]):
        R.mark_seg("In2.Cu", p[0], p[1], q[0], q[1], LANE_W / 2, m.net(net).GetNetCode())
    LOG.append((net, round(bl.plen(pts), 3), 0))
    order.remove(net)
# explicit In2 lanes for the east taps 10..15 (nested ribbon, TAP15 on top), below the power block's In2 vias
for k in range(10, 16):
    net = f"/TAP{k}"
    ef = [i for i in IF[net] if i["block"] == "fpga"][0]
    ep = [i for i in IF[net] if i["block"] == "phase"][0]
    a = endpoint(net, ef)
    b = endpoint(net, ep)
    fx, fy = a[0], a[1]
    px, py = b[0], b[1]
    Y = round(22.55 + 0.2 * (15 - k), 3)
    c = 0.2
    pts = [(fx, fy), (fx, Y - c), (fx + c, Y), (px - (py - Y), Y), (px, py)]
    m.track(net, LANE_W, pts, "In2.Cu", ch=0.0)
    for p, q in zip(pts, pts[1:]):
        R.mark_seg("In2.Cu", p[0], p[1], q[0], q[1], LANE_W / 2, m.net(net).GetNetCode())
    LOG.append((net, round(bl.plen(pts), 3), 0))
    order.remove(net)
for net in order:
    v = IF[net]
    if len(v) != 2:
        print("skip", net, len(v))
        continue
    w = max(i["width"] or 0.15 for i in v)
    w = min(w, 0.4)
    a, b = [endpoint(net, i) for i in v]
    if net in COMB_END:
        w = 0.12
        a, b = [COMB_END[net] if i["block"] == "fpga" else e for i, e in zip(v, (a, b))]
    if net in taps:
        kw = dict(w=0.1, layers=("In2.Cu",) if a[2] == "*" and b[2] == "*" else ("B.Cu", "In2.Cu"),
                  lcost={"B.Cu": 3.0}, via_cost=1.5, clr=0.1, avoid=TAP_AVOID)
    else:
        kw = dict(w=w, layers=("B.Cu", "In2.Cu"), lcost={"In2.Cu": 1.5}, via_cost=1.0, clr=0.15, avoid=X_AVOID)
    if net == "/COARSE":
        kw = dict(w=w, layers=("B.Cu",), clr=0.15)
    if rt(net, a, b, margin=6, maxn=200_000, **kw) is None:
        LOG.pop()
        if rt(net, a, b, margin=25, maxn=600_000, **kw) is None:
            LOG.pop()
            kw2 = dict(kw, layers=("B.Cu", "In2.Cu"), avoid=[("In2.Cu", 61.5, 21.0, 94.0, 23.8)])
            if net in taps or net == "/COARSE":
                kw2["layers"] = ("B.Cu", "In2.Cu")
            rt(net, a, b, margin=40, maxn=1_500_000, **kw2)

bl.save_board(B, os.path.join(SCR, "routed.kicad_pcb"))
json.dump({"log": LOG, "fail": R.log, "rf": RF}, open(os.path.join(SCR, "routed.json"), "w"), indent=1)
print("routes:")
for r in LOG:
    print("  ", r)
print("\n".join(R.log))

# ---------------------------------------------------------------- 3. supplies, planes, stitching, silk
import board_finish as bf
SUP = []
bf.route_supplies(B, m, R, SUP)
print("supply links:", sum(1 for s in SUP if s[-1]), "routed,", [s for s in SUP if not s[-1]], "failed")
rf_tr = []
for t in B.GetTracks():
    if t.GetClass() == "PCB_TRACK" and t.GetNetname() in RF and t.GetLayerName() == "F.Cu":
        rf_tr.append((loc(t.GetStart()), loc(t.GetEnd()), pcbnew.ToMM(t.GetWidth())))
for p0, p1, w_ in rf_tr:                         # F.Cu pour keep-out 2 w around the inter-block RF lines
    m.rf_keepout([p0, p1], w_)
bf.planes(B, m)
nst = bf.stitch(B, m, R, rf_tr)
print("GND stitching vias:", nst)
bf.silk(B, m)
pcbnew.ZONE_FILLER(B).Fill(B.Zones())
bl.save_board(B, OUT)
bf.write_pro(OUT.replace(".kicad_pcb", ".kicad_pro"), sorted(RF))
json.dump({"log": LOG, "fail": R.log, "rf": RF, "supply": SUP, "stitch": nst},
          open(os.path.join(HERE, "routes.json"), "w"), indent=1)
nref, badref = bf.in2_reference_check(B)
print(f"rule 10 In2 GND reference under B.Cu clock / fast nets: {nref} samples, {len(badref)} violations")
from collections import Counter
for k_, v_ in Counter((b_[0], b_[3]) for b_ in badref).most_common(30):
    print("   ", k_, v_)
json.dump(badref, open(os.path.join(SCR, "in2ref.json"), "w"))
c = bl.check_board(OUT, rf_widths=RF, verbose=8)
json.dump({k: v for k, v in c.items() if k != "details"}, open(os.path.join(SCR, "check.json"), "w"), indent=1)
json.dump(c["details"], open(os.path.join(SCR, "check_details.json"), "w"), indent=1)
