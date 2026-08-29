"""Unified Nowcast Service & Provider Registry (Services Layer).

Provides provider-independent ingestion, caching, and unified multi-horizon
nowcast generation supporting:
1. Optical Flow Semi-Lagrangian Advection (Phase A: 0-60 min radar extrapolation)
2. NWP + Doppler Radar Blending (Phase D: 30-180 min multi-model NWP fusion)
3. Spatio-Temporal Deep Learning (Phase A: PyTorch ConvLSTM/UNet stub)
4. Persistence Baseline (M8 benchmark for scientific skill evaluation)

Centralizes provider state and eliminates reverse dependencies from services to apps/api.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from services.ingestion.dem import GRID_CELLS as DEFAULT_GRID_CELLS
from services.nowcast import (
    NOWCAST_METHOD_ADVECTION,
    NOWCAST_METHOD_BLENDING,
    NOWCAST_METHOD_NEURAL,
    NOWCAST_METHOD_PERSISTENCE,
    NOWCAST_VERSION,
)
from services.nowcast.cache import NowcastCache
from services.nowcast.engine import NowcastConfig, PersistenceNowcast, create_nowcast_engine
from services.nowcast.nowcast_record import NowcastRecord
from services.nowcast.providers import (
    RainfallObservation,
    RainfallProvider,
)
from services.nowcast.providers.fixture_provider import FixtureRainfallProvider
from services.nowcast.providers.radar_provider import RadarRainfallProvider
from services.nowcast.providers.synthetic_provider import SyntheticRainfallProvider
from services.nowcast.quality import (
    DataFreshness,
    QualityConfig,
    QualityResult,
    validate_observation,
)

logger = logging.getLogger(__name__)

# Module-level singletons
_providers: dict[str, RainfallProvider] = {}
_active_provider_id: str | None = None
_nowcast_cache = NowcastCache(ttl_seconds=300)
_nowcast_config = NowcastConfig()
_quality_config = QualityConfig()
_default_engine = PersistenceNowcast(_nowcast_config)


def init_providers() -> None:
    """Initialize all built-in rainfall providers."""
    global _active_provider_id

    grid_shape = (DEFAULT_GRID_CELLS, DEFAULT_GRID_CELLS)

    # 1. Synthetic Provider
    synthetic = SyntheticRainfallProvider(
        provider_id="synthetic-v1",
        base_rate_mmh=15.0,
        pattern="convective_cell",
        grid_shape=grid_shape,
        seed=20260822,
    )
    _providers["synthetic-v1"] = synthetic

    # 2. Fixture Provider (M5 S3 Extreme Profile)
    from services.scenarios.profiles import build_profile_record

    extreme_profile = build_profile_record("P_EXTREME")
    fixture = FixtureRainfallProvider(
        provider_id="fixture-extreme-v1",
        profile_intensities_mmh=list(extreme_profile.intensities_mmh),
        interval_minutes=extreme_profile.temporal_resolution_minutes,
        pattern="convective_cell",
        grid_shape=grid_shape,
        seed=20260822,
        scenario_label="S3_EXTREME_FIXTURE",
    )
    _providers["fixture-extreme-v1"] = fixture

    # 3. Live Doppler Weather Radar (DWR) Provider
    radar = RadarRainfallProvider(
        provider_id="rainviewer-dwr-v1",
        source_name="Live Doppler Weather Radar Mosaic (IMD / RainViewer)",
        grid_shape=grid_shape,
    )
    _providers["rainviewer-dwr-v1"] = radar
    _providers["dwr-kolkata-v1"] = radar

    # Default provider (demo default is synthetic)
    _active_provider_id = "synthetic-v1"


# Initialize providers upon module loading
init_providers()


# ---------------------------------------------------------------------------
# Provider Registry Accessors
# ---------------------------------------------------------------------------

def get_providers() -> dict[str, RainfallProvider]:
    """Return all registered providers."""
    return dict(_providers)


def register_provider(provider: RainfallProvider) -> None:
    """Register or replace a rainfall provider."""
    _providers[provider.provider_id] = provider


def get_provider(provider_id: str) -> RainfallProvider | None:
    """Retrieve provider by identifier."""
    return _providers.get(provider_id)


def get_active_provider_id() -> str:
    """Return identifier of the active provider."""
    global _active_provider_id
    if _active_provider_id is None or _active_provider_id not in _providers:
        _active_provider_id = "synthetic-v1"
    return _active_provider_id


def set_active_provider_id(provider_id: str) -> None:
    """Set the active provider identifier."""
    global _active_provider_id
    if provider_id not in _providers:
        raise ValueError(f"Unknown provider: {provider_id!r}. Available: {list(_providers.keys())}")
    _active_provider_id = provider_id


def get_nowcast_config() -> NowcastConfig:
    """Retrieve and return nowcast config."""
    return _nowcast_config


def set_nowcast_config(config: NowcastConfig) -> None:
    """Set and apply new nowcast config."""
    global _nowcast_config, _default_engine
    _nowcast_config = config
    _default_engine = PersistenceNowcast(config)


def get_quality_config() -> QualityConfig:
    """Retrieve and return quality config."""
    return _quality_config


def get_nowcast_cache() -> NowcastCache:
    """Retrieve and return nowcast cache."""
    return _nowcast_cache


# ---------------------------------------------------------------------------
# Observation & Nowcast Generation Pipeline
# ---------------------------------------------------------------------------

def fetch_latest_observation(
    provider_id: str | None = None,
) -> tuple[RainfallProvider, RainfallObservation | None, QualityResult]:
    """Fetch latest observation from specified or active provider with quality validation."""
    pid = provider_id or get_active_provider_id()
    prov = get_provider(pid)
    if prov is None:
        raise ValueError(f"Provider {pid!r} not found.")

    obs = prov.fetch_latest()
    if obs is None:
        qual = QualityResult(
            observation=None,
            freshness=DataFreshness.MISSING,
            valid=False,
            errors=["no observation available"],
            warnings=[],
            checked_at=datetime.now(timezone.utc),
        )
        return prov, None, qual
    qual = validate_observation(obs, _quality_config)
    return prov, obs, qual


def fetch_latest_nowcast_records(
    provider_id: str | None = None,
    method: str | None = None,
    lead_minutes: int | None = None,
) -> tuple[RainfallProvider, RainfallObservation | None, QualityResult, list[NowcastRecord]]:
    """Fetch observation and compute nowcast records across configured horizons."""
    prov, obs, qual = fetch_latest_observation(provider_id)
    if obs is None:
        return prov, None, qual, []

    engine_method = method or _nowcast_config.method
    cfg = NowcastConfig(
        method=engine_method,
        lead_times_minutes=_nowcast_config.lead_times_minutes,
        max_lead_minutes=_nowcast_config.max_lead_minutes,
        status="PROVISIONAL",
        uncertainty=_nowcast_config.uncertainty,
    )

    # Check cache first
    cached_records = _nowcast_cache.get_nowcast(obs, engine_method, cfg.lead_times_minutes)
    if cached_records is not None:
        if lead_minutes is not None:
            filtered = [r for r in cached_records if r.lead_minutes == lead_minutes]
            return prov, obs, qual, filtered
        return prov, obs, qual, cached_records

    # Generate nowcast using requested or default method
    engine = create_nowcast_engine(cfg)

    if lead_minutes is not None:
        rec = engine.generate_for_lead(obs, lead_minutes, quality=qual)
        records = [rec] if rec is not None else []
    else:
        records = engine.generate(obs, quality=qual)

    if records:
        _nowcast_cache.put_nowcast(obs, engine_method, cfg.lead_times_minutes, records)

    return prov, obs, qual, records

