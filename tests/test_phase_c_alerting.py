"""Unit and integration test suite for Phase C: Early Warning & CAP v1.2 Alerts Engine."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import pytest
from fastapi.testclient import TestClient

from apps.api.app import app
from services.alerting.cap import (
    CAPAlert,
    CAPArea,
    CAPCategory,
    CAPCertainty,
    CAPInfo,
    CAPMsgType,
    CAPScope,
    CAPSeverity,
    CAPStatus,
    CAPUrgency,
    OperationalAuthorizationError,
)
from services.alerting.dispatcher import (
    AlertDispatcher,
    DeliveryStatus,
    DispatchChannel,
)
from services.alerting.ledger import AlertLedger, GLOBAL_ALERT_LEDGER
from services.alerting.screening import AlertThresholds, EarlyWarningScreener
import numpy as np


@pytest.fixture(autouse=True)
def clean_alert_ledger():
    """Reset the global alert ledger before each test."""
    GLOBAL_ALERT_LEDGER.clear()
    yield
    GLOBAL_ALERT_LEDGER.clear()


class TestCAPSchemaAndSerialization:
    """Verify OASIS CAP v1.2 / ITU-T X.1303 data model and XML/JSON serialization."""

    def test_cap_xml_generation_valid(self):
        """Test that cap xml generation valid behaves as expected."""
        info = CAPInfo(
            event="Urban Flash Flood",
            urgency=CAPUrgency.EXPECTED,
            severity=CAPSeverity.SEVERE,
            certainty=CAPCertainty.LIKELY,
            headline="[EXERCISE] Severe Flash Flood Warning for Kolkata Ward 84",
            description="Coupled hydraulic nowcast predicts 0.42m depth on Rashbehari Avenue & SP Mukherjee Rd.",
            instruction="Avoid flooded underpasses. Reroute via EM Bypass.",
            areas=[
                CAPArea(
                    area_desc="Kolkata Ward 84",
                    polygon=((22.5100, 88.3500), (22.5100, 88.3600), (22.5000, 88.3600), (22.5000, 88.3500), (22.5100, 88.3500)),
                    geocode={"Ward": "84"},
                )
            ],
        )

        alert = CAPAlert(
            identifier="UFNS-CAP-20260825-S4-001",
            sender="ncmrwf-ufns@gov.in",
            sent="2026-08-25T16:00:00+00:00",
            status=CAPStatus.EXERCISE,
            msg_type=CAPMsgType.ALERT,
            scope=CAPScope.PUBLIC,
            note="Simulation only",
            info=[info],
        )

        xml_str = alert.to_xml()
        assert xml_str.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        assert '<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">' in xml_str
        assert "<identifier>UFNS-CAP-20260825-S4-001</identifier>" in xml_str
        assert "<status>Exercise</status>" in xml_str
        assert "<severity>Severe</severity>" in xml_str
        assert "<polygon>22.510000,88.350000 22.510000,88.360000" in xml_str

        # Validate that generated XML is well-formed ElementTree XML
        root = ET.fromstring(xml_str)
        assert root.tag == "{urn:oasis:names:tc:emergency:cap:1.2}alert"

    def test_special_character_escaping(self):
        """Test that special character escaping behaves as expected."""
        info = CAPInfo(
            event="Flood & Heavy Storm <Special> 'Test'",
            urgency=CAPUrgency.IMMEDIATE,
            severity=CAPSeverity.EXTREME,
            certainty=CAPCertainty.OBSERVED,
            headline="Warning: Inundation > 0.50m & Power Risk",
            description="Water depth > 0.5m; check 'Safe Routes' & emergency contacts.",
        )
        alert = CAPAlert(
            identifier="UFNS-CAP-ESC-01",
            sender="ufns@gov.in",
            sent="2026-08-25T16:00:00+00:00",
            status=CAPStatus.TEST,
            msg_type=CAPMsgType.ALERT,
            info=[info],
        )
        xml_str = alert.to_xml()
        assert "&amp;" in xml_str
        assert "&gt;" in xml_str
        assert "&lt;" in xml_str
        # Must parse without XML syntax errors
        root = ET.fromstring(xml_str)
        assert root is not None

    def test_strict_governance_prohibits_actual_status(self):
        """Verifies that creating an 'Actual' alert raises OperationalAuthorizationError."""
        with pytest.raises(OperationalAuthorizationError, match="CANNOT ISSUE 'Actual' STATUS ALERT"):
            CAPAlert(
                identifier="UFNS-ACTUAL-FORBIDDEN",
                sender="ufns@gov.in",
                sent="2026-08-25T16:00:00+00:00",
                status=CAPStatus.ACTUAL,
                msg_type=CAPMsgType.ALERT,
            )

    def test_json_dict_and_fingerprint(self):
        """Test that json dict and fingerprint behaves as expected."""
        alert = CAPAlert(
            identifier="UFNS-JSON-001",
            sender="ufns@gov.in",
            sent="2026-08-25T16:00:00+00:00",
            status=CAPStatus.DRAFT,
            msg_type=CAPMsgType.ALERT,
            info=[
                CAPInfo(
                    event="Rainfall Screening",
                    urgency=CAPUrgency.FUTURE,
                    severity=CAPSeverity.MINOR,
                    certainty=CAPCertainty.POSSIBLE,
                    headline="Minor Advisory",
                    description="Ponding expected",
                )
            ],
        )
        d = alert.to_dict()
        assert d["identifier"] == "UFNS-JSON-001"
        assert d["status"] == "Draft"
        assert len(d["fingerprint"]) == 16


class TestEarlyWarningScreening:
    """Test automated threshold evaluation on 2D depth grids and road vectors."""

    def test_screening_dry_returns_none(self):
        """Test that screening dry returns none behaves as expected."""
        screener = EarlyWarningScreener()
        dry_grid = np.zeros((7, 7), dtype=np.float64)
        road_impacts = [{"road_id": "R-1", "classification": "DRY"}]

        alert = screener.screen_simulation_frame(
            depth_grid=dry_grid,
            road_impacts=road_impacts,
            lead_minutes=0,
            scenario_id="S1",
        )
        assert alert is None

    def test_screening_moderate_amber_alert(self):
        """Test that screening moderate amber alert behaves as expected."""
        screener = EarlyWarningScreener()
        grid = np.zeros((7, 7), dtype=np.float64)
        grid[3, 3] = 0.22  # Moderate depth
        road_impacts = [
            {"road_id": "R-1", "classification": "CAUTION"},
            {"road_id": "R-2", "classification": "CAUTION"},
        ]

        alert = screener.screen_simulation_frame(
            depth_grid=grid,
            road_impacts=road_impacts,
            lead_minutes=30,
            scenario_id="S3",
            status=CAPStatus.EXERCISE,
        )
        assert alert is not None
        assert alert.status == CAPStatus.EXERCISE
        assert alert.info[0].severity == CAPSeverity.MODERATE
        assert alert.info[0].parameters["AlertColor"] == "AMBER"
        assert float(alert.info[0].parameters["MaxDepthMeters"]) == pytest.approx(0.22, abs=1e-2)

    def test_screening_extreme_red_alert_with_impassable_roads(self):
        """Test that screening extreme red alert with impassable roads behaves as expected."""
        screener = EarlyWarningScreener()
        grid = np.zeros((7, 7), dtype=np.float64)
        grid[3, 3] = 0.65  # Extreme depth
        grid[3, 4] = 0.55
        road_impacts = [
            {"road_id": "ROAD-NORTH", "classification": "IMPASSABLE"},
            {"road_id": "ROAD-SOUTH", "classification": "IMPASSABLE"},
        ]

        alert = screener.screen_simulation_frame(
            depth_grid=grid,
            road_impacts=road_impacts,
            lead_minutes=60,
            scenario_id="S4",
            status=CAPStatus.EXERCISE,
        )
        assert alert is not None
        assert alert.info[0].severity == CAPSeverity.EXTREME
        assert alert.info[0].parameters["AlertColor"] == "RED"
        assert int(alert.info[0].parameters["ImpassableRoadCount"]) == 2
        assert "ROAD-NORTH" in alert.info[0].description
        assert len(alert.info[0].areas[0].polygon) == 5  # Closed 4-point bounding box


class TestAlertDispatcher:
    """Test multi-channel dispatch simulation and formatting constraints."""

    def test_sms_formatting_within_160_characters(self):
        """Test that sms formatting within 160 characters behaves as expected."""
        dispatcher = AlertDispatcher()
        info = CAPInfo(
            event="Severe Flash Flood",
            urgency=CAPUrgency.IMMEDIATE,
            severity=CAPSeverity.EXTREME,
            certainty=CAPCertainty.OBSERVED,
            headline="[EXERCISE] Extreme Flood in Kolkata Ward 84 Rashbehari",
            description="Water depth 0.65m on key roads.",
            parameters={"MaxDepthMeters": "0.65"},
            areas=[CAPArea(area_desc="Kolkata Ward 84 Sector A-B-C")],
        )
        alert = CAPAlert(
            identifier="UFNS-SMS-TEST",
            sender="ufns@gov.in",
            sent="2026-08-25T16:00:00+00:00",
            status=CAPStatus.EXERCISE,
            msg_type=CAPMsgType.ALERT,
            info=[info],
        )

        sms = dispatcher.format_sms_message(alert)
        assert len(sms) <= 160
        assert "[EXERCISE] EXTREME FLOOD" in sms
        assert "0.65m" in sms

    def test_whatsapp_formatting(self):
        """Test that whatsapp formatting behaves as expected."""
        dispatcher = AlertDispatcher()
        info = CAPInfo(
            event="Urban Flood",
            urgency=CAPUrgency.EXPECTED,
            severity=CAPSeverity.SEVERE,
            certainty=CAPCertainty.LIKELY,
            headline="Severe Flood Warning",
            description="Inundation expected along Central Avenue.",
            instruction="Take alternative route via Ring Road.",
        )
        alert = CAPAlert(
            identifier="UFNS-WA-TEST",
            sender="ufns@gov.in",
            sent="2026-08-25T16:00:00+00:00",
            status=CAPStatus.EXERCISE,
            msg_type=CAPMsgType.ALERT,
            info=[info],
        )
        wa = dispatcher.format_whatsapp_message(alert)
        assert "[CRITICAL ALERT]" in wa
        assert "Ring Road" in wa
        assert "http://localhost:8000" in wa

    def test_dispatch_channels_and_latency_budget(self):
        """Test that dispatch channels and latency budget behaves as expected."""
        dispatcher = AlertDispatcher()
        info = CAPInfo(
            event="Urban Flood",
            urgency=CAPUrgency.IMMEDIATE,
            severity=CAPSeverity.SEVERE,
            certainty=CAPCertainty.OBSERVED,
            headline="Flood Alert",
            description="Flood warning",
        )
        alert = CAPAlert(
            identifier="UFNS-DISP-01",
            sender="ufns@gov.in",
            sent="2026-08-25T16:00:00+00:00",
            status=CAPStatus.EXERCISE,
            msg_type=CAPMsgType.ALERT,
            info=[info],
        )

        receipts = dispatcher.dispatch(alert)
        assert len(receipts) == 4
        channels = [r.channel for r in receipts]
        assert DispatchChannel.CAP_FEED in channels
        assert DispatchChannel.WEBHOOK_PUSH in channels
        assert DispatchChannel.SMS_BROADCAST in channels
        assert DispatchChannel.WHATSAPP_BROADCAST in channels

        for r in receipts:
            assert r.status == DeliveryStatus.DELIVERED
            assert r.latency_ms < 500.0  # Ultra-low-latency processing constraint


class TestAlertLedger:
    """Test append-only alert ledger, queries, and cancellation lifecycle."""

    def test_record_and_query_active(self):
        """Test that record and query active behaves as expected."""
        ledger = AlertLedger()
        info = CAPInfo(
            event="Flood Alert",
            urgency=CAPUrgency.IMMEDIATE,
            severity=CAPSeverity.MODERATE,
            certainty=CAPCertainty.LIKELY,
            headline="Amber Watch",
            description="Moderate ponding",
        )
        alert = CAPAlert(
            identifier="UFNS-LEDGER-01",
            sender="ufns@gov.in",
            sent="2026-08-25T16:00:00+00:00",
            status=CAPStatus.EXERCISE,
            msg_type=CAPMsgType.ALERT,
            info=[info],
        )

        ledger.record_alert(alert, receipts=[], scenario_id="S3", lead_minutes=15)
        active = ledger.get_active_alerts()
        assert len(active) == 1
        assert active[0].identifier == "UFNS-LEDGER-01"

    def test_cancel_alert_lifecycle(self):
        """Test that cancel alert lifecycle behaves as expected."""
        ledger = AlertLedger()
        info = CAPInfo(
            event="Flood Alert",
            urgency=CAPUrgency.IMMEDIATE,
            severity=CAPSeverity.SEVERE,
            certainty=CAPCertainty.OBSERVED,
            headline="Orange Warning",
            description="Water on streets",
        )
        alert = CAPAlert(
            identifier="UFNS-TO-CANCEL",
            sender="ufns@gov.in",
            sent="2026-08-25T16:00:00+00:00",
            status=CAPStatus.EXERCISE,
            msg_type=CAPMsgType.ALERT,
            info=[info],
        )

        ledger.record_alert(alert, receipts=[])
        assert len(ledger.get_active_alerts()) == 1

        cancel_alert = ledger.cancel_alert("UFNS-TO-CANCEL", reason="Water pumped out")
        assert cancel_alert is not None
        assert cancel_alert.msg_type == CAPMsgType.CANCEL
        assert "CANCELLED" in cancel_alert.info[0].headline
        assert len(ledger.get_active_alerts()) == 0


class TestAlertsAPI:
    """Test FastAPI endpoints for Phase C."""

    client = TestClient(app)

    def test_evaluate_scenario_s4_generates_alert(self):
        """Test that evaluate scenario s4 generates alert behaves as expected."""
        res = self.client.post(
            "/api/v1/alerts/evaluate",
            json={
                "scenario_id": "S4",
                "lead_minutes": 110,
                "status": "Exercise",
                "dispatch": True,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["alert_generated"] is True
        assert "alert" in data
        assert data["alert"]["status"] == "Exercise"
        assert len(data["receipts"]) == 4

        alert_id = data["alert"]["identifier"]

        # Fetch XML endpoint
        xml_res = self.client.get(f"/api/v1/alerts/{alert_id}.xml")
        assert xml_res.status_code == 200
        assert "application/xml" in xml_res.headers["content-type"]
        assert "<identifier>" in xml_res.text

        # Fetch JSON endpoint
        json_res = self.client.get(f"/api/v1/alerts/{alert_id}")
        assert json_res.status_code == 200
        assert json_res.json()["identifier"] == alert_id

    def test_evaluate_actual_status_returns_403_forbidden(self):
        """Test that evaluate actual status returns 403 forbidden behaves as expected."""
        res = self.client.post(
            "/api/v1/alerts/evaluate",
            json={
                "scenario_id": "S4",
                "lead_minutes": 0,
                "status": "Actual",
            },
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "OPERATIONAL_AUTHORIZATION_REQUIRED"

    def test_active_alerts_and_georss_feed(self):
        """Test that active alerts and georss feed behaves as expected."""
        # 1. Trigger an alert first
        self.client.post(
            "/api/v1/alerts/evaluate",
            json={"scenario_id": "S4", "lead_minutes": 90, "status": "Exercise"},
        )

        # 2. Query active
        active_res = self.client.get("/api/v1/alerts/active")
        assert active_res.status_code == 200
        assert active_res.json()["count"] >= 1

        # 3. Query Atom feed
        feed_res = self.client.get("/api/v1/alerts/feed.atom")
        assert feed_res.status_code == 200
        assert "application/atom+xml" in feed_res.headers["content-type"]
        assert "<feed xmlns=" in feed_res.text

    def test_cancel_alert_api(self):
        """Test that cancel alert api behaves as expected."""
        eval_res = self.client.post(
            "/api/v1/alerts/evaluate",
            json={"scenario_id": "S4", "lead_minutes": 50, "status": "Exercise"},
        )
        alert_id = eval_res.json()["alert"]["identifier"]

        cancel_res = self.client.post(
            f"/api/v1/alerts/{alert_id}/cancel",
            json={"reason": "Drainage pumps cleared stormwater"},
        )
        assert cancel_res.status_code == 200
        assert cancel_res.json()["cancelled"] is True

    def test_alert_not_found_404(self):
        """Test that alert not found 404 behaves as expected."""
        res = self.client.get("/api/v1/alerts/NON-EXISTENT-ALERT.xml")
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "ALERT_NOT_FOUND"
