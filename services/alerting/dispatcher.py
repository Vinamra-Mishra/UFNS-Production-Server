"""Multi-channel early warning dispatch and push pipeline simulation (Phase C).

Handles simulated broadcast queues for:
  - CAP-XML / GeoRSS syndication feeds (NDMA / SDMA)
  - Civic Webhooks (Municipal Corporation EOCs)
  - Compact SMS emergency alerts (<160 chars)
  - WhatsApp rich template bulletins with routing links
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional, Sequence

from services.alerting.cap import CAPAlert, CAPSeverity


class DispatchChannel(str, Enum):
    """Dispatchchannel schema and data model representation."""
    CAP_FEED = "CAP_FEED"
    WEBHOOK_PUSH = "WEBHOOK_PUSH"
    SMS_BROADCAST = "SMS_BROADCAST"
    WHATSAPP_BROADCAST = "WHATSAPP_BROADCAST"
    WEBSOCKET_STREAM = "WEBSOCKET_STREAM"


class DeliveryStatus(str, Enum):
    """Deliverystatus schema and data model representation."""
    DELIVERED = "DELIVERED"
    QUEUED = "QUEUED"
    FAILED = "FAILED"


@dataclass
class DispatchReceipt:
    """Audit receipt for an alert dispatch attempt across a specific channel."""

    receipt_id: str
    alert_id: str
    channel: DispatchChannel
    recipient_group: str
    status: DeliveryStatus
    sent_at: str                                                    # RFC 3339
    latency_ms: float
    payload_digest: str
    message_preview: str

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "receipt_id": self.receipt_id,
            "alert_id": self.alert_id,
            "channel": self.channel.value,
            "recipient_group": self.recipient_group,
            "status": self.status.value,
            "sent_at": self.sent_at,
            "latency_ms": round(self.latency_ms, 2),
            "payload_digest": self.payload_digest,
            "message_preview": self.message_preview,
        }


class AlertDispatcher:
    """Dispatches CAP alerts across configured civic push channels."""

    def __init__(self, webhook_secret: str = "ufns-demo-secret-key") -> None:
        """Execute   Init   operation and return result."""
        self.webhook_secret = webhook_secret

    def format_sms_message(self, alert: CAPAlert) -> str:
        """Format compact SMS bulletin within 160-character budget."""
        inf = alert.info[0] if alert.info else None
        sev = inf.severity.value.upper() if inf else "WARNING"
        depth = inf.parameters.get("MaxDepthMeters", "0.00") if inf else "0.00"
        area = inf.areas[0].area_desc if (inf and inf.areas) else "Pilot Sector"
        # Truncate area if long
        area_short = area[:24]

        msg = f"[{alert.status.value.upper()}] {sev} FLOOD: {area_short}. Depth ~{float(depth):.2f}m. Avoid blocked roads. Detour: http://localhost:8000"
        return msg[:160]

    def format_whatsapp_message(self, alert: CAPAlert) -> str:
        """Format WhatsApp rich text alert with actionable icons and detour advice."""
        inf = alert.info[0] if alert.info else None
        sev = inf.severity.value if inf else "Severe"
        badge = "[CRITICAL ALERT]" if inf and inf.severity in (CAPSeverity.EXTREME, CAPSeverity.SEVERE) else "[FLOOD ADVISORY]"
        headline = inf.headline if inf else "Flood Warning"
        desc = inf.description if inf else "Inundation expected."
        instr = inf.instruction if inf else "Avoid waterlogged roads."

        msg = (
            f"{badge} *[EXERCISE] {headline}*\n\n"
            f"*Summary:* {desc}\n\n"
            f"*Action Advice:* {instr}\n\n"
            f"*Live Dynamic Route:* http://localhost:8000\n"
            f"_Issued by NCMRWF / MoES UFNS Early Warning Engine_"
        )
        return msg

    def dispatch(
        self,
        alert: CAPAlert,
        channels: Sequence[DispatchChannel] = (
            DispatchChannel.CAP_FEED,
            DispatchChannel.WEBHOOK_PUSH,
            DispatchChannel.SMS_BROADCAST,
            DispatchChannel.WHATSAPP_BROADCAST,
        ),
    ) -> list[DispatchReceipt]:
        """Execute simulated multi-channel broadcast and return delivery receipts."""
        receipts: list[DispatchReceipt] = []
        now_iso = datetime.now(timezone.utc).isoformat()
        digest = alert.fingerprint()

        for ch in channels:
            t0 = time.perf_counter()

            if ch == DispatchChannel.SMS_BROADCAST:
                preview = self.format_sms_message(alert)
                group = "CIVIC_SUBSCRIBERS_WARD_84"
            elif ch == DispatchChannel.WHATSAPP_BROADCAST:
                preview = self.format_whatsapp_message(alert)
                group = "EMERGENCY_VOLUNTEERS_GROUP"
            elif ch == DispatchChannel.WEBHOOK_PUSH:
                webhook_payload = json.dumps(alert.to_dict())
                sig = hmac.new(self.webhook_secret.encode("utf-8"), webhook_payload.encode("utf-8"), hashlib.sha256).hexdigest()
                preview = f"POST /api/webhook/eoc-alert (HMAC: {sig[:8]}...)"
                group = "MUNICIPAL_EOC_DASHBOARD"
            elif ch == DispatchChannel.CAP_FEED:
                preview = f"CAP-XML Syndication Feed: <identifier>{alert.identifier}</identifier>"
                group = "NDMA_CAP_INGESTOR"
            else:
                preview = f"WebSocket Broadcast: event={alert.msg_type.value}"
                group = "DASHBOARD_LIVE_CLIENTS"

            elapsed_ms = (time.perf_counter() - t0) * 1000.0 + 1.2  # Add nominal network baseline

            receipt = DispatchReceipt(
                receipt_id=f"RCPT-{hashlib.sha256(f'{alert.identifier}-{ch.value}'.encode('utf-8')).hexdigest()[:12]}",
                alert_id=alert.identifier,
                channel=ch,
                recipient_group=group,
                status=DeliveryStatus.DELIVERED,
                sent_at=now_iso,
                latency_ms=elapsed_ms,
                payload_digest=digest,
                message_preview=preview,
            )
            receipts.append(receipt)

        return receipts
