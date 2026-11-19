"""Waveform helpers: run one transient with probes and measure edges and pulses."""
from __future__ import annotations

import os
import tempfile

import numpy as np

import frontend as f

PROBES = ["v(stim_a_p)", "v(stim_a_n)", "v(stim_b_p)", "v(stim_b_n)", "v(star_p)", "v(star_n)",
          "v(hs_p)", "v(hs_n)", "v(tdr_p)", "v(tdr_n)", "v(mesh_end_p)", "v(mesh_end_n)",
          "v(strobe_a_p)", "v(strobe_a_n)", "v(strobe_b_p)", "v(strobe_b_n)", "v(nt_p)", "v(nt_n)",
          "v(ka_p)", "v(kk_p)", "v(ls_p)", "v(ls_n)"]


def waves(p: f.Params) -> dict[str, np.ndarray]:
    probes = [x for x in PROBES if p.stim == "fpga" or not any(k in x for k in ("stim_", "tdr_", "mesh_"))]
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "w.txt")
        f.run(p, probes, out)
        a = np.loadtxt(out, skiprows=1)
    w = {"t": a[:, 0]}
    for i, name in enumerate(probes):
        w[name[2:-1]] = a[:, i + 1]
    return w


def crossing(t: np.ndarray, v: np.ndarray, level: float, rising: bool = True) -> float:
    s = (v[:-1] < level) & (v[1:] >= level) if rising else (v[:-1] > level) & (v[1:] <= level)
    i = np.flatnonzero(s)
    if len(i) == 0:
        return float("nan")
    i = i[0]
    return float(t[i] + (level - v[i]) * (t[i + 1] - t[i]) / (v[i + 1] - v[i]))


def edge(t: np.ndarray, v: np.ndarray, t0: float, t1: float, lo: float = 0.1, hi: float = 0.9) -> tuple[float, float, float]:
    """(rise time lo-hi, amplitude, 50 % time) of a monotone-ish edge between t0 and t1.
    Start and end levels are the means over the first and last 5 % of the window."""
    m = (t >= t0) & (t <= t1)
    t, v = t[m], v[m]
    n = max(2, len(t) // 20)
    a, b = v[:n].mean(), v[-n:].mean()
    x = (v - a) / (b - a)
    return crossing(t, x, hi) - crossing(t, x, lo), b - a, crossing(t, x, 0.5)


def pulse(t: np.ndarray, v: np.ndarray, t0: float, t1: float) -> tuple[float, float, float]:
    """(peak above the starting level, full width at half maximum, time of peak)."""
    m = (t >= t0) & (t <= t1)
    t, v = t[m], v[m]
    v = v - v[:5].mean()
    k = int(np.argmax(v))
    half = v[k] / 2
    left = crossing(t[:k + 1], v[:k + 1], half, True)
    right = crossing(t[k:], v[k:], half, False)
    return float(v[k]), right - left, float(t[k])
