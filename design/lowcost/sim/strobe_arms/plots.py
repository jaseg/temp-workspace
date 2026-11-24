"""arms.png: (left) step response of the held value vs strobe-to-input delay (clean 35 ps input), each curve
shifted to its own 50 % point; (middle) differential bridge drive v(ka) - v(kk), quiet input, sampling edge;
(right) the same for the falling edge (reverse pulse, +160 ns), with and without D401.  python3 plots.py"""
import dataclasses, json, os, subprocess, tempfile
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import arms as a

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, "results.json")))
COL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
SEL = [("lumped (no arms, old deck geometry)", "lumped (old deck), +/-1 V", a.P(arm_mm=0.0, r204_pos="sym")),
       ("REC: as built + R204 sym + stub 80 ps + bias +/-1.3 V", "rev. 1: 99 ps arms, R204 sym, +/-1.3 V",
        a.P(r204_pos="sym", stub_td=80e-12, v_rev=2.6)),
       ("AB2: as built rev. 2, bias +/-1.0 V", "as built: 105.6 ps arms, +/-1.0 V", a.P(**a.AB)),
       ("AB2, bias +/-1.3 V", "as built: 105.6 ps arms, +/-1.3 V (recommended)", a.P(v_rev=2.6, **a.AB))]


def drive(p, noclamp=False):
    with tempfile.TemporaryDirectory() as td:
        dat = os.path.join(td, "w.dat")
        txt = a.build(dataclasses.replace(p, t_in=10e-9))
        if noclamp:
            txt = txt.replace("Xclamp clp_a clp dpk", "Rclamp_off clp 0 1g")
        txt = txt.replace(
            ".end\n", f".control\nrun\nset wr_singlescale\nwrdata {dat} v(ka) v(kk)\n.endc\n.end\n")
        cir = os.path.join(td, "a.cir")
        open(cir, "w").write(txt)
        subprocess.run(["ngspice", "-b", cir], capture_output=True)
        d = np.loadtxt(dat)
    return (d[:, 0] - p.t_strobe) * 1e12, d[:, 1] - d[:, 2]


fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 4.4))
for (key, lab, p), c in zip(SEL, COL):
    r = R[key]
    x = (np.array(r["x"]) - r["x50"]) * 1e12
    ax1.plot(x, r["n"], color=c, lw=2, label=f"{lab}: {r['tr']*1e12:.0f} ps, eff {r['eff']*100:.0f} %")
    t, v = drive(p)
    ax2.plot(t, v, color=c, lw=2, label=lab)
REC = a.P(v_rev=2.6, wave="fall", **a.AB)
for (lab, p, nc), c in zip([("as built, +/-1.3 V, D401 fitted", REC, False),
                            ("as built, +/-1.3 V, D401 removed", REC, True),
                            ("as built, +/-1.0 V, D401 fitted", a.P(wave="fall", **a.AB), False)],
                           [COL[3], "#c0392b", COL[2]]):
    t, v = drive(p, nc)
    ax3.plot(t, v, color=c, lw=2, label=lab)
ax3.axhline(0.5, color="#888888", lw=1, ls="--")
ax3.set_xlim(-100, 1000)
ax3.set_xlabel("time after the falling source edge (ps)")
ax3.set_ylabel("v(anode rail) - v(cathode rail) (V)")
ax3.set_title("Falling edge (reverse pulse, +160 ns), input 0 V", fontsize=10)
ax3.legend(fontsize=7, frameon=False, loc="lower right")
for ax in (ax1, ax2, ax3):
    ax.grid(color="#dddddd", lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
ax1.set_xlim(-900, 250)
ax1.set_xlabel("input step before the sampling instant (ps); < 0: step comes later")
ax1.set_ylabel("held value, normalised")
ax1.set_title("Step response (10-90 % = aperture); no 2nd sampling instant", fontsize=10)
ax1.set_ylim(-0.05, 1.45)
ax1.legend(fontsize=7, frameon=False, loc="upper left")
ax2.axhline(0.5, color="#888888", lw=1, ls="--")
ax2.text(900, 0.6, "two diodes conduct above ~0.5 V", fontsize=7, ha="right", color="#555555")
ax2.set_xlim(-100, 1000)
ax2.set_xlabel("time after the strobe source edge (ps)")
ax2.set_ylabel("v(anode rail) - v(cathode rail) at the diodes (V)")
ax2.set_title("Bridge drive, quiet input", fontsize=10)
ax2.legend(fontsize=7, frameon=False, loc="lower left")
fig.tight_layout()
fig.savefig(os.path.join(HERE, "arms.png"), dpi=110)
