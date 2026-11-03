import itertools
import math
import time

import numpy as np
import pytest
from finite_set_likelihood import (
    DEFAULT_ALIAS_HZ,
    finite_set_likelihood,
    prepare_finite_set_likelihood,
)


def _normal_density(measured, predicted, sigma_hz):
    residual = (measured - predicted + DEFAULT_ALIAS_HZ / 2) % DEFAULT_ALIAS_HZ
    residual -= DEFAULT_ALIAS_HZ / 2
    return np.exp(-0.5 * (residual / sigma_hz) ** 2) / (np.sqrt(2 * np.pi) * sigma_hz)


def _brute_force(measured, predicted, visible, sigma_hz, detection, clutter_rate):
    peak_count, satellite_count = predicted.shape
    density = _normal_density(measured[:, None], predicted, sigma_hz)
    total = 0.0
    association = np.zeros_like(predicted)
    miss = np.zeros(satellite_count)
    clutter = np.zeros(peak_count)
    terms = []
    choices = [-1, *range(peak_count)]
    for assignment in itertools.product(choices, repeat=satellite_count):
        assigned = [peak for peak in assignment if peak >= 0]
        if len(set(assigned)) != len(assigned):
            continue
        weight = np.exp(-clutter_rate)
        valid = True
        for satellite, peak in enumerate(assignment):
            satellite_visible = bool(np.any(visible[:, satellite]))
            probability = detection[satellite] if satellite_visible else 0.0
            if peak < 0:
                weight *= 1 - probability
            elif not visible[peak, satellite]:
                valid = False
                break
            else:
                weight *= probability * density[peak, satellite]
        if not valid:
            continue
        unassigned = set(range(peak_count)) - set(assigned)
        weight *= (clutter_rate / DEFAULT_ALIAS_HZ) ** len(unassigned)
        total += weight
        terms.append((assignment, unassigned, weight))
    for assignment, unassigned, weight in terms:
        probability = weight / total
        for satellite, peak in enumerate(assignment):
            if peak < 0:
                miss[satellite] += probability
            else:
                association[peak, satellite] += probability
        for peak in unassigned:
            clutter[peak] += probability
    visible_satellites = np.any(visible, axis=0)
    empty = np.exp(-clutter_rate) * np.prod(np.where(visible_satellites, 1 - detection, 1.0))
    return np.log(total) - np.log1p(-empty), association, miss, clutter


def _evaluate(measured, predicted, visible, group, **overrides):
    options = {
        "sigma_hz": 80.0,
        "detection_probability": 0.8,
        "clutter_rate": 2.0,
        "return_gradient": True,
        "return_precision": True,
    }
    options.update(overrides)
    return finite_set_likelihood(measured, predicted, visible, group, **options)


def test_small_problem_matches_brute_force_associations_and_normalizers():
    measured = np.array([-30.0, 510.0, 900.0])
    predicted = np.tile([-20.0, 600.0], (3, 1))
    visible = np.ones_like(predicted, dtype=bool)
    detection = np.array([0.65, 0.85])
    result = _evaluate(
        measured,
        predicted,
        visible,
        np.zeros(3, dtype=int),
        sigma_hz=120.0,
        detection_probability=detection,
        clutter_rate=1.3,
    )
    expected = _brute_force(measured, predicted, visible, 120.0, detection, 1.3)
    assert result["log_likelihood"][0] == pytest.approx(expected[0], abs=2e-12)
    np.testing.assert_allclose(result["association_probability"], expected[1], atol=2e-12)
    np.testing.assert_allclose(result["satellite_miss_probability"][0], expected[2])
    np.testing.assert_allclose(result["clutter_probability"], expected[3])


def test_two_real_peaks_support_two_satellites_in_one_group():
    measured = np.array([0.0, 3000.0])
    predicted = np.array([[0.0, 3000.0], [0.0, 3000.0]])
    result = _evaluate(
        measured,
        predicted,
        np.ones_like(predicted, dtype=bool),
        [4, 4],
        sigma_hz=20.0,
        detection_probability=0.95,
        clutter_rate=0.02,
    )
    assert result["association_probability"][0, 0] > 0.999
    assert result["association_probability"][1, 1] > 0.999
    assert np.sum(result["satellite_support"]) > 1.998


