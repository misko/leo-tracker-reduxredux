import hashlib
import json

import pytest
from compare_algo07_star_receipts import compare


def export(root, *, pid=100, read='observations.json', binding='native-evidence'):
    stage = root/'ALGO02'
    folder = stage/'worker'/'read_receipts'
    folder.mkdir(parents=True)
    relative = f'worker/read_receipts/{pid}.json'
    path = stage/relative
    path.write_text(json.dumps(dict(pid=pid, parent_pid=pid-1, python_spawns=[],
                                   read_paths=[str(root/read)], denied_paths=[])))
    descriptor = dict(kind='fast-graph-worker-evidence', model_version='test',
                      job_id='test-job', input_sha256=binding,
                      source_worker_root=str(root/'outputs'), source_store_root=str(root),
                      files={relative: 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()})
    (stage/'descriptor.json').write_text(json.dumps(descriptor))
    return path


@pytest.fixture(autouse=True)
def one_stage(monkeypatch):
    monkeypatch.setattr('compare_algo07_star_receipts.ALGORITHMS', ('ALGO02',))


def test_equal_provenance_does_not_claim_science_or_artifact_parity(tmp_path):
    export(tmp_path/'a')
    export(tmp_path/'b', pid=200)
    result = compare(tmp_path/'a', tmp_path/'b')
    assert result['process_provenance_equal']
    assert not result['scientific_parity_qualified']
    assert not result['artifact_parity_qualified']


def test_changed_read_is_reported_as_unequal(tmp_path):
    export(tmp_path/'a')
    export(tmp_path/'b', pid=200, read='other-observations.json')
    result = compare(tmp_path/'a', tmp_path/'b')
    assert not result['process_provenance_equal']
    assert not result['groups'][0]['equal']


def test_changed_export_bytes_are_rejected_before_normalization(tmp_path):
    path = export(tmp_path/'a')
    export(tmp_path/'b', pid=200)
    path.write_text(path.read_text()+'\n')
    with pytest.raises(ValueError, match='Export changed'):
        compare(tmp_path/'a', tmp_path/'b')


def test_different_input_binding_is_rejected(tmp_path):
    export(tmp_path/'a')
    export(tmp_path/'b', pid=200, binding='other-input')
    with pytest.raises(ValueError, match='input binding'):
        compare(tmp_path/'a', tmp_path/'b')
