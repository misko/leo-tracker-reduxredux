import numpy as np
import pytest

import position_interaction_study as study
from test_position_structure_study import data


def test_full_factorial_and_shared_zero_control():
    assert len(study.MODES)==4 and len(study.ARMS)==3
    assert {(s['kernel'],s['weights']) for s in study.MODES.values()}=={
        ('C1','C1'),('C1','A03'),('A06','C1'),('A06','A03')}
    assert study.solver_arm('prior-c')=='fitted-c'
    assert study.solver_arm('zero-c')=='zero-c'
    with pytest.raises(ValueError):study.solver_arm('invalid')


@pytest.mark.parametrize('sigma',[None,100.])
def test_rf_prior_gradient_curvature_and_exact_index(sigma):
    obj=object.__new__(study.Objective);obj.size=9;obj.rf_prior_sigma=sigma
    v=np.arange(10)*13.
    p,g,h=obj.extra_penalty(v)
    assert p==pytest.approx(0 if sigma is None else .5*(v[9]/sigma)**2)
    assert not np.any(h[:9,:]) and not np.any(g[:9])
    for i in range(10):
        l,r=v.copy(),v.copy();l[i]-=.001;r[i]+=.001
        num=(obj.extra_penalty(r)[0]-obj.extra_penalty(l)[0])/.002
        assert num==pytest.approx(g[i],abs=1e-10)
    assert np.linalg.eigvalsh(h).min()>=0
    v[9]=0.;assert obj.extra_penalty(v)[0]==0.


@pytest.mark.parametrize('mode',study.MODES)
def test_combinations_retain_all_rows_and_probabilities(mode):
    spec=study.MODES[mode];d=data()
    model=study.old.SingleWindowLikelihood(d,np.zeros((6,1)),spec['kernel'])
    model.weights=study.old.row_weights(d,spec['weights'])
    pred=np.column_stack([d.measured+90.,d.measured+550.])
    visible=np.ones((6,2),bool)
    a=model.evaluate(pred,visible,sigma_hz=200.)
    assert len(model.weights)==6 and np.all(model.weights>0)
    assert np.mean(model.weights)==pytest.approx(1.)
    ref=study.old.SingleWindowLikelihood(d,np.zeros((6,1)),spec['kernel'])
    b=ref.evaluate(pred,visible,sigma_hz=200.)
    np.testing.assert_allclose(a['row_association_probability'],b['row_association_probability'])
    np.testing.assert_allclose(a['prediction_gradient'],model.weights[:,None]*b['prediction_gradient'])
    eps=.001;l,r=pred.copy(),pred.copy();l[1,0]-=eps;r[1,0]+=eps
    num=(model.evaluate(r,visible,sigma_hz=200.)['total_log_likelihood']-
         model.evaluate(l,visible,sigma_hz=200.)['total_log_likelihood'])/(2*eps)
    assert num==pytest.approx(a['prediction_gradient'][1,0],abs=1e-8)
