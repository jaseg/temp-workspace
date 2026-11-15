"""Self-short cases per implementation: how many also fail conformance, which other kinds, family, notes.
Run: cd /tmp/claude-0/wt/next && PYTHONPATH=src:tests .venv/bin/python docs/comparison/scripts/selfshort.py"""
import json, re, collections
F = __import__('os').environ.get('KICOIL_BENCH', __import__('os').environ.get('KICOIL_BENCH', '/tmp/claude-0/bench/final')).rstrip('/') + '/'
files = dict(fixed='kicoil_full.json', cornerflat='cornerflat_full.json', optspan='geometry_alt_optspan_full.json',
             jog='geometry_alt_jog_full.json')
for impl, fn in files.items():
    d = json.load(open(F + fn))
    ss = [r for r in d if 'self short' in r.get('failures', [])]
    conf = [r for r in ss if 'conformance' in r['failures']]
    only = [r for r in ss if set(r['failures']) <= {'self short', 'conformance'}]
    fam = collections.Counter('round' if r['name'].startswith('round_') else 'concave' if r['name'].startswith('concave_') else 'main' for r in ss)
    a90 = sum(1 for r in ss if 'a0.9' in r['name'])
    print(f'## {impl}: self short {len(ss)}, also conformance {len(conf)}, only self short(+conformance) {len(only)}, '
          f'families {dict(fam)}, at a0.90 depth {a90}')
    for r in ss:
        turns = [m for n in r.get('notes', []) for m in re.findall(r'([0-9.]+) turns', n)]
        print(f"  {r['name']:40s} {','.join(r['failures']):45s} unc={r.get('uncovered_fraction',0):.3f} "
              f"worst_self_short={r.get('worst_self_short',0):.3f} bypass={r.get('max_self_touch_bypass',0):.3f} turns={turns[:3]}")
print('## cases whose only failure is self short (would pass if the self-short rule did not fire)')
for impl, fn in files.items():
    d = json.load(open(F + fn))
    only = [r['name'] for r in d if r.get('failures') == ['self short']]
    print(f'  {impl}: {len(only)} {only}')
