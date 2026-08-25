#!/usr/bin/env python3
"""Atomically compare correct and frozen-control TLE prediction epochs.

This Research-only producer loads one two-to-four-path raw PilotScanV3
inventory once, freezes one explicit catalogue shortlist and every declared
prediction-time arm, and evaluates every arm through the same nuisance-state
builder and fixed-state joint decoder.  The identity arm leaves prediction
epochs unchanged.  Each control arm applies one deterministic, session-wide
half-second block permutation shared by all paths, catalogue objects, delays,
and CFO-offset proposals.

The result is conditional on the supplied catalogue shortlist, retained raw
candidate inventory, discrete delay grid, data-proposed CFO modes, and bounded
state caps.  It is a prediction-time diagnostic, not a signal-absence control,
false-positive-rate estimate, payload decode, spacecraft identification, or
tracking result.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from leo.analysis.research.activity_block_permutation import (  # type: ignore[import-untyped]
    ActivityBlockPermutation,
    ActivityBlockPermutationDiagnostics,
    build_activity_block_permutation,
)
from leo.analysis.research.joint_multipath_satellite_activity import (  # type: ignore[import-untyped]
    decode_joint_fixed_multipath_satellites,
)
from leo.analysis.research.multipath_satellite_activity import (  # type: ignore[import-untyped]
    FixedMultipathSatelliteHypothesis,
    MultipathSatelliteActivityProblem,
    ReceiverPathFixedHypothesis,
    decode_fixed_multipath_satellite,
)
from leo.analysis.research.satellite_activity import (  # type: ignore[import-untyped]
    ActivityGrid,
    PredictedProbeCfo,
)
from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]
from leo.sky.propagation import parse_element_sets  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools import replay_raw_grouped_satellite_activity as raw_replay  # noqa: E402
from tools import replay_raw_multipath_satellite_activity as multipath  # noqa: E402
from tools.replay_joint_fixed_satellite_activity import _doppler_curve  # noqa: E402

OUTPUT_SCHEMA = "org.leo.research.raw-multipath-paired-prediction-time-specificity/v1"
ALGORITHM = "atomic-explicit-shortlist-paired-prediction-time-specificity-v1"
FIXED_STATE_ALGORITHM = "bounded-exact-fixed-nuisance-joint-multipath-semimarkov-v2"
NULL_VS_ANY_PROOF_ALGORITHM = "additive-exclusive-group-single-minimum-proof-v1"
FAMILY_PLAN_SCHEMA = "org.leo.research.raw-multipath-prediction-time-family-plan/v1"
UTC_CELL_NS = 100_000_000
MINIMUM_CATALOG_COUNT = 2
MAXIMUM_CATALOG_COUNT = 3
MAXIMUM_CONTROL_COUNT = 16

IDENTITY_NONACTIVATION = "identity_nonactivation"
DERANGED_ACTIVATION_WITNESS = "deranged_activation_witness"
CONTROL_NULL_NOT_CERTIFIED = "control_null_not_certified"
ADVANTAGE_BELOW_FROZEN_THRESHOLD = "advantage_below_frozen_threshold"
ADVANTAGE_THRESHOLD_NOT_CALIBRATED = "advantage_threshold_not_calibrated"
SELECTION_CAUSALITY_NOT_VERIFIED = "selection_causality_not_verified"
BOUNDED_PREDICTION_TIME_GATE_PASS = "bounded_prediction_time_gate_pass"
NOT_COMPARABLE = "not_comparable"

_IMPLEMENTATION_FILE_PATHS = (
    "tools/replay_raw_multipath_paired_prediction_time_specificity.py",
    "tools/replay_raw_multipath_satellite_activity.py",
    "tools/replay_raw_grouped_satellite_activity.py",
    "tools/replay_joint_fixed_satellite_activity.py",
    "src/leo/analysis/research/activity_block_permutation.py",
    "src/leo/analysis/research/joint_multipath_satellite_activity.py",
    "src/leo/analysis/research/multipath_satellite_activity.py",
    "src/leo/analysis/research/multi_satellite_activity.py",
    "src/leo/analysis/research/grouped_satellite_activity.py",
    "src/leo/analysis/research/satellite_activity.py",
    "src/leo/analysis/research/satellite_activity_scores.py",
    "src/leo/sky/doppler.py",
    "src/leo/sky/frames.py",
    "src/leo/sky/propagation.py",
    "src/leo/sky/sampling.py",
    "src/leo/sky/screening.py",
    "src/leo/contracts/base.py",
    "src/leo/contracts/digests.py",
    "src/leo/contracts/sky.py",
    "pyproject.toml",
    "uv.lock",
)


@dataclass(frozen=True, slots=True)
class _ArmTransform:
    arm_id: str
    role: Literal["identity", "block_permutation_control"]
    transform_digest: str
    plan: ActivityBlockPermutation | None
    receipt: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _ArmEvaluation:
    transform: _ArmTransform
    document: dict[str, Any]


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: str, label: str) -> str:
    digest = value if value.startswith("sha256:") else f"sha256:{value}"
    if len(digest) != 71 or any(character not in "0123456789abcdef" for character in digest[7:]):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _finite_nonnegative(value: float, label: str) -> float:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return value


def _implementation_file_digests() -> dict[str, str]:
    return {
        relative_path: _file_digest(REPOSITORY_ROOT / relative_path)
        for relative_path in _IMPLEMENTATION_FILE_PATHS
    }


def _raw_problem_payload(
    contexts: tuple[multipath._PathContext, ...],
    problem: MultipathSatelliteActivityProblem,
) -> dict[str, Any]:
    context_by_path = {item.path_id: item for item in contexts}
    return {
        "decision_problem": asdict(problem),
        "paths": [
            {
                "path_id": path.path_id,
                "duration_input_digest": context_by_path[path.path_id].dataset_digest,
                "pilot_scan_digest": context_by_path[path.path_id].inventory.scan_digest,
                "pilot_scan_content_digest": context_by_path[path.path_id].scan_content_digest,
                "persisted_probe_utc": [
                    asdict(item) for item in context_by_path[path.path_id].probe_utc
                ],
                "raw_candidate_bundles": [
                    asdict(item) for item in context_by_path[path.path_id].inventory.observations
                ],
                "source_candidate_count": (
                    context_by_path[path.path_id].inventory.source_candidate_count
                ),
                "returned_candidate_count": (
                    context_by_path[path.path_id].inventory.returned_candidate_count
                ),
                "truncated_candidate_count": 0,
                "probe_count_at_retained_candidate_cap": (
                    context_by_path[path.path_id].inventory.saturated_probe_count
                ),
                "constant_elided_from_exact_decision_problem": (
                    context_by_path[path.path_id].inventory.elided_clutter_constant
                ),
                "pre_acquisition_cap_inventory_complete": False,
                "physical_signal_inventory_complete": False,
            }
            for path in problem.paths
        ],
    }


def _objective_payload(
    *,
    problem: MultipathSatelliteActivityProblem,
    calibration_document: dict[str, Any],
    calibration_digest: str,
    config: multipath.MultipathReplayConfig,
) -> dict[str, Any]:
    return {
        "fixed_state_algorithm": FIXED_STATE_ALGORITHM,
        "association_costs": asdict(problem.costs),
        "raw_score_calibration_schema": calibration_document.get("schema"),
        "raw_score_calibration_digest": calibration_digest,
        "raw_score_calibration_content_digest": canonical_digest(calibration_document),
        "configuration_cost_fields": {
            "cfo_sigma_hz": config.cfo_sigma_hz,
            "satellite_cost": config.satellite_cost,
            "episode_cost": config.episode_cost,
            "huber_threshold": config.huber_threshold,
            "delay_prior_mean_s": config.delay_prior_mean_s,
            "delay_prior_sigma_s": config.delay_prior_sigma_s,
        },
        "detector_score_costs_empirically_calibrated": False,
        "structural_costs_calibrated": False,
        "constant_elision_is_decision_invariant": True,
    }


def _search_universe_payload(
    *,
    catalogue: Any,
    catalog_indices: tuple[int, ...],
    contexts: tuple[multipath._PathContext, ...],
    problem: MultipathSatelliteActivityProblem,
    observer: ObserverSiteV1,
    config: multipath.MultipathReplayConfig,
    tle_digest: str,
) -> dict[str, Any]:
    return {
        "mode": "explicit-frozen-catalogue-shortlist-v1",
        "catalogs": [
            {
                "catalog_number": int(catalogue.satellite_numbers[index]),
                "object_name": str(catalogue.names[index]),
                "catalogue_index": index,
            }
            for index in catalog_indices
        ],
        "catalogue_search_performed": False,
        "tle_digest": tle_digest,
        "observer": observer.model_dump(mode="json"),
        "path_ids": [item.path_id for item in contexts],
        "rf_eligibility": {
            "mode": "all-supplied-paths-all-cells-eligible-v1",
            "cell_count": problem.grid.cell_count,
            "inferred_from_scored_observations": False,
        },
        "configuration": asdict(config),
        "delay_grid": list(config.delay_grid),
        "cfo_mode_proposal": {
            "algorithm": "raw-residual-histogram-data-proposed-modes",
            "same_policy_and_caps_in_every_arm": True,
            "arm_values_may_differ_only_because_prediction_epochs_differ": True,
            "mode_bin_hz": config.mode_bin_hz,
            "mode_half_width_hz": config.mode_half_width_hz,
            "modes_per_delay": config.modes_per_delay,
        },
        "bounded_state_search": {
            "retained_states_per_catalog": config.retained_states_per_catalog,
            "maximum_path_offset_combinations_per_delay": (
                config.maximum_path_offset_combinations_per_delay
            ),
            "maximum_state_combinations": config.maximum_state_combinations,
            "fixed_state_decisions_exact": True,
            "null_vs_any_proof_algorithm": NULL_VS_ANY_PROOF_ALGORITHM,
            "state_sort_key": "multipath-state-sort-key-v1",
            "joint_sort_key": "total-cost-selected-count-hypothesis-id-v1",
        },
    }


def _selection_context(
    *,
    family_label: str,
    contexts: tuple[multipath._PathContext, ...],
    problem: MultipathSatelliteActivityProblem,
    raw_problem_digest: str,
    objective_digest: str,
    search_universe_digest: str,
    producer_digest: str,
    control_indices: tuple[int, ...],
    minimum_advantage_cost: float,
) -> dict[str, Any]:
    if not family_label:
        raise ValueError("paired family label must be nonempty")
    return {
        "schema": FAMILY_PLAN_SCHEMA,
        "algorithm": ALGORITHM,
        "family_label": family_label,
        "session_id": contexts[0].dataset["capture"]["session_id"],
        "recording_manifest_digest": contexts[0].dataset["capture"]["recording_manifest_digest"],
        "raw_problem_digest": raw_problem_digest,
        "objective_digest": objective_digest,
        "search_universe_digest": search_universe_digest,
        "producer_digest": producer_digest,
        "window": {
            "start_s": problem.grid.start_s,
            "cell_duration_s": problem.grid.cell_duration_s,
            "cell_count": problem.grid.cell_count,
            "minimum_active_cells": problem.grid.minimum_active_cells,
        },
        "identity_arm_id": "identity",
        "control_indices": list(control_indices),
        "minimum_advantage_cost": minimum_advantage_cost,
        "comparison": "identity improvement strictly greater than strongest control",
        "require_every_control_to_be_a_certified_null": True,
        "all_declared_arms_must_be_emitted": True,
        "external_preregistration_verified": False,
        "advantage_threshold_calibrated": False,
    }


def _permutation_receipt(plan: ActivityBlockPermutation) -> dict[str, Any]:
    receipt = {
        "algorithm_version": plan.algorithm_version,
        "ranking_version": plan.ranking_version,
        "block_duration_s": plan.block_duration_s,
        "minimum_circular_displacement_s": plan.minimum_circular_displacement_s,
        "forbidden_forward_lag_blocks": list(plan.forbidden_forward_lag_blocks),
        **asdict(plan),
    }
    if receipt.get("plan_digest") != plan.plan_digest:
        raise RuntimeError("serialized permutation plan omits its plan digest")
    return receipt


def _freeze_arm_transforms(
    *,
    problem: MultipathSatelliteActivityProblem,
    selection_context_digest: str,
    control_indices: tuple[int, ...],
    maximum_delay_support_s: float,
) -> tuple[_ArmTransform, ...]:
    if not control_indices:
        raise ValueError("paired replay requires at least one control index")
    if len(control_indices) > MAXIMUM_CONTROL_COUNT:
        raise ValueError(f"paired replay refuses more than {MAXIMUM_CONTROL_COUNT} controls")
    if any(
        isinstance(index, bool) or not isinstance(index, int) or index < 0
        for index in control_indices
    ):
        raise ValueError("control indices must be nonnegative integers")
    if len(set(control_indices)) != len(control_indices):
        raise ValueError("paired replay control indices must be unique")
    ordered_indices = tuple(sorted(control_indices))
    identity_receipt = {
        "algorithm_version": "identity-prediction-epoch-map-v1",
        "prediction_cell_by_observation_cell": list(range(problem.grid.cell_count)),
        "observation_inventory_modified": False,
        "tle_prediction_epochs_modified": False,
    }
    identity_digest = canonical_digest(identity_receipt)
    transforms = [
        _ArmTransform(
            arm_id="identity",
            role="identity",
            transform_digest=identity_digest,
            plan=None,
            receipt={**identity_receipt, "transform_digest": identity_digest},
        )
    ]
    seen_mappings: set[tuple[int, ...]] = set()
    seen_digests = {identity_digest}
    for control_index in ordered_indices:
        plan = build_activity_block_permutation(
            problem.grid,
            session_key=selection_context_digest,
            control_index=control_index,
            maximum_delay_support_s=maximum_delay_support_s,
        )
        mapping = tuple(plan.prediction_block_by_observation_block)
        if mapping in seen_mappings or plan.plan_digest in seen_digests:
            raise RuntimeError("declared control indices produced duplicate permutation plans")
        seen_mappings.add(mapping)
        seen_digests.add(plan.plan_digest)
        transforms.append(
            _ArmTransform(
                arm_id=f"control-{control_index:06d}",
                role="block_permutation_control",
                transform_digest=plan.plan_digest,
                plan=plan,
                receipt=_permutation_receipt(plan),
            )
        )
    return tuple(transforms)


def _prediction_epoch_mapping(
    *,
    transform: _ArmTransform,
    context: multipath._PathContext,
    path: Any,
    grid_start_utc_ns: int,
) -> tuple[dict[str, int], dict[str, Any]]:
    if grid_start_utc_ns % UTC_CELL_NS:
        raise ValueError("paired replay grid start must align to 100 ms")
    utc_by_id = {item.probe_id: item for item in context.probe_utc}
    if tuple(item.probe_id for item in context.probe_utc) != tuple(
        item.probe_id for item in path.probes
    ):
        raise ValueError("persisted probe order differs from the shared decision problem")
    mapped: dict[str, int] = {}
    rows = []
    for probe in path.probes:
        utc = utc_by_id[probe.probe_id]
        if utc.cell_index != probe.cell_index:
            raise ValueError("persisted probe cell differs from the shared decision problem")
        cell_start = grid_start_utc_ns + probe.cell_index * UTC_CELL_NS
        offset_ns = utc.estimate_utc_ns - cell_start
        if not 0 <= offset_ns < UTC_CELL_NS:
            raise ValueError("persisted probe UTC lies outside its declared activity cell")
        prediction_cell = (
            probe.cell_index
            if transform.plan is None
            else transform.plan.prediction_cell_for_observation_cell(probe.cell_index)
        )
        prediction_utc_ns = grid_start_utc_ns + prediction_cell * UTC_CELL_NS + offset_ns
        mapped[probe.probe_id] = prediction_utc_ns
        rows.append(
            {
                "probe_id": probe.probe_id,
                "observation_utc_ns": utc.estimate_utc_ns,
                "observation_cell_index": probe.cell_index,
                "prediction_utc_ns": prediction_utc_ns,
                "prediction_cell_index": prediction_cell,
                "within_cell_offset_ns": offset_ns,
            }
        )
    payload = {
        "path_id": path.path_id,
        "arm_id": transform.arm_id,
        "transform_digest": transform.transform_digest,
        "mapping": rows,
    }
    return mapped, {**payload, "mapping_digest": canonical_digest(payload)}


def _propagate_mapped_probe_epochs(
    *,
    catalogue: Any,
    catalogue_index: int,
    context: multipath._PathContext,
    path: Any,
    mapped_prediction_utc_ns_by_probe_id: dict[str, int],
    delay_s: float,
    observer: ObserverSiteV1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Propagate ordered epochs, then restore the observation-probe order."""

    first_sample_utc_ns = int(context.dataset["timing_binding"]["first_estimate_utc_ns"])
    mapped_epochs = tuple(
        mapped_prediction_utc_ns_by_probe_id[probe.probe_id] for probe in path.probes
    )
    if len(set(mapped_epochs)) != len(mapped_epochs):
        raise ValueError("mapped prediction epochs must be unique within each path")
    propagation_order = tuple(sorted(range(len(mapped_epochs)), key=mapped_epochs.__getitem__))
    scheduled_times_s = tuple(
        (mapped_epochs[index] - first_sample_utc_ns) / 1e9 for index in propagation_order
    )
    if any(
        later <= earlier
        for earlier, later in zip(scheduled_times_s, scheduled_times_s[1:], strict=False)
    ):
        raise RuntimeError("sorted mapped prediction epochs are not strictly increasing")
    sorted_curve, sorted_elevation, sorted_altitude = _doppler_curve(
        catalogue=catalogue,
        satellite_index=catalogue_index,
        first_sample_utc_ns=first_sample_utc_ns,
        scheduled_times_s=scheduled_times_s,
        delay_s=delay_s,
        sky_frequency_hz=float(context.dataset["frequency_binding"]["sky_frequency_hz"]),
        observer=observer,
    )

    def restore_observation_order(values: Any, label: str) -> np.ndarray:
        ordered = np.asarray(values, dtype=np.float64)
        if ordered.shape != (len(path.probes),):
            raise RuntimeError(f"propagated {label} shape differs from the probe inventory")
        restored = np.empty(len(path.probes), dtype=np.float64)
        restored[np.asarray(propagation_order, dtype=np.intp)] = ordered
        return restored

    return (
        restore_observation_order(sorted_curve, "Doppler curve"),
        restore_observation_order(sorted_elevation, "elevation"),
        restore_observation_order(sorted_altitude, "altitude"),
    )


