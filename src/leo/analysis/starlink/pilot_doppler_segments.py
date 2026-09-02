"""Piecewise modulo-pi pilot Doppler monitoring for Standard analysis."""

from __future__ import annotations

import io
import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.qam.pilot_phase_locklet import (
    PilotPhaseLockletConfig,
    PilotPhaseLockletResult,
    analyze_contiguous_pilot_phase_locklet,
)
from leo.analysis.qam.pilot_pnt_kalman import (
    PilotPntKalmanConfig,
    PilotPntKalmanConfigV2,
    PilotPntKalmanResult,
    analyze_contiguous_pilot_pnt_kalman,
    analyze_contiguous_pilot_pnt_kalman_v2,
)
from leo.analysis.starlink.kalman_tracking import (
    PolynomialFrequencyModel,
    raw_candidate_sources,
)
from leo.analysis.starlink.local_doppler import (
    complete_lattice_count,
    frequency_line,
    interleaved_held_out_rms,
    line_slope_sigma,
    stable_measurement_floats,
)
from leo.analysis.starlink.pilot_methods import PilotProbeDetection
from leo.analysis.starlink.templates import StarlinkEdge
from leo.contracts.cfo_dealias import DealiasedTrajectoryBankV4, FinalTrajectoryBankV3
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.kalman_tracking import StandardKalmanTrackingV1
from leo.contracts.pilot_doppler_segments import (
    PilotDopplerSegmentConfigV1,
    PilotDopplerSegmentConfigV2,
    PilotDopplerSegmentV1,
    PilotDopplerSegmentV2,
    PilotDopplerTrajectorySummaryV1,
    PilotDopplerTrajectorySummaryV2,
    StandardPilotDopplerSegmentsV1,
    StandardPilotDopplerSegmentsV2,
)
from leo.contracts.standard_pipeline import StandardScientificStatus
from leo.pipeline import IqReader


@dataclass(frozen=True, slots=True)
class _WindowRequest:
    source_trajectory_id: str
    source_branch_id: str
    probe_sample_start: int
    local_epoch_sample: int
    model: PolynomialFrequencyModel
    fractional_epoch_offset_samples: float | None = None


@dataclass(frozen=True, slots=True)
class PilotDopplerSegmentsBundleV3:
    """In-process V2 compatibility product plus index-aligned V3 phase evidence."""

    legacy_v2: StandardPilotDopplerSegmentsV2
    phase_config: PilotPhaseLockletConfig
    phase_locklets: tuple[PilotPhaseLockletResult, ...]

    def __post_init__(self) -> None:
        if len(self.phase_locklets) != len(self.legacy_v2.segments):
            raise ValueError("pilot Doppler V3 phase evidence is not aligned to V2 locklets")


def build_standard_pilot_doppler_segments(
    iq: IqReader,
    *,
    path_input_binding_digest: Sha256Digest,
    pilot_scan_digest: Sha256Digest,
    detections: tuple[PilotProbeDetection, ...],
    canonical_bank: DealiasedTrajectoryBankV4,
    final_bank: FinalTrajectoryBankV3,
    kalman_tracking: StandardKalmanTrackingV1,
    config: PilotDopplerSegmentConfigV1,
    edge: StarlinkEdge,
) -> StandardPilotDopplerSegmentsV1:
    """Replay the immutable V1 segment algorithm exactly."""

    result = _build_standard_pilot_doppler_segments(
        iq,
        path_input_binding_digest=path_input_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        detections=detections,
        canonical_bank=canonical_bank,
        final_bank=final_bank,
        kalman_tracking=kalman_tracking,
        config=config,
        contract_version=1,
        edge=edge,
    )
    if not isinstance(result, StandardPilotDopplerSegmentsV1) or isinstance(
        result, StandardPilotDopplerSegmentsV2
    ):
        raise TypeError("V1 pilot Doppler builder returned the wrong contract")
    return result


def build_standard_pilot_doppler_segments_v2(
    iq: IqReader,
    *,
    path_input_binding_digest: Sha256Digest,
    pilot_scan_digest: Sha256Digest,
    detections: tuple[PilotProbeDetection, ...],
    canonical_bank: DealiasedTrajectoryBankV4,
    final_bank: FinalTrajectoryBankV3,
    kalman_tracking: StandardKalmanTrackingV1,
    config: PilotDopplerSegmentConfigV2,
    edge: StarlinkEdge,
) -> StandardPilotDopplerSegmentsV2:
    """Build corrected independently reacquiring modulo-pi locklets."""

    result = _build_standard_pilot_doppler_segments(
        iq,
        path_input_binding_digest=path_input_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        detections=detections,
        canonical_bank=canonical_bank,
        final_bank=final_bank,
        kalman_tracking=kalman_tracking,
        config=config,
        contract_version=2,
        edge=edge,
    )
    if not isinstance(result, StandardPilotDopplerSegmentsV2):
        raise TypeError("V2 pilot Doppler builder returned the wrong contract")
    return result


