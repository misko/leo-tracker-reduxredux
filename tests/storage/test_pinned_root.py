from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CaptureRecordingIdentity, RunExecutionInfo
from leo.pipeline import ProductSpec, ScopeIdentityV1
from leo.processing import InputManifestMismatchError, RecordingIqReaderProvider
from leo.storage import BundleNotFoundError, PinnedLocalRoot, RecordingStore
from leo.storage import pinned as pinned_module

from .test_recording_store import _prepare_bundle


def test_pinned_stores_survive_root_path_swap_without_alternate_writes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bulk"
    initial = RecordingStore(root)
    prepared = _prepare_bundle(initial, "pinned-recording")
    prepared.writer.publish(prepared.manifest)
    pinned = PinnedLocalRoot(root)
    recordings = RecordingStore.open_pinned(pinned)
    artifacts = AnalysisArtifactStore.open_pinned(pinned)
    pinned.close()
    reused = [os.open("/dev/null", os.O_RDONLY) for _index in range(8)]

    retained = tmp_path / "retained"
    alternate = tmp_path / "alternate"
    (alternate / "recordings" / "2026" / "01" / "01" / "missing").mkdir(parents=True)
    root.rename(retained)
    root.symlink_to(alternate, target_is_directory=True)

    try:
        published = artifacts.publish_json(
            session_id="session-a",
            run_id="run-a",
            stage_key="stage-a",
            scope_key="scope-a",
            product=ProductSpec(kind="pinned.product"),
            document={"pinned": True},
        )

        assert artifacts.read_json(published.logical_uri, published.digest) == {"pinned": True}
        assert recordings.inspect("pinned-recording").manifest == prepared.manifest
        assert recordings.read_ci16("pinned-recording", "stream-a", 0, 6).shape == (6, 2, 2)
        assert tuple((retained / "analysis").rglob("pinned.product.v1.json"))
        assert not (alternate / "analysis").exists()
        with pytest.raises(BundleNotFoundError):
            recordings.inspect("missing")
    finally:
        for descriptor in reused:
            os.close(descriptor)


