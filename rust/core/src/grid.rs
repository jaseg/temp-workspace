//! A flat bucket grid of points (a counting sort by cell), for every point within a radius
//! of a query. Cells are half the usual radius, so a look-up scans about 5 x 5 cells: fewer
//! points to reject than 3 x 3 cells as wide as the radius.

use crate::geom::P;

pub struct Grid {
    x0: f64,
    y0: f64,
    cell: f64,
    w: usize,
    h: usize,
    start: Vec<u32>, // (per cell, into `items`; one more than cells)
    items: Vec<u32>,
}

impl Grid {
    /// The points `p` (only those `keep` says), in cells of `cell`.
    pub fn new(p: &[P], cell: f64, keep: impl Fn(usize) -> bool) -> Grid {
        let (mut x0, mut y0, mut x1, mut y1) = (f64::MAX, f64::MAX, f64::MIN, f64::MIN);
        for q in p {
            x0 = x0.min(q[0]);
            y0 = y0.min(q[1]);
            x1 = x1.max(q[0]);
            y1 = y1.max(q[1]);
        }
        if p.is_empty() {
            (x0, y0, x1, y1) = (0.0, 0.0, 0.0, 0.0);
        }
        let w = (((x1 - x0) / cell).floor() as usize + 1).max(1);
        let h = (((y1 - y0) / cell).floor() as usize + 1).max(1);
        let mut g = Grid {
            x0,
            y0,
            cell,
            w,
            h,
            start: vec![0; w * h + 1],
            items: Vec::new(),
        };
        let mut key = vec![u32::MAX; p.len()];
        for (i, q) in p.iter().enumerate() {
            if keep(i) {
                let k = g.key(*q);
                key[i] = k as u32;
                g.start[k + 1] += 1;
            }
        }
        for k in 0..w * h {
            g.start[k + 1] += g.start[k];
        }
        let mut fill = g.start.clone();
        g.items = vec![0; g.start[w * h] as usize];
        for (i, &k) in key.iter().enumerate() {
            if k != u32::MAX {
                g.items[fill[k as usize] as usize] = i as u32;
                fill[k as usize] += 1;
            }
        }
        g
    }

    #[inline]
    fn cx(&self, x: f64) -> i64 {
        ((x - self.x0) / self.cell).floor() as i64
    }

    #[inline]
    fn cy(&self, y: f64) -> i64 {
        ((y - self.y0) / self.cell).floor() as i64
    }

    #[inline]
    fn key(&self, q: P) -> usize {
        let i = self.cx(q[0]).clamp(0, self.w as i64 - 1) as usize;
        let j = self.cy(q[1]).clamp(0, self.h as i64 - 1) as usize;
        j * self.w + i
    }

    /// Each point in the cells within `r` of `q` (a superset of those within `r`).
    #[inline]
    pub fn around(&self, q: P, r: f64, mut f: impl FnMut(usize)) {
        let (i0, i1) = (
            self.cx(q[0] - r).max(0),
            self.cx(q[0] + r).min(self.w as i64 - 1),
        );
        let (j0, j1) = (
            self.cy(q[1] - r).max(0),
            self.cy(q[1] + r).min(self.h as i64 - 1),
        );
        for j in j0..=j1 {
            let row = j as usize * self.w;
            for i in i0..=i1 {
                let k = row + i as usize;
                for &it in &self.items[self.start[k] as usize..self.start[k + 1] as usize] {
                    f(it as usize);
                }
            }
        }
    }

    /// Whether any point is in the cells within `r` of `q` (cheap: most of a layout is far
    /// from its edge).
    #[inline]
    pub fn any_around(&self, q: P, r: f64) -> bool {
        let (i0, i1) = (
            self.cx(q[0] - r).max(0),
            self.cx(q[0] + r).min(self.w as i64 - 1),
        );
        let (j0, j1) = (
            self.cy(q[1] - r).max(0),
            self.cy(q[1] + r).min(self.h as i64 - 1),
        );
        if i0 > i1 || j0 > j1 {
            return false;
        }
        (j0..=j1).any(|j| {
            let row = j as usize * self.w;
            self.start[row + i1 as usize + 1] > self.start[row + i0 as usize]
        })
    }
}
