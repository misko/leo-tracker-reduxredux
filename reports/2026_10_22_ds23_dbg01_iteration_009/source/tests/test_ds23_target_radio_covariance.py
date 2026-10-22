import numpy as np

from ds23_target_radio_covariance import deterministic_checks,innovation_noise_screen
from ds23_radio_correlation import whitener,correlation


def test_colored_covariance_whitening_uses_the_full_native_heteroscedastic_matrix():
    t=np.array([0.,.3,1.2,4.]);sigma=np.array([20.,30.,40.,25.]);w,_=whitener(t,sigma,.9,30.)
    c=correlation(t,.9,30.)*sigma[:,None]*sigma[None,:]
    np.testing.assert_allclose(w@c@w.T,np.eye(len(t)),atol=1e-12)


def test_covariance_gate_cannot_hide_raw_deterministic_trends_or_steps():
    valid=dict(mean_z=0.,slope_z=0.,quadratic_bic_gain=-3.,maximum_step_z=1.,lag1_acf=.9)
    assert deterministic_checks(valid)
    for key,value in [('mean_z',3.1),('slope_z',3.1),('quadratic_bic_gain',10.1),('maximum_step_z',4.1)]:
        assert not deterministic_checks(dict(valid,**{key:value}))


def test_standardized_innovation_mean_is_checked_in_dimensionless_noise_units():
    t=np.linspace(0,30,77);r=.6+.1*np.sin(t)
    screen=innovation_noise_screen(r,t)
    assert screen['mean_z']>5 and not screen['noise_screen_pass']
    assert abs(screen['mean_z']-abs(r.mean())*np.sqrt(len(t)))<1e-10
