import numpy as np
from scipy.special import logsumexp

from ds23_nonlinear_phase_integral import ConditionalPhaseIntegral,phase_frequency_samples,summarize_log_ratio
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency


def test_batched_phase_geometry_matches_existing_scalar_geometry():
    times=np.arange(-5.,15.);r=np.random.default_rng(449)
    bank=dict(time_s=times,position_km=r.normal(size=(2,len(times),3))*100+np.array([7000.,0.,0.]),
        velocity_km_s=r.normal(size=(2,len(times),3)))
    t=np.array([1.,2.,4.,7.]);labels=np.array([0,1,0,1]);phases=r.uniform(-1,1,size=(7,2))
    batched=phase_frequency_samples(bank,t,labels,phases,37.,-122.)
    expected=np.array([paired_phase_frequency(bank,t,labels,p,37.,-122.)[0] for p in phases])
    np.testing.assert_allclose(batched,expected,atol=1e-9,rtol=1e-12)


def test_phase_conditional_inverse_and_evidence_ratio_match_dense_gaussian():
    r=np.random.default_rng(45);u=r.normal(size=(7,3));y=r.normal(size=7);w=r.uniform(.5,2.,7);prior=np.array([.7,1.4,2.])
    problem=ConditionalPhaseIntegral(y,u,w,prior,[1]);draw=problem.draws(128,9);delta=r.normal(size=(128,7))*.2
    rest=u[:,[0,2]];covariance=np.diag(1/w)+(rest/prior[[0,2]])@rest.T
    inverse=np.linalg.inv(covariance)
    np.testing.assert_allclose(problem.inverse_rest_covariance(delta.T),inverse@delta.T,atol=1e-10)
    linear=y[None,:]-draw@u[:,[1]].T
    expected=np.array([-.5*((a-d)@inverse@(a-d)-a@inverse@a) for a,d in zip(linear,delta,strict=True)])
    np.testing.assert_allclose(problem.log_ratio(draw,delta),expected,atol=1e-10)
    assert summarize_log_ratio(problem.log_ratio(draw,np.zeros_like(delta)))['negative_twice_log_evidence_correction']==0.


def test_quadratic_phase_evidence_matches_high_order_gaussian_quadrature():
    problem=ConditionalPhaseIntegral([.2],np.array([[0.]]),[1.],[1.],[0])
    draw=problem.draws(16384,47);delta=.3*draw**2
    actual=summarize_log_ratio(problem.log_ratio(draw,delta))['negative_twice_log_evidence_correction']
    z,weight=np.polynomial.hermite.hermgauss(128);correction=.3*(np.sqrt(2)*z)**2
    expected=-2*logsumexp(np.log(weight/np.sqrt(np.pi))+.2*correction-.5*correction**2)
    np.testing.assert_allclose(actual,expected,atol=2e-4)
