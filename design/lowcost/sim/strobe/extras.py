"""AC coupling / choke droop over real pulse trains, phase-strobe launch pulse, and plots.
python3 extras.py   (run chain.py and bridge.py first)"""
from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import chain as c
import frontend as f

HERE = c.HERE


def train(period, duty, n_per, l_choke, c_cpl, stages=c.CHAINS["2xTRF"], stub_td=0.0, tr=450e-12):
    """Real AC coupling: caps between every block, choke from every gain-block output to AC ground."""
    d = f.Deck()
    d.add("* pulse train")
    d.add(f"Vf fe 0 pulse(0 3.3 {period / 4:.6g} {tr / 0.8:.4g} {tr / 0.8:.4g} {period * duty:.6g} {period:.6g})")
    d.add("Rfo fe fp 40")
    d.add("Cfp fp 0 3p")
    d.add(f"Rfs fp c0x 47")
    d.add(f"Cc0 c0x c0 {c_cpl}")
    node = "c0"
    for i, (kind, db) in enumerate(stages):
        if i:
            d.add(f"Cc{i} {node} {node}x {c_cpl}")
            c.pad(d, f"p{i}", f"{node}x", f"s{i}in", db)
            node_in = f"s{i}in"
        else:
            node_in = node
        o = f"s{i}o"
        c.stage(d, f"S{i}", kind, node_in, o, "nominal")
        d.add(f"Lch{i} {o} 0 {l_choke}")
        node = o
    d.add(f"Ccf {node} out {c_cpl}")
    if stub_td:
        d.trace("out", "stend", 0, td=stub_td)
        d.add("Rstub stend 0 0.05")
    d.add("Rload out 0 50")
    tstop = period * n_per
    text = "\n".join(d.lines) + "\n"
    text += f".options klu reltol=1e-3\n.tran 5p {tstop:.6g} 0 20p\n.control\nrun\nset wr_singlescale\nwrdata __DAT__ v(out)\n.endc\n.end\n"
    import subprocess, tempfile
    with tempfile.TemporaryDirectory() as td:
        dat = os.path.join(td, "a.dat")
        open(os.path.join(td, "a.cir"), "w").write(text.replace("__DAT__", dat))
        subprocess.run(["ngspice", "-b", os.path.join(td, "a.cir")], capture_output=True, timeout=600)
        a = np.loadtxt(dat)
    t, v = a[:, 0], a[:, 1]
    te = period / 4 + (n_per - 1) * period            # last rising edge
    before = v[(t > te - 3e-9) & (t < te - 0.2e-9)].mean()
    after = v[(t > te + 0.6e-9) & (t < te + 1.5e-9)].mean()
    return t, v, after - before


