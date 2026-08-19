from __future__ import annotations

import numpy as np
import pytest

from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.domain.iq import IqBlock


def _metadata() -> IqBlockMetadataV1:
    return IqBlockMetadataV1(
        radio_id="fake-a",
        receiver_ids=(0, 1),
        sample_count=3,
        session_sample_start=0,
        host_request_utc_ns=NanosecondIntervalV1(lower_ns=1, upper_ns=2),
        host_request_monotonic_ns=NanosecondIntervalV1(lower_ns=3, upper_ns=4),
    )


def test_iq_block_requires_exact_native_layout_and_becomes_read_only() -> None:
    samples = np.arange(12, dtype="<i2").reshape(3, 2, 2)
    block = IqBlock(samples=samples, metadata=_metadata())

    assert block.wire_bytes.nbytes == 24
    with pytest.raises(ValueError, match="read-only"):
        block.samples[0, 0, 0] = 7


def test_iq_block_rejects_wrong_shape_dtype_and_contiguity() -> None:
    with pytest.raises(ValueError, match="shape"):
        IqBlock(samples=np.zeros((3, 1, 2), dtype="<i2"), metadata=_metadata())
    with pytest.raises(ValueError, match="little-endian"):
        IqBlock(samples=np.zeros((3, 2, 2), dtype=">i2"), metadata=_metadata())
    with pytest.raises(ValueError, match="C-contiguous"):
        IqBlock(
            samples=np.zeros((3, 4, 2), dtype="<i2")[:, ::2, :],
            metadata=_metadata(),
        )
