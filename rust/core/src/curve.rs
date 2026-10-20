//! The space-filling curve's geometry (`sfc._relax`): relaxed towards an even spacing in
//! its zones (per-zone CVT steps against a grid of samples), grown into the room between
//! its runs, its runs pushed apart and its tight bends rounded; never crossing itself.

use std::collections::HashSet;

use crate::closed::{at, dilate, lap, normals, radius, respace, spline, split, taubin};
use crate::geom::{add, dist, dot, norm, resample, scale, sub, P};
use crate::grid::Grid;
use crate::par::pmap;
use crate::segs::crossing;
use crate::zones::Zones;

/// `sfc.py`'s constants for the curve's geometry, by its names.
#[derive(Clone, Debug)]
pub struct CurveParams {
    pub lloyd_curve: usize, // LLOYD_CURVE
    pub gain: f64,          // GAIN
    pub push_margin: f64,   // PUSH_MARGIN
    pub window: f64,        // WINDOW
    pub bend_slack: f64,    // BEND_SLACK
    pub grow: usize,        // GROW
    pub reach: f64,         // REACH
    pub grow_rate: f64,     // GROW_RATE
    pub hard: usize,        // HARD
    pub stall: usize,       // STALL
    pub repair: usize,      // REPAIR
    pub inside: f64,        // INSIDE
}

impl Default for CurveParams {
    fn default() -> CurveParams {
        CurveParams {
            lloyd_curve: 20,
            gain: 3.0,
            push_margin: 1.04,
            window: 1.5,
            bend_slack: 0.85,
            grow: 150,
            reach: 1.06,
            grow_rate: 0.5,
            hard: 10,
            stall: 10,
            repair: 100,
            inside: 0.9,
        }
    }
}

/// What to relax: the curve (open, from the stem's left end round to its right end), the
/// stem (which closes it), the regions (each its rings), the length to aim at (the
/// regions' area over the spacing), the area's edge and the borders between regions (points
/// along them), the spacing, the least spacing (`n` pitches), the pitch, and the samples'
/// offset (from the layout's random state).
pub struct CurveInput {
    pub curve: Vec<P>,
    pub stem: Vec<P>,
    pub regions: Vec<Vec<Vec<P>>>,
    pub target: f64,
    pub edge: Vec<P>,
    pub borders: Vec<P>,
    pub spacing: f64,
    pub least: f64,
    pub pitch: f64,
    pub offset: [f64; 2],
}

