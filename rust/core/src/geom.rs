//! Points and the little vector arithmetic the settling needs.

pub type P = [f64; 2];

#[inline]
pub fn sub(a: P, b: P) -> P {
    [a[0] - b[0], a[1] - b[1]]
}

#[inline]
pub fn add(a: P, b: P) -> P {
    [a[0] + b[0], a[1] + b[1]]
}

#[inline]
pub fn scale(a: P, k: f64) -> P {
    [a[0] * k, a[1] * k]
}

#[inline]
pub fn dot(a: P, b: P) -> f64 {
    a[0] * b[0] + a[1] * b[1]
}

#[inline]
pub fn cross(a: P, b: P) -> f64 {
    a[0] * b[1] - a[1] * b[0]
}

#[inline]
pub fn norm(a: P) -> f64 {
    a[0].hypot(a[1])
}

#[inline]
pub fn dist(a: P, b: P) -> f64 {
    (a[0] - b[0]).hypot(a[1] - b[1])
}

/// The point of segment `a`-`b` nearest `q`, and where on it (0 at `a`, 1 at `b`).
#[inline]
pub fn closest(q: P, a: P, b: P) -> (P, f64) {
    let e = sub(b, a);
    let t = (dot(sub(q, a), e) / (dot(e, e)).max(1e-18)).clamp(0.0, 1.0);
    (add(a, scale(e, t)), t)
}

/// Whether segment `a`-`b` crosses `c`-`d` (strictly: not just touching).
#[inline]
pub fn crosses(a: P, b: P, c: P, d: P) -> bool {
    let side = |p: P, q: P, r: P| cross(sub(q, p), sub(r, p));
    side(a, b, c) * side(a, b, d) < 0.0 && side(c, d, a) * side(c, d, b) < 0.0
}

/// The open polyline at an even step along it (its ends kept), as `mesh.resample`.
pub fn resample(p: &[P], step: f64) -> Vec<P> {
    if p.len() < 2 {
        return p.to_vec();
    }
    let mut s = Vec::with_capacity(p.len());
    s.push(0.0);
    for w in p.windows(2) {
        s.push(s.last().unwrap() + dist(w[0], w[1]));
    }
    let total = *s.last().unwrap();
    let n = ((total / step).round() as usize).max(1);
    let mut out = Vec::with_capacity(n + 1);
    let mut k = 0;
    for i in 0..=n {
        let t = total * i as f64 / n as f64;
        while k + 2 < s.len() && s[k + 1] < t {
            k += 1;
        }
        let span = s[k + 1] - s[k];
        let f = if span > 0.0 {
            ((t - s[k]) / span).clamp(0.0, 1.0)
        } else {
            0.0
        };
        out.push(add(p[k], scale(sub(p[k + 1], p[k]), f)));
    }
    out
}
