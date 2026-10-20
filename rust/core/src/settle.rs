//! Settling (`sfc._settle`) and length matching (`sfc._match`): each trace moved, step by
//! step, towards the middle of the room either side of it, never nearer other copper than a
//! pitch nor across it; U-turn tips on out into the gap before them; lengths steered as it
//! goes and matched at the end. See ARCHITECTURE.md (Space-filling curve, 9. Settling).

use std::collections::HashSet;

use crate::geom::{add, closest, crosses, dist, dot, norm, resample, scale, sub, P};
use crate::grid::Grid;
use crate::par::pmap;
use crate::traces::{Traces, NONE};
use crate::zones::Zones;

/// The constants of `sfc.py` (`SETTLE*`, `MATCH*`), passed in so Python stays their source.
#[derive(Clone, Debug)]
pub struct Params {
    pub steps: usize,       // SETTLE
    pub rate: f64,          // SETTLE_RATE
    pub reach: f64,         // SETTLE_REACH
    pub pin: f64,           // SETTLE_PIN
    pub cool: f64,          // SETTLE_COOL
    pub step: f64,          // SETTLE_STEP
    pub still: f64,         // SETTLE_STILL
    pub band: f64,          // SETTLE_BAND
    pub leap: f64,          // SETTLE_LEAP
    pub tune: f64,          // SETTLE_TUNE
    pub steer: f64,         // SETTLE_STEER
    pub span: usize,        // SETTLE_SPAN
    pub steer_cool: f64,    // SETTLE_STEER_COOL
    pub tip: f64,           // SETTLE_TIP
    pub reach_out: f64,     // SETTLE_REACH_OUT
    pub match_steps: usize, // MATCH
    pub match_band: f64,    // MATCH_BAND
    pub match_rate: f64,    // MATCH_RATE
}

impl Default for Params {
    fn default() -> Params {
        Params {
            steps: 40,
            rate: 0.5,
            reach: 3.0,
            pin: 1.5,
            cool: 2.0,
            step: 0.35,
            still: 0.005,
            band: 1.0,
            leap: 0.34,
            tune: 3.0,
            steer: 0.6,
            span: 25,
            steer_cool: 2.0,
            tip: 1.0,
            reach_out: 1.0,
            match_steps: 20,
            match_band: 15.0,
            match_rate: 0.5,
        }
    }
}

/// What to settle: the traces (offsets of one curve, from the exit), the pitch, the edge
/// (points along the area's edge and the zones' borders but at the curve's joins), the
/// zones (each its rings), and the exit (a box left as laid).
pub struct Input {
    pub lines: Vec<Vec<P>>,
    pub pitch: f64,
    pub edge: Vec<P>,
    pub zones: Vec<Vec<Vec<P>>>,
    pub keep: [f64; 4],
}

/// How far settling has got, after each step.
#[derive(Clone, Debug, Default)]
pub struct Status {
    pub phase: &'static str, // "settle" or "match"
    pub step: usize,         // (steps done in this phase)
    pub steps: usize,        // (at most)
    pub vertices: usize,
    pub looked: usize,   // (vertices centred this step)
    pub moved: usize,    // (vertices that moved)
    pub checked: usize,  // (vertex-segment pairs measured for clearance)
    pub apart: Vec<f64>, // (each neighbouring pair's largest difference in length run)
}

struct Ctx<'a> {
    pitch: f64,
    step: f64,
    near: f64,
    far: f64,
    own: f64,
    pin: usize,
    zones: &'a Zones,
    keep: [f64; 4],
    edge: &'a [P],
    edges: &'a Grid,
}