/// The curve relaxed, closed (the stem last), with the number of vertices before the
/// stem's. `progress(step, steps)` after each step.
pub fn relax(
    input: &CurveInput,
    prm: &CurveParams,
    progress: &mut dyn FnMut(usize, usize),
) -> (Vec<P>, usize) {
    let (spacing, least, pitch) = (input.spacing, input.least, input.pitch);
    let zones = Zones::new(&input.regions, spacing);
    let total = prm.lloyd_curve + prm.repair / 4;
    let stem_len: f64 = input.stem.windows(2).map(|w| dist(w[0], w[1])).sum();
    let mut step = spacing / 2.0;
    let mut free = split(&input.curve, step);
    let (samples, sreg) = samples(&input.regions, &zones, spacing / 3.0, input.offset);
    let mut inner: Vec<P> = input.stem[1..input.stem.len() - 1].to_vec();
    let n = (least / pitch).round();
    let bend = ((n - 1.0) / 2.0 * pitch / prm.inside).max(n * pitch / 2.0);
    for it in 0..prm.lloyd_curve {
        progress(it, total);
        let mut p = [free.clone(), inner.clone()].concat();
        let k = free.len();
        let old = p.clone();
        let reg: Vec<Option<usize>> = pmap(p.len(), |i| zones.of(p[i]));
        let cen = lloyd(&p, &reg, &samples, &sreg, spacing);
        p[1..k - 1].copy_from_slice(&cen[1..k - 1]);
        p = taubin(&p, k, 2);
        // (bends tighter than the traces can follow: smoothed while the length is held)
        let mut sharp = sharp_bends(&p, k, prm.bend_slack * bend);
        sharp[0] = false;
        let mut soft = dilate(&sharp, 1);
        soft[0] = false;
        soft[k - 1..].iter_mut().for_each(|s| *s = false);
        let l = lap(&p);
        for i in 0..p.len() {
            if soft[i] {
                p[i] = add(p[i], scale(l[i], 0.5));
            }
        }
        let length: f64 = p[..k].windows(2).map(|w| dist(w[0], w[1])).sum::<f64>() + stem_len;
        let lam = (prm.gain * (length - input.target) / input.target).clamp(-0.2, 0.5);
        let l = lap(&p);
        let m = p.len();
        for i in 1..k - 1 {
            let mut s = [0.0, 0.0];
            for d in -2..=2isize {
                s = add(s, l[at(m, i as isize + d)]);
            }
            p[i] = add(p[i], scale(s, lam / 5.0));
        }
        cap_moves(&old, &mut p, step / 2.0);
        keep_in(&zones, &old, &mut p);
        free = within(&zones, even(&untangle(&old, &p), k, step, false));
    }

    step = spacing / 4.0;
    let ends = [
        &[*free.last().unwrap()][..],
        &input.stem[1..input.stem.len() - 1],
        &[free[0]],
    ]
    .concat();
    let r = resample(&ends, step);
    inner = r[1..r.len() - 1].to_vec();
    free = within(
        &zones,
        even(
            &[free.clone(), inner.clone()].concat(),
            free.len(),
            step,
            true,
        ),
    );
    let want = prm.push_margin * least;
    let window = prm.window * least;
    // The edge the curve keeps off by half a spacing: the area's, and the zones' borders but
    // where the curve crosses them (where it joins the zones).
    let closed = [free.clone(), inner.clone()].concat();
    let reg: Vec<Option<usize>> = pmap(closed.len(), |i| zones.of(closed[i]));
    let xs: Vec<P> = (0..closed.len())
        .filter(|&i| reg[i] != reg[(i + 1) % closed.len()])
        .map(|i| scale(add(closed[i], closed[(i + 1) % closed.len()]), 0.5))
        .collect();
    let xgrid = Grid::new(&xs, 1.5 * spacing, |_| true);
    let mut edge = input.edge.clone();
    edge.extend(input.borders.iter().filter(|&&b| {
        let mut near = false;
        xgrid.within(b, 1.5 * spacing, |_, _| near = true);
        !near
    }));
    let edges = Grid::new(&edge, want, |_| true);
    let (mut p, mut k) = grow(
        [free.clone(), inner.clone()].concat(),
        free.len(),
        step,
        least,
        input.target - stem_len,
        &edge,
        &edges,
        bend,
        &zones,
        prm,
    );
    let mut hot: Option<HashSet<(i64, i64)>> = None;
    for it in 0..prm.repair {
        progress(prm.lloyd_curve + it.min(prm.repair / 4), total);
        let free = within(&zones, respace(&p[..k], step));
        p = [free.clone(), inner.clone()].concat();
        k = free.len();
        let which: Vec<usize> = match &hot {
            None => (0..k).collect(),
            Some(h) => (0..k).filter(|&i| h.contains(&cell(p[i], want))).collect(),
        };
        let near = neighbours(&p, window, want, 0, &which);
        let de: Vec<Option<(f64, usize)>> =
            pmap(which.len(), |j| nearest_edge(&edges, p[which[j]], want));
        let mut sharp = sharp_bends(&p, k, prm.bend_slack * bend);
        sharp[0] = false;
        let mut hit = false;
        let mut mv = vec![[0.0, 0.0]; p.len()];
        for (j, &w) in which.iter().enumerate() {
            if w == 0 || w + 1 >= k {
                continue; // (the stem's ends stay)
            }
            // (the edge stands for a run's middle: twice the distance to it counts)
            let mut push = |other: P, d: f64| {
                let away = sub(p[w], other);
                let away = scale(away, 1.0 / norm(away).max(1e-12));
                mv[w] = add(mv[w], scale(away, 0.6 * (want - d) + step / 8.0));
                hit = true;
            };
            if let Some((d, o)) = near[j] {
                if d < want {
                    push(p[o], d);
                }
            }
            if let Some((d, e)) = de[j] {
                if 2.0 * d < want {
                    push(edge[e], 2.0 * d);
                }
            }
        }
        if !hit && !sharp.iter().any(|&s| s) {
            break;
        }
        let m = p.len();
        let mut mv: Vec<P> = (0..m)
            .map(|i| {
                let s = add(
                    add(mv[at(m, i as isize - 1)], scale(mv[i], 2.0)),
                    mv[(i + 1) % m],
                );
                scale(s, 0.25)
            })
            .collect();
        let soft = soften(&p, k, &sharp, it >= prm.hard);
        for i in 0..m {
            mv[i] = add(mv[i], soft[i]);
        }
        openings(&p, k, &mut mv);
        let moved: Vec<bool> = mv.iter().map(|v| norm(*v) > 0.0).collect();
        let mut new: Vec<P> = (0..m).map(|i| add(p[i], mv[i])).collect();
        cap_moves(&p, &mut new, step / 2.0);
        keep_in(&zones, &p, &mut new);
        p = untangle(&p, &new);
        hot = Some(hot_cells((0..k).filter(|&i| moved[i]).map(|i| p[i]), want));
    }
    (p, k)
}

