"""Local objective curvature diagnostic, not a calibrated position posterior."""

import json

import numpy as np
from associate_merged_track_catalogue import write
from build_dsx01_causal_forecast import OUTPUT
from compare_dsx01_retention_localization import METHODS, Scan
from prototype_dsx01_continuous_position import CENTER
from prototype_dsx01_receiver_geometry import OUTPUT as BASELINE
from prototype_dsx01_receiver_geometry import geometry_problem
from report_dsx01_model_iterations import REFERENCE


def run(case="DSX01-S05"):
    scan = Scan(case)
    target = np.array(
        [
            (REFERENCE[1] - CENTER[1]) * 111.32 * np.cos(np.deg2rad(CENTER[0])),
            (REFERENCE[0] - CENTER[0]) * 111,
        ]
    )
    rows = []
    for method in METHODS:
        data = json.loads((BASELINE / case / method / "endpoints.json").read_text())
        for arm in ("c0", "fitted_c"):
            fit = data[f"mean_10_height_0/{arm}"]
            p = geometry_problem(
                scan,
                dict(rows=fit["rows"], state=fit["state"]),
                method,
                arm == "fitted_c",
                fit["east_north_km"],
                mean_sigma=10,
                height_sigma=0,
            )
            p.problem.alias = list(fit["aliases"])
            chosen = min(fit["fits"], key=lambda f: f["score"])
            x = np.array(chosen["parameters"])
            r = p.residual(x)
            columns = []
            for k in range(len(x)):
                a, b = x.copy(), x.copy()
                a[k] -= 1e-3
                b[k] += 1e-3
                columns.append((p.residual(b) - p.residual(a)) / 0.002)
            jac = np.column_stack(columns)
            jp, jn = jac[:, :2], jac[:, 2:]
            projected = jp - jn @ np.linalg.lstsq(jn, jp, rcond=1e-10)[0]
            information = projected.T @ projected
            eigenvalue, eigenvector = np.linalg.eigh(information)
            delta = target - x[:2]
            rows.append(
                dict(
                    case=case,
                    method=method,
                    arm=arm,
                    local_residual_Gauss_Newton_curvature_not_calibrated_covariance=True,
                    information_per_km2=information,
                    unit_quadratic_cost_axis_lengths_km=1 / np.sqrt(eigenvalue),
                    axes_east_north=eigenvector,
                    GPS_displacement_unit_cost_distance=float(np.sqrt(delta @ information @ delta)),
                    endpoint_position_gradient=2 * jp.T @ r,
                    endpoint_nuisance_gradient_max=float(max(abs(2 * jn.T @ r))),
                    optimizer_stopped=chosen["stopped"],
                    closest_bound_distance=float(min(np.min(x - p.lower), np.min(p.upper - x))),
                )
            )
    write(OUTPUT / "position_curvature.json", rows)
    for r in rows:
        print(
            r["method"],
            r["arm"],
            r["unit_quadratic_cost_axis_lengths_km"],
            r["GPS_displacement_unit_cost_distance"],
            flush=True,
        )
    return rows


if __name__ == "__main__":
    run()
