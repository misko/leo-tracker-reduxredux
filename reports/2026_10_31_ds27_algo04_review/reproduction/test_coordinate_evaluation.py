"""Coordinator bookkeeping, pairing and public-port reuse; no scientific fits."""

import copy
from pathlib import Path

import pytest

import coordinate_evaluation as coordinator
import offline_algo04 as offline


def paired():
    case = dict(case='DS27-0002', input=dict(sha256='sha256:input', session_id='session'))
    baseline = dict(state='complete', terminal={'immutable_ALGO02': True})
    job = dict(job_id='job', input_sha256='sha256:input')
    terminal = dict(state='complete', input_sha256='sha256:input', session_id='session',
                    baseline=baseline['terminal'], read_audit={'verified': True},
                    decision='ALGO02_fallback', recovery_seconds=2.)
    return case, baseline, job, terminal


def test_fast_scope_keeps_all_fifteen_and_never_filters_scientific_failure():
    cases = [dict(case=f'DS27-{i:04d}', recording_format=(
        'short_window_iq_recording' if i <= 15 else 'starlink_adaptive_hop_iq'),
        input=None, failed=True) for i in range(1, 29)]
    original = copy.deepcopy(cases)
    assert len(coordinator.fast_cases({'cases': cases})) == 15
    assert cases == original


@pytest.mark.parametrize('change', ['baseline', 'input', 'session', 'historical_guard', 'state'])
def test_public_reuse_requires_exact_qualified_paired_source(change):
    case, baseline, job, terminal = paired()
    assert coordinator.paired_source(case, baseline, job, terminal)
    if change == 'baseline':
        terminal['baseline'] = {'different': True}
    elif change == 'input':
        job['input_sha256'] = 'sha256:other'
    elif change == 'session':
        terminal['session_id'] = 'other'
    elif change == 'historical_guard':
        terminal['read_audit']['verified'] = False
    else:
        baseline['state'] = 'failed'
    assert not coordinator.paired_source(case, baseline, job, terminal)


def test_public_recovery_reuse_relocates_hash_edges_and_preserves_terminal_bytes(tmp_path):
    case, baseline, job, terminal = paired()
    original = tmp_path / 'original/candidate-v2'
    offline.write(original / 'terminal.json', terminal)
    offline.write(original / 'recovery/snapshot/descriptor.json',
                  {'root': str(original / 'recovery/snapshot')})
    offline.write(original / 'recovery/proof.json', {'source_receipts': {
        str(original / 'recovery/snapshot/descriptor.json'):
            offline.digest(original / 'recovery/snapshot/descriptor.json')}})
    study = tmp_path / 'study'
    receipt = {'path': str(original / 'terminal.json'), 'sha256': offline.digest(original / 'terminal.json')}
    offline.write(study / 'completed-algo03-job-map.json', [{'job': job, 'terminal_receipt': receipt}])
    folder = study / 'cases' / case['case']
    folder.mkdir(parents=True)
    calls = []

    class PublicStore:
        def terminal(self, supplied):
            assert supplied == job
            calls.append('terminal')
            return copy.deepcopy(terminal), receipt

        def export_recovery(self, supplied, destination):
            assert supplied == job
            calls.append('export')
            return offline.export_recovery(original / 'terminal.json', original / 'recovery',
                                           destination, terminal)[0]

    before = offline.inventory(original)
    result = coordinator.reuse_candidate(case, study, baseline, store=PublicStore())
    assert result['reused_production'] and result['exact_paired_ALGO02'] and result['source_unchanged']
    assert calls == ['terminal', 'export', 'terminal']
    output = folder / 'candidate-v2'
    assert (output / 'terminal.json').read_bytes() == (original / 'terminal.json').read_bytes()
    proof = offline.read(output / 'recovery/proof.json')
    assert proof['source_receipts'] == {str(output / 'recovery/snapshot/descriptor.json'):
                                       offline.digest(output / 'recovery/snapshot/descriptor.json')}
    assert offline.inventory(original) == before


def test_protocol_detects_modified_source_and_rejects_more_than_twelve_workers(tmp_path):
    path = tmp_path / 'adapter.py'
    path.write_text('original')
    offline.write(tmp_path / 'evaluation-protocol.json', {'source_hashes': {str(path): offline.digest(path)}})
    coordinator.verify_protocol(tmp_path)
    path.write_text('changed')
    with pytest.raises(ValueError, match='dependency changed'):
        coordinator.verify_protocol(tmp_path)
    with pytest.raises(ValueError, match='1..12'):
        coordinator.batch(tmp_path, 13)
