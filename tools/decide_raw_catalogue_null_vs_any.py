#!/usr/bin/env python3
"""Decide bounded-exact raw-catalogue null versus any activation.

This tool is intentionally separate from
``screen_raw_satellite_activity_catalog.py``.  The latter is a frozen,
digest-bound coarse-to-fine producer; changing its bytes would invalidate
completed study receipts.  This adapter reuses its stable inventory,
geometry, and per-catalogue scoring helpers but exhausts every eligible
catalogue on the declared fine delay/data-proposed-CFO state bank.

The binary decision does not require a catalogue-scale joint search.  Under
the current additive objective, a feasible joint schedule's delta from the
null is the sum of its per-satellite reduced contributions, and one exclusion
group can be consumed at most once.  The exact single-satellite decoder can
reproduce each such contribution.  Therefore, if every fixed nuisance-state
single-satellite minimum is the null, no finite joint subset can beat it.  A
negative single-satellite minimum is already a feasible activation witness.

Exactness is deliberately limited to the persisted raw inventory, the
full-window-visible catalogue rows, the declared discrete delay grid, and the
generated data-proposed CFO modes.  The output never claims unrestricted
catalogue, continuous-nuisance, or astrophysical exactness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from leo.analysis.research.satellite_activity import (  # type: ignore[import-untyped]
    SatelliteActivityProblem,
    decode_single_satellite,
)
from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools import replay_raw_grouped_satellite_activity as raw_replay  # noqa: E402
from tools import screen_raw_satellite_activity_catalog as screen  # noqa: E402
from tools.raw_satellite_activity_search_configuration import (  # noqa: E402
    build_search_configuration,
)

OUTPUT_SCHEMA = "org.leo.research.raw-catalogue-bounded-null-vs-any/v1"
ALGORITHM = "bounded-exact-all-eligible-fine-null-vs-any-v1"
OUTPUT_SCHEMA_V2 = "org.leo.research.raw-catalogue-bounded-null-vs-any/v2"
ALGORITHM_V2 = "bounded-exact-all-eligible-fine-null-vs-any-identity-partition-v2"
IDENTITY_PARTITION_SCHEMA = "org.leo.research.catalogue-geometry-identity-partition/v1"
IDENTITY_PARTITION_ALGORITHM = "exact-named-full-window-visibility-identity-partition-v1"
SEPARABILITY_PROOF_ALGORITHM = "additive-exclusive-group-single-minimum-proof-v1"
PRODUCER_MANIFEST_ALGORITHM = "bounded-null-vs-any-producer-manifest-v1"
WRAPPER_RELATIVE_PATH = "tools/decide_raw_catalogue_null_vs_any.py"


def producer_implementation_manifest() -> dict[str, Any]:
    """Bind this adapter in addition to the unchanged frozen producer surface."""

    wrapper_path = REPOSITORY_ROOT / WRAPPER_RELATIVE_PATH
    return {
        "algorithm": PRODUCER_MANIFEST_ALGORITHM,
        "wrapper": {
            "path": WRAPPER_RELATIVE_PATH,
            "digest": "sha256:" + hashlib.sha256(wrapper_path.read_bytes()).hexdigest(),
        },
        "imported_catalogue_screen_producer": screen.producer_implementation_manifest(),
    }


def _modeled_null_cost(problem: SatelliteActivityProblem) -> float:
    clutter_by_group: dict[str, float] = {}
    for observation in problem.observations:
        prior = clutter_by_group.setdefault(
            observation.exclusion_group_id,
            observation.clutter_cost,
        )
        if prior != observation.clutter_cost:
            raise RuntimeError("exclusion-group clutter cost changed inside a validated problem")
    return math.fsum(clutter_by_group.values())


def _activation_witness(
    scores: tuple[screen.CatalogScore, ...],
    *,
    eligible_catalog_count: int,
) -> screen.CatalogScore | None:
    """Validate exhaustive minima and return the strongest feasible activation."""

    if len(scores) != eligible_catalog_count:
        raise RuntimeError("bounded binary scan did not score every eligible catalogue")
    if len({item.catalog_number for item in scores}) != len(scores):
        raise RuntimeError("bounded binary scan returned duplicate catalogue identities")
    for item in scores:
        state = item.best_state
        if item.generated_state_count < 1:
            raise RuntimeError("bounded binary scan produced an empty nuisance-state bank")
        if state.single_selected and state.single_delta_from_null >= 0.0:
            raise RuntimeError("selected single-satellite minimum is not below the null")
        if not state.single_selected and state.single_delta_from_null != 0.0:
            raise RuntimeError("nonselected single-satellite minimum does not equal the null")
    return next((item for item in scores if item.best_state.single_selected), None)


def _configured_score_summary(
    item: screen.CatalogScore,
    rank: int,
    *,
    satellite_cost: float,
) -> dict[str, Any]:
    """Serialize a minimum evaluated with the configured, nonzeroable objective."""

    state = item.best_state
    return {
        "rank": rank,
        "catalog_number": item.catalog_number,
        "object_name": item.object_name,
        "catalogue_index": item.catalogue_index,
        "generated_state_count": item.generated_state_count,
        "configured_satellite_cost": satellite_cost,
        "best_single_total_cost": state.single_total_cost,
        "best_single_delta_from_null": state.single_delta_from_null,
        "best_single_selected": state.single_selected,
        "best_delay_s": state.hypothesis.delay_s,
        "best_cfo_offset_hz": state.hypothesis.cfo_offset_hz,
        "delay_prior_cost": state.hypothesis.delay_prior_cost,
        "mode_support_probe_count": state.proposal.support_probe_count,
        "mode_support_group_count": state.proposal.support_group_count,
        "minimum_elevation_deg": state.minimum_elevation_deg,
        "maximum_elevation_deg": state.maximum_elevation_deg,
        "best_hypothesis_id": state.hypothesis.hypothesis_id,
    }


def _search_configuration(
    *,
    calibration_schema: object,
    calibration_digest: str,
    tle_digest: str,
    sky_frequency_hz: float,
    pilot_scan_configuration: dict[str, Any],
    observer: ObserverSiteV1,
    start_s: float,
    end_s: float,
    scheduled_probe_count: int,
    cell_count: int,
    evaluation_scope_digest: str,
    config: raw_replay.RawReplayConfig,
    catalogue_name_prefix: str,
    geometry_spacing_s: float,
    output_schema: str = OUTPUT_SCHEMA,
    algorithm: str = ALGORITHM,
) -> dict[str, Any]:
    configuration = build_search_configuration(
        calibration_schema=calibration_schema,
        calibration_digest=calibration_digest,
        tle_digest=tle_digest,
        sky_frequency_hz=sky_frequency_hz,
        pilot_scan_configuration=pilot_scan_configuration,
        observer_configuration=observer.model_dump(mode="json"),
        window_start_s=start_s,
        window_end_s=end_s,
        scheduled_probe_count=scheduled_probe_count,
        cell_count=cell_count,
        member_evaluation_scope_digest=evaluation_scope_digest,
        producer_implementation=producer_implementation_manifest(),
        raw_replay_configuration=asdict(config),
        catalogue_screen_configuration={
            "algorithm": algorithm,
            "name_prefix": catalogue_name_prefix,
            "geometry_spacing_s": geometry_spacing_s,
            "fine_delay_grid": list(config.delay_grid),
            "modes_per_delay": config.modes_per_delay,
            "full_probe_by_delay_visibility_required": True,
        },
    )
    configuration["state_generation_algorithm"] = configuration["algorithm"]
    configuration["algorithm"] = algorithm
    configuration["output_schema"] = output_schema
    configuration.pop("grouped_replay_algorithm", None)
    configuration["single_satellite_decoder_algorithm"] = "exact-single-satellite-semimarkov-v1"
    configuration["separability_proof_algorithm"] = SEPARABILITY_PROOF_ALGORITHM
    return configuration


def _raw_inventory_document(
    inventory: raw_replay._RawInventory,
    *,
    dataset: dict[str, Any],
    config: raw_replay.RawReplayConfig,
) -> dict[str, Any]:
    return {
        "source_candidate_count": inventory.source_candidate_count,
        "returned_candidate_count": inventory.returned_candidate_count,
        "truncated_candidate_count": inventory.problem.truncated_observation_count,
        "probe_count_at_retained_candidate_cap": inventory.saturated_probe_count,
        "declared_post_acquisition_inventory_complete": (
            inventory.problem.truncated_observation_count == 0
        ),
        "pre_acquisition_cap_inventory_complete": False,
        "exclusion_group_count": inventory.exclusion_group_count,
        "positive_candidate_count_after_group_scoring": inventory.positive_candidate_count,
        "positive_exclusion_group_count": inventory.positive_exclusion_group_count,
        "unsupported_positive_candidate_count": (inventory.unsupported_positive_candidate_count),
        "unsupported_positive_exclusion_group_count": (
            inventory.unsupported_positive_exclusion_group_count
        ),
        "modeled_candidate_count": inventory.problem.returned_observation_count,
        "modeled_exclusion_group_count": inventory.modeled_exclusion_group_count,
        "dominated_weak_candidate_count": inventory.dominated_weak_candidate_count,
        "dominated_weak_exclusion_group_count": (inventory.dominated_weak_exclusion_group_count),
        "dominated_weak_candidate_elision": {
            "applied": True,
            "decision_equivalent_under_nonnegative_residual_loss": True,
            "weak_match_is_dominated_by_miss": True,
            "unsupported_positive_groups_also_elided": True,
            "omitted_clutter_objective_constant": inventory.elided_clutter_constant,
        },
        "physical_exclusion_grouping": {
            "alias_spacing_hz": float(dataset["alias_collapse"]["alias_spacing_hz"]),
            "exact_duplicate_cfo_tolerance_hz": config.duplicate_cfo_tolerance_hz,
            "exact_duplicate_refined_basins_collapsed": True,
            "resolution_epoch_tolerance_samples": config.resolution_epoch_tolerance_samples,
            "resolution_tracking_cfo_tolerance_hz": (config.resolution_tracking_cfo_tolerance_hz),
            "unresolved_measurement_cells_collapsed": True,
            "resolution_cells_are_physical_source_identities": False,
            "nonidentical_integer_aliases_grouped": False,
        },
    }


def _witness_document(
    score: screen.CatalogScore,
    *,
    rank: int,
    problem: SatelliteActivityProblem,
    elided_clutter_constant: float,
) -> tuple[dict[str, Any], dict[str, float]]:
    decoded = decode_single_satellite(problem, score.best_state.hypothesis)
    if not decoded.selected or decoded.objective.delta_from_null >= 0.0:
        raise RuntimeError("reported activation witness does not beat the null")
    if not math.isclose(
        decoded.objective.delta_from_null,
        score.best_state.single_delta_from_null,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise RuntimeError("activation witness disagrees with catalogue-score minimum")
    full_objective = {
        "null_cost": decoded.objective.null_cost + elided_clutter_constant,
        "total_cost": decoded.objective.total_cost + elided_clutter_constant,
        "delta_from_null": decoded.objective.delta_from_null,
        "constant_elided_from_exact_decision_problem": elided_clutter_constant,
    }
    return (
        {
            "catalogue_minimum": _configured_score_summary(
                score,
                rank,
                satellite_cost=problem.costs.satellite_cost,
            ),
            "association_algorithm": decoded.algorithm,
            "association_exact": decoded.exact,
            "hypothesis_id": decoded.hypothesis_id,
            "activity_by_cell": list(decoded.activity_by_cell),
            "episodes": [asdict(item) for item in decoded.episodes],
            "assignments": [asdict(item) for item in decoded.assignments],
            "missed_probe_ids": list(decoded.missed_probe_ids),
            "modeled_objective": asdict(decoded.objective),
            "full_persisted_inventory_objective": full_objective,
        },
        full_objective,
    )


def _identity_partition_document(
    *,
    catalogue: Any,
    bank: Any,
    catalogue_name_prefix: str,
    tle_digest: str,
) -> dict[str, Any]:
    """Serialize an exact identity-level geometry partition for adapter use."""

    prefix = catalogue_name_prefix.strip().upper()
    named_indices = tuple(
        index for index, name in enumerate(catalogue.names) if str(name).upper().startswith(prefix)
    )
    named = tuple(sorted(int(catalogue.satellite_numbers[index]) for index in named_indices))
    eligible = tuple(
        sorted(int(catalogue.satellite_numbers[index]) for index in bank.catalogue_indices)
    )
    if len(set(named)) != len(named) or len(set(eligible)) != len(eligible):
        raise RuntimeError("catalogue geometry identity partition contains duplicate NORADs")
    ineligible = tuple(sorted(set(named) - set(eligible)))
    if set(eligible) - set(named) or tuple(sorted((*eligible, *ineligible))) != named:
        raise RuntimeError("catalogue geometry identity partition does not reconcile")
    accounting = bank.accounting
    if (
        len(named) != accounting.name_selected_count
        or len(eligible) != accounting.eligible_catalog_count
        or len(ineligible) != len(named) - len(eligible)
        or len(catalogue) != accounting.catalogue_object_count
    ):
        raise RuntimeError("catalogue geometry identity partition disagrees with accounting")
    payload = {
        "schema": IDENTITY_PARTITION_SCHEMA,
        "algorithm": IDENTITY_PARTITION_ALGORITHM,
        "tle_digest": tle_digest,
        "catalogue_name_prefix": catalogue_name_prefix,
        "catalogue_object_count": len(catalogue),
        "named_catalog_count": len(named),
        "eligible_catalog_count": len(eligible),
        "named_ineligible_catalog_count": len(ineligible),
        "named_catalog_numbers": list(named),
        "eligible_catalog_numbers": list(eligible),
        "named_ineligible_catalog_numbers": list(ineligible),
        "named_catalog_numbers_digest": canonical_digest(list(named)),
        "eligible_catalog_numbers_digest": canonical_digest(list(eligible)),
        "named_ineligible_catalog_numbers_digest": canonical_digest(list(ineligible)),
        "partition_exhausted": True,
        "partition_pruned": False,
        "eligibility_semantics": "named-and-full-window-visible-over-declared-delay-grid",
    }
    return {**payload, "partition_content_digest": canonical_digest(payload)}


def decide_raw_catalogue_null_vs_any(
    *,
    dataset: dict[str, Any],
    dataset_path: Path,
    calibration_document: dict[str, Any],
    calibration_path: Path,
    tle_path: Path,
    expected_tle_digest: str,
    start_s: float,
    end_s: float,
    observer: ObserverSiteV1,
    config: raw_replay.RawReplayConfig,
    catalogue_name_prefix: str = "STARLINK",
    geometry_spacing_s: float = 0.5,
    output_schema_version: int = 1,
) -> dict[str, Any]:
    """Exhaust the finite fine bank and solve only null versus any activation."""

    if not catalogue_name_prefix.strip():
        raise ValueError("catalogue name prefix must not be empty")
    if not math.isfinite(geometry_spacing_s) or geometry_spacing_s <= 0.0:
        raise ValueError("geometry spacing must be finite and positive")
    if output_schema_version not in {1, 2}:
        raise ValueError("bounded null-vs-any output schema version must be 1 or 2")
    output_schema = OUTPUT_SCHEMA if output_schema_version == 1 else OUTPUT_SCHEMA_V2
    algorithm = ALGORITHM if output_schema_version == 1 else ALGORITHM_V2
    observed_tle_digest = screen._file_digest(tle_path)
    if observed_tle_digest != expected_tle_digest:
        raise ValueError("bounded null-vs-any TLE digest mismatch")
    catalogue = screen.parse_element_sets(tle_path.read_text(encoding="utf-8"))
    if len(set(catalogue.satellite_numbers)) != len(catalogue):
        raise ValueError("catalogue contains duplicate NORAD identities")

    calibration, window, inventory, scheduled_times_s = screen._prepare_raw_inventory(
        dataset=dataset,
        calibration_document=calibration_document,
        start_s=start_s,
        end_s=end_s,
        config=config,
    )
    if inventory.problem.truncated_observation_count:
        raise ValueError("bounded null-vs-any proof requires an untruncated retained inventory")
    if inventory.problem.costs.satellite_cost != config.satellite_cost:
        raise ValueError("inventory and configured satellite costs disagree")
    if inventory.problem.costs.episode_cost != config.episode_cost:
        raise ValueError("inventory and configured episode costs disagree")
    sky_frequency_hz = float(dataset["frequency_binding"]["sky_frequency_hz"])
    pilot_scan_configuration = screen._pilot_scan_configuration(inventory.scan_path)
    evaluation_scope_digest = screen._member_evaluation_scope_digest(
        dataset=dataset,
        dataset_path=dataset_path,
        pilot_scan_digest=inventory.scan_digest,
        window=window,
        start_s=start_s,
        end_s=end_s,
    )
    optimistic_certificate = screen.optimistic_null_certificate(inventory.problem)
    bank = screen.build_catalogue_prediction_bank(
        catalogue=catalogue,
        scheduled_times_s=scheduled_times_s,
        first_sample_utc_ns=int(dataset["timing_binding"]["first_estimate_utc_ns"]),
        delay_grid=config.delay_grid,
        sky_frequency_hz=sky_frequency_hz,
        observer=observer,
        horizon_mask_deg=config.horizon_mask_deg,
        name_prefix=catalogue_name_prefix,
        geometry_spacing_s=geometry_spacing_s,
    )
    scores = screen._score_catalog_rows(
        bank=bank,
        row_indices=tuple(range(len(bank.catalogue_indices))),
        delay_grid=config.delay_grid,
        problem=inventory.problem,
        raw_observations=inventory.observations,
        calibration=calibration,
        config=config,
    )
    witness_score = _activation_witness(
        scores,
        eligible_catalog_count=len(bank.catalogue_indices),
    )

    modeled_null_cost = _modeled_null_cost(inventory.problem)
    full_null_cost = modeled_null_cost + inventory.elided_clutter_constant
    if witness_score is None:
        result_kind = "bounded_exact_null"
        selected_catalog_numbers: list[int] = []
        full_objective = {
            "null_cost": full_null_cost,
            "total_cost": full_null_cost,
            "delta_from_null": 0.0,
            "constant_elided_from_exact_decision_problem": (inventory.elided_clutter_constant),
        }
        witness_document = None
    else:
        result_kind = "activation_witness"
        selected_catalog_numbers = [witness_score.catalog_number]
        witness_rank = scores.index(witness_score) + 1
        witness_document, full_objective = _witness_document(
            witness_score,
            rank=witness_rank,
            problem=inventory.problem,
            elided_clutter_constant=inventory.elided_clutter_constant,
        )

    calibration_digest = screen._file_digest(calibration_path)
    search_configuration = _search_configuration(
        calibration_schema=calibration_document.get("schema"),
        calibration_digest=calibration_digest,
        tle_digest=observed_tle_digest,
        sky_frequency_hz=sky_frequency_hz,
        pilot_scan_configuration=pilot_scan_configuration,
        observer=observer,
        start_s=start_s,
        end_s=end_s,
        scheduled_probe_count=len(window.rows),
        cell_count=window.cell_count,
        evaluation_scope_digest=evaluation_scope_digest,
        config=config,
        catalogue_name_prefix=catalogue_name_prefix,
        geometry_spacing_s=geometry_spacing_s,
        output_schema=output_schema,
        algorithm=algorithm,
    )
    local_max_abs = max(
        abs(inventory.local_epoch_min_s or 0.0),
        abs(inventory.local_epoch_max_s or 0.0),
    )
    generated_state_count = sum(item.generated_state_count for item in scores)
    negative_minima = sum(item.best_state.single_selected for item in scores)
    document: dict[str, Any] = {
        "schema": output_schema,
        "algorithm": algorithm,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "catalogue_search_performed": True,
        "catalogue_search_avoided_by_global_null_certificate": False,
        "catalogue_search_exact": False,
        "finite_universe_catalogue_search_exact": True,
        "null_vs_any_activation_solved": True,
        "unknown_satellite_count_solved": False,
        "global_optimum_claimed": False,
        "unrestricted_global_exactness_claimed": False,
        "conditional_on_explicit_catalog_shortlist": False,
        "conditional_on_catalogue_screen_shortlist": False,
        "conditional_on_raw_glrt64_inventory": True,
        "conditional_on_full_window_visibility_screen": True,
        "conditional_on_data_proposed_cfo_modes": True,
        "conditional_on_pruned_joint_shortlist": False,
        "conditional_on_pruned_nuisance_state_bank": False,
        "costs_calibrated": False,
        "detector_score_costs_empirically_calibrated": False,
        "resolution_group_score_frequency_estimated": calibration_document.get("schema")
        in {raw_replay.CALIBRATION_SCHEMA_V2, raw_replay.CALIBRATION_SCHEMA_V3},
        "conservative_rank_mark_bounds_applied": calibration_document.get("schema")
        == raw_replay.CALIBRATION_SCHEMA_V3,
        "structural_costs_calibrated": False,
        "input": {
            "duration_dataset_path": str(dataset_path.resolve()),
            "duration_dataset_digest": screen._file_digest(dataset_path),
            "pilot_scan_path": str(inventory.scan_path),
            "pilot_scan_digest": inventory.scan_digest,
            "score_calibration_path": str(calibration_path.resolve()),
            "score_calibration_digest": calibration_digest,
            "tle_path": str(tle_path.resolve()),
            "tle_digest": observed_tle_digest,
        },
        "window": {
            "start_s": start_s,
            "end_s": end_s,
            "cell_duration_s": config.cell_duration_s,
            "cell_count": window.cell_count,
            "minimum_active_cells": config.minimum_active_cells,
            "minimum_active_duration_s": config.minimum_active_duration_s,
            "scheduled_probe_count": len(window.rows),
        },
        "raw_inventory": _raw_inventory_document(
            inventory,
            dataset=dataset,
            config=config,
        ),
        "score_calibration": asdict(calibration),
        "configuration": asdict(config),
        "search_configuration": search_configuration,
        "search_configuration_digest": canonical_digest(search_configuration),
        "observer": {**observer.model_dump(mode="json"), "capture_bound": False},
        "timing_approximation": {
            "prediction_epoch": "scheduled_probe_start",
            "candidate_local_epoch_applied": False,
            "minimum_candidate_local_epoch_offset_s": inventory.local_epoch_min_s,
            "maximum_candidate_local_epoch_offset_s": inventory.local_epoch_max_s,
            "maximum_absolute_candidate_local_epoch_offset_s": local_max_abs,
        },
        "optimistic_null_certificate": {
            **asdict(optimistic_certificate),
            "algorithm": screen.NULL_CERTIFICATE_ALGORITHM,
            "used_as_short_circuit": False,
        },
        "decision": {
            "result_kind": result_kind,
            "selected_catalog_numbers": selected_catalog_numbers,
            "selected_satellite_count": len(selected_catalog_numbers),
            "unknown_satellite_count_solved": False,
            "full_persisted_inventory_objective": full_objective,
        },
        "association": {
            "selected_catalog_numbers": selected_catalog_numbers,
            "selected_satellite_count": len(selected_catalog_numbers),
            "objective": full_objective,
            "activation_witness": witness_document,
        },
        "catalogue_search": {
            "algorithm": algorithm,
            "finite_universe_exact": True,
            "geometry_accounting": asdict(bank.accounting),
            "fine_stage": {
                "delay_grid": list(config.delay_grid),
                "modes_per_delay": config.modes_per_delay,
                "eligible_catalog_count": len(bank.catalogue_indices),
                "scored_catalog_count": len(scores),
                "omitted_eligible_catalog_count": len(bank.catalogue_indices) - len(scores),
                "generated_state_count": generated_state_count,
                "generated_state_count_upper_bound": (
                    len(bank.catalogue_indices) * len(config.delay_grid) * config.modes_per_delay
                ),
                "catalogue_rows_exhausted": True,
                "declared_discrete_delay_grid_exhausted": True,
                "generated_data_proposed_cfo_mode_bank_exhausted": True,
                "continuous_delay_space_exhausted": False,
                "continuous_cfo_offset_space_exhausted": False,
                "negative_catalogue_minimum_count": negative_minima,
                "all_catalogue_minima_nonactivating": witness_score is None,
                "ranking": [
                    _configured_score_summary(
                        item,
                        rank,
                        satellite_cost=config.satellite_cost,
                    )
                    for rank, item in enumerate(scores, start=1)
                ],
            },
            "finite_universe": {
                "retained_raw_inventory_digest": inventory.scan_digest,
                "catalogue_identity_scope": "named and full-window-visible",
                "eligible_catalogue_count": len(bank.catalogue_indices),
                "maximum_selected_satellite_count": len(bank.catalogue_indices),
                "one_nuisance_state_per_selected_catalogue": True,
                "delay_scope": "declared discrete fine grid",
                "cfo_offset_scope": "generated data-proposed modes",
                "rise_set_objects_supported": False,
                "pre_acquisition_cap_inventory_complete": False,
            },
            "separability_proof": {
                "algorithm": SEPARABILITY_PROOF_ALGORITHM,
                "single_satellite_minima_exact_over_generated_states": True,
                "joint_delta_is_sum_of_selected_satellite_reduced_contributions": True,
                "exclusion_group_assignment_capacity": 1,
                "satellite_and_episode_costs_nonnegative": (
                    config.satellite_cost >= 0.0 and config.episode_cost >= 0.0
                ),
                "arbitrary_subsets_of_finite_catalogue_universe_covered": True,
                "proof_conclusion": result_kind,
            },
        },
        "caveats": [
            "exact only over the explicitly reported finite catalogue/delay/CFO-mode universe",
            "the proof is conditional on the retained bounded raw peak inventory",
            "every probe may have saturated the upstream retained-candidate cap",
            (
                "the catalogue universe excludes rise/set objects because per-probe visibility "
                "is absent"
            ),
            "data-proposed CFO modes do not exhaust continuous CFO-offset space",
            "the declared discrete delay grid does not exhaust continuous orbital-time delay",
            "the binary decision does not estimate the selected satellite count",
            "TLE bytes are digest-bound but snapshot acquisition causality is not verified here",
            "observer coordinates are explicit but not capture-bound authority",
            "no payload was decoded",
        ],
    }
    if output_schema_version == 2:
        partition = _identity_partition_document(
            catalogue=catalogue,
            bank=bank,
            catalogue_name_prefix=catalogue_name_prefix,
            tle_digest=observed_tle_digest,
        )
        document["catalogue_identity_partition"] = partition
        finite_universe = document["catalogue_search"]["finite_universe"]
        finite_universe["identity_partition_content_digest"] = partition["partition_content_digest"]
        document["caveats"].append(
            "the identity partition certifies bounded geometry eligibility, not RF absence"
        )
    return document


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--score-calibration", type=Path, required=True)
    parser.add_argument("--start-s", type=float, required=True)
    parser.add_argument("--end-s", type=float, required=True)
    parser.add_argument("--tle", type=Path, required=True)
    parser.add_argument("--tle-sha256", required=True)
    parser.add_argument("--observer-latitude-deg", type=float, required=True)
    parser.add_argument("--observer-longitude-deg", type=float, required=True)
    parser.add_argument("--observer-altitude-m", type=float, required=True)
    parser.add_argument("--observer-label", required=True)
    parser.add_argument("--cell-duration-s", type=float, default=0.1)
    parser.add_argument("--minimum-active-duration-s", type=float, default=0.5)
    parser.add_argument("--allow-left-censored", action="store_true")
    parser.add_argument("--allow-right-censored", action="store_true")
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
    parser.add_argument("--horizon-mask-deg", type=float, default=0.0)
    parser.add_argument("--catalogue-name-prefix", default="STARLINK")
    parser.add_argument("--geometry-spacing-s", type=float, default=0.5)
    parser.add_argument("--output-schema-version", type=int, choices=(1, 2), default=1)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    expected_tle_digest = str(arguments.tle_sha256)
    if not expected_tle_digest.startswith("sha256:"):
        expected_tle_digest = f"sha256:{expected_tle_digest}"
    config = raw_replay.RawReplayConfig(
        cell_duration_s=arguments.cell_duration_s,
        minimum_active_duration_s=arguments.minimum_active_duration_s,
        allow_left_censored=arguments.allow_left_censored,
        allow_right_censored=arguments.allow_right_censored,
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
        horizon_mask_deg=arguments.horizon_mask_deg,
    )
    document = decide_raw_catalogue_null_vs_any(
        dataset=screen._read_json(arguments.input),
        dataset_path=arguments.input,
        calibration_document=screen._read_json(arguments.score_calibration),
        calibration_path=arguments.score_calibration,
        tle_path=arguments.tle,
        expected_tle_digest=expected_tle_digest,
        start_s=arguments.start_s,
        end_s=arguments.end_s,
        observer=ObserverSiteV1(
            latitude_deg=arguments.observer_latitude_deg,
            longitude_deg=arguments.observer_longitude_deg,
            altitude_m=arguments.observer_altitude_m,
            label=arguments.observer_label,
        ),
        config=config,
        catalogue_name_prefix=arguments.catalogue_name_prefix,
        geometry_spacing_s=arguments.geometry_spacing_s,
        output_schema_version=arguments.output_schema_version,
    )
    rendered = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        screen._refuse_qnap_output(arguments.output)
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
