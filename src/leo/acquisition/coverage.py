"""Pure operational coverage projections for capture and failure evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from leo.contracts.device_buffer import DirectAsyncEvidence, DirectAsyncRequest
from leo.contracts.recording import RecordingStreamV1, RecordingStreamV3


@dataclass(frozen=True, slots=True)
class CaptureStreamCoverage:
    """Exact integer evidence with percentages derived only at presentation time."""

    radio_id: str
    stream_id: str
    delivery_unit: Literal["frames", "device_samples"]
    delivered_units: int
    requested_units: int
    observed_samples: int
    logical_samples: int
    in_segment_returned_samples: int | None = None
    in_segment_missing_samples: int | None = None
    transport_returned_samples: int | None = None
    transport_missing_samples: int | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.delivered_units <= self.requested_units or self.requested_units <= 0:
            raise ValueError("delivery coverage counts are invalid")
        if not 0 <= self.observed_samples <= self.logical_samples:
            raise ValueError("observation coverage counts are invalid")
        density_counts = (
            self.in_segment_returned_samples,
            self.in_segment_missing_samples,
            self.transport_returned_samples,
            self.transport_missing_samples,
        )
        if any(value is not None for value in density_counts):
            if any(value is None for value in density_counts):
                raise ValueError("direct-async density counts must be complete")
            in_segment_returned = self.in_segment_returned_samples
            in_segment_missing = self.in_segment_missing_samples
            transport_returned = self.transport_returned_samples
            transport_missing = self.transport_missing_samples
            assert in_segment_returned is not None
            assert in_segment_missing is not None
            assert transport_returned is not None
            assert transport_missing is not None
            if (
                in_segment_returned <= 0
                or in_segment_missing < 0
                or transport_returned != in_segment_returned
                or transport_missing < in_segment_missing
            ):
                raise ValueError("direct-async density counts are invalid")

    @property
    def delivery_coverage_pct(self) -> float:
        return 100.0 * self.delivered_units / self.requested_units

    @property
    def observed_density_pct(self) -> float | None:
        if self.logical_samples == 0:
            return None
        return 100.0 * self.observed_samples / self.logical_samples

    @property
    def in_segment_density_pct(self) -> float | None:
        if self.in_segment_returned_samples is None:
            return None
        assert self.in_segment_missing_samples is not None
        denominator = self.in_segment_returned_samples + self.in_segment_missing_samples
        return 100.0 * self.in_segment_returned_samples / denominator

    @property
    def transport_density_pct(self) -> float | None:
        if self.transport_returned_samples is None:
            return None
        assert self.transport_missing_samples is not None
        denominator = self.transport_returned_samples + self.transport_missing_samples
        return 100.0 * self.transport_returned_samples / denominator


def project_recording_stream_coverage(
    stream: RecordingStreamV1 | RecordingStreamV3,
    *,
    direct_async_evidence: DirectAsyncEvidence | None = None,
) -> CaptureStreamCoverage:
    """Project one immutable recording without persisting rounded percentages."""

    if isinstance(stream, RecordingStreamV3):
        delivered_samples = stream.logical_sample_count
        logical_samples = stream.logical_sample_count
        observed_samples = stream.observed_sample_count
    else:
        delivered_samples = stream.captured_sample_count
        logical_samples = stream.requested_sample_count
        observed_samples = stream.captured_sample_count

    if direct_async_evidence is None:
        return CaptureStreamCoverage(
            radio_id=stream.radio.radio_id,
            stream_id=stream.stream_id,
            delivery_unit="device_samples",
            delivered_units=delivered_samples,
            requested_units=stream.requested_sample_count,
            observed_samples=observed_samples,
            logical_samples=logical_samples,
        )

    if direct_async_evidence.request.requested_device_samples != stream.requested_sample_count:
        raise ValueError("direct-async request disagrees with the recording stream")
    returned_samples = (
        direct_async_evidence.returned_frames * direct_async_evidence.request.frame_samples
    )
    in_segment_missing = (
        direct_async_evidence.counter_missing_sample_count
        - direct_async_evidence.inter_segment_skipped_samples
    )
    return CaptureStreamCoverage(
        radio_id=stream.radio.radio_id,
        stream_id=stream.stream_id,
        delivery_unit="frames",
        delivered_units=direct_async_evidence.returned_frames,
        requested_units=direct_async_evidence.request.target_frames,
        observed_samples=observed_samples,
        logical_samples=logical_samples,
        in_segment_returned_samples=returned_samples,
        in_segment_missing_samples=in_segment_missing,
        transport_returned_samples=returned_samples,
        transport_missing_samples=direct_async_evidence.counter_missing_sample_count,
    )


def project_capture_progress_coverage(
    *,
    radio_id: str,
    stream_id: str,
    requested_samples: int,
    observed_samples: int,
    covered_device_samples: int,
    direct_async_request: DirectAsyncRequest | None = None,
    returned_frames: int = 0,
    counter_missing_samples: int = 0,
    inter_segment_skipped_samples: int = 0,
) -> CaptureStreamCoverage:
    """Project live progress, including an unpublished partial direct-async spool."""

    logical_samples = min(requested_samples, max(observed_samples, covered_device_samples))
    observed_in_span = min(observed_samples, logical_samples)
    if direct_async_request is None:
        return CaptureStreamCoverage(
            radio_id=radio_id,
            stream_id=stream_id,
            delivery_unit="device_samples",
            delivered_units=min(covered_device_samples, requested_samples),
            requested_units=requested_samples,
            observed_samples=observed_in_span,
            logical_samples=logical_samples,
        )

    if not 0 <= returned_frames <= direct_async_request.target_frames:
        raise ValueError("returned direct-async frame count is outside the request")
    if not 0 <= inter_segment_skipped_samples <= counter_missing_samples:
        raise ValueError("direct-async missing-sample counts are invalid")
    returned_samples = returned_frames * direct_async_request.frame_samples
    return CaptureStreamCoverage(
        radio_id=radio_id,
        stream_id=stream_id,
        delivery_unit="frames",
        delivered_units=returned_frames,
        requested_units=direct_async_request.target_frames,
        observed_samples=observed_in_span,
        logical_samples=logical_samples,
        in_segment_returned_samples=returned_samples if returned_samples else None,
        in_segment_missing_samples=(
            counter_missing_samples - inter_segment_skipped_samples if returned_samples else None
        ),
        transport_returned_samples=returned_samples if returned_samples else None,
        transport_missing_samples=counter_missing_samples if returned_samples else None,
    )
