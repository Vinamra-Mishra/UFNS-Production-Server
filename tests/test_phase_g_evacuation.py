"""Phase G Test Suite — Multi-Modal Dynamic Evacuation & Safe-Route Optimization.

Tests:
- Multi-modal vehicle profiles and speed degradation physics
- Time-dependent dynamic flood-aware Dijkstra shortest path
- Evacuation cutoff timeline & window of opportunity calculations
- Nearest safe civic shelter discovery
- FastAPI /api/v1/evacuation/* endpoints
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.app import app
from services.ingestion.dem import CELL_SIZE_M, ORIGIN_X, ORIGIN_Y
from services.routing.evacuation import (
    DESIGNATED_SHELTERS,
    GLOBAL_EVACUATION_ENGINE,
    EvacuationEngine,
)
from services.routing.profiles import VEHICLE_PROFILES, get_profile


class TestVehicleProfiles:
    """Test vehicle profile specifications and speed degradation physics."""

    def test_profiles_catalog_completeness(self):
        """Test that profiles catalog completeness behaves as expected."""
        assert "AMBULANCE" in VEHICLE_PROFILES
        assert "HEAVY_RESCUE" in VEHICLE_PROFILES
        assert "LIGHT_VEHICLE" in VEHICLE_PROFILES
        assert "PEDESTRIAN" in VEHICLE_PROFILES

        amb = VEHICLE_PROFILES["AMBULANCE"]
        assert amb.max_depth_m == 0.20
        assert amb.base_speed_kmh == 45.0

        heavy = VEHICLE_PROFILES["HEAVY_RESCUE"]
        assert heavy.max_depth_m == 0.45
        assert heavy.base_speed_kmh == 30.0

        light = VEHICLE_PROFILES["LIGHT_VEHICLE"]
        assert light.max_depth_m == 0.10

        ped = VEHICLE_PROFILES["PEDESTRIAN"]
        assert ped.max_depth_m == 0.05

    def test_speed_degradation_behavior(self):
        """Test that speed degradation behavior behaves as expected."""
        amb = VEHICLE_PROFILES["AMBULANCE"]

        # Dry road
        assert amb.effective_speed_kmh(0.0) == 45.0
        # Partial flood
        v_partial = amb.effective_speed_kmh(0.10)
        assert 0.0 < v_partial < 45.0
        # Exceeding threshold
        assert amb.effective_speed_kmh(0.25) == 0.0
        assert not amb.is_passable(0.25)


class TestMultiModalRouting:
    """Test vehicle-specific dynamic shortest path solver."""

    def test_dry_condition_routing_all_profiles(self):
        """Test that dry condition routing all profiles behaves as expected."""
        engine = EvacuationEngine()
        origin = (ORIGIN_X + 20 * CELL_SIZE_M, ORIGIN_Y + 20 * CELL_SIZE_M)
        destination = (ORIGIN_X + 87 * CELL_SIZE_M, ORIGIN_Y + 87 * CELL_SIZE_M)

        for p_id in ["AMBULANCE", "HEAVY_RESCUE", "LIGHT_VEHICLE", "PEDESTRIAN"]:
            profile = get_profile(p_id)
            res = engine.compute_route(origin, destination, profile, scenario_id="S4", lead_minutes=0)
            assert res.is_viable is True
            assert res.travel_time_seconds > 0.0
            assert len(res.path_nodes) >= 2
            assert len(res.polyline_utm) >= 2

    def test_heavy_rescue_can_traverse_deeper_water_than_light_vehicle(self):
        """Test that heavy rescue can traverse deeper water than light vehicle behaves as expected."""
        engine = EvacuationEngine()
        # Route crossing the center street corridor (where depth reaches ~0.35m at lead 110 on S4)
        origin = (ORIGIN_X + 67 * CELL_SIZE_M, ORIGIN_Y + 20 * CELL_SIZE_M)
        destination = (ORIGIN_X + 67 * CELL_SIZE_M, ORIGIN_Y + 113 * CELL_SIZE_M)

        heavy = get_profile("HEAVY_RESCUE")
        res_heavy = engine.compute_route(origin, destination, heavy, scenario_id="S4", lead_minutes=110)

        light = get_profile("LIGHT_VEHICLE")
        res_light = engine.compute_route(origin, destination, light, scenario_id="S4", lead_minutes=110)

        # Heavy rescue should successfully find a route (direct or minor detour)
        assert res_heavy.is_viable is True

        # If light vehicle finds a route, it must take a longer detour or have smaller max depth encountered
        if res_light.is_viable:
            assert res_light.max_depth_encountered_m <= light.max_depth_m
            assert res_light.travel_time_seconds >= res_heavy.travel_time_seconds or res_light.total_distance_m >= res_heavy.total_distance_m


class TestEvacuationCutoffTimeline:
    """Test dynamic calculation of evacuation cutoff windows."""

    def test_evacuation_cutoff_calculation(self):
        """Test that evacuation cutoff calculation behaves as expected."""
        engine = EvacuationEngine()
        origin = (ORIGIN_X + 67 * CELL_SIZE_M, ORIGIN_Y + 20 * CELL_SIZE_M)
        destination = (ORIGIN_X + 67 * CELL_SIZE_M, ORIGIN_Y + 113 * CELL_SIZE_M)

        ped = get_profile("PEDESTRIAN")
        cutoff_data = engine.compute_evacuation_cutoff(origin, destination, ped, scenario_id="S4")

        assert "timeline" in cutoff_data
        assert len(cutoff_data["timeline"]) > 5
        assert cutoff_data["timeline"][0]["lead_minutes"] == 0
        assert cutoff_data["timeline"][0]["is_viable"] is True


class TestNearestShelterDiscovery:
    """Test nearest safe civic shelter solver."""

    def test_find_nearest_shelter_dry_and_flooded(self):
        """Test that find nearest shelter dry and flooded behaves as expected."""
        engine = EvacuationEngine()
        origin = (ORIGIN_X + 30 * CELL_SIZE_M, ORIGIN_Y + 30 * CELL_SIZE_M)
        amb = get_profile("AMBULANCE")

        res = engine.find_nearest_safe_shelter(origin, amb, scenario_id="S4", lead_minutes=60)
        assert res["accessible_shelter_found"] is True
        assert "optimal_shelter" in res
        assert res["optimal_shelter"]["shelter_id"] in [s.shelter_id for s in DESIGNATED_SHELTERS]
        assert len(res["all_accessible_shelters"]) > 0


class TestEvacuationAPIEndpoints:
    """Test FastAPI /api/v1/evacuation endpoints."""

    def test_profiles_endpoint(self):
        """Test that profiles endpoint behaves as expected."""
        client = TestClient(app)
        res = client.get("/api/v1/evacuation/profiles")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 4
        ids = [p["profile_id"] for p in data["profiles"]]
        assert "AMBULANCE" in ids
        assert "HEAVY_RESCUE" in ids

    def test_shelters_endpoint(self):
        """Test that shelters endpoint behaves as expected."""
        client = TestClient(app)
        res = client.get("/api/v1/evacuation/shelters")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 4

    def test_route_endpoint(self):
        """Test that route endpoint behaves as expected."""
        client = TestClient(app)
        payload = {
            "origin": [ORIGIN_X + 20 * CELL_SIZE_M, ORIGIN_Y + 20 * CELL_SIZE_M],
            "destination": [ORIGIN_X + 87 * CELL_SIZE_M, ORIGIN_Y + 87 * CELL_SIZE_M],
            "vehicle_profile": "AMBULANCE",
            "scenario_id": "S4",
            "lead_minutes": 110,
        }
        res = client.post("/api/v1/evacuation/route", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["is_viable"] is True
        assert data["travel_time_minutes"] > 0.0

    def test_cutoff_endpoint(self):
        """Test that cutoff endpoint behaves as expected."""
        client = TestClient(app)
        payload = {
            "origin": [ORIGIN_X + 67 * CELL_SIZE_M, ORIGIN_Y + 20 * CELL_SIZE_M],
            "destination": [ORIGIN_X + 67 * CELL_SIZE_M, ORIGIN_Y + 113 * CELL_SIZE_M],
            "vehicle_profile": "LIGHT_VEHICLE",
            "scenario_id": "S4",
        }
        res = client.post("/api/v1/evacuation/cutoff", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "timeline" in data

    def test_nearest_shelter_endpoint(self):
        """Test that nearest shelter endpoint behaves as expected."""
        client = TestClient(app)
        payload = {
            "origin": [ORIGIN_X + 47 * CELL_SIZE_M, ORIGIN_Y + 47 * CELL_SIZE_M],
            "vehicle_profile": "AMBULANCE",
            "scenario_id": "S4",
            "lead_minutes": 110,
        }
        res = client.post("/api/v1/evacuation/nearest-shelter", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["accessible_shelter_found"] is True
