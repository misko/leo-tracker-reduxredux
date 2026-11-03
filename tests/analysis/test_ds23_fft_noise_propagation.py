import numpy as np
import pytest

from ds23_fft_noise_propagation import inverse_noise_scale
from ds23_fft_grid_origin import correction


def test_noise_scale_is_derivative_of_same_inverse_map():
    x=np.linspace(-250,250,1001)
    response=dict(step_hz=500,actual_offset_hz=x,reported_offset_hz=x+15*np.sin(2*np.pi*x/500))
    f=np.array([-100123.1,-37123.4,128341.7]);epsilon=1e-4
    derivative=1+(correction(f+epsilon,response,312.5)-correction(f-epsilon,response,312.5))/(2*epsilon)
    scale=inverse_noise_scale(f,response,312.5)
    np.testing.assert_allclose(scale,derivative,atol=2e-7)
    assert (scale>0).all()


def test_linear_response_propagates_variance_and_standardized_residual():
    x=np.array([-250.,0.,250.]);r=dict(step_hz=500,actual_offset_hz=x,reported_offset_hz=.8*x)
    assert inverse_noise_scale(12.,r,0)==pytest.approx(1.25)
    observed,predicted,sigma=12.,10.,3.
    corrected=observed+correction(observed,r,0)
    assert (corrected-predicted)/float(inverse_noise_scale(observed,r,0)*sigma)==pytest.approx((observed-.8*predicted)/sigma)


def test_uncertainty_adapter_preserves_existing_noise_floor(monkeypatch):
    from types import SimpleNamespace
    import probe_ds23_fft_grid_uncertainty_floor as adapter
    changed=SimpleNamespace(fixed_window_noise=dict(per_observation_noise_sigma_hz={'a':25.,'b':40.,'c':75.}))
    monkeypatch.setattr(adapter,'original_correct',lambda *args:(changed,{}))
    result,receipt=adapter.corrected_scan(None,'unused',{})
    assert result.fixed_window_noise['per_observation_noise_sigma_hz']=={'a':40.,'b':40.,'c':75.}
    assert receipt['points_reaching_existing_floor']==1
