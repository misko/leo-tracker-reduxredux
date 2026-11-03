import numpy as np
import pytest
from finite_set_fit import FiniteSetLikelihoodAdapter
from finite_set_likelihood import prepare_finite_set_likelihood
from finite_set_sparse import SparseFiniteSetLikelihoodAdapter


def evaluate(prepared, predicted, visible, cutoff=1e-16, sigma=200):
    options = dict(sigma_hz=sigma, satellite_weights=np.ones(predicted.shape[1]),
                   background_mass=.2, return_gradient=True, return_precision=True)
    dense = FiniteSetLikelihoodAdapter(prepared, .2).evaluate(predicted, visible, **options)
    sparse = SparseFiniteSetLikelihoodAdapter(prepared, .2, odds_cutoff=cutoff).evaluate(
        predicted, visible, **options,
    )
    return dense, sparse


@pytest.mark.parametrize("duplicate", [False, True])
def test_dense_parity_with_duplicate_aliases_and_invisible_satellites(duplicate):
    measured = np.array([100., 20000., 300., 23000.])
    groups = np.array([0, 0, 1, 1])
    predicted = np.tile([150., 50000., 22000., 90000.], (4, 1))
    visible = np.tile([True, True, True, False], (4, 1))
    if duplicate:
        measured = np.r_[measured, measured[0] + 1 / 4.4e-6]
        groups = np.r_[groups, 0]
        predicted = np.vstack([predicted, predicted[0]])
        visible = np.vstack([visible, visible[0]])
    prepared = prepare_finite_set_likelihood(measured, groups)
    dense, sparse = evaluate(prepared, predicted, visible)
    assert sparse["packed_satellite_count"] < predicted.shape[1]
    for name in ["log_likelihood", "unconditioned_log_likelihood", "empty_probability",
                 "nonempty_probability", "association_probability", "row_association_probability",
                 "clutter_probability", "satellite_miss_probability", "prediction_gradient",
                 "prediction_precision", "satellite_support"]:
        np.testing.assert_allclose(sparse[name], dense[name], atol=1e-11, rtol=1e-10)


@pytest.mark.parametrize("cutoff", [1e-16, .01, 1., 10000.])
def test_omission_bound_covers_full_log_likelihood(cutoff):
    generator = np.random.default_rng(823)
    measured = generator.uniform(-1000, 1000, 30)
    groups = np.repeat(np.arange(10), 3)
    predicted = np.repeat(generator.uniform(-2000, 2000, (10, 7)), 3, axis=0)
    visible = np.repeat(generator.uniform(size=(10, 7)) > .2, 3, axis=0)
    prepared = prepare_finite_set_likelihood(measured, groups)
    dense, sparse = evaluate(prepared, predicted, visible, cutoff=cutoff)
    difference = dense["log_likelihood"] - sparse["log_likelihood"]
    assert np.all(difference >= -1e-11)
    assert np.all(difference <= sparse["omitted_log_likelihood_upper_bound_per_group"] + 1e-11)
    np.testing.assert_allclose(dense["nonempty_probability"], sparse["nonempty_probability"])


def test_all_far_predictions_keep_misses_and_full_normalization():
    prepared = prepare_finite_set_likelihood(np.array([0., 100.]), np.array([0, 0]))
    dense, sparse = evaluate(prepared, np.full((2, 4), 50000.), np.ones((2, 4), bool))
    assert sparse["packed_satellite_count"] == 0
    np.testing.assert_allclose(sparse["log_likelihood"], dense["log_likelihood"], atol=1e-12)
    np.testing.assert_array_equal(sparse["satellite_miss_probability"], np.ones((1, 4)))
    assert sparse["prediction_gradient"].shape == (2, 4)


def test_conflicting_far_prediction_cannot_be_hidden_by_packing():
    prepared = prepare_finite_set_likelihood(np.array([0., 100.]), np.array([0, 0]))
    predicted = np.array([[50000.], [50001.]])
    with pytest.raises(ValueError, match="groupwise equal"):
        evaluate(prepared, predicted, np.ones((2, 1), bool))


def test_invalid_visibility_cannot_be_hidden_by_packing():
    prepared = prepare_finite_set_likelihood(np.array([0., 100.]), np.array([0, 0]))
    with pytest.raises(ValueError, match="groupwise constant"):
        SparseFiniteSetLikelihoodAdapter(prepared, .2).evaluate(
            np.full((2, 1), 50000.), np.array([[True], [False]]),
            sigma_hz=200, satellite_weights=np.ones(1), background_mass=.2,
        )


def test_gradient_matches_groupwise_finite_difference():
    prepared = prepare_finite_set_likelihood(np.array([0., 100.]), np.array([0, 0]))
    adapter = SparseFiniteSetLikelihoodAdapter(prepared, .2)
    predicted = np.tile([40., 50000.], (2, 1))
    options = dict(sigma_hz=200, satellite_weights=np.ones(2), background_mass=.2,
                   return_gradient=True)
    visible = np.ones_like(predicted, dtype=bool)
    result = adapter.evaluate(predicted, visible, **options)
    for column in range(2):
        perturbation = np.zeros_like(predicted)
        perturbation[:, column] = .001
        plus = adapter.evaluate(predicted + perturbation, visible, **options)
        minus = adapter.evaluate(predicted - perturbation, visible, **options)
        numerical = (plus["total_log_likelihood"] - minus["total_log_likelihood"]) / .002
        assert numerical == pytest.approx(np.sum(result["prediction_gradient"][:, column]),
                                           abs=1e-9)


def test_zero_candidate_bank():
    prepared = prepare_finite_set_likelihood(np.array([0.]), np.array([0]))
    dense, sparse = evaluate(prepared, np.empty((1, 0)), np.empty((1, 0), dtype=bool))
    np.testing.assert_allclose(sparse["log_likelihood"], dense["log_likelihood"])
    assert sparse["prediction_gradient"].shape == (1, 0)
