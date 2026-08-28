"""OASIS Common Alerting Protocol (CAP v1.2 / ITU-T X.1303) data models and serializers (Phase C).

Compliant with NDMA India and international CAP v1.2 emergency alert schemas.
Strictly enforces operational safety: default status is EXERCISE / TEST / DRAFT.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape as xml_escape

CAP_XML_NAMESPACE = "urn:oasis:names:tc:emergency:cap:1.2"


class OperationalAuthorizationError(PermissionError):
    """Raised when attempting to issue an 'Actual' public alert on an unvalidated/exercise model."""


class CAPStatus(str, Enum):
    """Capstatus schema and data model representation."""
    EXERCISE = "Exercise"  # Standard demonstration / simulation mode
    TEST = "Test"          # Technical verification
    DRAFT = "Draft"        # Preliminary unreviewed bulletin
    SYSTEM = "System"      # Internal system message
    ACTUAL = "Actual"      # Operational public broadcast (STRICTLY RESTRICTED)


class CAPMsgType(str, Enum):
    """Capmsgtype schema and data model representation."""
    ALERT = "Alert"        # Initial emergency bulletin
    UPDATE = "Update"      # Severity escalation / boundary expansion
    CANCEL = "Cancel"      # Hazard receded / cancellation
    ACK = "Ack"            # Acknowledgment of receipt
    ERROR = "Error"        # Transmission or processing error


class CAPScope(str, Enum):
    """Capscope schema and data model representation."""
    PUBLIC = "Public"
    RESTRICTED = "Restricted"
    PRIVATE = "Private"


class CAPCategory(str, Enum):
    """Capcategory schema and data model representation."""
    GEO = "Geo"
    MET = "Met"
    SAFETY = "Safety"
    SECURITY = "Security"
    RESCUE = "Rescue"
    FIRE = "Fire"
    HEALTH = "Health"
    ENV = "Env"
    TRANSPORT = "Transport"
    INFRA = "Infra"
    CBRNE = "CBRNE"
    OTHER = "Other"


class CAPUrgency(str, Enum):
    """Capurgency schema and data model representation."""
    IMMEDIATE = "Immediate"  # Responsive action should be taken immediately
    EXPECTED = "Expected"    # Action within the next hour (nowcast lead)
    FUTURE = "Future"        # Action in subsequent hours
    PAST = "Past"
    UNKNOWN = "Unknown"


class CAPSeverity(str, Enum):
    """Capseverity schema and data model representation."""
    EXTREME = "Extreme"      # Extraordinary threat to life or property (>0.50m flood)
    SEVERE = "Severe"        # Significant threat to life or property (>0.30m flood)
    MODERATE = "Moderate"    # Possible threat (>0.15m flood / transit slowdown)
    MINOR = "Minor"          # Minimal threat (>0.05m advisory)
    UNKNOWN = "Unknown"


class CAPCertainty(str, Enum):
    """Capcertainty schema and data model representation."""
    OBSERVED = "Observed"    # Inundation confirmed by IoT depth gauges / sensors
    LIKELY = "Likely"        # High nowcast probability (>80%)
    POSSIBLE = "Possible"    # Moderate nowcast probability (50-80%)
    UNLIKELY = "Unlikely"
    UNKNOWN = "Unknown"


@dataclass(frozen=True)
class CAPArea:
    """Geographic area impacted by the alert."""

    area_desc: str
    polygon: tuple[tuple[float, float], ...] = field(default_factory=tuple)  # Lat, Lon tuples
    circle: Optional[str] = None                                            # "Lat,Lon RadiusKm"
    geocode: dict[str, str] = field(default_factory=dict)                   # {"Ward": "84", "Pincode": "700029"}

    def polygon_string(self) -> str:
        """Format polygon as whitespace-separated 'lat,lon' pairs per CAP 1.2 spec."""
        if not self.polygon:
            return ""
        return " ".join(f"{lat:.6f},{lon:.6f}" for lat, lon in self.polygon)

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "area_desc": self.area_desc,
            "polygon": [[round(lat, 6), round(lon, 6)] for lat, lon in self.polygon],
            "circle": self.circle,
            "geocode": self.geocode,
        }


@dataclass(frozen=True)
class CAPResource:
    """Associated digital resource (GeoJSON extent, evacuation map, bulletin PDF)."""

    resource_desc: str
    mime_type: str
    uri: Optional[str] = None
    size: Optional[int] = None
    digest: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "resource_desc": self.resource_desc,
            "mime_type": self.mime_type,
            "uri": self.uri,
            "size": self.size,
            "digest": self.digest,
        }


@dataclass
class CAPInfo:
    """Sub-container for alert event details in a specific language."""

    event: str                                                      # e.g. "Urban Flash Flood"
    urgency: CAPUrgency
    severity: CAPSeverity
    certainty: CAPCertainty
    headline: str
    description: str
    instruction: Optional[str] = None
    language: str = "en-IN"
    categories: list[CAPCategory] = field(default_factory=lambda: [CAPCategory.MET, CAPCategory.SAFETY, CAPCategory.TRANSPORT])
    event_codes: dict[str, str] = field(default_factory=lambda: {"NDMA": "FL", "SAME": "FFW"})
    effective: Optional[str] = None                                 # RFC3339
    onset: Optional[str] = None                                     # RFC3339
    expires: Optional[str] = None                                   # RFC3339
    sender_name: str = "National Centre for Medium Range Weather Forecasting (NCMRWF) / MoES"
    contact: str = "emergency-response@ncmrwf.gov.in"
    parameters: dict[str, str] = field(default_factory=dict)
    resources: list[CAPResource] = field(default_factory=list)
    areas: list[CAPArea] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "language": self.language,
            "categories": [c.value for c in self.categories],
            "event": self.event,
            "urgency": self.urgency.value,
            "severity": self.severity.value,
            "certainty": self.certainty.value,
            "event_codes": self.event_codes,
            "effective": self.effective,
            "onset": self.onset,
            "expires": self.expires,
            "sender_name": self.sender_name,
            "headline": self.headline,
            "description": self.description,
            "instruction": self.instruction,
            "contact": self.contact,
            "parameters": self.parameters,
            "resources": [r.to_dict() for r in self.resources],
            "areas": [a.to_dict() for a in self.areas],
        }


@dataclass
class CAPAlert:
    """OASIS CAP v1.2 / ITU-T X.1303 Root Alert Message."""

    identifier: str
    sender: str
    sent: str                                                      # RFC 3339 UTC timestamp
    status: CAPStatus
    msg_type: CAPMsgType
    scope: CAPScope = CAPScope.PUBLIC
    source: str = "UFNS-NOWCAST-ENGINE-V1"
    restriction: Optional[str] = None
    addresses: Optional[str] = None
    codes: list[str] = field(default_factory=lambda: ["IPAWS-CAP-1.2", "NDMA-CAP-1.2"])
    note: Optional[str] = None
    references: Optional[str] = None
    incidents: Optional[str] = None
    info: list[CAPInfo] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Execute   Post Init   operation and return result."""
        # Enforce strict civic safety governance: never allow Actual alerts from exercise/pilot models
        if self.status == CAPStatus.ACTUAL:
            raise OperationalAuthorizationError(
                "CANNOT ISSUE 'Actual' STATUS ALERT: The system operates under D-016 provisional hyetographs, "
                "B13 demonstration passability thresholds, and unmapped underground drainage geometries. "
                "Alerts must be issued with status=Exercise, Test, or Draft."
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to standard CAP-JSON representation."""
        return {
            "identifier": self.identifier,
            "sender": self.sender,
            "sent": self.sent,
            "status": self.status.value,
            "msg_type": self.msg_type.value,
            "scope": self.scope.value,
            "source": self.source,
            "restriction": self.restriction,
            "addresses": self.addresses,
            "codes": self.codes,
            "note": self.note,
            "references": self.references,
            "incidents": self.incidents,
            "info": [inf.to_dict() for inf in self.info],
            "fingerprint": self.fingerprint(),
        }

    def fingerprint(self) -> str:
        """Deterministic SHA-256 fingerprint of the alert content."""
        data_str = json.dumps(
            {
                "id": self.identifier,
                "sent": self.sent,
                "status": self.status.value,
                "msg_type": self.msg_type.value,
                "info": [inf.to_dict() for inf in self.info],
            },
            sort_keys=True,
        )
        return hashlib.sha256(data_str.encode("utf-8")).hexdigest()[:16]

    def to_xml(self) -> str:
        """Serialize to OASIS CAP v1.2 compliant XML string."""
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<alert xmlns="{CAP_XML_NAMESPACE}">',
            f'  <identifier>{xml_escape(self.identifier)}</identifier>',
            f'  <sender>{xml_escape(self.sender)}</sender>',
            f'  <sent>{xml_escape(self.sent)}</sent>',
            f'  <status>{xml_escape(self.status.value)}</status>',
            f'  <msgType>{xml_escape(self.msg_type.value)}</msgType>',
            f'  <scope>{xml_escape(self.scope.value)}</scope>',
            f'  <source>{xml_escape(self.source)}</source>',
        ]

        for code in self.codes:
            lines.append(f'  <code>{xml_escape(code)}</code>')

        if self.note:
            lines.append(f'  <note>{xml_escape(self.note)}</note>')
        if self.references:
            lines.append(f'  <references>{xml_escape(self.references)}</references>')
        if self.incidents:
            lines.append(f'  <incidents>{xml_escape(self.incidents)}</incidents>')

        for inf in self.info:
            lines.append('  <info>')
            lines.append(f'    <language>{xml_escape(inf.language)}</language>')
            for cat in inf.categories:
                lines.append(f'    <category>{xml_escape(cat.value)}</category>')
            lines.append(f'    <event>{xml_escape(inf.event)}</event>')
            lines.append(f'    <urgency>{xml_escape(inf.urgency.value)}</urgency>')
            lines.append(f'    <severity>{xml_escape(inf.severity.value)}</severity>')
            lines.append(f'    <certainty>{xml_escape(inf.certainty.value)}</certainty>')

            for name, val in inf.event_codes.items():
                lines.append('    <eventCode>')
                lines.append(f'      <valueName>{xml_escape(name)}</valueName>')
                lines.append(f'      <value>{xml_escape(val)}</value>')
                lines.append('    </eventCode>')

            if inf.effective:
                lines.append(f'    <effective>{xml_escape(inf.effective)}</effective>')
            if inf.onset:
                lines.append(f'    <onset>{xml_escape(inf.onset)}</onset>')
            if inf.expires:
                lines.append(f'    <expires>{xml_escape(inf.expires)}</expires>')

            lines.append(f'    <senderName>{xml_escape(inf.sender_name)}</senderName>')
            lines.append(f'    <headline>{xml_escape(inf.headline)}</headline>')
            lines.append(f'    <description>{xml_escape(inf.description)}</description>')
            if inf.instruction:
                lines.append(f'    <instruction>{xml_escape(inf.instruction)}</instruction>')
            if inf.contact:
                lines.append(f'    <contact>{xml_escape(inf.contact)}</contact>')

            for p_name, p_val in inf.parameters.items():
                lines.append('    <parameter>')
                lines.append(f'      <valueName>{xml_escape(p_name)}</valueName>')
                lines.append(f'      <value>{xml_escape(p_val)}</value>')
                lines.append('    </parameter>')

            for res in inf.resources:
                lines.append('    <resource>')
                lines.append(f'      <resourceDesc>{xml_escape(res.resource_desc)}</resourceDesc>')
                lines.append(f'      <mimeType>{xml_escape(res.mime_type)}</mimeType>')
                if res.uri:
                    lines.append(f'      <uri>{xml_escape(res.uri)}</uri>')
                if res.size is not None:
                    lines.append(f'      <size>{res.size}</size>')
                if res.digest:
                    lines.append(f'      <digest>{xml_escape(res.digest)}</digest>')
                lines.append('    </resource>')

            for area in inf.areas:
                lines.append('    <area>')
                lines.append(f'      <areaDesc>{xml_escape(area.area_desc)}</areaDesc>')
                poly_str = area.polygon_string()
                if poly_str:
                    lines.append(f'      <polygon>{poly_str}</polygon>')
                if area.circle:
                    lines.append(f'      <circle>{xml_escape(area.circle)}</circle>')
                for g_name, g_val in area.geocode.items():
                    lines.append('      <geocode>')
                    lines.append(f'        <valueName>{xml_escape(g_name)}</valueName>')
                    lines.append(f'        <value>{xml_escape(g_val)}</value>')
                    lines.append('      </geocode>')
                lines.append('    </area>')

            lines.append('  </info>')

        lines.append('</alert>')
        return "\n".join(lines)
