"""M12/Phase A — Doppler Weather Radar (DWR) & Satellite Raster Ingestion.

Parses meteorological raster data (Doppler radar reflectivity dBZ, surface
rainfall intensity mm/h, accumulation PAC, and INSAT-3D/3DR satellite QPE),
applies Marshall-Palmer / convective Z-R inversion, performs quality filtering
(clutter / hail capping / nodata masking), and aligns to the target GridSpec.

References:
  - Marshall, J. S., & Palmer, W. M. (1948). The distribution of raindrops with size.
  - Kumar, V., & Remesan, R. (2026). Urban hydrometeorological modeling.
  - IMD Doppler Weather Radar Technical Specifications (MoES, India).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import numpy as np


class RadarProductType(str, Enum):
    """Meteorological radar/satellite product types."""
    REFLECTIVITY_DBZ = "REFLECTIVITY_DBZ"       # Maximum Reflectivity (MAXZ) in dBZ
    RAIN_RATE_MMH = "RAIN_RATE_MMH"             # Surface Rainfall Intensity (SRI) in mm/h
    ACCUMULATION_MM = "ACCUMULATION_MM"         # Precipitation Accumulation (PAC) in mm
    SATELLITE_QPE = "SATELLITE_QPE"             # INSAT-3D/3DR Hydro-Estimator QPE in mm/h


@dataclass(frozen=True)
class ZRRelationship:
    """Z-R power-law relationship: Z = a * R^b <=> R = (10^(dBZ/10) / a)^(1/b).

    Attributes:
        a: Multiplicative coefficient (e.g., 200 for Marshall-Palmer, 300 for convective).
        b: Exponent (e.g., 1.6 for Marshall-Palmer, 1.4 for convective).
        name: Profile name.
        min_dbz: Minimum reflectivity threshold (dBZ) below which rain rate is 0.0.
        max_dbz: Hail cap threshold (dBZ) to prevent unphysical rain rates from hail contamination.
    """
    a: float = 200.0
    b: float = 1.6
    name: str = "Marshall-Palmer (Stratiform)"
    min_dbz: float = 10.0
    max_dbz: float = 55.0

    def dbz_to_rate(self, dbz: np.ndarray) -> np.ndarray:
        """Convert reflectivity dBZ array to rain rate R (mm/h)."""
        dbz_arr = np.asarray(dbz, dtype=np.float64)
        # Cap maximum dBZ to remove hail contamination
        capped_dbz = np.clip(dbz_arr, a_min=-30.0, a_max=self.max_dbz)
        
        # Z = 10^(dBZ / 10) in mm^6 / m^3
        z = np.power(10.0, capped_dbz / 10.0)
        
        # R = (Z / a)^(1 / b)
        rate = np.power(np.maximum(z / self.a, 0.0), 1.0 / self.b)
        
        # Mask out values below minimum detection threshold
        rate[dbz_arr < self.min_dbz] = 0.0
        
        # Ensure zero negative and replace non-finites with 0
        rate = np.nan_to_num(rate, nan=0.0, posinf=0.0, neginf=0.0)
        return np.maximum(rate, 0.0)

    def rate_to_dbz(self, rate: np.ndarray) -> np.ndarray:
        """Convert rain rate R (mm/h) array to reflectivity dBZ."""
        rate_arr = np.asarray(rate, dtype=np.float64)
        safe_rate = np.maximum(rate_arr, 1e-6)
        z = self.a * np.power(safe_rate, self.b)
        dbz = 10.0 * np.log10(np.maximum(z, 1e-10))
        dbz[rate_arr <= 0.0] = -30.0
        return np.nan_to_num(dbz, nan=-30.0, posinf=self.max_dbz, neginf=-30.0)


# Standard Z-R profiles for Indian tropical meteorology (IMD DWR standards)
ZR_MARSHALL_PALMER = ZRRelationship(a=200.0, b=1.6, name="Marshall-Palmer (Stratiform)")
ZR_CONVECTIVE = ZRRelationship(a=300.0, b=1.4, name="Tropical Convective")
ZR_ROSENFELD_TROPICAL = ZRRelationship(a=250.0, b=1.2, name="Deep Convection (Rosenfeld)")


@dataclass(frozen=True)
class RadarRasterMetadata:
    """Metadata describing an ingested radar/satellite raster."""
    source_id: str
    source_name: str
    product_type: RadarProductType
    timestamp: datetime
    spatial_reference: str
    spatial_resolution_m: float
    width: int
    height: int
    zr_profile: str
    rate_mean_mmh: float
    rate_max_mmh: float
    rate_min_mmh: float
    wet_fraction: float
    data_fingerprint: str
    is_real_data: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Execute To Dict operation and return result."""
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "product_type": self.product_type.value,
            "timestamp": self.timestamp.isoformat(),
            "spatial_reference": self.spatial_reference,
            "spatial_resolution_m": self.spatial_resolution_m,
            "width": self.width,
            "height": self.height,
            "zr_profile": self.zr_profile,
            "rate_mean_mmh": round(self.rate_mean_mmh, 4),
            "rate_max_mmh": round(self.rate_max_mmh, 4),
            "rate_min_mmh": round(self.rate_min_mmh, 4),
            "wet_fraction": round(self.wet_fraction, 4),
            "data_fingerprint": self.data_fingerprint,
            "is_real_data": self.is_real_data,
            "metadata": self.metadata,
        }


