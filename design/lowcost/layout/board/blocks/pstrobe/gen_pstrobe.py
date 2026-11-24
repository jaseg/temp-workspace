#!/usr/bin/env python3
"""PSTROBE block of the scope-fe board: two phase-strobe chains (A from PH_STROBE_P, K from PH_STROBE_N), each
47 R -> 100 nF -> TRF37D73 (bias tee per sim/bias_tee) -> 100 nF -> 10 dB pi pad (100 / 68 / 100 R) -> 100 nF ->
GVA-84+ (VBUS through bead + 2.2 uH) -> 100 nF -> launch node PSTRB_A/K with the 80 ps shorted stub TL402/TL403
(NT402/NT403, two GND vias) and the DNP BAT15 clamp -> 50 R output to the phase block (tap 0).

Both chains come from chain(s): s = +1 chain A (north, local y 0-8.5), s = -1 chain K, mirrored about the
tap axis y = 12.5 (board 37.5).  Every two-terminal part, track, via, stub and keep-out is mirrored; the two
ICs (TRF37D73 WSON, GVA-84+ SOT-89) cannot be mirrored (chiral pin-outs): they keep rotation 0 / 90 in both
chains, with their RF pins on the mirrored line points (identical electrical path).
Run: cd blocks/pstrobe && python3 gen_pstrobe.py
"""
import sys, os, math
sys.path.insert(0, "../..")
os.environ["BL_STACKUP"] = "6L"            # phase two: native 6-layer block (JLC06161H-3313, RULES rule 10)
import boardlib as bl
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board6/pstrobe"
os.makedirs(SCR, exist_ok=True)
BW, BH, AX = 17.0, 25.0, 12.5            # FLOORPLAN 17 x 23 at (9.5, 26.0), grown 1 mm N and S: board (9.5, 25.0)
CORR = (9.5, 15.5)                         # phase corridor (board y 34.5-40.5), not ours
blk = bl.Block("pstrobe")
nl = blk.nl
W = bl.W50                                 # 6L: 0.16 mm (50.2 R, L1 over L2 0.0994 mm 3313)
assert bl.STACKUP_NAME == "6L" and abs(W - 0.16) < 1e-9, W
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


# chain geometry (chain-A frame, local mm; K = mirror about AX).  Courtyards (KiCad library) never overlap:
# 0402 1.86 x 0.94, WSON-8 3.2 x 2.5, SOT-89 5.0 x 5.1 (tab side 4.2 from the line), SOD-323 3.2 x 1.9.
YL = 4.40              # RF line (GVA-84+ tab copper reaches YL - 3.95, its courtyard YL - 4.2)
YS = YL + 4.85         # stub lane: K stub edge 0.72 (2 w) from the GVA tab copper of chain K
X_IN = 0.52            # input leg column (iface on the N / S edge); R407 and C412 sit on the leg
XT = 2.74              # TRF37D73 centre x (courtyard touches the leg parts' courtyards)
X1 = XT + 1.60 + 0.47  # TRF bias bead on the corner, C416 below it (first column of the U-folded pi pad)
YR = YL + 2.55         # U row: R410 series, R408 / R409 shunts inside the U
XRS1 = X1 + 1.29       # first shunt R408 / R412 (0603 since 24 Nov) and series pad 1 column
XRS2 = XRS1 + 1.20     # second shunt (0402) column: its courtyard touches the 0603's
X2 = XRS2 + 0.95       # second column: C417 (courtyard touches the second shunt's); U 0.45 mm wider than in 0402
XO = 14.60             # output column: GVA bead on the corner, C421 below, launch node at YS
XG = XO - 1.47 - 1.50  # GVA centre x (pin 3 at XO - 1.47: courtyard edge = bead courtyard edge)
DL = 1.00              # TRF bias-tee choke offset east of the bead via (24 Nov, BIASTEE-6)
XD = XO + 0.47 + 0.95  # clamp column (vertical SOD-323 beside C421)
# RF-2 (24 Nov): the shorted end is NT pad 1 -> 1.0 mm net-tie bar (0.5 mm wide over L2) -> GND via IN NT pad 2
# (net-tie pads carry no paste, so the via is not a solder trap) -> L2.  Its inductance is counted as stub delay
# (dt = L / Z0) and the drawn stub is shortened by it so the stub is 80 ps electrically.
Z_TIE, EE_TIE = bl.microstrip_6l(0.5)
L_TIE_PH = Z_TIE * math.sqrt(EE_TIE) / bl.C0 * 1.0              # pH (ohm * ps/mm * mm)
H_VIA = bl.STACKUPS["6L"]["H"] + 0.035 / 2 + 0.0152 / 2        # L1 centre to L2, mm
L_VIA_PH = 200.0 * H_VIA * (math.log(4 * H_VIA / 0.2) + 1)     # pH (0.2 h (ln(4h/d) + 1) nH, mm)
DT_SHORT = (L_TIE_PH + L_VIA_PH) / 50.0                         # ps
L_STUB = (80.0 - DT_SHORT) / bl.PS_MM50
XR_IN, YR_IN = 2.30, YL + 2.00   # 47 R (horizontal, under the TRF courtyard) centre; PH_STROBE pad east
XV2, XG2 = 3.45, 4.10            # L6 -> L1 return via and its GND via on the 47 R row
# PH_STROBE entries on the NORTH edge (TOPOLOGY section 4), both chains: P (chain A) west, N (chain K) east
X_P, X_N = 0.50, 1.10            # board x 10.00 / 10.60 at board y 25.00
X_KC = 2.37                      # K line L6 column under the corridor: phase C309 / vias end at local x 1.79,
                                 # L302 pad 2 starts at 2.95 (blocks/phase B.Cu, board x 11.29..12.45 clear)


