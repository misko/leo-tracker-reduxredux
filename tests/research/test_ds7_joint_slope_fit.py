import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))
from ds7_joint_slope_fit import fit  # noqa: E402


def test_joint_recovery_and_nested_baseline():
    truth = np.array([0.2, -0.3, 0.1, 2.0])
    # Positive, correlated quadratic with a known joint optimum.
    design = np.array([[2.0, 0, 0, 1], [0, 3, 0, 0.2], [0, 0, 4, -0.1], [0, 0, 0, 1]])
    matrix = design.T @ design

    def evaluate(x):
        residual = x - truth
        return {"score": -0.5 * residual @ matrix @ residual, "gradient": -matrix @ residual}

    receipts = []
    baseline = fit(evaluate, np.zeros(3), False)
    augmented = fit(evaluate, np.zeros(3), True, receipts.append)
    assert len(receipts) == 3
    assert augmented["selected"]["qualified"]
    assert augmented["selected"]["x"] == pytest.approx(truth, abs=1e-4)
    assert augmented["selected"]["training_log_score"] > baseline["selected"]["training_log_score"]
    assert all(len(r["x"]) == 3 for r in baseline["starts"])
    for a, b in zip(baseline["starts"], augmented["starts"], strict=True):
        assert a["start"] == b["start"][:3]
        assert b["start"][3] == 0


def test_boundary_fit_retained_but_unqualified():
    def evaluate(x):
        target = np.array([0.0, 0.0, 0.0, 30.0])
        return {"score": -np.sum((x - target) ** 2), "gradient": -2 * (x - target)}

    result = fit(evaluate, np.zeros(3), True)
    assert result["selected"]["success"]
    assert result["selected"]["boundary_hit"]
    assert not result["selected"]["qualified"]
    assert result["selected"]["x"][3] == pytest.approx(20)
