#!/usr/bin/env python3
"""Freeze a pre-evidence Starlink association and tracking qualification plan.

This research-only freezer deliberately has no corpus discovery.  It reads only
the specification named by the caller and the four pre-evidence byte sources
named by that specification: a TLE snapshot, a score calibration, a TLE
authority receipt, and a chronology receipt.  In particular, it never accepts
or follows a future duration-dataset, PilotScan, recording, dwell, or result
path.

The resulting manifest freezes a full-catalogue search in an identity arm and
exactly twenty non-affine prediction-time controls.  Those controls test
catalogue/time specificity conditional on the captured RF; they do not
estimate a capture-wide presence false-positive rate.  Nor are the controls
currently proven exchangeable with the identity arm, so their rank is only a
descriptive diagnostic and is not a permutation p-value.  Separate natural-null
and positive-sensitivity qualifications remain mandatory before association
can be promoted.

No output from this tool identifies a spacecraft or establishes a track.  The
receipt checks below are structural and chronological, not cryptographic
authentication of an external authority.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import re
import sys
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, cast

from leo.analysis.research.activity_block_permutation import (  # type: ignore[import-untyped]
    ALGORITHM_VERSION as BLOCK_PERMUTATION_ALGORITHM,
)
from leo.analysis.research.activity_block_permutation import (  # type: ignore[import-untyped]
    BLOCK_DURATION_S,
    build_activity_block_permutation,
)
from leo.analysis.research.satellite_activity import (  # type: ignore[import-untyped]
    ActivityGrid,
)
from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]
from leo.sky.propagation import parse_element_sets  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools import decide_raw_catalogue_null_vs_any as bounded  # noqa: E402
from tools import replay_raw_grouped_satellite_activity as raw_replay  # noqa: E402
from tools.raw_satellite_activity_search_configuration import (  # noqa: E402
    INPUT_SCHEMA,
    pilot_scan_search_configuration,
)

SPECIFICATION_SCHEMA = "org.leo.research.prospective-starlink-tracking-freeze-spec/v1"
PLAN_SCHEMA = "org.leo.research.prospective-starlink-tracking-plan/v1"
TLE_AUTHORITY_RECEIPT_SCHEMA = "org.leo.research.tle-snapshot-authority-receipt/v1"
CHRONOLOGY_RECEIPT_SCHEMA = "org.leo.research.prospective-starlink-plan-chronology-receipt/v1"
PRESENCE_NULL_RECEIPT_SCHEMA = "org.leo.research.capture-wide-presence-null-qualification/v1"
POSITIVE_SENSITIVITY_RECEIPT_SCHEMA = (
    "org.leo.research.capture-wide-positive-sensitivity-qualification/v1"
)
TARGET_LOCK_RECEIPT_SCHEMA = "org.leo.research.prospective-norad-target-lock/v1"
PREDICTION_CONFIRMATION_RECEIPT_SCHEMA = (
    "org.leo.research.prospective-norad-prediction-confirmation/v1"
)

ALGORITHM = "pre-evidence-full-catalogue-randomization-tracking-state-machine-v1"
WINDOW_POLICY_ALGORITHM = "first-sealed-fixed-offset-complete-raw-window-v1"
PRIMARY_PATH_POLICY_ALGORITHM = "exact-predeclared-capture-metadata-primary-path-v1"
COHORT_POLICY_ALGORITHM = "fixed-chronological-sealed-dwell-cohort-v1"
PRESENCE_NULL_QUALIFICATION_ALGORITHM = "capture-wide-full-catalogue-familywise-null-upper-bound-v1"
POSITIVE_SENSITIVITY_QUALIFICATION_ALGORITHM = (
    "capture-wide-known-positive-sensitivity-lower-bound-v1"
)
PAIRED_OUTPUT_SCHEMA = "org.leo.research.raw-full-catalogue-paired-prediction-time-specificity/v1"
PAIRED_ALGORITHM = "atomic-full-catalogue-exhaustive-single-path-prediction-time-specificity-v1"
PAIRED_IMPLEMENTATION_PATH = "tools/replay_raw_full_catalogue_paired_prediction_time_specificity.py"
RANDOMIZATION_FORMULA = (
    "(1 + count(control_best_improvement >= identity_best_improvement)) / (M + 1)"
)
CONTROL_INDICES = tuple(range(20))
CONTROL_COUNT = len(CONTROL_INDICES)
MAX_PRESENCE_QUALIFICATION_SAMPLE_COUNT = 2**63 - 1
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


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
    return cast(dict[str, Any], value)


def _file_digest(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError(f"cannot read digest-bound file {path}: {error}") from error


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _strict_keys(document: dict[str, Any], expected: set[str], label: str) -> None:
    if set(document) != expected:
        missing = sorted(expected - set(document))
        extra = sorted(set(document) - expected)
        raise ValueError(f"{label} fields differ: missing={missing!r} extra={extra!r}")


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _sha256(value: object, label: str) -> str:
    result = _nonempty(value, label)
    if SHA256_PATTERN.fullmatch(result) is None:
        raise ValueError(f"{label} must be a canonical lowercase SHA-256 digest")
    return result


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _presence_sample_count(value: object, label: str) -> int:
    count = _integer(value, label, minimum=1)
    if count > MAX_PRESENCE_QUALIFICATION_SAMPLE_COUNT:
        raise ValueError(f"{label} must be <= {MAX_PRESENCE_QUALIFICATION_SAMPLE_COUNT}")
    return count


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _positive(value: object, label: str) -> float:
    result = _finite(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result


def _probability(value: object, label: str, *, strictly_positive: bool = False) -> float:
    result = _finite(value, label)
    lower_ok = result > 0.0 if strictly_positive else result >= 0.0
    if not lower_ok or result > 1.0:
        interval = "(0, 1]" if strictly_positive else "[0, 1]"
        raise ValueError(f"{label} must lie in {interval}")
    return result


def _true(value: object, label: str) -> None:
    if value is not True:
        raise ValueError(f"{label} must be true")


def _false(value: object, label: str) -> None:
    if value is not False:
        raise ValueError(f"{label} must be false")


def _resolve_file(value: object, *, base_directory: Path, label: str) -> Path:
    raw = Path(_nonempty(value, f"{label} path"))
    path = raw if raw.is_absolute() else base_directory / raw
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{label} path cannot be resolved: {error}") from error
    if not resolved.is_file():
        raise ValueError(f"{label} path must name a file")
    return resolved


def _bound_file(
    value: object,
    *,
    base_directory: Path,
    label: str,
) -> tuple[Path, str]:
    reference = _object(value, f"{label} reference")
    _strict_keys(reference, {"path", "file_digest"}, f"{label} reference")
    path = _resolve_file(reference["path"], base_directory=base_directory, label=label)
    expected = _sha256(reference["file_digest"], f"{label} file digest")
    observed = _file_digest(path)
    if observed != expected:
        raise ValueError(f"{label} file digest mismatch: expected {expected}, observed {observed}")
    return path, observed


def _json_copy(value: Any, label: str) -> Any:
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must contain only finite JSON values") from error


def _raw_configuration(value: object) -> raw_replay.RawReplayConfig:
    document = _object(value, "raw replay configuration")
    expected = {item.name for item in fields(raw_replay.RawReplayConfig)}
    _strict_keys(document, expected, "raw replay configuration")
    config = raw_replay.RawReplayConfig(**document)
    if config.allow_left_censored or config.allow_right_censored:
        raise ValueError("prospective controls require uncensored activity boundaries")
    # This is the persisted raw timebase and the block-permutation primitive's
    # currently audited geometry.  A new plan schema is required to change it.
    if not math.isclose(config.cell_duration_s, 0.1, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("prospective v1 requires exact 100-ms activity cells")
    _ = config.delay_grid
    return config


def _validate_window_policy(
    value: object,
    *,
    config: raw_replay.RawReplayConfig,
) -> tuple[dict[str, Any], ActivityGrid]:
    policy = _object(value, "future dwell window policy")
    _strict_keys(
        policy,
        {
            "algorithm",
            "required_input_schema",
            "required_seal_status",
            "required_tuning_tag",
            "required_sky_frequency_hz",
            "start_offset_s",
            "duration_s",
            "scheduled_probe_count",
            "cell_count",
            "complete_scheduled_probe_inventory_required",
            "post_acquisition_persisted_inventory_untruncated_required",
            "pre_acquisition_candidate_inventory_complete",
            "physical_raw_candidate_inventory_complete",
            "upstream_candidate_cap_saturation_must_be_reported",
            "capture_clock_binding_required",
            "recording_manifest_digest_binding_required",
            "future_product_paths_predeclared",
            "primary_path",
        },
        "future dwell window policy",
    )
    if policy.get("algorithm") != WINDOW_POLICY_ALGORITHM:
        raise ValueError("future dwell window policy uses an unsupported algorithm")
    if policy.get("required_input_schema") != INPUT_SCHEMA:
        raise ValueError("future dwell window policy requires the wrong input schema")
    if policy.get("required_seal_status") != "sealed":
        raise ValueError("future evidence must come from a sealed dwell")
    _nonempty(policy.get("required_tuning_tag"), "future required tuning tag")
    _positive(policy.get("required_sky_frequency_hz"), "future required sky frequency")
    start_s = _finite(policy.get("start_offset_s"), "future window start offset")
    if start_s < 0.0:
        raise ValueError("future window start offset must be nonnegative")
    duration_s = _positive(policy.get("duration_s"), "future window duration")
    scheduled_probe_count = _integer(
        policy.get("scheduled_probe_count"), "future scheduled probe count", minimum=2
    )
    cell_count = _integer(policy.get("cell_count"), "future activity cell count", minimum=1)
    expected_cell_count = round(duration_s / config.cell_duration_s)
    if (
        not math.isclose(
            expected_cell_count * config.cell_duration_s,
            duration_s,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        or cell_count != expected_cell_count
    ):
        raise ValueError("future duration, cell duration, and cell count do not tile exactly")
    if (
        not math.isclose(start_s, 50.0, rel_tol=0.0, abs_tol=1e-12)
        or not math.isclose(duration_s, 10.0, rel_tol=0.0, abs_tol=1e-12)
        or scheduled_probe_count != 400
        or cell_count != 100
    ):
        raise ValueError(
            "prospective v1 freezes the predeclared [50, 60) 10-second/100-cell/400-probe window"
        )
    for field in (
        "complete_scheduled_probe_inventory_required",
        "post_acquisition_persisted_inventory_untruncated_required",
        "capture_clock_binding_required",
        "recording_manifest_digest_binding_required",
        "upstream_candidate_cap_saturation_must_be_reported",
    ):
        _true(policy.get(field), f"future window {field}")
    _false(
        policy.get("future_product_paths_predeclared"),
        "future product paths predeclared",
    )
    _false(
        policy.get("pre_acquisition_candidate_inventory_complete"),
        "pre-acquisition candidate inventory complete",
    )
    _false(
        policy.get("physical_raw_candidate_inventory_complete"),
        "physical raw candidate inventory complete",
    )
    primary_path = _object(policy.get("primary_path"), "primary receiver-path policy")
    _strict_keys(
        primary_path,
        {
            "algorithm",
            "path_id",
            "stream_id",
            "radio_id",
            "radio_serial",
            "receiver_id",
            "tuning_tag",
            "sky_frequency_hz",
            "path_scope_digest",
            "inferential_path_count",
            "score_based_path_selection_permitted",
            "other_receiver_paths_role",
            "all_path_inference_requires_separately_bound_producer",
        },
        "primary receiver-path policy",
    )
    if primary_path.get("algorithm") != PRIMARY_PATH_POLICY_ALGORITHM:
        raise ValueError("primary receiver-path policy uses an unsupported algorithm")
    stream_id = _nonempty(primary_path.get("stream_id"), "primary path stream ID")
    radio_id = _nonempty(primary_path.get("radio_id"), "primary path radio ID")
    radio_serial = _nonempty(primary_path.get("radio_serial"), "primary path radio serial")
    receiver_id = _integer(primary_path.get("receiver_id"), "primary path receiver ID")
    tuning_tag = _nonempty(primary_path.get("tuning_tag"), "primary path tuning tag")
    sky_frequency_hz = _positive(primary_path.get("sky_frequency_hz"), "primary path sky frequency")
    if tuning_tag != policy.get("required_tuning_tag") or sky_frequency_hz != float(
        policy["required_sky_frequency_hz"]
    ):
        raise ValueError("primary path frequency identity differs from the window policy")
    stable_path_tuple = [
        stream_id,
        radio_id,
        radio_serial,
        receiver_id,
        tuning_tag,
        sky_frequency_hz,
    ]
    path_id = _sha256(primary_path.get("path_id"), "primary path ID")
    if path_id != canonical_digest(stable_path_tuple):
        raise ValueError("primary path ID does not recompute from the stable path tuple")
    path_scope_payload = {
        "algorithm": PRIMARY_PATH_POLICY_ALGORITHM,
        "path_id": path_id,
        "stream_id": stream_id,
        "radio_id": radio_id,
        "radio_serial": radio_serial,
        "receiver_id": receiver_id,
        "tuning_tag": tuning_tag,
        "sky_frequency_hz": sky_frequency_hz,
    }
    if _sha256(primary_path.get("path_scope_digest"), "primary path-scope digest") != (
        canonical_digest(path_scope_payload)
    ):
        raise ValueError("primary path-scope digest does not recompute")
    if primary_path.get("inferential_path_count") != 1:
        raise ValueError("prospective single-path inference requires exactly one primary path")
    _false(
        primary_path.get("score_based_path_selection_permitted"),
        "score-based receiver-path selection permitted",
    )
    if primary_path.get("other_receiver_paths_role") != "noninferential-diagnostics-only":
        raise ValueError("nonprimary receiver paths must remain noninferential diagnostics")
    _true(
        primary_path.get("all_path_inference_requires_separately_bound_producer"),
        "all-path inference separately bound",
    )
    grid = ActivityGrid(
        start_s=start_s,
        cell_duration_s=config.cell_duration_s,
        cell_count=cell_count,
        minimum_active_cells=config.minimum_active_cells,
        allow_left_censored=False,
        allow_right_censored=False,
    )
    # Keep these locals intentionally evaluated so malformed JSON cannot hide
    # behind an otherwise valid ActivityGrid constructor.
    _ = scheduled_probe_count
    return _json_copy(policy, "future window policy"), grid


def _validate_catalogue_screen(value: object) -> dict[str, Any]:
    screen = _object(value, "full-catalogue screen")
    _strict_keys(
        screen,
        {
            "output_schema",
            "algorithm",
            "catalogue_name_prefix",
            "geometry_spacing_s",
            "full_window_visibility_required",
            "identity_partition_required",
            "every_eligible_catalogue_scored_on_complete_fine_bank",
            "shortlist_or_catalogue_pruning_permitted",
            "nuisance_state_pruning_permitted",
        },
        "full-catalogue screen",
    )
    if (
        screen.get("output_schema") != bounded.OUTPUT_SCHEMA_V2
        or screen.get("algorithm") != bounded.ALGORITHM_V2
    ):
        raise ValueError("prospective v1 requires bounded full-catalogue V2")
    _nonempty(screen.get("catalogue_name_prefix"), "catalogue name prefix")
    _positive(screen.get("geometry_spacing_s"), "catalogue geometry spacing")
    for field in (
        "full_window_visibility_required",
        "identity_partition_required",
        "every_eligible_catalogue_scored_on_complete_fine_bank",
    ):
        _true(screen.get(field), f"catalogue screen {field}")
    for field in (
        "shortlist_or_catalogue_pruning_permitted",
        "nuisance_state_pruning_permitted",
    ):
        _false(screen.get(field), f"catalogue screen {field}")
    return _json_copy(screen, "catalogue screen")


def _validate_paired_producer(value: object) -> dict[str, Any]:
    producer = _object(value, "paired full-catalogue producer")
    _strict_keys(
        producer,
        {
            "output_schema",
            "algorithm",
            "implementation_path",
            "implementation_manifest_digest",
            "implementation_binding_status",
        },
        "paired full-catalogue producer",
    )
    if (
        producer.get("output_schema") != PAIRED_OUTPUT_SCHEMA
        or producer.get("algorithm") != PAIRED_ALGORITHM
        or producer.get("implementation_path") != PAIRED_IMPLEMENTATION_PATH
    ):
        raise ValueError("paired full-catalogue producer identity differs from prospective v1")
    binding_status = producer.get("implementation_binding_status")
    digest = producer.get("implementation_manifest_digest")
    implementation_manifest: dict[str, Any] | None = None
    implementation_verified = False
    if binding_status == "pre-evidence-bound":
        expected_digest = _sha256(digest, "paired producer implementation-manifest digest")
        module = importlib.import_module(
            "tools.replay_raw_full_catalogue_paired_prediction_time_specificity"
        )
        if (
            getattr(module, "OUTPUT_SCHEMA", None) != PAIRED_OUTPUT_SCHEMA
            or getattr(module, "ALGORITHM", None) != PAIRED_ALGORITHM
        ):
            raise ValueError("current paired producer schema or algorithm differs from the plan")
        manifest_builder = getattr(module, "producer_implementation_manifest", None)
        if not callable(manifest_builder):
            raise ValueError("current paired producer has no implementation manifest")
        implementation_manifest = _object(
            manifest_builder(), "current paired producer implementation manifest"
        )
        if canonical_digest(implementation_manifest) != expected_digest:
            raise ValueError("paired producer implementation-manifest digest is not current")
        implementation_verified = True
    elif binding_status == "required-before-first-future-dwell":
        if digest is not None:
            raise ValueError("an unbound paired implementation digest slot must be null")
    else:
        raise ValueError("paired producer implementation binding status is unsupported")
    return {
        **_json_copy(producer, "paired full-catalogue producer"),
        "implementation_manifest": implementation_manifest,
        "implementation_manifest_digest_verified_current": implementation_verified,
    }


def _validate_randomization(
    value: object,
    *,
    proposal_digest: str,
    config: raw_replay.RawReplayConfig,
    grid: ActivityGrid,
    gamma_dwell_control_margin_cost: float,
) -> dict[str, Any]:
    randomization = _object(value, "prediction-time randomization")
    _strict_keys(
        randomization,
        {
            "algorithm",
            "control_indices",
            "block_duration_s",
            "maximum_delay_support_s",
            "randomization_p_value_formula",
            "randomization_exchangeability_verified",
            "rerun_full_catalogue_selection_in_every_arm",
            "same_observations_and_objective_in_every_arm",
            "only_prediction_epoch_mapping_varies_between_arms",
            "ties_count_against_identity",
        },
        "prediction-time randomization",
    )
    if randomization.get("algorithm") != BLOCK_PERMUTATION_ALGORITHM:
        raise ValueError("prediction-time randomization algorithm is unsupported")
    if not math.isclose(
        _positive(randomization.get("block_duration_s"), "control block duration"),
        BLOCK_DURATION_S,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("prediction-time controls must use exact half-second blocks")
    maximum_delay_support_s = _finite(
        randomization.get("maximum_delay_support_s"), "maximum delay support"
    )
    expected_delay_support = max(abs(config.delay_min_s), abs(config.delay_max_s))
    if maximum_delay_support_s < 0.0 or not math.isclose(
        maximum_delay_support_s,
        expected_delay_support,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("control delay support must equal the complete fine delay support")
    indices = tuple(
        _integer(item, "prediction-time control index")
        for item in _list(randomization.get("control_indices"), "control indices")
    )
    if indices != CONTROL_INDICES:
        raise ValueError("prospective v1 requires exactly control indices 0 through 19")
    if randomization.get("randomization_p_value_formula") != RANDOMIZATION_FORMULA:
        raise ValueError("randomization p-value formula differs from prospective v1")
    _false(
        randomization.get("randomization_exchangeability_verified"),
        "randomization exchangeability verified",
    )
    for field in (
        "rerun_full_catalogue_selection_in_every_arm",
        "same_observations_and_objective_in_every_arm",
        "only_prediction_epoch_mapping_varies_between_arms",
        "ties_count_against_identity",
    ):
        _true(randomization.get(field), f"prediction-time randomization {field}")

    selection_context_digest = canonical_digest(
        {
            "algorithm": ALGORITHM,
            "proposal_digest": proposal_digest,
            "role": "pre-evidence-full-catalogue-prediction-time-control-family",
        }
    )
    plans = tuple(
        build_activity_block_permutation(
            grid,
            session_key=selection_context_digest,
            control_index=index,
            maximum_delay_support_s=maximum_delay_support_s,
        )
        for index in indices
    )
    mappings = tuple(tuple(item.prediction_block_by_observation_block) for item in plans)
    digests = tuple(item.plan_digest for item in plans)
    if len(set(mappings)) != len(mappings) or len(set(digests)) != len(digests):
        raise ValueError("frozen control indices produced duplicate semantic controls")
    if any(item.diagnostics.mapping_is_affine for item in plans):
        raise RuntimeError("block-permutation primitive emitted an affine control")
    controls = [
        {
            "arm_id": f"control-{item.control_index:06d}",
            "role": "full_catalogue_prediction_time_control",
            "transform_digest": item.plan_digest,
            "transform": _json_copy(asdict(item), "block-permutation receipt"),
            "full_catalogue_selection_required": True,
        }
        for item in plans
    ]
    return {
        **_json_copy(randomization, "prediction-time randomization"),
        "control_count": len(indices),
        "arm_count": len(indices) + 1,
        "reserved_minimum_rank_fraction": 1.0 / (len(indices) + 1),
        "permutation_p_value": None,
        "selection_context_digest": selection_context_digest,
        "identity_arm": {
            "arm_id": "identity",
            "role": "full_catalogue_identity",
            "prediction_epoch_mapping_algorithm": "identity-prediction-epoch-map-v1",
            "full_catalogue_selection_required": True,
        },
        "control_arms": controls,
        "gate": {
            "comparison_statistic": "full-catalogue-best-improvement-from-exact-null",
            "reserved_rank_formula": RANDOMIZATION_FORMULA,
            "randomization_exchangeability_verified": False,
            "permutation_p_value": None,
            "ties_count_against_identity": True,
            (
                "identity_improvement_minus_strongest_control_improvement_"
                "must_be_strictly_greater_than"
            ): gamma_dwell_control_margin_cost,
            "identity_activation_required": True,
            "every_arm_exact_complete_catalogue_and_finite_state_search_required": True,
        },
    }


def _validate_presence_qualification(value: object) -> dict[str, Any]:
    qualification = _object(value, "presence qualification")
    _strict_keys(
        qualification,
        {
            "natural_capture_wide_null",
            "positive_sensitivity",
            "block_controls_calibrate_presence_false_positive_rate",
            "both_qualifications_required_before_association",
        },
        "presence qualification",
    )
    _false(
        qualification.get("block_controls_calibrate_presence_false_positive_rate"),
        "block controls calibrate presence false-positive rate",
    )
    _true(
        qualification.get("both_qualifications_required_before_association"),
        "both presence qualifications required before association",
    )
    null = _object(qualification.get("natural_capture_wide_null"), "natural-null gate")
    _strict_keys(
        null,
        {
            "receipt_schema",
            "algorithm",
            "minimum_independent_capture_count",
            "required_false_activation_count",
            "maximum_familywise_false_activation_rate",
            "confidence_level",
            "natural_unmodified_captures_required",
            "sources_disjoint_from_future_tracking_evidence",
        },
        "natural-null gate",
    )
    if (
        null.get("receipt_schema") != PRESENCE_NULL_RECEIPT_SCHEMA
        or null.get("algorithm") != PRESENCE_NULL_QUALIFICATION_ALGORITHM
    ):
        raise ValueError("natural-null qualification identity is unsupported")
    null_count = _presence_sample_count(
        null.get("minimum_independent_capture_count"),
        "natural-null independent capture count",
    )
    if null.get("required_false_activation_count") != 0:
        raise ValueError("prospective v1 natural-null qualification requires zero activations")
    maximum_false_activation_rate = _probability(
        null.get("maximum_familywise_false_activation_rate"),
        "natural-null maximum familywise false-activation rate",
        strictly_positive=True,
    )
    null_confidence = _probability(
        null.get("confidence_level"),
        "natural-null confidence level",
        strictly_positive=True,
    )
    null_failure_log = -math.inf if null_confidence == 1.0 else math.log1p(-null_confidence)
    null_upper_bound = -math.expm1(null_failure_log / null_count)
    if null_upper_bound > maximum_false_activation_rate:
        raise ValueError(
            "natural-null sample count cannot attain its one-sided "
            "Clopper-Pearson upper-bound target"
        )
    _true(null.get("natural_unmodified_captures_required"), "natural unmodified null captures")
    _true(
        null.get("sources_disjoint_from_future_tracking_evidence"),
        "natural-null source disjointness",
    )

    positive = _object(qualification.get("positive_sensitivity"), "positive-sensitivity gate")
    _strict_keys(
        positive,
        {
            "receipt_schema",
            "algorithm",
            "minimum_independent_capture_count",
            "required_detected_capture_count",
            "minimum_detection_probability_lower_bound",
            "confidence_level",
            "independent_known_positive_or_injection_required",
            "sources_disjoint_from_future_tracking_evidence",
        },
        "positive-sensitivity gate",
    )
    if (
        positive.get("receipt_schema") != POSITIVE_SENSITIVITY_RECEIPT_SCHEMA
        or positive.get("algorithm") != POSITIVE_SENSITIVITY_QUALIFICATION_ALGORITHM
    ):
        raise ValueError("positive-sensitivity qualification identity is unsupported")
    positive_count = _presence_sample_count(
        positive.get("minimum_independent_capture_count"),
        "positive-sensitivity independent capture count",
    )
    detected_count = _presence_sample_count(
        positive.get("required_detected_capture_count"),
        "positive-sensitivity required detected count",
    )
    if detected_count != positive_count:
        raise ValueError(
            "prospective v1 uses the exact all-success Clopper-Pearson sensitivity boundary"
        )
    minimum_detection_probability = _probability(
        positive.get("minimum_detection_probability_lower_bound"),
        "minimum detection-probability lower bound",
        strictly_positive=True,
    )
    positive_confidence = _probability(
        positive.get("confidence_level"),
        "positive-sensitivity confidence level",
        strictly_positive=True,
    )
    if minimum_detection_probability == 1.0:
        raise ValueError(
            "a finite positive-sensitivity sample cannot attain a lower-bound target of 1"
        )
    positive_log_lower_bound = (
        -math.inf if positive_confidence == 1.0 else math.log1p(-positive_confidence)
    ) / positive_count
    positive_lower_bound = math.exp(positive_log_lower_bound)
    if positive_log_lower_bound < math.log(minimum_detection_probability):
        raise ValueError(
            "positive-sensitivity sample count cannot attain its one-sided "
            "Clopper-Pearson lower-bound target"
        )
    _true(
        positive.get("independent_known_positive_or_injection_required"),
        "independent known positive or injection",
    )
    _true(
        positive.get("sources_disjoint_from_future_tracking_evidence"),
        "positive-sensitivity source disjointness",
    )
    return {
        **_json_copy(qualification, "presence qualification"),
        "mathematical_adjudication": {
            "method": "exact-one-sided-clopper-pearson-boundary-v1",
            "maximum_supported_independent_capture_count": (
                MAX_PRESENCE_QUALIFICATION_SAMPLE_COUNT
            ),
            "natural_null_zero_activation_upper_bound": null_upper_bound,
            "natural_null_target_attainable": True,
            "positive_all_detection_lower_bound": positive_lower_bound,
            "positive_all_detection_log_lower_bound": positive_log_lower_bound,
            "positive_sensitivity_target_attainable": True,
        },
    }


def _validate_decision_thresholds(value: object) -> dict[str, Any]:
    thresholds = _object(value, "pre-evidence decision thresholds")
    _strict_keys(
        thresholds,
        {
            "beta_association_cost",
            "mu_catalogue_runner_margin_cost",
            "gamma_cohort_control_margin_cost",
            "gamma_dwell_control_margin_cost",
            "all_comparisons_are_strict",
            "equality_passes_any_threshold",
            "thresholds_frozen_before_future_evidence",
        },
        "pre-evidence decision thresholds",
    )
    beta = _positive(thresholds.get("beta_association_cost"), "beta association cost")
    mu = _positive(
        thresholds.get("mu_catalogue_runner_margin_cost"),
        "mu catalogue runner-margin cost",
    )
    gamma_cohort = _positive(
        thresholds.get("gamma_cohort_control_margin_cost"),
        "gamma cohort control-margin cost",
    )
    gamma_dwell = _positive(
        thresholds.get("gamma_dwell_control_margin_cost"),
        "gamma dwell control-margin cost",
    )
    _true(thresholds.get("all_comparisons_are_strict"), "all threshold comparisons strict")
    _false(thresholds.get("equality_passes_any_threshold"), "threshold equality passes")
    _true(
        thresholds.get("thresholds_frozen_before_future_evidence"),
        "decision thresholds frozen before future evidence",
    )
    return {
        **_json_copy(thresholds, "pre-evidence decision thresholds"),
        "definitions": {
            "beta_association_cost": (
                "shared-NORAD cohort improvement over the exact cohort null must exceed beta"
            ),
            "mu_catalogue_runner_margin_cost": (
                "the selected catalogue minimum must beat the identity-arm runner by more than mu"
            ),
            "gamma_cohort_control_margin_cost": (
                "the two-dwell summed identity improvement must exceed the summed "
                "strongest-control improvement by more than gamma_cohort"
            ),
            "gamma_dwell_control_margin_cost": (
                "each dwell identity improvement must exceed its strongest full-catalogue control "
                "improvement by more than gamma_dwell"
            ),
        },
        "gate_expressions": {
            "discovery_dwell_count": 2,
            "each_identity_improvement": "> 0",
            "identity_arm_cross_dwell_winner_minus_runner_margin": (
                "> mu_catalogue_runner_margin_cost"
            ),
            "each_identity_minus_strongest_control_margin": "> gamma_dwell_control_margin_cost",
            "summed_identity_minus_summed_strongest_control_margin": (
                "> gamma_cohort_control_margin_cost"
            ),
            "shared_norad_association_improvement": "> beta_association_cost",
            "same_norad_and_distinct_sessions_required": True,
            "every_presence_sensitivity_and_threshold_calibration_receipt_required": True,
            "equality_passes": False,
        },
        "validated_values": {
            "beta_association_cost": beta,
            "mu_catalogue_runner_margin_cost": mu,
            "gamma_cohort_control_margin_cost": gamma_cohort,
            "gamma_dwell_control_margin_cost": gamma_dwell,
        },
        "decision_thresholds_empirically_calibrated": False,
        "decision_threshold_calibration_receipt_present": False,
        "frozen_threshold_values_are_not_calibration_authority": True,
        "per_dwell_dominance_required_so_one_session_cannot_carry_the_cohort": True,
    }


def _validate_promotion(value: object) -> dict[str, Any]:
    promotion = _object(value, "cross-session promotion")
    _strict_keys(
        promotion,
        {
            "minimum_association_distinct_session_count",
            "minimum_tracking_prediction_session_count",
            "candidate_after_first_passing_full_selection_dwell",
            "association_requires_same_norad_from_full_selection_in_every_session",
            "association_sessions_must_have_distinct_recording_manifests",
            "tracking_requires_target_lock_before_later_session",
            "tracking_later_session_uses_fixed_norad_without_catalogue_reselection",
            "tracking_session_must_be_distinct_and_chronologically_later",
            "maximum_consecutive_coasting_sessions",
            "maximum_tracking_horizon_s",
            "initial_tracking_confirmation_uses_exact_frozen_holdout_ordinals",
            "initial_hold_nonactivation_consumes_ordinal_and_cannot_be_replaced",
            "coasting_only_after_confirmed_under_separately_frozen_monitoring_schedule",
            "post_confirmation_nonactivation_advances_coasting_not_lost",
            "lost_requires_positive_contradiction_or_coast_limit_exceeded",
            "invalid_provenance_or_incomplete_artifact_rejected_without_counter_mutation",
            "valid_identity_control_margin_failure_wrong_identity_or_innovation_rejection_means_lost",
            "weaker_control_activation_alone_is_not_loss",
            "target_lock_receipt_schema",
            "prediction_confirmation_receipt_schema",
        },
        "cross-session promotion",
    )
    minimum_sessions = _integer(
        promotion.get("minimum_association_distinct_session_count"),
        "minimum association distinct-session count",
        minimum=2,
    )
    minimum_prediction_sessions = _integer(
        promotion.get("minimum_tracking_prediction_session_count"),
        "minimum tracking prediction-session count",
        minimum=2,
    )
    if minimum_sessions != 2 or minimum_prediction_sessions != 2:
        raise ValueError(
            "prospective v1 requires exactly two discovery sessions and two later predictions"
        )
    for field in (
        "candidate_after_first_passing_full_selection_dwell",
        "association_requires_same_norad_from_full_selection_in_every_session",
        "association_sessions_must_have_distinct_recording_manifests",
        "tracking_requires_target_lock_before_later_session",
        "tracking_later_session_uses_fixed_norad_without_catalogue_reselection",
        "tracking_session_must_be_distinct_and_chronologically_later",
        "initial_tracking_confirmation_uses_exact_frozen_holdout_ordinals",
        "initial_hold_nonactivation_consumes_ordinal_and_cannot_be_replaced",
        "coasting_only_after_confirmed_under_separately_frozen_monitoring_schedule",
        "post_confirmation_nonactivation_advances_coasting_not_lost",
        "lost_requires_positive_contradiction_or_coast_limit_exceeded",
        "invalid_provenance_or_incomplete_artifact_rejected_without_counter_mutation",
        "valid_identity_control_margin_failure_wrong_identity_or_innovation_rejection_means_lost",
        "weaker_control_activation_alone_is_not_loss",
    ):
        _true(promotion.get(field), f"cross-session promotion {field}")
    maximum_coasts = _integer(
        promotion.get("maximum_consecutive_coasting_sessions"),
        "maximum consecutive coasting sessions",
        minimum=1,
    )
    maximum_horizon_s = _positive(
        promotion.get("maximum_tracking_horizon_s"), "maximum tracking horizon"
    )
    if (
        promotion.get("target_lock_receipt_schema") != TARGET_LOCK_RECEIPT_SCHEMA
        or promotion.get("prediction_confirmation_receipt_schema")
        != PREDICTION_CONFIRMATION_RECEIPT_SCHEMA
    ):
        raise ValueError("cross-session promotion receipt schema is unsupported")
    return {
        **_json_copy(promotion, "cross-session promotion"),
        "states": [
            "unqualified",
            "candidate",
            "associated",
            "target_locked",
            "confirming",
            "initial_confirmation_failed",
            "confirmed",
            "coasting",
            "lost",
            "expired",
            "protocol_invalid",
        ],
        "transitions": [
            {
                "from": "unqualified",
                "to": "candidate",
                "requires": (
                    "one future dwell passing presence and full-selection specificity gates"
                ),
            },
            {
                "from": "candidate",
                "to": "associated",
                "requires": (
                    f"same NORAD independently reselected in at least {minimum_sessions} "
                    "distinct sessions with every dwell gate passing"
                ),
            },
            {
                "from": "associated",
                "to": "target_locked",
                "requires": "digest-bound target-lock receipt issued before prediction evidence",
            },
            {
                "from": "target_locked",
                "to": "confirming",
                "requires": (
                    "frozen cohort ordinal 3 yields an accepted causal fixed-target update; "
                    "tracking remains unclaimed"
                ),
            },
            {
                "from": "confirming",
                "to": "confirmed",
                "requires": (
                    f"frozen cohort ordinal 4 yields the second accepted causal fixed-target "
                    f"update; the required update count is {minimum_prediction_sessions}"
                ),
            },
            {
                "from": "target_locked|confirming",
                "to": "initial_confirmation_failed",
                "requires": (
                    "either frozen initial holdout ordinal has valid nonactivation or no qualified "
                    "RF opportunity; consume the ordinal and forbid replacement or rescue"
                ),
            },
            {
                "from": "initial_confirmation_failed",
                "to": "initial_confirmation_failed",
                "requires": (
                    "adjudicate any remaining frozen initial holdout ordinal without allowing an "
                    "accepted update to rescue initial confirmation"
                ),
            },
            {
                "from": "confirmed",
                "to": "coasting",
                "requires": (
                    "a due session in a separately frozen post-confirmation monitoring schedule "
                    "has no RF activation or no qualified RF opportunity; increment the "
                    "consecutive-coast counter while the causal horizon still holds"
                ),
            },
            {
                "from": "coasting",
                "to": "confirmed",
                "requires": (
                    "an accepted fixed-target update passes under the separately frozen "
                    "post-confirmation monitoring schedule"
                ),
            },
            {
                "from": "target_locked|confirming|initial_confirmation_failed|confirmed|coasting",
                "to": "lost",
                "requires": (
                    "a valid artifact fails the frozen strict identity-over-strongest-control "
                    "margin, selects a wrong identity, fails the innovation gate, or "
                    "post-confirmation consecutive coasts exceed the frozen limit"
                ),
            },
            {
                "from": (
                    "unqualified|candidate|associated|target_locked|confirming|"
                    "initial_confirmation_failed|confirmed|coasting"
                ),
                "to": "protocol_invalid",
                "requires": (
                    "invalid provenance or an incomplete artifact; reject the evidence, mutate no "
                    "RF miss/coast counter, and fail closed"
                ),
            },
            {
                "from": (
                    "candidate|associated|target_locked|confirming|initial_confirmation_failed|"
                    "confirmed|coasting|lost"
                ),
                "to": "expired",
                "requires": "the TLE freshness limit or fixed cohort authority expires",
            },
        ],
        "tracking_is_not_same_as_repeated_retrospective_association": True,
        "tracking_status_states": ["confirmed", "coasting"],
        "accepted_later_update_count_state_invariant": {
            "target_locked": 0,
            "confirming": 1,
            "initial_confirmation_failed": "0 or 1; immutable for this plan",
            "confirmed": ">=2",
            "coasting": "preserve the confirmed accepted-later-update count (>=2)",
        },
        "coasting_tracking_claim_requires_accepted_later_update_count_at_least": 2,
        "initial_tracking_confirmation_policy": {
            "frozen_cohort_ordinals": [3, 4],
            "accepted_update_required_at_every_ordinal": True,
            "every_ordinal_consumed_even_after_failure": True,
            "replacement_or_fifth_session_rescue_permitted": False,
            "coasting_state_permitted_before_confirmation": False,
            "failure_requires_a_new_prospective_plan": True,
        },
        "post_confirmation_monitoring_policy": {
            "authorized_by_this_plan": False,
            "separately_frozen_schedule_required": True,
            "coasting_state_available_only_after_confirmation": True,
        },
        "maximum_consecutive_coasting_sessions": maximum_coasts,
        "maximum_tracking_horizon_s": maximum_horizon_s,
        "nonactivation_is_not_physical_loss_evidence": True,
        "invalid_evidence_semantics": {
            "categories": ["invalid-provenance", "incomplete-artifact"],
            "evidence_accepted": False,
            "rf_miss_counter_mutated": False,
            "coast_counter_mutated": False,
            "resulting_protocol_state": "protocol_invalid",
        },
        "valid_positive_contradiction_semantics": {
            "categories": [
                "identity-over-strongest-control-margin-gate-failure",
                "wrong-identity",
                "innovation-rejection",
            ],
            "resulting_tracking_state": "lost",
        },
        "weaker_control_activation_semantics": {
            "positive_contradiction": False,
            "result": "apply-the-frozen-strict-margin-gate",
            "loss_permitted_when_identity_strictly_beats_control_by_gamma": False,
        },
        "valid_initial_hold_nonactivation_semantics": {
            "resulting_protocol_state": "initial_confirmation_failed",
            "holdout_ordinal_consumed": True,
            "replacement_or_later_rescue_permitted": False,
            "physical_loss_claimed": False,
        },
        "valid_post_confirmation_nonactivation_semantics": {
            "resulting_tracking_state": "coasting",
            "coast_counter_incremented": True,
            "separately_frozen_monitoring_schedule_required": True,
        },
        "lost_or_expired_requires_a_new_prospective_plan_for_reacquisition": True,
    }


def _validate_cohort(
    value: object,
    *,
    minimum_association_sessions: int,
    minimum_prediction_sessions: int,
) -> dict[str, Any]:
    cohort = _object(value, "prospective cohort policy")
    _strict_keys(
        cohort,
        {
            "algorithm",
            "total_eligible_dwell_count",
            "association_selection_dwell_count",
            "tracking_prediction_holdout_dwell_count",
            "chronological_order_keys",
            "take_first_eligible_dwells_in_order",
            "association_and_holdout_roles_are_contiguous",
            "replacement_after_analysis_permitted",
            "optional_stopping_permitted",
            "every_frozen_ordinal_must_be_adjudicated",
        },
        "prospective cohort policy",
    )
    if cohort.get("algorithm") != COHORT_POLICY_ALGORITHM:
        raise ValueError("prospective cohort policy uses an unsupported algorithm")
    total = _integer(
        cohort.get("total_eligible_dwell_count"), "total cohort dwell count", minimum=3
    )
    association_count = _integer(
        cohort.get("association_selection_dwell_count"),
        "association-selection dwell count",
        minimum=minimum_association_sessions,
    )
    prediction_count = _integer(
        cohort.get("tracking_prediction_holdout_dwell_count"),
        "tracking-prediction holdout dwell count",
        minimum=minimum_prediction_sessions,
    )
    if total != association_count + prediction_count:
        raise ValueError("cohort total must equal association plus prediction-holdout counts")
    if total != 4 or association_count != 2 or prediction_count != 2:
        raise ValueError(
            "prospective v1 freezes two discovery dwells followed by two prediction holds"
        )
    order_keys = _list(cohort.get("chronological_order_keys"), "cohort order keys")
    if order_keys != [
        "sealed_at_utc_ns",
        "session_id",
        "recording_manifest_digest",
    ]:
        raise ValueError("prospective cohort order must use the frozen total ordering")
    for field in (
        "take_first_eligible_dwells_in_order",
        "association_and_holdout_roles_are_contiguous",
        "every_frozen_ordinal_must_be_adjudicated",
    ):
        _true(cohort.get(field), f"prospective cohort {field}")
    for field in ("replacement_after_analysis_permitted", "optional_stopping_permitted"):
        _false(cohort.get(field), f"prospective cohort {field}")
    return {
        **_json_copy(cohort, "prospective cohort policy"),
        "ordinal_roles": [
            *(
                {
                    "ordinal": index,
                    "role": "full-catalogue-association-selection",
                }
                for index in range(1, association_count + 1)
            ),
            *(
                {
                    "ordinal": association_count + index,
                    "role": "fixed-target-tracking-prediction-holdout",
                }
                for index in range(1, prediction_count + 1)
            ),
        ],
        "target_lock_may_be_issued_only_after_all_association_selection_ordinals": True,
        "prediction_holdout_identity_reselection_permitted": False,
    }


def adjudicate_randomization_gate(
    *,
    identity_best_improvement: float,
    control_best_improvements: tuple[float, ...],
    gamma_dwell_control_margin_cost: float,
) -> dict[str, Any]:
    """Apply the strict max-control margin and emit only a reserved rank diagnostic."""

    identity = _finite(identity_best_improvement, "identity best improvement")
    if identity < 0.0:
        raise ValueError("identity best improvement must be nonnegative")
    controls = tuple(
        _finite(item, "control best improvement") for item in control_best_improvements
    )
    if len(controls) != CONTROL_COUNT or any(item < 0.0 for item in controls):
        raise ValueError("control adjudication needs exactly twenty nonnegative controls")
    margin_threshold = _positive(
        gamma_dwell_control_margin_cost,
        "gamma dwell control margin",
    )
    count_at_least_identity = sum(item >= identity for item in controls)
    numerator = 1 + count_at_least_identity
    denominator = len(controls) + 1
    strongest_control = max(controls)
    margin = identity - strongest_control
    return {
        "reserved_rank_formula": RANDOMIZATION_FORMULA,
        "randomization_exchangeability_verified": False,
        "permutation_p_value": None,
        "control_count": len(controls),
        "controls_at_least_identity_count": count_at_least_identity,
        "reserved_rank_fraction_numerator": numerator,
        "reserved_rank_fraction_denominator": denominator,
        "reserved_rank_fraction": numerator / denominator,
        "identity_best_improvement": identity,
        "strongest_control_best_improvement": strongest_control,
        "identity_margin_over_strongest_control_cost": margin,
        "gamma_dwell_control_margin_cost": margin_threshold,
        "strict_margin_passed": margin > margin_threshold,
        "identity_activation_passed": identity > 0.0,
        "specificity_gate_passed": identity > 0.0 and margin > margin_threshold,
    }


def adjudicate_discovery_association_gate(
    *,
    association_improvement_cost: float,
    identity_improvements: tuple[float, float],
    catalogue_runner_margin_cost: float,
    dwell_control_margins: tuple[float, float],
    cohort_control_margin_cost: float,
    beta_association_cost: float,
    mu_catalogue_runner_margin_cost: float,
    gamma_cohort_control_margin_cost: float,
    gamma_dwell_control_margin_cost: float,
    same_norad_selected_in_both_sessions: bool,
    sessions_are_distinct: bool,
    natural_presence_null_qualified: bool,
    positive_sensitivity_qualified: bool,
    decision_threshold_calibration_qualified: bool,
) -> dict[str, Any]:
    """Adjudicate the exact two-dwell discovery gate; every comparison is strict."""

    association = _finite(association_improvement_cost, "association improvement")
    identities = tuple(_finite(item, "identity improvement") for item in identity_improvements)
    runner = _finite(catalogue_runner_margin_cost, "identity-arm cross-dwell runner margin")
    dwell_controls = tuple(_finite(item, "dwell control margin") for item in dwell_control_margins)
    if any(len(items) != 2 for items in (identities, dwell_controls)):
        raise ValueError("discovery association adjudication requires exactly two dwell rows")
    cohort_control = _finite(cohort_control_margin_cost, "cohort control margin")
    beta = _positive(beta_association_cost, "beta association cost")
    mu = _positive(mu_catalogue_runner_margin_cost, "mu catalogue runner-margin cost")
    gamma_cohort = _positive(gamma_cohort_control_margin_cost, "gamma cohort control-margin cost")
    gamma_dwell = _positive(gamma_dwell_control_margin_cost, "gamma dwell control-margin cost")
    boolean_inputs = {
        "same_norad_selected_in_both_sessions": same_norad_selected_in_both_sessions,
        "sessions_are_distinct": sessions_are_distinct,
        "natural_presence_null_qualified": natural_presence_null_qualified,
        "positive_sensitivity_qualified": positive_sensitivity_qualified,
        "decision_threshold_calibration_qualified": (decision_threshold_calibration_qualified),
    }
    if any(not isinstance(value, bool) for value in boolean_inputs.values()):
        raise ValueError("discovery association qualifier inputs must be booleans")
    identity_activation_passed = tuple(item > 0.0 for item in identities)
    runner_margin_passed = runner > mu
    dwell_control_margin_passed = tuple(item > gamma_dwell for item in dwell_controls)
    association_improvement_passed = association > beta
    cohort_control_margin_passed = cohort_control > gamma_cohort
    passed = (
        all(identity_activation_passed)
        and runner_margin_passed
        and all(dwell_control_margin_passed)
        and association_improvement_passed
        and cohort_control_margin_passed
        and all(boolean_inputs.values())
    )
    return {
        "comparison_is_strict": True,
        "equality_passes": False,
        "association_improvement_passed": association_improvement_passed,
        "identity_activation_passed_by_dwell": list(identity_activation_passed),
        "identity_arm_cross_dwell_runner_margin_passed": runner_margin_passed,
        "dwell_control_margin_passed_by_dwell": list(dwell_control_margin_passed),
        "cohort_control_margin_passed": cohort_control_margin_passed,
        **boolean_inputs,
        "discovery_association_gate_passed": passed,
    }


def adjudicate_initial_tracking_confirmation(
    *,
    holdout_outcomes: tuple[str, str],
) -> dict[str, Any]:
    """Adjudicate exactly frozen cohort ordinals 3 and 4 without optional rescue."""

    outcomes = tuple(holdout_outcomes)
    allowed = {
        "accepted-fixed-target-update",
        "valid-nonactivation-or-no-rf-opportunity",
        "valid-positive-contradiction",
        "invalid-provenance-or-incomplete-artifact",
    }
    if len(outcomes) != 2 or any(item not in allowed for item in outcomes):
        raise ValueError(
            "initial tracking adjudication requires exactly two recognized holdout outcomes"
        )
    accepted_count = outcomes.count("accepted-fixed-target-update")
    if "invalid-provenance-or-incomplete-artifact" in outcomes:
        state = "protocol_invalid"
    elif "valid-positive-contradiction" in outcomes:
        state = "lost"
    elif accepted_count == 2:
        state = "confirmation-gate-passed-awaiting-typed-receipt"
    else:
        state = "initial_confirmation_failed"
    return {
        "frozen_holdout_ordinals": [3, 4],
        "holdout_outcomes": list(outcomes),
        "every_frozen_holdout_ordinal_consumed": True,
        "accepted_fixed_target_update_count": accepted_count,
        "diagnostic_adjudication_state": state,
        "initial_confirmation_numerical_gate_passed": accepted_count == 2,
        "tracking_claimed": False,
        "promotion_authority_granted": False,
        "typed_plan_target_session_and_digest_receipt_required_for_promotion": True,
        "replacement_or_fifth_session_rescue_permitted": False,
        "new_plan_required_after_initial_confirmation_failure": (
            state == "initial_confirmation_failed"
        ),
    }


def _build_prospective_plan_unchecked(
    specification: dict[str, Any],
    *,
    specification_path: Path,
    specification_file_digest: str,
) -> dict[str, Any]:
    """Validate one pre-evidence proposal and build its deterministic manifest."""

    _strict_keys(specification, {"schema", "proposal", "receipts"}, "freeze specification")
    if specification.get("schema") != SPECIFICATION_SCHEMA:
        raise ValueError(f"expected freeze specification schema {SPECIFICATION_SCHEMA}")
    proposal = _object(specification.get("proposal"), "prospective proposal")
    _strict_keys(
        proposal,
        {
            "plan_id",
            "frozen_at_utc_ns",
            "future_evidence_not_before_utc_ns",
            "tle",
            "score_calibration",
            "observer",
            "future_dwell_window_policy",
            "pilot_scan_configuration",
            "raw_replay_configuration",
            "catalogue_screen",
            "paired_full_catalogue_producer",
            "prediction_time_randomization",
            "decision_thresholds",
            "presence_qualification",
            "cross_session_promotion",
            "prospective_cohort_policy",
        },
        "prospective proposal",
    )
    plan_id = _nonempty(proposal.get("plan_id"), "prospective plan ID")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", plan_id) is None:
        raise ValueError("prospective plan ID contains unsafe characters")
    frozen_at = _integer(proposal.get("frozen_at_utc_ns"), "proposal freeze UTC")
    evidence_not_before = _integer(
        proposal.get("future_evidence_not_before_utc_ns"),
        "future evidence not-before UTC",
    )
    if frozen_at >= evidence_not_before:
        raise ValueError("proposal must be frozen strictly before future evidence eligibility")
    proposal_digest = canonical_digest(proposal)
    base_directory = specification_path.parent

    tle_reference = _object(proposal.get("tle"), "TLE proposal reference")
    _strict_keys(
        tle_reference,
        {"path", "file_digest", "maximum_snapshot_age_at_dwell_s"},
        "TLE proposal reference",
    )
    tle_path, tle_digest = _bound_file(
        {"path": tle_reference.get("path"), "file_digest": tle_reference.get("file_digest")},
        base_directory=base_directory,
        label="TLE snapshot",
    )
    maximum_tle_age_s = _positive(
        tle_reference.get("maximum_snapshot_age_at_dwell_s"),
        "maximum TLE snapshot age at dwell",
    )
    try:
        tle_bytes = tle_path.read_bytes()
        tle_text = tle_bytes.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise ValueError(f"TLE snapshot is not readable UTF-8: {error}") from error
    catalogue = parse_element_sets(tle_text)
    if len(set(catalogue.satellite_numbers)) != len(catalogue):
        raise ValueError("TLE snapshot repeats a NORAD catalogue identity")

    calibration_reference = _object(
        proposal.get("score_calibration"), "score-calibration proposal reference"
    )
    _strict_keys(
        calibration_reference,
        {"path", "file_digest", "schema"},
        "score-calibration proposal reference",
    )
    calibration_path, calibration_digest = _bound_file(
        {
            "path": calibration_reference.get("path"),
            "file_digest": calibration_reference.get("file_digest"),
        },
        base_directory=base_directory,
        label="score calibration",
    )
    calibration = _read_json(calibration_path)
    if calibration.get("schema") != calibration_reference.get("schema"):
        raise ValueError("score-calibration schema differs from the frozen reference")

    observer = ObserverSiteV1.model_validate(_object(proposal.get("observer"), "observer"))
    config = _raw_configuration(proposal.get("raw_replay_configuration"))
    raw_replay._validate_calibration_grouping(calibration, config)
    score = raw_replay._score(calibration)
    if not score.weak_match_is_dominated_by_miss():
        raise ValueError("score calibration does not make weak matches miss-dominated")
    window_policy, grid = _validate_window_policy(
        proposal.get("future_dwell_window_policy"), config=config
    )
    pilot_configuration = pilot_scan_search_configuration(
        _object(proposal.get("pilot_scan_configuration"), "pilot scan configuration")
    )
    if pilot_configuration != proposal.get("pilot_scan_configuration"):
        raise ValueError("pilot scan configuration must freeze exactly its search fields")
    screen = _validate_catalogue_screen(proposal.get("catalogue_screen"))
    paired_producer = _validate_paired_producer(proposal.get("paired_full_catalogue_producer"))
    prefix = str(screen["catalogue_name_prefix"]).strip().upper()
    matching_indices = tuple(
        index for index, name in enumerate(catalogue.names) if str(name).upper().startswith(prefix)
    )
    if not matching_indices:
        raise ValueError("TLE snapshot contains no catalogue names matching the frozen prefix")

    receipts = _object(specification.get("receipts"), "freeze receipts")
    _strict_keys(receipts, {"tle_authority", "chronology"}, "freeze receipts")
    tle_receipt_path, tle_receipt_digest = _bound_file(
        receipts.get("tle_authority"),
        base_directory=base_directory,
        label="TLE authority receipt",
    )
    tle_receipt = _read_json(tle_receipt_path)
    _strict_keys(
        tle_receipt,
        {
            "schema",
            "authority",
            "authority_snapshot_id",
            "tle_file_digest",
            "snapshot_acquired_utc_ns",
            "available_to_analysis_utc_ns",
        },
        "TLE authority receipt",
    )
    if tle_receipt.get("schema") != TLE_AUTHORITY_RECEIPT_SCHEMA:
        raise ValueError("TLE authority receipt schema is unsupported")
    _nonempty(tle_receipt.get("authority"), "TLE receipt authority")
    _nonempty(tle_receipt.get("authority_snapshot_id"), "TLE authority snapshot ID")
    if _sha256(tle_receipt.get("tle_file_digest"), "receipt TLE digest") != tle_digest:
        raise ValueError("TLE authority receipt binds different TLE bytes")
    acquired = _integer(tle_receipt.get("snapshot_acquired_utc_ns"), "TLE snapshot acquisition UTC")
    available = _integer(tle_receipt.get("available_to_analysis_utc_ns"), "TLE availability UTC")
    if acquired > available or available > frozen_at:
        raise ValueError("TLE snapshot was not causally available when the proposal was frozen")
    element_epochs = catalogue.element_epoch_utc_ns()
    if max(element_epochs) > acquired:
        raise ValueError("TLE element epoch postdates the asserted snapshot acquisition")
    if (evidence_not_before - acquired) / 1e9 > maximum_tle_age_s:
        raise ValueError("TLE snapshot is already too old at the future-evidence boundary")

    chronology_path, chronology_digest = _bound_file(
        receipts.get("chronology"),
        base_directory=base_directory,
        label="chronology receipt",
    )
    chronology = _read_json(chronology_path)
    _strict_keys(
        chronology,
        {
            "schema",
            "authority",
            "receipt_id",
            "proposal_digest",
            "issued_utc_ns",
            "future_evidence_not_before_utc_ns",
            "proposal_reviewed_before_future_evidence",
        },
        "chronology receipt",
    )
    if chronology.get("schema") != CHRONOLOGY_RECEIPT_SCHEMA:
        raise ValueError("chronology receipt schema is unsupported")
    _nonempty(chronology.get("authority"), "chronology receipt authority")
    _nonempty(chronology.get("receipt_id"), "chronology receipt ID")
    if _sha256(chronology.get("proposal_digest"), "chronology proposal digest") != (
        proposal_digest
    ):
        raise ValueError("chronology receipt binds a different proposal digest")
    issued = _integer(chronology.get("issued_utc_ns"), "chronology receipt issue UTC")
    if (
        chronology.get("future_evidence_not_before_utc_ns") != evidence_not_before
        or chronology.get("proposal_reviewed_before_future_evidence") is not True
        or not (frozen_at <= issued < evidence_not_before)
    ):
        raise ValueError("chronology receipt does not prove pre-evidence proposal ordering")

    thresholds = _validate_decision_thresholds(proposal.get("decision_thresholds"))
    randomization = _validate_randomization(
        proposal.get("prediction_time_randomization"),
        proposal_digest=proposal_digest,
        config=config,
        grid=grid,
        gamma_dwell_control_margin_cost=float(
            thresholds["validated_values"]["gamma_dwell_control_margin_cost"]
        ),
    )
    presence = _validate_presence_qualification(proposal.get("presence_qualification"))
    promotion = _validate_promotion(proposal.get("cross_session_promotion"))
    if (evidence_not_before - acquired) / 1e9 + float(
        promotion["maximum_tracking_horizon_s"]
    ) > maximum_tle_age_s:
        raise ValueError("tracking horizon exceeds the frozen causal TLE freshness interval")
    cohort = _validate_cohort(
        proposal.get("prospective_cohort_policy"),
        minimum_association_sessions=int(promotion["minimum_association_distinct_session_count"]),
        minimum_prediction_sessions=int(promotion["minimum_tracking_prediction_session_count"]),
    )
    full_catalogue_manifest = bounded.producer_implementation_manifest()
    paired_bound = bool(paired_producer["implementation_manifest_digest_verified_current"])

    payload: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "algorithm": ALGORITHM,
        "plan_id": plan_id,
        "research_only": True,
        "candidate_only_until_every_gate_passes": True,
        "payload_decoded": False,
        "association_claimed": False,
        "tracking_claimed": False,
        "specification_path": str(specification_path.resolve()),
        "specification_file_digest": specification_file_digest,
        "proposal_digest": proposal_digest,
        "frozen_at_utc_ns": frozen_at,
        "future_evidence_not_before_utc_ns": evidence_not_before,
        "future_evidence_consumed_by_freezer": False,
        "future_product_paths_frozen_or_inspected": False,
        "post_acquisition_persisted_inventory_must_be_untruncated": True,
        "pre_acquisition_candidate_inventory_complete": False,
        "physical_raw_candidate_inventory_complete": False,
        "pre_evidence_inputs": {
            "tle": {
                "path": str(tle_path),
                "file_digest": tle_digest,
                "byte_count": len(tle_bytes),
                "catalogue_object_count": len(catalogue),
                "unique_catalogue_identity_count": len(set(catalogue.satellite_numbers)),
                "matching_name_prefix": prefix,
                "matching_catalogue_identity_count": len(matching_indices),
                "minimum_element_epoch_utc_ns": min(element_epochs),
                "maximum_element_epoch_utc_ns": max(element_epochs),
                "maximum_snapshot_age_at_dwell_s": maximum_tle_age_s,
            },
            "score_calibration": {
                "path": str(calibration_path),
                "file_digest": calibration_digest,
                "content_digest": canonical_digest(calibration),
                "schema": calibration.get("schema"),
            },
        },
        "authority_and_chronology": {
            "tle_authority_receipt": {
                "path": str(tle_receipt_path),
                "file_digest": tle_receipt_digest,
                "content_digest": canonical_digest(tle_receipt),
                "receipt": tle_receipt,
            },
            "chronology_receipt": {
                "path": str(chronology_path),
                "file_digest": chronology_digest,
                "content_digest": canonical_digest(chronology),
                "receipt": chronology,
            },
            "proposal_digest_bound_without_circular_specification_digest": True,
            "digest_and_chronology_structurally_verified": True,
            "external_authority_authentication_performed": False,
            "external_preregistration_verified": False,
            "association_authority_enabled_by_this_manifest": False,
            "tracking_authority_enabled_by_this_manifest": False,
        },
        "execution": {
            "future_dwell_window_policy": window_policy,
            "prospective_cohort_policy": cohort,
            "observer": observer.model_dump(mode="json"),
            "pilot_scan_configuration": pilot_configuration,
            "raw_replay_configuration": asdict(config),
            "penalties_and_calibration": {
                "satellite_cost": config.satellite_cost,
                "episode_cost": config.episode_cost,
                "delay_prior_mean_s": config.delay_prior_mean_s,
                "delay_prior_sigma_s": config.delay_prior_sigma_s,
                "score_calibration_file_digest": calibration_digest,
                "score_calibration_content_digest": canonical_digest(calibration),
            },
            "full_catalogue_search": {
                **screen,
                "producer_implementation_manifest": full_catalogue_manifest,
                "producer_implementation_manifest_digest": canonical_digest(
                    full_catalogue_manifest
                ),
                "member_evaluation_scope": {
                    "derived_only_after_a_future_dwell_is_sealed": True,
                    "required_bindings": [
                        "duration_dataset_digest",
                        "pilot_scan_digest",
                        "session_id",
                        "recording_manifest_digest",
                        "stream_id",
                        "radio_id",
                        "radio_serial",
                        "receiver_id",
                        "tuning_tag",
                        "sky_frequency_hz",
                        "path_scope_digest",
                        "scheduled_probe_ids",
                        "window_start_s",
                        "window_end_s",
                    ],
                },
            },
            "paired_full_catalogue_producer": paired_producer,
            "prediction_time_randomization": randomization,
            "tracking_prediction_hold_protocol": {
                "target_source": "digest-bound target-lock receipt from completed discovery cohort",
                "target_catalogue_number_frozen_before_hold_evidence": True,
                "catalogue_search_performed": False,
                "catalogue_identity_reselection_permitted": False,
                "full_catalogue_reacquisition_fallback_permitted": False,
                "control_transform_digests": [
                    item["transform_digest"] for item in randomization["control_arms"]
                ],
                "same_observations_objective_and_fixed_norad_in_every_hold_arm": True,
                "fixed_target_identity_activation_required_for_a_confirming_update": True,
                "identity_minus_strongest_control_must_strictly_exceed_gamma_dwell": True,
                "required_later_confirming_session_count": 2,
                "frozen_initial_holdout_ordinals": [3, 4],
                "accepted_update_required_in_every_initial_holdout_ordinal": True,
                "every_initial_holdout_ordinal_must_be_adjudicated": True,
                "replacement_or_fifth_session_rescue_permitted": False,
                "coasting_permitted_during_initial_tracking_confirmation": False,
                "post_confirmation_monitoring_authorized_by_this_plan": False,
                "post_confirmation_coasting_requires_separately_frozen_schedule": True,
                "invalid_provenance_or_incomplete_artifact_result": (
                    "protocol-invalid-reject-evidence-no-counter-mutation"
                ),
                "valid_identity_control_margin_failure_wrong_identity_or_innovation_result": (
                    "lost"
                ),
                "weaker_control_activation_with_strict_margin_pass_result": (
                    "not-alone-a-contradiction"
                ),
                "valid_initial_hold_nonactivation_or_no_rf_opportunity_result": (
                    "initial-confirmation-failed-consume-ordinal-no-replacement"
                ),
                "valid_post_confirmation_nonactivation_result": (
                    "coasting-increment-coast-counter-under-separately-frozen-schedule"
                ),
                "excess_post_confirmation_coast_result": "lost",
            },
        },
        "qualification_gates": {
            "presence": presence,
            "specificity": randomization["gate"],
            "decision_thresholds": thresholds,
            "block_control_scope": (
                "catalogue-and-prediction-time-specificity-conditional-on-real-rf"
            ),
            "block_controls_are_not_a_presence_false_positive_calibration": True,
            "natural_presence_null_receipt_required_before_association": True,
            "positive_sensitivity_receipt_required_before_association": True,
            "score_calibration_does_not_calibrate_presence_or_decision_thresholds": True,
            "current_calibration_gap": (
                "natural capture-wide presence, positive sensitivity, and beta/mu/gamma "
                "threshold qualification receipts are absent"
            ),
        },
        "promotion_state_machine": promotion,
        "execution_readiness": {
            "paired_producer_implementation_digest_slot_filled": paired_bound,
            "paired_producer_implementation_bytes_verified_by_freezer": paired_bound,
            "paired_producer_manifest_digest_must_be_reverified_before_execution": True,
            "presence_null_qualification_receipt_present": False,
            "positive_sensitivity_qualification_receipt_present": False,
            "decision_threshold_calibration_receipt_present": False,
            "external_authority_authentication_present": False,
            "ready_to_consume_future_evidence": False,
            "ready_to_claim_association": False,
            "ready_to_claim_tracking": False,
        },
        "downstream_fail_closed_requirements": [
            (
                "reject evidence whose first estimate or window starts before the frozen "
                "not-before UTC"
            ),
            "reject an unsealed or path-preselected future dwell",
            (
                "report every upstream per-probe candidate-cap saturation and never promote "
                "persisted-row completeness to pre-acquisition or physical completeness"
            ),
            (
                "reject TLE bytes, calibration bytes, observer, window, penalties, or search "
                "configuration that drift"
            ),
            (
                "reject a TLE snapshot unavailable before the dwell or older than the frozen "
                "maximum age"
            ),
            (
                "reject any arm that omits a named identity disposition or an eligible "
                "catalogue minimum"
            ),
            (
                "reject any arm with shortlist, catalogue pruning, nuisance-state pruning, "
                "or a transform collision"
            ),
            (
                "do not report a permutation p-value until identity/control exchangeability is "
                "independently established"
            ),
            "require every strict pre-evidence cost threshold; equality fails every gate",
            (
                "require separate natural-null and positive-sensitivity qualifications before "
                "association"
            ),
            "never promote retrospective repeated selection directly to tracking",
            (
                "require a target lock before a later fixed-NORAD prediction session and "
                "forbid identity reselection there"
            ),
            (
                "consume exactly frozen holdout ordinals 3 and 4 for initial tracking; any "
                "nonaccepted update fails confirmation without replacement or a rescue session"
            ),
            (
                "do not treat a weaker activating control as loss when identity still strictly "
                "beats the strongest control by the frozen gamma margin"
            ),
        ],
    }
    return {**payload, "plan_content_digest": canonical_digest(payload)}


def build_prospective_plan(
    specification: dict[str, Any],
    *,
    specification_path: Path,
    specification_file_digest: str,
) -> dict[str, Any]:
    """Build and independently reconstruct one deterministic prospective plan."""

    return validate_prospective_plan(
        _build_prospective_plan_unchecked(
            specification,
            specification_path=specification_path,
            specification_file_digest=specification_file_digest,
        )
    )


def validate_prospective_plan(document: dict[str, Any]) -> dict[str, Any]:
    """Recompute the narrow scientific bindings of one emitted prospective plan."""

    expected_top = {
        "schema",
        "algorithm",
        "plan_id",
        "research_only",
        "candidate_only_until_every_gate_passes",
        "payload_decoded",
        "association_claimed",
        "tracking_claimed",
        "specification_path",
        "specification_file_digest",
        "proposal_digest",
        "frozen_at_utc_ns",
        "future_evidence_not_before_utc_ns",
        "future_evidence_consumed_by_freezer",
        "future_product_paths_frozen_or_inspected",
        "post_acquisition_persisted_inventory_must_be_untruncated",
        "pre_acquisition_candidate_inventory_complete",
        "physical_raw_candidate_inventory_complete",
        "pre_evidence_inputs",
        "authority_and_chronology",
        "execution",
        "qualification_gates",
        "promotion_state_machine",
        "execution_readiness",
        "downstream_fail_closed_requirements",
        "plan_content_digest",
    }
    _strict_keys(document, expected_top, "prospective plan")
    if document.get("schema") != PLAN_SCHEMA or document.get("algorithm") != ALGORITHM:
        raise ValueError("prospective plan schema or algorithm is unsupported")
    payload = dict(document)
    content_digest = _sha256(payload.pop("plan_content_digest"), "plan content digest")
    if canonical_digest(payload) != content_digest:
        raise ValueError("prospective plan content digest does not recompute")
    specification_path = _resolve_file(
        document.get("specification_path"),
        base_directory=Path("/"),
        label="bound prospective specification",
    )
    specification_digest = _sha256(
        document.get("specification_file_digest"), "plan specification digest"
    )
    if _file_digest(specification_path) != specification_digest:
        raise ValueError("bound prospective specification bytes have drifted")
    reconstructed = _build_prospective_plan_unchecked(
        _read_json(specification_path),
        specification_path=specification_path,
        specification_file_digest=specification_digest,
    )
    if document != reconstructed:
        raise ValueError(
            "prospective plan does not exactly reconstruct from its chronology-bound specification"
        )
    proposal_digest = _sha256(document.get("proposal_digest"), "plan proposal digest")
    for field in (
        "future_evidence_consumed_by_freezer",
        "future_product_paths_frozen_or_inspected",
        "pre_acquisition_candidate_inventory_complete",
        "physical_raw_candidate_inventory_complete",
        "association_claimed",
        "tracking_claimed",
    ):
        _false(document.get(field), f"prospective plan {field}")
    _true(
        document.get("post_acquisition_persisted_inventory_must_be_untruncated"),
        "post-acquisition persisted inventory untruncated",
    )
    authority = _object(document.get("authority_and_chronology"), "plan authority")
    for field in (
        "external_authority_authentication_performed",
        "external_preregistration_verified",
        "association_authority_enabled_by_this_manifest",
        "tracking_authority_enabled_by_this_manifest",
    ):
        _false(authority.get(field), f"plan authority {field}")
    inputs = _object(document.get("pre_evidence_inputs"), "plan pre-evidence inputs")
    tle_input = _object(inputs.get("tle"), "plan TLE input")
    tle_path = _resolve_file(tle_input.get("path"), base_directory=Path("/"), label="plan TLE")
    tle_digest = _sha256(tle_input.get("file_digest"), "plan TLE file digest")
    if _file_digest(tle_path) != tle_digest:
        raise ValueError("prospective plan TLE bytes have drifted")
    calibration_input = _object(inputs.get("score_calibration"), "plan score calibration")
    calibration_path = _resolve_file(
        calibration_input.get("path"), base_directory=Path("/"), label="plan score calibration"
    )
    calibration_digest = _sha256(
        calibration_input.get("file_digest"), "plan score-calibration file digest"
    )
    calibration_document = _read_json(calibration_path)
    if (
        _file_digest(calibration_path) != calibration_digest
        or calibration_input.get("content_digest") != canonical_digest(calibration_document)
        or calibration_input.get("schema") != calibration_document.get("schema")
    ):
        raise ValueError("prospective plan score-calibration bytes have drifted")
    tle_authority = _object(authority.get("tle_authority_receipt"), "plan TLE receipt")
    chronology_authority = _object(authority.get("chronology_receipt"), "plan chronology receipt")
    for receipt_reference, label in (
        (tle_authority, "TLE authority receipt"),
        (chronology_authority, "chronology receipt"),
    ):
        receipt_path = _resolve_file(
            receipt_reference.get("path"), base_directory=Path("/"), label=label
        )
        receipt_document = _read_json(receipt_path)
        if (
            _file_digest(receipt_path)
            != _sha256(receipt_reference.get("file_digest"), f"plan {label} file digest")
            or receipt_reference.get("content_digest") != canonical_digest(receipt_document)
            or receipt_reference.get("receipt") != receipt_document
        ):
            raise ValueError(f"prospective plan {label} bytes have drifted")
    tle_receipt = _object(tle_authority.get("receipt"), "embedded plan TLE receipt")
    chronology_receipt = _object(
        chronology_authority.get("receipt"), "embedded plan chronology receipt"
    )
    if (
        tle_receipt.get("tle_file_digest") != tle_digest
        or chronology_receipt.get("proposal_digest") != proposal_digest
        or chronology_receipt.get("future_evidence_not_before_utc_ns")
        != document.get("future_evidence_not_before_utc_ns")
    ):
        raise ValueError("prospective plan receipt cross-links do not recompute")

    execution = _object(document.get("execution"), "plan execution")
    config = _raw_configuration(execution.get("raw_replay_configuration"))
    window, grid = _validate_window_policy(
        execution.get("future_dwell_window_policy"), config=config
    )
    _ = window
    screen_document = _object(execution.get("full_catalogue_search"), "plan catalogue search")
    screen_keys = {
        "output_schema",
        "algorithm",
        "catalogue_name_prefix",
        "geometry_spacing_s",
        "full_window_visibility_required",
        "identity_partition_required",
        "every_eligible_catalogue_scored_on_complete_fine_bank",
        "shortlist_or_catalogue_pruning_permitted",
        "nuisance_state_pruning_permitted",
    }
    _validate_catalogue_screen({key: screen_document.get(key) for key in screen_keys})
    current_bounded_manifest = bounded.producer_implementation_manifest()
    if screen_document.get(
        "producer_implementation_manifest"
    ) != current_bounded_manifest or _sha256(
        screen_document.get("producer_implementation_manifest_digest"),
        "bounded producer implementation-manifest digest",
    ) != canonical_digest(current_bounded_manifest):
        raise ValueError("prospective plan bounded producer implementation is not current")

    paired_producer = _object(
        execution.get("paired_full_catalogue_producer"), "plan paired producer"
    )
    if (
        paired_producer.get("output_schema") != PAIRED_OUTPUT_SCHEMA
        or paired_producer.get("algorithm") != PAIRED_ALGORITHM
        or paired_producer.get("implementation_path") != PAIRED_IMPLEMENTATION_PATH
    ):
        raise ValueError("prospective plan paired producer identity differs")
    paired_manifest = paired_producer.get("implementation_manifest")
    paired_verified = paired_producer.get("implementation_manifest_digest_verified_current")
    if paired_manifest is None:
        if (
            paired_verified is not False
            or paired_producer.get("implementation_binding_status")
            != "required-before-first-future-dwell"
            or paired_producer.get("implementation_manifest_digest") is not None
        ):
            raise ValueError("unbound paired producer state is inconsistent")
    else:
        current_module = importlib.import_module(
            "tools.replay_raw_full_catalogue_paired_prediction_time_specificity"
        )
        current_manifest = current_module.producer_implementation_manifest()
        declared_digest = _sha256(
            paired_producer.get("implementation_manifest_digest"),
            "paired producer implementation-manifest digest",
        )
        if (
            paired_verified is not True
            or paired_manifest != current_manifest
            or declared_digest != canonical_digest(current_manifest)
        ):
            raise ValueError("prospective plan paired producer implementation is not current")

    randomization = _object(
        execution.get("prediction_time_randomization"), "plan prediction-time controls"
    )
    if tuple(randomization.get("control_indices", ())) != CONTROL_INDICES:
        raise ValueError("prospective plan control indices differ from 0 through 19")
    _false(
        randomization.get("randomization_exchangeability_verified"),
        "plan control exchangeability",
    )
    if randomization.get("permutation_p_value") is not None:
        raise ValueError("prospective plan must not emit a permutation p-value")
    expected_selection_context = canonical_digest(
        {
            "algorithm": ALGORITHM,
            "proposal_digest": proposal_digest,
            "role": "pre-evidence-full-catalogue-prediction-time-control-family",
        }
    )
    if randomization.get("selection_context_digest") != expected_selection_context:
        raise ValueError("prospective plan control selection context does not recompute")
    controls = _list(randomization.get("control_arms"), "plan control arms")
    if len(controls) != CONTROL_COUNT:
        raise ValueError("prospective plan must emit exactly twenty control arms")
    maximum_delay_support_s = max(abs(config.delay_min_s), abs(config.delay_max_s))
    for control_index, raw_control in zip(CONTROL_INDICES, controls, strict=True):
        control = _object(raw_control, "plan control arm")
        transform = _object(control.get("transform"), "plan control transform")
        expected = build_activity_block_permutation(
            grid,
            session_key=expected_selection_context,
            control_index=control_index,
            maximum_delay_support_s=maximum_delay_support_s,
        )
        if (
            control.get("arm_id") != f"control-{control_index:06d}"
            or control.get("role") != "full_catalogue_prediction_time_control"
            or control.get("full_catalogue_selection_required") is not True
            or control.get("transform_digest") != expected.plan_digest
            or canonical_digest(transform)
            != canonical_digest(_json_copy(asdict(expected), "expected control transform"))
        ):
            raise ValueError("prospective plan control transform does not recompute")

    thresholds = _object(
        _object(document.get("qualification_gates"), "plan qualification gates").get(
            "decision_thresholds"
        ),
        "plan decision thresholds",
    )
    if (
        thresholds.get("all_comparisons_are_strict") is not True
        or thresholds.get("equality_passes_any_threshold") is not False
        or thresholds.get("decision_thresholds_empirically_calibrated") is not False
        or thresholds.get("decision_threshold_calibration_receipt_present") is not False
    ):
        raise ValueError("prospective plan decision-threshold authority is inconsistent")
    cohort = _object(execution.get("prospective_cohort_policy"), "plan cohort")
    if (
        cohort.get("total_eligible_dwell_count") != 4
        or cohort.get("association_selection_dwell_count") != 2
        or cohort.get("tracking_prediction_holdout_dwell_count") != 2
        or cohort.get("optional_stopping_permitted") is not False
        or cohort.get("replacement_after_analysis_permitted") is not False
    ):
        raise ValueError("prospective plan cohort differs from the fixed 2+2 protocol")
    readiness = _object(document.get("execution_readiness"), "plan execution readiness")
    expected_bound = paired_manifest is not None
    if (
        readiness.get("paired_producer_implementation_digest_slot_filled") is not expected_bound
        or readiness.get("paired_producer_implementation_bytes_verified_by_freezer")
        is not expected_bound
        or readiness.get("paired_producer_manifest_digest_must_be_reverified_before_execution")
        is not True
    ):
        raise ValueError("prospective plan paired-producer readiness is inconsistent")
    for field in (
        "presence_null_qualification_receipt_present",
        "positive_sensitivity_qualification_receipt_present",
        "decision_threshold_calibration_receipt_present",
        "external_authority_authentication_present",
        "ready_to_consume_future_evidence",
        "ready_to_claim_association",
        "ready_to_claim_tracking",
    ):
        _false(readiness.get(field), f"plan readiness {field}")
    return _json_copy(document, "validated prospective plan")


def load_and_validate_prospective_plan(
    *,
    plan_path: Path,
    expected_plan_file_digest: str,
) -> dict[str, Any]:
    """Digest-bind, load, and independently validate an emitted prospective plan."""

    try:
        resolved = plan_path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"prospective plan cannot be resolved: {error}") from error
    expected = _sha256(expected_plan_file_digest, "prospective plan file digest")
    observed = _file_digest(resolved)
    if observed != expected:
        raise ValueError(
            f"prospective plan file digest mismatch: expected {expected}, observed {observed}"
        )
    return validate_prospective_plan(_read_json(resolved))


def freeze_prospective_plan(
    *,
    specification_path: Path,
    expected_specification_digest: str,
) -> dict[str, Any]:
    """Digest-bind one specification and freeze its prospective plan."""

    try:
        resolved = specification_path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"freeze specification cannot be resolved: {error}") from error
    expected = _sha256(expected_specification_digest, "freeze specification digest")
    observed = _file_digest(resolved)
    if observed != expected:
        raise ValueError(
            f"freeze specification digest mismatch: expected {expected}, observed {observed}"
        )
    return build_prospective_plan(
        _read_json(resolved),
        specification_path=resolved,
        specification_file_digest=observed,
    )


def _refuse_protected_output(path: Path) -> None:
    resolved = path.resolve()
    for protected in (Path("/mnt/qnap01"), Path("/srv")):
        if resolved == protected or protected in resolved.parents:
            raise ValueError(f"prospective-plan output must not be written beneath {protected}")


def _write_new(document: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if output is None:
        sys.stdout.write(rendered)
        return
    _refuse_protected_output(output)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    except FileExistsError as error:
        raise ValueError(f"prospective-plan output already exists: {output}") from error
    except OSError as error:
        raise ValueError(f"cannot write prospective-plan output {output}: {error}") from error


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specification", type=Path, required=True)
    parser.add_argument("--specification-sha256", required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    document = freeze_prospective_plan(
        specification_path=arguments.specification,
        expected_specification_digest=arguments.specification_sha256,
    )
    _write_new(document, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
