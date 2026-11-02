"""Tables I-IV of arXiv:2610.40269 for every variant run through the hidden checks.

    analyze.py RESULTS_DIR

Reads RESULTS_DIR/runtime/<variant>/junit.xml (variant "original" is the no-change
baseline), RESULTS_DIR/runtime/<variant>-lintfb/junit.xml (lint-fallback runs, optional),
RESULTS_DIR/findings_<variant>.json (Rector findings on each variant's output),
RESULTS_DIR/lint_<variant>.json, and data/rule_necessity.json. Writes RESULTS_DIR/tables.md
and RESULTS_DIR/per_file.csv.
"""

import csv
import itertools
import json
import random
import re
import sys
import xml.etree.ElementTree as ET
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "original"
LABELS = {
    "original": "Unchanged originals",
    "opus_5_5_high": "Claude Opus 5.5 (high)",
    "Rector_Baseline": "Rector",
}
ORDER = list(LABELS)
NON_LLM = {"original", "Rector_Baseline"}


# ---------------------------------------------------------------- checks


def is_fingerprint(name):  # (collect_stats.detect_test_category)
    low = name.lower()
    return "semantic" in low or "fingerprint" in low


def parse_junit(path):
    """{(file_id, class, method): failure text or None}"""
    out = {}
    for tc in ET.parse(path).getroot().iter("testcase"):
        m = re.search(r"(\d{3})_", tc.get("file", "") or tc.get("class", ""))
        if not m:
            continue  # (SetupSmokeTest: not one of the 630 checks)
        fid = m.group(1)
        fail = [c for c in tc if c.tag in ("failure", "error")]
        skip = [c for c in tc if c.tag == "skipped"]
        text = None
        if fail:
            text = "\n".join((c.get("message") or "") + "\n" + (c.text or "") for c in fail)
        elif skip:
            text = "SKIPPED"
        out[(fid, tc.get("class", ""), tc.get("name", ""))] = text
    return out


def per_file(checks, keep=lambda k: True):
    files = {}
    for k, v in checks.items():
        if keep(k):
            files.setdefault(k[0], True)
            files[k[0]] &= v is None
    return files


# ---------------------------------------------------------------- failure causes

LOAD_RE = re.compile(
    r"ParseError|syntax error|unexpected token|unexpected end of file|"
    r"must be compatible with|Cannot redeclare|Cannot declare|cannot have a return type|"
    r"must have a return type|cannot be nullable|cannot have type|cannot be declared|"
    r"Cannot use .* as default value|Cannot (?:re)?define|Access level to .* must be|"
    r"Abstract function .* cannot|Cannot use the (?:static|final|abstract) modifier|"
    r"Cannot make (?:non )?static|Property .* cannot have type|Type .* cannot be|"
    r"PHP Fatal error:\s+(?!Uncaught)",
    re.I,
)
TYPE_RE = re.compile(r"TypeError|ArgumentCountError|ValueError|must be of type|Return value", re.I)
IFACE_RE = re.compile(
    r"Call to undefined method|Cannot access (?:private|protected)|Call to (?:private|protected)|"
    r"Class .* not found|Undefined property|Call to undefined function|Undefined constant|"
    r"Interface .* not found|Cannot instantiate",
    re.I,
)
OUT_RE = re.compile(r"Failed asserting|is not identical|is not equal|Comparison Failure", re.I)


def cause(text, lint_ok):
    if not lint_ok or LOAD_RE.search(text or ""):
        return "Load-time rejection"
    if TYPE_RE.search(text):
        return "Runtime type error"
    if IFACE_RE.search(text):
        return "Interface change"
    if OUT_RE.search(text):
        return "Output mismatch"
    if (text or "").strip():
        return "Other"
    return "Unclassified"


# ---------------------------------------------------------------- statistics


def mcnemar_exact(a, b):
    """Two-sided exact McNemar on paired booleans."""
    n01 = sum(1 for x, y in zip(a, b) if x and not y)
    n10 = sum(1 for x, y in zip(a, b) if y and not x)
    n = n01 + n10
    if n == 0:
        return 1.0
    k = min(n01, n10)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n)


def holm(pvals):
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, adj, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        adj[k] = run
    return adj


def bootstrap_gap(base, var, n=10000, seed=42):
    rng = random.Random(seed)
    d = [int(x) - int(y) for x, y in zip(base, var)]
    stats = sorted(sum(d[rng.randrange(len(d))] for _ in d) for _ in range(n))
    return stats[int(0.025 * n)], stats[int(0.975 * n) - 1]


# ---------------------------------------------------------------- main


