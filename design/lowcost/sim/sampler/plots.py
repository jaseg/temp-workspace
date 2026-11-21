"""bridge_step.png from bridge.json."""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))
r = json.load(open(os.path.join(HERE, "bridge.json")))
fig, ax = plt.subplots(1, 2, figsize=(12, 4.8))
for k, v in r.items():
    if "x" not in v:
        continue
    x = np.array(v["x"]) * 1e12
    y = (np.array(v["v"]) - v["v_lo"]) / v["params"]["in_step"]
    ax[0].plot(x, y, "o-", ms=3, lw=1.3, label=f"{k}: {v['tr_10_90']*1e12:.0f} ps, g {v['gain']:.2f}, eff {v['eff']*100:.0f} %")
ax[0].set_xlabel("strobe time - input step time (ps)"); ax[0].set_ylabel("held value / input step (steady state)")
ax[0].set_title("Equivalent-time step response at the hold node (ideal 1 ps input step)")
ax[0].grid(alpha=.3); ax[0].legend(fontsize=7, loc="upper left"); ax[0].set_xlim(-200, 1000)
lab = [k for k, v in r.items() if "x" not in v]
g = [r[k]["gain"] for k in lab]; e = [r[k]["eff"] for k in lab]
yy = np.arange(len(lab))
ax[1].barh(yy - 0.2, g, 0.4, label="gain (hold / input)")
ax[1].barh(yy + 0.2, e, 0.4, label="efficiency per strobe")
ax[1].set_yticks(yy); ax[1].set_yticklabels(lab, fontsize=7); ax[1].invert_yaxis()
ax[1].axvline(r["3 V strobe, unequal split (10 R)"]["gain"], color="C0", ls=":", lw=1)
ax[1].axvline(r["3 V strobe, unequal split (10 R)"]["eff"], color="C1", ls=":", lw=1)
ax[1].set_title("Sensitivities (unequal split, 10 R source)"); ax[1].grid(alpha=.3, axis="x"); ax[1].legend(fontsize=8)
fig.tight_layout(); fig.savefig(os.path.join(HERE, "bridge_step.png"), dpi=110)
