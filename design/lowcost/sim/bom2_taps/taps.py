"""BOM-2 tap-capacitor study on the as-built array (deck_ab.py).
(1) survey: coupling ("hold") capacitor cc x hold-node capacitance c_node -> strobe arrival per tap, captured value
    (edge passed / not yet arrived), feed-through (edge arriving after the strobe vs no edge), droop to the latch
    (+5 / +8 / +12 ns), tap-to-tap spread
(2) full edge sweeps (tap positions, spacing, single-shot rms with sim/phase_array/run.py's estimator) for the
    as-built nominal and the candidates.
python3 taps.py [survey|sweep|all]  -> survey.json / sweep.json, taps.png   (about 15-25 min, 4 processes)"""
import dataclasses, json, os, sys
from multiprocessing import Pool
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deck_ab as A  # noqa: E402
sys.path.insert(0, os.path.join(HERE, "..", "phase_array"))
import run as RN  # noqa: E402  (fit_taps, tdc, pulse_stats; not edited)

N = A.N
OV = [f"v(o{i})" for i in range(N)]
PA = [f"v(pa{i})" for i in range(N)]
TREAD = (1e-9, 3e-9, 5e-9, 8e-9, 12e-9)


def strobe_job(p):
    t, w = A.sim_ab(dataclasses.replace(p, signal=False, tstop=2e-9), A.D.T_ST + 0.7e-9, PA + ["v(a0)", "v(a15)"])
    st = {n: RN.pulse_stats(t, w[n]) for n in PA}
    return st, float(w["v(a0)"].max()), float(w["v(a15)"].max())


def read_job(args):
    p, tp0 = args
    t, w = A.sim_ab(p, tp0, OV)
    return {f"{dt*1e9:g}": [float(np.interp(tp0 + dt, t, w[o])) for o in OV] for dt in TREAD}


def survey(pool):
    cases = []
    for cn in (0.40e-12, 0.12e-12):
        for cc in (0.03e-12, 0.1e-12, 0.2e-12, 0.3e-12, 0.5e-12, 0.8e-12):
            cases.append((f"cc {cc*1e12:.2f} pF, c_node {cn*1e12:.2f} pF", A.AB(cc=cc, c_node=cn, tstop=13e-9)))
    cases.append(("original deck values (0.47 pF, c_node 0)", A.AB(cc=0.47e-12, c_node=0.0, tstop=13e-9)))
    sts = pool.map(strobe_job, [p for _, p in cases])
    jobs = []
    for (name, p), (st, _, _) in zip(cases, sts):
        tp0 = st["v(pa0)"]["t_peak"]
        jobs += [(dataclasses.replace(p, x=-900e-12), tp0), (dataclasses.replace(p, x=+300e-12), tp0),
                 (dataclasses.replace(p, signal=False), tp0)]
    rr = pool.map(read_job, jobs)
    out = {}
    for k, ((name, p), (st, a0, a15)) in enumerate(zip(cases, sts)):
        hi, lo, idle = rr[3 * k], rr[3 * k + 1], rr[3 * k + 2]
        arr = np.array([st[n]["t_peak"] for n in PA]); arr -= arr[0]
        r = dict(cc_pF=p.cc * 1e12, c_node_pF=p.c_node * 1e12,
                 strobe_tap0_V=st["v(pa0)"]["peak"], strobe_tap15_V=st["v(pa15)"]["peak"],
                 strobe_ps_per_tap=float(arr[-1] / 15 * 1e12), node_a0_peak_V=a0, node_a15_peak_V=a15)
        for dt in ("1", "3", "5", "8", "12"):
            h, l, i0 = (np.array(x[dt]) * 1e3 for x in (hi, lo, idle))
            sw = h - l
            r[f"t{dt}ns"] = dict(passed_mV=h.round(1).tolist(), not_arrived_mV=l.round(1).tolist(),
                                swing_min_mV=float(sw.min()), swing_mean_mV=float(sw.mean()), swing_max_mV=float(sw.max()),
                                mid_mean_mV=float(((h + l) / 2).mean()), mid_spread_mV=float(np.ptp((h + l) / 2)),
                                feedthrough_mean_mV=float((l - i0).mean()))
        s3, s12 = np.array(hi["3"]) - np.array(lo["3"]), np.array(hi["12"]) - np.array(lo["12"])
        r["droop_3_to_12ns_pct"] = float(100 * np.mean(1 - s12 / s3))
        out[name] = r
        print(name, {kk: (round(v, 3) if isinstance(v, float) else v) for kk, v in r.items() if not kk.startswith("t")},
              "swing3 min/mean", round(r["t3ns"]["swing_min_mV"], 1), round(r["t3ns"]["swing_mean_mV"], 1),
              "mid", round(r["t3ns"]["mid_mean_mV"], 1), "ft", round(r["t3ns"]["feedthrough_mean_mV"], 1),
              "swing12 min", round(r["t12ns"]["swing_min_mV"], 1), flush=True)
    return out


