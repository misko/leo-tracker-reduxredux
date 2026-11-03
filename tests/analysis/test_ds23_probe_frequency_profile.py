from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_probe_frequency_profile import curvature_contrast,frequency_only_fit,effective_times
from ds23_joint_component_refinement import JointComponentWorkspace


def test_unequal_effective_times_do_not_create_curvature_for_affine_carriers():
    t=np.array([[.003,.004],[.009,.011],[.016,.017]])
    f=np.array([10000.,-20000.])+t*np.array([2000.,-3000.])
    result=curvature_contrast(t,f,np.broadcast_to(np.eye(2)*4,(3,2,2)))
    np.testing.assert_allclose(result['non_affine_CFO_contrast_hz'],np.zeros(2),atol=1e-11)


def test_joint_local_covariance_is_retained_in_common_and_differential_contrasts():
    t=np.array([[0.,0.],[1.,1.],[2.,2.]])
    f=np.array([[0.,0.],[40.,40.],[0.,0.]])
    covariance=np.broadcast_to(np.array([[4.,3.],[3.,4.]]),(3,2,2))
    result=curvature_contrast(t,f,covariance)
    assert result['common_contrast_hz']==pytest.approx(40.)
    assert result['common_sigma_proxy_hz']==pytest.approx(np.sqrt(1.5*3.5))
    assert result['differential_contrast_hz']==pytest.approx(0.)


def test_repeated_or_reversed_effective_times_are_not_silently_used():
    with pytest.raises(ValueError):curvature_contrast(np.ones((3,2)),np.ones((3,2)),np.broadcast_to(np.eye(2),(3,2,2)))


def test_frequency_profile_recovers_injected_carriers_with_independent_frame_phases():
    rng=np.random.default_rng(69);n=50000;fs=2.5e6
    fits=[dict(CFO_hz=25000.,offset_samples=.1,modulation_ppm=2.),dict(CFO_hz=-35000.,offset_samples=-.1,modulation_ppm=-2.)]
    p=JointComponentWorkspace(rng.normal(size=n)+1j*rng.normal(size=n),fs,'upper',[120.,900.],fits)
    truth=p.start.copy();truth[[0,3]]+=[83.,-67.]
    (a,_),(b,_)=[p.columns_and_derivatives(v,k) for k,v in enumerate(truth.reshape(2,3))]
    for ix in p.segments:
        coef=(rng.normal(size=17)+1j*rng.normal(size=17))*12
        p.y[ix]+=np.column_stack((a[ix],b[ix],np.ones(len(ix))))@coef
    result=frequency_only_fit(p,p.start)
    np.testing.assert_allclose(result['CFO_hz'],truth[[0,3]],atol=2.)
    assert np.linalg.eigvalsh(result['covariance_hz2']).min()>0
    t=effective_times(p,result['parameters'])['effective_time_s']
    assert np.all((t>p.t.min())&(t<p.t.max()))
