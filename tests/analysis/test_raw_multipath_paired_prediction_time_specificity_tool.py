from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from leo.analysis.research.multipath_satellite_activity import (  # type: ignore[import-untyped]
    MultipathSatelliteActivityProblem,
    ReceiverPathActivityEvidence,
)
from leo.analysis.research.satellite_activity import (  # type: ignore[import-untyped]
    ActivityGrid,
    AssociationCostModel,
    CfoProbe,
)
from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]


def _tool() -> ModuleType:
    path = (
        Path(__file__).parents[2]
        / "tools/replay_raw_multipath_paired_prediction_time_specificity.py"
    )
    spec = importlib.util.spec_from_file_location(
        "raw_multipath_paired_prediction_time_specificity_tool",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _arm(
    *,
    tool: ModuleType,
    arm_id: str,
    role: str,
    delta: float,
    exact: bool = True,
    transform_digest: str | None = None,
    activation: bool | None = None,
    path_offset_exhausted: bool | None = None,
    transform: Any | None = None,
) -> dict[str, Any]:
    problem = _problem()
    if transform is None:
        control_index = 0 if arm_id == "identity" else int(arm_id.removeprefix("control-"))
        frozen = tool._freeze_arm_transforms(
            problem=problem,
            selection_context_digest="sha256:" + "6" * 64,
            control_indices=(control_index,),
            maximum_delay_support_s=0.0,
        )
        transform = frozen[0] if arm_id == "identity" else frozen[1]
    path_receipts = []
    contexts = _contexts(tool, problem)
    for path, context in zip(problem.paths, contexts, strict=True):
        _mapped, receipt = tool._prediction_epoch_mapping(
            transform=transform,
            context=context,
            path=path,
            grid_start_utc_ns=100_000_000_000,
        )
        path_receipts.append(receipt)
    single_witness = delta < 0.0
    all_single_states_nonactivating = not single_witness
    path_search_exhausted = exact if path_offset_exhausted is None else path_offset_exhausted
    return {
        "arm_id": arm_id,
        "role": role,
        "transform_digest": transform_digest or transform.transform_digest,
        "transform": transform.receipt,
        "common_digests": {},
        "prediction_epoch_mapping": {
            "same_mapping_all_catalogues_delays_and_cfo_modes": True,
            "combined_mapping_digest": canonical_digest(path_receipts),
            "paths": path_receipts,
        },
        "search": {
            "finite_declared_search_exact": exact,
            "per_catalog_path_offset_search_exhausted": path_search_exhausted,
            "single_fixed_state_activation_witness_found": single_witness,
            "all_generated_single_fixed_states_nonactivating": (all_single_states_nonactivating),
            "null_vs_any_declared_state_universe_solved": (
                single_witness or (path_search_exhausted and all_single_states_nonactivating)
            ),
        },
        "decision": {
            "activation_witness_found": delta < 0.0 if activation is None else activation,
            "full_persisted_inventory_objective": {
                "null_cost": 100.0,
                "total_cost": 100.0 + delta,
                "delta_from_null": delta,
            },
        },
    }


def _common(
    tool: ModuleType,
    arms: tuple[dict[str, Any], ...],
    *,
    minimum_advantage_cost: float,
    calibrated: bool,
    preregistered: bool,
) -> dict[str, Any]:
    raw_paths = []
    for path_receipt in arms[0]["prediction_epoch_mapping"]["paths"]:
        raw_paths.append(
            {
                "path_id": path_receipt["path_id"],
                "persisted_probe_utc": [
                    {
                        "probe_id": row["probe_id"],
                        "estimate_utc_ns": row["observation_utc_ns"],
                        "cell_index": row["observation_cell_index"],
                    }
                    for row in path_receipt["mapping"]
                ],
            }
        )
    documents = {
        "raw_problem": {"paths": raw_paths, "test_fixture": True},
        "objective": {"test_fixture": True},
        "search_universe": {
            "test_fixture": True,
            "configuration": {"delay_min_s": 0.0, "delay_max_s": 0.0},
        },
        "producer": {"test_fixture": True},
    }
    digests = {f"{key}_digest": canonical_digest(value) for key, value in documents.items()}
    control_indices = [int(arm["arm_id"].removeprefix("control-")) for arm in arms[1:]]
    problem = _problem()
    selection_context = {
        "schema": tool.FAMILY_PLAN_SCHEMA,
        "algorithm": tool.ALGORITHM,
        "family_label": "test-family",
        "session_id": "session-test",
        "recording_manifest_digest": "sha256:" + "c" * 64,
        **digests,
        "window": {
            "start_s": problem.grid.start_s,
            "cell_duration_s": problem.grid.cell_duration_s,
            "cell_count": problem.grid.cell_count,
            "minimum_active_cells": problem.grid.minimum_active_cells,
        },
        "identity_arm_id": "identity",
        "control_indices": control_indices,
        "minimum_advantage_cost": minimum_advantage_cost,
        "comparison": "identity improvement strictly greater than strongest control",
        "require_every_control_to_be_a_certified_null": True,
        "all_declared_arms_must_be_emitted": True,
        "external_preregistration_verified": preregistered,
        "advantage_threshold_calibrated": calibrated,
    }
    transforms = tool._freeze_arm_transforms(
        problem=problem,
        selection_context_digest=canonical_digest(selection_context),
        control_indices=tuple(control_indices),
        maximum_delay_support_s=0.0,
    )
    contexts = _contexts(tool, problem)
    for arm, transform in zip(arms, transforms, strict=True):
        arm["transform_digest"] = transform.transform_digest
        arm["transform"] = transform.receipt
        path_receipts = []
        for path, context in zip(problem.paths, contexts, strict=True):
            _mapped, receipt = tool._prediction_epoch_mapping(
                transform=transform,
                context=context,
                path=path,
                grid_start_utc_ns=100_000_000_000,
            )
            path_receipts.append(receipt)
        arm["prediction_epoch_mapping"] = {
            "same_mapping_all_catalogues_delays_and_cfo_modes": True,
            "combined_mapping_digest": canonical_digest(path_receipts),
            "paths": path_receipts,
        }
    family_plan = {
        **selection_context,
        "arms": [
            {
                "arm_id": arm["arm_id"],
                "role": arm["role"],
                "transform_digest": arm["transform_digest"],
                "transform": copy.deepcopy(arm["transform"]),
            }
            for arm in arms
        ],
        "family_frozen_before_arm_scoring": True,
        "all_control_plans_built_before_arm_scoring": True,
    }
    digests["family_plan_digest"] = canonical_digest(family_plan)
    common = {"digests": digests, **documents, "family_plan": family_plan}
    for arm in arms:
        arm["common_digests"] = digests
    return common


def _adjudicate(
    tool: ModuleType,
    arms: tuple[dict[str, Any], ...],
    *,
    minimum_advantage_cost: float = 0.0,
    calibrated: bool = True,
    preregistered: bool = True,
) -> dict[str, Any]:
    common = _common(
        tool,
        arms,
        minimum_advantage_cost=minimum_advantage_cost,
        calibrated=calibrated,
        preregistered=preregistered,
    )
    return tool.adjudicate_paired_arms(
        arms=arms,
        common=common,
        minimum_advantage_cost=minimum_advantage_cost,
        advantage_threshold_calibrated=calibrated,
        external_preregistration_verified=preregistered,
    )


def test_adjudicator_uses_the_strongest_control_and_rejects_any_activation() -> None:
    tool = _tool()
    arms = (
        _arm(tool=tool, arm_id="identity", role="identity", delta=-10.0),
        _arm(
            tool=tool,
            arm_id="control-000000",
            role="block_permutation_control",
            delta=-4.0,
            exact=False,
        ),
        _arm(
            tool=tool,
            arm_id="control-000001",
            role="block_permutation_control",
            delta=-6.0,
            exact=False,
        ),
    )

    result = _adjudicate(tool, arms, minimum_advantage_cost=3.0)

    assert result["disposition"] == tool.DERANGED_ACTIVATION_WITNESS
    assert result["strongest_control_arm_id"] == "control-000001"
    assert result["strongest_control_improvement_from_null"] == 6.0
    assert result["identity_advantage_over_strongest_control_cost"] == 4.0
    assert result["relative_advantage_passed"] is True
    assert result["paired_gate_passed"] is False
    assert all(item["null_vs_any_declared_state_universe_solved"] for item in result["controls"])
    assert result["activating_control_arm_ids"] == [
        "control-000000",
        "control-000001",
    ]
    assert result["specificity_claimed"] is False


def test_adjudicator_fail_closed_dispositions() -> None:
    tool = _tool()
    identity_null = _arm(tool=tool, arm_id="identity", role="identity", delta=0.0)
    exact_control_null = _arm(
        tool=tool,
        arm_id="control-000000",
        role="block_permutation_control",
        delta=0.0,
    )
    incomplete_control_null = _arm(
        tool=tool,
        arm_id="control-000000",
        role="block_permutation_control",
        delta=0.0,
        exact=False,
    )
    pruned_but_certified_control_null = _arm(
        tool=tool,
        arm_id="control-000000",
        role="block_permutation_control",
        delta=0.0,
        exact=False,
        path_offset_exhausted=True,
    )
    identity_active = _arm(tool=tool, arm_id="identity", role="identity", delta=-5.0)

    assert (
        _adjudicate(tool, (identity_null, exact_control_null))["disposition"]
        == tool.IDENTITY_NONACTIVATION
    )
    assert (
        _adjudicate(tool, (identity_active, incomplete_control_null))["disposition"]
        == tool.CONTROL_NULL_NOT_CERTIFIED
    )
    pruned_result = _adjudicate(tool, (identity_active, pruned_but_certified_control_null))
    assert pruned_result["disposition"] == tool.BOUNDED_PREDICTION_TIME_GATE_PASS
    assert pruned_result["all_declared_control_nulls_certified"] is True
    assert pruned_result["controls"][0]["finite_declared_search_exact"] is False
    assert (
        _adjudicate(
            tool,
            (identity_active, exact_control_null),
            minimum_advantage_cost=5.0,
        )["disposition"]
        == tool.ADVANTAGE_BELOW_FROZEN_THRESHOLD
    )
    assert (
        _adjudicate(
            tool,
            (identity_active, exact_control_null),
            minimum_advantage_cost=4.0,
            calibrated=False,
        )["disposition"]
        == tool.ADVANTAGE_THRESHOLD_NOT_CALIBRATED
    )
    selection_result = _adjudicate(
        tool,
        (identity_active, exact_control_null),
        minimum_advantage_cost=4.0,
        preregistered=False,
    )
    assert selection_result["disposition"] == tool.SELECTION_CAUSALITY_NOT_VERIFIED
    assert selection_result["comparable"] is True
    assert (
        _adjudicate(
            tool,
            (identity_active, exact_control_null),
            minimum_advantage_cost=4.0,
        )["disposition"]
        == tool.BOUNDED_PREDICTION_TIME_GATE_PASS
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "arm_set",
        "common_digest",
        "duplicate_transform",
        "objective",
        "activation",
        "null_certificate",
        "unknown_role",
        "missing_transform",
        "missing_mapping",
        "transform_digest_tamper",
        "mapping_digest_tamper",
        "common_content_tamper",
        "sub_tolerance_delta",
    ),
)
def test_adjudicator_marks_provenance_or_objective_mismatch_not_comparable(
    mutation: str,
) -> None:
    tool = _tool()
    arms = [
        _arm(tool=tool, arm_id="identity", role="identity", delta=-5.0),
        _arm(
            tool=tool,
            arm_id="control-000000",
            role="block_permutation_control",
            delta=0.0,
        ),
    ]
    common = _common(
        tool,
        tuple(arms),
        minimum_advantage_cost=0.0,
        calibrated=True,
        preregistered=True,
    )
    if mutation == "arm_set":
        common["family_plan"]["arms"].append(
            {
                "arm_id": "control-000001",
                "role": "block_permutation_control",
                "transform_digest": "sha256:" + "4" * 64,
                "transform": {},
            }
        )
        common["family_plan"]["control_indices"].append(1)
        common["digests"]["family_plan_digest"] = canonical_digest(common["family_plan"])
    elif mutation == "common_digest":
        arms[1]["common_digests"] = {"raw_problem_digest": "sha256:" + "4" * 64}
    elif mutation == "duplicate_transform":
        arms[1]["transform_digest"] = arms[0]["transform_digest"]
    elif mutation == "objective":
        arms[1]["decision"]["full_persisted_inventory_objective"]["total_cost"] = 99.0
    elif mutation == "activation":
        arms[1]["decision"]["activation_witness_found"] = True
    elif mutation == "null_certificate":
        arms[1]["search"]["null_vs_any_declared_state_universe_solved"] = False
    elif mutation == "unknown_role":
        arms[1]["role"] = "unknown-control"
    elif mutation == "missing_transform":
        del arms[1]["transform"]
    elif mutation == "missing_mapping":
        del arms[1]["prediction_epoch_mapping"]
    elif mutation == "transform_digest_tamper":
        arms[1]["transform"]["plan_digest"] = "sha256:" + "9" * 64
    elif mutation == "mapping_digest_tamper":
        arms[1]["prediction_epoch_mapping"]["paths"][0]["mapping_digest"] = "sha256:" + "8" * 64
    elif mutation == "common_content_tamper":
        common["objective"]["tampered"] = True
    else:
        objective = arms[1]["decision"]["full_persisted_inventory_objective"]
        objective["null_cost"] = 100.0
        objective["total_cost"] = 100.0
        objective["delta_from_null"] = -5e-10

    result = tool.adjudicate_paired_arms(
        arms=tuple(arms),
        common=common,
        minimum_advantage_cost=0.0,
        advantage_threshold_calibrated=True,
        external_preregistration_verified=True,
    )

    assert result["disposition"] == tool.NOT_COMPARABLE
    assert result["comparable"] is False
    assert result["paired_gate_passed"] is False
    assert result["reasons"]


