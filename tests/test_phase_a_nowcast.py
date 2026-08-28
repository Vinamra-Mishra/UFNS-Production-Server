"""Tests for Phase A: Doppler Radar Ingestion, 0-3h Optical Flow Nowcasting, and Projection Extension.

Tests cover:
  PA-01: Z-R Relationship inversion (Stratiform vs Convective formulas, hail capping)
  PA-02: RadarRasterParser (dBZ to mm/h, resample, metadata, fingerprinting)
  PA-03: RadarRainfallProvider (frame ingestion, latest fetch, query at timestamp)
  PA-04: Optical Flow Motion Field estimation (Lucas-Kanade gradient velocity tracking)
  PA-05: Semi-Lagrangian Advection extrapolation (motion accuracy, boundaries, decay)
  PA-06: AdvectionNowcastEngine 0–180 min record generation and invariants
  PA-07: NeuralNowcastEngine PyTorch stub & deterministic fallback
  PA-08: Verification metrics (CSI, POD, FAR, ETS, FSS, RMSE multi-threshold)
  PA-09: Projection Pipeline & API 0–180 min lead time validation
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from fastapi.testclient import TestClient

from apps.api.app import app
from services.ingestion.radar import (
    RadarProductType,
    RadarRasterMetadata,
    RadarRasterParser,
    ZRRelationship,
    ZR_CONVECTIVE,
    ZR_MARSHALL_PALMER,
)
from services.nowcast import (
    NOWCAST_METHOD_ADVECTION,
    NOWCAST_METHOD_NEURAL,
    NOWCAST_METHOD_PERSISTENCE,
)
from services.nowcast.advection import (
    AdvectionConfig,
    AdvectionNowcastEngine,
    compute_motion_field,
    semi_lagrangian_extrapolate,
)
from services.nowcast.neural_stub import NeuralNowcastConfig, NeuralNowcastEngine
from services.nowcast.nowcast_record import NowcastRecord
from services.nowcast.providers import RainfallObservation, SourceType
from services.nowcast.providers.radar_provider import RadarRainfallProvider
from services.nowcast.verification import (
    compute_csi,
    compute_ets,
    compute_far,
    compute_fss,
    compute_mae,
    compute_multi_threshold_verification,
    compute_pod,
    compute_rmse,
    verify_pair,
)
from services.projection import VALID_LEADS
from services.projection.configs import get_projection_config


# ---------------------------------------------------------------------------
# PA-01: Z-R Relationship Tests
# ---------------------------------------------------------------------------

class TestZRRelationship:
    """PA-01: Z-R power-law conversions and meteorological filtering."""

    def test_marshall_palmer_conversion(self):
        """Test that marshall palmer conversion behaves as expected."""
        zr = ZR_MARSHALL_PALMER
        # 30 dBZ => Z = 1000 => R = (1000 / 200)^(1/1.6) = 5^(0.625) ~ 2.734 mm/h
        dbz = np.array([[30.0]])
        rate = zr.dbz_to_rate(dbz)
        expected_rate = (1000.0 / 200.0) ** (1.0 / 1.6)
        assert rate[0, 0] == pytest.approx(expected_rate, rel=1e-3)

    def test_convective_conversion(self):
        """Test that convective conversion behaves as expected."""
        zr = ZR_CONVECTIVE
        # 45 dBZ => Z = 31622.77 => R = (31622.77 / 300)^(1/1.4) ~ 27.94 mm/h
        dbz = np.array([[45.0]])
        rate = zr.dbz_to_rate(dbz)
        expected_rate = (10.0 ** (4.5) / 300.0) ** (1.0 / 1.4)
        assert rate[0, 0] == pytest.approx(expected_rate, rel=1e-3)

    def test_minimum_threshold_masking(self):
        """Test that minimum threshold masking behaves as expected."""
        zr = ZRRelationship(a=200.0, b=1.6, min_dbz=15.0)
        dbz = np.array([[5.0, 10.0, 14.9, 15.1]])
        rate = zr.dbz_to_rate(dbz)
        assert rate[0, 0] == 0.0
        assert rate[0, 1] == 0.0
        assert rate[0, 2] == 0.0
        assert rate[0, 3] > 0.0

    def test_hail_capping(self):
        """Test that hail capping behaves as expected."""
        zr = ZRRelationship(a=200.0, b=1.6, max_dbz=55.0)
        dbz_extreme = np.array([[75.0]])
        rate_75 = zr.dbz_to_rate(dbz_extreme)
        rate_55 = zr.dbz_to_rate(np.array([[55.0]]))
        assert rate_75[0, 0] == pytest.approx(rate_55[0, 0], rel=1e-5)

    def test_roundtrip_rate_to_dbz(self):
        """Test that roundtrip rate to dbz behaves as expected."""
        zr = ZR_MARSHALL_PALMER
        initial_rate = np.array([[5.0, 25.0, 60.0]])
        dbz = zr.rate_to_dbz(initial_rate)
        recovered_rate = zr.dbz_to_rate(dbz)
        np.testing.assert_allclose(recovered_rate, initial_rate, rtol=1e-3)


# ---------------------------------------------------------------------------
# PA-02: RadarRasterParser Tests
# ---------------------------------------------------------------------------

class TestRadarRasterParser:
    """PA-02: Ingestion of radar arrays, resampling and metadata creation."""

    def test_parse_reflectivity_array(self):
        """Test that parse reflectivity array behaves as expected."""
        parser = RadarRasterParser(default_target_shape=(32, 32))
        raw_dbz = np.full((32, 32), 35.0)
        t = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        rate_arr, meta = parser.parse_array(
            data=raw_dbz,
            product_type=RadarProductType.REFLECTIVITY_DBZ,
            timestamp=t,
            source_id="TEST_RADAR",
        )
        assert rate_arr.shape == (32, 32)
        assert meta.product_type == RadarProductType.REFLECTIVITY_DBZ
        assert meta.rate_mean_mmh > 0.0
        assert meta.data_fingerprint != ""
        assert meta.is_real_data is True

    def test_parse_with_resampling(self):
        """Test that parse with resampling behaves as expected."""
        parser = RadarRasterParser(default_target_shape=(64, 64))
        raw_sri = np.full((16, 16), 20.0)
        t = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        rate_arr, meta = parser.parse_array(
            data=raw_sri,
            product_type=RadarProductType.RAIN_RATE_MMH,
            timestamp=t,
        )
        assert rate_arr.shape == (64, 64)
        assert np.allclose(rate_arr, 20.0)


# ---------------------------------------------------------------------------
# PA-03: RadarRainfallProvider Tests
# ---------------------------------------------------------------------------

class TestRadarRainfallProvider:
    """PA-03: Radar provider integration."""

    def test_ingest_and_fetch_observation(self):
        """Test that ingest and fetch observation behaves as expected."""
        provider = RadarRainfallProvider(grid_shape=(32, 32))
        t1 = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 8, 25, 10, 15, tzinfo=timezone.utc)
        
        raw_dbz_1 = np.full((32, 32), 25.0)
        raw_dbz_2 = np.full((32, 32), 40.0)

        obs1 = provider.ingest_frame(raw_dbz_1, RadarProductType.REFLECTIVITY_DBZ, t1)
        obs2 = provider.ingest_frame(raw_dbz_2, RadarProductType.REFLECTIVITY_DBZ, t2)

        assert provider.fetch_latest() == obs2
        assert provider.fetch_observation(t1) == obs1
        assert provider.health().status.value == "HEALTHY"


# ---------------------------------------------------------------------------
# PA-04: Optical Flow Motion Field Tests
# ---------------------------------------------------------------------------

class TestOpticalFlowMotionField:
    """PA-04: Calculation of storm motion vectors (u, v)."""

    def test_compute_motion_field_displacement(self):
        """Test that compute motion field displacement behaves as expected."""
        # Create a moving Gaussian rain cell
        grid_size = 64
        cell_size = 30.0
        dt = 900.0  # 15 min

        y, x = np.mgrid[0:grid_size, 0:grid_size]
        
        # Frame 1: center at (20, 20)
        f1 = 40.0 * np.exp(-((x - 20)**2 + (y - 20)**2) / (2 * 5**2))
        # Frame 2: moved 6 cells east (+x) and 4 cells north (+y) -> center at (26, 24)
        f2 = 40.0 * np.exp(-((x - 26)**2 + (y - 24)**2) / (2 * 5**2))

        u_field, v_field, u_glob, v_glob = compute_motion_field(
            frame_prev=f1,
            frame_curr=f2,
            cell_size_m=cell_size,
            dt_seconds=dt,
        )

        expected_u = (6 * cell_size) / dt  # (180 m) / 900 s = 0.2 m/s
        expected_v = (4 * cell_size) / dt  # (120 m) / 900 s = 0.133 m/s

        assert u_glob == pytest.approx(expected_u, abs=0.05)
        assert v_glob == pytest.approx(expected_v, abs=0.05)


# ---------------------------------------------------------------------------
# PA-05: Semi-Lagrangian Advection Tests
# ---------------------------------------------------------------------------

class TestSemiLagrangianAdvection:
    """PA-05: Extrapolating rainfall fields forward in time."""

    def test_advection_centroid_movement(self):
        """Test that advection centroid movement behaves as expected."""
        grid_size = 64
        cell_size = 30.0
        y, x = np.mgrid[0:grid_size, 0:grid_size]
        
        # Initial convective cell at center (30, 30)
        f0 = 50.0 * np.exp(-((x - 30)**2 + (y - 30)**2) / (2 * 4**2))
        
        # Advection velocity: u = 1.0 m/s (east), v = 0.0 m/s
        # Lead time: 15 min = 900 s -> distance = 900 m -> shift in cells = 900 / 30 = 30 cells east
        f_adv = semi_lagrangian_extrapolate(
            field=f0,
            u_mps=1.0,
            v_mps=0.0,
            lead_minutes=15.0,
            cell_size_m=cell_size,
            decay_tau_minutes=None,
        )

        # Centroid of f_adv should be approximately at x = 60
        max_idx_orig = np.unravel_index(np.argmax(f0), f0.shape)
        max_idx_adv = np.unravel_index(np.argmax(f_adv), f_adv.shape)

        assert max_idx_orig == (30, 30)
        assert max_idx_adv[0] == 30
        assert max_idx_adv[1] == pytest.approx(60, abs=1)

    def test_convective_decay(self):
        """Test that convective decay behaves as expected."""
        grid = np.full((32, 32), 20.0)
        lead = 60.0
        tau = 60.0
        f_decay = semi_lagrangian_extrapolate(
            field=grid,
            u_mps=0.0,
            v_mps=0.0,
            lead_minutes=lead,
            decay_tau_minutes=tau,
        )
        expected_rate = 20.0 * math.exp(-1.0)
        assert f_decay[10, 10] == pytest.approx(expected_rate, rel=1e-3)


# ---------------------------------------------------------------------------
# PA-06: AdvectionNowcastEngine 0–180 min Tests
# ---------------------------------------------------------------------------

class TestAdvectionNowcastEngine:
    """PA-06: 0–180 min nowcast record generation."""

    def test_full_0_to_180_min_records(self):
        """Test that full 0 to 180 min records behaves as expected."""
        engine = AdvectionNowcastEngine()
        t = datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc)
        rate = np.full((134, 134), 15.0)
        
        obs = RainfallObservation(
            observation_time=t,
            valid_from=t,
            valid_to=t + timedelta(minutes=15),
            rate_mmh=rate,
            source_type=SourceType.REAL,
            source_name="Radar Test",
            source_provider_id="radar-1",
            spatial_reference="EPSG:32645",
            spatial_resolution_m=30.0,
            width=134,
            height=134,
        )

        records = engine.generate(obs)
        expected_leads = (0, 15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180)
        
        assert len(records) == len(expected_leads)
        for i, lead in enumerate(expected_leads):
            rec = records[i]
            assert rec.lead_minutes == lead
            assert rec.valid_time == t + timedelta(minutes=lead)
            assert rec.method == NOWCAST_METHOD_ADVECTION
            assert rec.fingerprint != ""
            assert np.all(rec.rate_mmh >= 0.0)


# ---------------------------------------------------------------------------
# PA-07: NeuralNowcastEngine PyTorch Stub Tests
# ---------------------------------------------------------------------------

class TestNeuralNowcastEngine:
    """PA-07: Neural nowcaster interface and fallback."""

    def test_neural_fallback_execution(self):
        """Test that neural fallback execution behaves as expected."""
        engine = NeuralNowcastEngine()
        t = datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc)
        rate = np.full((134, 134), 10.0)
        
        obs = RainfallObservation(
            observation_time=t,
            valid_from=t,
            valid_to=t + timedelta(minutes=15),
            rate_mmh=rate,
            source_type=SourceType.SYNTHETIC,
            source_name="Synthetic Test",
            source_provider_id="synth-1",
            spatial_reference="EPSG:32645",
            spatial_resolution_m=30.0,
            width=134,
            height=134,
        )

        records = engine.generate(obs)
        assert len(records) == 13  # 0 to 180 min
        assert records[0].method == NOWCAST_METHOD_NEURAL
        assert "NEURAL_FALLBACK" in records[0].quality_flags
        assert records[0].metadata["engine_execution_mode"] == "DETERMINISTIC_ADVECTION_FALLBACK"


# ---------------------------------------------------------------------------
# PA-08: Verification Metrics Tests
# ---------------------------------------------------------------------------

class TestVerificationMetrics:
    """PA-08: Meteorological skill score evaluation."""

    def test_perfect_forecast_scores(self):
        """Test that perfect forecast scores behaves as expected."""
        field = np.array([[0.0, 5.0], [10.0, 20.0]])
        assert compute_mae(field, field) == 0.0
        assert compute_rmse(field, field) == 0.0
        assert compute_csi(field, field, threshold=1.0) == 1.0
        assert compute_pod(field, field, threshold=1.0) == 1.0
        assert compute_far(field, field, threshold=1.0) == 0.0
        assert compute_ets(field, field, threshold=1.0) == 1.0
        assert compute_fss(field, field, threshold=1.0) == 1.0

    def test_multi_threshold_verification(self):
        """Test that multi threshold verification behaves as expected."""
        f = np.array([[0.0, 10.0], [15.0, 30.0]])
        o = np.array([[0.0, 12.0], [8.0, 35.0]])
        res = compute_multi_threshold_verification(f, o, thresholds=(5.0, 15.0))
        assert res["status"] == "EVALUATED"
        assert "th_5.0_mmh" in res["thresholds"]
        assert "th_15.0_mmh" in res["thresholds"]


# ---------------------------------------------------------------------------
# PA-09: Projection Pipeline & API 0–180 min Tests
# ---------------------------------------------------------------------------

class TestProjectionHorizonExtension:
    """PA-09: Projection horizon up to 180 min."""

    def test_valid_leads_contains_180(self):
        """Test that valid leads contains 180 behaves as expected."""
        from services.projection import VALID_LEADS_3H
        assert 180 in VALID_LEADS_3H
        assert VALID_LEADS_3H[-1] == 180

    def test_projection_config_horizon_180(self):
        """Test that projection config horizon 180 behaves as expected."""
        cfg = get_projection_config("P_NORMAL_3H")
        assert cfg.duration_minutes == 180
        assert 180 in cfg.lead_times_minutes

    def test_projection_configs_available(self):
        """Test that projection configs available behaves as expected."""
        from services.projection.configs import PROJECTION_CONFIGS
        assert "P_NORMAL_3H" in PROJECTION_CONFIGS
        assert "P_BLOCKED_3H" in PROJECTION_CONFIGS

    def test_advection_and_neural_engines_support_180_min(self):
        """Test that advection and neural engines support 180 min behaves as expected."""
        adv_engine = AdvectionNowcastEngine(AdvectionConfig())
        assert 180 in adv_engine.config.lead_times_minutes

        neural_engine = NeuralNowcastEngine(NeuralNowcastConfig())
        assert 180 in neural_engine.config.lead_times_minutes


