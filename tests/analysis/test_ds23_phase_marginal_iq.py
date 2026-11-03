import numpy as np
import pytest

from ds23_phase_marginal_iq import PhaseMarginalIQ, phase_integral
from ds23_shared_receiver_phase import phase_NLL


def make(count=2,samples=None):
    rng=np.random.default_rng(617)
    if samples is None:samples=rng.normal(size=(2,20000))+1j*rng.normal(size=(2,20000))
    epochs=np.array([[23.2,193.4],[23.28,193.35]])[:,:count]
    frames=[np.arange(a,a+900) for a in [250,3650,7050,10450,13850]]
    problem=PhaseMarginalIQ(samples,2500000.,'lower',epochs,frames,[.3,.5],np.ones(count)*2)
    p=np.r_[np.array([12000.,42000.])[:count],1500.,
        np.array([.123,6.4,-.234,-3.3])[:2*count],np.array([.143,6.2,-.214,-3.1])[:2*count],
        np.array([.8,.2,.9,-.1])[:2*count],np.log(.4)]
    return problem,p


@pytest.mark.parametrize('count',[1,2])
def test_phase_marginal_RF_gradient_matches_finite_differences(count):
    problem,p=make(count)
    result=problem.statistics(p)
    scales=np.r_[problem.scale,1.]
    for k in range(len(p)):
        step=1e-3 if k<problem.code_start else (1e-7 if k<problem.ratio_start and (k-problem.code_start)%2==0 else 1e-6)
        delta=np.zeros_like(p);delta[k]=step
        numeric=(problem.statistics(p+delta,gradient=False)['NLL']-problem.statistics(p-delta,gradient=False)['NLL'])/(2*step)
        np.testing.assert_allclose(result['gradient_scaled'][k]/scales[k],numeric,atol=.003,rtol=4e-4)


def test_phase_marginal_RF_training_cannot_read_outside_support():
    first,p=make()
    changed=first.y.copy();used=np.zeros(changed.shape[1],bool);used[first.used]=True
    changed[:,~used]+=1e6+2e6j
    second,_=make(samples=changed)
    a,b=first.statistics(p),second.statistics(p)
    assert a['NLL']==b['NLL']
    np.testing.assert_array_equal(a['gradient_scaled'],b['gradient_scaled'])


def test_shared_phase_gradient_at_zero_matches_proper_joint_gaussian():
    problem,p=make(count=1)
    p=p[:-1]
    result=problem.statistics(p,fixed_sigma=0.)
    signals=problem.signals(p);signals[1]*=problem.ratios(p)
    expected=0.
    for ix in problem.frames:
        x=np.r_[signals[0][ix]-signals[0][ix].mean(axis=0),signals[1][ix]-signals[1][ix].mean(axis=0)]
        y=np.r_[problem.y[0,ix]-problem.y[0,ix].mean(),problem.y[1,ix]-problem.y[1,ix].mean()]
        variances=np.repeat(problem.noise,len(ix));x=x/np.sqrt(variances[:,None]);y=y/np.sqrt(variances)
        h=np.diag(1/problem.gain)+x.conj().T@x;c=x.conj().T@y
        expected+=np.vdot(y,y).real-np.vdot(c,np.linalg.solve(h,c)).real+np.linalg.slogdet(h)[1]+np.log(problem.gain).sum()
        expected+=(len(ix)-1)*np.log(np.pi*problem.noise).sum()
    np.testing.assert_allclose(result['NLL'],expected,atol=1e-8)


@pytest.mark.parametrize('source_receiver',[0,1])
def test_conditional_phase_prediction_matches_independent_dense_covariance(source_receiver):
    problem,p=make(count=2)
    held=[np.arange(2200,2210)]
    fit=dict(parameters=p[:-1],sigma_rad=np.exp(p[-1]))
    prediction=problem.predict(fit,held,source_receiver=source_receiver)
    signals=problem.signals(p[:-1]);signals[1]*=problem.ratios(p[:-1])
    source=source_receiver;target=1-source;ix=held[0]
    # Use an independent orthonormal basis of the DC-free target subspace.
    q=np.linalg.qr(np.column_stack((np.ones(len(ix)),np.eye(len(ix))[:,:-1])))[0][:,1:]
    bs=signals[source][ix]-signals[source][ix].mean(axis=0)
    bt=q.conj().T@signals[target][ix]
    ys=problem.y[source,ix]-problem.y[source,ix].mean()
    yt=q.conj().T@problem.y[target,ix]
    coefficient_covariance=np.linalg.inv(np.diag(1/problem.gain)+bs.conj().T@bs/problem.noise[source])
    coefficient=coefficient_covariance@bs.conj().T@ys/problem.noise[source]
    mean=bt@coefficient
    covariance=problem.noise[target]*np.eye(len(ix)-1)+bt@coefficient_covariance@bt.conj().T
    inverse=np.linalg.inv(covariance)
    cross=np.vdot(mean,inverse@yt)
    statistics=dict(constant=float(np.linalg.slogdet(covariance)[1]+(len(ix)-1)*np.log(np.pi)),
        y_quadratic=float(np.vdot(yt,inverse@yt).real),
        mean_quadratic=float(np.vdot(mean,inverse@mean).real),
        cross_real=float(cross.real),cross_imag=float(cross.imag))
    expected=phase_NLL(statistics,fit['sigma_rad'],grid_size=8192)
    np.testing.assert_allclose(prediction['NLL'],expected,atol=1e-8)
    with pytest.raises(ValueError,match='overlaps'):
        problem.predict(fit,problem.frames,source_receiver=source_receiver)


def test_phase_integral_and_log_sd_gradient_have_continuous_quadrature_limit():
    for sigma in [.03,.4,2.8]:
        for cross in [0.+0j,30.+45j,-70.-20j]:
            a=phase_integral(cross,sigma,2048)
            b=phase_integral(cross,sigma,8192)
            np.testing.assert_allclose(a,b,atol=1e-9)
            h=1e-5
            numeric=(phase_integral(cross,sigma*np.exp(h),8192)[0]
                -phase_integral(cross,sigma*np.exp(-h),8192)[0])/(2*h)
            np.testing.assert_allclose(a[2],numeric,atol=1e-7)


@pytest.mark.parametrize('count',[1,2])
def test_shared_phase_joint_density_matches_source_then_target_factorization(count):
    from audit_ds23_phase_marginal_iq import factorized_joint_NLL
    problem,p=make(count=count)
    expected=factorized_joint_NLL(problem,p[:-1],np.exp(p[-1]))
    np.testing.assert_allclose(problem.statistics(p)['NLL'],expected,atol=1e-8)
