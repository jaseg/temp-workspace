"""Annotate results/occt_kernel_cases.jsonl with the triage verdicts and SolidCraft's published
results, and write results/kernel_cases_side_by_side.md.

SolidCraft's side has two sources:
- docs/kernel-cases.md, the generated report (stale: it lists 372 cases, the folders hold ~1000);
- each area's KNOWN_FAILING gate list (newer: a case not listed passes the gate at the
  baseline it names; a listed one fails or is unsupported there).
"""

import collections
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SC = os.path.normpath(os.path.join(HERE, "..", ".."))
CASES = os.path.join(SC, "src", "solidcraft", "tests", "kernel-cases")
DOC = os.path.join(SC, "src", "solidcraft", "docs", "kernel-cases.md")
RES = os.path.join(SC, "results", "occt_kernel_cases.jsonl")
MD = os.path.join(SC, "results", "kernel_cases_side_by_side.md")

# Validation of every OCCT non-pass (see the report). Every non-pass not listed here was looked at
# and is a real OCCT failure with the replay doing what the recipe says.
UNCERTAIN = {
    "fillets/851-chamfer-knife-edge-tip-5":
        "chamfer of a zero-angle (tangent) knife edge: the expected answer sets the chamfer back where a ball of radius d touches the faces; "
        "OCCT measures d along each face, a different definition there (OCCT removed 10 mm3, expected 564)",
    "fillets/851-chamfer-knife-edge-tip-2-box-less-cylinder":
        "chamfer of a zero-angle (tangent) knife edge, defined by SolidCraft through ball contacts; OCCT refuses (NotDone) any chamfer of a G1 edge",
    "fillets/cov-fillet-section-chamfer-pipe-on-plate-2":
        "chamfer between a plane and a cylinder at 53 deg: the expected answer sets back by ball contact, OCCT by distance along each face; "
        "the 5.7e-4 volume difference is that definition, not a failure",
    "fillets/every-block-cylinder-tangent-concave-arc-r2-no-tangent-chain":
        "SolidCraft's chain stops where the concave arc runs on tangentially into convex edges; OCCT's fillet always propagates along "
        "tangent edges, so it attempts a different blend (it does return an invalid solid without raising)",
}
NOTES = {
    "fillets/cov-fillet-exact-cylinders-touching-at-a-point-r1": "precision only: rel error 1.2e-6 vs the case's 1e-6 (OCCT blend surfaces are approximations)",
    "fillets/cov-fillet-exact-oblique-plane-cone-rim-r1-5": "precision only: rel error 3.7e-6 vs the case's 1e-6",
    "fillets/cov-fillet-exact-oblique-plane-cylinder-rim-r2": "precision only: rel error 1.6e-5 vs the case's 1e-6",
    "fillets/cov-fillet-tee-pipe-r8-into-pipe-r20-r3": "precision only: rel error 1.2e-6 vs the case's 1e-6",
    "fillets/3655-chamfer-edge-order-box": "volume right; OCCT adds a corner facet at each of the 8 corners where SolidCraft's three chamfer planes meet in a point",
    "fillets/every-box-corner-three-edges-chamfer-2": "OCCT adds a 3.46 mm2 corner facet (volume 23825.33 vs 23826, within tolerance); faces 10 vs 9",
    "fillets/1080-fillet-notched-block-top-outline-r7": "silently wrong: valid solid, 88 mm3 too much material (same fillet without the notch is exact)",
    "fillets/cov-chamfer-concave-edge-through-up-down-joined-squares": "OCCT/FreeCAD process exits (status 1, no exception) inside makeChamfer",
    "fillets/2893-chamfer-two-distances-across-the-whole-top-refused": "OCCT builds a valid solid for a 10 mm setback on an r10 rim (the cone would end in a point)",
    "shell/545-shell-ring-cut-frame-open-at-an-outer-wall": "OCCT's thick solid comes out inside-out (volume -59122.5) yet passes isValid",
    "shell/1494-shell-box-with-cylinder-on-edge-line": "valid solid, cylinder part not hollowed (12688 vs 8857..8865)",
}
SILENT_NOOP = "OCCT's MakeThickSolid (FreeCAD makeThickness) returned the body unchanged without raising"


def docs_results():
    lines = open(DOC).read().split("\n")
    i0, i1 = lines.index("## Results"), lines.index("## Sources")
    out = {}
    for line in lines[i0:i1]:
        if not line.startswith("| ") or line.startswith("| Case"):
            continue
        cells = [x.strip() for x in line.strip().strip("|").split("|")]
        if "/" not in cells[0]:
            continue
        out[cells[0]] = cells[-1]
    return out


def docs_status(s):
    if s is None:
        return None
    t = s.lower()
    for k, v in (("**fail**", "fail"), ("**hang**", "hang"), ("**crash**", "crash"), ("not supported", "unsupported"), ("pass", "pass")):
        if t.startswith(k):
            return v
    return "?"


def gate():
    out = {}
    base = {}
    for area in os.listdir(CASES):
        p = os.path.join(CASES, area, "KNOWN_FAILING")
        if not os.path.exists(p):
            continue
        for line in open(p):
            if line.startswith("#"):
                m = re.search(r"Baseline: (.*)", line)
                if m:
                    base[area] = m.group(1).strip()
                continue
            if not line.strip():
                continue
            cid, _, why = line.strip().partition(" ")
            out[area + "/" + cid] = why
    return out, base


def gate_status(key, kf):
    why = kf.get(key)
    if why is None:
        return "pass", ""
    m = re.match(r"\[(\w+)\]", why)
    st = m.group(1) if m else "fail"
    continuity = "continuity" in why
    return ("fail(continuity)" if continuity and st == "fail" else st), why


