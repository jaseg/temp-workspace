"""strobe.kicad_sch: strobe drivers (design/lowcost/sim/strobe/RESULT.md, SPEC decision 3).

Signal paths, left to right (all 50 R, 50 % duty square waves from complementary LVCMOS33 FPGA pins):
  Sampler strobe (3.0 MHz, SPEC decision 18):
    S_STROBE_P -> 47 R -> 100 nF -> TRF37D73 #1 -> 100 nF -> 12 dB pi pad (82/91/82 R) -> 100 nF
    -> TRF37D73 #2 -> 100 nF -> clip node with shorted stub TL (80 ps one-way, 13.2 mm) and a fitted BAT15-03W clamp
    -> T401 common-mode-choke balun (Murata DLW21SN900HQ2L) -> STRB_A / STRB_K (floating rails;
    47 pF blocks, 1 k termination and bias feeds are on the sampler sheet).
    S_STROBE_N: unused complement, AC dummy load 47 R + 100 nF + 49.9 R (keeps pin currents equal).
  Phase strobe (48 MHz), one chain per polarity, identical layout:
    PH_STROBE_P/N -> 47 R -> 100 nF -> TRF37D73 -> 100 nF -> 10 dB pi pad (100/68/100 R) -> 100 nF
    -> GVA-84+ (+5V1 via bead + 2.2 uH) -> 100 nF -> launch node with shorted stub
    (80 ps, 13.2 mm, sim/phase_array/RESULT.md)
    and a DNP BAT15-03W clamp -> PSTRB_A / PSTRB_K (strobe lines along the taps, trigger_phase sheet).

Bias tees (sim/bias_tee/RESULT.md): every TRF37D73 output: BLM15HD102SN1D bead with its pad on the 50 R line
-> 47 uH LQH32CN470K23L (1210) with 1 k 0402 across it (kills the bead-L / 47 uH self-C resonance near 70 MHz,
-0.5 -> -0.28 dB) -> cold end 100 nF (own cap, GND via at its pad, supply via beyond it). GVA-84+: bead + 2.2 uH
LQM21PN2R2MGHL (its 80 ps shorted launch stub shorts everything below ~300 MHz, so the 2.2 uH is enough; DCR
budget 0.06-0.18 V at 108-130 mA), cold end = 1 nF / 100 nF, fed from +5V1 (5.40 V, 5.334-5.466 V, TPS63802) through
R419 / R420 2.49 R per chain (SPEC decision 26; +5V1 10 uF on the supply side): Vd 4.82-5.20 V at any USB voltage.
Pad input shunts R402 / R408 / R412 are 0603 (100 mW; 44-65 mW with the saturated square, validation PARTS-1); the
series and output resistors stay 0402 (<= 35 mW).

Deviation from RESULT.md: an extra 100 nF block in front of TRF #2 / GVA-84+ (both RF inputs carry
an internal DC bias and the pi pads' shunt resistors would otherwise load it).

TRF37D73IDSGR (TI SLASE43, WSON-8 DSG 2x2): 1 VCC, 2 RFIN, 3/4/6/8 NC (to GND), 5 PWDN (low/NC = on,
internal pull-down; tied to GND), 7 RFOUT + DC bias via RF choke, EP (pad 9) GND.
GVA-84+ (Mini-Circuits, case DF782 = SOT-89): 1 RF-IN, 3 RF-OUT and DC-IN, 2 and 4 GND; KiCad SOT-89-3
pad 2 is the tab (= Mini-Circuits pin 4 and pin 2). Vd 4.8-5.2 V (5.0 typ), Id 108 mA typ, DC on pin 3
max 5.8 V, input max +13 dBm; recommended circuit: Vcc -> RF choke -> pin 3, no bias resistor at 5 V."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schlib import g, ic_symbol
from common import new_sheet, hier_pins, R, C

WSON = "Package_SON:WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm"
TRF = ic_symbol("TRF37D73_S", left=[None, None, ("2", "RFIN", "input"), None, None],
                right=[None, None, ("7", "RFOUT", "output"), None, None], top=[("1", "VCC", "power_in")],
                bottom=[("3", "NC", "passive"), ("4", "NC", "passive"), ("5", "PWDN", "input"),
                        ("9", "GND", "power_in"), ("6", "NC", "passive"), ("8", "NC", "passive")],
                footprint=WSON, description="TRF37D73 1-6 GHz 50 R gain block (strobe drawing: PWDN at the bottom)")
TRF_F = {"Price": "1.50 USD (LCSC)", "Note": "WSON-8: 1 VCC, 2 RFIN, 5 PWDN, 7 RFOUT, 3/4/6/8 NC, EP GND"}
SOT89 = "Package_TO_SOT_SMD:SOT-89-3"
GVA = ic_symbol("GVA-84+", left=[None, ("1", "IN", "input"), None], right=[None, ("3", "OUT", "bidirectional"), None],
                bottom=[("2", "GND", "power_in")], footprint=SOT89,
                description="Mini-Circuits GVA-84+ DC-7 GHz MMIC amplifier, SOT-89 (pin 4 = tab = pad 2)")
GVA_F = {"Price": "2.99 USD (SPEC)", "Note": "SOT-89: 1 IN, 3 OUT+DC, 2/4(tab) GND; Vd 5.0 V 108 mA"}
TP = "Connector:TestPoint"
TP_FP = "TestPoint:TestPoint_Pad_D1.0mm"
BEAD = ("Device:FerriteBead_Small", "Inductor_SMD:L_0402_1005Metric", "BLM15HD102SN1D",
        {"LCSC": "C21516", "Price": "0.0197 USD (LCSC)",
         "Note": "1 k @100 MHz / 2 k @1 GHz, 250 mA, 1.25 R max; pad ON the 50 R line, body perpendicular"})
L47 = ("Device:L", "Inductor_SMD:L_1210_3225Metric", "LQH32CN470K23L",
       {"LCSC": "C701189", "Price": "0.1632 USD (LCSC 5+)",
        "Note": "47 uH 1210, 170 mA, DCR 1.3 R (1.69 max), SRF >= 15 MHz; 1 k across it; abuts the bead"})
L22 = ("Device:L", "Inductor_SMD:L_0805_2012Metric", "LQM21PN2R2MGHL",
       {"LCSC": "C341781", "Price": "0.3667 USD (LCSC 5+)",
        "Note": "2.2 uH 0805, Isat 450 mA, DCR 125 mR, SRF 40 MHz; abuts the bead"})
RFEED_F = {"Note": "GVA-84+ drain feed: 2.49 R 1 %, 39 mW at 125 mA (0402 62.5 mW); one per chain (A / K isolation); "
                   "Vd 4.82-5.20 V over +5V1 5.334-5.466 V, 85-125 mA, DCR spread (power-tree.md section 12)"}
RDAMP_F = {"Note": "damps the 47 uH (bias tee): 0402 beside the 1210, same two pads; sim/bias_tee/RESULT.md"}
CCOLD_F = {"Note": "47 uH cold end: abuts the 1210 cold pad, GND via at its pad, +3V3 plane vias beyond it"}
# explicit references for the parts added by the bias-tee revision (no renumbering of existing parts)
_NEW = {"R": iter(range(415, 430)), "C": iter(range(432, 450))}


def new_ref(prefix):
    return f"{prefix}{next(_NEW[prefix])}"
T = 1.0      # annotation text size


def P(x, y):
    return (g(x), g(y))


def add_tp(sh, name, at):
    return sh.add(TP, "TP", name, at, fp=TP_FP)


def trf(sh, X, Y):
    """TRF37D73 at (X, Y) grid units, RF pins on the line y = Y; bottom pins bussed to GND."""
    u = sh.add(TRF, "U", "TRF37D73", P(X, Y), fp=WSON, lcsc="C2151367", mpn="TRF37D73IDSGR", fields=TRF_F)
    bx = [u[n][0] for n in ("3", "4", "5", "9", "6", "8")]
    yb = g(Y + 10)
    for n in ("3", "4", "5", "9", "6", "8"):
        sh.wire(u[n], (u[n][0], yb))
    sh.path([(min(bx), yb), (max(bx), yb)])
    sh.gnd(P(X, Y + 10))
    return u


def rail_caps(sh, xs, Yr, vals):
    """Vertical decoupling caps hanging from the rail y = Yr at grid x positions xs (to GND)."""
    out = []
    for x, v in zip(xs, vals):
        size = "0402" if v in ("1n", "100n") else "0805"
        lcsc = "C1523" if v == "1n" else None
        kw = {"lcsc": lcsc} if lcsc else {}
        c = C(sh, v, P(x, Yr + 3), size=size, **kw)
        sh.gnd(c["2"])
        out.append(c)
    return out


def bias_tee(sh, x, Y, Yr, big, rail, cap_xs, tp_name):
    """RF choke from the line node (x, Y) up to the rail at y = Yr: bead (RF side, pad on the line) + big
    inductor; for the 47 uH (TRF37D73) also the 1 k damping resistor across it and an own 100 nF at its cold
    end (rail extended to x + 8). Returns (bead, L)."""
    lib, fp, mpn, f = BEAD
    b = sh.add(lib, "FB", "1k", P(x, Y - 4), rot=180, fp=fp, mpn=mpn, fields=f)  # pin 1 at the line
    lib, fp, mpn, f = big
    val = "47u" if big is L47 else "2.2u"
    l = sh.add(lib, "L", val, P(x, Y - 11), rot=180, fp=fp, mpn=mpn, fields=f)
    sh.wire(P(x, Y), b["1"])
    sh.wire(b["2"], l["1"])
    sh.wire(l["2"], P(x, Yr))
    if big is L47:
        rd = R(sh, "1k", P(x + 4, Y - 11), rot=180, ref=new_ref("R"), fields=RDAMP_F)
        sh.wire(l["1"], rd["1"])
        sh.wire(l["2"], rd["2"])
        sh.wire(P(x, Yr), P(x + 8, Yr))
        cc = C(sh, "100n", P(x + 8, Yr + 3), ref=new_ref("C"), fields=CCOLD_F)
        sh.gnd(cc["2"])
    # DC test point between bead and choke
    tp = add_tp(sh, tp_name, P(x - 5, Y - 7))
    sh.wire(P(x, Y - 7), tp["1"])
    return b, l


def pad(sh, x, Y, rs, rp):
    """Pi pad centred at grid x on line Y: shunt rs at x-5 / x+5, series rp at x. Returns (left, right) points.
    The input shunt (first part, driven by the saturated TRF37D73) is 0603 (validation PARTS-1)."""
    s1 = R(sh, rs, P(x - 5, Y + 3), size="0603", lcsc={"100": "C22775"}.get(rs, ""),
           fields={"Note": "0603 100 mW: input shunt of the pad, 44-65 mW with the saturated square (PARTS-1)"})
    s2 = R(sh, rs, P(x + 5, Y + 3))
    r = R(sh, rp, P(x, Y), rot=90)
    sh.gnd(s1["2"])
    sh.gnd(s2["2"])
    sh.wire(P(x - 5, Y), r["1"])
    sh.wire(r["2"], P(x + 5, Y))
    return P(x - 5, Y), P(x + 5, Y)


def stub(sh, xn, Y, name, ps, mm):
    """Shorted stub from node (xn, Y): wire down to the TLINE, far end through a net tie to GND."""
    tl = sh.add("Simulation_SPICE:TLINE", "TL", f"Z0=50 TD={ps}p", P(xn + 8, Y + 8),
                fields={"Note": f"PCB trace, not a part: {mm} mm 50 R microstrip, far end via to GND",
                        "Sim.Device": "TLINE", "Sim.Params": f"z0=50 td={ps}p"})
    sh.path([P(xn, Y), P(xn, Y + 8), tl["1"]])
    nt = sh.add("Device:NetTie_2", "NT", "stub short", P(xn + 16, Y + 8),
                fp="NetTie:NetTie-2_SMD_Pad0.5mm", fields={"Note": f"{name} shorted end: via to L2 GND here"})
    sh.wire(tl["3"], nt["1"])
    sh.wire(nt["2"], P(xn + 20, Y + 8))
    sh.gnd(P(xn + 20, Y + 8))
    sh.gnd(tl["2"])
    sh.gnd(tl["4"])
    return tl


def front(sh, label, shape, Y):
    """hlabel -> 47 R -> 100 nF -> TRF37D73 at x=50 with its 3V3 rail and output bias tee.
    Returns (trf symbol, output point after the 100 nF block at x=74)."""
    sh.hlabel(label, P(22, Y), shape, side="left")
    rs = R(sh, "47", P(27, Y), rot=90, fields={"Note": "at the FPGA pin (series termination)"})
    sh.wire(P(22, Y), rs["1"])
    c1 = C(sh, "100n", P(36, Y), rot=90)
    sh.wire(rs["2"], c1["1"])
    u = trf(sh, 50, Y)
    sh.wire(c1["2"], u["2"])
    return u


def trf_supply(sh, u, X, Y, tap_x, tp_name):
    """+3V3 rail at Y-16 from X-12 to tap_x: VCC pin, decoupling (10u, 100n, 1n nearest), bias tee."""
    Yr = Y - 22
    sh.path([P(X - 16, Yr), P(tap_x, Yr)])
    sh.wire(u["1"], P(X, Yr))
    rail_caps(sh, [X - 16, X - 10, X - 4], Yr, ["10u", "100n", "1n"])
    sh.power("+3V3", P(X + 4, Yr), dy=-2.54)
    bias_tee(sh, tap_x, Y, Yr, L47, "+3V3", (), tp_name)
    sh.wire(u["7"], P(tap_x, Y))


def main():
    sh = new_sheet("strobe", comments=["Generated by gen/gen_strobe.py from design/lowcost/sim/strobe/RESULT.md.",
                                       "All RF nets 50 R microstrip (0.36 mm on L1 over L2 GND, JLC04161H-7628).",
                                       "Part prices: TRF37D73 1.50, GVA-84+ 2.99, DLW21SN900HQ2L ~0.29 USD."])
    shapes = dict(hier_pins("strobe"))

    # ================================================================== sampler strobe (row 1)
    Y = 40
    sh.text("SAMPLER STROBE  S_STROBE 3.0 MHz, 50 % duty (167 / 167 ns), FPGA pins 38 (P) / 35 (N)",
            P(12, Y - 30), size=1.5)
    u1 = front(sh, "S_STROBE_P", shapes["S_STROBE_P"], Y)
    trf_supply(sh, u1, 50, Y, 64, "TRF1_OUT")
    c2 = C(sh, "100n", P(73, Y), rot=90)
    sh.wire(P(64, Y), c2["1"])
    a, b = pad(sh, 84, Y, "82", "91")
    sh.wire(c2["2"], a)
    c3 = C(sh, "100n", P(96, Y), rot=90)
    sh.wire(b, c3["1"])
    u2 = trf(sh, 113, Y)
    sh.wire(c3["2"], u2["2"])
    trf_supply(sh, u2, 113, Y, 127, "TRF2_OUT")
    c4 = C(sh, "100n", P(136, Y), rot=90)
    sh.wire(P(127, Y), c4["1"])
    sh.wire(c4["2"], P(142, Y))
    stub(sh, 142, Y, "TL401", 80, 13.2)
    bal = sh.add("Device:L_Ferrite_Coupled_Small", "T", "DLW21SN900HQ2L", P(180, Y + 1),
                 fp="Inductor_SMD:L_CommonModeChoke_Coilcraft_0805USB", lcsc="C97855", mpn="DLW21SN900HQ2L",
                 fields={"Price": "~0.29 USD", "Note": "CM choke as 1:1 TL balun; check pad map vs Murata drawing"})
    sh.wire(P(142, Y), bal["1"])
    # BAT15 shunt clamp at the launch node, fitted (sim/phase_array/RESULT.md (3): bridge reverse 3.27 -> 1.90 V)
    for rot in (90, 270):
        dc = sh.add("Device:D_Schottky", "D", "BAT15-03W", P(168, Y + 4), rot=rot, fp="Diode_SMD:D_SOD-323",
                    mpn="BAT1503WE6327HTSA1", lcsc="C5310874",
                    fields={"Note": "FITTED: clamps the wrong-polarity pulse of the falling edge (K to node, A to GND)"})
        if dc["1"][1] < dc["2"][1]:
            break
        sh.symbols.remove(dc)
        sh._refn["D"] -= 1
    sh.wire(P(168, Y), dc["1"])
    sh.gnd(dc["2"])
    sh.gnd(bal["3"])
    sh.wire(bal["2"], P(196, Y))
    sh.hlabel("STRB_A", P(196, Y), shapes["STRB_A"], side="right")
    k = bal["4"]
    sh.path([k, (k[0] + g(4), k[1]), (k[0] + g(4), g(Y + 8)), P(196, Y + 8)])
    sh.hlabel("STRB_K", P(196, Y + 8), shapes["STRB_K"], side="right")

    # S_STROBE_N dummy load
    Yn = Y + 14
    sh.hlabel("S_STROBE_N", P(22, Yn), shapes["S_STROBE_N"], side="left")
    rn = R(sh, "47", P(27, Yn), rot=90)
    sh.wire(P(22, Yn), rn["1"])
    cn = C(sh, "100n", P(36, Yn), rot=90)
    sh.wire(rn["2"], cn["1"])
    rt = R(sh, "49.9", P(42, Yn + 3))
    sh.wire(cn["2"], rt["1"])
    sh.gnd(rt["2"])

    sh.text("S_STROBE_N is not used: AC dummy load\n(47 R + 100 nF + 49.9 R) keeps the two\n"
            "pin currents and edges symmetric; no DC load.", P(12, Yn + 10), size=T)
    sh.text("TRF37D73 x2: 22 dB, OP1dB 16.5 dBm, 3.3 V 55 mA each.\n"
            "Edge 300-600 ps (FPGA) -> ~250 ps -> 133-152 ps.\n"
            "PWDN and NC pins to GND, EP: >= 5 vias to L2.\n"
            "Bias tee: bead (pad on the line) -> 47 uH || 1 k\n-> own 100 nF at the cold end (bias_tee RESULT).", P(46, Yn + 10), size=T)
    sh.text("12 dB pi pad 82 / 91 / 82 R (input shunt 0603):\n"
            "TRF #2 input ~+8.6 dBm square\n(abs. max +10 dBm).", P(78, Yn + 2), size=T)
    sh.text("CLIP STUB TL401: 80 ps one-way = 13.2 mm\n"
            "50 R microstrip (6.05 ps/mm). Tap right at\n"
            "C(TRF #2 out); far end via to GND (NT401).\n"
            "Pulse ~160 ps wide; trim 60 ps = 9.9 mm.\n"
            "D clamp BAT15-03W FITTED (bridge reverse\n3.27 V -> 1.9 V, phase_array RESULT).", P(128, Yn + 6), size=T)
    sh.text("BALUN T401: Murata DLW21SN900HQ2L CMC\n"
            "(0805, 90 R CM @100 MHz, LCSC C97855)\n"
            "as 1:1 TL balun: line 1 = signal -> STRB_A,\n"
            "line 2 = GND -> STRB_K, rails float.\n"
            "STRB_A/K: 17.83 mm 50 R arms (105.6 ps, as built), equal\n"
            "+/-0.1 mm, uncoupled (sim/strobe_arms RESULT:\n"
            "no second sampling instant; bias +/-1.3 V).\n"
            "Step at the bridge ~4.3-4.6 V (sim).", P(173, Y + 12), size=T)

    # ================================================================== phase strobe (rows 2, 3)
    def phase(Y, lab_in, lab_out, n):
        u = front(sh, lab_in, shapes[lab_in], Y)
        trf_supply(sh, u, 50, Y, 64, f"PTRF{n}_OUT")
        c2 = C(sh, "100n", P(73, Y), rot=90)
        sh.wire(P(64, Y), c2["1"])
        a, b = pad(sh, 84, Y, "100", "68")
        sh.wire(c2["2"], a)
        c3 = C(sh, "100n", P(96, Y), rot=90)
        sh.wire(b, c3["1"])
        gv = sh.add(GVA, "U", "GVA-84+", P(110, Y), fp=SOT89, lcsc="C5445191", mpn="GVA-84+", fields=GVA_F)
        sh.wire(c3["2"], gv["1"])
        sh.gnd(gv["2"])
        # +5V1 bias (TPS63802 on the power sheet, 5.40 V): +5V1 -> 10u -> R419 / R420 2.49 R (drain window 4.8-5.2 V,
        # SPEC decision 26) -> cold-end node with 1n (nearest the choke) and 100n -> 2.2 uH -> bead -> GVA pin 3
        Yr = Y - 22
        sh.path([P(120, Yr), P(143, Yr)])
        rail_caps(sh, [134, 140], Yr, ["1n", "100n"])
        rs = R(sh, "2.49", P(146, Yr), rot=90, ref=("R419" if n == 1 else "R420"), fields=RFEED_F)
        assert abs(rs["1"][0] - g(143)) < 1e-6, rs["1"]
        sh.path([rs["2"], P(156, Yr)])
        rail_caps(sh, [152], Yr, ["10u"])
        sh.hlabel("+5V1", P(156, Yr), shapes["+5V1"], side="right")
        bias_tee(sh, 120, Y, Yr, L22, "+5V1", (), f"GVA{n}_VD")
        sh.wire(gv["3"], P(120, Y))
        c4 = C(sh, "100n", P(140, Y), rot=90)
        sh.wire(P(120, Y), c4["1"])
        sh.wire(c4["2"], P(148, Y))
        stub(sh, 148, Y, f"TL40{n + 1}", 80, 13.2)   # 80 ps: sim/phase_array/RESULT.md
        # DNP clamp at the launch point
        want_k_top = lab_out == "PSTRB_A"
        for rot in (90, 270):
            d = sh.add("Device:D_Schottky", "D", "BAT15-03W", P(176, Y + 4), rot=rot, fp="Diode_SMD:D_SOD-323",
                       mpn="BAT1503WE6327HTSA1", lcsc="C5310874", dnp=True,
                       fields={"Note": "DNP: clamp for the wrong-polarity pulse of the second edge"})
            top, bot = ("1", "2") if want_k_top else ("2", "1")
            if d[top][1] < d[bot][1]:
                break
            sh.symbols.remove(d)
            sh._refn["D"] -= 1
        sh.wire(P(148, Y), P(196, Y))
        sh.wire(P(176, Y), d[top])
        sh.gnd(d[bot])
        sh.hlabel(lab_out, P(196, Y), shapes[lab_out], side="right")
        return u, gv

    Y2 = 105
    sh.text("PHASE STROBE  PH_STROBE 48 MHz, 50 % duty, FPGA pins 39 (P) / 40 (N); one chain per polarity",
            P(12, Y2 - 30), size=1.5)
    phase(Y2, "PH_STROBE_P", "PSTRB_A", 1)
    sh.text("10 dB pi pad 100 / 68 / 100 R (input shunt\n0603): GVA input ~+10 dBm square\n(abs. max +13 dBm).",
            P(78, Y2 + 12), size=T)
    sh.text("GVA-84+ (SOT-89): 1 IN, 3 OUT+DC, 2/4 GND.\n"
            "Vd 4.8-5.2 V, 108 mA; no Rbias at 5 V (datasheet\n"
            "Fig. 2): pin 3 -> bead -> 2.2 uH -> 2.49 R -> +5V1 (5.40 V),\n"
            "Vd 4.82-5.20 V (nom. 4.99 V at 110 mA). Pin 3 max 5.8 V.\n"
            "2.2 uH is enough: the launch stub shorts < 300 MHz.\n"
            "Step 7.2 V into 50 R (sim, nominal).", P(102, Y2 + 12), size=T)
    sh.text("LAUNCH STUB: 80 ps one-way = 13.2 mm 50 R\n"
            "(phase_array RESULT; was 45 ps), at the start of\n"
            "the tap line; far end via to GND. Launch ~4 V peak,\n"
            ">= 2.75 V at every tap. BAT15-03W clamp DNP\n"
            "(reverse 2.95 V < BV 4 V: not needed).", P(150, Y2 + 16), size=T)
    sh.text("PSTRB_A: anode strobe line (positive pulse);\n"
            "0.16 mm / 72.8 R line along the 16 gates, 40 ps/tap\n"
            "loaded, 4.514 mm pitch; "
            "ends in 50 R on trigger_phase.", P(200, Y2 + 3), size=T)

    Y3 = 165
    phase(Y3, "PH_STROBE_N", "PSTRB_K", 2)
    sh.text("PSTRB_K: cathode strobe line (negative pulse,\n"
            "chain from the complementary pin N).", P(200, Y3 + 3), size=T)
    sh.text("Both phase chains: identical layout, mirror-symmetric;\n"
            "launch points side by side, chain lengths matched\n"
            "to +/-0.2 mm (+/-1.2 ps) from FPGA pin to launch.", P(102, Y3 + 12), size=T)

    # ================================================================== general notes (right column)
    sh.text("LAYOUT / NOTES\n"
            "- All RF nets 50 R microstrip on L1 (0.36 mm, outer prepreg 7628 0.21 mm, L2 solid GND):\n"
            "  6.057 ps/mm. Gain blocks 0402 DC blocks inline, no stubs, GND vias at every shunt part.\n"
            "- Decoupling per supply node: 1 nF 0402 nearest the pin, then 100 nF, 10 uF.\n"
            "- Bias tees (sim/bias_tee): bead pad ON the 50 R line (no stub), chain perpendicular, compact;\n"
            "  TRF: 47 uH || 1 k + own 100 nF at the cold pad; supply enters through that cap.\n"
            "- Test points TRFx/GVAx: DC bias check only (expect ~3.2 V / ~4.8 V), not RF.\n"
            "- Supplies: +3V3 4 x TRF37D73 here (220 mA); +5V1 2 x GVA-84+ (216 mA), own track from the\n"
            "  TPS63802 output caps C610/C611 (power sheet), not through FB602.\n"
            "- Open: large-signal edge of both blocks in saturation, CMC differential\n"
            "  bandwidth, reverse pulse (second edge) vs BAT15 BV: measure one chain early.",
            P(232, 14), size=T)

    names = {n for n, _ in hier_pins("strobe")}
    assert names == {"S_STROBE_P", "S_STROBE_N", "PH_STROBE_P", "PH_STROBE_N",
                     "STRB_A", "STRB_K", "PSTRB_A", "PSTRB_K", "+5V1"}, names
    split_wires(sh)
    sh.save()


def split_wires(sh):
    """Split wires at every pin or wire end lying on their interior (kicad-cli only connects pins at
    wire ends), so T-junctions and pins placed on a wire are real connections."""
    pts = {p for w in sh.wires for p in w}
    for s in sh.symbols:
        for pd in s.pins:
            pts.add(s.pin(pd.number))
    out = []
    for a, b in sh.wires:
        inner = [p for p in pts if sh._on_mid(p, a, b)]
        inner.sort(key=lambda p: abs(p[0] - a[0]) + abs(p[1] - a[1]))
        chain = [a] + inner + [b]
        out += list(zip(chain, chain[1:]))
    sh.wires = out


def check(outdir):
    import schlib
    n = schlib.nets(os.path.join(schlib.OUTDIR, "strobe.kicad_sch"), os.path.join(outdir, "strobe.net"))
    A = schlib.assert_net

    def on(*m):
        k = next((k for k, v in n.items() if set(m) <= v), None)
        assert k is not None, f"not on one net: {m}"
        return k
    A(n, "S_STROBE_P", {("R401", "1")})
    A(n, "S_STROBE_N", {("R405", "1")})
    A(n, "PH_STROBE_P", {("R407", "1")})
    A(n, "PH_STROBE_N", {("R411", "1")})
    A(n, "STRB_A", {("T401", "2")})
    A(n, "STRB_K", {("T401", "4")})
    A(n, "PSTRB_A", {("C421", "2"), ("TL402", "1"), ("D402", "1")})
    A(n, "PSTRB_K", {("C431", "2"), ("TL403", "1"), ("D403", "2")})
    # sampler chain
    on(("R401", "2"), ("C401", "1")); on(("C401", "2"), ("U401", "2"))
    on(("U401", "7"), ("FB401", "1"), ("C405", "1")); on(("FB401", "2"), ("L401", "1"), ("TP401", "1"))
    on(("C405", "2"), ("R402", "1"), ("R404", "1")); on(("R404", "2"), ("R403", "1"), ("C406", "1"))
    on(("C406", "2"), ("U402", "2")); on(("U402", "7"), ("FB402", "1"), ("C410", "1"))
    on(("C410", "2"), ("TL401", "1"), ("T401", "1"), ("D401", "1")); on(("TL401", "3"), ("NT401", "1"))
    on(("R405", "2"), ("C411", "1")); on(("C411", "2"), ("R406", "1"))
    A(n, "GND", {("T401", "3"), ("NT401", "2"), ("TL401", "2"), ("TL401", "4"), ("R406", "2"),
                 ("D401", "2"), ("D402", "2"), ("D403", "1"), ("U404", "2"), ("U406", "2")}
      | {(u, p) for u in ("U401", "U402", "U403", "U405") for p in ("3", "4", "5", "6", "8", "9")})
    A(n, "+3V3", {(u, "1") for u in ("U401", "U402", "U403", "U405")} |
      {("L401", "2"), ("L402", "2"), ("L403", "2"), ("L405", "2")})
    A(n, "+5V1", {("R419", "2"), ("R420", "2"), ("C420", "1"), ("C430", "1")})
    on(("L404", "2"), ("R419", "1"), ("C418", "1"), ("C419", "1"))
    on(("L406", "2"), ("R420", "1"), ("C428", "1"), ("C429", "1"))
    # bias tees (sim/bias_tee/RESULT.md): RF pin -> bead -> 47 uH || 1 k (TRF) / 2.2 uH (GVA) -> rail, own 100 nF
    for u, fb, l, rd, cc in (("U401", "FB401", "L401", "R415", "C432"), ("U402", "FB402", "L402", "R416", "C433"),
                             ("U403", "FB403", "L403", "R417", "C434"), ("U405", "FB405", "L405", "R418", "C435")):
        on((u, "7"), (fb, "1"))
        on((fb, "2"), (l, "1"), (rd, "1"))
        A(n, "+3V3", {(l, "2"), (rd, "2"), (cc, "1")})
        A(n, "GND", {(cc, "2")})
    for g_, fb, l in (("U404", "FB404", "L404"), ("U406", "FB406", "L406")):
        on((g_, "3"), (fb, "1"))
        on((fb, "2"), (l, "1"))
    # phase chains
    for r, c, u, fb, cp, rs, rr, c3, g, fg, c4 in (("R407", "C412", "U403", "FB403", "C416", "R408", "R410", "C417",
                                                   "U404", "FB404", "C421"),
                                                  ("R411", "C422", "U405", "FB405", "C426", "R412", "R414", "C427",
                                                   "U406", "FB406", "C431")):
        on((r, "2"), (c, "1")); on((c, "2"), (u, "2")); on((u, "7"), (fb, "1"), (cp, "1"))
        on((cp, "2"), (rs, "1"), (rr, "1")); on((c3, "2"), (g, "1")); on((g, "3"), (fg, "1"), (c4, "1"))
    print("strobe netlist checks OK,", len(n), "nets")


if __name__ == "__main__":
    main()
    if "--check" in sys.argv:
        check(sys.argv[sys.argv.index("--check") + 1])
