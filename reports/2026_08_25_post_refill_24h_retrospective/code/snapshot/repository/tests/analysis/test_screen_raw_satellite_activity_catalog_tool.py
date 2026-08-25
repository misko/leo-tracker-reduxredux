from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

from leo.analysis.research.multi_satellite_activity import (  # type: ignore[import-untyped]
    decode_joint_fixed_hypotheses,
)
from leo.analysis.research.satellite_activity import (  # type: ignore[import-untyped]
    ActivityGrid,
    AssociationCostModel,
    CfoCandidate,
    CfoProbe,
    PredictedProbeCfo,
    SatelliteActivityProblem,
    SingleSatelliteHypothesis,
)
from leo.analysis.research.satellite_activity_scores import (  # type: ignore[import-untyped]
    BinaryPilotScoreCalibration,
)
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]
from leo.sky.propagation import ElementSetCatalogue  # type: ignore[import-untyped]


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools/screen_raw_satellite_activity_catalog.py"
    spec = importlib.util.spec_from_file_location(
        "screen_raw_satellite_activity_catalog_tool",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _problem(
    *,
    satellite_cost: float = 1.0,
    episode_cost: float = 1.0,
    clutter_cost: float = 8.0,
    matched_cost: float = 0.1,
) -> SatelliteActivityProblem:
    probes = tuple(
        CfoProbe(
            probe_id=f"p{index}",
            time_s=index * 0.1,
            cell_index=index,
            missed_detection_cost=3.0,
        )
        for index in range(5)
    )
    observations = tuple(
        CfoCandidate(
            observation_id=f"o{index}",
            probe_id=f"p{index}",
            exclusion_group_id=f"g{index}",
            cfo_hz=100.0 + 10.0 * index,
            sigma_hz=10.0,
            clutter_cost=clutter_cost,
            matched_base_cost=matched_cost,
            component_id="raw-gauge",
        )
        for index in range(5)
    )
    return SatelliteActivityProblem(
        grid=ActivityGrid(
            start_s=0.0,
            cell_duration_s=0.1,
            cell_count=5,
            minimum_active_cells=5,
        ),
        probes=probes,
        observations=observations,
        costs=AssociationCostModel(
            satellite_cost=satellite_cost,
            episode_cost=episode_cost,
        ),
    )


def _calibration() -> BinaryPilotScoreCalibration:
    return BinaryPilotScoreCalibration(
        score_threshold=0.1,
        null_positive_count=1,
        null_total_count=1_000,
        signal_positive_count=999,
        signal_total_count=1_000,
        detection_probability=0.9,
    )


def _pilot_configuration() -> dict[str, Any]:
    return {
        "schema_version": 3,
        "algorithm_version": "standard-pilot-scan-v3",
        "maximum_scored_candidates_per_probe": 10,
        "methods": ["anchor8", "glrt64", "symbolwise"],
        "probe_samples": 50,
        "coarse_window_samples": 1_000,
        "subwindow_samples": 100,
        "frequency_coordinate": "baseband_cfo_hz",
        "frequency_reference": "uncalibrated_prior",
    }


def _raw(tool: ModuleType) -> tuple[Any, ...]:
    return tuple(
        tool.raw_replay._RawObservation(
            observation_id=f"o{index}",
            exclusion_group_id=f"g{index}",
            probe_id=f"p{index}",
            probe_index=index,
            cfo_hz=100.0 + 10.0 * index,
            margin=1.0,
            rank=0,
            group_minimum_rank=0,
            group_maximum_margin=1.0,
            group_member_count=1,
            local_epoch_offset_s=0.0,
        )
        for index in range(5)
    )


def _bank(tool: ModuleType, rows: tuple[tuple[int, np.ndarray[Any, Any]], ...]) -> Any:
    catalogue = cast(
        ElementSetCatalogue,
        SimpleNamespace(
            satellite_numbers=tuple(item[0] for item in rows),
            names=tuple(f"STARLINK-{item[0]}" for item in rows),
        ),
    )
    accounting = tool.CatalogueGeometryAccounting(
        catalogue_object_count=len(rows),
        unique_catalog_number_count=len(rows),
        nonmatching_name_count=0,
        name_selected_count=len(rows),
        coarse_propagation_failure_count=0,
        implausible_altitude_count=0,
        safely_below_horizon_count=0,
        fine_propagation_failure_count=0,
        fine_implausible_altitude_count=0,
        not_full_window_visible_count=0,
        eligible_catalog_count=len(rows),
    )
    return tool.CataloguePredictionBank(
        catalogue=catalogue,
        exact_utc_ns=(0, 100_000_000, 200_000_000, 300_000_000, 400_000_000),
        scheduled_times_s=(0.0, 0.1, 0.2, 0.3, 0.4),
        first_sample_utc_ns=0,
        delay_grid=(0.0,),
        columns_by_delay=((0, 1, 2, 3, 4),),
        doppler_hz=np.stack([item[1] for item in rows]),
        elevation_deg=np.full((len(rows), 5), 60.0),
        catalogue_indices=tuple(range(len(rows))),
        accounting=accounting,
    )


def test_optimistic_null_certificate_bounds_every_catalogue_curve() -> None:
    tool = _tool()
    strong = tool.optimistic_null_certificate(_problem())
    assert strong.certified is False
    assert strong.optimistic_delta_from_null < 0.0
    assert strong.active_cell_count == 5

    weak = tool.optimistic_null_certificate(
        _problem(
            satellite_cost=100.0,
            episode_cost=100.0,
            clutter_cost=0.1,
            matched_cost=3.0,
        )
    )
    assert weak.certified is True
    assert weak.optimistic_delta_from_null == 0.0
    assert weak.active_cell_count == 0


def test_certified_null_remains_null_for_multiple_competing_satellites() -> None:
    tool = _tool()
    weak = _problem(
        satellite_cost=100.0,
        episode_cost=100.0,
        clutter_cost=0.1,
        matched_cost=3.0,
    )
    assert tool.optimistic_null_certificate(weak).certified
    hypotheses = tuple(
        SingleSatelliteHypothesis(
            hypothesis_id=f"h{catalog_number}",
            object_name=f"SAT-{catalog_number}",
            catalog_number=catalog_number,
            delay_s=0.0,
            cfo_offset_hz=0.0,
            delay_prior_cost=0.0,
            predictions=tuple(
                PredictedProbeCfo(probe_id=probe.probe_id, cfo_hz=10_000.0 * catalog_number)
                for probe in weak.probes
            ),
        )
        for catalog_number in (10, 20, 30)
    )
    joint = decode_joint_fixed_hypotheses(weak, hypotheses)
    assert joint.selected_catalog_numbers == ()
    assert joint.objective.delta_from_null == 0.0

    with pytest.raises(ValueError, match="complete retained"):
        tool.optimistic_null_certificate(replace(weak, truncated_observation_count=1))


def test_catalogue_ranking_uses_zero_satellite_cost_and_is_deterministic() -> None:
    tool = _tool()
    rows = (
        (30, np.asarray([0.0, 80.0, 160.0, 240.0, 320.0])),
        (10, np.asarray([0.0, 10.0, 20.0, 30.0, 40.0])),
        (20, np.asarray([0.0, -50.0, -100.0, -150.0, -200.0])),
    )
    bank = _bank(tool, rows)
    problem = tool._ranking_problem(_problem(satellite_cost=99.0))
    config = tool.raw_replay.RawReplayConfig(
        delay_min_s=0.0,
        delay_max_s=0.0,
        satellite_cost=0.0,
        modes_per_delay=1,
    )
    scored = tool._score_catalog_rows(
        bank=bank,
        row_indices=(2, 0, 1),
        delay_grid=(0.0,),
        problem=problem,
        raw_observations=_raw(tool),
        calibration=_calibration(),
        config=config,
    )
    assert scored[0].catalog_number == 10
    assert scored[0].best_state.single_delta_from_null < 0.0
    assert [item.catalog_number for item in scored[1:]] == sorted(
        item.catalog_number for item in scored[1:]
    )
    summary = tool._score_summary(scored[0], 1)
    assert summary["activation_satellite_cost_threshold"] == pytest.approx(
        -scored[0].best_state.single_delta_from_null
    )


def test_refinement_is_distinct_catalogue_bounded_and_guarded() -> None:
    tool = _tool()
    bank = _bank(
        tool,
        tuple((number, np.asarray([0.0, 10.0, 20.0, 30.0, 40.0])) for number in (10, 20, 30, 40)),
    )
    problem = tool._ranking_problem(_problem())
    raw = _raw(tool)
    calibration = _calibration()
    config = tool.raw_replay.RawReplayConfig(
        delay_min_s=0.0,
        delay_max_s=0.0,
        satellite_cost=0.0,
        modes_per_delay=1,
    )
    scores = tool._score_catalog_rows(
        bank=bank,
        row_indices=(0, 1, 2, 3),
        delay_grid=(0.0,),
        problem=problem,
        raw_observations=raw,
        calibration=calibration,
        config=config,
    )
    screen = tool.CatalogueScreenConfig(
        refinement_catalog_count=2,
        refinement_guard_cost=0.0,
        maximum_refinement_catalog_count=3,
        final_catalog_count=2,
    )
    assert len(tool._refinement_rows(scores, screen)) == 2
    with pytest.raises(ValueError, match="catalogue-screen v1"):
        tool._refinement_rows(scores[:1], screen)
    with pytest.raises(ValueError, match="hard cap"):
        tool._refinement_rows(
            scores,
            tool.CatalogueScreenConfig(
                refinement_catalog_count=2,
                refinement_guard_cost=1_000.0,
                maximum_refinement_catalog_count=3,
                final_catalog_count=2,
            ),
        )


def test_geometry_accounting_rejects_unpartitioned_catalogue() -> None:
    tool = _tool()
    with pytest.raises(ValueError, match="partition"):
        tool.CatalogueGeometryAccounting(
            catalogue_object_count=2,
            unique_catalog_number_count=2,
            nonmatching_name_count=0,
            name_selected_count=2,
            coarse_propagation_failure_count=0,
            implausible_altitude_count=0,
            safely_below_horizon_count=0,
            fine_propagation_failure_count=0,
            fine_implausible_altitude_count=0,
            not_full_window_visible_count=0,
            eligible_catalog_count=1,
        )


def test_geometry_screen_accounts_every_catalogue_row(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _tool()
    catalogue = ElementSetCatalogue(
        names=("OTHER", "STARLINK-A", "STARLINK-B", "STARLINK-C", "STARLINK-D"),
        satellite_numbers=(1, 2, 3, 4, 5),
        satellites=cast(tuple[Any, ...], (object(),) * 5),
    )
    calls = 0

    def fake_propagate(
        _catalogue: Any,
        grid: Any,
        indices: tuple[int, ...],
    ) -> Any:
        return SimpleNamespace(grid=grid, indices=tuple(indices))

    def fake_observe(propagated: Any, _observer: Any, grid: Any) -> Any:
        nonlocal calls
        calls += 1
        sample_count = len(grid.utc_ns)
        if calls == 1:
            assert propagated.indices == (1, 2, 3, 4)
            return SimpleNamespace(
                usable=np.asarray([False, True, True, True]),
                altitude_km=np.asarray(
                    [
                        [500.0] * sample_count,
                        [50.0] * sample_count,
                        [500.0] * sample_count,
                        [500.0] * sample_count,
                    ]
                ),
                elevation_deg=np.asarray(
                    [
                        [20.0] * sample_count,
                        [20.0] * sample_count,
                        [-20.0] * sample_count,
                        [20.0] * sample_count,
                    ]
                ),
                range_rate_km_s=np.zeros((4, sample_count)),
            )
        assert propagated.indices == (4,)
        return SimpleNamespace(
            usable=np.asarray([True]),
            altitude_km=np.asarray([[500.0] * sample_count]),
            elevation_deg=np.asarray([[20.0] * sample_count]),
            range_rate_km_s=np.zeros((1, sample_count)),
        )

    monkeypatch.setattr(tool, "propagate_grid", fake_propagate)
    monkeypatch.setattr(tool, "observe_grid", fake_observe)
    bank = tool.build_catalogue_prediction_bank(
        catalogue=catalogue,
        scheduled_times_s=(0.0, 0.1, 0.2, 0.3, 0.4),
        first_sample_utc_ns=1_000_000_000,
        delay_grid=(0.0,),
        sky_frequency_hz=10e9,
        observer=ObserverSiteV1(
            latitude_deg=0.0,
            longitude_deg=0.0,
            altitude_m=0.0,
            label="test-site",
        ),
        horizon_mask_deg=0.0,
        name_prefix="STARLINK",
        geometry_spacing_s=0.5,
    )
    assert bank.catalog_numbers == (5,)
    assert bank.accounting.nonmatching_name_count == 1
    assert bank.accounting.coarse_propagation_failure_count == 1
    assert bank.accounting.implausible_altitude_count == 1
    assert bank.accounting.safely_below_horizon_count == 1
    assert bank.accounting.eligible_catalog_count == 1


def test_duplicate_norad_and_partial_visibility_fail_closed_or_are_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    duplicate = ElementSetCatalogue(
        names=("STARLINK-A", "STARLINK-B"),
        satellite_numbers=(10, 10),
        satellites=cast(tuple[Any, ...], (object(), object())),
    )
    with pytest.raises(ValueError, match="duplicate NORAD"):
        tool.build_catalogue_prediction_bank(
            catalogue=duplicate,
            scheduled_times_s=(0.0, 0.1, 0.2),
            first_sample_utc_ns=0,
            delay_grid=(0.0,),
            sky_frequency_hz=10e9,
            observer=ObserverSiteV1(
                latitude_deg=0.0,
                longitude_deg=0.0,
                altitude_m=0.0,
                label="test-site",
            ),
            horizon_mask_deg=0.0,
            name_prefix="STARLINK",
            geometry_spacing_s=0.5,
        )

    catalogue = ElementSetCatalogue(
        names=("STARLINK-A", "STARLINK-B"),
        satellite_numbers=(10, 20),
        satellites=cast(tuple[Any, ...], (object(), object())),
    )
    calls = 0

    def fake_propagate(_catalogue: Any, grid: Any, indices: tuple[int, ...]) -> Any:
        return SimpleNamespace(grid=grid, indices=indices)

    def fake_observe(_propagated: Any, _observer: Any, grid: Any) -> Any:
        nonlocal calls
        calls += 1
        count = len(grid.utc_ns)
        if calls == 1:
            rows = 2
            elevation = np.full((rows, count), 20.0)
        else:
            rows = 2
            elevation = np.full((rows, count), 20.0)
            elevation[0, -1] = -0.1
        return SimpleNamespace(
            usable=np.ones(rows, dtype=np.bool_),
            altitude_km=np.full((rows, count), 500.0),
            elevation_deg=elevation,
            range_rate_km_s=np.zeros((rows, count)),
        )

    monkeypatch.setattr(tool, "propagate_grid", fake_propagate)
    monkeypatch.setattr(tool, "observe_grid", fake_observe)
    bank = tool.build_catalogue_prediction_bank(
        catalogue=catalogue,
        scheduled_times_s=(0.0, 0.1, 0.2),
        first_sample_utc_ns=0,
        delay_grid=(0.0,),
        sky_frequency_hz=10e9,
        observer=ObserverSiteV1(
            latitude_deg=0.0,
            longitude_deg=0.0,
            altitude_m=0.0,
            label="test-site",
        ),
        horizon_mask_deg=0.0,
        name_prefix="STARLINK",
        geometry_spacing_s=0.5,
    )
    assert bank.catalog_numbers == (20,)
    assert bank.accounting.not_full_window_visible_count == 1


@pytest.mark.parametrize(
    ("lower", "upper", "step", "expected"),
    [(-2.0, 2.0, 0.5, 9), (0.0, 0.0, 0.5, 1)],
)
def test_strict_delay_grid(lower: float, upper: float, step: float, expected: int) -> None:
    tool = _tool()
    assert len(tool._strict_delay_grid(lower, upper, step)) == expected
    with pytest.raises(ValueError, match="divide"):
        tool._strict_delay_grid(-2.0, 2.0, 0.3)


def test_null_document_has_stable_decision_and_search_config_digest(tmp_path: Path) -> None:
    tool = _tool()
    dataset_path = tmp_path / "input.json"
    calibration_path = tmp_path / "calibration.json"
    tle_path = tmp_path / "catalog.tle"
    scan_path = tmp_path / "scan.json"
    for path in (dataset_path, calibration_path, tle_path, scan_path):
        path.write_text("{}", encoding="utf-8")
    inventory = SimpleNamespace(
        problem=_problem(),
        elided_clutter_constant=2.0,
        source_candidate_count=50,
        returned_candidate_count=50,
        saturated_probe_count=5,
        exclusion_group_count=5,
        modeled_exclusion_group_count=5,
        positive_exclusion_group_count=5,
        scan_path=scan_path,
        scan_digest="sha256:" + "1" * 64,
    )
    certificate = tool.NullCertificate(
        certified=True,
        modeled_null_cost=40.0,
        optimistic_delta_from_null=0.0,
        optimistic_selected=False,
        active_cell_count=0,
        episode_count=0,
        assignment_count=0,
    )
    catalogue = ElementSetCatalogue(
        names=("STARLINK-A", "STARLINK-B"),
        satellite_numbers=(10, 20),
        satellites=cast(tuple[Any, ...], (object(), object())),
    )
    document = tool._null_certificate_document(
        dataset_path=dataset_path,
        calibration_path=calibration_path,
        tle_path=tle_path,
        tle_digest=tool._file_digest(tle_path),
        inventory=inventory,
        window=SimpleNamespace(rows=({},) * 5, cell_count=5),
        start_s=0.0,
        end_s=0.5,
        certificate=certificate,
        observer=ObserverSiteV1(
            latitude_deg=0.0,
            longitude_deg=0.0,
            altitude_m=0.0,
            label="test-site",
        ),
        config=tool.raw_replay.RawReplayConfig(delay_min_s=0.0, delay_max_s=0.0),
        screen_config=tool.CatalogueScreenConfig(final_catalog_count=2),
        catalogue=catalogue,
        calibration_schema=tool.raw_replay.CALIBRATION_SCHEMA_V3,
        sky_frequency_hz=10e9,
        pilot_scan_configuration=_pilot_configuration(),
        evaluation_scope_digest="sha256:" + "2" * 64,
    )
    assert document["decision"] == {
        "result_kind": "certified_null",
        "selected_catalog_numbers": [],
        "selected_satellite_count": 0,
        "full_persisted_inventory_objective": {
            "null_cost": 42.0,
            "total_cost": 42.0,
            "delta_from_null": 0.0,
            "constant_elided_from_exact_decision_problem": 2.0,
        },
    }
    assert document["raw_inventory"]["probe_count_at_retained_candidate_cap"] == 5
    assert document["search_configuration_digest"] == tool.canonical_digest(
        document["search_configuration"]
    )
    assert document["search_configuration"]["member_evaluation_scope_digest"] == (
        "sha256:" + "2" * 64
    )
    assert document["search_configuration"]["window"] == {
        "start_s": 0.0,
        "end_s": 0.5,
        "duration_s": 0.5,
        "scheduled_probe_count": 5,
        "cell_count": 5,
    }
    assert (
        document["search_configuration"]["producer_implementation"]["algorithm"]
        == (tool.producer_implementation_manifest()["algorithm"])
    )


def test_successful_orchestration_binds_union_grid_and_stable_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    dataset_path = tmp_path / "input.json"
    calibration_path = tmp_path / "calibration.json"
    tle_path = tmp_path / "catalog.tle"
    scan_path = tmp_path / "scan.json"
    for path in (dataset_path, calibration_path, tle_path):
        path.write_text("{}", encoding="utf-8")
    scan_path.write_text(json.dumps(_pilot_configuration()), encoding="utf-8")
    rows = (
        (10, np.asarray([0.0, 10.0, 20.0, 30.0, 40.0])),
        (20, np.asarray([0.0, 50.0, 100.0, 150.0, 200.0])),
        (30, np.asarray([0.0, -50.0, -100.0, -150.0, -200.0])),
    )
    base_bank = _bank(tool, rows)
    catalogue = ElementSetCatalogue(
        names=("STARLINK-10", "STARLINK-20", "STARLINK-30"),
        satellite_numbers=(10, 20, 30),
        satellites=cast(tuple[Any, ...], (object(), object(), object())),
    )
    problem = _problem()
    inventory = SimpleNamespace(
        problem=problem,
        observations=_raw(tool),
        scan_path=scan_path,
        scan_digest="sha256:" + "1" * 64,
    )
    window = SimpleNamespace(
        rows=tuple({"probe_id": f"probe-{index}"} for index in range(5)),
        cell_count=5,
    )
    monkeypatch.setattr(tool, "parse_element_sets", lambda _text: catalogue)
    monkeypatch.setattr(
        tool,
        "_prepare_raw_inventory",
        lambda **_kwargs: (_calibration(), window, inventory, (0.0, 0.1, 0.2, 0.3, 0.4)),
    )
    monkeypatch.setattr(
        tool,
        "optimistic_null_certificate",
        lambda _problem: tool.NullCertificate(
            certified=False,
            modeled_null_cost=40.0,
            optimistic_delta_from_null=-1.0,
            optimistic_selected=True,
            active_cell_count=5,
            episode_count=1,
            assignment_count=5,
        ),
    )
    observed_delay_grid: tuple[float, ...] = ()

    def fake_bank(**kwargs: Any) -> Any:
        nonlocal observed_delay_grid
        observed_delay_grid = tuple(kwargs["delay_grid"])
        return tool.CataloguePredictionBank(
            catalogue=catalogue,
            exact_utc_ns=base_bank.exact_utc_ns,
            scheduled_times_s=base_bank.scheduled_times_s,
            first_sample_utc_ns=base_bank.first_sample_utc_ns,
            delay_grid=observed_delay_grid,
            columns_by_delay=(base_bank.columns_by_delay[0],) * len(observed_delay_grid),
            doppler_hz=base_bank.doppler_hz,
            elevation_deg=base_bank.elevation_deg,
            catalogue_indices=base_bank.catalogue_indices,
            accounting=base_bank.accounting,
        )

    monkeypatch.setattr(tool, "build_catalogue_prediction_bank", fake_bank)
    supplied_catalogues: tuple[int, ...] = ()

    def fake_final(**kwargs: Any) -> dict[str, Any]:
        nonlocal supplied_catalogues
        supplied_catalogues = tuple(kwargs["catalog_numbers"])
        return {
            "association": {"association": {"selected_catalog_numbers": [10]}},
            "nuisance_state_search": {
                "retained_state_count": 12,
                "retained_state_space_exhausted": True,
            },
            "full_persisted_inventory_objective": {
                "null_cost": 40.0,
                "total_cost": 10.0,
                "delta_from_null": -30.0,
                "constant_elided_from_exact_decision_problem": 0.0,
            },
            "caveats": [],
        }

    monkeypatch.setattr(tool.raw_replay, "replay_raw_window", fake_final)
    config = tool.raw_replay.RawReplayConfig(
        delay_min_s=-1.0,
        delay_max_s=1.0,
        delay_step_s=0.2,
        modes_per_delay=1,
        retained_states_per_catalog=1,
    )
    screen_config = tool.CatalogueScreenConfig(
        coarse_delay_step_s=0.5,
        refinement_catalog_count=3,
        maximum_refinement_catalog_count=3,
        final_catalog_count=3,
    )
    document = tool.screen_raw_catalogue_window(
        dataset={
            "timing_binding": {"first_estimate_utc_ns": 0},
            "capture": {
                "session_id": "session-test",
                "recording_manifest_digest": "sha256:" + "3" * 64,
                "stream_id": "stream-0",
                "receiver_id": 0,
            },
            "frequency_binding": {
                "tuning_tag": "tuning:test",
                "sky_frequency_hz": 10e9,
            },
        },
        dataset_path=dataset_path,
        calibration_document={"schema": tool.raw_replay.CALIBRATION_SCHEMA_V3},
        calibration_path=calibration_path,
        tle_path=tle_path,
        expected_tle_digest=tool._file_digest(tle_path),
        start_s=0.0,
        end_s=0.5,
        observer=ObserverSiteV1(
            latitude_deg=0.0,
            longitude_deg=0.0,
            altitude_m=0.0,
            label="test-site",
        ),
        config=config,
        screen_config=screen_config,
    )
    assert -0.5 in observed_delay_grid and 0.5 in observed_delay_grid
    assert set(config.delay_grid).issubset(observed_delay_grid)
    assert len(supplied_catalogues) == 3
    assert document["decision"]["result_kind"] == "catalogue_screened_grouped_activity"
    assert document["decision"]["selected_catalog_numbers"] == [10]
    assert document["search_configuration_digest"] == tool.canonical_digest(
        document["search_configuration"]
    )
    assert document["search_configuration"]["member_evaluation_scope_digest"] == (
        tool._member_evaluation_scope_digest(
            dataset={
                "capture": {
                    "session_id": "session-test",
                    "recording_manifest_digest": "sha256:" + "3" * 64,
                    "stream_id": "stream-0",
                    "receiver_id": 0,
                },
                "frequency_binding": {
                    "tuning_tag": "tuning:test",
                    "sky_frequency_hz": 10e9,
                },
            },
            dataset_path=dataset_path,
            pilot_scan_digest="sha256:" + "1" * 64,
            window=window,
            start_s=0.0,
            end_s=0.5,
        )
    )
