//! Polylines, closed and open, as `sfc.py` handles them (closed: index arithmetic wraps).

use crate::geom::{add, dist, norm, scale, sub, P};

#[inline]
pub fn at(n: usize, i: isize) -> usize {
    i.rem_euclid(n as isize) as usize
}

/// Each vertex's step to the middle of its neighbours (closed).
pub fn lap(p: &[P]) -> Vec<P> {
    let n = p.len();
    (0..n)
        .map(|i| {
            let (a, b) = (p[at(n, i as isize - 1)], p[at(n, i as isize + 1)]);
            sub(scale(add(a, b), 0.5), p[i])
        })
        .collect()
}

/// The mean of `v` over `-w..=w` places round each (closed).
pub fn box_mean<T: Copy + Default + std::ops::Add<Output = T>>(
    v: &[T],
    w: usize,
    div: impl Fn(T, f64) -> T,
) -> Vec<T> {
    let n = v.len();
    (0..n)
        .map(|i| {
            let mut s = T::default();
            for d in -(w as isize)..=(w as isize) {
                s = s + v[at(n, i as isize + d)];
            }
            div(s, (2 * w + 1) as f64)
        })
        .collect()
}

/// Taubin smoothing (a shrinking step, then an inflating one) of the closed curve's first
/// `k` vertices but the first and last: zigzags gone, the shape kept.
pub fn taubin(p: &[P], k: usize, passes: usize) -> Vec<P> {
    let mut p = p.to_vec();
    for _ in 0..passes {
        for f in [0.5, -0.53] {
            let d = lap(&p);
            for i in 1..k.saturating_sub(1) {
                p[i] = add(p[i], scale(d[i], f));
            }
        }
    }
    p
}

/// The closed curve's signed radius of curvature at each vertex (positive turning left),
/// from the turn between the chords `reach` vertices either way.
pub fn radius(p: &[P], reach: usize) -> Vec<f64> {
    let n = p.len();
    (0..n)
        .map(|i| {
            let a = sub(p[i], p[at(n, i as isize - reach as isize)]);
            let b = sub(p[at(n, (i + reach) as isize)], p[i]);
            let turn = (a[0] * b[1] - a[1] * b[0]).atan2(a[0] * b[0] + a[1] * b[1]);
            let chord = (norm(a) + norm(b)) / 2.0;
            chord / if turn.abs() < 1e-9 { 1e-9 } else { turn }
        })
        .collect()
}

/// Unit normals (to the left) from the chord between each vertex's neighbours `reach`
/// either way (closed).
pub fn normals(p: &[P], reach: usize) -> Vec<P> {
    let n = p.len();
    (0..n)
        .map(|i| {
            let t = sub(
                p[at(n, (i + reach) as isize)],
                p[at(n, i as isize - reach as isize)],
            );
            let l = norm(t).max(1e-12);
            [-t[1] / l, t[0] / l]
        })
        .collect()
}

/// Each vertex's length run along the closed curve, and the whole length.
pub fn arcs(p: &[P]) -> (Vec<f64>, f64) {
    let n = p.len();
    let mut out = Vec::with_capacity(n);
    let mut s = 0.0;
    for i in 0..n {
        out.push(s);
        s += dist(p[i], p[(i + 1) % n]);
    }
    (out, s)
}

/// The open polyline with its segments longer than `longest` split evenly.
pub fn split(p: &[P], longest: f64) -> Vec<P> {
    let mut out = Vec::with_capacity(p.len());
    for w in p.windows(2) {
        let parts = ((dist(w[0], w[1]) / longest).ceil() as usize).max(1);
        for j in 0..parts {
            out.push(add(w[0], scale(sub(w[1], w[0]), j as f64 / parts as f64)));
        }
    }
    if let Some(&q) = p.last() {
        out.push(q);
    }
    out
}

/// The open polyline at about `step` between vertices without moving any: vertices closer
/// to the next but one than `step` dropped (not two in a row; the ends kept), segments
/// longer than one and a half split.
pub fn respace(p: &[P], step: f64) -> Vec<P> {
    let m = p.len();
    let short: Vec<bool> = (0..m)
        .map(|k| k > 0 && k + 1 < m && dist(p[k - 1], p[k]) + dist(p[k], p[k + 1]) < step)
        .collect();
    let kept: Vec<P> = (0..m)
        .filter(|&k| !(short[k] && !(k > 0 && short[k - 1])))
        .map(|k| p[k])
        .collect();
    split(&kept, 1.5 * step)
}

/// The closed polyline through `p` as a centripetal Catmull-Rom spline, `m` vertices per
/// segment (the first of each at the segment's start).
pub fn spline(p: &[P], m: usize) -> Vec<P> {
    let n = p.len();
    let knot = |a: P, b: P| dist(a, b).max(1e-9).sqrt();
    let mut out = Vec::with_capacity(n * m);
    for i in 0..n {
        let (p0, p1) = (p[at(n, i as isize - 1)], p[i]);
        let (p2, p3) = (p[(i + 1) % n], p[(i + 2) % n]);
        let t1 = knot(p0, p1);
        let t2 = t1 + knot(p1, p2);
        let t3 = t2 + knot(p2, p3);
        let mix = |a: P, ta: f64, b: P, tb: f64, t: f64| {
            scale(add(scale(a, tb - t), scale(b, t - ta)), 1.0 / (tb - ta))
        };
        for j in 0..m {
            let t = t1 + (t2 - t1) * j as f64 / m as f64;
            let a1 = mix(p0, 0.0, p1, t1, t);
            let a2 = mix(p1, t1, p2, t2, t);
            let a3 = mix(p2, t2, p3, t3, t);
            let b1 = mix(a1, 0.0, a2, t2, t);
            let b2 = mix(a2, t1, a3, t3, t);
            out.push(mix(b1, t1, b2, t2, t));
        }
    }
    out
}

/// `mask` grown `w` places either way (closed).
pub fn dilate(mask: &[bool], w: usize) -> Vec<bool> {
    let n = mask.len();
    (0..n)
        .map(|i| (-(w as isize)..=(w as isize)).any(|d| mask[at(n, i as isize + d)]))
        .collect()
}
