//! The traces' density about each point (`mesh.density`, as settling sees it): their length
//! per area on a grid, times the pitch (1: traces side by side at the pitch), blurred (three
//! box blurs: about a Gaussian) over the area blurred alike, so that the area's edge counts
//! no hole. Its slope points out of the holes between runs, from as far as the blur.

use crate::geom::{dist, P};
use crate::traces::{Traces, NONE};

pub struct Density {
    o: P,
    cell: f64,
    nx: usize,
    ny: usize,
    r: usize,
    inside: Vec<f64>, // (1 in the area)
    share: Vec<f64>,  // (the area, blurred)
    val: Vec<f64>,
}

impl Density {
    /// A grid over `bounds` (x0, y0, x1, y1) blurring over about `blur`, the cells inside
    /// the area those `inside` says.
    pub fn new(bounds: [f64; 4], blur: f64, inside: impl Fn(P) -> bool + Sync + Send) -> Density {
        let cell = blur / 3.0;
        let pad = 3.0 * blur;
        let o = [bounds[0] - pad, bounds[1] - pad];
        let nx = ((bounds[2] - bounds[0] + 2.0 * pad) / cell).ceil() as usize + 1;
        let ny = ((bounds[3] - bounds[1] + 2.0 * pad) / cell).ceil() as usize + 1;
        // (three box blurs of half-width r: variance r (r + 1) cells²)
        let r =
            ((((1.0 + 4.0 * (blur / cell).powi(2)).sqrt() - 1.0) / 2.0).round() as usize).max(1);
        let centre = |k: usize| {
            [
                o[0] + ((k % nx) as f64 + 0.5) * cell,
                o[1] + ((k / nx) as f64 + 0.5) * cell,
            ]
        };
        let inside: Vec<f64> = crate::par::pmap(nx * ny, |k| inside(centre(k)) as u8 as f64);
        let mut d = Density {
            o,
            cell,
            nx,
            ny,
            r,
            share: Vec::new(),
            val: vec![0.0; nx * ny],
            inside,
        };
        d.share = d.smooth(d.inside.clone());
        d
    }

    /// The density of `tr` (at `pitch`), from scratch.
    pub fn update(&mut self, tr: &Traces, pitch: f64) {
        let mut copper = vec![0.0; self.nx * self.ny];
        let per = pitch / (self.cell * self.cell);
        for i in 0..tr.len() {
            let j = tr.next[i];
            if j == NONE {
                continue;
            }
            let (a, b) = (tr.p[i], tr.p[j]);
            let m = [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0];
            if let Some(k) = self.index(m) {
                copper[k] += dist(a, b) * per * self.inside[k];
            }
        }
        let blurred = self.smooth(copper);
        self.val = blurred
            .iter()
            .zip(&self.share)
            .map(|(c, s)| if *s > 1e-9 { c / s } else { 0.0 })
            .collect();
    }

    fn index(&self, q: P) -> Option<usize> {
        let x = ((q[0] - self.o[0]) / self.cell).floor();
        let y = ((q[1] - self.o[1]) / self.cell).floor();
        (x >= 0.0 && y >= 0.0 && (x as usize) < self.nx && (y as usize) < self.ny)
            .then(|| y as usize * self.nx + x as usize)
    }

    /// The density at `q` (between the cells' middles: bilinear).
    pub fn at(&self, q: P) -> f64 {
        let fx = (q[0] - self.o[0]) / self.cell - 0.5;
        let fy = (q[1] - self.o[1]) / self.cell - 0.5;
        let (x, y) = (fx.floor(), fy.floor());
        if x < 0.0 || y < 0.0 || x as usize + 1 >= self.nx || y as usize + 1 >= self.ny {
            return 0.0;
        }
        let (tx, ty) = (fx - x, fy - y);
        let k = y as usize * self.nx + x as usize;
        let v = &self.val;
        (v[k] * (1.0 - tx) + v[k + 1] * tx) * (1.0 - ty)
            + (v[k + self.nx] * (1.0 - tx) + v[k + self.nx + 1] * tx) * ty
    }

    /// The density's slope at `q` (per mm).
    pub fn slope(&self, q: P) -> P {
        let h = self.cell;
        [
            (self.at([q[0] + h, q[1]]) - self.at([q[0] - h, q[1]])) / (2.0 * h),
            (self.at([q[0], q[1] + h]) - self.at([q[0], q[1] - h])) / (2.0 * h),
        ]
    }

    /// `a` blurred (three box blurs each way; nothing beyond the grid).
    fn smooth(&self, mut a: Vec<f64>) -> Vec<f64> {
        let (nx, ny, r) = (self.nx, self.ny, self.r);
        let w = (2 * r + 1) as f64;
        let mut c = Vec::new();
        for _ in 0..3 {
            for (len, stride, lines, gap) in [(nx, 1, ny, nx), (ny, nx, nx, 1)] {
                for l in 0..lines {
                    let base = l * gap;
                    c.clear();
                    c.push(0.0);
                    for k in 0..len {
                        c.push(c[k] + a[base + k * stride]);
                    }
                    for k in 0..len {
                        let hi = (k + r + 1).min(len);
                        let lo = k.saturating_sub(r);
                        a[base + k * stride] = (c[hi] - c[lo]) / w;
                    }
                }
            }
        }
        a
    }
}
