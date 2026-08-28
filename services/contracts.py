"""Core typed data contracts (IMPLEMENTATION_SPEC §6, ARCHITECTURE §7).

Executable source of truth for all UFNS data exchange. Every spatial object
identifies CRS, resolution, units, timestamp, provenance. Every forecast
identifies initialization time, valid time, horizon, model version, source.

Units: external rainfall mm/h; solver rainfall m/s; depth m; volume m^3;
Manning n s/m^(1/3). Timestamps are timezone-aware UTC RFC 3339.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "0.1.0"


# --------------------------------------------------------------------------
# Provenance and quality
# --------------------------------------------------------------------------

class ProvenanceClass(str, Enum):
    """IMPLEMENTATION_SPEC §3.2 + ARCHITECTURE §1 provenance vocabulary."""

    OBSERVED_REALTIME = "OBSERVED_REALTIME"
    OBSERVED_HISTORICAL = "OBSERVED_HISTORICAL"
    EXTERNAL_FORECAST = "EXTERNAL_FORECAST"
    SIMULATED_SCENARIO = "SIMULATED_SCENARIO"
    SYNTHETIC = "SYNTHETIC"          # generated fixture data (not from any real source)
    STATIC_REFERENCE = "STATIC_REFERENCE"
    MODEL_PREDICTION = "MODEL_PREDICTION"
    DERIVED = "DERIVED"


class QualityFlag(str, Enum):
    """Qualityflag schema and data model representation."""
    VALIDATED = "VALIDATED"
    ASSUMED_PARAMETER = "ASSUMED_PARAMETER"
    RESAMPLED = "RESAMPLED"
    STALE = "STALE"
    MISSING_VALUES = "MISSING_VALUES"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    UNVALIDATED_SOURCE = "UNVALIDATED_SOURCE"
    SYNTHETIC = "SYNTHETIC"
    PROVISIONAL = "PROVISIONAL"      # pending scientific review (e.g. D-016 hyetographs)


class DataLineage(BaseModel):
    """ARCHITECTURE §7.1."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    version: str
    source_name: str
    source_url: Optional[str] = None
    licence_id: Optional[str] = None
    acquired_at: datetime
    content_sha256: str = Field(min_length=64, max_length=64)
    provenance_class: ProvenanceClass
    quality_flags: list[QualityFlag] = []
    native_crs: Optional[str] = None
    native_resolution: Optional[dict[str, Any]] = None  # {"x": float, "y": float, "unit": str}
    processing_steps: list[str] = []

    @field_validator("acquired_at")
    @classmethod
    def _aware_utc(cls, v: datetime) -> datetime:
        """Execute  Aware Utc operation and return result."""
        if v.tzinfo is None:
            raise ValueError("acquired_at must be timezone-aware")
        return v.astimezone(timezone.utc)


class GridSpec(BaseModel):
    """ARCHITECTURE §7.2. One canonical grid per pilot bundle."""

    model_config = ConfigDict(extra="forbid")

    grid_id: str
    crs_wkt_or_epsg: str
    vertical_crs: Optional[str] = None
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    affine_transform: list[float] = Field(min_length=6, max_length=6)
    cell_size_m: float = Field(gt=0)
    nodata: Optional[float] = None
    bounds: list[float] = Field(min_length=4, max_length=4)  # xmin, ymin, xmax, ymax

    @property
    def n_cells(self) -> int:
        """Execute N Cells operation and return result."""
        return self.width * self.height


class RainfallGrid(BaseModel):
    """ARCHITECTURE §7.2. Field represents mean rate over [valid_from, valid_to)."""

    model_config = ConfigDict(extra="forbid")

    rainfall_id: str
    issue_time: datetime
    valid_from: datetime
    valid_to: datetime
    lead_minutes: int = Field(ge=0)
    grid: GridSpec
    variable: Literal["rainfall_rate"] = "rainfall_rate"
    units_external: Literal["mm/h"] = "mm/h"
    units_solver: Literal["m/s"] = "m/s"
    source_resolution: Optional[dict[str, Any]] = None
    source: DataLineage
    confidence: Optional[float] = None  # null unless a defensible method creates it
    asset_uri: str

    @model_validator(mode="after")
    def _check_interval(self) -> "RainfallGrid":
        """Execute  Check Interval operation and return result."""
        if self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be strictly after valid_from")
        if self.valid_from.tzinfo is None or self.valid_to.tzinfo is None or self.issue_time.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be in [0, 1]")
        return self


