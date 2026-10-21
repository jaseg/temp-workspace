//! Settling (`sfc._settle`) and length matching (`sfc._match`): each trace moved, step by
//! step, towards the middle of the room either side of it, never nearer other copper than a
//! pitch nor across it; U-turn tips on out into the gap before them; lengths steered as it
//! goes and matched at the end. See ARCHITECTURE.md (Space-filling curve, 9. Settling).

use std::collections::HashSet;

use crate::density::Density;
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
    pub fill: f64,          // SETTLE_FILL
    pub fill_blur: f64,     // SETTLE_FILL_BLUR
    pub bend: usize,        // SETTLE_BEND
    pub smooth: usize,      // SETTLE_SMOOTH
    pub finish: usize,      // SETTLE_FINISH
    pub match_steps: usize, // MATCH
    pub match_band: f64,    // MATCH_BAND
    pub match_rate: f64,    // MATCH_RATE
    pub ribbon: f64,        // (traces abreast in a lane; 0: a group's)
    pub holes: f64,         // SETTLE_HOLE (0: none filled after)
    pub hole_steps: usize,  // SETTLE_HOLE_STEPS
    pub hole_margin: f64,   // SETTLE_HOLE_MARGIN
    pub hole_ribbon: f64,   // SETTLE_HOLE_RIBBON
    pub phases: usize,      // (which to run: 1 settling, 2 the holes, 4 smoothing and matching)
    pub share: f64,         // SETTLE_SHARE (0: off)
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
            fill: 2.0,
            fill_blur: 0.5,
            bend: 2,
            smooth: 3,
            finish: 10,
            match_steps: 20,
            match_band: 15.0,
            match_rate: 0.5,
            ribbon: 0.0,
            share: 0.0,
            holes: 0.0,
            hole_steps: 160,
            hole_margin: 4.0,
            hole_ribbon: 4.0,
            phases: 7,
        }
    }
}

/// What to settle: the traces (offsets of one curve, from the exit), the pitch, the edge
/// (points along the area's edge and the zones' borders but at the curve's joins), the
/// zones (each its rings), and what is left as laid (the exit: polygons, each its rings).
pub struct Input {
    pub lines: Vec<Vec<P>>,
    pub pitch: f64,
    pub edge: Vec<P>,
    pub zones: Vec<Vec<Vec<P>>>,
    pub keep: Vec<Vec<Vec<P>>>,
    /// Each trace's group (its mesh's partition): lengths matched only within a group, of
    /// neighbours in turn (none given: one group).
    pub groups: Vec<usize>,
    /// The traces left as laid, whole (none given: none), and the box (x0, y0, x1, y1)
    /// outside which nothing moves (none: the whole area).
    pub hold: Vec<bool>,
    pub core: Option<[f64; 4]>,
    /// The traces as first laid, for their lengths (none given: `lines`; given when a
    /// later phase is run on its own).
    pub base: Vec<Vec<P>>,
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
    pub filled: usize,   // (holes filled so far)
}

struct Ctx<'a> {
    pitch: f64,
    step: f64,
    near: f64,
    far: f64,
    own: f64,
    pin: usize,
    zones: &'a Zones,
    keep: &'a Zones,
    group: &'a [usize],
    hold: &'a [bool],
    core: Option<[f64; 4]>,
    edge: &'a [P],
    edges: &'a Grid,
}

