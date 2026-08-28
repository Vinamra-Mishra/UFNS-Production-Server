"""Live Meteorological, Oceanographic, and Hydrological Feed Connectors.

Integrates authoritative, open, non-commercial public APIs without proprietary keys:
1. RainViewer Global Doppler Radar API: Real-time 5-min radar reflectivity composites (mosaicking IMD DWR).
2. Open-Meteo High-Resolution Precipitation: 15-minute sub-hourly rainfall observations.
3. Open-Meteo Multi-Model NWP: ECMWF IFS, NOAA GFS, and DWD ICON ensemble precipitation.
4. Open-Meteo Marine Surge & Tide API: 10-day hourly sea-level height & surge forecasts (Arabian Sea).
5. Open-Meteo / Copernicus GloFAS Flood API: 7-day Krishna River discharge at Prakasam Barrage.
6. OpenSenseMap Community IoT Network: Crowdsourced urban precipitation sensors.
"""

from __future__ import annotations

import json
import math
import ssl
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from services.ingestion.radar import ZR_CONVECTIVE, ZR_MARSHALL_PALMER, ZRRelationship

USER_AGENT = "UFNS-SIH26085/1.0 (Urban Flood Nowcasting System; research contact: sih2026@example.com)"
SSL_CTX = ssl.create_default_context()


def _http_get_json(url: str, timeout: float = 20.0) -> Any:
    """Safely fetch and parse JSON from a REST endpoint."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# 1. RainViewer Doppler Radar Client
# ---------------------------------------------------------------------------

class RainViewerClient:
    """Client for RainViewer global Doppler radar mosaic API."""

    INDEX_URL = "https://api.rainviewer.com/public/weather-maps.json"

    def get_latest_radar_frames(self) -> dict[str, Any]:
        """Fetch the list of latest available radar and nowcast frame timestamps."""
        data = _http_get_json(self.INDEX_URL)
        past_frames = data.get("radar", {}).get("past", [])
        nowcast_frames = data.get("radar", {}).get("nowcast", [])
        host = data.get("host", "https://tilecache.rainviewer.com")

        return {
            "host": host,
            "generated_at": data.get("generated"),
            "past_timestamps": [f.get("time") for f in past_frames],
            "nowcast_timestamps": [f.get("time") for f in nowcast_frames],
            "past_paths": [f.get("path") for f in past_frames],
            "nowcast_paths": [f.get("path") for f in nowcast_frames],
        }

    def get_tile_url(self, path: str, z: int, x: int, y: int, color_scheme: int = 2, smooth: int = 1) -> str:
        """Construct radar tile URL."""
        return f"https://tilecache.rainviewer.com{path}/256/{z}/{x}/{y}/{color_scheme}/{smooth}_{smooth}.png"


# ---------------------------------------------------------------------------
# 2. Open-Meteo High-Resolution Precipitation Client
# ---------------------------------------------------------------------------

class OpenMeteoPrecipitationClient:
    """Client for Open-Meteo 15-minute and hourly localized precipitation."""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def get_live_precipitation(self, lat: float, lon: float) -> dict[str, Any]:
        """Fetch current, 15-minute, and hourly rainfall observations."""
        url = (
            f"{self.BASE_URL}?latitude={lat:.4f}&longitude={lon:.4f}"
            "&current=precipitation,rain,weather_code,temperature_2m"
            "&minutely_15=precipitation"
            "&hourly=precipitation,rain,weather_code"
            "&forecast_days=2&timezone=auto"
        )
        return _http_get_json(url)


# ---------------------------------------------------------------------------
# 3. Open-Meteo Multi-Model NWP Client
# ---------------------------------------------------------------------------

class OpenMeteoNWPClient:
    """Client for ECMWF IFS, NOAA GFS, and DWD ICON ensemble forecasts."""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def get_multi_model_forecast(self, lat: float, lon: float) -> dict[str, Any]:
        """Fetch blended and individual NWP model rainfall predictions."""
        url = (
            f"{self.BASE_URL}?latitude={lat:.4f}&longitude={lon:.4f}"
            "&models=ecmwf_ifs,gfs_seamless,icon_seamless"
            "&hourly=precipitation,weather_code"
            "&forecast_days=3&timezone=auto"
        )
        return _http_get_json(url)


# ---------------------------------------------------------------------------
# 4. Marine Tide & Storm Surge Client (Mumbai Coastal Boundary)
# ---------------------------------------------------------------------------

class MarineTideSurgeClient:
    """Client for Copernicus / Open-Meteo Marine tidal & storm surge forecasts."""

    BASE_URL = "https://marine-api.open-meteo.com/v1/marine"

    def get_tide_surge_forecast(self, lat: float = 18.92, lon: float = 72.83) -> dict[str, Any]:
        """Fetch 7-day sea level height (MSL) and ocean wave/surge dynamics."""
        url = (
            f"{self.BASE_URL}?latitude={lat:.4f}&longitude={lon:.4f}"
            "&hourly=sea_level_height_msl,wave_height,ocean_current_velocity"
            "&forecast_days=7&timezone=auto"
        )
        return _http_get_json(url)


# ---------------------------------------------------------------------------
# 5. GloFAS River Discharge Client (Vijayawada / Krishna River)
# ---------------------------------------------------------------------------

class GloFASRiverDischargeClient:
    """Client for Copernicus GloFAS Krishna River streamflow at Prakasam Barrage."""

    BASE_URL = "https://flood-api.open-meteo.com/v1/flood"

    def get_river_discharge(self, lat: float = 16.51, lon: float = 80.62) -> dict[str, Any]:
        """Fetch 7-day river discharge (m^3/s) for Prakasam Barrage catchment."""
        url = (
            f"{self.BASE_URL}?latitude={lat:.4f}&longitude={lon:.4f}"
            "&daily=river_discharge,river_discharge_mean,river_discharge_median"
            "&forecast_days=7"
        )
        return _http_get_json(url)


# ---------------------------------------------------------------------------
# 6. OpenSenseMap Community IoT Rain Gauge Client
# ---------------------------------------------------------------------------

class OpenSenseMapClient:
    """Client for OpenSenseMap crowdsourced IoT weather stations."""

    BASE_URL = "https://api.opensensemap.org/boxes"

    def get_iot_boxes(self, bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
        """Query IoT sensor boxes within a geographic bounding box [w, s, e, n]."""
        w, s, e, n = bbox
        url = f"{self.BASE_URL}?bbox={w:.4f},{s:.4f},{e:.4f},{n:.4f}&phenomenon=precipitation"
        try:
            res = _http_get_json(url)
            return res if isinstance(res, list) else []
        except Exception:
            return []
