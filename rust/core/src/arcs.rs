//! A polyline drawn again in lines and circular arcs: each run of its vertices that a line or
//! an arc follows within a tolerance (its vertices and the middles of its segments) taken
//! in one, the longest from each start (greedy). The ends of each piece are the polyline's
//! own vertices; an arc's middle is the point halfway along it. The tolerance may differ
//! from vertex to vertex (`fit_all`: as much as the room to the copper beside allows).

use crate::geom::{add, closest, dist, norm, scale, sub, P};
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
/// its ends' mean).
fn run<'a>(p: &'a [P], tol: &'a [f64], i: usize, j: usize) -> impl Iterator<Item = (P, f64)> + 'a {
    (i..=j).flat_map(move |k| {
        let mid = (k < j).then(|| (scale(add(p[k], p[k + 1]), 0.5), 0.5 * (tol[k] + tol[k + 1])));
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
    let own = own_error(p);
    fit_within(p, &own.iter().map(|&e| e.max(tol)).collect::<Vec<_>>())
}

/// How far a polyline's own vertices and chords may be off the smooth curve they stand
/// for, at each vertex (with a tenth more, for rounding): a chord's sagitta on the circle
/// through its turn, `L θ / 8` (L the mean of the vertex's two segments, θ the turn there;
/// none at the ends). Lines and arcs as far off the polyline keep as near that curve as it.
pub fn own_error(p: &[P]) -> Vec<f64> {
    let n = p.len();
    (0..n)
        .map(|k| {
            if k == 0 || k + 1 == n {
                return 0.0;
            }
            let (a, b) = (dist(p[k - 1], p[k]), dist(p[k], p[k + 1]));
            if a < 1e-12 || b < 1e-12 {
                return 0.0;
            }
            let (u, v) = (
                [(p[k][0] - p[k - 1][0]) / a, (p[k][1] - p[k - 1][1]) / a],
                [(p[k + 1][0] - p[k][0]) / b, (p[k + 1][1] - p[k][1]) / b],
            );
            let turn = (u[0] * v[1] - u[1] * v[0])
                .atan2(u[0] * v[0] + u[1] * v[1])
                .abs();
            OWN_SLACK * 0.5 * (a + b) * turn / 8.0
        })
        .collect()
}

/// The polyline's own error (`own_error`) taken this much larger: rounding.
const OWN_SLACK: f64 = 1.1;

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

/// Each of `lines` (a mesh's traces, all of them) as lines and arcs, fitted to the smooth
/// curve through its vertices (`refine`, with `max_turn`; 0: to the polyline): within
/// `tol` of it everywhere; further where it has room to the copper beside it (`rooms`), as far as
/// that allows, up to the more of `most` and its own error from the smooth curve it stands
/// for (`own_error`).
pub fn fit_all(
    lines: &[Vec<P>],
    edges: &[Vec<P>],
    tol: f64,
    pitch: f64,
    most: f64,
    max_turn: f64,
    give: f64,
) -> Vec<Vec<Piece>> {
    // (fitted to the smooth curve the polyline stands for, not to its corners)
    let refined = refine_all(lines, edges, pitch, max_turn / 2.0, give);
    let lines = &refined;
    if pitch <= 0.0 {
        return lines.iter().map(|l| fit(l, tol)).collect();
    }
    let room = rooms(lines, edges, pitch, pitch + 4.0 * most.max(tol));
    lines
        .iter()
        .zip(room)
        .map(|(line, room)| {
            let own = own_error(line);
            let tols: Vec<f64> = own
                .iter()
                .zip(room)
                .map(|(&e, r)| r.max(0.0).min(e.max(most)).max(tol))
                .collect();
            fit_within(line, &tols)
        })
        .collect()
}

/// How far each vertex of `lines` may move (towards the copper beside it, the worst case)
/// and its traces keep the `pitch` apart: half of how much further than the pitch the
/// nearest other trace is (or its own, more than a pitch and a fifth along it, as round a
/// U-turn: either may move), all of how much further than half a pitch the area's edge
/// (`edges`, closed rings) is; copper only looked for within `reach` (none: `reach`).
/// Negative where the traces are already nearer than that.
pub fn rooms(lines: &[Vec<P>], edges: &[Vec<P>], pitch: f64, reach: f64) -> Vec<Vec<f64>> {
    rooms_to(lines, edges, pitch, reach, Copper::All)
}

/// Which copper `rooms_to` counts.
#[derive(Clone, Copy, PartialEq)]
enum Copper {
    All,
    Traces,
    Edges,
}

/// `rooms`, to the traces, the edges or both.
fn rooms_to(
    lines: &[Vec<P>],
    edges: &[Vec<P>],
    pitch: f64,
    reach: f64,
    which: Copper,
) -> Vec<Vec<f64>> {
    rooms_by(lines, edges, pitch, reach, which)
        .into_iter()
        .map(|l| l.into_iter().map(|(r, _)| r).collect())
        .collect()
}

/// A vertex's room, with the trace segment nearest it (its line, its segment there), if a
/// trace's.
type Room = (f64, Option<(usize, usize)>);

/// `rooms_to`, each with the trace segment nearest.
fn rooms_by(
    lines: &[Vec<P>],
    edges: &[Vec<P>],
    pitch: f64,
    reach: f64,
    which: Copper,
) -> Vec<Vec<Room>> {
    // (every segment, with its line (none: an edge's) and where along that it lies)
    let (mut a, mut b, mut owner) = (Vec::new(), Vec::new(), Vec::new());
    for (li, line) in lines.iter().enumerate() {
        let mut s = 0.0;
        for (si, w) in line.windows(2).enumerate() {
            let l = dist(w[0], w[1]);
            a.push(w[0]);
            b.push(w[1]);
            owner.push((Some((li, si)), s, s + l));
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
            line.iter()
                .enumerate()
                .map(|(k, &q)| {
                    if k > 0 {
                        s += dist(line[k - 1], q);
                    }
                    let mut room = reach;
                    let mut nearest = None;
                    let lo = [q[0] - reach, q[1] - reach];
                    let hi = [q[0] + reach, q[1] + reach];
                    segs.around(lo, hi, |i| {
                        let (o, s0, s1) = owner[i];
                        let d = dist(closest(q, segs.a[i], segs.b[i]).0, q);
                        let r = match o {
                            None if which == Copper::Traces => return,
                            Some(_) if which == Copper::Edges => return,
                            None => d - pitch / 2.0,
                            // (the trace itself, here: its own curve, not copper beside it)
                            Some((oi, _)) if oi == li && s0 - own < s && s < s1 + own => return,
                            Some(_) => (d - pitch) / 2.0,
                        };
                        if r < room {
                            room = r;
                            nearest = o;
                        }
                    });
                    (room, nearest)
                })
                .collect()
        })
        .collect()
}

/// The polyline as the smooth curve through its vertices that it stands for, sampled so
/// that no two segments turn more than `max_turn` (radians) from one another: a cubic
/// Hermite curve through every vertex, its tangent there along the vertex's neighbours'
/// chord (as long as the segment), each segment split as finely as its tangents turn.
pub fn refine(p: &[P], max_turn: f64) -> Vec<P> {
    refine_where(p, max_turn, &vec![true; p.len().saturating_sub(1)]).0
}

/// `refine`, but only the segments `allow`ed (the others straight, their chords); with the
/// segment each point lies on (a vertex: the segment it ends).
fn refine_where(p: &[P], max_turn: f64, allow: &[bool]) -> (Vec<P>, Vec<usize>) {
    let n = p.len();
    if n < 3 || max_turn <= 0.0 {
        return (p.to_vec(), (0..n).map(|k| k.saturating_sub(1)).collect());
    }
    let unit = |d: P| {
        let l = norm(d);
        if l < 1e-12 {
            [0.0, 0.0]
        } else {
            scale(d, 1.0 / l)
        }
    };
    let tangent: Vec<P> = (0..n)
        .map(|k| match k {
            0 => unit(sub(p[1], p[0])),
            _ if k == n - 1 => unit(sub(p[n - 1], p[n - 2])),
            _ => unit(sub(p[k + 1], p[k - 1])),
        })
        .collect();
    let mut out = vec![p[0]];
    let mut seg = vec![0];
    for k in 0..n - 1 {
        let (a, b) = (p[k], p[k + 1]);
        let l = dist(a, b);
        let (ta, tb) = (tangent[k], tangent[k + 1]);
        let turn = (ta[0] * tb[1] - ta[1] * tb[0])
            .atan2(ta[0] * tb[0] + ta[1] * tb[1])
            .abs();
        let m = if allow[k] {
            ((turn / max_turn).ceil() as usize).max(1)
        } else {
            1
        };
        for i in 1..m {
            let t = i as f64 / m as f64;
            let (t2, t3) = (t * t, t * t * t);
            let (h00, h10, h01, h11) = (
                2.0 * t3 - 3.0 * t2 + 1.0,
                t3 - 2.0 * t2 + t,
                -2.0 * t3 + 3.0 * t2,
                t3 - t2,
            );
            out.push([
                h00 * a[0] + h10 * l * ta[0] + h01 * b[0] + h11 * l * tb[0],
                h00 * a[1] + h10 * l * ta[1] + h01 * b[1] + h11 * l * tb[1],
            ]);
            seg.push(k);
        }
        out.push(b);
        seg.push(k);
    }
    (out, seg)
}

/// Each of `lines` as `refine` makes it, but a segment whose curve would come nearer the
/// copper beside it than the `pitch` (`rooms`: the curves', the area's `edges`), and nearer
/// than its chord did, by more than `give` (a share of the pitch), kept straight.
pub fn refine_all(
    lines: &[Vec<P>],
    edges: &[Vec<P>],
    pitch: f64,
    max_turn: f64,
    give: f64,
) -> Vec<Vec<P>> {
    if max_turn <= 0.0 || pitch <= 0.0 {
        return lines.iter().map(|l| refine(l, max_turn)).collect();
    }
    let reach = 1.5 * pitch;
    // (to the traces and to the edges each: a vertex tight to one may not crowd the other)
    let kinds = [Copper::Traces, Copper::Edges];
    let before: Vec<_> = kinds
        .iter()
        .map(|&c| rooms_to(lines, edges, pitch, reach, c))
        .collect();
    let mut allow: Vec<Vec<bool>> = lines
        .iter()
        .map(|l| vec![true; l.len().saturating_sub(1)])
        .collect();
    let mut out: Vec<(Vec<P>, Vec<usize>)> = Vec::new();
    for _ in 0..6 {
        out = lines
            .iter()
            .zip(&allow)
            .map(|(l, a)| refine_where(l, max_turn, a))
            .collect();
        let pts: Vec<Vec<P>> = out.iter().map(|(p, _)| p.clone()).collect();
        let mut changed = false;
        for (c, &kind) in kinds.iter().enumerate() {
            let after = rooms_by(&pts, edges, pitch, reach, kind);
            for (li, (_, seg)) in out.iter().enumerate() {
                for (q, &k) in seg.iter().enumerate() {
                    let k = k.min(lines[li].len().saturating_sub(2));
                    let floor =
                        before[c][li][k].min(before[c][li][k + 1]).min(0.0) - give * pitch / 2.0;
                    let (room, nearest) = after[li][q];
                    if room >= floor - 1e-9 {
                        continue;
                    }
                    // (straight: this point's segment, and the one crowding it)
                    let mut flag = |l: usize, k: usize| {
                        if allow[l][k] {
                            allow[l][k] = false;
                            changed = true;
                        }
                    };
                    flag(li, k);
                    if let Some((ol, os)) = nearest {
                        let ok = out[ol].1[os + 1].min(lines[ol].len().saturating_sub(2));
                        flag(ol, ok);
                    }
                }
            }
        }
        if !changed {
            break;
        }
    }
    out.into_iter().map(|(p, _)| p).collect()
}

/// The polyline with as few vertices as keep it within `tol` and each segment within a
/// quarter of `max_turn` of the polyline's own along it (greedy: each as long as both
/// allow). Its own turning at most half of that a vertex (`refine`), no two segments turn
/// more than `max_turn` from one another.
pub fn simplify(p: &[P], tol: f64, max_turn: f64) -> Vec<P> {
    let n = p.len();
    if n < 3 {
        return p.to_vec();
    }
    let heading = |a: P, b: P| (b[1] - a[1]).atan2(b[0] - a[0]);
    let wrap = |x: f64| {
        (x + std::f64::consts::PI).rem_euclid(std::f64::consts::TAU) - std::f64::consts::PI
    };
    let mut out = vec![p[0]];
    let mut i = 0;
    while i + 1 < n {
        let mut j = i + 1;
        // (the furthest end whose chord keeps the run within tol, and turns along it within
        // the cap)
        while j + 1 < n {
            let k = j + 1;
            let fits = (i + 1..k).all(|v| dist(closest(p[v], p[i], p[k]).0, p[v]) <= tol);
            let chord = heading(p[i], p[k]);
            let turns =
                (i..k).all(|v| wrap(heading(p[v], p[v + 1]) - chord).abs() <= max_turn / 4.0);
            if !(fits && turns) || k - i > SPAN {
                break;
            }
            j = k;
        }
        out.push(p[j]);
        i = j;
    }
    out
}

/// Each of `lines` as the smooth curve through its vertices (`refine_all`: straight where
/// it would crowd the copper beside it), simplified again within `tol`, no two segments
/// turning more than `max_turn` (`simplify`).
pub fn smooth_all(
    lines: &[Vec<P>],
    edges: &[Vec<P>],
    pitch: f64,
    tol: f64,
    max_turn: f64,
    give: f64,
) -> Vec<Vec<P>> {
    refine_all(lines, edges, pitch, max_turn / 2.0, give)
        .iter()
        .map(|l| simplify(l, tol, max_turn))
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
