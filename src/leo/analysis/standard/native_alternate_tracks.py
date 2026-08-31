"""Project and render persisted Standard-native segment-local CFO tracks."""

from __future__ import annotations

import io
from threading import RLock

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native_alternate_tracks import (
    NativeAlternateTrackProjectionDispositionV1,
    NativeAlternateTrackSegmentV1,
    StandardNativeAlternateCfoTrackBankV4,
    StandardNativeAlternateCfoTrackBankV5,
)
from leo.contracts.standard_native_stateful import NativePolynomialTrajectoryV1
from leo.contracts.standard_native_stateful_v2 import (
    NativeStatefulSegmentDispositionV2,
    StandardNativeStatefulPathV2,
    StandardNativeStatefulPathV3,
)

_RENDER_LOCK = RLock()


def build_standard_native_alternate_cfo_track_bank(
    stateful: StandardNativeStatefulPathV2 | StandardNativeStatefulPathV3,
    *,
    stateful_product_digest: Sha256Digest,
) -> StandardNativeAlternateCfoTrackBankV4 | StandardNativeAlternateCfoTrackBankV5:
    """Copy the exact persisted residual-Hough banks without reading or fitting IQ."""

    segments: list[NativeAlternateTrackSegmentV1] = []
    for stateful_segment in stateful.segments:
        science = stateful_segment.local_science
        if science is None:
            tracks: tuple[NativePolynomialTrajectoryV1, ...] = ()
            source_science_digest = None
            source_pilot_scan_digest = None
            source_bank_digest = None
            source_configuration_digest = None
            source_observation_count = 0
            truncated_track_count = 0
        else:
            source_bank = science.residual_hough_bank
            tracks = source_bank.trajectories
            source_science_digest = science.science_digest
            source_pilot_scan_digest = science.pilot_scan_digest
            source_bank_digest = science.raw_trajectory_bank_digest
            source_configuration_digest = source_bank.config_digest
            source_observation_count = source_bank.observation_count
            truncated_track_count = source_bank.truncated_trajectory_count

        if stateful_segment.continuity_segment.observed_sample_count == 0:
            projection_disposition = NativeAlternateTrackProjectionDispositionV1.EMPTY_TERMINAL
        elif science is None:
            projection_disposition = NativeAlternateTrackProjectionDispositionV1.NO_STATEFUL_SCIENCE
        elif tracks:
            projection_disposition = NativeAlternateTrackProjectionDispositionV1.PROJECTED
        else:
            projection_disposition = NativeAlternateTrackProjectionDispositionV1.NO_CANDIDATE_TRACKS

        values = {
            "schema_version": 1,
            "continuity_segment": stateful_segment.continuity_segment.model_dump(mode="json"),
            "continuity_segment_index": stateful_segment.continuity_segment_index,
            "stateful_segment_digest": stateful_segment.segment_digest,
            "stateful_disposition": stateful_segment.disposition.value,
            "projection_disposition": projection_disposition.value,
            "source_science_digest": source_science_digest,
            "source_pilot_scan_digest": source_pilot_scan_digest,
            "source_residual_hough_bank_digest": source_bank_digest,
            "source_residual_hough_configuration_digest": source_configuration_digest,
            "source_observation_count": source_observation_count,
            "detected_track_count": len(tracks) + truncated_track_count,
            "returned_track_count": len(tracks),
            "truncated_track_count": truncated_track_count,
            "tracks": tuple(item.model_dump(mode="json") for item in tracks),
        }
        segments.append(
            NativeAlternateTrackSegmentV1.model_validate(
                {
                    **values,
                    "segment_projection_digest": canonical_digest(values),
                }
            )
        )

    analyzed = any(
        item.disposition is NativeStatefulSegmentDispositionV2.ANALYZED
        for item in stateful.segments
    )
    returned_track_count = sum(item.returned_track_count for item in segments)
    if not analyzed:
        projection_status = "insufficient_data"
    elif stateful.stateful_science_status == "partial_coverage":
        projection_status = "partial_coverage"
    elif returned_track_count:
        projection_status = "complete"
    else:
        projection_status = "no_result"

    wideband = isinstance(stateful, StandardNativeStatefulPathV3)
    values = {
        "schema_version": 5 if wideband else 4,
        "algorithm_version": (
            "standard-native-alternate-cfo-track-bank-v5"
            if wideband
            else "standard-native-alternate-cfo-track-bank-v4"
        ),
        "source": stateful.source.model_dump(mode="json"),
        "starlink_edge": stateful.starlink_edge.value,
        "source_stateful_product_digest": stateful_product_digest,
        "source_stateful_path_digest": stateful.stateful_path_digest,
        "science_configuration_digest": stateful.science_configuration_digest,
        "stateful_science_status": stateful.stateful_science_status,
        "projection_status": projection_status,
        "coordinate_basis": "segment-local-device-axis-v1",
        "frequency_model": ("cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"),
        "segments": tuple(item.model_dump(mode="json") for item in segments),
        "source_observation_count": sum(item.source_observation_count for item in segments),
        "detected_track_count": sum(item.detected_track_count for item in segments),
        "returned_track_count": returned_track_count,
        "truncated_track_count": sum(item.truncated_track_count for item in segments),
        "native_evidence_only": True,
        "current_eligible": False,
        "candidate_only": True,
        "automatic_use_allowed": False,
        "cross_segment_association_permitted": False,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    product_type = (
        StandardNativeAlternateCfoTrackBankV5 if wideband else StandardNativeAlternateCfoTrackBankV4
    )
    return product_type.model_validate({**values, "bank_digest": canonical_digest(values)})


def render_standard_native_alternate_cfo_tracks_png(
    bank: StandardNativeAlternateCfoTrackBankV4 | StandardNativeAlternateCfoTrackBankV5,
) -> bytes:
    """Render only persisted projected tracks on the global display-time axis."""

    with _RENDER_LOCK:
        figure = Figure(figsize=(15, 6), dpi=160, constrained_layout=True)
        FigureCanvasAgg(figure)
        axis = figure.subplots(1, 1)
        colors = (
            "#0072b2",
            "#d55e00",
            "#009e73",
            "#cc79a7",
            "#e69f00",
            "#56b4e9",
        )
        rate = bank.source.sample_rate_hz
        rendered = 0
        for segment in bank.segments:
            authority = segment.continuity_segment
            if authority.preceding_missing_sample_count:
                gap_stop_s = authority.device_sample_start / rate
                gap_start_s = (
                    authority.device_sample_start - authority.preceding_missing_sample_count
                ) / rate
                axis.axvspan(gap_start_s, gap_stop_s, color="#8b949e", alpha=0.18)
            if authority.segment_index:
                axis.axvline(
                    authority.device_sample_start / rate,
                    color="#57606a",
                    linewidth=0.8,
                    alpha=0.5,
                )
            global_offset_s = authority.device_sample_start / rate
            for track_index, track in enumerate(segment.tracks):
                local_times = np.asarray((track.start_s, track.end_s), dtype=np.float64)
                frequencies_hz = np.polyval(
                    np.asarray(track.coefficients_hz, dtype=np.float64),
                    local_times - track.reference_time_s,
                )
                axis.plot(
                    global_offset_s + local_times,
                    frequencies_hz / 1_000.0,
                    color=colors[rendered % len(colors)],
                    linewidth=2.0,
                    label=(
                        f"S{authority.segment_index} T{track_index + 1} "
                        f"{track.coefficients_hz[0]:+.0f} Hz/s"
                    ),
                )
                rendered += 1

        duration_s = bank.source.logical_sample_count / rate
        axis.set_xlim(0.0, max(duration_s, 1e-9))
        axis.set_xlabel("Elapsed logical device time (s)")
        axis.set_ylabel("Segment-local residual CFO (kHz)")
        axis.set_title(
            "Candidate-only projection of persisted segment-local residual-Hough tracks",
            loc="left",
            fontweight="bold",
        )
        axis.grid(alpha=0.2)
        if rendered:
            axis.legend(loc="best", fontsize=7, ncols=2)
        else:
            axis.text(
                0.5,
                0.5,
                "No persisted residual-Hough candidates",
                transform=axis.transAxes,
                ha="center",
                va="center",
                color="#57606a",
            )
        target = io.BytesIO()
        figure.savefig(
            target,
            format="png",
            dpi=160,
            facecolor="white",
            metadata={"Software": f"leo-tracker {bank.algorithm_version}"},
        )
        return target.getvalue()
