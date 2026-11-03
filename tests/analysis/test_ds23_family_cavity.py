import numpy as np
from ds23_family_cavity import coarse_phase_scores,unused_student_gap,predictive_density_reference,legacy_phase_reference,directional_orbit_frequency_reference
from dsx01_hierarchical_bound import hierarchical_bound


def test_coarse_predictive_scores_match_dense_shared_covariance_and_aliases():
    rng=np.random.default_rng(240);n=12;k=4
    u=rng.normal(size=(n,3));cov=np.eye(n)*25+u@u.T*50
    f=rng.normal(size=(k,n))*20;d=rng.normal(size=(k,n))*10;sd=np.array([.3,.7,1.,2.])
    y=rng.normal(size=n)*30;r=np.zeros(n);g=np.repeat([0,1],6)
    result=coarse_phase_scores(y,r,f,d,sd,cov,g)
    for j in range(k):
        raw=y-f[j]+result['aliases'][j,g]/4.4e-6
        matrix=cov+np.outer(d[j],d[j])*sd[j]**2
        expected=raw@np.linalg.solve(matrix,raw)+np.linalg.slogdet(matrix)[1]+n*np.log(2*np.pi)
        assert abs(result['score'][j]-expected)<1e-8


def test_unused_student_coordinate_correction_matches_independent_bound_difference():
    x=np.arange(10);y=np.sin(x);u=np.ones((10,1));g=np.zeros(10,int)
    a=hierarchical_bound(y,u,np.ones(10),g,prior_groups=np.array([-1]),prior_nu=4.)
    b=hierarchical_bound(y,np.pad(u,((0,0),(0,1))),np.ones(10),g,prior_groups=np.array([-1,0]),prior_nu=4.)
    assert abs(b['negative_twice_elbo']-a['negative_twice_elbo']-unused_student_gap(4.))<1e-8
    assert unused_student_gap(None)==0


def test_SVD_density_reference_matches_dense_correlated_covariance():
    rng=np.random.default_rng(405);u=rng.normal(size=(260,5));b=rng.normal(size=(5,5));c=b@b.T+np.eye(5)
    raw=rng.normal(size=260);sigma=np.linspace(.5,1.5,260)
    actual,method=predictive_density_reference(raw,u,c,sigma)
    matrix=np.diag(sigma**2)+u@c@u.T
    expected=raw@np.linalg.solve(matrix,raw)+np.linalg.slogdet(matrix)[1]+len(raw)*np.log(2*np.pi)
    assert method=='economy_SVD' and abs(actual-expected)<1e-9


def test_legacy_reference_replay_excludes_final_posterior_phase():
    history=[dict(fit=dict(parameters=[k])) for k in [1.,2.,3.,4.,5.]];calls=[]
    def posterior(reference,parameters):
        calls.append(float(parameters[0]));return reference/2+parameters[0]
    result=legacy_phase_reference(history,np.zeros(1),posterior)
    assert calls==[1.,2.,3.,4.]
    np.testing.assert_array_equal(result,[6.125])


def test_extrapolated_orbit_reference_handles_large_modes_without_tolerance_relaxation():
    from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
    knots=np.arange(-20.,321.,5);p=np.array([-2400.,-4700.,4300.])[None,:]+knots[:,None]*[2.,-3.,.5]
    bank=dict(time_s=knots,position_km=p[None],velocity_km_s=np.broadcast_to([2.,-3.,.5],(1,*p.shape)).copy())
    dp=np.broadcast_to([4000.,2000.,-1000.],(3,*p.shape)).copy();dp[1:]*=.002
    modes=dict(time_s=knots,position_km=dp,velocity_km_s=np.broadcast_to([.001,-.002,.003],dp.shape).copy())
    t=np.array([3.,70.,180.,180.]);coef=np.array([.003,-3.5,19.5]);phase=1.375
    expected=paired_frequency_modes(bank,modes,t,np.zeros(len(t),int),np.array([phase]),37.906,-122.545)@coef
    actual,convergence=directional_orbit_frequency_reference(bank,modes,coef,t,phase,37.906,-122.545)
    assert convergence<2e-5
    np.testing.assert_allclose(actual,expected,atol=2e-5,rtol=0)
