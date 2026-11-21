"""Time-domain effect of the bias tees on the real waveforms (ngspice transient, KLU).

(1) Sampler strobe chain, 2x TRF37D73 (sim/strobe/chain.py stage model, nominal split), S_STROBE 3.125 MHz 50 %
    duty, 100 nF couplings, 12 dB pad, every TRF output with its bias tee subcircuit (tees.py) to AC ground;
    load (a) 50 R (as sim/strobe/extras.py) and (b) the real clip node: 100 nF -> 80 ps shorted stub + 50 R.
(2) Phase strobe chain TRF37D73 + 10 dB pad + GVA-84+, PH_STROBE 50 MHz, into the 80 ps launch stub + 50 R line.
(3) Line driver (sim/phase/line_drive.py chain with the choke replaced by the tee): 3 Gbps PRBS7, 1 MHz square.
Runs long enough for the choke currents to settle (the summary uses the last period / the last bits).
  python3 tran.py          writes tran.json, plot_strobe.png, plot_line.png
"""
from __future__ import annotations

import json
import os
import sys
from multiprocessing import Pool

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "strobe"))
sys.path.insert(0, os.path.join(HERE, "..", "phase"))
import chain as sc  # noqa: E402  (sim/strobe/chain.py)
import common as pc  # noqa: E402  (sim/phase/common.py)
import frontend as f  # noqa: E402
import line_drive as ld  # noqa: E402
import tees  # noqa: E402

# which tee sits on which stage
SETS = {
    "present": {"TRF": "present_sampler", "GVA": "present_gva", "LINE": "present_line"},
    "corrected": {"TRF": "corr_trf", "GVA": "corr_gva", "LINE": "corr_trf"},
    "ideal 47 uH": {"TRF": "L47", "GVA": "L47", "LINE": "L47"},
}


def attach(d, node, kind, tag):
    if kind == "L47":
        d.add(f"L{tag} {node} 0 47u")
    else:
        d.add(f"X{tag} {node} 0 TEE_{kind}")


def strobe_deck(setname, chain_name, period, n_per, load, d_bead):
    stages = {"2xTRF": [("TRF", 0), ("TRF", 12)], "TRF+GVA": [("TRF", 0), ("GVA", 10)]}[chain_name]
    d = f.Deck()
    d.add("* strobe chain with bias tees")
    d.add(tees.lib(d_bead))
    tr = 450e-12
    d.add(f"Vf fe 0 pulse(-1.65 1.65 {period / 4:.6g} {tr / 0.8:.4g} {tr / 0.8:.4g} {period / 2 - tr / 0.8:.6g} {period:.6g})")
    d.add("Rfo fe fp 40\nCfp fp 0 3p\nRfs fp c0x 47\nCc0 c0x c0 100n")
    node = "c0"
    for i, (kind, db) in enumerate(stages):
        if i:
            d.add(f"Cc{i} {node} {node}x 100n")
            sc.pad(d, f"p{i}", f"{node}x", f"s{i}in", db)
            node_in = f"s{i}in"
        else:
            node_in = node
        o = f"s{i}o"
        sc.stage(d, f"S{i}", kind, node_in, o, "nominal")
        attach(d, o, SETS[setname][kind], f"bt{i}")
        node = o
    d.add(f"Ccf {node} out 100n")
    if load == "stub":
        d.trace("out", "stend", 0, td=80e-12)
        d.add("Rstub stend 0 0.05")
    d.add("Rload out 0 50")
    tstop = period * n_per
    d.add(".options klu reltol=1e-3 abstol=1e-12 vntol=1e-6")
    d.add(f".tran 5p {tstop:.6g} {tstop - 1.25 * period:.6g} 25p")
    d.add(".end")
    return "\n".join(d.lines) + "\n", tstop


