"""Conditional signal/background evidence at completed blind endpoints only."""

import json
from math import lgamma

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from dsx01_satellite_prior_controls import SatellitePriorControls
from dsx01_smooth_background import background_logprob
from prototype_dsx01_remeasured_position import apply_measurements
from run_dsx01_clock_transfer import measurement_path
from run_dsx01_satellite_prior_controls import OUTPUT


def run():
    evidence = {}
    for case in (f"DSX01-S0{k}" for k in range(1, 6)):
        path = OUTPUT / case / "normal/endpoints.json"
        fit = json.loads(path.read_text())["fits"]["c0"]
        scan = Scan(case)
        apply_measurements(
            scan, json.loads(measurement_path(case).read_text())["points"], "glrt300"
        )
        p = SatellitePriorControls(
            scan,
            dict(rows=fit["rows"], state=fit["state"]),
            False,
            variant="normal",
            sigma=fit["diagnostics"]["noise_sigma_hz"],
            reference=np.array(fit["diagnostics"]["phase_reference_s"]),
            aliases=fit["aliases"],
            point_noise=fit["diagnostics"]["point_noise_sigma_hz"],
        )
        result = p.calculate(np.array(fit["parameters"]))
        u = result["features"] / p.point_noise[:, None]
        weighted = u * np.sqrt(result["noise_precision"][p.noise_groups, None])
        root = np.linalg.cholesky(np.eye(u.shape[1]) + weighted.T @ weighted)
        variance = np.sum(np.linalg.solve(root, u.T) ** 2, axis=0)
        expected_square = (result["conditional_residual_hz"] / p.point_noise) ** 2 + variance
        rows = []
        for i, sl, row in zip(p.members, p.slices, p.rows, strict=True):
            n = int(sl.stop - sl.start)
            alpha, beta = (4 + n) / 2, (4 + expected_square[sl].sum()) / 2
            signal = (
                lgamma(alpha)
                - lgamma(2)
                + 2 * np.log(2)
                - alpha * np.log(beta)
                - n / 2 * np.log(2 * np.pi)
                - np.log(p.point_noise[sl]).sum()
            )
            background = background_logprob(p.values[sl], p.flat_times[sl], p.point_noise[sl])
            log_odds = np.log(0.95 / 0.05) + signal - background["log_probability"]
            probability = float(np.exp(-np.logaddexp(0, -log_odds)))
            rows.append(
                dict(
                    component=scan.tracks[i]["key"],
                    norad=row["candidate_norad"],
                    points=n,
                    conditional_signal_probability=probability,
                    log_signal_vs_background=signal - background["log_probability"],
                    background_degree_posterior=background["degree_posterior"],
                )
            )
        evidence[case] = sorted(rows, key=lambda r: r["conditional_signal_probability"])
        print(
            json.dumps(
                dict(
                    case=case,
                    curves=len(rows),
                    background_favored_curves=sum(
                        r["conditional_signal_probability"] < 0.5 for r in rows
                    ),
                    background_favored_points=sum(
                        r["points"] for r in rows if r["conditional_signal_probability"] < 0.5
                    ),
                )
            ),
            flush=True,
        )
    write(OUTPUT / "conditional_smooth_background.json", evidence)


if __name__ == "__main__":
    run()
