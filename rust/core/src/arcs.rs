//! A polyline drawn again in lines and circular arcs: each run of its vertices that a line or
//! an arc follows within a tolerance (its vertices and the middles of its segments) taken
//! in one, the longest from each start (greedy). The ends of each piece are the polyline's
//! own vertices; an arc's middle is the point halfway along it. The tolerance may differ
//! from vertex to vertex (`fit_all`: as much as the room to the copper beside allows).

use crate::geom::{add, closest, dist, scale, P};
use crate::segs::Segs;

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

/// The run `p[i..=j]` and the middles of its segments, each with its tolerance (a middle's:
/// the less of its ends').
fn run<'a>(p: &'a [P], tol: &'a [f64], i: usize, j: usize) -> impl Iterator<Item = (P, f64)> + 'a {
    (i..=j).flat_map(move |k| {
        let mid = (k < j).then(|| (scale(add(p[k], p[k + 1]), 0.5), tol[k].min(tol[k + 1])));
        std::iter::once((p[k], tol[k])).chain(mid)
    })
}

fn line_fits(p: &[P], tol: &[f64], i: usize, j: usize) -> bool {
    run(p, tol, i, j).all(|(q, t)| dist(closest(q, p[i], p[j]).0, q) <= t)
}

/// The arc through `p[i]` and `p[j]` that the run follows within `tol` (its middle), if any:
/// every point within `tol` of it and on the way round from one end to the other (turning
/// one way, less than a full turn). Of the arcs through the two ends (one for each sagitta),
/// the one nearest the run at its worst: searched between the sagittas of the circles
/// through a few of its vertices (one vertex's wobble alone would miss it).
fn arc_fits(p: &[P], tol: &[f64], i: usize, j: usize) -> Option<P> {
    let (a, b) = (p[i], p[j]);
    let chord = dist(a, b);
    if chord < 1e-12 {
        return None;
    }
    let m = scale(add(a, b), 0.5);
    let n = [-(b[1] - a[1]) / chord, (b[0] - a[0]) / chord];
    let apex = |s: f64| add(m, scale(n, s));
    // (the worst share of its tolerance any point is off the arc by)
    let worst = |s: f64| -> f64 {
        match circle(a, apex(s), b) {
            Some((o, r)) => run(p, tol, i, j)
                .map(|(q, t)| (dist(q, o) - r).abs() / t)
                .fold(0.0, f64::max),
            None => f64::INFINITY,
        }
    };
    // (the sagittas of the circles through the ends and a few vertices between)
    let mut sags: Vec<f64> = Vec::new();
    let span = j - i;
    for k in 1..=5 {
        let v = i + (span * k) / 6;
        if v <= i || v >= j {
            continue;
        }
        if let Some((o, r)) = circle(a, p[v], b) {
            // (the apex on the side of the vertex)
            let side = (p[v][0] - m[0]) * n[0] + (p[v][1] - m[1]) * n[1];
            let h = (o[0] - m[0]) * n[0] + (o[1] - m[1]) * n[1];
            let s = if side >= 0.0 { h + r } else { h - r };
            if s.is_finite() {
                sags.push(s);
            }
        }
    }
    if sags.is_empty() {
        return None;
    }
    let (mut lo, mut hi) = sags
        .iter()
        .fold((f64::INFINITY, f64::NEG_INFINITY), |(l, h), &s| {
            (l.min(s), h.max(s))
        });
    let pad = 0.1 * (hi - lo) + tol[i].max(tol[j]);
    lo -= pad;
    hi += pad;
    // (golden-section search for the least worst deviation)
    let g = 0.5 * (5.0_f64.sqrt() - 1.0);
    let (mut x1, mut x2) = (hi - g * (hi - lo), lo + g * (hi - lo));
    let (mut f1, mut f2) = (worst(x1), worst(x2));
    for _ in 0..40 {
        if f1 <= f2 {
            hi = x2;
            x2 = x1;
            f2 = f1;
            x1 = hi - g * (hi - lo);
            f1 = worst(x1);
        } else {
            lo = x1;
            x1 = x2;
            f1 = f2;
            x2 = lo + g * (hi - lo);
            f2 = worst(x2);
        }
    }
    let s = if f1 <= f2 { x1 } else { x2 };
    if s.abs() < 1e-12 || worst(s) > 1.0 {
        return None;
    }
    let mid = apex(s);
    let (o, _) = circle(a, mid, b)?;
    let angle = |q: P| (q[1] - o[1]).atan2(q[0] - o[0]);
    // (round the way through the apex, one way, less than a full turn)
    let mut prev = angle(a);
    let mut sweep = 0.0;
    let mut sense = 0.0;
    for (q, _) in run(p, tol, i, j).skip(1) {
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
    Some(mid)
}

/// The most vertices one piece takes (each check runs over them all: this keeps the fit
/// linear in the polyline; a longer straight or round stretch is just more pieces).
const SPAN: usize = 64;

/// The polyline as lines and arcs within `tol` of it.
pub fn fit(p: &[P], tol: f64) -> Vec<Piece> {
    fit_within(p, &vec![tol; p.len()])
}

/// The polyline as lines and arcs within `tol[k]` of it at its vertex k (and the less of
/// its ends' at a segment's middle).
pub fn fit_within(p: &[P], tol: &[f64]) -> Vec<Piece> {
    let n = p.len();
    let mut out = Vec::new();
    if n < 2 {
        return out;
    }
    let piece = |i: usize, j: usize| -> Option<Piece> {
        if line_fits(p, tol, i, j) {
            return Some(Piece::Line(p[i], p[j]));
        }
        if j - i >= 2 {
            return arc_fits(p, tol, i, j).map(|m| Piece::Arc(p[i], m, p[j]));
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

/// Each of `lines` (a mesh's traces, all of them) as lines and arcs: within `tol` of it
/// everywhere, and further where it has room, up to `most`: half of how much further than
/// `pitch` the nearest copper beside it is (another trace, or the same one more than a
/// pitch and a fifth along it, as round a U-turn: either may move towards the other), and
/// all of how much further than half a pitch the area's edge (`edges`, closed rings) is.
pub fn fit_all(
    lines: &[Vec<P>],
    edges: &[Vec<P>],
    tol: f64,
    pitch: f64,
    most: f64,
) -> Vec<Vec<Piece>> {
    if pitch <= 0.0 || most <= tol {
        return lines.iter().map(|l| fit(l, tol)).collect();
    }
    // (every segment, with its line (none: an edge's) and where along that it lies)
    let reach = pitch + 2.0 * most;
    let (mut a, mut b, mut owner) = (Vec::new(), Vec::new(), Vec::new());
    for (li, line) in lines.iter().enumerate() {
        let mut s = 0.0;
        for w in line.windows(2) {
            let l = dist(w[0], w[1]);
            a.push(w[0]);
            b.push(w[1]);
            owner.push((Some(li), s, s + l));
            s += l;
        }
    }
    for ring in edges {
        for k in 0..ring.len() {
            a.push(ring[k]);
            b.push(ring[(k + 1) % ring.len()]);
            owner.push((None, 0.0, 0.0));
        }
    }
    let segs = Segs::new(a, b, reach);
    let own = 1.2 * pitch;
    lines
        .iter()
        .enumerate()
        .map(|(li, line)| {
            let mut s = 0.0;
            let tols: Vec<f64> = line
                .iter()
                .enumerate()
                .map(|(k, &q)| {
                    if k > 0 {
                        s += dist(line[k - 1], q);
                    }
                    let mut room = most;
                    let lo = [q[0] - reach, q[1] - reach];
                    let hi = [q[0] + reach, q[1] + reach];
                    segs.around(lo, hi, |i| {
                        let (o, s0, s1) = owner[i];
                        let d = dist(closest(q, segs.a[i], segs.b[i]).0, q);
                        let r = match o {
                            None => d - pitch / 2.0,
                            // (the trace itself, here: its own curve, not copper beside it)
                            Some(oi) if oi == li && s0 - own < s && s < s1 + own => return,
                            Some(_) => (d - pitch) / 2.0,
                        };
                        room = room.min(r);
                    });
                    room.max(tol)
                })
                .collect();
            fit_within(line, &tols)
        })
        .collect()
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
