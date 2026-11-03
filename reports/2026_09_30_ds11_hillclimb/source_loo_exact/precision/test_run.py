import importlib.util
from pathlib import Path

import numpy as np


SPEC = importlib.util.spec_from_file_location("precision_tested", Path(__file__).with_name("run.py"))
precision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(precision)


class Quadratic:
    def __init__(self):
        self.center = np.asarray((1.0, -2.0, 0.25))
        self.hessian = np.asarray(((4.0, 0.5, 0.2), (0.5, 3.0, -0.1), (0.2, -0.1, 2.0)))

    def evaluate(self, x, gradient=True):
        residual = np.asarray(x) - self.center
        return {
            "score": float(7.0 - 0.5 * residual @ self.hessian @ residual),
            "gradient": -self.hessian @ residual,
        }


def test_hessian_newton_and_score_audits_recover_quadratic():
    model = Quadratic()
    x = np.asarray((1.3, -2.2, 0.4))
    evaluated = model.evaluate(x)
    estimated = precision.negative_hessian(model, x, precision.STEPS)
    summary = precision.hessian_summary(estimated)
    assert np.allclose(estimated, model.hessian, rtol=1e-9, atol=1e-9)
    assert summary["positive_definite"]
    assert summary["relative_asymmetry"] < 1e-9
    delta = np.linalg.solve(np.asarray(summary["symmetric"]), evaluated["gradient"])
    assert np.allclose(x + delta, model.center, rtol=0, atol=1e-10)
    audit = precision.coordinate_audit(
        model, x, precision.STEPS, evaluated["score"], evaluated["gradient"]
    )
    assert audit["max_absolute_discrepancy"] < 1e-9
    probes = precision.directional_probes(model, x, delta, (0, 1, 2), precision.BOUNDS)
    assert probes[1]["gradient_max_abs"] < 1e-9
    assert probes[1]["score"] > probes[0]["score"]


def test_finiteness_walk_rejects_nested_nonfinite():
    assert precision.all_finite({"a": [1.0, None, True]})
    assert not precision.all_finite({"a": [1.0, float("inf")]})
