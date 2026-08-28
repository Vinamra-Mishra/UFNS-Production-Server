"""Phase B test suite — Automated Drainage Calibration & Parameter Estimation Engine.

Tests:
1. Mathematical metrics: NSE, KGE, PFE, TPE, PBIAS, RMSE, Spatial Depth RMSE, Composite fit.
2. Parameter definitions, bounds clipping, normalization, vectorization, and fingerprinting.
3. Observations: synthetic benchmark generation, temporal resampling, provenance tagging.
4. Optimizer: Nelder-Mead, Differential Evolution, monotonic best-so-far loss invariant, sensitivity analysis.
5. Inversion engine: forward simulation, synthetic parameter recovery, provenance governance.
6. Ledger: recording, retrieval, JSON export.
7. FastAPI: /api/v1/calibration/* endpoints (run, history, get, sensitivity, error handling).
"""

from __future__ import annotations

import math
import numpy as np
import pytest
from fastapi.testclient import TestClient

from apps.api.app import app
from services.calibration import (
    CALIBRATION_ENGINE_VERSION,
    GLOBAL_CALIBRATION_LEDGER,
    CalibrationLedger,
    CalibrationParameterSet,
    CalibrationResult,
    CompositeGoodnessOfFit,
    DEFAULT_PARAMETER_DEFINITIONS,
    DrainageCalibrationEngine,
    NetworkProvenance,
    ObservationProvenance,
    ObservationTarget,
    ObservedTimeSeries,
    OptimizationResult,
    OptimizationStrategy,
    ParameterDefinition,
    ParameterOptimizer,
    ParameterSensitivity,
    SensitivityAnalyzer,
    SyntheticBenchmarkGenerator,
    ValidationStatus,
    evaluate_composite_fit,
    kling_gupta_efficiency,
    nash_sutcliffe_efficiency,
    peak_flow_error,
    percent_bias,
    root_mean_squared_error,
    run_forward_calibration_simulation,
    spatial_depth_rmse,
    time_to_peak_error,
)


# ===========================================================================
# 1. Mathematical Metrics Tests
# ===========================================================================

