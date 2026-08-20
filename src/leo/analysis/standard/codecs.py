"""Strict bounded JSON codecs for durable Standard-v2 products."""

from __future__ import annotations

import math
from typing import Any, cast

from pydantic import BaseModel

from leo.analysis.quality import QualityReportV1
from leo.analysis.standard.products import (
    CFO_ALIAS_MAP_PRODUCT,
    CFO_LIFT_REPLAY_PRODUCT,
    DEALIASED_TRAJECTORY_BANK_PRODUCT,
    DEALIASED_TRAJECTORY_BANK_V1_PRODUCT,
    FINAL_TRAJECTORY_BANK_PRODUCT,
    GLRT64_FINAL_TRAJECTORY_TABLE_PRODUCT,
    GLRT64_TRAJECTORY_TABLE_PRODUCT,
    NUMERICAL_WATERFALL_PRODUCT,
    PAIRED_REPORT_PRODUCT,
    PAIRED_REPORT_V1_PRODUCT,
    PATH_INPUT_BIND_PRODUCT,
    PATH_PRESENTATION_PRODUCT,
    PATH_REPORT_PRODUCT,
    PATH_REPORT_V1_PRODUCT,
    PILOT_SCAN_PRODUCT,
    POWER_TIMELINE_PRODUCT,
    PROBE_SCHEDULE_PRODUCT,
    QUALITY_PRODUCT,
    RADIO_REPORT_PRODUCT,
    RADIO_REPORT_V1_PRODUCT,
    TRAJECTORY_BANK_PRODUCT,
    TRAJECTORY_FEEDBACK_PRODUCT,
)
from leo.analysis.standard.reports import _polynomial_trajectory, _trajectory_family
from leo.analysis.starlink.pilot_methods import STANDARD_PILOT_METHODS, PilotMethod
from leo.analysis.starlink.trajectories import default_trajectory_bank_config
from leo.contracts.cfo_dealias import (
    CfoAliasMapV2,
    CfoLiftReplayV1,
    DealiasedTrajectoryBankV1,
    DealiasedTrajectoryBankV2,
    FinalTrajectoryBankV1,
    Glrt64FinalTrajectoryTableV1,
)
from leo.contracts.digests import canonical_json_bytes
from leo.contracts.final_trajectory_reports import (
    PairedStandardReportV2,
    PathStandardReportV2,
    RadioStandardReportV2,
)
from leo.contracts.standard_pipeline import (
    PairedStandardReportV1,
    PathStandardReportV1,
    ProbeScheduleV2,
    RadioStandardReportV1,
    StandardNumericalWaterfallV2,
    StandardPathInputBindV3,
    StandardPowerTimelineV2,
)
from leo.pipeline import ProductSpec

_MAX_PRODUCT_BYTES = 64 * 1024 * 1024
_MAX_SEQUENCE_ITEMS = 250_000
_MAX_DEPTH = 16

_MODELS: dict[tuple[str, int], type[BaseModel]] = {
    (CFO_ALIAS_MAP_PRODUCT.kind, 2): CfoAliasMapV2,
    (DEALIASED_TRAJECTORY_BANK_PRODUCT.kind, 2): DealiasedTrajectoryBankV2,
    (DEALIASED_TRAJECTORY_BANK_V1_PRODUCT.kind, 1): DealiasedTrajectoryBankV1,
    (CFO_LIFT_REPLAY_PRODUCT.kind, 1): CfoLiftReplayV1,
    (FINAL_TRAJECTORY_BANK_PRODUCT.kind, 1): FinalTrajectoryBankV1,
    (GLRT64_FINAL_TRAJECTORY_TABLE_PRODUCT.kind, 1): Glrt64FinalTrajectoryTableV1,
    (PATH_INPUT_BIND_PRODUCT.kind, 3): StandardPathInputBindV3,
    (QUALITY_PRODUCT.kind, 1): QualityReportV1,
    (POWER_TIMELINE_PRODUCT.kind, 2): StandardPowerTimelineV2,
    (NUMERICAL_WATERFALL_PRODUCT.kind, 2): StandardNumericalWaterfallV2,
    (PROBE_SCHEDULE_PRODUCT.kind, 2): ProbeScheduleV2,
    (PATH_REPORT_PRODUCT.kind, 2): PathStandardReportV2,
    (RADIO_REPORT_PRODUCT.kind, 2): RadioStandardReportV2,
    (PAIRED_REPORT_PRODUCT.kind, 2): PairedStandardReportV2,
    (PATH_REPORT_V1_PRODUCT.kind, 1): PathStandardReportV1,
    (RADIO_REPORT_V1_PRODUCT.kind, 1): RadioStandardReportV1,
    (PAIRED_REPORT_V1_PRODUCT.kind, 1): PairedStandardReportV1,
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
        "session_id",
        "stream_id",
        "radio_id",
        "receiver_id",
        "tuned_center_frequency_hz",
        "first_sample_utc_ns",
        "last_sample_utc_ns",
        "path_report_digest",
        "sample_rate_hz",
        "declared_sample_count",
        "power_timeline",
        "waterfall",
        "pilot_scan",
        "trajectory_bank",
        "trajectory_feedback",
        "trajectory_table",
        "cfo_alias_map",
        "dealiased_trajectory_bank",
        "cfo_lift_replay",
        "final_trajectory_bank",
        "final_trajectory_table",
        "candidate_only",
        "specificity_claimed",
        "payload_decoded",
    },
}

