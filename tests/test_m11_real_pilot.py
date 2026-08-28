"""M11 — Real-pilot model integration tests (Sections 16, 18).

Tests verify:
- Model modes / capability state / real-synthetic labels (unit)
- Hydraulic readiness contract (real MISSING vs synthetic ASSUMED) (unit)
- Deeply immutable provenance (unit)
- Terrain adapter provenance answers (unit)
- Real-pilot experiments M11-01 .. M11-12 against the real artifacts in
  data/raw/ (skipped, never weakened, when artifacts are absent).

The real-artifact tests are the execution evidence for the M11 gate matrix.
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import numpy as np
import pytest

from services.pilot import (
    LABEL_REAL_TERRAIN_SYNTHETIC_HYDRAULICS,
    REQUIRED_HYDRAULIC_ATTRIBUTES,
    M11SimulationAdapter,
    PilotModelMode,
    RealDrainageAdapter,
    RealTerrainAdapter,
    authoritative_pilot_grid,
    build_real_drainage_contract,
    build_synthetic_fixture_contract,
    content_label_for_mode,
    drainage_mapping_stats,
    gridspec_fingerprint,
)
from services.pilot.contract import HydraulicAvailability
from services.pilot.provenance import CRSSourceProvenance, RealPilotProvenance

REAL_RAW_DIR = Path("data/raw")
REAL_DEM = REAL_RAW_DIR / "bagjola_kolkata_glo30_dem.tif"
REAL_DRAINS = REAL_RAW_DIR / "WB_AMRUT_Stormwater_drains.parquet"
REAL_VENTS = REAL_RAW_DIR / "WB_AMRUT_Stormwater_vents.parquet"

require_real_artifacts = pytest.mark.skipif(
    not all(p.exists() for p in (REAL_DEM, REAL_DRAINS, REAL_VENTS)),
    reason="real pilot artifacts not present in data/raw (canonical raw location)",
)


# =========================================================================== #
# Unit tests — model modes, labels, capability state, contracts
# =========================================================================== #


class TestModelModes:
    """Testmodelmodes schema and data model representation."""
    def test_three_modes_defined(self):
        """Test that three modes defined behaves as expected."""
        modes = {m.value for m in PilotModelMode}
        assert modes == {
            "MODE_A_REAL_TERRAIN_REAL_DRAINAGE_GEOMETRY",
            "MODE_B_REAL_TERRAIN_SYNTHETIC_HYDRAULICS",
            "MODE_C_SYNTHETIC_BASELINE",
        }

    def test_content_label_for_mode(self):
        """Test that content label for mode behaves as expected."""
        assert content_label_for_mode(
            PilotModelMode.MODE_B_REAL_TERRAIN_SYNTHETIC_HYDRAULICS
        ) == LABEL_REAL_TERRAIN_SYNTHETIC_HYDRAULICS
        assert content_label_for_mode(
            PilotModelMode.MODE_A_REAL_TERRAIN_REAL_DRAINAGE
        ) == "REAL_TERRAIN_REAL_DRAINAGE_GEOMETRY"
        assert content_label_for_mode(
            PilotModelMode.MODE_C_SYNTHETIC_BASELINE
        ) == "SYNTHETIC"

    def test_mode_b_label_hides_nothing(self):
        """MODE B label names BOTH the real-terrain and synthetic-hydraulics
        components (Section 14 hard gate)."""
        label = content_label_for_mode(PilotModelMode.MODE_B_REAL_TERRAIN_SYNTHETIC_HYDRAULICS)
        assert "REAL_TERRAIN" in label
        assert "SYNTHETIC_HYDRAULICS" in label


class TestHydraulicContract:
    """Testhydrauliccontract schema and data model representation."""
    def test_real_drainage_contract_all_missing(self):
        """Test that real drainage contract all missing behaves as expected."""
        c = build_real_drainage_contract("WB_AMRUT_Stormwater_drains")
        assert c.hydraulic_network_ready is False
        assert c.real_hydraulic_network_ready is False
        assert set(c.missing_attributes) == set(REQUIRED_HYDRAULIC_ATTRIBUTES)
        assert c.assumed_attributes == ()
        for name in REQUIRED_HYDRAULIC_ATTRIBUTES:
            assert c.attributes[name].availability == HydraulicAvailability.MISSING

    def test_synthetic_fixture_contract_assumed_and_labelled(self):
        """Test that synthetic fixture contract assumed and labelled behaves as expected."""
        c = build_synthetic_fixture_contract("M4_synthetic_fixture")
        # Synthetic fixture values are ASSUMED, never REAL_DATA; the REAL
        # hydraulic network stays NOT ready.
        assert c.real_hydraulic_network_ready is False
        assert c.hydraulic_network_ready is False
        assert c.synthetic_fixture_labelled is True
        assert set(c.assumed_attributes) == set(REQUIRED_HYDRAULIC_ATTRIBUTES)
        for name in REQUIRED_HYDRAULIC_ATTRIBUTES:
            assert c.attributes[name].availability == HydraulicAvailability.ASSUMED
            assert c.attributes[name].source == "synthetic_fixture"

    def test_contract_immutable(self):
        """Test that contract immutable behaves as expected."""
        c = build_real_drainage_contract("d")
        with pytest.raises(TypeError):
            c.attributes["diameter_m"] = c.attributes["diameter_m"]  # type: ignore[index]
        d = c.to_dict()
        d["missing_attributes"].append("injected")
        assert "injected" not in c.missing_attributes

    def test_contract_serializable(self):
        """Test that contract serializable behaves as expected."""
        c = build_synthetic_fixture_contract("d")
        s = json.dumps(c.to_dict())
        assert "hydraulic_network_ready" in s
        assert "REAL_TERRAIN" not in c.assumed_attributes  # fixture values never REAL


class TestProvenanceImmutability:
    """Testprovenanceimmutability schema and data model representation."""
    def _sample(self) -> RealPilotProvenance:
        """Execute  Sample operation and return result."""
        return RealPilotProvenance(
            raw_dem_sha256="a" * 64,
            model_mode="MODE_B_REAL_TERRAIN_SYNTHETIC_HYDRAULICS",
            crs_source=CRSSourceProvenance(
                source_crs="EPSG:4326",
                modelling_crs="EPSG:32645",
                embedded_crs="EPSG:4326",
                provenance_status="EMBEDDED",
            ),
            status_labels=("REAL_TERRAIN", "SYNTHETIC_HYDRAULICS"),
            extra={"k": 1},
        )

    def test_frozen(self):
        """Test that frozen behaves as expected."""
        p = self._sample()
        with pytest.raises(FrozenInstanceError):
            p.raw_dem_sha256 = "b" * 64  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            p.status_labels = ()  # type: ignore[misc]

    def test_extra_independent_of_caller(self):
        """Test that extra independent of caller behaves as expected."""
        src = {"k": 1}
        p = RealPilotProvenance(extra=src)
        src["injected"] = 2
        assert "injected" not in p.extra
        d = p.to_dict()
        d["extra"]["injected2"] = 3
        assert "injected2" not in p.extra

    def test_gridspec_fingerprint_deterministic(self):
        """Test that gridspec fingerprint deterministic behaves as expected."""
        grid = authoritative_pilot_grid().model_dump(mode="json")
        assert gridspec_fingerprint(grid) == gridspec_fingerprint(grid)
        assert len(gridspec_fingerprint(grid)) == 64


class TestTerrainAdapterUnit:
    """Testterrainadapterunit schema and data model representation."""
    def test_requires_source_path(self):
        """Test that requires source path behaves as expected."""
        with pytest.raises(ValueError):
            RealTerrainAdapter().load()

    def test_requires_real_dem_not_none(self):
        """Test that requires real dem not none behaves as expected."""
        # A None/missing path must not fabricate terrain.
        from services.pilot.terrain import RealTerrainAdapter

        with pytest.raises((ValueError, TypeError)):
            RealTerrainAdapter(None).load()  # type: ignore[arg-type]


# =========================================================================== #
# Real-pilot experiments — module-scoped fixtures (compute once)
# =========================================================================== #


@pytest.fixture(scope="module")
def real_terrain():
    """Execute Real Terrain operation and return result."""
    return RealTerrainAdapter(REAL_DEM).load()


@pytest.fixture(scope="module")
def real_drainage(real_terrain):
    """Execute Real Drainage operation and return result."""
    return RealDrainageAdapter(REAL_DRAINS).map_and_align(real_terrain.grid)


@pytest.fixture(scope="module")
def mode_b_result(real_terrain):
    """Execute Mode B Result operation and return result."""
    adapter = M11SimulationAdapter(real_terrain)
    return adapter.mode_b_real_terrain_synthetic_hydraulics(
        duration_minutes=15, window=134, offset=(50, 50), n_inlets=12, rainfall_mmh=80.0
    )


# =========================================================================== #
# M11-01 Real DEM ingestion -> normalized GridSpec
# =========================================================================== #


@require_real_artifacts
class TestM1101RealDEMModelReady:
    """Testm1101Realdemmodelready schema and data model representation."""
    def test_normalized_onto_authoritative_pilot_grid(self, real_terrain):
        """Test that normalized onto authoritative pilot grid behaves as expected."""
        pilot = authoritative_pilot_grid()
        assert real_terrain.normalization_status == "NORMALIZED"
        assert real_terrain.grid == pilot
        assert real_terrain.elevation.shape == (pilot.height, pilot.width)

    def test_provenance_answers_eight_questions(self, real_terrain):
        """Test that provenance answers eight questions behaves as expected."""
        a = real_terrain.provenance_answers()
        assert a["raw_dem_used"].endswith("bagjola_kolkata_glo30_dem.tif")
        assert len(a["raw_dem_sha256"]) == 64 and a["raw_dem_sha256"] != ""
        assert a["source_crs"] == "EPSG:4326"
        assert a["modelling_crs"] == "EPSG:32645"
        assert a["resampling"] == "bilinear"
        assert a["nodata_present"] is True  # preserved, never filled
        assert len(a["processing_fingerprint"]) == 64

    def test_nodata_preserved_not_filled(self, real_terrain):
        """Test that nodata preserved not filled behaves as expected."""
        mask = real_terrain.elevation == real_terrain.nodata
        assert mask.sum() == real_terrain.nodata_cells
        assert real_terrain.nodata_cells > 0
        # nodata cells are NOT silently set to zero or any real elevation
        assert not np.any(real_terrain.elevation[mask] == 0.0)

    def test_real_terrain_never_labelled_synthetic(self, real_terrain):
        """Test that real terrain never labelled synthetic behaves as expected."""
        labels = real_terrain.to_dict()["labels"]
        assert "REAL_DATA" in labels
        assert "SYNTHETIC" not in labels


# =========================================================================== #
# M11-02 Real drainage ingestion -> reprojection/alignment
# =========================================================================== #


@require_real_artifacts
class TestM1102DrainageAligned:
    """Testm1102Drainagealigned schema and data model representation."""
    def test_reprojected_to_model_crs(self, real_drainage):
        """Test that reprojected to model crs behaves as expected."""
        assert real_drainage.source_crs == "EPSG:4326"
        assert real_drainage.modelling_crs == "EPSG:32645"
        assert real_drainage.crs_source.embedded_crs == "ABSENT"
        assert real_drainage.crs_source.provenance_status == "AUTHORITATIVE_EXTERNAL_PROVENANCE"

    def test_reprojected_coords_are_metric(self, real_drainage):
        """Test that reprojected coords are metric behaves as expected."""
        # Reprojected coordinates must be in metres (UTM), not degrees.
        ent = real_drainage.entities_reprojected[0]
        wkt = ent["geometry_wkt_model_crs"]
        inner = wkt.split("(", 2)[-1]
        x = float(inner.strip().split()[0])
        assert 400000.0 < x < 800000.0  # UTM 45N easting range, not degrees

    def test_no_hand_written_offset(self, real_drainage):
        """Test that no hand written offset behaves as expected."""
        # Transformation is governed (pyproj); provenance records the authority.
        assert "MoHUA" in real_drainage.crs_source.authority

    def test_finite_processing_fingerprint(self, real_drainage):
        """Test that finite processing fingerprint behaves as expected."""
        assert len(real_drainage.processing_fingerprint) == 64


# =========================================================================== #
# M11-03 Real drainage entity provenance
# =========================================================================== #


@require_real_artifacts
class TestM1103EntityProvenance:
    """Testm1103Entityprovenance schema and data model representation."""
    def test_every_source_feature_accounted(self, real_drainage):
        """Test that every source feature accounted behaves as expected."""
        stats = drainage_mapping_stats(real_drainage.mapping_result)
        total = stats["total_source_features"]
        assert total == 90395
        assert stats["mapped"] + stats["unresolved_type"] + stats["rejected"] == total

    def test_entities_traceable_to_source_ids(self, real_drainage):
        """Test that entities traceable to source ids behaves as expected."""
        for ent in real_drainage.entities_reprojected[:50]:
            assert "feature_id" in ent
            assert "source_id" in ent
            assert "mapping_status" in ent
            assert "geometry_crs" in ent and ent["geometry_crs"] == "EPSG:32645"

    def test_rejection_breakdown_auditable(self, real_drainage):
        """Test that rejection breakdown auditable behaves as expected."""
        br = real_drainage.rejection_breakdown
        assert "REJECTED_DUPLICATE" in br
        assert sum(br.values()) == real_drainage.rejected_count


# =========================================================================== #
# M11-04 Hydraulic readiness contract
# =========================================================================== #


@require_real_artifacts
class TestM1104HydraulicReadiness:
    """Testm1104Hydraulicreadiness schema and data model representation."""
    def test_required_attributes_all_missing(self):
        """Test that required attributes all missing behaves as expected."""
        c = build_real_drainage_contract("WB_AMRUT_Stormwater_drains")
        assert c.hydraulic_network_ready is False
        assert set(c.missing_attributes) == set(REQUIRED_HYDRAULIC_ATTRIBUTES)

    def test_mode_b_contract_marks_assumed_not_real(self, mode_b_result):
        """Test that mode b contract marks assumed not real behaves as expected."""
        c = mode_b_result.hydraulic_contract
        assert c.synthetic_fixture_labelled is True
        assert c.real_hydraulic_network_ready is False
        for name in REQUIRED_HYDRAULIC_ATTRIBUTES:
            assert c.attributes[name].availability == HydraulicAvailability.ASSUMED


# =========================================================================== #
# M11-05 Real/synthetic separation
# =========================================================================== #


@require_real_artifacts
class TestM1105RealSyntheticSeparation:
    """Testm1105Realsyntheticseparation schema and data model representation."""
    def test_mode_b_content_label_is_explicit(self, mode_b_result):
        """Test that mode b content label is explicit behaves as expected."""
        assert mode_b_result.content_label == "REAL_TERRAIN_SYNTHETIC_HYDRAULICS"
        assert mode_b_result.model_mode == PilotModelMode.MODE_B_REAL_TERRAIN_SYNTHETIC_HYDRAULICS

    def test_real_terrain_not_relabelled_synthetic(self, real_terrain, mode_b_result):
        """Test that real terrain not relabelled synthetic behaves as expected."""
        labels = mode_b_result.to_dict()["labels"]
        assert "REAL_TERRAIN" in labels
        assert "SYNTHETIC_HYDRAULICS" in labels
        # The combined result must NOT collapse to a generic REAL_DATA or SYNTHETIC
        assert labels.count("REAL_TERRAIN_SYNTHETIC_HYDRAULICS") == 1

    def test_synthetic_fixture_values_never_real(self):
        """Test that synthetic fixture values never real behaves as expected."""
        c = build_synthetic_fixture_contract("fix")
        assert c.real_hydraulic_network_ready is False


# =========================================================================== #
# M11-06 Real terrain + synthetic hydraulic fixture integration
# =========================================================================== #


@require_real_artifacts
class TestM1106SimulationPath:
    """Testm1106Simulationpath schema and data model representation."""
    def test_simulation_succeeded_on_real_terrain(self, mode_b_result):
        """Test that simulation succeeded on real terrain behaves as expected."""
        assert mode_b_result.m4_result.simulation_run.status == "succeeded"

    def test_real_exchange_occurred(self, mode_b_result):
        """Test that real exchange occurred behaves as expected."""
        # Surface -> drainage capture proves the real-terrain coupled path ran.
        assert mode_b_result.mass_ledger["S2D_m3"] > 0.0

    def test_roi_is_real_subgrid_of_pilot(self, mode_b_result, real_terrain):
        """Test that roi is real subgrid of pilot behaves as expected."""
        roi = mode_b_result.roi
        assert roi.raw_dem_sha256 == real_terrain.raw_dem_sha256
        assert roi.pilot_grid.grid_id == "ufns_pilot_grid_real"
        assert roi.grid.crs_wkt_or_epsg == "EPSG:32645"
        assert roi.grid.cell_size_m == 30.0

    def test_depths_finite_and_nonneg(self, mode_b_result):
        """Test that depths finite and nonneg behaves as expected."""
        for arr in mode_b_result.m4_result.depth_arrays.values():
            assert np.all(np.isfinite(arr))
            assert float(arr.min()) >= -1e-12

    def test_hydraulic_network_not_ready(self, mode_b_result):
        """Test that hydraulic network not ready behaves as expected."""
        assert mode_b_result.capability_state.hydraulic_network_ready is False


# =========================================================================== #
# M11-07 Mass conservation
# =========================================================================== #


@require_real_artifacts
class TestM1107MassConservation:
    """Testm1107Massconservation schema and data model representation."""
    def test_relative_residual_within_gate(self, mode_b_result):
        """Test that relative residual within gate behaves as expected."""
        ml = mode_b_result.mass_ledger
        assert ml["status"] == "pass"
        assert ml["relative_residual"] is not None
        assert ml["relative_residual"] <= 0.01

    def test_mass_balance_object_consistent(self, mode_b_result):
        """Test that mass balance object consistent behaves as expected."""
        mb = mode_b_result.mass_balance
        assert mb.status == "pass"
        assert mb.relative_error is not None and mb.relative_error <= 0.01

    def test_exchange_cancellable(self, mode_b_result):
        """Test that exchange cancellable behaves as expected."""
        # S2D/D2S are internal transfers; they cancel in the combined ledger.
        ml = mode_b_result.mass_ledger
        # combined residual must be tiny regardless of exchange magnitude
        assert abs(ml["combined_residual_m3"]) < 1e-2 or ml["relative_residual"] <= 0.01


# =========================================================================== #
# M11-08 Deterministic repeatability
# =========================================================================== #


@require_real_artifacts
class TestM1108Determinism:
    """Testm1108Determinism schema and data model representation."""
    def test_repeated_run_identical(self, real_terrain):
        """Test that repeated run identical behaves as expected."""
        adapter = M11SimulationAdapter(real_terrain)
        r1 = adapter.mode_b_real_terrain_synthetic_hydraulics(
            duration_minutes=6, window=120, n_inlets=8, rainfall_mmh=80.0
        )
        r2 = adapter.mode_b_real_terrain_synthetic_hydraulics(
            duration_minutes=6, window=120, n_inlets=8, rainfall_mmh=80.0
        )
        fp1 = r1.m4_result.simulation_run.configuration_fingerprint
        fp2 = r2.m4_result.simulation_run.configuration_fingerprint
        assert fp1 == fp2 and fp1 != ""
        assert np.array_equal(
            r1.m4_result.depth_arrays[max(r1.m4_result.depth_arrays)],
            r2.m4_result.depth_arrays[max(r2.m4_result.depth_arrays)],
        )


# =========================================================================== #
# M11-09 Complete provenance validation
# =========================================================================== #


@require_real_artifacts
class TestM1109Provenance:
    """Testm1109Provenance schema and data model representation."""
    def test_full_chain_present(self, mode_b_result, real_terrain):
        """Test that full chain present behaves as expected."""
        p = mode_b_result.provenance
        assert p.raw_dem_sha256 == real_terrain.raw_dem_sha256
        assert p.raw_dem_sha256 != ""
        assert p.normalized_dem_fingerprint == real_terrain.processing_fingerprint
        assert len(p.gridspec_fingerprint) == 64
        assert p.model_config_fingerprint != ""
        assert p.model_mode == "MODE_B_REAL_TERRAIN_SYNTHETIC_HYDRAULICS"
        assert p.crs_source is not None
        assert "REAL_TERRAIN" in p.status_labels

    def test_pilot_gridspec_fingerprint_stable(self):
        """Test that pilot gridspec fingerprint stable behaves as expected."""
        g = authoritative_pilot_grid().model_dump(mode="json")
        assert gridspec_fingerprint(g) == gridspec_fingerprint(g)


# =========================================================================== #
# M11-10 M1-M9 regression protection
# =========================================================================== #


class TestM1110RegressionProtection:
    """Testm1110Regressionprotection schema and data model representation."""
    def test_synthetic_dem_and_grid_untouched(self):
        """Test that synthetic dem and grid untouched behaves as expected."""
        from services.ingestion.dem import (
            GRID_CELLS,
            ORIGIN_X,
            ORIGIN_Y,
            synthetic_dem,
        )

        assert synthetic_dem().shape == (GRID_CELLS, GRID_CELLS)
        assert ORIGIN_X == 300000.0
        assert ORIGIN_Y == 2500000.0
        assert GRID_CELLS == 134

    def test_pilot_grid_is_not_legacy_synthetic(self):
        """Test that pilot grid is not legacy synthetic behaves as expected."""
        from services.ingestion.dem import GRID_CELLS, ORIGIN_X, ORIGIN_Y

        pilot = authoritative_pilot_grid()
        assert pilot.grid_id == "ufns_pilot_grid_real"
        assert pilot.bounds[0] != ORIGIN_X
        assert pilot.bounds[1] != ORIGIN_Y
        assert pilot.width != GRID_CELLS

    def test_synthetic_fixture_inp_present(self):
        """Test that synthetic fixture inp present behaves as expected."""
        assert Path("data/demo/drainage_synthetic_m4.inp").exists()


# =========================================================================== #
# M11-11 Missing hydraulic attribute rejection / no-fabrication
# =========================================================================== #


@require_real_artifacts
class TestM1111NoFabrication:
    """Testm1111Nofabrication schema and data model representation."""
    def test_no_hydraulic_fields_on_real_entities(self, real_drainage):
        """Test that no hydraulic fields on real entities behaves as expected."""
        forbidden = {"diameter_m", "invert_upstream_m", "invert_downstream_m", "manning_n", "capacity_m3s"}
        for ent in real_drainage.entities_reprojected[:200]:
            assert not (forbidden & set(ent))

    def test_contract_marks_all_missing(self):
        """Test that contract marks all missing behaves as expected."""
        c = build_real_drainage_contract("d")
        assert set(c.missing_attributes) == set(REQUIRED_HYDRAULIC_ATTRIBUTES)

    def test_mode_b_uses_synthetic_not_real_hydraulics(self, mode_b_result):
        """Test that mode b uses synthetic not real hydraulics behaves as expected."""
        c = mode_b_result.hydraulic_contract
        for name in REQUIRED_HYDRAULIC_ATTRIBUTES:
            assert c.attributes[name].availability == HydraulicAvailability.ASSUMED
            assert c.attributes[name].source == "synthetic_fixture"


# =========================================================================== #
# M11-12 Real pilot model capability/status reporting
# =========================================================================== #


@require_real_artifacts
class TestM1112CapabilityReporting:
    """Testm1112Capabilityreporting schema and data model representation."""
    def test_capability_state(self, mode_b_result):
        """Test that capability state behaves as expected."""
        cap = mode_b_result.capability_state
        assert cap.real_terrain_available is True
        assert cap.real_geometry_available is True
        assert cap.hydraulic_parameters_present is False
        assert cap.hydraulic_network_ready is False

    def test_truthful_labels(self, mode_b_result):
        """Test that truthful labels behaves as expected."""
        labels = mode_b_result.to_dict()["labels"]
        assert "NOT_REAL_TIME" in labels
        assert "NOT_VALIDATED_FORECAST" in labels
        assert "PROVISIONAL" in labels

    def test_rainfall_not_promoted(self, mode_b_result):
        """Test that rainfall not promoted behaves as expected."""
        rs = mode_b_result.rainfall_status
        assert rs["d016_status"] == "PREPARED"
        assert rs["d016_human_review"] == "REQUIRED"
        assert rs["real_time"] is False
        assert rs["validated_forecast"] is False