class TestCalibrationMetrics:
    """Testcalibrationmetrics schema and data model representation."""

    def test_nse_exact_match(self):
        """Test that nse exact match behaves as expected."""
        obs = np.array([1.0, 2.0, 5.0, 8.0, 3.0, 1.0])
        sim = np.array([1.0, 2.0, 5.0, 8.0, 3.0, 1.0])
        nse = nash_sutcliffe_efficiency(obs, sim)
        assert pytest.approx(nse, abs=1e-6) == 1.0

    def test_nse_known_imperfect(self):
        """Test that nse known imperfect behaves as expected."""
        obs = np.array([2.0, 4.0, 6.0, 8.0])
        # mean_obs = 5.0, denom = 9 + 1 + 1 + 9 = 20.0
        # sim differs by 1.0 everywhere: num = 1 + 1 + 1 + 1 = 4.0
        sim = np.array([3.0, 5.0, 7.0, 9.0])
        nse = nash_sutcliffe_efficiency(obs, sim)
        # NSE = 1 - 4/20 = 0.80
        assert pytest.approx(nse, abs=1e-6) == 0.80

    def test_nse_mismatch_shape_raises(self):
        """Test that nse mismatch shape raises behaves as expected."""
        with pytest.raises(ValueError, match="Shape mismatch"):
            nash_sutcliffe_efficiency([1, 2, 3], [1, 2])

    def test_kge_exact_match(self):
        """Test that kge exact match behaves as expected."""
        obs = np.array([1.0, 3.0, 7.0, 12.0, 4.0, 1.0])
        sim = np.array([1.0, 3.0, 7.0, 12.0, 4.0, 1.0])
        kge, r, alpha, beta = kling_gupta_efficiency(obs, sim)
        assert pytest.approx(kge, abs=1e-6) == 1.0
        assert pytest.approx(r, abs=1e-6) == 1.0
        assert pytest.approx(alpha, abs=1e-6) == 1.0
        assert pytest.approx(beta, abs=1e-6) == 1.0

    def test_kge_decomposition(self):
        """Test that kge decomposition behaves as expected."""
        obs = np.array([2.0, 4.0, 6.0, 8.0])
        # Scaled by 2: r=1, alpha=2, beta=2
        sim = obs * 2.0
        kge, r, alpha, beta = kling_gupta_efficiency(obs, sim)
        assert pytest.approx(r, abs=1e-4) == 1.0
        assert pytest.approx(alpha, abs=1e-4) == 2.0
        assert pytest.approx(beta, abs=1e-4) == 2.0
        # ED = sqrt(0^2 + 1^2 + 1^2) = sqrt(2) ≈ 1.4142 -> KGE = 1 - 1.4142 = -0.4142
        assert pytest.approx(kge, abs=1e-4) == 1.0 - math.sqrt(2.0)

    def test_pfe_and_tpe(self):
        """Test that pfe and tpe behaves as expected."""
        obs = np.array([0.0, 1.0, 5.0, 10.0, 3.0, 0.5])  # peak at index 3 (t=30m if dt=10m)
        sim = np.array([0.0, 1.0, 6.0, 12.0, 2.0, 0.5])  # peak 12.0 at index 3
        pfe = peak_flow_error(obs, sim)
        # PFE = |12 - 10| / 10 * 100% = 20%
        assert pytest.approx(pfe, abs=1e-4) == 20.0

        # Peak at different index
        sim_shift = np.array([0.0, 1.0, 12.0, 6.0, 2.0, 0.5])  # peak at index 2
        tpe = time_to_peak_error(obs, sim_shift, dt_minutes=5.0)
        # TPE = |2 - 3| * 5.0 = 5.0 min
        assert pytest.approx(tpe, abs=1e-4) == 5.0

    def test_pbias_and_rmse(self):
        """Test that pbias and rmse behaves as expected."""
        obs = np.array([10.0, 20.0, 30.0])  # sum = 60
        sim = np.array([12.0, 22.0, 32.0])  # sum = 66
        pbias = percent_bias(obs, sim)
        # (66 - 60) / 60 * 100% = +10.0%
        assert pytest.approx(pbias, abs=1e-4) == 10.0

        rmse = root_mean_squared_error(obs, sim)
        # errors are all 2.0 -> RMSE = 2.0
        assert pytest.approx(rmse, abs=1e-4) == 2.0

    def test_spatial_depth_rmse(self):
        """Test that spatial depth rmse behaves as expected."""
        obs_2d = np.array([[0.0, 0.5], [1.0, 2.0]])
        sim_2d = np.array([[0.0, 0.6], [1.1, 2.0]])
        mask = np.array([[False, True], [True, True]])
        s_rmse = spatial_depth_rmse(obs_2d, sim_2d, mask=mask)
        # eval on (0.5, 1.0, 2.0) vs (0.6, 1.1, 2.0) -> diffs (0.1, 0.1, 0.0)
        # mean sq = (0.01 + 0.01 + 0.0)/3 = 0.02/3 -> sqrt = 0.081649
        assert pytest.approx(s_rmse, abs=1e-4) == math.sqrt(0.02 / 3.0)

    def test_composite_fit_evaluation(self):
        """Test that composite fit evaluation behaves as expected."""
        obs = np.array([1.0, 2.0, 5.0, 10.0, 4.0, 1.0])
        sim = np.array([1.0, 2.1, 4.9, 9.8, 4.1, 1.0])
        fit = evaluate_composite_fit(obs, sim, dt_minutes=1.0)
        assert isinstance(fit, CompositeGoodnessOfFit)
        assert fit.kge > 0.95
        assert fit.nse > 0.95
        assert fit.composite_loss < 0.10
        d = fit.to_dict()
        assert "nse" in d and "composite_loss" in d