def test_peak_and_satellite_posteriors_conserve_probability():
    measured = np.array([0.0, 200.0, 700.0, -500.0])
    predicted = np.array(
        [[10.0, 500.0, 0.0], [10.0, 500.0, 0.0], [10.0, 500.0, 0.0], [-450.0, 0.0, 0.0]]
    )
    visible = np.array(
        [[True, True, False], [True, True, False], [True, True, False], [True, False, False]]
    )
    result = _evaluate(measured, predicted, visible, [1, 1, 1, 2])
    np.testing.assert_allclose(
        np.sum(result["association_probability"], axis=1) + result["clutter_probability"],
        1.0,
        atol=2e-13,
    )
    for group_index in range(2):
        selected = result["unique_group_index"] == group_index
        np.testing.assert_allclose(
            np.sum(result["association_probability"][selected], axis=0)
            + result["satellite_miss_probability"][group_index],
            1.0,
            atol=2e-13,
        )
    np.testing.assert_array_equal(result["satellite_miss_probability"][:, 2], 1.0)


def test_prediction_gradient_and_complete_data_precision():
    measured = np.array([-200.0, 300.0, 1000.0])
    predicted = np.tile([-170.0, 420.0], (3, 1))
    visible = np.ones_like(predicted, dtype=bool)
    prepared = prepare_finite_set_likelihood(measured, [8, 8, 8])
    options = {
        "sigma_hz": 150.0,
        "detection_probability": [0.7, 0.85],
        "clutter_rate": 1.5,
    }
    result = prepared.evaluate(
        predicted,
        visible,
        **options,
        return_gradient=True,
        return_precision=True,
    )
    numerical = np.zeros(predicted.shape[1])
    step = 1e-3
    for satellite in range(predicted.shape[1]):
        lower = predicted.copy()
        upper = predicted.copy()
        lower[:, satellite] -= step
        upper[:, satellite] += step
        numerical[satellite] = (
            prepared.evaluate(upper, visible, **options)["total_log_likelihood"]
            - prepared.evaluate(lower, visible, **options)["total_log_likelihood"]
        ) / (2 * step)
    np.testing.assert_allclose(
        np.sum(result["prediction_gradient"], axis=0),
        numerical,
        rtol=2e-6,
        atol=2e-10,
    )
    np.testing.assert_allclose(
        result["prediction_precision"] * options["sigma_hz"] ** 2,
        result["row_association_probability"],
    )
    np.testing.assert_array_equal(result["prediction_gradient"][~visible], 0.0)


def test_alias_lifts_and_permutations_preserve_likelihood_and_marginals():
    measured = np.array([-500.0, 100.0, 900.0])
    predicted = np.tile([-450.0, 300.0], (3, 1))
    visible = np.ones_like(predicted, dtype=bool)
    group = np.array([5, 5, 5])
    baseline = _evaluate(measured, predicted, visible, group)
    row_order = np.array([2, 0, 1])
    satellite_order = np.array([1, 0])
    lifted = _evaluate(
        measured[row_order] + np.array([3, -2, 7]) * DEFAULT_ALIAS_HZ,
        predicted[row_order][:, satellite_order]
        + np.array([[2, -4], [5, 1], [-3, 8]]) * DEFAULT_ALIAS_HZ,
        visible[row_order][:, satellite_order],
        group[row_order],
        detection_probability=np.array([0.8, 0.8])[satellite_order],
    )
    assert lifted["total_log_likelihood"] == pytest.approx(
        baseline["total_log_likelihood"], abs=2e-11
    )
    np.testing.assert_allclose(
        lifted["satellite_support"][np.argsort(satellite_order)],
        baseline["satellite_support"],
        atol=2e-12,
    )
    np.testing.assert_allclose(
        lifted["association_probability"][:, np.argsort(satellite_order)],
        baseline["association_probability"],
        atol=2e-12,
    )
    restored_gradient = lifted["prediction_gradient"][np.argsort(row_order)][
        :, np.argsort(satellite_order)
    ]
    np.testing.assert_allclose(restored_gradient, baseline["prediction_gradient"], atol=2e-12)


