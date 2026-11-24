"""Board renders (REPAIR 24 Nov): scope-fe-L1..L6, -all, -detail-{analog,fpga-south,mcu,power}.png from a refilled copy.
Run: python3 render_board.py [scratch_dir]"""
import sys, os
sys.path.insert(0, "/home/user/temp-workspace/design/lowcost/layout/board")
os.environ.setdefault("BL_STACKUP", "6L")
import boardlib as bl, pcbnew
H = "/home/user/temp-workspace/design/lowcost/layout/board"
S = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/-home-user/b3209b1f-f7fb-5362-924e-8729f34e30b8/scratchpad/board"
os.makedirs(S, exist_ok=True)
b = pcbnew.LoadBoard(os.path.join(H, "scope-fe.kicad_pcb")); pcbnew.ZONE_FILLER(b).Fill(b.Zones())
f = os.path.join(S, "board_filled.kicad_pcb"); b.Save(f)
_bb = b.ComputeBoundingBox(False); _ox, _oy = pcbnew.ToMM(_bb.GetX()) - 100, pcbnew.ToMM(_bb.GetY()) - 100
O = lambda x0, y0, x1, y1: (x0 - _ox, y0 - _oy, x1 - _ox, y1 - _oy)
full = O(-0.5, -0.5, 100.5, 57.5)
L = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
for k, l in enumerate(L):
    bl.render(f, os.path.join(H, f"scope-fe-L{k+1}.png"), (l, "Edge.Cuts"), crop=full, tmpdir=S)
bl.render(f, os.path.join(H, "scope-fe-all.png"), ("F.Cu", "B.Cu", "F.SilkS", "Edge.Cuts"), crop=full, tmpdir=S)
for nm, c in (("analog", (0, 0, 36, 24)), ("fpga-south", (54, 8, 76, 26)), ("mcu", (68, 43, 100, 57)),
              ("power", (73.5, 0, 100, 23))):
    bl.render(f, os.path.join(H, f"scope-fe-detail-{nm}.png"), ("F.Cu", "F.Fab", "Edge.Cuts"), crop=O(*c), tmpdir=S)
