"""Sum and distribution of per-case gen_time (all statuses that recorded one), per implementation and family.
Run: cd /tmp/claude-0/wt/next && PYTHONPATH=src:tests .venv/bin/python docs/comparison/scripts/runtime.py"""
import json
F = __import__('os').environ.get('KICOIL_BENCH', __import__('os').environ.get('KICOIL_BENCH', '/tmp/claude-0/bench/final')).rstrip('/') + '/'
files = dict(original='original_full.json', fixed='kicoil_full.json', cornerflat='cornerflat_full.json',
             optspan='geometry_alt_optspan_full.json', jog='geometry_alt_jog_full.json')
fam = lambda n: 'round' if n.startswith('round_') else 'concave' if n.startswith('concave_') else 'main'
print('| impl | sum gen_time all [s] | main | round | concave | cases > 10 s | cases > 60 s |')
print('|---|---:|---:|---:|---:|---:|---:|')
for impl, fn in files.items():
    d = [r for r in json.load(open(F + fn)) if r['status'] in ('pass', 'fail')]
    s = {f: sum(r['gen_time'] for r in d if fam(r['name']) == f) for f in ('main', 'round', 'concave')}
    t = [r['gen_time'] for r in d]
    print(f"| {impl} | {sum(t):.0f} | {s['main']:.0f} | {s['round']:.0f} | {s['concave']:.0f} | "
          f"{sum(x > 10 for x in t)} | {sum(x > 60 for x in t)} |")
print('(pass/fail cases only; rejected/error/timeout cases excluded; optspan additionally has one 600 s timeout)')
