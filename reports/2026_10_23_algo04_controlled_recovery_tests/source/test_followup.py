import numpy as np
from followup import step_proposal,combine_ownership


def test_step_search_removes_affine_drift():
    t=np.arange(40.)
    r=3+2*t+150*(t>=20)
    result=step_proposal(t,r,np.full(40,10.))
    assert result['cut']==20
    np.testing.assert_allclose(result['amplitude_hz'],150,atol=1e-8)


def test_no_short_endpoint_chopping():
    assert step_proposal(np.arange(15),np.zeros(15),np.ones(15)) is None
    result=step_proposal(np.arange(20),np.arange(20),np.ones(20))
    assert 8<=result['cut']<=12


def test_explicit_predictive_ownership_has_single_authority():
    extended=[dict(component='same',compatible=True,observation_ids=['a']),
              dict(component='overlap',compatible=True,observation_ids=['a','b']),
              dict(component='independent',compatible=True,observation_ids=['c'])]
    explicit=[dict(component='same',compatible=True,observation_ids=['a'])]
    assert [r['component'] for r in combine_ownership(extended,explicit)]==['independent','same']
