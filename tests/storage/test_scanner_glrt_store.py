import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor

import pytest

from leo.storage.errors import BundleCorruptionError
from leo.storage.scanner_glrt import ScannerGlrtPresentationStore, ScannerGlrtStore
from tests.scanner.glrt_publication_fixtures import make_capture, make_publication


def test_atomic_idempotent_publication_does_not_change_capture(tmp_path):
    iq, capture = make_capture(tmp_path)
    publication = make_publication(capture)
    store = ScannerGlrtStore(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(store.publish, [publication] * 4))
    assert store.read(capture.session_id) == publication
    assert ScannerGlrtPresentationStore(iq, store).detail(capture.session_id) == publication
    assert iq.verify(capture.session_id).manifest_sha256 == capture.manifest_sha256
    assert not list((tmp_path / "scanner-hop-classifications").glob("*.partial"))
    with pytest.raises(BundleCorruptionError, match="differs"):
        store.publish(publication.model_copy(update={"published_utc_ns": 10}))
    assert store.read(capture.session_id) == publication


def test_maximum_inventory_fits_bounded_store_and_round_trips_exactly(tmp_path):
    _, capture = make_capture(tmp_path)
    source = make_publication(capture)
    evidence = source.evidence
    # Storage-capacity fixture only, not a source-attested 300-second recording.
    evidence = evidence.model_copy(
        update={
            "expected_results": 2500,
            "result_sequence_limit": 2500,
            "results": tuple(
                evidence.results[0].model_copy(update={"sequence": index, "visit": index})
                for index in range(2500)
            ),
        }
    )
    publication = source.model_copy(update={"evidence": evidence})
    store = ScannerGlrtStore(tmp_path)
    store.publish(publication)
    assert store.read(capture.session_id) == publication
    path = tmp_path / "scanner-hop-classifications" / f"{capture.session_id}.v1.json"
    assert path.stat().st_size < 4 * 1024 * 1024


def test_read_only_missing_namespace_creates_nothing_and_never_writes(tmp_path):
    reader = ScannerGlrtStore.open_read_only(tmp_path)
    assert reader.read("no-capture") is None
    assert list(tmp_path.iterdir()) == []
    _, capture = make_capture(tmp_path)
    with pytest.raises(PermissionError):
        reader.publish(make_publication(capture))


@pytest.mark.parametrize("stage", ["file_fsync", "link", "directory_fsync"])
def test_interrupted_publication_leaves_no_partial_final_or_iq_changes(
    tmp_path, monkeypatch, stage
):
    iq, capture = make_capture(tmp_path)
    publication = make_publication(capture)
    store = ScannerGlrtStore(tmp_path)
    original_fsync = os.fsync

    def fsync(descriptor):
        directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
        if (stage == "file_fsync" and not directory) or (stage == "directory_fsync" and directory):
            raise OSError("injected fsync failure")
        original_fsync(descriptor)

    def link(*args, **kwargs):
        raise OSError("injected atomic-link failure")

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fsync)
        if stage == "link":
            patch.setattr(os, "link", link)
        with pytest.raises(OSError, match="injected"):
            store.publish(publication)
    # A failed directory sync may leave a complete visible file. Do not erase
    # it or claim crash durability; a retry must be idempotent and sync it again.
    assert store.read(capture.session_id) == (publication if stage == "directory_fsync" else None)
    assert not list((tmp_path / "scanner-hop-classifications").glob("*.partial"))
    assert iq.verify(capture.session_id).manifest_sha256 == capture.manifest_sha256
    store.publish(publication)
    assert store.read(capture.session_id) == publication


@pytest.mark.parametrize("target", ["root", "namespace", "file"])
def test_symlink_paths_are_rejected_without_modifying_target(tmp_path, target):
    iq_root = tmp_path / "iq"
    _, capture = make_capture(iq_root)
    publication = make_publication(capture)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_text("untouched")
    if target == "root":
        link = tmp_path / "root-link"
        link.symlink_to(outside, target_is_directory=True)
        with pytest.raises(ValueError):
            ScannerGlrtStore(link)
    else:
        namespace = iq_root / "scanner-hop-classifications"
        if target == "namespace":
            namespace.symlink_to(outside, target_is_directory=True)
        else:
            namespace.mkdir()
            (namespace / f"{capture.session_id}.v1.json").symlink_to(sentinel)
        store = ScannerGlrtStore(iq_root)
        with pytest.raises((ValueError, OSError)):
            store.read(capture.session_id)
        with pytest.raises((ValueError, OSError)):
            store.publish(publication)
    assert sentinel.read_text() == "untouched"
    assert list(outside.iterdir()) == [sentinel]


@pytest.mark.parametrize("root", ["/mnt/qnap01", "/mnt/qnap01/scratch"])
def test_qnap_rejected_before_any_open(root):
    from pathlib import Path

    with pytest.raises(ValueError, match="local storage"):
        ScannerGlrtStore(Path(root))


def test_checksum_and_current_capture_binding_are_verified(tmp_path):
    iq, capture = make_capture(tmp_path)
    publication = make_publication(capture)
    store = ScannerGlrtStore(tmp_path)
    store.publish(publication)
    path = tmp_path / "scanner-hop-classifications" / f"{capture.session_id}.v1.json"
    original = path.read_bytes()
    sealed = json.loads(original)
    sealed["publication"]["evidence"]["results"][0]["cfo_hz"] += 1
    path.write_text(json.dumps(sealed))
    with pytest.raises(BundleCorruptionError):
        store.read(capture.session_id)
    path.write_bytes(original)
    # A valid standalone product for a stale input is rejected on presentation.
    other_root = tmp_path / "other"
    other_root.mkdir()
    stale_store = ScannerGlrtStore(other_root)
    stale_store.publish(
        publication.model_copy(update={"input_manifest_sha256": "sha256:" + "e" * 64})
    )
    with pytest.raises(ValueError, match="different capture"):
        ScannerGlrtPresentationStore(iq, stale_store).detail(capture.session_id)


def test_unsafe_ids_nonregular_files_and_oversize_are_bounded(tmp_path):
    store = ScannerGlrtStore(tmp_path)
    for value in ("../escape", "/absolute", "a/b", "a" * 129, ""):
        with pytest.raises(ValueError):
            store.read(value)
    namespace = tmp_path / "scanner-hop-classifications"
    namespace.mkdir()
    path = namespace / "test.v1.json"
    os.mkfifo(path)
    with pytest.raises(BundleCorruptionError, match="regular file"):
        store.read("test")
    path.unlink()
    with path.open("wb") as stream:
        stream.truncate(4 * 1024 * 1024 + 1)
    with pytest.raises(BundleCorruptionError, match="bounded"):
        store.read("test")
