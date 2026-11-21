"""Stage 2 of gen_board.py: supply routing on In2, planes and pours, GND stitching, silkscreen, project file.

finish(B, m, R, rf) works on the routed master board (B = pcbnew.BOARD, m = boardlib.Block wrapping it,
R = boardroute.Router over it).  Stand-alone:  python3 board_finish.py <routed.kicad_pcb>
"""
import os, sys, json, math
import numpy as np
import pcbnew
import boardlib as bl
import boardroute as br

W, H = 100.0, 57.0
SUPPLY_TRACK = ("+5V", "-5V", "+2V5", "-2V5", "+1V2", "VBUS")
HOLES = ((3, 3), (97, 3), (3, 54), (97, 54))


def loc(v):
    return pcbnew.ToMM(v.x) - bl.ORG[0], pcbnew.ToMM(v.y) - bl.ORG[1]


def supply_points(B, net):
    pts = []
    for t in B.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == net:
            pts.append(loc(t.GetPosition()))
    for fp in B.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                pts.append(loc(p.GetPosition()))
    return pts


def clusters(pts, d=2.5):
    cl = []
    for p in pts:
        for c in cl:
            if any(math.hypot(p[0] - q[0], p[1] - q[1]) < d for q in c):
                c.append(p)
                break
        else:
            cl.append([p])
    return cl


def in_zone(B, net, p):
    for z in B.Zones():
        if not z.GetIsRuleArea() and z.GetNetname() == net and z.IsOnLayer(pcbnew.In2_Cu):
            if z.Outline().Contains(pcbnew.VECTOR2I(pcbnew.FromMM(p[0] + bl.ORG[0]), pcbnew.FromMM(p[1] + bl.ORG[1]))):
                return True
    return False


def route_supplies(B, m, R, log):
    """each non-3V3 supply: MST over its via clusters, In2 tracks 0.5 mm (B.Cu fallback)"""
    for net in SUPPLY_TRACK:
        cl = clusters(supply_points(B, net))
        if len(cl) < 2:
            continue
        done = [cl[0]]
        todo = cl[1:]
        while todo:
            best = None
            for c in todo:
                for p in c:
                    for dc in done:
                        for q in dc:
                            dd = math.hypot(p[0] - q[0], p[1] - q[1])
                            if best is None or dd < best[0]:
                                best = (dd, c, p, q)
            _, c, p, q = best
            todo.remove(c)
            done.append(c)
            r = None
            for wid, lay, mg in ((0.5, ("In2.Cu",), 5), (0.4, ("In2.Cu", "B.Cu"), 10), (0.3, ("In2.Cu", "B.Cu"), 25)):
                r = R.route(net, (p[0], p[1], "*", "*"), (q[0], q[1], "*", "*"), w=wid, layers=lay,
                            lcost={"B.Cu": 3.0}, via_cost=3.0, clr=0.2, margin=mg, maxn=300_000)
                if r:
                    break
            log.append((net, round(p[0], 2), round(p[1], 2), round(q[0], 2), round(q[1], 2), bool(r)))


def zone(m, net, layer, pts, prio=0, clr=0.2, minw=0.25, thermal=False):
    z = m.zone(net, (layer,), pts, clearance=clr, prio=prio, minw=minw, thermal=thermal)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    return z


def planes(B, m):
    edge = 0.3
    full = [(edge, edge), (W - edge, edge), (W - edge, H - edge), (edge, H - edge)]
    zone(m, "GND", "In1.Cu", full, prio=0)
    zone(m, "+3V3", "In2.Cu", full, prio=0)
    # board-wide GND pours on F / B (the blocks' own GND pours stay; overlapping same-net pours are fine)
    zone(m, "GND", "F.Cu", full, prio=0, clr=0.2)
    zone(m, "GND", "B.Cu", full, prio=0, clr=0.2)


def stitch(B, m, R, rf_tracks):
    """GND stitching: fences along the inter-block RF lines, a ring along the analog block, a 2.5 mm grid"""
    code = m.net("GND").GetNetCode()
    n = 0
    occ = {ln: (R.own[ln] != -1) & (R.own[ln] != code) for ln in br.LAYERS}
    from scipy import ndimage
    d = np.minimum.reduce([ndimage.distance_transform_edt(~occ[ln]) * br.F for ln in br.LAYERS])
    nov = R.novia.copy()
    placed = []

    def try_via(x, y, need=bl.VIA_D / 2 + 0.2):
        nonlocal n
        i, j = int(round(x / br.F)), int(round(y / br.F))
        if not (0 <= i < d.shape[0] and 0 <= j < d.shape[1]):
            return False
        if d[i, j] < need or nov[i, j]:
            return False
        if any(math.hypot(x - hx, y - hy) < 3.6 for hx, hy in HOLES):
            return False
        if x < 0.8 or y < 0.8 or x > W - 0.8 or y > H - 0.8:
            return False
        if any(abs(x - px) < 0.7 and abs(y - py) < 0.7 for px, py in placed[-400:]):
            return False
        v = m.via(round(x, 3), round(y, 3), "GND")
        R.add_item(v)
        placed.append((x, y))
        r = int(0.7 / br.F)
        nov[max(0, i - r):i + r, max(0, j - r):j + r] = True
        n += 1
        return True
    # fences: 1.1 mm from the RF centre line, 1.5 mm pitch
    for (x0, y0), (x1, y1), w in rf_tracks:
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 0.5:
            continue
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        off = w / 2 + 2 * w + 0.35
        k = 0.0
        while k <= L:
            for s in (1, -1):
                try_via(x0 + ux * k - uy * off * s, y0 + uy * k + ux * off * s)
            k += 1.5
    # analog block ring (y 22.0 .. 22.9 seam and x 56 seam)
    for x in np.arange(1.0, 56.0, 1.2):
        for y in (22.6, 22.2):
            if try_via(x, y):
                break
    for y in np.arange(1.0, 22.5, 1.2):
        try_via(56.0, y) or try_via(55.6, y)
    # general grid
    for x in np.arange(1.25, W, 2.5):
        for y in np.arange(1.25, H, 2.5):
            for dx, dy in ((0, 0), (0.4, 0), (0, 0.4), (-0.4, 0), (0, -0.4)):
                if try_via(x + dx, y + dy):
                    break
    return n