pub fn settle(input: &Input, prm: &Params, progress: &mut dyn FnMut(&Status)) -> Vec<Vec<P>> {
    let pitch = input.pitch;
    let step = prm.step * pitch;
    let zones = Zones::new(&input.zones, 2.0 * pitch);
    let edges = Grid::new(&input.edge, prm.reach * pitch, |_| true);
    let cx = Ctx {
        pitch,
        step,
        near: 1.5 * pitch,
        far: prm.reach * pitch,
        own: 0.5 * pitch,
        pin: (prm.reach / prm.step).ceil() as usize,
        zones: &zones,
        keep: input.keep,
        edge: &input.edge,
        edges: &edges,
    };
    let lines: Vec<Vec<P>> = input.lines.iter().map(|t| resample(t, step)).collect();
    let mut tr = Traces::new(&lines, None);
    let n = tr.traces();
    let total = input
        .lines
        .iter()
        .map(|t| t.windows(2).map(|w| dist(w[0], w[1])).sum::<f64>())
        .fold(0.0, f64::max);
    let bins = ((total / (2.0 * pitch)) as usize).max(1);
    // (each trace's length by position, as laid: before resampling, which shaves more off
    // some, the inner in tight turns)
    let base = Traces::new(&input.lines, None).binned(bins);
    let mut gained = minus(&tr.binned(bins), &base);
    let sides = neighbour_sides(&tr);
    let mut hot: Option<HashSet<(i64, i64)>> = None;
    let mut status = Status {
        phase: "settle",
        steps: prm.steps,
        ..Default::default()
    };
    for it in 0..prm.steps {
        let f = 1.0 - it as f64 / prm.steps as f64;
        let (cool, steer) = (f.powf(prm.cool), prm.steer * f.powf(prm.steer_cool));
        let p = tr.p.clone();
        let arc = tr.arc();
        let normal = tr.normals();
        let at = tr.bins(bins);
        let (fixed, zone) = held(&tr, &cx);
        let look: Vec<usize> = match &hot {
            None => (0..tr.len()).collect(),
            Some(h) => (0..tr.len())
                .filter(|&i| h.contains(&cell(p[i], cx.near)))
                .collect(),
        };
        let curv = tr.turning(2);
        // a U-turn's tip, as tight as a ribbon's: on out along its axis
        let tip = bend_axes(&tr, &curv, &normal, prm.tip * n as f64 * pitch);
        let verts = Grid::new(&tr.p, cx.near / 2.0, |_| true);
        let pushes = pmap(look.len(), |k| {
            let i = look[k];
            let lean = -prm.reach_out * dot(tip[i], normal[i]);
            centring(&tr, &arc, &normal, &verts, cx.edge, cx.edges, i, lean, &cx)
        });
        let mut push = vec![0.0; tr.len()];
        for (k, &i) in look.iter().enumerate() {
            push[i] = pushes[k] * prm.rate * cool;
        }
        // a tight bend: no move along its axis into it (its tip pinned, its legs may close)
        let axis = bend_axes(&tr, &curv, &normal, prm.pin * pitch);
        let bend = tr.bends();
        let run: Vec<Vec<f64>> = gained.iter().map(|g| cumsum(g)).collect();
        // (per neighbouring pair: where along the curve the first gains on the second)
        let making: Vec<Vec<Vec<f64>>> = (0..n)
            .map(|t| {
                (0..n)
                    .map(|u| {
                        if t.abs_diff(u) == 1 {
                            window(&minus1(&gained[t], &gained[u]), prm.span)
                        } else {
                            Vec::new()
                        }
                    })
                    .collect()
            })
            .collect();
        let mut mv: Vec<P> = pmap(tr.len(), |i| {
            if fixed[i] {
                return [0.0, 0.0];
            }
            let mut m = scale(normal[i], push[i]);
            let into = dot(m, axis[i]);
            if into > 0.0 {
                m = sub(m, scale(axis[i], into));
            }
            // length steered (by the length each trace has run from the exit, at its place
            // along the curve), only where a lead is still being built up
            let (t, w) = (tr.net[i], at[i]);
            let mut grow: f64 = 0.0;
            for u in [t.wrapping_sub(1), t + 1] {
                if u >= n {
                    continue;
                }
                let lead = run[t][w] - run[u][w];
                let mut l = lead.signum() * (lead.abs() - prm.band * pitch).max(0.0);
                if l * making[t][u][w] <= 0.0 {
                    l = 0.0;
                }
                l /= prm.tune * pitch;
                grow = grow.max((-l).clamp(0.0, 1.0));
                let toward = scale(normal[i], sides[t][u]);
                let bump = dot(bend[i], toward) < 0.0; // (a bump towards the neighbour)
                let give = l.clamp(0.0, 1.0) * if bump { 1.0 } else { (l - 1.0).clamp(0.0, 1.0) };
                m = add(m, scale(bend[i], steer * give));
            }
            m = sub(m, scale(bend[i], steer * grow));
            let size = norm(m);
            if size < prm.still * pitch {
                return [0.0, 0.0];
            }
            scale(m, (prm.leap * step / size.max(1e-12)).min(1.0))
        });
        let mut new: Vec<P> = (0..tr.len()).map(|i| add(p[i], mv[i])).collect();
        // jitter smoothed away (Taubin: no shrinking) round what moved, but where fixed
        let moving: Vec<bool> = mv.iter().map(|m| m[0] != 0.0 || m[1] != 0.0).collect();
        let busy: Vec<bool> = (0..tr.len())
            .map(|i| {
                let (a, b) = (tr.prev[i], tr.next[i]);
                a != NONE && b != NONE && !fixed[i] && (moving[i] || moving[a] || moving[b])
            })
            .collect();
        for f in [0.3, -0.32] {
            let lap: Vec<P> = (0..tr.len())
                .map(|i| {
                    if !busy[i] {
                        return [0.0, 0.0];
                    }
                    let (a, b) = (tr.prev[i], tr.next[i]);
                    sub(scale(add(new[a], new[b]), 0.5), new[i])
                })
                .collect();
            for i in 0..tr.len() {
                if busy[i] {
                    new[i] = add(new[i], scale(lap[i], f));
                }
            }
        }
        for i in 0..tr.len() {
            // (the smoothing's least touches: not moves; no vertex into another zone)
            if dist(new[i], p[i]) < prm.still * pitch / 4.0 || cx.zones.of(new[i]) != zone[i] {
                new[i] = p[i];
            }
        }
        let checked;
        (new, checked) = keep_clear(&tr, &p, new, &cx);
        mv.iter_mut()
            .enumerate()
            .for_each(|(i, m)| *m = sub(new[i], p[i]));
        let moved: Vec<usize> = (0..tr.len())
            .filter(|&i| norm(mv[i]) > 0.02 * pitch)
            .collect();
        status.step = it + 1;
        status.vertices = tr.len();
        status.looked = look.len();
        status.moved = moved.len();
        status.checked = checked;
        if moved.is_empty() {
            status.apart = apart(&gained);
            progress(&status);
            break;
        }
        let mut h = HashSet::new();
        for &i in &moved {
            let (a, b) = cell(new[i], cx.near);
            for dx in -1..=1 {
                for dy in -1..=1 {
                    h.insert((a + dx, b + dy));
                }
            }
        }
        hot = Some(h);
        tr.p = new;
        tr = tr.respaced(step);
        gained = minus(&tr.binned(bins), &base);
        status.apart = apart(&gained);
        progress(&status);
    }
    matched(tr, &base, bins, prm, &cx, progress).lines()
}

