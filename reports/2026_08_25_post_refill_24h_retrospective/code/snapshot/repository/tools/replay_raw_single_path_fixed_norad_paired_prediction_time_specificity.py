#!/usr/bin/env python3
"""Atomically qualify one bounded-source NORAD with prediction-time controls.

This Research-only producer consumes one exact bounded-null-vs-any V2 source,
loads its one raw PilotScanV3 decision problem once, freezes the target NORAD
and at least four non-affine half-second block permutations, and evaluates the
identity and every control over every declared delay/data-proposed-CFO state.

The output is deliberately a fixed-target diagnostic.  It does not search a
catalogue, estimate a false-positive rate, identify a spacecraft, decode a
payload, or establish a track.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np

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
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]
from leo.sky.propagation import parse_element_sets  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools import decide_raw_catalogue_null_vs_any as bounded  # noqa: E402
from tools import replay_raw_grouped_satellite_activity as raw_replay  # noqa: E402
from tools import replay_raw_multipath_paired_prediction_time_specificity as paired  # noqa: E402
from tools import replay_raw_multipath_satellite_activity as multipath  # noqa: E402
from tools import screen_raw_satellite_activity_catalog as screen  # noqa: E402
from tools.replay_joint_fixed_satellite_activity import _doppler_curve  # noqa: E402

OUTPUT_SCHEMA = "org.leo.research.raw-single-path-fixed-norad-paired-prediction-time-specificity/v1"
ALGORITHM = "atomic-fixed-norad-exhaustive-single-path-prediction-time-specificity-v1"
FAMILY_PLAN_SCHEMA = "org.leo.research.raw-single-path-fixed-norad-family-plan/v1"
SOURCE_SCHEMA = bounded.OUTPUT_SCHEMA_V2
SOURCE_ALGORITHM = bounded.ALGORITHM_V2
UTC_CELL_NS = 100_000_000
MINIMUM_CONTROL_COUNT = 4
MAXIMUM_CONTROL_COUNT = 16
REQUIRED_DELAY_COUNT = 41
REQUIRED_MODES_PER_DELAY = 2

IDENTITY_NONACTIVATION = "identity_nonactivation"
CONTROL_ACTIVATION = "block_permutation_control_activation"
CONTROL_NULL_NOT_CERTIFIED = "control_finite_null_not_certified"
ADVANTAGE_BELOW_THRESHOLD = "identity_advantage_below_frozen_threshold"
GATE_PASS = "fixed_norad_prediction_time_gate_pass"
TARGET_SELECTION_CAUSALITY_NOT_VERIFIED = "target_selection_causality_not_verified"
NOT_COMPARABLE = "not_comparable"

_IMPLEMENTATION_FILE_PATHS = (
    "tools/replay_raw_single_path_fixed_norad_paired_prediction_time_specificity.py",
    "tools/decide_raw_catalogue_null_vs_any.py",
    "tools/screen_raw_satellite_activity_catalog.py",
    "tools/raw_satellite_activity_search_configuration.py",
    "tools/replay_raw_grouped_satellite_activity.py",
    "tools/replay_raw_multipath_paired_prediction_time_specificity.py",
    "tools/replay_raw_multipath_satellite_activity.py",
    "tools/replay_joint_fixed_satellite_activity.py",
    "src/leo/analysis/research/activity_block_permutation.py",
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
class _LoadedSource:
    source: dict[str, Any]
    source_path: Path
    source_digest: str
    dataset: dict[str, Any]
    dataset_path: Path
    dataset_digest: str
    calibration_document: dict[str, Any]
    calibration_path: Path
    calibration_digest: str
    tle_path: Path
    tle_digest: str
    catalogue: Any
    catalogue_index: int
    target_row: dict[str, Any]
    target_score: screen.CatalogScore
    observer: ObserverSiteV1
    config: raw_replay.RawReplayConfig
    calibration: raw_replay.ScoreCalibration
    window: Any
    inventory: raw_replay._RawInventory
    scheduled_times_s: tuple[float, ...]
    persisted_probe_utc: tuple[dict[str, Any], ...]
    start_s: float
    end_s: float
    window_start_utc_ns: int
    window_end_utc_ns: int


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value!r} is forbidden")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON document {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON document {path} must contain one object")
    return value


def _canonical_sha256(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a SHA-256 digest")
    result = value if value.startswith("sha256:") else f"sha256:{value}"
    if len(result) != 71 or any(character not in "0123456789abcdef" for character in result[7:]):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return result


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _finite_nonnegative(value: object, label: str) -> float:
    result = _finite(value, label)
    if result < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return result


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _list(value: object, label: str) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be a list")
    return list(value)


def _implementation_file_digests() -> dict[str, str]:
    return {
        relative_path: _file_digest(REPOSITORY_ROOT / relative_path)
        for relative_path in _IMPLEMENTATION_FILE_PATHS
    }


def producer_implementation_manifest() -> dict[str, Any]:
    return {
        "algorithm": ALGORITHM,
        "implementation_file_digests": _implementation_file_digests(),
        "runtime_versions": multipath._runtime_versions(),
    }


def _nested_reference(
    source_input: dict[str, Any],
    *,
    path_key: str,
    digest_key: str,
    label: str,
) -> tuple[Path, str]:
    raw_path = source_input.get(path_key)
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError(f"source {label} path must be nonempty")
    path = Path(raw_path).resolve()
    digest = _canonical_sha256(source_input.get(digest_key), f"source {label} digest")
    if _file_digest(path) != digest:
        raise ValueError(f"source {label} file digest mismatch")
    return path, digest


def _raw_config(document: dict[str, Any]) -> raw_replay.RawReplayConfig:
    expected = set(raw_replay.RawReplayConfig.__dataclass_fields__)
    if set(document) != expected:
        raise ValueError("source raw configuration has missing or extra fields")
    config = raw_replay.RawReplayConfig(**document)
    if not math.isclose(config.cell_duration_s, 0.1, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("fixed-NORAD controls require exact 100-ms activity cells")
    if config.allow_left_censored or config.allow_right_censored:
        raise ValueError("fixed-NORAD controls refuse boundary-censored activity")
    if len(config.delay_grid) != REQUIRED_DELAY_COUNT:
        raise ValueError("fixed-NORAD controls require the source's complete 41-point delay grid")
    if config.modes_per_delay != REQUIRED_MODES_PER_DELAY:
        raise ValueError("fixed-NORAD controls require exactly two proposed CFO modes per delay")
    return config


def _validate_exact_source_contract(source: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Fail closed on every bounded-V2 exactness and identity-partition claim."""

    required_true = (
        "catalogue_search_performed",
        "finite_universe_catalogue_search_exact",
        "null_vs_any_activation_solved",
        "conditional_on_raw_glrt64_inventory",
        "conditional_on_full_window_visibility_screen",
        "conditional_on_data_proposed_cfo_modes",
    )
    required_false = (
        "catalogue_search_avoided_by_global_null_certificate",
        "conditional_on_explicit_catalog_shortlist",
        "conditional_on_catalogue_screen_shortlist",
        "conditional_on_pruned_joint_shortlist",
        "conditional_on_pruned_nuisance_state_bank",
        "unrestricted_global_exactness_claimed",
    )
    bad_flags = [key for key in required_true if source.get(key) is not True]
    bad_flags.extend(key for key in required_false if source.get(key) is not False)
    if bad_flags:
        raise ValueError(f"bounded V2 source exactness flags are incomplete: {bad_flags!r}")
    raw_inventory = _object(source.get("raw_inventory"), "source raw inventory")
    if (
        raw_inventory.get("declared_post_acquisition_inventory_complete") is not True
        or _integer(raw_inventory.get("truncated_candidate_count"), "truncated candidates") != 0
    ):
        raise ValueError("bounded V2 retained raw inventory is truncated or incomplete")

    search = _object(source.get("catalogue_search"), "source catalogue search")
    fine = _object(search.get("fine_stage"), "source fine stage")
    finite = _object(search.get("finite_universe"), "source finite universe")
    proof = _object(search.get("separability_proof"), "source separability proof")
    if any(
        fine.get(key) is not True
        for key in (
            "catalogue_rows_exhausted",
            "declared_discrete_delay_grid_exhausted",
            "generated_data_proposed_cfo_mode_bank_exhausted",
        )
    ):
        raise ValueError("bounded V2 per-catalogue state generation is not exhausted")
    if (
        proof.get("single_satellite_minima_exact_over_generated_states") is not True
        or proof.get("joint_delta_is_sum_of_selected_satellite_reduced_contributions") is not True
        or proof.get("arbitrary_subsets_of_finite_catalogue_universe_covered") is not True
        or proof.get("satellite_and_episode_costs_nonnegative") is not True
        or proof.get("exclusion_group_assignment_capacity") != 1
    ):
        raise ValueError("bounded V2 separability proof is incomplete")
    ranking = tuple(
        _object(item, "source catalogue row")
        for item in _list(fine.get("ranking"), "source fine ranking")
    )
    eligible_count = _integer(fine.get("eligible_catalog_count"), "eligible catalog count")
    scored_count = _integer(fine.get("scored_catalog_count"), "scored catalog count")
    finite_count = _integer(finite.get("eligible_catalogue_count"), "finite catalog count")
    omitted_count = _integer(
        fine.get("omitted_eligible_catalog_count"), "omitted eligible catalog count"
    )
    if not (eligible_count == scored_count == finite_count == len(ranking)) or omitted_count:
        raise ValueError("bounded V2 eligible catalogue rows are omitted or count-inconsistent")
    if finite.get("catalogue_identity_scope") != "named and full-window-visible":
        raise ValueError("bounded V2 catalogue identity scope is unsupported")
    delay_grid = _list(fine.get("delay_grid"), "source delay grid")
    modes_per_delay = _integer(fine.get("modes_per_delay"), "source modes per delay", minimum=1)
    expected_states = len(delay_grid) * modes_per_delay
    prior_key: tuple[float, int, str] | None = None
    catalog_numbers = []
    generated_total = 0
    negative_count = 0
    for expected_rank, row in enumerate(ranking, start=1):
        if _integer(row.get("rank"), "source rank", minimum=1) != expected_rank:
            raise ValueError("bounded V2 source ranks are not contiguous")
        catalog_number = _integer(row.get("catalog_number"), "source catalog", minimum=1)
        generated = _integer(row.get("generated_state_count"), "source state count", minimum=1)
        if generated != expected_states:
            raise ValueError(f"bounded V2 NORAD {catalog_number} has an incomplete state bank")
        reduced = _finite(row.get("best_single_delta_from_null"), "source reduced objective")
        selected = row.get("best_single_selected")
        if not isinstance(selected, bool) or selected != (reduced < 0.0):
            raise ValueError("bounded V2 source selection disagrees with its minimum")
        hypothesis_id = row.get("best_hypothesis_id")
        if not isinstance(hypothesis_id, str) or not hypothesis_id:
            raise ValueError("bounded V2 source minimum has no hypothesis ID")
        key = (reduced, catalog_number, hypothesis_id)
        if prior_key is not None and key < prior_key:
            raise ValueError("bounded V2 source ranking is not canonical")
        prior_key = key
        catalog_numbers.append(catalog_number)
        generated_total += generated
        negative_count += int(reduced < 0.0)
    if len(set(catalog_numbers)) != len(catalog_numbers):
        raise ValueError("bounded V2 source repeats a NORAD identity")
    if (
        generated_total != _integer(fine.get("generated_state_count"), "generated states")
        or generated_total
        != _integer(fine.get("generated_state_count_upper_bound"), "state upper bound")
        or negative_count
        != _integer(fine.get("negative_catalogue_minimum_count"), "negative minima")
        or fine.get("all_catalogue_minima_nonactivating") is not (negative_count == 0)
    ):
        raise ValueError("bounded V2 source state/minimum totals are inconsistent")

    partition = _object(source.get("catalogue_identity_partition"), "identity partition")
    partition_digest = _canonical_sha256(
        partition.get("partition_content_digest"), "identity-partition content digest"
    )
    partition_payload = dict(partition)
    partition_payload.pop("partition_content_digest", None)
    if canonical_digest(partition_payload) != partition_digest:
        raise ValueError("bounded V2 identity-partition digest does not recompute")
    if (
        partition.get("schema") != bounded.IDENTITY_PARTITION_SCHEMA
        or partition.get("algorithm") != bounded.IDENTITY_PARTITION_ALGORITHM
        or partition.get("partition_exhausted") is not True
        or partition.get("partition_pruned") is not False
        or partition.get("eligibility_semantics")
        != "named-and-full-window-visible-over-declared-delay-grid"
    ):
        raise ValueError("bounded V2 identity partition is incomplete")

    def catalog_list(field: str) -> tuple[int, ...]:
        values = tuple(
            _integer(item, f"identity partition {field}", minimum=1)
            for item in _list(partition.get(field), f"identity partition {field}")
        )
        if values != tuple(sorted(set(values))):
            raise ValueError(f"identity partition {field} is not sorted and unique")
        return values

    named = catalog_list("named_catalog_numbers")
    eligible = catalog_list("eligible_catalog_numbers")
    ineligible = catalog_list("named_ineligible_catalog_numbers")
    if (
        set(eligible) & set(ineligible)
        or tuple(sorted((*eligible, *ineligible))) != named
        or set(eligible) != set(catalog_numbers)
    ):
        raise ValueError("bounded V2 identity partition does not reconcile with exact rows")
    for field, values in (
        ("named", named),
        ("eligible", eligible),
        ("named_ineligible", ineligible),
    ):
        if partition.get(f"{field}_catalog_count") != len(values):
            raise ValueError("bounded V2 identity-partition count does not reconcile")
        if _canonical_sha256(
            partition.get(f"{field}_catalog_numbers_digest"),
            f"identity partition {field} digest",
        ) != canonical_digest(list(values)):
            raise ValueError("bounded V2 identity-partition list digest does not recompute")
    if (
        _canonical_sha256(
            finite.get("identity_partition_content_digest"), "finite identity-partition digest"
        )
        != partition_digest
    ):
        raise ValueError("bounded V2 finite universe does not bind the identity partition")
    decision = _object(source.get("decision"), "source decision")
    decision_objective = _object(
        decision.get("full_persisted_inventory_objective"), "source decision objective"
    )
    decision_delta = _finite(decision_objective.get("delta_from_null"), "source decision delta")
    expected_selected = [] if negative_count == 0 else [catalog_numbers[0]]
    expected_delta = (
        0.0
        if negative_count == 0
        else _finite(ranking[0].get("best_single_delta_from_null"), "source winning delta")
    )
    if (
        decision.get("selected_catalog_numbers") != expected_selected
        or decision_delta != expected_delta
        or decision.get("result_kind")
        != ("bounded_exact_null" if negative_count == 0 else "activation_witness")
    ):
        raise ValueError("bounded V2 decision does not reconcile with exact minima")
    return ranking