def _arm_catalog_state_bank(
    *,
    transform: _ArmTransform,
    catalogue: Any,
    catalogue_index: int,
    contexts: tuple[multipath._PathContext, ...],
    problem: MultipathSatelliteActivityProblem,
    prediction_utc_ns_by_path_probe: dict[str, dict[str, int]],
    calibration: raw_replay.ScoreCalibration,
    observer: ObserverSiteV1,
    config: multipath.MultipathReplayConfig,
) -> multipath._CatalogBank:
    catalog_number = int(catalogue.satellite_numbers[catalogue_index])
    object_name = str(catalogue.names[catalogue_index])
    context_by_path = {item.path_id: item for item in contexts}
    generated: list[multipath._StateEvaluation] = []
    possible_combination_count = 0
    evaluated_combination_count = 0
    path_offset_cartesian_exhausted = True
    eligible_by_cell = (True,) * problem.grid.cell_count

    for delay_s in config.delay_grid:
        fixed_by_path: list[tuple[str, tuple[float, ...], float, float]] = []
        modes_by_path: list[tuple[Any, ...]] = []
        for path in problem.paths:
            context = context_by_path[path.path_id]
            mapped = prediction_utc_ns_by_path_probe[path.path_id]
            curve, elevation, _altitude = _propagate_mapped_probe_epochs(
                catalogue=catalogue,
                catalogue_index=catalogue_index,
                context=context,
                path=path,
                mapped_prediction_utc_ns_by_probe_id=mapped,
                delay_s=delay_s,
                observer=observer,
            )
            minimum_elevation = float(np.min(elevation))
            maximum_elevation = float(np.max(elevation))
            if minimum_elevation <= config.horizon_mask_deg:
                raise ValueError(
                    f"NORAD {catalog_number} is not full-window visible in arm "
                    f"{transform.arm_id!r} path {path.path_id!r}"
                )
            modes = raw_replay._offset_modes(
                raw=context.inventory.observations,
                base_prediction_hz=np.asarray(curve, dtype=np.float64),
                calibration=calibration,
                config=config,
            )
            fixed_by_path.append(
                (
                    path.path_id,
                    tuple(float(value) for value in curve),
                    minimum_elevation,
                    maximum_elevation,
                )
            )
            modes_by_path.append(modes)

        possible_at_delay = math.prod(len(item) for item in modes_by_path)
        possible_combination_count += possible_at_delay
        evaluated_at_delay = 0
        for modes in itertools.islice(
            itertools.product(*modes_by_path),
            config.maximum_path_offset_combinations_per_delay,
        ):
            evaluated_at_delay += 1
            path_states = tuple(
                multipath._PathModeState(
                    path_id=path_id,
                    cfo_offset_hz=mode.cfo_offset_hz,
                    support_group_count=mode.support_group_count,
                    support_probe_count=mode.support_probe_count,
                    minimum_elevation_deg=minimum_elevation,
                    maximum_elevation_deg=maximum_elevation,
                    predictions_hz=curve,
                    eligible_by_cell=eligible_by_cell,
                )
                for (path_id, curve, minimum_elevation, maximum_elevation), mode in zip(
                    fixed_by_path,
                    modes,
                    strict=True,
                )
            )
            delay_prior_cost = (
                0.5 * ((delay_s - config.delay_prior_mean_s) / config.delay_prior_sigma_s) ** 2
            )
            hypothesis_id = canonical_digest(
                {
                    "catalog_number": catalog_number,
                    "delay_s": delay_s,
                    "path_cfo_offsets_hz": [
                        [item.path_id, item.cfo_offset_hz] for item in path_states
                    ],
                    "prediction_epoch_transform_digest": transform.transform_digest,
                    "prediction_epoch_role": transform.role,
                }
            )
            hypothesis = FixedMultipathSatelliteHypothesis(
                hypothesis_id=hypothesis_id,
                object_name=object_name,
                catalog_number=catalog_number,
                delay_s=delay_s,
                delay_prior_cost=delay_prior_cost,
                paths=tuple(
                    ReceiverPathFixedHypothesis(
                        path_id=state.path_id,
                        cfo_offset_hz=state.cfo_offset_hz,
                        predictions=tuple(
                            PredictedProbeCfo(probe.probe_id, state.predictions_hz[index])
                            for index, probe in enumerate(
                                next(
                                    item for item in problem.paths if item.path_id == state.path_id
                                ).probes
                            )
                        ),
                        eligible_by_cell=eligible_by_cell,
                    )
                    for state in path_states
                ),
            )
            decoded = decode_fixed_multipath_satellite(problem, hypothesis)
            generated.append(
                multipath._StateEvaluation(
                    hypothesis=hypothesis,
                    paths=path_states,
                    single_total_cost=decoded.objective.total_cost,
                    single_delta_from_null=decoded.objective.delta_from_null,
                    single_selected=decoded.selected,
                )
            )
        evaluated_combination_count += evaluated_at_delay
        if evaluated_at_delay != possible_at_delay:
            path_offset_cartesian_exhausted = False

    ordered = tuple(sorted(generated, key=multipath._state_sort_key))
    if not ordered:
        raise RuntimeError(f"NORAD {catalog_number} generated no state in arm {transform.arm_id!r}")
    return multipath._CatalogBank(
        generated=ordered,
        retained=ordered[: config.retained_states_per_catalog],
        possible_path_offset_combination_count=possible_combination_count,
        evaluated_path_offset_combination_count=evaluated_combination_count,
        path_offset_cartesian_exhausted=path_offset_cartesian_exhausted,
    )