def build_standard_pilot_doppler_segments_bundle_v3(
    iq: IqReader,
    *,
    path_input_binding_digest: Sha256Digest,
    pilot_scan_digest: Sha256Digest,
    detections: tuple[PilotProbeDetection, ...],
    canonical_bank: DealiasedTrajectoryBankV4,
    final_bank: FinalTrajectoryBankV3,
    kalman_tracking: StandardKalmanTrackingV1,
    config: PilotDopplerSegmentConfigV2,
    edge: StarlinkEdge,
    phase_config: PilotPhaseLockletConfig | None = None,
) -> PilotDopplerSegmentsBundleV3:
    """Build immutable V2 output and corrected phase evidence in one IQ pass."""

    result = _build_standard_pilot_doppler_segments(
        iq,
        path_input_binding_digest=path_input_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        detections=detections,
        canonical_bank=canonical_bank,
        final_bank=final_bank,
        kalman_tracking=kalman_tracking,
        config=config,
        contract_version=2,
        edge=edge,
        phase_config=phase_config or PilotPhaseLockletConfig(),
    )
    if not isinstance(result, PilotDopplerSegmentsBundleV3):
        raise TypeError("V3 pilot Doppler bundle builder returned the wrong result")
    return result


def _build_standard_pilot_doppler_segments(
    iq: IqReader,
    *,
    path_input_binding_digest: Sha256Digest,
    pilot_scan_digest: Sha256Digest,
    detections: tuple[PilotProbeDetection, ...],
    canonical_bank: DealiasedTrajectoryBankV4,
    final_bank: FinalTrajectoryBankV3,
    kalman_tracking: StandardKalmanTrackingV1,
    config: PilotDopplerSegmentConfigV1 | PilotDopplerSegmentConfigV2,
    contract_version: int,
    edge: StarlinkEdge,
    phase_config: PilotPhaseLockletConfig | None = None,
) -> StandardPilotDopplerSegmentsV1 | StandardPilotDopplerSegmentsV2 | PilotDopplerSegmentsBundleV3:
    """Analyze disjoint complete-frame windows on every bounded final trajectory."""

    if contract_version not in (1, 2):
        raise ValueError("pilot Doppler contract version must be 1 or 2")
    if contract_version == 2 and not isinstance(config, PilotDopplerSegmentConfigV2):
        raise TypeError("pilot Doppler V2 requires its additive V2 configuration")
    if phase_config is not None and contract_version != 2:
        raise ValueError("pilot phase-locklet evidence requires the V2 compatibility product")

    selected_tracks = tuple(sorted(final_bank.trajectories, key=lambda item: item.trajectory_id))[
        : config.maximum_tracks
    ]
    raw_source_by_id = raw_candidate_sources(detections)
    canonical_by_id = {item.observation_id: item for item in canonical_bank.observations}
    requests_by_track: dict[str, tuple[_WindowRequest, ...]] = {}
    sample_count = round(config.window_duration_s * iq.sample_rate_hz)
    minimum_separation_samples = round(config.minimum_window_separation_s * iq.sample_rate_hz)
    for track in selected_tracks:
        model = PolynomialFrequencyModel(
            track.reference_time_s, tuple(track.absolute_coefficients_hz)
        )
        candidates: list[_WindowRequest] = []
        seen_probe_starts: set[int] = set()
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
            if source is None or source.detection_sample_start in seen_probe_starts:
                continue
            probe_start = source.detection_sample_start
            start_s = probe_start / iq.sample_rate_hz
            if (
                probe_start + sample_count > iq.sample_count
                or start_s < track.start_s
                or start_s + config.window_duration_s > track.end_s
            ):
                continue
            seen_probe_starts.add(probe_start)
            candidates.append(
                _WindowRequest(
                    source_trajectory_id=track.trajectory_id,
                    source_branch_id=track.branch_id,
                    probe_sample_start=probe_start,
                    local_epoch_sample=source.local_epoch_sample,
                    model=model,
                )
            )
        separated: list[_WindowRequest] = []
        for request in sorted(candidates, key=lambda item: item.probe_sample_start):
            if (
                not separated
                or request.probe_sample_start - separated[-1].probe_sample_start
                >= minimum_separation_samples
            ):
                separated.append(request)
        requests_by_track[track.trajectory_id] = _evenly_bounded(
            tuple(separated), config.maximum_windows_per_track
        )

    all_requests = tuple(
        sorted(
            (request for group in requests_by_track.values() for request in group),
            key=lambda item: (item.probe_sample_start, item.source_trajectory_id),
        )
    )
    analyzed_by_track: dict[str, list[dict[str, Any]]] = {
        track.trajectory_id: [] for track in selected_tracks
    }
    phase_by_request: dict[tuple[str, int], PilotPhaseLockletResult] = {}
    for request, samples in _iter_requested_windows(iq, all_requests, sample_count):
        initial_absolute_cfo_hz = float(
            request.model.frequency_hz(request.probe_sample_start / iq.sample_rate_hz)
        )
        if contract_version == 2:
            result = analyze_contiguous_pilot_pnt_kalman_v2(
                samples,
                iq.sample_rate_hz,
                epoch_sample=request.local_epoch_sample,
                initial_absolute_cfo_hz=initial_absolute_cfo_hz,
                edge=edge,
                maximum_residual_cfo_hz=config.maximum_residual_cfo_hz,
                config=PilotPntKalmanConfigV2(),
            )
            if phase_config is not None:
                phase_by_request[(request.source_trajectory_id, request.probe_sample_start)] = (
                    analyze_contiguous_pilot_phase_locklet(
                        samples,
                        iq.sample_rate_hz,
                        epoch_sample=request.local_epoch_sample,
                        initial_absolute_cfo_hz=initial_absolute_cfo_hz,
                        edge=edge,
                        maximum_residual_cfo_hz=config.maximum_residual_cfo_hz,
                        config=phase_config,
                    )
                )
        else:
            result = analyze_contiguous_pilot_pnt_kalman(
                samples,
                iq.sample_rate_hz,
                epoch_sample=request.local_epoch_sample,
                initial_absolute_cfo_hz=initial_absolute_cfo_hz,
                edge=edge,
                maximum_residual_cfo_hz=config.maximum_residual_cfo_hz,
                config=PilotPntKalmanConfig(),
            )
        analyzed_by_track[request.source_trajectory_id].append(
            _segment_document(
                request,
                result,
                iq.sample_rate_hz,
                config,
                contract_version=contract_version,
            )
        )

    segment_documents: list[dict[str, Any]] = []
    ordered_phase_locklets: list[PilotPhaseLockletResult] = []
    summaries: list[PilotDopplerTrajectorySummaryV1 | PilotDopplerTrajectorySummaryV2] = []
    for track in selected_tracks:
        previous_bias: float | None = None
        track_documents = analyzed_by_track[track.trajectory_id]
        for segment_document in sorted(track_documents, key=lambda item: item["start_time_s"]):
            bias = segment_document["carrier_bias_at_reference_hz"]
            segment_document["carrier_bias_change_hz"] = (
                None if previous_bias is None or bias is None else float(bias - previous_bias)
            )
            if bias is not None:
                previous_bias = float(bias)
            segment_document["segment_index"] = len(segment_documents)
            segment_documents.append(segment_document)
            if phase_config is not None:
                ordered_phase_locklets.append(
                    phase_by_request[
                        (
                            str(segment_document["source_trajectory_id"]),
                            int(segment_document["source_probe_sample_start"]),
                        )
                    ]
                )
        qualified = [item for item in track_documents if item["qualified"]]
        summary_document: dict[str, Any] = {
            "source_trajectory_id": track.trajectory_id,
            "source_branch_id": track.branch_id,
            "candidate_window_count": len(requests_by_track[track.trajectory_id]),
            "analyzed_segment_count": len(track_documents),
            "qualified_segment_count": len(qualified),
            "median_qualified_local_rate_hz_s": _median_optional(
                item["local_doppler_rate_hz_s"] for item in qualified
            ),
            "median_qualified_kalman_rate_hz_s": _median_optional(
                item["kalman_doppler_rate_hz_s"] for item in qualified
            ),
            "median_qualified_frozen_rate_hz_s": _median_optional(
                item["frozen_doppler_rate_hz_s"] for item in qualified
            ),
        }
        if contract_version == 2:
            summary_document["reacquisition_count"] = sum(
                int(item["reacquisition_count"]) for item in track_documents
            )
            summaries.append(PilotDopplerTrajectorySummaryV2.model_validate(summary_document))
        else:
            summaries.append(PilotDopplerTrajectorySummaryV1.model_validate(summary_document))

    segment_model = PilotDopplerSegmentV2 if contract_version == 2 else PilotDopplerSegmentV1
    segments = tuple(segment_model.model_validate(item) for item in segment_documents)
    qualified_count = sum(item.qualified for item in segments)
    status = (
        StandardScientificStatus.PARTIAL
        if qualified_count and len(selected_tracks) < len(final_bank.trajectories)
        else StandardScientificStatus.COMPLETE
        if qualified_count
        else StandardScientificStatus.INSUFFICIENT_DATA
        if selected_tracks
        else StandardScientificStatus.NO_RESULT
    )
    reason = (
        "piecewise modulo-pi pilot Doppler segments completed with bounded track truncation"
        if status is StandardScientificStatus.PARTIAL
        else "piecewise modulo-pi pilot Doppler segments completed"
        if status is StandardScientificStatus.COMPLETE
        else "no selected final trajectory supplied a qualified complete-lattice segment"
        if selected_tracks
        else "no final trajectory was available for pilot Doppler segmentation"
    )
    document: dict[str, Any] = {
        "path_input_binding_digest": path_input_binding_digest,
        "pilot_scan_digest": pilot_scan_digest,
        "dealiased_bank_digest": canonical_bank.content_digest,
        "final_trajectory_bank_digest": final_bank.content_digest,
        "kalman_tracking_digest": kalman_tracking.content_digest,
        "config": config.model_dump(mode="json"),
        "config_digest": config.digest,
        "source_track_count": len(final_bank.trajectories),
        "analyzed_track_count": len(selected_tracks),
        "truncated_track_count": len(final_bank.trajectories) - len(selected_tracks),
        "candidate_window_count": len(all_requests),
        "analyzed_segment_count": len(segments),
        "qualified_segment_count": qualified_count,
        # Multi-threaded linear algebra can differ below meaningful RF precision.
        # Stabilize only persisted measurement floats before hashing; all gates
        # above were evaluated at full precision and config values stay exact.
        "trajectory_summaries": [
            stable_measurement_floats(item.model_dump(mode="json")) for item in summaries
        ],
        "segments": [stable_measurement_floats(item.model_dump(mode="json")) for item in segments],
        "status": status,
        "reason": reason,
        "carrier_phase_period_rad": math.pi,
        "carrier_discontinuities_are_piecewise_bias": True,
        "frame_timing_is_receiver_relative": True,
        "absolute_carrier_phase_resolved": False,
        "candidate_only": True,
        "known_pilots_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    if contract_version == 2:
        document["phase_reacquisition_policy"] = "independent-phase-v2"
        document["legacy_kalman_is_diagnostic_only"] = True
        document["primary_rate_estimator"] = "direct-local-frequency-line"
        document["kalman_rate_is_diagnostic_only"] = True
    algorithm_version = f"standard-pilot-doppler-segments-v{contract_version}"
    identity = {
        "schema_version": contract_version,
        "algorithm_version": algorithm_version,
        **document,
    }
    document["content_digest"] = canonical_digest(identity)
    if contract_version == 2:
        legacy_v2 = StandardPilotDopplerSegmentsV2.model_validate(document)
        if phase_config is not None:
            return PilotDopplerSegmentsBundleV3(
                legacy_v2=legacy_v2,
                phase_config=phase_config,
                phase_locklets=tuple(ordered_phase_locklets),
            )
        return legacy_v2
    return StandardPilotDopplerSegmentsV1.model_validate(document)


def _segment_document(
    request: _WindowRequest,
    result: PilotPntKalmanResult,
    sample_rate_hz: int,
    config: PilotDopplerSegmentConfigV1 | PilotDopplerSegmentConfigV2,
    *,
    contract_version: int = 1,
) -> dict[str, Any]:
    start_s = request.probe_sample_start / sample_rate_hz
    end_s = start_s + config.window_duration_s
    supported = [item for item in result.frames if item.measurement_supported]
    window_samples = round(config.window_duration_s * sample_rate_hz)
    lattice_count = complete_lattice_count(
        window_samples, sample_rate_hz, request.local_epoch_sample
    )
    supported_fraction = len(supported) / lattice_count if lattice_count else 0.0
    relative_times = np.asarray([item.time_s for item in supported], dtype=float)
    absolute_times = start_s + relative_times
    frequencies = np.asarray([item.absolute_cfo_measurement_hz for item in supported], dtype=float)
    fit = frequency_line(relative_times, frequencies)
    held_out_rms = interleaved_held_out_rms(relative_times, frequencies)
    reference_time_s = start_s + fit.reference_time_s if fit is not None else (start_s + end_s) / 2
    local_rate = None if fit is None else fit.slope_hz_per_s
    local_cfo = None if fit is None else fit.intercept_at_reference_hz
    frozen_rate = float(request.model.doppler_rate_hz_s(reference_time_s))
    frozen_cfo = float(request.model.frequency_hz(reference_time_s))
    kalman_rate = result.frames[-1].tracked_doppler_rate_hz_s if result.frames else None
    gaps = np.diff(absolute_times)
    maximum_gap = float(np.max(gaps)) if gaps.size else None
    phase_rms = (
        float(math.sqrt(np.mean([item.phase_innovation_modulo_pi_rad**2 for item in supported])))
        if supported
        else None
    )
    median_margin = _median_optional(item.coherence_margin for item in supported)
    failures: list[str] = []
    if supported_fraction < config.minimum_supported_frame_fraction:
        failures.append("supported frame coverage below threshold")
    if maximum_gap is None or maximum_gap > config.maximum_supported_frame_gap_s:
        failures.append("supported frame gap exceeds threshold")
    if not result.phase_lock_qualified:
        failures.append("modulo-pi phase lock did not qualify")
    if median_margin is None or median_margin < config.minimum_median_coherence_margin:
        failures.append("exact-versus-control coherence margin below threshold")
    if fit is None:
        failures.append("too few supported frames for a local frequency line")
    elif fit.residual_rms_hz > config.maximum_frequency_line_rms_hz:
        failures.append("local frequency-line RMS exceeds threshold")
    if held_out_rms is None:
        failures.append("too few supported frames for interleaved held-out prediction")
    elif held_out_rms > config.maximum_held_out_frequency_rms_hz:
        failures.append("held-out local frequency prediction RMS exceeds threshold")
    disagreement = None if local_rate is None or kalman_rate is None else local_rate - kalman_rate
    if contract_version == 1 and (
        disagreement is None
        or abs(disagreement) > config.maximum_local_kalman_rate_disagreement_hz_s
    ):
        failures.append("local-line and Kalman Doppler rates disagree")
    document = {
        "segment_index": 0,
        "source_trajectory_id": request.source_trajectory_id,
        "source_branch_id": request.source_branch_id,
        "source_probe_sample_start": request.probe_sample_start,
        "start_time_s": start_s,
        "end_time_s": end_s,
        "reference_time_s": reference_time_s,
        "lattice_frame_count": lattice_count,
        "supported_frame_count": len(supported),
        "phase_update_count": result.phase_update_count,
        "frequency_update_count": result.frequency_update_count,
        "timing_update_count": result.timing_update_count,
        "supported_frame_fraction": supported_fraction,
        "maximum_supported_frame_gap_s": maximum_gap,
        "median_exact_coherence": _median_optional(item.exact_coherence for item in supported),
        "median_control_coherence": _median_optional(item.control_coherence for item in supported),
        "median_coherence_margin": median_margin,
        "phase_innovation_rms_rad": phase_rms,
        "phase_ambiguity_transition_count": result.phase_ambiguity_transition_count,
        "local_doppler_rate_hz_s": local_rate,
        "local_doppler_rate_sigma_hz_s": line_slope_sigma(relative_times, fit),
        "kalman_doppler_rate_hz_s": kalman_rate,
        "frozen_doppler_rate_hz_s": frozen_rate,
        "local_minus_kalman_rate_hz_s": disagreement,
        "local_minus_frozen_rate_hz_s": (None if local_rate is None else local_rate - frozen_rate),
        "local_cfo_at_reference_hz": local_cfo,
        "frozen_cfo_at_reference_hz": frozen_cfo,
        "carrier_bias_at_reference_hz": (None if local_cfo is None else local_cfo - frozen_cfo),
        "carrier_bias_change_hz": None,
        "frequency_line_rms_hz": None if fit is None else fit.residual_rms_hz,
        "held_out_frequency_rms_hz": held_out_rms,
        "final_fractional_timing_samples": (
            result.frames[-1].tracked_fractional_timing_samples if result.frames else None
        ),
        "final_timing_rate_s_s": (
            result.frames[-1].tracked_timing_rate_s_s if result.frames else None
        ),
        "phase_lock_qualified": result.phase_lock_qualified,
        "qualified": not failures,
        "qualification_failures": tuple(failures),
    }
    if contract_version == 2:
        document["reacquisition_count"] = result.reacquisition_count
        document["filter_version"] = "pilot-pnt-kalman-v2"
        document["primary_rate_estimator"] = "direct-local-frequency-line"
        document["kalman_rate_is_diagnostic_only"] = True
    return document


def _evenly_bounded(
    requests: tuple[_WindowRequest, ...], maximum: int
) -> tuple[_WindowRequest, ...]:
    if len(requests) <= maximum:
        return requests
    indexes = np.rint(np.linspace(0, len(requests) - 1, maximum)).astype(int)
    return tuple(requests[int(index)] for index in indexes)


def _iter_requested_windows(
    iq: IqReader,
    requests: tuple[_WindowRequest, ...],
    window_samples: int,
) -> Iterable[tuple[_WindowRequest, np.ndarray]]:
    """Yield requested windows during one bounded sequential IQ pass."""

    if not requests:
        return
    pending = np.empty(0, dtype=np.complex128)
    pending_start = 0
    expected_start = 0
    request_index = 0
    for block in iq.iter_blocks(block_samples=2**20):
        if block.metadata.session_sample_start != expected_start:
            raise ValueError("pilot Doppler segmentation requires contiguous IQ coverage")
        values = (
            block.samples[:, 0, 0].astype(np.float64)
            + 1j * block.samples[:, 0, 1].astype(np.float64)
        ) / 32_768.0
        if not pending.size:
            pending_start = expected_start
        pending = np.concatenate((pending, values))
        expected_start += block.metadata.sample_count
        pending_end = pending_start + len(pending)
        while request_index < len(requests):
            request = requests[request_index]
            stop = request.probe_sample_start + window_samples
            if stop > pending_end:
                break
            if request.probe_sample_start < pending_start:
                raise ValueError("pilot Doppler window fell behind the bounded IQ buffer")
            offset = request.probe_sample_start - pending_start
            yield request, np.ascontiguousarray(pending[offset : offset + window_samples])
            request_index += 1
        retain_start = (
            requests[request_index].probe_sample_start
            if request_index < len(requests)
            else expected_start
        )
        drop = min(max(retain_start - pending_start, 0), len(pending))
        if drop:
            pending = pending[drop:]
            pending_start += drop
        if request_index == len(requests):
            return
    if request_index != len(requests):
        raise ValueError("IQ source ended before all pilot Doppler windows were available")


def _median_optional(values: Iterable[float | None]) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(value)]
    return float(np.median(finite)) if finite else None


