//! The settling in the browser (wasm-bindgen): the Pyodide worker loads this beside Python,
//! and `sfc._settle` calls `settle` through Pyodide's bridge. Flat typed arrays in and out
//! (points as x, y, x, y, ...), the constants by name, progress to a JS function.

use js_sys::{Array, Float64Array, Function, Object, Reflect, Uint32Array};
use wasm_bindgen::prelude::*;
use yanartas_mesh_core::arcs::{fit, Piece};
use yanartas_mesh_core::curve::{relax, CurveInput, CurveParams};
use yanartas_mesh_core::graph::{curve, GraphInput, GraphParams, Segment};
use yanartas_mesh_core::lanes::{lanes, LaneParams};
use yanartas_mesh_core::{geom::P, settle as settle_core, Input, Params, Status};

fn points(flat: &[f64]) -> Vec<P> {
    flat.chunks_exact(2).map(|c| [c[0], c[1]]).collect()
}

/// `flat` cut into consecutive runs of `lens` points.
fn runs(flat: &[f64], lens: &[u32]) -> Vec<Vec<P>> {
    let mut at = 0;
    lens.iter()
        .map(|&n| {
            let run = points(&flat[2 * at..2 * (at + n as usize)]);
            at += n as usize;
            run
        })
        .collect()
}

fn params(obj: &JsValue) -> Result<Params, JsValue> {
    let mut p = Params::default();
    let num = |name: &str| -> Result<Option<f64>, JsValue> {
        Ok(Reflect::get(obj, &name.into())?.as_f64())
    };
    macro_rules! take {
        ($($field:ident: $t:ty),*) => {$(
            if let Some(v) = num(stringify!($field))? {
                p.$field = v as $t;
            }
        )*};
    }
    take!(
        steps: usize, rate: f64, reach: f64, pin: f64, cool: f64, step: f64, still: f64,
        band: f64, leap: f64, tune: f64, steer: f64, span: usize, steer_cool: f64, tip: f64,
        reach_out: f64, fill: f64, fill_blur: f64, bend: usize, smooth: usize, finish: usize, match_steps: usize, match_band: f64, match_rate: f64
    );
    Ok(p)
}

fn status(s: &Status) -> Result<Object, JsValue> {
    let o = Object::new();
    Reflect::set(&o, &"phase".into(), &s.phase.into())?;
    for (k, v) in [
        ("step", s.step),
        ("steps", s.steps),
        ("vertices", s.vertices),
        ("looked", s.looked),
        ("moved", s.moved),
        ("checked", s.checked),
    ] {
        Reflect::set(&o, &k.into(), &(v as f64).into())?;
    }
    let apart: Array = s.apart.iter().map(|&a| JsValue::from_f64(a)).collect();
    Reflect::set(&o, &"apart".into(), &apart)?;
    Ok(o)
}

/// The traces settled and matched in length: `lines`/`line_lens` the traces' points and
/// counts, `edge` the edge's points, `zones`/`ring_lens`/`zone_rings` the zones' rings
/// (points, each ring's count, each zone's number of rings), `keep`/`keep_lens`/`keep_rings`
/// what is left as laid (the exit) alike,
/// `params` the constants by name, `progress` called with each step's figures. Returns
/// `{points, lens}`.
#[wasm_bindgen]
#[allow(clippy::too_many_arguments)]
pub fn settle(
    lines: &[f64],
    line_lens: &[u32],
    pitch: f64,
    edge: &[f64],
    zones: &[f64],
    ring_lens: &[u32],
    zone_rings: &[u32],
    keep: &[f64],
    keep_lens: &[u32],
    keep_rings: &[u32],
    params_obj: JsValue,
    progress: Option<Function>,
) -> Result<Object, JsValue> {
    let polygons = |pts: &[f64], lens: &[u32], counts: &[u32]| -> Vec<Vec<Vec<P>>> {
        let rings = runs(pts, lens);
        let mut at = 0;
        counts
            .iter()
            .map(|&n| {
                let z = rings[at..at + n as usize].to_vec();
                at += n as usize;
                z
            })
            .collect()
    };
    let zones = polygons(zones, ring_lens, zone_rings);
    let keep = polygons(keep, keep_lens, keep_rings);
    let input = Input {
        lines: runs(lines, line_lens),
        pitch,
        edge: points(edge),
        zones,
        keep,
    };
    let prm = params(&params_obj)?;
    let mut failed: Option<JsValue> = None;
    let out = settle_core(&input, &prm, &mut |s: &Status| {
        if let (Some(f), None) = (&progress, &failed) {
            if let Err(e) = status(s).and_then(|o| f.call1(&JsValue::NULL, &o)) {
                failed = Some(e);
            }
        }
    });
    if let Some(e) = failed {
        return Err(e);
    }
    let flat: Vec<f64> = out.iter().flatten().flat_map(|q| [q[0], q[1]]).collect();
    let lens: Vec<u32> = out.iter().map(|t| t.len() as u32).collect();
    let o = Object::new();
    Reflect::set(&o, &"points".into(), &Float64Array::from(flat.as_slice()))?;
    Reflect::set(&o, &"lens".into(), &Uint32Array::from(lens.as_slice()))?;
    Ok(o)
}

