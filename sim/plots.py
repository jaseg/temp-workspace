"""Figures and the summary table from ../results/*.json."""
from __future__ import annotations

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
# fixed colour per case, in this order everywhere
CASES = {
    "redriver-linear": ("Redriver, linear", "#2a78d6"),
    "redriver-limiting": ("Redriver, limiting", "#eb6834"),
    "direct-1v2": ("No redriver, VCCIO 1.2 V", "#1baf7a"),
    "direct-3v3": ("No redriver, VCCIO 3.3 V", "#eda100"),
}

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10, "axes.titlesize": 11,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "lines.linewidth": 2,
    "legend.frameon": False, "font.family": "DejaVu Sans",
})


def load(name: str):
    with open(os.path.join(RES, name)) as fh:
        return json.load(fh)


def legend(ax) -> None:
    ax.legend(loc="best", labelcolor=INK2, fontsize=9)


def fig_waves() -> None:
    waves = [s for s in load("waves.json") if abs(s["fpga_tr"] - 300e-12) < 1e-15]
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    for s in waves:
        label, col = CASES[s["case"]]
        t = np.array(s["wave"]["t"]) * 1e9
        axs[0].plot(t, s["wave"]["strobe"], color=col, label=label)
        axs[1].plot(t, s["wave"]["stim_tdr"], color=col, label=label)
    axs[0].set_title("Strobe pulse between the clip-line nodes (bridges off)")
    axs[0].set_xlabel("time after the edge at the FPGA pin (ns)")
    axs[0].set_ylabel("V(anode rail) − V(cathode rail), change from idle (V)")
    axs[0].set_xlim(-0.2, 2.5)
    axs[1].set_title("Stimulus edge at the TDR port (TDR_1P − TDR_1N), 50 Ω load")
    axs[1].set_xlabel("time after the edge at the FPGA pin (ns)")
    axs[1].set_ylabel("differential voltage (V)")
    axs[1].set_xlim(-0.2, 2.5)
    legend(axs[0])
    legend(axs[1])
    fig.suptitle("FPGA edge 300 ps (20–80 %)", x=0.01, ha="left", fontsize=9, color=INK2)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "waveforms.png"), dpi=160)


def fig_aperture() -> None:
    ap = load("aperture.json")
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    for r in ap:
        if abs(r["fpga_tr"] - 300e-12) > 1e-15 or abs(r["overdrive"] - 0.65) > 1e-9:
            continue
        label, col = CASES[r["case"]]
        x, v = np.array(r["x"]) * 1e9, np.array(r["v"])
        lo, hi = v[:3].mean(), v[-3:].mean()
        axs[0].plot(x, (v - lo) / (hi - lo), color=col, label=f"{label}: {r['tr_10_90'] * 1e12:.0f} ps")
    axs[0].set_title("Sampler alone: recorded shape of an ideal step")
    axs[0].set_xlabel("strobe time − step time (ns)")
    axs[0].set_ylabel("held voltage, normalised")
    axs[0].set_xlim(-1.2, 1.2)
    axs[0].legend(loc="center left", bbox_to_anchor=(0.0, 0.62), labelcolor=INK2, fontsize=9, title="10–90 % rise time", title_fontsize=9)

    trs = sorted({r["fpga_tr"] for r in ap})
    for name, (label, col) in CASES.items():
        ys = [next(r["tr_10_90"] for r in ap if r["case"] == name and r["fpga_tr"] == tr and abs(r["overdrive"] - 0.65) < 1e-9) * 1e12 for tr in trs]
        axs[1].plot([t * 1e12 for t in trs], ys, color=col, marker="o", markersize=6, label=label)
        axs[1].annotate(f"{ys[-1]:.0f}", (trs[-1] * 1e12, ys[-1]), xytext=(6, 0), textcoords="offset points", va="center", color=INK2, fontsize=9)
    axs[1].set_title("Sampler rise time against FPGA edge rate")
    axs[1].set_xlabel("FPGA output edge, 20–80 % (ps)")
    axs[1].set_ylabel("sampler 10–90 % rise time (ps)")
    axs[1].set_ylim(0, None)
    axs[1].set_xticks([t * 1e12 for t in trs])
    legend(axs[1])
    fig.suptitle("Strobe overdrive 0.65 V; left: FPGA edge 300 ps", x=0.01, ha="left", fontsize=9, color=INK2)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "sampler-step-response.png"), dpi=160)


