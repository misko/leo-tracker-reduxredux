"""Bounded Standard-stage pilot detection, trajectory fitting, and IQ replay."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from typing import Any, cast

import numpy as np
from pydantic import JsonValue

from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
)
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotProbeDetection,
    detect_pilot_method_candidates,
    detect_pilot_methods,
)
from leo.analysis.starlink.trajectories import (
    PolynomialTrajectory,
    TrajectoryBankResult,
    TrajectoryObservation,
    correct_polynomial_cfo,
    default_trajectory_bank_config,
    fit_trajectory_bank,
)
from leo.contracts.digests import canonical_digest
from leo.pipeline import (
    AnalysisContext,
    IqReader,
    OutputSink,
    ProductReader,
    StageOutcome,
    StageResult,
    StageSpec,
)


@dataclass(frozen=True, slots=True)
class TrajectoryFeedbackConfig:
    """Frozen, bounded sampling and replay policy for Standard analysis."""

    coarse_window_samples_per_second: int = 1
    subwindow_ms: int = 50
    probe_ms: int = 20
    maximum_outer_windows: int = 120
    maximum_replayed_families: int = 16
    maximum_scored_candidates_per_probe: int = 4
    maximum_workers: int = 4


def validate_trajectory_feedback_config(config: TrajectoryFeedbackConfig) -> None:
    """Validate the complete shared policy at every public computation boundary."""

    coarse = config.coarse_window_samples_per_second
    if isinstance(coarse, bool) or not isinstance(coarse, int) or coarse != 1:
        raise ValueError("only exact one-second coarse windows are supported")
    integers = (
        config.subwindow_ms,
        config.probe_ms,
        config.maximum_outer_windows,
        config.maximum_replayed_families,
        config.maximum_scored_candidates_per_probe,
        config.maximum_workers,
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in integers
    ):
        raise ValueError("trajectory feedback bounds must be positive integers")
    if not config.probe_ms <= config.subwindow_ms <= 1_000:
        raise ValueError("trajectory feedback window geometry is invalid")
    if 1_000 % config.subwindow_ms:
        raise ValueError("subwindow_ms must divide one second exactly")


class TrajectoryFeedbackAnalyzer:
    """Run every pilot method, fit d1/d2/d3 tracks, then dechirp and replay."""

    def __init__(
        self,
        spec: StageSpec,
        config: TrajectoryFeedbackConfig | None = None,
    ) -> None:
        config = config or TrajectoryFeedbackConfig()
        validate_trajectory_feedback_config(config)
        self.spec = spec
        self._config = config

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        _products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        if len(iq.receiver_ids) != 1:
            return self._empty(context, outputs, "trajectory feedback requires one receiver scope")
        geometry = _geometry(iq.sample_rate_hz, self._config)
        if iq.sample_count < geometry.probe_samples:
            return self._empty(context, outputs, "recording is shorter than one pilot probe")
        detections = scan_legacy_pilot_detections(iq, self._config)
        bank, representatives = fit_legacy_pilot_trajectories(detections, self._config)
        replay = replay_pilot_trajectories(iq, detections, representatives, self._config)
        documents = _documents(
            context,
            detections,
            bank,
            representatives,
            replay,
            geometry,
        )
        published = tuple(
            outputs.publish_json(product, documents[product.kind])
            for product in self.spec.output_products
        )
        outcome = StageOutcome.COMPLETE if detections else StageOutcome.INSUFFICIENT_DATA
        return StageResult(
            outcome=outcome,
            products=published,
            summary={
                "probe_count": len(detections),
                "trajectory_count": len(bank.trajectories),
                "trajectory_family_count": len(bank.families),
                "replayed_family_count": len(representatives),
                "candidate_only": True,
            },
            message=(
                "candidate-only all-method polynomial trajectory feedback; no payload decoded"
                if detections
                else "no complete pilot probes"
            ),
        )

    def _empty(self, context: AnalysisContext, outputs: OutputSink, reason: str) -> StageResult:
        documents: dict[str, dict[str, JsonValue]] = {
            product.kind: {
                "schema_version": 1,
                "run_id": context.run_id,
                "candidate_only": True,
                "status": "insufficient",
                "reason": reason,
                "items": [],
            }
            for product in self.spec.output_products
        }
        published = tuple(
            outputs.publish_json(product, documents[product.kind])
            for product in self.spec.output_products
        )
        return StageResult(
            outcome=StageOutcome.INSUFFICIENT_DATA,
            products=published,
            summary={"probe_count": 0, "candidate_only": True},
            message=reason,
        )


@dataclass(frozen=True, slots=True)
class _Geometry:
    outer_samples: int
    subwindow_samples: int
    probe_samples: int


def scan_pilot_detections(
    iq: IqReader,
    config: TrajectoryFeedbackConfig,
) -> tuple[PilotProbeDetection, ...]:
    """Read scheduled probes and emit deterministic bounded multi-basin certificates."""

    validate_trajectory_feedback_config(config)
    if len(iq.receiver_ids) != 1:
        raise ValueError("pilot scan requires one receiver scope")
    geometry = _geometry(iq.sample_rate_hz, config)
    calibration = _baseband_prior(iq.receiver_ids[0])
    acquisition = SymbolwiseAcquisitionConfig(maximum_probe_samples=geometry.probe_samples)
    detection_batches = _bounded_parallel_batches(
        _iter_probe_batches(iq, geometry, config.maximum_outer_windows),
        lambda batch: _detect_batch(
            batch,
            iq.sample_rate_hz,
            calibration,
            acquisition,
            config.maximum_scored_candidates_per_probe,
        ),
        config.maximum_workers,
    )
    return tuple(
        sorted(
            (item for batch in detection_batches for item in batch),
            key=lambda item: item.sample_start,
        )
    )


def scan_legacy_pilot_detections(
    iq: IqReader,
    config: TrajectoryFeedbackConfig,
) -> tuple[PilotProbeDetection, ...]:
    """Preserve the published v1 winner-only detector behavior."""

    validate_trajectory_feedback_config(config)
    if len(iq.receiver_ids) != 1:
        raise ValueError("pilot scan requires one receiver scope")
    geometry = _geometry(iq.sample_rate_hz, config)
    calibration = _baseband_prior(iq.receiver_ids[0])
    acquisition = SymbolwiseAcquisitionConfig(maximum_probe_samples=geometry.probe_samples)
    batches = _bounded_parallel_batches(
        _iter_probe_batches(iq, geometry, config.maximum_outer_windows),
        lambda batch: _detect_batch(
            batch,
            iq.sample_rate_hz,
            calibration,
            acquisition,
            None,
        ),
        config.maximum_workers,
    )
    return tuple(
        sorted(
            (item for batch in batches for item in batch),
            key=lambda item: item.sample_start,
        )
    )


def fit_pilot_trajectories(
    detections: tuple[PilotProbeDetection, ...],
    config: TrajectoryFeedbackConfig,
) -> tuple[TrajectoryBankResult, tuple[tuple[str, PolynomialTrajectory], ...]]:
    """Fit degree-1/2/3 candidate families without IQ access."""

    validate_trajectory_feedback_config(config)
    observations = trajectory_observations(detections)
    bank = fit_trajectory_bank(observations, default_trajectory_bank_config())
    return bank, select_trajectory_representatives(bank, config.maximum_replayed_families)


def fit_legacy_pilot_trajectories(
    detections: tuple[PilotProbeDetection, ...],
    config: TrajectoryFeedbackConfig,
) -> tuple[TrajectoryBankResult, tuple[tuple[str, PolynomialTrajectory], ...]]:
    validate_trajectory_feedback_config(config)
    observations = legacy_trajectory_observations(detections)
    bank = fit_trajectory_bank(observations, default_trajectory_bank_config())
    return bank, select_trajectory_representatives(bank, config.maximum_replayed_families)


def replay_pilot_trajectories(
    iq: IqReader,
    detections: tuple[PilotProbeDetection, ...],
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    config: TrajectoryFeedbackConfig,
) -> tuple[dict[str, JsonValue], ...]:
    """Read the exact scheduled probes, dechirp, and rerun detector/QAM methods."""

    validate_trajectory_feedback_config(config)
    geometry = _geometry(iq.sample_rate_hz, config)
    return _replay(
        iq,
        list(detections),
        representatives,
        geometry,
        config.maximum_outer_windows,
        config.maximum_workers,
    )


def _geometry(sample_rate_hz: int, config: TrajectoryFeedbackConfig) -> _Geometry:
    validate_trajectory_feedback_config(config)
    if sample_rate_hz <= 0:
        raise ValueError("sample rate must be positive")
    subwindow = sample_rate_hz * config.subwindow_ms
    probe = sample_rate_hz * config.probe_ms
    if subwindow % 1_000 or probe % 1_000:
        raise ValueError("window durations do not map to integral samples")
    return _Geometry(sample_rate_hz, subwindow // 1_000, probe // 1_000)


def _iter_probe_batches(
    iq: IqReader,
    geometry: _Geometry,
    maximum_outer_windows: int,
):
    """Yield one bounded task containing all scheduled probes in a coarse second."""

    receiver_index = 0
    pending = np.empty(0, dtype=np.complex128)
    pending_start = 0
    expected_start = 0
    outer_count = 0
    for block in iq.iter_blocks(block_samples=geometry.outer_samples):
        if block.metadata.session_sample_start != expected_start:
            raise ValueError("trajectory feedback requires contiguous IQ coverage")
        expected_start += block.metadata.sample_count
        values = (
            block.samples[:, receiver_index, 0].astype(np.float64)
            + 1j * block.samples[:, receiver_index, 1].astype(np.float64)
        ) / 32_768.0
        pending = np.concatenate((pending, values))
        while len(pending) >= geometry.outer_samples and outer_count < maximum_outer_windows:
            outer = pending[: geometry.outer_samples]
            yield tuple(
                (
                    pending_start + relative,
                    np.ascontiguousarray(outer[relative : relative + geometry.probe_samples]),
                )
                for relative in range(0, geometry.outer_samples, geometry.subwindow_samples)
            )
            pending = pending[geometry.outer_samples :]
            pending_start += geometry.outer_samples
            outer_count += 1
        if outer_count >= maximum_outer_windows:
            return


def _detect_batch(
    batch: tuple[tuple[int, np.ndarray], ...],
    sample_rate_hz: int,
    calibration: ReceiverFrequencyCalibration,
    acquisition: SymbolwiseAcquisitionConfig,
    maximum_scored_candidates: int | None,
) -> tuple[PilotProbeDetection, ...]:
    result = []
    for sample_start, samples in batch:
        if maximum_scored_candidates is None:
            detected = detect_pilot_methods(
                samples,
                sample_rate_hz,
                sample_start=sample_start,
                calibration=calibration,
                acquisition_config=acquisition,
            )
        else:
            detected = detect_pilot_method_candidates(
                samples,
                sample_rate_hz,
                sample_start=sample_start,
                calibration=calibration,
                acquisition_config=acquisition,
                maximum_scored_candidates=maximum_scored_candidates,
            )
        result.append(detected)
    return tuple(result)


def _bounded_parallel_batches[BatchInput, BatchOutput](
    batches: Iterable[BatchInput],
    function: Callable[[BatchInput], BatchOutput],
    maximum_workers: int,
) -> tuple[BatchOutput, ...]:
    """Run coarse windows concurrently without retaining the whole dwell."""

    completed: dict[int, BatchOutput] = {}
    pending: dict[Future[BatchOutput], int] = {}
    with ThreadPoolExecutor(max_workers=maximum_workers) as executor:
        for index, batch in enumerate(batches):
            pending[executor.submit(function, batch)] = index
            if len(pending) >= maximum_workers * 2:
                finished, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in finished:
                    completed[pending.pop(future)] = future.result()
        while pending:
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                completed[pending.pop(future)] = future.result()
    return tuple(completed[index] for index in sorted(completed))


def trajectory_observations(
    detections: tuple[PilotProbeDetection, ...],
) -> tuple[TrajectoryObservation, ...]:
    values = []
    for detection in detections:
        candidates = detection.candidates
        candidate_scores = (
            tuple((candidate.rank, candidate.scores) for candidate in candidates)
            if candidates
            else ((0, detection.scores),)
        )
        for candidate_rank, scores in candidate_scores:
            for score in scores:
                values.append(
                    TrajectoryObservation(
                        canonical_digest(
                            {
                                "sample_start": detection.sample_start,
                                "candidate_rank": candidate_rank,
                                "method": score.method.value,
                            }
                        ),
                        score.method,
                        detection.sample_start,
                        detection.time_s,
                        score.tracking_cfo_hz,
                        score.exact_score,
                        score.control_score,
                        score.margin,
                    )
                )
    return tuple(values)


def legacy_trajectory_observations(
    detections: tuple[PilotProbeDetection, ...],
) -> tuple[TrajectoryObservation, ...]:
    """Exact v1 winner-only observation IDs and values."""

    return tuple(
        TrajectoryObservation(
            canonical_digest(
                {"sample_start": detection.sample_start, "method": score.method.value}
            ),
            score.method,
            detection.sample_start,
            detection.time_s,
            score.tracking_cfo_hz,
            score.exact_score,
            score.control_score,
            score.margin,
        )
        for detection in detections
        for score in detection.scores
    )


def select_trajectory_representatives(
    bank: Any, maximum: int
) -> tuple[tuple[str, PolynomialTrajectory], ...]:
    by_id = {item.trajectory_id: item for item in bank.trajectories}
    result = []
    for family in bank.families[:maximum]:
        members = tuple(by_id[item] for item in family.member_trajectory_ids)
        glrt64 = tuple(item for item in members if item.method is PilotMethod.GLRT64)
        if not glrt64:
            continue
        representative = min(
            glrt64,
            key=lambda item: (
                -float(item.end_s - item.start_s),
                item.bic / max(item.point_count, 1),
                item.polynomial_degree,
            ),
        )
        result.append((family.family_id, representative))
    return tuple(result)


def _replay(
    iq: IqReader,
    detections: list[PilotProbeDetection],
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    geometry: _Geometry,
    maximum_outer_windows: int,
    maximum_workers: int,
) -> tuple[dict[str, JsonValue], ...]:
    baseline = {item.sample_start: item for item in detections}
    result: list[dict[str, JsonValue]] = []
    replay_config = SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-20_000.0,
        residual_cfo_max_hz=20_000.0,
        coarse_cfo_step_hz=10_000.0,
        fine_cfo_radius_hz=20_000.0,
        retained_candidate_count=2,
        maximum_probe_samples=geometry.probe_samples,
    )
    calibrations = {
        trajectory.trajectory_id: ReceiverFrequencyCalibration(
            "trajectory-corrected",
            0.0,
            canonical_digest({"trajectory_id": trajectory.trajectory_id}).removeprefix("sha256:"),
        )
        for _, trajectory in representatives
    }
    replayed = _bounded_parallel_batches(
        _iter_probe_batches(iq, geometry, maximum_outer_windows),
        lambda batch: _replay_batch(
            batch,
            iq.sample_rate_hz,
            representatives,
            baseline,
            calibrations,
            replay_config,
        ),
        maximum_workers,
    )
    result.extend(item for batch in replayed for item in batch)
    return tuple(
        sorted(
            result,
            key=lambda item: (
                str(item["family_id"]),
                cast(int, item["sample_start"]),
                str(item["detector_method"]),
            ),
        )
    )


def _replay_batch(
    batch: tuple[tuple[int, np.ndarray], ...],
    sample_rate_hz: int,
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    baseline: dict[int, PilotProbeDetection],
    calibrations: dict[str, ReceiverFrequencyCalibration],
    replay_config: SymbolwiseAcquisitionConfig,
) -> tuple[dict[str, JsonValue], ...]:
    result: list[dict[str, JsonValue]] = []
    for sample_start, samples in batch:
        time_s = sample_start / sample_rate_hz
        for family_id, trajectory in representatives:
            if not trajectory.start_s <= time_s <= trajectory.end_s:
                continue
            corrected = correct_polynomial_cfo(samples, sample_rate_hz, sample_start, trajectory)
            detected = detect_pilot_methods(
                corrected,
                sample_rate_hz,
                sample_start=sample_start,
                calibration=calibrations[trajectory.trajectory_id],
                acquisition_config=replay_config,
            )
            original = {score.method: score for score in baseline[sample_start].scores}
            for score in detected.scores:
                before = original.get(score.method)
                if before is None:
                    continue
                result.append(
                    cast(
                        dict[str, JsonValue],
                        {
                            "family_id": family_id,
                            "trajectory_id": trajectory.trajectory_id,
                            "trajectory_method": trajectory.method.value,
                            "polynomial_degree": trajectory.polynomial_degree,
                            "sample_start": sample_start,
                            "time_s": time_s,
                            "detector_method": score.method.value,
                            "baseline_margin": before.margin,
                            "corrected_margin": score.margin,
                            "margin_delta": score.margin - before.margin,
                            "corrected_residual_cfo_hz": score.tracking_cfo_hz,
                        },
                    )
                )
    return tuple(result)


def _documents(context, detections, bank, representatives, replay, geometry):
    common = {
        "schema_version": 1,
        "run_id": context.run_id,
        "scope_key": context.scope_key,
        "candidate_only": True,
        "payload_decoded": False,
    }
    return {
        "starlink.pilot-method-detections": cast(
            dict[str, JsonValue],
            {
                **common,
                "coarse_window_samples": geometry.outer_samples,
                "subwindow_samples": geometry.subwindow_samples,
                "probe_samples": geometry.probe_samples,
                "methods": [method.value for method in PilotMethod],
                "detections": [_legacy_detection_document(item) for item in detections],
            },
        ),
        "starlink.polynomial-trajectories": cast(
            dict[str, JsonValue],
            {
                **common,
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
        ),
        "starlink.trajectory-redetection": cast(
            dict[str, JsonValue],
            {**common, "results": list(replay)},
        ),
        "starlink.glrt64-trajectory-table": cast(
            dict[str, JsonValue],
            {
                **common,
                "frequency_model": "cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)",
                "coefficient_order": "highest_polynomial_power_first",
                "fit_gate_hz": 2_500.0,
                "trajectories": build_glrt64_trajectory_table(bank, representatives, replay),
            },
        ),
    }


def _legacy_detection_document(item: PilotProbeDetection) -> dict[str, Any]:
    """Keep the published v1 document closed despite richer internal evidence."""

    return {
        "status": item.status,
        "sample_start": item.sample_start,
        "time_s": item.time_s,
        "local_epoch_sample": item.local_epoch_sample,
        "acquired_cfo_hz": item.acquired_cfo_hz,
        "scores": [asdict(score) for score in item.scores],
        "qam_accuracy": item.qam_accuracy,
        "qam_evm": item.qam_evm,
        "reason": item.reason,
    }


def _baseband_prior(receiver_id: int) -> ReceiverFrequencyCalibration:
    """Internal numerical coordinate only; never persisted as calibration authority."""

    return ReceiverFrequencyCalibration(
        receiver_id=str(receiver_id),
        center_hz=0.0,
        calibration_sha256=canonical_digest(
            {
                "receiver_id": receiver_id,
                "frequency_reference": "uncalibrated_prior",
                "coordinate": "baseband_cfo_hz",
            }
        ).removeprefix("sha256:"),
    )


def build_glrt64_trajectory_table(
    bank: Any,
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    replay: tuple[dict[str, JsonValue], ...],
) -> list[dict[str, JsonValue]]:
    family_by_member = {
        trajectory_id: family.family_id
        for family in bank.families
        for trajectory_id in family.member_trajectory_ids
    }
    replayed = {trajectory.trajectory_id for _, trajectory in representatives}
    result = []
    for trajectory in bank.trajectories:
        if trajectory.method is not PilotMethod.GLRT64:
            continue
        family_id = family_by_member.get(trajectory.trajectory_id)
        delta_values: list[float] = []
        for item in replay:
            if (
                item["trajectory_id"] != trajectory.trajectory_id
                or item["detector_method"] != "glrt64"
            ):
                continue
            value = item["margin_delta"]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("GLRT-64 replay margin delta must be numeric")
            delta_values.append(float(value))
        deltas = np.asarray(delta_values, dtype=np.float64)
        result.append(
            cast(
                dict[str, JsonValue],
                {
                    "trajectory_id": trajectory.trajectory_id,
                    "family_id": family_id,
                    "model": {1: "linear", 2: "quadratic", 3: "cubic"}[
                        trajectory.polynomial_degree
                    ],
                    "polynomial_degree": trajectory.polynomial_degree,
                    "reference_time_s": trajectory.reference_time_s,
                    "coefficients_hz": list(trajectory.coefficients_hz),
                    "start_s": trajectory.start_s,
                    "end_s": trajectory.end_s,
                    "duration_s": trajectory.end_s - trajectory.start_s,
                    "point_count": trajectory.point_count,
                    "residual_rms_hz": trajectory.residual_rms_hz,
                    "bic": trajectory.bic,
                    "high_gate": trajectory.high_gate,
                    "em_iterations": trajectory.em_iterations,
                    "fit_matches_well": trajectory.residual_rms_hz <= 2_500.0,
                    "selected_for_correction": trajectory.trajectory_id in replayed,
                    "corrected_glrt64_probe_count": int(deltas.size),
                    "median_glrt64_margin_delta": (
                        float(np.median(deltas)) if deltas.size else None
                    ),
                },
            )
        )
    return result
