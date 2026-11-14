#!/usr/bin/env python3
"""Run the layout corpus through a layout implementation and the geometric checker.

Usage:
    python tests/run_corpus.py [--impl kicoil|MODULE] [--kind full|quick] [--out results.json] [--svg-dir DIR] [-j N]
                               [--filter SUBSTR]

The implementation is imported from whatever `kicoil` package is first on sys.path, so to evaluate an older revision
run this with PYTHONPATH pointing to that revision's `src` directory.
"""

import sys
import os
import json
import math
import time
import argparse
import warnings
import logging
import traceback
import dataclasses
from pathlib import Path
from multiprocessing import Pool

sys.path.insert(0, str(Path(__file__).parent))

import corpus as corpus_mod
import geomcheck


def build_model(spec, impl='kicoil'):
    import importlib
    geometry = importlib.import_module('kicoil.geometry' if impl == 'kicoil' else f'kicoil.{impl}')

    if spec['shape'] == 'circle':
        shape = geometry.CircleShape(spec['outer_diameter'], spec['inner_diameter'])
    else:
        poly = [tuple(p) for p in spec['polygon']]
        base = getattr(geometry, 'PolygonShape', None)
        if base is not None:
            shape = base(polygon=poly, annular_width=spec['annular_width'])
        else:
            @dataclasses.dataclass
            class _PolygonShape(geometry.OffsetShape):
                polygon: list
                annular_width: float
                arc_tolerance: float = 0.05

                @property
                def slug(self):
                    return f'polygon_{len(self.polygon)}pt'

                @property
                def desc(self):
                    return f'{len(self.polygon)} point polygonal'
            shape = _PolygonShape(poly, spec['annular_width'])

    kw = dict(turns=spec['turns'], twists=spec['twists'], layers=spec['layers'], clockwise=spec['clockwise'],
              clearance=spec['clearance'])
    if spec.get('trace_width'):
        kw['trace_width'] = spec['trace_width']
    return geometry.PlanarInductor(shape=shape, **kw)


def run_case(args):
    spec, impl, svg_dir = args
    res = {'name': spec['name'], 'tags': spec['tags']}
    t0 = time.perf_counter()
    logging.getLogger('kicoil').setLevel(logging.ERROR)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            model = build_model(spec, impl)
            fp = model.render_footprint(circle_segments=64)
    except Exception as e:
        res['status'] = 'rejected' if isinstance(e, ValueError) else 'error'
        res['error'] = f'{type(e).__name__}: {e}'.splitlines()[0][:300]
        if res['status'] == 'error':
            res['traceback'] = traceback.format_exc()[-1500:]
        res['time'] = time.perf_counter() - t0
        return res
    res['gen_time'] = time.perf_counter() - t0
    res['nominal_pitch'] = getattr(model, 'spiral_pitch', float('nan'))

    try:
        intent = geomcheck.intent_from_model(model)
        copper = geomcheck.extract_copper(fp, layers=model.layer_pair)
        rep = geomcheck.check_layout(copper, intent, keep_samples=bool(svg_dir))
    except Exception as e:
        res['status'] = 'checker-error'
        res['error'] = f'{type(e).__name__}: {e}'
        res['traceback'] = traceback.format_exc()[-1500:]
        return res

    res['status'] = 'pass' if rep.passed(intent.clearance, intent.trace_width) else 'fail'
    res['conformance_ok'] = rep.conformance_ok(intent.trace_width)
    d = dataclasses.asdict(rep)
    viol, cross, samples = d.pop('violations'), d.pop('crossing_points'), d.pop('spacing_samples')
    res.update(d)
    res['score'] = rep.score(intent.clearance)
    res['clearance'] = intent.clearance
    res['trace_width'] = intent.trace_width
    res['rel_deficit'] = rep.worst_clearance_deficit / intent.clearance
    # How much of the nominal pitch survives as trace width + clearance (1.0 is ideal)
    res['pitch_ratio'] = (intent.trace_width + intent.clearance) / res['nominal_pitch']
    res['rel_via_deficit'] = rep.worst_via_deficit / intent.clearance
    res['tracks_ok'] = rep.passed(intent.clearance, intent.trace_width, vias=False)
    res['time'] = time.perf_counter() - t0
    if svg_dir and (res['status'] != 'pass' or os.environ.get('RENDER_ALL')):
        loc = getattr(model, 'min_pitch_location', None)
        if loc:
            cross = list(cross) + [('pitch', loc)]
        render_svg(Path(svg_dir) / f"{spec['name']}.svg", copper, intent, viol, cross, samples)
    return res


