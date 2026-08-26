from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.radio import IqBlockMetadataV1, IqBlockMetadataV2, NanosecondIntervalV1
from leo.contracts.rate_analysis import VerifiedIqGapMapEvidenceV1
from leo.contracts.recording import ContinuitySummaryV2, TerminalGapEvidenceV1
from leo.contracts.states import ContinuityStatus
from leo.contracts.validity import DeviceAxisContentKind
from leo.domain.iq import IqBlock
from leo.pipeline import WindowValidity
from leo.processing.continuity import (
    IqContinuityEvidenceError,
    V2ValidityAwareIqReader,
    build_iq_gap_map,
    iter_masked_device_iq,
)

_DIGEST = "sha256:" + "1" * 64


def _metadata(
    *,
    stored_start: int,
    count: int,
    counter: int,
    sequence: int,
    continuity: ContinuityStatus,
    missing: int = 0,
    overflow: bool = False,
) -> IqBlockMetadataV1:
    interval = NanosecondIntervalV1(lower_ns=1, upper_ns=2)
    return IqBlockMetadataV1(
        radio_id="radio-1",
        receiver_ids=(0, 1),
        sample_count=count,
        session_sample_start=stored_start,
        host_request_utc_ns=interval,
        host_request_monotonic_ns=interval,
        device_sample_counter=counter,
        source_sequence=sequence,
        continuity=continuity,
        missing_samples_before=missing,
        overflow_observed=overflow,
    )


@dataclass(frozen=True)
class _Reader:
    records: tuple[IqBlockMetadataV1, ...]
    zero_samples: bool = False

    @property
    def sample_rate_hz(self) -> int:
        return 2_500_000

    @property
    def center_frequency_hz(self) -> int:
        return 12_000_000_000

    @property
    def sample_count(self) -> int:
        return sum(item.sample_count for item in self.records)

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return (0, 1)

    def iter_blocks(self, *, block_samples: int):
        for record in self.records:
            assert record.sample_count <= block_samples
            values = np.zeros((record.sample_count, 2, 2), dtype="<i2")
            if not self.zero_samples:
                values[:, :, 0] = record.session_sample_start + 1
                values[:, :, 1] = -(record.session_sample_start + 1)
            yield IqBlock(samples=values, metadata=record)


class _GapAwareReader:
    def __init__(
        self,
        records: tuple[IqBlockMetadataV1, ...],
        *,
        zero_samples: bool = False,
        continuity: ContinuitySummaryV2 | None = None,
    ) -> None:
        self._source = _Reader(records, zero_samples=zero_samples)
        self._gap_map = build_iq_gap_map(
            stream_id="stream-0",
            timeline_sha256=_DIGEST,
            timeline=records,
            continuity=continuity,
        )
        self.closed = False

    @property
    def sample_rate_hz(self) -> int:
        return self._source.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        return self._source.center_frequency_hz

    @property
    def sample_count(self) -> int:
        return self._source.sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return self._source.receiver_ids

    def iter_blocks(self, *, block_samples: int):
        yield from self._source.iter_blocks(block_samples=block_samples)

    def gap_map_evidence(self) -> VerifiedIqGapMapEvidenceV1:
        return VerifiedIqGapMapEvidenceV1(
            persisted_sha256=_DIGEST,
            gap_map=self._gap_map,
        )

    def close(self) -> None:
        self.closed = True


def _gapped_records() -> tuple[IqBlockMetadataV1, ...]:
    return (
        _metadata(
            stored_start=0,
            count=4,
            counter=100,
            sequence=0,
            continuity=ContinuityStatus.UNKNOWN,
        ),
        _metadata(
            stored_start=4,
            count=4,
            counter=110,
            sequence=2,
            continuity=ContinuityStatus.GAP_BEFORE,
            missing=6,
        ),
        _metadata(
            stored_start=8,
            count=2,
            counter=114,
            sequence=3,
            continuity=ContinuityStatus.CONTIGUOUS,
        ),
    )


