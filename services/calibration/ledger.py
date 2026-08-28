"""Calibration history registry and audit ledger (Phase B).

Provides append-only tracking of calibration sessions, parameter versions,
goodness-of-fit metrics, and scientific provenance validation.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from services.calibration.engine import CalibrationResult


class CalibrationLedger:
    """In-memory and file-backed audit ledger for calibration sessions."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        """Execute   Init   operation and return result."""
        self.storage_path = storage_path
        self._records: dict[str, CalibrationResult] = {}
        if storage_path and storage_path.exists():
            self._load_from_disk()

    def record(self, result: CalibrationResult) -> None:
        """Record a completed calibration session."""
        self._records[result.calibration_id] = result
        if self.storage_path:
            self._save_to_disk()

    def get(self, calibration_id: str) -> Optional[CalibrationResult]:
        """Retrieve a specific calibration record by ID."""
        return self._records.get(calibration_id)

    def list_all(self) -> list[CalibrationResult]:
        """List all recorded calibration results sorted by creation epoch descending."""
        return sorted(self._records.values(), key=lambda r: r.created_at_epoch, reverse=True)

    def count(self) -> int:
        """Execute Count operation and return result."""
        return len(self._records)

    def clear(self) -> None:
        """Execute Clear operation and return result."""
        self._records.clear()

    def _save_to_disk(self) -> None:
        """Execute  Save To Disk operation and return result."""
        if not self.storage_path:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = {cid: res.to_dict() for cid, res in self._records.items()}
        self.storage_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")

    def _load_from_disk(self) -> None:
        """Execute  Load From Disk operation and return result."""
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            content = self.storage_path.read_text(encoding="utf-8").strip()
            if not content:
                return
            data = json.loads(content)
            for cid, item in data.items():
                try:
                    self._records[cid] = CalibrationResult.from_dict(item)
                except Exception:
                    import logging
                    logging.getLogger(__name__).warning("Skipping unreadable calibration record %s", cid, exc_info=True)
        except (OSError, ValueError):
            import logging
            logging.getLogger(__name__).warning("Could not load calibration ledger from %s", self.storage_path, exc_info=True)


# Global singleton instance for the API layer
GLOBAL_CALIBRATION_LEDGER = CalibrationLedger()
