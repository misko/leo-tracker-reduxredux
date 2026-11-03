"""Fixed blind endpoints: numerical backend and latent-precision convergence checks."""

import json
import time

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from dsx01_grouped_student import student_joint_bound as grouped_bound
from dsx01_robust_joint import student_joint_bound as original_bound
from prototype_dsx01_remeasured_position import apply_measurements
from report_dsx01_radio_orbit_followup import CASES, OUTPUT, problem_for
from run_dsx01_clock_transfer import measurement_path


def run():
    records = {}
    for case in CASES:
        scan = Scan(case)
        apply_measurements(
            scan, json.loads(measurement_path(case).read_text())["points"], "glrt300"
        )
        path = ROOT / "reports/2026_10_18_dsx01_window_noise" / case / "window_noise/endpoints.json"
        fit = json.loads(path.read_text())["fits"]["c0"]
        p = problem_for(scan, fit, "window_noise")
        x = np.array(fit["parameters"])
        design = p.calculate(x)
        raw = p.values - p.q * design["intercept"]
        timings, values, results = {}, {}, {}
        for name, kernel, iterations in (
            ("original_24", original_bound, 24),
            ("grouped_24", grouped_bound, 24),
            ("grouped_128", grouped_bound, 128),
        ):
            before = time.perf_counter()
            value = kernel(
                raw, design["features"], p.point_noise, p.noise_groups, iterations=iterations
            )
            timings[name] = time.perf_counter() - before
            results[name] = value
            values[name] = dict(
                score=float(value["residual"] @ value["residual"]),
                precision_iterations=value["precision_iterations"],
                final_log_precision_change=value["final_log_precision_change"],
            )
        old, fast, converged = [results[k] for k in ("original_24", "grouped_24", "grouped_128")]
        score_error = abs(values["original_24"]["score"] - values["grouped_24"]["score"])
        native_error = float(
            np.max(abs(old["conditional_residual_hz"] - fast["conditional_residual_hz"]))
        )
        if score_error > 1e-5 or native_error > 1e-4:
            raise ValueError(f"numerical backend changed the objective: {case}")
        records[case] = dict(
            controls=values,
            seconds=timings,
            backend_score_error=score_error,
            backend_maximum_native_error_hz=native_error,
            convergence_score_change=values["grouped_128"]["score"] - values["grouped_24"]["score"],
            convergence_native_RMS_change_hz=float(
                np.sqrt(
                    np.mean(
                        (converged["conditional_residual_hz"] - fast["conditional_residual_hz"])
                        ** 2
                    )
                )
            ),
            geographic_refit_performed=False,
        )
        print(json.dumps(dict(case=case, **records[case])), flush=True)
    write(OUTPUT / "precision_backend_checks.json", records)


if __name__ == "__main__":
    run()