def _state_bank_digest(bank: multipath._CatalogBank) -> str:
    return canonical_digest(
        {
            "generated": [
                {
                    "hypothesis": asdict(item.hypothesis),
                    "proposal_path_accounting": [
                        {
                            "path_id": path.path_id,
                            "cfo_offset_hz": path.cfo_offset_hz,
                            "support_group_count": path.support_group_count,
                            "support_probe_count": path.support_probe_count,
                            "minimum_elevation_deg": path.minimum_elevation_deg,
                            "maximum_elevation_deg": path.maximum_elevation_deg,
                        }
                        for path in item.paths
                    ],
                    "single_total_cost": item.single_total_cost,
                    "single_delta_from_null": item.single_delta_from_null,
                    "single_selected": item.single_selected,
                }
                for item in bank.generated
            ],
            "retained_hypothesis_ids": [item.hypothesis.hypothesis_id for item in bank.retained],
            "possible_path_offset_combination_count": (bank.possible_path_offset_combination_count),
            "evaluated_path_offset_combination_count": (
                bank.evaluated_path_offset_combination_count
            ),
            "path_offset_cartesian_exhausted": bank.path_offset_cartesian_exhausted,
        }
    )


def _evaluate_arm(
    *,
    transform: _ArmTransform,
    catalogue: Any,
    catalog_indices: tuple[int, ...],
    contexts: tuple[multipath._PathContext, ...],
    problem: MultipathSatelliteActivityProblem,
    calibration: raw_replay.ScoreCalibration,
    observer: ObserverSiteV1,
    config: multipath.MultipathReplayConfig,
    common_digests: dict[str, str],
    grid_start_utc_ns: int,
) -> _ArmEvaluation:
    context_by_path = {item.path_id: item for item in contexts}
    prediction_utc_ns_by_path_probe: dict[str, dict[str, int]] = {}
    mapping_receipts = []
    for path in problem.paths:
        mapped, receipt = _prediction_epoch_mapping(
            transform=transform,
            context=context_by_path[path.path_id],
            path=path,
            grid_start_utc_ns=grid_start_utc_ns,
        )
        prediction_utc_ns_by_path_probe[path.path_id] = mapped
        mapping_receipts.append(receipt)
    combined_mapping_digest = canonical_digest(mapping_receipts)

    banks = {
        int(catalogue.satellite_numbers[index]): _arm_catalog_state_bank(
            transform=transform,
            catalogue=catalogue,
            catalogue_index=index,
            contexts=contexts,
            problem=problem,
            prediction_utc_ns_by_path_probe=prediction_utc_ns_by_path_probe,
            calibration=calibration,
            observer=observer,
            config=config,
        )
        for index in catalog_indices
    }
    ordered_catalog_numbers = tuple(sorted(banks))
    possible_joint_combinations = math.prod(
        len(banks[catalog_number].retained) for catalog_number in ordered_catalog_numbers
    )
    evaluations: list[multipath._JointEvaluation] = []
    for states in itertools.islice(
        itertools.product(
            *(banks[catalog_number].retained for catalog_number in ordered_catalog_numbers)
        ),
        config.maximum_state_combinations,
    ):
        hypotheses = tuple(item.hypothesis for item in states)
        evaluations.append(
            multipath._JointEvaluation(
                hypotheses=hypotheses,
                result=decode_joint_fixed_multipath_satellites(problem, hypotheses),
            )
        )
    if not evaluations:
        raise RuntimeError(f"arm {transform.arm_id!r} generated no joint state combination")
    evaluations.sort(
        key=lambda item: (
            item.result.objective.total_cost,
            len(item.result.selected_catalog_numbers),
            tuple(hypothesis.hypothesis_id for hypothesis in item.hypotheses),
        )
    )
    best = evaluations[0]
    retained_joint_state_space_exhausted = len(evaluations) == possible_joint_combinations
    per_catalog_state_banks_pruned = any(
        len(bank.retained) < len(bank.generated) for bank in banks.values()
    )
    per_catalog_path_offset_search_exhausted = all(
        bank.path_offset_cartesian_exhausted for bank in banks.values()
    )
    finite_search_exact = (
        retained_joint_state_space_exhausted
        and not per_catalog_state_banks_pruned
        and per_catalog_path_offset_search_exhausted
    )
    generated_states = tuple(state for bank in banks.values() for state in bank.generated)
    if any(
        state.single_selected != (state.single_delta_from_null < 0.0) for state in generated_states
    ):
        raise RuntimeError("a fixed-state activation flag disagrees with its exact objective")
    exact_single_fixed_state_activation_witness_found = any(
        state.single_selected for state in generated_states
    )
    all_generated_single_fixed_states_nonactivating = all(
        not state.single_selected and state.single_delta_from_null >= 0.0
        for state in generated_states
    )
    exact_joint_activation_witness_found = bool(best.result.selected_catalog_numbers)
    if exact_joint_activation_witness_found != exact_single_fixed_state_activation_witness_found:
        raise RuntimeError(
            "joint activation disagrees with the exact single-state separability result"
        )
    elided_constant = math.fsum(context.inventory.elided_clutter_constant for context in contexts)
    full_null_cost = best.result.objective.null_cost + elided_constant
    full_total_cost = best.result.objective.total_cost + elided_constant
    primitive_delta_from_null = full_total_cost - full_null_cost
    solver_delta_from_null = best.result.objective.delta_from_null
    delta_tolerance = 2.0 * max(
        math.ulp(full_null_cost),
        math.ulp(full_total_cost),
        math.ulp(primitive_delta_from_null),
        math.ulp(solver_delta_from_null),
    )
    if (primitive_delta_from_null < 0.0) != (solver_delta_from_null < 0.0) or abs(
        primitive_delta_from_null - solver_delta_from_null
    ) > delta_tolerance:
        raise RuntimeError("serialized full objective is internally inconsistent")
    full_objective = {
        "null_cost": full_null_cost,
        "total_cost": full_total_cost,
        "delta_from_null": primitive_delta_from_null,
        "constant_elided_from_exact_decision_problem": elided_constant,
    }
    joint_activation_witness_found = primitive_delta_from_null < 0.0
    single_fixed_state_activation_witness_found = joint_activation_witness_found
    rounding_erased_activation_witness = (
        exact_single_fixed_state_activation_witness_found
        and not single_fixed_state_activation_witness_found
    )
    null_vs_any_declared_state_universe_solved = single_fixed_state_activation_witness_found or (
        per_catalog_path_offset_search_exhausted and all_generated_single_fixed_states_nonactivating
    )
    association = asdict(best.result)
    association["selected_catalog_numbers"] = list(best.result.selected_catalog_numbers)
    association["selected_satellite_count"] = len(best.result.selected_catalog_numbers)
    for satellite_document, satellite in zip(
        association["satellites"],
        best.result.satellites,
        strict=True,
    ):
        satellite_document["latent_activity_support"] = multipath._latent_activity_support(
            satellite,
            contexts,
        )

    joint_evaluation_payload = [
        {
            "hypothesis_ids": [hypothesis.hypothesis_id for hypothesis in item.hypotheses],
            "selected_catalog_numbers": list(item.result.selected_catalog_numbers),
            "total_cost": item.result.objective.total_cost,
            "delta_from_null": item.result.objective.delta_from_null,
        }
        for item in evaluations
    ]
    document = {
        "arm_id": transform.arm_id,
        "role": transform.role,
        "transform_digest": transform.transform_digest,
        "transform": transform.receipt,
        "common_digests": common_digests,
        "prediction_epoch_mapping": {
            "same_mapping_all_catalogues_delays_and_cfo_modes": True,
            "combined_mapping_digest": combined_mapping_digest,
            "paths": mapping_receipts,
        },
        "search": {
            "catalogs": [
                {
                    "catalog_number": catalog_number,
                    "generated_state_count": len(banks[catalog_number].generated),
                    "retained_state_count": len(banks[catalog_number].retained),
                    "generated_state_bank_digest": _state_bank_digest(banks[catalog_number]),
                    "possible_path_offset_combination_count": banks[
                        catalog_number
                    ].possible_path_offset_combination_count,
                    "evaluated_path_offset_combination_count": banks[
                        catalog_number
                    ].evaluated_path_offset_combination_count,
                    "path_offset_cartesian_exhausted": banks[
                        catalog_number
                    ].path_offset_cartesian_exhausted,
                    "retained_every_generated_state": (
                        len(banks[catalog_number].retained) == len(banks[catalog_number].generated)
                    ),
                }
                for catalog_number in ordered_catalog_numbers
            ],
            "possible_retained_joint_state_combination_count": possible_joint_combinations,
            "evaluated_retained_joint_state_combination_count": len(evaluations),
            "retained_joint_state_space_exhausted": retained_joint_state_space_exhausted,
            "per_catalog_state_banks_pruned": per_catalog_state_banks_pruned,
            "per_catalog_path_offset_search_exhausted": (per_catalog_path_offset_search_exhausted),
            "finite_declared_search_exact": finite_search_exact,
            "null_vs_any_declared_state_universe_solved": (
                null_vs_any_declared_state_universe_solved
            ),
            "single_fixed_state_activation_witness_found": (
                single_fixed_state_activation_witness_found
            ),
            "rounding_erased_fixed_state_activation_witness": rounding_erased_activation_witness,
            "all_generated_single_fixed_states_nonactivating": (
                all_generated_single_fixed_states_nonactivating
            ),
            "null_vs_any_separability_proof": {
                "algorithm": NULL_VS_ANY_PROOF_ALGORITHM,
                "single_fixed_state_decisions_exact": True,
                "joint_delta_is_sum_of_selected_satellite_reduced_contributions": True,
                "exclusion_group_assignment_capacity": 1,
                "satellite_and_episode_costs_nonnegative": (
                    problem.costs.satellite_cost >= 0.0 and problem.costs.episode_cost >= 0.0
                ),
                "retained_state_bank_pruning_irrelevant_to_a_certified_null": True,
            },
            "every_evaluated_fixed_state_decision_exact": True,
            "joint_evaluations_digest": canonical_digest(joint_evaluation_payload),
        },
        "decision": {
            "activation_witness_found": joint_activation_witness_found,
            "objective_improvement_is_global_exact": finite_search_exact,
            "objective_improvement_is_lower_bound_witness": (
                joint_activation_witness_found and not finite_search_exact
            ),
            "selected_catalog_numbers": list(best.result.selected_catalog_numbers),
            "selected_satellite_count": len(best.result.selected_catalog_numbers),
            "full_persisted_inventory_objective": full_objective,
        },
        "association": association,
        "path_full_persisted_inventory_objectives": multipath._full_path_objectives(
            best.result,
            contexts,
        ),
        "selected_path_assignment_details": multipath._selected_path_details(
            best.result,
            banks,
            contexts,
        ),
    }
    return _ArmEvaluation(transform=transform, document=document)


