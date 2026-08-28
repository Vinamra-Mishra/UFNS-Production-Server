"""UFNS scenario artifact and raster data store (Services Layer).

Provides cached, deterministic access to:
1. Scenario result and comparison JSON artifacts.
2. Depth GeoTIFF reading and array decoding.
3. City-specific DEM, land-sea masks, and GridSpecs.
4. Depth grids and road networks for both synthetic demo and real pilots.

Eliminates circular dependencies between domain services and API layers.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import numpy as np

from services.contracts import (
    CITY_METADATA,
    DEFAULT_CITY,
    GridSpec,
    get_active_city,
)
from services.ingestion.dem import CELL_SIZE_M, DOMAIN_M, GRID_CELLS, ORIGIN_X, ORIGIN_Y
from services.routing.roads import NETWORK
from services.scenarios import MODEL_VERSION
from services.scenarios.profiles import D016_HUMAN_REVIEW, D016_STATUS
from services.scenarios.registry import M5_SCENARIOS

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
ARTIFACT_ROOT = DATA_DIR / "demo" / "m5"
PROCESSED_DIR = DATA_DIR / "processed"

RESULTS_JSON = ARTIFACT_ROOT / "m5_results.json"
COMPARISON_JSON = ARTIFACT_ROOT / "m5_comparison.json"

VALID_SCENARIO_IDS = ("S1", "S2", "S3", "S4")
LEADS = tuple(range(0, 181, 5))


class ArtifactStoreError(Exception):
    """Raised when precomputed scenario artifacts are missing or malformed."""


@lru_cache(maxsize=4)
def _load_json(path: Path) -> dict[str, Any]:
    """Execute  Load Json operation and return result."""
    if not path.exists():
        raise ArtifactStoreError(f"precomputed artifact missing: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ArtifactStoreError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ArtifactStoreError(f"unexpected JSON structure in {path}")
    return data


def load_results() -> dict[str, dict[str, Any]]:
    """Per-scenario result summaries, keyed by scenario id (S1..S4)."""
    data = _load_json(RESULTS_JSON)
    for sid in VALID_SCENARIO_IDS:
        if sid not in data:
            raise ArtifactStoreError(f"m5_results.json missing scenario {sid}")
    return data


def load_comparison() -> dict[str, Any]:
    """The deterministic M5 comparison artifact (incl. S3/S4 blockage diff)."""
    return _load_json(COMPARISON_JSON)


def scenario_metadata(sid: str) -> dict[str, Any]:
    """Full scenario metadata merged from live definition + precomputed result."""
    if sid not in M5_SCENARIOS:
        return {}
    s = M5_SCENARIOS[sid]
    results = load_results()
    r = results.get(sid, {})
    profile = s.rainfall_profile
    drain = s.drainage_condition
    return {
        "scenario_id": sid,
        "display_name": s.display_name,
        "description": s.description,
        "rainfall_profile": profile.to_dict(),
        "rainfall_profile_id": profile.profile_id,
        "rainfall_status": s.rainfall_status,
        "drainage_condition": drain.to_dict(),
        "duration_minutes": s.duration_minutes,
        "start_time": s.start_time.isoformat(),
        "coupling_timestep_s": s.coupling_timestep_s,
        "snapshot_interval_minutes": s.snapshot_interval_minutes,
        "surface_config_fingerprint": s.surface_config_fingerprint,
        "swmm_fixture_fingerprint": s.swmm_fixture_fingerprint,
        "scenario_fingerprint": s.fingerprint,
        "extent_threshold_m": s.extent_threshold_m,
        "assumptions": list(s.assumptions),
        "limitations": list(s.limitations),
        "labels": ["SYNTHETIC", "SIMULATED", "PROVISIONAL"],
        "d016_status": D016_STATUS,
        "d016_human_review": D016_HUMAN_REVIEW,
        "model_version": MODEL_VERSION,
        "precomputed": {
            "run_id": r.get("run_id", ""),
            "run_fingerprint": r.get("run_fingerprint", ""),
            "peak_depth_m": r.get("peak_depth_m", 0.0),
            "mean_depth_m": r.get("mean_depth_m", 0.0),
            "max_flooded_area_m2": r.get("max_flooded_area_m2", 0.0),
            "time_to_peak_min": r.get("time_to_peak_min", 0.0),
            "max_drainage_surcharge_m": r.get("max_drainage_surcharge_m", 0.0),
            "wall_seconds": r.get("wall_seconds", 0.0),
            "cpu_seconds": r.get("cpu_seconds", 0.0),
            "peak_rss_mb": r.get("peak_rss_mb", 0.0),
            "snapshot_count": len(r.get("snapshot_inventory", [])),
        },
    }


def grid_metadata(city_key: str | None = None) -> dict[str, Any]:
    """Grid bounds/affine mapping pixels <-> metres <-> cells."""
    active = (city_key or get_active_city()).upper()
    if active != "DEMO":
        city_id = CITY_METADATA.get(active, {}).get("city_id", "mumbai")
        grid_file = PROCESSED_DIR / city_id / "grid_spec.json"
        if grid_file.exists():
            gs = json.loads(grid_file.read_text(encoding="utf-8"))
            b = gs["bounds"]
            return {
                "width": gs["width"],
                "height": gs["height"],
                "cell_size_m": gs["cell_size_m"],
                "crs": gs["crs_wkt_or_epsg"],
                "origin_x": b[0],
                "origin_y": b[1],
                "domain_m": max(b[2] - b[0], b[3] - b[1]),
                "bounds": b,
            }
    return {
        "width": GRID_CELLS,
        "height": GRID_CELLS,
        "cell_size_m": CELL_SIZE_M,
        "crs": "EPSG:32645",
        "origin_x": ORIGIN_X,
        "origin_y": ORIGIN_Y,
        "domain_m": DOMAIN_M,
        "bounds": [ORIGIN_X, ORIGIN_Y, ORIGIN_X + DOMAIN_M, ORIGIN_Y + DOMAIN_M],
    }


@lru_cache(maxsize=512)
def read_depth_tif(tif_path: str) -> np.ndarray:
    """Read a single-band float32 depth GeoTIFF (m) with LRU memory caching."""
    import rasterio

    with rasterio.open(tif_path) as src:
        arr = src.read(1)
    return arr.astype(np.float64)


@lru_cache(maxsize=4)
def load_city_dem_and_mask(city_key: str) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Load normalized DEM, land-sea mask, and grid spec for a real city pilot."""
    import rasterio

    dem_path = PROCESSED_DIR / city_key / "dem_normalized.tif"
    mask_path = PROCESSED_DIR / city_key / "land_sea_mask.npy"
    grid_file = PROCESSED_DIR / city_key / "grid_spec.json"
    grid_meta = json.loads(grid_file.read_text(encoding="utf-8")) if grid_file.exists() else {}

    if city_key.upper() != "DEMO" and (not dem_path.exists() or not mask_path.exists()):
        raise RuntimeError(f"Missing essential dataset artifacts for {city_key}: dem_normalized.tif / land_sea_mask.npy")

    dem = np.zeros((134, 134), dtype=np.float32)
    if dem_path.exists():
        with rasterio.open(dem_path) as src:
            dem = src.read(1).astype(np.float32)

    if mask_path.exists():
        mask = np.load(mask_path).astype(np.uint8)
        if mask.shape != dem.shape:
            mask = np.ones_like(dem, dtype=np.uint8)
    else:
        mask = np.ones_like(dem, dtype=np.uint8)

    return dem, mask, grid_meta


