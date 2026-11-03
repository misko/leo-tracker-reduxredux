from __future__ import annotations

import itertools

import numpy as np
import pytest
from finite_set_likelihood import DEFAULT_ALIAS_HZ, prepare_finite_set_likelihood
from finite_set_rank_marks import RankMarkedFiniteSetLikelihoodAdapter


def probabilities():
    q_signal = np.array([0.34, 0.22, 0.14, 0.10, 0.07, 0.055, 0.04, 0.035])
    q_clutter = np.array([0.08, 0.09, 0.10, 0.11, 0.12, 0.14, 0.16, 0.20])
    return q_signal, q_clutter


def evaluate(adapter, predicted, visible, **overrides):
    options = {
        "sigma_hz": 120.0,
        "satellite_weights": np.ones(np.asarray(predicted).shape[1]),
        "background_mass": 0.2,
        "return_gradient": True,
        "return_precision": True,
    }
    options.update(overrides)
    return adapter.evaluate(predicted, visible, **options)


def test_equal_signal_and_clutter_marks_add_expected_constant_only():
    measured = np.array([-100.0, 300.0, 850.0])
    group = np.array([4, 4, 9])
    prepared = prepare_finite_set_likelihood(measured, group)
    ranks = np.array([0, 5, 3])
    common = np.array([0.26, 0.19, 0.15, 0.12, 0.09, 0.07, 0.065, 0.055])
    predicted = np.array([[-80.0, 400.0], [-80.0, 400.0], [900.0, -200.0]])
    visible = np.ones_like(predicted, dtype=bool)
    original = prepared.evaluate(
        predicted,
        visible,
        sigma_hz=120.0,
        detection_probability=0.8,
        clutter_rate=1.7,
        return_gradient=True,
        return_precision=True,
    )
    marked = evaluate(
        RankMarkedFiniteSetLikelihoodAdapter(
            prepared, 0.8, ranks, common, common, clutter_rate=1.7
        ),
        predicted,
        visible,
    )
    expected = np.asarray(
        [np.sum(np.log(common[ranks[indices]])) for indices in prepared.group_unique_indices]
    )
    np.testing.assert_allclose(marked["log_likelihood"] - original["log_likelihood"], expected)
    for name in (
        "association_probability",
        "row_association_probability",
        "clutter_probability",
        "satellite_miss_probability",
        "prediction_gradient",
        "prediction_precision",
    ):
        np.testing.assert_allclose(marked[name], original[name], atol=2e-14)
    standard_keys = {
        "log_likelihood",
        "total_log_likelihood",
        "unconditioned_log_likelihood",
        "empty_probability",
        "nonempty_probability",
        "association_probability",
        "row_association_probability",
        "clutter_probability",
        "satellite_miss_probability",
        "satellite_detection_probability",
        "satellite_support",
        "expected_clutter_count",
        "prediction_gradient",
        "prediction_precision",
        "null_support",
    }
    assert standard_keys <= marked.keys()


def test_uniform_marks_supply_one_known_constant_per_unique_peak():
    prepared = prepare_finite_set_likelihood([0.0, 20.0, 50.0], [1, 1, 2])
    uniform = np.full(8, 1 / 8)
    adapter = RankMarkedFiniteSetLikelihoodAdapter(
        prepared, 0.7, [0, 7, 4], uniform, uniform
    )
    result = evaluate(adapter, np.zeros((3, 1)), np.ones((3, 1), dtype=bool))
    np.testing.assert_allclose(
        result["group_log_clutter_mark_constant"], -result["unique_peak_count"] * np.log(8)
    )


def test_frequency_integral_and_rank_sum_match_analytic_one_peak_mass():
    alias = DEFAULT_ALIAS_HZ
    points = 2048
    measured = np.linspace(-alias / 2, alias / 2, points, endpoint=False)
    group = np.arange(points)
    prepared = prepare_finite_set_likelihood(measured, group)
    predicted = np.zeros((points, 1))
    visible = np.ones((points, 1), dtype=bool)
    q_signal, q_clutter = probabilities()
    detection = 0.63
    clutter_rate = 1.4
    integrated = 0.0
    for rank in range(8):
        ranks = np.full(points, rank)
        adapter = RankMarkedFiniteSetLikelihoodAdapter(
            prepared,
            detection,
            ranks,
            q_signal,
            q_clutter,
            clutter_rate=clutter_rate,
        )
        result = evaluate(
            adapter,
            predicted,
            visible,
            sigma_hz=alias / 15,
            return_gradient=False,
            return_precision=False,
        )
        integrated += np.sum(np.exp(result["log_likelihood"])) * alias / points
    expected = (
        np.exp(-clutter_rate) * ((1 - detection) * clutter_rate + detection)
        / (1 - np.exp(-clutter_rate) * (1 - detection))
    )
    assert integrated == pytest.approx(expected, abs=2e-12)


def test_prediction_gradient_matches_finite_difference():
    measured = np.array([-180.0, 250.0, 900.0])
    prepared = prepare_finite_set_likelihood(measured, [3, 3, 3])
    q_signal, q_clutter = probabilities()
    adapter = RankMarkedFiniteSetLikelihoodAdapter(
        prepared, 0.76, [0, 2, 7], q_signal, q_clutter, clutter_rate=1.2
    )
    predicted = np.tile([-130.0, 500.0], (3, 1))
    visible = np.ones_like(predicted, dtype=bool)
    result = evaluate(adapter, predicted, visible, sigma_hz=170.0)
    numerical = np.zeros(2)
    step = 1e-3
    for satellite in range(2):
        lower = predicted.copy()
        upper = predicted.copy()
        lower[:, satellite] -= step
        upper[:, satellite] += step
        numerical[satellite] = (
            evaluate(
                adapter,
                upper,
                visible,
                sigma_hz=170.0,
                return_gradient=False,
                return_precision=False,
            )["total_log_likelihood"]
            - evaluate(
                adapter,
                lower,
                visible,
                sigma_hz=170.0,
                return_gradient=False,
                return_precision=False,
            )["total_log_likelihood"]
        ) / (2 * step)
    np.testing.assert_allclose(
        np.sum(result["prediction_gradient"], axis=0), numerical, rtol=2e-6, atol=2e-10
    )


