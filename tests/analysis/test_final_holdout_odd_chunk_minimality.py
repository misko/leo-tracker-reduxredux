from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from leo.analysis.research.doppler_holdout_odd_adapter import (
    AuthorizedOddChunk,
    preflight_exact_authorized_odd_chunks,
    resolve_authorized_odd_chunks_by_target,
)
from leo.analysis.research.doppler_holdout_pre_response import (
    DopplerHoldoutPredictionLedgerV1,
    build_odd_qin_target_authorities,
)
from leo.analysis.research.doppler_holdout_selector_v2 import (
    DopplerHoldoutDerivedManifestV2,
)
from leo.contracts.digests import canonical_digest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SELECTOR = (
    REPOSITORY_ROOT
    / "reports/figures/2026_08_26_doppler_holdout_selector_v2/derived-manifest-v2.json"
)
PREDICTION = (
    REPOSITORY_ROOT
    / "reports/figures/2026_08_26_final_doppler_holdout_attempt2/prediction-ledger.json"
)
V2_PROTOCOL = REPOSITORY_ROOT / "config/analysis/final-doppler-holdout-satellite-protocol-v2.json"
REMOVED_CHUNK_IDENTITY = (
    "cap-20260825T050946-ab916a6d0eee",
    "stream-0",
    "radio-1040005e0b100007100010000bf33a5d4d/iq-000007.ci16.zst",
)
V2_CHUNK_DIGEST = "sha256:f86a9cf8177d22ba6cf8507a24d9cdc723c2325dc97c34eabded642ebda2111e"
MINIMAL_CHUNK_DIGEST = "sha256:ff8a776f7f07f17bede7ab2fcb7e8cfa0e144771c571380db7a2b690c195a4cb"
TARGET_COUNTS = {
    "cap-20260825T022235-0afd1298f096": 911,
    "cap-20260825T030000-49e936766343": 355,
    "cap-20260825T031521-ec8adc0e9426": 920,
    "cap-20260825T033028-374381fbcd3a": 918,
    "cap-20260825T033302-80fddf217eb5": 442,
    "cap-20260825T034929-bc0480bdb4a8": 112,
    "cap-20260825T035201-d0abaead734c": 324,
    "cap-20260825T041207-a5f08ab5bd42": 482,
    "cap-20260825T043656-2da9e806d487": 457,
    "cap-20260825T050946-ab916a6d0eee": 492,
}


def _chunk(document: dict[str, object]) -> AuthorizedOddChunk:
    return AuthorizedOddChunk(
        session_id=str(document["session_id"]),
        stream_id=str(document["stream_id"]),
        relative_path=str(document["relative_path"]),
        sample_start=int(document["sample_start"]),
        sample_count=int(document["sample_count"]),
        compressed_sha256=str(document["compressed_sha256"]),
    )


def test_real_5413_target_minimized_chunks_are_sufficient_minimal_and_equivalent() -> None:
    """Prove the correction from frozen metadata only; no recording source is opened."""

    manifest = DopplerHoldoutDerivedManifestV2.model_validate_json(SELECTOR.read_text())
    prediction = DopplerHoldoutPredictionLedgerV1.model_validate_json(PREDICTION.read_text())
    protocol = json.loads(V2_PROTOCOL.read_text())
    chunk_documents = protocol["authorized_odd_chunks"]
    assert isinstance(chunk_documents, list)
    assert canonical_digest(chunk_documents) == V2_CHUNK_DIGEST
    minimal_documents = [
        item
        for item in chunk_documents
        if (
            item["session_id"],
            item["stream_id"],
            item["relative_path"],
        )
        != REMOVED_CHUNK_IDENTITY
    ]
    assert len(chunk_documents) == 11
    assert len(minimal_documents) == 10
    assert canonical_digest(minimal_documents) == MINIMAL_CHUNK_DIGEST

    authorities = build_odd_qin_target_authorities(
        manifest,
        prediction,
        residual_half_width_hz=float(protocol["odd_response"]["residual_half_width_hz"]),
    )
    assert len(authorities) == prediction.target_count == 5_413
    assert Counter(item.target.session_id for item in authorities) == TARGET_COUNTS
    sample_rates = {
        capture.session_id: capture.sample_rate_hz
        for capture in manifest.captures
        if capture.status == "evaluable"
    }
    original_chunks = tuple(_chunk(item) for item in chunk_documents)
    minimal_chunks = tuple(_chunk(item) for item in minimal_documents)

    original_resolution = resolve_authorized_odd_chunks_by_target(
        authorities=authorities,
        sample_rate_hz_by_session=sample_rates,
        authorized_chunks=original_chunks,
    )
    minimal_resolution = preflight_exact_authorized_odd_chunks(
        authorities=authorities,
        sample_rate_hz_by_session=sample_rates,
        authorized_chunks=minimal_chunks,
    )

    assert minimal_resolution == original_resolution
    used = Counter(chunk for target_chunks in minimal_resolution for chunk in target_chunks)
    assert set(used) == set(minimal_chunks)
    assert all(used[chunk] > 0 for chunk in minimal_chunks)
    removed = next(
        chunk
        for chunk in original_chunks
        if (chunk.session_id, chunk.stream_id, chunk.relative_path) == REMOVED_CHUNK_IDENTITY
    )
    assert all(removed not in target_chunks for target_chunks in original_resolution)
    with pytest.raises(ValueError, match="unused chunk"):
        preflight_exact_authorized_odd_chunks(
            authorities=authorities,
            sample_rate_hz_by_session=sample_rates,
            authorized_chunks=original_chunks,
        )

    for required_chunk in minimal_chunks:
        with pytest.raises(ValueError, match="cover"):
            preflight_exact_authorized_odd_chunks(
                authorities=authorities,
                sample_rate_hz_by_session=sample_rates,
                authorized_chunks=tuple(
                    chunk for chunk in minimal_chunks if chunk != required_chunk
                ),
            )