def test_typed_iq_reader_rejects_child_swap_before_any_outside_byte_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "bulk"
    initial = RecordingStore(root)
    prepared = _prepare_bundle(initial, "typed-fd-recording")
    published = prepared.writer.publish(prepared.manifest)
    pinned = PinnedLocalRoot(root)
    recordings = RecordingStore.open_pinned(pinned)
    pinned.close()
    provider = RecordingIqReaderProvider(recordings)
    identity = CaptureRecordingIdentity(
        session_id=published.session_id,
        bundle_uri=published.uri,
        manifest_digest=published.manifest_sha256,
    )
    attestation = provider.verify_integrity(identity)
    execution = RunExecutionInfo(
        run_id="typed-run",
        session_id=published.session_id,
        pipeline_release_id="1" * 40,
        pipeline_configuration={},
        input_manifest_digest=published.manifest_sha256,
        trigger="reprocess",
        bundle_uri=published.uri,
        raw_integrity_attestation_digest=attestation.attestation_digest,
        raw_integrity_attestation=attestation.model_dump(mode="json"),
    )
    scope = ScopeIdentityV1.receiver_path(
        session_id=published.session_id,
        stream_id="stream-a",
        receiver_id=0,
    )
    reader = provider.open_scope(execution, scope)
    chunk = published.path / prepared.manifest.streams[0].chunks[0].relative_path
    retained = tmp_path / "retained.zst"
    outside = tmp_path / "outside-secret.zst"
    chunk.rename(retained)
    outside.write_bytes(b"outside bytes must never be opened")
    chunk.symlink_to(outside)
    reads: list[tuple[int, int]] = []
    real_pread = os.pread

    def observed_pread(fd: int, length: int, offset: int) -> bytes:
        reads.append((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
        return real_pread(fd, length, offset)

    monkeypatch.setattr("leo.processing.adapters.os.pread", observed_pread)
    with pytest.raises(InputManifestMismatchError, match="binding changed"):
        tuple(reader.iter_blocks(block_samples=4))
    outside_stat = outside.stat()
    assert (outside_stat.st_dev, outside_stat.st_ino) not in reads


def test_typed_integrity_never_follows_swapped_bundle_ancestor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "bulk"
    initial = RecordingStore(root)
    prepared = _prepare_bundle(initial, "typed-ancestor-recording")
    published = prepared.writer.publish(prepared.manifest)
    pinned = PinnedLocalRoot(root)
    recordings = RecordingStore.open_pinned(pinned)
    pinned.close()
    outside = tmp_path / "outside-bundle"
    shutil.copytree(published.path, outside)
    retained = tmp_path / "retained-bundle"
    published.path.rename(retained)
    published.path.symlink_to(outside, target_is_directory=True)
    outside_identities = {(item.stat().st_dev, item.stat().st_ino) for item in outside.rglob("*")}
    opened: list[tuple[int, int]] = []
    real_open = os.open

    def observed_open(*args: object, **kwargs: object) -> int:
        descriptor = real_open(*args, **kwargs)  # type: ignore[arg-type]
        metadata = os.fstat(descriptor)
        opened.append((metadata.st_dev, metadata.st_ino))
        return descriptor

    monkeypatch.setattr("leo.storage.pinned.os.open", observed_open)
    provider = RecordingIqReaderProvider(recordings)
    with pytest.raises(ValueError, match="symlink"):
        provider.verify_integrity(
            CaptureRecordingIdentity(
                session_id=published.session_id,
                bundle_uri=published.uri,
                manifest_digest=published.manifest_sha256,
            )
        )
    assert outside_identities.isdisjoint(opened)


def test_typed_reader_retains_original_bundle_after_ancestor_swap_and_fd_reuse(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bulk"
    initial = RecordingStore(root)
    prepared = _prepare_bundle(initial, "typed-retained-recording")
    published = prepared.writer.publish(prepared.manifest)
    root_capability = PinnedLocalRoot(root)
    recordings = RecordingStore.open_pinned(root_capability)
    root_capability.close()
    reused = [os.open("/dev/null", os.O_RDONLY) for _ in range(16)]
    provider = RecordingIqReaderProvider(recordings)
    identity = CaptureRecordingIdentity(
        session_id=published.session_id,
        bundle_uri=published.uri,
        manifest_digest=published.manifest_sha256,
    )
    attestation = provider.verify_integrity(identity)
    execution = RunExecutionInfo(
        run_id="typed-retained-run",
        session_id=published.session_id,
        pipeline_release_id="1" * 40,
        pipeline_configuration={},
        input_manifest_digest=published.manifest_sha256,
        trigger="reprocess",
        bundle_uri=published.uri,
        raw_integrity_attestation_digest=attestation.attestation_digest,
        raw_integrity_attestation=attestation.model_dump(mode="json"),
    )
    reader = provider.open_scope(
        execution,
        ScopeIdentityV1.receiver_path(
            session_id=published.session_id,
            stream_id="stream-a",
            receiver_id=0,
        ),
    )
    outside = tmp_path / "outside-bundle"
    shutil.copytree(published.path, outside)
    retained = tmp_path / "retained-bundle"
    published.path.rename(retained)
    published.path.symlink_to(outside, target_is_directory=True)
    try:
        blocks = tuple(reader.iter_blocks(block_samples=2))
        assert sum(block.samples.shape[0] for block in blocks) == 6
    finally:
        for descriptor in reused:
            os.close(descriptor)


def test_typed_capability_cache_is_bounded_and_shutdown_waits_for_active_reader(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bulk"
    initial = RecordingStore(root)
    prepared = _prepare_bundle(initial, "typed-capability-lifetime")
    published = prepared.writer.publish(prepared.manifest)
    pinned = PinnedLocalRoot(root)
    recordings = RecordingStore.open_pinned(pinned)
    pinned.close()
    provider = RecordingIqReaderProvider(recordings)
    identity = CaptureRecordingIdentity(
        session_id=published.session_id,
        bundle_uri=published.uri,
        manifest_digest=published.manifest_sha256,
    )
    before = len(tuple(Path("/proc/self/fd").iterdir()))
    attestations = tuple(provider.verify_integrity(identity) for _ in range(100))
    after_reverify = len(tuple(Path("/proc/self/fd").iterdir()))
    assert after_reverify - before < 16
    attestation = attestations[-1]
    reader = provider.open_scope(
        RunExecutionInfo(
            run_id="typed-lifetime-run",
            session_id=published.session_id,
            pipeline_release_id="1" * 40,
            pipeline_configuration={},
            input_manifest_digest=published.manifest_sha256,
            trigger="reprocess",
            bundle_uri=published.uri,
            raw_integrity_attestation_digest=attestation.attestation_digest,
            raw_integrity_attestation=attestation.model_dump(mode="json"),
        ),
        ScopeIdentityV1.receiver_path(
            session_id=published.session_id,
            stream_id="stream-a",
            receiver_id=0,
        ),
    )
    provider.close()
    assert sum(block.samples.shape[0] for block in reader.iter_blocks(block_samples=2)) == 6
    reader.close()  # type: ignore[attr-defined]
    after_close = len(tuple(Path("/proc/self/fd").iterdir()))
    assert after_close <= before + 2


def test_typed_capability_cache_evicts_old_sessions_with_bounded_descriptors(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bulk"
    initial = RecordingStore(root)
    published = []
    for index in range(12):
        prepared = _prepare_bundle(initial, f"typed-capability-{index:02d}")
        published.append(prepared.writer.publish(prepared.manifest))
    pinned = PinnedLocalRoot(root)
    recordings = RecordingStore.open_pinned(pinned)
    pinned.close()
    provider = RecordingIqReaderProvider(recordings)
    before = len(tuple(Path("/proc/self/fd").iterdir()))

    for bundle in published:
        provider.verify_integrity(
            CaptureRecordingIdentity(
                session_id=bundle.session_id,
                bundle_uri=bundle.uri,
                manifest_digest=bundle.manifest_sha256,
            )
        )

    after = len(tuple(Path("/proc/self/fd").iterdir()))
    assert len(provider._capabilities) == provider._MAX_RETAINED_BUNDLES  # noqa: SLF001
    assert after - before < 100
    provider.close()


def test_typed_300_chunk_bundle_keeps_descriptor_plateau_bounded(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bulk"
    initial = RecordingStore(root)
    prepared = _prepare_bundle(
        initial,
        "typed-300-chunks",
        block_sizes=(1,) * 300,
        target_bytes=8,
    )
    published = prepared.writer.publish(prepared.manifest)
    assert len(prepared.receipt.chunks) == 300
    pinned = PinnedLocalRoot(root)
    recordings = RecordingStore.open_pinned(pinned)
    pinned.close()
    provider = RecordingIqReaderProvider(recordings)
    before = len(tuple(Path("/proc/self/fd").iterdir()))
    attestation = provider.verify_integrity(
        CaptureRecordingIdentity(
            session_id=published.session_id,
            bundle_uri=published.uri,
            manifest_digest=published.manifest_sha256,
        )
    )
    after_verify = len(tuple(Path("/proc/self/fd").iterdir()))
    assert after_verify - before < 12
    retained_root = tmp_path / "retained-300-root"
    alternate_root = tmp_path / "alternate-300-root"
    alternate_root.mkdir()
    root.rename(retained_root)
    root.symlink_to(alternate_root, target_is_directory=True)
    reader = provider.open_scope(
        RunExecutionInfo(
            run_id="typed-300-run",
            session_id=published.session_id,
            pipeline_release_id="1" * 40,
            pipeline_configuration={},
            input_manifest_digest=published.manifest_sha256,
            trigger="reprocess",
            bundle_uri=published.uri,
            raw_integrity_attestation_digest=attestation.attestation_digest,
            raw_integrity_attestation=attestation.model_dump(mode="json"),
        ),
        ScopeIdentityV1.receiver_path(
            session_id=published.session_id,
            stream_id="stream-a",
            receiver_id=0,
        ),
    )
    maximum = after_verify
    samples = 0
    with pytest.raises(ValueError, match="block_samples must be in"):
        tuple(reader.iter_blocks(block_samples=1_048_577))
    for block in reader.iter_blocks(block_samples=1):
        samples += block.samples.shape[0]
        maximum = max(maximum, len(tuple(Path("/proc/self/fd").iterdir())))
    assert samples == 300
    assert maximum - before < 16
    reader.close()  # type: ignore[attr-defined]
    first_chunk = prepared.manifest.streams[0].chunks[0]
    retained_bundle = retained_root / published.path.relative_to(root)
    chunk_path = retained_bundle / first_chunk.relative_path
    original_chunk = tmp_path / "retained-first-chunk.zst"
    outside_chunk = tmp_path / "outside-first-chunk.zst"
    chunk_path.rename(original_chunk)
    outside_chunk.write_bytes(b"never read this outside child")
    chunk_path.symlink_to(outside_chunk)
    swapped_reader = provider.open_scope(
        RunExecutionInfo(
            run_id="typed-300-swapped-run",
            session_id=published.session_id,
            pipeline_release_id="1" * 40,
            pipeline_configuration={},
            input_manifest_digest=published.manifest_sha256,
            trigger="reprocess",
            bundle_uri=published.uri,
            raw_integrity_attestation_digest=attestation.attestation_digest,
            raw_integrity_attestation=attestation.model_dump(mode="json"),
        ),
        ScopeIdentityV1.receiver_path(
            session_id=published.session_id,
            stream_id="stream-a",
            receiver_id=0,
        ),
    )
    with pytest.raises(InputManifestMismatchError, match="binding changed"):
        tuple(swapped_reader.iter_blocks(block_samples=1))
    swapped_reader.close()  # type: ignore[attr-defined]
    provider.close()


def test_pinned_stores_survive_namespace_swap_without_target_access(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bulk"
    initial = RecordingStore(root)
    prepared = _prepare_bundle(initial, "namespace-recording")
    prepared.writer.publish(prepared.manifest)
    pinned = PinnedLocalRoot(root)
    recordings = RecordingStore.open_pinned(pinned)
    artifacts = AnalysisArtifactStore.open_pinned(pinned)
    pinned.close()

    retained_recordings = root / "recordings-retained"
    retained_analysis = root / "analysis-retained"
    retained_spool_analysis = root / "spool" / "analysis-retained"
    alternate = tmp_path / "alternate"
    alternate_recordings = alternate / "recordings"
    alternate_analysis = alternate / "analysis"
    alternate_spool_analysis = alternate / "spool-analysis"
    for directory in (alternate_recordings, alternate_analysis, alternate_spool_analysis):
        directory.mkdir(parents=True)
    (root / "recordings").rename(retained_recordings)
    (root / "recordings").symlink_to(alternate_recordings, target_is_directory=True)
    (root / "analysis").rename(retained_analysis)
    (root / "analysis").symlink_to(alternate_analysis, target_is_directory=True)
    (root / "spool" / "analysis").rename(retained_spool_analysis)
    (root / "spool" / "analysis").symlink_to(
        alternate_spool_analysis,
        target_is_directory=True,
    )

    published = artifacts.publish_json(
        session_id="session-child",
        run_id="run-child",
        stage_key="stage-child",
        scope_key="scope-child",
        product=ProductSpec(kind="pinned.child-product"),
        document={"retained": True},
    )

    assert artifacts.read_json(published.logical_uri, published.digest) == {"retained": True}
    assert recordings.inspect("namespace-recording").manifest == prepared.manifest
    assert recordings.read_ci16("namespace-recording", "stream-a", 0, 6).shape == (6, 2, 2)
    assert tuple(retained_analysis.rglob("pinned.child-product.v1.json"))
    assert not tuple(alternate_analysis.rglob("*"))
    assert not tuple(alternate_spool_analysis.rglob("*"))
    assert not tuple(alternate_recordings.rglob("*"))


def test_pinned_root_rejects_qnap_before_any_filesystem_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes: list[object] = []

    def forbidden_open(*args: object, **kwargs: object) -> int:
        probes.append((args, kwargs))
        raise AssertionError("QNAP target reached a filesystem syscall")

    monkeypatch.setattr(pinned_module.os, "open", forbidden_open)
    with pytest.raises(ValueError, match="absolute local storage"):
        PinnedLocalRoot(Path("/mnt/qnap01/never-probe"))
    assert probes == []


def test_pinned_root_does_not_follow_ancestor_symlink_toward_qnap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    link = tmp_path / "qnap-link"
    link.symlink_to("/mnt/qnap01/never-probe", target_is_directory=True)
    real_open = pinned_module.os.open
    probes: list[object] = []

    def observed_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        probes.append(path)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(pinned_module.os, "open", observed_open)
    with pytest.raises(ValueError, match="symlink component"):
        PinnedLocalRoot(link)

    assert "/mnt/qnap01/never-probe" not in probes