# --------------------------------------------------------------------------
# Scenarios (IMPLEMENTATION_SPEC §7)
# --------------------------------------------------------------------------

class RainfallProfile(BaseModel):
    """A time series of rainfall intensity steps, mm/h (external units).

    The derivation of every profile must be documented (B03/D-016):
    `derivation` names the method and reference; `review_status` is
    PROVISIONAL until a hydrologist approves the parameters.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    derivation: str                      # named method + citation
    review_status: Literal["PROVISIONAL", "APPROVED", "REJECTED"] = "PROVISIONAL"
    interval_minutes: int = Field(gt=0)
    intensities_mmh: list[float] = Field(min_length=1)  # one value per interval

    @field_validator("intensities_mmh")
    @classmethod
    def _nonnegative(cls, v: list[float]) -> list[float]:
        """Execute  Nonnegative operation and return result."""
        import math
        if not all(isinstance(x, (int, float)) for x in v):
            raise ValueError("intensities must be numeric")
        if any(not math.isfinite(x) for x in v):
            raise ValueError("rainfall intensities must be finite")
        if any(x < 0 for x in v):
            raise ValueError("rainfall intensities must be non-negative")
        return v


class BlockageConfiguration(BaseModel):
    """Drainage blockage overrides for a scenario (0 = clear, 1 = fully blocked)."""

    model_config = ConfigDict(extra="forbid")

    blocked_links: list[str] = []
    fraction: float = Field(ge=0.0, le=1.0)
    start_minutes: int = Field(ge=0)
    end_minutes: Optional[int] = None  # None = until end of run
    implementation_note: str = "effective-opening reduction; hydraulic change, not a UI label"


class DrainageConfiguration(BaseModel):
    """Drainageconfiguration schema and data model representation."""
    model_config = ConfigDict(extra="forbid")

    network_asset_uri: str
    parameter_status: dict[str, Literal["measured", "published", "derived", "assumed"]] = {}
    blockage: Optional[BlockageConfiguration] = None


class SurfaceParameters(BaseModel):
    """Loss/roughness parameters. All provisional until reviewer approval."""

    model_config = ConfigDict(extra="forbid")

    manning_n: float = Field(gt=0)
    horton_f0_m_s: float = Field(ge=0)
    horton_fmin_m_s: float = Field(ge=0)
    horton_k_s1: float = Field(gt=0)
    depression_storage_m: float = Field(ge=0)
    review_status: Literal["PROVISIONAL", "APPROVED"] = "PROVISIONAL"


class ScenarioDefinition(BaseModel):
    """IMPLEMENTATION_SPEC §7. A scenario must be reproducible."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    name: str
    description: str
    rainfall_source: Literal["demo", "live", "historical"] = "demo"
    rainfall_profile: RainfallProfile
    spatial_pattern: Literal["uniform", "convective_cell", "custom"] = "uniform"
    duration_minutes: int = Field(gt=0)
    issue_time: datetime
    initial_conditions: dict[str, Any] = {"surface_depth_m": 0.0}
    drainage_configuration: Optional[DrainageConfiguration] = None
    surface_parameters: SurfaceParameters
    simulation_grid: GridSpec
    simulation_timestep_s: Optional[float] = None  # None = solver-adaptive
    random_seed: Optional[int] = None
    provenance: DataLineage

    @field_validator("issue_time")
    @classmethod
    def _aware_utc(cls, v: datetime) -> datetime:
        """Execute  Aware Utc operation and return result."""
        if v.tzinfo is None:
            raise ValueError("issue_time must be timezone-aware")
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _check_duration(self) -> "ScenarioDefinition":
        """Execute  Check Duration operation and return result."""
        n_intervals = self.duration_minutes // self.rainfall_profile.interval_minutes
        if n_intervals < 1:
            raise ValueError("scenario duration must cover at least one rainfall interval")
        return self

    def fingerprint(self, extra: Optional[dict[str, Any]] = None) -> str:
        """Deterministic run fingerprint: hashes scenario + parameters + versions."""
        payload = self.model_dump(mode="json")
        payload["schema_version"] = SCHEMA_VERSION
        if extra:
            payload["extra"] = extra
        canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Terrain, outputs, ledger
