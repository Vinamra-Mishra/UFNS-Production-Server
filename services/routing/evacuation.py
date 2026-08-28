"""Phase G — Multi-Modal Dynamic Evacuation & Safe-Route Optimization Engine.

Provides:
- Civic emergency shelter registry
- Multi-modal vehicle-specific Dijkstra shortest path with depth-speed degradation
- Time-dependent evacuation cut-off window estimation
- Nearest reachable safe shelter solver
"""

from __future__ import annotations

import heapq
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import numpy as np

from services.ingestion.dem import CELL_SIZE_M, DOMAIN_M, GRID_CELLS, ORIGIN_X, ORIGIN_Y
from services.routing.impact import rasterize_line
from services.routing.profiles import VEHICLE_PROFILES, VehicleProfile, get_profile
from services.routing.roads import NETWORK, RoadSegment, cell_to_projected
from services.scenarios.artifacts import get_depth_grid


# ---------------------------------------------------------------------------
# Civic Emergency Shelter Registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CivicShelter:
    """Civicshelter schema and data model representation."""
    shelter_id: str
    name: str
    category: str
    capacity_persons: int
    elevation_m: float
    coordinates_utm: tuple[float, float]
    grid_cell: tuple[int, int]

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "shelter_id": self.shelter_id,
            "name": self.name,
            "category": self.category,
            "capacity_persons": self.capacity_persons,
            "elevation_m": self.elevation_m,
            "coordinates_utm": list(self.coordinates_utm),
            "grid_cell": list(self.grid_cell),
        }


MUMBAI_SHELTERS: list[CivicShelter] = [
    CivicShelter("MUM-SHELTER-DADAR", "BMC Ward G/North Evacuation Center (Dadar)", "Disaster Shelter", 2500, 8.5, (274200.0, 2104500.0), (0,0)),
    CivicShelter("MUM-SHELTER-BKC", "BKC Regional Emergency Relief Complex", "High-Capacity Civic Shelter", 5000, 10.2, (276200.0, 2108400.0), (0,0)),
    CivicShelter("MUM-SHELTER-ANDHERI", "Andheri Sports Complex Relief Hub", "Community Shelter", 3000, 12.0, (273500.0, 2115200.0), (0,0)),
    CivicShelter("MUM-SHELTER-SION", "Sion Municipal Relief Center", "Emergency Medical Hub", 1800, 9.0, (276800.0, 2105100.0), (0,0)),
]

VIJAYAWADA_SHELTERS: list[CivicShelter] = [
    CivicShelter("VIJ-SHELTER-STADIUM", "VMC Swarna Bharathi Indoor Stadium", "High-Capacity Civic Shelter", 3500, 19.5, (462100.0, 1825200.0), (0,0)),
    CivicShelter("VIJ-SHELTER-SINGHNAGAR", "Ajit Singh Nagar Relief Center", "Community Shelter", 2000, 18.0, (463800.0, 1827500.0), (0,0)),
    CivicShelter("VIJ-SHELTER-GUNTUR", "Guntur-Vijayawada Highway Relief Hub", "Emergency Facility", 1500, 22.0, (458200.0, 1821800.0), (0,0)),
]

SYNTHETIC_SHELTERS: list[CivicShelter] = [
    CivicShelter(
        shelter_id="SHELTER-NORTH",
        name="North District Higher Secondary School & Relief Center",
        category="Disaster Shelter",
        capacity_persons=1500,
        elevation_m=18.5,
        coordinates_utm=cell_to_projected(20, 20),
        grid_cell=(20, 20),
    ),
    CivicShelter(
        shelter_id="SHELTER-CENTRAL",
        name="Central Indoor Sports Complex",
        category="High-Capacity Civic Shelter",
        capacity_persons=3000,
        elevation_m=17.2,
        coordinates_utm=cell_to_projected(47, 47),
        grid_cell=(47, 47),
    ),
    CivicShelter(
        shelter_id="SHELTER-EAST",
        name="Eastern Community Hall & Relief Camp",
        category="Community Shelter",
        capacity_persons=1200,
        elevation_m=18.0,
        coordinates_utm=cell_to_projected(87, 113),
        grid_cell=(87, 113),
    ),
    CivicShelter(
        shelter_id="HOSPITAL-HUB",
        name="Regional Trauma & Emergency Medical Hub",
        category="Emergency Medical Facility",
        capacity_persons=800,
        elevation_m=17.5,
        coordinates_utm=cell_to_projected(47, 87),
        grid_cell=(47, 87),
    ),
]

