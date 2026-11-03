import numpy as np
from ds23_fragment_offset_diagnostics import contrast_summary


def test_shared_calibration_uncertainty_cancels_in_receiver_difference():
    covariance=np.ones((4,4))*100+np.eye(4)*4
    mean=np.array([10.,12.,-10.,-12.])
    average=contrast_summary(mean,covariance,[0,1])
    difference=contrast_summary(mean,covariance,[0,1],[2,3])
    assert average['mean_hz']==11 and difference['mean_hz']==22
    np.testing.assert_allclose(average['conditional_SD_hz']**2,102.)
    np.testing.assert_allclose(difference['conditional_SD_hz']**2,4.)


def test_point_weights_keep_cross_fragment_covariance():
    r=contrast_summary([0.,10.],[[9.,3.],[3.,4.]],[0,1],weights=[1.,3.])
    assert r['mean_hz']==7.5
    np.testing.assert_allclose(r['conditional_SD_hz']**2,np.array([.25,.75])@np.array([[9.,3.],[3.,4.]])@np.array([.25,.75]))