/// The closed curve grown into the room between its runs, as by differential growth (see
/// `sfc._grow`).
#[allow(clippy::too_many_arguments)]
fn grow(
    mut p: Vec<P>,
    mut k: usize,
    step: f64,
    least: f64,
    target: f64,
    edge: &[P],
    edges: &Grid,
    bend: f64,
    zones: &Zones,
    prm: &CurveParams,
) -> (Vec<P>, usize) {
    let reach = prm.reach * least;
    let look = reach + step;
    let window = prm.window * least;
    let want = prm.push_margin * least;
    let width = ((least / step / 2.0).round() as usize).max(1);
    let mut hot: Option<HashSet<(i64, i64)>> = None;
    let mut lengths: Vec<f64> = Vec::new();
    for _ in 0..prm.grow {
        let free = within(zones, respace(&p[..k], step));
        p = [free.clone(), p[k..].to_vec()].concat();
        k = free.len();
        let length: f64 = free.windows(2).map(|w| dist(w[0], w[1])).sum();
        lengths.push(length);
        let stalled =
            lengths.len() > prm.stall && length < lengths[lengths.len() - prm.stall - 1] * 1.002;
        if length >= target || stalled {
            break;
        }
        let which: Vec<usize> = match &hot {
            None => (0..k).collect(),
            Some(h) => (0..k).filter(|&i| h.contains(&cell(p[i], look))).collect(),
        };
        if which.is_empty() {
            break;
        }
        let m = p.len();
        let normal = normals(&p, 1);
        let left = neighbours(&p, window, look, 1, &which);
        let right = neighbours(&p, window, look, -1, &which);
        let l = lap(&p);
        let force: Vec<f64> = pmap(which.len(), |j| {
            let w = which[j];
            let mut lft = left[j].map_or(look, |x| x.0);
            let mut rgt = right[j].map_or(look, |x| x.0);
            if let Some((d, e)) = nearest_edge(edges, p[w], want) {
                if dot(sub(edge[e], p[w]), normal[w]) > 0.0 {
                    lft = lft.min(2.0 * d);
                } else {
                    rgt = rgt.min(2.0 * d);
                }
            }
            let mut f = ((reach - rgt).max(0.0) - (reach - lft).max(0.0)) / 2.0;
            if length < target {
                let mut out = [0.0, 0.0];
                for d in -2..=2isize {
                    out = sub(out, l[at(m, w as isize + d)]);
                }
                let way = dot(out, normal[w]).signum();
                let room = if way > 0.0 { lft } else { rgt } - reach;
                f += way * prm.grow_rate * room.clamp(0.0, step);
            }
            f
        });
        let mut push = vec![0.0; m];
        for (j, &w) in which.iter().enumerate() {
            push[w] = force[j];
        }
        let busy: Vec<bool> = push.iter().map(|f| f.abs() > 0.05 * step).collect();
        if !busy.iter().any(|&b| b) {
            break;
        }
        for _ in 0..2 {
            push = crate::closed::box_mean(&push, width, |s, d| s / d);
        }
        let smooth = taubin(&p, k, 1);
        let mut sharp = sharp_bends(&p, k, prm.bend_slack * bend);
        sharp[0] = false;
        let soft = soften(&p, k, &sharp, false);
        let mut mv: Vec<P> = (0..m)
            .map(|i| {
                add(
                    add(scale(normal[i], push[i]), sub(smooth[i], p[i])),
                    soft[i],
                )
            })
            .collect();
        openings(&p, k, &mut mv);
        let mut new: Vec<P> = (0..m).map(|i| add(p[i], mv[i])).collect();
        cap_moves(&p, &mut new, step / 2.0);
        keep_in(zones, &p, &mut new);
        p = untangle(&p, &new);
        hot = Some(hot_cells((0..k).filter(|&i| busy[i]).map(|i| p[i]), look));
    }
    (p, k)
}

