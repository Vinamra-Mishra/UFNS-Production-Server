"""Alert audit ledger, active message index, and lifecycle management (Phase C).

Maintains a permanent, append-only registry of all issued, updated, and cancelled
CAP alerts, along with delivery audit receipts.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.alerting.cap import CAPAlert, CAPMsgType, CAPStatus
from services.alerting.dispatcher import DispatchReceipt


@dataclass
class AlertAuditRecord:
    """Full audit ledger entry for an issued CAP alert and its dispatch receipts."""

    record_id: str
    alert: CAPAlert
    receipts: list[DispatchReceipt]
    scenario_id: str
    lead_minutes: int
    created_at: str
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "record_id": self.record_id,
            "alert": self.alert.to_dict(),
            "receipts": [r.to_dict() for r in self.receipts],
            "scenario_id": self.scenario_id,
            "lead_minutes": self.lead_minutes,
            "created_at": self.created_at,
            "active": self.active,
        }


class AlertLedger:
    """In-memory and file-backed audit registry for early warning alerts."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        """Execute   Init   operation and return result."""
        self.storage_path = storage_path
        self._records: list[AlertAuditRecord] = []
        self._by_id: dict[str, AlertAuditRecord] = {}

    def record_alert(
        self,
        alert: CAPAlert,
        receipts: list[DispatchReceipt],
        scenario_id: str = "S4",
        lead_minutes: int = 0,
    ) -> AlertAuditRecord:
        """Register a newly issued CAP alert and its broadcast receipts."""
        rec_id = f"REC-{alert.identifier}"
        rec = AlertAuditRecord(
            record_id=rec_id,
            alert=alert,
            receipts=receipts,
            scenario_id=scenario_id,
            lead_minutes=lead_minutes,
            created_at=datetime.now(timezone.utc).isoformat(),
            active=(alert.msg_type != CAPMsgType.CANCEL),
        )
        self._records.append(rec)
        self._by_id[alert.identifier] = rec
        self._persist()
        return rec

    def get_alert_by_id(self, alert_id: str) -> Optional[CAPAlert]:
        """Retrieve alert by identifier."""
        rec = self._by_id.get(alert_id)
        return rec.alert if rec else None

    def get_active_alerts(self) -> list[CAPAlert]:
        """Return list of currently active (non-cancelled) alerts."""
        return [r.alert for r in self._records if r.active]

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return chronological audit records (newest first)."""
        return [r.to_dict() for r in reversed(self._records[-limit:])]

    def cancel_alert(self, alert_id: str, reason: str = "Flood waters receded") -> Optional[CAPAlert]:
        """Mark an alert as cancelled and generate a corresponding CANCEL CAP bulletin."""
        rec = self._by_id.get(alert_id)
        if not rec or not rec.active:
            return None

        rec.active = False
        orig = rec.alert
        now_iso = datetime.now(timezone.utc).isoformat()

        # Build Cancel message referencing the original
        cancel_info = copy.deepcopy(orig.info)
        for inf in cancel_info:
            inf.headline = f"[{orig.status.value.upper()} CANCELLED] {inf.headline}"
            inf.description = f"ALERT CANCELLED: {reason}. {inf.description}"
            inf.instruction = "Normal traffic and activities may resume. Monitor local authorities for updates."

        cancel_alert = CAPAlert(
            identifier=f"{orig.identifier}-CANCEL",
            sender=orig.sender,
            sent=now_iso,
            status=orig.status,
            msg_type=CAPMsgType.CANCEL,
            scope=orig.scope,
            references=f"{orig.sender},{orig.identifier},{orig.sent}",
            note=f"Cancellation notice for {orig.identifier}",
            info=cancel_info,
        )

        cancel_rec = AlertAuditRecord(
            record_id=f"REC-{cancel_alert.identifier}",
            alert=cancel_alert,
            receipts=[],
            scenario_id=rec.scenario_id,
            lead_minutes=rec.lead_minutes,
            created_at=now_iso,
            active=False,
        )
        self._records.append(cancel_rec)
        self._by_id[cancel_alert.identifier] = cancel_rec
        self._persist()
        return cancel_alert

    def clear(self) -> None:
        """Clear all records (for testing)."""
        self._records.clear()
        self._by_id.clear()

    def _persist(self) -> None:
        """Execute  Persist operation and return result."""
        if self.storage_path:
            try:
                self.storage_path.parent.mkdir(parents=True, exist_ok=True)
                data = [r.to_dict() for r in self._records]
                self.storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception:
                pass


GLOBAL_ALERT_LEDGER = AlertLedger()
