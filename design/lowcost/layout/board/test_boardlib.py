#!/usr/bin/env python3
"""Self-test of boardlib: netlist parse, check_board on the three tagged fragments, a trial merge of the
three fragments into one 100 x 50 mm board (positions from FLOORPLAN.md, fragments unchanged, so the
reference / net mismatches stay), a tiny Block built from the netlist, and renders.

Run: python3 test_boardlib.py [render_dir]   (renders default to the scratchpad given below or /tmp)
"""
import os, sys, json
import pcbnew
import boardlib as bl

HERE = os.path.dirname(os.path.abspath(__file__))
LAY = os.path.dirname(HERE)
OUT = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BOARD_SCRATCH", "/tmp/board_scratch")
os.makedirs(OUT, exist_ok=True)
FRAG = {"input_stage": (os.path.join(LAY, "input_stage", "input_stage.kicad_pcb"), 1),
        "sampler": (os.path.join(LAY, "sampler", "sampler.kicad_pcb"), 2),
        "phase_trigger": (os.path.join(LAY, "phase_trigger", "phase_trigger.kicad_pcb"), 3)}

bl.selftest()
summary = {}
for name, (path, grp) in FRAG.items():
    print()
    c = bl.check_board(path, refs=lambda r, g=grp: r[-3:].isdigit() and r[-3] == str(g), fill=True, verbose=6)
    summary[name] = {k: v for k, v in c.items() if k != "details"}

# --- a block built with boardlib: one strobe-chain detail, every net from the netlist
blk = bl.Block("libtest")
blk.place("U403", 4.0, 0.0, 180)

x7, y7 = blk.pad("U403", "7")
sx = -1 if x7 < 4.0 else 1                       # pad 7 side: leave along the pad axis (x)
q = blk.track(bl.net_of("U403", "7"), bl.W50, [("U403", "7"), (x7 + sx * 1.5, y7), (x7 + sx * 3.5, y7 + 2.0),
                                               (x7 + sx * 3.5, 6.0)], name="t", z=50)
blk.via(4.0, 3.0, "GND")
blk.iface(bl.net_of("U403", "7"), x7 + sx * 3.5, 6.0, "F.Cu", "S", "rf50", bl.W50)
blk.tline("TL402", [(10.0, 0.0), (10.0, 4.0), (14.0, 4.0), (14.0, 8.0)])
blk.edge_rect(-2, -3, 16, 10)
p = blk.save(OUT)
print()
bl.check_board(p, refs=["U403", "TL402"],
               rf_widths={bl.net_of("U403", "7"): bl.W50}, verbose=4)

# --- trial merge: fragments as they are, at their floorplan positions (see FLOORPLAN.md)
m = bl.new_master(100.0, 50.0)
cnt = []
# input: SMA on the left edge, below the top-left M3 hole; sampler X1 onto input IF1 (BUF_OUT_S, abutting);
# phase_trigger (105.2 mm, too long for 100 mm until it is folded) below, overhanging on the right
cnt.append(bl.merge(m.b, FRAG["input_stage"][0], 0.0, 6.5, 0))
cnt.append(bl.merge(m.b, FRAG["sampler"][0], 15.15 - 0.35, 6.5 + 6.35 - 8.95, 0))
cnt.append(bl.merge(m.b, FRAG["phase_trigger"][0], 0.0, 24.4, 0, skip_planes=True))
print("\nmerge counts:", cnt)
mp = os.path.join(OUT, "trial_merge.kicad_pcb")
bl.save_board(m.b, mp)
c = bl.check_board(mp, fill=True, verbose=4)
summary["trial_merge"] = {k: v for k, v in c.items() if k != "details"}
with open(os.path.join(OUT, "test_summary.json"), "w") as f:
    json.dump(summary, f, indent=1)
bl.render(mp, os.path.join(OUT, "trial_merge.png"), ("F.Cu", "F.SilkS", "Edge.Cuts"), tmpdir=OUT)
bl.render(p, os.path.join(OUT, "libtest.png"), ("F.Cu", "F.Fab", "Edge.Cuts"), tmpdir=OUT)
print("renders in", OUT)
