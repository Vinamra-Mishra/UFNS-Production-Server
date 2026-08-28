"""Phase K — Spatial Exceedance Probability Rasters & Ensemble Risk Engine.

Computes 2D flood exceedance probability maps P(h >= 10cm, 20cm, 30cm, 50cm),
probabilistic road impassability confidence intervals, and Brier verification skill scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional

import numpy as np

from services.ingestion.dem import GRID_CELLS
from services.probabilistic.ensemble import (
    EnsembleMember,
    EnsembleSimulationResult,
    generate_ensemble_members,
)
from services.routing.impact import rasterize_line
from services.routing.roads import NETWORK
from services.scenarios.artifacts import get_depth_grid


def calculate_brier_score(prob_grid: np.ndarray, obs_binary_grid: np.ndarray) -> float:
    """Compute Brier Score (BS) measuring the accuracy of probabilistic flood forecasts."""
    p = np.asarray(prob_grid, dtype=np.float64).reshape(-1)
    o = np.asarray(obs_binary_grid, dtype=np.float64).reshape(-1)
    if p.size == 0 or p.size != o.size:
        raise ValueError("Probability and binary observation grids must match in dimension.")
    return float(np.mean((p - o) ** 2))


def calculate_exceedance_probabilities(
    depth_stack: np.ndarray,
    thresholds: tuple[float, ...] = (0.10, 0.20, 0.30, 0.50),
) -> dict[str, Any]:
    """Calculate 2D pixel-wise exceedance probability fields across ensemble depth stack."""
    # depth_stack shape: (M, R, C) where M is member count
    m_count = depth_stack.shape[0]
    results: dict[str, Any] = {}

    for thresh in thresholds:
        tag = f"prob_exceed_{int(thresh * 100)}cm"
        exceed_bool = depth_stack >= thresh
        prob_2d = np.mean(exceed_bool, axis=0)  # Shape (R, C)
        # Summary statistics
        flooded_pixels = int(np.count_nonzero(prob_2d > 0.0))
        high_prob_pixels = int(np.count_nonzero(prob_2d >= 0.50))
        certain_pixels = int(np.count_nonzero(prob_2d >= 0.90))

        results[tag] = {
            "threshold_m": thresh,
            "flooded_pixels_count": flooded_pixels,
            "high_probability_pixels_count": high_prob_pixels,
            "certain_pixels_count": certain_pixels,
            "mean_exceedance_prob": round(float(np.mean(prob_2d)), 4),
            "max_exceedance_prob": round(float(np.max(prob_2d)), 4),
        }

    return results


@dataclass
class ProbabilisticRiskResult:
    """Probabilisticriskresult schema and data model representation."""
    scenario_id: str
    lead_minutes: int
    ensemble_size: int
    members: list[dict[str, Any]]
    confidence_bounds: dict[str, float]
    exceedance_statistics: dict[str, Any]
    probabilistic_road_impacts: list[dict[str, Any]]
    brier_skill_score: float
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "scenario_id": self.scenario_id,
            "lead_minutes": self.lead_minutes,
            "ensemble_size": self.ensemble_size,
            "members": self.members,
            "confidence_bounds": self.confidence_bounds,
            "exceedance_statistics": self.exceedance_statistics,
            "probabilistic_road_impacts": self.probabilistic_road_impacts,
            "brier_skill_score": round(self.brier_skill_score, 4),
            "provenance": self.provenance,
        }


class ProbabilisticRiskEngine:
    """Propagates stochastic precipitation perturbations through 2D flood hydraulic layers."""

    def simulate(
        self,
        scenario_id: str = "S4",
        lead_minutes: int = 110,
        member_count: int = 10,
    ) -> ProbabilisticRiskResult:
        """Run multi-member ensemble propagation and spatial exceedance probability analysis."""
        base_grid = np.array(get_depth_grid(scenario_id, lead_minutes), dtype=np.float64)
        members = generate_ensemble_members(member_count)

        depth_stack = np.zeros((len(members), base_grid.shape[0], base_grid.shape[1]), dtype=np.float64)
        member_metrics: list[dict[str, Any]] = []

        for idx, m in enumerate(members):
            # Apply intensity multiplier
            m_grid = base_grid * m.rainfall_multiplier
            # Apply spatial advection shift
            if m.spatial_shift_row != 0 or m.spatial_shift_col != 0:
                m_grid = np.roll(m_grid, shift=(m.spatial_shift_row, m.spatial_shift_col), axis=(0, 1))

            depth_stack[idx, :, :] = m_grid
            max_d = float(np.max(m_grid))
            inund_area = float(np.count_nonzero(m_grid >= 0.05) * 900.0)
            member_metrics.append({
                "member_id": m.member_id,
                "name": m.name,
                "percentile_tag": m.percentile_tag,
                "max_depth_m": round(max_d, 3),
                "inundated_area_m2": round(inund_area, 0),
            })

        # Calculate P10, P50, P90 confidence bounds across domain max depths
        all_max_depths = np.array([m["max_depth_m"] for m in member_metrics])
        p10 = float(np.percentile(all_max_depths, 10))
        p50 = float(np.percentile(all_max_depths, 50))
        p90 = float(np.percentile(all_max_depths, 90))
        iqr = float(p90 - p10)

        confidence_bounds = {
            "p10_max_depth_m": round(p10, 3),
            "p50_max_depth_m": round(p50, 3),
            "p90_max_depth_m": round(p90, 3),
            "interquartile_range_m": round(iqr, 3),
        }

        # Calculate 2D Exceedance Probabilities
        exceedance_stats = calculate_exceedance_probabilities(depth_stack)

        # Probabilistic Road Disruption Evaluation
        road_risks: list[dict[str, Any]] = []
        for road in NETWORK.segments:
            r1, c1 = road.start_cell
            r2, c2 = road.end_cell
            cells = rasterize_line(r1, c1, r2, c2)

            member_road_depths: list[float] = []
            for m_idx in range(len(members)):
                h_dim, w_dim = depth_stack.shape[1], depth_stack.shape[2]
                seg_d = [float(depth_stack[m_idx, r, c]) for r, c in cells if 0 <= r < h_dim and 0 <= c < w_dim]
                member_road_depths.append(max(seg_d) if seg_d else 0.0)

            arr_d = np.array(member_road_depths)
            p_impassable = float(np.mean(arr_d >= 0.30))
            p_caution = float(np.mean((arr_d >= 0.10) & (arr_d < 0.30)))
            p_dry = float(np.mean(arr_d < 0.10))

            road_risks.append({
                "road_id": road.road_id,
                "name": f"Road {road.road_id} ({road.start_node}->{road.end_node})",
                "prob_impassable": round(p_impassable, 3),
                "prob_caution": round(p_caution, 3),
                "prob_dry": round(p_dry, 3),
                "expected_depth_m": round(float(np.mean(arr_d)), 3),
                "depth_p90_m": round(float(np.percentile(arr_d, 90)), 3),
            })

        # Brier Verification Score: Compare P50 median binary field vs ensemble prob (h >= 0.10m)
        obs_binary = (base_grid >= 0.10).astype(np.float64)
        prob_10cm = np.mean(depth_stack >= 0.10, axis=0)
        brier = calculate_brier_score(prob_10cm, obs_binary)

        provenance = {
            "classification": "ENSEMBLE_PROBABILISTIC_FLOOD_FORECAST",
            "scenario_id": scenario_id,
            "lead_minutes": lead_minutes,
            "ensemble_members_count": len(members),
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
            "methodology": "10-member stochastic Monte Carlo perturbation with spatial advection tracking",
        }

        return ProbabilisticRiskResult(
            scenario_id=scenario_id,
            lead_minutes=lead_minutes,
            ensemble_size=len(members),
            members=member_metrics,
            confidence_bounds=confidence_bounds,
            exceedance_statistics=exceedance_stats,
            probabilistic_road_impacts=road_risks,
            brier_skill_score=brier,
            provenance=provenance,
        )


GLOBAL_PROBABILISTIC_ENGINE = ProbabilisticRiskEngine()