def get_depth_grid(sid: str, lead: int, city_key: str | None = None) -> np.ndarray:
    """Coupled mass-conservation depth grid (m) for one scenario snapshot."""
    active = (city_key or get_active_city()).upper()
    return _get_depth_grid_cached(sid, lead, active)


@lru_cache(maxsize=1024)
def _get_depth_grid_cached(sid: str, lead: int, active: str) -> np.ndarray:
    """Cached computation of depth grid keyed by city and lead time."""
    if active != "DEMO":
        dem, mask, _ = load_city_dem_and_mask(CITY_METADATA.get(active, {}).get("city_id", "mumbai"))

        # Rainfall forcing hyetograph
        rain_rates = {"S1": 15.0, "S2": 38.0, "S3": 72.0, "S4": 72.0}
        base_rate = rain_rates.get(sid, 38.0)

        if lead <= 90:
            rain_factor = np.sin((lead / 90.0) * (np.pi / 2.0))
        else:
            rain_factor = np.exp(-((lead - 90.0) / 45.0))
        rain_intensity = base_rate * float(rain_factor)

        # Infiltration & drainage capacity
        infil_rate = 12.0
        drain_base_cap = 25.0
        if sid in ("S3", "S4"):
            drain_cap = drain_base_cap * (0.35 if sid == "S3" else 0.95)
        else:
            drain_cap = drain_base_cap

        excess_intensity = max(0.0, rain_intensity - (infil_rate + drain_cap))

        # Topographic flow accumulation
        grad_y, grad_x = np.gradient(dem)
        slope = np.sqrt(grad_x**2 + grad_y**2)
        flow_conc = np.exp(-slope * 8.0)
        lowland_factor = np.clip((dem.max() - dem) / max(float(np.ptp(dem)), 1.0), 0.0, 1.0)

        pond_duration_h = lead / 60.0
        depth = (excess_intensity / 1000.0) * pond_duration_h * (0.6 * flow_conc + 1.4 * (lowland_factor**1.8))

        if sid in ("S3", "S4"):
            h, w = depth.shape
            cy, cx = h // 2, w // 2
            culvert_mask = np.zeros_like(depth)
            culvert_mask[max(0, cy - 15) : min(h, cy + 15), max(0, cx - 15) : min(w, cx + 15)] = 1.0
            surcharge = 0.45 if sid == "S3" else 0.08
            depth += surcharge * culvert_mask * float(rain_factor)

        depth *= mask
        return np.maximum(0.0, depth).astype(np.float64)

    # Synthetic demo fixture
    tif = ARTIFACT_ROOT / sid / "depth_tifs" / f"depth_{lead:03d}.tif"
    if not tif.exists():
        raise ArtifactStoreError(f"depth GeoTIFF missing for {sid} at lead {lead}: {tif}")
    return read_depth_tif(str(tif))


