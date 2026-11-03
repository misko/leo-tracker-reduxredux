import numpy as np
import pytest
from matching import ALIAS_HZ
from position_loss import CAP_HZ, best_group_rows, profile_receiver, rho, training_mask


def test_all_training_has_no_holdout():
    times = np.arange(0, 300, 0.5)
    assert np.all(training_mask(times, all_training=True))
    assert np.sum(~training_mask(times)) == 200


def test_group_duplicates_do_not_add_weight():
    residual = np.array([[100, 1000], [100, 1000], [500, 2000]])
    rows, _, errors = best_group_rows(residual, np.array([0, 0, 1]))
    assert len(rows) == 2
    assert np.mean(rho(errors)) == pytest.approx(np.mean(rho(np.array([100, 500]))))


def test_more_satellites_cannot_increase_fixed_position_loss():
    generator = np.random.default_rng(42)
    residual = generator.uniform(-100000, 100000, (90, 64))
    groups = np.repeat(np.arange(30), 3)
    costs = []
    for count in (8, 16, 32, 64):
        _, _, errors = best_group_rows(residual[:, :count], groups)
        costs.append(np.mean(rho(errors)))
    assert np.all(np.diff(costs) <= 0)


def test_unmatched_observations_pay_fixed_penalty():
    assert rho(np.inf) == pytest.approx(rho(CAP_HZ))
    assert rho(100000) == pytest.approx(rho(CAP_HZ))
    assert np.mean(rho(np.array([0, np.inf]))) > rho(0)


def test_profile_recovers_line_and_aliases():
    times = np.linspace(-150, 150, 80)
    values = -8800 + 6 * times + np.arange(80) % 4 * ALIAS_HZ
    base = np.column_stack([values, values + 45000])
    result = profile_receiver(base, np.arange(80), times, np.ones(80, dtype=bool), [-8500, 0])
    np.testing.assert_allclose(result, [-8800, 6], atol=0.01)


def test_profile_does_not_use_evaluation_values():
    times = np.linspace(-150, 150, 80)
    training = np.arange(80) % 3 != 2
    base = np.column_stack([-8800 + 6 * times, 35000 + 6 * times])
    result = profile_receiver(base, np.arange(80), times, training, [-8500, 0])
    base[~training] += 10000
    changed = profile_receiver(base, np.arange(80), times, training, [-8500, 0])
    np.testing.assert_allclose(result, changed, atol=1e-8)


def test_slope_bound():
    times = np.linspace(-150, 150, 80)
    result = profile_receiver(
        (-8800 + 14 * times)[:, None], np.arange(80), times, np.ones(80, dtype=bool), [-8800, 9]
    )
    assert result[1] == 10


def test_missing_predictions_preserve_parameters():
    times = np.linspace(-150, 150, 80)
    result = profile_receiver(
        np.full((80, 2), np.nan), np.arange(80), times, np.ones(80, dtype=bool), [-8800, 6]
    )
    np.testing.assert_allclose(result, [-8800, 6])
