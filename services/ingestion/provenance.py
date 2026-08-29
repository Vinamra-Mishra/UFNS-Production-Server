"""Provenance, manifests, checksums, fingerprints (ARCHITECTURE §7, §9)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from services.contracts import DataLineage, ProvenanceClass, QualityFlag


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """Execute Sha256 File operation and return result."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Execute Sha256 Bytes operation and return result."""
    return hashlib.sha256(data).hexdigest()


def make_lineage(
    dataset_id: str,
    version: str,
    source_name: str,
    provenance_class: ProvenanceClass,
    content: Path | bytes,
    licence_id: Optional[str] = None,
    source_url: Optional[str] = None,
    quality_flags: Optional[list[QualityFlag]] = None,
    native_crs: Optional[str] = None,
    native_resolution: Optional[dict[str, Any]] = None,
    processing_steps: Optional[list[str]] = None,
    acquired_at: Optional[datetime] = None,
) -> DataLineage:
    """Execute Make Lineage operation and return result."""
    digest = sha256_file(content) if isinstance(content, Path) else sha256_bytes(content)
    return DataLineage(
        dataset_id=dataset_id,
        version=version,
        source_name=source_name,
        source_url=source_url,
        licence_id=licence_id,
        acquired_at=acquired_at or datetime.now(timezone.utc),
        content_sha256=digest,
        provenance_class=provenance_class,
        quality_flags=quality_flags or [],
        native_crs=native_crs,
        native_resolution=native_resolution,
        processing_steps=processing_steps or [],
    )


class Manifest:
    """Versioned pilot/demo bundle manifest (DATA_SOURCES §10)."""

    def __init__(self, pilot_id: str, base_dir: Optional[Path] = None) -> None:
        """Execute   Init   operation and return result."""
        self.pilot_id = pilot_id
        self.base_dir = base_dir
        self.assets: list[dict[str, Any]] = []

    def add_asset(
        self,
        role: str,
        path: Path,
        lineage: DataLineage,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        """Execute Add Asset operation and return result."""
        p = Path(path)
        if self.base_dir is not None:
            base_p = Path(self.base_dir).resolve()
            candidate = p if p.is_absolute() else base_p / p
            try:
                uri = str(candidate.resolve().relative_to(base_p))
            except ValueError:
                raise ValueError(f"Asset path {p} is outside base_dir {self.base_dir}") from None
            if not p.is_absolute():
                uri = str(p)
        else:
            uri = str(p)

        base = {
            "role": role,
            "asset_uri": uri,
            "content_sha256": lineage.content_sha256,
            "provenance_class": lineage.provenance_class.value,
            "quality_flags": [f.value for f in lineage.quality_flags],
            "licence_id": lineage.licence_id,
            "native_crs": lineage.native_crs,
            "native_resolution": lineage.native_resolution,
        }
        if extra:
            for k, v in extra.items():
                if k not in base:
                    base[k] = v
        self.assets.append(base)

    def write(self, out_path: Path, extra: Optional[dict[str, Any]] = None, created_at: Optional[datetime] = None) -> Path:
        """Execute Write operation and return result."""
        from services.ingestion.timeutil import iso_utc

        doc = {
            "pilot_id": self.pilot_id,
            "bundle_version": "v1",
            "created_at": iso_utc(created_at or datetime.now(timezone.utc)),
            "interchange_crs": "OGC:CRS84",
            "assets": self.assets,
        }
        if extra:
            for k, v in extra.items():
                if k not in doc:
                    doc[k] = v
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(doc, indent=2))
        return out_path
