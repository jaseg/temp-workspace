#!/usr/bin/env python3
"""Evaluate tapered (variable width) traces on the layout corpus.

For every case: build the layout with the given implementation, run the checker on its constant width footprint, compute
the tapered widths (kicoil.taper), emit both representations (V track pairs and trapezoid polygons), verify them exactly
(TaperResult.verify) and with the checker in variable width mode, and record DC resistance, copper fill, widths,
primitive counts and times.

Usage:
    python tests/run_taper.py --impl kicoil|MODULE [--kind full] [--filter SUBSTR] [-j N] --out results.json
                              [--rank] [--piece-length-factor F]

--rank (cornerflat only): also re-rank the layout candidates by tapered resistance (kicoil.taper.rank_cornerflat_by_taper).
"""

import sys
import os
import json
import time
import math
import argparse
import warnings
import logging
import traceback
import dataclasses
from pathlib import Path
import multiprocessing

sys.path.insert(0, str(Path(__file__).parent))

import corpus as corpus_mod
import geomcheck
from run_corpus import build_model


def _check(fp, model, intent, sample_step):
    cu = geomcheck.extract_copper(fp, layers=model.layer_pair, shapes=True)
    rep = geomcheck.check_layout(cu, intent, sample_step=sample_step)
    kinds = rep.failure_kinds(intent.clearance, intent.trace_width)
    return dict(failures=kinds, status='fail' if kinds else 'pass', rel_deficit=rep.worst_clearance_deficit / intent.clearance,
                rel_via_deficit=rep.worst_via_deficit / intent.clearance,
                rel_pad_deficit=rep.worst_pad_deficit / intent.clearance, min_width=rep.min_width,
                max_width=rep.max_width, taper_pieces=rep.taper_pieces, taper_gaps=rep.taper_gaps,
                piece_width_error=rep.piece_width_error, stray=rep.stray_copper, notes=rep.notes[:4],
                n_items=rep.n_segments)


def _counts(fp, layers):
    lines = sum(1 for l in fp.lines if l.layer in layers)
    arcs = sum(1 for a in fp.arcs if a.layer in layers)
    polys = sum(1 for p in fp.polygons if p.layer in layers)
    circles = sum(1 for c in fp.circles if c.layer in layers)
    return dict(lines=lines, arcs=arcs, polys=polys, circles=circles, total=lines + arcs + polys + circles)