/// For the vertices `which` of the closed curve: the nearest vertex more than `window`
/// away along it, within `reach` (on its left for `side` 1, right for -1, either for 0),
/// with the distance.
pub fn neighbours(
    p: &[P],
    window: f64,
    reach: f64,
    side: i32,
    which: &[usize],
) -> Vec<Option<(f64, usize)>> {
    let n = p.len();
    let (arc, total) = crate::closed::arcs(p);
    let grid = Grid::new(p, reach / 2.0, |_| true);
    pmap(which.len(), |j| {
        let i = which[j];
        let t = sub(p[(i + 1) % n], p[at(n, i as isize - 1)]);
        let normal = [-t[1], t[0]];
        let mut best: Option<(f64, usize)> = None;
        grid.within(p[i], reach, |o, d2| {
            let gap = (arc[i] - arc[o]).abs();
            if gap.min(total - gap) <= window {
                return;
            }
            if side != 0 && (side as f64) * dot(sub(p[o], p[i]), normal) <= 0.0 {
                return;
            }
            if best.is_none_or(|b| d2 < b.0 * b.0) {
                best = Some((d2.sqrt(), o));
            }
        });
        best
    })
}

fn nearest_edge(edges: &Grid, q: P, r: f64) -> Option<(f64, usize)> {
    let mut best: Option<(f64, usize)> = None;
    edges.within(q, r, |e, d2| {
        if best.is_none_or(|b| d2 < b.0 * b.0) {
            best = Some((d2.sqrt(), e));
        }
    });
    best
}

/// Each vertex's centroid of the samples nearer to it than to any other vertex in its
/// region (the per-zone CVT): the vertex itself where none are.
fn lloyd(p: &[P], reg: &[Option<usize>], samples: &[P], sreg: &[usize], spacing: f64) -> Vec<P> {
    let r = 1.125 * spacing;
    let grid = Grid::new(p, r / 2.0, |_| true);
    let owner: Vec<Option<usize>> = pmap(samples.len(), |s| {
        let mut best: Option<(f64, usize)> = None;
        grid.within(samples[s], r, |i, d2| {
            if reg[i] == Some(sreg[s]) && best.is_none_or(|b| d2 < b.0) {
                best = Some((d2, i));
            }
        });
        best.map(|b| b.1)
    });
    let mut sums = vec![[0.0, 0.0]; p.len()];
    let mut count = vec![0usize; p.len()];
    for (s, o) in owner.iter().enumerate() {
        if let Some(i) = *o {
            sums[i] = add(sums[i], samples[s]);
            count[i] += 1;
        }
    }
    (0..p.len())
        .map(|i| {
            if count[i] > 0 {
                scale(sums[i], 1.0 / count[i] as f64)
            } else {
                p[i]
            }
        })
        .collect()
}

/// Points on a square grid (offset by `offset`) over the regions, with their region.
fn samples(
    regions: &[Vec<Vec<P>>],
    zones: &Zones,
    step: f64,
    offset: [f64; 2],
) -> (Vec<P>, Vec<usize>) {
    let mut pts = Vec::new();
    let mut reg = Vec::new();
    for (ri, rings) in regions.iter().enumerate() {
        let all = rings.iter().flatten();
        let (x0, x1) = all
            .clone()
            .fold((f64::MAX, f64::MIN), |(a, b), q| (a.min(q[0]), b.max(q[0])));
        let (y0, y1) = all.fold((f64::MAX, f64::MIN), |(a, b), q| (a.min(q[1]), b.max(q[1])));
        let nx = ((x1 + step - (x0 - offset[0])) / step).ceil() as usize;
        let ny = ((y1 + step - (y0 - offset[1])) / step).ceil() as usize;
        let cand: Vec<P> = (0..ny)
            .flat_map(|j| {
                (0..nx).map(move |i| {
                    [
                        x0 - offset[0] + i as f64 * step,
                        y0 - offset[1] + j as f64 * step,
                    ]
                })
            })
            .collect();
        let inside = pmap(cand.len(), |c| zones.of(cand[c]) == Some(ri));
        for (c, q) in cand.into_iter().enumerate() {
            if inside[c] {
                pts.push(q);
                reg.push(ri);
            }
        }
    }
    (pts, reg)
}

fn sharp_bends(p: &[P], k: usize, under: f64) -> Vec<bool> {
    let r = radius(p, 1);
    (0..p.len())
        .map(|i| i < k.saturating_sub(1) && r[i].abs() < under)
        .collect()
}

/// A move rounding the curve's `sharp` bends: Taubin's smoothing about them; `hard`: a
/// Laplacian step at them too.
fn soften(p: &[P], k: usize, sharp: &[bool], hard: bool) -> Vec<P> {
    let soft = dilate(sharp, 3);
    let t = taubin(p, k, 2);
    let mut out: Vec<P> = (0..p.len())
        .map(|i| if soft[i] { sub(t[i], p[i]) } else { [0.0, 0.0] })
        .collect();
    if hard {
        let near = dilate(sharp, 1);
        let l = lap(p);
        for i in 0..p.len() {
            if near[i] {
                out[i] = add(out[i], scale(l[i], 0.5));
            }
        }
    }
    out
}

