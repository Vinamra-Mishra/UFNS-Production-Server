"""Optimization algorithms and sensitivity analysis for hydraulic parameter estimation (Phase B).

Provides:
- OptimizationStrategy: Nelder-Mead, Differential Evolution, Grid Search, Random Search
- ParameterOptimizer: abstract base class enforcing parameter bounds and best-so-far monotonic loss tracking
- SensitivityAnalyzer: One-At-A-Time (OAT) parameter sensitivity and elasticity ranking
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import differential_evolution, minimize

from services.calibration.parameters import (
    DEFAULT_PARAMETER_DEFINITIONS,
    CalibrationParameterSet,
    ParameterDefinition,
)


class OptimizationStrategy(str, Enum):
    """Optimizationstrategy schema and data model representation."""
    NELDER_MEAD = "NELDER_MEAD"                   # Fast local simplex on bounded parameter space
    DIFFERENTIAL_EVOLUTION = "DIFF_EVOLUTION"     # Global stochastic search for non-convex landscapes
    GRID_SEARCH = "GRID_SEARCH"                   # Systematic multi-dimensional grid sweep
    RANDOM_SEARCH = "RANDOM_SEARCH"               # Latin hypercube / uniform random exploration


@dataclass
class IterationEvaluation:
    """Individual candidate evaluation during optimization."""

    iteration: int
    parameter_values: dict[str, float]
    loss: float
    best_so_far_loss: float
    timestamp_epoch: float


@dataclass
class OptimizationResult:
    """Complete summary of parameter optimization run."""

    strategy: OptimizationStrategy
    optimal_parameters: CalibrationParameterSet
    initial_loss: float
    final_loss: float
    best_so_far_loss: float
    total_evaluations: int
    converged: bool
    duration_seconds: float
    history: list[IterationEvaluation] = field(default_factory=list)

    @property
    def improvement_pct(self) -> float:
        """Execute Improvement Pct operation and return result."""
        if abs(self.initial_loss) < 1e-12:
            return 0.0
        return float((self.initial_loss - self.final_loss) / self.initial_loss * 100.0)

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "strategy": self.strategy.value,
            "optimal_parameters": self.optimal_parameters.to_dict(),
            "initial_loss": round(self.initial_loss, 6),
            "final_loss": round(self.final_loss, 6),
            "best_so_far_loss": round(self.best_so_far_loss, 6),
            "improvement_pct": round(self.improvement_pct, 2),
            "total_evaluations": self.total_evaluations,
            "converged": self.converged,
            "duration_seconds": round(self.duration_seconds, 3),
            "history_length": len(self.history),
        }


# ---------------------------------------------------------------------------
# Optimizers
# ---------------------------------------------------------------------------

class ParameterOptimizer:
    """Base parameter optimization orchestrator."""

    def __init__(
        self,
        strategy: OptimizationStrategy = OptimizationStrategy.NELDER_MEAD,
        target_param_names: Optional[Sequence[str]] = None,
        max_evaluations: int = 100,
        tolerance: float = 1e-4,
        definitions: Optional[dict[str, ParameterDefinition]] = None,
    ) -> None:
        """Execute   Init   operation and return result."""
        self.strategy = strategy
        self.param_names = list(target_param_names or ["pipe_manning_n", "blockage_ratio"])
        self.max_evaluations = max_evaluations
        self.tolerance = tolerance
        self.definitions = definitions or DEFAULT_PARAMETER_DEFINITIONS

    def optimize(
        self,
        objective_fn: Callable[[CalibrationParameterSet], float],
        initial_params: Optional[CalibrationParameterSet] = None,
    ) -> OptimizationResult:
        """Run optimization against the supplied objective function."""
        t_start = time.perf_counter()
        base_params = initial_params or CalibrationParameterSet()

        target_defs = [self.definitions[name] for name in self.param_names]
        norm_bounds = [(0.0, 1.0) for _ in self.param_names]

        history: list[IterationEvaluation] = []
        best_so_far = float("inf")
        best_param_set = base_params

        # Evaluate initial guess
        init_loss = float(objective_fn(base_params))
        best_so_far = init_loss
        best_param_set = base_params
        history.append(
            IterationEvaluation(
                iteration=0,
                parameter_values=base_params.to_dict(),
                loss=init_loss,
                best_so_far_loss=best_so_far,
                timestamp_epoch=time.time(),
            )
        )

        eval_count = 1

        def wrapped_loss(u_vec: np.ndarray) -> float:
            """Execute Wrapped Loss operation and return result."""
            nonlocal eval_count, best_so_far, best_param_set
            if eval_count >= self.max_evaluations:
                return best_so_far

            # Boundary excursion penalty so optimizer stays within [0, 1]
            penalty = 0.0
            for u in u_vec:
                if u < 0.0:
                    penalty += float((0.0 - u) ** 2 * 1000.0)
                elif u > 1.0:
                    penalty += float((u - 1.0) ** 2 * 1000.0)

            u_clipped = np.clip(u_vec, 0.0, 1.0)
            denorm_vec = [
                pdef.denormalize(float(u_val))
                for pdef, u_val in zip(target_defs, u_clipped)
            ]
            pset = CalibrationParameterSet.from_vector(
                denorm_vec, self.param_names, base=base_params
            )
            raw_loss = float(objective_fn(pset))
            if not math.isfinite(raw_loss):
                raw_loss = 1e6

            total_loss = raw_loss + penalty

            eval_count += 1
            if raw_loss < best_so_far and penalty < 1e-6:
                best_so_far = raw_loss
                best_param_set = pset

            history.append(
                IterationEvaluation(
                    iteration=eval_count,
                    parameter_values=pset.to_dict(),
                    loss=total_loss,
                    best_so_far_loss=best_so_far,
                    timestamp_epoch=time.time(),
                )
            )
            return total_loss

        converged = False
        u0 = np.array([
            max(0.05, min(0.95, pdef.normalize(float(getattr(base_params, pdef.name) if hasattr(base_params, pdef.name) else base_params.extra_params.get(pdef.name, pdef.default_value)))))
            for pdef in target_defs
        ], dtype=np.float64)

        if self.strategy == OptimizationStrategy.NELDER_MEAD:
            res = minimize(
                wrapped_loss,
                x0=u0,
                method="Nelder-Mead",
                options={
                    "maxiter": self.max_evaluations,
                    "xatol": self.tolerance,
                    "fatol": self.tolerance,
                },
            )
            converged = bool(res.success)
        elif self.strategy == OptimizationStrategy.DIFFERENTIAL_EVOLUTION:
            popsize = max(4, min(15, self.max_evaluations // (len(self.param_names) * 4)))
            maxiter = max(2, self.max_evaluations // (popsize * len(self.param_names)))
            res = differential_evolution(
                wrapped_loss,
                bounds=norm_bounds,
                maxiter=maxiter,
                popsize=popsize,
                tol=self.tolerance,
                seed=20260825,
            )
            converged = bool(res.success)
        elif self.strategy == OptimizationStrategy.GRID_SEARCH:
            # Grid sweep across parameter combinations
            steps_per_dim = max(2, int(round(self.max_evaluations ** (1.0 / len(self.param_names)))))
            grid_axes = [np.linspace(0.0, 1.0, steps_per_dim) for _ in norm_bounds]
            mesh = np.meshgrid(*grid_axes, indexing="ij")
            points = np.stack([m.ravel() for m in mesh], axis=-1)
            for pt in points:
                wrapped_loss(pt)
                if eval_count >= self.max_evaluations:
                    break
            converged = True
        elif self.strategy == OptimizationStrategy.RANDOM_SEARCH:
            rng = np.random.default_rng(20260825)
            for _ in range(self.max_evaluations - 1):
                pt = rng.uniform(0.0, 1.0, size=len(norm_bounds))
                wrapped_loss(pt)
            converged = True

        duration = float(time.perf_counter() - t_start)

        return OptimizationResult(
            strategy=self.strategy,
            optimal_parameters=best_param_set,
            initial_loss=init_loss,
            final_loss=best_so_far,
            best_so_far_loss=best_so_far,
            total_evaluations=eval_count,
            converged=converged,
            duration_seconds=duration,
            history=history,
        )


# ---------------------------------------------------------------------------
# Parameter Sensitivity Analysis
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParameterSensitivity:
    """Sensitivity metric for a single parameter."""

    parameter_name: str
    baseline_value: float
    perturbed_low: float
    perturbed_high: float
    loss_baseline: float
    loss_low: float
    loss_high: float
    elasticity: float  # (dLoss / Loss) / (dTheta / Theta)
    rank: int


class SensitivityAnalyzer:
    """Performs One-At-A-Time (OAT) parameter elasticity analysis."""

    def __init__(
        self,
        definitions: Optional[dict[str, ParameterDefinition]] = None,
        perturbation_fraction: float = 0.15,
    ) -> None:
        """Execute   Init   operation and return result."""
        self.definitions = definitions or DEFAULT_PARAMETER_DEFINITIONS
        self.fraction = perturbation_fraction

    def analyze(
        self,
        objective_fn: Callable[[CalibrationParameterSet], float],
        base_params: Optional[CalibrationParameterSet] = None,
        param_names: Optional[Sequence[str]] = None,
    ) -> list[ParameterSensitivity]:
        """Evaluate sensitivity coefficients for all selected parameters."""
        base = base_params or CalibrationParameterSet()
        params_to_eval = list(param_names or list(self.definitions.keys()))
        loss_base = max(1e-6, float(objective_fn(base)))

        results: list[dict[str, Any]] = []

        for name in params_to_eval:
            if not hasattr(base, name) and name not in base.extra_params:
                continue
            val_base = float(getattr(base, name) if hasattr(base, name) else base.extra_params[name])
            p_def = self.definitions.get(name)
            min_b = p_def.min_bound if p_def else 0.0
            max_b = p_def.max_bound if p_def else val_base * 2.0

            delta = max(val_base * self.fraction, 1e-4)
            val_low = max(min_b, val_base - delta)
            val_high = min(max_b, val_base + delta)

            # Evaluate low
            p_low = CalibrationParameterSet.from_vector([val_low], [name], base=base)
            loss_low = float(objective_fn(p_low))

            # Evaluate high
            p_high = CalibrationParameterSet.from_vector([val_high], [name], base=base)
            loss_high = float(objective_fn(p_high))

            # Compute normalized elasticity
            d_param = max(1e-6, (val_high - val_low) / max(abs(val_base), 1e-4))
            d_loss = abs(loss_high - loss_low) / loss_base
            elasticity = float(d_loss / d_param)

            results.append({
                "name": name,
                "val_base": val_base,
                "val_low": val_low,
                "val_high": val_high,
                "loss_base": loss_base,
                "loss_low": loss_low,
                "loss_high": loss_high,
                "elasticity": elasticity,
            })

        # Sort by elasticity descending to rank importance
        results.sort(key=lambda x: x["elasticity"], reverse=True)

        return [
            ParameterSensitivity(
                parameter_name=r["name"],
                baseline_value=r["val_base"],
                perturbed_low=r["val_low"],
                perturbed_high=r["val_high"],
                loss_baseline=r["loss_base"],
                loss_low=r["loss_low"],
                loss_high=r["loss_high"],
                elasticity=r["elasticity"],
                rank=i + 1,
            )
            for i, r in enumerate(results)
        ]
