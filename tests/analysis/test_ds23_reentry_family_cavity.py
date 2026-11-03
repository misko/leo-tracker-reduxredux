import copy
from types import SimpleNamespace
import numpy as np
import pytest

import probe_ds23_reentry_family_cavity as hybrid


@pytest.mark.parametrize('selected,phase_change,status,expected_source',[(False,0.,'complete','previous_conditional_family_method'),
    (True,.02,'complete','previous_conditional_family_method'),(True,.001,'complete','recovered_curves'),
    (True,.001,'budget_exhausted','previous_conditional_family_method')])
def test_hybrid_uses_current_incumbent_fallback_and_only_converged_recovery(monkeypatch,selected,phase_change,status,expected_source):
    arms={arm:dict(endpoint_east_north_km=[1.,2.],phase_reference=[.1,.2],final_phase_change_s=0.) for arm in ['c0','fitted_c']}
    base=dict(scan=SimpleNamespace(kind='original'),node=dict(marker='current'),keep=np.array([True,False]),
        means=np.array([.1,.2]),entries=[dict(component='linear')],powers=np.array([.5]),model=dict(nu=4),signed=dict(policy_arms=arms))
    original=dict(base,node=dict(marker='original'))
    recovered_arms={arm:dict(endpoint_east_north_km=[3.,4.],phase_reference=[.3,.4],final_phase_change_s=phase_change) for arm in arms}
    chosen=dict(paired_valid=True,arms=recovered_arms,node=dict(marker='reentry'),mask=[True,True],means=[.3,.4])
    record=dict(status=status,selected=chosen if selected else None,entries=base['entries'],powers=[.5],hyper=base['model'])
    monkeypatch.setattr(hybrid,'selected_context',lambda case:(copy.deepcopy(base),copy.deepcopy(arms)))
    monkeypatch.setattr(hybrid,'selected_original_context',lambda case:copy.deepcopy(original))
    monkeypatch.setattr(hybrid,'read',lambda path:copy.deepcopy(record))
    monkeypatch.setattr(hybrid.recovery,'fine_view',lambda scan:SimpleNamespace(kind='fine'))
    monkeypatch.setattr(hybrid,'make_event_problem',lambda *args:SimpleNamespace(arguments=args))
    result=hybrid.context('test')
    assert result['reentry_context_source']==expected_source
    good=expected_source=='recovered_curves'
    assert result['node']['marker']==('reentry' if good else 'current')
    assert result['scan'].kind==('fine' if good else 'original')
    np.testing.assert_array_equal(result['x'],[3.,4.] if good else [1.,2.])
    assert result['entries']==base['entries']
    assert result['keep'][0]  # no original active point can disappear


def test_legacy_gate_schema_bridge_preserves_decisions_membership_and_numerics():
    old=dict(component='curve',compatible=True,points=2,observation_ids=['a','b'],rms_hz=100.,bias_hz=20.)
    new=dict(component='curve',compatible=True,points=2,observation_ids=['a','b'],norad=101,candidate_index=1)
    hybrid.assert_linear_gate_replay(old,new,dict(rms_hz=100.+1e-8,bias_hz=20.-1e-8))
    with pytest.raises(ValueError,match='decision changed'):hybrid.assert_linear_gate_replay(old,dict(new,compatible=False),dict(rms_hz=100.,bias_hz=20.))
    with pytest.raises(ValueError,match='numerical diagnostic'):hybrid.assert_linear_gate_replay(old,new,dict(rms_hz=101.,bias_hz=20.))
    with pytest.raises(ValueError,match='candidate changed'):hybrid.assert_linear_gate_replay(dict(old,norad=102),new,dict(rms_hz=100.,bias_hz=20.))


def test_curved_replay_tolerates_roundoff_but_requires_exact_decisions_and_IDs():
    old=dict(tracks=[dict(component='curve',norad=101,points=2,compatible=True,observation_ids=['a','b'],profile_bias_hz=100.,diagnostics=dict(slope_z=2.))])
    new=copy.deepcopy(old);new['tracks'][0]['profile_bias_hz']+=5e-6;new['tracks'][0]['diagnostics']['slope_z']+=1e-8
    hybrid.assert_curved_gate_replay(old,new)
    wrong=copy.deepcopy(new);wrong['tracks'][0]['compatible']=False
    with pytest.raises(ValueError,match='decision changed'):hybrid.assert_curved_gate_replay(old,wrong)
    wrong=copy.deepcopy(new);wrong['tracks'][0]['norad']=102
    with pytest.raises(ValueError,match='integer metadata changed'):hybrid.assert_curved_gate_replay(old,wrong)
    wrong=copy.deepcopy(new);wrong['tracks'][0]['observation_ids'][0]='different'
    with pytest.raises(ValueError,match='identity metadata changed'):hybrid.assert_curved_gate_replay(old,wrong)
    wrong=copy.deepcopy(new);wrong['tracks'][0]['profile_bias_hz']+=.01
    with pytest.raises(ValueError,match='numerical diagnostic changed'):hybrid.assert_curved_gate_replay(old,wrong)


def test_legacy_reference_replay_uses_only_recorded_rounds_and_exact_convention():
    saved=dict(phase_reference=[2.,3.],state=dict(phases=[2.,9.,3.]),
        history=[dict(fit=dict(parameters=[1.,2.])),dict(fit=dict(parameters=[2.,3.])),dict(fit=dict(parameters=[4.,5.]))])
    result=hybrid.replay_archived_reference(saved,[0,2],2,lambda ref,x:ref+x*.1)
    np.testing.assert_allclose(result,[.3,.5],atol=1e-15)
    with pytest.raises(ValueError,match='legacy post-update convention'):
        hybrid.replay_archived_reference(dict(saved,phase_reference=[1.,3.]),[0,2],2,lambda ref,x:ref+x*.1)


def test_legacy_empty_linear_gate_array_requires_zero_predictive_entries():
    assert hybrid.archived_linear_gates({},0)==[]
    assert hybrid.archived_linear_gates(dict(linear_gates=[]),0)==[]
    with pytest.raises(ValueError,match='count changed or metadata missing'):
        hybrid.archived_linear_gates({},1)
    with pytest.raises(ValueError,match='count changed or metadata missing'):
        hybrid.archived_linear_gates(dict(linear_gates=[dict(compatible=True)]),0)
