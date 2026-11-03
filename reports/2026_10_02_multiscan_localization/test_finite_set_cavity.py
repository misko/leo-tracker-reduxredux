import finite_set_cavity
import finite_set_likelihood
import numpy as np
import pytest


def _groupwise_columns(rng, group, satellite_count):
    group_values = np.unique(group)
    predicted = np.empty((len(group), satellite_count))
    visible = np.empty_like(predicted, dtype=bool)
    for value in group_values:
        rows = group == value
        predicted[rows] = rng.uniform(-120_000.0, 120_000.0, size=satellite_count)
        visible[rows] = rng.random(satellite_count) > 0.2
    return predicted, visible


def _replace_and_compare(prepared, predicted, visible, probabilities, clutter, sigma, satellite):
    scorer = finite_set_cavity.prepare_replacement_scorer(
        prepared,
        predicted,
        visible,
        satellite_index=satellite,
        detection_probability=probabilities,
        clutter_rate=clutter,
        sigma_hz=sigma,
    )
    replacement_predicted = predicted[:, satellite].copy()
    replacement_visible = visible[:, satellite].copy()
    direct_predicted = predicted.copy()
    direct_visible = visible.copy()
    result = scorer.evaluate(replacement_predicted, replacement_visible)
    direct = prepared.evaluate(
        direct_predicted,
        direct_visible,
        sigma_hz=sigma,
        detection_probability=probabilities,
        clutter_rate=clutter,
        implementation="scalar",
    )
    np.testing.assert_allclose(result["log_likelihood"], direct["log_likelihood"], atol=2e-11)
    np.testing.assert_allclose(
        result["unconditioned_log_likelihood"],
        direct["unconditioned_log_likelihood"],
        atol=2e-11,
    )
    np.testing.assert_allclose(
        result["nonempty_probability"], direct["nonempty_probability"], atol=2e-14
    )
    assert result["total_log_likelihood"] == pytest.approx(
        direct["total_log_likelihood"], abs=2e-11
    )
    return scorer


def test_randomized_replacement_matches_direct_full_scalar_oracle():
    rng = np.random.default_rng(4971)
    alias = finite_set_likelihood.DEFAULT_ALIAS_HZ
    for _ in range(20):
        measured = []
        group = []
        for group_value in range(rng.integers(1, 7)):
            unique = rng.uniform(-alias / 2, alias / 2, size=rng.integers(1, 5))
            rows = list(unique)
            if rng.random() < 0.6:
                rows.append(unique[rng.integers(len(unique))] + alias)
            measured.extend(rows)
            group.extend([group_value] * len(rows))
        measured = np.asarray(measured)
        group = np.asarray(group)
        prepared = finite_set_likelihood.prepare_finite_set_likelihood(measured, group)
        satellite_count = int(rng.integers(1, 7))
        predicted, visible = _groupwise_columns(rng, group, satellite_count)
        probabilities = rng.uniform(0.02, 0.85, size=satellite_count)
        clutter = float(rng.uniform(0.05, 3.0))
        sigma = float(rng.uniform(20.0, 500.0))
        satellite = int(rng.integers(satellite_count))
        scorer = _replace_and_compare(
            prepared,
            predicted,
            visible,
            probabilities,
            clutter,
            sigma,
            satellite,
        )

        new_predicted = predicted[:, satellite].copy()
        new_visible = visible[:, satellite].copy()
        for value in np.unique(group):
            rows = group == value
            new_predicted[rows] += rng.uniform(-2000.0, 2000.0)
            new_visible[rows] = rng.random() > 0.35
        cavity = scorer.evaluate(new_predicted, new_visible)
        direct_predicted = predicted.copy()
        direct_visible = visible.copy()
        direct_predicted[:, satellite] = new_predicted
        direct_visible[:, satellite] = new_visible
        direct = prepared.evaluate(
            direct_predicted,
            direct_visible,
            sigma_hz=sigma,
            detection_probability=probabilities,
            clutter_rate=clutter,
            implementation="scalar",
        )
        np.testing.assert_allclose(cavity["log_likelihood"], direct["log_likelihood"], atol=3e-11)


def test_empty_leave_one_out_set_with_only_satellite_and_peak():
    measured = np.array([1234.0])
    group = np.array([7])
    prepared = finite_set_likelihood.prepare_finite_set_likelihood(measured, group)
    predicted = np.array([[1200.0]])
    visible = np.array([[True]])
    scorer = _replace_and_compare(
        prepared,
        predicted,
        visible,
        np.array([0.8]),
        2.0,
        200.0,
        0,
    )
    assert scorer.log_cavity_without_peak[0].shape == (1,)
    assert np.isfinite(scorer.log_cavity_without_peak[0][0])

    direct_scorer = finite_set_cavity.FiniteSetCavityScorer(
        prepared,
        predicted,
        visible,
        0,
        200.0,
        0.8,
        2.0,
    )
    result = direct_scorer.evaluate(predicted[:, 0], visible[:, 0])
    np.testing.assert_array_equal(result["group_log_likelihood"], result["log_likelihood"])
    assert result["satellite_column"] == 0


