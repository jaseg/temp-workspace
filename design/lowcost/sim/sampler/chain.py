"""Hold node -> TPH2501 G=+3 -> TPH2501 inverting level shift (0/3.3 V, 1k/1k, +in 0.725 V)
-> 33 R / 220 pF -> STM32G474 ADC sample switch (1 k, 5 pF, 108 ns window).

The strobe is replaced by a 150 ps current pulse into the hold node that gives the worst
full-scale jump (eff 0.69 x 0.72 V = 0.50 V at the hold node, settled). The ADC sampling
capacitor starts at the opposite end of the range (worst case kickback).
Writes chain.json and chain.png.   python3 chain.py
"""
import json, os, re, subprocess, sys, tempfile
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import amp  # noqa: E402

V0, DV = -0.25, 0.50           # hold node before the strobe, settled jump
C_G, C_D = 3.4e-12, 2.7e-12    # hold+pad+CM, differential
T_WIN = 108e-9
LSB = 2.9 / 4096


def deck(t_d, vcs0, probes=None, out=None):
    q = DV * C_G                                    # charge that gives DV once Cdiff is bootstrapped
    L = ["* chain", amp.SUBCKT,
         "Vp vp 0 2.5", "Vn vn 0 -2.5", "Vdd vdd 0 3.3",
         "Ch ls 0 3.4p", "Cdif ls inv 2.7p", "Ccmn inv 0 1.2p",
         f"Rleak ls 0 {os.environ.get('RLEAK', '7.5meg')}",                     # BAT15 model reverse conductance, both pairs
         "Ib 0 ls 3p",                              # TPH2501 max bias at 27 C
         f"Iinj 0 ls pulse(0 {q / 150e-12:.5g} 10n 1p 1p 150p 1)",
         "Xu1 ls inv o1 vp vn tph2501", "Rf o1 inv 1k", "Rg inv 0 499",
         "Rin o1 ninv2 1k", "Rf2 ninv2 o2 1k", "Vref ref 0 0.725", "Cinp2 ninv2 0 1p",
         "Xu2 ref ninv2 o2 vdd 0 tph2501",
         "Rpin o2 pin 33", "Cpin pin 0 220p", "Cpinpar pin 0 5p",
         f"Sadc pin cs ctl 0 sw1", f"Vctl ctl 0 pwl(0 0 {10e-9 + t_d:.6g} 0 {10e-9 + t_d + 1e-10:.6g} 1 "
         f"{10e-9 + t_d + T_WIN:.6g} 1 {10e-9 + t_d + T_WIN + 1e-10:.6g} 0)",
         ".model sw1 sw(vt=0.5 vh=0.01 ron=1k roff=1e12)",
         "Cs cs 0 5p", f".ic v(ls)={V0} v(cs)={vcs0}",
         ".options klu reltol=1e-5 abstol=1e-14 vntol=1e-8",
         f".tran 0.1n {10e-9 + 320e-9:.6g} 0 0.2n",
         f".meas tran vcs find v(cs) at={10e-9 + t_d + T_WIN:.6g}",
         f".meas tran vfin find v(pin) at={10e-9 + 315e-9:.6g}",
         f".meas tran vpin find v(pin) at={10e-9 + t_d + T_WIN:.6g}"]
    if probes:
        L.append(f".control\nrun\nwrdata {out} {' '.join(probes)}\n.endc")
    L.append(".end")
    return "\n".join(L) + "\n"


def run(t_d, vcs0, probes=None):
    with tempfile.TemporaryDirectory() as td:
        path, out = os.path.join(td, "c.cir"), os.path.join(td, "w.txt")
        open(path, "w").write(deck(t_d, vcs0, probes, out))
        r = subprocess.run(["ngspice", "-b", path], capture_output=True, text=True)
        m = {k: float(v) for k, v in re.findall(r"^(vcs|vfin|vpin)\s*=\s*([-+0-9.eE]+)", r.stdout, re.M)}
        w = np.loadtxt(out) if probes else None
    return m, w


if __name__ == "__main__":
    # ideal final value of the pin: Vadc = 1.45 - 3 * Vhold
    v_final = 1.45 - 3.0 * (V0 + DV)
    v_start = 1.45 - 3.0 * V0
    res = []
    for t_d in np.arange(20e-9, 215e-9, 16e-9):
        m, _ = run(t_d, v_start)            # sampling cap left at the previous (opposite) value
        res.append(dict(t_d=t_d, err_lsb=(m["vcs"] - v_final) / LSB, err_pin_lsb=(m["vpin"] - v_final) / LSB, vfin=m["vfin"]))
        print(f"trigger {t_d*1e9:5.0f} ns  error at end of window {res[-1]['err_lsb']:8.2f} LSB  (pin {res[-1]['err_pin_lsb']:7.2f})")
    m, w = run(150e-9, v_start, probes=["v(ls)", "v(o1)", "v(o2)", "v(pin)", "v(cs)"])
    json.dump(dict(v_final=v_final, sweep=res), open(os.path.join(HERE, "chain.json"), "w"), indent=1)
    t = w[:, 0] * 1e9 - 10
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    for col, lab in ((1, "hold node x3"), (3, "U1 out (hold amp)"), (5, "U2 out (level shift)"), (7, "ADC pin"), (9, "ADC sample cap (trigger 150 ns)")):
        y = w[:, col] * (3 if col == 1 else 1)
        ax[0].plot(t, y, label=lab, lw=1.4)
    ax[0].set_xlabel("time after strobe (ns)"); ax[0].set_ylabel("V"); ax[0].set_xlim(-5, 320)
    ax[0].set_title("Worst full-scale jump (0.50 V at the hold node)"); ax[0].grid(alpha=.3); ax[0].legend(fontsize=8)
    td = np.array([r["t_d"] for r in res]) * 1e9
    ax[1].semilogy(td, np.abs([r["err_lsb"] for r in res]), "o-", label="sample cap at end of 108 ns window")
    ax[1].semilogy(td, np.abs([r["err_pin_lsb"] for r in res]), "s--", label="pin at the same time")
    ax[1].axhline(0.5, color="k", lw=.8, ls=":")
    ax[1].set_xlabel("ADC trigger delay after strobe (ns)"); ax[1].set_ylabel("|error| (LSB, 2.9 V / 4096)")
    ax[1].set_title("Settling error vs. trigger delay"); ax[1].grid(alpha=.3, which="both"); ax[1].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "chain.png"), dpi=110)
