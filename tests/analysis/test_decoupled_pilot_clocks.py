import numpy as np

from decoupled_pilot_clocks import (
    DecoupledPilotWorkspace,ContinuousCoupledWorkspace,IsolatedRoundedCoupledWorkspace,
)
from fast_local_pilot_refinement import FastPilotWorkspace


def workspace():
    rng=np.random.default_rng(671)
    y=rng.normal(size=50000)+1j*rng.normal(size=50000)
    return DecoupledPilotWorkspace(y,2500000,'lower',510.23)


def test_equal_clocks_are_exactly_nested_in_published_replica():
    p=workspace();parameters=np.array([12345.,.12,7.3,7.3])
    reference=p.replica(.12,7.3)*np.exp(2j*np.pi*12345.*(p.t-p.mid))
    np.testing.assert_allclose(p.signal(parameters),reference,atol=1e-9)


def test_profiled_clock_gradient_matches_finite_difference():
    p=workspace();parameters=np.array([12345.,.123,4.2,-17.3])
    result=p.statistics(parameters)
    for k,scale in enumerate(p.parameter_scale):
        delta=np.zeros(4);delta[k]=scale*1e-6
        difference=(p.statistics(parameters+delta,derivatives=False)['score']-
                    p.statistics(parameters-delta,derivatives=False)['score'])/(2e-6)
        np.testing.assert_allclose(result['gradient_score'][k],difference,rtol=1e-3,atol=1e-8)


def test_integer_frame_period_removes_rounding_difference():
    samples=np.ones(60000,complex)
    a=ContinuousCoupledWorkspace(samples,3000000,'lower',400.2)
    b=IsolatedRoundedCoupledWorkspace(samples,3000000,'lower',400.2)
    np.testing.assert_array_equal(a.replica(.13,7.),b.replica(.13,7.))
    a=ContinuousCoupledWorkspace(samples[:50000],2500000,'lower',400.2)
    b=IsolatedRoundedCoupledWorkspace(samples[:50000],2500000,'lower',400.2)
    assert np.mean(abs(a.replica(.13,7.)-b.replica(.13,7.))**2)>.01


def test_distinct_clocks_are_recovered_with_independent_frame_gains():
    p=workspace();truth=np.array([12345.,.12,5.,-27.])
    signal=p.signal(truth);rng=np.random.default_rng(651)
    for ix in p.frames:
        signal[ix]*=np.exp(1j*rng.uniform(-np.pi,np.pi))
    p=DecoupledPilotWorkspace(signal+.01*(rng.normal(size=len(signal))+1j*rng.normal(size=len(signal))),
                              2500000,'lower',510.23)
    fit=p.clock_fit([12360.,0.,0.,0.])
    assert abs(fit['CFO_hz']-truth[0])<1.
    assert abs(fit['frame_ppm']-truth[2])<.1
    assert abs(fit['intra_ppm']-truth[3])<1.
    assert not fit['boundary']


def test_fractional_frame_position_agrees_with_reference_scorer_gradient():
    rng=np.random.default_rng(787);y=rng.normal(size=50000)+1j*rng.normal(size=50000)
    p=ContinuousCoupledWorkspace(y,2500000,'lower',510.23)
    parameters=np.array([12345.,.123,4.2])
    result=p.statistics(parameters)
    reference=float(p.evaluate([parameters[0]],parameters[1],parameters[2])[0])
    np.testing.assert_allclose(reference,result['score'],atol=1e-13)
    for k,scale in enumerate(p.parameter_scale):
        delta=np.zeros(3);delta[k]=scale*1e-6
        difference=(p.statistics(parameters+delta)['score']-p.statistics(parameters-delta)['score'])/(2e-6)
        np.testing.assert_allclose(result['gradient_score'][k],difference,rtol=1e-3,atol=1e-8)
