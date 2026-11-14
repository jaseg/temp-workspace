"""Tests for tapered (variable width) traces (kicoil.taper) and the checker's variable width mode.

The tapered footprints of a few corpus cases (fixed and cornerflat layouts, both representations) must pass the checker
in variable width mode, keep the clearance on the exact emitted copper, and conduct at least as well as the constant
width layout. The checker must still find defects in variable width copper (mutations), must not change its verdict on
constant width layouts in variable width mode, and must keep rejecting copper polygons in constant width mode.
"""

import copy
import math
import dataclasses
import warnings
import logging

import pytest

import corpus
import geomcheck
from geomcheck import Seg
from run_corpus import build_model

from kicoil import taper


CASES = [('kicoil', 'square40_a0.30_n8k3'), ('kicoil', 'l_shape_a0.30_n8k3'), ('kicoil', 'circle30x6_n2k1'),
         ('kicoil', 'hexagon_a0.60_n6_1layer'), ('geometry_alt_cornerflat', 'square40_a0.30_n8k3'),
         ('geometry_alt_cornerflat', 'l_shape_a0.30_n8k3')]

_cache = {}


def tapered(impl, name):
    key = (impl, name)
    if key not in _cache:
        spec = next(c for c in corpus.corpus('full') if c['name'] == name)
        logging.getLogger('kicoil').setLevel(logging.ERROR)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            model = build_model(spec, impl)
        _cache[key] = (model, taper.taper_layout(model))
    return _cache[key]


def variable_intent(model, res):
    base = geomcheck.intent_from_model(model)
    return dataclasses.replace(base, variable_width=True, width_range=(res.lo - 1e-6, None),
                               piece_widths=res.piece_intent())


def check(cu, intent, **kw):
    rep = geomcheck.check_layout(cu, intent, **kw)
    return rep, rep.failure_kinds(intent.clearance, intent.trace_width)


@pytest.mark.parametrize('impl,name', CASES)
@pytest.mark.parametrize('style', ['v', 'poly'])
def test_tapered_footprint_passes(impl, name, style):
    model, res = tapered(impl, name)
    fp = res.footprint(style)
    cu = geomcheck.extract_copper(fp, layers=model.layer_pair, shapes=True)
    intent = variable_intent(model, res)
    const = geomcheck.check_layout(geomcheck.extract_copper(model.render_footprint(circle_segments=64),
                                                            layers=model.layer_pair), geomcheck.intent_from_model(model))
    rep, kinds = check(cu, intent)
    # the tapered copper must not fail anything the constant width layout passes
    assert set(kinds) <= set(const.failure_kinds(intent.clearance, intent.trace_width)), rep.notes
    assert rep.taper_pieces > 0
    gap, where = res.verify(style)
    assert gap >= -1e-5, where
    assert res.gain >= 0.999
    if style == 'v':
        assert not fp.polygons and not fp.circles
    else:
        assert fp.polygons


@pytest.mark.parametrize('name', ['square40_a0.30_n8k3', 'circle30x6_n2k1', 'hexagon_a0.60_n6_1layer'])
def test_constant_layout_same_verdict_in_variable_mode(name):
    model, _res = tapered('kicoil', name)
    fp = model.render_footprint(circle_segments=64)
    base = geomcheck.intent_from_model(model)
    cu = geomcheck.extract_copper(fp, layers=model.layer_pair, shapes=True)
    rep0, k0 = check(cu, base)
    rep1, k1 = check(cu, dataclasses.replace(base, variable_width=True, width_range=(0.0, None)))
    assert k0 == k1
    assert rep1.taper_pieces == 0
    assert math.isclose(rep0.worst_clearance_deficit, rep1.worst_clearance_deficit, abs_tol=1e-9)


def test_polygons_are_stray_copper_in_constant_mode():
    model, res = tapered('kicoil', 'square40_a0.30_n8k3')
    fp = res.footprint('poly')
    cu = geomcheck.extract_copper(fp, layers=model.layer_pair, shapes=True)
    _rep, kinds = check(cu, geomcheck.intent_from_model(model), do_conformance=False)
    assert 'stray copper' in kinds
    cu = geomcheck.extract_copper(fp, layers=model.layer_pair)
    _rep, kinds = check(cu, geomcheck.intent_from_model(model), do_conformance=False)
    assert 'stray copper' in kinds


def _copper(style, name='square40_a0.30_n8k3', impl='kicoil'):
    model, res = tapered(impl, name)
    fp = res.footprint(style)
    return model, res, geomcheck.extract_copper(fp, layers=model.layer_pair, shapes=True)


def _v_pairs(cu):
    """ Pairs of indices of the two tracks of each V taper (shared start, equal width) """
    by_start = {}
    for i, s in enumerate(cu.segs):
        by_start.setdefault((s.layer, s.a, s.width), []).append(i)
    return [ix for ix in by_start.values() if len(ix) == 2
            and math.isclose(cu.segs[ix[0]].length, cu.segs[ix[1]].length, abs_tol=1e-5)
            and cu.segs[ix[0]].b != cu.segs[ix[1]].b]


def _spread(cu, i, j, h):
    """ Move the far ends of V tracks i and j to h on either side of their midpoint, perpendicular to the V's axis """
    si, sj = cu.segs[i], cu.segs[j]
    mid = ((si.b[0] + sj.b[0])/2, (si.b[1] + sj.b[1])/2)
    ax = (mid[0] - si.a[0], mid[1] - si.a[1])
    l = math.hypot(*ax)
    n = (-ax[1]/l, ax[0]/l)
    if (si.b[0] - mid[0])*n[0] + (si.b[1] - mid[1])*n[1] < 0:
        n = (-n[0], -n[1])
    cu.segs[i] = Seg(si.layer, si.a, (mid[0] + n[0]*h, mid[1] + n[1]*h), si.width)
    cu.segs[j] = Seg(sj.layer, sj.a, (mid[0] - n[0]*h, mid[1] - n[1]*h), sj.width)


