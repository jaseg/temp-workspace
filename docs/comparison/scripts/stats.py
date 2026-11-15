#!/usr/bin/env python3
"""Core statistics of the final full-corpus runs (1008 cases) of the five layout implementations.

Run from the worktree (so that tests/ is importable):
    cd /tmp/claude-0/wt/next && PYTHONPATH=src:tests /home/user/temp-workspace/kicoil/.venv/bin/python \
        docs/comparison/scripts/stats.py
Writes stats.md and stats.json next to this script. Reads only the result files; recomputes nothing.

Definitions
- Family: 'concave' if the case comes from tests/corpus_concave.py, 'round' if from tests/corpus_round.py, else 'main'
  (checked against the case names of corpus_round.cases() / corpus_concave.cases()).
- Percentiles: nearest rank as in tests/compare_results.py (sorted values, index int(q*n)), NaN dropped. Metrics over
  checked cases only (status pass or fail); generation time is gen_time of checked cases (geometry + footprint render).
- Failure classes (tests/test_layout.py test_corpus_case, tests/README.md):
    soft      = 'conformance' (outline coverage; not asserted by test_corpus_case at all)
    warnable  = WARNED_KINDS = clearance, via clearance, self short, self merge: acceptable in test_corpus_case only
                when the generator warned (warnings are not recorded in the result files, so they cannot be split here)
    hard      = every other kind (connectivity, short, stray via, via, duplicate, stray copper, crossing, backtrack,
                taper gap, width, pad size, pad clearance, via offset, winding)
  'any hard' = case has a hard kind; 'hard or clearance-class' = case has any non-conformance kind (strict reading).
- Thin: the nominal trace width annular_width*layers/turns - clearance (circle: annular = (OD-ID)/2) below 0.1 mm
  (THIN_TRACE of corpus_concave.py), computed for every case from its spec. NOTE: the 'thin' *tag* is not this: in the
  main corpus it is a shape tag of rect60x12 (14 cases, all with nominal traces >= 0.1 mm), in the round family it is
  never set. Both exclusions are reported; the computed one is the headline one.
"""

import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

import corpus
import corpus_concave
import corpus_round

HERE = os.path.dirname(os.path.abspath(__file__))
FINAL = __import__('os').environ.get('KICOIL_BENCH', '/tmp/claude-0/bench/final')
IMPLS = {
    'original': 'original_full.json',
    'fixed': 'kicoil_full.json',
    'cornerflat': 'cornerflat_full.json',
    'optspan': 'geometry_alt_optspan_full.json',
    'jog': 'geometry_alt_jog_full.json',
}
FAMILIES = ('all', 'main', 'round', 'concave')
STATUSES = ('pass', 'fail', 'rejected', 'error', 'checker-error', 'timeout')
SOFT = {'conformance'}
WARNABLE = {'clearance', 'via clearance', 'self short', 'self merge'}
THIN_TRACE = 0.1


