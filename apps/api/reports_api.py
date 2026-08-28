"""Phase E — Executive Disaster Management Dossier & PDF Export API.

FastAPI endpoints for:
- Generating official MoES/NDMA incident dossiers
- Exporting publication-quality vector PDF reports
- Retrieving structured dossier JSON and latest records
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from services.reporting.dossier import (
    GLOBAL_DOSSIER_COMPILER,
    FloodIncidentDossier,
    compile_dossier_from_scenario,
)

router = APIRouter(prefix="/api/v1/reports", tags=["Reports & Incident Dossiers"])

# In-memory registry for compiled dossiers
DOSSIER_REGISTRY: dict[str, FloodIncidentDossier] = {}
LATEST_DOSSIER_ID: str | None = None


class GenerateReportRequest(BaseModel):
    """Generatereportrequest schema and data model representation."""
    scenario_id: str = Field(default="S4", description="Scenario ID (S1..S4)")
    lead_minutes: int = Field(default=110, ge=0, le=180, description="Forecast lead time in minutes")


@router.post("/generate")
def generate_dossier(req: GenerateReportRequest) -> dict[str, Any]:
    """Generate an official incident dossier for a simulation scenario and lead time."""
    global LATEST_DOSSIER_ID

    dossier = compile_dossier_from_scenario(
        scenario_id=req.scenario_id,
        lead_minutes=req.lead_minutes,
    )

    DOSSIER_REGISTRY[dossier.dossier_id] = dossier
    LATEST_DOSSIER_ID = dossier.dossier_id

    return {
        "generated": True,
        "dossier_id": dossier.dossier_id,
        "pdf_url": f"/api/v1/reports/{dossier.dossier_id}.pdf",
        "dossier": dossier.to_dict(),
    }


@router.get("/latest")
def get_latest_dossier() -> dict[str, Any]:
    """Retrieve the most recently generated dossier."""
    if LATEST_DOSSIER_ID is None or LATEST_DOSSIER_ID not in DOSSIER_REGISTRY:
        # Generate default S4-110 dossier
        dossier = compile_dossier_from_scenario("S4", 110)
        DOSSIER_REGISTRY[dossier.dossier_id] = dossier
        return {
            "dossier_id": dossier.dossier_id,
            "pdf_url": f"/api/v1/reports/{dossier.dossier_id}.pdf",
            "dossier": dossier.to_dict(),
        }

    dossier = DOSSIER_REGISTRY[LATEST_DOSSIER_ID]
    return {
        "dossier_id": dossier.dossier_id,
        "pdf_url": f"/api/v1/reports/{dossier.dossier_id}.pdf",
        "dossier": dossier.to_dict(),
    }


@router.get("/{report_id}.pdf")
def download_dossier_pdf(report_id: str, download: bool = Query(default=False)) -> Response:
    """Compile and download/stream the official vector PDF dossier."""
    clean_id = report_id.replace(".pdf", "")

    if clean_id in DOSSIER_REGISTRY:
        dossier = DOSSIER_REGISTRY[clean_id]
    else:
        # Fallback compilation if ID encodes scenario-lead e.g. UFNS-DOSSIER-...-S4-110
        parts = clean_id.split("-")
        if len(parts) >= 2 and parts[-2] in ["S1", "S2", "S3", "S4"] and parts[-1].isdigit():
            scen = parts[-2]
            lead = max(0, min(180, int(parts[-1])))
            dossier = compile_dossier_from_scenario(scen, lead)
            if len(DOSSIER_REGISTRY) >= 100:
                DOSSIER_REGISTRY.pop(next(iter(DOSSIER_REGISTRY)))
            DOSSIER_REGISTRY[clean_id] = dossier
        else:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "DOSSIER_NOT_FOUND", "message": f"Dossier '{clean_id}' not found. Call POST /api/v1/reports/generate first."}},
            )

    compiler = GLOBAL_DOSSIER_COMPILER
    pdf_bytes = compiler.compile_pdf(dossier)

    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{clean_id}.pdf"',
            "Content-Type": "application/pdf",
        },
    )


@router.get("/{report_id}")
def get_dossier_json(report_id: str) -> dict[str, Any]:
    """Retrieve structured JSON representation of an incident dossier."""
    clean_id = report_id.replace(".pdf", "")
    if clean_id in DOSSIER_REGISTRY:
        dossier = DOSSIER_REGISTRY[clean_id]
    else:
        parts = clean_id.split("-")
        if len(parts) >= 2 and parts[-2] in ["S1", "S2", "S3", "S4"] and parts[-1].isdigit():
            scen = parts[-2]
            lead = max(0, min(180, int(parts[-1])))
            dossier = compile_dossier_from_scenario(scen, lead)
            if len(DOSSIER_REGISTRY) >= 100:
                DOSSIER_REGISTRY.pop(next(iter(DOSSIER_REGISTRY)))
            DOSSIER_REGISTRY[clean_id] = dossier
        else:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "DOSSIER_NOT_FOUND", "message": f"Dossier '{clean_id}' not found. Call POST /api/v1/reports/generate first."}},
            )

    return {
        "dossier_id": dossier.dossier_id,
        "pdf_url": f"/api/v1/reports/{dossier.dossier_id}.pdf",
        "dossier": dossier.to_dict(),
    }
