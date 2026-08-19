from __future__ import annotations

import hashlib
import json
import stat
from copy import deepcopy
from pathlib import Path

import pytest

from leo.importing import (
    ExistingFixtureConflictError,
    FixtureImporter,
    ManifestValidationError,
    RecordingCorpusIngestService,
    SourceVerificationError,
    TargetBoundaryError,
    load_corpus_manifest,
    load_recording_ingest_manifest,
)
from leo.storage import RecordingStore


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _document(
    source: Path,
    local_root: Path,
    *,
    source_bytes: bytes,
    offset: int = 3,
    count: int = 5,
    target: str = "recording.ci16",
    requirement: str = "REQUIRED",
) -> dict[str, object]:
    selected = source_bytes[offset : offset + count]
    return {
        "schema": "org.leo.test-corpus/v1",
        "corpus_id": "test-corpus-v1",
        "policy": {
            "source_access": "read_only",
            "source_type": "TEST",
            "tags": ["TEST"],
            "retention_hold": "indefinite",
            "default_local_root": str(local_root),
            "license": "NOASSERTION",
            "redistribution": "not-assessed",
        },
        "fixtures": [
            {
                "fixture_id": "fixture-one",
                "requirement": requirement,
                "role": "test-real-iq",
                "metadata": {
                    "truth": {
                        "tier": "unlabeled_sky",
                        "target_present": None,
                    }
                },
                "artifacts": [
                    {
                        "artifact_id": "iq",
                        "kind": "iq",
                        "source_absolute_path": str(source),
                        "source_byte_count": len(source_bytes),
                        "source_sha256": _sha256(source_bytes),
                        "selected_byte_offset": offset,
                        "selected_byte_count": count,
                        "selected_sha256": _sha256(selected),
                        "target_relative_path": target,
                    }
                ],
            }
        ],
    }


def _load(tmp_path: Path, document: dict[str, object]):
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return load_corpus_manifest(path)


