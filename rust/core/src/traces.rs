//! Open polylines held as one array: each vertex's trace, where along its trace it was as
//! laid (a share of it), and the vertex before and after it (`NONE` at its ends).

use crate::geom::{add, closest, dist, norm, scale, sub, P};

pub const NONE: usize = usize::MAX;

#[derive(Clone)]
pub struct Traces {
    pub p: Vec<P>,
    pub net: Vec<usize>,
    pub u: Vec<f64>,
    pub prev: Vec<usize>,
    pub next: Vec<usize>,
    pub first: Vec<usize>, // (each trace's first vertex, and one past the last)
}

impl Traces {
    pub fn new(lines: &[Vec<P>], u: Option<Vec<Vec<f64>>>) -> Traces {
        let mut tr = Traces {
            p: Vec::new(),
            net: Vec::new(),
            u: Vec::new(),
            prev: Vec::new(),
            next: Vec::new(),
            first: vec![0],
        };
        for (t, line) in lines.iter().enumerate() {
            let base = tr.p.len();
            let us = match &u {
                Some(u) => u[t].clone(),
                None => {
                    let mut arc = vec![0.0];
                    for w in line.windows(2) {
                        arc.push(arc.last().unwrap() + dist(w[0], w[1]));
                    }
                    let total = arc.last().copied().unwrap_or(0.0).max(1e-12);
                    arc.iter().map(|a| a / total).collect()
                }
            };
            for (k, &q) in line.iter().enumerate() {
                tr.p.push(q);
                tr.net.push(t);
                tr.u.push(us[k]);
                tr.prev.push(if k == 0 { NONE } else { base + k - 1 });
                tr.next.push(if k + 1 == line.len() {
                    NONE
                } else {
                    base + k + 1
                });
            }
            tr.first.push(tr.p.len());
        }
        tr
    }

    pub fn len(&self) -> usize {
        self.p.len()
    }

    pub fn is_empty(&self) -> bool {
        self.p.is_empty()
    }

    pub fn traces(&self) -> usize {
        self.first.len() - 1
    }

    pub fn lines(&self) -> Vec<Vec<P>> {
        self.first
            .windows(2)
            .map(|w| self.p[w[0]..w[1]].to_vec())
            .collect()
    }

    /// `k` vertices back (or on) along the trace, stopping at its end.
    #[inline]
    pub fn back(&self, mut i: usize, k: usize) -> usize {
        for _ in 0..k {
            if self.prev[i] == NONE {
                break;
            }
            i = self.prev[i];
        }
        i
    }

    #[inline]
    pub fn on(&self, mut i: usize, k: usize) -> usize {
        for _ in 0..k {
            if self.next[i] == NONE {
                break;
            }
            i = self.next[i];
        }
        i
    }

    /// The traces at about `step` between vertices (`_respace`), each vertex's place as
    /// laid carried along.
    pub fn respaced(&self, step: f64) -> Traces {
        let mut lines = Vec::with_capacity(self.traces());
        let mut us = Vec::with_capacity(self.traces());
        for w in self.first.windows(2) {
            let (t, u) = (&self.p[w[0]..w[1]], &self.u[w[0]..w[1]]);
            let m = t.len();
            // (a vertex whose segments together are shorter than the step, but not one
            // after another such: the one before it stays; and only where it is about on
            // the line between its neighbours: cutting a kink's corner would bring the
            // trace nearer other copper than it was checked to be)
            let mut short = vec![false; m];
            for k in 1..m.saturating_sub(1) {
                short[k] = dist(t[k - 1], t[k]) + dist(t[k], t[k + 1]) < step
                    && dist(closest(t[k], t[k - 1], t[k + 1]).0, t[k]) < 0.02 * step;
            }
            let drop: Vec<bool> = (0..m)
                .map(|k| short[k] && !(k > 0 && short[k - 1]))
                .collect();
            let (t, u): (Vec<P>, Vec<f64>) =
                (0..m).filter(|&k| !drop[k]).map(|k| (t[k], u[k])).unzip();
            let mut line = Vec::with_capacity(t.len() * 2);
            let mut uu = Vec::with_capacity(t.len() * 2);
            for k in 0..t.len().saturating_sub(1) {
                let parts = ((dist(t[k], t[k + 1]) / (1.5 * step)).ceil() as usize).max(1);
                for j in 0..parts {
                    let f = j as f64 / parts as f64;
                    line.push(add(t[k], scale(sub(t[k + 1], t[k]), f)));
                    uu.push(u[k] + (u[k + 1] - u[k]) * f);
                }
            }
            if let (Some(&q), Some(&v)) = (t.last(), u.last()) {
                line.push(q);
                uu.push(v);
            }
            lines.push(line);
            us.push(uu);
        }
        Traces::new(&lines, Some(us))
    }

    /// Each vertex's length run along its trace.
    pub fn arc(&self) -> Vec<f64> {
        let mut out = vec![0.0; self.len()];
        for i in 0..self.len() {
            if self.prev[i] != NONE {
                out[i] = out[self.prev[i]] + dist(self.p[self.prev[i]], self.p[i]);
            }
        }
        out
    }

    /// Each vertex's unit normal (to the left of the way along it).
    pub fn normals(&self) -> Vec<P> {
        (0..self.len())
            .map(|i| {
                let a = if self.prev[i] == NONE {
                    i
                } else {
                    self.prev[i]
                };
                let b = if self.next[i] == NONE {
                    i
                } else {
                    self.next[i]
                };
                let t = sub(self.p[b], self.p[a]);
                let l = norm(t).max(1e-12);
                [-t[1] / l, t[0] / l]
            })
            .collect()
    }

    /// Each vertex's signed curvature (turning left: positive), from the chords `reach`
    /// vertices either way along its trace (0 near its ends).
    pub fn turning(&self, reach: usize) -> Vec<f64> {
        (0..self.len())
            .map(|i| {
                let (a, b) = (self.back(i, reach), self.on(i, reach));
                let (u, v) = (sub(self.p[i], self.p[a]), sub(self.p[b], self.p[i]));
                let turn = (u[0] * v[1] - u[1] * v[0]).atan2(u[0] * v[0] + u[1] * v[1]);
                let chord = (norm(u) + norm(v)) / 2.0;
                if chord > 1e-12 {
                    turn / chord
                } else {
                    0.0
                }
            })
            .collect()
    }

    /// From each vertex towards the middle of the chord `reach` vertices either way:
    /// towards its bend's inside, as deep as the bend that wide.
    pub fn bends(&self, reach: usize) -> Vec<P> {
        (0..self.len())
            .map(|i| {
                let (a, b) = (self.back(i, reach), self.on(i, reach));
                sub(scale(add(self.p[a], self.p[b]), 0.5), self.p[i])
            })
            .collect()
    }

    /// Each trace's length by position along it as laid (`bins` of it).
    pub fn binned(&self, bins: usize) -> Vec<Vec<f64>> {
        let mut out = vec![vec![0.0; bins]; self.traces()];
        for i in 0..self.len() {
            if self.next[i] != NONE {
                let b = ((self.u[i] * bins as f64) as usize).min(bins - 1);
                out[self.net[i]][b] += dist(self.p[i], self.p[self.next[i]]);
            }
        }
        out
    }

    /// Each vertex's place along the curve (its bin).
    pub fn bins(&self, bins: usize) -> Vec<usize> {
        self.u
            .iter()
            .map(|u| ((u * bins as f64) as usize).min(bins - 1))
            .collect()
    }
}
