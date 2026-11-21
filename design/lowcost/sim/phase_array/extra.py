"""Follow-ups to run.py: 80 ps launch stub (larger peak, no extra amplifier) and the clean signal edge
along the line (strobes idle).  python3 extra.py -> extra.json"""
import dataclasses, json, os
from multiprocessing import Pool
import numpy as np
import deck as D, run as R, wave as wv

if __name__ == "__main__":
    out = {}
    p = dataclasses.replace(D.A(), stub_td=80e-12)
    _, _, st = R.strobe_only(p)
    tp0 = st["v(pa0)"]["t_peak"]
    out["stub80_strobe"] = {k: st[k] for k in ("v(pa0)", "v(pa8)", "v(pa15)", "v(pk15)")}
    xs = np.arange(-900e-12, 300.1e-12, 25e-12)
    with Pool(3) as pool:
        res = pool.map(R.sweep_job, [(dataclasses.replace(p, x=float(x)), tp0) for x in xs])
    V = np.array([r[R.T_CAP] for r in res]); ft = R.fit_taps(xs, V)
    pos = np.array([q["pos_ps"] for q in ft]) * 1e-12; half = np.array([(q["hi_mV"] - q["lo_mV"]) / 2e3 for q in ft])
    wid = float(np.median([q["w1090_ps"] for q in ft])) * 1e-12
    sp = np.diff(np.sort(pos)) * 1e12
    out["stub80_sweep"] = dict(taps=ft, spacing_ps=sp.round(1).tolist(), spacing_mean=float(sp.mean()), spacing_sd=float(sp.std()),
                               half_min_mV=float(half.min() * 1e3), rms_ps=R.tdc(pos, half, wid), rms_off6p5=R.tdc(pos, half, wid, off=6.5e-3))
    t, w = D.sim(D.A(x=0, scale=1e-6, tstop=4e-9), tp0, ["v(s0)", "v(s8)", "v(s15)"])
    ed = {}
    for n, tarr in (("v(s0)", 0), ("v(s8)", 8), ("v(s15)", 15)):
        v = w[n]; k = t > D.T_ST
        lo, hi = v[k][0], np.median(v[t > t[-1] - 0.5e-9])
        x = (v[k] - lo) / (hi - lo)
        ed[n] = dict(t1090_ps=(wv.crossing(t[k], x, 0.9) - wv.crossing(t[k], x, 0.1)) * 1e12, t50_ps=wv.crossing(t[k], x, 0.5) * 1e12,
                     overshoot=float(x.max() - 1), step=float(hi - lo))
    ed["tap_delay_ps"] = (ed["v(s15)"]["t50_ps"] - ed["v(s0)"]["t50_ps"]) / 15
    out["signal_edge_clean"] = ed
    print(json.dumps({k: v for k, v in out.items() if k != "stub80_sweep"}, indent=0))
    print({k: v for k, v in out["stub80_sweep"].items() if k != "taps"}, [round(q["hi_mV"] - q["lo_mV"]) for q in ft])
    json.dump(out, open(os.path.join(D.HERE, "extra.json"), "w"), indent=1, default=float)
