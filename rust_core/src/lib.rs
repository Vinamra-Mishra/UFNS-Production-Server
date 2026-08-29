//! Python bindings for UFNS high-performance Rust core (PyO3).

pub mod advection;
pub mod fingerprint;

use advection::{compute_motion_field_rs, semi_lagrangian_extrapolate_rs};
use fingerprint::compute_sha256_hex;
use numpy::{IntoPyArray, PyArray2, PyReadonlyArray2};
use pyo3::prelude::*;

use pyo3::exceptions::PyValueError;

/// Fast Semi-Lagrangian 2-D Advection Extrapolation.
#[pyfunction]
#[pyo3(signature = (field, u_mps, v_mps, lead_minutes, cell_size_m=30.0, decay_tau_minutes=Some(180.0)))]
fn advect_semi_lagrangian<'py>(
    py: Python<'py>,
    field: PyReadonlyArray2<'py, f64>,
    u_mps: PyReadonlyArray2<'py, f64>,
    v_mps: PyReadonlyArray2<'py, f64>,
    lead_minutes: f64,
    cell_size_m: f64,
    decay_tau_minutes: Option<f64>,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let f_view = field.as_array();
    let u_view = u_mps.as_array();
    let v_view = v_mps.as_array();

    if f_view.dim() != u_view.dim() || f_view.dim() != v_view.dim() {
        return Err(PyValueError::new_err(format!(
            "Dimension mismatch: field {:?}, u_mps {:?}, v_mps {:?}",
            f_view.dim(),
            u_view.dim(),
            v_view.dim()
        )));
    }

    let out = semi_lagrangian_extrapolate_rs(
        f_view,
        u_view,
        v_view,
        lead_minutes,
        cell_size_m,
        decay_tau_minutes,
    );

    Ok(out.into_pyarray_bound(py))
}

/// Fast optical flow motion field computation.
#[pyfunction]
#[pyo3(signature = (frame_prev, frame_curr, cell_size_m=30.0, dt_seconds=900.0))]
fn compute_motion_field<'py>(
    py: Python<'py>,
    frame_prev: PyReadonlyArray2<'py, f64>,
    frame_curr: PyReadonlyArray2<'py, f64>,
    cell_size_m: f64,
    dt_seconds: f64,
) -> PyResult<(Bound<'py, PyArray2<f64>>, Bound<'py, PyArray2<f64>>, f64, f64)> {
    let prev_view = frame_prev.as_array();
    let curr_view = frame_curr.as_array();

    if prev_view.dim() != curr_view.dim() {
        return Err(PyValueError::new_err(format!(
            "Dimension mismatch: frame_prev {:?}, frame_curr {:?}",
            prev_view.dim(),
            curr_view.dim()
        )));
    }

    let (u_dense, v_dense, u_glob, v_glob) =
        compute_motion_field_rs(prev_view, curr_view, cell_size_m, dt_seconds);

    Ok((
        u_dense.into_pyarray_bound(py),
        v_dense.into_pyarray_bound(py),
        u_glob,
        v_glob,
    ))
}


/// Fast SHA-256 digest computation for byte buffers.
#[pyfunction]
fn sha256_hex(_py: Python<'_>, data: &[u8]) -> String {
    compute_sha256_hex(data)
}

/// Return engine version and capabilities.
#[pyfunction]
fn engine_info() -> String {
    "UFNS-Rust-Core v4.1 (PyO3 SIMD / Rayon Multi-threaded)".to_string()
}

/// UFNS Native Rust Extension Module.
#[pymodule]
fn ufns_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(advect_semi_lagrangian, m)?)?;
    m.add_function(wrap_pyfunction!(compute_motion_field, m)?)?;
    m.add_function(wrap_pyfunction!(sha256_hex, m)?)?;
    m.add_function(wrap_pyfunction!(engine_info, m)?)?;
    Ok(())
}