# ===========================================================================
# 2. Parameter Definitions & Set Tests
# ===========================================================================

class TestCalibrationParameters:
    """Testcalibrationparameters schema and data model representation."""

    def test_parameter_bounds_and_clipping(self):
        """Test that parameter bounds and clipping behaves as expected."""
        p_pipe = DEFAULT_PARAMETER_DEFINITIONS["pipe_manning_n"]
        assert p_pipe.min_bound == 0.009
        assert p_pipe.max_bound == 0.040
        assert p_pipe.validate_and_clip(0.005) == 0.009
        assert p_pipe.validate_and_clip(0.080) == 0.040
        assert p_pipe.validate_and_clip(0.015) == 0.015

    def test_normalization_roundtrip(self):
        """Test that normalization roundtrip behaves as expected."""
        p_surf = DEFAULT_PARAMETER_DEFINITIONS["surface_manning_n"]
        orig_val = 0.045
        norm = p_surf.normalize(orig_val)
        assert 0.0 <= norm <= 1.0
        denorm = p_surf.denormalize(norm)
        assert pytest.approx(denorm, abs=1e-6) == orig_val

    def test_effective_conduit_diameter_blockage(self):
        """Test that effective conduit diameter blockage behaves as expected."""
        pset = CalibrationParameterSet(blockage_ratio=0.0)
        # Clean: D_eff == D_0
        assert pytest.approx(pset.get_effective_conduit_diameter(0.30), abs=1e-6) == 0.30

        # Blocked (50% capacity reduction beta=0.5): D_eff = 0.30 * (0.5)^(3/8)
        pset_blocked = CalibrationParameterSet(blockage_ratio=0.5)
        expected_d = 0.30 * (0.5 ** (3.0 / 8.0))
        assert pytest.approx(pset_blocked.get_effective_conduit_diameter(0.30), abs=1e-4) == expected_d

    def test_vector_conversion_and_recovery(self):
        """Test that vector conversion and recovery behaves as expected."""
        pset = CalibrationParameterSet(
            pipe_manning_n=0.018,
            blockage_ratio=0.35,
            cd_orifice=0.72,
        )
        vec = pset.to_vector(["pipe_manning_n", "blockage_ratio", "cd_orifice"])
        assert vec == [0.018, 0.35, 0.72]

        recovered = CalibrationParameterSet.from_vector(
            [0.022, 0.50],
            ["pipe_manning_n", "blockage_ratio"],
            base=pset,
        )
        assert recovered.pipe_manning_n == 0.022
        assert recovered.blockage_ratio == 0.50
        assert recovered.cd_orifice == 0.72  # preserved from base

    def test_deterministic_fingerprint(self):
        """Test that deterministic fingerprint behaves as expected."""
        p1 = CalibrationParameterSet(pipe_manning_n=0.015, blockage_ratio=0.2)
        p2 = CalibrationParameterSet(pipe_manning_n=0.015, blockage_ratio=0.2)
        p3 = CalibrationParameterSet(pipe_manning_n=0.016, blockage_ratio=0.2)
        assert p1.fingerprint() == p2.fingerprint()
        assert p1.fingerprint() != p3.fingerprint()


# ===========================================================================
# 3. Observations & Synthetic Benchmark Tests
# ===========================================================================

