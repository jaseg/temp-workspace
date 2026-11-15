#!/usr/bin/env python3
"""Case-level head-to-head analysis of the kicoil layout implementations on the full corpus (1008 cases).

Reads the per-case result JSON files of tests/run_corpus.py and the corpus definition (for family, shape, nominal trace
width and known issues), writes h2h.md next to this script and prints the headline numbers.

Run from the worktree:
    cd /tmp/claude-0/wt/next
    PYTHONPATH=src:tests /home/user/temp-workspace/kicoil/.venv/bin/python docs/comparison/scripts/h2h.py

Definitions used throughout:
- pass: status == 'pass' (the geomcheck verdict); everything else (fail, rejected, error, timeout) counts as not passing.
- thin: nominal trace width (annular width * layers / turns - clearance) below 0.1 mm, computed from the spec for every
  family. (The corpus tag 'thin' marks only the concave family's thin cases; in the main corpus the tag 'thin' is a shape
  tag of rect60x12, whose traces are not thin. Both facts are checked and reported.)
- failure kind classes, after tests/test_layout.py: 'conformance' is soft (coverage of the intended contour, not asserted
  by the pytest suite); 'clearance', 'via clearance', 'self short', 'self merge' are tolerated by the pytest suite only
  when the generator warned (the JSON does not record warnings, so they are reported as their own class 'warnable');
  every other kind is hard.
"""

import json
import math
import re
import sys
import statistics
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'tests'))
import corpus as corpus_mod  # noqa: E402

BENCH = Path(__import__('os').environ.get('KICOIL_BENCH', '/tmp/claude-0/bench/final'))
OUT = Path(__file__).resolve().parent / 'h2h.md'
IMPLS = {
    'original': 'original_full.json',
    'fixed': 'kicoil_full.json',
    'cornerflat': 'cornerflat_full.json',
    'optspan': 'geometry_alt_optspan_full.json',
    'jog': 'geometry_alt_jog_full.json',
}
NEW = ['fixed', 'cornerflat', 'optspan', 'jog']
WARNED_KINDS = ('clearance', 'via clearance', 'self short', 'self merge')
THIN_TRACE = 0.1

# Known-issue kinds of the corpus (test_layout.py) mapped to checker failure kinds: 'contour' (outer turn > 1.5 mm from
# the outline) and 'overshoot' are both part of the checker's 'conformance'.
KNOWN_KIND_MAP = {'contour': 'conformance', 'overshoot': 'conformance'}


# ---------------------------------------------------------------- corpus metadata

def shape_of(name):
    """ (family, shape, variant) from the case name """
    if name.startswith('concave_'):
        m = re.match(r'concave_(.*?)_a\d', name)
        return 'concave', m.group(1), 'base'
    if name.startswith('round_'):
        m = re.match(r'round_(.*?)_a\d', name)
        return 'round', m.group(1), 'base'
    m = re.match(r'(circle\d+x\d+)_n', name)
    if m:
        return 'main', m.group(1), 'base'
    for pre in ('sweep', 'dense'):
        if name.startswith(pre + '_'):
            m = re.match(pre + r'_(.*?)_[as]\d|' + pre + r'_(.*?)_n\d', name)
            return 'main', m.group(1) or m.group(2), pre
    if name.startswith('narrow_'):
        m = re.match(r'narrow_(.*?)_w', name)
        return 'main', 'narrow_' + m.group(1), 'base'
    m = re.match(r'(.*?)_a\d', name)
    return 'main', m.group(1), 'base'


