import sys
from pathlib import Path

import numpy as np
import pytest

REPORTS = Path(__file__).resolve().parent.parent
sys.path[:0] = [
    str(REPORTS / f"2026_10_08_position_error_iter{n}") for n in ("24", "19", "04", "10")
]
from slope_prior import SlopePrior  # noqa: E402
from test_joint_clock import setup  # noqa: E402


@pytest.mark.parametrize("sigma", [0.25, 0.5, 0.75])
def test_nuisance_derivative_at_tighter_prior(sigma):
    base, old = setup()
    knots = old.initial_clock.reshape(2, -1) @ old.null.T
    model = SlopePrior(base, old.nodes, knots, np.full(len(base.bank.numbers), 50.0), sigma)
    vector = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    clock = model.initial_clock.copy()
    clock[model.slope_slice] = 15
    _, _, analytic, _ = model.evaluate_joint(vector, clock)
    numeric = []
    for delta in np.eye(len(clock)) * 1e-4:
        numeric.append(
            (
                model.evaluate_joint(vector, clock + delta)[0]
                - model.evaluate_joint(vector, clock - delta)[0]
            )
            / 2e-4
        )
    np.testing.assert_allclose(analytic, numeric, atol=2e-4, rtol=2e-4)