/// The zones (regions) from flat rings: `ring_lens` each ring's count, `zone_rings` each
/// zone's number of rings.
fn zones_of(points: &[f64], ring_lens: &[u32], zone_rings: &[u32]) -> Vec<Vec<Vec<P>>> {
    let rings = runs(points, ring_lens);
    let mut at = 0;
    zone_rings
        .iter()
        .map(|&n| {
            let z = rings[at..at + n as usize].to_vec();
            at += n as usize;
            z
        })
        .collect()
}

fn number(obj: &JsValue, name: &str) -> Result<Option<f64>, JsValue> {
    Ok(Reflect::get(obj, &name.into())?.as_f64())
}

/// The curve relaxed (`sfc._relax`; the Python extension's `relax_curve`): returns
/// `{points, k}`, the closed curve and the number of vertices before the stem's.
#[wasm_bindgen]
#[allow(clippy::too_many_arguments)]
pub fn relax_curve(
    curve: &[f64],
    stem: &[f64],
    regions: &[f64],
    ring_lens: &[u32],
    zone_rings: &[u32],
    target: f64,
    edge: &[f64],
    borders: &[f64],
    spacing: f64,
    least: f64,
    pitch: f64,
    offset: &[f64],
    params_obj: JsValue,
    progress: Option<Function>,
) -> Result<Object, JsValue> {
    let input = CurveInput {
        curve: points(curve),
        stem: points(stem),
        regions: zones_of(regions, ring_lens, zone_rings),
        target,
        edge: points(edge),
        borders: points(borders),
        spacing,
        least,
        pitch,
        offset: [offset[0], offset[1]],
    };
    let mut p = CurveParams::default();
    macro_rules! take {
        ($($field:ident: $t:ty),*) => {$(
            if let Some(v) = number(&params_obj, stringify!($field))? {
                p.$field = v as $t;
            }
        )*};
    }
    take!(lloyd_curve: usize, gain: f64, push_margin: f64, window: f64, bend_slack: f64,
        grow: usize, reach: f64, grow_rate: f64, hard: usize, stall: usize, repair: usize,
        inside: f64);
    let mut failed: Option<JsValue> = None;
    let (out, k) = relax(&input, &p, &mut |step, steps| {
        if let (Some(f), None) = (&progress, &failed) {
            if let Err(e) = f.call2(
                &JsValue::NULL,
                &(step as f64).into(),
                &(steps as f64).into(),
            ) {
                failed = Some(e);
            }
        }
    });
    if let Some(e) = failed {
        return Err(e);
    }
    let flat: Vec<f64> = out.iter().flat_map(|q| [q[0], q[1]]).collect();
    let o = Object::new();
    Reflect::set(&o, &"points".into(), &Float64Array::from(flat.as_slice()))?;
    Reflect::set(&o, &"k".into(), &(k as f64).into())?;
    Ok(o)
}

/// The traces round the closed curve (`sfc._lanes`; the extension's `offset_lanes`):
/// returns `{points, lens}`.
#[wasm_bindgen]
#[allow(clippy::too_many_arguments)]
pub fn offset_lanes(
    p: &[f64],
    k: usize,
    edge_a: &[f64],
    edge_b: &[f64],
    n: usize,
    pitch: f64,
    spacing: f64,
    exact: &[u8],
    params_obj: JsValue,
) -> Result<Object, JsValue> {
    let edge: Vec<[P; 2]> = points(edge_a)
        .into_iter()
        .zip(points(edge_b))
        .map(|(a, b)| [a, b])
        .collect();
    let exact: Vec<bool> = exact.iter().map(|&x| x != 0).collect();
    let mut q = LaneParams::default();
    macro_rules! take {
        ($($field:ident: $t:ty),*) => {$(
            if let Some(v) = number(&params_obj, stringify!($field))? {
                q.$field = v as $t;
            }
        )*};
    }
    take!(spread: f64, smooth: usize, fine: usize, ramp: f64, margin: f64, inside: f64,
        window: f64, straight: f64);
    let out = lanes(&points(p), k, &edge, n, pitch, spacing, &exact, &q);
    let flat: Vec<f64> = out.iter().flatten().flat_map(|q| [q[0], q[1]]).collect();
    let lens: Vec<u32> = out.iter().map(|t| t.len() as u32).collect();
    let o = Object::new();
    Reflect::set(&o, &"points".into(), &Float64Array::from(flat.as_slice()))?;
    Reflect::set(&o, &"lens".into(), &Uint32Array::from(lens.as_slice()))?;
    Ok(o)
}

