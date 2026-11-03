import numpy as np
from probe_native_fft_bias import response_curve,debias


def test_template_response_is_odd_and_does_not_shift_exact_bins():
    curve=response_curve(2500000,'lower')
    np.testing.assert_allclose(curve['reported_offset_hz'],-curve['reported_offset_hz'][::-1],atol=1e-10)
    np.testing.assert_allclose(debias([-150000,0,150000],curve),[-150000,0,150000],atol=1e-12)


def test_template_predicts_observed_central_bin_attraction_without_fitting_native_data():
    curve=response_curve(2500000,'lower');actual=np.array(curve['actual_offset_hz']);reported=np.array(curve['reported_offset_hz'])
    estimate=np.interp(123,actual,reported)
    assert 95<estimate<110  # the characteristic bias has the observed scale
    assert abs(float(debias(estimate,curve))-123)<1e-8
