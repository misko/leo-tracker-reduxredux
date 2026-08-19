"""Build bounded terminal path reports from durable scientific documents."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from typing import Any

from pydantic import JsonValue

from leo.analysis.starlink.pilot_methods import PilotMethod, PilotProbeDetection
from leo.analysis.starlink.trajectories import PolynomialTrajectory, TrajectoryBankResult
from leo.analysis.starlink.trajectory_feedback import build_glrt64_trajectory_table
from leo.contracts.digests import canonical_digest, canonical_json_bytes
from leo.contracts.standard_pipeline import (
    Glrt64TimelinePointV1,
    PathStandardReportV1,
    PilotCandidateV2,
    PilotMethodScoreV2,
    PilotProbeCertificateV2,
    ProbeScheduleV1,
    ReceiverFrequencyReferenceV1,
    StandardProductRefV1,
    StandardScientificStatus,
    StandardTrajectoryV1,
    StreamTimingEvidenceV1,
)


@dataclass(frozen=True, slots=True)
class PathReportInputs:
    session_id: str
    stream_id: str
    radio_id: str
    receiver_id: int
    manifest_digest: str
    synchronization_inventory_digest: str
    sample_rate_hz: int
    declared_sample_count: int
    timing: StreamTimingEvidenceV1
    frequency_reference: ReceiverFrequencyReferenceV1
    schedule: ProbeScheduleV1


@dataclass(frozen=True, slots=True)
class PathStandardProducts:
    report: PathStandardReportV1
    pilot_certificates: tuple[PilotProbeCertificateV2, ...]


def build_path_standard_report(
    inputs: PathReportInputs,
    *,
    quality_document: dict[str, Any],
    power_document: dict[str, Any],
    waterfall_document: dict[str, Any],
    pilot_document: dict[str, Any],
    trajectory_document: dict[str, Any],
    feedback_document: dict[str, Any],
    trajectory_table_document: dict[str, Any],
) -> PathStandardProducts:
    """Bind separately computed stages into one honest path product.

    The builder performs no IQ or product-store access. Callers must pass the
    exact durable documents authorized by the expanded plan.
    """

    if inputs.schedule.sample_rate_hz != inputs.sample_rate_hz:
        raise ValueError("probe schedule sample rate disagrees with path")
    if inputs.schedule.declared_sample_count != inputs.declared_sample_count:
        raise ValueError("probe schedule sample count disagrees with path")
    for document in (
        pilot_document,
        trajectory_document,
        feedback_document,
        trajectory_table_document,
    ):
        _assert_reusable_science(document)

    quality_sample_rate = _integer(quality_document, "sample_rate_hz")
    quality_expected = _integer(quality_document, "expected_sample_count")
    observed = _integer(quality_document, "observed_sample_count")
    if (
        quality_sample_rate != inputs.sample_rate_hz
        or quality_expected != inputs.declared_sample_count
    ):
        raise ValueError("quality document geometry disagrees with path")
    _require_document_geometry(power_document, inputs, "power")
    _require_waterfall_geometry(waterfall_document, inputs)

    schedule_by_start = {item.sample_start: item for item in inputs.schedule.probes}
    detections = _list(pilot_document, "detections")
    if len(detections) != len(schedule_by_start):
        raise ValueError("pilot result count disagrees with the exact probe schedule")
    certificates = tuple(
        _pilot_certificate(item, schedule_by_start, inputs.sample_rate_hz) for item in detections
    )
    certificate_starts = tuple(item.sample_start for item in certificates)
    if certificate_starts != tuple(sorted(schedule_by_start)):
        raise ValueError("pilot results do not exactly cover the ordered probe schedule")

    method_names = tuple(_string(item) for item in _list(pilot_document, "methods"))
    expected_methods = {
        score.method for certificate in certificates for candidate in certificate.candidates
        for score in candidate.method_scores
    }
    if expected_methods and set(method_names) != expected_methods:
        raise ValueError("pilot document method inventory disagrees with candidates")
    initial = tuple(_glrt64_point(item) for item in certificates)
    trajectories = tuple(
        sorted(
            (_trajectory(item) for item in _list(trajectory_table_document, "trajectories")),
            key=lambda item: (item.start_s, item.end_s, item.polynomial_degree, item.trajectory_id),
        )
    )
    degrees = {item.polynomial_degree for item in trajectories}
    if trajectories and not degrees.issubset({1, 2, 3}):
        raise ValueError("path report contains an unsupported trajectory degree")

    truncated_candidates = sum(item.truncated_candidate_count for item in certificates)
    truncated_trajectories = _integer(
        trajectory_document, "truncated_trajectory_count", default=0
    )
    product_refs = tuple(
        sorted(
            (
                _product_ref("quality.summary", "quality.v1", quality_document, 1),
                _product_ref(
                    "power.summary",
                    "power.v1",
                    power_document,
                    _power_points(power_document),
                ),
                _product_ref(
                    "waterfall.tiles",
                    "waterfall.v1",
                    waterfall_document,
                    len(_list(waterfall_document, "tiles")),
                ),
                _product_ref(
                    "standard.pilot-scan",
                    "pilot-probe-certificate.v2",
                    pilot_document,
                    len(certificates),
                    truncated_candidates,
                ),
                _product_ref(
                    "standard.trajectory-bank",
                    "trajectory-bank.v2",
                    trajectory_document,
                    len(_list(trajectory_document, "trajectories")),
                    truncated_trajectories,
                ),
                _product_ref(
                    "standard.trajectory-feedback",
                    "trajectory-feedback.v2",
                    feedback_document,
                    len(_list(feedback_document, "results")),
                ),
                _product_ref(
                    "standard.glrt64-trajectory-table",
                    "glrt64-trajectory-table.v1",
                    trajectory_table_document,
                    len(trajectories),
                ),
            ),
            key=lambda item: (item.kind, item.contract_schema),
        )
    )
    status, reason = _path_status(
        observed,
        inputs.declared_sample_count,
        certificates,
        trajectories,
    )
    values: dict[str, Any] = {
        "schema_version": 1,
        "session_id": inputs.session_id,
        "stream_id": inputs.stream_id,
        "radio_id": inputs.radio_id,
        "receiver_id": inputs.receiver_id,
        "manifest_digest": inputs.manifest_digest,
        "synchronization_inventory_digest": inputs.synchronization_inventory_digest,
        "pipeline_family": "standard-glrt64-v2",
        "status": status,
        "reason": reason,
        "sample_rate_hz": inputs.sample_rate_hz,
        "declared_sample_count": inputs.declared_sample_count,
        "observed_sample_count": observed,
        "coverage_fraction": (
            observed / inputs.declared_sample_count if inputs.declared_sample_count else 0.0
        ),
        "timing": inputs.timing.model_dump(mode="json"),
        "frequency_reference": inputs.frequency_reference.model_dump(mode="json"),
        "probe_schedule_digest": inputs.schedule.schedule_digest,
        "method_names": method_names,
        "initial_glrt64": [item.model_dump(mode="json") for item in initial],
        "trajectories": [item.model_dump(mode="json") for item in trajectories],
        "products": [item.model_dump(mode="json") for item in product_refs],
        "truncated_candidate_count": truncated_candidates,
        "truncated_trajectory_count": truncated_trajectories,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return PathStandardProducts(
        report=PathStandardReportV1(**values, report_digest=canonical_digest(values)),
        pilot_certificates=certificates,
    )


def reusable_trajectory_documents(
    documents: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Project legacy analyzer output into stable v2 reusable scientific bytes."""

    mapping = {
        "starlink.pilot-method-detections": (
            "standard.pilot-scan",
            "standard-pilot-scan-v2",
        ),
        "starlink.polynomial-trajectories": (
            "standard.trajectory-bank",
            "standard-trajectory-bank-v2",
        ),
        "starlink.trajectory-redetection": (
            "standard.trajectory-feedback",
            "standard-trajectory-feedback-v2",
        ),
        "starlink.glrt64-trajectory-table": (
            "standard.glrt64-trajectory-table",
            "standard-glrt64-trajectory-table-v2",
        ),
    }
    if set(documents) != set(mapping):
        raise ValueError("trajectory document set is incomplete or contains an undeclared product")
    result = {}
    for old_kind, (new_kind, algorithm_version) in mapping.items():
        source = documents[old_kind]
        stable = {
            key: value
            for key, value in source.items()
            if key not in {"run_id", "scope_key", "pipeline_release", "pipeline_release_id"}
        }
        stable["schema_version"] = 2
        stable["algorithm_version"] = algorithm_version
        normalized = json.loads(canonical_json_bytes(stable))
        if not isinstance(normalized, dict):
            raise ValueError("reusable scientific output must be an object")
        _assert_reusable_science(normalized)
        result[new_kind] = normalized
    return result