/// The curve's graph walked into a curve (`sfc._curve`; the extension's `curve_graph`):
/// `seg_region` each segment's region, its domain's rings flat (`rings`, `ring_lens`,
/// `seg_rings`); the borders: `pairs` (region, region) flat, `pair_lines` each pair's
/// number of lines, the lines flat (`lines`, `line_lens`); the seed in two halves. Returns
/// `{points, region, cells, left}`.
#[wasm_bindgen]
#[allow(clippy::too_many_arguments)]
pub fn curve_graph(
    seg_region: &[u32],
    rings: &[f64],
    ring_lens: &[u32],
    seg_rings: &[u32],
    pairs: &[u32],
    pair_lines: &[u32],
    lines: &[f64],
    line_lens: &[u32],
    opening: &[f64],
    spacing: f64,
    seed_hi: u32,
    seed_lo: u32,
    params_obj: JsValue,
    progress: Option<Function>,
) -> Result<Object, JsValue> {
    let domains = zones_of(rings, ring_lens, seg_rings);
    let segments: Vec<Segment> = seg_region
        .iter()
        .zip(domains)
        .map(|(&r, domain)| Segment {
            region: r as usize,
            domain,
        })
        .collect();
    let all = runs(lines, line_lens);
    let mut at = 0;
    let borders: Vec<(usize, usize, Vec<Vec<P>>)> = pair_lines
        .iter()
        .enumerate()
        .map(|(k, &n)| {
            let ls = all[at..at + n as usize].to_vec();
            at += n as usize;
            (pairs[2 * k] as usize, pairs[2 * k + 1] as usize, ls)
        })
        .collect();
    let input = GraphInput {
        segments,
        borders,
        opening: [[opening[0], opening[1]], [opening[2], opening[3]]],
        spacing,
        seed: ((seed_hi as u64) << 32) | seed_lo as u64,
    };
    let mut p = GraphParams::default();
    if let Some(v) = number(&params_obj, "seed_spacing")? {
        p.seed_spacing = v;
    }
    if let Some(v) = number(&params_obj, "lloyd")? {
        p.lloyd = v as usize;
    }
    if let Some(v) = number(&params_obj, "attempts")? {
        p.attempts = v as usize;
    }
    let mut failed: Option<JsValue> = None;
    let out = curve(&input, &p, &mut |step, steps| {
        if let (Some(f), None) = (&progress, &failed) {
            if let Err(e) = f.call2(
                &JsValue::NULL,
                &(step as f64).into(),
                &(steps as f64).into(),
            ) {
                failed = Some(e);
            }
        }
    });
    if let Some(e) = failed {
        return Err(e);
    }
    let c = out.map_err(|e| JsValue::from_str(&e))?;
    let flat: Vec<f64> = c.pts.iter().flat_map(|q| [q[0], q[1]]).collect();
    let region: Vec<u32> = c.region.iter().map(|&r| r as u32).collect();
    let o = Object::new();
    Reflect::set(&o, &"points".into(), &Float64Array::from(flat.as_slice()))?;
    Reflect::set(&o, &"region".into(), &Uint32Array::from(region.as_slice()))?;
    Reflect::set(&o, &"cells".into(), &(c.cells as f64).into())?;
    Reflect::set(&o, &"left".into(), &(c.left as f64).into())?;
    Ok(o)
}

/// Each polyline (`lines`/`line_lens`) as lines and circular arcs within `tol` of it
/// (the extension's `fit_arcs`): `{rows, counts}`, seven numbers a piece (kind, start,
/// middle, end), each line's number of pieces.
#[wasm_bindgen]
pub fn fit_arcs(lines: &[f64], line_lens: &[u32], tol: f64) -> Result<Object, JsValue> {
    let mut rows = Vec::new();
    let mut counts = Vec::new();
    for line in runs(lines, line_lens) {
        let pieces = fit(&line, tol);
        counts.push(pieces.len() as u32);
        for p in pieces {
            rows.extend(match p {
                Piece::Line(a, b) => [
                    0.0,
                    a[0],
                    a[1],
                    (a[0] + b[0]) / 2.0,
                    (a[1] + b[1]) / 2.0,
                    b[0],
                    b[1],
                ],
                Piece::Arc(a, m, b) => [1.0, a[0], a[1], m[0], m[1], b[0], b[1]],
            });
        }
    }
    let o = Object::new();
    Reflect::set(&o, &"rows".into(), &Float64Array::from(rows.as_slice()))?;
    Reflect::set(&o, &"counts".into(), &Uint32Array::from(counts.as_slice()))?;
    Ok(o)
}