def main():
    res = Path(sys.argv[1])
    rt = res / "runtime"
    runs = {p.name: parse_junit(p / "junit.xml") for p in rt.iterdir() if (p / "junit.xml").exists()}
    base = runs[BASE]
    variants = [v for v in ORDER if v in runs]
    fids = sorted({k[0] for k in base})
    nec = json.loads((ROOT / "data" / "rule_necessity.json").read_text())

    def group(rule):
        return (
            "required" if rule in nec["required"]
            else "deprecated" if rule in nec["deprecated"] else "optional"
        )  # fmt: skip

    php = lambda rules: {r for r in rules if r.startswith("Rector\\Php")}  # noqa: E731
    orig_find = json.loads((res / "findings_original.json").read_text())
    orig_rules = {f[:3]: php(v["rules"]) for f, v in orig_find.items()}
    n_find = sum(map(len, orig_rules.values()))
    grp_n = {g: sum(group(r) == g for s in orig_rules.values() for r in s) for g in ("required", "deprecated", "optional")}
    req_files = {f for f, s in orig_rules.items() if any(group(r) == "required" for r in s)}

    base_file = per_file(base)
    base_ok = [base_file[f] for f in fids]
    rows, comp, per_file_rows = {}, {}, {f: {"file": f} for f in fids}
    t2, t3, t4 = {}, {}, {}
    for v in variants:
        ch = runs[v]
        assert set(ch) == set(base), f"{v}: check set differs from original"
        vf = per_file(ch)
        comp[v] = [vf[f] for f in fids]
        for f in fids:
            per_file_rows[f][v] = int(vf[f])
        trans = {"pres": 0, "reg": 0, "rep": 0, "unrep": 0}
        for k, t in ch.items():
            b_ok, v_ok = base[k] is None, t is None
            trans[{(1, 1): "pres", (1, 0): "reg", (0, 1): "rep", (0, 0): "unrep"}[(b_ok, v_ok)]] += 1
        broken = sum(base_file[f] and not vf[f] for f in fids)
        fixed = sum(vf[f] and not base_file[f] for f in fids)
        n_pass, n_fail = trans["pres"] + trans["reg"], trans["rep"] + trans["unrep"]
        row = {
            "compatible": sum(comp[v]),
            "broken": broken,
            "fixed": fixed,
            "pres": 100 * trans["pres"] / n_pass,
            "rep": 100 * trans["rep"] / n_fail,
            "reg": trans["reg"],
            "checks_pass": trans["pres"] + trans["rep"],
        }
        if v != BASE:
            lo, hi = bootstrap_gap(base_ok, comp[v])
            row["gap"] = f"{sum(base_ok) - sum(comp[v])} [{lo}, {hi}]"
        # Necessity split of broken/fixed files
        row["req_split"] = (
            sum(vf[f] and not base_file[f] for f in req_files),
            sum(base_file[f] and not vf[f] for f in req_files),
            sum(base_file[f] and not vf[f] for f in fids if f not in req_files),
            sum(base_file[f] for f in fids if f not in req_files),
            sum(vf[f] and not base_file[f] for f in fids if f not in req_files),
        )
        rows[v] = row
        # Table II: no fingerprint checks; lint fallback
        nofp = per_file(ch, lambda k: not is_fingerprint(k[2]))
        lfb = runs.get(v + "-lintfb")
        t2[v] = (sum(nofp.values()), sum(per_file(lfb).values()) if lfb else None)
        # Resolution + Table III
        ff = res / f"findings_{v}.json"
        if v not in NON_LLM and ff.exists():
            fnd = {k[:3]: val for k, val in json.loads(ff.read_text()).items()}
            resolved = {"required": 0, "deprecated": 0, "optional": 0}
            new, unparse = 0, 0
            for f, orules in orig_rules.items():
                if f not in fnd or "error" in fnd[f]:
                    unparse += 1
                    continue
                rem = php(fnd[f]["rules"])
                for r in orules - rem:
                    resolved[group(r)] += 1
                new += len(rem - orules)
            row["resolution"] = 100 * sum(resolved.values()) / n_find
            t3[v] = {g: 100 * resolved[g] / grp_n[g] for g in resolved} | {"new": new, "unparse": unparse}
        # Table IV: regression causes
        lint = {}
        lf = res / f"lint_{v}.json"
        if lf.exists():
            lint = {k[:3]: ok for k, ok in json.loads(lf.read_text()).items()}
        causes, files_reg, files_load = {}, set(), set()
        for k, t in ch.items():
            if base[k] is None and t is not None:
                c = cause(t, lint.get(k[0], True))
                causes[c] = causes.get(c, 0) + 1
                files_reg.add(k[0])
                if c == "Load-time rejection":
                    files_load.add(k[0])
        t4[v] = (causes, len(files_reg), len(files_load))

    # Pairwise exact McNemar + Holm over all pairs
    pairs = {(a, b): mcnemar_exact(comp[a], comp[b]) for a, b in itertools.combinations(variants, 2)}
    adj = holm(pairs)

    L = []
    L.append(f"# Results ({len(fids)} files, {len(base)} checks, {n_find} findings)\n")
    L.append("## Table I: behavioural compatibility and resolution\n")
    L.append("| Approach | Compatible | Gap [95% CI] | Broken | Fixed | Preservation | Repair | Regressions | Resolution |")
    L.append("|---|--:|---|--:|--:|--:|--:|--:|--:|")
    for v in variants:
        r = rows[v]
        res_s = f"{r['resolution']:.1f}%" if "resolution" in r else ("0.0%" if v == BASE else "--")
        L.append(
            f"| {LABELS[v]} | {r['compatible']} | {r.get('gap', '--')} | {r['broken']} | {r['fixed']} "
            f"| {r['pres']:.1f}% | {r['rep']:.1f}% | {r['reg']} | {res_s} |"
        )
    L.append(f"\nChecks passing on the originals: {rows[BASE]['checks_pass']} of {len(base)}.\n")
    L.append("## Table II: compatible files under the sensitivity analyses\n")
    L.append("| Approach | All checks | No fingerprint | Lint fallback |")
    L.append("|---|--:|--:|--:|")
    for v in variants:
        lfb = t2[v][1] if t2[v][1] is not None else (rows[v]["compatible"] if v in NON_LLM else "--")
        L.append(f"| {LABELS[v]} | {rows[v]['compatible']} | {t2[v][0]} | {lfb} |")
    L.append(f"\n## Table III: resolution by necessity (required n={grp_n['required']}, deprecated n={grp_n['deprecated']}, optional n={grp_n['optional']})\n")
    L.append("| Model | Required | Deprecated | Optional | New | Unparseable files |")
    L.append("|---|--:|--:|--:|--:|--:|")
    for v in variants:
        if v in t3:
            t = t3[v]
            L.append(f"| {LABELS[v]} | {t['required']:.1f}% | {t['deprecated']:.1f}% | {t['optional']:.1f}% | {t['new']} | {t['unparse']} |")
    L.append(f"\n## Files with / without a required finding ({len(req_files)} files with one)\n")
    L.append("| Approach | Fixed (req.) | Broken (req.) | Broken (no req.) / compatible no-req. | Fixed (no req.) |")
    L.append("|---|--:|--:|--:|--:|")
    for v in variants:
        if v == BASE:
            continue
        a, b, c, d, e = rows[v]["req_split"]
        L.append(f"| {LABELS[v]} | {a} | {b} | {c} / {d} ({100 * c / d:.0f}%) | {e} |")
    L.append("\n## Table IV: regression causes (checks)\n")
    cats = ["Load-time rejection", "Runtime type error", "Interface change", "Output mismatch", "Other", "Unclassified"]
    vs = [v for v in variants if v != BASE]
    L.append("| Cause | " + " | ".join(LABELS[v] for v in vs) + " |")
    L.append("|---|" + "--:|" * len(vs))
    for c in cats:
        L.append(f"| {c} | " + " | ".join(str(t4[v][0].get(c, 0)) for v in vs) + " |")
    L.append("| Total regressions | " + " | ".join(str(rows[v]["reg"]) for v in vs) + " |")
    L.append("| Files with regressions | " + " | ".join(str(t4[v][1]) for v in vs) + " |")
    L.append("| ... with load-time rejection | " + " | ".join(str(t4[v][2]) for v in vs) + " |")
    L.append(f"\n## Pairwise exact McNemar on file compatibility (Holm over {len(pairs)} pairs)\n")
    L.append("| A | B | compatible A | compatible B | p | p (Holm) |")
    L.append("|---|---|--:|--:|--:|--:|")
    for (a, b), p in sorted(pairs.items(), key=lambda kv: kv[1]):
        L.append(f"| {LABELS[a]} | {LABELS[b]} | {sum(comp[a])} | {sum(comp[b])} | {p:.2g} | {adj[(a, b)]:.2g} |")
    (res / "tables.md").write_text("\n".join(L) + "\n")
    with open(res / "per_file.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, ["file", *variants])
        w.writeheader()
        w.writerows(per_file_rows.values())
    print("\n".join(L))


if __name__ == "__main__":
    main()
