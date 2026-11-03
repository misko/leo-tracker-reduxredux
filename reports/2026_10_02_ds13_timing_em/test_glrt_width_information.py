from types import SimpleNamespace

import numpy as np
import pytest
from glrt_width_information import WIDTHS, WidthObjective


def test_width_protocol_is_prespecified_and_keeps_broad_and_narrow_cases():
    assert WIDTHS == (400., 100., 50.)
    with pytest.raises(ValueError, match="positive finite"):
        WidthObjective(None, None, None, 0)


def test_rf_curvature_uses_current_width_for_cross_and_calibration_blocks(monkeypatch):
    import glrt_width_information

    class Jacobian:
        def transpose_multiply(self, weights):
            return np.array([np.sum(weights)])

    objective = object.__new__(WidthObjective)
    objective.size = 1
    objective.features = np.array([[2.], [3.]])
    objective.likelihood = SimpleNamespace(last_result={
        "row_association_probability": np.array([[.5], [.25]])})
    objective.base = SimpleNamespace(
        sigma_hz=50., last={}, predict=lambda *args, **kwargs: (None, None, Jacobian()),
        vector_gradient=lambda gradient, _vector: gradient)
    monkeypatch.setattr(glrt_width_information, "_fisher_system",
                        lambda *args: (np.array([[7.]]), None))
    actual = objective.curvature(np.zeros(2))
    np.testing.assert_allclose(actual, [[7., 1.75 / 2500.], [1.75 / 2500., 4.25 / 2500.]])
