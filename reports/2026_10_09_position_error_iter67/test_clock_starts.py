import numpy as np
from clock_starts import clock_starts, pair_residuals, singleton_pairs


def test_pairing_excludes_ambiguous_and_unmatched_groups():
    times = [0, 0.0001, 1, 1, 1, 2, 3, 3]
    rf = [10, 10, 10, 10, 10, 10, 10, 11]
    receivers = [1, 0, 0, 1, 1, 0, 0, 1]
    np.testing.assert_array_equal(singleton_pairs(times, rf, receivers), [[1, 0]])


def test_pair_residual_cancels_shared_signal_and_current_nuisance():
    time = np.repeat(np.linspace(-100, 100, 80), 2)
    rx = np.tile([0, 1], 80)
    rf = np.full(len(rx), 10e9)
    shared_signal = np.repeat(130000 * np.sin(np.linspace(0, 8, 80)), 2)
    nuisance = np.where(rx == 0, 9000 + 3 * time, -7000 - 8 * time)
    correction = np.where(rx == 1, 6000 + 40 * time, 0)
    pairs, t, residual = pair_residuals(
        time, rf, rx, shared_signal + nuisance + correction, nuisance, 0
    )
    assert len(pairs) == 80
    np.testing.assert_allclose(residual, 6000 + 40 * t, atol=1e-9)
    seed = np.arange(14, dtype=float)
    seed[[3, 5]] = 0
    original = seed.copy()
    proposals, starts, rejected = clock_starts(seed, t, residual)
    assert len(proposals) == 1 and not rejected
    assert len(starts) == 3
    for name, candidate in starts[1:]:
        anchor = int(name[-1])
        predicted = (candidate[4] - seed[4]) - (candidate[2] - seed[2])
        predicted += ((candidate[5] - seed[5]) - (candidate[3] - seed[3])) * t
        np.testing.assert_allclose(predicted, residual, atol=1e-8)
        np.testing.assert_array_equal(
            candidate[2 + 2 * anchor : 4 + 2 * anchor], seed[2 + 2 * anchor : 4 + 2 * anchor]
        )
        np.testing.assert_array_equal(candidate[6:], seed[6:])
        np.testing.assert_array_equal(candidate[:2], seed[:2])
    np.testing.assert_array_equal(seed, original)


def test_bound_rejection_does_not_clip_or_change_control():
    time = np.linspace(-100, 100, 80)
    seed = np.zeros(10)
    seed[5] = 50
    _, starts, rejected = clock_starts(seed, time, 6000 + 40 * time)
    assert [name for name, _ in starts] == ["continued-original", "proposal-1-anchor-1"]
    assert rejected[0]["name"] == "proposal-1-anchor-0"
    assert rejected[0]["slope_hz_s"] > 60
    np.testing.assert_array_equal(starts[0][1], seed)


def test_no_pairs_returns_unchanged_control():
    pairs, time, residual = pair_residuals([0], [10], [0], [5], [1], 0)
    assert pairs.shape == (0, 2)
    proposals, starts, rejected = clock_starts(np.zeros(10), time, residual)
    assert proposals == [] and rejected == [] and len(starts) == 1
