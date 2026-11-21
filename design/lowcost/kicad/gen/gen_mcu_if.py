"""mcu_if.kicad_sch: 2x13 header to the user's STM32G474 board, DAC scaling stages (difference
amplifiers on +/-2.5 V), ADC reference divider, tap threshold divider, relay driver, I2C pull-ups.

DAC plan (docs/research/adc.md, "Analog control voltages"): PA4 DAC1_OUT1 -> TRIG_LEVEL, PA5 DAC1_OUT2 ->
VOFS, PA6 DAC2_OUT1 -> VTAP_TH, PA2 (DAC3_CH1 via OPAMP1) -> VBIAS_A, PB1 (DAC3_CH2 via OPAMP3) -> VBIAS_K.
Each bipolar output is a difference amplifier: Vout = G (Vdac - VMID) + Vr, VMID = VREF+/2 = 1.45 V
(buffered), G = R2/R1, Vr set by the Thevenin divider on the + input (Ra to a rail, Rb to GND, Ra||Rb = R2).
DAC range 0.25..2.65 V (buffer on) -> Vdac - VMID = +/-1.2 V."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schlib import g
from common import new_sheet, R, C, decoupler

OPAMP = "Amplifier_Operational:LMV358"   # standard dual pinout (1 OUTA, 2 -A, 3 +A, 4 V-, 5 +B, 6 -B, 7 OUTB, 8 V+)
OPA_FP = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
OPA_F = {"Price": "0.50 USD (SPEC)", "MPN": "TP2272-SR (3PEAK), any RRIO dual, 5 V total supply"}

HEADER = {1: "GND", 2: "GND", 3: "ADC_IN", 4: "GND", 5: "VREFP", 6: "GND", 7: "DAC_TRIG", 8: "DAC_OFS",
          9: "DAC_TAPTH", 10: "DAC_BIAS_A", 11: "DAC_BIAS_K", 12: "GND", 13: "ADC_TRIG", 14: "MCU_CLK",
          15: "GND", 16: "TRIG_SEL", 17: "RELAY_CTL", 18: "FPGA_DONE", 19: "FPGA_RECONFIG", 20: "I2C_SCL",
          21: "I2C_SDA", 22: "SPI_SCK", 23: "SPI_MOSI", 24: "SPI_MISO", 25: "SPI_CS", 26: "GND"}
MCU_PIN = {"ADC_IN": "PA0 ADC12_IN1", "VREFP": "VREF+ (VREFBUF 2.9 V)", "DAC_TRIG": "PA4 DAC1_OUT1",
           "DAC_OFS": "PA5 DAC1_OUT2", "DAC_TAPTH": "PA6 DAC2_OUT1", "DAC_BIAS_A": "PA2 OPAMP1 (DAC3_CH1)",
           "DAC_BIAS_K": "PB1 OPAMP3 (DAC3_CH2)", "ADC_TRIG": "EXTI11 pin (ADC12 ext. trigger)",
           "MCU_CLK": "PF0 OSC_IN (HSE bypass)", "TRIG_SEL": "GPIO", "RELAY_CTL": "GPIO",
           "FPGA_DONE": "GPIO in", "FPGA_RECONFIG": "GPIO open-drain", "I2C_SCL": "I2C SCL",
           "I2C_SDA": "I2C SDA", "SPI_SCK": "SPI SCK", "SPI_MOSI": "SPI MOSI", "SPI_MISO": "SPI MISO",
           "SPI_CS": "SPI NSS / GPIO"}
HIER_IN = {"ADC_IN", "ADC_TRIG", "MCU_CLK", "FPGA_DONE", "SPI_MISO"}
HIER_OUT = {"TRIG_SEL", "FPGA_RECONFIG", "I2C_SCL", "SPI_SCK", "SPI_MOSI", "SPI_CS"}


def diffamp(sh, u, x, y, dac, out, r1, r2, ra=None, rb=None, rail=None, note=""):
    """Unit u (already placed at (x, y), rot 0) as difference amplifier."""
    plus, minus, o = u["3"] if u.unit == 1 else u["5"], u["2"] if u.unit == 1 else u["6"], \
        u["1"] if u.unit == 1 else u["7"]
    N = (x - g(8), plus[1])
    sh.wire(plus, N)
    rin = R(sh, r1, (x - g(18), plus[1]), rot=90)           # DAC -> + (R1)
    sh.wire(rin["2"], N)
    sh.stub(rin, "1", dac)
    if ra:                                                     # Thevenin divider for Vr
        ra_ = R(sh, ra, (N[0], N[1] - g(5)))
        sh.wire(ra_["2"], N)
        sh.power(rail, ra_["1"], dy=-2.54)
        rb_ = R(sh, rb, (N[0] - g(6), N[1] - g(5)))
        sh.wire(rb_["2"], (rb_["2"][0], N[1]))
        sh.power("GND", rb_["1"], dy=-2.54, rot=180)
    else:
        rg = R(sh, r2, (N[0], N[1] - g(5)))
        sh.wire(rg["2"], N)
        sh.power("GND", rg["1"], dy=-2.54, rot=180)
    M = (x - g(8), minus[1])
    sh.wire(minus, M)
    rm = R(sh, r1, (x - g(18), minus[1]), rot=90)          # VMID -> - (R1)
    sh.wire(rm["2"], M)
    sh.stub(rm, "1", "VMID")
    rf = R(sh, r2, (x, minus[1] + g(6)), rot=90)            # feedback R2
    sh.path([M, (M[0], rf["1"][1]), rf["1"]])
    X = o[0] + g(2)
    sh.path([rf["2"], (X, rf["2"][1]), (X, o[1])])
    E = (o[0] + g(6), o[1])
    sh.wire(o, E)
    sh.hlabel(out, E, "output")
    if note:
        sh.text(note, (x - g(22), minus[1] + g(8)), size=1.0)


def opamp_power(sh, ref, at):
    p = sh.add(OPAMP, ref, "TP2272", at, unit=3, fp=OPA_FP)
    sh.stub(p, "8", "+2V5", kind="power")
    sh.power("-2V5", p["4"], dy=5.08, rot=180)
    return p


def main():
    sh = new_sheet("mcu_if", comments=["Header J701 to the STM32G474 board (3.3 V logic, common GND).",
                                       "DAC scaling: difference amplifiers, TP2272 on +/-2.5 V."])
    # header
    j = sh.add("Connector_Generic:Conn_02x13_Odd_Even", "J", "MCU 2x13", (g(40), g(60)),
               fp="Connector_PinHeader_2.54mm:PinHeader_2x13_P2.54mm_Vertical", lcsc="C2939733")
    for pin, net in HEADER.items():
        if net == "GND":
            sh.stub(j, str(pin), "GND_H", length=g(4))
        elif net in HIER_IN:
            sh.stub(j, str(pin), net, length=g(4), kind="hlabel", shape="output")
        elif net in HIER_OUT:
            sh.stub(j, str(pin), net, length=g(4), kind="hlabel", shape="input")
        elif net == "I2C_SDA":
            sh.stub(j, str(pin), net, length=g(4), kind="hlabel", shape="bidirectional")
        else:
            sh.stub(j, str(pin), net, length=g(4))
    gh = sh.power("GND", (g(20), g(90)), wire=False)
    sh.label("GND_H", (g(20), g(90)))
    sh.text("GND_H: header ground pins, tied to GND here.", (g(10), g(93)), size=1.0)
    sh.text("J701 pin -> STM32G474:\n" + "\n".join(
        f"{p:2d} {n:13s} {MCU_PIN.get(n, '')}" for p, n in HEADER.items() if n != "GND") +
        "\nGND: 1, 2, 4, 6, 12, 15, 26", (g(10), g(100)), size=1.0)

    # VMID buffer and ADC_REF_MID divider
    rt = R(sh, "10k", (g(90), g(30)))
    sh.stub(rt, "1", "VREFP")
    rbt = R(sh, "10k", (g(90), g(40)))
    sh.wire(rt["2"], rbt["1"])
    sh.gnd(rbt["2"])
    u1 = sh.add(OPAMP, "U", "TP2272", (g(110), g(32)), unit=1, fp=OPA_FP, fields=OPA_F)
    sh.path([rt["2"], (rt["2"][0] + g(4), rt["2"][1]),
                                                               (rt["2"][0] + g(4), u1["3"][1]), u1["3"]])
    sh.path([u1["2"], (u1["2"][0], u1["2"][1] + g(3)), (u1["1"][0] + g(2), u1["2"][1] + g(3)),
             (u1["1"][0] + g(2), u1["1"][1])])
    sh.wire(u1["1"], (u1["1"][0] + g(6), u1["1"][1]))
    sh.label("VMID", (u1["1"][0] + g(6), u1["1"][1]))
    c = C(sh, "100n", (g(122), g(37)))
    sh.wire(c["1"], (c["1"][0], u1["1"][1]))
    sh.gnd(c["2"])
    sh.text("VMID = VREF+/2 = 1.45 V, buffered", (g(95), g(22)), size=1.0)
    r3 = R(sh, "30k", (g(150), g(30)))
    sh.stub(r3, "1", "VREFP")
    r4 = R(sh, "10k", (g(150), g(40)))
    sh.wire(r3["2"], r4["1"])
    sh.gnd(r4["2"])
    c = C(sh, "10n", (g(156), g(40)))
    sh.path([r3["2"], (c["1"][0], r3["2"][1]), c["1"]])
    sh.gnd(c["2"])
    sh.path([(c["1"][0], r3["2"][1]), (c["1"][0] + g(6), r3["2"][1])])
    sh.hlabel("ADC_REF_MID", (c["1"][0] + g(6), r3["2"][1]), "output")
    sh.text("ADC_REF_MID = VREF+ x 10k/40k = 0.725 V\n(level-shift reference on the sampler sheet)",
            (g(145), g(20)), size=1.0)

    # difference amplifiers
    u1b = sh.add(OPAMP, u1.ref, "TP2272", (g(120), g(75)), unit=2, fp=OPA_FP, fields=OPA_F)
    diffamp(sh, u1b, g(120), g(75), "DAC_TRIG", "TRIG_LEVEL", "40.2k", "10k",
            note="TRIG_LEVEL = 0.25 (Vdac - VMID): +/-0.30 V, 0.18 mV/LSB")
    u2 = sh.add(OPAMP, "U", "TP2272", (g(185), g(75)), unit=1, fp=OPA_FP, fields=OPA_F)
    diffamp(sh, u2, g(185), g(75), "DAC_OFS", "VOFS", "24.9k", "10k",
            note="VOFS = 0.40 (Vdac - VMID): +/-0.48 V (into the OPA197 servo summing node)")
    u2b = sh.add(OPAMP, u2.ref, "TP2272", (g(120), g(120)), unit=2, fp=OPA_FP, fields=OPA_F)
    # bridge bias (sampler sheet): anode rail VBIAS_A NEGATIVE, cathode rail VBIAS_K POSITIVE (reverse bias,
    # sim/strobe/bridge.py, sim/sampler/RESULT.md); G = 0.5 -> 0.4..1.6 V magnitude (strobe RESULT: 0.5..1.2 V)
    diffamp(sh, u2b, g(120), g(120), "DAC_BIAS_A", "VBIAS_A", "20k", "10k", ra="24.9k", rb="16.5k",
            rail="-2V5", note="VBIAS_A = -1.00 V + 0.5 (Vdac - VMID): -1.60..-0.40 V (anode rail)")
    u3 = sh.add(OPAMP, "U", "TP2272", (g(185), g(120)), unit=1, fp=OPA_FP, fields=OPA_F)
    diffamp(sh, u3, g(185), g(120), "DAC_BIAS_K", "VBIAS_K", "20k", "10k", ra="24.9k", rb="16.5k",
            rail="+2V5", note="VBIAS_K = +1.00 V + 0.5 (Vdac - VMID): +0.40..+1.60 V (cathode rail)")
    # spare section: follower to GND
    u3b = sh.add(OPAMP, u3.ref, "TP2272", (g(250), g(120)), unit=2, fp=OPA_FP, fields=OPA_F)
    sh.path([u3b["5"], (u3b["5"][0] - g(3), u3b["5"][1])])
    sh.power("GND", (u3b["5"][0] - g(3), u3b["5"][1]), dy=g(8))
    sh.path([u3b["6"], (u3b["6"][0], u3b["6"][1] + g(3)), (u3b["7"][0] + g(2), u3b["6"][1] + g(3)),
             (u3b["7"][0] + g(2), u3b["7"][1]), u3b["7"]])
    sh.text("U703B spare (follower, input grounded)", (g(240), g(132)), size=1.0)
    for i, ref in enumerate([u1.ref, u2.ref, u3.ref]):
        opamp_power(sh, ref, (g(250 + 12 * i), g(40)))
    decoupler(sh, "+2V5", (g(245), g(60)), ("100n", "100n", "100n"))
    decoupler(sh, "-2V5", (g(275), g(60)), ("100n", "100n", "100n"), gnd="GND")

    # VTAP_TH divider, VTAP_P/N rails
    r5 = R(sh, "30k", (g(90), g(160)))
    sh.stub(r5, "1", "DAC_TAPTH")
    r6 = R(sh, "1k", (g(90), g(170)))
    sh.wire(r5["2"], r6["1"])
    sh.gnd(r6["2"])
    c = C(sh, "100n", (g(96), g(170)))
    sh.path([r5["2"], (c["1"][0], r5["2"][1]), c["1"]])
    sh.gnd(c["2"])
    sh.path([(c["1"][0], r5["2"][1]), (c["1"][0] + g(6), r5["2"][1])])
    sh.hlabel("VTAP_TH", (c["1"][0] + g(6), r5["2"][1]), "output")
    sh.text("VTAP_TH = Vdac/31: 8..85 mV, 0.02 mV/LSB (phase RESULT: 0..+80 mV)", (g(80), g(150)), size=1.0)
    for k, (rail, net) in enumerate((("+2V5", "VTAP_P"), ("-2V5", "VTAP_N"))):
        r = R(sh, "0", (g(140 + 20 * k), g(165)), rot=90, size="0603")
        sh.stub(r, "1", rail, kind="power")
        sh.stub(r, "2", net, kind="hlabel", shape="output", length=g(3))
    sh.text("VTAP_P/N = +2V5/-2V5 (phase RESULT: 12.5 mA per rail, fixed).\n"
            "0R links: replace by a DAC-driven stage if a trim turns out to be needed.", (g(135), g(150)), size=1.0)

    # relay driver
    q = sh.add("Device:Q_NMOS_GSD", "Q", "2N7002", (g(220), g(170)), fp="Package_TO_SOT_SMD:SOT-23",
               lcsc="C8545")
    rg = R(sh, "1k", (g(205), g(170)), rot=90)
    sh.wire(rg["2"], q["1"])
    sh.stub(rg, "1", "RELAY_CTL")
    rpd = R(sh, "100k", (g(212), g(176)))
    sh.wire(rpd["1"], (rpd["1"][0], q["1"][1]))
    sh.gnd(rpd["2"])
    sh.gnd(q["2"])
    d = sh.add("Device:D", "D", "1N4148W", (g(226), g(160)), rot=90, fp="Diode_SMD:D_SOD-123", lcsc="C81598")
    sh.wire(q["3"], d["2"], via="vh")
    sh.power("VBUS", d["1"], dy=-5.08)
    sh.path([(q["3"][0], d["2"][1]), (q["3"][0] + g(10), d["2"][1])])
    sh.hlabel("TERM_50", (q["3"][0] + g(10), d["2"][1]), "output")
    sh.text("Relay driver: TERM_50 is the low side of the HFD3/5 coil (coil top on VBUS, input sheet).\n"
            "Flyback diode here; RELAY_CTL high = 50R termination on.", (g(195), g(185)), size=1.0)

    # I2C pull-ups
    for k, net in enumerate(("I2C_SCL", "I2C_SDA")):
        r = R(sh, "4.7k", (g(268 + 12 * k), g(160)))
        sh.power("+3V3", r["1"], dy=-2.54)
        sh.stub(r, "2", net)
    sh.text("I2C pull-ups 4.7k (MS5351M at 0x60)", (g(262), g(150)), size=1.0)
    sh.save()


if __name__ == "__main__":
    main()
