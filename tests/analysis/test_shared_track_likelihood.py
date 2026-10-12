import numpy as np
import pytest

from leo.analysis.hard60_score import likelihood
from leo.analysis.regional_position_score import ALIAS_HZ
from leo.analysis.shared_track_likelihood import shared_track_likelihood
from leo.contracts.regional_position import POSITION_SCORES

SCORE = POSITION_SCORES["V16"]


def compare_terms(actual, expected):
    assert actual.nll == expected.nll
    for field in ("responsibilities", "clutter_probability", "prediction_gradient", "residual_hz"):
        np.testing.assert_array_equal(getattr(actual, field), getattr(expected, field))


def test_disabled_and_singleton_groups_reproduce_the_original_score_exactly():
    rng = np.random.default_rng(20261012)
    measured = rng.uniform(-2e5, 2e5, 20)
    prediction = measured[:, None] + rng.normal(0, 300, (20, 4))
    visible = rng.random((20, 4)) > 0.2
    baseline = likelihood(measured, prediction, visible, SCORE)
    disabled, _ = shared_track_likelihood(
        measured, prediction, visible, SCORE, [tuple(range(20))], shared_prior=0
    )
    singleton, singleton_receipts = shared_track_likelihood(
        measured, prediction, visible, SCORE, [(i,) for i in range(20)]
    )
    compare_terms(disabled, baseline)
    compare_terms(singleton, baseline)
    np.testing.assert_allclose(
        singleton_receipts[0].identity_probabilities,
        baseline.responsibilities[0] + baseline.clutter_probability[0] / prediction.shape[1],
    )


def test_shared_identity_supports_a_weak_window_without_forcing_an_incompatible_join():
    measured = np.zeros(16)
    coherent = np.tile([0.0, 20000.0], (16, 1))
    # A weak endpoint has an alternative local match, but the continuous group
    # supplies strong evidence for candidate zero.
    coherent[-1] = [300.0, 0.0]
    visible = np.ones(coherent.shape, bool)
    baseline = likelihood(measured, coherent, visible, SCORE)
    grouped, receipt = shared_track_likelihood(
        measured, coherent, visible, SCORE, [tuple(range(16))]
    )
    assert receipt[0].posterior_shared > 0.99
    assert grouped.responsibilities[-1, 0] > baseline.responsibilities[-1, 0]
    assert grouped.responsibilities[-1, 1] < baseline.responsibilities[-1, 1]
    incompatible = coherent.copy()
    incompatible[8:] = [20000.0, 0.0]
    independent = likelihood(measured, incompatible, visible, SCORE)
    reverted, receipt = shared_track_likelihood(
        measured, incompatible, visible, SCORE, [tuple(range(16))]
    )
    assert receipt[0].posterior_shared < 1e-10
    np.testing.assert_allclose(reverted.responsibilities, independent.responsibilities, atol=1e-10)
    # The independent branch remains available with only its fixed mixture penalty.
    assert reverted.nll - independent.nll == pytest.approx(np.log(2), abs=1e-10)


@pytest.mark.parametrize("shared_prior", [0.2, 0.5, 1.0])
def test_prediction_gradient_matches_finite_differences_with_visibility_and_aliases(shared_prior):
    rng = np.random.default_rng(56)
    measured = np.array([0.0, 10.0, -50.0, ALIAS_HZ - 40.0, 55.0, 190.0])
    prediction = measured[:, None] + rng.normal(0, 200, (6, 3))
    prediction[3, 0] -= ALIAS_HZ
    visible = np.ones((6, 3), bool)
    visible[2, 1] = False
    groups = [(0, 1, 2), (3, 4, 5)]
    terms, _ = shared_track_likelihood(
        measured, prediction, visible, SCORE, groups, shared_prior=shared_prior
    )
    for row, candidate in np.ndindex(prediction.shape):
        delta = np.zeros_like(prediction)
        delta[row, candidate] = 0.001
        plus = shared_track_likelihood(
            measured, prediction + delta, visible, SCORE, groups, shared_prior=shared_prior
        )[0].nll
        minus = shared_track_likelihood(
            measured, prediction - delta, visible, SCORE, groups, shared_prior=shared_prior
        )[0].nll
        assert terms.prediction_gradient[row, candidate] == pytest.approx(
            (plus - minus) / 0.002, rel=1e-5, abs=1e-8
        )
    np.testing.assert_allclose(
        terms.responsibilities.sum(axis=1) + terms.clutter_probability, 1, atol=1e-14
    )
    assert terms.responsibilities[2, 1] == 0


def test_long_groups_remain_finite_and_all_clutter_leaves_frequency_fit_unchanged():
    prediction = np.tile([0.0, 20000.0], (1500, 1))
    measured = np.zeros(1500)
    visible = np.ones(prediction.shape, bool)
    terms, receipt = shared_track_likelihood(
        measured, prediction, visible, SCORE, [tuple(range(1500))]
    )
    assert np.isfinite(terms.nll)
    assert np.isfinite(terms.prediction_gradient).all()
    assert receipt[0].posterior_shared == pytest.approx(1)
    visible[:] = False
    baseline = likelihood(measured, prediction, visible, SCORE)
    clutter, receipt = shared_track_likelihood(
        measured, prediction, visible, SCORE, [tuple(range(1500))]
    )
    compare_terms(clutter, baseline)
    assert receipt[0].log_bayes_factor == pytest.approx(0)


@pytest.mark.parametrize("groups", [[(0, 1), (1, 2)], [(0, 0)], [(-1,)], [(3,)], [(0.5,)], [()]])
def test_invalid_or_reused_rows_cannot_duplicate_original_evidence(groups):
    with pytest.raises(ValueError, match="unique disjoint"):
        shared_track_likelihood(np.zeros(3), np.zeros((3, 2)), np.ones((3, 2), bool), SCORE, groups)