def load_meta():
    cases = corpus_mod.corpus('full')
    meta = {}
    for c in cases:
        fam, shape, variant = shape_of(c['name'])
        tags = set(c['tags'])
        tag_fam = 'concave' if 'concave' in tags else 'round' if 'round' in tags else 'main'
        assert tag_fam == fam, (c['name'], tags)
        if c['shape'] == 'circle':
            aw = (c['outer_diameter'] - c['inner_diameter']) / 2
        else:
            aw = c['annular_width']
        pitch = aw * c['layers'] / c['turns']
        known = None
        if c.get('known_issue'):
            known = {'kinds': tuple(c['known_issue']['kinds']), 'reason': c['known_issue']['reason'],
                     'source': 'corpus_concave KNOWN_ISSUES/CASE_ISSUES'}
        elif c.get('known_failures'):
            known = {'kinds': tuple(c['known_failures']), 'reason': '; '.join(c['known_failures'].values()),
                     'source': 'corpus_round KNOWN_FAILURES'}
        meta[c['name']] = dict(family=fam, shape=shape, variant=variant, pitch=pitch,
                               trace=pitch - c['clearance'], thin=pitch - c['clearance'] < THIN_TRACE,
                               tag_thin='thin' in tags, known=known)
    return cases, meta


# ---------------------------------------------------------------- helpers

def passed(r):
    return r['status'] == 'pass'


def fmt_f(v, nd=3):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return '-'
    return f'{v:.{nd}f}'


def short(r):
    """ status, failure kinds, uncovered fraction, pitch ratio of one result, compact """
    st = r['status']
    if st in ('pass', 'fail'):
        k = ','.join(r.get('failures', [])) or 'pass'
        return f"{k} (unc {fmt_f(r.get('uncovered_fraction'))}, pr {fmt_f(r.get('pitch_ratio'))})"
    return st


def classes(kinds):
    hard = [k for k in kinds if k != 'conformance' and k not in WARNED_KINDS]
    warn = [k for k in kinds if k in WARNED_KINDS]
    soft = [k for k in kinds if k == 'conformance']
    return hard, warn, soft


def conf_causes(r):
    """ which conformance limits are exceeded (geomcheck.Report.conformance_ok) """
    out = []
    if r.get('uncovered_fraction', 0) >= 0.05:
        out.append('uncovered>=5%')
    if r.get('contour_hausdorff', 0) >= 1.25:
        out.append('undershoot>=1.25p')
    if r.get('overshoot', 0) >= 0.05:
        out.append('overshoot>=0.05mm')
    return out


def fail_class(r):
    """ single label for a non-passing result """
    if r['status'] != 'fail':
        return r['status']
    hard, warn, soft = classes(r['failures'])
    if hard:
        return 'hard'
    if warn:
        return 'warnable'
    return 'conformance only'


def md_table(header, rows):
    out = ['| ' + ' | '.join(map(str, header)) + ' |', '|' + '|'.join('---' for _ in header) + '|']
    out += ['| ' + ' | '.join(map(str, r)) + ' |' for r in rows]
    return '\n'.join(out)