def _persisted_probe_utc(
    dataset: dict[str, Any],
    *,
    rows: tuple[dict[str, Any], ...],
    problem: SatelliteActivityProblem,
) -> tuple[dict[str, Any], ...]:
    timing = _object(dataset.get("timing_binding"), "duration timing binding")
    if (
        timing.get("observation_utc_method")
        != "linear interpolation between manifest first/last sample timing anchors"
        or timing.get("receiver_relative_time_origin") != "first captured sample"
    ):
        raise ValueError("duration input has unsupported probe UTC authority")
    capture = _object(dataset.get("capture"), "duration capture")
    declared_sample_count = _integer(
        capture.get("declared_sample_count"), "duration sample count", minimum=2
    )
    probe_by_id = {probe.probe_id: probe for probe in problem.probes}
    result = []
    for row in rows:
        probe_id = str(row.get("probe_id", ""))
        probe = probe_by_id.get(probe_id)
        if probe is None:
            raise ValueError("raw problem and source window have different probe inventories")
        expected = multipath._interpolated_utc(
            timing,
            _integer(row.get("probe_sample_start"), "scheduled probe sample"),
            declared_sample_count,
        )
        if row.get("probe_start_utc") != expected:
            raise ValueError("scheduled probe UTC differs from the duration timing anchors")
        within_cell_offset_ns = round(
            (probe.time_s - problem.grid.start_s - probe.cell_index * problem.grid.cell_duration_s)
            * 1e9
        )
        if not 0 <= within_cell_offset_ns < UTC_CELL_NS:
            raise ValueError("scheduled probe lies outside its source activity cell")
        result.append(
            {
                "probe_id": probe_id,
                "estimate_utc_ns": expected["estimate_utc_ns"],
                "earliest_utc_ns": expected["earliest_utc_ns"],
                "latest_utc_ns": expected["latest_utc_ns"],
                "source_prediction_time_s": probe.time_s,
                "source_prediction_utc_ns": _integer(
                    timing.get("first_estimate_utc_ns"),
                    "duration first-estimate UTC",
                )
                + round(probe.time_s * 1e9),
                "observation_cell_index": probe.cell_index,
                "within_activity_cell_offset_ns": within_cell_offset_ns,
            }
        )
    if len(result) != len(problem.probes) or len({item["probe_id"] for item in result}) != len(
        result
    ):
        raise ValueError("persisted source probe inventory is incomplete or duplicated")
    return tuple(result)


