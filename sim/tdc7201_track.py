"""Can a TDC7201 follow the bit clock of fast data, including spread spectrum, from bursts
of time stamps? (see ../docs/scope-frontend.md)

Front end assumed: data squared up and divided so that divided edges are at least 67 ns
apart (the TDC7201's minimum stop-to-stop time). One measurement: START is an FPGA clock
edge, the next `stops` divided edges are the STOPs (up to 5 per converter, within 2 us).
A measurement cycle (window, calibration, SPI read) takes `cycle` seconds; with both
converters of the TDC7201 interleaved a burst starts every cycle/2.

Each divided edge lies on the bit grid but the number of bits between edges is unknown
(it depends on the data), so a tracker has to assign each stamp its bit index. Tracker:
quadratic fit of bit index against time over the last few bursts, extrapolated to the
new stamp and rounded. A wrong index is a cycle slip.

  python3 tdc7201_track.py
"""
import numpy as np

import sw_cdr as c

rng = np.random.default_rng(5)


def simulate(baud, div, cycle, converters, stops=5, tdc=35e-12, ssc=5000.0, hist=15, t_total=3e-3, seed=1):
    c.rng = np.random.default_rng(seed)
    n = int(t_total * baud / (4 * div) * 1.02) + 200
    t, k = c.edges(baud, n, presc=div, ssc_ppm=ssc)
    period = cycle / converters
    idx = []
    tb = 5e-6
    while tb < t[-1] - 5e-6:
        i0 = np.searchsorted(t, tb)
        sel = [i for i in range(i0, i0 + stops) if t[i] - tb < 2e-6]     # mode 1 range
        idx += sel
        tb += period
    idx = np.array(idx)
    tm = t[idx] + rng.normal(0, tdc, len(idx))
    kt = k[idx]
    # tracker: start with the first `hist` indices known (acquisition is a separate problem)
    ka = kt.copy()
    slips = 0
    for i in range(hist, len(idx)):
        s = slice(i - hist, i)
        x = (tm[s] - tm[i - 1]) * baud
        p = np.polyfit(x, ka[s] - ka[i - 1], 2)
        pred = ka[i - 1] + np.polyval(p, (tm[i] - tm[i - 1]) * baud)
        ka[i] = np.round(pred)
        if ka[i] != kt[i]:
            slips += 1
            ka[i] = kt[i]                      # count the slip, then carry on from the truth
    # accuracy of the recovered clock at arbitrary times (zero-phase quadratic fit over neighbouring stamps)
    err = []
    for i in range(hist, len(idx) - hist, 7):
        s = slice(i - hist // 2, i + hist // 2 + 1)
        tq = tm[i] + rng.uniform(0, period)                     # a strobe somewhere before the next burst
        kq = np.interp(tq, t, k)                                # true (fractional) bit phase there
        p = np.polyfit((tm[s] - tm[i]) * baud, kt[s] - kt[i], 2)
        err.append(kt[i] + np.polyval(p, (tq - tm[i]) * baud) - kq)
    return slips, len(idx) - hist, np.std(err) / baud, len(idx) / t_total


if __name__ == "__main__":
    print("%-58s %12s %14s %12s" % ("case", "stamps/s", "cycle slips", "clock error"))
    for label, kw in [
        ("1.25 Gbps, /64, both converters, 5 stops, cycle 12 us", dict(baud=1.25e9, div=64, cycle=12e-6, converters=2)),
        ("1.25 Gbps, /64, one converter (TDC7200), cycle 12 us", dict(baud=1.25e9, div=64, cycle=12e-6, converters=1)),
        ("1.25 Gbps, /64, both, single stop per measurement", dict(baud=1.25e9, div=64, cycle=8e-6, converters=2, stops=1)),
        ("1.25 Gbps, no spread spectrum, one converter, 1 stop", dict(baud=1.25e9, div=64, cycle=8e-6, converters=1, stops=1, ssc=0.0)),
        ("3 Gbps, /128, both converters, 5 stops", dict(baud=3e9, div=128, cycle=12e-6, converters=2)),
        ("3 Gbps, /128, one converter", dict(baud=3e9, div=128, cycle=12e-6, converters=1)),
        ("0.5 Gbps, /16, both converters, 5 stops", dict(baud=0.5e9, div=16, cycle=12e-6, converters=2)),
    ]:
        s, n, e, rate = simulate(**kw)
        print("%-58s %9.0f k %6d of %5d %9.1f ps" % (label, rate / 1e3, s, n, e * 1e12))
