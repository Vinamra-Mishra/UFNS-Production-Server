"""Phase G — Multi-Modal Dynamic Evacuation & Safe Route API.

FastAPI endpoints for:
- Listing multi-modal vehicle profiles and passability parameters
- Computing vehicle-specific, flood-aware evacuation paths
- Determining evacuation cut-off countdown windows
- Finding nearest accessible civic emergency shelters
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.routing.evacuation import (
    DESIGNATED_SHELTERS,
    GLOBAL_EVACUATION_ENGINE,
)
from services.routing.profiles import VEHICLE_PROFILES, get_profile

router = APIRouter(prefix="/api/v1/evacuation", tags=["Evacuation & Safe Routing"])


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------

class EvacuationRouteRequest(BaseModel):
    """Evacuationrouterequest schema and data model representation."""
    origin: tuple[float, float] = Field(..., description="Origin coordinates (x, y) in EPSG:32645 UTM")
    destination: tuple[float, float] = Field(..., description="Destination coordinates (x, y) in EPSG:32645 UTM")
    vehicle_profile: str = Field(default="LIGHT_VEHICLE", description="AMBULANCE, HEAVY_RESCUE, LIGHT_VEHICLE, or PEDESTRIAN")
    scenario_id: str = Field(default="S4", description="Scenario identifier (S1..S4)")
    lead_minutes: int = Field(default=110, ge=0, le=180, description="Lead time in minutes")


class EvacuationCutoffRequest(BaseModel):
    """Evacuationcutoffrequest schema and data model representation."""
    origin: tuple[float, float] = Field(..., description="Origin coordinates (x, y) in EPSG:32645 UTM")
    destination: tuple[float, float] = Field(..., description="Destination coordinates (x, y) in EPSG:32645 UTM")
    vehicle_profile: str = Field(default="LIGHT_VEHICLE", description="AMBULANCE, HEAVY_RESCUE, LIGHT_VEHICLE, or PEDESTRIAN")
    scenario_id: str = Field(default="S4", description="Scenario identifier (S1..S4)")


class NearestShelterRequest(BaseModel):
    """Nearestshelterrequest schema and data model representation."""
    origin: tuple[float, float] = Field(..., description="Origin coordinates (x, y) in EPSG:32645 UTM")
    vehicle_profile: str = Field(default="LIGHT_VEHICLE", description="AMBULANCE, HEAVY_RESCUE, LIGHT_VEHICLE, or PEDESTRIAN")
    scenario_id: str = Field(default="S4", description="Scenario identifier (S1..S4)")
    lead_minutes: int = Field(default=110, ge=0, le=180, description="Lead time in minutes")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/profiles")
def list_vehicle_profiles() -> dict[str, Any]:
    """List available multi-modal vehicle profiles and flood depth thresholds."""
    return {
        "count": len(VEHICLE_PROFILES),
        "profiles": [p.to_dict() for p in VEHICLE_PROFILES.values()],
    }


@router.get("/shelters")
def list_designated_shelters() -> dict[str, Any]:
    """List designated civic emergency shelters and medical relief hubs."""
    return {
        "count": len(DESIGNATED_SHELTERS),
        "shelters": [s.to_dict() for s in DESIGNATED_SHELTERS],
    }


@router.post("/route")
def compute_evacuation_route(req: EvacuationRouteRequest) -> dict[str, Any]:
    """Compute optimal flood-aware evacuation route for the specified vehicle profile."""
    profile = get_profile(req.vehicle_profile)
    res = GLOBAL_EVACUATION_ENGINE.compute_route(
        origin_utm=req.origin,
        destination_utm=req.destination,
        profile=profile,
        scenario_id=req.scenario_id,
        lead_minutes=req.lead_minutes,
    )
    return res.to_dict()


@router.post("/cutoff")
def compute_evacuation_cutoff(req: EvacuationCutoffRequest) -> dict[str, Any]:
    """Compute time-dependent evacuation cutoff timeline and window of opportunity."""
    profile = get_profile(req.vehicle_profile)
    return GLOBAL_EVACUATION_ENGINE.compute_evacuation_cutoff(
        origin_utm=req.origin,
        destination_utm=req.destination,
        profile=profile,
        scenario_id=req.scenario_id,
    )


@router.post("/nearest-shelter")
def find_nearest_shelter(req: NearestShelterRequest) -> dict[str, Any]:
    """Find the nearest reachable civic emergency shelter from an origin coordinate."""
    profile = get_profile(req.vehicle_profile)
    return GLOBAL_EVACUATION_ENGINE.find_nearest_safe_shelter(
        origin_utm=req.origin,
        profile=profile,
        scenario_id=req.scenario_id,
        lead_minutes=req.lead_minutes,
    )
