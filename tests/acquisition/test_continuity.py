from __future__ import annotations

import pytest

from leo.acquisition.continuity import (
    ContinuityChainValidator,
    ContinuityValidationError,
)
from leo.contracts.radio import IqBlockMetadataV1, IqBlockMetadataV2, NanosecondIntervalV1
from leo.contracts.states import ContinuityStatus


def _metadata(
    *,
    counter: int,
    sequence: int,
    generation: str = "capture-a",
    count: int = 4,
    continuity: ContinuityStatus = ContinuityStatus.UNKNOWN,
    missing: int = 0,
    overflow: bool = False,
) -> IqBlockMetadataV2:
    interval = NanosecondIntervalV1(lower_ns=1, upper_ns=2)
    return IqBlockMetadataV2(
        radio_id="radio-a",
        receiver_ids=(0, 1),
        sample_count=count,
        session_sample_start=0,
        host_request_utc_ns=interval,
        host_request_monotonic_ns=interval,
        device_sample_counter=counter,
        source_sequence=sequence,
        continuity=continuity,
        missing_samples_before=missing,
        overflow_observed=overflow,
        stream_generation=generation,
        metadata_abi_version=1,
        metadata_flags=0,
        kernel_buffers=8,
    )


def test_exact_gap_and_overflow_are_derived_from_counter_chain() -> None:
    validator = ContinuityChainValidator()

    first = validator.observe(_metadata(counter=100, sequence=17))
    gap = validator.observe(_metadata(counter=108, sequence=19, overflow=True))
    flag_only = validator.observe(_metadata(counter=112, sequence=20, overflow=True))

    assert first.continuity is ContinuityStatus.CONTIGUOUS
    assert gap.continuity is ContinuityStatus.GAP_BEFORE
    assert gap.missing_samples_before == 4
    assert flag_only.continuity is ContinuityStatus.OVERFLOW
    assert validator.gap_count == 1
    assert validator.missing_sample_count == 4
    assert validator.overflow_count == 2
    assert validator.validated


@pytest.mark.parametrize(
    ("counter", "sequence", "match"),
    [
        (103, 18, "counter"),
        (104, 17, "sequence"),
        (104, 19, "sequence"),
        (105, 18, "integer number"),
    ],
)
def test_duplicate_regression_overlap_and_sequence_disagreement_are_hard_errors(
    counter: int,
    sequence: int,
    match: str,
) -> None:
    validator = ContinuityChainValidator()
    validator.observe(_metadata(counter=100, sequence=17))

    with pytest.raises(ContinuityValidationError, match=match):
        validator.observe(_metadata(counter=counter, sequence=sequence))


def test_generation_change_requires_explicit_reset() -> None:
    validator = ContinuityChainValidator()
    validator.observe(_metadata(counter=100, sequence=17))

    with pytest.raises(ContinuityValidationError, match="generation"):
        validator.observe(_metadata(counter=104, sequence=18, generation="capture-b"))

    validator.reset()
    assert (
        validator.observe(_metadata(counter=5_000, sequence=2, generation="capture-b")).continuity
        is ContinuityStatus.CONTIGUOUS
    )


def test_storage_mode_rejects_declared_gap_that_disagrees_with_counter() -> None:
    validator = ContinuityChainValidator(validate_declared=True)
    validator.observe(_metadata(counter=100, sequence=17))

    with pytest.raises(ContinuityValidationError, match="declared continuity"):
        validator.observe(
            _metadata(
                counter=104,
                sequence=18,
                continuity=ContinuityStatus.GAP_BEFORE,
                missing=1,
            )
        )


def test_non_authoritative_v1_retains_one_sided_metadata_as_unobservable() -> None:
    interval = NanosecondIntervalV1(lower_ns=1, upper_ns=2)
    metadata = IqBlockMetadataV1(
        radio_id="radio-a",
        receiver_ids=(0, 1),
        sample_count=4,
        session_sample_start=0,
        host_request_utc_ns=interval,
        host_request_monotonic_ns=interval,
        source_sequence=7,
    )
    validator = ContinuityChainValidator(require_metadata=False)

    assert validator.observe(metadata) == metadata
    assert validator.validated is False
