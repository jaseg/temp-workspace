#!/usr/bin/env python3
"""PSTROBE block of the scope-fe board: two phase-strobe chains (A from PH_STROBE_P, K from PH_STROBE_N), each
47 R -> 100 nF -> TRF37D73 (bias tee per sim/bias_tee) -> 100 nF -> 10 dB pi pad (100 / 68 / 100 R) -> 100 nF ->
GVA-84+ (VBUS through bead + 2.2 uH) -> 100 nF -> launch node PSTRB_A/K with the 80 ps shorted stub TL402/TL403
(NT402/NT403, two GND vias) and the DNP BAT15 clamp -> 50 R output to the phase block (tap 0).

Both chains come from chain(s): s = +1 chain A (north, local y 0-8.5), s = -1 chain K, mirrored about the
tap axis y = 11.5 (board 37.5).  Every two-terminal part, track, via, stub and keep-out is mirrored; the two
ICs (TRF37D73 WSON, GVA-84+ SOT-89) cannot be mirrored (chiral pin-outs): they keep rotation 0 / 90 in both
chains, with their RF pins on the mirrored line points (identical electrical path).
Run: cd blocks/pstrobe && python3 gen_pstrobe.py
"""
import sys, os, math
sys.path.insert(0, "../..")
import boardlib as bl
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board/pstrobe"
os.makedirs(SCR, exist_ok=True)
BW, BH, AX = 17.0, 25.0, 12.5            # FLOORPLAN 17 x 23 at (9.5, 26.0), grown 1 mm N and S: board (9.5, 25.0)
CORR = (9.5, 15.5)                         # phase corridor (board y 34.5-40.5), not ours
blk = bl.Block("pstrobe")
nl = blk.nl
W = bl.W50
W_PWR, W_GND = 0.5, 0.4
N = bl.net_of
RFPOLY = []
RF = {}


def bplace(ref, x, y, rot=0, side="F"):
    """local helper: Block.place(side="B") segfaults in pcbnew 7.0.11 (flip before Board.Add): place, then flip"""
    fp = blk.place(ref, x, y, rot, "F")
    if side == "B":
        fp.Flip(blk.P(x, y), True)
        fp.Reference().SetLayer(pcbnew.B_Fab)
    return fp


def two(ref, x, y, first, net, side="F"):
    """2-terminal part centred at (x, y); the pad on `net` lies to the `first` side (W/E/N/S)"""
    net = bl.canon(net) if not net.startswith("Net-") else net
    for rot in ((0, 180) if first in "WE" else (90, 270)):
        fp = bplace(ref, x, y, rot, side)
        px, py = blk.pad(ref, "@" + net)
        ok = {"W": px < x - 1e-3, "E": px > x + 1e-3, "N": py < y - 1e-3, "S": py > y + 1e-3}[first]
        if ok:
            return fp
        blk.b.Remove(fp)
        del blk.fps[ref]
    raise ValueError((ref, net))


def gv(x, y):
    blk.via(x, y, "GND")


def rf(net, pts, name, w=W, ch=0.2):
    q = blk.track(net, w, pts, name=name, z=50, ch=ch)
    RFPOLY.append((q, w))
    RF[blk.nl.canon(net) if not net.startswith("Net-") else net] = w
    return q


# chain geometry (chain-A frame, local mm; K = mirror about AX)
YL = 4.40              # RF line (GVA-84+ tab copper reaches YL - 3.95)
YS = YL + 4.85         # stub lane: clears the GVA tab of the mirrored chain K by clamp + gaps
X_IN = 0.52            # input column (iface on the N / S edge)
XR_IN, XC_IN, XT = 1.00, 2.15, 4.30
XFB1, XC_O1 = 6.05, 7.10
XSH1, XSER, XSH2, XC_I2 = 8.10, 9.10, 10.10, 11.10
XG = 14.11             # GVA centre x (pin 1 at XG - 1.5, pin 3 at XG + 1.5)
XO = 16.45             # output column (GVA bead centred on the corner)
L_STUB = 80.0 / bl.PS_MM50


def snap(ref, net, x=None, y=None):
    """move a placed part so that its pad on net lands exactly at x / y"""
    px, py = blk.pad(ref, "@" + net)
    blk.fps[ref].Move(pcbnew.VECTOR2I(bl.mm(0 if x is None else x - px), bl.mm(0 if y is None else y - py)))


