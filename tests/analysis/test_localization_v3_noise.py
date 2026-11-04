import numpy as np
import pytest

from leo.analysis.localization_v3.noise import estimate_noise, fit_variance


def test_no_curvature_uses_original_noise_fallback_for_every_observation():
    observations = [dict(observation_id='a', fractional_margin=.5)]
    value = estimate_noise([], observations)
    assert value['constant_radio_sigma_hz'] == 150.
    assert value['noise_samples'] == 0
    assert value['per_observation_noise_sigma_hz'] == {'a': 150.}


def test_curved_polynomial_noise_uses_all_original_observation_ids():
    rng = np.random.default_rng(812)
    t = np.linspace(0, 60, 121)
    y = 1000 + 4*t*t + rng.normal(0, 100, len(t))
    ids = [str(i) for i in range(len(t))]
    track = dict(times=t, values=y, observation_ids=ids,
                  pieces=[dict(start_s=0., end_s=60., degree=2)])
    result = estimate_noise([track], [dict(observation_id=oid, fractional_margin=.5)
                                     for oid in ids])
    assert result['noise_samples'] == len(t)
    assert set(result['per_observation_noise_sigma_hz']) == set(ids)
    assert all(40 <= s <= 600 for s in result['per_observation_noise_sigma_hz'].values())


@pytest.mark.parametrize(('margin', 'square'), [([0.], [1.]), ([1.], [-1.]),
                                               ([float('nan')], [1.]), ([], [])])
def test_invalid_variance_observations_fail_explicitly(margin, square):
    with pytest.raises(ValueError):
        fit_variance(margin, square)
