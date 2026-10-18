import numpy as np
import pytest

from leo.analysis.research.family_switch_likelihood import family_residuals


def test_receiver_prior_is_unchanged_and_inconsistent_data_and_phase_are_bounded_together():
    # Last coordinate is a receiver prior; the first block contains both the
    # data and the shared phase residual for one satellite hypothesis.
    raw = np.array([10.0, 20.0, 0.3, 0.4, 2.0])
    result, info = family_residuals(raw, [[0, 1], [2, 3]], [50, 50], cap_per_point=4)
    assert result[-1] == raw[-1]
    assert result[:2] @ result[:2] == pytest.approx(200 * 500 / (200 + 500))
    assert info[0]["influence_weight"] < info[1]["influence_weight"]
    np.testing.assert_array_equal(raw, [10, 20, 0.3, 0.4, 2])


def test_evidence_and_derivative_have_no_jump_at_a_clutter_scale():
    def loss(x):
        r, _ = family_residuals(np.array([x]), [[0]], [50], cap_per_point=4)
        return r @ r

    centre = np.sqrt(200)
    h = 1e-4
    left = (loss(centre) - loss(centre - h)) / h
    right = (loss(centre + h) - loss(centre)) / h
    assert left == pytest.approx(right, rel=1e-4)
    assert loss(10000) < 200


def test_family_correlation_does_not_create_multiple_independent_orbit_votes():
    a, _ = family_residuals(np.array([1.0, 1.0]), [[0, 1]], [2], cap_per_point=None)
    b, _ = family_residuals(np.ones(10), [list(range(10))], [10], cap_per_point=None)
    assert a @ a == pytest.approx(b @ b)
    with pytest.raises(ValueError, match="disjoint"):
        family_residuals(np.ones(3), [[0, 1], [1, 2]], [2, 2])
