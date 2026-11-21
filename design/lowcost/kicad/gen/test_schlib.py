"""Self-test: R, dual op-amp and SOT-223 regulator in all 12 rotation/mirror cases, a label on every pin,
checked through the kicad-cli netlist (each label must land on exactly that pin)."""
import sys
import os, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import schlib
from schlib import Sheet, g
OUT = tempfile.mkdtemp(prefix="schlib_test_")  # never touches the project files
sub = Sheet("t", title="test", ref_base=100)
i = 0; exp = {}
for lib in ("Device:R", "Amplifier_Operational:LMV358", "Regulator_Linear:AMS1117-3.3"):
  for rot in (0, 90, 180, 270):
    for mir in (None, "x", "y"):
        x = g(20 + 20 * (i % 12)); y = g(30 + 30 * (i // 12)); i += 1
        r = sub.add(lib, "R" if lib == "Device:R" else "U", "v", (x, y), rot=rot, mirror=mir)
        for p in r.pins:
            nm = f"N_{r.ref}_{p.number}"; sub.label(nm, r[p.number]); exp[nm] = (r.ref, p.number)
sub.save(OUT, quiet=True)
root = Sheet(None, title="root", ref_base=900)
root.sheet("t", (g(40), g(40)), (g(30), g(20)))
fn = root.save(OUT, quiet=True); schlib.write_project(OUT, ["t"])
n = schlib.nets(fn); bad = 0
for nm, rp in exp.items():
    k = "/t/" + nm
    if k not in n or n[k] != {rp}: bad += 1; print("BAD", nm, n.get(k))
print("checked", len(exp), "bad", bad)