/// The settled traces matched in length (`sfc._match`): where one runs (from the exit) more
/// than `match_band` pitches ahead of the shortest, its bends there straightened by as much
/// as takes it back, over a few steps; never lengthened.
fn matched(
    mut tr: Traces,
    base: &[Vec<f64>],
    bins: usize,
    prm: &Params,
    cx: &Ctx,
    progress: &mut dyn FnMut(&Status),
) -> Traces {
    let mut status = Status {
        phase: "match",
        steps: prm.match_steps,
        ..Default::default()
    };
    for it in 0..prm.match_steps {
        let gained = minus(&tr.binned(bins), base);
        let excess = excess(&gained, prm.match_band * cx.pitch);
        let most = excess.iter().flatten().fold(0.0, |a: f64, &b| a.max(b));
        status.step = it;
        status.vertices = tr.len();
        status.apart = apart(&gained);
        if most < 0.01 * cx.pitch {
            break;
        }
        // (spread over the places round it, so that there are bends enough to straighten;
        // each place's share of what it holds beyond its length as laid, at most all)
        let share: Vec<Vec<f64>> = (0..gained.len())
            .map(|t| {
                let want = window(&excess[t], prm.span);
                let held = window(
                    &gained[t].iter().map(|g| g.max(0.0)).collect::<Vec<_>>(),
                    prm.span,
                );
                want.iter()
                    .zip(&held)
                    .map(|(w, h)| (w / h.max(1e-9)).clamp(0.0, 1.0))
                    .collect()
            })
            .collect();
        let p = tr.p.clone();
        let at = tr.bins(bins);
        let (fixed, zone) = held(&tr, cx);
        let bend = tr.bends();
        let mut new: Vec<P> = (0..tr.len())
            .map(|i| {
                if fixed[i] {
                    return p[i];
                }
                add(
                    p[i],
                    scale(bend[i], prm.match_rate * share[tr.net[i]][at[i]]),
                )
            })
            .collect();
        for i in 0..tr.len() {
            if cx.zones.of(new[i]) != zone[i] {
                new[i] = p[i];
            }
        }
        let checked;
        (new, checked) = keep_clear(&tr, &p, new, cx);
        status.checked = checked;
        status.moved = (0..tr.len()).filter(|&i| new[i] != p[i]).count();
        tr.p = new;
        tr = tr.respaced(cx.step);
        status.step = it + 1;
        progress(&status);
    }
    tr
}

