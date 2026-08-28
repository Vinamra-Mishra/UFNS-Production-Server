"""Hydrological observation data models, sensor ingestion, and synthetic benchmark generator (Phase B).

Provides:
- ObservationTarget: types of observed hydrological targets (flow, head, depth, extent)
- ObservationProvenance & NetworkProvenance: strict scientific governance tags
- ObservedTimeSeries: container for time-indexed sensor measurements
- SyntheticBenchmarkGenerator: generates synthetic ground truth + noise for inverse recovery verification
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np


class ObservationTarget(str, Enum):
    """Observationtarget schema and data model representation."""
    OUTFALL_DISCHARGE = "OUTFALL_DISCHARGE"  # m3/s outfall hydrograph
    NODE_HEAD = "NODE_HEAD"                  # m hydraulic head at manhole/storage node
    SURFACE_DEPTH = "SURFACE_DEPTH"          # m water depth at surface gauge point
    SPATIAL_EXTENT = "SPATIAL_EXTENT"        # 2D surface inundation depth array


class ObservationProvenance(str, Enum):
    """Observationprovenance schema and data model representation."""
    SYNTHETIC_BENCHMARK = "SYNTHETIC_BENCHMARK"                     # Ground-truth forward simulation + noise
    FIELD_SENSOR_RAW = "FIELD_SENSOR_RAW"                           # Unprocessed IoT depth/ultrasonic sensor
    FIELD_SENSOR_QUALITY_CONTROLLED = "FIELD_SENSOR_QC"             # Outlier-filtered field sensor feed


class NetworkProvenance(str, Enum):
    """Networkprovenance schema and data model representation."""
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"                         # M3/M4/M5 exact-exchange synthetic fixture
    ASSUMED_DEMO_NETWORK = "ASSUMED_DEMO_NETWORK"                   # Pilot domain with assumed/inferred pipes
    SURVEYED_ASSET_NETWORK = "SURVEYED_ASSET_NETWORK"               # Physically surveyed GIS pipe blueprints


class ValidationStatus(str, Enum):
    """Validationstatus schema and data model representation."""
    ALGORITHMIC_RECOVERY_VALIDATED = "ALGORITHMIC_RECOVERY_VALIDATED"  # Parameter recovery proven on synthetic benchmark
    PROVISIONAL_ESTIMATE = "PROVISIONAL_ESTIMATE"                     # Inverse fit on assumed/unverified network
    SCIENTIFICALLY_VALIDATED = "SCIENTIFICALLY_VALIDATED"             # Both surveyed network and real sensors present


@dataclass(frozen=True)
class ObservedTimeSeries:
    """Time-indexed hydrological observation series."""

    target_type: ObservationTarget
    sensor_id: str
    time_minutes: tuple[float, ...]
    values: tuple[float, ...]
    unit: str
    provenance: ObservationProvenance
    noise_std: float = 0.0
    quality_flag: str = "VALID"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Execute Post Init validation on lengths, finiteness, and monotonicity."""
        if len(self.time_minutes) != len(self.values):
            raise ValueError(
                f"Time length ({len(self.time_minutes)}) must match values length ({len(self.values)})"
            )
        if len(self.time_minutes) > 0:
            t_arr = np.asarray(self.time_minutes, dtype=np.float64)
            if not np.all(np.isfinite(t_arr)):
                raise ValueError("time_minutes contains non-finite values (NaN or Inf)")
            if len(t_arr) > 1 and not np.all(np.diff(t_arr) > 0):
                raise ValueError("time_minutes must contain strictly increasing timestamps")

    @property
    def time_array(self) -> np.ndarray:
        """Execute Time Array operation and return result."""
        return np.asarray(self.time_minutes, dtype=np.float64)

    @property
    def value_array(self) -> np.ndarray:
        """Execute Value Array operation and return result."""
        return np.asarray(self.values, dtype=np.float64)

    @property
    def peak_value(self) -> float:
        """Execute Peak Value operation and return result."""
        return float(np.max(self.value_array)) if len(self.values) > 0 else 0.0

    @property
    def time_to_peak_minutes(self) -> float:
        """Execute Time To Peak Minutes operation and return result."""
        if len(self.values) == 0:
            return 0.0
        idx = int(np.argmax(self.value_array))
        return float(self.time_minutes[idx])

    def resample_to(self, target_times_minutes: Sequence[float]) -> np.ndarray:
        """Resample observation series onto target simulation timestamps using linear interpolation."""
        t_target = np.asarray(target_times_minutes, dtype=np.float64)
        return np.interp(t_target, self.time_array, self.value_array)

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "target_type": self.target_type.value,
            "sensor_id": self.sensor_id,
            "time_minutes": list(self.time_minutes),
            "values": [round(float(v), 6) for v in self.values],
            "unit": self.unit,
            "provenance": self.provenance.value,
            "noise_std": self.noise_std,
            "quality_flag": self.quality_flag,
            "metadata": copy.deepcopy(self.metadata),
        }

    def fingerprint(self) -> str:
        """Execute Fingerprint operation and return result."""
        serialized = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Synthetic Benchmark Hydrograph Generator
# ---------------------------------------------------------------------------

class SyntheticBenchmarkGenerator:
    """Generates synthetic benchmark hydrographs for inverse calibration verification."""

    @staticmethod
    def generate_synthetic_hydrograph(
        duration_minutes: float = 60.0,
        dt_minutes: float = 1.0,
        peak_discharge_m3s: float = 0.085,
        time_to_peak_minutes: float = 25.0,
        baseflow_m3s: float = 0.005,
        recession_shape: float = 3.0,
        noise_std: float = 0.0,
        seed: int = 20260825,
    ) -> ObservedTimeSeries:
        """Generate a realistic synthetic gamma-type urban runoff hydrograph:

        Q(t) = Q_base + (Q_peak - Q_base) * (t / t_peak)^gamma * exp(gamma * (1 - t / t_peak))
        + optional Gaussian measurement noise N(0, noise_std).
        """
        rng = np.random.default_rng(seed)
        t_arr = np.arange(0.0, duration_minutes + dt_minutes / 2.0, dt_minutes, dtype=np.float64)

        t_peak = max(1.0, float(time_to_peak_minutes))
        gamma = float(recession_shape)
        q_amp = max(0.0, peak_discharge_m3s - baseflow_m3s)

        # Gamma synthetic hydrograph
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            ratio = t_arr / t_peak
            q_norm = np.where(t_arr > 0, (ratio**gamma) * np.exp(gamma * (1.0 - ratio)), 0.0)
            q_norm = np.nan_to_num(q_norm, nan=0.0, posinf=0.0, neginf=0.0)

        q_clean = baseflow_m3s + q_amp * q_norm

        if noise_std > 0:
            noise = rng.normal(0.0, noise_std, size=q_clean.shape)
            q_noisy = np.maximum(0.0, q_clean + noise)
        else:
            q_noisy = q_clean

        return ObservedTimeSeries(
            target_type=ObservationTarget.OUTFALL_DISCHARGE,
            sensor_id="SYNTHETIC-OUTFALL-GAUGE-01",
            time_minutes=tuple(float(t) for t in t_arr),
            values=tuple(float(v) for v in q_noisy),
            unit="m3/s",
            provenance=ObservationProvenance.SYNTHETIC_BENCHMARK,
            noise_std=noise_std,
            metadata={
                "true_peak_discharge_m3s": peak_discharge_m3s,
                "true_time_to_peak_minutes": time_to_peak_minutes,
                "gamma_shape": recession_shape,
                "seed": seed,
            },
        )
