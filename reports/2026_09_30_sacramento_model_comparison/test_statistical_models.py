import numpy as np
import pytest

from statistical_models import (
    conditional_held_logpdf,
    constant_contrasts,
    doppler_information,
    exponential_covariance,
    normalized_information_weights,
    normalized_profile_logpdf,
)


def test_profile_density_is_normalized_and_constant_invariant():
    residual = np.array([2.0, -1.0, 4.0, 0.5])
    covariance = exponential_covariance(np.array([0.0, 0.5, 2.0, 3.0]))
    contrast = constant_contrasts(4)
    projected = contrast @ residual
    projected_covariance = contrast @ covariance @ contrast.T
    sign, logdet = np.linalg.slogdet(projected_covariance)
    expected = -0.5 * (
        3 * np.log(2 * np.pi)
        + logdet
        + projected @ np.linalg.solve(projected_covariance, projected)
    )
    assert sign == 1
    assert normalized_profile_logpdf(residual, covariance) == pytest.approx(expected)
    assert normalized_profile_logpdf(residual + 1234.0, covariance) == pytest.approx(expected)


def test_held_score_is_train_only_and_accounts_for_offset_uncertainty():
    covariance = np.eye(4) * 4.0
    first = conditional_held_logpdf(np.array([9.0, 11.0]), np.array([10.0, 12.0]), covariance)
    changed = conditional_held_logpdf(np.array([9.0, 11.0]), np.array([-100.0, 500.0]), covariance)
    assert first.offset_hz == pytest.approx(10.0)
    assert changed.offset_hz == pytest.approx(first.offset_hz)
    assert first.mean_hz.tolist() == pytest.approx([10.0, 10.0])
    assert np.diag(first.covariance_hz2).tolist() == pytest.approx([6.0, 6.0])
    assert first.log_density > changed.log_density


def test_information_recovers_linear_jacobian_and_profiles_constant():
    design = np.array([[1.0, 2.0], [1.0, -1.0], [1.0, 0.0], [1.0, 3.0]])

    def predictor(position):
        return design @ position + 8.0

    result = doppler_information(predictor, np.array([3.0, -2.0]), np.eye(4), step_km=1e-3)
    assert result.jacobian_hz_per_km == pytest.approx(design)
    assert result.rank == 1
    # The first position column is exactly the profiled constant nuisance.
    assert result.profiled_information[0, 0] == pytest.approx(0.0, abs=1e-9)


def test_information_weights_normalize_and_reject_unidentifiable_set():
    def informative(scale):
        return doppler_information(
            lambda p: scale * np.array([p[0], p[1], -p[0], -p[1]]),
            np.zeros(2),
            np.eye(4),
        )

    weights = normalized_information_weights([informative(1.0), informative(2.0)])
    assert weights.sum() == pytest.approx(1.0)
    assert weights[1] > weights[0]
    flat = doppler_information(lambda p: np.ones(4), np.zeros(2), np.eye(4))
    with pytest.raises(ValueError):
        normalized_information_weights([flat])
