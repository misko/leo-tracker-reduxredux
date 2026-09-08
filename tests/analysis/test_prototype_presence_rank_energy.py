import numpy as np
import pytest

from tools.prototype_presence_rank_energy import projection_norms, select


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_projection_norms_zero_constant_and_exact_amplitude_scaling(rate):
    iq = np.full((6 * rate // 50, 2), 32767, dtype=np.int16)
    np.testing.assert_array_equal(projection_norms(iq, rate), np.zeros((2, 6)))
    rng = np.random.default_rng(99123)
    iq = rng.integers(-100, 100, size=iq.shape, dtype=np.int16)
    norms = projection_norms(iq, rate)
    np.testing.assert_allclose(projection_norms(iq * 2, rate), norms * 4, rtol=1e-12)
    assert (norms > 0).all()


def test_zero_exponent_preserves_normalized_ranking_and_ties():
    norms = np.ones((2, 6))
    scores = np.array([[1, 2, 1, 1, 1, 1], [1, 1, 3, 1, 1, 1]])
    assert select(scores, norms, 0) == 2
    norms[0, 4] = 10
    assert select(scores, norms, 1) == 4
    assert select(scores, norms, 0) == 2
    assert select(np.zeros((2, 6)), norms, 1) == 0
    with pytest.raises(ValueError):
        select(scores, norms, 0.25)
