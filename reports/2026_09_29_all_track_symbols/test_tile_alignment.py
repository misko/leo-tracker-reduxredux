import numpy as np
from tile_alignment import agreement, compare, fit


def test_shift_and_phase_transfer_to_independent_frame():
    rng = np.random.default_rng(21)
    a = rng.normal(size=(2, 90, 8)) + 1j * rng.normal(size=(2, 90, 8))
    b = np.zeros_like(a)
    b[:, 1:, 1:] = a[:, :-1, :-1] * np.exp(0.7j)
    dt, df, rotation, score = fit(a[0], b[0], 2, 16)
    assert (dt, df) == (1, 1)
    assert np.isclose(score, 1)
    assert np.isclose((compare(a[1], b[1], 2, 16, dt, df) * rotation).real, 1)
    assert np.isclose((compare(a[1], b[1], 18, 16, dt, df) * rotation).real, 1)


def test_discovery_search_does_not_create_held_similarity():
    rng = np.random.default_rng(3)
    held = []
    discovery = []
    for _ in range(100):
        a = rng.normal(size=(2, 90, 8)) + 1j * rng.normal(size=(2, 90, 8))
        b = rng.normal(size=(2, 90, 8)) + 1j * rng.normal(size=(2, 90, 8))
        dt, df, rotation, score = fit(a[0], b[0], 2, 16)
        discovery.append(score)
        held.append((compare(a[1], b[1], 2, 16, dt, df) * rotation).real)
    assert np.mean(discovery) > 0.1
    assert abs(np.mean(held)) < 0.03


def test_adjusted_rand_label_invariance():
    assert agreement([0, 0, 1, 1], [8, 8, 3, 3]) == 1
    assert np.isclose(agreement([0, 0, 1, 1], [0, 1, 0, 1]), -0.5)