def strobe_case(args):
    setname, chain_name, period, n_per, load, d_bead = args
    deck, tstop = strobe_deck(setname, chain_name, period, n_per, load, d_bead)
    a = pc.waves(deck, ["v(out)", "v(s0o)"], tmax_list=(None, "15p", "40p"))
    t, v, v0 = a[:, 0], a[:, 1], a[:, 2]
    te = period / 4 + (n_per - 1) * period            # last rising edge (FPGA 50 % point + chain delay ~0.4 ns)
    r = dict(set=setname, chain=chain_name, period=period, load=load, d=d_bead)
    if load == "50":
        before = v[(t > te - 3e-9) & (t < te - 0.2e-9)].mean()
        after = v[(t > te + 0.8e-9) & (t < te + 1.6e-9)].mean()
        end = v[(t > te + period / 2 - 3e-9) & (t < te + period / 2 - 0.2e-9)].mean()
        r.update(step=after - before, droop=(after - end) / (after - before),
                 s0_end=float(v0[(t > te + period / 2 - 3e-9) & (t < te + period / 2 - 0.2e-9)].mean()))
        late = (t > te + 2e-9) & (t < te + 30e-9)
        tt = t[late]
        fit = np.polyval(np.polyfit(tt, v[late], 1), tt)
        r["ring_pp"] = float(np.ptp(v[late] - fit))
    else:
        w = (t > te - 1e-9) & (t < te + 4e-9)
        pk = v[w].max()
        tw = t[w][v[w] > pk / 2]
        r.update(peak=pk, fwhm=(tw[-1] - tw[0]) * 1e12,
                 tail_pp=float(np.ptp(v[(t > te + 1.5e-9) & (t < te + period / 2 - 1e-9)])))
    r["t"] = (t - te).tolist()[::4]
    r["v"] = v.tolist()[::4]
    return r


# ------------------------------------------------------------------------------------------- line driver
def line_case(args):
    setname, case = args
    kind = SETS[setname]["LINE"]
    orig = ld.chain

    def chain(dk, line_in):
        dk.add(tees.lib(1.0))
        dk.add(f"Rdc cmp_p cmp_n {ld.R_DC}")
        dk.add(f"Cinp cmp_p trf_in {ld.C_IN}\nCinn cmp_n dum {ld.C_IN}\nRdum dum 0 50\nCdum dum 0 0.2p")
        dk.add(f"Rbrp cmp_p rxp {ld.R_BR}\nRbrn cmp_n rxn {ld.R_BR}\nCrxp rxp 0 {ld.C_RX}\nCrxn rxn 0 {ld.C_RX}")
        pc.trf(dk, "u", "trf_in", "trf_out")
        attach(dk, "trf_out", kind, "lt")
        dk.add(f"Cout trf_out pad_in {ld.C_OUT}")
        pc.pad12(dk, "pad_in", line_in)
    ld.chain = chain
    try:
        r = ld.slow(case)
    finally:
        ld.chain = orig
    out = dict(set=setname, case=case)
    t, v = r["t"], r["line"]
    if case == "PRBS":
        tb = 2e-9 + (np.arange(20, 254) + 0.5) / 3e9 + 0.25e-9
        vb = np.interp(tb, t, v)
        out.update(eye_hi_min=float(vb[vb > 0].min()), eye_lo_max=float(vb[vb < 0].max()))
        i = np.flatnonzero(np.sign(v[1:]) != np.sign(v[:-1]))
        tc = t[i] - v[i] * (t[i + 1] - t[i]) / (v[i + 1] - v[i])
        tc = tc[tc > 10e-9]
        ph = (tc - 2e-9) * 3e9
        dev = (ph - np.round(ph - np.median(ph - np.round(ph)))) / 3e9
        dev -= dev.mean()
        out.update(ddj_rms_ps=float(np.std(dev) * 1e12), ddj_pp_ps=float(np.ptp(dev) * 1e12))
        m = (t > 20e-9) & (t < 40e-9)
    elif case == "1MHz":
        out["after_halfperiod"] = [float(np.interp(5e-6 + x, t, v)) for x in (5e-9, 250e-9, 495e-9)]
        m = (t > 4.9e-6) & (t < 6.1e-6)
    else:
        out["after_edge"] = {f"{x * 1e6:g}us": float(np.interp(0.6e-3 + x, t, v)) for x in (10e-9, 1e-6, 5e-6, 20e-6)}
        m = (t > 0.6e-3 - 2e-6) & (t < 0.6e-3 + 20e-6)
    out["t"] = t[m].tolist()
    out["v"] = v[m].tolist()
    return out


