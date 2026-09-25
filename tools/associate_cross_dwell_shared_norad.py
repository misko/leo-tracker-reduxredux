#!/usr/bin/env python3
"""Reduce sealed per-dwell catalogue minima to a same-NORAD association.

This research-only adapter accepts only the bounded all-eligible catalogue
artifact.  That producer evaluates every full-window-visible catalogue row
over its declared finite delay/data-proposed-CFO bank and publishes the exact
minimum for each row.  Shortlist, pruned, multipath, and ordinary screen
artifacts are unknown evidence here and fail closed.

The adapter independently verifies every referenced file digest, derives each
session and absolute window from the digest-bound duration input, reconciles a
separately frozen union catalogue, and turns an exact per-catalogue minimum
into one reducer state.  A catalogue absent from a dwell's exhausted eligible
set is an explicit ineligible empty state space; an omitted or incompletely
searched row is never treated as null.

Any selected dwell/catalogue contribution must also be covered by a sealed,
internally re-adjudicated prediction-time control family that passed its
frozen gate.  TLE causality and capture timing are bound through a separate
receipt whose timestamps and content digests are checked.  Even a successful
result is only a bounded same-NORAD association, never an orbit or track.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, cast

from leo.analysis.research.cross_dwell_shared_norad import (  # type: ignore[import-untyped]
    AssociationDwell,
    CrossDwellAssociationProblem,
    ExactDwellCatalogStateSpace,
    FiniteDwellState,
    decode_cross_dwell_shared_norad,
)
from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools import decide_raw_catalogue_null_vs_any as bounded  # noqa: E402
from tools import replay_raw_multipath_paired_prediction_time_specificity as paired  # noqa: E402
from tools import (  # noqa: E402
    replay_raw_single_path_fixed_norad_paired_prediction_time_specificity as fixed_target,
)

REQUEST_SCHEMA = "org.leo.research.cross-dwell-shared-norad-adapter-request/v1"
FREEZE_SPEC_SCHEMA = "org.leo.research.cross-dwell-shared-norad-freeze-spec/v1"
FREEZE_SPEC_SCHEMA_V2 = "org.leo.research.cross-dwell-shared-norad-freeze-spec/v2"
FREEZE_MANIFEST_SCHEMA = "org.leo.research.cross-dwell-shared-norad-freeze-manifest/v1"
UNIVERSE_SCHEMA = "org.leo.research.cross-dwell-frozen-catalogue-union/v1"
QUALIFICATION_SCHEMA = "org.leo.research.cross-dwell-dwell-qualification/v1"
OUTPUT_SCHEMA = "org.leo.research.cross-dwell-shared-norad-association/v1"
SOURCE_SCHEMA = "org.leo.research.raw-catalogue-bounded-null-vs-any/v2"
SOURCE_ALGORITHM = "bounded-exact-all-eligible-fine-null-vs-any-identity-partition-v2"
SOURCE_IDENTITY_PARTITION_SCHEMA = "org.leo.research.catalogue-geometry-identity-partition/v1"
SOURCE_IDENTITY_PARTITION_ALGORITHM = "exact-named-full-window-visibility-identity-partition-v1"
ALGORITHM = "sealed-exact-minimum-cross-dwell-shared-norad-adapter-v1"
UNIVERSE_ALGORITHM = "frozen-union-of-exhausted-full-window-visible-catalogues-v1"
MATRIX_ALGORITHM = "exact-catalogue-minimum-compression-v1"

Disposition = Literal[
    "association",
    "finite_null",
    "association_threshold_not_met",
    "qualification_failed",
    "unknown_control_evidence",
]


class IncompleteAdapterEvidenceError(ValueError):
    """Raised when missing evidence could otherwise be mistaken for null."""


@dataclass(frozen=True, slots=True)
class _FileReference:
    path: Path
    file_digest: str


@dataclass(frozen=True, slots=True)
class _CatalogMinimum:
    catalog_number: int
    hypothesis_id: str
    reduced_objective: float
    generated_state_count: int


@dataclass(frozen=True, slots=True)
class _ControlEvidence:
    file_digest: str
    content_digest: str
    disposition: str
    comparable: bool
    paired_gate_passed: bool
    scientific_control_failed: bool
    fixed_target: bool
    catalog_numbers: tuple[int, ...]
    identity_selected_catalog_numbers: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _DwellEvidence:
    dwell_id: str
    session_id: str
    recording_manifest_digest: str
    source_path: Path
    source_file_digest: str
    source_content_digest: str
    dataset_file_digest: str
    pilot_scan_file_digest: str
    calibration_file_digest: str
    tle_file_digest: str
    window_start_utc_ns: int
    window_end_utc_ns: int
    null_objective: float
    minima: tuple[_CatalogMinimum, ...]
    named_catalog_numbers: tuple[int, ...]
    named_ineligible_catalog_numbers: tuple[int, ...]
    identity_partition_content_digest: str
    source_generated_state_count: int
    qualification_path: Path
    qualification_file_digest: str
    qualification_content_digest: str
    tle_authority: str
    tle_authority_snapshot_id: str
    tle_snapshot_acquired_utc_ns: int
    controls: tuple[_ControlEvidence, ...]


@dataclass(frozen=True, slots=True)
class _FreezeDwell:
    dwell_id: str
    source_reference: _FileReference
    session_id: str
    dataset_file_digest: str
    tle_file_digest: str
    first_estimate_utc_ns: int
    window_start_utc_ns: int
    window_end_utc_ns: int
    eligible_catalog_numbers: tuple[int, ...]
    named_ineligible_catalog_numbers: tuple[int, ...]
    tle_snapshot: dict[str, Any]
    timing: dict[str, Any]
    control_references: tuple[_FileReference, ...]


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value!r} is forbidden")


def _reject_duplicate_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
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
            object_pairs_hook=_reject_duplicate_object_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON document {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON document {path} must contain one object")
    return value


def _sha256(path: Path) -> str:
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError(f"cannot read digest-bound file {path}: {error}") from error
    return f"sha256:{digest}"


def _canonical_sha256(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a SHA-256 digest string")
    normalized = value if value.startswith("sha256:") else f"sha256:{value}"
    suffix = normalized.removeprefix("sha256:")
    if len(suffix) != 64 or any(character not in "0123456789abcdef" for character in suffix):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return normalized


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer greater than or equal to {minimum}")
    return value


def _positive_catalog(value: object, label: str) -> int:
    return _integer(value, label, minimum=1)


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _strict_keys(document: dict[str, Any], expected: set[str], label: str) -> None:
    if set(document) != expected:
        missing = sorted(expected - set(document))
        extra = sorted(set(document) - expected)
        raise ValueError(f"{label} fields differ: missing={missing!r} extra={extra!r}")


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _resolve(path_value: object, *, relative_to: Path, label: str) -> Path:
    raw = _nonempty(path_value, label)
    path = Path(raw)
    return (path if path.is_absolute() else relative_to / path).resolve()


def _file_reference(value: object, *, relative_to: Path, label: str) -> _FileReference:
    document = _object(value, label)
    _strict_keys(document, {"path", "file_digest"}, label)
    return _FileReference(
        path=_resolve(document["path"], relative_to=relative_to, label=f"{label} path"),
        file_digest=_canonical_sha256(document["file_digest"], f"{label} file digest"),
    )


def _verify_reference(reference: _FileReference, label: str) -> None:
    if _sha256(reference.path) != reference.file_digest:
        raise ValueError(f"{label} file digest mismatch")


def _artifact_nested_reference(
    artifact: dict[str, Any],
    key: str,
    *,
    artifact_path: Path,
) -> _FileReference:
    input_document = _object(artifact.get("input"), "source input")
    path_key = f"{key}_path"
    digest_key = f"{key}_digest"
    return _FileReference(
        path=_resolve(
            input_document.get(path_key),
            relative_to=artifact_path.parent,
            label=f"source {path_key}",
        ),
        file_digest=_canonical_sha256(
            input_document.get(digest_key),
            f"source {digest_key}",
        ),
    )


def _seconds_to_ns(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    try:
        nanoseconds = Decimal(str(value)) * Decimal(1_000_000_000)
    except InvalidOperation as error:
        raise ValueError(f"{label} cannot be represented as seconds") from error
    integral = nanoseconds.to_integral_value()
    if nanoseconds != integral:
        raise ValueError(f"{label} must resolve to an integral nanosecond")
    return int(integral)


def _validated_source(
    *,
    dwell_id: str,
    source_reference: _FileReference,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    tuple[_CatalogMinimum, ...],
    dict[str, Any],
    dict[str, Any],
]:
    _verify_reference(source_reference, f"dwell {dwell_id!r} source artifact")
    source = _read_json(source_reference.path)
    if source.get("schema") != SOURCE_SCHEMA or source.get("algorithm") != SOURCE_ALGORITHM:
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} source is not the bounded all-eligible exact producer"
        )

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
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} source exactness flags are incomplete: {sorted(bad_flags)!r}"
        )

    raw_inventory = _object(source.get("raw_inventory"), "source raw inventory")
    if (
        raw_inventory.get("declared_post_acquisition_inventory_complete") is not True
        or _integer(
            raw_inventory.get("truncated_candidate_count"),
            "truncated candidate count",
        )
        != 0
    ):
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} retained raw inventory is truncated or incomplete"
        )

    search = _object(source.get("catalogue_search"), "source catalogue search")
    fine = _object(search.get("fine_stage"), "source fine catalogue stage")
    finite_universe = _object(search.get("finite_universe"), "source finite universe")
    proof = _object(search.get("separability_proof"), "source separability proof")
    exact_flags = {
        "catalogue_rows_exhausted": True,
        "declared_discrete_delay_grid_exhausted": True,
        "generated_data_proposed_cfo_mode_bank_exhausted": True,
    }
    if any(fine.get(key) is not value for key, value in exact_flags.items()):
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} per-catalogue state generation is not exhausted"
        )
    if (
        proof.get("single_satellite_minima_exact_over_generated_states") is not True
        or proof.get("joint_delta_is_sum_of_selected_satellite_reduced_contributions") is not True
        or proof.get("arbitrary_subsets_of_finite_catalogue_universe_covered") is not True
        or proof.get("satellite_and_episode_costs_nonnegative") is not True
        or proof.get("exclusion_group_assignment_capacity") != 1
    ):
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} exact per-catalogue minimum proof is incomplete"
        )

    ranking = _list(fine.get("ranking"), "source catalogue ranking")
    eligible_count = _integer(fine.get("eligible_catalog_count"), "eligible catalogue count")
    scored_count = _integer(fine.get("scored_catalog_count"), "scored catalogue count")
    omitted_count = _integer(
        fine.get("omitted_eligible_catalog_count"),
        "omitted eligible catalogue count",
    )
    finite_count = _integer(
        finite_universe.get("eligible_catalogue_count"),
        "finite-universe eligible catalogue count",
    )
    if not (eligible_count == scored_count == finite_count == len(ranking)) or omitted_count != 0:
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} eligible catalogue rows are missing or count-inconsistent"
        )
    if finite_universe.get("catalogue_identity_scope") != "named and full-window-visible":
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} has an unsupported catalogue identity scope"
        )

    delay_grid = _list(fine.get("delay_grid"), "source delay grid")
    modes_per_delay = _integer(fine.get("modes_per_delay"), "modes per delay", minimum=1)
    expected_per_catalog = len(delay_grid) * modes_per_delay
    minima: list[_CatalogMinimum] = []
    expected_rank = 1
    for raw_row in ranking:
        row = _object(raw_row, "source catalogue row")
        rank = _integer(row.get("rank"), "source catalogue rank", minimum=1)
        if rank != expected_rank:
            raise ValueError(f"dwell {dwell_id!r} source catalogue ranks are not contiguous")
        expected_rank += 1
        catalog_number = _positive_catalog(row.get("catalog_number"), "source catalog number")
        generated_count = _integer(
            row.get("generated_state_count"),
            "source generated state count",
            minimum=1,
        )
        if generated_count != expected_per_catalog:
            raise IncompleteAdapterEvidenceError(
                f"dwell {dwell_id!r} catalog {catalog_number} has an incomplete state bank"
            )
        reduced = _finite(
            row.get("best_single_delta_from_null"),
            "source catalogue minimum reduced objective",
        )
        selected = row.get("best_single_selected")
        if not isinstance(selected, bool) or selected != (reduced < 0.0):
            raise ValueError(
                f"dwell {dwell_id!r} catalog {catalog_number} selection disagrees with its minimum"
            )
        _finite(row.get("best_single_total_cost"), "source catalogue minimum total cost")
        minima.append(
            _CatalogMinimum(
                catalog_number=catalog_number,
                hypothesis_id=_nonempty(
                    row.get("best_hypothesis_id"),
                    "source best hypothesis ID",
                ),
                reduced_objective=reduced,
                generated_state_count=generated_count,
            )
        )
    catalog_numbers = tuple(item.catalog_number for item in minima)
    if len(set(catalog_numbers)) != len(catalog_numbers):
        raise ValueError(f"dwell {dwell_id!r} source repeats a NORAD catalogue number")
    expected_order = tuple(
        item.catalog_number
        for item in sorted(
            minima,
            key=lambda item: (item.reduced_objective, item.catalog_number, item.hypothesis_id),
        )
    )
    if catalog_numbers != expected_order:
        raise ValueError(f"dwell {dwell_id!r} source ranking is not canonical")

    partition = _object(
        source.get("catalogue_identity_partition"),
        "source catalogue identity partition",
    )
    partition_digest = _canonical_sha256(
        partition.get("partition_content_digest"),
        "source identity-partition content digest",
    )
    partition_payload = dict(partition)
    partition_payload.pop("partition_content_digest", None)
    if canonical_digest(partition_payload) != partition_digest:
        raise ValueError(f"dwell {dwell_id!r} identity-partition content digest mismatch")
    if (
        partition.get("schema") != SOURCE_IDENTITY_PARTITION_SCHEMA
        or partition.get("algorithm") != SOURCE_IDENTITY_PARTITION_ALGORITHM
        or partition.get("partition_exhausted") is not True
        or partition.get("partition_pruned") is not False
        or partition.get("eligibility_semantics")
        != "named-and-full-window-visible-over-declared-delay-grid"
    ):
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} identity geometry partition is incomplete"
        )
    named = tuple(
        _positive_catalog(item, "source named catalog")
        for item in _list(
            partition.get("named_catalog_numbers"),
            "source named catalog numbers",
        )
    )
    eligible = tuple(
        _positive_catalog(item, "source identity-partition eligible catalog")
        for item in _list(
            partition.get("eligible_catalog_numbers"),
            "source identity-partition eligible catalogs",
        )
    )
    ineligible = tuple(
        _positive_catalog(item, "source named-ineligible catalog")
        for item in _list(
            partition.get("named_ineligible_catalog_numbers"),
            "source named-ineligible catalog numbers",
        )
    )
    if any(values != tuple(sorted(set(values))) for values in (named, eligible, ineligible)):
        raise ValueError(f"dwell {dwell_id!r} identity partition is not sorted and unique")
    if (
        set(eligible) & set(ineligible)
        or tuple(sorted((*eligible, *ineligible))) != named
        or set(eligible) != set(catalog_numbers)
    ):
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} identity partition does not reconcile with exact rows"
        )
    count_fields = (
        ("named_catalog_count", len(named)),
        ("eligible_catalog_count", len(eligible)),
        ("named_ineligible_catalog_count", len(ineligible)),
    )
    if any(
        _integer(partition.get(field), f"source {field}") != expected
        for field, expected in count_fields
    ):
        raise ValueError(f"dwell {dwell_id!r} identity-partition counts do not reconcile")
    digest_fields = (
        ("named_catalog_numbers_digest", named),
        ("eligible_catalog_numbers_digest", eligible),
        ("named_ineligible_catalog_numbers_digest", ineligible),
    )
    if any(
        _canonical_sha256(partition.get(field), f"source {field}") != canonical_digest(list(values))
        for field, values in digest_fields
    ):
        raise ValueError(f"dwell {dwell_id!r} identity-partition list digest mismatch")
    finite_partition_digest = _canonical_sha256(
        finite_universe.get("identity_partition_content_digest"),
        "finite-universe identity-partition digest",
    )
    if finite_partition_digest != partition_digest:
        raise ValueError(f"dwell {dwell_id!r} finite-universe partition binding mismatch")

    generated_total = sum(item.generated_state_count for item in minima)
    if generated_total != _integer(
        fine.get("generated_state_count"), "source generated state total"
    ) or generated_total != _integer(
        fine.get("generated_state_count_upper_bound"),
        "source generated state upper bound",
    ):
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} generated state counts do not exhaust the declared bank"
        )
    negative_count = sum(item.reduced_objective < 0.0 for item in minima)
    if _integer(
        fine.get("negative_catalogue_minimum_count"), "negative minimum count"
    ) != negative_count or fine.get("all_catalogue_minima_nonactivating") is not (
        negative_count == 0
    ):
        raise ValueError(f"dwell {dwell_id!r} minimum summary is internally inconsistent")

    decision = _object(source.get("decision"), "source decision")
    objective = _object(
        decision.get("full_persisted_inventory_objective"),
        "source full objective",
    )
    null_objective = _finite(objective.get("null_cost"), "source null objective")
    total_objective = _finite(objective.get("total_cost"), "source total objective")
    decision_delta = _finite(objective.get("delta_from_null"), "source decision delta")
    primitive_delta = total_objective - null_objective
    tolerance = 2.0 * max(
        math.ulp(null_objective),
        math.ulp(total_objective),
        math.ulp(primitive_delta),
        math.ulp(decision_delta),
    )
    if abs(primitive_delta - decision_delta) > tolerance or (primitive_delta < 0.0) != (
        decision_delta < 0.0
    ):
        raise ValueError(f"dwell {dwell_id!r} source full objective is inconsistent")
    selected_catalogs = tuple(
        _positive_catalog(item, "source selected catalog")
        for item in _list(decision.get("selected_catalog_numbers"), "source selected catalogs")
    )
    expected_selected = () if negative_count == 0 else (minima[0].catalog_number,)
    expected_delta = 0.0 if negative_count == 0 else minima[0].reduced_objective
    if (
        selected_catalogs != expected_selected
        or decision_delta != expected_delta
        or decision.get("result_kind")
        != ("bounded_exact_null" if negative_count == 0 else "activation_witness")
    ):
        raise ValueError(f"dwell {dwell_id!r} source decision disagrees with exact minima")

    search_configuration = _object(
        source.get("search_configuration"),
        "source search configuration",
    )
    if canonical_digest(search_configuration) != _canonical_sha256(
        source.get("search_configuration_digest"),
        "source search-configuration digest",
    ):
        raise ValueError(f"dwell {dwell_id!r} source search-configuration digest mismatch")
    return source, fine, tuple(minima), objective, partition


def _load_duration_and_nested_files(
    *,
    dwell_id: str,
    source: dict[str, Any],
    source_path: Path,
) -> tuple[dict[str, Any], dict[str, _FileReference]]:
    references = {
        key: _artifact_nested_reference(source, key, artifact_path=source_path)
        for key in ("duration_dataset", "pilot_scan", "score_calibration", "tle")
    }
    for key, reference in references.items():
        _verify_reference(reference, f"dwell {dwell_id!r} nested {key}")
    dataset = _read_json(references["duration_dataset"].path)
    capture = _object(dataset.get("capture"), "duration input capture")
    timing = _object(dataset.get("timing_binding"), "duration input timing binding")
    _nonempty(capture.get("session_id"), "duration input session ID")
    _canonical_sha256(
        capture.get("recording_manifest_digest"),
        "duration input recording-manifest digest",
    )
    _integer(timing.get("first_estimate_utc_ns"), "duration first-estimate UTC")
    _integer(timing.get("first_earliest_utc_ns"), "duration first-earliest UTC")
    _integer(timing.get("last_latest_utc_ns"), "duration last-latest UTC")
    return dataset, references


def _validate_source_crosslinks(
    *,
    dwell_id: str,
    source: dict[str, Any],
    dataset: dict[str, Any],
    nested: dict[str, _FileReference],
) -> None:
    """Recompute content links that a self-consistent forged summary could fake."""

    search = _object(source.get("search_configuration"), "source search configuration")
    source_input = _object(source.get("input"), "source input")
    source_window = _object(source.get("window"), "source window")
    source_configuration = _object(source.get("configuration"), "source configuration")
    source_observer = _object(source.get("observer"), "source observer")
    calibration = _read_json(nested["score_calibration"].path)
    capture = _object(dataset.get("capture"), "duration capture")
    frequency = _object(dataset.get("frequency_binding"), "duration frequency binding")

    expected_observer = dict(source_observer)
    if expected_observer.pop("capture_bound", None) is not False:
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} observer authority semantics are unsupported"
        )
    screen_configuration = _object(
        search.get("catalogue_screen"),
        "source catalogue-screen configuration",
    )
    fine = _object(
        _object(source.get("catalogue_search"), "source catalogue search").get("fine_stage"),
        "source fine catalogue stage",
    )
    expected_links = (
        (search.get("algorithm"), SOURCE_ALGORITHM, "search algorithm"),
        (
            search.get("state_generation_algorithm"),
            bounded.screen.ALGORITHM,
            "state algorithm",
        ),
        (search.get("output_schema"), SOURCE_SCHEMA, "search output schema"),
        (search.get("input_schema"), dataset.get("schema"), "duration input schema"),
        (search.get("tle_digest"), nested["tle"].file_digest, "TLE digest"),
        (
            search.get("score_calibration_digest"),
            nested["score_calibration"].file_digest,
            "score-calibration digest",
        ),
        (
            search.get("score_calibration_schema"),
            calibration.get("schema"),
            "score-calibration schema",
        ),
        (search.get("raw_replay"), source_configuration, "raw replay configuration"),
        (search.get("observer"), expected_observer, "observer configuration"),
        (
            search.get("sky_frequency_hz"),
            frequency.get("sky_frequency_hz"),
            "sky frequency",
        ),
        (screen_configuration.get("algorithm"), SOURCE_ALGORITHM, "screen algorithm"),
        (
            screen_configuration.get("fine_delay_grid"),
            fine.get("delay_grid"),
            "fine delay grid",
        ),
        (
            screen_configuration.get("modes_per_delay"),
            fine.get("modes_per_delay"),
            "modes per delay",
        ),
    )
    mismatches = [label for observed, expected, label in expected_links if observed != expected]
    if mismatches:
        raise ValueError(
            f"dwell {dwell_id!r} source search cross-links disagree: {sorted(mismatches)!r}"
        )
    if search.get("producer_implementation") != bounded.producer_implementation_manifest():
        raise ValueError(
            f"dwell {dwell_id!r} source producer implementation manifest is not current"
        )
    observed_pilot_configuration = bounded.screen._pilot_scan_configuration(
        nested["pilot_scan"].path
    )
    if search.get("pilot_scan") != observed_pilot_configuration:
        raise ValueError(f"dwell {dwell_id!r} pilot-scan configuration cross-link mismatch")

    start_s = _finite(source_window.get("start_s"), "source window start")
    end_s = _finite(source_window.get("end_s"), "source window end")
    sample_rate_hz = _integer(capture.get("sample_rate_hz"), "duration sample rate", minimum=1)
    start_sample = round(start_s * sample_rate_hz)
    end_sample = round(end_s * sample_rate_hz)
    schedule = tuple(
        sorted(
            _list(dataset.get("scheduled_probes"), "duration scheduled probes"),
            key=lambda item: (
                _integer(_object(item, "scheduled probe").get("schedule_ordinal"), "ordinal"),
                _nonempty(_object(item, "scheduled probe").get("probe_id"), "probe ID"),
            ),
        )
    )
    window_rows = tuple(
        _object(item, "scheduled probe")
        for item in schedule
        if start_sample
        <= _integer(_object(item, "scheduled probe").get("probe_sample_start"), "probe sample")
        < end_sample
    )
    scheduled_probe_ids = tuple(
        _nonempty(item.get("probe_id"), "scheduled probe ID") for item in window_rows
    )
    expected_member_digest = bounded.screen.member_evaluation_scope_digest(
        duration_dataset_digest=nested["duration_dataset"].file_digest,
        pilot_scan_digest=nested["pilot_scan"].file_digest,
        session_id=_nonempty(capture.get("session_id"), "duration session"),
        recording_manifest_digest=_canonical_sha256(
            capture.get("recording_manifest_digest"),
            "duration recording-manifest digest",
        ),
        stream_id=_nonempty(capture.get("stream_id"), "duration stream ID"),
        receiver_id=_integer(capture.get("receiver_id"), "duration receiver ID"),
        tuning_tag=_nonempty(frequency.get("tuning_tag"), "duration tuning tag"),
        sky_frequency_hz=_finite(frequency.get("sky_frequency_hz"), "duration sky frequency"),
        scheduled_probe_ids=scheduled_probe_ids,
        window_start_s=start_s,
        window_end_s=end_s,
    )
    if search.get("member_evaluation_scope_digest") != expected_member_digest:
        raise ValueError(f"dwell {dwell_id!r} member evaluation-scope digest mismatch")
    search_window = _object(search.get("window"), "source search window")
    expected_window_links = {
        "start_s": start_s,
        "end_s": end_s,
        "duration_s": end_s - start_s,
        "scheduled_probe_count": len(window_rows),
        "cell_count": _integer(source_window.get("cell_count"), "source cell count"),
    }
    if search_window != expected_window_links:
        raise ValueError(f"dwell {dwell_id!r} search window cross-link mismatch")
    if (
        _integer(source_window.get("scheduled_probe_count"), "source scheduled-probe count")
        != len(window_rows)
        or source_window.get("cell_duration_s") != source_configuration.get("cell_duration_s")
        or source_window.get("minimum_active_duration_s")
        != source_configuration.get("minimum_active_duration_s")
    ):
        raise ValueError(f"dwell {dwell_id!r} top-level window/configuration link mismatch")
    if source_input.get("tle_digest") != search.get("tle_digest"):
        raise ValueError(f"dwell {dwell_id!r} source input/search TLE link mismatch")


def _control_nested_files(
    *,
    document: dict[str, Any],
    path: Path,
    expected_session_id: str,
) -> tuple[set[str], str]:
    control_input = _object(document.get("input"), "paired-control input")
    if control_input.get("session_id") != expected_session_id:
        raise ValueError("paired-control session differs from the dwell session")
    tle_digest = _canonical_sha256(control_input.get("tle_digest"), "paired-control TLE digest")
    tle_reference = _FileReference(
        _resolve(
            control_input.get("tle_path"),
            relative_to=path.parent,
            label="paired-control TLE path",
        ),
        tle_digest,
    )
    calibration_reference = _FileReference(
        _resolve(
            control_input.get("score_calibration_path"),
            relative_to=path.parent,
            label="paired-control calibration path",
        ),
        _canonical_sha256(
            control_input.get("score_calibration_digest"),
            "paired-control calibration digest",
        ),
    )
    _verify_reference(tle_reference, "paired-control TLE")
    _verify_reference(calibration_reference, "paired-control calibration")

    duration_digests: set[str] = set()
    observed_sessions: set[str] = set()
    for raw_item in _list(control_input.get("duration_inputs"), "paired-control duration inputs"):
        item = _object(raw_item, "paired-control duration input")
        duration_reference = _FileReference(
            _resolve(item.get("path"), relative_to=path.parent, label="control duration path"),
            _canonical_sha256(item.get("file_digest"), "control duration digest"),
        )
        scan_reference = _FileReference(
            _resolve(
                item.get("pilot_scan_path"),
                relative_to=path.parent,
                label="control pilot-scan path",
            ),
            _canonical_sha256(item.get("pilot_scan_digest"), "control pilot-scan digest"),
        )
        _verify_reference(duration_reference, "paired-control duration input")
        _verify_reference(scan_reference, "paired-control pilot scan")
        scan_document = _read_json(scan_reference.path)
        if canonical_digest(scan_document) != _canonical_sha256(
            item.get("pilot_scan_content_digest"),
            "control pilot-scan content digest",
        ):
            raise ValueError("paired-control pilot-scan content digest mismatch")
        duration_document = _read_json(duration_reference.path)
        capture = _object(duration_document.get("capture"), "control duration capture")
        observed_sessions.add(_nonempty(capture.get("session_id"), "control duration session"))
        duration_digests.add(duration_reference.file_digest)
    if observed_sessions != {expected_session_id}:
        raise ValueError("paired-control duration inputs do not form the declared dwell session")
    return duration_digests, tle_digest


def _validated_control(
    *,
    reference: _FileReference,
    dwell_id: str,
    session_id: str,
    source_dataset_digest: str,
    source_artifact_digest: str,
    source_tle_digest: str,
    window_start_utc_ns: int,
    window_end_utc_ns: int,
) -> _ControlEvidence:
    _verify_reference(reference, f"dwell {dwell_id!r} paired-control artifact")
    document = _read_json(reference.path)
    multipath_schema = (
        document.get("schema") == paired.OUTPUT_SCHEMA
        and document.get("algorithm") == paired.ALGORITHM
    )
    fixed_target_schema = (
        document.get("schema") == fixed_target.OUTPUT_SCHEMA
        and document.get("algorithm") == fixed_target.ALGORITHM
    )
    if not multipath_schema and not fixed_target_schema:
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} control artifact has an unsupported schema or algorithm"
        )
    if fixed_target_schema:
        payload_digest = _canonical_sha256(
            document.get("payload_content_digest"), "fixed-target payload content digest"
        )
        payload = dict(document)
        payload.pop("payload_content_digest", None)
        if canonical_digest(payload) != payload_digest:
            raise ValueError("fixed-target payload content digest does not recompute")
    duration_digests, tle_digest = _control_nested_files(
        document=document,
        path=reference.path,
        expected_session_id=session_id,
    )
    if source_dataset_digest not in duration_digests:
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} control does not include the source duration input"
        )
    if tle_digest != source_tle_digest:
        raise IncompleteAdapterEvidenceError(f"dwell {dwell_id!r} control uses different TLE bytes")
    if fixed_target_schema:
        control_input = _object(document.get("input"), "fixed-target control input")
        if (
            _canonical_sha256(
                control_input.get("source_artifact_file_digest"),
                "fixed-target control source digest",
            )
            != source_artifact_digest
        ):
            raise IncompleteAdapterEvidenceError(
                f"dwell {dwell_id!r} fixed-target control uses a different source artifact"
            )
    window = _object(document.get("window"), "paired-control window")
    if (
        _integer(window.get("start_utc_ns"), "control window start") != window_start_utc_ns
        or _integer(window.get("end_utc_ns"), "control window end") != window_end_utc_ns
    ):
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} control does not cover the exact source window"
        )

    common = _object(document.get("common"), "paired-control common documents")
    family_plan = _object(common.get("family_plan"), "paired-control family plan")
    minimum_advantage_cost = _finite(
        family_plan.get("minimum_advantage_cost"),
        "paired-control minimum advantage cost",
    )
    calibrated = family_plan.get("advantage_threshold_calibrated")
    preregistered = family_plan.get("external_preregistration_verified")
    if not isinstance(calibrated, bool) or not isinstance(preregistered, bool):
        raise ValueError("paired-control gate-authority flags must be Boolean")
    arms_raw = _list(document.get("arms"), "paired-control arms")
    if any(not isinstance(item, dict) for item in arms_raw):
        raise ValueError("paired-control arms must be objects")
    if multipath_schema:
        recomputed = paired.adjudicate_paired_arms(
            arms=tuple(cast(dict[str, Any], item) for item in arms_raw),
            common=common,
            minimum_advantage_cost=minimum_advantage_cost,
            advantage_threshold_calibrated=calibrated,
            external_preregistration_verified=preregistered,
        )
    else:
        recomputed = fixed_target.adjudicate_fixed_norad_arms(
            arms=tuple(cast(dict[str, Any], item) for item in arms_raw),
            common=common,
        )
    if recomputed != document.get("adjudication"):
        raise ValueError("paired-control adjudication does not recompute exactly")

    search_universe = _object(common.get("search_universe"), "control search universe")
    if multipath_schema:
        catalog_rows = _list(search_universe.get("catalogs"), "control catalogue list")
        catalogs = tuple(
            _positive_catalog(
                _object(row, "control catalogue row").get("catalog_number"),
                "control catalog",
            )
            for row in catalog_rows
        )
    else:
        catalogs = (
            _positive_catalog(
                search_universe.get("target_catalog_number"),
                "fixed-target control catalog",
            ),
        )
    if len(set(catalogs)) != len(catalogs):
        raise ValueError("paired-control catalogue list repeats a NORAD identity")
    identity_arms = [item for item in arms_raw if item.get("role") == "identity"]
    if len(identity_arms) != 1:
        raise ValueError("paired-control artifact must contain exactly one identity arm")
    identity_decision = _object(identity_arms[0].get("decision"), "control identity decision")
    identity_selected = tuple(
        _positive_catalog(item, "control identity selected catalog")
        for item in _list(
            identity_decision.get("selected_catalog_numbers"),
            "control identity selected catalogs",
        )
    )
    if any(item not in set(catalogs) for item in identity_selected):
        raise ValueError("paired-control identity selected an undeclared catalogue")
    return _ControlEvidence(
        file_digest=reference.file_digest,
        content_digest=canonical_digest(document),
        disposition=_nonempty(recomputed.get("disposition"), "control disposition"),
        comparable=(
            recomputed.get("comparable") is True
            if multipath_schema
            else recomputed.get("association_authority_comparable") is True
        ),
        paired_gate_passed=recomputed.get("paired_gate_passed") is True,
        scientific_control_failed=(
            recomputed.get("conditional_control_test_failed") is True
            if fixed_target_schema
            else (
                recomputed.get("comparable") is True
                and recomputed.get("paired_gate_passed") is not True
            )
        ),
        fixed_target=fixed_target_schema,
        catalog_numbers=tuple(sorted(catalogs)),
        identity_selected_catalog_numbers=tuple(sorted(identity_selected)),
    )


def _validated_qualification(
    *,
    dwell_id: str,
    reference: _FileReference,
    source_reference: _FileReference,
    session_id: str,
    source_dataset_digest: str,
    source_tle_digest: str,
    dataset: dict[str, Any],
    window_start_utc_ns: int,
    window_end_utc_ns: int,
    control_references: tuple[_FileReference, ...],
) -> tuple[dict[str, Any], tuple[_ControlEvidence, ...]]:
    _verify_reference(reference, f"dwell {dwell_id!r} qualification receipt")
    receipt = _read_json(reference.path)
    _strict_keys(
        receipt,
        {
            "schema",
            "dwell_id",
            "source_artifact_file_digest",
            "session_id",
            "tle_snapshot",
            "timing",
            "control_artifact_file_digests",
        },
        "dwell qualification receipt",
    )
    if receipt.get("schema") != QUALIFICATION_SCHEMA or receipt.get("dwell_id") != dwell_id:
        raise ValueError("dwell qualification schema or dwell ID mismatch")
    if (
        _canonical_sha256(
            receipt.get("source_artifact_file_digest"),
            "qualification source-artifact digest",
        )
        != source_reference.file_digest
        or receipt.get("session_id") != session_id
    ):
        raise ValueError("dwell qualification source or session binding mismatch")
    receipt_control_digests = tuple(
        _canonical_sha256(item, "qualification control-artifact digest")
        for item in _list(
            receipt.get("control_artifact_file_digests"),
            "qualification control-artifact digests",
        )
    )
    expected_control_digests = tuple(item.file_digest for item in control_references)
    if receipt_control_digests != expected_control_digests or len(
        set(receipt_control_digests)
    ) != len(receipt_control_digests):
        raise ValueError("qualification control-artifact inventory differs or repeats a digest")

    tle = _object(receipt.get("tle_snapshot"), "qualification TLE snapshot")
    _strict_keys(
        tle,
        {
            "file_digest",
            "authority",
            "authority_snapshot_id",
            "snapshot_acquired_utc_ns",
            "available_to_analysis_utc_ns",
        },
        "qualification TLE snapshot",
    )
    if _canonical_sha256(tle.get("file_digest"), "qualification TLE digest") != source_tle_digest:
        raise ValueError("qualification TLE digest differs from source TLE bytes")
    _nonempty(tle.get("authority"), "qualification TLE authority")
    _nonempty(tle.get("authority_snapshot_id"), "qualification TLE snapshot ID")
    acquired_utc_ns = _integer(
        tle.get("snapshot_acquired_utc_ns"),
        "qualification TLE acquisition UTC",
    )
    available_utc_ns = _integer(
        tle.get("available_to_analysis_utc_ns"),
        "qualification TLE availability UTC",
    )
    if acquired_utc_ns > available_utc_ns or available_utc_ns > window_start_utc_ns:
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} TLE snapshot was not causally available before the window"
        )

    timing = _object(receipt.get("timing"), "qualification timing")
    _strict_keys(
        timing,
        {
            "duration_dataset_file_digest",
            "authority",
            "first_estimate_utc_ns",
            "window_start_utc_ns",
            "window_end_utc_ns",
            "capture_clock_binding_verified",
        },
        "qualification timing",
    )
    dataset_timing = _object(dataset.get("timing_binding"), "duration timing binding")
    if (
        _canonical_sha256(
            timing.get("duration_dataset_file_digest"),
            "qualification duration-input digest",
        )
        != source_dataset_digest
        or _integer(timing.get("first_estimate_utc_ns"), "qualified first estimate")
        != _integer(dataset_timing.get("first_estimate_utc_ns"), "duration first estimate")
        or _integer(timing.get("window_start_utc_ns"), "qualified window start")
        != window_start_utc_ns
        or _integer(timing.get("window_end_utc_ns"), "qualified window end") != window_end_utc_ns
        or timing.get("capture_clock_binding_verified") is not True
    ):
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} absolute capture timing is not exactly qualified"
        )
    _nonempty(timing.get("authority"), "qualification timing authority")

    controls = tuple(
        _validated_control(
            reference=item,
            dwell_id=dwell_id,
            session_id=session_id,
            source_dataset_digest=source_dataset_digest,
            source_artifact_digest=source_reference.file_digest,
            source_tle_digest=source_tle_digest,
            window_start_utc_ns=window_start_utc_ns,
            window_end_utc_ns=window_end_utc_ns,
        )
        for item in control_references
    )
    return receipt, controls


def _load_dwell(
    *,
    raw: dict[str, Any],
    request_path: Path,
) -> _DwellEvidence:
    _strict_keys(
        raw,
        {"dwell_id", "source_artifact", "qualification_receipt", "control_artifacts"},
        "request dwell",
    )
    dwell_id = _nonempty(raw.get("dwell_id"), "request dwell ID")
    source_reference = _file_reference(
        raw.get("source_artifact"),
        relative_to=request_path.parent,
        label=f"dwell {dwell_id!r} source artifact",
    )
    qualification_reference = _file_reference(
        raw.get("qualification_receipt"),
        relative_to=request_path.parent,
        label=f"dwell {dwell_id!r} qualification receipt",
    )
    control_references = tuple(
        _file_reference(
            item,
            relative_to=request_path.parent,
            label=f"dwell {dwell_id!r} control artifact",
        )
        for item in _list(raw.get("control_artifacts"), "request control artifacts")
    )
    if len({item.file_digest for item in control_references}) != len(control_references):
        raise ValueError(f"dwell {dwell_id!r} repeats a control artifact")

    source, fine, minima, objective, identity_partition = _validated_source(
        dwell_id=dwell_id,
        source_reference=source_reference,
    )
    dataset, nested = _load_duration_and_nested_files(
        dwell_id=dwell_id,
        source=source,
        source_path=source_reference.path,
    )
    _validate_source_crosslinks(
        dwell_id=dwell_id,
        source=source,
        dataset=dataset,
        nested=nested,
    )
    if (
        _canonical_sha256(
            identity_partition.get("tle_digest"),
            "source identity-partition TLE digest",
        )
        != nested["tle"].file_digest
    ):
        raise ValueError(f"dwell {dwell_id!r} identity partition uses different TLE bytes")
    capture = _object(dataset.get("capture"), "duration input capture")
    timing = _object(dataset.get("timing_binding"), "duration input timing")
    session_id = _nonempty(capture.get("session_id"), "duration input session")
    recording_manifest_digest = _canonical_sha256(
        capture.get("recording_manifest_digest"),
        "duration recording-manifest digest",
    )
    first_estimate_utc_ns = _integer(
        timing.get("first_estimate_utc_ns"),
        "duration first-estimate UTC",
    )
    source_window = _object(source.get("window"), "source window")
    window_start_utc_ns = first_estimate_utc_ns + _seconds_to_ns(
        source_window.get("start_s"),
        "source window start",
    )
    window_end_utc_ns = first_estimate_utc_ns + _seconds_to_ns(
        source_window.get("end_s"),
        "source window end",
    )
    if (
        window_end_utc_ns <= window_start_utc_ns
        or window_start_utc_ns
        < _integer(timing.get("first_earliest_utc_ns"), "duration first-earliest UTC")
        or window_end_utc_ns
        > _integer(timing.get("last_latest_utc_ns"), "duration last-latest UTC")
    ):
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} source window is not contained in capture timing bounds"
        )
    timing_approximation = _object(
        source.get("timing_approximation"),
        "source timing approximation",
    )
    if (
        timing_approximation.get("prediction_epoch") != "scheduled_probe_start"
        or timing_approximation.get("candidate_local_epoch_applied") is not False
    ):
        raise IncompleteAdapterEvidenceError(
            f"dwell {dwell_id!r} uses unsupported prediction-time semantics"
        )

    receipt, controls = _validated_qualification(
        dwell_id=dwell_id,
        reference=qualification_reference,
        source_reference=source_reference,
        session_id=session_id,
        source_dataset_digest=nested["duration_dataset"].file_digest,
        source_tle_digest=nested["tle"].file_digest,
        dataset=dataset,
        window_start_utc_ns=window_start_utc_ns,
        window_end_utc_ns=window_end_utc_ns,
        control_references=control_references,
    )
    tle_receipt = _object(receipt["tle_snapshot"], "qualification TLE snapshot")
    return _DwellEvidence(
        dwell_id=dwell_id,
        session_id=session_id,
        recording_manifest_digest=recording_manifest_digest,
        source_path=source_reference.path,
        source_file_digest=source_reference.file_digest,
        source_content_digest=canonical_digest(source),
        dataset_file_digest=nested["duration_dataset"].file_digest,
        pilot_scan_file_digest=nested["pilot_scan"].file_digest,
        calibration_file_digest=nested["score_calibration"].file_digest,
        tle_file_digest=nested["tle"].file_digest,
        window_start_utc_ns=window_start_utc_ns,
        window_end_utc_ns=window_end_utc_ns,
        null_objective=_finite(objective.get("null_cost"), "source null objective"),
        minima=minima,
        named_catalog_numbers=tuple(identity_partition["named_catalog_numbers"]),
        named_ineligible_catalog_numbers=tuple(
            identity_partition["named_ineligible_catalog_numbers"]
        ),
        identity_partition_content_digest=_canonical_sha256(
            identity_partition.get("partition_content_digest"),
            "source identity-partition content digest",
        ),
        source_generated_state_count=_integer(
            fine.get("generated_state_count"),
            "source generated state total",
        ),
        qualification_path=qualification_reference.path,
        qualification_file_digest=qualification_reference.file_digest,
        qualification_content_digest=canonical_digest(receipt),
        tle_authority=_nonempty(tle_receipt.get("authority"), "TLE authority"),
        tle_authority_snapshot_id=_nonempty(
            tle_receipt.get("authority_snapshot_id"),
            "TLE authority snapshot ID",
        ),
        tle_snapshot_acquired_utc_ns=_integer(
            tle_receipt.get("snapshot_acquired_utc_ns"),
            "TLE snapshot acquisition UTC",
        ),
        controls=controls,
    )


def _validated_universe(
    *,
    reference: _FileReference,
    dwells: tuple[_DwellEvidence, ...],
) -> tuple[dict[str, Any], tuple[int, ...]]:
    _verify_reference(reference, "frozen catalogue-universe receipt")
    document = _read_json(reference.path)
    _strict_keys(
        document,
        {
            "schema",
            "algorithm",
            "catalog_numbers",
            "expected_catalog_count",
            "candidate_universe_exhausted",
            "candidate_universe_pruned",
            "source_artifacts",
            "frozen_at_utc_ns",
            "selection_frozen_before_reduction",
            "external_preregistration_verified",
        },
        "frozen catalogue universe",
    )
    if document.get("schema") != UNIVERSE_SCHEMA or document.get("algorithm") != UNIVERSE_ALGORITHM:
        raise ValueError("frozen catalogue-universe schema or algorithm mismatch")
    if (
        document.get("candidate_universe_exhausted") is not True
        or document.get("candidate_universe_pruned") is not False
        or document.get("selection_frozen_before_reduction") is not True
        or document.get("external_preregistration_verified") is not False
    ):
        raise IncompleteAdapterEvidenceError(
            "catalogue union is not explicitly exhausted, unpruned, and frozen"
        )
    _integer(document.get("frozen_at_utc_ns"), "catalogue-universe freeze UTC")
    catalogs = tuple(
        _positive_catalog(item, "frozen universe catalog")
        for item in _list(document.get("catalog_numbers"), "frozen universe catalogs")
    )
    if catalogs != tuple(sorted(set(catalogs))):
        raise ValueError("frozen catalogue union must be sorted and unique")
    if _integer(document.get("expected_catalog_count"), "frozen universe catalog count") != len(
        catalogs
    ):
        raise ValueError("frozen catalogue-universe count does not reconcile")
    expected_union = tuple(
        sorted({minimum.catalog_number for dwell in dwells for minimum in dwell.minima})
    )
    if catalogs != expected_union:
        raise IncompleteAdapterEvidenceError(
            "frozen catalogue universe differs from the exact union of dwell-eligible rows"
        )

    source_rows = tuple(
        (
            _nonempty(
                _object(item, "universe source artifact").get("dwell_id"), "universe dwell ID"
            ),
            _canonical_sha256(
                _object(item, "universe source artifact").get("file_digest"),
                "universe source-artifact digest",
            ),
        )
        for item in _list(document.get("source_artifacts"), "universe source artifacts")
    )
    expected_sources = tuple((item.dwell_id, item.source_file_digest) for item in dwells)
    if source_rows != expected_sources or len(set(source_rows)) != len(source_rows):
        raise ValueError("frozen catalogue universe differs from the ordered source inventory")
    return document, catalogs


def _state_matrix(
    *,
    dwells: tuple[_DwellEvidence, ...],
    catalogs: tuple[int, ...],
) -> tuple[tuple[ExactDwellCatalogStateSpace, ...], list[dict[str, Any]]]:
    spaces = []
    rows = []
    for dwell in dwells:
        by_catalog = {item.catalog_number: item for item in dwell.minima}
        certified_ineligible = set(dwell.named_ineligible_catalog_numbers)
        for catalog in catalogs:
            minimum = by_catalog.get(catalog)
            if minimum is None:
                if catalog not in certified_ineligible:
                    raise IncompleteAdapterEvidenceError(
                        f"dwell {dwell.dwell_id!r} catalog {catalog} is absent without an "
                        "identity-level geometry-exclusion receipt"
                    )
                spaces.append(
                    ExactDwellCatalogStateSpace(
                        dwell_id=dwell.dwell_id,
                        catalog_number=catalog,
                        states=(),
                        expected_state_count=0,
                        supplied_state_space_exhausted=True,
                        pruned_state_count=0,
                    )
                )
                rows.append(
                    {
                        "dwell_id": dwell.dwell_id,
                        "catalog_number": catalog,
                        "eligibility": "certified_ineligible",
                        "source_generated_state_count": 0,
                        "compressed_exact_minimum_state_count": 0,
                        "state_id": None,
                        "reduced_objective": None,
                        "source_state_space_exhausted": True,
                        "source_state_space_pruned": False,
                    }
                )
                continue
            state_id = f"exact-minimum:{minimum.hypothesis_id}"
            spaces.append(
                ExactDwellCatalogStateSpace(
                    dwell_id=dwell.dwell_id,
                    catalog_number=catalog,
                    states=(FiniteDwellState(state_id, minimum.reduced_objective),),
                    expected_state_count=1,
                    supplied_state_space_exhausted=True,
                    pruned_state_count=0,
                )
            )
            rows.append(
                {
                    "dwell_id": dwell.dwell_id,
                    "catalog_number": catalog,
                    "eligibility": "evaluated_exact_minimum",
                    "source_generated_state_count": minimum.generated_state_count,
                    "compressed_exact_minimum_state_count": 1,
                    "state_id": state_id,
                    "reduced_objective": minimum.reduced_objective,
                    "source_state_space_exhausted": True,
                    "source_state_space_pruned": False,
                }
            )
    return tuple(spaces), rows


def _qualification_for_selected(
    *,
    result: Any,
    dwells: tuple[_DwellEvidence, ...],
    minimum_association_improvement_cost: float,
) -> tuple[Disposition, list[dict[str, Any]], list[str]]:
    if result.selected_catalog_number is None:
        return "finite_null", [], []
    improvement = -float(result.reduced_objective)
    if not improvement > minimum_association_improvement_cost:
        return (
            "association_threshold_not_met",
            [],
            [
                "shared-NORAD improvement is not strictly greater than the frozen "
                "association threshold"
            ],
        )
    selected = result.selected_catalog_number
    by_dwell = {item.dwell_id: item for item in dwells}
    rows = []
    failed = False
    unknown = False
    reasons = []
    for contribution in result.contributions:
        if not contribution.active:
            continue
        dwell = by_dwell[contribution.dwell_id]
        covering = tuple(
            item
            for item in dwell.controls
            if selected in item.catalog_numbers
            and (item.fixed_target or selected in item.identity_selected_catalog_numbers)
        )
        passed = tuple(item for item in covering if item.paired_gate_passed)
        scientific_failures = tuple(item for item in covering if item.scientific_control_failed)
        status: Literal["passed", "failed", "unknown"]
        if scientific_failures:
            status = "failed"
            failed = True
            reasons.append(
                f"dwell {dwell.dwell_id!r} selected NORAD {selected} failed its "
                "conditional prediction-time control"
            )
        elif passed:
            status = "passed"
        elif covering and all(item.comparable for item in covering):
            status = "failed"
            failed = True
            reasons.append(
                f"dwell {dwell.dwell_id!r} selected NORAD {selected} failed its paired control"
            )
        else:
            status = "unknown"
            unknown = True
            reasons.append(
                f"dwell {dwell.dwell_id!r} selected NORAD {selected} lacks a passed "
                "comparable control"
            )
        rows.append(
            {
                "dwell_id": dwell.dwell_id,
                "catalog_number": selected,
                "status": status,
                "covering_control_artifact_digests": [item.file_digest for item in covering],
                "passed_control_artifact_digests": [item.file_digest for item in passed],
            }
        )
    if failed:
        return "qualification_failed", rows, reasons
    if unknown:
        return "unknown_control_evidence", rows, reasons
    return "association", rows, reasons


def _json_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _write_new_document(path: Path, document: dict[str, Any]) -> str:
    payload = _json_bytes(document)
    try:
        with path.open("xb") as output:
            output.write(payload)
    except FileExistsError as error:
        raise ValueError(
            f"freeze output already exists and will not be overwritten: {path}"
        ) from error
    except OSError as error:
        raise ValueError(f"cannot write freeze output {path}: {error}") from error
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _refuse_protected_write(path: Path) -> None:
    resolved = path.resolve()
    for protected in (Path("/mnt/qnap01"), Path("/srv")):
        if resolved == protected or protected in resolved.parents:
            raise ValueError(f"cross-dwell outputs must not be written beneath {protected}")


def _prepare_freeze_dwell(
    *,
    raw: dict[str, Any],
    spec_path: Path,
    spec_schema: str,
) -> _FreezeDwell:
    expected_keys = {"dwell_id", "source_artifact", "tle_snapshot", "timing"}
    if spec_schema == FREEZE_SPEC_SCHEMA_V2:
        expected_keys.add("control_artifacts")
    _strict_keys(
        raw,
        expected_keys,
        "freeze-spec dwell",
    )
    dwell_id = _nonempty(raw.get("dwell_id"), "freeze-spec dwell ID")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", dwell_id) is None:
        raise ValueError("freeze-spec dwell ID is not safe for an output filename")
    source_reference = _file_reference(
        raw.get("source_artifact"),
        relative_to=spec_path.parent,
        label=f"freeze dwell {dwell_id!r} source artifact",
    )
    source, _fine, minima, _objective, partition = _validated_source(
        dwell_id=dwell_id,
        source_reference=source_reference,
    )
    dataset, nested = _load_duration_and_nested_files(
        dwell_id=dwell_id,
        source=source,
        source_path=source_reference.path,
    )
    _validate_source_crosslinks(
        dwell_id=dwell_id,
        source=source,
        dataset=dataset,
        nested=nested,
    )
    capture = _object(dataset.get("capture"), "duration capture")
    dataset_timing = _object(dataset.get("timing_binding"), "duration timing")
    session_id = _nonempty(capture.get("session_id"), "duration session ID")
    first_estimate_utc_ns = _integer(
        dataset_timing.get("first_estimate_utc_ns"),
        "duration first-estimate UTC",
    )
    source_window = _object(source.get("window"), "source window")
    window_start_utc_ns = first_estimate_utc_ns + _seconds_to_ns(
        source_window.get("start_s"),
        "source window start",
    )
    window_end_utc_ns = first_estimate_utc_ns + _seconds_to_ns(
        source_window.get("end_s"),
        "source window end",
    )

    tle = _object(raw.get("tle_snapshot"), "freeze-spec TLE snapshot")
    _strict_keys(
        tle,
        {
            "file_digest",
            "authority",
            "authority_snapshot_id",
            "snapshot_acquired_utc_ns",
            "available_to_analysis_utc_ns",
        },
        "freeze-spec TLE snapshot",
    )
    tle_digest = _canonical_sha256(tle.get("file_digest"), "freeze-spec TLE digest")
    if tle_digest != nested["tle"].file_digest:
        raise ValueError(f"freeze dwell {dwell_id!r} TLE assertion differs from source bytes")
    _nonempty(tle.get("authority"), "freeze-spec TLE authority")
    _nonempty(tle.get("authority_snapshot_id"), "freeze-spec TLE snapshot ID")
    acquired_utc_ns = _integer(
        tle.get("snapshot_acquired_utc_ns"),
        "freeze-spec TLE acquisition UTC",
    )
    available_utc_ns = _integer(
        tle.get("available_to_analysis_utc_ns"),
        "freeze-spec TLE availability UTC",
    )
    if acquired_utc_ns > available_utc_ns or available_utc_ns > window_start_utc_ns:
        raise IncompleteAdapterEvidenceError(
            f"freeze dwell {dwell_id!r} TLE snapshot is not causally available"
        )

    timing = _object(raw.get("timing"), "freeze-spec timing")
    _strict_keys(
        timing,
        {
            "duration_dataset_file_digest",
            "authority",
            "first_estimate_utc_ns",
            "window_start_utc_ns",
            "window_end_utc_ns",
            "capture_clock_binding_verified",
        },
        "freeze-spec timing",
    )
    if (
        _canonical_sha256(
            timing.get("duration_dataset_file_digest"),
            "freeze-spec duration-input digest",
        )
        != nested["duration_dataset"].file_digest
        or _integer(timing.get("first_estimate_utc_ns"), "freeze first estimate")
        != first_estimate_utc_ns
        or _integer(timing.get("window_start_utc_ns"), "freeze window start") != window_start_utc_ns
        or _integer(timing.get("window_end_utc_ns"), "freeze window end") != window_end_utc_ns
        or timing.get("capture_clock_binding_verified") is not True
    ):
        raise IncompleteAdapterEvidenceError(
            f"freeze dwell {dwell_id!r} timing assertions do not bind the source window"
        )
    _nonempty(timing.get("authority"), "freeze-spec timing authority")
    control_references = tuple(
        _file_reference(
            item,
            relative_to=spec_path.parent,
            label=f"freeze dwell {dwell_id!r} control artifact",
        )
        for item in (
            _list(raw.get("control_artifacts"), "freeze-spec control artifacts")
            if spec_schema == FREEZE_SPEC_SCHEMA_V2
            else []
        )
    )
    if len({item.file_digest for item in control_references}) != len(control_references):
        raise ValueError(f"freeze dwell {dwell_id!r} repeats a control artifact")
    for control_reference in control_references:
        _validated_control(
            reference=control_reference,
            dwell_id=dwell_id,
            session_id=session_id,
            source_dataset_digest=nested["duration_dataset"].file_digest,
            source_artifact_digest=source_reference.file_digest,
            source_tle_digest=nested["tle"].file_digest,
            window_start_utc_ns=window_start_utc_ns,
            window_end_utc_ns=window_end_utc_ns,
        )
    return _FreezeDwell(
        dwell_id=dwell_id,
        source_reference=source_reference,
        session_id=session_id,
        dataset_file_digest=nested["duration_dataset"].file_digest,
        tle_file_digest=nested["tle"].file_digest,
        first_estimate_utc_ns=first_estimate_utc_ns,
        window_start_utc_ns=window_start_utc_ns,
        window_end_utc_ns=window_end_utc_ns,
        eligible_catalog_numbers=tuple(sorted(item.catalog_number for item in minima)),
        named_ineligible_catalog_numbers=tuple(partition["named_ineligible_catalog_numbers"]),
        tle_snapshot=dict(tle),
        timing=dict(timing),
        control_references=control_references,
    )


def freeze_cross_dwell_request(
    *,
    spec_path: Path,
    expected_spec_digest: str,
    output_directory: Path,
) -> dict[str, Any]:
    """Create zero-control qualifications, exact union, and adapter request."""

    resolved_spec_path = spec_path.resolve()
    spec_digest = _canonical_sha256(expected_spec_digest, "freeze-spec digest")
    if _sha256(resolved_spec_path) != spec_digest:
        raise ValueError("cross-dwell freeze-spec digest mismatch")
    spec = _read_json(resolved_spec_path)
    _strict_keys(
        spec,
        {
            "schema",
            "association_id",
            "frozen_at_utc_ns",
            "sources",
            "required_confirmation_dwell_ids",
            "minimum_distinct_session_count",
            "shared_identity_cost",
            "minimum_association_improvement_cost",
        },
        "cross-dwell freeze spec",
    )
    spec_schema = spec.get("schema")
    if spec_schema not in {FREEZE_SPEC_SCHEMA, FREEZE_SPEC_SCHEMA_V2}:
        raise ValueError(
            f"expected cross-dwell freeze schema {FREEZE_SPEC_SCHEMA} or {FREEZE_SPEC_SCHEMA_V2}"
        )
    association_id = _nonempty(spec.get("association_id"), "freeze association ID")
    frozen_at_utc_ns = _integer(spec.get("frozen_at_utc_ns"), "freeze UTC")
    raw_sources = _list(spec.get("sources"), "freeze sources")
    if len(raw_sources) < 2 or any(not isinstance(item, dict) for item in raw_sources):
        raise ValueError("cross-dwell freeze requires at least two source objects")
    dwells = tuple(
        _prepare_freeze_dwell(
            raw=cast(dict[str, Any], item),
            spec_path=resolved_spec_path,
            spec_schema=cast(str, spec_schema),
        )
        for item in raw_sources
    )
    dwell_ids = tuple(item.dwell_id for item in dwells)
    session_ids = tuple(item.session_id for item in dwells)
    if len(set(dwell_ids)) != len(dwell_ids):
        raise ValueError("cross-dwell freeze repeats a dwell ID")
    if len(set(session_ids)) != len(session_ids):
        raise IncompleteAdapterEvidenceError(
            "cross-dwell freeze requires every declared dwell to have a unique session"
        )
    catalogs = tuple(
        sorted({catalog for dwell in dwells for catalog in dwell.eligible_catalog_numbers})
    )
    if not catalogs:
        raise IncompleteAdapterEvidenceError("cross-dwell freeze found no eligible catalogue rows")
    for dwell in dwells:
        accounted = set(dwell.eligible_catalog_numbers) | set(
            dwell.named_ineligible_catalog_numbers
        )
        missing = sorted(set(catalogs) - accounted)
        if missing:
            raise IncompleteAdapterEvidenceError(
                f"freeze dwell {dwell.dwell_id!r} lacks identity dispositions for {missing!r}"
            )

    required = tuple(
        _nonempty(item, "freeze required confirmation dwell ID")
        for item in _list(
            spec.get("required_confirmation_dwell_ids"),
            "freeze required confirmation dwell IDs",
        )
    )
    if required != tuple(sorted(set(required))) or not set(required) <= set(dwell_ids):
        raise ValueError("freeze required confirmation dwell IDs are not a sorted declared set")
    minimum_sessions = _integer(
        spec.get("minimum_distinct_session_count"),
        "freeze minimum distinct session count",
        minimum=2,
    )
    if minimum_sessions > len(session_ids):
        raise ValueError("freeze minimum session count exceeds its distinct session universe")
    shared_identity_cost = _finite(spec.get("shared_identity_cost"), "freeze shared identity cost")
    minimum_improvement = _finite(
        spec.get("minimum_association_improvement_cost"),
        "freeze minimum association improvement cost",
    )
    if shared_identity_cost < 0.0 or minimum_improvement < 0.0:
        raise ValueError("freeze objective thresholds must be nonnegative")

    resolved_output_directory = output_directory.resolve()
    _refuse_protected_write(resolved_output_directory)
    try:
        resolved_output_directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ValueError(f"cannot create freeze output directory: {error}") from error
    qualification_paths = tuple(
        resolved_output_directory / f"{item.dwell_id}.qualification.json" for item in dwells
    )
    universe_path = resolved_output_directory / "catalogue-universe.json"
    request_path = resolved_output_directory / "request.json"
    manifest_path = resolved_output_directory / "freeze-manifest.json"
    all_targets = (*qualification_paths, universe_path, request_path, manifest_path)
    existing = [str(path) for path in all_targets if path.exists()]
    if existing:
        raise ValueError(f"freeze outputs already exist and will not be overwritten: {existing!r}")

    qualification_references = []
    for dwell, path in zip(dwells, qualification_paths, strict=True):
        qualification = {
            "schema": QUALIFICATION_SCHEMA,
            "dwell_id": dwell.dwell_id,
            "source_artifact_file_digest": dwell.source_reference.file_digest,
            "session_id": dwell.session_id,
            "tle_snapshot": dwell.tle_snapshot,
            "timing": dwell.timing,
            "control_artifact_file_digests": [
                item.file_digest for item in dwell.control_references
            ],
        }
        digest = _write_new_document(path, qualification)
        qualification_references.append(_FileReference(path, digest))

    universe = {
        "schema": UNIVERSE_SCHEMA,
        "algorithm": UNIVERSE_ALGORITHM,
        "catalog_numbers": list(catalogs),
        "expected_catalog_count": len(catalogs),
        "candidate_universe_exhausted": True,
        "candidate_universe_pruned": False,
        "source_artifacts": [
            {
                "dwell_id": item.dwell_id,
                "file_digest": item.source_reference.file_digest,
            }
            for item in dwells
        ],
        "frozen_at_utc_ns": frozen_at_utc_ns,
        "selection_frozen_before_reduction": True,
        "external_preregistration_verified": False,
    }
    universe_digest = _write_new_document(universe_path, universe)
    request = {
        "schema": REQUEST_SCHEMA,
        "association_id": association_id,
        "candidate_universe": _reference_payload(universe_path, universe_digest),
        "dwells": [
            {
                "dwell_id": dwell.dwell_id,
                "source_artifact": _reference_payload(
                    dwell.source_reference.path,
                    dwell.source_reference.file_digest,
                ),
                "qualification_receipt": _reference_payload(
                    qualification.path,
                    qualification.file_digest,
                ),
                "control_artifacts": [
                    _reference_payload(item.path, item.file_digest)
                    for item in dwell.control_references
                ],
            }
            for dwell, qualification in zip(dwells, qualification_references, strict=True)
        ],
        "required_confirmation_dwell_ids": list(required),
        "minimum_distinct_session_count": minimum_sessions,
        "shared_identity_cost": shared_identity_cost,
        "minimum_association_improvement_cost": minimum_improvement,
    }
    request_digest = _write_new_document(request_path, request)
    manifest: dict[str, Any] = {
        "schema": FREEZE_MANIFEST_SCHEMA,
        "algorithm": ALGORITHM,
        "research_only": True,
        "association_not_tracking": True,
        "controls_status": (
            "recomputed_control_artifacts_supplied"
            if any(item.control_references for item in dwells)
            else "unknown_no_control_artifacts_supplied"
        ),
        "control_artifact_count": sum(len(item.control_references) for item in dwells),
        "association_claimed": False,
        "external_preregistration_verified": False,
        "freeze_spec": {
            "path": str(resolved_spec_path),
            "file_digest": spec_digest,
            "content_digest": canonical_digest(spec),
        },
        "request": _reference_payload(request_path, request_digest),
        "candidate_universe": _reference_payload(universe_path, universe_digest),
        "qualification_receipts": [
            _reference_payload(item.path, item.file_digest) for item in qualification_references
        ],
        "catalog_count": len(catalogs),
        "dwell_count": len(dwells),
        "session_count": len(session_ids),
        "caveat": (
            "the freeze timestamp and authority labels are digest-bound assertions, not "
            "external preregistration or cryptographic authentication"
        ),
    }
    manifest["payload_content_digest"] = canonical_digest(manifest)
    manifest_digest = _write_new_document(manifest_path, manifest)
    return {
        "manifest": manifest,
        "manifest_path": str(manifest_path),
        "manifest_file_digest": manifest_digest,
        "request_path": str(request_path),
        "request_file_digest": request_digest,
    }


def _reference_payload(path: Path, digest: str) -> dict[str, str]:
    return {"path": str(path.resolve()), "file_digest": digest}


def associate_cross_dwell_shared_norad(
    *,
    request_path: Path,
    expected_request_digest: str,
) -> dict[str, Any]:
    """Validate sealed artifacts, run the pure reducer, and serialize scope."""

    resolved_request_path = request_path.resolve()
    request_digest = _canonical_sha256(expected_request_digest, "request digest")
    if _sha256(resolved_request_path) != request_digest:
        raise ValueError("cross-dwell adapter request digest mismatch")
    request = _read_json(resolved_request_path)
    _strict_keys(
        request,
        {
            "schema",
            "association_id",
            "candidate_universe",
            "dwells",
            "required_confirmation_dwell_ids",
            "minimum_distinct_session_count",
            "shared_identity_cost",
            "minimum_association_improvement_cost",
        },
        "cross-dwell adapter request",
    )
    if request.get("schema") != REQUEST_SCHEMA:
        raise ValueError(f"expected cross-dwell request schema {REQUEST_SCHEMA}")
    association_id = _nonempty(request.get("association_id"), "association ID")
    raw_dwells = _list(request.get("dwells"), "request dwells")
    if len(raw_dwells) < 2 or any(not isinstance(item, dict) for item in raw_dwells):
        raise ValueError("cross-dwell adapter requires at least two dwell objects")
    dwells = tuple(
        _load_dwell(raw=cast(dict[str, Any], item), request_path=resolved_request_path)
        for item in raw_dwells
    )
    dwell_ids = tuple(item.dwell_id for item in dwells)
    session_ids = tuple(item.session_id for item in dwells)
    if len(set(dwell_ids)) != len(dwell_ids):
        raise ValueError("cross-dwell request repeats a dwell ID")
    if len(set(session_ids)) != len(session_ids):
        raise IncompleteAdapterEvidenceError(
            "cross-dwell association requires every declared dwell to have a unique session"
        )

    universe_reference = _file_reference(
        request.get("candidate_universe"),
        relative_to=resolved_request_path.parent,
        label="candidate universe",
    )
    universe, catalogs = _validated_universe(reference=universe_reference, dwells=dwells)
    required = tuple(
        _nonempty(item, "required confirmation dwell ID")
        for item in _list(
            request.get("required_confirmation_dwell_ids"),
            "required confirmation dwell IDs",
        )
    )
    if required != tuple(sorted(set(required))) or not required:
        raise ValueError("required confirmation dwell IDs must be sorted, unique, and nonempty")
    minimum_sessions = _integer(
        request.get("minimum_distinct_session_count"),
        "minimum distinct session count",
        minimum=2,
    )
    shared_identity_cost = _finite(request.get("shared_identity_cost"), "shared identity cost")
    if shared_identity_cost < 0.0:
        raise ValueError("shared identity cost must be nonnegative")
    minimum_association_improvement_cost = _finite(
        request.get("minimum_association_improvement_cost"),
        "minimum association improvement cost",
    )
    if minimum_association_improvement_cost < 0.0:
        raise ValueError("minimum association improvement cost must be nonnegative")

    spaces, matrix_rows = _state_matrix(dwells=dwells, catalogs=catalogs)
    problem = CrossDwellAssociationProblem(
        dwells=tuple(
            AssociationDwell(item.dwell_id, item.session_id, item.null_objective) for item in dwells
        ),
        catalog_numbers=catalogs,
        candidate_universe_catalog_count=len(catalogs),
        candidate_universe_exhausted=True,
        candidate_universe_pruned=False,
        state_spaces=spaces,
        required_confirmation_dwell_ids=required,
        minimum_distinct_session_count=minimum_sessions,
        shared_identity_cost=shared_identity_cost,
    )
    result = decode_cross_dwell_shared_norad(problem)
    disposition, qualification_rows, qualification_reasons = _qualification_for_selected(
        result=result,
        dwells=dwells,
        minimum_association_improvement_cost=minimum_association_improvement_cost,
    )
    association_claimed = disposition == "association"
    claim = (
        None
        if not association_claimed
        else {
            "kind": result.claim_kind,
            "scope": "association_not_tracking",
            "catalog_number": result.selected_catalog_number,
            "support_session_ids": list(result.support_session_ids),
            "exact_over_declared_finite_union": result.exact,
        }
    )
    document: dict[str, Any] = {
        "schema": OUTPUT_SCHEMA,
        "algorithm": ALGORITHM,
        "research_only": True,
        "candidate_only": True,
        "association_id": association_id,
        "association_not_tracking": True,
        "association_claimed": association_claimed,
        "tracking_claimed": False,
        "orbit_state_estimated": False,
        "payload_decoded": False,
        "disposition": disposition,
        "claim": claim,
        "request": {
            "path": str(resolved_request_path),
            "file_digest": request_digest,
            "content_digest": canonical_digest(request),
        },
        "candidate_universe": {
            "path": str(universe_reference.path),
            "file_digest": universe_reference.file_digest,
            "content_digest": canonical_digest(universe),
            "catalog_numbers": list(catalogs),
            "catalog_count": len(catalogs),
            "exhausted": True,
            "pruned": False,
            "external_preregistration_verified": False,
        },
        "dwell_provenance": [
            {
                "dwell_id": item.dwell_id,
                "session_id": item.session_id,
                "recording_manifest_digest": item.recording_manifest_digest,
                "window_start_utc_ns": item.window_start_utc_ns,
                "window_end_utc_ns": item.window_end_utc_ns,
                "source_artifact": {
                    "path": str(item.source_path),
                    "file_digest": item.source_file_digest,
                    "content_digest": item.source_content_digest,
                    "schema": SOURCE_SCHEMA,
                    "algorithm": SOURCE_ALGORITHM,
                },
                "identity_geometry_partition": {
                    "content_digest": item.identity_partition_content_digest,
                    "named_catalog_count": len(item.named_catalog_numbers),
                    "eligible_catalog_count": len(item.minima),
                    "named_ineligible_catalog_count": len(item.named_ineligible_catalog_numbers),
                    "exhausted": True,
                    "pruned": False,
                },
                "nested_file_digests": {
                    "duration_dataset": item.dataset_file_digest,
                    "pilot_scan": item.pilot_scan_file_digest,
                    "score_calibration": item.calibration_file_digest,
                    "tle": item.tle_file_digest,
                },
                "qualification_receipt": {
                    "path": str(item.qualification_path),
                    "file_digest": item.qualification_file_digest,
                    "content_digest": item.qualification_content_digest,
                },
                "tle_authority": {
                    "authority": item.tle_authority,
                    "authority_snapshot_id": item.tle_authority_snapshot_id,
                    "snapshot_acquired_utc_ns": item.tle_snapshot_acquired_utc_ns,
                },
                "control_artifacts": [asdict(control) for control in item.controls],
                "source_generated_state_count": item.source_generated_state_count,
            }
            for item in dwells
        ],
        "finite_state_matrix": {
            "algorithm": MATRIX_ALGORITHM,
            "row_count": len(matrix_rows),
            "expected_row_count": len(dwells) * len(catalogs),
            "every_dwell_catalog_pair_present": len(matrix_rows) == len(dwells) * len(catalogs),
            "exact_minimum_compression_applied": True,
            "compression_semantics": (
                "one exact source minimum represents every exhausted generated nuisance state; "
                "absence from an exhausted full-window-visible set is certified ineligibility"
            ),
            "unknown_rows": [],
            "rows": matrix_rows,
        },
        "reducer_problem": {
            "required_confirmation_dwell_ids": list(required),
            "minimum_distinct_session_count": minimum_sessions,
            "shared_identity_cost": shared_identity_cost,
            "minimum_association_improvement_cost": minimum_association_improvement_cost,
            "candidate_universe_catalog_count": len(catalogs),
            "candidate_universe_exhausted": True,
            "candidate_universe_pruned": False,
        },
        "reducer_result": asdict(result),
        "selected_contribution_qualification": {
            "all_selected_contributions_passed": association_claimed
            or result.selected_catalog_number is None,
            "rows": qualification_rows,
            "reasons": qualification_reasons,
        },
        "caveats": [
            (
                "the exactness scope is the frozen union of per-dwell full-window-visible "
                "catalogues, declared delay grids, data-proposed CFO modes, and retained "
                "raw inventories"
            ),
            (
                "catalogue minima are sufficient statistics for this additive shared-NORAD "
                "reducer; source generated-state counts remain explicit"
            ),
            ("pre-acquisition candidate caps and continuous delay/CFO spaces are not exhausted"),
            (
                "TLE authority assertions are timestamp- and digest-bound but are not "
                "cryptographically authenticated by this adapter"
            ),
            (
                "a passed prediction-time control is required for every selected "
                "dwell/catalogue contribution"
            ),
            (
                "same-NORAD association is not orbit estimation, continuous tracking, payload "
                "decoding, or spacecraft identity proof"
            ),
        ],
    }
    document["payload_content_digest"] = canonical_digest(document)
    return document


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    associate = commands.add_parser("associate", help="validate and reduce one frozen request")
    associate.add_argument("--request", type=Path, required=True)
    associate.add_argument("--request-sha256", required=True)
    associate.add_argument("--output", type=Path, required=True)
    freeze = commands.add_parser("freeze", help="freeze a union and zero-control request")
    freeze.add_argument("--spec", type=Path, required=True)
    freeze.add_argument("--spec-sha256", required=True)
    freeze.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    if arguments.command == "freeze":
        result = freeze_cross_dwell_request(
            spec_path=arguments.spec,
            expected_spec_digest=arguments.spec_sha256,
            output_directory=arguments.output_directory,
        )
        sys.stdout.write(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
        return
    document = associate_cross_dwell_shared_norad(
        request_path=arguments.request,
        expected_request_digest=arguments.request_sha256,
    )
    _refuse_protected_write(arguments.output)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    _write_new_document(arguments.output, document)


if __name__ == "__main__":
    main()
