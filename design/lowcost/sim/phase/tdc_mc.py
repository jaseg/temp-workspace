"""(c) Single-shot rms of the 16-tap snapshot, reusing sim/snapshot_tdc.run (code-density calibrated).
Half-swing about the (polarity-specific) threshold from feedthrough.py / neutralise.py at 2-3 ns:
Cin 3 pF: +32 mV (edge passed) vs -1.4 mV (edge arrives after the strobe) -> +/-17 mV about +15 mV;
Cin 6 pF: +20 vs -0.1 -> +/-10 mV. Line edge 10-90 240 ps (line_drive.py), taps 35 ps.
Offsets: comparator 6.5 mV max -> sigma 2.2 mV, gate/pedestal mismatch 3 mV, residue 1.6 mV, noise 1 mV.
  python3 tdc_mc.py
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../sim"))
import snapshot_tdc as s

HERE = os.path.dirname(os.path.abspath(__file__))
rows = []
for label, half, off, rise in [
        ("Cin 3 pF, nominal", 17e-3, np.hypot(2.2e-3, 3e-3), 240e-12),
        ("Cin 6 pF, nominal", 10e-3, np.hypot(2.2e-3, 3e-3), 240e-12),
        ("Cin 3 pF, offsets 6.5 mV rms (all at max)", 17e-3, 6.5e-3, 240e-12),
        ("Cin 6 pF, offsets 6.5 mV rms", 10e-3, 6.5e-3, 240e-12),
        ("Cin 3 pF, edge 300 ps", 17e-3, np.hypot(2.2e-3, 3e-3), 300e-12),
        ("Cin 3 pF, amplitude -30 % vs calibration", 17e-3 * 0.7, np.hypot(2.2e-3, 3e-3), 240e-12)]:
    kw = dict(n=16, step=35e-12, a=1.0, k_gate=half, rise=rise, off=off, noise=np.hypot(1e-3, 1.6e-3), chips=20, ev=4000)
    if "-30 %" in label:
        kw["cal_a"] = 1 / 0.7
    e, v = s.run(**kw)
    rows.append(dict(case=label, rms_ps=e * 1e12, usable=v))
    print("%-45s %5.1f ps rms, usable taps %3.0f %%" % (label, e * 1e12, v * 100))
json.dump(rows, open(os.path.join(HERE, "tdc_mc.json"), "w"), indent=1)
