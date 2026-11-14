#!/usr/bin/env python3
"""Compare corpus results of several layout implementations.

Usage: python tests/compare_results.py NAME=results.json [NAME=results.json ...] [--by-tag] [--worst N]
"""

import sys
import json
import math
import argparse
from collections import defaultdict


def pct(values, q):
    values = sorted(v for v in values if not math.isnan(v))
    if not values:
        return float('nan')
    return values[min(len(values)-1, int(q * len(values)))]


def metrics(results):
    checked = [r for r in results if r['status'] in ('pass', 'fail')]
    n = len(results)
    m = {
        'cases': n,
        'pass': sum(r['status'] == 'pass' for r in results),
        'rejected': sum(r['status'] == 'rejected' for r in results),
        'error': sum(r['status'] in ('error', 'checker-error') for r in results),
        'conn broken': sum(not r['ok_connectivity'] for r in checked),
        'shorts/stray via': sum(r.get('shorts', 0) + r.get('stray_vias', 0) > 0 for r in checked),
        'stray copper': sum(r.get('stray_copper', 0) > 0 for r in checked),
        'width wrong': sum(not r.get('width_ok', True) for r in checked),
        'backtracks': sum(r.get('backtracks', 0) > 0 for r in checked),
        'crossings': sum(r['crossings'] > 0 for r in checked),
        'winding wrong': sum(not abs(r['winding_error']) < 0.05 for r in checked),
        'clear. def>5%': sum(r['rel_deficit'] > 0.05 for r in checked),
        'via def>5%': sum(r.get('rel_via_deficit', 0) > 0.05 for r in checked),
        'pad def>5%': sum(r.get('rel_pad_deficit', 0) > 0.05 for r in checked),
        'via offset': sum(r.get('via_misplacement', 0) > 0.05 for r in checked),
        'conformance bad': sum(not r.get('conformance_ok', True) for r in checked),
        'tracks ok': sum(bool(r.get('tracks_ok')) for r in checked),
        'pitch p10': pct([r.get('pitch_ratio', float('nan')) for r in checked], 0.1),
        'pitch med': pct([r.get('pitch_ratio', float('nan')) for r in checked], 0.5),
        'uncov med': pct([r['uncovered_fraction'] for r in checked], 0.5),
        'uncov p90': pct([r['uncovered_fraction'] for r in checked], 0.9),
        'gen time p90': pct([r.get('gen_time', float('nan')) for r in checked], 0.9),
    }
    return m


def fmt(v):
    if isinstance(v, float):
        return f'{v:.3f}'
    return str(v)


def table(columns, rows, file=sys.stdout):
    widths = [max(len(str(c)), *(len(fmt(r[i])) for r in rows)) for i, c in enumerate(columns)]
    print('  '.join(str(c).rjust(w) for c, w in zip(columns, widths)), file=file)
    for r in rows:
        print('  '.join(fmt(v).rjust(w) for v, w in zip(r, widths)), file=file)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inputs', nargs='+')
    ap.add_argument('--by-tag', action='store_true')
    ap.add_argument('--worst', type=int, default=0)
    args = ap.parse_args()

    runs = {}
    for spec in args.inputs:
        name, _, path = spec.partition('=')
        runs[name] = json.load(open(path))

    ms = {name: metrics(res) for name, res in runs.items()}
    keys = list(next(iter(ms.values())).keys())
    table(['metric'] + list(runs), [[k] + [ms[n][k] for n in runs] for k in keys])

    if args.by_tag:
        print()
        tags = sorted({t for res in runs.values() for r in res for t in r['tags']})
        rows = []
        for t in tags:
            row = [t]
            for name, res in runs.items():
                sel = [r for r in res if t in r['tags']]
                mm = metrics(sel)
                row.append(f"{mm['pass']}/{mm['cases']} p{mm['pitch med']:.2f}")
            rows.append(row)
        table(['tag (pass/cases, median pitch ratio)'] + list(runs), rows)

    if args.worst:
        for name, res in runs.items():
            print(f'\nWorst {args.worst} by score in {name}:')
            for r in sorted([r for r in res if 'score' in r], key=lambda r: -r['score'])[:args.worst]:
                print(f"  {r['name']:45s} score={r['score']:.2f} deficit={r['rel_deficit']:.2f} "
                      f"pitch={r.get('pitch_ratio', float('nan')):.3f} uncovered={r['uncovered_fraction']:.3f} "
                      f"failures={','.join(r.get('failures', []))}")


if __name__ == '__main__':
    main()
