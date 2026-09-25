from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

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
    decode_single_satellite,
)
from leo.analysis.research.satellite_activity_scores import (  # type: ignore[import-untyped]
    BinaryPilotScoreCalibration,
)
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]
from leo.sky.propagation import ElementSetCatalogue  # type: ignore[import-untyped]


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools/decide_raw_catalogue_null_vs_any.py"
    spec = importlib.util.spec_from_file_location(
        "decide_raw_catalogue_null_vs_any_tool",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _problem(*, weak: bool) -> SatelliteActivityProblem:
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
            clutter_cost=0.1 if weak else 8.0,
            matched_base_cost=3.0 if weak else 0.1,
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
            satellite_cost=100.0 if weak else 1.0,
            episode_cost=100.0 if weak else 1.0,
        ),
    )


def _hypothesis(
    problem: SatelliteActivityProblem,
    catalog_number: int,
) -> SingleSatelliteHypothesis:
    return SingleSatelliteHypothesis(
        hypothesis_id=f"h{catalog_number}",
        object_name=f"STARLINK-{catalog_number}",
        catalog_number=catalog_number,
        delay_s=0.0,
        cfo_offset_hz=0.0,
        delay_prior_cost=0.0,
        predictions=tuple(
            PredictedProbeCfo(
                probe_id=probe.probe_id,
                cfo_hz=100.0 + 10.0 * index,
            )
            for index, probe in enumerate(problem.probes)
        ),
    )


