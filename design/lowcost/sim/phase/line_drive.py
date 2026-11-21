"""(a) Line drive: TLV3801 LVDS leg -> AC coupling -> TRF37D73 (behavioural) -> 12 dB pad -> line.

Part 1 (slow signals, line = lumped 50 R): 1 MHz square, 1 kHz square, 3 Gbps PRBS7, showing what
the gates see at 50 MHz strobe instants. Includes the 100 R DC termination across the LVDS pair,
the equal dummy load on the other leg, the TRF output choke and the bridged LVDS receiver.
Part 2 (fast edge): the same chain into a 16-tap line, 35 ps per tap, each tap loaded by one
BAT15-04W gate (hold caps 2 x 0.47 pF to the idle strobe lines, 2.2 k to the rails), 50 R end.

  python3 line_drive.py
"""
from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import common as c  # noqa: E402
import frontend as f  # noqa: E402

C_IN, C_OUT, L_CHOKE = 1e-6, 1e-6, 47e-6
R_DC, R_BR, C_RX = 100.0, 470.0, 3e-12
N_TAP, TD_TAP = 16, 35e-12
VB = 0.75


def chain(d: f.Deck, line_in: str) -> None:
    d.add(f"Rdc cmp_p cmp_n {R_DC}")
    d.add(f"Cinp cmp_p trf_in {C_IN}\nCinn cmp_n dum {C_IN}\nRdum dum 0 50\nCdum dum 0 0.2p")
    d.add(f"Rbrp cmp_p rxp {R_BR}\nRbrn cmp_n rxn {R_BR}\nCrxp rxp 0 {C_RX}\nCrxn rxn 0 {C_RX}")
    c.trf(d, "u", "trf_in", "trf_out")
    d.add(f"Lch trf_out 0 {L_CHOKE}\nRchp trf_out 0 20k")   # choke to Vcc (AC ground), 20k = its Q
    d.add(f"Cout trf_out pad_in {C_OUT}")
    c.pad12(d, "pad_in", line_in)


def pwl_square(f0: float, n_half: int, t0: float) -> str:
    """Starts at mid-current (so the DC state is the balanced one), first edge up at t0."""
    pts = ["0 0", f"{t0 - c.T_EDGE / 2:.9g} 0"]
    lvl = 1
    for k in range(n_half):
        t = t0 + k / (2 * f0)
        pts.append(f"{t - c.T_EDGE / 2:.9g} {-lvl * c.I_LVDS if k else 0}")
        pts.append(f"{t + c.T_EDGE / 2:.9g} {lvl * c.I_LVDS}")
        lvl = -lvl
    return " ".join(pts)


def pwl_prbs(rate: float, nbits: int, t0: float) -> str:
    s, bits = 0x7F, []
    for _ in range(nbits):
        b = ((s >> 6) ^ (s >> 5)) & 1
        s = ((s << 1) | b) & 0x7F
        bits.append(b)
    pts, prev = ["0 0", f"{t0 - c.T_EDGE / 2:.9g} 0"], 0.0
    for k, b in enumerate(bits):
        v = c.I_LVDS if b else -c.I_LVDS
        t = t0 + k / rate
        pts += [f"{t - c.T_EDGE / 2:.9g} {prev}", f"{t + c.T_EDGE / 2:.9g} {v}"]
        prev = v
    return " ".join(pts)


def slow(case: str):
    d = f.Deck()
    d.add("* line drive slow")
    if case == "1MHz":
        pwl, tend, tmax = pwl_square(1e6, 12, 1e-6), 7e-6, 2e-9
    elif case == "1kHz":
        pwl, tend, tmax = pwl_square(1e3, 3, 0.1e-3), 1.6e-3, 1e-6
    else:
        pwl, tend, tmax = pwl_prbs(3e9, 254, 2e-9), 2e-9 + 254 / 3e9 + 1e-9, 10e-12
    c.lvds(d, pwl)
    chain(d, "line")
    d.add("Rline line 0 50")
    d.add(".options klu reltol=1e-4 abstol=1e-12 vntol=1e-7")
    d.add(f".tran {min(tmax, 5e-12):.3g} {tend:.6g} 0 {tmax:.3g}")
    d.add(".end")
    a = c.waves("\n".join(d.lines) + "\n", ["v(line)", "v(cmp_p,cmp_n)", "v(rxp,rxn)", "v(trf_in)"],
                tmax_list=(None, tmax / 2, tmax / 5))
    return {"t": a[:, 0], "line": a[:, 1], "vod": a[:, 2], "rx": a[:, 3], "trf_in": a[:, 4]}


