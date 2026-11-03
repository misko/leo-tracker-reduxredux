import numpy as np

from ds23_tle_state_filter import pack,filter_histories,predict_state
from ds23_phase_score_filter import filter_with_mean,predict_with_mean


def test_acceleration_gauge_transport_is_exact_and_does_not_mutate_observations():
    t=np.array([0.,.4,2.,3.5]);y=np.array([[0.,0.],[.1,.02],[.2,.01],[.3,.04]])
    a=-.03;drift=np.column_stack((.5*a*t*t,a*t))
    def data(values):
        return pack([dict(norad=1,times_hours=t,observations=values,score_eligible=[False,False,True,True],publication_utc_ns=[1,2,3,4])])
    plain=data(y);shifted=data(y+drift);before=shifted['observations'].copy()
    base=filter_histories(plain,[.2,.05,.03]);actual=filter_with_mean(shifted,[.2,.05,.03,a])
    np.testing.assert_allclose(actual['phase_cost'],base['phase_cost'],atol=1e-12)
    np.testing.assert_allclose(actual['posterior_covariance'],base['posterior_covariance'],atol=1e-12)
    np.testing.assert_array_equal(shifted['observations'],before)
    expected=predict_state(base,[5.]);predicted=predict_with_mean(actual,[5.])
    np.testing.assert_allclose(predicted['mean'],expected['mean']+.5*a*25,atol=1e-12)
    np.testing.assert_allclose(predicted['latent_variance'],expected['latent_variance'],atol=1e-12)


def test_zero_acceleration_nests_original_filter_exactly():
    d=pack([dict(norad=1,times_hours=[0.,1.,2.],observations=[[0.,0.],[.1,.02],[.2,.03]],
        score_eligible=[False,False,True],publication_utc_ns=[1,2,3])])
    a=filter_histories(d,[.2,.05,.03]);b=filter_with_mean(d,[.2,.05,.03,0.])
    np.testing.assert_array_equal(a['phase_cost'],b['phase_cost'])
    np.testing.assert_array_equal(a['posterior_mean'],b['posterior_mean'])
