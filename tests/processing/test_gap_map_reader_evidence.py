from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from leo.catalog import CaptureRecordingIdentity, RunExecutionInfo
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.pipeline import GapAwareIqReader, ScopeIdentityV1
from leo.processing import RecordingIqReaderProvider
from leo.radio import FakeRadioSource
from leo.storage import BundleCorruptionError
from tests.acquisition.test_continuity_capture_v2 import _coordinator, _plan


def test_typed_reader_returns_digest_verified_timeline_rebuilt_gap_evidence(
    tmp_path: Path,
) -> None:
    coordinator, published = _capture_v2(tmp_path, "typed-gap-evidence", gap=True)
    provider = RecordingIqReaderProvider(
        coordinator.store,
        allow_unpinned_integrity_for_tests=True,
    )
    identity = CaptureRecordingIdentity(
        session_id=published.session_id,
        bundle_uri=published.uri,
        manifest_digest=published.manifest_sha256,
    )
    attestation = provider.verify_integrity(identity)
    reader = cast(
        GapAwareIqReader,
        provider.open_scope(
            _execution(
                published,
                attestation.attestation_digest,
                attestation.model_dump(mode="json"),
            ),
            ScopeIdentityV1.receiver_path(
                session_id=published.session_id,
                stream_id="stream-0",
                receiver_id=0,
            ),
        ),
    )

    evidence = reader.gap_map_evidence()

    stream = published.manifest.streams[0]
    assert evidence.persisted_sha256 == stream.gap_map_sha256
    assert evidence.gap_map.stream_id == stream.stream_id
    assert evidence.gap_map.observed_sample_count == stream.captured_sample_count
    assert evidence.gap_map.missing_sample_count == 4
    provider.close()


def test_integrity_verification_rejects_tampered_persisted_gap_map_bytes(
    tmp_path: Path,
) -> None:
    coordinator, published = _capture_v2(tmp_path, "typed-gap-digest-tamper", gap=False)
    gap_path = _gap_path(published)
    payload = bytearray(gap_path.read_bytes())
    payload[-2] = ord("0") if payload[-2] != ord("0") else ord("1")
    gap_path.write_bytes(payload)
    provider = RecordingIqReaderProvider(
        coordinator.store,
        allow_unpinned_integrity_for_tests=True,
    )

    with pytest.raises(BundleCorruptionError, match="gap-map digest mismatch"):
        provider.verify_integrity(
            CaptureRecordingIdentity(
                session_id=published.session_id,
                bundle_uri=published.uri,
                manifest_digest=published.manifest_sha256,
            )
        )


def test_integrity_verification_rejects_valid_gap_map_that_disagrees_with_timeline(
    tmp_path: Path,
) -> None:
    coordinator, published = _capture_v2(tmp_path, "typed-gap-rebuild-mismatch", gap=False)
    gap_path = _gap_path(published)
    gap_document = json.loads(gap_path.read_bytes())
    gap_document["first_device_sample_counter"] += 1
    gap_payload = canonical_json_bytes(gap_document)
    gap_path.write_bytes(gap_payload)

    manifest_path = published.path / "manifest.json"
    manifest_document = json.loads(manifest_path.read_bytes())
    manifest_document["streams"][0]["gap_map_sha256"] = sha256_digest(gap_payload)
    manifest_payload = canonical_json_bytes(manifest_document)
    manifest_path.write_bytes(manifest_payload)
    provider = RecordingIqReaderProvider(
        coordinator.store,
        allow_unpinned_integrity_for_tests=True,
    )

    with pytest.raises(
        BundleCorruptionError,
        match="disagrees with its retained verified timeline",
    ):
        provider.verify_integrity(
            CaptureRecordingIdentity(
                session_id=published.session_id,
                bundle_uri=published.uri,
                manifest_digest=sha256_digest(manifest_payload),
            )
        )


def _capture_v2(tmp_path: Path, session_id: str, *, gap: bool):
    coordinator = _coordinator(tmp_path)
    result = coordinator.capture_once(
        _plan(sample_count=12),
        {
            "radio-a": FakeRadioSource(
                "radio-a",
                gaps_before_blocks={1: 4} if gap else None,
            )
        },
        session_id=session_id,
    )
    assert result.bundle is not None
    return coordinator, result.bundle


def _gap_path(published: object) -> Path:
    stream = published.manifest.streams[0]
    assert stream.gap_map_relative_path is not None
    return published.path / stream.gap_map_relative_path


def _execution(published: object, attestation_digest: str, attestation: dict):
    return RunExecutionInfo(
        run_id="typed-gap-run",
        session_id=published.session_id,
        pipeline_release_id="1" * 40,
        pipeline_configuration={},
        input_manifest_digest=published.manifest_sha256,
        trigger="reprocess",
        bundle_uri=published.uri,
        raw_integrity_attestation_digest=attestation_digest,
        raw_integrity_attestation=attestation,
    )
