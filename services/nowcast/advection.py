"""M12/Phase A — Optical Flow & Semi-Lagrangian Advection Nowcasting Engine.

Implements motion estimation and extrapolation for precipitation nowcasting
across 0–3 hour (0–180 minute) lead times.

Mathematical Formulation:
  1. Optical Flow Motion Estimation:
     Solves the brightness constancy constraint:
         dI/dt = dI/dx * u + dI/dy * v + dI/dt_obs = 0
     to determine velocity vector fields (u, v) in m/s across the radar domain.

  2. Semi-Lagrangian Backward Trajectory Extrapolation:
     For any destination grid point (x, y) at lead time Δt:
         x_origin = x - u(x, y) * Δt / dx
         y_origin = y - v(x, y) * Δt / dy
     The forecast intensity is obtained via bilinear interpolation of the
     initial field at (x_origin, y_origin).

  3. Convective Cell Growth & Decay:
     I(t + Δt) = I_advected * exp(-Δt / tau_decay)
     where tau_decay models the life-cycle of convective precipitation.

References:
  - Germann, U., & Zawadzki, I. (2002). Scale-dependence of the predictibility of
    precipitation by radar. Monthly Weather Review, 130(12), 2859-2873.
  - Bowler, N. E., et al. (2006). STEPS: A probabilistic precipitation nowcasting system.
  - Pulkkinen, S., et al. (2019). Pysteps: an open-source Python library for
    probabilistic precipitation nowcasting.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np

from services.nowcast import NOWCAST_METHOD_ADVECTION
from services.nowcast.nowcast_record import NowcastRecord
from services.nowcast.providers import RainfallObservation, SourceType
from services.nowcast.quality import QualityResult


def compute_motion_field(
    frame_prev: np.ndarray,
    frame_curr: np.ndarray,
    cell_size_m: float = 30.0,
    dt_seconds: float = 900.0,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Compute dense (u, v) velocity field in m/s between two radar frames.

    Args:
        frame_prev: Previous rainfall field (height, width) in mm/h.
        frame_curr: Current rainfall field (height, width) in mm/h.
        cell_size_m: Grid cell size in metres (default 30.0 m).
        dt_seconds: Time interval between frames in seconds (default 15 min = 900 s).

    Returns:
        Tuple of (u_field_mps, v_field_mps, u_global_mps, v_global_mps).
        u is eastward velocity (columns/x direction), v is northward velocity (rows/y direction).
    """
    p_prev = np.asarray(frame_prev, dtype=np.float64)
    p_curr = np.asarray(frame_curr, dtype=np.float64)
    h, w = p_curr.shape

    # Spatial and temporal gradients
    # Ix: gradient along x (axis 1)
    # Iy: gradient along y (axis 0, note: row 0 is top / north)
    iy, ix = np.gradient(p_curr)
    it = p_curr - p_prev

    # Spatial smoothing over local 5x5 blocks (Lucas-Kanade formulation)
    # Filter only where there is active precipitation or significant gradient
    grad_mag = ix**2 + iy**2
    valid_mask = (grad_mag > 1e-4) & ((p_curr > 0.1) | (p_prev > 0.1))

    # Calculate global storm motion via center of mass tracking if precipitation exists
    mass_prev = np.sum(p_prev)
    mass_curr = np.sum(p_curr)
    
    if mass_prev > 1.0 and mass_curr > 1.0:
        y_grid, x_grid = np.mgrid[0:h, 0:w]
        cy_prev = np.sum(y_grid * p_prev) / mass_prev
        cx_prev = np.sum(x_grid * p_prev) / mass_prev
        cy_curr = np.sum(y_grid * p_curr) / mass_curr
        cx_curr = np.sum(x_grid * p_curr) / mass_curr

        # Shift in cells
        shift_x_cells = cx_curr - cx_prev
        shift_y_cells = cy_curr - cy_prev

        # Convert to m/s
        u_global = (shift_x_cells * cell_size_m) / max(dt_seconds, 1.0)
        v_global = (shift_y_cells * cell_size_m) / max(dt_seconds, 1.0)
    else:
        # Default convective drift if dry/isolated (e.g. 5 m/s eastward, 2 m/s northward)
        u_global = 3.0
        v_global = 2.0

    # Local optical flow estimation with Tikhonov regularization
    alpha = 1.0  # regularization parameter
    u_local = - (ix * it) / (grad_mag + alpha)
    v_local = - (iy * it) / (grad_mag + alpha)

    # Convert local pixel displacements to m/s
    u_field = (u_local * cell_size_m) / max(dt_seconds, 1.0)
    v_field = (v_local * cell_size_m) / max(dt_seconds, 1.0)

    # Blend local optical flow with global motion (global provides smooth baseline in dry cells)
    blend_weight = np.clip(grad_mag / (grad_mag + 0.1), 0.0, 1.0)
    u_dense = blend_weight * u_field + (1.0 - blend_weight) * u_global
    v_dense = blend_weight * v_field + (1.0 - blend_weight) * v_global

    # Clip velocity to realistic meteorological bounds for tropical storms (-50 to +50 m/s)
    u_dense = np.clip(u_dense, -50.0, 50.0)
    v_dense = np.clip(v_dense, -50.0, 50.0)

    return u_dense, v_dense, float(u_global), float(v_global)


