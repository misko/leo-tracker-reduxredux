"""Blind correlated RX drift prior: shared common mode, small band contrast."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from iterate_dsx01_position_nominations import AnchoredFamilies, fit_once
from prototype_s01_causal_shape import SOURCE, CausalShapeFamilies

OUTPUT = ROOT / "reports/2026_10_18_s01_receiver_drift"


class ReceiverDriftProblem:
    """Reparameterize four native band drifts into two RX means and contrasts."""

    def __init__(self, problem, mean_sigma=5.0, contrast_sigma=0.5):
        self.problem = problem
        if mean_sigma <= 0 or contrast_sigma <= 0:
            raise ValueError("positive drift scales required")
        self.mean_sigma, self.contrast_sigma = mean_sigma, contrast_sigma
        self.initial = np.array(problem.initial)
        self.lower = np.array(problem.lower)
        self.upper = np.array(problem.upper)
        self.coordinates = list(problem.coordinates)
        self.pairs = []
        indexes = {tuple(key): (k, scale) for k, (key, scale) in enumerate(problem.coordinates)}
        for receiver in range(2):
            low, sl = indexes["beta", 4 + 2 * receiver]
            high, sh = indexes["beta", 5 + 2 * receiver]
            dl, dh = self.initial[low] * sl / 150, self.initial[high] * sh / 150
            self.initial[low] = (dl + dh) / 2 / mean_sigma
            self.initial[high] = (dh - dl) / 2 / contrast_sigma
            self.lower[[low, high]] = -3
            self.upper[[low, high]] = 3
            self.coordinates[low] = (("RX_drift_mean_hz_s", receiver + 1), mean_sigma)
            self.coordinates[high] = (("RX_drift_band_contrast_hz_s", receiver + 1), contrast_sigma)
            self.pairs.append((low, high, sl, sh))

    def __getattr__(self, name):
        return getattr(self.problem, name)

    def native_parameters(self, x):
        native = np.array(x)
        for low, high, sl, sh in self.pairs:
            mean, difference = x[low] * self.mean_sigma, x[high] * self.contrast_sigma
            native[low] = 150 * (mean - difference) / sl
            native[high] = 150 * (mean + difference) / sh
        return native

    def decode(self, x):
        return self.problem.decode(self.native_parameters(x))

    def predicted(self, x):
        return self.problem.predicted(self.native_parameters(x))

    def association_state(self, x):
        native = self.native_parameters(x)
        if hasattr(self.problem, "association_state"):
            return self.problem.association_state(native)
        return self.problem.decode(native)

    def residual(self, x, *, details=False):
        result = self.problem.residual(self.native_parameters(x), details=details)
        r, diagnostics = result if details else (result, None)
        p = self.problem
        tail = len(p.labels) + sum(1 if p.method == "family_rate" else 2 for _ in p.extra_labels)
        if p.method == "receiver_smooth":
            tail += p.starts["smooth"].size
        tail += len(getattr(p, "shape_labels", []))
        tail += len(getattr(p, "motion_labels", []))
        tail += getattr(p, "altitude_parameters", 0)
        tail += getattr(p, "timing_parameters", 0)
        start = len(r) - tail - 4
        r[start : start + 4] = [
            x[self.pairs[0][0]],
            x[self.pairs[0][1]],
            x[self.pairs[1][0]],
            x[self.pairs[1][1]],
        ]
        return (r, diagnostics) if details else r


def receiver_problem(scan, seed, method, fitted_c, anchor, *, mean_sigma, shape_sigma):
    p = (
        CausalShapeFamilies(scan, seed, method, fitted_c, anchor, sigma=shape_sigma)
        if shape_sigma
        else AnchoredFamilies(scan, seed, method, fitted_c, anchor)
    )
    return ReceiverDriftProblem(p, mean_sigma=mean_sigma)


def run(method, means=(1.0, 5.0, 10.0), shapes=(0.0, 1.0)):
    directory = OUTPUT / method
    directory.mkdir(parents=True, exist_ok=True)
    scan = Scan("DSX01-S01")
    seed = json.loads((SOURCE / f"{method}_center.json").read_text())
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    write(
        directory / "protocol.json",
        dict(
            no_reference_GPS_or_oracle_parameters=True,
            four_offsets_remain_independent=True,
            drift_hz_s="RX mean +/- band contrast",
            mean_prior_sigmas_hz_s=means,
            band_contrast_prior_sigma_hz_s=0.5,
            parameter_bounds_sigma=3,
            causal_shape_sigmas=shapes,
            same_raw_curved_points_candidates_geographic_starts_and_24_iteration_budgets_for_c_arms=True,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for mean in means:
        for shape in shapes:
            name = f"rx_mean_{mean:g}_shape_{shape:g}"
            if all(f"{name}/{arm}" in results for arm in ("c0", "fitted_c")):
                continue

            def factory(scan, seed, method, fitted_c, anchor, ms=mean, ss=shape):
                return receiver_problem(
                    scan, seed, method, fitted_c, anchor, mean_sigma=ms, shape_sigma=ss
                )

            fits = fit_once(scan, seed, method, (0.0, 0.0), problem_class=factory)
            for arm, fit in fits.items():
                results[f"{name}/{arm}"] = fit
            write(path, results)
            print(
                json.dumps(
                    dict(
                        method=method,
                        variant=name,
                        positions={arm: list(f["east_north_km"]) for arm, f in fits.items()},
                        native_drifts_hz_s={
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
