"""Monte Carlo of clock recovery in software from time-stamped data edges.

Idea (see ../docs/scope-frontend.md): the strobe free-runs on the FPGA clock. The data
stream is squared up, its rising edges are divided down by a fast prescaler, and the
FPGA input-delay TDC time-stamps every divided edge. Those edges all sit on the bit
grid, so a phase-locked loop in software recovers the bit clock, and every sample gets
a position within the unit interval.

Compared: a causal second-order loop of natural frequency fn, and a non-causal
(zero-phase) quadratic fit over a sliding window, which is possible because the
record is processed after acquisition.

  python3 sw_cdr.py
"""
import numpy as np

rng = np.random.default_rng(2)


def edges(baud, n, presc=16, ssc_ppm=0.0, ssc_f=33e3, src_jit=3e-12):
    """True times of the divided rising edges, and their bit indices."""
    gaps = rng.negative_binomial(presc, 0.25, n) + presc      # bits between divided edges (rising edge every 4 bits on average)
    k = np.cumsum(gaps).astype(float)
    t = k / baud
    if ssc_ppm:
        # down-spread triangular modulation: f(t) = baud * (1 - d * tri(t)), tri = 0..1..0 once per period
        d = ssc_ppm * 1e-6
        for _ in range(6):
            x = (t * ssc_f) % 1.0
            tri_int = (np.floor(t * ssc_f) * 0.5 + np.where(x < 0.5, x * x, 2 * x - x * x - 0.5)) / ssc_f
            t = (k + d * baud * tri_int) / baud
    return t + rng.normal(0, src_jit, n), k


def causal(m, t_true, k, baud, fn, zeta=0.707):
    dt_mean = np.mean(np.diff(m))
    wn = 2 * np.pi * fn
    a, b = 2 * zeta * wn * dt_mean, (wn * dt_mean) ** 2
    th, f = k[0], baud
    err = np.empty(len(m))
    err[0] = 0
    for i in range(1, len(m)):
        pred_true = th + f * (t_true[i] - m[i - 1])     # loop's phase at the true edge time
        err[i] = pred_true - k[i]
        pred = th + f * (m[i] - m[i - 1])
        e = np.round(pred) - pred
        th = pred + a * e
        f += b * e / dt_mean
    q = err[len(err) // 4:]
    return np.std(q - np.round(q)) / baud


def noncausal(m, t_true, k, baud, win, order=2):
    """Local quadratic fit of bit index against measured time; error of the fit at the true time."""
    h = win // 2
    idx = np.arange(h, len(m) - h, max(1, win // 4))
    err = []
    for i in idx:
        s = slice(i - h, i + h + 1)
        c = np.polyfit((m[s] - m[i]) * baud, k[s] - k[i], order)
        err.append(np.polyval(c, (t_true[i] - m[i]) * baud))
    return np.std(err) / baud


if __name__ == "__main__":
    baud, tdc = 1.25e9, 31e-12
    print(f"data rate {baud / 1e9} Gbps, prescaler 16, TDC {tdc * 1e12:.0f} ps rms per edge, source jitter 3 ps rms")
    for ssc in (0.0, 5000.0):
        t, k = edges(baud, 120000, ssc_ppm=ssc)
        m = t + rng.normal(0, tdc, len(t))
        print(f"\nspread spectrum {ssc:.0f} ppm; divided edge rate {1 / np.mean(np.diff(t)) / 1e6:.1f} MHz")
        for fn in (30e3, 100e3, 300e3, 1e6):
            print(f"  causal loop, fn {fn / 1e3:5.0f} kHz: recovered-clock error {causal(m, t, k, baud, fn) * 1e12:6.1f} ps rms")
        for win in (17, 33, 65, 101, 301):
            print(f"  zero-phase fit over {win:4d} edges ({win * np.mean(np.diff(t)) * 1e6:5.1f} us): {noncausal(m, t, k, baud, win) * 1e12:6.1f} ps rms")