class TestCalibrationObservations:
    """Testcalibrationobservations schema and data model representation."""

    def test_synthetic_benchmark_generation(self):
        """Test that synthetic benchmark generation behaves as expected."""
        ts = SyntheticBenchmarkGenerator.generate_synthetic_hydrograph(
            duration_minutes=45.0,
            dt_minutes=1.0,
            peak_discharge_m3s=0.090,
            time_to_peak_minutes=20.0,
            noise_std=0.0,
        )
        assert ts.target_type == ObservationTarget.OUTFALL_DISCHARGE
        assert ts.provenance == ObservationProvenance.SYNTHETIC_BENCHMARK
        assert len(ts.time_minutes) == 46
        assert pytest.approx(ts.peak_value, abs=1e-3) == 0.090
        assert pytest.approx(ts.time_to_peak_minutes, abs=1.0) == 20.0

    def test_observation_resampling(self):
        """Test that observation resampling behaves as expected."""
        ts = SyntheticBenchmarkGenerator.generate_synthetic_hydrograph(
            duration_minutes=30.0,
            dt_minutes=5.0,  # [0, 5, 10, 15, 20, 25, 30]
        )
        target_t = [0.0, 2.5, 5.0, 7.5, 10.0]
        resampled = ts.resample_to(target_t)
        assert len(resampled) == 5
        assert np.all(np.isfinite(resampled))


# ===========================================================================
# 4. Optimizer & Convergence Invariant Tests
# ===========================================================================

class TestCalibrationOptimizer:
    """Testcalibrationoptimizer schema and data model representation."""

    def test_best_so_far_monotonic_invariant(self):
        """Verify that the optimizer guarantees best_so_far_loss decreases monotonically."""
        # Multi-modal objective function with local spikes
        def noisy_obj(p: CalibrationParameterSet) -> float:
            """Execute Noisy Obj operation and return result."""
            x = p.pipe_manning_n
            y = p.blockage_ratio
            # Paraboloid with noise
            return (x - 0.020) ** 2 * 1000.0 + (y - 0.40) ** 2 * 10.0 + (0.01 * math.sin(x * 100.0))

        optimizer = ParameterOptimizer(
            strategy=OptimizationStrategy.NELDER_MEAD,
            target_param_names=["pipe_manning_n", "blockage_ratio"],
            max_evaluations=30,
        )
        res = optimizer.optimize(noisy_obj)
        assert len(res.history) > 0

        # Monotonicity check
        best_losses = [step.best_so_far_loss for step in res.history]
        for k in range(1, len(best_losses)):
            assert best_losses[k] <= best_losses[k - 1] + 1e-12, (
                f"best_so_far_loss increased at step {k}: {best_losses[k]} > {best_losses[k-1]}"
            )

        assert res.final_loss <= res.initial_loss

    def test_nelder_mead_convex_convergence(self):
        """Test that nelder mead convex convergence behaves as expected."""
        # Target: pipe_manning_n = 0.022, blockage_ratio = 0.30
        target_x, target_y = 0.022, 0.30

        def convex_obj(p: CalibrationParameterSet) -> float:
            """Execute Convex Obj operation and return result."""
            # Scaled by parameter spans so both dimensions have balanced loss gradients
            dx = (p.pipe_manning_n - target_x) / 0.031
            dy = (p.blockage_ratio - target_y) / 0.90
            return float(dx ** 2 + dy ** 2)

        optimizer = ParameterOptimizer(
            strategy=OptimizationStrategy.NELDER_MEAD,
            target_param_names=["pipe_manning_n", "blockage_ratio"],
            max_evaluations=60,
            tolerance=1e-5,
        )
        res = optimizer.optimize(convex_obj)
        assert pytest.approx(res.optimal_parameters.pipe_manning_n, abs=1e-3) == target_x
        assert pytest.approx(res.optimal_parameters.blockage_ratio, abs=1e-2) == target_y
        assert res.final_loss < 1e-3

    def test_differential_evolution_global_convergence(self):
        """Test that differential evolution global convergence behaves as expected."""
        target_x, target_y = 0.018, 0.50

        def global_obj(p: CalibrationParameterSet) -> float:
            """Execute Global Obj operation and return result."""
            dx = (p.pipe_manning_n - target_x) / 0.031
            dy = (p.blockage_ratio - target_y) / 0.90
            return float(dx ** 2 + dy ** 2)

        optimizer = ParameterOptimizer(
            strategy=OptimizationStrategy.DIFFERENTIAL_EVOLUTION,
            target_param_names=["pipe_manning_n", "blockage_ratio"],
            max_evaluations=50,
        )
        res = optimizer.optimize(global_obj)
        assert pytest.approx(res.optimal_parameters.pipe_manning_n, abs=0.005) == target_x
        assert pytest.approx(res.optimal_parameters.blockage_ratio, abs=0.10) == target_y

    def test_sensitivity_analyzer_oat(self):
        """Test that sensitivity analyzer oat behaves as expected."""
        def sample_obj(p: CalibrationParameterSet) -> float:
            """Execute Sample Obj operation and return result."""
            # Blockage has 10x higher impact than pipe roughness
            return float(10.0 * p.blockage_ratio + 1.0 * (p.pipe_manning_n * 100.0))

        analyzer = SensitivityAnalyzer(perturbation_fraction=0.20)
        sensitivities = analyzer.analyze(
            objective_fn=sample_obj,
            param_names=["pipe_manning_n", "blockage_ratio"],
        )
        assert len(sensitivities) == 2
        # Highest elasticity should be ranked 1
        assert sensitivities[0].rank == 1
        assert sensitivities[1].rank == 2