def test_visibility_transitions_update_observed_and_nonempty_normalization():
    measured = np.array([-100.0, 150.0, 300.0])
    group = np.array([0, 0, 1])
    prepared = finite_set_likelihood.prepare_finite_set_likelihood(measured, group)
    predicted = np.array([[0.0, 50.0], [0.0, 50.0], [20.0, -30.0]])
    visible = np.ones_like(predicted, dtype=bool)
    probabilities = np.array([0.4, 0.7])
    scorer = finite_set_cavity.prepare_replacement_scorer(
        prepared,
        predicted,
        visible,
        satellite_index=1,
        detection_probability=probabilities,
        clutter_rate=0.3,
        sigma_hz=80.0,
    )
    replacement_visible = np.array([False, False, True])
    replacement_predicted = np.array([np.nan, np.nan, 75.0])
    cavity = scorer.evaluate(replacement_predicted, replacement_visible)
    direct_predicted = predicted.copy()
    direct_visible = visible.copy()
    direct_predicted[:, 1] = replacement_predicted
    direct_visible[:, 1] = replacement_visible
    direct = prepared.evaluate(
        direct_predicted,
        direct_visible,
        sigma_hz=80.0,
        detection_probability=probabilities,
        clutter_rate=0.3,
        implementation="scalar",
    )
    np.testing.assert_allclose(cavity["log_likelihood"], direct["log_likelihood"], atol=1e-12)
    np.testing.assert_allclose(
        cavity["nonempty_probability"], direct["nonempty_probability"], atol=1e-15
    )


def test_low_tail_logspace_score_remains_finite_and_matches_direct():
    alias = finite_set_likelihood.DEFAULT_ALIAS_HZ
    measured = np.array([-alias / 2 + 1.0, alias / 2 - 1.0, 0.0])
    group = np.array([0, 0, 0])
    prepared = finite_set_likelihood.prepare_finite_set_likelihood(measured, group)
    predicted = np.array([[0.0, 20_000.0], [0.0, 20_000.0], [0.0, 20_000.0]])
    visible = np.ones_like(predicted, dtype=bool)
    probabilities = np.array([0.999999, 0.999998])
    scorer = finite_set_cavity.prepare_replacement_scorer(
        prepared,
        predicted,
        visible,
        satellite_index=0,
        detection_probability=probabilities,
        clutter_rate=1e-6,
        sigma_hz=0.05,
    )
    replacement = np.full(3, alias / 3)
    cavity = scorer.evaluate(replacement, np.ones(3, dtype=bool))
    direct_predicted = predicted.copy()
    direct_predicted[:, 0] = replacement
    direct = prepared.evaluate(
        direct_predicted,
        visible,
        sigma_hz=0.05,
        detection_probability=probabilities,
        clutter_rate=1e-6,
        implementation="scalar",
    )
    assert np.all(np.isfinite(cavity["log_likelihood"]))
    np.testing.assert_allclose(cavity["log_likelihood"], direct["log_likelihood"], atol=1e-8)


def test_replacement_keeps_duplicate_and_groupwise_prediction_contracts():
    alias = finite_set_likelihood.DEFAULT_ALIAS_HZ
    measured = np.array([50.0, 50.0 + alias, -20.0])
    group = np.array([0, 0, 1])
    prepared = finite_set_likelihood.prepare_finite_set_likelihood(measured, group)
    predicted = np.zeros((3, 1))
    visible = np.ones_like(predicted, dtype=bool)
    scorer = finite_set_cavity.prepare_replacement_scorer(
        prepared,
        predicted,
        visible,
        satellite_index=0,
        detection_probability=0.8,
        clutter_rate=2.0,
        sigma_hz=200.0,
    )
    base = scorer.evaluate(np.zeros(3), np.ones(3, dtype=bool))
    alias_copy = scorer.evaluate(np.array([alias, alias, 0.0]), np.ones(3, dtype=bool))
    np.testing.assert_allclose(base["log_likelihood"], alias_copy["log_likelihood"], atol=1e-12)
    with pytest.raises(ValueError, match="groupwise equal modulo alias"):
        scorer.evaluate(np.array([0.0, 1.0, 0.0]), np.ones(3, dtype=bool))
    with pytest.raises(ValueError, match="groupwise constant"):
        scorer.evaluate(np.zeros(3), np.array([True, False, True]))