def _score(tool: ModuleType, problem: SatelliteActivityProblem, catalog_number: int) -> Any:
    hypothesis = _hypothesis(problem, catalog_number)
    decoded = decode_single_satellite(problem, hypothesis)
    return tool.screen.CatalogScore(
        catalog_number=catalog_number,
        object_name=hypothesis.object_name,
        catalogue_index=catalog_number,
        generated_state_count=1,
        best_state=tool.raw_replay._StateEvaluation(
            hypothesis=hypothesis,
            proposal=tool.raw_replay._OffsetMode(
                cfo_offset_hz=0.0,
                support_group_count=5,
                support_probe_count=5,
            ),
            single_total_cost=decoded.objective.total_cost,
            single_delta_from_null=decoded.objective.delta_from_null,
            single_selected=decoded.selected,
            minimum_elevation_deg=30.0,
            maximum_elevation_deg=60.0,
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


def _raw_observations(tool: ModuleType) -> tuple[Any, ...]:
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


def test_single_minima_certificate_covers_joint_subsets() -> None:
    tool = _tool()
    problem = _problem(weak=True)
    scores = tuple(_score(tool, problem, catalog_number) for catalog_number in (10, 20, 30))
    assert tool._activation_witness(scores, eligible_catalog_count=3) is None
    assert all(not item.best_state.single_selected for item in scores)

    joint = decode_joint_fixed_hypotheses(
        problem,
        tuple(item.best_state.hypothesis for item in scores),
    )
    assert joint.selected_catalog_numbers == ()
    assert joint.objective.delta_from_null == 0.0

    with pytest.raises(RuntimeError, match="every eligible catalogue"):
        tool._activation_witness(scores[:2], eligible_catalog_count=3)


def test_negative_single_minimum_is_activation_witness() -> None:
    tool = _tool()
    problem = _problem(weak=False)
    null_problem = _problem(weak=True)
    scores = (
        _score(tool, problem, 10),
        _score(tool, null_problem, 20),
    )
    witness = tool._activation_witness(scores, eligible_catalog_count=2)
    assert witness is scores[0]
    assert witness.best_state.single_selected
    assert witness.best_state.single_delta_from_null < 0.0


def _run_api(
    tool: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    weak: bool,
    output_schema_version: int = 1,
    eligible_catalog_numbers: tuple[int, ...] = (10, 20, 30),
) -> tuple[dict[str, Any], tuple[int, ...]]:
    dataset_path = tmp_path / "input.json"
    calibration_path = tmp_path / "calibration.json"
    tle_path = tmp_path / "catalog.tle"
    scan_path = tmp_path / "scan.json"
    dataset_path.write_text("{}", encoding="utf-8")
    calibration_path.write_text("{}", encoding="utf-8")
    tle_path.write_text("{}", encoding="utf-8")
    scan_path.write_text(json.dumps(_pilot_configuration()), encoding="utf-8")

    problem = _problem(weak=weak)
    catalogue = ElementSetCatalogue(
        names=("STARLINK-10", "STARLINK-20", "STARLINK-30"),
        satellite_numbers=(10, 20, 30),
        satellites=cast(tuple[Any, ...], (object(), object(), object())),
    )
    accounting = tool.screen.CatalogueGeometryAccounting(
        catalogue_object_count=3,
        unique_catalog_number_count=3,
        nonmatching_name_count=0,
        name_selected_count=3,
        coarse_propagation_failure_count=0,
        implausible_altitude_count=0,
        safely_below_horizon_count=0,
        fine_propagation_failure_count=0,
        fine_implausible_altitude_count=0,
        not_full_window_visible_count=3 - len(eligible_catalog_numbers),
        eligible_catalog_count=len(eligible_catalog_numbers),
    )
    index_by_catalog = {10: 0, 20: 1, 30: 2}
    bank = SimpleNamespace(
        catalogue_indices=tuple(index_by_catalog[item] for item in eligible_catalog_numbers),
        accounting=accounting,
        exact_utc_ns=(0, 100_000_000, 200_000_000, 300_000_000, 400_000_000),
    )
    inventory = SimpleNamespace(
        problem=problem,
        observations=_raw_observations(tool),
        source_candidate_count=5,
        returned_candidate_count=5,
        exclusion_group_count=5,
        positive_candidate_count=5,
        positive_exclusion_group_count=5,
        modeled_exclusion_group_count=5,
        unsupported_positive_candidate_count=0,
        unsupported_positive_exclusion_group_count=0,
        dominated_weak_candidate_count=0,
        dominated_weak_exclusion_group_count=0,
        elided_clutter_constant=2.0,
        saturated_probe_count=5,
        local_epoch_min_s=0.0,
        local_epoch_max_s=0.001,
        scan_path=scan_path,
        scan_digest="sha256:" + "1" * 64,
    )
    window = SimpleNamespace(
        rows=tuple({"probe_id": f"p{index}"} for index in range(5)),
        cell_count=5,
    )
    monkeypatch.setattr(tool.screen, "parse_element_sets", lambda _text: catalogue)
    monkeypatch.setattr(
        tool.screen,
        "_prepare_raw_inventory",
        lambda **_kwargs: (_calibration(), window, inventory, (0.0, 0.1, 0.2, 0.3, 0.4)),
    )
    monkeypatch.setattr(tool.screen, "build_catalogue_prediction_bank", lambda **_kwargs: bank)
    monkeypatch.setattr(
        tool.screen,
        "optimistic_null_certificate",
        lambda _problem: tool.screen.NullCertificate(
            certified=False,
            modeled_null_cost=tool._modeled_null_cost(problem),
            optimistic_delta_from_null=-1.0,
            optimistic_selected=True,
            active_cell_count=5,
            episode_count=1,
            assignment_count=5,
        ),
    )
    monkeypatch.setattr(
        tool,
        "producer_implementation_manifest",
        lambda: {
            "algorithm": tool.PRODUCER_MANIFEST_ALGORITHM,
            "wrapper": {"path": tool.WRAPPER_RELATIVE_PATH, "digest": "sha256:" + "9" * 64},
            "imported_catalogue_screen_producer": {"algorithm": "frozen-test-producer"},
        },
    )
    observed_rows: tuple[int, ...] = ()

    def fake_scores(**kwargs: Any) -> tuple[Any, ...]:
        nonlocal observed_rows
        observed_rows = tuple(kwargs["row_indices"])
        assert kwargs["problem"] is problem
        assert kwargs["config"].satellite_cost == problem.costs.satellite_cost
        assert tuple(kwargs["delay_grid"]) == (0.0,)
        return tuple(
            _score(tool, problem, catalog_number) for catalog_number in eligible_catalog_numbers
        )

    monkeypatch.setattr(tool.screen, "_score_catalog_rows", fake_scores)
    config = tool.raw_replay.RawReplayConfig(
        satellite_cost=problem.costs.satellite_cost,
        episode_cost=problem.costs.episode_cost,
        delay_min_s=0.0,
        delay_max_s=0.0,
        modes_per_delay=1,
    )
    dataset = {
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
        "alias_collapse": {"alias_spacing_hz": 227_272.72727272726},
    }
    document = tool.decide_raw_catalogue_null_vs_any(
        dataset=dataset,
        dataset_path=dataset_path,
        calibration_document={"schema": tool.raw_replay.CALIBRATION_SCHEMA_V3},
        calibration_path=calibration_path,
        tle_path=tle_path,
        expected_tle_digest=tool.screen._file_digest(tle_path),
        start_s=0.0,
        end_s=0.5,
        observer=ObserverSiteV1(
            latitude_deg=0.0,
            longitude_deg=0.0,
            altitude_m=0.0,
            label="test-site",
        ),
        config=config,
        output_schema_version=output_schema_version,
    )
    return document, observed_rows


def test_api_emits_bounded_exact_null_and_exhaustive_accounting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    document, observed_rows = _run_api(tool, tmp_path, monkeypatch, weak=True)
    assert observed_rows == (0, 1, 2)
    assert document["decision"]["result_kind"] == "bounded_exact_null"
    assert document["decision"]["selected_catalog_numbers"] == []
    assert document["finite_universe_catalogue_search_exact"] is True
    assert document["catalogue_search_exact"] is False
    assert document["unrestricted_global_exactness_claimed"] is False
    fine = document["catalogue_search"]["fine_stage"]
    assert fine["eligible_catalog_count"] == 3
    assert fine["scored_catalog_count"] == 3
    assert fine["omitted_eligible_catalog_count"] == 0
    assert fine["generated_state_count"] == 3
    assert fine["all_catalogue_minima_nonactivating"] is True
    minimum = fine["ranking"][0]
    assert minimum["configured_satellite_cost"] == 100.0
    assert minimum["best_single_delta_from_null"] == 0.0
    assert "best_single_delta_at_zero_satellite_cost" not in minimum
    proof = document["catalogue_search"]["separability_proof"]
    assert proof["arbitrary_subsets_of_finite_catalogue_universe_covered"] is True
    assert proof["proof_conclusion"] == "bounded_exact_null"
    assert document["search_configuration_digest"] == tool.canonical_digest(
        document["search_configuration"]
    )
    assert document["search_configuration"]["algorithm"] == tool.ALGORITHM


def test_api_emits_reproducible_activation_witness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    document, observed_rows = _run_api(tool, tmp_path, monkeypatch, weak=False)
    assert observed_rows == (0, 1, 2)
    assert document["decision"]["result_kind"] == "activation_witness"
    assert document["decision"]["selected_catalog_numbers"] == [10]
    witness = document["association"]["activation_witness"]
    assert witness["association_exact"] is True
    assert witness["catalogue_minimum"]["catalog_number"] == 10
    assert witness["catalogue_minimum"]["configured_satellite_cost"] == 1.0
    assert witness["catalogue_minimum"]["best_single_delta_from_null"] < 0.0
    assert "best_single_delta_at_zero_satellite_cost" not in witness["catalogue_minimum"]
    assert witness["full_persisted_inventory_objective"]["delta_from_null"] < 0.0
    assert len(witness["activity_by_cell"]) == 5
    assert len(witness["assignments"]) == 5
    assert document["unknown_satellite_count_solved"] is False
    assert document["global_optimum_claimed"] is False


def test_v2_identity_partition_is_complete_digest_bound_and_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    document, observed_rows = _run_api(
        tool,
        tmp_path,
        monkeypatch,
        weak=True,
        output_schema_version=2,
        eligible_catalog_numbers=(10, 30),
    )

    assert observed_rows == (0, 1)
    assert document["schema"] == tool.OUTPUT_SCHEMA_V2
    assert document["algorithm"] == tool.ALGORITHM_V2
    assert document["search_configuration"]["algorithm"] == tool.ALGORITHM_V2
    assert document["search_configuration"]["output_schema"] == tool.OUTPUT_SCHEMA_V2
    partition = document["catalogue_identity_partition"]
    assert partition["named_catalog_numbers"] == [10, 20, 30]
    assert partition["eligible_catalog_numbers"] == [10, 30]
    assert partition["named_ineligible_catalog_numbers"] == [20]
    assert partition["named_catalog_count"] == 3
    assert partition["eligible_catalog_count"] == 2
    assert partition["named_ineligible_catalog_count"] == 1
    payload = dict(partition)
    observed_digest = payload.pop("partition_content_digest")
    assert tool.canonical_digest(payload) == observed_digest
    assert (
        document["catalogue_search"]["finite_universe"]["identity_partition_content_digest"]
        == observed_digest
    )


def test_v1_output_does_not_silently_gain_an_identity_partition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    document, _observed_rows = _run_api(tool, tmp_path, monkeypatch, weak=True)
    assert document["schema"] == tool.OUTPUT_SCHEMA
    assert "catalogue_identity_partition" not in document


def test_producer_receipt_adds_wrapper_without_replacing_frozen_manifest() -> None:
    tool = _tool()
    manifest = tool.producer_implementation_manifest()
    wrapper = Path(__file__).parents[2] / manifest["wrapper"]["path"]
    assert manifest["wrapper"]["digest"] == (
        "sha256:" + hashlib.sha256(wrapper.read_bytes()).hexdigest()
    )
    imported = manifest["imported_catalogue_screen_producer"]
    paths = {item["path"] for item in imported["files"]}
    assert "tools/screen_raw_satellite_activity_catalog.py" in paths
