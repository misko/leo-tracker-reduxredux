from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from compact_satellite_selection import (
    _refit_shortlist,
    _same_observations,
    competitive_addition_scores,
    complexity_penalty,
    fixed_detection_probability,
    fixed_position_bounds,
    neighborhood_sets,
    remap_parameters,
    selected_indices_by_catalog,
    timing_prior,
)
from finite_set_likelihood import prepare_finite_set_likelihood


def test_fixed_probability_and_predeclared_penalty_do_not_renormalize_with_new_k():
    probability = fixed_detection_probability(16)
    assert probability == 0.05
    assert probability == fixed_detection_probability(16)
    assert complexity_penalty(100, 9) - complexity_penalty(100, 8) == pytest.approx(
        0.5 * np.log(100)
    )
    with pytest.raises(ValueError):
        fixed_detection_probability(0)


def test_timing_prior_uses_common_and_zero_sum_individual_components():
    shifts = np.array([1.0, 2.0, 3.0])
    expected = 0.5 * np.sum(np.array([-1.0, 0.0, 1.0]) ** 2) + 0.5 * (2.0 / 10.0) ** 2
    assert timing_prior(shifts) == pytest.approx(expected)


def test_compact_refit_bounds_fix_both_position_coordinates_exactly():
    bounds = [(-200.0, 200.0), (-200.0, 200.0), (None, None)]
    fixed = fixed_position_bounds(bounds, [-12.5, 8.25])
    assert fixed[:2] == [(-12.5, -12.5), (8.25, 8.25)]
    assert fixed[2] == bounds[2]
    assert bounds[:2] == [(-200.0, 200.0), (-200.0, 200.0)]


def test_parameter_remap_preserves_selected_catalogue_timings_and_sets_inactive_to_mean():
    source_numbers = np.array([30, 10, 20])
    source_parameters = np.r_[np.arange(6.0), [7.0, 8.0, 9.0]]
    expanded_numbers = np.array([20, 40, 10, 30])
    remapped, selected = remap_parameters(
        source_parameters, source_numbers, np.array([2, 0]), expanded_numbers
    )
    np.testing.assert_array_equal(selected, [0, 3])
    np.testing.assert_array_equal(remapped[:6], source_parameters[:6])
    np.testing.assert_array_equal(remapped[6 + selected], [9.0, 7.0])
    np.testing.assert_array_equal(remapped[6 + np.array([1, 2])], [8.0, 8.0])
    with pytest.raises(ValueError, match="missing"):
        selected_indices_by_catalog(expanded_numbers, [999])


def test_expanded_bank_must_preserve_every_grouped_observation():
    source = SimpleNamespace(
        times=np.array([1.0, 2.0]),
        measured=np.array([3.0, 4.0]),
        rf=np.array([5.0, 6.0]),
        receiver=np.array([0, 1]),
        channel=np.array([1, 2]),
        group=np.array([10, 11]),
    )
    expanded = SimpleNamespace(
        **{key: np.asarray(value).copy() for key, value in vars(source).items()}
    )
    _same_observations(source, expanded)
    expanded.measured[0] += 1.0
    with pytest.raises(ValueError, match="measured"):
        _same_observations(source, expanded)


def test_neighborhood_includes_baseline_all_drop_add_and_swap_moves():
    screening = [{"satellite_index": 3}, {"satellite_index": 4}]
    rows = neighborhood_sets([0, 1, 2], screening, shortlist_size=2)
    moves = {move for move, _ in rows}
    assert "baseline" in moves
    assert {"drop:0", "drop:1", "drop:2"} <= moves
    assert {"add:3", "add:4"} <= moves
    assert "swap:2->4" in moves
    assert len(rows) == 1 + 3 + 2 + 6