def _problem() -> MultipathSatelliteActivityProblem:
    grid = ActivityGrid(
        start_s=100.0,
        cell_duration_s=0.1,
        cell_count=100,
        minimum_active_cells=5,
    )
    paths = []
    for path_id in ("path-a", "path-b"):
        probes = tuple(
            CfoProbe(
                probe_id=f"{path_id}-p{cell}",
                time_s=100.0 + cell * 0.1 + 0.025,
                cell_index=cell,
                missed_detection_cost=1.0,
            )
            for cell in range(100)
        )
        paths.append(ReceiverPathActivityEvidence(path_id, probes, ()))
    return MultipathSatelliteActivityProblem(
        grid=grid,
        paths=tuple(paths),
        costs=AssociationCostModel(satellite_cost=1.0, episode_cost=1.0),
    )


def _contexts(tool: ModuleType, problem: MultipathSatelliteActivityProblem) -> tuple[Any, ...]:
    contexts = []
    for path in problem.paths:
        probe_utc = tuple(
            tool.multipath._ProbeUtc(
                probe_id=probe.probe_id,
                estimate_utc_ns=round(probe.time_s * 1e9),
                earliest_utc_ns=round(probe.time_s * 1e9),
                latest_utc_ns=round(probe.time_s * 1e9),
                cell_index=probe.cell_index,
                usable=True,
                retained_candidate_count=0,
            )
            for probe in path.probes
        )
        inventory = SimpleNamespace(
            observations=(),
            source_candidate_count=0,
            returned_candidate_count=0,
            saturated_probe_count=0,
            elided_clutter_constant=0.0,
            scan_digest="sha256:" + ("a" if path.path_id == "path-a" else "b") * 64,
            scan_path=Path(f"/{path.path_id}.json"),
        )
        contexts.append(
            SimpleNamespace(
                path_id=path.path_id,
                dataset={
                    "capture": {
                        "session_id": "session-test",
                        "recording_manifest_digest": "sha256:" + "c" * 64,
                    },
                    "frequency_binding": {"sky_frequency_hz": 10e9},
                    "timing_binding": {"first_estimate_utc_ns": 100_000_000_000},
                },
                dataset_path=Path(f"/{path.path_id}-duration.json"),
                dataset_digest="sha256:" + ("d" if path.path_id == "path-a" else "e") * 64,
                scan_content_digest="sha256:" + ("f" if path.path_id == "path-a" else "0") * 64,
                probe_utc=probe_utc,
                inventory=inventory,
            )
        )
    return tuple(contexts)