def fig_system() -> None:
    sy = load("system.json")
    fig, ax = plt.subplots(figsize=(11, 4.4))
    for r in sy:
        if r["case"] == "direct-3v3":
            continue    # the two-shot steady-state solve does not hold there, see README
        label, col = CASES[r["case"]]
        x, v = np.array(r["x"]) * 1e9, np.array(r["v"])
        ax.plot(x, v, color=col, label=label)
    ax.set_title("Recorded TDR trace: open 1 ns line on the TDR port")
    ax.set_xlabel("strobe time − stimulus edge at the FPGA pin (ns)")
    ax.set_ylabel("held voltage, SPL_LS_1P − SPL_LS_1N (V)")
    legend(ax)
    fig.suptitle("FPGA edge 300 ps (20–80 %), strobe overdrive 0.65 V", x=0.01, ha="left", fontsize=9, color=INK2)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "tdr-trace.png"), dpi=160)


def fig_system_optimum() -> None:
    base = next(r for r in load("system.json") if r["case"] == "redriver-linear")
    opt = load("system-optimum.json")
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.plot(np.array(base["x"]) * 1e9, base["v"], color="#52514e", label="As drawn: VCCIO 1.2 V, strobe through U2 (linear), bias −0.13 V")
    for r, col in zip(opt, ("#2a78d6", "#eb6834")):
        ax.plot(np.array(r["x"]) * 1e9, r["v"], color=col, label="Optimised, " + r["case"].split(", ")[1])
    ax.set_title("Recorded TDR trace at the optimised operating point: open 1 ns line on the TDR port")
    ax.set_xlabel("strobe time − stimulus edge at the FPGA pin (ns)")
    ax.set_ylabel("held voltage, SPL_LS_1P − SPL_LS_1N (V)")
    legend(ax)
    fig.suptitle("Optimised: VCCIO 3.3 V, strobe bypassing U2, R78/R79 220 Ω, bias +0.45 V per rail. FPGA edge 300 ps.", x=0.01, ha="left", fontsize=9, color=INK2)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "tdr-trace-optimum.png"), dpi=160)


OPT = {  # strobe options of the optimisation: U2 in two hues, bypass as one hue stepped by VCCIO
    "U2 limiting": "#eb6834", "U2 linear": "#1baf7a",
    "bypass, VCCIO 1.2 V": "#a9c9ef", "bypass, VCCIO 1.8 V": "#6fa5e3", "bypass, VCCIO 2.5 V": "#2a78d6", "bypass, VCCIO 3.3 V": "#174a8a",
}


def fig_optimize() -> None:
    """Rise time against sampling efficiency; each point is one bias setting."""
    R = [r for r in load("optimize.json") if r["usable"] and r["overshoot"] < 0.5]
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.4), sharey=True)
    for ax, tr in zip(axs, (150e-12, 300e-12, 600e-12)):
        for name, col in OPT.items():
            pts = sorted((r for r in R if r["strobe"] == name and abs(r["fpga_tr"] - tr) < 1e-15), key=lambda r: r["vbias"])
            if not pts:
                continue
            ax.plot([r["eff"] * 100 for r in pts], [r["tr_10_90"] * 1e12 for r in pts], color=col, marker="o", markersize=6,
                    label=name.replace("bypass, ", "Bypass, ").replace("U2", "Through U2,"))
            if name in ("bypass, VCCIO 3.3 V", "U2 limiting"):
                for r in pts:
                    ax.annotate(f"{r['vbias']:+.2f}", (r["eff"] * 100, r["tr_10_90"] * 1e12), xytext=(5, 4),
                                textcoords="offset points", fontsize=8, color=INK2)
        ax.set_title(f"FPGA edge {tr * 1e12:.0f} ps")
        ax.set_xlabel("sampling efficiency per strobe (%)")
        ax.set_ylim(0, 700)
        ax.set_xlim(0, 90)
    axs[0].set_ylabel("sampler 10–90 % rise time (ps)")
    legend(axs[1])
    fig.suptitle("Strobe path and VCCIO1; each point is one bias setting (numbers: bias per rail in V, shown for two of the lines). "
                 "Points with more than 50 % overshoot left out.", x=0.01, ha="left", fontsize=9, color=INK2)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "optimize.png"), dpi=160)


