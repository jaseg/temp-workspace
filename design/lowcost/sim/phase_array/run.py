"""Verification runs for the 16-tap array (deck.py). python3 run.py  -> results.json, *.png
(1) strobe along the loaded lines, (2) captured value vs edge position, tap spacing, single-shot rms,
(3) wrong-polarity pulse (taps; sampler bridge in bridge_rev.py), (4) signal-line return loss / edge."""
from __future__ import annotations

import dataclasses
import json
import os
from multiprocessing import Pool

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.special import erf  # noqa: E402

import deck as D  # noqa: E402
import frontend as f  # noqa: E402
import wave as wv  # noqa: E402

HERE = D.HERE
N = D.N
PA = [f"v(pa{i})" for i in range(N)]
T_CAP = 3e-9      # comparator input read 3 ns after the strobe peak (peak region, 1-5 ns)


def pulse_stats(t, v):
    i = np.argmax(np.abs(v)); pk = v[i]
    m = np.abs(v) > abs(pk) / 2
    j0 = i
    while j0 > 0 and m[j0 - 1]:
        j0 -= 1
    j1 = i
    while j1 < len(v) - 1 and m[j1 + 1]:
        j1 += 1
    return dict(peak=float(pk), t_peak=float(t[i]), fwhm_ps=float((t[j1] - t[j0]) * 1e12))


def strobe_only(p):
    t, w = D.sim(dataclasses.replace(p, signal=False, tstop=2e-9), D.T_ST + 0.7e-9, PA + ["v(pk0)", "v(pk8)", "v(pk15)"])
    k = t < D.T_ST + 2e-9
    st = {n: pulse_stats(t[k], w[n][k]) for n in w}
    return t, w, st


def sweep_job(args):
    p, tp0 = args
    t, w = D.sim(p, tp0, [f"v(o{i})" for i in range(N)] + ["v(s0)", "v(s15)"])
    return {dt: [float(np.interp(tp0 + dt, t, w[f"v(o{i})"])) for i in range(N)] for dt in (1e-9, 2e-9, 3e-9, 5e-9)}


def fit_taps(xs, V):
    """V[x, tap] -> per tap: lo/hi plateaus, effective position (-x at the half-way crossing), 10-90 width."""
    out = []
    for i in range(N):
        v = V[:, i]
        hi, lo = v[:3].mean(), v[-3:].mean()       # x very negative: edge passed the tap before the strobe
        n = (v - lo) / (hi - lo)
        nn = n[::-1]; xx = -xs[::-1]               # increasing in -x
        pos = wv.crossing(xx, nn, 0.5)
        w1090 = wv.crossing(xx, nn, 0.9) - wv.crossing(xx, nn, 0.1)
        out.append(dict(hi_mV=hi * 1e3, lo_mV=lo * 1e3, pos_ps=pos * 1e12, w1090_ps=w1090 * 1e12))
    return out


def tdc(taps, half, w1090, off=np.hypot(2.2e-3, 3e-3), noise=np.hypot(1e-3, 1.6e-3), chips=20, ev=4000, seed=3):
    """Estimator of sim/snapshot_tdc.run (code-density calibration, last-0/first-1 midpoint), with the
    simulated tap positions, per-tap half swings and edge width instead of a uniform line."""
    rng = np.random.default_rng(seed)
    taps = np.asarray(taps); half = np.asarray(half)
    sig = w1090 / 2.563
    n = len(taps); lo_w, hi_w = taps.min() - 4 * 35e-12, taps.max() + 4 * 35e-12
    errs = []
    for _ in range(chips):
        offs = rng.normal(0, off, n)
        tt = taps + rng.normal(0, 2e-12, n)

        def bits(T):
            return half[None, :] * erf((tt[None, :] - T[:, None]) / (np.sqrt(2) * sig)) + offs + rng.normal(0, noise, (len(T), n)) > 0
        p1 = bits(rng.uniform(lo_w, hi_w, 40000)).mean(0)
        eff = lo_w + (hi_w - lo_w) * p1
        good = (p1 > 0.02) & (p1 < 0.98)
        o = np.argsort(eff); o = o[good[o]]
        pos = eff[o]
        T = rng.uniform(taps.min() + 35e-12, taps.max() - 35e-12, ev)
        b = bits(T)[:, o]
        k = b.sum(1); m = len(pos)
        edges = np.concatenate([[pos[0] - 35e-12], pos, [pos[-1] + 35e-12]])
        est = (edges[m - k] + edges[m - k + 1]) / 2
        ok = (k > 0) & (k < m)
        e = (est - T)[ok]
        errs.append(e - np.median(e))
    e = np.concatenate(errs)
    return float(np.sqrt(np.mean(e ** 2)))