def _ingest_mapping(tmp_path: Path, fixture_id: str = "fixture-one"):
    path = tmp_path / "recording-ingest-v1.json"
    path.write_text(
        json.dumps(
            {
                "schema": "org.leo.test-recording-ingest/v1",
                "corpus_id": "test-corpus-v1",
                "fixtures": [
                    {
                        "fixture_id": fixture_id,
                        "center_frequency_hz": 1_709_687_500,
                        "bandwidth_hz": 2_500_000,
                        "sample_rate_hz": 2_500_000,
                        "sample_count": 8,
                        "receiver_count": 2,
                        "gain_mode": "manual",
                        "gains_db": [50.0, 50.0],
                        "timing_uncertainty_ns": 1000,
                        "streams": [
                            {
                                "artifact_id": "iq",
                                "radio_id": "pluto-test",
                                "first_sample_utc_ns": 1_786_655_533_795_059_712,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return load_recording_ingest_manifest(path)


def test_final_manifest_is_closed_and_honest_about_required_and_missing_data() -> None:
    manifest = load_corpus_manifest(Path("corpus/manifest.json").resolve())

    assert manifest.default_local_root == Path("/srv/bulk/leo/test-corpus")
    assert [item.fixture_id for item in manifest.required_fixtures()] == [
        "retro-positive-68p7",
        "sync-same-l-ch1-lower-20260814t001700z",
    ]
    by_id = {item.fixture_id: item for item in manifest.fixtures}
    assert by_id["j1-calibrated-positive-41p6"].requirement == "PLANNED"
    assert by_id["j1-calibrated-positive-41p6"].metadata["availability"]["source_present"] is False
    assert "ingest" not in by_id["retro-positive-68p7"].metadata
    ingest = load_recording_ingest_manifest(Path("corpus/recording-ingest-v1.json").resolve())
    assert ingest.corpus_id == manifest.corpus_id
    assert set(ingest.fixtures) == {
        "retro-positive-68p7",
        "sync-same-l-ch1-lower-20260814t001700z",
    }


def test_materialize_copies_only_selected_range_and_forces_test_hold(
    tmp_path: Path,
) -> None:
    source_bytes = b"prefix-selected-suffix"
    source = (tmp_path / "source.ci16").resolve()
    source.write_bytes(source_bytes)
    source.chmod(0o440)
    before_stat = source.stat()
    root = (tmp_path / "corpus").resolve()
    document = _document(
        source,
        root,
        source_bytes=source_bytes,
        offset=7,
        count=8,
    )
    manifest = _load(tmp_path, document)

    [result] = FixtureImporter(root).materialize_required(manifest)

    assert result.status == "created"
    assert (result.directory / "recording.ci16").read_bytes() == b"selected"
    fixture_document = json.loads(
        (result.directory / "fixture-manifest.json").read_text(encoding="utf-8")
    )
    assert fixture_document["source_type"] == "TEST"
    assert fixture_document["tags"] == ["TEST"]
    assert fixture_document["retention"] == {
        "hold": "indefinite",
        "protected": True,
        "reason": "TEST-corpus scientific regression fixture",
    }
    hold = json.loads((result.directory / "retention-hold.json").read_text(encoding="utf-8"))
    assert hold["source_type"] == "TEST"
    assert hold["tags"] == ["TEST"]
    assert hold["hold"] == "indefinite"
    assert hold["protected"] is True
    assert stat.S_IMODE((result.directory / "recording.ci16").stat().st_mode) == 0o440
    assert stat.S_IMODE((result.directory / "fixture-manifest.json").stat().st_mode) == 0o440
    assert source.read_bytes() == source_bytes
    after_stat = source.stat()
    assert (
        after_stat.st_dev,
        after_stat.st_ino,
        after_stat.st_size,
        after_stat.st_mtime_ns,
        after_stat.st_ctime_ns,
    ) == (
        before_stat.st_dev,
        before_stat.st_ino,
        before_stat.st_size,
        before_stat.st_mtime_ns,
        before_stat.st_ctime_ns,
    )


def test_materialize_is_idempotent_and_reverifies_existing_payload(tmp_path: Path) -> None:
    source_bytes = b"0123456789abcdef"
    source = (tmp_path / "source.ci16").resolve()
    source.write_bytes(source_bytes)
    root = (tmp_path / "corpus").resolve()
    manifest = _load(tmp_path, _document(source, root, source_bytes=source_bytes))
    importer = FixtureImporter(root)

    [created] = importer.materialize_required(manifest)
    protected = created.directory / "fixture-manifest.json"
    first_mtime = protected.stat().st_mtime_ns
    [existing] = importer.materialize_required(manifest)

    assert existing.status == "already_present"
    assert existing.directory == created.directory
    assert protected.stat().st_mtime_ns == first_mtime


def test_existing_payload_conflict_is_never_overwritten(tmp_path: Path) -> None:
    source_bytes = b"0123456789abcdef"
    source = (tmp_path / "source.ci16").resolve()
    source.write_bytes(source_bytes)
    root = (tmp_path / "corpus").resolve()
    manifest = _load(tmp_path, _document(source, root, source_bytes=source_bytes))
    importer = FixtureImporter(root)
    [created] = importer.materialize_required(manifest)
    payload = created.directory / "recording.ci16"
    payload.chmod(0o640)
    payload.write_bytes(b"wrong")

    with pytest.raises(ExistingFixtureConflictError, match="mismatch"):
        importer.materialize_required(manifest)

    assert payload.read_bytes() == b"wrong"
    assert source.read_bytes() == source_bytes


@pytest.mark.parametrize("mismatch", ["source", "selection"])
def test_digest_mismatch_fails_without_publishing_fixture(tmp_path: Path, mismatch: str) -> None:
    source_bytes = b"0123456789abcdef"
    source = (tmp_path / "source.ci16").resolve()
    source.write_bytes(source_bytes)
    root = (tmp_path / "corpus").resolve()
    document = _document(source, root, source_bytes=source_bytes)
    artifact = document["fixtures"][0]["artifacts"][0]
    digest_field = "selected_sha256" if mismatch == "selection" else "source_sha256"
    artifact[digest_field] = "0" * 64
    manifest = _load(tmp_path, document)

    with pytest.raises(SourceVerificationError, match="SHA-256 mismatch"):
        FixtureImporter(root).materialize_required(manifest)

    assert not (root / "fixture-one").exists()
    assert not tuple(root.glob("*.partial"))
    assert source.read_bytes() == source_bytes


def test_source_size_and_range_are_checked(tmp_path: Path) -> None:
    source_bytes = b"0123456789abcdef"
    source = (tmp_path / "source.ci16").resolve()
    source.write_bytes(source_bytes)
    root = (tmp_path / "corpus").resolve()
    wrong_size = _document(source, root, source_bytes=source_bytes)
    wrong_size["fixtures"][0]["artifacts"][0]["source_byte_count"] += 1
    manifest = _load(tmp_path, wrong_size)
    with pytest.raises(SourceVerificationError, match="source size mismatch"):
        FixtureImporter(root).materialize_required(manifest)

    outside = _document(source, root, source_bytes=source_bytes)
    outside["fixtures"][0]["artifacts"][0]["selected_byte_offset"] = len(source_bytes)
    with pytest.raises(ManifestValidationError, match="range exceeds"):
        _load(tmp_path, outside)


@pytest.mark.parametrize("target", ["../outside.ci16", "/tmp/outside.ci16"])
def test_target_must_be_relative_and_confined(tmp_path: Path, target: str) -> None:
    source_bytes = b"0123456789abcdef"
    source = (tmp_path / "source.ci16").resolve()
    source.write_bytes(source_bytes)
    document = _document(
        source,
        (tmp_path / "corpus").resolve(),
        source_bytes=source_bytes,
        target=target,
    )

    with pytest.raises(TargetBoundaryError):
        _load(tmp_path, document)


def test_existing_symlink_cannot_redirect_fixture_outside_root(tmp_path: Path) -> None:
    source_bytes = b"0123456789abcdef"
    source = (tmp_path / "source.ci16").resolve()
    source.write_bytes(source_bytes)
    root = (tmp_path / "corpus").resolve()
    outside = tmp_path / "outside"
    outside.mkdir()
    root.mkdir()
    (root / "fixture-one").symlink_to(outside, target_is_directory=True)
    manifest = _load(tmp_path, _document(source, root, source_bytes=source_bytes))

    with pytest.raises(TargetBoundaryError, match="outside configured"):
        FixtureImporter(root).materialize_required(manifest)

    assert not tuple(outside.iterdir())


@pytest.mark.parametrize(
    ("location", "value"),
    [
        ("artifact_key", False),
        ("metadata_value", "rename"),
        ("metadata_value", "remove-after-copy"),
    ],
)
def test_source_mutation_concepts_are_rejected(
    tmp_path: Path, location: str, value: object
) -> None:
    source_bytes = b"0123456789abcdef"
    source = (tmp_path / "source.ci16").resolve()
    source.write_bytes(source_bytes)
    document = _document(source, (tmp_path / "corpus").resolve(), source_bytes=source_bytes)
    if location == "artifact_key":
        document["fixtures"][0]["artifacts"][0]["delete_source"] = value
    else:
        document["fixtures"][0]["metadata"]["source_action"] = value

    with pytest.raises(ManifestValidationError, match="mutation concept"):
        _load(tmp_path, document)


def test_public_importer_api_has_no_source_mutation_operations() -> None:
    public = {name for name in dir(FixtureImporter) if not name.startswith("_")}

    assert {"delete", "move", "rename", "unlink", "remove"}.isdisjoint(public)
    assert public == {"local_corpus_root", "materialize", "materialize_required"}


@pytest.mark.parametrize("target", [Path("/mnt/qnap01"), Path("/mnt/qnap01/leo-test")])
def test_import_target_can_never_be_beneath_read_only_qnap(target: Path) -> None:
    with pytest.raises(TargetBoundaryError, match="read-only /mnt/qnap01"):
        FixtureImporter(target)


def test_required_materialization_does_not_touch_missing_planned_source(
    tmp_path: Path,
) -> None:
    source_bytes = b"0123456789abcdef"
    source = (tmp_path / "source.ci16").resolve()
    source.write_bytes(source_bytes)
    root = (tmp_path / "corpus").resolve()
    document = _document(source, root, source_bytes=source_bytes)
    planned = deepcopy(document["fixtures"][0])
    planned["fixture_id"] = "future-fixture"
    planned["requirement"] = "PLANNED"
    planned["artifacts"][0]["source_absolute_path"] = str((tmp_path / "absent.ci16").resolve())
    document["fixtures"].append(planned)
    manifest = _load(tmp_path, document)

    [result] = FixtureImporter(root).materialize_required(manifest)

    assert result.fixture_id == "fixture-one"
    assert not (root / "future-fixture").exists()


def test_source_below_target_root_is_rejected(tmp_path: Path) -> None:
    root = (tmp_path / "corpus").resolve()
    root.mkdir()
    source_bytes = b"0123456789abcdef"
    source = root / "source.ci16"
    source.write_bytes(source_bytes)
    manifest = _load(tmp_path, _document(source, root, source_bytes=source_bytes))

    with pytest.raises(TargetBoundaryError, match="cannot be used as an import source"):
        FixtureImporter(root).materialize_required(manifest)


def test_materialized_ci16_becomes_idempotent_verified_test_recording(tmp_path: Path) -> None:
    source_bytes = bytes(range(64))
    source = (tmp_path / "source.ci16").resolve()
    source.write_bytes(source_bytes)
    corpus_root = (tmp_path / "corpus").resolve()
    document = _document(
        source,
        corpus_root,
        source_bytes=source_bytes,
        offset=0,
        count=64,
    )
    manifest = _load(tmp_path, document)
    ingest = _ingest_mapping(tmp_path)
    materialized = FixtureImporter(corpus_root).materialize_required(manifest)
    recordings = RecordingStore(tmp_path / "bulk")
    service = RecordingCorpusIngestService(recordings)

    [created] = service.ingest_required(manifest, materialized, ingest)
    [existing] = service.ingest_required(manifest, materialized, ingest)

    assert created.status == "created"
    assert existing.status == "already_present"
    assert existing.bundle_uri == created.bundle_uri
    recordings.verify(created.session_id)
    bundle = recordings.inspect(created.session_id)
    assert bundle.manifest.source_type.value == "test"
    assert bundle.manifest.tags == ("TEST",)
    assert bundle.manifest.producer.source_revision == ingest.source_sha256
    assert bundle.manifest.streams[0].timing.first_sample.method.value == "imported"
    samples = recordings.read_ci16(bundle, "stream-0", 0, 8)
    assert samples.tobytes() == source_bytes
