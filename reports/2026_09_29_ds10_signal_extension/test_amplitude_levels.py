import numpy as np
from amplitude_levels import fit_levels, gaussian


def test_shared_binary_levels_beat_continuous_model_on_new_samples():
    rng = np.random.default_rng(381)
    x = rng.choice([-1., 1.], size=(1600, 1)) + rng.normal(size=(1600, 2)) * .2
    _, ll = fit_levels(x[:800], x[800:], 2)
    assert ll.mean() > gaussian(x[:800], x[800:]).mean() + .5


def test_continuous_shared_variation_is_not_binary():
    rng = np.random.default_rng(912)
    x = rng.normal(size=(4000, 1)) + rng.normal(size=(4000, 2)) * .3
    _, ll = fit_levels(x[:2000], x[2000:], 2)
    assert ll.mean() < gaussian(x[:2000], x[2000:]).mean() - .1