def decap(ref, x, y, net, s, side="B"):
    """bulk / spare capacitor: supply pad W with a via pair beside it, GND pad E with a GND via"""
    two(ref, x, y, "W", net, side=side)
    px, py = blk.pad(ref, "@" + net)
    for d in (-0.62, 0.62):
        blk.via(px - 0.35, py + d, net)
    blk.track(net, 0.6, [(px - 0.35, py - 0.62), (px - 0.35, py + 0.62)], layer="B.Cu")
    blk.track(net, 0.6, [(px - 0.35, py), (px, py)], layer="B.Cu")
    gx, gy = blk.pad(ref, "@GND")
    blk.track("GND", W_GND, [(gx, gy), (gx + 0.6, gy)], layer="B.Cu")
    gv(gx + 0.6, gy)


def chain(s):
    A = s > 0
    my = (lambda y: y) if A else (lambda y: 2 * AX - y)
    NS = (lambda d: d) if A else (lambda d: {"N": "S", "S": "N", "W": "W", "E": "E"}[d])
    R_IN, C_IN, U, FB, L, RD, CC, C1N, C100, C10U, CX, C_O, RS1, RSER, RS2, C_I, G, FBG, LG, CG1, CG2, CG10, C_OUT, \
        D, TL, NT, TP1, TP2 = (
            ("R407", "C412", "U403", "FB403", "L403", "R417", "C434", "C415", "C414", "C413", "C432", "C416", "R408",
             "R410", "R409", "C417", "U404", "FB404", "L404", "C418", "C419", "C420", "C421", "D402", "TL402", "NT402",
             "TP403", "TP404") if A else
            ("R411", "C422", "U405", "FB405", "L405", "R418", "C435", "C425", "C424", "C423", "C433", "C426", "R412",
             "R414", "R413", "C427", "U406", "FB406", "L406", "C428", "C429", "C430", "C431", "D403", "TL403", "NT403",
             "TP405", "TP406"))
    PIN = "/PH_STROBE_P" if A else "/PH_STROBE_N"
    OUT = "/PSTRB_A" if A else "/PSTRB_K"
    n_in1, n_rfin, n_rfout, n_bias = N(R_IN, 2), N(U, 2), N(U, 7), N(FB, 2)
    n_padin, n_padout, n_gin, n_gout, n_gbias, n_stub = N(C_O, 2), N(C_I, 1), N(G, 1), N(G, 3), N(FBG, 2), N(NT, 1)
    yl, ys = my(YL), my(YS)
    # ---------------------------------------------------------------- RF line parts
    two(R_IN, XR_IN, yl, "W", PIN)
    two(C_IN, XC_IN, yl, "W", n_in1)
    bplace(U, XT, yl + 0.25, 0)                         # pins 2 / 7 on the line (both chains: rotation 0)
    assert abs(blk.pad(U, "2")[1] - yl) < 1e-6
    two(FB, XFB1, yl - s * 0.48, NS("N"), n_bias)        # bead pad 1 centred on the line, tee away from the stub
    snap(FB, n_rfout, y=yl)
    two(C_O, XC_O1, yl, "W", n_rfout)
    for r_, x_ in ((RS1, XSH1), (RS2, XSH2)):           # pi pad shunts towards the stub side, GND via beyond
        two(r_, x_, yl + s * 0.48, NS("S"), "GND")
        snap(r_, n_padin if r_ == RS1 else n_padout, y=yl)
    two(RSER, XSER, yl, "W", n_padin)
    two(C_I, XC_I2, yl, "W", n_padout)
    bplace(G, XG, yl - 1.95, 90)                        # GVA-84+: pin 1 W, pin 3 E on the line, tab north
    assert abs(blk.pad(G, "1")[1] - yl) < 1e-6 and blk.pad(G, "1")[0] < XG
    two(FBG, XO, yl - s * 0.48, NS("N"), n_gbias)        # GVA bead: pad 1 centred on the corner, tee away
    snap(FBG, n_gout, y=yl)
    two(C_OUT, XO, my(YL + 1.40), NS("N"), n_gout)
    yd = my(YS - 0.53)
    two(D, XO - 1.05, yd, "E", OUT)                     # DNP clamp, pin on the output column
    # ---------------------------------------------------------------- RF tracks
    y0 = 0.0 if A else BH
    rf(PIN, [(X_IN, y0), (R_IN, "@" + PIN)], f"{PIN[1:]} input")
    rf(n_in1, [(R_IN, "@" + n_in1), (C_IN, "@" + n_in1)], f"{U} in 1")
    rf(n_rfin, [(C_IN, "@" + n_rfin), (U, "2")], f"{U} RFIN")
    rf(n_rfout, [(U, "7"), (FB, "1"), (C_O, "@" + n_rfout)], f"{U} RFOUT")
    rf(n_padin, [(C_O, "@" + n_padin), (RS1, "@" + n_padin), (RSER, "@" + n_padin)], f"{U} pad in")
    rf(n_padout, [(RSER, "@" + n_padout), (RS2, "@" + n_padout), (C_I, "@" + n_padout)], f"{U} pad out")
    rf(n_gin, [(C_I, "@" + n_gin), (G, "1")], f"{G} IN")
    rf(n_gout, [(G, "3"), (XO, yl), (C_OUT, "@" + n_gout)], f"{G} OUT", ch=0.3)
    rf(OUT, [(C_OUT, "@" + OUT), (XO, ys), (XO + 0.5, my(YS + 0.5)), (BW, my(YS + 0.5))], f"{OUT[1:]} output")
    q_st, l_st = blk.tline(TL, [(XO, ys), (XO - L_STUB, ys)], W)
    RFPOLY.append((q_st, W))
    RF[OUT] = W
    # stub short: NT pad 1 on the stub end, pad 2 -> two GND vias in a row
    xe = XO - L_STUB
    two(NT, xe - 0.5, ys, "E", n_stub)
    gx, gy = blk.pad(NT, "2")
    blk.track("GND", W_GND, [(gx, gy), (gx - 1.3, gy)])
    gv(gx - 0.62, gy)
    gv(gx - 1.3, gy)
    # clamp GND -> via west of its pad
    x, y = blk.pad(D, "@GND")
    blk.track("GND", W_GND, [(x, y), (x - 0.72, y)])
    gv(x - 0.72, y)
    for r in (RS1, RS2):
        x, y = blk.pad(r, "@GND")
        blk.track("GND", W_GND, [(x, y), (x, y + s * 0.62)])
        gv(x, y + s * 0.62)
    # ---------------------------------------------------------------- TRF GND pins -> EP, EP vias
    xu, yu = blk.loc(blk.fps[U].GetPosition())
    for pn in ("3", "4", "5", "6", "8"):
        x, y = blk.pad(U, pn)
        blk.track("GND", 0.25, [(x, y), (xu, y)])
    for dy in (-0.55, 0.0, 0.55):
        gv(xu, yu + dy)
    # ---------------------------------------------------------------- TRF VCC (pin 1 is north in both chains)
    p1 = blk.pad(U, "1")
    xa, xb = 2.62, 1.62
    yc = p1[1] - 1.40
    two(C1N, xa, yc, "S", "+3V3")
    two(C100, xb, yc, "S", "+3V3")
    c1 = blk.pad(C1N, "@+3V3")
    blk.track("+3V3", 0.25, [p1, (p1[0] - 0.40, p1[1]), (c1[0], p1[1] - (p1[0] - 0.40 - c1[0])), c1])
    c2 = blk.pad(C100, "@+3V3")
    blk.track("+3V3", W_PWR, [c1, c2])
    for c in (C1N, C100):
        x, y = blk.pad(c, "@GND")
        blk.track("GND", W_GND, [(x, y), (x, y - 0.55)])
        gv(x, y - 0.55)
    vv = [(c2[0] - 0.05, c2[1] + 0.62), (c1[0] - 0.05, c2[1] + 0.62)]
    for v in vv:
        blk.via(*v, "+3V3")
        blk.track("+3V3", W_PWR, [(v[0], c2[1]), v])
    # 10 uF + spare 100 nF on B.Cu under the pin-1 caps
    two(C10U, 1.62, yc - 0.15, "S", "+3V3", side="B")
    ct = blk.pad(C10U, "@+3V3")
    blk.track("+3V3", 0.6, [ct, (ct[0], vv[0][1])], layer="B.Cu")
    blk.track("+3V3", 0.6, [vv[0], vv[1]], layer="B.Cu")
    gb = blk.pad(C10U, "@GND")
    blk.track("GND", 0.6, [gb, (gb[0], gb[1] - 0.5)], layer="B.Cu")
    two(CX, 3.55, vv[1][1], "W", "+3V3", side="B")
    blk.track("+3V3", 0.5, [vv[1], blk.pad(CX, "@+3V3")], layer="B.Cu")
    x, y = blk.pad(CX, "@GND")
    blk.track("GND", W_GND, [(x, y), (x + 0.55, y)], layer="B.Cu")
    gv(x + 0.55, y)
    # ---------------------------------------------------------------- TRF bias tee on B.Cu (straight chain)
    pb = blk.pad(FB, "2")
    yt = my(1.60 + 1.0)
    blk.track(n_bias, 0.5, [pb, (pb[0], yt)])
    blk.via(pb[0], yt, n_bias)
    two(L, pb[0] + 1.40, yt, "W", n_bias, side="B")      # pad 1 over the via
    lc = blk.pad(L, "@+3V3")
    two(CC, lc[0] + 1.45, yt, "W", "+3V3", side="B")      # cold-pad 100 nF along the chain
    cc = blk.pad(CC, "@+3V3")
    blk.track("+3V3", 0.64, [lc, cc], layer="B.Cu")
    g = blk.pad(CC, "@GND")
    blk.track("GND", W_GND, [g, (g[0], g[1] + s * 0.65)], layer="B.Cu")
    gv(g[0], g[1] + s * 0.65)
    for d in (-0.75, 0.75):                               # +3V3 enters through the capacitor pad
        blk.via(cc[0], cc[1] + d, "+3V3")
    blk.track("+3V3", 0.56, [(cc[0], cc[1] - 0.75), (cc[0], cc[1] + 0.75)], layer="B.Cu")
    two(RD, pb[0] + 1.40, my(1.0), "W", n_bias, side="B")   # 1 k beside the 1210 (outer side)
    r1, r2 = blk.pad(RD, "@" + n_bias), blk.pad(RD, "@+3V3")
    l1 = blk.pad(L, "@" + n_bias)
    blk.track(n_bias, 0.4, [r1, (l1[0] + 0.35, r1[1]), (l1[0], r1[1] + s * 0.35), l1], layer="B.Cu")
    blk.track("+3V3", 0.4, [r2, (lc[0] - 0.35, r2[1]), (lc[0], r2[1] + s * 0.35), lc], layer="B.Cu")
    bplace(TP1, pb[0] - 1.35, yt, 0, "B")
    blk.track(n_bias, 0.4, [blk.pad(TP1, "1"), (pb[0], yt)], layer="B.Cu")
    # ---------------------------------------------------------------- GVA GND tab vias
    xg_, yg_ = blk.loc(blk.fps[G].GetPosition())
    for dx in (-0.45, 0.45):
        for dy in (-1.2, 0.0):
            gv(xg_ + dx, yg_ + dy)
    # ---------------------------------------------------------------- GVA bias tee on B.Cu (VBUS)
    pg = blk.pad(FBG, "2")
    yv = my(2.55)
    blk.track(n_gbias, 0.5, [pg, (XO, yv)])
    blk.via(XO, yv, n_gbias)
    two(LG, XO - 0.10, my(1.50), NS("S"), n_gbias, side="B")   # 2.2 uH straight on from the bead via
    snap(LG, n_gbias, y=yv)
    lv = blk.pad(LG, "@VBUS")
    two(CG1, lv[0] - 1.45, lv[1], "E", "VBUS", side="B")         # cold-pad caps across the VBUS pad
    c1v = blk.pad(CG1, "@VBUS")
    blk.track("VBUS", 0.64, [lv, c1v], layer="B.Cu")
    g = blk.pad(CG1, "@GND")
    blk.track("GND", W_GND, [g, (g[0] - 0.6, g[1])], layer="B.Cu")
    gv(g[0] - 0.6, g[1])
    for d in (0.55, 1.25):                                       # VBUS enters through the capacitor pad
        blk.via(c1v[0], c1v[1] + s * d, "VBUS")
    blk.track("VBUS", 0.6, [c1v, (c1v[0], c1v[1] + s * 1.25)], layer="B.Cu")
    bplace(TP2, XO, my(3.75), 0, "B")
    blk.track(n_gbias, 0.4, [(XO, yv), blk.pad(TP2, "1")], layer="B.Cu")
    decap(CG2, 12.75, my(YL + 1.75), "VBUS", s)
    decap(CG10, 12.95, my(YL + 3.45), "VBUS", s)
    return {"stub": l_st, "out": blk.route_len(f"{OUT[1:]} output"), "in": blk.route_len(f"{PIN[1:]} input")}


