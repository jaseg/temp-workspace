#!/usr/bin/env python3
"""Floorplan of the scope-fe board: block membership from the netlist, footprint-area estimates
(courtyard boxes of the netlist footprints), and floorplan.png (to scale, matplotlib).

Run: python3 floorplan.py  -> floorplan.png, prints the block table and area estimates (FLOORPLAN.md quotes them).
"""
import os, re
import pcbnew
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Polygon
import boardlib as bl

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 100.0, 55.0                 # outline decision (FLOORPLAN.md): 100 x 55 mm
HOLES = [(3, 3), (W - 3, 3), (3, H - 3), (W - 3, H - 3)]
HOLE_KEEP = 3.5                    # MountingHole_3.2mm_M3 courtyard radius 3.45 mm
POWER = {"GND", "+3V3", "+5V", "-5V", "+2V5", "-2V5", "+1V2", "VBUS"}

# block rectangles (x, y, w, h) in board mm, origin top-left, +y down; rot = block rotation when merged
BLOCKS = {
    "analog":  dict(r=(0.0, 1.0, 56.0, 21.5), rot=0, col="#d9534f",
                    note="input 1xx + sampler 2xx + sampler strobe (U401/U402, pad, T401, D401, TL401)"),
    "fpga":    dict(r=(56.0, 0.5, 18.0, 22.0), rot=0, col="#5bc0de", note="GW1NZ, MS5351M, Y501, J501, 5xx"),
    "power":   dict(r=(74.0, 0.0, 26.0, 22.5), rot=0, col="#f0ad4e", note="USB-C, boost, LDOs, inverter 6xx (2-sided)"),
    "pstrobe": dict(r=(9.5, 26.0, 17.0, 23.0), rot=0, col="#9b59b6",
                    note="chain A above / K below, mirror about y = 37.5"),
    "phase":   dict(r=(0.0, 22.5, 99.5, 22.5), rot=0, col="#5cb85c",
                    note="minus the pstrobe rectangle (axis corridor y 34.5..40.5 stays phase)"),
    "mcuif":   dict(r=(27.0, 45.0, 66.5, 10.0), rot=0, col="#777777", note="J701 2x13 on the bottom edge, TP2272 x3"),
}
TAP_Y = 37.5                       # tap axis (PH_LINE), board y
TAP0_X = 27.0                      # tap 0 diode centre; tap 15 at 27 + 15 x 4.514 = 94.7
def membership(nl):
    """refs -> block: by sheet; strobe sheet split by connectivity from S_STROBE_P/N (sampler strobe)"""
    blk = {}
    for r, c in nl.comps.items():
        s = c["sheet"].strip("/")
        blk[r] = {"input": "analog", "sampler": "analog", "trigger_phase": "phase", "strobe": "pstrobe",
                  "fpga_clock": "fpga", "power": "power", "mcu_if": "mcuif"}[s]
    # BFS through 4xx parts over non-supply nets, starting at the sampler-strobe launch
    by_ref = {}
    for (r, p), n in nl.pads.items():
        by_ref.setdefault(r, set()).add(n)
    seen, todo = set(), ["/S_STROBE_P", "/S_STROBE_N", "/STRB_A", "/STRB_K"]
    while todo:
        n = todo.pop()
        if n in seen or n in POWER:
            continue
        seen.add(n)
        for r, p in nl.nets[n]:
            if nl.comps[r]["sheet"] == "/strobe/" and blk[r] == "pstrobe":
                blk[r] = "analog"
                todo += list(by_ref[r])
    # bias / decoupling parts of the sampler-strobe TRFs hang on supply nets: follow their private nets
    return blk


def fp_area(fpid, cache={}):
    """courtyard bounding box of the library footprint (parsed from the .kicad_mod text)"""
    if not fpid:
        return 0.0, (0, 0)
    if fpid not in cache:
        lib, name = fpid.split(":", 1)
        txt = open(os.path.join(bl.FPLIB, lib + ".pretty", name + ".kicad_mod")).read()
        xs, ys = [], []
        for m in re.finditer(r"\((?:fp_line|fp_rect|fp_poly|fp_circle)[^\n]*?(?:\n[^(]*?)*?", txt):
            pass
        for blk in re.split(r"\n\s*\((?=fp_|pad )", txt):
            if '"F.CrtYd"' in blk or ("F.CrtYd" in blk and "layer" in blk):
                for a, b in re.findall(r"\((?:start|end|xy|center) ([-\d.]+) ([-\d.]+)\)", blk):
                    xs.append(float(a)); ys.append(float(b))
        if not xs:
            for a, b in re.findall(r"\(at ([-\d.]+) ([-\d.]+)", txt):
                xs.append(float(a)); ys.append(float(b))
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        cache[fpid] = (w * h, (w, h))
    return cache[fpid]