def test_exact_period_duplicates_are_collapsed_without_extra_evidence():
    single = _evaluate([20.0], np.array([[10.0, 500.0]]), [[True, True]], [3])
    duplicate = _evaluate(
        [20.0, 20.0 + DEFAULT_ALIAS_HZ, 20.0 - 2 * DEFAULT_ALIAS_HZ],
        np.array([[10.0, 500.0]] * 3),
        np.ones((3, 2), dtype=bool),
        [3, 3, 3],
    )
    assert duplicate["total_log_likelihood"] == pytest.approx(
        single["total_log_likelihood"], abs=2e-12
    )
    np.testing.assert_allclose(
        duplicate["association_probability"], single["association_probability"]
    )
    assert duplicate["raw_peak_count"].tolist() == [3]
    assert duplicate["unique_peak_count"].tolist() == [1]
    np.testing.assert_allclose(
        np.sum(duplicate["row_association_probability"], axis=0),
        single["row_association_probability"][0],
    )


def test_conditioned_pure_clutter_cardinality_and_visibility_normalize():
    clutter_rate = 1.7
    cardinality_mass = []
    for peak_count in range(1, 18):
        result = _evaluate(
            np.arange(peak_count, dtype=float) * 100.0,
            np.empty((peak_count, 0)),
            np.empty((peak_count, 0), dtype=bool),
            np.zeros(peak_count, dtype=int),
            clutter_rate=clutter_rate,
            max_peaks_per_group=20,
        )
        density = np.exp(result["log_likelihood"][0])
        cardinality_mass.append(density * DEFAULT_ALIAS_HZ**peak_count / math.factorial(peak_count))
        assert result["empty_probability"][0] == pytest.approx(np.exp(-clutter_rate))
    assert sum(cardinality_mass) == pytest.approx(1.0, abs=2e-10)

    invisible = _evaluate(
        [0.0],
        np.zeros((1, 3)),
        np.zeros((1, 3), dtype=bool),
        [0],
        detection_probability=[0.2, 0.7, 1.0],
        clutter_rate=clutter_rate,
    )
    assert invisible["nonempty_probability"][0] == pytest.approx(1 - np.exp(-clutter_rate))
    np.testing.assert_array_equal(invisible["satellite_miss_probability"], 1.0)


def test_peak_and_memory_guards_raise_after_deduplication():
    measured = np.arange(10.0)
    with pytest.raises(ValueError, match="unique peaks"):
        prepare_finite_set_likelihood(measured, np.zeros(10, dtype=int))

    prepared = prepare_finite_set_likelihood(
        np.arange(8.0), np.zeros(8, dtype=int), max_dp_cells=10_000
    )
    with pytest.raises(ValueError, match="max_dp_cells"):
        prepared.evaluate(
            np.zeros((8, 64)),
            np.ones((8, 64), dtype=bool),
            sigma_hz=100.0,
            detection_probability=0.8,
            clutter_rate=2.0,
            return_gradient=True,
        )

    batch_limited = prepare_finite_set_likelihood(
        np.arange(8.0), np.zeros(8, dtype=int), max_batch_dp_cells=10_000
    )
    with pytest.raises(ValueError, match="max_batch_dp_cells"):
        batch_limited.evaluate(
            np.zeros((8, 64)),
            np.ones((8, 64), dtype=bool),
            sigma_hz=100.0,
            detection_probability=0.8,
            clutter_rate=2.0,
        )

    deduplicated = prepare_finite_set_likelihood(np.zeros(20), np.zeros(20, dtype=int))
    assert deduplicated.unique_peak_count == 1


def test_groupwise_visibility_conflict_is_rejected_explicitly():
    prepared = prepare_finite_set_likelihood([0.0, 10.0], [2, 2])
    with pytest.raises(ValueError, match="groupwise constant"):
        prepared.evaluate(
            np.zeros((2, 1)),
            np.array([[True], [False]]),
            sigma_hz=100.0,
            detection_probability=0.8,
            clutter_rate=2.0,
        )