def snap(ref, net, x=None, y=None):
    """move a placed part so that its pad on net lands exactly at x / y"""
    px, py = blk.pad(ref, "@" + net)
    blk.fps[ref].Move(pcbnew.VECTOR2I(bl.mm(0 if x is None else x - px), bl.mm(0 if y is None else y - py)))


def chain(s):
    A = s > 0
    my = (lambda y: y) if A else (lambda y: 2 * AX - y)
    NS = (lambda d: d) if A else (lambda d: {"N": "S", "S": "N", "W": "W", "E": "E"}[d])
    R_IN, C_IN, U, FB, L, RD, CC, C1N, C100, C10U, CX, C_O, RS1, RSER, RS2, C_I, G, FBG, LG, CG1, CG2, CG10, C_OUT, \
        D, TL, NT, TP1, TP2, RG = (
            ("R407", "C412", "U403", "FB403", "L403", "R417", "C434", "C415", "C414", "C413", "C432", "C416", "R408",
             "R410", "R409", "C417", "U404", "FB404", "L404", "C418", "C419", "C420", "C421", "D402", "TL402", "NT402",
             "TP403", "TP404", "R419") if A else
            ("R411", "C422", "U405", "FB405", "L405", "R418", "C435", "C425", "C424", "C423", "C433", "C426", "R412",
             "R414", "R413", "C427", "U406", "FB406", "L406", "C428", "C429", "C430", "C431", "D403", "TL403", "NT403",
             "TP405", "TP406", "R420"))
    PIN = "/PH_STROBE_P" if A else "/PH_STROBE_N"
    OUT = "/PSTRB_A" if A else "/PSTRB_K"
    n_in1, n_rfin, n_rfout, n_bias = N(R_IN, 2), N(U, 2), N(U, 7), N(FB, 2)
    n_padin, n_padout, n_gin, n_gout, n_gbias, n_stub = N(C_O, 2), N(C_I, 1), N(G, 1), N(G, 3), N(FBG, 2), N(NT, 1)
    yl, ys, yr = my(YL), my(YS), my(YR)
    # ---------------------------------------------------------------- RF parts
    # input leg BELOW the line (toward the axis): C412 vertical (pad 2 just below the line), 47 R horizontal
    # under the TRF with its PH_STROBE pad east -> return via VA2 / VK2 (the north-west corner is free for the
    # two PH_STROBE entries and their L6 dive vias, TOPOLOGY section 4)
    # (A only: in K the TRF's pin-1 caps, which cannot be mirrored, occupy the axis side, and the K leg keeps
    #  its column toward the south edge, which no longer carries an entry; equal length is solved to TRF pin 2)
    if A:
        two(C_IN, X_IN, YL + 1.00, "N", n_rfin)
        two(R_IN, XR_IN, YR_IN, "E", PIN)
    else:
        two(C_IN, X_IN, my(YL - 1.00), "N", n_rfin)
        two(R_IN, X_IN, my(YL - 2.87), "S", PIN)
    bplace(U, XT, yl + 0.25, 0)                          # pins 2 / 7 on the line (both chains: rotation 0)
    assert abs(blk.pad(U, "2")[1] - yl) < 1e-6
    two(FB, X1, yl - s * 0.48, NS("N"), n_bias)          # bead pad 1 centred on the corner, body away from the stub
    snap(FB, n_rfout, y=yl)
    two(C_O, X1, my(YL + 1.40), NS("N"), n_rfout)        # DC block down the first column
    two(RSER, XRS1 + 0.51, yr, "W", n_padin)             # pi pad series 68 R on the U row
    two(RS1, XRS1, my(YR - 1.95), NS("S"), n_padin)      # 0603 shunt above series pad 1, inside the U
    two(RS2, XRS2, my(YR - 1.42), NS("S"), n_padout)     # 0402 shunt; its node track drops into series pad 2
    two(C_I, X2, my(YL + 1.40), NS("S"), n_padout)       # DC block up the second column
    bplace(G, XG, yl - 1.95, 90)                         # GVA-84+: pin 1 W, pin 3 E on the line, tab north
    assert abs(blk.pad(G, "1")[1] - yl) < 1e-6 and blk.pad(G, "1")[0] < XG
    two(FBG, XO, yl - s * 0.48, NS("N"), n_gbias)        # GVA bead: pad 1 centred on the corner, body away
    snap(FBG, n_gout, y=yl)
    two(C_OUT, XO, my(YL + 1.40), NS("N"), n_gout)
    two(D, XD, my(YS - 1.35), NS("S"), OUT)              # DNP clamp: cathode pad on the output row's edge
    # ---------------------------------------------------------------- RF tracks
    # L1 return segment of the PH_STROBE input: 47 R pad -> via (L6 -> L1), GND via beside it (mirrored)
    v2, g2 = ((XV2, YR_IN), (XG2, YR_IN)) if A else ((X_IN, BH - 0.40), (1.15, BH - 0.40))
    rf(PIN, [(R_IN, "@" + PIN), v2], f"{PIN[1:]} L1 return")
    blk.via(*v2, PIN)
    gv(*g2)
    if A:
        rf(n_in1, [(C_IN, "@" + n_in1), (X_IN, YR_IN - 0.20), (X_IN + 0.20, YR_IN), (R_IN, "@" + n_in1)], f"{U} in 1")
    else:
        rf(n_in1, [(R_IN, "@" + n_in1), (C_IN, "@" + n_in1)], f"{U} in 1")
    rf(n_rfin, [(C_IN, "@" + n_rfin), (X_IN, yl), (U, "2")], f"{U} RFIN")
    rf(n_rfout, [(U, "7"), (X1, yl)], f"{U} RFOUT")
    rf(n_rfout, [(X1, yl), (C_O, "@" + n_rfout)], f"{U} RFOUT b")   # 90-degree joint inside the bead pad
    rf(n_padin, [(C_O, "@" + n_padin), (X1, yr), (RSER, "@" + n_padin)], f"{U} pad in", ch=0.3)
    rf(n_padin, [(RSER, "@" + n_padin), (RS1, "@" + n_padin)], f"{U} shunt 1")
    rf(n_padout, [(RSER, "@" + n_padout), (X2, yr), (C_I, "@" + n_padout)], f"{U} pad out", ch=0.3)
    rf(n_padout, [(RS2, "@" + n_padout), (XRS2, yr)], f"{U} shunt 2")
    rf(n_gin, [(C_I, "@" + n_gin), (X2, yl), (G, "1")], f"{G} IN", ch=0.3)
    rf(n_gout, [(G, "3"), (XO, yl)], f"{G} OUT")
    rf(n_gout, [(XO, yl), (C_OUT, "@" + n_gout)], f"{G} OUT b")      # joint inside the bead pad
    # launch node = a T at (XO, ys): drop from C421 north, stub west, output east (6L: a 0.3 chamfer at the node
    # would leave the 0.16 mm stub start 0.21 mm off the line copper, i.e. disconnected)
    rf(OUT, [(C_OUT, "@" + OUT), (XO, ys)], f"{OUT[1:]} drop")
    rf(OUT, [(XO, ys), (BW - 0.5, ys), (BW, my(YS + 0.5))], f"{OUT[1:]} output", ch=0.3)
    dx_, dy_ = blk.pad(D, "@" + OUT)
    RFPOLY.append((blk.track(OUT, W, [(dx_, dy_), (dx_, ys)]), W))
    q_st, l_st = blk.tline(TL, [(XO, ys), (XO - L_STUB, ys)], W)
    RFPOLY.append((q_st, W))
    RF[OUT] = W
    # stub short: NT pad 1 on the stub end, pad 2 -> two GND vias towards the line.  6L: the 80 ps stub is
    # 0.30 mm longer (5.925 ps/mm), so the net tie stands across the stub (pad 2 towards the line, x 0.6-1.6 is
    # free between the input leg and U403) instead of in-line (that put pad 2 / the vias off the block edge)
    xe = XO - L_STUB
    two(NT, xe, my(YS - 0.5), NS("S"), n_stub)
    assert max(abs(a - b) for a, b in zip(blk.pad(NT, "@" + n_stub), (xe, ys))) < 1e-6
    gx, gy = blk.pad(NT, "2")
    gv(gx, gy)                                           # RF-2: GND via in NT pad 2, right at the tie bar
    blk.track("GND", W_GND, [(gx, gy), (gx - 0.6, gy)])  # second via west (in K the TRF pin-1 cap via is below)
    gv(gx - 0.6, gy)
    # clamp GND -> via beyond its pad
    x, y = blk.pad(D, "@GND")
    blk.track("GND", W_GND, [(x, y), (x, y - s * 0.62)])
    gv(x, y - s * 0.62)
    # shunt GND vias inside the U at the line level, east of their pads (the bias-tee choke on B is above them)
    x, y = blk.pad(RS2, "@GND")
    blk.track("GND", W_GND, [(x, y), (x, yl), (x + 0.5, yl)])
    gv(x + 0.5, yl)
    x, y = blk.pad(RS1, "@GND")
    blk.track("GND", W_GND, [(x, y), (x + 0.80, y)])                # hole edge 0.225 mm off the 0603 pad
    gv(x + 0.80, y)
    # ---------------------------------------------------------------- TRF GND pins -> EP, EP vias
    xu, yu = blk.loc(blk.fps[U].GetPosition())
    for pn in ("3", "4", "5", "6", "8"):
        x, y = blk.pad(U, pn)
        blk.track("GND", 0.25, [(x, y), (xu, y)])
    for dy in (-0.55, 0.0, 0.55):
        gv(xu, yu + dy)
    # ---------------------------------------------------------------- TRF VCC (pin 1 is north in both chains)
    p1 = blk.pad(U, "1")
    yc = (yu - 1.25) - 0.95
    two(C1N, p1[0], yc, "S", "+3V3")
    two(C100, p1[0] + 0.96, yc, "S", "+3V3")
    c1, c2 = blk.pad(C1N, "@+3V3"), blk.pad(C100, "@+3V3")
    blk.track("+3V3", 0.25, [p1, c1])
    # VIAS-OUT-OF-PADS (24 Nov): no via in a soldered pad (tented vias only, RULES.md rule 12).  The 10 uF used
    # to sit on B with its GND pad over the two 0402 GND vias and its +3V3 pad beside the via pair; it now lies
    # horizontal on B between the PH_STROBE_P L6 line and the via pair, which moved north of it (x = its +3V3
    # pad), so every via is >= 0.2 mm (hole edge) outside every pad.  F: pins -> 0402s -> track east and north
    # to the via pair (current passes the capacitors first).
    vx = c2[0] + 0.94
    va, vb = (vx, c2[1] - 1.43), (vx, c2[1] - 2.08)
    blk.track("+3V3", W_PWR, [c1, c2, (vx - 0.19, c2[1]), (vx, c2[1] - 0.19), va, vb])
    for v in (va, vb):
        blk.via(*v, "+3V3")
    gvs = []
    for c in (C1N, C100):
        x, y = blk.pad(c, "@GND")
        blk.track("GND", W_GND, [(x, y), (x, y - 0.60)])
        gv(x, y - 0.60)
        gvs.append((x, y - 0.60))
    # 10 uF on B.Cu: GND pad (west) below the C1N GND via, +3V3 pad (east) below the via pair, short B necks
    two(C10U, vx - 0.95, c2[1] - 0.38, "W", "GND", side="B")
    assert abs(blk.pad(C10U, "@GND")[0] - gvs[0][0]) < 1e-6
    cg_, ct = blk.pad(C10U, "@GND"), blk.pad(C10U, "@+3V3")
    blk.track("GND", W_GND, [cg_, gvs[0]], layer="B.Cu")
    blk.track("+3V3", W_PWR, [ct, va, vb], layer="B.Cu")
    # (the spare 100 nF CX moved to the bias-tee cold cap C434 / C435 below: the north-west B.Cu strip now
    #  carries the PH_STROBE L6 lines)
    # ---------------------------------------------------------------- TRF bias tee on B.Cu (straight chain)
    # BIASTEE-6 (24 Nov): the 1210 moved DL east, so the bead's via is no longer in choke pad 1 (0.15 mm gap); a
    # short B track enters the pad along its axis
    pb = blk.pad(FB, "2")
    yt = my(YL - 1.80)
    blk.track(n_bias, 0.5, [pb, (pb[0], yt)])
    blk.via(pb[0], yt, n_bias)
    two(L, pb[0] + 1.40 + DL, yt, "W", n_bias, side="B")
    blk.track(n_bias, 0.5, [(pb[0], yt), blk.pad(L, "@" + n_bias)], layer="B.Cu")
    lc = blk.pad(L, "@+3V3")
    two(CC, lc[0] + 1.85, yt, "W", "+3V3", side="B")      # cold-pad 100 nF along the chain (courtyards touch)
    cc = blk.pad(CC, "@+3V3")
    blk.track("+3V3", 0.64, [lc, cc], layer="B.Cu")
    g = blk.pad(CC, "@GND")
    # its GND via lands (through) in the GVA tab on F in chain A: 0.06 mm east so the whole via is inside the tab
    blk.track("GND", W_GND, [g, (g[0], g[1] + s * 0.59), (g[0] + 0.06, g[1] + s * 0.65)], layer="B.Cu")
    gv(g[0] + 0.06, g[1] + s * 0.65)
    for d in (-0.75, 0.75):                               # +3V3 enters through the capacitor pad
        blk.via(cc[0], cc[1] + d, "+3V3")
    blk.track("+3V3", 0.56, [(cc[0], cc[1] - 0.75), (cc[0], cc[1] + 0.75)], layer="B.Cu")
    # spare 100 nF CX on B below C434 / C435: +3V3 pad onto the cold cap's inner +3V3 via, own GND via
    two(CX, cc[0], my(4.45), NS("N"), "+3V3", side="B")
    cxp, cxg = blk.pad(CX, "@+3V3"), blk.pad(CX, "@GND")
    blk.track("+3V3", 0.4, [cxp, (cc[0], cc[1] + s * 0.75)], layer="B.Cu")
    blk.track("GND", W_GND, [cxg, (cxg[0], my(5.55))], layer="B.Cu")
    gv(cxg[0], my(5.55))
    two(RD, pb[0] + 1.40 + DL, my(0.54), "W", n_bias, side="B")  # 1 k beside the 1210 (outer side)
    r1, r2 = blk.pad(RD, "@" + n_bias), blk.pad(RD, "@+3V3")
    l1 = blk.pad(L, "@" + n_bias)
    blk.track(n_bias, 0.4, [r1, (l1[0] + 0.35, r1[1]), (l1[0], r1[1] + s * 0.35), l1], layer="B.Cu")
    blk.track("+3V3", 0.4, [r2, (lc[0] - 0.35, r2[1]), (lc[0], r2[1] + s * 0.35), lc], layer="B.Cu")
    bplace(TP1, l1[0], my(YL - 1.80 + 1.58 + 1.01), 0, "B")   # test point below the 1210
    blk.track(n_bias, 0.4, [l1, blk.pad(TP1, "1")], layer="B.Cu")
    # ---------------------------------------------------------------- GVA GND tab vias
    xg_, yg_ = blk.loc(blk.fps[G].GetPosition())
    # GVA tab = an exposed thermal / RF-ground pad: vias IN it are allowed (README 'Vias out of pads': Mini-Circuits
    # mounting layout PL-075 has plated holes in the tab), 0.2 mm drill, wholly inside the tab, tented on B and
    # never under a B pad.  A: east half of the tab (C434 below on B); K: one column west of the 10 uF on B.
    for dx, dy in (((0.05, -1.2), (0.05, 0.0), (0.55, -1.2), (0.55, 0.0)) if A else
                   ((-0.38, -1.2), (-0.38, -0.6), (-0.38, 0.0))):
        gv(xg_ + dx, yg_ + dy)
    # ---------------------------------------------------------------- GVA bias tee on B.Cu (+5V1, was VBUS)
    # BIASTEE-4 / -6 (24 Nov): the 2.2 uH stands 1.25 mm east of the bead via (B track into its pad, no via in the
    # pad); cold pad -> C418 1 nF and C419 100 nF stacked at it (identical in A and K), each with its own GND via
    # (none in a pad); the cold node enters through C419.  24 Nov 2026 (SPEC decision 26): +5V1 is 5.40 V, so the
    # drain feed has a series 2.49 R (R419 / R420, 0402) stacked below C419 / C429, 0.5 mm west so its node pad
    # clears the bead via; the +5V1 via pair moved from beside C419 to below the resistor's +5V1 pad.
    P5 = "/+5V1"
    NF = N(RG, 1)                                       # cold node: R pad 1, C418 / C419, choke cold pad
    pg = blk.pad(FBG, "2")
    yv = my(YL - 1.55)
    blk.track(n_gbias, 0.5, [pg, (XO, yv)])
    blk.via(XO, yv, n_gbias)
    two(LG, XO + 1.25, my(YL - 1.55 - 1.062), NS("S"), n_gbias, side="B")
    snap(LG, n_gbias, y=yv)
    lb = blk.pad(LG, "@" + n_gbias)
    blk.track(n_gbias, 0.5, [(XO, yv), lb], layer="B.Cu")
    lv = blk.pad(LG, "@" + NF)
    XCG = XO - 0.65
    two(CG1, XCG, lv[1], "E", NF, side="B")                        # 1 nF on the cold pad's row
    two(CG2, XCG, lv[1] + s * 0.94, "E", NF, side="B")             # 100 nF below it (courtyards touch)
    c1v, c2v = blk.pad(CG1, "@" + NF), blk.pad(CG2, "@" + NF)
    blk.track(NF, 0.64, [lv, c1v], layer="B.Cu")
    blk.track(NF, 0.5, [c1v, c2v], layer="B.Cu")
    for c in (CG1, CG2):
        g = blk.pad(c, "@GND")
        gv(g[0] - 0.62, g[1])
        blk.track("GND", W_GND, [g, (g[0] - 0.62, g[1])], layer="B.Cu")
    # 2.49 R below C419, 0.24 mm gap between courtyards: C419 pad -> down the axis -> 45 deg -> down into the R pad
    two(RG, XCG - 0.50, c2v[1] + s * 1.18, "E", NF, side="B")
    rn, rp = blk.pad(RG, "@" + NF), blk.pad(RG, "@" + P5)
    y1 = c2v[1] + s * 0.325                                         # just outside the C419 pad
    blk.track(NF, 0.4, [c2v, (c2v[0], y1), (rn[0], y1 + s * abs(c2v[0] - rn[0])), rn], layer="B.Cu", ch=0)
    # +5V1 reaches R419 / R420 from the 10 uF C420 / C430 (own via pair, below): supply -> 10 uF -> 2.49 R -> 100 nF
    # / 1 nF -> choke, as in the schematic; no extra via (the old pair beside C419 is gone)
    bplace(TP2, lb[0], my(4.56), 0, "B")                          # test point straight below the choke pad
    blk.track(n_gbias, 0.4, [lb, blk.pad(TP2, "1")], layer="B.Cu")
    # +5V1 bulk: 10 uF 0805 on B.Cu below the GVA, own via pair and GND via
    two(CG10, 11.25, my(7.00), "W", P5, side="B")
    p10, g10 = blk.pad(CG10, "@" + P5), blk.pad(CG10, "@GND")
    for d in (-0.40, 0.40):
        blk.via(p10[0] - 0.90, p10[1] + d, P5)
    blk.track(P5, 0.6, [(p10[0] - 0.90, p10[1] - 0.40), (p10[0] - 0.90, p10[1] + 0.40)], layer="B.Cu")
    blk.track(P5, 0.6, [(p10[0] - 0.90, p10[1]), p10], layer="B.Cu")
    blk.track("GND", W_GND, [g10, (g10[0] + 0.85, g10[1])], layer="B.Cu")   # hole edge 0.25 mm off the pad
    gv(g10[0] + 0.85, g10[1])
    # R419 / R420 +5V1 pad -> 10 uF pad: down the pad axis, one 45 deg leg, into the 10 uF pad from the north (A)
    ye, xe = p10[1] - s * 1.0, p10[0] + 0.25                    # 0.28 mm outside the 0805 pad, clear of C432's via
    yk = ye - s * abs(rp[0] - xe)                               # start of the 45 deg leg
    assert s * (yk - rp[1]) > 0.35, (yk, rp)
    blk.track(P5, 0.5, [rp, (rp[0], yk), (xe, ye), (xe, p10[1])], layer="B.Cu", ch=0)
    return {"stub": l_st, "out": blk.route_len(f"{OUT[1:]} drop") + blk.route_len(f"{OUT[1:]} output"),
            "ret": blk.route_len(f"{PIN[1:]} L1 return"), "PIN": PIN,
            "leg": blk.route_len(f"{U} in 1") + blk.route_len(f"{U} RFIN")}


