
from gerbonara.cad.kicad.pcb import Board, TrackSegment, Via
from gerbonara.cad.kicad.footprints import Atom, AtPos, XYCoord, Pad, Line, Arc, Stroke, Drill

def make_pad(num, layer, x, y, diameter, clearance):
    return Pad(
            number=str(num),
            type=Atom.smd,
            shape=Atom.circle,
            at=AtPos(x=x, y=y),
            size=XYCoord(x=diameter, y=diameter),
            layers=layer,
            clearance=clearance,
            zone_connect=0)

def make_line(x1, y1, x2, y2, trace_width, layer):
    return Line(
                start=XYCoord(x=x1, y=y1),
                end=XYCoord(x=x2, y=y2),
                layer=layer, 
                stroke=Stroke(width=trace_width))

def make_arc(x1, y1, x2, y2, xm, ym, trace_width, layer):
    return Arc(
                start=XYCoord(x=x1, y=y1),
                mid=XYCoord(x=xm, y=ym),
                end=XYCoord(x=x2, y=y2),
                layer=layer, 
                stroke=Stroke(width=trace_width))


def make_via(x, y, diameter, drill, clearance, layers):
    return Pad(number="NC",
                     type=Atom.thru_hole,
                     shape=Atom.circle,
                     at=AtPos(x=x, y=y),
                     size=XYCoord(x=diameter, y=diameter),
                     drill=Drill(diameter=drill),
                     layers=layers,
                     clearance=clearance, 
                     zone_connect=0)


def footprint_to_board(footprint):
    return Board.empty_board(
            zones=zones,
            track_segments=[TrackSegment.from_footprint_line(line) for line in lines],
            vias=[Via.from_pad(pad) for pad in pads if pad.type == Atom.thru_hole])

