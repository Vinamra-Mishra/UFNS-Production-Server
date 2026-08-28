"""Comprehensive tests for Unified Nowcast, Dynamic Storm Generators, and Layering Hygiene.

Tests:
1. No circular/reverse dependencies from services/ to apps.api
2. UnifiedNowcastEngine multi-horizon nowcasting (optical flow + NWP blending + persistence)
3. Dynamic Chicago Design Storm and Custom Hyetograph generators
4. Custom event scenario execution with coupled physical flood engine
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
import pytest

from services.contracts import (
    CITY_METADATA,
    get_active_city,
    set_active_city,
)
from services.nowcast.engine import NowcastConfig, UnifiedNowcastEngine, create_nowcast_engine
from services.nowcast.providers.synthetic_provider import SyntheticRainfallProvider
from services.nowcast.service import (
    fetch_latest_nowcast_records,
    fetch_latest_observation,
    get_active_provider_id,
    set_active_provider_id,
)
from services.scenarios.profiles import (
    generate_chicago_storm,
    generate_custom_hyetograph,
)
from services.scenarios.runner import run_custom_scenario


class TestLayeringAndImportHygiene:
    """Verify that services/ contains zero imports from apps.api."""

    def test_services_has_no_reverse_imports_from_apps(self):
        """Test that services has no reverse imports from apps behaves as expected."""
        repo_root = Path(__file__).resolve().parents[1]
        service_files = list((repo_root / "services").rglob("*.py"))
        offenders = []

        for f in service_files:
            content = f.read_text(encoding="utf-8")
            for line_idx, line in enumerate(content.splitlines(), start=1):
                clean_line = line.strip()
                if clean_line.startswith("#"):
                    continue
                if "from apps" in clean_line or "import apps" in clean_line:
                    offenders.append(f"{f.relative_to(repo_root)}:{line_idx}: {clean_line}")

        assert len(offenders) == 0, f"Found reverse imports from apps in services/:\n" + "\n".join(offenders)


class TestUnifiedNowcastEngine:
    """Test the unified nowcast multi-horizon pipeline."""

    def test_unified_nowcast_generation(self):
        """Test that unified nowcast generation behaves as expected."""
        config = NowcastConfig(
            method="NOWCAST-UNIFIED-V1",
            lead_times_minutes=(0, 15, 30, 45, 60, 90, 120),
            max_lead_minutes=120,
        )
        engine = create_nowcast_engine(config)
        assert isinstance(engine, UnifiedNowcastEngine)

        provider = SyntheticRainfallProvider(
            provider_id="test-synth-nowcast",
            base_rate_mmh=25.0,
            pattern="convective_cell",
            grid_shape=(134, 134),
            seed=20260822,
        )
        obs = provider.fetch_latest()
        records = engine.generate(obs)

        assert len(records) == len(config.lead_times_minutes)
        for rec in records:
            assert rec.method == "NOWCAST-UNIFIED-V1"
            assert rec.rate_mmh.shape == (134, 134)
            assert np.all(rec.rate_mmh >= 0.0)
            assert rec.fingerprint is not None
            assert "UNIFIED_MULTI_HORIZON" in rec.quality_flags

    def test_nowcast_service_registry(self):
        """Test that nowcast service registry behaves as expected."""
        orig_id = get_active_provider_id()
        try:
            set_active_provider_id("synthetic-v1")
            assert get_active_provider_id() == "synthetic-v1"

            prov, obs, qual, recs = fetch_latest_nowcast_records(method="NOWCAST-UNIFIED-V1")
            assert prov.provider_id == "synthetic-v1"
            assert obs is not None
            assert qual.valid is True
            assert len(recs) > 0
        finally:
            set_active_provider_id(orig_id)


class TestDynamicStormGenerators:
    """Test Chicago and Custom hyetograph generators."""

    def test_chicago_storm_generation(self):
        """Test that chicago storm generation behaves as expected."""
        prof = generate_chicago_storm(total_depth_mm=75.0, duration_minutes=180, interval_minutes=15)
        assert prof.total_depth_mm == 75.0
        assert prof.duration_minutes == 180
        assert len(prof.intensities_mmh) == 12
        assert prof.peak_intensity_mmh > 0.0
        assert prof.fingerprint != ""

    def test_custom_hyetograph_generation(self):
        """Test that custom hyetograph generation behaves as expected."""
        series = [10.0, 25.0, 60.0, 80.0, 45.0, 20.0, 5.0, 0.0]
        prof = generate_custom_hyetograph(series, interval_minutes=15, display_name="2005 Mumbai Historical Cloudburst")
        assert prof.duration_minutes == 120
        assert len(prof.intensities_mmh) == 8
        assert prof.peak_intensity_mmh == 80.0
        assert prof.total_depth_mm == round(sum(series) * 0.25, 2)


class TestCustomScenarioSimulation:
    """Test simulating on-demand custom storms with coupled physical engine."""

    def test_run_custom_scenario(self):
        """Test that run custom scenario behaves as expected."""
        prof = generate_custom_hyetograph([20.0, 40.0], interval_minutes=15, display_name="Quick Test Storm")
        res = run_custom_scenario(
            rainfall_profile=prof,
            duration_minutes=30,
            culvert_blockage_pct=0.0,
        )
        assert res.scenario.scenario_id == "CUSTOM_EVENT"
        assert res.peak_depth_m >= 0.0
        assert res.wall_seconds > 0.0
        assert len(res.snapshot_inventory) >= 1
