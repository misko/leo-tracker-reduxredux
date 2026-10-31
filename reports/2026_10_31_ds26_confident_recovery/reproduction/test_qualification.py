from copy import deepcopy
from qualification import qualify,ARMS

def fixture():
    trial=dict(paired_valid=True,arms={a:dict(proposed_associated_ids=['old','new'],
        proposed_owners={'old':10,'new':20},final_phase_change_s=.001) for a in ARMS})
    return trial,dict(all_verified=True),{a:{'old':10} for a in ARMS},{'old','new'}

def test_valid_recovery():
    assert qualify(*fixture())['qualified']

def test_rejected_trial_counts_do_not_become_recovered():
    args=list(fixture());args[0]['paired_valid']=False
    assert not qualify(*args)['qualified']

def test_missing_prior_recovery_cannot_be_discarded():
    args=list(fixture());args[2]['fitted_c']['previous_recovery']=30
    assert not qualify(*args)['qualified']

def test_changed_owner_rejected_even_with_same_count():
    args=list(fixture());args[0]['arms']['c0']['proposed_owners']['old']=11
    assert not qualify(*args)['qualified']

def test_exact_audit_required():
    args=list(fixture());args[1]=None
    assert not qualify(*args)['qualified']

def test_both_arms_and_same_added_identity_required():
    args=list(fixture());args[0]['arms']['c0']['proposed_owners']['new']=21
    assert not qualify(*args)['qualified']

def test_unknown_point_rejected():
    args=list(fixture());args[3]={'old'}
    assert not qualify(*args)['qualified']
