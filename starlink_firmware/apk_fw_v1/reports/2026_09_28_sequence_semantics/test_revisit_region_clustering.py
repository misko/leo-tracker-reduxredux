import numpy as np
import pytest
from revisit_region_clustering import phase_profile, profile_geometry


def test_profile_ignores_frame_order_and_positive_amplitude():
    rng = np.random.default_rng(2)
    z = rng.normal(size=(30, 6, 8)) + 1j * rng.normal(size=(30, 6, 8))
    assert np.allclose(phase_profile(z), phase_profile(z[::-1] * 7))


def test_correlations_and_metric_distances():
    rng = np.random.default_rng(3)
    p = rng.normal(size=(4, 6, 8)) + 1j * rng.normal(size=(4, 6, 8))
    c, d = profile_geometry(p)
    assert np.allclose(np.diag(c), 1)
    assert np.allclose(np.diag(d), 0)
    assert np.allclose(d**2, 2 * (1 - c), atol=1e-12)
    for j in range(4):
        assert np.all(d <= d[:, j, None] + d[None, j, :] + 1e-12)


def test_constant_profile_rejected():
    with pytest.raises(ValueError):
        profile_geometry(np.zeros((2, 6, 8), complex))
