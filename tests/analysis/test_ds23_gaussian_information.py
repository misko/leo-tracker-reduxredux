import numpy as np
import pytest
from scipy.integrate import quad
from scipy.special import gammaln,digamma
from scipy.stats import t,norm

from ds23_gaussian_information import gaussian_factor_bound,greedy_phase_design
from dsx01_hierarchical_bound import hierarchical_bound


def test_disabled_factors_are_bitwise_the_original_robust_bound():
    rng=np.random.default_rng(49);y=rng.normal(size=12);u=rng.normal(size=(12,4));g=np.repeat([0,1],6)
    kw=dict(prior_groups=np.array([-1,0,1,-1]),powers=[.7,1.],prior_nu=3.)
    old=hierarchical_bound(y,u,1.2,g,**kw)
    new=gaussian_factor_bound(y,u,1.2,g,[],np.empty((0,4)),[],**kw)
    for key in old:np.testing.assert_array_equal(new[key],old[key])


def test_independent_gaussian_factor_matches_exact_dense_conditioning():
    rng=np.random.default_rng(50);y=rng.normal(size=9);u=np.zeros((9,3));g=np.zeros(9,int)
    z=np.array([1.,-.5]);d=rng.normal(size=(2,3));s=np.array([.1,.4])
    old=hierarchical_bound(y,u,.8,g)
    new=gaussian_factor_bound(y,u,.8,g,z,d,s)
    covariance=np.linalg.inv(np.eye(3)+(d/s[:,None]).T@(d/s[:,None]))
    np.testing.assert_allclose(new['coefficient'],covariance@(d.T@(z/s**2)),atol=1e-12)
    np.testing.assert_allclose(new['coefficient_covariance'],covariance,atol=1e-12)
    marginal=np.diag(s*s)+d@d.T
    exact=float(z@np.linalg.solve(marginal,z)+np.linalg.slogdet(marginal)[1]+2*np.log(2*np.pi))
    assert abs(new['negative_twice_elbo']-old['negative_twice_elbo']-exact)<1e-9


def test_student_prior_survives_a_fixed_gaussian_measurement():
    y=np.array([.2,-.4]);u=np.zeros((2,1));g=np.zeros(2,int)
    result=gaussian_factor_bound(y,u,1.,g,[2.],[[1.]],[.15],prior_groups=[0],prior_nu=3.,iterations=1024)
    old=hierarchical_bound(y,np.zeros((2,0)),1.,g)
    density=quad(lambda x:t.pdf(x,3,scale=np.sqrt(1/3))*norm.pdf(2.,loc=x,scale=.15),-20,20,epsabs=1e-12)[0]
    exact=-2*np.log(density)
    assert result['negative_twice_elbo']-old['negative_twice_elbo']>=exact-1e-8
    assert result['negative_twice_elbo']-old['negative_twice_elbo']<exact+.05
    assert len(result['prior_group_precision'])==1
    assert abs(result['coefficient'][0]-2.)<.08


def test_normalized_ELBO_replays_from_independent_expected_log_densities():
    rng=np.random.default_rng(51);y=rng.normal(size=9);u=rng.normal(size=(9,3));g=np.repeat([0,1,2],3)
    s=np.linspace(.5,1.5,9);power=np.array([1.,.8,.6]);z=[.8];d=np.array([[0.,1.,0.]]);sf=.2
    r=gaussian_factor_bound(y,u,s,g,z,d,[sf],prior_groups=[-1,0,-1],prior_nu=3.,powers=power,iterations=2048)
    mu,cov=r['coefficient'],r['coefficient_covariance'];a,b=r['noise_shape'],r['noise_rate']
    pa,pb=r['prior_shape'],r['prior_rate'];weight=a/b;elog=digamma(a)-np.log(b)
    energy=(y-u@mu)**2+np.einsum('ij,jk,ik->i',u,cov,u)
    cost=np.sum(power[g]*(np.log(2*np.pi*s*s)-elog[g]+weight[g]*energy/s**2))
    cost+=np.log(2*np.pi*sf*sf)+((z-d@mu)**2+(d@cov@d.T).diagonal()).sum()/sf**2
    p=np.array([1.,pa[0]/pb[0],1.]);plog=np.array([0.,digamma(pa[0])-np.log(pb[0]),0.])
    cost+=3*np.log(2*np.pi)-plog.sum()+p@(mu**2+np.diag(cov))
    cost-=3*(1+np.log(2*np.pi))+np.linalg.slogdet(cov)[1]
    def twice_kl(a,b,a0,b0):
        return 2*((a-a0)*digamma(a)-gammaln(a)+gammaln(a0)+a0*np.log(b/b0)+a*(b0/b-1)).sum()
    cost+=twice_kl(a,b,2.,2.)+twice_kl(pa,pb,1.5,.5)
    # The fixed-point residual is bounded by the original 1e-5 tolerance.
    assert abs(float(cost)-r['negative_twice_elbo'])<1e-7


