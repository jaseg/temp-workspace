"""Breakdown of non-passing cases per implementation by annular depth token (a0.3/0.6/0.9), turns token and class,
and how many of cornerflat's failures also fail in every other new implementation.
Run: cd /tmp/claude-0/wt/next && PYTHONPATH=src:tests .venv/bin/python docs/comparison/scripts/fail_breakdown.py"""
import json, re, collections, statistics
F = __import__('os').environ.get('KICOIL_BENCH', __import__('os').environ.get('KICOIL_BENCH', '/tmp/claude-0/bench/final')).rstrip('/') + '/'
files = dict(fixed='kicoil_full.json', cornerflat='cornerflat_full.json', optspan='geometry_alt_optspan_full.json',
             jog='geometry_alt_jog_full.json')
R = {k: {r['name']: r for r in json.load(open(F + v))} for k, v in files.items()}
WARN = {'clearance', 'via clearance', 'self short', 'self merge'}
def depth(n):
    m = re.search(r'_a0\.(\d)', n)
    return f'a0.{m.group(1)}' if m else 'no depth token (circle, narrow_*, sweep_*, dense_*)'
def cls(r):
    f = set(r.get('failures', []))
    if r['status'] != 'fail': return r['status']
    if f - WARN - {'conformance'}: return 'hard'
    if f & WARN: return 'warnable'
    return 'conformance only'
for impl, d in R.items():
    c = collections.Counter((depth(n), cls(r)) for n, r in d.items() if r['status'] != 'pass')
    tot = collections.Counter(depth(n) for n in d)
    print(f'## {impl}')
    for dep in sorted(tot):
        row = {k[1]: v for k, v in c.items() if k[0] == dep}
        print(f'  {dep:52s} cases {tot[dep]:4d} not passing {sum(row.values()):4d} {dict(sorted(row.items()))}')
cf = R['cornerflat']
others = ['fixed', 'optspan', 'jog']
nonpass = [n for n, r in cf.items() if r['status'] != 'pass']
allfail = [n for n in nonpass if all(R[o][n]['status'] != 'pass' for o in others)]
print(f'cornerflat not passing: {len(nonpass)}; of these not passed by fixed, optspan or jog either: {len(allfail)}')
conf = [n for n, r in cf.items() if cls(r) == 'conformance only']
u = sorted(cf[n]['uncovered_fraction'] for n in conf)
print(f'cornerflat conformance-only: {len(conf)}; uncovered fraction median {statistics.median(u):.3f}; '
      f'>= 0.05: {sum(x >= 0.05 for x in u)}; at a0.9: {sum(depth(n)=="a0.9" for n in conf)}')
