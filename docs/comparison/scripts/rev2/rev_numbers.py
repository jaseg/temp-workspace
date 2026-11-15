"""Numbers for the second revision of docs/COMPARISON.md (the review fixes). Reads only the result JSON and the corpus.
Every percentile uses one rule: linear interpolation between order statistics (numpy's default; for q=0.5 it is the
standard median). Run from /tmp/claude-0/wt/next:
  PYTHONPATH=src:tests $PY docs/comparison/scripts/rev2/rev_numbers.py > docs/comparison/scripts/rev2/rev_numbers.out
"""
import json, math, re, statistics, sys
from collections import Counter
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))
import corpus

F = __import__('os').environ.get('KICOIL_BENCH', __import__('os').environ.get('KICOIL_BENCH', '/tmp/claude-0/bench/final')).rstrip('/') + '/'
FILES = {'original': 'original_full.json', 'fixed': 'kicoil_full.json', 'cornerflat': 'cornerflat_full.json',
         'optspan': 'geometry_alt_optspan_full.json', 'jog': 'geometry_alt_jog_full.json'}
R = {k: {r['name']: r for r in json.load(open(F + f))} for k, f in FILES.items()}
NEW = ['fixed', 'cornerflat', 'optspan', 'jog']
WARN = {'clearance', 'via clearance', 'self short', 'self merge'}
SOFT = {'conformance'}
specs = {c['name']: c for c in corpus.corpus('full')}
names = sorted(specs)
# Per-case process overhead of --timeout runs, measured by rev2/case_overhead.py (median of its two cases)
OVERHEAD = {'original': (0.214 + 0.218) / 2, 'optspan': (0.218 + 0.236) / 2, 'jog': (0.212 + 0.215) / 2}
TIMEOUT_RUNS = {'original', 'optspan', 'jog'}


def pct(v, q):
    v = sorted(x for x in v if x is not None and not math.isnan(x))
    if not v:
        return float('nan')
    p = q * (len(v) - 1); lo = int(math.floor(p)); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (p - lo)


med = lambda v: pct(list(v), 0.5)
fl = lambda i, n: set(R[i][n].get('failures') or [])
st = lambda i, n: R[i][n]['status']
fam = lambda n: 'round' if 'round' in specs[n]['tags'] else 'concave' if 'concave' in specs[n]['tags'] else 'main'
def depth(n):
    m = re.search(r'_a(0\.\d+)', n); return float(m.group(1)) if m else None
def turns(n):
    m = re.search(r'_n(\d+)', n); return int(m.group(1)) if m else None
from stats import nominal_trace
def thin(n): return nominal_trace(specs[n]) < 0.1
def hard(i, n): return st(i, n) == 'fail' and bool(fl(i, n) - WARN - SOFT)
def P(*a): print(*a)

P('== 1. pairwise sets: medians of uncovered fraction over the whole set and over the conformance subset')
for w, l in (('cornerflat', 'jog'), ('jog', 'cornerflat'), ('cornerflat', 'fixed')):
    s = [n for n in names if st(w, n) == 'pass' and st(l, n) != 'pass']
    laid = [n for n in s if st(l, n) == 'fail']
    conf = [n for n in laid if 'conformance' in fl(l, n)]
    cls = Counter('hard' if hard(l, n) else 'clr' if fl(l, n) & WARN else 'conf only' for n in laid)
    P(f'{w} passes, {l} fails: {len(s)} (laid out {len(laid)}; {dict(cls)}); over all: {l} {med(R[l][n]["uncovered_fraction"] for n in laid):.4f}'
      f' {w} {med(R[w][n]["uncovered_fraction"] for n in laid):.4f}; over the {len(conf)} with conformance: '
      f'{l} {med(R[l][n]["uncovered_fraction"] for n in conf):.4f} {w} {med(R[w][n]["uncovered_fraction"] for n in conf):.4f}')

P('\n== 2. hard failures: known-issue case? failure kind declared for the case?')
ki = {n for n, s in specs.items() if 'known_issue' in s or 'known_failures' in s}
def declared(n):
    s = specs[n]; return set(s['known_issue']['kinds']) if 'known_issue' in s else set(s.get('known_failures', {}))
for i in NEW:
    h = [n for n in names if hard(i, n)]
    decl = [n for n in h if (fl(i, n) - WARN - SOFT) <= declared(n)]
    P(f'{i:10s} hard {len(h)}; on known-issue cases {sum(n in ki for n in h)}; all hard kinds declared {len(decl)}; '
      f'not declared: {[(n, sorted(fl(i, n) - WARN - SOFT)) for n in h if n not in decl]}')