/// For each trace and place along the curve: how much length to take out there so that no
/// trace runs more than `band` ahead of the shortest, taken out where it gets ahead.
fn excess(gained: &[Vec<f64>], band: f64) -> Vec<Vec<f64>> {
    let n = gained.len();
    let bins = gained[0].len();
    let mut out = vec![vec![0.0; bins]; n];
    let mut run = vec![0.0; n];
    let mut taken = vec![0.0; n];
    for b in 0..bins {
        for t in 0..n {
            run[t] += gained[t][b];
        }
        let least = (0..n).map(|t| run[t] - taken[t]).fold(f64::MAX, f64::min);
        for t in 0..n {
            let over = (run[t] - taken[t] - (least + band)).max(0.0);
            out[t][b] = over;
            taken[t] += over;
        }
    }
    out
}

/// The vertices settling leaves where they are (the traces' ends and a few vertices on, the
/// exit, and a few pitches either way of where a trace crosses from one zone into another),
/// and each vertex's zone (none moves from one into another).
fn held(tr: &Traces, cx: &Ctx) -> (Vec<bool>, Vec<Option<usize>>) {
    let [x0, y0, x1, y1] = cx.keep;
    let mut fixed: Vec<bool> = (0..tr.len())
        .map(|i| {
            let q = tr.p[i];
            tr.prev[i] == NONE
                || tr.next[i] == NONE
                || (q[0] > x0 && q[0] < x1 && q[1] > y0 && q[1] < y1)
        })
        .collect();
    fixed = spread(tr, fixed, 4);
    let zone: Vec<Option<usize>> = pmap(tr.len(), |i| cx.zones.of(tr.p[i]));
    let join: Vec<bool> = (0..tr.len())
        .map(|i| tr.next[i] != NONE && zone[i] != zone[tr.next[i]])
        .collect();
    let join = spread(tr, join, cx.pin);
    (
        fixed.iter().zip(&join).map(|(a, b)| *a || *b).collect(),
        zone,
    )
}

/// `mask` grown `k` vertices either way along the traces.
fn spread(tr: &Traces, mut mask: Vec<bool>, k: usize) -> Vec<bool> {
    for _ in 0..k {
        let was = mask.clone();
        for i in 0..tr.len() {
            if (tr.prev[i] != NONE && was[tr.prev[i]]) || (tr.next[i] != NONE && was[tr.next[i]]) {
                mask[i] = true;
            }
        }
    }
    mask
}

/// How far (to the left: positive) the middle between the nearest copper either side of
/// vertex `i` is, short of a pitch from it (half one from the edge, which stands for copper
/// at twice its distance), leaning by `lean` of the room; nothing within reach: a hole.
#[allow(clippy::too_many_arguments)]
fn centring(
    tr: &Traces,
    arc: &[f64],
    normal: &[P],
    verts: &Grid,
    edge: &[P],
    edges: &Grid,
    i: usize,
    lean: f64,
    cx: &Ctx,
) -> f64 {
    let (q, n, t) = (tr.p[i], normal[i], tr.net[i]);
    let mut side = [cx.far, cx.far]; // (left, right)
    let look = |r: f64, side: &mut [f64; 2]| {
        verts.within(q, r, |j, d2| {
            if d2 <= 0.0 {
                return;
            }
            let (v, dd) = (sub(tr.p[j], q), d2.sqrt());
            if tr.net[j] == t && (arc[j] - arc[i]).abs() <= cx.own {
                return;
            }
            let across = dot(v, n);
            if across >= 0.7 * dd {
                side[0] = side[0].min(dd);
            } else if -across >= 0.7 * dd {
                side[1] = side[1].min(dd);
            }
        });
    };
    look(cx.near, &mut side);
    if side[0] >= cx.far || side[1] >= cx.far {
        look(cx.far, &mut side); // (further only where nothing that near)
    }
    // the edge: the nearest point on either side (most vertices: none near, at once)
    let mut de = [cx.far, cx.far];
    if edges.any_around(q, 2.0 * cx.far) {
        edges.within(q, 2.0 * cx.far, |e, d2| {
            let (v, d) = (sub(edge[e], q), d2.sqrt());
            let k = if dot(v, n) > 0.0 { 0 } else { 1 };
            if dot(v, n) != 0.0 && d < de[k] {
                de[k] = d;
            }
        });
    }
    let (left, right) = (side[0].min(2.0 * de[0]), side[1].min(2.0 * de[1]));
    let push = (left - right) / 2.0 + lean * ((left + right) / 2.0 - cx.pitch).max(0.0);
    if push > 0.0 {
        push.min((left - cx.pitch).min(de[0] - cx.pitch / 2.0))
    } else {
        push.max(-(right - cx.pitch).min(de[1] - cx.pitch / 2.0))
    }
}

