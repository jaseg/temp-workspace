//! The space-filling curve's combinatorial part (`sfc._curve`): per segment a centroidal
//! Voronoi tessellation (Lloyd iterations of jittered seeds), its cells' edges a planar
//! graph; the exit's stem; the cycles a perfect matching leaves out (Edmonds); a vertex
//! at each cell's centre threaded into a cycle edge (bipartite matching); the cycles merged
//! by split-and-reconnect and doubled edges; the segments joined across their borders along
//! a spanning tree; the curve walked from the stem's end round to its other end.

use std::collections::{BTreeSet, HashMap, HashSet, VecDeque};

use crate::geom::{add, closest, cross, dist, norm, scale, sub, P};
use crate::grid::Grid;
use crate::par::pmap;
use crate::poly::{
    area, boundary_distance, centroid, contains, distance, inner_point, intersection, rect, Rings,
};
use crate::segs::Segs;

/// `sfc.py`'s constants for the graph, by its names.
#[derive(Clone, Debug)]
pub struct GraphParams {
    pub seed_spacing: f64, // SEED_SPACING
    pub lloyd: usize,      // LLOYD
    pub attempts: usize,   // ATTEMPTS
}

impl Default for GraphParams {
    fn default() -> GraphParams {
        GraphParams {
            seed_spacing: 1.4,
            lloyd: 6,
            attempts: 8,
        }
    }
}

/// One zone's piece of the area: its region, and where its graph lies (the region shrunk by
/// half a spacing).
pub struct Segment {
    pub region: usize,
    pub domain: Rings,
}

/// What the graph is built from: the segments, the borders between regions (each pair of
/// regions with the lines of their shared border, longest first; the pairs longest first:
/// only those a curve may cross), the exits' openings (each a stem's two ends), the
/// spacing and the random seed.
pub struct GraphInput {
    pub segments: Vec<Segment>,
    pub borders: Vec<(usize, usize, Vec<Vec<P>>)>,
    pub openings: Vec<[P; 2]>,
    pub spacing: f64,
    pub seed: u64,
}

/// The curves, one per exit: each its vertices from its stem's end at `opening[0]` round
/// to its other end, and each vertex's region; the number of cells, and the number of
/// regions no curve could reach.
pub struct Curves {
    pub curves: Vec<(Vec<P>, Vec<usize>)>,
    pub cells: usize,
    pub left: usize,
}

/// A small, seeded random source (SplitMix64).
pub struct Rng(u64);

impl Rng {
    pub fn new(seed: u64) -> Rng {
        Rng(seed)
    }

    pub fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// In [0, 1).
    pub fn random(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 / (1u64 << 53) as f64
    }

    pub fn shuffle<T>(&mut self, v: &mut [T]) {
        for i in (1..v.len()).rev() {
            let j = (self.next_u64() % (i as u64 + 1)) as usize;
            v.swap(i, j);
        }
    }
}

type Edge = (usize, usize);

fn key(a: usize, b: usize) -> Edge {
    (a.min(b), a.max(b))
}

struct Graph {
    pts: Vec<P>,
    adj: Vec<BTreeSet<usize>>,
    seg: Vec<usize>,
    nbr: Vec<Vec<usize>>,
    faces: Vec<(Vec<usize>, Rings, usize)>,
    index: HashMap<(i64, i64), usize>,
    fixed: HashSet<Edge>,
}

impl Graph {
    fn new() -> Graph {
        Graph {
            pts: Vec::new(),
            adj: Vec::new(),
            seg: Vec::new(),
            nbr: Vec::new(),
            faces: Vec::new(),
            index: HashMap::new(),
            fixed: HashSet::new(),
        }
    }

    /// The vertex at `p` (within a micrometre), added if new.
    fn vertex(&mut self, p: P, seg: usize) -> usize {
        let q = 1e-6;
        let (kx, ky) = ((p[0] / q).round() as i64, (p[1] / q).round() as i64);
        for dx in [0, -1, 1] {
            for dy in [0, -1, 1] {
                if let Some(&i) = self.index.get(&(kx + dx, ky + dy)) {
                    return i;
                }
            }
        }
        let i = self.add(p, seg);
        self.index.insert((kx, ky), i);
        i
    }

    fn add(&mut self, p: P, seg: usize) -> usize {
        self.pts.push(p);
        self.adj.push(BTreeSet::new());
        self.seg.push(seg);
        self.nbr.push(Vec::new());
        self.pts.len() - 1
    }

    fn connect(&mut self, a: usize, b: usize) {
        self.adj[a].insert(b);
        self.adj[b].insert(a);
    }

    fn link(&mut self, a: usize, b: usize) {
        self.nbr[a].push(b);
        self.nbr[b].push(a);
    }

    fn unlink(&mut self, a: usize, b: usize) {
        if let Some(i) = self.nbr[a].iter().position(|&x| x == b) {
            self.nbr[a].remove(i);
        }
        if let Some(i) = self.nbr[b].iter().position(|&x| x == a) {
            self.nbr[b].remove(i);
        }
    }
}

struct Retry;

/// A build: the graph, its cycles' union, the stems' ends, the cells, the vertices lost.
type Built = (Graph, Union, Vec<(usize, usize)>, usize, usize);