# --------------------------------------------------------------------------

class TerrainBundle(BaseModel):
    """ARCHITECTURE §7.3 (minimal M1 fields)."""

    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    grid: GridSpec
    dem_asset_uri: str
    dem_units: Literal["m"] = "m"
    vertical_reference: str  # e.g. "SYNTHETIC_LOCAL_DATUM" or "EGM2008"
    roughness_asset_uri: Optional[str] = None
    roughness_units: Optional[Literal["s/m^(1/3)"]] = None
    infiltration_parameter_asset_uris: Optional[dict[str, str]] = None
    depression_storage_asset_uri: Optional[str] = None
    source_lineage: list[DataLineage]
    conditioning_report_uri: Optional[str] = None


class MassBalance(BaseModel):
    """ARCHITECTURE §7.7. Whole-system ledger; exchange cancels internally."""

    model_config = ConfigDict(extra="forbid")

    interval_start: datetime
    interval_end: datetime
    rainfall_input_m3: float
    external_inflow_m3: float = 0.0
    infiltration_loss_m3: float = 0.0
    surface_boundary_outflow_m3: float = 0.0
    drainage_outfall_m3: float = 0.0
    initial_surface_storage_m3: float = 0.0
    final_surface_storage_m3: float = 0.0
    initial_drain_storage_m3: float = 0.0
    final_drain_storage_m3: float = 0.0
    residual_m3: float = 0.0
    relative_error: Optional[float] = None
    status: Literal["pass", "warning", "fail"]

    @model_validator(mode="after")
    def _finite(cls_self) -> "MassBalance":
        """Execute  Finite operation and return result."""
        import math

        for name in type(cls_self).model_fields:
            v = getattr(cls_self, name)
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                raise ValueError(f"{name} must be finite")
        return cls_self


class SimulationRun(BaseModel):
    """ARCHITECTURE §7.7 + IMPLEMENTATION_SPEC §6 run abstraction."""

    model_config = ConfigDict(extra="forbid")

    simulation_id: str
    created_at: datetime
    forecast_issue_time: datetime
    mode: Literal["demo", "live"] = "demo"
    scenario_id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    model_versions: dict[str, str] = {}
    input_dataset_versions: dict[str, str] = {}
    parameters: dict[str, Any] = {}
    output_manifest_uri: Optional[str] = None
    failure: Optional[dict[str, Any]] = None
    # --- M4 extensions (additive; defaults keep M1 contracts valid) ---------
    run_id: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    simulation_timestep_s: Optional[float] = None      # surface solver step (adaptive)
    coupling_timestep_s: Optional[int] = None          # dt_c (integer seconds)
    output_interval_minutes: Optional[int] = None
    grid_spec: Optional[GridSpec] = None
    rainfall_source: str = "demo"
    surface_model: str = "landlab_overlandflow_dealmeida2012"
    drainage_model: str = "epa_swmm_5_2_dynamic_wave"
    coupling_model: str = "signed_head_driven_orifice"
    configuration_fingerprint: str = ""
    input_manifest: dict[str, Any] = {}
    model_version: str = SCHEMA_VERSION


class DrainageStateSummary(BaseModel):
    """Per-snapshot drainage state (M4). Units: m, m3, m3/s."""

    model_config = ConfigDict(extra="forbid")

    st1_head_m: float
    st1_depth_m: float
    vent_depth_m: float
    vent_head_m: float
    outfall_cum_m3: float
    flooding_cum_m3: float
    exchange_S2D_cum_m3: float
    exchange_D2S_cum_m3: float
    surcharged: bool  # ST1 head above the mapped vent ground level


