"""Hydrological and hydraulic goodness-of-fit metrics (Phase B).

Provides standard and specialized objective functions:
- Nash-Sutcliffe Efficiency (NSE)
- Kling-Gupta Efficiency (KGE: correlation, variability, bias decomposition)
- Peak Flow Error (PFE: percentage error of flood peak magnitude)
- Time-to-Peak Error (TPE: flash flood wave arrival timing difference)
- Percent Bias (PBIAS: mass volume conservation)
- Root Mean Squared Error (RMSE)
- Spatial Inundation Depth RMSE (for 2D flood depth maps)
- CompositeGoodnessOfFit & Multi-objective Loss evaluation
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np


def nash_sutcliffe_efficiency(obs: Sequence[float] | np.ndarray, sim: Sequence[float] | np.ndarray) -> float:
    """Compute Nash-Sutcliffe Efficiency (NSE) between observed and simulated series.

    NSE = 1 - (sum((Q_obs - Q_sim)^2) / sum((Q_obs - mean(Q_obs))^2))
    Range: (-inf, 1.0]. NSE = 1 is a perfect match. NSE > 0 indicates model is
    better than the mean observed baseline.
    """
    o = np.asarray(obs, dtype=np.float64)
    s = np.asarray(sim, dtype=np.float64)
    if o.shape != s.shape:
        raise ValueError(f"Shape mismatch: obs {o.shape} != sim {s.shape}")
    if o.size < 2:
        raise ValueError("Series must contain at least 2 data points for NSE")

    numerator = float(np.sum((o - s) ** 2))
    mean_obs = float(np.mean(o))
    denominator = float(np.sum((o - mean_obs) ** 2))

    if denominator < 1e-12:
        # Zero variance in observation: perfect if match, else -inf
        return 1.0 if numerator < 1e-12 else -1e6

    return 1.0 - (numerator / denominator)


def kling_gupta_efficiency(
    obs: Sequence[float] | np.ndarray,
    sim: Sequence[float] | np.ndarray,
    s_r: float = 1.0,
    s_alpha: float = 1.0,
    s_beta: float = 1.0,
) -> tuple[float, float, float, float]:
    """Compute 2012 Kling-Gupta Efficiency (KGE) and its sub-components.

    Decomposition:
    - r: Pearson correlation coefficient (timing & shape)
    - alpha: ratio of standard deviations sigma_sim / sigma_obs (variability)
    - beta: ratio of means mu_sim / mu_obs (volume bias)

    KGE = 1 - sqrt( (s_r*(r - 1))^2 + (s_alpha*(alpha - 1))^2 + (s_beta*(beta - 1))^2 )

    Returns:
        (kge, r, alpha, beta)
    """
    o = np.asarray(obs, dtype=np.float64)
    s = np.asarray(sim, dtype=np.float64)
    if o.shape != s.shape:
        raise ValueError(f"Shape mismatch: obs {o.shape} != sim {s.shape}")
    if o.size < 2:
        raise ValueError("Series must contain at least 2 data points for KGE")

    mu_o = float(np.mean(o))
    mu_s = float(np.mean(s))
    sigma_o = float(np.std(o, ddof=1))
    sigma_s = float(np.std(s, ddof=1))

    # 1. Pearson correlation coefficient r
    if sigma_o < 1e-12 or sigma_s < 1e-12:
        # Zero variance: if both constants and equal, r=1, else r=0
        r = 1.0 if abs(mu_o - mu_s) < 1e-6 else 0.0
    else:
        cov = float(np.cov(o, s)[0, 1])
        r = float(cov / (sigma_o * sigma_s))
        r = max(-1.0, min(1.0, r))

    # 2. Variability ratio alpha (sigma_sim / sigma_obs)
    alpha = (sigma_s / sigma_o) if sigma_o > 1e-12 else (1.0 if sigma_s < 1e-12 else 10.0)

    # 3. Bias ratio beta (mu_sim / mu_obs)
    beta = (mu_s / mu_o) if abs(mu_o) > 1e-12 else (1.0 if abs(mu_s) < 1e-12 else 10.0)

    ed = math.sqrt(
        (s_r * (r - 1.0)) ** 2
        + (s_alpha * (alpha - 1.0)) ** 2
        + (s_beta * (beta - 1.0)) ** 2
    )
    kge = 1.0 - ed
    return float(kge), float(r), float(alpha), float(beta)


def peak_flow_error(obs: Sequence[float] | np.ndarray, sim: Sequence[float] | np.ndarray) -> float:
    """Compute Peak Flow Percentage Error (PFE).

    PFE = |max(Q_sim) - max(Q_obs)| / max(Q_obs) * 100%
    """
    o = np.asarray(obs, dtype=np.float64)
    s = np.asarray(sim, dtype=np.float64)
    peak_o = float(np.max(o)) if o.size > 0 else 0.0
    peak_s = float(np.max(s)) if s.size > 0 else 0.0

    if peak_o < 1e-12:
        return 0.0 if peak_s < 1e-12 else 100.0
    return float(abs(peak_s - peak_o) / peak_o * 100.0)


def time_to_peak_error(
    obs: Sequence[float] | np.ndarray,
    sim: Sequence[float] | np.ndarray,
    dt_minutes: float = 1.0,
) -> float:
    """Compute Time-to-Peak Error (TPE) in minutes.

    TPE = |t_peak,sim - t_peak,obs|
    """
    o = np.asarray(obs, dtype=np.float64)
    s = np.asarray(sim, dtype=np.float64)
    if o.size == 0 or s.size == 0:
        return 0.0

    idx_peak_o = int(np.argmax(o))
    idx_peak_s = int(np.argmax(s))
    return float(abs(idx_peak_s - idx_peak_o) * dt_minutes)


def percent_bias(obs: Sequence[float] | np.ndarray, sim: Sequence[float] | np.ndarray) -> float:
    """Compute Percent Bias (PBIAS).

    PBIAS = sum(Q_sim - Q_obs) / sum(Q_obs) * 100%
    Positive value indicates over-estimation bias; negative indicates under-estimation.
    """
    o = np.asarray(obs, dtype=np.float64)
    s = np.asarray(sim, dtype=np.float64)
    sum_o = float(np.sum(o))
    sum_s = float(np.sum(s))

    if abs(sum_o) < 1e-12:
        return 0.0 if abs(sum_s) < 1e-12 else 100.0
    return float((sum_s - sum_o) / sum_o * 100.0)


def root_mean_squared_error(obs: Sequence[float] | np.ndarray, sim: Sequence[float] | np.ndarray) -> float:
    """Compute Root Mean Squared Error (RMSE)."""
    o = np.asarray(obs, dtype=np.float64)
    s = np.asarray(sim, dtype=np.float64)
    if o.shape != s.shape:
        raise ValueError(f"Shape mismatch: obs {o.shape} != sim {s.shape}")
    if o.size == 0:
        return 0.0
    return float(math.sqrt(np.mean((o - s) ** 2)))


def spatial_depth_rmse(
    obs_2d: np.ndarray,
    sim_2d: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> float:
    """Compute 2D spatial surface water depth RMSE on active domain cells."""
    if obs_2d.shape != sim_2d.shape:
        raise ValueError(f"2D shape mismatch: obs {obs_2d.shape} != sim {sim_2d.shape}")
    if mask is not None:
        if mask.shape != obs_2d.shape:
            raise ValueError("Mask shape must match 2D depth array")
        o_eval = obs_2d[mask]
        s_eval = sim_2d[mask]
    else:
        o_eval = obs_2d.ravel()
        s_eval = sim_2d.ravel()

    if o_eval.size == 0:
        return 0.0
    return float(math.sqrt(np.mean((o_eval - s_eval) ** 2)))


@dataclass(frozen=True)
class CompositeGoodnessOfFit:
    """Comprehensive multi-metric summary and weighted composite loss."""

    nse: float
    kge: float
    r: float
    alpha: float
    beta: float
    pfe_pct: float
    tpe_minutes: float
    pbias_pct: float
    rmse: float
    spatial_rmse: Optional[float]
    composite_loss: float

    def to_dict(self) -> dict[str, float | None]:
        """Execute To Dict operation and return result."""
        return {
            "nse": round(self.nse, 6),
            "kge": round(self.kge, 6),
            "r": round(self.r, 6),
            "alpha": round(self.alpha, 6),
            "beta": round(self.beta, 6),
            "pfe_pct": round(self.pfe_pct, 4),
            "tpe_minutes": round(self.tpe_minutes, 2),
            "pbias_pct": round(self.pbias_pct, 4),
            "rmse": round(self.rmse, 6),
            "spatial_rmse": round(self.spatial_rmse, 6) if self.spatial_rmse is not None else None,
            "composite_loss": round(self.composite_loss, 6),
        }


def evaluate_composite_fit(
    obs: Sequence[float] | np.ndarray,
    sim: Sequence[float] | np.ndarray,
    dt_minutes: float = 1.0,
    obs_spatial: Optional[np.ndarray] = None,
    sim_spatial: Optional[np.ndarray] = None,
    spatial_mask: Optional[np.ndarray] = None,
    w_kge: float = 0.50,
    w_pfe: float = 0.25,
    w_pbias: float = 0.15,
    w_spatial: float = 0.10,
) -> CompositeGoodnessOfFit:
    """Evaluate full suite of calibration metrics and compute weighted composite loss.

    Loss function formulation:
    Loss = w_kge * max(0.0, 1.0 - KGE)
         + w_pfe * (PFE / 100.0)
         + w_pbias * (|PBIAS| / 100.0)
         + w_spatial * (spatial_rmse / (max(obs_spatial) + 0.01))
    """
    nse_val = nash_sutcliffe_efficiency(obs, sim)
    kge_val, r_val, alpha_val, beta_val = kling_gupta_efficiency(obs, sim)
    pfe_val = peak_flow_error(obs, sim)
    tpe_val = time_to_peak_error(obs, sim, dt_minutes=dt_minutes)
    pbias_val = percent_bias(obs, sim)
    rmse_val = root_mean_squared_error(obs, sim)

    s_rmse: Optional[float] = None
    if obs_spatial is not None and sim_spatial is not None:
        s_rmse = spatial_depth_rmse(obs_spatial, sim_spatial, mask=spatial_mask)

    # Composite loss calculation (minimization objective, 0 is perfect)
    kge_penalty = max(0.0, 1.0 - kge_val)
    pfe_penalty = min(5.0, pfe_val / 100.0)
    pbias_penalty = min(5.0, abs(pbias_val) / 100.0)

    loss = w_kge * kge_penalty + w_pfe * pfe_penalty + w_pbias * pbias_penalty
    if s_rmse is not None and obs_spatial is not None:
        max_obs_s = float(np.max(obs_spatial)) if obs_spatial.size > 0 else 1.0
        s_penalty = min(5.0, s_rmse / max(max_obs_s, 0.01))
        loss += w_spatial * s_penalty
    elif w_spatial > 0:
        # Re-normalize weights if spatial comparison not present
        total_w = w_kge + w_pfe + w_pbias
        if total_w > 0:
            loss = loss / total_w

    return CompositeGoodnessOfFit(
        nse=nse_val,
        kge=kge_val,
        r=r_val,
        alpha=alpha_val,
        beta=beta_val,
        pfe_pct=pfe_val,
        tpe_minutes=tpe_val,
        pbias_pct=pbias_val,
        rmse=rmse_val,
        spatial_rmse=s_rmse,
        composite_loss=float(loss),
    )