if __name__ == "__main__":
    res = {}
    cases = [
        ("S_STROBE 3.125 MHz, 50 % duty, choke 2.2 uH", 320e-9, 0.5, 2.2e-6),
        ("S_STROBE 3.125 MHz, 50 % duty, choke 47 uH", 320e-9, 0.5, 47e-6),
        ("S_STROBE 3.125 MHz, 1/64 duty, choke 47 uH", 320e-9, 1 / 64, 47e-6),
        ("PH_STROBE 50 MHz, 50 % duty, choke 2.2 uH", 20e-9, 0.5, 2.2e-6),
        ("PH_STROBE 50 MHz, 1/20 duty, choke 2.2 uH", 20e-9, 1 / 20, 2.2e-6),
    ]
    waves = {}
    for label, per, duty, lch in cases:
        n = 4 if per > 100e-9 else 30
        t, v, step = train(per, duty, n, lch, "100n")
        res[label] = step
        waves[label] = (t, v, per)
        print("%-48s step at the output of the 2xTRF chain: %.2f V (50 %% duty ideal 4.59 V)" % (label, step), flush=True)
    # phase strobe launch: chain into a shorted 50 ps stub + 50 R line
    r = c.edge(c.CHAINS["2xTRF"], tr=600e-12, duty=0.5, stub_td=50e-12)
    tt, vv = r["t"], r["v(out)"]
    pk = vv.max(); above = tt[vv > pk / 2]
    res["phase_pulse_peak"] = float(pk); res["phase_pulse_fwhm_ps"] = float((above[-1] - above[0]) * 1e12)
    print("phase strobe launched on a 50 R line through a 50 ps shorted stub: %.2f V peak, FWHM %.0f ps" % (pk, (above[-1] - above[0]) * 1e12))
    json.dump(res, open(os.path.join(HERE, "extras.json"), "w"), indent=1)

    # ---- plots
    plt.rcParams.update({"font.size": 12})
    fig, ax = plt.subplots(1, 2, figsize=(14, 5.5))
    for name, col in (("2xTRF", "C0"), ("3xTRF", "C1"), ("TRF+GVA", "C2")):
        for tr, ls in ((300e-12, "-"), (600e-12, "--")):
            q = c.edge(c.CHAINS[name], tr=tr, duty=0.5)
            a, m, b, lo, hi = c.t1090(q["t"], q["v(out)"])
            ax[0].plot((q["t"] - m) * 1e12, q["v(out)"], ls, color=col, label=f"{name}, FPGA {tr * 1e12:.0f} ps: {(b - a) * 1e12:.0f} ps")
    q = c.edge(c.CHAINS["2xTRF"], tr=600e-12, duty=0.5, split="pess")
    a, m, b, lo, hi = c.t1090(q["t"], q["v(out)"])
    ax[0].plot((q["t"] - m) * 1e12, q["v(out)"], ":", color="k", label=f"2xTRF pessimistic split: {(b - a) * 1e12:.0f} ps")
    ax[0].set(xlim=(-600, 600), xlabel="time from 50 % crossing, ps", ylabel="V into 50 R",
              title="Chain output edge (50 % duty, behavioural blocks)")
    ax[0].legend(fontsize=9); ax[0].grid(alpha=.3)
    ax[1].plot((tt - tt[np.argmax(vv)]) * 1e12, vv, color="C0", label="PH_STROBE launch, 50 ps stub")
    for o in json.load(open(os.path.join(HERE, "bridge_results.json"))):
        pass
    ax[1].set(xlim=(-400, 800), xlabel="ps", ylabel="V on the 50 R line", title="Shorted-stub pulse (2xTRF, 50 % duty)")
    ax[1].grid(alpha=.3); ax[1].legend()
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "chain_edges.png"), dpi=100)

    fig, ax = plt.subplots(1, 2, figsize=(14, 5.5))
    for label, (t, v, per) in waves.items():
        k = 0 if per > 100e-9 else 1
        ax[k].plot(t * 1e9, v, lw=0.8, label=f"{label}: step {res[label]:.2f} V")
    ax[0].set(xlabel="ns", ylabel="V into 50 R", title="S_STROBE train, AC coupled 100 nF, chokes"); ax[0].legend(fontsize=9)
    ax[1].set(xlabel="ns", xlim=(500, 600), title="PH_STROBE train (last 5 periods)"); ax[1].legend(fontsize=9)
    for a in ax: a.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "baseline.png"), dpi=100)

    br = json.load(open(os.path.join(HERE, "bridge_results.json")))
    fig, ax = plt.subplots(figsize=(12, 6))
    for o in br:
        if o["eff"] < 0.2:
            continue
        ax.plot(np.array(o["x"]) * 1e12, o["n"], ".-", ms=3,
                label="%s: %.0f ps, eff %.0f %%" % (o["label"], o["tr"], o["eff"] * 100))
    ax.set(xlim=(-400, 400), ylim=(-0.2, 1.7), xlabel="strobe edge minus input step, ps", ylabel="held / final",
           title="Sampler bridge step response with simulated strobe waveforms (sim/scope_sampler.py deck D)")
    ax.legend(fontsize=8, loc="upper left"); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "bridge_step.png"), dpi=100)
