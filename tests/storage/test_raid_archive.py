import json
from pathlib import Path

import pytest

from leo.storage.raid_archive import VerifiedDirectoryArchive
from leo.cli.raid_archive import eligible_names


def example(tmp_path):
    source = tmp_path / 'nvme'
    target = tmp_path / 'raid'
    recording = source / 'capture'
    (recording / 'empty').mkdir(parents=True)
    (recording / 'iq').write_bytes(bytes(range(256)) * 100)
    (recording / 'iq').chmod(0o640)
    (recording / 'empty').chmod(0o2750)
    (recording / 'run.json').write_text(json.dumps({'run_id': 'capture', 'state': 'stopped'}))
    return source, target


def test_verified_move_keeps_historical_paths_and_is_idempotent(tmp_path):
    source, target = example(tmp_path)
    original = (source / 'capture/iq').read_bytes()
    events = []
    archive = VerifiedDirectoryArchive(source, target, progress=events.append)
    receipt = archive.archive('capture')
    assert receipt['state'] == 'complete'
    assert (source / 'capture').is_symlink()
    assert (source / 'capture').resolve() == target / 'capture'
    assert (source / 'capture/iq').read_bytes() == original
    assert (target / 'capture/empty').is_dir()
    assert (target / 'capture/empty').stat().st_mode & 0o7777 == 0o2750
    assert (target / 'capture/iq').stat().st_mode & 0o777 == 0o640
    assert not list(source.glob('.archive-retired-*'))
    assert archive.archive('capture') == receipt
    assert events[-1]['state'] == 'complete'


def test_copy_failure_never_retires_source(tmp_path, monkeypatch):
    import leo.storage.raid_archive as module
    source, target = example(tmp_path)
    original = module._digest
    monkeypatch.setattr(module, '_digest', lambda p: 'bad' if p.name.endswith('.copying') else original(p))
    with pytest.raises(ValueError, match='SHA-256'):
        VerifiedDirectoryArchive(source, target).archive('capture')
    assert not (source / 'capture').is_symlink()
    assert (source / 'capture/iq').is_file()
    assert not (target / 'capture').exists()


@pytest.mark.parametrize('checkpoint', ['before_exchange', 'after_exchange', 'after_publish'])
def test_crash_recovery_completes_only_verified_publication(tmp_path, monkeypatch, checkpoint):
    import leo.storage.raid_archive as module
    source, target = example(tmp_path)
    exchange = module._exchange
    write_json = module._json
    if checkpoint == 'after_publish':
        def fail(path, value):
            if value['state'] == 'published':
                raise RuntimeError('crash after destination rename')
            return write_json(path, value)
        monkeypatch.setattr(module, '_json', fail)
    else:
        def fail(left, right):
            if checkpoint == 'after_exchange': exchange(left, right)
            raise RuntimeError('crash at source exchange')
        monkeypatch.setattr(module, '_exchange', fail)
    with pytest.raises(RuntimeError, match='crash'):
        module.VerifiedDirectoryArchive(source, target).archive('capture')
    monkeypatch.setattr(module, '_exchange', exchange)
    monkeypatch.setattr(module, '_json', write_json)
    assert module.VerifiedDirectoryArchive(source, target).archive('capture')['state'] == 'complete'
    assert (source / 'capture/iq').read_bytes() == (target / 'capture/iq').read_bytes()


def test_changed_source_preserves_original_and_refuses_retirement(tmp_path):
    source, target = example(tmp_path)
    def changed(event):
        if event['state'] == 'copying':
            (source / 'capture/new-data').write_bytes(b'new')
    with pytest.raises(ValueError, match='source directory changed'):
        VerifiedDirectoryArchive(source, target, progress=changed).archive('capture')
    assert not (source / 'capture').is_symlink()
    assert (source / 'capture/new-data').read_bytes() == b'new'


def test_corrupt_published_copy_blocks_pending_source_cleanup(tmp_path, monkeypatch):
    import leo.storage.raid_archive as module
    source, target = example(tmp_path)
    retire = module.VerifiedDirectoryArchive._retire
    def fail(*args): raise RuntimeError('crash before cleanup')
    monkeypatch.setattr(module.VerifiedDirectoryArchive, '_retire', fail)
    with pytest.raises(RuntimeError):
        module.VerifiedDirectoryArchive(source, target).archive('capture')
    assert module.VerifiedDirectoryArchive(source, target).pending_names() == ['capture']
    (target / 'capture/iq').write_bytes(b'corruption')
    monkeypatch.setattr(module.VerifiedDirectoryArchive, '_retire', retire)
    with pytest.raises(ValueError, match='digest changed'):
        module.VerifiedDirectoryArchive(source, target).archive('capture')
    assert list(source.glob('.archive-retired-*'))


def test_rejects_symlinks_qnap_and_conflicting_destinations(tmp_path):
    source, target = example(tmp_path)
    (source / 'capture/link').symlink_to(tmp_path / 'outside')
    with pytest.raises(ValueError, match='regular file'):
        VerifiedDirectoryArchive(source, target).archive('capture')
    with pytest.raises(ValueError, match='QNAP'):
        VerifiedDirectoryArchive(Path('/mnt/qnap01/spool'), target)
    (source / 'capture/link').unlink()
    (target / 'capture').mkdir()
    with pytest.raises(FileExistsError):
        VerifiedDirectoryArchive(source, target).archive('capture')
    with pytest.raises(ValueError, match='safe'):
        VerifiedDirectoryArchive(source, target).archive('../capture')


def test_automatic_selection_requires_terminal_checkpoint_and_skips_links(tmp_path):
    source, target = example(tmp_path)
    (source / 'active').mkdir()
    (source / 'active/run.json').write_text(json.dumps({'run_id': 'active', 'state': 'running'}))
    (source / 'alias').symlink_to(source / 'capture')
    assert eligible_names(source) == ['capture']
    assert eligible_names(source, include_incomplete=True) == ['active', 'capture']


def test_old_fast_input_manifest_and_iq_digests_still_replay(tmp_path):
    from tests.fast_scan_support import recording
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource
    source = tmp_path / 'nvme'
    recording(source, count=2)
    _, _, inventory = FastScanStore(tmp_path / 'bulk').ingest(source / 'segment')
    entry = inventory['segments'][0]
    before = [w.iq_sha256 for w in FastSegmentSource(entry).windows()]
    VerifiedDirectoryArchive(source, tmp_path / 'raid').archive('segment')
    assert [w.iq_sha256 for w in FastSegmentSource(entry).windows()] == before
