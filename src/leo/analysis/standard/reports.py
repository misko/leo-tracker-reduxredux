"""Build bounded terminal path reports from durable scientific documents."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Literal

from pydantic import JsonValue

from leo.analysis.quality import QualityReportV1
from leo.analysis.standard.alternate_tracks import default_alternate_cfo_config
from leo.analysis.standard.source_bindings import verify_standard_source_bindings
from leo.analysis.starlink.pilot_methods import (
    STANDARD_PILOT_METHODS,
    PilotMethod,
    PilotProbeDetection,
    integer_epoch_detection_document,
)
from leo.analysis.starlink.trajectories import (
    PolynomialTrajectory,
    TrajectoryBankResult,
    TrajectoryFamily,
    default_trajectory_bank_config,
)
from leo.analysis.starlink.trajectory_feedback import (
    build_glrt64_trajectory_table,
    select_trajectory_representatives,
    validate_maximum_replayed_families,
)
from leo.contracts.digests import canonical_digest, canonical_json_bytes
from leo.contracts.standard_pipeline import (
    STANDARD_NUMERICAL_WATERFALL_KIND,
    STANDARD_PATH_INPUT_BIND_KIND,
    STANDARD_POWER_TIMELINE_KIND,
    STANDARD_PROBE_SCHEDULE_KIND,
    Glrt64TimelinePointV1,
    PathStandardReportV1,
    PilotCandidateV2,
    PilotMethodScoreV2,
    PilotProbeCertificateV2,
    ProbeScheduleV2,
    ReceiverFrequencyReferenceV1,
    StandardNumericalWaterfallV2,
    StandardPathInputBindV3,
    StandardPowerTimelineV2,
    StandardProductRefV1,
    StandardScientificStatus,
    StandardTrajectoryV1,
    StreamTimingEvidenceV1,
)


@dataclass(frozen=True, slots=True)
class PathReportInputs:
    input_bind: StandardPathInputBindV3
    schedule: ProbeScheduleV2
    quality_clipping_abs_threshold: int
    power_window_samples: int
    waterfall_config_digest: str
    maximum_scored_candidates_per_probe: int
    maximum_replayed_families: int

    @property
    def session_id(self) -> str:
        return self.input_bind.session_id

    @property
    def stream_id(self) -> str:
        return self.input_bind.stream_id

    @property
    def radio_id(self) -> str:
        return self.input_bind.radio_id

    @property
    def receiver_id(self) -> int:
        return self.input_bind.receiver_id

    @property
    def manifest_digest(self) -> str:
        return self.input_bind.manifest_digest

    @property
    def synchronization_inventory_digest(self) -> str:
        return self.input_bind.synchronization_inventory_digest

    @property
    def sample_rate_hz(self) -> int:
        return self.input_bind.sample_rate_hz

    @property
    def declared_sample_count(self) -> int:
        return self.input_bind.declared_sample_count

    @property
    def timing(self) -> StreamTimingEvidenceV1:
        return self.input_bind.timing

    @property
    def frequency_reference(self) -> ReceiverFrequencyReferenceV1:
        return self.input_bind.frequency_reference


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
    source_binding_documents: dict[str, dict[str, Any]],
) -> PathStandardProducts:
    """Bind separately computed stages into one honest path product.

    The builder performs no IQ or product-store access. Callers must pass the
    exact durable documents authorized by the expanded plan.
    """

    validate_maximum_replayed_families(inputs.maximum_replayed_families)
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

    for document in (
        quality_document,
        power_document,
        waterfall_document,
        pilot_document,
        trajectory_document,
        feedback_document,
        trajectory_table_document,
    ):
        _assert_finite_numbers(document)
    source_documents = {
        "quality.summary": quality_document,
        STANDARD_POWER_TIMELINE_KIND: power_document,
        STANDARD_NUMERICAL_WATERFALL_KIND: waterfall_document,
        STANDARD_PROBE_SCHEDULE_KIND: inputs.schedule.model_dump(mode="json"),
        "standard.pilot-scan": pilot_document,
        "standard.trajectory-bank": trajectory_document,
        "standard.trajectory-feedback": feedback_document,
        "standard.glrt64-trajectory-table": trajectory_table_document,
    }
    verify_standard_source_bindings(
        inputs.input_bind,
        source_documents,
        source_binding_documents,
    )
    quality = QualityReportV1.model_validate(quality_document)
    power = StandardPowerTimelineV2.model_validate(power_document)
    waterfall = StandardNumericalWaterfallV2.model_validate(waterfall_document)
    observed = _validate_observability(inputs, quality, power, waterfall)

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
    _validate_pilot_document(inputs, pilot_document, certificates, method_names)
    expected_methods = {
        score.method
        for certificate in certificates
        for candidate in certificate.candidates
        for score in candidate.method_scores
    }
    if expected_methods and set(method_names) != expected_methods:
        raise ValueError("pilot document method inventory disagrees with candidates")
    initial = tuple(_glrt64_point(item) for item in certificates)
    trajectories = _validate_trajectory_documents(
        inputs,
        certificates,
        method_names,
        pilot_document,
        trajectory_document,
        feedback_document,
        trajectory_table_document,
    )
    degrees = {item.polynomial_degree for item in trajectories}
    if trajectories and not degrees.issubset({1, 2, 3}):
        raise ValueError("path report contains an unsupported trajectory degree")

    truncated_candidates = sum(item.truncated_candidate_count for item in certificates)
    truncated_trajectories = _integer(trajectory_document, "truncated_trajectory_count", default=0)
    product_refs = tuple(
        sorted(
            (
                _product_ref(
                    STANDARD_PATH_INPUT_BIND_KIND,
                    "standard-path-input-bind.v2",
                    inputs.input_bind.model_dump(mode="json"),
                    1,
                ),
                _product_ref(
                    STANDARD_PROBE_SCHEDULE_KIND,
                    "standard-probe-schedule.v1",
                    inputs.schedule.model_dump(mode="json"),
                    inputs.schedule.returned_probe_count,
                    inputs.schedule.truncated_probe_count,
                ),
                _product_ref("quality.summary", "quality.v1", quality_document, 1),
                _product_ref(
                    STANDARD_POWER_TIMELINE_KIND,
                    "standard-power-timeline.v2",
                    power_document,
                    power.returned_window_count,
                    power.truncated_window_count,
                ),
                _product_ref(
                    STANDARD_NUMERICAL_WATERFALL_KIND,
                    "standard-numerical-waterfall.v2",
                    waterfall_document,
                    waterfall.time_bin_count,
                ),
                _product_ref(
                    "standard.pilot-scan",
                    "pilot-probe-certificate.v2",
                    pilot_document,
                    inputs.schedule.returned_probe_count,
                    inputs.schedule.truncated_probe_count,
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
                    "glrt64-trajectory-table.v2",
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
        schedule_truncated=bool(inputs.schedule.truncated_probe_count),
        candidate_truncated=bool(truncated_candidates),
        trajectory_truncated=bool(truncated_trajectories),
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
    probe_schedule_digest: str,
    _trajectory_schema_version: Literal[2, 3] = 2,
) -> dict[str, dict[str, Any]]:
    """Create new closed, run-independent Standard-v2 numerical documents."""

    common = {
        "schema_version": _trajectory_schema_version,
        "frequency_coordinate": "baseband_cfo_hz",
        "frequency_reference": "uncalibrated_prior",
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    pilot_document = {
        **common,
        "schema_version": 3,
        "algorithm_version": "standard-pilot-scan-v3",
        "probe_schedule_digest": probe_schedule_digest,
        "coarse_window_samples": coarse_window_samples,
        "subwindow_samples": subwindow_samples,
        "probe_samples": probe_samples,
        "maximum_scored_candidates_per_probe": maximum_scored_candidates_per_probe,
        "methods": [method.value for method in STANDARD_PILOT_METHODS],
        "detections": [integer_epoch_detection_document(item) for item in detections],
    }
    pilot_document = json.loads(canonical_json_bytes(pilot_document))
    bank_document = {
        **common,
        "algorithm_version": f"standard-trajectory-bank-v{_trajectory_schema_version}",
        "pilot_scan_digest": canonical_digest(pilot_document),
        "config_digest": bank.config_digest,
        "observation_count": bank.observation_count,
        "truncated_trajectory_count": bank.truncated_trajectory_count,
        "trajectories": [asdict(item) for item in bank.trajectories],
        "families": [asdict(item) for item in bank.families],
        "replayed_representatives": [
            {"family_id": family_id, **asdict(trajectory)}
            for family_id, trajectory in representatives
        ],
    }
    bank_document = json.loads(canonical_json_bytes(bank_document))
    feedback_document = {
        **common,
        "algorithm_version": f"standard-trajectory-feedback-v{_trajectory_schema_version}",
        "pilot_scan_digest": canonical_digest(pilot_document),
        "trajectory_bank_digest": canonical_digest(bank_document),
        "results": list(replay),
    }
    feedback_document = json.loads(canonical_json_bytes(feedback_document))
    table_document = {
        **common,
        "algorithm_version": f"standard-glrt64-trajectory-table-v{_trajectory_schema_version}",
        "trajectory_bank_digest": canonical_digest(bank_document),
        "trajectory_feedback_digest": canonical_digest(feedback_document),
        "frequency_model": ("cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"),
        "coefficient_order": "highest_polynomial_power_first",
        "fit_gate_hz": 2_500.0,
        "trajectories": build_glrt64_trajectory_table(bank, representatives, replay),
    }
    result = {
        "standard.pilot-scan": pilot_document,
        "standard.trajectory-bank": bank_document,
        "standard.trajectory-feedback": feedback_document,
        "standard.glrt64-trajectory-table": table_document,
    }
    normalized = json.loads(canonical_json_bytes(result))
    if not isinstance(normalized, dict):
        raise ValueError("Standard-v2 trajectory output must be an object")
    for document in normalized.values():
        if not isinstance(document, dict):
            raise ValueError("Standard-v2 trajectory product must be an object")
        _assert_reusable_science(document)
    return normalized


def standard_v3_trajectory_documents(
    *,
    detections: tuple[PilotProbeDetection, ...],
    bank: TrajectoryBankResult,
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    replay: tuple[dict[str, JsonValue], ...],
    coarse_window_samples: int,
    subwindow_samples: int,
    probe_samples: int,
    maximum_scored_candidates_per_probe: int,
    probe_schedule_digest: str,
) -> dict[str, dict[str, Any]]:
    """Create V3 products for residual-Hough linear segmentation and unchanged replay."""

    return standard_v2_trajectory_documents(
        detections=detections,
        bank=bank,
        representatives=representatives,
        replay=replay,
        coarse_window_samples=coarse_window_samples,
        subwindow_samples=subwindow_samples,
        probe_samples=probe_samples,
        maximum_scored_candidates_per_probe=maximum_scored_candidates_per_probe,
        probe_schedule_digest=probe_schedule_digest,
        _trajectory_schema_version=3,
    )


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


def _validate_observability(
    inputs: PathReportInputs,
    quality: QualityReportV1,
    power: StandardPowerTimelineV2,
    waterfall: StandardNumericalWaterfallV2,
) -> int:
    expected_geometry = (inputs.sample_rate_hz, inputs.declared_sample_count)
    if (quality.sample_rate_hz, quality.expected_sample_count) != expected_geometry:
        raise ValueError("quality document geometry disagrees with path")
    if (power.sample_rate_hz, power.expected_sample_count) != expected_geometry:
        raise ValueError("power document geometry disagrees with path")
    if (
        waterfall.sample_rate_hz,
        waterfall.coverage.expected_samples,
    ) != expected_geometry:
        raise ValueError("waterfall document geometry disagrees with path")
    if quality.clipping_abs_threshold != inputs.quality_clipping_abs_threshold:
        raise ValueError("quality configuration disagrees with path")
    if power.window_samples != inputs.power_window_samples:
        raise ValueError("power configuration disagrees with path")
    if waterfall.config_digest != inputs.waterfall_config_digest:
        raise ValueError("waterfall configuration disagrees with path")
    expected_receiver = (inputs.receiver_id,)
    if power.receiver_ids != expected_receiver or waterfall.receiver_ids != expected_receiver:
        raise ValueError("observability product receiver disagrees with path")
    if len(quality.receivers) != 1 or quality.receivers[0].receiver_id != inputs.receiver_id:
        raise ValueError("quality product receiver disagrees with path")

    observed = quality.observed_sample_count
    if quality.missing_sample_count != inputs.declared_sample_count - observed:
        raise ValueError("quality missing count disagrees with coverage")
    expected_fraction = (
        observed / inputs.declared_sample_count if inputs.declared_sample_count else 0.0
    )
    if not math.isclose(quality.coverage_fraction, expected_fraction, abs_tol=1e-15):
        raise ValueError("quality coverage fraction disagrees with counts")
    receiver = quality.receivers[0]
    if receiver.observed_sample_count != observed:
        raise ValueError("quality receiver coverage disagrees with report")
    if receiver.clipped_complex_sample_count > observed:
        raise ValueError("quality clipped sample count exceeds observations")
    if receiver.clipped_component_count > observed * 2:
        raise ValueError("quality clipped component count exceeds observations")
    expected_clipped_fraction = (
        receiver.clipped_complex_sample_count / observed if observed else 0.0
    )
    if not math.isclose(
        receiver.clipped_complex_fraction,
        expected_clipped_fraction,
        abs_tol=1e-15,
    ):
        raise ValueError("quality clipping fraction disagrees with counts")
    extrema = (
        receiver.minimum_i,
        receiver.maximum_i,
        receiver.minimum_q,
        receiver.maximum_q,
    )
    if observed and any(item is None for item in extrema):
        raise ValueError("observed quality product requires IQ extrema")
    if not observed and any(item is not None for item in extrema):
        raise ValueError("empty quality product cannot contain IQ extrema")

    if power.observed_sample_count != observed:
        raise ValueError("power coverage disagrees with quality")
    if waterfall.coverage.observed_samples != observed:
        raise ValueError("waterfall coverage disagrees with quality")
    if waterfall.coverage.gap_count != quality.uncovered_region_count:
        raise ValueError("waterfall gaps disagree with quality coverage")
    if bool(quality.missing_sample_count) != bool(quality.uncovered_region_count):
        raise ValueError("quality partial coverage accounting is inconsistent")
    return observed


def _validate_pilot_document(
    inputs: PathReportInputs,
    document: dict[str, Any],
    certificates: tuple[PilotProbeCertificateV2, ...],
    method_names: tuple[str, ...],
) -> None:
    _require_exact_keys(
        document,
        {
            "schema_version",
            "algorithm_version",
            "probe_schedule_digest",
            "frequency_coordinate",
            "frequency_reference",
            "candidate_only",
            "specificity_claimed",
            "payload_decoded",
            "coarse_window_samples",
            "subwindow_samples",
            "probe_samples",
            "maximum_scored_candidates_per_probe",
            "methods",
            "detections",
        },
        "pilot",
    )
    _require_standard_common(document, "standard-pilot-scan-v3", schema_version=3)
    if _sha256(document["probe_schedule_digest"]) != inputs.schedule.schedule_digest:
        raise ValueError("pilot document does not bind the exact probe schedule")
    expected_geometry = (
        inputs.sample_rate_hz,
        inputs.sample_rate_hz * inputs.schedule.subwindow_ms // 1_000,
        inputs.sample_rate_hz * inputs.schedule.probe_ms // 1_000,
        inputs.maximum_scored_candidates_per_probe,
    )
    observed_geometry = (
        _integer(document, "coarse_window_samples"),
        _integer(document, "subwindow_samples"),
        _integer(document, "probe_samples"),
        _integer(document, "maximum_scored_candidates_per_probe"),
    )
    if observed_geometry != expected_geometry:
        raise ValueError("pilot configuration disagrees with the exact schedule")
    expected_methods = tuple(item.value for item in STANDARD_PILOT_METHODS)
    if method_names != expected_methods:
        raise ValueError("pilot method inventory is not canonical")

    raw_detections = tuple(_mapping(item) for item in _list(document, "detections"))
    for raw, certificate in zip(raw_detections, certificates, strict=True):
        _require_exact_keys(
            raw,
            {
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
            },
            "pilot detection",
        )
        if certificate.returned_candidate_count > inputs.maximum_scored_candidates_per_probe:
            raise ValueError("pilot result exceeds its candidate bound")
        if certificate.status is StandardScientificStatus.COMPLETE and not certificate.candidates:
            raise ValueError("complete pilot result requires a candidate")
        if certificate.status is not StandardScientificStatus.COMPLETE and certificate.candidates:
            raise ValueError("non-complete pilot result cannot contain candidates")
        for certificate_candidate in certificate.candidates:
            if tuple(item.method for item in certificate_candidate.method_scores) != method_names:
                raise ValueError("pilot candidate method inventory is incomplete or reordered")
        raw_candidates = tuple(_mapping(item) for item in _list(raw, "candidates"))
        for raw_candidate in raw_candidates:
            _require_exact_keys(
                raw_candidate,
                {
                    "rank",
                    "local_epoch_sample",
                    "acquired_cfo_hz",
                    "scores",
                    "qam_accuracy",
                    "qam_evm",
                },
                "pilot candidate",
            )
            for score in (_mapping(item) for item in _list(raw_candidate, "scores")):
                _require_exact_keys(
                    score,
                    {
                        "method",
                        "exact_score",
                        "control_score",
                        "margin",
                        "residual_cfo_hz",
                        "tracking_cfo_hz",
                    },
                    "pilot method score",
                )
                acquired = _number(raw_candidate, "acquired_cfo_hz")
                if not math.isclose(
                    _number(score, "tracking_cfo_hz"),
                    acquired + _number(score, "residual_cfo_hz"),
                    abs_tol=1e-9,
                ):
                    raise ValueError("pilot tracking CFO disagrees with acquisition plus residual")
        if raw_candidates:
            primary = raw_candidates[0]
            for key in (
                "local_epoch_sample",
                "acquired_cfo_hz",
                "scores",
                "qam_accuracy",
                "qam_evm",
            ):
                if canonical_digest(raw[key]) != canonical_digest(primary[key]):
                    raise ValueError("pilot primary fields disagree with rank-zero candidate")
        elif (
            raw["local_epoch_sample"] is not None
            or raw["acquired_cfo_hz"] is not None
            or raw["qam_accuracy"] is not None
            or raw["qam_evm"] is not None
            or _list(raw, "scores")
        ):
            raise ValueError("candidate-free pilot result contains orphan primary evidence")


def _validate_trajectory_documents(
    inputs: PathReportInputs,
    certificates: tuple[PilotProbeCertificateV2, ...],
    method_names: tuple[str, ...],
    pilot_document: dict[str, Any],
    bank_document: dict[str, Any],
    feedback_document: dict[str, Any],
    table_document: dict[str, Any],
) -> tuple[StandardTrajectoryV1, ...]:
    _require_exact_keys(
        bank_document,
        {
            "schema_version",
            "algorithm_version",
            "pilot_scan_digest",
            "frequency_coordinate",
            "frequency_reference",
            "candidate_only",
            "specificity_claimed",
            "payload_decoded",
            "config_digest",
            "observation_count",
            "truncated_trajectory_count",
            "trajectories",
            "families",
            "replayed_representatives",
        },
        "trajectory bank",
    )
    trajectory_schema_version = _integer(bank_document, "schema_version")
    if trajectory_schema_version not in (2, 3):
        raise ValueError("trajectory bank schema version is unsupported")
    _require_standard_common(
        bank_document,
        f"standard-trajectory-bank-v{trajectory_schema_version}",
        schema_version=trajectory_schema_version,
    )
    if _sha256(bank_document["pilot_scan_digest"]) != canonical_digest(pilot_document):
        raise ValueError("trajectory bank does not bind the exact pilot product")
    expected_config_digest = (
        default_trajectory_bank_config().digest
        if trajectory_schema_version == 2
        else canonical_digest(default_alternate_cfo_config().model_dump(mode="json"))
    )
    if _string(bank_document["config_digest"]) != expected_config_digest:
        raise ValueError("trajectory configuration digest is not the Standard configuration")
    raw_trajectories = tuple(
        _polynomial_trajectory(_mapping(item)) for item in _list(bank_document, "trajectories")
    )
    trajectory_order = tuple(
        (
            item.start_s,
            item.end_s,
            item.method.value,
            item.polynomial_degree,
            item.trajectory_id,
        )
        for item in raw_trajectories
    )
    if trajectory_order != tuple(sorted(trajectory_order)):
        raise ValueError("trajectory bank is not canonically ordered")
    trajectory_by_id = {item.trajectory_id: item for item in raw_trajectories}
    if len(trajectory_by_id) != len(raw_trajectories):
        raise ValueError("trajectory bank IDs must be unique")
    raw_families = tuple(
        _trajectory_family(_mapping(item), trajectory_by_id)
        for item in _list(bank_document, "families")
    )
    if len({item.family_id for item in raw_families}) != len(raw_families):
        raise ValueError("trajectory family IDs must be unique")
    family_order = tuple((item.start_s, item.end_s, item.family_id) for item in raw_families)
    if family_order != tuple(sorted(family_order)):
        raise ValueError("trajectory families are not canonically ordered")
    member_ids = tuple(
        trajectory_id for family in raw_families for trajectory_id in family.member_trajectory_ids
    )
    if len(member_ids) != len(set(member_ids)):
        raise ValueError("a trajectory cannot belong to multiple families")
    expected_observations = sum(
        sum(score.method == PilotMethod.GLRT64.value for score in candidate.method_scores)
        for certificate in certificates
        for candidate in certificate.candidates
    )
    expected_observation_ids = {
        canonical_digest(
            {
                "sample_start": certificate.sample_start,
                "candidate_rank": candidate.rank,
                "method": score.method,
            }
        )
        for certificate in certificates
        for candidate in certificate.candidates
        for score in candidate.method_scores
        if score.method == PilotMethod.GLRT64.value
    }
    if any(
        observation_id not in expected_observation_ids
        for trajectory in raw_trajectories
        for observation_id in trajectory.observation_ids
    ):
        raise ValueError("trajectory support is outside the exact pilot candidate inventory")
    if _integer(bank_document, "observation_count") != expected_observations:
        raise ValueError("trajectory observation count disagrees with pilot candidates")
    bank = TrajectoryBankResult(
        config_digest=_string(bank_document["config_digest"]),
        trajectories=raw_trajectories,
        families=raw_families,
        observation_count=expected_observations,
        truncated_trajectory_count=_integer(bank_document, "truncated_trajectory_count"),
    )
    representatives = select_trajectory_representatives(bank, inputs.maximum_replayed_families)
    expected_representatives = [
        {"family_id": family_id, **asdict(trajectory)} for family_id, trajectory in representatives
    ]
    if canonical_json_bytes(_list(bank_document, "replayed_representatives")) != (
        canonical_json_bytes(expected_representatives)
    ):
        raise ValueError("trajectory representative inventory is not canonical")

    replay = _validate_feedback_document(
        inputs,
        certificates,
        method_names,
        feedback_document,
        representatives,
        pilot_document,
        bank_document,
    )
    _require_exact_keys(
        table_document,
        {
            "schema_version",
            "algorithm_version",
            "trajectory_bank_digest",
            "trajectory_feedback_digest",
            "frequency_coordinate",
            "frequency_reference",
            "candidate_only",
            "specificity_claimed",
            "payload_decoded",
            "frequency_model",
            "coefficient_order",
            "fit_gate_hz",
            "trajectories",
        },
        "trajectory table",
    )
    _require_standard_common(
        table_document,
        f"standard-glrt64-trajectory-table-v{trajectory_schema_version}",
        schema_version=trajectory_schema_version,
    )
    if _sha256(table_document["trajectory_bank_digest"]) != canonical_digest(
        bank_document
    ) or _sha256(table_document["trajectory_feedback_digest"]) != canonical_digest(
        feedback_document
    ):
        raise ValueError("trajectory table does not bind its exact predecessors")
    if (
        _string(table_document["frequency_model"])
        != "cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"
        or _string(table_document["coefficient_order"]) != "highest_polynomial_power_first"
        or _number(table_document, "fit_gate_hz") != 2_500.0
    ):
        raise ValueError("trajectory table model contract is inconsistent")
    expected_table = build_glrt64_trajectory_table(bank, representatives, replay)
    actual_table = _list(table_document, "trajectories")
    if canonical_json_bytes(actual_table) != canonical_json_bytes(expected_table):
        raise ValueError("trajectory table is not an exact derivation of bank and replay")
    return tuple(
        sorted(
            (_trajectory(item) for item in actual_table),
            key=lambda item: (
                item.start_s,
                item.end_s,
                item.polynomial_degree,
                item.trajectory_id,
            ),
        )
    )


def _validate_feedback_document(
    inputs: PathReportInputs,
    certificates: tuple[PilotProbeCertificateV2, ...],
    method_names: tuple[str, ...],
    document: dict[str, Any],
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    pilot_document: dict[str, Any],
    bank_document: dict[str, Any],
) -> tuple[dict[str, JsonValue], ...]:
    _require_exact_keys(
        document,
        {
            "schema_version",
            "algorithm_version",
            "pilot_scan_digest",
            "trajectory_bank_digest",
            "frequency_coordinate",
            "frequency_reference",
            "candidate_only",
            "specificity_claimed",
            "payload_decoded",
            "results",
        },
        "trajectory feedback",
    )
    trajectory_schema_version = _integer(bank_document, "schema_version")
    _require_standard_common(
        document,
        f"standard-trajectory-feedback-v{trajectory_schema_version}",
        schema_version=trajectory_schema_version,
    )
    if _sha256(document["pilot_scan_digest"]) != canonical_digest(pilot_document) or _sha256(
        document["trajectory_bank_digest"]
    ) != canonical_digest(bank_document):
        raise ValueError("trajectory feedback does not bind its exact predecessors")
    selected = {
        trajectory.trajectory_id: (family_id, trajectory)
        for family_id, trajectory in representatives
    }
    baseline = {item.sample_start: item for item in certificates}
    rows = tuple(_mapping(item) for item in _list(document, "results"))
    identities = []
    order_keys = []
    for row in rows:
        _require_exact_keys(
            row,
            {
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
            },
            "trajectory feedback row",
        )
        trajectory_id = _string(row["trajectory_id"])
        selected_item = selected.get(trajectory_id)
        if selected_item is None:
            raise ValueError("feedback row does not name a selected representative")
        family_id, trajectory = selected_item
        if (
            _string(row["family_id"]) != family_id
            or _string(row["trajectory_method"]) != trajectory.method.value
            or _integer(row, "polynomial_degree") != trajectory.polynomial_degree
        ):
            raise ValueError("feedback row disagrees with its selected trajectory")
        sample_start = _integer(row, "sample_start")
        certificate = baseline.get(sample_start)
        if certificate is None:
            raise ValueError("feedback row lies outside the exact probe schedule")
        time_s = _number(row, "time_s")
        if (
            not math.isclose(time_s, sample_start / inputs.sample_rate_hz, abs_tol=1e-15)
            or not trajectory.start_s <= time_s <= trajectory.end_s
        ):
            raise ValueError("feedback row time disagrees with trajectory coverage")
        detector_method = _string(row["detector_method"])
        if detector_method not in method_names:
            raise ValueError("feedback detector method is outside the pilot inventory")
        primary = certificate.candidates[0] if certificate.candidates else None
        original = (
            next(
                (item for item in primary.method_scores if item.method == detector_method),
                None,
            )
            if primary is not None
            else None
        )
        if original is None or not math.isclose(
            _number(row, "baseline_margin"), original.margin, abs_tol=1e-15
        ):
            raise ValueError("feedback baseline does not match the pilot certificate")
        baseline_margin = _number(row, "baseline_margin")
        corrected_margin = _number(row, "corrected_margin")
        if not math.isclose(
            _number(row, "margin_delta"),
            corrected_margin - baseline_margin,
            abs_tol=1e-15,
        ):
            raise ValueError("feedback margin delta is inconsistent")
        _number(row, "corrected_residual_cfo_hz")
        identities.append((trajectory_id, sample_start, detector_method))
        order_keys.append((family_id, sample_start, detector_method))
    if len(identities) != len(set(identities)):
        raise ValueError("feedback rows must have unique trajectory/probe/method identities")
    if order_keys != sorted(order_keys):
        raise ValueError("feedback rows must be deterministically ordered")
    return tuple(rows)


def _polynomial_trajectory(values: dict[str, Any]) -> PolynomialTrajectory:
    _require_exact_keys(
        values,
        {
            "trajectory_id",
            "method",
            "polynomial_degree",
            "reference_time_s",
            "coefficients_hz",
            "start_s",
            "end_s",
            "observation_ids",
            "point_count",
            "residual_rms_hz",
            "bic",
            "high_gate",
            "em_iterations",
            "candidate_only",
        },
        "trajectory",
    )
    if values["candidate_only"] is not True:
        raise ValueError("trajectory must remain candidate-only")
    trajectory_id = _sha256(values["trajectory_id"])
    method = PilotMethod(_string(values["method"]))
    degree = _integer(values, "polynomial_degree")
    reference_time_s = _number(values, "reference_time_s")
    coefficients_hz = tuple(_number_value(item) for item in _list(values, "coefficients_hz"))
    observation_ids = tuple(_sha256(item) for item in _list(values, "observation_ids"))
    expected_id = canonical_digest(
        {
            "method": method.value,
            "degree": degree,
            "reference_time_s": round(reference_time_s, 12),
            "coefficients_hz": [round(item, 12) for item in coefficients_hz],
            "observation_ids": list(observation_ids),
        }
    )
    if trajectory_id != expected_id:
        raise ValueError("trajectory ID does not match its exact fitted model")
    return PolynomialTrajectory(
        trajectory_id=trajectory_id,
        method=method,
        polynomial_degree=degree,
        reference_time_s=reference_time_s,
        coefficients_hz=coefficients_hz,
        start_s=_number(values, "start_s"),
        end_s=_number(values, "end_s"),
        observation_ids=observation_ids,
        point_count=_integer(values, "point_count"),
        residual_rms_hz=_number(values, "residual_rms_hz"),
        bic=_number(values, "bic"),
        high_gate=_number(values, "high_gate"),
        em_iterations=_integer(values, "em_iterations"),
    )


def _trajectory_family(
    values: dict[str, Any],
    trajectory_by_id: dict[str, PolynomialTrajectory],
) -> TrajectoryFamily:
    _require_exact_keys(
        values,
        {
            "family_id",
            "representative_trajectory_id",
            "member_trajectory_ids",
            "start_s",
            "end_s",
        },
        "trajectory family",
    )
    members = tuple(_sha256(item) for item in _list(values, "member_trajectory_ids"))
    if not members or len(members) != len(set(members)):
        raise ValueError("trajectory family members must be nonempty and unique")
    if any(item not in trajectory_by_id for item in members):
        raise ValueError("trajectory family names an unknown member")
    expected_members = tuple(
        item.trajectory_id
        for item in sorted(
            (trajectory_by_id[item] for item in members),
            key=lambda item: (
                -(item.end_s - item.start_s),
                -item.point_count,
                item.bic / item.point_count,
                item.polynomial_degree,
                item.trajectory_id,
            ),
        )
    )
    if members != expected_members:
        raise ValueError("trajectory family members are not canonically ordered")
    representative = _sha256(values["representative_trajectory_id"])
    family_id = _sha256(values["family_id"])
    if family_id != canonical_digest({"members": members}):
        raise ValueError("trajectory family ID does not match its exact members")
    if representative != members[0]:
        raise ValueError("trajectory family representative is not canonical")
    start_s = _number(values, "start_s")
    end_s = _number(values, "end_s")
    if start_s != min(trajectory_by_id[item].start_s for item in members) or end_s != max(
        trajectory_by_id[item].end_s for item in members
    ):
        raise ValueError("trajectory family extent disagrees with members")
    return TrajectoryFamily(
        family_id=family_id,
        representative_trajectory_id=representative,
        member_trajectory_ids=members,
        start_s=start_s,
        end_s=end_s,
    )


def _require_standard_common(
    document: dict[str, Any], algorithm: str, *, schema_version: int = 2
) -> None:
    if (
        _integer(document, "schema_version") != schema_version
        or _string(document["algorithm_version"]) != algorithm
        or document.get("frequency_coordinate") != "baseband_cfo_hz"
        or document.get("frequency_reference") != "uncalibrated_prior"
        or document.get("candidate_only") is not True
        or document.get("specificity_claimed") is not False
        or document.get("payload_decoded") is not False
    ):
        raise ValueError("Standard-v2 scientific document common contract is inconsistent")


def _require_standard_v2_common(document: dict[str, Any], algorithm: str) -> None:
    _require_standard_common(document, algorithm)


def _require_exact_keys(document: dict[str, Any], expected: set[str], label: str) -> None:
    if set(document) != expected:
        raise ValueError(f"{label} document fields are not the closed contract")


def _assert_finite_numbers(value: Any) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("scientific documents cannot contain NaN or infinity")
        return
    if isinstance(value, dict):
        for item in value.values():
            _assert_finite_numbers(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_finite_numbers(item)
        return
    raise ValueError("scientific document contains an unsupported value type")


def _sha256(value: Any) -> str:
    result = _string(value)
    if len(result) != 71 or not result.startswith("sha256:"):
        raise ValueError("scientific identity must be a sha256 digest")
    try:
        int(result[7:], 16)
    except ValueError as error:
        raise ValueError("scientific identity must be a sha256 digest") from error
    return result


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
    status_text = _string(values["status"])
    status = {
        "complete": StandardScientificStatus.COMPLETE,
        "no_result": StandardScientificStatus.NO_RESULT,
        "insufficient": StandardScientificStatus.INSUFFICIENT_DATA,
        "insufficient_data": StandardScientificStatus.INSUFFICIENT_DATA,
    }.get(status_text)
    if status is None:
        raise ValueError(f"unsupported pilot status: {status_text}")
    source_candidate_count = _integer(values, "source_candidate_count", default=len(candidates))
    truncated_candidate_count = _integer(values, "truncated_candidate_count", default=0)
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


def _path_status(
    observed: int,
    declared: int,
    certificates: tuple[PilotProbeCertificateV2, ...],
    trajectories: tuple[StandardTrajectoryV1, ...],
    *,
    schedule_truncated: bool,
    candidate_truncated: bool,
    trajectory_truncated: bool,
) -> tuple[StandardScientificStatus, str]:
    if observed == 0 or not certificates:
        return StandardScientificStatus.INSUFFICIENT_DATA, "insufficient IQ or probe coverage"
    if observed != declared:
        return StandardScientificStatus.PARTIAL, "partial IQ coverage; candidate evidence only"
    insufficient = sum(
        item.status is StandardScientificStatus.INSUFFICIENT_DATA for item in certificates
    )
    if insufficient == len(certificates):
        return StandardScientificStatus.INSUFFICIENT_DATA, "all pilot probes were insufficient"
    if insufficient:
        return StandardScientificStatus.PARTIAL, "some pilot probes were insufficient"
    if schedule_truncated or candidate_truncated or trajectory_truncated:
        return (
            StandardScientificStatus.PARTIAL,
            "bounded Standard analysis retained truncated evidence",
        )
    if all(item.status is StandardScientificStatus.NO_RESULT for item in certificates):
        return StandardScientificStatus.NO_RESULT, "complete bounded pilot search found no result"
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