RES = {"A": chain(+1), "K": chain(-1)}

# ============================================================================= PH_STROBE inputs (TOPOLOGY s. 4)
# Both enter on the north edge on L1 (0.16 mm), take L1 -> via -> L6 -> via -> L1 and land on the 47 R of their
# chain (netlist: PH_STROBE_P -> R407 chain A, PH_STROBE_N -> R411 chain K).  L6 over L5 (0.0994 mm 3313) is
# the same microstrip as L1 over L2: 0.16 mm = 50.2 R, 5.925 ps/mm, so L1 and L6 millimetres add 1:1.
# K: dives at the corner, runs down the west strip, passes under the trigger corridor in the clear B.Cu
# channel at x 2.37 (phase C309 / GND vias end at 1.79, L302 pad 2 starts at 2.95) and surfaces at VK2.
# A: same structure, its L6 detour is a U in the free B.Cu band between the 47 R row and the stub (solved for
# equal total length).  A GND via stands beside every signal via.
RFPOLY_B = []
YV2A, YV2K = YR_IN, 2 * AX - YR_IN


def l6(net, pts, name):
    q = blk.track(net, W, pts, layer="B.Cu", name=name, z=50)
    RFPOLY_B.append((q, W))
    return q


VA1, GA1 = (1.00, 1.35), (1.60, 0.95)
VK1, GK1 = (X_N, 0.45), (1.70, 0.45)
inA = rf("/PH_STROBE_P", [(X_P, 0.0), (X_P, 0.85), VA1], "PH_STROBE_P L1 entry")
inK = rf("/PH_STROBE_N", [(X_N, 0.0), VK1], "PH_STROBE_N L1 entry")
for v, n_ in ((VA1, "/PH_STROBE_P"), (VK1, "/PH_STROBE_N")):
    blk.via(*v, n_)
