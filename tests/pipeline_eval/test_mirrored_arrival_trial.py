from importlib import import_module

import numpy as np


trial = import_module("reports.ALGO08.single-core-2x.mirrored_arrival_trial")


def test_whole_orbit_blocks_share_folds_and_boundary_intervals_are_excluded():
    times = np.array([6., 7.5, 8.5, 9.5, 11.9, 15., 16., 17.])
    assert trial.interval_blocks(times).tolist() == [0, -1, 1, 1, -1, -1, 2]
    first = trial.assign_blocks(123, {0, 1, 2, 3})
    assert first == trial.assign_blocks(123, [2, 0, 1, 3])
    assert list(first.values()).count(0) == list(first.values()).count(1) == 2


def test_held_fractional_increments_choose_planted_range_with_unknown_rate():
    dt = np.tile([.8, 1., 1.2], 4)
    labels = np.repeat([0, 1, 0, 1], 3)
    a = np.sin(np.arange(len(dt))) + 20.
    b = a + .05 * np.cos(np.arange(len(dt)))
    period = trial.arrival.phase.FRAME_HZ
    codes = trial.arrival.phase.wrap(a + 2.75 * dt, period)
    models = dict(A=a, B=b, rate_only=np.zeros_like(a), reflected=-a)
    both = trial.held_residuals(codes, models, dt, labels, period)
    assert {entry[0] for entry in both} == {0, 1}
    for _, held, residual in both:
        assert held.sum() == 6
        assert np.max(np.abs(residual["A"])) < 1e-10
        assert all(np.dot(residual[arm], residual[arm]) > 0 for arm in ("B", "rate_only", "reflected"))


def test_satellite_groups_have_equal_weight_even_when_one_has_more_intervals():
    held = {100: {name: np.ones(30) for name in trial.HYPOTHESES},
            200: {name: np.ones(2) for name in trial.HYPOTHESES}}
    held[100]["A"][:] = 0.
    held[200]["A"][:] = 2.
    result = trial.summarize(held)
    assert result["aggregate_mse_samples2"]["A"] == 2.
    assert result["delta_B_minus_A_samples2"] == -1.
    assert result["leave_one_satellite_out_samples2"] == [-3., 1.]
