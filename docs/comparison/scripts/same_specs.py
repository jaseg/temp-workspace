"""Check that all five result files cover the same case names and the same nominal pitch per case.
Run: /home/user/temp-workspace/kicoil/.venv/bin/python docs/comparison/scripts/same_specs.py"""
import json
F = __import__('os').environ.get('KICOIL_BENCH', __import__('os').environ.get('KICOIL_BENCH', '/tmp/claude-0/bench/final')).rstrip('/') + '/'
files = ['original_full.json', 'kicoil_full.json', 'cornerflat_full.json', 'geometry_alt_optspan_full.json',
         'geometry_alt_jog_full.json']
ref = {r['name']: r.get('nominal_pitch') for r in json.load(open(F + files[1]))}
for fn in files:
    d = {r['name']: r.get('nominal_pitch') for r in json.load(open(F + fn))}
    both = [n for n in ref if d.get(n) is not None and ref[n] is not None]
    diff = [n for n in both if abs(d[n] - ref[n]) > 1e-9]
    print(f'{fn}: {len(d)} cases, same names: {set(d) == set(ref)}, pitch compared on {len(both)}, differing: {len(diff)} {diff[:3]}')