def standard_v2_trajectory_documents(
    *,
    detections: tuple[PilotProbeDetection, ...],
    bank: TrajectoryBankResult,
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    replay: tuple[dict[str, JsonValue], ...],
    coarse_window_samples: int,
    subwindow_samples: int,
    probe_samples: int,
    maximum_scored_candidates_per_probe: int,
) -> dict[str, dict[str, Any]]:
    """Create new closed, run-independent Standard-v2 numerical documents."""

    common = {
        "schema_version": 2,
        "frequency_coordinate": "baseband_cfo_hz",
        "frequency_reference": "uncalibrated_prior",
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    result = {
        "standard.pilot-scan": {
            **common,
            "algorithm_version": "standard-pilot-scan-v2",
            "coarse_window_samples": coarse_window_samples,
            "subwindow_samples": subwindow_samples,
            "probe_samples": probe_samples,
            "maximum_scored_candidates_per_probe": maximum_scored_candidates_per_probe,
            "methods": [method.value for method in PilotMethod],
            "detections": [asdict(item) for item in detections],
        },
        "standard.trajectory-bank": {
            **common,
            "algorithm_version": "standard-trajectory-bank-v2",
            "config_digest": bank.config_digest,
            "observation_count": bank.observation_count,
            "truncated_trajectory_count": bank.truncated_trajectory_count,
            "trajectories": [asdict(item) for item in bank.trajectories],
            "families": [asdict(item) for item in bank.families],
            "replayed_representatives": [
                {"family_id": family_id, **asdict(trajectory)}
                for family_id, trajectory in representatives
            ],
        },
        "standard.trajectory-feedback": {
            **common,
            "algorithm_version": "standard-trajectory-feedback-v2",
            "results": list(replay),
        },
        "standard.glrt64-trajectory-table": {
            **common,
            "algorithm_version": "standard-glrt64-trajectory-table-v2",
            "frequency_model": (
                "cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"
            ),
            "coefficient_order": "highest_polynomial_power_first",
            "fit_gate_hz": 2_500.0,
            "trajectories": build_glrt64_trajectory_table(bank, representatives, replay),
        },
    }
    normalized = json.loads(canonical_json_bytes(result))
    if not isinstance(normalized, dict):
        raise ValueError("Standard-v2 trajectory output must be an object")
    for document in normalized.values():
        if not isinstance(document, dict):
            raise ValueError("Standard-v2 trajectory product must be an object")
        _assert_reusable_science(document)
    return normalized


def _assert_reusable_science(document: dict[str, Any]) -> None:
    forbidden = {"run_id", "job_id", "scope_key", "pipeline_release", "pipeline_release_id"}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            overlap = forbidden & set(value)
            if overlap:
                raise ValueError(f"reusable scientific bytes contain run membership: {overlap}")
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(document)


def _require_document_geometry(
    document: dict[str, Any], inputs: PathReportInputs, label: str
) -> None:
    if _integer(document, "sample_rate_hz") != inputs.sample_rate_hz:
        raise ValueError(f"{label} sample rate disagrees with path")
    if _integer(document, "expected_sample_count") != inputs.declared_sample_count:
        raise ValueError(f"{label} sample count disagrees with path")


def _require_waterfall_geometry(document: dict[str, Any], inputs: PathReportInputs) -> None:
    if _integer(document, "sample_rate_hz") != inputs.sample_rate_hz:
        raise ValueError("waterfall sample rate disagrees with path")
    receiver_ids = tuple(_integer_value(item) for item in _list(document, "receiver_ids"))
    if receiver_ids != (inputs.receiver_id,):
        raise ValueError("waterfall must represent exactly the requested receiver")


def _pilot_certificate(
    document: Any,
    schedule_by_start: dict[int, Any],
    sample_rate_hz: int,
) -> PilotProbeCertificateV2:
    values = _mapping(document)
    sample_start = _integer(values, "sample_start")
    scheduled = schedule_by_start.get(sample_start)
    if scheduled is None:
        raise ValueError("pilot result is not part of the exact schedule")
    if not math.isclose(_number(values, "time_s"), scheduled.time_s, abs_tol=1e-15):
        raise ValueError("pilot result time disagrees with its sample coordinate")
    raw_candidates = values.get("candidates", [])
    if not isinstance(raw_candidates, (list, tuple)):
        raise ValueError("pilot candidates must be an array")
    candidates = tuple(_pilot_candidate(_mapping(item)) for item in raw_candidates)
    if not candidates:
        scores = _pilot_scores(values)
        epoch = values.get("local_epoch_sample")
        acquired = values.get("acquired_cfo_hz")
        if scores:
            if epoch is None or acquired is None:
                raise ValueError("scored pilot result requires epoch and acquired CFO")
            candidates = (
                PilotCandidateV2(
                    rank=0,
                    local_epoch_sample=_integer_value(epoch),
                    acquired_baseband_cfo_hz=_number_value(acquired),
                    method_scores=scores,
                    qam_accuracy=_optional_number(values.get("qam_accuracy")),
                    qam_evm=_optional_number(values.get("qam_evm")),
                ),
            )
    status_text = _string(values["status"])
    status = {
        "complete": StandardScientificStatus.COMPLETE,
        "no_result": StandardScientificStatus.NO_RESULT,
        "insufficient": StandardScientificStatus.INSUFFICIENT_DATA,
        "insufficient_data": StandardScientificStatus.INSUFFICIENT_DATA,
    }.get(status_text)
    if status is None:
        raise ValueError(f"unsupported pilot status: {status_text}")
    source_candidate_count = _integer(
        values, "source_candidate_count", default=len(candidates)
    )
    truncated_candidate_count = _integer(
        values, "truncated_candidate_count", default=0
    )
    if not raw_candidates and candidates and source_candidate_count == 0:
        source_candidate_count = len(candidates)
        truncated_candidate_count = 0
    return PilotProbeCertificateV2(
        probe_id=scheduled.probe_id,
        sample_start=sample_start,
        time_s=sample_start / sample_rate_hz,
        status=status,
        source_candidate_count=source_candidate_count,
        returned_candidate_count=len(candidates),
        truncated_candidate_count=truncated_candidate_count,
        candidates=candidates,
        reason=_string(values["reason"]),
    )


def _pilot_candidate(values: dict[str, Any]) -> PilotCandidateV2:
    return PilotCandidateV2(
        rank=_integer(values, "rank"),
        local_epoch_sample=_integer(values, "local_epoch_sample"),
        acquired_baseband_cfo_hz=_number(values, "acquired_cfo_hz"),
        method_scores=_pilot_scores(values),
        qam_accuracy=_optional_number(values.get("qam_accuracy")),
        qam_evm=_optional_number(values.get("qam_evm")),
    )


def _pilot_scores(values: dict[str, Any]) -> tuple[PilotMethodScoreV2, ...]:
    return tuple(
        PilotMethodScoreV2(
            method=_string(score["method"]),
            exact_score=_number(score, "exact_score"),
            control_score=_optional_number(score.get("control_score")),
            margin=_number(score, "margin"),
            tracking_cfo_hz=_number(score, "tracking_cfo_hz"),
        )
        for score in (_mapping(item) for item in _list(values, "scores"))
    )


def _glrt64_point(certificate: PilotProbeCertificateV2) -> Glrt64TimelinePointV1:
    candidate = certificate.candidates[0] if certificate.candidates else None
    glrt64 = (
        next((item for item in candidate.method_scores if item.method == "glrt64"), None)
        if candidate is not None
        else None
    )
    return Glrt64TimelinePointV1(
        probe_id=certificate.probe_id,
        sample_start=certificate.sample_start,
        time_s=certificate.time_s,
        baseband_cfo_hz=None if glrt64 is None else glrt64.tracking_cfo_hz,
        initial_margin=None if glrt64 is None else glrt64.margin,
        qam_accuracy=None if candidate is None else candidate.qam_accuracy,
    )


def _trajectory(document: Any) -> StandardTrajectoryV1:
    values = _mapping(document)
    return StandardTrajectoryV1(
        trajectory_id=_string(values["trajectory_id"]),
        family_id=_optional_string(values.get("family_id")),
        method="glrt64",
        polynomial_degree=_integer(values, "polynomial_degree"),
        reference_time_s=_number(values, "reference_time_s"),
        coefficients_hz=tuple(_number_value(item) for item in _list(values, "coefficients_hz")),
        start_s=_number(values, "start_s"),
        end_s=_number(values, "end_s"),
        point_count=_integer(values, "point_count"),
        residual_rms_hz=_number(values, "residual_rms_hz"),
        bic=_number(values, "bic"),
        em_iterations=_integer(values, "em_iterations"),
        fit_matches_well=_boolean(values, "fit_matches_well"),
        selected_for_correction=_boolean(values, "selected_for_correction"),
        corrected_glrt64_probe_count=_integer(values, "corrected_glrt64_probe_count"),
        median_glrt64_margin_delta=_optional_number(values.get("median_glrt64_margin_delta")),
    )


def _product_ref(
    kind: str,
    schema: str,
    document: dict[str, Any],
    returned: int,
    truncated: int = 0,
) -> StandardProductRefV1:
    return StandardProductRefV1(
        kind=kind,
        contract_schema=schema,
        content_digest=canonical_digest(document),
        source_point_count=returned + truncated,
        returned_point_count=returned,
        truncated_point_count=truncated,
    )


def _power_points(document: dict[str, Any]) -> int:
    timeline = document.get("timeline")
    if timeline is None:
        return len(_list(document, "receivers"))
    return len(_list_value(timeline))


def _path_status(
    observed: int,
    declared: int,
    certificates: tuple[PilotProbeCertificateV2, ...],
    trajectories: tuple[StandardTrajectoryV1, ...],
) -> tuple[StandardScientificStatus, str]:
    if observed == 0 or not certificates:
        return StandardScientificStatus.INSUFFICIENT_DATA, "insufficient IQ or probe coverage"
    if observed != declared:
        return StandardScientificStatus.PARTIAL, "partial IQ coverage; candidate evidence only"
    if not trajectories:
        return (
            StandardScientificStatus.NO_RESULT,
            "complete bounded search produced no retained trajectory",
        )
    return (
        StandardScientificStatus.COMPLETE,
        "complete bounded Standard analysis; candidate-only and no payload was decoded",
    )


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("scientific document item must be an object")
    return value


def _list(document: dict[str, Any], key: str) -> list[Any]:
    if key not in document:
        raise ValueError(f"scientific document is missing {key}")
    return _list_value(document[key])


def _list_value(value: Any) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("scientific document value must be an array")
    return list(value)


def _string(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("scientific document value must be a nonempty string")
    return value


def _optional_string(value: Any) -> str | None:
    return None if value is None else _string(value)


def _integer(document: dict[str, Any], key: str, *, default: int | None = None) -> int:
    if key not in document:
        if default is None:
            raise ValueError(f"scientific document is missing {key}")
        return default
    return _integer_value(document[key])


def _integer_value(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("scientific document value must be an integer")
    return value


def _number(document: dict[str, Any], key: str) -> float:
    if key not in document:
        raise ValueError(f"scientific document is missing {key}")
    return _number_value(document[key])


def _number_value(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("scientific document value must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("scientific document number must be finite")
    return result


def _optional_number(value: Any) -> float | None:
    return None if value is None else _number_value(value)


def _boolean(document: dict[str, Any], key: str) -> bool:
    value = document.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"scientific document {key} must be boolean")
    return value
