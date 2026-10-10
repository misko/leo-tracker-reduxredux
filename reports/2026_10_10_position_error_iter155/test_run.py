"""Prepared fake-port driver and artifact guards; no recording calls."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

import run


def test_claim_before_work_and_no_orphan_retry(tmp_path):
    member = {'label': 'x'}
    calls = []
    def evaluate(m):
        assert (tmp_path/'x.claim.json').exists()
        calls.append(m)
        return dict(label='x',status='failed',arms={})
    assert run.run_member(member,tmp_path,'d',evaluate=evaluate)['status']=='failed'
    run.run_member(member,tmp_path,'d',evaluate=lambda m:pytest.fail('retry'))
    assert len(calls)==1
    with pytest.raises(ValueError): run.run_member(member,tmp_path,'foreign',evaluate=evaluate)
    (tmp_path/'x.json').unlink()
    with pytest.raises(FileExistsError): run.run_member(member,tmp_path,'d',evaluate=evaluate)


def member_fixture(tmp_path):
    path=tmp_path/'selected.json'
    path.write_text(json.dumps(dict(label='x',branch='native',protocol_sha256='old')))
    return dict(label='x',selected_path=str(path),selected_sha256=run.sha(path),
                selected_protocol_digest='old',binding={'expected_input_binding':{'input':'same'}})


def test_input_failure_preserves_both_arms_and_bad_receipt_blocks_loader(tmp_path):
    member=member_fixture(tmp_path)
    def fail(m): raise ValueError('loader failure')
    row=run.evaluate_member(member,dependency_factory=fail)
    assert row['status']=='failed' and set(row['arms'])=={'fitted-c','zero-c'}
    member['selected_sha256']='bad'
    row=run.evaluate_member(member,dependency_factory=lambda m:pytest.fail('loader opened'))
    assert 'changed' in row['error']


def test_each_arm_checked_separately_required_ports_forwarded(tmp_path,monkeypatch):
    member=member_fixture(tmp_path)
    monkeypatch.setattr(run,'fingerprint',lambda model:{'identity':'same'})
    calls=[]
    def reconstruct(case,receipt,arm,**kwargs):
        calls.append(('reconstruct',arm))
        if arm=='fitted-c': raise ValueError('unsupported state')
        return dict(model=object(),vector=np.zeros(8),clock=np.zeros(4),saved_objective=1.,
            saved_joint_objective=1.,feasible=lambda *a:True,anchor_audit=lambda *a:{'qualified':True},
            local_center=np.zeros(2),seed_stage='B5',helper_projection_delta=np.zeros(8))
    def check(model,vector,clock,**options):
        assert options['stored_joint_objective']==1.
        assert callable(options['anchor_audit']) and options['fingerprint']()=={'identity':'same'}
        calls.append(('check',options['arm']))
        return dict(status='passed',joint_attempts=6)
    ports=dict(loader=lambda binding:{},reconstruct=reconstruct,construct=None,components={},problem=None,
               check=check,conditional=None,evidence=lambda x:x.tolist())
    row=run.evaluate_member(member,dependency_factory=lambda m:ports)
    assert calls==[('reconstruct','fitted-c'),('reconstruct','zero-c'),('check','zero-c')]
    assert row['arms']['zero-c']['status']=='passed' and row['status']=='failed'
    assert row['matched_model'] is False


def test_fingerprint_detects_inference_mutation_but_ignores_private_cache():
    model=SimpleNamespace()
    for name in ('baseline','design','basis','clock_design','precision','nodes','null',
                 'rf_time_design','satellite_basis','centers_s','delta_time'):
        setattr(model,name,np.zeros(2))
    model.observations=SimpleNamespace(times_s=np.array([0.,1.]),time_center_s=.5)
    model.bank=SimpleNamespace(numbers=np.array([1,2]),position_km=np.zeros((2,2,3)))
    model.prior=None;model.score=None
    before=run.fingerprint(model)
    model._cache=123
    assert run.fingerprint(model)==before
    model.bank.position_km[0,0,0]=1
    assert run.fingerprint(model)!=before


def test_runtime_gate_precedes_any_inherited_import(monkeypatch):
    monkeypatch.setenv('OPENBLAS_NUM_THREADS','2')
    plan=dict(policy={},runtime={'interpreter':str(run.Path(run.sys.executable).absolute()),'sha256':{}},
              source_sha256={},input_sha256={},members=[])
    with pytest.raises(ValueError,match='single-thread'):run.verify(plan,{})
