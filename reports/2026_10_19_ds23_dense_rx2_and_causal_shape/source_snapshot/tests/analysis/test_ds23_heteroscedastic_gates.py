import numpy as np
from ds23_heteroscedastic_gates import noise_screen
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def test_equal_75Hz_noise_reproduces_every_legacy_structure_statistic():
    rng=np.random.default_rng(44);t=np.sort(rng.uniform(0,100,60));r=rng.normal(0,120,len(t))+.2*t
    a=batch_noise_screen(r[None],t);b=noise_screen(r,t,np.full(len(t),75.))
    for key in a:np.testing.assert_allclose(a[key][0],b[key],rtol=1e-10,atol=1e-10)


def test_heterogeneous_zero_mean_noise_has_lower_false_rejection_than_unweighted_test():
    rng=np.random.default_rng(80);t=np.arange(50.);sigma=np.r_[np.full(5,150.),np.full(45,10.)]
    r=rng.normal(size=(400,50))*sigma
    legacy=~batch_noise_screen(r,t)['noise_screen_pass']
    corrected=[not noise_screen(row,t,sigma)['noise_screen_pass'] for row in r]
    assert np.mean(corrected)<.05 and np.mean(legacy)>np.mean(corrected)+.1


def test_weighted_gate_still_rejects_a_real_slope_or_discontinuity():
    t=np.arange(50.);sigma=np.r_[np.full(5,150.),np.full(45,10.)]
    assert not noise_screen(4*(t-t.mean()),t,sigma)['noise_screen_pass']
    assert not noise_screen(np.where(t<25,-80,80),t,sigma)['noise_screen_pass']
