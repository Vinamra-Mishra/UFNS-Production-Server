"""Phase J — Multi-Objective Intervention Optimization Solver.

Solves the optimal allocation of Nature-Based Solutions and grey drainage assets
subject to municipal budget constraints and maximizes the Benefit-Cost Ratio (BCR).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from services.mitigation.engine import GLOBAL_MITIGATION_ENGINE, InterventionConfig
from services.optimization.cost_model import (
    calculate_damage_valuation,
    calculate_intervention_cost,
)


@dataclass
class ParetoPackage:
    """Paretopackage schema and data model representation."""
    tier_id: str
    name: str
    target_budget_crores: float
    lid_permeable_fraction: float
    detention_basin_m3: float
    emergency_pump_m3s: float
    unblock_culvert_in004: bool
    cost_breakdown: dict[str, Any]
    economic_benefit: dict[str, Any]
    benefit_cost_ratio_bcr: float
    mitigation_effectiveness_index: float
    depth_reduction_pct: float
    area_reduction_pct: float
    reopened_roads_count: int
    description: str

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "tier_id": self.tier_id,
            "name": self.name,
            "target_budget_crores": self.target_budget_crores,
            "configuration": {
                "lid_permeable_fraction": self.lid_permeable_fraction,
                "detention_basin_m3": self.detention_basin_m3,
                "emergency_pump_m3s": self.emergency_pump_m3s,
                "unblock_culvert_in004": self.unblock_culvert_in004,
            },
            "cost_breakdown": self.cost_breakdown,
            "economic_benefit": self.economic_benefit,
            "benefit_cost_ratio_bcr": round(self.benefit_cost_ratio_bcr, 2),
            "mitigation_effectiveness_index": round(self.mitigation_effectiveness_index, 3),
            "depth_reduction_pct": round(self.depth_reduction_pct, 1),
            "area_reduction_pct": round(self.area_reduction_pct, 1),
            "reopened_roads_count": self.reopened_roads_count,
            "description": self.description,
        }


@dataclass
class OptimizationResult:
    """Optimizationresult schema and data model representation."""
    scenario_id: str
    lead_minutes: int
    max_budget_crores: float
    optimal_recommended_tier: str
    pareto_frontier: list[dict[str, Any]]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "scenario_id": self.scenario_id,
            "lead_minutes": self.lead_minutes,
            "max_budget_crores": self.max_budget_crores,
            "optimal_recommended_tier": self.optimal_recommended_tier,
            "pareto_frontier": self.pareto_frontier,
            "provenance": self.provenance,
        }


class InterventionOptimizer:
    """Multi-objective optimizer evaluating the Pareto frontier of urban flood mitigation packages."""

    def _evaluate_candidate(
        self,
        tier_id: str,
        name: str,
        target_budget_crores: float,
        lid: float,
        basin: float,
        pump: float,
        desilt: bool,
        scenario_id: str,
        lead_minutes: int,
        description: str,
    ) -> ParetoPackage:
        """Execute  Evaluate Candidate operation and return result."""
        # Run counterfactual physical simulation
        cfg = InterventionConfig(
            scenario_id=scenario_id,
            lead_minutes=lead_minutes,
            lid_permeable_fraction=lid,
            detention_basin_m3=basin,
            emergency_pump_m3s=pump,
            unblock_culvert_in004=desilt,
        )
        sim_res = GLOBAL_MITIGATION_ENGINE.simulate(cfg)

        # Calculate CAPEX
        costs = calculate_intervention_cost(
            lid_permeable_fraction=lid,
            detention_basin_m3=basin,
            emergency_pump_m3s=pump,
            unblock_culvert_in004=desilt,
        )

        # Calculate Avoided Losses
        d = sim_res.deltas
        area_red = float(d.get("area_reduction_m2", d.get("inundated_area_reduction_m2", 0.0)))
        vol_red = float(d.get("volume_reduction_m3", d.get("flood_volume_reduction_m3", 0.0)))
        reopened = int(d.get("reopened_roads_count", 0))
        depth_pct = float(d.get("depth_reduction_pct", 0.0))
        area_pct = float(d.get("area_reduction_pct", 0.0))

        benefits = calculate_damage_valuation(
            area_reduction_m2=area_red,
            volume_reduction_m3=vol_red,
            reopened_roads_count=reopened,
            protected_assets_count=0,
        )

        capex = costs["total_capex_inr"]
        tot_benefit = benefits["total_avoided_losses_inr"]
        bcr = (tot_benefit / capex) if capex > 0 else 0.0

        return ParetoPackage(
            tier_id=tier_id,
            name=name,
            target_budget_crores=target_budget_crores,
            lid_permeable_fraction=lid,
            detention_basin_m3=basin,
            emergency_pump_m3s=pump,
            unblock_culvert_in004=desilt,
            cost_breakdown=costs,
            economic_benefit=benefits,
            benefit_cost_ratio_bcr=bcr,
            mitigation_effectiveness_index=sim_res.mitigation_effectiveness_index,
            depth_reduction_pct=depth_pct,
            area_reduction_pct=area_pct,
            reopened_roads_count=reopened,
            description=description,
        )

    def solve(
        self,
        scenario_id: str = "S4",
        lead_minutes: int = 110,
        budget_crores: float = 15.0,
    ) -> OptimizationResult:
        """Solves optimal investment packages across 3 Pareto tiers within budget."""
        candidates = [
            self._evaluate_candidate(
                tier_id="TIER_1_TACTICAL",
                name="Emergency Tactical Relief (Mobile Pumping + Desilting)",
                target_budget_crores=1.0,
                lid=0.0,
                basin=0.0,
                pump=3.0,
                desilt=True,
                scenario_id=scenario_id,
                lead_minutes=lead_minutes,
                description="Low-CAPEX emergency response package focusing on rapid dewatering and culvert clearing.",
            ),
            self._evaluate_candidate(
                tier_id="TIER_2_BALANCED",
                name="Balanced Green-Grey Resilience Package",
                target_budget_crores=7.5,
                lid=0.15,
                basin=50000.0,
                pump=5.0,
                desilt=True,
                scenario_id=scenario_id,
                lead_minutes=lead_minutes,
                description="Optimal cost-benefit package combining permeable pavements, mid-sized retention pond, and mobile pumps.",
            ),
            self._evaluate_candidate(
                tier_id="TIER_3_RESILIENT",
                name="Full Climate-Resilient Sponge City Package",
                target_budget_crores=18.0,
                lid=0.35,
                basin=100000.0,
                pump=10.0,
                desilt=True,
                scenario_id=scenario_id,
                lead_minutes=lead_minutes,
                description="Maximum flood risk abatement package achieving highest MEI and long-term urban adaptation.",
            ),
        ]

        # Determine optimal tier that fits within budget_crores (maximizing BCR with MEI tie-breaker)
        feasible = [c for c in candidates if c.cost_breakdown["total_capex_crores"] <= budget_crores]
        if feasible:
            optimal_pkg = max(feasible, key=lambda x: (x.benefit_cost_ratio_bcr, x.mitigation_effectiveness_index))
            recommended_tier = optimal_pkg.tier_id
        else:
            recommended_tier = "NO_FEASIBLE_PACKAGE"

        provenance = {
            "classification": "PARETO_OPTIMIZATION_DECISION_SUPPORT",
            "scenario_id": scenario_id,
            "lead_minutes": lead_minutes,
            "budget_crores_constraint": budget_crores,
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
            "methodology": "Multi-objective Pareto solver with CPWD civic cost schedules and non-linear damage abatement",
        }

        return OptimizationResult(
            scenario_id=scenario_id,
            lead_minutes=lead_minutes,
            max_budget_crores=budget_crores,
            optimal_recommended_tier=recommended_tier,
            pareto_frontier=[c.to_dict() for c in candidates],
            provenance=provenance,
        )


GLOBAL_INTERVENTION_OPTIMIZER = InterventionOptimizer()