/// The curves through the segments, one closed through each exit's stem (the segments a
/// border joins: one curve; those of different exits never joined).
pub fn curve(
    input: &GraphInput,
    prm: &GraphParams,
    progress: &mut dyn FnMut(usize, usize),
) -> Result<Curves, String> {
    let segments = &input.segments;
    if segments.is_empty() || input.openings.is_empty() {
        return Err("no room for the mesh".into());
    }
    let spacing = input.spacing;
    let d = prm.seed_spacing * spacing;
    let nearest = |q: P| {
        (0..segments.len())
            .min_by(|&i, &j| {
                distance(&segments[i].domain, q).total_cmp(&distance(&segments[j].domain, q))
            })
            .unwrap()
    };
    // (a seed pinned inside each opening: no cell wall reaches the edge between its ends;
    // inwards: square to the opening, to the left going from its first end to its second)
    let mut pins: Vec<Vec<P>> = vec![Vec::new(); segments.len()];
    for opening in &input.openings {
        let across = sub(opening[1], opening[0]);
        let inward = scale([-across[1], across[0]], 1.0 / norm(across).max(1e-12));
        let pin = add(
            scale(add(opening[0], opening[1]), 0.5),
            scale(inward, d / 2.0),
        );
        let seg = nearest(opening[0]);
        if contains(&segments[seg].domain, pin) {
            pins[seg].push(pin);
        }
    }
    let mut rng = Rng::new(input.seed);
    // (a build with a cycle no exit's curve took in, as one cut off in a narrow spot: tried
    // afresh, the best kept)
    let mut best: Option<Built> = None;
    for _ in 0..prm.attempts {
        if crate::cancelled() {
            break;
        }
        let mut g = Graph::new();
        for (si, s) in segments.iter().enumerate() {
            let cells = cells(&s.domain, d, &mut rng, &pins[si], prm.lloyd);
            build(&mut g, cells, si);
            progress(si + 1, segments.len() + 1);
        }
        let mut ends = Vec::new();
        for &opening in &input.openings {
            match stem(&mut g, segments, opening) {
                Ok(e) => ends.push(e),
                Err(Retry) => break,
            }
        }
        if ends.len() < input.openings.len() || two_factor(&mut g, &mut rng).is_err() {
            continue;
        }
        let cells = g.faces.len();
        centres(&mut g);
        let mut u = Union::new(g.pts.len());
        for x in 0..g.pts.len() {
            for &y in &g.nbr[x] {
                u.join(x, y);
            }
        }
        merge(&mut g, &mut u);
        join_segments(&mut g, &mut u, segments, &input.borders, spacing);
        let roots: HashSet<usize> = ends.iter().map(|&(a, _)| u.find(a)).collect();
        let lost = (0..g.pts.len())
            .filter(|&v| !g.nbr[v].is_empty() && !roots.contains(&u.find(v)))
            .count();
        if best.as_ref().is_none_or(|b| lost < b.4) {
            best = Some((g, u, ends, cells, lost));
        }
        if lost == 0 {
            break;
        }
    }
    let (g, mut u, ends, cells, _) = best.ok_or("could not build the curve's graph")?;
    let region = |v: usize| segments[g.seg[v]].region;
    let mut curves = Vec::new();
    let mut roots = HashSet::new();
    for &(a, b) in &ends {
        roots.insert(u.find(a));
        let mut order = vec![b, a]; // (walk from a away from b: the stem between them)
        for _ in 0..g.pts.len() + 2 {
            let last = order[order.len() - 1];
            let before = order[order.len() - 2];
            let Some(&nxt) = g.nbr[last].iter().find(|&&x| x != before) else {
                return Err("the curve's graph does not close".into());
            };
            if nxt == b {
                break;
            }
            order.push(nxt);
        }
        order.remove(0);
        order.push(b);
        curves.push((
            order.iter().map(|&v| g.pts[v]).collect(),
            order.iter().map(|&v| region(v)).collect(),
        ));
    }
    if roots.len() < ends.len() {
        return Err("two exits' curves were joined".into());
    }
    let all: HashSet<usize> = (0..g.pts.len())
        .filter(|&v| !g.nbr[v].is_empty())
        .map(region)
        .collect();
    let reached: HashSet<usize> = (0..g.pts.len())
        .filter(|&v| !g.nbr[v].is_empty() && roots.contains(&u.find(v)))
        .map(region)
        .collect();
    Ok(Curves {
        curves,
        cells,
        left: all.difference(&reached).count(),
    })
}

// ---------------------------------------------------------------------------- cells

/// Seeds on a triangular grid of side `d`, jittered by up to `d / 20` (section 3.2).
fn seeds(domain: &Rings, d: f64, rng: &mut Rng) -> Vec<P> {
    let [x0, y0, x1, y1] = crate::poly::bounds(domain);
    let h = d * 0.75f64.sqrt();
    let mut out = Vec::new();
    for j in 0..((y1 - y0) / h) as usize + 2 {
        for i in 0..((x1 - x0) / d) as usize + 2 {
            let (r, a) = (
                d / 20.0 * rng.random().sqrt(),
                2.0 * std::f64::consts::PI * rng.random(),
            );
            let q = [
                x0 + (i as f64 + 0.5 * (j % 2) as f64) * d + r * a.cos(),
                y0 + j as f64 * h + r * a.sin(),
            ];
            if contains(domain, q) {
                out.push(q);
            }
        }
    }
    out
}

/// The convex polygon `poly` cut to where `(x - m) . n <= 0`.
fn clip_half(poly: &[P], m: P, n: P) -> Vec<P> {
    let side = |q: P| (q[0] - m[0]) * n[0] + (q[1] - m[1]) * n[1];
    let mut out = Vec::with_capacity(poly.len() + 1);
    for i in 0..poly.len() {
        let (a, b) = (poly[i], poly[(i + 1) % poly.len()]);
        let (sa, sb) = (side(a), side(b));
        if sa <= 0.0 {
            out.push(a);
        }
        if (sa < 0.0 && sb > 0.0) || (sa > 0.0 && sb < 0.0) {
            out.push(add(a, scale(sub(b, a), sa / (sa - sb))));
        }
    }
    out
}

