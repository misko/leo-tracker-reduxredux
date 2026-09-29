"""Verify receiver sign/order and analytic chain rule independently of RF."""

import numpy as np
import pytest
from pooled_timing import PooledTiming


class Quadratic:
    def evaluate(self, x, gradient=True, held=False):
        weights = np.arange(1, len(x) + 1)
        return {
            "score": float(-np.dot(weights * x, x) / 2),
            "gradient": -weights * x if gradient else np.zeros_like(x),
            "rows": [{"held": 17}] if held else [],
        }


@pytest.mark.parametrize("n", [4, 8])
def test_gradient_with_unequal_receiver_and_recording_sensitivities(n):
    model = PooledTiming(Quadratic(), n)
    x = np.linspace(-0.7, 0.9, n + 3)
    result = model.evaluate(x, held=True)
    assert result["rows"] == [{"held": 17}]
    for axis in range(len(x)):
        shift = np.eye(len(x))[axis] * 1e-5
        finite = (
            model.evaluate(x + shift, gradient=False)["score"]
            - model.evaluate(x - shift, gradient=False)["score"]
        ) / 2e-5
        assert abs(finite - result["gradient"][axis]) < 1e-8
    value, gradient = model.value_gradient(x)
    assert value == -result["score"]
    np.testing.assert_array_equal(gradient, -result["gradient"])


def test_receiver_order_and_box_limits():
    model = PooledTiming(Quadratic(), 2)
    np.testing.assert_array_equal(model.expand([1, 2, 3, -4, 2]), [1, 2, 2, -5, 4, -3])
    for delta in (-2, 2):
        for center in (-4, 4):
            assert max(abs(model.expand([0, 0, center, center, delta])[2:])) <= 5
    with pytest.raises(ValueError):
        model.expand([1, 2, 3])