def pct(values, q):
    """Percentile by linear interpolation between order statistics (numpy's default 'linear' method); for q=0.5
    this is the standard median. Used for every percentile in docs/COMPARISON.md."""
    values = sorted(v for v in values if v is not None and not math.isnan(v))
    if not values:
        return float('nan')
    pos = q * (len(values) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


# ---------------------------------------------------------------- main

def main():
    cases, meta = load_meta()
    names = [c['name'] for c in cases]
    res = {}
    for impl, fn in IMPLS.items():
        rs = json.load(open(BENCH / fn))
        d = {r['name']: r for r in rs}
        assert len(d) == len(rs) == len(names) and set(d) == set(names), impl
        res[impl] = d

    L = []  # markdown lines
    P = lambda *a: L.append(' '.join(str(x) for x in a))  # noqa: E731

    P('# Head-to-head: kicoil layout implementations, case by case')
    P()
    P('Generated by `docs/comparison/scripts/h2h.py` from `/tmp/claude-0/bench/final/*_full.json` '
      '(same 1008-case corpus and checker for every implementation). Every number below is computed by that script.')
    P()

    # ---- corpus facts
    fam_count = Counter(meta[n]['family'] for n in names)
    thin_names = [n for n in names if meta[n]['thin']]
    tagthin = [n for n in names if meta[n]['tag_thin']]
    P('## Corpus and definitions')
    P()
    P(f"- Cases: {len(names)} ({', '.join(f'{k} {v}' for k, v in fam_count.items())}). Family from the name prefix, "
      "checked against the 'round'/'concave' tags (no mismatch).")
    P(f"- **thin** here = nominal trace (annular width x layers / turns - clearance) < {THIN_TRACE} mm, computed for "
      f"every case: {len(thin_names)} cases ("
      + ', '.join(f'{k} {v}' for k, v in Counter(meta[n]['family'] for n in thin_names).items()) + ').')
    tag_and_thin = [n for n in tagthin if meta[n]['thin']]
    tag_not_thin = [n for n in tagthin if not meta[n]['thin']]
    thin_untagged = [n for n in thin_names if not meta[n]['tag_thin']]
    P(f"  - The corpus tag 'thin' is on {len(tagthin)} cases: {len(tag_and_thin)} concave cases that are thin by this "
      f"definition, and {len(tag_not_thin)} main-corpus cases of `rect60x12`, where 'thin' is a *shape* tag (a 5:1 "
      f"rectangle) and the traces are not thin (nominal trace {min(meta[n]['trace'] for n in tag_not_thin):.2f}"
      f"-{max(meta[n]['trace'] for n in tag_not_thin):.2f} mm).")
    P(f"  - {len(thin_untagged)} thin cases have no 'thin' tag: " + ', '.join(
        f"`{n}` ({meta[n]['trace']:.3f})" for n in thin_untagged) + '.')
    P("  - Headline numbers are given for **all 1008** cases and for **non-thin** cases (the computed definition), "
      f"i.e. {len(names) - len(thin_names)} cases.")
    P("- pass = checker status 'pass'. Not passing = fail, rejected (ValueError), error or timeout.")
    P("- Failure classes (tests/test_layout.py): *hard* = connectivity, short, stray via/copper, via, duplicate, "
      "crossing, backtrack, width, pad size, pad clearance, via offset, winding; *warnable* = clearance, via clearance, "
      "self short, self merge (the pytest suite tolerates these only if the generator warned; warnings are not in the "
      "JSON); *soft* = conformance (uncovered >= 5 %, undershoot >= 1.25 pitches or overshoot >= 0.05 mm).")
    P()

    subsets = {'all': names, 'non-thin': [n for n in names if not meta[n]['thin']]}

    # ---- status overview
    P('## Status overview')
    P()
    rows = []
    for impl in IMPLS:
        for sname, sub in subsets.items():
            st = Counter(res[impl][n]['status'] for n in sub)
            fc = Counter(fail_class(res[impl][n]) for n in sub if res[impl][n]['status'] == 'fail')
            rows.append([impl, sname, len(sub), st['pass'], f"{100*st['pass']/len(sub):.1f}%", st['fail'],
                         fc['hard'], fc['warnable'], fc['conformance only'], st['rejected'],
                         st['error'] + st.get('checker-error', 0), st['timeout']])
    P(md_table(['impl', 'subset', 'cases', 'pass', 'pass %', 'fail', 'fail: any hard', 'fail: warnable (no hard)',
                'fail: conformance only', 'rejected', 'error', 'timeout'], rows))
    P()
    rows = []
    for impl in IMPLS:
        row = [impl]
        for fam in ('main', 'round', 'concave'):
            for sname, sub in subsets.items():
                s = [n for n in sub if meta[n]['family'] == fam]
                row.append(f"{sum(passed(res[impl][n]) for n in s)}/{len(s)}")
        rows.append(row)
    P('Passes per family:')
    P()
    P(md_table(['impl', 'main all', 'main non-thin', 'round all', 'round non-thin', 'concave all',
                'concave non-thin'], rows))
    P()
    rej = {impl: {n for n in names if res[impl][n]['status'] == 'rejected'} for impl in IMPLS}
    same_rej = all(rej[i] == rej['fixed'] for i in NEW)
    P(f"Rejected sets of fixed, cornerflat, optspan and jog are {'identical' if same_rej else 'NOT identical'} "
      f"({len(rej['fixed'])} cases, {sum(meta[n]['thin'] for n in rej['fixed'])} of them thin); original rejects "
      f"{len(rej['original'])}.")
    P()

    # ---- pairwise matrix
    P('## Pairwise win/loss on pass status')
    P()
    P('Cell (row A, column B) = cases A passes and B does not. Net = row minus column.')
    P()
    impls = list(IMPLS)
    for sname, sub in subsets.items():
        P(f'**{sname}** ({len(sub)} cases)')
        P()
        rows = []
        for a in impls:
            row = [a]
            for b in impls:
                if a == b:
                    row.append('-')
                    continue
                w = sum(passed(res[a][n]) and not passed(res[b][n]) for n in sub)
                l_ = sum(passed(res[b][n]) and not passed(res[a][n]) for n in sub)
                row.append(f'{w} (net {w - l_:+d})')
            rows.append(row)
        P(md_table(['A \\ B'] + impls, rows))
        P()

    # ---- oracle
    P('## Oracle (best of all, picked per case) vs best single implementation')
    P()
    rows = []
    for sname, sub in subsets.items():
        best_single = max(impls, key=lambda i: sum(passed(res[i][n]) for n in sub))
        bs = sum(passed(res[best_single][n]) for n in sub)
        def oracle(group):
            return sum(any(passed(res[i][n]) for i in group) for n in sub)
        nonrej = [n for n in sub if n not in rej['fixed']]
        rows.append([sname, len(sub), len(nonrej), f'{best_single} {bs}', oracle(impls), oracle(NEW),
                     oracle(['cornerflat', 'jog']), oracle(['cornerflat', 'fixed']), oracle(['jog', 'fixed']),
                     oracle(['cornerflat', 'jog', 'optspan']),
                     sum(not any(passed(res[i][n]) for i in impls) for n in sub)])
    P(md_table(['subset', 'cases', 'not rejected by new impls', 'best single', 'oracle all 5', 'oracle 4 new',
                'oracle cf+jog', 'oracle cf+fixed', 'oracle jog+fixed', 'oracle cf+jog+optspan',
                'passed by none'], rows))
    P()
    # contribution of each implementation to the oracle: cases only it passes
    rows = []
    for sname, sub in subsets.items():
        row = [sname]
        for i in impls:
            row.append(sum(passed(res[i][n]) and not any(passed(res[j][n]) for j in impls if j != i) for n in sub))
        rows.append(row)
    P('Cases passed by exactly one implementation (its unique contribution to the oracle):')
    P()
    P(md_table(['subset'] + impls, rows))
    P()

    # ---- discordant cases cf vs jog / fixed
    def kinds_summary(sub_names, impl):
        c = Counter()
        for n in sub_names:
            r = res[impl][n]
            if r['status'] == 'fail':
                c.update(r['failures'])
            else:
                c[r['status']] += 1
        return ', '.join(f'{k} {v}' for k, v in c.most_common())

    def discord(a, b):
        P(f'## {a} vs {b}: cases where exactly one passes')
        P()
        for sname, sub in subsets.items():
            wa = sum(passed(res[a][n]) and not passed(res[b][n]) for n in sub)
            wb = sum(passed(res[b][n]) and not passed(res[a][n]) for n in sub)
            both = sum(passed(res[a][n]) and passed(res[b][n]) for n in sub)
            nei = sum(not passed(res[a][n]) and not passed(res[b][n]) for n in sub)
            P(f'- {sname}: both pass {both}, only {a} {wa}, only {b} {wb}, neither {nei}.')
        P()
        for winner, loser in ((a, b), (b, a)):
            sel = [n for n in names if passed(res[winner][n]) and not passed(res[loser][n])]
            P(f'### {winner} passes, {loser} does not: {len(sel)} cases '
              f'({sum(meta[n]["thin"] for n in sel)} thin)')
            P()
            P(f'{loser} failure classes: ' + ', '.join(
                f'{k} {v}' for k, v in Counter(fail_class(res[loser][n]) for n in sel).most_common()))
            P()
            P(f'{loser} failure kinds (cases per kind): ' + kinds_summary(sel, loser))
            P()
            conf = [n for n in sel if res[loser][n]['status'] == 'fail' and 'conformance' in res[loser][n]['failures']]
            cc = Counter(c for n in conf for c in conf_causes(res[loser][n]))
            if conf:
                P(f'{loser} conformance causes ({len(conf)} cases): ' + ', '.join(f'{k} {v}' for k, v in cc.most_common())
                  + f"; {loser} uncovered fraction median {statistics.median(res[loser][n]['uncovered_fraction'] for n in conf):.3f}"
                  f" vs {winner} {statistics.median(res[winner][n]['uncovered_fraction'] for n in conf):.3f} on these.")
                P()
            groups = defaultdict(list)
            for n in sel:
                groups[(meta[n]['family'], meta[n]['shape'])].append(n)
            rows = []
            for (fam, shape), ns in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
                rows.append([fam, shape, len(ns), kinds_summary(ns, loser)])
            P(f'By shape ({len(groups)} shapes):')
            P()
            P(md_table(['family', 'shape', 'cases', f'what {loser} fails (cases per kind)'], rows))
            P()
            rows = []
            for (fam, shape), ns in sorted(groups.items(), key=lambda kv: (kv[0])):
                for n in ns:
                    rows.append([fam, shape, f'`{n}`' + (' (thin)' if meta[n]['thin'] else '')
                                 + (' (known)' if meta[n]['known'] else ''),
                                 short(res[loser][n]), short(res[winner][n])])
            P('<details><summary>case list</summary>')
            P()
            P(md_table(['family', 'shape', 'case', f'{loser}', f'{winner}'], rows))
            P()
            P('</details>')
            P()

    discord('cornerflat', 'jog')
    discord('cornerflat', 'fixed')

    # ---- shapes failed by every implementation; failed only by cornerflat
    P('## Shapes and cases that every implementation fails')
    P()
    by_shape = defaultdict(list)
    for n in names:
        by_shape[(meta[n]['family'], meta[n]['shape'])].append(n)
    rows = []
    for key, ns in sorted(by_shape.items()):
        none_all = [n for n in ns if not any(passed(res[i][n]) for i in impls)]
        if none_all:
            rows.append([key[0], key[1], len(ns), len(none_all),
                         sum(res['fixed'][n]['status'] == 'rejected' for n in none_all),
                         sum(meta[n]['thin'] for n in none_all),
                         ' '.join(str(sum(passed(res[i][n]) for n in ns)) for i in impls)])
    zero_shapes = [r for r in rows if r[2] == r[3]]
    P(f"Shapes with no passing case in any implementation: "
      + (', '.join(f'{r[0]}/{r[1]} ({r[2]} cases)' for r in zero_shapes) or 'none') + '.')
    P()
    P('Per shape: cases passed by none of the five (and how many of those are rejected by all new implementations, '
      'or thin); last column = passes per implementation (' + ' '.join(impls) + ').')
    P()
    P(md_table(['family', 'shape', 'cases', 'passed by none', 'of which rejected', 'of which thin',
                'passes per impl'], rows))
    P()
    none_fail = [n for n in names if not any(passed(res[i][n]) for i in impls) and res['fixed'][n]['status'] == 'fail']
    P(f'Cases laid out but failed by every implementation ({len(none_fail)}; non-rejected): '
      'failure kinds of the four new implementations:')
    P()
    rows = []
    for n in none_fail:
        rows.append([f'`{n}`' + (' (thin)' if meta[n]['thin'] else '') + (' (known)' if meta[n]['known'] else '')]
                    + [short(res[i][n]) for i in NEW])
    P(md_table(['case'] + NEW, rows))
    P()
    def depth_frac(n):
        m = re.search(r'_a(\d\.\d+)_', n)
        if m:
            return f'a{float(m.group(1)):.1f}'
        return 'narrow (absolute width)' if n.startswith('narrow_') else 'circle' if n.startswith('circle') else 'dense (0.7) or sweep scale (0.6)'
    P('Laid-out cases failed by all five, by annular width fraction: ' + ', '.join(
        f'{k} {v}' for k, v in Counter(depth_frac(n) for n in none_fail).most_common())
      + f" (all cases: {', '.join(f'{k} {v}' for k, v in Counter(depth_frac(n) for n in names).most_common())}).")
    P()
    for i in NEW:
        fc = Counter(fail_class(res[i][n]) for n in none_fail)
        P(f"- {i} on these {len(none_fail)}: " + ', '.join(f'{k} {v}' for k, v in fc.most_common())
          + f"; median uncovered {statistics.median(res[i][n]['uncovered_fraction'] for n in none_fail if res[i][n]['status'] == 'fail'):.3f}, "
          f"median pitch ratio {statistics.median(res[i][n]['pitch_ratio'] for n in none_fail if res[i][n]['status'] == 'fail'):.3f}"
          " (over its laid-out cases)")
    best_unc = [min(res[i][n]['uncovered_fraction'] for i in NEW if res[i][n]['status'] == 'fail') for n in none_fail]
    best_pr = [max(res[i][n]['pitch_ratio'] for i in NEW if res[i][n]['status'] == 'fail') for n in none_fail]
    P(f"- best of the four per case: median uncovered {statistics.median(best_unc):.3f}, median pitch ratio "
      f"{statistics.median(best_pr):.3f}; {sum(u >= 0.2 for u in best_unc)} cases where even the best leaves >= 20 % "
      f"uncovered, {sum(r < 0.8 for r in best_pr)} where even the best pitch ratio is < 0.8.")
    only_conf = [n for n in none_fail if any(fail_class(res[i][n]) == 'conformance only' for i in NEW)]
    P(f"- {len(only_conf)} of the {len(none_fail)} have at least one new implementation failing on conformance alone "
      "(no hard or warnable kind).")
    P()

    P('## Cases that only cornerflat fails')
    P()
    for others, label in ((['fixed', 'optspan', 'jog'], 'fixed, optspan and jog all pass'),
                          (['fixed', 'jog'], 'fixed and jog both pass'),
                          (['jog'], 'jog passes')):
        sel = [n for n in names if not passed(res['cornerflat'][n]) and all(passed(res[o][n]) for o in others)]
        P(f"- cornerflat fails, {label}: {len(sel)} cases ({sum(meta[n]['thin'] for n in sel)} thin)")
    P()
    sel = [n for n in names if not passed(res['cornerflat'][n]) and all(passed(res[o][n]) for o in NEW if o != 'cornerflat')]
    groups = defaultdict(list)
    for n in sel:
        groups[(meta[n]['family'], meta[n]['shape'])].append(n)
    rows = [[f, s, len(ns), len(by_shape[(f, s)]), kinds_summary(ns, 'cornerflat')]
            for (f, s), ns in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
    P('Cornerflat fails while fixed, optspan and jog all pass, by shape:')
    P()
    P(md_table(['family', 'shape', 'cases', 'shape cases', 'cornerflat failure kinds'], rows))
    P()
    rows = [[f'`{n}`' + (' (thin)' if meta[n]['thin'] else ''), short(res['cornerflat'][n]),
             fmt_f(res['fixed'][n].get('pitch_ratio')), fmt_f(res['jog'][n].get('pitch_ratio'))] for n in sel]
    P(md_table(['case', 'cornerflat', 'fixed pitch ratio', 'jog pitch ratio'], rows))
    P()
    # the mirror: only X fails among the four new
    rows = []
    for i in NEW:
        s = [n for n in names if not passed(res[i][n]) and all(passed(res[o][n]) for o in NEW if o != i)]
        rows.append([i, len(s), sum(not meta[n]['thin'] for n in s),
                     len({(meta[n]['family'], meta[n]['shape']) for n in s})])
    P('For comparison, cases where one new implementation fails and the other three pass:')
    P()
    P(md_table(['impl', 'cases', 'non-thin', 'shapes'], rows))
    P()
    # shapes where cornerflat has fewer passes than all of the other new implementations
    rows = []
    for key, ns in sorted(by_shape.items()):
        p = {i: sum(passed(res[i][n]) for n in ns) for i in NEW}
        if all(p['cornerflat'] < p[o] for o in NEW if o != 'cornerflat'):
            rows.append([key[0], key[1], len(ns)] + [p[i] for i in NEW])
    P('Shapes on which cornerflat passes fewer cases than each of fixed, optspan and jog:')
    P()
    P(md_table(['family', 'shape', 'cases'] + NEW, rows) if rows else 'none')
    P()

    # ---- known issues
    P('## Known issues (corpus KNOWN_ISSUES / CASE_ISSUES / KNOWN_FAILURES)')
    P()
    known_names = [n for n in names if meta[n]['known']]
    P(f"{len(known_names)} cases carry a known issue: "
      + ', '.join(f'{k} {v}' for k, v in Counter(meta[n]['known']['source'] for n in known_names).items()) + '.')
    P()
    for src in sorted({meta[n]['known']['source'] for n in known_names}):
        kn = [n for n in known_names if meta[n]['known']['source'] == src]
        reasons = Counter((meta[n]['known']['kinds'], meta[n]['known']['reason']) for n in kn)
        for (kinds, reason), c in reasons.items():
            P(f"- {src}: {c} cases, kinds {list(kinds)}: {reason}")
    P()
    rows = []
    for impl in impls:
        fails = [n for n in names if res[impl][n]['status'] == 'fail']
        kf = [n for n in fails if meta[n]['known']]
        covered = []
        for n in kf:
            allowed = {KNOWN_KIND_MAP.get(k, k) for k in meta[n]['known']['kinds']}
            if set(res[impl][n]['failures']) <= allowed:
                covered.append(n)
        kpass = sum(passed(res[impl][n]) for n in known_names)
        covered_w = [n for n in kf if set(res[impl][n]['failures'])
                     <= {KNOWN_KIND_MAP.get(k, k) for k in meta[n]['known']['kinds']} | set(WARNED_KINDS)]
        rows.append([impl, len(fails), len(kf), len(covered), len(covered_w), len(kf) - len(covered_w), kpass,
                     sum(meta[n]['thin'] for n in kf)])
    P('Per implementation: failures on known-issue cases, and whether every failure kind is one the known issue names '
      "('contour'/'overshoot' map to the checker's 'conformance'):")
    P()
    P(md_table(['impl', 'fails (all)', 'fails on known-issue cases', 'fully explained by the known kinds',
                '... or by known + warnable kinds', 'with other kinds', 'known-issue cases passed', 'known-issue fails that are thin'], rows))
    P()
    rows = []
    for n in known_names:
        rows.append([f'`{n}`' + (' (thin)' if meta[n]['thin'] else ''), '/'.join(meta[n]['known']['kinds'])]
                    + [short(res[i][n]) for i in NEW])
    P('<details><summary>known-issue cases</summary>')
    P()
    P(md_table(['case', 'known kinds'] + NEW, rows))
    P()
    P('</details>')
    P()
    P('So known issues explain only a small part of the failures; the bulk of the failures (below, by class) is '
      'conformance on unlisted cases.')
    P()
    rows = []
    for impl in impls:
        fails = [n for n in names if res[impl][n]['status'] == 'fail' and not meta[n]['known']]
        fc = Counter(fail_class(res[impl][n]) for n in fails)
        rows.append([impl, len(fails), fc['hard'], fc['warnable'], fc['conformance only'],
                     sum(meta[n]['thin'] for n in fails)])
    P(md_table(['impl', 'fails without known issue', 'hard', 'warnable (no hard)', 'conformance only', 'thin'], rows))
    P()

    # ---- quality on common passes
    P('## Quality on cases both pass')
    P()
    P('pitch ratio = (narrowest emitted track width + clearance) / nominal pitch (higher is better, 1.0 = the whole '
      'nominal pitch becomes copper + clearance). uncovered = uncovered fraction of the intended band (lower is better). '
      'Paired: per case difference A - B; "A better" counts cases with a difference beyond 0.005 (pitch) or 0.002 '
      '(uncovered) in A\'s favour.')
    P()
    pairs = [('cornerflat', 'jog'), ('cornerflat', 'fixed'), ('jog', 'fixed'), ('cornerflat', 'optspan'),
             ('optspan', 'fixed'), ('jog', 'optspan'), ('fixed', 'original')]
    for sname, sub in subsets.items():
        rows = []
        for a, b in pairs:
            both = [n for n in sub if passed(res[a][n]) and passed(res[b][n])]
            if not both:
                continue
            pa = [res[a][n]['pitch_ratio'] for n in both]
            pb = [res[b][n]['pitch_ratio'] for n in both]
            ua = [res[a][n]['uncovered_fraction'] for n in both]
            ub = [res[b][n]['uncovered_fraction'] for n in both]
            dp = [x - y for x, y in zip(pa, pb)]
            du = [x - y for x, y in zip(ua, ub)]
            rows.append([f'{a} vs {b}', len(both),
                         f'{statistics.median(pa):.3f} / {statistics.median(pb):.3f}',
                         f'{pct(pa, 0.1):.3f} / {pct(pb, 0.1):.3f}',
                         f'{statistics.mean(pa):.3f} / {statistics.mean(pb):.3f}',
                         f'{statistics.median(dp):+.4f}',
                         f'{sum(d > 0.005 for d in dp)} / {sum(d < -0.005 for d in dp)}',
                         f'{statistics.median(ua):.4f} / {statistics.median(ub):.4f}',
                         f'{statistics.mean(ua):.4f} / {statistics.mean(ub):.4f}',
                         f'{sum(d < -0.002 for d in du)} / {sum(d > 0.002 for d in du)}'])
        P(f'**{sname}**')
        P()
        P(md_table(['A vs B', 'both pass', 'pitch med A/B', 'pitch p10 A/B', 'pitch mean A/B', 'pitch diff med',
                    'pitch: A better / B better', 'uncov med A/B', 'uncov mean A/B', 'uncov: A better / B better'],
                   rows))
        P()
    # by family for the key pairs (non-thin)
    rows = []
    for a, b in pairs[:3]:
        for fam in ('main', 'round', 'concave'):
            both = [n for n in subsets['non-thin'] if meta[n]['family'] == fam
                    and passed(res[a][n]) and passed(res[b][n])]
            if not both:
                continue
            pa = [res[a][n]['pitch_ratio'] for n in both]
            pb = [res[b][n]['pitch_ratio'] for n in both]
            ua = [res[a][n]['uncovered_fraction'] for n in both]
            ub = [res[b][n]['uncovered_fraction'] for n in both]
            dp = [x - y for x, y in zip(pa, pb)]
            rows.append([f'{a} vs {b}', fam, len(both), f'{statistics.median(pa):.3f} / {statistics.median(pb):.3f}',
                         f'{sum(d > 0.005 for d in dp)} / {sum(d < -0.005 for d in dp)}',
                         f'{statistics.median(ua):.4f} / {statistics.median(ub):.4f}'])
    P('By family (non-thin):')
    P()
    P(md_table(['A vs B', 'family', 'both pass', 'pitch med A/B', 'pitch: A better / B better', 'uncov med A/B'], rows))
    P()
    # Biggest pitch differences cf vs jog on common passes
    for a, b in (('cornerflat', 'jog'), ('cornerflat', 'fixed')):
        both = [n for n in subsets['non-thin'] if passed(res[a][n]) and passed(res[b][n])]
        diff = {n: res[a][n]['pitch_ratio'] - res[b][n]['pitch_ratio'] for n in both}
        fb = sorted((n for n in both if diff[n] < -1e-9), key=lambda n: diff[n])[:5]
        fa = sorted((n for n in both if diff[n] > 1e-9), key=lambda n: -diff[n])[:5]
        rows = [[f'`{n}`', f"{res[a][n]['pitch_ratio']:.3f}", f"{res[b][n]['pitch_ratio']:.3f}"] for n in fb + fa]
        P(f'Largest pitch-ratio differences {a} vs {b} on common non-thin passes ({len(fb)} most in favour of {b}, '
          f'then {len(fa)} most in favour of {a}; largest difference in favour of {b}: '
          f"{-min(diff.values()):.4f}):")
        P()
        P(md_table(['case', a, b], rows))
        P()

    # ---- taper placeholder
    P('## Tapering')
    P()
    P('Placeholder: fixed+taper results exist (`taper_kicoil_full.json`), the cornerflat+taper run is still going. '
      'Not part of this head-to-head.')
    P()

    OUT.write_text('\n'.join(L) + '\n')
    print(f'wrote {OUT} ({len(L)} lines)')


if __name__ == '__main__':
    main()
