from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants import algo08_temporal_trust as method


def test_interpolation_reconstructs_quadratic_local_frequency_derivatives():
    first = np.arange(0.0, 43.0, 1.25)
    second = np.r_[8.5, 9, 13, np.arange(20.0, 38.0)]
    times = np.r_[first, second]
    layout = method.temporal_layout(times, [slice(0, len(first)), slice(len(first), len(times))])
    fields = np.column_stack((3 + 4 * times + times**2, 1.5 - 0.7 * times + 0.8 * times**2))
    assert len(layout.nodes) < len(times) / 2
    np.testing.assert_allclose(layout.interpolate(fields[layout.nodes]), fields, rtol=2e-13)


def test_frozen_precision_jacobian_replays_whitened_residual_and_prior():
    rng = np.random.default_rng(300)
    design, raw, tangent = rng.normal(size=(13, 4)), rng.normal(size=13), rng.normal(size=(13, 2))
    prior = np.array([0.1, 3, 4, 0.5])

    def calculate(y):
        fitted = np.linalg.solve(design.T @ design + np.diag(prior), design.T @ y)
        return y - design @ fitted, np.sqrt(prior) * fitted

    increment = 1e-4 * np.array([0.6, -0.4])
    exact = calculate(raw + tangent @ increment)
    original = calculate(raw)
    jacobians = method.profile_jacobian(design, prior, tangent)
    for observed, initial, jacobian in zip(exact, original, jacobians, strict=True):
        np.testing.assert_allclose(observed, initial + jacobian @ increment, atol=1e-13)


@pytest.mark.parametrize("direction", (1.0, -1.0))
def test_temporal_proposals_get_exact_scores_and_bad_tangent_uses_stock(direction, monkeypatch):
    target = np.array([2.2, -0.4])

    def calculate(point):
        return {"residual": point - target, "elevation": np.array([1.0])}

    def objective(point):
        return np.r_[point - target, 0.0]

    fake = SimpleNamespace(calculate=calculate, keep=np.array([True]))
    layout = SimpleNamespace(nodes=np.array([0, 2]), length=4)
    monkeypatch.setattr(method, "layout_for", lambda problem: layout)
    monkeypatch.setattr(method, "proposal_jacobian",
                        lambda *args: direction * np.vstack((np.eye(2), np.zeros(2))))
    counters = Counter()
    result = method.proposed_fit(
        fake, counters, objective, (0., 0.), np.array([-3., -3.]), np.array([3., 3.]), 12, 0.001,
    )
    assert counters["approximate_calls"] == 2
    assert counters["fallbacks"] == (direction < 0)
    assert counters["exact_calls"] > 1
    for row in result["history"]:
        evaluated = objective(row["parameters"])
        assert row["score"] == evaluated @ evaluated
    assert np.linalg.norm(result["parameters"] - target) < 1e-3
