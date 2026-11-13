"""Archive corruption and crash checks use only local temporary files."""

import importlib.util
import json
from pathlib import Path

import pytest


PATH = Path(__file__).resolve().parents[2] / 'tools/initial_discovery_archive.py'
SPEC = importlib.util.spec_from_file_location('initial_archive_tests', PATH)
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


def setup(tmp_path):
    stage_root, archive_root = tmp_path / 'stage', tmp_path / 'archive'
    stage, destination = stage_root / 'case/role', archive_root / 'case/role'
    stage.mkdir(parents=True)
    archive_root.mkdir()
    (stage / 'publication').mkdir()
    (stage / 'publication/evidence').write_bytes(b'bound evidence')
    (stage / 'request.json').write_text('absolute path binding')
    receipt = stage.parent / 'execution.json'
    receipt.write_text('{}')
    return dict(stage=stage, destination=destination, receipt_path=receipt,
                staging_root=stage_root, archive_root=archive_root)


def test_archive_preserves_absolute_paths_and_revalidates_resume(tmp_path):
    args = setup(tmp_path)
    before = archive.tree_binding(args['stage'])
    receipt = archive.archive_role(**args)
    assert args['stage'].is_symlink()
    assert archive.tree_binding(args['destination']) == before
    assert (args['stage'] / 'publication/evidence').read_bytes() == b'bound evidence'
    assert receipt['archive']['verified']
    assert archive.archive_role(**args) == receipt


def test_corrupt_partial_retains_original_and_partial(tmp_path):
    args = setup(tmp_path)
    partial = args['destination'].with_name('role.archive-partial')
    partial.mkdir(parents=True)
    (partial / 'request.json').write_text('truncated')
    with pytest.raises(ValueError, match='partial differs'):
        archive.archive_role(**args)
    assert args['stage'].is_dir() and not args['stage'].is_symlink()
    assert (partial / 'request.json').read_text() == 'truncated'


def test_corrupt_destination_retains_original(tmp_path):
    args = setup(tmp_path)
    args['destination'].mkdir(parents=True)
    (args['destination'] / 'request.json').write_text('wrong')
    with pytest.raises(ValueError, match='Archive differs'):
        archive.archive_role(**args)
    assert (args['stage'] / 'publication/evidence').read_bytes() == b'bound evidence'


def test_resume_after_rename_before_symlink(tmp_path, monkeypatch):
    args = setup(tmp_path)
    symlink = Path.symlink_to

    def crash(path, *parameters, **kwargs):
        raise OSError('simulated crash')

    monkeypatch.setattr(Path, 'symlink_to', crash)
    with pytest.raises(OSError, match='simulated'):
        archive.archive_role(**args)
    parked = args['stage'].with_name('role.archive-parked')
    assert parked.is_dir() and not args['stage'].exists()
    monkeypatch.setattr(Path, 'symlink_to', symlink)
    archive.archive_role(**args)
    assert args['stage'].is_symlink() and not parked.exists()


def test_changed_parked_original_is_retained(tmp_path, monkeypatch):
    args = setup(tmp_path)
    symlink = Path.symlink_to
    monkeypatch.setattr(Path, 'symlink_to', lambda *args, **kwargs: (_ for _ in ()).throw(OSError('crash')))
    with pytest.raises(OSError):
        archive.archive_role(**args)
    parked = args['stage'].with_name('role.archive-parked')
    (parked / 'request.json').write_text('changed original')
    monkeypatch.setattr(Path, 'symlink_to', symlink)
    with pytest.raises(ValueError, match='Parked original differs'):
        archive.archive_role(**args)
    assert parked.exists()


def test_changed_verified_archive_rejected(tmp_path):
    args = setup(tmp_path)
    archive.archive_role(**args)
    (args['destination'] / 'request.json').write_text('changed')
    with pytest.raises(ValueError, match='Verified archive changed'):
        archive.archive_role(**args)


def test_resume_after_partial_parked_cleanup(tmp_path, monkeypatch):
    args = setup(tmp_path)
    remove = archive.shutil.rmtree

    def partial_cleanup(path):
        (path / 'request.json').unlink()
        raise OSError('interrupted cleanup')

    monkeypatch.setattr(archive.shutil, 'rmtree', partial_cleanup)
    with pytest.raises(OSError, match='interrupted cleanup'):
        archive.archive_role(**args)
    parked = args['stage'].with_name('role.archive-parked')
    assert parked.exists() and args['stage'].is_symlink()
    monkeypatch.setattr(archive.shutil, 'rmtree', remove)
    archive.archive_role(**args)
    assert not parked.exists()
    assert (args['stage'] / 'request.json').read_text() == 'absolute path binding'


def test_outside_paths_or_qnap_rejected(tmp_path):
    args = setup(tmp_path)
    args['destination'] = tmp_path / 'escaped'
    with pytest.raises(ValueError, match='owned roots'):
        archive.archive_role(**args)
    args['stage'] = Path('/mnt/qnap01/example')
    with pytest.raises(ValueError, match='QNAP'):
        archive.archive_role(**args)


def test_disk_and_memory_guards(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.shutil, 'disk_usage', lambda path: type('Disk', (), {'free': 2 * 1024 ** 3})())
    result = archive.resources_ready(tmp_path, stage_free_gib=3)
    assert not result['ready'] and result['stage_free_gib'] == 2


@pytest.mark.parametrize('escape', ['overlapping_roots', 'destination_in_stage', 'parent_traversal', 'receipt_in_stage'])
def test_unsafe_root_overlap_or_destructive_boundaries_rejected(tmp_path, escape):
    args = setup(tmp_path)
    if escape == 'overlapping_roots':
        args['archive_root'] = args['staging_root'] / 'archive'
        args['destination'] = args['archive_root'] / 'role'
    elif escape == 'destination_in_stage':
        args['archive_root'] = args['stage'] / 'archive'
        args['destination'] = args['archive_root'] / 'role'
    elif escape == 'parent_traversal':
        args['stage'] = args['staging_root'] / '..' / 'outside'
    else:
        args['receipt_path'] = args['stage'] / 'execution.json'
    with pytest.raises(ValueError):
        archive.archive_role(**args)
