from types import SimpleNamespace
import numpy as np
import pytest
import export_endpoints_v2 as export

def test_saved_context_does_not_qualify_or_refit(monkeypatch,tmp_path):
    case='test';model=dict(shrinkage=.5,multiplier=2.,nu=4.)
    export.write(tmp_path/'family_cavity/position'/(case+'.json'),dict(status='complete',accepted=False,selected=None,baseline_node={},original_mask=[True],powers=[1.],model=model,baseline_means=[0.],baseline_entries=[],policy_arms={}))
    export.write(tmp_path/case/'observations.json',[])
    export.write(tmp_path/'causal_phase_history'/(case+'.json'),dict(case=case))
    export.write(tmp_path/'causal_phase_history'/(case+'_forecast.json'),dict(transitions=[]))
    monkeypatch.setattr(export.algo,'bind_run_directory',lambda root:None)
    monkeypatch.setattr(export.algo,'load_scan',lambda root,c:SimpleNamespace(elements={'x':dict(provenance=dict(element_epoch_utc_ns=8,collected_utc_ns=7))},receipt=dict(cutoff_utc_ns=10)))
    monkeypatch.setattr(export.algo,'validate_history',lambda *a:(model,True))
    with export.forbid_refits() as calls:
        d=export.context_from_saved(tmp_path,case)
    assert calls==[] and d['model']==model
    assert d['means'].tolist()==[0.]

def test_guard_rejects_a_prior_refit(monkeypatch):
    original=export.recovery.context
    with export.forbid_refits() as calls:
        with pytest.raises(RuntimeError,match='forbidden refit'):export.recovery.context('unused')
    assert len(calls)==1 and export.recovery.context is original

@pytest.mark.parametrize('role',['curved','predictive'])
def test_native_alias_includes_graph_lift_in_both_roles(monkeypatch,role):
    track=dict(observation_ids=['native'],values=[100.+2*export.PERIOD])
    scan=SimpleNamespace(tracks=[track],norads=np.asarray([123]))
    p=SimpleNamespace(scan=scan,rows=[dict(candidate_index=0)] if role=='curved' else [],members=[0] if role=='curved' else [],slices=[slice(0,1)] if role=='curved' else [],alias=[-1] if role=='curved' else [],keep=np.asarray([True]))
    monkeypatch.setattr(export.recovery,'build',lambda *a:p)
    d=dict(scan=scan,arms=dict(c0=dict(phase_reference=[])),observations=[dict(observation_id='native',measured_cfo_hz=100.)],entries=[] if role=='curved' else [dict(track_index=0,candidate_index=0,observation_ids=['native'],alias=-1)])
    result,_=export.mapping(d,'c0')
    assert result['native']==dict(role=role,norad=123,alias_lift=1)
