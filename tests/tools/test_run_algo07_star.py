from pathlib import Path
from types import SimpleNamespace

import pytest
from run_algo07_star import verify_coverage


def fixture(tmp_path, monkeypatch):
    runtime = tmp_path/'runtime'
    (runtime/'src').mkdir(parents=True)
    source = runtime/'src/worker.py'
    source.write_text('pass')
    interpreter = tmp_path/'python'
    interpreter.write_text('fixture only')
    tle = tmp_path/'catalogue.tle'
    tle.write_text('fixture only')
    monkeypatch.setattr('leo.operations.tle_archive.TleArchiveReader.list_snapshots',
                        lambda _: [SimpleNamespace(path=tle)])
    spec = dict(ALGO02=dict(runtime=str(runtime), python=str(interpreter)))
    manifest = dict(files=[dict(path=str(p)) for p in (source, interpreter, tle)],
                    metadata=dict(tle_snapshot_paths=[str(tle)]))
    return spec, manifest


def test_source_additions_require_a_new_pin(tmp_path, monkeypatch):
    spec, manifest = fixture(tmp_path, monkeypatch)
    verify_coverage(spec, manifest)
    (Path(spec['ALGO02']['runtime'])/'src/new.py').write_text('pass')
    with pytest.raises(ValueError, match='Complete worker'):
        verify_coverage(spec, manifest)


def test_archive_additions_are_not_silently_shared(tmp_path, monkeypatch):
    spec, manifest = fixture(tmp_path, monkeypatch)
    manifest['metadata']['tle_snapshot_paths'].append('/another.tle')
    with pytest.raises(ValueError, match='archive membership changed'):
        verify_coverage(spec, manifest)


def test_archive_inventory_without_byte_pin_is_insufficient(tmp_path, monkeypatch):
    spec, manifest = fixture(tmp_path, monkeypatch)
    manifest['files'].pop()
    with pytest.raises(ValueError, match='bytes must be frozen'):
        verify_coverage(spec, manifest)
