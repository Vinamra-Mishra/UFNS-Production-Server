"""ISRO / MOSDAC Satellite Data FastAPI Router.

Provides endpoints for:
- MOSDAC Authentication & Session Token Status (/status)
- Satellite Product Catalogue (/catalog)
- Live Dataset Search (/search)
- Real-time Satellite Precipitation & Convective Cloud Top Observation (/latest-observation)
- Satellite Telemetry Status for UFNS (/telemetry)
"""

from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel

from services.ingestion.mosdac_client import GLOBAL_MOSDAC_CLIENT
from apps.api import city_api

router = APIRouter(prefix="/api/v1/mosdac", tags=["ISRO MOSDAC Satellite Ingestion"])


class MOSDACSearchRequest(BaseModel):
    datasetId: str = "3SIMG_L2B_HEM"
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    boundingBox: Optional[str] = None
    count: int = 10
    startIndex: int = 1


@router.get("/status")
def get_mosdac_status() -> dict[str, Any]:
    """Check MOSDAC session token and authentication status."""
    token_info = GLOBAL_MOSDAC_CLIENT.get_token()
    return {
        "service": "ISRO / MOSDAC Data Download API",
        "auth_status": token_info.get("status"),
        "user": token_info.get("username"),
        "quota_daily": 5000,
        "token_valid": token_info.get("status") in ("AUTHENTICATED", "CACHED_VALID", "CALIBRATED_SANDBOX"),
        "timestamp": token_info.get("authenticated_at"),
    }


@router.get("/catalog")
def get_mosdac_catalog() -> dict[str, Any]:
    """List supported ISRO satellite missions and product levels."""
    return GLOBAL_MOSDAC_CLIENT.get_catalog()


@router.get("/search")
def search_mosdac(
    dataset_id: str = Query("3SIMG_L2B_HEM", alias="datasetId"),
    start_time: Optional[str] = Query(None, alias="startTime"),
    end_time: Optional[str] = Query(None, alias="endTime"),
    bounding_box: Optional[str] = Query(None, alias="boundingBox"),
    count: int = Query(10),
    start_index: int = Query(1, alias="startIndex"),
) -> dict[str, Any]:
    """Search live satellite granules across INSAT-3DS, INSAT-3DR, and Oceansat."""
    return GLOBAL_MOSDAC_CLIENT.search_datasets(
        dataset_id=dataset_id,
        start_time=start_time,
        end_time=end_time,
        bounding_box=bounding_box,
        count=count,
        start_index=start_index,
    )


@router.get("/latest-observation")
def get_latest_observation(city: Optional[str] = Query(None)) -> dict[str, Any]:
    """Get latest INSAT-3DS Hydro-Estimator precipitation rate & cloud top temperature."""
    target_city = city or city_api.ACTIVE_CITY
    return GLOBAL_MOSDAC_CLIENT.get_latest_satellite_observation(target_city)


@router.get("/telemetry")
def get_mosdac_telemetry(city: Optional[str] = Query(None)) -> dict[str, Any]:
    """Unified telemetry payload for real-time nowcast fusion engine."""
    target_city = city or city_api.ACTIVE_CITY
    obs = GLOBAL_MOSDAC_CLIENT.get_latest_satellite_observation(target_city)
    return {
        "source": "ISRO_MOSDAC_INSAT3DS",
        "satellite": obs.get("satellite"),
        "sensor": obs.get("sensor"),
        "hydro_estimator_rain_rate_mmh": obs.get("hydro_estimator_rain_rate_mmh"),
        "cloud_top_temp_c": obs.get("cloud_top_temp_c"),
        "cloud_fraction_pct": obs.get("cloud_fraction_pct"),
        "convective_intensity": obs.get("convective_intensity"),
        "data_quality_flag": obs.get("data_quality_flag"),
        "timestamp_ist": obs.get("acquisition_time_ist"),
    }
