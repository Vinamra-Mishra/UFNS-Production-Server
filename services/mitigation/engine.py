"""Phase F — Nature-Based Solutions (NbS) / Sponge City Drainage Mitigation Engine.

Evaluates non-mutating counterfactual intervention scenario layers on top of immutable baselines.
Zero hard-coded metrics: all values are calculated dynamically in real-time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional

import numpy as np
from pydantic import BaseModel, Field

from services.ingestion.dem import CELL_SIZE_M, DOMAIN_M, GRID_CELLS
from services.routing.impact import rasterize_line
from services.routing.policy import POLICY, classify
from services.routing.roads import NETWORK
from services.scenarios.artifacts import VALID_SCENARIO_IDS, get_depth_grid


# ---------------------------------------------------------------------------
# Intervention Configuration Schema
# ---------------------------------------------------------------------------

class InterventionConfig(BaseModel):
    """Interventionconfig schema and data model representation."""
    scenario_id: str = Field(default="S4", description="Base scenario identifier (S1..S4)")
    lead_minutes: int = Field(default=110, ge=0, le=180, description="Lead time snapshot to mitigate")
    lid_permeable_fraction: float = Field(default=0.0, ge=0.0, le=0.50, description="Permeable pavement / green roof LID coverage (0.0 to 0.50)")
    detention_basin_m3: float = Field(default=0.0, ge=0.0, le=100000.0, description="Urban retention / detention basin storage volume in m³")
    emergency_pump_m3s: float = Field(default=0.0, ge=0.0, le=10.0, description="Emergency mobile dewatering pump capacity in m³/s")
    unblock_culvert_in004: bool = Field(default=False, description="Desilt and restore Culvert IN-004 to design capacity")


# ---------------------------------------------------------------------------
# Mitigation Result Data Structures
# ---------------------------------------------------------------------------

@dataclass
class MitigationResult:
    """Mitigationresult schema and data model representation."""
    scenario_id: str
    lead_minutes: int
    config: dict[str, Any]
    baseline_metrics: dict[str, Any]
    mitigated_metrics: dict[str, Any]
    deltas: dict[str, Any]
    reopened_roads: list[str]
    still_impassable_roads: list[str]
    mitigation_effectiveness_index: float
    provenance: dict[str, Any]
    mitigated_depth_grid: list[float] = field(default_factory=list)

    def to_dict(self, include_raster: bool = False) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        out = {
            "scenario_id": self.scenario_id,
            "lead_minutes": self.lead_minutes,
            "config": self.config,
            "baseline_metrics": self.baseline_metrics,
            "mitigated_metrics": self.mitigated_metrics,
            "deltas": self.deltas,
            "reopened_roads": self.reopened_roads,
            "still_impassable_roads": self.still_impassable_roads,
            "mitigation_effectiveness_index": round(self.mitigation_effectiveness_index, 4),
            "provenance": self.provenance,
        }
        if include_raster:
            out["mitigated_depth_grid"] = self.mitigated_depth_grid
        return out


# ---------------------------------------------------------------------------
# Intervention Scenario Engine (Non-Mutating Counterfactual Simulator)
# ---------------------------------------------------------------------------

class InterventionScenarioEngine:
    """Executes dynamic counterfactual flood mitigation modeling without altering baseline data."""

    def __init__(self) -> None:
        """Execute   Init   operation and return result."""
        self.cell_area_m2 = float(CELL_SIZE_M * CELL_SIZE_M)  # 30m x 30m = 900 m²

    def simulate(self, config: InterventionConfig, return_raster: bool = False) -> MitigationResult:
        """Dynamically simulate the effect of green and grey interventions on a baseline scenario."""
        clean_sid = config.scenario_id.upper()
        if clean_sid not in VALID_SCENARIO_IDS:
            clean_sid = "S4"

        lead = config.lead_minutes

        # 1. Fetch immutable baseline depth grid
        base_grid = np.array(get_depth_grid(clean_sid, lead), dtype=np.float64)

        base_impassable = []
        base_caution = []
        base_dry = []
        for road in NETWORK.segments:
            r1, c1 = road.start_cell
            r2, c2 = road.end_cell
            cells = rasterize_line(r1, c1, r2, c2)
            depths = [float(base_grid[r, c]) for r, c in cells if 0 <= r < GRID_CELLS and 0 <= c < GRID_CELLS]
            if not depths:
                continue
            cls = classify(max(depths), POLICY)
            if cls == "IMPASSABLE":
                base_impassable.append(road.road_id)
            elif cls in ("CAUTION", "HIGH_IMPACT", "LOW_IMPACT"):
                base_caution.append(road.road_id)
            else:
                base_dry.append(road.road_id)

        base_max_d = float(np.max(base_grid)) if base_grid.size > 0 else 0.0
        base_inundated_cells = int(np.count_nonzero(base_grid >= 0.05))
        base_inundated_area_m2 = float(base_inundated_cells * self.cell_area_m2)
        base_volume_m3 = float(np.sum(base_grid) * self.cell_area_m2)

        # 2. Dynamic Counterfactual Abatement Calculation (Layered)
        delta_grid = np.zeros_like(base_grid, dtype=np.float64)
        cur_depth = np.copy(base_grid)

        # Intervention A: Desilting / Unblocking Culvert IN-004
        if config.unblock_culvert_in004 and clean_sid == "S4":
            # Counterfactual comparison with clean baseline S3 + localized surcharge relief around IN-004
            s3_grid = np.array(get_depth_grid("S3", lead), dtype=np.float64)
            unblock_delta = np.maximum(0.0, base_grid - s3_grid)
            # Hydraulic surcharge relief around street corridor & culvert junction
            corridor_mask = (base_grid > 0.20)
            unblock_delta = np.where(corridor_mask, unblock_delta + np.minimum(cur_depth, 0.08), unblock_delta)
            delta_grid += unblock_delta
            cur_depth = np.maximum(0.0, cur_depth - unblock_delta)

        # Intervention B: Permeable Pavement / Green Roofs (LID Infiltration Layer)
        if config.lid_permeable_fraction > 0.0:
            # Infiltration rate 25 mm/h over a 30-minute interval = 12.5 mm = 0.0125 m per interval
            # Scaled by LID coverage fraction
            lid_depth_abatement_m = (25.0 / 1000.0) * 0.5 * config.lid_permeable_fraction
            lid_delta = np.minimum(cur_depth, lid_depth_abatement_m)
            delta_grid += lid_delta
            cur_depth = np.maximum(0.0, cur_depth - lid_delta)

        # Intervention C: Urban Retention / Detention Basins
        if config.detention_basin_m3 > 0.0:
            # Allocate basin storage to deep ponding zones (cells with depth > 0.15m)
            deep_cells = cur_depth >= 0.15
            n_deep = int(np.count_nonzero(deep_cells))
            if n_deep > 0:
                basin_capacity_per_cell_m = config.detention_basin_m3 / (n_deep * self.cell_area_m2)
                basin_delta = np.where(deep_cells, np.minimum(cur_depth, basin_capacity_per_cell_m), 0.0)
                delta_grid += basin_delta
                cur_depth = np.maximum(0.0, cur_depth - basin_delta)

        # Intervention D: Emergency Mobile Dewatering Pumps
        if config.emergency_pump_m3s > 0.0:
            # Active pumping over 30-minute window (1800 s)
            pump_volume_m3 = config.emergency_pump_m3s * 1800.0
            flooded_cells = cur_depth >= 0.10
            n_flooded = int(np.count_nonzero(flooded_cells))
            if n_flooded > 0:
                pump_depth_per_cell_m = pump_volume_m3 / (n_flooded * self.cell_area_m2)
                pump_delta = np.where(flooded_cells, np.minimum(cur_depth, pump_depth_per_cell_m), 0.0)
                delta_grid += pump_delta
                cur_depth = np.maximum(0.0, cur_depth - pump_delta)

        # Final non-negative counterfactual depth raster
        mitigated_grid = np.maximum(0.0, base_grid - delta_grid)

        # 3. Dynamic Mitigated Metrics Computation
        mit_max_d = float(np.max(mitigated_grid)) if mitigated_grid.size > 0 else 0.0
        mit_inundated_cells = int(np.count_nonzero(mitigated_grid >= 0.05))
        mit_inundated_area_m2 = float(mit_inundated_cells * self.cell_area_m2)
        mit_volume_m3 = float(np.sum(mitigated_grid) * self.cell_area_m2)

        # 4. Dynamic Road Impassability Re-evaluation
        mit_impassable: list[str] = []
        mit_caution: list[str] = []
        mit_dry: list[str] = []

        # Re-evaluate all road segments across mitigated depth raster using standard POLICY
        for road in NETWORK.segments:
            r1, c1 = road.start_cell
            r2, c2 = road.end_cell
            cells = rasterize_line(r1, c1, r2, c2)
            depths_on_road = [float(mitigated_grid[r, c]) for r, c in cells if 0 <= r < GRID_CELLS and 0 <= c < GRID_CELLS]
            if not depths_on_road:
                continue
            max_road_d = max(depths_on_road)
            cls = classify(max_road_d, POLICY)
            if cls == "IMPASSABLE":
                mit_impassable.append(road.road_id)
            elif cls in ("CAUTION", "HIGH_IMPACT", "LOW_IMPACT"):
                mit_caution.append(road.road_id)
            else:
                mit_dry.append(road.road_id)

        # Reopened roads: roads that were IMPASSABLE in baseline but are now CAUTION or DRY
        reopened_roads = [rid for rid in base_impassable if rid not in mit_impassable]

        # 5. Compute Dynamic Deltas & Reductions
        d_depth = max(0.0, base_max_d - mit_max_d)
        d_depth_pct = (d_depth / base_max_d * 100.0) if base_max_d > 0 else 0.0

        d_area = max(0.0, base_inundated_area_m2 - mit_inundated_area_m2)
        d_area_pct = (d_area / base_inundated_area_m2 * 100.0) if base_inundated_area_m2 > 0 else 0.0

        d_vol = max(0.0, base_volume_m3 - mit_volume_m3)
        d_vol_pct = (d_vol / base_volume_m3 * 100.0) if base_volume_m3 > 0 else 0.0

        # Mitigation Effectiveness Index (MEI) in [0.0, 1.0]
        mei_depth_term = min(1.0, d_depth / base_max_d) if base_max_d > 0 else 0.0
        mei_area_term = min(1.0, d_area / base_inundated_area_m2) if base_inundated_area_m2 > 0 else 0.0
        mei_road_term = (len(reopened_roads) / len(base_impassable)) if len(base_impassable) > 0 else 1.0
        mei = 0.40 * mei_depth_term + 0.40 * mei_area_term + 0.20 * mei_road_term

        base_metrics = {
            "max_depth_m": round(base_max_d, 3),
            "inundated_area_m2": round(base_inundated_area_m2, 1),
            "flood_volume_m3": round(base_volume_m3, 1),
            "impassable_count": len(base_impassable),
            "caution_count": len(base_caution),
            "dry_count": len(base_dry),
        }

        mit_metrics = {
            "max_depth_m": round(mit_max_d, 3),
            "inundated_area_m2": round(mit_inundated_area_m2, 1),
            "flood_volume_m3": round(mit_volume_m3, 1),
            "impassable_count": len(mit_impassable),
            "caution_count": len(mit_caution),
            "dry_count": len(mit_dry),
        }

        deltas = {
            "depth_reduction_m": round(d_depth, 3),
            "depth_reduction_pct": round(d_depth_pct, 1),
            "area_reduction_m2": round(d_area, 1),
            "area_reduction_pct": round(d_area_pct, 1),
            "volume_reduction_m3": round(d_vol, 1),
            "volume_reduction_pct": round(d_vol_pct, 1),
            "reopened_roads_count": len(reopened_roads),
            "reopened_road_ids": reopened_roads,
        }

        provenance = {
            "classification": "COUNTERFACTUAL_INTERVENTION_SCENARIO",
            "baseline_unaltered": True,
            "baseline_scenario_id": clean_sid,
            "lead_minutes": lead,
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
            "scientific_disclaimer": "SIMULATION ESTIMATE FOR CIVIC INTERVENTION PLANNING · NOT FOR LIVE OPERATIONAL DISPATCH",
        }

        flat_raster = [round(float(v), 4) for v in mitigated_grid.reshape(-1)] if return_raster else []

        return MitigationResult(
            scenario_id=clean_sid,
            lead_minutes=lead,
            config=config.model_dump(),
            baseline_metrics=base_metrics,
            mitigated_metrics=mit_metrics,
            deltas=deltas,
            reopened_roads=reopened_roads,
            still_impassable_roads=mit_impassable,
            mitigation_effectiveness_index=float(mei),
            provenance=provenance,
            mitigated_depth_grid=flat_raster,
        )


GLOBAL_MITIGATION_ENGINE = InterventionScenarioEngine()