def render_standard_pilot_doppler_segments_png(
    product: StandardPilotDopplerSegmentsV1 | StandardPilotDopplerSegmentsV2,
    *,
    session_id: str,
    path_label: str,
) -> bytes:
    """Render the replaceable Standard monitoring view from only the durable product."""

    figure = Figure(figsize=(15, 10.5), constrained_layout=True)
    canvas = FigureCanvasAgg(figure)
    axes = figure.subplots(2, 2)
    segments = product.segments
    qualified = np.asarray([item.qualified for item in segments], dtype=bool)
    times = np.asarray([item.reference_time_s for item in segments], dtype=float)
    local = np.asarray(
        [
            math.nan if item.local_doppler_rate_hz_s is None else item.local_doppler_rate_hz_s
            for item in segments
        ]
    )
    kalman = np.asarray(
        [
            math.nan if item.kalman_doppler_rate_hz_s is None else item.kalman_doppler_rate_hz_s
            for item in segments
        ]
    )
    frozen = np.asarray([item.frozen_doppler_rate_hz_s for item in segments], dtype=float)
    colors = np.where(qualified, "#d48806", "#aeb8c2")
    axes[0, 0].scatter(times, local / 1e3, c=colors, s=28, label="direct local line")
    axes[0, 0].scatter(
        times,
        kalman / 1e3,
        color="#2f83b7",
        s=18,
        marker="x",
        label="modulo-pi Kalman",
    )
    axes[0, 0].scatter(
        times,
        frozen / 1e3,
        color="#17394d",
        s=14,
        marker=".",
        label="frozen trajectory",
    )
    axes[0, 0].set_title(
        "A · Doppler-rate estimates; amber segments passed every gate",
        loc="left",
        fontweight="bold",
    )
    axes[0, 0].set_ylabel("receiver-relative rate (kHz/s)")
    axes[0, 0].legend(fontsize=8)

    discrepancy = local - frozen
    axes[0, 1].axhline(0, color="#17394d", linewidth=1)
    axes[0, 1].scatter(times, discrepancy / 1e3, c=colors, s=28)
    axes[0, 1].set_title("B · Local minus frozen rate", loc="left", fontweight="bold")
    axes[0, 1].set_ylabel("rate discrepancy (kHz/s)")

    coverage = np.asarray([item.supported_frame_fraction for item in segments])
    heldout = np.asarray(
        [
            math.nan if item.held_out_frequency_rms_hz is None else item.held_out_frequency_rms_hz
            for item in segments
        ]
    )
    axes[1, 0].scatter(coverage, heldout, c=colors, s=28)
    axes[1, 0].axvline(
        product.config.minimum_supported_frame_fraction,
        color="#d62728",
        linestyle="--",
    )
    axes[1, 0].axhline(
        product.config.maximum_held_out_frequency_rms_hz,
        color="#d62728",
        linestyle="--",
    )
    axes[1, 0].set_title("C · Coverage and held-out prediction gate", loc="left", fontweight="bold")
    axes[1, 0].set_xlabel("supported complete-frame fraction")
    axes[1, 0].set_ylabel("interleaved held-out RMS (Hz)")

    bias = np.asarray(
        [
            math.nan
            if item.carrier_bias_at_reference_hz is None
            else item.carrier_bias_at_reference_hz
            for item in segments
        ]
    )
    axes[1, 1].scatter(times, bias, c=colors, s=28)
    for left, right in zip(segments, segments[1:], strict=False):
        if left.source_trajectory_id != right.source_trajectory_id:
            axes[1, 1].axvline(right.reference_time_s, color="#d62728", alpha=0.25)
    axes[1, 1].set_title("D · Piecewise carrier-bias state", loc="left", fontweight="bold")
    axes[1, 1].set_ylabel("local CFO minus frozen CFO (Hz)")

    for axis in axes.flat:
        axis.grid(alpha=0.22)
        if axis is not axes[1, 0]:
            axis.set_xlabel("capture time (s)")
    figure.suptitle(
        "Standard pilot Doppler segments\n"
        f"{session_id} · {path_label} · "
        f"{product.qualified_segment_count}/{product.analyzed_segment_count} qualified",
        fontsize=16,
        fontweight="bold",
    )
    payload = io.BytesIO()
    canvas.print_png(payload)
    return payload.getvalue()