# ===========================================================================
# 5. Inversion Engine & Provenance Tests
# ===========================================================================

class TestCalibrationEngine:
    """Testcalibrationengine schema and data model representation."""

    def test_forward_calibration_simulation(self):
        """Test that forward calibration simulation behaves as expected."""
        params = CalibrationParameterSet(pipe_manning_n=0.013, blockage_ratio=0.0)
        t_arr, q_arr = run_forward_calibration_simulation(
            params=params,
            duration_minutes=15.0,
            rain_mmh=45.0,
        )
        assert len(t_arr) == len(q_arr)
        assert len(t_arr) > 0
        assert np.max(q_arr) > 0.0  # water reaches outfall

    def test_synthetic_inverse_recovery(self):
        """Algorithmic verification: recover pipe roughness from synthetic benchmark."""
        # 1. Generate observation
        obs = SyntheticBenchmarkGenerator.generate_synthetic_hydrograph(
            duration_minutes=20.0,
            dt_minutes=1.0,
            peak_discharge_m3s=0.080,
            noise_std=0.0,
        )

        engine = DrainageCalibrationEngine(
            strategy=OptimizationStrategy.NELDER_MEAD,
            target_param_names=["pipe_manning_n"],
            max_evaluations=12,
        )

        result = engine.calibrate(
            observed=obs,
            initial_params=CalibrationParameterSet(pipe_manning_n=0.025),
            duration_minutes=20.0,
            rain_mmh=45.0,
        )

        assert isinstance(result, CalibrationResult)
        assert result.validation_status == ValidationStatus.ALGORITHMIC_RECOVERY_VALIDATED
        assert "SYNTHETIC BENCHMARK" in result.provenance_disclaimer
        # Loss should have improved or converged
        assert result.final_metrics.composite_loss <= result.initial_metrics.composite_loss + 1e-4

    def test_provenance_labeling_governance(self):
        """Test that provenance labeling governance behaves as expected."""
        # Real field observation on assumed network fixture
        field_obs = ObservedTimeSeries(
            target_type=ObservationTarget.OUTFALL_DISCHARGE,
            sensor_id="FIELD-GAUGE-KOLKATA-01",
            time_minutes=(0.0, 10.0, 20.0),
            values=(0.01, 0.05, 0.02),
            unit="m3/s",
            provenance=ObservationProvenance.FIELD_SENSOR_RAW,
        )

        engine = DrainageCalibrationEngine(max_evaluations=4)
        result = engine.calibrate(
            observed=field_obs,
            network_provenance=NetworkProvenance.ASSUMED_DEMO_NETWORK,
            duration_minutes=20.0,
        )

        # Must NOT claim scientific validation
        assert result.validation_status == ValidationStatus.PROVISIONAL_ESTIMATE
        assert "PROVISIONAL ESTIMATE" in result.provenance_disclaimer
        assert "NOT validated for operational deployment" in result.provenance_disclaimer


