"""(b) Line feed-through into the tap readout: a line edge after the strobe reaches the comparator
input through the diode capacitance (common mode of the two hold nodes). One gate, gate50.py network.
Cases: static line (+a), line edge +a -> -a at 0.5 / 3 ns after the strobe, and an edge with no strobe.
  python3 feedthrough.py
"""
import dataclasses, json, os, re
from multiprocessing import Pool
import numpy as np
import common as c
import gate50 as g

def deck(p, t_edge, strobe=True):
    s = g.build(p)
    t0 = 5e-9
    s = re.sub(r"Vs s_e 0 pwl\([^)]*\)", f"Vs s_e 0 pwl(0 {2*p.a} {t0+t_edge:.6g} {2*p.a} {t0+t_edge+0.24e-9:.6g} {-2*p.a})", s)
    if not strobe:
        s = re.sub(r"pulse\(0 \S+ ", "pulse(0 0 ", s)
    s = re.sub(r"\.tran 1p \S+", f".tran 1p {t0+20e-9:.6g}", s)
    return s

def job(args):
    p, te, st = args
    a = c.waves(deck(p, te, st), ["v(out)"], tmax_list=(None, 2e-12))
    t, v = a[:, 0], a[:, 1]
    return [float(np.interp(5e-9 + x, t, v) * 1e3) for x in (1e-9, 2e-9, 3e-9, 5e-9, 8e-9, 12e-9, 16e-9, 19.5e-9)]

if __name__ == "__main__":
    res = {}
    jobs = []
    for cin in (3e-12, 6e-12):
        p = g.P(cin=cin)
        jobs += [(p, 100e-9, True), (p, 0.5e-9, True), (p, 3e-9, True), (p, 0.5e-9, False)]
    with Pool(4) as pool:
        out = pool.map(job, jobs)
    names = ["static +a", "edge to -a at +0.5 ns", "edge to -a at +3 ns", "edge at +0.5 ns, no strobe"]
    print("comparator input (mV) at 1,2,3,5,8,12,16,19.5 ns after the strobe; a = 0.21 V")
    for k, o in enumerate(out):
        lab = ("Cin 3 pF " if k < 4 else "Cin 6 pF ") + names[k % 4]
        res[lab] = o
        print("%-40s" % lab + " ".join("%6.1f" % x for x in o))
    json.dump(res, open(os.path.join(c.HERE, "feedthrough.json"), "w"), indent=1)
