import numpy as np
import pytest

from leo.analysis.localization_candidate_set import candidate_set_log_ratio, wrapped_cauchy_pdf


def test_wrapped_density_normalization_and_alias_invariance():
    grid = (np.arange(8192)+.5)/8192
    for scale in [.005, .1, 10.]:
        assert np.mean(wrapped_cauchy_pdf(grid, 1., scale)) == pytest.approx(1., abs=1e-12)
    x = np.array([.01, .4, -.2])
    np.testing.assert_allclose(wrapped_cauchy_pdf(x+np.array([2., -3., 5.]), 1., .03),
                               wrapped_cauchy_pdf(x, 1., .03), rtol=1e-12)


def test_two_candidate_joint_density_normalizes():
    grid = (np.arange(128)+.5)/128
    density = np.array([[np.exp(candidate_set_log_ratio(
        [a, b], [.2, .7], period=1., scale=.1)) for b in grid] for a in grid])
    assert density.mean() == pytest.approx(1., abs=1e-12)


def test_permutations_null_model_and_invalid_input():
    kwargs = dict(period=1., scale=.1)
    assert candidate_set_log_ratio([.1, .5], [.2, .6], **kwargs) == pytest.approx(
        candidate_set_log_ratio([.5, .1], [.6, .2], **kwargs))
    assert candidate_set_log_ratio([], [.2], **kwargs) == 0
    assert candidate_set_log_ratio([.2], [], **kwargs) == 0
    assert candidate_set_log_ratio([.2], [.2], signal_probability=0, **kwargs) == 0
    with pytest.raises(ValueError):
        candidate_set_log_ratio([.2], [.2], period=0, scale=1)