def reference_gate(vp=2.0, fwhm=170e-12, cin=3e-12):
    """One gate as in phase/gate50.py (unloaded strobe vp per side on a terminated 50 R line), one strobe:
    loaded strobe-node peak and comparator input for line +0.21 V vs -0.21 V at T_CAP."""
    res = {}
    for lvl in (0.21, -0.21):
        d = f.Deck(); d.add("* ref gate"); d.add(f.MODELS)
        d.add(f"Vs s_e 0 {2 * lvl}\nRs s_e s 50\nRt s 0 50")
        t0, tr = 1e-9, 60e-12
        for nm, node, amp in (("sp", "stp", 2 * vp), ("sn", "stn", -2 * vp)):
            d.add(f"V{nm} {nm}_e 0 pulse(0 {amp} {t0 - fwhm / 2:.6g} {tr} {tr} {fwhm - tr:.4g} 1)")
            d.add(f"R{nm} {nm}_e {node} 50\nR{nm}t {node} 0 50")
        d.add("Xd1 a s dpk\nXd2 s k dpk\nCa a stp 0.47p\nCk k stn 0.47p\nVba vba 0 -2.5\nVbk vbk 0 2.5")
        d.add(f"Rba a vba 2.2k\nRbk k vbk 2.2k\nRoa a out 1k\nRok k out 1k\nCout out 0 {cin}")
        d.add(".options klu reltol=3e-4 abstol=1e-12 vntol=1e-7\n.tran 1p 6n 0 3p\n.end")
        a = D.c.waves("\n".join(d.lines) + "\n", ["v(out)", "v(stp)"])
        res[lvl] = (float(np.interp(t0 + T_CAP, a[:, 0], a[:, 1])), float(a[:, 2].max()))
    return dict(vp=vp, half_mV=(res[0.21][0] - res[-0.21][0]) / 2 * 1e3, mid_mV=(res[0.21][0] + res[-0.21][0]) / 2 * 1e3,
                loaded_node_peak=res[0.21][1])


def long_job(args):
    p, tp0 = args
    vec = [f"v(o{i})" for i in (0, 8, 15)] + [f"v(s{i},a{i})" for i in (0, 8, 15)] + [f"v(k{i},s{i})" for i in (0, 8, 15)] + ["v(pa0)", "v(pk0)"]
    t, w = D.sim(p, tp0, vec)
    return t, w


def ret_loss():
    """Small-signal S11 of the loaded signal line at the strobe-idle bias (AC, 50 R source)."""
    out = {}
    for gates in (True, False):
        p = D.A(gates=gates)
        txt = D.build(p, 2e-9)
        lines = [l for l in txt.splitlines() if not l.startswith(".tran")]
        # replace the driver chain by an AC source with 50 R at s0
        txt = "\n".join(lines[:-1]) + "\nVac acs 0 dc 0 ac 1\nRac acs s0x 50\nCblk s0x s0 1u\n.ac dec 40 10meg 8g\n"
        txt = txt.replace("Rpd2 pad_in s0 91", "Rpd2 pad_in pad_x 91").replace("Rpd3 s0 0 82", "Rpd3 pad_x 0 82")
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as td:
            dat = os.path.join(td, "a.dat")
            txt = txt + f".control\nrun\nset wr_singlescale\nwrdata {dat} v(s0)\n.endc\n.end"
            open(os.path.join(td, "a.cir"), "w").write(txt + "\n")
            subprocess.run(["ngspice", "-b", os.path.join(td, "a.cir")], capture_output=True, timeout=300)
            a = np.loadtxt(dat)
        fr, vs = (a[:, 0], a[:, 1] + 1j * a[:, 2]) if a.shape[1] == 3 else (a[:, 0], a[:, 2] + 1j * a[:, 3])
        g = 2 * vs - 1
        out["gates" if gates else "no_gates"] = (fr, -20 * np.log10(np.abs(g) + 1e-12))
    return out


