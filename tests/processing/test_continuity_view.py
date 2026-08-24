from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from leo.contracts.radio import IqBlockMetadataV1, IqBlockMetadataV2, NanosecondIntervalV1
from leo.contracts.recording import ContinuitySummaryV2, TerminalGapEvidenceV1
from leo.contracts.states import ContinuityStatus
from leo.domain.iq import IqBlock
from leo.processing.continuity import (
    IqContinuityEvidenceError,
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
            values = np.empty((record.sample_count, 2, 2), dtype="<i2")
            values[:, :, 0] = record.session_sample_start + 1
            values[:, :, 1] = -(record.session_sample_start + 1)
            yield IqBlock(samples=values, metadata=record)


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
