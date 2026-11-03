import numpy as np
from scipy.linalg import null_space
from scipy.special import logsumexp
from numpy.polynomial.hermite import hermgauss

from ds23_joint_receiver_iq import conditional_frame_density
from ds23_shared_receiver_phase import frame_statistics, phase_NLL, fit_phase_sigma


def test_zero_shared_phase_reproduces_source_only_IQ_prediction():
    rng = np.random.default_rng(218)
    bs = rng.normal(size=(18, 2))+1j*rng.normal(size=(18, 2))
    bt = rng.normal(size=(23, 2))+1j*rng.normal(size=(23, 2))
    a = rng.normal(size=18)+1j*rng.normal(size=18)
    b = rng.normal(size=23)+1j*rng.normal(size=23)
    stats = frame_statistics(a,b,bs,bt,.3,.5)
    expected = conditional_frame_density(a,b,bs,bt,.3,.5)['NLL']
    np.testing.assert_allclose(phase_NLL(stats,0.), expected, atol=1e-9)


def test_phase_marginal_matches_dense_unwrapped_gaussian_quadrature():
    rng = np.random.default_rng(913)
    bs = rng.normal(size=(12,2))+1j*rng.normal(size=(12,2))
    bt = rng.normal(size=(15,2))+1j*rng.normal(size=(15,2))
    a = rng.normal(size=12)+1j*rng.normal(size=12)
    b = rng.normal(size=15)+1j*rng.normal(size=15)
    stats = frame_statistics(a,b,bs,bt,.7,1.5)
    x = np.column_stack((bs,np.ones(len(bs))))
    c = np.linalg.lstsq(x,a,rcond=None)[0]
    covariance = .7*np.linalg.inv(x.conj().T@x)[:2,:2]
    q = null_space(np.ones((1,len(b))))
    v = q.conj().T@(1.5*np.eye(len(b))+bt@covariance@bt.conj().T)@q
    mean = q.conj().T@(bt@c[:2]);y=q.conj().T@b
    nodes,weights=hermgauss(96);sigma=.4;loss=[]
    for phi in np.sqrt(2)*sigma*nodes:
        residual=y-np.exp(1j*phi)*mean
        loss.append(float(np.vdot(residual,np.linalg.solve(v,residual)).real+np.linalg.slogdet(v)[1]+len(y)*np.log(np.pi)))
    expected=-logsumexp(np.log(weights/np.sqrt(np.pi))-loss)
    np.testing.assert_allclose(phase_NLL(stats,sigma),expected,atol=1e-8)


def test_shared_frame_phase_variance_is_learned_without_TX_phase_continuity():
    rng=np.random.default_rng(412)
    basis=(rng.normal(size=(32,2))+1j*rng.normal(size=(32,2)))/2
    frames=[]
    phases=rng.normal(0,.4,48)
    for phi in phases:
        gain=np.exp(1j*rng.uniform(-np.pi,np.pi,2))
        noise=lambda:.03*(rng.normal(size=32)+1j*rng.normal(size=32))/np.sqrt(2)
        source=basis@gain+noise();target=np.exp(1j*phi)*basis@gain+noise()
        frames.append(frame_statistics(source,target,basis,basis,.03**2,.03**2))
    fit=fit_phase_sigma(frames[:32])
    assert fit['converged'] and .25<fit['sigma_rad']<.6
    gain=sum(phase_NLL(s,0.)-phase_NLL(s,fit['sigma_rad']) for s in frames[32:])
    assert gain>100
