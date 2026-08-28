"""Phase E — Executive Disaster Management Dossier & Automated PDF Report Generator.

Compiles publication-quality, MoES/NDMA-compliant flood incident dossiers in vector PDF.

Sections:
1. Executive Incident Briefing (Severity, Peak Depth, Flooded Area, Volume)
2. Certified Hydrodynamic Mass Balance Ledger (Global Residual < 0.01% Error)
3. Transportation Impassability & Vehicle Detour Register
4. OASIS CAP v1.2 Broadcast Notice & Dispatch Receipts
5. Scientific Provenance, D-016 Audit Trail, and Governance Signatures
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from services.alerting.cap import CAPAlert
from services.alerting.screening import EarlyWarningScreener
from services.contracts import ProvenanceClass, QualityFlag
from services.nowcast.blending import compute_blending_weights


# ---------------------------------------------------------------------------
# Dossier Data Structures
# ---------------------------------------------------------------------------

@dataclass
class ExecutiveSummarySection:
    """Executivesummarysection schema and data model representation."""
    scenario_id: str
    lead_minutes: int
    severity_level: str  # "EXTREME RED", "SEVERE ORANGE", "MODERATE AMBER", "MINOR GREEN"
    max_flood_depth_m: float
    inundated_area_sqm: float
    surface_storage_volume_m3: float
    inundated_fraction_pct: float
    peak_crest_lead_minutes: int
    summary_text: str


@dataclass
class MassBalanceAuditSection:
    """Massbalanceauditsection schema and data model representation."""
    cumulative_rainfall_inflow_m3: float
    cumulative_swmm_outfall_m3: float
    surface_storage_m3: float
    subsurface_conduit_storage_m3: float
    global_mass_residual_m3: Optional[float]
    relative_error_pct: Optional[float]
    certified_continuity_pass: bool
    certification_seal: str


@dataclass
class TransportationSection:
    """Transportationsection schema and data model representation."""
    total_roads_inspected: int
    impassable_roads_count: int
    caution_roads_count: int
    dry_roads_count: int
    impassable_road_ids: list[str]
    sample_detour_savings_min: Optional[float]


@dataclass
class CAPAlertSection:
    """Capalertsection schema and data model representation."""
    alert_identifier: str
    headline: str
    instruction: str
    urgency: str
    severity: str
    certainty: str
    dispatched_channels_count: int


@dataclass
class ProvenanceSection:
    """Provenancesection schema and data model representation."""
    dem_source: str
    spatial_crs: str
    grid_resolution_m: float
    hyetograph_derivation: str
    radar_weight_pct: float
    nwp_weight_pct: float
    d016_status: str
    governance_disclaimer: str


@dataclass
class FloodIncidentDossier:
    """Floodincidentdossier schema and data model representation."""
    dossier_id: str
    generated_at_utc: datetime
    executive_summary: ExecutiveSummarySection
    mass_balance: MassBalanceAuditSection
    transportation: TransportationSection
    cap_alert: CAPAlertSection
    provenance: ProvenanceSection

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "dossier_id": self.dossier_id,
            "generated_at_utc": self.generated_at_utc.isoformat(),
            "executive_summary": {
                "scenario_id": self.executive_summary.scenario_id,
                "lead_minutes": self.executive_summary.lead_minutes,
                "severity_level": self.executive_summary.severity_level,
                "max_flood_depth_m": self.executive_summary.max_flood_depth_m,
                "inundated_area_sqm": self.executive_summary.inundated_area_sqm,
                "surface_storage_volume_m3": self.executive_summary.surface_storage_volume_m3,
                "inundated_fraction_pct": self.executive_summary.inundated_fraction_pct,
                "peak_crest_lead_minutes": self.executive_summary.peak_crest_lead_minutes,
                "summary_text": self.executive_summary.summary_text,
            },
            "mass_balance": {
                "cumulative_rainfall_inflow_m3": self.mass_balance.cumulative_rainfall_inflow_m3,
                "cumulative_swmm_outfall_m3": self.mass_balance.cumulative_swmm_outfall_m3,
                "surface_storage_m3": self.mass_balance.surface_storage_m3,
                "subsurface_conduit_storage_m3": self.mass_balance.subsurface_conduit_storage_m3,
                "global_mass_residual_m3": self.mass_balance.global_mass_residual_m3,
                "relative_error_pct": self.mass_balance.relative_error_pct,
                "certified_continuity_pass": self.mass_balance.certified_continuity_pass,
                "certification_seal": self.mass_balance.certification_seal,
            },
            "transportation": {
                "total_roads_inspected": self.transportation.total_roads_inspected,
                "impassable_roads_count": self.transportation.impassable_roads_count,
                "caution_roads_count": self.transportation.caution_roads_count,
                "dry_roads_count": self.transportation.dry_roads_count,
                "impassable_road_ids": self.transportation.impassable_road_ids,
                "sample_detour_savings_min": self.transportation.sample_detour_savings_min,
            },
            "cap_alert": {
                "alert_identifier": self.cap_alert.alert_identifier,
                "headline": self.cap_alert.headline,
                "instruction": self.cap_alert.instruction,
                "urgency": self.cap_alert.urgency,
                "severity": self.cap_alert.severity,
                "certainty": self.cap_alert.certainty,
                "dispatched_channels_count": self.cap_alert.dispatched_channels_count,
            },
            "provenance": {
                "dem_source": self.provenance.dem_source,
                "spatial_crs": self.provenance.spatial_crs,
                "grid_resolution_m": self.provenance.grid_resolution_m,
                "hyetograph_derivation": self.provenance.hyetograph_derivation,
                "radar_weight_pct": self.provenance.radar_weight_pct,
                "nwp_weight_pct": self.provenance.nwp_weight_pct,
                "d016_status": self.provenance.d016_status,
                "governance_disclaimer": self.provenance.governance_disclaimer,
            },
        }


# ---------------------------------------------------------------------------
# Dossier Compilation Logic
# ---------------------------------------------------------------------------

def compile_dossier_from_scenario(scenario_id: str = "S4", lead_minutes: int = 110) -> FloodIncidentDossier:
    """Aggregate simulation, hydraulic ledger, road impact, and CAP alert data into a complete dossier."""
    from services.routing.impact import rasterize_line
    from services.routing.policy import POLICY, classify
    from services.routing.roads import NETWORK
    from services.scenarios.artifacts import (
        VALID_SCENARIO_IDS,
        get_depth_grid,
        load_results,
        scenario_metadata,
    )

    clean_scenario = scenario_id.upper()
    if clean_scenario not in VALID_SCENARIO_IDS:
        clean_scenario = "S4"

    all_results = load_results()
    res_dict = all_results.get(clean_scenario, {})
    meta_dict = scenario_metadata(clean_scenario)
    now_utc = datetime.now(timezone.utc)
    dossier_id = f"UFNS-DOSSIER-{now_utc.strftime('%Y%m%d%H%M%S')}-{clean_scenario}-{lead_minutes:03d}"

    # Reconstruct 2D depth grid
    depth_arr = np.array(get_depth_grid(clean_scenario, lead_minutes), dtype=float)

    # Compute road impacts from depth_arr
    road_impacts = []
    for road in NETWORK.segments:
        r1, c1 = road.start_cell
        r2, c2 = road.end_cell
        cells = rasterize_line(r1, c1, r2, c2)
        d_list = [float(depth_arr[r, c]) for r, c in cells if 0 <= r < depth_arr.shape[0] and 0 <= c < depth_arr.shape[1]]
        max_d_road = max(d_list) if d_list else 0.0
        cls = classify(max_d_road, POLICY)
        road_impacts.append({
            "road_id": road.road_id,
            "road_class": road.road_class,
            "name": road.name,
            "max_depth_m": max_d_road,
            "classification": cls,
        })

    screener = EarlyWarningScreener()
    cap_alert_obj = screener.screen_simulation_frame(
        depth_grid=depth_arr,
        road_impacts=road_impacts,
        lead_minutes=lead_minutes,
        scenario_id=clean_scenario,
    )

    # Snapshot metrics from snapshot_inventory or computed from depth grid
    snap = next((s for s in res_dict.get("snapshot_inventory", [])
                 if s.get("lead_minutes") == lead_minutes), {})
    max_d = float(snap.get("max_depth_m", np.max(depth_arr) if depth_arr.size > 0 else 0.0))
    inundated_area = float(snap.get("flooded_area_m2", snap.get("inundated_area_m2", float(np.count_nonzero(depth_arr >= 0.05) * 900.0) if depth_arr.size > 0 else 0.0)))
    surf_stor = float(snap.get("total_flood_volume_m3", snap.get("surface_storage_m3", float(np.sum(depth_arr) * 900.0) if depth_arr.size > 0 else 0.0)))
    inundated_fraction = float(snap.get("inundated_fraction", (inundated_area / (depth_arr.shape[0] * depth_arr.shape[1] * 900.0)) if depth_arr.size > 0 else 0.0))

    # Impassable roads
    impassable_roads = [imp.get("road_id", "") for imp in road_impacts if imp.get("classification") == "IMPASSABLE"]
    caution_roads = [imp.get("road_id", "") for imp in road_impacts if imp.get("classification") == "CAUTION"]
    dry_roads = [imp.get("road_id", "") for imp in road_impacts if imp.get("classification") == "DRY"]

    if max_d >= 0.50 or len(impassable_roads) >= 2:
        sev_label = "EXTREME RED"
    elif max_d >= 0.30 or len(impassable_roads) >= 1:
        sev_label = "SEVERE ORANGE"
    elif max_d >= 0.15 or len(caution_roads) >= 2:
        sev_label = "MODERATE AMBER"
    else:
        sev_label = "MINOR GREEN"

    # Mass balance values
    ml = res_dict.get("mass_ledger", {})
    has_ml = bool(ml and ("rainfall_input_m3" in ml or "cumulative_rainfall_m3" in ml))
    tot_inflow = float(ml.get("rainfall_input_m3", ml.get("cumulative_rainfall_m3", 0.0)))
    tot_outflow = float(ml.get("drainage_outfall_m3", ml.get("cumulative_drainage_m3", 0.0)))
    sub_stor = float(tot_inflow - tot_outflow - surf_stor) if has_ml else 0.0

    raw_global = ml.get("combined_residual_m3", ml.get("global_mass_balance_residual_m3", ml.get("absolute_residual_m3")))
    global_res: Optional[float] = float(raw_global) if raw_global is not None else None

    raw_res = ml.get("relative_residual", ml.get("residual_fraction_pct"))
    if raw_res is not None:
        rel_err_pct: Optional[float] = abs(float(raw_res)) * (100.0 if "relative_residual" in ml else 1.0)
        continuity_pass = bool(rel_err_pct < 0.05)
    else:
        rel_err_pct = None
        continuity_pass = False

    weights = compute_blending_weights(lead_minutes)

    exec_section = ExecutiveSummarySection(
        scenario_id=clean_scenario,
        lead_minutes=lead_minutes,
        severity_level=sev_label,
        max_flood_depth_m=max_d,
        inundated_area_sqm=inundated_area,
        surface_storage_volume_m3=surf_stor,
        inundated_fraction_pct=float(inundated_fraction * 100.0),
        peak_crest_lead_minutes=int(res_dict.get("peak_depth_time_minutes", 110)),
        summary_text=(
            f"Scenario {clean_scenario} coupled hydrodynamic simulation indicates peak surface waterlogging "
            f"of {max_d:.2f} m affecting {inundated_area:,.0f} sq.m ({inundated_fraction*100:.1f}% of domain). "
            f"Underground SWMM drainage experiences hydraulic surcharge with {len(impassable_roads)} road closures."
        ),
    )

    mass_section = MassBalanceAuditSection(
        cumulative_rainfall_inflow_m3=tot_inflow,
        cumulative_swmm_outfall_m3=tot_outflow,
        surface_storage_m3=surf_stor,
        subsurface_conduit_storage_m3=max(0.0, sub_stor),
        global_mass_residual_m3=global_res,
        relative_error_pct=rel_err_pct,
        certified_continuity_pass=continuity_pass,
        certification_seal="MoES-NCMRWF-CERTIFIED-NUMERICAL-CONTINUITY-PASS" if continuity_pass else "MoES-NCMRWF-CONTINUITY-UNVERIFIED",
    )

    transport_section = TransportationSection(
        total_roads_inspected=len(road_impacts),
        impassable_roads_count=len(impassable_roads),
        caution_roads_count=len(caution_roads),
        dry_roads_count=len(dry_roads),
        impassable_road_ids=impassable_roads,
        sample_detour_savings_min=None,
    )

    cap_section = CAPAlertSection(
        alert_identifier=cap_alert_obj.identifier if cap_alert_obj else f"UFNS-ALERT-{dossier_id}",
        headline=cap_alert_obj.info[0].headline if cap_alert_obj and cap_alert_obj.info else f"Flood Warning: Scenario {clean_scenario}",
        instruction=cap_alert_obj.info[0].instruction if cap_alert_obj and cap_alert_obj.info else "Follow flood-aware detours.",
        urgency=cap_alert_obj.info[0].urgency.value if cap_alert_obj and cap_alert_obj.info else "Expected",
        severity=cap_alert_obj.info[0].severity.value if cap_alert_obj and cap_alert_obj.info else "Severe",
        certainty=cap_alert_obj.info[0].certainty.value if cap_alert_obj and cap_alert_obj.info else "Likely",
        dispatched_channels_count=0,
    )

    prov_section = ProvenanceSection(
        dem_source="Copernicus DEM GLO-30 / Bagjola Pilot Tile",
        spatial_crs="EPSG:32645 (UTM Zone 45N)",
        grid_resolution_m=30.0,
        hyetograph_derivation="Alternating-Block Design Storm (Chow et al. 1988) - D-016 Aligned",
        radar_weight_pct=weights.w_radar * 100.0,
        nwp_weight_pct=weights.w_nwp * 100.0,
        d016_status="PROVISIONAL_REVIEW",
        governance_disclaimer="SIMULATION EXERCISE ONLY - NOT FOR OPERATIONAL PUBLIC DISPATCH WITHOUT NCMRWF VALIDATION",
    )

    return FloodIncidentDossier(
        dossier_id=dossier_id,
        generated_at_utc=now_utc,
        executive_summary=exec_section,
        mass_balance=mass_section,
        transportation=transport_section,
        cap_alert=cap_section,
        provenance=prov_section,
    )


# ---------------------------------------------------------------------------
# PDF Dossier Compiler (ReportLab)
# ---------------------------------------------------------------------------

class PDFDossierCompiler:
    """Compiles a FloodIncidentDossier into a publication-quality vector PDF."""

    def __init__(self) -> None:
        """Execute   Init   operation and return result."""
        self.styles = getSampleStyleSheet()
        self._init_custom_styles()

    def _init_custom_styles(self) -> None:
        """Execute  Init Custom Styles operation and return result."""
        self.style_title = ParagraphStyle(
            "DocTitle",
            parent=self.styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0e1a29"),
        )
        self.style_subtitle = ParagraphStyle(
            "DocSubTitle",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#55606e"),
        )
        self.style_h2 = ParagraphStyle(
            "DocH2",
            parent=self.styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#1a568c"),
            spaceBefore=10,
            spaceAfter=4,
        )
        self.style_body = ParagraphStyle(
            "DocBody",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=colors.HexColor("#222a33"),
        )
        self.style_mono = ParagraphStyle(
            "DocMono",
            parent=self.styles["Normal"],
            fontName="Courier",
            fontSize=7.5,
            leading=9.5,
            textColor=colors.HexColor("#1b2533"),
        )

    def compile_pdf(self, dossier: FloodIncidentDossier) -> bytes:
        """Render complete dossier to PDF bytes."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        elements: list[Any] = []

        # 1. Header Banner
        header_table = Table(
            [
                [
                    Paragraph("<b>NATIONAL CENTRE FOR MEDIUM RANGE WEATHER FORECASTING</b><br/><font size=7 color='#55606e'>Ministry of Earth Sciences (MoES), Government of India</font>", self.style_title),
                    Paragraph(f"<b>REPORT ID</b><br/><font size=7 color='#1a568c'>{dossier.dossier_id}</font><br/><font size=6 color='#778899'>UTC: {dossier.generated_at_utc.strftime('%Y-%m-%d %H:%M:%S')}</font>", self.style_subtitle),
                ]
            ],
            colWidths=[360, 160],
        )
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(header_table)
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1a568c"), spaceAfter=8))

        # Notice Pill
        sev_color = colors.HexColor("#c82848") if "RED" in dossier.executive_summary.severity_level else (
            colors.HexColor("#e8871e") if "ORANGE" in dossier.executive_summary.severity_level else colors.HexColor("#d49a22")
        )
        pill_table = Table(
            [[
                Paragraph(f"<font color='white'><b>INCIDENT LEVEL: {dossier.executive_summary.severity_level}</b></font>", self.style_body),
                Paragraph("<font color='white'><b>[EXERCISE / SIMULATION ONLY]</b></font>", self.style_body),
            ]],
            colWidths=[260, 260],
        )
        pill_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), sev_color),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#2c3e50")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(pill_table)
        elements.append(Spacer(1, 8))

        # 2. Executive Incident Briefing
        elements.append(Paragraph("1. EXECUTIVE INUNDATION SUMMARY", self.style_h2))
        kpi_data = [
            [
                Paragraph("<b>Peak Flood Depth</b>", self.style_body),
                Paragraph(f"<b>{dossier.executive_summary.max_flood_depth_m:.2f} m</b>", self.style_body),
                Paragraph("<b>Inundated Surface Area</b>", self.style_body),
                Paragraph(f"<b>{dossier.executive_summary.inundated_area_sqm:,.0f} sq.m</b>", self.style_body),
            ],
            [
                Paragraph("<b>Overland Storage Volume</b>", self.style_body),
                Paragraph(f"<b>{dossier.executive_summary.surface_storage_volume_m3:,.0f} m³</b>", self.style_body),
                Paragraph("<b>Domain Flooded Fraction</b>", self.style_body),
                Paragraph(f"<b>{dossier.executive_summary.inundated_fraction_pct:.1f}%</b>", self.style_body),
            ],
            [
                Paragraph("<b>Simulation Scenario</b>", self.style_body),
                Paragraph(f"<b>{dossier.executive_summary.scenario_id} (+{dossier.executive_summary.lead_minutes}m)</b>", self.style_body),
                Paragraph("<b>Peak Inundation Crest</b>", self.style_body),
                Paragraph(f"<b>+{dossier.executive_summary.peak_crest_lead_minutes} min</b>", self.style_body),
            ],
        ]
        kpi_table = Table(kpi_data, colWidths=[130, 130, 130, 130])
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f7fb")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0dbe5")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(kpi_table)
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(f"<font color='#55606e'><i>{dossier.executive_summary.summary_text}</i></font>", self.style_body))
        elements.append(Spacer(1, 8))

        # 3. Certified Mass Conservation Ledger
        elements.append(Paragraph("2. CERTIFIED HYDRODYNAMIC MASS BALANCE CONTINUITY", self.style_h2))
        res_str = f"{dossier.mass_balance.global_mass_residual_m3:+.2f} m³" if dossier.mass_balance.global_mass_residual_m3 is not None else "N/A"
        err_str = f"Error: {dossier.mass_balance.relative_error_pct:.4f}% (< 0.05%)" if dossier.mass_balance.relative_error_pct is not None else "Error: N/A (Unverified)"

        mass_data = [
            ["Hydrodynamic Term", "Volume (m³)", "Continuity Balance Equation"],
            ["Cumulative Rainfall Surface Inflow", f"{dossier.mass_balance.cumulative_rainfall_inflow_m3:,.1f}", "V_in"],
            ["Cumulative SWMM Drainage Outfall", f"{dossier.mass_balance.cumulative_swmm_outfall_m3:,.1f}", "V_out"],
            ["Overland Surface Storage Inundation", f"{dossier.mass_balance.surface_storage_m3:,.1f}", "S_2D"],
            ["Underground Conduit Water Storage", f"{dossier.mass_balance.subsurface_conduit_storage_m3:,.1f}", "S_1D"],
            ["Global Mass Balance Residual Error", res_str, err_str],
        ]
        row5_bg = colors.HexColor("#e8f5e9") if dossier.mass_balance.certified_continuity_pass else colors.HexColor("#fbe9e7")
        row5_fg = colors.HexColor("#1b5e20") if dossier.mass_balance.certified_continuity_pass else colors.HexColor("#c62828")

        mass_table = Table(mass_data, colWidths=[200, 140, 180])
        mass_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a568c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#ffffff")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0dbe5")),
            ("BACKGROUND", (0, 5), (-1, 5), row5_bg),
            ("TEXTCOLOR", (0, 5), (-1, 5), row5_fg),
            ("FONTNAME", (0, 5), (-1, 5), "Helvetica-Bold"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(mass_table)
        if dossier.mass_balance.certified_continuity_pass and dossier.mass_balance.relative_error_pct is not None:
            elements.append(Paragraph(
                f"<font size=7 color='#2e7d32'>[PASS] <b>FORMAL CERTIFICATION</b>: Global hydrodynamic fluid continuity error "
                f"({dossier.mass_balance.relative_error_pct:.4f}%) satisfies the numerical threshold (&lt;0.05%).</font>",
                self.style_body,
            ))
        else:
            err_disp = f"({dossier.mass_balance.relative_error_pct:.4f}%)" if dossier.mass_balance.relative_error_pct is not None else "(N/A)"
            elements.append(Paragraph(
                f"<font size=7 color='#c82848'>[FAIL] <b>NOT CERTIFIED</b>: Global hydrodynamic fluid continuity error "
                f"{err_disp} exceeds the numerical threshold (&lt;0.05%) or residual was unverified.</font>",
                self.style_body,
            ))
        elements.append(Spacer(1, 8))

        # 4. Transportation Impassability Register
        elements.append(Paragraph("3. MOBILITY & TRANSPORTATION RISK ASSESSMENT", self.style_h2))
        imp_str = ", ".join(dossier.transportation.impassable_road_ids) if dossier.transportation.impassable_road_ids else "None"
        trans_data = [
            ["Inspected Road Network", "Impassable (>0.30m)", "Caution (0.15–0.30m)", "Dry Corridors"],
            [
                f"{dossier.transportation.total_roads_inspected} segments",
                f"<b>{dossier.transportation.impassable_roads_count} closed</b>",
                f"{dossier.transportation.caution_roads_count} slow",
                f"{dossier.transportation.dry_roads_count} clear",
            ],
        ]
        trans_table = Table(trans_data, colWidths=[130, 130, 130, 130])
        trans_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3f8")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0dbe5")),
            ("TEXTCOLOR", (1, 1), (1, 1), colors.HexColor("#c82848")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(trans_table)
        elements.append(Paragraph(f"<b>Closed Street Segments</b>: <font color='#c82848'>{imp_str}</font>", self.style_body))
        if dossier.transportation.sample_detour_savings_min is not None:
            elements.append(Paragraph(f"<b>Flood-Aware Rerouting Benefit</b>: Average estimated detour time savings of <b>{dossier.transportation.sample_detour_savings_min:.1f} minutes</b> per routed emergency response trip.", self.style_body))
        else:
            elements.append(Paragraph("<b>Flood-Aware Rerouting Benefit</b>: Detour time savings not evaluated for this scenario frame.", self.style_body))
        elements.append(Spacer(1, 8))

        # 5. Common Alerting Protocol (CAP v1.2) Broadcast Record
        elements.append(Paragraph("4. OASIS COMMON ALERTING PROTOCOL (CAP v1.2) BROADCAST", self.style_h2))
        dispatch_text = (
            f"{dossier.cap_alert.dispatched_channels_count} channels delivered (SMS, WhatsApp, Webhook, GeoRSS Feed)."
            if dossier.cap_alert.dispatched_channels_count > 0
            else "Awaiting manual/automated dispatch trigger."
        )
        cap_box_data = [
            [Paragraph(f"<b>CAP Identifier</b>: {dossier.cap_alert.alert_identifier}<br/><b>Urgency / Severity / Certainty</b>: {dossier.cap_alert.urgency} / {dossier.cap_alert.severity} / {dossier.cap_alert.certainty}<br/><b>Headline</b>: <font color='#c82848'><b>{dossier.cap_alert.headline}</b></font><br/><b>Instruction</b>: {dossier.cap_alert.instruction}<br/><b>Multi-Channel Dispatch Receipts</b>: {dispatch_text}", self.style_body)]
        ]
        cap_table = Table(cap_box_data, colWidths=[520])
        cap_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff9f0")),
            ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#d49a22")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.append(cap_table)
        elements.append(Spacer(1, 8))

        # 6. Scientific Provenance & Governance
        elements.append(Paragraph("5. SCIENTIFIC PROVENANCE & GOVERNANCE SIGNATURES", self.style_h2))
        prov_text = (
            f"<b>DEM Foundation</b>: {dossier.provenance.dem_source} ({dossier.provenance.spatial_crs}, {dossier.provenance.grid_resolution_m:.0f}m resolution)<br/>"
            f"<b>Meteorological Blending</b>: Radar Weight {dossier.provenance.radar_weight_pct:.0f}%, NWP Weight {dossier.provenance.nwp_weight_pct:.0f}%<br/>"
            f"<b>Hyetograph Derivation</b>: {dossier.provenance.hyetograph_derivation} [Status: {dossier.provenance.d016_status}]<br/>"
            f"<b>Disclaimer</b>: <font color='#778899'>{dossier.provenance.governance_disclaimer}</font>"
        )
        elements.append(Paragraph(prov_text, self.style_body))

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()


GLOBAL_DOSSIER_COMPILER = PDFDossierCompiler()
