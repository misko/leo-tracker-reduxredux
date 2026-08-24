from __future__ import annotations

from pathlib import Path

from leo.application.presentation import _radio_stream
from leo.contracts.radio import IqBlockMetadataV2, NanosecondIntervalV1
from leo.contracts.recording import ContinuitySummaryV2, RecordingStreamV2
from leo.contracts.states import ContinuityStatus, SourceType, StreamState
from leo.presentation.models import StorageStateV1
from tests.station.manifest_examples import manifest_example_v2


def test_terminal_rejected_refill_evidence_reaches_the_recording_view() -> None:
    manifest = manifest_example_v2(
        radio_count=1,
        applied_receiver_ids=(0, 1),
        source_type=SourceType.IMPORT,
    )
    original = manifest.streams[0]
    original_continuity = original.continuity
    interval = NanosecondIntervalV1(lower_ns=1, upper_ns=2)
    rejected = IqBlockMetadataV2(
        radio_id=original.radio.radio_id,
        receiver_ids=(0, 1),
        sample_count=1,
        session_sample_start=1,
        host_request_utc_ns=interval,
        host_request_monotonic_ns=interval,
        device_sample_counter=5,
        source_sequence=5,
        continuity=ContinuityStatus.GAP_BEFORE,
        missing_samples_before=4,
        overflow_observed=True,
        stream_generation="generation-0",
        metadata_abi_version=1,
        metadata_flags=1 << 11,
        kernel_buffers=8,
    )
    continuity = ContinuitySummaryV2.model_validate(
        {
            **original_continuity.model_dump(mode="json"),
            "enqueue_failure_count": 1,
            "terminal_enqueue_failure": rejected.model_dump(mode="json"),
            "terminal_rejected_gap_count": 1,
            "terminal_rejected_missing_sample_count": 4,
            "terminal_rejected_overflow_count": 1,
        }
    )
    stream = RecordingStreamV2.model_validate(
        {
            **original.model_dump(mode="json"),
            "state": StreamState.PARTIAL.value,
            "continuity": continuity.model_dump(mode="json"),
            "error": "refill queue full",
        }
    )

    presented = _radio_stream(stream, Path("/bulk/recording"), StorageStateV1.AVAILABLE)

    assert presented.continuity_gaps == 0
    assert presented.enqueue_failures == 1
    assert presented.terminal_rejected_gaps == 1
    assert presented.terminal_rejected_missing_samples == 4
    assert presented.terminal_rejected_overflows == 1
