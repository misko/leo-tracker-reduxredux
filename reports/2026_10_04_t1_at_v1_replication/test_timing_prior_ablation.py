from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest
from timing_prior_ablation import ScaledTimingObjective, PriorObjective, TimingObjective, CalibrationObjective, reprice, best_record
from timing_model import zero_sum_basis


def prior(precision):
    obj=object.__new__(ScaledTimingObjective);obj.prior_precision=precision
    obj.basis=zero_sum_basis(3);obj.common_prior=True
    return obj


@pytest.mark.parametrize('precision',[1.,1./9.,0.])
def test_penalty_value_gradient_and_no_position_prior(precision):
    obj=prior(precision);vector=np.array([4.,2.,100.,1.,200.,3.,2.,3.,-4.])
    value,g=obj.penalty(vector);raw,rg=TimingObjective.penalty(obj,vector)
    np.testing.assert_allclose(value,precision*raw)
    np.testing.assert_allclose(g,precision*rg)
    np.testing.assert_array_equal(g[:6],np.zeros(6))
    for j in range(len(vector)):
        e=np.eye(len(vector))[j]*1e-5
        fd=(obj.penalty(vector+e)[0]-obj.penalty(vector-e)[0])/(2e-5)
        assert abs(fd-g[j])<1e-8


@pytest.mark.parametrize('precision',[1.,1./9.,0.])
def test_fisher_removes_old_precision_as_well(precision):
    obj=object.__new__(PriorObjective);obj.size=9;obj.base=SimpleNamespace(prior_precision=precision)
    raw=np.diag([4.,4.,4.,4.,4.,4.,4.01,5.,5.,4.])
    with patch.object(CalibrationObjective,'curvature',return_value=raw.copy()):
        h=obj.curvature(np.zeros(10))
    expected=np.eye(10)*4.;expected[6,6]+=.01*precision
    expected[7,7]+=precision;expected[8,8]+=precision
    np.testing.assert_allclose(h,expected)


@pytest.mark.parametrize('precision',[-1.,np.nan,np.inf])
def test_invalid_precision_rejected(precision):
    with pytest.raises(ValueError):ScaledTimingObjective(prior_precision=precision)


def test_repricing_does_not_inherit_other_models_convergence():
    original=dict(objective=10.,success=True,parameters=[1,2],fixed_location=False)
    obj=SimpleNamespace(base=SimpleNamespace(deadline=0.))
    with patch('timing_prior_ablation.check_stationarity',return_value=(9.,2.)):
        result=reprice(obj,original)
    assert result['objective']==9. and not result['success']
    assert original['objective']==10. and original['success']


def test_candidate_selection_is_by_score_not_position_accuracy():
    near=dict(objective=11.,success=True,fixed_location=False,point_km=[0.,0.])
    far=dict(objective=10.,success=False,fixed_location=False,point_km=[3.,0.])
    assert best_record([near,far]) is far