def main():
    nl = bl.netlist()
    blk = membership(nl)
    print(f"{'block':8s} {'parts':>5s} {'courtyard mm2':>13s} {'x1.6 routing':>12s} {'rect mm2':>9s}  rect (x, y, w, h)")
    est = {}
    for b, d in BLOCKS.items():
        refs = [r for r in blk if blk[r] == b]
        a = sum(fp_area(nl.comps[r]["footprint"])[0] for r in refs)
        x, y, w, h = d["r"]
        est[b] = (len(refs), a)
        print(f"{b:8s} {len(refs):5d} {a:13.0f} {1.6 * a:12.0f} {w * h:9.0f}  {d['r']}")
    tot = sum(a for _, a in est.values())
    print(f"total courtyard {tot:.0f} mm2, x1.6 = {1.6 * tot:.0f} mm2; board 100 x 50 = 5000, 100 x 55 = 5500 mm2 "
          f"(minus 4 x {3.14159 * HOLE_KEEP ** 2:.0f} mm2 holes)")
    big = sorted(((fp_area(c["footprint"])[0], r) for r, c in nl.comps.items()), reverse=True)[:12]
    print("largest footprints:", ", ".join(f"{r} {a:.0f}" for a, r in big))
    print("analog strobe parts:", " ".join(sorted(r for r in blk if blk[r] == "analog" and nl.comps[r]["sheet"] == "/strobe/")))

    fig, ax = plt.subplots(figsize=(14, 8.4))
    ax.add_patch(Rectangle((0, 0), W, H, fill=False, lw=2, ec="k"))
    for hx, hy in HOLES:
        ax.add_patch(Circle((hx, hy), HOLE_KEEP, fc="#eeeeee", ec="k", lw=1, hatch="//"))
        ax.add_patch(Circle((hx, hy), 1.6, fc="white", ec="k"))
    for b, d in BLOCKS.items():
        x, y, w, h = d["r"]
        n, a = est[b]
        ax.add_patch(Rectangle((x, y), w, h, fc=d["col"], alpha=0.22, ec=d["col"], lw=1.8))
        ax.text(x + 0.8, y + 1.6, f"{b}  {w:g} x {h:g} mm  @({x:g}, {y:g})", fontsize=9, weight="bold", va="top")
        ax.text(x + 0.8, y + 3.6, f"{n} parts, courtyards {a:.0f} mm2", fontsize=7.5, va="top")
        ax.text(x + 0.8, y + 5.4, d["note"], fontsize=7, va="top", style="italic")
        ax.plot([x], [y], "k+", ms=8)        # block origin = top-left, rotation 0
    # sub-structures
    ax.add_patch(Rectangle((0.0, 4.0), 15.3, 17.6, fill=False, ec="#d9534f", ls="--"))
    ax.text(0.5, 21.2, "input 15.3 x 17.6", fontsize=6.5)
    ax.add_patch(Rectangle((14.8, 1.4), 30.8, 19.3, fill=False, ec="#d9534f", ls="--"))
    ax.text(30, 21.2, "sampler 30.8 x 19.3", fontsize=6.5)
    ax.add_patch(Rectangle((46.0, 6.5), 9.5, 7.0, fill=False, ec="#d9534f", ls=":"))
    ax.text(46.2, 15.0, "U401 + 12 dB pad", fontsize=6.5)
    ax.plot([TAP0_X, TAP0_X + 15 * 4.514], [TAP_Y, TAP_Y], color="#2e7d32", lw=3)
    ax.plot([TAP0_X - 3, TAP0_X + 15 * 4.514 + 3], [TAP_Y - 4.4] * 2, color="#9b59b6", lw=1)
    ax.plot([TAP0_X - 3, TAP0_X + 15 * 4.514 + 3], [TAP_Y + 4.4] * 2, color="#9b59b6", lw=1)
    ax.text(40, TAP_Y + 1.6, "PH_LINE: 16 taps x 4.514 mm (tap 0 x 27.0, tap 15 x 94.7), 50 R ends x 96-98", fontsize=7)
    ax.add_patch(Rectangle((TAP0_X - 2, 22.8), 72.5, 6.4, fill=False, ec="#2e7d32", ls=":"))
    ax.text(TAP0_X, 28.6, "8 x COS3502 + VTH rail (behind PSTRB_A), TAP0..15 leave north", fontsize=6.5)
    ax.add_patch(Rectangle((0.5, TAP_Y - 3.0), 26.0, 6.0, fill=False, ec="#2e7d32", ls="--"))
    ax.text(5.0, TAP_Y - 3.4, "front chain on axis: J102 > U301 > U302 > U303 + bias tee > pad > tap 0", fontsize=5.6)
    ax.text(0.8, 31.5, "U304,\nTLV sup.", fontsize=5.6)
    ax.add_patch(Rectangle((9.5, 26.5), 17.0, 8.0, fill=False, ec="#9b59b6", ls="--"))
    ax.add_patch(Rectangle((9.5, 40.5), 17.0, 8.0, fill=False, ec="#9b59b6", ls="--"))
    ax.text(10, 31.0, "chain A: TRF>10dB>GVA>stub", fontsize=5.8)
    ax.text(10, 46.0, "chain K (mirror)", fontsize=5.8)
    ax.add_patch(Rectangle((52.0, 49.9), 33.0, 5.1, fill=False, ec="k", lw=1.2))
    ax.text(53, 52.8, "J701 2x13, pins along the bottom edge", fontsize=7)
    for (x, y, lab) in ((0, 12.85, "J101 SIG_IN"), (0, TAP_Y, "J102 EXT_CLK")):
        ax.add_patch(Rectangle((x - 1.5, y - 2.5), 4.5, 5, fc="gold", ec="k"))
        ax.text(x + 3.2, y + 0.6, lab, fontsize=7, weight="bold")
    ax.add_patch(Rectangle((W - 7.5, 9.0), 8.5, 9.0, fc="gold", ec="k"))
    ax.text(W - 15.5, 19.5, "J601 USB-C, right edge", fontsize=7, weight="bold")
    links = [
        ([(15.3, 16.6), (7.0, 24.9), (7.0, TAP_Y - 1.0)], "BUF_OUT_T 50R", "rf"),
        ([(56.0, 10.0), (54.5, 10.0)], "", "pair"),
        ([(56.5, 21.5), (50.0, 23.5), (30.0, 23.5), (24.0, 26.5)], "PH_STROBE_P/N", "pair"),
        ([(26.5, TAP_Y - 4.4), (TAP0_X, TAP_Y - 4.4)], "", "rf"),
        ([(26.5, TAP_Y + 4.4), (TAP0_X, TAP_Y + 4.4)], "", "rf"),
        ([(64.0, 22.5), (64.0, 25.0)], "TAP0..15", "slow"),
        ([(54.0, 22.0), (54.0, 25.0)], "COARSE", "slow"),
        ([(74.0, 8.0), (72.0, 8.0)], "+3V3/+1V2", "supply"),
        ([(80.0, 45.0), (80.0, 22.5)], "SPI/I2C/ADC_TRIG/MCU_CLK (B.Cu)", "slow"),
        ([(34.0, 45.0), (34.0, 22.0)], "VBIAS_A/K, VOFS, ADC_IN, ADC_REF_MID (B.Cu)", "slow"),
        ([(28.0, 45.0), (20.0, 40.5), (8.0, 40.5)], "TRIG_LEVEL (B.Cu)", "slow"),
        ([(45.0, 45.0), (45.0, 42.0)], "VTAP_TH", "slow"),
    ]
    sty = {"rf": dict(color="red", lw=2.2), "pair": dict(color="blue", lw=1.8, ls="--"),
           "slow": dict(color="k", lw=1.0, ls=":"), "supply": dict(color="#e67e22", lw=3, alpha=0.6)}
    for pts, lab, s_ in links:
        xs, ys = zip(*pts)
        ax.plot(xs, ys, **sty[s_])
        if lab:
            ax.text(xs[-1] + 0.4, ys[-1] - 0.4, lab, fontsize=6.3, color=sty[s_]["color"])
    ax.text(57, 3.5, "S_STROBE_P/N: FPGA W side", fontsize=5.5, color="blue")
    ax.text(0, H + 2.6, "In1: solid GND (cut only under SMA pins / hold nodes).  In2 regions: analog: +5V/-5V (input), +-2V5 (sampler), "
            "+3V3 (TRFs); fpga: +3V3 with +1V2 island; power: VBUS / +5V4F; pstrobe: +3V3 + VBUS (GVA chokes);", fontsize=6.3)
    ax.text(0, H + 4.0, "phase: +3V3 (TRF, LVDS2, COS3502), +2V5 / -2V5 islands (TLV), VTAP_P / VTAP_N strips under the taps; "
            "mcuif: +2V5/-2V5. Slow inter-block signals on B.Cu.", fontsize=6.3)
    ax.set_xlim(-4, W + 4)
    ax.set_ylim(H + 5, -3)
    ax.set_aspect("equal")
    ax.set_xticks(range(0, 101, 10))
    ax.set_yticks(range(0, 56, 5))
    ax.grid(alpha=0.25)
    ax.set_title("scope-fe board floorplan, 100 x 55 mm, origin top-left, +y down, all blocks rotation 0 (top view)")
    fig.tight_layout()
    out = os.path.join(HERE, "floorplan.png")
    fig.savefig(out, dpi=130)
    print("wrote", out)


if __name__ == "__main__":
    main()
