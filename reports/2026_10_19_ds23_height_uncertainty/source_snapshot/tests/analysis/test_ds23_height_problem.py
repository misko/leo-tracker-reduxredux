from types import SimpleNamespace
import numpy as np
from ds23_height_problem import geometry_features,height_column,make_height_problem
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal,integrated_gaussian


def example():
    t=np.linspace(-30,330,31);position=[];velocity=[]
    for offset,speed in ((-.3,.0011),(.7,-.0009)):
        a=offset+speed*t
        position.append(np.column_stack((6900*np.cos(a),5000*np.sin(a),4500*np.sin(a))))
        velocity.append(np.column_stack((-6900*speed*np.sin(a),5000*speed*np.cos(a),4500*speed*np.cos(a))))
    sky=dict(time_s=t,position_km=np.array(position),velocity_km_s=np.array(velocity))
    mode=np.zeros((6,len(t),3));v=np.zeros_like(mode)
    for k in range(6):mode[k,:,k%3]=.1
    n=24;labels=np.repeat([0,1],n//2);times=np.tile(np.linspace(0,300,n//2),2)
    hardware=np.zeros((n,8));hardware[np.arange(n),labels]=1000
    constants=np.column_stack((labels==0,labels==1))*1000
    return SimpleNamespace(sky=sky,flat_times=times,flat_labels=labels,reference=np.array([.2,-.4]),
        labels=[0,1],supported=[0,1],supported_local=[0,1],phase_sigma=np.array([1.2,2.1]),
        q=np.linspace(.94,1.04,n),hardware=hardware,smooth=np.zeros((n,2)),constants=constants,
        mode_bank=dict(time_s=t,position_km=mode,velocity_km_s=v),variant='radio_noise',
        sigma=100.,values=np.linspace(-1000,1000,n),point_noise=np.full(n,100.),
        noise_groups=labels,keep=np.ones(n,bool),members=[0,1])


def test_zero_altitude_geometry_matches_existing_physics_at_two_regional_positions():
    p=example()
    for x in (np.zeros(2),np.array([7.,-4.])):
        expected=JointMarginal.calculate(p,x);actual=geometry_features(p,x,0)
        for key in ('features','frequency','intercept','derivative','elevation'):
            np.testing.assert_allclose(actual[key],expected[key],rtol=1e-12,atol=1e-12)


def test_height_derivative_includes_orbit_correction_and_matches_smaller_physical_step():
    p=example();x=np.array([4.,-3.]);orbit=np.arange(6)*.7
    actual=height_column(p,x,200.,orbit)
    begin=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)
    values=[]
    for h in (200.05,199.95):
        g=geometry_features(p,x,h);values.append(p.q*g['frequency']+g['features'][:,begin:begin+6]@orbit)
    np.testing.assert_allclose(actual,(values[0]-values[1])/.1,rtol=5e-6,atol=2e-9)


def test_unused_zero_height_gaussian_integrates_to_one_with_student_phase_priors(monkeypatch):
    import ds23_height_problem as module
    p=example();monkeypatch.setattr(module,'precision_problem',lambda *a,**k:p)
    powers=np.array([1.,.6]);mu=np.array([.1,-.1]);model=dict(nu=3.)
    g=geometry_features(p,np.zeros(2),0);features=g['features'];start=10;width=features.shape[1]
    mean=np.zeros(width);mean[start:start+2]=mu/p.phase_sigma
    groups=np.full(width,-1,int);groups[start:start+2]=[0,1];scale=np.ones(width);scale[-2:]=.3
    expected=hierarchical_bound(p.values-p.q*g['intercept']-features@mean,features*scale,
        p.point_noise,p.noise_groups,powers=powers,prior_groups=groups,prior_nu=3.)
    actual=make_height_problem(None,None,p.keep,'c0',p.reference,powers,mu,model,{},0).calculate(np.zeros(2))
    np.testing.assert_allclose(actual['negative_twice_elbo'],expected['negative_twice_elbo'],rtol=1e-12,atol=1e-9)
    expected_coefficient=expected['coefficient']*scale+mean
    np.testing.assert_allclose(np.delete(actual['coefficient'],p.height_index),expected_coefficient,rtol=1e-11,atol=1e-9)
    assert actual['height_posterior_mean_m']==0


def test_known_position_height_signal_has_correct_sign_scale_and_gaussian_shrinkage():
    p=example();x=np.zeros(2);height=350.
    base=geometry_features(p,x,0);truth=geometry_features(p,x,height)
    observed=p.q*(truth['frequency']-base['frequency'])
    derivative=height_column(p,x,0,np.zeros(6))
    posterior=integrated_gaussian(observed,derivative[:,None]*1000,.01)
    estimate=1000*posterior['coefficient'][0]
    assert abs(estimate-height)<.5
    narrow=integrated_gaussian(observed,derivative[:,None],.01)
    assert abs(narrow['coefficient'][0])<abs(estimate)
