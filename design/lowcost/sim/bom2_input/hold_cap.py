"""Hold capacitor C205 value study (BOM defragmentation): imports sim/strobe_arms/arms.py unchanged and only
overrides its module constant C_HOLD (2.2 pF as built) before building the decks. Cases: as-built rev. 2
geometry (AB), clean-input aperture / efficiency / gain at several bridge biases, plus the system case.
python3 hold_cap.py  -> hold_cap.json (about 5-10 min, 4 processes)"""
import dataclasses, json, os, sys, multiprocessing as mp
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "strobe_arms"))
import arms  # noqa: E402

CH = [float(a) * 1e-12 for a in sys.argv[1:]] or [2.2e-12, 3.3e-12, 1.65e-12]
BIAS = {2.2e-12: (2.6, 2.0), 3.3e-12: (2.6, 2.0, 1.6), 1.65e-12: (2.6, 2.8)}
if __name__ == "__main__":
    path = os.path.join(HERE, "hold_cap.json")
    res = json.load(open(path)) if os.path.exists(path) else {}
    for ch in CH:
        arms.C_HOLD = ch                      # forked workers inherit the patched constant
        with mp.Pool(4) as pool:
            for vr in BIAS.get(round(ch, 14), (2.6,)):
                for sysc in (False, True):
                    p = arms.P(v_rev=vr, **arms.AB, **(arms.SYS if sysc else {}))
                    r = arms.step_response(pool, p)
                    key = f"Ch {ch*1e12:.2f} pF, bias +/-{vr/2:.2f} V{', system BUF802 2 GHz' if sysc else ''}"
                    res[key] = {k: r[k] for k in ("tr", "overshoot", "gain", "eff", "ped")}
                    print(key, {k: round(float(v), 4) for k, v in res[key].items()}, flush=True)
                    json.dump(res, open(path, "w"), indent=1, default=float)
