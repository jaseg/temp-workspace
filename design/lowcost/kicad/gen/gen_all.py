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
        "TAP0": {("U501", "9")}, "TAP15": {("U501", "27")}, "COARSE": {("U501", "47")},
        "FPGA_CLK": {("U501", "33"), ("R508", "2")},
        "I2C_SCL": {("U502", "4"), ("J701", "20")}, "I2C_SDA": {("U502", "5"), ("J701", "21")},
        "FPGA_RECONFIG": {("U501", "48"), ("J701", "19")}, "FPGA_DONE": {("U501", "46"), ("J701", "18")},
        "SPI_MISO": {("U501", "30"), ("J701", "24")}, "ADC_TRIG": {("U501", "41"), ("J701", "13")},
        "MCU_CLK": {("J701", "14")}, "+3V3": {("U501", "36"), ("U501", "1"), ("U501", "25")},
        "+1V2": {("U501", "12"), ("U501", "37")}, "GND": {("U501", "2"), ("U501", "26"), ("U501", "49")},
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
    for net, m in {"VBIAS_A": {("U702", "7"), ("R717", "2"), ("R205", "1")},
                   "VBIAS_K": {("U703", "1"), ("R722", "2"), ("R206", "2")},
                   "STRB_A": {("T401", "2"), ("C201", "1")}, "STRB_K": {("T401", "4"), ("C202", "1")},
                   "BUF_OUT_S": {("U101", "11"), ("R201", "1")}, "BUF_OUT_T": {("R113", "2"), ("U301", "1")},
                   "EXT_CLK": {("J102", "1"), ("U301", "3")}, "TRIG_LEVEL": {("U701", "7"), ("U302", "4")},
                   "TERM_50": {("Q701", "3"), ("K101", "12")}, "VOFS": {("U702", "1"), ("R119", "1")},
                   "ADC_IN": {("R211", "2"), ("J701", "3")}, "ADC_REF_MID": {("R703", "2"), ("U202", "3")}}.items():
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
    sys.exit(1 if bad else 0)
