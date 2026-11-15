"""List each new implementation's hard-failure cases with their hard kinds.
Run: PYTHONPATH=src:tests $PY docs/comparison/scripts/rev2/hard_lists.py"""
import json
F = __import__('os').environ.get('KICOIL_BENCH', __import__('os').environ.get('KICOIL_BENCH', '/tmp/claude-0/bench/final')).rstrip('/') + '/'
WARN = {'clearance', 'via clearance', 'self short', 'self merge'}
for i, f in dict(fixed='kicoil_full.json', cornerflat='cornerflat_full.json', optspan='geometry_alt_optspan_full.json',
                 jog='geometry_alt_jog_full.json').items():
    h = [(r['name'], sorted(set(r['failures']) - WARN - {'conformance'})) for r in json.load(open(F + f))
         if r['status'] == 'fail' and set(r['failures']) - WARN - {'conformance'}]
    print(i, len(h), 'heart/heartdeep', sum('heart' in n for n, _ in h))
    for x in h: print('   ', *x)
