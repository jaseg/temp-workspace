"""Mutation tests for the geometric checker (geomcheck.py).

Each test takes the copper of a clean layout from the corpus, injects one kind of defect and asserts that the checker
reports it as the right kind of failure. Further tests make legitimate changes to the copper (geometry other layout
implementations may emit) and assert that the checker still passes it.

The mutations work on the extracted `Copper` object. The conductor is walked independently of the checker (exact
endpoint matches and via centers) to find path order and winding angles.
"""

import copy
import math
import warnings
import logging

import pytest
from shapely.geometry import Polygon, LineString, Point

import corpus
import geomcheck
from geomcheck import Seg, Via, Pad
from run_corpus import build_model


RECT = 'rect40x20_a0.30_n2k1' # 8 long straight segments, one via, pads 1 and 2 on top of each other
SQUARE = 'square40_a0.30_n8k3' # three twists, five vias
CIRCLE = 'circle50x25_n5k1' # arcs
WIDE = 'circle30x6_n2k1' # 11 mm wide traces, two turns
SINGLE = 'hexagon_a0.60_n6_1layer' # single layer, return track on the other layer
LSHAPE = 'l_shape_a0.30_n8k3' # reflex corner, vias at a nonzero offset
CASES = [RECT, SQUARE, CIRCLE, WIDE, SINGLE, LSHAPE]

_cache = {}


def generate(name, **override):
    """ (model, footprint) of a corpus case, with some of its parameters overridden """
    spec = dict(next(c for c in corpus.corpus('full') if c['name'] == name), **override)
    logging.getLogger('kicoil').setLevel(logging.ERROR)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = build_model(spec)
        fp = model.render_footprint(circle_segments=64)
    return model, fp


def load(name, **override):
    """ (intent, copper, failure kinds) of a corpus case, cached; do not modify the copper """
    k = (name, tuple(sorted(override.items())))
    if k not in _cache:
        model, fp = generate(name, **override)
        intent = geomcheck.intent_from_model(model)
        # Arcs to within 1 % of the clearance (at most 5 µm) instead of 0.5 µm: fewer segments, which keeps the tests
        # fast. The chord error stays well below the 5 % clearance tolerance.
        cu = geomcheck.extract_copper(fp, layers=model.layer_pair, arc_tol=min(0.005, 0.01*intent.clearance))
        _cache[k] = (intent, cu, check(cu, intent))
    return _cache[k]


def clean(name, **override):
    """ (intent, copper) of a corpus case that passes the checker; the copper is a fresh copy """
    intent, cu, kinds = load(name, **override)
    if kinds:
        # test_clean_layout_passes fails for the cases in CASES
        pytest.skip(f'{name} does not pass the checker before mutation: {kinds}')
    return intent, copy.deepcopy(cu)


def check(cu, intent, **kw):
    rep = geomcheck.check_layout(cu, intent, **kw)
    return rep.failure_kinds(intent.clearance, intent.trace_width)


def report(cu, intent, **kw):
    return geomcheck.check_layout(cu, intent, **kw)


def key(layer, p):
    return (layer, round(p[0], 6), round(p[1], 6))


def walk(cu):
    """ The conductor from pad 1 to pad 2 as [(segment index, forward)] """
    ends = {}
    for i, s in enumerate(cu.segs):
        ends.setdefault(key(s.layer, s.a), []).append((i, 0))
        ends.setdefault(key(s.layer, s.b), []).append((i, 1))
    vias = {(round(v.x, 6), round(v.y, 6)) for v in cu.vias}
    p1 = next(p for p in cu.pads if p.number == '1')
    cur = key(p1.layers[0], (p1.x, p1.y))
    used, out = set(), []
    while True:
        cand = [(i, e) for i, e in ends.get(cur, []) if i not in used]
        if not cand and cur[1:] in vias:
            for l in cu.layers:
                cand = [(i, e) for i, e in ends.get((l,) + cur[1:], []) if i not in used]
                if cand:
                    break
        if not cand:
            break
        i, e = cand[0]
        used.add(i)
        out.append((i, e == 0))
        s = cu.segs[i]
        cur = key(s.layer, s.b if e == 0 else s.a)
    assert len(out) == len(cu.segs)
    return out


def winding_angles(cu, order, center):
    """ Cumulative winding angle around center at the end of each step of the walk """
    cx, cy = center
    ang = lambda p: math.atan2(p[1]-cy, p[0]-cx)
    total, out = 0.0, []
    for i, fwd in order:
        s = cu.segs[i]
        a, b = (s.a, s.b) if fwd else (s.b, s.a)
        total += (ang(b) - ang(a) + math.pi) % (2*math.pi) - math.pi
        out.append(total)
    return out


def body_distance(cu, p):
    """ Distance from p to the copper edge of the nearest via or pad """
    return min([math.dist(p, (v.x, v.y)) - v.diameter/2 for v in cu.vias] +
               [math.dist(p, (q.x, q.y)) - q.diameter/2 for q in cu.pads])


