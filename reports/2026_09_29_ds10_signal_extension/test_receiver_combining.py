import numpy as np
from receiver_combining import apply, fit_combiner, measure


def test_combiner_downweights_noisy_receiver_on_heldout_samples():
    rng = np.random.default_rng(278)
    signs = rng.choice([-1., 1.], size=(20, 100, 3))
    values = signs[..., None] + rng.normal(size=(*signs.shape, 2)) * [0.2, 2.]
    offset, weights = fit_combiner(values[:10], signs[:10])
    result = apply(values[10:], offset, weights)
    assert measure(result, signs[10:])["errors"] < measure(
        values[10:].mean(axis=-1), signs[10:])["errors"]
    assert np.all(weights[:, 0] > weights[:, 1])