def test_identity_and_general_permutation_preserve_raw_probe_offsets() -> None:
    tool = _tool()
    problem = _problem()
    contexts = _contexts(tool, problem)
    transforms = tool._freeze_arm_transforms(
        problem=problem,
        selection_context_digest="sha256:" + "9" * 64,
        control_indices=(0, 1),
        maximum_delay_support_s=2.0,
    )

    assert [item.arm_id for item in transforms] == [
        "identity",
        "control-000000",
        "control-000001",
    ]
    assert all(
        not item.plan.diagnostics.mapping_is_affine
        for item in transforms[1:]
        if item.plan is not None
    )
    assert len({item.transform_digest for item in transforms}) == 3

    path = problem.paths[0]
    identity, identity_receipt = tool._prediction_epoch_mapping(
        transform=transforms[0],
        context=contexts[0],
        path=path,
        grid_start_utc_ns=100_000_000_000,
    )
    control, control_receipt = tool._prediction_epoch_mapping(
        transform=transforms[1],
        context=contexts[0],
        path=path,
        grid_start_utc_ns=100_000_000_000,
    )
    assert tuple(identity.values()) == tuple(item.estimate_utc_ns for item in contexts[0].probe_utc)
    assert tuple(control.values()) != tuple(identity.values())
    assert {value % tool.UTC_CELL_NS for value in control.values()} == {25_000_000}
    assert identity_receipt["mapping_digest"] != control_receipt["mapping_digest"]

    with pytest.raises(ValueError, match="unique"):
        tool._freeze_arm_transforms(
            problem=problem,
            selection_context_digest="sha256:" + "9" * 64,
            control_indices=(0, 0),
            maximum_delay_support_s=2.0,
        )


