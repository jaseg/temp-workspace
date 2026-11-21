"""mcu_if.kicad_sch: STM32G474CBT6 microcontroller (on board since 21 Nov 2026; it replaced the 2x13 header
J701 to an external STM32 board), DAC scaling stages (difference amplifiers on +/-2.5 V), ADC reference divider,
tap threshold divider, I2C pull-ups. SWD, NRST, DBG1 and the UART (HOST_RX / HOST_TX, sensing-board naming: the
MCU is the host, HOST_RX = MCU RX) go to the programming header J501 on fpga_clock; USB FS (PA11/PA12) to the
USB-C receptacle on the power sheet. Pin plan: PINS below and kicad/README.md.

DAC plan (docs/research/adc.md, "Analog control voltages"): PA4 DAC1_OUT1 -> TRIG_LEVEL, PA5 DAC1_OUT2 ->
VOFS, PA6 DAC2_OUT1 -> VTAP_TH, PA2 (DAC3_CH1 via OPAMP1) -> VBIAS_A, PB1 (DAC3_CH2 via OPAMP3) -> VBIAS_K.
Each bipolar output is a difference amplifier: Vout = G (Vdac - VMID) + Vr, VMID = VREF+/2 = 1.45 V
(buffered), G = R2/R1, Vr set by the Thevenin divider on the + input (Ra to a rail, Rb to GND, Ra||Rb = R2).
DAC range 0.25..2.65 V (buffer on) -> Vdac - VMID = +/-1.2 V."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schlib import g
from common import new_sheet, hier_pins, R, C, decoupler

OPAMP = "Amplifier_Operational:LMV358"   # standard dual pinout (1 OUTA, 2 -A, 3 +A, 4 V-, 5 +B, 6 -B, 7 OUTB, 8 V+)
OPA_FP = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
OPA_F = {"Price": "0.50 USD (LCSC C39487549)", "MPN": "TP2272-SO1R (3PEAK), any RRIO dual, 5 V total supply",
         "LCSC": "C39487549"}

# STM32G474CBT6 (LQFP-48) pin plan. Pin numbers: DS12288 LQFP48 pinout = KiCad MCU_ST_STM32G4:STM32G474CBTx.
# (pin, port, net, how): how h = hierarchical label, l = local label, nc = NC flag
MCU = "MCU_ST_STM32G4:STM32G474CBTx"
MCU_FP = "Package_QFP:LQFP-48_7x7mm_P0.5mm"
PINS = [
    (8, "PA0", "ADC_IN", "h", "ADC12_IN1 (fast channel), sampler output"),
    (9, "PA1", None, "nc", "spare (ADC12_IN2)"),
    (10, "PA2", "DAC_BIAS_A", "l", "OPAMP1_VOUT follower of DAC3_CH1 -> VBIAS_A stage"),
    (11, "PA3", None, "nc", "spare"),
    (12, "PA4", "DAC_TRIG", "l", "DAC1_OUT1 -> TRIG_LEVEL stage"),
    (13, "PA5", "DAC_OFS", "l", "DAC1_OUT2 -> VOFS stage"),
    (14, "PA6", "DAC_TAPTH", "l", "DAC2_OUT1 -> VTAP_TH divider"),
    (15, "PA7", None, "nc", "spare"),
    (30, "PA8", None, "nc", "reserved: OPAMP5_VOUT (DAC4_CH2 follower, spare analog output)"),
    (31, "PA9", "HOST_TX", "h", "USART1_TX (AF7) -> 100R R512 -> J501 pin 4"),
    (32, "PA10", "HOST_RX", "h", "USART1_RX (AF7) <- 100R R511 <- J501 pin 2"),
    (33, "PA11", "USB_DM", "h", "USB FS D-"),
    (34, "PA12", "USB_DP", "h", "USB FS D+ (internal 1.5k pull-up)"),
    (37, "PA13", "UC_SWDIO", "h", "SWDIO -> J501 pin 8"),
    (38, "PA14", "UC_SWCLK", "h", "SWCLK -> J501 pin 10"),
    (39, "PA15", "I2C_SCL", "h", "I2C1_SCL (AF4) -> MS5351M"),
    (7, "PG10", "UC_NRST", "h", "NRST, 100 nF -> J501 pin 14"),
    (5, "PF0", "MCU_CLK", "h", "OSC_IN, HSE bypass from MS5351M CLK1"),
    (6, "PF1", None, "nc", "OSC_OUT unused in bypass"),
    (2, "PC13", "LED", "l", "status LED D701, active low"),
    (3, "PC14", None, "nc", "spare"),
    (4, "PC15", None, "nc", "spare"),
    (16, "PB0", "FPGA_DONE", "h", "GPIO in (FPGA DONE)"),
    (17, "PB1", "DAC_BIAS_K", "l", "OPAMP3_VOUT follower of DAC3_CH2 -> VBIAS_K stage"),
    (18, "PB2", "FPGA_RECONFIG", "h", "GPIO open-drain (FPGA RECONFIG_N)"),
    (40, "PB3", "SPI_SCK", "h", "SPI1_SCK (AF5), master"),
    (41, "PB4", "SPI_MISO", "h", "SPI1_MISO (AF5); UCPD dead-battery pull-down until disabled"),
    (42, "PB5", "SPI_MOSI", "h", "SPI1_MOSI (AF5)"),
    (43, "PB6", "TRIG_SEL", "h", "GPIO out (TMUX136 select); UCPD dead-battery pull-down = 0 at reset"),
    (44, "PB7", "I2C_SDA", "h", "I2C1_SDA (AF4)"),
    (45, "PB8", "BOOT0", "l", "BOOT0: 10k pull-down, JP701 to +3V3 for the bootloader"),
    (46, "PB9", "DBG1", "h", "GPIO, debug -> J501 pin 12"),
    (22, "PB10", "SPI_CS", "h", "GPIO, SPI chip select (software NSS)"),
    (25, "PB11", "ADC_TRIG", "h", "EXTI11 = ADC12 regular external trigger (EXTSEL EXTI11)"),
    (26, "PB12", None, "nc", "reserved: OPAMP4_VOUT (DAC4_CH1 follower, ADC_REF_MID trim option)"),
    (27, "PB13", None, "nc", "spare"),
    (28, "PB14", None, "nc", "spare"),
    (29, "PB15", None, "nc", "spare"),
    (20, "VREF+", "VREFP", "l", "VREFBUF 2.9 V output, 1 uF + 100 nF"),
]


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
    sh = new_sheet("mcu_if", comments=["STM32G474CBT6 on board (USB FS, SWD + UART on J501, SPI/I2C to FPGA/clock).",
                                       "DAC scaling: difference amplifiers, TP2272 on +/-2.5 V."])
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
    decoupler(sh, "+2V5", (g(245), g(68)), ("100n", "100n", "100n"))
    decoupler(sh, "-2V5", (g(275), g(68)), ("100n", "100n", "100n"), gnd="GND")

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

    # I2C pull-ups
    for k, net in enumerate(("I2C_SCL", "I2C_SDA")):
        r = R(sh, "4.7k", (g(268 + 12 * k), g(160)))
        sh.power("+3V3", r["1"], dy=-2.54)
        sh.stub(r, "2", net)
    sh.text("I2C pull-ups 4.7k (MS5351M at 0x60)", (g(262), g(150)), size=1.0)
    mcu_section(sh)
    sh.save()


def mcu_section(sh):
    """STM32G474CBT6 with supplies, VREFBUF, VDDA filter, NRST, BOOT0, LED (placed last: new refs U704,
    C710..., R729..., FB701, JP701, D701; the existing refs stay as they were)."""
    shape = dict(hier_pins("mcu_if"))
    u = sh.add(MCU, "U", "STM32G474CBT6", (g(45), g(72)), fp=MCU_FP, lcsc="C730123",
               fields={"Price": "4.11 USD (LCSC C730123, 1 pc)",
                       "Note": "LQFP-48, 128 KB flash; CET6 (C730125, 512 KB) is the drop-in if flash runs short"})
    for pin, _port, net, how, _f in PINS:
        if how == "nc":
            sh.nc(u[str(pin)])
        elif how == "h":
            sh.stub(u, str(pin), net, length=g(4), kind="hlabel", shape=shape[net])
        else:
            sh.stub(u, str(pin), net, length=g(4))
    # VBAT + VDD x3 on one bus to +3V3, VDDA filtered (label), VSS + VSSA to GND
    pts = [u[p] for p in ("1", "24", "36", "48")]
    yb = pts[0][1] - g(3)
    for pt in pts:
        sh.wire(pt, (pt[0], yb))
    sh.wire((pts[0][0], yb), (pts[-1][0], yb))
    sh.power("+3V3", (pts[0][0], yb), dy=-2.54)
    sh.stub(u, "21", "VDDA", length=g(5))
    a, b = u["23"], u["19"]
    sh.wire(a, (a[0], a[1] + g(2)))
    sh.wire(b, (b[0], b[1] + g(2)))
    sh.wire((a[0], a[1] + g(2)), (b[0], b[1] + g(2)))
    sh.gnd((a[0], a[1] + g(2)))

    def capl(net, value, x, y):
        c = C(sh, value, (x, y))
        sh.stub(c, "1", net)
        sh.gnd(c["2"])
        return c

    sh.text("MCU supply (DS12288): 100 nF at each VDD (24, 36, 48) and VBAT, 10 uF bulk.\n"
            "VDDA: +3V3 through BLM15HD102 bead, 1 uF + 10 nF. VREF+: internal VREFBUF 2.9 V\n"
            "(docs/research/adc.md), 1 uF + 100 nF only, nothing else drives VREFP.", (g(10), g(174)), size=1.0)
    decoupler(sh, "+3V3", (g(12), g(186)), ("100n", "100n", "100n", "100n", "10u"), pitch=g(5))
    fb = sh.add("Device:FerriteBead_Small", "FB", "1k", (g(50), g(186)), fp="Inductor_SMD:L_0402_1005Metric",
                mpn="BLM15HD102SN1D", lcsc="C21516")
    sh.stub(fb, "1", "+3V3", kind="power")
    sh.stub(fb, "2", "VDDA")
    capl("VDDA", "1u", g(56), g(186))
    capl("VDDA", "10n", g(61), g(186))
    capl("VREFP", "1u", g(68), g(186))
    capl("VREFP", "100n", g(73), g(186))
    # NRST 100 nF (as C89 on the sensing board), BOOT0 pull-down + jumper, status LED
    capl("UC_NRST", "100n", g(84), g(186))
    rb = R(sh, "10k", (g(94), g(186)))
    sh.stub(rb, "1", "BOOT0")
    sh.gnd(rb["2"])
    jp = sh.add("Jumper:SolderJumper_2_Open", "JP", "BOOT0", (g(106), g(183)),
                fp="Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm")
    sh.stub(jp, "1", "BOOT0")
    sh.stub(jp, "2", "+3V3", kind="power")
    d = sh.add("Device:LED", "D", "green", (g(122), g(184)), rot=90, fp="LED_SMD:LED_0603_1608Metric")
    sh.stub(d, "2", "+3V3", kind="power")
    k = d["1"]
    rl = R(sh, "1k", (k[0], k[1] + 2.54 + 3.81))
    sh.wire(k, rl["1"])
    sh.stub(rl, "2", "LED")
    sh.text("NRST 100 nF; BOOT0 low (close JP701 for the\nUSB DFU / USART1 bootloader); LED on PC13, active low.",
            (g(84), g(199)), size=1.0)
    sh.text("STM32G474CBT6 pin plan:\n" + "\n".join(
        f"{pin:2d} {port:5s} {net or 'NC':13s} {f}" for pin, port, net, _h, f in PINS) +
        "\nHOST_RX/HOST_TX named as on the yanartas sensing board (MCU as host):\n"
        "HOST_RX = MCU UART RX, HOST_TX = MCU UART TX.", (g(9), g(118)), size=1.0)


if __name__ == "__main__":
    main()
