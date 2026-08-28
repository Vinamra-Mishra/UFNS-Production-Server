"""Phase F Test Suite — Nature-Based Solutions (NbS) & Sponge City Urban Intervention Simulator.

Tests:
- Strict non-mutation of baseline physical models and precomputed artifacts
- Dynamic counterfactual physics (LID, detention basins, dewatering pumps, culvert desilting)
- Zero hard-coding: all results are evaluated dynamically from scenario rasters
- FastAPI endpoints (/api/v1/mitigation/*)
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from apps.api import impacts, store
from apps.api.app import app
from services.mitigation.engine import (
    GLOBAL_MITIGATION_ENGINE,
    InterventionConfig,
    InterventionScenarioEngine,
)
from services.mitigation.evaluator import (
    MITIGATION_STRATEGIES,
    calculate_effectiveness_index,
)


class TestNonMutatingBaselineIntegrity:
    """Ensure baseline simulation artifacts are strictly preserved and never mutated."""

    def test_baseline_arrays_unaltered_after_mitigation_runs(self):
        """Test that baseline arrays unaltered after mitigation runs behaves as expected."""
        engine = InterventionScenarioEngine()
        
        # Capture baseline state before simulation
        grid_before = np.copy(impacts.depth_grid("S4", 110))
        result_meta_before = store.scenario_result("S4")
        hash_before = hash(grid_before.tobytes())

        # Run aggressive hybrid mitigation
        config = InterventionConfig(
            scenario_id="S4",
            lead_minutes=110,
            lid_permeable_fraction=0.40,
            detention_basin_m3=80000.0,
            emergency_pump_m3s=8.0,
            unblock_culvert_in004=True,
        )
        res = engine.simulate(config, return_raster=True)

        # Re-read baseline state after simulation
        grid_after = impacts.depth_grid("S4", 110)
        hash_after = hash(grid_after.tobytes())

        # Verify bitwise identical baseline
        assert hash_before == hash_after
        assert np.array_equal(grid_before, grid_after)
        assert res.provenance["baseline_unaltered"] is True
        assert res.provenance["classification"] == "COUNTERFACTUAL_INTERVENTION_SCENARIO"


class TestInterventionPhysics:
    """Test dynamic counterfactual physics formulations."""

    def test_null_intervention_matches_baseline(self):
        """Test that null intervention matches baseline behaves as expected."""
        engine = InterventionScenarioEngine()
        config = InterventionConfig(
            scenario_id="S4",
            lead_minutes=110,
            lid_permeable_fraction=0.0,
            detention_basin_m3=0.0,
            emergency_pump_m3s=0.0,
            unblock_culvert_in004=False,
        )
        res = engine.simulate(config)

        assert res.deltas["depth_reduction_m"] == 0.0
        assert res.deltas["area_reduction_m2"] == 0.0
        assert res.deltas["volume_reduction_m3"] == 0.0
        assert res.deltas["reopened_roads_count"] == 0
        assert res.baseline_metrics["max_depth_m"] == res.mitigated_metrics["max_depth_m"]
        assert res.mitigation_effectiveness_index == 0.0

    def test_lid_permeable_pavement_reduces_depth_and_area(self):
        """Test that lid permeable pavement reduces depth and area behaves as expected."""
        engine = InterventionScenarioEngine()
        config = InterventionConfig(
            scenario_id="S4",
            lead_minutes=110,
            lid_permeable_fraction=0.30,
            detention_basin_m3=0.0,
            emergency_pump_m3s=0.0,
            unblock_culvert_in004=False,
        )
        res = engine.simulate(config)

        assert res.deltas["depth_reduction_m"] > 0.0
        assert res.deltas["area_reduction_m2"] > 0.0
        assert res.deltas["volume_reduction_m3"] > 0.0
        assert res.mitigated_metrics["flood_volume_m3"] < res.baseline_metrics["flood_volume_m3"]
        assert 0.0 < res.mitigation_effectiveness_index <= 1.0

    def test_detention_basin_captures_volume(self):
        """Test that detention basin captures volume behaves as expected."""
        engine = InterventionScenarioEngine()
        config = InterventionConfig(
            scenario_id="S4",
            lead_minutes=110,
            lid_permeable_fraction=0.0,
            detention_basin_m3=50000.0,
            emergency_pump_m3s=0.0,
            unblock_culvert_in004=False,
        )
        res = engine.simulate(config)

        assert res.deltas["volume_reduction_m3"] > 0.0
        assert res.deltas["depth_reduction_m"] > 0.0

    def test_emergency_pumping_reopens_roads(self):
        """Test that emergency pumping reopens roads behaves as expected."""
        engine = InterventionScenarioEngine()
        config = InterventionConfig(
            scenario_id="S4",
            lead_minutes=110,
            lid_permeable_fraction=0.0,
            detention_basin_m3=0.0,
            emergency_pump_m3s=6.0,
            unblock_culvert_in004=False,
        )
        res = engine.simulate(config)

        assert res.deltas["volume_reduction_m3"] > 0.0
        assert res.mitigated_metrics["impassable_count"] <= res.baseline_metrics["impassable_count"]

    def test_culvert_unblocking_relieves_surcharge(self):
        """Test that culvert unblocking relieves surcharge behaves as expected."""
        engine = InterventionScenarioEngine()
        config = InterventionConfig(
            scenario_id="S4",
            lead_minutes=110,
            lid_permeable_fraction=0.0,
            detention_basin_m3=0.0,
            emergency_pump_m3s=0.0,
            unblock_culvert_in004=True,
        )
        res = engine.simulate(config)

        # Unblocking IN-004 culvert significantly abates surcharge backflow on S4
        assert res.deltas["depth_reduction_m"] > 0.05
        assert res.deltas["volume_reduction_m3"] > 0.0
        assert res.mitigation_effectiveness_index > 0.0

    def test_effectiveness_index_bounds(self):
        """Test that effectiveness index bounds behaves as expected."""
        mei_zero = calculate_effectiveness_index(0.0, 0.0, 0.0)
        assert mei_zero == 0.0

        mei_max = calculate_effectiveness_index(100.0, 100.0, 1.0)
        assert mei_max == 1.0

        mei_mid = calculate_effectiveness_index(50.0, 30.0, 0.5)
        assert 0.0 < mei_mid < 1.0


class TestMitigationAPIEndpoints:
    """Test FastAPI /api/v1/mitigation endpoints."""

    def test_list_strategies_endpoint(self):
        """Test that list strategies endpoint behaves as expected."""
        client = TestClient(app)
        res = client.get("/api/v1/mitigation/strategies")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 4
        strategy_ids = [s["strategy_id"] for s in data["strategies"]]
        assert "sponge_city_green" in strategy_ids
        assert "emergency_pumping" in strategy_ids
        assert "culvert_desilting" in strategy_ids
        assert "hybrid_max_mitigation" in strategy_ids

    def test_simulate_mitigation_endpoint(self):
        """Test that simulate mitigation endpoint behaves as expected."""
        client = TestClient(app)
        payload = {
            "scenario_id": "S4",
            "lead_minutes": 110,
            "lid_permeable_fraction": 0.25,
            "detention_basin_m3": 40000.0,
            "emergency_pump_m3s": 3.0,
            "unblock_culvert_in004": True,
            "include_raster": True,
        }
        res = client.post("/api/v1/mitigation/simulate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["scenario_id"] == "S4"
        assert "baseline_metrics" in data
        assert "mitigated_metrics" in data
        assert "deltas" in data
        assert len(data["mitigated_depth_grid"]) == 134 * 134
        assert data["deltas"]["depth_reduction_m"] > 0.0
        assert data["deltas"]["volume_reduction_pct"] > 0.0

    def test_simulate_preset_strategy_endpoint(self):
        """Test that simulate preset strategy endpoint behaves as expected."""
        client = TestClient(app)
        res = client.get("/api/v1/mitigation/strategies/sponge_city_green/simulate?scenario_id=S4&lead_minutes=110")
        assert res.status_code == 200
        data = res.json()
        assert data["preset_strategy"] == "Sponge City Green Infrastructure (NbS)"
        assert "deltas" in data
        assert data["mitigation_effectiveness_index"] > 0.0

    def test_unknown_strategy_returns_404(self):
        """Test that unknown strategy returns 404 behaves as expected."""
        client = TestClient(app)
        res = client.get("/api/v1/mitigation/strategies/nonexistent_package/simulate")
        assert res.status_code == 404
