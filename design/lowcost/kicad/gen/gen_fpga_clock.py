"""fpga_clock.kicad_sch: GW1NZ-LV1QN48C6/I5 FPGA, MS5351M clock generator with 25 MHz crystal, JTAG,
configuration straps, decoupling, programming header J501 (Würth WR-WST 490107671612, yanartas sensing
board J3 pinout: FPGA JTAG + DBG2 and the MCU SWD/UART/NRST/DBG1 nets, which continue to the STM32G474 on mcu_if).

Pinout source: Gowin UG842-1.6.8E "GW1NZ-1 Pinout" (pin list, QN48 column) and UG843-1.8.7E figure 3-6
(QN48 top view): Bank0 = pins 3-8, 35, 38-48; Bank1 = pins 9-11, 13-24, 27-34; VCC 12, 37; VCCIO0 1;
VCCIO1 25; VCCX 36; VSS 2, 26; EPAD to GND. DS841-2.8E: GW1NZ-1 has no true LVDS (LVDS column NONE for
all pins; "GW1NZ-1 only supports ELVDS output"); emulated LVDS needs VCCIO 2.5 V and an external resistor
network, so the strobes here are complementary LVCMOS33 outputs on True/Comp pairs (IOT16A/B, IOT17A/B).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import schlib
from schlib import g
from common import new_sheet, R, C, decoupler, MCU_DBG_FPGA

IO, PWR = "bidirectional", "power_in"

# (pin, pin name per UG842, net, how) ; how: h = hierarchical label, l = local label, nc
BANK1 = [(9, "IOR2A", "TAP0", "h"), (10, "IOR2B", "TAP1", "h"), (11, "IOR3A", "TAP2", "h"),
         (13, "IOR10B", "TAP3", "h"), (14, "IOR6B/MO/D6", "TAP4", "h"), (15, "IOR6D/MCLK/D4", "TAP5", "h"),
         (16, "IOR6F", "TAP6", "h"), (17, "IOR6G", "TAP7", "h"), (18, "IOR6H", "TAP8", "h"),
         (19, "IOR6J/DOUT/WE_N", "TAP9", "h"), (20, "IOR10A", "TAP10", "h"), (21, "IOR7B/GCLKC_3", "TAP11", "h"),
         (22, "IOR9A/SI/D2", "TAP12", "h"), (23, "IOR8B", "TAP13", "h"), (24, "IOR8A/SO/D1", "TAP14", "h"),
         (27, "IOR7A/GCLKT_3/SSPI_CS_N/D0", "TAP15", "h"), (28, "IOR6I/DIN/CLKHOLD_N", "SPI_SCK", "h"),
         (29, "IOR6E/FASTRD_N/D3", "SPI_MOSI", "h"), (30, "IOR6C/MCS_N/D5", "SPI_MISO", "h"),
         (31, "IOR6A/MI/D7", "SPI_CS", "h"), (33, "IOR5A/GCLKT_2/RPLL_T_in", "FPGA_CLK", "l"),
         (32, "IOR5B/GCLKC_2/RPLL_C_in", None, "nc"), (34, "IOR3B", "CLK2_FPGA", "l")]
BANK0 = [(40, "IOT16A", "PH_STROBE_P", "h"), (39, "IOT16B", "PH_STROBE_N", "h"),
         (38, "IOT17A", "S_STROBE_P", "h"), (35, "IOT17B", "S_STROBE_N", "h"),
         (41, "IOT15B", "ADC_TRIG", "h"), (47, "IOT10A/GCLKT_0", "COARSE", "h"),
         (48, "IOT9B/RECONFIG_N", "FPGA_RECONFIG", "h"), (46, "IOT12A/DONE", "FPGA_DONE", "h"),
         (45, "IOT12B/READY", "FPGA_READY", "l"), (44, "IOT13A/JTAGSEL_N", "JTAGSEL_N", "l"),
         (43, "IOT14A/MODE0", "FPGA_MODE0", "l"), (42, "IOT14B/MODE1", "FPGA_MODE1", "l"),
         (3, "IOT7B/TCK", "JTAG_TCK", "l"), (4, "IOT7A/TMS", "JTAG_TMS", "l"), (5, "IOT8A/TDI", "JTAG_TDI", "l"),
         (7, "IOT8B/TDO", "JTAG_TDO", "l"), (6, "IOT9A/SCLK", "DBG2", "l"), (8, "IOT10B/GCLKC_0", None, "nc")]
TOP = [(12, "VCC", "+1V2"), (37, "VCC", "+1V2"), (36, "VCCX", "+3V3"), (1, "VCCIO0", "+3V3"),
       (25, "VCCIO1", "+3V3")]
BOT = [(2, "VSS"), (26, "VSS"), (49, "EPAD")]


def fpga_symbol():
    return schlib.ic_symbol(
        "GW1NZ-LV1QN48",
        left=[(str(p), n, IO) for p, n, _net, _h in BANK1],
        right=[(str(p), n, IO) for p, n, _net, _h in BANK0],
        top=[(str(p), n, PWR) for p, n, _ in TOP],
        bottom=[(str(p), n, PWR) for p, n in BOT],
        width=g(48), footprint="Package_DFN_QFN:QFN-48-1EP_6x6mm_P0.4mm_EP4.3x4.3mm",
        datasheet="https://cdn.gowinsemi.com.cn/UG842E.pdf",
        description="Gowin GW1NZ-1 FPGA, QN48 6x6 mm 0.4 mm; pinout UG842 (QN48 column)")


def series_out(sh, sym, pin, value, net, kind="label", shape="output"):
    p = sym[pin]
    d = sym.pin_dir(pin)
    r = R(sh, value, (p[0] + d[0] * (2.54 + 3.81), p[1]), rot=90 if d[0] > 0 else 270)
    sh.wire(p, r["1"])
    sh.stub(r, "2", net, kind=kind, shape=shape)
    return r


def pull(sh, net, at, value="4.7k", to="+3V3"):
    """Vertical resistor at 'at': pin 1 to rail (+3V3 above or GND below), pin 2 / pin 1 to label <net>."""
    r = R(sh, value, at)
    if to == "GND":
        sh.stub(r, "1", net)          # label above
        sh.gnd(r["2"])
    else:
        sh.power(to, r["1"], dy=-2.54)
        sh.stub(r, "2", net)          # label below
    return r


def main():
    sh = new_sheet("fpga_clock", comments=[
        "Pinout: Gowin UG842-1.6.8E (QN48) + UG843 fig. 3-6",
        "VCCIO0/1 = VCCX = 3.3 V, VCC = 1.2 V; strobes LVCMOS33"])
    fid = fpga_symbol()
    u = sh.add(fid, "U", "GW1NZ-LV1QN48C6/I5", (g(190), g(115)),
               fp="Package_DFN_QFN:QFN-48-1EP_6x6mm_P0.4mm_EP4.3x4.3mm", lcsc="C5799569",
               fields={"Price": "6.68 USD (LCSC, 1 pc)"})
    for p, _n, net, how in BANK1 + BANK0:
        if how == "nc":
            sh.nc(u[str(p)])
        else:
            sh.stub(u, str(p), net, length=5.08, kind="hlabel" if how == "h" else "label",
                    shape="input" if net.startswith(("TAP", "SPI_S", "SPI_M", "COARSE", "FPGA_RECONFIG"))
                    and net != "SPI_MISO" else "output")
    # supply pins: one short bus per rail with a single power symbol (adjacent symbols' texts overlapped)
    for rail in ("+1V2", "+3V3"):
        pts = [u[str(p)] for p, _n, r in TOP if r == rail]
        yb = pts[0][1] - g(3)
        for pt in pts:
            sh.wire(pt, (pt[0], yb))
        if len(pts) > 1:
            sh.wire((pts[0][0], yb), (pts[-1][0], yb))
        end = pts[0] if rail == "+1V2" else pts[-1]
        sh.power(rail, (end[0], yb), dy=-2.54)
    pts = [u[str(p)] for p, _n in BOT]
    yb = pts[0][1] + g(3)
    for pt in pts:
        sh.wire(pt, (pt[0], yb))
    sh.wire((pts[0][0], yb), (pts[-1][0], yb))
    sh.gnd((pts[1][0], yb))

    # decoupling next to the FPGA (one 100 nF per supply pin, bulk 10 uF per rail)
    sh.text("FPGA decoupling: 100 nF at each of pins 12, 37 (VCC) and 36, 1, 25 (VCCX, VCCIO0/1)",
            (g(150), g(170)))
    decoupler(sh, "+1V2", (g(150), g(180)), ("100n", "100n", "10u"))
    decoupler(sh, "+3V3", (g(180), g(180)), ("100n", "100n", "100n", "10u"))

    # configuration straps (UG842 pin definitions; mode values per UG290, see README open points)
    x0, y0 = g(235), g(30)
    sh.text("Configuration: internal flash (autoboot), MODE1=MODE0=0 via 4.7k pull-downs.\n"
            "RECONFIG_N, DONE, READY open-drain with 4.7k pull-ups; MCU sees FPGA_DONE and drives FPGA_RECONFIG.\n"
            "JTAGSEL_N pulled up (JTAG pins dedicated); close JP501 to force JTAG if they were reused as GPIO.",
            (x0 - g(30), y0 - g(14)))
    pull(sh, "FPGA_RECONFIG", (x0, y0))
    pull(sh, "FPGA_DONE", (x0 + g(16), y0))
    pull(sh, "FPGA_READY", (x0 + g(32), y0))
    rj = pull(sh, "JTAGSEL_N", (x0 + g(48), y0))
    jp = sh.add("Jumper:SolderJumper_2_Open", "JP", "JTAGSEL", (x0 + g(64), y0 + g(8)),
                fp="Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm")
    sh.stub(jp, "1", "JTAGSEL_N")
    sh.stub(jp, "2", "GND", kind="gnd")
    pull(sh, "FPGA_MODE0", (x0, y0 + g(22)), to="GND")
    pull(sh, "FPGA_MODE1", (x0 + g(16), y0 + g(22)), to="GND")
    pull(sh, "JTAG_TCK", (x0 + g(32), y0 + g(22)), to="GND")

    # programming header J501: Würth WR-WST 490107671612 (2x08 Redfit IDC direct-to-board, footprint only),
    # same part and pinout as the yanartas sensing board J3 (odd pins left, even pins right):
    #  1 VBUS (5 V)  2 HOST_RX (100 R)  3 +3V3  4 HOST_TX (100 R)  5 DBG2 (FPGA pin 6)  6 GND
    #  7 TCK  8 UC_SWDIO  9 TMS  10 UC_SWCLK  11 TDI  12 DBG1  13 TDO  14 UC_NRST  15 GND  16 GND
    j = sh.add("Connector_Generic:Conn_02x08_Odd_Even", "J501", "WR-WST 490107671612", (g(280), g(130)),
               fp="scope-fe:Würth_WR-WST_debug_490107671612_2x08_P2.54mm_Vertical", lcsc="NA",
               mpn="Würth 490107671612",
               fields={"Note": "footprint only; same part and pinout as the yanartas sensing board J3"})
    p1, p3 = j["1"], j["3"]
    sh.stub(j, "1", "VBUS", kind="power")                       # VBUS (USB 5 V) up, short stub
    xr = p3[0] - g(12)                                         # +3V3: further left, then up past pin 1
    sh.path([p3, (xr, p3[1])])
    sh.power("+3V3", (xr, p3[1]), dy=p1[1] - p3[1] - 2.54)
    for pin, rot in (("15", 270), ("6", 90), ("16", 90)):     # GND symbols pointing away from the body
        p, d = j[pin], j.pin_dir(pin)
        e = (p[0] + d[0] * 2.54, p[1])
        sh.wire(p, e)
        sh.power("GND", e, rot=rot)
    for pin, net in (("5", "DBG2"), ("7", "JTAG_TCK"), ("9", "JTAG_TMS"), ("11", "JTAG_TDI"), ("13", "JTAG_TDO")):
        sh.stub(j, pin, net, length=g(6))
    xl = j["2"][0] + g(20)                                     # right-hand hierarchical labels aligned here
    for pin, net, ref, xc in (("2", "HOST_RX", "R511", g(6)), ("4", "HOST_TX", "R512", g(12))):
        p = j[pin]
        r = R(sh, "100", (p[0] + xc, p[1]), rot=90, ref=ref, lcsc="C25076")   # staggered: texts do not collide
        sh.wire(p, r["1"])
        sh.wire(r["2"], (xl, p[1]))
        sh.hlabel(net, (xl, p[1]), dict(MCU_DBG_FPGA)[net])
    for pin, net in (("8", "UC_SWDIO"), ("10", "UC_SWCLK"), ("12", "DBG1"), ("14", "UC_NRST")):
        sh.stub(j, pin, net, length=g(20), kind="hlabel", shape=dict(MCU_DBG_FPGA)[net])
    sh.text("J501 programming header: Würth WR-WST 490107671612 (Redfit IDC, footprint only),\n"
            "pinout of the yanartas sensing board J3. FPGA JTAG (TCK/TMS/TDI/TDO, DBG2 = FPGA pin 6)\n"
            "and the STM32G474 SWD / UART / NRST / DBG1 (mcu_if; NRST 100 nF at the MCU).\n"
            "HOST_RX/HOST_TX named as on the sensing board (MCU = host): HOST_RX = MCU RX (PA10).\n"
            "1 VBUS 2 HOST_RX 3 +3V3 4 HOST_TX 5 DBG2 6 GND 7 TCK 8 SWDIO\n"
            "9 TMS 10 SWCLK 11 TDI 12 DBG1 13 TDO 14 NRST 15 GND 16 GND", (g(255), g(150)), size=1.0)

    # MS5351M clock generator (pin-compatible with Si5351A-B-GT, MSOP-10) + 25 MHz crystal
    ck = sh.add("Oscillator:Si5351A-B-GT", "U", "MS5351M", (g(70), g(60)),
                fp="Package_SO:MSOP-10_3x3mm_P0.5mm", lcsc="C1509083",
                fields={"Price": "0.91 USD (LCSC)", "Note": "Si5351A-B-GT compatible, I2C addr 0x60"})
    sh.stub(ck, "1", "+3V3", kind="power")
    sh.stub(ck, "7", "+3V3", kind="power")
    sh.stub(ck, "8", "GND", kind="gnd")
    sh.stub(ck, "4", "I2C_SCL", length=5.08, kind="hlabel", shape="input")
    sh.stub(ck, "5", "I2C_SDA", length=5.08, kind="hlabel", shape="bidirectional")
    series_out(sh, ck, "10", "33", "FPGA_CLK")
    series_out(sh, ck, "9", "33", "MCU_CLK", kind="hlabel")
    series_out(sh, ck, "6", "33", "CLK2_FPGA")
    y = sh.add("Device:Crystal_GND24", "Y", "25MHz", (g(40), g(50)),
               fp="Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", lcsc="C9006",
               fields={"Note": "25 MHz, CL 8 pF (Si5351 internal load caps), ESR < 100R"})
    sh.wire(ck["2"], y["3"], via="vh")
    sh.path([ck["3"], (y["1"][0] - 2.54, ck["3"][1]), (y["1"][0] - 2.54, y["1"][1]), y["1"]])
    sh.power("GND", y["2"], dy=-2.54, rot=180)
    sh.stub(y, "4", "GND", kind="gnd")
    decoupler(sh, "+3V3", (g(50), g(85)), ("100n", "100n", "10u"))
    sh.text("MS5351M: CLK0 -> FPGA_CLK (RPLL_T_in pin 33), CLK1 -> MCU_CLK (STM32 HSE bypass),\n"
            "CLK2 -> FPGA pin 34 (spare clock / beat mode). One 100 nF each at VDD and VDDO.",
            (g(25), g(98)))
    sh.text("Pin plan (UG842): Bank1 = TAP0..15 (COS3502 outputs, LVCMOS33 in), SPI slave, FPGA_CLK;\n"
            "Bank0 = strobes (OSER10, pairs IOT16A/B and IOT17A/B), ADC_TRIG, COARSE (GCLKT_0), config, JTAG,\n"
            "DBG2 (pin 6, IOT9A/SCLK, to J501 pin 5).\n"
            "TAP pins may be swapped within Bank1 for routing (update this table).\n"
            "Unused: 8 (IOT10B/GCLKC_0), 32 (GCLKC_2).", (g(150), g(200)))
    sh.save()


if __name__ == "__main__":
    main()
