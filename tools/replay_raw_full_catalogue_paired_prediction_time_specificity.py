#!/usr/bin/env python3
"""Run an atomic full-catalogue prediction-time randomization family.

This research-only producer consumes one bounded-null-vs-any V2 artifact for
one explicitly bound receiver path.  It loads that artifact's raw decision
problem once, freezes the identity arm and exactly twenty non-affine block
permutations before any arm is scored, and independently repeats the complete
named-catalogue, discrete-delay, data-proposed-CFO search in every arm.  Every
control therefore selects its own best NORAD instead of inheriting an identity
chosen from the evidence.

The result is a conditional single-path prediction-time-specificity test.  Its
block controls are not signal-absence controls, do not estimate a presence
false-positive rate, and cannot by themselves identify or track a spacecraft.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np

from leo.analysis.research.activity_block_permutation import (  # type: ignore[import-untyped]
    build_activity_block_permutation,
)
from leo.analysis.research.satellite_activity import (  # type: ignore[import-untyped]
    PredictedProbeCfo,
    SingleSatelliteHypothesis,
    decode_single_satellite,
)
from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools import decide_raw_catalogue_null_vs_any as bounded  # noqa: E402
from tools import replay_raw_grouped_satellite_activity as raw_replay  # noqa: E402
from tools import (  # noqa: E402
    replay_raw_multipath_paired_prediction_time_specificity as paired,
)
from tools import replay_raw_multipath_satellite_activity as multipath  # noqa: E402
from tools import (  # noqa: E402
    replay_raw_single_path_fixed_norad_paired_prediction_time_specificity as fixed,
)
from tools import screen_raw_satellite_activity_catalog as screen  # noqa: E402

OUTPUT_SCHEMA = "org.leo.research.raw-full-catalogue-paired-prediction-time-specificity/v1"
ALGORITHM = "atomic-full-catalogue-exhaustive-single-path-prediction-time-specificity-v1"
FAMILY_PLAN_SCHEMA = "org.leo.research.raw-full-catalogue-prediction-time-family-plan/v1"
SOURCE_SCHEMA = bounded.OUTPUT_SCHEMA_V2
SOURCE_ALGORITHM = bounded.ALGORITHM_V2
PROSPECTIVE_PLAN_SCHEMA = "org.leo.research.prospective-starlink-tracking-plan/v1"
PROSPECTIVE_PLAN_ALGORITHM = "pre-evidence-full-catalogue-randomization-tracking-state-machine-v1"
STATE_DIGEST_ALGORITHM = "canonical-complete-generated-single-satellite-state-bank-v1"
PATH_SCOPE_ALGORITHM = "exact-predeclared-capture-metadata-primary-path-v1"
REQUIRED_CONTROL_INDICES = tuple(range(20))
OUTPUT_CAVEATS = (
    "this artifact covers one predeclared receiver path, not a capture-wide or multipath search",
    "another receiver path cannot be selected post hoc or counted as independent confirmation",
    (
        "block permutations test conditional prediction-time specificity, not presence "
        "false-positive rate"
    ),
    ("the finite exact search is conditional on named/full-window-visible geometry eligibility"),
    "the exact delay/CFO bank is discrete and data-proposed, not continuous-nuisance exact",
    "multiple controls from one path and capture are dependent randomization arms",
    "upstream retained-candidate caps may have saturated before this exact decision problem",
    "TLE, calibration, raw scan, source, and current implementation bytes are digest-bound",
    "without a separately verified pre-evidence plan this is a diagnostic only",
    "neither a passing diagnostic nor its best NORAD is a spacecraft identity or a track",
)

NOT_COMPARABLE = "not_comparable"
IDENTITY_NONACTIVATION = "identity_nonactivation"
STRICT_MARGIN_NOT_PASSED = "strict_frozen_margin_not_passed"
PLAN_AUTHORITY_NOT_VERIFIED = "prospective_plan_authority_not_verified"
CONDITIONAL_GATE_PASS = "conditional_full_catalogue_specificity_gate_pass"

_IMPLEMENTATION_FILE_PATHS = (
    "tools/replay_raw_full_catalogue_paired_prediction_time_specificity.py",
    "tools/freeze_prospective_starlink_tracking_plan.py",
    "tools/replay_raw_single_path_fixed_norad_paired_prediction_time_specificity.py",
    "tools/replay_raw_multipath_paired_prediction_time_specificity.py",
    "tools/decide_raw_catalogue_null_vs_any.py",
    "tools/screen_raw_satellite_activity_catalog.py",
    "tools/raw_satellite_activity_search_configuration.py",
    "tools/replay_raw_grouped_satellite_activity.py",
    "tools/replay_raw_multipath_satellite_activity.py",
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
class _MemberEvaluation:
    score: screen.CatalogScore
    best_decoded: Any
    state_bank_digest: str


@dataclass(frozen=True, slots=True)
class _MappedCatalogueBank:
    """A monotone-propagated bank whose curves are restored to RF-probe order."""

    base: screen.CataloguePredictionBank
    sorted_source_indices: tuple[int, ...]

    @property
    def catalogue(self) -> Any:
        return self.base.catalogue

    @property
    def catalogue_indices(self) -> tuple[int, ...]:
        return self.base.catalogue_indices

    @property
    def accounting(self) -> screen.CatalogueGeometryAccounting:
        return self.base.accounting

    def _restore(self, values: Any) -> np.ndarray:
        ordered = np.asarray(values, dtype=np.float64)
        if ordered.shape != (len(self.sorted_source_indices),):
            raise RuntimeError("catalogue bank returned an invalid mapped-probe shape")
        restored = np.empty(len(self.sorted_source_indices), dtype=np.float64)
        restored[np.asarray(self.sorted_source_indices, dtype=np.intp)] = ordered
        return restored

    def curve(self, row_index: int, delay_s: float) -> np.ndarray:
        return self._restore(self.base.curve(row_index, delay_s))

    def elevation(self, row_index: int, delay_s: float) -> np.ndarray:
        return self._restore(self.base.elevation(row_index, delay_s))


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def producer_implementation_manifest() -> dict[str, Any]:
    return {
        "algorithm": ALGORITHM,
        "implementation_file_digests": {
            relative: _file_digest(REPOSITORY_ROOT / relative)
            for relative in _IMPLEMENTATION_FILE_PATHS
        },
        "runtime_versions": multipath._runtime_versions(),
    }


def _object(value: object, label: str) -> dict[str, Any]:
    return fixed._object(value, label)


def _list(value: object, label: str) -> list[Any]:
    return fixed._list(value, label)


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    return fixed._integer(value, label, minimum=minimum)


def _finite(value: object, label: str) -> float:
    return fixed._finite(value, label)


def _finite_nonnegative(value: object, label: str) -> float:
    return fixed._finite_nonnegative(value, label)


def _canonical_sha256(value: object, label: str) -> str:
    return fixed._canonical_sha256(value, label)


def _source_ranking(source: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    search = _object(source.get("catalogue_search"), "source catalogue search")
    fine = _object(search.get("fine_stage"), "source catalogue fine stage")
    ranking = tuple(
        _object(item, "source catalogue row")
        for item in _list(fine.get("ranking"), "source catalogue ranking")
    )
    if not ranking:
        raise ValueError("full-catalogue controls require at least one eligible named object")
    return ranking


def _load_source(*, source_path: Path, expected_source_digest: str) -> fixed._LoadedSource:
    """Load one source once, using one row only to invoke the strict V2 loader."""

    resolved = source_path.resolve()
    digest = _canonical_sha256(expected_source_digest, "source artifact digest")
    if _file_digest(resolved) != digest:
        raise ValueError("bounded V2 source artifact digest mismatch")
    source_document = fixed._read_json(resolved)
    ranking = _source_ranking(source_document)
    bootstrap_catalog = _integer(
        ranking[0].get("catalog_number"), "source bootstrap catalogue", minimum=1
    )
    loaded = fixed._load_source(
        source_path=resolved,
        expected_source_digest=digest,
        target_catalog_number=bootstrap_catalog,
    )
    if canonical_digest(loaded.source) != canonical_digest(source_document):
        raise RuntimeError("source bytes changed during the single atomic load")
    return loaded


def _source_catalogue_parameters(source: fixed._LoadedSource) -> tuple[str, float]:
    search = _object(source.source.get("search_configuration"), "source search configuration")
    catalogue = _object(search.get("catalogue_screen"), "source catalogue configuration")
    name_prefix = catalogue.get("name_prefix")
    if not isinstance(name_prefix, str) or not name_prefix.strip():
        raise ValueError("source catalogue name prefix must be nonempty")
    spacing = _finite(catalogue.get("geometry_spacing_s"), "source geometry spacing")
    if spacing <= 0.0:
        raise ValueError("source geometry spacing must be positive")
    return name_prefix, spacing


def _single_path_scope(source: fixed._LoadedSource) -> dict[str, Any]:
    capture = _object(source.dataset.get("capture"), "duration capture")
    frequency = _object(source.dataset.get("frequency_binding"), "frequency binding")
    stream_id = capture.get("stream_id")
    radio_id = capture.get("radio_id")
    radio_serial = capture.get("radio_serial")
    tuning_tag = frequency.get("tuning_tag")
    if any(
        not isinstance(value, str) or not value
        for value in (stream_id, radio_id, radio_serial, tuning_tag)
    ):
        raise ValueError("duration input has an incomplete explicit receiver-path identity")
    receiver_id = _integer(capture.get("receiver_id"), "receiver ID")
    sky_frequency_hz = _finite(frequency.get("sky_frequency_hz"), "sky frequency")
    if sky_frequency_hz <= 0.0:
        raise ValueError("sky frequency must be positive")
    identity_tuple = [
        stream_id,
        radio_id,
        radio_serial,
        receiver_id,
        tuning_tag,
        sky_frequency_hz,
    ]
    path_id = canonical_digest(identity_tuple)
    predeclared_payload = {
        "algorithm": PATH_SCOPE_ALGORITHM,
        "path_id": path_id,
        "stream_id": stream_id,
        "radio_id": radio_id,
        "radio_serial": radio_serial,
        "receiver_id": receiver_id,
        "tuning_tag": tuning_tag,
        "sky_frequency_hz": sky_frequency_hz,
    }
    evidence_payload = {
        **predeclared_payload,
        "duration_dataset_digest": source.dataset_digest,
    }
    return {
        **evidence_payload,
        "path_scope_digest": canonical_digest(predeclared_payload),
        "evidence_path_scope_digest": canonical_digest(evidence_payload),
    }


def _validate_path_scope_document(value: object) -> dict[str, Any]:
    scope = _object(value, "single receiver-path scope")
    required = {
        "algorithm",
        "stream_id",
        "radio_id",
        "radio_serial",
        "receiver_id",
        "tuning_tag",
        "sky_frequency_hz",
        "duration_dataset_digest",
        "path_id",
        "path_scope_digest",
        "evidence_path_scope_digest",
    }
    if set(scope) != required or scope.get("algorithm") != PATH_SCOPE_ALGORITHM:
        raise ValueError("single receiver-path scope has missing, extra, or invalid fields")
    for field in ("stream_id", "radio_id", "radio_serial", "tuning_tag"):
        value = scope.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"single receiver-path {field} must be nonempty")
    receiver_id = _integer(scope.get("receiver_id"), "receiver ID")
    sky_frequency_hz = _finite(scope.get("sky_frequency_hz"), "sky frequency")
    dataset_digest = _canonical_sha256(
        scope.get("duration_dataset_digest"), "duration dataset digest"
    )
    identity_tuple = [
        scope["stream_id"],
        scope["radio_id"],
        scope["radio_serial"],
        receiver_id,
        scope["tuning_tag"],
        sky_frequency_hz,
    ]
    if scope.get("path_id") != canonical_digest(identity_tuple):
        raise ValueError("single receiver-path ID does not bind its complete identity tuple")
    predeclared_payload = {
        key: scope[key]
        for key in (
            "algorithm",
            "path_id",
            "stream_id",
            "radio_id",
            "radio_serial",
            "receiver_id",
            "tuning_tag",
            "sky_frequency_hz",
        )
    }
    if scope.get("path_scope_digest") != canonical_digest(predeclared_payload):
        raise ValueError("predeclared receiver-path scope digest does not recompute")
    evidence_payload = {**predeclared_payload, "duration_dataset_digest": dataset_digest}
    if _canonical_sha256(
        scope.get("evidence_path_scope_digest"), "evidence receiver-path scope digest"
    ) != canonical_digest(evidence_payload):
        raise ValueError("evidence receiver-path scope digest does not recompute")
    return scope


def _build_mapped_catalogue_bank(
    *,
    source: fixed._LoadedSource,
    scheduled_times: tuple[float, ...],
    prediction_utc_ns: tuple[int, ...],
    name_prefix: str,
    geometry_spacing_s: float,
) -> _MappedCatalogueBank:
    if len(scheduled_times) != len(prediction_utc_ns) or not scheduled_times:
        raise ValueError("mapped prediction time/UTC inventories differ or are empty")
    order = tuple(sorted(range(len(prediction_utc_ns)), key=prediction_utc_ns.__getitem__))
    ordered_utc = tuple(prediction_utc_ns[index] for index in order)
    if any(right <= left for left, right in pairwise(ordered_utc)):
        raise ValueError("mapped prediction UTC epochs must be unique and strictly sortable")
    ordered_times = tuple(scheduled_times[index] for index in order)
    timing = _object(source.dataset.get("timing_binding"), "duration timing")
    base = screen.build_catalogue_prediction_bank(
        catalogue=source.catalogue,
        scheduled_times_s=ordered_times,
        first_sample_utc_ns=_integer(
            timing.get("first_estimate_utc_ns"), "duration first-estimate UTC"
        ),
        delay_grid=source.config.delay_grid,
        sky_frequency_hz=float(source.dataset["frequency_binding"]["sky_frequency_hz"]),
        observer=source.observer,
        horizon_mask_deg=source.config.horizon_mask_deg,
        name_prefix=name_prefix,
        geometry_spacing_s=geometry_spacing_s,
    )
    return _MappedCatalogueBank(base=base, sorted_source_indices=order)


def _freeze_arm_transforms(
    *,
    problem: Any,
    selection_context_digest: str,
    control_indices: tuple[int, ...],
    maximum_delay_support_s: float,
) -> tuple[paired._ArmTransform, ...]:
    """Freeze a larger family than the legacy sixteen-control diagnostic."""

    if control_indices != REQUIRED_CONTROL_INDICES:
        raise ValueError("full-catalogue replay requires exactly control indices 0 through 19")
    ordered = REQUIRED_CONTROL_INDICES
    identity_payload = {
        "algorithm_version": "identity-prediction-epoch-map-v1",
        "prediction_cell_by_observation_cell": list(range(problem.grid.cell_count)),
        "observation_inventory_modified": False,
        "tle_prediction_epochs_modified": False,
    }
    identity_digest = canonical_digest(identity_payload)
    transforms = [
        paired._ArmTransform(
            arm_id="identity",
            role="identity",
            transform_digest=identity_digest,
            plan=None,
            receipt={**identity_payload, "transform_digest": identity_digest},
        )
    ]
    seen_mappings: set[tuple[int, ...]] = set()
    seen_digests = {identity_digest}
    for control_index in ordered:
        plan = build_activity_block_permutation(
            problem.grid,
            session_key=selection_context_digest,
            control_index=control_index,
            maximum_delay_support_s=maximum_delay_support_s,
        )
        mapping = tuple(plan.prediction_block_by_observation_block)
        if mapping in seen_mappings or plan.plan_digest in seen_digests:
            raise RuntimeError("declared controls produced a mapping or digest collision")
        if plan.diagnostics.mapping_is_affine:
            raise RuntimeError("declared control unexpectedly produced an affine mapping")
        seen_mappings.add(mapping)
        seen_digests.add(plan.plan_digest)
        transforms.append(
            paired._ArmTransform(
                arm_id=f"control-{control_index:06d}",
                role="block_permutation_control",
                transform_digest=plan.plan_digest,
                plan=plan,
                receipt=paired._permutation_receipt(plan),
            )
        )
    return tuple(transforms)


def _require_prospective_execution_readiness(plan: dict[str, Any]) -> None:
    readiness = _object(plan.get("execution_readiness"), "prospective execution readiness")
    required_readiness = (
        "paired_producer_implementation_digest_slot_filled",
        "presence_null_qualification_receipt_present",
        "positive_sensitivity_qualification_receipt_present",
        "decision_threshold_calibration_receipt_present",
        "external_authority_authentication_present",
        "ready_to_consume_future_evidence",
    )
    if any(readiness.get(field) is not True for field in required_readiness):
        raise ValueError(
            "prospective plan is not ready to consume or assign a fixed future cohort ordinal"
        )


def _validate_prospective_plan_binding(
    *,
    source: fixed._LoadedSource,
    plan_path: Path,
    expected_plan_digest: str,
    cohort_ordinal: int,
    minimum_advantage_cost: float,
    validated_plan: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    """Bind a validated pre-evidence plan to this one future single-path source."""

    from tools import freeze_prospective_starlink_tracking_plan as prospective

    resolved = plan_path.resolve(strict=True)
    plan_file_digest = _canonical_sha256(expected_plan_digest, "prospective plan file digest")
    if _file_digest(resolved) != plan_file_digest:
        raise ValueError("prospective plan file changed after readiness validation")
    plan = (
        prospective.load_and_validate_prospective_plan(
            plan_path=resolved,
            expected_plan_file_digest=plan_file_digest,
        )
        if validated_plan is None
        else validated_plan
    )
    if (
        plan.get("schema") != PROSPECTIVE_PLAN_SCHEMA
        or plan.get("algorithm") != PROSPECTIVE_PLAN_ALGORITHM
    ):
        raise ValueError("prospective plan schema or algorithm is unsupported")
    _require_prospective_execution_readiness(plan)
    execution = _object(plan.get("execution"), "prospective plan execution")
    paired_producer = _object(
        execution.get("paired_full_catalogue_producer"), "prospective paired producer"
    )
    current_manifest = producer_implementation_manifest()
    if (
        paired_producer.get("output_schema") != OUTPUT_SCHEMA
        or paired_producer.get("algorithm") != ALGORITHM
        or paired_producer.get("implementation_path")
        != "tools/replay_raw_full_catalogue_paired_prediction_time_specificity.py"
        or paired_producer.get("implementation_binding_status") != "pre-evidence-bound"
        or paired_producer.get("implementation_manifest") != current_manifest
        or paired_producer.get("implementation_manifest_digest")
        != canonical_digest(current_manifest)
        or paired_producer.get("implementation_manifest_digest_verified_current") is not True
    ):
        raise ValueError("prospective plan does not pre-evidence-bind the current producer")
    pre_evidence = _object(plan.get("pre_evidence_inputs"), "prospective pre-evidence inputs")
    tle = _object(pre_evidence.get("tle"), "prospective TLE binding")
    calibration = _object(pre_evidence.get("score_calibration"), "prospective calibration binding")
    if (
        Path(str(tle.get("path", ""))).resolve() != source.tle_path.resolve()
        or tle.get("file_digest") != source.tle_digest
        or Path(str(calibration.get("path", ""))).resolve() != source.calibration_path.resolve()
        or calibration.get("file_digest") != source.calibration_digest
        or calibration.get("content_digest") != canonical_digest(source.calibration_document)
    ):
        raise ValueError("future source TLE or calibration differs from the prospective plan")
    if execution.get("raw_replay_configuration") != asdict(source.config):
        raise ValueError("future source raw replay configuration differs from the plan")
    if execution.get("observer") != source.observer.model_dump(mode="json"):
        raise ValueError("future source observer differs from the plan")
    if execution.get("pilot_scan_configuration") != screen._pilot_scan_configuration(
        source.inventory.scan_path
    ):
        raise ValueError("future source PilotScan configuration differs from the plan")
    window = _object(
        execution.get("future_dwell_window_policy"), "prospective future-window policy"
    )
    if (
        source.start_s != _finite(window.get("start_offset_s"), "plan window start")
        or source.end_s - source.start_s
        != _finite(window.get("duration_s"), "plan window duration")
        or len(source.window.rows)
        != _integer(window.get("scheduled_probe_count"), "plan scheduled probes", minimum=2)
        or source.inventory.problem.grid.cell_count
        != _integer(window.get("cell_count"), "plan activity cells", minimum=1)
    ):
        raise ValueError("future source window differs from the prospective plan")
    path_scope = _single_path_scope(source)
    primary = _object(window.get("primary_path"), "prospective primary receiver path")
    for field in (
        "algorithm",
        "path_id",
        "stream_id",
        "radio_id",
        "radio_serial",
        "receiver_id",
        "tuning_tag",
        "sky_frequency_hz",
        "path_scope_digest",
    ):
        if primary.get(field) != path_scope[field]:
            raise ValueError("future source receiver path differs from the prospective plan")
    if (
        window.get("required_tuning_tag") != path_scope["tuning_tag"]
        or window.get("required_sky_frequency_hz") != path_scope["sky_frequency_hz"]
    ):
        raise ValueError("future source frequency identity differs from the plan window")
    full_search = _object(
        execution.get("full_catalogue_search"), "prospective full-catalogue search"
    )
    name_prefix, geometry_spacing_s = _source_catalogue_parameters(source)
    bounded_manifest = bounded.producer_implementation_manifest()
    if (
        full_search.get("output_schema") != SOURCE_SCHEMA
        or full_search.get("algorithm") != SOURCE_ALGORITHM
        or full_search.get("catalogue_name_prefix") != name_prefix
        or full_search.get("geometry_spacing_s") != geometry_spacing_s
        or full_search.get("producer_implementation_manifest") != bounded_manifest
        or full_search.get("producer_implementation_manifest_digest")
        != canonical_digest(bounded_manifest)
    ):
        raise ValueError("future full-catalogue search differs from the prospective plan")
    thresholds = _object(
        _object(plan.get("qualification_gates"), "prospective gates").get("decision_thresholds"),
        "prospective decision thresholds",
    )
    values = _object(thresholds.get("validated_values"), "prospective threshold values")
    gamma_dwell = _finite_nonnegative(
        values.get("gamma_dwell_control_margin_cost"), "prospective gamma dwell"
    )
    if minimum_advantage_cost != gamma_dwell:
        raise ValueError("requested dwell-control margin differs from the prospective plan")
    randomization = _object(
        execution.get("prediction_time_randomization"), "prospective prediction-time controls"
    )
    if (
        tuple(randomization.get("control_indices", ())) != REQUIRED_CONTROL_INDICES
        or randomization.get("randomization_exchangeability_verified") is not False
        or randomization.get("permutation_p_value") is not None
    ):
        raise ValueError("prospective control family identity or inferential status differs")
    seed_digest = _canonical_sha256(
        randomization.get("selection_context_digest"), "prospective control seed digest"
    )
    regenerated = _freeze_arm_transforms(
        problem=SimpleNamespace(grid=source.inventory.problem.grid),
        selection_context_digest=seed_digest,
        control_indices=REQUIRED_CONTROL_INDICES,
        maximum_delay_support_s=max(abs(source.config.delay_min_s), abs(source.config.delay_max_s)),
    )
    plan_controls = _list(randomization.get("control_arms"), "prospective control arms")
    for control, transform in zip(plan_controls, regenerated[1:], strict=True):
        raw = _object(control, "prospective control arm")
        serialized_transform = _object(raw.get("transform"), "prospective control transform")
        if (
            raw.get("arm_id") != transform.arm_id
            or raw.get("transform_digest") != transform.transform_digest
            or canonical_digest(serialized_transform)
            != canonical_digest(asdict(cast(Any, transform.plan)))
        ):
            raise ValueError("prospective control receipt differs from regenerated transform")
    not_before = _integer(
        plan.get("future_evidence_not_before_utc_ns"), "future evidence not-before UTC"
    )
    if source.window_start_utc_ns < not_before:
        raise ValueError("future source window begins before the prospective not-before UTC")
    authority = _object(
        plan.get("authority_and_chronology"), "prospective authority and chronology"
    )
    tle_receipt = _object(
        _object(authority.get("tle_authority_receipt"), "TLE authority receipt binding").get(
            "receipt"
        ),
        "TLE authority receipt",
    )
    acquired_utc_ns = _integer(tle_receipt.get("snapshot_acquired_utc_ns"), "TLE acquisition UTC")
    maximum_age_s = _finite_nonnegative(
        tle.get("maximum_snapshot_age_at_dwell_s"), "maximum TLE age"
    )
    if (source.window_start_utc_ns - acquired_utc_ns) / 1e9 > maximum_age_s:
        raise ValueError("future source TLE exceeds the prospective maximum age")
    cohort = _object(execution.get("prospective_cohort_policy"), "prospective cohort policy")
    if isinstance(cohort_ordinal, bool) or cohort_ordinal not in (1, 2):
        raise ValueError("full-catalogue producer accepts only discovery cohort ordinals 1 or 2")
    roles = _list(cohort.get("ordinal_roles"), "prospective cohort ordinal roles")
    matching_roles = [
        _object(item, "cohort ordinal role")
        for item in roles
        if _object(item, "cohort ordinal role").get("ordinal") == cohort_ordinal
    ]
    if (
        len(matching_roles) != 1
        or matching_roles[0].get("role") != "full-catalogue-association-selection"
    ):
        raise ValueError("requested cohort ordinal is not a full-catalogue discovery dwell")
    binding = {
        "schema": PROSPECTIVE_PLAN_SCHEMA,
        "algorithm": PROSPECTIVE_PLAN_ALGORITHM,
        "plan_id": plan.get("plan_id"),
        "plan_path": str(resolved),
        "plan_file_digest": plan_file_digest,
        "plan_content_digest": plan.get("plan_content_digest"),
        "proposal_digest": plan.get("proposal_digest"),
        "future_evidence_not_before_utc_ns": not_before,
        "evidence_window_start_utc_ns": source.window_start_utc_ns,
        "evidence_after_not_before_verified": True,
        "cohort_ordinal": cohort_ordinal,
        "cohort_role": "full-catalogue-association-selection",
        "cohort_chronological_membership_asserted_by_caller": True,
        "cohort_predecessor_order_independently_verified": False,
        "path_id": path_scope["path_id"],
        "path_scope_digest": path_scope["path_scope_digest"],
        "duration_dataset_digest": path_scope["duration_dataset_digest"],
        "producer_implementation_manifest_digest": canonical_digest(current_manifest),
        "bounded_producer_implementation_manifest_digest": canonical_digest(bounded_manifest),
        "control_selection_context_digest": seed_digest,
        "control_transform_digests": [item.transform_digest for item in regenerated[1:]],
        "decision_thresholds": dict(values),
        "plan_structural_and_source_binding_verified": True,
        "external_authority_authentication_performed": authority.get(
            "external_authority_authentication_performed"
        ),
        "external_preregistration_verified": authority.get("external_preregistration_verified"),
        "association_authority_enabled": False,
        "tracking_authority_enabled": False,
    }
    return binding, seed_digest


def _source_binding_document(
    source: fixed._LoadedSource, *, path_scope: dict[str, Any]
) -> dict[str, Any]:
    source_partition = _object(
        source.source.get("catalogue_identity_partition"), "source identity partition"
    )
    return {
        "schema": SOURCE_SCHEMA,
        "algorithm": SOURCE_ALGORITHM,
        "source_artifact_path": str(source.source_path),
        "source_artifact_file_digest": source.source_digest,
        "source_artifact_content_digest": canonical_digest(source.source),
        "source_producer_implementation": bounded.producer_implementation_manifest(),
        "duration_dataset_path": str(source.dataset_path),
        "duration_dataset_file_digest": source.dataset_digest,
        "duration_dataset_content_digest": canonical_digest(source.dataset),
        "pilot_scan_path": str(source.inventory.scan_path.resolve()),
        "pilot_scan_file_digest": source.inventory.scan_digest,
        "pilot_scan_content_digest": canonical_digest(fixed._read_json(source.inventory.scan_path)),
        "score_calibration_path": str(source.calibration_path),
        "score_calibration_file_digest": source.calibration_digest,
        "score_calibration_content_digest": canonical_digest(source.calibration_document),
        "tle_path": str(source.tle_path),
        "tle_file_digest": source.tle_digest,
        "session_id": source.dataset["capture"]["session_id"],
        "recording_manifest_digest": source.dataset["capture"]["recording_manifest_digest"],
        "path_id": path_scope["path_id"],
        "path_scope": path_scope,
        "single_receiver_path_only": True,
        "capture_wide_or_multipath_search_performed": False,
        "other_receiver_paths_may_not_be_posthoc_confirmation": True,
        "source_exact_ranking_digest": canonical_digest(list(_source_ranking(source.source))),
        "source_identity_partition_content_digest": source_partition["partition_content_digest"],
        "source_search_configuration_digest": source.source.get("search_configuration_digest"),
        "raw_inventory_receipt": source.source.get("raw_inventory"),
        "timing_approximation_receipt": source.source.get("timing_approximation"),
        "window": {
            "start_s": source.start_s,
            "end_s": source.end_s,
            "start_utc_ns": source.window_start_utc_ns,
            "end_utc_ns": source.window_end_utc_ns,
            "cell_count": source.inventory.problem.grid.cell_count,
        },
    }


def _objective_document(source: fixed._LoadedSource) -> dict[str, Any]:
    return {
        "single_satellite_decoder_algorithm": "exact-single-satellite-semimarkov-v1",
        "association_costs": asdict(source.inventory.problem.costs),
        "score_calibration_schema": source.calibration_document.get("schema"),
        "score_calibration_file_digest": source.calibration_digest,
        "score_calibration_content_digest": canonical_digest(source.calibration_document),
        "constant_elision_is_decision_invariant": True,
        "test_statistic": "max(0, -primitive best catalogue delta_from_null)",
        "structural_costs_calibrated": False,
    }


def _search_universe_document(
    source: fixed._LoadedSource, *, named_catalog_numbers: tuple[int, ...]
) -> dict[str, Any]:
    name_prefix, geometry_spacing_s = _source_catalogue_parameters(source)
    return {
        "mode": "same-complete-named-catalogue-reselected-independently-in-every-arm-v1",
        "single_receiver_path_only": True,
        "capture_wide_or_multipath_search_performed": False,
        "catalogue_name_prefix": name_prefix,
        "geometry_spacing_s": geometry_spacing_s,
        "tle_digest": source.tle_digest,
        "named_catalog_numbers": list(named_catalog_numbers),
        "named_catalog_numbers_digest": canonical_digest(list(named_catalog_numbers)),
        "named_catalogue_count": len(named_catalog_numbers),
        "each_arm_partitions_every_named_identity": True,
        "each_arm_reselects_its_own_best_norad": True,
        "catalogue_shortlist_permitted": False,
        "catalogue_or_state_pruning_permitted": False,
        "configuration": asdict(source.config),
        "delay_grid": list(source.config.delay_grid),
        "modes_per_delay": source.config.modes_per_delay,
        "expected_state_count_per_eligible_catalogue": (
            len(source.config.delay_grid) * source.config.modes_per_delay
        ),
        "observer": source.observer.model_dump(mode="json"),
    }


def _hypothesis_id(
    *,
    catalog_number: int,
    delay_s: float,
    cfo_offset_hz: float,
    transform: paired._ArmTransform,
) -> str:
    if transform.role == "identity":
        # Preserve exact identity-arm compatibility with the bounded V2 source.
        payload = {
            "catalog_number": catalog_number,
            "delay_s": delay_s,
            "cfo_offset_hz": cfo_offset_hz,
            "prediction_epoch": "scheduled_probe_start",
            "catalogue_screen": screen.ALGORITHM,
        }
    else:
        payload = {
            "catalog_number": catalog_number,
            "delay_s": delay_s,
            "cfo_offset_hz": cfo_offset_hz,
            "prediction_epoch_transform_digest": transform.transform_digest,
            "prediction_epoch_role": transform.role,
            "catalogue_control": ALGORITHM,
        }
    return canonical_digest(payload)


def _state_receipt(state: raw_replay._StateEvaluation, decoded: Any) -> dict[str, Any]:
    return {
        "hypothesis": asdict(state.hypothesis),
        "proposal": asdict(state.proposal),
        "minimum_elevation_deg": state.minimum_elevation_deg,
        "maximum_elevation_deg": state.maximum_elevation_deg,
        "decoded": asdict(decoded),
    }


def _evaluate_member(
    *,
    source: fixed._LoadedSource,
    bank: _MappedCatalogueBank,
    row_index: int,
    transform: paired._ArmTransform,
) -> _MemberEvaluation:
    problem = source.inventory.problem
    catalogue_index = bank.catalogue_indices[row_index]
    catalog_number = int(bank.catalogue.satellite_numbers[catalogue_index])
    object_name = str(bank.catalogue.names[catalogue_index])
    generated: list[tuple[raw_replay._StateEvaluation, Any]] = []
    for delay_s in source.config.delay_grid:
        curve = bank.curve(row_index, delay_s)
        elevation = bank.elevation(row_index, delay_s)
        modes = raw_replay._offset_modes(
            raw=source.inventory.observations,
            base_prediction_hz=curve,
            calibration=source.calibration,
            config=source.config,
        )
        if len(modes) != source.config.modes_per_delay:
            raise RuntimeError(
                f"arm {transform.arm_id!r} NORAD {catalog_number} delay {delay_s!r} "
                "did not generate the declared CFO-mode count"
            )
        for mode in modes:
            delay_prior_cost = (
                0.5
                * ((delay_s - source.config.delay_prior_mean_s) / source.config.delay_prior_sigma_s)
                ** 2
            )
            hypothesis = SingleSatelliteHypothesis(
                hypothesis_id=_hypothesis_id(
                    catalog_number=catalog_number,
                    delay_s=delay_s,
                    cfo_offset_hz=mode.cfo_offset_hz,
                    transform=transform,
                ),
                object_name=object_name,
                catalog_number=catalog_number,
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
                minimum_elevation_deg=float(np.min(elevation)),
                maximum_elevation_deg=float(np.max(elevation)),
            )
            if decoded.selected is not (decoded.objective.delta_from_null < 0.0):
                raise RuntimeError("single-satellite selection disagrees with primitive delta")
            generated.append((state, decoded))
    generated.sort(key=lambda item: raw_replay._state_sort_key(item[0]))
    expected = len(source.config.delay_grid) * source.config.modes_per_delay
    if len(generated) != expected:
        raise RuntimeError(f"NORAD {catalog_number} has an incomplete nuisance-state bank")
    receipts = [_state_receipt(state, decoded) for state, decoded in generated]
    hypothesis_ids = [state.hypothesis.hypothesis_id for state, _decoded in generated]
    semantic_states = [
        (
            state.hypothesis.delay_s,
            state.hypothesis.cfo_offset_hz,
            state.hypothesis.hypothesis_id,
        )
        for state, _decoded in generated
    ]
    if len(set(hypothesis_ids)) != expected or len(set(semantic_states)) != expected:
        raise RuntimeError(f"NORAD {catalog_number} generated a nuisance-state collision")
    best_state, best_decoded = generated[0]
    return _MemberEvaluation(
        score=screen.CatalogScore(
            catalog_number=catalog_number,
            object_name=object_name,
            catalogue_index=catalogue_index,
            generated_state_count=len(generated),
            best_state=best_state,
        ),
        best_decoded=best_decoded,
        state_bank_digest=canonical_digest(receipts),
    )


def _partition_binding(
    *, arm_id: str, transform_digest: str, mapping_digest: str, partition_digest: str
) -> str:
    return canonical_digest(
        {
            "arm_id": arm_id,
            "transform_digest": transform_digest,
            "prediction_epoch_mapping_digest": mapping_digest,
            "partition_content_digest": partition_digest,
        }
    )


def _evaluate_arm(
    *,
    source: fixed._LoadedSource,
    transform: paired._ArmTransform,
    common_digests: dict[str, str],
) -> dict[str, Any]:
    problem = source.inventory.problem
    mapped, mapping_receipt = fixed._prediction_mapping(
        transform=transform,
        persisted_probe_utc=source.persisted_probe_utc,
        problem=problem,
    )
    scheduled_times = tuple(mapped[probe.probe_id] for probe in problem.probes)
    if len(set(scheduled_times)) != len(scheduled_times):
        raise ValueError("prediction-time transform collides mapped probe epochs")
    if transform.role == "identity" and scheduled_times != source.scheduled_times_s:
        raise RuntimeError("identity mapping does not reproduce source scheduled epochs")
    mapping_rows = _list(mapping_receipt.get("mapping"), "prediction mapping rows")
    source_epoch_set = sorted(
        _integer(item["source_prediction_utc_ns"], "source prediction UTC")
        for item in source.persisted_probe_utc
    )
    mapped_epoch_set = sorted(
        _integer(_object(item, "prediction mapping row")["prediction_utc_ns"], "mapped UTC")
        for item in mapping_rows
    )
    if mapped_epoch_set != source_epoch_set:
        raise RuntimeError("prediction-time control did not preserve the exact source epoch set")
    name_prefix, geometry_spacing_s = _source_catalogue_parameters(source)
    prediction_utc = tuple(
        _integer(
            _object(item, "prediction mapping row").get("prediction_utc_ns"),
            "mapped prediction UTC",
        )
        for item in mapping_rows
    )
    bank = _build_mapped_catalogue_bank(
        source=source,
        scheduled_times=scheduled_times,
        prediction_utc_ns=prediction_utc,
        name_prefix=name_prefix,
        geometry_spacing_s=geometry_spacing_s,
    )
    partition = bounded._identity_partition_document(
        catalogue=source.catalogue,
        bank=bank,
        catalogue_name_prefix=name_prefix,
        tle_digest=source.tle_digest,
    )
    if not bank.catalogue_indices:
        raise ValueError(f"arm {transform.arm_id!r} has no eligible named catalogue objects")
    members = tuple(
        sorted(
            (
                _evaluate_member(
                    source=source,
                    bank=bank,
                    row_index=row_index,
                    transform=transform,
                )
                for row_index in range(len(bank.catalogue_indices))
            ),
            key=lambda item: screen._catalog_score_key(item.score),
        )
    )
    rows = []
    state_receipts = []
    for rank, member in enumerate(members, start=1):
        summary = bounded._configured_score_summary(
            member.score, rank, satellite_cost=source.config.satellite_cost
        )
        row = {
            **summary,
            "state_bank_digest_algorithm": STATE_DIGEST_ALGORITHM,
            "state_bank_digest": member.state_bank_digest,
            "best_modeled_objective": asdict(member.best_decoded.objective),
        }
        rows.append(row)
        state_receipts.append(
            {
                "catalog_number": member.score.catalog_number,
                "generated_state_count": member.score.generated_state_count,
                "state_bank_digest": member.state_bank_digest,
            }
        )
    expected_per_member = len(source.config.delay_grid) * source.config.modes_per_delay
    expected_total = len(members) * expected_per_member
    generated_total = sum(item.score.generated_state_count for item in members)
    if generated_total != expected_total:
        raise RuntimeError("arm did not exhaust every declared catalogue/nuisance state")
    if len({item.state_bank_digest for item in members}) != len(members):
        raise RuntimeError("arm generated a cross-catalogue state-bank digest collision")
    state_accounting_payload = {
        "state_digest_algorithm": STATE_DIGEST_ALGORITHM,
        "expected_state_count_per_eligible_catalogue": expected_per_member,
        "eligible_catalogue_count": len(members),
        "expected_generated_state_count": expected_total,
        "generated_state_count": generated_total,
        "members": state_receipts,
    }
    winner = members[0]
    winner_row = rows[0]
    primitive_delta = float(winner.score.best_state.single_delta_from_null)
    signed_primitive_improvement = -primitive_delta
    statistic = max(0.0, signed_primitive_improvement)
    selected = primitive_delta < 0.0
    modeled_null = float(winner.best_decoded.objective.null_cost)
    modeled_total = float(winner.best_decoded.objective.total_cost)
    elided = source.inventory.elided_clutter_constant
    partition_digest = str(partition["partition_content_digest"])
    arm = {
        "arm_id": transform.arm_id,
        "role": transform.role,
        "transform_digest": transform.transform_digest,
        "transform": transform.receipt,
        "common_digests": common_digests,
        "prediction_epoch_mapping": mapping_receipt,
        "catalogue_identity_partition": partition,
        "catalogue_identity_partition_binding_digest": _partition_binding(
            arm_id=transform.arm_id,
            transform_digest=transform.transform_digest,
            mapping_digest=str(mapping_receipt["mapping_digest"]),
            partition_digest=partition_digest,
        ),
        "geometry_accounting": asdict(bank.accounting),
        "finite_catalogue_search": {
            "named_catalogue_exhausted": True,
            "eligible_catalogue_rows_exhausted": True,
            "declared_discrete_delay_grid_exhausted": True,
            "generated_data_proposed_cfo_mode_bank_exhausted": True,
            "catalogue_shortlist_applied": False,
            "catalogue_rows_pruned": False,
            "nuisance_states_pruned": False,
            "finite_declared_search_exact": True,
            "delay_grid": list(source.config.delay_grid),
            "modes_per_delay": source.config.modes_per_delay,
            "ranking": rows,
            "ranking_digest": canonical_digest(rows),
            "state_accounting": {
                **state_accounting_payload,
                "content_digest": canonical_digest(state_accounting_payload),
            },
        },
        "decision": {
            "selected_catalog_numbers": [winner.score.catalog_number] if selected else [],
            "selected_satellite_count": int(selected),
            "activation_witness_found": selected,
            "best_catalog_number": winner.score.catalog_number,
            "best_object_name": winner.score.object_name,
            "best_hypothesis_id": winner.score.best_state.hypothesis.hypothesis_id,
            "test_statistic_improvement_from_null": statistic,
            "test_statistic_definition": "max(0, -primitive best catalogue delta_from_null)",
            "signed_primitive_improvement_from_null": signed_primitive_improvement,
            "nonnegative_activation_improvement_from_null": statistic,
            "full_persisted_inventory_objective": {
                "null_cost": modeled_null + elided,
                "total_cost": modeled_total + elided,
                "delta_from_null": primitive_delta,
                "modeled_null_cost": modeled_null,
                "modeled_total_cost": modeled_total,
                "decision_invariant_delta_from_null": primitive_delta,
                "constant_elided_from_exact_decision_problem": elided,
            },
            "winning_catalogue_minimum": winner_row,
        },
    }
    source_partition = _object(
        source.source.get("catalogue_identity_partition"), "source identity partition"
    )
    if partition != source_partition:
        raise RuntimeError(
            "prediction-time arm changed the invariant eligible/ineligible identity partition"
        )
    if transform.role == "identity":
        source_ranking = _source_ranking(source.source)
        compatible_rows = tuple(
            {key: value for key, value in row.items() if key in source_ranking[index]}
            for index, row in enumerate(rows)
        )
        if compatible_rows != source_ranking:
            raise RuntimeError("identity arm does not reproduce every bounded V2 ranking row")
    return arm


def _validate_partition(
    *, arm: dict[str, Any], named_catalog_numbers: tuple[int, ...]
) -> tuple[int, ...]:
    partition = _object(arm.get("catalogue_identity_partition"), "arm identity partition")
    payload = dict(partition)
    observed_digest = _canonical_sha256(
        payload.pop("partition_content_digest", None), "arm partition digest"
    )
    if canonical_digest(payload) != observed_digest:
        raise ValueError("arm identity-partition digest does not recompute")
    if (
        partition.get("schema") != bounded.IDENTITY_PARTITION_SCHEMA
        or partition.get("algorithm") != bounded.IDENTITY_PARTITION_ALGORITHM
        or partition.get("partition_exhausted") is not True
        or partition.get("partition_pruned") is not False
    ):
        raise ValueError("arm identity partition is not an exhaustive declared partition")

    def values(field: str) -> tuple[int, ...]:
        result = tuple(
            _integer(item, f"arm partition {field}", minimum=1)
            for item in _list(partition.get(field), f"arm partition {field}")
        )
        if result != tuple(sorted(set(result))):
            raise ValueError(f"arm partition {field} is not sorted and unique")
        return result

    named = values("named_catalog_numbers")
    eligible = values("eligible_catalog_numbers")
    ineligible = values("named_ineligible_catalog_numbers")
    if named != named_catalog_numbers or set(eligible) & set(ineligible):
        raise ValueError("arm changed the declared named catalogue universe")
    if tuple(sorted((*eligible, *ineligible))) != named:
        raise ValueError("arm eligible/ineligible identities do not partition the named universe")
    for label, rows in (
        ("named", named),
        ("eligible", eligible),
        ("named_ineligible", ineligible),
    ):
        if partition.get(f"{label}_catalog_count") != len(rows):
            raise ValueError("arm identity-partition count is inconsistent")
        if partition.get(f"{label}_catalog_numbers_digest") != canonical_digest(list(rows)):
            raise ValueError("arm identity-partition list digest is inconsistent")
    mapping = _object(arm.get("prediction_epoch_mapping"), "arm prediction mapping")
    expected_binding = _partition_binding(
        arm_id=str(arm.get("arm_id", "")),
        transform_digest=str(arm.get("transform_digest", "")),
        mapping_digest=str(mapping.get("mapping_digest", "")),
        partition_digest=observed_digest,
    )
    if arm.get("catalogue_identity_partition_binding_digest") != expected_binding:
        raise ValueError("arm identity partition is not bound to its prediction-time mapping")
    geometry = _object(arm.get("geometry_accounting"), "arm geometry accounting")
    expected_geometry_fields = set(screen.CatalogueGeometryAccounting.__dataclass_fields__)
    if set(geometry) != expected_geometry_fields:
        raise ValueError("arm geometry accounting has missing or extra fields")
    accounting = screen.CatalogueGeometryAccounting(**geometry)
    if (
        accounting.name_selected_count != len(named)
        or accounting.eligible_catalog_count != len(eligible)
        or accounting.catalogue_object_count != partition.get("catalogue_object_count")
    ):
        raise ValueError("arm geometry accounting differs from its identity partition")
    return eligible


def _validate_raw_problem_receipts(raw_problem: dict[str, Any], *, problem: Any) -> None:
    expected_fields = {
        "decision_problem",
        "persisted_probe_utc",
        "raw_candidate_bundles",
        "source_candidate_count",
        "returned_candidate_count",
        "probe_count_at_retained_candidate_cap",
        "constant_elided_from_exact_decision_problem",
        "pre_acquisition_cap_inventory_complete",
        "physical_signal_inventory_complete",
    }
    if set(raw_problem) != expected_fields:
        raise ValueError("raw-problem receipt inventory is incomplete or extended")
    _list(raw_problem.get("persisted_probe_utc"), "persisted probe UTC")
    _list(raw_problem.get("raw_candidate_bundles"), "raw candidate bundles")
    source_count = _integer(raw_problem.get("source_candidate_count"), "source candidates")
    returned_count = _integer(raw_problem.get("returned_candidate_count"), "returned candidates")
    saturated_probe_count = _integer(
        raw_problem.get("probe_count_at_retained_candidate_cap"), "saturated probes"
    )
    if returned_count > source_count or saturated_probe_count > len(problem.probes):
        raise ValueError("raw-problem candidate or saturation accounting is impossible")
    _finite(
        raw_problem.get("constant_elided_from_exact_decision_problem"),
        "elided objective constant",
    )
    if (
        raw_problem.get("pre_acquisition_cap_inventory_complete") is not False
        or raw_problem.get("physical_signal_inventory_complete") is not False
    ):
        raise ValueError("raw-problem cap or physical-signal completeness claim is invalid")


def _validate_objective_document(
    objective: dict[str, Any], *, problem: Any, source_binding: dict[str, Any]
) -> None:
    expected_fields = {
        "single_satellite_decoder_algorithm",
        "association_costs",
        "score_calibration_schema",
        "score_calibration_file_digest",
        "score_calibration_content_digest",
        "constant_elision_is_decision_invariant",
        "test_statistic",
        "structural_costs_calibrated",
    }
    if set(objective) != expected_fields:
        raise ValueError("objective receipt inventory is incomplete or extended")
    calibration_schema = objective.get("score_calibration_schema")
    if not isinstance(calibration_schema, str) or not calibration_schema:
        raise ValueError("objective omits the score-calibration schema")
    if (
        objective.get("single_satellite_decoder_algorithm")
        != "exact-single-satellite-semimarkov-v1"
        or objective.get("association_costs") != asdict(problem.costs)
        or objective.get("score_calibration_file_digest")
        != source_binding.get("score_calibration_file_digest")
        or objective.get("score_calibration_content_digest")
        != source_binding.get("score_calibration_content_digest")
        or objective.get("constant_elision_is_decision_invariant") is not True
        or objective.get("test_statistic") != "max(0, -primitive best catalogue delta_from_null)"
        or objective.get("structural_costs_calibrated") is not False
    ):
        raise ValueError("objective receipt changes the frozen primitive decision semantics")


def _validate_search_universe_document(
    universe: dict[str, Any],
    *,
    named: tuple[int, ...],
    config: Any,
    source_binding: dict[str, Any],
) -> None:
    expected_fields = {
        "mode",
        "single_receiver_path_only",
        "capture_wide_or_multipath_search_performed",
        "catalogue_name_prefix",
        "geometry_spacing_s",
        "tle_digest",
        "named_catalog_numbers",
        "named_catalog_numbers_digest",
        "named_catalogue_count",
        "each_arm_partitions_every_named_identity",
        "each_arm_reselects_its_own_best_norad",
        "catalogue_shortlist_permitted",
        "catalogue_or_state_pruning_permitted",
        "configuration",
        "delay_grid",
        "modes_per_delay",
        "expected_state_count_per_eligible_catalogue",
        "observer",
    }
    if set(universe) != expected_fields:
        raise ValueError("search-universe receipt inventory is incomplete or extended")
    name_prefix = universe.get("catalogue_name_prefix")
    if not isinstance(name_prefix, str) or not name_prefix:
        raise ValueError("search universe omits its catalogue name prefix")
    geometry_spacing_s = _finite(universe.get("geometry_spacing_s"), "search geometry spacing")
    if geometry_spacing_s <= 0.0:
        raise ValueError("search geometry spacing must be positive")
    if (
        universe.get("mode")
        != "same-complete-named-catalogue-reselected-independently-in-every-arm-v1"
        or universe.get("single_receiver_path_only") is not True
        or universe.get("capture_wide_or_multipath_search_performed") is not False
        or universe.get("tle_digest") != source_binding.get("tle_file_digest")
        or universe.get("named_catalog_numbers") != list(named)
        or universe.get("named_catalog_numbers_digest") != canonical_digest(list(named))
        or universe.get("named_catalogue_count") != len(named)
        or universe.get("each_arm_partitions_every_named_identity") is not True
        or universe.get("each_arm_reselects_its_own_best_norad") is not True
        or universe.get("catalogue_shortlist_permitted") is not False
        or universe.get("catalogue_or_state_pruning_permitted") is not False
        or universe.get("configuration") != asdict(config)
        or universe.get("delay_grid") != list(config.delay_grid)
        or universe.get("modes_per_delay") != config.modes_per_delay
        or universe.get("expected_state_count_per_eligible_catalogue")
        != len(config.delay_grid) * config.modes_per_delay
    ):
        raise ValueError("search universe changes the frozen exhaustive procedure")
    _object(universe.get("observer"), "search observer")


def _validate_source_binding_receipts(
    source_binding: dict[str, Any], *, problem: Any, raw_problem: dict[str, Any]
) -> None:
    expected_fields = {
        "schema",
        "algorithm",
        "source_artifact_path",
        "source_artifact_file_digest",
        "source_artifact_content_digest",
        "source_producer_implementation",
        "duration_dataset_path",
        "duration_dataset_file_digest",
        "duration_dataset_content_digest",
        "pilot_scan_path",
        "pilot_scan_file_digest",
        "pilot_scan_content_digest",
        "score_calibration_path",
        "score_calibration_file_digest",
        "score_calibration_content_digest",
        "tle_path",
        "tle_file_digest",
        "session_id",
        "recording_manifest_digest",
        "path_id",
        "path_scope",
        "single_receiver_path_only",
        "capture_wide_or_multipath_search_performed",
        "other_receiver_paths_may_not_be_posthoc_confirmation",
        "source_exact_ranking_digest",
        "source_identity_partition_content_digest",
        "source_search_configuration_digest",
        "raw_inventory_receipt",
        "timing_approximation_receipt",
        "window",
    }
    if set(source_binding) != expected_fields:
        raise ValueError("source-binding receipt inventory is incomplete or extended")
    if (
        source_binding.get("schema") != SOURCE_SCHEMA
        or source_binding.get("algorithm") != SOURCE_ALGORITHM
        or source_binding.get("source_producer_implementation")
        != bounded.producer_implementation_manifest()
    ):
        raise ValueError("source binding schema, algorithm, or current producer differs")
    if (
        source_binding.get("single_receiver_path_only") is not True
        or source_binding.get("capture_wide_or_multipath_search_performed") is not False
        or source_binding.get("other_receiver_paths_may_not_be_posthoc_confirmation") is not True
    ):
        raise ValueError("source binding changes the frozen single-path scope")
    references = (
        ("source_artifact_path", "source_artifact_file_digest"),
        ("duration_dataset_path", "duration_dataset_file_digest"),
        ("pilot_scan_path", "pilot_scan_file_digest"),
        ("score_calibration_path", "score_calibration_file_digest"),
        ("tle_path", "tle_file_digest"),
    )
    for path_field, digest_field in references:
        path = source_binding.get(path_field)
        if not isinstance(path, str) or not path:
            raise ValueError(f"source binding omits {path_field}")
        _canonical_sha256(source_binding.get(digest_field), digest_field)
    for digest_field in (
        "source_artifact_content_digest",
        "duration_dataset_content_digest",
        "pilot_scan_content_digest",
        "score_calibration_content_digest",
        "source_exact_ranking_digest",
        "source_identity_partition_content_digest",
        "source_search_configuration_digest",
    ):
        _canonical_sha256(source_binding.get(digest_field), digest_field)
    for field in ("session_id", "recording_manifest_digest", "path_id"):
        value = source_binding.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"source binding omits {field}")
    _canonical_sha256(source_binding.get("recording_manifest_digest"), "recording manifest")
    raw_inventory = _object(source_binding.get("raw_inventory_receipt"), "raw inventory receipt")
    expected_inventory_fields = {
        "source_candidate_count",
        "returned_candidate_count",
        "truncated_candidate_count",
        "probe_count_at_retained_candidate_cap",
        "declared_post_acquisition_inventory_complete",
        "pre_acquisition_cap_inventory_complete",
        "exclusion_group_count",
        "positive_candidate_count_after_group_scoring",
        "positive_exclusion_group_count",
        "unsupported_positive_candidate_count",
        "unsupported_positive_exclusion_group_count",
        "modeled_candidate_count",
        "modeled_exclusion_group_count",
        "dominated_weak_candidate_count",
        "dominated_weak_exclusion_group_count",
        "dominated_weak_candidate_elision",
        "physical_exclusion_grouping",
    }
    if set(raw_inventory) != expected_inventory_fields:
        raise ValueError("source raw-inventory receipt is incomplete or extended")
    count_fields = tuple(
        field
        for field in expected_inventory_fields
        if field
        not in {
            "declared_post_acquisition_inventory_complete",
            "pre_acquisition_cap_inventory_complete",
            "dominated_weak_candidate_elision",
            "physical_exclusion_grouping",
        }
    )
    counts = {
        field: _integer(raw_inventory.get(field), f"raw inventory {field}")
        for field in count_fields
    }
    if (
        raw_inventory.get("declared_post_acquisition_inventory_complete") is not True
        or raw_inventory.get("pre_acquisition_cap_inventory_complete") is not False
        or counts["truncated_candidate_count"] != 0
    ):
        raise ValueError("source binding retained raw inventory or cap semantics are invalid")
    if (
        counts["returned_candidate_count"] > counts["source_candidate_count"]
        or counts["probe_count_at_retained_candidate_cap"] > len(problem.probes)
        or counts["modeled_candidate_count"] != len(problem.observations)
        or counts["positive_candidate_count_after_group_scoring"]
        > counts["returned_candidate_count"]
        or counts["unsupported_positive_candidate_count"]
        > counts["positive_candidate_count_after_group_scoring"]
        or counts["modeled_candidate_count"]
        != counts["positive_candidate_count_after_group_scoring"]
        - counts["unsupported_positive_candidate_count"]
        or counts["dominated_weak_candidate_count"]
        != counts["returned_candidate_count"]
        - counts["positive_candidate_count_after_group_scoring"]
        or counts["positive_exclusion_group_count"] > counts["exclusion_group_count"]
        or counts["unsupported_positive_exclusion_group_count"]
        > counts["positive_exclusion_group_count"]
        or counts["modeled_exclusion_group_count"]
        != counts["positive_exclusion_group_count"]
        - counts["unsupported_positive_exclusion_group_count"]
        or counts["dominated_weak_exclusion_group_count"]
        != counts["exclusion_group_count"] - counts["positive_exclusion_group_count"]
        or counts["source_candidate_count"] != raw_problem["source_candidate_count"]
        or counts["returned_candidate_count"] != raw_problem["returned_candidate_count"]
        or counts["probe_count_at_retained_candidate_cap"]
        != raw_problem["probe_count_at_retained_candidate_cap"]
    ):
        raise ValueError("source binding candidate or saturation counts are inconsistent")
    weak_elision = _object(
        raw_inventory.get("dominated_weak_candidate_elision"), "weak elision receipt"
    )
    if set(weak_elision) != {
        "applied",
        "decision_equivalent_under_nonnegative_residual_loss",
        "weak_match_is_dominated_by_miss",
        "unsupported_positive_groups_also_elided",
        "omitted_clutter_objective_constant",
    } or any(
        weak_elision.get(field) is not True
        for field in (
            "applied",
            "decision_equivalent_under_nonnegative_residual_loss",
            "weak_match_is_dominated_by_miss",
            "unsupported_positive_groups_also_elided",
        )
    ):
        raise ValueError("source weak-candidate elision receipt changes exact semantics")
    if _finite(
        weak_elision.get("omitted_clutter_objective_constant"),
        "omitted clutter objective constant",
    ) != _finite(
        raw_problem.get("constant_elided_from_exact_decision_problem"),
        "raw-problem elided objective constant",
    ):
        raise ValueError("source weak-elision and raw-problem constants differ")
    physical_grouping = _object(
        raw_inventory.get("physical_exclusion_grouping"), "physical grouping receipt"
    )
    if set(physical_grouping) != {
        "alias_spacing_hz",
        "exact_duplicate_cfo_tolerance_hz",
        "exact_duplicate_refined_basins_collapsed",
        "resolution_epoch_tolerance_samples",
        "resolution_tracking_cfo_tolerance_hz",
        "unresolved_measurement_cells_collapsed",
        "resolution_cells_are_physical_source_identities",
        "nonidentical_integer_aliases_grouped",
    }:
        raise ValueError("source physical-grouping receipt inventory differs")
    if (
        _finite_nonnegative(physical_grouping.get("alias_spacing_hz"), "physical alias spacing")
        <= 0.0
        or _finite_nonnegative(
            physical_grouping.get("exact_duplicate_cfo_tolerance_hz"),
            "duplicate-CFO tolerance",
        )
        < 0.0
        or _integer(
            physical_grouping.get("resolution_epoch_tolerance_samples"),
            "resolution epoch tolerance",
        )
        < 0
        or _finite_nonnegative(
            physical_grouping.get("resolution_tracking_cfo_tolerance_hz"),
            "resolution tracking tolerance",
        )
        < 0.0
        or physical_grouping.get("exact_duplicate_refined_basins_collapsed") is not True
        or physical_grouping.get("unresolved_measurement_cells_collapsed") is not True
        or physical_grouping.get("resolution_cells_are_physical_source_identities") is not False
        or physical_grouping.get("nonidentical_integer_aliases_grouped") is not False
    ):
        raise ValueError("source physical-grouping receipt changes frozen semantics")
    timing = _object(source_binding.get("timing_approximation_receipt"), "timing receipt")
    if set(timing) != {
        "prediction_epoch",
        "candidate_local_epoch_applied",
        "minimum_candidate_local_epoch_offset_s",
        "maximum_candidate_local_epoch_offset_s",
        "maximum_absolute_candidate_local_epoch_offset_s",
    } or (
        timing.get("prediction_epoch") != "scheduled_probe_start"
        or timing.get("candidate_local_epoch_applied") is not False
    ):
        raise ValueError("source timing-approximation receipt changes frozen semantics")
    minimum_local = timing.get("minimum_candidate_local_epoch_offset_s")
    maximum_local = timing.get("maximum_candidate_local_epoch_offset_s")
    maximum_absolute = _finite_nonnegative(
        timing.get("maximum_absolute_candidate_local_epoch_offset_s"),
        "maximum absolute local epoch",
    )
    if (minimum_local is None) != (maximum_local is None):
        raise ValueError("source timing local-epoch bounds are incomplete")
    if minimum_local is not None and maximum_local is not None:
        minimum_value = _finite(minimum_local, "minimum local epoch")
        maximum_value = _finite(maximum_local, "maximum local epoch")
        if minimum_value > maximum_value or maximum_absolute < max(
            abs(minimum_value), abs(maximum_value)
        ):
            raise ValueError("source timing local-epoch bounds are inconsistent")
    window = _object(source_binding.get("window"), "source binding window")
    if set(window) != {"start_s", "end_s", "start_utc_ns", "end_utc_ns", "cell_count"}:
        raise ValueError("source binding window inventory is incomplete or extended")
    if (
        _finite(window.get("start_s"), "source window start")
        >= _finite(window.get("end_s"), "source window end")
        or _integer(window.get("start_utc_ns"), "source window start UTC")
        >= _integer(window.get("end_utc_ns"), "source window end UTC")
        or window.get("cell_count") != problem.grid.cell_count
    ):
        raise ValueError("source binding window differs from the raw decision problem")


def _validate_arm_search(
    *,
    arm: dict[str, Any],
    eligible: tuple[int, ...],
    expected_states_per_member: int,
    modeled_null_cost: float,
) -> dict[str, Any]:
    search = _object(arm.get("finite_catalogue_search"), "arm finite catalogue search")
    required_true = (
        "named_catalogue_exhausted",
        "eligible_catalogue_rows_exhausted",
        "declared_discrete_delay_grid_exhausted",
        "generated_data_proposed_cfo_mode_bank_exhausted",
        "finite_declared_search_exact",
    )
    required_false = (
        "catalogue_shortlist_applied",
        "catalogue_rows_pruned",
        "nuisance_states_pruned",
    )
    if any(search.get(key) is not True for key in required_true) or any(
        search.get(key) is not False for key in required_false
    ):
        raise ValueError("arm catalogue/state search is incomplete or pruned")
    rows = tuple(
        _object(item, "arm ranking row") for item in _list(search.get("ranking"), "arm ranking")
    )
    if not rows or search.get("ranking_digest") != canonical_digest(list(rows)):
        raise ValueError("arm ranking is empty or its digest does not recompute")
    if len(rows) != len(eligible):
        raise ValueError("arm omitted an eligible catalogue row")
    prior: tuple[float, int, str] | None = None
    state_receipts = []
    for rank, row in enumerate(rows, start=1):
        if _integer(row.get("rank"), "arm catalogue rank", minimum=1) != rank:
            raise ValueError("arm catalogue ranks are not contiguous")
        catalog_number = _integer(row.get("catalog_number"), "arm catalogue", minimum=1)
        generated = _integer(row.get("generated_state_count"), "arm state count", minimum=1)
        if generated != expected_states_per_member:
            raise ValueError("arm catalogue has an incomplete nuisance-state bank")
        delta = _finite(row.get("best_single_delta_from_null"), "arm catalogue delta")
        selected = row.get("best_single_selected")
        if not isinstance(selected, bool) or selected is not (delta < 0.0):
            raise ValueError("arm catalogue selected flag disagrees with its primitive delta")
        hypothesis = row.get("best_hypothesis_id")
        if not isinstance(hypothesis, str) or not hypothesis:
            raise ValueError("arm catalogue minimum has no hypothesis identity")
        key = (delta, catalog_number, hypothesis)
        if prior is not None and key < prior:
            raise ValueError("arm catalogue ranking is not deterministic")
        prior = key
        state_digest = _canonical_sha256(row.get("state_bank_digest"), "state-bank digest")
        if row.get("state_bank_digest_algorithm") != STATE_DIGEST_ALGORITHM:
            raise ValueError("arm state-bank digest algorithm is unsupported")
        objective = _object(row.get("best_modeled_objective"), "arm best objective")
        if (
            _finite(objective.get("null_cost"), "arm modeled null") != modeled_null_cost
            or _finite(objective.get("total_cost"), "arm modeled total")
            != _finite(row.get("best_single_total_cost"), "arm best total")
            or _finite(objective.get("delta_from_null"), "arm modeled delta") != delta
        ):
            raise ValueError("arm best objective primitives are inconsistent")
        state_receipts.append(
            {
                "catalog_number": catalog_number,
                "generated_state_count": generated,
                "state_bank_digest": state_digest,
            }
        )
    if tuple(sorted(row["catalog_number"] for row in rows)) != eligible:
        raise ValueError("arm ranking identities differ from its eligible partition")
    accounting = _object(search.get("state_accounting"), "arm state accounting")
    payload = dict(accounting)
    content_digest = _canonical_sha256(payload.pop("content_digest", None), "state accounting")
    if canonical_digest(payload) != content_digest:
        raise ValueError("arm state-accounting digest does not recompute")
    expected_total = len(rows) * expected_states_per_member
    if payload != {
        "state_digest_algorithm": STATE_DIGEST_ALGORITHM,
        "expected_state_count_per_eligible_catalogue": expected_states_per_member,
        "eligible_catalogue_count": len(rows),
        "expected_generated_state_count": expected_total,
        "generated_state_count": expected_total,
        "members": state_receipts,
    }:
        raise ValueError("arm state accounting is incomplete or inconsistent")
    decision = _object(arm.get("decision"), "arm decision")
    winner = rows[0]
    runner = rows[1] if len(rows) > 1 else None
    delta = _finite(winner.get("best_single_delta_from_null"), "arm winner delta")
    selected = delta < 0.0
    signed_primitive_improvement = -delta
    statistic = max(0.0, signed_primitive_improvement)
    selected_numbers = [winner["catalog_number"]] if selected else []
    if (
        decision.get("selected_catalog_numbers") != selected_numbers
        or decision.get("selected_satellite_count") != int(selected)
        or decision.get("activation_witness_found") is not selected
        or decision.get("best_catalog_number") != winner["catalog_number"]
        or decision.get("best_object_name") != winner["object_name"]
        or decision.get("best_hypothesis_id") != winner["best_hypothesis_id"]
        or _finite(decision.get("test_statistic_improvement_from_null"), "arm statistic")
        != statistic
        or _finite(
            decision.get("signed_primitive_improvement_from_null"),
            "arm signed primitive improvement",
        )
        != signed_primitive_improvement
        or _finite_nonnegative(
            decision.get("nonnegative_activation_improvement_from_null"),
            "arm nonnegative activation improvement",
        )
        != statistic
        or decision.get("winning_catalogue_minimum") != winner
    ):
        raise ValueError("arm decision does not select its deterministic full-catalogue minimum")
    objective = _object(decision.get("full_persisted_inventory_objective"), "arm full objective")
    if (
        _finite(objective.get("modeled_null_cost"), "arm objective null") != modeled_null_cost
        or _finite(objective.get("decision_invariant_delta_from_null"), "arm primitive delta")
        != delta
        or _finite(objective.get("delta_from_null"), "arm reported delta") != delta
    ):
        raise ValueError("arm full objective does not preserve the primitive winner delta")
    return {
        "arm_id": str(arm.get("arm_id", "")),
        "role": str(arm.get("role", "")),
        "best_catalog_number": int(winner["catalog_number"]),
        "runner_up_catalog_number": (None if runner is None else int(runner["catalog_number"])),
        "delta_from_null": delta,
        "runner_up_delta_from_null": _finite(
            0.0 if runner is None else runner.get("best_single_delta_from_null"),
            "arm runner-up or exact-null delta",
        ),
        "signed_primitive_improvement": signed_primitive_improvement,
        "test_statistic": statistic,
        "activation_witness_found": selected,
    }


def _gate_from_statistics(
    *, statistics: tuple[dict[str, Any], ...], family_plan: dict[str, Any]
) -> dict[str, Any]:
    if len(statistics) != len(REQUIRED_CONTROL_INDICES) + 1:
        raise ValueError("control family does not contain exactly identity plus controls 0..19")
    if statistics[0].get("role") != "identity":
        raise ValueError("control family does not begin with the identity arm")
    controls = statistics[1:]
    if any(item.get("role") != "block_permutation_control" for item in controls):
        raise ValueError("randomization family has a non-control arm after identity")
    identity_t = _finite_nonnegative(statistics[0].get("test_statistic"), "identity statistic")
    gamma = _finite_nonnegative(family_plan.get("minimum_advantage_cost"), "frozen margin")
    greater_or_equal = sum(
        _finite_nonnegative(item.get("test_statistic"), "control statistic") >= identity_t
        for item in controls
    )
    strongest = min(
        controls,
        key=lambda item: (-float(item["test_statistic"]), str(item["arm_id"])),
    )
    strongest_t = _finite_nonnegative(strongest["test_statistic"], "strongest control statistic")
    margin = math.fsum((identity_t, -strongest_t))
    strict_margin_passed = identity_t > strongest_t + gamma
    identity_runner_delta = _finite(
        statistics[0].get("runner_up_delta_from_null"), "identity runner-up delta"
    )
    identity_winner_delta = _finite(statistics[0].get("delta_from_null"), "identity winner delta")
    winner_runner_margin = math.fsum((identity_runner_delta, -identity_winner_delta))
    identity_activated = statistics[0].get("activation_witness_found") is True
    conditional_passed = identity_activated and strict_margin_passed
    plan_verified = family_plan.get("plan_authority_verified") is True
    prospective_binding_verified = family_plan.get("prospective_plan_binding_verified") is True
    preregistered = family_plan.get("external_preregistration_verified") is True
    if not identity_activated:
        disposition = IDENTITY_NONACTIVATION
        reasons = ["the identity full-catalogue search did not beat its exact finite null"]
    elif not strict_margin_passed:
        disposition = STRICT_MARGIN_NOT_PASSED
        reasons = ["identity T is not strictly greater than strongest-control T plus gamma"]
    elif not plan_verified or not preregistered:
        disposition = PLAN_AUTHORITY_NOT_VERIFIED
        reasons = ["pre-evidence plan authority and external preregistration are not verified"]
    else:
        disposition = CONDITIONAL_GATE_PASS
        reasons = ["the conditional full-catalogue randomization and strict-margin gates passed"]
    control_rows = [
        {
            "arm_id": item["arm_id"],
            "best_catalog_number": item["best_catalog_number"],
            "delta_from_null": item["delta_from_null"],
            "signed_primitive_improvement_from_null": item["signed_primitive_improvement"],
            "T": item["test_statistic"],
            "test_statistic_improvement_from_null": item["test_statistic"],
            "ties_or_exceeds_identity": item["test_statistic"] >= identity_t,
            "activation_witness_found": item["activation_witness_found"],
        }
        for item in controls
    ]
    return {
        "disposition": disposition,
        "comparable": True,
        "conditional_full_catalogue_gate_passed": conditional_passed,
        "authority_gate_passed": conditional_passed and plan_verified and preregistered,
        "association_claimed": False,
        "tracking_claimed": False,
        "specificity_claimed": False,
        "presence_false_positive_rate_estimated": False,
        "identity_arm_id": statistics[0]["arm_id"],
        "identity_best_catalog_number": statistics[0]["best_catalog_number"],
        "identity_runner_up_catalog_number": statistics[0]["runner_up_catalog_number"],
        "identity_delta_from_null": statistics[0]["delta_from_null"],
        "identity_runner_up_delta_from_null": identity_runner_delta,
        "identity_winner_over_runner_cost_margin": winner_runner_margin,
        "identity_signed_primitive_improvement_from_null": statistics[0][
            "signed_primitive_improvement"
        ],
        "T_identity": identity_t,
        "identity_test_statistic_improvement_from_null": identity_t,
        "strongest_control_arm_id": strongest["arm_id"],
        "strongest_control_best_catalog_number": strongest["best_catalog_number"],
        "T_control_max": strongest_t,
        "strongest_control_test_statistic_improvement_from_null": strongest_t,
        "identity_advantage_over_strongest_control_cost": margin,
        "minimum_advantage_cost": gamma,
        "strict_margin_comparison": "identity_T > strongest_control_T + gamma",
        "strict_margin_passed": strict_margin_passed,
        "A_k": margin,
        "per_dwell_dominance_A_k": margin,
        "cohort_control_max_statistic": None,
        "cohort_control_max_reducible_from_one_dwell": False,
        "descriptive_control_rank": {
            "inferential_permutation_p_value": None,
            "randomization_exchangeability_verified": False,
            "interpretation": "descriptive rank only; not a p-value or false-positive rate",
            "control_count": len(controls),
            "controls_with_T_at_least_identity_count": greater_or_equal,
            "identity_rank_among_21": greater_or_equal + 1,
            "minimum_possible_rank_fraction": 1.0 / 21.0,
        },
        "plan_authority_verified": plan_verified,
        "prospective_plan_binding_verified": prospective_binding_verified,
        "external_preregistration_verified": preregistered,
        "controls": control_rows,
        "reasons": reasons,
    }


def _validate_family_plan_document(
    family: dict[str, Any],
    *,
    digests: dict[str, Any],
    problem: Any,
    source_binding: dict[str, Any],
) -> None:
    expected_family_fields = {
        "schema",
        "algorithm",
        "selection_context",
        "selection_context_digest",
        "arm_selection_context_digest",
        "arm_selection_context_source",
        "control_indices",
        "control_count",
        "minimum_advantage_cost",
        "randomization_exchangeability_verified",
        "permutation_p_value",
        "prospective_plan_binding_verified",
        "plan_authority_verified",
        "external_preregistration_verified",
        "prospective_plan_binding",
        "arms",
        "family_frozen_before_arm_scoring",
        "all_control_plans_built_before_arm_scoring",
        "full_catalogue_procedure_frozen_before_arm_scoring",
    }
    if set(family) != expected_family_fields:
        raise ValueError("family-plan receipt inventory is incomplete or extended")
    selection = _object(family.get("selection_context"), "selection context")
    expected_selection_fields = {
        "schema",
        "algorithm",
        "family_label",
        "session_id",
        "recording_manifest_digest",
        "path_id",
        "path_scope_digest",
        "evidence_path_scope_digest",
        "stream_id",
        "radio_id",
        "radio_serial",
        "receiver_id",
        "tuning_tag",
        "sky_frequency_hz",
        "duration_dataset_digest",
        "window",
        "raw_problem_digest",
        "objective_digest",
        "search_universe_digest",
        "producer_digest",
        "source_binding_digest",
        "control_indices",
        "minimum_advantage_cost",
        "prospective_plan_binding_digest",
        "randomization_exchangeability_verified",
        "permutation_p_value",
        "same_named_catalogue_reselected_in_every_arm",
    }
    if set(selection) != expected_selection_fields:
        raise ValueError("selection-context receipt inventory is incomplete or extended")
    family_label = selection.get("family_label")
    if not isinstance(family_label, str) or not family_label:
        raise ValueError("selection context omits its family label")
    controls = _list(family.get("control_indices"), "family control indices")
    gamma = _finite_nonnegative(family.get("minimum_advantage_cost"), "frozen margin")
    window = _object(selection.get("window"), "selection window")
    if set(window) != {
        "start_s",
        "end_s",
        "cell_duration_s",
        "cell_count",
        "minimum_active_cells",
    }:
        raise ValueError("selection window inventory is incomplete or extended")
    bound_window = _object(source_binding.get("window"), "source binding window")
    if window != {
        "start_s": bound_window.get("start_s"),
        "end_s": bound_window.get("end_s"),
        "cell_duration_s": problem.grid.cell_duration_s,
        "cell_count": problem.grid.cell_count,
        "minimum_active_cells": problem.grid.minimum_active_cells,
    }:
        raise ValueError("selection window differs from the raw problem or source binding")
    if (
        family.get("schema") != FAMILY_PLAN_SCHEMA
        or family.get("algorithm") != ALGORITHM
        or selection.get("schema") != FAMILY_PLAN_SCHEMA
        or selection.get("algorithm") != ALGORITHM
        or selection.get("session_id") != source_binding.get("session_id")
        or selection.get("recording_manifest_digest")
        != source_binding.get("recording_manifest_digest")
        or any(
            selection.get(field) != digests.get(field)
            for field in (
                "raw_problem_digest",
                "objective_digest",
                "search_universe_digest",
                "producer_digest",
                "source_binding_digest",
            )
        )
        or family.get("control_count") != len(REQUIRED_CONTROL_INDICES)
        or controls != list(REQUIRED_CONTROL_INDICES)
        or selection.get("control_indices") != controls
        or _finite_nonnegative(selection.get("minimum_advantage_cost"), "selection margin") != gamma
        or family.get("randomization_exchangeability_verified") is not False
        or family.get("permutation_p_value") is not None
        or selection.get("randomization_exchangeability_verified") is not False
        or selection.get("permutation_p_value") is not None
        or selection.get("same_named_catalogue_reselected_in_every_arm") is not True
        or family.get("plan_authority_verified") is not False
        or family.get("external_preregistration_verified") is not False
        or family.get("family_frozen_before_arm_scoring") is not True
        or family.get("all_control_plans_built_before_arm_scoring") is not True
        or family.get("full_catalogue_procedure_frozen_before_arm_scoring") is not True
    ):
        raise ValueError("family plan changes the frozen noninferential control procedure")
    prospective_binding = family.get("prospective_plan_binding")
    binding_verified = family.get("prospective_plan_binding_verified")
    expected_binding_digest = (
        None
        if prospective_binding is None
        else canonical_digest(_object(prospective_binding, "prospective plan binding"))
    )
    if (
        not isinstance(binding_verified, bool)
        or binding_verified is (prospective_binding is None)
        or selection.get("prospective_plan_binding_digest") != expected_binding_digest
    ):
        raise ValueError("family prospective-plan binding receipt is inconsistent")
    _list(family.get("arms"), "family planned arms")


def adjudicate_full_catalogue_arms(
    *, arms: tuple[dict[str, Any], ...], common: dict[str, Any]
) -> dict[str, Any]:
    """Rebuild the frozen family and fail closed on all serialized invariants."""

    try:
        expected_common = {
            "digests",
            "raw_problem",
            "objective",
            "search_universe",
            "producer",
            "source_binding",
            "family_plan",
        }
        if set(common) != expected_common:
            raise ValueError("full-catalogue common document inventory is incomplete")
        digests = _object(common.get("digests"), "common digests")
        digest_fields = {
            "raw_problem_digest": "raw_problem",
            "objective_digest": "objective",
            "search_universe_digest": "search_universe",
            "producer_digest": "producer",
            "source_binding_digest": "source_binding",
            "family_plan_digest": "family_plan",
        }
        if set(digests) != set(digest_fields):
            raise ValueError("full-catalogue common digest inventory is incomplete")
        for digest_name, field in digest_fields.items():
            if _canonical_sha256(digests[digest_name], digest_name) != canonical_digest(
                common[field]
            ):
                raise ValueError(f"full-catalogue {field} digest does not recompute")
        if common.get("producer") != producer_implementation_manifest():
            raise ValueError("full-catalogue producer implementation manifest is not current")
        raw_problem = _object(common.get("raw_problem"), "raw problem")
        problem = fixed._problem_from_payload(raw_problem)
        _validate_raw_problem_receipts(raw_problem, problem=problem)
        persisted = tuple(
            _object(item, "persisted probe UTC")
            for item in _list(raw_problem.get("persisted_probe_utc"), "persisted probe UTC")
        )
        source_binding = _object(common.get("source_binding"), "source binding")
        _validate_source_binding_receipts(source_binding, problem=problem, raw_problem=raw_problem)
        objective = _object(common.get("objective"), "objective")
        _validate_objective_document(objective, problem=problem, source_binding=source_binding)
        modeled_null = bounded._modeled_null_cost(problem)
        universe = _object(common.get("search_universe"), "search universe")
        named = tuple(
            _integer(item, "named catalogue identity", minimum=1)
            for item in _list(universe.get("named_catalog_numbers"), "named catalogue identities")
        )
        if named != tuple(sorted(set(named))) or not named:
            raise ValueError(
                "declared named catalogue universe is not sorted, unique, and nonempty"
            )
        if universe.get("named_catalog_numbers_digest") != canonical_digest(list(named)):
            raise ValueError("declared named catalogue universe digest does not recompute")
        config = fixed._raw_config(_object(universe.get("configuration"), "configuration"))
        _validate_search_universe_document(
            universe,
            named=named,
            config=config,
            source_binding=source_binding,
        )
        if (
            config.satellite_cost != problem.costs.satellite_cost
            or config.episode_cost != problem.costs.episode_cost
        ):
            raise ValueError("search configuration and raw-problem structural costs differ")
        expected_states = len(config.delay_grid) * config.modes_per_delay
        family = _object(common.get("family_plan"), "family plan")
        _validate_family_plan_document(
            family,
            digests=digests,
            problem=problem,
            source_binding=source_binding,
        )
        selection_context = _object(family.get("selection_context"), "selection context")
        selection_digest = _canonical_sha256(
            family.get("selection_context_digest"), "selection-context digest"
        )
        if canonical_digest(selection_context) != selection_digest:
            raise ValueError("selection-context digest does not recompute")
        arm_selection_digest = _canonical_sha256(
            family.get("arm_selection_context_digest"), "arm selection-context digest"
        )
        controls = tuple(
            _integer(item, "control index")
            for item in _list(family.get("control_indices"), "control indices")
        )
        if selection_context.get("control_indices") != list(controls):
            raise ValueError("selection context and family control indices differ")
        if (
            family.get("family_frozen_before_arm_scoring") is not True
            or family.get("all_control_plans_built_before_arm_scoring") is not True
            or family.get("full_catalogue_procedure_frozen_before_arm_scoring") is not True
        ):
            raise ValueError("full-catalogue arm family was not atomically frozen")
        transforms = _freeze_arm_transforms(
            problem=SimpleNamespace(grid=problem.grid),
            selection_context_digest=arm_selection_digest,
            control_indices=controls,
            maximum_delay_support_s=max(abs(config.delay_min_s), abs(config.delay_max_s)),
        )
        planned = _list(family.get("arms"), "planned arms")
        expected_planned = [
            {
                "arm_id": item.arm_id,
                "role": item.role,
                "transform_digest": item.transform_digest,
                "transform": item.receipt,
            }
            for item in transforms
        ]
        if canonical_digest(planned) != canonical_digest(expected_planned):
            raise ValueError("frozen arm plans do not regenerate")
        if len(arms) != len(transforms):
            raise ValueError("full-catalogue artifact omitted or added an arm")
        statistics: list[dict[str, Any]] = []
        mapping_digests = []
        invariant_eligible: tuple[int, ...] | None = None
        invariant_partition_digest: str | None = None
        for arm, transform in zip(arms, transforms, strict=True):
            if arm.get("common_digests") != digests:
                raise ValueError("arm common digests differ from the frozen family")
            expected_plan = expected_planned[len(statistics)]
            if any(
                arm.get(key) != expected_plan[key] for key in ("arm_id", "role", "transform_digest")
            ):
                raise ValueError("emitted arm identity differs from its frozen plan")
            serialized_transform = _object(arm.get("transform"), "emitted arm transform")
            if canonical_digest(serialized_transform) != canonical_digest(transform.receipt):
                raise ValueError("emitted arm transform differs from its frozen plan")
            mapping_digest = fixed._validate_mapping(
                arm=arm,
                persisted=persisted,
                problem=problem,
                transform=transform,
            )
            mapping_digests.append(mapping_digest)
            eligible = _validate_partition(arm=arm, named_catalog_numbers=named)
            partition = _object(arm.get("catalogue_identity_partition"), "arm identity partition")
            partition_digest = _canonical_sha256(
                partition.get("partition_content_digest"), "arm partition digest"
            )
            if invariant_eligible is None:
                invariant_eligible = eligible
                invariant_partition_digest = partition_digest
            elif eligible != invariant_eligible or partition_digest != invariant_partition_digest:
                raise ValueError(
                    "prediction-time arms changed the invariant geometry identity partition"
                )
            statistics.append(
                _validate_arm_search(
                    arm=arm,
                    eligible=eligible,
                    expected_states_per_member=expected_states,
                    modeled_null_cost=modeled_null,
                )
            )
        if len(set(mapping_digests)) != len(mapping_digests):
            raise ValueError("full-catalogue arms have colliding prediction-time mappings")
        if source_binding.get("single_receiver_path_only") is not True:
            raise ValueError("source binding does not explicitly constrain one receiver path")
        if source_binding.get("capture_wide_or_multipath_search_performed") is not False:
            raise ValueError("source binding improperly claims capture-wide or multipath search")
        path_scope = _validate_path_scope_document(source_binding.get("path_scope"))
        if (
            source_binding.get("path_id") != path_scope["path_id"]
            or selection_context.get("path_id") != path_scope["path_id"]
            or selection_context.get("path_scope_digest") != path_scope["path_scope_digest"]
            or selection_context.get("evidence_path_scope_digest")
            != path_scope["evidence_path_scope_digest"]
            or any(
                selection_context.get(field) != path_scope[field]
                for field in (
                    "stream_id",
                    "radio_id",
                    "radio_serial",
                    "receiver_id",
                    "tuning_tag",
                    "sky_frequency_hz",
                    "duration_dataset_digest",
                )
            )
        ):
            raise ValueError("family selection context changed the bound receiver-path identity")
        if (
            source_binding.get("source_identity_partition_content_digest")
            != invariant_partition_digest
        ):
            raise ValueError("arm identity partition differs from the bound source partition")
        prospective_binding_raw = family.get("prospective_plan_binding")
        if prospective_binding_raw is None:
            if (
                family.get("prospective_plan_binding_verified") is not False
                or family.get("plan_authority_verified") is not False
                or family.get("external_preregistration_verified") is not False
                or family.get("arm_selection_context_source") != "diagnostic-evidence-bound-context"
                or arm_selection_digest != selection_digest
                or selection_context.get("prospective_plan_binding_digest") is not None
            ):
                raise ValueError("diagnostic family improperly claims prospective-plan authority")
        else:
            prospective_binding = _object(prospective_binding_raw, "prospective plan binding")
            if (
                family.get("prospective_plan_binding_verified") is not True
                or family.get("plan_authority_verified") is not False
                or family.get("external_preregistration_verified") is not False
                or family.get("arm_selection_context_source") != "pre-evidence-prospective-plan"
                or prospective_binding.get("plan_structural_and_source_binding_verified")
                is not True
                or prospective_binding.get("association_authority_enabled") is not False
                or prospective_binding.get("tracking_authority_enabled") is not False
                or prospective_binding.get("path_id") != path_scope["path_id"]
                or prospective_binding.get("path_scope_digest") != path_scope["path_scope_digest"]
                or prospective_binding.get("duration_dataset_digest")
                != path_scope["duration_dataset_digest"]
                or prospective_binding.get("producer_implementation_manifest_digest")
                != canonical_digest(common["producer"])
                or prospective_binding.get("bounded_producer_implementation_manifest_digest")
                != canonical_digest(bounded.producer_implementation_manifest())
                or prospective_binding.get("control_selection_context_digest")
                != arm_selection_digest
                or prospective_binding.get("control_transform_digests")
                != [item.transform_digest for item in transforms[1:]]
                or selection_context.get("family_label") != prospective_binding.get("plan_id")
                or selection_context.get("prospective_plan_binding_digest")
                != canonical_digest(prospective_binding)
                or prospective_binding.get("external_preregistration_verified") is not False
            ):
                raise ValueError("prospective plan binding receipt is incomplete or inconsistent")
        result = _gate_from_statistics(statistics=tuple(statistics), family_plan=family)
    except (KeyError, IndexError, OSError, OverflowError, TypeError, ValueError) as error:
        return {
            "disposition": NOT_COMPARABLE,
            "comparable": False,
            "conditional_full_catalogue_gate_passed": False,
            "authority_gate_passed": False,
            "association_claimed": False,
            "tracking_claimed": False,
            "specificity_claimed": False,
            "presence_false_positive_rate_estimated": False,
            "reasons": [str(error)],
        }
    return result


def replay_raw_full_catalogue_paired_prediction_time(
    *,
    source_path: Path,
    expected_source_digest: str,
    control_indices: tuple[int, ...],
    family_label: str,
    minimum_advantage_cost: float,
    prospective_plan_path: Path | None = None,
    expected_prospective_plan_digest: str | None = None,
    prospective_cohort_ordinal: int | None = None,
) -> dict[str, Any]:
    """Freeze and score one complete full-catalogue identity/control family."""

    if not family_label:
        raise ValueError("full-catalogue family label must be nonempty")
    gamma = _finite_nonnegative(minimum_advantage_cost, "minimum advantage cost")
    ordered_controls = tuple(sorted(control_indices))
    if control_indices != REQUIRED_CONTROL_INDICES:
        raise ValueError("full-catalogue replay requires exact ordered control indices 0..19")
    plan_arguments = (
        prospective_plan_path,
        expected_prospective_plan_digest,
        prospective_cohort_ordinal,
    )
    if any(item is not None for item in plan_arguments) and any(
        item is None for item in plan_arguments
    ):
        raise ValueError(
            "prospective plan path, digest, and discovery cohort ordinal must be supplied together"
        )
    validated_plan: dict[str, Any] | None = None
    if prospective_plan_path is not None:
        from tools import freeze_prospective_starlink_tracking_plan as prospective

        assert expected_prospective_plan_digest is not None
        validated_plan = prospective.load_and_validate_prospective_plan(
            plan_path=prospective_plan_path,
            expected_plan_file_digest=_canonical_sha256(
                expected_prospective_plan_digest, "prospective plan file digest"
            ),
        )
        _require_prospective_execution_readiness(validated_plan)
    source = _load_source(source_path=source_path, expected_source_digest=expected_source_digest)
    problem = source.inventory.problem
    raw_problem = fixed._problem_payload(source)
    source_partition = _object(
        source.source.get("catalogue_identity_partition"), "source identity partition"
    )
    named = tuple(
        _integer(item, "source named catalogue", minimum=1)
        for item in _list(
            source_partition.get("named_catalog_numbers"), "source named catalogue identities"
        )
    )
    path_scope = _single_path_scope(source)
    prospective_binding: dict[str, Any] | None = None
    prospective_seed_digest: str | None = None
    if prospective_plan_path is not None:
        assert expected_prospective_plan_digest is not None
        assert prospective_cohort_ordinal is not None
        prospective_binding, prospective_seed_digest = _validate_prospective_plan_binding(
            source=source,
            plan_path=prospective_plan_path,
            expected_plan_digest=expected_prospective_plan_digest,
            cohort_ordinal=prospective_cohort_ordinal,
            minimum_advantage_cost=gamma,
            validated_plan=validated_plan,
        )
        if family_label != prospective_binding.get("plan_id"):
            raise ValueError("plan-bound family label must equal the prospective plan ID")
    objective = _objective_document(source)
    search_universe = _search_universe_document(source, named_catalog_numbers=named)
    source_binding = _source_binding_document(source, path_scope=path_scope)
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
            "start_s": source.start_s,
            "end_s": source.end_s,
            "cell_duration_s": problem.grid.cell_duration_s,
            "cell_count": problem.grid.cell_count,
            "minimum_active_cells": problem.grid.minimum_active_cells,
        },
        **preliminary,
        "control_indices": list(ordered_controls),
        "minimum_advantage_cost": gamma,
        "prospective_plan_binding_digest": (
            None if prospective_binding is None else canonical_digest(prospective_binding)
        ),
        "randomization_exchangeability_verified": False,
        "permutation_p_value": None,
        "same_named_catalogue_reselected_in_every_arm": True,
    }
    selection_context_digest = canonical_digest(selection_context)
    arm_selection_context_digest = (
        selection_context_digest if prospective_seed_digest is None else prospective_seed_digest
    )
    transforms = _freeze_arm_transforms(
        problem=SimpleNamespace(grid=problem.grid),
        selection_context_digest=arm_selection_context_digest,
        control_indices=ordered_controls,
        maximum_delay_support_s=max(abs(source.config.delay_min_s), abs(source.config.delay_max_s)),
    )
    family_plan = {
        "schema": FAMILY_PLAN_SCHEMA,
        "algorithm": ALGORITHM,
        "selection_context": selection_context,
        "selection_context_digest": selection_context_digest,
        "arm_selection_context_digest": arm_selection_context_digest,
        "arm_selection_context_source": (
            "diagnostic-evidence-bound-context"
            if prospective_binding is None
            else "pre-evidence-prospective-plan"
        ),
        "control_indices": list(ordered_controls),
        "control_count": len(ordered_controls),
        "minimum_advantage_cost": gamma,
        "randomization_exchangeability_verified": False,
        "permutation_p_value": None,
        "prospective_plan_binding_verified": prospective_binding is not None,
        "plan_authority_verified": False,
        "external_preregistration_verified": False,
        "prospective_plan_binding": prospective_binding,
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
        "full_catalogue_procedure_frozen_before_arm_scoring": True,
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
        _evaluate_arm(source=source, transform=transform, common_digests=common_digests)
        for transform in transforms
    )
    if canonical_digest(fixed._problem_payload(source)) != common_digests["raw_problem_digest"]:
        raise RuntimeError("shared raw problem changed while the atomic family was evaluated")
    adjudication = adjudicate_full_catalogue_arms(arms=arms, common=common)
    if not adjudication.get("comparable"):
        raise RuntimeError(
            "fresh full-catalogue family failed internal adjudication: "
            + "; ".join(str(item) for item in adjudication.get("reasons", ()))
        )
    document: dict[str, Any] = {
        "schema": OUTPUT_SCHEMA,
        "algorithm": ALGORITHM,
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
        "prospective_plan_binding_verified": prospective_binding is not None,
        "plan_authority_verified": False,
        "external_preregistration_verified": False,
        "continuous_nuisance_space_exhausted": False,
        "pre_acquisition_cap_inventory_complete": False,
        "physical_signal_inventory_complete": False,
        "common": common,
        "arms": list(arms),
        "adjudication": adjudication,
        "caveats": list(OUTPUT_CAVEATS),
    }
    document["payload_content_digest"] = canonical_digest(document)
    return document


def _validate_top_level_document(document: dict[str, Any]) -> None:
    expected_fields = {
        "schema",
        "algorithm",
        "research_only",
        "candidate_only",
        "single_receiver_path_only",
        "capture_wide_or_multipath_search_performed",
        "association_claimed",
        "tracking_claimed",
        "specificity_claimed",
        "payload_decoded",
        "presence_false_positive_rate_estimated",
        "randomization_exchangeability_verified",
        "permutation_p_value",
        "block_controls_are_conditional_prediction_time_specificity_only",
        "all_arms_share_one_loaded_raw_problem",
        "all_arms_share_one_objective",
        "same_named_catalogue_reselected_in_every_arm",
        "every_arm_partitions_every_named_identity",
        "all_declared_arms_emitted",
        "prospective_plan_binding_verified",
        "plan_authority_verified",
        "external_preregistration_verified",
        "continuous_nuisance_space_exhausted",
        "pre_acquisition_cap_inventory_complete",
        "physical_signal_inventory_complete",
        "common",
        "arms",
        "adjudication",
        "caveats",
        "payload_content_digest",
    }
    if set(document) != expected_fields:
        raise ValueError("full-catalogue top-level field inventory is incomplete or extended")
    required_true = (
        "research_only",
        "candidate_only",
        "single_receiver_path_only",
        "block_controls_are_conditional_prediction_time_specificity_only",
        "all_arms_share_one_loaded_raw_problem",
        "all_arms_share_one_objective",
        "same_named_catalogue_reselected_in_every_arm",
        "every_arm_partitions_every_named_identity",
        "all_declared_arms_emitted",
    )
    required_false = (
        "capture_wide_or_multipath_search_performed",
        "association_claimed",
        "tracking_claimed",
        "specificity_claimed",
        "payload_decoded",
        "presence_false_positive_rate_estimated",
        "randomization_exchangeability_verified",
        "plan_authority_verified",
        "external_preregistration_verified",
        "continuous_nuisance_space_exhausted",
        "pre_acquisition_cap_inventory_complete",
        "physical_signal_inventory_complete",
    )
    if any(document.get(field) is not True for field in required_true) or any(
        document.get(field) is not False for field in required_false
    ):
        raise ValueError("full-catalogue top-level authority, claim, or scope flags are invalid")
    if not isinstance(document.get("prospective_plan_binding_verified"), bool):
        raise ValueError("full-catalogue prospective-plan binding flag is not boolean")
    if document.get("permutation_p_value") is not None:
        raise ValueError("full-catalogue top level improperly reports a permutation p-value")
    caveats = _list(document.get("caveats"), "full-catalogue caveats")
    if caveats != list(OUTPUT_CAVEATS):
        raise ValueError("full-catalogue caveat inventory differs from the frozen producer")
    _object(document.get("common"), "full-catalogue common document")
    _list(document.get("arms"), "full-catalogue arms")
    _object(document.get("adjudication"), "full-catalogue adjudication")


def verify_full_catalogue_document(document: dict[str, Any]) -> dict[str, Any]:
    """Reload source bytes once and regenerate every arm for independent verification."""

    payload = dict(document)
    digest = _canonical_sha256(payload.pop("payload_content_digest", None), "payload digest")
    if canonical_digest(payload) != digest:
        raise ValueError("full-catalogue payload digest does not recompute")
    _validate_top_level_document(document)
    if document.get("schema") != OUTPUT_SCHEMA or document.get("algorithm") != ALGORITHM:
        raise ValueError("full-catalogue output schema or algorithm is unsupported")
    common = _object(document.get("common"), "full-catalogue common document")
    source_binding = _object(common.get("source_binding"), "source binding")
    source_path_raw = source_binding.get("source_artifact_path")
    if not isinstance(source_path_raw, str) or not source_path_raw:
        raise ValueError("source binding has no artifact path")
    source = _load_source(
        source_path=Path(source_path_raw),
        expected_source_digest=_canonical_sha256(
            source_binding.get("source_artifact_file_digest"), "source artifact digest"
        ),
    )
    if source_binding != _source_binding_document(source, path_scope=_single_path_scope(source)):
        raise ValueError("source binding does not regenerate from bound nested source bytes")
    raw_problem = _object(common.get("raw_problem"), "raw problem")
    if raw_problem != fixed._problem_payload(source):
        raise ValueError("raw problem does not regenerate from the bound source bytes")
    if _object(common.get("objective"), "objective") != _objective_document(source):
        raise ValueError("objective does not regenerate from the bound source bytes")
    source_partition = _object(
        source.source.get("catalogue_identity_partition"), "source identity partition"
    )
    named_catalog_numbers = tuple(
        _integer(item, "source named catalogue", minimum=1)
        for item in _list(
            source_partition.get("named_catalog_numbers"), "source named catalogue identities"
        )
    )
    if _object(common.get("search_universe"), "search universe") != (
        _search_universe_document(source, named_catalog_numbers=named_catalog_numbers)
    ):
        raise ValueError("search universe does not regenerate from the bound source bytes")
    family = _object(common.get("family_plan"), "family plan")
    controls = tuple(
        _integer(item, "control index")
        for item in _list(family.get("control_indices"), "control indices")
    )
    selection_digest = _canonical_sha256(
        family.get("arm_selection_context_digest"), "arm selection-context digest"
    )
    prospective_binding_raw = family.get("prospective_plan_binding")
    if prospective_binding_raw is not None:
        prospective_binding = _object(prospective_binding_raw, "prospective plan binding")
        verified_binding, verified_seed = _validate_prospective_plan_binding(
            source=source,
            plan_path=Path(str(prospective_binding.get("plan_path", ""))),
            expected_plan_digest=_canonical_sha256(
                prospective_binding.get("plan_file_digest"), "prospective plan file digest"
            ),
            cohort_ordinal=_integer(
                prospective_binding.get("cohort_ordinal"), "prospective cohort ordinal", minimum=1
            ),
            minimum_advantage_cost=_finite_nonnegative(
                family.get("minimum_advantage_cost"), "minimum advantage cost"
            ),
        )
        if verified_binding != prospective_binding or verified_seed != selection_digest:
            raise ValueError("prospective plan binding does not independently revalidate")
        selection_context = _object(family.get("selection_context"), "selection context")
        if selection_context.get("family_label") != prospective_binding.get("plan_id"):
            raise ValueError("prospective family label differs from the bound plan ID")
    transforms = _freeze_arm_transforms(
        problem=SimpleNamespace(grid=source.inventory.problem.grid),
        selection_context_digest=selection_digest,
        control_indices=controls,
        maximum_delay_support_s=max(abs(source.config.delay_min_s), abs(source.config.delay_max_s)),
    )
    digests = cast(dict[str, str], _object(common.get("digests"), "common digests"))
    regenerated = tuple(
        _evaluate_arm(source=source, transform=transform, common_digests=digests)
        for transform in transforms
    )
    arms = tuple(
        _object(item, "full-catalogue arm")
        for item in _list(document.get("arms"), "full-catalogue arms")
    )
    if canonical_digest(regenerated) != canonical_digest(arms):
        raise ValueError("full-catalogue arms do not regenerate from bound source bytes")
    adjudication = adjudicate_full_catalogue_arms(arms=arms, common=common)
    if adjudication != _object(document.get("adjudication"), "full-catalogue adjudication"):
        raise ValueError("full-catalogue adjudication does not recompute")
    family = _object(common.get("family_plan"), "full-catalogue family plan")
    if document.get("prospective_plan_binding_verified") is not (
        family.get("prospective_plan_binding_verified") is True
    ):
        raise ValueError("top-level prospective-plan binding flag differs from the family")
    return adjudication


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-artifact", type=Path, required=True)
    parser.add_argument("--source-artifact-sha256", required=True)
    parser.add_argument("--control-index", action="append", type=int, required=True)
    parser.add_argument("--family-label", required=True)
    parser.add_argument("--minimum-advantage-cost", type=float, required=True)
    parser.add_argument("--prospective-plan", type=Path)
    parser.add_argument("--prospective-plan-sha256")
    parser.add_argument("--prospective-cohort-ordinal", type=int)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _write_new(rendered: str, output: Path | None) -> None:
    if output is None:
        sys.stdout.write(rendered)
        return
    resolved = output.resolve(strict=False)
    for protected in (Path("/mnt/qnap01"), Path("/srv")):
        if resolved == protected or protected in resolved.parents:
            raise ValueError(f"full-catalogue output must not be written beneath {protected}")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    except FileExistsError as error:
        raise ValueError(f"full-catalogue output already exists: {output}") from error
    except OSError as error:
        raise ValueError(f"cannot write full-catalogue output {output}: {error}") from error


def main() -> int:
    arguments = _arguments()
    document = replay_raw_full_catalogue_paired_prediction_time(
        source_path=arguments.source_artifact,
        expected_source_digest=arguments.source_artifact_sha256,
        control_indices=tuple(arguments.control_index),
        family_label=arguments.family_label,
        minimum_advantage_cost=arguments.minimum_advantage_cost,
        prospective_plan_path=arguments.prospective_plan,
        expected_prospective_plan_digest=arguments.prospective_plan_sha256,
        prospective_cohort_ordinal=arguments.prospective_cohort_ordinal,
    )
    rendered = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    _write_new(rendered, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
