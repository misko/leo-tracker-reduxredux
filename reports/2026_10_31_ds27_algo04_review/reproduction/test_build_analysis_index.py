"""Index sealing preserves independent method coverage and the exact native IDs."""

import pytest

import build_analysis_index as builder
from offline_algo04 import digest, read, write


def fixture(tmp_path, *, state='complete'):
    manifest = tmp_path / 'dataset/manifest.json'
    write(manifest, {'members': ['recording']})
    write(tmp_path / 'datasets/DS27.json', dict(manifest_path=str(manifest), manifest_sha256=digest(manifest),
        cases=[dict(case='DS27-0001', recording_id='recording', input={'sha256': 'sha256:input'},
                    recording_format='short_window_iq_recording')]))
    root = tmp_path / 'cases/DS27-0001'
    write(root / 'pipeline-receipt.json', {'state': state})
    write(root / 'baseline-receipt.json', dict(state='complete', terminal={'model_version': 'ALGO02'}))
    write(root / 'candidate-receipt.json', {'state': 'complete'})
    write(root / 'candidate-v2/terminal.json', {'model_version': 'ALGO03'})
    write(root / 'candidate-v3/receipt.json', {'state': state, 'reason': 'numerical_failed'})
    if state == 'complete':
        write(root / 'candidate-v3/terminal.json', {'decision': 'ALGO03_fallback'})
        write(root / 'candidate-v3/inference-seal.json', {'output_hashes': {
            str(root / 'candidate-v3/terminal.json'): digest(root / 'candidate-v3/terminal.json')}})
        write(root / 'candidate-v2/recovery/snapshot/inference/SCAN/tracks.json', [])
        write(root / 'candidate-v2/recovery/snapshot/inference/SCAN/observations.json', [])
        write(root / 'candidate-v2/recovery/all-large-track-recovery/job/inventory.json', {
            'job': {'identities': ['actual-scan-identity', 'alias']}})
    return root


def test_complete_index_uses_inventory_identity_basis_and_binds_exact_roster(tmp_path):
    fixture(tmp_path)
    calls = []
    result = builder.build(tmp_path, validate_v3=lambda doc, **kw: calls.append(kw))
    assert result['complete'] == result['cases'] == 1
    row = read(tmp_path / 'analysis-index.json')['cases'][0]
    assert row['identities'] == ['actual-scan-identity', 'alias']
    assert row['input_sha256'] == 'sha256:input'
    assert calls == [{'input_sha256': 'sha256:input'}]
    assert row['baseline_terminal_sha256'] == digest(row['baseline_terminal_path'])
    assert row['candidate_terminal_sha256'] == digest(row['candidate_terminal_path'])
    seal = read(tmp_path / 'analysis-seal.json')
    assert seal['analysis_index_sha256'] == digest(tmp_path / 'analysis-index.json')
    assert seal['dataset_execution_manifest_sha256'] == digest(tmp_path / 'datasets/DS27.json')
    assert seal['dataset_manifest_sha256'] == digest(tmp_path / 'dataset/manifest.json')
    assert seal['fast_cases'] == ['DS27-0001']


def test_failed_numerical_case_retains_available_comparators(tmp_path):
    fixture(tmp_path, state='failed')
    result = builder.build(tmp_path, validate_v3=lambda *a, **k: None)
    row = read(tmp_path / 'analysis-index.json')['cases'][0]
    assert result['failed'] == 1 and row['state'] == 'failed'
    assert row['method_states'] == {'ALGO02': 'complete', 'ALGO03': 'complete', 'ALGO04': 'failed'}
    assert row['reason'] == 'numerical_failed'
    assert row['baseline_terminal_path'] and row['candidate_terminal_path']


def test_index_refuses_unfinished_case(tmp_path):
    root = fixture(tmp_path)
    (root / 'pipeline-receipt.json').unlink()
    with pytest.raises(ValueError, match='unfinished'):
        builder.build(tmp_path, validate_v3=lambda *a, **k: None)


def test_index_refuses_terminal_changed_after_inference_seal(tmp_path):
    root = fixture(tmp_path)
    (root / 'candidate-v3/terminal.json').write_text('{"decision":"changed"}')
    with pytest.raises(ValueError, match='inference seal'):
        builder.build(tmp_path, validate_v3=lambda *a, **k: None)


def test_failed_baseline_preserves_underlying_phase_gate_and_wrapper_error(tmp_path):
    root = fixture(tmp_path, state='unavailable')
    baseline = root / 'baseline-receipt.json'
    baseline.write_text('{"state":"failed","terminal":{"state":"failed","reason":"missing output"}}')
    (root / 'algo02').mkdir()
    (root / 'algo02/family.log').write_text('ValueError: family-excluded calibration phase did not converge\n')
    builder.build(tmp_path, validate_v3=lambda *a, **k: None)
    row = read(tmp_path / 'analysis-index.json')['cases'][0]
    assert row['method_states']['ALGO02'] == 'failed'
    assert 'phase did not converge' in row['reason']
    assert row['wrapper_failure'] == 'missing output'
    assert row['underlying_baseline_gate']['maximum_phase_change_s'] == .01