if __name__ == "__main__":
    R = {}
    nom = D.A()
    # ---------- (1) strobe along the lines
    t1, w1, st = strobe_only(nom)
    tp0 = st["v(pa0)"]["t_peak"]
    arr = np.array([st[n]["t_peak"] for n in PA]) - tp0
    R["strobe"] = {k: v for k, v in st.items() if k in ("v(pa0)", "v(pa8)", "v(pa15)", "v(pk0)", "v(pk8)", "v(pk15)")}
    R["strobe_arrival_ps"] = (arr * 1e12).round(1).tolist()
    _, _, st_ng = strobe_only(dataclasses.replace(nom, gates=False))
    R["strobe_no_diodes"] = {k: st_ng[k] for k in ("v(pa0)", "v(pa8)", "v(pa15)")}
    R["strobe_no_diodes_arrival_15_ps"] = (st_ng["v(pa15)"]["t_peak"] - st_ng["v(pa0)"]["t_peak"]) * 1e12
    ref = [reference_gate(v) for v in (2.0, 1.5)] + [reference_gate(2.0, cin=6e-12)]
    R["reference_gate"] = ref
    print(json.dumps(R, indent=0)[:3000], flush=True)
    # line delay calibration: where is the line 50 % at tap 0 for x = 0
    t, w = D.sim(D.A(x=0, tstop=1.5e-9), tp0, ["v(s0)", "v(s15)"])
    k = t > D.T_ST
    lo, hi = -0.21, 0.21
    t50_0 = wv.crossing(t[k], (w["v(s0)"][k] - w["v(s0)"][k][0]) / (w["v(s0)"][k][-1] - w["v(s0)"][k][0]), 0.5)
    R["edge_x0_actual_ps"] = (t50_0 - tp0) * 1e12
    print("edge at tap0 for x=0:", R["edge_x0_actual_ps"], flush=True)

    # ---------- (2) sweeps
    xs = np.arange(-850e-12, 300.1e-12, 25e-12)
    cases = {"co, Cin 3 pF": nom, "co, Cin 6 pF": dataclasses.replace(nom, cin=6e-12),
             "co, launch x1.3": dataclasses.replace(nom, scale=1.3),
             "counter 30+30 ps (60 ps taps)": dataclasses.replace(nom, counter=True, td_sig=30e-12, td_s=20e-12, z_s=73.0)}
    sweeps = {}
    with Pool(3) as pool:
        for name, p in cases.items():
            if p.counter:
                pc = p
                _, _, stc = strobe_only(pc)
                tpc = stc["v(pa15)"]["t_peak"]          # strobe peak at tap 15 (launch end)
                xsc = np.arange(-800e-12, 800.1e-12, 25e-12)
                # x is relative to the strobe peak at the launch tap (15); keep the deck's tap-0 reference
                res = pool.map(sweep_job, [(dataclasses.replace(pc, x=float(x)), tpc) for x in xsc])
                R["counter_strobe"] = {k: stc[k] for k in ("v(pa0)", "v(pa8)", "v(pa15)")}
                xx = xsc
            else:
                res = pool.map(sweep_job, [(dataclasses.replace(p, x=float(x)), tp0) for x in xs])
                xx = xs
            V = np.array([r[T_CAP] for r in res])
            ft = fit_taps(xx, V)
            pos = np.array([q["pos_ps"] for q in ft]) * 1e-12
            half = np.array([(q["hi_mV"] - q["lo_mV"]) / 2e3 for q in ft])
            wid = float(np.median([q["w1090_ps"] for q in ft])) * 1e-12
            o = np.argsort(pos)
            sp = np.diff(pos[o]) * 1e12
            rms = tdc(pos, half, wid)
            sweeps[name] = dict(x=xx.tolist(), V=V.tolist(), taps=ft, spacing_ps=sp.round(1).tolist(),
                                spacing_mean=float(sp.mean()), spacing_sd=float(sp.std()), spacing_min=float(sp.min()),
                                spacing_max=float(sp.max()), half_min_mV=float(half.min() * 1e3), half_max_mV=float(half.max() * 1e3),
                                w1090_ps=wid * 1e12, rms_ps=rms,
                                rms_ps_off6p5=tdc(pos, half, wid, off=6.5e-3))
            print(name, {k: v for k, v in sweeps[name].items() if k not in ("x", "V", "taps")}, flush=True)
    R["sweeps"] = {k: {kk: vv for kk, vv in v.items() if kk not in ("x", "V")} for k, v in sweeps.items()}

    # ---------- (3) wrong-polarity pulse at the taps, latch timing
    lc = {"50 % duty": dataclasses.replace(nom, reverse=True, tstop=19e-9),
          "50 % duty, no reverse edge (reference)": dataclasses.replace(nom, reverse=False, tstop=19e-9),
          "50 % duty + BAT15 clamp at launch": dataclasses.replace(nom, reverse=True, clamp=True, tstop=19e-9),
          "70 % duty (reverse at +14 ns)": dataclasses.replace(nom, reverse=True, duty=0.7, tstop=19e-9)}
    longs = {}
    with Pool(3) as pool:
        for xe, tag in ((-700e-12, "edge before all taps"), (200e-12, "edge after all taps"), (-260e-12, "edge mid-array")):
            rr = pool.map(long_job, [(dataclasses.replace(p, x=xe), tp0) for p in lc.values()])
            longs[tag] = dict(zip(lc.keys(), rr))
    rev = {}
    for tag, d in longs.items():
        tref, wref = d["50 % duty, no reverse edge (reference)"]
        for name, (t, w) in d.items():
            e = {}
            for i in (0, 8, 15):
                vo = w[f"v(o{i})"]; vr = np.interp(t, tref, wref[f"v(o{i})"])
                for lt in (9e-9, 10.5e-9, 12e-9, 14e-9):
                    e[f"o{i}_dmV_at_{lt * 1e9:g}ns"] = float((np.interp(tp0 + lt, t, vo) - np.interp(tp0 + lt, t, vr)) * 1e3)
                e[f"o{i}_mV_at_5ns"] = float(np.interp(tp0 + 5e-9, t, vo) * 1e3)
                e[f"o{i}_maxdev_mV"] = float(np.abs(vo - vr)[t > tp0 + 8e-9].max() * 1e3)
                e[f"rev_d1_{i}"] = float(w[f"v(s{i},a{i})"].max()); e[f"rev_d2_{i}"] = float(w[f"v(k{i},s{i})"].max())
            k = t < tp0 + 1e-9
            e["pa0_peak"] = float(w["v(pa0)"][k].max()); e["pa0_min_late"] = float(w["v(pa0)"][t > tp0 + 5e-9].min())
            rev[f"{tag} | {name}"] = e
    R["reverse"] = rev
    for k, v in rev.items():
        print(k, {kk: round(vv, 2) for kk, vv in v.items() if "rev" in kk or "maxdev" in kk or "pa0" in kk or "12ns" in kk})
    # clamp effect on the wanted pulse along the line
    _, _, stcl = strobe_only(dataclasses.replace(nom, clamp=True))
    R["strobe_with_clamp"] = {k: stcl[k] for k in ("v(pa0)", "v(pa8)", "v(pa15)", "v(pk15)")}

    # ---------- (4) signal line: return loss and edge at tap 15
    rl = ret_loss()
    R["return_loss_dB"] = {k: {f"{fr / 1e9:g}GHz": float(np.interp(fr, v[0], v[1])) for fr in (0.5e9, 1e9, 2e9, 3e9, 4e9, 6e9)} for k, v in rl.items()}
    t, w = D.sim(D.A(x=0, tstop=2.5e-9, reverse=False), tp0, ["v(s0)", "v(s8)", "v(s15)"])
    ed = {}
    for n in ("v(s0)", "v(s8)", "v(s15)"):
        v = w[n]; k = t > D.T_ST
        lo_, hi_ = v[k][0], np.median(v[t > t[-1] - 0.3e-9])
        x = (v[k] - lo_) / (hi_ - lo_)
        ed[n] = dict(t1090_ps=(wv.crossing(t[k], x, 0.9) - wv.crossing(t[k], x, 0.1)) * 1e12,
                     t50_ps=wv.crossing(t[k], x, 0.5) * 1e12, overshoot=float(x.max() - 1), step=float(hi_ - lo_))
    R["signal_edge"] = ed
    R["sig_tap_delay_ps"] = (ed["v(s15)"]["t50_ps"] - ed["v(s0)"]["t50_ps"]) / 15
    print(R["return_loss_dB"], ed, flush=True)
    json.dump(R, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=float)

    # ---------- plots
    fig, ax = plt.subplots(1, 3, figsize=(17, 5))
    for n, col in (("v(pa0)", "C0"), ("v(pa8)", "C1"), ("v(pa15)", "C2")):
        ax[0].plot((t1 - tp0) * 1e12, w1[n], color=col, label=f"PSTRB_A {n[4:-1].replace('a', 'tap ')}: {st[n]['peak']:.2f} V, {st[n]['fwhm_ps']:.0f} ps")
        ax[0].plot((t1 - tp0) * 1e12, w1[n.replace("pa", "pk")], color=col, ls="--")
    ax[0].set(xlim=(-300, 1000), xlabel="ps after peak at tap 0", ylabel="V on the strobe line at the gate",
              title="Loaded strobe lines (A solid, K dashed)"); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3)
    ax[1].plot(range(N), arr * 1e12, "o-", label="strobe peak arrival")
    for name, s in sweeps.items():
        pos = np.array([q["pos_ps"] for q in s["taps"]])
        ax[1].plot(range(N), pos - pos[0], "x--", label=f"effective tap position: {name}")
    ax[1].set(xlabel="tap", ylabel="ps", title="Strobe arrival and effective tap positions"); ax[1].legend(fontsize=7); ax[1].grid(alpha=.3)
    for name, s in sweeps.items():
        ax[2].plot(range(N - 1), s["spacing_ps"], "o-", label=f"{name}: {s['spacing_mean']:.1f} +/- {s['spacing_sd']:.1f} ps")
    ax[2].set(xlabel="tap pair (sorted)", ylabel="ps", title="Tap-to-tap effective spacing"); ax[2].legend(fontsize=7); ax[2].grid(alpha=.3)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "strobe_spacing.png"), dpi=95)

    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
    for a_, name in zip(ax, ("co, Cin 3 pF", "co, Cin 6 pF")):
        s = sweeps[name]; V = np.array(s["V"]) * 1e3
        cm = plt.get_cmap("viridis")
        for i in range(N):
            a_.plot(np.array(s["x"]) * 1e12, V[:, i], color=cm(i / 15), lw=1.2, label=f"tap {i}" if i % 3 == 0 or i == 15 else None)
        a_.set(xlabel="signal edge at tap 0 minus strobe peak at tap 0, ps", ylabel="comparator input at strobe + 3 ns, mV",
               title=f"{name}: captured value, line -0.25 -> +0.25 V (rms {s["rms_ps"] * 1e12:.0f} ps)")
        a_.grid(alpha=.3); a_.legend(fontsize=7, ncol=2)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "capture.png"), dpi=95)

    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
    d = longs["edge before all taps"]
    for (name, (t, w)), col in zip(d.items(), ("C0", "k", "C2", "C3")):
        ax[0].plot((t - tp0) * 1e9, w["v(o0)"] * 1e3, color=col, lw=1, label=f"tap 0, {name}")
        ax[0].plot((t - tp0) * 1e9, w["v(o15)"] * 1e3, color=col, lw=1, ls="--")
        ax[1].plot((t - tp0) * 1e9, np.maximum(w["v(s0,a0)"], w["v(k0,s0)"]), color=col, lw=1, label=name)
    for a_ in ax:
        a_.axvline(12, color="r", lw=0.8); a_.grid(alpha=.3); a_.set_xlabel("ns after strobe peak at tap 0")
    ax[0].set(ylabel="mV", title="Comparator input, tap 0 (solid) / 15 (dashed); latch at +12 ns (red)"); ax[0].legend(fontsize=8)
    ax[1].set(ylabel="V", title="Reverse voltage on tap-0 diodes (BAT15 BV 4 V)"); ax[1].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "reverse.png"), dpi=95)
