"""AC analysis of every bias tee (ngspice): branch impedance, S21/S11 of a 50 R through line with the branch
attached at its middle, and the transfer of a stub-loaded output stage (TRF #2 / GVA-84+ drive a shorted
80 ps stub through 100 nF). 100 kHz - 8 GHz. Writes ac.json and plot_branch.png, plot_line.png.
  python3 ac.py
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from multiprocessing import Pool

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import tees  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PS_MM = 6.057


def ladder(a, b, td, z0=50.0, sec=2e-12, tag="t"):
    n = max(1, int(np.ceil(td / sec)))
    l, c = td * z0 / n, td / z0 / n
    out, prev = [], a
    for k in range(n):
        nxt = b if k == n - 1 else f"{tag}{k}"
        out += [f"C{tag}{k} {prev} 0 {c / 2 if k == 0 else c:.5g}", f"L{tag}{k} {prev} {nxt} {l:.5g}"]
        prev = nxt
    out.append(f"C{tag}e {b} 0 {c / 2:.5g}")
    return out


def run(text, vecs):
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "o.txt")
        deck = text + f".control\nset wr_singlescale\nrun\nwrdata {out} {' '.join(vecs)}\n.endc\n.end\n"
        open(os.path.join(td, "d.cir"), "w").write(deck)
        r = subprocess.run(["ngspice", "-b", os.path.join(td, "d.cir")], capture_output=True, text=True, timeout=600)
        if not os.path.exists(out):
            raise RuntimeError(r.stdout[-2000:] + r.stderr[-1000:])
        a = np.loadtxt(out)
    f = a[:, 0]
    return f, [a[:, 1 + 2 * i] + 1j * a[:, 2 + 2 * i] for i in range(len(vecs))]


AC = ".ac dec 150 100k 8g\n"


def case(args):
    kind, d = args
    lib = tees.lib(d)
    # branch impedance
    f, (z,) = run(f"* Z\n{lib}Xt tap 0 TEE_{kind}\nI1 0 tap dc 0 ac 1\n{AC}", ["v(tap)"])
    # through line: 3 mm of 50 R each side of the tap
    L = [f"* line\n{lib}Vs s 0 dc 0 ac 2", "Rs s a 50"] + ladder("a", "tap", 3 * PS_MM * 1e-12, tag="ta") + \
        ladder("tap", "b", 3 * PS_MM * 1e-12, tag="tb") + ["Rl b 0 50", f"Xt tap 0 TEE_{kind}"]
    f, (va, vb) = run("\n".join(L) + "\n" + AC, ["v(a)", "v(b)"])
    # stub-loaded stage: 50 R source -> tap (branch) -> 100 nF -> launch (80 ps shorted stub + 50 R line)
    S = [f"* stub\n{lib}Vs s 0 dc 0 ac 2", "Rs s tap 50", f"Xt tap 0 TEE_{kind}", "Xc tap l C100N"] + \
        ladder("l", "se", 80e-12, tag="st") + ["Rse se 0 1m", "Rl l 0 50"]
    f, (vl,) = run("\n".join(S) + "\n" + AC, ["v(l)"])
    return kind, d, f, z, vb, va - 1, vl


def main():
    jobs = [(k, 1.0) for k in tees.KINDS] + [(k, 0.85) for k in ("present_sampler", "corr_trf")] + \
           [(k, 0.65) for k in ("present_gva", "corr_gva")]
    with Pool(2) as p:
        res = p.map(case, jobs)
    R = {(k, d): (f, z, s21, s11, vl) for k, d, f, z, s21, s11, vl in res}
    f = res[0][2]
    vl0 = R[("ideal", 1.0)][4]
    summ = {}
    for (k, d), (f, z, s21, s11, vl) in R.items():
        if k == "ideal":
            continue
        db = 20 * np.log10(np.abs(s21))
        h = 20 * np.log10(np.abs(vl / vl0))
        def worst(arr, lo, hi):
            msk = (f >= lo) & (f <= hi)
            i = np.argmin(arr[msk])
            return [round(float(arr[msk][i]), 3), round(float(f[msk][i] / 1e6), 1)]
        zz = np.abs(z)
        summ[f"{k}|d={d}"] = dict(
            label=tees.LABEL[k],
            S21_worst_1M_3G=worst(db, 1e6, 3e9), S21_worst_3G_6G=worst(db, 3e9, 6e9),
            S21_worst_100k_1M=worst(db, 1e5, 1e6),
            S11_worst_dB_1M_6G=round(float(20 * np.log10(np.abs(s11[(f > 1e6) & (f < 6e9)]).max())), 1),
            Zmin_1M_6G=[round(float(zz[(f > 1e6) & (f < 6e9)].min()), 1),
                        round(float(f[(f > 1e6) & (f < 6e9)][np.argmin(zz[(f > 1e6) & (f < 6e9)])] / 1e6), 1)],
            Z_at={str(fq): round(float(np.interp(fq, f, zz)), 0) for fq in (1e5, 1e6, 3.125e6, 50e6, 300e6, 1e9, 3e9, 5e9)},
            stub_stage_worst_100M_6G=worst(h, 1e8, 6e9))
    json.dump(summ, open(os.path.join(HERE, "ac.json"), "w"), indent=1)
    for k, v in summ.items():
        print(k, v["S21_worst_1M_3G"], v["S21_worst_3G_6G"], "Zmin", v["Zmin_1M_6G"], "stub", v["stub_stage_worst_100M_6G"])

    plt.rcParams.update({"font.size": 11})
    sty = {"present_sampler": ("C3", "-"), "present_line": ("C1", "-"), "present_gva": ("C4", "-"),
           "corr_trf": ("C0", "-"), "corr_trf_noR": ("C0", ":"), "corr_gva": ("C2", "-")}
    fig, ax = plt.subplots(1, 2, figsize=(14, 5.6))
    for k, (c, ls) in sty.items():
        f, z, *_ = R[(k, 1.0)]
        ax[0].loglog(f, np.abs(z), ls, color=c, lw=1.6, label=tees.LABEL[k])
    f, z, *_ = R[("corr_trf", 0.85)]
    ax[0].loglog(f, np.abs(z), "--", color="C0", lw=1, label="corrected TRF, bead derated x0.85 (55 mA)")
    for y, t in ((700, "700 R: 0.3 dB if resistive"), (93, "93 R: 0.3 dB if reactive")):
        ax[0].axhline(y, color="0.5", lw=0.8, ls="--")
        ax[0].text(1.3e5, y * 1.08, t, color="0.35", fontsize=9)
    ax[0].axvspan(3e9, 8e9, color="0.92")
    ax[0].text(3.3e9, 1.3e5, "bead model\nextrapolated", fontsize=8, color="0.4")
    ax[0].set(xlim=(1e5, 8e9), ylim=(5, 3e5), xlabel="Hz", ylabel="|Z| of the bias branch, ohm",
              title="Bias-branch impedance at the line node (incl. layout parasitics)")
    ax[0].legend(fontsize=8, loc="upper left"); ax[0].grid(alpha=0.3, which="both")
    for k, (c, ls) in sty.items():
        f, z, s21, s11, vl = R[(k, 1.0)]
        ax[1].semilogx(f, 20 * np.log10(np.abs(s21)), ls, color=c, lw=1.6, label=tees.LABEL[k])
    ax[1].axhline(-0.3, color="0.5", lw=0.8, ls="--")
    ax[1].set(xlim=(1e5, 8e9), ylim=(-12, 0.5), xlabel="Hz", ylabel="S21 of the 50 R line with the branch, dB",
              title="Through-line loss (50 R both ends)")
    ins = ax[1].inset_axes([0.08, 0.08, 0.55, 0.42])
    for k, (c, ls) in sty.items():
        f, z, s21, s11, vl = R[(k, 1.0)]
        ins.semilogx(f, 20 * np.log10(np.abs(s21)), ls, color=c, lw=1.3)
    ins.axhline(-0.3, color="0.5", lw=0.8, ls="--")
    ins.set(xlim=(1e5, 8e9), ylim=(-1.2, 0.05)); ins.grid(alpha=0.3); ins.tick_params(labelsize=8)
    ax[1].legend(fontsize=8, loc="lower right"); ax[1].grid(alpha=0.3, which="both")
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "plot_branch.png"), dpi=100)
    return summ


if __name__ == "__main__":
    main()
