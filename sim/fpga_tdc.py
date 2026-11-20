"""Monte Carlo of a trigger-phase TDC built from GW1NZ input pins (see ../docs/scope-frontend.md).

The trigger is fanned out to N input pins. Each pin has an IODELAY set to a staggered
static code and feeds an IDES10 deserialiser at 1 Gbps (1 ns bins). The pins together
form a thermometer code that divides the 1 ns bin into N parts.

Assumptions (the datasheet gives only "30 ps typ" for the delay step and no PLL jitter):
  step        per-chip delay step, 30 ps +/- 20 % (unknown to the firmware)
  skew        pin-to-pin offset, 40 ps rms (routing, pad, comparator fan-out)
  jit         sampling jitter per pin and event, 10 ps rms
Calibration: a code-density test on triggers that are asynchronous to the FPGA clock
gives the true width of every bin, which removes step and skew errors.

  python3 fpga_tdc.py
"""
import numpy as np

rng = np.random.default_rng(1)
BIN = 1000.0   # ps, IDES10 at 1 Gbps
SYS = 175.0    # ps, 10-90 % rise time of the scope without timing error


def run(n_pins: int, calibrated: bool, n_chips: int = 40, n_ev: int = 20000, jit: float = 10.0) -> float:
    errs = []
    for _ in range(n_chips):
        step = 30.0 * (1 + rng.uniform(-0.2, 0.2))
        codes = np.round(np.arange(n_pins) * BIN / n_pins / 30.0)        # firmware assumes 30 ps
        thr = np.sort((codes * step + rng.normal(0, 40.0, n_pins)) % BIN)  # true sampling instants within the bin
        t = rng.uniform(0, BIN, n_ev)                                     # trigger phase, asynchronous
        k = (t[:, None] + rng.normal(0, jit, (n_ev, n_pins)) > thr[None, :]).sum(1)   # thermometer code 0..N
        if calibrated:
            # code density: bin edges from the measured occupancy, estimate = bin centre
            occ = np.bincount(k, minlength=n_pins + 1) / n_ev * BIN
            edges = np.concatenate([[0], np.cumsum(occ)])
            est = (edges[k] + edges[k + 1]) / 2
        else:
            est = (k + 0.5) * BIN / (n_pins + 1)
        e = est - t
        errs.append(e - e.mean() if not calibrated else e)
    return float(np.sqrt(np.mean(np.concatenate(errs) ** 2)))


if __name__ == "__main__":
    print("pins  LSB(ps)  rms error uncalibrated  calibrated   scope rise time with calibrated TDC")
    for n in (4, 8, 12, 16, 24):
        u, c = run(n, False), run(n, True)
        print(f"{n:4d}  {BIN / n:6.0f}  {u:14.0f} ps  {c:10.0f} ps   {np.hypot(SYS, 2.563 * c):6.0f} ps")
    for name, s in (("TDC7200 (35 ps rms)", 35.0), ("TDC-GPX2 (10-20 ps rms)", 15.0), ("Si5351C beat mode (est. 10 ps rms)", 10.0)):
        print(f"{name:36s} {np.hypot(SYS, 2.563 * s):6.0f} ps")