# ===========================================================================
# 6. Ledger & Audit History Tests
# ===========================================================================

class TestCalibrationLedger:
    """Testcalibrationledger schema and data model representation."""

    def test_ledger_record_and_query(self):
        """Test that ledger record and query behaves as expected."""
        ledger = CalibrationLedger()
        assert ledger.count() == 0

        obs = SyntheticBenchmarkGenerator.generate_synthetic_hydrograph(duration_minutes=10.0)
        fit = evaluate_composite_fit([1, 2], [1, 2])
        res = CalibrationResult(
            calibration_id="CAL-TEST-001",
            scenario_id="S1",
            network_provenance=NetworkProvenance.SYNTHETIC_FIXTURE,
            observation_provenance=ObservationProvenance.SYNTHETIC_BENCHMARK,
            validation_status=ValidationStatus.ALGORITHMIC_RECOVERY_VALIDATED,
            target_type=ObservationTarget.OUTFALL_DISCHARGE,
            target_sensor_id=obs.sensor_id,
            initial_metrics=fit,
            final_metrics=fit,
            initial_parameters=CalibrationParameterSet(),
            optimal_parameters=CalibrationParameterSet(),
            observed_values=(0.0, 0.1),
            simulated_values=(0.0, 0.1),
            time_minutes=(0.0, 5.0),
            optimization_summary={"evaluations": 5},
            provenance_disclaimer="Test disclaimer",
        )

        ledger.record(res)
        assert ledger.count() == 1
        fetched = ledger.get("CAL-TEST-001")
        assert fetched is not None
        assert fetched.calibration_id == "CAL-TEST-001"
        assert len(ledger.list_all()) == 1


# ===========================================================================
# 7. FastAPI Endpoints Tests
# ===========================================================================

class TestCalibrationAPI:
    """Testcalibrationapi schema and data model representation."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """Execute Setup Client operation and return result."""
        self.client = TestClient(app)

    def test_api_run_calibration_endpoint(self):
        """Test that api run calibration endpoint behaves as expected."""
        payload = {
            "scenario_id": "D_NORMAL_CAL",
            "strategy": "NELDER_MEAD",
            "target_params": ["pipe_manning_n"],
            "max_evaluations": 6,
            "duration_minutes": 15.0,
            "rain_mmh": 45.0,
            "initial_pipe_n": 0.015,
            "synthetic_benchmark": True,
        }
        resp = self.client.post("/api/v1/calibration/run", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "calibration_id" in data
        assert "validation_status" in data
        assert "initial_metrics" in data
        assert "final_metrics" in data
        assert "optimal_parameters" in data
        assert data["validation_status"] == "ALGORITHMIC_RECOVERY_VALIDATED"

    def test_api_history_and_get_record(self):
        """Test that api history and get record behaves as expected."""
        # 1. Fetch history
        resp_list = self.client.get("/api/v1/calibration/history")
        assert resp_list.status_code == 200
        items = resp_list.json()
        assert isinstance(items, list)
        if len(items) > 0:
            cid = items[0]["calibration_id"]
            resp_item = self.client.get(f"/api/v1/calibration/{cid}")
            assert resp_item.status_code == 200
            assert resp_item.json()["calibration_id"] == cid

    def test_api_calibration_not_found(self):
        """Test that api calibration not found behaves as expected."""
        resp = self.client.get("/api/v1/calibration/CAL-NONEXISTENT-999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "CALIBRATION_NOT_FOUND"

    def test_api_sensitivity_endpoint(self):
        """Test that api sensitivity endpoint behaves as expected."""
        payload = {
            "param_names": ["pipe_manning_n", "blockage_ratio"],
            "perturbation_fraction": 0.15,
            "duration_minutes": 15.0,
            "rain_mmh": 45.0,
        }
        resp = self.client.post("/api/v1/calibration/sensitivity", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["rank"] == 1
        assert "elasticity" in data[0]