class RadarRasterParser:
    """Ingests and converts radar/satellite rasters to standardized rainfall fields."""

    def __init__(
        self,
        zr_relationship: ZRRelationship | None = None,
        default_target_shape: tuple[int, int] = (134, 134),
        default_resolution_m: float = 30.0,
        default_crs: str = "EPSG:32645",
    ) -> None:
        """Execute   Init   operation and return result."""
        self.zr = zr_relationship or ZR_MARSHALL_PALMER
        self.target_shape = default_target_shape
        self.target_resolution_m = default_resolution_m
        self.target_crs = default_crs

    def parse_array(
        self,
        data: np.ndarray,
        product_type: RadarProductType,
        timestamp: datetime,
        source_id: str = "IMD_DWR_RADAR",
        source_name: str = "IMD Doppler Weather Radar",
        is_real_data: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, RadarRasterMetadata]:
        """Parse in-memory 2-D array of radar/satellite observations.

        Args:
            data: 2-D array of reflectivity (dBZ) or rain rate (mm/h).
            product_type: Type of the input product.
            timestamp: Observation time (timezone-aware).
            source_id: Source identifier.
            source_name: Human-readable source name.
            is_real_data: Flag indicating whether data is real observed data.
            metadata: Extra dictionary metadata.

        Returns:
            Tuple of (standardized rain rate array in mm/h, metadata record).
        """
        if timestamp.tzinfo is None:
            raise ValueError("Observation timestamp must be timezone-aware")

        raw_arr = np.asarray(data, dtype=np.float64)
        if raw_arr.ndim != 2:
            raise ValueError(f"Radar raster must be 2-D array, got shape {raw_arr.shape}")

        # Convert to rain rate (mm/h) if input is reflectivity
        if product_type == RadarProductType.REFLECTIVITY_DBZ:
            rate_arr = self.zr.dbz_to_rate(raw_arr)
            zr_used = self.zr.name
        elif product_type in (RadarProductType.RAIN_RATE_MMH, RadarProductType.SATELLITE_QPE):
            rate_arr = np.nan_to_num(np.maximum(raw_arr, 0.0), nan=0.0, posinf=0.0, neginf=0.0)
            zr_used = "DIRECT_RATE"
        elif product_type == RadarProductType.ACCUMULATION_MM:
            # Assume 1-hour accumulation if not specified -> mm/h
            rate_arr = np.nan_to_num(np.maximum(raw_arr, 0.0), nan=0.0, posinf=0.0, neginf=0.0)
            zr_used = "ACCUMULATION_DIRECT"
        else:
            raise ValueError(f"Unsupported product type: {product_type}")

        # Resize / resample to target shape if different
        if rate_arr.shape != self.target_shape:
            rate_arr = self._resample_array(rate_arr, self.target_shape)

        rate_float = np.ascontiguousarray(rate_arr, dtype=np.float64)
        rate_float = np.nan_to_num(rate_float, nan=0.0, posinf=0.0, neginf=0.0)
        rate_float = np.maximum(rate_float, 0.0)

        # Compute field metrics and deterministic fingerprint
        wet_mask = rate_float >= 0.1
        wet_frac = float(np.mean(wet_mask)) if rate_float.size > 0 else 0.0
        
        fp_payload = {
            "source_id": source_id,
            "product_type": product_type.value,
            "timestamp": timestamp.isoformat(),
            "shape": list(rate_float.shape),
            "zr": zr_used,
            "hash": hashlib.sha256(rate_float.tobytes()).hexdigest(),
        }
        fp = hashlib.sha256(json.dumps(fp_payload, sort_keys=True).encode("utf-8")).hexdigest()

        meta = RadarRasterMetadata(
            source_id=source_id,
            source_name=source_name,
            product_type=product_type,
            timestamp=timestamp,
            spatial_reference=self.target_crs,
            spatial_resolution_m=self.target_resolution_m,
            width=rate_float.shape[1],
            height=rate_float.shape[0],
            zr_profile=zr_used,
            rate_mean_mmh=float(np.mean(rate_float)),
            rate_max_mmh=float(np.max(rate_float)),
            rate_min_mmh=float(np.min(rate_float)),
            wet_fraction=wet_frac,
            data_fingerprint=fp,
            is_real_data=is_real_data,
            metadata=dict(metadata or {}),
        )

        return rate_float, meta

    def _resample_array(self, arr: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
        """Bilinear spatial resampling of 2-D array to target shape."""
        src_h, src_w = arr.shape
        dst_h, dst_w = target_shape
        if src_h == dst_h and src_w == dst_w:
            return arr

        y_coords = np.linspace(0, src_h - 1, dst_h)
        x_coords = np.linspace(0, src_w - 1, dst_w)
        
        x_idx = np.clip(np.floor(x_coords).astype(int), 0, src_w - 2)
        y_idx = np.clip(np.floor(y_coords).astype(int), 0, src_h - 2)
        
        x_frac = (x_coords - x_idx)[:, np.newaxis]
        y_frac = (y_coords - y_idx)[np.newaxis, :]
        
        # Bilinear interpolation
        top_left = arr[y_idx[:, np.newaxis], x_idx[np.newaxis, :]]
        top_right = arr[y_idx[:, np.newaxis], (x_idx + 1)[np.newaxis, :]]
        bottom_left = arr[(y_idx + 1)[:, np.newaxis], x_idx[np.newaxis, :]]
        bottom_right = arr[(y_idx + 1)[:, np.newaxis], (x_idx + 1)[np.newaxis, :]]
        
        top = top_left * (1.0 - x_frac.T) + top_right * x_frac.T
        bottom = bottom_left * (1.0 - x_frac.T) + bottom_right * x_frac.T
        resampled = top * (1.0 - y_frac.T) + bottom * y_frac.T
        return resampled