RES = {"A": chain(+1), "K": chain(-1)}

# ============================================================================= pours, keep-outs
IN = 0.15
REG = {"A": bl.rect_pts(IN, IN, BW - IN, CORR[0] - IN), "K": bl.rect_pts(IN, CORR[1] + IN, BW - IN, BH - IN)}
for r in REG.values():
    blk.zone("GND", ["In1.Cu"], r, clearance=0.2, prio=0)
    blk.zone("GND", ["F.Cu"], r, clearance=0.25, prio=0)
    blk.zone("GND", ["B.Cu"], r, clearance=0.25, prio=0)
for q, w in RFPOLY:
    blk.rf_keepout(q, w, gap=2 * w + 0.03)

# ============================================================================= interfaces, outline
blk.iface("PH_STROBE_P", X_IN, 0.0, "F.Cu", "N", "pair", W, "chain A input, R407 47 R here; FPGA U501")
blk.iface("PH_STROBE_N", X_IN, BH, "F.Cu", "S", "pair", W, "chain K input (mirror), R411 47 R here; match P/N")
blk.iface("PSTRB_A", BW, 9.75, "F.Cu", "E", "rf50", W, "to phase tap 0 (phase iface 26.5 / 34.75 board)")
blk.iface("PSTRB_K", BW, 15.25, "F.Cu", "E", "rf50", W, "to phase tap 0 (phase iface 26.5 / 40.25 board)")
blk.iface("+3V3", 0, 0, "In2.Cu", "-", "supply", None, "TRF VCC and bias tees: via pairs, In2 island x 0-12")
blk.iface("VBUS", 0, 0, "In2.Cu", "-", "supply", None, "GVA-84+ tees: via pairs at C418 / C428, In2 x 10-15")
blk.edge_rect(0, 0, BW, BH, layer="Dwgs.User")
blk.line(0, CORR[0], BW, CORR[0], layer="Dwgs.User")
blk.line(0, CORR[1], BW, CORR[1], layer="Dwgs.User")
blk.text("PSTROBE A", 6.0, 7.6, 0.4, "F.SilkS")
blk.text("PSTROBE K", 6.0, 17.4, 0.4, "F.SilkS")
for fp_ in blk.fps.values():
    for g_ in fp_.GraphicalItems():
        if g_.GetClass() in ("FP_TEXT", "PCB_TEXT"):
            g_.SetTextSize(pcbnew.VECTOR2I(bl.mm(0.3), bl.mm(0.3)))
            g_.SetTextThickness(bl.mm(0.05))
