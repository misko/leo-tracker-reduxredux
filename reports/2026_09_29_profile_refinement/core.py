"""Training-only probe selection and bounded joint refinement."""

import numpy as np
from scipy.optimize import minimize


def starts(profiles):
    result = []
    for radius in (0.25, 1.0):
        candidates = [p for p in profiles if p["qualified"] and p["radius_km"] == radius]
        if not candidates:
            raise ValueError("No audited probe at declared radius")
        p = max(candidates, key=lambda p: p["score"])
        result.append(
            dict(
                radius_km=radius,
                axis=p["axis"],
                sign=p["sign"],
                x=p["position"] + p["selected"]["timing"],
                score=p["score"],
            )
        )
    return result


def refine(evaluate, initial):
    limits = np.r_[[12.0, 12.0], np.full(len(initial) - 2, 5.0)]

    def objective(x):
        r = evaluate(x)
        return -r["score"], -np.asarray(r["gradient"])

    fit = minimize(
        objective,
        initial,
        jac=True,
        method="L-BFGS-B",
        bounds=list(zip(-limits, limits, strict=True)),
        options=dict(maxiter=120, maxfun=180, ftol=1e-14, gtol=1e-8, maxls=30),
    )
    ev = evaluate(fit.x)
    assert abs(ev["score"] + fit.fun) < 1e-7
    checks = []
    for axis in range(len(initial)):
        for step in (0.0005, 0.00025) if axis < 2 else (0.0000625, 0.00003125):
            delta = np.eye(len(initial))[axis] * step
            numerical = (
                evaluate(fit.x + delta, gradient=False)["score"]
                - evaluate(fit.x - delta, gradient=False)["score"]
            ) / (2 * step)
            checks.append(
                dict(
                    axis=axis,
                    step=step,
                    numerical=float(numerical),
                    difference=float(abs(numerical - ev["gradient"][axis])),
                    crosses_node=bool(
                        axis >= 2
                        and np.floor((fit.x[axis] - step) * 4) != np.floor((fit.x[axis] + step) * 4)
                    ),
                )
            )
    agreement = [
        abs(checks[2 * i]["numerical"] - checks[2 * i + 1]["numerical"])
        for i in range(len(initial))
    ]
    boundary = bool(np.any(limits - abs(fit.x) < 0.001))
    qualified = bool(
        fit.success
        and not boundary
        and max(abs(ev["gradient"])) <= 0.01
        and all(c["difference"] < 0.002 and not c["crosses_node"] for c in checks)
        and max(agreement) < 0.002
    )
    return dict(
        initial=list(initial),
        x=fit.x.tolist(),
        success=bool(fit.success),
        message=str(fit.message),
        evaluations=int(fit.nfev),
        boundary=boundary,
        score=float(ev["score"]),
        gradient=np.asarray(ev["gradient"]).tolist(),
        checks=checks,
        step_agreement=agreement,
        qualified=qualified,
    )
