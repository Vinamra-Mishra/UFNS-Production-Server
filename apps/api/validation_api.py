"""Phase I — Scientific Hydrodynamic Benchmark & Model Validation API.

FastAPI endpoints for:
- Listing reference hydrodynamic benchmark datasets
- Running quantitative model accuracy evaluations (NSE, KGE, CSI, POD, FAR, RMSE)
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.validation.benchmark import (
    BENCHMARK_CATALOG,
    GLOBAL_BENCHMARK_ENGINE,
)

router = APIRouter(prefix="/api/v1/validation", tags=["Scientific Validation & Benchmarks"])


class EvaluateBenchmarkRequest(BaseModel):
    """Evaluatebenchmarkrequest schema and data model representation."""
    scenario_id: str = Field(default="S4", description="Scenario identifier (S1..S4)")
    lead_minutes: int = Field(default=110, ge=0, le=180, description="Lead time in minutes")
    benchmark_id: str = Field(default="BENCHMARK_S3_CLEAN", description="Reference benchmark ID")


@router.get("/benchmarks")
def list_benchmarks() -> dict[str, Any]:
    """List available reference hydrodynamic benchmark datasets."""
    return {
        "count": len(BENCHMARK_CATALOG),
        "benchmarks": [b.to_dict() for b in BENCHMARK_CATALOG.values()],
    }


@router.post("/evaluate")
def evaluate_model_benchmark(req: EvaluateBenchmarkRequest) -> dict[str, Any]:
    """Evaluate simulation against a reference benchmark and compute scientific metrics."""
    res = GLOBAL_BENCHMARK_ENGINE.evaluate(
        scenario_id=req.scenario_id,
        lead_minutes=req.lead_minutes,
        benchmark_id=req.benchmark_id,
    )
    return res.to_dict()