def run_case(args):
    spec, impl, opts = args
    from kicoil import taper
    res = {'name': spec['name'], 'tags': spec['tags'], 'turns': spec['turns'], 'twists': spec['twists'],
           'layers': spec['layers'], 'annular_width': spec.get('annular_width'), 'shape': spec['shape']}
    logging.getLogger('kicoil').setLevel(logging.ERROR)
    t0 = time.perf_counter()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            model = build_model(spec, impl)
            fp_const = model.render_footprint(circle_segments=64)
    except Exception as e:
        res['status'] = 'rejected' if isinstance(e, ValueError) else 'error'
        res['error'] = f'{type(e).__name__}: {e}'.splitlines()[0][:300]
        return res
    res['gen_time'] = time.perf_counter() - t0
    res['w0'] = model.trace_width
    res['clearance'] = model.clearance
    res['pitch'] = model.spiral_pitch
    res['depth_ratio'] = None
    sk = getattr(model.shape, 'sk', None)
    if sk is not None and getattr(sk, 'max_depth', None):
        res['depth_ratio'] = model.shape.annular_width / sk.max_depth
    res['layout_key'] = list(model._layout_key()) if hasattr(model, '_layout_key') else None
    layers = tuple(model.layer_pair)
    try:
        base = geomcheck.intent_from_model(model)
        step = 2 * base.pitch
        res['const'] = _check(fp_const, model, base, step)
        res['const']['counts'] = _counts(fp_const, layers)

        t1 = time.perf_counter()
        r = taper.taper_layout(model, piece_length=opts.get('piece_length_factor', 0.5) * model.spiral_pitch)
        res['taper_time'] = time.perf_counter() - t1
        res['r_const'] = r.r_const
        res['r_taper_vertex'] = r.r_taper
        res['r_taper'] = r.resistance()
        res['gain'] = r.r_const / res['r_taper']
        res['gain_vertex'] = r.r_const / r.r_taper
        res['lo'] = r.lo
        res['t_min_width'] = r.min_width
        res['t_max_width'] = float(r.widths.max())
        res['forced'] = r.forced
        res['unresolved'] = r.unresolved
        res['n_vertices'] = len(r.widths)
        res['fill_const'] = r.fill_fraction()
        for style in ('v', 'poly'):
            t2 = time.perf_counter()
            prims = r.primitives(style)
            fp = r.footprint(style)
            res[f'{style}_emit_time'] = time.perf_counter() - t2
            gap, where = r.verify(style, prims)
            intent = dataclasses.replace(base, variable_width=True, width_range=(r.lo - 1e-6, None),
                                         piece_widths=r.piece_intent())
            d = _check(fp, model, intent, step)
            d['verify_gap'] = gap if math.isfinite(gap) else None
            d['verify_where'] = list(map(float, where)) if where is not None else None
            d['counts'] = _counts(fp, layers)
            d['fill'] = r.fill_fraction(style)
            res[style] = d
        # The constant layout checked in variable width mode must give the same verdict (no false positives)
        intent = dataclasses.replace(base, variable_width=True, width_range=(0.0, None))
        res['const_var'] = _check(fp_const, model, intent, step)['failures']

        if opts.get('rank') and hasattr(model, '_measure_cache'):
            def make(cls):
                import importlib
                geometry = importlib.import_module(f'kicoil.{impl}')
                poly = [tuple(p) for p in spec['polygon']] if spec['shape'] != 'circle' else None
                shape = (geometry.PolygonShape(polygon=poly, annular_width=spec['annular_width']) if poly else
                         geometry.CircleShape(spec['outer_diameter'], spec['inner_diameter']))
                kw = dict(turns=spec['turns'], twists=spec['twists'], layers=spec['layers'],
                          clockwise=spec['clockwise'], clearance=spec['clearance'])
                if spec.get('trace_width'):
                    kw['trace_width'] = spec['trace_width']
                return cls(shape=shape, **kw)
            t3 = time.perf_counter()
            ranked = taper.rank_cornerflat_by_taper(make, model, max_candidates=opts.get('max_candidates', 8),
                                                    piece_length=opts.get('piece_length_factor', 0.5) * model.spiral_pitch)
            res['rank'] = [dict(key=list(c['key']), spacing=c.get('spacing'), w0=c.get('w0'), r_const=c.get('r_const'),
                                r_taper=c.get('r_taper'), vias_ok=c.get('vias_ok'), default=c['default'],
                                error=c.get('error')) for c in ranked]
            res['rank_time'] = time.perf_counter() - t3
    except Exception as e:
        res['status'] = 'error'
        res['error'] = f'{type(e).__name__}: {e}'[:300]
        res['traceback'] = traceback.format_exc()[-2000:]
        return res
    res['status'] = 'ok'
    res['time'] = time.perf_counter() - t0
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--impl', default='kicoil')
    ap.add_argument('--kind', default='full')
    ap.add_argument('--out', required=True)
    ap.add_argument('--filter', action='append')
    ap.add_argument('--every', type=int, default=1, help='take every n-th case')
    ap.add_argument('-j', type=int, default=1)
    ap.add_argument('--rank', action='store_true')
    ap.add_argument('--max-candidates', type=int, default=8)
    ap.add_argument('--piece-length-factor', type=float, default=0.5)
    args = ap.parse_args()

    cases = corpus_mod.corpus(args.kind)
    if args.filter:
        cases = [c for c in cases if any(f in c['name'] for f in args.filter)]
    cases = cases[::args.every]
    import kicoil.geometry  # noqa: compile the wasm module once before the workers start
    if args.impl != 'kicoil' and cases:
        build_model(cases[0], args.impl)
    opts = dict(rank=args.rank, max_candidates=args.max_candidates, piece_length_factor=args.piece_length_factor)
    jobs = [(c, args.impl, opts) for c in cases]
    t0 = time.perf_counter()
    if args.j <= 1:
        results = []
        for job in jobs:
            results.append(run_case(job))
    else:
        ctx = multiprocessing.get_context('forkserver')
        with ctx.Pool(args.j) as pool:
            results = pool.map(run_case, jobs, chunksize=1)
    print(f'{len(results)} cases in {time.perf_counter() - t0:.0f} s')
    Path(args.out).write_text(json.dumps(results, indent=1, default=str))


if __name__ == '__main__':
    main()
