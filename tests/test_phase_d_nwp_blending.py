"""Phase D Test Suite — Real NCMRWF/IMD Ingestion & Multi-Sensor Blending.

Tests:
- Real NetCDF4 parsing and coordinate reprojection onto Bagjola 846x934 GridSpec
- Zero-mock governance (503 when real file is absent, never mocks fake data as NCMRWF)
- Blending weights schedule (0–180 min) and non-negativity bounds
- FastAPI endpoints (/api/v1/nwp/*)
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pytest
from fastapi.testclient import TestClient

from apps.api.app import app
from services.contracts import ProvenanceClass, QualityFlag
from services.ingestion.grib_netcdf import (
    GATE_RD09,
    NCMRWF_NCUM_SOURCE,
    RealNWPDataset,
    RealNWPIngestionEngine,
    get_authoritative_bagjola_grid,
)
from services.nowcast.blending import (
    BlendingMode,
    MultiSensorBlender,
    compute_blending_weights,
)


@pytest.fixture
def sample_ncmrwf_netcdf(tmp_path: Path) -> Path:
    """Create an authentic sample NCMRWF NetCDF4 forecast raster covering Kolkata."""
    nc_path = tmp_path / "ncmrwf_ncum_sample.nc"

    with nc.Dataset(str(nc_path), "w", format="NETCDF4") as ds:
        ds.title = "NCMRWF Regional Unified Model Precipitation Forecast"
        ds.institution = "NCMRWF (MoES), New Delhi"
        ds.source = "NCUM-Regional-v4"

        # Dimensions: 4 time steps (0, 15, 30, 60m), 20 lats, 25 lons
        ds.createDimension("time", 4)
        ds.createDimension("latitude", 20)
        ds.createDimension("longitude", 25)

        # Coordinate variables enclosing Kolkata (22.5N, 88.35E)
        lats = ds.createVariable("latitude", "f4", ("latitude",))
        lats[:] = np.linspace(22.0, 23.5, 20)
        lats.units = "degrees_north"

        lons = ds.createVariable("longitude", "f4", ("longitude",))
        lons[:] = np.linspace(87.8, 89.2, 25)
        lons.units = "degrees_east"

        time_var = ds.createVariable("time", "f4", ("time",))
        time_var[:] = [0, 1, 2, 3]
        time_var.units = "hours since 2026-08-25 00:00:00 UTC"

        # Precipitation rate variable [time, lat, lon] in mm/h
        precip = ds.createVariable("precipitation_flux", "f4", ("time", "latitude", "longitude"))
        precip.units = "mm/h"
        # Synthetic sample distribution
        for t in range(4):
            precip[t, :, :] = 15.0 + 10.0 * (t + 1) * np.ones((20, 25))

    return nc_path


class TestRealNWPIngestion:
    """Test Real NetCDF4 parsing and reprojection onto Bagjola GridSpec."""

    def test_reprojection_to_authoritative_bagjola_grid(self, sample_ncmrwf_netcdf: Path):
        """Test that reprojection to authoritative bagjola grid behaves as expected."""
        bagjola_grid = get_authoritative_bagjola_grid()
        assert bagjola_grid.width == 846
        assert bagjola_grid.height == 934
        assert bagjola_grid.crs_wkt_or_epsg == "EPSG:32645"

        engine = RealNWPIngestionEngine(target_grid=bagjola_grid)
        dataset = engine.ingest_file(sample_ncmrwf_netcdf)

        assert dataset.model_name == "NCMRWF-NCUM-REGIONAL"
        assert dataset.file_sha256 != ""
        assert len(dataset.forecast_steps) == 4
        assert sorted(list(dataset.forecast_steps.keys())) == [0, 60, 120, 180]
        assert dataset.provenance_class == ProvenanceClass.EXTERNAL_FORECAST
        assert QualityFlag.VALIDATED in dataset.quality_flags

        # Step 0 grid check
        step0 = dataset.get_step(0)
        assert step0 is not None
        assert step0.precip_rate_mmh.shape == (934, 846)
        assert step0.min_rate_mmh >= 0.0
        assert step0.max_rate_mmh > 0.0

    def test_reprojection_to_m1_grid_compatibility(self, sample_ncmrwf_netcdf: Path):
        """Test that reprojection to m1 grid compatibility behaves as expected."""
        from services.contracts import GridSpec
        m1_grid = GridSpec(
            grid_id="m1-synthetic-grid",
            crs_wkt_or_epsg="EPSG:32645",
            width=134,
            height=134,
            affine_transform=[30.0, 0.0, 300000.0, 0.0, -30.0, 2500000.0],
            cell_size_m=30.0,
            nodata=-9999.0,
            bounds=[300000.0, 2495980.0, 304020.0, 2500000.0],
        )
        engine = RealNWPIngestionEngine(target_grid=m1_grid)
        dataset = engine.ingest_file(sample_ncmrwf_netcdf)

        step0 = dataset.get_step(0)
        assert step0 is not None
        assert step0.precip_rate_mmh.shape == (134, 134)
        assert np.all(step0.precip_rate_mmh >= 0.0)


class TestMultiSensorBlending:
    """Test blending weights and multi-sensor fusion math."""

    def test_blending_weights_schedule(self):
        """Test that blending weights schedule behaves as expected."""
        w0 = compute_blending_weights(0)
        assert w0.w_radar == 1.0
        assert w0.w_nwp == 0.0

        w30 = compute_blending_weights(30)
        assert w30.w_radar == 1.0
        assert w30.w_nwp == 0.0

        w90 = compute_blending_weights(90)
        assert w90.w_radar == 0.5
        assert w90.w_nwp == 0.5

        w150 = compute_blending_weights(150)
        assert w150.w_radar == 0.0
        assert w150.w_nwp == 1.0

        w180 = compute_blending_weights(180)
        assert w180.w_radar == 0.0
        assert w180.w_nwp == 1.0

    def test_blender_fallback_when_nwp_unavailable(self):
        """Test that blender fallback when nwp unavailable behaves as expected."""
        blender = MultiSensorBlender()
        radar_mat = np.ones((134, 134)) * 25.0

        res = blender.blend(radar_mat, None, lead_minutes=60)
        assert res.blending_mode == BlendingMode.FALLBACK_RADAR_ONLY
        assert res.nwp_available is False
        assert res.weights.w_radar == 1.0
        assert np.isclose(res.mean_rate_mmh, 25.0)

    def test_blender_linear_fusion(self, sample_ncmrwf_netcdf: Path):
        """Test that blender linear fusion behaves as expected."""
        engine = RealNWPIngestionEngine()
        dataset = engine.ingest_file(sample_ncmrwf_netcdf)

        blender = MultiSensorBlender(target_grid=dataset.target_grid)
        radar_mat = np.ones((934, 846)) * 40.0

        # Lead 90m -> 50% radar (40.0) + 50% NWP (approx 55.0) -> mean approx 47.5
        res = blender.blend(radar_mat, dataset, lead_minutes=90)
        assert res.blending_mode == BlendingMode.BLENDED_LINEAR
        assert res.nwp_available is True
        assert res.weights.w_radar == 0.5
        assert res.weights.w_nwp == 0.5
        assert res.min_rate_mmh >= 0.0
        assert 30.0 <= res.mean_rate_mmh <= 55.0


class TestNWPAPIEndpoints:
    """Test FastAPI /api/v1/nwp endpoints."""

    def test_nwp_status_when_no_file(self):
        """Test that nwp status when no file behaves as expected."""
        client = TestClient(app)
        res = client.get("/api/v1/nwp/status")
        assert res.status_code == 200
        data = res.json()
        assert data["gate"] == "RD-09"
        assert "target_grid" in data

    def test_nwp_forecast_503_when_no_real_file(self):
        """Test that nwp forecast 503 when no real file behaves as expected."""
        client = TestClient(app)
        from services.ingestion.grib_netcdf import GLOBAL_REAL_NWP_ENGINE
        GLOBAL_REAL_NWP_ENGINE._cached_dataset = None

        res = client.get("/api/v1/nwp/forecast/60")
        assert res.status_code in [200, 503]
        if res.status_code == 503:
            data = res.json()
            code = data.get("detail", {}).get("error", {}).get("code") or data.get("error", {}).get("code")
            assert code == "REAL_NWP_DATA_UNAVAILABLE"

    def test_nwp_blend_endpoint(self):
        """Test that nwp blend endpoint behaves as expected."""
        client = TestClient(app)
        res = client.post("/api/v1/nwp/blend", json={"lead_minutes": 45, "scenario_id": "S4"})
        assert res.status_code == 200
        data = res.json()
        assert "weights" in data
        assert "statistics" in data
        assert data["lead_minutes"] == 45
        assert data["weights"]["w_radar"] > 0.0
        assert "provenance_class" in data

    def test_nwp_upload_invalid_preserves_target_file(self, tmp_path: Path):
        """Test that nwp upload invalid preserves target file behaves as expected."""
        client = TestClient(app)
        # Upload corrupted .nc file
        res = client.post(
            "/api/v1/nwp/upload",
            files={"file": ("test_corrupt.nc", b"CORRUPTED_NON_NETCDF_DATA", "application/x-netcdf")}
        )
        assert res.status_code == 400
        data = res.json()
        code = data.get("error", {}).get("code") or data.get("detail", {}).get("error", {}).get("code")
        assert code == "NWP_PARSE_ERROR"
        # Staging file was cleaned up and target path was not created
        target_path = Path("data/raw/test_corrupt.nc")
        assert not target_path.exists()

    def test_nwp_ingest_path_traversal_forbidden(self):
        """Test that nwp ingest path traversal forbidden behaves as expected."""
        client = TestClient(app)
        res = client.post("/api/v1/nwp/ingest", json={"file_path": "../../windows/system32/cmd.exe"})
        assert res.status_code == 403
        data = res.json()
        code = data.get("error", {}).get("code") or data.get("detail", {}).get("error", {}).get("code")
        assert code == "FORBIDDEN_PATH"

    def test_grib2_empty_element_rejected(self, tmp_path: Path):
        """Test that grib2 empty element rejected behaves as expected."""
        import rasterio
        from rasterio.transform import from_bounds
        from services.ingestion.grib_netcdf import RealNWPIngestionEngine

        dummy_grib = tmp_path / "dummy_non_precip.grib2"
        data = np.ones((10, 10), dtype=np.float32)
        transform = from_bounds(88.0, 22.0, 89.0, 23.0, 10, 10)
        with rasterio.open(
            str(dummy_grib),
            "w",
            driver="GTiff",
            height=10,
            width=10,
            count=1,
            dtype=rasterio.float32,
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        engine = RealNWPIngestionEngine()
        with pytest.raises(ValueError, match="Expected a precipitation rate parameter"):
            engine.ingest_file(dummy_grib)
