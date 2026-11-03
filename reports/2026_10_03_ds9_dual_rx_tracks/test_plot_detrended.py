import numpy as np
from plot_detrended import prediction


def test_reference_time_and_channel_offsets():
    model=dict(channel_intercepts_hz_at_150s={'1':100.,'2':200.},slope_hz_s_at_150s=2.,quadratic_coefficient_hz_s2=0.)
    np.testing.assert_allclose(prediction(model,[140,150,160],[1,2,1]),[80,200,120])


def test_quadratic_difference_does_not_remove_curvature():
    line=dict(channel_intercepts_hz_at_150s={'1':100.},slope_hz_s_at_150s=2.,quadratic_coefficient_hz_s2=0.)
    curved=dict(line,quadratic_coefficient_hz_s2=.1)
    t=np.array([140,150,160]);ch=np.ones(3)
    np.testing.assert_allclose(prediction(curved,t,ch)-prediction(line,t,ch),[10,0,10])