/// Each seed's Voronoi cell within `frame` (convex: its box cut by the bisectors with the
/// seeds near it), clipped by the domain (its pieces).
fn voronoi(seeds: &[P], domain: &Rings, frame: [f64; 4], d: f64, edges: &Segs) -> Vec<Vec<Rings>> {
    let reach = 4.0 * d;
    let grid = Grid::new(seeds, reach / 2.0, |_| true);
    pmap(seeds.len(), |i| {
        let s = seeds[i];
        let (x0, y0) = ((s[0] - reach).max(frame[0]), (s[1] - reach).max(frame[1]));
        let (x1, y1) = ((s[0] + reach).min(frame[2]), (s[1] + reach).min(frame[3]));
        let mut cell = vec![[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
        grid.within(s, 2.0 * reach, |j, _| {
            if j != i && cell.len() >= 3 {
                cell = clip_half(&cell, scale(add(s, seeds[j]), 0.5), sub(seeds[j], s));
            }
        });
        if cell.len() < 3 {
            return Vec::new();
        }
        // (inside the domain and no edge of it near: the cell as it is)
        let lo = cell.iter().fold([f64::MAX, f64::MAX], |m, q| {
            [m[0].min(q[0]), m[1].min(q[1])]
        });
        let hi = cell.iter().fold([f64::MIN, f64::MIN], |m, q| {
            [m[0].max(q[0]), m[1].max(q[1])]
        });
        let mut near = false;
        edges.around(lo, hi, |_| near = true);
        if !near {
            return if contains(domain, centroid(&vec![cell.clone()])) {
                vec![vec![cell]]
            } else {
                Vec::new()
            };
        }
        intersection(&vec![cell], domain)
    })
}

/// A centroidal Voronoi tessellation of the domain (Lloyd iterations), cells clipped by it,
/// cells holding a hole split through it. Seeds at `pins` stay there.
pub fn cells(domain: &Rings, d: f64, rng: &mut Rng, pins: &[P], lloyd: usize) -> Vec<Rings> {
    let mut s = seeds(domain, d, rng);
    for &pin in pins {
        s.retain(|q| dist(*q, pin) > 0.75 * d);
        s.push(pin);
    }
    if s.len() < 2 {
        return split_holes(domain.clone());
    }
    let b = crate::poly::bounds(domain);
    let frame = [
        b[0] - 2.0 * d,
        b[1] - 2.0 * d,
        b[2] + 2.0 * d,
        b[3] + 2.0 * d,
    ];
    let (ea, eb): (Vec<P>, Vec<P>) = domain
        .iter()
        .flat_map(|r| (0..r.len()).map(move |i| (r[i], r[(i + 1) % r.len()])))
        .unzip();
    let edges = Segs::new(ea, eb, d);
    let mut pieces = Vec::new();
    for it in 0..=lloyd {
        if crate::cancelled() {
            break;
        }
        pieces = voronoi(&s, domain, frame, d, &edges);
        pieces.retain(|p: &Vec<Rings>| !p.is_empty());
        if it == lloyd {
            break;
        }
        s = pieces
            .iter()
            .map(|parts| {
                let part = parts
                    .iter()
                    .max_by(|a, b| area(a).total_cmp(&area(b)))
                    .unwrap();
                let c = centroid(part);
                if contains(domain, c) {
                    c
                } else {
                    inner_point(part)
                }
            })
            .collect();
        // (the pins where they were, the seeds that came near one since left out: else a
        // seed in a corner beside an exit's opening comes back each step, its cell's wall
        // across the opening)
        for &pin in pins {
            if let Some(k) =
                (0..s.len()).min_by(|&a, &b| dist(s[a], pin).total_cmp(&dist(s[b], pin)))
            {
                s[k] = pin;
            }
        }
        s.retain(|q| pins.contains(q) || pins.iter().all(|&pin| dist(*q, pin) > 0.75 * d));
    }
    pieces
        .into_iter()
        .flatten()
        .filter(|p| area(p) > 1e-9)
        .flat_map(split_holes)
        .collect()
}

/// The polygon cut so that no piece has a hole (a vertical cut through each).
fn split_holes(p: Rings) -> Vec<Rings> {
    if p.len() < 2 {
        return vec![p];
    }
    let cx = centroid(&vec![p[1].clone()])[0];
    let [x0, y0, x1, y1] = crate::poly::bounds(&p);
    let mut out = Vec::new();
    for half in [
        rect(x0 - 1.0, y0 - 1.0, cx, y1 + 1.0),
        rect(cx, y0 - 1.0, x1 + 1.0, y1 + 1.0),
    ] {
        for q in intersection(&p, &half) {
            out.extend(split_holes(q));
        }
    }
    out
}

/// The cells' edges and corners added to the graph.
fn build(g: &mut Graph, cells: Vec<Rings>, seg: usize) {
    for cell in cells {
        let mut ids: Vec<usize> = Vec::new();
        for &q in &cell[0] {
            let i = g.vertex(q, seg);
            if ids.last() != Some(&i) {
                ids.push(i);
            }
        }
        while ids.len() > 1 && ids[0] == ids[ids.len() - 1] {
            ids.pop();
        }
        if ids.len() < 3 {
            continue;
        }
        for k in 0..ids.len() {
            g.connect(ids[k], ids[(k + 1) % ids.len()]);
        }
        g.faces.push((ids, cell, seg));
    }
}

// ---------------------------------------------------------------------------- stem

/// The exit's stem in the graph: its two ends, on one edge along the rim of the segment
/// nearest them (which they split), the edge between them one the cycle must take.
fn stem(g: &mut Graph, segments: &[Segment], opening: [P; 2]) -> Result<(usize, usize), Retry> {
    let seg = (0..segments.len())
        .min_by(|&i, &j| {
            distance(&segments[i].domain, opening[0])
                .total_cmp(&distance(&segments[j].domain, opening[0]))
        })
        .unwrap();
    let mut count: HashMap<Edge, usize> = HashMap::new();
    let mut order: Vec<Edge> = Vec::new();
    for (ids, _, si) in &g.faces {
        if *si == seg {
            for k in 0..ids.len() {
                let e = key(ids[k], ids[(k + 1) % ids.len()]);
                let c = count.entry(e).or_insert(0);
                if *c == 0 {
                    order.push(e);
                }
                *c += 1;
            }
        }
    }
    let rim: Vec<Edge> = order.into_iter().filter(|e| count[e] == 1).collect();
    if rim.is_empty() {
        return Err(Retry);
    }
    let gap = |e: &Edge, q: P| dist(closest(q, g.pts[e.0], g.pts[e.1]).0, q);
    // (the edge nearest both ends: an end on a corner is as near the next edge too)
    let both = |e: &Edge| gap(e, opening[0]).max(gap(e, opening[1]));
    let near = (0..rim.len())
        .min_by(|&i, &j| both(&rim[i]).total_cmp(&both(&rim[j])))
        .unwrap();
    if both(&rim[near]) > 1e-6 {
        return Err(Retry); // (a cell wall between the ends, or the opening off the rim)
    }
    let (x, y) = rim[near];
    let (px, py) = (g.pts[x], g.pts[y]);
    let len = dist(px, py);
    let t: Vec<f64> = opening
        .iter()
        .map(|&q| closest(q, px, py).1 * len)
        .collect();
    // (an end on the edge's corner: that corner, as where the opening is just as wide as
    // the segment there; else a vertex splitting the edge)
    let eps = 1e-6;
    let along = |ti: f64| add(px, scale(sub(py, px), ti / len.max(1e-12)));
    let mut end = |ti: f64| {
        if ti <= eps {
            x
        } else if ti >= len - eps {
            y
        } else {
            g.add(along(ti), seg)
        }
    };
    let (a, b) = (end(t[0]), end(t[1]));
    if a == b {
        return Err(Retry);
    }
    let order = if t[0] < t[1] {
        [x, a, b, y]
    } else {
        [x, b, a, y]
    };
    let chain: Vec<usize> = order.into_iter().fold(Vec::new(), |mut c, v| {
        if c.last() != Some(&v) {
            c.push(v);
        }
        c
    });
    if chain.len() > 2 {
        g.adj[x].remove(&y);
        g.adj[y].remove(&x);
        for w in chain.windows(2) {
            g.connect(w[0], w[1]);
        }
        for (ids, _, _) in g.faces.iter_mut() {
            // (the cell along that edge: through the new vertices)
            let n = ids.len();
            if let Some(j) = (0..n).find(|&j| key(ids[j], ids[(j + 1) % n]) == key(x, y)) {
                let inner = &chain[1..chain.len() - 1];
                let ins: Vec<usize> = if ids[j] == x {
                    inner.to_vec()
                } else {
                    inner.iter().rev().copied().collect()
                };
                ids.splice(j + 1..j + 1, ins);
                break;
            }
        }
    }
    g.fixed.insert(key(a, b));
    Ok((a, b))
}

// ---------------------------------------------------------------------------- matching

/// A maximum matching (Edmonds' blossom algorithm), greedy start: `mate` per vertex.
fn matching(n: usize, nbrs: &[Vec<usize>], rng: &mut Rng) -> Vec<Option<usize>> {
    const NO: usize = usize::MAX;
    let mut mate = vec![NO; n];
    let mut order: Vec<usize> = (0..n).collect();
    rng.shuffle(&mut order);
    for &v in &order {
        if mate[v] == NO {
            if let Some(&u) = nbrs[v].iter().find(|&&u| mate[u] == NO && u != v) {
                mate[v] = u;
                mate[u] = v;
            }
        }
    }
    let mut base: Vec<usize> = (0..n).collect();
    let mut parent = vec![NO; n];
    let mut used = vec![false; n];
    let mut blossom = vec![false; n];
    let lca = |a0: usize, b0: usize, base: &[usize], mate: &[usize], parent: &[usize]| -> usize {
        let mut seen = HashSet::new();
        let mut a = a0;
        loop {
            a = base[a];
            seen.insert(a);
            if mate[a] == NO {
                break;
            }
            a = parent[mate[a]];
        }
        let mut b = b0;
        loop {
            b = base[b];
            if seen.contains(&b) {
                return b;
            }
            b = parent[mate[b]];
        }
    };
    let mark = |mut v: usize,
                b: usize,
                mut child: usize,
                base: &[usize],
                mate: &[usize],
                parent: &mut [usize],
                blossom: &mut [bool]| {
        while base[v] != b {
            blossom[base[v]] = true;
            blossom[base[mate[v]]] = true;
            parent[v] = child;
            child = mate[v];
            v = parent[mate[v]];
        }
    };
    for &root in &order {
        if mate[root] != NO {
            continue;
        }
        let mut touched = vec![root];
        used[root] = true;
        let mut queue = VecDeque::from([root]);
        let mut end = NO;
        'search: while let Some(v) = queue.pop_front() {
            for &u in &nbrs[v] {
                if base[v] == base[u] || mate[v] == u || u == v {
                    continue;
                }
                if u == root || (mate[u] != NO && parent[mate[u]] != NO) {
                    let b = lca(v, u, &base, &mate, &parent);
                    mark(v, b, u, &base, &mate, &mut parent, &mut blossom);
                    mark(u, b, v, &base, &mate, &mut parent, &mut blossom);
                    for &i in &touched {
                        if blossom[base[i]] {
                            base[i] = b;
                            if !used[i] {
                                used[i] = true;
                                queue.push_back(i);
                            }
                        }
                    }
                    for &i in &touched {
                        blossom[i] = false;
                    }
                } else if parent[u] == NO {
                    parent[u] = v;
                    touched.push(u);
                    if mate[u] == NO {
                        end = u;
                        break 'search;
                    }
                    used[mate[u]] = true;
                    touched.push(mate[u]);
                    queue.push_back(mate[u]);
                }
            }
        }
        let mut v = end;
        while v != NO {
            let pv = parent[v];
            let nxt = mate[pv];
            mate[v] = pv;
            mate[pv] = v;
            v = nxt;
        }
        for &i in &touched {
            used[i] = false;
            parent[i] = NO;
            base[i] = i;
        }
    }
    mate.into_iter().map(|m| (m != NO).then_some(m)).collect()
}

fn ring(g: &Graph, v: usize) -> Vec<usize> {
    let (mut out, mut prev, mut here) = (vec![v], usize::MAX, v);
    loop {
        let nxt = g.adj[here].iter().copied().find(|&x| x != prev);
        match nxt {
            Some(n) if n != v && g.adj[here].len() == 2 => {
                out.push(n);
                prev = here;
                here = n;
            }
            _ => return out,
        }
    }
}

/// Cycle links covering every vertex of degree three: the edges a perfect matching leaves
/// out (section 3.3.1); chains of degree-two vertices act as one edge.
fn two_factor(g: &mut Graph, rng: &mut Rng) -> Result<(), Retry> {
    let deg: Vec<usize> = g.adj.iter().map(|a| a.len()).collect();
    if deg.iter().any(|&k| k > 3) {
        return Err(Retry);
    }
    let cubic: Vec<usize> = (0..deg.len()).filter(|&i| deg[i] == 3).collect();
    let index: HashMap<usize, usize> = cubic.iter().enumerate().map(|(j, &v)| (v, j)).collect();
    let mut chains: Vec<Vec<usize>> = Vec::new();
    let mut seen: HashSet<Edge> = HashSet::new();
    for &u in &cubic {
        for &w in &g.adj[u] {
            if seen.contains(&(u, w)) {
                continue;
            }
            let (mut chain, mut prev, mut here) = (vec![u, w], u, w);
            while deg[here] == 2 {
                let nxt = *g.adj[here].iter().find(|&&x| x != prev).unwrap();
                prev = here;
                here = nxt;
                chain.push(here);
            }
            seen.insert((u, w));
            seen.insert((here, prev));
            chains.push(chain);
        }
    }
    let held: Vec<bool> = chains
        .iter()
        .map(|c| c.windows(2).any(|w| g.fixed.contains(&key(w[0], w[1]))))
        .collect();
    let mut nbrs = vec![Vec::new(); cubic.len()];
    for (c, &keep) in chains.iter().zip(&held) {
        if c[0] != c[c.len() - 1] && !keep {
            let (a, b) = (index[&c[0]], index[&c[c.len() - 1]]);
            nbrs[a].push(b);
            nbrs[b].push(a);
        }
    }
    let mate = matching(cubic.len(), &nbrs, rng);
    if mate.iter().any(|m| m.is_none()) {
        return Err(Retry);
    }
    let mut matched: HashSet<Edge> = HashSet::new();
    for (c, &keep) in chains.iter().zip(&held) {
        let (a, b) = (c[0], c[c.len() - 1]);
        if a != b && !keep && cubic[mate[index[&a]].unwrap()] == b && matched.insert(key(a, b)) {
            continue;
        }
        for w in c.windows(2) {
            g.link(w[0], w[1]);
        }
    }
    // (rings of degree-two vertices only: a cycle by themselves)
    for v in 0..deg.len() {
        if deg[v] == 2 && g.nbr[v].is_empty() {
            let r = ring(g, v);
            if !r.iter().any(|&u| deg[u] == 3) {
                for k in 0..r.len() {
                    g.link(r[k], r[(k + 1) % r.len()]);
                }
            }
        }
    }
    if cubic.iter().any(|&u| g.nbr[u].len() != 2) {
        return Err(Retry);
    }
    Ok(())
}

// ---------------------------------------------------------------------------- refinement

/// Whether the segment from `c` to `v` lies within the polygon (within a hair of it).
fn covers(p: &Rings, c: P, v: P) -> bool {
    let e = sub(v, c);
    let mut ts = vec![0.0, 1.0];
    for r in p {
        for i in 0..r.len() {
            let (a, b) = (r[i], r[(i + 1) % r.len()]);
            let f = sub(b, a);
            let den = cross(e, f);
            if den.abs() < 1e-18 {
                continue;
            }
            let w = sub(a, c);
            let t = cross(w, f) / den;
            let s = cross(w, e) / den;
            if (0.0..=1.0).contains(&t) && (-1e-9..=1.0 + 1e-9).contains(&s) {
                ts.push(t);
            }
        }
    }
    ts.sort_by(f64::total_cmp);
    ts.windows(2).all(|w| {
        let m = add(c, scale(e, (w[0] + w[1]) / 2.0));
        w[1] - w[0] < 1e-12 || contains(p, m) || boundary_distance(p, m) <= 1e-7
    })
}

/// A vertex at each cell's centre, joined to the corners it sees; each threaded into one
/// cycle edge along its cell (section 3.3.2: a bipartite matching of cells to edges).
fn centres(g: &mut Graph) {
    let cen: Vec<P> = g.faces.iter().map(|f| centroid(&f.1)).collect();
    let sees: Vec<BTreeSet<usize>> = pmap(g.faces.len(), |fi| {
        let (ids, poly, _) = &g.faces[fi];
        if !contains(poly, cen[fi]) {
            return BTreeSet::new();
        }
        ids.iter()
            .copied()
            .filter(|&v| covers(poly, cen[fi], g.pts[v]))
            .collect()
    });
    let mut cands: Vec<(usize, Vec<Edge>)> = Vec::new();
    for (fi, vs) in sees.iter().enumerate() {
        if vs.iter().filter(|&&v| !g.nbr[v].is_empty()).count() < 3 {
            continue;
        }
        let ids = &g.faces[fi].0;
        let es: Vec<Edge> = (0..ids.len())
            .map(|k| (ids[k], ids[(k + 1) % ids.len()]))
            .filter(|&(a, b)| vs.contains(&a) && vs.contains(&b) && g.nbr[a].contains(&b))
            // (the centre across the edge from inside, not off beyond one of its ends: the
            // detour a - c - b would fold back on itself)
            .filter(|&(a, b)| {
                let t = closest(cen[fi], g.pts[a], g.pts[b]).1;
                t > 0.0 && t < 1.0
            })
            .map(|(a, b)| key(a, b))
            .filter(|e| !g.fixed.contains(e))
            .collect();
        if !es.is_empty() {
            cands.push((fi, es));
        }
    }
    let mut owner: HashMap<Edge, usize> = HashMap::new();
    let mut chosen: Vec<Option<Edge>> = vec![None; cands.len()];
    let mut first: Vec<usize> = Vec::new(); // (the order the cells were first given an edge)
    for start in 0..cands.len() {
        // augmenting paths (BFS) over cells and their edges
        let mut prev: HashMap<usize, Option<(usize, Edge)>> = HashMap::from([(start, None)]);
        let mut queue = VecDeque::from([start]);
        let mut end = None;
        while let (Some(f), None) = (queue.pop_front(), end) {
            for &e in &cands[f].1 {
                match owner.get(&e) {
                    None => {
                        end = Some((f, e));
                        break;
                    }
                    Some(&o) if !prev.contains_key(&o) => {
                        prev.insert(o, Some((f, e)));
                        queue.push_back(o);
                    }
                    _ => {}
                }
            }
        }
        let Some((mut f, mut e)) = end else { continue };
        loop {
            owner.insert(e, f);
            if chosen[f].is_none() {
                first.push(f);
            }
            chosen[f] = Some(e);
            match prev[&f] {
                None => break,
                Some((pf, pe)) => {
                    f = pf;
                    e = pe;
                }
            }
        }
    }
    for f in first {
        let fi = cands[f].0;
        let (a, b) = chosen[f].unwrap();
        let c = g.add(cen[fi], g.faces[fi].2);
        g.unlink(a, b);
        g.link(a, c);
        g.link(c, b);
        for &v in &sees[fi] {
            g.connect(c, v);
        }
    }
}

struct Union(Vec<usize>);

impl Union {
    fn new(n: usize) -> Union {
        Union((0..n).collect())
    }

    fn find(&mut self, mut a: usize) -> usize {
        while self.0[a] != a {
            self.0[a] = self.0[self.0[a]];
            a = self.0[a];
        }
        a
    }

    fn join(&mut self, a: usize, b: usize) -> bool {
        let (a, b) = (self.find(a), self.find(b));
        if a == b {
            return false;
        }
        self.0[b] = a;
        true
    }

    fn grow(&mut self, n: usize) {
        let m = self.0.len();
        self.0.extend(m..n);
    }
}

/// Join the cycles of each segment into one: split-and-reconnect where two cycle edges face
/// each other across a quad of graph edges, then doubled edges (section 3.3.2).
fn merge(g: &mut Graph, u: &mut Union) {
    let mut changed = true;
    while changed {
        changed = false;
        for x1 in 0..g.pts.len() {
            let around = g.nbr[x1].clone();
            for x2 in around {
                if g.fixed.contains(&key(x1, x2)) || !g.nbr[x1].contains(&x2) {
                    continue;
                }
                let ys: Vec<usize> = g.adj[x1].iter().copied().collect();
                for y1 in ys {
                    if g.nbr[y1].is_empty() || u.find(y1) == u.find(x1) {
                        continue;
                    }
                    let Some(y2) = g.nbr[y1].iter().copied().find(|y| g.adj[x2].contains(y)) else {
                        continue;
                    };
                    if g.fixed.contains(&key(y1, y2)) {
                        continue;
                    }
                    g.unlink(x1, x2);
                    g.unlink(y1, y2);
                    g.link(x1, y1);
                    g.link(x2, y2);
                    u.join(x1, y1);
                    changed = true;
                    break;
                }
            }
        }
    }
    for x in 0..g.pts.len() {
        // what is left: double a graph edge between two cycles
        if g.nbr[x].is_empty() {
            continue;
        }
        let ys: Vec<usize> = g.adj[x].iter().copied().collect();
        for y in ys {
            if !g.nbr[y].is_empty()
                && g.seg[y] == g.seg[x]
                && u.find(x) != u.find(y)
                && double(g, x, y)
            {
                u.grow(g.pts.len());
                u.join(x, y);
                u.join(x, g.pts.len() - 1);
                u.join(x, g.pts.len() - 2);
            }
        }
    }
}

/// Join the cycles through `u` and `v` by doubling the edge between them (paper figure 8).
fn double(g: &mut Graph, u: usize, v: usize) -> bool {
    let (pu, pv) = (g.pts[u], g.pts[v]);
    let side = |w: P| cross(sub(pv, pu), sub(w, pu));
    for sign in [1.0, -1.0] {
        let q = g.nbr[u]
            .iter()
            .copied()
            .find(|&w| sign * side(g.pts[w]) > 1e-9 && !g.fixed.contains(&key(u, w)));
        let r = g.nbr[v]
            .iter()
            .copied()
            .find(|&w| sign * side(g.pts[w]) > 1e-9 && !g.fixed.contains(&key(v, w)));
        let (Some(q), Some(r)) = (q, r) else { continue };
        let a = add(pu, scale(sub(g.pts[q], pu), 0.25));
        let b = add(pv, scale(sub(g.pts[r], pv), 0.25));
        let mut around: BTreeSet<usize> = BTreeSet::new();
        for x in [u, v, q, r] {
            around.insert(x);
            around.extend(g.adj[x].iter().copied());
        }
        let blocked = around.iter().any(|&x| {
            g.nbr[x]
                .iter()
                .any(|&y| x < y && crate::geom::crosses(a, b, g.pts[x], g.pts[y]))
        });
        if blocked {
            continue;
        }
        let u2 = g.add(a, g.seg[u]);
        let v2 = g.add(b, g.seg[v]);
        g.unlink(u, q);
        g.unlink(v, r);
        g.link(u, v);
        g.link(u2, v2);
        g.link(u2, q);
        g.link(v2, r);
        return true;
    }
    false
}

// ---------------------------------------------------------------------------- zoning

fn polyline_length(line: &[P]) -> f64 {
    line.windows(2).map(|w| dist(w[0], w[1])).sum()
}

/// How far along the polyline its point nearest `q` is, and how far `q` is from it.
fn project(line: &[P], q: P) -> (f64, f64) {
    let (mut best, mut at, mut run) = (f64::MAX, 0.0, 0.0);
    for w in line.windows(2) {
        let (c, t) = closest(q, w[0], w[1]);
        let d = dist(c, q);
        let l = dist(w[0], w[1]);
        if d < best {
            best = d;
            at = run + t * l;
        }
        run += l;
    }
    (at, best)
}

/// How far along the polyline the segment `p`-`q` crosses it (the first crossing), if it does.
fn crosses_at(line: &[P], p: P, q: P) -> Option<f64> {
    let mut run = 0.0;
    for w in line.windows(2) {
        let (a, b) = (w[0], w[1]);
        let (d, e) = (sub(q, p), sub(b, a));
        let den = cross(d, e);
        if den.abs() > 1e-12 {
            let f = sub(a, p);
            let (t, k) = (cross(f, e) / den, cross(f, d) / den);
            if (0.0..=1.0).contains(&t) && (0.0..=1.0).contains(&k) {
                return Some(run + k * dist(a, b));
            }
        }
        run += dist(a, b);
    }
    None
}

/// Whether segments `a`-`b` and `c`-`d` meet (touching counts).
fn meet(a: P, b: P, c: P, d: P) -> bool {
    let o = |p: P, q: P, r: P| {
        let v = cross(sub(q, p), sub(r, p));
        if v.abs() < 1e-15 {
            0.0
        } else {
            v.signum()
        }
    };
    // (`r`, on the line through `p` and `q`, within their box)
    let on = |p: P, q: P, r: P| {
        let (x0, x1) = (p[0].min(q[0]), p[0].max(q[0]));
        let (y0, y1) = (p[1].min(q[1]), p[1].max(q[1]));
        r[0] >= x0 - 1e-12 && r[0] <= x1 + 1e-12 && r[1] >= y0 - 1e-12 && r[1] <= y1 + 1e-12
    };
    let (o1, o2, o3, o4) = (o(a, b, c), o(a, b, d), o(c, d, a), o(c, d, b));
    if o1 * o2 < 0.0 && o3 * o4 < 0.0 {
        return true;
    }
    (o1 == 0.0 && on(a, b, c))
        || (o2 == 0.0 && on(a, b, d))
        || (o3 == 0.0 && on(c, d, a))
        || (o4 == 0.0 && on(c, d, b))
}

/// Join the segments' cycles along a spanning tree of the regions that share a border
/// (longest borders first): each join one split-and-reconnect across the border.
fn join_segments(
    g: &mut Graph,
    u: &mut Union,
    segments: &[Segment],
    borders: &[(usize, usize, Vec<Vec<P>>)],
    spacing: f64,
) {
    let mut by_region: HashMap<usize, Vec<usize>> = HashMap::new();
    for v in 0..g.pts.len() {
        if !g.nbr[v].is_empty() {
            by_region
                .entry(segments[g.seg[v]].region)
                .or_default()
                .push(v);
        }
    }
    let none = Vec::new();
    for (ri, rj, lines) in borders {
        // (one join a pair, but more where a region's cycles are not yet all of a piece:
        // each as it comes, while one can be made)
        let mut va = by_region.get(ri).unwrap_or(&none).clone();
        let mut vb = by_region.get(rj).unwrap_or(&none).clone();
        // (a cycle edge along the border running into its ends, as a small region's one cell
        // has: split where the ends' margins begin, so its middle can take the join)
        for line in lines {
            let length = polyline_length(line);
            if length >= 2.0 * spacing {
                let end = (2.0 * spacing).min(length / 6.0);
                for vs in [&mut va, &mut vb] {
                    split_at(g, u, segments, vs, line, spacing, &[end, length - end]);
                }
            }
        }
        by_region.insert(*ri, va.clone());
        by_region.insert(*rj, vb.clone());
        let roots = |u: &mut Union, vs: &[usize]| {
            let mut r: Vec<usize> = vs.iter().map(|&v| u.find(v)).collect();
            r.sort_unstable();
            r.dedup();
            r.len()
        };
        for _ in 0..roots(u, &va) + roots(u, &vb) {
            let joined = lines.iter().any(|line| {
                polyline_length(line) >= 2.0 * spacing
                    && connect(g, u, segments, &va, &vb, line, spacing)
            });
            if !joined {
                break;
            }
        }
    }
}

/// Split the cycle edges of `vs` that run along their domain's boundary within `near` of
/// `line` across any of the positions `cuts` along it (each at its projection there), the
/// new vertices added to `vs`.
fn split_at(
    g: &mut Graph,
    u: &mut Union,
    segments: &[Segment],
    vs: &mut Vec<usize>,
    line: &[P],
    near: f64,
    cuts: &[f64],
) {
    for &cut in cuts {
        let mut edges = Vec::new();
        for &a in vs.iter() {
            for &b in &g.nbr[a] {
                if a > b || g.fixed.contains(&(a, b)) || g.seg[a] != g.seg[b] {
                    continue;
                }
                let (pa, pb) = (g.pts[a], g.pts[b]);
                let (sa, da) = project(line, pa);
                let (sb, db) = project(line, pb);
                if da.max(db) > near
                    || boundary_distance(&segments[g.seg[a]].domain, scale(add(pa, pb), 0.5)) > 1e-6
                {
                    continue;
                }
                let (lo, hi) = (sa.min(sb), sa.max(sb));
                // (both pieces worth keeping)
                if lo + 0.05 * near < cut && cut < hi - 0.05 * near {
                    edges.push((a, b, (cut - sa) / (sb - sa)));
                }
            }
        }
        for (a, b, t) in edges {
            let p = add(g.pts[a], scale(sub(g.pts[b], g.pts[a]), t));
            let v = g.add(p, g.seg[a]);
            u.grow(g.pts.len());
            u.join(a, v);
            g.unlink(a, b);
            g.link(a, v);
            g.link(v, b);
            vs.push(v);
        }
    }
}

/// One split-and-reconnect across the border `line` between two cycle edges (of cycles not
/// yet joined) facing each other across it, away from the border's ends: the shortest joins,
/// nearest the border's middle; the joins cross no edge of the curve.
fn connect(
    g: &mut Graph,
    u: &mut Union,
    segments: &[Segment],
    va: &[usize],
    vb: &[usize],
    line: &[P],
    spacing: f64,
) -> bool {
    let length = polyline_length(line);
    let end = (2.0 * spacing).min(length / 6.0);
    let cycle: Vec<Edge> = (0..g.pts.len())
        .flat_map(|a| {
            g.nbr[a]
                .iter()
                .filter(move |&&b| a < b)
                .map(move |&b| (a, b))
        })
        .collect();
    let tree = Segs::new(
        cycle.iter().map(|e| g.pts[e.0]).collect(),
        cycle.iter().map(|e| g.pts[e.1]).collect(),
        spacing,
    );
    let mid = length / 2.0;
    // (the last pass: edges anywhere near the border, ends' margins or not, as long as both
    // joins cross it away from its ends; a run that keeps to the border's far end, where its
    // narrow region leaves room, reaches a small region's cycle across its middle)
    for (along, near, reach, crossing) in [
        (true, 1.0, 2.0, false),
        (false, 1.8, 2.6, false),
        (false, 1.8, 2.6, true),
    ] {
        let margin = if crossing { 0.0 } else { end };
        let ea = border_edges(g, segments, va, line, near * spacing, margin, along);
        let eb = border_edges(g, segments, vb, line, near * spacing, margin, along);
        let mut cands: Vec<(f64, usize, usize, usize, usize)> = Vec::new();
        for &(a1, a2, s1, s2) in &ea {
            for &(b1, b2, t1, t2) in &eb {
                if u.find(a1) == u.find(b1) {
                    continue;
                }
                let inside = |p: P, q: P| {
                    crosses_at(line, p, q).is_some_and(|s| end <= s && s <= length - end)
                };
                if crossing {
                    if !(inside(g.pts[a1], g.pts[b1]) && inside(g.pts[a2], g.pts[b2])) {
                        continue;
                    }
                } else if s2.min(t2) - s1.max(t1) < 0.1 * spacing {
                    continue;
                }
                let (l1, l2) = (dist(g.pts[a1], g.pts[b1]), dist(g.pts[a2], g.pts[b2]));
                if l1.max(l2) <= reach * spacing {
                    cands.push((
                        l1 + l2 + 0.05 * ((s1 + s2) / 2.0 - mid).abs(),
                        a1,
                        a2,
                        b1,
                        b2,
                    ));
                }
            }
        }
        cands.sort_by(|x, y| {
            x.0.total_cmp(&y.0)
                .then((x.1, x.2, x.3, x.4).cmp(&(y.1, y.2, y.3, y.4)))
        });
        for &(_, a1, a2, b1, b2) in cands.iter().take(100) {
            let ends = [(a1, b1), (a2, b2)];
            let (j0, j1) = ((g.pts[a1], g.pts[b1]), (g.pts[a2], g.pts[b2]));
            if meet(j0.0, j0.1, j1.0, j1.1) {
                continue;
            }
            let mut blocked = false;
            for (e, j) in ends.iter().zip([j0, j1]) {
                tree.around(j.0, j.1, |i| {
                    let c = cycle[i];
                    if c.0 != e.0
                        && c.0 != e.1
                        && c.1 != e.0
                        && c.1 != e.1
                        && meet(j.0, j.1, g.pts[c.0], g.pts[c.1])
                    {
                        blocked = true;
                    }
                });
            }
            if blocked {
                continue;
            }
            g.unlink(a1, a2);
            g.unlink(b1, b2);
            g.link(a1, b1);
            g.link(a2, b2);
            u.join(a1, b1);
            return true;
        }
    }
    false
}

/// The cycle edges among `vs` within `near` of `line` and `end` from its ends (`along`: only
/// those along their segment's edge), each with its ends' places along the line, in order.
fn border_edges(
    g: &Graph,
    segments: &[Segment],
    vs: &[usize],
    line: &[P],
    near: f64,
    end: f64,
    along: bool,
) -> Vec<(usize, usize, f64, f64)> {
    let length = polyline_length(line);
    let keep: Vec<usize> = vs
        .iter()
        .copied()
        .filter(|&v| project(line, g.pts[v]).1 <= near)
        .collect();
    let kept: HashSet<usize> = keep.iter().copied().collect();
    let mut out = Vec::new();
    for &a in &keep {
        for &b in &g.nbr[a] {
            if a > b || !kept.contains(&b) || g.fixed.contains(&(a, b)) {
                continue;
            }
            let (pa, pb) = (g.pts[a], g.pts[b]);
            if along
                && (g.seg[a] != g.seg[b]
                    || boundary_distance(&segments[g.seg[a]].domain, scale(add(pa, pb), 0.5))
                        > 1e-6)
            {
                continue;
            }
            let (sa, sb) = (project(line, pa).0, project(line, pb).0);
            // (a little past the ends' margins is clear enough: an edge further past them is
            // split there first, `split_at`)
            let slack = 0.1 * near;
            if sa.min(sb) < end - slack || sa.max(sb) > length - end + slack {
                continue;
            }
            out.push(if sa <= sb {
                (a, b, sa, sb)
            } else {
                (b, a, sb, sa)
            });
        }
    }
    out
}
