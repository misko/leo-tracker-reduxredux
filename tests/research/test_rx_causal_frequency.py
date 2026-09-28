import numpy as np
import pytest

from tools.rx_causal_frequency import CausalFrequencyPredictor

PERIOD = 227_000.0


def test_predictive_phase_density_integrates_to_one() -> None:
    predictor = CausalFrequencyPredictor(PERIOD)
    predictor.score_then_update(0.0, [10_000.0, 20_000.0])
    predictor.score_then_update(1.0, [11_000.0, 21_000.0])
    grid = np.linspace(0.0, PERIOD, 200_001)
    density, receipt = predictor.density_at(2.0, grid)
    assert receipt["mode"] == "two_history"
    assert np.trapezoid(density, grid / PERIOD) == pytest.approx(1.0, abs=2e-9)


def test_receipt_and_predictor_are_prefix_invariant_to_current_candidates() -> None:
    first = CausalFrequencyPredictor(PERIOD)
    second = CausalFrequencyPredictor(PERIOD)
    for predictor in (first, second):
        predictor.score_then_update(0.0, [100.0, 200.0])
    _, first_receipt = first.score_then_update(1.0, [300.0])
    _, second_receipt = second.score_then_update(1.0, [90_000.0, 100_000.0])
    first_receipt.pop("scored_candidate_count")
    second_receipt.pop("scored_candidate_count")
    assert first_receipt == second_receipt
    probe_first, _ = first.density_at(2.0, [400.0])
    probe_second, _ = second.density_at(2.0, [400.0])
    assert probe_first[0] != pytest.approx(probe_second[0])


def test_exact_duplicate_history_candidates_do_not_change_weighting() -> None:
    unique = CausalFrequencyPredictor(PERIOD)
    duplicate = CausalFrequencyPredictor(PERIOD)
    unique.score_then_update(0.0, [100.0, 200.0])
    duplicate.score_then_update(0.0, [100.0, 100.0, 200.0, 200.0])
    expected, expected_receipt = unique.density_at(1.0, [150.0, 500.0])
    actual, actual_receipt = duplicate.density_at(1.0, [150.0, 500.0])
    np.testing.assert_array_equal(actual, expected)
    assert actual_receipt == expected_receipt


def test_empty_windows_advance_clock_without_replacing_history_and_old_history_expires() -> None:
    predictor = CausalFrequencyPredictor(PERIOD)
    predictor.score_then_update(0.0, [100.0])
    empty_density, empty_receipt = predictor.score_then_update(2.0, [])
    assert empty_density.size == 0
    assert empty_receipt["mode"] == "one_history"
    _, recent = predictor.score_then_update(9.0, [200.0])
    assert recent["mode"] == "one_history"
    density, expired = predictor.density_at(20.0, [300.0])
    assert expired["mode"] == "uniform"
    np.testing.assert_array_equal(density, [1.0])


def test_synthetic_constant_velocity_predicts_future_peak() -> None:
    predictor = CausalFrequencyPredictor(PERIOD)
    predictor.score_then_update(0.0, [10_000.0])
    predictor.score_then_update(1.0, [11_000.0])
    density, receipt = predictor.density_at(2.0, [12_000.0, 11_000.0, 30_000.0])
    assert receipt["mode"] == "two_history"
    assert receipt["components"][0]["mean_hz"] == pytest.approx(12_000.0)
    assert density[0] > density[1] > density[2]


def test_strict_chronology_is_enforced() -> None:
    predictor = CausalFrequencyPredictor(PERIOD)
    predictor.score_then_update(1.0, [100.0])
    with pytest.raises(ValueError, match="strictly increasing"):
        predictor.score_then_update(1.0, [200.0])


def test_fresh_observation_after_stale_two_history_restarts_one_history() -> None:
    predictor = CausalFrequencyPredictor(PERIOD)
    predictor.score_then_update(0.0, [100.0])
    predictor.score_then_update(1.0, [200.0])
    _, stale = predictor.score_then_update(20.0, [5_000.0])
    assert stale["mode"] == "uniform"
    density, restarted = predictor.density_at(21.0, [5_100.0])
    assert restarted["mode"] == "one_history"
    assert restarted["history_times_s"] == [1.0, 20.0]
    assert density[0] > 0


def test_tiny_gap_extreme_velocity_pair_weights_and_density_normalize() -> None:
    predictor = CausalFrequencyPredictor(PERIOD)
    predictor.score_then_update(0.0, [0.0, 2_000.0])
    predictor.score_then_update(1e-9, [1_000.0])
    grid = np.linspace(0.0, PERIOD, 200_000, endpoint=False)
    density, receipt = predictor.density_at(2e-9, grid)
    assert receipt["mode"] == "two_history"
    assert sum(component["weight"] for component in receipt["components"]) == pytest.approx(1.0)
    np.testing.assert_allclose(
        [component["weight"] for component in receipt["components"]], [0.5, 0.5]
    )
    assert np.mean(density) == pytest.approx(1.0, abs=2e-12)