def test_permuted_epochs_propagate_in_time_order_and_restore_probe_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    problem = _problem()
    contexts = _contexts(tool, problem)
    transform = tool._freeze_arm_transforms(
        problem=problem,
        selection_context_digest="sha256:" + "7" * 64,
        control_indices=(0,),
        maximum_delay_support_s=0.0,
    )[1]
    path = problem.paths[0]
    mapped, _receipt = tool._prediction_epoch_mapping(
        transform=transform,
        context=contexts[0],
        path=path,
        grid_start_utc_ns=100_000_000_000,
    )
    expected_in_probe_order = np.asarray(
        [(mapped[probe.probe_id] - 100_000_000_000) / 1e9 for probe in path.probes],
        dtype=np.float64,
    )
    assert np.any(np.diff(expected_in_probe_order) < 0.0)

    def ordered_curve(**kwargs: Any) -> tuple[Any, Any, Any]:
        scheduled = np.asarray(kwargs["scheduled_times_s"], dtype=np.float64)
        assert np.all(np.diff(scheduled) > 0.0)
        return scheduled, scheduled + 1_000.0, scheduled + 2_000.0

    monkeypatch.setattr(tool, "_doppler_curve", ordered_curve)
    curve, elevation, altitude = tool._propagate_mapped_probe_epochs(
        catalogue=SimpleNamespace(),
        catalogue_index=0,
        context=contexts[0],
        path=path,
        mapped_prediction_utc_ns_by_probe_id=mapped,
        delay_s=0.0,
        observer=ObserverSiteV1(
            latitude_deg=0.0,
            longitude_deg=0.0,
            altitude_m=0.0,
            label="test-site",
        ),
    )

    np.testing.assert_array_equal(curve, expected_in_probe_order)
    np.testing.assert_array_equal(elevation, expected_in_probe_order + 1_000.0)
    np.testing.assert_array_equal(altitude, expected_in_probe_order + 2_000.0)