def render_standard_pilot_carrier_tracking_png(
    kalman_tracking: StandardKalmanTrackingV1,
    final_bank: FinalTrajectoryBankV3,
    pilot_segments: StandardPilotDopplerSegmentsV1 | StandardPilotDopplerSegmentsV2,
    *,
    session_id: str,
    path_label: str,
) -> bytes:
    """Render frame CFO residuals and carrier-rate state like panels A and C."""

    if pilot_segments.kalman_tracking_digest != kalman_tracking.content_digest:
        raise ValueError("pilot carrier plot inputs disagree on Kalman evidence")
    if pilot_segments.final_trajectory_bank_digest != final_bank.content_digest:
        raise ValueError("pilot carrier plot inputs disagree on frozen trajectories")
    models = {
        item.trajectory_id: PolynomialFrequencyModel(
            item.reference_time_s,
            tuple(item.absolute_coefficients_hz),
        )
        for item in final_bank.trajectories
    }
    figure = Figure(figsize=(15.5, 6.8), constrained_layout=True)
    canvas = FigureCanvasAgg(figure)
    cfo_axis, rate_axis = figure.subplots(1, 2)
    colors = ("#277da1", "#43aa8b", "#9d4edd", "#d1495b", "#f8961e")
    accepted_frames = 0
    rejected_frames = 0
    accepted_measurement_residuals: list[float] = []
    tracked_residuals: list[float] = []
    tracked_rates: list[float] = []
    for track_index, track in enumerate(kalman_tracking.tracks):
        model = models.get(track.source_trajectory_id)
        if model is None or not track.frames:
            continue
        color = colors[track_index % len(colors)]
        times = np.asarray([item.time_s for item in track.frames], dtype=float)
        updates = np.asarray([item.update_applied for item in track.frames], dtype=bool)
        measured = np.asarray([item.measurement_doppler_hz for item in track.frames], dtype=float)
        tracked = np.asarray([item.doppler_shift_hz for item in track.frames], dtype=float)
        frame_rates = np.asarray([item.doppler_rate_hz_s for item in track.frames], dtype=float)
        frozen_cfo = model.frequency_hz(times)
        frozen_rates = model.doppler_rate_hz_s(times)
        measurement_residual = measured - frozen_cfo
        tracked_residual = tracked - frozen_cfo
        accepted_frames += int(np.count_nonzero(updates))
        rejected_frames += int(np.count_nonzero(~updates))
        accepted_measurement_residuals.extend(measurement_residual[updates])
        tracked_residuals.extend(tracked_residual)
        tracked_rates.extend(frame_rates)
        if np.any(~updates):
            cfo_axis.scatter(
                times[~updates],
                measurement_residual[~updates],
                s=9,
                color="#aeb8c2",
                alpha=0.28,
                marker="x",
                label="rejected/coasted frame",
            )
            rate_axis.scatter(
                times[~updates],
                frame_rates[~updates] / 1_000,
                s=9,
                color="#aeb8c2",
                alpha=0.28,
                marker="x",
                label="coasted rate state",
            )
        if np.any(updates):
            cfo_axis.scatter(
                times[updates],
                measurement_residual[updates],
                s=11,
                color=color,
                alpha=0.48,
                label="accepted frame CFO residual",
            )
            cfo_axis.scatter(
                times[updates],
                tracked_residual[updates],
                color="#d48806",
                s=9,
                alpha=0.62,
                label="tracked CFO residual",
            )
            rate_axis.scatter(
                times[updates],
                frame_rates[updates] / 1_000,
                s=10,
                color="#d48806",
                alpha=0.58,
                label="tracked rate on accepted frames",
            )
        rate_axis.plot(
            times,
            frozen_rates / 1_000,
            color="#17394d",
            linewidth=1.5,
            label="frozen trajectory rate",
        )
    for segment in pilot_segments.segments:
        span_color = "#d48806" if segment.qualified else "#aeb8c2"
        for axis in (cfo_axis, rate_axis):
            axis.axvspan(segment.start_time_s, segment.end_time_s, color=span_color, alpha=0.035)
    cfo_limits = _robust_display_limits(accepted_measurement_residuals, minimum_span=2_000.0)
    cfo_axis.set_ylim(*cfo_limits)
    rate_references = [
        value
        for segment in pilot_segments.segments
        for value in (
            segment.local_doppler_rate_hz_s,
            segment.kalman_doppler_rate_hz_s if segment.qualified else None,
            segment.frozen_doppler_rate_hz_s,
        )
        if value is not None
    ]
    rate_limits = _robust_display_limits(
        rate_references or tracked_rates,
        minimum_span=20_000.0,
    )
    rate_axis.set_ylim(rate_limits[0] / 1_000, rate_limits[1] / 1_000)
    clipped_cfo = sum(value < cfo_limits[0] or value > cfo_limits[1] for value in tracked_residuals)
    clipped_rate = sum(value < rate_limits[0] or value > rate_limits[1] for value in tracked_rates)
    if clipped_cfo:
        cfo_axis.text(
            0.99,
            0.02,
            f"{clipped_cfo} tracked-state outliers outside robust display range",
            transform=cfo_axis.transAxes,
            ha="right",
            va="bottom",
            fontsize=8,
            color="#6b7280",
        )
    if clipped_rate:
        rate_axis.text(
            0.99,
            0.02,
            f"{clipped_rate} tracked-rate outliers outside physical-reference display range",
            transform=rate_axis.transAxes,
            ha="right",
            va="bottom",
            fontsize=8,
            color="#6b7280",
        )
    cfo_axis.axhline(0, color="#17394d", linewidth=0.8)
    cfo_axis.set_title(
        f"A · Frame CFO residuals vs frozen model ({accepted_frames} accepted; "
        f"{rejected_frames} coasted)",
        loc="left",
        fontweight="bold",
    )
    cfo_axis.set_ylabel("CFO residual vs frozen trajectory (Hz)")
    rate_axis.set_title(
        "C · Carrier-rate state across independently timed pilot frames",
        loc="left",
        fontweight="bold",
    )
    rate_axis.set_ylabel("receiver-relative Doppler/CFO rate (kHz/s)")
    for axis in (cfo_axis, rate_axis):
        axis.set_xlabel("capture time (s)")
        axis.grid(alpha=0.22)
        handles, labels = axis.get_legend_handles_labels()
        unique = dict(zip(labels, handles, strict=True))
        if unique:
            axis.legend(unique.values(), unique.keys(), fontsize=8, loc="best")
    figure.suptitle(
        "Standard frame-level pilot carrier tracking\n"
        f"{session_id} · {path_label} · shaded regions are independent "
        f"{1_000 * pilot_segments.config.window_duration_s:.0f} ms segments",
        fontsize=15,
        fontweight="bold",
    )
    payload = io.BytesIO()
    canvas.print_png(payload)
    return payload.getvalue()


