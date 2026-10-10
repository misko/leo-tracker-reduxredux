"""Synthetic193 receipt gate: no reference documents or recording inputs."""
import json
from pathlib import Path
import pytest
import evaluation


def corpus(tmp_path):
    datasets = ['DS16']*63+['DS17']*51+['DS18']*34+['POST18-development']*45
    members = [dict(label=f'L{i}', dataset=datasets[i],membership=dict(session_id=f'S{i}')) for i in range(193)]
    labels = [m['label'] for m in members]
    batches = [labels[:4]]+[labels[i:i+16] for i in range(4,193,16)]
    plan = dict(members=members, execution_batches=batches)
    def write(path, row):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(row))
    for label in labels:
        for phase in evaluation.PHASES:
            row = dict(protocol_sha256='d', label=label, status='failed', fallback_available=False)
            if phase != 'search': row['branch'] = phase
            write(tmp_path/label/phase/'result.json', row)
    for i, batch in enumerate(batches):
        for shard in (0,1):
            identity = dict(protocol_sha256='d', batch=i, shard=shard)
            stem = f'batch-{i}-shard-{shard}'
            write(tmp_path/(stem+'.claim.json'), identity)
            write(tmp_path/(stem+'.json'), dict(identity, status='terminal', members=[
                dict(label=l, phases={p:'failed' for p in evaluation.PHASES}) for l in batch[shard::2]]))
    return plan


def test_all_scientific_failures_are_terminal_not_excluded(tmp_path):
    plan=corpus(tmp_path)
    hashes=evaluation.authenticate(plan,tmp_path,'d')
    assert len(hashes)==579+4*len(plan['execution_batches'])


def test_one_missing_phase_blocks_gate(tmp_path):
    plan=corpus(tmp_path)
    (tmp_path/'L192'/'zero'/'result.json').unlink()
    with pytest.raises(FileNotFoundError):evaluation.authenticate(plan,tmp_path,'d')


@pytest.mark.parametrize('change', ['foreign', 'claim', 'coverage', 'status'])
def test_tampered_checkpoint_blocks_gate(tmp_path,change):
    plan=corpus(tmp_path)
    path=tmp_path/'batch-0-shard-0.json'
    row=json.loads(path.read_text())
    if change=='foreign': row['protocol_sha256']='other'
    if change=='claim': (tmp_path/'batch-0-shard-0.claim.json').unlink()
    if change=='coverage': row['members']=row['members'][:1]
    if change=='status': row['members'][0]['phases']['zero']='complete'
    path.write_text(json.dumps(row))
    with pytest.raises((ValueError, FileNotFoundError)):evaluation.authenticate(plan,tmp_path,'d')


def test_partial_stage_foreign_identity_blocks_gate(tmp_path):
    plan=corpus(tmp_path)
    path=tmp_path/'L0'/'native'/'stages'/'partial.json'
    path.parent.mkdir();path.write_text(json.dumps(dict(protocol_sha256='foreign')))
    with pytest.raises(ValueError):evaluation.authenticate(plan,tmp_path,'d')


def test_orphan_slice_blocks_even_if_phase_claims_terminal_failure(tmp_path):
    plan=corpus(tmp_path)
    path=tmp_path/'L0'/'search'/'slices'/'01.started.json'
    path.parent.mkdir();path.write_text(json.dumps(dict(protocol_sha256='d')))
    with pytest.raises(ValueError,match='orphan'):
        evaluation.authenticate(plan,tmp_path,'d')


def test_inherited_summary_requires193_and_has_zero_branch():
    api=evaluation.reporter()
    assert api['BRANCHES']==('native','zero')
    row=dict(phases={p:dict(status='failed') for p in evaluation.PHASES})
    assert not api['sealed']([row]*12)
    assert not api['sealed']([row]*192)
    assert api['sealed']([row]*193)


def test_reference_factory_unreachable_with_one_missing_phase(tmp_path,monkeypatch):
    plan=corpus(tmp_path/'results')
    plan.update(source_sha256={},input_sha256={},evaluation_source_sha256={})
    (tmp_path/'protocol.json').write_text(json.dumps(plan))
    (tmp_path/'evaluation_protocol.json').write_text(json.dumps(dict(
        numerical_protocol_digest='d',numerical_protocol_sha256=evaluation.sha(tmp_path/'protocol.json'),
        source_sha256={})))
    monkeypatch.setattr(evaluation,'HERE',tmp_path)
    (tmp_path/'results'/'L192'/'zero'/'result.json').unlink()
    called=[]
    def factory(*args):
        called.append(True)
        raise AssertionError('Reference access before seal')
    with pytest.raises(FileNotFoundError):
        evaluation.build(plan,tmp_path/'results','d',evaluation_factory=factory)
    assert called==[]


def test_evaluation_failure_keeps_selected_endpoint_and_full_membership(tmp_path,monkeypatch):
    plan=corpus(tmp_path/'results')
    plan.update(source_sha256={},input_sha256={},evaluation_source_sha256={})
    (tmp_path/'protocol.json').write_text(json.dumps(plan))
    (tmp_path/'evaluation_protocol.json').write_text(json.dumps(dict(
        numerical_protocol_digest='d',numerical_protocol_sha256=evaluation.sha(tmp_path/'protocol.json'),
        source_sha256={})))
    monkeypatch.setattr(evaluation,'HERE',tmp_path)
    path=tmp_path/'results'/'L0'/'native'/'result.json'
    row=json.loads(path.read_text())
    row['operational']={'fitted-c':dict(fit=dict(converged=True,objective=1.,posterior_rms_hz=2.))}
    path.write_text(json.dumps(row))
    def factory(*args):
        def unavailable(*args):raise ValueError('reference missing')
        return unavailable
    summary=evaluation.build(plan,tmp_path/'results','d',evaluation_factory=factory)
    assert len(summary['rows'])==193 and summary['all_terminal']
    endpoint=summary['rows'][0]['arms']['fitted-c']['native']
    assert endpoint['status']=='selected' and endpoint['qualified']
    assert endpoint['evaluation_status']=='failed' and 'reference missing' in endpoint['evaluation_error']
    assert 'error_km' not in endpoint
