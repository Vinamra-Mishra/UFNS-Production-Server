"""Phase D — Multi-Sensor NWP + Doppler Radar Blending Engine.

Combines short-range Doppler Weather Radar (DWR) optical flow nowcasting
with long-range Numerical Weather Prediction (NCMRWF NCUM / IMD WRF) fields.

Dynamic Blending Schedule (0–180 minutes):
  - Lead 0–30 min:  100% Radar, 0% NWP (radar advection dominates)
  - Lead 30–150 min: Linear transition from Radar to NWP
  - Lead 150–180 min: 0% Radar, 100% NWP (thermodynamic model physics dominates)

Strict Zero-Mock Governance:
  - When real NWP data is absent, gracefully operates in RADAR_ONLY mode.
  - Never fabricates synthetic fields as real NCMRWF forecast data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import numpy as np

from services.contracts import (
    DataLineage,
    GridSpec,
    ProvenanceClass,
    QualityFlag,
    RainfallGrid,
)
from services.ingestion.grib_netcdf import (
    GLOBAL_REAL_NWP_ENGINE,
    RealNWPDataset,
    get_authoritative_bagjola_grid,
)


class BlendingMode(str, Enum):
    """Blendingmode schema and data model representation."""
    RADAR_ONLY = "RADAR_ONLY"
    NWP_ONLY = "NWP_ONLY"
    BLENDED_LINEAR = "BLENDED_LINEAR"
    FALLBACK_RADAR_ONLY = "FALLBACK_RADAR_ONLY"


@dataclass(frozen=True)
class BlendingWeights:
    """Dynamic multi-sensor weights at lead time t."""
    lead_minutes: int
    w_radar: float
    w_nwp: float


@dataclass
class BlendedRainfallResult:
    """Output container for blended precipitation field."""
    lead_minutes: int
    blending_mode: BlendingMode
    weights: BlendingWeights
    blended_matrix: np.ndarray  # [height, width] in mm/h
    min_rate_mmh: float
    max_rate_mmh: float
    mean_rate_mmh: float
    radar_available: bool
    nwp_available: bool
    nwp_model_name: Optional[str]
    nwp_sha256: Optional[str]
    provenance_class: ProvenanceClass
    quality_flags: list[QualityFlag]


def compute_blending_weights(lead_minutes: int) -> BlendingWeights:
    """Compute continuous blending weights over 0–180 min horizon.

    w_radar(t):
      t <= 30 min: 1.0
      30 < t < 150 min: 1.0 - (t - 30) / 120.0
      t >= 150 min: 0.0
    w_nwp(t) = 1.0 - w_radar(t)
    """
    t = float(max(0, lead_minutes))
    if t <= 30.0:
        w_radar = 1.0
    elif t >= 150.0:
        w_radar = 0.0
    else:
        w_radar = 1.0 - (t - 30.0) / 120.0

    w_radar = round(float(np.clip(w_radar, 0.0, 1.0)), 4)
    w_nwp = round(1.0 - w_radar, 4)

    return BlendingWeights(lead_minutes=lead_minutes, w_radar=w_radar, w_nwp=w_nwp)


class MultiSensorBlender:
    """Engine for fusing Doppler radar extrapolation with NCMRWF/IMD NWP forecasts."""

    def __init__(self, target_grid: GridSpec | None = None) -> None:
        """Execute   Init   operation and return result."""
        self.target_grid = target_grid or get_authoritative_bagjola_grid()

    def blend(
        self,
        radar_matrix: np.ndarray,
        nwp_dataset: RealNWPDataset | None,
        lead_minutes: int,
    ) -> BlendedRainfallResult:
        """Blend radar optical flow matrix with real NWP forecast at specified lead time."""
        weights = compute_blending_weights(lead_minutes)
        r_mat = np.array(radar_matrix, dtype=float)

        # 1. Fallback if NWP dataset is missing or unavailable
        if nwp_dataset is None or not nwp_dataset.forecast_steps:
            blended = np.clip(r_mat, 0.0, 300.0)
            return BlendedRainfallResult(
                lead_minutes=lead_minutes,
                blending_mode=BlendingMode.FALLBACK_RADAR_ONLY,
                weights=BlendingWeights(lead_minutes=lead_minutes, w_radar=1.0, w_nwp=0.0),
                blended_matrix=blended,
                min_rate_mmh=float(np.min(blended)),
                max_rate_mmh=float(np.max(blended)),
                mean_rate_mmh=float(np.mean(blended)),
                radar_available=True,
                nwp_available=False,
                nwp_model_name=None,
                nwp_sha256=None,
                provenance_class=ProvenanceClass.DERIVED,
                quality_flags=[QualityFlag.VALIDATED, QualityFlag.RESAMPLED],
            )

        # 2. Extract matching NWP step
        nwp_step = nwp_dataset.get_step(lead_minutes)
        if nwp_step is None:
            blended = np.clip(r_mat, 0.0, 300.0)
            return BlendedRainfallResult(
                lead_minutes=lead_minutes,
                blending_mode=BlendingMode.FALLBACK_RADAR_ONLY,
                weights=BlendingWeights(lead_minutes=lead_minutes, w_radar=1.0, w_nwp=0.0),
                blended_matrix=blended,
                min_rate_mmh=float(np.min(blended)),
                max_rate_mmh=float(np.max(blended)),
                mean_rate_mmh=float(np.mean(blended)),
                radar_available=True,
                nwp_available=False,
                nwp_model_name=nwp_dataset.model_name,
                nwp_sha256=nwp_dataset.file_sha256,
                provenance_class=ProvenanceClass.DERIVED,
                quality_flags=[QualityFlag.VALIDATED, QualityFlag.RESAMPLED],
            )

        n_mat = np.array(nwp_step.precip_rate_mmh, dtype=float)

        # 3. Shape alignment check
        if r_mat.shape != n_mat.shape:
            blended = np.clip(r_mat, 0.0, 300.0)
            return BlendedRainfallResult(
                lead_minutes=lead_minutes,
                blending_mode=BlendingMode.FALLBACK_RADAR_ONLY,
                weights=BlendingWeights(lead_minutes=lead_minutes, w_radar=1.0, w_nwp=0.0),
                blended_matrix=blended,
                min_rate_mmh=float(np.min(blended)),
                max_rate_mmh=float(np.max(blended)),
                mean_rate_mmh=float(np.mean(blended)),
                radar_available=True,
                nwp_available=False,
                nwp_model_name=nwp_dataset.model_name,
                nwp_sha256=nwp_dataset.file_sha256,
                provenance_class=ProvenanceClass.DERIVED,
                quality_flags=[QualityFlag.VALIDATED, QualityFlag.RESAMPLED],
            )

        # 4. Compute weighted fusion
        blended = weights.w_radar * r_mat + weights.w_nwp * n_mat
        blended = np.clip(blended, 0.0, 300.0)

        mode = BlendingMode.RADAR_ONLY if weights.w_radar == 1.0 else (
            BlendingMode.NWP_ONLY if weights.w_nwp == 1.0 else BlendingMode.BLENDED_LINEAR
        )

        return BlendedRainfallResult(
            lead_minutes=lead_minutes,
            blending_mode=mode,
            weights=weights,
            blended_matrix=blended,
            min_rate_mmh=float(np.min(blended)),
            max_rate_mmh=float(np.max(blended)),
            mean_rate_mmh=float(np.mean(blended)),
            radar_available=True,
            nwp_available=True,
            nwp_model_name=nwp_dataset.model_name,
            nwp_sha256=nwp_dataset.file_sha256,
            provenance_class=ProvenanceClass.DERIVED,
            quality_flags=[QualityFlag.VALIDATED, QualityFlag.RESAMPLED],
        )


GLOBAL_MULTI_SENSOR_BLENDER = MultiSensorBlender()
