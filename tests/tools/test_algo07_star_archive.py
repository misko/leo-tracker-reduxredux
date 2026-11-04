import hashlib
import json
from types import SimpleNamespace

import pytest
from algo07_star_archive import execute, materialize, verify_view

from leo.operations.tle_archive import TleArchiveReader


def fixture(tmp_path):
    root = tmp_path/'live'
    folder = root/'archive/space-track'
    folder.mkdir(parents=True)
    payload = b'frozen snapshot\n'
    digest = hashlib.sha256(payload).hexdigest()
    snapshot = folder/f'1-{digest}.tle'
    snapshot.write_bytes(payload)
    manifest = tmp_path/'frozen.json'
    manifest.write_text(json.dumps(dict(
        metadata=dict(tle_snapshot_paths=[str(snapshot)]),
        files=[dict(path=str(snapshot), sha256=digest)])))
    return TleArchiveReader(root), manifest, snapshot


def test_new_live_snapshots_do_not_enter_the_frozen_view(tmp_path):
    reader, manifest, snapshot = fixture(tmp_path)
    payload = b'later snapshot\n'
    newer = snapshot.parent/f'2-{hashlib.sha256(payload).hexdigest()}.tle'
    newer.write_bytes(payload)
    target = tmp_path/'clone'
    receipt = materialize(reader, manifest, target)
    assert len(receipt['files']) == 1
    assert verify_view(target, manifest) == receipt
    assert len(reader.list_snapshots()) == 2
    assert len(TleArchiveReader(target).list_snapshots()) == 1


def test_corrupted_clone_is_rejected(tmp_path):
    reader, manifest, _ = fixture(tmp_path)
    target = tmp_path/'clone'
    receipt = materialize(reader, manifest, target)
    (target/receipt['files'][0]['path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='bytes or identity changed'):
        verify_view(target, manifest)


def test_clone_cannot_overwrite_original_archive_or_qnap(tmp_path):
    reader, manifest, _ = fixture(tmp_path)
    for target in (reader.root, reader.root/'clone', tmp_path, '/mnt/qnap01/no'):
        with pytest.raises(ValueError, match='separate from its source'):
            materialize(reader, manifest, target)


def test_changed_fixture_binding_is_rejected(tmp_path):
    reader, manifest, _ = fixture(tmp_path)
    target = tmp_path/'clone'
    materialize(reader, manifest, target)
    manifest.write_text(manifest.read_text()+'\n')
    with pytest.raises(ValueError, match='different frozen fixture'):
        verify_view(target, manifest)


def test_namespace_failure_never_mounts_over_parent_archive(tmp_path, monkeypatch):
    reader, manifest, _ = fixture(tmp_path)
    target = tmp_path/'clone'
    materialize(reader, manifest, target)
    monkeypatch.setattr('algo07_star_archive.ARCHIVE', reader.root)
    monkeypatch.setattr('algo07_star_archive.os.unshare', lambda _: None)
    monkeypatch.setattr('algo07_star_archive.os.readlink', lambda _: 'same namespace')
    mounts = []
    monkeypatch.setattr('algo07_star_archive.subprocess.run', lambda *a, **k: mounts.append(a))
    with pytest.raises(ValueError, match='parent namespace'):
        execute(SimpleNamespace(view=target, manifest=manifest, command=['/bin/true']))
    assert not mounts
