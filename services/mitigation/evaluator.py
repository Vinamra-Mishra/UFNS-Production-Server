"""Phase F — Mitigation Strategies Catalog and Evaluation Logic.

Defines standard green/grey infrastructure presets and scoring metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.mitigation.engine import InterventionConfig


@dataclass(frozen=True)
class MitigationStrategyPreset:
    """Mitigationstrategypreset schema and data model representation."""
    strategy_id: str
    name: str
    category: str
    description: str
    config: InterventionConfig

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "config": self.config.model_dump(),
        }


MITIGATION_STRATEGIES: dict[str, MitigationStrategyPreset] = {
    "sponge_city_green": MitigationStrategyPreset(
        strategy_id="sponge_city_green",
        name="Sponge City Green Infrastructure (NbS)",
        category="Nature-Based Solutions (NbS)",
        description="Deploys 30% permeable pavements and green roofs across the catchment with a 30,000 m³ urban retention wetland.",
        config=InterventionConfig(
            scenario_id="S4",
            lead_minutes=110,
            lid_permeable_fraction=0.30,
            detention_basin_m3=30000.0,
            emergency_pump_m3s=0.0,
            unblock_culvert_in004=False,
        ),
    ),
    "emergency_pumping": MitigationStrategyPreset(
        strategy_id="emergency_pumping",
        name="Emergency Mobile Dewatering Deployment",
        category="Emergency Operations",
        description="Deploys 5.0 m³/s of high-capacity mobile dewatering pumps directly at critical flooded road intersections.",
        config=InterventionConfig(
            scenario_id="S4",
            lead_minutes=110,
            lid_permeable_fraction=0.0,
            detention_basin_m3=0.0,
            emergency_pump_m3s=5.0,
            unblock_culvert_in004=False,
        ),
    ),
    "culvert_desilting": MitigationStrategyPreset(
        strategy_id="culvert_desilting",
        name="Sewer Outfall Desilting (IN-004)",
        category="Structural Remediation",
        description="Removes sediment clogging at Culvert IN-004, restoring orifice exchange capacity (Cd = 0.60) and relieving subsurface surcharge.",
        config=InterventionConfig(
            scenario_id="S4",
            lead_minutes=110,
            lid_permeable_fraction=0.0,
            detention_basin_m3=0.0,
            emergency_pump_m3s=0.0,
            unblock_culvert_in004=True,
        ),
    ),
    "hybrid_max_mitigation": MitigationStrategyPreset(
        strategy_id="hybrid_max_mitigation",
        name="Integrated Hybrid Green-Grey Package",
        category="Comprehensive Resilience",
        description="Combines 35% permeable LID pavements, 50,000 m³ retention storage, 4.0 m³/s dewatering pumps, and full culvert desilting.",
        config=InterventionConfig(
            scenario_id="S4",
            lead_minutes=110,
            lid_permeable_fraction=0.35,
            detention_basin_m3=50000.0,
            emergency_pump_m3s=4.0,
            unblock_culvert_in004=True,
        ),
    ),
}


def calculate_effectiveness_index(
    depth_red_pct: float,
    area_red_pct: float,
    reopened_fraction: float,
) -> float:
    """Compute normalized composite Mitigation Effectiveness Index (MEI)."""
    d_term = max(0.0, min(1.0, depth_red_pct / 100.0))
    a_term = max(0.0, min(1.0, area_red_pct / 100.0))
    r_term = max(0.0, min(1.0, reopened_fraction))
    return 0.40 * d_term + 0.40 * a_term + 0.20 * r_term
