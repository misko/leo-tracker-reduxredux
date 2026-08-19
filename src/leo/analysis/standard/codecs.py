"""Strict bounded JSON codecs for durable Standard-v2 products."""

from __future__ import annotations

import math
from typing import Any, cast

from pydantic import BaseModel

from leo.analysis.quality import QualityReportV1
from leo.analysis.standard.products import (
    GLRT64_TRAJECTORY_TABLE_PRODUCT,
    NUMERICAL_WATERFALL_PRODUCT,
    PAIRED_REPORT_PRODUCT,
    PATH_INPUT_BIND_PRODUCT,
    PATH_PRESENTATION_PRODUCT,
    PATH_REPORT_PRODUCT,
    PILOT_SCAN_PRODUCT,
    POWER_TIMELINE_PRODUCT,
    PROBE_SCHEDULE_PRODUCT,
    QUALITY_PRODUCT,
    RADIO_REPORT_PRODUCT,
    TRAJECTORY_BANK_PRODUCT,
    TRAJECTORY_FEEDBACK_PRODUCT,
)
from leo.contracts.digests import canonical_json_bytes
from leo.contracts.standard_pipeline import (
    PairedStandardReportV1,
    PathStandardReportV1,
    ProbeScheduleV1,
    RadioStandardReportV1,
    StandardNumericalWaterfallV2,
    StandardPathInputBindV2,
    StandardPowerTimelineV2,
)
from leo.pipeline import ProductSpec

_MAX_PRODUCT_BYTES = 64 * 1024 * 1024
_MAX_SEQUENCE_ITEMS = 250_000
_MAX_DEPTH = 16

_MODELS: dict[tuple[str, int], type[BaseModel]] = {
    (PATH_INPUT_BIND_PRODUCT.kind, 2): StandardPathInputBindV2,
    (QUALITY_PRODUCT.kind, 1): QualityReportV1,
    (POWER_TIMELINE_PRODUCT.kind, 2): StandardPowerTimelineV2,
    (NUMERICAL_WATERFALL_PRODUCT.kind, 2): StandardNumericalWaterfallV2,
    (PROBE_SCHEDULE_PRODUCT.kind, 1): ProbeScheduleV1,
    (PATH_REPORT_PRODUCT.kind, 1): PathStandardReportV1,
    (RADIO_REPORT_PRODUCT.kind, 1): RadioStandardReportV1,
    (PAIRED_REPORT_PRODUCT.kind, 1): PairedStandardReportV1,
}

_EXACT_KEYS = {
    PILOT_SCAN_PRODUCT.kind: {
        "schema_version",
        "algorithm_version",
        "probe_schedule_digest",
        "coarse_window_samples",
        "subwindow_samples",
        "probe_samples",
        "maximum_scored_candidates_per_probe",
        "methods",
        "detections",
        "frequency_coordinate",
        "frequency_reference",
        "candidate_only",
        "specificity_claimed",
        "payload_decoded",
    },
    TRAJECTORY_BANK_PRODUCT.kind: {
        "schema_version",
        "algorithm_version",
        "pilot_scan_digest",
        "config_digest",
        "observation_count",
        "truncated_trajectory_count",
        "trajectories",
        "families",
        "replayed_representatives",
        "frequency_coordinate",
        "frequency_reference",
        "candidate_only",
        "specificity_claimed",
        "payload_decoded",
    },
    TRAJECTORY_FEEDBACK_PRODUCT.kind: {
        "schema_version",
        "algorithm_version",
        "pilot_scan_digest",
        "trajectory_bank_digest",
        "results",
        "frequency_coordinate",
        "frequency_reference",
        "candidate_only",
        "specificity_claimed",
        "payload_decoded",
    },
    GLRT64_TRAJECTORY_TABLE_PRODUCT.kind: {
        "schema_version",
        "algorithm_version",
        "trajectory_bank_digest",
        "trajectory_feedback_digest",
        "frequency_model",
        "coefficient_order",
        "fit_gate_hz",
        "trajectories",
        "frequency_coordinate",
        "frequency_reference",
        "candidate_only",
        "specificity_claimed",
        "payload_decoded",
    },
    PATH_PRESENTATION_PRODUCT.kind: {
        "schema_version",
        "algorithm_version",
        "path_report_digest",
        "sample_rate_hz",
        "declared_sample_count",
        "power_timeline",
        "waterfall",
        "pilot_scan",
        "trajectory_bank",
        "trajectory_feedback",
        "trajectory_table",
        "candidate_only",
        "specificity_claimed",
        "payload_decoded",
    },
}

