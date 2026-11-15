"""Tapering numbers for COMPARISON.md section 8 (fixed+taper and cornerflat+taper, full corpus)."""
import json, sys, collections
D = sys.argv[1] if len(sys.argv) > 1 else __import__('os').environ.get('KICOIL_BENCH', '/tmp/claude-0/bench/final')
A = json.load(open(f'{D}/taper_kicoil_full.json'))
B = json.load(open(f'{D}/taper_cornerflat_full.json'))
def fam(r):
    return 'round' if r['name'].startswith('round_') else 'concave' if r['name'].startswith('concave_') else 'main'
def q(v):
    v = sorted(v); n = len(v)
    return f'p10 {v[n//10]:.3f} median {v[n//2]:.3f} p90 {v[9*n//10]:.3f} mean {sum(v)/n:.3f} max {v[-1]:.3f} (n={n})'
for label, d in (('fixed+taper', A), ('cornerflat+taper', B)):
    ok = [r for r in d if r['status'] == 'ok']
    print(f'== {label}: status', dict(collections.Counter(r['status'] for r in d)))
    for r in d:
        if r['status'] in ('timeout', 'error'): print('   ', r['name'], r['status'], str(r.get('error'))[:80])
    g = [r['gain'] for r in ok]
    print('  gain over own constant width:', q(g))
    print(f'  gain > 5 %: {sum(x > 1.05 for x in g)}, > 10 %: {sum(x > 1.10 for x in g)}, < 1: {sum(x < 1 for x in g)}')
    for f in ('main', 'round', 'concave'):
        print(f'   {f:8s}', q([r['gain'] for r in ok if fam(r) == f]))
    print('  taper time:', q([r['taper_time'] for r in ok]), '| layout gen_time:', q([r['gen_time'] for r in ok]))
    print('  cases with necks', sum(r['necks'] > 0 for r in ok), 'unresolved', sum(r['unresolved'] > 0 for r in ok))
    tr = collections.Counter((r['const']['status'], r['v']['status']) for r in ok)
    print('  checker status constant -> V taper:', dict(tr))
    print('  V pass', sum(r['v']['status'] == 'pass' for r in ok), 'polygon pass', sum(r['poly']['status'] == 'pass' for r in ok))
    for r in ok:
        a, b = set(r['const']['failures']), set(r['v']['failures'])
        if a != b: print(f"    {r['name']:42s} {sorted(a)} -> {sorted(b)}  gain {r['gain']:.3f}")
# conductance relative to fixed constant width, non-thin cases laid out by both
Ad = {r['name']: r for r in A if r['status'] == 'ok'}; Bd = {r['name']: r for r in B if r['status'] == 'ok'}
common = [n for n in Ad if n in Bd and 'thin' not in Ad[n]['tags']]
print(f'== conductance relative to fixed constant width (1/R), {len(common)} common non-thin cases')
for f in ('all', 'main', 'round', 'concave'):
    cs = [n for n in common if f == 'all' or fam(Ad[n]) == f]
    print(f' {f}')
    print('   cornerflat constant', q([Ad[n]['r_const'] / Bd[n]['r_const'] for n in cs]))
    print('   fixed tapered      ', q([Ad[n]['r_const'] / Ad[n]['r_taper'] for n in cs]))
    print('   cornerflat tapered ', q([Ad[n]['r_const'] / Bd[n]['r_taper'] for n in cs]))
