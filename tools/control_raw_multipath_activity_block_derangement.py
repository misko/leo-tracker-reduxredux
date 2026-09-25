#!/usr/bin/env python3
"""Apply one session-wide block derangement to raw multipath catalogue predictions.

This Research-only adapter keeps every persisted RF probe, candidate bundle,
usability flag, exclusion group, and score cost fixed.  It changes only the
absolute UTC epochs at which TLE predictions are evaluated.  One deterministic
half-second block plan is shared by every receiver path, catalogue object,
delay, and CFO-offset state in the run.

The full eligible named catalogue is screened on a coarse delay/CFO-mode bank,
a deterministic shortlist is refined, and the retained shortlist states are
decoded exactly.  Catalogue pruning and data-proposed CFO modes make the
overall search heuristic.  This is a conditional prediction-time specificity
control, not a signal-absence control and not an estimate of a raw presence
false-positive rate.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from leo.analysis.research.activity_block_derangement import (  # type: ignore[import-untyped]
    ActivityBlockDerangement,
    build_activity_block_derangement,
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
from tools import screen_raw_satellite_activity_catalog as catalogue_screen  # noqa: E402
from tools.raw_satellite_activity_search_configuration import (  # noqa: E402
    CatalogueScreenConfig,
)

OUTPUT_SCHEMA = "org.leo.research.raw-multipath-block-derangement-control/v1"
ALGORITHM = "heuristic-catalogue-raw-multipath-block-derangement-control-v1"
FIXED_STATE_ALGORITHM = "bounded-exact-fixed-nuisance-joint-multipath-semimarkov-v2"
UTC_CELL_NS = 100_000_000
BLOCK_NS = 500_000_000

ACTIVATION_DISCRIMINATOR = "deranged_prediction_activity_witness"
RETAINED_NULL_DISCRIMINATOR = "conditional_deranged_null_over_retained_state_bank"
PREFIX_NULL_DISCRIMINATOR = "conditional_deranged_null_over_evaluated_state_prefix"

_IMPLEMENTATION_FILE_PATHS = (
    "tools/control_raw_multipath_activity_block_derangement.py",
    "tools/replay_raw_multipath_satellite_activity.py",
    "tools/replay_raw_grouped_satellite_activity.py",
    "tools/replay_joint_fixed_satellite_activity.py",
    "tools/screen_raw_satellite_activity_catalog.py",
    "tools/raw_satellite_activity_search_configuration.py",
    "src/leo/analysis/research/activity_block_derangement.py",
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
class _PathPredictionBank:
    path_id: str
    bank: catalogue_screen.CataloguePredictionBank
    mapped_prediction_utc_ns_by_probe_id: dict[str, int]


@dataclass(frozen=True, slots=True)
class _CatalogScore:
    catalogue_index: int
    catalog_number: int
    object_name: str
    bank: multipath._CatalogBank

    @property
    def best(self) -> multipath._StateEvaluation:
        return self.bank.generated[0]


def _implementation_file_digests() -> dict[str, str]:
    return {
        relative_path: multipath._file_digest(REPOSITORY_ROOT / relative_path)
        for relative_path in _IMPLEMENTATION_FILE_PATHS
    }


def _maximum_delay_support_s(config: multipath.MultipathReplayConfig) -> float:
    return max(abs(config.delay_min_s), abs(config.delay_max_s))


def _session_plan_selection_context(
    *,
    contexts: tuple[multipath._PathContext, ...],
    problem: MultipathSatelliteActivityProblem,
    start_utc_ns: int,
    end_utc_ns: int,
    control_label: str,
) -> dict[str, Any]:
    if not isinstance(control_label, str) or not control_label:
        raise ValueError("block-derangement control label must be nonempty")
    return {
        "algorithm": ALGORITHM,
        "control_label": control_label,
        "session_id": contexts[0].dataset["capture"]["session_id"],
        "recording_manifest_digest": contexts[0].dataset["capture"]["recording_manifest_digest"],
        "window": {
            "start_utc_ns": start_utc_ns,
            "end_utc_ns": end_utc_ns,
            "cell_duration_ns": UTC_CELL_NS,
            "cell_count": problem.grid.cell_count,
        },
        "duration_inputs": [
            {
                "path_id": context.path_id,
                "duration_input_digest": context.dataset_digest,
                "pilot_scan_digest": context.inventory.scan_digest,
                "pilot_scan_content_digest": context.scan_content_digest,
            }
            for context in contexts
        ],
    }


def build_session_derangement(
    *,
    problem: MultipathSatelliteActivityProblem,
    selection_context: dict[str, Any],
    maximum_delay_support_s: float,
    minimum_circular_displacement_blocks: int,
) -> tuple[ActivityBlockDerangement, dict[str, Any]]:
    """Build and serialize the one plan used by a complete control run."""

    selection_context_digest = canonical_digest(selection_context)
    plan = build_activity_block_derangement(
        problem.grid,
        session_key=selection_context_digest,
        maximum_delay_support_s=maximum_delay_support_s,
        minimum_circular_displacement_blocks=minimum_circular_displacement_blocks,
    )
    receipt = {
        "algorithm_version": plan.algorithm_version,
        "ranking_version": plan.ranking_version,
        "selection_context": selection_context,
        "selection_context_digest": selection_context_digest,
        "session_key_digest": plan.session_key_digest,
        "plan_digest": plan.plan_digest,
        "block_duration_s": plan.block_duration_s,
        "block_cells": plan.block_cells,
        "block_count": plan.block_count,
        "maximum_delay_support_s": plan.maximum_delay_support_s,
        "minimum_circular_displacement_blocks": (plan.minimum_circular_displacement_blocks),
        "minimum_circular_displacement_s": plan.minimum_circular_displacement_s,
        "realized_minimum_circular_displacement_blocks": (
            plan.realized_minimum_circular_displacement_blocks
        ),
        "realized_minimum_circular_displacement_s": (
            plan.realized_minimum_circular_displacement_blocks * plan.block_duration_s
        ),
        "displacement_strictly_exceeds_delay_support": (
            plan.minimum_circular_displacement_s > plan.maximum_delay_support_s
        ),
        "realized_displacement_strictly_exceeds_delay_support": (
            plan.realized_minimum_circular_displacement_blocks * plan.block_duration_s
            > plan.maximum_delay_support_s
        ),
        "affine_multiplier": plan.affine_multiplier,
        "affine_offset": plan.affine_offset,
        "forward_block_adjacency_broken": plan.forward_block_adjacency_broken,
        "prediction_block_by_observation_block": list(plan.prediction_block_by_observation_block),
        "same_plan_for_all_receiver_paths": True,
        "same_plan_for_all_catalogue_hypotheses": True,
        "observation_inventory_modified": False,
        "tle_prediction_epochs_modified": True,
    }
    if not (
        receipt["displacement_strictly_exceeds_delay_support"]
        and receipt["realized_displacement_strictly_exceeds_delay_support"]
    ):
        raise RuntimeError("derangement displacement does not exceed delay support")
    return plan, receipt


def _prediction_cell_mapping(
    plan: ActivityBlockDerangement,
    path: Any,
    *,
    grid_start_utc_ns: int,
    observation_utc_ns_by_probe_id: dict[str, int],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Map prediction epochs exactly in integer UTC while leaving probes untouched."""

    if grid_start_utc_ns % UTC_CELL_NS:
        raise ValueError("integer derangement grid start must align to 100 ms")
    if not math.isclose(
        plan.grid.start_s,
        grid_start_utc_ns / 1e9,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise ValueError("integer derangement grid start disagrees with activity grid")
    mapped: dict[str, int] = {}
    rows = []
    if set(observation_utc_ns_by_probe_id) != {probe.probe_id for probe in path.probes}:
        raise ValueError("persisted UTC binding differs from the path probe inventory")
    for probe in path.probes:
        observation_utc_ns = observation_utc_ns_by_probe_id[probe.probe_id]
        if not math.isclose(
            probe.time_s,
            observation_utc_ns / 1e9,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("path probe float time disagrees with persisted UTC binding")
        observation_cell_start_utc_ns = grid_start_utc_ns + probe.cell_index * UTC_CELL_NS
        within_cell_offset_ns = observation_utc_ns - observation_cell_start_utc_ns
        if not 0 <= within_cell_offset_ns < UTC_CELL_NS:
            raise ValueError("probe UTC lies outside its declared derangement cell")
        prediction_cell = plan.prediction_cell_for_observation_cell(probe.cell_index)
        prediction_utc_ns = (
            grid_start_utc_ns + prediction_cell * UTC_CELL_NS + within_cell_offset_ns
        )
        mapped[probe.probe_id] = prediction_utc_ns
        rows.append(
            {
                "probe_id": probe.probe_id,
                "observation_utc_ns": observation_utc_ns,
                "observation_cell_index": probe.cell_index,
                "prediction_utc_ns": prediction_utc_ns,
                "prediction_cell_index": prediction_cell,
                "within_cell_offset_ns": within_cell_offset_ns,
            }
        )
    return mapped, rows


def _observation_inventory_payload(context: multipath._PathContext, path: Any) -> dict[str, Any]:
    return {
        "path_id": context.path_id,
        "probes": [asdict(item) for item in path.probes],
        "persisted_probe_utc": [asdict(item) for item in context.probe_utc],
        "modeled_candidates": [asdict(item) for item in path.observations],
        "raw_candidate_bundles": [asdict(item) for item in context.inventory.observations],
        "source_candidate_count": context.inventory.source_candidate_count,
        "returned_candidate_count": context.inventory.returned_candidate_count,
        "truncated_candidate_count": 0,
        "probe_count_at_retained_candidate_cap": context.inventory.saturated_probe_count,
        "elided_clutter_constant": context.inventory.elided_clutter_constant,
    }


def _mapping_receipts(
    plan: ActivityBlockDerangement,
    mappings: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], str]:
    receipts = []
    for path_id in sorted(mappings):
        payload = {
            "path_id": path_id,
            "plan_digest": plan.plan_digest,
            "mapping": mappings[path_id],
        }
        receipts.append(
            {
                **payload,
                "probe_count": len(mappings[path_id]),
                "mapping_digest": canonical_digest(payload),
            }
        )
    return receipts, canonical_digest(receipts)


def _unchanged_observation_accounting(
    contexts: tuple[multipath._PathContext, ...],
    problem: MultipathSatelliteActivityProblem,
) -> dict[str, Any]:
    context_by_path = {item.path_id: item for item in contexts}
    paths = []
    for path in problem.paths:
        payload = _observation_inventory_payload(context_by_path[path.path_id], path)
        digest = canonical_digest(payload)
        paths.append(
            {
                "path_id": path.path_id,
                "before_control_digest": digest,
                "after_control_digest": digest,
                "unchanged": True,
                "scheduled_probe_count": len(path.probes),
                "usable_probe_count": sum(item.usable for item in path.probes),
                "modeled_candidate_count": len(path.observations),
                "raw_candidate_bundle_count": len(
                    context_by_path[path.path_id].inventory.observations
                ),
                "truncated_candidate_count": 0,
                "declared_post_acquisition_inventory_complete": True,
                "pre_acquisition_cap_inventory_complete": False,
                "probe_count_at_retained_candidate_cap": context_by_path[
                    path.path_id
                ].inventory.saturated_probe_count,
            }
        )
    return {
        "observations_unchanged": True,
        "candidate_bundles_unchanged": True,
        "probe_utc_and_cell_assignments_unchanged": True,
        "probe_usability_unchanged": True,
        "exclusion_groups_unchanged": True,
        "score_costs_unchanged": True,
        "paths": paths,
        "combined_inventory_digest": canonical_digest(paths),
    }


def _inventory_cap_accounting(
    contexts: tuple[multipath._PathContext, ...],
) -> dict[str, Any]:
    """Disclose persisted detector caps without claiming physical completeness."""

    paths = []
    for context in contexts:
        if multipath._file_digest(context.inventory.scan_path) != context.inventory.scan_digest:
            raise RuntimeError("raw scan bytes changed after path-context validation")
        scan = multipath._read_json(context.inventory.scan_path)
        raw_cap = scan.get("maximum_scored_candidates_per_probe")
        cap = (
            raw_cap
            if isinstance(raw_cap, int) and not isinstance(raw_cap, bool) and raw_cap > 0
            else None
        )
        actual_maximum = max(
            (item.retained_candidate_count for item in context.probe_utc),
            default=0,
        )
        probes_at_cap = context.inventory.saturated_probe_count
        if cap is not None:
            derived_probes_at_cap = sum(
                item.retained_candidate_count == cap for item in context.probe_utc
            )
            if derived_probes_at_cap != probes_at_cap:
                raise RuntimeError("persisted probe cap accounting disagrees with the raw scan")
        truncated_count = (
            context.inventory.source_candidate_count - context.inventory.returned_candidate_count
        )
        if truncated_count != 0:
            raise RuntimeError("validated raw inventory unexpectedly declares truncation")
        paths.append(
            {
                "path_id": context.path_id,
                "maximum_scored_candidates_per_probe": cap,
                "actual_maximum_returned_candidates_per_probe": actual_maximum,
                "probe_count_at_retained_candidate_cap": probes_at_cap,
                "declared_post_acquisition_truncated_candidate_count": truncated_count,
                "declared_post_acquisition_inventory_complete": True,
                # A zero saturation count only establishes that the persisted rows do not
                # visibly hit this declared cap.  It is not pre-cap or physical authority.
                "pre_acquisition_cap_inventory_complete": False,
                "pre_acquisition_cap_saturation_observed": probes_at_cap > 0,
                "physical_signal_inventory_complete": False,
            }
        )
    cap_values = sorted({item["maximum_scored_candidates_per_probe"] for item in paths} - {None})
    uniform_cap = cap_values[0] if len(cap_values) == 1 and len(paths) > 0 else None
    return {
        "maximum_scored_candidates_per_probe": uniform_cap,
        "maximum_scored_candidates_per_probe_values": cap_values,
        "all_paths_declare_the_same_scored_candidate_cap": (
            len(cap_values) == 1
            and all(item["maximum_scored_candidates_per_probe"] is not None for item in paths)
        ),
        "actual_maximum_returned_candidates_per_probe": max(
            (item["actual_maximum_returned_candidates_per_probe"] for item in paths),
            default=0,
        ),
        "probe_count_at_retained_candidate_cap": sum(
            item["probe_count_at_retained_candidate_cap"] for item in paths
        ),
        "declared_post_acquisition_truncated_candidate_count": sum(
            item["declared_post_acquisition_truncated_candidate_count"] for item in paths
        ),
        "declared_post_acquisition_inventory_complete": all(
            item["declared_post_acquisition_inventory_complete"] for item in paths
        ),
        "pre_acquisition_cap_inventory_complete": False,
        "physical_signal_inventory_complete": False,
        "paths": paths,
    }


def _timing_uncertainty_accounting(
    contexts: tuple[multipath._PathContext, ...],
    *,
    start_utc_ns: int,
) -> dict[str, Any]:
    """Count timing intervals spanning a derangement block boundary."""

    paths = []
    for context in contexts:
        crossing = sum(
            (item.earliest_utc_ns - start_utc_ns) // BLOCK_NS
            != (item.latest_utc_ns - start_utc_ns) // BLOCK_NS
            for item in context.probe_utc
        )
        paths.append(
            {
                "path_id": context.path_id,
                "probe_count": len(context.probe_utc),
                "timing_interval_crosses_derangement_block_boundary_count": crossing,
            }
        )
    return {
        "prediction_epoch_authority": "persisted_probe_start_utc_point_estimate",
        "prediction_epochs_use_point_estimates": True,
        "timing_intervals_used_to_marginalize_predictions": False,
        "derangement_block_duration_ns": BLOCK_NS,
        "derangement_block_origin_utc_ns": start_utc_ns,
        "timing_interval_crosses_derangement_block_boundary_count": sum(
            item["timing_interval_crosses_derangement_block_boundary_count"] for item in paths
        ),
        "paths": paths,
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
            raise ValueError("absolute UTC control window is not contained in every path")
        if any(
            item.estimate_utc_ns < start_utc_ns or item.estimate_utc_ns >= end_utc_ns
            for item in context.probe_utc
        ):
            raise ValueError("path probe selection disagrees with the common UTC window")
        if context.inventory.returned_candidate_count != context.inventory.source_candidate_count:
            raise ValueError("block control refuses a truncated candidate inventory")


def _prediction_banks(
    *,
    catalogue: Any,
    contexts: tuple[multipath._PathContext, ...],
    problem: MultipathSatelliteActivityProblem,
    plan: ActivityBlockDerangement,
    delay_grid: tuple[float, ...],
    observer: ObserverSiteV1,
    config: multipath.MultipathReplayConfig,
    screen_config: CatalogueScreenConfig,
    grid_start_utc_ns: int,
) -> tuple[dict[str, _PathPredictionBank], dict[str, list[dict[str, Any]]]]:
    context_by_path = {item.path_id: item for item in contexts}
    banks: dict[str, _PathPredictionBank] = {}
    mappings: dict[str, list[dict[str, Any]]] = {}
    for path in problem.paths:
        context = context_by_path[path.path_id]
        expected_probe_ids = tuple(item.probe_id for item in context.probe_utc)
        problem_probe_ids = tuple(item.probe_id for item in path.probes)
        if problem_probe_ids != expected_probe_ids:
            raise ValueError("raw inventory probe order disagrees with UTC-bound path order")
        mapped, mapping_rows = _prediction_cell_mapping(
            plan,
            path,
            grid_start_utc_ns=grid_start_utc_ns,
            observation_utc_ns_by_probe_id={
                item.probe_id: item.estimate_utc_ns for item in context.probe_utc
            },
        )
        first_sample_utc_ns = int(context.dataset["timing_binding"]["first_estimate_utc_ns"])
        scheduled_times_s = tuple(
            (mapped[probe.probe_id] - first_sample_utc_ns) / 1e9 for probe in path.probes
        )
        bank = catalogue_screen.build_catalogue_prediction_bank(
            catalogue=catalogue,
            scheduled_times_s=scheduled_times_s,
            first_sample_utc_ns=first_sample_utc_ns,
            delay_grid=delay_grid,
            sky_frequency_hz=float(context.dataset["frequency_binding"]["sky_frequency_hz"]),
            observer=observer,
            horizon_mask_deg=config.horizon_mask_deg,
            name_prefix=screen_config.name_prefix,
            geometry_spacing_s=screen_config.geometry_spacing_s,
        )
        banks[path.path_id] = _PathPredictionBank(path.path_id, bank, mapped)
        mappings[path.path_id] = mapping_rows
    return banks, mappings


def _eligible_catalogue_indices(
    banks: dict[str, _PathPredictionBank],
) -> tuple[int, ...]:
    eligible_sets = [set(item.bank.catalogue_indices) for item in banks.values()]
    if not eligible_sets:
        raise ValueError("catalogue prediction bank has no receiver paths")
    return tuple(sorted(set.intersection(*eligible_sets)))


def _state_bank(
    *,
    catalogue: Any,
    catalogue_index: int,
    path_banks: dict[str, _PathPredictionBank],
    contexts: tuple[multipath._PathContext, ...],
    problem: MultipathSatelliteActivityProblem,
    calibration: raw_replay.ScoreCalibration,
    config: multipath.MultipathReplayConfig,
    plan_digest: str,
) -> multipath._CatalogBank:
    catalog_number = int(catalogue.satellite_numbers[catalogue_index])
    object_name = str(catalogue.names[catalogue_index])
    context_by_path = {item.path_id: item for item in contexts}
    problem_path_by_id = {item.path_id: item for item in problem.paths}
    bank_row_by_path = {
        path_id: item.bank.catalogue_indices.index(catalogue_index)
        for path_id, item in path_banks.items()
    }
    generated: list[multipath._StateEvaluation] = []
    possible_combination_count = 0
    evaluated_combination_count = 0
    exhausted = True
    eligible_by_cell = (True,) * problem.grid.cell_count
    for delay_s in config.delay_grid:
        fixed_by_path = []
        modes_by_path = []
        for path_id in sorted(path_banks):
            path_bank = path_banks[path_id].bank
            row_index = bank_row_by_path[path_id]
            curve = tuple(float(value) for value in path_bank.curve(row_index, delay_s))
            elevation = path_bank.elevation(row_index, delay_s)
            if float(np.min(elevation)) <= config.horizon_mask_deg:
                raise ValueError(
                    f"NORAD {catalog_number} violates the all-path full-window horizon gate"
                )
            modes = raw_replay._offset_modes(
                raw=context_by_path[path_id].inventory.observations,
                base_prediction_hz=np.asarray(curve, dtype=np.float64),
                calibration=calibration,
                config=config,
            )
            fixed_by_path.append(
                (
                    path_id,
                    curve,
                    float(np.min(elevation)),
                    float(np.max(elevation)),
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
                    fixed_by_path, modes, strict=True
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
                    "prediction_epoch": "shared-activity-block-deranged-absolute-utc",
                    "activity_block_derangement_plan_digest": plan_digest,
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
                            for index, probe in enumerate(problem_path_by_id[state.path_id].probes)
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
            exhausted = False
    ordered = tuple(sorted(generated, key=multipath._state_sort_key))
    if not ordered:
        raise RuntimeError(f"NORAD {catalog_number} generated no deranged multipath states")
    return multipath._CatalogBank(
        generated=ordered,
        retained=ordered[: config.retained_states_per_catalog],
        possible_path_offset_combination_count=possible_combination_count,
        evaluated_path_offset_combination_count=evaluated_combination_count,
        path_offset_cartesian_exhausted=exhausted,
    )


def _score_catalogues(
    *,
    catalogue: Any,
    catalogue_indices: tuple[int, ...],
    path_banks: dict[str, _PathPredictionBank],
    contexts: tuple[multipath._PathContext, ...],
    problem: MultipathSatelliteActivityProblem,
    calibration: raw_replay.ScoreCalibration,
    config: multipath.MultipathReplayConfig,
    plan_digest: str,
) -> tuple[_CatalogScore, ...]:
    scored = tuple(
        _CatalogScore(
            catalogue_index=index,
            catalog_number=int(catalogue.satellite_numbers[index]),
            object_name=str(catalogue.names[index]),
            bank=_state_bank(
                catalogue=catalogue,
                catalogue_index=index,
                path_banks=path_banks,
                contexts=contexts,
                problem=problem,
                calibration=calibration,
                config=config,
                plan_digest=plan_digest,
            ),
        )
        for index in catalogue_indices
    )
    return tuple(
        sorted(
            scored,
            key=lambda item: (
                item.best.single_delta_from_null,
                item.catalog_number,
                item.best.hypothesis.hypothesis_id,
            ),
        )
    )


def _refinement_catalogue_indices(
    scores: tuple[_CatalogScore, ...],
    config: CatalogueScreenConfig,
) -> tuple[int, ...]:
    if len(scores) < config.final_catalog_count:
        raise ValueError("too few all-path-visible catalogue objects for the control")
    count = min(config.refinement_catalog_count, len(scores))
    selected = list(scores[:count])
    cutoff = selected[-1].best.single_delta_from_null
    if cutoff < 0.0 and config.refinement_guard_cost > 0.0:
        guarded_cutoff = min(0.0, cutoff + config.refinement_guard_cost)
        selected.extend(
            item
            for item in scores[count:]
            if item.best.single_delta_from_null < 0.0
            and item.best.single_delta_from_null <= guarded_cutoff
        )
    if len(selected) > config.maximum_refinement_catalog_count:
        raise ValueError("coarse score guard band exceeds the refinement hard cap")
    return tuple(item.catalogue_index for item in selected)


def _score_summary(item: _CatalogScore, rank: int) -> dict[str, Any]:
    best = item.best
    return {
        "rank": rank,
        "catalog_number": item.catalog_number,
        "object_name": item.object_name,
        "catalogue_index": item.catalogue_index,
        "generated_fixed_state_count": len(item.bank.generated),
        "best_single_delta_at_zero_satellite_cost": best.single_delta_from_null,
        "activation_satellite_cost_threshold": max(0.0, -best.single_delta_from_null),
        "best_delay_s": best.hypothesis.delay_s,
        "best_path_cfo_offsets_hz": [
            {"path_id": path.path_id, "cfo_offset_hz": path.cfo_offset_hz} for path in best.paths
        ],
        "best_hypothesis_id": best.hypothesis.hypothesis_id,
        "path_offset_cartesian_exhausted": item.bank.path_offset_cartesian_exhausted,
    }


def result_discriminator(*, activation: bool, retained_cartesian_exhausted: bool) -> str:
    if activation:
        return ACTIVATION_DISCRIMINATOR
    if retained_cartesian_exhausted:
        return RETAINED_NULL_DISCRIMINATOR
    return PREFIX_NULL_DISCRIMINATOR


def truth_flags(
    *,
    activation: bool,
    retained_cartesian_exhausted: bool,
    per_catalog_state_banks_pruned: bool,
) -> dict[str, bool]:
    """Centralize deliberately conservative truth flags for tests and output."""

    return {
        "research_only": True,
        "candidate_only": True,
        "specificity_claimed": False,
        "conditional_prediction_time_specificity_control": True,
        "signal_absence_control": False,
        "raw_presence_false_positive_rate_estimated": False,
        "payload_decoded": False,
        "catalogue_search_performed": True,
        "catalogue_search_exact": False,
        "global_optimum_claimed": False,
        "same_derangement_plan_all_paths": True,
        "same_derangement_plan_all_catalogue_hypotheses": True,
        "raw_observations_modified": False,
        "tle_prediction_epochs_modified": True,
        "evaluated_fixed_state_decisions_exact": True,
        "retained_joint_state_space_exhausted": retained_cartesian_exhausted,
        "per_catalog_state_banks_pruned": per_catalog_state_banks_pruned,
        "deranged_activation_witness_found": activation,
        "null_vs_any_activation_solved": activation,
        "unknown_satellite_count_solved": False,
        "correct_time_reference_evaluated_in_this_artifact": False,
    }


def control_raw_multipath_block_derangement(
    *,
    dataset_paths: tuple[Path, ...],
    expected_dataset_digests: tuple[str, ...],
    calibration_document: dict[str, Any],
    calibration_path: Path,
    expected_calibration_digest: str,
    tle_path: Path,
    expected_tle_digest: str,
    start_utc_ns: int,
    end_utc_ns: int,
    observer: ObserverSiteV1,
    config: multipath.MultipathReplayConfig,
    screen_config: CatalogueScreenConfig,
    minimum_circular_displacement_blocks: int,
    control_label: str = "activity-block-derangement-control-0",
) -> dict[str, Any]:
    """Run one provenance-bound, shared-plan, deranged catalogue control."""

    if start_utc_ns < 0 or end_utc_ns <= start_utc_ns:
        raise ValueError("absolute UTC control window must be nonnegative and increasing")
    if start_utc_ns % UTC_CELL_NS or end_utc_ns % UTC_CELL_NS:
        raise ValueError("absolute UTC control window must align to 100-ms epoch boundaries")
    if (end_utc_ns - start_utc_ns) % BLOCK_NS:
        raise ValueError("absolute UTC control window must contain complete 0.5-second blocks")
    calibration_digest = multipath._file_digest(calibration_path)
    if calibration_digest != multipath._canonical_sha256(
        expected_calibration_digest, "score-calibration digest"
    ):
        raise ValueError("score-calibration file digest mismatch")
    if calibration_document != multipath._read_json(calibration_path):
        raise ValueError("score-calibration document does not match its digest-bound file")
    if calibration_document.get("schema") != raw_replay.CALIBRATION_SCHEMA_V3:
        raise ValueError("block control requires raw V3 resolution-group calibration")
    calibration_content_digest = canonical_digest(calibration_document)
    calibration_source_digests = multipath._calibration_source_digests(calibration_document)
    raw_replay._validate_calibration_grouping(calibration_document, config)
    calibration = raw_replay._score(calibration_document)
    if not calibration.weak_match_is_dominated_by_miss():
        raise ValueError("score calibration does not make weak candidates miss-dominated")
    tle_digest = multipath._file_digest(tle_path)
    if tle_digest != multipath._canonical_sha256(expected_tle_digest, "TLE digest"):
        raise ValueError("block-control TLE digest mismatch")
    catalogue = parse_element_sets(tle_path.read_text(encoding="utf-8"))
    if len(set(catalogue.satellite_numbers)) != len(catalogue):
        raise ValueError("catalogue contains duplicate NORAD identities")

    contexts = multipath._load_path_contexts(
        dataset_paths=dataset_paths,
        expected_dataset_digests=expected_dataset_digests,
        calibration=calibration,
        calibration_document=calibration_document,
        start_utc_ns=start_utc_ns,
        end_utc_ns=end_utc_ns,
        config=config,
    )
    _validate_window_coverage(contexts, start_utc_ns=start_utc_ns, end_utc_ns=end_utc_ns)
    problem = multipath._multipath_problem(
        contexts,
        start_utc_ns=start_utc_ns,
        end_utc_ns=end_utc_ns,
        config=config,
    )
    selection_context = _session_plan_selection_context(
        contexts=contexts,
        problem=problem,
        start_utc_ns=start_utc_ns,
        end_utc_ns=end_utc_ns,
        control_label=control_label,
    )
    plan, plan_receipt = build_session_derangement(
        problem=problem,
        selection_context=selection_context,
        maximum_delay_support_s=_maximum_delay_support_s(config),
        minimum_circular_displacement_blocks=minimum_circular_displacement_blocks,
    )
    coarse_delay_grid = catalogue_screen._strict_delay_grid(
        config.delay_min_s,
        config.delay_max_s,
        screen_config.coarse_delay_step_s,
    )
    prediction_delay_grid = tuple(sorted(set(config.delay_grid) | set(coarse_delay_grid)))
    path_banks, path_prediction_mappings = _prediction_banks(
        catalogue=catalogue,
        contexts=contexts,
        problem=problem,
        plan=plan,
        delay_grid=prediction_delay_grid,
        observer=observer,
        config=config,
        screen_config=screen_config,
        grid_start_utc_ns=start_utc_ns,
    )
    mapping_receipts, combined_mapping_digest = _mapping_receipts(
        plan,
        path_prediction_mappings,
    )
    eligible_indices = _eligible_catalogue_indices(path_banks)
    if len(eligible_indices) < screen_config.final_catalog_count:
        raise ValueError("too few all-path-visible catalogue objects after derangement")

    ranking_problem = replace(
        problem,
        costs=replace(problem.costs, satellite_cost=0.0),
    )
    coarse_config = replace(
        config,
        delay_step_s=screen_config.coarse_delay_step_s,
        modes_per_delay=screen_config.coarse_modes_per_delay,
        satellite_cost=0.0,
    )
    coarse_scores = _score_catalogues(
        catalogue=catalogue,
        catalogue_indices=eligible_indices,
        path_banks=path_banks,
        contexts=contexts,
        problem=ranking_problem,
        calibration=calibration,
        config=coarse_config,
        plan_digest=plan.plan_digest,
    )
    refinement_indices = _refinement_catalogue_indices(coarse_scores, screen_config)
    fine_config = replace(config, satellite_cost=0.0)
    fine_scores = _score_catalogues(
        catalogue=catalogue,
        catalogue_indices=refinement_indices,
        path_banks=path_banks,
        contexts=contexts,
        problem=ranking_problem,
        calibration=calibration,
        config=fine_config,
        plan_digest=plan.plan_digest,
    )
    shortlisted_indices = tuple(
        item.catalogue_index for item in fine_scores[: screen_config.final_catalog_count]
    )
    final_scores = _score_catalogues(
        catalogue=catalogue,
        catalogue_indices=shortlisted_indices,
        path_banks=path_banks,
        contexts=contexts,
        problem=problem,
        calibration=calibration,
        config=config,
        plan_digest=plan.plan_digest,
    )
    final_bank_by_catalog = {item.catalog_number: item.bank for item in final_scores}
    ordered_catalog_numbers = tuple(item.catalog_number for item in final_scores)
    possible_joint_combinations = math.prod(
        len(final_bank_by_catalog[item].retained) for item in ordered_catalog_numbers
    )
    joint_evaluations: list[multipath._JointEvaluation] = []
    for states in itertools.islice(
        itertools.product(
            *(final_bank_by_catalog[item].retained for item in ordered_catalog_numbers)
        ),
        config.maximum_state_combinations,
    ):
        hypotheses = tuple(item.hypothesis for item in states)
        joint_evaluations.append(
            multipath._JointEvaluation(
                hypotheses=hypotheses,
                result=decode_joint_fixed_multipath_satellites(problem, hypotheses),
            )
        )
    if not joint_evaluations:
        raise RuntimeError("deranged retained state bank generated no joint combinations")
    joint_evaluations.sort(
        key=lambda item: (
            item.result.objective.total_cost,
            len(item.result.selected_catalog_numbers),
            tuple(hypothesis.hypothesis_id for hypothesis in item.hypotheses),
        )
    )
    best = joint_evaluations[0]
    retained_cartesian_exhausted = len(joint_evaluations) == possible_joint_combinations
    per_catalog_state_banks_pruned = any(
        len(bank.retained) < len(bank.generated) for bank in final_bank_by_catalog.values()
    )
    activation = bool(best.result.selected_catalog_numbers)
    discriminator = result_discriminator(
        activation=activation,
        retained_cartesian_exhausted=retained_cartesian_exhausted,
    )
    flags = truth_flags(
        activation=activation,
        retained_cartesian_exhausted=retained_cartesian_exhausted,
        per_catalog_state_banks_pruned=per_catalog_state_banks_pruned,
    )

    association = asdict(best.result)
    association["selected_catalog_numbers"] = list(best.result.selected_catalog_numbers)
    association["selected_satellite_count"] = len(best.result.selected_catalog_numbers)
    for satellite_document, satellite in zip(
        association["satellites"], best.result.satellites, strict=True
    ):
        satellite_document["latent_activity_support"] = multipath._latent_activity_support(
            satellite, contexts
        )
    elided_constant = math.fsum(item.inventory.elided_clutter_constant for item in contexts)
    inventory_accounting = _unchanged_observation_accounting(contexts, problem)
    inventory_cap_accounting = _inventory_cap_accounting(contexts)
    timing_uncertainty_accounting = _timing_uncertainty_accounting(
        contexts,
        start_utc_ns=start_utc_ns,
    )
    evaluated_scan_digests = {item.inventory.scan_digest for item in contexts}
    if evaluated_scan_digests & calibration_source_digests:
        raise RuntimeError("evaluated pilot scans overlap score-calibration sources")
    calibration_source_exclusion = {
        "evaluated_pilot_scan_file_digests": sorted(evaluated_scan_digests),
        "score_calibration_source_file_digests": sorted(calibration_source_digests),
        "evaluated_scans_disjoint_from_calibration_sources": True,
    }
    implementation_digests = _implementation_file_digests()
    search_configuration = {
        "algorithm": ALGORITHM,
        "output_schema": OUTPUT_SCHEMA,
        "fixed_state_algorithm": FIXED_STATE_ALGORITHM,
        "implementation_file_digests": implementation_digests,
        "runtime_versions": multipath._runtime_versions(),
        "duration_inputs": [
            {
                "path_id": item.path_id,
                "file_digest": item.dataset_digest,
                "pilot_scan_digest": item.inventory.scan_digest,
                "pilot_scan_content_digest": item.scan_content_digest,
                "sky_frequency_hz": float(item.dataset["frequency_binding"]["sky_frequency_hz"]),
            }
            for item in contexts
        ],
        "score_calibration_digest": calibration_digest,
        "score_calibration_content_digest": calibration_content_digest,
        "calibration_source_exclusion_digest": canonical_digest(calibration_source_exclusion),
        "tle_digest": tle_digest,
        "activity_block_derangement_plan_digest": plan.plan_digest,
        "activity_block_derangement_ranking_version": plan.ranking_version,
        "path_probe_prediction_mappings_digest": combined_mapping_digest,
        "unchanged_observation_inventory_digest": inventory_accounting["combined_inventory_digest"],
        "inventory_cap_accounting_digest": canonical_digest(inventory_cap_accounting),
        "timing_uncertainty_accounting_digest": canonical_digest(timing_uncertainty_accounting),
        "window": {
            "start_utc_ns": start_utc_ns,
            "end_utc_ns": end_utc_ns,
            "cell_duration_ns": UTC_CELL_NS,
            "cell_count": problem.grid.cell_count,
        },
        "observer": observer.model_dump(mode="json"),
        "configuration": asdict(config),
        "catalogue_screen_configuration": asdict(screen_config),
    }
    selected_details = multipath._selected_path_details(
        best.result, final_bank_by_catalog, contexts
    )
    cap_by_path = {item["path_id"]: item for item in inventory_cap_accounting["paths"]}
    block_timing_by_path = {
        item["path_id"]: item for item in timing_uncertainty_accounting["paths"]
    }
    path_inventories = []
    for context in contexts:
        serialized = multipath._serialize_inventory(context)
        serialized["candidate_cap_accounting"] = cap_by_path[context.path_id]
        serialized.update(block_timing_by_path[context.path_id])
        path_inventories.append(serialized)
    return {
        "schema": OUTPUT_SCHEMA,
        "algorithm": ALGORITHM,
        "result_discriminator": discriminator,
        **flags,
        "conditional_on_raw_glrt64_inventory": True,
        "conditional_on_full_window_all_path_visibility_screen": True,
        "conditional_on_data_proposed_path_cfo_offsets": True,
        "conditional_on_catalogue_screen_shortlist": True,
        "conditional_on_retained_nuisance_state_bank": True,
        "structural_costs_calibrated": False,
        "detector_score_costs_empirically_calibrated": False,
        "score_costs_use_conservative_v3_rank_mark_bounds": True,
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
            "score_calibration_content_digest": calibration_content_digest,
            "calibration_source_exclusion": calibration_source_exclusion,
            "tle_path": str(tle_path.resolve()),
            "tle_digest": tle_digest,
            "implementation_file_digests": implementation_digests,
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
        "activity_block_derangement": {
            **plan_receipt,
            "path_probe_prediction_mappings_digest": combined_mapping_digest,
            "path_probe_prediction_mappings": mapping_receipts,
        },
        "unchanged_observation_accounting": inventory_accounting,
        "inventory_cap_accounting": inventory_cap_accounting,
        "timing_uncertainty_accounting": timing_uncertainty_accounting,
        "path_inventories": path_inventories,
        "catalogue_search": {
            "exact": False,
            "name_prefix": screen_config.name_prefix,
            "catalogue_object_count": len(catalogue),
            "unique_catalog_number_count": len(set(catalogue.satellite_numbers)),
            "all_path_full_window_visible_catalog_count": len(eligible_indices),
            "per_path_geometry_accounting": [
                {
                    "path_id": path_id,
                    **asdict(path_banks[path_id].bank.accounting),
                }
                for path_id in sorted(path_banks)
            ],
            "coarse_stage": {
                "full_eligible_catalogue_scored": True,
                "delay_grid": list(coarse_delay_grid),
                "modes_per_delay_per_path": screen_config.coarse_modes_per_delay,
                "scored_catalog_count": len(coarse_scores),
                "ranking": [
                    _score_summary(item, rank) for rank, item in enumerate(coarse_scores, start=1)
                ],
            },
            "fine_stage": {
                "delay_grid": list(config.delay_grid),
                "modes_per_delay_per_path": config.modes_per_delay,
                "refined_catalog_count": len(fine_scores),
                "omitted_catalog_count": len(coarse_scores) - len(fine_scores),
                "ranking": [
                    _score_summary(item, rank) for rank, item in enumerate(fine_scores, start=1)
                ],
            },
            "shortlist": {
                "catalog_numbers": [
                    int(catalogue.satellite_numbers[index]) for index in shortlisted_indices
                ],
                "final_catalog_count": len(shortlisted_indices),
                "tie_key": [
                    "best_exact_fixed_state_delta_at_zero_satellite_cost",
                    "catalog_number",
                    "hypothesis_id",
                ],
            },
        },
        "nuisance_state_search": {
            "catalogs": [
                {
                    "catalog_number": catalog_number,
                    "generated_state_count": len(final_bank_by_catalog[catalog_number].generated),
                    "retained_state_count": len(final_bank_by_catalog[catalog_number].retained),
                    "possible_path_offset_combination_count": final_bank_by_catalog[
                        catalog_number
                    ].possible_path_offset_combination_count,
                    "evaluated_path_offset_combination_count": final_bank_by_catalog[
                        catalog_number
                    ].evaluated_path_offset_combination_count,
                    "path_offset_cartesian_exhausted": final_bank_by_catalog[
                        catalog_number
                    ].path_offset_cartesian_exhausted,
                    "states": [
                        multipath._state_document(
                            item,
                            retained=item in final_bank_by_catalog[catalog_number].retained,
                            config=config,
                        )
                        for item in final_bank_by_catalog[catalog_number].generated
                    ],
                }
                for catalog_number in ordered_catalog_numbers
            ],
            "possible_retained_joint_state_combination_count": possible_joint_combinations,
            "evaluated_retained_joint_state_combination_count": len(joint_evaluations),
            "retained_joint_state_space_exhausted": retained_cartesian_exhausted,
            "every_evaluated_fixed_joint_decision_exact": True,
            "evaluations": [
                {
                    "hypothesis_ids": [hypothesis.hypothesis_id for hypothesis in item.hypotheses],
                    "selected_catalog_numbers": list(item.result.selected_catalog_numbers),
                    "total_cost": item.result.objective.total_cost,
                    "delta_from_null": item.result.objective.delta_from_null,
                    "selected_as_best": item is best,
                }
                for item in joint_evaluations
            ],
        },
        "decision": {
            "result_discriminator": discriminator,
            "selected_catalog_numbers": list(best.result.selected_catalog_numbers),
            "selected_satellite_count": len(best.result.selected_catalog_numbers),
            "deranged_activation_witness_found": activation,
            "interpretation": (
                "an activation witness exists under the declared deranged prediction-time search"
                if activation
                else (
                    "no activation was found in the exact retained joint state bank"
                    if retained_cartesian_exhausted
                    else "no activation was found in the evaluated retained-state prefix"
                )
            ),
            "full_persisted_inventory_objective": {
                "null_cost": best.result.objective.null_cost + elided_constant,
                "total_cost": best.result.objective.total_cost + elided_constant,
                "delta_from_null": best.result.objective.delta_from_null,
                "constant_elided_from_exact_decision_problem": elided_constant,
                "persisted_candidate_scope": ("post-acquisition retained candidate inventory"),
                "nuisance_search_scope": ("best evaluated retained bounded state bank or prefix"),
                "physical_inventory_completeness_claimed": False,
            },
        },
        "association": association,
        "path_full_persisted_inventory_objectives": multipath._full_path_objectives(
            best.result, contexts
        ),
        "selected_path_assignment_details": selected_details,
        "observer": {**observer.model_dump(mode="json"), "capture_bound": False},
        "configuration": asdict(config),
        "catalogue_screen_configuration": asdict(screen_config),
        "search_configuration": search_configuration,
        "search_configuration_digest": canonical_digest(search_configuration),
        "caveats": [
            (
                "this is a conditional prediction-time specificity control, not a signal-"
                "absence control and not a raw presence false-positive-rate estimate"
            ),
            (
                "the complete eligible named catalogue is scored only on the coarse grid; "
                "coarse-to-fine pruning can omit the best fine-grid catalogue"
            ),
            (
                "CFO modes are proposed from the unchanged evaluated observations and their "
                "continuous parameter space is not exhausted"
            ),
            (
                "the final joint replay is exact only for each retained fixed nuisance-state "
                "tuple and the evaluated retained Cartesian"
            ),
            (
                "all-path full-window visibility excludes rise/set objects and is conditional "
                "on the explicit observer and horizon mask"
            ),
            (
                "one global half-second block mapping is shared across paths and catalogue "
                "hypotheses; probe offsets inside cells and blocks remain fixed"
            ),
            (
                "prediction epochs use persisted UTC point estimates; earliest/latest timing "
                "intervals that cross a half-second derangement-block boundary are counted "
                "per path but are not marginalized"
            ),
            (
                "the control label and resulting digest-ranked mapping must be frozen before "
                "the deranged result is inspected; labels or mappings must not be retried or "
                "selected for a preferred outcome"
            ),
            (
                "multiple labels or permutations applied to this same captured session remain "
                "one dependent session replicate and cannot be counted or cherry-picked as "
                "independent controls"
            ),
            (
                "derangement displacement is strictly beyond the declared orbital-delay "
                "support, but path CFO offsets can still absorb a constant frequency shift"
            ),
            (
                "a deranged activation weakens prediction-time specificity only conditional "
                "on this inventory, objective, catalogue, and bounded search"
            ),
            (
                "a deranged null is not proof of spacecraft identity and does not establish "
                "signal presence or absence"
            ),
            (
                "post-acquisition candidate inventories declare no truncation, but the "
                "declared scored-candidate cap can saturate; no pre-acquisition or physical "
                "inventory completeness is claimed"
            ),
            (
                "the field named full_persisted_inventory_objective covers the retained "
                "post-acquisition candidate inventory only for the best evaluated bounded "
                "nuisance-state bank or prefix; it is not a full physical-inventory or "
                "global-search objective"
            ),
            "TLE bytes are digest-bound but snapshot acquisition causality is not verified",
            "raw V3 detector-score costs are conservative; structural costs are provisional",
            "observer coordinates are explicit but not capture-bound authority",
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
    parser.add_argument("--window-start-utc-ns", type=int, required=True)
    parser.add_argument("--window-end-utc-ns", type=int, required=True)
    parser.add_argument("--observer-latitude-deg", type=float, required=True)
    parser.add_argument("--observer-longitude-deg", type=float, required=True)
    parser.add_argument("--observer-altitude-m", type=float, required=True)
    parser.add_argument("--observer-label", required=True)
    parser.add_argument("--control-label", default="activity-block-derangement-control-0")
    parser.add_argument("--minimum-circular-displacement-blocks", type=int, default=5)
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
    parser.add_argument("--resolution-tracking-cfo-tolerance-hz", type=float, default=500.0)
    parser.add_argument("--mode-bin-hz", type=float, default=100.0)
    parser.add_argument("--mode-half-width-hz", type=float, default=300.0)
    parser.add_argument("--modes-per-delay", type=int, default=2)
    parser.add_argument("--retained-states-per-catalog", type=int, default=4)
    parser.add_argument("--maximum-state-combinations", type=int, default=256)
    parser.add_argument("--maximum-path-offset-combinations-per-delay", type=int, default=64)
    parser.add_argument("--horizon-mask-deg", type=float, default=0.0)
    parser.add_argument("--catalogue-name-prefix", default="STARLINK")
    parser.add_argument("--geometry-spacing-s", type=float, default=0.5)
    parser.add_argument("--coarse-delay-step-s", type=float, default=0.5)
    parser.add_argument("--coarse-modes-per-delay", type=int, default=1)
    parser.add_argument("--refinement-catalog-count", type=int, default=32)
    parser.add_argument("--refinement-guard-cost", type=float, default=0.0)
    parser.add_argument("--maximum-refinement-catalog-count", type=int, default=64)
    parser.add_argument("--final-catalog-count", type=int, choices=(2, 3), default=3)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if len(arguments.input) != len(arguments.input_sha256):
        parser.error("each --input needs one --input-sha256")
    return arguments


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
        resolution_epoch_tolerance_samples=arguments.resolution_epoch_tolerance_samples,
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
    screen_config = CatalogueScreenConfig(
        name_prefix=arguments.catalogue_name_prefix,
        geometry_spacing_s=arguments.geometry_spacing_s,
        coarse_delay_step_s=arguments.coarse_delay_step_s,
        coarse_modes_per_delay=arguments.coarse_modes_per_delay,
        refinement_catalog_count=arguments.refinement_catalog_count,
        refinement_guard_cost=arguments.refinement_guard_cost,
        maximum_refinement_catalog_count=arguments.maximum_refinement_catalog_count,
        final_catalog_count=arguments.final_catalog_count,
    )
    document = control_raw_multipath_block_derangement(
        dataset_paths=tuple(arguments.input),
        expected_dataset_digests=tuple(arguments.input_sha256),
        calibration_document=multipath._read_json(arguments.score_calibration),
        calibration_path=arguments.score_calibration,
        expected_calibration_digest=arguments.score_calibration_sha256,
        tle_path=arguments.tle,
        expected_tle_digest=arguments.tle_sha256,
        start_utc_ns=arguments.window_start_utc_ns,
        end_utc_ns=arguments.window_end_utc_ns,
        observer=ObserverSiteV1(
            latitude_deg=arguments.observer_latitude_deg,
            longitude_deg=arguments.observer_longitude_deg,
            altitude_m=arguments.observer_altitude_m,
            label=arguments.observer_label,
        ),
        config=config,
        screen_config=screen_config,
        minimum_circular_displacement_blocks=(arguments.minimum_circular_displacement_blocks),
        control_label=arguments.control_label,
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
