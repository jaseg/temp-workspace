#!/usr/bin/env python3
"""Where the original code raises for the cases it rejects or crashes on (stats.py only has the message).

Re-runs only build_model (generation, no footprint render, no checker) of the original's non-checked cases, one at a
time, and records the innermost kicoil frame of the exception. Run from the worktree:
    cd /tmp/claude-0/wt/next && PYTHONPATH=/tmp/claude-0/orig/src:tests \
        /home/user/temp-workspace/kicoil/.venv/bin/python docs/comparison/scripts/reject_sites.py
Writes reject_sites.json next to this script and prints a table. Also cross-tabulates with the fixed code's status.
"""

import json
import os
import re
import sys
import traceback
import warnings
from collections import Counter, defaultdict

import kicoil
import corpus
from run_corpus import build_model

HERE = os.path.dirname(os.path.abspath(__file__))
FINAL = __import__('os').environ.get('KICOIL_BENCH', '/tmp/claude-0/bench/final')
assert kicoil.__file__.startswith('/tmp/claude-0/orig/'), kicoil.__file__


def main():
    orig = {r['name']: r for r in json.load(open(os.path.join(FINAL, 'original_full.json')))}
    fixed = {r['name']: r for r in json.load(open(os.path.join(FINAL, 'kicoil_full.json')))}
    specs = {c['name']: c for c in corpus.corpus('full')}
    rows = []
    for name, r in orig.items():
        if r['status'] not in ('rejected', 'error'):
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                build_model(specs[name])
            site, msg = 'no exception in build_model (raised in render_footprint)', ''
        except Exception as e:
            frames = [f for f in traceback.extract_tb(e.__traceback__) if '/kicoil/' in f.filename]
            f = frames[-1] if frames else traceback.extract_tb(e.__traceback__)[-1]
            site = f'{os.path.basename(f.filename)}:{f.lineno} in {f.name}: {f.line}'
            msg = f'{type(e).__name__}: {e}'.splitlines()[0]
        rows.append(dict(name=name, status=r['status'], recorded=r.get('error', ''), site=site, rerun=msg,
                         fixed_status=fixed[name]['status'], fixed_failures=fixed[name].get('failures', []),
                         fixed_error=fixed[name].get('error', '')))
    json.dump(rows, open(os.path.join(HERE, 'reject_sites.json'), 'w'), indent=1)
    norm = lambda m: re.sub(r'-?\d+(\.\d+)?', '#', m)[:70]
    g = defaultdict(list)
    for x in rows:
        g[(x['status'], norm(x['recorded']), x['site'])].append(x)
    print('| status | message | raised at (original) | n | fixed: pass/fail/rejected | examples |')
    print('|---|---|---|---:|---|---|')
    for (st, m, site), xs in sorted(g.items(), key=lambda kv: -len(kv[1])):
        fs = Counter(x['fixed_status'] for x in xs)
        print(f"| {st} | `{m}` | `{site}` | {len(xs)} | {fs.get('pass', 0)}/{fs.get('fail', 0)}/{fs.get('rejected', 0)} "
              f"| {', '.join(x['name'] for x in xs[:3])} |")
    mism = [x for x in rows if norm(x['recorded']) != norm(x['rerun'])]
    print(f'\nrerun message differs from recorded: {len(mism)}', [x['name'] for x in mism[:10]])


if __name__ == '__main__':
    main()
