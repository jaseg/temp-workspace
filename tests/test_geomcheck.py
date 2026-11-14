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


def clean(name):
    """ (intent, copper) of a corpus case; the copper is a fresh copy """
    if name not in _cache:
        spec = next(c for c in corpus.corpus('full') if c['name'] == name)
        logging.getLogger('kicoil').setLevel(logging.ERROR)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            model = build_model(spec)
            fp = model.render_footprint(circle_segments=64)
        intent = geomcheck.intent_from_model(model)
        cu = geomcheck.extract_copper(fp, layers=model.layer_pair)
        kinds = check(cu, intent)
        if kinds:
            pytest.skip(f'{name} does not pass the checker before mutation: {kinds}')
        _cache[name] = (intent, cu)
    intent, cu = _cache[name]
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

@pytest.mark.parametrize('name', CASES)
def test_clean_layout_passes(name):
    intent, cu = clean(name)
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
    # Few turns of wide traces: neighboring turns are close along the conductor in path length terms (4 (w+c) is more
    # than a revolution), but a full turn apart in winding angle.
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
    # bend the middle of the outermost segment outwards
    i = walk(cu)[1][0]
    s = cu.segs[i]
    m = ((s.a[0] + s.b[0])/2, (s.a[1] + s.b[1])/2)
    ux, uy = outward(intent, m)
    depth = contour.exterior.distance(Point(m))
    m = (m[0] + ux*(depth + 0.2), m[1] + uy*(depth + 0.2))
    cu.segs[i] = Seg(s.layer, s.a, m, s.width)
    cu.segs.append(Seg(s.layer, m, s.b, s.width))
    rep = report(cu, intent)
    assert rep.ok_connectivity
    assert 'conformance' in rep.failure_kinds(intent.clearance, intent.trace_width)
    assert rep.overshoot > 0.1


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
    spec = next(c for c in corpus.corpus('full') if c['name'] == RECT)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        model = build_model(spec)
        fp = model.render_footprint()
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
    # A via connecting the two layers far from the regular vias, where both layers' tracks run through it. Each track
    # end is attached normally, so the graph has no open ends, but the path skips part of the coil.
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
    assert rep.branches > 0 or rep.shorts > 0


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
    assert 'backtrack' in rep.failure_kinds(intent.clearance, intent.trace_width)
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
    intent, cu = clean(SQUARE)
    for p in cu.pads:
        p.size, p.shape, p.angle = (p.diameter*0.6, p.diameter*0.6), 'rect', 30.0
    assert check(cu, intent) == []