def _load_source(
    *,
    source_path: Path,
    expected_source_digest: str,
    target_catalog_number: int,
) -> _LoadedSource:
    resolved_source_path = source_path.resolve()
    source_digest = _canonical_sha256(expected_source_digest, "source artifact digest")
    if _file_digest(resolved_source_path) != source_digest:
        raise ValueError("bounded V2 source artifact digest mismatch")
    source = _read_json(resolved_source_path)
    if source.get("schema") != SOURCE_SCHEMA or source.get("algorithm") != SOURCE_ALGORITHM:
        raise ValueError("fixed-NORAD controls require a bounded-null-vs-any V2 source")
    if source.get("finite_universe_catalogue_search_exact") is not True:
        raise ValueError("source catalogue universe is not finite-universe exact")
    exact_ranking = _validate_exact_source_contract(source)
    source_search = _object(source.get("search_configuration"), "source search configuration")
    if source.get("search_configuration_digest") != canonical_digest(source_search):
        raise ValueError("source search-configuration digest does not recompute")
    if source_search.get("producer_implementation") != bounded.producer_implementation_manifest():
        raise ValueError("source bounded producer implementation is not current")

    source_input = _object(source.get("input"), "source input")
    dataset_path, dataset_digest = _nested_reference(
        source_input,
        path_key="duration_dataset_path",
        digest_key="duration_dataset_digest",
        label="duration input",
    )
    calibration_path, calibration_digest = _nested_reference(
        source_input,
        path_key="score_calibration_path",
        digest_key="score_calibration_digest",
        label="score calibration",
    )
    tle_path, tle_digest = _nested_reference(
        source_input,
        path_key="tle_path",
        digest_key="tle_digest",
        label="TLE",
    )
    pilot_scan_path, pilot_scan_digest = _nested_reference(
        source_input,
        path_key="pilot_scan_path",
        digest_key="pilot_scan_digest",
        label="pilot scan",
    )
    dataset = _read_json(dataset_path)
    calibration_document = _read_json(calibration_path)
    _read_json(pilot_scan_path)
    if calibration_document.get("schema") != raw_replay.CALIBRATION_SCHEMA_V3:
        raise ValueError("fixed-NORAD controls require raw PilotScanV3 score calibration")
    if (
        source_search.get("tle_digest") != tle_digest
        or source_search.get("score_calibration_digest") != calibration_digest
        or source_search.get("score_calibration_schema") != calibration_document.get("schema")
        or source_search.get("algorithm") != SOURCE_ALGORITHM
        or source_search.get("output_schema") != SOURCE_SCHEMA
        or source_search.get("input_schema") != dataset.get("schema")
        or source_search.get("state_generation_algorithm") != screen.ALGORITHM
    ):
        raise ValueError("source search configuration disagrees with nested file lineage")

    config_document = _object(source.get("configuration"), "source configuration")
    if source_search.get("raw_replay") != config_document:
        raise ValueError("source raw configuration cross-link mismatch")
    config = _raw_config(config_document)
    source_screen = _object(
        source_search.get("catalogue_screen"), "source catalogue-screen configuration"
    )
    if (
        source_screen.get("algorithm") != SOURCE_ALGORITHM
        or source_screen.get("fine_delay_grid") != list(config.delay_grid)
        or source_screen.get("modes_per_delay") != config.modes_per_delay
        or source_screen.get("full_probe_by_delay_visibility_required") is not True
    ):
        raise ValueError("source catalogue-screen state scope cross-link mismatch")
    observer_document = dict(_object(source.get("observer"), "source observer"))
    if observer_document.pop("capture_bound", None) is not False:
        raise ValueError("source observer authority semantics are unsupported")
    observer = ObserverSiteV1.model_validate(observer_document)
    if source_search.get("observer") != observer.model_dump(mode="json"):
        raise ValueError("source observer search cross-link mismatch")

    window_document = _object(source.get("window"), "source window")
    start_s = _finite(window_document.get("start_s"), "source window start")
    end_s = _finite(window_document.get("end_s"), "source window end")
    if end_s <= start_s:
        raise ValueError("source window must be increasing")
    calibration, window, inventory, scheduled_times_s = screen._prepare_raw_inventory(
        dataset=dataset,
        calibration_document=calibration_document,
        start_s=start_s,
        end_s=end_s,
        config=config,
    )
    if (
        inventory.scan_path.resolve() != pilot_scan_path
        or inventory.scan_digest != pilot_scan_digest
    ):
        raise ValueError("loaded raw inventory differs from the source pilot scan")
    if inventory.problem.truncated_observation_count:
        raise ValueError("fixed-NORAD controls require an untruncated retained raw inventory")
    if (
        window_document.get("cell_count") != window.cell_count
        or window_document.get("scheduled_probe_count") != len(window.rows)
        or window_document.get("cell_duration_s") != config.cell_duration_s
        or window_document.get("minimum_active_cells") != config.minimum_active_cells
    ):
        raise ValueError("loaded raw window differs from the bounded V2 source window")
    expected_search_window = {
        "start_s": start_s,
        "end_s": end_s,
        "duration_s": end_s - start_s,
        "scheduled_probe_count": len(window.rows),
        "cell_count": window.cell_count,
    }
    expected_scope_digest = screen._member_evaluation_scope_digest(
        dataset=dataset,
        dataset_path=dataset_path,
        pilot_scan_digest=inventory.scan_digest,
        window=window,
        start_s=start_s,
        end_s=end_s,
    )
    if (
        source_search.get("window") != expected_search_window
        or source_search.get("member_evaluation_scope_digest") != expected_scope_digest
        or source_search.get("pilot_scan") != screen._pilot_scan_configuration(inventory.scan_path)
        or source_search.get("sky_frequency_hz") != dataset["frequency_binding"]["sky_frequency_hz"]
    ):
        raise ValueError("source search window, raw scan, frequency, or scope cross-link differs")

    fine = _object(
        _object(source.get("catalogue_search"), "source catalogue search").get("fine_stage"),
        "source fine stage",
    )
    required_flags = (
        "catalogue_rows_exhausted",
        "declared_discrete_delay_grid_exhausted",
        "generated_data_proposed_cfo_mode_bank_exhausted",
    )
    if any(fine.get(flag) is not True for flag in required_flags):
        raise ValueError("source fine catalogue/state universe is not exhausted")
    if (
        fine.get("delay_grid") != list(config.delay_grid)
        or fine.get("modes_per_delay") != config.modes_per_delay
    ):
        raise ValueError("source fine state grid differs from its raw configuration")
    target_rows = [
        row for row in exact_ranking if row.get("catalog_number") == target_catalog_number
    ]
    if len(target_rows) != 1:
        raise ValueError("fixed target is absent or duplicated in the exhausted source universe")
    target_row = target_rows[0]
    expected_state_count = len(config.delay_grid) * config.modes_per_delay
    if target_row.get("generated_state_count") != expected_state_count:
        raise ValueError("source target did not generate the complete 41x2 nuisance bank")

    catalogue = parse_element_sets(tle_path.read_text(encoding="utf-8"))
    if len(set(catalogue.satellite_numbers)) != len(catalogue):
        raise ValueError("source TLE contains duplicate NORAD identities")
    catalogue_index = multipath._unique_satellite_index(catalogue, target_catalog_number)
    if str(catalogue.names[catalogue_index]) != target_row.get("object_name"):
        raise ValueError("source target name differs from the digest-bound TLE")
    name_prefix = source_screen.get("name_prefix")
    geometry_spacing_s = _finite(
        source_screen.get("geometry_spacing_s"),
        "source geometry spacing",
    )
    if not isinstance(name_prefix, str) or not name_prefix:
        raise ValueError("source catalogue name prefix must be nonempty")
    partition = _object(source.get("catalogue_identity_partition"), "identity partition")
    if (
        partition.get("tle_digest") != tle_digest
        or partition.get("catalogue_name_prefix") != name_prefix
        or partition.get("catalogue_object_count") != len(catalogue)
    ):
        raise ValueError("source identity partition differs from its TLE/name catalogue scope")
    target_bank = screen.build_catalogue_prediction_bank(
        catalogue=catalogue,
        scheduled_times_s=scheduled_times_s,
        first_sample_utc_ns=int(dataset["timing_binding"]["first_estimate_utc_ns"]),
        delay_grid=config.delay_grid,
        sky_frequency_hz=float(dataset["frequency_binding"]["sky_frequency_hz"]),
        observer=observer,
        horizon_mask_deg=config.horizon_mask_deg,
        name_prefix=name_prefix,
        geometry_spacing_s=geometry_spacing_s,
    )
    regenerated_eligible = set(target_bank.catalog_numbers)
    declared_eligible = {
        _integer(row.get("catalog_number"), "source exact catalog", minimum=1)
        for row in exact_ranking
    }
    partition_eligible = set(
        _integer(item, "partition eligible catalog", minimum=1)
        for item in _list(partition.get("eligible_catalog_numbers"), "partition eligible catalogs")
    )
    if (
        regenerated_eligible != declared_eligible
        or regenerated_eligible != partition_eligible
        or target_bank.accounting.eligible_catalog_count != len(regenerated_eligible)
    ):
        raise ValueError(
            "source exact rows/identity partition do not match regenerated TLE geometry"
        )
    try:
        target_bank_row = target_bank.catalog_numbers.index(target_catalog_number)
    except ValueError as error:
        raise ValueError("source target is absent from regenerated eligible geometry") from error
    target_score = screen._evaluate_catalog(
        bank=target_bank,
        row_index=target_bank_row,
        delay_grid=config.delay_grid,
        problem=inventory.problem,
        raw_observations=inventory.observations,
        calibration=calibration,
        config=config,
    )
    regenerated_target_row = bounded._configured_score_summary(
        target_score,
        _integer(target_row.get("rank"), "source target rank", minimum=1),
        satellite_cost=config.satellite_cost,
    )
    if regenerated_target_row != target_row:
        raise ValueError("source target ranking row does not regenerate from bound source bytes")

    persisted_probe_utc = _persisted_probe_utc(
        dataset,
        rows=tuple(window.rows),
        problem=inventory.problem,
    )
    timing = _object(dataset.get("timing_binding"), "duration timing")
    first_estimate_utc_ns = _integer(
        timing.get("first_estimate_utc_ns"), "duration first-estimate UTC"
    )
    window_start_utc_ns = first_estimate_utc_ns + round(start_s * 1e9)
    window_end_utc_ns = first_estimate_utc_ns + round(end_s * 1e9)
    if (window_end_utc_ns - window_start_utc_ns) % 500_000_000:
        raise ValueError("source window must contain complete half-second permutation blocks")
    capture = _object(dataset.get("capture"), "duration capture")
    if not isinstance(capture.get("session_id"), str) or not capture["session_id"]:
        raise ValueError("duration input has no session ID")
    return _LoadedSource(
        source=source,
        source_path=resolved_source_path,
        source_digest=source_digest,
        dataset=dataset,
        dataset_path=dataset_path,
        dataset_digest=dataset_digest,
        calibration_document=calibration_document,
        calibration_path=calibration_path,
        calibration_digest=calibration_digest,
        tle_path=tle_path,
        tle_digest=tle_digest,
        catalogue=catalogue,
        catalogue_index=catalogue_index,
        target_row=target_row,
        target_score=target_score,
        observer=observer,
        config=config,
        calibration=calibration,
        window=window,
        inventory=inventory,
        scheduled_times_s=scheduled_times_s,
        persisted_probe_utc=persisted_probe_utc,
        start_s=start_s,
        end_s=end_s,
        window_start_utc_ns=window_start_utc_ns,
        window_end_utc_ns=window_end_utc_ns,
    )


