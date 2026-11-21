"""Check of the steady-state method: N strobes 60 ns apart on a constant input, read the hold node."""
import dataclasses, os, re, subprocess, sys, tempfile
import numpy as np
import bridge as b

def run(p, n=10, period=60e-9, vin=0.1, amp_cin=True):
    one = b.strobe_pwl(dataclasses.replace(p, t_strobe=1.5e-9)).split()
    t1 = np.array(one[0::2], float); v1 = np.array(one[1::2], float)
    m = t1 > 0.9e-9
    pts = ["0 0"]
    for k in range(n):
        pts += [f"{t + k * period:.6g} {v:.5g}" for t, v in zip(t1[m], v1[m])]
    q = dataclasses.replace(p, t_in=2e-6, in_step=2 * -vin, t_tail=n * period, amp_cin=amp_cin)
    deck = b.build(q)
    deck = re.sub(r"^Vdrv .*$", "Vdrv drv_e 0 pwl(" + " ".join(pts) + ")", deck, flags=re.M)
    meas = "".join(f".meas tran v{k} find v(ls) at={(k + 1) * period - 1e-9:.6g}\n" for k in range(n))
    deck = deck.replace(".end\n", meas + ".end\n")
    for tmax in ("2p", "1.5p", "3p", "1p"):
        with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as fh:
            fh.write(deck.replace(" 0 2p\n", f" 0 {tmax}\n")); path = fh.name
        r = subprocess.run(["ngspice", "-b", path], capture_output=True, text=True); os.unlink(path)
        if "v0 " in r.stdout or re.search(r"^v0\s*=", r.stdout, re.M):
            break
    return [float(x) for x in re.findall(r"^v\d+\s*=\s*([-+0-9.eE]+)", r.stdout, re.M)]

if __name__ == "__main__":
    for ac in (True, False):
        for vin in (0.1, -0.1):
            print(ac, vin, np.round(np.array(run(b.P(), vin=vin, amp_cin=ac)) * 1e3, 1))
