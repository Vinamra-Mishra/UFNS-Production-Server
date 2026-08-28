"""Hydraulic and hydrological parameter definitions and bounds (Phase B).

Governs parameter validation, clipping, normalization, vectorization, and
reproducibility fingerprinting for urban flood model calibration.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ParameterDefinition:
    """Definition and physical bounds of a calibratable parameter."""

    name: str
    display_name: str
    default_value: float
    min_bound: float
    max_bound: float
    step_size: float
    unit: str
    description: str
    category: str  # "pipe" | "surface" | "infiltration" | "exchange"

    def validate_and_clip(self, value: float) -> float:
        """Validate and clamp value to physical bounds."""
        if not math.isfinite(value):
            return self.default_value
        return float(max(self.min_bound, min(self.max_bound, value)))

    def normalize(self, value: float) -> float:
        """Normalize value to [0.0, 1.0] interval."""
        clipped = self.validate_and_clip(value)
        span = self.max_bound - self.min_bound
        if span <= 1e-12:
            return 0.5
        return float((clipped - self.min_bound) / span)

    def denormalize(self, norm_value: float) -> float:
        """Denormalize [0.0, 1.0] value back to physical units."""
        norm_clipped = max(0.0, min(1.0, float(norm_value)))
        val = self.min_bound + norm_clipped * (self.max_bound - self.min_bound)
        return float(val)


# ---------------------------------------------------------------------------
# Standard Urban Flood Physics Calibratable Parameters
# ---------------------------------------------------------------------------

DEFAULT_PARAMETER_DEFINITIONS: dict[str, ParameterDefinition] = {
    "pipe_manning_n": ParameterDefinition(
        name="pipe_manning_n",
        display_name="Conduit Manning Roughness (n_pipe)",
        default_value=0.013,
        min_bound=0.009,
        max_bound=0.040,
        step_size=0.001,
        unit="s/m^(1/3)",
        description="Hydraulic wall roughness for closed drainage conduits.",
        category="pipe",
    ),
    "surface_manning_n": ParameterDefinition(
        name="surface_manning_n",
        display_name="Overland Manning Roughness (n_surface)",
        default_value=0.030,
        min_bound=0.010,
        max_bound=0.150,
        step_size=0.005,
        unit="s/m^(1/3)",
        description="Surface overland flow friction coefficient (streets, pavement, grass).",
        category="surface",
    ),
    "blockage_ratio": ParameterDefinition(
        name="blockage_ratio",
        display_name="Conduit Siltation / Blockage Ratio (beta)",
        default_value=0.0,
        min_bound=0.0,
        max_bound=0.90,
        step_size=0.05,
        unit="fraction [0-1]",
        description="Effective hydraulic capacity reduction ratio due to sediment or debris.",
        category="pipe",
    ),
    "cd_orifice": ParameterDefinition(
        name="cd_orifice",
        display_name="Inlet Orifice Discharge Coefficient (Cd)",
        default_value=0.60,
        min_bound=0.20,
        max_bound=0.95,
        step_size=0.05,
        unit="dimensionless",
        description="Inlet capture and return orifice discharge efficiency.",
        category="exchange",
    ),
    "horton_f0_mmh": ParameterDefinition(
        name="horton_f0_mmh",
        display_name="Horton Initial Infiltration Capacity (f0)",
        default_value=25.0,
        min_bound=5.0,
        max_bound=100.0,
        step_size=2.5,
        unit="mm/h",
        description="Initial infiltration capacity rate of dry surface soil.",
        category="infiltration",
    ),
    "horton_fmin_mmh": ParameterDefinition(
        name="horton_fmin_mmh",
        display_name="Horton Asymptotic Infiltration Capacity (f_min)",
        default_value=2.0,
        min_bound=0.5,
        max_bound=25.0,
        step_size=0.5,
        unit="mm/h",
        description="Saturated asymptotic infiltration rate.",
        category="infiltration",
    ),
    "horton_decay_k": ParameterDefinition(
        name="horton_decay_k",
        display_name="Horton Infiltration Decay Rate (k)",
        default_value=1.0 / 1800.0,
        min_bound=0.0001,
        max_bound=0.0050,
        step_size=0.0002,
        unit="1/s",
        description="Exponential rate decay constant for soil wetting.",
        category="infiltration",
    ),
    "microstore_m": ParameterDefinition(
        name="microstore_m",
        display_name="Micro-Depression Storage Depth (S_micro)",
        default_value=0.002,
        min_bound=0.0005,
        max_bound=0.0100,
        step_size=0.0005,
        unit="m",
        description="Initial surface depression retention depth before overland flow initiation.",
        category="surface",
    ),
}


@dataclass
class CalibrationParameterSet:
    """Strongly-typed parameter container with bounds enforcement and hashing."""

    pipe_manning_n: float = 0.013
    surface_manning_n: float = 0.030
    blockage_ratio: float = 0.0
    cd_orifice: float = 0.60
    horton_f0_mmh: float = 25.0
    horton_fmin_mmh: float = 2.0
    horton_decay_k: float = 1.0 / 1800.0
    microstore_m: float = 0.002
    extra_params: dict[str, float] = field(default_factory=dict)

    def validate_and_clip(self, definitions: Optional[dict[str, ParameterDefinition]] = None) -> CalibrationParameterSet:
        """Return a clean parameter set with all values validated and clipped to bounds."""
        defs = definitions or DEFAULT_PARAMETER_DEFINITIONS
        return CalibrationParameterSet(
            pipe_manning_n=defs["pipe_manning_n"].validate_and_clip(self.pipe_manning_n),
            surface_manning_n=defs["surface_manning_n"].validate_and_clip(self.surface_manning_n),
            blockage_ratio=defs["blockage_ratio"].validate_and_clip(self.blockage_ratio),
            cd_orifice=defs["cd_orifice"].validate_and_clip(self.cd_orifice),
            horton_f0_mmh=defs["horton_f0_mmh"].validate_and_clip(self.horton_f0_mmh),
            horton_fmin_mmh=defs["horton_fmin_mmh"].validate_and_clip(self.horton_fmin_mmh),
            horton_decay_k=defs["horton_decay_k"].validate_and_clip(self.horton_decay_k),
            microstore_m=defs["microstore_m"].validate_and_clip(self.microstore_m),
            extra_params=dict(self.extra_params),
        )

    def get_effective_conduit_diameter(self, nominal_diameter_m: float) -> float:
        """Compute effective hydraulic diameter under Manning full-bore blockage.

        Capacity ratio Q_blocked / Q_clean = (1 - beta)
        Since Manning Q ~ D^(8/3), effective diameter D_eff = D_0 * (1 - beta)^(3/8).
        """
        beta = max(0.0, min(0.95, float(self.blockage_ratio)))
        remaining_capacity = max(0.01, 1.0 - beta)
        d_eff = nominal_diameter_m * (remaining_capacity ** (3.0 / 8.0))
        return float(d_eff)

    def to_vector(self, param_names: Sequence[str]) -> list[float]:
        """Convert selected parameters to a float vector for optimization solvers."""
        vec: list[float] = []
        for name in param_names:
            if hasattr(self, name):
                vec.append(float(getattr(self, name)))
            elif name in self.extra_params:
                vec.append(float(self.extra_params[name]))
            else:
                raise KeyError(f"Unknown parameter name {name!r}")
        return vec

    @classmethod
    def from_vector(
        cls,
        vec: Sequence[float],
        param_names: Sequence[str],
        base: Optional[CalibrationParameterSet] = None,
    ) -> CalibrationParameterSet:
        """Construct parameter set from an optimization vector on top of a base set."""
        if len(vec) != len(param_names):
            raise ValueError(f"Vector length {len(vec)} does not match param names {len(param_names)}")

        base_params = base or cls()
        kwargs: dict[str, Any] = {
            "pipe_manning_n": base_params.pipe_manning_n,
            "surface_manning_n": base_params.surface_manning_n,
            "blockage_ratio": base_params.blockage_ratio,
            "cd_orifice": base_params.cd_orifice,
            "horton_f0_mmh": base_params.horton_f0_mmh,
            "horton_fmin_mmh": base_params.horton_fmin_mmh,
            "horton_decay_k": base_params.horton_decay_k,
            "microstore_m": base_params.microstore_m,
            "extra_params": dict(base_params.extra_params),
        }

        for val, name in zip(vec, param_names):
            if name in kwargs:
                kwargs[name] = float(val)
            else:
                kwargs["extra_params"][name] = float(val)

        return cls(**kwargs).validate_and_clip()

    def to_dict(self) -> dict[str, float]:
        """Execute To Dict operation and return result."""
        d = {
            "pipe_manning_n": round(self.pipe_manning_n, 6),
            "surface_manning_n": round(self.surface_manning_n, 6),
            "blockage_ratio": round(self.blockage_ratio, 4),
            "cd_orifice": round(self.cd_orifice, 4),
            "horton_f0_mmh": round(self.horton_f0_mmh, 4),
            "horton_fmin_mmh": round(self.horton_fmin_mmh, 4),
            "horton_decay_k": round(self.horton_decay_k, 8),
            "microstore_m": round(self.microstore_m, 6),
        }
        for k, v in self.extra_params.items():
            d[k] = round(float(v), 6)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalibrationParameterSet:
        """Construct a parameter set from a serialized dictionary."""
        known = {
            "pipe_manning_n", "surface_manning_n", "blockage_ratio", "cd_orifice",
            "horton_f0_mmh", "horton_fmin_mmh", "horton_decay_k", "microstore_m"
        }
        kwargs: dict[str, Any] = {}
        extra: dict[str, float] = {}
        for k, v in d.items():
            if k in known:
                kwargs[k] = float(v)
            else:
                extra[k] = float(v)
        kwargs["extra_params"] = extra
        return cls(**kwargs)

    def fingerprint(self) -> str:
        """Deterministic SHA-256 fingerprint of parameter values."""
        serialized = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
