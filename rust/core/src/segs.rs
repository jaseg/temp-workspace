//! Segments bucketed by the grid cells their boxes touch (`mesh.Rays`): the segments that
//! may meet a segment or a ray, and the closed curve's self-crossings (`sfc._crossing`).

use std::collections::HashMap;

use crate::geom::{cross, dot, sub, P};
use crate::par::pmap;

pub struct Segs {
    pub a: Vec<P>,
    pub b: Vec<P>,
    cell: f64,
    cells: HashMap<(i64, i64), Vec<u32>>,
}

impl Segs {
    pub fn new(a: Vec<P>, b: Vec<P>, cell: f64) -> Segs {
        let mut cells: HashMap<(i64, i64), Vec<u32>> = HashMap::new();
        for i in 0..a.len() {
            let (lo, hi) = Self::span(a[i], b[i], cell);
            for x in lo.0..=hi.0 {
                for y in lo.1..=hi.1 {
                    cells.entry((x, y)).or_default().push(i as u32);
                }
            }
        }
        Segs { a, b, cell, cells }
    }

    fn span(a: P, b: P, cell: f64) -> ((i64, i64), (i64, i64)) {
        let c = |v: f64| (v / cell).floor() as i64;
        (
            (c(a[0].min(b[0])), c(a[1].min(b[1]))),
            (c(a[0].max(b[0])), c(a[1].max(b[1]))),
        )
    }

    /// Each segment whose cells the box of `p`-`q` touches (maybe more than once).
    pub fn around(&self, p: P, q: P, mut f: impl FnMut(usize)) {
        let (lo, hi) = Self::span(p, q, self.cell);
        for x in lo.0..=hi.0 {
            for y in lo.1..=hi.1 {
                if let Some(v) = self.cells.get(&(x, y)) {
                    for &i in v {
                        f(i as usize);
                    }
                }
            }
        }
    }

    /// Where the ray from `p` along `d` (unit) first meets a segment within `reach` (its
    /// distance), with the segment; none: `None`.
    pub fn cast(&self, p: P, d: P, reach: f64) -> Option<(f64, usize)> {
        let q = [p[0] + d[0] * reach, p[1] + d[1] * reach];
        let mut best: Option<(f64, usize)> = None;
        self.around(p, q, |j| {
            if let Some(t) = ray_hit(p, d, self.a[j], self.b[j]) {
                if t <= reach && best.is_none_or(|b| t < b.0) {
                    best = Some((t, j));
                }
            }
        });
        best
    }
}

/// The ray from `p` along unit `d` meeting segment `a`-`b`: how far along it (`> 1e-9`).
#[inline]
pub fn ray_hit(p: P, d: P, a: P, b: P) -> Option<f64> {
    let e = sub(b, a);
    let den = cross(d, e);
    if den.abs() <= 1e-12 {
        return None;
    }
    let w = sub(a, p);
    let t = cross(w, e) / den;
    let s = cross(w, d) / den;
    (t > 1e-9 && (0.0..=1.0).contains(&s)).then_some(t)
}

/// The closed polyline's segments among `which` (segment `i` from vertex `i` to the next)
/// that cross or touch another, other than their neighbours: the pairs.
pub fn crossing(p: &[P], which: &[usize]) -> Vec<(usize, usize)> {
    let n = p.len();
    if n < 4 {
        return Vec::new();
    }
    let next = |i: usize| p[(i + 1) % n];
    // (cells a few typical segments wide: a long one is put in every cell its box touches)
    let mean = (0..n)
        .map(|i| crate::geom::dist(p[i], next(i)))
        .sum::<f64>()
        / n as f64;
    let segs = Segs::new(
        p.to_vec(),
        (0..n).map(next).collect(),
        (4.0 * mean).max(1e-6),
    );
    let found: Vec<Vec<(usize, usize)>> = pmap(which.len(), |k| {
        let i = which[k];
        let (a, b) = (p[i], next(i));
        let e = sub(b, a);
        let len = dot(e, e).sqrt();
        if len <= 0.0 {
            return Vec::new();
        }
        let d = [e[0] / len, e[1] / len];
        let mut out = Vec::new();
        segs.around(a, b, |j| {
            let gap = i.abs_diff(j);
            if gap.min(n - gap) <= 1 {
                return;
            }
            if let Some(t) = ray_hit(a, d, segs.a[j], segs.b[j]) {
                if t <= len {
                    out.push((i, j));
                }
            }
        });
        out.sort_unstable();
        out.dedup();
        out
    });
    found.into_iter().flatten().collect()
}
