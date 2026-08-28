"""Phase J — Intervention Optimization & Cost-Benefit Civic Allocator API.

FastAPI endpoints for:
- Retrieving standard CPWD / Indian Municipal schedule of rates
- Running budget-constrained Pareto optimization solver for urban flood abatement
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.optimization.cost_model import CIVIL_COST_RATES, DAMAGE_VALUATION_RATES
from services.optimization.solver import GLOBAL_INTERVENTION_OPTIMIZER

router = APIRouter(prefix="/api/v1/optimization", tags=["Intervention Optimization & Cost-Benefit"])


class SolveOptimizationRequest(BaseModel):
    """Solveoptimizationrequest schema and data model representation."""
    scenario_id: str = Field(default="S4", description="Scenario identifier (S1..S4)")
    lead_minutes: int = Field(default=110, ge=0, le=180, description="Lead time in minutes")
    budget_crores: float = Field(default=10.0, ge=0.9, le=100.0, description="Municipal budget limit in Crores INR (min 0.9 Cr)")


@router.get("/rates")
def get_cost_rates() -> dict[str, Any]:
    """Retrieve itemized civil construction cost and avoided damage rates."""
    return {
        "civil_cost_rates_inr": CIVIL_COST_RATES,
        "damage_valuation_rates_inr": DAMAGE_VALUATION_RATES,
    }


@router.post("/solve")
def solve_pareto_interventions(req: SolveOptimizationRequest) -> dict[str, Any]:
    """Solve multi-objective Pareto optimization across budget constraints."""
    res = GLOBAL_INTERVENTION_OPTIMIZER.solve(
        scenario_id=req.scenario_id,
        lead_minutes=req.lead_minutes,
        budget_crores=req.budget_crores,
    )
    return res.to_dict()
