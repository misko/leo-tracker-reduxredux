import copy
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

import run_candidate as runner


def fit(score=80.):
    return dict(x=[0.,0.],error_m=999.,objective=score,rms_hz=12.,qualified=True,all_gates_pass=True,
                phase_closed=True,optimizer_success=True,mixture_phase_interior=True,lost_ids=[],
                unexpected_reassigned_ids=[],native_ids_sha256='same',status='complete')


def test_requires_paired_qualified_controls_and_positive_penalized_gain():
    h=dict(name='replacement',penalty=2.)
    pair={a:fit() for a in runner.e.ARMS};control={a:fit(100.) for a in runner.e.ARMS}
    assert runner.score_record(h,pair,control,dict(c0=100.,fitted_c=100.))['accepted']
    control['c0']=None
    record=runner.score_record(h,pair,control,{})
    assert not record['accepted'] and record['gains']=={}
    control['c0']=fit(100.)
    assert not runner.score_record(h,pair,control,dict(c0=81.,fitted_c=100.))['accepted']


def test_destination_collision_in_either_arm_and_exact_fallback():
    z=dict(baseline_owners=dict(c0={'a':10},fitted_c={'a':20}))
    assert runner.destination_owned(z,20)
    assert not runner.destination_owned(z,30)
    baseline={a:dict(x=[0.,1.],error_m=900.,objective=123.,associated=1,rms_hz=None) for a in runner.e.ARMS}
    result=runner.fallback(baseline,'compute_fallback')
    assert result['final']==baseline
    result['final']['c0']['x'][0]=10.
    assert baseline['c0']['x']==[0.,1.]


def test_public_preflight_checks_full_owner_map_and_geographic_endpoint(monkeypatch):
    monkeypatch.setattr(runner,'latlon',lambda x:x)
    owners={a:{'obs':10} for a in runner.e.ARMS}
    monkeypatch.setattr(runner,'public_owners',lambda terminal:owners)
    d=dict(problems={'fitted_c':(None,np.array([1.,2.]))})
    z=dict(baseline_owners=copy.deepcopy(owners));base={a:dict(associated=1) for a in runner.e.ARMS}
    terminal=dict(position=dict(latitude_deg=1.,longitude_deg=2.))
    assert runner.preflight_public(d,z,base,terminal)['public_owner_maps_equal']
    z['baseline_owners']['c0']['obs']=20
    with pytest.raises(ValueError,match='owner contract'):runner.preflight_public(d,z,base,terminal)
    terminal['position']['latitude_deg']=1.00001
    with pytest.raises(ValueError,match='latitude/longitude'):runner.preflight_public(d,z,base,terminal)


def worker_context(monkeypatch,tmp_path,guard_pass):
    baseline={a:dict(x=[0.,0.],error_m=900.,objective=100.,associated=1,rms_hz=None) for a in runner.e.ARMS}
    monkeypatch.setattr(runner,'verify_frozen',lambda *args:dict(baselines={'TEST-0001':baseline}))
    monkeypatch.setattr(runner,'configure',lambda *args:None)
    monkeypatch.setattr(runner,'sha',lambda *args:'hash')
    d=dict(problems={a:(None,np.zeros(2)) for a in runner.e.ARMS})
    z=dict(baseline_owners={a:{'obs':10} for a in runner.e.ARMS},scan_receipt={'origin_utc_ns':0})
    monkeypatch.setattr(runner.e,'load_case',lambda case:(d,z,{}))
    monkeypatch.setattr(runner.e,'objective',lambda *args:100.)
    monkeypatch.setattr(runner,'preflight_public',lambda *args:{'public_owner_maps_equal':True})
    monkeypatch.setattr(runner,'read',lambda path:{})
    monkeypatch.setattr(runner.e.rec,'causal_records',lambda *args:{'10':{},'20':{}})
    monkeypatch.setattr(runner.e,'rank_families',lambda *args:([],[10]))
    monkeypatch.setattr(runner.e.rec,'bank_for',lambda *args:([10,20],dict(position_km=np.zeros((2,2,3)),velocity_km_s=np.zeros((2,2,3))),[]))
    monkeypatch.setattr(runner,'audit_catalogue',lambda *args:dict(failures=[],nominal_causality_verified=True,partial_or_unknown_blocks=[]))
    h=dict(name='10_to_20',norad=20,mapping={'track':20},allowed_families=[10,20],penalty=2.,
           predictive={a:dict(pass_check=True) for a in runner.e.ARMS})
    screen=dict(proposals=[h],cavity={'fitted_c':{'x':[1.,1.]}})
    monkeypatch.setattr(runner.e.rec,'screen',lambda *args:screen)
    monkeypatch.setattr(runner,'receiver_shared_check',lambda *args:{'new':20})
    guard=dict(passed=guard_pass,model='receiver_offset',unique_folds=5,missing=[],minimum_margin=1.)
    monkeypatch.setattr(runner,'from_additional_checks',lambda *args:guard)
    return baseline,d,z


def test_no_history_read_or_joint_refit_when_predictive_guard_rejects(monkeypatch,tmp_path):
    baseline,_,_=worker_context(monkeypatch,tmp_path,False)
    def forbidden(*args,**kwargs):raise AssertionError('history/refit before guard admission')
    monkeypatch.setattr(runner.e,'complete_history',forbidden)
    monkeypatch.setattr(runner.e,'fit_rows',forbidden)
    result=runner.run_worker('TEST-0001',tmp_path/'inputs',tmp_path/'outputs')
    assert result['selected'] is None and result['final']==baseline
    assert result['history'] is None


