"""M8 — Forecast verification metrics framework.

Defines the verification metrics appropriate for rainfall nowcasting and
provides computation functions for when paired (forecast, observation) data
becomes available.

IMPORTANT: Verification metrics MUST NOT be computed or reported until real
paired data exists. The default status is NOT_EVALUATED.

Metrics implemented:
  - MAE (Mean Absolute Error) — continuous
  - RMSE (Root Mean Square Error) — continuous
  - Bias — continuous
  - Correlation (Pearson) — continuous
  - CSI (Critical Success Index) — categorical
  - POD (Probability of Detection) — categorical
  - FAR (False Alarm Ratio) — categorical

References:
  - Germann & Zawadzki (2002, 2004) — scale-dependent predictability
  - Roberts & Lean (2008) — FSS for gridded rainfall
  - WMO (2017) — verification standards
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


class VerificationStatus:
    """Status of forecast verification."""
    NOT_EVALUATED = "NOT_EVALUATED"
    EVALUATED = "EVALUATED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class VerificationResult:
    """Result of forecast verification for a single metric or metric set.

    Attributes:
        status: NOT_EVALUATED / EVALUATED / INSUFFICIENT_DATA.
        metrics: Dictionary of metric name -> value.
        n_samples: Number of paired samples used.
        method: Verification method description.
        notes: Additional notes.
    """
    status: str = VerificationStatus.NOT_EVALUATED
    metrics: dict[str, float] = field(default_factory=dict)
    n_samples: int = 0
    method: str = "pairwise_comparison"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "status": self.status,
            "metrics": self.metrics,
            "n_samples": self.n_samples,
            "method": self.method,
            "notes": self.notes,
        }


def compute_mae(forecast: np.ndarray, observed: np.ndarray) -> float:
    """Mean Absolute Error (mm/h)."""
    return float(np.mean(np.abs(forecast - observed)))


def compute_rmse(forecast: np.ndarray, observed: np.ndarray) -> float:
    """Root Mean Square Error (mm/h)."""
    return float(np.sqrt(np.mean((forecast - observed) ** 2)))


def compute_bias(forecast: np.ndarray, observed: np.ndarray) -> float:
    """Bias (mean forecast − mean observed). Positive = overforecast."""
    return float(np.mean(forecast) - np.mean(observed))


def compute_correlation(forecast: np.ndarray, observed: np.ndarray) -> float:
    """Pearson correlation coefficient between forecast and observed fields."""
    f_flat = forecast.ravel()
    o_flat = observed.ravel()
    if np.std(f_flat) < 1e-12 or np.std(o_flat) < 1e-12:
        return 0.0  # constant field has zero correlation
    return float(np.corrcoef(f_flat, o_flat)[0, 1])


def compute_csi(
    forecast: np.ndarray,
    observed: np.ndarray,
    threshold: float = 0.1,
) -> float:
    """Critical Success Index (CSI) for a rain/no-rain threshold (mm/h).

    CSI = hits / (hits + misses + false_alarms)
    """
    f_rain = forecast >= threshold
    o_rain = observed >= threshold
    hits = np.sum(f_rain & o_rain)
    misses = np.sum(~f_rain & o_rain)
    false_alarms = np.sum(f_rain & ~o_rain)
    denom = hits + misses + false_alarms
    return float(hits / denom) if denom > 0 else 0.0


def compute_pod(
    forecast: np.ndarray,
    observed: np.ndarray,
    threshold: float = 0.1,
) -> float:
    """Probability of Detection (POD) for a rain/no-rain threshold (mm/h).

    POD = hits / (hits + misses)
    """
    f_rain = forecast >= threshold
    o_rain = observed >= threshold
    hits = np.sum(f_rain & o_rain)
    misses = np.sum(~f_rain & o_rain)
    denom = hits + misses
    return float(hits / denom) if denom > 0 else 0.0


def compute_far(
    forecast: np.ndarray,
    observed: np.ndarray,
    threshold: float = 0.1,
) -> float:
    """False Alarm Ratio (FAR) for a rain/no-rain threshold (mm/h).

    FAR = false_alarms / (hits + false_alarms)
    """
    f_rain = forecast >= threshold
    o_rain = observed >= threshold
    hits = np.sum(f_rain & o_rain)
    false_alarms = np.sum(f_rain & ~o_rain)
    denom = hits + false_alarms
    return float(false_alarms / denom) if denom > 0 else 0.0


def compute_ets(
    forecast: np.ndarray,
    observed: np.ndarray,
    threshold: float = 0.1,
) -> float:
    """Equitable Threat Score (ETS / Gilbert Skill Score) for a threshold (mm/h).

    ETS = (hits - hits_random) / (hits + misses + false_alarms - hits_random)
    where hits_random = (hits + misses) * (hits + false_alarms) / total_cells
    """
    f_rain = forecast >= threshold
    o_rain = observed >= threshold
    hits = np.sum(f_rain & o_rain)
    misses = np.sum(~f_rain & o_rain)
    false_alarms = np.sum(f_rain & ~o_rain)
    total = float(forecast.size)
    if total == 0:
        return 0.0

    hits_random = float((hits + misses) * (hits + false_alarms)) / total
    denom = (hits + misses + false_alarms) - hits_random
    return float((hits - hits_random) / denom) if denom > 0 else 0.0


def compute_fss(
    forecast: np.ndarray,
    observed: np.ndarray,
    threshold: float = 1.0,
    window_size: int = 5,
) -> float:
    """Fractions Skill Score (FSS) over spatial neighborhood windows (Roberts & Lean 2008)."""
    f_bin = (forecast >= threshold).astype(np.float64)
    o_bin = (observed >= threshold).astype(np.float64)
    
    # 2D moving average over window_size
    pad = window_size // 2
    f_pad = np.pad(f_bin, pad, mode="constant", constant_values=0.0)
    o_pad = np.pad(o_bin, pad, mode="constant", constant_values=0.0)

    h, w = forecast.shape
    f_frac = np.zeros_like(f_bin)
    o_frac = np.zeros_like(o_bin)

    for i in range(h):
        for j in range(w):
            f_frac[i, j] = np.mean(f_pad[i : i + window_size, j : j + window_size])
            o_frac[i, j] = np.mean(o_pad[i : i + window_size, j : j + window_size])

    mse = np.mean((f_frac - o_frac) ** 2)
    mse_ref = np.mean(f_frac ** 2) + np.mean(o_frac ** 2)
    if mse_ref <= 1e-12:
        return 1.0 if mse <= 1e-12 else 0.0
    return float(1.0 - (mse / mse_ref))


def verify_pair(
    forecast: np.ndarray,
    observed: np.ndarray,
    rain_threshold_mmh: float = 0.1,
) -> VerificationResult:
    """Compute all verification metrics for one (forecast, observed) pair.

    Args:
        forecast: Forecast rainfall field (mm/h).
        observed: Observed rainfall field (mm/h).
        rain_threshold_mmh: Threshold for categorical metrics.

    Returns:
        VerificationResult with all metrics.
    """
    if forecast.shape != observed.shape:
        return VerificationResult(
            status=VerificationStatus.INSUFFICIENT_DATA,
            notes=f"shape mismatch: forecast {forecast.shape} vs observed {observed.shape}",
        )

    metrics = {
        "mae_mmh": compute_mae(forecast, observed),
        "rmse_mmh": compute_rmse(forecast, observed),
        "bias_mmh": compute_bias(forecast, observed),
        "correlation": compute_correlation(forecast, observed),
        "csi": compute_csi(forecast, observed, rain_threshold_mmh),
        "pod": compute_pod(forecast, observed, rain_threshold_mmh),
        "far": compute_far(forecast, observed, rain_threshold_mmh),
        "ets": compute_ets(forecast, observed, rain_threshold_mmh),
    }
    return VerificationResult(
        status=VerificationStatus.EVALUATED,
        metrics=metrics,
        n_samples=1,
        method="pairwise_comparison",
        notes=f"rain_threshold={rain_threshold_mmh} mm/h",
    )


def compute_multi_threshold_verification(
    forecast: np.ndarray,
    observed: np.ndarray,
    thresholds: tuple[float, ...] = (0.1, 1.0, 5.0, 15.0, 30.0),
) -> dict[str, Any]:
    """Compute categorical skill scores across multiple rainfall intensity thresholds."""
    if forecast.shape != observed.shape:
        return {"status": VerificationStatus.INSUFFICIENT_DATA, "thresholds": {}}

    res: dict[str, Any] = {
        "status": VerificationStatus.EVALUATED,
        "continuous": {
            "mae_mmh": compute_mae(forecast, observed),
            "rmse_mmh": compute_rmse(forecast, observed),
            "bias_mmh": compute_bias(forecast, observed),
            "correlation": compute_correlation(forecast, observed),
        },
        "thresholds": {},
    }
    for th in thresholds:
        res["thresholds"][f"th_{th}_mmh"] = {
            "threshold_mmh": th,
            "csi": compute_csi(forecast, observed, th),
            "pod": compute_pod(forecast, observed, th),
            "far": compute_far(forecast, observed, th),
            "ets": compute_ets(forecast, observed, th),
        }
    return res


def no_evaluation_available(reason: str = "") -> VerificationResult:
    """Return a NOT_EVALUATED result (the default until real data exists)."""
    return VerificationResult(
        status=VerificationStatus.NOT_EVALUATED,
        metrics={},
        n_samples=0,
        method="none",
        notes=reason or (
            "No paired (forecast, observation) data available. "
            "Verification requires real-time observations. "
            "Status is NOT_EVALUATED — no skill scores are fabricated."
        ),
    )

