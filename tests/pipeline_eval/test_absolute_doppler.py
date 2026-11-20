import numpy as np
import pytest

from tools.pipeline_eval.qualification.absolute_doppler_results import calibration_support
from tools.pipeline_eval.variants import absolute_doppler as solver


def test_coherent_clock_prefers_wrapped_matches_over_independently_better_shapes():
    period = solver.physical.PERIOD_HZ
    true = np.array([-period / 2 + 200, period / 2 - 400, period / 2 - 100])
    distractors = [11_000, -30_000, 63_000]

    def option(false, real):
        return np.array([1, 2]), np.zeros(2), np.array([false, real]), np.array([0.1, 0.3])

    level, picked, cost = solver.common_level(
        [option(false, real) for false, real in zip(distractors, true, strict=True)]
    )
    assert picked == [1, 1, 1]
    assert max(cost) < 0.5
    assert abs(solver.physical.fold(level - period / 2)) < 1_500


def test_shared_calibration_has_rf_contrast_and_never_fits_held_samples():
    rf = np.tile([-0.35, 0.30, 0.72], 120)
    group = np.repeat([0, 1], rf.size // 2)
    free_levels = np.eye(2)[group]
    design = np.column_stack((free_levels, rf))
    use = np.arange(rf.size) % 5 != 0
    measurements = design @ [420.0, -750.0, 2300.0]
    c0, no_rf = solver.clock_fit(measurements, free_levels, use, False)
    fitted, residual = solver.clock_fit(measurements, design, use, True)
    held_shift = ~use * 16000
    reweighted, after = solver.clock_fit(measurements + held_shift, design, use, True)
    assert len(c0) == 2
    assert fitted[2] == pytest.approx(2300, abs=12)
    assert np.sqrt(np.mean(residual[~use] ** 2)) < np.sqrt(np.mean(no_rf[~use] ** 2)) / 100
    np.testing.assert_array_equal(fitted, reweighted)
    np.testing.assert_allclose(after - residual, held_shift)


def test_scoring_rejects_changed_integer_branch_between_calibration_arms():
    arms = {"c0": {"train_aliases": [-1, 1]}, "fitted_c": {"train_aliases": [0, 1]}}
    with pytest.raises(ValueError, match="train_aliases"):
        calibration_support(arms)