def test_competitive_addition_score_matches_full_finite_set_with_duplicates():
    measured = np.array([10.0, 10.0, 80.0, -40.0])
    groups = np.array([0, 0, 0, 1])
    prepared = prepare_finite_set_likelihood(measured, groups)
    incumbent_prediction = np.array([[0.0], [0.0], [0.0], [-20.0]])
    incumbent_visible = np.ones_like(incumbent_prediction, dtype=bool)
    baseline = prepared.evaluate(
        incumbent_prediction,
        incumbent_visible,
        sigma_hz=200.0,
        detection_probability=0.2,
        clutter_rate=2.0,
    )
    candidate_prediction = np.array([[70.0], [70.0], [70.0], [30.0]])
    candidate_visible = np.ones_like(candidate_prediction, dtype=bool)
    score = competitive_addition_scores(
        prepared,
        baseline,
        candidate_prediction,
        candidate_visible,
        0.2,
    )
    combined = prepared.evaluate(
        np.column_stack([incumbent_prediction, candidate_prediction]),
        np.column_stack([incumbent_visible, candidate_visible]),
        sigma_hz=200.0,
        detection_probability=0.2,
        clutter_rate=2.0,
    )
    np.testing.assert_allclose(
        score["log_likelihood_change"],
        combined["total_log_likelihood"] - baseline["total_log_likelihood"],
        rtol=0.0,
        atol=1e-10,
    )
    np.testing.assert_allclose(
        score["candidate_expected_group_support"],
        combined["satellite_support"][-1],
        rtol=0.0,
        atol=1e-10,
    )


def test_refit_selection_uses_penalized_objective_not_success_or_support():
    data = SimpleNamespace(group=np.arange(10), numbers=np.arange(5))
    neighborhood = [
        {
            "move": "candidate",
            "satellite_indices": (0, 1),
            "parameters": np.zeros(11),
            "penalized_objective": 1.0,
        },
        {
            "move": "baseline",
            "satellite_indices": (0, 1, 2),
            "parameters": np.zeros(11),
            "penalized_objective": 2.0,
        },
    ]

    def fitter(_data, _initial, satellites, _probability, _coefficient, *, budget_s):
        count = len(satellites)
        return {
            "objective": 5.0 if count == 2 else 4.0,
            "success": count == 3,
            "status": "optimizer_stopped" if count == 2 else "optimizer_converged",
            "parameters": np.zeros(11),
            "budget_s": budget_s,
        }

    clock = iter([0.0, 0.0, 0.0, 0.0]).__next__
    rows, selected = _refit_shortlist(
        data,
        neighborhood,
        np.array([0, 1, 2]),
        0.2,
        np.array([0.0]),
        10.0,
        clock=clock,
        fitter=fitter,
    )
    assert len(rows) == 2
    assert selected["move"] == "candidate"
    assert selected["fit"]["success"] is False


def test_refit_budget_exhaustion_preserves_unattempted_finalist():
    data = SimpleNamespace(group=np.arange(4), numbers=np.arange(3))
    neighborhood = [
        {
            "move": "baseline",
            "satellite_indices": (0, 1),
            "parameters": np.zeros(9),
            "penalized_objective": 1.0,
        },
        {
            "move": "drop:1",
            "satellite_indices": (0,),
            "parameters": np.zeros(9),
            "penalized_objective": 2.0,
        },
    ]
    calls = iter([0.0, 0.9])

    def fitter(_data, _initial, satellites, _probability, _coefficient, *, budget_s):
        return {
            "objective": float(len(satellites)),
            "success": True,
            "status": "optimizer_converged",
            "parameters": np.zeros(9),
            "budget_s": budget_s,
        }

    rows, selected = _refit_shortlist(
        data,
        neighborhood,
        np.array([0, 1]),
        0.4,
        np.array([0.0]),
        1.0,
        clock=lambda: next(calls),
        fitter=fitter,
    )
    assert rows[0]["attempted"] is True
    assert rows[1]["attempted"] is False
    assert selected["move"] == "baseline"
