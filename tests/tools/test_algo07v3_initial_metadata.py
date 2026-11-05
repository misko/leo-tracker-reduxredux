"""Excluded bookkeeping must retain its actual input and source meaning."""

import hashlib
import json

import pytest
from check_algo07v3_initial_metadata import audit


@pytest.fixture
def evidence(tmp_path):
    root, runtime = tmp_path / 'evidence', tmp_path / 'runtime'
    folder = root / 'ALGO02'
    folder.mkdir(parents=True)
    (runtime / 'tools').mkdir(parents=True)
    descriptor = dict(source_worker_root='/original/worker', files={})
    files = []

    def put(name, value):
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        descriptor['files'][name] = 'sha256:' + digest
        (folder / 'descriptor.json').write_text(json.dumps(descriptor))
        return digest

    sources = {}
    for name in ('evaluate_ds23_phase_refreshed.py', 'run_algo01_ds23_sample.py', 'algo02_scan.py'):
        path = runtime / 'tools' / name
        path.write_text('# frozen ' + name)
        sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(dict(path=str(path), sha256=sources[name]))
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps(dict(files=files)))
    initial = dict(case='SCAN', seconds=1.25, noise_mode='radio',
                   source_sha256=sources['evaluate_ds23_phase_refreshed.py'],
                   physical_prior_previous_tle_path='/original/worker/inference/SCAN/previous.tle')
    initial['input_read_paths'] = []
    for name in ('bank.npz', 'nominal_elements.json', 'previous.tle', 'radio_noise.json',
                 'receipt.json', 'tracking.json', 'tracks.json'):
        digest = put('worker/inference/SCAN/' + name, dict(name=name))
        initial['input_read_paths'].append('/original/worker/inference/SCAN/' + name)
        if name == 'radio_noise.json':
            initial['noise_features_sha256'] = digest
    recovery = dict(case='SCAN', seconds=2., algorithm='ALGO01 batch composition',
                    source_sha256=sources['run_algo01_ds23_sample.py'])
    baseline = put('worker/inference/SCAN/result.json', recovery)
    history = put('worker/inference/causal_phase_history/SCAN.json', {'history': 1})
    forecast = put('worker/inference/causal_phase_history/SCAN_forecast.json', {'forecast': 1})
    family = dict(case='SCAN', seconds=3., algorithm='ALGO02-v1', baseline_sha256=baseline,
                  engine_sha256=sources['algo02_scan.py'], history_sha256=history,
                  history_forecast_sha256=forecast)
    nomination = put('worker/inference/family_cavity/SCAN_nominations.json', dict(seconds=4.))
    put('worker/inference/family_cavity/position/SCAN.json',
        dict(seconds=5., nomination_sha256=nomination))
    put('worker/inference/SCAN/fit_radio_noise.json', initial)
    put('worker/inference/SCAN/algo02_result.json', family)
    return root, runtime, manifest, put


def test_all_initial_exclusions_are_independently_qualified(evidence):
    result = audit(*evidence[:3])
    assert result['initial_metadata_links_verified']
    assert len(result['policies']) == 5
    assert sum(map(len, result['policies'].values())) == 21
    assert not result['full_intermediate_equivalence']


@pytest.mark.parametrize('field,value', [
    ('case', 'ANOTHER_SCAN'), ('noise_mode', 'estimated'),
    ('seconds', -1.), ('seconds', float('nan')), ('seconds', float('inf')), ('seconds', True),
    ('source_sha256', '0' * 64), ('noise_features_sha256', '1' * 64),
    ('physical_prior_previous_tle_path', '/original/worker/inference/SCAN/bank.npz'),
    ('physical_prior_previous_tle_path', '/unrelated/worker/previous.tle'),
    ('input_read_paths', []),
    ('input_read_paths', ['/original/worker/inference/SCAN/previous.tle'] * 7),
])
def test_rebound_export_cannot_hide_invalid_metadata(evidence, field, value):
    root, runtime, manifest, put = evidence
    name = 'worker/inference/SCAN/fit_radio_noise.json'
    initial = json.loads((root / 'ALGO02' / name).read_bytes())
    initial[field] = value
    put(name, initial)
    with pytest.raises(ValueError):
        audit(root, runtime, manifest)


@pytest.mark.parametrize('field', ['baseline_sha256', 'history_sha256',
                                  'history_forecast_sha256', 'engine_sha256'])
def test_family_binding_cannot_point_to_different_evidence(evidence, field):
    root, runtime, manifest, put = evidence
    name = 'worker/inference/SCAN/algo02_result.json'
    value = json.loads((root / 'ALGO02' / name).read_bytes())
    value[field] = '0' * 64
    put(name, value)
    with pytest.raises(ValueError):
        audit(root, runtime, manifest)


def test_changed_numerical_source_fails_even_when_document_is_unchanged(evidence):
    root, runtime, manifest, _ = evidence
    (runtime / 'tools/algo02_scan.py').write_text('# changed source')
    with pytest.raises(ValueError, match='source bytes'):
        audit(root, runtime, manifest)


def test_changed_cavity_nomination_link_fails(evidence):
    root, runtime, manifest, put = evidence
    put('worker/inference/family_cavity/position/SCAN.json',
        dict(seconds=5., nomination_sha256='0' * 64))
    with pytest.raises(ValueError):
        audit(root, runtime, manifest)
