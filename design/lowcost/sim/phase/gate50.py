"""(b)/(d) One tap gate (BAT15-04W, 2 x 0.47 pF) strobed at 50 MHz with the final readout network.

Line: 50 R, driven from 50 R and terminated (as tap_gate.py), level changes between strobes in a
random +/-a pattern, edges 240 ps (as the line edge from line_drive.py). Strobe per side: EMF 2*vp
through 50 R into a 50 R-terminated node (= a strobe line passing the gate), trapezoid with width
at half height `fwhm`. Readout: hold nodes -> 2.2k to VTAP_N/VTAP_P, -> 1k each to the comparator
input, Cin to ground. The comparator input is fitted as  v_n = g*L_n + r*L_(n-1) + c  at several
times after each strobe (L = line level, +/-1).

  python3 gate50.py
"""
from __future__ import annotations

import dataclasses
import json
import os
from multiprocessing import Pool

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import common as c  # noqa: E402
import frontend as f  # noqa: E402

T_P = 20e-9
N_ST = 14
rng = np.random.default_rng(7)
PATTERN = rng.choice([-1, 1], N_ST)
PATTERN[:2] = [1, -1]


@dataclasses.dataclass
class P:
    vp: float = 2.0           # unloaded strobe amplitude at the gate, per side
    fwhm: float = 150e-12
    tr: float = 60e-12
    vb: float = 0.75          # hold-node bias (rails = vb*(rb+rs)/rs)
    rb: float = 2.2e3
    rs: float = 1e3
    cin: float = 3e-12
    a: float = 0.21           # line half swing (data); isolated edges reach 2a
    c: float = 0.47e-12
    label: str = ""


def build(p: P) -> str:
    d = f.Deck()
    d.add("* gate at 50 MHz")
    d.add(f.MODELS)
    t0 = 5e-9
    pts, prev = ["0", f"{2 * p.a * PATTERN[0]}"], PATTERN[0]
    pts = [f"0 {2 * p.a * PATTERN[0]}"]
    for n in range(1, N_ST):
        te = t0 + n * T_P - T_P / 2
        pts += [f"{te:.6g} {2 * p.a * prev}", f"{te + 0.3e-9:.6g} {2 * p.a * PATTERN[n]}"]
        prev = PATTERN[n]
    d.add(f"Vs s_e 0 pwl({' '.join(pts)})\nRs s_e s 50\nRt s 0 50")
    for name, node, amp in (("sp", "stp", 2 * p.vp), ("sn", "stn", -2 * p.vp)):
        d.add(f"V{name} {name}_e 0 pulse(0 {amp} {t0 - p.fwhm / 2:.6g} {p.tr:.4g} {p.tr:.4g} {p.fwhm - p.tr:.4g} {T_P:.6g})")
        d.add(f"R{name} {name}_e {node} 50\nR{name}t {node} 0 50")
    rail = p.vb * (p.rb + p.rs) / p.rs
    d.add("Xd1 a s dpk\nXd2 s k dpk")
    d.add(f"Ca a stp {p.c}\nCk k stn {p.c}")
    d.add(f"Vba vba 0 {-rail}\nVbk vbk 0 {rail}\nRba a vba {p.rb}\nRbk k vbk {p.rb}")
    d.add(f"Roa a out {p.rs}\nRok k out {p.rs}\nCout out 0 {p.cin}")
    d.add(".options klu reltol=3e-4 abstol=1e-12 vntol=1e-7")
    d.add(f".tran 1p {t0 + N_ST * T_P:.6g} 0 3p")
    d.add(".end")
    return "\n".join(d.lines) + "\n"


DTS = [1e-9, 2e-9, 3e-9, 5e-9, 8e-9, 12e-9, 19.5e-9]


