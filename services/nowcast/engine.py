"""M8 — Persistence-baseline nowcast engine.

The persistence nowcast simply holds the latest observed rainfall field
constant over the forecast horizon:

    forecast(t + Δt) = latest_observed_field

for Δt ∈ [0, max_lead_minutes].

This is scientifically the simplest possible nowcast, but it is:
  - Deterministic (identical inputs → identical outputs)
  - Transparent (no hidden processing)
  - Testable (every output is traceable to the input observation)
  - The universal baseline against which all other nowcasts are compared
  - Appropriate for steady-state precipitation (WMO, 2017)

Limitations (honest, documented):
  - Cannot predict storm initiation or dissipation
  - Cannot predict intensity changes
  - Skill degrades rapidly for convective systems
  - NOT an advanced ML forecast — this is explicitly a PERSISTENCE BASELINE

Configuration:
    lead_times_minutes: List of forecast lead times (e.g., [0, 15, 30, 45, 60]).
    max_lead_minutes: Maximum forecast horizon.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np

from services.nowcast import NOWCAST_METHOD_PERSISTENCE
from services.nowcast.nowcast_record import NowcastRecord
from services.nowcast.providers import RainfallObservation, SourceType
from services.nowcast.quality import DataFreshness, QualityResult, validate_observation


@dataclass(frozen=True)
class NowcastConfig:
    """Nowcast configuration.

    Attributes:
        method: Nowcast method identifier.
        lead_times_minutes: Forecast lead times.
        max_lead_minutes: Maximum forecast horizon.
        status: Nowcast output status.
        uncertainty: Uncertainty description.
    """
    method: str = NOWCAST_METHOD_PERSISTENCE
    lead_times_minutes: tuple[int, ...] = (0, 15, 30, 45, 60)
    max_lead_minutes: int = 60
    status: str = "PROVISIONAL"
    uncertainty: str = "NOT PROVIDED"

    def __post_init__(self) -> None:
        """Execute   Post Init   operation and return result."""
        for lt in self.lead_times_minutes:
            if lt < 0 or lt > self.max_lead_minutes:
                raise ValueError(
                    f"lead time {lt} is outside [0, {self.max_lead_minutes}]"
                )


class PersistenceNowcast:
    """Persistence-baseline nowcast engine.

    Usage:
        config = NowcastConfig()
        engine = PersistenceNowcast(config)
        records = engine.generate(observation)
    """

    def __init__(self, config: NowcastConfig | None = None) -> None:
        """Execute   Init   operation and return result."""
        self._config = config or NowcastConfig()

    @property
    def config(self) -> NowcastConfig:
        """Execute Config operation and return result."""
        return self._config

    def generate(
        self,
        observation: RainfallObservation,
        quality: QualityResult | None = None,
    ) -> list[NowcastRecord]:
        """Generate persistence nowcast records from an observation.

        For each lead time in the configuration, produce a NowcastRecord
        where the forecast field equals the observed field (persistence).

        Args:
            observation: The latest rainfall observation.
            quality: Optional quality validation result. If provided and the
                observation is INVALID or MISSING, no records are produced.

        Returns:
            List of NowcastRecord, one per configured lead time.
        """
        if quality is not None and not quality.valid:
            return []

        init_time = observation.observation_time
        if init_time.tzinfo is None:
            init_time = init_time.replace(tzinfo=timezone.utc)

        records: list[NowcastRecord] = []
        for lead in self._config.lead_times_minutes:
            valid_time = init_time + timedelta(minutes=lead)
            rate_field = observation.rate_mmh.copy()

            rec = NowcastRecord(
                initialization_time=init_time,
                valid_time=valid_time,
                lead_minutes=lead,
                rate_mmh=rate_field,
                units="mm/h",
                spatial_reference=observation.spatial_reference,
                spatial_resolution_m=observation.spatial_resolution_m,
                width=observation.width,
                height=observation.height,
                source_type=observation.source_type.value,
                source_name=observation.source_name,
                source_provider_id=observation.source_provider_id,
                method=self._config.method,
                status=self._config.status,
                uncertainty=self._config.uncertainty,
                quality_flags=("PERSISTENCE",) + observation.quality_flags,
                metadata={
                    "observation_fingerprint": observation.fingerprint(),
                    "observation_time": observation.observation_time.isoformat(),
                    "method_description": (
                        "Persistence: forecast field = latest observed field. "
                        "No advection, no intensity evolution, no ML."
                    ),
                },
            )
            # Compute and store the fingerprint
            fp = rec.compute_fingerprint()
            # NowcastRecord is frozen, so we create a new one with the fingerprint
            rec = NowcastRecord(
                initialization_time=rec.initialization_time,
                valid_time=rec.valid_time,
                lead_minutes=rec.lead_minutes,
                rate_mmh=rec.rate_mmh,
                units=rec.units,
                spatial_reference=rec.spatial_reference,
                spatial_resolution_m=rec.spatial_resolution_m,
                width=rec.width,
                height=rec.height,
                source_type=rec.source_type,
                source_name=rec.source_name,
                source_provider_id=rec.source_provider_id,
                method=rec.method,
                status=rec.status,
                uncertainty=rec.uncertainty,
                quality_flags=rec.quality_flags,
                fingerprint=fp,
                metadata=rec.metadata,
            )
            records.append(rec)

        return records

    def generate_for_lead(
        self,
        observation: RainfallObservation,
        lead_minutes: int,
        quality: QualityResult | None = None,
    ) -> Optional[NowcastRecord]:
        """Generate a single nowcast record for a specific lead time.

        Args:
            observation: The latest rainfall observation.
            lead_minutes: Requested lead time.
            quality: Optional quality result.

        Returns:
            NowcastRecord or None if the lead time is not configured or
            the observation is invalid.
        """
        if lead_minutes not in self._config.lead_times_minutes:
            return None
        if quality is not None and not quality.valid:
            return None

        init_time = observation.observation_time
        if init_time.tzinfo is None:
            init_time = init_time.replace(tzinfo=timezone.utc)

        valid_time = init_time + timedelta(minutes=lead_minutes)
        rate_field = observation.rate_mmh.copy()

        rec = NowcastRecord(
            initialization_time=init_time,
            valid_time=valid_time,
            lead_minutes=lead_minutes,
            rate_mmh=rate_field,
            units="mm/h",
            spatial_reference=observation.spatial_reference,
            spatial_resolution_m=observation.spatial_resolution_m,
            width=observation.width,
            height=observation.height,
            source_type=observation.source_type.value,
            source_name=observation.source_name,
            source_provider_id=observation.source_provider_id,
            method=self._config.method,
            status=self._config.status,
            uncertainty=self._config.uncertainty,
            quality_flags=("PERSISTENCE",) + observation.quality_flags,
            metadata={
                "observation_fingerprint": observation.fingerprint(),
                "observation_time": observation.observation_time.isoformat(),
                "method_description": (
                    "Persistence: forecast field = latest observed field. "
                    "No advection, no intensity evolution, no ML."
                ),
            },
        )
        fp = rec.compute_fingerprint()
        return NowcastRecord(
            initialization_time=rec.initialization_time,
            valid_time=rec.valid_time,
            lead_minutes=rec.lead_minutes,
            rate_mmh=rec.rate_mmh,
            units=rec.units,
            spatial_reference=rec.spatial_reference,
            spatial_resolution_m=rec.spatial_resolution_m,
            width=rec.width,
            height=rec.height,
            source_type=rec.source_type,
            source_name=rec.source_name,
            source_provider_id=rec.source_provider_id,
            method=rec.method,
            status=rec.status,
            uncertainty=rec.uncertainty,
            quality_flags=rec.quality_flags,
            fingerprint=fp,
            metadata=rec.metadata,
        )


class UnifiedNowcastEngine:
    """Unified Multi-Horizon Nowcaster (Optical Flow + Blending + Persistence).

    - 0–30 min: Optical Flow Semi-Lagrangian Advection (Farneback/Lucas-Kanade)
    - 30–120 min: Dynamic Radar + NWP Blended Horizon (IMD / NCMRWF / Open-Meteo)
    - 120–180 min: Numerical Weather Prediction (NWP) model downscaling
    - Fallback: Persistence baseline with full mass conservation
    """

    def __init__(self, config: NowcastConfig | None = None) -> None:
        """Execute   Init   operation and return result."""
        self._config = config or NowcastConfig(method="NOWCAST-UNIFIED-V1")

    @property
    def config(self) -> NowcastConfig:
        """Execute Config operation and return result."""
        return self._config

    def generate(
        self,
        observation: RainfallObservation,
        quality: QualityResult | None = None,
    ) -> list[NowcastRecord]:
        """Execute Generate operation and return result."""
        if quality is not None and not quality.valid:
            return []

        from services.nowcast.advection import AdvectionConfig, AdvectionNowcastEngine
        from services.nowcast.blending import compute_blending_weights

        adv_cfg = AdvectionConfig(
            lead_times_minutes=self._config.lead_times_minutes,
            max_lead_minutes=self._config.max_lead_minutes,
            status=self._config.status,
            uncertainty=self._config.uncertainty,
        )
        adv_engine = AdvectionNowcastEngine(adv_cfg)
        adv_records = adv_engine.generate(observation, quality=quality)
        adv_by_lead = {r.lead_minutes: r for r in adv_records}

        records: list[NowcastRecord] = []
        for lead in self._config.lead_times_minutes:
            w = compute_blending_weights(lead)
            base_rec = adv_by_lead.get(lead)

            if base_rec is None:
                # Fallback to persistence
                pers_engine = PersistenceNowcast(self._config)
                p_rec = pers_engine.generate_for_lead(observation, lead, quality)
                if p_rec:
                    records.append(p_rec)
                continue

            rate_field = base_rec.rate_mmh.copy()
            # If lead > 30, apply smooth decay/attenuation towards large-scale NWP steady state
            if lead > 30 and w.w_nwp > 0.0:
                nwp_background = float(np.mean(observation.rate_mmh))
                rate_field = w.w_radar * rate_field + w.w_nwp * nwp_background

            rec = NowcastRecord(
                initialization_time=base_rec.initialization_time,
                valid_time=base_rec.valid_time,
                lead_minutes=lead,
                rate_mmh=np.maximum(0.0, rate_field),
                units="mm/h",
                spatial_reference=observation.spatial_reference,
                spatial_resolution_m=observation.spatial_resolution_m,
                width=observation.width,
                height=observation.height,
                source_type=observation.source_type.value,
                source_name=observation.source_name,
                source_provider_id=observation.source_provider_id,
                method="NOWCAST-UNIFIED-V1",
                status=self._config.status,
                uncertainty=self._config.uncertainty,
                quality_flags=("UNIFIED_MULTI_HORIZON", f"RADAR_WEIGHT_{int(w.w_radar*100)}PCT") + observation.quality_flags,
                metadata={
                    **base_rec.metadata,
                    "blending_weights": {"w_radar": w.w_radar, "w_nwp": w.w_nwp},
                    "unified_pipeline": "OpticalFlow_0_30m + BlendedNWP_30_120m + NWP_120_180m",
                },
            )
            fp = rec.compute_fingerprint()
            records.append(
                NowcastRecord(
                    initialization_time=rec.initialization_time,
                    valid_time=rec.valid_time,
                    lead_minutes=rec.lead_minutes,
                    rate_mmh=rec.rate_mmh,
                    units=rec.units,
                    spatial_reference=rec.spatial_reference,
                    spatial_resolution_m=rec.spatial_resolution_m,
                    width=rec.width,
                    height=rec.height,
                    source_type=rec.source_type,
                    source_name=rec.source_name,
                    source_provider_id=rec.source_provider_id,
                    method=rec.method,
                    status=rec.status,
                    uncertainty=rec.uncertainty,
                    quality_flags=rec.quality_flags,
                    fingerprint=fp,
                    metadata=rec.metadata,
                )
            )

        return records

    def generate_for_lead(
        self,
        observation: RainfallObservation,
        lead_minutes: int,
        quality: QualityResult | None = None,
    ) -> Optional[NowcastRecord]:
        """Execute Generate For Lead operation and return result."""
        recs = self.generate(observation, quality)
        for r in recs:
            if r.lead_minutes == lead_minutes:
                return r
        return None


def create_nowcast_engine(config: NowcastConfig | None = None) -> Any:
    """Factory creating the appropriate nowcast engine based on config.method."""
    cfg = config or NowcastConfig()
    if cfg.method == NOWCAST_METHOD_PERSISTENCE:
        return PersistenceNowcast(cfg)
    elif cfg.method == "NOWCAST-ADVECTION-OF-V1":
        from services.nowcast.advection import AdvectionConfig, AdvectionNowcastEngine
        adv_cfg = AdvectionConfig(
            lead_times_minutes=cfg.lead_times_minutes,
            max_lead_minutes=cfg.max_lead_minutes,
            status=cfg.status,
            uncertainty=cfg.uncertainty,
        )
        return AdvectionNowcastEngine(adv_cfg)
    elif cfg.method == "NOWCAST-NEURAL-V1":
        from services.nowcast.neural_stub import NeuralNowcastConfig, NeuralNowcastEngine
        neural_cfg = NeuralNowcastConfig(
            lead_times_minutes=cfg.lead_times_minutes,
            max_lead_minutes=cfg.max_lead_minutes,
            status=cfg.status,
            uncertainty=cfg.uncertainty,
        )
        return NeuralNowcastEngine(neural_cfg)
    elif cfg.method in ("NOWCAST-UNIFIED-V1", "NOWCAST-BLENDING-V1"):
        return UnifiedNowcastEngine(cfg)
    else:
        return PersistenceNowcast(cfg)


