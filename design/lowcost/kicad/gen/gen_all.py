"""Regenerate the whole scope-fe project, check the netlist, export PDF + per-sheet SVG/PNG.
Usage: python3 gen_all.py [--no-export]"""
import glob, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import schlib
from common import SHEETS, CRITICAL

OUT = schlib.OUTDIR
EXP = os.path.join(OUT, "export")


def run_generators():
    import gen_placeholders
    subprocess.run([sys.executable, os.path.join(HERE, "gen_footprints.py")], check=True)   # lib/scope-fe.pretty
    for n in CRITICAL:
        own = os.path.join(HERE, f"gen_{n}.py")
        if os.path.exists(own):
            subprocess.run([sys.executable, own], check=True)
        else:
            gen_placeholders.make(n)
    for n in ("fpga_clock", "power", "mcu_if", "root"):
        subprocess.run([sys.executable, os.path.join(HERE, f"gen_{n}.py")], check=True)
    # custom symbols are embedded in each sheet; also collect them into the project library
    # (the generators run as subprocesses: collect their embedded "scope-fe:" symbols from the sheet files)
    for n in SHEETS:
        tree = schlib.parse_sexpr(open(os.path.join(OUT, n + ".kicad_sch"), encoding="utf-8").read())
        for sym in schlib.find(schlib.find(tree, "lib_symbols")[0], "symbol"):
            if str(sym[1]).startswith(schlib.PROJECT + ":"):
                schlib.CUSTOM.setdefault(str(sym[1]), sym)
    schlib.write_custom_lib(os.path.join(OUT, "scope-fe.kicad_sym"))
    schlib.write_project(OUT, list(SHEETS))


