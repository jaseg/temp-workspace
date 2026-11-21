"""(3b) Wrong-polarity pulse on the main sampler bridge: deck D of sim/scope_sampler.py (10 R source,
balun, 80 ps shorted stub, +/-1 V bias) driven by the falling edge of the 50 % duty strobe
(-4.6 V step, 150 ps), with and without a BAT15 shunt clamp at the stub/launch node ("clip").
Also the wanted (+4.6 V) pulse with the clamp in place: peak drive and held value.
  python3 bridge_rev.py  -> bridge_rev.json
"""
import dataclasses
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "sim"))
import scope_sampler as ss  # noqa: E402


def run(v_step, clamp):
    p = ss.P(r_in=10.0, stub_td=80e-12, v_step=v_step, tr=150e-12, v_rev=2.0, t_in=0.5e-9, v_ls=0.1)
    txt = ss.build(p)
    extra = ""
    if clamp:
        extra += ("Xclamp 0 clip dpk\n" if v_step > 0 else "Xclamp 0 clip dpk\n")
    extra += (".meas tran rev_da max par('v(ls)-v(ka)')\n.meas tran rev_dk max par('v(kk)-v(ls)')\n"
              ".meas tran rev_dah max par('v(hs)-v(ka)')\n.meas tran rev_dkh max par('v(kk)-v(hs)')\n"
              ".meas tran clipmin min v(clip)\n.meas tran clipmax max v(clip)\n")
    txt = txt.replace(".end\n", extra + ".end\n")
    with tempfile.TemporaryDirectory() as td:
        fn = os.path.join(td, "a.cir"); open(fn, "w").write(txt)
        r = subprocess.run(["ngspice", "-b", fn], capture_output=True, text=True, timeout=600)
    o = {m.group(1): float(m.group(2)) for m in re.finditer(r"^(\w+)\s*=\s*([-+0-9.eE]+)", r.stdout, re.M)}
    return dict(v_step=v_step, clamp=clamp, held_change_mV=(o["end_ls"] - 0.1) * 1e3, **{k: o[k] for k in
                ("pk_drive", "rev_da", "rev_dk", "rev_dah", "rev_dkh", "clipmin", "clipmax")})


if __name__ == "__main__":
    out = [run(s, c) for s in (-4.6, 4.6) for c in (False, True)]
    for o in out:
        print(o)
    json.dump(out, open(os.path.join(HERE, "bridge_rev.json"), "w"), indent=1)