def _problem_payload(source: _LoadedSource) -> dict[str, Any]:
    inventory = source.inventory
    return {
        "decision_problem": asdict(inventory.problem),
        "persisted_probe_utc": list(source.persisted_probe_utc),
        "raw_candidate_bundles": [asdict(item) for item in inventory.observations],
        "source_candidate_count": inventory.source_candidate_count,
        "returned_candidate_count": inventory.returned_candidate_count,
        "probe_count_at_retained_candidate_cap": inventory.saturated_probe_count,
        "constant_elided_from_exact_decision_problem": inventory.elided_clutter_constant,
        "pre_acquisition_cap_inventory_complete": False,
        "physical_signal_inventory_complete": False,
    }


def _problem_from_payload(payload: dict[str, Any]) -> SatelliteActivityProblem:
    raw = _object(payload.get("decision_problem"), "raw decision problem")
    grid_raw = _object(raw.get("grid"), "raw activity grid")
    costs_raw = _object(raw.get("costs"), "raw association costs")
    probes = tuple(
        CfoProbe(**_object(item, "raw probe")) for item in _list(raw.get("probes"), "raw probes")
    )
    observations = tuple(
        CfoCandidate(**_object(item, "raw observation"))
        for item in _list(raw.get("observations"), "raw observations")
    )
    problem = SatelliteActivityProblem(
        grid=ActivityGrid(**grid_raw),
        probes=probes,
        observations=observations,
        costs=AssociationCostModel(**costs_raw),
        truncated_observation_count=_integer(
            raw.get("truncated_observation_count"), "raw truncated observation count"
        ),
    )
    if canonical_digest(asdict(problem)) != canonical_digest(raw):
        raise ValueError("raw decision problem does not reconstruct exactly")
    return problem


def _prediction_mapping(
    *,
    transform: paired._ArmTransform,
    persisted_probe_utc: tuple[dict[str, Any], ...],
    problem: SatelliteActivityProblem,
) -> tuple[dict[str, float], dict[str, Any]]:
    probe_by_id = {item.probe_id: item for item in problem.probes}
    mapped: dict[str, float] = {}
    rows = []
    for persisted in persisted_probe_utc:
        probe_id = str(persisted["probe_id"])
        probe = probe_by_id[probe_id]
        observation_cell = probe.cell_index
        prediction_cell = (
            observation_cell
            if transform.plan is None
            else transform.plan.prediction_cell_for_observation_cell(observation_cell)
        )
        observation_utc_ns = _integer(persisted["estimate_utc_ns"], "persisted observation UTC")
        source_prediction_time_s = _finite(
            persisted["source_prediction_time_s"], "source prediction time"
        )
        prediction_time_s = (
            source_prediction_time_s
            + (prediction_cell - observation_cell) * problem.grid.cell_duration_s
        )
        first_utc_ns = persisted["source_prediction_utc_ns"] - round(source_prediction_time_s * 1e9)
        prediction_utc_ns = first_utc_ns + round(prediction_time_s * 1e9)
        mapped[probe_id] = prediction_time_s
        rows.append(
            {
                "probe_id": probe_id,
                "observation_utc_ns": observation_utc_ns,
                "source_prediction_time_s": source_prediction_time_s,
                "source_prediction_utc_ns": persisted["source_prediction_utc_ns"],
                "observation_cell_index": observation_cell,
                "prediction_time_s": prediction_time_s,
                "prediction_utc_ns": prediction_utc_ns,
                "prediction_cell_index": prediction_cell,
                "within_activity_cell_offset_ns": persisted["within_activity_cell_offset_ns"],
            }
        )
    payload = {
        "arm_id": transform.arm_id,
        "transform_digest": transform.transform_digest,
        "mapping": rows,
    }
    return mapped, {**payload, "mapping_digest": canonical_digest(payload)}