def job(p: P):
    a = c.waves(build(p), ["v(out)", "v(s)", "v(a,s)", "v(s,k)", "i(vsp)", "v(a)", "v(k)"],
                tmax_list=(None, 2e-12, 5e-12))
    t = a[:, 0]
    out, s = a[:, 1], a[:, 2]
    t0 = 5e-9
    rows = {}
    L = PATTERN.astype(float)
    for dt in DTS:
        v = np.array([np.interp(t0 + n * T_P + dt, t, out) for n in range(N_ST)])
        X = np.column_stack([L[2:], L[1:-1], np.ones(N_ST - 2)])
        g, r, cc = np.linalg.lstsq(X, v[2:], rcond=None)[0]
        rows[f"{dt * 1e9:g}ns"] = dict(g_mV=g * 1e3, r_mV=r * 1e3, c_mV=cc * 1e3, resid_mV=float(np.std(v[2:] - X @ [g, r, cc]) * 1e3))
    # strobe charge per pulse (positive side), kick-out on the line, peak reverse voltage
    m = (t > t0 + 5 * T_P - 1e-9) & (t < t0 + 5 * T_P + 2e-9)
    ivs = -a[:, 5]
    q = np.trapezoid(ivs[m] - (2 * p.vp) / 100 * 0, t[m])
    rev = max(-(a[:, 3]).min(), -(a[:, 4]).min())
    kick = []
    for n in range(3, N_ST):
        mm = (t > t0 + n * T_P - 0.3e-9) & (t < t0 + n * T_P + 0.6e-9)
        kick.append(np.ptp(s[mm]))
    return dict(p=dataclasses.asdict(p), fit=rows, kick_mV=float(np.max(kick) * 1e3), rev_V=float(rev),
                rail_V=p.vb * (p.rb + p.rs) / p.rs, i_rail_mA=(p.vb * (p.rb + p.rs) / p.rs) / (p.rb + p.rs / 2) * 1e3 if False else None), (t, out, a[:, 6], a[:, 7])


CASES = [
    P(vp=2.0, cin=3e-12, label="vp 2.0 V, Cin 3 pF"),
    P(vp=2.0, cin=6e-12, label="vp 2.0 V, Cin 6 pF"),
    P(vp=1.5, cin=3e-12, label="vp 1.5 V, Cin 3 pF"),
    P(vp=2.5, cin=3e-12, label="vp 2.5 V, Cin 3 pF"),
    P(vp=2.0, cin=3e-12, fwhm=250e-12, label="vp 2.0 V, 250 ps, Cin 3 pF"),
    P(vp=2.0, cin=3e-12, a=0.42, label="vp 2.0 V, isolated edge 2a=0.42"),
]

if __name__ == "__main__":
    with Pool(3) as pool:
        res = pool.map(job, CASES)
    out = []
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
    for (r, (t, v, va, vk)), p in zip(res, CASES):
        r["fit"] = {k: {kk: round(vv, 3) for kk, vv in x.items()} for k, x in r["fit"].items()}
        out.append(r)
        print(p.label, "| kick %.0f mV | rev %.2f V" % (r["kick_mV"], r["rev_V"]))
        for k, x in r["fit"].items():
            print("   %6s  g %6.2f mV  residue %6.2f mV  const %6.2f  fit-err %.2f" % (k, x["g_mV"], x["r_mV"], x["c_mV"], x["resid_mV"]))
        if p.label in ("vp 2.0 V, Cin 3 pF", "vp 2.0 V, Cin 6 pF", "vp 1.5 V, Cin 3 pF"):
            ax[0].plot(t * 1e9, v * 1e3, lw=1, label=p.label)
    ts = 5e-9 + np.arange(N_ST) * T_P
    for x in ts:
        ax[0].axvline(x * 1e9, color="0.85", lw=0.6, zorder=0)
    for n, x in enumerate(ts):
        ax[0].text(x * 1e9 + 1, 38, "+" if PATTERN[n] > 0 else "-", fontsize=9)
    ax[0].set_xlabel("ns")
    ax[0].set_ylabel("comparator input, mV")
    ax[0].set_title("tap readout 2.2k / 2x1k at 50 MHz (line +/-0.21 V, sign of each snapshot on top)")
    ax[0].grid(alpha=0.3)
    ax[0].legend(fontsize=8)
    ax[0].set_ylim(-45, 45)
    for r, p in zip(out, CASES[:4]):
        dts = [float(k[:-2]) for k in r["fit"]]
        ax[1].plot(dts, [x["g_mV"] for x in r["fit"].values()], "o-", label=p.label + ": signal")
        ax[1].plot(dts, [x["r_mV"] for x in r["fit"].values()], "x--", label=p.label + ": residue of previous")
    ax[1].axhline(0, color="k", lw=0.5)
    ax[1].set_xlabel("time after strobe, ns")
    ax[1].set_ylabel("mV per unit line sign")
    ax[1].set_title("fit v = g*L_n + r*L_n-1 (line +/-0.21 V)")
    ax[1].grid(alpha=0.3)
    ax[1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(c.HERE, "gate50.png"), dpi=100)
    json.dump(out, open(os.path.join(c.HERE, "gate50.json"), "w"), indent=1, default=float)
