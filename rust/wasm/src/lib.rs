//! The settling in the browser (wasm-bindgen): the Pyodide worker loads this beside Python,
//! and `sfc._settle` calls `settle` through Pyodide's bridge. Flat typed arrays in and out
//! (points as x, y, x, y, ...), the constants by name, progress to a JS function.

use js_sys::{Array, Float64Array, Function, Object, Reflect, Uint32Array};
use pillowbox_mesh_core::{geom::P, settle as settle_core, Input, Params, Status};
use wasm_bindgen::prelude::*;

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
        reach_out: f64, match_steps: usize, match_band: f64, match_rate: f64
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
/// (points, each ring's count, each zone's number of rings), `keep` the exit's box,
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
    params_obj: JsValue,
    progress: Option<Function>,
) -> Result<Object, JsValue> {
    let rings = runs(zones, ring_lens);
    let mut at = 0;
    let zones: Vec<Vec<Vec<P>>> = zone_rings
        .iter()
        .map(|&n| {
            let z = rings[at..at + n as usize].to_vec();
            at += n as usize;
            z
        })
        .collect();
    if keep.len() != 4 {
        return Err("keep: a box (x0, y0, x1, y1)".into());
    }
    let input = Input {
        lines: runs(lines, line_lens),
        pitch,
        edge: points(edge),
        zones,
        keep: [keep[0], keep[1], keep[2], keep[3]],
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