def joints(cu, order):
    """ Path vertices between two consecutive same-layer segments, away from vias and pads:
    [(step k, point, (seg in, end), (seg out, end))] """
    out = []
    for k in range(len(order) - 1):
        (i, fi), (j, fj) = order[k], order[k+1]
        if cu.segs[i].layer != cu.segs[j].layer:
            continue
        p = cu.segs[i].b if fi else cu.segs[i].a
        if body_distance(cu, p) > 1.0:
            out.append((k, p, (i, 1 if fi else 0), (j, 0 if fj else 1)))
    return out


def set_end(cu, i, e, p):
    if e == 0:
        cu.segs[i].a = tuple(p)
    else:
        cu.segs[i].b = tuple(p)


def move_joint(cu, joint, p):
    _k, _p, (i, ei), (j, ej) = joint
    set_end(cu, i, ei, p)
    set_end(cu, j, ej, p)


def nearest_other_turn(cu, order, th, k, p):
    """ Closest point to p on a segment of a different turn on the same layer: (distance, point) """
    layer = cu.segs[order[k][0]].layer
    best = None
    for m, (j, _f) in enumerate(order):
        s = cu.segs[j]
        if s.layer != layer or abs(th[m] - th[k]) < 1.5*math.pi:
            continue
        ls = LineString([s.a, s.b])
        d = ls.distance(Point(p))
        if best is None or d < best[0]:
            q = ls.interpolate(ls.project(Point(p)))
            best = (d, (q.x, q.y))
    return best