@pytest.mark.parametrize(
    ("delay_max_s", "finite_search_exact", "elided_constant"),
    ((0.0, True, 0.0), (0.1, False, 1e12)),
)
def test_identity_and_control_use_one_generic_arm_evaluator(
    monkeypatch: pytest.MonkeyPatch,
    delay_max_s: float,
    finite_search_exact: bool,
    elided_constant: float,
) -> None:
    tool = _tool()
    problem = _problem()
    contexts = _contexts(tool, problem)
    for context in contexts:
        context.inventory.elided_clutter_constant = elided_constant
    transforms = tool._freeze_arm_transforms(
        problem=problem,
        selection_context_digest="sha256:" + "8" * 64,
        control_indices=(0,),
        maximum_delay_support_s=0.0,
    )

    def flat_curve(**kwargs: Any) -> tuple[Any, Any, Any]:
        assert all(
            earlier < later
            for earlier, later in zip(
                kwargs["scheduled_times_s"],
                kwargs["scheduled_times_s"][1:],
                strict=False,
            )
        )
        count = len(kwargs["scheduled_times_s"])
        return (
            np.zeros(count, dtype=np.float64),
            np.full(count, 45.0, dtype=np.float64),
            np.full(count, 550_000.0, dtype=np.float64),
        )

    monkeypatch.setattr(tool, "_doppler_curve", flat_curve)

    class Calibration:
        @staticmethod
        def is_positive(_margin: float) -> bool:
            return False

        @staticmethod
        def match_supported(_rank: int) -> bool:
            return False

    class Catalogue(SimpleNamespace):
        def __len__(self) -> int:
            return len(self.satellite_numbers)

    catalogue = Catalogue(
        satellite_numbers=(10, 20),
        names=("STARLINK-10", "STARLINK-20"),
    )
    config = tool.multipath.MultipathReplayConfig(
        delay_min_s=0.0,
        delay_max_s=delay_max_s,
        delay_step_s=0.1,
        modes_per_delay=1,
        retained_states_per_catalog=1,
        maximum_state_combinations=1,
        maximum_path_offset_combinations_per_delay=1,
    )
    common = {
        "raw_problem_digest": "sha256:" + "1" * 64,
        "objective_digest": "sha256:" + "2" * 64,
        "search_universe_digest": "sha256:" + "3" * 64,
        "producer_digest": "sha256:" + "4" * 64,
        "family_plan_digest": "sha256:" + "5" * 64,
    }
    evaluations = tuple(
        tool._evaluate_arm(
            transform=transform,
            catalogue=catalogue,
            catalog_indices=(0, 1),
            contexts=contexts,
            problem=problem,
            calibration=Calibration(),
            observer=ObserverSiteV1(
                latitude_deg=0.0,
                longitude_deg=0.0,
                altitude_m=0.0,
                label="test-site",
            ),
            config=config,
            common_digests=common,
            grid_start_utc_ns=100_000_000_000,
        ).document
        for transform in transforms
    )

    assert [item["role"] for item in evaluations] == [
        "identity",
        "block_permutation_control",
    ]
    assert all(item["common_digests"] == common for item in evaluations)
    assert all(
        item["search"]["finite_declared_search_exact"] is finite_search_exact
        for item in evaluations
    )
    assert all(
        item["search"]["per_catalog_state_banks_pruned"] is (not finite_search_exact)
        for item in evaluations
    )
    assert all(item["search"]["null_vs_any_declared_state_universe_solved"] for item in evaluations)
    assert all(item["decision"]["activation_witness_found"] is False for item in evaluations)
    assert {
        item["decision"]["full_persisted_inventory_objective"]["delta_from_null"]
        for item in evaluations
    } == {0.0}
    assert all(tool._arm_objective(item)["delta_from_null"] == 0.0 for item in evaluations)
    if elided_constant:
        assert all(
            item["decision"]["full_persisted_inventory_objective"]["null_cost"] >= 2e12
            for item in evaluations
        )
    assert (
        evaluations[0]["prediction_epoch_mapping"]["combined_mapping_digest"]
        != evaluations[1]["prediction_epoch_mapping"]["combined_mapping_digest"]
    )
    json.dumps(evaluations, allow_nan=False)


