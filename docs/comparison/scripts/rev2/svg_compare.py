"""Render 3 (round_dense2500_a0.60_n21k8): compare the render-run SVGs of fixed, optspan and jog token by token,
and print the render-run and benchmark gen_time of each implementation.
Run: python3 docs/comparison/scripts/rev2/svg_compare.py"""
import hashlib, json, re
S = 'docs/comparison/scripts/svg/'
C = 'round_dense2500_a0.60_n21k8'
B = __import__('os').environ.get('KICOIL_BENCH', __import__('os').environ.get('KICOIL_BENCH', '/tmp/claude-0/bench/final')).rstrip('/') + '/'
BF = dict(original='original_full.json', fixed='kicoil_full.json', cornerflat='cornerflat_full.json',
          optspan='geometry_alt_optspan_full.json', jog='geometry_alt_jog_full.json')
tok = lambda s: re.findall(r'-?\d+\.?\d*(?:e-?\d+)?|[^\d\s.-]+|\S', s)
ref = open(S + f'fixed/{C}.svg').read()
for impl in ('optspan', 'jog', 'cornerflat'):
    txt = open(S + f'{impl}/{C}.svg').read()
    a, b = tok(ref), tok(txt)
    same_len = len(a) == len(b)
    nonnum = maxrel = 0.0; ndiff = 0
    if same_len:
        for x, y in zip(a, b):
            if x != y:
                ndiff += 1
                try:
                    fx, fy = float(x), float(y)
                    maxrel = max(maxrel, abs(fx - fy) / max(abs(fx), abs(fy), 1e-300))
                except ValueError:
                    nonnum += 1
    print(f'{impl:10s} md5 {hashlib.md5(txt.encode()).hexdigest()[:8]} (fixed {hashlib.md5(ref.encode()).hexdigest()[:8]}); '
          f'same token count {same_len}; differing tokens {ndiff}, non-numeric {int(nonnum)}, max relative difference {maxrel:.1e}')
for impl in BF:
    rr = json.load(open(S + f'{impl}/{C}.json'))[0]
    br = next(r for r in json.load(open(B + BF[impl])) if r['name'] == C)
    print(f'{impl:10s} render run {rr["status"]} gen_time {rr["gen_time"]:.2f} s; benchmark {br["status"]} gen_time {br["gen_time"]:.2f} s')
