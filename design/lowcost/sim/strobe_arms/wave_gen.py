"""Strobe source for the arm study: 2xTRF chain, FPGA 600 ps, 50 % duty, nominal split (sim/strobe/chain.py,
used read-only), scaled to the 4.30 V step of the AC-coupled chain with 47 uH chokes (sim/strobe/extras.json).
Writes strobe_wave.json (t, v into 50 R)."""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "strobe"))
import chain  # noqa: E402

r = chain.edge(chain.CHAINS["2xTRF"], tr=600e-12, duty=0.5, split="nominal", tstop=5e-9)
a, m, b, lo, hi = chain.t1090(r["t"], r["v(out)"])
s = 4.30 / (hi - lo)
t = r["t"]; v = (r["v(out)"] - lo) * s
k = (t > m - 0.6e-9) & (t < m + 1.6e-9)
tt = np.arange(t[k][0], t[k][-1], 2e-12)
json.dump(dict(t=(tt - m).tolist(), v=np.interp(tt, t, v).tolist(), tr_ps=(b - a) * 1e12, step=4.30), open(os.path.join(HERE, "strobe_wave.json"), "w"))
print("edge %.0f ps, step %.2f V (scale %.3f)" % ((b - a) * 1e12, hi - lo, s))