def check(n):
    members = {
        "TAP0": {("U501", "28")}, "TAP9": {("U501", "9")}, "TAP8": {("U501", "10")}, "TAP15": {("U501", "11")}, "TAP10": {("U501", "17")},
        "PH_STROBE_P": {("U501", "39"), ("R407", "1")}, "PH_STROBE_N": {("U501", "40"), ("R411", "1")}, "COARSE": {("U501", "27")},
        "FPGA_CLK": {("U501", "33"), ("R508", "2")},
        # STM32G474CBT6 U704 (mcu_if), pin numbers LQFP-48
        "I2C_SCL": {("U502", "4"), ("U704", "39")}, "I2C_SDA": {("U502", "5"), ("U704", "44")},
        "FPGA_RECONFIG": {("U501", "48"), ("U704", "27")}, "FPGA_DONE": {("U501", "46"), ("U704", "43")},
        "SPI_MISO": {("U501", "21"), ("U704", "41")}, "SPI_SCK": {("U501", "20"), ("U704", "40")},
        "SPI_MOSI": {("U501", "22"), ("U704", "42")}, "SPI_CS": {("U501", "24"), ("U704", "46")},
        "ADC_TRIG": {("U501", "18"), ("U704", "25")}, "MCU_CLK": {("R509", "2"), ("U704", "5")},
        "TRIG_SEL": {("U704", "9"), ("R302", "1")},
        # control voltages (21 Nov 2026: passive networks, U701 TLV9001 makes VNEG_REF)
        "DAC_TRIG": {("U704", "12"), ("R383", "2")}, "VOFS": {("U704", "13"), ("R119", "1")},
        "DAC_TAPTH": {("U704", "10"), ("R723", "1")}, "DAC_BIAS_A": {("U704", "14"), ("R733", "1")},
        "DAC_BIAS_K": {("U704", "17"), ("R735", "1"), ("R736", "1")},
        "VREFP": {("U704", "20"), ("R731", "1"), ("R703", "1")},
        "VNEG_REF": {("U701", "1"), ("R732", "2"), ("C722", "2"), ("R123", "1")},
        "TRIG_LEVEL": {("R383", "1"), ("R384", "1"), ("R385", "1"), ("U302", "4")},
        # programming header J501 (yanartas sensing board J3 pinout) <-> U704
        "UC_SWDIO": {("J501", "8"), ("U704", "37")}, "UC_SWCLK": {("J501", "10"), ("U704", "38")},
        "UC_NRST": {("J501", "14"), ("U704", "7"), ("C719", "1")}, "DBG1": {("J501", "12"), ("U704", "6")},
        "HOST_RX": {("R511", "2"), ("U704", "32")}, "HOST_TX": {("R512", "2"), ("U704", "31")},
        "USB_DP": {("J601", "A6"), ("J601", "B6"), ("U608", "1"), ("U608", "6"), ("U704", "34")},
        "USB_DM": {("J601", "A7"), ("J601", "B7"), ("U608", "3"), ("U608", "4"), ("U704", "33")},
        "VBUS": {("J501", "1")}, "JTAG_TCK": {("J501", "7"), ("U501", "3"), ("R507", "1")},
        "JTAG_TMS": {("J501", "9"), ("U501", "4")}, "JTAG_TDI": {("J501", "11"), ("U501", "5")},
        "JTAG_TDO": {("J501", "13"), ("U501", "7")}, "DBG2": {("J501", "5"), ("U501", "8")}, "+3V3": {("U501", "36"), ("U501", "1"), ("U501", "25")},
        "+1V2": {("U501", "12"), ("U501", "37")}, "GND": {("U501", "2"), ("U501", "26"), ("U501", "49"),
                                                    ("J501", "6"), ("J501", "15"), ("J501", "16"),
                                                    ("U704", "19"), ("U704", "23")},
    }
    bad = 0
    for net, m in members.items():
        try:
            schlib.assert_net(n, net, m)
        except AssertionError as e:
            bad += 1
            print("NET CHECK FAILED:", e)
    # two-pin parts with both pins on one net (a wire drawn through the body after split_wires)
    pins = {}
    for k, v in n.items():
        for r, p in v:
            pins.setdefault(r, {})[p] = k
    for r, d in sorted(pins.items()):
        if len(d) == 2 and len(set(d.values())) == 1:
            bad += 1
            print("SHORTED two-pin part:", r, d)
    for net, m in {"VBIAS_A": {("R733", "2"), ("R734", "1"), ("R205", "1")},
                   "VBIAS_K": {("R735", "2"), ("R206", "2")},
                   "STRB_A": {("T401", "2"), ("C201", "1")}, "STRB_K": {("T401", "4"), ("C202", "1")},
                   "BUF_OUT_S": {("U101", "11"), ("R201", "1")}, "BUF_OUT_T": {("R113", "2"), ("U301", "1")},
                   "EXT_CLK": {("J102", "1"), ("U301", "3")},
                   "ADC_IN": {("R211", "2"), ("U704", "8")}, "ADC_REF_MID": {("R703", "2"), ("U202", "3")}}.items():
        try:
            schlib.assert_net(n, net, m)
        except AssertionError as e:
            bad += 1
            print("NET CHECK FAILED:", e)
    singles = sorted(k for k, v in n.items() if len(v) == 1 and not k.startswith("unconnected"))
    nc = sorted(k for k in n if k.startswith("unconnected"))
    print(f"netlist: {len(n)} nets, {bad} failed checks; single-node nets: {len(singles)}; "
          f"unconnected (NC-flagged) pins: {len(nc)}")
    for s in singles:
        print("   single:", s, sorted(n[s]))
    for s in nc:
        print("   nc:", s)
    return bad


def export():
    os.makedirs(EXP, exist_ok=True)
    root = os.path.join(OUT, "scope-fe.kicad_sch")
    schlib.export_pdf(root, os.path.join(EXP, "scope-fe.pdf"))
    tmp = os.path.join(EXP, "svg")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    schlib.export_svg(root, tmp)
    svgs = sorted(glob.glob(os.path.join(tmp, "*.svg")))
    subprocess.run(["node", os.path.join(HERE, "svg2png.js"), EXP] + svgs, check=True, cwd=HERE)
    for f in svgs:
        shutil.move(f, os.path.join(EXP, os.path.basename(f)))
    os.rmdir(tmp)


if __name__ == "__main__":
    run_generators()
    n = schlib.nets(os.path.join(OUT, "scope-fe.kicad_sch"), os.path.join(EXP if os.path.isdir(EXP) else OUT, "scope-fe.net"))
    bad = check(n)
    if "--no-export" not in sys.argv:
        export()
    if os.path.isdir(EXP):
        import gen_bom
        gen_bom.main()                     # docs/bom.csv, docs/bom.md
    sys.exit(1 if bad else 0)
