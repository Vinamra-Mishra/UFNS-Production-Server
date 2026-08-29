//! Semi-Lagrangian Advection & Optical Flow in Rust with Rayon parallelism.

use ndarray::{Array2, ArrayView2};
use rayon::prelude::*;

/// Semi-Lagrangian backward trajectory extrapolation for 2-D scalar fields.
/// 
/// Solves x_origin = x - (u * dt) / dx, y_origin = y - (v * dt) / dy
/// with bilinear interpolation and exponential convective decay.
pub fn semi_lagrangian_extrapolate_rs(
    field: ArrayView2<f64>,
    u_mps: ArrayView2<f64>,
    v_mps: ArrayView2<f64>,
    lead_minutes: f64,
    cell_size_m: f64,
    decay_tau_minutes: Option<f64>,
) -> Array2<f64> {
    let (height, width) = field.dim();
    if lead_minutes <= 0.0 {
        return field.to_owned();
    }

    let dt_s = lead_minutes * 60.0;
    let max_x = (width - 1) as f64;
    let max_y = (height - 1) as f64;

    let decay_factor = match decay_tau_minutes {
        Some(tau) if tau > 0.0 => (-lead_minutes / tau).exp(),
        _ => 1.0,
    };

    let mut result = Array2::<f64>::zeros((height, width));

    // Parallel row-wise processing via contiguous slice chunks
    if let Some(slice_mut) = result.as_slice_mut() {
        slice_mut
            .par_chunks_exact_mut(width)
            .enumerate()
            .for_each(|(r, row)| {
                let y_dst = r as f64;
                for c in 0..width {
                    let x_dst = c as f64;
                    let u = u_mps[[r, c]];
                    let v = v_mps[[r, c]];

                    // Backward trajectory
                    let x_src = (x_dst - (u * dt_s) / cell_size_m).clamp(0.0, max_x);
                    let y_src = (y_dst - (v * dt_s) / cell_size_m).clamp(0.0, max_y);

                    let x0 = x_src.floor() as usize;
                    let y0 = y_src.floor() as usize;
                    let x1 = (x0 + 1).min(width - 1);
                    let y1 = (y0 + 1).min(height - 1);

                    let wx = x_src - (x0 as f64);
                    let wy = y_src - (y0 as f64);

                    let v00 = field[[y0, x0]];
                    let v01 = field[[y0, x1]];
                    let v10 = field[[y1, x0]];
                    let v11 = field[[y1, x1]];

                    let mut val = (1.0 - wx) * (1.0 - wy) * v00
                        + wx * (1.0 - wy) * v01
                        + (1.0 - wx) * wy * v10
                        + wx * wy * v11;

                    if !val.is_finite() || val < 0.0 {
                        val = 0.0;
                    }

                    row[c] = val * decay_factor;
                }
            });
    }

    result
}

