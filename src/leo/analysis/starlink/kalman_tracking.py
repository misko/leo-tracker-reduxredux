"""Five-state Starlink frame/carrier Kalman tracking from known edge pilots.

The state and continuous-white-noise discretization follow Equation (8) of
Kozhaya, Saroufim, and Kassas, "Unveiling Starlink for PNT" (2025).  The
paper's code-phase pair is used here as frame phase and frame-rate error: this
repository knows the Qin edge synchronization pilots but does not claim the
paper's full proprietary OFDM beacon or pseudorange observable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from leo.analysis.starlink.pilot_methods import PilotMethodCandidate, PilotProbeDetection
from leo.analysis.starlink.templates import (
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    qin_edge_pilot_frame,
)
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    iter_pilot_probe_samples,
)
from leo.contracts.cfo_dealias import DealiasedTrajectoryBankV4, FinalTrajectoryBankV3
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.kalman_tracking import (
    KalmanFrameEstimateV1,
    KalmanTrackingConfigV1,
    KalmanTrajectoryTrackV1,
    StandardKalmanTrackingV1,
)
from leo.contracts.standard_pipeline import StandardScientificStatus
from leo.pipeline import IqReader


@dataclass(frozen=True, slots=True)
class PolynomialFrequencyModel:
    """Absolute CFO polynomial using the Standard highest-power-first convention."""

    reference_time_s: float
    coefficients_hz: tuple[float, ...]

    def frequency_hz(self, time_s: npt.ArrayLike) -> npt.NDArray[np.float64]:
        delta = np.asarray(time_s, dtype=float) - self.reference_time_s
        return np.asarray(np.polyval(self.coefficients_hz, delta), dtype=float)

    def doppler_rate_hz_s(self, time_s: npt.ArrayLike) -> npt.NDArray[np.float64]:
        derivative = np.polyder(np.asarray(self.coefficients_hz, dtype=float))
        delta = np.asarray(time_s, dtype=float) - self.reference_time_s
        return np.asarray(np.polyval(derivative, delta), dtype=float)

    def phase_rad(self, time_s: npt.ArrayLike) -> npt.NDArray[np.float64]:
        delta = np.asarray(time_s, dtype=float) - self.reference_time_s
        integral = np.polyint(np.asarray(self.coefficients_hz, dtype=float))
        cycles = np.polyval(integral, delta) - np.polyval(integral, 0.0)
        return np.asarray(2 * math.pi * cycles, dtype=float)


@dataclass(frozen=True, slots=True)
class RawFrameMeasurement:
    sample_start: int
    time_s: float
    prompt_coherence: float
    carrier_phase_rad: float
    doppler_hz: float


@dataclass(frozen=True, slots=True)
class KalmanFrameObservation:
    frame_index: int
    sample_start: int
    time_s: float
    prompt_coherence: float
    carrier_phase_rad: float
    doppler_hz: float
    frame_phase_s: float


@dataclass(frozen=True, slots=True)
class KalmanFrameEstimate:
    observation: KalmanFrameObservation
    update_applied: bool
    phase_innovation_rad: float
    doppler_innovation_hz: float
    frame_phase_innovation_s: float
    carrier_phase_rad: float
    doppler_shift_hz: float
    doppler_rate_hz_s: float
    frame_phase_s: float
    frame_rate_error_s_s: float
    carrier_phase_sigma_rad: float
    doppler_sigma_hz: float
    doppler_rate_sigma_hz_s: float
    frame_phase_sigma_s: float
    phase_slip_detected: bool
    cfo_correction_detected: bool
    estimated_cfo_correction_hz: float | None


@dataclass(frozen=True, slots=True)
class _CandidateSource:
    detection_sample_start: int
    local_epoch_sample: int


def state_transition(dt_s: float) -> npt.NDArray[np.float64]:
    """Exact transition for phase/phase-rate/phase-acceleration and frame phase/drift."""

    if not math.isfinite(dt_s) or dt_s < 0:
        raise ValueError("Kalman transition interval must be finite and nonnegative")
    return np.asarray(
        (
            (1.0, dt_s, 0.5 * dt_s**2, 0.0, 0.0),
            (0.0, 1.0, dt_s, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 1.0, dt_s),
            (0.0, 0.0, 0.0, 0.0, 1.0),
        ),
        dtype=float,
    )


def process_covariance(
    dt_s: float,
    *,
    carrier_acceleration_psd_rad2_s3: float,
    frame_rate_psd_s2_s: float,
) -> npt.NDArray[np.float64]:
    """Exact integral of ``exp(A t) B Q B.T exp(A.T t)`` from the paper."""

    if not math.isfinite(dt_s) or dt_s < 0:
        raise ValueError("Kalman covariance interval must be finite and nonnegative")
    q_phase = carrier_acceleration_psd_rad2_s3
    q_frame = frame_rate_psd_s2_s
    if any(not math.isfinite(value) or value <= 0 for value in (q_phase, q_frame)):
        raise ValueError("Kalman process spectral densities must be finite and positive")
    result = np.zeros((5, 5), dtype=float)
    result[:3, :3] = q_phase * np.asarray(
        (
            (dt_s**5 / 20, dt_s**4 / 8, dt_s**3 / 6),
            (dt_s**4 / 8, dt_s**3 / 3, dt_s**2 / 2),
            (dt_s**3 / 6, dt_s**2 / 2, dt_s),
        )
    )
    result[3:, 3:] = q_frame * np.asarray(((dt_s**3 / 3, dt_s**2 / 2), (dt_s**2 / 2, dt_s)))
    return result


def track_frame_observations(
    observations: tuple[KalmanFrameObservation, ...],
    config: KalmanTrackingConfigV1,
    *,
    initial_doppler_rate_hz_s: float,
) -> tuple[KalmanFrameEstimate, ...]:
    """Run the paper's closed-loop five-state KF over irregular received frames."""

    if not observations:
        return ()
    if not math.isfinite(initial_doppler_rate_hz_s):
        raise ValueError("initial Doppler rate must be finite")
    ordered = tuple(sorted(observations, key=lambda item: (item.time_s, item.frame_index)))
    if len({item.frame_index for item in ordered}) != len(ordered):
        raise ValueError("Kalman frame observation indexes must be unique")
    if any(right.time_s <= left.time_s for left, right in zip(ordered, ordered[1:], strict=False)):
        raise ValueError("Kalman frame observation times must increase strictly")

    first = ordered[0]
    x = np.asarray(
        (
            first.carrier_phase_rad,
            2 * math.pi * first.doppler_hz,
            2 * math.pi * initial_doppler_rate_hz_s,
            first.frame_phase_s,
            0.0,
        ),
        dtype=float,
    )
    phase_sigma = config.carrier_phase_measurement_sigma_rad
    frequency_sigma = config.carrier_frequency_measurement_sigma_rad_s
    frame_sigma = config.frame_phase_measurement_sigma_s
    p = np.diag(
        (
            phase_sigma**2,
            frequency_sigma**2,
            (2 * math.pi * config.initial_doppler_rate_sigma_hz_s) ** 2,
            frame_sigma**2,
            config.frame_rate_psd_s2_s,
        )
    )
    h = np.asarray(
        ((1.0, 0.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0, 0.0))
    )
    identity = np.eye(5)
    estimates: list[KalmanFrameEstimate] = []
    previous_time = first.time_s
    last_correction_time = -math.inf

    for index, observation in enumerate(ordered):
        if index:
            dt = observation.time_s - previous_time
            transition = state_transition(dt)
            x = transition @ x
            p = transition @ p @ transition.T + process_covariance(
                dt,
                carrier_acceleration_psd_rad2_s3=(config.carrier_acceleration_psd_rad2_s3),
                frame_rate_psd_s2_s=config.frame_rate_psd_s2_s,
            )
        measurement = np.asarray(
            (
                observation.carrier_phase_rad,
                2 * math.pi * observation.doppler_hz,
                observation.frame_phase_s,
            )
        )
        innovation = measurement - h @ x
        innovation[0] = _wrap_rad(float(innovation[0]))
        doppler_innovation_hz = float(innovation[1] / (2 * math.pi))
        update = observation.prompt_coherence >= config.minimum_prompt_coherence
        phase_slip = update and abs(float(innovation[0])) >= config.phase_slip_threshold_rad
        correction = (
            update
            and abs(doppler_innovation_hz) >= config.cfo_correction_threshold_hz
            and observation.time_s - last_correction_time
            >= config.cfo_correction_minimum_separation_s
        )
        correction_hz = doppler_innovation_hz if correction else None
        if correction:
            last_correction_time = observation.time_s
        if update:
            # Lower-coherence prompt matches carry proportionally larger
            # discriminator noise without changing the paper's nominal tuning.
            scale = 1 / max(observation.prompt_coherence, config.minimum_prompt_coherence)
            r = np.diag(
                (
                    (phase_sigma * scale) ** 2,
                    (frequency_sigma * scale) ** 2,
                    (frame_sigma * scale) ** 2,
                )
            )
            innovation_covariance = h @ p @ h.T + r
            gain = np.linalg.solve(innovation_covariance, h @ p).T
            x = x + gain @ innovation
            # Joseph form keeps the covariance symmetric and positive under
            # long, gapped frame histories.
            residual_operator = identity - gain @ h
            p = residual_operator @ p @ residual_operator.T + gain @ r @ gain.T
            p = 0.5 * (p + p.T)
        diagonal = np.maximum(np.diag(p), 0.0)
        estimates.append(
            KalmanFrameEstimate(
                observation=observation,
                update_applied=update,
                phase_innovation_rad=float(innovation[0]),
                doppler_innovation_hz=doppler_innovation_hz,
                frame_phase_innovation_s=float(innovation[2]),
                carrier_phase_rad=float(x[0]),
                doppler_shift_hz=float(x[1] / (2 * math.pi)),
                doppler_rate_hz_s=float(x[2] / (2 * math.pi)),
                frame_phase_s=float(x[3]),
                frame_rate_error_s_s=float(x[4]),
                carrier_phase_sigma_rad=float(math.sqrt(diagonal[0])),
                doppler_sigma_hz=float(math.sqrt(diagonal[1]) / (2 * math.pi)),
                doppler_rate_sigma_hz_s=float(math.sqrt(diagonal[2]) / (2 * math.pi)),
                frame_phase_sigma_s=float(math.sqrt(diagonal[3])),
                phase_slip_detected=phase_slip,
                cfo_correction_detected=correction,
                estimated_cfo_correction_hz=correction_hz,
            )
        )
        previous_time = observation.time_s
    return tuple(estimates)