def sweep(pool, cases):
    xs = np.arange(-900e-12, 300.1e-12, 25e-12)
    out = {}
    for name, p in cases.items():
        st, _, _ = strobe_job(p)
        tp0 = st["v(pa0)"]["t_peak"]
        rr = pool.map(read_job, [(dataclasses.replace(p, x=float(x), tstop=4e-9), tp0) for x in xs])
        V = np.array([r["3"] for r in rr])
        ft = RN.fit_taps(xs, V)
        pos = np.array([q["pos_ps"] for q in ft]) * 1e-12
        half = np.array([(q["hi_mV"] - q["lo_mV"]) / 2e3 for q in ft])
        wid = float(np.median([q["w1090_ps"] for q in ft])) * 1e-12
        sp = np.diff(np.sort(pos)) * 1e12
        def rms(**kw):
            try:
                return RN.tdc(pos, half, wid, **kw) * 1e12
            except ValueError:            # no usable captures (taps never switch)
                return float("nan")
        out[name] = dict(taps=ft, spacing_ps=sp.round(1).tolist(), spacing_mean=float(sp.mean()), spacing_sd=float(sp.std()),
                         spacing_min=float(sp.min()), spacing_max=float(sp.max()), window_ps=float((pos.max() - pos.min()) * 1e12),
                         half_min_mV=float(half.min() * 1e3), half_max_mV=float(half.max() * 1e3), w1090_ps=wid * 1e12,
                         rms_ps=rms(), rms_ps_off6p5=rms(off=6.5e-3),
                         x=xs.tolist(), V=V.tolist())
        print(name, {k: (round(v, 2) if isinstance(v, float) else v) for k, v in out[name].items() if k not in ("taps", "x", "V")}, flush=True)
    return out


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    with Pool(4) as pool:
        if what in ("survey", "all"):
            json.dump(survey(pool), open(os.path.join(HERE, "survey.json"), "w"), indent=1)
        if what in ("sweep", "all"):
            cases = {"as built: 0.5 pF part, c_node 0.40 pF": A.AB(cc=0.5e-12, c_node=0.40e-12),
                     "0.5 pF, L2 cut enlarged (c_node 0.12 pF)": A.AB(cc=0.5e-12, c_node=0.12e-12),
                     "printed 0.5 pF (L1 patch / L2 island), cut enlarged, c_node 0.12 pF": A.AB(cc=0.5e-12, c_node=0.12e-12, pad_s=0.16e-12),
                     "FH -0.25 pF corner: 0.25 pF, c_node 0.40": A.AB(cc=0.25e-12, c_node=0.40e-12),
                     "printed -15 % (0.43 pF), c_node 0.12": A.AB(cc=0.43e-12, c_node=0.12e-12, pad_s=0.16e-12),
                     "printed +15 % (0.58 pF), c_node 0.12": A.AB(cc=0.58e-12, c_node=0.12e-12, pad_s=0.16e-12),
                     "Murata W -0.05 pF corner: 0.45 pF, c_node 0.40": A.AB(cc=0.45e-12, c_node=0.40e-12),
                     "DNP (0.03 pF pad pair), c_node 0.40": A.AB(cc=0.03e-12, c_node=0.40e-12)}
            sw = sweep(pool, cases)
            json.dump({k: {kk: vv for kk, vv in v.items() if kk not in ("x", "V")} for k, v in sw.items()},
                      open(os.path.join(HERE, "sweep.json"), "w"), indent=1)
            fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
            cm = plt.get_cmap("viridis")
            for a_, name in zip(ax, list(cases)[:2]):
                s = sw[name]; V = np.array(s["V"]) * 1e3
                for i in range(N):
                    a_.plot(np.array(s["x"]) * 1e12, V[:, i], color=cm(i / 15), lw=1.1, label=f"tap {i}" if i % 3 == 0 or i == 15 else None)
                a_.set(xlabel="signal edge at tap 0 minus strobe peak at tap 0, ps", ylabel="comparator input at strobe + 3 ns, mV",
                       title=f"{name}\nrms {s['rms_ps']:.0f} ps, spacing {s['spacing_mean']:.1f} +/- {s['spacing_sd']:.1f} ps")
                a_.grid(alpha=.3); a_.legend(fontsize=7, ncol=2)
            fig.tight_layout(); fig.savefig(os.path.join(HERE, "taps.png"), dpi=90)