def push_toward_other_turn(cu, intent, gap):
    """ Move a joint toward the neighboring turn until the centerline distance is `gap`. Returns the moved copy. """
    order = walk(cu)
    th = winding_angles(cu, order, intent.center)
    js = joints(cu, order)
    for joint in js[len(js)//3:] + js[:len(js)//3]:
        k, p = joint[0], joint[1]
        nb = nearest_other_turn(cu, order, th, k, p)
        if nb is None or nb[0] > 2*intent.pitch or nb[0] <= gap:
            continue
        d, q = nb
        t = (d - gap) / d
        out = copy.deepcopy(cu)
        move_joint(out, joint, (p[0] + t*(q[0]-p[0]), p[1] + t*(q[1]-p[1])))
        return out
    pytest.skip('no joint next to another turn')


def longest_free_segment(cu):
    """ Index of the longest segment whose ends are away from vias and pads """
    cand = [i for i, s in enumerate(cu.segs) if body_distance(cu, s.a) > 1.0 and body_distance(cu, s.b) > 1.0]
    return max(cand, key=lambda i: cu.segs[i].length)


# ---- the clean layouts pass ----

@pytest.mark.parametrize('name', CASES + ['circle20x18_n5k3', 'rect60x12_a0.30_n8k3'])
def test_clean_layout_passes(name):
    intent, cu, kinds = load(name)
    assert kinds == []
    rep = report(cu, intent)
    assert rep.passed(intent.clearance, intent.trace_width), rep.notes
    assert rep.ok_connectivity and rep.stray_copper == 0 and rep.width_error == 0


# ---- defects ----

@pytest.mark.parametrize('name', [RECT, SQUARE, CIRCLE, SINGLE, LSHAPE])
@pytest.mark.parametrize('gap', [0.01, 0.5])
def test_gap(name, gap):
    intent, cu = clean(name)
    order = walk(cu)
    joint = joints(cu, order)[0]
    _k, p, _a, (j, ej) = joint
    s = cu.segs[j]
    dx, dy = s.b[0]-s.a[0], s.b[1]-s.a[1]
    l = math.hypot(dx, dy)
    set_end(cu, j, ej, (p[0] - dy/l*gap, p[1] + dx/l*gap)) # sideways, so the ends do not overlap collinearly
    rep = report(cu, intent, do_conformance=False)
    assert not rep.ok_connectivity and rep.open_ends + rep.orphans > 0, rep.notes


@pytest.mark.parametrize('name', [RECT, SQUARE, CIRCLE, WIDE, LSHAPE])
def test_deleted_segment(name):
    intent, cu = clean(name)
    del cu.segs[longest_free_segment(cu)]
    rep = report(cu, intent, do_conformance=False)
    assert not rep.ok_connectivity and rep.open_ends > 0


@pytest.mark.parametrize('name', [RECT, SQUARE, SINGLE])
@pytest.mark.parametrize('reverse', [False, True])
def test_duplicated_segment(name, reverse):
    intent, cu = clean(name)
    s = copy.deepcopy(cu.segs[len(cu.segs)//2])
    if reverse:
        s.a, s.b = s.b, s.a
    cu.segs.append(s)
    rep = report(cu, intent, do_conformance=False)
    assert 'duplicate' in rep.failure_kinds(intent.clearance, intent.trace_width) and not rep.ok_connectivity


def test_loose_piece_on_top_of_a_track():
    intent, cu = clean(SQUARE)
    s = cu.segs[longest_free_segment(cu)]
    lerp = lambda t: (s.a[0] + t*(s.b[0]-s.a[0]), s.a[1] + t*(s.b[1]-s.a[1]))
    cu.segs.append(Seg(s.layer, lerp(0.3), lerp(0.6), s.width))
    rep = report(cu, intent, do_conformance=False)
    assert rep.duplicate_segments == 1 and not rep.ok_connectivity


@pytest.mark.parametrize('name', [SQUARE, CIRCLE, LSHAPE])
def test_vertex_pushed_into_clearance(name):
    intent, cu = clean(name)
    # edge-to-edge distance of half the clearance
    cu = push_toward_other_turn(cu, intent, intent.trace_width + 0.5*intent.clearance)
    rep = report(cu, intent, do_conformance=False)
    assert 'clearance' in rep.failure_kinds(intent.clearance, intent.trace_width)
    assert rep.worst_clearance_deficit > 0.4 * intent.clearance


@pytest.mark.parametrize('name', [WIDE, 'circle30x6_n5k1'])
def test_shorted_adjacent_turns_with_wide_traces(name):
    # Few turns of wide traces. In circle30x6_n2k1 neighboring turns are close along the conductor in path length terms
    # (4 (w+c) is more than a revolution), so only the winding angle tells them apart.
    intent, cu = clean(name)
    cu = push_toward_other_turn(cu, intent, 0.75 * intent.trace_width) # copper overlaps by a quarter of the width
    rep = report(cu, intent, do_conformance=False)
    assert 'clearance' in rep.failure_kinds(intent.clearance, intent.trace_width)
    assert rep.worst_clearance_deficit > intent.clearance + 0.2 * intent.trace_width


def outward(intent, p):
    """ Unit vector pointing away from the outline at a point p near its edge """
    contour = Polygon(intent.contour)
    inner = contour.buffer(-1.0)
    q = inner.exterior.interpolate(inner.exterior.project(Point(p)))
    l = math.dist(p, (q.x, q.y))
    return (p[0] - q.x)/l, (p[1] - q.y)/l


@pytest.mark.parametrize('name', [SQUARE, LSHAPE])
@pytest.mark.parametrize('distance', [1.0, 5.0])
def test_via_moved_outside_with_its_tracks(name, distance):
    intent, cu = clean(name)
    contour = Polygon(intent.contour)
    # an outer via (at or outside the outline), moved outwards with a track on each layer to its old place
    vi, v = next((i, v) for i, v in enumerate(cu.vias) if not contour.contains(Point(v.x, v.y)))
    ux, uy = outward(intent, (v.x, v.y))
    nv = (v.x + ux*distance, v.y + uy*distance)
    cu.vias[vi] = Via(nv[0], nv[1], v.diameter)
    for layer in cu.layers:
        cu.segs.append(Seg(layer, (v.x, v.y), nv, intent.trace_width))
    rep = report(cu, intent)
    kinds = rep.failure_kinds(intent.clearance, intent.trace_width)
    assert rep.ok_connectivity, rep.notes
    assert 'conformance' in kinds and 'via offset' in kinds
    assert rep.overshoot > 0.8*distance
    assert rep.via_misplacement > 0.8*distance - intent.via_offset


@pytest.mark.parametrize('name', [RECT, CIRCLE])
def test_outer_turn_pushed_outside(name):
    # 0.2 mm of copper outside the envelope. The overshoot tolerance does not grow with the trace width (here 2.8 and
    # 4.8 mm, which used to allow 0.28 and 0.48 mm).
    intent, cu = clean(name)
    contour = Polygon(intent.contour)
    # a bump in the middle of the outermost segment, its centerline 0.2 mm outside the outline
    i = walk(cu)[1][0]
    s = cu.segs[i]
    lerp = lambda t: (s.a[0] + t*(s.b[0]-s.a[0]), s.a[1] + t*(s.b[1]-s.a[1]))
    m = lerp(0.5)
    ux, uy = outward(intent, m)
    depth = contour.exterior.distance(Point(m))
    m = (m[0] + ux*(depth + 0.2), m[1] + uy*(depth + 0.2))
    cu.segs[i] = Seg(s.layer, s.a, lerp(0.4), s.width)
    cu.segs += [Seg(s.layer, lerp(0.4), m, s.width), Seg(s.layer, m, lerp(0.6), s.width),
                Seg(s.layer, lerp(0.6), s.b, s.width)]
    rep = report(cu, intent)
    assert rep.ok_connectivity
    assert rep.failure_kinds(intent.clearance, intent.trace_width) == ['conformance'], rep.notes
    assert 0.15 < rep.overshoot < 0.25 and rep.uncovered_fraction < 0.05


@pytest.mark.parametrize('name', [SQUARE, CIRCLE])
@pytest.mark.parametrize('scale', [0.5, 1.03])
def test_track_width(name, scale):
    intent, cu = clean(name)
    cu.segs[len(cu.segs)//2].width *= scale
    rep = report(cu, intent, do_conformance=False)
    kinds = rep.failure_kinds(intent.clearance, intent.trace_width)
    assert kinds[0] == 'width' and set(kinds) <= {'width', 'clearance'} # a wider track also eats into the clearance


def test_all_tracks_narrow():
    intent, cu = clean(RECT)
    for s in cu.segs:
        s.width *= 0.3
    rep = report(cu, intent)
    assert 'width' in rep.failure_kinds(intent.clearance, intent.trace_width)
    assert math.isclose(rep.min_width, 0.3 * intent.trace_width)


@pytest.mark.parametrize('name', [SQUARE, LSHAPE])
def test_pad_overlapping_another_turn(name):
    # Pad 1 sits at the outer end of the first turn. Make it an oval reaching inwards across the neighboring turn,
    # without leaving the outline.
    intent, cu = clean(name)
    k, pad = next((k, p) for k, p in enumerate(cu.pads) if p.number == '1')
    cx, cy = intent.center
    ux, uy = cx - pad.x, cy - pad.y
    l = math.hypot(ux, uy)
    reach = intent.pitch + intent.trace_width/2
    angle = -math.degrees(math.atan2(uy, ux))
    cu.pads[k] = Pad(pad.number, pad.layers, pad.x + ux/l*reach/2, pad.y + uy/l*reach/2, reach + pad.diameter,
                     size=(reach + pad.diameter, pad.diameter), shape='oval', angle=angle)
    rep = report(cu, intent)
    assert 'pad clearance' in rep.failure_kinds(intent.clearance, intent.trace_width), rep.notes
    assert rep.worst_pad_deficit > intent.clearance


@pytest.mark.parametrize('name', [SQUARE, CIRCLE])
def test_pad_outside_the_outline(name):
    intent, cu = clean(name)
    k, pad = next((k, p) for k, p in enumerate(cu.pads) if p.number == '1')
    cx, cy = intent.center
    ux, uy = pad.x - cx, pad.y - cy
    l = math.hypot(ux, uy)
    w = intent.trace_width
    # Still contains the track end (0.4 w from its center), but sticks out 0.4 w + 0.6 w - w/2 beyond the envelope
    cu.pads[k] = Pad(pad.number, pad.layers, pad.x + ux/l*0.4*w, pad.y + uy/l*0.4*w, 1.2*w)
    rep = report(cu, intent)
    assert rep.ok_connectivity, rep.notes
    assert 'conformance' in rep.failure_kinds(intent.clearance, intent.trace_width)
    assert rep.overshoot > 0.25*w


@pytest.mark.parametrize('name', [RECT, SQUARE])
def test_copper_on_inner_layer(name):
    intent, cu = clean(name)
    xs = [p[0] for p in intent.contour]
    cu.segs.append(Seg('In1.Cu', (min(xs), 0.0), (max(xs), 0.0), intent.trace_width))
    rep = report(cu, intent, do_conformance=False)
    assert rep.failure_kinds(intent.clearance, intent.trace_width) == ['stray copper']


def test_track_moved_to_inner_layer():
    intent, cu = clean(SQUARE)
    cu.segs[longest_free_segment(cu)].layer = 'In1.Cu'
    kinds = check(cu, intent, do_conformance=False)
    assert 'stray copper' in kinds and 'connectivity' in kinds


def test_unhandled_copper_items():
    intent, cu = clean(RECT)
    cu.unhandled.append('polygon on F.Cu')
    assert check(cu, intent, do_conformance=False) == ['stray copper']


def test_unhandled_footprint_copper_is_extracted():
    from gerbonara.cad.kicad import footprints as fp_mod
    from gerbonara.cad.kicad.primitives import XYCoord
    model, fp = generate(RECT)
    fp.circles.append(fp_mod.Circle(center=XYCoord(0, 0), end=XYCoord(1, 0), layer='F.Cu'))
    fp.circles.append(fp_mod.Circle(center=XYCoord(0, 0), end=XYCoord(1, 0), layer='F.SilkS'))
    cu = geomcheck.extract_copper(fp, layers=model.layer_pair)
    assert cu.unhandled == ['circle on F.Cu']


@pytest.mark.parametrize('name', [RECT, CIRCLE, WIDE])
def test_via_shorting_pad1_and_pad2(name):
    # k = 1: pad 1 (front) and pad 2 (back) sit on top of each other
    intent, cu = clean(name)
    p1 = next(p for p in cu.pads if p.number == '1')
    cu.vias.append(Via(p1.x, p1.y, p1.diameter))
    rep = report(cu, intent, do_conformance=False)
    kinds = rep.failure_kinds(intent.clearance, intent.trace_width)
    assert 'short' in kinds and 'connectivity' in kinds


def test_jumper_bypassing_turns():
    # A via connecting the two layers far from the regular vias, with a track from it straight to pad 2. Every track
    # end is attached, so there are no open ends, but the path can skip part of the coil: the via and pad 2 have three
    # and two track connections (branches).
    intent, cu = clean(RECT)
    order = walk(cu)
    i, fwd = order[1]
    s = cu.segs[i]
    m = ((s.a[0] + s.b[0])/2, (s.a[1] + s.b[1])/2)
    # split the front track at m and connect it to the back layer through a via whose back track goes to pad 2
    cu.segs[i] = Seg(s.layer, s.a, m, s.width)
    cu.segs.append(Seg(s.layer, m, s.b, s.width))
    p2 = next(p for p in cu.pads if p.number == '2')
    cu.vias.append(Via(m[0], m[1], intent.trace_width))
    cu.segs.append(Seg(cu.layers[1], m, (p2.x, p2.y), s.width))
    rep = report(cu, intent, do_conformance=False)
    assert not rep.ok_connectivity
    assert rep.branches == 2 and rep.open_ends == 0 and rep.shorts == 0, rep.notes
    assert any('via at' in n and '3 track connections' in n for n in rep.notes)


@pytest.mark.parametrize('name', [SQUARE, CIRCLE, SINGLE])
def test_stray_via_on_a_track(name):
    intent, cu = clean(name)
    s = cu.segs[longest_free_segment(cu)]
    cu.vias.append(Via((s.a[0] + s.b[0])/2, (s.a[1] + s.b[1])/2, intent.via_diameter))
    rep = report(cu, intent, do_conformance=False)
    assert rep.stray_vias == 1 and not rep.ok_connectivity
    assert 'stray via' in rep.failure_kinds(intent.clearance, intent.trace_width)


@pytest.mark.parametrize('name', [RECT, SQUARE, CIRCLE])
def test_hairpin_backtrack(name):
    # A spike that runs back along the track inside its own copper lane: harmless electrically, but a backtrack
    intent, cu = clean(name)
    order = walk(cu)
    joint = joints(cu, order)[len(joints(cu, order))//2]
    _k, p, _a, (j, ej) = joint
    s = cu.segs[j]
    q = s.b if ej == 0 else s.a
    dx, dy = q[0]-p[0], q[1]-p[1]
    l = math.hypot(dx, dy)
    tip = (p[0] + dx*0.5, p[1] + dy*0.5)
    back = (p[0] + dx/l*0.001, p[1] + dy/l*0.001)
    set_end(cu, j, ej, back)
    cu.segs += [Seg(s.layer, p, tip, s.width), Seg(s.layer, tip, back, s.width)]
    rep = report(cu, intent, do_conformance=False)
    assert rep.ok_connectivity, rep.notes
    assert rep.backtracks > 0
    # The spike stays within the same turn (no winding angle between it and its track), so its copper overlapping the
    # track is a self overlap, not a clearance violation, however long it is.
    assert rep.failure_kinds(intent.clearance, intent.trace_width) == ['backtrack'], rep.notes
    assert not rep.passed(intent.clearance, intent.trace_width)


def test_mirrored_copper_has_wrong_winding():
    intent, cu = clean(SQUARE)
    f = lambda p: (-p[0], p[1])
    for s in cu.segs:
        s.a, s.b = f(s.a), f(s.b)
    cu.vias = [Via(-v.x, v.y, v.diameter) for v in cu.vias]
    for p in cu.pads:
        p.x = -p.x
    assert 'winding' in check(cu, intent, do_conformance=False)


# ---- legitimate variations ----

@pytest.mark.parametrize('name', [RECT, SQUARE, CIRCLE, SINGLE, LSHAPE])
def test_track_end_inside_via(name):
    intent, cu = clean(name)
    v = cu.vias[0]
    for i, s in enumerate(cu.segs):
        for e, p in ((0, s.a), (1, s.b)):
            if math.dist(p, (v.x, v.y)) < 1e-9:
                # pull the end back along its track by 30 % of the via radius
                o = s.b if e == 0 else s.a
                l = math.dist(p, o)
                t = min(0.3*v.diameter/2, 0.5*l) / l
                set_end(cu, i, e, (p[0] + t*(o[0]-p[0]), p[1] + t*(o[1]-p[1])))
                break
        else:
            continue
        break
    assert check(cu, intent) == []


@pytest.mark.parametrize('name', [RECT, SQUARE, WIDE])
def test_track_end_inside_pad(name):
    intent, cu = clean(name)
    pad = next(p for p in cu.pads if p.number == '1')
    for i, s in enumerate(cu.segs):
        for e, p in ((0, s.a), (1, s.b)):
            if math.dist(p, (pad.x, pad.y)) < 1e-9 and s.layer in pad.layers:
                o = s.b if e == 0 else s.a
                l = math.dist(p, o)
                t = min(0.3*pad.diameter/2, 0.5*l) / l
                set_end(cu, i, e, (p[0] + t*(o[0]-p[0]), p[1] + t*(o[1]-p[1])))
    assert check(cu, intent) == []


@pytest.mark.parametrize('name', [RECT, SQUARE, CIRCLE, SINGLE])
def test_pad_slightly_off_track_end(name):
    intent, cu = clean(name)
    pad = next(p for p in cu.pads if p.number == '1')
    cx, cy = intent.center
    l = math.dist((pad.x, pad.y), (cx, cy))
    # 0.01 mm toward the center: the track end stays inside the pad, the pad inside the envelope
    pad.x += (cx - pad.x)/l*0.01
    pad.y += (cy - pad.y)/l*0.01
    assert check(cu, intent) == []


@pytest.mark.parametrize('name', [RECT, SQUARE, CIRCLE, LSHAPE])
def test_track_split_into_overlapping_pieces(name):
    intent, cu = clean(name)
    i = longest_free_segment(cu)
    s = cu.segs[i]
    lerp = lambda t: (s.a[0] + t*(s.b[0]-s.a[0]), s.a[1] + t*(s.b[1]-s.a[1]))
    cu.segs[i] = Seg(s.layer, s.a, lerp(0.6), s.width)
    cu.segs.append(Seg(s.layer, lerp(0.4), s.b, s.width))
    rep = report(cu, intent)
    assert rep.failure_kinds(intent.clearance, intent.trace_width) == [], rep.notes
    assert abs(rep.winding_error) < 1e-6


@pytest.mark.parametrize('name', [SQUARE, SINGLE])
def test_track_split_at_a_point(name):
    intent, cu = clean(name)
    i = longest_free_segment(cu)
    s = cu.segs[i]
    m = ((s.a[0] + s.b[0])/2, (s.a[1] + s.b[1])/2)
    cu.segs[i] = Seg(s.layer, s.a, m, s.width)
    cu.segs.append(Seg(s.layer, m, s.b, s.width))
    assert check(cu, intent) == []


@pytest.mark.parametrize('name', [SQUARE, CIRCLE])
def test_reversed_and_shuffled_segments(name):
    import random
    intent, cu = clean(name)
    for s in cu.segs:
        s.a, s.b = s.b, s.a
    random.Random(1).shuffle(cu.segs)
    assert check(cu, intent) == []


def test_rect_pad_shapes():
    # Square pads of the trace width at the square outline's corner: aligned with the outline they stay within the
    # envelope, rotated by 30 degrees their corners stick out 0.24 mm (via diameter = trace width here, so there is no
    # via allowance either).
    intent, cu = clean(SQUARE)
    for p in cu.pads:
        p.size, p.shape, p.angle = (p.diameter, p.diameter), 'rect', 0.0
    assert check(cu, intent) == []
    for p in cu.pads:
        p.angle = 30.0
    assert check(cu, intent) == ['conformance']


# ---- dots (zero-length tracks) ----

def next_to_other_turn(cu, intent):
    """ (layer, p, q): p is the middle of a long track away from vias and pads, q the closest point of the
    neighboring turn """
    order = walk(cu)
    th = winding_angles(cu, order, intent.center)
    free = set(i for i, s in enumerate(cu.segs) if body_distance(cu, s.a) > 1.0 and body_distance(cu, s.b) > 1.0)
    for k in sorted(range(len(order)), key=lambda k: -cu.segs[order[k][0]].length):
        s = cu.segs[order[k][0]]
        if order[k][0] not in free:
            continue
        p = ((s.a[0] + s.b[0])/2, (s.a[1] + s.b[1])/2)
        nb = nearest_other_turn(cu, order, th, k, p)
        if nb is not None and nb[0] < 1.5*intent.pitch:
            return s.layer, p, nb[1]
    pytest.skip('no track next to another turn')


def between_turns(cu, intent):
    """ (layer, point halfway between a track and the neighboring turn, centerline distance) """
    layer, p, q = next_to_other_turn(cu, intent)
    return layer, ((p[0] + q[0])/2, (p[1] + q[1])/2), math.dist(p, q)


@pytest.mark.parametrize('name', [SQUARE, CIRCLE, LSHAPE])
@pytest.mark.parametrize('length', [0.0, 5e-7])
def test_dot_bridging_two_turns(name, length):
    # KiCad draws a zero-length line as a disk of its stroke width
    intent, cu = clean(name)
    layer, m, d = between_turns(cu, intent)
    cu.segs.append(Seg(layer, m, (m[0] + length, m[1]), d + intent.trace_width))
    rep = report(cu, intent)
    kinds = rep.failure_kinds(intent.clearance, intent.trace_width)
    assert rep.dots == 1
    assert 'clearance' in kinds and rep.worst_clearance_deficit > intent.clearance + 0.4*intent.trace_width
    assert 'connectivity' in kinds and rep.orphans == 1 # its center is not on any track


@pytest.mark.parametrize('name', [SQUARE, CIRCLE])
def test_dot_of_trace_width_bridging_two_turns(name):
    # A dot of the right width attached to a track, reaching into the neighboring turn: only the clearance fails
    intent, cu = clean(name)
    layer, p, q = next_to_other_turn(cu, intent)
    w = intent.trace_width
    # centered just inside the track's copper edge, toward the neighbor; its copper reaches w/2 further
    d = math.dist(p, q)
    c = (p[0] + (q[0] - p[0]) * 0.45*w / d, p[1] + (q[1] - p[1]) * 0.45*w / d)
    cu.segs.append(Seg(layer, c, c, w))
    rep = report(cu, intent)
    assert rep.failure_kinds(intent.clearance, intent.trace_width) == ['clearance'], rep.notes


@pytest.mark.parametrize('name', [SQUARE, LSHAPE])
def test_dot_outside_the_outline(name):
    intent, cu = clean(name)
    cx, cy = intent.center
    pt = max(intent.contour, key=lambda t: math.dist(t, (cx, cy)))
    l = math.dist(pt, (cx, cy))
    o = (pt[0] + (pt[0] - cx)/l*5, pt[1] + (pt[1] - cy)/l*5)
    cu.segs.append(Seg(cu.layers[0], o, o, intent.trace_width))
    rep = report(cu, intent)
    kinds = rep.failure_kinds(intent.clearance, intent.trace_width)
    assert 'conformance' in kinds and rep.overshoot > 4
    assert 'connectivity' in kinds and rep.orphans == 1


@pytest.mark.parametrize('name', [RECT, SQUARE, CIRCLE, LSHAPE])
def test_dots_at_joints_and_vias(name):
    # Dots of the trace width on the conductor (at a joint, on a track, at a via center) are harmless
    intent, cu = clean(name)
    order = walk(cu)
    _k, p, (i, _e), _b = joints(cu, order)[0]
    s = cu.segs[longest_free_segment(cu)]
    m = ((s.a[0] + s.b[0])/2, (s.a[1] + s.b[1])/2)
    v = cu.vias[0]
    cu.segs += [Seg(cu.segs[i].layer, p, p, intent.trace_width), Seg(s.layer, m, m, intent.trace_width),
                Seg(cu.layers[1], (v.x, v.y), (v.x, v.y), intent.trace_width)]
    rep = report(cu, intent)
    assert rep.failure_kinds(intent.clearance, intent.trace_width) == [], rep.notes
    assert rep.dots == 3


# ---- via and pad integrity ----

@pytest.mark.parametrize('name', [SQUARE, LSHAPE])
@pytest.mark.parametrize('defect', ['not plated', 'no annular ring', 'one layer', 'small', 'large drill'])
def test_via_defects(name, defect):
    intent, cu = clean(name)
    v = cu.vias[len(cu.vias)//2]
    if defect == 'not plated':
        v.plated = False
    elif defect == 'no annular ring':
        v.drill = v.diameter
    elif defect == 'one layer':
        v.layers = (cu.layers[0],)
    elif defect == 'small':
        v.diameter *= 0.5
    elif defect == 'large drill':
        v.drill *= 1.2
    rep = report(cu, intent, do_conformance=False)
    kinds = rep.failure_kinds(intent.clearance, intent.trace_width)
    assert 'via' in kinds and rep.via_defects == 1, rep.notes
    message = {'not plated': 'is not plated', 'no annular ring': 'no annular ring', 'one layer': 'copper only on',
               'small': 'diameter is', 'large drill': 'drill is'}[defect]
    assert any(message in n for n in rep.notes), rep.notes
    if defect == 'one layer':
        # the track on the other layer is not connected
        assert 'connectivity' in kinds
    else:
        assert kinds == ['via']


def test_via_type_and_drill_are_extracted():
    from gerbonara.cad.kicad.sexp import Atom
    model, fp = generate(SQUARE)
    via_pads = [p for p in fp.pads if p.number in ('', 'NC')]
    via_pads[0].type = Atom.np_thru_hole
    via_pads[1].drill.diameter = via_pads[1].size.x
    cu = geomcheck.extract_copper(fp, layers=model.layer_pair)
    intent = geomcheck.intent_from_model(model)
    assert [v.plated for v in cu.vias].count(False) == 1
    rep = report(cu, intent, do_conformance=False)
    assert rep.via_defects == 2 and rep.failure_kinds(intent.clearance, intent.trace_width) == ['via']


@pytest.mark.parametrize('name', [RECT, SQUARE, CIRCLE])
def test_pads_too_small(name):
    intent, cu = clean(name)
    for p in cu.pads:
        p.diameter, p.size = 0.01, (0.01, 0.01)
    rep = report(cu, intent)
    assert rep.failure_kinds(intent.clearance, intent.trace_width) == ['pad size'], rep.notes
    assert rep.min_pad_size == 0.01


def test_via_grown_into_the_neighboring_turn():
    intent, cu = clean(SQUARE)
    for v in cu.vias:
        v.diameter += 2*intent.clearance + intent.trace_width
    kinds = check(cu, intent, do_conformance=False)
    assert 'via clearance' in kinds and 'via' in kinds


# ---- crossings ----

@pytest.mark.parametrize('name', [SQUARE, CIRCLE, LSHAPE])
def test_joint_pushed_past_the_neighboring_centerline(name):
    intent, cu = clean(name)
    order = walk(cu)
    th = winding_angles(cu, order, intent.center)
    for joint in joints(cu, order)[2:]:
        k, p = joint[0], joint[1]
        nb = nearest_other_turn(cu, order, th, k, p)
        if nb is None or nb[0] > 2*intent.pitch:
            continue
        d, q = nb
        out = copy.deepcopy(cu)
        move_joint(out, joint, (p[0] + (q[0]-p[0])*(1 + 0.3*intent.pitch/d), p[1] + (q[1]-p[1])*(1 + 0.3*intent.pitch/d)))
        kinds = check(out, intent, do_conformance=False)
        assert 'crossing' in kinds and 'clearance' in kinds, kinds
        return
    pytest.skip('no joint next to another turn')


# ---- stubs and copper inside bodies ----

@pytest.mark.parametrize('name', [CIRCLE, SQUARE, LSHAPE])
@pytest.mark.parametrize('body', ['pad', 'via'])
def test_tail_inside_a_body(name, body):
    # A short piece of track from the center of a pad or via that stays within its copper is harmless
    intent, cu = clean(name)
    b = next(p for p in cu.pads if p.number == '1') if body == 'pad' else cu.vias[0]
    layer = b.layers[0] if body == 'pad' else cu.layers[0]
    r = b.diameter/2
    # along a track that ends at the body's center, so its copper stays within the track's
    s = next(s for s in cu.segs if s.layer == layer and min(math.dist(s.a, (b.x, b.y)), math.dist(s.b, (b.x, b.y))) < 1e-6)
    o = s.b if math.dist(s.a, (b.x, b.y)) < 1e-6 else s.a
    l = math.dist((b.x, b.y), o)
    t = min(0.2*r, 0.5*l) / l
    cu.segs.append(Seg(layer, (b.x, b.y), (b.x + (o[0] - b.x)*t, b.y + (o[1] - b.y)*t), intent.trace_width))
    rep = report(cu, intent)
    assert rep.failure_kinds(intent.clearance, intent.trace_width) == [], rep.notes
    assert rep.stubs == 1


@pytest.mark.parametrize('name', [SQUARE, LSHAPE])
def test_dead_end_at_a_pad(name):
    # A dead-end track at a pad, toward the coil's center: a stub when it is shorter than the pad plus three times the
    # via offset, an open end when it is longer
    intent, cu = clean(name)
    pad = next(p for p in cu.pads if p.number == '1')
    cx, cy = intent.center
    l = math.dist((pad.x, pad.y), (cx, cy))
    u = ((cx - pad.x)/l, (cy - pad.y)/l)
    limit = pad.diameter + 3*intent.via_offset
    for length, stub in ((0.9*limit, True), (1.1*limit + 0.01, False)):
        cu2 = copy.deepcopy(cu)
        m = (pad.x + u[0]*length/2, pad.y + u[1]*length/2)
        e = (pad.x + u[0]*length, pad.y + u[1]*length)
        cu2.segs += [Seg(pad.layers[0], (pad.x, pad.y), m, intent.trace_width),
                     Seg(pad.layers[0], m, e, intent.trace_width)]
        rep = report(cu2, intent, do_conformance=False)
        if stub:
            assert rep.stubs == 1 and rep.ok_connectivity, rep.notes
        else:
            assert rep.stubs == 0 and rep.open_ends == 1 and not rep.ok_connectivity, rep.notes


@pytest.mark.parametrize('name', ['circle20x18_n5k3', 'rect60x12_a0.30_n8k3'])
def test_pads_on_the_outer_via_ring(name):
    # Terminal pads may sit where outer vias sit: one via offset outside the outline (here 0.15 to 0.18 mm)
    intent, cu = clean(name)
    assert intent.via_offset > 0.1
    cx, cy = intent.center
    for pad in cu.pads:
        l = math.dist((pad.x, pad.y), (cx, cy))
        n = (pad.x + (pad.x - cx)/l*intent.via_offset, pad.y + (pad.y - cy)/l*intent.via_offset)
        cu.segs.append(Seg(pad.layers[0], (pad.x, pad.y), n, intent.trace_width))
        pad.x, pad.y = n
    assert check(cu, intent) == []
    # but not further out
    for pad in cu.pads:
        l = math.dist((pad.x, pad.y), (cx, cy))
        n = (pad.x + (pad.x - cx)/l*0.3, pad.y + (pad.y - cy)/l*0.3)
        cu.segs.append(Seg(pad.layers[0], (pad.x, pad.y), n, intent.trace_width))
        pad.x, pad.y = n
    assert check(cu, intent) == ['conformance']


# ---- same turn: folds and wraps ----

def test_wrap_around_a_tiny_hole_is_a_self_short():
    # A trace about 4 mm wide wraps around a hole smaller than itself and touches its own copper 0.25 to 0.46 turns
    # further on, which shorts part of the turn.
    intent, cu, _kinds = load('sector180_a0.90_n3k1')
    rep = report(cu, intent, do_conformance=False)
    if rep.worst_self_overlap < intent.clearance:
        pytest.skip('the generator no longer produces this wrap')
    assert 'self short' in rep.failure_kinds(intent.clearance, intent.trace_width)
    assert rep.worst_self_short > intent.clearance
    assert all(0.18 <= dth < 0.5 for _l, _p, _q, deficit, dth, _ds in rep.self_overlap_points
               if deficit >= intent.clearance and dth >= 0.18)


def test_fold_at_a_tip_is_not_a_self_short():
    # At the narrow ends of an ellipse the conductor folds onto itself (copper contact within 0.07 turns)
    intent, cu, _kinds = load('ellipse3to1_a0.90_n3k1')
    rep = report(cu, intent, do_conformance=False)
    if rep.worst_self_overlap < intent.clearance:
        pytest.skip('the generator no longer produces this fold')
    assert rep.self_shorts == 0
    kinds = rep.failure_kinds(intent.clearance, intent.trace_width)
    assert 'self short' not in kinds and 'clearance' not in kinds
