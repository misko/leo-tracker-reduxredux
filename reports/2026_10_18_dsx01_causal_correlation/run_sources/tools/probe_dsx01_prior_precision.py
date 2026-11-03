"""Tighter latent-precision checks at saved blind endpoints, without geographic refits."""

import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_prior_bias_iterations import CASES, OUTPUT, ROOT, SPECS, problem_for
from compare_dsx01_retention_localization import Scan
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_satellite_prior_controls import orbital_prior_groups
from prototype_dsx01_remeasured_position import apply_measurements
from report_dsx01_joint_marginal import reference_xy
from run_dsx01_clock_transfer import measurement_path


def run():
    rows = []
    for case in CASES:
        targets = []
        for variant, (stem, _) in SPECS.items():
            path = ROOT / f"reports/2026_10_18_dsx01_{stem}" / case / variant / "endpoints.json"
            for arm, fit in json.loads(path.read_text())["fits"].items():
                if fit["diagnostics"]["final_log_precision_change"] >= 1e-5:
                    targets.append((variant, arm, fit))
        if not targets:
            continue
        scan = Scan(case)
        apply_measurements(
            scan, json.loads(measurement_path(case).read_text())["points"], "glrt300"
        )
        for variant, arm, fit in targets:
            p = problem_for(scan, fit, variant)
            for site, x in [
                ("blind_endpoint", np.array(fit["parameters"])),
                ("evaluation_GPS", reference_xy()),
            ]:
                original = p.calculate(x)
                features = original["features"] * original.get(
                    "prior_covariance_scales", np.ones(original["features"].shape[1])
                )
                prior = None
                if variant.startswith("tail_"):
                    prior = orbital_prior_groups(
                        features.shape[1],
                        p.hardware.shape[1] + p.smooth.shape[1],
                        p.labels,
                        p.supported_local,
                    )
                refined = hierarchical_bound(
                    p.values - p.q * original["intercept"],
                    features,
                    p.point_noise,
                    p.noise_groups,
                    prior_groups=prior,
                    powers=getattr(p, "power", 1.0),
                    prior_nu=float(variant.split("_")[-1]) if prior is not None else 4,
                    iterations=2048,
                )
                previous = original["residual"] @ original["residual"] - p.diagonal_logvolume
                row = dict(
                    case=case,
                    variant=variant,
                    arm=arm,
                    site=site,
                    cost_change=float(refined["residual"] @ refined["residual"] - previous),
                    native_mean_RMS_change_hz=float(
                        np.sqrt(
                            np.mean(
                                (
                                    refined["conditional_residual_hz"]
                                    - original["conditional_residual_hz"]
                                )
                                ** 2
                            )
                        )
                    ),
                    old_final_log_precision_change=original["final_log_precision_change"],
                    refined_final_log_precision_change=refined["final_log_precision_change"],
                    refined_iterations=refined["precision_iterations"],
                    GPS_only_in_diagnostic=True,
                    geographic_refit_performed=False,
                )
                rows.append(row)
                print(json.dumps(row), flush=True)
    write(OUTPUT / "precision_convergence_checks.json", rows)


if __name__ == "__main__":
    run()
