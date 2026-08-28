"""Phase J Test Suite — Intervention Optimization & Cost-Benefit Civic Allocator.

Tests:
- Civil engineering unit cost calculations and damage avoidance valuations
- Budget-constrained Pareto frontier optimization
- Benefit-Cost Ratio (BCR) and Mitigation Effectiveness Index (MEI) scaling
- FastAPI /api/v1/optimization/* endpoints
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.app import app
from services.optimization.cost_model import (
    calculate_damage_valuation,
    calculate_intervention_cost,
)
from services.optimization.solver import (
    GLOBAL_INTERVENTION_OPTIMIZER,
    InterventionOptimizer,
)


class TestCostModelsAndLossValuation:
    """Test civil engineering cost models and avoided loss valuation formulas."""

    def test_calculate_intervention_cost_zero(self):
        """Test that calculate intervention cost zero behaves as expected."""
        res = calculate_intervention_cost(0.0, 0.0, 0.0, False)
        assert res["total_capex_inr"] == 0.0
        assert res["total_capex_crores"] == 0.0

    def test_calculate_intervention_cost_with_assets(self):
        """Test that calculate intervention cost with assets behaves as expected."""
        res = calculate_intervention_cost(
            lid_permeable_fraction=0.10,
            detention_basin_m3=50000.0,
            emergency_pump_m3s=5.0,
            unblock_culvert_in004=True,
        )
        assert res["lid_cost_inr"] > 0
        assert res["basin_cost_inr"] == 50000.0 * 450.0
        assert res["pump_cost_inr"] == 5.0 * 2500000.0
        assert res["desilt_cost_inr"] == 1500000.0
        assert res["total_capex_inr"] == (
            res["lid_cost_inr"] + res["basin_cost_inr"] + res["pump_cost_inr"] + res["desilt_cost_inr"]
        )
        assert res["total_capex_crores"] > 0

    def test_calculate_damage_valuation(self):
        """Test that calculate damage valuation behaves as expected."""
        res = calculate_damage_valuation(
            area_reduction_m2=100000.0,
            volume_reduction_m3=50000.0,
            reopened_roads_count=5,
            protected_assets_count=2,
        )
        assert res["avoided_property_damage_inr"] > 0
        assert res["avoided_traffic_disruption_inr"] == 5 * 2500000.0
        assert res["total_avoided_losses_inr"] > 0
        assert res["total_avoided_losses_crores"] > 0


class TestParetoOptimizer:
    """Test multi-objective Pareto solver across budget limits."""

    def test_solve_low_budget_selects_tactical(self):
        """Test that solve low budget selects tactical behaves as expected."""
        optimizer = InterventionOptimizer()
        res = optimizer.solve(scenario_id="S4", lead_minutes=110, budget_crores=2.0)

        assert res.max_budget_crores == 2.0
        assert len(res.pareto_frontier) == 3
        # With 2 Cr budget, only Tactical tier fits
        assert res.optimal_recommended_tier == "TIER_1_TACTICAL"

        tactical = next(p for p in res.pareto_frontier if p["tier_id"] == "TIER_1_TACTICAL")
        assert tactical["cost_breakdown"]["total_capex_crores"] <= 2.0
        assert tactical["benefit_cost_ratio_bcr"] > 0.0
        assert tactical["economic_benefit"]["total_avoided_losses_inr"] > 0.0

    def test_solve_high_budget_selects_higher_tier(self):
        """Test that solve high budget selects higher tier behaves as expected."""
        optimizer = InterventionOptimizer()
        res = optimizer.solve(scenario_id="S4", lead_minutes=110, budget_crores=20.0)

        assert res.max_budget_crores == 20.0
        assert res.optimal_recommended_tier in ("TIER_2_BALANCED", "TIER_3_RESILIENT")

        for p in res.pareto_frontier:
            assert p["mitigation_effectiveness_index"] >= 0.0
            assert p["depth_reduction_pct"] >= 0.0


class TestOptimizationAPIEndpoints:
    """Test FastAPI /api/v1/optimization endpoints."""

    def test_rates_endpoint(self):
        """Test that rates endpoint behaves as expected."""
        client = TestClient(app)
        res = client.get("/api/v1/optimization/rates")
        assert res.status_code == 200
        data = res.json()
        assert "civil_cost_rates_inr" in data
        assert "damage_valuation_rates_inr" in data

    def test_solve_endpoint(self):
        """Test that solve endpoint behaves as expected."""
        client = TestClient(app)
        payload = {
            "scenario_id": "S4",
            "lead_minutes": 110,
            "budget_crores": 10.0,
        }
        res = client.post("/api/v1/optimization/solve", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["max_budget_crores"] == 10.0
        assert "optimal_recommended_tier" in data
        assert len(data["pareto_frontier"]) == 3