def fast():
    """Single rising edge into the loaded 16-tap line. Trace between taps: Z and td chosen so the
    loaded section is 50 R / 35 ps with the gate's ~0.37 pF (2 x 0.3 pF diode in series with 0.47 pF)."""
    c_tap = 0.37e-12
    c_tr = TD_TAP / 50 - c_tap
    l_tr = TD_TAP * 50
    zu, tdu = np.sqrt(l_tr / c_tr), np.sqrt(l_tr * c_tr)
    d = f.Deck()
    d.add("* line drive fast")
    d.add(f.MODELS)
    c.lvds(d, f"0 {-c.I_LVDS} 1n {-c.I_LVDS} {1e-9 + c.T_EDGE:.6g} {c.I_LVDS}")
    chain(d, "s0")
    for i in range(N_TAP):
        if i:
            d.trace(f"s{i - 1}", f"s{i}", 0, z0=zu, td=tdu, sec=2.5e-12)
        d.add(f"Xd1_{i} a{i} s{i} dpk\nXd2_{i} s{i} k{i} dpk")
        d.add(f"Ca{i} a{i} 0 0.47p\nCk{i} k{i} 0 0.47p")
        d.add(f"Rba{i} a{i} vba 2.2k\nRbk{i} k{i} vbk 2.2k")
    d.add(f"Rt s{N_TAP - 1} 0 50\nVba vba 0 {-VB}\nVbk vbk 0 {VB}")
    d.add(".options klu reltol=3e-4 abstol=1e-12 vntol=1e-7")
    d.add(".tran 1p 4n 0 2p")
    d.add(".end")
    vec = ["v(trf_out)", "v(s0)", "v(s7)", "v(s15)"]
    a = c.waves("\n".join(d.lines) + "\n", vec, tmax_list=(None, 1e-12, 3e-12))
    t = a[:, 0]
    out = {"zu": zu, "tdu": tdu}
    w = {}
    for j, n in enumerate(vec):
        v = a[:, j + 1]
        w[n] = v
        lo, hi = v[t < 1e-9].mean(), v[(t > 2.6e-9) & (t < 3.0e-9)].mean()
        x = (v - lo) / (hi - lo)
        import wave as wv
        t10, t20, t50, t80, t90 = (wv.crossing(t, x, q) for q in (0.1, 0.2, 0.5, 0.8, 0.9))
        out[n] = dict(lo=lo, hi=hi, t1090=t90 - t10, t2080=t80 - t20, t50=t50, over=x[t < 3e-9].max() - 1)
    out["tap_delay"] = (out["v(s15)"]["t50"] - out["v(s0)"]["t50"]) / 15
    return out, t, w


if __name__ == "__main__":
    from multiprocessing import Pool
    with Pool(3) as pool:
        rs = pool.map(slow, ["1MHz", "1kHz", "PRBS"])
    fr, tf, wf = fast()
    summ = {"fast": fr}
    fig, ax = plt.subplots(2, 2, figsize=(13, 8.5))
    for (name, r), axx in zip(zip(["1 MHz square", "1 kHz square", "3 Gbps PRBS7"], rs), ax.flat):
        t = r["t"]
        if name.startswith("1 kHz"):
            sc, unit = 1e3, "ms"
        elif name.startswith("1 MHz"):
            sc, unit = 1e6, "us"
        else:
            sc, unit = 1e9, "ns"
        axx.plot(t * sc, r["line"], lw=1, label="line (tap input)")
        axx.plot(t * sc, r["rx"], lw=1, alpha=0.8, label="bridged receiver input, differential")
        # 50 MHz strobe instants
        ts = np.arange(t[0], t[-1], 20e-9)
        vs = np.interp(ts, t, r["line"])
        if len(ts) < 2000:
            axx.plot(ts * sc, vs, ".", ms=3, label="line at 50 MHz strobes")
        axx.set_title(name)
        axx.set_xlabel(unit)
        axx.set_ylabel("V")
        axx.grid(alpha=0.3)
        axx.legend(fontsize=8, loc="lower right")
        summ[name] = dict(line_max=float(r["line"].max()), line_min=float(r["line"].min()),
                          rx_min_abs=float(np.min(np.abs(r["rx"][t > t[-1] * 0.3]))),
                          trf_in_pk=float(np.abs(r["trf_in"]).max()))
        if name.startswith("1 MHz"):
            m = (t > 5e-6) & (t < 6e-6)
            summ[name]["line_after_halfperiod"] = [float(np.interp(5e-6 + x, t, r["line"])) for x in (5e-9, 250e-9, 495e-9)]
        if name.startswith("1 kHz"):
            summ[name]["line_after"] = {f"{x * 1e6:g}us": float(np.interp(0.6e-3 + x, t, r["line"])) for x in (10e-9, 1e-6, 2e-6, 5e-6, 20e-6, 100e-6)}
        if name.startswith("3 Gbps"):
            m = t > 10e-9
            # sample at bit centres
            tb = 2e-9 + (np.arange(20, 254) + 0.5) / 3e9 + 0.25e-9
            vb = np.interp(tb, t, r["line"])
            summ[name]["eye_hi_min"] = float(vb[vb > 0].min())
            summ[name]["eye_lo_max"] = float(vb[vb < 0].max())
            v = r["line"]
            i = np.flatnonzero(np.sign(v[1:]) != np.sign(v[:-1]))
            tc = t[i] - v[i] * (t[i + 1] - t[i]) / (v[i + 1] - v[i])
            tc = tc[tc > 10e-9]
            ph = (tc - 2e-9) * 3e9
            dev = (ph - np.round(ph - np.median(ph - np.round(ph)))) / 3e9
            dev -= dev.mean()
            summ[name]["ddj_rms_ps"] = float(np.std(dev) * 1e12)
            summ[name]["ddj_pp_ps"] = float(np.ptp(dev) * 1e12)
            rb = np.interp(tb, t, r["rx"])
            summ[name]["rx_min_abs_bitcentre"] = float(np.abs(rb).min())
    axx = ax.flat[3]
    for n, v in wf.items():
        axx.plot(tf * 1e9, v, lw=1.2, label=n.replace("v(", "").replace(")", "").replace("s0", "tap 0").replace("s7", "tap 7").replace("s15", "tap 15"))
    axx.set_xlim(0.9, 2.6)
    axx.set_title("single edge into the loaded 16-tap line (35 ps/tap)")
    axx.set_xlabel("ns")
    axx.set_ylabel("V")
    axx.grid(alpha=0.3)
    axx.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(c.HERE, "line_drive.png"), dpi=100)
    json.dump(summ, open(os.path.join(c.HERE, "line_drive.json"), "w"), indent=1, default=float)
    print(json.dumps(summ, indent=1, default=float))
