"""Phase K — Stochastic Rainfall Perturbation Ensemble Generator.

Generates multi-member stochastic nowcast ensembles spanning precipitation intensity,
convective cloud advection vector uncertainties, and NWP/radar blend variations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, List

import numpy as np


@dataclass(frozen=True)
class EnsembleMember:
    """Ensemblemember schema and data model representation."""
    member_id: str
    name: str
    percentile_tag: str  # P10 | P50 | P90 | STOCHASTIC
    rainfall_multiplier: float
    spatial_shift_row: int
    spatial_shift_col: int
    weight: float

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return asdict(self)


def generate_ensemble_members(count: int = 10) -> list[EnsembleMember]:
    """Generate canonical 10-member stochastic nowcast perturbation ensemble."""
    members: list[EnsembleMember] = [
        # Core distribution anchor members
        EnsembleMember(
            member_id="ENS_01_P10",
            name="10th Percentile (Conservative Attenuation)",
            percentile_tag="P10",
            rainfall_multiplier=0.75,
            spatial_shift_row=0,
            spatial_shift_col=0,
            weight=0.10,
        ),
        EnsembleMember(
            member_id="ENS_02_P50",
            name="50th Percentile (Deterministic Median Baseline)",
            percentile_tag="P50",
            rainfall_multiplier=1.00,
            spatial_shift_row=0,
            spatial_shift_col=0,
            weight=0.20,
        ),
        EnsembleMember(
            member_id="ENS_03_P90",
            name="90th Percentile (Extreme Convective Surge)",
            percentile_tag="P90",
            rainfall_multiplier=1.25,
            spatial_shift_row=0,
            spatial_shift_col=0,
            weight=0.10,
        ),
        # Spatial advection perturbation members
        EnsembleMember(
            member_id="ENS_04_NORTH",
            name="Stochastic Advection North (+60m)",
            percentile_tag="STOCHASTIC",
            rainfall_multiplier=1.05,
            spatial_shift_row=-2,
            spatial_shift_col=0,
            weight=0.10,
        ),
        EnsembleMember(
            member_id="ENS_05_SOUTH",
            name="Stochastic Advection South (-60m)",
            percentile_tag="STOCHASTIC",
            rainfall_multiplier=1.05,
            spatial_shift_row=2,
            spatial_shift_col=0,
            weight=0.10,
        ),
        EnsembleMember(
            member_id="ENS_06_EAST",
            name="Stochastic Advection East (+60m)",
            percentile_tag="STOCHASTIC",
            rainfall_multiplier=1.10,
            spatial_shift_row=0,
            spatial_shift_col=2,
            weight=0.10,
        ),
        EnsembleMember(
            member_id="ENS_07_WEST",
            name="Stochastic Advection West (-60m)",
            percentile_tag="STOCHASTIC",
            rainfall_multiplier=1.10,
            spatial_shift_row=0,
            spatial_shift_col=-2,
            weight=0.10,
        ),
        EnsembleMember(
            member_id="ENS_08_BURST",
            name="Localized Microburst Cell (+20%)",
            percentile_tag="STOCHASTIC",
            rainfall_multiplier=1.20,
            spatial_shift_row=1,
            spatial_shift_col=1,
            weight=0.10,
        ),
        EnsembleMember(
            member_id="ENS_09_DRY",
            name="Rapid Orographic Dissipation (-20%)",
            percentile_tag="STOCHASTIC",
            rainfall_multiplier=0.80,
            spatial_shift_row=-1,
            spatial_shift_col=-1,
            weight=0.05,
        ),
        EnsembleMember(
            member_id="ENS_10_HIGH_STORM",
            name="Multi-Cell Convective Merging (+15%)",
            percentile_tag="STOCHASTIC",
            rainfall_multiplier=1.15,
            spatial_shift_row=1,
            spatial_shift_col=-1,
            weight=0.05,
        ),
    ]

    return members[:count]


@dataclass
class EnsembleSimulationResult:
    """Ensemblesimulationresult schema and data model representation."""
    scenario_id: str
    lead_minutes: int
    member_count: int
    members: list[dict[str, Any]]
    member_metrics: list[dict[str, Any]]
    p10_max_depth_m: float
    p50_max_depth_m: float
    p90_max_depth_m: float
    interquartile_range_m: float

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "scenario_id": self.scenario_id,
            "lead_minutes": self.lead_minutes,
            "member_count": self.member_count,
            "members": self.members,
            "member_metrics": self.member_metrics,
            "summary_confidence_envelope": {
                "p10_max_depth_m": round(self.p10_max_depth_m, 3),
                "p50_max_depth_m": round(self.p50_max_depth_m, 3),
                "p90_max_depth_m": round(self.p90_max_depth_m, 3),
                "interquartile_range_m": round(self.interquartile_range_m, 3),
            },
        }
