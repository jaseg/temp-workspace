
from gerbonara.cad.kicad import footprints as kicad_fp

def make_pad(num, layer, x, y):
    return kicad_fp.Pad(
            number=str(num),
            type=kicad_fp.Atom.smd,
            shape=kicad_fp.Atom.circle,
            at=kicad_fp.AtPos(x=x, y=y),
            size=kicad_fp.XYCoord(x=trace_width, y=trace_width),
            layers=layer,
            clearance=clearance,
            zone_connect=0)

def make_line(x1, y1, x2, y2, layer):
    return kicad_fp.Line(
                start=kicad_fp.XYCoord(x=x1, y=y1),
                end=kicad_fp.XYCoord(x=x2, y=y2),
                layer=layer, 
                stroke=kicad_fp.Stroke(width=trace_width))

def make_arc(x1, y1, x2, y2, xm, ym, layer):
    return kicad_fp.Arc(
                start=kicad_fp.XYCoord(x=x1, y=y1),
                mid=kicad_fp.XYCoord(x=xm, y=ym),
                end=kicad_fp.XYCoord(x=x2, y=y2),
                layer=layer, 
                stroke=kicad_fp.Stroke(width=trace_width))


def make_via(x, y, layers):
    return kicad_fp.Pad(number="NC",
                     type=kicad_fp.Atom.thru_hole,
                     shape=kicad_fp.Atom.circle,
                     at=kicad_fp.AtPos(x=x, y=y),
                     size=kicad_fp.XYCoord(x=via_diameter, y=via_diameter),
                     drill=kicad_fp.Drill(diameter=via_drill),
                     layers=layers,
                     clearance=clearance, 
                     zone_connect=0)

