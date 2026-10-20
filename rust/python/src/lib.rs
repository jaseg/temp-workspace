//! `yanartas_mesh`: the Rust settling as a Python extension (PyO3). `sfc._settle` calls
//! `settle` when this is installed, and its own numpy code otherwise.

use numpy::ndarray::Array2;
use numpy::{IntoPyArray, PyArray2, PyReadonlyArray2};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use yanartas_mesh_core::curve::{relax, CurveInput, CurveParams};
use yanartas_mesh_core::lanes::{lanes, LaneParams};
use yanartas_mesh_core::{geom::P, settle, Input, Params, Status};

fn points(a: &PyReadonlyArray2<f64>) -> PyResult<Vec<P>> {
    let a = a.as_array();
    if a.ncols() != 2 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "points: an (n, 2) array",
        ));
    }
    Ok(a.rows().into_iter().map(|r| [r[0], r[1]]).collect())
}

fn read_params(d: &Bound<'_, PyDict>) -> PyResult<Params> {
    let mut p = Params::default();
    macro_rules! take {
        ($($field:ident),*) => {$(
            if let Some(v) = d.get_item(stringify!($field))? {
                p.$field = v.extract()?;
            }
        )*};
    }
    take!(
        steps,
        rate,
        reach,
        pin,
        cool,
        step,
        still,
        band,
        leap,
        tune,
        steer,
        span,
        steer_cool,
        tip,
        reach_out,
        match_steps,
        match_band,
        match_rate
    );
    Ok(p)
}

fn status<'py>(py: Python<'py>, s: &Status) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("phase", s.phase)?;
    d.set_item("step", s.step)?;
    d.set_item("steps", s.steps)?;
    d.set_item("vertices", s.vertices)?;
    d.set_item("looked", s.looked)?;
    d.set_item("moved", s.moved)?;
    d.set_item("checked", s.checked)?;
    d.set_item("apart", s.apart.clone())?;
    Ok(d)
}

/// The traces settled and matched in length (`sfc._settle`): `lines` the traces (each an
/// (n, 2) array), `edge` points along the edge, `zones` each zone's rings, `keep` the
/// exit's box (x0, y0, x1, y1), `params` the constants by name, `progress` called with a
/// dict after each step (phase, step, steps, vertices, looked, moved, checked, apart).
#[pyfunction]
#[pyo3(signature = (lines, pitch, edge, zones, keep, params, progress=None))]
#[allow(clippy::too_many_arguments)]
fn settle_traces<'py>(
    py: Python<'py>,
    lines: Vec<PyReadonlyArray2<'py, f64>>,
    pitch: f64,
    edge: PyReadonlyArray2<'py, f64>,
    zones: Vec<Vec<PyReadonlyArray2<'py, f64>>>,
    keep: (f64, f64, f64, f64),
    params: &Bound<'py, PyDict>,
    progress: Option<PyObject>,
) -> PyResult<Bound<'py, PyList>> {
    let input = Input {
        lines: lines.iter().map(points).collect::<PyResult<_>>()?,
        pitch,
        edge: points(&edge)?,
        zones: zones
            .iter()
            .map(|z| z.iter().map(points).collect::<PyResult<Vec<_>>>())
            .collect::<PyResult<_>>()?,
        keep: [keep.0, keep.1, keep.2, keep.3],
    };
    let prm = read_params(params)?;
    let mut failed: Option<PyErr> = None;
    let out = py.allow_threads(|| {
        settle(&input, &prm, &mut |s: &Status| {
            if failed.is_some() {
                return;
            }
            if let Some(cb) = &progress {
                Python::with_gil(|py| {
                    if let Err(e) = status(py, s).and_then(|d| cb.call1(py, (d,)).map(|_| ())) {
                        failed = Some(e);
                    }
                });
            }
        })
    });
    if let Some(e) = failed {
        return Err(e);
    }
    let arrays: Vec<Bound<'py, PyArray2<f64>>> = out
        .into_iter()
        .map(|t| {
            let flat: Vec<f64> = t.iter().flat_map(|q| [q[0], q[1]]).collect();
            Array2::from_shape_vec((t.len(), 2), flat)
                .expect("(n, 2)")
                .into_pyarray(py)
        })
        .collect();
    PyList::new(py, arrays)
}

