"""Shared definitions for the scope-fe sheet generators: sheet table (names, ref bases, sheet pins)
and passive-part helpers with default footprints and LCSC numbers.

LCSC numbers for jellybean passives are the usual JLCPCB "basic" parts (typical, re-check stock and
value before ordering). Prices are not tracked for passives (about 0.001-0.01 USD each)."""
from schlib import Sheet, g  # noqa: F401

# sheet name -> (title, ref_base, page, left pins [(net, shape)], right pins)
TAPS = [f"TAP{i}" for i in range(16)]
# MCU debug / console nets between the programming header J501 (fpga_clock; yanartas sensing board J3 pinout)
# and the STM32G474 (mcu_if). HOST_RX / HOST_TX follow the sensing board, where the MCU is the host:
# HOST_RX = MCU UART RX (J501 pin 2 via 100R), HOST_TX = MCU UART TX (J501 pin 4 via 100R).
# (net, shape on fpga_clock, shape on mcu_if)
MCU_DBG = [("UC_SWDIO", "bidirectional", "bidirectional"), ("UC_SWCLK", "output", "input"),
           ("UC_NRST", "bidirectional", "bidirectional"), ("DBG1", "bidirectional", "bidirectional"),
           ("HOST_RX", "output", "input"), ("HOST_TX", "input", "output")]
MCU_DBG_FPGA = [(n, a) for n, a, _b in MCU_DBG]      # shapes as seen from fpga_clock
MCU_DBG_MCU = [(n, b) for n, _a, b in MCU_DBG]       # shapes as seen from mcu_if
SHEETS = {
    "input": ("Input: 5:1 divider, BUF802 + OPA197 servo", 100, 2,
              [("VOFS", "input"), ("VNEG_REF", "input")],
              [("BUF_OUT_S", "output"), ("BUF_OUT_T", "output"), ("EXT_CLK", "output")]),
    "sampler": ("Sampler: diode bridge, hold, TPH2501 hold amp, level shift", 200, 3,
                [("BUF_OUT_S", "input"), ("STRB_A", "input"), ("STRB_K", "input"), ("VBIAS_A", "input"),
                 ("VBIAS_K", "input"), ("ADC_REF_MID", "input")],
                [("ADC_IN", "output")]),
    "trigger_phase": ("Trigger + phase recovery: TLV3801, 16-tap line, COS3502", 300, 4,
                      [("BUF_OUT_T", "input"), ("EXT_CLK", "input"), ("TRIG_SEL", "input"),
                       ("DAC_TRIG", "input"), ("PSTRB_A", "input"), ("PSTRB_K", "input"), ("VTAP_P", "input"),
                       ("VTAP_N", "input"), ("VTAP_TH", "input")],
                      [("COARSE", "output")] + [(t, "output") for t in TAPS]),
    "strobe": ("Strobe drivers: sampler (2x TRF37D73), phase (TRF + GVA-84+)",
               400, 5,
               [("S_STROBE_P", "input"), ("S_STROBE_N", "input"), ("PH_STROBE_P", "input"),
                ("PH_STROBE_N", "input"), None, ("+5V1", "input")],
               [("STRB_A", "output"), ("STRB_K", "output"), ("PSTRB_A", "output"), ("PSTRB_K", "output")]),
    "fpga_clock": ("FPGA GW1NZ-LV1QN48 and clock MS5351M", 500, 6,
                   [(t, "input") for t in TAPS] + [("COARSE", "input"), None, ("SPI_SCK", "input"),
                                                  ("SPI_MOSI", "input"), ("SPI_CS", "input"),
                                                  ("SPI_MISO", "output"), None, ("I2C_SCL", "input"),
                                                  ("I2C_SDA", "bidirectional"), ("FPGA_RECONFIG", "input"),
                                                  ("FPGA_DONE", "output")],
                   [("PH_STROBE_P", "output"), ("PH_STROBE_N", "output"), ("S_STROBE_P", "output"),
                    ("S_STROBE_N", "output"), None, ("ADC_TRIG", "output"), ("MCU_CLK", "output"), None]
                   + MCU_DBG_FPGA),
    "power": ("Power: USB-C 5 V in, +3V3, +1V2, +5V1, +5V, -5V, +2V5, -2V5", 600, 7, [],
              [("USB_DP", "bidirectional"), ("USB_DM", "bidirectional"), None, ("+5V1", "output")]),
    "mcu_if": ("MCU: STM32G474CBT6, control voltages", 700, 8,
               [("ADC_IN", "input"), ("ADC_TRIG", "input"), ("MCU_CLK", "input"), ("FPGA_DONE", "input"),
                ("SPI_MISO", "input"), None, ("SPI_SCK", "output"), ("SPI_MOSI", "output"), ("SPI_CS", "output"),
                ("FPGA_RECONFIG", "output"), ("I2C_SCL", "output"), ("I2C_SDA", "bidirectional"), None]
               + MCU_DBG_MCU + [None, ("USB_DP", "bidirectional"), ("USB_DM", "bidirectional")],
               [("ADC_REF_MID", "output"), ("VOFS", "output"), ("VNEG_REF", "output"), ("DAC_TRIG", "output"), ("TRIG_SEL", "output"),
                ("VBIAS_A", "output"), ("VBIAS_K", "output"), ("VTAP_P", "output"), ("VTAP_N", "output"),
                ("VTAP_TH", "output")]),
}
CRITICAL = ["input", "sampler", "trigger_phase", "strobe"]


