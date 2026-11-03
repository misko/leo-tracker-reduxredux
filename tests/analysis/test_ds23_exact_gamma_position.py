from pathlib import Path
import sys
import numpy as np
import pytest
from scipy.special import gammaln

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_exact_gamma_position import gaussian_blocks,linear_schur,integrate
from probe_ds23_marginal_evidence import gaussian_integral,gamma_logratio


def test_batched_curved_integration_matches_existing_scalar_oracle_draw_by_draw():
    rng=np.random.default_rng(12);u=rng.normal(size=(19,5));y=rng.normal(size=19);s=np.ones(19)*1.7;g=np.arange(19)%3;p=np.array([.2,.6,1.])
    noise=np.array([.9,1.2,.6]);phase_indices=np.array([1,3]);phase_mean=np.array([1.3,.9]);nu=4.;n=41;seed=2026
    value=integrate(gaussian_blocks(y,u,s,g,p),noise,phase_indices,phase_mean,nu,samples=n,seed=seed,batch=7)
    random=np.random.default_rng(seed);shape=2+p*np.bincount(g)/2;rate=shape/noise
    tau=random.gamma(shape,1.,size=(n,len(p)))/rate
    pshape=np.full(2,(nu+1)/2);prate=pshape/phase_mean;ph=random.gamma(pshape,1.,size=(n,2))/prate
    ratio=gamma_logratio(tau,2.,2.,shape,rate)+gamma_logratio(ph,nu/2,(nu-2)/2,pshape,prate)
    expected=[]
    for k in range(n):
        precision=np.ones(5);precision[phase_indices]=ph[k]
        expected.append(-.5*gaussian_integral(y,u,s,g,p,tau[k],precision)+ratio[k])
    np.testing.assert_allclose(value['curved_log_importance_weights'],expected,rtol=1e-12,atol=1e-11)


def test_linear_schur_matches_dense_augmented_gaussian_integral():
    rng=np.random.default_rng(20);u=rng.normal(size=(15,4));y=rng.normal(size=15)*40;s=np.ones(15)*50;g=np.arange(15)%3
    schur=linear_schur(y,u,s,g);prior=np.array([1.,2.,.7,1.3]);root=np.linalg.cholesky(np.diag(prior)+schur['matrix'])
    coeff=np.linalg.solve(root.T,np.linalg.solve(root,schur['rhs']))
    reduced=schur['squared']-schur['rhs']@coeff+2*np.log(np.diag(root)).sum()-np.log(prior).sum()+schur['normalization']
    bias=np.eye(3)[g]*300;direct=gaussian_integral(y,np.column_stack((u,bias)),s,np.zeros(len(y),int),np.ones(1),np.ones(1),np.r_[prior,np.ones(3)])
    assert reduced==pytest.approx(direct,rel=1e-12,abs=1e-11)


def test_exact_noise_gamma_proposal_has_constant_weights_and_analytic_evidence():
    y=np.array([1.,-2.,.7]);s=np.array([2.,1.,1.5]);p=np.array([.6]);b=gaussian_blocks(y,np.empty((3,0)),s,np.zeros(3,int),p)
    alpha=2+.6*3/2;beta=2+.6*np.sum((y/s)**2)/2
    result=integrate(b,np.array([alpha/beta]),np.array([],int),np.array([]),None,samples=128,seed=12)
    expected=b['normalization']-2*(gammaln(alpha)-gammaln(2)+2*np.log(2)-alpha*np.log(beta))
    assert result['joint']['negative_twice_log_evidence']==pytest.approx(expected,abs=1e-12)
    assert result['joint']['effective_samples']==pytest.approx(128.)


def test_linear_observations_cannot_change_curved_calibration_moments():
    rng=np.random.default_rng(96);u=rng.normal(size=(30,3));y=rng.normal(size=30);s=np.ones(30);g=np.arange(30)%2
    b=gaussian_blocks(y,u,s,g,np.ones(2));args=(b,np.ones(2),np.array([1]),np.array([1.]),4.)
    a=integrate(*args,samples=128,seed=2)
    linear=linear_schur(np.ones(10)*100,np.ones((10,3)),np.ones(10),np.zeros(10,int))
    c=integrate(*args,linear=linear,samples=128,seed=2)
    np.testing.assert_array_equal(a['curved_log_importance_weights'],c['curved_log_importance_weights'])
    np.testing.assert_array_equal(a['curved_coefficient_mean'],c['curved_coefficient_mean'])
    assert c['joint']['negative_twice_log_evidence']!=a['joint']['negative_twice_log_evidence']


def test_curved_and_linear_joint_weights_match_full_augmented_gaussian_oracle():
    rng=np.random.default_rng(52);uc=rng.normal(size=(13,4));yc=rng.normal(size=13)*10;sc=np.ones(13)*3;gc=np.arange(13)%2;p=np.array([.2,.6])
    ul=rng.normal(size=(9,4));yl=rng.normal(size=9)*10;sl=np.ones(9)*5;gl=np.arange(9)%3
    n=19;seed=90;noise=np.array([.8,1.3]);phase_indices=np.array([2]);phase_mean=np.array([1.7]);nu=3.
    result=integrate(gaussian_blocks(yc,uc,sc,gc,p),noise,phase_indices,phase_mean,nu,
        linear=linear_schur(yl,ul,sl,gl),samples=n,seed=seed,batch=4)
    random=np.random.default_rng(seed);shape=2+p*np.bincount(gc)/2;rate=shape/noise
    tau=random.gamma(shape,1.,size=(n,2))/rate;pshape=np.full(1,(nu+1)/2);prate=pshape/phase_mean
    ph=random.gamma(pshape,1.,size=(n,1))/prate
    ratio=gamma_logratio(tau,2.,2.,shape,rate)+gamma_logratio(ph,nu/2,(nu-2)/2,pshape,prate)
    u=np.block([[uc,np.zeros((13,3))],[ul,np.eye(3)[gl]*300]])
    y,s,g=np.r_[yc,yl],np.r_[sc,sl],np.r_[gc,np.full(9,2)]
    expected=[]
    for k in range(n):
        precision=np.ones(7);precision[phase_indices]=ph[k]
        expected.append(-.5*gaussian_integral(y,u,s,g,np.r_[p,1.],np.r_[tau[k],1.],precision)+ratio[k])
    np.testing.assert_allclose(result['joint_log_importance_weights'],expected,rtol=1e-11,atol=1e-10)