fn array<'py>(py: Python<'py>, t: &[P]) -> Bound<'py, PyArray2<f64>> {
    let flat: Vec<f64> = t.iter().flat_map(|q| [q[0], q[1]]).collect();
    Array2::from_shape_vec((t.len(), 2), flat)
        .expect("(n, 2)")
        .into_pyarray(py)
}

macro_rules! read {
    ($d:expr, $p:expr, $($field:ident),*) => {$(
        if let Some(v) = $d.get_item(stringify!($field))? {
            $p.$field = v.extract()?;
        }
    )*};
}

/// The curve relaxed (`sfc._relax`): `curve` open from the tongue's left end round to its
/// right end, `tongue` closing it, `regions` each region's rings, `target` the length to
/// aim at, `edge`/`borders` points along the area's edge and the regions' borders,
/// `offset` the samples' offset, `params` the constants by name, `progress(step, steps)`.
/// Returns the closed curve (the tongue last) and the number of vertices before the tongue.
#[pyfunction]
#[pyo3(signature = (curve, tongue, regions, target, edge, borders, spacing, least, pitch, offset, params, progress=None))]
#[allow(clippy::too_many_arguments)]
fn relax_curve<'py>(
    py: Python<'py>,
    curve: PyReadonlyArray2<'py, f64>,
    tongue: PyReadonlyArray2<'py, f64>,
    regions: Vec<Vec<PyReadonlyArray2<'py, f64>>>,
    target: f64,
    edge: PyReadonlyArray2<'py, f64>,
    borders: PyReadonlyArray2<'py, f64>,
    spacing: f64,
    least: f64,
    pitch: f64,
    offset: (f64, f64),
    params: &Bound<'py, PyDict>,
    progress: Option<PyObject>,
) -> PyResult<(Bound<'py, PyArray2<f64>>, usize)> {
    let input = CurveInput {
        curve: points(&curve)?,
        tongue: points(&tongue)?,
        regions: regions
            .iter()
            .map(|z| z.iter().map(points).collect::<PyResult<Vec<_>>>())
            .collect::<PyResult<_>>()?,
        target,
        edge: points(&edge)?,
        borders: points(&borders)?,
        spacing,
        least,
        pitch,
        offset: [offset.0, offset.1],
    };
    let mut prm = CurveParams::default();
    read!(
        params,
        prm,
        lloyd_curve,
        gain,
        push_margin,
        window,
        bend_slack,
        grow,
        reach,
        grow_rate,
        hard,
        stall,
        repair,
        inside
    );
    let mut failed: Option<PyErr> = None;
    let (p, k) = py.allow_threads(|| {
        relax(&input, &prm, &mut |step, steps| {
            if let (Some(cb), None) = (&progress, &failed) {
                Python::with_gil(|py| {
                    if let Err(e) = cb.call1(py, (step, steps)) {
                        failed = Some(e);
                    }
                });
            }
        })
    });
    if let Some(e) = failed {
        return Err(e);
    }
    Ok((array(py, &p), k))
}

/// The `n` traces round the closed curve `p` (`sfc._lanes`): `k` the tongue's first vertex,
/// `edge_a`/`edge_b` the area's edge in short segments, `exact` the tongue's legs.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn offset_lanes<'py>(
    py: Python<'py>,
    p: PyReadonlyArray2<'py, f64>,
    k: usize,
    edge_a: PyReadonlyArray2<'py, f64>,
    edge_b: PyReadonlyArray2<'py, f64>,
    n: usize,
    pitch: f64,
    spacing: f64,
    exact: Vec<bool>,
    params: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyList>> {
    let p = points(&p)?;
    let edge: Vec<[P; 2]> = points(&edge_a)?
        .into_iter()
        .zip(points(&edge_b)?)
        .map(|(a, b)| [a, b])
        .collect();
    let mut prm = LaneParams::default();
    read!(params, prm, spread, smooth, fine, ramp, margin, inside, window, straight);
    let out = py.allow_threads(|| lanes(&p, k, &edge, n, pitch, spacing, &exact, &prm));
    PyList::new(py, out.iter().map(|t| array(py, t)))
}

#[pymodule]
fn yanartas_mesh(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(settle_traces, m)?)?;
    m.add_function(wrap_pyfunction!(relax_curve, m)?)?;
    m.add_function(wrap_pyfunction!(offset_lanes, m)?)?;
    Ok(())
}
