"""One alternative-solver continuation; original qualification stays mandatory."""
import numpy as np
from scipy.optimize import minimize


def eligible(result, qualification, bounds):
    x = np.asarray(result.x, dtype=float)
    bounds = np.asarray(bounds, dtype=float)
    grad = qualification.get("gradient_max_abs")
    audit = qualification.get("gradient_audit_max_abs")
    return bool(not result.success and not qualification["qualified"]
                and not qualification["boundary"]
                and x.shape == (len(bounds),) and np.isfinite(x).all()
                and np.isfinite(result.fun) and np.isfinite(result.jac).all()
                and np.all(x-bounds[:, 0] >= 0.001)
                and np.all(bounds[:, 1]-x >= 0.001)
                and grad is not None and 0 <= grad <= 0.01
                and audit is not None and 0 <= audit <= 0.02)


def recover(model, original, qualification, bounds, qualify_fn, minimize_fn=minimize):
    if not eligible(original, qualification, bounds):
        raise ValueError("only failed, interior, finite, near-stationary fits may continue")

    def objective(x):
        row = model.evaluate(x, gradient=True)
        return -float(row["score"]), -np.asarray(row["gradient"], dtype=float)

    result = minimize_fn(objective, np.asarray(original.x, dtype=float).copy(),
                         jac=True, method="SLSQP", bounds=np.asarray(bounds).tolist(),
                         options={"maxiter": 100, "ftol": 1e-12, "disp": False})
    checked = qualify_fn(result, model, np.asarray(bounds))
    accepted = bool(checked["qualified"] and result.success
                    and np.isfinite(result.fun) and result.fun <= original.fun + 1e-7)
    return result, checked, accepted
