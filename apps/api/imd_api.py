"""India Meteorological Department (IMD) FastAPI Endpoints.

Exposes REST APIs for all 20 official IMD public data streams:
- City Forecast 7-Day & Lat/Lon
- Synoptic Current Weather (MSLP, Wind, Humidity, Weather Codes 01-99)
- District 3-Hour Nowcasts & 5-Day Multi-Hazard Warnings
- AWS/ARG Automated Weather Stations
- River Basin QPF (Quantitative Precipitation Forecast)
- Marine, Port, Sea and Coastal Bulletins
- Astronomical Ephemeris (Sun & Moon Rise/Set)
- Live Cyclone Tracking, Wind Radii, and Cone of Uncertainty
"""

from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, Query

from services.ingestion.imd_client import (
    GLOBAL_IMD_CLIENT,
    CITY_STATION_MAP,
    WEATHER_CODES,
    WIND_DIRECTIONS,
    WARNING_CODES,
    WARNING_COLOR_CODES,
    _resolve_city_key,
)
from apps.api import city_api

router = APIRouter(prefix="/api/v1/imd", tags=["IMD Meteorological Feeds"])


@router.get("/overview")
def get_imd_overview(city: Optional[str] = Query(None)) -> dict[str, Any]:
    """Get aggregated official IMD meteorological dossier for the active/requested city."""
    target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
    return GLOBAL_IMD_CLIENT.get_unified_city_overview(target_city)


@router.get("/city-forecast")
def get_city_forecast(
    station_id: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
) -> dict[str, Any]:
    """1. 7-Day City Weather Forecast."""
    if not station_id:
        target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
        meta = CITY_STATION_MAP[target_city]
        station_id = meta["city_station_id"]
    return GLOBAL_IMD_CLIENT.get_city_forecast(station_id)


@router.get("/city-forecast-loc")
def get_city_forecast_loc(
    station_id: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
) -> dict[str, Any]:
    """2. 7-Day City Weather Forecast with Latitude and Longitude."""
    if not station_id:
        target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
        meta = CITY_STATION_MAP[target_city]
        station_id = meta["city_station_id"]
    return GLOBAL_IMD_CLIENT.get_city_forecast_loc(station_id)


@router.get("/current-weather")
def get_current_weather(
    station_id: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
) -> dict[str, Any]:
    """3. Current Synoptic Weather (MSLP, Wind Speed & Dir, Temp, Humidity, Weather Code)."""
    if not station_id:
        target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
        meta = CITY_STATION_MAP[target_city]
        station_id = meta["city_station_id"]
    return GLOBAL_IMD_CLIENT.get_current_weather(station_id)


@router.get("/district-nowcast")
def get_district_nowcast(
    district_id: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
) -> dict[str, Any]:
    """4. District-wise Nowcast (3-Hour Lead Warnings with Color Severity Codes)."""
    if not district_id:
        target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
        meta = CITY_STATION_MAP[target_city]
        district_id = meta["district_id"]
    return GLOBAL_IMD_CLIENT.get_district_nowcast(district_id)


@router.get("/district-rainfall")
def get_district_rainfall(
    district_id: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
) -> dict[str, Any]:
    """5. District-wise Daily, Weekly, and Cumulative Rainfall Departures."""
    if not district_id:
        target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
        meta = CITY_STATION_MAP[target_city]
        district_id = meta["district_id"]
    return GLOBAL_IMD_CLIENT.get_district_rainfall(district_id)


@router.get("/district-warnings")
def get_district_warnings(
    district_id: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
) -> dict[str, Any]:
    """6. District-wise 5-Day Hazard Warnings Matrix."""
    if not district_id:
        target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
        meta = CITY_STATION_MAP[target_city]
        district_id = meta["district_id"]
    return GLOBAL_IMD_CLIENT.get_district_warnings(district_id)


@router.get("/station-nowcast")
def get_station_nowcast(
    station_name: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
) -> dict[str, Any]:
    """7. Station-wise Nowcast Alerts."""
    if station_name:
        return GLOBAL_IMD_CLIENT.get_station_nowcast(station_name)
    target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
    meta = CITY_STATION_MAP[target_city]
    return GLOBAL_IMD_CLIENT.get_station_nowcast(meta["station_name"])


@router.get("/state-rainfall")
def get_state_rainfall(
    state: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
) -> dict[str, Any]:
    """8. State-wise Rainfall Actual vs Normal."""
    if state:
        return GLOBAL_IMD_CLIENT.get_state_rainfall(state)
    target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
    meta = CITY_STATION_MAP[target_city]
    return GLOBAL_IMD_CLIENT.get_state_rainfall(meta["state_name"])


@router.get("/aws-stations")
def get_aws_stations(
    call_sign: Optional[str] = Query(None),
    state_id: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
) -> dict[str, Any]:
    """9. AWS/ARG Automated Weather Station Observations."""
    if call_sign or state_id:
        return GLOBAL_IMD_CLIENT.get_aws_data(call_sign=call_sign, state_id=state_id)
    target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
    return GLOBAL_IMD_CLIENT.get_aws_data(call_sign=target_city)



