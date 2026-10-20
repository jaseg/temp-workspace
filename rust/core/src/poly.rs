//! Polygons as rings of points (the outline first, then holes; not closed), and the few
//! operations the curve's graph needs: area, centroid, containment, distances, clipping
//! (`geo`'s boolean operations, pure Rust: the same in the browser).

use geo::{BooleanOps, Coord, LineString, MultiPolygon, Polygon};

use crate::geom::{closest, dist, P};

pub type Rings = Vec<Vec<P>>;

pub fn ring_area(r: &[P]) -> f64 {
    let n = r.len();
    (0..n)
        .map(|i| {
            let (a, b) = (r[i], r[(i + 1) % n]);
            a[0] * b[1] - b[0] * a[1]
        })
        .sum::<f64>()
        / 2.0
}

pub fn area(p: &Rings) -> f64 {
    let mut s = 0.0;
    for (k, r) in p.iter().enumerate() {
        let a = ring_area(r).abs();
        s += if k == 0 { a } else { -a };
    }
    s
}

pub fn centroid(p: &Rings) -> P {
    let (mut cx, mut cy, mut a) = (0.0, 0.0, 0.0);
    for (k, r) in p.iter().enumerate() {
        let sign = if k == 0 { 1.0 } else { -1.0 } * ring_area(r).signum();
        let n = r.len();
        for i in 0..n {
            let (u, v) = (r[i], r[(i + 1) % n]);
            let c = (u[0] * v[1] - v[0] * u[1]) * sign;
            cx += (u[0] + v[0]) * c;
            cy += (u[1] + v[1]) * c;
            a += c;
        }
    }
    if a.abs() < 1e-18 {
        return p[0][0];
    }
    [cx / (3.0 * a), cy / (3.0 * a)]
}

/// Whether `q` is inside (even-odd over all rings).
pub fn contains(p: &Rings, q: P) -> bool {
    let mut inside = false;
    for r in p {
        let n = r.len();
        for i in 0..n {
            let (a, b) = (r[i], r[(i + 1) % n]);
            if (a[1] > q[1]) != (b[1] > q[1]) {
                let x = a[0] + (q[1] - a[1]) / (b[1] - a[1]) * (b[0] - a[0]);
                if x > q[0] {
                    inside = !inside;
                }
            }
        }
    }
    inside
}

/// The distance from `q` to the rings (the boundary).
pub fn boundary_distance(p: &Rings, q: P) -> f64 {
    let mut d = f64::MAX;
    for r in p {
        let n = r.len();
        for i in 0..n {
            d = d.min(dist(closest(q, r[i], r[(i + 1) % n]).0, q));
        }
    }
    d
}

/// The distance from `q` to the polygon (0 inside).
pub fn distance(p: &Rings, q: P) -> f64 {
    if contains(p, q) {
        0.0
    } else {
        boundary_distance(p, q)
    }
}

pub fn bounds(p: &Rings) -> [f64; 4] {
    let mut b = [f64::MAX, f64::MAX, f64::MIN, f64::MIN];
    for q in p.iter().flatten() {
        b = [
            b[0].min(q[0]),
            b[1].min(q[1]),
            b[2].max(q[0]),
            b[3].max(q[1]),
        ];
    }
    b
}

fn to_geo(p: &Rings) -> Polygon<f64> {
    let ring = |r: &Vec<P>| LineString::new(r.iter().map(|q| Coord { x: q[0], y: q[1] }).collect());
    Polygon::new(ring(&p[0]), p[1..].iter().map(ring).collect())
}

fn from_geo(m: MultiPolygon<f64>) -> Vec<Rings> {
    m.0.into_iter()
        .map(|poly| {
            let ring = |l: &LineString<f64>| {
                let mut r: Vec<P> = l.0.iter().map(|c| [c.x, c.y]).collect();
                if r.len() > 1 && r.first() == r.last() {
                    r.pop();
                }
                r
            };
            let mut out = vec![ring(poly.exterior())];
            out.extend(poly.interiors().iter().map(ring));
            out
        })
        .filter(|r: &Rings| r[0].len() >= 3)
        .collect()
}

/// The pieces of `a` within `b`.
pub fn intersection(a: &Rings, b: &Rings) -> Vec<Rings> {
    from_geo(to_geo(a).intersection(&to_geo(b)))
}

pub fn rect(x0: f64, y0: f64, x1: f64, y1: f64) -> Rings {
    vec![vec![[x0, y0], [x1, y0], [x1, y1], [x0, y1]]]
}

/// A point inside the polygon (its centroid when inside, else the middle of the widest
/// stretch inside across the row through the bounds' middle height).
pub fn inner_point(p: &Rings) -> P {
    let c = centroid(p);
    if contains(p, c) {
        return c;
    }
    let b = bounds(p);
    for frac in [0.5, 0.25, 0.75, 0.125, 0.375, 0.625, 0.875] {
        let y = b[1] + (b[3] - b[1]) * frac;
        let mut xs: Vec<f64> = Vec::new();
        for r in p {
            let n = r.len();
            for i in 0..n {
                let (u, v) = (r[i], r[(i + 1) % n]);
                if (u[1] > y) != (v[1] > y) {
                    xs.push(u[0] + (y - u[1]) / (v[1] - u[1]) * (v[0] - u[0]));
                }
            }
        }
        xs.sort_by(f64::total_cmp);
        let best = xs
            .chunks_exact(2)
            .max_by(|a, b| (a[1] - a[0]).total_cmp(&(b[1] - b[0])));
        if let Some(w) = best {
            return [(w[0] + w[1]) / 2.0, y];
        }
    }
    c
}
