"""trigger_phase.kicad_sch: trigger path and phase recovery (design/lowcost/sim/phase/RESULT.md,
SPEC decisions 4-6).

Signal path, left to right (top of the sheet):
  BUF_OUT_T / EXT_CLK (49.9 R termination) -> U301 TMUX136 (local switch ground VSW_GND = -0.9 V,
  SEL level-shifted from TRIG_SEL) -> U302 TLV3801 (+/-2V5, IN- = TRIG_LEVEL), 100 R across CMP_P/CMP_N
  -> CMP_P -> 1 uF -> U303 TRF37D73 (3V3, 120 nH + 47 uH choke) -> 1 uF -> 12 dB pi pad 82/91/82 R
  -> 16-tap delay line (two rows of 8 on the sheet, wired through) -> 49.9 R termination.
  CMP_N -> 1 uF -> 49.9 R dummy; CMP_P/CMP_N bridged by 2 x 470 R -> U304 SN65LVDS2 -> COARSE.
Taps (ladder): BAT15-04W gate (pin 3 common on the line), 0.47 pF C0G hold caps to PSTRB_A (anode
node) / PSTRB_K (cathode node), 2.2 k to VTAP_N (anode node) / VTAP_P (cathode node), 2 x 1 k summing to
COS3502 IN+, IN- = VTAP_TH (1 k + 100 nF per row), OUT -> TAPn. Strobe lines end in 49.9 R.

Pinouts (datasheets, checked):
  TMUX136 RSE UQFN-10 (SCDS367E table 5-1): 1 A1, 2 A2, 3 B1, 4 B2, 5 GND, 6 EN (low active), 7 COM2,
    8 COM1, 9 SEL (low = A), 10 VCC.
  TLV3801 DSG WSON-8 (SNOSDD7C table 5-1): 1 OUT-, 2 GND, 3 VEE, 4 IN-, 5 IN+, 6/7 VCC, 8 OUT+;
    thermal pad -> VEE.
  TRF37D73 DSG WSON-8 (SLASE43): 1 VCC, 2 RFIN, 3/4/6/8 NC (to GND), 5 PWDN (high = off), 7 RFOUT
    (bias through choke), pad = GND.
  SN65LVDS2 DBV SOT-23-5 (SLLS373M): 1 VCC, 2 GND, 3 A, 4 B, 5 R.
  COS3502 SOP-8 (Cosine rev 1.0 pin diagram, NOT the TLV3502 pinout): 1 +INA, 2 -INA, 3 +INB,
    4 -INB, 5 Vs-, 6 OUTB, 7 OUTA, 8 Vs+.
  BAT15-04W SOT-323: 1 A1, 2 K2, 3 K1/A2 (common)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import schlib
from schlib import g, ic_symbol, Q, FONT, num
from common import new_sheet, hier_pins, R, C

T = 1.0                                  # annotation text size
TP = "Connector:TestPoint"
TP_FP = "TestPoint:TestPoint_Pad_D1.0mm"
DUAL = "Device:D_Schottky_Dual_Series_AKC"
DUAL_FP = "Package_TO_SOT_SMD:SOT-323_SC-70"
BAT_F = {"Price": "0.37 USD @10 (SPEC)", "Note": "SOT-323: 1 A1, 2 K2, 3 K1/A2"}
WSON = "Package_SON:WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm"


def P(x, y):
    return (g(x), g(y))


def cos3502_symbol():
    """Dual comparator COS3502 with its own pinout, 3 units (A, B, power)."""
    name = "COS3502"
    st = ["stroke", ["width", "0.254"], ["type", "default"]]
    tri = ["polyline", ["pts", ["xy", "-5.08", "5.08"], ["xy", "5.08", "0"], ["xy", "-5.08", "-5.08"],
                        ["xy", "-5.08", "5.08"]], st, ["fill", ["type", "background"]]]

    def pin(n, nm, typ, x, y, ang):
        return ["pin", typ, "line", ["at", num(x), num(y), str(ang)], ["length", "2.54"],
                ["name", Q(nm), FONT], ["number", Q(n), FONT]]
    hid = ["effects", ["font", ["size", "1.27", "1.27"]], "hide"]
    u = lambda k, pins, body: ["symbol", Q(f"{name}_{k}_1")] + body + pins
    sym = ["symbol", Q("scope-fe:" + name), ["pin_names", ["offset", "0.254"]], ["in_bom", "yes"],
           ["on_board", "yes"],
           ["property", Q("Reference"), Q("U"), ["at", "1.27", "6.35", "0"],
            ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left"]]],
           ["property", Q("Value"), Q(name), ["at", "1.27", "-6.35", "0"],
            ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left"]]],
           ["property", Q("Footprint"), Q("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"), ["at", "0", "0", "0"], hid],
           ["property", Q("Datasheet"), Q("https://www.cosine-ic.com (COS3501/COS3502 rev 1.0)"),
            ["at", "0", "0", "0"], hid],
           u(1, [pin("1", "+", "input", -7.62, 2.54, 0), pin("2", "-", "input", -7.62, -2.54, 0),
                 pin("7", "~", "output", 7.62, 0, 180)], [tri]),
           u(2, [pin("3", "+", "input", -7.62, 2.54, 0), pin("4", "-", "input", -7.62, -2.54, 0),
                 pin("6", "~", "output", 7.62, 0, 180)], [tri]),
           u(3, [pin("8", "V+", "power_in", 0, 7.62, 270), pin("5", "V-", "power_in", 0, -7.62, 90)],
             [["rectangle", ["start", "-2.54", "5.08"], ["end", "2.54", "-5.08"], st,
               ["fill", ["type", "background"]]]])]
    schlib.CUSTOM["scope-fe:" + name] = sym
    return "scope-fe:" + name


def split_wires(sh):
    """Split wires at every pin or wire end on their interior (as gen_sampler.py)."""
    pts = {p for w in sh.wires for p in w}
    for s in sh.symbols:
        for pd in s.pins:
            pts.add(s.pin(pd.number))
    out = []
    for a, b in sh.wires:
        inner = sorted((p for p in pts if sh._on_mid(p, a, b)), key=lambda p: abs(p[0] - a[0]) + abs(p[1] - a[1]))
        chain = [a] + inner + [b]
        out += list(zip(chain, chain[1:]))
    sh.wires = out


def main():
    sh = new_sheet("trigger_phase", comments=[
        "gen/gen_trigger_phase.py, sim/phase/RESULT.md, SPEC dec. 4-6",
        "Line drawn as 2 rows of 8 taps; PCB: one straight line"])

    def dec_up(pt, x, val="100n", note=None):
        """Cap hanging upward from a rail point (wired horizontally to x), GND on top."""
        c = C(sh, val, (x, pt[1] - g(3)))
        sh.wire(pt, c["2"])
        sh.power("GND", c["1"], dy=-2.54, rot=180)
        return c

    def dec_down(pt, x, val="100n", gnd="GND"):
        c = C(sh, val, (x, pt[1] + g(3)))
        sh.wire(pt, c["1"])
        sh.power(gnd, c["2"], dy=2.54)
        return c

    # ================================================================== TMUX136
    tmux = ic_symbol("TMUX136", left=[("1", "A1", "passive"), ("3", "B1", "passive"), None, ("2", "A2", "passive"),
                                      ("4", "B2", "passive"), ("6", "EN", "input"), None, ("9", "SEL", "input")],
                     right=[("8", "COM1", "passive"), None, None, ("7", "COM2", "passive")],
                     top=[("10", "VCC", "power_in")], bottom=[("5", "GND", "power_in")],
                     footprint="Package_DFN_QFN:Texas_UQFN-10_1.5x2mm_P0.5mm",
                     description="2:1 2-channel 6 GHz switch")
    u1 = sh.add(tmux, "U301", "TMUX136", P(52, 44), fp="Package_DFN_QFN:Texas_UQFN-10_1.5x2mm_P0.5mm",
                lcsc="C2673277", mpn="TMUX136MRSER", fields={"Price": "1.22 USD (DigiKey)"})
    yS = u1["8"][1]                                       # main trigger signal row
    # BUF_OUT_T -> A1
    sh.hlabel("BUF_OUT_T", (g(22), u1["1"][1]), "input", side="left")
    sh.wire((g(22), u1["1"][1]), u1["1"])
    # EXT_CLK -> 49.9 R termination -> B1
    sh.hlabel("EXT_CLK", (g(22), u1["3"][1]), "input", side="left")
    sh.wire((g(22), u1["3"][1]), u1["3"])
    rt = R(sh, "49.9", (g(28), u1["3"][1] + g(3)), fields={"Note": "EXT_CLK 50 R termination at U301.3"})
    sh.gnd(rt["2"])
    # TRIG_SEL -> 10 k -> SEL, 18 k to -2V5
    ysel = u1["9"][1]
    sh.hlabel("TRIG_SEL", (g(14), ysel), "input", side="left")
    rs1 = R(sh, "10k", (g(20), ysel), rot=90)
    sh.wire((g(14), ysel), rs1["1"])
    sh.wire(rs1["2"], u1["9"])
    rs2 = R(sh, "18k", (g(36), ysel + g(3)), lcsc="")
    sh.gnd(rs2["2"], dy=g(4), name="-2V5")
    sh.text("SEL: 3V3 GPIO -> -0.89 / +1.23 V\n= 0.0 / 2.1 V above VSW_GND", (g(9), ysel + g(5)), size=T)
    # A2, B2, EN to the local switch ground
    xj = u1["2"][0] - g(3)
    for p in ("2", "4", "6"):
        sh.wire(u1[p], (xj, u1[p][1]))
    sh.path([(xj, u1["2"][1]), (xj, u1["6"][1] + g(2))])
    sh.label("VSW_GND", (xj, u1["6"][1] + g(2)), rot=180)
    sh.stub(u1, "7", "VSW_GND", length=g(2))
    # VCC (+2V5) with decoupling to the switch ground
    pv = u1["10"]
    q = (pv[0], pv[1] - g(2))
    sh.wire(pv, q)
    sh.power("+2V5", q, dy=-2.54)
    cv = C(sh, "100n", (pv[0] + g(5), q[1]), rot=90)
    sh.wire(q, cv["1"])
    sh.wire(cv["2"], (cv["2"][0] + g(2), q[1]))
    sh.label("VSW_GND", (cv["2"][0] + g(2), q[1]))
    # local ground -0.9 V: 1.5 k to GND, 2.7 k to -2V5, 100 n + 1 n
    pg = u1["5"]
    yn = pg[1] + g(3)
    sh.wire(pg, (pg[0], yn))
    sh.path([(pg[0] - g(5), yn), (pg[0] + g(14), yn)])
    r15 = R(sh, "1.5k", (pg[0] - g(5), yn + g(3)), lcsc="C25867")
    sh.wire((pg[0] - g(5), yn), r15["1"])
    sh.gnd(r15["2"])
    r27 = R(sh, "2.7k", (pg[0], yn + g(3)), lcsc="")
    sh.gnd(r27["2"], dy=g(4), name="-2V5")
    c1 = C(sh, "100n", (pg[0] + g(5), yn + g(3)))
    sh.gnd(c1["2"])
    c2 = C(sh, "1n", (pg[0] + g(10), yn + g(3)), lcsc="C1523", fields={"Note": "C0G, at U301.5"})
    sh.gnd(c2["2"])
    sh.label("VSW_GND", (pg[0] + g(14), yn))
    sh.add(TP, "TP", "VSW_GND", (pg[0] + g(14), yn), fp=TP_FP)
    sh.text("VSW_GND = -2.5 x 1.5k/4.2k = -0.89 V (switch ground)\nVCC-GND = 3.4 V; ramp 100-1000 us/V",
            (pg[0] - g(8), yn + g(12)), size=T)

    # ================================================================== TLV3801
    tlv = ic_symbol("TLV3801", left=[("5", "IN+", "input"), ("4", "IN-", "input")],
                    right=[("8", "OUT+", "output"), ("1", "OUT-", "output")],
                    top=[("6", "VCC", "power_in"), ("7", "VCC", "power_in")],
                    bottom=[("2", "GND", "power_in"), ("3", "VEE", "power_in"), ("9", "EP", "passive")],
                    footprint=WSON, description="225 ps comparator, LVDS out", width=17.78)
    xt = 88
    u2 = sh.add(tlv, "U302", "TLV3801", (g(xt), yS + g(2)), fp=WSON, lcsc="C3658765", mpn="TLV3801DSGR",
                fields={"Price": "5.13 USD (Mouser)"})
    sh.wire(u1["8"], u2["5"])
    # TRIG_LEVEL -> IN-, 10 nF
    ym = u2["4"][1]
    sh.hlabel("TRIG_LEVEL", (g(68), ym + g(6)), "input", side="left")
    sh.path([(g(68), ym + g(6)), (g(74), ym + g(6)), (g(74), ym), u2["4"]])
    dec_down((g(74), ym + g(6)), g(77), "10n")
    sh.add(TP, "TP", "TRIG_LEVEL", (g(71), ym + g(6)), fp=TP_FP)
    # supplies
    a, b = u2["6"], u2["7"]
    sh.wire(a, (a[0], a[1] - g(2)))
    sh.wire(b, (b[0], b[1] - g(2)))
    sh.wire((a[0], a[1] - g(2)), (b[0], b[1] - g(2)))
    sh.power("+2V5", (a[0], a[1] - g(2)), dy=-2.54)
    dec_up((b[0], b[1] - g(2)), b[0] + g(4))
    c = dec_up((b[0] + g(4), b[1] - g(2)), b[0] + g(8))
    sh.text("1 x 100n per VCC pin", (b[0] + g(10), b[1] - g(6)), size=T)
    sh.gnd(u2["2"])
    pe, px = u2["3"], u2["9"]
    sh.wire(pe, (pe[0], pe[1] + g(3)))
    sh.path([px, (px[0], pe[1] + g(3)), (pe[0], pe[1] + g(3))])
    sh.power("-2V5", (pe[0], pe[1] + g(3)), dy=g(6))
    c = C(sh, "100n", (px[0] + g(4), pe[1] + g(6)))
    sh.wire((px[0], pe[1] + g(3)), (c["1"][0], pe[1] + g(3)))
    sh.wire((c["1"][0], pe[1] + g(3)), c["1"])
    sh.gnd(c["2"])
    sh.text("EP -> VEE", (px[0] + g(6), pe[1] + g(1)), size=T)
    # outputs: 100 R across
    op, on = u2["8"], u2["1"]
    xr = op[0] + g(3)
    r100 = R(sh, "100", (xr, op[1] + g(3)), lcsc="C25076", fields={"Note": "at the U302 pins"})
    sh.wire(op, r100["1"])
    nN = (xr, op[1] + g(6))
    sh.path([on, (on[0] + g(1), on[1]), (on[0] + g(1), nN[1]), nN])
    xP_end = xr + g(10)
    sh.wire(r100["1"], (xr + g(4), op[1]))
    sh.label("CMP_P", (xr + g(1), op[1]))
    sh.label("CMP_N", (xr + g(1), nN[1]))

    # ================================================================== line driver TRF37D73
    trf = ic_symbol("TRF37D73", left=[("2", "RFIN", "input"), ("5", "PWDN", "input")],
                    right=[("7", "RFOUT", "output")], top=[("1", "VCC", "power_in")],
                    bottom=[("3", "NC", "passive"), ("4", "NC", "passive"), ("9", "GND", "power_in"),
                            ("6", "NC", "passive"), ("8", "NC", "passive")],
                    footprint=WSON, description="1-6 GHz RF gain block, 50 R", width=25.4)
    u3 = sh.add(trf, "U303", "TRF37D73", (g(140), yS + g(2)), fp=WSON, lcsc="C2151367", mpn="TRF37D73IDSGR",
                fields={"Price": "1.50 USD (LCSC)"})
    cin = C(sh, "1u", (g(124), yS), rot=90, fields={"Note": "X7R 0402, DC block"})
    sh.wire((xr + g(4), yS), cin["1"])
    sh.wire(cin["2"], u3["2"])
    pw = u3["5"]
    sh.wire(pw, (pw[0] - g(2), pw[1]))
    sh.gnd((pw[0] - g(2), pw[1]))
    bot = [u3[p] for p in ("3", "4", "9", "6", "8")]
    yb = bot[0][1] + g(2)
    for p in bot:
        sh.wire(p, (p[0], yb))
    sh.wire((bot[0][0], yb), (bot[-1][0], yb))
    sh.gnd((u3["9"][0], yb))
    pv = u3["1"]
    sh.wire(pv, (pv[0], pv[1] - g(2)))
    sh.power("+3V3", (pv[0], pv[1] - g(2)), dy=-2.54)
    dec_up((pv[0], pv[1] - g(2)), pv[0] - g(8))
    # output choke: RFOUT -> 120 nH (high SRF) -> 47 uH -> +3V3
    po = u3["7"]
    xo = po[0] + g(3)
    l1 = sh.add("Device:L", "L", "120n", (xo, po[1] - g(4)), fp="Inductor_SMD:L_0402_1005Metric",
                fields={"Note": "high-SRF section at the pin (> 2 GHz SRF, e.g. Murata LQG15/LQW15)"})
    l2 = sh.add("Device:L", "L", "47u", (xo, po[1] - g(11)), fp="Inductor_SMD:L_1008_2520Metric",
                fields={"Note": "Isat >= 100 mA, e.g. Murata LQH2MCN470K02 (verify)"})
    sh.wire(po, (xo, po[1]))
    sh.wire((xo, po[1]), l1["2"])
    sh.wire(l1["1"], l2["2"])
    pt = l2["1"]
    sh.power("+3V3", pt, dy=-2.54)
    dec_up(pt, pt[0] + g(5))
    # 1 uF -> 12 dB pi pad 82/91/82
    cout = C(sh, "1u", (xo + g(5), po[1]), rot=90, fields={"Note": "X7R 0402, DC block"})
    sh.wire((xo, po[1]), cout["1"])
    xa = xo + g(10)
    sh.wire(cout["2"], (xa, po[1]))
    rp1 = R(sh, "82", (xa, po[1] + g(3)), fields={"Note": "12 dB pi pad, 1 %"})
    sh.gnd(rp1["2"])
    rp2 = R(sh, "91", (xa + g(5), po[1]), rot=90, fields={"Note": "12 dB pi pad, 1 %"})
    sh.wire((xa, po[1]), rp2["1"])
    xb = xa + g(10)
    sh.wire(rp2["2"], (xb, po[1]))
    rp3 = R(sh, "82", (xb, po[1] + g(3)), fields={"Note": "12 dB pi pad, 1 %"})
    sh.gnd(rp3["2"])

    # ================================================================== CMP_N dummy load, LVDS receiver
    xn = xr + g(5)
    cn = C(sh, "1u", (xn + g(3), nN[1]), rot=90, fields={"Note": "X7R 0402"})
    sh.wire(nN, cn["1"])
    rdm = R(sh, "49.9", (cn["2"][0] + g(4), nN[1] + g(3)), fields={"Note": "dummy load = TRF input (equal load)"})
    sh.wire(cn["2"], rdm["1"])
    sh.gnd(rdm["2"])
    lv = ic_symbol("SN65LVDS2", left=[("3", "A", "input"), ("4", "B", "input")], right=[("5", "R", "output")],
                   top=[("1", "VCC", "power_in")], bottom=[("2", "GND", "power_in")],
                   footprint="Package_TO_SOT_SMD:SOT-23-5", description="LVDS receiver")
    u4 = sh.add(lv, "U304", "SN65LVDS2", (g(140), yS + g(32)), fp="Package_TO_SOT_SMD:SOT-23-5", lcsc="C38204",
                mpn="SN65LVDS2DBVR", fields={"Price": "0.54 USD (LCSC)"})
    ya, yb2 = u4["3"][1], u4["4"][1]
    xpa, xnb = xr + g(2), xr - g(0)
    # CMP_P tap (crosses CMP_N), CMP_N tap
    ra = R(sh, "470", (g(120), ya - g(3)), rot=90, fields={"Note": "bridge, at the U302 pins"})
    rb = R(sh, "470", (g(120), yb2 + g(3)), rot=90, fields={"Note": "bridge, at the U302 pins"})
    sh.path([(g(114), yS), (g(114), ra["1"][1]), ra["1"]])
    sh.path([ra["2"], (ra["2"][0] + g(2), ra["2"][1]), (ra["2"][0] + g(2), ya), u4["3"]])
    sh.path([(xr, nN[1]), (xr, rb["1"][1]), rb["1"]])
    sh.path([rb["2"], (rb["2"][0] + g(4), rb["2"][1]), (rb["2"][0] + g(4), yb2), u4["4"]])
    sh.gnd(u4["2"])
    pv = u4["1"]
    sh.wire(pv, (pv[0], pv[1] - g(2)))
    sh.power("+3V3", (pv[0], pv[1] - g(2)), dy=-2.54)
    dec_up((pv[0], pv[1] - g(2)), pv[0] + g(5))
    sh.wire(u4["5"], (u4["5"][0] + g(12), u4["5"][1]))
    sh.hlabel("COARSE", (u4["5"][0] + g(12), u4["5"][1]), "output")
    sh.add(TP, "TP", "COARSE", (u4["5"][0] + g(6), u4["5"][1]), fp=TP_FP)

    # ================================================================== delay line ladder
    cos = cos3502_symbol()
    W, X0 = 34, 48
    YL = [98, 152]
    LINE_CH = 82                           # return channel from the pad to row 1
    xl_launch = 34
    # line from the pad: right, down, left along the channel, down to row 1
    sh.path([(xb, po[1]), (xb + g(6), po[1]), (xb + g(6), g(LINE_CH)), (g(xl_launch), g(LINE_CH)),
             (g(xl_launch), g(YL[0])), (g(X0), g(YL[0]))])
    sh.add(TP, "TP", "LINE_IN", (xb + g(6), po[1]), fp=TP_FP)
    sh.text("LINE LAUNCH: pad R303-R305 at the first tap; 50 R microstrip\n"
            "(~0.18 mm on L1 over L2 GND). Drawn long here only.", (g(186), g(LINE_CH) - g(9)), size=T)
    # strobe line launch
    yA0, yK0 = YL[0] - 12, YL[0] - 9
    sh.hlabel("PSTRB_A", (g(26), g(yA0)), "input", side="left")
    sh.hlabel("PSTRB_K", (g(26), g(yK0)), "input", side="left")
    sh.text("PSTRB_A/K: 50 R strobe lines from the strobe sheet, launched at the same end as the line.",
            (g(10), g(78)), size=T)

    ref = {"D": 300, "Ca": 0}
    cmp_refs = [f"U{305 + p}" for p in range(8)]
    for r_ in range(2):
        yl = YL[r_]
        yA, yK = yl - 12, yl - 9
        first, last = X0, X0 + 7 * W
        # horizontal lines across the row (split later at the tap points)
        x_start = 26 if r_ == 0 else None
        if r_ == 0:
            sh.path([(g(26), g(yA)), (g(last + 6), g(yA))])
            sh.path([(g(26), g(yK)), (g(last + 6), g(yK))])
        sh.path([(g(first), g(yl)), (g(last + 4), g(yl))])
        for j in range(8):
            i = 8 * r_ + j
            x0 = X0 + W * j
            # gate
            d = sh.add(DUAL, "D", "BAT15-04W", P(x0, yl + 5), mirror="x", fp=DUAL_FP, lcsc="C5380972",
                       mpn="BAT1504WH6327XTSA1", fields=BAT_F)
            sh.wire(P(x0, yl), d["3"])
            pa, pk = d["1"], d["2"]                      # anode node (x0-6), cathode node (x0+6)
            # hold caps up to the strobe lines (cross the signal line)
            ca = C(sh, "0.5p", P(x0 - 9, yl - 5), lcsc="C1544", fields={"Note": "C0G 0402, hold A"})
            ck = C(sh, "0.5p", P(x0 + 9, yl - 5), lcsc="C1544", fields={"Note": "C0G 0402, hold K"})
            sh.path([pa, P(x0 - 9, yl + 5), ca["2"]])
            sh.wire(ca["1"], P(x0 - 9, yA))
            sh.path([pk, P(x0 + 9, yl + 5), ck["2"]])
            sh.wire(ck["1"], P(x0 + 9, yK))
            # readout: 2.2 k to the rails, 1 k summing
            rna = R(sh, "2.2k", P(x0 - 9, yl + 10))
            sh.wire(P(x0 - 9, yl + 5), rna["1"])
            sh.wire(rna["2"], P(x0 - 9, yl + 15))
            sh.label("VTAP_N", P(x0 - 9, yl + 15), rot=270)
            rpk = R(sh, "2.2k", P(x0 + 9, yl + 10))
            sh.wire(P(x0 + 9, yl + 5), rpk["1"])
            sh.wire(rpk["2"], P(x0 + 9, yl + 15))
            sh.label("VTAP_P", P(x0 + 9, yl + 15), rot=270)
            rsa = R(sh, "1k", P(x0 - 5, yl + 11))
            rsk = R(sh, "1k", P(x0 + 5, yl + 11))
            # 1 k tops tie to the hold nodes via the diode pin rows
            sh.path([rsa["1"], P(x0 - 5, yl + 7), P(x0 - 7, yl + 7), P(x0 - 7, yl + 5)])
            sh.path([rsk["1"], P(x0 + 5, yl + 7), P(x0 + 7, yl + 7), P(x0 + 7, yl + 5)])
            sh.path([rsa["2"], P(x0 - 5, yl + 16), P(x0 + 5, yl + 16), rsk["2"]])
            # comparator half
            p, unit = divmod(i, 2)
            u = sh.add(cos, cmp_refs[p], "COS3502", P(x0 + 6, yl + 26), unit=unit + 1,
                       fp="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", lcsc="C49304672", mpn="COS3502SR",
                       fields={"Price": "0.36 USD (LCSC)"})
            pin_p, pin_m, pin_o = ("1", "2", "7") if unit == 0 else ("3", "4", "6")
            sh.path([P(x0, yl + 16), (g(x0), u[pin_p][1]), u[pin_p]])
            sh.wire(u[pin_m], (u[pin_m][0] - g(2), u[pin_m][1]))
            sh.label(f"VTH{r_ + 1}", (u[pin_m][0] - g(2), u[pin_m][1]), rot=180)
            e = (u[pin_o][0] + g(2), u[pin_o][1])
            sh.wire(u[pin_o], e)
            sh.hlabel(f"TAP{i}", e, "output")
            sh.text(f"tap {i}", P(x0 + 1, yl - 3), size=T)
        if r_ == 0:
            # wrap: S, K, A down the right side, left along the gap, down to row 2
            xr0 = last + 24
            ym = YL[0] + 34
            yl2 = YL[1]
            xl = 36
            sh.path([P(last + 4, yl), P(xr0, yl), P(xr0, ym), P(xl - 6, ym), P(xl - 6, yl2), P(X0, yl2)])
            sh.path([P(last + 6, yK), P(xr0 + 3, yK), P(xr0 + 3, ym + 3), P(xl - 3, ym + 3), P(xl - 3, yl2 - 9),
                     P(xl + 4, yl2 - 9)])
            sh.path([P(last + 6, yA), P(xr0 + 6, yA), P(xr0 + 6, ym + 6), P(xl, ym + 6), P(xl, yl2 - 12),
                     P(xl + 4, yl2 - 12)])
            sh.path([P(xl + 4, yl2 - 12), P(last + 6, yl2 - 12)])
            sh.path([P(xl + 4, yl2 - 9), P(last + 6, yl2 - 9)])
        else:
            # terminations
            for (yy, xx, net) in ((yl, last + 14, "line"), (yK, last + 20, "PSTRB_K"), (yA, last + 26, "PSTRB_A")):
                sh.wire(P(last + (4 if yy == yl else 6), yy), P(xx, yy))
                rr = R(sh, "49.9", P(xx, yy + 3), fields={"Note": f"{net} end termination, at the last tap"})
                sh.gnd(rr["2"])
            sh.text("END TERMINATIONS\n49.9 R 0402 to GND\n(L2 via at the pad)", P(last + 10, yl + 12), size=T)

    # ================================================================== comparator power, VTAP_TH, rails
    yb0 = 200
    for p in range(8):
        x = 46 + 18 * p
        u = sh.add(cos, cmp_refs[p], "COS3502", P(x, yb0), unit=3, fp="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                   lcsc="C49304672", mpn="COS3502SR", fields={"Price": "0.36 USD (LCSC)"})
        sh.power("+3V3", u["8"], dy=-2.54)
        sh.wire(u["5"], (u["5"][0], u["5"][1] + g(3)))
        sh.gnd((u["5"][0], u["5"][1] + g(3)))
        c = C(sh, "100n", (u["8"][0] + g(10), u["8"][1] + g(3)))
        sh.path([u["8"], (c["1"][0], u["8"][1]), c["1"]])
        sh.gnd(c["2"])
    sh.text("COS3502 (U305-U312) on +3V3/GND, 100 nF X7R at each pin 8. Pinout NOT TLV3502: 1 +INA, 2 -INA,\n"
            "3 +INB, 4 -INB, 5 V-, 6 OUTB, 7 OUTA, 8 V+ (Cosine datasheet rev 1.0). Tap 2p -> unit A, 2p+1 -> B.",
            P(42, 216), size=T)
    # VTAP_TH: 1 k + 100 nF per row
    xth = 191
    sh.hlabel("VTAP_TH", P(xth, 196), "input", side="left")
    sh.path([P(xth, 196), P(xth + 2, 196), P(xth + 2, 208)])
    for k in range(2):
        yy = 196 + 12 * k
        r = R(sh, "1k", P(xth + 7, yy), rot=90)
        sh.wire(P(xth + 2, yy), r["1"])
        sh.wire(r["2"], P(xth + 16, yy))
        dec_down(P(xth + 12, yy), g(xth + 12))
        sh.label(f"VTH{k + 1}", P(xth + 16, yy))
    sh.add(TP, "TP", "VTAP_TH", P(xth + 2, 203), fp=TP_FP)
    sh.text("VTH1: taps 0-7, VTH2: taps 8-15\nVTAP_TH 0..+80 mV (+17 mV, phase_array)", P(150, 220), size=T)
    # VTAP_P / VTAP_N rails: hierarchical labels + local labels, 1 uF + 100 nF each
    for k, (net, gnd_rot) in enumerate((("VTAP_P", 0), ("VTAP_N", 0))):
        yy = 186 + 14 * k
        x = 214
        sh.hlabel(net, P(x, yy), "input", side="left")
        sh.wire(P(x, yy), P(x + 12, yy))
        sh.label(net, P(x + 12, yy))
        dec_down(P(x + 4, yy), g(x + 4), "1u")
        dec_down(P(x + 8, yy), g(x + 8), "100n")
    sh.text("VTAP_P/N = +/-2.5 V\n12.5 mA each", P(212, 216), size=T)

    # ================================================================== annotations
    sh.text("TRIGGER (sim/phase/RESULT.md (f)): TMUX136 on local -0.9 V ground, VCC +2V5.\n"
            "A1 = BUF_OUT_T (signal, high-Z end of the 50 R line), B1 = EXT_CLK (SMA on the input sheet,\n"
            "49.9 R here at U301.3). Signal +/-0.5 V = 0.4..1.4 V above switch GND. Ron unspecified there.",
            P(10, 10), size=T)
    sh.text("TLV3801: +/-2V5, GND pin to GND, LVDS-type out.\n100 R R3xx across OUT+/OUT- at the pins\n"
            "(350 mV VOD, 25 R per leg at HF). Trace to\nTRF/LVDS2 short (< 5 mm, ~30 ps).",
            P(78, 10), size=T)
    sh.text("LINE DRIVER: TRF37D73 22 dB, 50 R in/out.\nBias via 120 nH (at pin) + 47 uH, tau 1.9 us.\n"
            "12 dB pad 82/91/82: line +/-0.21 V (data),\n0.42 V steps; 10-90 % 225-250 ps at the taps.",
            P(165, 10), size=T)
    sh.text("COARSE: 2 x 470 R bridge (high-Z tap,\nTRF input drop < 5 %). SN65LVDS2 at 3V3\n"
            "-> FPGA pin 47. Good to ~100-150 MHz edges.", P(148, 72), size=T)
    sh.text("DELAY LINE (SPEC decision 4, co-propagating): signal line 70 ps per tap (73 R trace, meander between\n"
            "taps, loaded to ~50 R by each gate ~0.37 pF); strobe lines PSTRB_A/K 35 ps per tap (73 R trace,\n"
            "3.5 mm pitch, loaded); effective tap spacing 70 - 35 = 35 ps, 16 taps = 560 ps window.\n"
            "Gate: BAT15-04W pin 3 on the line (stub < 0.3 mm), 0.47 pF C0G hold caps to PSTRB_A (anode)\n"
            "/ PSTRB_K (cathode). Strobe >= 2.75 V per side with the 80 ps launch stub (~4 V launch), FWHM 220-320 ps.\n"
            "phase_array RESULT: line measured 75.7 ps/tap with the 70 ps design -> make the meander ~5 ps shorter.",
            P(232, 26), size=T)
    sh.text("READOUT: 2.2 k to VTAP_N (A node) / VTAP_P (K node),\n2 x 1 k summing to COS3502 IN+, IN- = VTH (VTAP_TH).\n"
            "Hold nodes and the 1 k < 2 mm from the diode; comparator\nnext to its gate. Rising edges only, VTAP_TH ~ +17 mV.\n"
            "FPGA samples TAP[15:0] at strobe + 12 ns (10-22 ns); 50 % duty OK\n(reverse pulse < 0.5 mV; 70 % optional).", P(232, 54), size=T)
    sh.text("line 70 ps/tap", P(X0 + 11, YL[0] + 1), size=T)
    sh.text("strobe lines PSTRB_A / PSTRB_K: 35 ps/tap each", P(X0 + 12, YL[0] - 14.5), size=T)

    names = {n for n, _ in hier_pins("trigger_phase")}
    split_wires(sh)
    sh.save()
    return names


def check(outdir):
    n = schlib.nets(os.path.join(schlib.OUTDIR, "trigger_phase.kicad_sch"), os.path.join(outdir, "trigger_phase.net"))
    on = lambda *m: next(k for k, v in n.items() if set(m) <= v)
    print("A1", on(("U301", "1")), "B1", on(("U301", "3")), "SEL", on(("U301", "9")))
    print("COM1-IN+", on(("U301", "8"), ("U302", "5")))
    print("IN-", on(("U302", "4")))
    print("VSW", on(("U301", "5"), ("U301", "6"), ("U301", "2"), ("U301", "4"), ("U301", "7")))
    print("CMP_P", on(("U302", "8")), sorted(n[on(("U302", "8"))]))
    print("CMP_N", on(("U302", "1")), sorted(n[on(("U302", "1"))]))
    print("RFIN", sorted(n[on(("U303", "2"))]))
    print("RFOUT", sorted(n[on(("U303", "7"))]))
    print("LVDS A", sorted(n[on(("U304", "3"))]), "B", sorted(n[on(("U304", "4"))]))
    print("COARSE", on(("U304", "5")))
    line = on(("D301", "3"))
    print("LINE", line, sorted(x for x in n[line]))
    for k in ("VTAP_P", "VTAP_N", "VTAP_TH", "PSTRB_A", "PSTRB_K", "VTH1", "VTH2", "-2V5", "+3V3", "+2V5"):
        c = [x for x in n if x.endswith(k)]
        print(k, [(x, len(n[x])) for x in c])
    for i in range(16):
        u = on(("D%d" % (301 + i), "1"))
        print(i, on(("D%d" % (301 + i), "3")) == line, len(n[u]), n[u], on(*[x for x in n[on(("D%d" % (301 + i), "2"))]][:1]))


if __name__ == "__main__":
    main()
    if "--check" in sys.argv:
        check(sys.argv[sys.argv.index("--check") + 1])
