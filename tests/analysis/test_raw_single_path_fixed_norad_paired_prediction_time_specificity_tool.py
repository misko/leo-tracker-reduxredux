from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
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
    PredictedProbeCfo,
    SatelliteActivityProblem,
    SingleSatelliteHypothesis,
    decode_single_satellite,
)
from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]


def _tool() -> ModuleType:
    path = (
        Path(__file__).parents[2]
        / "tools/replay_raw_single_path_fixed_norad_paired_prediction_time_specificity.py"
    )
    spec = importlib.util.spec_from_file_location(
        "raw_single_path_fixed_norad_paired_prediction_time_specificity_tool",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _problem(cell_count: int = 20) -> SatelliteActivityProblem:
    probes = tuple(
        CfoProbe(
            probe_id=f"p{cell:03d}",
            time_s=cell * 0.1 + 0.025,
            cell_index=cell,
            missed_detection_cost=5.0,
        )
        for cell in range(cell_count)
    )
    observations = tuple(
        CfoCandidate(
            observation_id=f"o{cell:03d}",
            probe_id=probe.probe_id,
            exclusion_group_id=f"g{cell:03d}",
            cfo_hz=0.0,
            sigma_hz=1.0,
            clutter_cost=5.0,
            matched_base_cost=0.0,
            component_id="component",
        )
        for cell, probe in enumerate(probes)
    )
    return SatelliteActivityProblem(
        grid=ActivityGrid(
            start_s=0.0,
            cell_duration_s=0.1,
            cell_count=cell_count,
            minimum_active_cells=1,
        ),
        probes=probes,
        observations=observations,
        costs=AssociationCostModel(satellite_cost=0.0, episode_cost=0.0),
    )


def _identity_transform(tool: ModuleType) -> Any:
    receipt = {
        "algorithm_version": "identity-prediction-epoch-map-v1",
        "prediction_cell_by_observation_cell": list(range(20)),
        "observation_inventory_modified": False,
        "tle_prediction_epochs_modified": False,
    }
    digest = canonical_digest(receipt)
    return tool.paired._ArmTransform(
        arm_id="identity",
        role="identity",
        transform_digest=digest,
        plan=None,
        receipt={**receipt, "transform_digest": digest},
    )


def _persisted(problem: SatelliteActivityProblem) -> tuple[dict[str, Any], ...]:
    first_utc_ns = 1_000_000_000_123
    return tuple(
        {
            "probe_id": probe.probe_id,
            "estimate_utc_ns": first_utc_ns + round(probe.time_s * 1e9) + 12_345,
            "earliest_utc_ns": first_utc_ns + round(probe.time_s * 1e9),
            "latest_utc_ns": first_utc_ns + round(probe.time_s * 1e9) + 24_690,
            "source_prediction_time_s": probe.time_s,
            "source_prediction_utc_ns": first_utc_ns + round(probe.time_s * 1e9),
            "observation_cell_index": probe.cell_index,
            "within_activity_cell_offset_ns": 25_000_000,
        }
        for probe in problem.probes
    )


def test_raw_problem_round_trip_accepts_memory_tuples_and_persisted_json_lists() -> None:
    tool = _tool()
    problem = _problem()
    memory_payload = {"decision_problem": asdict(problem)}
    json_payload = json.loads(json.dumps(memory_payload))

    assert tool._problem_from_payload(memory_payload) == problem
    assert tool._problem_from_payload(json_payload) == problem


def test_identity_mapping_uses_source_nominal_epoch_not_interpolated_timing_estimate() -> None:
    tool = _tool()
    problem = _problem()
    persisted = _persisted(problem)

    mapped, receipt = tool._prediction_mapping(
        transform=_identity_transform(tool),
        persisted_probe_utc=persisted,
        problem=problem,
    )

    assert tuple(mapped.values()) == tuple(probe.time_s for probe in problem.probes)
    for row, timing in zip(receipt["mapping"], persisted, strict=True):
        assert row["prediction_utc_ns"] == timing["source_prediction_utc_ns"]
        assert row["prediction_utc_ns"] != timing["estimate_utc_ns"]
        assert row["observation_utc_ns"] == timing["estimate_utc_ns"]


def test_recomputed_gate_delta_survives_a_huge_elided_objective_constant() -> None:
    tool = _tool()
    problem = _problem()
    transform = _identity_transform(tool)
    persisted = _persisted(problem)
    _mapped, mapping_receipt = tool._prediction_mapping(
        transform=transform,
        persisted_probe_utc=persisted,
        problem=problem,
    )
    evaluated = []
    for index, cfo_offset_hz in enumerate((0.0, 0.1)):
        hypothesis = SingleSatelliteHypothesis(
            hypothesis_id=f"state-{index}",
            object_name="STARLINK-TEST",
            catalog_number=66811,
            delay_s=0.0,
            cfo_offset_hz=cfo_offset_hz,
            delay_prior_cost=0.0,
            predictions=tuple(PredictedProbeCfo(probe.probe_id, 0.0) for probe in problem.probes),
        )
        decoded = decode_single_satellite(problem, hypothesis)
        state = tool.raw_replay._StateEvaluation(
            hypothesis=hypothesis,
            proposal=tool.raw_replay._OffsetMode(cfo_offset_hz, 20, 20),
            single_total_cost=decoded.objective.total_cost,
            single_delta_from_null=decoded.objective.delta_from_null,
            single_selected=decoded.selected,
            minimum_elevation_deg=10.0,
            maximum_elevation_deg=20.0,
        )
        evaluated.append((state, decoded))
    evaluated.sort(key=lambda item: tool.raw_replay._state_sort_key(item[0]))
    states = [tool._serialize_state(state=state, decoded=decoded) for state, decoded in evaluated]
    best_state, best = evaluated[0]
    huge = 1e300
    arm = {
        "arm_id": transform.arm_id,
        "role": transform.role,
        "transform_digest": transform.transform_digest,
        "transform": transform.receipt,
        "prediction_epoch_mapping": mapping_receipt,
        "finite_state_search": {
            "target_catalog_number": 66811,
            "delay_grid": [0.0],
            "modes_per_delay": 2,
            "expected_generated_state_count": 2,
            "generated_state_count": 2,
            "declared_delay_grid_exhausted": True,
            "every_delay_generated_declared_cfo_mode_count": True,
            "generated_data_proposed_cfo_mode_bank_exhausted": True,
            "state_bank_pruned": False,
            "finite_declared_search_exact": True,
            "all_generated_states_nonactivating": False,
            "state_bank_digest": canonical_digest(states),
            "states": states,
        },
        "decision": {
            "activation_witness_found": True,
            "selected_catalog_numbers": [66811],
            "best_hypothesis_id": best_state.hypothesis.hypothesis_id,
            "best_delay_s": 0.0,
            "best_cfo_offset_hz": best_state.hypothesis.cfo_offset_hz,
            "full_persisted_inventory_objective": {
                "null_cost": best.objective.null_cost + huge,
                "total_cost": best.objective.total_cost + huge,
                "delta_from_null": best.objective.delta_from_null,
                "modeled_null_cost": best.objective.null_cost,
                "modeled_total_cost": best.objective.total_cost,
                "decision_invariant_delta_from_null": best.objective.delta_from_null,
                "constant_elided_from_exact_decision_problem": huge,
            },
        },
    }

    objective, _mapping_digest, all_null = tool._recompute_arm(
        arm=arm,
        problem=problem,
        persisted=persisted,
        transform=transform,
        target_catalog_number=66811,
        delay_grid=(0.0,),
        modes_per_delay=2,
        elided_constant=huge,
    )

    assert objective["null_cost"] == objective["total_cost"]
    assert objective["delta_from_null"] == best.objective.delta_from_null
    assert objective["delta_from_null"] < 0.0
    assert all_null is False

    for mutation in ("prediction", "proposal", "mapping", "delay_coverage"):
        tampered = copy.deepcopy(arm)
        if mutation == "prediction":
            tampered["finite_state_search"]["states"][0]["hypothesis"]["predictions"][0][
                "cfo_hz"
            ] += 1.0
        elif mutation == "proposal":
            tampered["finite_state_search"]["states"][0]["proposal"]["cfo_offset_hz"] += 1.0
        elif mutation == "mapping":
            tampered["prediction_epoch_mapping"]["mapping"][0]["prediction_utc_ns"] += 1
        else:
            tampered["finite_state_search"]["states"][0]["hypothesis"]["delay_s"] = 0.1
        with pytest.raises(ValueError):
            tool._recompute_arm(
                arm=tampered,
                problem=problem,
                persisted=persisted,
                transform=transform,
                target_catalog_number=66811,
                delay_grid=(0.0,),
                modes_per_delay=2,
                elided_constant=huge,
            )


def test_permuted_prediction_times_propagate_sorted_and_restore_probe_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    problem = _problem()
    mapped = {
        probe.probe_id: float(len(problem.probes) - index) * 0.1
        for index, probe in enumerate(problem.probes)
    }
    expected = np.asarray([mapped[probe.probe_id] for probe in problem.probes])

    def ordered_curve(**keywords: Any) -> tuple[Any, Any, Any]:
        scheduled = np.asarray(keywords["scheduled_times_s"], dtype=np.float64)
        assert np.all(np.diff(scheduled) > 0.0)
        return scheduled, scheduled + 100.0, scheduled + 200.0

    monkeypatch.setattr(tool, "_doppler_curve", ordered_curve)
    source = SimpleNamespace(
        inventory=SimpleNamespace(problem=problem),
        dataset={
            "timing_binding": {"first_estimate_utc_ns": 1_000_000_000},
            "frequency_binding": {"sky_frequency_hz": 10e9},
        },
        catalogue=SimpleNamespace(),
        catalogue_index=0,
        observer=SimpleNamespace(),
    )
    curve, elevation = tool._propagate_mapped_epochs(
        source=source,
        prediction_time_s_by_probe_id=mapped,
        delay_s=0.0,
    )

    np.testing.assert_array_equal(curve, expected)
    np.testing.assert_array_equal(elevation, expected + 100.0)


def _exact_source_contract(tool: ModuleType) -> dict[str, Any]:
    row = {
        "rank": 1,
        "catalog_number": 10,
        "generated_state_count": 2,
        "best_single_delta_from_null": -2.0,
        "best_single_selected": True,
        "best_hypothesis_id": "source-state",
    }
    partition = {
        "schema": tool.bounded.IDENTITY_PARTITION_SCHEMA,
        "algorithm": tool.bounded.IDENTITY_PARTITION_ALGORITHM,
        "catalogue_name_prefix": "STARLINK",
        "catalogue_object_count": 1,
        "tle_digest": "sha256:" + "a" * 64,
        "eligibility_semantics": "named-and-full-window-visible-over-declared-delay-grid",
        "partition_exhausted": True,
        "partition_pruned": False,
        "named_catalog_count": 1,
        "eligible_catalog_count": 1,
        "named_ineligible_catalog_count": 0,
        "named_catalog_numbers": [10],
        "eligible_catalog_numbers": [10],
        "named_ineligible_catalog_numbers": [],
        "named_catalog_numbers_digest": canonical_digest([10]),
        "eligible_catalog_numbers_digest": canonical_digest([10]),
        "named_ineligible_catalog_numbers_digest": canonical_digest([]),
    }
    partition["partition_content_digest"] = canonical_digest(partition)
    return {
        "catalogue_search_performed": True,
        "finite_universe_catalogue_search_exact": True,
        "null_vs_any_activation_solved": True,
        "conditional_on_raw_glrt64_inventory": True,
        "conditional_on_full_window_visibility_screen": True,
        "conditional_on_data_proposed_cfo_modes": True,
        "catalogue_search_avoided_by_global_null_certificate": False,
        "conditional_on_explicit_catalog_shortlist": False,
        "conditional_on_catalogue_screen_shortlist": False,
        "conditional_on_pruned_joint_shortlist": False,
        "conditional_on_pruned_nuisance_state_bank": False,
        "unrestricted_global_exactness_claimed": False,
        "raw_inventory": {
            "declared_post_acquisition_inventory_complete": True,
            "truncated_candidate_count": 0,
        },
        "catalogue_search": {
            "fine_stage": {
                "catalogue_rows_exhausted": True,
                "declared_discrete_delay_grid_exhausted": True,
                "generated_data_proposed_cfo_mode_bank_exhausted": True,
                "eligible_catalog_count": 1,
                "scored_catalog_count": 1,
                "omitted_eligible_catalog_count": 0,
                "delay_grid": [0.0],
                "modes_per_delay": 2,
                "generated_state_count": 2,
                "generated_state_count_upper_bound": 2,
                "negative_catalogue_minimum_count": 1,
                "all_catalogue_minima_nonactivating": False,
                "ranking": [row],
            },
            "finite_universe": {
                "eligible_catalogue_count": 1,
                "catalogue_identity_scope": "named and full-window-visible",
                "identity_partition_content_digest": partition["partition_content_digest"],
            },
            "separability_proof": {
                "single_satellite_minima_exact_over_generated_states": True,
                "joint_delta_is_sum_of_selected_satellite_reduced_contributions": True,
                "arbitrary_subsets_of_finite_catalogue_universe_covered": True,
                "satellite_and_episode_costs_nonnegative": True,
                "exclusion_group_assignment_capacity": 1,
            },
        },
        "catalogue_identity_partition": partition,
        "decision": {
            "result_kind": "activation_witness",
            "selected_catalog_numbers": [10],
            "full_persisted_inventory_objective": {"delta_from_null": -2.0},
        },
    }


def test_exact_source_contract_rejects_pruning_and_partition_tampering() -> None:
    tool = _tool()
    source = _exact_source_contract(tool)
    assert tool._validate_exact_source_contract(source)[0]["catalog_number"] == 10

    pruned = copy.deepcopy(source)
    pruned["conditional_on_pruned_nuisance_state_bank"] = True
    with pytest.raises(ValueError, match="exactness flags"):
        tool._validate_exact_source_contract(pruned)

    partition_tamper = copy.deepcopy(source)
    partition_tamper["catalogue_identity_partition"]["eligible_catalog_numbers"] = []
    with pytest.raises(ValueError, match="partition"):
        tool._validate_exact_source_contract(partition_tamper)


def test_load_source_calls_exact_contract_before_other_source_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    source_path = tmp_path / "source.json"
    source_path.write_text(
        json.dumps(
            {
                "schema": tool.SOURCE_SCHEMA,
                "algorithm": tool.SOURCE_ALGORITHM,
                "finite_universe_catalogue_search_exact": True,
            }
        ),
        encoding="utf-8",
    )
    digest = "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        tool,
        "_validate_exact_source_contract",
        lambda _source: (_ for _ in ()).throw(ValueError("exact-contract-sentinel")),
    )

    with pytest.raises(ValueError, match="exact-contract-sentinel"):
        tool._load_source(
            source_path=source_path,
            expected_source_digest=digest,
            target_catalog_number=10,
        )


def test_strict_reader_rejects_duplicate_keys_and_nonfinite_numbers(tmp_path: Path) -> None:
    tool = _tool()
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        tool._read_json(duplicate)
    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"value":NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="non-finite"):
        tool._read_json(nonfinite)


def test_seventy_five_cell_source_fails_closed_in_frozen_permutation_builder() -> None:
    tool = _tool()
    grid = ActivityGrid(
        start_s=52.5,
        cell_duration_s=0.1,
        cell_count=75,
        minimum_active_cells=5,
    )

    with pytest.raises(ValueError, match="directed-displacement diversity is impossible"):
        tool.paired._freeze_arm_transforms(
            problem=SimpleNamespace(grid=grid),
            selection_context_digest="sha256:" + "a" * 64,
            control_indices=(0, 1, 2, 3),
            maximum_delay_support_s=2.0,
        )