def main():
    recs = [json.loads(line) for line in open(RES)]
    docs = docs_results()
    kf, base = gate()
    for r in recs:
        key = r["area"] + "/" + r["id"]
        st = r["status"]
        noop = any("NOOP" in x for x in r.get("log_tail", []))
        if st in ("pass", "unsupported"):
            r["verdict"] = st
        elif key in UNCERTAIN:
            r["verdict"] = "uncertain"
            r["verdict_note"] = UNCERTAIN[key]
        else:
            r["verdict"] = "real_occt_failure"
            note = NOTES.get(key, "")
            if noop:
                note = (SILENT_NOOP + ". " + note).strip()
            if st == "error" and not note:
                note = "OCCT raised: " + (r.get("error") or "")[:120]
            r["verdict_note"] = note
        d = docs.get(key)
        r["solidcraft_docs"] = d
        r["solidcraft_docs_status"] = docs_status(d) if d else "not in docs table"
        gs, why = gate_status(key, kf)
        r["solidcraft_gate_status"] = gs
        if why:
            r["solidcraft_gate_why"] = why
    with open(RES, "w") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")

    def occt_col(r):
        return r["status"] if r["verdict"] != "uncertain" else r["status"] + " (uncertain)"

    areas = sorted(set(r["area"] for r in recs))
    out = ["# SolidCraft kernel cases: OCCT replay vs SolidCraft's published results", "",
           "OCCT 7.9.3 through FreeCAD 1.1.3's Part module, an independent replay of each case's recipe "
           "(`harness/kernelcases/replay.py`), graded against the case's own `expected.json` "
           "(`harness/kernelcases/run_cases.py`). One process per case, 120 s timeout.", "",
           "SolidCraft columns: **docs** is `docs/kernel-cases.md` (generated; stale, it covers only %d of these %d cases); "
           "**gate** is the area's `KNOWN_FAILING` list (a case not listed passes the kernel-rig gate at the list's baseline). "
           "Gate failures marked `fail(continuity)` fail only the continuity check, which this replay does not grade." % (
               sum(1 for r in recs if r["solidcraft_docs"]), len(recs)), "",
           "Checks graded: body_count, volume, area, faces, shells, bbox, center_of_mass, validity, refusal (by any OCCT exception; "
           "the message is not compared). Not graded: continuity, surface_types, splines, watertight, edges/vertices, inspect results.", ""]
    out.append("## Counts")
    out.append("")
    out.append("| Area | Cases | OCCT pass | fail | error | invalid | crash | timeout | unsupported | uncertain (of the non-pass) | SolidCraft gate pass | SolidCraft docs pass / listed |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    tot = collections.Counter()
    for a in areas + ["all"]:
        rs = [r for r in recs if a == "all" or r["area"] == a]
        c = collections.Counter(r["status"] for r in rs)
        unc = sum(1 for r in rs if r["verdict"] == "uncertain")
        gp = sum(1 for r in rs if r["solidcraft_gate_status"] == "pass")
        dl = [r for r in rs if r["solidcraft_docs"]]
        dp = sum(1 for r in dl if r["solidcraft_docs_status"] == "pass")
        out.append("| %s | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d / %d |" % (
            a, len(rs), c["pass"], c["fail"], c["error"], c["invalid"], c["crash"], c["timeout"], c["unsupported"], unc, gp, dp, len(dl)))
    out.append("")
    out.append("## Every case")
    out.append("")
    out.append("| Case | OCCT | OCCT detail | SolidCraft docs | SolidCraft gate | wall s |")
    out.append("|---|---|---|---|---|---|")
    for r in recs:
        key = r["area"] + "/" + r["id"]
        if r["status"] == "pass":
            detail = "; ".join(r.get("notes") or [])[:160]
        elif r["status"] == "unsupported":
            detail = "; ".join(r.get("notes") or [])[:160]
        else:
            detail = "; ".join(r.get("checks") or [])[:200]
            if r.get("verdict_note"):
                detail += " — " + r["verdict_note"][:220]
        docs_cell = r["solidcraft_docs_status"]
        if r["solidcraft_docs"] and docs_cell != "pass":
            docs_cell += ": " + re.sub(r"\*\*\w+\*\*:?\s*", "", r["solidcraft_docs"])[:120]
        gate_cell = r["solidcraft_gate_status"]
        if r.get("solidcraft_gate_why"):
            gate_cell += ": " + r["solidcraft_gate_why"][:100]
        cell = lambda s: s.replace("|", "\\|").replace("\n", " ")
        out.append("| %s | %s | %s | %s | %s | %.1f |" % (key, occt_col(r), cell(detail), cell(docs_cell), cell(gate_cell), r.get("wall_s", 0)))
    out.append("")
    out.append("Gate baselines: " + "; ".join("%s: %s" % (a, base[a]) for a in areas if a in base))
    open(MD, "w").write("\n".join(out) + "\n")

    # console summary
    print(out[out.index("## Counts") + 2: out.index("## Every case") - 1] and "\n".join(out[out.index("## Counts") + 2: out.index("## Every case") - 1]))
    print()
    disagree = []
    for r in recs:
        if r["status"] == "unsupported" or r["verdict"] == "uncertain":
            continue
        occt_pass = r["status"] == "pass"
        for src, st in (("gate", r["solidcraft_gate_status"]), ("docs", r["solidcraft_docs_status"])):
            if st in ("not in docs table",):
                continue
            sc_pass = st == "pass"
            sc_unsup = st == "unsupported"
            if sc_unsup:
                continue
            if occt_pass != sc_pass:
                disagree.append((r["area"] + "/" + r["id"], src, r["status"], st))
    for d in disagree:
        print("DISAGREE", *d)


if __name__ == "__main__":
    main()