def test_v_widened_into_other_turn_is_a_clearance_violation():
    """ Moving the far ends of a V outwards (wider taper) must be caught on the exact copper. """
    model, res, cu = _copper('v')
    intent = variable_intent(model, res)
    intent = dataclasses.replace(intent, piece_widths=None)
    # the V with the least room: closest far end to copper of another turn is hard to find independently, so widen every
    # V by a full clearance on each side; some must then violate the clearance
    for i, j in _v_pairs(cu):
        _spread(cu, i, j, math.dist(cu.segs[i].b, cu.segs[j].b) / 2 + model.clearance)
    rep, kinds = check(cu, intent)
    assert 'taper gap' in kinds or 'clearance' in kinds


def test_v_gap_is_reported():
    model, res, cu = _copper('v')
    intent = dataclasses.replace(variable_intent(model, res), piece_widths=None)
    i, j = _v_pairs(cu)[0]
    _spread(cu, i, j, 0.75 * cu.segs[i].width) # far ends 1.5 track widths apart
    rep, kinds = check(cu, intent, do_conformance=False)
    assert rep.taper_gaps == 1 and 'taper gap' in kinds


def test_v_with_one_track_removed_breaks_the_profile():
    model, res, cu = _copper('v')
    intent = variable_intent(model, res)
    i, j = _v_pairs(cu)[0]
    del cu.segs[j]
    rep, kinds = check(cu, intent, do_conformance=False)
    assert 'connectivity' in kinds or 'width' in kinds


def test_polygon_removed_breaks_connectivity():
    model, res, cu = _copper('poly')
    intent = variable_intent(model, res)
    del cu.polys[len(cu.polys)//2]
    rep, kinds = check(cu, intent, do_conformance=False)
    assert 'connectivity' in kinds


def test_polygon_grown_into_other_turn_is_a_clearance_violation():
    model, res, cu = _copper('poly')
    intent = dataclasses.replace(variable_intent(model, res), piece_widths=None)
    # grow every trapezoid sideways by a clearance (keeping its end edge midpoints)
    for k, (layer, pts) in enumerate(cu.polys):
        p0, p1, p2, p3 = pts
        def grow(a, b):
            m = ((a[0] + b[0])/2, (a[1] + b[1])/2)
            d = (a[0] - m[0], a[1] - m[1])
            l = math.hypot(*d)
            g = (l + model.clearance) / l
            return (m[0] + d[0]*g, m[1] + d[1]*g), (m[0] - d[0]*g, m[1] - d[1]*g)
        p1, p2 = grow(p1, p2)
        p0, p3 = grow(p0, p3)
        cu.polys[k] = (layer, [p0, p1, p2, p3])
    rep, kinds = check(cu, intent, do_conformance=False)
    assert 'clearance' in kinds


def test_unrecognized_polygon_and_circle():
    model, res, cu = _copper('poly')
    intent = variable_intent(model, res)
    cu.polys.append((model.layer_pair[0], [(100, 100), (101, 100), (101, 101), (100, 101)]))
    cu.disks.append((model.layer_pair[0], 100.0, 100.0, 0.3))
    rep, kinds = check(cu, intent, do_conformance=False)
    assert rep.stray_copper == 2 and 'stray copper' in kinds


def test_width_profile_deviation():
    model, res, cu = _copper('v')
    intent = variable_intent(model, res)
    k = next(i for i, s in enumerate(cu.segs) if s.width > res.lo + 0.1)
    s = cu.segs[k]
    cu.segs[k] = Seg(s.layer, s.a, s.b, s.width - 0.05)
    rep, kinds = check(cu, intent, do_conformance=False)
    assert 'width' in kinds and rep.piece_width_error > 0.04


def test_minimum_width_option():
    model, res = tapered('kicoil', 'l_shape_a0.30_n8k3')
    r = taper.taper_layout(model, min_width=0.1, max_width=res.w0 * 1.1)
    assert r.widths.max() <= res.w0 * 1.1 + 1e-9
    assert r.resistance() <= r.r_const * 1.001


def test_v_split_for_steep_tapers():
    prims = taper._v_taper((0.0, 0.0), (1.0, 0.0), 0.2, 1.0, 0, (0, (0.0, 0.0), (1.0, 0.0), 0, 0, 0, 0, 0, 1))
    assert len(prims) == 2 * 3 # 0.2 -> 1.0 needs ceil(log2(5)) = 3 Vs
    for a, b in zip(prims[::2], prims[1::2]):
        sep = math.dist(a['b'], b['b'])
        assert sep <= a['width'] + 1e-9


def test_footprint_round_trip_and_gerber(tmp_path):
    from gerbonara.cad.kicad.footprints import Footprint
    model, res = tapered('kicoil', 'square40_a0.30_n8k3')
    for style in ('v', 'poly'):
        fp = res.footprint(style)
        path = tmp_path / f'coil_{style}.kicad_mod'
        fp.write(path)
        fp2 = Footprint.open_mod(path)
        assert len(fp2.lines) == len(fp.lines) and len(fp2.polygons) == len(fp.polygons)
        cu = geomcheck.extract_copper(fp2, layers=model.layer_pair, shapes=True)
        rep, kinds = check(cu, variable_intent(model, res))
        assert not set(kinds) - {'conformance'}, rep.notes
