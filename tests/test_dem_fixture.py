"""Synthetic DEM fixture tests (M1; SYNTHETIC — never real terrain)."""

import numpy as np
import rasterio

from services.ingestion.dem import (
    CELL_SIZE_M,
    GRID_CELLS,
    VERTICAL_REFERENCE,
    grid_affine,
    synthetic_dem,
)


def test_fixture_shape_and_stats():
    """Test that fixture shape and stats behaves as expected."""
    z = synthetic_dem()
    assert z.shape == (GRID_CELLS, GRID_CELLS)
    assert z.dtype == np.float32
    assert np.all(np.isfinite(z))
    assert 10.0 < z.min() < 30.0 and 15.0 < z.max() < 40.0


def test_fixture_deterministic():
    """Test that fixture deterministic behaves as expected."""
    a = synthetic_dem(seed=20260821)
    b = synthetic_dem(seed=20260821)
    c = synthetic_dem(seed=1)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_street_corridor_is_lower_than_neighbors():
    """Test that street corridor is lower than neighbors behaves as expected."""
    z = synthetic_dem()
    row = GRID_CELLS // 2
    street_vals = z[row, GRID_CELLS // 4 : 3 * GRID_CELLS // 4]
    away_vals = z[row - 8, GRID_CELLS // 4 : 3 * GRID_CELLS // 4]
    assert np.mean(street_vals) < np.mean(away_vals)  # corridor guides flow


def test_depression_is_intentionally_unfilled():
    """Test that depression is intentionally unfilled behaves as expected."""
    z = synthetic_dem()
    # basin centre (~0.55, 0.72 of domain) must be locally minimal
    by, bx = int(0.72 * GRID_CELLS), int(0.55 * GRID_CELLS)

    # depth of basin relative to its rim
    rim = np.concatenate([z[by - 12, bx - 12 : bx + 13], z[by + 12, bx - 12 : bx + 13]])
    assert z[by, bx] < np.mean(rim)


def test_geotiff_crs_and_transform(tmp_path):
    """Test that geotiff crs and transform behaves as expected."""
    z = synthetic_dem()
    from services.ingestion.dem import write_geotiff

    p = write_geotiff(z, tmp_path / "dem.tif")
    with rasterio.open(p) as src:
        assert src.crs.to_epsg() == 32645
        assert src.res[0] == CELL_SIZE_M
        assert src.tags()["ARENA_PROVENANCE"] == "SYNTHETIC"
        assert src.tags()["ARENA_VERTICAL_REFERENCE"] == VERTICAL_REFERENCE
        loaded = src.read(1)
    assert np.array_equal(loaded, z)
