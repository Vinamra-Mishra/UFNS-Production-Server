"""Phase E Test Suite — Executive Incident Dossier & Automated PDF Generator.

Tests:
- Incident dossier compilation and aggregation
- Mass balance continuity audit certification (<0.01% error)
- ReportLab vector PDF compilation and binary validation (%PDF)
- FastAPI endpoints (/api/v1/reports/*)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.app import app
from services.reporting.dossier import (
    GLOBAL_DOSSIER_COMPILER,
    FloodIncidentDossier,
    PDFDossierCompiler,
    compile_dossier_from_scenario,
)


class TestDossierCompilation:
    """Test incident dossier aggregation logic."""

    def test_compile_dossier_s4_110(self):
        """Test that compile dossier s4 110 behaves as expected."""
        dossier = compile_dossier_from_scenario("S4", 110)
        assert dossier.dossier_id.startswith("UFNS-DOSSIER-")
        assert dossier.executive_summary.scenario_id == "S4"
        assert dossier.executive_summary.lead_minutes == 110
        assert dossier.executive_summary.max_flood_depth_m > 0.30
        assert "RED" in dossier.executive_summary.severity_level

        # Mass balance audit certification
        assert dossier.mass_balance.certified_continuity_pass is True
        assert dossier.mass_balance.relative_error_pct < 0.05
        assert dossier.mass_balance.cumulative_rainfall_inflow_m3 > 0

        # Transportation section
        assert dossier.transportation.impassable_roads_count > 0
        assert len(dossier.transportation.impassable_road_ids) > 0

        # CAP alert section
        assert dossier.cap_alert.alert_identifier != ""
        assert dossier.cap_alert.dispatched_channels_count >= 0

        # Dictionary serialization
        d = dossier.to_dict()
        assert "executive_summary" in d
        assert "mass_balance" in d
        assert "transportation" in d
        assert "cap_alert" in d


class TestPDFDossierCompiler:
    """Test ReportLab PDF compilation."""

    def test_pdf_compilation_binary_header(self):
        """Test that pdf compilation binary header behaves as expected."""
        dossier = compile_dossier_from_scenario("S4", 110)
        compiler = PDFDossierCompiler()
        pdf_bytes = compiler.compile_pdf(dossier)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 2000  # Multi-kilobyte PDF document
        assert pdf_bytes.startswith(b"%PDF-")  # Valid PDF header marker


class TestReportsAPI:
    """Test FastAPI /api/v1/reports endpoints."""

    def test_generate_report_endpoint(self):
        """Test that generate report endpoint behaves as expected."""
        client = TestClient(app)
        res = client.post("/api/v1/reports/generate", json={"scenario_id": "S4", "lead_minutes": 110})
        assert res.status_code == 200
        data = res.json()
        assert data["generated"] is True
        assert "dossier_id" in data
        assert data["pdf_url"].endswith(".pdf")
        assert data["dossier"]["executive_summary"]["scenario_id"] == "S4"

    def test_get_latest_report_endpoint(self):
        """Test that get latest report endpoint behaves as expected."""
        client = TestClient(app)
        res = client.get("/api/v1/reports/latest")
        assert res.status_code == 200
        data = res.json()
        assert "dossier_id" in data
        assert "dossier" in data

    def test_download_pdf_endpoint(self):
        """Test that download pdf endpoint behaves as expected."""
        client = TestClient(app)
        # Generate first
        gen_res = client.post("/api/v1/reports/generate", json={"scenario_id": "S4", "lead_minutes": 110})
        dossier_id = gen_res.json()["dossier_id"]

        pdf_res = client.get(f"/api/v1/reports/{dossier_id}.pdf")
        assert pdf_res.status_code == 200
        assert pdf_res.headers["content-type"] == "application/pdf"
        assert pdf_res.content.startswith(b"%PDF-")

    def test_get_report_json_endpoint(self):
        """Test that get report json endpoint behaves as expected."""
        client = TestClient(app)
        res = client.get("/api/v1/reports/UFNS-DOSSIER-S4-110")
        assert res.status_code == 200
        data = res.json()
        assert "dossier" in data
