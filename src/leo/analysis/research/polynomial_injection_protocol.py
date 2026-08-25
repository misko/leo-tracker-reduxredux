"""Strict preregistration loader for real-background polynomial injection."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leo.analysis.research.doppler_dataset_policy import (
    DopplerDatasetPolicy,
    authorize_capture,
)

SCHEMA = "org.leo.research.polynomial-phase-injection-protocol/v1"

_TOP_LEVEL_KEYS = {
    "schema",
    "protocol_status",
    "basis_repository_commit",
    "input_authority",
    "backgrounds",
    "span_selection",
    "signal_model",
    "estimator_model",
    "metrics",
    "promotion_gates",
    "balanced_design",
    "interpretation_limits",
}
_AUTHORITY_KEYS = {
    "dataset_policy_path",
    "dataset_policy_sha256",
    "experiment_role",
    "dynamic_discovery_forbidden",
    "capture_substitution_forbidden",
}
_BACKGROUND_KEYS = {
    "session_id",
    "recording_manifest_path",
    "recording_manifest_sha256",
    "analysis_run_id",
    "analysis_manifest_path",
    "analysis_manifest_sha256",
    "stream_id",
    "radio_id",
    "radio_serial",
    "receiver_id",
    "sample_rate_hz",
    "sample_start",
    "sample_count",
    "chunk",
}
_CHUNK_KEYS = {
    "chunk_index",
    "sample_start",
    "sample_count",
    "relative_path",
    "compressed_sha256",
    "uncompressed_sha256",
}
_SCENARIO_KEYS = {
    "scenario_id",
    "background_session_id",
    "seed",
    "rate_hz_s",
    "acceleration_hz_s2",
    "jerk_hz_s3",
    "snr_db",
    "frame_occupancy",
    "alias_change_hz",
    "cfo_step_hz",
    "sample_clock_offset_ppm",
}
_HISTORY_KEYS = {"name", "history_s", "minimum_frames", "minimum_effective_frames"}
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_QIN_TEMPLATE_SHA256 = "sha256:15455635bcdcfe0747f686ae317d235b5dfa54ae49c76b9741e6acc889d8a657"


@dataclass(frozen=True, slots=True)
class ChunkBinding:
    """One sealed compressed CI16 chunk containing an entire selected span."""

    chunk_index: int
    sample_start: int
    sample_count: int
    relative_path: str
    compressed_sha256: str
    uncompressed_sha256: str


@dataclass(frozen=True, slots=True)
class BackgroundSpan:
    """One exact authorized real-background span."""

    session_id: str
    recording_manifest_path: Path
    recording_manifest_sha256: str
    analysis_run_id: str
    analysis_manifest_path: Path
    analysis_manifest_sha256: str
    stream_id: str
    radio_id: str
    radio_serial: str
    receiver_id: int
    sample_rate_hz: int
    sample_start: int
    sample_count: int
    chunk: ChunkBinding


@dataclass(frozen=True, slots=True)
class InjectionScenario:
    """One explicitly frozen row of the balanced truth design."""

    scenario_id: str
    background_session_id: str
    seed: int
    rate_hz_s: float
    acceleration_hz_s2: float
    jerk_hz_s3: float
    snr_db: float
    frame_occupancy: float
    alias_change_hz: float
    cfo_step_hz: float
    sample_clock_offset_ppm: float


@dataclass(frozen=True, slots=True)
class HistoryEstimator:
    """One preregistered causal fixed-history line estimator."""

    name: str
    history_s: float
    minimum_frames: int
    minimum_effective_frames: float


@dataclass(frozen=True, slots=True)
class PolynomialInjectionProtocol:
    """Validated, immutable experiment protocol."""

    basis_repository_commit: str
    dataset_policy_path: Path
    dataset_policy_sha256: str
    backgrounds: tuple[BackgroundSpan, ...]
    scenarios: tuple[InjectionScenario, ...]
    duration_s: float
    frame_rate_hz: int
    frame_count: int
    carrier_origin_hz: float
    reference_time_s: float
    alias_change_time_s: float
    cfo_step_time_s: float
    frame_cfo_search_half_width_hz: float
    profile_step_hz: float
    minimum_exact_coherence: float
    minimum_coherence_margin: float
    fixed_measurement_sigma_hz: float
    histories: tuple[HistoryEstimator, ...]
    minimum_history_coverage: float
    maximum_gap_s: float
    huber_tuning: float
    maximum_iterations: int
    prediction_convergence_hz: float
    consistency_chi_square: float
    standardized_scale_floor: float
    maximum_normal_condition: float
    diagnostic_minimum_frames: int
    confidence_level: float
    step_transition_exclusion_s: float
    rate_failure_absolute_error_hz_s: float
    acceleration_failure_absolute_error_hz_s2: float
    jerk_failure_absolute_error_hz_s3: float

    def background(self, session_id: str) -> BackgroundSpan:
        for background in self.backgrounds:
            if background.session_id == session_id:
                return background
        raise ValueError(f"scenario references an unbound background: {session_id}")


def load_polynomial_injection_protocol(
    path: Path,
    *,
    dataset_policy: DopplerDatasetPolicy,
    repository_root: Path,
) -> PolynomialInjectionProtocol:
    """Load the frozen protocol and bind it to the reviewed dataset policy."""

    document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    root = _mapping(document, "protocol")
    _exact_keys(root, _TOP_LEVEL_KEYS, "protocol")
    if root["schema"] != SCHEMA:
        raise ValueError("unsupported polynomial-injection protocol schema")
    if root["protocol_status"] != "frozen_before_scoring":
        raise ValueError("protocol was not frozen before scoring")
    basis_commit = _matching_string(
        root["basis_repository_commit"], _COMMIT_RE, "basis_repository_commit"
    )

    authority = _mapping(root["input_authority"], "input_authority")
    _exact_keys(authority, _AUTHORITY_KEYS, "input_authority")
    if authority["experiment_role"] != "polynomial_injection":
        raise ValueError("protocol uses the wrong dataset role")
    for name in ("dynamic_discovery_forbidden", "capture_substitution_forbidden"):
        if authority[name] is not True:
            raise ValueError(f"input_authority.{name} must be true")
    policy_relative_path = _relative_path(authority["dataset_policy_path"], "dataset policy")
    policy_path = repository_root / policy_relative_path
    policy_digest = _matching_string(
        authority["dataset_policy_sha256"], _SHA256_RE, "dataset_policy_sha256"
    )
    if _sha256(policy_path) != policy_digest:
        raise ValueError("dataset policy bytes differ from the frozen protocol")

    role = dataset_policy.role("polynomial_injection")
    background_documents = _sequence(root["backgrounds"], "backgrounds")
    backgrounds = tuple(
        _load_background(item, dataset_policy=dataset_policy, duration_s=2.0)
        for item in background_documents
    )
    background_ids = tuple(item.session_id for item in backgrounds)
    if background_ids != role.capture_ids:
        raise ValueError("background order or membership differs from the role allowlist")

    span_selection = _mapping(root["span_selection"], "span_selection")
    _exact_keys(
        span_selection,
        {"selection_basis", "justification", "raw_iq_opened_before_freeze"},
        "span_selection",
    )
    if span_selection["selection_basis"] != "metadata_only_pre_response":
        raise ValueError("background spans were not selected response-blind")
    _nonempty_string(span_selection["justification"], "span_selection.justification")
    if span_selection["raw_iq_opened_before_freeze"] is not False:
        raise ValueError("protocol must attest that IQ remained closed before freeze")

    signal = _mapping(root["signal_model"], "signal_model")
    _exact_keys(
        signal,
        {
            "duration_s",
            "frame_rate_hz",
            "frame_start_formula",
            "frame_count",
            "template_function",
            "template_edge",
            "template_sample_count",
            "template_sha256",
            "template_digest_serialization",
            "template_placement",
            "occupancy_model",
            "carrier_origin_hz",
            "reference_time_s",
            "alias_change_time_s",
            "cfo_step_time_s",
            "snr_definition",
            "sample_clock_model",
        },
        "signal_model",
    )
    duration_s = _positive_float(signal["duration_s"], "duration_s")
    frame_rate_hz = _positive_int(signal["frame_rate_hz"], "frame_rate_hz")
    frame_count = _positive_int(signal["frame_count"], "frame_count")
    if signal["frame_start_formula"] != "round(10000*k/3)":
        raise ValueError("frame lattice is not the frozen 3333/3334 schedule")
    if frame_rate_hz != 750 or frame_count != 1500:
        raise ValueError("frame count and rate disagree with the frozen two-second lattice")
    if (
        signal["template_function"] != ("leo.analysis.starlink.templates.qin_edge_pilot_frame")
        or signal["template_edge"] != "lower"
    ):
        raise ValueError("primary injection must use the repository exact lower-edge Qin template")
    if _positive_int(signal["template_sample_count"], "template_sample_count") != 3333:
        raise ValueError("Qin template must contain exactly 3333 samples")
    template_digest = _matching_string(signal["template_sha256"], _SHA256_RE, "template_sha256")
    if template_digest != _QIN_TEMPLATE_SHA256:
        raise ValueError("Qin template digest differs from preregistration")
    if signal["template_digest_serialization"] != (
        "leo.analysis.starlink.templates.template_sha256 canonical little-endian complex64 bytes"
    ):
        raise ValueError("Qin template digest serialization differs from preregistration")
    for name in (
        "template_placement",
        "occupancy_model",
        "snr_definition",
        "sample_clock_model",
    ):
        _nonempty_string(signal[name], f"signal_model.{name}")
    carrier_origin_hz = _finite_float(signal["carrier_origin_hz"], "carrier_origin_hz")
    reference_time_s = _finite_float(signal["reference_time_s"], "reference_time_s")
    alias_change_time_s = _finite_float(signal["alias_change_time_s"], "alias_change_time_s")
    cfo_step_time_s = _finite_float(signal["cfo_step_time_s"], "cfo_step_time_s")
    if not 0.0 < reference_time_s < duration_s:
        raise ValueError("reference time must be inside the injection")
    if not 0.0 < alias_change_time_s < duration_s:
        raise ValueError("alias event must be inside the injection")
    if not 0.0 < cfo_step_time_s < duration_s:
        raise ValueError("CFO step must be inside the injection")

    estimator = _mapping(root["estimator_model"], "estimator_model")
    _exact_keys(
        estimator,
        {
            "timing_and_coarse_carrier_known",
            "coarse_seed_policy",
            "alias_change_known_and_canonicalized",
            "frame_cfo_method",
            "residual_half_width_hz",
            "profile_step_hz",
            "minimum_exact_coherence",
            "minimum_coherence_margin",
            "fixed_measurement_sigma_hz",
            "odd_qin_may_influence_training",
            "even_rolled_control_is_training_gate",
            "odd_rolled_control_may_influence_training",
            "history_estimators",
            "minimum_history_coverage",
            "maximum_gap_s",
            "huber_tuning",
            "maximum_iterations",
            "prediction_convergence_hz",
            "consistency_chi_square",
            "standardized_scale_floor",
            "maximum_normal_condition",
            "diagnostic_estimator",
            "confidence_level",
            "step_transition_exclusion_s",
        },
        "estimator_model",
    )
    if estimator["timing_and_coarse_carrier_known"] is not True:
        raise ValueError("component experiment requires known timing and coarse carrier")
    _nonempty_string(estimator["coarse_seed_policy"], "coarse_seed_policy")
    if estimator["alias_change_known_and_canonicalized"] is not True:
        raise ValueError("component experiment requires frozen alias canonicalization")
    if estimator["frame_cfo_method"] != (
        "leo.analysis.qam.pilot.evaluate_edge_pilot_frame_cfo_likelihood with embedded "
        "even-trained odd-held-out split validation"
    ):
        raise ValueError("frame-CFO estimator differs from preregistration")
    frozen_estimator_scalars = {
        "residual_half_width_hz": 2_000.0,
        "profile_step_hz": 50.0,
        "minimum_exact_coherence": 0.02,
        "minimum_coherence_margin": 0.0,
        "fixed_measurement_sigma_hz": 50.0,
        "minimum_history_coverage": 0.95,
        "maximum_gap_s": 0.1,
        "huber_tuning": 1.345,
        "prediction_convergence_hz": 1e-6,
        "consistency_chi_square": 9.210340371976184,
        "standardized_scale_floor": 1.0,
        "maximum_normal_condition": 1e14,
        "confidence_level": 0.95,
        "step_transition_exclusion_s": 0.5,
    }
    for name, expected in frozen_estimator_scalars.items():
        if not math.isclose(
            _finite_float(estimator[name], f"estimator_model.{name}"),
            expected,
            rel_tol=0.0,
            abs_tol=1e-15,
        ):
            raise ValueError(f"estimator setting differs from preregistration: {name}")
    if estimator["maximum_iterations"] != 24:
        raise ValueError("maximum_iterations differs from preregistration")
    if estimator["odd_qin_may_influence_training"] is not False:
        raise ValueError("odd Qin must remain held out")
    if estimator["even_rolled_control_is_training_gate"] is not True:
        raise ValueError("even rolled Qin must remain the public specificity gate")
    if estimator["odd_rolled_control_may_influence_training"] is not False:
        raise ValueError("odd rolled Qin must remain held out")
    histories = tuple(
        _load_history(item)
        for item in _sequence(estimator["history_estimators"], "history_estimators")
    )
    if tuple(item.name for item in histories) != (
        "causal_20ms_linear",
        "fixed_125ms_linear",
        "fixed_500ms_linear",
    ):
        raise ValueError("history estimators differ from preregistration")
    expected_histories = (
        (0.02, 3, 3.0),
        (0.125, 12, 8.0),
        (0.5, 12, 8.0),
    )
    if (
        tuple(
            (item.history_s, item.minimum_frames, item.minimum_effective_frames)
            for item in histories
        )
        != expected_histories
    ):
        raise ValueError("history geometry differs from preregistration")
    diagnostic = _mapping(estimator["diagnostic_estimator"], "diagnostic_estimator")
    _exact_keys(
        diagnostic,
        {"name", "polynomial_order", "minimum_frames", "fit_method"},
        "diagnostic",
    )
    if diagnostic["name"] != "offline_full_span_cubic" or diagnostic["polynomial_order"] != 3:
        raise ValueError("diagnostic estimator must remain a full-span cubic")
    if diagnostic["fit_method"] != (
        "weighted least squares with fixed 50 Hz frame scale and residual chi-square "
        "covariance inflation"
    ):
        raise ValueError("diagnostic fit method differs from preregistration")
    metrics = _mapping(root["metrics"], "metrics")
    required_metrics = {
        "primary_coordinate",
        "secondary_coordinate",
        "reported",
        "strata",
        "aggregation",
        "coverage_interpretation",
        "rate_failure_absolute_error_hz_s",
        "acceleration_failure_absolute_error_hz_s2",
        "jerk_failure_absolute_error_hz_s3",
    }
    _exact_keys(metrics, required_metrics, "metrics")
    if metrics["primary_coordinate"] != "receiver_clock":
        raise ValueError("receiver-clock truth must remain primary")
    if metrics["secondary_coordinate"] != "injected_physical":
        raise ValueError("physical truth must remain the secondary coordinate")
    _nonempty_string_sequence(metrics["reported"], "metrics.reported")
    _nonempty_string_sequence(metrics["strata"], "metrics.strata")
    if metrics["aggregation"] != (
        "compute per-frame metrics within scenario, then give every scenario equal weight; "
        "aggregate RMSE is square root of mean scenario MSE"
    ):
        raise ValueError("metric aggregation differs from preregistration")
    if metrics["coverage_interpretation"] != (
        "frame endpoints are serially correlated, so nominal interval coverage is descriptive "
        "calibration rather than a binomial confidence experiment"
    ):
        raise ValueError("coverage interpretation differs from preregistration")

    gates = _mapping(root["promotion_gates"], "promotion_gates")
    _exact_keys(
        gates,
        {
            "scope",
            "fixed_500ms_rate_rmse_hz_s_max",
            "fixed_500ms_rate_failure_rate_max",
            "fixed_500ms_rate_coverage_min",
            "fixed_500ms_rate_coverage_max",
            "offline_cubic_acceleration_rmse_hz_s2_max",
            "offline_cubic_jerk_rmse_hz_s3_max",
            "all_three_backgrounds_required",
        },
        "promotion_gates",
    )
    _nonempty_string(gates["scope"], "promotion_gates.scope")
    for name, value in gates.items():
        if name == "scope":
            continue
        if name == "all_three_backgrounds_required":
            if value is not True:
                raise ValueError("all backgrounds must remain required")
            continue
        _positive_float(value, f"promotion_gates.{name}")

    design = _mapping(root["balanced_design"], "balanced_design")
    _exact_keys(design, {"scenario_count", "design_note", "scenarios"}, "balanced_design")
    _nonempty_string(design["design_note"], "balanced_design.design_note")
    scenario_count = _positive_int(design["scenario_count"], "scenario_count")
    scenarios = tuple(_load_scenario(item) for item in _sequence(design["scenarios"], "scenarios"))
    if len(scenarios) != scenario_count:
        raise ValueError("scenario count differs from the frozen design")
    _validate_balanced_design(scenarios, set(background_ids))
    limits = _nonempty_string_sequence(root["interpretation_limits"], "interpretation_limits")
    if len(limits) < 5:
        raise ValueError("protocol must retain its interpretation limits")

    protocol = PolynomialInjectionProtocol(
        basis_repository_commit=basis_commit,
        dataset_policy_path=policy_relative_path,
        dataset_policy_sha256=policy_digest,
        backgrounds=backgrounds,
        scenarios=scenarios,
        duration_s=duration_s,
        frame_rate_hz=frame_rate_hz,
        frame_count=frame_count,
        carrier_origin_hz=carrier_origin_hz,
        reference_time_s=reference_time_s,
        alias_change_time_s=alias_change_time_s,
        cfo_step_time_s=cfo_step_time_s,
        frame_cfo_search_half_width_hz=_positive_float(
            estimator["residual_half_width_hz"], "residual_half_width_hz"
        ),
        profile_step_hz=_positive_float(estimator["profile_step_hz"], "profile_step_hz"),
        minimum_exact_coherence=_finite_float(
            estimator["minimum_exact_coherence"], "minimum_exact_coherence"
        ),
        minimum_coherence_margin=_finite_float(
            estimator["minimum_coherence_margin"], "minimum_coherence_margin"
        ),
        fixed_measurement_sigma_hz=_positive_float(
            estimator["fixed_measurement_sigma_hz"], "fixed_measurement_sigma_hz"
        ),
        histories=histories,
        minimum_history_coverage=_probability(
            estimator["minimum_history_coverage"], "minimum_history_coverage"
        ),
        maximum_gap_s=_positive_float(estimator["maximum_gap_s"], "maximum_gap_s"),
        huber_tuning=_positive_float(estimator["huber_tuning"], "huber_tuning"),
        maximum_iterations=_positive_int(estimator["maximum_iterations"], "maximum_iterations"),
        prediction_convergence_hz=_positive_float(
            estimator["prediction_convergence_hz"], "prediction_convergence_hz"
        ),
        consistency_chi_square=_positive_float(
            estimator["consistency_chi_square"], "consistency_chi_square"
        ),
        standardized_scale_floor=_positive_float(
            estimator["standardized_scale_floor"], "standardized_scale_floor"
        ),
        maximum_normal_condition=_positive_float(
            estimator["maximum_normal_condition"], "maximum_normal_condition"
        ),
        diagnostic_minimum_frames=_positive_int(
            diagnostic["minimum_frames"], "diagnostic.minimum_frames"
        ),
        confidence_level=_probability(estimator["confidence_level"], "confidence_level"),
        step_transition_exclusion_s=_positive_float(
            estimator["step_transition_exclusion_s"], "step_transition_exclusion_s"
        ),
        rate_failure_absolute_error_hz_s=_positive_float(
            metrics["rate_failure_absolute_error_hz_s"], "rate failure threshold"
        ),
        acceleration_failure_absolute_error_hz_s2=_positive_float(
            metrics["acceleration_failure_absolute_error_hz_s2"],
            "acceleration failure threshold",
        ),
        jerk_failure_absolute_error_hz_s3=_positive_float(
            metrics["jerk_failure_absolute_error_hz_s3"], "jerk failure threshold"
        ),
    )
    expected_samples = int(round(protocol.duration_s * backgrounds[0].sample_rate_hz))
    if any(item.sample_count != expected_samples for item in backgrounds):
        raise ValueError("background span length differs from signal duration")
    return protocol


def _load_background(
    value: object,
    *,
    dataset_policy: DopplerDatasetPolicy,
    duration_s: float,
) -> BackgroundSpan:
    row = _mapping(value, "background")
    _exact_keys(row, _BACKGROUND_KEYS, "background")
    session_id = _nonempty_string(row["session_id"], "background.session_id")
    recording_digest = _matching_string(
        row["recording_manifest_sha256"], _SHA256_RE, "recording manifest digest"
    )
    run_id = _nonempty_string(row["analysis_run_id"], "analysis run id")
    analysis_digest = _matching_string(
        row["analysis_manifest_sha256"], _SHA256_RE, "analysis manifest digest"
    )
    authorize_capture(
        dataset_policy,
        experiment_role="polynomial_injection",
        session_id=session_id,
        recording_manifest_sha256=recording_digest,
        analysis_run_id=run_id,
        analysis_manifest_sha256=analysis_digest,
    )
    chunk_document = _mapping(row["chunk"], "background.chunk")
    _exact_keys(chunk_document, _CHUNK_KEYS, "background.chunk")
    chunk = ChunkBinding(
        chunk_index=_nonnegative_int(chunk_document["chunk_index"], "chunk_index"),
        sample_start=_nonnegative_int(chunk_document["sample_start"], "chunk.sample_start"),
        sample_count=_positive_int(chunk_document["sample_count"], "chunk.sample_count"),
        relative_path=_relative_path(
            chunk_document["relative_path"], "chunk.relative_path"
        ).as_posix(),
        compressed_sha256=_matching_string(
            chunk_document["compressed_sha256"], _SHA256_RE, "compressed chunk digest"
        ),
        uncompressed_sha256=_matching_string(
            chunk_document["uncompressed_sha256"], _SHA256_RE, "uncompressed chunk digest"
        ),
    )
    sample_start = _nonnegative_int(row["sample_start"], "background.sample_start")
    sample_count = _positive_int(row["sample_count"], "background.sample_count")
    if sample_start < chunk.sample_start or sample_start + sample_count > (
        chunk.sample_start + chunk.sample_count
    ):
        raise ValueError("background span must lie wholly inside its sealed chunk")
    sample_rate_hz = _positive_int(row["sample_rate_hz"], "sample_rate_hz")
    if not math.isclose(sample_count / sample_rate_hz, duration_s, abs_tol=1e-12):
        raise ValueError("background span is not exactly two seconds")
    recording_path = _absolute_path(row["recording_manifest_path"], "recording manifest")
    analysis_path = _absolute_path(row["analysis_manifest_path"], "analysis manifest")
    return BackgroundSpan(
        session_id=session_id,
        recording_manifest_path=recording_path,
        recording_manifest_sha256=recording_digest,
        analysis_run_id=run_id,
        analysis_manifest_path=analysis_path,
        analysis_manifest_sha256=analysis_digest,
        stream_id=_nonempty_string(row["stream_id"], "stream_id"),
        radio_id=_nonempty_string(row["radio_id"], "radio_id"),
        radio_serial=_nonempty_string(row["radio_serial"], "radio_serial"),
        receiver_id=_nonnegative_int(row["receiver_id"], "receiver_id"),
        sample_rate_hz=sample_rate_hz,
        sample_start=sample_start,
        sample_count=sample_count,
        chunk=chunk,
    )


def _load_history(value: object) -> HistoryEstimator:
    row = _mapping(value, "history estimator")
    _exact_keys(row, _HISTORY_KEYS, "history estimator")
    history = HistoryEstimator(
        name=_nonempty_string(row["name"], "history name"),
        history_s=_positive_float(row["history_s"], "history_s"),
        minimum_frames=_positive_int(row["minimum_frames"], "minimum_frames"),
        minimum_effective_frames=_positive_float(
            row["minimum_effective_frames"], "minimum_effective_frames"
        ),
    )
    if not 2.0 < history.minimum_effective_frames <= history.minimum_frames:
        raise ValueError("minimum effective frames must lie in (2, minimum frames]")
    return history


def _load_scenario(value: object) -> InjectionScenario:
    row = _mapping(value, "scenario")
    _exact_keys(row, _SCENARIO_KEYS, "scenario")
    return InjectionScenario(
        scenario_id=_nonempty_string(row["scenario_id"], "scenario_id"),
        background_session_id=_nonempty_string(
            row["background_session_id"], "background_session_id"
        ),
        seed=_nonnegative_int(row["seed"], "scenario seed"),
        rate_hz_s=_finite_float(row["rate_hz_s"], "rate_hz_s"),
        acceleration_hz_s2=_finite_float(row["acceleration_hz_s2"], "acceleration_hz_s2"),
        jerk_hz_s3=_finite_float(row["jerk_hz_s3"], "jerk_hz_s3"),
        snr_db=_finite_float(row["snr_db"], "snr_db"),
        frame_occupancy=_probability(row["frame_occupancy"], "frame_occupancy"),
        alias_change_hz=_finite_float(row["alias_change_hz"], "alias_change_hz"),
        cfo_step_hz=_finite_float(row["cfo_step_hz"], "cfo_step_hz"),
        sample_clock_offset_ppm=_finite_float(
            row["sample_clock_offset_ppm"], "sample_clock_offset_ppm"
        ),
    )


def _validate_balanced_design(
    scenarios: tuple[InjectionScenario, ...], background_ids: set[str]
) -> None:
    if len(scenarios) != 18:
        raise ValueError("frozen balanced design must contain 18 scenarios")
    if tuple(item.scenario_id for item in scenarios) != tuple(
        f"P{index:03d}" for index in range(1, 19)
    ):
        raise ValueError("scenario identifiers or order differ from preregistration")
    if len({item.seed for item in scenarios}) != len(scenarios):
        raise ValueError("scenario seeds must be unique")
    if {item.background_session_id for item in scenarios} != background_ids:
        raise ValueError("balanced design does not use exactly the authorized backgrounds")
    expected_counts: tuple[tuple[str, Counter[float | str], Counter[float | str]], ...] = (
        (
            "background",
            Counter(item.background_session_id for item in scenarios),
            Counter({item: 6 for item in background_ids}),
        ),
        (
            "rate",
            Counter(item.rate_hz_s for item in scenarios),
            Counter({item: 3 for item in (-6000.0, -3500.0, -1500.0, 1500.0, 3500.0, 6000.0)}),
        ),
        (
            "acceleration",
            Counter(item.acceleration_hz_s2 for item in scenarios),
            Counter({item: 6 for item in (-800.0, 0.0, 800.0)}),
        ),
        (
            "jerk",
            Counter(item.jerk_hz_s3 for item in scenarios),
            Counter({item: 6 for item in (-300.0, 0.0, 300.0)}),
        ),
        (
            "SNR",
            Counter(item.snr_db for item in scenarios),
            Counter({item: 6 for item in (-32.0, -24.0, -16.0)}),
        ),
        (
            "occupancy",
            Counter(item.frame_occupancy for item in scenarios),
            Counter({item: 6 for item in (0.35, 0.65, 1.0)}),
        ),
        (
            "alias",
            Counter(item.alias_change_hz for item in scenarios),
            Counter({item: 6 for item in (-750.0, 0.0, 750.0)}),
        ),
        (
            "step",
            Counter(item.cfo_step_hz for item in scenarios),
            Counter({item: 6 for item in (-300.0, 0.0, 300.0)}),
        ),
        (
            "clock",
            Counter(item.sample_clock_offset_ppm for item in scenarios),
            Counter({item: 6 for item in (-25.0, 0.0, 25.0)}),
        ),
    )
    for name, observed, expected in expected_counts:
        if observed != expected:
            raise ValueError(f"{name} factor is not marginally balanced")
    crossed = Counter(
        (item.snr_db, item.frame_occupancy, item.sample_clock_offset_ppm) for item in scenarios
    )
    if len(crossed) != 18 or set(crossed.values()) != {1}:
        raise ValueError("SNR, occupancy, and clock triples must remain distinct")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{name} fields differ from the v1 schema")


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _matching_string(value: object, pattern: re.Pattern[str], name: str) -> str:
    checked = _nonempty_string(value, name)
    if pattern.fullmatch(checked) is None:
        raise ValueError(f"{name} has an invalid format")
    return checked


def _nonempty_string_sequence(value: object, name: str) -> tuple[str, ...]:
    return tuple(_nonempty_string(item, name) for item in _sequence(value, name))


def _nonnegative_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _positive_int(value: object, name: str) -> int:
    checked = _nonnegative_int(value, name)
    if checked == 0:
        raise ValueError(f"{name} must be positive")
    return checked


def _finite_float(value: object, name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    checked = float(value)
    if not math.isfinite(checked):
        raise ValueError(f"{name} must be finite")
    return checked


def _positive_float(value: object, name: str) -> float:
    checked = _finite_float(value, name)
    if checked <= 0.0:
        raise ValueError(f"{name} must be positive")
    return checked


def _probability(value: object, name: str) -> float:
    checked = _finite_float(value, name)
    if not 0.0 < checked <= 1.0:
        raise ValueError(f"{name} must lie in (0, 1]")
    return checked


def _relative_path(value: object, name: str) -> Path:
    path = Path(_nonempty_string(value, name))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{name} must be repository-relative")
    return path


def _absolute_path(value: object, name: str) -> Path:
    path = Path(_nonempty_string(value, name))
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{name} must be an absolute normalized path")
    return path


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