/// For each vertex in a bend tighter than `radius` (zero elsewhere): the direction into the
/// bend at its tightest point (its axis, pointing in).
fn bend_axes(tr: &Traces, curv: &[f64], normal: &[P], radius: f64) -> Vec<P> {
    let mut axis = vec![[0.0, 0.0]; tr.len()];
    let tight = |i: usize| curv[i].abs() * radius > 1.0;
    let mut i = 0;
    while i < tr.len() {
        if !tight(i) {
            i += 1;
            continue;
        }
        // a run of tight vertices along a trace, turning the same way
        let mut j = i;
        let mut best = i;
        while tr.next[j] != NONE
            && tight(tr.next[j])
            && curv[tr.next[j]].signum() == curv[i].signum()
        {
            j = tr.next[j];
            if curv[j].abs() >= curv[best].abs() {
                best = j;
            }
        }
        let a = scale(normal[best], curv[best].signum());
        axis[i..=j].fill(a);
        i = j + 1;
    }
    axis
}

/// `new` with the vertices that would come nearer other copper than a pitch (with a margin),
/// or whose segments would cross, back where they were (`old`). A trace's own copper counts
/// where it faces itself (straight across, or much further along it than away): it may
/// turn sharply, but not pinch. Also how many vertex-segment pairs it measured.
fn keep_clear(tr: &Traces, old: &[P], mut new: Vec<P>, cx: &Ctx) -> (Vec<P>, usize) {
    let need = 1.01 * cx.pitch;
    let len = tr.len();
    let mut check: Vec<usize> = (0..len).filter(|&i| new[i] != old[i]).collect();
    let mut measured = 0;
    let grow = (0..len).map(|i| dist(new[i], old[i])).fold(0.0, f64::max);
    for _ in 0..6 {
        if check.is_empty() {
            break;
        }
        let mut at = tr.clone();
        at.p = new.clone();
        let arc = at.arc();
        let normal = at.normals();
        let longest = (0..len)
            .filter(|&i| tr.next[i] != NONE)
            .map(|i| dist(new[i], new[tr.next[i]]))
            .fold(0.0, f64::max);
        let reach = need + longest;
        // (segments by their first vertex)
        let segs = Grid::new(&new, reach / 2.0, |i| tr.next[i] != NONE);
        let found: Vec<(bool, usize)> = pmap(check.len(), |k| {
            let q = check[k];
            let tangent = [normal[q][1], -normal[q][0]];
            let (mut bad, mut count) = (false, 0);
            segs.within(new[q], reach, |s, _| {
                if bad {
                    return;
                }
                count += 1;
                let s1 = tr.next[s];
                let (c, t) = closest(new[q], new[s], new[s1]);
                let v = sub(c, new[q]);
                let d = norm(v);
                if d >= need {
                    return;
                }
                if tr.net[s] != tr.net[q] {
                    bad = true;
                    return;
                }
                let sep = (arc[s] + t * (arc[s1] - arc[s]) - arc[q]).abs();
                if sep > cx.own && (dot(v, tangent).abs() < 0.5 * d.max(1e-12) || sep > 2.0 * d) {
                    bad = true;
                }
            });
            // the edge (the area's, the zones' borders): no nearer than half a pitch, so
            // that copper on the far side of a fold need never be looked at (as a panel's
            // worker cannot); a vertex already nearer may only move away
            let half = cx.pitch / 2.0;
            if !bad && cx.edges.any_around(new[q], half) {
                let near = |at: P| {
                    let mut d = f64::MAX;
                    cx.edges.within(at, half, |_, d2| d = d.min(d2.sqrt()));
                    d
                };
                let now = near(new[q]);
                bad = now < half && now < near(old[q]);
            }
            (bad, count)
        });
        measured += found.iter().map(|f| f.1).sum::<usize>();
        let mut back: Vec<usize> = (0..check.len())
            .filter(|&k| found[k].0)
            .map(|k| check[k])
            .collect();
        // segments that cross (not merely sharing an end with their neighbours)
        let mut checking = vec![false; len];
        for &q in &check {
            checking[q] = true;
        }
        let touched: Vec<usize> = (0..len)
            .filter(|&s| tr.next[s] != NONE && (checking[s] || checking[tr.next[s]]))
            .collect();
        let crossed: Vec<Vec<usize>> = pmap(touched.len(), |k| {
            let s = touched[k];
            let s1 = tr.next[s];
            let mut out = Vec::new();
            segs.within(new[s], dist(new[s], new[s1]) + longest, |h, _| {
                if h == s || h == tr.prev[s] || h == s1 {
                    return;
                }
                if crosses(new[s], new[s1], new[h], new[tr.next[h]]) {
                    out.extend([s, s1, h, tr.next[h]]);
                }
            });
            out
        });
        back.extend(crossed.into_iter().flatten());
        back.sort_unstable();
        back.dedup();
        if back.is_empty() {
            break;
        }
        for &b in &back {
            new[b] = old[b];
        }
        // (next: what moved near what went back)
        let mut next: Vec<usize> = Vec::new();
        for &b in &back {
            next.push(b);
            if tr.prev[b] != NONE {
                next.push(tr.prev[b]);
            }
            if tr.next[b] != NONE {
                next.push(tr.next[b]);
            }
            segs.within(old[b], reach + grow, |s, _| {
                next.push(s);
                next.push(tr.next[s]);
            });
        }
        next.sort_unstable();
        next.dedup();
        check = next.into_iter().filter(|&i| new[i] != old[i]).collect();
    }
    (new, measured)
}