for g_ in (GA1, GK1):
    gv(*g_)
YV2K = BH - 0.40
pts_K = [VK1, (0.80, 0.45), (0.45, 0.80), (0.45, 8.20), (X_KC, 8.20 + X_KC - 0.45), (X_KC, 15.95),
         (X_KC - 0.30, 16.25), (X_IN + 0.30, 16.25), (X_IN, 16.55), (X_IN, YV2K)]


N_SERP, P_SERP, Y_BOT, Y_RET = 7, 0.70, 9.00, 6.95   # A detour: serpentine on B.Cu, same-net gap 0.54 mm


def pts_A(yt):
    """VA1 -> west strip -> leg 0 down at x 2.45 -> N_SERP legs (pitch 0.7, between yt and Y_BOT, the last one
    up to the return lane Y_RET) -> west along Y_RET -> 45 degrees into VA2"""
    p = [VA1, (1.00, 5.60), (1.45, 6.05), (1.95, 6.05), (2.45, 6.55), (2.45, Y_BOT)]
    x = 2.45
    for i in range(1, N_SERP + 1):
        x += P_SERP
        p += [(x, p[-1][1])]
        p += [(x, Y_RET if i == N_SERP else (yt if i % 2 else Y_BOT))]
    return p + [(XV2 + Y_RET - YV2A, Y_RET), (XV2, YV2A)]


