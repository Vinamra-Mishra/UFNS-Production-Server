"""FastAPI router for Phase C: Early Warning & CAP v1.2 Alerts API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from apps.api import impacts, store
from services.alerting.cap import (
    CAPAlert,
    CAPMsgType,
    CAPScope,
    CAPSeverity,
    CAPStatus,
    OperationalAuthorizationError,
)
from services.alerting.dispatcher import (
    AlertDispatcher,
    DispatchChannel,
    DispatchReceipt,
)
from services.alerting.ledger import GLOBAL_ALERT_LEDGER
from services.alerting.screening import AlertThresholds, EarlyWarningScreener
from services.routing.impact import RoadImpact

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class EvaluateAlertRequest(BaseModel):
    """Evaluatealertrequest schema and data model representation."""
    scenario_id: str = Field(default="S4", description="Scenario ID (S1..S4)")
    lead_minutes: int = Field(default=0, ge=0, le=180, description="Lead time in minutes")
    status: CAPStatus = Field(default=CAPStatus.EXERCISE, description="CAP Status (Exercise / Test / Draft)")
    dispatch: bool = Field(default=True, description="Whether to execute simulated multi-channel dispatch")


class CancelAlertRequest(BaseModel):
    """Cancelalertrequest schema and data model representation."""
    reason: str = Field(default="Flood waters receded below caution threshold", description="Cancellation reason")


class TestDispatchRequest(BaseModel):
    """Testdispatchrequest schema and data model representation."""
    alert_id: str = Field(..., description="Alert ID to dispatch")
    channels: list[DispatchChannel] = Field(
        default=[DispatchChannel.SMS_BROADCAST, DispatchChannel.WHATSAPP_BROADCAST, DispatchChannel.WEBHOOK_PUSH],
        description="Target channels",
    )


@router.post("/generate")
@router.post("/evaluate")
def evaluate_alerts(req: EvaluateAlertRequest) -> dict[str, Any]:
    """Evaluate flood depths and road impacts to generate a standardized CAP v1.2 alert."""
    if req.status == CAPStatus.ACTUAL:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "OPERATIONAL_AUTHORIZATION_REQUIRED",
                    "message": "Cannot issue 'Actual' status alert: System operates under D-016 provisional hyetographs and B13 demonstration passability. Must use Exercise/Test/Draft.",
                }
            },
        )

    clean_sid = req.scenario_id.upper()
    effective_sid = "S4" if clean_sid == "REALTIME" or clean_sid not in store.VALID_SCENARIO_IDS else req.scenario_id

    # 1. Load depth grid and road impacts from impacts module
    try:
        depth_grid = impacts.depth_grid(effective_sid, req.lead_minutes)
        raw_impacts = impacts.impacts_at(effective_sid, req.lead_minutes)
        road_impacts = [imp.to_dict() if hasattr(imp, "to_dict") else imp for imp in raw_impacts.values()]
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "DATA_NOT_FOUND", "message": f"Data not found for {req.scenario_id} at lead {req.lead_minutes}: {exc}"}},
        )

    # 3. Run threshold screening
    screener = EarlyWarningScreener()
    alert = screener.screen_simulation_frame(
        depth_grid=depth_grid,
        road_impacts=road_impacts,
        lead_minutes=req.lead_minutes,
        scenario_id=effective_sid,
        status=req.status,
    )

    if alert is None:
        return {
            "alert_generated": False,
            "message": f"Conditions in scenario {req.scenario_id} at lead +{req.lead_minutes}m are below advisory thresholds (<0.05m).",
            "scenario_id": req.scenario_id,
            "lead_minutes": req.lead_minutes,
        }

    # 4. Dispatch if requested
    dispatcher = AlertDispatcher()
    receipts: list[DispatchReceipt] = []
    if req.dispatch:
        receipts = dispatcher.dispatch(alert)

    # 5. Record in ledger
    rec = GLOBAL_ALERT_LEDGER.record_alert(
        alert=alert,
        receipts=receipts,
        scenario_id=effective_sid,
        lead_minutes=req.lead_minutes,
    )

    alert_dict = alert.to_dict()
    info_0 = alert_dict.get("info", [{}])[0] if alert_dict.get("info") else {}

    return {
        "alert_generated": True,
        "record_id": rec.record_id,
        "alert_id": alert.identifier,
        "event": info_0.get("event", "Urban Flood Warning"),
        "headline": info_0.get("headline", "Urban Flood Advisory"),
        "severity": info_0.get("severity", "Severe"),
        "urgency": info_0.get("urgency", "Immediate"),
        "certainty": info_0.get("certainty", "Observed"),
        "description": info_0.get("description", ""),
        "instruction": info_0.get("instruction", ""),
        "alert": alert_dict,
        "xml_url": f"/api/v1/alerts/{alert.identifier}.xml",
        "receipts": [r.to_dict() for r in receipts],
    }


@router.get("/active")
def get_active_alerts() -> dict[str, Any]:
    """Retrieve all currently active public early warning CAP alerts."""
    active = GLOBAL_ALERT_LEDGER.get_active_alerts()
    return {
        "count": len(active),
        "alerts": [a.to_dict() for a in active],
        "disclaimer": "SIMULATED EXERCISE / PROVISIONAL DEMONSTRATION ONLY — NOT FOR OPERATIONAL USE (D-016 / B13)",
    }


@router.get("/history")
def get_alert_history(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    """Retrieve historical alert audit log."""
    history = GLOBAL_ALERT_LEDGER.get_history(limit=limit)
    return {
        "count": len(history),
        "records": history,
    }


@router.get("/feed.atom")
def get_georss_atom_feed() -> Response:
    """Syndication GeoRSS / Atom feed of active CAP alerts for NDMA ingestors."""
    active = GLOBAL_ALERT_LEDGER.get_active_alerts()
    now_iso = datetime.now(timezone.utc).isoformat()

    entries_xml = []
    for a in active:
        inf = a.info[0] if a.info else None
        title = inf.headline if inf else a.identifier
        summary = inf.description if inf else "Flood alert"
        entries_xml.append(f"""
    <entry>
      <title>{title}</title>
      <id>urn:uuid:{a.identifier}</id>
      <updated>{a.sent}</updated>
      <summary>{summary}</summary>
      <link rel="alternate" type="application/xml" href="/api/v1/alerts/{a.identifier}.xml"/>
    </entry>""")

    feed_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>UFNS Common Alerting Protocol (CAP v1.2) Early Warning Feed</title>
  <subtitle>National Centre for Medium Range Weather Forecasting (NCMRWF) - SIH26085 [EXERCISE FEED]</subtitle>
  <link href="http://localhost:8000/api/v1/alerts/feed.atom" rel="self"/>
  <updated>{now_iso}</updated>
  <id>urn:uuid:ufns-cap-feed-v1</id>
  {''.join(entries_xml)}
</feed>"""
    return Response(
        content=feed_xml.encode("utf-8"),
        media_type="application/atom+xml",
        headers={"Content-Type": "application/atom+xml; charset=utf-8"},
    )


