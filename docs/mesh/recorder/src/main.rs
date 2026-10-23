//! The cells `graph::curve` builds its graph from, as its first try does: one random stream
//! (the call's key) through the segments in turn, `graph::cells` for each, the openings'
//! pins placed as `graph::curve` places them. The core is used as it is; nothing here
//! changes what it computes.
//!
//! stdin (whitespace-separated numbers): key (64 hex digits), spacing, seed_spacing, lloyd,
//! the openings (count, then x0 y0 x1 y1 each), the segments (count, then per segment its
//! rings: count, then per ring its points: count, then x y each).
//! stdout: per segment, its cells: count, then per cell its rings (count, then per ring its
//! points: count, then x y each, in Rust's shortest round-trip notation).

use std::io::Read;

use yanartas_mesh_core::geom::{add, norm, scale, sub, P};
use yanartas_mesh_core::graph::{cells, Rng};
use yanartas_mesh_core::poly::{contains, distance, Rings};

fn main() {
    let mut text = String::new();
    std::io::stdin().read_to_string(&mut text).unwrap();
    let mut it = text.split_whitespace();
    let hex = it.next().unwrap();
    let mut key = [0u8; 32];
    for (i, k) in key.iter_mut().enumerate() {
        *k = u8::from_str_radix(&hex[2 * i..2 * i + 2], 16).unwrap();
    }
    let mut num = || it.next().unwrap().parse::<f64>().unwrap();
    let spacing = num();
    let seed_spacing = num();
    let lloyd = num() as usize;
    let openings: Vec<[P; 2]> = (0..num() as usize)
        .map(|_| [[num(), num()], [num(), num()]])
        .collect();
    let segments: Vec<Rings> = (0..num() as usize)
        .map(|_| {
            (0..num() as usize)
                .map(|_| (0..num() as usize).map(|_| [num(), num()]).collect())
                .collect()
        })
        .collect();
    // (as graph::curve)
    let d = seed_spacing * spacing;
    let nearest = |q: P| {
        (0..segments.len())
            .min_by(|&i, &j| distance(&segments[i], q).total_cmp(&distance(&segments[j], q)))
            .unwrap()
    };
    let mut pins: Vec<Vec<P>> = vec![Vec::new(); segments.len()];
    for opening in &openings {
        let across = sub(opening[1], opening[0]);
        let inward = scale([-across[1], across[0]], 1.0 / norm(across).max(1e-12));
        let pin = add(scale(add(opening[0], opening[1]), 0.5), scale(inward, d / 2.0));
        let seg = nearest(opening[0]);
        if contains(&segments[seg], pin) {
            pins[seg].push(pin);
        }
    }
    let mut rng = Rng::new(&key);
    let mut out = String::new();
    for (si, domain) in segments.iter().enumerate() {
        let got = cells(domain, d, &mut rng, &pins[si], lloyd);
        out += &format!("{}\n", got.len());
        for cell in got {
            out += &format!("{}\n", cell.len());
            for ring in cell {
                out += &format!("{}", ring.len());
                for q in ring {
                    out += &format!(" {:?} {:?}", q[0], q[1]);
                }
                out += "\n";
            }
        }
    }
    print!("{out}");
}
