import json
from types import SimpleNamespace

import pytest

from leo.storage.fast_graph_position import sha
from leo.storage.fast_graph_worker_evidence import export_worker_evidence


def fixture(tmp_path):
    root = tmp_path/'private-store'
    output = root/'owned-output'
    output.mkdir(parents=True)
    terminal = output/'terminal.json'
    terminal.write_text(json.dumps(dict(state='complete')))
    evidence = output/'intermediate.json'
    evidence.write_text(json.dumps(dict(owners=dict(point=123), gate=False)))
    store = SimpleNamespace(root=root, terminal=lambda _: (
        json.loads(terminal.read_text()), dict(path=str(terminal), sha256=sha(terminal))))
    job = dict(input_sha256='sha256:input', model_version='model', job_id='job')
    return store, job, output


def test_snapshot_keeps_every_worker_file_and_original_bytes(tmp_path):
    store, job, output = fixture(tmp_path)
    target = tmp_path/'export'
    descriptor = export_worker_evidence(store, job, target)
    assert set(descriptor['files']) == {'worker/terminal.json', 'worker/intermediate.json'}
    for name, digest in descriptor['files'].items():
        assert sha(target/name) == digest
    assert ((target/'worker/intermediate.json').read_bytes() ==
            (output/'intermediate.json').read_bytes())


def test_export_cannot_write_source_or_qnap(tmp_path):
    store, job, _ = fixture(tmp_path)
    for target in (store.root, store.root/'copy', tmp_path, '/mnt/qnap01/no'):
        with pytest.raises(ValueError, match='separate from the source'):
            export_worker_evidence(store, job, target)


def test_symbolic_links_are_rejected(tmp_path):
    store, job, output = fixture(tmp_path)
    (output/'alias.json').symlink_to(output/'terminal.json')
    with pytest.raises(ValueError, match='symbolic links'):
        export_worker_evidence(store, job, tmp_path/'export')
