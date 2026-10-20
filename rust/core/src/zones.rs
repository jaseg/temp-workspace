//! Which zone (panel) a point is in: an even-odd ray test against the zones' rings, their
//! edges bucketed by height so a test looks at the few edges across its row.

use crate::geom::P;

pub struct Zones {
    y0: f64,
    row: f64,
    rows: Vec<Vec<(usize, P, P)>>, // (zone, edge's ends) per row of height `row`
    zones: usize,
}

impl Zones {
    /// `zones[z]` is zone z's rings (outline and holes, each closed or not).
    pub fn new(zones: &[Vec<Vec<P>>], row: f64) -> Zones {
        let mut edges = Vec::new();
        for (z, rings) in zones.iter().enumerate() {
            for ring in rings {
                for k in 0..ring.len() {
                    let (a, b) = (ring[k], ring[(k + 1) % ring.len()]);
                    if a != b {
                        edges.push((z, a, b));
                    }
                }
            }
        }
        let y0 = edges
            .iter()
            .map(|e| e.1[1].min(e.2[1]))
            .fold(f64::MAX, f64::min);
        let y1 = edges
            .iter()
            .map(|e| e.1[1].max(e.2[1]))
            .fold(f64::MIN, f64::max);
        let (y0, y1) = if edges.is_empty() {
            (0.0, 0.0)
        } else {
            (y0, y1)
        };
        let n = (((y1 - y0) / row).floor() as usize + 1).max(1);
        let mut rows = vec![Vec::new(); n];
        for e in edges {
            let lo = (((e.1[1].min(e.2[1]) - y0) / row).floor() as usize).min(n - 1);
            let hi = (((e.1[1].max(e.2[1]) - y0) / row).floor() as usize).min(n - 1);
            for r in &mut rows[lo..=hi] {
                r.push(e);
            }
        }
        Zones {
            y0,
            row,
            rows,
            zones: zones.len(),
        }
    }

    /// The zone `q` is in (the first holding it), or `None`.
    pub fn of(&self, q: P) -> Option<usize> {
        let r = ((q[1] - self.y0) / self.row).floor();
        if r < 0.0 || r as usize >= self.rows.len() {
            return None;
        }
        let mut inside = vec![false; self.zones];
        for &(z, a, b) in &self.rows[r as usize] {
            if (a[1] > q[1]) != (b[1] > q[1]) {
                let x = a[0] + (q[1] - a[1]) / (b[1] - a[1]) * (b[0] - a[0]);
                if x > q[0] {
                    inside[z] = !inside[z];
                }
            }
        }
        inside.iter().position(|&i| i)
    }
}