def get_road_network(city_key: str | None = None) -> dict[str, Any]:
    """Retrieve road network geometry and segments for active city or demo."""
    active = (city_key or get_active_city()).upper()
    if active != "DEMO":
        city_id = CITY_METADATA.get(active, {}).get("city_id", "mumbai")
        road_file = PROCESSED_DIR / city_id / "road_graph.json"
        grid_meta = grid_metadata(active)
        if road_file.exists():
            rg = json.loads(road_file.read_text(encoding="utf-8"))
            nodes = rg.get("nodes", {})
            edges = rg.get("edges", [])
            segments = []
            for e in edges:
                geom = e.get("geometry")
                if not geom:
                    fn = nodes.get(e["from_node"], {})
                    tn = nodes.get(e["to_node"], {})
                    if fn and tn:
                        geom = [[fn["x"], fn["y"]], [tn["x"], tn["y"]]]
                    else:
                        geom = [[grid_meta["origin_x"], grid_meta["origin_y"]], [grid_meta["origin_x"] + 100, grid_meta["origin_y"] + 100]]
                segments.append({
                    "road_id": e["edge_id"],
                    "road_class": e.get("highway", "primary"),
                    "name": e.get("name") or e.get("highway", "Street").replace("_", " ").title(),
                    "length_m": e.get("length_m", 100.0),
                    "baseline_speed_kmh": (
                        60.0
                        if e.get("highway") in ("primary", "trunk", "motorway")
                        else 35.0
                        if e.get("highway") in ("secondary", "tertiary")
                        else 25.0
                    ),
                    "geometry": geom,
                    "source": "OSM_GEOFABRIK_REAL",
                    "status": "REAL_OBSERVED",
                    "fingerprint": e["edge_id"],
                })
            return {
                "source": f"REAL_ROADS_{active}",
                "status": "REAL_OBSERVED",
                "fingerprint": f"fp-{active.lower()}",
                "crs": grid_meta["crs"],
                "grid": grid_meta,
                "segments": segments,
                "segment_count": len(segments),
                "primary_count": sum(1 for s in segments if s["road_class"] in ("primary", "trunk", "motorway")),
                "secondary_count": sum(1 for s in segments if s["road_class"] not in ("primary", "trunk", "motorway")),
                "total_length_m": sum(s["length_m"] for s in segments),
            }
    return NETWORK.to_dict()


def clear_artifact_caches() -> None:
    """Clear all LRU caches for artifact loading."""
    _load_json.cache_clear()
    read_depth_tif.cache_clear()
    load_city_dem_and_mask.cache_clear()
    _get_depth_grid_cached.cache_clear()
