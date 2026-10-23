import pytest
import numpy as np
from qualify_native import bad_new_paths,protected_exclusion,eligible

def test_union_both_arms_only_new_paths():
    entries=[dict(component=k) for k in ['old','newA','newB','newC']]
    slacks={'c0':{'newA/linear/lag1':-.1,'newB/linear/lag1':.2,'old/linear/lag1':-.3},
            'fitted_c':{'newB/linear/step':-.1,'newC/linear/rms':0.,'curve/conditional/step':-.2}}
    keys,reasons,protected=bad_new_paths(entries,entries[:1],slacks)
    assert keys==['newA','newB']
    assert len(protected)==2 and 'c0:old/linear/lag1' in protected
    assert set(reasons)==set(keys)

def test_exclusion_protects_postfit_parent_associations():
    entries=[dict(component='new',observation_ids=['a','b'])]
    parent={'c0':dict(accepted_observation_ids=['b']),'fitted_c':dict(accepted_observation_ids=[])}
    with pytest.raises(AssertionError,match='parent IDs'):protected_exclusion(entries,['new'],parent)
    parent['c0']['accepted_observation_ids']=['c']
    remaining,removed=protected_exclusion(entries,['new'],parent)
    assert remaining==[] and removed==entries

def test_nonfinite_gate_is_not_silently_accepted():
    with pytest.raises(ValueError):bad_new_paths([dict(component='n')],[],{'c0':{'n/linear/lag1':np.nan}})

def test_scope_is_original_eligibility_not_rescue_acceptance():
    assert eligible({'eligible':True,'accepted':False})
    assert not eligible({'eligible':False,'accepted':False})
