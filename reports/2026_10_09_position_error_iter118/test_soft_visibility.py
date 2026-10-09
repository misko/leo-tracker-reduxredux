import runpy
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.hard60_score import likelihood as hard
from leo.application.hard60_runner import HARD60_SCORE

soft = runpy.run_path(str(Path(__file__).with_name("soft_visibility.py")))["likelihood"]


def test_binary_limit_matches_hard_normalization_and_gradient():
    y = np.array([0.0, 50.0])
    p = np.array([[1.0, 100.0, 200.0], [50.0, 300.0, 1000.0]])
    v = np.array([[1, 0, 1], [0, 1, 1]], bool)
    a = hard(y, p, v, HARD60_SCORE)
    b = soft(y, p, v, HARD60_SCORE)
    assert b["nll"] == pytest.approx(a.nll, rel=0, abs=1e-13)
    np.testing.assert_allclose(b["prediction_gradient"], a.prediction_gradient, atol=1e-15, rtol=0)


def test_soft_visibility_and_frequency_finite_derivatives():
    y = np.array([0.0, 50.0])
    p = np.array([[1.0, 100.0, 200.0], [50.0, 300.0, 1000.0]])
    v = np.array([[0.2, 0.5, 0.9], [0.1, 0.4, 0.7]])
    result = soft(y, p, v, HARD60_SCORE)
    for name, values in [("visibility", v), ("prediction", p)]:
        for index in np.ndindex(values.shape):
            plus = values.copy()
            minus = values.copy()
            # Five-point stencil avoids visibility truncation and tiny-step cancellation.
            step = 1e-4 if name == "visibility" else 1e-2
            plus[index] += step
            minus[index] -= step
            argsplus = (y, p, plus) if name == "visibility" else (y, plus, v)
            argsminus = (y, p, minus) if name == "visibility" else (y, minus, v)
            near = (
                soft(*argsplus, HARD60_SCORE)["nll"] - soft(*argsminus, HARD60_SCORE)["nll"]
            )
            plus[index] += step
            minus[index] -= step
            far = soft(*argsplus, HARD60_SCORE)["nll"] - soft(*argsminus, HARD60_SCORE)["nll"]
            finite = (8 * near - far) / (12 * step)
            assert result[name + "_gradient"][index] == pytest.approx(finite, rel=0, abs=2e-9)


def test_invalid_visibility_rejected():
    with pytest.raises(ValueError):
        soft([0], np.ones((1, 3)), np.full((1, 3), 1.1), HARD60_SCORE)