def test_exact_alias_duplicate_family_uses_one_canonical_rank():
    q_signal, q_clutter = probabilities()
    single_prepared = prepare_finite_set_likelihood([20.0], [5])
    duplicate_prepared = prepare_finite_set_likelihood(
        [20.0, 20.0 + DEFAULT_ALIAS_HZ, 20.0 - 2 * DEFAULT_ALIAS_HZ], [5, 5, 5]
    )
    single = RankMarkedFiniteSetLikelihoodAdapter(
        single_prepared, 0.8, [3], q_signal, q_clutter
    )
    duplicate = RankMarkedFiniteSetLikelihoodAdapter(
        duplicate_prepared, 0.8, [3], q_signal, q_clutter
    )
    single_result = evaluate(single, np.array([[10.0]]), np.array([[True]]))
    duplicate_result = evaluate(
        duplicate,
        np.array([[10.0], [10.0 + DEFAULT_ALIAS_HZ], [10.0 - DEFAULT_ALIAS_HZ]]),
        np.ones((3, 1), dtype=bool),
    )
    assert duplicate_result["total_log_likelihood"] == pytest.approx(
        single_result["total_log_likelihood"], abs=2e-12
    )
    np.testing.assert_allclose(
        np.sum(duplicate_result["row_association_probability"], axis=0),
        single_result["row_association_probability"][0],
    )
    with pytest.raises(ValueError, match="per unique peak"):
        RankMarkedFiniteSetLikelihoodAdapter(
            duplicate_prepared, 0.8, [3, 3, 3], q_signal, q_clutter
        )


@pytest.mark.parametrize(
    ("ranks", "q_signal", "q_clutter"),
    [
        ([0.0], np.full(8, 1 / 8), np.full(8, 1 / 8)),
        ([8], np.full(8, 1 / 8), np.full(8, 1 / 8)),
        ([0], np.ones(7) / 7, np.full(8, 1 / 8)),
        ([0], np.array([0.0, *([1 / 7] * 7)]), np.full(8, 1 / 8)),
        ([0], np.full(8, 0.2), np.full(8, 1 / 8)),
        ([0], np.full(8, 1 / 8), np.array([np.nan, *([1 / 7] * 7)])),
    ],
)
def test_invalid_ranks_and_mark_probabilities_are_rejected(ranks, q_signal, q_clutter):
    prepared = prepare_finite_set_likelihood([0.0], [0])
    with pytest.raises(ValueError):
        RankMarkedFiniteSetLikelihoodAdapter(
            prepared, 0.8, ranks, q_signal, q_clutter
        )


def test_group_geometry_conflicts_match_original_rejections():
    prepared = prepare_finite_set_likelihood([0.0, 20.0], [2, 2])
    uniform = np.full(8, 1 / 8)
    adapter = RankMarkedFiniteSetLikelihoodAdapter(
        prepared, 0.8, [0, 1], uniform, uniform
    )
    with pytest.raises(ValueError, match="groupwise constant"):
        evaluate(adapter, np.zeros((2, 1)), np.array([[True], [False]]))
    with pytest.raises(ValueError, match="groupwise equal modulo alias"):
        evaluate(adapter, np.array([[0.0], [1.0]]), np.ones((2, 1), dtype=bool))


def test_injective_competition_matches_scalar_assignment_oracle():
    measured = np.array([-40.0, 210.0])
    predicted = np.array([[-30.0, 180.0], [-30.0, 180.0]])
    visible = np.ones_like(predicted, dtype=bool)
    ranks = np.array([0, 6])
    sigma = 90.0
    detection = 0.72
    clutter_rate = 1.1
    q_signal, q_clutter = probabilities()
    prepared = prepare_finite_set_likelihood(measured, [1, 1])
    adapter = RankMarkedFiniteSetLikelihoodAdapter(
        prepared, detection, ranks, q_signal, q_clutter, clutter_rate=clutter_rate
    )
    result = evaluate(adapter, predicted, visible, sigma_hz=sigma)

    residual = measured[:, None] - predicted
    density = np.exp(-0.5 * (residual / sigma) ** 2) / (np.sqrt(2 * np.pi) * sigma)
    total = 0.0
    association = np.zeros((2, 2))
    terms = []
    for assignment in itertools.product((-1, 0, 1), repeat=2):
        assigned = [peak for peak in assignment if peak >= 0]
        if len(set(assigned)) != len(assigned):
            continue
        weight = np.exp(-clutter_rate)
        for satellite, peak in enumerate(assignment):
            if peak < 0:
                weight *= 1 - detection
            else:
                weight *= detection * density[peak, satellite] * q_signal[ranks[peak]]
        unassigned = set(range(2)) - set(assigned)
        for peak in unassigned:
            weight *= clutter_rate / DEFAULT_ALIAS_HZ * q_clutter[ranks[peak]]
        total += weight
        terms.append((assignment, weight))
    for assignment, weight in terms:
        for satellite, peak in enumerate(assignment):
            if peak >= 0:
                association[peak, satellite] += weight / total
    nonempty = 1 - np.exp(-clutter_rate) * (1 - detection) ** 2
    assert result["log_likelihood"][0] == pytest.approx(np.log(total) - np.log(nonempty))
    np.testing.assert_allclose(result["association_probability"], association, atol=2e-13)