def cl(pts):
    return bl.plen(bl.chamfer(pts, 0.2) if len(pts) > 2 else pts)      # as blk.track draws it


L_K = cl([(X_N, 0.0), VK1]) + cl(pts_K) + RES["K"]["ret"] + RES["K"]["leg"]       # north edge -> TRF pin 2
fixedA = cl([(X_P, 0.0), (X_P, 0.85), VA1]) + RES["A"]["ret"] + RES["A"]["leg"]
lo, hi = 7.45, Y_BOT - 0.45                     # amplitude: yt in [7.45, 8.55]; length falls as yt rises
assert cl(pts_A(lo)) >= L_K - fixedA >= cl(pts_A(hi)), (cl(pts_A(lo)), L_K - fixedA, cl(pts_A(hi)))
for _ in range(60):
    mid = (lo + hi) / 2
    lo, hi = (mid, hi) if cl(pts_A(mid)) > L_K - fixedA else (lo, mid)
YT = (lo + hi) / 2
XE = YT
l6("/PH_STROBE_P", pts_A(YT), "PH_STROBE_P L6")
l6("/PH_STROBE_N", pts_K, "PH_STROBE_N L6")
INP = {}
for k_, net_ in (("A", "PH_STROBE_P"), ("K", "PH_STROBE_N")):
    e_, m_, r_ = (blk.route_len(f"{net_} L1 entry"), blk.route_len(f"{net_} L6"), blk.route_len(f"{net_} L1 return"))
    INP[k_] = (e_, m_, r_, e_ + m_ + r_, RES[k_]["leg"], e_ + m_ + r_ + RES[k_]["leg"])