def _arm_objective(arm: dict[str, Any]) -> dict[str, float]:
    raw = arm.get("decision", {}).get("full_persisted_inventory_objective")
    if not isinstance(raw, dict):
        raise ValueError("paired arm omits its full persisted-inventory objective")
    null_cost = float(raw["null_cost"])
    total_cost = float(raw["total_cost"])
    serialized_delta = float(raw["delta_from_null"])
    if not all(math.isfinite(value) for value in (null_cost, total_cost, serialized_delta)):
        raise ValueError("paired arm objective must be finite")
    primitive_delta = total_cost - null_cost
    if serialized_delta != primitive_delta:
        raise ValueError(
            "paired arm serialized delta must equal primitive total cost minus null cost"
        )
    if primitive_delta > 0.0:
        raise ValueError("paired arm minimum cannot be more costly than its available null")
    return {
        "null_cost": null_cost,
        "total_cost": total_cost,
        "delta_from_null": primitive_delta,
    }


def _control_plan_from_receipt(receipt: dict[str, Any]) -> ActivityBlockPermutation:
    grid_raw = receipt["grid"]
    diagnostics_raw = receipt["diagnostics"]
    if not isinstance(grid_raw, dict) or not isinstance(diagnostics_raw, dict):
        raise ValueError("control transform grid and diagnostics must be objects")

    def pairs(value: Any, label: str) -> tuple[tuple[int, int], ...]:
        if not isinstance(value, (list, tuple)) or any(
            not isinstance(item, (list, tuple)) or len(item) != 2 for item in value
        ):
            raise ValueError(f"control transform {label} must contain pairs")
        return tuple((item[0], item[1]) for item in value)

    grid = ActivityGrid(
        start_s=grid_raw["start_s"],
        cell_duration_s=grid_raw["cell_duration_s"],
        cell_count=grid_raw["cell_count"],
        minimum_active_cells=grid_raw["minimum_active_cells"],
        allow_left_censored=grid_raw["allow_left_censored"],
        allow_right_censored=grid_raw["allow_right_censored"],
    )
    diagnostics = ActivityBlockPermutationDiagnostics(
        selection_attempt_count=diagnostics_raw["selection_attempt_count"],
        selected_attempt_search_step_count=diagnostics_raw["selected_attempt_search_step_count"],
        total_search_step_count=diagnostics_raw["total_search_step_count"],
        forbidden_forward_lag_blocks=tuple(diagnostics_raw["forbidden_forward_lag_blocks"]),
        preserved_forward_lag_counts=pairs(
            diagnostics_raw["preserved_forward_lag_counts"],
            "preserved-forward-lag diagnostics",
        ),
        directed_displacement_multiplicities=pairs(
            diagnostics_raw["directed_displacement_multiplicities"],
            "directed-displacement diagnostics",
        ),
        distinct_directed_displacement_count=diagnostics_raw[
            "distinct_directed_displacement_count"
        ],
        required_distinct_directed_displacement_count=diagnostics_raw[
            "required_distinct_directed_displacement_count"
        ],
        maximum_directed_displacement_multiplicity=diagnostics_raw[
            "maximum_directed_displacement_multiplicity"
        ],
        allowed_maximum_directed_displacement_multiplicity=diagnostics_raw[
            "allowed_maximum_directed_displacement_multiplicity"
        ],
        realized_minimum_circular_displacement_blocks=diagnostics_raw[
            "realized_minimum_circular_displacement_blocks"
        ],
        mapping_is_affine=diagnostics_raw["mapping_is_affine"],
    )
    plan = ActivityBlockPermutation(
        grid=grid,
        block_cells=receipt["block_cells"],
        block_count=receipt["block_count"],
        maximum_delay_support_s=receipt["maximum_delay_support_s"],
        minimum_circular_displacement_blocks=receipt["minimum_circular_displacement_blocks"],
        session_key_digest=receipt["session_key_digest"],
        control_index=receipt["control_index"],
        maximum_search_attempts=receipt["maximum_search_attempts"],
        maximum_search_steps_per_attempt=receipt["maximum_search_steps_per_attempt"],
        prediction_block_by_observation_block=tuple(
            receipt["prediction_block_by_observation_block"]
        ),
        diagnostics=diagnostics,
        plan_digest=receipt["plan_digest"],
    )
    if canonical_digest(receipt) != canonical_digest(_permutation_receipt(plan)):
        raise ValueError("control transform receipt has missing, extra, or derived-field changes")
    return plan


