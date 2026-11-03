import numpy as np
import pytest

from ds23_radio_calibration_factor import condition_unit_gaussian,radio_difference_design,principal_radio_contrast
from leo.analysis.research.retained_track_likelihood import PERIOD


def cost(y,cov):
    return float(y@np.linalg.solve(cov,y)+np.linalg.slogdet(cov)[1]+len(y)*np.log(2*np.pi))


def test_relative_carrier_branch_is_invariant_to_pilot_alias():
    raw=669896.3340425736
    expected=-11921.8477756082
    for k in range(-4,5):
        assert principal_radio_contrast(raw+k*PERIOD)==pytest.approx(expected,abs=1e-8)
    assert principal_radio_contrast(PERIOD/2)==pytest.approx(-PERIOD/2)
    with pytest.raises(ValueError):principal_radio_contrast(np.nan)


def test_conditional_prior_preserves_exact_joint_gaussian_evidence():
    d=np.array([[1.,-1.,.2],[.1,.3,1.]])
    z=np.array([2.,-.5]);sigma=np.array([.3,.8])
    a=np.array([[.5,1.,-.2],[1.,-.7,.8]])
    y=np.array([.7,1.1]);noise=np.array([.4,.6])
    result=condition_unit_gaussian(d,z,sigma)
    conditional=cost(y-a@result['mean'],np.diag(noise**2)+a@result['covariance']@a.T)
    combined=np.vstack((d,a))
    joint=cost(np.r_[z,y],combined@combined.T+np.diag(np.r_[sigma**2,noise**2]))
    assert conditional+result['negative_twice_log_density']==pytest.approx(joint,abs=1e-10)
    np.testing.assert_allclose(result['transform']@result['transform'].T,result['covariance'],atol=1e-12)
    np.testing.assert_allclose(result['inverse_transform']@result['transform'],np.eye(3),atol=1e-12)


def test_a_differential_measurement_does_not_constrain_common_mode():
    result=condition_unit_gaussian(np.array([[-1.,1.]]),np.array([2.]),np.array([.1]))
    common=np.array([1.,1.])/np.sqrt(2)
    assert common@result['covariance']@common==pytest.approx(1.)
    assert common@result['mean']==pytest.approx(0.,abs=1e-12)


def test_radio_contrast_cancels_shared_RF_term_and_has_no_orbit_or_fragment_columns():
    # 9 hardware + 4 smooth + 2 phase + 3 orbital + 2 constants + 1 radio event.
    width,event_start=21,20
    row=radio_difference_design(width,9,4,event_start,[dict(kind='receiver',receiver=1,time_s=100.,sigma_hz=300.)],
        np.array([200.]),np.array([2]),np.array([11.5e9]),np.array([[.2,-.3]]))[0]
    assert row[0]==pytest.approx(-PERIOD/np.sqrt(12))
    assert row[2]==pytest.approx(PERIOD/np.sqrt(12))
    assert row[4]==-500. and row[6]==500.
    assert row[5]==25. and row[7]==-25.
    assert row[8]==0.
    np.testing.assert_allclose(row[9:13],[-40.,60.,40.,-60.])
    np.testing.assert_array_equal(row[13:20],np.zeros(7))
    assert row[20]==-300.


def test_weak_or_zero_design_restores_the_original_prior():
    result=condition_unit_gaussian(np.zeros((1,3)),np.array([2.]),np.array([.3]))
    np.testing.assert_array_equal(result['mean'],np.zeros(3))
    np.testing.assert_array_equal(result['covariance'],np.eye(3))
    with pytest.raises(ValueError):condition_unit_gaussian(np.zeros((1,3)),np.array([2.]),np.array([0.]))
