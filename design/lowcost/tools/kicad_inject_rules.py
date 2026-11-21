#!/usr/bin/env python3
"""Create or patch a (scratch-copy) .kicad_pro with board design-rule constraints.

usage: kicad_inject_rules.py <project.kicad_pro> jlc4
       kicad_inject_rules.py <project.kicad_pro> show   (print the rules in effect)

Only ever call this on a COPY (run_drc.sh does). Values for "jlc4" follow JLCPCB's
4-layer capabilities (0.09 mm track/space is their limit) with this project's
targets: 0.1 mm clearance, 0.2 mm via drill / 0.45 mm via diameter.
"""
import json
import os
import sys

# board-level hard minimums (Board Setup > Constraints), mm
JLC4_RULES = {
    "min_clearance": 0.09,             # JLC 4-layer min spacing
    "min_track_width": 0.09,           # JLC 4-layer min trace
    "min_connection": 0.0,
    "min_via_diameter": 0.35,          # project uses 0.40 / 0.45
    "min_through_hole_diameter": 0.15, # JLC multilayer min drill (project: 0.2)
    "min_via_annular_width": 0.075,    # project: 0.1 (0.4/0.2) .. 0.125 (0.45/0.2)
    "min_hole_clearance": 0.2,         # hole edge to copper
    "min_hole_to_hole": 0.25,
    "min_copper_edge_clearance": 0.2,  # JLC routed edge; edge-launch SMA pads may need a local rule
    "min_microvia_diameter": 0.2,
    "min_microvia_drill": 0.1,
    "min_silk_clearance": 0.0,
    "min_text_height": 0.8,
    "min_text_thickness": 0.08,
    "solder_mask_to_copper_clearance": 0.0,
}
# Default net class (used for every net, the generators assign no classes)
JLC4_DEFAULT_CLASS = {
    "name": "Default",
    "clearance": 0.1,
    "track_width": 0.15,
    "via_diameter": 0.45,
    "via_drill": 0.2,
    "microvia_diameter": 0.3,
    "microvia_drill": 0.1,
    "diff_pair_gap": 0.25,
    "diff_pair_via_gap": 0.25,
    "diff_pair_width": 0.2,
}


def main():
    path, mode = sys.argv[1], sys.argv[2]
    d = {}
    if os.path.exists(path):
        with open(path) as f:
            d = json.load(f)
    if mode == "show":
        rules = d.get("board", {}).get("design_settings", {}).get("rules", {})
        classes = d.get("net_settings", {}).get("classes", [])
        dflt = next((c for c in classes if c.get("name") == "Default"), {})
        keys = ["min_clearance", "min_track_width", "min_via_diameter", "min_through_hole_diameter",
                "min_via_annular_width", "min_hole_clearance", "min_hole_to_hole", "min_copper_edge_clearance"]
        print("  rules: " + (", ".join(f"{k}={rules[k]:.3g}" for k in keys if k in rules) or "(none in .kicad_pro: KiCad defaults)"))
        if dflt:
            print("  Default netclass: " + ", ".join(f"{k}={dflt[k]}" for k in
                  ("clearance", "track_width", "via_diameter", "via_drill") if k in dflt))
        return
    if mode != "jlc4":
        sys.exit(f"unknown rule set {mode}")
    d.setdefault("meta", {"filename": os.path.basename(path), "version": 1})
    ds = d.setdefault("board", {}).setdefault("design_settings", {})
    ds.setdefault("rules", {}).update(JLC4_RULES)
    ns = d.setdefault("net_settings", {"meta": {"version": 3}})
    classes = ns.setdefault("classes", [])
    for c in classes:
        if c.get("name") == "Default":
            c.update(JLC4_DEFAULT_CLASS)
            break
    else:
        classes.insert(0, dict(JLC4_DEFAULT_CLASS))
    with open(path, "w") as f:
        json.dump(d, f, indent=2)


if __name__ == "__main__":
    main()