out = blk.save(HERE)

# ============================================================================= tables
print(f"block {BW} x {BH} mm at board (9.5, 25.0); lines at local y {YL} / {2 * AX - YL}")
print(f"{'route':28s} {'w':>5s} {'mm':>7s} {'ps':>6s}")
for nm in blk.routes:
    if blk.routes[nm]["z"]:
        L_ = blk.route_len(nm)
        print(f"{nm:28s} {blk.routes[nm]['width']:5.2f} {L_:7.3f} {L_ * bl.PS_MM50:6.1f}")
for k, r in RES.items():
    print(f"chain {k}: stub {r['stub']:.3f} mm = {r['stub'] * bl.PS_MM50:.1f} ps; output (C421/C431 pad -> edge) "
          f"{r['out']:.3f} mm; input (edge -> 47 R) {r['in']:.3f} mm")
dA = abs(RES["A"]["out"] - RES["K"]["out"])
print(f"A/K output mismatch {dA * 1e3:.1f} um")
assert dA < 0.05

# ============================================================================= checks
import floorplan as fpl
mem = fpl.membership(nl)
ANALOG_TOOK = ("C402", "C403", "C404", "C407", "C408", "C409")
REFS = sorted(r for r, b_ in mem.items() if b_ == "pstrobe" and r not in ANALOG_TOOK)
res = bl.check_board(out, refs=REFS, rf_widths=RF, verbose=12)

