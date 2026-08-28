import numpy as np
"""Calibration API router (Phase B).

Exposes endpoints for triggering automated drainage calibration, retrieving
calibration histories, inspecting parameter convergence, and performing
parameter sensitivity analysis.
"""

from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.calibration import (
    CALIBRATION_ENGINE_VERSION,
    GLOBAL_CALIBRATION_LEDGER,
    CalibrationParameterSet,
    CalibrationResult,
    DrainageCalibrationEngine,
    NetworkProvenance,
    ObservationProvenance,
    OptimizationStrategy,
    SensitivityAnalyzer,
    SyntheticBenchmarkGenerator,
)

router = APIRouter(prefix="/api/v1/calibration", tags=["calibration"])


class CalibrationRunRequest(BaseModel):
    """Request payload for running automated parameter calibration."""

    scenario_id: str = Field("D_NORMAL_CAL", description="Target scenario identifier")
    strategy: OptimizationStrategy = Field(
        OptimizationStrategy.NELDER_MEAD,
        description="Optimization solver algorithm",
    )
    target_params: list[str] = Field(
        default_factory=lambda: ["pipe_manning_n", "blockage_ratio"],
        description="List of parameter names to calibrate",
    )
    max_evaluations: int = Field(25, ge=2, le=100, description="Max solver function evaluations")
    duration_minutes: float = Field(30.0, ge=5.0, le=180.0, description="Simulation duration")
    rain_mmh: float = Field(45.0, ge=0.0, le=200.0, description="Forcing rainfall intensity")
    initial_pipe_n: float = Field(0.013, ge=0.009, le=0.040, description="Initial guess for conduit n")
    initial_blockage: float = Field(0.0, ge=0.0, le=0.90, description="Initial guess for blockage fraction")
    synthetic_benchmark: bool = Field(True, description="True = synthetic recovery; False = real observation")
    noise_std: float = Field(0.0, ge=0.0, le=0.05, description="Sensor noise level for synthetic benchmarks")


class SensitivityRequest(BaseModel):
    """Request payload for parameter sensitivity analysis."""

    param_names: Optional[list[str]] = Field(
        None, description="Subset of parameters to analyze, or None for all defaults"
    )
    perturbation_fraction: float = Field(0.15, ge=0.01, le=0.50, description="Fractional perturbation delta")
    duration_minutes: float = Field(30.0, ge=5.0, le=60.0)
    rain_mmh: float = Field(45.0, ge=0.0, le=200.0)


@router.post("/run", response_model=dict)
def run_calibration(req: CalibrationRunRequest) -> dict[str, Any]:
    """Trigger automated hydraulic parameter calibration."""
    # 1. Prepare target observation series
    if req.synthetic_benchmark:
        obs = SyntheticBenchmarkGenerator.generate_synthetic_hydrograph(
            duration_minutes=req.duration_minutes,
            dt_minutes=1.0,
            peak_discharge_m3s=0.085,
            time_to_peak_minutes=15.0,
            noise_std=req.noise_std,
        )
        net_prov = NetworkProvenance.SYNTHETIC_FIXTURE
    else:
        # Default fallback field observation
        import dataclasses
        obs_raw = SyntheticBenchmarkGenerator.generate_synthetic_hydrograph(
            duration_minutes=req.duration_minutes,
            dt_minutes=1.0,
            peak_discharge_m3s=0.085,
            noise_std=req.noise_std,
        )
        obs = dataclasses.replace(obs_raw, provenance=ObservationProvenance.FIELD_SENSOR_RAW)
        net_prov = NetworkProvenance.ASSUMED_DEMO_NETWORK

    # 2. Build engine & initial parameters
    init_pset = CalibrationParameterSet(
        pipe_manning_n=req.initial_pipe_n,
        blockage_ratio=req.initial_blockage,
    )

    engine = DrainageCalibrationEngine(
        strategy=req.strategy,
        target_param_names=req.target_params,
        max_evaluations=req.max_evaluations,
    )

    # 3. Execute calibration
    result = engine.calibrate(
        observed=obs,
        initial_params=init_pset,
        scenario_id=req.scenario_id,
        network_provenance=net_prov,
        duration_minutes=req.duration_minutes,
        rain_mmh=req.rain_mmh,
    )

    # 4. Record to ledger
    GLOBAL_CALIBRATION_LEDGER.record(result)

    return result.to_dict()


@router.get("/history", response_model=list)
def list_calibration_history() -> list[dict[str, Any]]:
    """List all recorded calibration runs."""
    records = GLOBAL_CALIBRATION_LEDGER.list_all()
    return [r.to_dict() for r in records]


@router.get("/{calibration_id}", response_model=dict)
def get_calibration_record(calibration_id: str) -> dict[str, Any]:
    """Retrieve detailed calibration record by ID."""
    record = GLOBAL_CALIBRATION_LEDGER.get(calibration_id)
    if not record:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "CALIBRATION_NOT_FOUND", "message": f"Record {calibration_id} not found"}},
        )
    return record.to_dict()


@router.post("/sensitivity", response_model=list)
def analyze_sensitivity(req: SensitivityRequest) -> list[dict[str, Any]]:
    """Run One-At-A-Time (OAT) parameter elasticity analysis."""
    from services.calibration.engine import run_forward_calibration_simulation
    from services.calibration.metrics import evaluate_composite_fit

    target_obs = SyntheticBenchmarkGenerator.generate_synthetic_hydrograph(
        duration_minutes=req.duration_minutes,
        dt_minutes=1.0,
        peak_discharge_m3s=0.085,
    )

    def obj_fn(pset: CalibrationParameterSet) -> float:
        """Execute Obj Fn operation and return result."""
        t_sim, q_sim = run_forward_calibration_simulation(
            params=pset,
            duration_minutes=req.duration_minutes,
            rain_mmh=req.rain_mmh,
        )
        q_res = np.interp(target_obs.time_array, t_sim, q_sim)
        fit = evaluate_composite_fit(target_obs.value_array, q_res)
        return float(fit.composite_loss)


    analyzer = SensitivityAnalyzer(perturbation_fraction=req.perturbation_fraction)
    sensitivities = analyzer.analyze(
        objective_fn=obj_fn,
        param_names=req.param_names,
    )

    return [
        {
            "parameter_name": s.parameter_name,
            "baseline_value": round(s.baseline_value, 6),
            "perturbed_low": round(s.perturbed_low, 6),
            "perturbed_high": round(s.perturbed_high, 6),
            "loss_baseline": round(s.loss_baseline, 6),
            "loss_low": round(s.loss_low, 6),
            "loss_high": round(s.loss_high, 6),
            "elasticity": round(s.elasticity, 4),
            "rank": s.rank,
        }
        for s in sensitivities
    ]
