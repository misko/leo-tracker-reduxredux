import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from run_algo07_star import verify_coverage, worker_environment


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


def test_qualified_runtime_needs_its_explicit_production_environment_pin(tmp_path):
    manifest = tmp_path/'runtime-manifest.json'
    manifest.write_bytes(b'fixture manifest')
    spec = dict(runtime=str(tmp_path))
    with pytest.raises(ValueError, match='Explicit deployment runtime pin'):
        worker_environment(spec, 'ALGO03')
    pin = hashlib.sha256(manifest.read_bytes()).hexdigest()
    spec['environment'] = dict(LEO_ALGO03_RUNTIME_MANIFEST_SHA256=pin)
    assert worker_environment(spec, 'ALGO03') == ['LEO_ALGO03_RUNTIME_MANIFEST_SHA256='+pin]


def test_environment_cannot_replace_arbitrary_worker_configuration(tmp_path):
    with pytest.raises(ValueError, match='Unexpected worker environment'):
        worker_environment(dict(runtime=str(tmp_path), environment=dict(PYTHONPATH='/other')),
                           'ALGO03')
