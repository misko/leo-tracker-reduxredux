from types import SimpleNamespace

import finite_set_tau_profile as profile
import numpy as np
import pytest


class QuadraticPrepared:
    def evaluate(self, means, visible, **options):
        return {"total_log_likelihood": -0.5 * float((np.sum(means) - 2.) ** 2)}


class QuadraticCavity:
    def __init__(self, prepared, means, visible, column, **options):
        self.prepared = prepared
        self.means = means.copy()
        self.column = column

    def evaluate(self, mean, visible):
        means = self.means.copy()
        means[:, self.column] = mean
        return self.prepared.evaluate(means, visible)


def predictor(data, parameters, satellites):
    return parameters[6 + satellites][None, :].copy(), np.ones((1, len(satellites)), dtype=bool)


def test_sequential_profiles_include_prior_and_rebuild_after_each_update():
    initial = np.zeros(8)
    result = profile.profile_timing_offsets(
        SimpleNamespace(), initial, [0, 1], QuadraticPrepared(),
        cavity_factory=QuadraticCavity, detection_probability=0.1,
        predictor=predictor, step_s=0.5,
    )
    np.testing.assert_array_equal(initial, np.zeros(8))
    np.testing.assert_array_equal(result["parameters"][6:], [1., 0.5])
    assert result["initial_objective"] == pytest.approx(2.)
    assert result["objective"] == pytest.approx(0.75)
    assert result["complete"]


def test_grid_includes_off_grid_incumbent_and_both_bounds():
    values = profile.timing_grid(0.123, step_s=0.5)
    assert values[0] == 0.123
    assert -3. in values and 3. in values
    with pytest.raises(ValueError):
        profile.timing_grid(3.1)


def test_budget_preserves_incumbent_and_does_not_claim_completed_search(monkeypatch):
    clock = iter(range(100))
    monkeypatch.setattr(profile.time, "monotonic", lambda: next(clock))
    initial = np.zeros(8)
    result = profile.profile_timing_offsets(
        SimpleNamespace(), initial, [0, 1], QuadraticPrepared(),
        cavity_factory=QuadraticCavity, detection_probability=0.1,
        predictor=predictor, budget_s=0.01,
    )
    assert not result["complete"]
    assert result["profiles"] == []
    np.testing.assert_array_equal(result["parameters"], initial)


def test_cavity_reproduction_failure_is_not_silently_accepted():
    class Broken(QuadraticCavity):
        def evaluate(self, mean, visible):
            return {"total_log_likelihood": -100.}

    with pytest.raises(ValueError, match="reproduce"):
        profile.profile_timing_offsets(
            SimpleNamespace(), np.zeros(8), [0, 1], QuadraticPrepared(),
            cavity_factory=Broken, detection_probability=0.1, predictor=predictor,
        )


def test_prediction_geometry_is_cached_across_grid_nodes(monkeypatch):
    constructed = []

    class Plan:
        def __init__(self, data, satellites):
            self.satellites = satellites
            constructed.append(tuple(satellites))

        def predict(self, parameters):
            return parameters[6 + self.satellites], np.ones(len(self.satellites), dtype=bool), None

    monkeypatch.setattr(profile, "SharedPredictionPlan", Plan)
    result = profile.profile_timing_offsets(
        SimpleNamespace(times=np.zeros(1)), np.zeros(8), [0, 1], QuadraticPrepared(),
        cavity_factory=QuadraticCavity, detection_probability=0.1, step_s=0.5,
    )
    assert result["complete"]
    assert constructed == [(0, 1), (0,), (1,)]