_ALGORITHMS = {
    PILOT_SCAN_PRODUCT.kind: "standard-pilot-scan-v2",
    TRAJECTORY_BANK_PRODUCT.kind: "standard-trajectory-bank-v2",
    TRAJECTORY_FEEDBACK_PRODUCT.kind: "standard-trajectory-feedback-v2",
    GLRT64_TRAJECTORY_TABLE_PRODUCT.kind: "standard-glrt64-trajectory-table-v2",
    PATH_PRESENTATION_PRODUCT.kind: "standard-path-presentation-v1",
}


def decode_standard_product(product: ProductSpec, document: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one exact declared Standard product."""

    payload = canonical_json_bytes(document)
    if not payload or len(payload) > _MAX_PRODUCT_BYTES:
        raise ValueError("Standard JSON product exceeds its byte bound")
    _validate_json_tree(document)
    identity = (product.kind, product.schema_version)
    model = _MODELS.get(identity)
    if model is not None:
        return cast(dict[str, Any], model.model_validate_json(payload).model_dump(mode="json"))
    expected = _EXACT_KEYS.get(product.kind)
    if expected is None or product.schema_version not in {1, 2}:
        raise ValueError(f"no strict Standard codec for {identity!r}")
    if set(document) != expected:
        raise ValueError(f"{product.kind} JSON keys do not match its closed schema")
    if document.get("schema_version") != product.schema_version:
        raise ValueError(f"{product.kind} schema version disagrees with ProductSpec")
    if document.get("algorithm_version") != _ALGORITHMS[product.kind]:
        raise ValueError(f"{product.kind} algorithm version is unsupported")
    for claim, expected_value in (
        ("candidate_only", True),
        ("specificity_claimed", False),
        ("payload_decoded", False),
    ):
        if document.get(claim) is not expected_value:
            raise ValueError(f"{product.kind} violates candidate-only claims")
    _validate_scientific_counts(product.kind, document)
    return cast(dict[str, Any], document)


def _validate_scientific_counts(kind: str, document: dict[str, Any]) -> None:
    if kind == PILOT_SCAN_PRODUCT.kind:
        maximum = _strict_nonnegative_int(
            document["maximum_scored_candidates_per_probe"],
            positive=True,
        )
        methods = document["methods"]
        detections = document["detections"]
        if not isinstance(methods, list) or len(methods) != len(set(methods)):
            raise ValueError("pilot method inventory must be a unique array")
        if not isinstance(detections, list):
            raise ValueError("pilot detections must be an array")
        starts = []
        for detection in detections:
            if not isinstance(detection, dict):
                raise ValueError("pilot detection must be an object")
            candidates = detection.get("candidates")
            if not isinstance(candidates, list) or len(candidates) > maximum:
                raise ValueError("pilot candidates exceed their declared bound")
            source = _strict_nonnegative_int(detection.get("source_candidate_count"))
            truncated = _strict_nonnegative_int(detection.get("truncated_candidate_count"))
            if source != len(candidates) + truncated:
                raise ValueError("pilot candidate truncation counts are inconsistent")
            if [item.get("rank") for item in candidates if isinstance(item, dict)] != list(
                range(len(candidates))
            ):
                raise ValueError("pilot candidate ranks are not canonical")
            starts.append(_strict_nonnegative_int(detection.get("sample_start")))
        if starts != sorted(set(starts)):
            raise ValueError("pilot detections are not uniquely ordered")
    elif kind == TRAJECTORY_BANK_PRODUCT.kind:
        for field in ("observation_count", "truncated_trajectory_count"):
            _strict_nonnegative_int(document[field])
        for field in ("trajectories", "families", "replayed_representatives"):
            if not isinstance(document[field], list):
                raise ValueError(f"trajectory bank {field} must be an array")
    elif kind == TRAJECTORY_FEEDBACK_PRODUCT.kind:
        if not isinstance(document["results"], list):
            raise ValueError("trajectory feedback results must be an array")
    elif kind == GLRT64_TRAJECTORY_TABLE_PRODUCT.kind:
        if not isinstance(document["trajectories"], list):
            raise ValueError("trajectory table rows must be an array")


def _strict_nonnegative_int(value: Any, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0):
        raise ValueError("Standard count must be a bounded nonnegative integer")
    return value


def _validate_json_tree(value: Any, *, depth: int = 0) -> None:
    if depth > _MAX_DEPTH:
        raise ValueError("Standard JSON product exceeds its nesting bound")
    if isinstance(value, dict):
        if len(value) > _MAX_SEQUENCE_ITEMS or any(not isinstance(key, str) for key in value):
            raise ValueError("Standard JSON object is invalid or oversized")
        for child in value.values():
            _validate_json_tree(child, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        if len(value) > _MAX_SEQUENCE_ITEMS:
            raise ValueError("Standard JSON array exceeds its item bound")
        for child in value:
            _validate_json_tree(child, depth=depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Standard JSON numbers must be finite")
    elif isinstance(value, str) and len(value) > 4096:
        raise ValueError("Standard JSON string exceeds its bound")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError("Standard product contains a non-JSON value")
