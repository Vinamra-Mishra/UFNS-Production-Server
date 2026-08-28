"""Hyperlocal early warning threshold screening and ward spatial aggregation engine (Phase C).

Analyzes hydrodynamic 2D water depth rasters and road network impact vectors to
generate structured OASIS CAP v1.2 alerts with targeted warning geofences.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

from services.alerting.cap import (
    CAPAlert,
    CAPArea,
    CAPCategory,
    CAPCertainty,
    CAPInfo,
    CAPMsgType,
    CAPResource,
    CAPScope,
    CAPSeverity,
    CAPStatus,
    CAPUrgency,
)
from services.routing.policy import THRESHOLDS


@dataclass(frozen=True)
class AlertThresholds:
    """Configurable physical trigger thresholds for early warning escalation."""

    minor_depth_m: float = 0.05      # Advisory threshold
    moderate_depth_m: float = 0.15   # Amber watch threshold
    severe_depth_m: float = 0.30     # Orange warning threshold
    extreme_depth_m: float = 0.50    # Red emergency action threshold
    impassable_count_extreme: int = 2


@dataclass
class WardImpactSummary:
    """Aggregated civic risk metrics for an administrative ward / sector."""

    ward_id: str
    ward_name: str
    inundated_area_m2: float
    severe_inundated_area_m2: float
    max_depth_m: float
    mean_depth_m: float
    impacted_road_km: float
    impassable_road_count: int
    caution_road_count: int
    critical_facilities_at_risk: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "ward_id": self.ward_id,
            "ward_name": self.ward_name,
            "inundated_area_m2": round(self.inundated_area_m2, 1),
            "severe_inundated_area_m2": round(self.severe_inundated_area_m2, 1),
            "max_depth_m": round(self.max_depth_m, 3),
            "mean_depth_m": round(self.mean_depth_m, 3),
            "impacted_road_km": round(self.impacted_road_km, 2),
            "impassable_road_count": self.impassable_road_count,
            "caution_road_count": self.caution_road_count,
            "critical_facilities_at_risk": self.critical_facilities_at_risk,
        }


class EarlyWarningScreener:
    """Translates 2D flood depths and road impacts into standardized CAP v1.2 alerts."""

    def __init__(self, thresholds: Optional[AlertThresholds] = None) -> None:
        """Execute   Init   operation and return result."""
        self.thresholds = thresholds or AlertThresholds()

    def screen_simulation_frame(
        self,
        depth_grid: np.ndarray,
        road_impacts: list[dict[str, Any]],
        lead_minutes: int = 0,
        scenario_id: str = "S4",
        status: CAPStatus = CAPStatus.EXERCISE,
        base_time: Optional[datetime] = None,
        cell_size_m: float = 30.0,
        origin_utm: tuple[float, float] = (300000.0, 2500000.0),
    ) -> Optional[CAPAlert]:
        """Screen flood depth grid & road impacts to evaluate if an alert should be issued.

        Returns None if conditions are below the minor advisory threshold.
        """
        now = base_time or datetime.now(timezone.utc)
        valid_time = now + timedelta(minutes=lead_minutes)
        expires_time = valid_time + timedelta(hours=2)

        depth_arr = np.asarray(depth_grid, dtype=np.float64)
        max_d = float(np.max(depth_arr)) if depth_arr.size > 0 else 0.0
        wet_mask = depth_arr > self.thresholds.minor_depth_m
        inundated_cells = int(np.count_nonzero(wet_mask))
        inundated_area_m2 = inundated_cells * (cell_size_m ** 2)

        severe_cells = int(np.count_nonzero(depth_arr > self.thresholds.severe_depth_m))
        severe_area_m2 = severe_cells * (cell_size_m ** 2)

        impassable_roads = [r for r in road_impacts if r.get("classification") == "IMPASSABLE"]
        caution_roads = [r for r in road_impacts if r.get("classification") in ("CAUTION", "HIGH_IMPACT")]

        # Determine severity
        if max_d >= self.thresholds.extreme_depth_m or len(impassable_roads) >= self.thresholds.impassable_count_extreme:
            severity = CAPSeverity.EXTREME
            color_band = "RED"
            event_name = "Urban Flash Flood - Emergency Inundation Warning"
        elif max_d >= self.thresholds.severe_depth_m or len(impassable_roads) >= 1:
            severity = CAPSeverity.SEVERE
            color_band = "ORANGE"
            event_name = "Urban Flood Warning - High Waterlogging & Road Closures"
        elif max_d >= self.thresholds.moderate_depth_m or len(caution_roads) >= 2:
            severity = CAPSeverity.MODERATE
            color_band = "AMBER"
            event_name = "Urban Flood Watch - Moderate Road Waterlogging"
        elif max_d >= self.thresholds.minor_depth_m or len(caution_roads) >= 1:
            severity = CAPSeverity.MINOR
            color_band = "GREEN"
            event_name = "Urban Ponding Advisory - Minor Surface Runoff"
        else:
            return None  # No alert required

        urgency = CAPUrgency.IMMEDIATE if lead_minutes == 0 else CAPUrgency.EXPECTED
        certainty = CAPCertainty.OBSERVED if lead_minutes == 0 else CAPCertainty.LIKELY

        # Extract bounding polygon of inundated zone (approximate bounding envelope)
        rows, cols = np.where(wet_mask)
        polygon_coords: list[tuple[float, float]] = []
        if len(rows) > 0:
            min_r, max_r = int(np.min(rows)), int(np.max(rows))
            min_c, max_c = int(np.min(cols)), int(np.max(cols))

            # Convert grid cell to accurate lat/lon near Kolkata pilot (22.5 deg N, 88.35 deg E)
            lat_base, lon_base = 22.5000, 88.3500
            deg_per_m_lat = 1.0 / 111132.0
            deg_per_m_lon = 1.0 / (111320.0 * math.cos(math.radians(lat_base)))

            y_min = origin_utm[1] + (depth_arr.shape[0] - max_r - 1) * cell_size_m
            y_max = origin_utm[1] + (depth_arr.shape[0] - min_r) * cell_size_m
            x_min = origin_utm[0] + min_c * cell_size_m
            x_max = origin_utm[0] + (max_c + 1) * cell_size_m

            # 4-corner bounding box
            lat_s = lat_base + (y_min - origin_utm[1]) * deg_per_m_lat
            lat_n = lat_base + (y_max - origin_utm[1]) * deg_per_m_lat
            lon_w = lon_base + (x_min - origin_utm[0]) * deg_per_m_lon
            lon_e = lon_base + (x_max - origin_utm[0]) * deg_per_m_lon

            polygon_coords = [
                (lat_n, lon_w),
                (lat_n, lon_e),
                (lat_s, lon_e),
                (lat_s, lon_w),
                (lat_n, lon_w),
            ]

        # Generate targeted instructions and road detour advice
        impassable_names = [r.get("road_id", "Unknown Road") for r in impassable_roads]
        impassable_str = ", ".join(impassable_names) if impassable_names else "None"

        headline = (
            f"[{status.value.upper()} / SIMULATION ONLY] {color_band} LEVEL: {event_name} "
            f"(Lead +{lead_minutes}m, Max Depth: {max_d:.2f}m)"
        )

        desc = (
            f"Coupled hydrodynamic simulation projections indicate maximum flood depth of {max_d:.2f} m "
            f"across {inundated_area_m2:,.0f} sq.m of urban surface. "
            f"Impassable road segments ({len(impassable_roads)}): {impassable_str}. "
            f"Caution road segments ({len(caution_roads)}). "
            f"Scientific Provenance: Scenario {scenario_id}, Resolution {cell_size_m}m, D-016 hyetograph profile."
        )

        instr = (
            "1. Avoid waterlogged corridors and submerged road underpasses. "
            "2. Utilize UFNS flood-aware dynamic rerouting to bypass impassable road segments. "
            "3. Emergency services should stage response units outside low-elevation drainage sinks."
        )

        area = CAPArea(
            area_desc=f"Kolkata Urban Pilot Sector — High Inundation Zone (Scenario {scenario_id})",
            polygon=tuple(polygon_coords),
            geocode={"Ward": "84", "District": "Kolkata", "State": "West Bengal"},
        )

        info = CAPInfo(
            event=event_name,
            urgency=urgency,
            severity=severity,
            certainty=certainty,
            headline=headline,
            description=desc,
            instruction=instr,
            effective=now.isoformat(),
            onset=valid_time.isoformat(),
            expires=expires_time.isoformat(),
            parameters={
                "AlertColor": color_band,
                "LeadMinutes": str(lead_minutes),
                "MaxDepthMeters": f"{max_d:.3f}",
                "InundatedAreaM2": f"{inundated_area_m2:.1f}",
                "ImpassableRoadCount": str(len(impassable_roads)),
                "ScenarioId": scenario_id,
                "Disclaimer": "EXERCISE / SIMULATION ONLY — NOT FOR OPERATIONAL USE (D-016 / B13-DEMO-V1)",
            },
            resources=[
                CAPResource(
                    resource_desc="Flood Extent GeoJSON",
                    mime_type="application/geo+json",
                    uri=f"/api/v1/scenarios/{scenario_id}/flood-extent",
                ),
                CAPResource(
                    resource_desc="Interactive Dashboard Reroute",
                    mime_type="text/html",
                    uri="http://localhost:8000",
                ),
            ],
            areas=[area],
        )

        alert_id = f"UFNS-CAP-{now.strftime('%Y%m%d%H%M%S')}-{scenario_id}-{lead_minutes:03d}"

        return CAPAlert(
            identifier=alert_id,
            sender="ncmrwf-ufns-screening@ncmrwf.gov.in",
            sent=now.isoformat(),
            status=status,
            msg_type=CAPMsgType.ALERT,
            scope=CAPScope.PUBLIC,
            note="SIMULATED EXERCISE / PROVISIONAL DEMONSTRATION — NOT AN ACTUAL ALERT. NOT FOR OPERATIONAL DEPLOYMENT (D-016 / B13).",
            info=[info],
        )