def extract_probe_frame_measurements(
    samples: npt.NDArray[np.complex128],
    *,
    probe_sample_start: int,
    local_epoch_sample: int,
    sample_rate_hz: int,
    model: PolynomialFrequencyModel,
    edge: StarlinkEdge,
    pilot_symbol_count: int,
    start_time_s: float,
    end_time_s: float,
) -> tuple[RawFrameMeasurement, ...]:
    """Measure prompt phase and phase-slope Doppler on each complete pilot frame."""

    values = np.asarray(samples, dtype=np.complex128)
    if values.ndim != 1 or not values.size:
        raise ValueError("Kalman probe samples must be a nonempty vector")
    if sample_rate_hz <= 0 or probe_sample_start < 0:
        raise ValueError("Kalman probe geometry is invalid")
    if not 8 <= pilot_symbol_count <= 300:
        raise ValueError("Kalman pilot symbol count must lie in 8..300")
    template = np.asarray(qin_edge_pilot_frame(sample_rate_hz, edge), dtype=np.complex128)
    symbols = np.arange(2, 2 + pilot_symbol_count)
    symbol_period = sample_rate_hz * OFDM_SYMBOL_DURATION_S
    local_starts = np.rint(symbols * symbol_period).astype(int)
    local_stops = np.minimum(np.rint((symbols + 1) * symbol_period).astype(int), len(template))
    frame_period = sample_rate_hz / FRAME_RATE_HZ
    frame_starts: list[int] = []
    frame_number = 0
    while True:
        frame_start = local_epoch_sample + round(frame_number * frame_period)
        if frame_start + int(local_stops[-1]) > len(values):
            break
        frame_number += 1
        if frame_start >= 0:
            frame_starts.append(frame_start)
    if not frame_starts:
        return ()
    starts = np.asarray(frame_starts, dtype=int)
    counts = local_stops - local_starts
    correlations = np.zeros((len(starts), len(symbols)), dtype=np.complex128)
    moments = np.zeros((len(starts), len(symbols)), dtype=float)
    for count in np.unique(counts):
        if count < 2:
            continue
        positions = np.flatnonzero(counts == count)
        symbol_offsets = local_starts[positions, None] + np.arange(int(count))[None, :]
        indexes = starts[:, None, None] + symbol_offsets[None, :, :]
        absolute_samples = probe_sample_start + indexes
        times = absolute_samples / sample_rate_hz
        corrected = values[indexes] * np.exp(-1j * model.phase_rad(times))
        reference = template[symbol_offsets]
        correlations[:, positions] = np.sum(np.conj(reference)[None, :, :] * corrected, axis=2)
        moments[:, positions] = np.mean(times, axis=2)

    results: list[RawFrameMeasurement] = []
    for frame_start, correlation, times in zip(frame_starts, correlations, moments, strict=True):
        weights = np.abs(correlation)
        total_weight = float(np.sum(weights))
        if total_weight <= np.finfo(float).tiny:
            continue
        center = float(np.sum(weights * times) / total_weight)
        centered_times = times - center
        angles = np.unwrap(np.angle(correlation))
        mean_angle = float(np.sum(weights * angles) / total_weight)
        denominator = float(np.sum(weights * centered_times**2))
        residual_rate_rad_s = (
            float(np.sum(weights * centered_times * (angles - mean_angle)) / denominator)
            if denominator > np.finfo(float).tiny
            else 0.0
        )
        residual_phase = float(
            np.angle(np.sum(correlation * np.exp(-1j * residual_rate_rad_s * centered_times)))
        )
        coherence = float(
            abs(np.sum(correlation * np.exp(-1j * residual_rate_rad_s * centered_times)))
            / total_weight
        )
        if not start_time_s <= center <= end_time_s:
            continue
        nominal_phase = float(model.phase_rad(center))
        nominal_frequency = float(model.frequency_hz(center))
        results.append(
            RawFrameMeasurement(
                sample_start=probe_sample_start + frame_start,
                time_s=center,
                prompt_coherence=min(max(coherence, 0.0), 1.0),
                carrier_phase_rad=_wrap_rad(nominal_phase + residual_phase),
                doppler_hz=nominal_frequency + residual_rate_rad_s / (2 * math.pi),
            )
        )
    return tuple(results)


