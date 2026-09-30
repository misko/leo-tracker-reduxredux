import numpy as np
from residual_constellation import plane_stats


def test_shared_planes_are_distinguished_from_frame_mismatch():
    rng = np.random.default_rng(128)
    a = rng.normal(size=(30, 20, 6)) + 1j * rng.normal(size=(30, 20, 6))
    result = plane_stats(a, a)
    for r in result.values():
        assert np.isclose(r["correlation"], 1)
        assert r["centered_sign_agreement"] == 1
        assert 0.45 < r["control_sign_mean"] < 0.55


def test_coordinate_bias_is_removed_before_plane_comparison():
    rng = np.random.default_rng(13)
    a = rng.normal(size=(30, 20, 6)) + 1j * rng.normal(size=(30, 20, 6))
    b = rng.normal(size=(30, 20, 6)) + 1j * rng.normal(size=(30, 20, 6))
    offset = 100 * (rng.normal(size=(20, 6)) + 1j * rng.normal(size=(20, 6)))
    base, biased = plane_stats(a, b), plane_stats(a + offset, b + offset)
    for key in base:
        assert np.isclose(base[key]["correlation"], biased[key]["correlation"])
        assert base[key]["centered_sign_agreement"] == biased[key]["centered_sign_agreement"]
