"""Falling-edge strobe source (the other edge of the 50 % S_STROBE square wave, half a period = 160 ns after the
sampling edge): same 2xTRF chain as wave_gen.py (sim/strobe/chain.py, used read-only) with the FPGA edge falling,
scaled with the SAME factor as the rising edge (so the AC-coupled chain's real asymmetry is kept).
Writes strobe_wave_fall.json (t, v into 50 R; v = 0 before the edge, negative after)."""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "strobe"))
import chain  # noqa: E402

r = chain.edge(chain.CHAINS["2xTRF"], tr=600e-12, duty=0.5, split="nominal", tstop=5e-9)
_, _, _, lo, hi = chain.t1090(r["t"], r["v(out)"])
s = 4.30 / (hi - lo)

d = chain.f.Deck()
d.add("* strobe chain, falling edge")
chain.fpga(d, 600e-12, 0.5, 1e-9, rising=False)
chain.chain(d, chain.CHAINS["2xTRF"], "fp", "out", "nominal")
d.add("Rload out 0 50")
q = chain.run_deck("\n".join(d.lines) + "\n", ["v(out)"], 5e-9)
t, v = q["t"], q["v(out)"]
a, m, b, lo2, hi2 = chain.t1090(t, v)
v = (v - lo2) * s
k = (t > m - 0.6e-9) & (t < m + 1.6e-9)
tt = np.arange(t[k][0], t[k][-1], 2e-12)
json.dump(dict(t=(tt - m).tolist(), v=np.interp(tt, t, v).tolist(), tr_ps=(b - a) * 1e12, step=(hi2 - lo2) * s),
          open(os.path.join(HERE, "strobe_wave_fall.json"), "w"))
print("rising: step 4.30 V (scale %.3f); falling: edge %.0f ps, step %.2f V" % (s, (b - a) * 1e12, (hi2 - lo2) * s))
