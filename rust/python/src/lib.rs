//! `pillowbox_mesh`: the Rust settling as a Python extension (PyO3). `sfc._settle` calls
//! `settle` when this is installed, and its own numpy code otherwise.

use numpy::ndarray::Array2;
use numpy::{IntoPyArray, PyArray2, PyReadonlyArray2};
use pillowbox_mesh_core::{geom::P, settle, Input, Params, Status};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

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

#[pymodule]
fn pillowbox_mesh(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(settle_traces, m)?)?;
    Ok(())
}