def test_gap_map_and_masked_view_preserve_observed_iq_and_mark_zero_fill() -> None:
    records = _gapped_records()
    gap_map = build_iq_gap_map(stream_id="stream-0", timeline_sha256=_DIGEST, timeline=records)

    assert gap_map.observed_sample_count == 10
    assert gap_map.device_span_sample_count == 16
    assert gap_map.missing_sample_count == 6
    assert gap_map.segment_count == 2
    assert gap_map.boundaries[0].model_dump(mode="json") == {
        "schema_version": 1,
        "segment_index": 1,
        "stored_sample_offset": 4,
        "device_sample_offset": 4,
        "expected_device_sample_counter": 104,
        "actual_device_sample_counter": 110,
        "header_evidence_sha256": sha256_digest(
            canonical_json_bytes(records[1].model_dump(mode="json"))
        ),
        "observed_counter_gap_sample_count": 6,
        "missing_sample_count": 6,
        "reason": "counter_gap",
    }

    blocks = tuple(iter_masked_device_iq(_Reader(records), gap_map, block_samples=4))
    assert [item.device_sample_start for item in blocks] == [0, 4, 8, 10, 14]
    assert [item.sample_count for item in blocks] == [4, 4, 2, 4, 2]
    assert [item.is_zero_fill for item in blocks] == [False, True, True, False, False]
    assert [item.continuity_segment_index for item in blocks] == [0, 1, 1, 1, 1]
    assert all(not np.any(item.samples) for item in blocks[1:3])
    assert all(not np.any(item.valid_samples) for item in blocks[1:3])
    assert all(np.all(item.valid_samples) for item in (blocks[0], blocks[3], blocks[4]))
    assert sum(item.sample_count for item in blocks) == 16


def test_overflow_without_counter_gap_starts_a_new_segment_without_zero_fill() -> None:
    records = (
        _metadata(
            stored_start=0,
            count=4,
            counter=100,
            sequence=0,
            continuity=ContinuityStatus.UNKNOWN,
        ),
        _metadata(
            stored_start=4,
            count=4,
            counter=104,
            sequence=1,
            continuity=ContinuityStatus.OVERFLOW,
            overflow=True,
        ),
    )
    gap_map = build_iq_gap_map(stream_id="stream-0", timeline_sha256=_DIGEST, timeline=records)
    assert gap_map.boundaries[0].reason == "overflow_flag"
    assert gap_map.missing_sample_count == 0
    blocks = tuple(iter_masked_device_iq(_Reader(records), gap_map, block_samples=4))
    assert len(blocks) == 2
    assert not any(item.is_zero_fill for item in blocks)
    assert [item.continuity_segment_index for item in blocks] == [0, 1]


def test_first_refill_overflow_is_bound_without_inventing_a_prior_gap() -> None:
    records = (
        _metadata(
            stored_start=0,
            count=4,
            counter=100,
            sequence=0,
            continuity=ContinuityStatus.OVERFLOW,
            overflow=True,
        ),
    )
    gap_map = build_iq_gap_map(stream_id="stream-0", timeline_sha256=_DIGEST, timeline=records)
    assert gap_map.capture_start_overflow is True
    assert gap_map.capture_start_header_evidence_sha256 == sha256_digest(
        canonical_json_bytes(records[0].model_dump(mode="json"))
    )
    assert gap_map.boundaries == ()
    assert gap_map.missing_sample_count == 0


def test_gap_map_rejects_counter_and_declared_gap_disagreement() -> None:
    records = list(_gapped_records())
    records[1] = records[1].model_copy(update={"missing_samples_before": 5})
    with pytest.raises(
        IqContinuityEvidenceError,
        match="declared missing samples disagree",
    ):
        build_iq_gap_map(stream_id="stream-0", timeline_sha256=_DIGEST, timeline=records)


def test_masked_view_rejects_a_reader_that_disagrees_with_bound_gap_map() -> None:
    records = _gapped_records()
    gap_map = build_iq_gap_map(stream_id="stream-0", timeline_sha256=_DIGEST, timeline=records)
    altered = list(records)
    altered[1] = altered[1].model_copy(update={"device_sample_counter": 111})
    with pytest.raises(IqContinuityEvidenceError, match="device gap is absent"):
        tuple(iter_masked_device_iq(_Reader(tuple(altered)), gap_map, block_samples=4))