def _validate_arm_transform_receipt(
    arm: dict[str, Any],
    planned_arm: dict[str, Any],
    *,
    cell_count: int,
    family_window: dict[str, Any],
    expected_session_key_digest: str,
    expected_maximum_delay_support_s: float,
) -> ActivityBlockPermutation | None:
    if set(planned_arm) != {"arm_id", "role", "transform_digest", "transform"}:
        raise ValueError("frozen family arm receipt has missing or extra fields")
    if arm.get("arm_id") != planned_arm["arm_id"] or arm.get("role") != planned_arm["role"]:
        raise ValueError("emitted arm identity or role differs from the frozen family plan")
    transform_digest = arm.get("transform_digest")
    if transform_digest != planned_arm["transform_digest"]:
        raise ValueError("emitted arm transform digest differs from the frozen family plan")
    transform = arm.get("transform")
    planned_transform = planned_arm["transform"]
    if not isinstance(transform, dict) or not isinstance(planned_transform, dict):
        raise ValueError("paired arm omits its full transform receipt")
    if canonical_digest(transform) != canonical_digest(planned_transform):
        raise ValueError("emitted arm transform receipt differs from the frozen family plan")

    if arm["role"] == "identity":
        identity_payload = {
            "algorithm_version": "identity-prediction-epoch-map-v1",
            "prediction_cell_by_observation_cell": list(range(cell_count)),
            "observation_inventory_modified": False,
            "tle_prediction_epochs_modified": False,
        }
        expected_digest = canonical_digest(identity_payload)
        expected_receipt = {**identity_payload, "transform_digest": expected_digest}
        if transform_digest != expected_digest or canonical_digest(transform) != canonical_digest(
            expected_receipt
        ):
            raise ValueError("identity transform receipt is not the exact identity mapping")
        return None

    plan = _control_plan_from_receipt(transform)
    if transform_digest != plan.plan_digest:
        raise ValueError("control transform digest disagrees with its recomputed plan digest")
    if plan.grid.cell_count != cell_count:
        raise ValueError("control transform grid differs from the frozen family window")
    if (
        plan.grid.start_s != family_window.get("start_s")
        or plan.grid.cell_duration_s != family_window.get("cell_duration_s")
        or plan.grid.minimum_active_cells != family_window.get("minimum_active_cells")
        or plan.grid.allow_left_censored
        or plan.grid.allow_right_censored
        or plan.session_key_digest != expected_session_key_digest
        or plan.maximum_delay_support_s != expected_maximum_delay_support_s
        or plan.control_index != int(str(arm["arm_id"]).removeprefix("control-"))
    ):
        raise ValueError("control transform receipt differs from its frozen selection context")
    return plan


def _validate_mapping_receipts(
    arm: dict[str, Any],
    *,
    expected_paths: tuple[tuple[str, tuple[dict[str, Any], ...]], ...],
    control_plan: ActivityBlockPermutation | None,
    cell_count: int,
) -> str:
    envelope = arm.get("prediction_epoch_mapping")
    if not isinstance(envelope, dict) or set(envelope) != {
        "same_mapping_all_catalogues_delays_and_cfo_modes",
        "combined_mapping_digest",
        "paths",
    }:
        raise ValueError("paired arm omits its full prediction-epoch mapping receipt")
    if envelope["same_mapping_all_catalogues_delays_and_cfo_modes"] is not True:
        raise ValueError("paired arm does not declare one shared prediction-epoch mapping")
    path_receipts = envelope["paths"]
    if not isinstance(path_receipts, list) or len(path_receipts) != len(expected_paths):
        raise ValueError("paired arm mapping paths differ from the raw path inventory")
    combined_digest = envelope["combined_mapping_digest"]
    if combined_digest != canonical_digest(path_receipts):
        raise ValueError("paired arm combined mapping digest does not recompute")

    semantic_mapping = []
    for receipt, (expected_path_id, expected_probes) in zip(
        path_receipts,
        expected_paths,
        strict=True,
    ):
        if not isinstance(receipt, dict) or set(receipt) != {
            "path_id",
            "arm_id",
            "transform_digest",
            "mapping",
            "mapping_digest",
        }:
            raise ValueError("paired arm path mapping receipt has missing or extra fields")
        mapping = receipt["mapping"]
        if not isinstance(mapping, list) or len(mapping) != len(expected_probes):
            raise ValueError("paired arm mapping rows differ from the persisted probe inventory")
        payload = {
            "path_id": receipt["path_id"],
            "arm_id": receipt["arm_id"],
            "transform_digest": receipt["transform_digest"],
            "mapping": mapping,
        }
        if receipt["mapping_digest"] != canonical_digest(payload):
            raise ValueError("paired arm path mapping digest does not recompute")
        if (
            receipt["path_id"] != expected_path_id
            or receipt["arm_id"] != arm["arm_id"]
            or receipt["transform_digest"] != arm["transform_digest"]
        ):
            raise ValueError("paired arm path mapping provenance is inconsistent")

        semantic_rows = []
        for row, expected_probe in zip(mapping, expected_probes, strict=True):
            if not isinstance(row, dict) or set(row) != {
                "probe_id",
                "observation_utc_ns",
                "observation_cell_index",
                "prediction_utc_ns",
                "prediction_cell_index",
                "within_cell_offset_ns",
            }:
                raise ValueError("paired arm probe mapping row has missing or extra fields")
            integer_fields = (
                row["observation_utc_ns"],
                row["observation_cell_index"],
                row["prediction_utc_ns"],
                row["prediction_cell_index"],
                row["within_cell_offset_ns"],
            )
            if any(
                isinstance(value, bool) or not isinstance(value, int) for value in integer_fields
            ):
                raise ValueError("paired arm probe mapping uses noninteger geometry")
            observation_cell = row["observation_cell_index"]
            if not 0 <= observation_cell < cell_count:
                raise ValueError("paired arm observation cell lies outside the family window")
            expected_prediction_cell = (
                observation_cell
                if control_plan is None
                else control_plan.prediction_cell_for_observation_cell(observation_cell)
            )
            if (
                row["probe_id"] != expected_probe.get("probe_id")
                or row["observation_utc_ns"] != expected_probe.get("estimate_utc_ns")
                or observation_cell != expected_probe.get("cell_index")
                or row["prediction_cell_index"] != expected_prediction_cell
                or row["within_cell_offset_ns"] != row["observation_utc_ns"] % UTC_CELL_NS
                or not 0 <= row["within_cell_offset_ns"] < UTC_CELL_NS
                or row["prediction_utc_ns"] - row["observation_utc_ns"]
                != (expected_prediction_cell - observation_cell) * UTC_CELL_NS
            ):
                raise ValueError("paired arm probe mapping disagrees with raw epochs or transform")
            semantic_rows.append(
                [
                    row["probe_id"],
                    row["prediction_cell_index"],
                    row["prediction_utc_ns"],
                ]
            )
        semantic_mapping.append([expected_path_id, semantic_rows])
    return canonical_digest(semantic_mapping)