/// For each two neighbouring traces: on which side of the first (along its normals: 1 left,
/// -1 right) the second runs.
fn neighbour_sides(tr: &Traces) -> Vec<Vec<f64>> {
    let n = tr.traces();
    let normal = tr.normals();
    let mut out = vec![vec![0.0; n]; n];
    for t in 0..n.saturating_sub(1) {
        for (a, b) in [(t, t + 1), (t + 1, t)] {
            let mine: Vec<usize> = (tr.first[a]..tr.first[a + 1]).collect();
            let every = (mine.len() / 60).max(1);
            let (mut left, mut all) = (0, 0);
            for &i in mine.iter().step_by(every) {
                let mut best = (f64::MAX, [0.0, 0.0]);
                for j in tr.first[b]..tr.first[b + 1] - 1 {
                    let (c, _) = closest(tr.p[i], tr.p[j], tr.p[j + 1]);
                    let d = dist(c, tr.p[i]);
                    if d < best.0 {
                        best = (d, c);
                    }
                }
                all += 1;
                if dot(sub(best.1, tr.p[i]), normal[i]) > 0.0 {
                    left += 1;
                }
            }
            out[a][b] = if 2 * left > all { 1.0 } else { -1.0 };
        }
    }
    out
}

fn cell(q: P, size: f64) -> (i64, i64) {
    ((q[0] / size).floor() as i64, (q[1] / size).floor() as i64)
}

fn cumsum(a: &[f64]) -> Vec<f64> {
    let mut s = 0.0;
    a.iter()
        .map(|x| {
            s += x;
            s
        })
        .collect()
}

fn minus(a: &[Vec<f64>], b: &[Vec<f64>]) -> Vec<Vec<f64>> {
    a.iter().zip(b).map(|(a, b)| minus1(a, b)).collect()
}

fn minus1(a: &[f64], b: &[f64]) -> Vec<f64> {
    a.iter().zip(b).map(|(a, b)| a - b).collect()
}

/// The mean over `m` places centred on each (as `np.convolve(a, ones(m) / m, "same")`).
fn window(a: &[f64], m: usize) -> Vec<f64> {
    let mut pre = vec![0.0; a.len() + 1];
    for (k, x) in a.iter().enumerate() {
        pre[k + 1] = pre[k] + x;
    }
    (0..a.len())
        .map(|k| {
            let lo = k.saturating_sub(m / 2);
            let hi = (k + (m - 1) / 2 + 1).min(a.len());
            (pre[hi] - pre[lo]) / m as f64
        })
        .collect()
}

fn apart(gained: &[Vec<f64>]) -> Vec<f64> {
    let run: Vec<Vec<f64>> = gained.iter().map(|g| cumsum(g)).collect();
    (0..run.len().saturating_sub(1))
        .map(|t| {
            run[t]
                .iter()
                .zip(&run[t + 1])
                .map(|(a, b)| (a - b).abs())
                .fold(0.0, f64::max)
        })
        .collect()
}