assert abs(INP["A"][5] - INP["K"][5]) < 0.1, INP

# ============================================================================= pours, keep-outs
IN = 0.15
REG = {"A": bl.rect_pts(IN, IN, BW - IN, CORR[0] - IN), "K": bl.rect_pts(IN, CORR[1] + IN, BW - IN, BH - IN)}
for r in REG.values():
    blk.zone("GND", ["In1.Cu"], r, clearance=0.2, prio=0)
    blk.zone("GND", ["F.Cu"], r, clearance=0.25, prio=0)
    blk.zone("GND", ["B.Cu"], r, clearance=0.25, prio=0)
    blk.zone("GND", ["In4.Cu"], r, clearance=0.2, prio=0)        # L5: solid ground (reference of the L6 lines)
for q, w in RFPOLY:
    blk.rf_keepout(q, w, gap=2 * w + 0.03)
for q, w in RFPOLY_B:
    blk.rf_keepout(q, w, gap=2 * w + 0.03, layer="B.Cu")

# ============================================================================= 6L pad compensation
# (same method as blocks/analog) pF/mm from boardlib.microstrip (mask corrected): L2 at H2 (3313, er 4.1); where
# L2 is cut under a pad the reference is L3 (GND pour, 0.565 mm deeper, core er ~4.5).  Every in-line RF pad
# whose excess C over L2 (pad vs. the 0.16 mm line over the pad length) exceeds 30 fF gets an L2 cut of the pad
# size; L3 keeps its GND pour under it with a no-track / no-via rule area (no bias line under an RF pad).
H2 = bl.STACKUPS["6L"]["H"]
H3 = H2 + 0.0152 + 0.55
ER_DEEP = 4.5
C_EXCESS_MAX = 0.030