def table_optimize() -> str:
    R = load("optimize.json")
    rows = ["| Strobe path | FPGA edge | Bias per rail | Sampler 10–90 % | Gain | Efficiency | Overshoot |", "|---|---|---|---|---|---|---|"]
    for r in R:
        if r["usable"]:
            rows.append(f"| {r['strobe']} | {r['fpga_tr'] * 1e12:.0f} ps | {r['vbias']:+.2f} V | {r['tr_10_90'] * 1e12:.0f} ps | "
                        f"{r['gain']:.2f} | {r['eff'] * 100:.0f} % | {r['overshoot'] * 100:.0f} % |")
    return "\n".join(rows) + "\n"


def edges(x: np.ndarray, v: np.ndarray, a: float, b: float) -> float:
    """10-90 % time of the edge of v between x = a and x = b."""
    import wave as w
    m = (x >= a) & (x <= b)
    x, v = x[m], v[m]
    n = (v - v[:3].mean()) / (v[-3:].mean() - v[:3].mean())
    return w.crossing(x, n, 0.9) - w.crossing(x, n, 0.1)


def table() -> str:
    waves, ap, sy = load("waves.json"), load("aperture.json"), load("system.json")
    rows = ["| Case | FPGA edge 20–80 % | Strobe pulse peak / FWHM | Stimulus 10–90 % at TDR port | Bias VBIAS_K − VBIAS_A | Sampler 10–90 % | Sampler bandwidth (0.35/tr) | Sampler gain | Efficiency per strobe |",
            "|---|---|---|---|---|---|---|---|---|"]
    for name, (label, _) in CASES.items():
        for tr in sorted({s["fpga_tr"] for s in waves}):
            s = next(q for q in waves if q["case"] == name and q["fpga_tr"] == tr)
            r = next(q for q in ap if q["case"] == name and q["fpga_tr"] == tr and abs(q["overdrive"] - 0.65) < 1e-9)
            rows.append(f"| {label} | {tr * 1e12:.0f} ps | {s['strobe_peak']:.2f} V / {s['strobe_fwhm'] * 1e12:.0f} ps | "
                        f"{s['stim_tdr_port_tr'] * 1e12:.0f} ps | {2 * r['vbias']:+.2f} V | {r['tr_10_90'] * 1e12:.0f} ps | "
                        f"{0.35 / r['tr_10_90'] / 1e9:.1f} GHz | {r['gain']:.2f} | {r['eff_plateau'] * 100:.0f} % |")
    rows += ["", "| Case (FPGA edge 300 ps) | Overdrive | Bias VBIAS_K − VBIAS_A | Sampler 10–90 % | Sampler gain | Efficiency per strobe |", "|---|---|---|---|---|---|"]
    for name, (label, _) in CASES.items():
        for r in ap:
            if r["case"] == name and abs(r["fpga_tr"] - 300e-12) < 1e-15:
                rows.append(f"| {label} | {r['overdrive']:.2f} V | {2 * r['vbias']:+.2f} V | {r['tr_10_90'] * 1e12:.0f} ps | {r['gain']:.2f} | {r['eff_plateau'] * 100:.0f} % |")
    rows += ["", "| Case (FPGA edge 300 ps, overdrive 0.65 V) | Incident edge 10–90 % as recorded | Reflected edge 10–90 % as recorded |", "|---|---|---|"]
    for r in sy:
        if r["case"] == "direct-3v3":
            continue
        x, v = np.array(r["x"]), np.array(r["v"])
        rows.append(f"| {CASES[r['case']][0]} | {edges(x, v, 0.0, 1.3e-9) * 1e12:.0f} ps | {edges(x, v, 2.2e-9, 3.5e-9) * 1e12:.0f} ps |")
    return "\n".join(rows) + "\n"


if __name__ == "__main__":
    fig_waves()
    fig_aperture()
    fig_system()
    fig_optimize()
    fig_system_optimum()
    with open(os.path.join(RES, "optimize.md"), "w") as fh:
        fh.write(table_optimize())
    t = table()
    with open(os.path.join(RES, "summary.md"), "w") as fh:
        fh.write(t)
    print(t)
