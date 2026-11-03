import numpy as np
import pytest
from scipy.integrate import quad
from scipy.stats import t,norm
from scipy.optimize import minimize
from scipy.special import gammaln

from ds23_skew_bound import skew_bound,positive_second_moment
from ds23_skew_phase_prior import density_cost,side_scales
from dsx01_hierarchical_bound import hierarchical_bound


def test_zero_skew_is_an_exact_original_bound_control():
    rng=np.random.default_rng(29401);u=rng.normal(size=(24,4));y=rng.normal(size=24)
    prior=np.array([-1,0,-1,1]);groups=np.repeat([0,1],12)
    expected=hierarchical_bound(y,u,np.ones(24),groups,prior_groups=prior,prior_nu=3.)
    result=skew_bound(y,u,np.ones(24),groups,[1,3],3.,0.)
    assert result['negative_twice_elbo']==expected['negative_twice_elbo']
    np.testing.assert_array_equal(result['coefficient'],expected['coefficient'])


def test_small_nonzero_skew_converges_to_original_normalized_multivariate_bound():
    rng=np.random.default_rng(28410);u=rng.normal(size=(24,4));y=rng.normal(size=24)
    groups=np.repeat([0,1,2],8);power=np.array([.4,.7,1.])
    prior=np.array([-1,0,-1,1])
    expected=hierarchical_bound(y,u,np.ones(24),groups,powers=power,prior_groups=prior,prior_nu=3.)
    result=skew_bound(y,u,np.ones(24),groups,[1,3],3.,1e-8,powers=power)
    assert abs(result['negative_twice_elbo']-expected['negative_twice_elbo'])<1e-5
    np.testing.assert_allclose(result['coefficient'],expected['coefficient'],atol=1e-5,rtol=0)


@pytest.mark.parametrize('mean,variance',[(0.,1.),(-2.,.3),(1.2,2.)])
def test_truncated_gaussian_moment_matches_numerical_integration(mean,variance):
    exact=quad(lambda x:x*x*norm.pdf(x,mean,np.sqrt(variance)),0,np.inf)[0]
    assert abs(positive_second_moment(mean,variance)-exact)<1e-9


@pytest.mark.parametrize('nu,kappa,observed',[(3.,.35,1.1),(8.,-.3,-.8),(None,.25,.5)])
def test_one_coordinate_ELBO_is_below_exact_evidence_and_variationally_stationary(nu,kappa,observed):
    sigma=.5
    result=skew_bound([observed],[[1.]],[sigma],[0],[0],nu,kappa,iterations=512)
    prior=lambda x:float(np.exp(-.5*density_cost(x,1.,1.,nu,kappa)))
    integral=quad(lambda x:t.pdf((observed-x)/sigma,4)/sigma*prior(x),-np.inf,0,epsabs=1e-10)[0]
    integral+=quad(lambda x:t.pdf((observed-x)/sigma,4)/sigma*prior(x),0,np.inf,epsabs=1e-10)[0]
    assert result['negative_twice_elbo']>=-2*np.log(integral)-1e-7
    left,right,_=side_scales(kappa,nu)
    def direct(coordinates):
        m,logv=coordinates;v=np.exp(logv);positive=positive_second_moment(m,v)
        energy=(m*m+v-positive)/left**2+positive/right**2
        noise_rate=2.+.5*((observed-m)**2+v)/sigma**2
        noise=np.log(2*np.pi*sigma*sigma)+2*gammaln(2.)-2*gammaln(2.5)+np.log(2.)+5*np.log(noise_rate/2.)
        if nu is not None:
            a,b=nu/2,(nu-2)/2;p=a+.5
            phase=2*np.log((left+right)/2)+2*gammaln(a)-2*gammaln(p)-2*a*np.log(b)+2*p*np.log(b+energy/2)
        else:phase=energy+2*np.log((left+right)/2)
        return float(noise+phase-1-logv)
    point=[result['coefficient'][0],np.log(result['gaussian_covariance'][0,0])]
    assert abs(direct(point)-result['negative_twice_elbo'])<1e-7
    optimum=minimize(direct,point,method='BFGS')
    assert direct(point)-optimum.fun<1e-6
    assert result['final_log_precision_change']<1e-4


def test_correlated_phase_covariance_and_fractional_powers_are_variationally_stationary():
    u=np.array([[1.,.4],[-.3,1.],[.5,1.2],[1.4,-.6]])
    y=np.array([.7,-.1,1.1,1.3]);g=np.array([0,0,1,1]);power=np.array([.5,1.]);sigma=.7;nu=3.;kappa=.3
    result=skew_bound(y,u,np.full(4,sigma),g,[0,1],nu,kappa,powers=power,iterations=512)
    left,right,_=side_scales(kappa,nu);root=np.linalg.cholesky(result['gaussian_covariance'])
    initial=np.r_[result['coefficient'],np.log(root[0,0]),root[1,0],np.log(root[1,1])]
    def direct(parameters):
        mean=parameters[:2];l=np.array([[np.exp(parameters[2]),0.],[parameters[3],np.exp(parameters[4])]])
        covariance=l@l.T;variance=np.diag(covariance)
        expected=(y-u@mean)**2+np.einsum('ij,jk,ik->i',u,covariance,u)
        noise=0.
        for group in range(2):
            use=g==group;a=2+power[group]*use.sum()/2;rate=2+power[group]*expected[use].sum()/(2*sigma*sigma)
            noise+=power[group]*use.sum()*np.log(2*np.pi*sigma*sigma)+2*gammaln(2)-2*gammaln(a)+power[group]*use.sum()*np.log(2)+2*a*np.log(rate/2)
        positive=positive_second_moment(mean,variance)
        energy=(mean*mean+variance-positive)/left**2+positive/right**2
        a,b=nu/2,(nu-2)/2;p=a+.5
        phase=np.sum(2*np.log((left+right)/2)+2*gammaln(a)-2*gammaln(p)-2*a*np.log(b)+2*p*np.log(b+energy/2))
        return float(noise+phase-2-np.linalg.slogdet(covariance)[1])
    assert abs(direct(initial)-result['negative_twice_elbo'])<1e-7
    optimized=minimize(direct,initial,method='BFGS')
    assert direct(initial)-optimized.fun<1e-6
