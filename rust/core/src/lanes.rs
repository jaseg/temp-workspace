//! The traces round the curve (`sfc._lanes`): offsets of it at a pitch that shares the
//! spacing to the next run on each side evenly (the area's edge counts as a run's middle),
//! never below the least (with a margin, but exactly on the tongue's legs), in bends only as
//! far as keeps neighbouring traces' skew down (`_balance`); offset from a fine spline
//! through the curve, small loops in tight bends cut out (`_unloop`).

use crate::closed::{at, normals, radius, spline};
use crate::curve::neighbours;
use crate::geom::{add, dist, dot, scale, sub, P};
use crate::par::pmap;
use crate::segs::Segs;

/// `sfc.py`'s constants for the lanes, by its names.
#[derive(Clone, Debug)]
pub struct LaneParams {
    pub spread: f64,   // SPREAD
    pub smooth: usize, // SMOOTH
    pub fine: usize,   // FINE
    pub ramp: f64,     // RAMP
    pub margin: f64,   // MARGIN
    pub inside: f64,   // INSIDE
    pub window: f64,   // WINDOW
    pub straight: f64, // STRAIGHT
}

impl Default for LaneParams {
    fn default() -> LaneParams {
        LaneParams {
            spread: 1.3,
            smooth: 10,
            fine: 4,
            ramp: 3.0,
            margin: 0.02,
            inside: 0.9,
            window: 1.5,
            straight: 0.1,
        }
    }
}

/// The `n` traces round the closed curve `p` (vertices `k` on: the tongue's) as closed
/// polylines; `edge` the area's edge in short segments (each `[a, b]`), `exact` the
/// vertices on the tongue's legs.
#[allow(clippy::too_many_arguments)]
pub fn lanes(
    p: &[P],
    k: usize,
    edge: &[[P; 2]],
    n: usize,
    pitch: f64,
    spacing: f64,
    exact: &[bool],
    prm: &LaneParams,
) -> Vec<Vec<P>> {
    let m = p.len();
    let least = n as f64 * pitch;
    let cap = prm.spread * spacing;
    let normal = normals(p, 2); // (a smooth normal)
    let segs = Segs::new(
        edge.iter().map(|e| e[0]).collect(),
        edge.iter().map(|e| e[1]).collect(),
        cap / 2.0,
    );
    let rad = radius(p, 2);
    // the least pitch: with the margin, but on the tongue's legs, ramped in off them
    let idx: Vec<usize> = (0..m).filter(|&i| exact[i]).collect();
    let floor: Vec<f64> = (0..m)
        .map(|i| {
            let off = if exact[i] || idx.is_empty() {
                0.0
            } else {
                [idx[0], idx[idx.len() - 1]]
                    .iter()
                    .map(|&j| {
                        let g = i.abs_diff(j);
                        g.min(m - g) as f64
                    })
                    .fold(f64::MAX, f64::min)
            };
            least * (1.0 + prm.margin * (off / prm.ramp).clamp(0.0, 1.0))
        })
        .collect();
    let all: Vec<usize> = (0..m).collect();
    let mut sides = Vec::new();
    for side in [1i32, -1] {
        let near = neighbours(p, prm.window * least, cap, side, &all);
        let s = side as f64;
        let mut d: Vec<f64> = pmap(m, |i| {
            let mut d = near[i].map_or(cap, |x| x.0.min(cap));
            if let Some((t, _)) = segs.cast(p[i], scale(normal[i], s), cap / 2.0) {
                d = d.min(2.0 * t);
            }
            // inside a bend: the innermost trace within its radius
            if s * rad[i] > 0.0 {
                d = d.min(prm.inside * rad[i].abs() * 2.0 * n as f64 / (n.max(2) - 1) as f64);
            }
            if exact[i] {
                d = least;
            }
            d
        });
        // smoothed: a running minimum, then a running mean (never above d)
        let w = prm.smooth as isize;
        let mn: Vec<f64> = (0..m)
            .map(|i| {
                (-w..=w)
                    .map(|o| d[at(m, i as isize + o)])
                    .fold(f64::MAX, f64::min)
            })
            .collect();
        d = (0..m)
            .map(|i| {
                let mean =
                    (-w..=w).map(|o| mn[at(m, i as isize + o)]).sum::<f64>() / (2 * w + 1) as f64;
                mean.max(floor[i])
            })
            .collect();
        let lo: Vec<f64> = floor.iter().map(|f| f / n as f64).collect();
        let hi: Vec<f64> = d.iter().map(|x| x / n as f64).collect();
        sides.push(balance(&lo, &hi, p, &rad, k, least, prm));
    }
    let f = prm.fine;
    let fine = spline(p, f);
    let fl = fine.len();
    let fnormal = normals(&fine, 1);
    pmap(n, |j| {
        let o = j as f64 - (n as f64 - 1.0) / 2.0;
        let side = if o > 0.0 { &sides[0] } else { &sides[1] };
        let lane: Vec<P> = (0..fl)
            .map(|i| {
                let (lo, t) = (i / f % m, (i % f) as f64 / f as f64);
                let hi = (lo + 1) % m;
                let w = (side[lo] * (1.0 - t) + side[hi] * t) * o;
                add(fine[i], scale(fnormal[i], w))
            })
            .collect();
        // inside a bend tighter than the offset, the offset runs backwards: not those
        let tangent: Vec<P> = fnormal.iter().map(|q| [q[1], -q[0]]).collect();
        let fwd: Vec<bool> = (0..fl)
            .map(|i| dot(sub(lane[(i + 1) % fl], lane[i]), tangent[i]) > 0.0)
            .collect();
        let kept: Vec<P> = (0..fl)
            .filter(|&i| fwd[i] && fwd[at(fl, i as isize - 1)])
            .map(|i| lane[i])
            .collect();
        unloop(kept, 40)
    })
}