/// Off the stem's openings: the curve on along their arcs' end for a while (`mv` amended;
/// the stem and its ends stay).
fn openings(p: &[P], k: usize, mv: &mut [P]) {
    let n = p.len();
    for (end, prev, sign) in [(0, n - 1, 1isize), (k - 1, k, -1isize)] {
        let t = sub(p[end], p[prev]);
        let t = scale(t, 1.0 / norm(t).max(1e-12));
        for m in 1..=3isize {
            let i = (end as isize + sign * m) as usize;
            let on = add(p[end], scale(t, dist(p[i], p[end])));
            let to = sub(on, p[i]);
            mv[i] = if m == 1 {
                to
            } else {
                add(mv[i], scale(to, 0.5 / m as f64))
            };
        }
    }
    mv[0] = [0.0, 0.0];
    mv[k - 1] = [0.0, 0.0];
    mv[k..].iter_mut().for_each(|v| *v = [0.0, 0.0]);
}

/// Each move of `new` from `old` shortened to `most`.
fn cap_moves(old: &[P], new: &mut [P], most: f64) {
    for i in 0..old.len() {
        let m = sub(new[i], old[i]);
        let s = norm(m);
        if s > most {
            new[i] = add(old[i], scale(m, most / s));
        }
    }
}

/// Each vertex of `new` that `old` had in a zone and the move takes out of them all back
/// where it was (the curve never leaves its area).
fn keep_in(zones: &Zones, old: &[P], new: &mut [P]) {
    let out: Vec<bool> = pmap(old.len(), |i| {
        new[i] != old[i] && zones.of(new[i]).is_none() && zones.of(old[i]).is_some()
    });
    for (i, &o) in out.iter().enumerate() {
        if o {
            new[i] = old[i];
        }
    }
}

/// The open curve without the vertices out of the zones (but its ends): resampled, a chord
/// across a corner of the edge puts them there, and pushed off the edge they would leave.
fn within(zones: &Zones, free: Vec<P>) -> Vec<P> {
    let k = free.len();
    let keep: Vec<bool> = pmap(k, |i| i == 0 || i + 1 == k || zones.of(free[i]).is_some());
    free.into_iter()
        .zip(keep)
        .filter_map(|(q, k)| k.then_some(q))
        .collect()
}

/// The closed curve `new` (`old` moved, `old` crossing nowhere) with the vertices of every
/// segment that would cross another back where they were.
pub fn untangle(old: &[P], new: &[P]) -> Vec<P> {
    let n = new.len();
    let mut new = new.to_vec();
    let mut moved: Vec<usize> = (0..n).filter(|&i| new[i] != old[i]).collect();
    for _ in 0..50 {
        if moved.is_empty() {
            return new;
        }
        let mut which: Vec<usize> = moved
            .iter()
            .flat_map(|&i| [i, at(n, i as isize - 1)])
            .collect();
        which.sort_unstable();
        which.dedup();
        let pairs = crossing(&new, &which);
        if pairs.is_empty() {
            return new;
        }
        let mut back: Vec<usize> = pairs
            .iter()
            .flat_map(|&(i, j)| [i, (i + 1) % n, j, (j + 1) % n])
            .collect();
        back.sort_unstable();
        back.dedup();
        for &b in &back {
            new[b] = old[b];
        }
        moved = back;
    }
    old.to_vec()
}

/// The closed curve's first `k` vertices (an open polyline) resampled at an even step
/// (`smooth`: along a spline through them), unless that would make it cross itself: then
/// only its long segments split.
fn even(p: &[P], k: usize, step: f64, smooth: bool) -> Vec<P> {
    let free = if smooth {
        let fine = spline(p, 4);
        resample(&fine[..4 * (k - 1) + 1], step)
    } else {
        resample(&p[..k], step)
    };
    let q = [free.clone(), p[k..].to_vec()].concat();
    let all: Vec<usize> = (0..q.len()).collect();
    if crossing(&q, &all).is_empty() {
        free
    } else {
        split(&p[..k], 1.5 * step)
    }
}

fn cell(q: P, size: f64) -> (i64, i64) {
    ((q[0] / size).floor() as i64, (q[1] / size).floor() as i64)
}

fn hot_cells(pts: impl Iterator<Item = P>, size: f64) -> HashSet<(i64, i64)> {
    let mut h = HashSet::new();
    for q in pts {
        let (a, b) = cell(q, size);
        for dx in -1..=1 {
            for dy in -1..=1 {
                h.insert((a + dx, b + dy));
            }
        }
    }
    h
}