def new_sheet(name: str, **kw) -> Sheet:
    title, base, _page, _l, _r = SHEETS[name]
    return Sheet(name, title=title, ref_base=base, **kw)


def hier_pins(name: str):
    """[(net, shape)] of all sheet pins of <name> (for hierarchical labels inside the sheet)."""
    _t, _b, _p, left, right = SHEETS[name]
    return [p for p in left + right if p]


# ----------------------------------------------------------------------------- passives
FP = {
    "R0402": "Resistor_SMD:R_0402_1005Metric", "R0603": "Resistor_SMD:R_0603_1608Metric",
    "C0402": "Capacitor_SMD:C_0402_1005Metric", "C0603": "Capacitor_SMD:C_0603_1608Metric",
    "C0805": "Capacitor_SMD:C_0805_2012Metric", "C1206": "Capacitor_SMD:C_1206_3216Metric",
    "R1206": "Resistor_SMD:R_1206_3216Metric",
    "FB0603": "Inductor_SMD:L_0603_1608Metric", "FB0805": "Inductor_SMD:L_0805_2012Metric",
}
# LCSC numbers, all verified on lcsc.com (product-detail JSON) on 24 Nov 2026: part number, value, tolerance,
# rating, package and stock; data and stock/prices in lcsc_parts.py (docs/bom.md "LCSC verification").
# JLC class (24 Nov 2026, BOM optimisation and BOM review 2): JLCPCB basic parts wherever one exists with an adequate
# rating (class per part from the jlcpcb.com parts API, componentLibraryType "base"); 1 % thick film everywhere, no
# 0.1 % part left (SPEC decisions 25, 30). Generic passives: UNI-ROYAL 0402WGF 1 % 0402; FH 0402CG
# C0G; Samsung X5R/X7R. One number per value / package / rating.
LCSC_R = {"0": "C17168", "10": "C25077", "22": "C25092", "33": "C25105", "49.9": "C25120",
          "100": "C25076", "120": "C25079", "470": "C25117", "510": "C25123", "1k": "C11702", "1.00k": "C11702",
          "1.5k": "C25867", "2.0k": "C4109", "2.2k": "C25879", "3.3k": "C25890", "4.7k": "C25900",
          "5.1k": "C25905", "10k": "C25744", "10.0k": "C25744", "15k": "C25756", "20k": "C25765", "22k": "C25768",
          "33k": "C25779", "100k": "C25741", "200k": "C25764", "1M": "C26083"}