/// The pitch of one side's traces along the closed curve: up to `hi` (to share the room),
/// down to `lo` (the least) where that would skew them (see `sfc._balance`).
fn balance(
    lo: &[f64],
    hi: &[f64],
    p: &[P],
    rad: &[f64],
    k: usize,
    least: f64,
    prm: &LaneParams,
) -> Vec<f64> {
    let m = p.len();
    let mut out = lo.to_vec();
    let (mut skew, mut u) = (0.0, 0.0);
    let ease = 2.0 / (prm.smooth as f64 + 1.0);
    let straight = prm.straight / least;
    for o in 0..m {
        let i = (k + o) % m;
        let c = 1.0 / rad[i];
        let want = if c.abs() < straight || skew * c <= 0.0 {
            1.0
        } else {
            0.0
        };
        u += ease * (want - u);
        out[i] = lo[i] + u * (hi[i] - lo[i]);
        skew += out[i] * c * dist(p[(i + 1) % m], p[i]);
    }
    out
}

/// The closed polyline without the small loops an offset leaves inside tight bends: where
/// a segment crosses one up to `reach` segments on, the vertices between give way to the
/// crossing.
fn unloop(mut q: Vec<P>, reach: usize) -> Vec<P> {
    for _ in 0..4 {
        let n = q.len();
        if n < 4 {
            return q;
        }
        let mut hits: Vec<(usize, usize, P)> = Vec::new();
        for i in 0..n {
            let (a, r) = (q[i], sub(q[(i + 1) % n], q[i]));
            for j in 2..=reach.min(n - 1) {
                let c = q[(i + j) % n];
                let s = sub(q[(i + j + 1) % n], c);
                let den = r[0] * s[1] - r[1] * s[0];
                if den.abs() <= 1e-15 {
                    continue;
                }
                let w = sub(c, a);
                let t = (w[0] * s[1] - w[1] * s[0]) / den;
                let u = (w[0] * r[1] - w[1] * r[0]) / den;
                if t > 0.0 && t < 1.0 && u > 0.0 && u < 1.0 {
                    hits.push((i, j, add(a, scale(r, t))));
                }
            }
        }
        if hits.is_empty() {
            return q;
        }
        let mut keep = vec![true; n];
        hits.sort_by(|x, y| x.0.cmp(&y.0).then(y.1.cmp(&x.1)));
        let mut done: isize = -1;
        for (i, j, x) in hits {
            let span: Vec<usize> = (1..=j).map(|m| (i + m) % n).collect();
            if (i as isize) <= done || !keep[i] || !span.iter().all(|&v| keep[v]) {
                continue;
            }
            q[span[0]] = x;
            for &v in &span[1..] {
                keep[v] = false;
            }
            done = (i + j) as isize;
        }
        q = (0..n).filter(|&v| keep[v]).map(|v| q[v]).collect();
    }
    q
}
