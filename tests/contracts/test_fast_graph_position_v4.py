"""Gap promotion must retain complete prior evidence and independent pairing."""
import copy
import pytest
from test_fast_graph_position_v3 import terminal as v3_terminal
from leo.contracts.fast_graph_position_v4 import owners,validate_terminal
from algo05_production_worker import envelope

def terminal():
    old=v3_terminal();target=[f'gap-{i}' for i in range(12)]
    prior=owners(old)
    trial=dict(paired_valid=True,arms={a:dict(endpoint_latlon=[37.9,-122.54],
        proposed_owners=dict(v,**dict.fromkeys(target,100)),proposed_associated_ids=[*v,*target],final_phase_change_s=.001) for a,v in prior.items()})
    audit=dict(all_verified=True,rows=[dict(role=role,arm=a,verified=True,gate_slacks={'slope':.1}) for role in ('control','target_0') for a in prior])
    candidate=dict(policy='gap_conditional',identity=dict(status='conditionally_supported_identity',norad=100),
        trial=trial,audit=audit,observation_ids=[*prior['c0'],*target,'tail'],target_ids=target,parent_ids=[*target,'tail'],target_times_s=list(range(12)))
    return envelope(old,candidate,dict(verified=True),20)

def test_success_retains_incumbent_and_both_arms():
    d=terminal();before=copy.deepcopy(d['incumbent'])
    assert validate_terminal(d,input_sha256=d['input_sha256'])==d
    assert d['incumbent']==before and d['decision']=='ALGO05_additive'

@pytest.mark.parametrize('failure',['owner','unknown','arm','gate','missing_audit','phase','nan','full_parent','time_gap','short','identity','position','read','runtime','gps','future'])
def test_rejects_invalid_promotion(failure):
    d=terminal();c=d['candidate'];r=c['trial']['arms']['c0']
    if failure=='owner':r['proposed_owners']['old']=999
    elif failure=='unknown':c['observation_ids'].remove('gap-1')
    elif failure=='arm':r['proposed_owners']['gap-1']=999
    elif failure=='gate':c['audit']['rows'][0]['gate_slacks']['slope']=-.01
    elif failure=='missing_audit':c['audit']['rows'].pop()
    elif failure=='phase':r['final_phase_change_s']=.02
    elif failure=='nan':r['final_phase_change_s']=float('nan')
    elif failure=='full_parent':c['parent_ids']=c['target_ids']
    elif failure=='time_gap':c['target_times_s'][-1]+=6
    elif failure=='short':c['target_times_s']=[i/2 for i in range(12)]
    elif failure=='identity':c['identity']['norad']=999
    elif failure=='position':d['position']['latitude_deg']+=1
    elif failure=='read':d['read_audit']['verified']=False
    elif failure=='runtime':d['recovery_seconds']=1201
    elif failure=='gps':d['reference_usage']='GPS'
    elif failure=='future':d['future_TLE_used']=True
    with pytest.raises(ValueError):validate_terminal(d,input_sha256=d['input_sha256'])

def test_fallback_is_exact_even_if_recovery_failed():
    old=v3_terminal();d=envelope(old,None,None,2,'timeout')
    assert d['position']==old['position'] and d['decision']=='ALGO04_fallback'
    d['position']=dict(latitude_deg=0,longitude_deg=0)
    with pytest.raises(ValueError):validate_terminal(d,input_sha256=d['input_sha256'])
