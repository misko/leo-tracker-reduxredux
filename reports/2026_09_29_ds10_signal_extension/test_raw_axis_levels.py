import numpy as np
from raw_axis_levels import assess


def test_unequal_binary_population_survives_scalar_normalization():
    rng = np.random.default_rng(651)
    values = rng.choice([-1., 1.], size=(40, 28), p=[.2, .8])
    values += rng.normal(size=values.shape) * .15
    result = assess(values[:20], values[20:])
    assert result["delta_from_gaussian"] > .5
    assert np.allclose(result["centers"], [-1, 1], atol=.1)