def build_standard_kalman_tracking(
    iq: IqReader,
    *,
    path_input_binding_digest: Sha256Digest,
    pilot_scan_digest: Sha256Digest,
    detections: tuple[PilotProbeDetection, ...],
    canonical_bank: DealiasedTrajectoryBankV4,
    final_bank: FinalTrajectoryBankV3,
    feedback_config: TrajectoryFeedbackConfig,
    config: KalmanTrackingConfigV1,
    edge: StarlinkEdge,
) -> StandardKalmanTrackingV1:
    """Build the additive Standard Kalman product through the IQ-reader port."""

    selected = tuple(sorted(final_bank.trajectories, key=lambda item: item.trajectory_id))[
        : config.maximum_tracks
    ]
    model_by_track = {
        item.trajectory_id: PolynomialFrequencyModel(
            item.reference_time_s, tuple(item.absolute_coefficients_hz)
        )
        for item in selected
    }
    raw_source_by_id = raw_candidate_sources(detections)
    canonical_by_id = {item.observation_id: item for item in canonical_bank.observations}
    sources_by_probe: dict[int, list[tuple[str, _CandidateSource]]] = {}
    for track in selected:
        seen_probes: set[int] = set()
        for canonical_id in track.observation_ids:
            canonical = canonical_by_id.get(canonical_id)
            if canonical is None:
                continue
            source = next(
                (
                    raw_source_by_id[source_id]
                    for source_id in canonical.source_observation_ids
                    if source_id in raw_source_by_id
                ),
                None,
            )
            if source is None or source.detection_sample_start in seen_probes:
                continue
            seen_probes.add(source.detection_sample_start)
            sources_by_probe.setdefault(source.detection_sample_start, []).append(
                (track.trajectory_id, source)
            )

    raw_by_track: dict[str, list[RawFrameMeasurement]] = {
        item.trajectory_id: [] for item in selected
    }
    source_frame_counts = {item.trajectory_id: 0 for item in selected}
    probe_stream = iter_pilot_probe_samples(iq, feedback_config) if sources_by_probe else ()
    for probe_start, samples in probe_stream:
        for trajectory_id, source in sources_by_probe.get(probe_start, ()):
            track = next(item for item in selected if item.trajectory_id == trajectory_id)
            measured = extract_probe_frame_measurements(
                samples,
                probe_sample_start=probe_start,
                local_epoch_sample=source.local_epoch_sample,
                sample_rate_hz=iq.sample_rate_hz,
                model=model_by_track[trajectory_id],
                edge=edge,
                pilot_symbol_count=config.pilot_symbol_count,
                start_time_s=track.start_s,
                end_time_s=track.end_s,
            )
            source_frame_counts[trajectory_id] += len(measured)
            remaining = config.maximum_source_frames_per_track - len(raw_by_track[trajectory_id])
            if remaining > 0:
                raw_by_track[trajectory_id].extend(measured[:remaining])

    tracks = tuple(
        _build_track(
            track,
            tuple(raw_by_track[track.trajectory_id]),
            source_frame_count=source_frame_counts[track.trajectory_id],
            sample_rate_hz=iq.sample_rate_hz,
            model=model_by_track[track.trajectory_id],
            config=config,
        )
        for track in selected
    )
    has_complete = any(item.status is StandardScientificStatus.COMPLETE for item in tracks)
    truncated = len(final_bank.trajectories) > len(selected) or any(
        item.truncated_frame_count for item in tracks
    )
    status = (
        StandardScientificStatus.PARTIAL
        if has_complete and truncated
        else StandardScientificStatus.COMPLETE
        if has_complete
        else StandardScientificStatus.INSUFFICIENT_DATA
        if selected
        else StandardScientificStatus.NO_RESULT
    )
    reason = (
        "five-state known-pilot frame tracking completed with bounded truncation"
        if status is StandardScientificStatus.PARTIAL
        else "five-state known-pilot frame tracking completed"
        if status is StandardScientificStatus.COMPLETE
        else "final trajectories had too few known-pilot frames for Kalman tracking"
        if selected
        else "no final CFO trajectory was available for Kalman tracking"
    )
    document: dict[str, Any] = {
        "path_input_binding_digest": path_input_binding_digest,
        "pilot_scan_digest": pilot_scan_digest,
        "dealiased_bank_digest": canonical_bank.content_digest,
        "final_trajectory_bank_digest": final_bank.content_digest,
        "config": config.model_dump(mode="json"),
        "config_digest": config.digest,
        "source_track_count": len(final_bank.trajectories),
        "returned_track_count": len(tracks),
        "truncated_track_count": len(final_bank.trajectories) - len(tracks),
        "tracks": [item.model_dump(mode="json") for item in tracks],
        "status": status,
        "reason": reason,
        "candidate_only": True,
        "known_pilots_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    identity = {
        "schema_version": 1,
        "algorithm_version": "standard-kalman-tracking-v1",
        **document,
    }
    document["content_digest"] = canonical_digest(identity)
    return StandardKalmanTrackingV1.model_validate(document)


