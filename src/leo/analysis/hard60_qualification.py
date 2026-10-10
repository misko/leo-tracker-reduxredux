"""Reference-free retained-calibration trigger and one bounded Newton attempt."""

import time

import numpy as np

from leo.analysis import hard60_reduced_newton as newton


def qualify(
    objective,
    vector,
    saved_objective,
    *,
    retained,
    stage,
    independently_qualified,
    maximum_rounds=2,
    maximum_evaluations=100,
):
    """No alternate seeds or grid-level condition; preserve every ordinary candidate.

    Already accepted fits are unchanged. For an unqualified retained calibration
    state, one frozen100 polish attempt either independently qualifies or leaves
    the original failure available as a fallback receipt. No chained retries.
    independently_qualified means fit.converged after the full physical/KKT gate,
    never the optimizer's success flag (which may be true for an unqualified fit).
    """
    for value, limit in ((maximum_rounds, 2), (maximum_evaluations, 100)):
        if isinstance(value, bool) or int(value) != value or not 1 <= value <= limit:
            raise ValueError("Invalid bounded qualification budget")
    original = np.asarray(vector, float).copy()
    receipt = dict(
        original_vector=original.tolist(),
        saved_objective=float(saved_objective),
        stage=stage,
        retained=bool(retained),
        objective_evaluations=0,
        objective_verified=False,
        polish_elapsed_s=0.0,
        maximum_rounds=maximum_rounds,
        maximum_evaluations=maximum_evaluations,
        fit=None,
        qualified=False,
    )
    if (
        not retained
        or stage not in ("calibration-prefit", "calibration-postfit")
        or independently_qualified
    ):
        return dict(receipt, status="not-triggered")
    try:
        if (
            original.ndim != 1
            or not np.isfinite(original).all()
            or not np.isfinite(saved_objective)
        ):
            raise ValueError("Invalid saved vector or objective")
        problem = newton._Problem(
            objective, original, rf_arm="fitted-c", fixed_position=True, slope_half_width_hz_s=60
        )
        if not problem.feasible(original):
            return dict(receipt, status="infeasible-saved-state")
        _, geometry = newton.tangent_basis(problem, original)
    except Exception as error:
        return dict(receipt, status="qualification-invalid-state", error=repr(error))
    needed = (
        2 * geometry["tangent_dimension"] + 2
    )  # Initial evaluation + central sweep + one trial.
    receipt.update(geometry=geometry, minimum_first_round_evaluations=needed)
    if needed > maximum_evaluations:
        return dict(receipt, status="dimension-exceeds-budget")

    class VerifiedObjective:
        def __getattr__(self, name):
            return getattr(objective, name)

        def evaluate(self, candidate):
            receipt["objective_evaluations"] += 1
            assert receipt["objective_evaluations"] <= maximum_evaluations
            value = objective.evaluate(candidate)
            if receipt["objective_evaluations"] == 1:
                np.testing.assert_array_equal(candidate, original)
                np.testing.assert_allclose(value[0], saved_objective, rtol=0, atol=1e-6)
                receipt["objective_verified"] = True
            return value

    begun = time.monotonic()
    try:
        fit = newton.polish(
            VerifiedObjective(),
            original,
            maximum_rounds=maximum_rounds,
            maximum_evaluations=maximum_evaluations,
        )
        assert fit["evaluations"] == receipt["objective_evaluations"]
        receipt.update(
            status="qualified" if fit["converged"] else "unqualified",
            qualified=bool(fit["converged"]),
            fit=fit,
        )
    except Exception as error:
        receipt.update(status="failed", error=repr(error))
    receipt["polish_elapsed_s"] = time.monotonic() - begun
    return receipt
