import numpy as np
from fit_visits import select_fit

def test_unwraps_known_multiturn_nonlinear_phase_without_using_B():
    x=np.linspace(0,.12,73);truth=5*np.sin(4*np.pi*x/.12)+110*x
    observed=np.angle(np.exp(1j*(truth+np.random.default_rng(922).normal(0,.07,len(x)))))
    best,curves,_,_=select_fit(x,observed)
    assert best.startswith('spline_')
    error=np.angle(np.exp(1j*(curves[best]-truth)))
    assert np.sqrt(np.mean(error**2))<.2

def test_prefers_linear_for_exact_constant_frequency():
    x=np.linspace(0,.12,73);phase=.6+240*x
    best,curves,_,_=select_fit(x,np.angle(np.exp(1j*phase)))
    assert best=='linear'
    assert max(abs(curves[best]-phase))<1e-10
