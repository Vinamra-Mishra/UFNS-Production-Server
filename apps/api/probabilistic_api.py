"""Phase K — Probabilistic Flood Forecasting & Ensemble Uncertainty API.

FastAPI endpoints for:
- Retrieving stochastic ensemble member specifications
- Running 10-member ensemble simulations and probabilistic exceedance risk analysis
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.probabilistic.ensemble import generate_ensemble_members
from services.probabilistic.risk_map import GLOBAL_PROBABILISTIC_ENGINE

router = APIRouter(prefix="/api/v1/probabilistic", tags=["Probabilistic Flood Forecasting & Uncertainty"])


class SimulateProbabilisticRequest(BaseModel):
    """Simulateprobabilisticrequest schema and data model representation."""
    scenario_id: str = Field(default="S4", description="Scenario identifier (S1..S4)")
    lead_minutes: int = Field(default=110, ge=0, le=180, description="Lead time in minutes")
    member_count: int = Field(default=10, ge=3, le=10, description="Number of ensemble members (3..10)")


@router.get("/members")
def list_ensemble_members() -> dict[str, Any]:
    """Retrieve canonical stochastic perturbation ensemble member definitions."""
    members = generate_ensemble_members(10)
    return {
        "count": len(members),
        "members": [m.to_dict() for m in members],
    }


@router.post("/simulate")
def simulate_probabilistic_ensemble(req: SimulateProbabilisticRequest) -> dict[str, Any]:
    """Execute stochastic ensemble simulation and return probabilistic risk envelope."""
    res = GLOBAL_PROBABILISTIC_ENGINE.simulate(
        scenario_id=req.scenario_id,
        lead_minutes=req.lead_minutes,
        member_count=req.member_count,
    )
    return res.to_dict()
