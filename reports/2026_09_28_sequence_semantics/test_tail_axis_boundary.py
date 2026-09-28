import numpy as np
from tail_axis_boundary import first_axis_window


def test_boundary_ignores_signs_and_tracks_error_allowance():
    rng = np.random.default_rng(17)
    values = np.r_[np.full(317, 1j), np.ones(600)].astype(complex)
    signs = rng.choice([-1, 1], size=values.size)
    for allowed in (0, 1, 2):
        assert first_axis_window(values, allowed_errors=allowed) == 317 - allowed
        assert first_axis_window(values * signs, allowed_errors=allowed) == 317 - allowed


def test_no_axis_region_returns_none():
    assert first_axis_window(np.full(1000, 1j)) is None
