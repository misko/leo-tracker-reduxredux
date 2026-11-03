import copy
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))
from ds7_slope_identifiability import evaluate, observed_hessian, retention  # noqa: E402


def example():
    t = np.arange(16, dtype=float)
    design = np.stack([t**2, np.sin(t), np.cos(t)], axis=-1)
    track = {
        "mask": np.arange(16) % 3 != 0,
        "rf_hz": 11_200_000_000,
        "times_s": t,
        "y": 3 + 0.3 * t + 0.05 * t**2,
        "catalogue_size": 2,
    }

    def predict(track, x):
        a = design @ x
        return np.stack([a, a + 5 * np.sin(t / 3)]), np.ones(2, dtype=bool)

    return track, predict


def test_full_mixture_gradient_curvature_and_held_independence():
    track, predict = example()
    x = np.array([0.01, 0.02, 0.03, 0.04])

    def fn(point):
        return evaluate([track], predict, point)

    got = fn(x)
    for axis in range(4):
        delta = np.eye(4)[axis] * 1e-4
        numerical = (fn(x + delta)["score"] - fn(x - delta)["score"]) / 2e-4
        assert got["gradient"][axis] == pytest.approx(numerical, abs=1e-6)
    h, _ = observed_hessian(fn, x, np.full(4, 1e-3))
    assert h == pytest.approx(h.T, abs=1e-6)
    direction = np.array([0.2, -0.3, 0.4, 0.1])
    step = 1e-3
    second = (
        -(fn(x + step * direction)["score"] - 2 * got["score"] + fn(x - step * direction)["score"])
        / step**2
    )
    assert direction @ h @ direction == pytest.approx(second, abs=1e-5)
    changed = copy.deepcopy(track)
    changed["y"][~changed["mask"]] += 100000
    other = evaluate([changed], predict, x)
    for key in ("score", "gradient", "fisher"):
        assert other[key] == pytest.approx(got[key], abs=1e-12)


def test_schur_retention_detects_confounding_and_independence():
    assert retention(np.eye(4))["information_retention_eigenvalues"] == pytest.approx([1, 1])
    matrix = np.eye(4)
    matrix[0, 3] = matrix[3, 0] = 0.99
    result = retention(matrix)
    assert result["information_retention_eigenvalues"] == pytest.approx([1 - 0.99**2, 1])
    assert result["worst_direction_standard_error_inflation"] > 7
    matrix[3, 3] = -1
    assert retention(matrix)["status"] == "nonpositive_nuisance_block"
