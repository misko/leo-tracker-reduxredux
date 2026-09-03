"""Bind fractional persistent-hop products to UTC trajectory candidates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from leo.analysis.persistent_hop_trajectory import PersistentHopCfoCandidate
from leo.analysis.starlink.fractional_epoch import fractional_take_bounds
from leo.analysis.starlink.templates import FRAME_RATE_HZ, OFDM_SYMBOL_DURATION_S
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.scanner.persistent_hop_products import (
    PERSISTENT_HOP_FRACTIONAL_ANALYZER_ID,
    PersistentHopAnalysisChunkV2,
    PersistentHopCandidateV2,
    PersistentHopProbeMetricV2,
)
from leo.storage.persistent_hop import PersistentHopIqSessionManifestV2

_ALGORITHM_VERSION = "persistent-hop-fractional-chunk-trajectory-projection-v1"
_GLRT64_SYMBOLS = tuple(range(2, 66))


class PersistentHopTrajectoryProjectionError(ValueError):
    """The fractional products cannot be bound to qualified capture authority."""


@dataclass(frozen=True, slots=True)
class PersistentHopTrajectoryProjectionConfig:
    base_standard_uncertainty_hz: float = 400.0
    maximum_abs_doppler_rate_hz_per_s: float = 15_000.0
    require_complete_capture: bool = True
    require_continuity_attestation: bool = True
    require_qualified_utc: bool = True

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.base_standard_uncertainty_hz)
            or self.base_standard_uncertainty_hz <= 0.0
            or not math.isfinite(self.maximum_abs_doppler_rate_hz_per_s)
            or self.maximum_abs_doppler_rate_hz_per_s <= 0.0
        ):
            raise PersistentHopTrajectoryProjectionError(
                "trajectory projection uncertainty controls are invalid"
            )

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(
            {
                "algorithm_version": _ALGORITHM_VERSION,
                "base_standard_uncertainty_hz": self.base_standard_uncertainty_hz,
                "maximum_abs_doppler_rate_hz_per_s": (
                    self.maximum_abs_doppler_rate_hz_per_s
                ),
                "require_complete_capture": self.require_complete_capture,
                "require_continuity_attestation": self.require_continuity_attestation,
                "require_qualified_utc": self.require_qualified_utc,
            }
        )


@dataclass(frozen=True, slots=True)
class PersistentHopTrajectoryProjection:
    candidates: tuple[PersistentHopCfoCandidate, ...]
    input_probe_count: int
    nonoverlapping_probe_count: int
    fractionally_scored_candidate_count: int
    passing_fractional_candidate_count: int
    projected_candidate_count: int
    input_manifest_digest: Sha256Digest
    raw_recording_authority_digest: Sha256Digest
    config_digest: Sha256Digest
    algorithm_version: Literal[
        "persistent-hop-fractional-chunk-trajectory-projection-v1"
    ] = "persistent-hop-fractional-chunk-trajectory-projection-v1"
    integer_decision_values_consumed: Literal[False] = False
    overlapping_probe_evidence_consumed: Literal[False] = False


@dataclass(frozen=True, slots=True)
class _SupportGeometry:
    source_start_in_probe: int
    source_end_in_probe: int
    center_in_probe_samples: float
    factorial_support_moments_s: tuple[float, float, float, float]


def project_fractional_persistent_hop_candidates(
    manifest: PersistentHopIqSessionManifestV2,
    chunks: tuple[PersistentHopAnalysisChunkV2, ...],
    *,
    config: PersistentHopTrajectoryProjectionConfig | None = None,
) -> PersistentHopTrajectoryProjection:
    """Project all passing fractional candidates from independent 20 ms probes."""

    selected = config or PersistentHopTrajectoryProjectionConfig()
    manifest = _revalidate_manifest(manifest)
    chunks = _revalidate_chunks(chunks)
    receipt = manifest.receipt
    timing = manifest.timing
    if selected.require_complete_capture and receipt.capture_outcome != "complete":
        raise PersistentHopTrajectoryProjectionError("trajectory capture is not complete")
    if selected.require_continuity_attestation and not receipt.continuity_attested:
        raise PersistentHopTrajectoryProjectionError(
            "trajectory capture lacks device-counter continuity attestation"
        )
    if selected.require_qualified_utc and not timing.qualified:
        raise PersistentHopTrajectoryProjectionError(
            "trajectory capture lacks qualified UTC timing authority"
        )
    if not chunks:
        raise PersistentHopTrajectoryProjectionError("fractional trajectory chunks are empty")
    if any(
        item.session_id != manifest.session_id
        or item.input_manifest_sha256 != chunks[0].input_manifest_sha256
        or item.configuration.analyzer_id != PERSISTENT_HOP_FRACTIONAL_ANALYZER_ID
        for item in chunks
    ):
        raise PersistentHopTrajectoryProjectionError(
            "fractional chunks do not share the capture and analyzer authority"
        )
    if len({item.configuration for item in chunks}) != 1:
        raise PersistentHopTrajectoryProjectionError(
            "fractional chunks do not share one numerical configuration"
        )
    configuration = chunks[0].configuration
    expected_sweeps = tuple(dict.fromkeys(item.sweep_index for item in receipt.visits))
    if tuple(item.sweep_index for item in chunks) != expected_sweeps:
        raise PersistentHopTrajectoryProjectionError(
            "fractional chunks do not cover the complete ordered sweep inventory"
        )
    probes = tuple(item for chunk in chunks for item in chunk.probes)
    expected_probe_count = (
        len(receipt.visits)
        * len(receipt.plan.receiver_ids)
        * chunks[0].scheduled_probe_count_per_receiver_visit
    )
    if len(probes) != expected_probe_count:
        raise PersistentHopTrajectoryProjectionError(
            "fractional chunks do not cover every capture visit"
        )

    visit_by_index = {item.visit_index: item for item in receipt.visits}
    payload_start_by_visit: dict[int, int] = {}
    payload_cursor = 0
    for visit in receipt.visits:
        payload_start_by_visit[visit.visit_index] = payload_cursor
        payload_cursor += visit.valid_sample_count
    nonoverlapping = _nonoverlapping_probes(probes, configuration.probe_ms)
    raw_authority = canonical_digest(
        {
            "algorithm_version": "persistent-hop-iq-recording-authority-v1",
            "input_manifest_sha256": chunks[0].input_manifest_sha256,
            "uncompressed_sha256": manifest.uncompressed_sha256,
            "session_id": manifest.session_id,
            "stream_generation": receipt.stream_generation,
        }
    )
    timing_half_width_s = timing.first_sample_bracket_width_ns / 2e9
    standard_uncertainty_hz = math.hypot(
        selected.base_standard_uncertainty_hz,
        selected.maximum_abs_doppler_rate_hz_per_s * timing_half_width_s,
    )

    output: list[PersistentHopCfoCandidate] = []
    for probe in nonoverlapping:
        try:
            visit = visit_by_index[probe.visit_index]
        except KeyError as error:
            raise PersistentHopTrajectoryProjectionError(
                "fractional probe references an absent visit"
            ) from error
        if probe.target != visit.target or probe.target_index != visit.target_index:
            raise PersistentHopTrajectoryProjectionError(
                "fractional probe target disagrees with capture evidence"
            )
        probe_start_sample = probe.probe_start_ms * receipt.plan.sample_rate_hz // 1_000
        source_group_id = canonical_digest(
            {
                "algorithm_version": _ALGORITHM_VERSION,
                "input_manifest_sha256": chunks[0].input_manifest_sha256,
                "visit_index": probe.visit_index,
                "receiver_id": probe.receiver_id,
                "probe_index": probe.probe_index,
                "probe_start_ms": probe.probe_start_ms,
            }
        )
        for candidate in probe.fractional_candidates:
            if not candidate.passed_fractional_margin_gate:
                continue
            geometry = _fractional_glrt64_support_geometry(
                candidate,
                sample_rate_hz=receipt.plan.sample_rate_hz,
                probe_sample_count=receipt.plan.sample_rate_hz
                * configuration.probe_ms
                // 1_000,
            )
            source_start = (
                payload_start_by_visit[probe.visit_index]
                + probe_start_sample
                + geometry.source_start_in_probe
            )
            source_end = (
                payload_start_by_visit[probe.visit_index]
                + probe_start_sample
                + geometry.source_end_in_probe
            )
            support_start_counter = (
                visit.valid_device_sample_counter
                + probe_start_sample
                + geometry.source_start_in_probe
            )
            support_end_counter = (
                visit.valid_device_sample_counter
                + probe_start_sample
                + geometry.source_end_in_probe
            )
            support_center_counter = (
                visit.valid_device_sample_counter
                + probe_start_sample
                + geometry.center_in_probe_samples
            )
            actual_rf_hz = float(probe.target.rf_center_hz - visit.actual_if_offset_hz)
            candidate_id = canonical_digest(
                {
                    "algorithm_version": _ALGORITHM_VERSION,
                    "source_group_id": source_group_id,
                    "candidate_rank": candidate.candidate_rank,
                    "fractional_device_sample_counter": (
                        candidate.fractional_device_sample_counter
                    ),
                    "fractional_tracking_cfo_hz": candidate.fractional_tracking_cfo_hz,
                    "fractional_exact_score": candidate.fractional_exact_score,
                    "fractional_control_score": candidate.fractional_control_score,
                }
            )
            output.append(
                PersistentHopCfoCandidate(
                    candidate_id=candidate_id,
                    source_group_id=source_group_id,
                    candidate_rank=candidate.candidate_rank,
                    session_id=manifest.session_id,
                    input_manifest_digest=chunks[0].input_manifest_sha256,
                    raw_recording_authority_digest=raw_authority,
                    radio_id=receipt.radio_id,
                    stream_generation=receipt.stream_generation,
                    receiver_id=probe.receiver_id,
                    visit_index=probe.visit_index,
                    probe_index=probe.probe_index,
                    channel=probe.target.channel,
                    edge=probe.target.edge,
                    actual_rf_hz=actual_rf_hz,
                    source_sample_start=source_start,
                    source_sample_end=source_end,
                    support_start_utc_ns=_utc_ns_for_counter(
                        timing.first_sample_estimate_utc_ns,
                        timing.session_start_device_sample_counter,
                        timing.sample_rate_hz,
                        support_start_counter,
                    ),
                    support_center_utc_ns=_utc_ns_for_counter(
                        timing.first_sample_estimate_utc_ns,
                        timing.session_start_device_sample_counter,
                        timing.sample_rate_hz,
                        support_center_counter,
                    ),
                    support_end_utc_ns=_utc_ns_for_counter(
                        timing.first_sample_estimate_utc_ns,
                        timing.session_start_device_sample_counter,
                        timing.sample_rate_hz,
                        support_end_counter,
                    ),
                    measured_cfo_hz=candidate.fractional_tracking_cfo_hz,
                    standard_uncertainty_hz=standard_uncertainty_hz,
                    factorial_support_moments_s=geometry.factorial_support_moments_s,
                    exact_score=candidate.fractional_exact_score,
                    control_score=candidate.fractional_control_score,
                    margin=candidate.fractional_margin,
                )
            )
    passing_count = sum(
        candidate.passed_fractional_margin_gate
        for probe in probes
        for candidate in probe.fractional_candidates
    )
    return PersistentHopTrajectoryProjection(
        candidates=tuple(output),
        input_probe_count=len(probes),
        nonoverlapping_probe_count=len(nonoverlapping),
        fractionally_scored_candidate_count=sum(
            probe.fractionally_scored_candidate_count for probe in probes
        ),
        passing_fractional_candidate_count=passing_count,
        projected_candidate_count=len(output),
        input_manifest_digest=chunks[0].input_manifest_sha256,
        raw_recording_authority_digest=raw_authority,
        config_digest=selected.digest,
    )


def _nonoverlapping_probes(
    probes: tuple[PersistentHopProbeMetricV2, ...],
    probe_ms: int,
) -> tuple[PersistentHopProbeMetricV2, ...]:
    by_stream: dict[tuple[int, int], list[PersistentHopProbeMetricV2]] = {}
    for probe in probes:
        by_stream.setdefault((probe.visit_index, probe.receiver_id), []).append(probe)
    retained: list[PersistentHopProbeMetricV2] = []
    for key in sorted(by_stream):
        next_start_ms = -1
        for probe in sorted(by_stream[key], key=lambda item: item.probe_start_ms):
            if probe.probe_start_ms >= next_start_ms:
                retained.append(probe)
                next_start_ms = probe.probe_start_ms + probe_ms
    return tuple(
        sorted(
            retained,
            key=lambda item: (
                item.visit_index,
                item.receiver_id,
                item.probe_start_ms,
            ),
        )
    )


def _fractional_glrt64_support_geometry(
    candidate: PersistentHopCandidateV2,
    *,
    sample_rate_hz: int,
    probe_sample_count: int,
) -> _SupportGeometry:
    symbol_period = sample_rate_hz * OFDM_SYMBOL_DURATION_S
    frame_period = sample_rate_hz / FRAME_RATE_HZ
    template_count = round(frame_period)
    local_starts = tuple(round(symbol * symbol_period) for symbol in _GLRT64_SYMBOLS)
    local_stops = tuple(
        min(round((symbol + 1) * symbol_period), template_count)
        for symbol in _GLRT64_SYMBOLS
    )
    left_guard, right_guard = fractional_take_bounds(
        candidate.fractional_epoch_offset_samples
    )
    centers: list[float] = []
    source_starts: list[int] = []
    source_ends: list[int] = []
    frame = 0
    while True:
        frame_start = candidate.integer_epoch_sample + round(frame * frame_period)
        if (
            frame_start + candidate.fractional_epoch_offset_samples >= probe_sample_count
            or frame_start
            + local_starts[0]
            + candidate.fractional_epoch_offset_samples
            >= probe_sample_count
        ):
            break
        for local_start, local_stop in zip(local_starts, local_stops, strict=True):
            count = local_stop - local_start
            if count < 2:
                continue
            continuous_start = (
                frame_start + local_start + candidate.fractional_epoch_offset_samples
            )
            if continuous_start < left_guard or (
                continuous_start + count - 1 >= probe_sample_count - right_guard
            ):
                continue
            centers.append(continuous_start + (count - 1) / 2.0)
            source_starts.append(math.floor(continuous_start) - left_guard)
            source_ends.append(
                math.floor(continuous_start + count - 1) + right_guard + 1
            )
        frame += 1
    if len(centers) < 2:
        raise PersistentHopTrajectoryProjectionError(
            "passing fractional GLRT candidate has insufficient source support"
        )
    center = math.fsum(centers) / len(centers)
    offsets_s = tuple((item - center) / sample_rate_hz for item in centers)
    raw_second = math.fsum(item**2 for item in offsets_s) / len(offsets_s)
    raw_third = math.fsum(item**3 for item in offsets_s) / len(offsets_s)
    return _SupportGeometry(
        source_start_in_probe=min(source_starts),
        source_end_in_probe=max(source_ends),
        center_in_probe_samples=center,
        factorial_support_moments_s=(1.0, 0.0, raw_second / 2.0, raw_third / 6.0),
    )


def _utc_ns_for_counter(
    first_sample_utc_ns: int,
    first_sample_counter: int,
    sample_rate_hz: int,
    counter: float,
) -> int:
    return first_sample_utc_ns + round(
        (counter - first_sample_counter) * 1_000_000_000 / sample_rate_hz
    )


def _revalidate_manifest(
    value: PersistentHopIqSessionManifestV2,
) -> PersistentHopIqSessionManifestV2:
    try:
        return PersistentHopIqSessionManifestV2.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise PersistentHopTrajectoryProjectionError(
            "persistent-hop manifest is invalid"
        ) from error


def _revalidate_chunks(
    values: tuple[PersistentHopAnalysisChunkV2, ...],
) -> tuple[PersistentHopAnalysisChunkV2, ...]:
    try:
        return tuple(
            PersistentHopAnalysisChunkV2.model_validate(item.model_dump(mode="json"))
            for item in values
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise PersistentHopTrajectoryProjectionError(
            "fractional persistent-hop chunk inventory is invalid"
        ) from error


__all__ = [
    "PersistentHopTrajectoryProjection",
    "PersistentHopTrajectoryProjectionConfig",
    "PersistentHopTrajectoryProjectionError",
    "project_fractional_persistent_hop_candidates",
]
