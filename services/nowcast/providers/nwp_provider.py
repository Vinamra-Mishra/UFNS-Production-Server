"""Phase D — Real NWP Rainfall Provider.

Implements the RainfallProvider interface for authentic NCMRWF/IMD
Numerical Weather Prediction rasters.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from services.ingestion.grib_netcdf import (
    GLOBAL_REAL_NWP_ENGINE,
    RealNWPDataset,
    RealNWPIngestionEngine,
    get_authoritative_bagjola_grid,
)
from services.nowcast.providers import (
    ProviderHealth,
    ProviderStatus,
    RainfallObservation,
    RainfallProvider,
    SourceType,
)


class RealNWPRainfallProvider(RainfallProvider):
    """Rainfall provider backed by authentic NCMRWF/IMD NWP forecasts."""

    def __init__(
        self,
        *,
        provider_id: str = "ncmrwf-ncum-provider",
        source_name: str = "NCMRWF Regional Unified Model",
        source_type: SourceType = SourceType.REAL,
        ingestion_engine: RealNWPIngestionEngine | None = None,
    ) -> None:
        """Execute   Init   operation and return result."""
        self._provider_id = provider_id
        self._source_name = source_name
        self._source_type = source_type
        self._engine = ingestion_engine or GLOBAL_REAL_NWP_ENGINE
        self._target_grid = self._engine.target_grid
        self._dataset: RealNWPDataset | None = None

        # Check if raw file exists
        discovered = self._engine.discover_raw_file()
        if discovered:
            try:
                self._dataset = self._engine.ingest_file(discovered)
            except Exception:
                self._dataset = None

    @property
    def provider_id(self) -> str:
        """Execute Provider Id operation and return result."""
        return self._provider_id

    @property
    def source_name(self) -> str:
        """Execute Source Name operation and return result."""
        return self._source_name

    @property
    def source_type(self) -> SourceType:
        """Execute Source Type operation and return result."""
        return self._source_type

    @property
    def dataset(self) -> RealNWPDataset | None:
        """Execute Dataset operation and return result."""
        return self._dataset

    def fetch_latest(self) -> Optional[RainfallObservation]:
        """Return the latest available NWP initial step observation."""
        if self._dataset is None or not self._dataset.forecast_steps:
            return None
        step_0 = self._dataset.get_step(0) or next(iter(self._dataset.forecast_steps.values()))
        ref_t = self._dataset.reference_time_utc
        from datetime import timedelta
        return RainfallObservation(
            observation_time=ref_t,
            valid_from=ref_t,
            valid_to=ref_t + timedelta(minutes=15),
            rate_mmh=step_0.precip_rate_mmh,
            source_type=self._source_type,
            source_name=self._source_name,
            source_provider_id=self._provider_id,
            spatial_reference=self._target_grid.crs_wkt_or_epsg,
            spatial_resolution_m=self._target_grid.cell_size_m,
            width=self._target_grid.width,
            height=self._target_grid.height,
            quality_flags=("NWP_FORECAST",),
            metadata={"model_name": self._dataset.model_name, "file_sha256": self._dataset.file_sha256},
        )

    def fetch_observation(self, observation_time: Optional[datetime] = None) -> Optional[RainfallObservation]:
        """Return NWP observation corresponding to the requested time."""
        if not self._dataset or not self._dataset.forecast_steps:
            return None
        if observation_time is None:
            return self.fetch_latest()

        ref_t = self._dataset.reference_time_utc
        delta_sec = (observation_time - ref_t).total_seconds()
        lead_min = int(round(delta_sec / 60.0))
        step = self._dataset.get_step(lead_min)
        if step is None:
            return None

        from datetime import timedelta
        obs_time = step.valid_time_utc
        return RainfallObservation(
            observation_time=obs_time,
            valid_from=obs_time,
            valid_to=obs_time + timedelta(minutes=15),
            rate_mmh=step.precip_rate_mmh,
            source_type=self._source_type,
            source_name=self._source_name,
            source_provider_id=self._provider_id,
            spatial_reference=self._target_grid.crs_wkt_or_epsg,
            spatial_resolution_m=self._target_grid.cell_size_m,
            width=self._target_grid.width,
            height=self._target_grid.height,
            quality_flags=("NWP_FORECAST",),
            metadata={"model_name": self._dataset.model_name, "file_sha256": self._dataset.file_sha256, "lead_minutes": step.lead_minutes},
        )

    def health(self) -> ProviderHealth:
        """Current health status of this provider."""
        has_data = self._dataset is not None and bool(self._dataset.forecast_steps)
        return ProviderHealth(
            provider_id=self._provider_id,
            status=ProviderStatus.HEALTHY if has_data else ProviderStatus.UNAVAILABLE,
            source_type=self._source_type,
            last_observation_time=self._dataset.reference_time_utc if self._dataset else None,
            message="Operational NCMRWF/IMD NWP dataset loaded" if has_data else "No valid NWP dataset ingested",
            metadata={
                "model_name": self._dataset.model_name if self._dataset else None,
                "file_sha256": self._dataset.file_sha256 if self._dataset else None,
                "available_leads": list(self._dataset.forecast_steps.keys()) if self._dataset else [],
            },
        )

    def metadata(self) -> dict[str, Any]:
        """Provider metadata and capabilities."""
        return {
            "provider_id": self._provider_id,
            "source_name": self._source_name,
            "source_type": self._source_type.value,
            "has_dataset": self._dataset is not None,
            "model_name": self._dataset.model_name if self._dataset else None,
            "grid_id": self._target_grid.grid_id,
            "resolution_m": self._target_grid.cell_size_m,
        }

    def get_forecast_grid(self, lead_minutes: int) -> np.ndarray | None:
        """Retrieve 2D precipitation matrix at lead time t."""
        if self._dataset is None:
            return None
        step = self._dataset.get_step(lead_minutes)
        if step is None:
            return None
        return step.precip_rate_mmh


GLOBAL_REAL_NWP_PROVIDER = RealNWPRainfallProvider()
