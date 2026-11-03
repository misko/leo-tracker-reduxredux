from types import SimpleNamespace

import numpy as np
import rx_difference


def layout(rows):
    return SimpleNamespace(
        times=np.asarray([row[0] for row in rows], dtype=float),
        rf=np.asarray([row[1] for row in rows], dtype=float),
        receiver=np.asarray([row[2] for row in rows], dtype=int),
        group=np.asarray([row[3] for row in rows], dtype=int),
        measured=np.asarray([row[4] for row in rows], dtype=float),
    )


def test_categorical_alternatives_are_duplicate_invariant():
    unique = layout(
        [
            (1.0, 10.0, 0, 10, 100.0),
            (1.0, 10.0, 0, 10, 200.0),
            (1.0002, 10.0, 1, 20, 500.0),
            (1.0002, 10.0, 1, 20, 700.0),
        ]
    )
    duplicated = layout(
        [
            (1.0, 10.0, 0, 10, 100.0),
            (1.0, 10.0, 0, 10, 100.0),
            (1.0, 10.0, 0, 10, 200.0),
            (1.0002, 10.0, 1, 20, 500.0),
            (1.0002, 10.0, 1, 20, 700.0),
            (1.0002, 10.0, 1, 20, 700.0),
        ]
    )

    first = rx_difference.pair_receiver_groups(unique)
    second = rx_difference.pair_receiver_groups(duplicated)

    np.testing.assert_allclose(first.differences, second.differences)
    np.testing.assert_allclose(first.weights, second.weights)
    assert first.pair_count == second.pair_count == 1
    assert np.isclose(np.add.reduceat(first.weights, first.starts)[0], 1.0)
    assert "never independent observations" in first.metadata["evidence_accounting"]


def test_pairing_is_nearest_same_rf_and_one_to_one():
    data = layout(
        [
            (0.0000, 10.0, 0, 1, 100.0),
            (0.0007, 10.0, 0, 2, 200.0),
            (0.0002, 10.0, 1, 3, 300.0),
            (0.0014, 10.0, 1, 4, 400.0),
            (2.0000, 20.0, 0, 5, 500.0),
            (2.0001, 30.0, 1, 6, 600.0),
        ]
    )

    paired = rx_difference.pair_receiver_groups(data)

    np.testing.assert_array_equal(paired.rx0_groups, [1, 2])
    np.testing.assert_array_equal(paired.rx1_groups, [3, 4])
    assert len(np.unique(paired.rx0_groups)) == paired.pair_count
    assert len(np.unique(paired.rx1_groups)) == paired.pair_count
    assert paired.metadata["unpaired_group_count_rx0"] == 1
    assert paired.metadata["unpaired_group_count_rx1"] == 1
    assert paired.metadata["pair_tolerance_s"] == 0.001


def test_group_receive_time_is_row_median():
    data = layout(
        [
            (1.0000, 10.0, 0, 1, 100.0),
            (1.0004, 10.0, 0, 1, 200.0),
            (1.0003, 10.0, 1, 2, 300.0),
            (1.0005, 10.0, 1, 2, 400.0),
        ]
    )

    paired = rx_difference.pair_receiver_groups(data)

    np.testing.assert_allclose(paired.times, [1.0003])
    assert np.isclose(paired.metadata["within_source_group_time_span_ms"]["maximum"], 0.4)


def synthetic_groups(seed=41):
    rng = np.random.default_rng(seed)
    times = np.linspace(0.0, 120.0, 160)
    reference = 60.0
    intercept = 37000.0
    slope = 37.0
    values = []
    weights = []
    counts = []
    for time_value in times:
        signal = rx_difference.circular(intercept + slope * (time_value - reference))
        alternatives = np.r_[
            signal, rng.uniform(-rx_difference.ALIAS_HZ / 2, rx_difference.ALIAS_HZ / 2, 5)
        ]
        values.extend(alternatives)
        weights.extend(np.full(len(alternatives), 1.0 / len(alternatives)))
        counts.append(len(alternatives))
    counts = np.asarray(counts, dtype=int)
    return (
        rx_difference.DifferentialGroups(
            times=times,
            rf=np.full(len(times), 11.0e9),
            rx0_groups=np.arange(len(times)),
            rx1_groups=np.arange(len(times)) + len(times),
            starts=np.r_[0, np.cumsum(counts[:-1])],
            counts=counts,
            differences=np.asarray(values),
            weights=np.asarray(weights),
            metadata={},
        ),
        intercept,
        slope,
    )


def test_known_synthetic_difference_recovers_with_categorical_clutter():
    groups, intercept, slope = synthetic_groups()
    fitted = rx_difference.fit_difference_models(
        groups,
        include_quadratic=False,
        budget_s=5.0,
    )["line"]

    assert abs(float(rx_difference.circular(fitted["intercept_hz_at_reference"], intercept))) < 1
    assert abs(fitted["slope_hz_s"] - slope) < 0.05
    assert fitted["objective"] < min(
        trial["objective"]
        for trial in rx_difference.coarse_hough(
            groups,
            rx_difference.DifferentialLikelihood(groups),
            60.0,
        )
    )


def test_postseal_comparison_uses_rx1_minus_rx0():
    fit = {
        "reference_time_s": 160.0,
        "line": {"intercept_hz_at_reference": 1500.0, "slope_hz_s": 3.0},
    }
    initial = np.array([0.0, 0.0, 100.0, 2.0, 1000.0, 5.0])

    result = rx_difference.postseal_model_comparison(fit, initial)

    assert result["model_rx1_minus_rx0_intercept_hz_at_reference"] == 930.0
    assert result["model_rx1_minus_rx0_slope_hz_s"] == 3.0
    assert result["fitted_minus_model_intercept_hz"] == 570.0
    assert result["used_by_fitter"] is False
