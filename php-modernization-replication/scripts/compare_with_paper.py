"""Paired file-level tests of Opus 5.5 against every approach in the paper.

    compare_with_paper.py RESULTS_DIR

Uses the authors' published per-file compatibility (data/paper_per_file.csv, from their
replication package) for the originals, the five LLMs and Rector, and RESULTS_DIR/per_file.csv
for Opus. Exact McNemar, Holm over all 28 pairs, bootstrap gap interval (as the paper).
Writes RESULTS_DIR/paired_tests_with_paper.md.
"""

import csv
import itertools
import sys
from pathlib import Path

from analyze import bootstrap_gap, holm, mcnemar_exact

ROOT = Path(__file__).resolve().parent.parent
NAMES = {
    "original": "Unchanged originals",
    "claude_sonnet_4_20250514": "Claude Sonnet 4",
    "gemini_2_5_flash": "Gemini 2.5 Flash",
    "gemini_2_5_pro": "Gemini 2.5 Pro",
    "gpt_5_codex": "GPT-5 Codex",
    "meta_llama_llama_3_3_70b_instruct": "Llama 3.3 70B",
    "Rector_Baseline": "Rector",
    "opus_5_5_high": "Claude Opus 5.5 (high)",
}


def main():
    res = Path(sys.argv[1])
    comp = {}
    with open(ROOT / "data" / "paper_per_file.csv") as fh:
        for r in csv.DictReader(fh):
            comp.setdefault(r["variant"], {})[r["file_id"]] = r["file_has_no_failed_tests"] == "yes"
    with open(res / "per_file.csv") as fh:
        rows = list(csv.DictReader(fh))
    comp["opus_5_5_high"] = {r["file"]: r["opus_5_5_high"] == "1" for r in rows}
    ours_orig = {r["file"]: r["original"] == "1" for r in rows}
    assert ours_orig == comp["original"], "originals differ from the published baseline"
    fids = sorted(ours_orig)
    vec = {v: [comp[v][f] for f in fids] for v in NAMES}
    pairs = {(a, b): mcnemar_exact(vec[a], vec[b]) for a, b in itertools.combinations(NAMES, 2)}
    adj = holm(pairs)
    L = ["# Opus 5.5 against the paper's approaches (file-level, paired)\n"]
    L.append("| Approach | Compatible | Gap to originals [95% CI] |")
    L.append("|---|--:|---|")
    for v in NAMES:
        g = "--"
        if v != "original":
            lo, hi = bootstrap_gap(vec["original"], vec[v])
            g = f"{sum(vec['original']) - sum(vec[v])} [{lo}, {hi}]"
        L.append(f"| {NAMES[v]} | {sum(vec[v])} | {g} |")
    L.append(f"\nExact McNemar, Holm-adjusted over all {len(pairs)} pairs; pairs with Opus:\n")
    L.append("| Opus 5.5 vs | Opus better only | Other better only | p (Holm) |")
    L.append("|---|--:|--:|--:|")
    for (a, b), p in pairs.items():
        if "opus_5_5_high" not in (a, b):
            continue
        o = a if a != "opus_5_5_high" else b
        x, y = vec["opus_5_5_high"], vec[o]
        L.append(f"| {NAMES[o]} | {sum(i and not j for i, j in zip(x, y))} | {sum(j and not i for i, j in zip(x, y))} | {adj[(a, b)]:.2g} |")
    (res / "paired_tests_with_paper.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
