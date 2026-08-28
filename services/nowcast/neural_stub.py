"""M12/Phase A — PyTorch Spatio-Temporal Deep Learning Nowcaster Interface.

Defines the neural nowcasting interface for ConvLSTM / U-Net / RainNet models
for 0–3 hour radar extrapolation with deterministic fallback to the optical flow
advection engine.

References:
  - Shi, X., et al. (2015). Convolutional LSTM Network: A Machine Learning
    Approach for Precipitation Nowcasting. NeurIPS 2015.
  - Ayzel, G., et al. (2020). RainNet v1.0: a convolutional neural network for
    radar-based precipitation nowcasting. Geoscientific Model Development.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from services.nowcast import NOWCAST_METHOD_NEURAL
from services.nowcast.advection import AdvectionConfig, AdvectionNowcastEngine
from services.nowcast.nowcast_record import NowcastRecord
from services.nowcast.providers import RainfallObservation
from services.nowcast.quality import QualityResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NeuralNowcastConfig:
    """Configuration for Neural Deep Learning Nowcasting."""
    model_name: str = "ConvLSTM-RainNet-v1"
    weights_path: Optional[str] = None
    lead_times_minutes: tuple[int, ...] = (0, 15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180)
    max_lead_minutes: int = 180
    method: str = NOWCAST_METHOD_NEURAL
    use_gpu: bool = False
    status: str = "PROVISIONAL"
    uncertainty: str = "DEEP_LEARNING_ENSEMBLE_PROVISIONAL"


class NeuralNowcastEngine:
    """PyTorch Deep Learning Nowcaster with seamless advection fallback."""

    def __init__(self, config: NeuralNowcastConfig | None = None) -> None:
        """Execute   Init   operation and return result."""
        self._config = config or NeuralNowcastConfig()
        self._torch_available = self._check_torch()
        self._model = None
        self._advection_fallback = AdvectionNowcastEngine(
            AdvectionConfig(
                lead_times_minutes=self._config.lead_times_minutes,
                max_lead_minutes=self._config.max_lead_minutes,
                status=self._config.status,
            )
        )
        if self._torch_available and self._config.weights_path:
            self._load_model()

    @property
    def config(self) -> NeuralNowcastConfig:
        """Execute Config operation and return result."""
        return self._config

    @property
    def is_torch_active(self) -> bool:
        """Execute Is Torch Active operation and return result."""
        return self._torch_available and self._model is not None

    def _check_torch(self) -> bool:
        """Execute  Check Torch operation and return result."""
        try:
            import torch
            return True
        except ImportError:
            return False

    def _load_model(self) -> None:
        """Attempt to load PyTorch model weights from checkpoint."""
        if not self._config.weights_path:
            return
        weights_file = Path(self._config.weights_path)
        if not weights_file.exists():
            logger.warning("Neural nowcast weights not found at %s, using fallback", weights_file)
            return

        try:
            import torch
            self._model = torch.jit.load(str(weights_file))
            self._model.eval()
            logger.info("Loaded PyTorch neural nowcast model from %s", weights_file)
        except Exception as e:
            logger.warning("Failed loading PyTorch model: %s. Using advection fallback.", e)
            self._model = None

    def generate(
        self,
        observation: RainfallObservation,
        previous_observation: RainfallObservation | None = None,
        quality: QualityResult | None = None,
    ) -> list[NowcastRecord]:
        """Generate nowcast records using Neural Model or Advection Fallback.

        Args:
            observation: Current observation.
            previous_observation: Optional historical observation.
            quality: Quality validation.

        Returns:
            List of NowcastRecord instances.
        """
        if quality is not None and not quality.valid:
            return []

        if not self.is_torch_active:
            # Fallback to the advection engine with neural metadata annotations
            records = self._advection_fallback.generate(
                observation=observation,
                previous_observation=previous_observation,
                quality=quality,
            )
            annotated_records: list[NowcastRecord] = []
            for rec in records:
                new_meta = dict(rec.metadata)
                new_meta["neural_engine"] = self._config.model_name
                new_meta["neural_weights_loaded"] = False
                new_meta["engine_execution_mode"] = "DETERMINISTIC_ADVECTION_FALLBACK"

                annotated = NowcastRecord(
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
                    method=self._config.method,
                    status=self._config.status,
                    uncertainty=self._config.uncertainty,
                    quality_flags=tuple(list(rec.quality_flags) + ["NEURAL_FALLBACK"]),
                    metadata=new_meta,
                )
                fp = annotated.compute_fingerprint()
                object.__setattr__(annotated, "fingerprint", fp)
                annotated_records.append(annotated)
            return annotated_records

        # PyTorch active path
        import torch
        with torch.no_grad():
            tensor_in = torch.from_numpy(observation.rate_mmh).float().unsqueeze(0).unsqueeze(0)
            pred_tensor = self._model(tensor_in)
            pred_np = pred_tensor.squeeze().cpu().numpy()

        if pred_np.ndim != 2 or pred_np.shape != observation.rate_mmh.shape:
            logger.warning(
                "Neural prediction shape %s does not match observation shape %s; using advection fallback.",
                getattr(pred_np, "shape", None),
                observation.rate_mmh.shape,
            )
            return self._advection_fallback.generate(
                observation=observation,
                previous_observation=previous_observation,
                quality=quality,
            )

        pred_np = np.nan_to_num(np.maximum(pred_np, 0.0), nan=0.0, posinf=0.0, neginf=0.0)

        # Build records from neural outputs
        records = []
        obs_fp = observation.fingerprint()
        for lead_min in self._config.lead_times_minutes:
            valid_time = observation.observation_time + timedelta(minutes=lead_min)
            decay = float(np.exp(-lead_min / 90.0)) if lead_min > 0 else 1.0
            field_data = (pred_np * decay).copy() if lead_min > 0 else observation.rate_mmh.copy()
            rec = NowcastRecord(
                initialization_time=observation.observation_time,
                valid_time=valid_time,
                lead_minutes=lead_min,
                rate_mmh=field_data,
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
                quality_flags=tuple(list(observation.quality_flags) + [f"NEURAL_LEAD_{lead_min}"]),
                metadata={
                    "observation_fingerprint": obs_fp,
                    "neural_engine": self._config.model_name,
                    "neural_weights_loaded": True,
                    "lead_minutes": lead_min,
                },
            )
            fp = rec.compute_fingerprint()
            object.__setattr__(rec, "fingerprint", fp)
            records.append(rec)

        return records