def c_mm(w, h=H2):
    """pF per mm of a w-wide strip over a plane h below"""
    z, ee = bl.microstrip(w, h=h, er=bl.STACKUPS["6L"]["ER"] if h <= H2 + 1e-6 else ER_DEEP)
    return math.sqrt(ee) / (bl.C0 * z)


def _pad_axis(pd, net):
    """axis (0 = x, 1 = y) of the RF track that enters the pad; None for the TLine footprints' own pads"""
    if pd.GetParent().GetReference().startswith("TL"):
        return None
    for t in blk.b.GetTracks():
        if t.GetNetname() != net or isinstance(t, pcbnew.PCB_VIA) or t.GetLayer() != pcbnew.F_Cu:
            continue
        for e, o in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
            if pd.HitTest(e) or t.HitTest(pd.GetPosition()):
                a, b_ = blk.loc(e), blk.loc(o)
                return 0 if abs(b_[0] - a[0]) >= abs(b_[1] - a[1]) else 1
    return 0                                     # NT402 / NT403 pad 1: the stub enters along x


PADCOMP = []
for f_ in blk.fps.values():
    for pd in f_.Pads():
        net_ = pd.GetNetname()
        if net_ not in RF or not pd.IsOnLayer(pcbnew.F_Cu):
            continue
        ax = _pad_axis(pd, net_)
        if ax is None:
            continue
        bb = pd.GetBoundingBox()
        dims = (pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight()))
        along, across = dims[ax], dims[1 - ax]
        cx, cy = blk.loc(pd.GetPosition())
        c_line = c_mm(W) * along
        ex2 = c_mm(across) * along - c_line
        cut = ex2 > C_EXCESS_MAX
        if cut:
            r_ = bl.rect_pts(cx - dims[0] / 2, cy - dims[1] / 2, cx + dims[0] / 2, cy + dims[1] / 2)
            blk.keepout(r_, ("In1.Cu",))
            blk.keepout(r_, ("In2.Cu",), tracks=True, vias=True).SetDoNotAllowCopperPour(False)
        PADCOMP.append((f"{f_.GetReference()}.{pd.GetNumber()}", across, along, ex2 * 1e3,
                        "L2 cut" if cut else "-", ((c_mm(across, H3) * along - c_line) if cut else ex2) * 1e3))

# ============================================================================= interfaces, outline
blk.iface("PH_STROBE_P", X_P, 0.0, "F.Cu", "N", "pair", W,
          f"chain A (R407); board (10.00, 25.00); edge -> TRF pin 2 {INP['A'][5]:.3f} mm; FPGA U501 pin 40")
blk.iface("PH_STROBE_N", X_N, 0.0, "F.Cu", "N", "pair", W,
          f"chain K (R411); board (10.60, 25.00); edge -> TRF pin 2 {INP['K'][5]:.3f} mm (L6 under the corridor at "
          f"board x 11.87); FPGA U501 pin 39")
blk.iface("PSTRB_A", BW, 9.75, "F.Cu", "E", "rf50", W, "to phase tap 0 (phase iface 26.5 / 34.75 board)")
blk.iface("PSTRB_K", BW, 15.25, "F.Cu", "E", "rf50", W, "to phase tap 0 (phase iface 26.5 / 40.25 board)")
blk.iface("+3V3", 0, 0, "In3.Cu", "-", "supply", None, "TRF VCC and bias tees: via pairs, L4 (In3) x 0-12")
blk.iface("/+5V1", 0, 0, "In3.Cu", "-", "supply", None,
          "GVA-84+ tees (+5V1, was VBUS): via pairs at C419 / C429 (both chains alike) and at C420 / C430, L4 x 9-15")
blk.edge_rect(0, 0, BW, BH, layer="Dwgs.User")
blk.line(0, CORR[0], BW, CORR[0], layer="Dwgs.User")
blk.line(0, CORR[1], BW, CORR[1], layer="Dwgs.User")
blk.text("PSTROBE A", 6.0, 7.6, 0.4, "F.Fab")
blk.text("PSTROBE K", 6.0, 17.4, 0.4, "F.Fab")
for fp_ in blk.fps.values():                 # reference designators hidden on Fab (no room for 0.8 mm silk text)
    fab = pcbnew.B_Fab if fp_.GetLayer() == pcbnew.B_Cu else pcbnew.F_Fab
    for t_ in (fp_.Reference(), fp_.Value()):
        t_.SetLayer(fab)
        t_.SetTextSize(pcbnew.VECTOR2I(bl.mm(0.3), bl.mm(0.3)))
        t_.SetTextThickness(bl.mm(0.05))
    for g_ in fp_.GraphicalItems():           # the library's ${REFERENCE} copy on Fab
        if g_.GetClass() in ("FP_TEXT", "PCB_TEXT") and g_.GetLayer() in (pcbnew.F_Fab, pcbnew.B_Fab):
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
          f"{r['out']:.3f} mm")