def render_svg(path, copper, intent, violations, crossings, samples=()):
    xs = [p[0] for p in intent.contour]
    ys = [p[1] for p in intent.contour]
    m = 3
    x0, y0, x1, y1 = min(xs)-m, min(ys)-m, max(xs)+m, max(ys)+m
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {-y1} {x1-x0} {y1-y0}" width="800" '
           f'height="{800*(y1-y0)/(x1-x0):.0f}"><g transform="scale(1,-1)">',
           f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="white"/>']
    pts = ' '.join(f'{x},{y}' for x, y in intent.contour)
    out.append(f'<polygon points="{pts}" fill="none" stroke="black" stroke-width="0.05"/>')
    colors = {copper.layers[0]: '#eb5c5c', copper.layers[1]: '#5c5ceb'}
    for s in copper.segs:
        out.append(f'<line x1="{s.a[0]}" y1="{s.a[1]}" x2="{s.b[0]}" y2="{s.b[1]}" stroke="{colors.get(s.layer, "gray")}" '
                   f'stroke-opacity="0.45" stroke-width="{s.width}" stroke-linecap="round"/>')
    for s in copper.segs:
        out.append(f'<line x1="{s.a[0]}" y1="{s.a[1]}" x2="{s.b[0]}" y2="{s.b[1]}" stroke="black" stroke-width="0.03"/>')
    for v in copper.vias:
        out.append(f'<circle cx="{v.x}" cy="{v.y}" r="{v.diameter/2}" fill="#52cc52" fill-opacity="0.6"/>')
    # Spacing heat map: (spacing + width) / nominal pitch at sample points, green = 1.0, red <= 0.8, blue >= 1.2
    for layer, (x, y), ratio in samples:
        if layer != copper.layers[0]:
            continue
        v = max(-1, min(1, (ratio - 1) / 0.2))
        color = f'rgb({int(255*max(0, -v))},{int(200*(1-abs(v)))},{int(255*max(0, v))})'
        out.append(f'<circle cx="{x}" cy="{y}" r="{intent.trace_width/4}" fill="{color}"/>')
    for layer, (x, y), deficit in violations:
        out.append(f'<circle cx="{x}" cy="{y}" r="{max(0.3, deficit*3)}" fill="none" stroke="orange" stroke-width="0.1"/>')
    for layer, (x, y) in crossings:
        out.append(f'<circle cx="{x}" cy="{y}" r="0.6" fill="none" stroke="magenta" stroke-width="0.15"/>')
    out.append('</g></svg>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(out))


def summarize(results, file=sys.stdout):
    from collections import Counter
    st = Counter(r['status'] for r in results)
    print(f'{len(results)} cases: ' + ', '.join(f'{k}={v}' for k, v in sorted(st.items())), file=file)
    checked = [r for r in results if r['status'] in ('pass', 'fail')]
    if not checked:
        return
    def cnt(pred):
        return sum(1 for r in checked if pred(r))
    print(f'  connectivity broken: {cnt(lambda r: not r["ok_connectivity"])}', file=file)
    print(f'  winding wrong (>0.05 turns): {cnt(lambda r: not abs(r["winding_error"]) < 0.05)}', file=file)
    print(f'  with crossings: {cnt(lambda r: r["crossings"] > 0)}', file=file)
    print(f'  clearance deficit >5%: {cnt(lambda r: r["rel_deficit"] > 0.05)}   >50%: {cnt(lambda r: r["rel_deficit"] > 0.5)}', file=file)
    print(f'  via deficit >5%: {cnt(lambda r: r["rel_via_deficit"] > 0.05)}', file=file)
    print(f'  backtracks: {cnt(lambda r: r["backtracks"] > 0)}   stubs: {cnt(lambda r: r["stubs"] > 0)}', file=file)
    print(f'  tracks ok (ignoring via issues): {cnt(lambda r: r["tracks_ok"])}', file=file)
    unc = sorted(r['uncovered_fraction'] for r in checked if not math.isnan(r['uncovered_fraction']))
    exc = sorted(r['excess_fraction'] for r in checked if not math.isnan(r['excess_fraction']))
    haus = sorted(r['contour_hausdorff'] for r in checked if not math.isnan(r['contour_hausdorff']))
    over = sorted(r['overshoot'] for r in checked if not math.isnan(r['overshoot']))
    med = lambda l: l[len(l)//2] if l else float('nan')
    print(f'  uncovered fraction: median {med(unc):.4f} max {max(unc, default=float("nan")):.4f}', file=file)
    print(f'  excess fraction:    median {med(exc):.4f} max {max(exc, default=float("nan")):.4f}', file=file)
    print(f'  contour undershoot: median {med(haus):.3f} max {max(haus, default=float("nan")):.3f} pitches', file=file)
    print(f'  copper overshoot:   median {med(over):.3f} max {max(over, default=float("nan")):.3f} mm', file=file)
    print(f'  conformance bad: {cnt(lambda r: not r["conformance_ok"])}', file=file)
    pr = sorted(r['pitch_ratio'] for r in checked if not math.isnan(r.get('pitch_ratio', float('nan'))))
    if pr:
        print(f'  pitch ratio (w+c)/nominal: p10 {pr[len(pr)//10]:.3f} median {med(pr):.3f} min {pr[0]:.3f}', file=file)
    print(f'  total score: {sum(r["score"] for r in checked):.1f}', file=file)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--impl', default='kicoil')
    ap.add_argument('--kind', default='full')
    ap.add_argument('--out')
    ap.add_argument('--svg-dir')
    ap.add_argument('--filter', action='append')
    ap.add_argument('-j', type=int, default=os.cpu_count())
    ap.add_argument('-v', action='store_true')
    args = ap.parse_args()

    cases = corpus_mod.corpus(args.kind)
    if args.filter:
        cases = [c for c in cases if any(f in c['name'] for f in args.filter)]

    # warm up the wasm module cache once before forking
    import kicoil.geometry  # noqa
    if args.impl != 'kicoil':
        build_model(cases[0], args.impl) if cases else None

    t0 = time.perf_counter()
    with Pool(args.j) as pool:
        results = pool.map(run_case, [(c, args.impl, args.svg_dir) for c in cases], chunksize=1)
    elapsed = time.perf_counter() - t0

    if args.v:
        for r in results:
            if r['status'] == 'pass':
                continue
            if r['status'] in ('fail',):
                print(f"{r['status']:8s} {r['name']:45s} conn={r['ok_connectivity']!s:5s} open={r['open_ends']} "
                      f"branch={r['branches']} wind={r['winding_error']:+.3f} cross={r['crossings']} "
                      f"deficit={r['rel_deficit']:.2f} via={r['rel_via_deficit']:.2f} unc={r['uncovered_fraction']:.3f} under={r['contour_hausdorff']:.2f} "
                      f"over={r['overshoot']:.3f}")
            else:
                print(f"{r['status']:8s} {r['name']:45s} {r.get('error', '')}")
    summarize(results)
    print(f'  elapsed: {elapsed:.1f} s')
    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=1, default=str))


if __name__ == '__main__':
    main()