P('\n== 3. known-issue table: unexplained = failure kinds not declared and not clearance-class (conformance excluded, '
  'as in test_layout); variant B also counts conformance')
P(f'known-issue cases {len(ki)}: ' + str(Counter(fam(n) for n in ki)))
for i in NEW:
    a = [(n, sorted(fl(i, n) - declared(n) - WARN - SOFT)) for n in sorted(ki) if st(i, n) == 'fail' and fl(i, n) - declared(n) - WARN - SOFT]
    b = [(n, sorted(fl(i, n) - declared(n) - WARN)) for n in sorted(ki) if st(i, n) == 'fail' and fl(i, n) - declared(n) - WARN]
    P(f'{i:10s} passed {sum(st(i, n) == "pass" for n in ki)}; unexplained (A) {len(a)} {a}')
    P(f'{"":10s} with conformance (B) {len(b)}; B only: {[x for x in b if x[0] not in dict(a)]}')
P('hard failures outside known-issue cases: ' + str({i: sum(hard(i, n) for n in names if n not in ki) for i in NEW}))

P('\n== 4. self shorts: mechanism, turns, depth, trace width')
for i in NEW:
    ss = [n for n in names if st(i, n) == 'fail' and 'self short' in fl(i, n)]
    ownvia = [n for n in ss if R[i][n]['own_via_shorts'] == R[i][n]['self_shorts']]
    mixed = [n for n in ss if 0 < R[i][n]['own_via_shorts'] < R[i][n]['self_shorts']]
    tw = sorted((R[i][n]['trace_width'], n) for n in ss)
    P(f'{i:10s} {len(ss)} cases; turns {dict(sorted(Counter(turns(n) for n in ss).items()))}; at a0.90 '
      f'{sum(depth(n) == 0.9 for n in ss)}; n3 at a0.90 {sum(depth(n) == 0.9 and turns(n) == 3 for n in ss)}; '
      f'also conformance {sum("conformance" in fl(i, n) for n in ss)}; own-via only {len(ownvia)} {ownvia}; mixed {len(mixed)}; '
      f'narrowest traces {[(round(w, 2), n) for w, n in tw[:3]]}')
    only = [n for n in ss if fl(i, n) == {'self short'}]
    P(f'{"":10s} self short is the only failure: {len(only)}: '
      + ', '.join(f'{n} ({"own-via" if R[i][n]["own_via_shorts"] == R[i][n]["self_shorts"] else "mixed" if R[i][n]["own_via_shorts"] else "turn"})' for n in only))
P('cornerflat clearance-class cases with no hard failure, by kind and mechanism:')
c = [n for n in names if st('cornerflat', n) == 'fail' and fl('cornerflat', n) & WARN and not hard('cornerflat', n)]
r = R['cornerflat']
P(f'  n={len(c)}; at a0.90 {sum(depth(n) == 0.9 for n in c)}; self short with a turn-type contact '
  f'{sum(r[n]["self_shorts"] > r[n]["own_via_shorts"] for n in c)}; own-via-only self short '
  f'{sum(r[n]["self_shorts"] > 0 and r[n]["self_shorts"] == r[n]["own_via_shorts"] for n in c)}; self merge '
  f'{sum("self merge" in fl("cornerflat", n) for n in c)}; via clearance {sum("via clearance" in fl("cornerflat", n) for n in c)}; '
  f'track clearance {sum("clearance" in fl("cornerflat", n) for n in c)}')
P('fixed cases with track or via clearance: ' + str([(n, sorted(fl('fixed', n) & {'clearance', 'via clearance'})) for n in names
                                                      if st('fixed', n) == 'fail' and fl('fixed', n) & {'clearance', 'via clearance'}]))

P('clearance-class cases with no hard failure, per implementation:')
for i in NEW:
    c = [n for n in names if st(i, n) == 'fail' and fl(i, n) & WARN and not hard(i, n)]
    r = R[i]
    turn_ss = [n for n in c if r[n]['self_shorts'] > r[n]['own_via_shorts']]
    P(f'  {i:10s} n={len(c)} (non-thin {sum(not thin(n) for n in c)}); at a0.90 {sum(depth(n) == 0.9 for n in c)}; '
      f'turn-type self short {len(turn_ss)}; own-via-only self short '
      f'{sum(r[n]["self_shorts"] > 0 and r[n]["self_shorts"] == r[n]["own_via_shorts"] for n in c)}; self merge '
      f'{sum("self merge" in fl(i, n) for n in c)}; via clearance {sum("via clearance" in fl(i, n) for n in c)}; '
      f'track clearance {sum("clearance" in fl(i, n) for n in c)}; '
      f'turn-type self short only (no other clearance kind) {sum(fl(i, n) & WARN == {"self short"} and r[n]["own_via_shorts"] == 0 for n in c)}')
