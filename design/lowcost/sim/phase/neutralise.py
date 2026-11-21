"""(b) Feed-through cancellation: a complementary line (LVDS N leg through a second TRF37D73, same pad,
same tap loading) and a C0G capacitor Cn from each hold node to it. Same gate/readout as gate50.py.
Prints comparator input (mV) at 1,2,3,5,8,12 ns after the strobe; a = 0.21 V, Cin 3 pF.
  python3 neutralise.py
"""
import json, os, re
from multiprocessing import Pool
import numpy as np
import common as c
import gate50 as g

def deck(p, t_edge, strobe, cn, sign=1):
    s = g.build(p)
    t0 = 5e-9
    v0, v1 = 2 * p.a * sign, -2 * p.a * sign
    w = f"0 {v0} {t0+t_edge:.6g} {v0} {t0+t_edge+0.24e-9:.6g} {v1}"
    wn = f"0 {-v0} {t0+t_edge:.6g} {-v0} {t0+t_edge+0.24e-9:.6g} {-v1}"
    s = re.sub(r"Vs s_e 0 pwl\([^)]*\)", f"Vs s_e 0 pwl({w})\nVcl cl_e 0 pwl({wn})\nRcl cl_e cl 50\nRclt cl 0 50"
               + (f"\nCna a cl {cn}\nCnk k cl {cn}" if cn else ""), s)
    if not strobe:
        s = re.sub(r"pulse\(0 \S+ ", "pulse(0 0 ", s)
    s = re.sub(r"\.tran 1p \S+", f".tran 1p {t0+15e-9:.6g}", s)
    return s

T = (1e-9, 2e-9, 3e-9, 5e-9, 8e-9, 12e-9)
def job(args):
    a = c.waves(deck(*args), ["v(out)"], tmax_list=(None, 2e-12))
    return [float(np.interp(5e-9 + x, a[:, 0], a[:, 1]) * 1e3) for x in T]

if __name__ == "__main__":
    jobs, labels = [], []
    for cin in (3e-12, 6e-12):
        p = g.P(cin=cin)
        for cn in (0, 0.22e-12, 0.27e-12, 0.33e-12):
            for name, te, st, sg in (("edge passed long before", 100e-9, True, -1), ("edge 0.3 ns after strobe", 0.3e-9, True, 1),
                                      ("edge, no strobe", 0.3e-9, False, 1)):
                jobs.append((p, te, st, cn, sg)); labels.append(f"Cin {cin*1e12:.0f}p Cn {cn*1e12:.2f}p {name}")
    with Pool(4) as pool:
        out = pool.map(job, jobs)
    print("comparator input, mV, at " + ", ".join(f"{x*1e9:g}" for x in T) + " ns; rising edge (line -a -> +a)")
    for l, o in zip(labels, out):
        print("%-52s" % l + " ".join("%6.1f" % x for x in o))
    json.dump(dict(zip(labels, out)), open(os.path.join(c.HERE, "neutralise.json"), "w"), indent=1)
