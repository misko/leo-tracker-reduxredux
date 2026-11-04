import hashlib
import json

import pytest
from compare_algo07_star_links import execution_context


def write(path, value):
    path.write_text(json.dumps(value))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path):
    spec, manifest, reference, candidate = [tmp_path/n for n in
                                           ('runtime.json', 'frozen.json', 'ref.json', 'cand.json')]
    pin = write(spec, {'ALGO02': {'maximum_seconds': 1200}})
    frozen = write(manifest, {'files': [{'path': str(spec), 'sha256': pin}]})
    binding = dict(job_id='job', model_version='model', input_sha256='input',
                   path='/candidate/terminal.json', sha256='sha256:abc')
    common = dict(state='scientific_complete', runtime_manifest_sha256=frozen,
                  runtime_verification=dict(verified=True, failed=[]))
    write(reference, dict(common, stages=[dict(algorithm='ALGO02', executed=True, exit_code=0,
          command=['/python', '--maximum-seconds', '1200', '--bulk-root', '/reference'])]))
    write(candidate, dict(common, stages=[dict(algorithm='ALGO02')], incumbent=dict(
        job_id='job', model_version='model', input_sha256='input',
        terminal={k: binding[k] for k in ('path', 'sha256')})))
    return (spec, manifest, reference, candidate, ['ALGO02']), binding


def call(paths, binding):
    return execution_context(*paths, reference_store='/reference', candidate_binding=binding)


def test_runtime_and_execution_receipts_bind_original_budget(tmp_path):
    paths, binding = fixture(tmp_path)
    result = call(paths, binding)
    assert result['maximum_seconds'] == {'ALGO02': 1200}
    assert result['reference_checkpoint_stages'] == []


@pytest.mark.parametrize('change', ['budget', 'root', 'manifest', 'terminal', 'input', 'failed'])
def test_mismatched_execution_cannot_justify_accounting(tmp_path, change):
    paths, binding = fixture(tmp_path)
    reference, candidate = paths[2:4]
    if change in ('budget', 'root'):
        data = json.loads(reference.read_text())
        data['stages'][0]['command'][2 if change == 'budget' else 4] = 'other'
        write(reference, data)
    else:
        data = json.loads(candidate.read_text())
        if change == 'manifest':
            data['runtime_manifest_sha256'] = 'different'
        elif change == 'terminal':
            data['incumbent']['terminal']['sha256'] = 'different'
        elif change == 'input':
            data['incumbent']['input_sha256'] = 'different'
        else:
            data['runtime_verification']['failed'] = ['changed-worker.py']
        write(candidate, data)
    with pytest.raises(ValueError):
        call(paths, binding)


def test_modified_specification_is_rejected(tmp_path):
    paths, binding = fixture(tmp_path)
    write(paths[0], {'ALGO02': {'maximum_seconds': 1199}})
    with pytest.raises(ValueError, match='not bound'):
        call(paths, binding)