@router.post("/dispatch/test")
def test_dispatch(req: TestDispatchRequest) -> dict[str, Any]:
    """Test multi-channel dispatch simulation on an existing alert."""
    alert = GLOBAL_ALERT_LEDGER.get_alert_by_id(req.alert_id)
    if alert is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ALERT_NOT_FOUND", "message": f"Alert {req.alert_id} not found"}},
        )
    dispatcher = AlertDispatcher()
    receipts = dispatcher.dispatch(alert, channels=req.channels)
    return {
        "dispatched": True,
        "alert_id": req.alert_id,
        "receipts": [r.to_dict() for r in receipts],
    }


@router.get("/{alert_id}.xml")
def get_alert_xml(alert_id: str) -> Response:
    """Serve OASIS CAP v1.2 XML bulletin."""
    clean_id = alert_id.replace(".xml", "")
    alert = GLOBAL_ALERT_LEDGER.get_alert_by_id(clean_id)
    if alert is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ALERT_NOT_FOUND", "message": f"Alert {alert_id} not found"}},
        )
    return Response(
        content=alert.to_xml().encode("utf-8"),
        media_type="application/xml",
        headers={
            "Content-Type": "application/xml; charset=utf-8",
            "Content-Disposition": f'inline; filename="{clean_id}.xml"',
        },
    )


@router.post("/{alert_id}/cancel")
def cancel_alert(alert_id: str, req: CancelAlertRequest) -> dict[str, Any]:
    """Cancel an active alert and issue a CAP Cancel notice."""
    clean_id = alert_id.replace(".json", "")
    cancel_alert_obj = GLOBAL_ALERT_LEDGER.cancel_alert(clean_id, reason=req.reason)
    if cancel_alert_obj is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ALERT_NOT_FOUND_OR_INACTIVE", "message": f"Active alert {alert_id} not found"}},
        )
    return {
        "cancelled": True,
        "original_alert_id": clean_id,
        "cancellation_alert": cancel_alert_obj.to_dict(),
        "xml_url": f"/api/v1/alerts/{cancel_alert_obj.identifier}.xml",
    }


@router.get("/{alert_id}")
def get_alert_by_id(alert_id: str) -> dict[str, Any]:
    """Retrieve CAP alert details by identifier."""
    # Strip optional .json suffix if provided
    clean_id = alert_id.replace(".json", "")
    alert = GLOBAL_ALERT_LEDGER.get_alert_by_id(clean_id)
    if alert is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ALERT_NOT_FOUND", "message": f"Alert {alert_id} not found"}},
        )
    return alert.to_dict()
