#!/usr/bin/env python3
"""Summarise a kicad-cli (8+/nightly) ERC or DRC JSON report by type and severity.

usage: kicad_report_summary.py erc|drc report.json
"""
import collections
import json
import sys


def main():
    kind, path = sys.argv[1], sys.argv[2]
    d = json.load(open(path))
    rows = []  # (section, severity, type, description)
    if kind == "erc":
        for sheet in d.get("sheets", []):
            for v in sheet.get("violations", []):
                rows.append(("violations", v["severity"], v["type"], v["description"]))
    else:
        for sec in ("violations", "unconnected_items", "schematic_parity"):
            for v in d.get(sec, []):
                rows.append((sec, v["severity"], v["type"], v["description"]))

    print(f"{kind.upper()} {d.get('source', '')}  (KiCad {d.get('kicad_version', '?')})")
    by_sev = collections.Counter(r[1] for r in rows)
    print("  total %d: %s" % (len(rows), ", ".join(f"{k} {n}" for k, n in sorted(by_sev.items())) or "clean"))
    by_type = collections.Counter((r[0], r[1], r[2]) for r in rows)
    desc = {}
    for r in rows:
        desc.setdefault((r[0], r[1], r[2]), r[3])
    for (sec, sev, typ), n in sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0])):
        tag = "" if sec == "violations" else f" [{sec}]"
        print(f"  {n:5d}  {sev:8s} {typ}{tag}  -- {desc[(sec, sev, typ)][:70]}")


if __name__ == "__main__":
    main()
