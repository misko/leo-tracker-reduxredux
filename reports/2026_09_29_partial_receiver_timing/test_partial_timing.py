"""Independent derivative and invariance checks for the partial-pooling penalty."""

import numpy as np
import pytest
from partial_timing import PartialTiming


class Quadratic:
    def evaluate(self, x, gradient=True, held=False):
        w = np.arange(1, len(x) + 1)
        return {
            "score": float(-np.dot(w * x, x) / 2),
            "gradient": -w * x if gradient else np.zeros_like(x),
            "rows": [{"held_log_score": 73}] if held else [],
        }


@pytest.mark.parametrize("n", [4, 8])
@pytest.mark.parametrize("sigma", [0.1, 0.5, 2.0])
def test_penalized_gradient_and_unpenalized_held(n, sigma):
    base = Quadratic()
    model = PartialTiming(base, n, sigma)
    x = np.random.default_rng(123).normal(size=2 + 2 * n)
    r = model.evaluate(x, held=True)
    assert r["rows"] == base.evaluate(x, held=True)["rows"]
    assert r["raw_training_log_score"] - r["penalty"] == r["score"]
    for axis in range(len(x)):
        d = np.eye(len(x))[axis] * 1e-5
        finite = (
            model.evaluate(x + d, gradient=False)["score"]
            - model.evaluate(x - d, gradient=False)["score"]
        ) / 2e-5
        assert abs(finite - r["gradient"][axis]) < 1e-6
    changed = x.copy()
    changed[2 + n :] += 1.75
    assert abs(model.evaluate(changed)["penalty"] - r["penalty"]) < 1e-9


def test_common_nonzero_difference_has_zero_penalty_and_gradient_correction():
    base = Quadratic()
    model = PartialTiming(base, 4, 0.1)
    x = np.r_[1.0, -1.0, [-1.0, 0.0, 1.0, 2.0], [1.0, 2.0, 3.0, 4.0]]
    r = model.evaluate(x)
    assert r["penalty"] == 0 and r["common_difference_s"] == 2
    np.testing.assert_array_equal(r["gradient"], base.evaluate(x)["gradient"])


def test_invalid_scale_or_shape_is_rejected():
    for sigma in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            PartialTiming(Quadratic(), 4, sigma)
    with pytest.raises(ValueError):
        PartialTiming(Quadratic(), 4, 1).evaluate(np.zeros(9))
