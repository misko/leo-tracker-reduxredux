"""Matched tighter inner-solver checks at frozen S05 endpoints; no new search."""

import json
import sys
from functools import partial

import numpy as np
from associate_merged_track_catalogue import write
from map_dsx01_clean_region import factory, finite_gradient, loss
from run_dsx01_clean_region import OUTPUT, load_scan


def run():
    case = "DSX01-S05"
    scan, sigma = load_scan(case)
    scan.strict_causal_history = json.loads((OUTPUT / case / "causal_history.json").read_text())
    rows = []
    for name in ("tail_4", "frame_linked_100"):
        data = json.loads((OUTPUT / case / "surfaces" / name / "result.json").read_text())
        for arm, row in data["arms"].items():
            p = factory(
                scan,
                data["selected_assignment_node"],
                sigma,
                name,
                arm == "fitted_c",
                reference=row["phase_reference_s"],
            )
            x = np.array(row["fit"]["parameters"])
            before = p.calculate(x)
            old_score = loss(p, x)
            old_gradient = finite_gradient(lambda v, p=p: loss(p, v), x)
            step = 0.05
            eye = np.eye(2) * step
            hessian = np.diag(
                [(loss(p, x + v) + loss(p, x - v) - 2 * old_score) / step**2 for v in eye]
            )
            hessian[0, 1] = hessian[1, 0] = (
                loss(p, x + eye[0] + eye[1])
                - loss(p, x + eye[0] - eye[1])
                - loss(p, x - eye[0] + eye[1])
                + loss(p, x - eye[0] - eye[1])
            ) / (4 * step**2)
            module = sys.modules[type(p).__module__]
            original = module.hierarchical_bound
            try:
                module.hierarchical_bound = partial(original, iterations=2048)
                after = p.calculate(x)
                new_score = loss(p, x)
                new_gradient = finite_gradient(lambda v, p=p: loss(p, v), x)
            finally:
                module.hierarchical_bound = original
            eigenvalues = np.linalg.eigvalsh(hessian)
            shift = (
                -np.linalg.solve(hessian, new_gradient - old_gradient)
                if min(eigenvalues) > 0
                else None
            )
            rows.append(
                dict(
                    case=case,
                    method=name,
                    arm=arm,
                    point_frozen=True,
                    matched_c0_fitted_c_inner_budgets=[256, 2048],
                    before_precision_change=before["final_log_precision_change"],
                    after_precision_change=after["final_log_precision_change"],
                    score_difference=new_score - old_score,
                    maximum_conditional_mean_difference_hz=float(
                        np.max(
                            abs(
                                after["conditional_residual_hz"] - before["conditional_residual_hz"]
                            )
                        )
                    ),
                    gradient_before=old_gradient,
                    gradient_after=new_gradient,
                    hessian_eigenvalues=eigenvalues,
                    local_quadratic_shift_estimate_m=None
                    if shift is None
                    else float(np.linalg.norm(shift) * 1000),
                    shift_estimate_is_not_a_refitted_position=True,
                )
            )
    write(OUTPUT / "precision_cap_check.json", rows)
    print(len(rows), "matched frozen checks", flush=True)


if __name__ == "__main__":
    run()
