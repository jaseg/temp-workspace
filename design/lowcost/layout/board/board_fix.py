#!/usr/bin/env python3
"""Stage 3 of the board flow: DRC-driven clean-up of the integrator's own GND stitching vias.

Usage:  python3 board_fix.py <board.kicad_pcb> <drc.json>
Every GND via that the nightly DRC names in an error (clearance, shorting_items, items_not_allowed,
hole_clearance, hole_to_hole) and that has no track attached (i.e. a stitching via placed by
board_finish.stitch, not a block's pad via) is removed; zones are refilled and the board saved in place.
"""
import sys, json, re, glob, os
import pcbnew

FP_DNP = getattr(pcbnew, "FP_DNP", 0)            # KiCad 7 footprints have no DNP attribute (KiCad 8+)
SCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "kicad")


def sync_attributes(b):
    """review: copy the schematic's DNP / exclude-from-BOM flags onto the footprints (the netlist export
    carries neither, so the parity check flagged 30 footprint_symbol_mismatch warnings)"""
    flags = {}
    for f in glob.glob(os.path.join(SCH, "*.kicad_sch")):
        for ln in open(f):
            m = re.search(r'\(in_bom (yes|no)\).*?\(dnp (yes|no)\).*?\(property "Reference" "([^"#]+)"', ln)
            if m:
                flags[m.group(3)] = (m.group(1) == "no", m.group(2) == "yes")
    n = 0
    for fp in b.GetFootprints():
        r = fp.GetReference()
        if r in flags:
            nobom, dnp = flags[r]
            a = fp.GetAttributes()
            a2 = (a & ~(pcbnew.FP_EXCLUDE_FROM_BOM | FP_DNP)) | (pcbnew.FP_EXCLUDE_FROM_BOM if nobom else 0) \
                | (FP_DNP if dnp else 0)
            if a2 != a:
                fp.SetAttributes(a2)
                n += 1
    return n

TYPES = {"clearance", "shorting_items", "items_not_allowed", "hole_clearance", "hole_to_hole"}


def main(pcb, drc):
    b = pcbnew.LoadBoard(pcb)
    na = sync_attributes(b)                            # before any Remove() (SWIG list handling)
    d = json.load(open(drc))
    want = set()
    for v in d["violations"]:
        if v["type"] not in TYPES:
            continue
        for it in v["items"]:
            if it["description"].startswith("Via [GND]"):
                want.add((round(it["pos"]["x"], 3), round(it["pos"]["y"], 3)))
    ends = set()
    for t in b.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA) or t.GetNetname() != "GND":
            continue
        for p in (t.GetStart(), t.GetEnd()):
            ends.add((p.x, p.y))
    pads = []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == "GND":
                pads.append(p)
    n = 0
    for t in list(b.GetTracks()):
        if not isinstance(t, pcbnew.PCB_VIA) or t.GetNetname() != "GND":
            continue
        pos = t.GetPosition()
        key = (round(pcbnew.ToMM(pos.x), 3), round(pcbnew.ToMM(pos.y), 3))
        if not any(abs(key[0] - x) < 0.002 and abs(key[1] - y) < 0.002 for x, y in want):
            continue
        if (pos.x, pos.y) in ends or any(p.HitTest(pos) for p in pads):
            continue                                   # a block's own pad / track via: keep
        b.Remove(t)
        n += 1
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(pcb, b)
    print(f"board_fix: DNP / BOM flags synced on {na} footprints")
    print(f"board_fix: removed {n} stitching vias of {len(want)} flagged GND via positions")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