def test_terminal_gap_is_zero_filled_only_through_the_requested_device_span() -> None:
    interval = NanosecondIntervalV1(lower_ns=1, upper_ns=2)
    records = (
        IqBlockMetadataV2(
            radio_id="radio-1",
            receiver_ids=(0, 1),
            sample_count=4,
            session_sample_start=0,
            host_request_utc_ns=interval,
            host_request_monotonic_ns=interval,
            device_sample_counter=100,
            source_sequence=0,
            continuity=ContinuityStatus.UNKNOWN,
            stream_generation="generation-1",
            metadata_abi_version=1,
            metadata_flags=1,
            kernel_buffers=8,
        ),
    )
    terminal_header = IqBlockMetadataV2(
        radio_id="radio-1",
        receiver_ids=(0, 1),
        sample_count=4,
        session_sample_start=4,
        host_request_utc_ns=interval,
        host_request_monotonic_ns=interval,
        device_sample_counter=112,
        source_sequence=2,
        continuity=ContinuityStatus.GAP_BEFORE,
        missing_samples_before=8,
        stream_generation="generation-1",
        metadata_abi_version=1,
        metadata_flags=1,
        kernel_buffers=8,
    )
    terminal = TerminalGapEvidenceV1(
        expected_device_sample_counter=104,
        actual_device_sample_counter=112,
        actual_missing_sample_count=8,
        in_span_missing_sample_count=6,
        source_sequence=2,
        returned_sample_count=4,
        stream_generation="generation-1",
        metadata_abi_version=1,
        metadata_flags=1,
        header=terminal_header,
    )
    summary = ContinuitySummaryV2(
        refill_count=1,
        segment_count=1,
        gap_count=1,
        missing_sample_count=6,
        sample_loss_observable=True,
        first_source_sequence=0,
        last_source_sequence=0,
        first_device_sample_counter=100,
        last_device_sample_counter=103,
        observed_sample_count=4,
        device_span_sample_count=10,
        kernel_buffers=8,
        metadata_abi_version=1,
        validated_stream_generation="generation-1",
        queue_capacity_refills=32,
        queue_high_water_refills=1,
        terminal_gap=terminal,
    )

    gap_map = build_iq_gap_map(
        stream_id="stream-0",
        timeline_sha256=_DIGEST,
        timeline=records,
        continuity=summary,
    )

    assert gap_map.device_span_sample_count == 10
    assert gap_map.boundaries[0].observed_counter_gap_sample_count == 8
    assert gap_map.boundaries[0].missing_sample_count == 6
    assert gap_map.boundaries[0].reason == "terminal_counter_gap"
    blocks = tuple(iter_masked_device_iq(_Reader(records), gap_map, block_samples=4))
    assert [item.sample_count for item in blocks] == [4, 4, 2]
    assert [item.is_zero_fill for item in blocks] == [False, True, True]
    assert sum(item.sample_count for item in blocks) == 10


def test_v2_validity_view_closes_coordinates_reads_and_segment_mapping() -> None:
    source = _GapAwareReader(_gapped_records())
    reader = V2ValidityAwareIqReader(source)

    with pytest.raises(ValueError, match="block_samples must be in"):
        tuple(reader.iter_masked_blocks(block_samples=1_048_577))
    with pytest.raises(ValueError, match="cannot exceed"):
        reader.read_device_span(0, 1_048_577)

    inventory = reader.validity_inventory
    assert inventory.logical_sample_count == 16
    assert inventory.observed_sample_count == 10
    assert inventory.missing_sample_count == 6
    assert inventory.gap_map_content_digest == canonical_digest(
        source.gap_map_evidence().gap_map.model_dump(mode="json")
    )
    assert [
        (
            run.content_kind,
            run.device_sample_start,
            run.sample_count,
            run.stored_sample_start,
            run.continuity_segment_index,
        )
        for run in inventory.runs
    ] == [
        (DeviceAxisContentKind.OBSERVED, 0, 4, 0, 0),
        (DeviceAxisContentKind.ZERO_FILL, 4, 6, None, None),
        (DeviceAxisContentKind.OBSERVED, 10, 6, 4, 1),
    ]
    assert [
        (
            segment.segment_index,
            segment.device_sample_start,
            segment.device_sample_stop,
            segment.stored_sample_start,
            segment.stored_sample_stop,
            segment.preceding_missing_sample_count,
        )
        for segment in inventory.segments
    ] == [(0, 0, 4, 0, 4, 0), (1, 10, 16, 4, 10, 6)]

    masked = tuple(reader.iter_masked_blocks(block_samples=4))
    assert [block.device_sample_start for block in masked] == [0, 4, 8, 10, 14]
    assert [block.continuity_segment_ids.tolist() for block in masked] == [
        [0, 0, 0, 0],
        [-1, -1, -1, -1],
        [-1, -1],
        [1, 1, 1, 1],
        [1, 1],
    ]

    valid = tuple(reader.iter_valid_blocks(block_samples=4))
    assert [block.device_sample_start for block in valid] == [0, 10, 14]
    assert [block.sample_count for block in valid] == [4, 4, 2]
    assert all(np.all(block.valid_samples) for block in valid)

    bounded = reader.read_device_span(2, 8)
    assert bounded.valid_samples.tolist() == [True, True, False, False, False, False, False, False]
    assert bounded.continuity_segment_ids.tolist() == [0, 0, -1, -1, -1, -1, -1, -1]
    assert not bounded.samples[2:].any()
    tail = reader.read_device_span(8, 8)
    assert tail.valid_samples.tolist() == [False, False, True, True, True, True, True, True]
    assert tail.continuity_segment_ids.tolist() == [-1, -1, 1, 1, 1, 1, 1, 1]

    segments = reader.segment_readers()
    assert [segment.continuity_segment_index for segment in segments] == [0, 1]
    assert [segment.global_device_sample_start for segment in segments] == [0, 10]
    assert [segment.sample_count for segment in segments] == [4, 6]
    assert segments[1].to_global_device_sample(3) == 13
    second_blocks = tuple(segments[1].iter_blocks(block_samples=4))
    assert [block.metadata.session_sample_start for block in second_blocks] == [0, 4]
    assert [
        block.metadata.hardware_metadata["global_device_sample_start"] for block in second_blocks
    ] == [10, 14]
    assert [
        block.metadata.hardware_metadata["continuity_segment_index"] for block in second_blocks
    ] == [1, 1]
    np.testing.assert_array_equal(
        np.concatenate([block.samples for block in second_blocks]),
        np.concatenate([block.samples for block in valid[1:]]),
    )

    reader.close()
    reader.close()
    assert source.closed is True
    with pytest.raises(RuntimeError, match="closed"):
        reader.read_device_span(0, 1)


