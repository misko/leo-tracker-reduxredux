"""Controlled combination of small receiver drift and causal orbit-shape error."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from iterate_dsx01_position_nominations import AnchoredFamilies, fit_once
from prototype_s01_causal_shape import SOURCE, CausalShapeFamilies

OUTPUT = ROOT / "reports/2026_10_18_s01_joint_radio_orbit"


class WideDriftProblem:
    """Keep data identical; replace only the four receiver/band drift priors."""

    def __init__(self, problem):
        self.problem = problem
        self.lower, self.upper = np.array(problem.lower), np.array(problem.upper)
        for k, (key, scale) in enumerate(problem.coordinates):
            if key[0] == "beta" and 4 <= key[1] < 8:
                self.lower[k], self.upper[k] = -750 / scale, 750 / scale

    def __getattr__(self, name):
        return getattr(self.problem, name)

    def residual(self, x, *, details=False):
        result = self.problem.residual(x, details=details)
        r, diagnostics = result if details else (result, None)
        p = self.problem
        tail = len(p.labels) + sum(1 if p.method == "family_rate" else 2 for _ in p.extra_labels)
        if p.method == "receiver_smooth":
            tail += p.starts["smooth"].size
        tail += len(getattr(p, "shape_labels", []))
        start = len(r) - tail - 4
        r[start : start + 4] *= 0.25  # sigma 0.5 -> 2 Hz/s, with the same native units.
        return (r, diagnostics) if details else r


def radio_problem(scan, seed, method, fitted_c, anchor, *, sigma):
    p = (
        CausalShapeFamilies(scan, seed, method, fitted_c, anchor, sigma=sigma)
        if sigma
        else AnchoredFamilies(scan, seed, method, fitted_c, anchor)
    )
    return WideDriftProblem(p)


def run(method, sigmas=(0.0, 1.0, 3.0)):
    directory = OUTPUT / method
    directory.mkdir(parents=True, exist_ok=True)
    scan = Scan("DSX01-S01")
    seed = json.loads((SOURCE / f"{method}_center.json").read_text())
    output = directory / "endpoints.json"
    results = json.loads(output.read_text()) if output.exists() else {}
    write(
        directory / "protocol.json",
        dict(
            no_evaluation_GPS_or_oracle_seed=True,
            controlled_factorial_reference="2026_10_18_s01_causal_shape",
            same_center_labels_observations_and_geographic_grid=True,
            receiver_band_drift_sigma_hz_s=2,
            receiver_band_drift_bound_hz_s=5,
            causal_shape_prior_sigmas=list(sigmas),
            same_c0_fitted_c_budgets=True,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for sigma in sigmas:
        name = f"wide_shape_sigma_{sigma:g}"
        if all(f"{name}/{arm}" in results for arm in ("c0", "fitted_c")):
            continue

        def factory(scan, seed, method, fitted_c, anchor, scale=sigma):
            return radio_problem(scan, seed, method, fitted_c, anchor, sigma=scale)

        fits = fit_once(scan, seed, method, (0.0, 0.0), problem_class=factory)
        for arm, fit in fits.items():
            results[f"{name}/{arm}"] = fit
        write(output, results)
        print(
            json.dumps(
                dict(
                    method=method,
                    sigma=sigma,
                    positions={arm: list(f["east_north_km"]) for arm, f in fits.items()},
                    drift_hz_s={
                        arm: list(f["state"]["beta"][4:8] / 150) for arm, f in fits.items()
                    },
                )
            ),
            flush=True,
        )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=METHODS, required=True)
    a = parser.parse_args()
    run(a.method)
