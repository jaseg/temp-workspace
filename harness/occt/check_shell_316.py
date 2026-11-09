import sys; sys.path.append(sys.argv[1])  # FreeCAD's lib directory
import FreeCAD as App, Part
for r in (1.0, 2.0, 2.4):
    b = Part.makeBox(40,30,10)
    es=[e for e in b.Edges if abs(e.BoundBox.ZMax)<1e-9]
    f = b.makeFillet(r, es)
    bottom=[x for x in f.Faces if abs(x.BoundBox.ZMax)<1e-9 and x.Area>100]
    for join in (0,2):
        try:
            s = f.makeThickness(bottom, -2.0, 1e-4, False, False, 0, join)
            print(r, join, "vol", round(s.Volume,3), "valid", s.isValid(), "faces", len(s.Faces), "unchanged" if abs(s.Volume-f.Volume)<1e-6 else "")
        except Exception as e: print(r, join, "ERR", e)