def test_atomic_producer_loads_once_freezes_all_arms_and_emits_common_digests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    problem = _problem()
    contexts = _contexts(tool, problem)
    calibration_path = tmp_path / "calibration.json"
    tle_path = tmp_path / "catalog.tle"
    calibration_document = {"schema": tool.raw_replay.CALIBRATION_SCHEMA_V3}
    calibration_path.write_text(json.dumps(calibration_document), encoding="utf-8")
    tle_path.write_text("test TLE bytes", encoding="utf-8")
    calibration = SimpleNamespace(weak_match_is_dominated_by_miss=lambda: True)

    class Catalogue(SimpleNamespace):
        def __len__(self) -> int:
            return len(self.satellite_numbers)

    catalogue = Catalogue(
        satellite_numbers=(10, 20),
        names=("STARLINK-10", "STARLINK-20"),
    )

    monkeypatch.setattr(tool.raw_replay, "_validate_calibration_grouping", lambda *_args: None)
    monkeypatch.setattr(tool.raw_replay, "_score", lambda _document: calibration)
    monkeypatch.setattr(tool, "parse_element_sets", lambda _text: catalogue)
    monkeypatch.setattr(
        tool.multipath,
        "_unique_satellite_index",
        lambda _catalogue, catalog_number: 0 if catalog_number == 10 else 1,
    )
    monkeypatch.setattr(tool, "_validate_window_coverage", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tool.multipath, "_multipath_problem", lambda *_args, **_kwargs: problem)
    monkeypatch.setattr(
        tool,
        "_implementation_file_digests",
        lambda: {"paired-producer": "sha256:" + "7" * 64},
    )
    monkeypatch.setattr(
        tool.multipath,
        "_runtime_versions",
        lambda: {"python": "test", "numpy": "test", "sgp4": "test"},
    )
    load_count = 0

    def fake_load(**_kwargs: Any) -> tuple[Any, ...]:
        nonlocal load_count
        load_count += 1
        return contexts

    monkeypatch.setattr(tool.multipath, "_load_path_contexts", fake_load)
    events: list[str] = []
    real_builder = tool.build_activity_block_permutation

    def recording_builder(*args: Any, **kwargs: Any) -> Any:
        events.append(f"build-{kwargs['control_index']}")
        return real_builder(*args, **kwargs)

    monkeypatch.setattr(tool, "build_activity_block_permutation", recording_builder)

    def fake_evaluate(**kwargs: Any) -> Any:
        transform = kwargs["transform"]
        events.append(f"evaluate-{transform.arm_id}")
        assert kwargs["contexts"] is contexts
        assert kwargs["problem"] is problem
        delta_by_id = {
            "identity": -10.0,
            "control-000000": -4.0,
            "control-000001": 0.0,
        }
        document = _arm(
            tool=tool,
            arm_id=transform.arm_id,
            role=transform.role,
            delta=delta_by_id[transform.arm_id],
            exact=transform.role == "identity" or delta_by_id[transform.arm_id] == 0.0,
            transform_digest=transform.transform_digest,
            transform=transform,
        )
        document["common_digests"] = kwargs["common_digests"]
        return tool._ArmEvaluation(transform, document)

    monkeypatch.setattr(tool, "_evaluate_arm", fake_evaluate)
    config = tool.multipath.MultipathReplayConfig(
        delay_min_s=0.0,
        delay_max_s=0.0,
        delay_step_s=0.1,
        modes_per_delay=1,
        retained_states_per_catalog=1,
        maximum_state_combinations=1,
        maximum_path_offset_combinations_per_delay=1,
    )

    result = tool.replay_raw_multipath_paired_prediction_time(
        dataset_paths=(tmp_path / "a.json", tmp_path / "b.json"),
        expected_dataset_digests=("sha256:" + "d" * 64, "sha256:" + "e" * 64),
        calibration_document=calibration_document,
        calibration_path=calibration_path,
        expected_calibration_digest=tool._file_digest(calibration_path),
        tle_path=tle_path,
        expected_tle_digest=tool._file_digest(tle_path),
        catalog_numbers=(10, 20),
        start_utc_ns=100_000_000_000,
        end_utc_ns=110_000_000_000,
        observer=ObserverSiteV1(
            latitude_deg=0.0,
            longitude_deg=0.0,
            altitude_m=0.0,
            label="test-site",
        ),
        config=config,
        control_indices=(1, 0),
        family_label="frozen-test-family",
    )

    assert load_count == 1
    assert events[:2] == ["build-0", "build-1"]
    assert events[2:] == [
        "evaluate-identity",
        "evaluate-control-000000",
        "evaluate-control-000001",
    ]
    assert result["all_arms_share_one_loaded_raw_problem"] is True
    assert result["only_prediction_epoch_mapping_varies_between_arms"] is True
    assert result["all_declared_arms_emitted"] is True
    assert result["common"]["family_plan"]["family_frozen_before_arm_scoring"] is True
    assert "selection_context_digest" not in result["common"]["family_plan"]
    assert result["common"]["family_plan"]["control_indices"] == [0, 1]
    control_plans = result["common"]["family_plan"]["arms"][1:]
    assert all(not item["transform"]["diagnostics"]["mapping_is_affine"] for item in control_plans)
    assert all(item["transform"]["forbidden_forward_lag_blocks"] == [] for item in control_plans)
    digests = result["common"]["digests"]
    assert canonical_digest(result["common"]["raw_problem"]) == digests["raw_problem_digest"]
    assert canonical_digest(result["common"]["objective"]) == digests["objective_digest"]
    assert (
        canonical_digest(result["common"]["search_universe"]) == digests["search_universe_digest"]
    )
    assert canonical_digest(result["common"]["producer"]) == digests["producer_digest"]
    assert canonical_digest(result["common"]["family_plan"]) == digests["family_plan_digest"]
    assert all(item["common_digests"] == digests for item in result["arms"])
    assert result["adjudication"]["disposition"] == tool.DERANGED_ACTIVATION_WITNESS
    assert result["adjudication"]["strongest_control_arm_id"] == "control-000000"
    assert result["adjudication"]["identity_advantage_over_strongest_control_cost"] == 6.0
    assert result["specificity_claimed"] is False
    assert result["payload_decoded"] is False
    json.dumps(result, allow_nan=False)
