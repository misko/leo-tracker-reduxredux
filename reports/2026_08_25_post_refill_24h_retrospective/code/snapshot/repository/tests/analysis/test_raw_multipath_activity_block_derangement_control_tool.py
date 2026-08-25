from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from leo.analysis.research.multipath_satellite_activity import (  # type: ignore[import-untyped]
    FixedMultipathSatelliteHypothesis,
    MultipathSatelliteActivityProblem,
    ReceiverPathActivityEvidence,
    ReceiverPathFixedHypothesis,
    decode_fixed_multipath_satellite,
)
from leo.analysis.research.satellite_activity import (  # type: ignore[import-untyped]
    ActivityGrid,
    AssociationCostModel,
    CfoCandidate,
    CfoProbe,
    DelayProfileCandidate,
    PredictedProbeCfo,
    profile_delay_and_cfo_offset,
)
from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]

GRID_START_UTC_NS = 100_000_000_000
CELL_COUNT = 40


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools/control_raw_multipath_activity_block_derangement.py"
    spec = importlib.util.spec_from_file_location(
        "raw_multipath_activity_block_derangement_control_tool", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _curve(relative_time_s: float) -> float:
    return 1_500.0 * relative_time_s**2 + 250.0 * relative_time_s**3


def _path(path_id: str, path_offset_hz: float) -> ReceiverPathActivityEvidence:
    probes = tuple(
        CfoProbe(
            probe_id=f"{path_id}-probe-{cell}",
            time_s=100.0 + cell * 0.1 + 0.025,
            cell_index=cell,
            missed_detection_cost=3.0,
        )
        for cell in range(CELL_COUNT)
    )
    observations = tuple(
        CfoCandidate(
            observation_id=f"{path_id}-observation-{cell}",
            probe_id=probe.probe_id,
            exclusion_group_id=f"{path_id}-group-{cell}",
            cfo_hz=_curve(probe.time_s - 100.0) + path_offset_hz,
            sigma_hz=1.0,
            clutter_cost=8.0,
            matched_base_cost=0.0,
            component_id=f"component:{path_id}",
        )
        for cell, probe in enumerate(probes)
    )
    return ReceiverPathActivityEvidence(path_id, probes, observations)


def _problem() -> MultipathSatelliteActivityProblem:
    return MultipathSatelliteActivityProblem(
        grid=ActivityGrid(100.0, 0.1, CELL_COUNT, minimum_active_cells=5),
        paths=(_path("path-b", 75.0), _path("path-a", -40.0)),
        costs=AssociationCostModel(
            satellite_cost=8.0,
            episode_cost=2.0,
            huber_threshold=1.0,
        ),
    )


def _utc_by_probe(path: ReceiverPathActivityEvidence) -> dict[str, int]:
    return {
        probe.probe_id: GRID_START_UTC_NS + probe.cell_index * 100_000_000 + 25_000_000
        for probe in path.probes
    }


def _plan(tool: ModuleType, problem: MultipathSatelliteActivityProblem):
    return tool.build_session_derangement(
        problem=problem,
        selection_context={
            "session_id": "synthetic-session",
            "control_label": "frozen-before-inspection-0",
            "input_digests": ["sha256:" + "1" * 64, "sha256:" + "2" * 64],
        },
        maximum_delay_support_s=0.2,
        minimum_circular_displacement_blocks=1,
    )


def test_adapter_plan_is_deterministic_digest_bound_and_serializes_ranking_version() -> None:
    tool = _tool()
    problem = _problem()
    first, first_receipt = _plan(tool, problem)
    repeated, repeated_receipt = _plan(tool, problem)
    changed, changed_receipt = tool.build_session_derangement(
        problem=problem,
        selection_context={
            "session_id": "synthetic-session",
            "control_label": "independent-frozen-control-1",
            "input_digests": ["sha256:" + "1" * 64, "sha256:" + "2" * 64],
        },
        maximum_delay_support_s=0.2,
        minimum_circular_displacement_blocks=1,
    )

    assert first == repeated
    assert first_receipt == repeated_receipt
    assert first_receipt["ranking_version"] == first.ranking_version
    assert first_receipt["plan_digest"] == first.plan_digest
    assert first_receipt["realized_displacement_strictly_exceeds_delay_support"]
    assert changed_receipt["selection_context_digest"] != first_receipt["selection_context_digest"]
    assert changed.plan_digest != first.plan_digest


def test_adapter_uses_one_integer_utc_mapping_across_paths_and_preserves_cadence() -> None:
    tool = _tool()
    problem = _problem()
    plan, receipt = _plan(tool, problem)
    mapped_rows = []
    for path in problem.paths:
        _mapped, rows = tool._prediction_cell_mapping(
            plan,
            path,
            grid_start_utc_ns=GRID_START_UTC_NS,
            observation_utc_ns_by_probe_id=_utc_by_probe(path),
        )
        mapped_rows.append(rows)
        assert all(row["within_cell_offset_ns"] == 25_000_000 for row in rows)
        for block_start in range(0, CELL_COUNT, plan.block_cells):
            prediction_times = [
                row["prediction_utc_ns"]
                for row in rows[block_start : block_start + plan.block_cells]
            ]
            assert [
                later - earlier
                for earlier, later in zip(prediction_times, prediction_times[1:], strict=False)
            ] == [100_000_000] * (plan.block_cells - 1)

    assert [row["prediction_cell_index"] for row in mapped_rows[0]] == [
        row["prediction_cell_index"] for row in mapped_rows[1]
    ]
    mappings = {path.path_id: rows for path, rows in zip(problem.paths, mapped_rows, strict=True)}
    mapping_receipts, combined_digest = tool._mapping_receipts(plan, mappings)
    repeated_receipts, repeated_digest = tool._mapping_receipts(plan, mappings)
    assert mapping_receipts == repeated_receipts
    assert combined_digest == repeated_digest
    assert all(item["plan_digest"] == plan.plan_digest for item in mapping_receipts)
    assert all(item["mapping_digest"].startswith("sha256:") for item in mapping_receipts)
    assert receipt["same_plan_for_all_receiver_paths"]
    assert receipt["same_plan_for_all_catalogue_hypotheses"]
    assert not receipt["observation_inventory_modified"]


def test_correct_time_multipath_curve_activates_but_adapter_derangement_does_not() -> None:
    tool = _tool()
    problem = _problem()
    plan, _receipt = _plan(tool, problem)
    offsets = {"path-a": -40.0, "path-b": 75.0}
    correct = FixedMultipathSatelliteHypothesis(
        hypothesis_id="correct-time",
        object_name="SYNTHETIC-SATELLITE",
        catalog_number=1,
        delay_s=0.0,
        delay_prior_cost=0.0,
        paths=tuple(
            ReceiverPathFixedHypothesis(
                path_id=path.path_id,
                cfo_offset_hz=offsets[path.path_id],
                predictions=tuple(
                    PredictedProbeCfo(
                        probe.probe_id,
                        _curve(probe.time_s - 100.0),
                    )
                    for probe in path.probes
                ),
                eligible_by_cell=(True,) * CELL_COUNT,
            )
            for path in problem.paths
        ),
    )

    deranged_results = []
    for delay_s in (-0.2, 0.0, 0.2):
        path_hypotheses = []
        for path in problem.paths:
            mapped, _rows = tool._prediction_cell_mapping(
                plan,
                path,
                grid_start_utc_ns=GRID_START_UTC_NS,
                observation_utc_ns_by_probe_id=_utc_by_probe(path),
            )
            prediction = tuple(
                _curve(mapped[probe.probe_id] / 1e9 - 100.0 + delay_s) for probe in path.probes
            )
            observed = tuple(
                _curve(probe.time_s - 100.0) + offsets[path.path_id] for probe in path.probes
            )
            profile = profile_delay_and_cfo_offset(
                observed,
                (1.0,) * len(observed),
                (DelayProfileCandidate(delay_s, prediction),),
                delay_prior_mean_s=0.0,
                delay_prior_sigma_s=1.0,
                huber_threshold=1.0,
            )
            path_hypotheses.append(
                ReceiverPathFixedHypothesis(
                    path_id=path.path_id,
                    cfo_offset_hz=profile.posterior_best.fitted_cfo_offset_hz,
                    predictions=tuple(
                        PredictedProbeCfo(probe.probe_id, predicted)
                        for probe, predicted in zip(path.probes, prediction, strict=True)
                    ),
                    eligible_by_cell=(True,) * CELL_COUNT,
                )
            )
        deranged_results.append(
            decode_fixed_multipath_satellite(
                problem,
                FixedMultipathSatelliteHypothesis(
                    hypothesis_id=f"deranged-{delay_s:+.1f}",
                    object_name="SYNTHETIC-SATELLITE",
                    catalog_number=1,
                    delay_s=delay_s,
                    delay_prior_cost=0.0,
                    paths=tuple(path_hypotheses),
                ),
            )
        )

    correct_result = decode_fixed_multipath_satellite(problem, correct)
    assert correct_result.selected
    assert correct_result.objective.delta_from_null < 0.0
    assert all(not result.selected for result in deranged_results)
    assert all(
        result.objective.delta_from_null > correct_result.objective.delta_from_null
        for result in deranged_results
    )


def test_truth_flags_and_discriminators_never_upgrade_bounded_null_to_presence_fpr() -> None:
    tool = _tool()
    retained = tool.truth_flags(
        activation=False,
        retained_cartesian_exhausted=True,
        per_catalog_state_banks_pruned=True,
    )
    prefix = tool.truth_flags(
        activation=False,
        retained_cartesian_exhausted=False,
        per_catalog_state_banks_pruned=True,
    )

    assert (
        tool.result_discriminator(activation=False, retained_cartesian_exhausted=True)
        == tool.RETAINED_NULL_DISCRIMINATOR
    )
    assert (
        tool.result_discriminator(activation=False, retained_cartesian_exhausted=False)
        == tool.PREFIX_NULL_DISCRIMINATOR
    )
    assert not retained["null_vs_any_activation_solved"]
    assert not prefix["null_vs_any_activation_solved"]
    for flags in (retained, prefix):
        assert flags["conditional_prediction_time_specificity_control"]
        assert not flags["specificity_claimed"]
        assert not flags["signal_absence_control"]
        assert not flags["raw_presence_false_positive_rate_estimated"]
        assert not flags["catalogue_search_exact"]
        assert not flags["global_optimum_claimed"]


def test_adapter_fails_closed_on_invalid_grid_binding_delay_and_qnap_output() -> None:
    tool = _tool()
    problem = _problem()
    plan, _receipt = _plan(tool, problem)
    path = problem.paths[0]
    bad_utc = _utc_by_probe(path)
    bad_utc.pop(next(iter(bad_utc)))

    with pytest.raises(ValueError, match="UTC binding differs"):
        tool._prediction_cell_mapping(
            plan,
            path,
            grid_start_utc_ns=GRID_START_UTC_NS,
            observation_utc_ns_by_probe_id=bad_utc,
        )
    with pytest.raises(ValueError, match="beyond maximum delay support"):
        tool.build_session_derangement(
            problem=problem,
            selection_context={"session_id": "invalid-delay"},
            maximum_delay_support_s=0.5,
            minimum_circular_displacement_blocks=1,
        )
    with pytest.raises(ValueError, match="qnap01"):
        tool.multipath._refuse_qnap_output(Path("/mnt/qnap01/control.json"))


def test_public_control_propagates_mapped_utc_and_discloses_saturated_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    base_problem = _problem()
    problem = MultipathSatelliteActivityProblem(
        grid=base_problem.grid,
        paths=base_problem.paths,
        costs=AssociationCostModel(
            satellite_cost=1_000_000.0,
            episode_cost=1_000_000.0,
            huber_threshold=1.0,
        ),
    )

    class Catalogue:
        satellite_numbers = (10, 20)
        names = ("STARLINK-10", "STARLINK-20")

        def __len__(self) -> int:
            return len(self.satellite_numbers)

    catalogue = Catalogue()
    monkeypatch.setattr(tool, "parse_element_sets", lambda _text: catalogue)

    contexts = []
    for path_index, path in enumerate(sorted(problem.paths, key=lambda item: item.path_id)):
        scan_path = tmp_path / f"scan-{path_index}.json"
        scan = {"maximum_scored_candidates_per_probe": 2}
        scan_path.write_text(json.dumps(scan), encoding="utf-8")
        scan_digest = tool.multipath._file_digest(scan_path)
        utc_by_probe = _utc_by_probe(path)
        probe_utc = tuple(
            tool.multipath._ProbeUtc(
                probe_id=probe.probe_id,
                estimate_utc_ns=utc_by_probe[probe.probe_id],
                earliest_utc_ns=(
                    GRID_START_UTC_NS + 400_000_000
                    if probe.cell_index == 4
                    else utc_by_probe[probe.probe_id] - 1_000_000
                ),
                latest_utc_ns=(
                    GRID_START_UTC_NS + 510_000_000
                    if probe.cell_index == 4
                    else utc_by_probe[probe.probe_id] + 1_000_000
                ),
                cell_index=probe.cell_index,
                usable=True,
                retained_candidate_count=2 if probe.cell_index == 0 else 1,
            )
            for probe in path.probes
        )
        raw_observations = tuple(
            tool.raw_replay._RawObservation(
                observation_id=observation.observation_id,
                exclusion_group_id=observation.exclusion_group_id,
                probe_id=observation.probe_id,
                probe_index=index,
                cfo_hz=observation.cfo_hz,
                margin=0.5,
                rank=0,
                group_minimum_rank=0,
                group_maximum_margin=0.5,
                group_member_count=1,
                local_epoch_offset_s=0.0,
            )
            for index, observation in enumerate(path.observations)
        ) + (
            tool.raw_replay._RawObservation(
                observation_id=f"{path.path_id}-weak-extra",
                exclusion_group_id=f"{path.path_id}-weak-group",
                probe_id=path.probes[0].probe_id,
                probe_index=0,
                cfo_hz=0.0,
                margin=-0.5,
                rank=1,
                group_minimum_rank=1,
                group_maximum_margin=-0.5,
                group_member_count=1,
                local_epoch_offset_s=0.0,
            ),
        )
        single_path_problem = tool.raw_replay.SatelliteActivityProblem(
            grid=problem.grid,
            probes=path.probes,
            observations=path.observations,
            costs=problem.costs,
        )
        inventory = tool.raw_replay._RawInventory(
            problem=single_path_problem,
            observations=raw_observations,
            source_candidate_count=len(raw_observations),
            returned_candidate_count=len(raw_observations),
            exclusion_group_count=len(raw_observations),
            positive_candidate_count=len(path.observations),
            positive_exclusion_group_count=len(path.observations),
            modeled_exclusion_group_count=len(path.observations),
            unsupported_positive_candidate_count=0,
            unsupported_positive_exclusion_group_count=0,
            dominated_weak_candidate_count=1,
            dominated_weak_exclusion_group_count=1,
            elided_clutter_constant=1.5 + path_index,
            saturated_probe_count=1,
            local_epoch_min_s=0.0,
            local_epoch_max_s=0.0,
            scan_path=scan_path,
            scan_digest=scan_digest,
        )
        contexts.append(
            tool.multipath._PathContext(
                path_id=path.path_id,
                dataset={
                    "capture": {
                        "session_id": "synthetic-session",
                        "recording_manifest_digest": "sha256:" + "a" * 64,
                        "sample_rate_hz": 10,
                        "declared_sample_count": 40,
                    },
                    "frequency_binding": {
                        "sky_frequency_hz": 11_000_000_000.0 + path_index * 100_000_000.0
                    },
                    "timing_binding": {
                        "first_estimate_utc_ns": GRID_START_UTC_NS,
                        "last_estimate_utc_ns": (
                            GRID_START_UTC_NS + CELL_COUNT * 100_000_000 - 100_000_000
                        ),
                    },
                },
                dataset_path=tmp_path / f"duration-{path_index}.json",
                dataset_digest="sha256:" + str(path_index + 1) * 64,
                scan_content_digest=canonical_digest(scan),
                window_rows=tuple({"probe_id": item.probe_id} for item in path.probes),
                probe_utc=probe_utc,
                inventory=inventory,
            )
        )
    bound_contexts = tuple(contexts)
    monkeypatch.setattr(tool.multipath, "_load_path_contexts", lambda **_kwargs: bound_contexts)
    monkeypatch.setattr(tool.multipath, "_multipath_problem", lambda *_args, **_kwargs: problem)

    calibration_document = {"schema": tool.raw_replay.CALIBRATION_SCHEMA_V3}
    calibration_path = tmp_path / "calibration.json"
    calibration_path.write_text(json.dumps(calibration_document), encoding="utf-8")
    tle_path = tmp_path / "catalog.tle"
    tle_path.write_text("synthetic digest-bound catalogue\n", encoding="utf-8")
    monkeypatch.setattr(tool.raw_replay, "_validate_calibration_grouping", lambda *_a, **_k: None)
    monkeypatch.setattr(
        tool.raw_replay,
        "_score",
        lambda _document: SimpleNamespace(weak_match_is_dominated_by_miss=lambda: True),
    )

    scheduled_times_by_frequency: dict[float, tuple[float, ...]] = {}

    def prediction_bank(**kwargs: Any) -> Any:
        scheduled_times_by_frequency[float(kwargs["sky_frequency_hz"])] = tuple(
            kwargs["scheduled_times_s"]
        )
        accounting = tool.catalogue_screen.CatalogueGeometryAccounting(
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
            eligible_catalog_count=2,
        )
        return SimpleNamespace(
            catalogue_indices=(0, 1),
            accounting=accounting,
            scheduled_times_s=tuple(kwargs["scheduled_times_s"]),
        )

    monkeypatch.setattr(
        tool.catalogue_screen,
        "build_catalogue_prediction_bank",
        prediction_bank,
    )
    scored_prediction_times: dict[str, tuple[float, ...]] = {}

    def score_catalogues(**kwargs: Any) -> tuple[Any, ...]:
        scores = []
        for catalogue_index in kwargs["catalogue_indices"]:
            path_states = []
            fixed_paths = []
            for path in kwargs["problem"].paths:
                prediction = tuple(kwargs["path_banks"][path.path_id].bank.scheduled_times_s)
                scored_prediction_times[path.path_id] = prediction
                path_states.append(
                    tool.multipath._PathModeState(
                        path_id=path.path_id,
                        cfo_offset_hz=0.0,
                        support_group_count=0,
                        support_probe_count=0,
                        minimum_elevation_deg=60.0,
                        maximum_elevation_deg=60.0,
                        predictions_hz=prediction,
                        eligible_by_cell=(True,) * CELL_COUNT,
                    )
                )
                fixed_paths.append(
                    ReceiverPathFixedHypothesis(
                        path_id=path.path_id,
                        cfo_offset_hz=0.0,
                        predictions=tuple(
                            PredictedProbeCfo(probe.probe_id, value)
                            for probe, value in zip(path.probes, prediction, strict=True)
                        ),
                        eligible_by_cell=(True,) * CELL_COUNT,
                    )
                )
            hypothesis = FixedMultipathSatelliteHypothesis(
                hypothesis_id=f"deranged-catalog-{catalogue_index}",
                object_name=catalogue.names[catalogue_index],
                catalog_number=catalogue.satellite_numbers[catalogue_index],
                delay_s=0.0,
                delay_prior_cost=0.0,
                paths=tuple(fixed_paths),
            )
            state = tool.multipath._StateEvaluation(
                hypothesis=hypothesis,
                paths=tuple(path_states),
                single_total_cost=float(catalogue_index),
                single_delta_from_null=float(catalogue_index),
                single_selected=False,
            )
            bank = tool.multipath._CatalogBank(
                generated=(state,),
                retained=(state,),
                possible_path_offset_combination_count=1,
                evaluated_path_offset_combination_count=1,
                path_offset_cartesian_exhausted=True,
            )
            scores.append(
                tool._CatalogScore(
                    catalogue_index=catalogue_index,
                    catalog_number=catalogue.satellite_numbers[catalogue_index],
                    object_name=catalogue.names[catalogue_index],
                    bank=bank,
                )
            )
        return tuple(scores)

    monkeypatch.setattr(tool, "_score_catalogues", score_catalogues)
    config = tool.multipath.MultipathReplayConfig(
        satellite_cost=problem.costs.satellite_cost,
        episode_cost=problem.costs.episode_cost,
        delay_min_s=0.0,
        delay_max_s=0.0,
        modes_per_delay=1,
        retained_states_per_catalog=1,
        maximum_state_combinations=1,
        maximum_path_offset_combinations_per_delay=1,
    )
    screen_config = tool.CatalogueScreenConfig(
        coarse_delay_step_s=0.5,
        refinement_catalog_count=2,
        maximum_refinement_catalog_count=2,
        final_catalog_count=2,
    )

    document = tool.control_raw_multipath_block_derangement(
        dataset_paths=tuple(item.dataset_path for item in bound_contexts),
        expected_dataset_digests=tuple(item.dataset_digest for item in bound_contexts),
        calibration_document=calibration_document,
        calibration_path=calibration_path,
        expected_calibration_digest=tool.multipath._file_digest(calibration_path),
        tle_path=tle_path,
        expected_tle_digest=tool.multipath._file_digest(tle_path),
        start_utc_ns=GRID_START_UTC_NS,
        end_utc_ns=GRID_START_UTC_NS + CELL_COUNT * 100_000_000,
        observer=ObserverSiteV1(
            latitude_deg=37.0,
            longitude_deg=-122.0,
            altitude_m=10.0,
            label="synthetic observer",
        ),
        config=config,
        screen_config=screen_config,
        minimum_circular_displacement_blocks=1,
        control_label="frozen-synthetic-public-control",
    )

    assert document["schema"] == tool.OUTPUT_SCHEMA
    assert document["search_configuration_digest"] == canonical_digest(
        document["search_configuration"]
    )
    assert document["result_discriminator"] == tool.RETAINED_NULL_DISCRIMINATOR
    assert not document["null_vs_any_activation_solved"]
    assert not document["raw_presence_false_positive_rate_estimated"]
    assert document["retained_joint_state_space_exhausted"]
    cap_accounting = document["inventory_cap_accounting"]
    assert cap_accounting["maximum_scored_candidates_per_probe"] == 2
    assert cap_accounting["actual_maximum_returned_candidates_per_probe"] == 2
    assert cap_accounting["probe_count_at_retained_candidate_cap"] == 2
    assert cap_accounting["declared_post_acquisition_inventory_complete"]
    assert not cap_accounting["pre_acquisition_cap_inventory_complete"]
    assert not cap_accounting["physical_signal_inventory_complete"]
    assert all(
        item["candidate_cap_accounting"]["probe_count_at_retained_candidate_cap"] == 1
        for item in document["path_inventories"]
    )
    timing = document["timing_uncertainty_accounting"]
    assert timing["prediction_epochs_use_point_estimates"]
    assert timing["timing_interval_crosses_derangement_block_boundary_count"] == 2
    assert all(
        item["timing_interval_crosses_derangement_block_boundary_count"] == 1
        for item in document["path_inventories"]
    )
    assert document["unchanged_observation_accounting"]["observations_unchanged"]
    assert all(
        item["before_control_digest"] == item["after_control_digest"]
        for item in document["unchanged_observation_accounting"]["paths"]
    )

    first_sample_by_path = {
        item.path_id: item.dataset["timing_binding"]["first_estimate_utc_ns"]
        for item in bound_contexts
    }
    frequency_by_path = {
        item.path_id: item.dataset["frequency_binding"]["sky_frequency_hz"]
        for item in bound_contexts
    }
    for mapping_receipt in document["activity_block_derangement"]["path_probe_prediction_mappings"]:
        path_id = mapping_receipt["path_id"]
        expected_times = tuple(
            (row["prediction_utc_ns"] - first_sample_by_path[path_id]) / 1e9
            for row in mapping_receipt["mapping"]
        )
        assert scheduled_times_by_frequency[frequency_by_path[path_id]] == expected_times
        assert scored_prediction_times[path_id] == expected_times
        assert any(
            row["prediction_utc_ns"] != row["observation_utc_ns"]
            for row in mapping_receipt["mapping"]
        )

    modeled = document["association"]["objective"]
    persisted = document["decision"]["full_persisted_inventory_objective"]
    elided = persisted["constant_elided_from_exact_decision_problem"]
    assert persisted["null_cost"] == pytest.approx(modeled["null_cost"] + elided)
    assert persisted["total_cost"] == pytest.approx(modeled["total_cost"] + elided)
    assert persisted["delta_from_null"] == pytest.approx(modeled["delta_from_null"])
    assert not persisted["physical_inventory_completeness_claimed"]
    assert any(
        "best evaluated bounded nuisance-state bank or prefix" in caveat
        for caveat in document["caveats"]
    )