def _validated_common_documents(
    common: dict[str, Any],
    *,
    minimum_advantage_cost: float,
    advantage_threshold_calibrated: bool,
    external_preregistration_verified: bool,
) -> tuple[
    dict[str, str],
    tuple[dict[str, Any], ...],
    tuple[tuple[str, tuple[dict[str, Any], ...]], ...],
]:
    expected_document_fields = {
        "digests",
        "raw_problem",
        "objective",
        "search_universe",
        "producer",
        "family_plan",
    }
    if not isinstance(common, dict) or set(common) != expected_document_fields:
        raise ValueError("paired adjudication requires every exact common document")
    if any(
        not isinstance(common[field], dict)
        for field in expected_document_fields
        if field != "digests"
    ):
        raise ValueError("paired common documents must be objects")
    digests = common["digests"]
    if not isinstance(digests, dict):
        raise ValueError("paired common digests must be an object")
    digest_fields = {
        "raw_problem": "raw_problem_digest",
        "objective": "objective_digest",
        "search_universe": "search_universe_digest",
        "producer": "producer_digest",
        "family_plan": "family_plan_digest",
    }
    if set(digests) != set(digest_fields.values()):
        raise ValueError("paired common digest inventory is incomplete or has extra fields")
    for document_field, digest_field in digest_fields.items():
        observed_digest = _canonical_sha256(str(digests[digest_field]), digest_field)
        if observed_digest != canonical_digest(common[document_field]):
            raise ValueError(f"paired common {document_field!r} content digest does not recompute")

    raw_paths = common["raw_problem"].get("paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ValueError("paired raw problem omits its path inventory")
    expected_paths = []
    for raw_path in raw_paths:
        if not isinstance(raw_path, dict) or not isinstance(raw_path.get("path_id"), str):
            raise ValueError("paired raw path inventory is malformed")
        persisted_probes = raw_path.get("persisted_probe_utc")
        if (
            not isinstance(persisted_probes, list)
            or not persisted_probes
            or any(not isinstance(item, dict) for item in persisted_probes)
        ):
            raise ValueError("paired raw path omits its persisted probe UTC inventory")
        expected_paths.append((raw_path["path_id"], tuple(persisted_probes)))
    if len({item[0] for item in expected_paths}) != len(expected_paths):
        raise ValueError("paired raw problem contains duplicate path IDs")

    family_plan = common["family_plan"]
    if not isinstance(family_plan, dict):
        raise ValueError("paired family plan must be an object")
    for digest_field in (
        "raw_problem_digest",
        "objective_digest",
        "search_universe_digest",
        "producer_digest",
    ):
        if family_plan.get(digest_field) != digests[digest_field]:
            raise ValueError("paired family plan differs from its common content digests")
    if family_plan.get("schema") != FAMILY_PLAN_SCHEMA or family_plan.get("algorithm") != ALGORITHM:
        raise ValueError("paired family plan schema or algorithm is invalid")
    if (
        family_plan.get("minimum_advantage_cost") != minimum_advantage_cost
        or family_plan.get("advantage_threshold_calibrated") is not advantage_threshold_calibrated
        or family_plan.get("external_preregistration_verified")
        is not external_preregistration_verified
    ):
        raise ValueError("paired gate authority differs from the frozen family plan")
    if (
        family_plan.get("identity_arm_id") != "identity"
        or family_plan.get("comparison")
        != "identity improvement strictly greater than strongest control"
        or family_plan.get("require_every_control_to_be_a_certified_null") is not True
        or family_plan.get("all_declared_arms_must_be_emitted") is not True
        or family_plan.get("family_frozen_before_arm_scoring") is not True
        or family_plan.get("all_control_plans_built_before_arm_scoring") is not True
    ):
        raise ValueError("paired family plan does not freeze the required gate semantics")
    planned_arms = family_plan.get("arms")
    if (
        not isinstance(planned_arms, list)
        or len(planned_arms) < 2
        or any(not isinstance(item, dict) for item in planned_arms)
    ):
        raise ValueError("paired family plan omits its complete arm inventory")
    planned_ids = tuple(item.get("arm_id") for item in planned_arms)
    planned_roles = tuple(item.get("role") for item in planned_arms)
    if (
        planned_ids[0] != "identity"
        or planned_roles[0] != "identity"
        or any(role != "block_permutation_control" for role in planned_roles[1:])
        or len(set(planned_ids)) != len(planned_ids)
        or any(not isinstance(arm_id, str) or not arm_id for arm_id in planned_ids)
    ):
        raise ValueError("paired family plan has an invalid role or arm-ID inventory")
    control_indices = family_plan.get("control_indices")
    expected_control_ids = (
        tuple(
            f"control-{index:06d}"
            for index in control_indices
            if isinstance(index, int) and not isinstance(index, bool) and index >= 0
        )
        if isinstance(control_indices, list)
        else ()
    )
    if (
        not isinstance(control_indices, list)
        or len(expected_control_ids) != len(control_indices)
        or len(set(control_indices)) != len(control_indices)
        or tuple(control_indices) != tuple(sorted(control_indices))
        or planned_ids[1:] != expected_control_ids
    ):
        raise ValueError("paired family plan control indices disagree with its arm IDs")
    return (
        {str(key): str(value) for key, value in digests.items()},
        tuple(planned_arms),
        tuple(expected_paths),
    )


def _arm_null_vs_any_status(arm: dict[str, Any]) -> dict[str, bool]:
    search = arm.get("search")
    if not isinstance(search, dict):
        raise ValueError("paired arm omits its declared-state search accounting")
    keys = (
        "finite_declared_search_exact",
        "per_catalog_path_offset_search_exhausted",
        "single_fixed_state_activation_witness_found",
        "all_generated_single_fixed_states_nonactivating",
        "null_vs_any_declared_state_universe_solved",
    )
    status: dict[str, bool] = {}
    for key in keys:
        value = search.get(key)
        if not isinstance(value, bool):
            raise ValueError(f"paired arm search field {key!r} must be Boolean")
        status[key] = value
    witness = status["single_fixed_state_activation_witness_found"]
    all_nonactivating = status["all_generated_single_fixed_states_nonactivating"]
    if witness and all_nonactivating:
        raise ValueError(
            "paired arm single-state search cannot report both activation and all-null"
        )
    expected_solved = witness or (
        status["per_catalog_path_offset_search_exhausted"] and all_nonactivating
    )
    if status["null_vs_any_declared_state_universe_solved"] != expected_solved:
        raise ValueError("paired arm null-vs-any certificate is internally inconsistent")
    return status


def adjudicate_paired_arms(
    *,
    arms: tuple[dict[str, Any], ...],
    common: dict[str, Any],
    minimum_advantage_cost: float,
    advantage_threshold_calibrated: bool,
    external_preregistration_verified: bool,
) -> dict[str, Any]:
    """Reduce one already-frozen arm family without upgrading its claims."""

    _finite_nonnegative(minimum_advantage_cost, "minimum advantage cost")
    reasons = []
    try:
        expected_common_digests, planned_arms, expected_paths = _validated_common_documents(
            common,
            minimum_advantage_cost=minimum_advantage_cost,
            advantage_threshold_calibrated=advantage_threshold_calibrated,
            external_preregistration_verified=external_preregistration_verified,
        )
    except (KeyError, IndexError, TypeError, ValueError) as error:
        reasons.append(str(error))
        expected_common_digests = {}
        planned_arms = ()
        expected_paths = ()

    arm_ids = tuple(str(item.get("arm_id", "")) for item in arms)
    roles = tuple(str(item.get("role", "")) for item in arms)
    planned_arm_ids = tuple(str(item.get("arm_id", "")) for item in planned_arms)
    if arm_ids != planned_arm_ids:
        reasons.append("emitted arm IDs differ from the frozen family plan")
    if len(set(arm_ids)) != len(arm_ids) or any(not item for item in arm_ids):
        reasons.append("emitted arm IDs are empty or duplicated")
    expected_roles = ("identity",) + ("block_permutation_control",) * max(0, len(arms) - 1)
    if roles != expected_roles:
        reasons.append("paired arm roles must be identity followed only by block controls")
    transform_digests = tuple(str(item.get("transform_digest", "")) for item in arms)
    if len(set(transform_digests)) != len(transform_digests) or any(
        not item for item in transform_digests
    ):
        reasons.append("prediction-time transform digests are empty or duplicated")
    for arm in arms:
        if arm.get("common_digests") != expected_common_digests:
            reasons.append(f"arm {arm.get('arm_id')!r} differs from the frozen common digests")
    semantic_mapping_digests = []
    if len(arms) == len(planned_arms) and expected_paths:
        try:
            family_plan = common["family_plan"]
            family_window = family_plan["window"]
            if not isinstance(family_window, dict):
                raise ValueError("paired family window must be an object")
            cell_count = family_window["cell_count"]
            if isinstance(cell_count, bool) or not isinstance(cell_count, int) or cell_count < 1:
                raise ValueError("paired family window cell count must be a positive integer")
            selection_context = {
                key: value
                for key, value in family_plan.items()
                if key
                not in {
                    "arms",
                    "family_frozen_before_arm_scoring",
                    "all_control_plans_built_before_arm_scoring",
                }
            }
            selection_context_digest = canonical_digest(selection_context)
            expected_session_key_digest = (
                "sha256:" + hashlib.sha256(selection_context_digest.encode("utf-8")).hexdigest()
            )
            search_configuration = common["search_universe"]["configuration"]
            if not isinstance(search_configuration, dict):
                raise ValueError("paired search configuration must be an object")
            expected_maximum_delay_support_s = max(
                abs(float(search_configuration["delay_min_s"])),
                abs(float(search_configuration["delay_max_s"])),
            )
            for arm, planned_arm in zip(arms, planned_arms, strict=True):
                control_plan = _validate_arm_transform_receipt(
                    arm,
                    planned_arm,
                    cell_count=cell_count,
                    family_window=family_window,
                    expected_session_key_digest=expected_session_key_digest,
                    expected_maximum_delay_support_s=expected_maximum_delay_support_s,
                )
                semantic_mapping_digests.append(
                    _validate_mapping_receipts(
                        arm,
                        expected_paths=expected_paths,
                        control_plan=control_plan,
                        cell_count=cell_count,
                    )
                )
        except (KeyError, IndexError, TypeError, ValueError) as error:
            reasons.append(str(error))
    if semantic_mapping_digests and len(set(semantic_mapping_digests)) != len(
        semantic_mapping_digests
    ):
        reasons.append("paired arms have duplicate prediction-epoch mapping receipts")
    try:
        objective_by_id = {
            str(arm["arm_id"]): _arm_objective(arm)
            for arm in arms
            if isinstance(arm, dict) and isinstance(arm.get("arm_id"), str)
        }
    except (KeyError, TypeError, ValueError) as error:
        reasons.append(str(error))
        objective_by_id = {}
    try:
        search_status_by_id = {
            str(arm["arm_id"]): _arm_null_vs_any_status(arm)
            for arm in arms
            if isinstance(arm, dict) and isinstance(arm.get("arm_id"), str)
        }
    except (KeyError, TypeError, ValueError) as error:
        reasons.append(str(error))
        search_status_by_id = {}
    null_costs = {item["null_cost"].hex() for item in objective_by_id.values()}
    if len(null_costs) != 1:
        reasons.append("paired arms do not have one bit-identical null cost")
    for arm in arms:
        arm_id = str(arm.get("arm_id", ""))
        objective = objective_by_id.get(arm_id)
        if objective is None:
            continue
        activation_raw = arm.get("decision", {}).get("activation_witness_found")
        if not isinstance(activation_raw, bool):
            reasons.append(f"arm {arm_id!r} activation flag must be Boolean")
            continue
        activation = activation_raw
        if activation != (objective["delta_from_null"] < 0.0):
            reasons.append(f"arm {arm_id!r} activation flag disagrees with its objective")
        search_status = search_status_by_id.get(arm_id)
        if (
            search_status is not None
            and activation != search_status["single_fixed_state_activation_witness_found"]
        ):
            reasons.append(f"arm {arm_id!r} joint activation disagrees with its single-state proof")

    if reasons:
        return {
            "disposition": NOT_COMPARABLE,
            "comparable": False,
            "paired_gate_passed": False,
            "relative_advantage_passed": False,
            "specificity_claimed": False,
            "reasons": reasons,
        }

    identity = next(arm for arm in arms if arm["role"] == "identity")
    controls = tuple(arm for arm in arms if arm["role"] == "block_permutation_control")
    identity_objective = objective_by_id[str(identity["arm_id"])]
    identity_improvement = max(0.0, -identity_objective["delta_from_null"])
    control_rows = []
    for control in controls:
        objective = objective_by_id[str(control["arm_id"])]
        search_status = search_status_by_id[str(control["arm_id"])]
        improvement = max(0.0, -objective["delta_from_null"])
        control_rows.append(
            {
                "arm_id": control["arm_id"],
                "delta_from_null": objective["delta_from_null"],
                "improvement_from_null": improvement,
                "identity_advantage_cost": identity_improvement - improvement,
                "activation_witness_found": bool(
                    control.get("decision", {}).get("activation_witness_found")
                ),
                "finite_declared_search_exact": bool(search_status["finite_declared_search_exact"]),
                "null_vs_any_declared_state_universe_solved": bool(
                    search_status["null_vs_any_declared_state_universe_solved"]
                ),
            }
        )
    strongest_control = min(
        control_rows,
        key=lambda item: (-item["improvement_from_null"], item["arm_id"]),
    )
    strongest_control_improvement = float(strongest_control["improvement_from_null"])
    paired_advantage = identity_improvement - strongest_control_improvement
    relative_advantage_passed = paired_advantage > minimum_advantage_cost
    identity_activation = bool(identity["decision"]["activation_witness_found"])
    activating_controls = tuple(
        item["arm_id"] for item in control_rows if item["activation_witness_found"]
    )
    certified_control_nulls = all(
        not item["activation_witness_found"] and item["null_vs_any_declared_state_universe_solved"]
        for item in control_rows
    )

    if not identity_activation:
        disposition = IDENTITY_NONACTIVATION
        disposition_reasons = ["the identity arm did not beat the shared null"]
    elif activating_controls:
        disposition = DERANGED_ACTIVATION_WITNESS
        disposition_reasons = ["at least one frozen block-permutation control beat the shared null"]
    elif not certified_control_nulls:
        disposition = CONTROL_NULL_NOT_CERTIFIED
        disposition_reasons = [
            "no control activated, but its declared-state separability proof is incomplete"
        ]
    elif not relative_advantage_passed:
        disposition = ADVANTAGE_BELOW_FROZEN_THRESHOLD
        disposition_reasons = [
            "identity advantage is not strictly greater than the frozen threshold"
        ]
    elif not advantage_threshold_calibrated:
        disposition = ADVANTAGE_THRESHOLD_NOT_CALIBRATED
        disposition_reasons = ["the frozen objective-cost threshold is not calibrated"]
    elif not external_preregistration_verified:
        disposition = SELECTION_CAUSALITY_NOT_VERIFIED
        disposition_reasons = ["external preregistration or timestamp causality was not verified"]
    else:
        disposition = BOUNDED_PREDICTION_TIME_GATE_PASS
        disposition_reasons = ["identity activated and every declared control was a certified null"]

    return {
        "disposition": disposition,
        "comparable": disposition != NOT_COMPARABLE,
        "paired_gate_passed": disposition == BOUNDED_PREDICTION_TIME_GATE_PASS,
        "relative_advantage_passed": relative_advantage_passed,
        "specificity_claimed": False,
        "identity_arm_id": identity["arm_id"],
        "identity_delta_from_null": identity_objective["delta_from_null"],
        "identity_improvement_from_null": identity_improvement,
        "strongest_control_arm_id": strongest_control["arm_id"],
        "strongest_control_delta_from_null": strongest_control["delta_from_null"],
        "strongest_control_improvement_from_null": strongest_control_improvement,
        "identity_advantage_over_strongest_control_cost": paired_advantage,
        "minimum_advantage_cost": minimum_advantage_cost,
        "comparison_is_strict": True,
        "activating_control_arm_ids": list(activating_controls),
        "all_declared_control_nulls_certified": certified_control_nulls,
        "advantage_threshold_calibrated": advantage_threshold_calibrated,
        "external_preregistration_verified": external_preregistration_verified,
        "controls": control_rows,
        "reasons": disposition_reasons,
    }


def _validate_window_coverage(
    contexts: tuple[multipath._PathContext, ...],
    *,
    start_utc_ns: int,
    end_utc_ns: int,
) -> None:
    for context in contexts:
        timing = context.dataset["timing_binding"]
        capture = context.dataset["capture"]
        first = int(timing["first_estimate_utc_ns"])
        last = int(timing["last_estimate_utc_ns"])
        sample_period_ns = round(1e9 / int(capture["sample_rate_hz"]))
        if start_utc_ns < first or end_utc_ns > last + sample_period_ns:
            raise ValueError("paired UTC window is not contained in every path")
        if any(
            item.estimate_utc_ns < start_utc_ns or item.estimate_utc_ns >= end_utc_ns
            for item in context.probe_utc
        ):
            raise ValueError("path probe selection disagrees with the paired UTC window")
        if context.inventory.returned_candidate_count != context.inventory.source_candidate_count:
            raise ValueError("paired replay refuses a truncated candidate inventory")


def replay_raw_multipath_paired_prediction_time(
    *,
    dataset_paths: tuple[Path, ...],
    expected_dataset_digests: tuple[str, ...],
    calibration_document: dict[str, Any],
    calibration_path: Path,
    expected_calibration_digest: str,
    tle_path: Path,
    expected_tle_digest: str,
    catalog_numbers: tuple[int, ...],
    start_utc_ns: int,
    end_utc_ns: int,
    observer: ObserverSiteV1,
    config: multipath.MultipathReplayConfig,
    control_indices: tuple[int, ...],
    family_label: str,
    minimum_advantage_cost: float = 0.0,
) -> dict[str, Any]:
    """Freeze and evaluate one identity/control family on one loaded problem."""

    _finite_nonnegative(minimum_advantage_cost, "minimum advantage cost")
    if start_utc_ns < 0 or end_utc_ns <= start_utc_ns:
        raise ValueError("paired absolute UTC window must be nonnegative and increasing")
    if start_utc_ns % UTC_CELL_NS or end_utc_ns % UTC_CELL_NS:
        raise ValueError("paired absolute UTC window must align to 100-ms boundaries")
    if (end_utc_ns - start_utc_ns) % 500_000_000:
        raise ValueError("paired absolute UTC window must contain complete 0.5-second blocks")
    if not MINIMUM_CATALOG_COUNT <= len(catalog_numbers) <= MAXIMUM_CATALOG_COUNT:
        raise ValueError(
            f"paired replay requires {MINIMUM_CATALOG_COUNT} to "
            f"{MAXIMUM_CATALOG_COUNT} catalogue objects"
        )
    if len(set(catalog_numbers)) != len(catalog_numbers):
        raise ValueError("paired replay catalogue shortlist contains duplicate identities")

    calibration_digest = _file_digest(calibration_path)
    if calibration_digest != _canonical_sha256(
        expected_calibration_digest,
        "score-calibration digest",
    ):
        raise ValueError("paired score-calibration file digest mismatch")
    if calibration_document != multipath._read_json(calibration_path):
        raise ValueError("score-calibration document differs from its digest-bound file")
    if calibration_document.get("schema") != raw_replay.CALIBRATION_SCHEMA_V3:
        raise ValueError("paired replay requires raw V3 resolution-group calibration")
    raw_replay._validate_calibration_grouping(calibration_document, config)
    calibration = raw_replay._score(calibration_document)
    if not calibration.weak_match_is_dominated_by_miss():
        raise ValueError("score calibration does not make weak candidates miss-dominated")

    tle_digest = _file_digest(tle_path)
    if tle_digest != _canonical_sha256(expected_tle_digest, "TLE digest"):
        raise ValueError("paired TLE file digest mismatch")
    catalogue = parse_element_sets(tle_path.read_text(encoding="utf-8"))
    if len(set(catalogue.satellite_numbers)) != len(catalogue):
        raise ValueError("paired TLE catalogue contains duplicate NORAD identities")
    ordered_catalog_numbers = tuple(sorted(catalog_numbers))
    catalog_indices = tuple(
        multipath._unique_satellite_index(catalogue, catalog_number)
        for catalog_number in ordered_catalog_numbers
    )

    # This is the sole raw path-context load.  Every arm below receives these
    # same objects and the one decision problem constructed from them.
    contexts = multipath._load_path_contexts(
        dataset_paths=dataset_paths,
        expected_dataset_digests=expected_dataset_digests,
        calibration=calibration,
        calibration_document=calibration_document,
        start_utc_ns=start_utc_ns,
        end_utc_ns=end_utc_ns,
        config=config,
    )
    _validate_window_coverage(
        contexts,
        start_utc_ns=start_utc_ns,
        end_utc_ns=end_utc_ns,
    )
    problem = multipath._multipath_problem(
        contexts,
        start_utc_ns=start_utc_ns,
        end_utc_ns=end_utc_ns,
        config=config,
    )

    raw_problem = _raw_problem_payload(contexts, problem)
    raw_problem_digest = canonical_digest(raw_problem)
    objective = _objective_payload(
        problem=problem,
        calibration_document=calibration_document,
        calibration_digest=calibration_digest,
        config=config,
    )
    objective_digest = canonical_digest(objective)
    search_universe = _search_universe_payload(
        catalogue=catalogue,
        catalog_indices=catalog_indices,
        contexts=contexts,
        problem=problem,
        observer=observer,
        config=config,
        tle_digest=tle_digest,
    )
    search_universe_digest = canonical_digest(search_universe)
    producer = {
        "algorithm": ALGORITHM,
        "implementation_file_digests": _implementation_file_digests(),
        "runtime_versions": multipath._runtime_versions(),
    }
    producer_digest = canonical_digest(producer)
    ordered_control_indices = tuple(sorted(control_indices))
    selection_context = _selection_context(
        family_label=family_label,
        contexts=contexts,
        problem=problem,
        raw_problem_digest=raw_problem_digest,
        objective_digest=objective_digest,
        search_universe_digest=search_universe_digest,
        producer_digest=producer_digest,
        control_indices=ordered_control_indices,
        minimum_advantage_cost=minimum_advantage_cost,
    )
    selection_context_digest = canonical_digest(selection_context)
    transforms = _freeze_arm_transforms(
        problem=problem,
        selection_context_digest=selection_context_digest,
        control_indices=ordered_control_indices,
        maximum_delay_support_s=max(abs(config.delay_min_s), abs(config.delay_max_s)),
    )
    family_plan = {
        **selection_context,
        "arms": [
            {
                "arm_id": item.arm_id,
                "role": item.role,
                "transform_digest": item.transform_digest,
                "transform": item.receipt,
            }
            for item in transforms
        ],
        "family_frozen_before_arm_scoring": True,
        "all_control_plans_built_before_arm_scoring": True,
    }
    family_plan_digest = canonical_digest(family_plan)
    common_digests = {
        "raw_problem_digest": raw_problem_digest,
        "objective_digest": objective_digest,
        "search_universe_digest": search_universe_digest,
        "producer_digest": producer_digest,
        "family_plan_digest": family_plan_digest,
    }
    common = {
        "digests": common_digests,
        "raw_problem": raw_problem,
        "objective": objective,
        "search_universe": search_universe,
        "producer": producer,
        "family_plan": family_plan,
    }

    evaluations = tuple(
        _evaluate_arm(
            transform=transform,
            catalogue=catalogue,
            catalog_indices=catalog_indices,
            contexts=contexts,
            problem=problem,
            calibration=calibration,
            observer=observer,
            config=config,
            common_digests=common_digests,
            grid_start_utc_ns=start_utc_ns,
        )
        for transform in transforms
    )
    if canonical_digest(_raw_problem_payload(contexts, problem)) != raw_problem_digest:
        raise RuntimeError("shared raw problem changed while paired arms were evaluated")
    arm_documents = tuple(item.document for item in evaluations)
    adjudication = adjudicate_paired_arms(
        arms=arm_documents,
        common=common,
        minimum_advantage_cost=minimum_advantage_cost,
        advantage_threshold_calibrated=False,
        external_preregistration_verified=False,
    )
    inventory_cap_saturated = any(
        context.inventory.saturated_probe_count > 0 for context in contexts
    )
    return {
        "schema": OUTPUT_SCHEMA,
        "algorithm": ALGORITHM,
        "research_only": True,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "conditional_prediction_time_specificity_test": True,
        "signal_absence_control": False,
        "raw_presence_false_positive_rate_estimated": False,
        "catalogue_search_performed": False,
        "conditional_on_explicit_frozen_catalogue_shortlist": True,
        "all_arms_share_one_loaded_raw_problem": True,
        "all_arms_share_one_objective": True,
        "all_arms_share_one_search_universe": True,
        "only_prediction_epoch_mapping_varies_between_arms": True,
        "family_frozen_before_arm_scoring": True,
        "all_declared_arms_emitted": True,
        "global_optimum_claimed": False,
        "structural_costs_calibrated": False,
        "detector_score_costs_empirically_calibrated": False,
        "pre_acquisition_cap_inventory_complete": False,
        "physical_signal_inventory_complete": False,
        "retained_candidate_cap_saturation_observed": inventory_cap_saturated,
        "common": common,
        "input": {
            "session_id": contexts[0].dataset["capture"]["session_id"],
            "recording_manifest_digest": contexts[0].dataset["capture"][
                "recording_manifest_digest"
            ],
            "duration_inputs": [
                {
                    "path_id": item.path_id,
                    "path": str(item.dataset_path),
                    "file_digest": item.dataset_digest,
                    "pilot_scan_path": str(item.inventory.scan_path),
                    "pilot_scan_digest": item.inventory.scan_digest,
                    "pilot_scan_content_digest": item.scan_content_digest,
                }
                for item in contexts
            ],
            "score_calibration_path": str(calibration_path.resolve()),
            "score_calibration_digest": calibration_digest,
            "tle_path": str(tle_path.resolve()),
            "tle_digest": tle_digest,
        },
        "window": {
            "start_utc_ns": start_utc_ns,
            "end_utc_ns": end_utc_ns,
            "cell_duration_s": config.cell_duration_s,
            "cell_count": problem.grid.cell_count,
            "minimum_active_duration_s": config.minimum_active_duration_s,
            "minimum_active_cells": config.minimum_active_cells,
            "probe_epoch": "persisted_probe_start_utc_estimate",
        },
        "arms": list(arm_documents),
        "adjudication": adjudication,
        "caveats": [
            "conditional on one explicit catalogue shortlist; no catalogue search was run",
            (
                "the discrete delay grid and data-proposed CFO modes do not exhaust their "
                "continuous parameter spaces"
            ),
            (
                "a nonactivating control is certified only when every generated exact "
                "single state is null and the declared path-offset Cartesian is exhausted"
            ),
            (
                "multiple controls from one captured session are dependent and count as one "
                "session replicate"
            ),
            (
                "the strongest control is used familywise; control counts are not a p-value "
                "or false-positive-rate estimate"
            ),
            (
                "atomic in-process freezing prevents arm omission inside this run but does "
                "not verify external preregistration or prevent rerunning another family"
            ),
            (
                "post-acquisition raw inventories declare no truncation, but upstream caps "
                "can saturate and no physical inventory completeness is claimed"
            ),
            "TLE bytes are digest-bound but snapshot acquisition causality is not verified",
            "observer coordinates are explicit but not capture-bound authority",
            "structural objective costs and the paired advantage threshold are uncalibrated",
            "a bounded prediction-time result is not catalogue identity or satellite tracking",
            "no payload was decoded",
        ],
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--input-sha256", action="append", required=True)
    parser.add_argument("--score-calibration", type=Path, required=True)
    parser.add_argument("--score-calibration-sha256", required=True)
    parser.add_argument("--tle", type=Path, required=True)
    parser.add_argument("--tle-sha256", required=True)
    parser.add_argument("--catalog-number", action="append", type=int, required=True)
    parser.add_argument("--window-start-utc-ns", type=int, required=True)
    parser.add_argument("--window-end-utc-ns", type=int, required=True)
    parser.add_argument("--observer-latitude-deg", type=float, required=True)
    parser.add_argument("--observer-longitude-deg", type=float, required=True)
    parser.add_argument("--observer-altitude-m", type=float, required=True)
    parser.add_argument("--observer-label", required=True)
    parser.add_argument("--family-label", required=True)
    parser.add_argument("--control-index", action="append", type=int, required=True)
    parser.add_argument("--minimum-advantage-cost", type=float, default=0.0)
    parser.add_argument("--minimum-active-duration-s", type=float, default=0.5)
    parser.add_argument("--cfo-sigma-hz", type=float, default=100.0)
    parser.add_argument("--satellite-cost", type=float, default=5.25)
    parser.add_argument("--episode-cost", type=float, default=5.75)
    parser.add_argument("--huber-threshold", type=float, default=1.345)
    parser.add_argument("--delay-min-s", type=float, default=-2.0)
    parser.add_argument("--delay-max-s", type=float, default=2.0)
    parser.add_argument("--delay-step-s", type=float, default=0.1)
    parser.add_argument("--delay-prior-mean-s", type=float, default=0.0)
    parser.add_argument("--delay-prior-sigma-s", type=float, default=0.5)
    parser.add_argument("--duplicate-cfo-tolerance-hz", type=float, default=0.0)
    parser.add_argument("--resolution-epoch-tolerance-samples", type=int, default=1)
    parser.add_argument(
        "--resolution-tracking-cfo-tolerance-hz",
        type=float,
        default=500.0,
    )
    parser.add_argument("--mode-bin-hz", type=float, default=100.0)
    parser.add_argument("--mode-half-width-hz", type=float, default=300.0)
    parser.add_argument("--modes-per-delay", type=int, default=2)
    parser.add_argument("--retained-states-per-catalog", type=int, default=4)
    parser.add_argument("--maximum-state-combinations", type=int, default=256)
    parser.add_argument(
        "--maximum-path-offset-combinations-per-delay",
        type=int,
        default=64,
    )
    parser.add_argument("--horizon-mask-deg", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    config = multipath.MultipathReplayConfig(
        minimum_active_duration_s=arguments.minimum_active_duration_s,
        cfo_sigma_hz=arguments.cfo_sigma_hz,
        satellite_cost=arguments.satellite_cost,
        episode_cost=arguments.episode_cost,
        huber_threshold=arguments.huber_threshold,
        delay_min_s=arguments.delay_min_s,
        delay_max_s=arguments.delay_max_s,
        delay_step_s=arguments.delay_step_s,
        delay_prior_mean_s=arguments.delay_prior_mean_s,
        delay_prior_sigma_s=arguments.delay_prior_sigma_s,
        duplicate_cfo_tolerance_hz=arguments.duplicate_cfo_tolerance_hz,
        resolution_epoch_tolerance_samples=(arguments.resolution_epoch_tolerance_samples),
        resolution_tracking_cfo_tolerance_hz=(arguments.resolution_tracking_cfo_tolerance_hz),
        mode_bin_hz=arguments.mode_bin_hz,
        mode_half_width_hz=arguments.mode_half_width_hz,
        modes_per_delay=arguments.modes_per_delay,
        retained_states_per_catalog=arguments.retained_states_per_catalog,
        maximum_state_combinations=arguments.maximum_state_combinations,
        maximum_path_offset_combinations_per_delay=(
            arguments.maximum_path_offset_combinations_per_delay
        ),
        horizon_mask_deg=arguments.horizon_mask_deg,
    )
    document = replay_raw_multipath_paired_prediction_time(
        dataset_paths=tuple(arguments.input),
        expected_dataset_digests=tuple(arguments.input_sha256),
        calibration_document=multipath._read_json(arguments.score_calibration),
        calibration_path=arguments.score_calibration,
        expected_calibration_digest=arguments.score_calibration_sha256,
        tle_path=arguments.tle,
        expected_tle_digest=arguments.tle_sha256,
        catalog_numbers=tuple(arguments.catalog_number),
        start_utc_ns=arguments.window_start_utc_ns,
        end_utc_ns=arguments.window_end_utc_ns,
        observer=ObserverSiteV1(
            latitude_deg=arguments.observer_latitude_deg,
            longitude_deg=arguments.observer_longitude_deg,
            altitude_m=arguments.observer_altitude_m,
            label=arguments.observer_label,
        ),
        config=config,
        control_indices=tuple(arguments.control_index),
        family_label=arguments.family_label,
        minimum_advantage_cost=arguments.minimum_advantage_cost,
    )
    rendered = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        multipath._refuse_qnap_output(arguments.output)
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
