import numpy as np
import pytest
from leo.analysis.research.covariance_structure import prepare,evaluate


def fixture():
    t=np.arange(24,dtype=float);o=np.zeros(24,int)
    c=25*np.eye(24)+16*np.exp(-abs(t[:,None]-t[None,:])/3)
    return t,o,c


def test_physical_gls_and_permutation_invariance():
    t,o,c=fixture();r=np.sin(t)*5;train=(t%3)!=0
    p=prepare(c,t,o,[train],draws=1024)
    inv=np.linalg.solve(c,np.ones(len(t)))
    assert p['weights'][0]@r==pytest.approx(inv@r/np.sqrt(inv.sum()))
    permutation=np.random.default_rng(8).permutation(len(t))
    q=prepare(c[np.ix_(permutation,permutation)],t[permutation],o[permutation],[train[permutation]],draws=1024)
    assert evaluate(p,r)==evaluate(q,r[permutation])


def test_calibration_does_not_depend_on_values_and_detects_structure():
    t,o,c=fixture();p=prepare(c,t,o,draws=1024)
    assert evaluate(p,np.zeros(len(t)))['compatible']
    for r in (np.ones(len(t))*40,(t-t.mean())*10,(t>12)*100,(t-t.mean())**2*5):
        assert not evaluate(p,r)['compatible']
    assert p['threshold']==prepare(c,t,o,draws=1024)['threshold']


def test_rejects_invalid_covariance_and_masks():
    t,o,c=fixture()
    with pytest.raises(ValueError):prepare(c,t,o,[np.ones(len(t),bool)])
    c[0,1]+=1
    with pytest.raises(ValueError):prepare(c,t,o)
