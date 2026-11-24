"""mcu_if.kicad_sch: STM32G474CBT6 microcontroller (on board since 21 Nov 2026; it replaced the 2x13 header
J701 to an external STM32 board), control-voltage networks, ADC reference divider, tap threshold divider,
I2C pull-ups. SWD, NRST, DBG1 and the UART (HOST_RX / HOST_TX, sensing-board naming: the MCU is the host,
HOST_RX = MCU RX) go to the programming header J501 on fpga_clock; USB FS (PA11/PA12) to the USB-C receptacle
on the power sheet. Pin plan: PINS below and kicad/README.md.

Control voltages (21 Nov 2026 simplification: the three TP2272 difference-amplifier packages U701-U703 and the
VMID buffer are gone; the DAC outputs drive passive networks, one op-amp section remains):
  PA4 DAC1_OUT1 -> DAC_TRIG (raw 0.2..2.7 V) -> passive sum with -2V5 at the TLV3801 (trigger_phase).
  PA5 DAC1_OUT2 -> VOFS (raw 0.2..2.7 V) -> Rofs into the OPA197 servo summing node (input sheet);
        mid-scale cancelled by Rmid from VNEG_REF.
  PA6 DAC2_OUT1 -> DAC_BIAS_A -> R733 7.5k / R734 4.7k divider to -2V5 -> VBIAS_A (-1.46..-0.50 V).
  PB1 OPAMP3_VOUT (DAC3_CH2 follower) -> DAC_BIAS_K -> R735 4.7k -> VBIAS_K, R736 5.1k to GND
        (24 Nov 2026, validation PARTS-4: 0.520 x Vdac = +0.10..+1.40 V, so the BAT15-04W reverse voltage stays
        <= 2.9 V at the -1.5 V input clamp; R735 isolates the 10 nF on the sampler sheet, DAC/OPAMP CL <= 50 pF).
  PA2 OPAMP1_VOUT (DAC3_CH1 follower) -> DAC_TAPTH -> 30k/1k divider -> VTAP_TH.
  U701 TLV9001 on +/-2V5: VNEG_REF = -VREF+ x 10.0k/14.7k = -1.973 V (ratiometric to the DAC reference, so the
        VOFS mid-scale cancellation does not drift with the -2V5 regulator); drives only Rmid (34.0k)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schlib import g
from common import new_sheet, hier_pins, R, C, decoupler

# U701: TLV9001IDBVR (TI, SOT-23-5, 1.8-5.5 V, RRIO, Vos 0.4 mV typ / 1.6 mV max, 0.6 uV/K). KiCad has no DBV
# symbol for it; OPA197xDBV has the identical DBV pinout: 1 OUT, 2 V-, 3 +IN, 4 -IN, 5 V+.
OPAMP = "Amplifier_Operational:OPA197xDBV"
OPA_FP = "Package_TO_SOT_SMD:SOT-23-5"
OPA_F = {"Price": "0.080 USD (LCSC C398363, 5+)", "MPN": "TLV9001IDBVR (TI), on +/-2V5 (5.0 V total, spec 1.8-5.5 V)",
         "Note": "VNEG_REF inverter; pinout = OPA197 DBV"}

# STM32G474CBT6 (LQFP-48) pin plan. Pin numbers: DS12288 LQFP48 pinout = KiCad MCU_ST_STM32G4:STM32G474CBTx.
# (pin, port, net, how): how h = hierarchical label, l = local label, nc = NC flag
MCU = "MCU_ST_STM32G4:STM32G474CBTx"
MCU_FP = "Package_QFP:LQFP-48_7x7mm_P0.5mm"
PINS = [
    (8, "PA0", "ADC_IN", "h", "ADC12_IN1 (fast channel), sampler output"),
    (9, "PA1", "TRIG_SEL", "h", "GPIO out (TMUX136 select); moved from PB6 for the layout fan-out"),
    (10, "PA2", "DAC_TAPTH", "l", "OPAMP1_VOUT follower of DAC3_CH1 -> VTAP_TH divider"),
    (11, "PA3", None, "nc", "spare"),
    (12, "PA4", "DAC_TRIG", "h", "DAC1_OUT1 -> TRIG_LEVEL sum at the TLV3801 (trigger_phase)"),
    (13, "PA5", "VOFS", "h", "DAC1_OUT2 -> Rofs into the OPA197 servo node (input)"),
    (14, "PA6", "DAC_BIAS_A", "l", "DAC2_OUT1 -> VBIAS_A divider to -2V5"),
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
    (6, "PF1", "DBG1", "h", "GPIO (OSC_OUT free in HSE bypass), debug -> J501 pin 12; moved from PB9"),
    (2, "PC13", None, "nc", "spare"),
    (3, "PC14", None, "nc", "spare"),
    (4, "PC15", None, "nc", "spare"),
    (16, "PB0", None, "nc", "spare"),
    (17, "PB1", "DAC_BIAS_K", "l", "OPAMP3_VOUT follower of DAC3_CH2 -> 4.7k / 5.1k divider -> VBIAS_K"),
    (18, "PB2", None, "nc", "spare"),
    (40, "PB3", "SPI_SCK", "h", "SPI1_SCK (AF5), master"),
    (41, "PB4", "SPI_MISO", "h", "SPI1_MISO (AF5); UCPD dead-battery pull-down until disabled"),
    (42, "PB5", "SPI_MOSI", "h", "SPI1_MOSI (AF5)"),
    (43, "PB6", "FPGA_DONE", "h", "GPIO in (FPGA DONE); UCPD dead-battery pull-down harmless on an input; moved from PB0"),
    (44, "PB7", "I2C_SDA", "h", "I2C1_SDA (AF4)"),
    (45, "PB8", "BOOT0", "l", "BOOT0: 10k pull-down, JP701 to +3V3 for the bootloader"),
    (46, "PB9", "SPI_CS", "h", "GPIO, SPI chip select (software NSS); moved from PB10"),
    (22, "PB10", None, "nc", "spare"),
    (25, "PB11", "ADC_TRIG", "h", "TIM2_CH4 (AF1) frame mark to FPGA pin 18; ADC12 triggered internally by TIM2_TRGO (OC4REF)"),
    (26, "PB12", None, "nc", "reserved: OPAMP4_VOUT (DAC4_CH1 follower, ADC_REF_MID trim option)"),
    (27, "PB13", "FPGA_RECONFIG", "h", "GPIO open-drain (FPGA RECONFIG_N); moved from PB2"),
    (28, "PB14", "LED", "l", "status LED D701, active low; moved from PC13"),
    (29, "PB15", None, "nc", "spare"),
    (20, "VREF+", "VREFP", "l", "VREFBUF 2.9 V output, 1 uF + 100 nF"),
]


def main():
    sh = new_sheet("mcu_if", comments=["STM32G474CBT6 on board (USB FS, SWD + UART on J501, SPI/I2C to FPGA/clock).",
                                       "Control voltages: DAC outputs into passive networks; U701 TLV9001 makes VNEG_REF."])
    T = 1.0
    # ---------------------------------------------------------------- ADC_REF_MID divider (unchanged R703/R704/C702)
    r3 = R(sh, "30k", (g(150), g(30)), ref="R703")
    sh.stub(r3, "1", "VREFP")
    r4 = R(sh, "10k", (g(150), g(40)), ref="R704")
    sh.wire(r3["2"], r4["1"])
    sh.gnd(r4["2"])
    c = C(sh, "10n", (g(156), g(40)), ref="C702")
    sh.path([r3["2"], (c["1"][0], r3["2"][1]), c["1"]])
    sh.gnd(c["2"])
    sh.path([(c["1"][0], r3["2"][1]), (c["1"][0] + g(6), r3["2"][1])])
    sh.hlabel("ADC_REF_MID", (c["1"][0] + g(6), r3["2"][1]), "output")
    sh.text("ADC_REF_MID = VREF+ x 10k/40k = 0.725 V\n(level-shift reference on the sampler sheet)",
            (g(145), g(20)), size=T)

    # ---------------------------------------------------------------- VNEG_REF: U701 TLV9001 inverter from VREF+
    x, y = g(120), g(80)
    u = sh.add(OPAMP, "U701", "TLV9001IDBVR", (x, y), fp=OPA_FP, lcsc="C398363", fields=OPA_F)
    plus, minus, o = u["3"], u["4"], u["1"]
    sh.path([plus, (plus[0] - g(3), plus[1])])
    sh.power("GND", (plus[0] - g(3), plus[1]), dy=-g(3), rot=180)
    M = (minus[0] - g(4), minus[1])
    sh.wire(minus, M)
    rin = R(sh, "14.7k", (M[0] - g(6), M[1]), rot=90, ref="R731", fields={"Note": "0.1 % 25 ppm/K"})
    sh.wire(rin["2"], M)
    sh.stub(rin, "1", "VREFP")
    X = o[0] + g(3)
    yf, yc = minus[1] + g(10), minus[1] + g(15)
    rf = R(sh, "10.0k", (x, yf), rot=90, ref="R732", lcsc="C25744", fields={"Note": "0.1 % 25 ppm/K"})
    cf = C(sh, "100n", (x, yc), rot=90, ref="C722")
    sh.path([M, (M[0], yc), cf["1"]])
    sh.wire((M[0], yf), rf["1"])
    sh.path([cf["2"], (X, yc), (X, o[1])])
    sh.wire(rf["2"], (X, yf))
    sh.wire(o, (X, o[1]))
    E = (X + g(6), o[1])
    sh.wire((X, o[1]), E)
    sh.hlabel("VNEG_REF", E, "output")
    sh.stub(u, "5", "+2V5", kind="power")
    sh.power("-2V5", u["2"], dy=g(4))
    cp = C(sh, "100n", (x + g(14), y - g(12)), ref="C720")
    sh.power("+2V5", cp["1"], dy=-2.54)
    sh.gnd(cp["2"])
    cn = C(sh, "100n", (x + g(20), y - g(12)), ref="C721")
    sh.power("GND", cn["1"], dy=-2.54, rot=180)
    sh.power("-2V5", cn["2"], dy=5.08)
    sh.text("VNEG_REF = -VREF+ x R732/R731 = -1.973 V, ratiometric to the DACs\n"
            "(mid-scale of VOFS cancels independent of VREF+ and of -2V5).\n"
            "Load: Rmid 34.0k on the input sheet only. C722 100n: 160 Hz.\n"
            "U701 TLV9001IDBVR on +/-2V5; C720/C721 at its pins 5/2.\n"
            "Reset: VREFBUF off (VREF+ ~0 V) -> VNEG_REF = 0 V.", (g(95), g(102)), size=T)

    # ---------------------------------------------------------------- VBIAS_A: divider DAC -> -2V5 (no op-amp)
    xa, ya = g(185), g(70)
    ra = R(sh, "7.5k", (xa, ya), ref="R733", fields={"Note": "1 %"})
    sh.stub(ra, "1", "DAC_BIAS_A")
    rb = R(sh, "4.7k", (xa, ya + g(10)), ref="R734", lcsc="C25900", fields={"Note": "1 %"})
    sh.wire(ra["2"], rb["1"])
    sh.power("-2V5", rb["2"], dy=5.08)
    N = (xa + g(10), ra["2"][1])
    sh.wire(ra["2"], N)
    sh.hlabel("VBIAS_A", N, "output")
    sh.text("VBIAS_A = 0.385 x Vdac - 0.615 x 2.5 V (Thevenin 2.89k,\n"
            "with 10 nF on the sampler sheet: 5.5 kHz):\n"
            "DAC 0.2..2.7 V -> -1.46..-0.50 V, 0.27 mV/LSB.\n"
            "Reset (PA6 high-Z, clamped ~-0.4 V): about -1.7 V = reverse bias.\n"
            "DAC load 12.2k to -2V5 (<= 0.43 mA).", (g(170), g(52)), size=T)

    # ---------------------------------------------------------------- VBIAS_K: DAC3_CH2 follower, isolation, pull-down
    xk, yk = g(185), g(118)
    rk = R(sh, "4.7k", (xk + g(6), yk), rot=90, ref="R735", lcsc="C25900",
           fields={"Note": "1 %; with R736: VBIAS_K = 0.520 Vdac, isolates the 10 nF (DAC CL <= 50 pF)"})
    K = (xk, yk)
    sh.wire(K, rk["1"])
    sh.wire((xk - g(6), yk), K)
    sh.label("DAC_BIAS_K", (xk - g(6), yk), rot=180)
    E = (rk["2"][0] + g(4), yk)
    sh.wire(rk["2"], E)
    rpd = R(sh, "5.1k", (E[0] - g(2), yk + g(5)), ref="R736", lcsc="C25905",
            fields={"Note": "1 %; VBIAS_K divider (max 1.40 V, PARTS-4) and reset state VBIAS_K = 0 V"})
    sh.wire((E[0] - g(2), yk), rpd["1"])
    sh.gnd(rpd["2"])
    sh.hlabel("VBIAS_K", E, "output")
    sh.text("VBIAS_K = 0.520 x Vdac (DAC3_CH2 -> OPAMP3 -> PB1 -> R735 4.7k / R736 5.1k):\n"
            "+0.10..+1.40 V, 0.37 mV/LSB; nominal +1.3 V (sim/strobe_arms). Bridge reverse voltage\n"
            "<= 1.40 + 1.5 V (CLL clamp) = 2.9 V < 4 V (PARTS-4). Thevenin 2.45k: rectified strobe\n"
            "current 4.3 uA x 3.45k = 15 mV (calibrated). DAC load 9.8k (<= 0.28 mA). Reset: 0 V.",
            (g(170), g(135)), size=T)

    # ---------------------------------------------------------------- VTAP_TH divider (unchanged), VTAP_P/N rails
    r5 = R(sh, "30k", (g(90), g(160)), ref="R723")
    sh.stub(r5, "1", "DAC_TAPTH")
    r6 = R(sh, "1k", (g(90), g(170)), ref="R724")
    sh.wire(r5["2"], r6["1"])
    sh.gnd(r6["2"])
    c = C(sh, "100n", (g(96), g(170)), ref="C709")
    sh.path([r5["2"], (c["1"][0], r5["2"][1]), c["1"]])
    sh.gnd(c["2"])
    sh.path([(c["1"][0], r5["2"][1]), (c["1"][0] + g(6), r5["2"][1])])
    sh.hlabel("VTAP_TH", (c["1"][0] + g(6), r5["2"][1]), "output")
    sh.text("VTAP_TH = Vdac/31: 3..90 mV, 0.02 mV/LSB (phase RESULT: 0..+80 mV)", (g(80), g(150)), size=T)
    for k, (rail, net) in enumerate((("+2V5", "VTAP_P"), ("-2V5", "VTAP_N"))):
        r = R(sh, "0", (g(140 + 20 * k), g(165)), rot=90, size="0603", ref=f"R{725 + k}")
        sh.stub(r, "1", rail, kind="power")
        sh.stub(r, "2", net, kind="hlabel", shape="output", length=g(3))
    sh.text("VTAP_P/N = +2V5/-2V5 (phase RESULT: 12.5 mA per rail, fixed).\n"
            "0R links: replace by a DAC-driven stage if a trim turns out to be needed.", (g(135), g(150)), size=T)

    # DAC_TRIG / VOFS leave as raw DAC voltages (hierarchical labels at PA4 / PA5)
    sh.text("DAC_TRIG (PA4) and VOFS (PA5) are raw DAC outputs (0.2..2.7 V):\n"
            "summing networks at the TLV3801 (trigger_phase) and at the\n"
            "OPA197 servo node (input). DAC1/DAC2 buffered: RL >= 5k, CL <= 50 pF.", (g(225), g(92)), size=T)

    # I2C pull-ups
    for k, net in enumerate(("I2C_SCL", "I2C_SDA")):
        r = R(sh, "4.7k", (g(268 + 12 * k), g(160)), ref=f"R{727 + k}")
        sh.power("+3V3", r["1"], dy=-2.54)
        sh.stub(r, "2", net)
    sh.text("I2C pull-ups 4.7k (MS5351M at 0x60)", (g(262), g(150)), size=T)
    # TRIG_SEL reset pull-down (PA1 floats at reset). Without it the TMUX136 SEL network (10k series, 18k to
    # -2V5) pulls the floating pin towards -2V5 (MCU clamp) and SEL to about -1.6 V below the switch ground.
    # 2.0k: pin at -0.17 V (inside the -0.3 V limit), SEL at -1.00 V = 0.11 V below VSW_GND (-0.89 V);
    # 1.65 mA from the GPIO when high. (5.1k would leave the pin at -0.39 V and SEL at -1.14 V.)
    rts = R(sh, "2.0k", (g(292), g(160)), ref="R737", fields={"Note": "TRIG_SEL reset pull-down"})
    sh.stub(rts, "1", "TRIG_SEL", kind="hlabel", shape="output")
    sh.gnd(rts["2"])
    sh.text("R737: TRIG_SEL pull-down (PA1 has none at reset)", (g(286), g(172)), size=T)
    # MCU part refs continue as before: U704, C710..C719, R729, R730, FB701, JP701, D701
    sh._refn.update({"U": 3, "C": 9, "R": 28})
    mcu_section(sh)
    # PWR_FLAG: VDDA is driven through FB701 from +3V3 (ERC power_pin_not_driven otherwise)
    sh.power("PWR_FLAG", (g(20), g(215)))
    sh.wire((g(20), g(215)), (g(20), g(217)))
    sh.label("VDDA", (g(20), g(217)))
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
    sh.text("NRST 100 nF; BOOT0 low (close JP701 for the\nUSB DFU / USART1 bootloader); LED on PB14, active low.",
            (g(84), g(199)), size=1.0)
    sh.text("STM32G474CBT6 pin plan:\n" + "\n".join(
        f"{pin:2d} {port:5s} {net or 'NC':13s} {f}" for pin, port, net, _h, f in PINS) +
        "\nHOST_RX/HOST_TX named as on the yanartas sensing board (MCU as host):\n"
        "HOST_RX = MCU UART RX, HOST_TX = MCU UART TX.", (g(9), g(118)), size=1.0)


if __name__ == "__main__":
    main()