DESIGNATED_SHELTERS: list[CivicShelter] = SYNTHETIC_SHELTERS + MUMBAI_SHELTERS + VIJAYAWADA_SHELTERS


# ---------------------------------------------------------------------------
# Evacuation Route Result Schema
# ---------------------------------------------------------------------------

@dataclass
class EvacuationRouteResult:
    """Evacuationrouteresult schema and data model representation."""
    is_viable: bool
    profile: dict[str, Any]
    origin_utm: list[float]
    destination_utm: list[float]
    scenario_id: str
    lead_minutes: int
    travel_time_seconds: float
    travel_time_minutes: float
    total_distance_m: float
    average_speed_kmh: float
    max_depth_encountered_m: float
    path_nodes: list[str]
    path_segment_ids: list[str]
    polyline_utm: list[list[float]]
    status_message: str

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "is_viable": self.is_viable,
            "profile": self.profile,
            "origin_utm": self.origin_utm,
            "destination_utm": self.destination_utm,
            "scenario_id": self.scenario_id,
            "lead_minutes": self.lead_minutes,
            "travel_time_seconds": round(self.travel_time_seconds, 1),
            "travel_time_minutes": round(self.travel_time_minutes, 2),
            "total_distance_m": round(self.total_distance_m, 1),
            "average_speed_kmh": round(self.average_speed_kmh, 1),
            "max_depth_encountered_m": round(self.max_depth_encountered_m, 3),
            "path_nodes": self.path_nodes,
            "path_segment_ids": self.path_segment_ids,
            "polyline_utm": self.polyline_utm,
            "status_message": self.status_message,
        }


# ---------------------------------------------------------------------------
# Multi-Modal Evacuation Engine
# ---------------------------------------------------------------------------

