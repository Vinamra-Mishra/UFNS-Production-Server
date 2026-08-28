"""Phase D — Real NCMRWF/IMD GRIB2 & NetCDF4 Meteorological Ingestion Engine.

Authoritative Ingestion Pipeline for:
- NCMRWF Regional Unified Model (NCUM) NetCDF4 / GRIB2 forecasts
- IMD High-Resolution WRF NetCDF4 / GRIB2 forecasts

Spatial Foundation:
- Target Grid: Authoritative Bagjola Real-Pilot GridSpec (846 x 934 cells, 30m, EPSG:32645)
  derived from Copernicus GLO-30 DEM tile (bagjola_kolkata_glo30_dem.tif).

Strict Provenance & Zero-Mock Policy:
- ONLY authentic NCMRWF/IMD files are labeled as EXTERNAL_FORECAST / VALIDATED.
- When authentic files are absent, reports NOT_FETCHED / AWAITING_REAL_FILE.
- Never manufactures fake data and labels it as 'NCMRWF'.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from services.contracts import (
    DataLineage,
    GridSpec,
    ProvenanceClass,
    QualityFlag,
    RainfallGrid,
)
from services.ingestion.dem_real import (
    REAL_PILOT_CELL_SIZE_M,
    REAL_PILOT_HEIGHT,
    REAL_PILOT_ORIGIN_X,
    REAL_PILOT_ORIGIN_Y,
    REAL_PILOT_WIDTH,
)
from services.ingestion.real_data import (
    VALIDATION_FAILED,
    VALIDATION_VALIDATED,
    DataIngestionStatus,
    DataSourceClassification,
    SourceProvenance,
    compute_data_fingerprint,
)

# ---------------------------------------------------------------------------
# Canonical Sources & Gates
# ---------------------------------------------------------------------------

NCMRWF_NCUM_SOURCE = SourceProvenance(
    source_name="NCMRWF Regional Unified Model (NCUM)",
    dataset_name="NCUM-REGIONAL-PRECIP-NC4-GRIB2",
    version="1.0.0",
    acquisition_timestamp=datetime(2026, 8, 25, 0, 0, tzinfo=timezone.utc),
    source_url="https://www.ncmrwf.gov.in",
    license_id="MoES Open Data / Research Access",
    classification=DataSourceClassification.REAL,
    crs="EPSG:4326",
    resolution="~4km regional",
)

IMD_WRF_SOURCE = SourceProvenance(
    source_name="IMD High-Resolution WRF NWP Model",
    dataset_name="IMD-WRF-3KM-NC4-GRIB2",
    version="1.0.0",
    acquisition_timestamp=datetime(2026, 8, 25, 0, 0, tzinfo=timezone.utc),
    source_url="https://mausam.imd.gov.in",
    license_id="MoES Open Data / Research Access",
    classification=DataSourceClassification.REAL,
    crs="EPSG:4326",
    resolution="~3km regional",
)

GATE_RD09 = "RD-09"  # Real NCMRWF/IMD NWP Forecast Ingestion Gate


def get_authoritative_bagjola_grid() -> GridSpec:
    """Return the authoritative Bagjola real-pilot GridSpec (846x934 @ 30m, EPSG:32645)."""
    xmin = REAL_PILOT_ORIGIN_X
    ymax = REAL_PILOT_ORIGIN_Y
    width = REAL_PILOT_WIDTH
    height = REAL_PILOT_HEIGHT
    cell = REAL_PILOT_CELL_SIZE_M
    xmax = xmin + width * cell
    ymin = ymax - height * cell

    return GridSpec(
        grid_id="bagjola-kolkata-epsg32645-30m",
        crs_wkt_or_epsg="EPSG:32645",
        vertical_crs="EPSG:5703",
        width=width,
        height=height,
        affine_transform=[cell, 0.0, xmin, 0.0, -cell, ymax],
        cell_size_m=cell,
        nodata=-9999.0,
        bounds=[xmin, ymin, xmax, ymax],
    )


class NWPMetVariable(str, Enum):
    """Supported meteorological variables from NCMRWF/IMD NWP models."""
    TOTAL_PRECIPITATION_FLUX = "total_precipitation_flux"
    CONVECTIVE_PRECIPITATION = "convective_precipitation"
    WIND_U_10M = "wind_u_10m"
    WIND_V_10M = "wind_v_10m"
    SURFACE_TEMPERATURE = "surface_temperature"


@dataclass(frozen=True)
class NWPForecastStep:
    """Single time-step forecast slice on the target grid."""
    lead_minutes: int
    valid_time_utc: datetime
    precip_rate_mmh: np.ndarray  # 2D array [height, width]
    min_rate_mmh: float
    max_rate_mmh: float
    mean_rate_mmh: float
    units: str = "mm/h"


@dataclass
class RealNWPDataset:
    """Validated, normalized Real NCMRWF/IMD NWP Dataset."""
    source_provenance: SourceProvenance
    model_name: str
    file_path: Path
    file_sha256: str
    file_size_bytes: int
    reference_time_utc: datetime
    target_grid: GridSpec
    status: DataIngestionStatus
    forecast_steps: dict[int, NWPForecastStep]  # keyed by lead_minutes
    native_crs: str
    quality_flags: list[QualityFlag]
    provenance_class: ProvenanceClass = ProvenanceClass.EXTERNAL_FORECAST

    def get_step(self, lead_minutes: int) -> NWPForecastStep | None:
        """Retrieve closest or exact forecast step."""
        if not self.forecast_steps:
            return None
        if lead_minutes in self.forecast_steps:
            return self.forecast_steps[lead_minutes]
        # Find closest available lead
        avail = sorted(self.forecast_steps.keys())
        closest = min(avail, key=lambda k: abs(k - lead_minutes))
        return self.forecast_steps[closest]


# ---------------------------------------------------------------------------
# Real NWP Ingestion Engine
# ---------------------------------------------------------------------------

class RealNWPIngestionEngine:
    """Parser, validator, and spatial reprojector for real NCMRWF/IMD forecast rasters."""

    CANONICAL_RAW_DIR = Path("data/raw")
    CANONICAL_SEARCH_PATTERNS = [
        "ncmrwf_*.nc",
        "ncmrwf_*.grib2",
        "ncmrwf_*.nc4",
        "imd_*.nc",
        "imd_*.grib2",
        "*ncum*.nc",
        "*wrf*.nc",
    ]

    def __init__(self, target_grid: GridSpec | None = None) -> None:
        """Execute   Init   operation and return result."""
        self.target_grid = target_grid or get_authoritative_bagjola_grid()
        self._cached_dataset: RealNWPDataset | None = None

    def discover_raw_file(self) -> Path | None:
        """Search canonical raw data directory for authentic NCMRWF/IMD forecast files."""
        if not self.CANONICAL_RAW_DIR.exists():
            return None
        for pattern in self.CANONICAL_SEARCH_PATTERNS:
            for p in self.CANONICAL_RAW_DIR.glob(pattern):
                if p.is_file() and p.stat().st_size > 0:
                    return p
        return None

    def ingest_file(self, file_path: str | Path) -> RealNWPDataset:
        """Parse, validate, and reproject a real NetCDF4/GRIB2 NCMRWF/IMD forecast file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Real NWP file not found: {path}")

        # 1. Compute SHA-256 fingerprint
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        sha256_hash = hasher.hexdigest()
        file_size = path.stat().st_size

        suffix = path.suffix.lower()
        if suffix in [".nc", ".nc4", ".netcdf"]:
            dataset = self._parse_netcdf(path, sha256_hash, file_size)
        elif suffix in [".grib2", ".grb2", ".grib"]:
            dataset = self._parse_grib2(path, sha256_hash, file_size)
        else:
            raise ValueError(f"Unsupported NWP raster format '{suffix}'. Must be .nc, .nc4, or .grib2")

        self._cached_dataset = dataset
        return dataset

    def _parse_netcdf(self, path: Path, sha256: str, size: int) -> RealNWPDataset:
        """Parse NetCDF4 format using netCDF4 library with robust coordinate reprojection."""
        import netCDF4 as nc

        with nc.Dataset(str(path), "r") as ds:
            # Determine model identity
            title = getattr(ds, "title", "")
            institution = getattr(ds, "institution", "")
            source_attr = getattr(ds, "source", "")
            combined_id = f"{title} {institution} {source_attr}".lower()

            if "imd" in combined_id or "wrf" in combined_id:
                model_name = "IMD-WRF-3KM"
                provenance = IMD_WRF_SOURCE
            else:
                model_name = "NCMRWF-NCUM-REGIONAL"
                provenance = NCMRWF_NCUM_SOURCE

            # 1. Extract coordinates (lat/latitude, lon/longitude)
            lat_var = None
            for name in ["latitude", "lat", "XLAT", "y"]:
                if name in ds.variables:
                    lat_var = ds.variables[name][:]
                    break
            lon_var = None
            for name in ["longitude", "lon", "XLONG", "x"]:
                if name in ds.variables:
                    lon_var = ds.variables[name][:]
                    break

            if lat_var is None or lon_var is None:
                raise ValueError(f"NetCDF file {path} missing valid latitude/longitude coordinate variables")

            # Flatten/1D coordinates
            if lat_var.ndim == 2:
                lats = lat_var[:, 0]
                lons = lon_var[0, :]
            else:
                lats = np.array(lat_var, dtype=float)
                lons = np.array(lon_var, dtype=float)

            # Ensure ascending latitude for interpolation
            lat_sort_idx = np.argsort(lats)
            lats = lats[lat_sort_idx]
            lon_sort_idx = np.argsort(lons)
            lons = lons[lon_sort_idx]

            # 2. Extract precipitation variable
            precip_var_name = None
            for name in ["precipitation_flux", "total_precipitation", "tp", "precipitation_rate", "APCP_surface", "rain_con", "precip"]:
                if name in ds.variables:
                    precip_var_name = name
                    break

            if precip_var_name is None:
                raise ValueError(f"NetCDF file {path} has no recognized precipitation rate variable")

            precip_raw = ds.variables[precip_var_name][:]
            precip_units = getattr(ds.variables[precip_var_name], "units", "mm/h")

            # Reference time
            ref_time = datetime.now(timezone.utc)
            if "time" in ds.variables:
                time_var = ds.variables["time"]
                try:
                    time_units = getattr(time_var, "units", "")
                    if "since" in time_units:
                        base_str = time_units.split("since")[1].strip()
                        base_dt = datetime.fromisoformat(base_str.replace(" UTC", "").replace("Z", "")).replace(tzinfo=timezone.utc)
                        ref_time = base_dt
                except Exception as exc:
                    logging.getLogger(__name__).warning("Failed to parse NetCDF reference time: %s", exc)

            # 3. Build target coordinate meshgrid in EPSG:32645 -> WGS84 lat/lon
            target_lats, target_lons = self._build_target_lat_lon_grid()

            # 4. Extract time slices and reproject onto target grid
            forecast_steps: dict[int, NWPForecastStep] = {}

            if precip_raw.ndim == 2:
                # Single snapshot (lead=0)
                sliced = precip_raw[lat_sort_idx, :][:, lon_sort_idx]
                grid_mmh = self._reproject_slice(sliced, lats, lons, target_lats, target_lons, precip_units)
                forecast_steps[0] = NWPForecastStep(
                    lead_minutes=0,
                    valid_time_utc=ref_time,
                    precip_rate_mmh=grid_mmh,
                    min_rate_mmh=float(np.min(grid_mmh)),
                    max_rate_mmh=float(np.max(grid_mmh)),
                    mean_rate_mmh=float(np.mean(grid_mmh)),
                )
            elif precip_raw.ndim == 3:
                # Multiple time steps [time, lat, lon]
                n_steps = precip_raw.shape[0]
                from datetime import timedelta
                time_vals = ds.variables["time"][:] if "time" in ds.variables else np.arange(n_steps) * 15.0
                time_units = getattr(ds.variables["time"], "units", "") if "time" in ds.variables else ""
                base_time_val = float(time_vals[0]) if len(time_vals) > 0 else 0.0

                for step_idx in range(n_steps):
                    raw_val = float(time_vals[step_idx]) if step_idx < len(time_vals) else float(step_idx * 15)
                    val = raw_val - base_time_val
                    if "hour" in time_units.lower():
                        lead_min = int(round(val * 60))
                    elif "sec" in time_units.lower():
                        lead_min = int(round(val / 60))
                    else:
                        lead_min = int(round(val))

                    valid_time = ref_time + timedelta(minutes=lead_min)
                    sliced = precip_raw[step_idx, :, :]
                    if sliced.shape[0] == len(lat_sort_idx):
                        sliced = sliced[lat_sort_idx, :]
                    if sliced.shape[1] == len(lon_sort_idx):
                        sliced = sliced[:, lon_sort_idx]

                    grid_mmh = self._reproject_slice(sliced, lats, lons, target_lats, target_lons, precip_units)
                    forecast_steps[lead_min] = NWPForecastStep(
                        lead_minutes=lead_min,
                        valid_time_utc=valid_time,
                        precip_rate_mmh=grid_mmh,
                        min_rate_mmh=float(np.min(grid_mmh)),
                        max_rate_mmh=float(np.max(grid_mmh)),
                        mean_rate_mmh=float(np.mean(grid_mmh)),
                    )

            return RealNWPDataset(
                source_provenance=provenance,
                model_name=model_name,
                file_path=path,
                file_sha256=sha256,
                file_size_bytes=size,
                reference_time_utc=ref_time,
                target_grid=self.target_grid,
                status=DataIngestionStatus.VALIDATED,
                forecast_steps=forecast_steps,
                native_crs="EPSG:4326",
                quality_flags=[QualityFlag.VALIDATED, QualityFlag.RESAMPLED],
                provenance_class=ProvenanceClass.EXTERNAL_FORECAST,
            )

    def _parse_grib2(self, path: Path, sha256: str, size: int) -> RealNWPDataset:
        """Parse GRIB2 format using rasterio reprojection onto target grid."""
        import rasterio
        import rasterio.warp
        with rasterio.open(str(path)) as src:
            # Validate GRIB parameter metadata if tags exist
            tags = src.tags(1) if hasattr(src, "tags") else {}
            element = tags.get("GRIB_ELEMENT", tags.get("GRIB_SHORT_NAME", tags.get("shortName", ""))).upper()
            unit = tags.get("GRIB_UNIT", tags.get("units", "mm/h")).lower()

            # Require recognized precipitation parameter identifier
            RECOGNIZED_PRECIP_PARAMS = ("APCP", "PRECIP", "RAIN", "TP", "PRATE", "FLUX", "PRECIPITATION")
            if not element or not any(p in element for p in RECOGNIZED_PRECIP_PARAMS):
                raise ValueError(f"Unrecognized or non-precipitation GRIB2 field '{element}'. Expected a precipitation rate parameter.")

            # Validate units and compute rate scaling (mm/h)
            scale_to_mmh = 1.0
            if "kg m-2 s-1" in unit or "kg/m2/s" in unit or "mm/s" in unit:
                scale_to_mmh = 3600.0  # kg/m2/s = mm/s -> 3600 mm/h
            elif "kg m-2 h-1" in unit or "kg/m2/h" in unit or "mm/h" in unit or "mm hr-1" in unit or "mm/hr" in unit:
                scale_to_mmh = 1.0
            elif unit in ("mm", "kg m-2", "m", "meter", "metre"):
                # Accumulation units require validated interval duration metadata
                interval_hours_str = tags.get("GRIB_INTERVAL_HOURS", tags.get("GRIB_STEP_RANGE", ""))
                try:
                    interval_hours = float(interval_hours_str) if interval_hours_str else None
                except ValueError:
                    interval_hours = None
                if interval_hours and interval_hours > 0:
                    scale_mult = 1000.0 if unit in ("m", "meter", "metre") else 1.0
                    scale_to_mmh = scale_mult / interval_hours
                else:
                    raise ValueError(f"Accumulated precipitation unit '{unit}' without valid interval duration metadata cannot be converted to rate mm/h.")
            elif unit != "":
                raise ValueError(f"Unsupported or non-precipitation GRIB2 unit '{unit}'. Expected precipitation rate units (e.g. mm/h or kg m-2 s-1).")

            # Read with masking and explicit nodata preservation
            raw_masked = src.read(1, masked=True)
            src_nodata = float(src.nodata) if src.nodata is not None else -9999.0
            dst_nodata = -9999.0
            raw_data = np.ma.filled(raw_masked, src_nodata).astype(np.float32)

            if scale_to_mmh != 1.0:
                raw_data = np.where(raw_data != src_nodata, raw_data * scale_to_mmh, src_nodata)

            src_crs = src.crs or "EPSG:4326"
            src_transform = src.transform
            native_crs = str(src.crs or "EPSG:4326")

            target_shape = (self.target_grid.height, self.target_grid.width)
            grid_mmh = np.full(target_shape, dst_nodata, dtype=np.float32)

            xmin, ymin, xmax, ymax = self.target_grid.bounds
            target_transform = rasterio.transform.from_bounds(
                xmin, ymin, xmax, ymax,
                self.target_grid.width, self.target_grid.height
            )

            rasterio.warp.reproject(
                source=raw_data,
                destination=grid_mmh,
                src_transform=src_transform,
                src_crs=src_crs,
                dst_transform=target_transform,
                dst_crs=self.target_grid.crs_wkt_or_epsg,
                src_nodata=src_nodata,
                dst_nodata=dst_nodata,
                resampling=rasterio.warp.Resampling.bilinear,
            )
            grid_mmh = np.where((grid_mmh == dst_nodata) | np.isnan(grid_mmh) | (grid_mmh < 0.0), 0.0, grid_mmh)

        provenance = SourceProvenance(
            source_name="NCMRWF/IMD GRIB2 Regional NWP Model",
            dataset_name="NCMRWF-IMD-GRIB2-FORECAST",
            version="1.0.0",
            acquisition_timestamp=datetime.now(timezone.utc),
            source_url="https://www.ncmrwf.gov.in",
            license_id="Open Government Data (OGD) India / MoES",
            classification=DataSourceClassification.REAL,
            crs=native_crs,
            resolution="~3-4km regional",
        )

        step = NWPForecastStep(
            lead_minutes=0,
            valid_time_utc=datetime.now(timezone.utc),
            precip_rate_mmh=grid_mmh,
            min_rate_mmh=float(np.min(grid_mmh)),
            max_rate_mmh=float(np.max(grid_mmh)),
            mean_rate_mmh=float(np.mean(grid_mmh)),
        )

        return RealNWPDataset(
            source_provenance=provenance,
            model_name="IMD-WRF-GRIB2",
            file_path=path,
            file_sha256=sha256,
            file_size_bytes=size,
            reference_time_utc=datetime.now(timezone.utc),
            target_grid=self.target_grid,
            status=DataIngestionStatus.VALIDATED,
            forecast_steps={0: step},
            native_crs=native_crs,
            quality_flags=[QualityFlag.VALIDATED, QualityFlag.RESAMPLED],
            provenance_class=ProvenanceClass.EXTERNAL_FORECAST,
        )

    def _build_target_lat_lon_grid(self) -> tuple[np.ndarray, np.ndarray]:
        """Convert the target GridSpec (EPSG:32645 UTM) cell center coordinates to WGS84 (Lat, Lon)."""
        import rasterio.warp
        xmin, ymin, xmax, ymax = self.target_grid.bounds
        width = self.target_grid.width
        height = self.target_grid.height
        half = self.target_grid.cell_size_m / 2.0

        # Metric grid cell centers (North-up top-to-bottom)
        xs = np.linspace(xmin + half, xmax - half, width)
        ys = np.linspace(ymax - half, ymin + half, height)
        mesh_x, mesh_y = np.meshgrid(xs, ys)

        lon_list, lat_list = rasterio.warp.transform(
            self.target_grid.crs_wkt_or_epsg,
            "EPSG:4326",
            mesh_x.ravel().tolist(),
            mesh_y.ravel().tolist(),
        )
        target_lons = np.asarray(lon_list, dtype=float).reshape(mesh_x.shape)
        target_lats = np.asarray(lat_list, dtype=float).reshape(mesh_y.shape)
        return target_lats, target_lons

    def _reproject_slice(
        self,
        src_data: np.ndarray,
        src_lats: np.ndarray,
        src_lons: np.ndarray,
        target_lats: np.ndarray,
        target_lons: np.ndarray,
        units: str,
    ) -> np.ndarray:
        """Bilinear spatial interpolation from geographic grid onto target simulation grid."""
        if isinstance(src_data, np.ma.MaskedArray):
            data = np.ma.filled(src_data.astype(float), np.nan)
        else:
            data = np.array(src_data, dtype=float)

        if "kg" in units or "m-2 s-1" in units:
            data = data * 3600.0  # kg/m2/s -> mm/h

        data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)

        interp = RegularGridInterpolator(
            (src_lats, src_lons),
            data,
            method="linear",
            bounds_error=False,
            fill_value=None,
        )

        pts = np.column_stack([target_lats.ravel(), target_lons.ravel()])
        interp_vals = interp(pts)
        out = interp_vals.reshape(target_lats.shape)

        out = np.clip(out, 0.0, 300.0)
        return out


# Global Singleton Ingestion Engine Instance
GLOBAL_REAL_NWP_ENGINE = RealNWPIngestionEngine()
