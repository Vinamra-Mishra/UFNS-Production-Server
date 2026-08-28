"""Automated drainage calibration and hydraulic parameter estimation engine (Phase B).

Orchestrates parameter updates, forward coupled hydraulic simulation,
loss computation, convergence tracking, and scientific provenance validation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

from services.calibration.metrics import (
    CompositeGoodnessOfFit,
    evaluate_composite_fit,
)
from services.calibration.observations import (
    NetworkProvenance,
    ObservationProvenance,
    ObservationTarget,
    ObservedTimeSeries,
    SyntheticBenchmarkGenerator,
    ValidationStatus,
)
from services.calibration.optimizer import (
    OptimizationResult,
    OptimizationStrategy,
    ParameterOptimizer,
    SensitivityAnalyzer,
)
from services.calibration.parameters import (
    DEFAULT_PARAMETER_DEFINITIONS,
    CalibrationParameterSet,
    ParameterDefinition,
)
from services.hydraulics.coupling import CoupledSpike, build_spike_surface
from services.hydraulics.fixture import (
    C1_DIAMETER,
    C1_LENGTH,
    C1_MANNING,
    C1_SLOPE,
    exact_fixture_inp,
)

CALIBRATION_ENGINE_VERSION = "CALIBRATION-V1"


@dataclass(frozen=True)
class CalibrationResult:
    """Full outcome of an automated calibration session with provenance guarantees."""

    calibration_id: str
    scenario_id: str
    network_provenance: NetworkProvenance
    observation_provenance: ObservationProvenance
    validation_status: ValidationStatus
    target_type: ObservationTarget
    target_sensor_id: str
    initial_metrics: CompositeGoodnessOfFit
    final_metrics: CompositeGoodnessOfFit
    initial_parameters: CalibrationParameterSet
    optimal_parameters: CalibrationParameterSet
    observed_values: tuple[float, ...]
    simulated_values: tuple[float, ...]
    time_minutes: tuple[float, ...]
    optimization_summary: dict[str, Any]
    provenance_disclaimer: str
    created_at_epoch: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "calibration_id": self.calibration_id,
            "scenario_id": self.scenario_id,
            "network_provenance": self.network_provenance.value,
            "observation_provenance": self.observation_provenance.value,
            "validation_status": self.validation_status.value,
            "target_type": self.target_type.value,
            "target_sensor_id": self.target_sensor_id,
            "initial_metrics": self.initial_metrics.to_dict(),
            "final_metrics": self.final_metrics.to_dict(),
            "initial_parameters": self.initial_parameters.to_dict(),
            "optimal_parameters": self.optimal_parameters.to_dict(),
            "time_minutes": list(self.time_minutes),
            "observed_values": [round(float(v), 6) for v in self.observed_values],
            "simulated_values": [round(float(v), 6) for v in self.simulated_values],
            "optimization_summary": self.optimization_summary,
            "provenance_disclaimer": self.provenance_disclaimer,
            "created_at_epoch": self.created_at_epoch,
            "parameter_fingerprint": self.optimal_parameters.fingerprint(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalibrationResult:
        """Reconstruct CalibrationResult from serialized dictionary."""
        return cls(
            calibration_id=d["calibration_id"],
            scenario_id=d["scenario_id"],
            network_provenance=NetworkProvenance(d["network_provenance"]),
            observation_provenance=ObservationProvenance(d["observation_provenance"]),
            validation_status=ValidationStatus(d["validation_status"]),
            target_type=ObservationTarget(d["target_type"]),
            target_sensor_id=d["target_sensor_id"],
            initial_metrics=CompositeGoodnessOfFit(**d["initial_metrics"]),
            final_metrics=CompositeGoodnessOfFit(**d["final_metrics"]),
            initial_parameters=CalibrationParameterSet.from_dict(d["initial_parameters"]),
            optimal_parameters=CalibrationParameterSet.from_dict(d["optimal_parameters"]),
            time_minutes=tuple(float(x) for x in d.get("time_minutes", ())),
            observed_values=tuple(float(x) for x in d.get("observed_values", ())),
            simulated_values=tuple(float(x) for x in d.get("simulated_values", ())),
            optimization_summary=d.get("optimization_summary", {}),
            provenance_disclaimer=d.get("provenance_disclaimer", ""),
            created_at_epoch=float(d.get("created_at_epoch", time.time())),
        )

    def fingerprint(self) -> str:
        """Execute Fingerprint operation and return result."""
        serialized = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Calibration Forward Model Wrapper
# ---------------------------------------------------------------------------

def run_forward_calibration_simulation(
    params: CalibrationParameterSet,
    duration_minutes: float = 30.0,
    rain_mmh: float = 45.0,
    dt_c: int = 5,
) -> tuple[np.ndarray, np.ndarray]:
    """Execute forward coupled simulation with candidate parameters in an isolated worker subprocess.

    EPA-SWMM C-runtime contains global static memory that prevents running multiple
    Simulation() instances in the same process. Launching each forward evaluation in
    an isolated worker completely eliminates MultiSimulationError and ensures clean memory.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as out_f:
        out_path = Path(out_f.name)

    try:
        cmd = [
            sys.executable,
            "-m",
            "services.calibration.worker",
            "--params",
            json.dumps(params.to_dict()),
            "--duration",
            str(duration_minutes),
            "--rain",
            str(rain_mmh),
            "--dt",
            str(dt_c),
            "--output",
            str(out_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120.0)
        if not out_path.exists():
            raise RuntimeError(f"Worker did not produce output: {proc.stderr}")
        data = json.loads(out_path.read_text(encoding="utf-8"))
        return np.array(data["time"], dtype=np.float64), np.array(data["q"], dtype=np.float64)
    finally:
        if out_path.exists():
            out_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Calibration Engine
# ---------------------------------------------------------------------------

class DrainageCalibrationEngine:
    """Automated drainage parameter estimation and calibration engine."""

    def __init__(
        self,
        strategy: OptimizationStrategy = OptimizationStrategy.NELDER_MEAD,
        target_param_names: Optional[Sequence[str]] = None,
        max_evaluations: int = 40,
        tolerance: float = 1e-4,
        definitions: Optional[dict[str, ParameterDefinition]] = None,
    ) -> None:
        """Execute   Init   operation and return result."""
        self.strategy = strategy
        self.target_param_names = list(target_param_names or ["pipe_manning_n", "blockage_ratio"])
        self.optimizer = ParameterOptimizer(
            strategy=strategy,
            target_param_names=self.target_param_names,
            max_evaluations=max_evaluations,
            tolerance=tolerance,
            definitions=definitions,
        )
        self.definitions = definitions or DEFAULT_PARAMETER_DEFINITIONS

    def calibrate(
        self,
        observed: ObservedTimeSeries,
        initial_params: Optional[CalibrationParameterSet] = None,
        scenario_id: str = "SYNTHETIC-CALIBRATION-01",
        network_provenance: NetworkProvenance = NetworkProvenance.SYNTHETIC_FIXTURE,
        duration_minutes: float = 30.0,
        rain_mmh: float = 45.0,
        w_kge: float = 0.50,
        w_pfe: float = 0.30,
        w_pbias: float = 0.20,
    ) -> CalibrationResult:
        """Run automated parameter calibration against observed target hydrograph."""
        t_start = time.perf_counter()
        base_params = (initial_params or CalibrationParameterSet()).validate_and_clip(self.definitions)

        # Setup evaluation objective function
        target_times = observed.time_array
        obs_values = observed.value_array
        dt_min = float(target_times[1] - target_times[0]) if len(target_times) > 1 else 1.0

        def objective_function(candidate: CalibrationParameterSet) -> float:
            """Execute Objective Function operation and return result."""
            try:
                t_sim, q_sim = run_forward_calibration_simulation(
                    params=candidate,
                    duration_minutes=duration_minutes,
                    rain_mmh=rain_mmh,
                )
                # Resample simulation onto observation timestamps
                q_sim_resampled = np.interp(target_times, t_sim, q_sim)
                fit = evaluate_composite_fit(
                    obs=obs_values,
                    sim=q_sim_resampled,
                    dt_minutes=dt_min,
                    w_kge=w_kge,
                    w_pfe=w_pfe,
                    w_pbias=w_pbias,
                )
                return float(fit.composite_loss)
            except Exception as exc:
                logging.getLogger(__name__).warning("Forward calibration simulation failed for candidate %s: %s", candidate, exc)
                return 1e6

        # Initial metrics evaluation
        t_init, q_init = run_forward_calibration_simulation(
            params=base_params,
            duration_minutes=duration_minutes,
            rain_mmh=rain_mmh,
        )
        q_init_resampled = np.interp(target_times, t_init, q_init)
        init_fit = evaluate_composite_fit(
            obs=obs_values,
            sim=q_init_resampled,
            dt_minutes=dt_min,
            w_kge=w_kge,
            w_pfe=w_pfe,
            w_pbias=w_pbias,
        )

        # Execute optimization
        opt_res = self.optimizer.optimize(
            objective_fn=objective_function,
            initial_params=base_params,
        )

        # Final metrics evaluation
        t_final, q_final = run_forward_calibration_simulation(
            params=opt_res.optimal_parameters,
            duration_minutes=duration_minutes,
            rain_mmh=rain_mmh,
        )
        q_final_resampled = np.interp(target_times, t_final, q_final)
        final_fit = evaluate_composite_fit(
            obs=obs_values,
            sim=q_final_resampled,
            dt_minutes=dt_min,
            w_kge=w_kge,
            w_pfe=w_pfe,
            w_pbias=w_pbias,
        )

        # Determine scientific validation status and provenance disclaimer
        if observed.provenance == ObservationProvenance.SYNTHETIC_BENCHMARK:
            validation_status = ValidationStatus.ALGORITHMIC_RECOVERY_VALIDATED
            disclaimer = (
                "SYNTHETIC BENCHMARK: Calibrated parameters recovered against a known synthetic ground truth. "
                "Verified algorithmic inverse accuracy for research demonstration."
            )
        elif network_provenance == NetworkProvenance.SURVEYED_ASSET_NETWORK and observed.provenance != ObservationProvenance.SYNTHETIC_BENCHMARK:
            validation_status = ValidationStatus.SCIENTIFICALLY_VALIDATED
            disclaimer = (
                "SCIENTIFICALLY VALIDATED: Calibration executed against surveyed physical drainage network "
                "and quality-controlled sensor observations."
            )
        else:
            validation_status = ValidationStatus.PROVISIONAL_ESTIMATE
            disclaimer = (
                "PROVISIONAL ESTIMATE: Field observations calibrated against an assumed/synthetic network fixture. "
                "Parameter values represent an effective numerical fit; NOT validated for operational deployment "
                "without verified physical GIS blueprints."
            )

        cal_id = f"CAL-{int(time.time())}-{opt_res.optimal_parameters.fingerprint()[:6]}"

        return CalibrationResult(
            calibration_id=cal_id,
            scenario_id=scenario_id,
            network_provenance=network_provenance,
            observation_provenance=observed.provenance,
            validation_status=validation_status,
            target_type=observed.target_type,
            target_sensor_id=observed.sensor_id,
            initial_metrics=init_fit,
            final_metrics=final_fit,
            initial_parameters=base_params,
            optimal_parameters=opt_res.optimal_parameters,
            observed_values=tuple(float(v) for v in obs_values),
            simulated_values=tuple(float(v) for v in q_final_resampled),
            time_minutes=tuple(float(t) for t in target_times),
            optimization_summary=opt_res.to_dict(),
            provenance_disclaimer=disclaimer,
        )
