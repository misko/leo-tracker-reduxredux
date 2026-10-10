from __future__ import annotations

import pytest
from pydantic import ValidationError

from leo.contracts.short_window_recording import (
    ShortWindowChunkV1,
    ShortWindowIndexV1,
    ShortWindowManifestV1,
)


def test_index_cannot_claim_full_window_for_partial_iq() -> None:
    with pytest.raises(ValidationError, match="byte count"):
        ShortWindowIndexV1(
            sequence=0,
            target_id="a",
            sample_count=50_000,
            receiver_count=2,
            payload_offset_bytes=0,
            payload_bytes=399_992,
            iq_sha256="sha256:" + "0" * 64,
            acquisition={},
            powers=({}, {}),
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"receiver_ids": (0, 0)},
        {"receiver_ids": (0, 1, 2)},
        {"window_count": 1},
        {"failure": "disk full"},
        {"finalized_utc_ns": 0},
    ],
)
def test_manifest_rejects_inconsistent_coverage_or_status(updates: dict) -> None:
    value = dict(
        session_id="capture",
        configuration={},
        radio={},
        receiver_ids=(0, 1),
        created_utc_ns=1,
        finalized_utc_ns=2,
        status="complete",
        stop_reason="duration",
        window_count=0,
        chunks=(),
    )
    value.update(updates)
    with pytest.raises(ValidationError):
        ShortWindowManifestV1(**value)


def test_chunk_cannot_request_unbounded_compressed_allocation() -> None:
    digest = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="compressed_bytes"):
        ShortWindowChunkV1(
            chunk_index=0,
            first_sequence=0,
            window_count=1,
            payload_relative_path="iq.zst",
            index_relative_path="index.jsonl",
            uncompressed_bytes=400_000,
            compressed_bytes=104_857_601,
            index_bytes=100,
            uncompressed_sha256=digest,
            compressed_sha256=digest,
            index_sha256=digest,
        )
