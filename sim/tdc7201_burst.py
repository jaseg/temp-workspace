"""TDC7201 on fast data with spread spectrum: treat every burst of stamps on its own.

tdc7201_track.py shows that stamps cannot be stitched across the gaps between
measurements (the frequency moves by thousands of ppm in a few microseconds and turns
around twice per modulation period). Here each burst is solved alone:
  - one measurement gives `stamps` divided data edges within a 2 us window
    (5 with one converter, 10 with both converters of a TDC7201 started together on
     two differently divided edge streams)
  - the bit rate and its slope during the burst are found by a search for the pair that
    puts all stamps on the bit grid; then a quadratic fit gives the bit phase
  - only scope samples whose strobe falls inside the burst window are used

  python3 tdc7201_burst.py
"""
import numpy as np

import sw_cdr as c

rng = np.random.default_rng(7)
C0 = 0.005 * 2 * 33e3          # relative frequency slope of 5000 ppm triangular spread spectrum, 1/s


def burst_solve(tm, baud, tdc_grid=8e-6):
    """Find bit indices (relative to the first stamp) for the stamps of one burst."""
    dt = tm - tm[0]
    fr = np.arange(-0.0058, 0.0008, tdc_grid)            # relative frequency offsets searched
    best = (1e9, None)
    for ch in np.linspace(-1.3 * C0, 1.3 * C0, 27):
        ph = baud * ((1 + fr[:, None]) * dt[None, :] + 0.5 * ch * dt[None, :] ** 2)
        res = ph - np.round(ph)
        sc = (res ** 2).sum(1)
        j = int(np.argmin(sc))
        if sc[j] < best[0]:
            best = (sc[j], np.round(ph[j]))
    return best[1]


def simulate(baud, div, stamps, tdc=35e-12, ssc=5000.0, n_burst=400, period=12e-6, seed=3):
    c.rng = np.random.default_rng(seed)
    n = int(n_burst * period * baud / (4 * div) * 1.05) + 500
    t, k = c.edges(baud, n, presc=div, ssc_ppm=ssc)
    wrong = used = 0
    err, span = [], []
    for b in range(2, n_burst - 2):
        tb = b * period
        i0 = np.searchsorted(t, tb)
        if stamps <= 5:
            idx = np.arange(i0, i0 + stamps)
        else:                                            # second converter: every other divided edge of a 2x faster stream
            idx = np.arange(i0, i0 + stamps)
        idx = idx[t[idx] - tb < 2e-6]
        if len(idx) < 4:
            continue
        tm = t[idx] + rng.normal(0, tdc, len(idx))
        ka = burst_solve(tm, baud)
        kt = k[idx] - k[idx[0]]
        used += 1
        if not np.array_equal(ka, kt):
            wrong += 1
            continue
        x = (tm - tm.mean()) * baud
        p = np.polyfit(x, ka, 2)
        for tq in rng.uniform(tm[0], tm[-1], 6):         # strobes inside the burst
            kq = np.interp(tq, t, k) - k[idx[0]]
            err.append(np.polyval(p, (tq - tm.mean()) * baud) - kq)
        span.append(tm[-1] - tm[0])
    return wrong, used, np.std(err) / baud, np.mean(span), np.mean(span) / period


if __name__ == "__main__":
    print("%-52s %16s %12s %10s %14s" % ("case", "bursts unsolved", "clock error", "burst", "strobes usable"))
    for label, kw in [
        ("1.25 Gbps, /64, 5 stamps (one converter)", dict(baud=1.25e9, div=64, stamps=5)),
        ("1.25 Gbps, /32, 10 stamps (both converters)", dict(baud=1.25e9, div=32, stamps=10)),
        ("1.25 Gbps, /32, 10 stamps, cycle 20 us", dict(baud=1.25e9, div=32, stamps=10, period=20e-6)),
        ("3 Gbps, /128, 5 stamps", dict(baud=3e9, div=128, stamps=5)),
        ("3 Gbps, /64, 10 stamps", dict(baud=3e9, div=64, stamps=10)),
        ("0.5 Gbps, /16, 10 stamps", dict(baud=0.5e9, div=16, stamps=10)),
        ("1.25 Gbps, /32, 10 stamps, no spread spectrum", dict(baud=1.25e9, div=32, stamps=10, ssc=0.0)),
    ]:
        w_, u, e, sp, frac = simulate(**kw)
        print("%-52s %7d of %4d %9.1f ps %7.2f us %11.0f %%" % (label, w_, u, e * 1e12, sp * 1e6, frac * 100))
