
from gerbonara.cad.kicad.pcb import Board, TrackSegment, TrackArc, Via
import copy

from gerbonara.cad.kicad.footprints import Atom, AtPos, XYCoord, Pad, Line, Arc, Stroke, Drill, Footprint
from gerbonara.cad.kicad.base_types import DrawnProperty

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
    """ Convert a coil footprint into a board: tracks, arcs and vias become free board items, the keepout zone becomes a
    board rule area. The terminal pads are SMD pads, which can only exist inside a footprint, so they are placed on the
    board in a footprint of their own (named after the coil footprint with a "-terminals" suffix). """
    board = Board.empty_board(
            zones=list(footprint.zones),
            track_segments=[TrackSegment.from_footprint_line(line) for line in footprint.lines],
            track_arcs=[TrackArc(arc.start, arc.mid, arc.end, arc.stroke.width, arc.layer) for arc in footprint.arcs],
            vias=[Via.from_pad(pad) for pad in footprint.pads if pad.type == Atom.thru_hole])

    terminal_pads = [copy.deepcopy(pad) for pad in footprint.pads if pad.type != Atom.thru_hole]
    if terminal_pads:
        terminals = Footprint(
                name=f'{footprint.name or "planar-coil"}-terminals',
                layer='F.Cu',
                descr=f'Terminal pads of {footprint.name or "a planar coil"}',
                properties=[DrawnProperty(key='Reference', value='L1', at=AtPos(x=0, y=0), layer='F.SilkS', hide=True),
                            DrawnProperty(key='Value', value=footprint.name or 'planar-coil', at=AtPos(x=0, y=0),
                                          layer='F.Fab', hide=True)],
                pads=terminal_pads)
        board.footprints.append(terminals)

    # gerbonara (1.6.0) cannot serialize the empty list of legacy "module" footprints that Board() creates by default
    # (MappingError in Board.serialize()). None is skipped by the serializer, and is what a parsed board without legacy
    # footprints holds as well.
    board.legacy_footprints = None
    return board
