from prepare_candidates import effective

def test_noise_comparison_uses_effective_policy_not_inactive_proxy():
    noise=dict(extra_parameter_BIC_gain=-2.,constant_radio_sigma_hz=110.,per_observation_noise_sigma_hz={'x':50.})
    assert effective(noise,['x'])=={'x':110.}
    noise['extra_parameter_BIC_gain']=1.
    assert effective(noise,['x'])=={'x':50.}
