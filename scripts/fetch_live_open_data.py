#!/usr/bin/env python3
"""Fetch and synchronize real-time meteorological, oceanographic, and hydrological feeds.

Pulls live data from free public APIs:
- RainViewer Doppler Radar Mosaic index & frame timestamps
- Open-Meteo 15-minute sub-hourly localized precipitation (Mumbai & Vijayawada)
- Open-Meteo Multi-Model NWP (ECMWF IFS, GFS, ICON) precipitation
- Open-Meteo Marine Tide & Storm Surge (Mumbai Arabian Sea coast)
- Open-Meteo GloFAS Krishna River Discharge (Vijayawada Prakasam Barrage)
- OpenSenseMap IoT Community Rain Gauges

Usage:
    python scripts/fetch_live_open_data.py
    python scripts/fetch_live_open_data.py --city mumbai
    python scripts/fetch_live_open_data.py --city vijayawada
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from services.ingestion.live_feeds import (
    GloFASRiverDischargeClient,
    MarineTideSurgeClient,
    OpenMeteoNWPClient,
    OpenMeteoPrecipitationClient,
    OpenSenseMapClient,
    RainViewerClient,
)

LIVE_DIR = REPO_ROOT / "data" / "live"

CITY_COORDS = {
    "mumbai": {
        "name": "Mumbai",
        "lat": 18.96,
        "lon": 72.82,
        "bbox": (72.75, 18.88, 72.98, 19.28),
        "has_marine": True,
        "marine_coords": (18.92, 72.83),
        "has_river": False,
    },
    "vijayawada": {
        "name": "Vijayawada",
        "lat": 16.51,
        "lon": 80.62,
        "bbox": (80.55, 16.45, 80.72, 16.58),
        "has_marine": False,
        "has_river": True,
        "river_coords": (16.51, 80.62),
    },
}


def sha256_bytes(data: bytes) -> str:
    """Execute Sha256 Bytes operation and return result."""
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    """Execute Main operation and return result."""
    parser = argparse.ArgumentParser(description="Fetch live open feeds for UFNS")
    parser.add_argument("--city", choices=list(CITY_COORDS) + ["all"], default="all")
    args = parser.parse_args()

    target_cities = list(CITY_COORDS) if args.city == "all" else [args.city]

    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    manifest_files = {}

    print("\n" + "=" * 70)
    print("  UFNS LIVE DATA SYNCHRONIZATION PIPELINE")
    print("=" * 70)

    # 1. Global RainViewer Radar
    print("\n>>> [1/5] Fetching RainViewer Global Doppler Radar Index ...")
    radar_client = RainViewerClient()
    try:
        radar_meta = radar_client.get_latest_radar_frames()
        radar_path = LIVE_DIR / "radar_index.json"
        radar_bytes = json.dumps(radar_meta, indent=2).encode("utf-8")
        radar_path.write_bytes(radar_bytes)
        n_past = len(radar_meta.get("past_timestamps", []))
        n_nowcast = len(radar_meta.get("nowcast_timestamps", []))
        print(f"    [OK] RainViewer Index: {n_past} past frames, {n_nowcast} nowcast frames -> radar_index.json")
        manifest_files["radar_index.json"] = {
            "size_bytes": len(radar_bytes),
            "sha256": sha256_bytes(radar_bytes),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        print(f"    [WARN] RainViewer fetch failed: {e}")

    # 2. City-Specific Feeds
    precip_client = OpenMeteoPrecipitationClient()
    nwp_client = OpenMeteoNWPClient()
    marine_client = MarineTideSurgeClient()
    glofas_client = GloFASRiverDischargeClient()
    iot_client = OpenSenseMapClient()

    for city in target_cities:
        cfg = CITY_COORDS[city]
        city_dir = LIVE_DIR / city
        city_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n>>> Processing Live Feeds for {cfg['name'].upper()} ...")

        # 2a. 15-Minute Local Precipitation
        try:
            precip_data = precip_client.get_live_precipitation(cfg["lat"], cfg["lon"])
            p_path = city_dir / "live_precipitation.json"
            p_bytes = json.dumps(precip_data, indent=2).encode("utf-8")
            p_path.write_bytes(p_bytes)
            curr = precip_data.get("current", {})
            curr_rain = curr.get("precipitation", 0.0)
            curr_temp = curr.get("temperature_2m", 0.0)
            print(f"    [OK] 15-Min Precipitation: Current Rain = {curr_rain} mm/h, Temp = {curr_temp}°C -> live_precipitation.json")
            manifest_files[f"{city}/live_precipitation.json"] = {
                "size_bytes": len(p_bytes),
                "sha256": sha256_bytes(p_bytes),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            print(f"    [WARN] Precipitation fetch failed for {city}: {e}")

        # 2b. Multi-Model NWP Forecasts
        try:
            nwp_data = nwp_client.get_multi_model_forecast(cfg["lat"], cfg["lon"])
            nwp_path = city_dir / "nwp_forecast.json"
            nwp_bytes = json.dumps(nwp_data, indent=2).encode("utf-8")
            nwp_path.write_bytes(nwp_bytes)
            print(f"    [OK] Multi-Model NWP (ECMWF+GFS+ICON): 72-hr forecast synced -> nwp_forecast.json")
            manifest_files[f"{city}/nwp_forecast.json"] = {
                "size_bytes": len(nwp_bytes),
                "sha256": sha256_bytes(nwp_bytes),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            print(f"    [WARN] NWP fetch failed for {city}: {e}")

        # 2c. Marine Tides & Storm Surge (if coastal)
        if cfg.get("has_marine"):
            try:
                mlat, mlon = cfg["marine_coords"]
                marine_data = marine_client.get_tide_surge_forecast(mlat, mlon)
                m_path = city_dir / "marine_tide_surge.json"
                m_bytes = json.dumps(marine_data, indent=2).encode("utf-8")
                m_path.write_bytes(m_bytes)
                print(f"    [OK] Arabian Sea Tide & Storm Surge: 7-day sea level MSL synced -> marine_tide_surge.json")
                manifest_files[f"{city}/marine_tide_surge.json"] = {
                    "size_bytes": len(m_bytes),
                    "sha256": sha256_bytes(m_bytes),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as e:
                print(f"    [WARN] Marine tide fetch failed: {e}")

        # 2d. River Discharge / Barrage Inflow (if riverine)
        if cfg.get("has_river"):
            try:
                rlat, rlon = cfg["river_coords"]
                river_data = glofas_client.get_river_discharge(rlat, rlon)
                r_path = city_dir / "krishna_river_discharge.json"
                r_bytes = json.dumps(river_data, indent=2).encode("utf-8")
                r_path.write_bytes(r_bytes)
                daily_q = river_data.get("daily", {}).get("river_discharge", [])
                latest_q = daily_q[0] if daily_q else "N/A"
                print(f"    [OK] Krishna River GloFAS Inflow: {latest_q} m³/s at Prakasam Barrage -> krishna_river_discharge.json")
                manifest_files[f"{city}/krishna_river_discharge.json"] = {
                    "size_bytes": len(r_bytes),
                    "sha256": sha256_bytes(r_bytes),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as e:
                print(f"    [WARN] River discharge fetch failed: {e}")

        # 2e. OpenSenseMap Community IoT Gauges
        try:
            iot_boxes = iot_client.get_iot_boxes(cfg["bbox"])
            iot_path = city_dir / "iot_gauges.json"
            iot_bytes = json.dumps(iot_boxes, indent=2).encode("utf-8")
            iot_path.write_bytes(iot_bytes)
            print(f"    [OK] OpenSenseMap IoT Gauges: {len(iot_boxes)} community stations -> iot_gauges.json")
            manifest_files[f"{city}/iot_gauges.json"] = {
                "size_bytes": len(iot_bytes),
                "sha256": sha256_bytes(iot_bytes),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            print(f"    [WARN] IoT gauge fetch failed: {e}")

    # Write Manifest
    manifest = {
        "status": "OPERATIONAL_LIVE_FEEDS_SYNCED",
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "files": manifest_files,
    }
    (LIVE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n  [OK] Live synchronization manifest written -> {LIVE_DIR / 'manifest.json'}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