def render_standard_pilot_carrier_tracking_v2_png(
    pilot_segments: StandardPilotDopplerSegmentsV2,
    *,
    session_id: str,
    path_label: str,
) -> bytes:
    """Render only corrected V2 locklet evidence, never the legacy V1 state."""

    figure = Figure(figsize=(15.5, 6.8), constrained_layout=True)
    canvas = FigureCanvasAgg(figure)
    phase_axis, rate_axis = figure.subplots(1, 2)
    segments = pilot_segments.segments
    times = np.asarray([item.reference_time_s for item in segments], dtype=float)
    qualified = np.asarray([item.qualified for item in segments], dtype=bool)
    colors = np.where(qualified, "#d48806", "#aeb8c2")
    phase_rms = np.asarray(
        [
            math.nan if item.phase_innovation_rms_rad is None else item.phase_innovation_rms_rad
            for item in segments
        ],
        dtype=float,
    )
    phase_update_fraction = np.asarray(
        [
            item.phase_update_count / item.lattice_frame_count if item.lattice_frame_count else 0.0
            for item in segments
        ],
        dtype=float,
    )
    reacquisitions = np.asarray([item.reacquisition_count for item in segments], dtype=int)
    sizes = 24.0 + 14.0 * np.minimum(reacquisitions, 4)
    phase_axis.scatter(times, phase_rms, c=colors, s=sizes)
    phase_axis.axhline(0.5, color="#d62728", linestyle="--", label="V2 phase RMS gate")
    for time_s, rms, count in zip(times, phase_rms, reacquisitions, strict=True):
        if count and math.isfinite(rms):
            phase_axis.annotate(
                f"R{count}",
                (time_s, rms),
                xytext=(3, 4),
                textcoords="offset points",
                fontsize=7,
                color="#6b7280",
            )
    update_axis = phase_axis.twinx()
    update_axis.scatter(
        times,
        phase_update_fraction,
        marker="x",
        s=20,
        color="#277da1",
        alpha=0.65,
        label="phase-update fraction",
    )
    update_axis.axhline(0.8, color="#277da1", linestyle=":", alpha=0.7)
    update_axis.set_ylim(-0.02, 1.02)
    update_axis.set_ylabel("phase-update fraction")
    phase_axis.set_title(
        "A · Corrected modulo-π locklets; R labels are reacquisitions",
        loc="left",
        fontweight="bold",
    )
    phase_axis.set_ylabel("phase innovation RMS (rad)")

    local = np.asarray(
        [
            math.nan if item.local_doppler_rate_hz_s is None else item.local_doppler_rate_hz_s
            for item in segments
        ],
        dtype=float,
    )
    tracked = np.asarray(
        [
            math.nan if item.kalman_doppler_rate_hz_s is None else item.kalman_doppler_rate_hz_s
            for item in segments
        ],
        dtype=float,
    )
    frozen = np.asarray([item.frozen_doppler_rate_hz_s for item in segments], dtype=float)
    rate_axis.scatter(
        times,
        local / 1_000,
        c=colors,
        s=32,
        label="direct 75 ms line",
    )
    rate_axis.scatter(
        times,
        tracked / 1_000,
        color="#277da1",
        marker="x",
        s=26,
        label="V2 Kalman rate (diagnostic only)",
    )
    rate_axis.scatter(
        times,
        frozen / 1_000,
        color="#17394d",
        marker=".",
        s=18,
        label="frozen GLRT trajectory",
    )
    rate_axis.set_title(
        "B · Segment-local rate; no dwell-long phase state is claimed",
        loc="left",
        fontweight="bold",
    )
    rate_axis.set_ylabel("receiver-relative Doppler/CFO rate (kHz/s)")
    if not segments:
        phase_axis.text(
            0.5,
            0.5,
            pilot_segments.reason,
            transform=phase_axis.transAxes,
            ha="center",
            va="center",
        )
    for axis in (phase_axis, rate_axis):
        axis.set_xlabel("capture time (s)")
        axis.grid(alpha=0.22)
        handles, labels = axis.get_legend_handles_labels()
        unique = dict(zip(labels, handles, strict=True))
        if unique:
            axis.legend(unique.values(), unique.keys(), fontsize=8, loc="best")
    figure.suptitle(
        "Standard V2 pilot carrier locklets\n"
        f"{session_id} · {path_label} · {pilot_segments.qualified_segment_count}/"
        f"{pilot_segments.analyzed_segment_count} qualified · "
        f"{sum(reacquisitions)} reacquisitions",
        fontsize=15,
        fontweight="bold",
    )
    payload = io.BytesIO()
    canvas.print_png(payload)
    return payload.getvalue()