P('winding-angle distance of turn-type self-short contacts in the checker notes (first notes only):')
for i in NEW:
    v = [float(m.group(1)) for n in names if st(i, n) == 'fail' and 'self short' in fl(i, n)
         for x in R[i][n]['notes'] for m in [re.search(r'touches itself ([\d.]+) turns further on', x)] if m]
    P(f'  {i:10s} {len(v)} notes: min {min(v):.2f} max {max(v):.2f}; >= 0.46: {sum(x >= 0.46 for x in v)}')
P('pass counts if every case whose only failure is a turn-type or mixed self short passed (upper bound):')
for i in NEW:
    base = sum(st(i, n) == 'pass' for n in names)
    add = [n for n in names if st(i, n) == 'fail' and fl(i, n) == {'self short'} and R[i][n]['self_shorts'] > R[i][n]['own_via_shorts']]
    pure = [n for n in add if R[i][n]['own_via_shorts'] == 0]
    P(f'  {i:10s} with any turn-type contact: {base} + {len(add)} = {base + len(add)}; '
      f'with no own-via contact (the own-via rule would still fail the others): {base} + {len(pure)} = {base + len(pure)}')

P('\n== 5. jog via offsets (final run)')
for n in names:
    if st('jog', n) == 'fail' and 'via offset' in fl('jog', n):
        P(n, round(R['jog'][n]['via_misplacement'], 3), [x for x in R['jog'][n]['notes'] if 'via center' in x][:2])

P('\n== 6. quality where both pass')
def common(a, b): return [n for n in names if st(a, n) == 'pass' and st(b, n) == 'pass']
for a, b in (('cornerflat', 'jog'), ('cornerflat', 'fixed'), ('jog', 'fixed'), ('fixed', 'original')):
    cm = common(a, b)
    P(f'{a}/{b}: {len(cm)} common; median pitch ratio {med(R[a][n]["pitch_ratio"] for n in cm):.4f} / '
      f'{med(R[b][n]["pitch_ratio"] for n in cm):.4f}; raw: {a} lower pitch ratio on '
      f'{sum(R[a][n]["pitch_ratio"] < R[b][n]["pitch_ratio"] for n in cm)}, higher uncovered on '
      f'{sum(R[a][n]["uncovered_fraction"] > R[b][n]["uncovered_fraction"] for n in cm)}; beyond thresholds: '
      f'{sum(R[a][n]["pitch_ratio"] < R[b][n]["pitch_ratio"] - 0.005 for n in cm)} / '
      f'{sum(R[a][n]["uncovered_fraction"] > R[b][n]["uncovered_fraction"] + 0.002 for n in cm)}')
cm = common('cornerflat', 'fixed')
worst = max(cm, key=lambda n: R['fixed'][n]['pitch_ratio'] - R['cornerflat'][n]['pitch_ratio'])
P(f'  largest cornerflat pitch deficit vs fixed: {worst} {R["cornerflat"][worst]["pitch_ratio"]:.4f} vs {R["fixed"][worst]["pitch_ratio"]:.4f}; '
  f'uncovered {R["cornerflat"][worst]["uncovered_fraction"]:.4f} vs {R["fixed"][worst]["uncovered_fraction"]:.4f}')
worst = max(cm, key=lambda n: R['cornerflat'][n]['uncovered_fraction'] - R['fixed'][n]['uncovered_fraction'])
P(f'  largest cornerflat uncovered excess vs fixed: {worst} {R["cornerflat"][worst]["uncovered_fraction"]:.4f} vs {R["fixed"][worst]["uncovered_fraction"]:.4f}')
P('  max raw deficits of cornerflat vs fixed: pitch ratio %.5f, uncovered %.5f' % (
    max(R['fixed'][n]['pitch_ratio'] - R['cornerflat'][n]['pitch_ratio'] for n in cm),
    max(R['cornerflat'][n]['uncovered_fraction'] - R['fixed'][n]['uncovered_fraction'] for n in cm)))
