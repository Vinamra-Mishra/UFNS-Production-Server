"""Phase K Test Suite — Probabilistic Flood Forecasting & Ensemble Uncertainty Quantification.

Tests:
- 10-member stochastic rainfall perturbation ensemble generation
- 2D spatial exceedance probability calculations P(h >= 10cm, 20cm, 30cm, 50cm)
- P10/P50/P90 confidence bounds and interquartile ranges
- Probabilistic road impassability confidence levels
- Brier Skill Score calculation
- FastAPI /api/v1/probabilistic/* endpoints
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from apps.api.app import app
from services.probabilistic.ensemble import (
    EnsembleMember,
    generate_ensemble_members,
)
from services.probabilistic.risk_map import (
    GLOBAL_PROBABILISTIC_ENGINE,
    ProbabilisticRiskEngine,
    calculate_brier_score,
    calculate_exceedance_probabilities,
)


class TestEnsembleGeneration:
    """Test stochastic ensemble member specifications."""

    def test_ensemble_count_and_anchors(self):
        """Test that ensemble count and anchors behaves as expected."""
        members = generate_ensemble_members(10)
        assert len(members) == 10

        tags = {m.percentile_tag for m in members}
        assert "P10" in tags
        assert "P50" in tags
        assert "P90" in tags

        tot_weight = sum(m.weight for m in members)
        assert abs(tot_weight - 1.0) < 1e-4

        # P10 has lower multiplier than P50 which is lower than P90
        p10 = next(m for m in members if m.percentile_tag == "P10")
        p50 = next(m for m in members if m.percentile_tag == "P50")
        p90 = next(m for m in members if m.percentile_tag == "P90")
        assert p10.rainfall_multiplier < p50.rainfall_multiplier < p90.rainfall_multiplier


class TestProbabilisticRiskCalculations:
    """Test spatial exceedance probabilities, confidence bounds, and Brier score."""

    def test_brier_score_perfect(self):
        """Test that brier score perfect behaves as expected."""
        prob = np.array([1.0, 0.0, 1.0, 0.0])
        obs = np.array([1.0, 0.0, 1.0, 0.0])
        assert calculate_brier_score(prob, obs) == 0.0

    def test_brier_score_worst(self):
        """Test that brier score worst behaves as expected."""
        prob = np.array([1.0, 1.0])
        obs = np.array([0.0, 0.0])
        assert calculate_brier_score(prob, obs) == 1.0

    def test_exceedance_probabilities_synthetic(self):
        """Test that exceedance probabilities synthetic behaves as expected."""
        stack = np.array([
            [[0.05, 0.15], [0.35, 0.55]],
            [[0.12, 0.25], [0.45, 0.65]],
            [[0.08, 0.18], [0.32, 0.52]],
        ])  # 3 members, 2x2 grid
        res = calculate_exceedance_probabilities(stack, thresholds=(0.10, 0.30, 0.50))

        assert "prob_exceed_10cm" in res
        assert "prob_exceed_30cm" in res
        assert "prob_exceed_50cm" in res
        assert 0.0 <= res["prob_exceed_10cm"]["mean_exceedance_prob"] <= 1.0

    def test_probabilistic_simulation_engine(self):
        """Test that probabilistic simulation engine behaves as expected."""
        engine = ProbabilisticRiskEngine()
        res = engine.simulate(scenario_id="S4", lead_minutes=110, member_count=10)

        assert res.ensemble_size == 10
        assert len(res.members) == 10
        cb = res.confidence_bounds
        assert cb["p10_max_depth_m"] <= cb["p50_max_depth_m"] <= cb["p90_max_depth_m"]
        assert cb["interquartile_range_m"] >= 0.0

        assert 0.0 <= res.brier_skill_score <= 1.0
        assert len(res.probabilistic_road_impacts) > 0
        for r in res.probabilistic_road_impacts:
            assert 0.0 <= r["prob_impassable"] <= 1.0
            assert 0.0 <= r["prob_caution"] <= 1.0
            assert 0.0 <= r["prob_dry"] <= 1.0
            assert abs(r["prob_impassable"] + r["prob_caution"] + r["prob_dry"] - 1.0) < 1e-2


class TestProbabilisticAPIEndpoints:
    """Test FastAPI /api/v1/probabilistic endpoints."""

    def test_list_members_endpoint(self):
        """Test that list members endpoint behaves as expected."""
        client = TestClient(app)
        res = client.get("/api/v1/probabilistic/members")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] == 10
        assert len(data["members"]) == 10

    def test_simulate_endpoint(self):
        """Test that simulate endpoint behaves as expected."""
        client = TestClient(app)
        payload = {
            "scenario_id": "S4",
            "lead_minutes": 110,
            "member_count": 10,
        }
        res = client.post("/api/v1/probabilistic/simulate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["ensemble_size"] == 10
        assert "confidence_bounds" in data
        assert "exceedance_statistics" in data
        assert "probabilistic_road_impacts" in data
        assert "brier_skill_score" in data