def pct(values, q):
    """Percentile by linear interpolation between order statistics (numpy's default 'linear' method); for q=0.5
    this is the standard median. Used for every percentile in docs/COMPARISON.md."""
    values = sorted(v for v in values if v is not None and not math.isnan(v))
    if not values:
        return float('nan')
    pos = q * (len(values) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def nominal_trace(c):
    aw = c.get('annular_width')
    if aw is None:
        aw = (c['outer_diameter'] - c['inner_diameter']) / 2
    return aw * c['layers'] / c['turns'] - c['clearance']


def summarize(rs):
    st = Counter(r['status'] for r in rs)
    checked = [r for r in rs if r['status'] in ('pass', 'fail')]
    kinds = Counter(k for r in checked for k in set(r.get('failures', [])))
    hard = sum(any(k not in SOFT | WARNABLE for k in r.get('failures', [])) for r in checked)
    nonconf = sum(any(k not in SOFT for k in r.get('failures', [])) for r in checked)
    warn_only = sum(bool(set(r.get('failures', [])) - SOFT) and not (set(r.get('failures', [])) - SOFT - WARNABLE)
                    for r in checked)
    conf_only = sum(set(r.get('failures', [])) == {'conformance'} for r in checked)
    pr = [r.get('pitch_ratio', float('nan')) for r in checked]
    uf = [r.get('uncovered_fraction', float('nan')) for r in checked]
    gt = [r.get('gen_time', float('nan')) for r in checked]
    return {
        'cases': len(rs),
        'status': {s: st.get(s, 0) for s in STATUSES},
        'checked': len(checked),
        'failure_kinds': dict(sorted(kinds.items(), key=lambda kv: (-kv[1], kv[0]))),
        'any_hard': hard,
        'hard_or_clearance_class': nonconf,
        'clearance_class_only': warn_only,
        'conformance_only': conf_only,
        'pitch_ratio_p10': pct(pr, 0.1),
        'pitch_ratio_median': pct(pr, 0.5),
        'uncovered_median': pct(uf, 0.5),
        'uncovered_p90': pct(uf, 0.9),
        'gen_time_median': pct(gt, 0.5),
        'gen_time_p90': pct(gt, 0.9),
        'gen_time_max': max((v for v in gt if not math.isnan(v)), default=float('nan')),
        'gen_time_max_case': max(checked, key=lambda r: r.get('gen_time', -1))['name'] if checked else None,
    }


def main():
    specs = {c['name']: c for c in corpus.corpus('full')}
    round_names = {c['name'] for c in corpus_round.cases()}
    concave_names = {c['name'] for c in corpus_concave.cases()}
    assert len(specs) == 1008 and not round_names & concave_names
    family = {n: 'concave' if n in concave_names else 'round' if n in round_names else 'main' for n in specs}
    # cross-check against the tags
    for n, c in specs.items():
        tagfam = 'concave' if 'concave' in c['tags'] else 'round' if 'round' in c['tags'] else 'main'
        assert tagfam == family[n], n
    thin = {n for n, c in specs.items() if nominal_trace(c) < THIN_TRACE}
    thin_tag = {n for n, c in specs.items() if 'thin' in c['tags']}

    data = {}
    for impl, fn in IMPLS.items():
        rs = json.load(open(os.path.join(FINAL, fn)))
        names = [r['name'] for r in rs]
        assert len(names) == len(set(names)) == 1008 and set(names) == set(specs), impl
        data[impl] = rs

    by_name = {i: {r['name']: r for r in rs} for i, rs in data.items()}
    out = {'corpus': {
        'cases': len(specs),
        'family_counts': dict(Counter(family.values())),
        'thin_nominal': sorted(thin),
        'thin_nominal_by_family': dict(Counter(family[n] for n in thin)),
        'thin_tag': sorted(thin_tag),
        'thin_tag_not_thin_nominal': sorted(thin_tag - thin),
        'thin_nominal_not_tagged': sorted(thin - thin_tag),
        'thin_tag_nominal_trace_min': min(nominal_trace(specs[n]) for n in thin_tag - thin) if thin_tag - thin else None,
    }, 'impls': {}}

    for impl, rs in data.items():
        o = {}
        for excl, ex in (('all_cases', set()), ('excl_thin', thin), ('excl_thin_tag', thin_tag)):
            o[excl] = {}
            for fam in FAMILIES:
                sub = [r for r in rs if r['name'] not in ex and (fam == 'all' or family[r['name']] == fam)]
                o[excl][fam] = summarize(sub)
        # rejections, errors, timeouts
        groups = defaultdict(list)
        for r in rs:
            if r['status'] in ('rejected', 'error', 'checker-error', 'timeout'):
                msg = r.get('error', '')
                groups[(r['status'], _msg_kind(msg))].append(r['name'])
        o['nonchecked_groups'] = [
            {'status': s, 'message': m, 'count': len(v), 'by_family': dict(Counter(family[n] for n in v)),
             'thin': sum(n in thin for n in v), 'examples': v[:4]}
            for (s, m), v in sorted(groups.items(), key=lambda kv: (kv[0][0], -len(kv[1])))]
        o['timeouts'] = [{'name': r['name'], 'family': family[r['name']], 'time': r.get('time'),
                          'error': r.get('error')} for r in rs if r['status'] == 'timeout']
        o['hard_declared'] = sorted(
            r['name'] for r in rs if r['status'] == 'fail' and any(k not in SOFT | WARNABLE for k in r['failures'])
            and all(k in set(specs[r['name']].get('known_failures', {})) | set(specs[r['name']].get('known_issue', {}).get('kinds', ()))
                    for k in r['failures'] if k not in SOFT | WARNABLE))
        o['hard_cases'] = {r['name']: [k for k in r['failures'] if k not in SOFT | WARNABLE] for r in rs
                           if r['status'] == 'fail' and any(k not in SOFT | WARNABLE for k in r['failures'])}
        o['error_tracebacks'] = _tb_sites([r for r in rs if r['status'] in ('error', 'checker-error')])
        out['impls'][impl] = o
    for impl in out['impls']:
        for t in out['impls'][impl]['timeouts']:
            t['other_impls'] = {i: {'status': by_name[i][t['name']]['status'],
                                    'gen_time': by_name[i][t['name']].get('gen_time'),
                                    'failures': by_name[i][t['name']].get('failures')}
                                for i in out['impls'] if i != impl}
    rs_file = os.path.join(HERE, 'reject_sites.json')
    if os.path.exists(rs_file):
        out['original_nonchecked_sites'] = _sites(json.load(open(rs_file)))

    with open(os.path.join(HERE, 'stats.json'), 'w') as f:
        json.dump(out, f, indent=1, default=float)
    with open(os.path.join(HERE, 'stats.md'), 'w') as f:
        write_md(out, f)
    print('wrote', os.path.join(HERE, 'stats.md'), os.path.join(HERE, 'stats.json'))


def _msg_kind(msg):
    """ Group error messages: numbers vary per case, so replace them by '#'. """
    return re.sub(r'-?\d+(\.\d+)?(e-?\d+)?', '#', msg)[:160]


def _sites(rows):
    """ Group reject_sites.py output: message kind, raise site in the original, status of the fixed code. """
    g = defaultdict(list)
    for x in rows:
        g[(x['status'], _msg_kind(x['recorded'])[:70], x['site'])].append(x)
    res = []
    for (st, m, site), xs in sorted(g.items(), key=lambda kv: -len(kv[1])):
        fs = Counter(x['fixed_status'] for x in xs)
        shapes = Counter(re.sub(r'_(a|w|s)[0-9.]+.*$', '', x['name']) for x in xs)
        res.append({'status': st, 'message': m, 'site': site, 'count': len(xs),
                    'fixed': {k: fs.get(k, 0) for k in ('pass', 'fail', 'rejected')},
                    'fixed_rejected_shapes': dict(Counter(re.sub(r'_(a|w|s)[0-9.]+.*$', '', x['name'])
                                                          for x in xs if x['fixed_status'] == 'rejected')),
                    'shapes': dict(shapes.most_common())})
    return res


def _tb_sites(rs):
    """ Last source line ('File ..., line N, in f') of each error traceback, counted. """
    c = Counter()
    for r in rs:
        tb = r.get('traceback', '')
        sites = [l.strip() for l in tb.splitlines() if l.strip().startswith('File ')]
        c[(sites[-1] if sites else '?', r.get('error', ''))] += 1
    return [{'site': s, 'error': e, 'count': n} for (s, e), n in c.most_common()]


def f3(v):
    return 'n/a' if v is None or (isinstance(v, float) and math.isnan(v)) else f'{v:.3f}'


def f2(v):
    return 'n/a' if v is None or (isinstance(v, float) and math.isnan(v)) else f'{v:.2f}'


def write_md(out, f):
    impls = list(out['impls'])
    p = lambda *a: print(*a, file=f)
    cor = out['corpus']
    p('# Core statistics, full corpus\n')
    p(f"Cases: {cor['cases']} ({', '.join(f'{k} {v}' for k, v in cor['family_counts'].items())}). "
      f"Generated by stats.py from /tmp/claude-0/bench/final/*.json.\n")
    p(f"Thin (nominal trace = annular*layers/turns - clearance < 0.1 mm, computed from the spec): "
      f"{len(cor['thin_nominal'])} cases ({', '.join(f'{k} {v}' for k, v in cor['thin_nominal_by_family'].items())}).")
    p(f"The 'thin' tag marks {len(cor['thin_tag'])} cases; {len(cor['thin_tag_not_thin_nominal'])} of them are the "
      f"rect60x12 shape tag of the main corpus with nominal traces >= {f3(cor['thin_tag_nominal_trace_min'])} mm, and "
      f"{len(cor['thin_nominal_not_tagged'])} thin cases are not tagged: {', '.join(cor['thin_nominal_not_tagged'])}. "
      f"Headline 'excl. thin' uses the computed set.\n")
    p('Failure classes: *soft* = conformance; *clearance-class* = clearance, via clearance, self short, self merge '
      '(test_layout.WARNED_KINDS: tolerated only when the generator warned; warnings are not in the result files); '
      '*hard* = any other kind. Percentiles: nearest rank (compare_results.py), over checked (pass/fail) cases.\n')

    for excl, title in (('all_cases', 'All cases'), ('excl_thin', 'Excluding thin cases (nominal trace < 0.1 mm)')):
        p(f'## {title}\n')
        for fam in FAMILIES:
            p(f'### Family: {fam}\n')
            S = {i: out['impls'][i][excl][fam] for i in impls}
            p('| metric | ' + ' | '.join(impls) + ' |')
            p('|---|' + '---:|' * len(impls))
            row = lambda name, fn: p(f'| {name} | ' + ' | '.join(fn(S[i]) for i in impls) + ' |')
            row('cases', lambda s: str(s['cases']))
            for st in STATUSES:
                if any(S[i]['status'][st] for i in impls) or st != 'checker-error':
                    row(st, lambda s, st=st: str(s['status'][st]))
            row('**any hard failure**', lambda s: f"**{s['any_hard']}**")
            row('hard or clearance-class', lambda s: str(s['hard_or_clearance_class']))
            row('clearance-class only (no hard)', lambda s: str(s['clearance_class_only']))
            row('conformance only', lambda s: str(s['conformance_only']))
            kinds = sorted({k for i in impls for k in S[i]['failure_kinds']},
                           key=lambda k: (0 if k not in SOFT | WARNABLE else 1 if k in WARNABLE else 2, k))
            for k in kinds:
                cls = 'hard' if k not in SOFT | WARNABLE else 'clr' if k in WARNABLE else 'soft'
                row(f'kind: {k} ({cls})', lambda s, k=k: str(s['failure_kinds'].get(k, 0)))
            row('pitch ratio p10', lambda s: f3(s['pitch_ratio_p10']))
            row('pitch ratio median', lambda s: f3(s['pitch_ratio_median']))
            row('uncovered median', lambda s: f'{s["uncovered_median"]:.4f}' if not math.isnan(s['uncovered_median']) else 'n/a')
            row('uncovered p90', lambda s: f'{s["uncovered_p90"]:.4f}' if not math.isnan(s['uncovered_p90']) else 'n/a')
            row('gen time median [s]', lambda s: f2(s['gen_time_median']))
            row('gen time p90 [s]', lambda s: f2(s['gen_time_p90']))
            row('gen time max [s]', lambda s: f2(s['gen_time_max']))
            row('slowest case', lambda s: str(s['gen_time_max_case']))
            p()

    p("## Excluding cases with the 'thin' tag (for comparison only)\n")
    S = {i: out['impls'][i]['excl_thin_tag']['all'] for i in impls}
    p('| metric | ' + ' | '.join(impls) + ' |')
    p('|---|' + '---:|' * len(impls))
    for name, fn in (('cases', lambda s: s['cases']), ('pass', lambda s: s['status']['pass']),
                     ('fail', lambda s: s['status']['fail']), ('rejected', lambda s: s['status']['rejected']),
                     ('error', lambda s: s['status']['error']), ('timeout', lambda s: s['status']['timeout']),
                     ('any hard failure', lambda s: s['any_hard'])):
        p(f'| {name} | ' + ' | '.join(str(fn(S[i])) for i in impls) + ' |')
    p()

    p('## Rejections, errors and timeouts (grouped by message, numbers replaced by #)\n')
    for i in impls:
        g = out['impls'][i]['nonchecked_groups']
        if not g:
            continue
        p(f'### {i}\n')
        p('| status | count | families | thin | message | examples |')
        p('|---|---:|---|---:|---|---|')
        for e in g:
            fam = ', '.join(f'{k} {v}' for k, v in e['by_family'].items())
            p(f"| {e['status']} | {e['count']} | {fam} | {e['thin']} | `{e['message']}` | {', '.join(e['examples'])} |")
        p()
        if out['impls'][i]['error_tracebacks']:
            p('Error sites (last traceback frame):\n')
            for e in out['impls'][i]['error_tracebacks']:
                p(f"- {e['count']} x `{e['site']}`: {e['error']}")
            p()
        for t in out['impls'][i]['timeouts']:
            p(f"Timeout: {t['name']} ({t['family']}, killed after {t['time']:.0f} s). Same case elsewhere: " +
              '; '.join(f"{j} {o['status']} in {f2(o['gen_time'])} s" + (f" [{','.join(o['failures'])}]" if o['failures'] else '')
                        for j, o in t['other_impls'].items()))
            p()
    p('## Cases with a hard failure (alternatives and fixed)\n')
    for i in impls[1:]:
        hc = out['impls'][i]['hard_cases']
        dec = out['impls'][i]['hard_declared']
        p(f"- {i} ({len(hc)}, of which {len(dec)} declared in the corpus as known_failures/known_issue, marked *): " +
          ', '.join(f"{n}{'*' if n in dec else ''} [{','.join(k)}]" for n, k in sorted(hc.items())))
    p()
    if 'original_nonchecked_sites' in out:
        p('## Why the original rejects or crashes (reject_sites.py: re-raised with build_model on the original code)\n')
        p('| status | message | raised at (original source) | n | fixed code: pass/fail/rejected | shapes |')
        p('|---|---|---|---:|---|---|')
        for e in out['original_nonchecked_sites']:
            fx = e['fixed']
            sh = ', '.join(f'{k} {v}' for k, v in list(e['shapes'].items())[:8]) + (' ...' if len(e['shapes']) > 8 else '')
            p(f"| {e['status']} | `{e['message']}` | `{e['site'][:110]}` | {e['count']} | "
              f"{fx['pass']}/{fx['fail']}/{fx['rejected']} | {sh} |")
        p()


if __name__ == '__main__':
    main()