@router.get("/basin-qpf")
def get_basin_qpf(
    basin_id: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
) -> dict[str, Any]:
    """10. River Basin Quantitative Precipitation Forecast (QPF)."""
    target_key = basin_id or city or city_api.ACTIVE_CITY
    return GLOBAL_IMD_CLIENT.get_basin_qpf(target_key)


@router.get("/port-warnings")
def get_port_warnings(
    port_id: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
) -> dict[str, Any]:
    """11. Port Signals & Weather Warnings."""
    target_key = port_id or city or city_api.ACTIVE_CITY
    return GLOBAL_IMD_CLIENT.get_port_warnings(target_key)


@router.get("/sea-bulletin")
def get_sea_bulletin(
    bulletin_id: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
) -> dict[str, Any]:
    """12. Marine Sea Area Bulletin."""
    target_key = bulletin_id or city or city_api.ACTIVE_CITY
    return GLOBAL_IMD_CLIENT.get_sea_bulletin(target_key)


@router.get("/coastal-bulletin")
def get_coastal_bulletin(city: Optional[str] = Query(None)) -> dict[str, Any]:
    """13. Coastal Weather & Sea Condition Bulletin."""
    target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
    return GLOBAL_IMD_CLIENT.get_coastal_bulletin(target_city)


@router.get("/subdivision-warnings")
def get_subdivision_warnings(city: Optional[str] = Query(None)) -> dict[str, Any]:
    """14. Subdivisional-wise 5-Day Warnings."""
    target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
    return GLOBAL_IMD_CLIENT.get_subdivision_warnings(target_city)


@router.get("/sun-moon")
def get_sun_moon(
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
    city: Optional[str] = Query(None),
) -> dict[str, Any]:
    """15. Sun & Moon Rise/Set Ephemeris (IST)."""
    if lat is None or lon is None:
        target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
        meta = CITY_STATION_MAP[target_city]
        lat = meta["lat"]
        lon = meta["lon"]
    return GLOBAL_IMD_CLIENT.get_sun_moon(lat, lon)


@router.get("/subdivision-rainfall-forecast")
def get_subdivision_rainfall_forecast(city: Optional[str] = Query(None)) -> dict[str, Any]:
    """16. Subdivisional Rainfall Forecast (7-Days)."""
    target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
    return GLOBAL_IMD_CLIENT.get_subdivision_rainfall_forecast(target_city)


@router.get("/state-district-rainfall-forecast")
def get_state_district_rainfall_forecast(city: Optional[str] = Query(None)) -> dict[str, Any]:
    """17. State District Rainfall Forecast (5-Days)."""
    target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
    return GLOBAL_IMD_CLIENT.get_state_district_rainfall_forecast(target_city)


@router.get("/cyclone/track")
def get_cyclone_track(city: Optional[str] = Query(None)) -> dict[str, Any]:
    """18. Live Cyclone Observed & Forecast Tracks."""
    target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
    return GLOBAL_IMD_CLIENT.get_cyclone_track(target_city)


@router.get("/cyclone/wind")
def get_cyclone_wind(city: Optional[str] = Query(None)) -> dict[str, Any]:
    """19. Cyclone Wind Warning Polygons (27kt, 34kt, 50kt, 64kt)."""
    target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
    return GLOBAL_IMD_CLIENT.get_cyclone_wind(target_city)


@router.get("/cyclone/cou")
def get_cyclone_cou(city: Optional[str] = Query(None)) -> dict[str, Any]:
    """20. Cyclone Cone of Uncertainty (CoU) Polygon."""
    target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
    return GLOBAL_IMD_CLIENT.get_cyclone_cou(target_city)


@router.get("/cyclone/bundle")
def get_cyclone_bundle(city: Optional[str] = Query(None)) -> dict[str, Any]:
    """Aggregated Cyclone Emergency Package (Tracks + Wind Radii + Cone of Uncertainty)."""
    target_city = _resolve_city_key(city or city_api.ACTIVE_CITY)
    track = GLOBAL_IMD_CLIENT.get_cyclone_track(target_city)
    wind = GLOBAL_IMD_CLIENT.get_cyclone_wind(target_city)
    cou = GLOBAL_IMD_CLIENT.get_cyclone_cou(target_city)
    return {
        "status": "ACTIVE_SURVEILLANCE",
        "city": target_city,
        "cyclone_track": track,
        "cyclone_wind": wind,
        "cone_of_uncertainty": cou,
    }


@router.get("/reference/codes")
def get_reference_codes() -> dict[str, Any]:
    """Get IMD Weather Codes (01-99), Wind Direction, and Warning Severity definitions."""
    return {
        "weather_codes": WEATHER_CODES,
        "wind_directions": WIND_DIRECTIONS,
        "warning_codes": WARNING_CODES,
        "warning_color_codes": WARNING_COLOR_CODES,
    }