P('DC resistance proxy (total_length / trace_width), jog / cornerflat on common passes:')
cm = common('cornerflat', 'jog')
rp = [(R['jog'][n]['total_length'] / R['jog'][n]['trace_width']) / (R['cornerflat'][n]['total_length'] / R['cornerflat'][n]['trace_width']) for n in cm]
lr = [R['jog'][n]['total_length'] / R['cornerflat'][n]['total_length'] for n in cm]
wr = [R['jog'][n]['trace_width'] / R['cornerflat'][n]['trace_width'] for n in cm]
P(f'  n={len(cm)} ratio p10 {pct(rp, .1):.4f} median {med(rp):.4f} p90 {pct(rp, .9):.4f}; jog lower by > 0.5 % on '
  f'{sum(x < 0.995 for x in rp)}, higher by > 0.5 % on {sum(x > 1.005 for x in rp)}; length ratio median {med(lr):.4f} '
  f'p90 {pct(lr, .9):.4f}; trace width ratio median {med(wr):.4f} p90 {pct(wr, .9):.4f}')

P('\n== 7. section 3 / 5 medians')
for i in FILES:
    laid = [n for n in names if st(i, n) in ('pass', 'fail')]
    P(f'{i:10s} laid out {len(laid)}: pitch p10 {pct([R[i][n]["pitch_ratio"] for n in laid], .1):.4f} median '
      f'{med(R[i][n]["pitch_ratio"] for n in laid):.4f}; uncovered median {med(R[i][n]["uncovered_fraction"] for n in laid):.4f}'
      f' p90 {pct([R[i][n]["uncovered_fraction"] for n in laid], .9):.4f}')
for i in ('fixed', 'cornerflat'):
    m = [n for n in names if fam(n) == 'main' and st(i, n) in ('pass', 'fail')]
    P(f'{i} main laid {len(m)}: uncovered median {med(R[i][n]["uncovered_fraction"] for n in m):.4f}, pitch p10 '
      f'{pct([R[i][n]["pitch_ratio"] for n in m], .1):.4f}')
co = [n for n in names if st('cornerflat', n) == 'fail' and fl('cornerflat', n) == {'conformance'}]
P(f'cornerflat conformance-only {len(co)}: median uncovered {med(R["cornerflat"][n]["uncovered_fraction"] for n in co):.4f}; '
  f'>= 0.05: {sum(R["cornerflat"][n]["uncovered_fraction"] >= 0.05 for n in co)}; a0.90 {sum(depth(n) == 0.9 for n in co)}')

P('\n== 8. runtime over laid-out cases (pass or fail); timeouts listed separately')
for i in FILES:
    laid = [n for n in names if st(i, n) in ('pass', 'fail')]
    t = [R[i][n]['gen_time'] for n in laid]
    to = [(n, R[i][n].get('time')) for n in names if st(i, n) == 'timeout']
    nt = [R[i][n]['gen_time'] for n in laid if not thin(n)]
    fm = {f: med(R[i][n]['gen_time'] for n in laid if fam(n) == f) for f in ('main', 'round', 'concave')}
    P(f'{i:10s} n={len(t)} min {min(t):.4f} median {med(t):.4f} p90 {pct(t, .9):.4f} max {max(t):.2f} max non-thin '
      f'{max(nt):.2f} sum {sum(t):.0f} >10 s {sum(x > 10 for x in t)}; family medians '
      f'{fm["main"]:.4f} / {fm["round"]:.4f} / {fm["concave"]:.4f}; timeouts {to}')
    if i in TIMEOUT_RUNS:
        o = OVERHEAD[i]; ta = [x - o for x in t]
        fa = {f: med(R[i][n]['gen_time'] - o for n in laid if fam(n) == f) for f in ('main', 'round', 'concave')}
        P(f'{"":10s} minus {o:.4f} s per case: median {med(ta):.4f} p90 {pct(ta, .9):.4f} sum {sum(ta):.0f} '
          f'(overhead total {o * len(t):.0f}); family medians {fa["main"]:.4f} / {fa["round"]:.4f} / {fa["concave"]:.4f}; '
          f'>10 s {sum(x > 10 for x in ta)}')
P('circle cases median gen_time: ' + ', '.join(
    f'{i} {med(R[i][n]["gen_time"] for n in names if n.startswith("circle") and st(i, n) in ("pass", "fail")):.4f}' for i in FILES))

P('\n== 9. render 3 timings in the benchmark JSON')
for i in FILES:
    r = R[i]['round_dense2500_a0.60_n21k8']; P(f'{i:10s} {r["status"]} gen_time {r.get("gen_time")}')
P('\n== 10. the optspan timeout case in the other runs')
for i in FILES:
    r = R[i]['round_dense2500_a0.90_n16k5']; P(f'{i:10s} {r["status"]} gen_time {r.get("gen_time")} time {r.get("time")}')
