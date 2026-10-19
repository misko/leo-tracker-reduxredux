import numpy as np
from ds23_family_screen import screen_family
from ds23_precision_diagnostics import compare_screens
from dsx01_joint_marginal import integrated_gaussian
from leo.analysis.research.retained_track_likelihood import PERIOD


def test_shared_family_screen_matches_dense_gaussian_integration_with_heterogeneous_noise():
    rng=np.random.default_rng(97);curves=[];widths=np.array([1.5,.7])
    for n in [17,23]:
        y=rng.normal(0,40,n);f=rng.normal(0,20,(2,n));d=rng.normal(0,10,(2,n));sigma=rng.uniform(8,40,n)
        curves.append(dict(observed=y,predicted=f,derivative=d,sigma=sigma,power=.6,visible=[True,True]))
    result=screen_family(curves,widths)
    for j in range(2):
        y=np.concatenate([c['observed']-c['predicted'][j] for c in curves]);noise=np.concatenate([c['sigma']/np.sqrt(.6) for c in curves])
        features=np.zeros((len(y),3));begin=0
        for k,c in enumerate(curves):
            end=begin+len(c['observed']);features[begin:end,0]=c['derivative'][j]*widths[j]
            features[begin:end,k+1]=300;begin=end
        expected=integrated_gaussian(y,features,noise)
        assert abs(result['cost'][j]-(expected['quadratic']+expected['logvolume']))<1e-9


def test_shared_phase_cannot_independently_explain_opposing_family_tracks():
    t=np.linspace(-2,2,30);curves=[]
    for sign in [1,-1]:
        curves.append(dict(observed=sign*20*t,predicted=np.zeros((1,30)),derivative=t[None]*20,
            sigma=np.ones(30)*3,power=1.,visible=[True]))
    opposite=screen_family(curves,[2])['cost'][0]
    curves[1]['observed']*=-1
    same=screen_family(curves,[2])['cost'][0]
    assert opposite>1000 and same<50


def test_aliases_preserve_equivalent_measurements_and_visibility_excludes_candidate():
    c=dict(observed=np.arange(12.)+2*PERIOD,predicted=np.arange(12.)[None],derivative=np.ones((1,12)),
           sigma=np.ones(12)*10,power=1.,visible=[True])
    a=screen_family([c],[1]);assert a['aliases'][0][0]==-2
    c['observed']-=2*PERIOD;b=screen_family([c],[1])
    assert abs(a['cost'][0]-b['cost'][0])<1e-8
    c['visible']=[False];assert np.isinf(screen_family([c],[1])['cost'][0])


def test_precision_scaling_exposes_small_linear_structure_hidden_by_75Hz_floor():
    t=np.linspace(0,15,16);r=np.linspace(-10,10,16)
    d=compare_screens(r,t,np.ones(16)*2)
    assert d['legacy']['noise_screen_pass']
    assert not d['RF_scaled']['noise_screen_pass']
    assert d['RF_scaled']['slope_z']>3


def test_cross_RF_clock_covariance_preserves_marginals_without_mixing_families():
    from probe_ds23_cross_rf_constants import cross_rf_correlation
    c=cross_rf_correlation([1,1,2],[10.,12.,11.],.9)
    np.testing.assert_allclose(c,[[1,.75,0],[.75,1,0],[0,0,1]])
    np.testing.assert_allclose(cross_rf_correlation([1,1],[10.,12.],0),np.eye(2))
    assert np.linalg.eigvalsh(c).min()>0