def main():
    jobs = []
    for s in SETS:
        jobs += [(s, "2xTRF", 320e-9, 12, "50", 1.0), (s, "2xTRF", 320e-9, 12, "stub", 1.0),
                 (s, "TRF+GVA", 20e-9, 60, "stub", 1.0)]
    jobs += [("corrected", "2xTRF", 320e-9, 12, "50", 0.85), ("present", "TRF+GVA", 20e-9, 60, "stub", 0.65),
             ("corrected", "TRF+GVA", 20e-9, 60, "stub", 0.65)]
    ljobs = [(s, c) for s in SETS for c in ("PRBS", "1MHz", "1kHz")]
    with Pool(2) as p:
        sres = p.map(strobe_case, jobs)
        lres = p.map(line_case, ljobs)
    summ = {"strobe": [{k: v for k, v in r.items() if k not in ("t", "v")} for r in sres],
            "line": [{k: v for k, v in r.items() if k not in ("t", "v")} for r in lres]}
    json.dump(summ, open(os.path.join(HERE, "tran.json"), "w"), indent=1, default=float)
    for r in summ["strobe"] + summ["line"]:
        print(r)

    plt.rcParams.update({"font.size": 11})
    col = {"present": "C3", "corrected": "C0", "ideal 47 uH": "k"}
    fig, ax = plt.subplots(1, 3, figsize=(17, 5.4))
    for r in sres:
        if r["d"] != 1.0:
            continue
        t, v = np.array(r["t"]), np.array(r["v"])
        lw, ls = (1.0, "--") if r["set"].startswith("ideal") else (1.5, "-")
        if r["chain"] == "2xTRF" and r["load"] == "50":
            ax[0].plot(t * 1e9, v, ls, color=col[r["set"]], lw=lw,
                       label=f"{r['set']}: step {r['step']:.2f} V, droop {100 * r['droop']:.1f} %, ring {1e3 * r['ring_pp']:.0f} mV pp")
        elif r["chain"] == "2xTRF":
            ax[1].plot(t * 1e12, v, ls, color=col[r["set"]], lw=lw,
                       label=f"{r['set']}: {r['peak']:.2f} V, FWHM {r['fwhm']:.0f} ps, tail {1e3 * r['tail_pp']:.0f} mV pp")
        else:
            ax[2].plot(t * 1e12, v, ls, color=col[r["set"]], lw=lw,
                       label=f"{r['set']}: {r['peak']:.2f} V, FWHM {r['fwhm']:.0f} ps, tail {1e3 * r['tail_pp']:.0f} mV pp")
    ax[0].set(xlim=(-20, 170), xlabel="ns after the last rising edge", ylabel="V into 50 R",
              title="Sampler chain 2x TRF37D73, 3.125 MHz, 50 R load")
    ax[1].set(xlim=(-300, 1200), xlabel="ps", ylabel="V at the clip node",
              title="Sampler chain into the 80 ps shorted stub")
    ax[2].set(xlim=(-300, 1200), xlabel="ps", ylabel="V at the launch node",
              title="Phase chain TRF + GVA-84+, 50 MHz, 80 ps stub")
    for a in ax:
        a.grid(alpha=0.3)
        a.legend(fontsize=8, loc="lower right" if a is ax[0] else "upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "plot_strobe.png"), dpi=100)

    fig, ax = plt.subplots(1, 2, figsize=(15, 5.2))
    for r in lres:
        t, v = np.array(r["t"]), np.array(r["v"])
        ls = "--" if r["set"].startswith("ideal") else "-"
        if r["case"] == "PRBS":
            ax[0].plot(t * 1e9, v, ls, color=col[r["set"]], lw=1.3,
                       label=f"{r['set']}: DDJ {r['ddj_rms_ps']:.1f} ps rms / {r['ddj_pp_ps']:.1f} pp, eye {r['eye_hi_min']:.2f} / {r['eye_lo_max']:.2f} V")
        elif r["case"] == "1MHz":
            ax[1].plot(t * 1e6, v, ls, color=col[r["set"]], lw=1.3,
                       label=f"{r['set']}: {r['after_halfperiod'][0]:.3f} -> {r['after_halfperiod'][2]:.3f} V over the half period")
    ax[0].set(xlim=(20, 32), xlabel="ns", ylabel="V on the delay line", title="Line driver, 3 Gbps PRBS7 (line = 50 R)")
    ax[1].set(xlabel="us", ylabel="V", title="Line driver, 1 MHz square (choke droop)")
    for a in ax:
        a.grid(alpha=0.3)
        a.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "plot_line.png"), dpi=100)


if __name__ == "__main__":
    main()
