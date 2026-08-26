"""Central validity gate for Standard-native numerical windows and segments.

The adapter deliberately accepts only :class:`ValidityAwareIqReader`.  It
never projects the logical device axis onto a mask-blind reader.  Numerical
kernels instead receive either a complete, wholly observed local window or a
contiguous segment reader, both carrying an explicit global device mapping.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from leo.contracts.radio import IqBlockMetadataV1
from leo.contracts.standard_native import (
    NativeOpportunityAccountingV1,
    NativeProbeWindowV3,
    NativeWindowDisposition,
    NativeWindowEvidenceV1,
    StandardProbeScheduleV3,
)
from leo.contracts.states import ContinuityStatus
from leo.contracts.validity import ContinuitySegmentV1
from leo.domain.iq import IqBlock
from leo.pipeline.validity import (
    ContinuitySegmentIqReader,
    ValidityAwareIqReader,
    WindowClassification,
    WindowValidity,
)

_MAX_KERNEL_BLOCK_SAMPLES = 1_048_576


class NativeWindowPurpose(StrEnum):
    """In-process identity of one reviewed complete-support kernel input."""

    FFT = "fft"
    PROBE_20MS = "probe_20ms"
    FRAME_QAM = "frame_qam"
    FULL_CAPTURE_GLRT20MS = "full_capture_glrt20ms"


@dataclass(frozen=True, slots=True)
class NativeWindowRequest:
    """One globally scheduled numerical opportunity on the device axis."""

    opportunity_index: int
    purpose: NativeWindowPurpose
    device_sample_start: int
    sample_count: int

    def __post_init__(self) -> None:
        if self.opportunity_index < 0:
            raise ValueError("native window opportunity index must be non-negative")
        if self.sample_count <= 0:
            raise ValueError("native window sample count must be positive")

    @property
    def device_sample_stop(self) -> int:
        return self.device_sample_start + self.sample_count


@dataclass(frozen=True, slots=True)
class NativeWindowDecision:
    """Authoritative disposition retained for one scheduled opportunity."""

    request: NativeWindowRequest
    classification: WindowClassification

    def __post_init__(self) -> None:
        if (
            self.classification.device_sample_start != self.request.device_sample_start
            or self.classification.sample_count != self.request.sample_count
        ):
            raise ValueError("native window classification changed its requested support")

    @property
    def eligible(self) -> bool:
        return self.classification.status is WindowValidity.VALID


@dataclass(frozen=True, slots=True)
class NativeSegmentKernelInput:
    """One state-reset boundary and its optional non-empty contiguous IQ view."""

    segment: ContinuitySegmentV1
    iq: ContinuitySegmentIqReader | None

    def __post_init__(self) -> None:
        if self.segment.observed_sample_count == 0:
            if self.iq is not None:
                raise ValueError("empty continuity segment cannot expose numerical IQ")
            return
        if self.iq is None or self.iq.segment != self.segment:
            raise ValueError("native segment input is not bound to its validity segment")
        if (
            self.iq.continuity_segment_index != self.segment.segment_index
            or self.iq.global_device_sample_start != self.segment.device_sample_start
            or self.iq.sample_count != self.segment.observed_sample_count
        ):
            raise ValueError("native segment reader coordinates disagree with validity")

    @property
    def continuity_segment_index(self) -> int:
        return self.segment.segment_index

    @property
    def global_device_sample_start(self) -> int:
        return self.segment.device_sample_start


class NativeWindowIqReader:
    """Immutable local IQ reader for exactly one wholly valid global window."""

    def __init__(
        self,
        *,
        request: NativeWindowRequest,
        continuity_segment_index: int,
        sample_rate_hz: int,
        center_frequency_hz: int,
        receiver_ids: tuple[int, ...],
        blocks: tuple[IqBlock, ...],
    ) -> None:
        if continuity_segment_index < 0 or sample_rate_hz <= 0 or not receiver_ids:
            raise ValueError("native window reader geometry is invalid")
        cursor = 0
        for block in blocks:
            if (
                block.metadata.session_sample_start != cursor
                or block.metadata.receiver_ids != receiver_ids
            ):
                raise ValueError("native window blocks are not locally contiguous")
            cursor += block.metadata.sample_count
        if not blocks or cursor != request.sample_count:
            raise ValueError("native window blocks do not close requested support")
        self._request = request
        self._continuity_segment_index = continuity_segment_index
        self._sample_rate_hz = sample_rate_hz
        self._center_frequency_hz = center_frequency_hz
        self._receiver_ids = receiver_ids
        self._blocks = blocks

    @property
    def request(self) -> NativeWindowRequest:
        return self._request

    @property
    def purpose(self) -> NativeWindowPurpose:
        return self._request.purpose

    @property
    def opportunity_index(self) -> int:
        return self._request.opportunity_index

    @property
    def global_device_sample_start(self) -> int:
        return self._request.device_sample_start

    @property
    def global_device_sample_stop(self) -> int:
        return self._request.device_sample_stop

    @property
    def continuity_segment_index(self) -> int:
        return self._continuity_segment_index

    @property
    def sample_rate_hz(self) -> int:
        return self._sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        return self._center_frequency_hz

    @property
    def sample_count(self) -> int:
        return self._request.sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return self._receiver_ids

    def to_global_device_sample(self, local_sample: int) -> int:
        if not 0 <= local_sample <= self.sample_count:
            raise ValueError("local sample lies outside the native kernel window")
        return self.global_device_sample_start + local_sample

    def iter_blocks(self, *, block_samples: int) -> Iterable[IqBlock]:
        _validate_block_samples(block_samples)
        cursor = 0
        for source in self._blocks:
            for offset in range(0, source.metadata.sample_count, block_samples):
                count = min(block_samples, source.metadata.sample_count - offset)
                samples = np.ascontiguousarray(source.samples[offset : offset + count])
                yield IqBlock(
                    samples=samples,
                    metadata=_window_metadata(
                        source.metadata,
                        source_offset=offset,
                        sample_count=count,
                        window_local_start=cursor,
                        global_device_sample_start=(self.global_device_sample_start + cursor),
                        continuity_segment_index=self.continuity_segment_index,
                    ),
                )
                cursor += count
        if cursor != self.sample_count:
            raise ValueError("native kernel window ended before its declared support")


class StandardNativeWindowAdapter:
    """Validate schedules once and feed kernels only complete observed support."""

    def __init__(self, source: ValidityAwareIqReader) -> None:
        if source.sample_rate_hz <= 0 or source.sample_count <= 0 or not source.receiver_ids:
            raise ValueError("native validity-aware source geometry is invalid")
        self._source = source
        self._segments = _bind_segment_inputs(source)

    @property
    def source(self) -> ValidityAwareIqReader:
        return self._source

    @property
    def segment_inputs(self) -> tuple[NativeSegmentKernelInput, ...]:
        """Return every reset boundary, including an empty terminal segment."""

        return self._segments

    def decide(self, requests: Sequence[NativeWindowRequest]) -> tuple[NativeWindowDecision, ...]:
        """Classify one canonical global schedule without reading any IQ bytes."""

        _validate_request_schedule(requests)
        return tuple(
            NativeWindowDecision(
                request=request,
                classification=self._source.classify_window(
                    request.device_sample_start,
                    request.sample_count,
                ),
            )
            for request in requests
        )

    def fixed_stride_schedule(
        self,
        *,
        purpose: NativeWindowPurpose,
        window_samples: int,
        stride_samples: int,
        device_sample_start: int = 0,
        device_sample_stop: int | None = None,
    ) -> tuple[NativeWindowDecision, ...]:
        """Build and classify an exact global fixed-window schedule."""

        if window_samples <= 0 or stride_samples <= 0 or device_sample_start < 0:
            raise ValueError("native fixed-window schedule geometry is invalid")
        stop = self._source.sample_count if device_sample_stop is None else device_sample_stop
        if stop < device_sample_start or stop > self._source.sample_count:
            raise ValueError("native fixed-window schedule extent is invalid")
        requests = tuple(
            NativeWindowRequest(
                opportunity_index=index,
                purpose=purpose,
                device_sample_start=start,
                sample_count=window_samples,
            )
            for index, start in enumerate(
                range(device_sample_start, stop - window_samples + 1, stride_samples)
            )
        )
        return self.decide(requests)

    def full_capture_glrt20ms_schedule(
        self,
        *,
        window_ms: int = 20,
        stride_ms: int = 10,
    ) -> tuple[NativeWindowDecision, ...]:
        """Retain the global GLRT schedule and its exact exclusion inventory."""

        window_samples = _duration_samples(self._source.sample_rate_hz, window_ms)
        stride_samples = _duration_samples(self._source.sample_rate_hz, stride_ms)
        return self.fixed_stride_schedule(
            purpose=NativeWindowPurpose.FULL_CAPTURE_GLRT20MS,
            window_samples=window_samples,
            stride_samples=stride_samples,
        )

    def frame_qam_schedule(
        self,
        windows: Sequence[tuple[int, int]],
    ) -> tuple[NativeWindowDecision, ...]:
        """Classify caller-selected complete frame/QAM support on global time."""

        return self.decide(
            tuple(
                NativeWindowRequest(
                    opportunity_index=index,
                    purpose=NativeWindowPurpose.FRAME_QAM,
                    device_sample_start=start,
                    sample_count=count,
                )
                for index, (start, count) in enumerate(windows)
            )
        )

    def iter_valid_frame_qam_windows(
        self,
        windows: Sequence[tuple[int, int]],
        *,
        block_samples: int = 262_144,
    ) -> Iterator[tuple[NativeWindowDecision, NativeWindowIqReader]]:
        """Dispatch caller-selected frame/QAM windows after complete-support gating."""

        yield from self.iter_valid_windows(
            self.frame_qam_schedule(windows),
            block_samples=block_samples,
        )

    def iter_valid_full_capture_glrt20ms_windows(
        self,
        *,
        window_ms: int = 20,
        stride_ms: int = 10,
        block_samples: int = 262_144,
    ) -> Iterator[tuple[NativeWindowDecision, NativeWindowIqReader]]:
        """Dispatch eligible global GLRT windows; retain exclusions in the schedule."""

        yield from self.iter_valid_windows(
            self.full_capture_glrt20ms_schedule(
                window_ms=window_ms,
                stride_ms=stride_ms,
            ),
            block_samples=block_samples,
        )

    def iter_valid_windows(
        self,
        decisions: Sequence[NativeWindowDecision],
        *,
        block_samples: int = 262_144,
    ) -> Iterator[tuple[NativeWindowDecision, NativeWindowIqReader]]:
        """Scan each segment once and yield only wholly valid local IQ readers."""

        _validate_block_samples(block_samples)
        requests = tuple(item.request for item in decisions)
        _validate_request_schedule(requests)
        refreshed = self.decide(requests)
        if tuple(item.classification for item in decisions) != tuple(
            item.classification for item in refreshed
        ):
            raise ValueError("native window decisions disagree with current validity authority")

        by_segment: dict[int, list[NativeWindowDecision]] = {}
        for decision in decisions:
            if not decision.eligible:
                continue
            segment_index = decision.classification.continuity_segment_index
            assert segment_index is not None
            by_segment.setdefault(segment_index, []).append(decision)

        yielded = 0
        for segment_input in self._segments:
            selected = tuple(by_segment.pop(segment_input.continuity_segment_index, ()))
            if not selected:
                continue
            if segment_input.iq is None:
                raise ValueError("valid numerical window was assigned to an empty segment")
            for decision, blocks in _iter_segment_window_blocks(
                segment_input.iq,
                selected,
                block_samples=block_samples,
            ):
                yielded += 1
                yield (
                    decision,
                    NativeWindowIqReader(
                        request=decision.request,
                        continuity_segment_index=segment_input.continuity_segment_index,
                        sample_rate_hz=self._source.sample_rate_hz,
                        center_frequency_hz=self._source.center_frequency_hz,
                        receiver_ids=self._source.receiver_ids,
                        blocks=blocks,
                    ),
                )
        if by_segment:
            raise ValueError("valid numerical windows reference unknown continuity segments")
        if yielded != sum(item.eligible for item in decisions):
            raise ValueError("native valid-window iterator lost an eligible opportunity")

    def iter_valid_probe_windows(
        self,
        schedule: StandardProbeScheduleV3,
        *,
        block_samples: int = 262_144,
    ) -> Iterator[tuple[NativeProbeWindowV3, NativeWindowIqReader]]:
        """Bind persisted 20 ms opportunities to wholly valid local readers."""

        source = schedule.source
        inventory = self._source.validity_inventory
        if (
            source.sample_rate_hz != self._source.sample_rate_hz
            or source.logical_sample_count != self._source.sample_count
            or source.observed_sample_count != self._source.observed_sample_count
            or source.missing_sample_count != self._source.missing_sample_count
            or source.validity_inventory_digest != inventory.inventory_digest
            or source.continuity_segments != inventory.segments
        ):
            raise ValueError("native probe schedule source disagrees with validity authority")
        requests = tuple(
            NativeWindowRequest(
                opportunity_index=index,
                purpose=NativeWindowPurpose.PROBE_20MS,
                device_sample_start=item.probe.sample_start,
                sample_count=item.probe.sample_count,
            )
            for index, item in enumerate(schedule.opportunities)
        )
        decisions = self.decide(requests)
        for opportunity, decision in zip(schedule.opportunities, decisions, strict=True):
            if opportunity.validity != native_window_evidence(decision.classification):
                raise ValueError("native probe schedule validity disagrees with live authority")
        for decision, iq in self.iter_valid_windows(
            decisions,
            block_samples=block_samples,
        ):
            yield schedule.opportunities[decision.request.opportunity_index], iq

    def iter_fft_windows(
        self,
        *,
        fft_samples: int,
        hop_samples: int | None = None,
        block_samples: int = 262_144,
    ) -> Iterator[tuple[NativeWindowDecision, NativeWindowIqReader]]:
        """Reset at each segment and emit complete per-segment FFT support only."""

        hop = fft_samples if hop_samples is None else hop_samples
        if fft_samples <= 0 or hop <= 0:
            raise ValueError("native FFT window geometry is invalid")
        _validate_block_samples(block_samples)
        opportunity_index = 0
        for segment_input in self._segments:
            segment = segment_input.segment
            if segment_input.iq is None or segment.observed_sample_count < fft_samples:
                continue
            decisions = tuple(
                NativeWindowDecision(
                    request=NativeWindowRequest(
                        opportunity_index=opportunity_index + local_index,
                        purpose=NativeWindowPurpose.FFT,
                        device_sample_start=global_start,
                        sample_count=fft_samples,
                    ),
                    classification=self._source.classify_window(global_start, fft_samples),
                )
                for local_index, global_start in enumerate(
                    range(
                        segment.device_sample_start,
                        segment.device_sample_stop - fft_samples + 1,
                        hop,
                    )
                )
            )
            if any(
                not item.eligible
                or item.classification.continuity_segment_index != segment.segment_index
                for item in decisions
            ):
                raise ValueError("per-segment FFT schedule escaped its validity segment")
            for decision, blocks in _iter_segment_window_blocks(
                segment_input.iq,
                decisions,
                block_samples=block_samples,
            ):
                yield (
                    decision,
                    NativeWindowIqReader(
                        request=decision.request,
                        continuity_segment_index=segment.segment_index,
                        sample_rate_hz=self._source.sample_rate_hz,
                        center_frequency_hz=self._source.center_frequency_hz,
                        receiver_ids=self._source.receiver_ids,
                        blocks=blocks,
                    ),
                )
            opportunity_index += len(decisions)


def native_window_evidence(
    classification: WindowClassification,
) -> NativeWindowEvidenceV1:
    """Convert the storage-neutral classifier to persisted native evidence."""

    disposition = {
        WindowValidity.VALID: NativeWindowDisposition.VALID,
        WindowValidity.GAP_OVERLAP: NativeWindowDisposition.GAP_OVERLAP,
        WindowValidity.CONTINUITY_BOUNDARY: NativeWindowDisposition.CONTINUITY_BOUNDARY,
        WindowValidity.OUTSIDE_SPAN: NativeWindowDisposition.OUTSIDE_SPAN,
    }[classification.status]
    return NativeWindowEvidenceV1(
        device_sample_start=classification.device_sample_start,
        sample_count=classification.sample_count,
        disposition=disposition,
        missing_sample_count=classification.missing_sample_count,
        continuity_segment_index=classification.continuity_segment_index,
        crossed_segment_indexes=classification.crossed_segment_indexes,
    )


def native_opportunity_accounting(
    decisions: Sequence[NativeWindowDecision],
    *,
    analyzed_count: int,
    passing_count: int = 0,
) -> NativeOpportunityAccountingV1:
    """Close scheduled/eligible/excluded counts without signal-absence conflation."""

    counts = {
        status: sum(item.classification.status is status for item in decisions)
        for status in WindowValidity
    }
    return NativeOpportunityAccountingV1(
        scheduled_count=len(decisions),
        valid_count=counts[WindowValidity.VALID],
        analyzed_count=analyzed_count,
        passing_count=passing_count,
        gap_excluded_count=counts[WindowValidity.GAP_OVERLAP],
        continuity_boundary_excluded_count=counts[WindowValidity.CONTINUITY_BOUNDARY],
        outside_span_count=counts[WindowValidity.OUTSIDE_SPAN],
    )


def _bind_segment_inputs(
    source: ValidityAwareIqReader,
) -> tuple[NativeSegmentKernelInput, ...]:
    readers = source.segment_readers()
    by_index: dict[int, ContinuitySegmentIqReader] = {}
    for reader in readers:
        index = reader.continuity_segment_index
        if index in by_index:
            raise ValueError("native source repeats a continuity-segment reader")
        if (
            reader.sample_rate_hz != source.sample_rate_hz
            or reader.center_frequency_hz != source.center_frequency_hz
            or reader.receiver_ids != source.receiver_ids
        ):
            raise ValueError("native segment reader geometry changed")
        by_index[index] = reader
    inputs = tuple(
        NativeSegmentKernelInput(
            segment=segment,
            iq=(
                None
                if segment.observed_sample_count == 0
                else by_index.pop(segment.segment_index, None)
            ),
        )
        for segment in source.validity_inventory.segments
    )
    if by_index:
        raise ValueError("native source returned a segment absent from validity")
    return inputs


def _validate_request_schedule(requests: Sequence[NativeWindowRequest]) -> None:
    indexes = tuple(item.opportunity_index for item in requests)
    if indexes != tuple(range(len(requests))):
        raise ValueError("native window opportunity indexes must be contiguous from zero")
    coordinates = tuple((item.device_sample_start, item.sample_count) for item in requests)
    if coordinates != tuple(sorted(coordinates)):
        raise ValueError("native window schedule must be ordered by global support")


def _duration_samples(sample_rate_hz: int, duration_ms: int) -> int:
    if duration_ms <= 0 or sample_rate_hz * duration_ms % 1_000:
        raise ValueError("native duration does not map to an integral sample count")
    return sample_rate_hz * duration_ms // 1_000


def _validate_block_samples(block_samples: int) -> None:
    if not 0 < block_samples <= _MAX_KERNEL_BLOCK_SAMPLES:
        raise ValueError(f"block_samples must be in [1, {_MAX_KERNEL_BLOCK_SAMPLES}]")


def _iter_segment_window_blocks(
    segment_reader: ContinuitySegmentIqReader,
    decisions: Sequence[NativeWindowDecision],
    *,
    block_samples: int,
) -> Iterator[tuple[NativeWindowDecision, tuple[IqBlock, ...]]]:
    """Extract ordered, possibly overlapping windows during one segment pass."""

    if not decisions:
        return
    segment = segment_reader.segment
    for decision in decisions:
        classification = decision.classification
        if (
            not decision.eligible
            or classification.continuity_segment_index != segment.segment_index
            or decision.request.device_sample_start < segment.device_sample_start
            or decision.request.device_sample_stop > segment.device_sample_stop
        ):
            raise ValueError("native window is not wholly contained in its selected segment")

    source = iter(segment_reader.iter_blocks(block_samples=block_samples))
    buffered: list[IqBlock] = []
    source_cursor = 0
    for decision in decisions:
        local_start = decision.request.device_sample_start - segment.device_sample_start
        local_stop = local_start + decision.request.sample_count
        buffered = [
            block
            for block in buffered
            if block.metadata.session_sample_start + block.metadata.sample_count > local_start
        ]
        buffered_stop = (
            buffered[-1].metadata.session_sample_start + buffered[-1].metadata.sample_count
            if buffered
            else source_cursor
        )
        while buffered_stop < local_stop:
            try:
                block = next(source)
            except StopIteration as error:
                raise ValueError("native segment ended before a scheduled window") from error
            if (
                block.metadata.session_sample_start != source_cursor
                or block.metadata.receiver_ids != segment_reader.receiver_ids
            ):
                raise ValueError("native segment source is not locally contiguous")
            source_cursor += block.metadata.sample_count
            buffered.append(block)
            buffered_stop = source_cursor

        selected: list[IqBlock] = []
        selected_cursor = local_start
        for block in buffered:
            block_start = block.metadata.session_sample_start
            block_stop = block_start + block.metadata.sample_count
            overlap_start = max(local_start, block_start)
            overlap_stop = min(local_stop, block_stop)
            if overlap_start >= overlap_stop:
                continue
            if overlap_start != selected_cursor:
                raise ValueError("native window extraction lost contiguous IQ support")
            source_offset = overlap_start - block_start
            count = overlap_stop - overlap_start
            window_local_start = overlap_start - local_start
            selected.append(
                IqBlock(
                    samples=np.ascontiguousarray(
                        block.samples[source_offset : source_offset + count]
                    ),
                    metadata=_window_metadata(
                        block.metadata,
                        source_offset=source_offset,
                        sample_count=count,
                        window_local_start=window_local_start,
                        global_device_sample_start=(
                            decision.request.device_sample_start + window_local_start
                        ),
                        continuity_segment_index=segment.segment_index,
                    ),
                )
            )
            selected_cursor = overlap_stop
        if selected_cursor != local_stop:
            raise ValueError("native window extraction ended before requested support")
        yield decision, tuple(selected)


def _window_metadata(
    metadata: IqBlockMetadataV1,
    *,
    source_offset: int,
    sample_count: int,
    window_local_start: int,
    global_device_sample_start: int,
    continuity_segment_index: int,
) -> IqBlockMetadataV1:
    document = metadata.model_dump(mode="json")
    document.update(
        {
            "sample_count": sample_count,
            "session_sample_start": window_local_start,
            "device_sample_counter": (
                None
                if metadata.device_sample_counter is None
                else metadata.device_sample_counter + source_offset
            ),
            "continuity": (
                ContinuityStatus.UNKNOWN.value
                if window_local_start == 0
                else ContinuityStatus.CONTIGUOUS.value
            ),
            "missing_samples_before": 0,
            "overflow_observed": False,
            "hardware_metadata": {
                **metadata.hardware_metadata,
                "native_window_source_local_sample_start": (
                    metadata.session_sample_start + source_offset
                ),
                "native_window_global_device_sample_start": global_device_sample_start,
                "native_window_continuity_segment_index": continuity_segment_index,
            },
        }
    )
    return type(metadata).model_validate(document)
