import numpy as np
import pytest

from leo.analysis.localization_candidate_derivatives import (
    candidate_set_derivatives,
    profile_offset_jacobian,
)
from leo.analysis.localization_candidate_set import candidate_set_log_ratio


def test_exact_gradient_and_responsibilities():
    y, mu = np.array([.1, .4, .7]), np.array([.2, .8])
    kwargs = dict(period=1., scale=.07, signal_probability=.6)
    value, gradient, responsibilities = candidate_set_derivatives(y, mu, **kwargs)
    numerical = []
    for direction in np.eye(2)*1e-6:
        numerical.append((candidate_set_log_ratio(y, mu+direction, **kwargs)
                          -candidate_set_log_ratio(y, mu-direction, **kwargs))/2e-6)
    np.testing.assert_allclose(gradient, numerical, rtol=1e-8, atol=1e-9)
    assert responsibilities.sum() == pytest.approx(1-.4/np.exp(value))
    assert 0 <= responsibilities.sum() <= 1


def test_alias_invariance_and_null_model():
    kwargs = dict(period=1., scale=.03)
    a = candidate_set_derivatives([.12, .54], [.2, .6], **kwargs)
    b = candidate_set_derivatives([2.12, -2.46], [-2.8, 4.6], **kwargs)
    np.testing.assert_allclose(a[1], b[1], atol=1e-11)
    np.testing.assert_allclose(a[2], b[2], atol=1e-11)
    assert np.all(candidate_set_derivatives([.1], [.2], signal_probability=0, **kwargs)[1] == 0)
    assert candidate_set_derivatives([], [.2], **kwargs)[1].shape == (1,)


def test_profiled_offset_chain_rule_removes_common_shift():
    j = np.array([[1., 0.], [1., 2.], [1., 3.], [1., 4.]])
    expected = np.array([[0., 1.5], [0., 2.5]])
    np.testing.assert_allclose(profile_offset_jacobian(j, 2, [.25, .75]), expected)
    with pytest.raises(ValueError):
        profile_offset_jacobian(j, 2, [.2, .2])