# 0603 (power or voltage rating, or no 0402 basic value): all JLC basic (BOM review 2, 24 Nov 2026)
LCSC_R0603 = {"0": "C21189", "100": "C22775", "120": "C22787", "18k": "C25810", "150k": "C22807", "220k": "C22961",
              "300k": "C23024", "470k": "C23178", "510k": "C23192", "10M": "C7250"}
LCSC_R1206 = {"0": "C17888", "1": "C17928"}
# 0.1 % thin film: none left on the board (BOM review 2: the U603 divider is 1 %, SPEC decision 30)
LCSC_R01 = {}
# 0402 unless noted by the size rule in C(): pF/nF and 1u/2.2u/4.7u 0402, 10u/22u 0805
LCSC_C = {"0.5p": "C76912", "1.5p": "C76901", "2.2p": "C1559", "3.3p": "C76906", "18p": "C1549", "47p": "C1567",
          "100p": "C1546", "1n": "C1523", "10n": "C15195",
          "100n": "C1525", "1u": "C52923", "4.7u": "C23733", "10u": "C15850", "22u": "C45783"}
LCSC_C0603 = {"1u": "C15849", "4.7u": "C19666"}
LCSC_C1206 = {"47u": "C96123"}
LCSC_C_C0G = {"1n": "C53547"}          # parts whose Note asks for C0G where the default is X7R


def _note(kw) -> str:
    return str((kw.get("fields") or {}).get("Note", ""))


def _mpn(lcsc: str) -> str:
    try:
        from lcsc_parts import PARTS
    except ImportError:
        return ""
    return PARTS.get(lcsc, {}).get("mpn", "")


def R(sh: Sheet, value: str, at, rot: int = 0, size: str = "0402", ref: str = "R", **kw):
    fp = FP["R" + size]
    base = value.replace(" 0.1%", "")
    if value.endswith("0.1%") or "0.1 %" in _note(kw):
        table = LCSC_R01
    else:
        table = {"0603": LCSC_R0603, "1206": LCSC_R1206}.get(size, LCSC_R)
    lcsc = kw.pop("lcsc", "") or table.get(base, "")
    if lcsc and not kw.get("mpn"):
        kw["mpn"] = _mpn(lcsc)
    return sh.add("Device:R", ref, value, at, rot=rot, fp=fp, lcsc=lcsc, **kw)


def C(sh: Sheet, value: str, at, rot: int = 0, size: str | None = None, ref: str = "C", **kw):
    if size is None:
        # pF/nF values and 1u/2.2u/4.7u are 0402 (SPEC decision 9); bulk (10u and up) 0805
        size = "0402" if value.endswith(("p", "n")) or value in ("1u", "2.2u", "4.7u") else "0805"
    note = _note(kw)
    if size == "0603":
        table = LCSC_C0603
    elif size == "1206":
        table = LCSC_C1206
    elif "C0G" in note and value in LCSC_C_C0G:
        table = LCSC_C_C0G
    else:
        table = LCSC_C
    lcsc = kw.pop("lcsc", "") or table.get(value, "")
    if lcsc and not kw.get("mpn"):
        kw["mpn"] = _mpn(lcsc)
    return sh.add("Device:C", ref, value, at, rot=rot, fp=FP["C" + size], lcsc=lcsc, **kw)


def decoupler(sh: Sheet, rail: str, at, values=("100n",), pitch: float = 7.62, gnd: str = "GND"):
    """Row of vertical capacitors from <rail> (power symbol above) to GND (below), starting at 'at'."""
    caps = []
    x, y = at
    top = (x, y - 5.08)
    for i, v in enumerate(values):
        c = C(sh, v, (x + i * pitch, y))
        caps.append(c)
        if i == 0:
            sh.power(rail, c["1"], dy=-2.54)
            sh.power(gnd, c["2"], dy=2.54)
        else:
            p, q = caps[i - 1]["1"], caps[i - 1]["2"]
            sh.path([(p[0], p[1] - 2.54), (c["1"][0], p[1] - 2.54), c["1"]])
            sh.path([(q[0], q[1] + 2.54), (c["2"][0], q[1] + 2.54), c["2"]])
    return caps
