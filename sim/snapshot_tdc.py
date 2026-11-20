"""Monte Carlo of the delay-line snapshot TDC (see ../docs/scope-frontend.md).

N gates tap a delay line every `step` and are fired by the same strobe as the main
sampler. Each hold node feeds a 1-bit readout. An edge in the window shows up as the
position where the bits change.

Per tap:   held = k * A * edge(t_tap - T) + offset + noise      bit = held > 0
  k        0.375: single-shot gate efficiency 0.5 (tap_gate.py) times 0.75 left at readout
  A        half swing of the signal on the line
  edge     10-90 % rise = sqrt(signal rise^2 + gate aperture^2), aperture 70 ps
  offset   gate pedestal mismatch plus comparator offset, fixed per tap
  noise    per shot

A fixed offset moves a tap's effective position by offset/slope. A code-density
calibration finds the effective positions, but only for the amplitude and edge shape
it was made with.

  python3 snapshot_tdc.py
"""
import numpy as np
from scipy.special import erf

rng = np.random.default_rng(3)
K = 0.375


def run(n=16, step=60e-12, a=0.3, rise=150e-12, off=25e-3, noise=3e-3, tap_tol=3e-12, cal_a=None, chips=30, ev=6000, k_gate=K):
    sig = np.hypot(rise, 70e-12) / 2.563
    win = n * step
    errs, valid = [], []
    for _ in range(chips):
        taps = np.arange(n) * step + rng.normal(0, tap_tol, n)
        offs = rng.normal(0, off, n)

        def bits(T, amp):
            held = k_gate * amp * erf((taps[None, :] - T[:, None]) / (np.sqrt(2) * sig)) + offs[None, :] + rng.normal(0, noise, (len(T), n))
            return held > 0

        # calibration: edges uniform over a range wider than the window; P(bit=1) gives each tap's effective position
        Tc = rng.uniform(-step * 4, win + step * 4, 40000)
        p1 = bits(Tc, cal_a or a).mean(0)
        eff_pos = -step * 4 + (win + 8 * step) * p1          # P(T < pos) for uniform T
        stuck = (p1 < 0.02) | (p1 > 0.98)
        T = rng.uniform(step, win - step, ev)
        b = bits(T, a)
        order = np.argsort(eff_pos)
        good = ~stuck[order]
        pos = eff_pos[order][good]
        bb = b[:, order][:, good]
        k = bb.sum(1)                                        # taps reading "after the edge"
        edges = np.concatenate([[pos[0] - step], pos, [pos[-1] + step]])
        m = len(pos)
        est = (edges[m - k] + edges[m - k + 1]) / 2          # the edge lies between the last 0 tap and the first 1 tap
        ok = (k > 0) & (k < len(pos))
        e = (est - T)[ok]
        errs.append(e - np.median(e))
        valid.append(good.mean())
    e = np.concatenate(errs)
    return np.sqrt(np.mean(e ** 2)), np.mean(valid)


if __name__ == "__main__":
    rows = [
        ("limiter, +/-0.3 V on the line, 60 ps taps", dict()),
        ("limiter, 100 ps taps", dict(step=100e-12)),
        ("limiter, 50 ps taps", dict(step=50e-12)),
        ("limiter, 1-diode gates (offset 60 mV)", dict(off=60e-3)),
        ("limiter, travelling strobe line (gate swing 20 % -> k 0.15)", dict(k_gate=0.15, step=72e-12)),
        ("limiter, travelling strobe, +/-0.5 V on the line", dict(k_gate=0.15, step=72e-12, a=0.5)),
        ("limiter, travelling strobe, offsets 10 mV", dict(k_gate=0.15, step=72e-12, off=10e-3)),
        ("no limiter, +/-0.3 V signal", dict(rise=175e-12)),
        ("no limiter, +/-0.1 V signal", dict(a=0.1, rise=175e-12)),
        ("no limiter, +/-0.1 V, calibrated at +/-0.3 V", dict(a=0.1, rise=175e-12, cal_a=0.3)),
        ("no limiter, +/-0.03 V signal", dict(a=0.03, rise=175e-12)),
        ("no limiter, trimmed thresholds (2 mV), +/-0.1 V", dict(a=0.1, rise=175e-12, off=2e-3)),
        ("no limiter, trimmed thresholds (2 mV), +/-0.03 V", dict(a=0.03, rise=175e-12, off=2e-3)),
        ("no limiter, trimmed, +/-0.03 V, calibrated at +/-0.3 V", dict(a=0.03, rise=175e-12, off=2e-3, cal_a=0.3)),
    ]
    print("%-58s %10s %12s %14s" % ("case", "rms error", "usable taps", "scope rise"))
    for label, kw in rows:
        e, v = run(**kw)
        print("%-58s %7.0f ps %10.0f %% %11.0f ps" % (label, e * 1e12, v * 100, np.hypot(175, 2.563 * e * 1e12)))