def raw_candidate_sources(
    detections: tuple[PilotProbeDetection, ...],
) -> dict[str, _CandidateSource]:
    """Resolve canonical observation IDs to their exact raw probe timing source."""
    result: dict[str, _CandidateSource] = {}
    for detection in detections:
        candidates = detection.candidates
        if not candidates and detection.local_epoch_sample is not None:
            candidates = (
                PilotMethodCandidate(
                    rank=0,
                    local_epoch_sample=detection.local_epoch_sample,
                    acquired_cfo_hz=float(detection.acquired_cfo_hz or 0.0),
                    scores=detection.scores,
                    qam_accuracy=detection.qam_accuracy,
                    qam_evm=detection.qam_evm,
                ),
            )
        for candidate in candidates:
            observation_id = canonical_digest(
                {
                    "sample_start": detection.sample_start,
                    "candidate_rank": candidate.rank,
                    "method": "glrt64",
                }
            )
            result[observation_id] = _CandidateSource(
                detection.sample_start, candidate.local_epoch_sample
            )
    return result


def _build_track(
    track,
    raw: tuple[RawFrameMeasurement, ...],
    *,
    source_frame_count: int,
    sample_rate_hz: int,
    model: PolynomialFrequencyModel,
    config: KalmanTrackingConfigV1,
) -> KalmanTrajectoryTrackV1:
    ordered = tuple(sorted(raw, key=lambda item: (item.sample_start, -item.prompt_coherence)))
    if ordered:
        anchor = ordered[0].sample_start
        by_index: dict[int, KalmanFrameObservation] = {}
        for item in ordered:
            frame_index = round(
                (item.sample_start - anchor) * config.frame_rate_hz / sample_rate_hz
            )
            nominal_start = anchor + round(frame_index * sample_rate_hz / config.frame_rate_hz)
            observation = KalmanFrameObservation(
                frame_index=frame_index,
                sample_start=item.sample_start,
                time_s=item.time_s,
                prompt_coherence=item.prompt_coherence,
                carrier_phase_rad=item.carrier_phase_rad,
                doppler_hz=item.doppler_hz,
                frame_phase_s=(item.sample_start - nominal_start) / sample_rate_hz,
            )
            previous = by_index.get(frame_index)
            if previous is None or observation.prompt_coherence > previous.prompt_coherence:
                by_index[frame_index] = observation
        observations = tuple(by_index[index] for index in sorted(by_index))
    else:
        observations = ()
    initial_rate = float(model.doppler_rate_hz_s(observations[0].time_s)) if observations else 0.0
    estimates = track_frame_observations(
        observations, config, initial_doppler_rate_hz_s=initial_rate
    )
    retained = _bounded_estimates(estimates, config.maximum_returned_frames_per_track)
    frames = tuple(_contract_frame(item) for item in retained)
    complete = len(estimates) >= 2
    return KalmanTrajectoryTrackV1(
        source_trajectory_id=track.trajectory_id,
        source_branch_id=track.branch_id,
        source_frame_count=source_frame_count,
        processed_frame_count=len(estimates),
        returned_frame_count=len(frames),
        omitted_frame_count=len(estimates) - len(frames),
        # Overlapping pilot probes can contribute more than one measurement for
        # the same 750 Hz frame.  Only the strongest observation for that frame
        # reaches the filter, so both bounded input truncation and duplicate
        # collapse belong to the source frames that were not processed.
        truncated_frame_count=source_frame_count - len(estimates),
        measurement_update_count=sum(item.update_applied for item in estimates),
        rejected_measurement_count=sum(not item.update_applied for item in estimates),
        phase_slip_count=sum(item.phase_slip_detected for item in estimates),
        cfo_correction_count=sum(item.cfo_correction_detected for item in estimates),
        status=(
            StandardScientificStatus.COMPLETE
            if complete
            else StandardScientificStatus.INSUFFICIENT_DATA
        ),
        reason=(
            "known-pilot frame phase, Doppler, Doppler-rate, and timing track"
            if complete
            else "fewer than two unique known-pilot frames were available"
        ),
        frames=frames,
    )