_bb = pcbnew.LoadBoard(out).ComputeBoundingBox(False)
_ox, _oy = pcbnew.ToMM(_bb.GetX()), pcbnew.ToMM(_bb.GetY())


def render(png, layers, crop):
    """local helper: kicad-cli page-size-mode 2 puts the SVG origin at the board bbox; shift the crop (local mm)"""
    x0, y0, x1, y1 = crop
    o = (100.0 - _ox, 100.0 - _oy)
    bl.render(out, png, layers, crop=(x0 + o[0], y0 + o[1], x1 + o[0], y1 + o[1]), tmpdir=SCR)


if "--norender" not in sys.argv:
    lay = ("F.Cu", "B.Cu", "F.SilkS", "F.Fab", "Dwgs.User")
    render(os.path.join(HERE, "pstrobe.png"), lay, (-0.5, -0.5, 17.5, 25.5))
    render(os.path.join(HERE, "pstrobe_detail.png"), lay, (9.5, -0.3, 17.3, 10.3))
    render(os.path.join(SCR, "pstrobe_f.png"), ("F.Cu", "F.Fab", "Dwgs.User"), (-0.5, -0.5, 17.5, 25.5))
    render(os.path.join(SCR, "pstrobe_b.png"), ("B.Cu", "B.Fab", "Dwgs.User"), (-0.5, -0.5, 17.5, 25.5))
