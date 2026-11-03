from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from leo.analysis.gaussian_sum_location import Candidate, ObservationFactor, Prediction
from leo.analysis.greedy_joint_location import fit_joint_greedy
from leo.analysis.localization_evaluation import ObservationFactorTrackPort
from leo.analysis.localization_fast import fit_localization_fast
from leo.analysis.robust_likelihood import student_t_logpdf


def _factor(identifier: str, observation: float, rows: tuple[tuple[float, ...], ...]):
    covariance = np.array([[0.4]])
    candidates = []
    for index, row in enumerate(rows):
        matrix = np.asarray(row, dtype=float).reshape(1, -1)
        candidates.append(
            Candidate(
                f"{identifier}-{index}",
                1.0 / len(rows),
                lambda state, matrix=matrix: Prediction(
                    matrix @ state, matrix, covariance
                ),
            )
        )
    return ObservationFactor(
        (identifier,), np.array([observation]), tuple(candidates), 0.05, -12.0
    )


def _score(factor: ObservationFactor, degrees_of_freedom: float | None = None):
    def score(state: np.ndarray) -> np.ndarray:
        values = []
        for candidate in factor.candidates:
            prediction = candidate.predict(state)
            residual = factor.observation - prediction.mean
            if degrees_of_freedom is None:
                variance = prediction.covariance[0, 0]
                likelihood = -0.5 * (
                    np.log(2.0 * np.pi * variance) + residual[0] ** 2 / variance
                )
            else:
                likelihood = student_t_logpdf(
                    residual, prediction.covariance, degrees_of_freedom
                )
            values.append(np.log(candidate.prior) + likelihood)
        values.append(np.log(factor.background_prior) + factor.background_log_likelihood)
        return np.asarray(values)

    return score


@pytest.mark.parametrize("degrees_of_freedom", [None, 4.0])
def test_matches_existing_solver_for_affine_reassignment_and_robust_fit(
    degrees_of_freedom: float | None,
) -> None:
    factors = (
        _factor("a", 3.0, ((1.0, 1.0), (-1.0, 0.2))),
        _factor("b", 1.0, ((1.0, -1.0), (0.1, 1.0))),
        _factor("outlier", 30.0, ((1.0, 0.0), (-1.0, 0.0))),
    )
    scorers = tuple(_score(factor, degrees_of_freedom) for factor in factors)
    ports = tuple(
        ObservationFactorTrackPort(factor, scorer, degrees_of_freedom)
        for factor, scorer in zip(factors, scorers, strict=True)
    )
    arguments = (
        np.array([-4.0, 2.0]),
        np.array([0.01, 0.01]),
        lambda _state: True,
    )
    old = fit_joint_greedy(
        arguments[0],
        factors,
        scorers,
        arguments[1],
        arguments[2],
        degrees_of_freedom=degrees_of_freedom,
    )
    new = fit_localization_fast(
        arguments[0],
        ports,
        arguments[1],
        arguments[2],
        degrees_of_freedom=degrees_of_freedom,
    )
    np.testing.assert_allclose(new.mean, old.mean, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(new.objectives, old.objectives, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(
        new.accepted_step_norms, old.accepted_step_norms, rtol=1e-12, atol=1e-12
    )
    assert new.associations == old.associations
    assert (new.converged, new.iterations, new.reason) == (
        old.converged,
        old.iterations,
        old.reason,
    )


def test_matches_all_background_status_without_requesting_a_prediction() -> None:
    factor = _factor("background", 0.0, ((1.0,),))

    @dataclass
    class BackgroundPort:
        observation_ids = factor.observation_ids
        observation = factor.observation
        candidate_count = 1
        prediction_calls: int = 0

        def score_all(self, _state):
            return np.array([-np.inf, -1.0])

        def score_selected(self, _state, index):
            return (-np.inf, -1.0)[index]

        def predict_selected(self, _state, _index):
            self.prediction_calls += 1
            raise AssertionError("background must not request a satellite prediction")

    port = BackgroundPort()
    result = fit_localization_fast(
        np.zeros(1), (port,), np.ones(1), lambda _state: True
    )
    assert not result.converged
    assert result.reason == "all_background"
    assert result.associations == (1,)
    assert port.prediction_calls == 0


def test_line_search_uses_scores_and_selected_prediction_only_for_the_step() -> None:
    factor = _factor("counted", 2.0, ((1.0,),))
    scorer = _score(factor)

    @dataclass
    class CountingPort:
        observation_ids = factor.observation_ids
        observation = factor.observation
        candidate_count = 1
        score_calls: int = 0
        selected_score_calls: int = 0
        prediction_calls: int = 0

        def score_all(self, state):
            self.score_calls += 1
            return scorer(state)

        def score_selected(self, state, index):
            self.selected_score_calls += 1
            return scorer(state)[index]

        def predict_selected(self, state, index):
            self.prediction_calls += 1
            return factor.candidates[index].predict(state)

    port = CountingPort()
    result = fit_localization_fast(
        np.zeros(1), (port,), np.zeros(1), lambda _state: True, max_iterations=1
    )
    assert result.iterations == 1
    assert port.prediction_calls == 1
    assert port.score_calls == 1
    assert port.selected_score_calls >= 3  # guard, current objective, and line search


def test_adapter_rejects_background_as_selected_prediction() -> None:
    factor = _factor("adapter", 0.0, ((1.0,),))
    port = ObservationFactorTrackPort(factor, _score(factor))
    assert port.candidate_count == 1
    np.testing.assert_array_equal(port.score_all(np.zeros(1)), _score(factor)(np.zeros(1)))
    assert port.score_selected(np.zeros(1), 0) == pytest.approx(port.score_all(np.zeros(1))[0])
    with pytest.raises(IndexError, match="out of range"):
        port.predict_selected(np.zeros(1), port.candidate_count)


def test_invalid_scores_and_duplicate_physical_observations_are_rejected() -> None:
    factor = _factor("same", 0.0, ((1.0,),))
    invalid = ObservationFactorTrackPort(factor, lambda _state: np.array([np.nan, -1.0]))
    with pytest.raises(ValueError, match="invalid branch scores"):
        fit_localization_fast(
            np.zeros(1), (invalid,), np.ones(1), lambda _state: True
        )

    valid = ObservationFactorTrackPort(factor, _score(factor))
    with pytest.raises(ValueError, match="must not be reused"):
        fit_localization_fast(
            np.zeros(1), (valid, valid), np.ones(1), lambda _state: True
        )


def test_selected_score_mismatch_and_ineligible_prediction_are_rejected() -> None:
    factor = _factor("guard", 0.0, ((1.0,),))

    @dataclass
    class GuardPort:
        observation_ids = factor.observation_ids
        observation = factor.observation
        candidate_count = 1
        mismatch: bool = False
        eligible: bool = True

        def score_all(self, state):
            return _score(factor)(state)

        def score_selected(self, state, index):
            value = _score(factor)(state)[index]
            return value + 1.0 if self.mismatch else value

        def predict_selected(self, state, index):
            prediction = factor.candidates[index].predict(state)
            return Prediction(
                prediction.mean,
                prediction.jacobian,
                prediction.covariance,
                eligible=self.eligible,
            )

    with pytest.raises(ValueError, match="selected physical score"):
        fit_localization_fast(
            np.zeros(1), (GuardPort(mismatch=True),), np.ones(1), lambda _state: True
        )
    with pytest.raises(ValueError, match="ineligible"):
        fit_localization_fast(
            np.zeros(1), (GuardPort(eligible=False),), np.ones(1), lambda _state: True
        )