/// Computes dense motion velocity fields (u, v) in m/s between two radar frames.
pub fn compute_motion_field_rs(
    frame_prev: ArrayView2<f64>,
    frame_curr: ArrayView2<f64>,
    cell_size_m: f64,
    dt_seconds: f64,
) -> (Array2<f64>, Array2<f64>, f64, f64) {
    let (height, width) = frame_curr.dim();
    let dt_safe = if dt_seconds > 0.0 { dt_seconds } else { 1.0 };

    let mut mass_prev = 0.0;
    let mut mass_curr = 0.0;
    let mut cx_prev = 0.0;
    let mut cy_prev = 0.0;
    let mut cx_curr = 0.0;
    let mut cy_curr = 0.0;

    for r in 0..height {
        for c in 0..width {
            let p_p = frame_prev[[r, c]];
            let p_c = frame_curr[[r, c]];
            if p_p > 0.0 {
                mass_prev += p_p;
                cx_prev += (c as f64) * p_p;
                cy_prev += (r as f64) * p_p;
            }
            if p_c > 0.0 {
                mass_curr += p_c;
                cx_curr += (c as f64) * p_c;
                cy_curr += (r as f64) * p_c;
            }
        }
    }

    let (u_global, v_global) = if mass_prev > 1.0 && mass_curr > 1.0 {
        let x_shift = (cx_curr / mass_curr) - (cx_prev / mass_prev);
        let y_shift = (cy_curr / mass_curr) - (cy_prev / mass_prev);
        ((x_shift * cell_size_m) / dt_safe, (y_shift * cell_size_m) / dt_safe)
    } else {
        (3.0, 2.0)
    };

    let mut u_dense = Array2::<f64>::zeros((height, width));
    let mut v_dense = Array2::<f64>::zeros((height, width));

    let alpha = 1.0;

    for r in 0..height {
        let r_prev = if r > 0 { r - 1 } else { 0 };
        let r_next = if r + 1 < height { r + 1 } else { height - 1 };

        for c in 0..width {
            let c_prev = if c > 0 { c - 1 } else { 0 };
            let c_next = if c + 1 < width { c + 1 } else { width - 1 };

            let iy = (frame_curr[[r_next, c]] - frame_curr[[r_prev, c]]) / 2.0;
            let ix = (frame_curr[[r, c_next]] - frame_curr[[r, c_prev]]) / 2.0;
            let it = frame_curr[[r, c]] - frame_prev[[r, c]];

            let grad_mag = ix * ix + iy * iy;
            let u_local = - (ix * it) / (grad_mag + alpha);
            let v_local = - (iy * it) / (grad_mag + alpha);

            let u_field = (u_local * cell_size_m) / dt_safe;
            let v_field = (v_local * cell_size_m) / dt_safe;

            let blend_weight = (grad_mag / (grad_mag + 0.1)).clamp(0.0, 1.0);
            let u_val = blend_weight * u_field + (1.0 - blend_weight) * u_global;
            let v_val = blend_weight * v_field + (1.0 - blend_weight) * v_global;

            u_dense[[r, c]] = u_val.clamp(-50.0, 50.0);
            v_dense[[r, c]] = v_val.clamp(-50.0, 50.0);
        }
    }

    (u_dense, v_dense, u_global, v_global)
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::Array2;

    #[test]
    fn test_zero_lead_identity() {
        let mut field = Array2::<f64>::zeros((10, 10));
        field[[5, 5]] = 25.0;
        let u = Array2::<f64>::from_elem((10, 10), 5.0);
        let v = Array2::<f64>::from_elem((10, 10), 2.0);

        let out = semi_lagrangian_extrapolate_rs(field.view(), u.view(), v.view(), 0.0, 30.0, Some(180.0));
        assert_eq!(out, field);
    }

    #[test]
    fn test_positive_advection_bounds() {
        let mut field = Array2::<f64>::zeros((20, 20));
        for r in 8..12 {
            for c in 8..12 {
                field[[r, c]] = 50.0;
            }
        }
        let u = Array2::<f64>::from_elem((20, 20), 10.0);
        let v = Array2::<f64>::from_elem((20, 20), 0.0);

        let out = semi_lagrangian_extrapolate_rs(field.view(), u.view(), v.view(), 15.0, 30.0, Some(180.0));
        assert_eq!(out.dim(), (20, 20));
        for val in out.iter() {
            assert!(val.is_finite());
            assert!(*val >= 0.0);
        }
    }

    #[test]
    fn test_motion_field_computation() {
        let mut prev = Array2::<f64>::zeros((20, 20));
        let mut curr = Array2::<f64>::zeros((20, 20));
        prev[[5, 5]] = 30.0;
        curr[[5, 6]] = 30.0;

        let (u, v, u_g, v_g) = compute_motion_field_rs(prev.view(), curr.view(), 30.0, 900.0);
        assert_eq!(u.dim(), (20, 20));
        assert_eq!(v.dim(), (20, 20));
        assert!(u_g.is_finite());
        assert!(v_g.is_finite());
    }
}