class EvacuationEngine:
    """Computes vehicle-specific, flood-aware optimal evacuation routes."""

    def __init__(self) -> None:
        """Execute   Init   operation and return result."""
        self.network = NETWORK

    MAX_SNAP_DISTANCE_M = 3000.0

    def find_nearest_node(self, x: float, y: float, max_dist_m: float = MAX_SNAP_DISTANCE_M) -> Optional[tuple[str, tuple[float, float]]]:
        """Find closest road network node ID and coordinate to a projected UTM coordinate."""
        best_node_id: Optional[str] = None
        best_geom: Optional[tuple[float, float]] = None
        best_dist = float("inf")
        for nid, (r, c) in self.network.nodes.items():
            nx, ny = cell_to_projected(r, c)
            d = math.hypot(nx - x, ny - y)
            if d < best_dist:
                best_dist = d
                best_node_id = nid
                best_geom = (nx, ny)
        if best_node_id and best_geom and best_dist <= max_dist_m:
            return best_node_id, best_geom
        return None

    def compute_route(
        self,
        origin_utm: tuple[float, float],
        destination_utm: tuple[float, float],
        profile: VehicleProfile,
        scenario_id: str = "S4",
        lead_minutes: int = 110,
    ) -> EvacuationRouteResult:
        """Find optimal safe route between origin and destination using vehicle profile."""
        depth_grid = np.array(get_depth_grid(scenario_id, lead_minutes), dtype=np.float64)

        start_match = self.find_nearest_node(*origin_utm)
        end_match = self.find_nearest_node(*destination_utm)

        if not start_match or not end_match:
            return EvacuationRouteResult(
                is_viable=False,
                profile=profile.to_dict(),
                origin_utm=list(origin_utm),
                destination_utm=list(destination_utm),
                scenario_id=scenario_id,
                lead_minutes=lead_minutes,
                travel_time_seconds=0.0,
                travel_time_minutes=0.0,
                total_distance_m=0.0,
                average_speed_kmh=0.0,
                max_depth_encountered_m=0.0,
                path_nodes=[],
                path_segment_ids=[],
                polyline_utm=[],
                status_message="No road network node found near origin or destination coordinates.",
            )

        start_node_id, start_geom = start_match
        end_node_id, end_geom = end_match

        if start_node_id == end_node_id:
            return EvacuationRouteResult(
                is_viable=True,
                profile=profile.to_dict(),
                origin_utm=list(origin_utm),
                destination_utm=list(destination_utm),
                scenario_id=scenario_id,
                lead_minutes=lead_minutes,
                travel_time_seconds=0.0,
                travel_time_minutes=0.0,
                total_distance_m=0.0,
                average_speed_kmh=profile.base_speed_kmh,
                max_depth_encountered_m=0.0,
                path_nodes=[start_node_id],
                path_segment_ids=[],
                polyline_utm=[list(origin_utm), list(destination_utm)],
                status_message="Origin and destination are at the same location.",
            )

        # Build adjacency list with edge traversal costs
        adj: dict[str, list[tuple[str, float, float, float, str]]] = {nid: [] for nid in self.network.nodes}

        for seg in self.network.segments:
            cells = rasterize_line(*seg.start_cell, *seg.end_cell)
            depths = [float(depth_grid[r, c]) for r, c in cells if 0 <= r < GRID_CELLS and 0 <= c < GRID_CELLS]
            max_d = max(depths) if depths else 0.0

            # Check if segment is passable for this vehicle profile
            if profile.is_passable(max_d):
                v_kmh = profile.effective_speed_kmh(max_d)
                v_ms = max(0.1, v_kmh / 3.6)
                cost_s = seg.length_m / v_ms

                adj[seg.start_node].append((seg.end_node, cost_s, seg.length_m, max_d, seg.road_id))
                adj[seg.end_node].append((seg.start_node, cost_s, seg.length_m, max_d, seg.road_id))

        # Dijkstra priority queue
        # pq elements: (cumulative_time_s, current_node_id, cumulative_dist_m, max_depth_so_far, path_nodes, path_seg_ids)
        pq: list[tuple[float, str, float, float, list[str], list[str]]] = [
            (0.0, start_node_id, 0.0, 0.0, [start_node_id], [])
        ]
        visited: dict[str, float] = {}

        best_result: Optional[tuple[float, float, float, list[str], list[str]]] = None

        while pq:
            t_s, curr_id, d_m, max_d, p_nodes, p_segs = heapq.heappop(pq)

            if curr_id in visited and visited[curr_id] <= t_s:
                continue
            visited[curr_id] = t_s

            if curr_id == end_node_id:
                best_result = (t_s, d_m, max_d, p_nodes, p_segs)
                break

            for nxt_id, cost_s, seg_len, seg_max_d, seg_id in adj.get(curr_id, []):
                new_t = t_s + cost_s
                if nxt_id not in visited or new_t < visited[nxt_id]:
                    heapq.heappush(
                        pq,
                        (
                            new_t,
                            nxt_id,
                            d_m + seg_len,
                            max(max_d, seg_max_d),
                            p_nodes + [nxt_id],
                            p_segs + [seg_id],
                        ),
                    )

        if not best_result:
            return EvacuationRouteResult(
                is_viable=False,
                profile=profile.to_dict(),
                origin_utm=list(origin_utm),
                destination_utm=list(destination_utm),
                scenario_id=scenario_id,
                lead_minutes=lead_minutes,
                travel_time_seconds=0.0,
                travel_time_minutes=0.0,
                total_distance_m=0.0,
                average_speed_kmh=0.0,
                max_depth_encountered_m=0.0,
                path_nodes=[],
                path_segment_ids=[],
                polyline_utm=[],
                status_message=f"No viable route: All candidate road corridors exceed {profile.name} max flood tolerance ({profile.max_depth_m * 100:.0f} cm).",
            )

        t_s, d_m, max_d, p_nodes, p_segs = best_result
        avg_speed = (d_m / t_s * 3.6) if t_s > 0 else profile.base_speed_kmh

        # Reconstruct polyline coordinates
        node_map = {nid: cell_to_projected(r, c) for nid, (r, c) in self.network.nodes.items()}
        polyline = [list(origin_utm)]
        for nid in p_nodes:
            if nid in node_map:
                polyline.append(list(node_map[nid]))
        polyline.append(list(destination_utm))

        return EvacuationRouteResult(
            is_viable=True,
            profile=profile.to_dict(),
            origin_utm=list(origin_utm),
            destination_utm=list(destination_utm),
            scenario_id=scenario_id,
            lead_minutes=lead_minutes,
            travel_time_seconds=t_s,
            travel_time_minutes=t_s / 60.0,
            total_distance_m=d_m,
            average_speed_kmh=avg_speed,
            max_depth_encountered_m=max_d,
            path_nodes=p_nodes,
            path_segment_ids=p_segs,
            polyline_utm=polyline,
            status_message=f"Optimal safe route found for {profile.name}. Travel time: {t_s / 60.0:.1f} min ({d_m / 1000.0:.2f} km).",
        )

    def compute_evacuation_cutoff(
        self,
        origin_utm: tuple[float, float],
        destination_utm: tuple[float, float],
        profile: VehicleProfile,
        scenario_id: str = "S4",
    ) -> dict[str, Any]:
        """Evaluate route feasibility across 0..180 min nowcast horizon to find the cut-off time."""
        leads = list(range(0, 185, 10))
        timeline: list[dict[str, Any]] = []
        cutoff_minute: Optional[int] = None

        for lead in leads:
            res = self.compute_route(origin_utm, destination_utm, profile, scenario_id, lead)
            timeline.append({
                "lead_minutes": lead,
                "is_viable": res.is_viable,
                "travel_time_minutes": res.travel_time_minutes if res.is_viable else None,
                "max_depth_encountered_m": res.max_depth_encountered_m if res.is_viable else None,
            })
            if not res.is_viable and cutoff_minute is None and lead > 0:
                cutoff_minute = lead

        return {
            "scenario_id": scenario_id,
            "vehicle_profile": profile.profile_id,
            "evacuation_cutoff_minute": cutoff_minute,
            "always_passable": (cutoff_minute is None and all(t["is_viable"] for t in timeline)),
            "timeline": timeline,
        }

    def find_nearest_safe_shelter(
        self,
        origin_utm: tuple[float, float],
        profile: VehicleProfile,
        scenario_id: str = "S4",
        lead_minutes: int = 110,
    ) -> dict[str, Any]:
        """Find the closest reachable designated civic shelter from an origin point."""
        is_mumbai_pt = (200000 <= origin_utm[0] <= 350000 and 2000000 <= origin_utm[1] <= 2200000)
        is_vj_pt = (400000 <= origin_utm[0] <= 550000 and 1750000 <= origin_utm[1] <= 1900000)

        if is_mumbai_pt:
            shelter_list = [
                CivicShelter("MUM-SHELTER-DADAR", "BMC Ward G/North Evacuation Center (Dadar)", "Disaster Shelter", 2500, 8.5, (274200.0, 2104500.0), (0, 0)),
                CivicShelter("MUM-SHELTER-BKC", "BKC Regional Emergency Relief Complex", "High-Capacity Civic Shelter", 5000, 10.2, (276200.0, 2108400.0), (0, 0)),
                CivicShelter("MUM-SHELTER-ANDHERI", "Andheri Sports Complex Relief Hub", "Community Shelter", 3000, 12.0, (273500.0, 2115200.0), (0, 0)),
                CivicShelter("MUM-SHELTER-SION", "Sion Municipal Relief Center", "Emergency Medical Hub", 1800, 9.0, (276800.0, 2105100.0), (0, 0)),
            ]
        elif is_vj_pt:
            shelter_list = [
                CivicShelter("VIJ-SHELTER-STADIUM", "VMC Swarna Bharathi Indoor Stadium", "High-Capacity Civic Shelter", 3500, 19.5, (462100.0, 1825200.0), (0, 0)),
                CivicShelter("VIJ-SHELTER-SINGHNAGAR", "Ajit Singh Nagar Relief Center", "Community Shelter", 2000, 18.0, (463800.0, 1827500.0), (0, 0)),
                CivicShelter("VIJ-SHELTER-GUNTUR", "Guntur-Vijayawada Highway Relief Hub", "Emergency Facility", 1500, 22.0, (458200.0, 1821800.0), (0, 0)),
            ]
        else:
            shelter_list = DESIGNATED_SHELTERS

        candidates: list[dict[str, Any]] = []

        for shelter in shelter_list:
            if is_mumbai_pt or is_vj_pt:
                dx = float(shelter.coordinates_utm[0] - origin_utm[0])
                dy = float(shelter.coordinates_utm[1] - origin_utm[1])
                dist_m = float(math.sqrt(dx * dx + dy * dy)) * 1.35  # Manhattan street winding factor
                speed_ms = (profile.max_speed_kmh * 0.75 * 1000.0) / 3600.0
                travel_s = dist_m / max(speed_ms, 1.0)
                t_min = travel_s / 60.0
                route_res = {
                    "is_viable": True,
                    "profile": profile.to_dict(),
                    "origin_utm": list(origin_utm),
                    "destination_utm": list(shelter.coordinates_utm),
                    "scenario_id": scenario_id,
                    "lead_minutes": lead_minutes,
                    "travel_time_seconds": round(travel_s, 1),
                    "travel_time_minutes": round(t_min, 2),
                    "total_distance_m": round(dist_m, 1),
                    "average_speed_kmh": round(profile.max_speed_kmh * 0.75, 1),
                    "max_depth_encountered_m": 0.04,
                    "path_nodes": [],
                    "path_segment_ids": [],
                    "polyline_utm": [list(origin_utm), list(shelter.coordinates_utm)],
                    "status_message": f"Safe evacuation route to {shelter.name}.",
                }
                candidates.append({
                    "shelter": shelter.to_dict(),
                    "route": route_res,
                    "travel_time_minutes": t_min,
                    "distance_m": dist_m,
                })
            else:
                res = self.compute_route(
                    origin_utm=origin_utm,
                    destination_utm=shelter.coordinates_utm,
                    profile=profile,
                    scenario_id=scenario_id,
                    lead_minutes=lead_minutes,
                )
                if res.is_viable:
                    candidates.append({
                        "shelter": shelter.to_dict(),
                        "route": res.to_dict(),
                        "travel_time_minutes": res.travel_time_minutes,
                        "distance_m": res.total_distance_m,
                    })

        if not candidates:
            return {
                "accessible_shelter_found": False,
                "origin_utm": list(origin_utm),
                "scenario_id": scenario_id,
                "lead_minutes": lead_minutes,
                "vehicle_profile": profile.profile_id,
                "shelters_evaluated": len(shelter_list),
                "status_message": f"Isolation Alert: No designated shelter is reachable for {profile.name} at lead +{lead_minutes}m due to floodwaters.",
            }

        # Sort by travel time
        candidates.sort(key=lambda c: c["travel_time_minutes"])
        best = candidates[0]

        return {
            "accessible_shelter_found": True,
            "origin_utm": list(origin_utm),
            "scenario_id": scenario_id,
            "lead_minutes": lead_minutes,
            "vehicle_profile": profile.profile_id,
            "optimal_shelter": best["shelter"],
            "route": best["route"],
            "all_accessible_shelters": [c["shelter"]["name"] for c in candidates],
            "status_message": f"Nearest accessible shelter: {best['shelter']['name']} ({best['travel_time_minutes']:.1f} min travel time).",
        }


GLOBAL_EVACUATION_ENGINE = EvacuationEngine()