def _bounded_estimates(
    estimates: tuple[KalmanFrameEstimate, ...], maximum: int
) -> tuple[KalmanFrameEstimate, ...]:
    if len(estimates) <= maximum:
        return estimates
    indexes = np.rint(np.linspace(0, len(estimates) - 1, maximum)).astype(int)
    return tuple(estimates[int(index)] for index in indexes)


def _contract_frame(estimate: KalmanFrameEstimate) -> KalmanFrameEstimateV1:
    observation = estimate.observation
    return KalmanFrameEstimateV1(
        frame_index=observation.frame_index,
        sample_start=observation.sample_start,
        time_s=observation.time_s,
        prompt_coherence=observation.prompt_coherence,
        measurement_phase_rad=observation.carrier_phase_rad,
        measurement_doppler_hz=observation.doppler_hz,
        measurement_frame_phase_s=observation.frame_phase_s,
        update_applied=estimate.update_applied,
        phase_innovation_rad=estimate.phase_innovation_rad,
        doppler_innovation_hz=estimate.doppler_innovation_hz,
        frame_phase_innovation_s=estimate.frame_phase_innovation_s,
        carrier_phase_rad=estimate.carrier_phase_rad,
        phase_shift_rad=_wrap_rad(estimate.carrier_phase_rad),
        doppler_shift_hz=estimate.doppler_shift_hz,
        doppler_rate_hz_s=estimate.doppler_rate_hz_s,
        frame_phase_s=estimate.frame_phase_s,
        frame_rate_error_s_s=estimate.frame_rate_error_s_s,
        carrier_phase_sigma_rad=estimate.carrier_phase_sigma_rad,
        doppler_sigma_hz=estimate.doppler_sigma_hz,
        doppler_rate_sigma_hz_s=estimate.doppler_rate_sigma_hz_s,
        frame_phase_sigma_s=estimate.frame_phase_sigma_s,
        phase_slip_detected=estimate.phase_slip_detected,
        cfo_correction_detected=estimate.cfo_correction_detected,
        estimated_cfo_correction_hz=estimate.estimated_cfo_correction_hz,
    )


def _wrap_rad(value: float) -> float:
    wrapped = (value + math.pi) % (2 * math.pi) - math.pi
    return math.pi if wrapped == -math.pi and value > 0 else wrapped
