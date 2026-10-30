"""Input identity and path confinement belong to the local position store."""

import pytest
import json

from leo.storage.fast_graph_position import FastGraphPositionStore
from leo.storage.fast_graph_position import sha


def test_public_input_updates_produce_new_job_ids(tmp_path):
    folder = tmp_path / "fast-scan-tracking-inputs"
    folder.mkdir()
    source = folder / "scan.json"
    source.write_text("first")
    store = FastGraphPositionStore(tmp_path)
    first = next(store.inputs())
    source.write_text("second")
    second = next(store.inputs())
    assert first["job_id"] != second["job_id"]
    with pytest.raises(ValueError):
        store.verify_input(first)
    with pytest.raises(ValueError):
        store.path("../escape")


def export_fixture(tmp_path, monkeypatch):
    (tmp_path / 'bulk').mkdir()
    store = FastGraphPositionStore(tmp_path / 'bulk')
    path = store.path('job') / 'output'
    source = path / 'inference/SCAN/tracking.json'
    source.parent.mkdir(parents=True)
    source.write_text('tracking')
    terminal = path / 'terminal.json'
    terminal.write_text('{}')
    job = dict(job_id='job', input_sha256=sha(source))
    monkeypatch.setattr(store, 'status', lambda _: dict(state='complete'))
    monkeypatch.setattr(store, 'terminal', lambda _: (
        dict(state='complete', session_id='scan'), dict(path=str(terminal), sha256=sha(terminal))))
    return store, job, source


def test_export_is_isolated_and_records_content_hashes(tmp_path, monkeypatch):
    store, job, source = export_fixture(tmp_path, monkeypatch)
    destination = tmp_path / 'snapshot'
    result = store.export_analysis(job, destination)
    copied = destination / 'inference/SCAN/tracking.json'
    assert copied.read_bytes() == source.read_bytes()
    assert result['files']['SCAN/tracking.json'] == sha(source)
    copied.write_text('downstream mutation')
    assert source.read_text() == 'tracking'
    assert json.loads((destination / 'descriptor.json').read_text()) == result
    with pytest.raises(FileExistsError):
        store.export_analysis(job, destination)
    with pytest.raises(ValueError, match='production namespace'):
        store.export_analysis(job, store.path('new'))


def test_export_rejects_symlinks_and_wrong_tracking_identity(tmp_path, monkeypatch):
    store, job, source = export_fixture(tmp_path, monkeypatch)
    link = source.parent / 'external.json'
    link.symlink_to(tmp_path / 'unrelated')
    with pytest.raises(ValueError, match='symbolic'):
        store.export_analysis(job, tmp_path / 'bad-link')
    link.unlink()
    job['input_sha256'] = 'sha256:changed'
    with pytest.raises(ValueError, match='tracking input'):
        store.export_analysis(job, tmp_path / 'bad-identity')
