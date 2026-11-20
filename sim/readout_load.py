"""What reaches the comparator input of one tap gate (see ../docs/scope-frontend.md).

The hold capacitors are 2 x 0.47 pF. The summing resistors and the comparator input
capacitance load them, and the summing resistors also divide the reverse bias. This
prints the swing at the comparator input over time, in percent of the line voltage,
for one gate with an ideal 1.5 V strobe (the array gives about half of that).

  python3 readout_load.py
"""
import dataclasses
import os
import re
import subprocess
import tempfile

import numpy as np

import tap_gate as tg


def run(g, level):
    deck = re.sub(r"Vs s_e 0 pwl\([^)]*\)", f"Vs s_e 0 {2 * level}", tg.build(dataclasses.replace(g, t_in=0.5e-9)))
    deck = re.sub(r"\.tran 1p \S+ 0 2p", f".tran 1p {g.t_s + 100e-9:.6g} 0 4p", deck)
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "o.txt")
        deck = deck.replace(".end\n", f".control\nset wr_singlescale\nrun\nwrdata {out} v(out)\n.endc\n.end\n")
        path = os.path.join(td, "d.cir")
        open(path, "w").write(deck)
        subprocess.run(["ngspice", "-b", path], capture_output=True)
        d = np.loadtxt(out)
    return d[:, 0], d[:, 1]


CASES = [
    ("as drawn: 43k bias, 2 x 20k sum, Cin 3 pF, rails +/-0.5 V", tg.G(c=0.47e-12, rb=43e3, rsum=20e3, c_out=3e-12, a=0.5)),
    ("rails raised so the nodes sit at +/-0.5 V", tg.G(c=0.47e-12, rb=43e3, rsum=20e3, c_out=3e-12, a=0.5, ideal_bias=False)),
    ("  same, Cin 6 pF", tg.G(c=0.47e-12, rb=43e3, rsum=20e3, c_out=6e-12, a=0.5, ideal_bias=False)),
    ("  same, Cin 1 pF", tg.G(c=0.47e-12, rb=43e3, rsum=20e3, c_out=1e-12, a=0.5, ideal_bias=False)),
    ("2 x 4.7k sum, 10k bias, Cin 3 pF", tg.G(c=0.47e-12, rb=10e3, rsum=4.7e3, c_out=3e-12, a=0.5, ideal_bias=False)),
    ("2 x 4.7k sum, 22k bias, Cin 3 pF", tg.G(c=0.47e-12, rb=22e3, rsum=4.7e3, c_out=3e-12, a=0.5, ideal_bias=False)),
    ("2 x 4.7k sum, 22k bias, Cin 1 pF", tg.G(c=0.47e-12, rb=22e3, rsum=4.7e3, c_out=1e-12, a=0.5, ideal_bias=False)),
    ("hold 2 x 1 pF, 2 x 10k sum, 22k bias, Cin 3 pF", tg.G(c=1e-12, rb=22e3, rsum=10e3, c_out=3e-12, a=0.5, ideal_bias=False)),
]

if __name__ == "__main__":
    print("%-58s %s" % ("readout network", "swing at the comparator input, % of line voltage"))
    print("%-58s %5s %5s %5s %5s | %-16s | %s" % ("", "3 ns", "5 ns", "10 ns", "20 ns", "peak", "left after 100 ns"))
    for label, g in CASES:
        t, hi = run(g, +g.a)
        _, lo = run(g, -g.a)
        sw = (hi - lo) / (2 * g.a) * 100
        at = lambda dt: sw[min(np.searchsorted(t, g.t_s + dt), len(t) - 1)]
        i = int(np.argmax(np.abs(sw)))
        print("%-58s %5.0f %5.0f %5.0f %5.0f | %3.0f %% at %3.0f ns | %3.0f %% of the peak" % (
            label, at(3e-9), at(5e-9), at(10e-9), at(20e-9), sw[i], (t[i] - g.t_s) * 1e9, 100 * sw[-1] / sw[i]))