for k, (e_, m_, r_, t_, lg_, tt_) in INP.items():
    print(f"input {k}: L1 entry {e_:.3f} + L6 {m_:.3f} + L1 return {r_:.3f} = {t_:.3f} mm to the 47 R; + leg {lg_:.3f}"
          f" = {tt_:.3f} mm = {tt_ * bl.PS_MM50:.2f} ps to TRF pin 2 (+ 2 vias)")
print(f"stub short: tie {L_TIE_PH:.0f} pH + via {L_VIA_PH:.0f} pH -> {DT_SHORT:.2f} ps; drawn stub {L_STUB:.3f} mm "
      f"= {L_STUB * bl.PS_MM50:.2f} ps, total {L_STUB * bl.PS_MM50 + DT_SHORT:.2f} ps")
print(f"input A-K mismatch to TRF pin 2 {(INP['A'][5] - INP['K'][5]) * 1e3:.1f} um; A serpentine top y {YT:.3f}")
print("impedance (JLC06161H-3313, L1 over L2 h 0.0994 mm er 4.1, mask corrected; L6 over L5 identical)")
for z_ in (50,):
    w_ = bl.width_for_6l(z_)
    print(f"  {z_:3d} R: w {w_:.3f} mm (drawn {bl.r01(w_):.2f}: {bl.microstrip_6l(bl.r01(w_))[0]:.1f} R)")
for w_ in (0.10, W, 0.25, 0.36, 0.5):
    z_, ee_ = bl.microstrip_6l(w_)
    print(f"  w {w_:.2f} mm: Z0 {z_:5.1f} R, eps_eff {ee_:.3f}, {math.sqrt(ee_) / bl.C0:.3f} ps/mm, "
          f"{c_mm(w_) * 1e3:.0f} fF/mm")
print(f"pad compensation (excess C vs. the {W} mm line over the pad length; L2 cut if > {C_EXCESS_MAX * 1e3:.0f} fF)")
print(f"  {'pad':10s} {'across':>6s} {'along':>6s} {'over L2 fF':>10s}  action  {'after fF':>8s}")
for row in sorted(PADCOMP):
    print(f"  {row[0]:10s} {row[1]:6.2f} {row[2]:6.2f} {row[3]:10.1f}  {row[4]:6s}  {row[5]:8.1f}")
print("intended vs actual (6L ps/mm %.3f)" % bl.PS_MM50)
for k, r in RES.items():
    print(f"  chain {k}: stub target 80.0 ps = {80.0 / bl.PS_MM50:.3f} mm, drawn {r['stub']:.3f} mm = "
          f"{r['stub'] * bl.PS_MM50:.2f} ps; output target A = K, drawn {r['out']:.3f} mm = {r['out'] * bl.PS_MM50:.2f} ps")
dA = abs(RES["A"]["out"] - RES["K"]["out"])
print(f"A/K output mismatch {dA * 1e3:.1f} um")
assert dA < 0.05

# ============================================================================= checks
import floorplan as fpl
mem = fpl.membership(nl)
ANALOG_TOOK = ("C402", "C403", "C404", "C407", "C408", "C409")
REFS = sorted(r for r, b_ in mem.items() if b_ == "pstrobe" and r not in ANALOG_TOOK)
res = bl.check_board(out, refs=REFS, rf_widths=RF, verbose=12)


def courtyard_overlaps(path, min_area=0.005):
    """local helper: pairwise intersection of the library courtyards (F.CrtYd / B.CrtYd) per board side"""
    b_ = pcbnew.LoadBoard(path)
    fps = list(b_.GetFootprints())
    cy = []
    for f_ in fps:
        f_.BuildCourtyardCaches()
        for lay in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            p_ = f_.GetCourtyard(lay)
            if p_.OutlineCount():
                cy.append((f_.GetReference(), lay, p_))
    hits = []
    for i in range(len(cy)):
        for j in range(i + 1, len(cy)):
            (ra, la, pa), (rb, lb, pb_) = cy[i], cy[j]
            if la != lb or not pa.BBox().Intersects(pb_.BBox()):
                continue
            x_ = pa.CloneDropTriangulation() if hasattr(pa, "CloneDropTriangulation") else pcbnew.SHAPE_POLY_SET(pa)
            x_.BooleanIntersection(pb_, pcbnew.SHAPE_POLY_SET.PM_FAST)
            ar = x_.Area() / 1e12
            if ar > min_area:
                hits.append((ra, rb, round(ar, 3)))
    nocy = [f_.GetReference() for f_ in fps if not any(c[0] == f_.GetReference() for c in cy)]
    print(f"courtyard overlaps (> {min_area} mm2): {len(hits)}  {hits[:20]}   (no courtyard: {nocy})")
    return hits


CY_HITS = courtyard_overlaps(out)

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
    render(os.path.join(HERE, "pstrobe_detail.png"), ("F.Cu", "B.Cu", "F.Fab", "Dwgs.User"), (-0.3, -0.3, 9.3, 19.5))
    render(os.path.join(HERE, "pstrobe_detail_L1L2.png"), ("F.Cu", "In1.Cu", "F.Fab", "Dwgs.User"),
           (-0.3, 3.0, 17.3, 10.0))
    render(os.path.join(SCR, "pstrobe_f.png"), ("F.Cu", "F.Fab", "Dwgs.User"), (-0.5, -0.5, 17.5, 25.5))
    render(os.path.join(SCR, "pstrobe_b.png"), ("B.Cu", "B.Fab", "Dwgs.User"), (-0.5, -0.5, 17.5, 25.5))
