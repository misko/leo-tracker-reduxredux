from __future__ import annotations

import copy
import hashlib
import importlib.util
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from leo.analysis.research.satellite_activity import (  # type: ignore[import-untyped]
    ActivityGrid,
    AssociationCostModel,
    CfoCandidate,
    CfoProbe,
    SatelliteActivityProblem,
)
from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]


def _tool() -> ModuleType:
    path = (
        Path(__file__).parents[2]
        / "tools/replay_raw_full_catalogue_paired_prediction_time_specificity.py"
    )
    spec = importlib.util.spec_from_file_location(
        "raw_full_catalogue_paired_prediction_time_specificity_tool", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _problem() -> SatelliteActivityProblem:
    probes = tuple(
        CfoProbe(
            probe_id=f"p{cell:03d}",
            time_s=50.0 + cell * 0.1 + 0.025,
            cell_index=cell,
            missed_detection_cost=1.0,
        )
        for cell in range(100)
    )
    observations = tuple(
        CfoCandidate(
            observation_id=f"o{cell:03d}",
            probe_id=probe.probe_id,
            exclusion_group_id=f"g{cell:03d}",
            cfo_hz=0.0,
            sigma_hz=1.0,
            clutter_cost=1.0,
            matched_base_cost=0.0,
            component_id="component",
        )
        for cell, probe in enumerate(probes)
    )
    return SatelliteActivityProblem(
        grid=ActivityGrid(
            start_s=50.0,
            cell_duration_s=0.1,
            cell_count=100,
            minimum_active_cells=5,
        ),
        probes=probes,
        observations=observations,
        costs=AssociationCostModel(satellite_cost=5.25, episode_cost=5.75),
    )


def _persisted(problem: SatelliteActivityProblem) -> tuple[dict[str, Any], ...]:
    first_utc_ns = 1_000_000_000_000
    return tuple(
        {
            "probe_id": probe.probe_id,
            "estimate_utc_ns": first_utc_ns + round(probe.time_s * 1e9),
            "earliest_utc_ns": first_utc_ns + round(probe.time_s * 1e9),
            "latest_utc_ns": first_utc_ns + round(probe.time_s * 1e9),
            "source_prediction_time_s": probe.time_s,
            "source_prediction_utc_ns": first_utc_ns + round(probe.time_s * 1e9),
            "observation_cell_index": probe.cell_index,
            "within_activity_cell_offset_ns": 25_000_000,
        }
        for probe in problem.probes
    )


def _partition(tool: ModuleType) -> dict[str, Any]:
    payload = {
        "schema": tool.bounded.IDENTITY_PARTITION_SCHEMA,
        "algorithm": tool.bounded.IDENTITY_PARTITION_ALGORITHM,
        "tle_digest": "sha256:" + "a" * 64,
        "catalogue_name_prefix": "STARLINK",
        "catalogue_object_count": 2,
        "named_catalog_count": 2,
        "eligible_catalog_count": 2,
        "named_ineligible_catalog_count": 0,
        "named_catalog_numbers": [10, 20],
        "eligible_catalog_numbers": [10, 20],
        "named_ineligible_catalog_numbers": [],
        "named_catalog_numbers_digest": canonical_digest([10, 20]),
        "eligible_catalog_numbers_digest": canonical_digest([10, 20]),
        "named_ineligible_catalog_numbers_digest": canonical_digest([]),
        "partition_exhausted": True,
        "partition_pruned": False,
        "eligibility_semantics": "named-and-full-window-visible-over-declared-delay-grid",
    }
    return {**payload, "partition_content_digest": canonical_digest(payload)}


def _row(
    tool: ModuleType,
    *,
    rank: int,
    catalog_number: int,
    delta: float,
    modeled_null: float,
) -> dict[str, Any]:
    hypothesis_id = canonical_digest(
        {"catalog_number": catalog_number, "delta": delta, "synthetic": True}
    )
    return {
        "rank": rank,
        "catalog_number": catalog_number,
        "object_name": f"STARLINK-{catalog_number}",
        "catalogue_index": rank - 1,
        "generated_state_count": 82,
        "configured_satellite_cost": 5.25,
        "best_single_total_cost": modeled_null + delta,
        "best_single_delta_from_null": delta,
        "best_single_selected": delta < 0.0,
        "best_delay_s": 0.0,
        "best_cfo_offset_hz": 0.0,
        "delay_prior_cost": 0.0,
        "mode_support_probe_count": 100,
        "mode_support_group_count": 100,
        "minimum_elevation_deg": 20.0,
        "maximum_elevation_deg": 30.0,
        "best_hypothesis_id": hypothesis_id,
        "state_bank_digest_algorithm": tool.STATE_DIGEST_ALGORITHM,
        "state_bank_digest": canonical_digest(
            {"catalog_number": catalog_number, "complete_state_count": 82, "delta": delta}
        ),
        "best_modeled_objective": {
            "null_cost": modeled_null,
            "total_cost": modeled_null + delta,
            "delta_from_null": delta,
        },
    }


def _arm(
    tool: ModuleType,
    *,
    transform: Any,
    common_digests: dict[str, str],
    problem: SatelliteActivityProblem,
    persisted: tuple[dict[str, Any], ...],
    deltas: tuple[tuple[int, float], tuple[int, float]],
) -> dict[str, Any]:
    _mapped, mapping = tool.fixed._prediction_mapping(
        transform=transform, persisted_probe_utc=persisted, problem=problem
    )
    partition = _partition(tool)
    modeled_null = tool.bounded._modeled_null_cost(problem)
    ordered = sorted(deltas, key=lambda item: (item[1], item[0]))
    rows = [
        _row(
            tool,
            rank=rank,
            catalog_number=catalog_number,
            delta=delta,
            modeled_null=modeled_null,
        )
        for rank, (catalog_number, delta) in enumerate(ordered, start=1)
    ]
    state_members = [
        {
            "catalog_number": row["catalog_number"],
            "generated_state_count": 82,
            "state_bank_digest": row["state_bank_digest"],
        }
        for row in rows
    ]
    state_payload = {
        "state_digest_algorithm": tool.STATE_DIGEST_ALGORITHM,
        "expected_state_count_per_eligible_catalogue": 82,
        "eligible_catalogue_count": 2,
        "expected_generated_state_count": 164,
        "generated_state_count": 164,
        "members": state_members,
    }
    winner = rows[0]
    delta = float(winner["best_single_delta_from_null"])
    selected = delta < 0.0
    return {
        "arm_id": transform.arm_id,
        "role": transform.role,
        "transform_digest": transform.transform_digest,
        "transform": transform.receipt,
        "common_digests": common_digests,
        "prediction_epoch_mapping": mapping,
        "catalogue_identity_partition": partition,
        "catalogue_identity_partition_binding_digest": tool._partition_binding(
            arm_id=transform.arm_id,
            transform_digest=transform.transform_digest,
            mapping_digest=mapping["mapping_digest"],
            partition_digest=partition["partition_content_digest"],
        ),
        "geometry_accounting": {
            "catalogue_object_count": 2,
            "unique_catalog_number_count": 2,
            "nonmatching_name_count": 0,
            "name_selected_count": 2,
            "coarse_propagation_failure_count": 0,
            "implausible_altitude_count": 0,
            "safely_below_horizon_count": 0,
            "fine_propagation_failure_count": 0,
            "fine_implausible_altitude_count": 0,
            "not_full_window_visible_count": 0,
            "eligible_catalog_count": 2,
        },
        "finite_catalogue_search": {
            "named_catalogue_exhausted": True,
            "eligible_catalogue_rows_exhausted": True,
            "declared_discrete_delay_grid_exhausted": True,
            "generated_data_proposed_cfo_mode_bank_exhausted": True,
            "catalogue_shortlist_applied": False,
            "catalogue_rows_pruned": False,
            "nuisance_states_pruned": False,
            "finite_declared_search_exact": True,
            "delay_grid": list(tool.raw_replay.RawReplayConfig().delay_grid),
            "modes_per_delay": 2,
            "ranking": rows,
            "ranking_digest": canonical_digest(rows),
            "state_accounting": {
                **state_payload,
                "content_digest": canonical_digest(state_payload),
            },
        },
        "decision": {
            "selected_catalog_numbers": [winner["catalog_number"]] if selected else [],
            "selected_satellite_count": int(selected),
            "activation_witness_found": selected,
            "best_catalog_number": winner["catalog_number"],
            "best_object_name": winner["object_name"],
            "best_hypothesis_id": winner["best_hypothesis_id"],
            "test_statistic_improvement_from_null": max(0.0, -delta),
            "test_statistic_definition": "max(0, -primitive best catalogue delta_from_null)",
            "signed_primitive_improvement_from_null": -delta,
            "nonnegative_activation_improvement_from_null": max(0.0, -delta),
            "full_persisted_inventory_objective": {
                "null_cost": modeled_null,
                "total_cost": modeled_null + delta,
                "delta_from_null": delta,
                "modeled_null_cost": modeled_null,
                "modeled_total_cost": modeled_null + delta,
                "decision_invariant_delta_from_null": delta,
                "constant_elided_from_exact_decision_problem": 0.0,
            },
            "winning_catalogue_minimum": winner,
        },
    }


def _artifact(
    tool: ModuleType,
    *,
    identity_deltas: tuple[tuple[int, float], tuple[int, float]] = ((10, -10.0), (20, -3.0)),
    control_deltas: tuple[tuple[int, float], tuple[int, float]] = ((10, -2.0), (20, -1.0)),
    minimum_advantage_cost: float = 1.0,
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
    problem = _problem()
    persisted = _persisted(problem)
    raw_problem = {
        "decision_problem": asdict(problem),
        "persisted_probe_utc": list(persisted),
        "raw_candidate_bundles": [],
        "source_candidate_count": 100,
        "returned_candidate_count": 100,
        "probe_count_at_retained_candidate_cap": 0,
        "constant_elided_from_exact_decision_problem": 0.0,
        "pre_acquisition_cap_inventory_complete": False,
        "physical_signal_inventory_complete": False,
    }
    config = tool.raw_replay.RawReplayConfig()
    objective = {
        "single_satellite_decoder_algorithm": "exact-single-satellite-semimarkov-v1",
        "association_costs": asdict(problem.costs),
        "score_calibration_schema": "synthetic-calibration/v1",
        "score_calibration_file_digest": "sha256:" + "6" * 64,
        "score_calibration_content_digest": "sha256:" + "7" * 64,
        "constant_elision_is_decision_invariant": True,
        "test_statistic": "max(0, -primitive best catalogue delta_from_null)",
        "structural_costs_calibrated": False,
    }
    universe = {
        "mode": "same-complete-named-catalogue-reselected-independently-in-every-arm-v1",
        "single_receiver_path_only": True,
        "capture_wide_or_multipath_search_performed": False,
        "catalogue_name_prefix": "STARLINK",
        "geometry_spacing_s": 1.0,
        "tle_digest": "sha256:" + "a" * 64,
        "named_catalog_numbers": [10, 20],
        "named_catalog_numbers_digest": canonical_digest([10, 20]),
        "named_catalogue_count": 2,
        "each_arm_partitions_every_named_identity": True,
        "each_arm_reselects_its_own_best_norad": True,
        "catalogue_shortlist_permitted": False,
        "catalogue_or_state_pruning_permitted": False,
        "configuration": asdict(config),
        "delay_grid": list(config.delay_grid),
        "modes_per_delay": config.modes_per_delay,
        "expected_state_count_per_eligible_catalogue": 82,
        "observer": {"synthetic": True},
    }
    producer = tool.producer_implementation_manifest()
    partition = _partition(tool)
    path_identity = [
        "stream-0",
        "radio-test",
        "serial-test",
        0,
        "tuning:test",
        10_700_000_000.0,
    ]
    predeclared_path_payload = {
        "algorithm": tool.PATH_SCOPE_ALGORITHM,
        "path_id": canonical_digest(path_identity),
        "stream_id": path_identity[0],
        "radio_id": path_identity[1],
        "radio_serial": path_identity[2],
        "receiver_id": path_identity[3],
        "tuning_tag": path_identity[4],
        "sky_frequency_hz": path_identity[5],
    }
    evidence_path_payload = {
        **predeclared_path_payload,
        "duration_dataset_digest": "sha256:" + "d" * 64,
    }
    path_scope = {
        **evidence_path_payload,
        "path_scope_digest": canonical_digest(predeclared_path_payload),
        "evidence_path_scope_digest": canonical_digest(evidence_path_payload),
    }
    source_binding = {
        "schema": tool.SOURCE_SCHEMA,
        "algorithm": tool.SOURCE_ALGORITHM,
        "source_producer_implementation": tool.bounded.producer_implementation_manifest(),
        "source_artifact_path": "/synthetic/source.json",
        "source_artifact_file_digest": "sha256:" + "1" * 64,
        "source_artifact_content_digest": "sha256:" + "2" * 64,
        "duration_dataset_path": "/synthetic/duration.json",
        "duration_dataset_file_digest": "sha256:" + "d" * 64,
        "duration_dataset_content_digest": "sha256:" + "3" * 64,
        "pilot_scan_path": "/synthetic/scan.json",
        "pilot_scan_file_digest": "sha256:" + "4" * 64,
        "pilot_scan_content_digest": "sha256:" + "5" * 64,
        "score_calibration_path": "/synthetic/calibration.json",
        "score_calibration_file_digest": "sha256:" + "6" * 64,
        "score_calibration_content_digest": "sha256:" + "7" * 64,
        "tle_path": "/synthetic/catalogue.tle",
        "tle_file_digest": "sha256:" + "a" * 64,
        "session_id": "synthetic-session",
        "recording_manifest_digest": "sha256:" + "8" * 64,
        "source_exact_ranking_digest": "sha256:" + "9" * 64,
        "source_search_configuration_digest": "sha256:" + "b" * 64,
        "raw_inventory_receipt": {
            "source_candidate_count": 100,
            "returned_candidate_count": 100,
            "declared_post_acquisition_inventory_complete": True,
            "pre_acquisition_cap_inventory_complete": False,
            "truncated_candidate_count": 0,
            "probe_count_at_retained_candidate_cap": 0,
            "exclusion_group_count": 100,
            "positive_candidate_count_after_group_scoring": 100,
            "positive_exclusion_group_count": 100,
            "unsupported_positive_candidate_count": 0,
            "unsupported_positive_exclusion_group_count": 0,
            "modeled_candidate_count": 100,
            "modeled_exclusion_group_count": 100,
            "dominated_weak_candidate_count": 0,
            "dominated_weak_exclusion_group_count": 0,
            "dominated_weak_candidate_elision": {
                "applied": True,
                "decision_equivalent_under_nonnegative_residual_loss": True,
                "weak_match_is_dominated_by_miss": True,
                "unsupported_positive_groups_also_elided": True,
                "omitted_clutter_objective_constant": 0.0,
            },
            "physical_exclusion_grouping": {
                "alias_spacing_hz": 1_000.0,
                "exact_duplicate_cfo_tolerance_hz": 0.0,
                "exact_duplicate_refined_basins_collapsed": True,
                "resolution_epoch_tolerance_samples": 0,
                "resolution_tracking_cfo_tolerance_hz": 0.0,
                "unresolved_measurement_cells_collapsed": True,
                "resolution_cells_are_physical_source_identities": False,
                "nonidentical_integer_aliases_grouped": False,
            },
        },
        "timing_approximation_receipt": {
            "prediction_epoch": "scheduled_probe_start",
            "candidate_local_epoch_applied": False,
            "minimum_candidate_local_epoch_offset_s": None,
            "maximum_candidate_local_epoch_offset_s": None,
            "maximum_absolute_candidate_local_epoch_offset_s": 0.0,
        },
        "window": {
            "start_s": 50.0,
            "end_s": 60.0,
            "start_utc_ns": 1_050_000_000_000,
            "end_utc_ns": 1_060_000_000_000,
            "cell_count": 100,
        },
        "single_receiver_path_only": True,
        "capture_wide_or_multipath_search_performed": False,
        "other_receiver_paths_may_not_be_posthoc_confirmation": True,
        "source_identity_partition_content_digest": partition["partition_content_digest"],
        "path_id": path_scope["path_id"],
        "path_scope": path_scope,
    }
    preliminary = {
        "raw_problem_digest": canonical_digest(raw_problem),
        "objective_digest": canonical_digest(objective),
        "search_universe_digest": canonical_digest(universe),
        "producer_digest": canonical_digest(producer),
        "source_binding_digest": canonical_digest(source_binding),
    }
    selection = {
        "schema": tool.FAMILY_PLAN_SCHEMA,
        "algorithm": tool.ALGORITHM,
        "family_label": "synthetic-family",
        "session_id": "synthetic-session",
        "recording_manifest_digest": "sha256:" + "8" * 64,
        "control_indices": list(tool.REQUIRED_CONTROL_INDICES),
        "path_id": path_scope["path_id"],
        "path_scope_digest": path_scope["path_scope_digest"],
        "evidence_path_scope_digest": path_scope["evidence_path_scope_digest"],
        "stream_id": path_scope["stream_id"],
        "radio_id": path_scope["radio_id"],
        "radio_serial": path_scope["radio_serial"],
        "receiver_id": path_scope["receiver_id"],
        "tuning_tag": path_scope["tuning_tag"],
        "sky_frequency_hz": path_scope["sky_frequency_hz"],
        "duration_dataset_digest": path_scope["duration_dataset_digest"],
        "window": {
            "start_s": 50.0,
            "end_s": 60.0,
            "cell_duration_s": 0.1,
            "cell_count": 100,
            "minimum_active_cells": 5,
        },
        **preliminary,
        "minimum_advantage_cost": minimum_advantage_cost,
        "prospective_plan_binding_digest": None,
        "randomization_exchangeability_verified": False,
        "permutation_p_value": None,
        "same_named_catalogue_reselected_in_every_arm": True,
    }
    selection_digest = canonical_digest(selection)
    transforms = tool._freeze_arm_transforms(
        problem=SimpleNamespace(grid=problem.grid),
        selection_context_digest=selection_digest,
        control_indices=tool.REQUIRED_CONTROL_INDICES,
        maximum_delay_support_s=2.0,
    )
    family = {
        "schema": tool.FAMILY_PLAN_SCHEMA,
        "algorithm": tool.ALGORITHM,
        "selection_context": selection,
        "selection_context_digest": selection_digest,
        "arm_selection_context_digest": selection_digest,
        "arm_selection_context_source": "diagnostic-evidence-bound-context",
        "control_indices": list(tool.REQUIRED_CONTROL_INDICES),
        "control_count": 20,
        "minimum_advantage_cost": minimum_advantage_cost,
        "randomization_exchangeability_verified": False,
        "permutation_p_value": None,
        "prospective_plan_binding_verified": False,
        "plan_authority_verified": False,
        "external_preregistration_verified": False,
        "prospective_plan_binding": None,
        "arms": [
            {
                "arm_id": transform.arm_id,
                "role": transform.role,
                "transform_digest": transform.transform_digest,
                "transform": transform.receipt,
            }
            for transform in transforms
        ],
        "family_frozen_before_arm_scoring": True,
        "all_control_plans_built_before_arm_scoring": True,
        "full_catalogue_procedure_frozen_before_arm_scoring": True,
    }
    common_digests = {**preliminary, "family_plan_digest": canonical_digest(family)}
    common = {
        "digests": common_digests,
        "raw_problem": raw_problem,
        "objective": objective,
        "search_universe": universe,
        "producer": producer,
        "source_binding": source_binding,
        "family_plan": family,
    }
    arms = tuple(
        _arm(
            tool,
            transform=transform,
            common_digests=common_digests,
            problem=problem,
            persisted=persisted,
            deltas=identity_deltas if transform.role == "identity" else control_deltas,
        )
        for transform in transforms
    )
    return arms, common


def _resign_common_field(
    *,
    arms: tuple[dict[str, Any], ...],
    common: dict[str, Any],
    field: str,
    mutation: Callable[[dict[str, Any]], None],
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
    resigned_common = copy.deepcopy(common)
    resigned_arms = copy.deepcopy(arms)
    mutation(resigned_common[field])
    digest_field = f"{field}_digest"
    resigned_common["digests"][digest_field] = canonical_digest(resigned_common[field])
    for arm in resigned_arms:
        arm["common_digests"] = copy.deepcopy(resigned_common["digests"])
    return tuple(resigned_arms), resigned_common


def _synthetic_document(
    tool: ModuleType,
    *,
    arms: tuple[dict[str, Any], ...],
    common: dict[str, Any],
) -> dict[str, Any]:
    document = {
        "schema": tool.OUTPUT_SCHEMA,
        "algorithm": tool.ALGORITHM,
        "research_only": True,
        "candidate_only": True,
        "single_receiver_path_only": True,
        "capture_wide_or_multipath_search_performed": False,
        "association_claimed": False,
        "tracking_claimed": False,
        "specificity_claimed": False,
        "payload_decoded": False,
        "presence_false_positive_rate_estimated": False,
        "randomization_exchangeability_verified": False,
        "permutation_p_value": None,
        "block_controls_are_conditional_prediction_time_specificity_only": True,
        "all_arms_share_one_loaded_raw_problem": True,
        "all_arms_share_one_objective": True,
        "same_named_catalogue_reselected_in_every_arm": True,
        "every_arm_partitions_every_named_identity": True,
        "all_declared_arms_emitted": True,
        "prospective_plan_binding_verified": False,
        "plan_authority_verified": False,
        "external_preregistration_verified": False,
        "continuous_nuisance_space_exhausted": False,
        "pre_acquisition_cap_inventory_complete": False,
        "physical_signal_inventory_complete": False,
        "common": common,
        "arms": list(arms),
        "adjudication": tool.adjudicate_full_catalogue_arms(arms=arms, common=common),
        "caveats": list(tool.OUTPUT_CAVEATS),
    }
    document["payload_content_digest"] = canonical_digest(document)
    return document


def test_exact_controls_and_no_inferential_permutation_p_value() -> None:
    tool = _tool()
    arms, common = _artifact(tool)

    result = tool.adjudicate_full_catalogue_arms(arms=arms, common=common)

    assert result["comparable"] is True
    assert result["disposition"] == tool.PLAN_AUTHORITY_NOT_VERIFIED
    assert result["conditional_full_catalogue_gate_passed"] is True
    assert result["authority_gate_passed"] is False
    assert result["T_identity"] == 10.0
    assert result["T_control_max"] == 2.0
    assert result["A_k"] == 8.0
    assert result["per_dwell_dominance_A_k"] == 8.0
    assert result["identity_winner_over_runner_cost_margin"] == 7.0
    assert result["descriptive_control_rank"] == {
        "inferential_permutation_p_value": None,
        "randomization_exchangeability_verified": False,
        "interpretation": "descriptive rank only; not a p-value or false-positive rate",
        "control_count": 20,
        "controls_with_T_at_least_identity_count": 0,
        "identity_rank_among_21": 1,
        "minimum_possible_rank_fraction": 1.0 / 21.0,
    }
    assert result["presence_false_positive_rate_estimated"] is False


def test_full_catalogue_confuser_can_win_a_control_and_activate() -> None:
    tool = _tool()
    arms, common = _artifact(
        tool,
        identity_deltas=((10, -10.0), (20, -3.0)),
        control_deltas=((10, -2.0), (20, -12.0)),
    )

    result = tool.adjudicate_full_catalogue_arms(arms=arms, common=common)

    assert result["strongest_control_best_catalog_number"] == 20
    assert result["controls"][0]["best_catalog_number"] == 20
    assert result["controls"][0]["activation_witness_found"] is True
    assert result["descriptive_control_rank"]["controls_with_T_at_least_identity_count"] == 20
    assert result["strict_margin_passed"] is False
    assert result["disposition"] == tool.STRICT_MARGIN_NOT_PASSED


def test_exact_null_identity_and_controls_remain_nonactivating() -> None:
    tool = _tool()
    arms, common = _artifact(
        tool,
        identity_deltas=((10, 0.0), (20, 0.0)),
        control_deltas=((10, 0.0), (20, 0.0)),
    )

    result = tool.adjudicate_full_catalogue_arms(arms=arms, common=common)

    assert result["comparable"] is True
    assert result["disposition"] == tool.IDENTITY_NONACTIVATION
    assert result["identity_best_catalog_number"] == 10
    assert result["identity_test_statistic_improvement_from_null"] == 0.0
    assert all(not item["activation_witness_found"] for item in result["controls"])


def test_one_eligible_catalogue_uses_the_exact_null_as_its_runner() -> None:
    tool = _tool()
    arms, _common = _artifact(tool)
    arm = copy.deepcopy(arms[0])
    search = arm["finite_catalogue_search"]
    search["ranking"] = search["ranking"][:1]
    search["ranking_digest"] = canonical_digest(search["ranking"])
    accounting = search["state_accounting"]
    accounting_payload = {
        "state_digest_algorithm": tool.STATE_DIGEST_ALGORITHM,
        "expected_state_count_per_eligible_catalogue": 82,
        "eligible_catalogue_count": 1,
        "expected_generated_state_count": 82,
        "generated_state_count": 82,
        "members": accounting["members"][:1],
    }
    search["state_accounting"] = {
        **accounting_payload,
        "content_digest": canonical_digest(accounting_payload),
    }

    statistic = tool._validate_arm_search(
        arm=arm,
        eligible=(10,),
        expected_states_per_member=82,
        modeled_null_cost=tool.bounded._modeled_null_cost(_problem()),
    )

    assert statistic["best_catalog_number"] == 10
    assert statistic["runner_up_catalog_number"] is None
    assert statistic["runner_up_delta_from_null"] == 0.0
    assert statistic["test_statistic"] == 10.0


def test_control_statistic_uses_the_null_floor_for_the_strict_margin() -> None:
    tool = _tool()
    arms, common = _artifact(
        tool,
        identity_deltas=((10, -4.0), (20, -1.0)),
        control_deltas=((10, 3.0), (20, 5.0)),
        minimum_advantage_cost=5.0,
    )

    result = tool.adjudicate_full_catalogue_arms(arms=arms, common=common)

    assert result["identity_test_statistic_improvement_from_null"] == 4.0
    assert result["strongest_control_test_statistic_improvement_from_null"] == 0.0
    assert result["per_dwell_dominance_A_k"] == 4.0
    assert result["controls"][0]["T"] == 0.0
    assert result["controls"][0]["test_statistic_improvement_from_null"] == 0.0
    assert result["controls"][0]["signed_primitive_improvement_from_null"] == -3.0
    assert result["controls"][0]["activation_witness_found"] is False
    assert result["strict_margin_passed"] is False
    assert result["disposition"] == tool.STRICT_MARGIN_NOT_PASSED


def test_verifier_rejects_resigned_top_level_claim_tamper_before_source_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    arms, common = _artifact(tool)
    adjudication = tool.adjudicate_full_catalogue_arms(arms=arms, common=common)
    document = {
        "schema": tool.OUTPUT_SCHEMA,
        "algorithm": tool.ALGORITHM,
        "research_only": True,
        "candidate_only": True,
        "single_receiver_path_only": True,
        "capture_wide_or_multipath_search_performed": False,
        "association_claimed": False,
        "tracking_claimed": False,
        "specificity_claimed": False,
        "payload_decoded": False,
        "presence_false_positive_rate_estimated": False,
        "randomization_exchangeability_verified": False,
        "permutation_p_value": None,
        "block_controls_are_conditional_prediction_time_specificity_only": True,
        "all_arms_share_one_loaded_raw_problem": True,
        "all_arms_share_one_objective": True,
        "same_named_catalogue_reselected_in_every_arm": True,
        "every_arm_partitions_every_named_identity": True,
        "all_declared_arms_emitted": True,
        "prospective_plan_binding_verified": False,
        "plan_authority_verified": False,
        "external_preregistration_verified": False,
        "continuous_nuisance_space_exhausted": False,
        "pre_acquisition_cap_inventory_complete": False,
        "physical_signal_inventory_complete": False,
        "common": common,
        "arms": list(arms),
        "adjudication": adjudication,
        "caveats": list(tool.OUTPUT_CAVEATS),
    }
    document["payload_content_digest"] = canonical_digest(document)
    document["association_claimed"] = True
    payload = dict(document)
    payload.pop("payload_content_digest")
    document["payload_content_digest"] = canonical_digest(payload)
    monkeypatch.setattr(
        tool,
        "_load_source",
        lambda **_keywords: (_ for _ in ()).throw(AssertionError("source was loaded")),
    )

    with pytest.raises(ValueError, match="authority, claim, or scope flags"):
        tool.verify_full_catalogue_document(document)


@pytest.mark.parametrize("count", [19, 21])
def test_freezer_rejects_control_count_other_than_exact_zero_through_nineteen(
    count: int,
) -> None:
    tool = _tool()
    problem = _problem()
    with pytest.raises(ValueError, match="exactly control indices 0 through 19"):
        tool._freeze_arm_transforms(
            problem=SimpleNamespace(grid=problem.grid),
            selection_context_digest="sha256:" + "a" * 64,
            control_indices=tuple(range(count)),
            maximum_delay_support_s=2.0,
        )


def test_freezer_rejects_omission_extra_retry_and_reordering() -> None:
    tool = _tool()
    problem = _problem()
    bad_families = (
        tuple(range(19)) + (20,),
        tuple(range(20)) + (19,),
        tuple(reversed(range(20))),
    )
    for controls in bad_families:
        with pytest.raises(ValueError, match="exactly control indices 0 through 19"):
            tool._freeze_arm_transforms(
                problem=SimpleNamespace(grid=problem.grid),
                selection_context_digest="sha256:" + "a" * 64,
                control_indices=controls,
                maximum_delay_support_s=2.0,
            )


def test_mapped_catalogue_propagation_is_monotone_then_inverse_scattered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    scheduled = (50.3, 50.1, 50.2)
    utc_ns = (503, 501, 502)

    class FakeBank:
        catalogue = SimpleNamespace()
        catalogue_indices = (0,)
        accounting = SimpleNamespace(eligible_catalog_count=1)

        @staticmethod
        def curve(_row_index: int, _delay_s: float) -> np.ndarray:
            return np.asarray([50.1, 50.2, 50.3])

        @staticmethod
        def elevation(_row_index: int, _delay_s: float) -> np.ndarray:
            return np.asarray([10.1, 10.2, 10.3])

    def build_bank(**keywords: Any) -> FakeBank:
        assert keywords["scheduled_times_s"] == (50.1, 50.2, 50.3)
        return FakeBank()

    monkeypatch.setattr(tool.screen, "build_catalogue_prediction_bank", build_bank)
    source = SimpleNamespace(
        catalogue=SimpleNamespace(),
        dataset={
            "timing_binding": {"first_estimate_utc_ns": 1_000_000_000},
            "frequency_binding": {"sky_frequency_hz": 10_700_000_000.0},
        },
        config=SimpleNamespace(delay_grid=(0.0,), horizon_mask_deg=0.0),
        observer=SimpleNamespace(),
    )

    bank = tool._build_mapped_catalogue_bank(
        source=source,
        scheduled_times=scheduled,
        prediction_utc_ns=utc_ns,
        name_prefix="STARLINK",
        geometry_spacing_s=0.5,
    )

    np.testing.assert_array_equal(bank.curve(0, 0.0), np.asarray(scheduled))
    np.testing.assert_array_equal(bank.elevation(0, 0.0), np.asarray([10.3, 10.1, 10.2]))


def test_mapping_tamper_is_not_comparable_even_if_receipt_digest_is_resigned() -> None:
    tool = _tool()
    arms, common = _artifact(tool)
    tampered = copy.deepcopy(list(arms))
    mapping = tampered[1]["prediction_epoch_mapping"]
    mapping["mapping"][0]["prediction_utc_ns"] += 1
    payload = {key: mapping[key] for key in ("arm_id", "transform_digest", "mapping")}
    mapping["mapping_digest"] = canonical_digest(payload)
    partition = tampered[1]["catalogue_identity_partition"]
    tampered[1]["catalogue_identity_partition_binding_digest"] = tool._partition_binding(
        arm_id=tampered[1]["arm_id"],
        transform_digest=tampered[1]["transform_digest"],
        mapping_digest=mapping["mapping_digest"],
        partition_digest=partition["partition_content_digest"],
    )

    result = tool.adjudicate_full_catalogue_arms(arms=tuple(tampered), common=common)

    assert result["comparable"] is False
    assert "mapping" in result["reasons"][0]


def test_incomplete_catalogue_and_state_banks_fail_closed() -> None:
    tool = _tool()
    arms, common = _artifact(tool)

    missing_catalogue = copy.deepcopy(list(arms))
    search = missing_catalogue[0]["finite_catalogue_search"]
    search["ranking"].pop()
    search["ranking_digest"] = canonical_digest(search["ranking"])
    result = tool.adjudicate_full_catalogue_arms(arms=tuple(missing_catalogue), common=common)
    assert result["comparable"] is False
    assert "eligible catalogue row" in result["reasons"][0]

    incomplete_state = copy.deepcopy(list(arms))
    incomplete_state[0]["finite_catalogue_search"]["ranking"][0]["generated_state_count"] = 81
    incomplete_state[0]["finite_catalogue_search"]["ranking_digest"] = canonical_digest(
        incomplete_state[0]["finite_catalogue_search"]["ranking"]
    )
    result = tool.adjudicate_full_catalogue_arms(arms=tuple(incomplete_state), common=common)
    assert result["comparable"] is False
    assert "incomplete nuisance-state bank" in result["reasons"][0]


def test_common_digest_drift_and_partition_drift_fail_closed() -> None:
    tool = _tool()
    arms, common = _artifact(tool)

    digest_drift = copy.deepcopy(common)
    digest_drift["objective"]["association_costs"]["satellite_cost"] += 1.0
    result = tool.adjudicate_full_catalogue_arms(arms=arms, common=digest_drift)
    assert result["comparable"] is False
    assert "digest does not recompute" in result["reasons"][0]

    partition_drift = copy.deepcopy(list(arms))
    partition_drift[1]["catalogue_identity_partition"]["tle_digest"] = "sha256:" + "b" * 64
    result = tool.adjudicate_full_catalogue_arms(arms=tuple(partition_drift), common=common)
    assert result["comparable"] is False
    assert "partition digest" in result["reasons"][0]


@pytest.mark.parametrize(
    ("field", "mutation", "reason"),
    [
        (
            "raw_problem",
            lambda value: value.update(pre_acquisition_cap_inventory_complete=True),
            "cap or physical-signal completeness",
        ),
        (
            "raw_problem",
            lambda value: value.update(physical_signal_inventory_complete=True),
            "cap or physical-signal completeness",
        ),
        (
            "raw_problem",
            lambda value: value.update(probe_count_at_retained_candidate_cap=101),
            "saturation accounting",
        ),
        (
            "source_binding",
            lambda value: value["raw_inventory_receipt"].update(
                pre_acquisition_cap_inventory_complete=True
            ),
            "cap semantics",
        ),
        (
            "source_binding",
            lambda value: value["raw_inventory_receipt"].update(
                physical_signal_inventory_complete=True
            ),
            "incomplete or extended",
        ),
        (
            "source_binding",
            lambda value: value["raw_inventory_receipt"].update(
                probe_count_at_retained_candidate_cap=101
            ),
            "candidate or saturation counts",
        ),
        (
            "source_binding",
            lambda value: value["timing_approximation_receipt"].update(
                candidate_local_epoch_applied=True
            ),
            "timing-approximation receipt",
        ),
        (
            "source_binding",
            lambda value: value["raw_inventory_receipt"]["physical_exclusion_grouping"].update(
                resolution_cells_are_physical_source_identities=True
            ),
            "physical-grouping receipt",
        ),
        (
            "objective",
            lambda value: value.update(structural_costs_calibrated=True),
            "objective receipt",
        ),
        (
            "search_universe",
            lambda value: value.update(
                catalogue_shortlist_permitted=True,
                catalogue_or_state_pruning_permitted=True,
            ),
            "search universe",
        ),
        (
            "family_plan",
            lambda value: value.update(
                randomization_exchangeability_verified=True,
                permutation_p_value=0.05,
            ),
            "family plan",
        ),
    ],
)
def test_resigned_common_semantic_claims_fail_closed(
    field: str,
    mutation: Callable[[dict[str, Any]], None],
    reason: str,
) -> None:
    tool = _tool()
    arms, common = _artifact(tool)
    resigned_arms, resigned_common = _resign_common_field(
        arms=arms,
        common=common,
        field=field,
        mutation=mutation,
    )

    result = tool.adjudicate_full_catalogue_arms(
        arms=resigned_arms,
        common=resigned_common,
    )

    assert result["comparable"] is False
    assert reason in result["reasons"][0]


def test_verifier_rebuilds_raw_problem_before_accepting_resigned_cap_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    arms, common = _artifact(tool)
    baseline_raw_problem = copy.deepcopy(common["raw_problem"])
    resigned_arms, resigned_common = _resign_common_field(
        arms=arms,
        common=common,
        field="raw_problem",
        mutation=lambda value: value.update(
            pre_acquisition_cap_inventory_complete=True,
            physical_signal_inventory_complete=True,
        ),
    )
    document = _synthetic_document(
        tool,
        arms=resigned_arms,
        common=resigned_common,
    )
    fake_source = SimpleNamespace()
    monkeypatch.setattr(tool, "_load_source", lambda **_keywords: fake_source)
    monkeypatch.setattr(
        tool,
        "_single_path_scope",
        lambda _source: resigned_common["source_binding"]["path_scope"],
    )
    monkeypatch.setattr(
        tool,
        "_source_binding_document",
        lambda _source, *, path_scope: resigned_common["source_binding"],
    )
    monkeypatch.setattr(tool.fixed, "_problem_payload", lambda _source: baseline_raw_problem)

    with pytest.raises(ValueError, match="raw problem does not regenerate"):
        tool.verify_full_catalogue_document(document)


def test_resigned_extreme_numeric_receipt_fails_closed_without_escaping() -> None:
    tool = _tool()
    arms, common = _artifact(tool)
    resigned_arms, resigned_common = _resign_common_field(
        arms=arms,
        common=common,
        field="search_universe",
        mutation=lambda value: value.update(geometry_spacing_s=10**309),
    )

    result = tool.adjudicate_full_catalogue_arms(
        arms=resigned_arms,
        common=resigned_common,
    )

    assert result["comparable"] is False
    assert "too large" in result["reasons"][0]


def test_deterministic_catalogue_ties_use_norad_then_hypothesis() -> None:
    tool = _tool()
    arms, common = _artifact(
        tool,
        identity_deltas=((20, -10.0), (10, -10.0)),
        control_deltas=((20, -1.0), (10, -1.0)),
    )
    result = tool.adjudicate_full_catalogue_arms(arms=arms, common=common)
    assert result["comparable"] is True
    assert result["identity_best_catalog_number"] == 10

    reversed_tie = copy.deepcopy(list(arms))
    ranking = reversed_tie[0]["finite_catalogue_search"]["ranking"]
    ranking.reverse()
    for rank, row in enumerate(ranking, start=1):
        row["rank"] = rank
    reversed_tie[0]["finite_catalogue_search"]["ranking_digest"] = canonical_digest(ranking)
    result = tool.adjudicate_full_catalogue_arms(arms=tuple(reversed_tie), common=common)
    assert result["comparable"] is False
    assert "deterministic" in result["reasons"][0]


def test_not_ready_prospective_plan_cannot_consume_a_cohort_ordinal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    from tools import freeze_prospective_starlink_tracking_plan as prospective

    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}\n", encoding="utf-8")
    plan_digest = "sha256:" + hashlib.sha256(plan_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        prospective,
        "load_and_validate_prospective_plan",
        lambda **_keywords: {
            "schema": tool.PROSPECTIVE_PLAN_SCHEMA,
            "algorithm": tool.PROSPECTIVE_PLAN_ALGORITHM,
            "execution_readiness": {
                "paired_producer_implementation_digest_slot_filled": True,
                "presence_null_qualification_receipt_present": False,
                "positive_sensitivity_qualification_receipt_present": False,
                "decision_threshold_calibration_receipt_present": False,
                "external_authority_authentication_present": False,
                "ready_to_consume_future_evidence": False,
            },
        },
    )

    with pytest.raises(ValueError, match="not ready to consume"):
        tool._validate_prospective_plan_binding(
            source=SimpleNamespace(),
            plan_path=plan_path,
            expected_plan_digest=plan_digest,
            cohort_ordinal=1,
            minimum_advantage_cost=1.0,
        )


def test_not_ready_plan_is_rejected_before_future_source_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    from tools import freeze_prospective_starlink_tracking_plan as prospective

    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}\n", encoding="utf-8")
    plan_digest = "sha256:" + hashlib.sha256(plan_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        prospective,
        "load_and_validate_prospective_plan",
        lambda **_keywords: {
            "execution_readiness": {
                "paired_producer_implementation_digest_slot_filled": True,
                "presence_null_qualification_receipt_present": False,
                "positive_sensitivity_qualification_receipt_present": False,
                "decision_threshold_calibration_receipt_present": False,
                "external_authority_authentication_present": False,
                "ready_to_consume_future_evidence": False,
            }
        },
    )
    monkeypatch.setattr(
        tool,
        "_load_source",
        lambda **_keywords: (_ for _ in ()).throw(AssertionError("future source was loaded")),
    )

    with pytest.raises(ValueError, match="not ready to consume"):
        tool.replay_raw_full_catalogue_paired_prediction_time(
            source_path=tmp_path / "future-source.json",
            expected_source_digest="sha256:" + "a" * 64,
            control_indices=tool.REQUIRED_CONTROL_INDICES,
            family_label="plan",
            minimum_advantage_cost=1.0,
            prospective_plan_path=plan_path,
            expected_prospective_plan_digest=plan_digest,
            prospective_cohort_ordinal=1,
        )


def test_output_is_create_only_and_refuses_protected_roots(tmp_path: Path) -> None:
    tool = _tool()
    output = tmp_path / "receipt.json"
    tool._write_new("{}\n", output)
    assert output.read_text(encoding="utf-8") == "{}\n"
    with pytest.raises(ValueError, match="already exists"):
        tool._write_new("{}\n", output)
    with pytest.raises(ValueError, match="/srv"):
        tool._write_new("{}\n", Path("/srv/bulk/leo/forbidden.json"))
    with pytest.raises(ValueError, match="/mnt/qnap01"):
        tool._write_new("{}\n", Path("/mnt/qnap01/forbidden.json"))
