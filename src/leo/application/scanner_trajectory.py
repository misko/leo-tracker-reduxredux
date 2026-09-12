"""Project both capture modes through the same physical support geometry."""

import math

from leo.analysis.persistent_hop_trajectory import PersistentHopCfoCandidate
from leo.application.persistent_hop_trajectory import (
    PersistentHopTrajectoryProjectionError,
    fractional_glrt64_support_geometry,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.scanner_tracking import TrackingInput
from leo.contracts.states import StarlinkEdge


def project_scanner_candidates(source: TrackingInput) -> tuple[PersistentHopCfoCandidate, ...]:
    timing = source.timing
    if not source.qualified or not source.stream_generation:
        raise PersistentHopTrajectoryProjectionError(
            "capture lacks complete counter-continuity authority"
        )
    if timing is None or not timing.qualified:
        raise PersistentHopTrajectoryProjectionError("capture lacks qualified UTC timing authority")
    if timing.sample_rate_hz != source.sample_rate_hz or timing.session_id != source.session_id:
        raise PersistentHopTrajectoryProjectionError(
            "UTC authority does not bind sample rate and session"
        )
    fs = source.sample_rate_hz
    uncertainty = math.hypot(400.0, 15_000.0 * timing.first_sample_bracket_width_ns / 2e9)
    output = []
    next_start: dict[tuple[int, int], int] = {}
    for probe in sorted(
        source.probes, key=lambda p: (p.visit_index, p.receiver_id, p.probe_start_ms)
    ):
        key = probe.visit_index, probe.receiver_id
        if probe.probe_start_ms < next_start.get(key, -1):
            continue
        next_start[key] = probe.probe_start_ms + source.probe_ms
        offset = probe.probe_start_ms * fs // 1000
        group_id = canonical_digest(
            {
                "capture": source.input_manifest_sha256,
                "visit": probe.visit_index,
                "rx": probe.receiver_id,
                "probe": probe.probe_index,
            }
        )
        for candidate in probe.candidates:
            if not candidate.passed_fractional_margin_gate:
                continue
            geometry = fractional_glrt64_support_geometry(
                candidate, sample_rate_hz=fs, probe_sample_count=fs * source.probe_ms // 1000
            )
            # Subtract integer device counters BEFORE adding fractional positions.
            # Absolute counters can exceed the exact integer range of float64.
            relative = (
                probe.valid_start_counter - timing.session_start_device_sample_counter + offset
            )

            def utc(local: float, relative: int = relative) -> int:
                return timing.first_sample_estimate_utc_ns + round((relative + local) * 1e9 / fs)

            output.append(
                PersistentHopCfoCandidate(
                    candidate_id=canonical_digest(
                        {
                            "group": group_id,
                            "rank": candidate.candidate_rank,
                            "analysis": source.analysis_manifest_sha256,
                        }
                    ),
                    source_group_id=group_id,
                    candidate_rank=candidate.candidate_rank,
                    session_id=source.session_id,
                    input_manifest_digest=source.input_manifest_sha256,
                    raw_recording_authority_digest=source.raw_recording_authority_digest,
                    radio_id=source.radio_id,
                    stream_generation=source.stream_generation,
                    receiver_id=probe.receiver_id,
                    visit_index=probe.visit_index,
                    probe_index=probe.probe_index,
                    channel=probe.channel,
                    edge=StarlinkEdge(probe.edge),
                    actual_rf_hz=probe.actual_rf_hz,
                    source_sample_start=probe.payload_start_sample
                    + offset
                    + geometry.source_start_in_probe,
                    source_sample_end=probe.payload_start_sample
                    + offset
                    + geometry.source_end_in_probe,
                    support_start_utc_ns=utc(geometry.source_start_in_probe),
                    support_center_utc_ns=utc(geometry.center_in_probe_samples),
                    support_end_utc_ns=utc(geometry.source_end_in_probe),
                    measured_cfo_hz=candidate.fractional_tracking_cfo_hz,
                    standard_uncertainty_hz=uncertainty,
                    factorial_support_moments_s=geometry.factorial_support_moments_s,
                    exact_score=candidate.fractional_exact_score,
                    control_score=candidate.fractional_control_score,
                    margin=candidate.fractional_margin,
                )
            )
    return tuple(output)