_ALGORITHMS = {
    PILOT_SCAN_PRODUCT.kind: "standard-pilot-scan-v3",
    TRAJECTORY_BANK_PRODUCT.kind: "standard-trajectory-bank-v2",
    TRAJECTORY_FEEDBACK_PRODUCT.kind: "standard-trajectory-feedback-v2",
    GLRT64_TRAJECTORY_TABLE_PRODUCT.kind: "standard-glrt64-trajectory-table-v2",
    PATH_PRESENTATION_PRODUCT.kind: "standard-path-presentation-v3",
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
    if expected is None or product.schema_version not in {1, 2, 3}:
        raise ValueError(f"no strict Standard codec for {identity!r}")
    if set(document) != expected:
        raise ValueError(f"{product.kind} JSON keys do not match its closed schema")
    if document.get("schema_version") != product.schema_version:
        raise ValueError(f"{product.kind} schema version disagrees with ProductSpec")
    expected_algorithm = (
        "standard-pilot-scan-v2"
        if product.kind == PILOT_SCAN_PRODUCT.kind and product.schema_version == 2
        else _ALGORITHMS[product.kind]
    )
    if document.get("algorithm_version") != expected_algorithm:
        raise ValueError(f"{product.kind} algorithm version is unsupported")
    for claim, expected_value in (
        ("candidate_only", True),
        ("specificity_claimed", False),
        ("payload_decoded", False),
    ):
        if document.get(claim) is not expected_value:
            raise ValueError(f"{product.kind} violates candidate-only claims")
    _validate_scientific_counts(product.kind, product.schema_version, document)
    return cast(dict[str, Any], document)


def _validate_scientific_counts(kind: str, schema_version: int, document: dict[str, Any]) -> None:
    if kind == PILOT_SCAN_PRODUCT.kind:
        _validate_pilot_scan(document, schema_version=schema_version)
    elif kind == TRAJECTORY_BANK_PRODUCT.kind:
        _validate_trajectory_bank(document)
    elif kind == TRAJECTORY_FEEDBACK_PRODUCT.kind:
        _validate_feedback(document)
    elif kind == GLRT64_TRAJECTORY_TABLE_PRODUCT.kind:
        _validate_trajectory_table(document)


_SCORE_KEYS = {
    "method",
    "exact_score",
    "control_score",
    "margin",
    "residual_cfo_hz",
    "tracking_cfo_hz",
}
_CANDIDATE_KEYS = {
    "rank",
    "local_epoch_sample",
    "acquired_cfo_hz",
    "scores",
    "qam_accuracy",
    "qam_evm",
}
_DETECTION_KEYS = {
    "status",
    "sample_start",
    "time_s",
    "local_epoch_sample",
    "acquired_cfo_hz",
    "scores",
    "qam_accuracy",
    "qam_evm",
    "reason",
    "source_candidate_count",
    "truncated_candidate_count",
    "candidates",
}


def _validate_pilot_scan(document: dict[str, Any], *, schema_version: int) -> None:
    maximum = _strict_nonnegative_int(
        document["maximum_scored_candidates_per_probe"], positive=True
    )
    sample_rate_hz = _strict_nonnegative_int(document["coarse_window_samples"], positive=True)
    subwindow_samples = _strict_nonnegative_int(document["subwindow_samples"], positive=True)
    probe_samples = _strict_nonnegative_int(document["probe_samples"], positive=True)
    if probe_samples > subwindow_samples or subwindow_samples > sample_rate_hz:
        raise ValueError("pilot window geometry is inconsistent")
    _digest(document["probe_schedule_digest"])
    methods = _array(document["methods"], "pilot methods")
    expected_methods = [
        item.value for item in (STANDARD_PILOT_METHODS if schema_version == 3 else PilotMethod)
    ]
    if methods != expected_methods:
        raise ValueError("pilot method inventory is not the frozen ordered family")
    detections = _array(document["detections"], "pilot detections")
    starts = []
    for detection in detections:
        values = _object(detection, "pilot detection")
        _exact_keys(values, _DETECTION_KEYS, "pilot detection")
        status = _string(values["status"], "pilot status")
        if status not in {"complete", "no_result", "insufficient"}:
            raise ValueError("pilot status is unsupported")
        sample_start = _strict_nonnegative_int(values["sample_start"])
        if not math.isclose(
            _number(values["time_s"], "pilot time"),
            sample_start / sample_rate_hz,
            abs_tol=1e-15,
        ):
            raise ValueError("pilot time disagrees with sample coordinate")
        reason = _string(values["reason"], "pilot reason")
        if len(reason) > 2048:
            raise ValueError("pilot reason exceeds its bound")
        candidates = _array(values["candidates"], "pilot candidates")
        if len(candidates) > maximum:
            raise ValueError("pilot candidates exceed their declared bound")
        normalized_candidates = [
            _validate_candidate(_object(item, "pilot candidate"), rank, expected_methods)
            for rank, item in enumerate(candidates)
        ]
        source = _strict_nonnegative_int(values["source_candidate_count"])
        truncated = _strict_nonnegative_int(values["truncated_candidate_count"])
        if source != len(candidates) + truncated:
            raise ValueError("pilot candidate truncation counts are inconsistent")
        top_scores = _validate_scores(values["scores"], expected_methods, allow_empty=True)
        top_epoch = _optional_nonnegative_int(values["local_epoch_sample"])
        top_cfo = _optional_number(values["acquired_cfo_hz"], "pilot CFO")
        top_accuracy = _optional_fraction(values["qam_accuracy"], "QAM accuracy")
        top_evm = _optional_nonnegative_number(values["qam_evm"], "QAM EVM")
        if normalized_candidates:
            primary = normalized_candidates[0]
            observed = (top_epoch, top_cfo, top_scores, top_accuracy, top_evm)
            if observed != primary or status != "complete":
                raise ValueError("pilot primary evidence disagrees with its first candidate")
        else:
            if status == "complete":
                raise ValueError("complete pilot detection requires a retained candidate")
            if any(
                item is not None and item != []
                for item in (top_epoch, top_cfo, top_scores, top_accuracy, top_evm)
            ):
                raise ValueError("candidate-free pilot detection has primary evidence")
        starts.append(sample_start)
    if starts != sorted(set(starts)):
        raise ValueError("pilot detections are not uniquely ordered")


def _validate_candidate(
    values: dict[str, Any], rank: int, methods: list[str]
) -> tuple[int, float, list[dict[str, Any]], float | None, float | None]:
    _exact_keys(values, _CANDIDATE_KEYS, "pilot candidate")
    if _strict_nonnegative_int(values["rank"]) != rank:
        raise ValueError("pilot candidate ranks are not canonical")
    epoch = _strict_nonnegative_int(values["local_epoch_sample"])
    cfo = _number(values["acquired_cfo_hz"], "candidate CFO")
    scores = _validate_scores(values["scores"], methods, allow_empty=False)
    accuracy = _optional_fraction(values["qam_accuracy"], "QAM accuracy")
    evm = _optional_nonnegative_number(values["qam_evm"], "QAM EVM")
    return epoch, cfo, scores, accuracy, evm


def _validate_scores(value: Any, methods: list[str], *, allow_empty: bool) -> list[dict[str, Any]]:
    scores = _array(value, "pilot scores")
    if not scores and allow_empty:
        return []
    normalized = []
    for score in scores:
        item = _object(score, "pilot score")
        _exact_keys(item, _SCORE_KEYS, "pilot score")
        method = _string(item["method"], "pilot method")
        if method not in methods:
            raise ValueError("pilot score method is undeclared")
        normalized.append(
            {
                "method": method,
                "exact_score": _number(item["exact_score"], "exact score"),
                "control_score": _optional_number(item["control_score"], "control score"),
                "margin": _number(item["margin"], "score margin"),
                "residual_cfo_hz": _number(item["residual_cfo_hz"], "residual CFO"),
                "tracking_cfo_hz": _number(item["tracking_cfo_hz"], "tracking CFO"),
            }
        )
    if [item["method"] for item in normalized] != methods:
        raise ValueError("pilot scores do not exactly cover the ordered method family")
    return normalized


def _validate_trajectory_bank(document: dict[str, Any]) -> None:
    _digest(document["pilot_scan_digest"])
    if _digest(document["config_digest"]) != default_trajectory_bank_config().digest:
        raise ValueError("trajectory bank configuration is not Standard-v2")
    _strict_nonnegative_int(document["observation_count"])
    _strict_nonnegative_int(document["truncated_trajectory_count"])
    trajectories = tuple(
        _polynomial_trajectory(_object(item, "trajectory"))
        for item in _array(document["trajectories"], "trajectories")
    )
    order = tuple(
        (item.start_s, item.end_s, item.method.value, item.polynomial_degree, item.trajectory_id)
        for item in trajectories
    )
    if order != tuple(sorted(order)) or len({item.trajectory_id for item in trajectories}) != len(
        trajectories
    ):
        raise ValueError("trajectory inventory is not unique and ordered")
    by_id = {item.trajectory_id: item for item in trajectories}
    families = tuple(
        _trajectory_family(_object(item, "trajectory family"), by_id)
        for item in _array(document["families"], "trajectory families")
    )
    if len({item.family_id for item in families}) != len(families):
        raise ValueError("trajectory families are not unique")
    family_order = tuple((item.start_s, item.end_s, item.family_id) for item in families)
    if family_order != tuple(sorted(family_order)):
        raise ValueError("trajectory families are not ordered")
    members = tuple(item for family in families for item in family.member_trajectory_ids)
    if len(members) != len(set(members)):
        raise ValueError("trajectory belongs to multiple families")
    family_by_id = {item.family_id: item for item in families}
    family_positions = {item.family_id: index for index, item in enumerate(families)}
    representatives = _array(document["replayed_representatives"], "representatives")
    representative_order = []
    for raw in representatives:
        values = _object(raw, "trajectory representative")
        if "family_id" not in values:
            raise ValueError("trajectory representative lacks family identity")
        family_id = _digest(values["family_id"])
        trajectory = _polynomial_trajectory(
            {key: value for key, value in values.items() if key != "family_id"}
        )
        family = family_by_id.get(family_id)
        if family is None or trajectory.trajectory_id not in family.member_trajectory_ids:
            raise ValueError("trajectory representative is outside its family")
        if trajectory != by_id[trajectory.trajectory_id]:
            raise ValueError("trajectory representative differs from its bank model")
        representative_order.append((family_id, trajectory.trajectory_id))
    positions = [family_positions[item[0]] for item in representative_order]
    if len(representative_order) != len(set(representative_order)) or positions != sorted(
        positions
    ):
        raise ValueError("trajectory representatives are not unique and ordered")


def _validate_feedback(document: dict[str, Any]) -> None:
    _digest(document["pilot_scan_digest"])
    _digest(document["trajectory_bank_digest"])
    identities = []
    order = []
    keys = {
        "family_id",
        "trajectory_id",
        "trajectory_method",
        "polynomial_degree",
        "sample_start",
        "time_s",
        "detector_method",
        "baseline_margin",
        "corrected_margin",
        "margin_delta",
        "corrected_residual_cfo_hz",
    }
    for raw in _array(document["results"], "trajectory feedback results"):
        row = _object(raw, "trajectory feedback row")
        _exact_keys(row, keys, "trajectory feedback row")
        family_id = _digest(row["family_id"])
        trajectory_id = _digest(row["trajectory_id"])
        trajectory_method = _pilot_method(row["trajectory_method"])
        degree = _strict_nonnegative_int(row["polynomial_degree"], positive=True)
        if degree not in {1, 2, 3}:
            raise ValueError("feedback trajectory degree is unsupported")
        sample_start = _strict_nonnegative_int(row["sample_start"])
        _nonnegative_number(row["time_s"], "feedback time")
        detector_method = _pilot_method(row["detector_method"])
        baseline = _number(row["baseline_margin"], "baseline margin")
        corrected = _number(row["corrected_margin"], "corrected margin")
        delta = _number(row["margin_delta"], "margin delta")
        if not math.isclose(delta, corrected - baseline, abs_tol=1e-15):
            raise ValueError("feedback margin delta is inconsistent")
        _number(row["corrected_residual_cfo_hz"], "corrected residual CFO")
        identities.append((trajectory_id, sample_start, detector_method))
        order.append((family_id, sample_start, detector_method, trajectory_method))
    if len(identities) != len(set(identities)) or order != sorted(order):
        raise ValueError("feedback rows are not unique and ordered")


def _validate_trajectory_table(document: dict[str, Any]) -> None:
    _digest(document["trajectory_bank_digest"])
    _digest(document["trajectory_feedback_digest"])
    if (
        document["frequency_model"]
        != "cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"
        or document["coefficient_order"] != "highest_polynomial_power_first"
        or _number(document["fit_gate_hz"], "fit gate") != 2_500.0
    ):
        raise ValueError("trajectory table model metadata is inconsistent")
    keys = {
        "trajectory_id",
        "family_id",
        "model",
        "polynomial_degree",
        "reference_time_s",
        "coefficients_hz",
        "start_s",
        "end_s",
        "duration_s",
        "point_count",
        "residual_rms_hz",
        "bic",
        "high_gate",
        "em_iterations",
        "fit_matches_well",
        "selected_for_correction",
        "corrected_glrt64_probe_count",
        "median_glrt64_margin_delta",
    }
    order = []
    for raw in _array(document["trajectories"], "trajectory table rows"):
        row = _object(raw, "trajectory table row")
        _exact_keys(row, keys, "trajectory table row")
        trajectory_id = _digest(row["trajectory_id"])
        if row["family_id"] is not None:
            _digest(row["family_id"])
        degree = _strict_nonnegative_int(row["polynomial_degree"], positive=True)
        if row["model"] != {1: "linear", 2: "quadratic", 3: "cubic"}.get(degree):
            raise ValueError("trajectory table model disagrees with degree")
        coefficients = [
            _number(item, "trajectory coefficient")
            for item in _array(row["coefficients_hz"], "trajectory coefficients")
        ]
        if len(coefficients) != degree + 1:
            raise ValueError("trajectory table coefficient count disagrees with degree")
        reference = _number(row["reference_time_s"], "trajectory reference time")
        start = _nonnegative_number(row["start_s"], "trajectory start")
        end = _nonnegative_number(row["end_s"], "trajectory end")
        duration = _nonnegative_number(row["duration_s"], "trajectory duration")
        if end < start or not math.isclose(duration, end - start, abs_tol=1e-15):
            raise ValueError("trajectory table duration is inconsistent")
        _strict_nonnegative_int(row["point_count"], positive=True)
        residual = _nonnegative_number(row["residual_rms_hz"], "trajectory RMS")
        _number(row["bic"], "trajectory BIC")
        _number(row["high_gate"], "trajectory high gate")
        _strict_nonnegative_int(row["em_iterations"])
        fit = _boolean(row["fit_matches_well"], "fit flag")
        if fit is not (residual <= 2_500.0):
            raise ValueError("trajectory fit flag disagrees with RMS")
        _boolean(row["selected_for_correction"], "correction selection")
        _strict_nonnegative_int(row["corrected_glrt64_probe_count"])
        _optional_number(row["median_glrt64_margin_delta"], "median margin delta")
        order.append((start, end, degree, trajectory_id, reference))
    if order != sorted(order) or len(order) != len(set(order)):
        raise ValueError("trajectory table rows are not unique and ordered")


def _strict_nonnegative_int(value: Any, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0):
        raise ValueError("Standard count must be a bounded nonnegative integer")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _nonnegative_number(value: Any, label: str) -> float:
    result = _number(value, label)
    if result < 0:
        raise ValueError(f"{label} must be nonnegative")
    return result


def _optional_number(value: Any, label: str) -> float | None:
    return None if value is None else _number(value, label)


def _optional_nonnegative_number(value: Any, label: str) -> float | None:
    return None if value is None else _nonnegative_number(value, label)


def _optional_fraction(value: Any, label: str) -> float | None:
    result = _optional_number(value, label)
    if result is not None and not 0 <= result <= 1:
        raise ValueError(f"{label} must lie in [0,1]")
    return result


def _optional_nonnegative_int(value: Any) -> int | None:
    return None if value is None else _strict_nonnegative_int(value)


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _digest(value: Any) -> str:
    result = _string(value, "scientific digest")
    if len(result) != 71 or not result.startswith("sha256:"):
        raise ValueError("scientific digest must be SHA-256")
    try:
        int(result[7:], 16)
    except ValueError as error:
        raise ValueError("scientific digest must be SHA-256") from error
    return result


def _pilot_method(value: Any) -> str:
    result = _string(value, "pilot method")
    try:
        PilotMethod(result)
    except ValueError as error:
        raise ValueError("pilot method is unsupported") from error
    return result


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields do not match the closed schema")


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