def test_groupwise_prediction_conflict_is_rejected_explicitly():
    prepared = prepare_finite_set_likelihood([0.0, 10.0], [2, 2])
    with pytest.raises(ValueError, match="predicted means must be groupwise equal"):
        prepared.evaluate(
            np.array([[0.0], [1.0]]),
            np.ones((2, 1), dtype=bool),
            sigma_hz=100.0,
            detection_probability=0.8,
            clutter_rate=2.0,
        )


def test_groupwise_predictions_may_differ_by_whole_alias_periods():
    prepared = prepare_finite_set_likelihood([0.0, 10.0, 20.0], [2, 2, 2])
    predicted = np.array([[300.0], [300.0 + DEFAULT_ALIAS_HZ], [300.0 - 2 * DEFAULT_ALIAS_HZ]])
    result = prepared.evaluate(
        predicted,
        np.ones((3, 1), dtype=bool),
        sigma_hz=100.0,
        detection_probability=0.8,
        clutter_rate=2.0,
        return_gradient=True,
    )
    assert np.isfinite(result["total_log_likelihood"])
    assert np.all(np.isfinite(result["prediction_gradient"]))


def test_batched_matches_scalar_oracle_for_mixed_cardinality_and_visibility():
    rng = np.random.default_rng(7203)
    counts = np.array([1, 2, 2, 3, 4, 6, 8, 8])
    group = np.repeat(np.arange(len(counts)), counts)
    measured = rng.uniform(-8000.0, 8000.0, np.sum(counts))
    satellite_count = 7
    group_prediction = rng.uniform(-9000.0, 9000.0, (len(counts), satellite_count))
    predicted = np.repeat(group_prediction, counts, axis=0)
    group_visibility = rng.random((len(counts), satellite_count)) > 0.3
    visible = np.repeat(group_visibility, counts, axis=0)
    detection = rng.uniform(0.15, 0.95, satellite_count)
    prepared = prepare_finite_set_likelihood(measured, group, max_batch_dp_cells=4096)
    options = {
        "sigma_hz": 450.0,
        "detection_probability": detection,
        "clutter_rate": 1.7,
        "return_gradient": True,
        "return_precision": True,
    }
    batched = prepared.evaluate(predicted, visible, implementation="batched", **options)
    scalar = prepared.evaluate(predicted, visible, implementation="scalar", **options)
    for key in (
        "log_likelihood",
        "unconditioned_log_likelihood",
        "empty_probability",
        "nonempty_probability",
        "association_probability",
        "row_association_probability",
        "clutter_probability",
        "satellite_miss_probability",
        "prediction_gradient",
        "prediction_precision",
    ):
        np.testing.assert_allclose(batched[key], scalar[key], rtol=2e-13, atol=2e-13)


def test_k64_n8_stress_is_finite_and_conservative():
    rng = np.random.default_rng(1844)
    measured = rng.uniform(-5000.0, 5000.0, 8)
    predicted = np.broadcast_to(rng.uniform(-6000.0, 6000.0, 64), (8, 64)).copy()
    visible = np.broadcast_to(rng.random(64) > 0.15, (8, 64)).copy()
    started = time.perf_counter()
    result = _evaluate(
        measured,
        predicted,
        visible,
        np.zeros(8, dtype=int),
        sigma_hz=500.0,
    )
    elapsed = time.perf_counter() - started
    assert np.isfinite(result["total_log_likelihood"])
    assert np.all(np.isfinite(result["prediction_gradient"]))
    np.testing.assert_allclose(
        np.sum(result["association_probability"], axis=1) + result["clutter_probability"],
        1.0,
        atol=2e-12,
    )
    np.testing.assert_allclose(
        np.sum(result["association_probability"], axis=0) + result["satellite_miss_probability"][0],
        1.0,
        atol=2e-12,
    )
    assert elapsed < 3.0
