import numpy as np
import pytest
from cluster_tracks import (
    hellinger_features,
    mean_bit_features,
    normalized_phase_features,
    phase_distribution,
)
from scipy.spatial.distance import pdist


def test_phase_distribution_balances_regions_and_ignores_amplitude():
    rng = np.random.default_rng(5)
    z = np.exp(1j * rng.uniform(-3, 3, (2, 300, 4)))
    a = phase_distribution(z)
    assert np.allclose(a.reshape(4, 16).sum(axis=1), 0.25)
    assert np.allclose(a, phase_distribution(9 * z[::-1]))
    with pytest.raises(ValueError):
        phase_distribution(z[:, :5])


def test_hellinger_endpoints_and_validation():
    x = hellinger_features([[1, 0], [0, 1], [1, 0]])
    assert np.allclose(pdist(x), [1, 0, 1])
    with pytest.raises(ValueError):
        hellinger_features([[1, 1]])


def test_profile_normalization_has_expected_geometry():
    rng = np.random.default_rng(77)
    p = rng.normal(size=(4, 6, 4)) + 1j * rng.normal(size=(4, 6, 4))
    x = normalized_phase_features(p)
    assert np.allclose(np.linalg.norm(x, axis=1), 1)
    assert np.allclose(x.mean(axis=1), 0)


def test_real_axis_noise_does_not_cross_histogram_boundary():
    z = np.ones((2, 300, 4), complex)
    z[1] *= -1
    assert np.array_equal(
        phase_distribution(z * np.exp(1j * 0.001)), phase_distribution(z * np.exp(-1j * 0.001))
    )


def test_singleton_bit_distance_and_unknown_exclusion():
    x = mean_bit_features([[1, 0], [0, 1]], ["0" * 60, "1" + "0" * 59])
    assert np.allclose(pdist(x), np.sqrt(1 / 60))
    with pytest.raises(ValueError):
        mean_bit_features([[1]], ["?" * 60])