pub fn settle(input: &Input, prm: &Params, progress: &mut dyn FnMut(&Status)) -> Vec<Vec<P>> {
    let pitch = input.pitch;
    let step = prm.step * pitch;
    let zones = Zones::new(&input.zones, 2.0 * pitch);
    let keep = Zones::new(&input.keep, 2.0 * pitch);
    let edges = Grid::new(&input.edge, prm.reach * pitch, |_| true);
    let group: Vec<usize> = if input.groups.len() == input.lines.len() {
        input.groups.clone()
    } else {
        vec![0; input.lines.len()]
    };
    let cx = Ctx {
        pitch,
        step,
        near: 1.5 * pitch,
        far: prm.reach * pitch,
        own: 0.5 * pitch,
        pin: (prm.reach / prm.step).ceil() as usize,
        zones: &zones,
        keep: &keep,
        group: &group,
        hold: &input.hold,
        core: input.core,
        edge: &input.edge,
        edges: &edges,
    };
    let laid = if input.base.is_empty() {
        &input.lines
    } else {
        &input.base
    };
    // (resampled to the step to settle; as given to go on from an earlier phase)
    let lines: Vec<Vec<P>> = if prm.phases & 1 != 0 {
        input.lines.iter().map(|t| resample(t, step)).collect()
    } else {
        input.lines.clone()
    };
    let mut tr = Traces::new(&lines, None);
    let n = tr.traces();
    let total = laid
        .iter()
        .map(|t| t.windows(2).map(|w| dist(w[0], w[1])).sum::<f64>())
        .fold(0.0, f64::max);
    let bins = ((total / (2.0 * pitch)) as usize).max(1);
    // (each trace's length by position, as laid: before resampling, which shaves more off
    // some, the inner in tight turns)
    let base = Traces::new(laid, None).binned(bins);
    let mut gained = minus(&tr.binned(bins), &base);
    let sides = neighbour_sides(&tr, &group);
    // (per trace and side, left then right: how many of its group's traces' legs belong
    // between it and its own copper across, there in turn: the room theirs too)
    let across: Vec<[f64; 2]> = (0..n)
        .map(|t| {
            let mut k = [0.0, 0.0];
            for (u, on) in [(t.wrapping_sub(1), -1i64), (t + 1, 1)] {
                if prm.share <= 0.0 || u >= n || group[u] != group[t] {
                    continue;
                }
                let mut v = t as i64 + on;
                while v >= 0 && (v as usize) < n && group[v as usize] == group[t] {
                    k[if sides[t][u] > 0.0 { 0 } else { 1 }] += 2.0;
                    v += on;
                }
            }
            k
        })
        .collect();
    let mut hot: Option<HashSet<(i64, i64)>> = None;
    // (a group's traces, matched in length together, abreast: their U-turns' tips; the
    // density's blur: about the size of the holes where a lane's bends meet)
    let ribbon = (0..n)
        .map(|t| group.iter().filter(|&&g| g == group[t]).count())
        .max()
        .unwrap_or(0) as f64;
    let lane = if prm.ribbon > 0.0 { prm.ribbon } else { ribbon };
    let blur = prm.fill_blur * lane * pitch;
    let mut density = (prm.fill > 0.0).then(|| {
        // (over the zones; a hole's run: round its box)
        let z = bounds(input.zones.iter().flatten().flatten());
        let b = match input.core {
            None => z,
            Some(c) => {
                let m = 3.0 * cx.far;
                [
                    z[0].max(c[0] - m),
                    z[1].max(c[1] - m),
                    z[2].min(c[2] + m),
                    z[3].min(c[3] + m),
                ]
            }
        };
        Density::new(b, blur, |q| zones.of(q).is_some())
    });
    let mut status = Status {
        phase: "settle",
        steps: prm.steps,
        ..Default::default()
    };
    for it in 0..if prm.phases & 1 != 0 { prm.steps } else { 0 } {
        if crate::cancelled() {
            break;
        }
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
        let tip = bend_axes(&tr, &curv, &normal, prm.tip * ribbon * pitch);
        let verts = Grid::new(&tr.p, cx.near / 2.0, |_| true);
        if let Some(d) = density.as_mut() {
            d.update(&tr, pitch);
        }
        let pushes = pmap(look.len(), |k| {
            let i = look[k];
            let lean = -prm.reach_out * dot(tip[i], normal[i]);
            centring(
                &tr,
                &arc,
                &normal,
                &verts,
                cx.edge,
                cx.edges,
                i,
                lean,
                across[tr.net[i]],
                &cx,
            )
        });
        let mut push = vec![0.0; tr.len()];
        for (k, &i) in look.iter().enumerate() {
            push[i] = pushes[k] * prm.rate * cool;
        }
        // copper nearer than the pitch (as laid: at a sharp corner, off to the side where
        // centring does not look): straight away from it
        let crowd: Vec<P> = pmap(tr.len(), |i| crowded(&tr, &arc, &verts, i, &cx));
        // a tight bend: no move along its axis into it (its tip pinned, its sides may close)
        let axis = bend_axes(&tr, &curv, &normal, prm.pin * pitch);
        let bend = tr.bends(prm.bend);
        let run: Vec<Vec<f64>> = gained.iter().map(|g| cumsum(g)).collect();
        // (per neighbouring pair: where along the curve the first gains on the second)
        let making: Vec<Vec<Vec<f64>>> = (0..n)
            .map(|t| {
                (0..n)
                    .map(|u| {
                        if t.abs_diff(u) == 1 && group[t] == group[u] {
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
            // (out of the area, as the lanes left it: only back in, towards its edge)
            if zone[i].is_none() {
                return match nearest_edge(&cx, p[i], 4.0 * cx.far) {
                    Some(e) => {
                        let v = sub(e, p[i]);
                        let size = norm(v).max(1e-12);
                        scale(v, (prm.leap * step / size).min(1.0))
                    }
                    None => [0.0, 0.0],
                };
            }
            let mut m = add(scale(normal[i], push[i]), crowd[i]);
            // down the density's slope, the whole ribbon at once: into the holes
            if let Some(d) = &density {
                let down = -dot(d.slope(p[i]), normal[i]) * blur * blur;
                m = add(m, scale(normal[i], prm.fill * cool * down));
            }
            let into = dot(m, axis[i]);
            if into > 0.0 {
                m = sub(m, scale(axis[i], into));
            }
            // length steered (by the length each trace has run from the exit, at its place
            // along the curve), only where a lead is still being built up
            let (t, w) = (tr.net[i], at[i]);
            let mut grow: f64 = 0.0;
            for u in [t.wrapping_sub(1), t + 1] {
                if u >= n || cx.group[u] != cx.group[t] {
                    continue;
                }
                let lead = run[t][w] - run[u][w];
                let mut l = lead.signum() * (lead.abs() - prm.band * pitch).max(0.0);
                if l * making[t][u][w] <= 0.0 {
                    l = 0.0;
                }
                l /= prm.tune * pitch;
                let toward = scale(normal[i], sides[t][u]);
                let bump = dot(bend[i], toward) < 0.0; // (a bump towards the neighbour)
                                                       // (behind: its bumps towards the one ahead grown, after it, not those away)
                if bump || prm.share <= 0.0 {
                    grow = grow.max((-l).clamp(0.0, 1.0));
                }
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
        for f in [0.3, -0.32].repeat(prm.smooth) {
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
            status.apart = apart(&gained, cx.group);
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
        status.apart = apart(&gained, cx.group);
        progress(&status);
    }
    if prm.holes > 0.0 && prm.phases & 2 != 0 {
        tr = filled(tr, input, prm, &cx, progress);
    }
    if prm.phases & 4 == 0 {
        return tr.lines();
    }
    let tr = smoothed(tr, prm, &cx);
    matched(tr, &base, bins, prm, &cx, progress).lines()
}

/// The traces with the holes settling left (`holes`) filled where they can be: each hole in
/// turn, the traces round it (those nearest it, and their groups: the pairs) settled again
/// on their own in a box round it (`hole_margin` pitches wider), for `hole_steps` steps,
/// each trace's own room shared with its pair's (`share`), all else there held as laid. A
/// pair's U-turns into a hole grow one inside the other, the outer first: too slow to wait
/// for over the whole area, a few hundred vertices' work each here.
fn filled(
    tr: Traces,
    input: &Input,
    prm: &Params,
    cx: &Ctx,
    progress: &mut dyn FnMut(&Status),
) -> Traces {
    let found = holes(
        &tr,
        bounds(input.zones.iter().flatten().flatten()),
        cx,
        prm.holes,
    );
    let pitch = cx.pitch;
    let mut lines = tr.lines();
    let n = lines.len();
    let inside = |q: P, b: [f64; 4]| q[0] >= b[0] && q[1] >= b[1] && q[0] <= b[2] && q[1] <= b[3];
    let grow = |b: [f64; 4], m: f64| [b[0] - m, b[1] - m, b[2] + m, b[3] + m];
    let mut status = Status {
        phase: "fill",
        steps: found.len(),
        ..Default::default()
    };
    for (h, cells) in found.iter().enumerate() {
        if crate::cancelled() {
            break;
        }
        status.step = h;
        progress(&status);
        let hb = bounds(cells.iter());
        let centre = [(hb[0] + hb[2]) / 2.0, (hb[1] + hb[3]) / 2.0];
        let core = grow(hb, prm.hole_margin * pitch);
        // (what anything moving in the core looks at, held)
        let outer = grow(core, 2.0 * cx.far + pitch);
        // the traces round it: the one nearest each of its places (not filled since)
        let reach = (prm.holes + 2.0) * pitch;
        let pts: Vec<(P, usize)> = lines
            .iter()
            .enumerate()
            .flat_map(|(t, l)| {
                l.iter()
                    .filter(|q| inside(**q, grow(hb, reach)))
                    .map(move |q| (*q, t))
            })
            .collect();
        let mut free = vec![false; n];
        let mut open = false;
        for &c in cells {
            let best = pts
                .iter()
                .map(|&(q, t)| (dist(q, c), t))
                .fold((f64::MAX, NONE), |a, b| if b.0 < a.0 { b } else { a });
            if best.1 != NONE {
                free[best.1] = true;
                open |= best.0 > pitch;
            }
        }
        if !open {
            continue;
        }
        let free: Vec<bool> = (0..n)
            .map(|t| (0..n).any(|u| free[u] && cx.group[u] == cx.group[t]))
            .collect();
        // each trace's runs in the box: those of the traces round it that reach into the
        // core moved, the others held
        let mut pieces: Vec<(usize, usize, usize, bool)> = Vec::new(); // (trace, from, to, moved)
        for (t, l) in lines.iter().enumerate() {
            let mut k = 0;
            while k < l.len() {
                if !inside(l[k], outer) {
                    k += 1;
                    continue;
                }
                let a = k;
                while k < l.len() && inside(l[k], outer) {
                    k += 1;
                }
                if k - a >= 2 {
                    let moved = free[t] && l[a..k].iter().any(|&q| inside(q, core));
                    pieces.push((t, a, k, moved));
                }
            }
        }
        // the moved runs side by side as the traces are, a pair's in turn: from each run of
        // a group's first trace, the next trace's run nearest it, and so on
        let rep = |j: usize| {
            let (t, a, b, _) = pieces[j];
            lines[t][a..b]
                .iter()
                .copied()
                .fold((f64::MAX, centre), |m, q| {
                    let d = dist(q, centre);
                    if d < m.0 {
                        (d, q)
                    } else {
                        m
                    }
                })
                .1
        };
        let gap = |j: usize, q: P| {
            let (t, a, b, _) = pieces[j];
            lines[t][a..b]
                .iter()
                .map(|&r| dist(r, q))
                .fold(f64::MAX, f64::min)
        };
        let mut used = vec![false; pieces.len()];
        let mut chains: Vec<Vec<usize>> = Vec::new(); // (moved runs side by side, in turn)
        for j in 0..pieces.len() {
            let t = pieces[j].0;
            if used[j] || !pieces[j].3 || (t > 0 && cx.group[t - 1] == cx.group[t]) {
                continue;
            }
            used[j] = true;
            let mut chain = vec![j];
            let mut u = t + 1;
            while u < n && cx.group[u] == cx.group[t] {
                let q = rep(*chain.last().unwrap());
                let next = (0..pieces.len())
                    .filter(|&k| !used[k] && pieces[k].3 && pieces[k].0 == u)
                    .map(|k| (gap(k, q), k))
                    .fold((f64::MAX, NONE), |a, b| if b.0 < a.0 { b } else { a });
                if next.1 == NONE || next.0 > 2.0 * pitch {
                    break;
                }
                used[next.1] = true;
                chain.push(next.1);
                u += 1;
            }
            chains.push(chain);
        }
        // (a moved run alone: its own chain)
        for j in 0..pieces.len() {
            if pieces[j].3 && !used[j] {
                used[j] = true;
                chains.push(vec![j]);
            }
        }
        if chains.is_empty() {
            continue;
        }
        let held: Vec<Vec<P>> = (0..pieces.len())
            .filter(|&j| !pieces[j].3)
            .map(|j| {
                let (t, a, b, _) = pieces[j];
                lines[t][a..b].to_vec()
            })
            .collect();
        let run = |j: usize| {
            let (t, a, b, _) = pieces[j];
            lines[t][a..b].to_vec()
        };
        let edge: Vec<P> = input
            .edge
            .iter()
            .copied()
            .filter(|&q| inside(q, grow(outer, cx.far)))
            .collect();
        let local = |lines: Vec<Vec<P>>, moved: usize, groups: Vec<usize>, pitch: f64| Input {
            hold: (0..lines.len()).map(|k| k >= moved).collect(),
            lines,
            pitch,
            edge: edge.clone(),
            zones: input.zones.clone(),
            keep: input.keep.clone(),
            groups,
            core: Some(core),
            base: Vec::new(),
        };
        // (smoothed first, kept clear: a kinked run faces itself nearer than a pitch, and
        // may only move apart there)
        let even = |sub: Input, prm: &Params| -> Input {
            let only = Params {
                steps: 0,
                finish: prm.finish,
                match_steps: 0,
                holes: 0.0,
                phases: 5,
                ..prm.clone()
            };
            Input {
                lines: settle(&sub, &only, &mut |_| {}),
                ..sub
            }
        };
        // 1. each chain as one trace along its middle, as wide as its traces: into the hole
        // as one U-turn (its traces' U-turns one inside the other; settled apart, the outer
        // fills it alone), then its traces offset from it again
        let mut moved: Vec<Vec<Vec<P>>> = chains
            .iter()
            .map(|c| c.iter().map(|&j| run(j)).collect())
            .collect();
        let wide = chains.iter().map(|c| c.len()).max().unwrap_or(1);
        if wide > 1 {
            let mids: Vec<usize> = (0..chains.len()).filter(|&c| chains[c].len() > 1).collect();
            let mut ls: Vec<Vec<P>> = mids.iter().map(|&c| middle(&moved[c])).collect();
            let before = ls.clone();
            let k = ls.len();
            ls.extend(chains.iter().filter(|c| c.len() == 1).map(|c| run(c[0])));
            ls.extend(held.iter().cloned());
            let groups = (0..ls.len()).collect();
            let wp = wide as f64 * pitch;
            let one = Params {
                steps: prm.hole_steps,
                share: 0.0,
                steer: 0.0,
                ribbon: prm.hole_ribbon / wide as f64,
                holes: 0.0,
                match_steps: 0,
                phases: 5,
                ..prm.clone()
            };
            let sub = even(local(ls, k, groups, wp), &one);
            let out = settle(&sub, &one, &mut |_| {});
            for (m, &c) in mids.iter().enumerate() {
                let w = chains[c].len();
                let side = side_of(&before[m], &moved[c][0]);
                for (j, r) in moved[c].iter_mut().enumerate() {
                    let off = side * ((w - 1) as f64 / 2.0 - j as f64) * pitch;
                    *r = spliced(r, &offset(&out[m], off), core);
                }
            }
        }
        // 2. all the moved runs settled at the pitch, a chain's together (its room shared)
        let mut ls: Vec<Vec<P>> = Vec::new();
        let mut groups = Vec::new();
        for (c, rs) in moved.iter().enumerate() {
            for r in rs {
                ls.push(r.clone());
                groups.push(c);
            }
        }
        let k = ls.len();
        ls.extend(held.iter().cloned());
        groups.extend(chains.len()..chains.len() + held.len());
        let two = Params {
            steps: prm.hole_steps / 4,
            share: 1.0,
            steer: 0.0,
            ribbon: prm.hole_ribbon,
            holes: 0.0,
            finish: 0,
            match_steps: 0,
            phases: 5,
            ..prm.clone()
        };
        let sub = even(local(ls, k, groups, pitch), &two);
        // (the held runs as they are, not as settling resampled them: a resampled U-turn's
        // tip is cut a little, and what moved measured against that comes too near)
        let mut out = settle(&sub, &two, &mut |_| {});
        out.truncate(k);
        out.extend(held.iter().cloned());
        let out = pushed_apart(out, k, pitch, core);
        // 3. kept only if clear (else the hole stays as it was)
        if !clear(&out, k, pitch) {
            continue;
        }
        // (back in place, each trace's later runs first: its earlier ones' places unchanged)
        let mut back: Vec<(usize, usize, usize, Vec<P>)> = chains
            .iter()
            .flatten()
            .zip(out)
            .map(|(&j, l)| (pieces[j].0, pieces[j].1, pieces[j].2, l))
            .collect();
        back.sort_by_key(|b| (b.0, std::cmp::Reverse(b.1)));
        for (t, a, b, l) in back {
            lines[t].splice(a..b, l);
        }
        let moved = k;
        status.moved = moved;
        status.filled += 1;
    }
    status.step = found.len();
    progress(&status);
    Traces::new(&lines, None)
}

/// The holes left in `b` (each its places, on a grid half a pitch apart: inside the zones, not in
/// what is kept as laid, a pitch or more from the edge and further than a pitch from any
/// trace), those whose furthest place is more than `least` pitches from a trace.
fn holes(tr: &Traces, b: [f64; 4], cx: &Ctx, least: f64) -> Vec<Vec<P>> {
    let (pitch, h) = (cx.pitch, cx.pitch / 2.0);
    let nx = ((b[2] - b[0]) / h) as usize + 1;
    let ny = ((b[3] - b[1]) / h) as usize + 1;
    let at = |k: usize| [b[0] + (k % nx) as f64 * h, b[1] + (k / nx) as f64 * h];
    let verts = Grid::new(&tr.p, pitch, |_| true);
    let cap = (least + 1.0) * pitch;
    let d: Vec<f64> = pmap(nx * ny, |k| {
        let q = at(k);
        let mut m = cap;
        verts.within(q, pitch, |_, d2| m = m.min(d2.sqrt()));
        if m < pitch || cx.zones.of(q).is_none() || cx.keep.of(q).is_some() {
            return 0.0;
        }
        let mut edge = false;
        if cx.edges.any_around(q, pitch) {
            cx.edges.within(q, pitch, |_, _| edge = true);
        }
        if edge {
            return 0.0;
        }
        verts.within(q, cap, |_, d2| m = m.min(d2.sqrt()));
        m
    });
    let mut seen = vec![false; nx * ny];
    let mut out = Vec::new();
    for k0 in 0..nx * ny {
        if seen[k0] || d[k0] <= pitch {
            continue;
        }
        seen[k0] = true;
        let (mut stack, mut cells, mut peak) = (vec![k0], Vec::new(), 0.0f64);
        while let Some(k) = stack.pop() {
            cells.push(at(k));
            peak = peak.max(d[k]);
            let (i, j) = (k % nx, k / nx);
            for (di, dj) in [(-1i64, 0i64), (1, 0), (0, -1), (0, 1)] {
                let (a, c) = (i as i64 + di, j as i64 + dj);
                if a < 0 || c < 0 || a >= nx as i64 || c >= ny as i64 {
                    continue;
                }
                let kk = c as usize * nx + a as usize;
                if !seen[kk] && d[kk] > pitch {
                    seen[kk] = true;
                    stack.push(kk);
                }
            }
        }
        if peak > least * pitch {
            out.push(cells);
        }
    }
    out
}

/// The middle of some runs side by side (each resampled to as many points, by its share of
/// its length; their mean).
fn middle(runs: &[Vec<P>]) -> Vec<P> {
    let m = runs.iter().map(|r| r.len()).max().unwrap_or(2).max(2);
    let at = |r: &[P], f: f64| -> P {
        let mut arc = vec![0.0];
        for w in r.windows(2) {
            arc.push(arc.last().unwrap() + dist(w[0], w[1]));
        }
        let want = f * arc.last().unwrap();
        let k = arc.partition_point(|&a| a < want).clamp(1, r.len() - 1);
        let span = (arc[k] - arc[k - 1]).max(1e-12);
        add(
            r[k - 1],
            scale(sub(r[k], r[k - 1]), (want - arc[k - 1]) / span),
        )
    };
    (0..m)
        .map(|i| {
            let f = i as f64 / (m - 1) as f64;
            let sum = runs.iter().fold([0.0, 0.0], |s, r| add(s, at(r, f)));
            scale(sum, 1.0 / runs.len() as f64)
        })
        .collect()
}

/// On which side (along its normals: 1 left, -1 right) of `line` most of `other` runs.
fn side_of(line: &[P], other: &[P]) -> f64 {
    let normal = Traces::new(&[line.to_vec()], None).normals();
    let mut left = 0i64;
    for &q in other.iter().step_by((other.len() / 30).max(1)) {
        let (k, _) = line
            .iter()
            .enumerate()
            .map(|(k, &r)| (k, dist(r, q)))
            .fold((0, f64::MAX), |a, b| if b.1 < a.1 { b } else { a });
        left += if dot(sub(q, line[k]), normal[k]) > 0.0 {
            1
        } else {
            -1
        };
    }
    if left >= 0 {
        1.0
    } else {
        -1.0
    }
}

/// `line` moved `by` to its left, mitred: at a corner along the middle of its segments'
/// normals, as far as keeps each segment `by` off (at most twice).
fn offset(line: &[P], by: f64) -> Vec<P> {
    let left = |a: P, b: P| {
        let v = sub(b, a);
        let l = norm(v).max(1e-12);
        [-v[1] / l, v[0] / l]
    };
    let m = line.len();
    (0..m)
        .map(|i| {
            let n1 = if i > 0 {
                left(line[i - 1], line[i])
            } else {
                left(line[0], line[1])
            };
            let n2 = if i + 1 < m {
                left(line[i], line[i + 1])
            } else {
                n1
            };
            let mid = add(n1, n2);
            let l = norm(mid);
            if l < 1e-9 {
                return add(line[i], scale(n1, by));
            }
            let b = scale(mid, 1.0 / l);
            add(line[i], scale(b, by / dot(b, n1).max(0.5)))
        })
        .collect()
}

/// `old` with its part in box `b` (from its first point in it to its last) that of `new`.
fn spliced(old: &[P], new: &[P], b: [f64; 4]) -> Vec<P> {
    let inside = |q: &P| q[0] >= b[0] && q[1] >= b[1] && q[0] <= b[2] && q[1] <= b[3];
    let (Some(a0), Some(a1)) = (old.iter().position(inside), old.iter().rposition(inside)) else {
        return old.to_vec();
    };
    let (Some(b0), Some(b1)) = (new.iter().position(inside), new.iter().rposition(inside)) else {
        return old.to_vec();
    };
    let mut out = old[..a0].to_vec();
    out.extend_from_slice(&new[b0..=b1]);
    out.extend_from_slice(&old[a1 + 1..]);
    out
}

/// The first `moved` of `lines` pushed (where in box `b`, a few times) straight away from
/// copper nearer than a pitch, as far as it is too near: what an offset's corners and
/// settling's last steps leave a little too near.
fn pushed_apart(mut lines: Vec<Vec<P>>, moved: usize, pitch: f64, b: [f64; 4]) -> Vec<Vec<P>> {
    let inside = |q: P| q[0] >= b[0] && q[1] >= b[1] && q[0] <= b[2] && q[1] <= b[3];
    let need = 1.01 * pitch;
    for _ in 0..20 {
        let tr = Traces::new(&lines, None);
        let arc = tr.arc();
        let verts = Grid::new(&tr.p, pitch, |_| true);
        let can = |i: usize| {
            tr.net[i] < moved && tr.prev[i] != NONE && tr.next[i] != NONE && inside(tr.p[i])
        };
        // (each vertex near a segment of other copper, one of the two moved: the vertex, or
        // the segment's ends, pushed away from the other, all the way if it is held, else
        // half: it moves too)
        let found: Vec<Vec<(usize, P)>> = pmap(tr.len(), |i| {
            let mut out = Vec::new();
            verts.within(tr.p[i], need + pitch, |s, _| {
                let s1 = tr.next[s];
                if s1 == NONE || s == i || s1 == i || !(can(i) || can(s) || can(s1)) {
                    return;
                }
                let (c, t) = closest(tr.p[i], tr.p[s], tr.p[s1]);
                let v = sub(tr.p[i], c);
                let d = norm(v);
                if d >= need || d < 1e-12 {
                    return;
                }
                if tr.net[s] == tr.net[i]
                    && (arc[s] + t * (arc[s1] - arc[s]) - arc[i]).abs() <= 2.0 * need
                {
                    return;
                }
                let segment = can(s) || can(s1);
                let share = if can(i) && segment { 0.5 } else { 1.0 };
                let away = scale(v, share * (need - d) / d);
                if can(i) {
                    out.push((i, away));
                }
                for e in [s, s1] {
                    if can(e) {
                        out.push((e, scale(away, -1.0)));
                    }
                }
            });
            out
        });
        let mut push = vec![[0.0, 0.0]; tr.len()];
        for (i, m) in found.into_iter().flatten() {
            if norm(m) > norm(push[i]) {
                push[i] = m;
            }
        }
        if push.iter().all(|m| m[0] == 0.0 && m[1] == 0.0) {
            break;
        }
        for (i, m) in push.iter().enumerate() {
            let (t, k) = (tr.net[i], i - tr.first[tr.net[i]]);
            lines[t][k] = add(lines[t][k], *m);
        }
    }
    lines
}

/// Whether the first `moved` lines keep a pitch (but 1 %) from all other copper and from
/// themselves where they face themselves (as `keep_clear`), and cross none.
fn clear(lines: &[Vec<P>], moved: usize, pitch: f64) -> bool {
    let tr = Traces::new(lines, None);
    let arc = tr.arc();
    let longest = (0..tr.len())
        .filter(|&i| tr.next[i] != NONE)
        .map(|i| dist(tr.p[i], tr.p[tr.next[i]]))
        .fold(0.0, f64::max);
    let need = 0.99 * pitch;
    let segs = Grid::new(&tr.p, pitch, |i| tr.next[i] != NONE);
    // (each vertex against the segments near it, the one or the other moved)
    let bad = pmap(tr.len(), |q| {
        let mut bad = false;
        segs.within(tr.p[q], need + longest, |s, _| {
            let s1 = tr.next[s];
            if bad || s == q || s1 == q || (tr.net[q] >= moved && tr.net[s] >= moved) {
                return;
            }
            // (its segment on, across another not next to it)
            let q1 = tr.next[q];
            if q1 != NONE && s != q1 && crosses(tr.p[q], tr.p[q1], tr.p[s], tr.p[s1]) {
                bad = true;
                return;
            }
            let (c, t) = closest(tr.p[q], tr.p[s], tr.p[s1]);
            let v = sub(c, tr.p[q]);
            let d = norm(v);
            if d >= need {
                return;
            }
            // (its own: only much further along it than across, more than a U-turn as
            // tight as laid takes, half a pitch across)
            bad = tr.net[s] != tr.net[q] || {
                let sep = (arc[s] + t * (arc[s1] - arc[s]) - arc[q]).abs();
                sep > 2.0 * d.max(pitch)
            };
        });
        bad
    });
    !bad.iter().any(|&b| b)
}

/// The bounds (x0, y0, x1, y1) of some points.
fn bounds<'a>(ps: impl Iterator<Item = &'a P>) -> [f64; 4] {
    ps.fold([f64::MAX, f64::MAX, f64::MIN, f64::MIN], |b, q| {
        [
            b[0].min(q[0]),
            b[1].min(q[1]),
            b[2].max(q[0]),
            b[3].max(q[1]),
        ]
    })
}

/// The traces smoothed at the end (`finish` Taubin steps, each kept clear as settling's
/// moves): the jitter and the shortest bumps the steering left taken out, the bends
/// wider than a few vertices kept (as their coverage).
fn smoothed(mut tr: Traces, prm: &Params, cx: &Ctx) -> Traces {
    for _ in 0..prm.finish {
        if crate::cancelled() {
            break;
        }
        let (fixed, zone) = held(&tr, cx);
        let p = tr.p.clone();
        let mut new = p.clone();
        for f in [0.5, -0.53] {
            let lap: Vec<P> = (0..tr.len())
                .map(|i| {
                    let (a, b) = (tr.prev[i], tr.next[i]);
                    if a == NONE || b == NONE || fixed[i] {
                        return [0.0, 0.0];
                    }
                    sub(scale(add(new[a], new[b]), 0.5), new[i])
                })
                .collect();
            for i in 0..tr.len() {
                new[i] = add(new[i], scale(lap[i], f));
            }
        }
        for i in 0..tr.len() {
            if cx.zones.of(new[i]) != zone[i] {
                new[i] = p[i];
            }
        }
        (new, _) = keep_clear(&tr, &p, new, cx);
        tr.p = new;
        tr = tr.respaced(cx.step);
    }
    tr
}

/// The settled traces matched in length (`sfc._match`): where one runs (from the exit) more
/// than `match_band` pitches longer than the shortest, its bends there straightened by as much
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
        if crate::cancelled() {
            break;
        }
        let gained = minus(&tr.binned(bins), base);
        let excess = excess(&gained, prm.match_band * cx.pitch, cx.group);
        let most = excess.iter().flatten().fold(0.0, |a: f64, &b| a.max(b));
        status.step = it;
        status.vertices = tr.len();
        status.apart = apart(&gained, cx.group);
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
        let bend = tr.bends(prm.bend);
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
/// trace runs more than `band` longer than the shortest, taken out where it gains.
fn excess(gained: &[Vec<f64>], band: f64, group: &[usize]) -> Vec<Vec<f64>> {
    let n = gained.len();
    let bins = gained[0].len();
    let mut out = vec![vec![0.0; bins]; n];
    let mut run = vec![0.0; n];
    let mut taken = vec![0.0; n];
    let groups = group.iter().copied().max().map_or(0, |g| g + 1);
    for b in 0..bins {
        for t in 0..n {
            run[t] += gained[t][b];
        }
        let mut least = vec![f64::MAX; groups];
        for t in 0..n {
            least[group[t]] = least[group[t]].min(run[t] - taken[t]);
        }
        for t in 0..n {
            let over = (run[t] - taken[t] - (least[group[t]] + band)).max(0.0);
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
    let mut fixed: Vec<bool> = pmap(tr.len(), |i| {
        let q = tr.p[i];
        tr.prev[i] == NONE
            || tr.next[i] == NONE
            || cx.hold.get(tr.net[i]).copied().unwrap_or(false)
            || cx
                .core
                .is_some_and(|b| q[0] < b[0] || q[1] < b[1] || q[0] > b[2] || q[1] > b[3])
            || cx.keep.of(q).is_some()
    });
    fixed = spread(tr, fixed, 4);
    let zone: Vec<Option<usize>> = pmap(tr.len(), |i| cx.zones.of(tr.p[i]));
    // (from one zone into another: not out of them all, as the leads leave through the exit)
    let join: Vec<bool> = (0..tr.len())
        .map(|i| {
            let j = tr.next[i];
            j != NONE && zone[i].is_some() && zone[j].is_some() && zone[i] != zone[j]
        })
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

/// The way out of copper nearer than a pitch to vertex `i` (other traces', or its own
/// across from it), as far as it is too near: none, mostly.
fn crowded(tr: &Traces, arc: &[f64], verts: &Grid, i: usize, cx: &Ctx) -> P {
    let need = 1.01 * cx.pitch;
    let q = tr.p[i];
    let mut out = [0.0, 0.0];
    verts.within(q, need + cx.step, |s, _| {
        let s1 = tr.next[s];
        if s1 == NONE {
            return;
        }
        let (c, t) = closest(q, tr.p[s], tr.p[s1]);
        let v = sub(q, c);
        let d = norm(v);
        if d >= need || d < 1e-12 {
            return;
        }
        if tr.net[s] == tr.net[i] && (arc[s] + t * (arc[s1] - arc[s]) - arc[i]).abs() <= 2.0 * need
        {
            return; // (its own copper, just along it)
        }
        let away = scale(v, (need - d) / 2.0 / d);
        if norm(away) > norm(out) {
            out = away;
        }
    });
    out
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
    across: [f64; 2],
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
            let own = |k: usize| {
                if tr.net[j] != t || across[k] <= 0.0 {
                    dd
                } else {
                    (dd - across[k] * cx.pitch).max(0.01 * cx.pitch)
                }
            };
            let a = dot(v, n);
            if a >= 0.7 * dd {
                side[0] = side[0].min(own(0));
            } else if -a >= 0.7 * dd {
                side[1] = side[1].min(own(1));
            }
        });
    };
    look(cx.near, &mut side);
    if side[0] >= cx.far || side[1] >= cx.far {
        // (further only where nothing that near; its own copper as far as it counts)
        look(cx.far + across[0].max(across[1]) * cx.pitch, &mut side);
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

/// The edge's point nearest `q` within `reach`, if any.
fn nearest_edge(cx: &Ctx, q: P, reach: f64) -> Option<P> {
    let mut best: Option<(f64, usize)> = None;
    cx.edges.within(q, reach, |e, d2| {
        if best.is_none_or(|b| d2 < b.0) {
            best = Some((d2, e));
        }
    });
    best.map(|(_, e)| cx.edge[e])
}

/// Rounds of taking back clashing moves at most.
const ROUNDS: usize = 100;

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
    let mut clear = false;
    // (once a call: where the vertices are as moved, the arc and normals there, and the
    // segments by their first vertex; a round only puts some back where they were, at
    // most `grow` off, so the grid is looked up that much further)
    let (arc, normal) = {
        let mut at = tr.clone();
        at.p = new.clone();
        (at.arc(), at.normals())
    };
    let longest = (0..len)
        .filter(|&i| tr.next[i] != NONE)
        .map(|i| dist(new[i], new[tr.next[i]]).max(dist(old[i], old[tr.next[i]])))
        .fold(0.0, f64::max);
    let reach = need + longest;
    let segs = Grid::new(&new, (reach + grow) / 2.0, |i| tr.next[i] != NONE);
    let mut seen = vec![usize::MAX; len]; // (the round a vertex was last taken in)
    for round in 0..ROUNDS {
        if check.is_empty() {
            break;
        }
        let moved = |i: usize| new[i] != old[i];
        // (the vertices that moved, and those that did not near them: two segments come
        // nearest at an end of one, maybe one that stayed, facing a segment that moved)
        let mut look: Vec<usize> = Vec::new();
        for &q in &check {
            for i in [q] {
                if seen[i] != round {
                    seen[i] = round;
                    look.push(i);
                }
            }
            segs.within(new[q], reach + grow, |s, _| {
                for i in [s, tr.next[s]] {
                    if seen[i] != round {
                        seen[i] = round;
                        look.push(i);
                    }
                }
            });
        }
        let found: Vec<(Vec<usize>, usize)> = pmap(look.len(), |k| {
            let q = look[k];
            let tangent = [normal[q][1], -normal[q][0]];
            let (mut bad, mut count) = (Vec::new(), 0);
            segs.within(new[q], reach + grow, |s, _| {
                if !bad.is_empty() {
                    return;
                }
                let s1 = tr.next[s];
                if !(moved(q) || moved(s) || moved(s1)) {
                    return;
                }
                count += 1;
                let (c, t) = closest(new[q], new[s], new[s1]);
                let v = sub(c, new[q]);
                let d = norm(v);
                // (too near already, as laid: it may only get further)
                if d >= need || d >= dist(closest(old[q], old[s], old[s1]).0, old[q]) {
                    return;
                }
                let clash = tr.net[s] != tr.net[q] || {
                    let sep = (arc[s] + t * (arc[s1] - arc[s]) - arc[q]).abs();
                    sep > cx.own && (dot(v, tangent).abs() < 0.5 * d.max(1e-12) || sep > 2.0 * d)
                };
                if clash {
                    // (back: whichever of the two moved)
                    bad.extend([q, s, s1].into_iter().filter(|&i| moved(i)));
                }
            });
            // the edge (the area's, the zones' borders): no nearer than half a pitch, so
            // that copper on the far side of a fold need never be looked at (as a panel's
            // worker cannot); a vertex already nearer may only move away
            let half = cx.pitch / 2.0;
            // (one out of the area: never further out)
            if bad.is_empty() && moved(q) && cx.zones.of(old[q]).is_none() {
                let far = 4.0 * cx.far;
                let gap = |at: P| nearest_edge(cx, at, far).map_or(far, |e| dist(e, at));
                if gap(new[q]) > gap(old[q]) + 1e-9 {
                    bad.push(q);
                }
            }
            if bad.is_empty() && moved(q) && cx.edges.any_around(new[q], half) {
                let near = |at: P| {
                    let mut d = f64::MAX;
                    cx.edges.within(at, half, |_, d2| d = d.min(d2.sqrt()));
                    d
                };
                let now = near(new[q]);
                if now < half && now < near(old[q]) {
                    bad.push(q);
                }
            }
            (bad, count)
        });
        measured += found.iter().map(|f| f.1).sum::<usize>();
        let mut back: Vec<usize> = found.into_iter().flat_map(|f| f.0).collect();
        // segments that cross (not merely sharing an end with their neighbours)
        let mut touched: Vec<usize> = check
            .iter()
            .flat_map(|&q| [q, tr.prev[q]])
            .filter(|&s| s != NONE && tr.next[s] != NONE)
            .collect();
        touched.sort_unstable();
        touched.dedup();
        let crossed: Vec<Vec<usize>> = pmap(touched.len(), |k| {
            let s = touched[k];
            let s1 = tr.next[s];
            let mut out = Vec::new();
            segs.within(new[s], dist(new[s], new[s1]) + longest + grow, |h, _| {
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
            clear = true;
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
            segs.within(old[b], reach + 2.0 * grow, |s, _| {
                next.push(s);
                next.push(tr.next[s]);
            });
        }
        next.sort_unstable();
        next.dedup();
        check = next.into_iter().filter(|&i| new[i] != old[i]).collect();
    }
    // (each round takes back the moves that clash, which may leave others clashing: a
    // step with many moves takes a few dozen rounds; one that does not settle in time is
    // not taken at all)
    if !clear && !check.is_empty() {
        return (old.to_vec(), measured);
    }
    (new, measured)
}

/// For each two neighbouring traces: on which side of the first (along its normals: 1 left,
/// -1 right) the second runs.
fn neighbour_sides(tr: &Traces, group: &[usize]) -> Vec<Vec<f64>> {
    let n = tr.traces();
    let normal = tr.normals();
    let mut out = vec![vec![0.0; n]; n];
    for t in 0..n.saturating_sub(1) {
        if group[t] != group[t + 1] {
            continue;
        }
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

fn apart(gained: &[Vec<f64>], group: &[usize]) -> Vec<f64> {
    let run: Vec<Vec<f64>> = gained.iter().map(|g| cumsum(g)).collect();
    (0..run.len().saturating_sub(1))
        .map(|t| {
            if group[t] != group[t + 1] {
                return 0.0;
            }
            run[t]
                .iter()
                .zip(&run[t + 1])
                .map(|(a, b)| (a - b).abs())
                .fold(0.0, f64::max)
        })
        .collect()
}
