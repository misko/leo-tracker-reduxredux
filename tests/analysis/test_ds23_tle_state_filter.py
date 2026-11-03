import numpy as np
import pytest
from scipy.stats import multivariate_t

from ds23_tle_state_filter import pack,filter_histories,predict_state,student_cost
from prepare_ds23_tle_state_filter import extract


def example():
    return pack([dict(norad=1,times_hours=[0.,1.,2.],observations=[[0.,0.],[.1,.02],[.13,.015]],
        score_eligible=[False,False,True],publication_utc_ns=[1,2,3])])


def test_student_density_matches_independent_library():
    error=np.array([[.2,-.1],[.4,.3]])
    covariance=np.array([[[2.,.2],[.2,1.]],[[1.,.1],[.1,3.]]])
    alpha=np.array([1.5,3.5]);beta=np.array([.5,2.])
    expected=[-2*multivariate_t.logpdf(e,shape=s*b/a,df=2*a) for e,s,a,b in zip(error,covariance,alpha,beta)]
    np.testing.assert_allclose(student_cost(error,covariance,alpha,beta),expected,atol=1e-12)


def test_filter_gaussian_component_matches_dense_conditioning():
    data=example();rp,rv,sqrtq=.2,.05,.03
    result=filter_histories(data,[rp,rv,sqrtq])
    r=np.diag([rp*rp,rv*rv]);f=np.array([[1.,1.],[0.,1.]])
    q=sqrtq**2*np.array([[1/3,.5],[.5,1.]])
    p0=r;p1=f@p0@f.T+q;p2=f@p1@f.T+q
    cross=f@p1
    observation_cov=np.block([[p1+r,p1@f.T],[cross,p2+r]])
    target_cross=np.column_stack((cross,p2))
    ys=data['observations'][0,1:].ravel()
    expected_mean=target_cross@np.linalg.solve(observation_cov,ys)
    expected_cov=p2-target_cross@np.linalg.solve(observation_cov,target_cross.T)
    np.testing.assert_allclose(result['posterior_mean'][0],expected_mean,atol=1e-12)
    np.testing.assert_allclose(result['posterior_covariance'][0],expected_cov,atol=1e-12)


def test_forecast_variance_includes_measurement_noise_latent_variance_does_not():
    result=filter_histories(example(),[.2,.05,.03]);prediction=predict_state(result,[3.])
    expected=.2**2*result['beta']/(result['alpha']-1)
    np.testing.assert_allclose(prediction['next_measurement_variance']-prediction['latent_variance'],expected,atol=1e-12)
    assert prediction['latent_variance'][0]>0


def test_appending_a_future_update_never_changes_an_earlier_prediction():
    first=example();second=example();second['observations'][0,2]=[999.,99.]
    a=filter_histories(first,[.2,.05,.03]);b=filter_histories(second,[.2,.05,.03])
    np.testing.assert_array_equal(a['predicted_mean'],b['predicted_mean'])
    np.testing.assert_array_equal(a['predicted_variance'],b['predicted_variance'])
    assert not np.array_equal(a['posterior_mean'],b['posterior_mean'])
    with pytest.raises(ValueError,match='before the last'):
        predict_state(a,[1.])


def test_covariance_stays_positive_with_irregular_time_gaps():
    rng=np.random.default_rng(811)
    series=[]
    for number in range(40):
        times=np.r_[0,np.cumsum(rng.uniform(.001,20.,10))]
        series.append(dict(norad=number,times_hours=times,observations=rng.normal(size=(11,2)),
            score_eligible=[False,False]+[True]*9,publication_utc_ns=np.arange(11)))
    result=filter_histories(pack(series),[.01,.001,1.])
    assert np.all(np.linalg.eigvalsh(result['posterior_covariance'])>0)
    assert np.isfinite(result['joint_cost']).all()


def test_measurement_off_control_has_equal_latent_and_forecast_variance():
    result=filter_histories(example(),[0.,0.,.03])
    prediction=predict_state(result,[3.])
    np.testing.assert_allclose(prediction['next_measurement_variance'],prediction['latent_variance'],atol=1e-12)
    assert np.isfinite(result['joint_cost']).all()


@pytest.mark.parametrize('field',['epoch','collected_utc_ns'])
def test_feature_extraction_rejects_future_elements_before_propagation(field):
    version=dict(epoch=1,collected_utc_ns=2)
    version[field]=11
    history=dict(cutoff_utc_ns=10,origin_utc_ns=10,past_versions={'1':[version]})
    with pytest.raises(ValueError,match='future TLE'):
        extract(history,dict(transitions=[]),{})