def _propagate_mapped_epochs(
    *,
    source: _LoadedSource,
    prediction_time_s_by_probe_id: dict[str, float],
    delay_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    problem = source.inventory.problem
    mapped_times = tuple(prediction_time_s_by_probe_id[probe.probe_id] for probe in problem.probes)
    if len(set(mapped_times)) != len(mapped_times):
        raise ValueError("mapped prediction epochs must remain unique")
    order = tuple(sorted(range(len(mapped_times)), key=mapped_times.__getitem__))
    first_utc_ns = _integer(
        _object(source.dataset.get("timing_binding"), "duration timing").get(
            "first_estimate_utc_ns"
        ),
        "duration first-estimate UTC",
    )
    scheduled_times_s = tuple(mapped_times[index] for index in order)
    curve, elevation, _altitude = _doppler_curve(
        catalogue=source.catalogue,
        satellite_index=source.catalogue_index,
        first_sample_utc_ns=first_utc_ns,
        scheduled_times_s=scheduled_times_s,
        delay_s=delay_s,
        sky_frequency_hz=float(source.dataset["frequency_binding"]["sky_frequency_hz"]),
        observer=source.observer,
    )

    def restore(values: Any) -> np.ndarray:
        ordered = np.asarray(values, dtype=np.float64)
        if ordered.shape != (len(problem.probes),):
            raise RuntimeError("mapped target propagation returned an invalid shape")
        restored = np.empty(len(problem.probes), dtype=np.float64)
        restored[np.asarray(order, dtype=np.intp)] = ordered
        return restored

    return restore(curve), restore(elevation)


def _serialize_state(
    *,
    state: raw_replay._StateEvaluation,
    decoded: Any,
) -> dict[str, Any]:
    return {
        "hypothesis": asdict(state.hypothesis),
        "proposal": asdict(state.proposal),
        "minimum_elevation_deg": state.minimum_elevation_deg,
        "maximum_elevation_deg": state.maximum_elevation_deg,
        "decoded": asdict(decoded),
    }


def _evaluate_arm(
    *,
    source: _LoadedSource,
    target_catalog_number: int,
    transform: paired._ArmTransform,
    common_digests: dict[str, str],
) -> dict[str, Any]:
    problem = source.inventory.problem
    mapped, mapping_receipt = _prediction_mapping(
        transform=transform,
        persisted_probe_utc=source.persisted_probe_utc,
        problem=problem,
    )
    generated: list[tuple[raw_replay._StateEvaluation, Any]] = []
    for delay_s in source.config.delay_grid:
        curve, elevation = _propagate_mapped_epochs(
            source=source,
            prediction_time_s_by_probe_id=mapped,
            delay_s=delay_s,
        )
        minimum_elevation = float(np.min(elevation))
        maximum_elevation = float(np.max(elevation))
        if minimum_elevation <= source.config.horizon_mask_deg:
            raise ValueError(
                f"target NORAD {target_catalog_number} is not full-window visible in "
                f"arm {transform.arm_id!r}"
            )
        modes = raw_replay._offset_modes(
            raw=source.inventory.observations,
            base_prediction_hz=curve,
            calibration=source.calibration,
            config=source.config,
        )
        if len(modes) != REQUIRED_MODES_PER_DELAY:
            raise ValueError(
                f"arm {transform.arm_id!r} delay {delay_s!r} generated "
                f"{len(modes)} CFO modes instead of the source-declared two"
            )
        for mode in modes:
            delay_prior_cost = (
                0.5
                * ((delay_s - source.config.delay_prior_mean_s) / source.config.delay_prior_sigma_s)
                ** 2
            )
            hypothesis = SingleSatelliteHypothesis(
                hypothesis_id=canonical_digest(
                    {
                        "catalog_number": target_catalog_number,
                        "delay_s": delay_s,
                        "cfo_offset_hz": mode.cfo_offset_hz,
                        "prediction_epoch_transform_digest": transform.transform_digest,
                        "prediction_epoch_role": transform.role,
                        "algorithm": ALGORITHM,
                    }
                ),
                object_name=str(source.catalogue.names[source.catalogue_index]),
                catalog_number=target_catalog_number,
                delay_s=delay_s,
                cfo_offset_hz=mode.cfo_offset_hz,
                delay_prior_cost=delay_prior_cost,
                predictions=tuple(
                    PredictedProbeCfo(probe.probe_id, float(curve[index]))
                    for index, probe in enumerate(problem.probes)
                ),
            )
            decoded = decode_single_satellite(problem, hypothesis)
            state = raw_replay._StateEvaluation(
                hypothesis=hypothesis,
                proposal=mode,
                single_total_cost=decoded.objective.total_cost,
                single_delta_from_null=decoded.objective.delta_from_null,
                single_selected=decoded.selected,
                minimum_elevation_deg=minimum_elevation,
                maximum_elevation_deg=maximum_elevation,
            )
            generated.append((state, decoded))
    generated.sort(key=lambda item: raw_replay._state_sort_key(item[0]))
    expected_count = len(source.config.delay_grid) * source.config.modes_per_delay
    if len(generated) != expected_count:
        raise RuntimeError("fixed-NORAD arm did not exhaust the declared 41x2 state bank")
    serialized_states = [
        _serialize_state(state=state, decoded=decoded) for state, decoded in generated
    ]
    best_state, best_decoded = generated[0]
    elided = source.inventory.elided_clutter_constant
    full_null = best_decoded.objective.null_cost + elided
    full_total = best_decoded.objective.total_cost + elided
    invariant_delta = best_decoded.objective.delta_from_null
    if (invariant_delta < 0.0) != best_decoded.selected:
        raise RuntimeError("fixed-NORAD selected flag disagrees with its reduced objective")
    every_state_nonactivating = all(not item[1].selected for item in generated)
    return {
        "arm_id": transform.arm_id,
        "role": transform.role,
        "transform_digest": transform.transform_digest,
        "transform": transform.receipt,
        "common_digests": common_digests,
        "prediction_epoch_mapping": mapping_receipt,
        "finite_state_search": {
            "target_catalog_number": target_catalog_number,
            "delay_grid": list(source.config.delay_grid),
            "modes_per_delay": source.config.modes_per_delay,
            "expected_generated_state_count": expected_count,
            "generated_state_count": len(generated),
            "declared_delay_grid_exhausted": True,
            "every_delay_generated_declared_cfo_mode_count": True,
            "generated_data_proposed_cfo_mode_bank_exhausted": True,
            "state_bank_pruned": False,
            "finite_declared_search_exact": True,
            "all_generated_states_nonactivating": every_state_nonactivating,
            "state_bank_digest": canonical_digest(serialized_states),
            "states": serialized_states,
        },
        "decision": {
            "activation_witness_found": best_decoded.selected,
            "selected_catalog_numbers": [target_catalog_number] if best_decoded.selected else [],
            "best_hypothesis_id": best_state.hypothesis.hypothesis_id,
            "best_delay_s": best_state.hypothesis.delay_s,
            "best_cfo_offset_hz": best_state.hypothesis.cfo_offset_hz,
            "full_persisted_inventory_objective": {
                "null_cost": full_null,
                "total_cost": full_total,
                "delta_from_null": invariant_delta,
                "modeled_null_cost": best_decoded.objective.null_cost,
                "modeled_total_cost": best_decoded.objective.total_cost,
                "decision_invariant_delta_from_null": invariant_delta,
                "constant_elided_from_exact_decision_problem": elided,
            },
        },
    }


def _hypothesis_from_document(raw: dict[str, Any]) -> SingleSatelliteHypothesis:
    predictions = tuple(
        PredictedProbeCfo(**_object(item, "serialized prediction"))
        for item in _list(raw.get("predictions"), "serialized predictions")
    )
    eligible_raw = raw.get("eligible_probe_ids")
    eligible = None if eligible_raw is None else tuple(_list(eligible_raw, "eligible probes"))
    return SingleSatelliteHypothesis(
        hypothesis_id=str(raw.get("hypothesis_id", "")),
        object_name=str(raw.get("object_name", "")),
        catalog_number=_integer(raw.get("catalog_number"), "state catalog number", minimum=1),
        delay_s=_finite(raw.get("delay_s"), "state delay"),
        cfo_offset_hz=_finite(raw.get("cfo_offset_hz"), "state CFO offset"),
        delay_prior_cost=_finite_nonnegative(raw.get("delay_prior_cost"), "delay prior cost"),
        predictions=predictions,
        eligible_probe_ids=eligible,
    )


def _validate_mapping(
    *,
    arm: dict[str, Any],
    persisted: tuple[dict[str, Any], ...],
    problem: SatelliteActivityProblem,
    transform: paired._ArmTransform,
) -> str:
    receipt = _object(arm.get("prediction_epoch_mapping"), "arm prediction mapping")
    if set(receipt) != {"arm_id", "transform_digest", "mapping", "mapping_digest"}:
        raise ValueError("arm prediction mapping has missing or extra fields")
    payload = {key: receipt[key] for key in ("arm_id", "transform_digest", "mapping")}
    if receipt.get("mapping_digest") != canonical_digest(payload):
        raise ValueError("arm prediction mapping digest does not recompute")
    if receipt.get("arm_id") != arm.get("arm_id") or receipt.get("transform_digest") != arm.get(
        "transform_digest"
    ):
        raise ValueError("arm prediction mapping provenance is inconsistent")
    rows = _list(receipt.get("mapping"), "arm mapping rows")
    if len(rows) != len(persisted):
        raise ValueError("arm prediction mapping has the wrong probe count")
    probe_by_id = {item.probe_id: item for item in problem.probes}
    semantic = []
    for raw_row, expected in zip(rows, persisted, strict=True):
        row = _object(raw_row, "arm mapping row")
        expected_fields = {
            "probe_id",
            "observation_utc_ns",
            "source_prediction_time_s",
            "source_prediction_utc_ns",
            "observation_cell_index",
            "prediction_time_s",
            "prediction_utc_ns",
            "prediction_cell_index",
            "within_activity_cell_offset_ns",
        }
        if set(row) != expected_fields:
            raise ValueError("arm mapping row has missing or extra fields")
        probe_id = str(expected["probe_id"])
        probe = probe_by_id[probe_id]
        prediction_cell = (
            probe.cell_index
            if transform.plan is None
            else transform.plan.prediction_cell_for_observation_cell(probe.cell_index)
        )
        expected_prediction_time = (
            expected["source_prediction_time_s"]
            + (prediction_cell - probe.cell_index) * problem.grid.cell_duration_s
        )
        first_utc_ns = expected["source_prediction_utc_ns"] - round(
            expected["source_prediction_time_s"] * 1e9
        )
        expected_prediction_utc = first_utc_ns + round(expected_prediction_time * 1e9)
        if (
            row["probe_id"] != probe_id
            or row["observation_utc_ns"] != expected["estimate_utc_ns"]
            or row["source_prediction_time_s"] != expected["source_prediction_time_s"]
            or row["source_prediction_utc_ns"] != expected["source_prediction_utc_ns"]
            or row["observation_cell_index"] != probe.cell_index
            or row["prediction_cell_index"] != prediction_cell
            or row["prediction_time_s"] != expected_prediction_time
            or row["prediction_utc_ns"] != expected_prediction_utc
            or row["within_activity_cell_offset_ns"] != expected["within_activity_cell_offset_ns"]
        ):
            raise ValueError("arm mapping disagrees with source epochs or frozen transform")
        semantic.append(
            [probe_id, prediction_cell, expected_prediction_time, expected_prediction_utc]
        )
    return canonical_digest(semantic)


def _recompute_arm(
    *,
    arm: dict[str, Any],
    problem: SatelliteActivityProblem,
    persisted: tuple[dict[str, Any], ...],
    transform: paired._ArmTransform,
    target_catalog_number: int,
    delay_grid: tuple[float, ...],
    modes_per_delay: int,
    elided_constant: float,
) -> tuple[dict[str, float], str, bool]:
    if (
        arm.get("arm_id") != transform.arm_id
        or arm.get("role") != transform.role
        or arm.get("transform_digest") != transform.transform_digest
        or canonical_digest(_object(arm.get("transform"), "emitted arm transform"))
        != canonical_digest(transform.receipt)
    ):
        raise ValueError("emitted arm differs from its regenerated frozen transform")
    mapping_digest = _validate_mapping(
        arm=arm,
        persisted=persisted,
        problem=problem,
        transform=transform,
    )
    search = _object(arm.get("finite_state_search"), "arm finite-state search")
    states_raw = _list(search.get("states"), "arm states")
    expected_count = len(delay_grid) * modes_per_delay
    exact_flags = (
        search.get("target_catalog_number") == target_catalog_number,
        search.get("delay_grid") == list(delay_grid),
        search.get("modes_per_delay") == modes_per_delay,
        search.get("expected_generated_state_count") == expected_count,
        search.get("generated_state_count") == expected_count,
        len(states_raw) == expected_count,
        search.get("declared_delay_grid_exhausted") is True,
        search.get("every_delay_generated_declared_cfo_mode_count") is True,
        search.get("generated_data_proposed_cfo_mode_bank_exhausted") is True,
        search.get("state_bank_pruned") is False,
        search.get("finite_declared_search_exact") is True,
        search.get("state_bank_digest") == canonical_digest(states_raw),
    )
    if not all(exact_flags):
        raise ValueError("arm does not prove its exact unpruned 41x2 finite state bank")
    evaluated: list[tuple[raw_replay._StateEvaluation, Any]] = []
    counts = {value.hex(): 0 for value in delay_grid}
    for raw_state in states_raw:
        state = _object(raw_state, "serialized arm state")
        hypothesis = _hypothesis_from_document(
            _object(state.get("hypothesis"), "serialized hypothesis")
        )
        if hypothesis.catalog_number != target_catalog_number:
            raise ValueError("arm state changes the fixed target NORAD")
        delay_key = hypothesis.delay_s.hex()
        if delay_key not in counts:
            raise ValueError("arm state delay lies outside the frozen grid")
        counts[delay_key] += 1
        proposal = raw_replay._OffsetMode(
            cfo_offset_hz=_finite(
                _object(state.get("proposal"), "serialized proposal").get("cfo_offset_hz"),
                "proposal CFO offset",
            ),
            support_group_count=_integer(
                _object(state.get("proposal"), "serialized proposal").get("support_group_count"),
                "proposal support groups",
            ),
            support_probe_count=_integer(
                _object(state.get("proposal"), "serialized proposal").get("support_probe_count"),
                "proposal support probes",
            ),
        )
        if proposal.cfo_offset_hz != hypothesis.cfo_offset_hz:
            raise ValueError("arm proposal and hypothesis CFO offsets differ")
        decoded = decode_single_satellite(problem, hypothesis)
        if canonical_digest(asdict(decoded)) != canonical_digest(
            _object(state.get("decoded"), "serialized decoded decision")
        ):
            raise ValueError("arm state decoded decision or objective does not recompute")
        evaluation = raw_replay._StateEvaluation(
            hypothesis=hypothesis,
            proposal=proposal,
            single_total_cost=decoded.objective.total_cost,
            single_delta_from_null=decoded.objective.delta_from_null,
            single_selected=decoded.selected,
            minimum_elevation_deg=_finite(
                state.get("minimum_elevation_deg"), "state minimum elevation"
            ),
            maximum_elevation_deg=_finite(
                state.get("maximum_elevation_deg"), "state maximum elevation"
            ),
        )
        evaluated.append((evaluation, decoded))
    if set(counts.values()) != {modes_per_delay}:
        raise ValueError("arm does not serialize exactly two CFO modes at every delay")
    ordered = sorted(evaluated, key=lambda item: raw_replay._state_sort_key(item[0]))
    serialized_ids = [
        _object(item, "serialized state").get("hypothesis", {}).get("hypothesis_id")
        for item in states_raw
    ]
    recomputed_ids = [item[0].hypothesis.hypothesis_id for item in ordered]
    if serialized_ids != recomputed_ids or len(set(recomputed_ids)) != expected_count:
        raise ValueError("arm state ordering or hypothesis identity does not recompute")
    best_state, best = ordered[0]
    full_null = best.objective.null_cost + elided_constant
    full_total = best.objective.total_cost + elided_constant
    objective = {
        "null_cost": full_null,
        "total_cost": full_total,
        "delta_from_null": best.objective.delta_from_null,
        "modeled_null_cost": best.objective.null_cost,
        "modeled_total_cost": best.objective.total_cost,
        "best_hypothesis_id": best_state.hypothesis.hypothesis_id,
        "best_object_name": best_state.hypothesis.object_name,
        "best_delay_s": best_state.hypothesis.delay_s,
        "best_cfo_offset_hz": best_state.hypothesis.cfo_offset_hz,
        "best_delay_prior_cost": best_state.hypothesis.delay_prior_cost,
        "best_mode_support_group_count": best_state.proposal.support_group_count,
        "best_mode_support_probe_count": best_state.proposal.support_probe_count,
        "best_minimum_elevation_deg": best_state.minimum_elevation_deg,
        "best_maximum_elevation_deg": best_state.maximum_elevation_deg,
        "best_selected": best.selected,
    }
    decision = _object(arm.get("decision"), "arm decision")
    serialized_objective = _object(
        decision.get("full_persisted_inventory_objective"), "arm full objective"
    )
    if (
        serialized_objective.get("null_cost") != objective["null_cost"]
        or serialized_objective.get("total_cost") != objective["total_cost"]
        or serialized_objective.get("delta_from_null") != objective["delta_from_null"]
        or serialized_objective.get("modeled_null_cost") != objective["modeled_null_cost"]
        or serialized_objective.get("modeled_total_cost") != objective["modeled_total_cost"]
        or serialized_objective.get("decision_invariant_delta_from_null")
        != objective["delta_from_null"]
        or serialized_objective.get("constant_elided_from_exact_decision_problem")
        != elided_constant
        or decision.get("best_hypothesis_id") != best_state.hypothesis.hypothesis_id
        or decision.get("best_delay_s") != best_state.hypothesis.delay_s
        or decision.get("best_cfo_offset_hz") != best_state.hypothesis.cfo_offset_hz
        or decision.get("activation_witness_found") is not best.selected
        or decision.get("selected_catalog_numbers")
        != ([target_catalog_number] if best.selected else [])
    ):
        raise ValueError("arm minimum decision or primitive full objective does not recompute")
    all_nonactivating = all(not item[1].selected for item in ordered)
    if search.get("all_generated_states_nonactivating") is not all_nonactivating:
        raise ValueError("arm all-state null certificate does not recompute")
    return objective, mapping_digest, all_nonactivating


def adjudicate_fixed_norad_arms(
    *,
    arms: tuple[dict[str, Any], ...],
    common: dict[str, Any],
) -> dict[str, Any]:
    """Independently rebuild transforms, mappings, every state decision, and the gate."""

    reasons: list[str] = []
    try:
        if set(common) != {
            "digests",
            "raw_problem",
            "objective",
            "search_universe",
            "producer",
            "source_binding",
            "family_plan",
        }:
            raise ValueError("fixed-NORAD common document inventory is incomplete")
        digests = _object(common.get("digests"), "fixed-NORAD common digests")
        document_by_digest = {
            "raw_problem_digest": "raw_problem",
            "objective_digest": "objective",
            "search_universe_digest": "search_universe",
            "producer_digest": "producer",
            "source_binding_digest": "source_binding",
            "family_plan_digest": "family_plan",
        }
        if set(digests) != set(document_by_digest):
            raise ValueError("fixed-NORAD common digest inventory is incomplete")
        for digest_field, document_field in document_by_digest.items():
            if _canonical_sha256(digests[digest_field], digest_field) != canonical_digest(
                common[document_field]
            ):
                raise ValueError(f"fixed-NORAD {document_field} digest does not recompute")
        if common.get("producer") != producer_implementation_manifest():
            raise ValueError("fixed-NORAD producer implementation manifest is not current")
        problem_payload = _object(common.get("raw_problem"), "fixed-NORAD raw problem")
        problem = _problem_from_payload(problem_payload)
        persisted = tuple(
            _object(item, "persisted probe UTC")
            for item in _list(
                problem_payload.get("persisted_probe_utc"), "persisted probe UTC inventory"
            )
        )
        objective_document = _object(common.get("objective"), "fixed-NORAD objective")
        if objective_document.get("association_costs") != asdict(problem.costs):
            raise ValueError("fixed-NORAD objective costs differ from the raw problem")
        elided = _finite_nonnegative(
            problem_payload.get("constant_elided_from_exact_decision_problem"),
            "fixed-NORAD elided objective constant",
        )
        universe = _object(common.get("search_universe"), "fixed-NORAD universe")
        target = _integer(universe.get("target_catalog_number"), "fixed target", minimum=1)
        configuration = _object(universe.get("configuration"), "fixed-NORAD configuration")
        config = _raw_config(configuration)
        delay_grid = config.delay_grid
        family = _object(common.get("family_plan"), "fixed-NORAD family plan")
        if family.get("schema") != FAMILY_PLAN_SCHEMA or family.get("algorithm") != ALGORITHM:
            raise ValueError("fixed-NORAD family schema or algorithm is invalid")
        for digest_field in document_by_digest:
            if digest_field == "family_plan_digest":
                continue
            if family.get(digest_field) != digests[digest_field]:
                raise ValueError("fixed-NORAD family plan differs from common digests")
        control_indices_raw = _list(family.get("control_indices"), "control indices")
        control_indices = tuple(_integer(item, "control index") for item in control_indices_raw)
        if (
            len(control_indices) < MINIMUM_CONTROL_COUNT
            or len(control_indices) > MAXIMUM_CONTROL_COUNT
            or control_indices != tuple(sorted(set(control_indices)))
        ):
            raise ValueError("fixed-NORAD family needs four to sixteen unique sorted controls")
        selection_context = {
            key: value
            for key, value in family.items()
            if key
            not in {
                "arms",
                "fixed_target_frozen_before_arm_scoring",
                "family_frozen_before_arm_scoring",
                "all_control_plans_built_before_arm_scoring",
            }
        }
        if (
            family.get("family_frozen_before_arm_scoring") is not True
            or family.get("all_control_plans_built_before_arm_scoring") is not True
            or family.get("fixed_target_frozen_before_arm_scoring") is not True
        ):
            raise ValueError("fixed-NORAD family was not atomically frozen")
        transforms = paired._freeze_arm_transforms(
            problem=cast(
                paired.MultipathSatelliteActivityProblem,
                SimpleNamespace(grid=problem.grid),
            ),
            selection_context_digest=canonical_digest(selection_context),
            control_indices=control_indices,
            maximum_delay_support_s=max(abs(config.delay_min_s), abs(config.delay_max_s)),
        )
        planned_arms = _list(family.get("arms"), "planned arms")
        expected_plans = [
            {
                "arm_id": item.arm_id,
                "role": item.role,
                "transform_digest": item.transform_digest,
                "transform": item.receipt,
            }
            for item in transforms
        ]
        if canonical_digest(planned_arms) != canonical_digest(expected_plans):
            raise ValueError("fixed-NORAD arm plans do not regenerate exactly")
        if len(arms) != len(transforms):
            raise ValueError("fixed-NORAD artifact omitted or added an arm")
        if any(arm.get("common_digests") != digests for arm in arms):
            raise ValueError("fixed-NORAD arm differs from the common digests")
        objectives = []
        mappings = []
        all_null = []
        for arm, transform in zip(arms, transforms, strict=True):
            arm_objective, mapping_digest, arm_all_null = _recompute_arm(
                arm=arm,
                problem=problem,
                persisted=persisted,
                transform=transform,
                target_catalog_number=target,
                delay_grid=delay_grid,
                modes_per_delay=config.modes_per_delay,
                elided_constant=elided,
            )
            objectives.append(arm_objective)
            mappings.append(mapping_digest)
            all_null.append(arm_all_null)
        if len(set(mappings)) != len(mappings):
            raise ValueError("fixed-NORAD arms have duplicate semantic epoch mappings")
        if len({item["modeled_null_cost"].hex() for item in objectives}) != 1:
            raise ValueError("fixed-NORAD arms do not share one bit-identical null objective")
        source_binding = _object(common.get("source_binding"), "fixed-NORAD source binding")
        source_minimum = _object(
            source_binding.get("target_minimum"), "bounded-source target minimum"
        )
        identity_arm = arms[0]
        identity_objective = objectives[0]
        if (
            identity_arm.get("role") != "identity"
            or source_minimum.get("catalog_number") != target
            or source_minimum.get("object_name") != universe.get("object_name")
            or source_minimum.get("object_name") != identity_objective["best_object_name"]
            or source_minimum.get("catalogue_index") != universe.get("catalogue_index")
            or source_minimum.get("generated_state_count")
            != len(delay_grid) * config.modes_per_delay
            or source_minimum.get("configured_satellite_cost") != problem.costs.satellite_cost
            or source_minimum.get("best_single_total_cost")
            != identity_objective["modeled_total_cost"]
            or source_minimum.get("best_single_delta_from_null")
            != identity_objective["delta_from_null"]
            or source_minimum.get("best_single_selected") is not identity_objective["best_selected"]
            or source_minimum.get("best_delay_s") != identity_objective["best_delay_s"]
            or source_minimum.get("best_cfo_offset_hz") != identity_objective["best_cfo_offset_hz"]
            or source_minimum.get("delay_prior_cost") != identity_objective["best_delay_prior_cost"]
            or source_minimum.get("mode_support_group_count")
            != identity_objective["best_mode_support_group_count"]
            or source_minimum.get("mode_support_probe_count")
            != identity_objective["best_mode_support_probe_count"]
            or source_minimum.get("minimum_elevation_deg")
            != identity_objective["best_minimum_elevation_deg"]
            or source_minimum.get("maximum_elevation_deg")
            != identity_objective["best_maximum_elevation_deg"]
        ):
            raise ValueError("identity arm does not reproduce the bounded V2 target minimum")
        source_hypothesis_id = source_minimum.get("best_hypothesis_id")
        if not isinstance(source_hypothesis_id, str) or not source_hypothesis_id:
            raise ValueError("bounded V2 target minimum has no source hypothesis identity")
        identity_source_hypothesis_crosswalk = {
            "source_best_hypothesis_id": source_hypothesis_id,
            "fixed_target_identity_hypothesis_id": identity_objective["best_hypothesis_id"],
            "identifiers_differ_because_wrapper_binds_prediction_transform": (
                source_hypothesis_id != identity_objective["best_hypothesis_id"]
            ),
            "every_shared_source_row_primitive_reproduced": True,
        }
        minimum_advantage = _finite_nonnegative(
            family.get("minimum_advantage_cost"), "frozen minimum advantage"
        )
        target_selection_causality_verified = family.get("target_selection_causality_verified")
        all_catalogue_selection_matched = family.get("all_catalogue_selection_matched_in_controls")
        threshold_calibrated = family.get("advantage_threshold_calibrated")
        preregistration_verified = family.get("external_preregistration_verified")
        if any(
            value is not False
            for value in (
                target_selection_causality_verified,
                all_catalogue_selection_matched,
                threshold_calibrated,
                preregistration_verified,
            )
        ):
            raise ValueError(
                "fixed-NORAD v1 must fail closed on target, catalogue, threshold, and "
                "preregistration authority"
            )

        source_path_raw = source_binding.get("source_artifact_path")
        if not isinstance(source_path_raw, str) or not source_path_raw:
            raise ValueError("fixed-NORAD source binding omits its source path")
        regenerated_source = _load_source(
            source_path=Path(source_path_raw),
            expected_source_digest=_canonical_sha256(
                source_binding.get("source_artifact_file_digest"),
                "fixed-NORAD source artifact digest",
            ),
            target_catalog_number=target,
        )
        if (
            canonical_digest(regenerated_source.source)
            != source_binding.get("source_artifact_content_digest")
            or source_binding.get("source_producer_implementation")
            != bounded.producer_implementation_manifest()
            or canonical_digest(_problem_payload(regenerated_source))
            != digests["raw_problem_digest"]
        ):
            raise ValueError("fixed-NORAD source or regenerated raw problem binding differs")
        regenerated_arms = tuple(
            _evaluate_arm(
                source=regenerated_source,
                target_catalog_number=target,
                transform=transform,
                common_digests=cast(dict[str, str], digests),
            )
            for transform in transforms
        )
        if canonical_digest(regenerated_arms) != canonical_digest(arms):
            raise ValueError(
                "fixed-NORAD emitted arms do not regenerate from bound raw/TLE/calibration bytes"
            )
    except (KeyError, IndexError, OSError, TypeError, ValueError) as error:
        reasons.append(str(error))
        return {
            "disposition": NOT_COMPARABLE,
            "comparable": False,
            "association_authority_comparable": False,
            "paired_gate_passed": False,
            "conditional_fixed_target_gate_passed": False,
            "conditional_comparison_completed": False,
            "conditional_control_test_failed": False,
            "relative_advantage_passed": False,
            "specificity_claimed": False,
            "reasons": reasons,
        }

    identity_improvement = max(0.0, -objectives[0]["delta_from_null"])
    control_rows = []
    for arm, objective, certified_null in zip(arms[1:], objectives[1:], all_null[1:], strict=True):
        improvement = max(0.0, -objective["delta_from_null"])
        control_rows.append(
            {
                "arm_id": arm["arm_id"],
                "delta_from_null": objective["delta_from_null"],
                "improvement_from_null": improvement,
                "activation_witness_found": objective["delta_from_null"] < 0.0,
                "finite_declared_search_exact": True,
                "finite_null_certified": certified_null,
            }
        )
    strongest = min(
        control_rows,
        key=lambda item: (-float(item["improvement_from_null"]), str(item["arm_id"])),
    )
    advantage = identity_improvement - float(strongest["improvement_from_null"])
    activating_controls = [
        str(item["arm_id"]) for item in control_rows if item["activation_witness_found"]
    ]
    controls_certified_null = all(item["finite_null_certified"] for item in control_rows)
    relative_passed = advantage > minimum_advantage
    if identity_improvement <= 0.0:
        disposition = IDENTITY_NONACTIVATION
        gate_reasons = ["the fixed-target identity arm did not beat its exact null"]
    elif activating_controls:
        disposition = CONTROL_ACTIVATION
        gate_reasons = ["at least one frozen non-affine control activated"]
    elif not controls_certified_null:
        disposition = CONTROL_NULL_NOT_CERTIFIED
        gate_reasons = ["a control lacks an exact all-state finite-null certificate"]
    elif not relative_passed:
        disposition = ADVANTAGE_BELOW_THRESHOLD
        gate_reasons = ["identity advantage is not strictly above the frozen threshold"]
    elif (
        not target_selection_causality_verified
        or not all_catalogue_selection_matched
        or not threshold_calibrated
        or not preregistration_verified
    ):
        disposition = TARGET_SELECTION_CAUSALITY_NOT_VERIFIED
        gate_reasons = [
            "fixed-target v1 has no authenticated pre-evidence target, all-catalogue matched "
            "controls, calibrated advantage threshold, or external preregistration"
        ]
    else:
        disposition = GATE_PASS
        gate_reasons = ["identity activated above threshold and every exact control was null"]
    conditional_gate_passed = (
        identity_improvement > 0.0
        and not activating_controls
        and controls_certified_null
        and relative_passed
    )
    conditional_control_test_failed = disposition in {
        IDENTITY_NONACTIVATION,
        CONTROL_ACTIVATION,
        CONTROL_NULL_NOT_CERTIFIED,
        ADVANTAGE_BELOW_THRESHOLD,
    }
    return {
        "disposition": disposition,
        "comparable": True,
        "association_authority_comparable": (
            target_selection_causality_verified
            and all_catalogue_selection_matched
            and threshold_calibrated
            and preregistration_verified
        ),
        "paired_gate_passed": False,
        "conditional_fixed_target_gate_passed": conditional_gate_passed,
        "conditional_comparison_completed": True,
        "conditional_control_test_failed": conditional_control_test_failed,
        "relative_advantage_passed": relative_passed,
        "specificity_claimed": False,
        "target_catalog_number": target,
        "identity_source_hypothesis_crosswalk": identity_source_hypothesis_crosswalk,
        "identity_arm_id": arms[0]["arm_id"],
        "identity_delta_from_null": objectives[0]["delta_from_null"],
        "identity_improvement_from_null": identity_improvement,
        "strongest_control_arm_id": strongest["arm_id"],
        "strongest_control_delta_from_null": strongest["delta_from_null"],
        "strongest_control_improvement_from_null": strongest["improvement_from_null"],
        "identity_advantage_over_strongest_control_cost": advantage,
        "minimum_advantage_cost": minimum_advantage,
        "comparison_is_strict": True,
        "target_selection_causality_verified": target_selection_causality_verified,
        "all_catalogue_selection_matched_in_controls": all_catalogue_selection_matched,
        "advantage_threshold_calibrated": threshold_calibrated,
        "external_preregistration_verified": preregistration_verified,
        "activating_control_arm_ids": activating_controls,
        "all_declared_control_nulls_certified": controls_certified_null,
        "controls": control_rows,
        "reasons": gate_reasons,
    }


def replay_raw_single_path_fixed_norad_paired_prediction_time(
    *,
    source_path: Path,
    expected_source_digest: str,
    target_catalog_number: int,
    control_indices: tuple[int, ...],
    family_label: str,
    minimum_advantage_cost: float = 0.0,
) -> dict[str, Any]:
    """Freeze and score a fixed-target identity/control family on one raw problem."""

    if isinstance(target_catalog_number, bool) or target_catalog_number < 1:
        raise ValueError("fixed target NORAD must be a positive integer")
    if not family_label:
        raise ValueError("fixed-NORAD family label must be nonempty")
    _finite_nonnegative(minimum_advantage_cost, "minimum advantage cost")
    ordered_controls = tuple(sorted(control_indices))
    if (
        len(ordered_controls) < MINIMUM_CONTROL_COUNT
        or len(ordered_controls) > MAXIMUM_CONTROL_COUNT
        or len(set(ordered_controls)) != len(ordered_controls)
        or any(isinstance(item, bool) or item < 0 for item in ordered_controls)
    ):
        raise ValueError("fixed-NORAD replay requires four to sixteen unique controls")
    source = _load_source(
        source_path=source_path,
        expected_source_digest=expected_source_digest,
        target_catalog_number=target_catalog_number,
    )
    problem = source.inventory.problem
    raw_problem = _problem_payload(source)
    objective = {
        "single_satellite_decoder_algorithm": "exact-single-satellite-semimarkov-v1",
        "association_costs": asdict(problem.costs),
        "score_calibration_schema": source.calibration_document.get("schema"),
        "score_calibration_file_digest": source.calibration_digest,
        "score_calibration_content_digest": canonical_digest(source.calibration_document),
        "constant_elision_is_decision_invariant": True,
        "structural_costs_calibrated": False,
    }
    search_universe = {
        "mode": "fixed-target-from-exhausted-bounded-v2-source-v1",
        "target_catalog_number": target_catalog_number,
        "object_name": str(source.catalogue.names[source.catalogue_index]),
        "catalogue_index": source.catalogue_index,
        "catalogue_search_performed": False,
        "fixed_target_frozen_before_arm_scoring": True,
        "configuration": asdict(source.config),
        "delay_grid": list(source.config.delay_grid),
        "cfo_mode_proposal": {
            "algorithm": "raw-residual-histogram-data-proposed-modes",
            "modes_per_delay": source.config.modes_per_delay,
            "same_policy_and_caps_in_every_arm": True,
            "arm_values_may_differ_only_because_prediction_epochs_differ": True,
        },
        "expected_state_count_per_arm": len(source.config.delay_grid)
        * source.config.modes_per_delay,
        "state_bank_pruning_permitted": False,
        "tle_digest": source.tle_digest,
        "observer": source.observer.model_dump(mode="json"),
    }
    source_binding = {
        "schema": SOURCE_SCHEMA,
        "algorithm": SOURCE_ALGORITHM,
        "source_artifact_path": str(source.source_path),
        "source_artifact_file_digest": source.source_digest,
        "source_artifact_content_digest": canonical_digest(source.source),
        "source_producer_implementation": bounded.producer_implementation_manifest(),
        "session_id": source.dataset["capture"]["session_id"],
        "recording_manifest_digest": source.dataset["capture"]["recording_manifest_digest"],
        "window": {
            "start_s": source.start_s,
            "end_s": source.end_s,
            "start_utc_ns": source.window_start_utc_ns,
            "end_utc_ns": source.window_end_utc_ns,
            "cell_count": problem.grid.cell_count,
        },
        "target_minimum": dict(source.target_row),
    }
    producer = producer_implementation_manifest()
    preliminary = {
        "raw_problem_digest": canonical_digest(raw_problem),
        "objective_digest": canonical_digest(objective),
        "search_universe_digest": canonical_digest(search_universe),
        "producer_digest": canonical_digest(producer),
        "source_binding_digest": canonical_digest(source_binding),
    }
    selection_context = {
        "schema": FAMILY_PLAN_SCHEMA,
        "algorithm": ALGORITHM,
        "family_label": family_label,
        "session_id": source.dataset["capture"]["session_id"],
        "recording_manifest_digest": source.dataset["capture"]["recording_manifest_digest"],
        **preliminary,
        "window": {
            "start_s": source.start_s,
            "cell_duration_s": problem.grid.cell_duration_s,
            "cell_count": problem.grid.cell_count,
            "minimum_active_cells": problem.grid.minimum_active_cells,
        },
        "fixed_target_catalog_number": target_catalog_number,
        "identity_arm_id": "identity",
        "control_indices": list(ordered_controls),
        "minimum_advantage_cost": minimum_advantage_cost,
        "target_selection_causality_verified": False,
        "all_catalogue_selection_matched_in_controls": False,
        "advantage_threshold_calibrated": False,
        "external_preregistration_verified": False,
        "comparison": "identity improvement strictly greater than strongest control",
        "require_every_control_to_be_an_exact_finite_null": True,
        "all_declared_arms_must_be_emitted": True,
    }
    # The frozen permutation builder deliberately raises when the source
    # geometry cannot support its non-affine displacement constraints.
    transforms = paired._freeze_arm_transforms(
        problem=cast(
            paired.MultipathSatelliteActivityProblem,
            SimpleNamespace(grid=problem.grid),
        ),
        selection_context_digest=canonical_digest(selection_context),
        control_indices=ordered_controls,
        maximum_delay_support_s=max(abs(source.config.delay_min_s), abs(source.config.delay_max_s)),
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
        "fixed_target_frozen_before_arm_scoring": True,
        "target_selection_causality_verified": False,
        "all_catalogue_selection_matched_in_controls": False,
        "advantage_threshold_calibrated": False,
        "external_preregistration_verified": False,
        "family_frozen_before_arm_scoring": True,
        "all_control_plans_built_before_arm_scoring": True,
    }
    common_digests = {**preliminary, "family_plan_digest": canonical_digest(family_plan)}
    common = {
        "digests": common_digests,
        "raw_problem": raw_problem,
        "objective": objective,
        "search_universe": search_universe,
        "producer": producer,
        "source_binding": source_binding,
        "family_plan": family_plan,
    }
    arms = tuple(
        _evaluate_arm(
            source=source,
            target_catalog_number=target_catalog_number,
            transform=transform,
            common_digests=common_digests,
        )
        for transform in transforms
    )
    if canonical_digest(_problem_payload(source)) != common_digests["raw_problem_digest"]:
        raise RuntimeError("shared raw problem changed while fixed-NORAD arms were evaluated")
    adjudication = adjudicate_fixed_norad_arms(arms=arms, common=common)
    if not adjudication.get("comparable"):
        raise RuntimeError(
            "fresh fixed-NORAD artifact failed internal re-adjudication: "
            + "; ".join(str(item) for item in adjudication.get("reasons", ()))
        )
    document: dict[str, Any] = {
        "schema": OUTPUT_SCHEMA,
        "algorithm": ALGORITHM,
        "research_only": True,
        "candidate_only": True,
        "association_not_tracking": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "catalogue_search_performed": False,
        "fixed_target_frozen_before_arm_scoring": True,
        "target_selection_causality_verified": False,
        "all_catalogue_selection_matched_in_controls": False,
        "advantage_threshold_calibrated": False,
        "external_preregistration_verified": False,
        "all_arms_share_one_loaded_raw_problem": True,
        "all_arms_share_one_objective": True,
        "all_arms_share_one_finite_search_universe": True,
        "only_prediction_epoch_mapping_varies_between_arms": True,
        "all_declared_arms_emitted": True,
        "continuous_nuisance_space_exhausted": False,
        "pre_acquisition_cap_inventory_complete": False,
        "physical_signal_inventory_complete": False,
        "common": common,
        "input": {
            "session_id": source.dataset["capture"]["session_id"],
            "recording_manifest_digest": source.dataset["capture"]["recording_manifest_digest"],
            "source_artifact_path": str(source.source_path),
            "source_artifact_file_digest": source.source_digest,
            "source_artifact_content_digest": canonical_digest(source.source),
            "duration_inputs": [
                {
                    "path_id": source.dataset["capture"]["stream_id"],
                    "path": str(source.dataset_path),
                    "file_digest": source.dataset_digest,
                    "pilot_scan_path": str(source.inventory.scan_path.resolve()),
                    "pilot_scan_digest": source.inventory.scan_digest,
                    "pilot_scan_content_digest": canonical_digest(
                        _read_json(source.inventory.scan_path)
                    ),
                }
            ],
            "score_calibration_path": str(source.calibration_path),
            "score_calibration_digest": source.calibration_digest,
            "tle_path": str(source.tle_path),
            "tle_digest": source.tle_digest,
        },
        "window": {
            "start_s": source.start_s,
            "end_s": source.end_s,
            "start_utc_ns": source.window_start_utc_ns,
            "end_utc_ns": source.window_end_utc_ns,
            "cell_duration_s": problem.grid.cell_duration_s,
            "cell_count": problem.grid.cell_count,
            "minimum_active_duration_s": source.config.minimum_active_duration_s,
            "minimum_active_cells": source.config.minimum_active_cells,
            "probe_epoch": "source_scheduled_probe_start",
        },
        "arms": list(arms),
        "adjudication": adjudication,
        "caveats": [
            "the target NORAD was fixed from one exhausted bounded V2 source before scoring",
            (
                "a post-hoc fixed target does not calibrate catalogue look-elsewhere and cannot "
                "qualify a cross-dwell association"
            ),
            "the exact 41x2 bank is discrete and data-proposed, not continuous-nuisance exact",
            "multiple controls from one capture are dependent and form one session replicate",
            "the strongest control is not a p-value or false-positive-rate estimate",
            "upstream retained-candidate caps can saturate",
            "TLE bytes are bound but snapshot acquisition causality is qualified separately",
            "observer coordinates are explicit but not capture-bound authority",
            "a passed fixed-target diagnostic is neither spacecraft identity nor tracking",
        ],
    }
    document["payload_content_digest"] = canonical_digest(document)
    return document


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-artifact", type=Path, required=True)
    parser.add_argument("--source-artifact-sha256", required=True)
    parser.add_argument("--target-catalog-number", type=int, required=True)
    parser.add_argument("--control-index", action="append", type=int, required=True)
    parser.add_argument("--family-label", required=True)
    parser.add_argument("--minimum-advantage-cost", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    document = replay_raw_single_path_fixed_norad_paired_prediction_time(
        source_path=arguments.source_artifact,
        expected_source_digest=arguments.source_artifact_sha256,
        target_catalog_number=arguments.target_catalog_number,
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
