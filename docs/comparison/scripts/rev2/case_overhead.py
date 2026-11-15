"""Per-case process overhead in run_corpus.py --timeout runs.
With --timeout, every case runs in a fresh forkserver child that has imported only run_corpus.py's module-level
imports (corpus, geomcheck); build_model() then imports the layout module inside the gen_time window.
This script starts a fresh process per sample, imports run_corpus, and calls run_case() on the same case twice:
the first gen_time is what a --timeout run records, the second is what a warm (pool or -j 1 without --timeout)
worker records. The difference is the per-case overhead.
Run from /tmp/claude-0/wt/next:
  $PY docs/comparison/scripts/rev2/case_overhead.py > docs/comparison/scripts/rev2/case_overhead.out"""
import subprocess, sys, statistics
PY = sys.executable
CASES = ['circle50x25_n5k1', 'square40_a0.30_n5k2']
IMPLS = [('original', '/tmp/claude-0/orig/src', 'kicoil'), ('fixed', 'src', 'kicoil'),
         ('cornerflat', 'src', 'geometry_alt_cornerflat'), ('optspan', 'src', 'geometry_alt_optspan'),
         ('jog', 'src', 'geometry_alt_jog')]
CODE = r'''
import sys; sys.path.insert(0, "tests"); sys.argv = ["x"]
import run_corpus, corpus
spec = {c["name"]: c for c in corpus.corpus("full")}[CASE]
a = run_corpus.run_case((spec, IMPL, None)); b = run_corpus.run_case((spec, IMPL, None))
print(a["gen_time"], b["gen_time"], a["status"])
'''
for case in CASES:
    for label, pp, impl in IMPLS:
        firsts, seconds = [], []
        for _ in range(5):
            code = CODE.replace('CASE', repr(case)).replace('IMPL', repr(impl))
            out = subprocess.run([PY, '-c', code], capture_output=True, text=True, env={'PYTHONPATH': pp})
            line = out.stdout.strip().splitlines()[-1].split()
            firsts.append(float(line[0])); seconds.append(float(line[1])); st = line[2]
        d = [f - s for f, s in zip(firsts, seconds)]
        print(f'{case:22s} {label:10s} status {st:5s} first {statistics.median(firsts):.3f} s  '
              f'second {statistics.median(seconds):.3f} s  overhead median {statistics.median(d):.3f} s '
              f'(min {min(d):.3f}, max {max(d):.3f})')
