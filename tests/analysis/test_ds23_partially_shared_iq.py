import numpy as np
import pytest

from ds23_partially_shared_iq import PartiallySharedIQ
from test_ds23_phase_marginal_iq import make


def partial(shared):
    original,p=make()
    # Expand the common clock into separate physical contrasts.
    p=np.r_[p[:2],p[2],p[2],p[3:]]
    problem=PartiallySharedIQ(original.y,original.fs,'lower',original.epochs,original.frames,
        original.noise,original.gain,separate_clocks=True,shared_components=shared)
    return problem,p


@pytest.mark.parametrize('shared',[[True,False],[False,True],[False,False]])
def test_partial_correspondence_gradient_matches_finite_differences(shared):
    problem,p=partial(shared);result=problem.statistics(p);scales=np.r_[problem.scale,1.]
    for k in range(len(p)):
        step=1e-3 if k<problem.code_start else (1e-7 if k<problem.ratio_start and (k-problem.code_start)%2==0 else 1e-6)
        delta=np.zeros_like(p);delta[k]=step
        numeric=(problem.statistics(p+delta,gradient=False)['NLL']-problem.statistics(p-delta,gradient=False)['NLL'])/(2*step)
        np.testing.assert_allclose(result['gradient_scaled'][k]/scales[k],numeric,atol=.003,rtol=4e-4)


def test_all_shared_matches_previous_joint_density_and_prediction():
    from ds23_phase_marginal_iq import PhaseMarginalIQ
    problem,p=partial([True,True])
    original=PhaseMarginalIQ(problem.y,problem.fs,'lower',problem.epochs,problem.frames,
        problem.noise,problem.gain,separate_clocks=True)
    a,b=problem.statistics(p),original.statistics(p)
    np.testing.assert_allclose(a['NLL'],b['NLL'],atol=1e-9)
    np.testing.assert_allclose(a['gradient_scaled'],b['gradient_scaled'],atol=1e-9)
    fit=dict(parameters=p[:-1],sigma_rad=np.exp(p[-1]))
    for r in [0,1]:
        np.testing.assert_allclose(problem.predict(fit,[np.arange(2200,2240)],source_receiver=r)['NLL'],
            original.predict(fit,[np.arange(2200,2240)],source_receiver=r)['NLL'],atol=1e-9)


def test_no_shared_components_factorizes_into_independent_receiver_densities():
    problem,p=partial([False,False]);expected=0.
    signals=problem.signals(p[:-1]);signals[1]*=problem.ratios(p[:-1])
    for r in [0,1]:
        for ix in problem.frames:
            a=signals[r][ix]-signals[r][ix].mean(axis=0)
            y=problem.y[r,ix]-problem.y[r,ix].mean()
            h=np.diag(1/problem.gain)+a.conj().T@a/problem.noise[r];c=a.conj().T@y/problem.noise[r]
            expected+=np.vdot(y,y).real/problem.noise[r]-np.vdot(c,np.linalg.solve(h,c)).real
            expected+=np.linalg.slogdet(h)[1]+np.log(problem.gain).sum()+(len(ix)-1)*np.log(np.pi*problem.noise[r])
    np.testing.assert_allclose(problem.statistics(p)['NLL'],expected,atol=1e-8)
    np.testing.assert_allclose(problem.statistics(p)['gradient_scaled'][-1],0.,atol=1e-12)


def test_unmatched_target_channel_phase_is_a_gauge():
    problem,p=partial([True,False]);q=p.copy()
    index=problem.ratio_start+2
    value=(p[index]+1j*p[index+1])*np.exp(.9j)
    q[index:index+2]=[value.real,value.imag]
    np.testing.assert_allclose(problem.statistics(p)['NLL'],problem.statistics(q)['NLL'],atol=1e-8)


def test_unmatched_component_prediction_ignores_source_realization():
    problem,p=partial([False,False]);fit=dict(parameters=p[:-1],sigma_rad=.4);held=[np.arange(2200,2240)]
    original=problem.predict(fit,held)['NLL']
    problem.y[0,held[0]]+=100+200j*np.arange(len(held[0]))
    np.testing.assert_allclose(problem.predict(fit,held)['NLL'],original,atol=1e-9)


def test_partial_joint_density_matches_dense_phase_mixture():
    from scipy.special import logsumexp
    problem,p=partial([True,False]);problem.grid_size=32
    problem.frames=[ix[:40] for ix in problem.frames]
    physical=problem.signals(p[:-1]);physical[1]*=problem.ratios(p[:-1])
    signals=[problem.expanded(physical[r],r) for r in [0,1]]
    sigma=np.exp(p[-1]);phi=np.linspace(-np.pi,np.pi,32,endpoint=False)
    images=phi[:,None]+2*np.pi*np.arange(-3,4)[None]
    logprior=logsumexp(-.5*(images/sigma)**2,axis=1);logprior-=logsumexp(logprior)
    expected=0.
    q=np.linalg.qr(np.column_stack((np.ones(40),np.eye(40)[:,:-1])))[0][:,1:]
    for ix in problem.frames:
        a=q.conj().T@signals[0][ix]/np.sqrt(problem.noise[0])
        b=q.conj().T@signals[1][ix]/np.sqrt(problem.noise[1])
        y=np.r_[q.conj().T@problem.y[0,ix]/np.sqrt(problem.noise[0]),
            q.conj().T@problem.y[1,ix]/np.sqrt(problem.noise[1])]
        values=[]
        for angle in phi:
            design=np.r_[a,b*np.exp(1j*angle)]
            covariance=np.eye(78)+(design*problem.latent_gain)@design.conj().T
            value=np.linalg.slogdet(covariance)[1]+np.vdot(y,np.linalg.solve(covariance,y)).real
            value+=78*np.log(np.pi)+39*np.log(problem.noise).sum()
            values.append(value)
        expected-=logsumexp(logprior-np.asarray(values))
    np.testing.assert_allclose(problem.statistics(p)['NLL'],expected,atol=1e-8)


@pytest.mark.parametrize('shared',[[True,False],[False,True],[False,False]])
def test_partial_density_matches_source_then_target_factorization(shared):
    from audit_ds23_partial_clock_controls import independent_joint_NLL
    problem,p=partial(shared)
    expected=independent_joint_NLL(problem,p[:-1],np.exp(p[-1]))
    np.testing.assert_allclose(problem.statistics(p)['NLL'],expected,atol=1e-8)
