from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import finite_set_identity_screen as screen
import numpy as np
import pytest


class FakeEvaluator:
    prepared = object()
    detection_probability = 0.2
    clutter_rate = 2.0

    def evaluate(self, predicted, visible, **kwargs):
        del visible
        assert kwargs["sigma_hz"] == 200.0
        assert kwargs["background_mass"] == 0.2
        value = float(np.sum(predicted))
        association = np.maximum(predicted, 0.0)
        return {
            "total_log_likelihood": value,
            "group_values": np.array([0, 1]),
            "row_association_probability": association,
        }


class FakeCavity:
    def __init__(self, predicted, slot, **kwargs):
        self.predicted = predicted
        self.slot = slot
        assert kwargs["detection_probability"] == 0.2

    def evaluate(self, replacement, visible):
        del visible
        direct = self.predicted.copy()
        direct[:, self.slot] = replacement
        return {"total_log_likelihood": float(np.sum(direct))}


def data_and_trial():
    data = SimpleNamespace(
        times=np.array([0.0, 1.0]),
        group=np.array([0, 1]),
        numbers=np.array([100, 200, 300, 400]),
    )
    parameters = np.zeros(10)
    parameters[[6, 7]] = [1.0, -2.0]
    baseline_prediction = np.array([[1.0, 2.0], [1.0, 2.0]])
    prior = 0.5 * (1.0**2 + (-2.0) ** 2)
    objective = -float(np.sum(baseline_prediction)) + prior
    trial = {
        "satellite_indices": np.array([0, 1]),
        "parameters": parameters,
        "satellite_weights": np.array([0.5, 0.5]),
        "objective": objective,
        "entry_penalty": np.log(2.0),
    }
    return data, trial


def plan_factory(data, satellites):
    del data
    satellites = np.asarray(satellites)

    class Plan:
        def predict(self, parameters):
            del parameters
            values = np.column_stack(
                [np.full(2, float(satellite + 1)) for satellite in satellites]
            )
            return values.ravel(), np.ones(values.size, dtype=bool), None

    return Plan()


def arms_factory(data, selected_count, full_count):
    del data
    assert selected_count == 2
    assert full_count == 4
    return {"finite_set": FakeEvaluator()}


def cavity_factory(prepared, predicted, visible, satellite_index, **kwargs):
    del prepared, visible
    return FakeCavity(predicted, satellite_index, **kwargs)


def test_all_same_k_pairs_keep_probability_penalty_and_remove_old_tau_prior():
    data, trial = data_and_trial()
    result = screen.screen_identity_replacements(
        data,
        trial,
        [0, 1, 2, 3],
        arms_factory=arms_factory,
        plan_factory=plan_factory,
        cavity_factory=cavity_factory,
    )

    assert result["complete"]
    assert result["evaluated_pair_count"] == 4
    assert result["total_pair_count"] == 4
    assert result["detection_probability_per_satellite"] == 0.2
    assert result["source_entry_penalty"] == pytest.approx(np.log(2.0))
    assert all(
        item["selection_score_improvement"] == item["objective_improvement"]
        for item in result["all_scores"]
    )
    removed_zero = [item for item in result["all_scores"] if item["removed_index"] == 0]
    removed_one = [item for item in result["all_scores"] if item["removed_index"] == 1]
    assert all(item["tau_prior_change"] == -0.5 for item in removed_zero)
    assert all(item["tau_prior_change"] == -2.0 for item in removed_one)
    assert all(item["added_index"] in (2, 3) for item in result["all_scores"])
    assert result["top3_full_dp"][0]["replacement_support_label"].endswith(
        "row_posterior_support"
    )


def test_budget_expiry_returns_honest_partial_pair_count():
    data, trial = data_and_trial()
    values = iter([0.0, 0.0, 0.0, 0.0, 61.0, 61.0])

    def clock():
        return next(values, 61.0)

    result = screen.screen_identity_replacements(
        data,
        trial,
        [0, 1, 2, 3],
        budget_s=60.0,
        clock=clock,
        arms_factory=arms_factory,
        plan_factory=plan_factory,
        cavity_factory=cavity_factory,
    )
    assert not result["complete"]
    assert result["status"] == "partial"
    assert result["evaluated_pair_count"] < result["total_pair_count"]


def test_source_and_replacement_full_dp_parity_are_enforced():
    data, trial = data_and_trial()

    class WrongCavity(FakeCavity):
        def evaluate(self, replacement, visible):
            result = super().evaluate(replacement, visible)
            result["total_log_likelihood"] += 1.0
            return result

    def wrong_factory(prepared, predicted, visible, satellite_index, **kwargs):
        del prepared, visible
        return WrongCavity(predicted, satellite_index, **kwargs)

    with pytest.raises(ValueError, match="source replacement"):
        screen.screen_identity_replacements(
            data,
            trial,
            [0, 1, 2, 3],
            arms_factory=arms_factory,
            plan_factory=plan_factory,
            cavity_factory=wrong_factory,
        )


def test_invisible_and_exact_zero_support_labels_are_descriptive_only():
    assert screen._support_label(0, 0.0) == "invisible_all_groups"
    assert screen._support_label(2, 0.0) == "exact_zero_row_posterior_support"
    assert screen._support_label(2, 1e-30) == "positive_row_posterior_support"


def test_source_closure_includes_inherited_and_direct_dependencies(tmp_path):
    inherited = tmp_path / "input.json"
    profile_path = tmp_path / "profile.json"
    grouped_path = tmp_path / "grouped.json"
    for path in (inherited, profile_path, grouped_path):
        path.write_text("sealed")
    profile = {"source_hashes": {str(inherited.resolve()): "a" * 64}}
    paths = screen.source_dependency_paths(profile, profile_path, grouped_path)
    names = {Path(path).name for path in paths}
    assert {
        "finite_set_identity_screen.py",
        "finite_set_cavity.py",
        "finite_set_rf_score.py",
        "finite_set_likelihood.py",
    } <= names
    assert str(inherited.resolve()) in paths
    order = []

    def snapshotter(received):
        order.append("snapshot")
        assert set(received) == set(paths)
        return {path: "b" * 64 for path in received}

    receipt = screen.snapshot_before_validation(
        profile, profile_path, grouped_path, snapshotter=snapshotter
    )
    order.append("validator_would_run_next")
    assert order == ["snapshot", "validator_would_run_next"]
    assert set(receipt) == set(paths)


def test_malformed_source_hash_closure_is_rejected(tmp_path):
    profile_path = tmp_path / "profile.json"
    grouped_path = tmp_path / "grouped.json"
    with pytest.raises(ValueError, match="authoritative source hashes"):
        screen.source_dependency_paths({}, profile_path, grouped_path)
    with pytest.raises(ValueError, match="malformed"):
        screen.source_dependency_paths(
            {"source_hashes": {"path": "short"}}, profile_path, grouped_path
        )


def test_run_is_limited_to_two_truth_free_pilots():
    calls = []
    receipt = screen.run(
        diagnoser=lambda unit_id, **kwargs: calls.append(unit_id) or {"unit_id": unit_id}
    )
    assert tuple(calls) == screen.SUPPORTED_UNITS
    assert len(receipt["units"]) == 2
    assert "No reference" in receipt["scope"]
