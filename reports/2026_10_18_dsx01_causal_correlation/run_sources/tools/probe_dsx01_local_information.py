"""Local curvature of the nuisance-integrated bound, not calibrated confidence."""

import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from prototype_dsx01_remeasured_position import apply_measurements
from report_dsx01_joint_marginal import reference_xy
from report_dsx01_radio_orbit_followup import CASES, OUTPUT, problem_for
from run_dsx01_clock_transfer import measurement_path


def local_curvature(function, point, step=0.1):
    x = np.asarray(point, float)
    if x.shape != (2,) or not np.isfinite(x).all() or not np.isfinite(step) or step <= 0:
        raise ValueError("finite two-coordinate point and positive step required")
    e = np.eye(2) * step
    centre = float(function(x))
    plus = np.array([function(x + v) for v in e])
    minus = np.array([function(x - v) for v in e])
    gradient = (plus - minus) / (2 * step)
    hessian = np.diag((plus + minus - 2 * centre) / step**2)
    hessian[0, 1] = hessian[1, 0] = (
        function(x + e[0] + e[1])
        - function(x + e[0] - e[1])
        - function(x - e[0] + e[1])
        + function(x - e[0] - e[1])
    ) / (4 * step**2)
    eigenvalues = np.linalg.eigvalsh(hessian)
    covariance = 2 * np.linalg.inv(hessian) if eigenvalues.min() > 0 else None
    return dict(
        cost=centre,
        gradient=gradient,
        hessian=hessian,
        hessian_eigenvalues=eigenvalues,
        formal_covariance_km2=covariance,
        formal_principal_sigma_km=(
            np.sqrt(np.linalg.eigvalsh(covariance)) if covariance is not None else None
        ),
    )


def run():
    output = []
    for case in CASES:
        scan = Scan(case)
        apply_measurements(
            scan, json.loads(measurement_path(case).read_text())["points"], "glrt300"
        )
        for variant, stem, configuration in (
            ("baseline", "joint_marginal", "robust"),
            ("window_precise", "precision_control", "window_precise"),
        ):
            path = (
                ROOT / f"reports/2026_10_18_dsx01_{stem}" / case / configuration / "endpoints.json"
            )
            fits = json.loads(path.read_text())["fits"]
            for arm, fit in fits.items():
                p = problem_for(scan, fit, variant)
                x = np.array(fit["parameters"])

                def cost(point, p=p):
                    z = p.residual(point)
                    return float(z @ z)

                values = local_curvature(cost, x)
                truth = reference_xy()
                output.append(
                    dict(
                        case=case,
                        variant=variant,
                        arm=arm,
                        finite_difference_step_km=0.1,
                        **values,
                        GPS_minus_endpoint_cost=cost(truth) - values["cost"],
                        evaluation_GPS_not_used_for_fit_or_curvature=True,
                        conditional_on_frozen_labels_aliases_and_numerical_orbit_references=True,
                        bound_curvature_is_not_calibrated_position_confidence=True,
                    )
                )
            print(json.dumps(dict(case=case, variant=variant)), flush=True)
    write(OUTPUT / "local_information.json", output)


if __name__ == "__main__":
    run()
