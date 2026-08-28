"""Phase G — Multi-Modal Vehicle & Mobility Profiles for Evacuation Routing.

Defines vehicle-specific flood depth tolerance, speed degradation curves, and passability policies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class VehicleProfile:
    """Vehicleprofile schema and data model representation."""
    profile_id: str
    name: str
    icon: str
    max_depth_m: float           # Critical flood depth threshold beyond which link is IMPASSABLE
    base_speed_kmh: float        # Free-flow dry travel speed in km/h
    min_speed_factor: float      # Minimum crawling speed factor in wet conditions (e.g. 0.20)
    description: str

    def effective_speed_kmh(self, depth_m: float) -> float:
        """Compute degradation of travel speed as water depth increases up to max_depth_m."""
        if depth_m <= 0.01:
            return self.base_speed_kmh
        if depth_m > self.max_depth_m:
            return 0.0  # Impassable
        # Linear degradation from 1.0 down to min_speed_factor at max_depth_m
        fraction = depth_m / self.max_depth_m
        factor = max(self.min_speed_factor, 1.0 - (1.0 - self.min_speed_factor) * fraction)
        return self.base_speed_kmh * factor

    def is_passable(self, depth_m: float) -> bool:
        """Check if vehicle can safely traverse a road with the given water depth."""
        return depth_m <= self.max_depth_m

    def to_dict(self) -> dict[str, Any]:
        """Convert vehicle profile configuration to dictionary."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Standard Multi-Modal Vehicle Fleet Catalog
# ---------------------------------------------------------------------------

VEHICLE_PROFILES: dict[str, VehicleProfile] = {
    "AMBULANCE": VehicleProfile(
        profile_id="AMBULANCE",
        name="Emergency Ambulance",
        icon="ambulance",
        max_depth_m=0.20,
        base_speed_kmh=45.0,
        min_speed_factor=0.30,
        description="High-priority medical transport. Can traverse water up to 20 cm with moderate speed reduction.",
    ),
    "SUV": VehicleProfile(
        profile_id="SUV",
        name="SUV / High Clearance",
        icon="suv",
        max_depth_m=0.30,
        base_speed_kmh=45.0,
        min_speed_factor=0.25,
        description="High ground clearance civilian SUVs and commercial vans. Safe up to 30 cm water depth.",
    ),
    "RESCUE_4X4": VehicleProfile(
        profile_id="RESCUE_4X4",
        name="Emergency / Rescue 4x4",
        icon="rescue_4x4",
        max_depth_m=0.60,
        base_speed_kmh=35.0,
        min_speed_factor=0.25,
        description="Heavy 4x4 high-clearance emergency rescue vehicle. Capable of traversing severe floodwaters up to 60 cm.",
    ),
    "HEAVY_RESCUE": VehicleProfile(
        profile_id="HEAVY_RESCUE",
        name="NDRF / Fire Rescue Truck",
        icon="heavy_rescue",
        max_depth_m=0.45,
        base_speed_kmh=30.0,
        min_speed_factor=0.25,
        description="Heavy high-clearance disaster rescue truck. Capable of traversing severe floodwaters up to 45 cm.",
    ),
    "LIGHT_VEHICLE": VehicleProfile(
        profile_id="LIGHT_VEHICLE",
        name="Civilian Light Vehicle / Car",
        icon="car",
        max_depth_m=0.10,
        base_speed_kmh=50.0,
        min_speed_factor=0.20,
        description="Standard passenger cars and auto-rickshaws. Highly vulnerable; impassable when water depth exceeds 10 cm.",
    ),
    "PEDESTRIAN": VehicleProfile(
        profile_id="PEDESTRIAN",
        name="Pedestrian Evacuee",
        icon="pedestrian",
        max_depth_m=0.05,
        base_speed_kmh=4.5,
        min_speed_factor=0.40,
        description="Walking evacuation on foot. Strict safety limit of 5 cm to avoid open manhole and swift-water hazards.",
    ),
}

PROFILE_ALIASES: dict[str, str] = {
    "CAR": "LIGHT_VEHICLE",
    "AUTO": "LIGHT_VEHICLE",
    "SEDAN": "LIGHT_VEHICLE",
    "LIGHT": "LIGHT_VEHICLE",
    "4X4": "RESCUE_4X4",
    "RESCUE": "RESCUE_4X4",
    "TRUCK": "HEAVY_RESCUE",
    "HEAVY": "HEAVY_RESCUE",
    "MEDIC": "AMBULANCE",
    "FOOT": "PEDESTRIAN",
    "WALK": "PEDESTRIAN",
}


def get_profile(profile_id: Optional[str] = None) -> VehicleProfile:
    """Lookup vehicle profile by ID (case-insensitive). Defaults to LIGHT_VEHICLE if omitted."""
    if not profile_id or not str(profile_id).strip():
        return VEHICLE_PROFILES["LIGHT_VEHICLE"]
    clean_id = str(profile_id).strip().upper()
    
    if clean_id in VEHICLE_PROFILES:
        return VEHICLE_PROFILES[clean_id]
    if clean_id in PROFILE_ALIASES:
        return VEHICLE_PROFILES[PROFILE_ALIASES[clean_id]]
        
    return VEHICLE_PROFILES["LIGHT_VEHICLE"]