class FloodSnapshot(BaseModel):
    """IMPLEMENTATION_SPEC §7: time-indexed flood state.

    Depth is always h = max(0, η − z) (MODEL_ASSUMPTIONS §9). Flood extent is
    derived from depth with an explicit, configurable, non-safety threshold
    (`extent_threshold_m`). Bulk depth arrays live in artifacts (GeoTIFF/NetCDF);
    this model carries per-snapshot statistics and state for API/UI use.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    simulation_id: str
    run_id: str
    valid_time: datetime
    lead_minutes: int
    grid: GridSpec
    depth_asset_uri: Optional[str] = None
    max_depth_m: float = Field(ge=0.0)
    mean_depth_m: float = Field(ge=0.0)
    flooded_cells: int = Field(ge=0)
    flooded_area_m2: float = Field(ge=0.0)
    extent_threshold_m: float = Field(gt=0.0)
    total_surface_storage_m3: float = Field(ge=0.0)
    drainage: DrainageStateSummary
    provenance_class: ProvenanceClass = ProvenanceClass.MODEL_PREDICTION
    quality_flags: list[QualityFlag] = []

    @field_validator("valid_time")
    @classmethod
    def _aware_utc(cls, v: datetime) -> datetime:
        """Execute  Aware Utc operation and return result."""
        if v.tzinfo is None:
            raise ValueError("valid_time must be timezone-aware")
        return v.astimezone(timezone.utc)


# --------------------------------------------------------------------------
# Multi-City Spatial & Pilot Registry
# --------------------------------------------------------------------------

DEFAULT_CITY = "DEMO"

CITY_METADATA: dict[str, dict[str, Any]] = {
    "MUMBAI": {
        "city_id": "mumbai",
        "name": "Mumbai Metropolitan Region",
        "state": "Maharashtra",
        "crs": "EPSG:32643",
        "utm_zone": "43N",
        "bbox": [72.75, 18.88, 72.98, 19.28],
        "dem_cells": [825, 1486],
        "resolution_m": 30.0,
        "drainage_junctions": 1822,
        "drainage_conduits": 916,
        "road_nodes": 3440,
        "road_edges": 2000,
        "has_coastal_surge": True,
        "has_riverine_flood": False,
        "live_radar_station": "Mumbai (Colaba S-band / Veravali X-band)",
        "provenance_status": "OPERATIONAL_PRODUCTION",
    },
    "VIJAYAWADA": {
        "city_id": "vijayawada",
        "name": "Vijayawada Urban Area (Krishna Basin)",
        "state": "Andhra Pradesh",
        "crs": "EPSG:32644",
        "utm_zone": "44N",
        "bbox": [80.55, 16.45, 80.72, 16.58],
        "dem_cells": [606, 481],
        "resolution_m": 30.0,
        "drainage_junctions": 162,
        "drainage_conduits": 86,
        "road_nodes": 1200,
        "road_edges": 850,
        "has_coastal_surge": False,
        "has_riverine_flood": True,
        "live_radar_station": "Machilipatnam DWR (55km east)",
        "provenance_status": "OPERATIONAL_PRODUCTION",
    },
    "DEMO": {
        "city_id": "demo",
        "name": "Synthetic Basin Pilot (M5-M11 Baseline)",
        "state": "West Bengal",
        "crs": "EPSG:32645",
        "utm_zone": "45N",
        "bbox": [88.35, 22.50, 88.45, 22.60],
        "dem_cells": [200, 200],
        "resolution_m": 20.1,
        "drainage_junctions": 16,
        "drainage_conduits": 15,
        "road_nodes": 14,
        "road_edges": 18,
        "has_coastal_surge": False,
        "has_riverine_flood": False,
        "live_radar_station": "Kolkata Doppler Radar (Simulated)",
        "provenance_status": "SYNTHETIC_BENCHMARK",
    },
}

_active_city_state: str = DEFAULT_CITY


def get_active_city() -> str:
    """Return currently active city key (MUMBAI, VIJAYAWADA, or DEMO)."""
    import os
    global _active_city_state
    env_city = os.getenv("UFNS_ACTIVE_CITY")
    if env_city and env_city.upper() in CITY_METADATA:
        return env_city.upper()
    return _active_city_state


def set_active_city(city_key: str) -> str:
    """Set active city key globally."""
    global _active_city_state
    norm = city_key.upper()
    if norm in CITY_METADATA:
        _active_city_state = norm
        return _active_city_state
    raise ValueError(f"Unknown city key: {city_key}. Available: {list(CITY_METADATA.keys())}")