def test_v2_validity_window_classification_distinguishes_gap_and_reset_boundary() -> None:
    gapped = V2ValidityAwareIqReader(_GapAwareReader(_gapped_records()))
    assert gapped.classify_window(0, 4).status is WindowValidity.VALID
    assert gapped.classify_window(0, 4).continuity_segment_index == 0
    overlap = gapped.classify_window(3, 8)
    assert overlap.status is WindowValidity.GAP_OVERLAP
    assert overlap.missing_sample_count == 6
    assert overlap.crossed_segment_indexes == (1,)
    assert gapped.classify_window(-1, 1).status is WindowValidity.OUTSIDE_SPAN
    assert gapped.classify_window(15, 2).status is WindowValidity.OUTSIDE_SPAN

    overflow_records = (
        _metadata(
            stored_start=0,
            count=4,
            counter=100,
            sequence=0,
            continuity=ContinuityStatus.UNKNOWN,
        ),
        _metadata(
            stored_start=4,
            count=4,
            counter=104,
            sequence=1,
            continuity=ContinuityStatus.OVERFLOW,
            overflow=True,
        ),
    )
    overflow = V2ValidityAwareIqReader(_GapAwareReader(overflow_records))
    crossing = overflow.classify_window(3, 2)
    assert crossing.status is WindowValidity.CONTINUITY_BOUNDARY
    assert crossing.crossed_segment_indexes == (1,)
    assert overflow.classify_window(0, 4).status is WindowValidity.VALID
    assert overflow.classify_window(4, 4).status is WindowValidity.VALID
    assert [item.continuity_segment_index for item in overflow.segment_readers()] == [0, 1]


def test_v2_validity_preserves_empty_terminal_segment_and_genuine_observed_zeros() -> None:
    interval = NanosecondIntervalV1(lower_ns=1, upper_ns=2)
    records = (
        IqBlockMetadataV2(
            radio_id="radio-1",
            receiver_ids=(0, 1),
            sample_count=4,
            session_sample_start=0,
            host_request_utc_ns=interval,
            host_request_monotonic_ns=interval,
            device_sample_counter=100,
            source_sequence=0,
            continuity=ContinuityStatus.UNKNOWN,
            stream_generation="generation-1",
            metadata_abi_version=1,
            metadata_flags=1,
            kernel_buffers=8,
        ),
    )
    terminal_header = records[0].model_copy(
        update={
            "session_sample_start": 4,
            "device_sample_counter": 112,
            "source_sequence": 2,
            "continuity": ContinuityStatus.GAP_BEFORE,
            "missing_samples_before": 8,
        }
    )
    terminal = TerminalGapEvidenceV1(
        expected_device_sample_counter=104,
        actual_device_sample_counter=112,
        actual_missing_sample_count=8,
        in_span_missing_sample_count=6,
        source_sequence=2,
        returned_sample_count=4,
        stream_generation="generation-1",
        metadata_abi_version=1,
        metadata_flags=1,
        header=terminal_header,
    )
    summary = ContinuitySummaryV2(
        refill_count=1,
        segment_count=1,
        gap_count=1,
        missing_sample_count=6,
        sample_loss_observable=True,
        first_source_sequence=0,
        last_source_sequence=0,
        first_device_sample_counter=100,
        last_device_sample_counter=103,
        observed_sample_count=4,
        device_span_sample_count=10,
        kernel_buffers=8,
        metadata_abi_version=1,
        validated_stream_generation="generation-1",
        queue_capacity_refills=32,
        queue_high_water_refills=1,
        terminal_gap=terminal,
    )
    terminal_reader = V2ValidityAwareIqReader(
        _GapAwareReader(records, zero_samples=True, continuity=summary)
    )

    assert [
        segment.observed_sample_count for segment in terminal_reader.validity_inventory.segments
    ] == [4, 0]
    assert len(terminal_reader.segment_readers()) == 1
    dense = terminal_reader.read_device_span(0, 10)
    assert dense.valid_samples.tolist() == [
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
    ]
    assert not dense.samples.any()
    assert dense.continuity_segment_ids.tolist() == [0, 0, 0, 0, -1, -1, -1, -1, -1, -1]
