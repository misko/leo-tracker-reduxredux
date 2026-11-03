import numpy as np
from ds23_joint_component_refinement import JointComponentWorkspace
from ds23_chirped_component_workspace import ChirpedComponentWorkspace
from ds23_smooth_component_workspace import SmoothComponentWorkspace


def workspace():
    rng=np.random.default_rng(8042);n=50000
    fits=[dict(CFO_hz=12000.,offset_samples=.12,modulation_ppm=2.),
          dict(CFO_hz=-28000.,offset_samples=-.17,modulation_ppm=-3.)]
    base=JointComponentWorkspace(rng.normal(size=n)+1j*rng.normal(size=n),2.5e6,'upper',[100.,800.],fits)
    return base,ChirpedComponentWorkspace.from_workspace(base)


def test_zero_rates_reproduce_the_same_smooth_waveform_and_score():
    base,p=workspace();s=SmoothComponentWorkspace.from_workspace(base)
    assert p.y is base.y and len(base.start)==6
    for k in [0,1]:
        a,_=s.columns_and_derivatives(base.start[3*k:3*k+3],k);b,_=p.component_columns(p.start,k)
        np.testing.assert_array_equal(a,b)
    assert p.statistics(p.start)['squared_error']==s.statistics(s.start)['squared_error']


def test_chirped_profile_gradient_matches_independent_finite_differences():
    _,p=workspace();x=p.start.copy();x[6:]=[2300.,-1700.]
    analytic=p.statistics(x,0)['gradient_score'];finite=[]
    for k in range(8):
        delta=np.zeros(8);delta[k]=p.scale[k]*1e-5
        finite.append((p.statistics(x+delta,0)['score']-p.statistics(x-delta,0)['score'])/2e-5)
    np.testing.assert_allclose(analytic,finite,rtol=5e-4,atol=1e-7)


def test_noiseless_chirps_recover_the_instantaneous_midpoint_carriers():
    _,p=workspace();rng=np.random.default_rng(641);truth=p.start.copy();truth[6:]=[4200.,-3100.]
    a,_=p.component_columns(truth,0);b,_=p.component_columns(truth,1);p.y=np.zeros_like(p.y)
    for ix in p.segments:
        c=rng.normal(size=17)+1j*rng.normal(size=17)
        p.y[ix]=np.column_stack((a[ix],b[ix],np.ones(len(ix))))@c
    fit=p.fit(p.start)
    assert not fit['boundary']
    np.testing.assert_allclose(np.asarray(fit['parameters'])[[0,3]],truth[[0,3]],atol=.01)
    np.testing.assert_allclose(np.asarray(fit['parameters'])[6:],truth[6:],atol=2.)