def semi_lagrangian_extrapolate(
    field: np.ndarray,
    u_mps: np.ndarray | float,
    v_mps: np.ndarray | float,
    lead_minutes: float,
    cell_size_m: float = 30.0,
    decay_tau_minutes: float | None = 180.0,
) -> np.ndarray:
    """Extrapolate a 2-D rainfall field forward in time via Semi-Lagrangian advection.

    Args:
        field: Input 2-D array of rainfall rates (mm/h).
        u_mps: Eastward velocity in m/s (2-D array or scalar).
        v_mps: Northward velocity in m/s (2-D array or scalar).
        lead_minutes: Forecast horizon in minutes.
        cell_size_m: Spatial resolution in metres.
        decay_tau_minutes: Optional exponential decay time scale (in minutes).

    Returns:
        Advected 2-D rainfall field (height, width) at lead_minutes.
    """
    arr = np.asarray(field, dtype=np.float64)
    h, w = arr.shape
    if lead_minutes <= 0.0:
        return arr.copy()

    dt_s = lead_minutes * 60.0
    u_arr = np.broadcast_to(np.asarray(u_mps, dtype=np.float64), (h, w))
    v_arr = np.broadcast_to(np.asarray(v_mps, dtype=np.float64), (h, w))

    # Grid coordinates
    y_dst, x_dst = np.mgrid[0:h, 0:w].astype(np.float64)

    # Backward trajectory: find where the air parcel originated at t=0
    # x_origin = x_dst - (u * dt) / dx
    # y_origin = y_dst - (v * dt) / dy
    x_src = x_dst - (u_arr * dt_s) / cell_size_m
    y_src = y_dst - (v_arr * dt_s) / cell_size_m

    # Bilinear interpolation
    x_src_cl = np.clip(x_src, 0.0, float(w - 1))
    y_src_cl = np.clip(y_src, 0.0, float(h - 1))

    x0 = np.floor(x_src_cl).astype(int)
    y0 = np.floor(y_src_cl).astype(int)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)

    wx = x_src_cl - x0
    wy = y_src_cl - y0

    val_00 = arr[y0, x0]
    val_01 = arr[y0, x1]
    val_10 = arr[y1, x0]
    val_11 = arr[y1, x1]

    interpolated = (
        (1.0 - wx) * (1.0 - wy) * val_00
        + wx * (1.0 - wy) * val_01
        + (1.0 - wx) * wy * val_10
        + wx * wy * val_11
    )
    interpolated = np.nan_to_num(np.maximum(interpolated, 0.0), nan=0.0, posinf=0.0, neginf=0.0)

    # Apply exponential convective decay if configured
    if decay_tau_minutes is not None and decay_tau_minutes > 0.0:
        decay_factor = float(np.exp(-lead_minutes / decay_tau_minutes))
        interpolated *= decay_factor

    return np.ascontiguousarray(interpolated, dtype=np.float64)


