"""Reject noncausal, ambiguous, unpaired, or non-additive promotion evidence."""
import copy
import pytest
from test_fast_graph_position_v4 import terminal as previous_terminal
from leo.contracts.fast_graph_position_v5 import owners, validate_terminal, GATES
from algo06_production_worker import envelope

def terminal():
    old=previous_terminal(); prior=owners(old); ids=[f'new-{i}' for i in range(20)]
    row=dict(checks=dict.fromkeys(GATES,True),all_checked_gates_pass=True,changed_incumbent_ids=[],
        history=[dict(success=True,phase_change_s=.001)],incumbent_exact_orbits=[dict(all_pass=True)],
        quadrature=dict(local_agreement=True),family_details=[dict(phase_boundary_mass=0,gates=[dict(compatible=True)])],
        endpoint_latlon=[37.9,-122.5])
    arms={a:copy.deepcopy(row) for a in prior}
    candidate=dict(norad=999,target_ids=ids,target_times_s=list(range(20)),
        observation_ids=sorted(set(ids)|set().union(*(set(v) for v in prior.values()))),
        element=dict(element_epoch_utc_ns=100_000_000_000,collected_utc_ns=100_000_000_000),cutoff_utc_ns=200_000_000_000,
        screen=dict(policy='72h_30s',screen_pass=True,arms={a:dict(folds={f:dict(winner=dict(norad=999),margin=15)
                    for f in ['full','20261031','94721','4081']}) for a in prior}),
        replay_checks={a:dict(incumbent_core_objective_difference=0,full_selected_likelihood_difference=0) for a in prior},
        control=copy.deepcopy(arms),trial=dict(arms=arms,entry=dict(observation_ids=ids,norad=999),prior=dict(phase_limit_s=30)),
        published_owners={a:dict(v,**dict.fromkeys(ids,999)) for a,v in prior.items()})
    return envelope(old,candidate,dict(verified=True),30,policy='72h_30s')

def test_additive_result_preserves_previous_contract():
    d=terminal()
    assert validate_terminal(d,input_sha256=d['input_sha256']) is d
    assert d['incumbent']==previous_terminal()

@pytest.mark.parametrize('failure',['future_epoch','future_collection','too_old','identity','margin','missing_fold',
    'control','candidate','owner','unknown','unpaired','read','replay','phase_bound','position','runtime','gps','gap','nan_phase','nan_boundary'])
def test_fail_closed(failure):
    d=terminal(); c=d['candidate']; arm='c0'
    if failure=='future_epoch':c['element']['element_epoch_utc_ns']=d['candidate']['cutoff_utc_ns']+1
    elif failure=='future_collection':c['element']['collected_utc_ns']=d['candidate']['cutoff_utc_ns']+1
    elif failure=='too_old':c['cutoff_utc_ns']=c['element']['element_epoch_utc_ns']+73*3600*10**9
    elif failure=='identity':c['screen']['arms'][arm]['folds']['94721']['winner']['norad']=998
    elif failure=='margin':c['screen']['arms'][arm]['folds']['full']['margin']=9.9
    elif failure=='missing_fold':c['screen']['arms'][arm]['folds'].pop('4081')
    elif failure=='control':c['control'][arm]['checks']['optimizer']=False
    elif failure=='candidate':c['trial']['arms'][arm]['checks']['family_residuals']=False
    elif failure=='owner':c['published_owners'][arm]['old']=998
    elif failure=='unknown':c['observation_ids'].remove('new-0')
    elif failure=='unpaired':c['trial']['arms'].pop(arm)
    elif failure=='read':d['read_audit']['verified']=False
    elif failure=='replay':c['replay_checks'][arm]['full_selected_likelihood_difference']=.1
    elif failure=='phase_bound':c['trial']['prior']['phase_limit_s']=60
    elif failure=='position':d['position']['latitude_deg']=0
    elif failure=='runtime':d['recovery_seconds']=1201
    elif failure=='gps':d['reference_usage']='GPS'
    elif failure=='gap':c['target_times_s'][-1]+=10
    elif failure=='nan_phase':c['trial']['arms'][arm]['history'][-1]['phase_change_s']=float('nan')
    elif failure=='nan_boundary':c['trial']['arms'][arm]['family_details'][0]['phase_boundary_mass']=float('nan')
    with pytest.raises(ValueError):validate_terminal(d,input_sha256=d['input_sha256'])

def test_exact_fallback_when_recovery_fails():
    old=previous_terminal();d=envelope(old,None,None,2,'failed',policy='72h_30s')
    assert d['position']==old['position'] and d['decision']=='ALGO05_fallback'
    d['position']=dict(latitude_deg=0,longitude_deg=0)
    with pytest.raises(ValueError):validate_terminal(d,input_sha256=d['input_sha256'])
