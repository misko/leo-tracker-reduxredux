import numpy as np
import pytest

from ds23_fft_bias_diagnostic import polynomial_press,interpolation_bias,native_correction,active_curvature


def response():
    actual=np.linspace(-250,250,1001)
    return dict(step_hz=500.,actual_offset_hz=actual,reported_offset_hz=actual-15*np.sin(2*np.pi*actual/500))


def test_press_equals_independent_deleted_point_fits():
    t=np.linspace(0,50,30);y=10000+30*t+.8*t*t+np.random.default_rng(31).normal(0,25,len(t))
    got=polynomial_press(t,y,2)
    for k in (0,7,17,29):
        use=np.arange(len(t))!=k
        fitted=np.polynomial.Polynomial.fit(t[use],y[use],2)
        assert got['prediction'][k]==pytest.approx(fitted(t[k]),abs=1e-8)
        changed=y.copy();changed[k]+=3000
        assert polynomial_press(t,changed,2)['prediction'][k]==pytest.approx(got['prediction'][k],abs=1e-8)


def test_native_response_must_not_be_evaluated_after_graph_alias_lifting():
    curve=response();native=100123.;period=1/4.4e-6
    bias=interpolation_bias(native,curve)
    assert abs(bias)>10
    # The pilot alias is NOT an integer number of 500 Hz FFT bins.
    assert abs(interpolation_bias(native+period,curve)-bias)>5
    graph=native+3*period
    restored=graph+(native-graph)
    assert interpolation_bias(restored,curve)==pytest.approx(bias,abs=1e-8)


def test_monotonic_response_inverse_and_exact_bins():
    curve=response();truth=np.array([-200123.,-100000.,100031.,200087.])
    reported=truth+interpolation_bias(truth,curve)
    np.testing.assert_allclose(reported+native_correction(reported,curve),truth,atol=1e-7)
    np.testing.assert_allclose(native_correction([-100000.,0,100000.],curve),0,atol=1e-10)
    with pytest.raises(ValueError):polynomial_press(np.ones(10),np.arange(10),2)


def test_curvature_requires_active_signal_not_only_degree_label():
    t=np.linspace(0,60,60)
    assert not active_curvature(t,100*t)
    assert active_curvature(t,100*t+5*(t-30)**2)
