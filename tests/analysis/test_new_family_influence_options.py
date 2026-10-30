from diagnose_new_family_influence import family_options


def test_diagnostic_uses_trial_quadrature_and_uncertainty_options():
    p=dict(phase_step_s=.025,uncalibrated_label=True,family_prior=dict(phase_limit_s=20.,integrate_receiver_uncertainty=False))
    v=family_options(p)
    assert v==dict(phase_step=.025,allow_uncalibrated_label=True,phase_limit_s=20.,integrate_receiver_uncertainty=False,integrate_orbit_uncertainty=True)
