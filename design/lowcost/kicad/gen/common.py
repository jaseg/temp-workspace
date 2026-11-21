"""Shared definitions for the scope-fe sheet generators: sheet table (names, ref bases, sheet pins)
and passive-part helpers with default footprints and LCSC numbers.

LCSC numbers for jellybean passives are the usual JLCPCB "basic" parts (typical, re-check stock and
value before ordering). Prices are not tracked for passives (about 0.001-0.01 USD each)."""
from schlib import Sheet, g  # noqa: F401

# sheet name -> (title, ref_base, page, left pins [(net, shape)], right pins)
TAPS = [f"TAP{i}" for i in range(16)]
SHEETS = {
    "input": ("Input: 5:1 divider, BUF802 + OPA197 servo", 100, 2,
              [("VOFS", "input")],
              [("BUF_OUT_S", "output"), ("BUF_OUT_T", "output"), ("EXT_CLK", "output")]),
    "sampler": ("Sampler: diode bridge, hold, TPH2501 hold amp, level shift", 200, 3,
                [("BUF_OUT_S", "input"), ("STRB_A", "input"), ("STRB_K", "input"), ("VBIAS_A", "input"),
                 ("VBIAS_K", "input"), ("ADC_REF_MID", "input")],
                [("ADC_IN", "output")]),
    "trigger_phase": ("Trigger + phase recovery: TLV3801, 16-tap line, COS3502", 300, 4,
                      [("BUF_OUT_T", "input"), ("EXT_CLK", "input"), ("TRIG_SEL", "input"),
                       ("TRIG_LEVEL", "input"), ("PSTRB_A", "input"), ("PSTRB_K", "input"), ("VTAP_P", "input"),
                       ("VTAP_N", "input"), ("VTAP_TH", "input")],
                      [("COARSE", "output")] + [(t, "output") for t in TAPS]),
    "strobe": ("Strobe drivers: sampler (2x TRF37D73), phase (TRF + GVA-84+)",
               400, 5,
               [("S_STROBE_P", "input"), ("S_STROBE_N", "input"), ("PH_STROBE_P", "input"),
                ("PH_STROBE_N", "input")],
               [("STRB_A", "output"), ("STRB_K", "output"), ("PSTRB_A", "output"), ("PSTRB_K", "output")]),
    "fpga_clock": ("FPGA GW1NZ-LV1QN48 and clock MS5351M", 500, 6,
                   [(t, "input") for t in TAPS] + [("COARSE", "input"), None, ("SPI_SCK", "input"),
                                                  ("SPI_MOSI", "input"), ("SPI_CS", "input"),
                                                  ("SPI_MISO", "output"), None, ("I2C_SCL", "input"),
                                                  ("I2C_SDA", "bidirectional"), ("FPGA_RECONFIG", "input"),
                                                  ("FPGA_DONE", "output")],
                   [("PH_STROBE_P", "output"), ("PH_STROBE_N", "output"), ("S_STROBE_P", "output"),
                    ("S_STROBE_N", "output"), None, ("ADC_TRIG", "output"), ("MCU_CLK", "output")]),
    "power": ("Power: USB-C 5 V in, +3V3, +1V2, +5V, -5V, +2V5, -2V5", 600, 7, [], []),
    "mcu_if": ("MCU interface: STM32G474 header, DAC scaling", 700, 8,
               [("ADC_IN", "input"), ("ADC_TRIG", "input"), ("MCU_CLK", "input"), ("FPGA_DONE", "input"),
                ("SPI_MISO", "input"), None, ("SPI_SCK", "output"), ("SPI_MOSI", "output"), ("SPI_CS", "output"),
                ("FPGA_RECONFIG", "output"), ("I2C_SCL", "output"), ("I2C_SDA", "bidirectional")],
               [("ADC_REF_MID", "output"), ("VOFS", "output"), ("TRIG_LEVEL", "output"), ("TRIG_SEL", "output"),
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
    "FB0603": "Inductor_SMD:L_0603_1608Metric", "FB0805": "Inductor_SMD:L_0805_2012Metric",
}
# entries removed 2026-11-21 whose C number pointed at another value (24.9k, 25.5k, 30k, 40.2k, 60.4k,
# 16.5k, 78.7k, 499k, 1.54M): fill in after an LCSC search
# Removed 2026-11-21 (C number was another value on lcsc.com): 24.9k, 25.5k, 30k, 40.2k, 60.4k, 16.5k, 78.7k,
# 499k, 1.54M, 2.2u (0603 part), 220p (0603 part), 4.7u (0402, no stock). Fill in after an LCSC search.
LCSC_R = {"0": "C17168", "10": "C25077", "22": "C25092", "33": "C25105", "120": "C25079", "1k": "C11702",
          "2.2k": "C25879", "4.7k": "C25900", "5.1k": "C25905", "10k": "C25744", "20k": "C25765",
          "49.9k": "C25897", "100k": "C25741"}
LCSC_C = {"100n": "C1525", "1u": "C52923", "10n": "C15195", "10u": "C15850", "22u": "C45783", "18p": "C1549"}


def R(sh: Sheet, value: str, at, rot: int = 0, size: str = "0402", ref: str = "R", **kw):
    fp = FP["R" + size]
    return sh.add("Device:R", ref, value, at, rot=rot, fp=fp, lcsc=kw.pop("lcsc", LCSC_R.get(value, "")), **kw)


def C(sh: Sheet, value: str, at, rot: int = 0, size: str | None = None, ref: str = "C", **kw):
    if size is None:
        # pF/nF values and 1u/2.2u are 0402 (SPEC decision 9); bulk (4.7u and up) 0805
        size = "0402" if value.endswith(("p", "n")) or value in ("1u", "2.2u") else "0805"
    return sh.add("Device:C", ref, value, at, rot=rot, fp=FP["C" + size],
                  lcsc=kw.pop("lcsc", LCSC_C.get(value, "")), **kw)


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