def silk(B, m):
    def txt(s, x, y, size=1.0, layer="F.SilkS", rot=0):
        t = m.text(s, x, y, size, layer, rot)
        t.SetTextThickness(pcbnew.FromMM(0.15))
        return t
    txt("scope-fe  rev A", 20.0, 55.6, 1.0)
    txt("SIG IN", 3.2, 7.3, 0.8)
    txt("EXT CLK", 3.6, 46.6, 0.8)
    txt("USB", 95.0, 20.6, 0.8)
    for s, x, y in (("ANALOG", 40.0, 0.9), ("FPGA", 65.0, 23.2), ("POWER", 88.0, 23.2)):
        pass
    txt("PHASE", 22.0, 52.2, 0.8)
    txt("MCU / IF", 20.0, 53.9, 0.8)
    txt("JLC04161H-7628", 79.0, 56.2, 0.8, "B.SilkS")


def write_pro(path, rf_nets):
    pro = {
        "meta": {"filename": os.path.basename(path), "version": 1},
        "board": {"design_settings": {
            "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2, "copper_text_size_h": 1.0,
                         "copper_text_size_v": 1.0, "copper_text_thickness": 0.15, "silk_line_width": 0.15,
                         "silk_text_size_h": 0.8, "silk_text_size_v": 0.8, "silk_text_thickness": 0.15},
            "rules": {"min_clearance": 0.09, "min_track_width": 0.09, "min_connection": 0.0,
                      "min_via_diameter": 0.35, "min_through_hole_diameter": 0.15, "min_via_annular_width": 0.075,
                      "min_hole_clearance": 0.2, "min_hole_to_hole": 0.25, "min_copper_edge_clearance": 0.2,
                      "min_microvia_diameter": 0.2, "min_microvia_drill": 0.1, "min_silk_clearance": 0.0,
                      "min_text_height": 0.8, "min_text_thickness": 0.08, "solder_mask_to_copper_clearance": 0.0},
            "track_widths": [0.0, 0.15, 0.2, 0.25, 0.36, 0.4, 0.5],
            "via_dimensions": [{"diameter": 0.0, "drill": 0.0}, {"diameter": 0.45, "drill": 0.2}]}},
        "net_settings": {"meta": {"version": 3}, "classes": [
            {"name": "Default", "clearance": 0.1, "track_width": 0.15, "via_diameter": 0.45, "via_drill": 0.2,
             "microvia_diameter": 0.3, "microvia_drill": 0.1, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
             "diff_pair_width": 0.2, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
             "schematic_color": "rgba(0, 0, 0, 0.000)", "wire_width": 6, "bus_width": 12},
            {"name": "RF50", "clearance": 0.15, "track_width": 0.36, "via_diameter": 0.45, "via_drill": 0.2,
             "microvia_diameter": 0.3, "microvia_drill": 0.1, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
             "diff_pair_width": 0.36, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
             "schematic_color": "rgba(0, 0, 0, 0.000)", "wire_width": 6, "bus_width": 12},
            {"name": "USB90", "clearance": 0.15, "track_width": 0.295, "via_diameter": 0.45, "via_drill": 0.2,
             "microvia_diameter": 0.3, "microvia_drill": 0.1, "diff_pair_gap": 0.205, "diff_pair_via_gap": 0.25,
             "diff_pair_width": 0.295, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
             "schematic_color": "rgba(0, 0, 0, 0.000)", "wire_width": 6, "bus_width": 12},
            {"name": "Power", "clearance": 0.15, "track_width": 0.4, "via_diameter": 0.45, "via_drill": 0.2,
             "microvia_diameter": 0.3, "microvia_drill": 0.1, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
             "diff_pair_width": 0.2, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
             "schematic_color": "rgba(0, 0, 0, 0.000)", "wire_width": 6, "bus_width": 12}],
            "netclass_patterns": [{"netclass": "RF50", "pattern": n} for n in rf_nets] +
                                 [{"netclass": "USB90", "pattern": "/USB_D*"}] +
                                 [{"netclass": "Power", "pattern": p} for p in
                                  ("+3V3", "+5V", "-5V", "+2V5", "-2V5", "+1V2", "VBUS")]},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [], "text_variables": {}}
    with open(path, "w") as f:
        json.dump(pro, f, indent=2)