def _robust_display_limits(
    values: Iterable[float],
    *,
    minimum_span: float,
) -> tuple[float, float]:
    finite = np.asarray([value for value in values if math.isfinite(value)], dtype=float)
    if not finite.size:
        return (-minimum_span / 2, minimum_span / 2)
    lower, upper = (float(value) for value in np.quantile(finite, (0.005, 0.995)))
    center = (lower + upper) / 2
    span = max(minimum_span, (upper - lower) * 1.15)
    return center - span / 2, center + span / 2


def render_standard_pilot_segment_rates_png(
    product: StandardPilotDopplerSegmentsV1 | StandardPilotDopplerSegmentsV2,
    *,
    session_id: str,
    path_label: str,
) -> bytes:
    """Render direct, Kalman, and frozen rates over every local segment interval."""

    figure = Figure(figsize=(15.5, 6.2), constrained_layout=True)
    canvas = FigureCanvasAgg(figure)
    axis = figure.subplots(1, 1)
    for segment in product.segments:
        color = "#d48806" if segment.qualified else "#aeb8c2"
        if segment.local_doppler_rate_hz_s is not None:
            local = segment.local_doppler_rate_hz_s / 1_000
            axis.hlines(
                local,
                segment.start_time_s,
                segment.end_time_s,
                color=color,
                linewidth=3.0 if segment.qualified else 1.5,
                alpha=0.9,
                label=(
                    "qualified direct local rate"
                    if segment.qualified
                    else "failed-gate direct rate"
                ),
            )
            if segment.local_doppler_rate_sigma_hz_s is not None:
                sigma = segment.local_doppler_rate_sigma_hz_s / 1_000
                axis.fill_between(
                    (segment.start_time_s, segment.end_time_s),
                    local - sigma,
                    local + sigma,
                    color=color,
                    alpha=0.10,
                )
        if segment.kalman_doppler_rate_hz_s is not None:
            axis.scatter(
                segment.reference_time_s,
                segment.kalman_doppler_rate_hz_s / 1_000,
                color="#277da1",
                marker="x",
                s=42,
                label="segment-final modulo-π Kalman rate",
            )
        axis.hlines(
            segment.frozen_doppler_rate_hz_s / 1_000,
            segment.start_time_s,
            segment.end_time_s,
            color="#17394d",
            linestyle="--",
            linewidth=1.1,
            label="frozen trajectory rate over segment",
        )
    if not product.segments:
        axis.text(0.5, 0.5, product.reason, transform=axis.transAxes, ha="center", va="center")
    axis.axhline(0, color="#17394d", linewidth=0.7, alpha=0.6)
    axis.set_title(
        "Doppler-rate estimates over each independently qualified segment region",
        loc="left",
        fontweight="bold",
    )
    axis.set_xlabel("capture time (s)")
    axis.set_ylabel("receiver-relative Doppler/CFO rate (kHz/s)")
    axis.grid(alpha=0.22)
    handles, labels = axis.get_legend_handles_labels()
    unique = dict(zip(labels, handles, strict=True))
    if unique:
        axis.legend(unique.values(), unique.keys(), fontsize=8, loc="best")
    figure.suptitle(
        "Standard local pilot-segment Doppler rates\n"
        f"{session_id} · {path_label} · {product.qualified_segment_count}/"
        f"{product.analyzed_segment_count} segments qualified",
        fontsize=15,
        fontweight="bold",
    )
    payload = io.BytesIO()
    canvas.print_png(payload)
    return payload.getvalue()
