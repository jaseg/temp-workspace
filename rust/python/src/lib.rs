//! `yanartas_mesh`: the Rust settling as a Python extension (PyO3). `sfc._settle` calls
//! `settle` when this is installed, and its own numpy code otherwise.

use numpy::ndarray::Array2;
use numpy::{IntoPyArray, PyArray2, PyReadonlyArray2};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use yanartas_mesh_core::arcs::{fit, Piece};
use yanartas_mesh_core::curve::{relax, CurveInput, CurveParams};
use yanartas_mesh_core::graph::{curve, GraphInput, GraphParams, Segment};
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
        fill,
        fill_blur,
        bend,
        smooth,
        finish,
        match_steps,
        match_band,
        match_rate,
        ribbon,
        share,
        holes,
        hole_steps,
        hole_margin,
        hole_ribbon,
        phases
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
    d.set_item("filled", s.filled)?;
    Ok(d)
}

/// The traces settled and matched in length (`sfc._settle`): `lines` the traces (each an
/// (n, 2) array), `edge` points along the edge, `zones` each zone's rings, `keep` what is
/// left as laid (the exits: polygons, each its rings), `params` the constants by name,
/// `progress` called with a dict after each step (phase, step, steps, vertices, looked,
/// moved, checked, apart, filled), `groups` each trace's group (lengths matched within it),
/// `base` the traces as first laid (when a later phase is run on its own: `params`' `phases`).
#[pyfunction]
#[pyo3(signature = (lines, pitch, edge, zones, keep, params, progress=None, groups=None, base=None))]
#[allow(clippy::too_many_arguments)]
fn settle_traces<'py>(
    py: Python<'py>,
    lines: Vec<PyReadonlyArray2<'py, f64>>,
    pitch: f64,
    edge: PyReadonlyArray2<'py, f64>,
    zones: Vec<Vec<PyReadonlyArray2<'py, f64>>>,
    keep: Vec<Vec<PyReadonlyArray2<'py, f64>>>,
    params: &Bound<'py, PyDict>,
    progress: Option<PyObject>,
    groups: Option<Vec<usize>>,
    base: Option<Vec<PyReadonlyArray2<'py, f64>>>,
) -> PyResult<Bound<'py, PyList>> {
    let input = Input {
        lines: lines.iter().map(points).collect::<PyResult<_>>()?,
        pitch,
        edge: points(&edge)?,
        zones: zones
            .iter()
            .map(|z| z.iter().map(points).collect::<PyResult<Vec<_>>>())
            .collect::<PyResult<_>>()?,
        keep: keep
            .iter()
            .map(|z| z.iter().map(points).collect::<PyResult<Vec<_>>>())
            .collect::<PyResult<_>>()?,
        groups: groups.unwrap_or_default(),
        hold: Vec::new(),
        core: None,
        base: match base {
            Some(b) => b.iter().map(points).collect::<PyResult<_>>()?,
            None => Vec::new(),
        },
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
                        {
                            yanartas_mesh_core::cancel(true);
                            failed = Some(e);
                        }
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

/// The curve relaxed (`sfc._relax`): `curve` open from the stem's left end round to its
/// right end, `stem` closing it, `regions` each region's rings, `target` the length to
/// aim at, `edge`/`borders` points along the area's edge and the regions' borders,
/// `offset` the samples' offset, `params` the constants by name, `progress(step, steps)`.
/// Returns the closed curve (the stem last) and the number of vertices before the stem.
#[pyfunction]
#[pyo3(signature = (curve, stem, regions, target, edge, borders, spacing, least, pitch, offset, params, progress=None))]
#[allow(clippy::too_many_arguments)]
fn relax_curve<'py>(
    py: Python<'py>,
    curve: PyReadonlyArray2<'py, f64>,
    stem: PyReadonlyArray2<'py, f64>,
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
        stem: points(&stem)?,
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
        inside,
        hold
    );
    let mut failed: Option<PyErr> = None;
    let (p, k) = py.allow_threads(|| {
        relax(&input, &prm, &mut |step, steps| {
            if let (Some(cb), None) = (&progress, &failed) {
                Python::with_gil(|py| {
                    if let Err(e) = cb.call1(py, (step, steps)) {
                        {
                            yanartas_mesh_core::cancel(true);
                            failed = Some(e);
                        }
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

/// The `n` traces round the closed curve `p` (`sfc._lanes`): `k` the stem's first vertex,
/// `edge_a`/`edge_b` the area's edge in short segments, `exact` the stem's rails.
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

/// The curves' graph walked into curves (`sfc._curve`): `segments` each (region, its
/// domain's rings), `borders` each (region, region, the lines of their shared border; the
/// longest first), `openings` each a stem's ends, `seed` the random seed. Returns per
/// opening its curve's points and each one's region, the number of cells and of regions
/// left out.
#[pyfunction]
#[pyo3(signature = (segments, borders, openings, spacing, seed, params, progress=None))]
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn curve_graph<'py>(
    py: Python<'py>,
    segments: Vec<(usize, Vec<PyReadonlyArray2<'py, f64>>)>,
    borders: Vec<(usize, usize, Vec<PyReadonlyArray2<'py, f64>>)>,
    openings: Vec<((f64, f64), (f64, f64))>,
    spacing: f64,
    seed: u64,
    params: &Bound<'py, PyDict>,
    progress: Option<PyObject>,
) -> PyResult<(Vec<(Bound<'py, PyArray2<f64>>, Vec<usize>)>, usize, usize)> {
    let input = GraphInput {
        segments: segments
            .iter()
            .map(|(r, rings)| {
                Ok(Segment {
                    region: *r,
                    domain: rings.iter().map(points).collect::<PyResult<_>>()?,
                })
            })
            .collect::<PyResult<_>>()?,
        borders: borders
            .iter()
            .map(|(i, j, lines)| Ok((*i, *j, lines.iter().map(points).collect::<PyResult<_>>()?)))
            .collect::<PyResult<_>>()?,
        openings: openings
            .iter()
            .map(|(a, b)| [[a.0, a.1], [b.0, b.1]])
            .collect(),
        spacing,
        seed,
    };
    let mut prm = GraphParams::default();
    read!(params, prm, seed_spacing, lloyd, attempts);
    let mut failed: Option<PyErr> = None;
    let out = py.allow_threads(|| {
        curve(&input, &prm, &mut |step, steps| {
            if let (Some(cb), None) = (&progress, &failed) {
                Python::with_gil(|py| {
                    if let Err(e) = cb.call1(py, (step, steps)) {
                        {
                            yanartas_mesh_core::cancel(true);
                            failed = Some(e);
                        }
                    }
                });
            }
        })
    });
    if let Some(e) = failed {
        return Err(e);
    }
    let c = out.map_err(pyo3::exceptions::PyValueError::new_err)?;
    let curves = c
        .curves
        .iter()
        .map(|(pts, region)| (array(py, pts), region.clone()))
        .collect();
    Ok((curves, c.cells, c.left))
}

/// (testing) The tessellation of one domain: its cells' outlines.
#[pyfunction]
fn _cells<'py>(
    py: Python<'py>,
    domain: Vec<PyReadonlyArray2<'py, f64>>,
    d: f64,
    seed: u64,
    pin: Option<(f64, f64)>,
    lloyd: usize,
) -> PyResult<Bound<'py, PyList>> {
    let domain: Vec<Vec<P>> = domain.iter().map(points).collect::<PyResult<_>>()?;
    let mut rng = yanartas_mesh_core::graph::Rng::new(seed);
    let pins: Vec<P> = pin.map(|p| [p.0, p.1]).into_iter().collect();
    let out = yanartas_mesh_core::graph::cells(&domain, d, &mut rng, &pins, lloyd);
    PyList::new(py, out.iter().map(|c| array(py, &c[0])))
}

/// Each polyline as lines and circular arcs within `tol` of it: per line an (m, 7) array,
/// a row per piece: kind (0 line, 1 arc), start, middle (an arc's halfway point; a line's
/// middle), end.
#[pyfunction]
fn fit_arcs<'py>(
    py: Python<'py>,
    lines: Vec<PyReadonlyArray2<'py, f64>>,
    tol: f64,
) -> PyResult<Bound<'py, PyList>> {
    let lines: Vec<Vec<P>> = lines.iter().map(points).collect::<PyResult<_>>()?;
    let out: Vec<Vec<[f64; 7]>> = py.allow_threads(|| {
        lines
            .iter()
            .map(|l| fit(l, tol).iter().map(row).collect())
            .collect()
    });
    PyList::new(
        py,
        out.iter().map(|rows| {
            let flat: Vec<f64> = rows.iter().flatten().copied().collect();
            Array2::from_shape_vec((rows.len(), 7), flat)
                .expect("(m, 7)")
                .into_pyarray(py)
        }),
    )
}

fn row(p: &Piece) -> [f64; 7] {
    match *p {
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
    }
}

/// Stop (`on`) the layout under way at its next step, or (off) let the next one run.
#[pyfunction]
fn cancel(on: bool) {
    yanartas_mesh_core::cancel(on);
}

#[pymodule]
fn yanartas_mesh(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(cancel, m)?)?;
    m.add_function(wrap_pyfunction!(fit_arcs, m)?)?;
    m.add_function(wrap_pyfunction!(_cells, m)?)?;
    m.add_function(wrap_pyfunction!(curve_graph, m)?)?;
    m.add_function(wrap_pyfunction!(settle_traces, m)?)?;
    m.add_function(wrap_pyfunction!(relax_curve, m)?)?;
    m.add_function(wrap_pyfunction!(offset_lanes, m)?)?;
    Ok(())
}
