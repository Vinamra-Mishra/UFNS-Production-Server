"""Phase I Test Suite — Scientific Hydrodynamic Benchmark & Model Validation Suite.

Tests:
- Nash–Sutcliffe Efficiency (NSE) and Kling–Gupta Efficiency (KGE) formulations
- Spatial contingency metrics (CSI, POD, FAR, F1)
- Continuous depth error metrics (RMSE, MAE, Bias)
- Benchmark engine and publication-grade validation tiering
- FastAPI /api/v1/validation/* endpoints
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from apps.api.app import app
from services.validation.benchmark import (
    BENCHMARK_CATALOG,
    GLOBAL_BENCHMARK_ENGINE,
    BenchmarkEngine,
)
from services.validation.metrics import (
    calculate_contingency_scores,
    calculate_depth_errors,
    calculate_kge,
    calculate_nse,
)


class TestHydrologicalMetrics:
    """Test analytical correctness of validation metric formulations."""

    def test_nse_perfect_match(self):
        """Test that nse perfect match behaves as expected."""
        obs = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        sim = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert calculate_nse(sim, obs) == 1.0

    def test_nse_poor_match(self):
        """Test that nse poor match behaves as expected."""
        obs = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        sim = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
        nse = calculate_nse(sim, obs)
        assert nse < 0.0

    def test_kge_perfect_match(self):
        """Test that kge perfect match behaves as expected."""
        obs = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        sim = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        res = calculate_kge(sim, obs)
        assert res["kge"] == 1.0
        assert res["correlation_r"] == 1.0
        assert res["variability_alpha"] == 1.0
        assert res["bias_beta"] == 1.0

    def test_contingency_scores_perfect_overlap(self):
        """Test that contingency scores perfect overlap behaves as expected."""
        grid = np.array([[0.1, 0.2], [0.0, 0.0]])
        res = calculate_contingency_scores(grid, grid, threshold_m=0.05)
        assert res["critical_success_index_csi"] == 1.0
        assert res["probability_of_detection_pod"] == 1.0
        assert res["false_alarm_ratio_far"] == 0.0
        assert res["hits"] == 2
        assert res["misses"] == 0
        assert res["false_alarms"] == 0

    def test_depth_errors_calculation(self):
        """Test that depth errors calculation behaves as expected."""
        grid_sim = np.array([[0.10, 0.20], [0.30, 0.40]])
        grid_obs = np.array([[0.12, 0.18], [0.28, 0.42]])
        res = calculate_depth_errors(grid_sim, grid_obs)
        assert 0.015 < res["rmse_m"] < 0.025
        assert res["mae_m"] == 0.02
        assert abs(res["mean_bias_m"]) <= 1e-4


class TestBenchmarkEvaluationEngine:
    """Test benchmark evaluation against reference scenarios."""

    def test_self_benchmark_evaluation_self_consistency(self):
        """Test that self benchmark evaluation self consistency behaves as expected."""
        engine = BenchmarkEngine()
        res = engine.evaluate(scenario_id="S3", lead_minutes=110, benchmark_id="BENCHMARK_S3_CLEAN")

        assert res.hydrograph_metrics["nash_sutcliffe_efficiency_nse"] == 1.0
        assert res.hydrograph_metrics["kling_gupta_efficiency_kge"] == 1.0
        assert res.spatial_contingency["critical_success_index_csi"] == 1.0
        assert res.depth_errors["rmse_m"] == 0.0
        assert res.provenance["self_consistency_check"] is True
        assert res.scientific_validation_tier == "TIER_2_OPERATIONAL_GRADE"

    def test_surcharge_vs_clean_benchmark_divergence(self):
        """Test that surcharge vs clean benchmark divergence behaves as expected."""
        engine = BenchmarkEngine()
        res = engine.evaluate(scenario_id="S4", lead_minutes=110, benchmark_id="BENCHMARK_S3_CLEAN")

        assert res.depth_errors["rmse_m"] > 0.0
        assert res.spatial_contingency["critical_success_index_csi"] > 0.50
        assert res.mass_conservation_residual_pct is not None
        assert res.mass_conservation_residual_pct <= 0.05
        assert res.provenance["self_consistency_check"] is False


class TestValidationAPIEndpoints:
    """Test FastAPI /api/v1/validation endpoints."""

    def test_list_benchmarks_endpoint(self):
        """Test that list benchmarks endpoint behaves as expected."""
        client = TestClient(app)
        res = client.get("/api/v1/validation/benchmarks")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 3
        bids = [b["benchmark_id"] for b in data["benchmarks"]]
        assert "BENCHMARK_S3_CLEAN" in bids
        assert "BENCHMARK_S4_SURCHARGE" in bids

    def test_evaluate_endpoint(self):
        """Test that evaluate endpoint behaves as expected."""
        client = TestClient(app)
        payload = {
            "scenario_id": "S4",
            "lead_minutes": 110,
            "benchmark_id": "BENCHMARK_S3_CLEAN",
        }
        res = client.post("/api/v1/validation/evaluate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "hydrograph_metrics" in data
        assert "spatial_contingency" in data
        assert "depth_errors" in data
        assert "scientific_validation_tier" in data
