import numpy as np

from ds23_joint_component_refinement import JointComponentWorkspace
from ds23_smooth_component_workspace import SmoothComponentWorkspace,periodic_template_spline


def workspace():
    rng=np.random.default_rng(7801);n=50000
    fits=[dict(CFO_hz=12000.,offset_samples=.12,modulation_ppm=2.),
          dict(CFO_hz=-28000.,offset_samples=-.17,modulation_ppm=-3.)]
    base=JointComponentWorkspace(rng.normal(size=n)+1j*rng.normal(size=n),2.5e6,'upper',[100.,800.],fits)
    return base,SmoothComponentWorkspace.from_workspace(base)


def test_smooth_view_preserves_original_data_and_support():
    base,p=workspace()
    assert p.y is base.y and p.segments is base.segments and p.start is base.start
    assert type(base) is JointComponentWorkspace
    original,_=base.columns_and_derivatives(base.start[:3],0)
    smooth,_=p.columns_and_derivatives(p.start[:3],0)
    assert np.linalg.norm(smooth-original)/np.linalg.norm(original)<.002


def test_cubic_template_and_derivative_are_periodic():
    spline=periodic_template_spline(2.5e6,'upper');period=spline.x[-1]
    x=np.array([.1,10.2,1234.56])
    np.testing.assert_allclose(spline(x),spline(x+period),atol=1e-9)
    np.testing.assert_allclose(spline(x,1),spline(x+period,1),atol=1e-9)


def test_smoothed_physical_derivatives_match_finite_differences():
    _,p=workspace();parameters=p.start[:3].copy()
    _,analytic=p.columns_and_derivatives(parameters,0)
    for k in range(3):
        step=1e-5;delta=np.zeros(3);delta[k]=step*p.scale[k]
        a,_=p.columns_and_derivatives(parameters+delta,0)
        b,_=p.columns_and_derivatives(parameters-delta,0)
        np.testing.assert_allclose((a-b)/(2*step),analytic[:,:,k],rtol=2e-4,atol=2e-5)