def test_full_bank_propagation_failure_forces_exact_fallback(monkeypatch,tmp_path):
    baseline,_,_=worker_context(monkeypatch,tmp_path,True)
    monkeypatch.setattr(runner.e.rec,'bank_for',lambda *args:([10],None,[20]))
    def forbidden(*args,**kwargs):raise AssertionError('incomplete bank must not be ranked')
    monkeypatch.setattr(runner.e.rec,'screen',forbidden)
    result=runner.run_worker('TEST-0001',tmp_path/'inputs',tmp_path/'outputs')
    assert result['execution_status']=='propagation_fallback'
    assert result['final']==baseline and result['selected'] is None


def test_single_combined_path_uses_matched_starts_and_never_history_only(monkeypatch,tmp_path):
    baseline,d,z=worker_context(monkeypatch,tmp_path,True)
    requests=[]
    monkeypatch.setattr(runner.e,'active_ids',lambda *args:{10})
    monkeypatch.setattr(runner.e,'complete_history',lambda context,z,case,identities,path:
                        (requests.append(set(identities)) or context,dict(changed=True)))
    monkeypatch.setattr(runner.e,'remap',lambda context,*args:context)
    def fit_rows(context,z,starts,allowed,path):
        assert list(starts)==['published','family_omitted']
        assert np.array_equal(starts['published'],[0.,0.])
        assert np.array_equal(starts['family_omitted'],[1.,1.])
        return [dict(fit(80. if allowed else 100.),arm=a,start=s) for a in runner.e.ARMS for s in starts]
    monkeypatch.setattr(runner.e,'fit_rows',fit_rows)
    result=runner.run_worker('TEST-0001',tmp_path/'inputs',tmp_path/'outputs')
    assert result['selected']=='10_to_20'
    assert requests==[{10},{20}]
    assert result['records'][0]['gains']=={'c0':18.,'fitted_c':18.}
    assert result['final']['c0']['associated']==baseline['c0']['associated']


def test_supervisor_hardcap_ignores_partial_winner_and_keeps_exact_baseline(monkeypatch,tmp_path):
    baseline={a:dict(x=[0.,0.],objective=100.,error_m=900.,associated=1,rms_hz=None) for a in runner.e.ARMS}
    monkeypatch.setattr(runner,'verify_frozen',lambda *args:dict(baselines={'TEST-0001':baseline}))
    monkeypatch.setattr(runner,'sha',lambda *args:'hash')
    class TimedOut:
        pid=12345
        def wait(self,timeout):raise subprocess.TimeoutExpired('worker',timeout)
    monkeypatch.setattr(runner.subprocess,'Popen',lambda *args,**kwargs:TimedOut())
    killed=[]
    monkeypatch.setattr(runner,'terminate_group',lambda process:killed.append(process.pid))
    folder=tmp_path/'output/TEST-0001';folder.mkdir(parents=True)
    runner.write(folder/'worker_result.json',dict(selected='partial_winner'))
    result=runner.supervise('TEST-0001',tmp_path/'inputs',tmp_path/'output')
    assert result['execution_status']=='compute_fallback'
    assert result['selected'] is None and result['final']==baseline and killed==[12345]
    assert result['limit_s']==1200


def test_any_incomplete_start_forces_fallback_while_complete_rejection_is_normal(monkeypatch,tmp_path):
    baseline,_,_=worker_context(monkeypatch,tmp_path,True)
    monkeypatch.setattr(runner.e,'active_ids',lambda *args:{10})
    monkeypatch.setattr(runner.e,'complete_history',lambda context,*args:(context,dict(changed=False)))
    rows=[dict(fit(100.),arm=a,start=s) for a in runner.e.ARMS for s in ('published','family_omitted')]
    assert runner.fit_rows_complete(rows)
    rows[0]['qualified']=False
    assert runner.fit_rows_complete(rows)
    rows[0]['status']='incomplete'
    monkeypatch.setattr(runner.e,'fit_rows',lambda *args:rows)
    result=runner.run_worker('TEST-0001',tmp_path/'inputs',tmp_path/'outputs')
    assert result['execution_status']=='incomplete_fit_fallback'
    assert result['selected'] is None and result['final']==baseline


def test_output_root_safety_runs_before_freeze_or_supervisor_writes(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'OUT',tmp_path)
    root=tmp_path/'fresh'
    with pytest.raises(ValueError,match='overwrite'):
        runner.freeze(root,root)
    with pytest.raises(ValueError,match='overwrite'):
        runner.supervise('FRSH-0001',root,root)
    assert not root.exists()


def test_only_explicit_all_grid_invalid_catalogue_exclusions_are_permitted():
    receipt=dict(nominal_causality_verified=True,partial_or_unknown_blocks=[],
                 failures=[dict(norad=20,classification='exclude_consistent_model_invalid_all_grid')])
    assert runner.propagation_eligible(receipt,[20])
    assert not runner.propagation_eligible(receipt,[20,30])
    receipt['failures'][0]['classification']='block_partial_grid_failure'
    assert not runner.propagation_eligible(receipt,[20])
