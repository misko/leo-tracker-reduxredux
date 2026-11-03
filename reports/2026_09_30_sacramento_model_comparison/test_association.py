"""Component tests for clean-room association baselines."""

from __future__ import annotations

import importlib.util
import sys
from itertools import product
from math import exp, isclose, log
from pathlib import Path

import numpy as np
import pytest

MODULE_PATH = Path(__file__).with_name("association.py")
SPEC = importlib.util.spec_from_file_location("sacramento_association", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
association = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = association
SPEC.loader.exec_module(association)


def problem(signal: list[list[float]], background: list[float]):
    return association.AssociationProblem(
        np.array(signal),
        np.array(background),
        tuple(f"sat-{i}" for i in range(len(signal[0]))),
    )


def brute_force_best(value):
    n_rows, n_candidates = value.log_signal_scores.shape
    best = None
    for choices in product(range(-1, n_candidates), repeat=n_rows):
        selected = [choice for choice in choices if choice >= 0]
        if len(selected) != len(set(selected)):
            continue
        score = sum(
            value.log_background_scores[row]
            if choice == -1
            else value.log_signal_scores[row, choice]
            for row, choice in enumerate(choices)
        )
        if best is None or score > best[0]:
            best = (score, choices)
    assert best is not None
    return best


def test_hungarian_matches_brute_force_with_background() -> None:
    value = problem([[9.0, 8.0], [8.5, -np.inf], [0.0, 7.0]], [1.0, 2.0, 6.0])
    result = association.hungarian_association(value)
    score, choices = brute_force_best(value)
    expected = tuple(None if item == -1 else value.candidate_labels[item] for item in choices)
    assert result.hard_assignments == expected
    assert isclose(result.joint_hypotheses[0].log_score, score)
    assert not result.probabilities_are_calibrated
    assert result.candidate_exclusivity_assumed


def test_scipy_hungarian_matches_clean_room_when_available() -> None:
    pytest.importorskip("scipy")
    value = problem([[9.0, 8.0], [8.5, -np.inf], [0.0, 7.0]], [1.0, 2.0, 6.0])
    expected = association.hungarian_association(value)
    actual = association.scipy_hungarian_association(value)
    assert actual.method == "scipy-linear-sum-assignment-v1"
    assert actual.hard_assignments == expected.hard_assignments
    assert actual.joint_hypotheses[0].log_score == expected.joint_hypotheses[0].log_score


def test_exact_joint_probabilities_preserve_mass_and_match_manual() -> None:
    value = problem([[log(3), log(2)], [log(5), log(7)]], [0.0, 0.0])
    result = association.exact_joint_association(value)
    # Feasible weights: BB=1, A/B singles=3+2+5+7, and distinct pairs=21+10.
    assert isclose(exp(result.joint_log_evidence), 49.0)
    np.testing.assert_allclose(
        result.signal_probabilities.sum(axis=1) + result.background_probabilities,
        np.ones(2),
    )
    assert isclose(result.retained_probability, 1.0)
    assert isclose(result.discarded_probability, 0.0)
    assert result.hard_assignments == ("sat-0", "sat-1")


def test_retained_joint_hypotheses_report_discarded_probability() -> None:
    result = association.exact_joint_association(
        problem([[0.0, 0.0], [0.0, 0.0]], [0.0, 0.0]), retained_hypotheses=2
    )
    assert len(result.joint_hypotheses) == 2
    assert 0.0 < result.retained_probability < 1.0
    assert isclose(result.retained_probability + result.discarded_probability, 1.0)
    # Marginals remain exact even when only the leading hypotheses are serialized.
    np.testing.assert_allclose(
        result.signal_probabilities.sum(axis=1) + result.background_probabilities,
        np.ones(2),
    )


def test_exact_oracle_fails_before_exceeding_budget() -> None:
    with pytest.raises(association.AssociationBudgetError, match="exceeds"):
        association.exact_joint_association(
            problem(np.zeros((8, 8)).tolist(), np.zeros(8).tolist()), max_events=1000
        )


def test_analytic_large_pair_matches_small_enumeration() -> None:
    value = problem([[1.0, 2.0, 3.0], [3.0, 1.0, 2.0]], [0.5, -0.5])
    enumerated = association.exact_joint_association(value, max_events=100)
    analytic = association.exact_joint_association(
        value, max_events=1, retained_hypotheses=1
    )
    assert analytic.method == "exact-pair-jpda-analytic-v1"
    assert analytic.joint_log_evidence == pytest.approx(enumerated.joint_log_evidence)
    np.testing.assert_allclose(analytic.signal_probabilities, enumerated.signal_probabilities)
    np.testing.assert_allclose(
        analytic.background_probabilities, enumerated.background_probabilities
    )
    assert analytic.retained_probability + analytic.discarded_probability == pytest.approx(1.0)


def test_analytic_pair_is_stable_when_same_candidate_dominates() -> None:
    value = problem([[0.0], [0.0]], [-1000.0, -1000.0])
    result = association.exact_joint_association(value, max_events=1, retained_hypotheses=1)
    assert np.isfinite(result.joint_log_evidence)
    assert result.joint_log_evidence == pytest.approx(log(2.0) - 1000.0)
    np.testing.assert_allclose(result.signal_probabilities, [[0.5], [0.5]])
    np.testing.assert_allclose(result.background_probabilities, [0.5, 0.5])


def test_stone_soup_feasibility_has_exact_jpda_semantics() -> None:
    value = problem([[1.0], [2.0]], [0.0, 0.0])
    exact = association.exact_joint_association(value)
    adapted = association.stone_soup_jpda_feasibility(value)
    assert adapted.method == "stone-soup-jpda-feasibility-v1"
    assert adapted.joint_log_evidence == exact.joint_log_evidence
    np.testing.assert_array_equal(adapted.signal_probabilities, exact.signal_probabilities)
    np.testing.assert_array_equal(adapted.background_probabilities, exact.background_probabilities)


def test_pinned_stonesoup_library_matches_exact_oracle_when_available() -> None:
    pytest.importorskip("stonesoup")
    value = problem([[1.0, 0.5], [0.25, 1.5]], [-0.2, 0.1])
    exact = association.exact_joint_association(value)
    actual = association.stonesoup_library_jpda_association(value, max_events=100)
    assert actual.method == "stonesoup-jpda-e5a3e09f-v1"
    np.testing.assert_allclose(actual.signal_probabilities, exact.signal_probabilities)
    np.testing.assert_allclose(actual.background_probabilities, exact.background_probabilities)


@pytest.mark.parametrize(
    ("signal", "background", "message"),
    [
        ([[0.0, np.nan]], [0.0], "negative infinity"),
        ([[0.0]], [np.inf], "finite background"),
    ],
)
def test_invalid_scores_rejected(signal, background, message) -> None:
    with pytest.raises(association.AssociationInputError, match=message):
        problem(signal, background)
