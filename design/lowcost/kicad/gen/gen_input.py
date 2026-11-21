"""input.kicad_sch: SIG_IN SMA (no on-board termination), fixed 5:1 compensated divider (1 Mohm),
BUF802 in composite-loop (CL) mode with OPA197 differential-integrator servo, output 49.9R to BUF_OUT_T,
EXT_CLK SMA.

Values: design/lowcost/sim/input/RESULT.md (final network) and SPEC decisions 1 and 7.
VOFS (21 Nov 2026): the directly driven summing node of sim/input again. VOFS is the raw STM32 DAC1_OUT2
(0.2..2.7 V) through Rofs 24.9k; the mid-scale is cancelled by Rmid 34.0k (R123) from VNEG_REF (-1.973 V =
-0.680 x VREF+, U701 on mcu_if, ratiometric to the DAC) instead of from the -2V5 rail. Gsum = 1/Rf1 + 1/Rf2 +
1/Rofs + 1/Rmid = 2/Rf1 with Rf2 nominal 32.9k = 22.1k + RV101 ~10.8k (LF gain 0.200, trim -8.3 %..+7.4 %).

BUF802 pinout (TI SBOS998E, Table 4-1, RGT VQFN-16 3x3, EP 1.68 mm isolated from the die):
1 VS+, 2 IN, 3 In_Bias, 4 In_Aux, 5 VS-, 6 Aux_Bias, 7 R_Bias, 8 VS-, 9 NC, 10 VSO-, 11 OUT,
12 VSO+, 13 NC, 14 CLL, 15 CLH, 16 NC. R_Bias resistor goes to VS-.
No switchable 50R termination (SPEC decision 10): a user who needs 50R fits an external SMA feed-through
terminator. R101..R103 and K101 are unused references (removed termination)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schlib import g, ic_symbol, nets, assert_net, OUTDIR
from common import new_sheet, R, C, decoupler, hier_pins

TS = 1.0          # annotation text size
BUF_FP = "Package_DFN_QFN:VQFN-16-1EP_3x3mm_P0.5mm_EP1.68x1.68mm"
SMA_FP = "Connector_Coaxial:SMA_Samtec_SMA-J-P-X-ST-EM1_EdgeMount"
TP_FP = "TestPoint:TestPoint_Pad_D1.0mm"


def buf802_symbol():
    lid = ic_symbol(
        "BUF802",
        left=[("2", "IN", "input"), None, None, None, None, None, ("3", "In_Bias", "input"), None,
              ("7", "R_Bias", "input")],
        right=[("11", "OUT", "output"), None, ("9", "NC", "no_connect"), ("13", "NC", "no_connect"),
               ("16", "NC", "no_connect")],
        top=[("15", "CLH", "input"), None, None, ("1", "VS+", "power_in"), None, None,
             ("12", "VSO+", "power_in")],
        bottom=[("4", "In_Aux", "input"), None, ("6", "Aux_Bias", "passive"), None, ("5", "VS-", "power_in"),
                None, ("8", "VS-", "power_in"), None, ("10", "VSO-", "power_in"), None,
                ("14", "CLL", "input"), None, ("17", "EP", "passive")],
        footprint=BUF_FP, datasheet="https://www.ti.com/lit/ds/symlink/buf802.pdf",
        description="BUF802 3.1 GHz JFET-input buffer, RGT VQFN-16 (pin 17 = thermal pad, isolated)")
    from schlib import CUSTOM, find, Q
    for p in find(CUSTOM[lid], "property"):          # value text in the body centre (bottom has pins)
        if p[1] == "Value":
            p[3] = ["at", "0", "0", "0"]
            p[4] = ["effects", ["font", ["size", "1.27", "1.27"]]]
    return lid


def tp(sh, at, name):
    t = sh.add("Connector:TestPoint", "TP", name, at, fp=TP_FP)
    return t


def split_wires(sh):
    """KiCad connects a pin or wire end only at wire ends: split every wire at each pin, wire end and
    label point that lies on its interior (the library adds the junction dots)."""
    pts = set()
    for a_, b_ in sh.wires:
        pts.update((a_, b_))
    for s_ in sh.symbols:
        for p in s_.pins:
            if p.hidden and p.type == "power_in" and not s_.power:
                continue
            pts.add(s_.pin(p.number))
    pts.update(sh.label_pts)
    out = []
    for a_, b_ in sh.wires:
        inner = sorted((p for p in pts if sh._on_mid(p, a_, b_)),
                       key=lambda p: abs(p[0] - a_[0]) + abs(p[1] - a_[1]))
        chain = [a_] + inner + [b_]
        out += list(zip(chain, chain[1:]))
    sh.wires = out


def main():
    sh = new_sheet("input", comments=[
        "Values: sim/input/RESULT.md (final network), SPEC decisions 1 and 7.",
        "Refs 1xx. PCB: 4 layers JLC04161H-7628, L2 solid GND, 0402 unless noted."])
    Y0 = g(46)                     # HF signal row
    Ys = Y0 + g(42)                # servo row

    # ------------------------------------------------------------------ SIG_IN SMA and VIN line
    j1 = sh.add("Connector:Conn_Coaxial", "J", "SIG_IN", (g(10), Y0), mirror="y", fp=SMA_FP,
                mpn="SMA edge-launch 50R (Samtec SMA-J-P-H-ST-EM1 or equivalent)")
    sh.gnd(j1["2"])
    VINX = g(87)                   # Ctop left pin
    sh.wire(j1["1"], (VINX, Y0))
    sh.label("VIN", (g(18), Y0))
    sh.text("J101 SIG_IN, edge-launch SMA.\nVIN: 50R microstrip on L1 over L2 GND,\n"
            "w 0.36 mm (7628 prepreg 0.21 mm),\n6 mm (~37 ps) to the Ctop pad.\n"
            "GND stitching vias along the line.", (g(4), Y0 - g(22)), size=TS)

    # ------------------------------------------------------------------ no termination (user decision)
    # The switchable 50R termination (K101 HFD3/3, 2 x 100R, coil 39R) was removed: SMA -> divider directly.
    # R101..R103 stay unused so the remaining references (and the layout fragment) do not shift.
    sh._refn["R"] = 3
    sh.text("No on-board 50R termination.\n50 ohm: use an external SMA feed-through\n"
            "terminator; input is 1 Mohm || ~3 pF.", (g(26), Y0 + g(8)), size=TS)

    # ------------------------------------------------------------------ HF divider and BUF802
    buf = buf802_symbol()
    Bx, By = g(130), Y0 + g(8)
    u1 = sh.add(buf, "U", "BUF802IRGTR", (Bx, By), fp=BUF_FP, lcsc="C4370628", mpn="BUF802IRGTR",
                fields={"Price": "5.89 USD (LCSC)"})
    ctop = C(sh, "1.5p", (g(90), Y0), rot=90, size="0402",
             fields={"Note": "C0G +/-0.05 pF 100 V"})
    GA = (g(96), Y0)
    sh.wire(ctop["2"], GA)
    cbot = C(sh, "3.3p", (g(96), Y0 + g(6)), size="0402", fields={"Note": "C0G +/-0.1 pF"})
    sh.wire(GA, cbot["1"])
    sh.gnd(cbot["2"])
    rg = R(sh, "10", (g(104), Y0), rot=90)
    sh.wire(GA, rg["1"])
    sh.label("GA", (g(96), Y0))
    XN = g(110)
    sh.wire(rg["2"], u1["2"])
    rb1 = R(sh, "4.99M", (XN, Y0 + g(3)))
    rb2 = R(sh, "4.99M", (XN, Y0 + g(9)))
    sh.wire(rb1["2"], rb2["1"])
    sh.path([rb2["2"], u1["3"]])
    sh.text("HF 5:1: Ctop 1.5p / Cbot 3.3p, k = 1.53/(1.53+3.3+2.4+0.3) = 0.206,\n"
            "x G 0.971 = 0.200. Ctop-GA-Rg-IN node as small as possible (pads\n"
            "~0.3 pF are part of k). Rg 10R (22-33R if step overshoot, RESULT op. 1).",
            (g(70), Y0 - g(35)), size=TS)

    # R_Bias, Aux_Bias, supplies
    pr = u1["7"]
    rbias = R(sh, "17.8k", (g(106), pr[1] + g(3) + g(2)), fields={"Note": "1 %"})
    sh.path([pr, (g(106), pr[1]), rbias["1"]])
    sh.power("-5V", rbias["2"], dy=5.08)
    yb = u1["6"][1] + g(3)
    for pin in ("6", "5", "8", "10"):
        sh.wire(u1[pin], (u1[pin][0], yb))
    sh.path([(u1["6"][0], yb), (u1["10"][0], yb)])
    sh.power("-5V", (u1["8"][0], yb), dy=2.54)
    sh.stub(u1, "17", "GND", kind="gnd")
    for pin in ("1", "12"):
        sh.stub(u1, pin, "+5V", kind="power")
    for pin in ("9", "13", "16"):
        sh.nc(u1[pin])
    sh.text("U101 CL mode: Aux_Bias = VS-,\nR_Bias 17.8k (wide-BW mode).\nEP isolated -> GND plane.",
            (g(160), Y0 + g(8)), size=TS)

    # CLH divider (+1.5 V from +2V5)
    pc = u1["15"]
    NH = (pc[0], Y0 - g(16))
    sh.wire(pc, NH)
    rh1 = R(sh, "1k", (g(118), NH[1] - g(3)), lcsc="C11702")
    sh.power("+2V5", rh1["1"], dy=-2.54)
    sh.path([rh1["2"], NH])
    rh2 = R(sh, "1.5k", (g(112), NH[1] + g(3)))
    sh.path([NH, (g(112), NH[1]), rh2["1"]])
    sh.gnd(rh2["2"])
    ch = C(sh, "1u", (g(106), NH[1] + g(3)))
    sh.path([(g(112), NH[1]), (g(106), NH[1]), ch["1"]])
    sh.gnd(ch["2"])
    tp(sh, (g(132), NH[1]), "CLH")
    sh.wire(NH, (g(132), NH[1]))
    sh.text("CLH = +1.5 V", (g(136), NH[1] - g(2)), size=TS)

    # CLL divider (-1.5 V from -2V5)
    pl = u1["14"]
    NL = (pl[0], Y0 + g(32))
    sh.wire(pl, NL)
    rl1 = R(sh, "1k", (pl[0], NL[1] + g(3)), lcsc="C11702")
    sh.wire(NL, rl1["1"])
    sh.power("-2V5", rl1["2"], dy=5.08)
    rl2 = R(sh, "1.5k", (pl[0] + g(6), NL[1] + g(3)))
    sh.path([NL, (rl2["1"][0], NL[1]), rl2["1"]])
    sh.gnd(rl2["2"])
    cl = C(sh, "1u", (pl[0] + g(12), NL[1] + g(3)))
    sh.path([(rl2["1"][0], NL[1]), (cl["1"][0], NL[1]), cl["1"]])
    sh.gnd(cl["2"])
    tp(sh, (pl[0] - g(4), NL[1]), "CLL")
    sh.wire(NL, (pl[0] - g(4), NL[1]))
    sh.text("CLL = -1.5 V. Clamps: OUT within +/-1.5 V,\ninput diodes to CLH/VS- (100 mA max).",
            (pl[0] - g(10), NL[1] + g(12)), size=TS)

    # ------------------------------------------------------------------ output: BUF_OUT_S / BUF_OUT_T
    po = u1["11"]
    A = (g(150), Y0)
    sh.wire(po, A)
    sh.path([A, (A[0], Y0 - g(4)), (A[0] + g(2), Y0 - g(4))])
    sh.hlabel("BUF_OUT_S", (A[0] + g(2), Y0 - g(4)), "output", side="right")
    FBT = (g(158), Y0)
    r499 = R(sh, "49.9", (g(168), Y0), rot=90, fields={"Note": "1 %, at the OUT pin"})
    sh.wire(A, r499["1"])
    rser = R(sh, "0", (g(180), Y0), rot=90, lcsc="C17168",
             fields={"Note": "series position: 0R / ferrite (BLM15) / 100R vs strobe kick-out"})
    sh.wire(r499["2"], rser["1"])
    E = (g(192), Y0)
    sh.wire(rser["2"], E)
    sh.hlabel("BUF_OUT_T", E, "output", side="right")
    sh.text("BUF_OUT_S = U101 OUT node: 10R + sampler bridge on the sampler\n"
            "sheet, bridge within 3 mm of the OUT pin (Zout 1.2R + 0.3 nH).\n"
            "49.9R directly at the OUT pin, then 0R/ferrite/100R position.\n"
            "BUF_OUT_T: 50R microstrip (0.36 mm, 6.06 ps/mm) to TMUX136\n"
            "(high-impedance end, trigger_phase): no termination at the far\n"
            "end, keep it short (< 30 mm, ~180 ps), no stubs.",
            (g(156), Y0 - g(22)), size=TS)

    # ------------------------------------------------------------------ servo: alpha divider
    TX = g(22)
    sh.path([(TX, Y0), (TX, Ys)])
    x = TX
    prev = (TX, Ys)
    for cx in (g(28), g(36), g(44)):
        r = R(sh, "300k", (cx, Ys), rot=90, fields={"Note": "0.1 %, 0402 50 V"})
        sh.wire(prev, r["1"])
        prev = r["2"]
    TAP = (g(52), Ys)
    sh.wire(prev, TAP)
    sh.label("TAP", (g(48), Ys))
    r100 = R(sh, "100k", (g(52), Ys + g(3)), lcsc="C25741", fields={"Note": "0.1 %"})
    sh.wire(TAP, r100["1"])
    sh.gnd(r100["2"])
    cp = C(sh, "18p", (g(58), Ys + g(3)), fields={"Note": "C0G"})
    sh.path([TAP, (g(58), Ys), cp["1"]])
    sh.gnd(cp["2"])

    # OPA197 integrator
    Ox = g(76)
    u2 = sh.add("Amplifier_Operational:OPA197xDBV", "U", "OPA197IDBVR", (Ox, Ys + 2.54),
                fp="Package_TO_SOT_SMD:SOT-23-5", lcsc="C221351", mpn="OPA197IDBVR",
                fields={"Price": "0.75 USD (LCSC)"})
    sh.wire((g(58), Ys), u2["3"])
    sh.stub(u2, "5", "+5V", kind="power")
    sh.stub(u2, "2", "-5V", kind="power")
    FBX = g(66)
    pm = u2["4"]
    sh.path([pm, (FBX, pm[1]), (FBX, Ys + g(28))])
    sh.label("FB", (FBX, pm[1]), rot=180)
    po2 = u2["1"]
    OX2 = g(86)
    # Cint OUT -> FB
    cint = C(sh, "470p", (Ox, Ys + g(16)), rot=90, size="0402", fields={"Note": "C0G"})
    sh.wire((FBX, cint["1"][1]), cint["1"])
    sh.path([cint["2"], (OX2, cint["2"][1]), (OX2, po2[1])])
    # Rf1 from BUF802 OUT
    rf1 = R(sh, "10.0k", (Ox, Ys + g(21)), rot=90, lcsc="C25744", fields={"Note": "0.1 %"})
    sh.wire((FBX, rf1["1"][1]), rf1["1"])
    sh.path([rf1["2"], (FBT[0], rf1["2"][1]), FBT])
    # Rofs from VOFS
    rofs = R(sh, "24.9k", (g(58), Ys + g(24)), rot=90, fields={"Note": "0.1 % 25 ppm/K"})
    sh.wire(rofs["2"], (FBX, rofs["2"][1]))
    sh.wire(rofs["1"], (g(50), rofs["1"][1]))
    sh.hlabel("VOFS", (g(50), rofs["1"][1]), "input", side="left")
    # Rmid from VNEG_REF (explicit ref: the auto-numbered refs after it stay as they were)
    rmid = R(sh, "34.0k", (g(58), Ys + g(27)), rot=90, ref="R123", fields={"Note": "0.1 % 25 ppm/K"})
    sh.wire(rmid["2"], (FBX, rmid["2"][1]))
    sh.wire(rmid["1"], (g(50), rmid["1"][1]))
    sh.hlabel("VNEG_REF", (g(50), rmid["1"][1]), "input", side="left")
    # Rf2 = 22.1k + 50k trimmer (rheostat) to GND
    rf2 = R(sh, "22.1k", (FBX, Ys + g(31)), fields={"Note": "0.1 %"})
    sh.wire((FBX, Ys + g(28)), rf2["1"])
    rv = sh.add("Device:R_Potentiometer_Trim", "RV", "50k", (FBX, Ys + g(40)),
                fp="Potentiometer_SMD:Potentiometer_Bourns_3314J_Vertical", mpn="Bourns 3314J-1-503E")
    sh.wire(rf2["2"], rv["1"])
    sh.path([rv["2"], (rv["2"][0] + g(2), rv["2"][1]), (rv["2"][0] + g(2), rv["3"][1] + g(2)),
             (rv["3"][0], rv["3"][1] + g(2))])
    sh.wire(rv["3"], (rv["3"][0], rv["3"][1] + g(2)))
    sh.gnd((rv["3"][0], rv["3"][1] + g(2)))
    # OPA out -> Raux -> In_Aux, Caux
    raux = R(sh, "1k", (g(100), po2[1]), rot=90, lcsc="C11702")
    sh.wire(po2, raux["1"])
    tp(sh, (g(92), po2[1]), "SERVO")
    pa = u1["4"]
    sh.path([raux["2"], (pa[0], po2[1]), pa])
    caux = C(sh, "100p", (g(110), po2[1] + g(3)), size="0402", fields={"Note": "C0G"})
    sh.wire((g(110), po2[1]), caux["1"])
    sh.gnd(caux["2"])
    sh.label("IN_AUX", (g(112), po2[1]))

    sh.text("Servo (differential integrator, OPA197 on +/-5 V):\n"
            "LF 5:1 alpha = 100k/(3x300k+100k) = 0.100, Rin 1.000 Mohm,\n"
            "0.1 % 0402 string (3 x 50 V: +/-50 V peak). Tap the string at\n"
            "the VIN pad with the first 300k, keep it off the 50R line.\n"
            "Cp 18p: tap RC 90k x 26 pF = Rpar x Cint, cancels feed-through.\n"
            "Loop BW = Ga/(2 pi Rf1 Cint) = 8.8 kHz.",
            (g(4), Ys + g(31)), size=TS)
    sh.text("FB node: Gsum = 1/Rf1 + 1/Rf2 + 1/Rofs + 1/Rmid = 2/Rf1\n"
            "-> LF gain alpha x Rf1 x Gsum = 0.200 (= HF gain).\n"
            "Rf2 nominal 32.9k = 22.1k + RV ~10.8k (range -8.3 %..+7.4 %).\n"
            "Trim once: 1 kHz square wave, flat top LF = HF.\n"
            "VOFS = DAC1_OUT2 0.2..2.7 V via Rofs 24.9k, mid-scale\n"
            "cancelled by Rmid 34.0k from VNEG_REF (-1.973 V, mcu_if):\n"
            "OUT offset = 0.580 - 0.402 x VOFS = +0.50..-0.50 V\n"
            "(+/-2.5 V at the input), 0.28 mV/LSB at OUT. VOFS and\n"
            "VNEG_REF must be quiet below 10 kHz (gain 0.4 / 0.29 to OUT).",
            (g(74), Ys + g(28)), size=TS)

    # ------------------------------------------------------------------ decoupling
    decoupler(sh, "+5V", (g(204), g(30)), ("100n", "100n", "100n", "10u"))
    sh.text("+5V: C at U101 pin 1 (VS+), pin 12 (VSO+),\nU102 pin 5; 10u bulk. 0402 at the pins, via to L2.",
            (g(200), g(16)), size=TS)
    decoupler(sh, "-5V", (g(204), g(66)), ("100n", "100n", "100n", "100n", "10u"))
    sh.text("-5V: C at U101 pin 5, pin 8 (VS-), pin 10 (VSO-),\nU102 pin 2; 10u bulk.",
            (g(200), g(52)), size=TS)
    sh.text("+2V5/-2V5 (clamp dividers): 1u at CLH/CLL nodes.", (g(200), g(80)), size=TS)

    # ------------------------------------------------------------------ EXT_CLK SMA
    YE = g(176)
    j2 = sh.add("Connector:Conn_Coaxial", "J", "EXT_CLK", (g(10), YE), mirror="y", fp=SMA_FP,
                mpn="SMA edge-launch 50R (Samtec SMA-J-P-H-ST-EM1 or equivalent)")
    sh.gnd(j2["2"])
    rt = R(sh, "49.9", (g(30), YE + g(4)), dnp=True, fields={"Note": "DNP unless trigger_phase has no 50R"})
    sh.wire(j2["1"], (g(44), YE))
    sh.wire((g(30), YE), rt["1"])
    sh.gnd(rt["2"])
    sh.hlabel("EXT_CLK", (g(44), YE), "output", side="right")
    sh.text("J102 EXT_CLK: 50R microstrip to TMUX136 B input (trigger_phase).\n"
            "Termination at the far end preferred; R near the SMA only as DNP option.",
            (g(4), YE - g(10)), size=TS)

    # ------------------------------------------------------------------ test points, general notes
    tg = tp(sh, (g(120), g(176)), "GND")
    sh.gnd(tg["1"], dy=0)
    sh.text("Protection: no external TVS (0.3-1 pF). U101 input clamp diodes to CLH / VS- (100 mA);\n"
            "Ctop limits the current (100 V/ns -> 150 mA for < 1 ns); 900k string limits servo input current.\n"
            "Overload recovery > 60 us (servo winds up, gate re-biases through 10 Mohm): RESULT open point 2.\n"
            "Max input: 1 Mohm +/-50 V peak (with an external 50R terminator: its rating). Linear range +/-2.5 V around the offset.\n"
            "Noise (sim): 0.57 mV rms referred to the input, 10 Hz-2 GHz. -3 dB ~2 GHz, 50R source + external terminator (real BUF802).",
            (g(100), g(186)), size=TS)

    split_wires(sh)
    labels = "".join(sh.items)
    for net, shape in hier_pins("input"):
        assert f'(hierarchical_label "{net}" (shape {shape})' in labels, net
    fn = sh.save()
    return fn


def check(fn):
    """Netlist of this sheet alone (kicad-cli), key connections asserted."""
    import tempfile
    n = nets(fn, out=os.path.join(tempfile.mkdtemp(), "input.net"))
    from schlib import net_of

    def same(*members):
        ns = {net_of(n, r, p) for r, p in members}
        assert len(ns) == 1 and None not in ns, (members, ns)
        return ns.pop()

    assert same(("J101", "1"), ("C101", "1"), ("R114", "1")).endswith("VIN")
    assert len(n[net_of(n, "J101", "1")]) == 3, "VIN: SMA, Ctop and the 300k string only"
    assert same(("J101", "2"), ("U101", "17")) == "GND"
    assert not any(r.startswith("K") or r in ("R101", "R102", "R103") for v in n.values() for r, _ in v)
    same(("C101", "2"), ("C102", "1"), ("R104", "1"))                       # GA
    same(("R104", "2"), ("U101", "2"), ("R105", "1"))                       # IN
    same(("R106", "2"), ("U101", "3"))                                      # In_Bias
    assert same(("U101", "11"), ("R112", "1"), ("R118", "2")).endswith("BUF_OUT_S")
    same(("R112", "2"), ("R113", "1"))
    assert same(("R113", "2"),).endswith("BUF_OUT_T")
    same(("R116", "2"), ("R117", "1"), ("C105", "1"), ("U102", "3"))        # TAP
    assert same(("U102", "4"), ("C106", "1"), ("R118", "1"), ("R119", "2"), ("R120", "1")).endswith("FB")
    assert same(("R119", "1"),).endswith("VOFS")
    assert same(("R123", "1"),).endswith("VNEG_REF")
    assert net_of(n, "R123", "2") == net_of(n, "U102", "4"), "Rmid not on FB"
    same(("U102", "1"), ("C106", "2"), ("R121", "1"), ("TP103", "1"))
    same(("R121", "2"), ("C107", "1"), ("U101", "4"))                       # In_Aux
    assert same(("U101", "5"), ("U101", "8"), ("U101", "10"), ("U101", "6"), ("R107", "2"), ("U102", "2")) == "-5V"
    assert same(("U101", "1"), ("U101", "12"), ("U102", "5")) == "+5V"
    same(("U101", "15"), ("R108", "2"), ("R109", "1"), ("C103", "1"))
    same(("U101", "14"), ("R110", "1"), ("R111", "1"), ("C104", "1"))
    assert same(("J102", "1"),).endswith("EXT_CLK")
    single = [k for k, v in n.items() if len(v) == 1 and not k.startswith("unconnected")
              and not any(h in k for h in ("BUF_OUT_T", "VOFS", "VNEG_REF", "+2V5", "-2V5"))]
    assert not single, single
    print("input.kicad_sch: netlist checks passed")


if __name__ == "__main__":
    check(main())
