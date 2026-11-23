from collections import Counter
from importlib import import_module
from pathlib import Path

import numpy as np
import pytest
from scipy.linalg import cho_factor, cho_solve


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("finalist_tangent")


def test_implicit_nuisance_and_volume_derivative_matches_fixed_precision(trial):
    rng = np.random.default_rng(233)
    u, du = rng.normal(size=(12, 4)), rng.normal(size=(12, 4))
    y, dy = rng.normal(size=(2, 12))
    p = rng.uniform(.7, 2, size=4)

    def profile(t):
        a, b = u + t*du, y + t*dy
        matrix = a.T @ a + np.diag(p)
        factor = cho_factor(matrix, lower=True)
        coef = cho_solve(factor, a.T@b)
        volume = np.linalg.slogdet(matrix)[1] - np.log(p).sum()
        return np.r_[b-a@coef, np.sqrt(p)*coef, np.sqrt(volume)], coef, volume, factor

    _, coefficient, volume, factor = profile(0.)
    implicit = trial.nuisance_tangent(u, y, du, dy, coefficient, p, volume, factor, cho_solve(factor, u.T).T)
    epsilon = 1e-5
    exact = (profile(epsilon)[0] - profile(-epsilon)[0]) / (2*epsilon)
    assert np.allclose(np.r_[implicit[0], implicit[1], implicit[2]], exact, rtol=1e-7, atol=1e-8)


def test_bad_local_tangents_leave_original_stopping_and_acceptance(trial):
    from tools.pipeline_eval.variants.compact_cavity_optimizer import bounded_secant

    def residual(point):
        return point - np.array([1., 2.])

    for wrong in (np.zeros((2, 2)), -np.eye(2)):
        audit = Counter()
        with_tangent = trial.change_optimizer(bounded_secant, lambda *_: wrong.copy(), audit)
        result = with_tangent(residual, np.zeros(2), np.full(2, -5.), np.full(2, 5.), iterations=12)
        assert result["stopped"] == "small_bounded_step"
        assert np.linalg.norm(result["parameters"] - np.array([1., 2.])) < 1e-6
        path = [item["score"] for item in result["history"]]
        assert all(b < a for a, b in zip(path, path[1:]))
        assert audit["exact_linearizations"] > 0
        if wrong[0, 0] < 0:
            assert audit["exact_retries"] == 1
