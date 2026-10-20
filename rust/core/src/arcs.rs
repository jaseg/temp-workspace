//! A polyline drawn again in lines and circular arcs: each run of its vertices that a line or
//! an arc follows within a tolerance (its vertices and the middles of its segments) taken
//! in one, the longest from each start (greedy). The ends of each piece are the polyline's
//! own vertices; an arc's middle is the point halfway along it.

use crate::geom::{add, closest, dist, scale, P};

/// A piece: a line from its start to its end, or an arc through its middle.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Piece {
    Line(P, P),
    Arc(P, P, P),
}

/// The circle through three points (its centre and radius), if they are not in a line.
fn circle(a: P, b: P, c: P) -> Option<(P, f64)> {
    let d = 2.0 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]));
    if d.abs() < 1e-12 {
        return None;
    }
    let (a2, b2, c2) = (
        a[0] * a[0] + a[1] * a[1],
        b[0] * b[0] + b[1] * b[1],
        c[0] * c[0] + c[1] * c[1],
    );
    let o = [
        (a2 * (b[1] - c[1]) + b2 * (c[1] - a[1]) + c2 * (a[1] - b[1])) / d,
        (a2 * (c[0] - b[0]) + b2 * (a[0] - c[0]) + c2 * (b[0] - a[0])) / d,
    ];
    Some((o, dist(o, a)))
}

/// The run `p[i..=j]` and the middles of its segments.
fn run(p: &[P], i: usize, j: usize) -> impl Iterator<Item = P> + '_ {
    (i..=j).flat_map(move |k| {
        let mid = (k < j).then(|| scale(add(p[k], p[k + 1]), 0.5));
        std::iter::once(p[k]).chain(mid)
    })
}

fn line_fits(p: &[P], i: usize, j: usize, tol: f64) -> bool {
    run(p, i, j).all(|q| dist(closest(q, p[i], p[j]).0, q) <= tol)
}

/// The arc through `p[i]` and `p[j]` that the run follows within `tol` (its centre, radius,
/// and middle), if any: through the run's middle vertex, every point within `tol` of it and
/// on the way round from one end to the other (turning one way, less than a full turn).
fn arc_fits(p: &[P], i: usize, j: usize, tol: f64) -> Option<P> {
    let (o, r) = circle(p[i], p[(i + j) / 2], p[j])?;
    let angle = |q: P| (q[1] - o[1]).atan2(q[0] - o[0]);
    let mut prev = angle(p[i]);
    let mut sweep = 0.0;
    let mut sense = 0.0;
    for q in run(p, i, j).skip(1) {
        if (dist(q, o) - r).abs() > tol {
            return None;
        }
        let a = angle(q);
        let mut step = a - prev;
        if step > std::f64::consts::PI {
            step -= 2.0 * std::f64::consts::PI;
        } else if step < -std::f64::consts::PI {
            step += 2.0 * std::f64::consts::PI;
        }
        if sense == 0.0 {
            sense = step.signum();
        } else if step * sense < -1e-12 {
            return None; // (back the other way round)
        }
        sweep += step;
        prev = a;
    }
    if sweep.abs() >= 1.9 * std::f64::consts::PI {
        return None;
    }
    let half = angle(p[i]) + sweep / 2.0;
    Some([o[0] + r * half.cos(), o[1] + r * half.sin()])
}

/// The most vertices one piece takes (each check runs over them all: this keeps the fit
/// linear in the polyline; a longer straight or round stretch is just more pieces).
const SPAN: usize = 64;

/// The polyline as lines and arcs within `tol` of it.
pub fn fit(p: &[P], tol: f64) -> Vec<Piece> {
    let n = p.len();
    let mut out = Vec::new();
    if n < 2 {
        return out;
    }
    let piece = |i: usize, j: usize| -> Option<Piece> {
        if line_fits(p, i, j, tol) {
            return Some(Piece::Line(p[i], p[j]));
        }
        if j - i >= 2 {
            return arc_fits(p, i, j, tol).map(|m| Piece::Arc(p[i], m, p[j]));
        }
        None
    };
    let mut i = 0;
    while i + 1 < n {
        // (the furthest end that fits: doubling, then halving between the last that did
        // and the first that did not)
        let (mut good, mut bad) = (i + 1, None);
        let mut stride = 1;
        while bad.is_none() {
            let j = (i + 2 * stride).min(n - 1).min(i + SPAN);
            if j == good {
                break;
            }
            if piece(i, j).is_some() {
                good = j;
                stride *= 2;
                if j == n - 1 {
                    break;
                }
            } else {
                bad = Some(j);
            }
        }
        if let Some(mut hi) = bad {
            while hi - good > 1 {
                let mid = (good + hi) / 2;
                if piece(i, mid).is_some() {
                    good = mid;
                } else {
                    hi = mid;
                }
            }
        }
        out.push(piece(i, good).unwrap_or(Piece::Line(p[i], p[good])));
        i = good;
    }
    out
}

/// The pieces drawn as a polyline again (arcs every `step` along them at most), for
/// checking what is exported.
pub fn sample(pieces: &[Piece], step: f64) -> Vec<P> {
    let mut out: Vec<P> = Vec::new();
    for piece in pieces {
        match *piece {
            Piece::Line(a, b) => {
                if out.is_empty() {
                    out.push(a);
                }
                out.push(b);
            }
            Piece::Arc(a, m, b) => {
                if out.is_empty() {
                    out.push(a);
                }
                let (o, r) = circle(a, m, b).expect("an arc's points are not in a line");
                let ang = |q: P| (q[1] - o[1]).atan2(q[0] - o[0]);
                let (a0, am, a1) = (ang(a), ang(m), ang(b));
                // (the way round through the middle: anticlockwise if the middle comes
                // before the end that way)
                let tau = std::f64::consts::TAU;
                let wrap = |x: f64| x.rem_euclid(tau);
                let sweep = if wrap(am - a0) < wrap(a1 - a0) {
                    wrap(a1 - a0)
                } else {
                    wrap(a1 - a0) - tau
                };
                let k = ((r * sweep.abs() / step).ceil() as usize).max(1);
                for s in 1..k {
                    let t = a0 + sweep * s as f64 / k as f64;
                    out.push([o[0] + r * t.cos(), o[1] + r * t.sin()]);
                }
                out.push(b);
            }
        }
    }
    out
}