def test_greedy_design_matches_dense_information_updates():
    rng=np.random.default_rng(52);a=rng.normal(size=(8,8));c=np.linalg.inv(a.T@a+np.eye(8))
    result=greedy_phase_design(c,np.arange(2,8),.2,3)
    precision=np.linalg.inv(c)
    for k in result['coordinates']:precision[k,k]+=25.
    np.testing.assert_allclose(result['covariance'],np.linalg.inv(precision),atol=1e-12)
    assert all(r['trace_after_km2']<=r['trace_before_km2'] for r in result['history'])


@pytest.mark.parametrize('sigma,budget',[(0.,1),(.2,-1),(np.nan,1)])
def test_invalid_phase_design_rejected(sigma,budget):
    with pytest.raises(ValueError):greedy_phase_design(np.eye(3),np.array([2]),sigma,budget)


def test_absolute_phase_factor_keeps_the_original_mean_and_variance(monkeypatch):
    from types import SimpleNamespace
    import ds23_phase_measurement_design as module
    def fake_problem(*args):
        return SimpleNamespace(hardware=np.zeros((3,1)),smooth=np.zeros((3,1)),labels=[5,7],
            supported=[],members=[0],phase_sigma=np.array([2.,3.]),values=np.zeros(3),q=np.ones(3),
            noise_groups=np.zeros(3,int),point_noise=np.full(3,40.))
    monkeypatch.setattr(module,'make_event_problem',fake_problem)
    monkeypatch.setattr(module.JointMarginal,'calculate',lambda *args:dict(features=np.zeros((3,5)),intercept=np.zeros(3)))
    for reference in ([0.,0.],[8.,-5.]):
        p=module.make_phase_measured_problem(None,None,np.ones(3,bool),'c0',reference,np.ones(1),
            np.array([1.,-2.]),dict(nu=None),[dict(candidate_index=5,phase_s=4.,sigma_s=.2)])
        c=p.calculate(np.zeros(2));mean=2*c['coefficient'][2]
        variance=4*np.linalg.inv(c['calibration_posterior_precision'])[2,2]
        expected_variance=1/(1/4+1/.04);expected_mean=expected_variance*(1/4+4/.04)
        assert abs(mean-expected_mean)<1e-12 and abs(variance-expected_variance)<1e-12


def test_measurement_selection_uses_covariance_and_support_only():
    from ds23_phase_measurement_design import choose_labels
    covariance=np.eye(5);covariance[0,2]=covariance[2,0]=.5
    covariance[1,4]=covariance[4,1]=.7
    design=dict(covariance=covariance,phase_coordinates=[2,3,4],phase_label_indices=[0,1,2],
        phase_coordinate_begin=2,curved_point_counts=[12,1000,20])
    assert choose_labels(design,.1,1)['label_indices']==[2]
    assert choose_labels(design,.1,1,'point_count')['label_indices']==[1]
    assert choose_labels(design,.1,2,'random',123)==choose_labels(design,.1,2,'random',123)