@dataclass(frozen=True)
class AdvectionConfig:
    """Configuration for optical flow advection nowcasting."""
    lead_times_minutes: tuple[int, ...] = (0, 15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180)
    max_lead_minutes: int = 180
    method: str = NOWCAST_METHOD_ADVECTION
    decay_tau_minutes: Optional[float] = 180.0
    default_velocity_mps: tuple[float, float] = (5.0, 2.0)
    cell_size_m: float = 30.0
    status: str = "PROVISIONAL"
    uncertainty: str = "SEMI_LAGRANGIAN_ADVECTION"


class AdvectionNowcastEngine:
    """0–3 Hour Optical Flow & Semi-Lagrangian Advection Nowcast Engine."""

    def __init__(self, config: AdvectionConfig | None = None) -> None:
        """Execute   Init   operation and return result."""
        self._config = config or AdvectionConfig()

    @property
    def config(self) -> AdvectionConfig:
        """Execute Config operation and return result."""
        return self._config

    def generate(
        self,
        observation: RainfallObservation,
        previous_observation: RainfallObservation | None = None,
        quality: QualityResult | None = None,
    ) -> list[NowcastRecord]:
        """Generate 0–180 minute nowcast records from observation(s).

        Args:
            observation: Current rainfall observation at t=0.
            previous_observation: Optional observation at t=-dt for velocity tracking.
            quality: Quality validation result.

        Returns:
            List of NowcastRecord instances for each lead time up to 180 minutes.
        """
        if quality is not None and not quality.valid:
            return []

        h, w = observation.rate_mmh.shape
        cell_size = observation.spatial_resolution_m or self._config.cell_size_m

        # Compute velocity field
        if previous_observation is not None:
            dt_s = abs(
                (observation.observation_time - previous_observation.observation_time).total_seconds()
            )
            u_field, v_field, u_glob, v_glob = compute_motion_field(
                frame_prev=previous_observation.rate_mmh,
                frame_curr=observation.rate_mmh,
                cell_size_m=cell_size,
                dt_seconds=dt_s,
            )
        else:
            # Single observation: use default meteorological advection vector
            u_glob, v_glob = self._config.default_velocity_mps
            u_field = np.full((h, w), u_glob, dtype=np.float64)
            v_field = np.full((h, w), v_glob, dtype=np.float64)

        obs_fp = observation.fingerprint()
        records: list[NowcastRecord] = []

        for lead_min in self._config.lead_times_minutes:
            if lead_min == 0:
                forecast_field = observation.rate_mmh.copy()
            else:
                forecast_field = semi_lagrangian_extrapolate(
                    field=observation.rate_mmh,
                    u_mps=u_field,
                    v_mps=v_field,
                    lead_minutes=float(lead_min),
                    cell_size_m=cell_size,
                    decay_tau_minutes=self._config.decay_tau_minutes,
                )

            valid_time = observation.observation_time + timedelta(minutes=lead_min)
            
            meta: dict[str, Any] = {
                "observation_fingerprint": obs_fp,
                "u_global_mps": round(u_glob, 4),
                "v_global_mps": round(v_glob, 4),
                "decay_tau_minutes": self._config.decay_tau_minutes,
                "lead_minutes": lead_min,
                "advection_engine": "SEMI_LAGRANGIAN_BILINEAR",
            }

            rec = NowcastRecord(
                initialization_time=observation.observation_time,
                valid_time=valid_time,
                lead_minutes=lead_min,
                rate_mmh=forecast_field,
                units="mm/h",
                spatial_reference=observation.spatial_reference,
                spatial_resolution_m=cell_size,
                width=w,
                height=h,
                source_type=observation.source_type.value,
                source_name=observation.source_name,
                source_provider_id=observation.source_provider_id,
                method=self._config.method,
                status=self._config.status,
                uncertainty=self._config.uncertainty,
                quality_flags=tuple(
                    list(observation.quality_flags) + [f"ADVECTION_LEAD_{lead_min}"]
                ),
                metadata=meta,
            )
            # Attach deterministic fingerprint
            fp = rec.compute_fingerprint()
            object.__setattr__(rec, "fingerprint", fp)
            records.append(rec)

        return records
