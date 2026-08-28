"""Phase I — Benchmark Datasets Catalog and Evaluation Engine.

Provides automated model evaluation against reference hydrodynamic baselines.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from services.scenarios.artifacts import get_depth_grid, load_results
from services.validation.metrics import (
    calculate_contingency_scores,
    calculate_depth_errors,
    calculate_kge,
    calculate_nse,
)


@dataclass(frozen=True)
class BenchmarkDataset:
    """Benchmarkdataset schema and data model representation."""
    benchmark_id: str
    name: str
    source: str
    reference_scenario_id: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return asdict(self)


BENCHMARK_CATALOG: dict[str, BenchmarkDataset] = {
    "BENCHMARK_S3_CLEAN": BenchmarkDataset(
        benchmark_id="BENCHMARK_S3_CLEAN",
        name="M5-S3 High-Efficiency Reference Drainage Benchmark",
        source="SWMM5_SAINT_VENANT_HIGH_RES",
        reference_scenario_id="S3",
        description="Clean, unblocked 1D drainage network with full orifice exchange (Cd = 0.60) serving as ideal conveyance baseline.",
    ),
    "BENCHMARK_S4_SURCHARGE": BenchmarkDataset(
        benchmark_id="BENCHMARK_S4_SURCHARGE",
        name="M5-S4 Hydraulic Surcharge & Blockage Benchmark",
        source="SWMM5_BLOCKED_IN004",
        reference_scenario_id="S4",
        description="Severe surcharge benchmark with 80% culvert sediment clogging at Outfall IN-004.",
    ),
    "BENCHMARK_S1_DESIGN_STORM": BenchmarkDataset(
        benchmark_id="BENCHMARK_S1_DESIGN_STORM",
        name="M5-S1 Design Storm Standard Benchmark",
        source="SYNTHETIC_DESIGN_P1",
        reference_scenario_id="S1",
        description="Standard 25-year design storm baseline under uniform low-intensity rainfall.",
    ),
}


@dataclass
class BenchmarkEvaluationResult:
    """Benchmarkevaluationresult schema and data model representation."""
    scenario_id: str
    lead_minutes: int
    benchmark_id: str
    benchmark_name: str
    hydrograph_metrics: dict[str, Any]
    spatial_contingency: dict[str, Any]
    depth_errors: dict[str, Any]
    mass_conservation_residual_pct: Optional[float]
    scientific_validation_tier: str
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "scenario_id": self.scenario_id,
            "lead_minutes": self.lead_minutes,
            "benchmark_id": self.benchmark_id,
            "benchmark_name": self.benchmark_name,
            "hydrograph_metrics": self.hydrograph_metrics,
            "spatial_contingency": self.spatial_contingency,
            "depth_errors": self.depth_errors,
            "mass_conservation_residual_pct": round(self.mass_conservation_residual_pct, 6) if self.mass_conservation_residual_pct is not None else None,
            "scientific_validation_tier": self.scientific_validation_tier,
            "provenance": self.provenance,
        }


class BenchmarkEngine:
    """Evaluates simulation models against scientific hydrodynamic benchmark standards."""

    def evaluate(
        self,
        scenario_id: str = "S4",
        lead_minutes: int = 110,
        benchmark_id: str = "BENCHMARK_S3_CLEAN",
    ) -> BenchmarkEvaluationResult:
        """Run quantitative model validation against a reference benchmark dataset."""
        clean_bid = benchmark_id.upper()
        if clean_bid not in BENCHMARK_CATALOG:
            clean_bid = "BENCHMARK_S3_CLEAN"
        benchmark = BENCHMARK_CATALOG[clean_bid]

        # 1. Fetch simulation and benchmark 2D depth grids
        sim_grid = np.array(get_depth_grid(scenario_id, lead_minutes), dtype=np.float64)
        ref_grid = np.array(get_depth_grid(benchmark.reference_scenario_id, lead_minutes), dtype=np.float64)

        # 2. Compute 1D hydrograph surrogate metrics (along central drain column 67)
        sim_slice = sim_grid[:, 67]
        ref_slice = ref_grid[:, 67]
        nse = calculate_nse(sim_slice, ref_slice)
        kge_data = calculate_kge(sim_slice, ref_slice)

        hydrograph_metrics = {
            "nash_sutcliffe_efficiency_nse": round(nse, 4),
            "kling_gupta_efficiency_kge": kge_data["kge"],
            "correlation_r": kge_data["correlation_r"],
            "variability_ratio_alpha": kge_data["variability_alpha"],
            "bias_ratio_beta": kge_data["bias_beta"],
        }

        # 3. Compute 2D spatial contingency metrics
        contingency = calculate_contingency_scores(sim_grid, ref_grid, threshold_m=0.05)

        # 4. Compute continuous depth errors
        depth_errors = calculate_depth_errors(sim_grid, ref_grid)

        # 5. Mass continuity check from scenario store
        all_results = load_results()
        sc_res = all_results.get(scenario_id, {})
        ledger = sc_res.get("mass_ledger", {}) if isinstance(sc_res, dict) else {}
        raw_residual = ledger.get("relative_residual", ledger.get("residual_fraction_pct"))
        if raw_residual is not None:
            residual_err: Optional[float] = abs(float(raw_residual)) * (100.0 if "relative_residual" in ledger else 1.0)
        else:
            residual_err = None

        # Scientific Tier Classification
        csi = contingency["critical_success_index_csi"]
        is_self_eval = (benchmark.reference_scenario_id == scenario_id)
        if not is_self_eval and nse >= 0.75 and csi >= 0.70 and residual_err is not None and residual_err <= 0.05:
            tier = "TIER_1_PUBLICATION_GRADE"
        elif nse >= 0.50 and csi >= 0.50:
            tier = "TIER_2_OPERATIONAL_GRADE"
        else:
            tier = "TIER_3_DIAGNOSTIC_GRADE"

        provenance = {
            "classification": "HYDRODYNAMIC_MODEL_VALIDATION",
            "scenario_id": scenario_id,
            "lead_minutes": lead_minutes,
            "benchmark_dataset": benchmark.name,
            "self_consistency_check": is_self_eval,
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
            "guideline": "MoES / WMO-No. 1072 Hydrological Modeling Benchmarking Standard",
        }

        return BenchmarkEvaluationResult(
            scenario_id=scenario_id,
            lead_minutes=lead_minutes,
            benchmark_id=clean_bid,
            benchmark_name=benchmark.name,
            hydrograph_metrics=hydrograph_metrics,
            spatial_contingency=contingency,
            depth_errors=depth_errors,
            mass_conservation_residual_pct=residual_err,
            scientific_validation_tier=tier,
            provenance=provenance,
        )


GLOBAL_BENCHMARK_ENGINE = BenchmarkEngine()
